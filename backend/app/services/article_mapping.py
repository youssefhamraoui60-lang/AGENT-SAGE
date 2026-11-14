"""General article proposal from declared data and reviewed TEST rules only."""
from datetime import date
from decimal import Decimal,InvalidOperation
from app.schemas.sage_crud import Preparation
from app.services.sage_soap import SageError


def request(article,rules):
    category=rules.get('categories',{}).get(article.get('categorie'))
    if not category:raise SageError('article_category_not_creatable',422)
    unit=article.get('unite')
    if not unit:raise SageError('article_unit_required',422)
    fields={'ITM0_1.DES1AXX':article['designation'],'ITM0_1.TCLCOD':article['categorie']}
    statuses=category.get('statuses',[]);status=category.get('default_status')
    if not status and len(statuses)==1:status=statuses[0]
    if status not in statuses:raise SageError('article_status_not_reviewed',422)
    fields['ITM0_1.ITMSTA']=status
    combos=[c for c in category.get('unit_combinations',[]) if c.get('ITM3_1.STU')==unit and
            all(not article.get(key) or c.get(path)==article[key] for key,path in [('unite_achat','ITM3_1.PUU'),('unite_vente','ITM3_1.SAU')])]
    if len(combos)!=1:raise SageError('article_unit_combination_ambiguous',422)
    if not set(combos[0])<={'ITM3_1.STU','ITM3_1.PUU','ITM3_1.SAU','ITM3_1.PUUSTUCOE','ITM3_1.SAUSTUCOE'}:raise SageError('article_unit_combination_ambiguous',422)
    fields.update(combos[0])
    if article.get('taux_tva'):
        refs=article.get('checks',{}).get('tools',{});sites=refs.get('site',{}).get('rows',[])
        company=str(sites[0].get('LEGCPY_0') or '').strip() if len(sites)==1 else None
        contexts=[]
        for ctx in category.get('tax_contexts',[]):
            try:
                valid=(ctx.get('reviewed') is True and ctx['site']==article.get('site') and ctx['company']==company
                    and Decimal(str(ctx['rate']))==Decimal(article['taux_tva'])
                    and date.fromisoformat(ctx['valid_from'])<=date.today()<=date.fromisoformat(ctx['valid_to']))
                if valid:contexts.append(ctx)
            except (KeyError,ValueError,InvalidOperation):continue
        if len(contexts)!=1:raise SageError('article_tax_context_unverified',422)
        context=contexts[0];combo=context['fields']
        if combo not in category.get('tax_combinations',[]):raise SageError('article_tax_context_unverified',422)
        if set(combo)!=set(category.get('tax_fields',[])) or set(combo)&set(fields):raise SageError('article_tax_context_unverified',422)
        # Context review does not replace actual TEST rate/determination reads.
        rates=refs.get('taxes',{}).get('rows',[])
        determination=[r for name,value in refs.items() if name.startswith('requested_tax_determination_') for r in value.get('rows',[])]
        if not any(str(r.get('VAT_0','')).strip()==context['vat_code'] for r in rates):raise SageError('article_tax_context_unverified',422)
        if not any(r.get('ENAFLG_0')==2 and str(r.get('VAT_0','')).strip()==context['vat_code'] and str(r.get('VACITM_0','')).strip()==context['level'] and str(r.get('VACBPR_0','')).strip()==context['regime'] for r in determination):raise SageError('article_tax_context_unverified',422)
        fields.update(combo)
    elif category.get('tax_fields') and category.get('tax_default_verified') is not True:
        raise SageError('article_tax_defaults_unverified',422)
    else:
        default=category.get('tax_default_fields',{})
        if default:fields.update(default)
    for source,path in [('code_comptable','ITM5_1.ACCCOD'),('gestion_stock','ITM2_1.STOMGTCOD'),('gestion_lots','ITM2_3.LOTMGTCOD')]:
        if article.get(source):fields[path]=article[source]
    if article.get('code_fournisseur'):
        paths=category.get('supplier_fields',[])
        if len(paths)!=1:raise SageError('article_supplier_mapping_not_reviewed',422)
        fields[paths[0]]=article['code_fournisseur']
    # Unmapped user requests are never silently dropped.
    if article.get('compte_general') or (article.get('accounting_category') and not article.get('code_comptable')):
        raise SageError('article_accounting_mapping_unverified',422)
    for explicit in ('niveau_taxe','code_tva'):
        if article.get(explicit):
            names=[v for p,v in fields.items() if p in category.get('tax_fields',[])]
            if not any(article[explicit] in (v if isinstance(v,list) else [v]) for v in names):raise SageError('article_tax_context_unverified',422)
    payload=[]
    for path,value in fields.items():
        if '[' in path:raise SageError('article_table_mapping_unreviewed',422)
        group,name=path.split('.',1);payload.append({'group':group,'name':name,'value':value})
    return Preparation(action='create',keys={'ITMREF':article['code_article']},fields=payload)
