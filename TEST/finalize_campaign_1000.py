"""Fail closed: publish a summary only after all expected IDs have evidence."""
import json,hashlib,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];T=ROOT/'TEST'
def read(name):return [json.loads(x) for x in (T/name).read_text(encoding='utf-8').splitlines()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
corpus=read('campaign-1000-corpus.jsonl');expected={x['id'] for x in corpus};assert len(expected)==1000
initial=[];references={}
for j in range(4):
 name=f'campaign-1000-shard-{j}-results.jsonl';rows=read(name);assert len(rows)==250
 for line,r in enumerate(rows,1):references[r['id']]=(name,line)
 initial+=rows
assert len(initial)==len({x['id'] for x in initial})==1000
assert {x['id'] for x in initial}==expected
final={x['id']:x for x in initial};replay=read('campaign-1000-replay-ordinals-results.jsonl');assert len(replay)==25
for line,r in enumerate(replay,1):
 assert r['id'] in expected
 final[r['id']]=r;references[r['id']]=('campaign-1000-replay-ordinals-results.jsonl',line)
extras=[]
for name in ('campaign-long-emails-final-results.jsonl','campaign-article-sites-final-results.jsonl'):
 rows=read(name);assert len(rows)==25
 for line,r in enumerate(rows,1):references[r['id']]=(name,line)
 extras+=rows
all_final=list(final.values())+extras
assert len({r['id'] for r in all_final})==1050
failed=[r for r in all_final if not r['passed']]
assert not failed,[(r['id'],r['errors']) for r in failed]
with (T/'campaign-1000-final-results.jsonl').open('w',encoding='utf-8') as f:
 for r in all_final:f.write(json.dumps(r,ensure_ascii=False)+'\n')
with (T/'campaign-1000-index.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.writer(f);writer.writerow(['scenario','family','messages','passed','evidence_file','evidence_line'])
 for r in sorted(all_final,key=lambda r:r['id']):writer.writerow([r['id'],r['family'],len(r['turns']),r['passed'],*references[r['id']]])
files=['campaign-1000-corpus.jsonl','campaign-1000-final-results.jsonl','campaign-1000-index.csv','campaign-1000-replay-ordinals-results.jsonl','campaign-long-emails-final-corpus.jsonl','campaign-long-emails-final-results.jsonl','campaign-article-sites-final-corpus.jsonl','campaign-article-sites-final-results.jsonl','campaign-real-deepseek.json','campaign-real-ollama.json','semantic-chat-browser-results.json','compact-react-browser-results.json','campaign-1000-regression.xml']+[f'campaign-1000-shard-{j}-results.jsonl' for j in range(4)]
summary={'principal_scenarios':1000,'principal_turns':sum(len(r['turns']) for r in final.values()),'first_full_pass':{'passed':sum(r['passed'] for r in initial),'failed':sum(not r['passed'] for r in initial)},'replayed_scenarios':len(replay),'final_principal':{'passed':sum(r['passed'] for r in final.values()),'failed':sum(not r['passed'] for r in final.values())},'supplementary_unique_scenarios':50,'total_unique_scenarios':1050,'total_final_turns':sum(len(r['turns']) for r in all_final),'final_failed':len(failed),'real_sage_writes':0,'families':{f:{'executed':sum(r['family']==f for r in all_final),'passed':sum(r['family']==f and r['passed'] for r in all_final)} for f in sorted({r['family'] for r in all_final})},'boundaries':{'bulk':'FastAPI TestClient + actual isolated PostgreSQL; AI and Sage transports simulated','personas':'1000 isolated conversations, 4 test accounts and 4 workers; not 1000 simultaneous real users','real_deepseek_calls':3,'real_ollama_probes':1,'real_sage':'Read-only checks in separately recorded React probes; no live write validation','model_comprehension':'Real DeepSeek comprehension tested on 3 calls only. Bulk mocks cannot establish a 100% live-model comprehension rate.'},'sha256':{name:sha(T/name) for name in files}}
(T/'campaign-1000-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
summary['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'backend/app/services'/name for name in ('supplier_tasks.py','supplier_multiturn.py','supplier_dialogue.py','modification_dialogue.py','chat_turns.py')]+[T/'test_campaign_1000.py',T/'campaign_1000.py']}
(T/'campaign-1000-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('families','sha256')},ensure_ascii=True))
