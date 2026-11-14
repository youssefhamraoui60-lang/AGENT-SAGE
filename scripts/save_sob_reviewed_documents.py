"""Save visually checked transcriptions, scoped to exact source file hashes."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'telegram-test'))
import learning_memory as memory
OUT=ROOT/'runtime/sob-improvements-20261113'
old=ROOT/'runtime/sob-quality-audit-20261112'
rows={r['id']:(old,r) for r in json.loads((old/'messages-layout.json').read_text(encoding='utf-8'))}
rows.update({r['id']:(OUT,r) for r in json.loads((OUT/'messages-week.json').read_text(encoding='utf-8'))})
def line(label,q,unit,p=None,base=None,kind='TTC'):
    return {'label':label,'quantity':q,'unit':unit,'price':p,'price_unit':base,'price_kind':kind,'total':None,'uncertain':False}
docs={
 5171:dict(issuer='Aziza Tours SARL',ice=None,client_code=None,reference=None,
           lines=[line('Acier HA diamètre 6 mm',2,'TONNE',9.2,'KG'),line('Acier HA diamètre 8 mm',2,'TONNE',8.9,'KG'),line('Acier HA diamètre 10 mm',2,'TONNE',8.9,'KG'),line('Acier HA diamètre 12 mm',4,'TONNE',8.9,'KG')],total_ttc=89600),
 5180:dict(issuer='STE EDWISOL',ice='003288034000004',client_code=None,reference='019/26',lines=[line('FER T12',1100,'KG'),line('FER T10',200,'KG'),line('FER T8',100,'KG')],total_ttc=None),
 5243:dict(issuer='ENIBAC SARL',ice='001556993000019',client_code=None,reference='326/2026',lines=[line('CPJ45',28,'TONNE',82,'SAC')],total_ttc=45920),
 5362:dict(issuer='HAJJI ISSKAN SHAMA BAY',ice=None,client_code=None,reference='222/2026',lines=[line('BRIQUE 07',1500,'UN',2.6,'UN'),line('MANTD',1,'UN',500,'UN')],total_ttc=4400),
 5371:dict(issuer=None,ice=None,client_code='C05751',reference=None,lines=[line('TRADICEM',30,'SAC',65,'SAC'),line('CPJ35',4,'SAC',77,'SAC'),line('Ciment Blanc 40 kg',4,'SAC',120,'SAC'),line('AB Silicone Transparent',50,'UN',50,'UN'),line('AB Silicone Blanc',50,'UN',50,'UN'),line('Silicone Mastic Fixation',12,'UN',38,'UN')],total_ttc=None),
}
saved=[]
for mid,data in docs.items():
    data.update(uncertain=False,notes='Relecture visuelle Codex. Ligne barrée exclue.' if mid==5371 else '',tax_percent=None)
    prefix='BON DE COMMANDE\n'+('Client : '+data['issuer']+'\n' if data['issuer'] else '')
    if data['ice']:prefix+='ICE : '+data['ice']+'\n'
    if data['client_code']:prefix+='Code client : '+data['client_code']+'\n'
    if data['reference']:prefix+='Référence : '+data['reference']+'\n'
    if data['total_ttc'] is not None:prefix+='Total TTC : '+str(data['total_ttc'])+'\n'
    text=prefix+'TRANSCRIPTION STRUCTUREE SOB : '+json.dumps(data,ensure_ascii=False,separators=(',',':'))
    payload={'transcription':text}
    assert len(json.dumps(payload))<=2000
    folder,r=rows[mid];digest=hashlib.sha256((folder/r['file']).read_bytes()).hexdigest()
    rid=memory.save('interpretation','document_sha256_'+digest,payload,actor='Codex relecture visuelle SOB',
      source=f'Demande utilisateur 13/11 : corriger lecture. Inspection visuelle du document Telegram {mid}, mêmes octets uniquement ; aucun tarif ou quantité recopié depuis OB pour compléter une zone illisible.',approved=True)
    saved.append({'id':mid,'sha256':digest,'rule':rid,'transcription':text})
(OUT/'reviewed-document-memory.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'saved':len(saved),'messages':[r['id'] for r in saved]}))
