import copy
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send
from test_conversation_chat import create
from app.services import erp_modification as service

def test_two_status_proposals_are_independent_and_require_confirmation(native_chat,monkeypatch):
    c,q,_,_,attempts,_=native_chat
    original=service.snapshot
    def snapshot(resource,code):
        view=copy.deepcopy(original(resource,code))
        for key in ('partners','suppliers'):view[key][0]['ENAFLG_0']=2
        view['menus']=[{'CODFIC_0':t,'CODZONE_0':'ENAFLG','LANNUM_0':v,'LANMES_0':label} for t in ('BPARTNER','BPSUPPLIER') for v,label in ((1,'Non'),(2,'Oui'))]
        return view
    monkeypatch.setattr(service,'snapshot',snapshot)
    q.extend([native(*[call('prepare_modification',resource='supplier',code=code,changes=[{'field':'enabled','value':False,'evidence':'désactiver les fournisseurs F994 et F995'}]) for code in ('F994','F995')]),say('Deux désactivations préparées, confirmation individuelle nécessaire.')])
    s=send(c,create(c),'désactiver les fournisseurs F994 et F995')
    drafts=s['state']['modification_drafts']
    assert len(drafts)==2 and {d['code'] for d in drafts}=={'F994','F995'}
    assert all(d['operation']['status']=='prepared' and d['operation']['plan']['policy']['sensitive'] for d in drafts)
    assert set(s['state']['supplier_status_batch']['codes'])=={'F994','F995'}
    for d in drafts:
        response=c.post(f"/api/v1/chat/conversations/{s['id']}/modifications/{d['id']}/approve",json={'revision':s['revision'],'confirm':False,'sensitive_confirm':False})
        assert response.status_code==403
    assert all(not a['execute'] for a in attempts)
