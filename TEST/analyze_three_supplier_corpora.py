"""Additional independent field oracles; never grade prose with generated AI."""
import json,re,sys,collections,csv,hashlib
from pathlib import Path
from three_supplier_corpora import cases
ROOT=Path(__file__).resolve().parent;SPECS={c['id']:c for c in cases()}
def norm(v):
 import unicodedata
 return ''.join(c for c in unicodedata.normalize('NFD',str(v)).casefold() if not unicodedata.combining(c)).strip()
def evaluate(item):
 spec=SPECS[item['id']];failures=[];assertions=0
 for t in item['turns']:
  k=t['turn'];state=t.get('state') or {};rows=state.get('partners',[]);text=t['text'];n=norm(text);kind=t.get('type') or '';checks=[]
  def check(label,passed,expected=None,actual=None):
   nonlocal assertions
   assertions+=1
   if not passed:checks.append({'turn':k,'check':label,'expected':expected,'actual':actual})
  for err in t.get('errors',[]):
   # Old bulk-driver assertions mistakenly treated an article designation as a
   # supplier name for mixed article/supplier emails. Do not retain that false
   # failure; article preparation has its separate regression suite.
   if kind=='creation_article_lie' and err.startswith('declared_name_not_preserved:'):continue
   check(err,False)
  if t.get('error'):check('real_browser_transport',False,actual=t['error'])
  check('reply_and_completed',bool(t.get('reply')) and not state.get('_pending') and state.get('analysis_job',{}).get('status')=='completed')
  check('no_unapproved_main_write',not any(p.get('approved') or p.get('operation',{}).get('status') in ('executing','approved','succeeded') for key in ('partners','articles','modification_drafts') for p in state.get(key,[])))
  declared=re.findall(r'(?<!\w)([A-Z][A-Z0-9 ]{3,}? TEST(?: [0-9]{3})?)(?!\w)',text)
  name_cue=kind=='create' or kind in ('creation_simple','creation_multiple') or (spec['dataset']=='darija' and re.search(r'\b(?:smito|smiya|lowwel|tani|jdid)\b',n))
  if name_cue and not re.search(r'\bf\d+\b',n):
   for name in declared:
    # Explicit negated old names are not the corrected identity.
    before=norm(text[:text.find(name)])[-15:]
    if re.search(r'\b(?:pas|machi)\s*$',before):continue
    check('declared_supplier_name',any(norm(p.get('nom',''))==norm(name) for p in rows),name,[p.get('nom') for p in rows])
  for p in rows:
   if p.get('nom'):check('identity_not_user_instruction',not re.match(r'^(?:bghit|bghina|3afak|chno|wach|ma3reftch)\s+',norm(p['nom'])),actual=p['nom'])
  active=[p for p in rows if p.get('operation',{}).get('status') not in ('cancelled','succeeded','failed','ambiguous','unverified')]
  field_scope=not re.search(r'\bf\d+\b|\b(?:recherche|cherche|9elleb|qelleb|consulte|verifie)\b',n) and len(active)==1
  if field_scope:
   p=active[0]
   phone=re.search(r'\b(?:telephone|telefon|tel)\s*[:=]?\s*(0[0-9]{9})\b',n)
   if phone:check('declared_phone_preserved',p.get('telephone')==phone[1],phone[1],p.get('telephone'))
   ice=re.search(r'\bice\s*(?:(?:est|cest|c.est|dyalo|dyalou)\s*)?[:=]?\s*([0-9]{10,20})\b',n)
   if ice:check('literal_ice_with_initial_zeros',p.get('ice')==ice[1],ice[1],p.get('ice'))
   city=re.search(r'\bville\s*(?:est|c.est|doit etre|:)\s*([a-z]+)\b',n)
   if city:check('explicit_city_corrected',norm(p.get('ville',''))==city[1],city[1],p.get('ville'))
  failures.extend(checks)
 return {'id':item['id'],'dataset':spec['dataset'],'theme':spec['theme'],'messages':len(item['turns']),'assertions':assertions,'passed':not failures,'failures':failures,'confirmation_tested':item.get('confirmation_tested',False)}
def phase(prefix):
 items=[];summaries=[]
 for shard in range(4):
  path=ROOT/f'{prefix}-{shard}.jsonl'
  if path.exists():items.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines())
  path=ROOT/f'{prefix}-{shard}-summary.json'
  if path.exists():summaries.append(json.loads(path.read_text(encoding='utf-8')))
 results=[evaluate(i) for i in items];counter=collections.Counter(e['check'] for r in results for e in r['failures'])
 out={'cases':len(results),'messages':sum(r['messages'] for r in results),'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'assertions':sum(r['assertions'] for r in results),'failures':dict(counter),'confirmation_forks':[p for s in summaries for p in s['confirmation_forks']],'results':results,'scope':'real backend/isolated PostgreSQL; simulated AI outage and simulated Sage'}
 (ROOT/f'{prefix}-evaluation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 return out
if __name__=='__main__':
 for prefix in sys.argv[1:] or ['three-corpora-baseline','three-corpora-final']:
  r=phase(prefix);print(prefix,json.dumps({k:v for k,v in r.items() if k not in ('results','confirmation_forks')},ensure_ascii=False))
