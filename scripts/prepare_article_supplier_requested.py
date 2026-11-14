"""Prepare requested ITM/BPS drafts via FastAPI; never approve or execute writes."""
import json,copy
from datetime import datetime,timezone
from pathlib import Path
import httpx
import native_stack as stack
ROOT=stack.ROOT
previous=json.loads((ROOT/'logs/step4-crud-live-tests.json').read_text())
out={'checked_at':datetime.now(timezone.utc).isoformat(),'mode':'REAL_API_READ_AND_PREPARATION_ONLY','resources':{},'sage_writes':0}
labels={'articles':'ARTICLE TEST AGENT IA FASTAPI','suppliers':'FOURNISSEUR TEST AGENT IA'}
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},trust_env=False,timeout=90) as client:
    security=client.get('/api/v1/sage/security');security.raise_for_status();out['security']=security.json()
    for resource,label in labels.items():
        request=copy.deepcopy(previous['resources'][resource]['create_preparation']['request'])
        for field in request['fields']:
            if resource=='articles' and field['name']=='DES1AXX':field['value']=label
            if resource=='suppliers' and field['name']=='BPRNAM':field['value']=[label,'']
        schema=client.get('/api/v1/sage/'+resource+'/schema');schema.raise_for_status()
        response=client.post('/api/v1/sage/'+resource+'/prepare',json=request);response.raise_for_status();op=response.json()
        assert op['before_record']['exists'] is False,'Duplicate detected: no creation may be approved'
        assert label in op['object_xml']
        out['resources'][resource]={'publication':previous['resources'][resource]['publication'],'sample_keys':previous['resources'][resource]['sample_keys'],
            'schema_http':schema.status_code,'schema_fields':len(schema.json()['fields']),'create_preparation':{'http':response.status_code,'request':request,'operation':op}}
        # A final read-only HTTP check confirms the candidate still does not exist.
        read=client.get('/api/v1/sage/'+resource+'/'+'/'.join(request['keys'].values()))
        out['resources'][resource]['read_http']=read.status_code
        if resource=='articles':assert read.status_code==404
        else:assert read.status_code==200 and read.json()['record']['exists'] is False
with stack.connect() as conn:
    out['approvals']=conn.execute('SELECT count(*) FROM sage_ai.soap_operation_approvals').fetchone()[0]
    out['write_attempt_claimed']=conn.execute("SELECT count(*) FROM sage_ai.soap_operation_events WHERE event_type='write_attempt_claimed'").fetchone()[0]
assert out['approvals']==0 and out['write_attempt_claimed']==0
out['status']='PREPARED_SECURITY_BLOCKED' if not out['security']['ready'] else 'PREPARED_APPROVAL_REQUIRED'
(ROOT/'logs/step4-article-supplier-requested.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
lines=['# Article et fournisseur — préparations demandées via FastAPI', '',f"Date : {out['checked_at']}", '',
       '**Aucune création effectuée.** Les valeurs demandées remplacent les anciens libellés des brouillons précédents. Ces préparations ne sont pas des approbations.', '',
       'Sécurité actuelle : '+', '.join(out['security']['blockers'])+'.', '',
       'Les droits métier du compte technique restent non vérifiés ; le pool utilise encore une identité administrateur. HTTPS 443/8443 non joignable lors du contrôle associé. Aucune modification de production autorisée ni appliquée. Voir docs/ETAPE-4-ACTIONS-AVANT-ECRITURE.md pour les changements techniques proposés et leurs risques.']
for resource,r in out['resources'].items():
    op=r['create_preparation']['operation'];code=next(iter(op['record_keys'].values()))
    lines += ['',f"## {r['publication']} — {code}", '',f"Libellé : **{labels[resource]}**. Cible **V12 / TEST**, pool POOL_AI_TEST.",
              f"Préparation : HTTP {r['create_preparation']['http']}, UUID `{op['id']}`.",f"Empreinte : `{op['digest']}`.",
              f"Read préalable : SOAP {op['before_record']['status']}, messages `{json.dumps(op['before_record'].get('messages',[]),ensure_ascii=False)}`, existe = false.",
              '', '| Champ transmis | Valeur |','|---|---|']
    for f in r['create_preparation']['request']['fields']:lines.append(f"| {f['group']}.{f['name']} | {json.dumps(f['value'],ensure_ascii=False)} |")
    lines += ['', '```xml',op['object_xml'].rstrip(),'```', '',
              'Mapping, types, longueurs, dimensions et méthode CREATE contrôlés sur la publication réelle. **Les champs obligatoires conditionnels et droits ne sont pas certifiés par ce contrôle structurel.**',
              'Revue métier encore nécessaire : '+('catégorie NEG, code manuel, unités SAC/coefficient 1, stock/lots/statut et code comptable CPJ35.' if resource=='articles' else 'catégorie fournisseur, pays, code manuel, adresse et autres obligations conditionnelles. BPRNAM est une liste de deux valeurs ; BPSNAM est Display et ne doit pas être utilisé en saisie.'),
              '', f"Consultation React : http://127.0.0.1:8000/sage/?resource={resource}&code={code} — fiche absente actuellement.",
              'Sage : dossier TEST, '+('GESITM — Données de base > Articles > Articles.' if resource=='articles' else 'GESBPS — Données de base > Tiers > Fournisseurs.'),
              '', 'Demande individuelle à présenter **après** validation technique et métier, nouvelle préparation si les paramètres changent :',
              f"« Autorisez-vous une seule création de {code}, libellé {labels[resource]}, dans TEST, via FastAPI → SOAP save, sur l’UUID et l’empreinte finaux présentés ? »",
              '', 'Aucun statut SOAP de création ni read après création disponible : save non exécuté. Les réponses de lecture « Fiche inexistante » ne sont pas des erreurs de création.']
lines += ['', '## Suites nécessaires', '',
          '1. Autorisation explicite des changements techniques déjà décrits : relais TLS/certificat/filtrage et compte technique TEST avec droits minimaux ; intervention administrateur Sage requise.',
          '2. Contrôle TLS réel et lectures avec ce compte ; validation des droits/règles à partir d’exports fiables, puis attestations locales.',
          '3. Nouvelles préparations si identité, publication ou valeurs changent ; deux accords séparés, jamais un accord groupé implicite.',
          '4. Une tentative par accord depuis FastAPI, read exact, affichage React et historique PostgreSQL ; aucune relance sur réponse ambiguë.']
(ROOT/'logs/ETAPE-4-PREPARATION-ARTICLE-FOURNISSEUR.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'status':out['status'],'preparations':{k:{'keys':v['create_preparation']['request']['keys'],'id':v['create_preparation']['operation']['id']} for k,v in out['resources'].items()},'sage_writes':0},indent=2))
