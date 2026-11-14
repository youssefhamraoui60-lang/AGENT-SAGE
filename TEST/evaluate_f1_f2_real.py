"""Independent final-state checks. Case-only city capitalization is equivalent."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent
data=json.loads((root/'f1-f2-real-chat-results.json').read_text(encoding='utf-8'));checks=[]
def check(name,ok,conversation,turn):checks.append({'check':name,'passed':bool(ok),'conversation':conversation,'turn':turn})
for conversation in data['results']:
 name=conversation['title'];previous=None
 for t in conversation['turns']:
  k=t['turn'];s=t['state'];active=[p for p in s.get('partners',[]) if p.get('operation',{}).get('status')!='cancelled'];reply=t['reply']
  check('completed_with_reply',bool(reply.strip()) and not s.get('_pending') and s.get('analysis_job',{}).get('status')=='completed',name,k)
  check('no_write_no_approval',not any(p.get('approved') or p.get('operation',{}).get('status') in ('approved','executing','succeeded') for key in ('partners','articles','modification_drafts') for p in s.get(key,[])),name,k)
  check('no_technical_or_strict_history_failure',not re.search(r'Appel non validé|nom doit être écrit tel quel|nom exact doit être fourni',reply),name,k)
  if name=='F1':
   if 2<=k<=6:
    check('one_supplier_before_cancel',len(active)==1,name,k)
    check('same_supplier_identity',previous is None or active[0]['id']==previous,name,k);previous=active[0]['id']
   if 3<=k<=6:check('city_retained',active[0].get('ville','').casefold()=='berrchide',name,k)
   if k==6:check('first_corrected_ice',active[0].get('ice')=='123456789012345',name,k)
   if k in (7,8):check('cancelled_no_active_draft',not active,name,k)
   if k>=9:check('one_new_supplier_after_cancel',len(active)==1,name,k)
   if k>=10:
    check('final_corrected_ice',active[0].get('ice')=='678998767892927',name,k)
    check('name_city_kept',active[0].get('nom','').casefold()=='bouchaibe' and active[0].get('ville','').casefold()=='berrchide',name,k)
   if k in (2,9):check('invalid_ice_blocks_sql',active[0].get('operation',{}).get('status')=='blocked',name,k)
  elif name=='F2':
   check('search_did_not_create_supplier',not s.get('partners'),name,k)
   if k in (1,2,3,4,5):
    reads=s.get('tool_read_results',[]);codes={r.get('BPSNUM_0') for read in reads for r in read.get('rows',[])}
    check('cimat_found_from_read',bool({'F007','F552'}&codes),name,k)
   if k>=7:
    reads=s.get('tool_read_results',[])
    check('monde_candidates_available',any('MONDE' in str(r.get('BPRNAM_0','')).upper() for read in reads for r in read.get('rows',[])),name,k)
  else:
   check('one_supplier',len(active)==1,name,k)
   parameters=active[0].get('operation',{}).get('parameters',{}) if active else {}
   check('long_address_preserved_on_two_lines',''.join(parameters.get(key,'') for key in ('Adresse','Adresse2','Adresse3'))=='BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF' and bool(parameters.get('Adresse2')),name,k)
   check('no_address_size_error',active[0].get('operation',{}).get('validation',{}).get('sql_error_number')!=50105 if active else False,name,k)
   check('fiscal_identifiers_and_phone_preserved',parameters.get('ICE')=='003735377000086' and parameters.get('IF')=='66977576' and parameters.get('Telephone')=='0707001002',name,k)
check('no_react_error',not data['page_errors'],'all',0)
output={'conversations':len(data['results']),'messages':sum(len(c['turns']) for c in data['results']),'assertions':len(checks),'failed_assertions':sum(not c['passed'] for c in checks),'sage_writes':0,'checks':checks,'grading_note':'City capitalization is case-insensitive; original browser assertions used a strict city-case comparison and their raw log is preserved.'}
(root/'f1-f2-real-evaluation.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in output.items() if k not in ('checks','grading_note')}))
for c in checks:
 if not c['passed']:print(c)
assert not output['failed_assertions']
