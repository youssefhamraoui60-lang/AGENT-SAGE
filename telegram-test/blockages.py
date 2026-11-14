"""Explain missing references and propose choices, never replace a Sage identity."""
import asyncio

async def explain(details):
    from prepare import lookup,canonical_article
    source=details.get('source_draft',{})
    notices=[];proposals=[]
    try:
        if not details.get('client') and source.get('client'):
            ob=await asyncio.to_thread(lookup,'client',source['client'],folder='OB')
            if len(ob)==1:
                details['reference_client_ob']=ob[0]
                notices.append('Client '+ob[0]['BPCNUM_0']+' trouvé dans OB, absent ou non identifié dans TEST. Ses lignes restent préparées.')
                proposals.append('Faire valider la création/synchronisation de la fiche client dans TEST, ou indiquer un autre client TEST explicitement. Aucun remplacement automatique.')
                from understanding import normalized
                possible=await asyncio.to_thread(lookup,'client',ob[0]['BPCNAM_0'])
                valid=[r for r in possible if normalized(r['BPCNAM_0'])==normalized(ob[0]['BPCNAM_0']) and r['CUR_0'].strip()==ob[0]['CUR_0'].strip()]
                details['alternative_clients_test']=valid
                if valid:proposals.append('Même nom/devise dans TEST sous les codes '+', '.join(r['BPCNUM_0'] for r in valid)+'. Confirmer explicitement le code client voulu avant de recalculer le récapitulatif.')
        if any(canonical_article(line.get('article') or '')=='COL' for line in source.get('lines',[])):
            test=await asyncio.to_thread(lookup,'article','COL')
            ob=await asyncio.to_thread(lookup,'article','COL',folder='OB')
            t=next((r for r in test if r['ITMREF_0'].strip()=='COL'),None)
            o=next((r for r in ob if r['ITMREF_0'].strip()=='COL'),None)
            if t and o and 'TRADICEM' in o['ITMDES1_0'].upper() and 'TRADICEM' not in t['ITMDES1_0'].upper():
                notice='Code COL différent : TEST « '+t['ITMDES1_0']+' » ('+t['SAU_0']+'), OB « '+o['ITMDES1_0']+' » ('+o['SAU_0']+'). Produit à valider.'
                notices.append(notice);details['missing'].append(notice);details['missing_fields'].append('identité produit COL')
                candidates=await asyncio.to_thread(lookup,'article','TRADICEM')
                valid=[r for r in candidates if r['ITMREF_0'].strip()!='COL' and r['SITE_OK'] and r['SAU_0'].strip()==o['SAU_0'].strip() and r['VACITM_0'].strip()==o['VACITM_0'].strip()]
                details['alternatives_test']=valid
                proposals.append('Choisir et confirmer un code TEST réellement équivalent au TRADICEM : '+(', '.join(r['ITMREF_0']+' — '+r['ITMDES1_0'] for r in valid) if valid else 'aucun candidat compatible vérifié. Faire préparer sa fiche article-site 201 sous un code distinct.'))
    except Exception:
        notices.append('Vérification complémentaire indisponible. Brouillon conservé ; aucune substitution ni création automatique.')
    details['notices']=notices;details['proposals']=proposals
    if notices or proposals:details['reply']+='\n\n'+ '\n'.join(notices+proposals)
    return details
