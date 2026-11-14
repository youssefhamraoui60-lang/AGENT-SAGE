import React from 'react';
import {supplierResult} from './supplierResult.js';
export function SupplierResult({operation}){
 const result=supplierResult(operation);if(!result)return null;
 const row=result.record;
 return <section role="status" aria-label="Résultat fournisseur"><strong>{result.label}</strong>{result.code&&<p>Code : {result.code} · Dossier {operation.folder||'TEST'}</p>}
 {row&&<><h3>{row.BPSNUM_0} — {row.BPSNAM_0}</h3><dl>{Object.entries({Catégorie:row.BSGCOD_0,ICE:row.XICE_0,IF:row.XIF_0,RC:row.XRC_0,Pays:row.CRY_0,Devise:row.CUR_0,Statut:row.supplier_active===2?'Actif':'À vérifier'}).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></>}
 <p>{result.message}</p></section>;
}
