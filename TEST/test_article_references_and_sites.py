import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import article_references,article_sites,article_fact_resolution
from app.core.config import settings
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact
from test_conversation_chat import create


def test_tax_levels_are_not_confused_with_tax_codes_and_rates():
    schema={'tax_levels':[{'VACITM_0':'LEVEL20'}],'taxes':[{'VAT_0':'VAT20','VATRAT_0':20}],
            'tax_determinations':[{'VACITM_0':'LEVEL20','VAT_0':'VAT20','VACBPR_0':'MAR','ENAFLG_0':2}]}
    choices=article_references.taxes(schema,20)
    assert choices[0]['code']=='LEVEL20' and choices[0]['tax_code']=='VAT20'
    assert choices[0]['rate']=='20'
    state={'article_reference_choices':{'tax':{'ok':True,'folder':'TEST','rate':20,'choices':choices}}}
    assert article_fact_resolution.resolve('code_tva','LEVEL20','TVA 20',state,{'taux_tva':'20'},None)['source']=='verified_tax_rate_reference'
    state['article_reference_choices']['tax']['folder']='OB'
    assert article_fact_resolution.resolve('code_tva','LEVEL20','TVA 20',state,{'taux_tva':'20'},None) is None


def test_accounting_search_returns_real_labels_and_mapped_accounts():
    schema={'accounting':[{'ACCCOD_0':'SAC_VIDE','DES_0':'Sac Vide','COA_0':'MAR','ACC_0':'61224000','ACC_1':'71100000'},
                          {'ACCCOD_0':'23310000','DES_0':'Installations techniques','COA_0':'MAR','ACC_0':'23310000'}]}
    assert article_references.accounting(schema,'6122')[0]['code']=='SAC_VIDE'
    assert article_references.accounting(schema,'installations')[0]['code']=='23310000'
    assert article_references.accounting(schema,'4415')==[]


def test_site_addition_and_both_are_scoped_to_the_draft():
    article={'site':'202','requested_sites':['202']};values={'site':'201'}
    article_sites.merge(article,values,'ajouter aussi dans le site 201');article.update(values)
    assert article['requested_sites']==['202','201']
    values={'site':'201'};article_sites.merge(article,values,'LES DEUX site')
    assert values['requested_sites']==['202','201']


def test_full_article_sequence_lists_references_and_retains_sites(native_chat,monkeypatch):
    from app.services import article_sql
    schema=json.loads((ROOT/'TEST/fixtures/article-sql-schema.json').read_text())
    category=copy.deepcopy(schema['categories'][0]);category.update(TCLCOD_0='GEN',TCLDES_0='Frais généraux',STOFCY_0='',ACCCOD_0='STD')
    schema['categories']=[row for row in schema['categories'] if row['TCLCOD_0'].strip()!='GEN']+[category]
    schema.update(tax_levels=[{'VACITM_0':'T20'}],taxes=[{'VAT_0':'T20','VATRAT_0':20}],tax_determinations=[{'VACITM_0':'T20','VAT_0':'T20','VACBPR_0':'MAR','ENAFLG_0':2}])
    monkeypatch.setattr(article_sql,'catalog',lambda *a,**kw:copy.deepcopy(schema))
    monkeypatch.setattr(settings,'conversation_deepseek_primary_enabled',True)
    c,q,requests,reads,attempts,fault=native_chat
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','CAF Y78 9X')])),say('Quelle catégorie ?')])
    s=send(c,create(c),'bonjour je veyux créer un article le nom est CAF Y78 9X');identifier=s['state']['articles'][0]['id']
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('categorie','GEN')])),say('Quels sites ?')])
    s=send(c,s,'la catigoirer est GEN')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('site','202'),fact('unite_vente','UN')])),say('Données conservées.')])
    s=send(c,s,'le site 202 LE UNIT2 de vente est UN')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('taux_tva','20')])),
              native(call('read_article_references',kind='tax',rate=20)),
              native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('code_tva','T20','TVA est 20')])),say('Niveau T20 retrouvé à 20 %.')])
    s=send(c,s,'le TVA est 20')
    assert s['state']['articles'][0]['code_tva']=='T20'
    q.extend([native(call('read_article_references',kind='accounting')),say('Voici les codes comptables disponibles.')])
    s=send(c,s,'je sais pas code donne la liste')
    assert s['state']['article_reference_choices']['accounting']['choices']
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('compte_general','4415')])),say('Compte à préciser.')])
    s=send(c,s,'et le compte comptables est 4415')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('unite','UN')])),say('Unité conservée.')])
    s=send(c,s,'le unter de sotok est UN')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('site','201')])),say('Les deux sites sont conservés.')])
    s=send(c,s,'ajouter aussi dans le site 201')
    q.extend([native(call('prepare_draft',resource='article',mode='update',target_id=identifier,fields=[fact('requested_sites',['202','201'],'LES DEUX site')])),say('202 et 201 restent conservés.')])
    s=send(c,s,'LES DEUX site')
    a=s['state']['articles'][0]
    assert a['id']==identifier and a['requested_sites']==['202','201']
    assert a['unite']=='UN' and a['unite_vente']=='UN' and a['code_tva']=='T20'
    assert a['compte_general']=='4415' and not a.get('approved')
    assert all(not item['execute'] for item in attempts)
