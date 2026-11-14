"""Conversation semantics and provenance; contains no ERP transport or authorization."""
import copy
import re
from datetime import datetime, timezone
from app.services.chat_turns import norm,SUPPLIER_WORD

VERSION = 'conversation-semantics-v1'
ORDINALS = {'premier':1, 'premiere':1, 'deuxieme':2, 'second':2, 'seconde':2,
            'troisieme':3, 'quatrieme':4, 'cinquieme':5, 'sixieme':6,
            'septieme':7, 'huitieme':8, 'neuvieme':9, 'dixieme':10}
NUMBERS = {'un':1, 'une':1, 'deux':2, 'trois':3, 'quatre':4, 'cinq':5,
           'six':6, 'sept':7, 'huit':8, 'neuf':9, 'dix':10}
SUPPLIER = SUPPLIER_WORD


def expected_count(text, entity='articles'):
    match = re.search(r'\b(20|1[0-9]|[1-9]|vingt|'+ '|'.join(NUMBERS) +r')\s+'+entity+r'\b', norm(text))
    if match and match[1]=='vingt':return 20
    return (NUMBERS.get(match[1]) or int(match[1])) if match else None


def targets(text):
    value = norm(text)
    found = re.findall(r'\b(?:'+ '|'.join(ORDINALS) +r')\s+article\b|\barticle\s+(?:n[°o]?\s*)?(20|1[0-9]|[1-9])\b', value)
    result = []
    for match in re.finditer(r'\b('+ '|'.join(ORDINALS) +r')\s+article\b|\barticle\s+(?:n[°o]?\s*)?(20|1[0-9]|[1-9])\b', value):
        result.append(ORDINALS[match[1]] if match[1] else int(match[2]))
    return sorted(set(result))


def expanded_designations(text):
    """Only expand an explicitly shared prefix/suffix around two literal letters."""
    match = re.search(r'\b(?:deux|2)\s+articles\s*:?\s*([^,;\n]+?)\s+([A-Z])\s+et\s+([A-Z])\s+([^,;\n.]+)', text)
    if not match or match[2] == match[3]: return []
    labels = [f'{match[1].strip()} {letter} {match[4].strip()}' for letter in (match[2],match[3])]
    return labels if all(len(label)<=70 for label in labels) else []


def supplier_decision(text):
    value = norm(text)
    if re.search(SUPPLIER+r'\s+(?:n.est\s+)?(?:pas\s+oblig(?:atoire|er|e)?|facultatif|optionnel)', value):
        return 'optional'
    if re.search(r'\b(?:sans\s+|aucun\s+|pas\s+de\s+)'+SUPPLIER+r'\b|\b(?:retire|supprime|enleve)\s+(?:le\s+)?'+SUPPLIER+r'\b', value):
        return 'none'
    return None


def clarification(text,state,delta):
    value=norm(text)
    if re.search(r'\b(?:non\s+pas\s+celui|l.autre|pas\s+celui.la)\b',value) and not any(
        v and norm(str(v)) in value for v in delta.shared.model_dump(exclude_unset=True).values()):
        return 'Quelle fiche ou quelle valeur souhaitez-vous retenir ? Indiquez son nom, son code ou son numéro.'
    if state.get('articles') and re.search(r'\b(?:change|changer|remplace|remplacer|modifie)\b[^.;!?]{0,30}\b(?:le\s+)?code\b',value):
        supplied=delta.shared.code_article or any(p.code_article for p in delta.articles)
        if not supplied and not naming_request(text):return 'Quel nouveau code article souhaitez-vous utiliser, et pour quel article ?'
    return None


def literal_scope(text, label, labels):
    """Return the literal declaration segment for a particular newly named object."""
    lowered = norm(text)
    start = lowered.find(norm(label))
    if start < 0: return ''
    ends = [lowered.find(norm(other), start+len(label)) for other in labels if other != label]
    end = min((pos for pos in ends if pos >= 0), default=len(text))
    return text[start:end]


def naming_request(text):
    value = norm(text)
    replace = re.search(r'(?:remplace(?:r)?|utilise(?:r)?)\s+[«"\']?([-_])[»"\']?\s+(?:par|a la place de)\s+[«"\']?([-_])', value)
    inverse = re.search(r'(?:utilise(?:r)?\s+)?[«"\']?([_-])[»"\']?\s+a la place (?:de|du)\s+[«"\']?([_-])', value)
    prefix = bool(re.search(r'(?:commenc\w*|prefix\w*)[^.;!?]{0,70}(?:categorie|catigorie)', value))
    if not replace and not inverse and not prefix: return None
    return {'replace': [replace[1],replace[2]] if replace else [inverse[2],inverse[1]] if inverse else None,
            'category_prefix':prefix, 'scope':'selection' if targets(text) else 'conversation', 'source':'user_declared',
            'global':False}


def apply_naming(state, text, invalidate):
    request = naming_request(text)
    explicit=bool(request)
    if not request:
        request=state.get('naming_convention')
        if not request or request.get('scope')!='conversation':return
    selected = targets(text) if explicit else []
    if not selected:selected=list(range(1,len(state.get('articles',[]))+1))
    errors=[]
    for index in selected:
        if index > len(state['articles']): raise ValueError('invalid_article_target')
        article=state['articles'][index-1];old=article.get('code_article') or ''
        source=article.get('sources',{}).get('code_article','')
        if not explicit and source not in ('application_proposal_not_reserved','user_naming_convention_not_reserved'):continue
        candidate=article.get('naming_base_code',old) if not explicit else old
        if explicit:article['naming_base_code']=old
        if request['replace']: candidate=candidate.replace(*request['replace'])
        if request['category_prefix']:
            category=article.get('categorie')
            if not category:
                errors.append({'article_id':article['id'],'reason':'category_required_for_naming'});continue
            separator=request['replace'][1] if request['replace'] else '_'
            if not candidate.startswith(category+separator): candidate=category+separator+candidate
        if not re.fullmatch(r'[A-Za-z0-9_./ -]{1,20}',candidate):
            errors.append({'article_id':article['id'],'reason':'naming_code_invalid_or_too_long'});continue
        if candidate!=old:
            invalidate(article);article['code_article']=candidate
            article.setdefault('sources',{})['code_article']='user_naming_convention_not_reserved'
    state['naming_convention']=request
    state['naming_errors']=errors


def record_changes(before, after, text, fields):
    """Keep bounded value history with provenance; an interpretation is not approval."""
    if after.get('last_turn',{}).get('readonly'):return after
    previous={a['id']:a for a in before.get('articles',[])}
    changes=[]
    for article in after.get('articles',[]):
        old=previous.get(article['id'],{})
        for name in fields:
            if old.get(name)==article.get(name) and name in old: continue
            value=article.get(name);source=article.get('sources',{}).get(name,'unknown')
            status='removed' if source=='user_explicitly_removed' else 'unknown' if value is None else 'proposed' if 'proposal' in source else 'declared'
            article.setdefault('field_states',{})[name]={'value':value,'status':status,'source':source,'previous':old.get(name)}
            if value!=old.get(name):changes.append({'article_id':article['id'],'field':name,'before':old.get(name),'after':value,'status':status,'source':source})
    if changes:
        history=after.setdefault('correction_history',[])
        history.append({'at':datetime.now(timezone.utc).isoformat(),'version':VERSION,'changes':changes})
        after['correction_history']=history[-100:]
    return after


def memory_context(state):
    # PostgreSQL keeps the full ledger. Sending it all grows quadratically with
    # batch size and can evict the system prompt from Qwen's bounded context.
    latest={}
    for entry in reversed(state.get('correction_history',[])):
        for change in reversed(entry.get('changes',[])):
            key=(change.get('article_id'),change.get('field'))
            if key not in latest:latest[key]={k:change.get(k) for k in ('article_id','field','before','after')}
            if len(latest)>=12:break
        if len(latest)>=12:break
    return {'conventions':state.get('naming_convention'), 'supplier_requirement':state.get('supplier_requirement'),
            'recent_corrections':list(latest.values()),
            'awaiting_confirmation':state.get('awaiting_confirmation'),
            'workflow':state.get('workflow','draft'),
            'decisions':[{'id':a.get('id'),'supplier_intent':a.get('supplier_intent'),
                          'sources':{k:v for k,v in a.get('sources',{}).items() if v!='user_declared'}} for a in state.get('articles',[])]}
