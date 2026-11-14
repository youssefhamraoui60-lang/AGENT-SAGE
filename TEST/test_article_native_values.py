import pytest
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create

@pytest.mark.parametrize('yes,no',[(True,False),('oui','non'),('Article acheté et vendu','Non géré en stock'),('2','1')])
@pytest.mark.parametrize('whole',[False,True])
def test_article_site_flags_tax_and_unknown_code_survive_native_extraction(native_chat,yes,no,whole):
    c,q,_,_,attempts,_=native_chat
    text='Merci de créer les articles pour le site 202 : GANTS DE PROTECTION TEST. Catégorie : AVNS. Unité : UN. Article acheté et vendu. Non géré en stock. Fournisseur : F007. TVA : 20 %'
    fields=[fact('designation','GANTS DE PROTECTION TEST'),fact('categorie','AVNS','Catégorie : AVNS'),fact('unite','UN','Unité : UN'),fact('site','202','site 202'),fact('achete',yes,'Article acheté et vendu'),fact('vendu',yes,'Article acheté et vendu'),fact('gestion_stock',no,'Non géré en stock'),fact('fournisseur_principal','F007','Fournisseur : F007'),fact('taux_tva',20,'TVA : 20 %')]
    if whole and type(yes) in (bool,) or whole and yes=='2':
        for f in fields:
            if f['field'] in ('achete','vendu','gestion_stock'):f['evidence']=text
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=fields,unknowns=['code_article'])),say('Informations conservées pour vérification.')])
    s=send(c,create(c),text)
    errors=[e['result'] for e in s['state']['tool_orchestration']['calls'] if not e['result'].get('ok')]
    assert not errors,errors
    a=s['state']['articles'][0]
    assert a['designation']=='GANTS DE PROTECTION TEST' and a['categorie']=='AVNS' and a['unite']=='UN'
    assert a['site']=='202' and a['achete']==a['vendu']=='2' and a['gestion_stock']=='1' and a['taux_tva']=='20'
    assert a['fournisseur_principal']=='F007'
    assert all(not r['execute'] for r in attempts)
