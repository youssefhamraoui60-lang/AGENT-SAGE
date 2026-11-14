import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import chat_documents,document_fields
from make_document_fixtures import make

def test_bilingual_tax_form_without_colons():
    text='Nom, prénom(s) ou raison   الاسم\nDROGUERIE TEST\nN° d’identification fiscale  01067182 الرقم\nIdentifiant commun de l’entreprise « ICE »  001850814000094 الرقم\nN° du registre de commerce 10909 الرقم\nDomicile fiscal ou siège social المقر\n134 LOT TEST H RDC\nDate de réception 06-02-2026'
    report=document_fields.parse({'pages':[{'page':1,'text':text,'method':'pdf_text','uncertain':False}]},'tax.pdf','test')
    fields={c['field']:c['value'] for c in report['candidates']}
    assert fields=={'nom':'DROGUERIE TEST','identifiant_fiscal':'01067182','ice':'001850814000094','rc':'10909','adresse':'134 LOT TEST H RDC'}
    assert all(c['source']['page']==1 for c in report['candidates'])

def test_email_and_label_on_next_line():
    report=document_fields.parse({'pages':[{'page':2,'text':'ICE :\n001234567890123\nEmail : contact@example.test','method':'pdf_text','uncertain':False}]},'contact.pdf','test')
    assert {c['field']:c['value'] for c in report['candidates']}=={'ice':'001234567890123','email':'contact@example.test'}

def read(name,kind):
    path=make()/name
    raw=chat_documents.decode(path.read_bytes(),kind)
    return raw,document_fields.parse(raw,name,'test-file')

def test_text_pdf_exact_fiscal_values_and_provenance():
    raw,report=read('supplier-text.pdf','pdf')
    fields={c['field']:c for c in report['candidates']}
    assert fields['ice']['value']=='001234567890123' and fields['identifiant_fiscal']['value']=='01067182'
    assert fields['nom']['value']=='DOC LECTURE TEST'
    assert all(c['source']['page']==1 and c['source']['filename']=='supplier-text.pdf' and not c['uncertain'] for c in report['candidates'])

def test_scanned_pdf_uses_real_ocr_and_requires_review():
    raw,report=read('supplier-scan.pdf','pdf')
    fields={c['field']:c for c in report['candidates']}
    assert fields['ice']['value']=='001234567890123' and fields['identifiant_fiscal']['value']=='01067182'
    assert all(c['uncertain'] and c['source']['method']=='windows_ocr' for c in report['candidates'])

def test_poor_photo_never_becomes_a_verified_fact():
    raw,report=read('supplier-poor-photo.jpg','image')
    assert raw['pages'][0]['uncertain']
    assert 'low_resolution' in raw['pages'][0]['warnings']
    assert not report['candidates'] or all(c['uncertain'] for c in report['candidates'])

def test_conflicting_pages_are_retained_separately():
    raw,report=read('supplier-conflicts.pdf','pdf')
    assert [(c['value'],c['source']['page']) for c in report['candidates'] if c['field']=='ville']==[('Rabat',1),('Casablanca',2)]

def test_embedded_instructions_are_not_candidates_or_approvals():
    raw,report=read('supplier-instructions.pdf','pdf')
    assert raw['instructions_executed'] is False and report['warnings']
    assert set(c['field'] for c in report['candidates'])=={'nom','ice'}
