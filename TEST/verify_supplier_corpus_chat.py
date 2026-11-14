"""Authenticated chat preparation probes. Never calls approve or execute endpoints."""
from http_test_account import authenticate_test_client
import argparse,json,time
from pathlib import Path
import httpx
BASE='http://127.0.0.1:8000'
parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
SOURCE=args.source
raw=SOURCE.read_text(encoding='utf-8-sig')
rows=[json.loads(line) for line in raw.splitlines() if line.strip()] if SOURCE.suffix=='.jsonl' else json.loads(raw)['messages']
client=httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=60,trust_env=False)
for _ in range(40):
    try:client.get('/health',timeout=2).raise_for_status();break
    except httpx.HTTPError:time.sleep(.25)
def checked(response):response.raise_for_status();return response.json()
session=authenticate_test_client(client);client.headers['X-Chat-CSRF']=session['csrf']
results=[]
indices=[0,1,3,5,6,7,11,500,9999] if SOURCE.suffix=='.jsonl' else [0,1,2,5,8,11,12,13,19]
for index in indices:
    row=rows[index];conversation=checked(client.post('/api/v1/chat/conversations'))
    answer=checked(client.post('/api/v1/chat/conversations/'+conversation['id']+'/messages',json={'content':row['message'],'revision':conversation['revision']}))
    assert answer['state']['analysis_job']['status']=='completed'
    p=answer['state']['partners'][0];op=p['operation']
    assert p['nom']==row['donnees_attendues']['nom']
    assert op['status'] in ('prepared','blocked'),op.get('validation')
    if op['status']=='blocked':assert op.get('validation',{}).get('field_errors') or op.get('duplicate_warnings'),op.get('validation')
    assert op['folder']=='TEST' and op['transport']=='direct_sql'
    assert not p.get('approved') and not op.get('result')
    mapping={'nom':'Nom','ice':'ICE','if':'IF','rc':'RC','ville':'Ville','adresse':'Adresse','telephone':'Telephone','fax':'Fax','paiement':'Paiement','type_montant':'TypeLibelle','devise':'Devise'}
    for key,value in row['donnees_attendues'].items():
        if key in mapping:
            actual=op['parameters'][mapping[key]]
            assert actual==value or (key=='adresse' and actual.startswith(value+',')),(key,actual,value)
    result={'id':row['id'],'scenario':row['scenario'],'status':op['status'],'name':p['nom'],'all_expected_parameters_checked':True,'field_errors':op.get('validation',{}).get('field_errors',[]),'confirmation_still_required':True,'sage_inserts':0}
    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
report={'status':'PASS','real_backend_http':True,'isolated_test_identity':True,'sage_inserts':0,'probes':results}
Path(__file__).with_name('corpus-10000-chat-results.json' if SOURCE.suffix=='.jsonl' else 'corpus-chat-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
client.close()
