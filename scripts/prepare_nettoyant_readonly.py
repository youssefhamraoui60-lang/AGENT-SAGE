"""Limited fixed SQL SELECTs only; no Sage SOAP, approval or write."""
import sys,json,secrets,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_tools
from app.core.config import settings
target=ROOT/'runtime/nettoyant-candidate.json'
if target.is_file():candidate=json.loads(target.read_text())['candidate']
else:candidate={'code':'TAI261026'+secrets.token_hex(3).upper(),'designation':'NETTOYANT DÉGRAISSANT ALCALIN','supplier':'F890','vat_requested_percent':'20'}
plan=chat_tools.Plan()
keys={'designation':chat_tools.search_articles(plan,candidate['designation']),'similar':chat_tools.search_articles(plan,'NETTOYANT'),'supplier':chat_tools.search_suppliers(plan,code='F890'),'tax_rate_candidates':chat_tools.get_tax_rules(plan,rate='20'),'candidate_code':chat_tools.check_article_duplicate(plan,candidate['code'])}
results=chat_tools.run(plan.calls);out={name:results.get(identifier,{'ok':False,'rows':[]}) for name,identifier in keys.items()}
tax_levels={row.get('VACITM_0','').strip() for row in out['similar'].get('rows',[]) if row.get('VACITM_0','').strip()}
if tax_levels:
    tax_plan=chat_tools.Plan();tax_refs={level:tax_plan.add('get_tax_determination',Level=level) for level in tax_levels}
    tax_results=chat_tools.run(tax_plan.calls)
    out['comparable_article_tax_determination_candidates']={level:tax_results.get(ref) for level,ref in tax_refs.items()}
context=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/read_supplier_tax_context.ps1')],capture_output=True,text=True,timeout=20)
try:out['supplier_tax_context']=json.loads(context.stdout.lstrip('\ufeff'))
except Exception:out['supplier_tax_context']={'ok':False}
report={'at':datetime.now(timezone.utc).isoformat(),'mode':'READ_ONLY_SQL','candidate':candidate,'results':out,'configured_http_identity_is_aiagt':settings.sage_soap_username.get_secret_value()=='AIAGT','dpapi_loaded':bool(settings.sage_soap_password.get_secret_value()),'configured_pool':settings.sage_soap_pool,'crl_bundle_present':Path(settings.sage_soap_crl_bundle).is_file(),'writes_disabled':not settings.sage_writes_enabled,'soap_authenticated_calls_sent':False,'human_approval':False,'xml_creation_complete':False}
target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
(ROOT/'logs/nettoyant-readonly-preparation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=str))
