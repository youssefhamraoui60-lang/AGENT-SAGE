import React,{useId,useLayoutEffect,useRef,useState} from 'react';

export function CompactTable({columns,rows,label,limit=5}){
 const [expanded,setExpanded]=useState(false),id=useId();
 if(![...columns,...rows.flat()].some(cell=>String(cell??'').trim()))return null;
 const shown=expanded?rows:rows.slice(0,limit);
 return <div className="compact-table"><div className="chat-table-scroll"><table id={id} aria-label={label}><thead><tr>{columns.map((c,i)=><th key={i} scope="col">{c}</th>)}</tr></thead><tbody>{shown.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>{rows.length>limit&&<button type="button" className="expand-link" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(!expanded)}>{expanded?'Voir moins':'Voir plus'}<span className="chat-muted"> · {expanded?rows.length:limit}/{rows.length}</span></button>}</div>;
}

export function ExpandableText({children}){
 const [expanded,setExpanded]=useState(false),[overflow,setOverflow]=useState(false),ref=useRef(null),id=useId();
 useLayoutEffect(()=>{const el=ref.current;if(!el)return;const measure=()=>{if(!expanded)setOverflow(el.scrollHeight>el.clientHeight+2);};measure();const observer=new ResizeObserver(measure);observer.observe(el);return()=>observer.disconnect();},[children,expanded]);
 return <div className="expandable-text"><div ref={ref} id={id} className={expanded?'':'text-preview'} style={{whiteSpace:'pre-wrap'}}>{children}</div>{(overflow||expanded)&&<button type="button" className="expand-link" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(!expanded)}>{expanded?'Voir moins':'Voir plus'}</button>}</div>;
}
