import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import article_sql_dialogue,conversation_tools as engine
from app.core.config import settings
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create


def test_complete_name_is_not_an_implicit_article_code():
    state={'articles':[{'id':'one','designation':'ANT789 X7'}]}
    article_sql_dialogue.enrich(state,'Créer un article ANT789 X7')
    assert not state['articles'][0].get('code_article')
    assert article_sql_dialogue.clean_designation("' ANT789\tX7'")=='ANT789 X7'


def test_new_article_flags_and_suppliers_stay_in_same_draft(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','ANT789 X7'),fact('code_article','ANT789')])),say('Quelle catégorie ?')])
    s=send(c,create(c),'bonjour je veux créer le articles ANT789 X7')
    a=s['state']['articles'][0];identifier=a['id']
    assert a['designation']=='ANT789 X7' and a.get('code_article')!='ANT789'
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('designation','X7'),fact('code_article','ANT789')])),say('Nom conservé.')])
    s=send(c,s,'corriger le nom de le aricles est ANT789 X7')
    assert s['state']['articles'][0]['designation']=='ANT789 X7'
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('designation','ANT789\tX7',"' ANT789\tX7'")])),say('Nom conservé.')])
    s=send(c,s,"la Désignation est ' ANT789\tX7'")
    message='mon articles est géré on sotok et ne outirise pas le stock negatif'
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('gestion_stock','2',message),fact('allow_negative_stock',False,message)])),say('Stock géré, négatif interdit.')])
    s=send(c,s,message)
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('vendu','2','utisble dans la vente')])),say('Vente conservée.')])
    s=send(c,s,'pour le articles et utisble dans la vente')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('flag_fournisseur','2','Flag fournisseur dois active')])),say('Choix conservé ; fournisseurs à préciser.')])
    s=send(c,s,'Flag fournisseur dois active')
    # Even a model choosing the existing-record tool must not switch this
    # uncreated article into an ERP modification operation.
    code=s['state']['articles'][0].get('code_article') or 'ANT789'
    q.extend([native(call('prepare_modification',resource='article',code=code,changes=[{'field':'add_suppliers','value':[{'code':'F007','reference':''},{'code':'F889','reference':''}],'evidence':'F007 ET F889'}])),say('Fournisseurs conservés dans le brouillon.')])
    s=send(c,s,'CIMAT : F007 ET F889 NOVACIM')
    a=s['state']['articles'][0]
    assert a['id']==identifier and a['designation']=='ANT789 X7'
    assert a['gestion_stock']=='2' and a['allow_negative_stock'] is False and a['vendu']=='2'
    assert {supplier['code'] for supplier in a['fournisseurs']}=={'F007','F889'}
    assert not s['state'].get('modification_drafts')
    article_sql_dialogue.enrich({'articles':[a]},'unités à vérifier')
    assert len(a['fournisseurs'])==2 and not a.get('approved')
    assert all(not item['execute'] for item in attempts)
