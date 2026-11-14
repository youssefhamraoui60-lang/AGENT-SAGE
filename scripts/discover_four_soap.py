"""Read publication descriptions only, including bounded client-publication probes."""
import json,sys
from pathlib import Path
from types import SimpleNamespace
from lxml import etree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.services.sage_soap import SageReader
out={}
for publication in ['WS_ARTICLE','WS_AR_SITE','WS_FOURNIS','WS_CLIENT','WS_CUSTOMER','AOWSIMPORT']:
    config=SimpleNamespace(**{n:getattr(settings,n) for n in ['sage_soap_base_url','sage_soap_username','sage_soap_password','sage_soap_pool','sage_soap_language','sage_soap_timeout','sage_soap_ca_bundle']},sage_soap_publication=publication)
    try:
        desc=SageReader(config)._invoke('getDescription')
        assert desc.get('FOL')=='TEST' and desc.get('SOL')=='V12'
        (ROOT/'runtime'/('four-'+publication+'-description.xml')).write_bytes(etree.tostring(desc))
        fields=[{'group':g.get('NAM'),**dict(f.attrib)} for g in desc.findall('./ADXDATA/GRP') for f in g.findall('FLD')]
        out[publication]={'status':'PASS','object':desc.get('OBJ'),'folder':desc.get('FOL'),'solution':desc.get('SOL'),
            'admin_identity':desc.get('USER','').casefold() in ['admin','administrator'],
            'keys':[dict(n.attrib) for n in desc.findall('./ADXREAD//FLD')],'methods':[n.get('ID') for n in desc.iter('MET')],
            'input_fields':[n for n in fields if n.get('MOD')=='Input']}
    except Exception as exc:out[publication]={'status':'UNAVAILABLE','error_code':getattr(exc,'code',type(exc).__name__)}
(ROOT/'logs/four-creation-soap-discovery.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({p:{k:v for k,v in r.items() if k!='input_fields'} for p,r in out.items()},indent=2))
for p in ['WS_FOURNIS','WS_CLIENT']:
    print(json.dumps({'publication':p,'selected_fields':[n for n in out.get(p,{}).get('input_fields',[]) if n.get('NAM') in ['BPRNAM','BPRSHO','BSGCOD','BCGCOD','CRY','LAN','CUR','BPCNUM']]},ensure_ascii=False))
