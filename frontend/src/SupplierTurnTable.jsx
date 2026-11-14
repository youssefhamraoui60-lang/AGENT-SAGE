import React from 'react';
import {supplierDisplayValue} from './SupplierCard.jsx';
import {CompactTable} from './CompactTable.jsx';

export function SupplierTurnTable({snapshot,payments=[],historical=false}){
 if(historical)return <details className="supplier-snapshot-history"><summary>Ancienne fiche : {snapshot.name||"Fournisseur"}</summary><SupplierTurnTable snapshot={snapshot} payments={payments}/></details>;
 const addressProvided=snapshot.rows.some(row=>row.key==='Adresse'&&row.value&&['declared','document'].includes(row.origin));
 const priority=['Nom',...(addressProvided?['Adresse']:[]),'Ville','FormeJuridique','ICE','Paiement'];
 const rows=[...snapshot.rows].sort((a,b)=>(priority.includes(a.key)?priority.indexOf(a.key):99)-(priority.includes(b.key)?priority.indexOf(b.key):99));
 return <section className="supplier-turn-table" aria-label="Récapitulatif fournisseur à cette étape"><h4>{snapshot.name||'Fournisseur à compléter'}</h4><CompactTable label="Valeurs du fournisseur à cette étape" columns={['Information','Valeur','Origine']} rows={rows.map(row=>[row.label,row.key==='Paiement'?(payments.find(p=>p.code===row.value)?.label||supplierDisplayValue(row.key,row.value)):supplierDisplayValue(row.key,row.value),row.source?row.source.filename+', page '+row.source.page:row.origin==='default'?'Modèle':row.origin==='missing'?'Non renseigné':'Renseigné'])}/></section>;
}
