"""Real local Qwen + actual chat persistence, synthetic SQL, no ERP writes.

Only isolated local PostgreSQL schemas and Ollama loopback are permitted. Every
turn records assertions and provenance. A simulated user is not a human reviewer.
"""
import argparse,asyncio,copy,datetime,hashlib,json,socket,sys,time
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_isolated_regression as boundary
from app.core.config import settings
from app.services import conversation_chat as chat,business_store as db,sage_crud,article_agent,chat_model,chat_partners
from test_conversation_chat import FakeSQL
import httpx

PERSONAS=['débutant','magasinier','achats','commercial','comptable','administrateur',
          'orthographe approximative','changements d’avis','demande complexe','questions fréquentes']


def step(text,**expect):return {'message':text,'expected':expect}


def scenarios():
    result=[]
    for size in range(1,11):
        initial='Créer les '+str(size)+' articles suivants, site 201 :\n'+'\n'.join(
            f'{i}. Panneau série {size} modèle {i}, catégorie NEG, unité UN.' for i in range(1,size+1))
        base=[step(initial,article_count=size),step('Le site est-il 202 ?',unchanged=True),
              step('Site déclaré 202',articles={'site':'202'}),step('pas de forniseur',articles={'supplier_intent':'none'})]
        paths=[
          base+[step('la catigorer CADP',articles={'categorie':'CADP'}),step('unité M2',articles={'unite':'M2'}),step('Et pour le fournisseur ?',unchanged=True)],
          base+[step('Gestion stock 1',articles={'gestion_stock':'1'}),step('Peux-tu changer la catégorie en NEG ?',articles={'categorie':'NEG'}),step('Site déclaré 201',articles={'site':'201'})],
          base+[step('Remplacer - par _ dans les codes articles.',no_hyphens=True),step('Pour le premier article : code article TEST_RENOMME',target={'index':1,'code_article':'TEST_RENOMME'}),step('Vérifie le site 209',unchanged=True)],
          None,None,
          base+[step('Code fournisseur F234',articles={'code_fournisseur':'F234'}),step('TVA 20 %',articles={'taux_tva':'20'}),step('Catégorie comptable Marchandises',articles={'accounting_category':'Marchandises'}),step('Est-ce que le fournisseur existe ?',unchanged=True)],
          base+[step('Change la catégorie CADP. Le site existe-t-il ?',articles={'categorie':'CADP'}),step(f'Pour article {size} : site 209',target={'index':size,'site':'209'}),step('Quels sont les codes articles ?',unchanged=True)],
          base+[step('oui',no_approval=True),step('Change le site 202 vers 201',articles={'site':'201'}),step('Remplace la catégorie NEG par CADP',articles={'categorie':'CADP'})],
          base+[step('Crée un fournisseur Partenaire Atlas, pays MA, devise MAD.',partner_count=1),step('Crée un client Client Boréal, email contact@boreal.example.',partner_count=2),step('Vérifie la catégorie NEG',unchanged=True)],
          base+[step('unité M2',articles={'unite':'M2'}),step('unité UN',articles={'unite':'UN'}),
                step('Change le site 202 vers 209',articles={'site':'209'}),step('Le site est-il 201 ?',unchanged=True),
                step('la catigorer CADP',articles={'categorie':'CADP'}),step('Remplace la catégorie CADP par NEG',articles={'categorie':'NEG'}),
                step('Code fournisseur F234',articles={'code_fournisseur':'F234'}),step('sans fournisseur',articles={'supplier_intent':'none'}),
                step('TVA 20 %',articles={'taux_tva':'20'}),step('Quel est le code article ?',unchanged=True),step('oui',no_approval=True)]
        ]
        for path,kind in ((3,'fournisseur'),(4,'client')):
            names=' et '.join(f'Société {kind} {size} numéro {i}' for i in range(1,size+1))
            paths[path]=[step(f'Créer les {kind}s : '+names,partner_count=size),
                step(f'Pour le {kind} {size} : devise MAD',partner_target={'kind':kind,'index':size,'devise':'MAD'}),
                step(f'Pour le {kind} {size} : pays MA',partner_target={'kind':kind,'index':size,'pays':'MA'}),
                step(f'Pour le {kind} {size} : email contact@example.test',partner_target={'kind':kind,'index':size,'email':'contact@example.test'}),
                step(f'Le {kind} existe-t-il ?',unchanged=True),
                step(f'Pour le {kind} {size} : code TIERS{size:02}',partner_target={'kind':kind,'index':size,'code':f'TIERS{size:02}'}),
                step('oui',no_approval=True)]
        for path,turns in enumerate(paths):
            result.append({'id':f'conversation-{size:02}-{path:02}','persona':PERSONAS[path],
                           'cardinality':size,'path':path,'turns':turns})
    return result


def business_snapshot(state):
    return {'articles':[{k:v for k,v in a.items() if k in chat.FIELDS or k in ('id','supplier_intent')} for a in state.get('articles',[])],
            'partners':[{k:v for k,v in p.items() if k in ('id','kind') or k in chat_partners.FIELDS} for p in state.get('partners',[])]}


def check(before,state,expected):
    errors=[]
    if expected.get('unchanged') and business_snapshot(state)!=business_snapshot(before):errors.append('question_mutated_business_values')
    if 'article_count' in expected and len(state.get('articles',[]))!=expected['article_count']:errors.append('article_cardinality')
    if 'partner_count' in expected and len(state.get('partners',[]))!=expected['partner_count']:errors.append('partner_cardinality')
    for field,value in expected.get('articles',{}).items():
        if not state.get('articles') or any(a.get(field)!=value for a in state['articles']):errors.append('article_field:'+field)
    target=expected.get('target')
    if target:
        index=target['index']-1
        if index>=len(state.get('articles',[])):errors.append('target_missing')
        else:
            for field,value in target.items():
                if field!='index' and state['articles'][index].get(field)!=value:errors.append('target_field:'+field)
            for i,old in enumerate(before.get('articles',[])):
                if i!=index:
                    for field in target:
                        if field!='index' and state['articles'][i].get(field)!=old.get(field):errors.append('target_scope:'+field)
    target=expected.get('partner_target')
    if target:
        kind='supplier' if target['kind']=='fournisseur' else 'customer'
        selected=[p for p in state.get('partners',[]) if p['kind']==kind]
        index=target['index']-1
        if index>=len(selected):errors.append('partner_target_missing')
        else:
            for field,value in target.items():
                if field not in ('kind','index') and selected[index].get(field)!=value:errors.append('partner_field:'+field)
    if expected.get('no_hyphens') and any('-' in a.get('code_article','') for a in state.get('articles',[])):errors.append('naming_not_applied')
    if any(a.get('approved') or a.get('outcome') or a.get('operation') for a in state.get('articles',[])):errors.append('forbidden_write_or_approval')
    return errors


async def run(args):
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory=ROOT/'tests/ai-evaluation/conversations'/stamp;directory.mkdir(parents=True)
    schema='evaluation_test_'+uuid4().hex[:12];settings.business_schema=schema
    settings.sage_powershell_chat_enabled=False
    if settings.ollama_url!='http://127.0.0.1:11434':raise RuntimeError('LOCAL_OLLAMA_REQUIRED')
    # Permit only Ollama; external networking and all child processes stay denied.
    previous=socket.socket.connect
    def connect(sock,address):
        if address[0]=='127.0.0.1' and address[1]==11434:return boundary.boundary._socket_connect(sock,address)
        return previous(sock,address)
    socket.socket.connect=connect
    chat.tools.run=FakeSQL()
    db.migrate();sage_crud.migrate();article_agent.migrate();chat.migrate()
    async with httpx.AsyncClient(timeout=5,trust_env=False) as client:
        response=await client.get(settings.ollama_url+'/api/tags');response.raise_for_status()
        model=next(x for x in response.json()['models'] if x['name']==settings.ollama_model)
    selected=[c for c in scenarios() if not args.only or c['id'] in args.only.split(',')]
    if args.limit:selected=selected[:args.limit]
    manifest={'started_at':stamp,'schema':schema,'model':model['name'],'model_digest':model['digest'],
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/app').rglob('*.py')},
              'prompt_sha256':hashlib.sha256(chat_model.PROMPT.encode()).hexdigest(),'sql':'synthetic_fixed_fixtures',
              'real_ERP_writes':0,'human_review_performed':False,'conversations':[]}
    (directory/'scenario-inputs.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'directory':str(directory),'planned':len(selected),'schema':schema}),flush=True)
    for scenario in selected:
        owner=uuid4();session=chat.create(owner)
        record={**scenario,'owner_id':str(owner),'conversation_id':str(session['id']),'results':[]}
        for number,turn in enumerate(scenario['turns'],1):
            before=copy.deepcopy(session['state']);started=time.perf_counter()
            try:
                session=await chat.send(owner,session['id'],turn['message'],session['revision'])
                errors=check(before,session['state'],turn['expected'])
                last=next(m for m in reversed(session['messages']) if m['role']=='assistant')
                result={'turn':number,**turn,'status':'failed' if errors else 'passed','errors':errors,
                        'actual':business_snapshot(session['state']),'reply':last['content'],
                        'provenance':last.get('payload',{}).get('provenance'),
                        'delta':last.get('payload',{}).get('delta'),
                        'performance':session.get('performance')}
            except Exception as exc:
                session=chat.read(owner,session['id'])
                result={'turn':number,**turn,'status':'failed','errors':['exception:'+type(exc).__name__],
                        'actual':business_snapshot(session['state'])}
            result['seconds']=round(time.perf_counter()-started,3);record['results'].append(result)
            (directory/(scenario['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str),encoding='utf8')
            print(json.dumps({'id':scenario['id'],'turn':number,'status':result['status'],'errors':result['errors'],'seconds':result['seconds']}),flush=True)
        record['passed']=all(r['status']=='passed' for r in record['results'])
        manifest['conversations'].append({'id':scenario['id'],'passed':record['passed'],'turns':len(record['results'])})
        (directory/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    manifest['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest['passed']=sum(c['passed'] for c in manifest['conversations'])
    (directory/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'completed':len(selected),'passed':manifest['passed'],'directory':str(directory)}),flush=True)
    return 0 if manifest['passed']==len(selected) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);parser.add_argument('--only',default='')
    raise SystemExit(asyncio.run(run(parser.parse_args())))
