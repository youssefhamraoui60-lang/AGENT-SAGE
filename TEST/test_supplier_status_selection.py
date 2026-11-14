import pytest
from app.services.conversation_tools import known_code
from test_supplier_status_chat import native_chat,campaign,fixture,simulated,call,native,say,send
from test_conversation_chat import create
from app.services import erp_modification as service
import copy

def test_exact_selected_name_and_previous_user_code_are_valid_targets():
    state={'supplier_target':'TEST','tool_read_results':[{'ok':True,'folder':'TEST','rows':[{'BPSNUM_0':'F10030','BPRNAM_0':'AHMDE rachid'},{'BPSNUM_0':'F10043','BPRNAM_0':'Ahmde rachide'}]}]}
    assert known_code('F10030','désactiver le AHMDE rachid',state)
    assert not known_code('F10043','désactiver le AHMDE rachid',state)
    assert not known_code('F10030','rachid',state)
    state['tool_user_messages']=['F10030']
    assert known_code('F10030','désactiver ce fournisseur',state)

def test_code_selection_retains_pending_deactivation_without_any_write(native_chat,monkeypatch):
    c,q,_,_,attempts,_=native_chat;original=service.snapshot
    def snapshot(resource,code):
        view=copy.deepcopy(original(resource,code))
        for key in ('partners','suppliers'):view[key][0]['ENAFLG_0']=2
        view['menus']=[{'CODFIC_0':t,'CODZONE_0':'ENAFLG','LANNUM_0':v,'LANMES_0':label} for t in ('BPARTNER','BPSUPPLIER') for v,label in ((1,'Non'),(2,'Oui'))]
        return view
    monkeypatch.setattr(service,'snapshot',snapshot)
    q.extend([native(call('respond',intent='UPDATE_SUPPLIER',text='Quel fournisseur ?'))])
    s=send(c,create(c),'je veux desctiver le fournisseur rachid')
    q.extend([native(call('prepare_modification',resource='supplier',code='F994',changes=[{'field':'enabled','value':False,'evidence':'F994'}])),say('Désactivation préparée ; confirmation nécessaire.')])
    s=send(c,s,'F994')
    assert s['state']['modification_drafts'][-1]['operation']['status']=='prepared'
    assert all(not a['execute'] for a in attempts)
