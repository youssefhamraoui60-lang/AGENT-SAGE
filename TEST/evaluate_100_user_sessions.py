"""Independent assertions from the supplied corpus, never model-generated grades.

Reads evidence only. Does not connect to Sage, providers or the application.
Free-form naturalness and business completeness still require human review.
"""
import json,re,collections,unicodedata,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'sessions-100-real'
source=json.loads((ROOT/'source.json').read_text(encoding='utf-8'))
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s)) if not unicodedata.combining(c)).casefold().strip()
def names(text):return re.findall(r'\b([A-Z][A-ZÉÈÀÂÙÊÎÔÇ0-9 -]*? TEST \d{3}(?: SERVICES)?)\b',text)
def city(text):
 cities=['Casablanca','Rabat','Agadir','Tanger','Marrakech','Fès','Oujda','Meknès','Salé','Kénitra']
 match=re.search(r'(?:\ba\s+|\bville\s*:?\s*)('+ '|'.join(norm(c) for c in cities)+r')\b',norm(text))
 return next((c for c in cities if match and norm(c)==match.group(1)),None)
def pay(text):
 n=norm(text);prefix='CHQ' if 'cheque' in n else 'VIR' if 'virement' in n else 'EFF' if 'effet' in n else 'ESP' if 'espece' in n else None
 days=re.search(r'(?<!\d)(120|90|60|30)(?!\d)',n)
 return prefix+(days.group(1) if days else '00') if prefix else None
def payment(p):return p.get('operation',{}).get('parameters',{}).get('Paiement')
def active(rows):return [p for p in rows if p.get('operation',{}).get('status') not in ('cancelled','succeeded','failed','ambiguous','unverified')]
results=[]
for spec in source['sessions']:
 path=ROOT/(spec['id']+'.json')
 if not path.exists():continue
 evidence=json.loads(path.read_text(encoding='utf-8'));idx=int(spec['id'][1:]);theme=(idx-1)//10;messages=spec['messages_utilisateur'];checks=[]
 def check(label,ok,turn,expected=None,actual=None):checks.append({'check':label,'passed':bool(ok),'turn':turn,'expected':expected,'actual':actual})
 allnames=names(' '.join(messages));expected_name=allnames[0] if allnames else None
 expected_city=city(messages[1] if theme==7 else messages[0])
 trace=[]
 for t in evidence['turns']:
  k=t['turn'];state=t.get('state') or {};rows=state.get('partners',[]);current=active(rows);mods=state.get('modification_drafts',[]);trace.extend(state.get('tool_orchestration',{}).get('calls',[]));reply=t.get('reply') or ''
  check('reply_visible_and_turn_completed',not t.get('error') and bool(reply.strip()) and not state.get('_pending') and state.get('analysis_job',{}).get('status')=='completed',k)
  check('useful_response_not_generic_tool_error',not norm(reply).startswith('appel non valide. corrigez les arguments'),k)
  check('no_approval_no_write',not any(p.get('approved') or p.get('operation',{}).get('status') in ('executing','approved','succeeded') for p in rows+mods+state.get('articles',[])),k)
  claimed=re.search(r'(?:a ete|ont ete|j.ai|nous avons)\s+(?:bien\s+)?(?:cree|modifie|supprime|desactive|reactive)\b|(?:cree|modifie|supprime|desactive|reactive).{0,15}avec succes',norm(reply))
  check('no_false_sage_success',not claimed or bool(re.search(r'aucun|n.a pas|n.ont pas|ne .{0,30}pas',norm(reply))),k)
  if theme in (0,1,7,8) and (theme!=7 or k>=2):
   check('one_supplier_no_duplicate_draft',len(rows)==1,k,1,len(rows))
   matched=next((p for p in rows if p.get('nom')==expected_name),{})
   check('supplier_name_preserved',bool(matched),k,expected_name,[p.get('nom') for p in rows])
   c='Agadir' if theme==8 and k>=4 else expected_city
   check('supplier_city_preserved',matched.get('ville')==c,k,c,matched.get('ville'))
   if theme in (0,7,8):check('unknown_ice_not_invented',not any(p.get('ice') for p in rows),k)
   if theme==0 and k>=2:
    phone=re.search(r'\b0\d{9}\b',messages[1]).group(0)
    check('phone_and_legal_form_same_supplier',matched.get('telephone')==phone and matched.get('forme_juridique')=='SARL AU',k,{'telephone':phone,'forme_juridique':'SARL AU'},{f:matched.get(f) for f in ('telephone','forme_juridique')})
   if theme==8:check('legal_form_retained',matched.get('forme_juridique')=='SARL',k,'SARL',matched.get('forme_juridique'))
   threshold={0:3,1:4,7:3,8:1}[theme]
   if k>=threshold:
    expected_pay=pay(messages[{0:2,1:3,7:2,8:0}[theme]])
    check('payment_code_matches_request',payment(matched)==expected_pay,k,expected_pay,payment(matched))
   if theme==1 and k in (2,3):
    check('ambiguous_payment_clarified',bool(re.search(r'precis|quel|delai|option|choix|comptant|30|60|90|120|ambigu',norm(reply))),k)
  if theme==2:
   original=names(messages[0]);wanted=[names(messages[3])[0],original[1]] if k>=4 else original
   check('two_independent_drafts',len(rows)==2 and len({p.get('id') for p in rows})==2,k,2,len(rows))
   for j,name in enumerate(wanted):
    p=next((p for p in rows if p.get('nom')==name),{})
    check(f'supplier_{j+1}_identity_city',bool(p) and p.get('ville')==['Casablanca','Rabat'][j],k,name,{f:p.get(f) for f in ('nom','ville')})
    if k>=2:check(f'supplier_{j+1}_legal_form',p.get('forme_juridique')==['SARL AU','SARL'][j],k,['SARL AU','SARL'][j],p.get('forme_juridique'))
    if k>=3:check(f'supplier_{j+1}_payment',payment(p)==['CHQ00','CHQ60'][j],k,['CHQ00','CHQ60'][j],payment(p))
    if k>=2 and j==1:
     phone=re.search(r'\b0\d{9}\b',messages[1]).group(0);check('second_phone_not_assigned_first',p.get('telephone')==phone and not rows[0].get('telephone'),k)
  if theme==3:
   if k>=2:check('cancelled_creation_never_resurrected',not current,k,[],[p.get('nom') for p in current])
   if k>=4:check('no_modification_without_new_value',not any(p.get('changes') for p in active(mods)),k)
   if k>=5:check('cancelled_modification_no_confirmation',not active(mods),k,[],[(p.get('code'),p.get('operation',{}).get('status')) for p in active(mods)])
  if theme in (4,5):
   check('consultation_not_creation',not rows,k,[],[p.get('nom') for p in rows])
   if theme==4 and k==1:check('destructive_delete_refused',bool(re.search(r'pas|refus|impossible|interdit|non|secur|conserv|desactiv',norm(reply))),k)
   if k==6:check('analysis_only_no_active_write_plan',not any(p.get('operation',{}).get('status')=='prepared' for p in mods),k)
   if theme==5 and k>=3:
    target=re.findall(r'\bF\d+\b',messages[2])[-1]
    focus=((state.get('supplier_tasks') or {}).get('control') or {}).get('code')
    last_reads=state.get('tool_read_results',[])
    check('corrected_existing_supplier_target',focus==target or bool(last_reads and last_reads[-1].get('code')==target),k,target,{'control':focus,'last_read':last_reads[-1].get('code') if last_reads else None})
  if theme==6:
   check('update_not_creation',not rows,k,[],[p.get('nom') for p in rows])
   if k>=4:
    requested=re.search(r'\bF\d+\b',messages[0]).group(0)
    relevant=[p for p in mods if p.get('code')==requested]
    readable=any(e.get('result',{}).get('ok') and e.get('result',{}).get('code')==requested for e in trace if e.get('tool') in ('read_sage','select_for_modification'))
    check('payment_update_or_truthful_read_limit',any(p.get('changes',{}).get('payment')=='CHQ60' for p in relevant) or (not readable and bool(re.search(r'introuv|aucun|non trouv|indispon|impossible|ambigu|lecture|verifi',norm(reply)))),k,'CHQ60 or explained unavailable read',[p.get('changes') for p in relevant])
  if theme==9:
   if k<6:
    p=next((p for p in rows if p.get('nom')==expected_name),{})
    check('combined_creation_kept_separate',len(rows)==1 and bool(p) and p.get('ville')==expected_city,k,{'nom':expected_name,'ville':expected_city},[{f:p.get(f) for f in ('nom','ville')} for p in rows])
   if k==2:
    p=next((p for p in rows if p.get('nom')==expected_name),{});check('combined_request_payment',payment(p)==pay(messages[1]),k,pay(messages[1]),payment(p))
   if k>=6:check('combined_creation_cancelled',not current,k,[],[p.get('nom') for p in current])
  if t.get('rendered') is not None:check('react_reply_rendered',bool(t['rendered'].strip()),k)
 # An actual read must be represented by a successful tool result, not prose alone.
 read_calls=[e for e in trace if e.get('tool') in ('read_sage','select_for_modification','sage_get_supplier')]
 check('lookup_attempt_instrumented',bool(read_calls) or any(p.get('preparation') for t in evidence['turns'] for p in (t.get('state') or {}).get('partners',[])),len(messages))
 failures=[c for c in checks if not c['passed']]
 results.append({'id':spec['id'],'theme':spec['theme'],'passed':not failures and not evidence['errors'],'messages':len(evidence['turns']),'assertions':len(checks),'failed_assertions':len(failures),'failures':failures,'transport_errors':evidence['errors'],'read_calls':len(read_calls)})
counter=collections.Counter(c['check'] for r in results for c in r['failures'])
out={'sessions_evaluated':len(results),'messages':sum(r['messages'] for r in results),'sessions_passed':sum(r['passed'] for r in results),'sessions_failed':sum(not r['passed'] for r in results),'assertions':sum(r['assertions'] for r in results),'failed_assertions':sum(r['failed_assertions'] for r in results),'failure_categories':dict(counter),'source_sha256':hashlib.sha256((ROOT/'source.json').read_bytes()).hexdigest(),'grading':'Deterministic state/transport checks; free-text semantics not fully certified','results':results}
(ROOT/'evaluation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
suite=ET.Element('testsuite',name='100 real supplier conversations',tests=str(len(results)),failures=str(out['sessions_failed']),errors='0')
for row in results:
 case=ET.SubElement(suite,'testcase',name=row['id'],classname=row['theme'])
 if not row['passed']:ET.SubElement(case,'failure',message=f"{row['failed_assertions']} failed assertions").text=json.dumps({'failures':row['failures'],'transport':row['transport_errors']},ensure_ascii=False)
ET.ElementTree(suite).write(ROOT/'evaluation.xml',encoding='utf-8',xml_declaration=True)
print(json.dumps({k:v for k,v in out.items() if k!='results'},ensure_ascii=False))
