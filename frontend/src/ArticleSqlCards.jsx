import React from 'react';
import {CompactTable} from './CompactTable.jsx';
const yes=v=>Number(v)===2?'Oui':Number(v)===1?'Non':'À préciser';
const stock=v=>({'1':'Non géré en stock','2':'Géré en stock','3':'Géré avec titre'}[String(v)]||'À préciser');
const flags=[['achete','Acheté'],['vendu','Vendu'],['fabrique','Fabriqué'],['livrable','Livrable'],['sous_traite','Sous-traité'],['receptionne','Réceptionné']];
export function sqlConfirmed(item){const op=item.operation,r=op?.result;return op?.status==='succeeded'&&op.verification?.sql_verified===true&&r?.ok===true&&['TEST','OB'].includes(op.folder)&&r.folder===op.folder&&r.folder===op.plan?.folder&&r.transaction_state==='COMMIT'&&r.executed===true&&r.code===op.plan?.code;}
function Rows({rows,label}){return <CompactTable label={label} columns={['Information','Valeur']} rows={rows.map(([k,v])=>[k,v||'Non renseign\u00e9'])}/>;}
export function ArticleSqlCard({article:a,session,busy,onAction}){
 const op=a.operation,s=op?.summary||{},created=sqlConfirmed(a),terminal=['executing','ambiguous','unverified','failed','succeeded'].includes(op?.status);
 const sites=s.sites||a.requested_sites||(a.site?[a.site]:[]),providers=s.suppliers||a.fournisseurs||[];
 const rows=[['Code article',a.code_article],['Désignation',a.designation],['Catégorie',s.category||a.categorie||a.categorie_libelle],['Gestion de stock',stock(s.gestion_stock||a.gestion_stock)],['Sites à créer',sites.join(', ')],['Unité',s.unit||a.unite],['Code comptable',s.accounting||a.code_comptable],['Code taxe',s.tax||a.code_tva],['Statut article',s.status||a.statut_article],...flags.map(([f,label])=>[label,yes(s[f]??a[f])]),['Flag fournisseur',yes(s.flag_fournisseur??a.flag_fournisseur)],['Fournisseur principal (facultatif)',s.principal||a.fournisseur_principal||(a.supplier_intent==='none'?'Aucun':'')],['Traduction française',s.translation==='FRA'?'Prévue : '+a.designation:'À préparer'],['Paramètres complémentaires issus du modèle',s.model]];
 if(typeof a.allow_negative_stock==='boolean')rows.splice(4,0,['Stock négatif autorisé',a.allow_negative_stock?'Oui':'Non']);
 if(a.coefficient_vente_declare)rows.splice(7,0,['Coefficient de vente déclaré — non appliqué',a.coefficient_vente_declare]);
 return <section className="chat-article" aria-label={'Fiche article SQL '+(a.dossier_cible||'TEST')}><h3>{a.designation||'Article à compléter'}</h3><strong>{created?'Creation enregistree dans '+(op?.folder==='OB'?'Production OB':'TEST'):op?.status==='executing'?'Création en cours…':'Brouillon — non créé'}</strong><Rows rows={rows} label="Paramètres article avant confirmation"/>
 {providers.length>0&&<><h4>Référencements fournisseurs à confirmer</h4><CompactTable label={"R\u00e9f\u00e9rences fournisseurs"} columns={['Fournisseur','R\u00e9f\u00e9rence','Origine']} rows={providers.map(p=>[p.code,p.reference||'\u00c0 pr\u00e9parer',p.generated?'Propos\u00e9e':'Renseign\u00e9e'])}/></>}
 {s.copied_defaults&&<details><summary>Familles et paramètres repris du modèle</summary><Rows rows={Object.entries(s.copied_defaults)} label="Paramètres complémentaires du modèle"/></details>}
 {op?.message&&<p role="status">{op.message}</p>}{(a.sql_blockers||[]).map(v=><p className="chat-error" key={v}>{v}</p>)}
 {created&&<p>Enregistrements contrôlés dans la transaction. Consultation Sage : {op.verification.sage_consultation_verified?'concordante':'à vérifier'}. Les opérations métier restent à tester.</p>}
 {!terminal&&<div className="panel-actions"><button disabled={busy||!onAction} onClick={()=>onAction(a,'prepare',false)}>Vérifier la fiche</button>{['prepared','approved'].includes(op?.status)&&a.execution?.security?.ready&&<button className="primary" disabled={busy||!onAction} onClick={()=>onAction(a,op.status==='approved'?'execute':'approve',true)}>Confirmer la création dans {op?.folder==='OB'?'Production OB':'TEST'}</button>}</div>}
 {session.supplier_security?.blockers?.some(b=>b.includes('Pilote MCP'))&&<p>Ce pilote conserve les brouillons et les consultations. Les créations sont désactivées.</p>}
 </section>;
}
export function CategorySqlCard({draft:d,busy,onAction}){
 const op=d.operation,created=sqlConfirmed(d),terminal=['executing','succeeded','ambiguous','unverified','failed'].includes(op?.status);
 const rows=[['Code',d.code],['Libellé',d.designation],['Nom court',d.nom_court],['Modèle',d.modele],['Gestion de stock',stock(d.gestion_stock)],...flags.map(([f,label])=>[label,yes(d[f])]),['Unité',d.unite],['Code comptable',d.code_comptable],['Taxe',d.taxe]];
 return <section className="chat-article" aria-label="Catégorie à confirmer"><h3>Catégorie {d.code}</h3><strong>{created?'Creation enregistree dans '+(op?.folder==='OB'?'Production OB':'TEST'):'Brouillon catégorie — non créé'}</strong><Rows rows={rows} label="Paramètres catégorie avant confirmation"/>{op?.message&&<p role="status">{op.message}</p>}
 <p>Vous pouvez corriger le libellé et les paramètres dans la conversation avant de confirmer.</p>
 {!terminal&&<div className="panel-actions"><button disabled={busy} onClick={()=>onAction(d,'prepare')}>Vérifier la catégorie</button>{['prepared','approved'].includes(op?.status)&&<button className="primary" disabled={busy} onClick={()=>onAction(d,op.status==='approved'?'execute':'approve')}>Confirmer la création de la catégorie dans {op?.folder==='OB'?'Production OB':'TEST'}</button>}</div>}
 </section>;
}
