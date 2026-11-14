"""Per-article routing: legacy exceptions stay bounded; general TEST is strict."""
from app.core.config import settings
from app.services import sage_crud


def legacy_scope(article):
    if (article.get('operation') or {}).get('transport')=='strict_generic':return False
    if not settings.sage_powershell_chat_enabled:return False
    from app.services.sage_powershell_chat import creation_blockers
    return not creation_blockers(article)


def tax_review(article):
    refs=article.get('checks',{}).get('tools',{})
    defaults=sorted({str(r.get('VACITM_0') or '').strip() for r in refs.get('category',{}).get('rows',[]) if r.get('VACITM_0')})
    candidates=sorted({str(r.get('VAT_0') or '').strip() for r in refs.get('taxes',{}).get('rows',[]) if r.get('VAT_0')})
    levels=sorted({str(r.get('VACITM_0') or '').strip() for key,value in refs.items() if key.startswith('requested_tax_determination_') for r in value.get('rows',[]) if r.get('ENAFLG_0')==2 and str(r.get('VAT_0') or '').strip() in candidates and r.get('VACITM_0')})
    return {'requested_rate':article.get('taux_tva'),'category_defaults':defaults,'rate_codes_found':candidates,'candidate_levels':levels,
            'applicability_verified':bool(((article.get('operation') or {}).get('checks',{}).get('business_checks') or {}).get('tax_validated')),
            'default_differs_from_rate_code':bool(article.get('taux_tva') and defaults and levels and not set(defaults)&set(levels))}


def describe(article):
    op=article.get('operation') or {}
    if op.get('transport')=='direct_sql_article' or settings.sage_article_sql_enabled and op.get('status') not in ('executing','succeeded','ambiguous','unverified','failed'):
        return {'route':'sql_test','security':{'ready':settings.sage_article_sql_enabled and not settings.sage_mcp_enabled,'folder':article.get('dossier_cible','TEST'),'transport':'direct_sql_article','individual_approval_required':True},'blockers':article.get('sql_blockers',[]),'tax':tax_review(article)}
    if legacy_scope(article):
        from app.services.sage_powershell_chat import security
        return {'route':'legacy_scoped','security':security(),'blockers':[],'tax':tax_review(article)}
    security=sage_crud.security('articles','create')
    errors=list(article.get('checks',{}).get('errors',[]))
    if not security['ready']:errors.append('article_security_pending')
    return {'route':'general_test','security':security,'security_controls':security_controls(security),'site_security':sage_crud.security('article-sites','create'),'blockers':sorted(set(errors)),'tax':tax_review(article)}


def security_controls(security):
    controls={
        'WRITES_DISABLED':('Écritures désactivées (SAGE_WRITES_ENABLED).','Faire autoriser leur activation après validation des autres contrôles.'),
        'CA_CRL_MATERIAL_REQUIRED':('Révocation HTTPS non vérifiable : CRL de confiance absente ou invalide.','Obtenir la CRL signée et à jour auprès de l’autorité de certification et vérifier la chaîne.'),
        'VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED':('Politique de sécurité du compte technique non validée.','Faire approuver les preuves de droits AIAGT et le périmètre TEST.'),
        'SCOPED_X3_RIGHTS_AND_RULES_EVIDENCE_REQUIRED':('Droits ou règles métier de cette opération non justifiés.','Faire valider les droits et règles liés à la publication SOAP.'),
        'DEDICATED_TECHNICAL_ACCOUNT_REQUIRED':('Compte technique dédié non vérifié.','Faire vérifier l’identité technique AIAGT ; ne pas réutiliser un compte administrateur.'),
        'VERIFIED_HTTPS_REQUIRED':('Transport HTTPS de confiance non configuré.','Faire vérifier l’adresse HTTPS et sa chaîne de confiance sans désactiver TLS.')}
    return [{'code':b,'label':controls.get(b,('Contrôle de sécurité non satisfait.','Faire examiner ce contrôle par l’administrateur.'))[0],
             'action':controls.get(b,('','Faire examiner ce contrôle par l’administrateur.'))[1]} for b in security.get('blockers',[])]


def reason(code):
    if code.startswith('missing:'):
        field={'unite':'unité de stock','site':'site','categorie':'catégorie','designation':'désignation'}.get(code.split(':',1)[1],code.split(':',1)[1])
        return field+' manquant. Action : précisez '+field+'.'
    return {'article_security_pending':'validation technique et droits Sage en attente. Action : faire lever les prérequis par l’administrateur.',
            'article_connection_unavailable':'connexion Sage indisponible pendant la préparation. Action : reprendre les vérifications ; aucun SAVE envoyé.',
            'duplicate_article_code':'code déjà existant. Action : consulter la fiche ou choisir un autre code après contrôle.',
            'article_reference_rules_unavailable':'règles métier TEST non encore approuvées. Action : faire valider le référentiel du connecteur.',
            'article_tax_context_unverified':'TVA demandée non validée dans ce contexte. Action : faire confirmer le niveau fiscal applicable pour cette catégorie et ce site.',
            'article_unit_required':'unité de stock absente. Action : indiquez une unité autorisée.',
            'article_unit_combination_ambiguous':'conversion des unités non déterminée. Action : préciser les unités achat/vente ou valider la règle de catégorie.'}.get(code,code)


def blocked_message(article,codes):
    details=(' '+' '.join(c['label']+' Action : '+c['action'] for c in security_controls(sage_crud.security('articles','create')))) if 'article_security_pending' in codes else ''
    return "BLOQUÉ : l’article "+str(article.get('code_article') or article.get('designation') or '')+" n’a pas été créé. Cause : "+' '.join(reason(c) for c in codes)+details
