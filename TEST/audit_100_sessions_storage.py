"""Read-only PostgreSQL audit for this exact browser campaign's test accounts."""
import json,sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'backend'))
from app.services import business_store as db
folder=ROOT/'sessions-100-real';spec=json.loads((folder/'source.json').read_text(encoding='utf-8'));expected={s['id']:s for s in spec['sessions']};rows=[];owners=set();ids=set()
with db.connection() as c:
 for path in sorted(folder.glob('S[0-9][0-9][0-9].json')):
  item=json.loads(path.read_text(encoding='utf-8'));identifier=item.get('conversation_id')
  row=c.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(identifier,)).fetchone()
  account=c.execute('SELECT email,active FROM chat_accounts WHERE id=%s',(row['owner_id'],)).fetchone() if row else None
  messages=c.execute('SELECT role,content FROM chat_messages WHERE conversation_id=%s ORDER BY id',(identifier,)).fetchall() if row else []
  users=[m['content'] for m in messages if m['role']=='user']
  ok=bool(account and account['email'].startswith('ui-sessions-') and account['email'].endswith('@example.test') and not account['active'])
  accepted=[t['text'] for t in item['turns'] if t.get('admitted',not bool(t.get('error')))]
  def business_state(state):
   value=copy.deepcopy(state);value.get('analysis_job',{}).pop('performance',None);return value
  checks={'isolated_deactivated_test_account':ok,'unique_conversation':identifier not in ids,'exact_user_message_sequence':users==expected[item['id']]['messages_utilisateur'],'accepted_messages_persisted_in_order':users==accepted,'state_matches_last_observation':bool(row) and row['state']==item['turns'][-1]['state'],'business_state_matches_last_observation':bool(row) and business_state(row['state'])==business_state(item['turns'][-1]['state']),'no_pending':bool(row) and not row['state'].get('_pending')}
  rows.append({'session':item['id'],'conversation_id':identifier,'checks':checks,'passed':all(v for k,v in checks.items() if k not in ('exact_user_message_sequence','state_matches_last_observation')),'messages_persisted':len(users),'messages_submitted':len(item['turns'])});ids.add(identifier)
  if row:owners.add(str(row['owner_id']))
 usage=c.execute("SELECT provider,status,count(*) AS calls,COALESCE(sum(input_tokens),0) AS input_tokens,COALESCE(sum(output_tokens),0) AS output_tokens,COALESCE(sum(estimated_cost_usd),0) AS estimated_cost_usd FROM chat_ai_usage WHERE conversation_id=ANY(%s::uuid[]) GROUP BY provider,status",(list(ids),)).fetchall() if ids else []
out={'sessions':len(rows),'accounts':len(owners),'passed':sum(r['passed'] for r in rows),'failed':sum(not r['passed'] for r in rows),'strict_state_matches':sum(r['checks']['state_matches_last_observation'] for r in rows),'late_performance_metadata_only':sum(not r['checks']['state_matches_last_observation'] and r['checks']['business_state_matches_last_observation'] for r in rows),'full_sequences':sum(r['checks']['exact_user_message_sequence'] for r in rows),'user_messages_persisted':sum(r['messages_persisted'] for r in rows),'user_messages_submitted':sum(r['messages_submitted'] for r in rows),'usage':[{k:str(v) if k=='estimated_cost_usd' else v for k,v in u.items()} for u in usage],'results':rows}
(folder/'storage-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in out.items() if k!='results'}))
