"""Local-browser approval bridge; only PowerShell sends SOAP. Public CRUD stays locked."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import subprocess
from uuid import uuid4

from app.core.config import settings
from app.services import business_store as db
from app.services.sage_crud import CrudError, digest
from app.services.article_agent import Draft, sql_check

ROOT = Path(__file__).resolve().parents[3]
PERMITS = {}


def extinguisher_scope(article):
    return (article.get('code_article')=='EXT_POUDRE'
            and article.get('designation','').casefold()=='extincteur à poudre'
            and article.get('code_fournisseur')=='F1025'
            and article.get('fournisseur_nom','').casefold()=='chaouia protect'
            and article.get('gestion_stock')=='1')


def foam_scope(article):
    names={'MFB-A-XPS-40':'Modern foam boards A XPS 4 CM','MFB-B-XPS-40':'Modern foam boards B XPS 4 CM'}
    return (article.get('code_article') in names and article.get('designation')==names[article['code_article']]
            and article.get('site')=='202' and article.get('categorie')=='NEG' and article.get('unite')=='M2'
            and not any(article.get(k) for k in ('code_fournisseur','fournisseur_nom','gestion_stock','gestion_lots')))


def creation_blockers(article):
    blockers=[]
    foam=foam_scope(article)
    if article.get('site')!=('202' if foam else '201') or article.get('sources',{}).get('site')!='user_declared':
        blockers.append('site_201_explicit_required')
    special=extinguisher_scope(article) or foam
    if not special and not re.fullmatch(r'TEST[A-Z0-9_.-]{1,16}',article.get('code_article','')):
        blockers.append('test_article_code_required')
    if article.get('categorie')!='NEG' or article.get('unite')!=('M2' if foam else 'UN'):
        blockers.append('web_test_requires_NEG_UN')
    if not special and (article.get('code_fournisseur') or article.get('fournisseur_nom')):
        blockers.append('supplier_write_mapping_not_supported')
    if (not special and article.get('gestion_stock')) or article.get('gestion_lots'):
        blockers.append('stock_write_mapping_not_supported')
    return blockers


def security():
    ready = settings.sage_powershell_chat_enabled
    return {'ready':ready, 'blockers':[] if ready else ['POWERSHELL_CHAT_DISABLED'],
            'folder':'TEST','transport':'PowerShell 5.1 SOAP', 'required_site':'by_article_scope',
            'individual_approval_required':True, 'article_site_creation':False,
            'scope':'TEST-prefixed codes or exact EXT_POUDRE at 201/UN; exact MFB-A-XPS-40 and MFB-B-XPS-40 at 202/M2 without supplier; TEST/NEG; human approval required'}


def validate_scope(article):
    if not settings.sage_powershell_chat_enabled:
        raise CrudError('powershell_chat_disabled',423)
    foam=foam_scope(article)
    if article.get('site') != ('202' if foam else '201') or article.get('sources',{}).get('site') != 'user_declared':
        raise CrudError('site_201_explicit_required',423)
    special=extinguisher_scope(article) or foam
    if not special and not re.fullmatch(r'TEST[A-Z0-9_.-]{1,16}',article.get('code_article','')):
        raise CrudError('test_article_code_required',422)
    if article.get('categorie') != 'NEG' or article.get('unite') != ('M2' if foam else 'UN'):
        raise CrudError('web_test_requires_NEG_UN',422)
    unsupported=('taux_tva','code_tva','niveau_taxe','code_comptable','compte_general','accounting_category','gestion_lots')
    if not special:unsupported+=('code_fournisseur','fournisseur_nom','gestion_stock')
    if any(article.get(k) for k in unsupported):
        raise CrudError('web_test_extra_fields_not_supported',422)
    if any(article.get(k) and article[k]!=article['unite'] for k in ('unite_achat','unite_vente')):
        raise CrudError('web_test_requires_NEG_UN',422)


def worker(article, mode, **extra):
    validate_scope(article)
    payload={'Mode':mode,'Code':article['code_article'],'Designation':article['designation'],
             'Category':article['categorie'],'Unit':article['unite'],'Site':article['site'],
             'SupplierCode':article.get('code_fournisseur') or '',
             'StockManagement':article.get('gestion_stock') or '',**extra}
    try:
        process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',
                                str(ROOT/'scripts/sage_chat_worker.ps1')],
            input=json.dumps(payload,ensure_ascii=False),capture_output=True,text=True,
            encoding='utf-8',timeout=180)
        if len(process.stdout)>1000000:
            raise ValueError()
        result=json.loads(process.stdout.lstrip('\ufeff'))
        if not result.get('ok'):
            raise CrudError(result.get('code','powershell_worker_failed'),409)
        if process.returncode:
            raise ValueError()
        return result['result']
    except (OSError,ValueError,subprocess.SubprocessError):
        raise CrudError('powershell_outcome_unknown_do_not_retry',503) from None


def sql_verify(article):
    draft=Draft(code_article=article['code_article'],designation=article['designation'],
                categorie=article['categorie'],unite=article['unite'],site=article['site'],
                code_fournisseur=article.get('code_fournisseur') or '')
    result=sql_check(draft)
    if not result.get('ok') or not result.get('category') or not result.get('unit') or not result.get('site'):
        raise CrudError('sql_business_checks_failed',409)
    if article.get('code_fournisseur') and not result.get('supplier'):
        raise CrudError('supplier_not_found',409)
    if foam_scope(article) and not any(str(r.get('LEGCPY_0','')).strip()=='20' for r in result['site']):
        raise CrudError('modern_foam_site_not_in_OULD_BOUAZZA',423)
    return result


def article_hash(article):
    from app.services.conversation_chat import FIELDS
    return digest({k:article.get(k) for k in FIELDS+['reference_interne']})


def write_action(owner, identifier, article_id, action, revision, confirm):
    from app.services import conversation_chat as chat
    if action not in ('prepare','approve','execute'):
        raise CrudError('unknown_action',422)
    # Claim executing and consume approval in a committed transaction BEFORE SOAP.
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True)
        if row['revision']!=revision:
            raise CrudError('stale_revision',409)
        state=row['state']
        article=next((a for a in state['articles'] if a['id']==str(article_id)),None)
        if not article or state.get('_pending') or state.get('workflow')=='cancelled':
            raise CrudError('article_not_ready',409)
        validate_scope(article)
        if not article.get('reviewed') or not article.get('checks',{}).get('valid_basic'):
            raise CrudError('human_review_required',409)
        op=article.get('operation') or {}
        if article.get('outcome') is not None or op.get('status') in ('executing','ambiguous','succeeded','failed','unverified'):
            raise CrudError('existing_attempt_requires_readback_no_retry',409)
        if action=='prepare':
            sql=sql_verify(article)
            if sql.get('article'):
                raise CrudError('duplicate_article_code',409)
            plan=worker(article,'prepare')
            PERMITS.pop(article['id'],None)
            article['approved']=False
            article['operation']={'id':str(uuid4()),'status':'prepared','transport':'PowerShell 5.1',
                'object_xml':plan['ObjectXml'],'digest':plan['Digest'],'plan':plan,'article_hash':article_hash(article)}
        elif action=='approve':
            if not confirm or op.get('status')!='prepared' or op.get('article_hash')!=article_hash(article):
                raise CrudError('specific_confirmation_required',409)
            if article.get('approved'):
                raise CrudError('already_approved',409)
            PERMITS[article['id']]={'owner':str(owner),'hash':article_hash(article),'operation_id':op['id'],
                'expires_at':datetime.now(timezone.utc)+timedelta(minutes=15)}
            article['approved']=True
        else:
            permit=PERMITS.get(article['id'])
            if (not confirm or not article.get('approved') or not permit or permit['owner']!=str(owner)
                    or permit['hash']!=article_hash(article) or permit['operation_id']!=op.get('id')
                    or permit['expires_at']<=datetime.now(timezone.utc)):
                raise CrudError('fresh_specific_approval_required',403)
            sql=sql_verify(article)
            if sql.get('article'):
                raise CrudError('duplicate_article_code',409)
            PERMITS.pop(article['id'],None)
            article['approved']=False
            op['status']='executing'
            approval={'Approved':True,'Folder':'TEST','Site':article['site'],'Code':article['code_article'],
                'Digest':op['plan']['Digest'],'DescriptionHash':op['plan']['DescriptionHash'],
                'Actor':'chat:'+str(owner),'ExpiresAt':permit['expires_at'].isoformat()}
            snapshot=json.loads(json.dumps(article))
        chat.save_conversation_context(conn,owner,identifier,state)
        chat.append(conn,identifier,'system','PowerShell : '+action,
                    {'article_id':str(article_id),'human_confirmation':confirm,'site':'201','retry_allowed':False})
    if action!='execute':
        return chat.read(owner,identifier)
    try:
        result=worker(snapshot,'execute',Plan=snapshot['operation']['plan'],Approval=approval)
    except Exception:
        result={'State':'SAVE_OUTCOME_UNKNOWN','SaveStatus':None,'ReadConfirmed':False,'Messages':[], 'RetryAllowed':False}
    try:
        sql=sql_verify(snapshot)
    except Exception:
        sql={'ok':False,'folder':'TEST','article':[]}
    saved=(sql.get('article') or [{}])[0]
    comparisons={k:str(saved.get(k,'')).strip()==v for k,v in {
        'ITMREF_0':snapshot['code_article'],'ITMDES1_0':snapshot['designation'],'TCLCOD_0':'NEG',
        'STU_0':snapshot['unite'],'PUU_0':snapshot['unite'],'SAU_0':snapshot['unite']}.items()}
    if extinguisher_scope(snapshot):
        comparisons['STOMGTCOD_0']=str(saved.get('STOMGTCOD_0',''))=='1'
        comparisons['supplier_link']=bool(sql.get('supplier_link'))
    confirmed=(result.get('State')=='CREATED_AND_READ_BACK' and result.get('ReadConfirmed') is True
               and sql.get('ok') is True and all(comparisons.values()))
    with db.connection() as conn:
        row=chat.get_row(conn,owner,identifier,True);state=row['state']
        article=next(a for a in state['articles'] if a['id']==str(article_id))
        op=article['operation']
        op.update(status='succeeded' if confirmed else 'ambiguous',
            result={'status':result.get('SaveStatus'),'messages':result.get('Messages',[]),
                    'powershell':result,'retry_allowed':False},
            after_record={'exists':result.get('ReadConfirmed') is True,'status':result.get('ReadStatus')})
        article['outcome']={'confirmed':confirmed,'sql_readback':sql,'comparisons':comparisons,
                            'site_creation_executed':False,'required_site':snapshot['site'],'retry_allowed':False}
        chat.save_conversation_context(conn,owner,identifier,state)
        chat.append(conn,identifier,'assistant',
            ('Création confirmée par PowerShell SOAP READ et SQL : ' if confirmed else
             'Résultat non confirmé, ne pas relancer SAVE : ')+article['code_article'],
            {'article_id':str(article_id),'confirmed':confirmed,'retry_allowed':False})
    return chat.read(owner,identifier)
