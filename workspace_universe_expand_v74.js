(function(){
'use strict';

const SESSION_KEY='leadscope_company_universe_expand_started_v74';
let started=false;

async function maybeStartUniverseExpansion(){
  if(started)return;
  started=true;
  try{
    const statsResp=await fetch('/api/company-universe/stats');
    if(!statsResp.ok)return;
    const stats=await statsResp.json();
    const total=Number(stats.total||0);
    if(total>=10000)return;
    if(sessionStorage.getItem(SESSION_KEY)==='1')return;

    const statusResp=await fetch('/api/library/expand/status');
    if(!statusResp.ok)return;
    const status=await statusResp.json();
    if(['running','starting'].includes(String(status.status||''))){
      sessionStorage.setItem(SESSION_KEY,'1');
      decorateUniverseStatus(status);
      return;
    }

    sessionStorage.setItem(SESSION_KEY,'1');
    const start=await fetch('/api/library/expand?target=10000',{method:'POST'});
    if(!start.ok)return;
    const payload=await start.json();
    decorateUniverseStatus(payload);
  }catch(err){
    console.debug('LeadScope Company Universe expansion skipped',err);
  }
}

function decorateUniverseStatus(status){
  const bar=document.querySelector('.v73UniverseBar');
  if(!bar)return;
  let note=bar.querySelector('.v74UniverseStatus');
  if(!note){
    note=document.createElement('div');
    note.className='v74UniverseStatus';
    bar.appendChild(note);
  }
  const current=Number(status.company_count||0);
  const target=Number(status.target||10000);
  const message=String(status.message||'Expanding public company index in the background…');
  note.textContent=current?`${message} · ${current.toLocaleString()} / ${target.toLocaleString()}`:message;
}

async function refreshUniverseStatusOnce(){
  try{
    const response=await fetch('/api/library/expand/status');
    if(!response.ok)return;
    const status=await response.json();
    if(['running','starting'].includes(String(status.status||'')))decorateUniverseStatus(status);
  }catch(e){}
}

function isDiscoverVisible(){
  return Boolean(document.querySelector('#v7DiscoverSearch') && document.querySelector('.v73UniverseBar'));
}

function onDiscoverReady(){
  if(!isDiscoverVisible())return;
  maybeStartUniverseExpansion();
  refreshUniverseStatusOnce();
}

// No MutationObserver: workspace previously had browser-freeze bugs from recursive DOM observers.
// Patch the two public workspace navigation functions instead.
const oldOpen=window.openV7Workspace;
if(typeof oldOpen==='function'){
  window.openV7Workspace=async function(...args){
    const result=await oldOpen.apply(this,args);
    setTimeout(onDiscoverReady,50);
    return result;
  };
}
const oldTab=window.setV7WorkspaceTab;
if(typeof oldTab==='function'){
  window.setV7WorkspaceTab=async function(...args){
    const result=await oldTab.apply(this,args);
    setTimeout(onDiscoverReady,50);
    return result;
  };
}
setTimeout(onDiscoverReady,100);
})();
