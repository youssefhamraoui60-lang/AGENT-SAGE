"""Fast extraction only when the existing controlled state machine is sufficient."""
import re,time
from app.services import chat_turns

def extract(message,state):
    from app.services.chat_model import Delta
    started=time.perf_counter();turn=chat_turns.analyse(message,state)
    # A request to act on an existing draft is not a new extraction or a
    # write authorization. Keep this internal speech act out of Delta's
    # business speech_act enum, as in the existing article request path.
    if turn.kind=='creation_request':
        return Delta(intent='approve'),{'model':None,'real_model_called':False,'route':'existing_draft_creation_request','validation_and_sql_required':True}
    from app.services.chat_article_requests import literal_extract as article_extract
    article=article_extract(message,state)
    if article:
        return article,{'model':None,'real_model_called':False,'route':'literal_article_request_or_presentation','validation_and_sql_required':True}
    from app.services.chat_multi_operations import literal_extract as multi_extract
    multi=multi_extract(message,state)
    if multi:
        return multi,{'model':None,'real_model_called':False,'route':'literal_dependent_operations','fine_tuning':False,'validation_and_sql_required':True}
    supplier_name=re.fullmatch(r'\s*(?:(?:corrige|change|remplace)\s+)?(?:le\s+)?fournisseur\s*(?:(?:est|par|vers)\s+|[:=]\s*)?([^?\n]{1,100})[.]?\s*',message,re.I)
    if state.get('articles') and supplier_name:
        name=supplier_name[1].strip().rstrip('.')
        from app.services.chat_semantics import supplier_decision
        if not supplier_decision(message) and not re.fullmatch(r'F[A-Z0-9_-]*\d[A-Z0-9_-]*',name,re.I) and not re.match(r'(?:code\b|\d+$)',chat_turns.norm(name)) and not re.search(r'\b(?:pas|sans|aucun|optionnel|obligatoire)\b',chat_turns.norm(name)):
            return Delta(intent='update',shared={'fournisseur_nom':name}),{'model':None,'real_model_called':False,'route':'literal_supplier_association_correction','validation_and_sql_required':True}
    from app.services.chat_partners import literal_extract
    partner_delta=literal_extract(message,state)
    if partner_delta:
        return partner_delta,{'model':None,'real_model_called':False,'route':'literal_partner_facts','fine_tuning':False,'validation_and_sql_required':True}
    value=None;route=None;n=chat_turns.norm(message).strip()
    if turn.values.get('categorie') and re.fullmatch(r'[a-z][a-z0-9_-]{0,4}',n):
        value=Delta(intent='update',shared=turn.values);route='pending_category_answer'
    if turn.lookups.get('catalogue_categories'):
        value=Delta(intent='lookup');route='reference_catalogue_request'
    from app.services.chat_semantics import naming_request,supplier_decision
    if state.get('articles') and naming_request(message) and '?' not in message:
        value=Delta(intent='generate');route='user_naming_convention'
    if state.get('articles') and supplier_decision(message)=='optional' and '?' not in message:
        value=Delta(intent='update');route='supplier_optional_declaration'
    if state.get('articles') and re.fullmatch(r'gestion(?:\s+de)?\s+stock\s*[:=]?\s*[123][.!\s]*',n):
        value=Delta(intent='update',shared=turn.values);route='literal_stock_declaration'
    accounting=re.fullmatch(r'\s*(?:catégorie|categorie|famille)\s+comptable\s*[:=]?\s+([^,;\n?!]{1,70})[.\s]*',message,re.I)
    if state.get('articles') and accounting:
        label=accounting[1].strip().rstrip('.')
        value=Delta(intent='update',shared={'accounting_category':label});route='literal_accounting_label'
    if (state.get('articles') or state.get('partners')) and turn.readonly:
        value=Delta(intent='lookup',shared=turn.values,speech_act=turn.kind);route='controlled_speech_act'
    if state.get('articles') and turn.values and re.fullmatch(
        r'\s*(?:(?:pour\s+)?(?:le\s+)?(?:premier|deuxieme|second|troisieme|quatrieme|cinquieme)\s+article\s*[:;,]?\s*|(?:pour\s+)?article\s+(?:20|1[0-9]|[1-9])\s*[:;,]?\s*)?'
        r'(?:(?:change|remplace|corrige|utilise|confirme|retiens)\s+)?(?:le\s+|la\s+)?'
        r'(?:categorie|catigorie|catigorer|categ|cat|unite|site|code\s+articles?|code\s+fournisseur)\s*(?:est\s+|en\s+|[:=]\s*)?[a-z0-9_./-]+'
        r'(?:\s+(?:par|vers|en)\s+[a-z0-9_./-]+)?[.!\s]*',n):
        value=Delta(intent='update',shared=turn.values);route='literal_scalar_correction'
    if (state.get('articles') or state.get('partners')) and re.fullmatch(r'(?:oui|ok|d.accord)[.!\s]*',n):
        value=Delta(intent='update',shared=turn.values);route='scoped_confirmation'
    if state.get('articles'):
        if turn.clear_fields:
            value=Delta(intent='update',shared=turn.values);route='explicit_field_removal'
        elif turn.readonly or turn.restricted:
            value=Delta(intent='lookup',shared=turn.values,speech_act=turn.kind);route='controlled_speech_act'
        elif re.fullmatch(r'(?:\d{2,5}|f[a-z0-9_-]*\d[a-z0-9_-]*)[.\s]*',n) and turn.values:
            value=Delta(intent='update',shared=turn.values);route='explicit_short_value'
        elif re.fullmatch(r'(?:oui|oui merci|ok|d.accord)[.!\s]*',n) and state.get('pending'):
            value=Delta(intent='update',shared=turn.values);route='scoped_confirmation'
        elif re.fullmatch(r'(?:le )?site\s*(?:(?:declare|declaree|retenu|choisi|selectionne)\s+)?(?:est\s*|[:=]\s*)?[a-z0-9_-]{1,5}[.!\s]*',n) and turn.values.get('site'):
            value=Delta(intent='update',shared=turn.values);route='explicit_site'
        elif re.fullmatch(r'(?:oui[, ]+)?(?:utilise|confirme|retiens) (?:la )?categorie [a-z0-9_-]{1,5}[.!\s]*',n) and turn.values.get('categorie'):
            value=Delta(intent='update',shared=turn.values);route='explicit_category_confirmation'
        elif re.fullmatch(r'(?:change|remplace|corrige) (?:le )?site [a-z0-9_-]{1,5} (?:vers|par) [a-z0-9_-]{1,5}[.!\s]*',n) and turn.values.get('site'):
            value=Delta(intent='update',shared=turn.values);route='explicit_site_correction'
        elif re.fullmatch(r'(?:tva|tva souhaitee|tva proposee|tva par defaut)\s*[:=]?\s*(\d{1,2}(?:[.,]\d{1,3})?)\s*%[.\s]*',n):
            rate=re.search(r'(\d{1,2}(?:[.,]\d{1,3})?)\s*%',n)[1].replace(',','.')
            value=Delta(intent='update',shared={'taux_tva':rate});route='explicit_tax_rate'
    if not state.get('articles'):
        from app.services.chat_slash_extract import parse
        declared=parse(message)
        if declared:
            value=Delta(intent='new',articles=declared);route='literal_slash_articles'
        if re.fullmatch(r'(?:bonjour|salut|bonsoir|merci|aide)[!,.\s]*',n):
            value=Delta(intent='other');route='local_greeting'
        # Every numbered line must match the same strict literal grammar. Never
        # accept a partial list or drop an unrecognised clause.
        lines=message.strip().splitlines()
        header=re.fullmatch(r'creer les (\d{1,2}) articles suivants, site ([a-z0-9_-]{1,5})\s*:',chat_turns.norm(lines[0])) if lines else None
        if header and 1<=int(header[1])<=20 and len(lines)==int(header[1])+1:
            articles=[]
            for i,line in enumerate(lines[1:],1):
                numbered=re.fullmatch(r'(\d+)\.\s*(.+)',line.strip())
                if not numbered or int(numbered[1])!=i:break
                parsed=extract('Crée un article '+numbered[2],{})
                if not parsed:break
                delta,_=parsed
                articles.append({**delta.shared.model_dump(exclude_unset=True),**delta.articles[0].model_dump(exclude_unset=True)})
            if len(articles)==int(header[1]):
                value=Delta(intent='new',shared={'site':header[2].upper()},articles=articles);route='literal_numbered_articles'
        # General, fully delimited two-article declarations. Names remain literal;
        # an extra clause, ambiguous "et", or unsupported field goes to Qwen.
        pair=re.fullmatch(r"\s*(?:Bonjour,\s*)?(?:j['’]ai besoin de la création de ces|crée(?:r)?(?: ces)?|prépare(?: ces)?)\s+deux articles\s*:\s*([^.;\n]+)\.\s*(.+?)[.\s]*",message,re.I|re.S)
        if pair:
            names=re.split(r'\s+et\s+',pair[1],flags=re.I)
            fields={};supported=len(names)==2 and all(0<len(x.strip())<=70 for x in names)
            for part in re.split(r'[,;]\s*',pair[2]):
                found=False
                for pattern,key in [(r'(?:catégorie|categorie|cat)\s*[:=]?\s*([A-Z0-9_-]{1,5})','categorie'),
                    (r'(?:unité|unite|u)\s*[:=]?\s*([A-Z0-9]{1,3})','unite'),
                    (r'(?:pour\s+le\s+)?site\s*[:=]?\s*([A-Z0-9_-]{1,5})','site'),
                    (r'(?:fournisseur|FRS)\s*[:=]?\s*([^,;\n?!]{1,100})','fournisseur_nom')]:
                    match=re.fullmatch(pattern,part.strip().rstrip('.'),re.I)
                    if match:
                        raw=match[1].strip();raw=raw if key=='fournisseur_nom' else raw.upper()
                        if key in fields and fields[key]!=raw:supported=False
                        fields[key]=raw;found=True;break
                if not found:supported=False
            if supported:
                supplier=fields.get('fournisseur_nom','')
                if re.fullmatch(r'F[A-Z0-9_-]{1,14}',supplier,re.I) and re.search(r'\d',supplier):
                    fields['code_fournisseur']=fields.pop('fournisseur_nom').upper()
                value=Delta(intent='new',shared=fields,articles=[{'designation':x.strip()} for x in names]);route='literal_two_articles'
        literal=re.sub(r'\s*Aucun envoi sans approbation\.\s*$','',message,flags=re.I)
        m=re.fullmatch(r'\s*(?:(?:Crée|Créer|Prépare|Ajoute)\s+un\s+article|Crée\s+uniquement\s+un\s+brouillon\s+pour)\s+([^,;.\n]+)[,;]\s*(.+?)[.\s]*',literal,re.I|re.S)
        if m and len(m[1].strip())<=70:
            fields={};supported=True
            for part in re.split(r'[,;]\s*',m[2]):
                found=False
                for pattern,key in [(r'(?:catégorie|categorie|cat)\s*[:=]?\s*([A-Z0-9_-]{1,5})','categorie'),
                    (r'(?:unité|unite|u)\s*[:=]?\s*([A-Z0-9]{1,3})','unite'),
                    (r'(?:pour\s+le\s+)?site\s*[:=]?\s*([A-Z0-9_-]{1,5})','site')]:
                    match=re.fullmatch(pattern,part.strip().rstrip('.'),re.I)
                    if match:
                        if key in fields and fields[key]!=match[1].upper():supported=False
                        fields[key]=match[1].upper();found=True;break
                if not found:supported=False
            if supported and fields:
                value=Delta(intent='new',shared=fields,articles=[{'designation':m[1].strip()}]);route='literal_single_article'
    if value is None:return None
    return value,{'model':None,'real_model_called':False,'route':route,'seconds':round(time.perf_counter()-started,6),'fine_tuning':False,'validation_and_sql_required':True}
