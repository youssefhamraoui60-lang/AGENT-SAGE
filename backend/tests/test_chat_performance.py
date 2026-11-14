"""Optimization invariants: no validation removal, cache freshness and secure streaming."""
import json
import asyncio
import pytest
from app.services import chat_tools as tools,chat_model as model,chat_fast_extract as fast
from test_conversation_chat import fixture,create,TEXT,initial

def test_literal_article_and_unknown_clause():
    value,proof=fast.extract('Crée un article Ciment CPJ35, catégorie NEG, unité SAC, pour le site 201.',{})
    assert value.articles[0].designation=='Ciment CPJ35'
    assert value.shared.site=='201' and value.shared.categorie=='NEG'
    assert proof['validation_and_sql_required'] and not proof['real_model_called']
    assert fast.extract('Crée un article Ciment, catégorie NEG, unité SAC, fournisseur inconnu.',{}) is None
    greeting,proof=fast.extract('Bonjour !',{})
    assert greeting.intent=='other' and not greeting.articles and not proof['real_model_called']

def test_questions_cannot_become_site_or_change_category():
    state={'articles':[{'site':'131','categorie':'AR'}]}
    delta,_=fast.extract('Et pour le site est-ce qu’il existe ?',state)
    assert not delta.shared.model_dump(exclude_unset=True)
    delta,_=fast.extract('Recherche la catégorie NEGOSE.',state)
    assert not delta.shared.model_dump(exclude_unset=True)

def test_numbered_ten_preserves_every_literal_field():
    text='Créer les 10 articles suivants, site 201 :\n'+'\n'.join(f'{i}. Panneau {i}, catégorie {"AR" if i%2 else "NEG"}, unité {"M2" if i%2 else "UN"}.' for i in range(1,11))
    value,proof=fast.extract(text,{})
    assert len(value.articles)==10 and value.shared.site=='201'
    assert [x.designation for x in value.articles]==[f'Panneau {i}' for i in range(1,11)]
    assert [x.unite for x in value.articles]==['M2' if i%2 else 'UN' for i in range(1,11)]
    assert not proof['real_model_called']
    assert fast.extract(text.replace('Panneau 6,','Panneau 6, champ inconnu 7,'),{}) is None

def test_literal_pair_is_general_and_never_drops_unknown_fields():
    text="Crée deux articles : Panneau rouge et Panneau bleu. Unité M2, fournisseur SOCIETE INCONNUE, catégorie NEG."
    delta,proof=fast.extract(text,{})
    assert [a.designation for a in delta.articles]==['Panneau rouge','Panneau bleu']
    assert delta.shared.fournisseur_nom=='SOCIETE INCONNUE' and delta.shared.unite=='M2'
    assert proof['validation_and_sql_required']
    assert fast.extract(text+' Prix 45.',{}) is None
    assert fast.extract(text.replace('Panneau rouge et','Panneau rouge et vert et'),{}) is None

def test_cache_never_reuses_duplicates_and_can_invalidate(monkeypatch):
    tools.invalidate_cache();count=[]
    def worker(calls):
        count.extend(calls)
        return {'results':[{'id':c['id'],'tool':c['tool'],'ok':True,'rows':[], 'source':'SQL TEST','checked_at':'original-time'} for c in calls]}
    monkeypatch.setattr(tools,'_worker',worker)
    calls=[{'id':'a','tool':'get_sites','args':{'Site':'201'}},{'id':'b','tool':'check_article_duplicate','args':{'Code':'A'}}]
    tools.run(calls);value=tools.run(calls)
    assert len(count)==3 and value['a']['cache_hit'] and value['a']['checked_at']=='original-time'
    tools.invalidate_cache();tools.run(calls);assert len(count)==5
    tools.invalidate_cache()

def test_failed_queries_not_cached(monkeypatch):
    tools.invalidate_cache();count=[]
    def worker(calls):
        count.extend(calls)
        return {'results':[{'id':c['id'],'tool':c['tool'],'ok':False,'rows':[]} for c in calls]}
    monkeypatch.setattr(tools,'_worker',worker)
    call=[{'id':'a','tool':'get_sites','args':{'Site':'201'}}]
    tools.run(call);tools.run(call);assert len(count)==2

def test_worker_batches_are_bounded(monkeypatch):
    sizes=[]
    def worker(calls):
        sizes.append(len(calls))
        return {'results':[{'id':c['id'],'tool':c['tool'],'ok':True,'rows':[]} for c in calls]}
    monkeypatch.setattr(tools,'_worker',worker)
    calls=[{'id':str(i),'tool':'check_article_duplicate','args':{'Code':str(i)}} for i in range(180)]
    assert len(tools.run(calls))==180 and max(sizes)<=60
    with pytest.raises(ValueError):tools.run(calls+[calls[0]])

def test_one_qwen_call_compact_memory_and_keep_alive(monkeypatch):
    captured=[]
    async def request(client,payload):
        captured.append(payload)
        return {'done':True,'message':{'content':'{"intent":"update","shared":{"unite":"M2"}}'}},{}
    monkeypatch.setattr(model,'request_stream',request)
    token=model.FORCE_AI.set(True)
    try:
        asyncio.run(model.extract('unité M2',{'articles':[{'designation':'A'}],'pending':[]},[{'role':'assistant','content':'NEVER_SEND_THIS_SQL_PROSE'},{'role':'user','content':'ancien'}]))
    finally:model.FORCE_AI.reset(token)
    assert len(captured)==1 and captured[0]['keep_alive']=='30m'
    assert 'NEVER_SEND_THIS_SQL_PROSE' not in json.dumps(captured)
    assert len(captured[0]['messages'])==2

def test_partial_model_list_is_rejected_without_second_inference(monkeypatch):
    calls=[]
    async def request(client,payload):
        calls.append(payload)
        return {'done':True,'message':{'content':json.dumps({'intent':'new','articles':[{'designation':str(i)} for i in range(4)]})}},{}
    monkeypatch.setattr(model,'request_stream',request)
    token=model.FORCE_AI.set(True)
    try:
        with pytest.raises(ValueError,match='incomplete_article_list'):asyncio.run(model.extract('Prépare dix articles distincts',{},[]))
    finally:model.FORCE_AI.reset(token)
    assert len(calls)==1
    assert calls[0]['format']['properties']['articles']['minItems']==10

def test_stream_retains_auth_and_final_validated_result(fixture):
    client,q=fixture;c=create(client);q.append(initial())
    route='/api/v1/chat/conversations/'+c['id']+'/messages/stream'
    headers=client.headers.pop('X-Chat-CSRF');assert client.post(route,json={'content':TEXT,'revision':c['revision']}).status_code==403
    client.headers['X-Chat-CSRF']=headers
    response=client.post(route,json={'content':TEXT,'revision':c['revision']})
    assert response.status_code==200
    events=[json.loads(x[6:]) for x in response.text.splitlines() if x.startswith('data: ')]
    assert [x['event'] for x in events]==['accepted','understanding','drafts','text','result']
    result=events[-1]['data'];assert len(result['state']['articles'])==2
    assert result['security']['ready'] is False
    assert 'fastapi_service_ms' in result['performance']
    assert client.post(route,json={'content':TEXT,'revision':c['revision']}).status_code==409
    from uuid import uuid4
    assert client.post('/api/v1/chat/conversations/'+str(uuid4())+'/messages/stream',json={'content':TEXT,'revision':1}).status_code==404
