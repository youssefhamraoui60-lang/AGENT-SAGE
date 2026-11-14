from email.message import EmailMessage
from app.services import supplier_mail as mail,supplier_mail_replies as replies
import pytest


def original():
    m=EmailMessage();m['From']='Requester <requester@example.test>';m['To']='inbox@example.test'
    m['Cc']='someone-else@example.test';m['Subject']='FRS OB';m['Message-ID']='<request-719@example.test>'
    m.set_content('From: quoted-person@example.test\nSupplier details')
    return m


def test_reply_targets_requester_and_cc_and_stays_in_thread():
    message=replies.build_reply(original(),{'status':'blocked_duplicate','existing_codes':['F1099']},'TEST')
    assert str(message['To'])=='requester@example.test'
    assert str(message['Cc'])=='someone-else@example.test'
    assert message['In-Reply-To']=='<request-719@example.test>'
    assert message['References']=='<request-719@example.test>'
    assert message['Auto-Submitted']=='auto-replied'
    assert message['Subject']=='Re: FRS OB'
    assert 'F1099' in message.get_content() and 'TEST' in message.get_content()
    assert 'quoted-person' not in message.as_string()


def test_reply_to_is_primary():
    m=original();m['Reply-To']='other-requester@example.test'
    assert replies.recipient(m)=='other-requester@example.test'


@pytest.mark.parametrize('header,value',[('Auto-Submitted','auto-replied'),('Auto-Submitted','auto-generated'),('Precedence','bulk'),('X-Auto-Response-Suppress','All')])
def test_automatic_mail_never_gets_a_reply(header,value):
    m=original();m[header]=value
    assert replies.build_reply(m,{'status':'succeeded'},'TEST') is None


@pytest.mark.parametrize('sender',['a@example.test, b@example.test','mailer-daemon@example.test','postmaster@example.test','invalid'])
def test_invalid_ambiguous_and_bounce_recipients_skipped(sender):
    m=original();m.replace_header('From',sender)
    assert replies.recipient(m) is None


def test_success_and_uncertainty_are_distinct():
    success=replies.response_text({'status':'succeeded','operations':[{'kind':'create','status':'succeeded','keys':{'BPSNUM':'F123'}}]},'TEST')
    uncertain=replies.response_text({'status':'requires_readback','operations':[{'kind':'create','status':'ambiguous'}]},'TEST')
    assert 'F123' in success and 'vérifié' in success
    assert 'créé' not in uncertain and 'vérifier' in uncertain


def test_attachment_reply_explains_next_action():
    body=replies.response_text({'status':'requires_review','reason':'attachments_require_text_body_without_attachments'},'TEST')
    assert 'sans pièce jointe' in body


@pytest.fixture
def ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(mail.settings,'supplier_mail_state_file',str(tmp_path/'mail.sqlite3'))
    with mail.ledger() as c:yield c


def test_reply_sent_once_even_after_reopening_ledger(ledger,monkeypatch):
    sent=[];monkeypatch.setattr(replies,'send',lambda msg:sent.append(msg))
    assert replies.notify(ledger,'key',original(),{'status':'blocked_duplicate','existing_codes':['F1099']},'TEST')=='sent'
    assert replies.notify(ledger,'key',original(),{'status':'blocked_duplicate'},'TEST') is None
    assert len(sent)==1 and ledger.execute('SELECT status FROM replies').fetchone()[0]=='sent'


def test_smtp_timeout_never_automatically_replays(ledger,monkeypatch):
    calls=[]
    def fail(msg):calls.append(True);raise TimeoutError()
    monkeypatch.setattr(replies,'send',fail)
    assert replies.notify(ledger,'key',original(),{'status':'requires_review'},'TEST')=='requires_review'
    assert replies.notify(ledger,'key',original(),{'status':'requires_review'},'TEST') is None
    assert calls==[True]


def test_in_progress_sage_execution_does_not_get_a_final_reply(ledger,monkeypatch):
    monkeypatch.setattr(replies,'send',lambda msg:pytest.fail('No premature response'))
    assert replies.notify(ledger,'key',original(),{'status':'processing'},'TEST') is None
    assert ledger.execute('SELECT count(*) FROM replies').fetchone()[0]==0


def test_existing_request_gets_reply_without_reexecuting_sage(ledger,monkeypatch):
    import hashlib
    monkeypatch.setattr(mail.settings,'supplier_mail_owner_id','11111111-1111-1111-1111-111111111111')
    message=original()
    key=hashlib.sha256((mail.settings.gmail_user.lower()+'\0TEST\0'+str(message['Message-ID'])).encode()).hexdigest()
    assert mail.claim(ledger,key,'TEST')
    mail.save(ledger,key,'blocked_duplicate',result={'status':'blocked_duplicate','existing_codes':['F1099']})
    class IMAP:
        def select(self,*a,**kw):return 'OK',[]
        def uid(self,command,*args):return ('OK',[b'719']) if command=='search' else ('OK',[(b'header',message.as_bytes())])
        def logout(self):pass
    monkeypatch.setattr(mail,'connect',lambda:IMAP())
    async def forbidden(*args):pytest.fail('Existing request must not execute Sage again')
    monkeypatch.setattr(mail,'process_text',forbidden)
    sent=[];monkeypatch.setattr(replies,'send',lambda msg:sent.append(msg))
    assert mail.poll('TEST')['messages'][0]['reply']=='sent'
    assert mail.poll('TEST')['messages']==[] and len(sent)==1


def test_smtp_starts_tls_before_login(monkeypatch):
    calls=[]
    class SMTP:
        def __init__(self,*a,**kw):calls.append('connect')
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def ehlo(self):calls.append('ehlo')
        def starttls(self,**kw):calls.append('tls')
        def login(self,*a):calls.append('login')
        def send_message(self,*a):calls.append('send');return {}
    monkeypatch.setattr(replies.smtplib,'SMTP',SMTP)
    monkeypatch.setattr(mail.settings,'smtp_port',587)
    replies.send(replies.build_reply(original(),{'status':'blocked_duplicate','existing_codes':['F1099']},'TEST'))
    assert calls==['connect','ehlo','tls','ehlo','login','send']


@pytest.fixture(autouse=True)
def configured_mailbox(monkeypatch):
    monkeypatch.setattr(mail.settings,'gmail_user','inbox@example.test')


def test_reply_all_deduplicates_and_preserves_blind_recipients():
    m=original()
    m.replace_header('To','inbox@example.test, colleague@example.test, REQUESTER@example.test')
    m.replace_header('Cc','colleague@example.test, someone-else@example.test, INBOX@example.test')
    m['Bcc']='secret@example.test, someone-else@example.test'
    reply=replies.build_reply(m,{'status':'blocked_duplicate','existing_codes':['F1099']},'TEST')
    assert str(reply['To'])=='requester@example.test, colleague@example.test'
    assert str(reply['Cc'])=='someone-else@example.test'
    assert str(reply['Bcc'])=='secret@example.test'
    assert 'secret@example.test' not in str(reply['To'])+str(reply['Cc'])


def test_no_hidden_recipient_is_inferred_from_forwarded_body():
    m=original();m.set_content('Cc: quoted-copy@example.test\nBcc: hidden@example.test')
    reply=replies.build_reply(m,{'status':'needs_input'},'TEST')
    assert reply['Bcc'] is None
    assert 'quoted-copy' not in reply.as_string() and 'hidden@example.test' not in reply.as_string()


def test_smtp_envelope_includes_bcc_without_disclosing_header():
    import smtplib
    m=original();m['Bcc']='secret@example.test'
    reply=replies.build_reply(m,{'status':'needs_input'},'TEST')
    captured={}
    class CaptureSMTP(smtplib.SMTP):
        def __init__(self):pass
        def ehlo_or_helo_if_needed(self):pass
        def sendmail(self,from_addr,to_addrs,msg,mail_options=(),rcpt_options=()):
            captured.update(recipients=to_addrs,body=msg);return {}
    CaptureSMTP().send_message(reply)
    assert 'secret@example.test' in captured['recipients']
    assert 'someone-else@example.test' in captured['recipients']
    assert b'Bcc:' not in captured['body'] and b'secret@example.test' not in captured['body']


def test_formal_creation_response_uses_separate_verified_fields():
    body=replies.response_text({'status':'succeeded','operations':[
        {'kind':'create','status':'succeeded','keys':{'BPSNUM':'F10048'},'name':'Rappe BTP','ice':'001234567890123'}]},'TEST')
    assert body.startswith('Bonjour,\n\nNous vous informons que le fournisseur a bien été créé')
    assert 'Code fournisseur : F10048\nNom du fournisseur : Rappe BTP\nICE : 001234567890123' in body
    assert body.endswith('Cordialement,\nÉquipe SI.')
    assert 'TEST' in body


def test_missing_ice_is_not_replaced_with_supplier_code():
    body=replies.response_text({'status':'succeeded','operations':[
        {'kind':'create','status':'succeeded','keys':{'BPSNUM':'F10048'},'name':'Rappe BTP','ice':''}]},'TEST')
    assert 'ICE : Non renseigné' in body and 'ICE : F10048' not in body
