"""Normalize the three user-supplied datasets; contents are fixtures, not code."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=[('darija','100_sessions_complexes_darija_fournisseurs_sage_x3 (1).json'),('mixed','100_sessions_mixtes_fournisseurs_21_messages.json'),('emails','100_emails_tests_fournisseurs_sage_x3.json')]
def cases():
 result=[]
 for kind,name in FILES:
  raw=(Path('C:/Users/youssef/Desktop')/name).read_bytes();data=json.loads(raw.decode('utf-8-sig'))
  for row in data.get('sessions',data.get('mails',[])):
   steps=[{'text':m.get('content',m.get('utilisateur','')),'expected':m.get('attendu'),'type':m.get('type_attendu')} for m in row.get('messages',[])] if kind!='emails' else [{'text':row['corps'],'expected':row.get('attendu'),'type':','.join(row.get('intentions_attendues',[]))}]
   result.append({'id':kind+'-'+str(row.get('session_id',row.get('id'))),'dataset':kind,'theme':row.get('scenario',row.get('title',row.get('objet'))),'steps':steps,'oracle':row.get('oracle_global',row.get('expected_behaviors',[row.get('attendu')])),'source_file':name,'sha256':hashlib.sha256(raw).hexdigest()})
 return result
if __name__=='__main__':
 data=cases();(ROOT/'three-supplier-corpora.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in data),encoding='utf-8');print({'cases':len(data),'messages':sum(len(c['steps']) for c in data)})
