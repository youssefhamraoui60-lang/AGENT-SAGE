"""Confirm every remaining case must reject approval/execution in isolated forks."""
import os,json,copy
from uuid import uuid4
from pathlib import Path
from psycopg.types.json import Jsonb
from test_campaign_1000 import campaign,fixture,simulated
from test_conversation_chat import create
from app.services import business_store as db

def test_confirmations_of_blocked_cancelled_or_absent_drafts(campaign):
 c,_,_,attempts,_=campaign;root=Path(__file__).resolve().parent;shard=os.getenv('CORPUS_SHARD','0')
 summary=json.loads((root/f'three-corpora-final-{shard}-summary.json').read_text(encoding='utf-8'));tested={p['case'] for p in summary['confirmation_forks']}
 records=[json.loads(l) for l in (root/f'three-corpora-final-{shard}.jsonl').read_text(encoding='utf-8').splitlines()];out=[]
 for row in records:
  if row['id'] in tested:continue
  state=copy.deepcopy(row['turns'][-1].get('state',{}));state.pop('_pending',None)
  fork=create(c)
  with db.connection() as conn:conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb(state),fork['id']))
  fork=c.get('/api/v1/chat/conversations/'+fork['id']).json();partner=(state.get('partners') or [{}])[0].get('id',str(uuid4()));actions=[]
  for step in ('approve','execute'):
   r=c.post('/api/v1/chat/conversations/'+fork['id']+'/partners/'+partner+'/'+step,json={'revision':fork['revision'],'confirm':True,'confirm_draft_only_fields':True})
   try:detail=r.json().get('detail') if r.status_code!=200 else 'UNEXPECTED_APPROVAL'
   except ValueError:detail=r.text[:200]
   actions.append({'step':step,'http':r.status_code,'detail':detail})
   if r.status_code==200:fork=r.json()
  out.append({'case':row['id'],'passed':all(a['http'] in (403,404,409,422,423) for a in actions),'SIMULATED':True,'expected':'blocked_cancelled_or_no_creation','actions':actions})
 (root/f'three-corpora-denials-{shard}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 assert all(p['passed'] for p in out),[p for p in out if not p['passed']]
 assert all(not a.get('execute') for a in attempts)
