"""Reviewable Excel evidence for the deployed SOB reader improvements."""
import json,collections
from pathlib import Path
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.worksheet.table import Table,TableStyleInfo
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runtime/sob-improvements-20261113';OLD=ROOT/'runtime/sob-quality-audit-20261112'
def load(name,default=None):
    p=OUT/name
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default
def stringify(value):return json.dumps(value,ensure_ascii=False,default=str) if isinstance(value,(list,dict,tuple)) else value
wb=Workbook();wb.remove(wb.active)
def sheet(title,headers,rows,widths):
    s=wb.create_sheet(title);s.append(headers);s.freeze_panes='B2';s.sheet_view.zoomScale=85
    for r in rows:
        s.append([stringify(v) for v in r])
        for c in s[s.max_row]:
            if isinstance(c.value,str):c.value=c.value[:32760];c.data_type='s'
    for c in s[1]:c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True);c.alignment=Alignment(wrap_text=True)
    s.row_dimensions[1].height=34
    for i,width in enumerate(widths,1):s.column_dimensions[s.cell(1,i).column_letter].width=width
    for row in s.iter_rows(min_row=2):
        s.row_dimensions[row[0].row].height=78
        for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
    if s.max_row>1:
        t=Table(displayName='Evidence'+str(len(wb.worksheets)),ref=s.dimensions);t.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);s.add_table(t)
    return s
def build():
    results=load('preparations-after.json');docs=load('documents-after.json');tests=load('tests-final.json',{})
    previews=load('sql-previews-final.json',[]);deployment=load('deployment.json',{})
    counts=collections.Counter(r['status'] for r in results)
    before={tuple(r['ids']):r for r in json.loads((OLD/'readonly-replays.json').read_text(encoding='utf-8'))}
    ready=[r for r in results if r['status']=='Préparation sans manque signalé']
    zeros=[r for r in ready if any(l.get('price')==0 for l in r['details']['lines'])]
    summary=[
      ('État','Modifications déployées ; écoute SOB active dans TEST, source sob commandes, réponses COMMANDES SOB.'),
      ('Périmètre','Cas ciblés du 11–12/11 et demandes du 13/11 jusqu’à 10:31:10 heure de Paris ; les messages ultérieurs relèvent du service actif.'),
      ('Documents relus',len(docs)),('Dossiers rejoués en préparation seule',len(results)),
      *counts.items(),('Tests ciblés réussis',tests.get('passed')),
      ('Simulations SQL TEST réussies',sum(p['result'].get('ok',False) for p in previews)),
      ('Commandes créées par les scripts de contrôle',0),
      ('Voyages ciment','VYS/VGS/VGE/VOY/voyage et variantes reconnues. Ni 540 ni 560 sacs imposés. Le chargement absent est demandé avant création ; 2 voyages explicitement confirmés à 560 sacs donnent 1120 sacs.'),
      ('Résultats complets ≠ précision garantie','Préparation sans manque signalé signifie absence de blocage détecté. Ce n’est ni une commande créée, ni une validation humaine de tous les champs. Deux cas imprimés sont en plus contrôlés en simulation SQL.'),
      ('Prix nuls dans les préparations sans manque',len(zeros)),
      ('Politique prix existante','Le dernier recours à zéro TTC est une règle préexistante autorisée dans TEST. Ces cas restent à contrôler financièrement ; cette règle n’a pas été remplacée silencieusement.'),
      ('Limites','Certaines écritures restent difficiles, certains clients/références ne sont pas identifiés, certains conditionnements ou montants sont ambigus. Les blocages sont détaillés : aucun chiffre n’est inventé pour les lever.'),
      ('Transcriptions relues','Quelques corrections sont limitées au SHA256 exact du fichier ; l’OCR/lecture des colonnes et les règles d’interprétation sont des améliorations générales pour les nouveaux documents.'),
      ('Historique','Aucune commande historique OB/TEST modifiée par ces scripts. Les services habituels continuent indépendamment.'),
      ('Mémoire','Corrections et exemples persistés en PostgreSQL ; cela ne correspond pas à un entraînement des poids du modèle.'),
      ('Déploiement',deployment),
    ]
    sheet('Synthèse',['Point','Résultat / limite'],summary,[48,130])
    headers=['Messages','Statut après','Client Sage','Lignes interprétées','Manques après','Blocages avant','Réponse de préparation corrigée','Texte source du rejeu','Lien Telegram','Contexte']
    def row(r):
        d=r.get('details',{});b=before.get(tuple(r['ids']),{});c=d.get('client') or {}
        lines=[{k:l.get(k) for k in ['article','quantity','unit','price','price_source_order']} for l in d.get('lines',[])]
        return [r['ids'],r['status'],(c.get('BPCNUM_0','')+' — '+c.get('BPCNAM_0','')).strip(' —'),lines,d.get('missing_fields',r.get('error')),b.get('details',{}).get('missing_fields',b.get('error','Non inclus dans le premier rejeu')),d.get('reply',r.get('error')),r['source'],'https://t.me/c/4375687420/'+str(r['ids'][0]),'Préparation actuelle ; catalogue/prix du moment. Les compléments isolés ne constituent pas forcément une nouvelle commande.']
    sheet('Tous les rejeux',headers,[row(r) for r in results],[24,48,40,90,75,65,110,115,48,85])
    sheet('À clarifier',headers,[row(r) for r in results if r['status']!='Préparation sans manque signalé' and not r['status'].startswith('Message administratif')],[24,48,40,90,75,65,110,115,48,85])
    sheet('Préparations complètes',headers,[row(r) for r in ready],[24,48,40,90,75,65,110,115,48,85])
    sheet('Prix nuls à contrôler',headers,[row(r) for r in zeros],[24,48,40,90,75,65,110,115,48,85])
    source={r['id']:(OLD,r) for r in json.loads((OLD/'messages-layout.json').read_text(encoding='utf-8')) if r.get('file')}
    source.update({r['id']:(OUT,r) for r in load('messages-week.json') if r.get('file')})
    docrows=[]
    for mid,d in docs.items():
        folder,r=source[int(mid)];p=(folder/r['file']).resolve()
        docrows.append([int(mid),r['date'],d.get('ok'),d.get('method') or d.get('methods','OCR/PDF figé du contrôle initial'),d.get('requires_review') or 'LECTURE INCERTAINE A CONFIRMER' in d.get('text',''),d.get('vision_errors'),d.get('sha256'),d.get('text',d.get('error')),str(p)])
    s=sheet('Documents',['Message','Date Paris','Texte obtenu','Méthode','Zone incertaine signalée','Limites du lecteur','SHA256','Lecture retenue','Original'],docrows,[18,30,18,45,28,35,68,130,100])
    for i,r in enumerate(docrows,2):s.cell(i,9).hyperlink=Path(r[8]).as_uri()
    previewrows=[]
    for p in previews:
        payload=p.get('payload',{})
        previewrows.append([p['message'],p['mode'],p['result'].get('ok'),payload.get('client'),payload.get('lines'),payload.get('total'),payload.get('comment'),p['result']])
    sheet('Simulations SQL',['Message','Mode','Contrôle passé','Client','Lignes','Total TTC','Consigne Sage','Résultat natif'],previewrows,[18,18,20,22,100,25,100,120])
    corrections=[
      ('Voyages','cement_trips.py / understanding.py','Variantes, fautes, espaces manquants ; chargement explicite ; pas de conversion historique 540/560 automatique.'),
      ('Unités / prix','understanding.py / prepare.py','Séparer quantité et base du prix ; pièces de madriers en ML ; bidons SIK_5L en L sur équivalence vérifiée ; prix par tonne du ciment en prix par sac.'),
      ('Lecture générale','read_documents_layout.py / document_vision.py','OCR visuel local des images/scans ; lumière/orientation ; en-têtes gauche/droit, pieds/cachets et colonnes de prix agrandis.'),
      ('Identité acheteur','prepare.py / learning_memory.py','Noms légaux, aliases vérifiés et ICE N° ; fournisseur propre exclu ; client sans preuve source refusé ; aliases d’un autre client exclus du prompt.'),
      ('Tableaux','document_grounding.py','Préserver diamètres, largeurs, finitions, quantités et bases HT/TTC ; contrôler les montants ; restaurer un détail omis seulement s’il est écrit dans la source.'),
      ('Références','telegram_batch.py','BC NO / Numéro Commande, séparation des demandes, références pour les contrôles de doublons.'),
      ('Contrainte Sage','delivery_notes.py','Abréviations usuelles ; noms/téléphones/instructions conservés. Pas de troncature silencieuse au-delà de100caractères.'),
      ('Messages administratifs','message_intent.py','Relance, activation et récupération de chèques distinguées d’une création de commande.'),
      ('Apprentissage durable','PostgreSQL','Aliases/règles vérifiés activés ; observations rejouées dans sob_learning_examples. Les observations OB seules ne deviennent pas des règles générales de chargement.'),
    ]
    sheet('Corrections appliquées',['Sujet','Module / preuve','Comportement'],corrections,[33,65,130])
    sheet('Validation et limites',['Point','Détail'],[
      ('Tests',tests),('Contrôles des brouillons',load('payload-checks-final.json',{})),
      ('Prix / quantités OB','Les écarts avec une saisie manuelle ne prouvent pas une erreur de lecture. Aucun tarif ni chargement n’est importé depuis une commande OB ressemblante pour combler un manque.'),
      ('Réponses réelles','La colonne corrigée est un résultat de préparation en lecture seule, pas une réponse envoyée dans le groupe pendant l’audit.'),
      ('Sans manque','Ne pas confondre absence de blocage, vérification de quelques champs à la source, contrôle SQL et création effective.'),
      ('Dates','Les dates explicites sont conservées ; une livraison passée ou une correction ambiguë reste à préciser.'),
      ('Étendue','Corpus ciblé, pas un taux de précision global de l’agent. Les cas déjà créés historiquement ne sont pas tous rejoués dans ce contrôle.'),
      ('Docs suivis',len(docs)),('Scripts','recheck_sob_improvements.py / finalize_sob_improvements.py ; pas d’appel à creation.confirm.'),
    ],[45,140])
    for s in wb:
        for rowdata in s.iter_rows(min_row=2):
            for c in rowdata:
                if isinstance(c.value,str) and c.value.startswith('https://t.me/'):
                    c.hyperlink=c.value;c.style='Hyperlink'
    dest=ROOT/'TEST/CORRECTIONS-AGENT-SOB-2026-11-13.xlsx';wb.save(dest)
    check=load_workbook(dest)
    assert check['Tous les rejeux'].max_row-1==len(results)
    assert check['Documents'].max_row-1==34
    assert all(c.data_type!='f' for s in check for rowdata in s for c in rowdata)
    print(json.dumps({'file':str(dest),'cases':len(results),'documents':len(docs),'counts':dict(counts),'zero_price_ready_cases':len(zeros),'validation':'OK'},ensure_ascii=True))
if __name__=='__main__':build()
