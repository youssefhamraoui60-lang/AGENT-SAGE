import React from 'react';
import {SupplierActions} from './SupplierActions.jsx';
import {SupplierResult} from './SupplierResult.jsx';
const fields=[['Statut','Statut fournisseur','statut'],['Nom','Nom du fournisseur','nom'],['NomCourt','Nom court','intitule_court'],['ICE','ICE','ice'],['IF','Identifiant fiscal','identifiant_fiscal'],['RC','Registre de commerce','rc'],['Adresse','Adresse','adresse'],['Ville','Ville','ville'],['Pays','Pays','pays'],['Telephone','Téléphone','telephone'],['Fax','Fax','fax'],['Email','Email','email'],['Paiement','Conditions de paiement','conditions_paiement'],['Devise','Devise','devise'],['TypeLibelle','Prix','type_montant'],['Categorie','Catégorie fournisseur','categorie_fournisseur'],['CodeComptable','Code comptable','code_comptable'],['RegimeTaxe','Régime fiscal','regime_taxe'],['DateRegularite','Date de régularité','date_regularite']];
export function supplierDisplayValue(key,value){
 if(!value||key==='DateRegularite'&&value==='1753-01-01')return 'Non renseigné';
 if(key==='Statut')return ['1','non','inactif','inactive','désactivé','désactivée','desactive','desactivee'].includes(String(value).toLowerCase())?'Désactivé':['2','oui','actif','active'].includes(String(value).toLowerCase())?'Actif':value;
 if(key==='TypeLibelle')return value==='HT'?'Hors taxes (HT)':value==='TTC'?'Toutes taxes comprises (TTC)':value;
 if(key==='Pays'&&value==='MA')return 'Maroc';
 if(key==='Devise'&&value==='MAD')return 'Dirham marocain (MAD)';
 if(key==='DateRegularite'&&/^\d{4}-\d{2}-\d{2}$/.test(value))return value.split('-').reverse().join('/');
 return value;
}
export function SupplierCard({partner,security,busy,onAction,hideActions=false}){
 const op=partner.operation,terminal=['ambiguous','unverified','succeeded','failed'].includes(op?.status);
 const values=op?.status==='invalidated'?{}:op?.parameters||{};
 const displayFields=fields.flatMap(row=>row[0]==='Adresse'&&(values.Adresse2||values.Adresse3)?[['Adresse','Adresse — ligne 1','adresse'],...['Adresse2','Adresse3'].filter(k=>values[k]).map(k=>[k,'Adresse — ligne '+k.slice(-1),'adresse'])]:[row]);
 return <section className="chat-article" aria-label="Fiche fournisseur"><h3>{partner.nom||'Nouveau fournisseur'}</h3>
 {terminal?<SupplierResult operation={op}/>:op?.status==='executing'?<p role="status">Création du fournisseur en cours…</p>:<>
 <p>Voici les informations de la fiche à créer dans {partner.dossier_cible==='OB'?'Production OB':'TEST'}. Vérifiez-les avant de confirmer.</p>
 <div className="chat-table-scroll"><table aria-label="Informations du fournisseur"><thead><tr><th>Information</th><th>Valeur</th><th>Origine</th></tr></thead><tbody>{displayFields.map(([key,label,field])=>{
  const value=values[key]??partner[field],empty=!value||key==='DateRegularite'&&value==='1753-01-01';
  const reference=op?.reference_resolutions?.find(r=>r.field===key);
  const source=partner.document_sources?.[field];
  return <tr key={key}><th scope="row">{label}</th><td>{reference&&key==='Paiement'?reference.requested+' ('+reference.code+')':supplierDisplayValue(key,value)}</td><td>{source?source.filename+', page '+source.page:empty?'À compléter si nécessaire':op?.defaulted_fields?.includes(['Adresse2','Adresse3'].includes(key)?'Adresse':key)?'Valeur habituelle':'Renseigné'}</td></tr>;
 })}</tbody></table></div>
 {partner.forme_juridique&&<p>Forme juridique : <strong>{partner.forme_juridique}</strong></p>}
 <p>Vous pouvez corriger une information dans le chat avant de confirmer.</p>
 {!hideActions&&<SupplierActions partner={partner} security={security} busy={busy} onAction={onAction}/>}
 </>}
 </section>;
}
