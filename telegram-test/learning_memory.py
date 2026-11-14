"""Persistent SOB lessons in the existing PostgreSQL learning database.

Lessons are data: they cannot provide SQL, write permissions, client scope or
execution authority. Only an explicit, validated article correction is activated.
"""
import json
import re
import unicodedata
import hashlib
from contextvars import ContextVar
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import business_store as db
from psycopg.types.json import Jsonb

ACTIVE = ContextVar('sob_learning_rules',default=())


def key(value):
    # Keep Arabic and other letters: dropping them made "حديد 14" collide with
    # the unrelated alias "14", and made Arabic-only corrections impossible.
    normalized=''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())
    pointe=re.fullmatch(r'pointes?(?:deparis)?0?([68])',normalized)
    return 'pointe'+pointe[1] if pointe else normalized


def migrate():
    with db.connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS sob_learning_rules (
            id bigserial PRIMARY KEY, kind text NOT NULL, rule_key text NOT NULL,
            payload jsonb NOT NULL, status text NOT NULL CHECK(status IN ('approved','pending','disabled')),
            source text NOT NULL, revision integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(kind,rule_key))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sob_learning_events (
            id bigserial PRIMARY KEY, rule_id bigint REFERENCES sob_learning_rules(id),
            event text NOT NULL,payload jsonb NOT NULL,actor text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now())''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sob_learning_examples (
            source_key text PRIMARY KEY,input_data jsonb NOT NULL,expected jsonb,
            observed jsonb,status text NOT NULL,created_at timestamptz NOT NULL DEFAULT now())''')


def approved_rules():
    with db.connection() as conn:
        return conn.execute("SELECT kind,rule_key,payload,revision FROM sob_learning_rules WHERE status='approved' ORDER BY kind,rule_key").fetchall()


def rules():
    with db.connection() as conn:
        return conn.execute('SELECT id,kind,rule_key,payload,status,source,revision,updated_at FROM sob_learning_rules ORDER BY id').fetchall()


def save(kind, rule_key, payload, *, actor, source, approved=False, replace=True):
    if kind not in ('article_alias','client_alias','policy','interpretation'):
        raise ValueError('Unsupported rule type')
    if not rule_key or len(rule_key)>100 or len(json.dumps(payload))>2000:
        raise ValueError('Invalid rule')
    if kind=='article_alias':
        rule_key=key(rule_key)
        if not rule_key:
            raise ValueError('Empty alias')
        if set(payload)!={'code'} or not re.fullmatch(r'[A-Z][A-Z0-9_./-]{0,39}',payload['code']):
            raise ValueError('Invalid Sage article code')
    if kind=='client_alias':
        rule_key=key(rule_key)
        if not rule_key or not re.fullmatch(r'C\d{4,8}',payload.get('code','')) or set(payload)-{'code','representative'}:
            raise ValueError('Invalid client alias')
    status='approved' if approved else 'pending'
    with db.connection() as conn:
        old=conn.execute('SELECT * FROM sob_learning_rules WHERE kind=%s AND rule_key=%s FOR UPDATE',(kind,rule_key)).fetchone()
        if old and not replace:
            return old['id']
        if not replace:
            inserted=conn.execute('''INSERT INTO sob_learning_rules(kind,rule_key,payload,status,source)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(kind,rule_key) DO NOTHING RETURNING id''',
                (kind,rule_key,Jsonb(payload),status,source)).fetchone()
            if inserted:
                conn.execute('INSERT INTO sob_learning_events(rule_id,event,payload,actor) VALUES(%s,%s,%s,%s)',
                    (inserted['id'],'created',Jsonb({'after':{'payload':payload,'status':status}}),actor))
                return inserted['id']
            return conn.execute('SELECT id FROM sob_learning_rules WHERE kind=%s AND rule_key=%s',(kind,rule_key)).fetchone()['id']
        row=conn.execute('''INSERT INTO sob_learning_rules(kind,rule_key,payload,status,source)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(kind,rule_key) DO UPDATE
            SET payload=EXCLUDED.payload,status=EXCLUDED.status,source=EXCLUDED.source,
                revision=sob_learning_rules.revision+1,updated_at=now() RETURNING id''',
            (kind,rule_key,Jsonb(payload),status,source)).fetchone()
        conn.execute('INSERT INTO sob_learning_events(rule_id,event,payload,actor) VALUES(%s,%s,%s,%s)',
                     (row['id'],'updated' if old else 'created',Jsonb({'before':dict(old) if old else None,'after':{'payload':payload,'status':status}} if not old else {'before':{'payload':old['payload'],'status':old['status'],'revision':old['revision']},'after':{'payload':payload,'status':status}}),actor))
        return row['id']


def article_alias(value):
    target=key(value)
    for rule in ACTIVE.get():
        if rule['kind']=='article_alias' and rule['rule_key']==target:
            return rule['payload']['code']
    return None


def client_alias(value,representative=None):
    candidates=[r for r in ACTIVE.get() if r['kind']=='client_alias' and r['rule_key']==key(value)
                and (not r['payload'].get('representative') or r['payload']['representative']==representative)]
    return candidates[0]['payload']['code'] if len(candidates)==1 else None


def policy(name,default=None):
    for rule in ACTIVE.get():
        if rule['kind']=='policy' and rule['rule_key']==name:
            return rule['payload'].get('value',default)
    return default


def prompt_context(text=''):
    # Bounded approved instructions only. No examples or arbitrary pending text.
    normalized=key(text)
    # A transcription belongs only to its exact file, never to another prompt.
    body='\n'.join(line for line in text.splitlines() if not re.match(r'^\s*(?:contact|num[eé]ro)\s*:',line,re.I))
    body_hash=hashlib.sha256(re.sub(r'\s+',' ',body).strip().casefold().encode()).hexdigest()
    general=[r for r in ACTIVE.get() if r['kind'] not in ('article_alias','client_alias')
             and not r['rule_key'].startswith(('document_sha256_','confirmed_source_group_'))
             and not r['payload'].get('source_message')
             and (not r['payload'].get('source_body_key') or r['payload']['source_body_key']==body_hash)]
    relevant=[r for r in ACTIVE.get() if r['kind'] in ('article_alias','client_alias') and r['rule_key'] in normalized]
    selected=general+relevant[:40]
    while len(json.dumps(selected,ensure_ascii=False,default=str))>16000 and selected:
        selected.pop()
    return json.dumps(selected,ensure_ascii=False,default=str)


def parse_correction(text):
    match=re.fullmatch(r'\s*(?:/?corrig(?:er|e)|correction|remplace(?:r)?)\b\s*:?\s*(?:article\s+)?(.{1,80}?)\s*(?:=|->|→|\bpar\b)\s*([A-Za-z][A-Za-z0-9_-]{0,39})\s*',text,re.I)
    if not match:
        match=re.fullmatch(r"\s*(?:non[, :]\s*)?(?:l['’]article|article)\s+(.{1,80}?)\s+(?:c['’]est|est|correspond\s+[àa])\s+([A-Za-z][A-Za-z0-9_-]{0,39})\s*[.!]?\s*",text,re.I)
    return (match[1].strip(),match[2].upper()) if match else None


def seed():
    aliases={'pointe 6':'PF-TP16X20','pointe 8':'PF-TP08X20','PP6':'PP06','PP8':'PP08',
             'TRS':'MANTD','TRC':'MANTD','transport':'MANTD','manutention':'MANTD',
             'ciment 35':'CPJ35','ciment 45':'CPJ45','sima 35':'CPJ35','sima 45':'CPJ45',
             'perfecto':'CPJ35P','tradicem':'COL','rab 6':'RABT6'}
    for alias,code in aliases.items():
        save('article_alias',alias,{'code':code},actor='user_confirmed_history',source='Corrections utilisateur dans cette conversation ; references Sage verifiees',approved=True,replace=False)
    for name,value in [('missing_price_ttc',0),('delivery_default','today'),('service_quantity',1),('telegram_max_chars',200),('telegram_batch_seconds',30)]:
        save('policy',name,{'value':value},actor='user_confirmed_history',source='Regle explicitement demandee par utilisateur',approved=True,replace=False)
    for name,text in [('contact_role','Contact désigne le commercial, pas le client.'),
                      ('grouped_order','Messages rapprochés du même commercial : regrouper articles, transport et lieu pour une commande ; ne pas fusionner des clients différents.'),
                      ('price_priority','Prix explicite, sinon dernier prix du même client/article, sinon zéro TTC autorisé.'),
                      ('reference_resolution','Rechercher les codes et noms dans Sage, départager les homonymes par commercial ; jamais inventer de code.')]:
        save('interpretation',name,{'text':text},actor='user_confirmed_history',source='Corrections utilisateur dans cette conversation',approved=True,replace=False)


def import_audit():
    root=Path(__file__).resolve().parents[1]/'runtime/sob-audit'
    audit=root/'evaluation-release.json'
    if not audit.exists():return 0
    messages={r['id']:r for r in json.loads((root/'messages-selected.json').read_text(encoding='utf-8'))}
    count=0
    with db.connection() as conn:
        for row in json.loads(audit.read_text(encoding='utf-8')):
            source_key='sob-20261107-'+','.join(map(str,row['message_ids']))
            inputs=[{'id':i,'date':messages[i]['date'],'text':messages[i]['text']} for i in row['message_ids']]
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO NOTHING''',
                (source_key,Jsonb(inputs),Jsonb({'orders':row['ob_orders'],'quantities':row.get('expected_quantities')}),
                 Jsonb({'client_match':row.get('client_match'),'lines_match':row.get('lines_match'),'missing':row.get('details',{}).get('missing_fields',[])}),
                 'matched_ob' if row.get('complete_match') else 'needs_review'))
            count+=1
    return count


if __name__=='__main__':
    migrate();seed()
    print(json.dumps({'rules':len(rules()),'examples':import_audit(),'sage_writes':0}))
