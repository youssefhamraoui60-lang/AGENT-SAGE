"""Historical successful payload + cached schema + existing read-only SQL checks.
No SOAP, no approval, no Sage write, no executable operation registration.
"""
import sys,json,secrets,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
from lxml import etree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.schemas.sage_crud import Preparation
from app.services.sage_gateway import build_xml,RESOURCES,projection
from app.services.sage_soap import parse_xml
target=ROOT/'runtime/single-save-candidate-20261025.json'
if target.exists():candidate=json.loads(target.read_text())['candidate']
else:candidate={'code':'TAI261025'+secrets.token_hex(3).upper(),'designation':'ARTICLE TEST AGENT IA'}
source=ROOT/'examples/step4/manual-success-object.xml';original=parse_xml(source.read_bytes())
fields=[]
for group in original:
    for field in group:
        if field.get('NAME')!='ITMREF':fields.append({'group':group.get('ID'),'name':field.get('NAME'),'value':field.text or ''})
request={'action':'create','keys':{'ITMREF':candidate['code']},'fields':fields}
description=parse_xml((ROOT/'runtime/crud-WS_ARTICLE-description.xml').read_bytes())
xml=build_xml(description,RESOURCES['articles'],Preparation.model_validate(request))
old_fields=projection(original);new_fields=projection(parse_xml(xml))
assert {k:v for k,v in old_fields.items() if k!='ITM0_1.ITMREF'}=={k:v for k,v in new_fields.items() if k!='ITM0_1.ITMREF'}
sql_input={'code_article':candidate['code'],'designation':candidate['designation'],'categorie':'NEG','unite':'SAC','site':'','code_fournisseur':'','reference_article':'CPJ35'}
process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/article_agent_sql_reader.ps1')],input=json.dumps(sql_input),capture_output=True,text=True,encoding='utf-8',timeout=35)
try:sql=json.loads(process.stdout.lstrip('\ufeff'))
except Exception:sql={'ok':False,'code':'sql_reader_unavailable'}
report={'candidate':candidate,'request':request,'object_xml':xml,'historical_manual_source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'cached_mapping_validated':True,'mapping_timestamp':description.get('TIM'),'cached_identity_is_not_current_aiagt_proof':True,'only_changed_field':'ITM0_1.ITMREF','soap_inexistence_verified':False,'sql_read_only_check':sql,'human_approval':False,'executable_operation_registered':False,'save_sent':False,'at':datetime.now(timezone.utc).isoformat()}
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'examples/step4/single-save-candidate-20261025-NOT-SENT.xml').write_text(xml,encoding='utf-8')
print(json.dumps({'candidate':candidate,'mapping_valid':True,'sql_check_ok':sql.get('ok'),'sql_code_absent':not sql.get('article') if sql.get('ok') else None,'category_found':bool(sql.get('category')),'unit_found':bool(sql.get('unit')),'soap_inexistence_verified':False,'save_sent':False}))
