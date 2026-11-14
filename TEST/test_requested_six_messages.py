from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create
from app.core.config import settings


def test_dimension_asterisks_are_business_data():
    from app.services.article_sql_dialogue import clean_text
    assert clean_text('DRENTEX 400 * 3M*2M')=='DRENTEX 400 * 3M*2M'
    assert clean_text('**DRENTEX 400 * 3M*2M**')=='DRENTEX 400 * 3M*2M'


def test_six_reported_messages_keep_all_records_and_scopes(native_chat,monkeypatch):
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    names=['Polo','Casquette','Gilet','Blouse','T-shirt','Ensemble veste et pantalon']
    text='Merci de créer les articles suivants : '+' '.join(name+'/U/FG/MIDO PUB MAROC S.A.R.L' for name in names)
    drafts=[{'resource':'article','mode':'new','fields':[fact('designation',name),fact('unite','UN','U'),fact('categorie','FG'),fact('fournisseur_nom','MIDO PUB MAROC S.A.R.L')]} for name in names]
    q.extend([native(call('prepare_drafts',drafts=drafts)),say('Les six brouillons sont conservés ; catégorie FG à vérifier.')])
    s=send(c,create(c),text)
    assert [a['designation'] for a in s['state']['articles']]==names
    identifiers=[a['id'] for a in s['state']['articles']]
    assert all(a['categorie']=='FG' and a['unite']=='UN' for a in s['state']['articles'])
    assert not s['state'].get('category_drafts')
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','DRENTEX 400 * 3M*2M'),fact('unite','RLX'),fact('categorie','AR'),fact('fournisseur_nom','SOPREMA')])),say('Brouillon DRENTEX conservé.')])
    s=send(c,s,'Bonsoir Merci de créer cet article : DRENTEX 400 * 3M*2M/ RLX / AR/ SOPREMA')
    message='Bonsoir, Merci de bien vouloir modifier toutes les unités des articles Technoseal en Rlx.'
    q.extend([native(call('request_article_unit_batch',query='Technoseal',unit='RLX',unit_scope='unspecified',evidence=message)),say('La demande Technoseal est conservée ; quelles unités : stock, achat ou vente ?')])
    s=send(c,s,message)
    batch=s['state']['batch_modification_requests'][0]
    assert batch['query']=='Technoseal' and batch['unit']=='RLX' and batch['unit_scope']=='unspecified'
    assert [a['id'] for a in s['state']['articles'][:6]]==identifiers
    assert all(a['unite']=='UN' for a in s['state']['articles'][:6])
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','POLYSTYRENE 60*60*25'),fact('unite','UN','UNITE'),fact('categorie','AR'),fact('fournisseur_nom','ISONIMA')])),say('Brouillon polystyrène conservé.')])
    s=send(c,s,'MERCI DE CREER CET ARTICLE : POLYSTYRENE 60*60*25/ UNITE/ AR / fournisseur : ISONIMA')
    q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','DELTA BUREAU'),fact('ice','000102081000068'),fact('identifiant_fiscal','01007203'),fact('telephone','05 22 09 00 01')])),say('Fournisseur conservé pour vérification.')])
    s=send(c,s,'Merci de créer le fournisseur suivant : DELTA BUREAU ICE : 000102081000068 IF : 01007203 TEL : 05 22 09 00 01')
    p=s['state']['partners'][0]
    assert p['nom']=='DELTA BUREAU' and p['identifiant_fiscal']=='01007203' and p['telephone']=='05 22 09 00 01'
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','TELEPHONE PORTABLE'),fact('fournisseur_nom','ALLO FOURNI'),fact('unite','UN','UNITE')])),say('Brouillon téléphone conservé. Quelle catégorie retenir ?')])
    s=send(c,s,'BONJOUR MERCI DE CREER CET ARTICLE : TELEPHONE PORTABLE / ALLO FOURNI/ UNITE')
    assert len(s['state']['articles'])==9
    last=s['state']['articles'][-1]
    assert last['designation']=='TELEPHONE PORTABLE' and last['fournisseur_nom']=='ALLO FOURNI'
    assert not last.get('categorie')
    assert not s['messages'][-1]['payload'].get('supplier_snapshots')
    assert any(op['parameters'].get('query')=='Technoseal' for op in s['state']['operation_context']['operations'])
    assert all(not item.get('approved') for key in ('articles','partners') for item in s['state'][key])
    assert all(not attempt['execute'] for attempt in attempts)
