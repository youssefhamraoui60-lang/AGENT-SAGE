"""Supplier/customer draft lifecycle. No SAVE, approval, or write connector."""
from copy import deepcopy
from pathlib import Path
import re
from uuid import uuid4
from collections import Counter
from app.schemas.conversation_entities import PartnerPatch
from app.services.chat_turns import norm
from app.services.sage_soap import parse_xml,SageError

ROOT=Path(__file__).resolve().parents[3]
KINDS={'fournisseurs':('supplier','Fournisseur','BPSNUM_0'), 'clients':('customer','Client','BPCNUM_0')}
FIELDS=set(PartnerPatch.model_fields)-{'index'}
ALIASES={'code':'code','code fournisseur':'code','code client':'code','raison sociale':'nom',
         'nom':'nom','nom commercial':'nom_commercial','adresse':'adresse','pays':'pays',
         'devise':'devise','email':'email','courriel':'email','telephone':'telephone',
         'identifiant fiscal':'identifiant_fiscal','conditions de paiement':'conditions_paiement',
         'if':'identifiant_fiscal','dossier':'dossier_cible','categorie':'categorie_fournisseur','categorie fournisseur':'categorie_fournisseur','regime taxe':'regime_taxe',
         'forme juridique':'forme_juridique','capital':'capital','annee de creation':'annee_creation',
         'rc':'rc','ville rc':'ville_rc','ice':'ice',
         'statut':'statut','activation':'statut','actif':'statut','intitule court':'intitule_court','societe':'societe','site':'site','code comptable':'code_comptable'}


ALIASES.update({'ville':'ville','fax':'fax','date regularite':'date_regularite','date de regularite':'date_regularite',
                'nom court':'intitule_court','condition paiement':'conditions_paiement','condition de paiement':'conditions_paiement',
                'conditions paiement':'conditions_paiement','regime de taxe':'regime_taxe',
                'date regularite fiscale':'date_regularite','date de regularite fiscale':'date_regularite',
                'type montant':'type_montant','type montant valeur':'type_montant_valeur','paiement':'conditions_paiement'})

def literal_extract(text,state):
    """Strict labelled facts only; ambiguous free prose stays with the model."""
    from app.services.chat_model import Delta
    from app.services.chat_supplier_preparation import literal_extract as supplier_extract
    supplier=supplier_extract(text,state)
    if supplier:return supplier
    n=norm(text).strip()
    if '?' in n:return None
    create=re.match(r'\s*(?:creer?|prepare|ajoute)\s+(?:(?:un|une|le|les|deux|2)\s+)?(fournisseurs?|clients?)\s*:?\s*',n)
    collection=None;items=[]
    if create:
        collection='fournisseurs' if create[1].startswith('fournisseur') else 'clients'
        body=text[create.end():].strip().rstrip('.')
        parts=re.split(r'[,;]\s*',body)
        names_text=parts.pop(0)
        plural=create[1].endswith('s')
        names=re.split(r'\s+et\s+',names_text,flags=re.I) if plural else [names_text]
        if not names or any(not name.strip() for name in names):return None
        items=[{'nom':name.strip()} for name in names]
    else:
        target=re.match(r'\s*(?:pour\s+)?(?:le\s+)?(fournisseur|client)\s+(10|[1-9])\s*[:;,]\s*',n)
        if target:
            collection='fournisseurs' if target[1]=='fournisseur' else 'clients'
            kind=KINDS[collection][0]
            current=[p for p in state.get('partners',[]) if p['kind']==kind]
            if int(target[2])>len(current):return None
            parts=re.split(r'[,;]\s*',text[target.end():].strip().rstrip('.'))
            items=[{'index':int(target[2])}]
        else:
            return _single_partner_update(text,state)
    return _literal_facts(parts,items,collection,'new' if create else 'update')


def _single_partner_update(text,state):
    # Shared words such as "site" belong to the current article conversation.
    # Updating a partner's site/account requires an explicit partner target.
    if state.get('articles') and re.match(r'\s*(?:site|code\s+fournisseur|code\s+comptable)\b',norm(text)):return None
    kinds={p['kind'] for p in state.get('partners',[])}
    if len(kinds)!=1:return None
    collection='fournisseurs' if next(iter(kinds))=='supplier' else 'clients'
    current=[p for p in state['partners'] if p['kind']==next(iter(kinds))]
    if len(current)!=1:return None
    parts=re.split(r'[,;]\s*',text.strip().rstrip('.'))
    items=[{'index':1}]
    return _literal_facts(parts,items,collection,'update')


def _literal_facts(parts,items,collection,intent):
    from app.services.chat_model import Delta
    facts={}
    for part in parts:
        match=re.fullmatch(r'\s*('+ '|'.join(sorted(ALIASES,key=len,reverse=True)) +r')\s*[:=]?\s+(.+)',norm(part))
        if not match:return None
        # Preserve the original spelling and capitalization of values.
        value=part[match.start(2):match.end(2)].strip()
        key=ALIASES[match[1]]
        if key=='type_montant':value=value.upper()
        if key=='date_regularite':
            from app.services.supplier_dates import normalize_date
            value=normalize_date(value)
        if key=='type_montant_valeur':
            if value not in ('1','2'):return None
            value=int(value)
        if key in facts and facts[key]!=value:return None
        facts[key]=value
    try:
        return Delta(intent=intent,**{collection:[{**item,**facts} for item in items]})
    except ValueError:return None


def metadata(kind):
    # Only observed publication names are used. A customer service is not guessed.
    if kind=='customer':return {'status':'not_observed','publication':None,'required_fields_verified':False}
    path=ROOT/'runtime/crud-WS_FOURNIS-description.xml'
    try:
        root=parse_xml(path.read_bytes())
        if any(root.get(k)!=v for k,v in {'FOL':'TEST','SOL':'V12','PNA':'WS_FOURNIS','OBJ':'BPS'}.items()):raise ValueError()
        required=[g.get('NAM')+'.'+f.get('NAM') for g in root.findall('./ADXDATA/GRP')
                  for f in g.findall('FLD') if f.get('OBL')=='1']
        mapping={}
        for group in root.findall('./ADXDATA/GRP'):
            for field in group.findall('FLD'):
                if field.get('NAM') in ('XICE','XIF','XRC','BPRNAM','BPSNUM','BSGCOD','CUR','PTE','VACBPR','ACCCOD','ENAFLG'):
                    mapping[field.get('NAM')]={'path':group.get('NAM')+'.'+field.get('NAM'),'mode':field.get('MOD'),'length':field.get('LEN')}
        return {'status':'local_description_only','publication':'WS_FOURNIS','required_published_fields':required,
                'folder':'TEST','observed_field_mapping':mapping,
                'required_fields_verified':False,'live_service_verified':False}
    except (OSError,ValueError,SageError):return {'status':'description_unavailable','publication':'WS_FOURNIS','required_fields_verified':False}


def merge(state,delta,text):
    result=deepcopy(state);partners=result.setdefault('partners',[])
    readonly=result.get('last_turn',{}).get('readonly',False)
    if readonly:return result
    for collection,(kind,label,_) in KINDS.items():
        current=[p for p in partners if p['kind']==kind]
        for patch in getattr(delta,collection,[]):
            fields=patch.model_dump(exclude_unset=True,exclude_none=True);index=fields.pop('index',None)
            if index is None and delta.intent=='new':
                noun=r'fournisseurs?' if kind=='supplier' else r'clients?'
                direct=r'\b(?:creer?|ajoute(?:r)?|prepare(?:r)?|nouveau|nouveaux|nouvelle|nouvelles)\s+(?:(?:un|une|ce|le|la|les|des|deux|[1-9]|10)\s+)?(?:nouveau\s+|nouvelle\s+)?(?:fiches?\s+)?'+noun+r'\b'
                coordinated=r'\bet\s+(?:un|une|le|la|des|les)\s+(?:fiches?\s+)?'+noun+r'\b'
                from app.services.chat_multi_operations import canonical
                creation_text=norm(canonical(text))
                explicit=bool(re.search(direct,creation_text)) or bool(re.search(r'\b(?:creer?|ajoute|prepare)\b',creation_text) and re.search(coordinated,creation_text))
                if kind=='supplier':
                    from app.services.supplier_multiturn import creation_declared
                    explicit=explicit or creation_declared(text)
                if kind=='supplier' and re.search(r'\b(?:creation\s+(?:du|d.un|de|d.une)|nouvelle fiche)\s+fournisseur\b',creation_text):explicit=True
                if not explicit:
                    result.setdefault('turn_clarifications',[]).append(f'Souhaitez-vous créer une nouvelle fiche {label.lower()} ou utiliser une fiche existante ?')
                    continue
            if index is not None and len(current)>1:
                from app.services.chat_semantics import ORDINALS
                words='fournisseur' if kind=='supplier' else 'client'
                mentioned=bool(re.search(r'\b'+words+r'\s+(?:n[°o]?\s*)?'+str(index)+r'(?!\d)',norm(text)))
                mentioned=mentioned or any(i==index and re.search(r'\b'+ordinal+r'\s+'+words+r'\b',norm(text)) for ordinal,i in ORDINALS.items())
                named=[i for i,p in enumerate(current,1) if p.get('nom') and norm(p['nom']) in norm(text)]
                if not mentioned and named!=[index]:
                    result['turn_clarifications']=[f'Quel {label.lower()} souhaitez-vous modifier ? Indiquez son numéro ou son nom.']
                    continue
            if index is None and delta.intent!='new':
                matches=[i for i,p in enumerate(current,1) if fields.get('nom') and norm(p.get('nom',''))==norm(fields['nom'])]
                if len(matches)==1:index=matches[0]
                elif len(current)==1:index=1
                else:
                    result['turn_clarifications']=[f'Quel {label.lower()} souhaitez-vous modifier ? Indiquez son numéro ou son nom.']
                    continue
            if index is not None:
                if index>len(current):
                    result['unapplied_partner_patch']={'kind':kind,'fields':fields,'reason':'invalid_partner_target'}
                    result.setdefault('turn_clarifications',[]).append('Aucun brouillon '+label.lower()+" ne correspond à cette réponse. Précisez son nom ; les informations reçues sont conservées.")
                    continue
                item=current[index-1]
            else:
                if not fields.get('nom'):raise ValueError('partner_name_required')
                if norm(fields['nom']) not in norm(text):raise ValueError('partner_name_not_grounded')
                if len(current)>=10:raise ValueError('maximum_ten_partners_per_kind')
                repeated=[p for p in current if fields.get('ice') and p.get('ice')==fields['ice'] and norm(p.get('nom',''))==norm(fields['nom'])]
                if len(repeated)==1:item=repeated[0]
                else:
                    item={'id':str(uuid4()),'kind':kind,'sources':{},'field_states':{},'history':[],'reviewed':False}
                    partners.append(item);current.append(item)
            operation=item.get('operation') or {}
            if operation.get('status') in ('executing','ambiguous','unverified','succeeded','failed') and any(item.get(k)!=v for k,v in fields.items()):
                result.setdefault('turn_clarifications',[]).append('Une tentative fournisseur existe : relisez son résultat avant de modifier cette fiche. Aucune nouvelle création automatique.')
                continue
            changes=[]
            for field,value in fields.items():
                # Literal grounding prevents invented contact and fiscal values.
                explicit=norm(str(value)) in norm(text)
                if field=='date_regularite' and not explicit:
                    from app.services.supplier_dates import normalize_date
                    for date_match in re.finditer(r'\bdate\s+(?:de\s+)?regularite(?:\s+fiscale)?\s*[:=]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.-]\d{2}[/.-]\d{4})',norm(text)):
                        try:explicit=normalize_date(date_match[1])==value
                        except ValueError:continue
                        if explicit:break
                if field in ('code','code_comptable','identifiant_fiscal','societe','site','pays','devise','conditions_paiement','statut','forme_juridique','capital','annee_creation','rc','ville_rc','ice','dossier_cible','categorie_fournisseur','regime_taxe','type_montant','type_montant_valeur'):
                    cues=[alias for alias,key in ALIASES.items() if key==field]
                    explicit=bool(re.search(r'\b(?:'+ '|'.join(map(re.escape,cues)) +r')\b\s*(?:est\s+|en\s+|[:=]\s*)?[«"\']?'+re.escape(norm(str(value)))+r'(?!\w)',norm(text)))
                    if field=='ville_rc':explicit=explicit or bool(re.search(r'\brc\b\s*[:=]?\s*[\w/-]+\s*\('+re.escape(norm(value))+r'\)',norm(text)))
                    if field=='dossier_cible':explicit=explicit or bool(re.search(r'\bdans\s+'+re.escape(norm(value))+r'\b',norm(text)))
                if not explicit and value!=item.get(field):
                    result.setdefault('rejected_values',[]).append({'kind':kind,'field':field,'reason':'not_explicit_in_message'})
                    continue
                if value==item.get(field):continue
                changes.append({'field':field,'before':item.get(field),'after':value})
                item.setdefault('field_states',{})[field]={'value':value,'previous':item.get(field),'status':'declared','source':'user_declared'}
                item[field]=value;item['sources'][field]='user_declared';item['reviewed']=False
                item.setdefault('document_sources',{}).pop(field,None)
            if changes:
                item['history']=(item.get('history',[])+[{'changes':changes,'source':'user_turn'}])[-100:]
                if operation.get('status') in ('prepared','approved','blocked'):
                    operation['status']='invalidated';item['approved']=False
    return result


def tool_plan(state,plan):
    bindings={}
    for p in state.get('partners',[]):
        tool='search_suppliers' if p['kind']=='supplier' else 'search_customers'
        if p['kind']=='supplier':
            folder=p.get('dossier_cible') or 'TEST'
            fiscal=plan.add('check_supplier_fiscal_duplicates',Folder=folder,Label=p.get('nom',''),Supplier=p.get('code') or '',Ice=p.get('ice') or '',Fiscal=p.get('identifiant_fiscal') or '',Rc=p.get('rc') or '')
            bindings[p['id']]={'fiscal':fiscal,'profile':plan.add('get_supplier_preparation_profile',Folder=folder,Category=p.get('categorie_fournisseur') or 'FR'),
                'name':plan.add(tool,Label=p.get('nom',''),Supplier='') if folder=='TEST' else fiscal,
                'code':(plan.add(tool,Label='',Supplier=p['code']) if folder=='TEST' else fiscal) if p.get('code') else None}
        else:
            bindings[p['id']]={'name':plan.add(tool,Label=p.get('nom',''),Supplier=''),
                               'code':plan.add(tool,Label='',Supplier=p['code']) if p.get('code') else None}
    return bindings


def validate(state,results,bindings):
    result=deepcopy(state)
    codes=Counter((p['kind'],p['code'].casefold()) for p in result.get('partners',[]) if p.get('code'))
    for p in result.get('partners',[]):
        errors=[];refs=bindings.get(p['id'],{})
        name=results.get(refs.get('name'),{'ok':False,'rows':[]})
        code=results.get(refs.get('code'),{'ok':False,'rows':[]}) if p.get('code') else None
        if not p.get('nom'):errors.append('missing:nom')
        if p.get('code') and not re.fullmatch(r'[A-Za-z0-9_-]{1,15}',p['code']):errors.append('invalid_partner_code')
        if p.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',p['email']):errors.append('invalid_email')
        if not name.get('ok') or (code is not None and not code.get('ok')):errors.append('sql_checks_incomplete')
        if code and any(str(r.get('BPSNUM_0') or r.get('BPCNUM_0') or r.get('BPRNUM_0') or '').strip().upper()==p['code'].upper() for r in code.get('rows',[])):errors.append('duplicate_partner_code')
        if p.get('code') and codes[(p['kind'],p['code'].casefold())]>1:errors.append('duplicate_partner_code_in_drafts')
        name_rows=name.get('rows',[])
        exact_name=any(norm(str(r.get('BPSNAM_0') or '').strip())==norm(p.get('nom','').strip()) or norm(str(r.get('BPRNAM_0') or '').strip())==norm(p.get('nom','').strip()) for r in name_rows)
        if name_rows and p['kind']!='supplier':errors.append('similar_partner_requires_review')
        description=metadata(p['kind']) if p.get('dossier_cible')!='OB' else {'status':'OB_read_only_publication_not_inspected','folder':'OB','required_fields_verified':False}
        p['checks']={'errors':errors,'valid_basic':not errors,'tools':{'name':name,'code':code},
                     'publication':description,'creation_ready':False,'sage_created':False,
                     'creation_blockers':['published_mapping_and_business_rules_review_required'],
                     'source':'controlled_SQL_TEST' if name.get('source')=='SQL TEST' else 'simulation_or_unverified'}
        if p['kind']=='supplier':
            from app.services.chat_supplier_preparation import prepare
            prepare(p,{k:results.get(refs.get(k),{'ok':False,'rows':[]}) for k in ('fiscal','profile')})
            p['preparation']['near_names']=[{'code':str(r.get('BPSNUM_0') or r.get('BPRNUM_0') or '').strip(),'name':r.get('BPSNAM_0') or r.get('BPRNAM_0')} for r in name_rows] if not exact_name else []
            blocking=[e for e in p['preparation']['errors'] if e not in ('target_supplier_rules_unavailable','OB_read_only_no_creation')]
            p['checks']['errors']=sorted(set(errors+blocking));p['checks']['valid_basic']=not p['checks']['errors']
            p['checks']['creation_blockers']+=p['preparation']['errors']
            p['checks']['tools'].update({k:results.get(refs.get(k),{'ok':False,'rows':[]}) for k in ('fiscal','profile')})
            fiscal_source=p['checks']['tools']['fiscal'].get('source')
            if fiscal_source in ('SQL OB','SQL TEST'):p['checks']['source']='controlled_'+fiscal_source.replace(' ','_')
    return result


def compose(state):
    lines=list(state.get('turn_clarifications',[]))
    if state.get('last_turn',{}).get('creation_requested'):
        lines.append("Votre demande de création est comprise. Les brouillons et leurs vérifications sont conservés ; ce message ne déclenche aucune écriture Sage. Les blocages ci-dessous doivent être résolus avant toute approbation de création.")
    for p in state.get('partners',[]):
        label='Fournisseur' if p['kind']=='supplier' else 'Client'
        lines.append(f"{label} — {p.get('nom','À préciser')} : brouillon conservé, aucune création exécutée.")
        for name in sorted(FIELDS):
            if p.get(name):lines.append(f"- {name.replace('_',' ')} : {str(p[name]).replace(chr(10),' ')}")
        errors=p.get('checks',{}).get('errors',[])
        if 'sql_checks_incomplete' in errors:lines.append('Consultation indisponible : existence non vérifiée.')
        if 'duplicate_partner_code' in errors:lines.append('Ce code existe déjà : nouvelle création bloquée.')
        if 'similar_partner_requires_review' in errors:lines.append('Des fiches proches existent ; il faut lever le risque de doublon.')
        prep=p.get('preparation')
        if prep:
            if prep.get('near_names'):lines.append('Noms proches dans la recherche élargie, sans doublon exact confirmé : '+ '; '.join(str(r['code'])+' — '+str(r.get('name') or '') for r in prep['near_names'][:5])+'. Ces ressemblances seules ne prouvent pas un doublon fiscal.')
            lines.append('Préparation SQL fournisseur dans '+prep['target_folder']+' ; modèle OB.F103 lu par la requête enregistrée, écritures uniquement dans TEST.')
            for duplicate in prep['duplicates']:
                if 'supplier_inactive' in duplicate.get('issues',[]):lines.append('Attention : fournisseur '+duplicate['code']+' inactif dans '+duplicate['folder']+' (BPSUPPLIER.ENAFLG=1). Le statut du tiers est contrôlé séparément.')
                if any(x.endswith('name_differs_from_request') for x in duplicate.get('issues',[])):lines.append('Le nom enregistré pour '+duplicate['code']+' diffère du nom demandé. Aucune correction automatique de cette fiche existante.')
                lines.append('Avertissement '+duplicate['folder']+' : '+duplicate['code']+' — '+str(duplicate.get('name') or '')+' ; champs concordants : '+', '.join(duplicate['matched_fields'])+'. Une nouvelle fiche dans TEST nécessite votre confirmation explicite malgré ces correspondances.')
            if prep['target_folder']=='OB':lines.append('OB est exclusivement en lecture seule : aucune création ou modification proposée.')
            proposal=prep.get('code_proposal')
            if prep.get('activation_requested'):lines.append('Activation demandée : Oui. Elle devra être confirmée après enregistrement dans la fiche fournisseur et le tiers ; le brouillon ne prouve aucune activation.')
            if proposal:lines.append('Code proposé dans TEST : '+proposal['code']+', absent lors du contrôle, non réservé. Convention observée à confirmer ; ce n’est pas un numéro officiellement alloué par Sage.')
            if prep['suggested_defaults']:lines.append('Valeurs du dossier cible à confirmer, non appliquées : '+' ; '.join(k+'='+v['value'] for k,v in prep['suggested_defaults'].items())+'.')
            if not prep['duplicates'] and prep['target_folder']=='TEST':lines.append('Confirmez les valeurs proposées et complétez les champs manquants avant la préparation définitive. Cette confirmation conversationnelle ne déclenche aucune création Sage.')
            lines.append('ICE, IF et RC sont contrôlés en format et rapprochés du référentiel ; aucune validation auprès d’une autorité fiscale n’est revendiquée. Une confirmation humaine des données exactes sera requise après résolution des blocages et validation du mapping d’écriture.')
        if p['kind']=='supplier':
            missing=(prep or {}).get('missing_sql_fields',[])
            if missing:lines.append('Champs SQL à compléter : '+', '.join(missing)+'.')
            lines.append('Relisez le brouillon, puis préparez la requête SQL. Le bouton d’approbation confirme les paramètres affichés avant exécution dans TEST ; le code F + 1 est calculé automatiquement.')
        if p['kind']=='customer':lines.append('Aucune publication SOAP client vérifiée dans les descriptions disponibles ; diagnostic de publication requis.')
    return '\n\n'.join(lines)
