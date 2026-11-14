"""Reviewed examples, not model training or authoritative business rules."""
from datetime import datetime,timezone
import copy,re
from difflib import SequenceMatcher
from app.services.chat_turns import norm

VERSION='reviewed-experience-v1'
SECRET=re.compile(r'(?i)(?:password|mot\s+de\s+passe|token|secret|authorization|bearer)\s*[:=]?\s*\S+')


def safe(value):
    if isinstance(value,str):return SECRET.sub('[REDACTED]',value)[:1200]
    if isinstance(value,list):return [safe(x) for x in value[:20]]
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items() if not re.search(r'password|token|secret',k,re.I)}
    return value


def snapshot(article,state,fields,model):
    result={k:article.get(k) for k in fields if article.get(k) is not None}
    if article.get('kind'):
        history=[x for entry in article.get('history',[]) for x in entry.get('changes',[])][-12:]
    else:history=[x for entry in state.get('correction_history',[]) for x in entry.get('changes',[]) if x.get('article_id')==article['id']][-12:]
    result['_experience']={'version':VERSION,'validated_by_human':True,'source':'explicit_draft_review',
        'recorded_at':datetime.now(timezone.utc).isoformat(),'model_version':model,'model_digest':None,
        'correct_intent':article.get('kind','article')+'_draft','fields_concerned':[x['field'] for x in history],
        'validated_corrections':history,'obtained':{k:article.get(k) for k in fields if article.get(k) is not None},
        'expected':'reviewed_snapshot','problem_type':'user_correction' if history else 'draft_review',
        'confidence':'human_reviewed_not_business_certification','rule_version':'conversation-semantics-v1',
        'observed_model_error':None,'scope':'same_owner_only','training_performed':False}
    return safe(result)


def relevant(text,rows,limit=2):
    query=norm(text);tokens=set(re.findall(r'\w+',query));ranked=[]
    for row in rows:
        value=row.get('snapshot',row)
        # Old examples were inserted by the same explicit review path.
        experience=value.get('_experience')
        if experience and experience.get('validated_by_human') is not True:continue
        words=' '.join(str(v) for k,v in value.items() if not k.startswith('_'))
        normalized=norm(words);terms=set(re.findall(r'\w+',normalized))
        overlap=len(tokens&terms)/max(1,len(tokens))
        similarity=SequenceMatcher(None,query[:600],normalized[:600]).ratio()
        score=.8*overlap+.2*similarity
        if overlap>0 and score>=.12:ranked.append((score,safe(value)))
    return [value for _,value in sorted(ranked,key=lambda x:x[0],reverse=True)[:limit]]
