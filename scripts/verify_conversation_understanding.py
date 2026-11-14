"""Replay the reported conversation through real HTTP/SQL/model, without approvals or SAVE."""
import json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
s=requests.Session();s.trust_env=False
s.headers['Origin']='http://127.0.0.1:8000'
base='http://127.0.0.1:8000/api/v1/chat'
r=s.post(base+'/session',timeout=15);r.raise_for_status()
s.headers['X-Chat-CSRF']=r.json()['csrf']
r=s.post(base+'/conversations',timeout=15);r.raise_for_status();value=r.json()
report={'mode':'REAL_HTTP_CONVERSATION_AND_SQL_NO_APPROVAL_NO_SAVE','save_attempts':0,'conversation_id':value['id'],'turns':[]}
texts=[
    'Bonjour, j’ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie NEG.',
    'LE SOSITER OB et le site 202',
    'pas de forniseur dans cette article',
]
try:
    for text in texts:
        r=s.post(base+'/conversations/'+value['id']+'/messages',json={'content':text,'revision':value['revision']},timeout=210)
        r.raise_for_status();value=r.json()
        report['turns'].append({'input':text,'articles':[{
            k:a.get(k) for k in ('designation','code_article','categorie','unite','site','fournisseur_nom','code_fournisseur')
        } for a in value['state']['articles']],
            'answer':next(m['content'] for m in reversed(value['messages']) if m['role']=='assistant')})
    articles=value['state']['articles']
    assert len(articles)==2
    assert all(a['site']=='202' and a['categorie']=='NEG' and a['unite']=='M2' for a in articles)
    assert all(not a.get('fournisseur_nom') and not a.get('code_fournisseur') for a in articles)
    assert not any(q['field']=='code_fournisseur' for q in value['state'].get('pending',[]))
    assert all(a.get('checks',{}).get('verified',{}).get('categorie') for a in articles)
    report['status']='PASS'
finally:
    (ROOT/'logs/conversation-understanding-real-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report.get('status','FAILED'),'save_attempts':0,'turns':report['turns']},ensure_ascii=True))
