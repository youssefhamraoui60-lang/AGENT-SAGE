"""Durable preparations, including incomplete drafts. No Sage writes."""
import json
import time
import secrets
import creation

def save(owner,details,history):
    with creation.connection() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS sob_preparations(owner TEXT PRIMARY KEY,details TEXT NOT NULL,history TEXT NOT NULL,updated REAL NOT NULL)')
        conn.execute('INSERT OR REPLACE INTO sob_preparations VALUES(?,?,?,?)',(owner,json.dumps(details,ensure_ascii=False),json.dumps(history,ensure_ascii=False),time.time()))

def handoff(owner):
    token=secrets.token_hex(16)
    with creation.connection() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS sob_handoffs(token TEXT PRIMARY KEY,owner TEXT NOT NULL,created REAL NOT NULL,claimed_by TEXT)')
        conn.execute('INSERT INTO sob_handoffs VALUES(?,?,?,NULL)',(token,owner,time.time()))
    return token

def claim(token,actor):
    with creation.connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM sob_handoffs WHERE token=?',(token,)).fetchone()
        if not row or row['created']<time.time()-28800 or row['claimed_by'] not in (None,actor):raise ValueError('Code absent, expiré ou déjà rattaché à un autre utilisateur.')
        draft=conn.execute('SELECT history FROM sob_preparations WHERE owner=?',(row['owner'],)).fetchone()
        if not draft:raise ValueError('Brouillon source introuvable.')
        conn.execute('UPDATE sob_handoffs SET claimed_by=? WHERE token=?',(actor,token))
        return json.loads(draft['history'])

