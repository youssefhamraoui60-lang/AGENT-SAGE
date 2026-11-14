from difflib import SequenceMatcher
import re
import unicodedata
import json
from pathlib import Path
from app.schemas.business import Proposal
from app.core.config import settings

def configuration():
    config=json.loads(Path(settings.business_rules_file).read_text(encoding='utf-8'))
    article_fields={'designation','unite','categorie','famille','fournisseur','code_fournisseur','code_article','site'}
    if not set(config['article_required_fields'])<=article_fields:
        raise ValueError('Unsupported article rule field')
    if any(not re.fullmatch(r'nom|code_fournisseur|informations\.[a-zA-Z_]+',field) for field in config['supplier_required_fields']):
        raise ValueError('Unsupported supplier rule field')
    if type(config['deployment_validated']) is not bool: raise ValueError('Invalid deployment rules validation')
    return config

def normalize(text):
    text=unicodedata.normalize('NFKD',text or '').casefold()
    text=''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+',text))

def matches(value,row):
    return value is not None and normalize(value) in {normalize(x) for x in [row['code'],row['label'],*row['aliases']]}

def duplicate_candidates(label,refs,kind='article',limit=5):
    found=[]
    for row in refs:
        if row['kind']!=kind: continue
        exact=label==row['label']
        normalized=normalize(label)==normalize(row['label'])
        score=1.0 if normalized else SequenceMatcher(None,normalize(label),normalize(row['label'])).ratio()
        if score>=0.55:
            found.append({'code':row['code'],'designation':row['label'],'score':round(score,4),
                'correspondance':'exact' if exact else ('normalized' if normalized else 'approximate'),
                'source':row['provenance'],'scope':'local_only'})
    return sorted(found,key=lambda x:(-x['score'],x['code']))[:limit]

def evaluate(proposal: Proposal,refs):
    config=configuration()
    articles=[]
    suppliers=[]
    for item in proposal.articles:
        data=item.model_dump()
        missing=[name for name in config['article_required_fields'] if data[name] is None]
        errors=['missing:'+name for name in missing]
        confirmed={}
        sources={}
        warnings=['local_references_only','human_approval_required']
        for field,kind in [('unite','unit'),('categorie','category'),('famille','family'),('site','site')]:
            if data[field] is None: continue
            rows=[r for r in refs if r['kind']==kind and matches(data[field],r)]
            if len(rows)==1:
                confirmed[field]=rows[0]['code'];sources[field]=rows[0]['provenance']
            else: errors.append('unknown_or_ambiguous:'+field)
        candidates=[r for r in refs if r['kind']=='supplier' and (
            (data['code_fournisseur'] is not None and r['code']==data['code_fournisseur']) or
            (data['code_fournisseur'] is None and matches(data['fournisseur'],r)))]
        if len(candidates)==1 and (data['fournisseur'] is None or matches(data['fournisseur'],candidates[0])):
            confirmed['code_fournisseur']=candidates[0]['code'];sources['code_fournisseur']=candidates[0]['provenance']
        else: errors.append('supplier_unresolved')
        duplicates=duplicate_candidates(data['designation'] or '',refs)
        if duplicates:
            warnings.append('possible_local_duplicate')
            errors.append('duplicate_review_required')
        articles.append({'extrait':data,'confirme':confirmed,'sources_confirmation':sources,
            'statut_validation':'ready_for_human_review' if not errors else 'needs_information',
            'champs_manquants':missing,'erreurs':errors,'avertissements':warnings,'doublons':duplicates})
    for item in proposal.fournisseurs:
        data=item.model_dump()
        missing=[]
        for field in config['supplier_required_fields']:
            value=data['informations'].get(field.split('.',1)[1]) if field.startswith('informations.') else data[field]
            if not value: missing.append(field)
        errors=['missing:'+name for name in missing]
        confirmed={}
        if data['code_fournisseur'] is not None:
            candidates=[r for r in refs if r['kind']=='supplier' and r['code']==data['code_fournisseur']]
            if len(candidates)!=1 or (data['nom'] and not matches(data['nom'],candidates[0])):
                errors.append('supplier_code_unverified')
            else: confirmed['code_fournisseur']=candidates[0]['code']
        duplicates=duplicate_candidates(data['nom'] or '',refs,'supplier')
        if duplicates: errors.append('duplicate_review_required')
        suppliers.append({'extrait':data,'confirme':confirmed,'champs_manquants':missing,
            'statut_validation':'ready_for_human_review' if not errors else 'needs_information',
            'erreurs':errors,'avertissements':['deployment_rules_not_validated'] if not config['deployment_validated'] else ['human_approval_required'],
            'doublons':duplicates})
    if not config['deployment_validated']:
        for item in articles+suppliers:
            item['erreurs'].append('deployment_rules_not_validated')
            item['statut_validation']='needs_information'
    meaningful=bool(articles or suppliers)
    all_valid=meaningful and not proposal.ambigu and proposal.intention in ('create_article','create_supplier') and all(
        not item['erreurs'] for item in articles+suppliers)
    return {'articles':articles,'fournisseurs':suppliers,'business_valid':all_valid,
        'scope':'local_only','sage_x3_checked':False,'execution_sage_autorisee':False,
        'reference_count':len(refs),'reference_status':'configured' if refs else 'empty',
        'questions':proposal.questions,'ambigu':proposal.ambigu,
        'rules_version':config['version'],'rules_validated':config['deployment_validated'],'rules_provenance':config['provenance']}
