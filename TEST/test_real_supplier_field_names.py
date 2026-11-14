from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send
from test_conversation_chat import create

def test_french_supplier_modification_fields_are_canonical_and_validated(native_chat):
 c,q,_,_,_,_=native_chat
 q.extend([native(call('prepare_modification',resource='supplier',code='F994',changes=[{'field':'ville','value':'Casablanca','evidence':'ville Casablanca'},{'field':'telephone','value':'0600000000','evidence':'telephone 0600000000'}])),say('La proposition est prête à relire.')])
 s=send(c,create(c),'modifie le fournisseur F994 ville Casablanca et telephone 0600000000')
 d=s['state']['modification_drafts'][-1]
 assert d['changes']=={'city':'Casablanca','phone':'0600000000'} and d['operation']['status']=='prepared'
