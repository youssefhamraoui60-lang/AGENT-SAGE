"""Literal additions to existing article dialogue; no SQL or creation authority."""
import re,copy,unicodedata
from time import monotonic
from uuid import uuid4
from app.services.chat_turns import norm
from app.services import article_sql as sql,sage_crud as crud

def clean_text(text):
    """Strip presentation delimiters without changing identifiers or zeros."""
    return text.replace('`','').replace('**','').replace('\u00a0',' ')


def clean_designation(text):
    value=clean_text(text).strip()
    if len(value)>1 and (value[0],value[-1]) in (("'","'"),('"','"'),('«','»'),('“','”')):value=value[1:-1].strip()
    return re.sub(r'\s+',' ',value)

def separately_named_code(text):
    """A leading identifier is a code only with a separate designation clause."""
    match=re.search(r"\b(?:creer|cree|creation)\s+(?:(?:un|le|l['’])\s*)?article\s+([a-z0-9_-]+)\s*[,;]\s*designation\b",norm(clean_text(text)))
    return match[1].upper() if match and re.search(r'\d',match[1]) else None

def dimensioned_references(text):
    """Literal dimensioned product labels; multiplication signs are data."""
    text=clean_text(text)
    return list(dict.fromkeys(m.group(0).strip() for m in re.finditer(
        r'\b[A-ZÀ-Ÿ][A-ZÀ-Ÿ0-9_-]*(?:[ \t]+[A-ZÀ-Ÿ][A-ZÀ-Ÿ_-]*){0,3}[ \t]+\d+(?:[.,]\d+)?(?:\s*[*x×]\s*\d+(?:[.,]\d+)?){2,3}',text)))

def default_article_code(article):
    """Deterministic proposal only; existing SQL validates and checks duplicates."""
    generated=article.get('code_generation') or {}
    current=article.get('code_article')
    automatic=current==generated.get('code') and article.get('sources',{}).get('code_article')=='category_designation_default'
    if current and not automatic:return current
    category=clean_text(article.get('categorie') or '').strip().upper()
    name=clean_text(article.get('designation') or '').strip()
    if not re.fullmatch(r'[A-Z0-9_]{1,5}',category) or not name:return current
    slug=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().upper()
    slug=re.sub(r'[^A-Z0-9]+','_',slug).strip('_')
    if not slug:return current
    code=(category+'_'+slug)[:20].rstrip('_')
    if code!=current:
        article['operation']={'status':'invalidated'};article['approved']=False
    article['code_article']=code
    article.setdefault('sources',{})['code_article']='category_designation_default'
    article['code_generation']={'code':code,'category':category,'designation':name,'not_reserved':True}
    article.setdefault('field_states',{})['code_article']={'value':code,'status':'proposed','source':'category_designation_default'}
    return code

def recover_declared_batch(state,history):
    """Recover missing local drafts from an explicit email list, never Sage data.

    Only a batch containing an already-present draft is eligible. A later
    cancellation/removal prevents recovery; existing records are never replaced.
    """
    articles=state.get('articles',[])
    if not articles:return 0
    if any(a.get('operation',{}).get('status') in sql.TERMINAL for a in articles):return 0
    later=[]
    for message in reversed(history):
        if message.get('role')!='user':continue
        text=message.get('content','');n=norm(text)
        if re.search(r'\b(?:annul\w*|supprim\w*|retire|enleve)\b',n):return 0
        dimensions=dimensioned_references(text) if re.search(r'\b(?:creer|creation)\b',n) else []
        if not re.search(r'\barticles\s+suivants\b',n) and len(dimensions)<2:later.append(n);continue
        candidates=[]
        if len(dimensions)>=2:
            provider=re.search(r'\bfournisseur\s+(.+?)(?=\s+qui\b|[\n,;]|$)',text,re.I)
            candidates=[{'id':str(uuid4()),'designation':name,'sources':{'designation':'recovered_user_declaration'},'approved':False,'operation':{'status':'invalidated'},**({'fournisseur_nom':provider[1].strip()} if provider else {})} for name in dimensions]
        for segment in re.split(r'[.\n]+',text):
            if not re.search(r',\s*unit[eé]\b',segment,re.I):continue
            name=segment.split(',',1)[0].split(':')[-1].strip()
            if not name or len(name)>70:continue
            candidate={'id':str(uuid4()),'designation':name,'unite':'UN','sources':{'designation':'recovered_user_declaration'},'approved':False,'operation':{'status':'invalidated'}}
            enrich({'articles':[candidate]},segment)
            provider=re.search(r'\bfournisseur\s*:?\s+([^,;\n]+)',segment,re.I)
            if provider and not candidate.get('code_fournisseur'):candidate['fournisseur_nom']=provider[1].strip()
            candidates.append(candidate)
        names={norm(a.get('designation') or '') for a in articles}
        if len(candidates)<2 or not any(norm(a['designation']) in names for a in candidates):return 0
        # The old identity bug could also leave one item's flags on another.
        # Remove only unconfirmed flags absent from that item's literal scope
        # and never mentioned by a later user correction.
        for current in articles:
            declared=next((a for a in candidates if norm(a['designation'])==norm(current.get('designation',''))),None)
            if not declared:continue
            for field,cue in (('gestion_stock','stock'),('achete','achet'),('vendu','vend')):
                if field in current and field not in declared and current.get('field_states',{}).get(field,{}).get('status')!='confirmed' and not any(re.search(r'\b'+cue+r'\w*\b',m) for m in later):
                    current.setdefault('recovered_fields',{})[field]={'previous':current.pop(field),'reason':'not_declared_for_this_article'}
                    current.get('sources',{}).pop(field,None)
        recovered=[a for a in candidates if norm(a['designation']) not in names]
        articles.extend(recovered)
        order={norm(a['designation']):i for i,a in enumerate(candidates)}
        articles.sort(key=lambda a:order.get(norm(a.get('designation','')),len(order)))
        return len(recovered)
    return 0

def initial(text,state):
    from app.services.chat_model import Delta,Patch
    text=clean_text(text);n=norm(text)
    dimensions=dimensioned_references(text)
    if len(dimensions)>=2 and re.search(r'\b(?:creer|creation)\b',n):
        return Delta(intent='new',articles=[Patch(designation=name) for name in dimensions]),text
    if len(state.get('articles',[]))==1 and re.search(r'\b(?:deja|etoiles?|etoile|quprumer)\b',n):
        return Delta(intent='update'),text
    if state.get('articles') and '?' not in text and not re.search(r'\b(?:creer?|creation)\b.*\barticles?\b',n) and not re.search(r'\b(?:nouveau|nouvelle)\s+fournisseur',n):
        if re.match(r'\s*(?:(?:ajoute|ajouter|rajoute|retire|enleve|remplace|zid|avec|pour|les?|la|sans|aucun)\s+)*(?:fournisseurs?|frs|sites?|categorie|unite|taxe|stock|gestion|code\s+article|reference)\b',n):return Delta(intent='update'),text
    if not re.search(r'\b(?:creer?|creation|ajouter?|zid|bghit)\b',n) or re.search(r'\b(?:deux|trois|plusieurs|[2-9])\s+articles?\b|\bet\s+articles?\b',n):return None
    m=re.search(r'\bdesignation\s*[:=]?\s*(.+?)(?=\s+(?:code|categorie|unite|sites?|fournisseurs?|gestion)\s*:|[,;\n]|$)',n)
    if not m:m=re.search(r'\b(?:un\s+|le\s+)?article\s+(.+?)(?=,|;|\n|\s+(?:non\s+gere|gere\s+en|categorie|sites?|pour\s+les\s+sites|avec\s+les?\s+fournisseurs?)\b|$)',n)
    if not m or not 0<len(m[1])<=70 or re.search(r'\b(?:fournisseur\s+et|code\s*:|et)\b',m[1]):return None
    name=text[m.start(1):m.end(1)].strip(' .:')
    if state.get('articles') and any(norm(a.get('designation') or '')==norm(name) for a in state['articles']):return None
    return Delta(intent='new',articles=[Patch(designation=name)]),text

def enrich(state,text,previous=None,grounding_text=None):
    from app.services.chat_article_requests import declared_sites
    text=clean_text(text);n=norm(text);articles=state.get('articles',[])
    if not articles:return
    from app.services.chat_semantics import targets
    selected=targets(text)
    if len(articles)>1 and not selected and not (previous or {}).get('articles'):
        from app.services.chat_semantics import literal_scope
        labels=[a.get('designation') or '' for a in articles]
        for a in articles:
            scope=literal_scope(text,a.get('designation') or '',labels)
            if scope:enrich({'articles':[a]},scope,{'articles':[]},text)
        return
    if len(articles)>1 and not selected:
        if not re.search(r'\b(?:tous|toutes|chaque)\b',n) and previous and previous.get('articles'):return
        selected=list(range(1,len(articles)+1))
    if not selected:selected=[1]
    values={};sites=declared_sites(text)
    reminder=re.search(r'\bcode\s+(?:est\s+)?([a-z0-9_]{1,5})\b',n)
    if reminder and re.search(r'\bdeja\b',n) and any(clean_text(a.get('categorie') or a.get('categorie_libelle') or '').upper()==reminder[1].upper() for a in articles):
        values.update(categorie=reminder[1].upper(),categorie_libelle=None)
    designation=re.search(r'\bdesignation\s*(?:(?:est|c.est)\s+|[:=]\s*)?(.+?)(?=[,;\n]|$)',n)
    if designation:values['designation']=text[designation.start(1):designation.end(1)].strip(' .')
    code=re.search(r'\bcode\s+(?:article\s*)?[:=]\s*([^\s,;]+)',n)
    if code:values['code_article']=text[code.start(1):code.end(1)]
    elif separately_named_code(text):values['code_article']=separately_named_code(text)
    for cue,key in ((r'\bcategorie\s*(?:(?:cest|c.est|est|dois|doit)\s+)?[:=]?\s*(.+?)(?=\s+(?:pas|unite|articles?|code\s+comptable|fournisseurs?|tva|non\s+gere|achete|vendu|sites?)\b|[,;.\n]|$)','categorie'),(r'\bunite(?:r)?\b\s*(?:(?:cest|c.est|est|dois|doit)\s+)?[:=]?\s*([A-Z0-9_]+)','unite'),(r'\bcode\s+comptable\s*(?:(?:cest|c.est|est|dois|doit)\s+)?[:=]?\s*([A-Z0-9_]+)','code_comptable'),(r'\b(?:code\s+taxe|taxe|niveau\s+taxe)\s*[:=]?\s*([A-Z0-9_]+)','code_tva')):
        m=re.search(cue,n,re.I)
        if m:
            value=text[m.start(1):m.end(1)].strip(' .')
            if key=='categorie':
                if re.match(r'^(?:pas|selon|choisie|a verifier)\b',norm(value)):continue
                # A business label is not an invented/truncated category code.
                if re.fullmatch(r'[A-Z0-9_]{1,5}',value,re.I):values[key]=value.upper();values['categorie_libelle']=None
                else:values['categorie_libelle']=value;values['categorie']=None
            else:values[key]=value.upper()
    if values.get('unite') in ('DE','DU','EST','LA','LE'):values.pop('unite',None)
    stock_unit=re.search(r'\b(?:unite|uniter|unter)(?:\s+(?:de\s+)?stock)?\s*(?:(?:est|dois|doit|en)\s+)?[:=]?\s*([a-z0-9_]{1,3})\b',n)
    if stock_unit and stock_unit[1] not in ('de','du','est','la','le'):values['unite']=stock_unit[1].upper()
    sale_unit=re.search(r'\b(?:vente|vent)\s*(?:(?:est|dois|doit|en)\s+)?[:=]?\s*([a-z0-9_]{1,3})\b',n)
    if sale_unit and sale_unit[1] not in ('de','du','est','la','le'):values['unite_vente']=sale_unit[1].upper()
    coefficient=re.search(r'\b(?:coefficient|coeficient|cofission|cofssion|conversion)\s*(?:(?:est|de)\s+)?[:=]?\s*(\d+(?:[.,]\d+)?)\b',n)
    if coefficient and (sale_unit or any(a.get('unite_vente') for a in articles)):
        values['coefficient_vente_declare']=coefficient[1].replace(',','.')
    if re.search(r'\bnon\s+(?:gere\s+en\s+stock|stocke)|\bpas\s+gere\b|\bbla\s+stock\b|\bma\s+kaytstockach\b',n):values['gestion_stock']='1'
    elif re.search(r'\bgere\s+en\s+stock|\bstocke\b|\bmstocki\b|\bkaytstocka\b',n):values['gestion_stock']='2'
    for cue,key in (('achete','achete'),('vendu','vendu'),('fabrique','fabrique'),('livrable','livrable'),('receptionne','receptionne'),('sous.traite','sous_traite')):
        if re.search(r'\b(?:non|pas)\s+'+cue+r'\b',n):values[key]='1'
        elif re.search(r'\b'+cue+r'\b',n):values[key]='2'
    if re.search(r'\bma\s+kaytba3ch\b|\bmachi\s+lbi3\b',n):values['vendu']='1'
    elif re.search(r'\bkaytba3\b|\bkanbi3ouh\b',n):values['vendu']='2'
    if re.search(r'\bkanchriwh\b|\bkaytchra\b',n):values['achete']='2'
    if sites:values['requested_sites']=sites;values['site']=sites[0]
    no_provider=bool(re.search(r'\b(?:sans|aucun|pas\s+de)\s+fournisseurs?\b(?!\s+principal\b)|\baucun\s+frs\b',n))
    provider_clause=re.search(r'\b(?:fournisseurs?|frs)\s*[:=]?\s*(?:par\s+)?((?:f[0-9]+[\s,;/]*(?:et\s+)?)+)',n)
    if no_provider:values.update(fournisseurs=[],code_fournisseur=None,fournisseur_nom=None,fournisseur_principal='',flag_fournisseur='1',supplier_intent='none')
    elif provider_clause:
        codes=list(dict.fromkeys(re.findall(r'\bf[0-9]+\b',provider_clause[1])))
        values['fournisseurs']=[{'code':c.upper(),'reference':''} for c in codes];values['code_fournisseur']=codes[0].upper();values['supplier_intent']='specified'
    for index in selected:
        if not 1<=index<=len(articles):continue
        article=articles[index-1]
        if (article.get('operation') or {}).get('status') in sql.TERMINAL:continue
        before=next((a for a in (previous or {}).get('articles',[]) if a.get('id')==article['id']),copy.deepcopy(article) if previous is None else {})
        unit_proof=article.get('field_provenance',{}).get('unite',{})
        if unit_proof.get('source')=='verified_unit_label' and unit_proof.get('declared_label') and norm(unit_proof['declared_label']) in n:
            values['unite']=unit_proof['value']
        # A partial model response must not clear or replace established facts.
        # Only a literal declaration in this turn may change these fields.
        for key in ('designation','code_article','categorie','categorie_libelle','unite','site','requested_sites','gestion_stock','achete','vendu','fournisseurs','code_fournisseur','supplier_intent','flag_fournisseur'):
            if key not in values and key in before and before[key] is not None:
                article[key]=copy.deepcopy(before[key])
        for key in ('designation','code_article','categorie','categorie_libelle','unite','site'):
            if isinstance(article.get(key),str):article[key]=clean_designation(article[key]) if key=='designation' else clean_text(article[key])
        if 'designation' in values:values['designation']=clean_designation(values['designation'])
        if not re.search(r'\bfamilles?\s+statistiques?\b',n):article['familles_statistiques']=copy.deepcopy(before.get('familles_statistiques'))
        local=copy.deepcopy(values)
        from app.services.article_sites import merge as merge_sites
        merge_sites(article,local,text)
        category_proof=article.get('field_provenance',{}).get('categorie',{})
        if local.get('categorie') is None and local.get('categorie_libelle') and category_proof.get('source')=='verified_category_label' and article.get('categorie')==category_proof.get('reference'):
            from app.services.article_fact_resolution import label
            if label(local['categorie_libelle'])==label(category_proof.get('declared_label','')):
                local.update(categorie=category_proof['reference'],categorie_libelle=category_proof['reference_label'])
        if provider_clause and before:
            prior=copy.deepcopy(before.get('fournisseurs') or ([{'code':before['code_fournisseur'],'reference':before.get('reference_fournisseur') or ''}] if before.get('code_fournisseur') else []))
            if re.search(r'\b(?:retire|enleve)\b',n):local['fournisseurs']=[p for p in prior if p['code'] not in {x['code'] for x in values['fournisseurs']}]
            elif not re.search(r'\b(?:remplace|uniquement|seulement)\b',n):local['fournisseurs']=prior+[p for p in values['fournisseurs'] if p['code'] not in {x['code'] for x in prior}]
            local['code_fournisseur']=local['fournisseurs'][0]['code'] if local['fournisseurs'] else None
            if not local['fournisseurs']:local.update(supplier_intent='none',flag_fournisseur='1',fournisseur_principal='')
        principal=re.search(r'\bfournisseur\s+principal\s*[:=]?\s*(f[0-9]+)',n)
        if principal:local['fournisseur_principal']=principal[1].upper()
        ref=re.search(r'\breference\s+(?:fournisseur\s+)?(f[0-9]+)\s*[:=]\s*([^\s;,]+)',n)
        if ref:
            providers=copy.deepcopy(local.get('fournisseurs') or article.get('fournisseurs') or before.get('fournisseurs') or [])
            for provider in providers:
                if provider['code']==ref[1].upper():provider['reference']=text[ref.start(2):ref.end(2)]
            local['fournisseurs']=providers
        # Model-added provider lists must be grounded in user text or previous facts.
        if article.get('fournisseurs') and not provider_clause and not no_provider:
            known={p['code'] for p in before.get('fournisseurs') or []}
            article['fournisseurs']=[p for p in article['fournisseurs'] if p['code'] in known or re.search(r'\b'+re.escape(p['code'])+r'\b',grounding_text or text,re.I)]
        if any(article.get(k)!=v for k,v in local.items()):article['operation']={'status':'invalidated'};article['approved']=False
        article.update(local);article.setdefault('sources',{}).update({k:'user_declared' for k in local})

def prepare_state(state,text='',previous=None):
    enrich(state,text,previous);messages=[];catalogues={};deadline=monotonic()+90
    for a in state.get('articles',[]):
        if (a.get('operation') or {}).get('status') in sql.TERMINAL:continue
        a['sql_blockers']=[]
        folder=sql.supplier_sql.target(state.get('supplier_target',a.get('dossier_cible','TEST')))
        if a.get('dossier_cible',folder)!=folder:sql.fail('Dossier du brouillon article incoherent.')
        a['dossier_cible']=folder
        try:
            if a.get('taux_tva') and not a.get('code_tva') and not a.get('niveau_taxe'):
                from app.services.article_fact_resolution import resolve
                reference=(state.get('article_reference_choices') or {}).get('tax') or {}
                candidates=reference.get('choices') or []
                if candidates:
                    proposal=resolve('code_tva',candidates[0]['code'],'',state,a,None)
                    if proposal:
                        a['code_tva']=proposal['value'];a['approved']=False;a['reviewed']=False
                        a['operation']={'status':'invalidated'}
                        a.setdefault('sources',{})['code_tva']=proposal['source']
                        a.setdefault('field_provenance',{})['code_tva']=proposal
                        messages.append('Niveau de taxe '+proposal['value']+' proposé depuis le référentiel '+folder+' pour '+str(proposal['rate'])+' %. Son applicabilité reste à vérifier avant confirmation.')
            if monotonic()>deadline:sql.fail('La vérification du lot a atteint son délai. Les données sont conservées ; reprenez la vérification de cette fiche.')
            if not a.get('categorie') and not a.get('categorie_libelle'):
                key=('available_categories',folder)
                if key not in catalogues:catalogues[key]=sql.catalog(folder=folder,require_insert=False)
                categories=catalogues[key].get('categories',[])
                a['category_options']={'folder':folder,'choices':[{'code':sql.text(r.get('TCLCOD_0')),'label':sql.text(r.get('TCLDES_0'))} for r in categories if sql.text(r.get('TCLCOD_0')) and not sql.text(r.get('STOFCY_0')) and r.get('ENAFLG_0',2)==2]}
                choices=list(dict.fromkeys(sql.text(r.get('TCLCOD_0'))+' — '+sql.text(r.get('TCLDES_0')) for r in categories if sql.text(r.get('TCLCOD_0')) and not sql.text(r.get('STOFCY_0')) and r.get('ENAFLG_0',2)==2))
                sql.fail('Quelle catégorie souhaitez-vous retenir pour ces articles ? '+('Catégories existantes dans '+folder+' : '+' ; '.join(choices[:12])+'. Vous pouvez indiquer le code ou décrire la catégorie souhaitée.' if choices else 'La liste des catégories est indisponible ; indiquez le code ou le libellé à rechercher.'))
            if a.get('categorie_libelle') and not a.get('categorie'):
                from app.services.modification_resolvers import CategoryResolver
                wanted=' '.join(CategoryResolver.SYNONYMS.get(w,w) for w in norm(a['categorie_libelle']).split())
                schema=(sql.catalog(folder=folder) if folder!='TEST' else sql.catalog());rows=[r for r in schema['categories'] if not sql.text(r['STOFCY_0']) and (norm(sql.text(r['TCLDES_0']))==wanted or sql.text(r['TCLCOD_0']).upper()==clean_text(a['categorie_libelle']).upper())]
                compatible=[r for r in rows if all(not a.get(f) or int(a[f])==int(r[c]) for f,c in sql.FLAGS.items())]
                if len(compatible)==1:a['categorie']=sql.text(compatible[0]['TCLCOD_0']);a.setdefault('sources',{})['categorie']='verified_label_or_alias_and_business_parameters'
                else:
                    from app.core.config import settings
                    if settings.sage_modification_enabled:
                        from app.services.modification_resolvers import CategoryResolver
                        choices=CategoryResolver().search(a['categorie_libelle'],schema['categories'],{c:int(a[f]) for f,c in sql.FLAGS.items() if a.get(f)},include_incompatible=True)
                        state['category_choices']={'article_id':a['id'],'query':a['categorie_libelle'],'choices':choices,'rejected':[]}
                        state.setdefault('category_choices_by_article',{})[a['id']]=state['category_choices']
                        if choices:sql.fail('Catégories trouvées : '+', '.join(c['code']+' — '+c['label']+(' (incompatible avec les paramètres demandés : '+', '.join({'STOMGTCOD_0':'gestion de stock','PURFLG_0':'achat','SALFLG_0':'vente','STU_0':'unite'}.get(k,k) for k in c['conflicts'])+')' if not c['compatible'] else ' (compatible)') for c in choices)+'. Indiquez le code à retenir et résolvez les éventuelles incompatibilités ; aucune création autorisée.')
                    sql.fail('Précisez le code de la catégorie et ses paramètres : le libellé seul ne permet pas un choix certain.')
            default_article_code(a)
            if not a.get('unite'):sql.fail('Quelle unité de stock souhaitez-vous retenir pour cet article ? Indiquez le code ou le libellé, par exemple UN ou mètre carré. Précisez aussi les unités d’achat et de vente si elles diffèrent. Aucune unité ne sera choisie automatiquement.')
            # Re-read and preview, but never execute physical INSERTs here.
            if (a.get('operation') or {}).get('status') not in ('prepared','approved'):
                schema=None
                if a.get('categorie'):
                    key=(a['categorie'],a.get('gestion_stock') or '0')
                    if key not in catalogues:catalogues[key]=sql.catalog(a['categorie'],int(key[1]),a.get('code_article') or '',folder=folder) if folder!='TEST' else sql.catalog(a['categorie'],int(key[1]),a.get('code_article') or '')
                    schema=catalogues[key]
                    category=next((r for r in schema['categories'] if sql.text(r['TCLCOD_0'])==a['categorie'] and not sql.text(r['STOFCY_0'])),None)
                    if category and int(a.get('vendu') or category['SALFLG_0'])==2:
                        required=sql.supplier_required(a.get('requested_sites') or [a.get('site')])
                        a['flag_fournisseur']='2' if required or a.get('fournisseurs') or a.get('code_fournisseur') else '1'
                        a.setdefault('sources',{})['flag_fournisseur']='sale_supplier_rule'
                    if not any(sql.text(r['TCLCOD_0'])==a['categorie'] for r in schema['categories']):
                        sql.fail('La catégorie déclarée '+a['categorie']+' est absente de '+folder+'. Le brouillon et ses paramètres sont conservés. Choisissez une catégorie existante ou demandez explicitement la préparation d’une nouvelle catégorie.')
                a['operation']=sql.prepare(a,schema=schema);a['approved']=False
            messages.append('La fiche '+str(a.get('designation') or '')+' est preparee dans '+folder+'. Verifiez les sites, fournisseurs et paramètres avant confirmation.')
        except (crud.CrudError,ValueError,TypeError) as exc:
            message=exc.code if isinstance(exc,crud.CrudError) else 'Une information nécessite une précision. Les données restent conservées.'
            a['sql_blockers']=[message];a['operation']={'status':'blocked','transport':'direct_sql_article','message':message};a['approved']=False
            messages.append(message)
    state['pending']=[]
    return '\n\n'.join(dict.fromkeys(messages)) or 'Les fiches et leur résultat sont conservés. Aucune nouvelle création automatique.'

def prepare_missing_category(state,article,schema):
    candidates=[r for r in schema['categories'] if not sql.text(r['STOFCY_0']) and all(article.get(f) is None or int(article[f])==int(r[c]) for f,c in sql.FLAGS.items())]
    preferred=[r for r in candidates if sql.text(r['TCLCOD_0'])==(article.get('modele_categorie') or 'GEN')]
    source=preferred[0] if preferred else candidates[0] if len(candidates)==1 else None
    if not source:sql.fail('Catégorie absente. Précisez un modèle dont les paramètres correspondent au besoin, pas seulement au libellé.')
    existing=next((c for c in state.get('category_drafts',[]) if c['code']==article['categorie']),None)
    if existing:
        article['category_draft_id']=existing['id'];return
    draft={'id':str(uuid4()),'code':article['categorie'],'dossier_cible':article.get('dossier_cible','TEST'),'designation':article.get('categorie_libelle') or article['categorie'],'nom_court':article['categorie'],'modele':sql.text(source['TCLCOD_0']),
      **{field:int(article.get(field) or source[column]) for field,column in sql.FLAGS.items()},'unite':article.get('unite') or sql.text(source['STU_0']),'code_comptable':article.get('code_comptable') or sql.text(source['ACCCOD_0']),'taxe':article.get('code_tva') or sql.text(source['VACITM_0'])}
    state.setdefault('category_drafts',[]).append(draft);article['category_draft_id']=draft['id']
    try:draft['operation']=sql.prepare(draft,'category',schema)
    except crud.CrudError as exc:draft['operation']={'status':'blocked','message':exc.code,'transport':'direct_sql_article'}

def category_turn(text,state):
    n=norm(text)
    if not re.search(r'\bcategorie\b',n):return None
    creation=re.search(r'\b(?:creer?|ajouter?|zid)\s+(?:une\s+)?categorie\s+([a-z0-9_]{1,5})\b',n)
    changed=copy.deepcopy(state)
    if creation:
        code=creation[1].upper();schema=sql.catalog(code)
        existing=[r for r in schema['categories'] if sql.text(r['TCLCOD_0'])==code]
        if existing:return {'state':changed,'reply':'La catégorie '+code+' existe déjà dans TEST. Aucune nouvelle catégorie ne sera créée.'}
        data={'id':'category-request','categorie':code};fake={'articles':[data]};enrich(fake,text)
        data['categorie']=code
        label=re.search(r'\b(?:libelle|designation)\s*:\s*(.+?)(?=\s+(?:modele|unite|code comptable|taxe)\s*:|[;\n]|$)',n)
        if label:data['categorie_libelle']=text[label.start(1):label.end(1)].strip(' .')
        model=re.search(r'\bmodele\s*:?\s*([a-z0-9_]{1,5})',n)
        if model:data['modele_categorie']=model[1].upper()
        prepare_missing_category(changed,data,schema)
        draft=next(d for d in changed['category_drafts'] if d['code']==code)
        reply='La catégorie '+code+' est préparée dans TEST. Relisez son tableau puis confirmez sa création. Aucun article n’est créé automatiquement.' if draft['operation']['status']=='prepared' else draft['operation'].get('message','La catégorie nécessite une précision ; ses informations sont conservées.')
        return {'state':changed,'reply':reply}
    if not re.search(r'\b(?:corrige|corriger|modifie|remplace|rectifie)\b',n):return None
    candidates=[d for d in changed.get('category_drafts',[]) if (d.get('operation') or {}).get('status') not in sql.TERMINAL]
    named=[d for d in candidates if re.search(r'\b'+re.escape(d['code'].casefold())+r'\b',n)]
    if named:candidates=named
    if len(candidates)!=1:return {'state':changed,'reply':'Quelle catégorie souhaitez-vous corriger ? Indiquez son code.'} if candidates else None
    field=next((key for cue,key in ((r'\bnom court\b','nom_court'),(r'\blibelle\b|\bdesignation\b','designation'),(r'\bcode comptable\b','code_comptable'),(r'\btaxe\b','taxe'),(r'\bunite\b','unite'),(r'\bmodele\b','modele')) if re.search(cue,n)),None)
    value=re.search(r'\s*(?::|=)\s*(.+)$',text)
    if not field or not value:return {'state':changed,'reply':'Précisez le paramètre à corriger et sa valeur, par exemple « corrige le libellé de la catégorie : … ».'}
    draft=candidates[0];draft[field]=value[1].strip(' .');draft['approved']=False
    data={k:v for k,v in draft.items() if k not in ('operation','approved')}
    try:draft['operation']=sql.prepare(data,'category')
    except crud.CrudError as exc:draft['operation']={'status':'blocked','message':exc.code}
    return {'state':changed,'reply':'La correction de la catégorie est conservée. Relisez les nouvelles valeurs avant toute confirmation.'}
