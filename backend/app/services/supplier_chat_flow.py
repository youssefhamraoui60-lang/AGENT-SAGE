"""Deterministic supplier turns and read-only SQL preparation. No execution."""
import re
from html import unescape
from app.services.chat_turns import norm
from app.services import supplier_sql as sql,sage_crud as crud

def strip_missing_fiscal_note(text):
    """Separate a trailing absence statement from a field value, without inventing IDs."""
    match=re.search(r"\s+je\s+n['’]ai\s+pas\s+(?:encore\s+)?(?:son|mon|le|l['’])?\s*(?:ice|if|rc)\b[\s\S]*$",text,re.I)
    if match:
        # Only consume a list of missing fiscal identifiers, never additional data.
        tail=text[match.start():]
        words=re.sub(r"[.,;:'’]",' ',tail.casefold()).split()
        if all(w in {'je','n','ai','pas','encore','son','mon','le','l','ice','if','rc','ni','et','de','d'} for w in words):
            return text[:match.start()].rstrip()
    return text

def extract(text,state,history=()):
    # Canonicalize the label before narrative parsers can mistake the request
    # introduction ("fournisseur suivant dans le système") for its actual name.
    text=re.sub(r'\bnom\s+(?:de\s+frs|de\s+fournisseur|du\s+fournisseur|fournisseur)\s*:', 'Nom :',text,flags=re.I)
    # Email signatures are not the value of the last declared business field.
    # Remove the conventional sentence only; keep any following labelled data.
    text=re.sub(r'\bje\s+reste\s+[aà]\s+votre\s+disposition\s+pour\s+toute\s+information\s+compl[eé]mentaire\s*[.!]?', '',text,flags=re.I)
    text=re.sub(r'\s+(?:bien\s+)?cordialement\s*[.!\s]*$','',text,flags=re.I)
    from app.services.supplier_fiscal_slashes import extract as fiscal_slashes
    slash_form=fiscal_slashes(text,state,history)
    if slash_form:return slash_form
    # A pasted supplier form prepares a draft; it is never a write approval.
    form=re.match(r'^\s*(?:(?:bonjour|bonsoir|salut)\s*[,!:.]?\s*)?(?:frs|fournisseur)\s*:\s*',norm(text))
    if form and not state.get('articles'):
        text='Créer un fournisseur\nNom : '+text[form.end():]
        text=re.sub(r'\s+(?:bien\s+)?cordialement\s*[.!\s]*$','',text,flags=re.I)
    from app.services.chat_multi_operations import literal_extract as mixed_extract
    mixed=mixed_extract(text,state)
    if mixed:
        existing=state.get('partners',[])
        if len(existing)==1 and existing[0].get('kind')=='supplier' and len(mixed.fournisseurs)==1:
            old=existing[0]
            contaminated=re.match(re.escape(norm(mixed.fournisseurs[0].nom))+r'\s+et\s+(?:(?:les|des)\s+)?articles?\s*:',norm(old.get('nom') or ''))
            if contaminated and (old.get('operation') or {}).get('status') in (None,'prepared','blocked','invalidated'):
                mixed.fournisseurs[0].index=1
        return mixed,text
    if re.search(r'\bet\s+(?:(?:les|des)\s+)?articles?\s*:',norm(text)):return None
    from app.services.supplier_discourse import language_clarification
    if language_clarification(text):return None
    from app.schemas.conversation_entities import SupplierPatch as PartnerPatch
    from app.services.chat_model import Delta
    from app.services.chat_partners import ALIASES,literal_extract
    from app.services.supplier_noisy_language import extract as noisy_extract
    labelled_name=bool(re.search(r'\b(?:nom|raison\s+sociale)\s*:',norm(text)))
    noisy=None if labelled_name else noisy_extract(text,state)
    if noisy:return noisy
    # Separate an unlabelled payment clause from the preceding fiscal identifier.
    text=re.sub(r'\s+(?:et\s+)?paiement\s+(?:par\s+)?(?=(?:ch[eè]que|effet|virement)\b)', '\nPaiement : ',text,flags=re.I)
    from app.services.chat_turns import SUPPLIER_WORD
    # Recognize common supplier spelling variants in the request introduction.
    text=re.sub(r'\b((?:cr[eé]er?|ajouter?|pr[eé]pare)\s+(?:(?:le|les|un|une|nouveau|nouvelle)\s+)*)'+SUPPLIER_WORD+r's?\b',lambda m:m[1]+'fournisseur',unescape(text),count=1,flags=re.I)
    suppliers=[p for p in state.get('partners',[]) if p.get('kind')=='supplier']
    if len(suppliers)==1 and not state.get('articles'):
        from app.services.supplier_language import extract_followup
        followup=extract_followup(text)
        if followup:return followup
        update=re.fullmatch(r"\s*(?:ajoute|ajouter|rajoute|renseigne|corrige|modifie|remplace|compl[eè]te)\s+(?:l['’]\s*|(?:le|la|son|sa)\s+)?("+'|'.join(map(re.escape,sorted(ALIASES,key=len,reverse=True)))+r")\s*(?::|=|\bpar\b|\best\b)?\s+(.+?)\s*[.!]?\s*",norm(text))
        if update:
            field=ALIASES[update[1]]
            value=text[update.start(2):update.end(2)].strip().rstrip('.')
            if field=='type_montant':value=value.upper()
            if field=='date_regularite':
                from app.services.supplier_dates import normalize_date
                value=normalize_date(value)
            try:patch=PartnerPatch.model_validate({'index':1,field:value})
            except ValueError:return None
            return Delta(intent='update',fournisseurs=[patch]),update[1]+' : '+str(value)
    from app.services.supplier_language import extract_request
    multilingual=None if labelled_name else extract_request(text)
    if multilingual:return multilingual
    text=strip_missing_fiscal_note(unescape(text))
    # An explicit correction in the same message supersedes the initial name.
    correction=re.search(r'\b(?:attention,?\s*)?correction\s*:\s*la\s+raison\s+sociale\s+exacte\s+est\s+([^,.\n]+),\s*pas\s+([^.!\n]+)[.]?',text,re.I)
    if correction:
        corrected=correction[1].strip()
        text=text[:correction.start()]+'\n'+text[correction.end():]
        # Replace the initial explicit name only; do not carry its rejected value.
        initial=re.search(r'(\bfournisseur\s+)([^.!\n]+)',text,re.I)
        if initial and norm(initial[2].strip())==norm(correction[2].strip()):
            text=text[:initial.start(2)]+corrected+text[initial.end(2):]
        else:
            text+='\nNom : '+corrected
    text=re.sub(r'\bLe\s+paiement\s+est\s+par\s+(virement|effet|ch[eè]que)\s+[aà]\s+(\d+)\s+jours\s+et\s+les\s+montants\s+sont\s+(HT|TTC)[.]?',
        lambda m:'\nPaiement : '+m[1]+' '+m[2]+' jours\nType montant : '+m[3],text,flags=re.I)
    text=re.sub(r'\s+merci\s+de\s+prendre\s+uniquement\s+les\s+informations\s+corrig[eé]es[.!\s]*$','',text,flags=re.I)
    # Frequent Darija/French business phrasing; retain the user's actual values.
    text=re.sub(r'\bzid\s+lina\s+fournisseur\s+jdid\s+smitou\s+', 'Créer un fournisseur\nNom : ',text,flags=re.I)
    text=re.sub(r'\bICE\s+dyalou\s+', '\nICE : ',text,flags=re.I)
    def location_clause(match):
        parts=re.split(r'\s+(?=(?:route|rue|avenue|boulevard|zone)\b)',match[1].strip(),maxsplit=1,flags=re.I)
        return '\nVille : '+parts[0]+('\nAdresse : '+parts[1] if len(parts)==2 else '')
    text=re.sub(r'\bkayn\s+f\s+([^,.\n]+)',location_clause,text,flags=re.I)
    text=re.sub(r'\.?\s*bghit\s+paiement\s+b\s+', '\nPaiement : ',text,flags=re.I)
    text=re.sub(r'\.?\s*les\s+autres\s+param[eè]tres\s+khalihom\s+standard\s+bhal\s+les\s+fournisseurs\s+li\s+3andna[.\s]*', '\n',text,flags=re.I)
    # Turn explicit narrative clauses into the same labelled extraction path.
    # Keep values literal; only normalize verified reference descriptions later.
    text=re.sub(r"\bil\s+s['’]agit\s+de\s+",'\nNom : ',text,flags=re.I)
    text=re.sub(r',?\s*situ[eé]\s+[aà]\s+([^,.\n]+),\s*([^\n]+?)(?=\.\s|\n|$)',
        lambda m:'\nVille : '+m[1].strip()+'\nAdresse : '+m[2].strip(),text,flags=re.I)
    text=re.sub(r'\.\s*le\s+r[eè]glement\s+se\s+fera\s+par\s+([a-zéèê]+)\s+[aà]\s+(\d+)\s+jours[.]?',
        lambda m:'\nPaiement : '+m[1]+' '+m[2]+' jours\n',text,flags=re.I)
    text=re.sub(r'\bson\s+(?:num[eé]ro\s+)?(ICE|IF|RC)\s+(?:est\s+)?',lambda m:'\n'+m[1]+' : ',text,flags=re.I)
    text=re.sub(r'\.?\s*je\s+souhaite\s+que\s+les\s+montants\s+soient\s+en\s+(HT|TTC)\s+et\s+que\s+la\s+devise\s+soit\s+(?:le\s+)?([^.!\n]+)[.]?',
        lambda m:'\nType montant : '+m[1]+'\nDevise : '+m[2],text,flags=re.I)
    text=re.sub(r'\s+merci\s+de\s+faire\s+le\s+n[eé]cessaire[.!\s]*$','',text,flags=re.I)
    text=re.sub(r'(?i)(\bDevise\s*:\s*)dirham\s+marocain\b',r'\1MAD',text)
    # Common conversational supplier requests, without asking users for labels.
    if re.search(r'\b(?:frs|fournisseur)\b',text,re.I):
        text=re.sub(r'\bfrs\b','fournisseur',text,flags=re.I)
        text=re.sub(r'\bcr[eé]e\s+moi\s+', 'créer ',text,flags=re.I)
        text=re.sub(r"\bson\s+nom\s+c['’]est\s+",'\nNom : ',text,flags=re.I)
        text=re.sub(r'\bson\s+nom\s+(?!:)', '\nNom : ',text,flags=re.I)
        text=re.sub(r'\bil\s+est\s+[aà]\s+','\nVille : ',text,flags=re.I)
        text=re.sub(r'\bil\s+habite\s+[aà]\s+([^,.\n]+?)(?=\s+(?:telephone|téléphone|tel|paiement|paiment)\b|[,.\n]|$)',location_clause,text,flags=re.I)
        text=re.sub(r'\bet\s+pour\s+le\s+pa[iy]ement\s+je\s+veux\s+', '\nPaiement : ',text,flags=re.I)
        text=re.sub(r'\bet\s+pour\s+le\s+paiment\s+je\s+veux\s+', '\nPaiement : ',text,flags=re.I)
        text=re.sub(r'\beffe\s+(\d+)\s*j\b',r'effet \1 jours',text,flags=re.I)
        text=re.sub(r'\bet\s+(TTC|HT)\s+pas\s+(?:HT|TTC)\b',lambda m:'\nType montant : '+m[1].upper(),text,flags=re.I)
        text=re.sub(r'\bpaiement\s+par\s+','\nPaiement : ',text,flags=re.I)
        text=re.sub(r'\s+merci[.!\s]*$','',text,flags=re.I)
        text=re.sub(r'\b(ch[eè]que)\s+(\d+)\s*j\b',r'\1 \2 jours',text,flags=re.I)
    text=re.sub(r'(?im)\n[ \t]*(?:merci|cordialement|bien cordialement)[.! \t]*$', '', text)
    text=re.sub(r'(?is)\s+merci\s+de\s+pr[eé]parer\s+la\s+fiche\s+pour\s+validation[.!\s]*$', '', text)
    # A closing request is not part of the last business field (e.g. TTC).
    text=re.sub(r'(?is)\s+merci\s+de\s+pr[eé]parer\s+(?:sa\s+cr[eé]ation|(?:la|cette)\s+(?:fiche|cr[eé]ation))(?:\s+pour\s+validation)?[.!\s]*$', '', text)
    # Recognize prose field introductions as well as colon-labelled forms.
    # Require a numeric value so words in a company name are not split blindly.
    text=re.sub(r"(?:\b(?:avec|et)\s+)?(?:\bl['’]|\ble\s+|\bla\s+)?\b(ice|if|rc|téléphone|telephone|tél|tel|fax)\s*[:=]?\s*(?=[0-9])",
        lambda m:'\n'+{'tél':'telephone','tel':'telephone','téléphone':'telephone'}.get(m[1].casefold(),m[1])+' : ',text,flags=re.I)
    n=norm(text).strip(' .!')
    clarification=bool(re.fullmatch(r'(?:oui[, ]+)?(?:une |la )?(?:nouvelle fiche|nouveau) fournisseur',n) or re.fullmatch(r'un\s+nevue\s+xfourbnseur',n))
    suppliers=[p for p in state.get('partners',[]) if p.get('kind')=='supplier']
    if len(suppliers)==1 and not suppliers[0].get('ice') and re.fullmatch(r'[0-9]{15}',n):
        return Delta(intent='update',fournisseurs=[{'index':1,'ice':n}]),'ICE : '+text
    if len(suppliers)==1 and n in ('creer le','creer le fournisseur','creer','ok','oui'):
        return Delta(intent='update',fournisseurs=[{'index':1}]),text
    if not suppliers and n in ('oui','ok'):
        # Resume the immediately preceding request; this only prepares a draft.
        previous=next((row for row in reversed(history) if row.get('role')=='user' and row.get('content')!=text),None)
        if previous:
            recovered=extract(previous['content'],state)
            if recovered:return recovered[0],recovered[1]+'\n'+text
    if clarification:
        if len(suppliers)==1:return Delta(intent='update',fournisseurs=[{'index':1}]),text
        if suppliers:return None
        for row in reversed(history):
            if row.get('role')!='user' or row.get('content')==text:continue
            recovered=extract(row['content'],state)
            if recovered:return recovered[0],recovered[1]+'\n'+text
        return None
    if re.search(r'\b(?:articles?|clients?)\b',n):return None
    aliases={**ALIASES,'nom de frs':'nom','nom de fournisseur':'nom','nom du fournisseur':'nom','nom fournisseur':'nom','raison sociale':'nom'}
    creating=bool(re.search(r'\bfournisseur\b',n) and re.search(r'\b(?:creer|creation|nouveau|nouvelle|ajoute|ajouter|prepare)\b',n))
    if not creating:
        if len(suppliers)==1:
            delta=literal_extract(text,state)
            return (delta,text) if delta and delta.fournisseurs else None
        return None
    matches=list(re.finditer(r'\b('+ '|'.join(map(re.escape,sorted(aliases,key=len,reverse=True))) +r')\s*:\s*',n))
    fields={}
    for i,m in enumerate(matches):
        value=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip(' \n\r,;')
        value=re.sub(r'\s+et\s*$','',value,flags=re.I).rstrip(' .')
        key=aliases[m[1]]
        if key in ('ice','identifiant_fiscal','rc','telephone','fax'):value=value.rstrip('.')
        if key=='type_montant':value=value.upper()
        if key=='date_regularite':
            from app.services.supplier_dates import normalize_date
            value=normalize_date(value)
        if key=='dossier_cible':value=value.upper()
        if key=='type_montant_valeur':
            if value not in ('1','2'):return None
            value=int(value)
        if key in fields and fields[key]!=value:return None
        fields[key]=value
    if not fields.get('nom'):
        # A name in the sentence is as explicit as a labelled "Nom :" field.
        header=n[:matches[0].start()] if matches else n
        named=re.search(r'\bfournisseur\s+(?:(?:nomme|appele)\s+)?(.+)',header)
        if named:
            name=text[named.start(1):named.end(1)].strip(' \n\r.:;,')
            if name and not re.match(r'(?:suivant|ci-dessous|dans le|dans test)\b',norm(name)):
                fields['nom']=name
    if fields.get('nom'):
        patch=PartnerPatch.model_validate(fields)
        # A reformulated name-only request can repair the current initial draft.
        # Explicit "nouveau/autre" requests and enriched/executed drafts stay distinct.
        if (len(suppliers)==1 and set(fields)=={'nom'} and
            re.match(r'je\s+(?:veux|souhaite)\s+creer\s+le\s+fournisseur\b',n) and
            not any(suppliers[0].get(k) for k in ('ice','identifiant_fiscal','rc','adresse','ville','telephone')) and
            (suppliers[0].get('operation') or {}).get('status') in (None,'prepared','blocked','invalidated')):
            return Delta(intent='update',fournisseurs=[PartnerPatch(index=1,nom=fields['nom'])]),text
        return Delta(intent='new',fournisseurs=[patch]),text
    delta=literal_extract(text,state)
    return (delta,text) if delta and delta.fournisseurs else None

def repair_embedded_fields(partner):
    """Repair an unexecuted draft produced by the previous prose parser."""
    if (partner.get('operation') or {}).get('status') not in (None,'blocked','invalidated'):return
    payment=partner.get('conditions_paiement') or ''
    cleaned=strip_missing_fiscal_note(payment)
    if cleaned!=payment:
        partner['conditions_paiement']=cleaned
        partner['approved']=False;partner['reviewed']=False
        if partner.get('operation'):partner['operation']['status']='invalidated'
    rc=partner.get('rc') or ''
    date_in_rc=re.fullmatch(r'\s*([a-z0-9/-]{1,30})\s+date\s+(?:de\s+)?regularite(?:\s+fiscale)?\s*[:=]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.-]\d{2}[/.-]\d{4})[.\s]*',norm(rc))
    if date_in_rc:
        from app.services.supplier_dates import normalize_date
        corrected_date=normalize_date(date_in_rc[2])
        if not partner.get('date_regularite') or partner['date_regularite']==corrected_date:
            partner['rc']=rc[date_in_rc.start(1):date_in_rc.end(1)]
            partner['date_regularite']=corrected_date
            partner.setdefault('sources',{})['date_regularite']='user_declared'
            partner['approved']=False;partner['reviewed']=False
            if partner.get('operation'):partner['operation']['status']='invalidated'
    name=partner.get('nom','')
    if partner.get('ice') or not re.search(r"\bavec\s+l['’]ice\s+[0-9]{15}\b",norm(name)):return
    parsed=extract('Créer le fournisseur '+name,{})
    if not parsed:return
    fields=parsed[0].fournisseurs[0].model_dump(exclude_none=True,exclude_unset=True)
    if not fields.get('ice') or fields.get('nom')==name:return
    for key,value in fields.items():
        if key=='nom' or not partner.get(key):partner[key]=value
    partner['approved']=False;partner['reviewed']=False
    if partner.get('operation'):partner['operation']['status']='invalidated'

def prepare_state(state):
    from app.services.chat_supplier_sql_actions import fingerprint
    messages=[]
    for p in state.get('partners',[]):
        if p.get('kind')!='supplier':continue
        if state.get('supplier_target')=='OB':p['dossier_cible']='OB'
        repair_embedded_fields(p)
        p['preparation']={'target_folder':p.get('dossier_cible','TEST'),'transport':'direct_sql','duplicates':[]}
        p['checks']={'valid_basic':bool(p.get('nom')),'errors':[]}
        missing=[key for key in ('nom',) if not p.get(key)]
        if missing:
            messages.append('Votre demande est conservée. Indiquez '+', '.join('le nom' if k=='nom' else 'l’ICE' for k in missing)+'. Les autres informations seront complétées avec les valeurs habituelles et présentées avant confirmation.')
            continue
        op=p.get('operation') or {}
        if op.get('status') not in (None,'invalidated','blocked'):
            messages.append('Les informations de la fiche sont conservées. Consultez son état dans le tableau ci-dessous.')
            continue
        if p.get('ice') and not re.fullmatch(r'[0-9]{15}',p['ice']):
            state.setdefault('_supplier_dialogue',{})['expected_field']='ice'
            p['approved']=False;p['reviewed']=False
            p['checks']['errors']=['invalid_ice_length']
            p['operation']={'status':'blocked','needs_correction':True}
            messages.append('L’ICE fourni contient '+str(len(p['ice']))+' chiffres ; 15 sont requis. Vérifiez l’ICE. Les autres informations sont conservées.')
            continue
        if p.get('email'):
            p['approved']=False;p['reviewed']=False
            p['checks']['errors']=['unsupported_write_field:email']
            p['operation']={'status':'blocked','needs_correction':True}
            messages.append('Email conservé dans la fiche. Son enregistrement dans Sage n’est pas encore pris en charge par la requête actuelle.')
            continue
        from app.services.supplier_followups import phone_warning
        warning=phone_warning(p)
        if warning:
            p['approved']=False;p['operation']={'status':'blocked','needs_correction':True,'validation':{'message':warning}}
            messages.append(warning)
            continue
        try:
            p['operation']=sql.prepare_operation(p);p['operation']['partner_hash']=fingerprint(p);p['approved']=False
            op=p['operation']
            warnings=op.get('duplicate_warnings',[])
            messages.append('Fiche à corriger. Consultez le motif ci-dessous.' if op.get('status')=='blocked' else 'Fiche prête. Vérifiez le tableau avant de confirmer.')
            if warnings and not op.get('validation'):messages.append(sql.preparation_message({'duplicate_warnings':warnings}))
            if op.get('validation'):messages.append(op['validation']['message'])
            if not p.get('conditions_paiement') and op.get('status')!='blocked':
                messages.append('Paiement habituel proposé, à vérifier.')
            if op.get('draft_only_fields'):
                messages.append('La forme juridique '+p['forme_juridique']+' sera conservée uniquement dans le brouillon. Cochez cet accord avant de confirmer la création ; elle ne sera pas enregistrée dans Sage.')
        except crud.CrudError as exc:
            if exc.code.startswith('Champs absents de la requête fournie :'):
                p['operation']={'status':'blocked','needs_mapping':True}
                p['checks']['errors']=[exc.code]
                messages.append('Les informations sont conservées dans le brouillon. Leur enregistrement dans Sage nécessite une correspondance validée : '+exc.code.split(':',1)[1].strip()+'. Vous pouvez continuer à compléter la fiche ; aucune création effectuée.')
                continue
            from uuid import uuid4
            import logging
            diagnostic=uuid4().hex[:12]
            logging.getLogger('agent_sage.chat').warning('supplier_verification_unavailable diagnostic=%s code=%s',diagnostic,exc.code)
            p['operation']={'status':'invalidated','verification_unavailable':True}
            p['preparation'].update(sql_error=exc.code,diagnostic=diagnostic)
            if exc.code.startswith(('Champ trop long :','ICE invalide :','Date de régularité invalide','Type montant HT/TTC requis','Référence ')):
                p['operation']={'status':'blocked','needs_correction':True}
                p['checks']['errors']=[exc.code]
                messages.append('Votre fiche est conservée. '+exc.code+' Vous pouvez corriger cette information dans le chat.')
                continue
            messages.append('La vérification Sage est momentanément indisponible. Votre fiche est conservée : vous pouvez la compléter ou réessayer. Référence : '+diagnostic+'.')
    return '\n\n'.join(messages)
