"""1,000 distinct deterministic contract scenarios. Not a Qwen quality benchmark.

Cases vary semantic operations, target positions, cardinalities, fields and failure
modes. SQL and SOAP results are explicitly synthetic. No network or database.
"""
import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.services import conversation_chat as chat, chat_model, chat_tools, chat_turns
from app.services import chat_partners, chat_semantics
from app.schemas.conversation_entities import PartnerPatch
from app.services.sage_gateway import OneShotTransport, RESOURCES
from app.services.sage_soap import parse_xml, SOAP_NS, NS, SOAP_PATH, SageError

DOMAINS={'language':120,'memory':120,'corrections':100,'articles':120,
         'suppliers':100,'customers':100,'references':80,'naming':70,
         'sql_tools':70,'security':70,'workflow':50}


def article_state(count=2):
    return {'articles':[{'id':f'a{i}','designation':f'Panneau {i}', 'code_article':f'PAN-{i}',
                        'categorie':'AR','unite':'UN','site':'201','sources':{},'proposals':{},
                        'fournisseur_nom':'Atlas','code_fournisseur':'F12'} for i in range(1,count+1)],
            'pending':[], 'asked':[]}


LANGUAGE=[('site 202',{'site':'202'}),('le site 209',{'site':'209'}),
 ('Site déclaré 201',{'site':'201'}),('la catigorer NEG',{'categorie':'NEG'}),
 ('la catigorie AR',{'categorie':'AR'}),('catégorie NEG',{'categorie':'NEG'}),
 ('Change le site 201 vers 202',{'site':'202'}),('Remplace le site 201 par 209',{'site':'209'}),
 ('Remplace la catégorie AR par NEG',{'categorie':'NEG'}),('Change la catégorie en NEG',{'categorie':'NEG'}),
 ('unité M2',{'unite':'M2'}),('Remplace unité UN par M2',{'unite':'M2'}),
 ('code article TEST_A',{'code_article':'TEST_A'}),('code fournisseur F42',{'code_fournisseur':'F42'}),
 ('Remplace le fournisseur F12 par F42',{'code_fournisseur':'F42'}),
 ('Peux-tu changer la catégorie en NEG ?',{'categorie':'NEG'}),
 ('Change la catégorie NEG. Le site existe-t-il ?',{'categorie':'NEG'}),
 ('Change le site 201 vers 202 ; quelles catégories existent ?',{'site':'202'}),
 ('fournisseur F99',{'code_fournisseur':'F99'}),('gestion stock 1',{'gestion_stock':'1'})]


def cases():
    output=[]
    for domain,count in DOMAINS.items():
        for number in range(count):
            output.append({'id':f'{domain}-{number+1:03d}','domain':domain,'variant':number})
    return output


CASES=cases()


def run_case(case):
    domain=case['domain'];n=case['variant'];before=article_state(1+n%6)
    if domain=='language':
        before=article_state(1+n//20)
        text,expected=LANGUAGE[n%20]
        value=chat_turns.analyse(text,before)
        case.update(message=text,cardinality=len(before['articles']),expected=expected)
        assert all(value.values.get(k)==v for k,v in expected.items())
        if '?' not in text:assert not value.readonly
        return {'values':value.values,'readonly':value.readonly}
    if domain=='memory':
        count=1+n%10;before=article_state(count);op=n//10
        if op<6:
            field,value=[('categorie','NEG'),('unite','M2'),('site','202'),('code_fournisseur','F42'),
                         ('taux_tva','20'),('accounting_category','Marchandises')][op]
            cue={'categorie':'catégorie','unite':'unité','site':'site','code_fournisseur':'code fournisseur',
                 'taux_tva':'TVA','accounting_category':'catégorie comptable'}[field]
            text=f'{cue} {value}'+(' %' if field=='taux_tva' else '')
            delta=chat_model.Delta(intent='update',shared={field:value})
            after=chat.merge(before,delta,text)
            assert all(a.get(field)==value for a in after['articles'])
            for old,new in zip(before['articles'],after['articles']):
                for other in ('designation','categorie','unite','site','code_fournisseur'):
                    if other!=field:assert new.get(other)==old.get(other)
        else:
            text=['Le site est-il 202 ?','Vérifie le fournisseur F42','Est-ce possible sans fournisseur ?',
                  'Quels sont les codes articles ?','Vérifie la catégorie NEG','Et pour le site ?'][op-6]
            after=chat.merge(before,chat_model.Delta(intent='lookup',shared={'site':'202','categorie':'NEG'}),text)
            assert after['articles']==before['articles']
        assert before==article_state(count)
        case.update(message=text,cardinality=count,expected='only_declared_fields_change_or_question_is_readonly')
        return {'articles':after['articles']}
    if domain=='corrections':
        before=article_state(5);index=1+n%5;op=n//5
        field,value,cue=[('site','202','site'),('categorie','NEG','catégorie'),('unite','M2','unité'),
                         ('code_fournisseur','F42','code fournisseur'),('code_article','TEST_X','code article')][op%5]
        ordinal=['premier','deuxième','troisième','quatrième','cinquième'][index-1]
        text=[f'Pour le {ordinal} article : {cue} {value}.',
              f'Article {index} : {cue} {value}.',
              f'Corrige le {ordinal} article : {cue} {value}.',
              f'Pour article {index}, {cue} {value}.'][op//5]
        after=chat.merge(before,chat_model.Delta(intent='update',targets=[index],shared={field:value}),text)
        assert after['articles'][index-1][field]==value
        for i in range(5):
            if i!=index-1:
                assert all(after['articles'][i].get(k)==before['articles'][i].get(k) for k in chat.FIELDS)
        case.update(message=text,target=index,expected={field:value})
        return {'selected':after['articles'][index-1]}
    if domain=='articles':
        count=1+n%10;variant=n//10
        category,unit,site=[('NEG','UN','201'),('AR','M2','202'),('NEG','SAC','209')][variant%3]
        names=[f'Produit {i} série {variant}' for i in range(1,count+1)]
        text='Créer les '+str(count)+' articles : '+' ; '.join(names)+f', catégorie {category}, unité {unit}, site {site}.'
        patches=[{'designation':name} for name in names]
        shared={'categorie':category,'unite':unit,'site':site}
        if variant//3==1:shared['code_fournisseur']='F42';text+=' Code fournisseur F42.'
        if variant//3==2:text+=' Sans fournisseur.'
        if variant//3==3:
            shared['unite_achat']=unit;shared['unite_vente']=unit
        after=chat.merge({'articles':[]},chat_model.Delta(intent='new',shared=shared,articles=patches),text)
        assert [a['designation'] for a in after['articles']]==names
        assert len({a['id'] for a in after['articles']})==count
        assert all(a['categorie']==category and a['unite']==unit and a['site']==site for a in after['articles'])
        assert all(not a.get('approved') and not a.get('outcome') for a in after['articles'])
        if variant//3==2:assert all(a['supplier_intent']=='none' for a in after['articles'])
        case.update(message=text,expected={'count':count,'category':category,'unit':unit,'site':site})
        return {'count':len(after['articles']),'codes':[a['code_article'] for a in after['articles']]}
    if domain in ('suppliers','customers'):
        collection='fournisseurs' if domain=='suppliers' else 'clients'
        kind='supplier' if domain=='suppliers' else 'customer'
        word='fournisseur' if kind=='supplier' else 'client';op=n//10;size=1+n%10
        names=[f'Société {kind} {i}' for i in range(1,size+1)]
        text=f'Créer les {word}s : '+' et '.join(names)
        before={'articles':[]}
        delta=chat_model.Delta(intent='new',**{collection:[{'nom':x} for x in names]})
        state=chat.merge(before,delta,text)
        assert len(state['partners'])==size and not state['articles']
        field,value,cue=[('email','contact@example.test','email'),('devise','MAD','devise'),('pays','MA','pays'),
          ('adresse','12 rue Atlas','adresse'),('telephone','0123456789','téléphone'),
          ('identifiant_fiscal','IF123','identifiant fiscal'),('conditions_paiement','30 jours','conditions de paiement'),
          ('site','202','site'),('societe','20','société'),('code','TIER123','code')][op]
        index=size
        correction=f'Pour le {word} {index} : {cue} {value}.'
        after=chat.merge(state,chat_model.Delta(intent='update',**{collection:[{'index':index,field:value}]}),correction)
        assert len(after['partners'])==size and after['partners'][index-1][field]==value
        assert all(p.get(field) is None for p in after['partners'][:index-1])
        assert all(p['kind']==kind for p in after['partners'])
        case.update(messages=[text,correction],target=index,expected={field:value,'count':size})
        return {'partners':after['partners']}
    if domain=='references':
        before=article_state(1);a=before['articles'][0];mode=n//10;fixture=n%10
        refs={k:{'ok':True,'rows':[]} for k in ('duplicate','recent','article_site')}
        refs.update(category={'ok':True,'rows':[{'TCLCOD_0':'AR'}]},units={'ok':True,'rows':[{'UOM_0':'UN'}]},
                    site={'ok':True,'rows':[{'FCY_0':'201'}]},supplier={'ok':True,'rows':[{'BPSNUM_0':'F12','BPRNAM_0':'Atlas'}]})
        expected=None
        if mode==0:a['site']=None;expected='missing:site'
        if mode==1:refs['category']['rows']=[];expected='unknown:categorie'
        if mode==2:refs['units']['rows']=[];expected='unknown:unite'
        if mode==3:refs['site']['rows']=[];expected='unknown:site'
        if mode==4:refs['supplier']['rows']=[];expected='supplier_code_not_verified'
        if mode==5:refs['duplicate']['rows']=[{'ITMREF_0':a['code_article']}];expected='duplicate_article_code'
        if mode==6:refs['category']['ok']=False;expected='sql_checks_incomplete'
        if mode==7:refs['supplier']['rows']=[{'BPSNUM_0':'F12','BPRNAM_0':'Autre société'}];expected='supplier_name_code_mismatch'
        # Different declared stock/purchase/sales contexts affect the same reference invariant.
        a['unite_achat']=('UN','M2','SAC','KG','L')[fixture//2]
        if fixture%2:a['unite_vente']='UN'
        a['gestion_stock']=str(1+fixture%3)
        result=chat.validate_article_draft(a,refs)
        assert expected in result['errors'] and not result['valid_basic'] and not result['sage_created']
        case.update(article=a,reference_fixture=refs,expected_error=expected)
        return result
    if domain=='naming':
        size=1+n%10;mode=n//10;state=article_state(size)
        for a in state['articles']:a['code_article']='PAN-'+a['id'][1:]
        text=['Remplacer - par _ dans les codes articles.', 'Commencer les codes avec la catégorie.',
              'Commencer les codes avec la catégorie et remplacer - par _.',
              'Remplacer _ par - dans les codes articles.',
              'Remplacer - par _ pour le premier article.',
              'Commencer le code avec la catégorie pour le premier article.',
              'Remplacer - par _ pour article '+str(size)+'.'][mode]
        result=chat.merge(state,chat_model.Delta(intent='generate'),text)
        for i,a in enumerate(result['articles'],1):
            selected=mode<4 or (mode in (4,5) and i==1) or (mode==6 and i==size)
            expected=state['articles'][i-1]['code_article']
            if selected:
                if mode in (0,2,4,6):expected=expected.replace('-','_')
                if mode in (1,2,5):expected='AR_'+expected
            assert a['code_article']==expected
        assert not result['naming_convention']['global']
        case.update(message=text,cardinality=size,expected_scope='conversation_or_explicit_target')
        return {'codes':[a['code_article'] for a in result['articles']]}
    if domain=='sql_tools':
        mode=n//10;size=1+n%10;state=article_state(size)
        if mode==0:
            for a in state['articles']:a['site']='202'
        if mode==1:
            for a in state['articles']:a['categorie']='NEG'
        if mode==2:
            for a in state['articles']:a['unite_achat']='M2'
        if mode==3:
            for a in state['articles']:a['unite_vente']='M2'
        if mode==4:
            for a in state['articles']:a['code_fournisseur']=None;a['fournisseur_nom']=None
        if mode==5:
            for a in state['articles']:a['taux_tva']='20'
        if mode==6:
            for a in state['articles']:a['accounting_category']='Marchandises'
        plan,bindings=chat.tool_plan(state)
        assert len(bindings)==size and all(c['tool'] in chat_tools.TOOLS for c in plan.calls)
        assert len({chat_tools.key(c['tool'],c['args']) for c in plan.calls})==len(plan.calls)
        if mode==4:assert not any(c['tool']=='search_suppliers' for c in plan.calls)
        if mode==2:assert any(c['tool']=='get_unit_conversions' for c in plan.calls)
        if mode==5:assert any(c['tool']=='get_tax_rules' for c in plan.calls)
        case.update(state=state,expected='bounded_deduplicated_predefined_read_tools')
        return {'calls':plan.calls}
    if domain=='security':
        mode=n//10;size=1+n%10
        if mode==0:
            with pytest.raises(ValidationError):chat_model.Delta(intent='new',**{f'unsafe_{size}':'SAVE'})
        elif mode==1:
            with pytest.raises(ValidationError):PartnerPatch(index=size,**{'password':'secret'})
        elif mode==2:
            with pytest.raises(ValueError):chat_tools._run([{'id':'x','tool':f'execute_sql_{size}','args':{}}])
        elif mode==3:
            with pytest.raises(ValueError):chat_tools._run([{'id':'x','tool':'get_sites','args':{'Site':'a'*(100+size)}}])
        elif mode==4:
            with pytest.raises(SageError):parse_xml('<!DOCTYPE x [<!ENTITY a "bad">]><x>'+str(size)+'</x>')
        elif mode==5:
            state=article_state(size);after=chat.merge(state,chat_model.Delta(intent='approve'),'oui')
            assert all(not a.get('approved') and not a.get('operation') for a in after['articles'])
        elif mode==6:
            state=article_state(size);after=chat.merge(state,chat_model.Delta(intent='update',shared={'site':'999'}),'Le site est-il 999 ?')
            assert state['articles']==after['articles']
        case.update(mode=mode,size=size,expected='forbidden_effect_refused')
        return {'protected':True}
    if domain=='workflow':
        # Exercise the actual one-shot transport with a simulated bounded sender.
        from lxml import etree
        mode=n//10;variant=n%10;base='https://offline.test';xml=f'<PARAM><FLD>{variant}</FLD></PARAM>'
        import hashlib
        expected={'method':'save','publication':'WS_ARTICLE','pool':'POOL_AI_TEST',
                  'xml_hash':hashlib.sha256(xml.encode()).hexdigest(),'keys':{'ITMREF':f'TEST{variant}'}}
        env=etree.Element('{'+SOAP_NS+'}Envelope');body=etree.SubElement(env,'{'+SOAP_NS+'}Body')
        node=etree.SubElement(body,'{'+NS+'}save');context=etree.SubElement(node,'callContext')
        etree.SubElement(context,'poolAlias').text='POOL_AI_TEST'
        etree.SubElement(node,'publicName').text='WS_ARTICLE';etree.SubElement(node,'objectXml').text=xml
        transport=OneShotTransport(base,expected);sent=[]
        transport._bounded=lambda *a,**k:sent.append(a) or {'simulated':True}
        if mode==0:
            assert transport.post_xml(base+SOAP_PATH,env,{})=={'simulated':True}
            with pytest.raises(SageError):transport.post_xml(base+SOAP_PATH,env,{})
            assert len(sent)==1
        else:
            if mode==1:node.find('publicName').text='UNAPPROVED'
            if mode==2:context.find('poolAlias').text='PRODUCTION'
            if mode==3:node.find('objectXml').text=xml+' '
            address=base+SOAP_PATH if mode!=4 else 'https://unapproved.test'+SOAP_PATH
            with pytest.raises(SageError):transport.post_xml(address,env,{})
            assert not sent
        case.update(mode=mode,variant=variant,expected='single_simulated_send_or_fail_closed')
        return {'simulated_sends':len(sent),'real_sends':0}
    raise AssertionError(domain)


@pytest.mark.parametrize('case',CASES,ids=[c['id'] for c in CASES])
def test_contract_scenario(case,request):
    try:
        actual=run_case(case)
        request.node.user_properties.append(('actual',json.dumps(actual,ensure_ascii=False,default=str)))
    finally:
        request.node.user_properties.append(('scenario',json.dumps(case,ensure_ascii=False,default=str)))
