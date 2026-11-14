"""Local lexical RAG (BM25), without a vector server or invented documents."""
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
from uuid import uuid4
from app.services.business_rules import normalize
from app.services import business_store as store

INJECTION=re.compile(r'ignore.{0,45}(instruction|regle|preced|system)|system\s*prompt|revel.{0,25}(secret|password|mot de passe)|execute.{0,25}(shell|powershell|sql)|<\|(?:system|im_start)',re.I)

def suspicious(text): return bool(INJECTION.search(normalize(text)))

def index_document(path,root,reviewed=False,synthetic=False):
    root=Path(root).resolve()
    path=Path(path).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {'.md','.txt'}:
        raise ValueError('Only local .md/.txt files within the document root are allowed')
    content=path.read_text(encoding='utf-8-sig')
    if len(content)>500_000: raise ValueError('Document too large')
    # Do not delete or overwrite previously indexed source revisions.
    digest=hashlib.sha256(content.encode()).hexdigest()
    source=path.relative_to(root).as_posix()+'#'+digest
    paragraphs=[content[i:i+1200] for i in range(0,len(content),1000)]
    with store.connection() as conn:
        row=conn.execute('SELECT id FROM knowledge_documents WHERE source_path=%s',(source,)).fetchone()
        if row: return str(row['id'])
        doc_id=uuid4()
        conn.execute('INSERT INTO knowledge_documents(id,source_path,sha256,source_kind,reviewed,synthetic) VALUES (%s,%s,%s,%s,%s,%s)',
            (doc_id,source,digest,'synthetic_test' if synthetic else 'user_supplied',reviewed,synthetic))
        for ordinal,paragraph in enumerate(paragraphs):
            conn.execute('INSERT INTO knowledge_passages(document_id,ordinal,content) VALUES (%s,%s,%s)',(doc_id,ordinal,paragraph))
    return str(doc_id)

def retrieve(query,conn,limit=4):
    rows=conn.execute('SELECT p.id,p.content,p.ordinal,d.source_path,d.sha256,d.reviewed,d.source_kind FROM knowledge_passages p JOIN knowledge_documents d ON d.id=p.document_id WHERE d.synthetic=false OR %s ORDER BY p.id LIMIT 2000',
        (store.settings.allow_synthetic_references,)).fetchall()
    tokens=[normalize(row['content']).split() for row in rows]
    query_tokens=set(normalize(query).split())
    document_frequency=Counter(term for words in tokens for term in set(words))
    average=sum(map(len,tokens))/len(tokens) if tokens else 1
    scored=[]
    for row,words in zip(rows,tokens):
        if suspicious(row['content']): continue
        counts=Counter(words)
        score=0.0
        for term in query_tokens:
            df=document_frequency[term]
            frequency=counts[term]
            if frequency:
                score+=math.log(1+(len(tokens)-df+0.5)/(df+0.5))*(frequency*2.2)/(frequency+1.2*(0.25+0.75*len(words)/average))
        if score>0:
            scored.append({'passage_id':row['id'],'source':row['source_path'],'sha256':row['sha256'],
                'reviewed':row['reviewed'],'source_kind':row['source_kind'],'score':round(score,4),'content':row['content'],
                'authority':'local_document_only_not_officially_certified'})
    return {'status':'empty_corpus' if not rows else ('matches' if scored else 'no_relevant_passages'),
        'passages':sorted(scored,key=lambda row:(-row['score'],row['passage_id']))[:limit],
        'method':'local_bm25','scope':'local_only','documents_are_untrusted_data':True}
