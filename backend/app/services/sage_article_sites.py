"""Separate child workflow for existing EXT_POUDRE; never modifies/recreates parent."""
import json,re,subprocess
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from pathlib import Path
from app.services import business_store as db
from app.services.sage_crud import CrudError,digest
from app.core.config import settings

ROOT=Path(__file__).resolve().parents[3]
PERMITS={}


def run(script,payload=None):
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts'/script)],
            input=json.dumps(payload or {}),text=True,capture_output=True,encoding='utf-8',timeout=150)
        result=json.loads(p.stdout.lstrip('\ufeff'))
        if p.returncode or not result.get('ok'):raise CrudError(result.get('code','site_worker_failed'),409)
        return result
    except (OSError,ValueError,subprocess.SubprocessError):raise CrudError('site_outcome_unknown_do_not_retry',503) from None


def catalog():
    result=run('read_site_catalog.ps1')
    if result.get('folder')!='TEST':raise CrudError('site_catalog_not_test',423)
    return [s for s in result['sites'] if s['company']=='20' and s['site'] in ('201','202','209')]


def worker(code,site,mode,**extra):
    if not settings.sage_powershell_chat_enabled or code!='EXT_POUDRE' or site not in {s['site'] for s in catalog()}:
        raise CrudError('site_scope_denied',423)
    return run('sage_site_worker.ps1',{'Code':code,'Site':site,'Mode':mode,**extra})['result']


def requested_sites(text):
    if not re.search(r'article[\s-]*sites?|rattach',text,re.I):return None
    values=sorted(set(re.findall(r'(?<!\d)(\d{3})(?!\d)',text)))
    if re.search(r'\b(?:tous|tout|toutes)\b',text,re.I):return 'all'
    return values if values else None


def capture(owner,identifier,text,revision):
    selected=requested_sites(text)
    if selected is None:return None
    from app.services import conversation_chat as chat
    available=catalog();valid={s['site'] for s in available}
    if selected=='all':selected=sorted(valid)
    if not selected or not set(selected)<=valid:raise CrudError('sites_not_in_OULD_BOUAZZA_TEST',422)
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision or row['state'].get('_pending'):raise CrudError('stale_or_pending_conversation',409)
        articles=[a for a in row['state'].get('articles',[]) if (a.get('outcome') or {}).get('confirmed') and a.get('code_article')=='EXT_POUDRE']
        if len(articles)!=1:raise CrudError('existing_article_required_for_site_request',409)
        a=articles[0];previous=a.get('site_request') or {}
        if previous.get('status') in ('executing','ambiguous'):raise CrudError('site_attempt_requires_readback_no_retry',409)
        a['site_request']={'id':str(uuid4()),'sites':selected,'company':'20','company_name':'OULD BOUAZZA',
            'folder':'TEST','status':'requested','available_sites':available,'results':{},'plans':{}}
        chat.save_conversation_context(conn,owner,identifier,row['state'])
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
        chat.append(conn,identifier,'user',text)
        chat.append(conn,identifier,'assistant','L’article EXT_POUDRE est déjà créé et sera conservé. '
            +'Fiches article-site demandées dans TEST / OULD BOUAZZA : '+', '.join(selected)
            +'. Préparez les fiches, puis confirmez cette sélection avant exécution. Aucun SAVE envoyé.',
            {'article_site_request':True,'sites':selected,'save_sent':False})
    return chat.read(owner,identifier)


def action(owner,identifier,article_id,kind,revision,confirm):
    from app.services import conversation_chat as chat
    if not settings.sage_powershell_chat_enabled:raise CrudError('powershell_chat_disabled',423)
    if kind not in ('site-prepare','site-approve','site-execute'):raise CrudError('unknown_site_action',422)
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision or row['state'].get('_pending'):raise CrudError('stale_or_pending_conversation',409)
        a=next((a for a in row['state']['articles'] if a['id']==str(article_id)),None)
        if not a or a.get('code_article')!='EXT_POUDRE' or not (a.get('outcome') or {}).get('confirmed'):raise CrudError('parent_not_confirmed',409)
        req=a.get('site_request')
        if not req or req['status'] in ('executing','ambiguous','succeeded'):raise CrudError('site_request_not_editable',409)
        if kind=='site-prepare':
            req['plans']={site:worker(a['code_article'],site,'prepare') for site in req['sites']}
            req['digest']=digest(req['plans']);req['status']='prepared'
            PERMITS.pop(req['id'],None)
        elif kind=='site-approve':
            if not confirm or req['status']!='prepared':raise CrudError('site_specific_confirmation_required',403)
            PERMITS[req['id']]={'owner':str(owner),'digest':req['digest'],'expires':datetime.now(timezone.utc)+timedelta(minutes=15)}
            req['status']='approved'
        else:
            permit=PERMITS.get(req['id'])
            if (not confirm or req['status']!='approved' or not permit or permit['owner']!=str(owner)
                or permit['digest']!=digest(req['plans']) or permit['expires']<=datetime.now(timezone.utc)):
                raise CrudError('site_approval_expired_or_missing',403)
            PERMITS.pop(req['id'],None);req['status']='executing'
            code=a['code_article'];snapshot=json.loads(json.dumps(req))
        chat.save_conversation_context(conn,owner,identifier,row['state'])
        chat.append(conn,identifier,'system',kind,{'sites':req['sites'],'parent_save_sent':False})
    if kind!='site-execute':return chat.read(owner,identifier)
    results={};uncertain=False
    for site in snapshot['sites']:
        if uncertain:
            results[site]={'State':'NOT_ATTEMPTED_AFTER_UNCERTAINTY','SaveAttempts':0};continue
        plan=snapshot['plans'][site]
        approval={'Approved':True,'Folder':'TEST','Code':code,'Site':site,'Actor':'chat:'+str(owner),
            'Digest':plan.get('Digest'),'DescriptionHash':plan.get('DescriptionHash'),'ExpiresAt':permit['expires'].isoformat()}
        try:
            result=worker(code,site,'execute',Plan=plan,Approval=approval)
        except Exception:result={'State':'UNCERTAIN','ReadConfirmed':False,'RetryAllowed':False}
        results[site]=result
        if not result.get('ReadConfirmed') or result.get('State') not in ('CREATED_AND_READ_BACK','ALREADY_EXISTS'):uncertain=True
        # Persist each result; never roll back a completed SOAP call with local state.
        with db.connection() as conn:
            row=chat.get_row(conn,owner,identifier,True)
            a=next(a for a in row['state']['articles'] if a['id']==str(article_id))
            a['site_request']['results']=dict(results)
            chat.save_conversation_context(conn,owner,identifier,row['state'])
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        a=next(a for a in row['state']['articles'] if a['id']==str(article_id))
        a['site_request']['results']=results;a['site_request']['status']='ambiguous' if uncertain else 'succeeded'
        chat.save_conversation_context(conn,owner,identifier,row['state'])
        chat.append(conn,identifier,'assistant','Fiches article-site : '+('relecture confirmée.' if not uncertain else 'résultat incomplet, ne pas relancer.')
            +' L’article maître n’a pas été recréé.',{'site_results':results,'parent_save_sent':False})
    return chat.read(owner,identifier)
