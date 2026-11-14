import React,{useEffect,useState} from 'react';

export function formatDuration(milliseconds){
 const seconds=Math.max(0,Math.floor(milliseconds/1000));
 return seconds<60?`${seconds} s`:`${Math.floor(seconds/60)} min ${seconds%60} s`;
}

export function responseMilliseconds(messages,index){
 if(messages[index]?.role!=='assistant'||messages[index-1]?.role!=='user')return null;
 const start=Date.parse(messages[index-1].created_at),end=Date.parse(messages[index].created_at);
 return Number.isFinite(start)&&Number.isFinite(end)&&end>=start?end-start:null;
}

export function ResponseTime({milliseconds}){
 return milliseconds===null?null:<span className="response-time">Réponse en {formatDuration(milliseconds)}</span>;
}

export function WaitingTime({startedAt}){
 const [mountedAt]=useState(()=>Date.now()),[now,setNow]=useState(()=>Date.now());
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
 const parsed=Date.parse(startedAt),start=Number.isFinite(parsed)?parsed:mountedAt;
 return <span className="response-time waiting-time" aria-label="Temps écoulé">{formatDuration(now-start)}</span>;
}
