import React from 'react';
import {CompactTable,ExpandableText} from './CompactTable.jsx';
// Text-only renderer: no HTML interpretation or new Markdown dependency.
export function MessageContent({content}){
 const lines=String(content||'').split('\n'),blocks=[];
 const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
 for(let i=0;i<lines.length;){
  if(lines[i].trim().startsWith('|')&&i+1<lines.length&&/^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(lines[i+1])){
   const header=cells(lines[i]),rows=[];i+=2;
   while(i<lines.length&&lines[i].trim().startsWith('|'))rows.push(cells(lines[i++]));
   blocks.push(<CompactTable key={i} label="Tableau de la réponse" columns={header} rows={rows.map(row=>header.map((_,k)=>row[k]||''))}/>);
  }else{const text=[];do{text.push(lines[i++]);}while(i<lines.length&&!lines[i].trim().startsWith('|'));blocks.push(<ExpandableText key={i}>{text.join('\n').trim()}</ExpandableText>);}
 }
 return <>{blocks}</>;
}
