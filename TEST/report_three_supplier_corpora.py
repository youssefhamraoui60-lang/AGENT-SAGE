"""Reviewable per-case outcomes, with simulated and real evidence kept distinct."""
import json,csv,collections,hashlib,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'backend'))
from three_supplier_corpora import cases
from analyze_three_supplier_corpora import phase,evaluate
from app.services import business_store as db
baseline=phase('three-corpora-baseline');final=phase('three-corpora-final');specs={s['id']:s for s in cases()}
assert baseline['cases']==final['cases']==300 and baseline['messages']==final['messages']==4600
outdir=ROOT/'three-corpora-report';(outdir/'cases').mkdir(parents=True,exist_ok=True)
items={}
for i in range(4):
 for line in (ROOT/f'three-corpora-final-{i}.jsonl').read_text(encoding='utf-8').splitlines():
  item=json.loads(line);items[item['id']]=item
positive={p['case']:p for p in final['confirmation_forks']};denials={}
for i in range(4):
 for proof in json.loads((ROOT/f'three-corpora-denials-{i}.json').read_text(encoding='utf-8')):denials[proof['case']]=proof
assert set(positive)|set(denials)==set(specs)
grades={r['id']:r for r in final['results']};index=[]
for key,item in sorted(items.items()):
 spec=specs[key];assert [s['text'] for s in spec['steps']]==[t['text'] for t in item['turns']]
 proof=positive.get(key) or denials[key];created=key in positive and proof['passed'];grade=grades[key]
 state=item['turns'][-1].get('state',{});duplicates=[w for p in state.get('partners',[]) for w in p.get('operation',{}).get('duplicate_warnings',[])]
 observed='création sur copie SIMULÉE' if created else 'doublon SIMULÉ, création bloquée' if duplicates else 'confirmation refusée : annulé, incomplet, non pris en charge ou aucune création'
 packet={'id':key,'dataset':spec['dataset'],'source_file':spec['source_file'],'source_sha256':spec['sha256'],'expected':spec['oracle'],'observed':observed,'SIMULATED_SAGE':True,'passed_checks':grade['passed'],'failures':grade['failures'],'confirmation':proof,'messages':item['turns']}
 (outdir/'cases'/f'{key}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
 index.append({'case':key,'dataset':spec['dataset'],'messages':len(item['turns']),'checks_passed':grade['passed'],'observed':observed,'SIMULATED_CODE':proof.get('code',''),'confirmation_check_passed':proof['passed'],'failures':len(grade['failures']),'evidence':'cases/'+key+'.json'})
with (outdir/'index.csv').open('w',encoding='utf-8-sig',newline='') as stream:
 writer=csv.DictWriter(stream,fieldnames=list(index[0]));writer.writeheader();writer.writerows(index)
real={};raw_real_messages=0
for name in ('three-corpora-real','three-corpora-real-replay'):
 for p in (ROOT/name).glob('*.json'):
  if p.name in ('summary.json','progress.json'):continue
  item=json.loads(p.read_text(encoding='utf-8'));raw_real_messages+=len(item['turns']);real[item['id']]=item
realgrades=[evaluate(item) for item in real.values()]
realout={'cases':len(realgrades),'canonical_messages':sum(len(r['turns']) for r in real.values()),'messages_with_replays':raw_real_messages,'passed':sum(r['passed'] for r in realgrades),'failed':sum(not r['passed'] for r in realgrades),'results':realgrades}
(outdir/'real-evaluation.json').write_text(json.dumps(realout,ensure_ascii=False,indent=2),encoding='utf-8')
ids=[r['conversation_id'] for r in real.values() if r.get('conversation_id')]
with db.connection() as c:
 usage=c.execute("SELECT provider,status,count(*) AS calls,COALESCE(sum(input_tokens),0) AS input_tokens,COALESCE(sum(output_tokens),0) AS output_tokens,COALESCE(sum(estimated_cost_usd),0) AS estimated_cost_usd FROM chat_ai_usage WHERE conversation_id=ANY(%s::uuid[]) GROUP BY provider,status",(ids,)).fetchall()
 accounts=c.execute("SELECT count(DISTINCT a.id) AS accounts,bool_and(NOT a.active) AS all_deactivated FROM chat_accounts a JOIN chat_conversations c ON c.owner_id=a.id WHERE c.id=ANY(%s::uuid[])",(ids,)).fetchone()
assert accounts['all_deactivated']
consumption=[{k:str(v) if k=='estimated_cost_usd' else v for k,v in r.items()} for r in usage]
summary={'cases':300,'messages':4600,'baseline_passed':baseline['passed'],'baseline_failed':baseline['failed'],'final_passed':final['passed'],'final_failed':final['failed'],'simulated_confirmations':len(positive),'simulated_successes':sum(p['passed'] for p in positive.values()),'simulated_denial_checks':len(denials),'denial_checks_passed':sum(p['passed'] for p in denials.values()),'real_sample':{k:v for k,v in realout.items() if k!='results'},'real_usage_for_latest_conversations':consumption,'real_sage_writes':0,'all_real_test_accounts_deactivated':True}
(outdir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# Tests des trois fichiers fournisseurs','', '**Aucun fournisseur réel n’a été créé. Tous les codes F900… de cette campagne sont des résultats de Sage simulé.**','',f"Les trois fichiers contiennent **300 cas et 4 600 messages**. Chaque session démarre avec un nouveau brouillon, et tous ses messages sont envoyés dans l’ordre à FastAPI. Les dialogues d’origine restent sans écriture. Les confirmations sont testées sur des copies isolées : les états annulés, incomplets et non pris en charge doivent rester bloqués.",'','## Résultats mesurés','',f"Mode de panne IA simulée, backend réel et PostgreSQL isolé : première passe **{baseline['passed']} cas sans échec d’assertion / {baseline['failed']} en échec** ; après corrections **{final['passed']} / {final['failed']}**. Ce résultat mesure le repli et les règles contrôlées ; il ne mesure pas la compréhension de DeepSeek sur les 4 600 messages.",'',f"Confirmations sur copies : **{len(positive)} parcours de création simulée**, dont {sum(p['passed'] for p in positive.values())} réussis ; **{len(denials)} contrôles de refus**, dont {sum(p['passed'] for p in denials.values())} réussis. Chaque cas dispose d’un résultat et de la preuve des appels API dans l’index.",'',f"React avec DeepSeek et lectures Sage TEST réels : **{realout['cases']} cas / {realout['canonical_messages']} messages**, {realout['passed']} sans échec d’assertion et {realout['failed']} avec anomalies. Avec les rejeux ciblés : {raw_real_messages} messages réels effectivement envoyés. Les boutons de confirmation réelle sont interdits dans le navigateur.",'','| Corpus | Cas | Messages | Sans échec après corrections |','|---|---:|---:|---:|']
for dataset in ('darija','mixed','emails'):
 rows=[r for r in final['results'] if r['dataset']==dataset];lines.append(f"| {dataset} | {len(rows)} | {sum(r['messages'] for r in rows)} | {sum(r['passed'] for r in rows)} |")
lines+=['','## Corrections effectuées','', '- Réponse de reprise sûre après panne IA en mode local également ; conservation de l’état et du diagnostic, sans panne HTTP en cascade.', '- Une phrase de consigne en darija est refusée comme raison sociale au niveau du schéma, avant toute préparation de création.', '- Reconnaissance de la demande d’ouverture d’un dossier fournisseur, des noms explicitement introduits et des précisions de téléphone.', '- Suppression du détournement de « kayn f Casa » vers une recherche de doublons et du contrôleur qui absorbait des précisions avant leur extraction.', '- Consultation des vrais paiements et des champs compatibles via des outils SELECT bornés. Les variantes « après/ba3d … nhar » conservent le délai en jours ; aucune conversion arbitraire de mois en jours.', '- Les citations malveillantes explicitement présentées comme données de mail ne provoquent plus de refus HTTP automatique ; les secrets et ordres techniques directs restent filtrés.', '- Une consultation suspend la confirmation de création tout en conservant le brouillon. Les arrêts ciblés par code et le retrait du deuxième brouillon ne doivent pas annuler les autres demandes.', '- Reprise des noms et villes explicitement associés dans l’historique, sans transfert automatique d’identifiants fiscaux ou de contacts entre fournisseurs.','', '## Limites et échecs restants','',f"**{final['failed']} cas présentent encore au moins un échec des contrôles en panne IA simulée.** Les traces détaillent les valeurs attendues/observées et les limites d’extraction, de consultation ou de contextualisation. Les opérations métier absentes restent bloquées. Un résultat de consultation, d’annulation ou de refus ne doit pas être remplacé artificiellement par « créé avec succès ».",'', 'Les assertions couvrent les champs explicites, les états, la persistance et les protections. Elles ne certifient pas toutes les nuances des attendus en texte libre. Le code affiché après une création simulée valide le parcours backend, pas une insertion transactionnelle réelle dans Sage. Les brouillons contenant des champs non mappés ou des valeurs inconnues ne sont pas forcés pour obtenir un succès.','', '## Preuves et budget','', '- [Index des 300 cas](three-corpora-report/index.csv)', '- [Synthèse chiffrée](three-corpora-report/summary.json)', '- `three-corpora-report/cases/` : messages, réponses, états, attendus et résultats de confirmation, cas par cas.', '- `three-corpora-baseline-evaluation.json`, `three-corpora-final-evaluation.json` : évaluations complètes avant/après.', '- `three-corpora-regressions.xml` : tests de non-régression ciblés.', '- `three-corpora-real/` et `three-corpora-real-replay/` : preuves React et rejeux réels.', '', 'Les schémas PostgreSQL de test sont isolés et supprimés par leurs fixtures à la fin des exécutions complètes. Les comptes des tests React sont désactivés. Ni les permissions SQL, ni la configuration de budget, ni les données de production n’ont été modifiées.', '', 'Consommation enregistrée pour les dernières conversations réelles retenues (les premiers essais et rejeux remplacés peuvent ajouter du crédit, journalisé séparément en base) :','', '```json',json.dumps(consumption,ensure_ascii=False,indent=2),'```']
suite=ET.parse(ROOT/'three-corpora-regressions.xml').getroot().find('testsuite')
lines[6:6]=[f"Non-régression ciblée : **{suite.attrib['tests']} tests réussis, {suite.attrib['failures']} échec**. Les réussites techniques des confirmations sont distinctes de la qualité des données : un cas peut valider le transport simulé et échouer à une assertion de compréhension.",'']
lines+=['', 'Les essais interrompus pendant le développement sont exclus des 300 cas finaux. Huit schémas abandonnés ont été nettoyés après vérification du compte fictif, de la date et du premier message du corpus ; aucun schéma d’application ou Sage n’a été supprimé. Preuve : `three-corpora-schema-cleanup.json`.']
(ROOT/'RAPPORT-TROIS-FICHIERS-FOURNISSEURS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in outdir.rglob('*') if p.is_file() and p.name!='sha256.json'}
(outdir/'sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
