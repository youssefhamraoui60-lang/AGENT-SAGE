import React from 'react';
const names={DES1AXX:'Désignation',TCLCOD:'Catégorie',ITMSTA:'Statut Sage',STU:'Unité stock',PUU:'Unité achat',SAU:'Unité vente',PUUSTUCOE:'Coefficient achat/stock',SAUSTUCOE:'Coefficient vente/stock',VACITM:'Niveaux de taxe article',ACCCOD:'Code comptable',BPSNUM:'Fournisseur',STOMGTCOD:'Gestion stock',LOTMGTCOD:'Gestion lots'};
function cause(value){
 if(value==='article_stock_management_not_allowed')return 'Cette gestion de stock n’est pas autorisée par les règles métier approuvées de la catégorie.';
 if(value==='article_supplier_required')return 'Un fournisseur est obligatoire selon la règle de catégorie approuvée : préciser un fournisseur existant.';
 if(value==='article_reference_rules_unavailable')return 'Référentiel métier TEST non validé : faire approuver les règles de cette publication.';
 if(value.startsWith('missing:'))return 'À préciser : '+({unite:'unité de stock',site:'site',categorie:'catégorie',designation:'désignation'}[value.split(':')[1]]||value.split(':')[1]);
 return {article_security_pending:'Validation technique et droits Sage en attente : intervention administrative nécessaire.',duplicate_article_code:'Ce code existe déjà : consulter la fiche avant toute autre décision.',sql_checks_incomplete:'Une consultation du référentiel est indisponible : reprendre la vérification.'}[value]||value;
}
export function GeneralArticleActions({article,busy,onAction}){
 const execution=article.execution,op=article.operation;const blockers=execution?.blockers||[];
 const terminal=['executing','ambiguous','unverified','succeeded','failed'].includes(op?.status);
 const tax=execution?.tax;
 return <section aria-label="Création article TEST">
 {!op&&blockers.length>0&&<><strong>BLOQUÉ — article non créé</strong><ul>{blockers.map(c=><li key={c}>{cause(c)}</li>)}</ul></>}
 {!!execution?.security_controls?.length&&<details><summary>Contrôles bloquants et actions nécessaires</summary><ul>{execution.security_controls.map(c=><li key={c.code}><strong>{c.label}</strong> {c.action}</li>)}</ul><p>Une confirmation de brouillon ne remplace pas ces contrôles.</p></details>}
 {!op&&article.write_status?.message&&<p>{article.write_status.message}</p>}
 {tax?.default_differs_from_rate_code&&!tax.applicability_verified&&!terminal&&<p>TVA demandée : {tax.requested_rate} %. Défaut de catégorie : {tax.category_defaults.join(', ')}. Niveaux candidats : {tax.candidate_levels.join(', ')}. Une validation métier du niveau applicable est nécessaire ; aucun remplacement automatique.</p>}
 {!op&&execution?.security?.ready&&<button disabled={busy||blockers.length>0} onClick={()=>onAction(article,'prepare',false)}>Préparer les données exactes à approuver</button>}
 {op?.status==='blocked'&&<><p>BLOQUÉ — préparation non approuvable ; contrôles métier ou de sécurité à compléter.</p><ul>{op.checks?.blockers?.map(c=><li key={c}>{cause(c)}</li>)}</ul></>}
 {op?.status==='prepared'&&<><strong>Données exactes à approuver — TEST / {article.code_article}</strong><details><summary>{'Donn\u00e9es exactes'}</summary><dl>{op.payload?.fields?.map(f=><div key={f.group+f.name}><dt>{names[f.name]||f.name}</dt><dd>{Array.isArray(f.value)?f.value.filter(Boolean).join(' / '):f.value}</dd></div>)}</dl></details><button disabled={busy||!execution?.security?.ready} onClick={()=>onAction(article,'approve',true)}>Approuver et créer cet article dans TEST</button></>}
 {op?.status==='approved'&&<button disabled={busy||!execution?.security?.ready} onClick={()=>onAction(article,'execute',true)}>Exécuter l’article approuvé</button>}
 {terminal&&article.outcome?.confirmed&&<p>CRÉÉ — article relu et vérifié. Les fiches article-site sont des opérations distinctes.</p>}
 {article.outcome?.confirmed&&<section aria-label="Création article-site séparée"><p>Fiches article-site : préparation et approbation séparées de la fiche article générale.</p>{(article.requested_sites?.length?article.requested_sites:[article.site]).filter(Boolean).map(site=>{
  const child=article.strict_site_operations?.[site];
  return <div key={site}><strong>{article.code_article} / {site}</strong>{!execution.site_security?.ready&&<p>Fiche article-site bloquée : droits et règles du site à valider séparément.</p>}{!child&&<button disabled={busy||!execution.site_security?.ready} onClick={()=>onAction(article,'site-prepare',false,site)}>Préparer la fiche du site {site}</button>}{child?.status==='prepared'&&<><dl>{child.payload?.fields?.map(f=><div key={f.group+f.name}><dt>{names[f.name]||f.name}</dt><dd>{String(f.value)}</dd></div>)}</dl><button disabled={busy||!execution.site_security?.ready} onClick={()=>onAction(article,'site-approve',true,site)}>Approuver et créer la fiche du site {site}</button></>}{child?.status==='approved'&&<button disabled={busy||!execution.site_security?.ready} onClick={()=>onAction(article,'site-execute',true,site)}>Exécuter la fiche du site {site}</button>}{child?.confirmed&&<p>Fiche article-site créée et vérifiée.</p>}{child&&['ambiguous','unverified','failed'].includes(child.status)&&<p>Résultat article-site non confirmé ; aucune relance automatique.</p>}</div>;
 })}</section>}
 </section>;
}
