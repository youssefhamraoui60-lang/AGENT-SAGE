"""Grounded short corrections; uncertainties produce questions, never Sage writes."""
import copy,re
from difflib import get_close_matches,SequenceMatcher
from app.services.chat_turns import norm

def phone_warning(partner):
    number=partner.get('telephone') or ''
    if not number or partner.get('pays') not in (None,'','MA','Maroc'):return None
    digits=re.sub(r'[\s().-]','',number)
    if digits.startswith('+212'):digits='0'+digits[4:]
    elif digits.startswith('00212'):digits='0'+digits[5:]
    if not re.fullmatch(r'0[5678]\d{8}',digits):
        return 'Le téléphone '+number+' ne correspond pas au format marocain attendu. Indiquez le bon numéro ou précisez le pays ; aucune correction automatique des chiffres ne sera faite.'
    return None

def turn(text,state):
    if state.get('articles') or len(state.get('partners',[]))!=1 or state['partners'][0].get('kind')!='supplier':return None
    p=state['partners'][0]
    if (p.get('operation') or {}).get('status') in ('executing','succeeded','failed','ambiguous','unverified'):return None
    n=norm(text).strip(' .!');changed=copy.deepcopy(state);focus=changed.setdefault('_supplier_dialogue',{})
    prefix=r'(?:(?:la|le|les)\s+)?(?:(?:conditions?|codition|coditions?)\s+(?:de\s+)?)?(?:paiement|payment|paiment)\s*(?:est|:|=)?\s*'
    body=re.sub('^'+prefix,'',n)
    payment=re.fullmatch(r'(?:(cheque|effet|virement)\s*(?:a\s*)?)?(\d{1,3})\s*(?:jours?|j|jr)\s*(cheque|effet|virement)?',body)
    from app.services.supplier_dialogue import assign
    # A labelled fiscal fact can be embedded in a sentence referring to the
    # current draft. Its digits do not depend on spelling the surrounding prose.
    fiscal=list(re.finditer(r'\b(ice|if|rc)\s*(?:(?:est|numero|n[°o])\s*|[:=]\s*)?(\d{1,30})(?!\d)',n))
    if fiscal and '?' not in text and not re.search(r'\b(?:pas|non|sans|nouveau|nouvelle|autre|creer|ajouter|annul\w*|supprim\w*)\b',n):
        # Do not transfer facts explicitly attributed to a different supplier.
        reference=re.search(r'\b(?:fourn\w*|foun\w*)\s+(.+?)\b(?:ice|if|rc)\b',n)
        named=re.sub(r"\b(?:avec|avce|le|la|les|son|sa|est|de|du)\b|[:=,]",' ',reference[1]).strip() if reference else ''
        named=' '.join(named.split())
        if not named or named==norm(p.get('nom') or ''):
            facts={}
            for match in fiscal:
                field={'ice':'ice','if':'identifiant_fiscal','rc':'rc'}[match[1]]
                if field in facts and facts[field]!=match[2]:
                    return {'state':changed,'reply':'Plusieurs valeurs sont indiquées pour '+match[1].upper()+'. Quelle valeur faut-il conserver pour '+str(p.get('nom') or 'ce fournisseur')+' ?'}
                facts[field]=match[2]
            # Rich clauses remain with the complete parser rather than losing
            # address, telephone or payment facts alongside fiscal identifiers.
            if not re.search(r'\b(?:adresse|ville|telephone|tel|email|paiement)\b',n):
                for field,value in facts.items():
                    error=assign(changed,field,value)
                    if error:return {'state':changed,'reply':error}
                return {'state':changed,'prepare':True}
    # Tolerate spelling errors in an explicitly labelled field. Only the
    # label is matched; the original value is preserved byte for byte.
    labelled=re.fullmatch(r"\s*(?:(?:le|la|les)\s+|l['’]\s*)?([\w]+)\s+(?:est\s+|[:=]\s*)(.+?)\s*",text,re.I|re.S)
    if labelled:
        labels={'adresse':'adresse','ville':'ville','telephone':'telephone','fax':'fax','ice':'ice','nom':'nom','paiement':'conditions_paiement'}
        declared=norm(labelled[1])
        ranked=sorted(((SequenceMatcher(None,declared,label).ratio(),label) for label in labels),reverse=True)
        score,label=ranked[0]
        if .7<=score<1 and len(declared)>=5 and declared[:2]==label[:2] and score-ranked[1][0]>=.15:
            error=assign(changed,labels[label],labelled[2])
            return {'state':changed,'prepare':not error,'reply':error}
    if payment:
        method=payment[1] or payment[3]
        if not method:
            previous=re.search(r'\b(cheque|effet|virement)\b',norm(p.get('conditions_paiement') or ''))
            method=previous[1] if previous else None
        if not method:
            focus.update(expected_field='payment_method',payment_days=payment[2])
            return {'state':changed,'reply':'Pour '+payment[2]+' jours, souhaitez-vous payer par chèque, effet ou virement ?'}
        error=assign(changed,'conditions_paiement',method+' '+payment[2]+' jours')
        return {'state':changed,'prepare':not error,'reply':error}
    if re.fullmatch(prefix+r'fix',n):
        return {'state':changed,'reply':'« Fix » ne précise pas un mode de paiement. Indiquez chèque, effet ou virement et le délai ; le choix précédent est conservé.'}
    if re.search(r'\b(?:telephone|telefon|tele|fix)\b',n) and re.search(r'\b(?:valid|valder|valider|maroc|coriger|corriger)',n):
        telephone=p.get('telephone') or ''
        digits=re.sub(r'[\s().-]','',telephone)
        if digits.startswith('+212'):digits='0'+digits[4:]
        elif digits.startswith('00212'):digits='0'+digits[5:]
        plausible=bool(re.fullmatch(r'0[5678]\d{8}',digits))
        reply=('Le format du téléphone est compatible avec le plan marocain ; son attribution n’est pas vérifiée.' if plausible else 'Le téléphone '+(telephone or 'non renseigné')+' doit être vérifié. Je ne peux pas inventer un numéro corrigé. Quel numéro faut-il retenir ?')
        if re.search(r'\bville\b',n):
            city=p.get('ville') or ''
            choices=get_close_matches(norm(city),['berrechid','kenitra','rabat','casablanca','marrakech','fes','tanger'],n=1,cutoff=.78)
            if choices and choices[0]!=norm(city):reply+=' Pour la ville, souhaitez-vous retenir « '+choices[0].title()+' » à la place de « '+city+' » ?'
        return {'state':changed,'reply':reply}
    return None
