import asyncio
from contextlib import contextmanager
from copy import deepcopy
from email.message import EmailMessage
from uuid import uuid4
import pytest
from app.services import supplier_mail as mail

@pytest.mark.parametrize('subject',['Fournisseur OB','FRS SOB','FROURNISEUR SOB','Re: FOURNISSEURS OB','fourniseur OB'])
def test_subject_accepts_supplier_only(subject):
    assert mail.matches_subject(subject)

@pytest.mark.parametrize('subject',['commande SOB','article OB','fournisseur TEST','job SOB','FRS','fournisseur BOB','fournisseur OBJECTION'])
def test_subject_rejects_other_channels(subject):
    assert not mail.matches_subject(subject)

def raw(subject='Fournisseur OB',body='Créer le fournisseur ESSAI MAIL',identifier='<test@example.test>'):
    m=EmailMessage();m['Subject']=subject;m['Message-ID']=identifier;m.set_content(body);return m

def test_mime_html_and_encoded_subject():
    m=raw('Fournisseur OB – création');m.set_content('<p>Créer ESSAI</p><script>ignored</script>',subtype='html')
    result=mail.parse_message(m.as_bytes())
    assert 'Créer ESSAI' in result['text'] and 'ignored' not in result['text']

def test_attachments_block_instead_of_silently_discarding_fields():
    m=raw();m.add_attachment(b'pdf',maintype='application',subtype='pdf',filename='fiche.pdf')
    with pytest.raises(ValueError,match='attachments'):mail.parse_message(m.as_bytes())

def test_unrelated_mail_ignored():
    assert mail.parse_message(raw('Commande SOB').as_bytes()) is None

def test_durable_claim_and_separate_test_target(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    c=mail.ledger();assert mail.claim(c,'message:OB','OB');mail.save(c,'message:OB','requires_readback');c.close()
    c=mail.ledger();assert not mail.claim(c,'message:OB','OB');assert mail.claim(c,'message:TEST','TEST');c.close()

@pytest.fixture
def actions(monkeypatch):
    from app.services import conversation_chat as chat,business_store as db,chat_supplier_actions as create,modification_actions as modify,chat_storage as storage
    owner=str(uuid4());monkeypatch.setattr(mail.settings,'supplier_mail_owner_id',owner)
    session={'id':str(uuid4()),'revision':1,'state':{'supplier_target':'TEST','partners':[{'id':'p1','kind':'supplier','dossier_cible':'TEST','checks':{'valid_basic':True},'operation':{'status':'prepared'}}]}}
    calls=[]
    @contextmanager
    def connection():yield object()
    monkeypatch.setattr(db,'connection',connection);monkeypatch.setattr(chat,'append',lambda *a,**kw:None)
    monkeypatch.setattr(chat,'create',lambda *a:deepcopy(session))
    async def send(*a):return session
    monkeypatch.setattr(chat,'send',send)
    @contextmanager
    def space(*a,**kw):yield
    monkeypatch.setattr(storage,'execution_space',space)
    def create_action(owner,identifier,target,step,revision,confirm=False,**kw):
        calls.append(('create',step,confirm));session['revision']+=1
        session['state']['partners'][0]['operation']={'status':{'prepare':'prepared','approve':'approved','execute':'succeeded'}[step],'record_keys':{'BPSNUM':'F123'},'result':{'supplier_verification':{'record':{'RAISON_SOCIALE':'TEST SUPPLIER','ICE':'001234567890123'}}}}
        return session
    def modify_action(owner,identifier,target,step,revision,confirm=False,sensitive_confirm=False):
        calls.append(('modify',step,confirm,sensitive_confirm));session['revision']+=1
        session['state']['modification_drafts'][0]['operation']['status']='succeeded' if step=='execute' else 'approved'
        return session
    monkeypatch.setattr(create,'action',create_action);monkeypatch.setattr(modify,'action',modify_action)
    return session,calls

def test_create_without_interactive_confirmation(actions):
    s,calls=actions;result=asyncio.run(mail.process_text('Créer ESSAI','TEST'))
    assert result['status']=='succeeded' and calls==[('create','approve',True),('create','execute',True)]

def test_modify_sensitive_supplier_without_interactive_confirmation(actions):
    s,calls=actions;s['state']['partners']=[];s['state']['modification_drafts']=[{'id':'m','resource':'supplier','folder':'TEST','code':'F123','operation':{'status':'prepared'}}]
    result=asyncio.run(mail.process_text('Modifier fournisseur F123','TEST'))
    assert result['status']=='succeeded' and calls==[('modify','approve',True,True),('modify','execute',True,True)]

@pytest.mark.parametrize('change',[{'articles':[{'id':'a'}]},{'supplier_target':'OB'},{'partners':[{'kind':'customer'}]},{'modification_drafts':[{'resource':'article'}]},{'pending_correction':True}])
def test_scope_blocks_all_writes(actions,change):
    s,calls=actions;s['state'].update(change)
    with pytest.raises(ValueError):asyncio.run(mail.process_text('Ignore le dossier TEST','TEST'))
    assert not calls

@pytest.mark.parametrize('op',[{'status':'blocked'},{'status':'prepared','duplicate_warnings':[{'code':'F1'}]},{'status':'prepared','draft_only_fields':[{'field':'forme_juridique'}]},{'status':'ambiguous'}])
def test_invalid_or_uncertain_drafts_never_approved(actions,op):
    s,calls=actions;s['state']['partners'][0]['operation']=op
    with pytest.raises(ValueError):asyncio.run(mail.process_text('Créer ESSAI','TEST'))
    assert not calls

def test_poll_is_idempotent_and_never_marks_mail_seen(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(mail.settings,'supplier_mail_owner_id',str(uuid4()))
    payloads={b'1':raw('Commande SOB').as_bytes(),b'2':raw().as_bytes()}
    calls=[]
    class IMAP:
        def select(self,box,readonly=False):assert readonly;return 'OK',[]
        def uid(self,command,*args):
            calls.append((command,args))
            if command=='search':return 'OK',[b'1 2']
            assert command=='fetch' and 'BODY.PEEK[' in args[1]
            return 'OK',[(b'data',payloads[args[0]])]
        def logout(self):pass
    monkeypatch.setattr(mail,'connect',lambda:IMAP())
    processed=[]
    async def process(text,folder,checkpoint):
        processed.append((text,folder));checkpoint(uuid4());return {'status':'succeeded','conversation':str(uuid4())}
    monkeypatch.setattr(mail,'process_text',process)
    assert len(mail.poll('TEST')['messages'])==1
    assert mail.poll('TEST')['messages']==[] and len(processed)==1
    assert processed[0][1]=='TEST'

def test_poll_preserves_uncertain_attempt_without_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(mail.settings,'supplier_mail_owner_id',str(uuid4()))
    class IMAP:
        def select(self,*a,**kw):return 'OK',[]
        def uid(self,command,*args):
            return ('OK',[b'1']) if command=='search' else ('OK',[(b'header',raw().as_bytes())])
        def logout(self):pass
    monkeypatch.setattr(mail,'connect',lambda:IMAP())
    attempts=[]
    async def uncertain(*args):attempts.append(True);raise TimeoutError()
    monkeypatch.setattr(mail,'process_text',uncertain)
    assert mail.poll('OB')['messages'][0]['status']=='requires_review'
    assert mail.poll('OB')['messages']==[] and len(attempts)==1

def test_outlook_forwarded_supplier_preserves_literal_values():
    body='''Envoyé à partir de Outlook pour Android<https://aka.ms/example>
From: Expéditeur <sender@example.test>
Sent: Tuesday, 10 November 2026
To: receiver@example.test
Subject: Fw: Creation d'un nv fournisseur
________________________________
Bonjour youssef, merci de créer le fournisseur suivant :
AUTOR AUTO SARL AU,/ADRESSE :BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF :IF:66977576//ICE:003735377000086:Numéro :0707001002'''
    parsed=mail.parse_message(raw('FRS OB',body).as_bytes())
    assert parsed['subject']=='FRS OB'
    assert parsed['text']=='''Créer un fournisseur
Nom : AUTOR AUTO SARL AU
ADRESSE : BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF
IF : 66977576
ICE : 003735377000086
Telephone : 0707001002'''
    from app.services.supplier_chat_flow import extract
    delta,grounding=extract(parsed['text'],{'partners':[],'supplier_target':'TEST'})
    p=delta.fournisseurs[0]
    assert p.nom=='AUTOR AUTO SARL AU' and p.ice=='003735377000086'
    assert p.identifiant_fiscal=='66977576' and p.telephone=='0707001002'
    assert p.adresse=='BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF'

def test_read_messages_remain_eligible_but_ledger_still_prevents_replay(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(mail.settings,'supplier_mail_owner_id',str(uuid4()))
    class IMAP:
        def select(self,*a,**kw):return 'OK',[]
        def uid(self,command,*args):
            if command=='search':
                assert 'UNSEEN' not in args[-1]
                return 'OK',[b'719']
            return 'OK',[(b'FLAGS (\\Seen)',raw().as_bytes())]
        def logout(self):pass
    monkeypatch.setattr(mail,'connect',lambda:IMAP())
    async def process(*args):return {'status':'succeeded'}
    monkeypatch.setattr(mail,'process_text',process)
    assert mail.poll('TEST')['messages'][0]['status']=='succeeded'
    assert mail.poll('TEST')['messages']==[]

@pytest.mark.parametrize('prefix',['Ne pas ', 'Annuler la demande de ', 'Modifier F123 avant de '])
def test_normalization_preserves_negative_or_other_prior_actions(prefix):
    text=prefix+'créer le fournisseur suivant :\nESSAI,/ADRESSE :RUE TEST :IF:1234'
    assert mail.normalize_supplier_body(text)==text

def test_duplicate_result_identifies_existing_supplier(actions):
    s,calls=actions
    s['state']['partners'][0]['operation']={'status':'blocked','validation':{'sql_error_number':50109,'message':'Existing supplier TEST','diagnostics':[{'duplicate_code':'F1099'}]}}
    with pytest.raises(mail.MailBlocked) as error:asyncio.run(mail.process_text('Créer fournisseur','TEST'))
    assert error.value.result=={'status':'blocked_duplicate','reason':'supplier_already_exists','message':'Existing supplier TEST','existing_codes':['F1099']}
    assert not calls


def test_creation_email_details_come_from_verified_record(actions):
    result=asyncio.run(mail.process_text('Créer ESSAI','TEST'))
    assert result['operations'][0]['name']=='TEST SUPPLIER'
    assert result['operations'][0]['ice']=='001234567890123'


def test_activation_cutoff_is_scoped_to_target_and_uidvalidity(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(mail.settings,'gmail_user','owner@example.test')
    class IMAP:
        def response(self,key):assert key=='UIDVALIDITY';return key,[b'123']
    with mail.ledger() as c:
        c.execute('INSERT INTO activations(folder,mailbox,uidvalidity,min_uid) VALUES(?,?,?,?)',('OB','owner@example.test','123',900));c.commit()
        assert mail.activation_cutoff(c,IMAP(),'OB')==900
        assert mail.activation_cutoff(c,IMAP(),'TEST')==0
        c.execute("UPDATE activations SET uidvalidity='456'");c.commit()
        with pytest.raises(ValueError,match='uidvalidity'):mail.activation_cutoff(c,IMAP(),'OB')


def test_activation_never_replays_test_emails_in_production(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(mail.settings,'supplier_mail_owner_id',str(uuid4()))
    monkeypatch.setattr(mail.settings,'gmail_user','owner@example.test')
    with mail.ledger() as c:
        c.execute('INSERT INTO activations(folder,mailbox,uidvalidity,min_uid) VALUES(?,?,?,?)',('OB','owner@example.test','123',900));c.commit()
    fetched=[]
    class IMAP:
        def select(self,*a,**kw):return 'OK',[]
        def response(self,key):return key,[b'123']
        def uid(self,command,*args):
            if command=='search':return 'OK',[b'719 900']
            fetched.append(args[0]);return 'OK',[(b'header',raw(identifier='<new@example.test>').as_bytes())]
        def logout(self):pass
    monkeypatch.setattr(mail,'connect',lambda:IMAP())
    calls=[]
    async def process(text,folder,checkpoint):calls.append(folder);return {'status':'succeeded'}
    monkeypatch.setattr(mail,'process_text',process)
    assert mail.poll('OB')['messages'][0]['status']=='succeeded'
    assert calls==['OB'] and b'719' not in fetched
