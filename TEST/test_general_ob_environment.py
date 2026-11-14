import copy,json,subprocess
import pytest
from uuid import UUID
from test_article_direct_sql import fixture,simulated,article,proof,step
from app.services import article_sql as sql,conversation_chat as chat,business_store as db,conversation_tools as engine
from app.services.sage_crud import CrudError

def test_ob_button_creates_general_conversation(fixture):
    c,_=fixture;s=c.post('/api/v1/chat/conversations',json={'discussion_mode':'ob'}).json()
    assert s['folder']=='OB' and s['state']['discussion_mode']=='general'
    assert 'article' in s['messages'][0]['content'].lower()

def test_ob_article_and_two_sites_plan_and_confirmations(fixture,simulated,monkeypatch):
    c,_=fixture;schema,_=simulated;schema['folder']='OB';calls=[]
    monkeypatch.setattr(sql,'catalog',lambda *a,**kw:copy.deepcopy(schema) if kw.get('folder')=='OB' else pytest.fail('TEST read in OB'))
    def transport(action,plan=None,execute=False,**kwargs):
        assert plan['folder']==kwargs.get('folder')=='OB';calls.append(execute)
        return {**proof(plan,execute),'folder':'OB'}
    monkeypatch.setattr(sql,'transport',transport)
    s=c.post('/api/v1/chat/conversations',json={'discussion_mode':'ob'}).json()
    with db.connection() as conn:
        row=conn.execute('SELECT owner_id,state FROM chat_conversations WHERE id=%s',(s['id'],)).fetchone()
        row['state']['articles']=[article(dossier_cible='OB',requested_sites=['201','202'])]
        chat.save_conversation_context(conn,row['owner_id'],s['id'],row['state'])
    s=chat.read(row['owner_id'],UUID(s['id']))
    r=step(c,s,'prepare');assert r.status_code==200,r.text
    s=r.json();op=s['state']['articles'][0]['operation'];assert op['folder']=='OB'
    assert {n['overrides']['STOFCY_0'] for n in op['plan']['nodes'] if n['table']=='ITMFACILIT'}=={'201','202'}
    assert step(c,s,'execute',True).status_code==403
    s=step(c,s,'approve',True).json();r=step(c,s,'execute',True)
    assert r.status_code==200,r.text
    assert r.json()['state']['articles'][0]['operation']['status']=='succeeded'
    assert calls==[False,True]  # simulated writes only

def test_article_transport_rejects_cross_folder_and_binds_ob(monkeypatch):
    calls=[]
    def process(args,**kw):
        calls.append((json.loads(kw['input']),kw['env']['SAGE_SUPPLIER_TARGET_FOLDER']))
        return subprocess.CompletedProcess(args,0,json.dumps({'ok':True,'folder':'OB'}),'')
    monkeypatch.setattr(sql.subprocess,'run',process)
    sql.transport('catalog',folder='OB');assert calls[0][0]['folder']==calls[0][1]=='OB'
    with pytest.raises(CrudError):sql.transport('plan',{'folder':'TEST'},True,folder='OB')
    assert len(calls)==1

def test_article_name_in_ob_is_preserved_without_supplier_only_block():
    state={'supplier_target':'OB','discussion_mode':'supplier'}
    r=engine.dispatch('prepare_draft',engine.Draft(resource='article',mode='new',fields=[engine.DraftValue(field='designation',value='POWER DUR OB  25Kg ECO',evidence='POWER DUR OB  25Kg ECO')]),state,'Merci de créer l\u0027article "POWER DUR OB  25Kg ECO"')
    assert r['ok'] and state['articles'][0]['dossier_cible']=='OB'
    assert state['articles'][0]['designation']=='POWER DUR OB  25Kg ECO'
    assert 'catégorie' in r['message']
