"""Prepare only. No network save, no write transport, no approval/execution option."""
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.sage_soap import SageReader,parse_xml,SOAP_NS,NS
from app.services.sage_creation_preflight import build_object_xml

def main():
    reader=SageReader();description=reader._invoke('getDescription')
    code=json.loads((ROOT/'runtime/step4-candidate-code.json').read_text())['reference']
    designation='TEST IA SOAP '+code[-6:]+' - NE PAS UTILISER'
    object_xml,fields=build_object_xml(description,code,designation)
    session,service=reader._client()
    try:
        assert 'save' in service._binding._operations
        context={'codeLang':'FRA','poolAlias':'POOL_AI_TEST','poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'}
        # Serialization only; create_message does not invoke the SOAP transport.
        envelope=service._client.create_message(service,'save',callContext=context,publicName='WS_ARTICLE',objectXml=object_xml)
        with service._client.settings(raw_response=True):
            response=service.read(callContext=context,publicName='WS_ARTICLE',objectKeys=[{'key':'ITMREF','value':code}])
        assert response.status_code==200,'Existence check HTTP failure'
        body=parse_xml(response.content).find('{'+SOAP_NS+'}Body')
        reply=body.find('{'+NS+'}readResponse') if body is not None else None
        assert reply is not None,'Unexpected existence response'
        values={etree.QName(node).localname:node.text for node in reply.iter()}
        messages=[node.text or '' for node in reply.iter() if etree.QName(node).localname=='message']
        # Only this explicit not-found response proves absence; generic failures never do.
        assert values.get('status')=='0' and any(message.strip()=='Fiche inexistante' for message in messages),'Absence not established; stop'
        assert not values.get('resultXml'),'Unexpected object returned; stop'
    finally: session.close()
    folder=ROOT/'examples/step4';folder.mkdir(exist_ok=True)
    (folder/'article-object.xml').write_text(object_xml,encoding='utf-8')
    serialized=etree.tostring(envelope,encoding='utf-8',xml_declaration=True,pretty_print=True)
    (folder/'save-request-NOT-SENT.xml').write_bytes(serialized)
    proof={'status':'PREPARED_NOT_APPROVED','prepared_utc':datetime.now(timezone.utc).isoformat(),
        'target':{'base_url':reader.config.sage_soap_base_url,'solution':description.get('SOL'),'folder':description.get('FOL'),'pool':'POOL_AI_TEST','publication':'WS_ARTICLE','object':'ITM'},
        'reference':code,'designation':designation,'fields':fields,'code_absence':{'status':'CONFIRMED_AT_CHECK_TIME','soap_status':0,'message':'Fiche inexistante'},
        'save_available_in_wsdl':True,'create_declared_by_publication':True,'authenticated_reads_succeeded':True,
        'effective_create_authorization_verified':False,'all_conditional_mandatory_fields_verified':False,
        'category_manual_reference_rule_verified':False,'reference_values_evidence':'step4-observed-values.json: two existing DIVE articles, not CPJ35',
        'object_xml_sha256':hashlib.sha256(object_xml.encode()).hexdigest(),'envelope_sha256':hashlib.sha256(serialized).hexdigest(),
        'human_confirmation':None,'save_sent':False,'article_created':False,
        'pending':['Confirm DIVE permits a manual reference and all conditional mandatory fields','Verify effective create rights or explicitly record them as unverified','Explicit human approval for this exact payload before any save']}
    (ROOT/'logs/step4-preparation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':proof['status'],'reference':code,'folder':'TEST','code_absent':True,'fields_checked_against_publication':len(fields),'save_sent':False},ensure_ascii=False))

if __name__=='__main__':main()
