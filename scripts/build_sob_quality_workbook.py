"""Build an evidence workbook from frozen, read-only SOB audit snapshots."""
import json,collections,sys
from pathlib import Path
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.worksheet.table import Table,TableStyleInfo
from openpyxl.drawing.image import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runtime/sob-quality-audit-20261112'
DEST=ROOT/'TEST/AUDIT-QUALITE-SOB-OB-TEST-2026-11-12.xlsx'
def load(n,default=None):
    p=OUT/n
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def val(v):
    if isinstance(v,(dict,list,tuple)):return json.dumps(v,ensure_ascii=False,default=str)
    return v
wb=Workbook();wb.remove(wb.active)
def sheet(name,headers,rows,widths=None):
    ws=wb.create_sheet(name);ws.append(headers)
    for row in rows:
        ws.append([val(x) for x in row])
        for cell in ws[ws.max_row]:
            if isinstance(cell.value,str):cell.data_type='s';cell.value=cell.value[:32760]
    ws.freeze_panes='C2';ws.sheet_view.zoomScale=85
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.print_options.horizontalCentered=True
    ws.sheet_properties.tabColor='17365D'
    for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='17365D');c.alignment=Alignment(wrap_text=True,vertical='center')
    ws.row_dimensions[1].height=34
    for i,col in enumerate(ws.columns):
        ws.column_dimensions[col[0].column_letter].width=(widths[i] if widths and i<len(widths) else 24)
    for row in ws.iter_rows(min_row=2):
        ws.row_dimensions[row[0].row].height=48
        for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
    if ws.max_row>1:
        tab=Table(displayName='T'+str(len(wb.worksheets)),ref=ws.dimensions);tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);ws.add_table(tab)
    return ws
a=load('analysis-reviewed.json');cases=a['cases'];byid={i:c for c in cases for i in c['ids']}
for c in cases:
    if c['source_client_confidence']==.99 and '?' in c['source_client_proof']:
        c['source_client_proof']='Identité légale relue visuellement ; code rapproché du référentiel Sage'
test=load('ob-test_orders_audit.json')['rows'];ob=load('ob-orders.json')['rows'];visual=load('visual-transcriptions.json')
created_numbers={n for c in cases for n in c['test_numbers']}
zero=[r for r in test if r['SOHNUM_0'] in created_numbers and float(r['NETPRIATI_0'])==0]
zeroorders={r['SOHNUM_0'] for r in zero}
noncreated=[c for c in cases if not c['test_numbers']]
replays=load('readonly-replays.json',[]); rp={r['case']:r for r in replays}
summary=[
('Périmètre','11–12 novembre 2026, dernier message '+a['scope']['latest_message']),
('Seuil de 15h','Journées complètes conservées pour ne pas omettre les compléments ; filtre Avant/Après 15h dans Comparaisons. Le 10/11 en OB sert uniquement de contexte.'),
('Messages source',a['counts']['messages']),('Dossiers / regroupements',len(cases)),('Dossiers avec commande TEST retrouvée',a['counts']['created_cases']),('Dossiers sans commande TEST retrouvée',len(noncreated)),('Pièces jointes inspectées',len(visual)),('Rapprochements forts OB/TEST',a['counts']['strong_matches']),
('Erreur article confirmée par la source','Message 5204 : 1000 kg RAB10 → TEST 2026ARC15142 : FL_ET (film étirable). OB 2026ARC25612 comporte RAB10. Commande TEST existante non modifiée par cet audit.'),
('Risque prix nuls',f'{len(zeroorders)} commandes TEST liées aux messages comportent au moins une ligne à prix TTC nul ({len(zero)} lignes). À vérifier avant toute utilisation métier ; absence de prix source ne prouve pas le bon tarif.'),
('Politique prix existante','La mémoire SOB autorise explicitement zéro TTC en dernier recours après prix source puis dernier prix client/article. Ces lignes sont un risque métier à contrôler, pas une violation automatique de la consigne existante.'),
('Lecture documents','Des clients/articles figurent dans les en-têtes, pieds de page, cachets et photos manuscrites. Consulter Documents et Non créées ; distinguer identification lisible et données suffisantes pour créer.'),
('Important sur les 95 dossiers','Ce total inclut compléments, photos seules, corrections et messages non exploitables ; il ne représente pas 95 commandes commerciales distinctes manquées.'),
('Écarts de prix/quantités','Un écart avec OB peut venir d’une décision de saisie manuelle. Seule une valeur explicite du message/document permet d’attribuer une erreur à l’agent.'),
('État global','La fiabilité complète de l’agent ne peut pas être validée : erreur article prouvée, tarifs nuls et nombreux documents non créés nécessitent revue.'),
('Corrections','Garde article explicite, désambiguïsation lexicale avant unité, diamètres acier/brique 07, rotation OCR, reconnaissance des libellés client. Tests de non-régression et mémoire PostgreSQL.'),
('Rejeux actuels',f'{len(replays)} préparations en lecture seule enregistrées au moment de génération. Aucun appel de création par le script de rejeu.'),
('Restrictions','Aucune commande OB/TEST ni aucun message Telegram envoyé/modifié par les scripts d’audit. Les services habituels peuvent continuer indépendamment.'),
('Données non concluantes','Pas de taux de précision global : clients homonymes, regroupements, unités absentes et correspondances OB candidates restent à confirmer.'),
]
summary=[('Rapprochements forts à OB (créés ou non)' if k=='Rapprochements forts OB/TEST' else k,v) for k,v in summary]
focus=[c for c in cases if c['date']>='2026-11-11T15:00:00']
summary.extend([('Focus depuis le 11/11 à 15h',f'{len(focus)} dossiers techniques ; {sum(bool(c["test_numbers"]) for c in focus)} avec commande TEST retrouvée. Les compléments avant 15h sont conservés ailleurs dans le classeur.'),('Liens forts pour dossiers créés',sum(bool(c['test_numbers']) and c['match_level'].startswith('Fort') for c in cases))])
summary.extend([('Rejeux sans manques signalés',sum(r.get('ok',False) and r.get('details',{}).get('intent')=='order' and not r.get('details',{}).get('missing_fields') for r in replays)),('Rejeux en erreur technique',sum(not r.get('ok',False) for r in replays)),('Attention aux rejeux','Même sans manques signalés, un brouillon reste à confronter à sa source. Les documents relus visuellement ne démontrent pas une amélioration équivalente de l’OCR automatique.')])
sheet('Synthèse',['Indicateur','Résultat / interprétation'],summary,[37,135])
headers=['Dossier','Messages','Date Paris','Seuil 15h','Contact','Commandes TEST','Client source','Nom client source','Preuve identité','Confiance identité','OB proposé','Force rapprochement','Évaluation','Observations / risques','Pièces jointes','Première réponse agent','Dernière réponse agent','Message source','Candidats OB','Lien source']
def case_row(c):return [c['case'],c['ids'],c['date'],c['periode_15h'],c['contact'],c['test_numbers'],c['source_client'],c['source_client_name'],c['source_client_proof'],c['source_client_confidence'],c['selected_ob'],c['match_level'],c['severity'],c['issues'],c['files'],c['agent_reply_first'],c['agent_reply'],c['source_text'],c['ob_candidates'],'https://t.me/c/4375687420/'+str(c['ids'][0])]
ws=sheet('Comparaisons',headers,[case_row(c) for c in cases],[35,20,28,18,23,25,18,34,48,18,24,42,34,80,18,80,80,95,65,42])
for r in range(2,ws.max_row+1):
    if 5204 in cases[r-2]['ids']:
        for cell in ws[r]:cell.fill=PatternFill('solid',fgColor='FFC7CE')
    ws.cell(r,20).hyperlink=ws.cell(r,20).value;ws.cell(r,20).style='Hyperlink'
sheet('Non créées',headers,[case_row(c) for c in noncreated],[35,20,28,18,23,25,18,34,48,18,24,42,34,80,18,80,80,95,65,42])
missed=[]
for c in noncreated:
    for mid in c['files']:
        v=visual.get(str(mid),{})
        if v.get('client_name'):
            missed.append([mid,c['source_client'],v.get('client_name'),v.get('client_quote'),c['agent_reply'],v.get('note'),c['selected_ob'],c['match_level'],'Identité présente sur la pièce. Cela ne suffit pas à valider toutes les unités/prix ni à autoriser une création automatique.'])
sheet('Identités non reconnues',['Message','Client proposé','Nom visible','Preuve visuelle','Réponse historique','Articles / réserves document','OB candidat','Solidité du lien','Conclusion prudente'],missed,[16,20,35,65,105,110,25,48,100])
ld=a['line_differences']; keys=list(ld[0])
sheet('Écarts lignes',keys,[[r.get(k) for k in keys] for r in ld])
zkeys=['SOHNUM_0','BPCORD_0','BPCNAM_0','ITMREF_0','ITMDES1_0','QTY_0','SAU_0','NETPRIATI_0','ORDATI_0']
sheet('Alerte prix nuls',zkeys,[[r.get(k) for k in zkeys] for r in zero])
sheet('Messages source',['ID','Date Paris','Dossier','Contact','Texte original','Réponse à','Pièce jointe','Lien Telegram'],[[r['id'],r['date'],byid[r['id']]['case'],byid[r['id']]['contact'],r.get('text'),r.get('reply_to'),r.get('file'),'https://t.me/c/4375687420/'+str(r['id'])] for r in a['source']],[14,29,40,24,115,16,75,50])
responses=load('response-messages.json')
sheet('Messages groupe réponses',['ID','Date Paris','Émetteur','Réponse à','Message réel'],[[r['id'],r['date'],r['sender'],r['reply_to'],r['text']] for r in responses],[14,29,22,18,150])
attempts=[r for r in load('routing-batches.json') if r['source']==-1004375687420 and any(r['id']==c['case'] or (':'+str(i)+':') in r['id'] for c in cases for i in c['ids'])]
if attempts:sheet('Journal agent',list(attempts[0]),[[r.get(k) for k in attempts[0]] for r in attempts])
docs=[]
for mid,v in visual.items():
    r=next(r for r in a['source'] if r['id']==int(mid));c=byid[int(mid)]
    docs.append([int(mid),r['date'],v['document_type'],v['client_name'],v['client_code'],v['client_quote'],v['note'],v['text'],r.get('layout_text',''),v['goods'],v['prices'],v['sha256'],str((OUT/r['file']).resolve()),c['test_numbers'],c['agent_reply'],''])
ws=sheet('Documents',['Message','Date','Type','Nom visuel','Code vérifié','Preuve sur la pièce','Relecture et limites','Transcription retenue','Lecture automatique initiale','Quantités explicites','Prix explicites','SHA256','Original','Commandes TEST','Réponse agent','Aperçu'],docs,[14,28,20,30,18,65,100,100,100,42,42,66,80,26,95,47])
for row in range(2,len(docs)+2):
    ws.row_dimensions[row].height=180
    ws.cell(row,13).hyperlink=Path(docs[row-2][12]).as_uri();ws.cell(row,13).style='Hyperlink'
    preview=OUT/'previews'/f'{docs[row-2][0]}.png'
    if preview.exists():
        im=Image(str(preview));factor=min(310/im.width,225/im.height);im.width*=factor;im.height*=factor;ws.add_image(im,'P'+str(row))
for title,data in [('Lignes SQL OB',ob),('Lignes SQL TEST',test)]:
    keys=list(data[0]);sheet(title,keys,[[r.get(k) for k in keys] for r in data])
linked={c['selected_ob'] for c in cases if c['selected_ob'] and c['match_level'].startswith('Fort')}
obgroups=collections.defaultdict(list)
for r in ob:obgroups[r['SOHNUM_0']].append(r)
sheet('OB sans lien fort',['Commande OB','Date SQL brute','Client','Nom','Articles','Total TTC','Interprétation'],[[n,rr[0]['ORDDAT_0'],rr[0]['BPCORD_0'],rr[0]['BPCNAM_0'],sorted({r['ITMREF_0'] for r in rr}),rr[0]['ORDATI_0'],'Aucun lien fort dans le périmètre source gelé. Peut provenir d’un autre canal/jour ; ne prouve pas une commande manquée.'] for n,rr in obgroups.items() if n not in linked],[25,30,18,40,65,22,115])
replayrows=[]
for r in replays:
    d=r.get('details',{});c=next(c for c in cases if c['case']==r['case'])
    replayrows.append([r['ids'],c['agent_reply'],r['ok'],d.get('client'),d.get('lines'),d.get('missing_fields'),d.get('reply'),r.get('error'),r.get('mode'),'Simulation actuelle : catalogue/prix du moment, pas reproduction historique exacte. Aucun ordre créé.'])
sheet('Rejeux corrigés',['Messages','Réponse historique','Rejeu terminé','Client résolu','Lignes proposées','Manques persistants','Nouvelle préparation','Erreur technique','Mode','Limite'],replayrows,[20,90,18,38,90,65,110,50,50,85])
corrections=[
('Article source 5204','Rab générique pouvait choisir FILM ETIRABLE via KG','source_article_safety.py + prepare.py','Diamètre source explicite conservé ; article spécifique incompatible bloque. Quantités/prix non remplacés par OB.'),
('Libellés documents','Acier HA diamètre / BRIQUE 07 non reconnus','prepare.py','Alias stricts ; brique rouge sans diamètre reste ambiguë.'),
('Photos tournées','Lecture faible sans rotation','read_documents_layout.py','Nouvelle tentative 90°/270° si OCR faible ; original intact. Écriture manuscrite non garantie.'),
('Identité document','Variantes nom client/acheteur','prepare.py','Libellés explicites étendus ; destinataire/fournisseur non utilisés comme client par défaut.'),
('Mémoire persistante','Corrections SOB en PostgreSQL','learning-audit-saved.json',load('learning-audit-saved.json',{})),
('Exemples persistants','182 dossiers conservés en PostgreSQL','sob_learning_examples',load('learning-examples-audit.json',{})),
('Vérification','Tests des gardes, OCR, documents, compréhension','pytest','Voir audit-validation.json ; aucun test ne crée de commande réelle.'),
('Limite des rejeux documents','Relecture visuelle injectée dans les dossiers documentaires','Rejeux corrigés','Une préparation réussie après transcription visuelle ne prouve pas que l’OCR automatique sait désormais lire ce document. Les diamètres peuvent encore être perdus par le modèle ; consulter les manques persistants.'),
('Commande déjà erronée','2026ARC15142 reste dans TEST','Action requise','Revoir/isoler cette commande ; l’audit ne modifie pas les ventes existantes et ne considère pas le prix manuel OB comme prix explicitement reçu.'),
]
sheet('Corrections',['Sujet','Constat','Fichier / preuve','Correction / limites'],corrections,[32,70,52,120])
method=[('Snapshots','SQL SELECT uniquement, OB et TEST. Les lignes SQL représentent toutes les commandes de la fenêtre, pas seulement celles du groupe.'),('Regroupement','232 messages → 182 dossiers techniques selon journal agent. Les compléments peuvent former plusieurs dossiers : ne pas assimiler ces dossiers à des commandes commerciales distinctes.'),('Correspondances','Rapprochement client, date, articles, quantités ; candidats conservés si ambiguïté. Même client seul ne suffit pas à prouver la même commande.'),('Preuve source','Texte brut, relecture visuelle des pièces, ICE/code client unique. Les codes visuels proviennent du rapprochement avec référentiel Sage, pas tous du texte imprimé.'),('Écarts lignes','Quantité/prix source vide = non démontré. La colonne attribution indique qu’une preuve partielle existe, pas que tous les écarts de la ligne sont fautifs.'),('Relecture','Inspection visuelle Codex, sans confirmation humaine. Les incertitudes manuscrites, unités et corrections de transport restent explicites.'),('Documents répétés','5153 remplacé par 5168 ; 5187/5188, 5320/5355 et 5330/5331 nécessitent vigilance anti-doublon. Aucun rejeu ne crée de commande.'),('Temps','Dates source ISO en heure de Paris ; SQL conserve /Date(ms)/ brut. Le seuil 15h est un filtre, pas une supposition sur la date demandée.'),('Corrections','La préparation native est lancée en nouveau processus par le service ; les modifications sont prises en compte aux prochaines préparations. Aucun redémarrage de service ni changement de dossier cible par cet audit.'),('Exhaustivité','Contrôle de couverture : chaque ID source apparaît exactement une fois dans la liste Messages source et dans un dossier Comparaisons. Les réceptions après le gel ne sont pas incluses.'),('Validation',load('audit-validation.json',{}))]
sheet('Méthode et limites',['Point','Détail'],method,[36,145])
DEST.parent.mkdir(exist_ok=True);wb.save(DEST)
check=load_workbook(DEST)
assert check['Messages source'].max_row-1==232
assert check['Comparaisons'].max_row-1==len(cases)
assert len({r['id'] for r in a['source']})==232
assert len(byid)==232
assert len(check['Documents']._images)==31
assert all(c.data_type!='f' for ws in check for row in ws for c in row)
print(json.dumps({'file':str(DEST),'sheets':len(check.sheetnames),'messages':232,'documents':31,'cases':len(cases),'zero_price_orders':len(zeroorders),'replays':len(replays),'validation':'OK'},ensure_ascii=False))
