import React from 'react';
import {SupplierResult} from './SupplierResult.jsx';
import {SupplierActions} from './SupplierActions.jsx';
const fields={categorie_fournisseur:'Catégorie fournisseur',pays:'Pays',devise:'Devise',conditions_paiement:'Conditions de paiement',regime_taxe:'Régime fiscal',code_comptable:'Code comptable'};
export function SupplierPreparation({partner,security,busy,onAction}){
 const prep=partner.preparation;if(!prep)return null;
 if(partner.operation&&['executing','ambiguous','unverified','succeeded','failed'].includes(partner.operation.status))return <section aria-label="Préparation fournisseur">{partner.operation.status==='executing'?<p>Tentative fournisseur en cours ; aucune relance automatique.</p>:<SupplierResult operation={partner.operation}/>}</section>;
 return <section className="chat-next-question" aria-label="Préparation fournisseur"><strong>Dossier cible : {prep.target_folder}{prep.target_folder==='OB'?' — lecture seule':''}</strong>
 {prep.duplicates?.length>0&&<><p>Avertissement : correspondances existantes</p><ul>{prep.duplicates.map((d,i)=><li key={d.folder+d.code+i}>{d.folder} / {d.code} — {d.name} · {d.supplier_exists?'Fournisseur existant':'Tiers existant'} · {d.matched_fields.map(x=>({ice:'ICE',identifiant_fiscal:'IF',rc:'RC',nom:'nom'}[x]||x)).join(', ')}</li>)}</ul><p>Vous pouvez confirmer explicitement une nouvelle fiche dans TEST malgré ces doublons.</p></>}
 {prep.code_proposal&&<p>Code proposé : {prep.code_proposal.code} — absent lors du contrôle, non réservé. Convention observée à confirmer, aucun numéro officiel consommé.</p>}
 {prep.near_names?.length>0&&<><p>Noms proches dans la recherche élargie — ces ressemblances seules ne prouvent pas un doublon fiscal :</p><ul>{prep.near_names.map((r,i)=><li key={r.code+i}>{r.code} — {r.name}</li>)}</ul></>}
 {prep.duplicates?.filter(d=>d.issues?.includes('supplier_inactive')).map(d=><p role="status" key={'inactive'+d.folder+d.code}>Attention : {d.folder} / {d.code} — fournisseur inactif. Le tiers associé possède un statut distinct.</p>)}
 {prep.duplicates?.filter(d=>d.issues?.some(x=>x.endsWith('name_differs_from_request'))).map(d=><p key={'name'+d.folder+d.code}>Le nom enregistré pour {d.code} diffère du nom demandé ; aucune correction automatique.</p>)}
 {prep.activation_requested&&<p>Activation demandée : Oui — à vérifier après enregistrement, aucune activation exécutée.</p>}
 {prep.short_name_proposal&&<p>Intitulé court proposé : {prep.short_name_proposal.value} — {prep.short_name_proposal.confirmed?'déclaré':'à confirmer'}.</p>}
 {prep.transport==='direct_sql'&&<><p>Création par SQL dans TEST avec la requête fournisseur enregistrée. Code automatique F + 1.</p>{prep.missing_sql_fields?.length>0&&<p>À compléter : {prep.missing_sql_fields.join(', ')}.</p>}</>}
 {Object.keys(prep.suggested_defaults||{}).length>0&&<><p>Références retrouvées dans le dossier cible — propositions à confirmer :</p><dl>{Object.entries(prep.suggested_defaults).map(([key,value])=><div key={key}><dt>{fields[key]||key}</dt><dd>{value.value}<small> Source : {value.source} · non appliqué</small></dd></div>)}</dl></>}
 <p>Les champs fiscaux sont contrôlés en format et rapprochés des données Sage ; leur validité auprès de l’administration fiscale n’est pas certifiée. La confirmation des données exactes et le mapping d’écriture restent nécessaires.</p>
 {prep.target_folder==='OB'&&<p>Aucune création ou modification dans OB.</p>}
 {partner.operation&&<SupplierResult operation={partner.operation}/>}
 <SupplierActions partner={partner} security={security} busy={busy} onAction={onAction}/>
 </section>;
}
