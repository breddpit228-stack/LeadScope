(function(){
'use strict';

const STATE_KEY='leadscope_workspace_state_v77';
let currentWorkspace=null;
let currentTab='discover';
let pendingTab=null;
let navigationRunning=false;
let navigationPromise=Promise.resolve();
let restoreStarted=false;
const discoverControllers=new Set();
const nativeFetch=window.fetch.bind(window);

function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
function normalizeTab(tab){return tab==='selected'||tab==='research'?'shortlist':(['discover','shortlist','results'].includes(tab)?tab:'discover')}
function readState(){
  try{return JSON.parse(sessionStorage.getItem(STATE_KEY)||'{}')||{}}catch(e){return {}}
}
function saveState(patch={}){
  try{
    const previous=readState();
    const next={...previous,...patch};
    if(currentWorkspace)next.workspaceId=currentWorkspace;
    if(currentTab)next.tab=currentTab;
    sessionStorage.setItem(STATE_KEY,JSON.stringify(next));
    return next;
  }catch(e){return {}}
}
function clearState(){try{sessionStorage.removeItem(STATE_KEY)}catch(e){}}
function isDiscoverRequest(url){
  const value=String(url||'');
  return value.includes('/api/company-universe/stats')||value.includes('/api/library/expand/status')||/\/api\/workspaces\/[^/]+\/discover/.test(value);
}
function cancelDiscoverRequests(){
  discoverControllers.forEach(controller=>{try{controller.abort()}catch(e){}});
  discoverControllers.clear();
}
window.fetch=function(input,init={}){
  const url=typeof input==='string'?input:(input&&input.url)||'';
  if(!isDiscoverRequest(url)||init.signal)return nativeFetch(input,init);
  const controller=new AbortController();
  discoverControllers.add(controller);
  return nativeFetch(input,{...init,signal:controller.signal}).finally(()=>discoverControllers.delete(controller));
};

function setVisualTab(tab){
  document.querySelectorAll('[data-v7-tab]').forEach(button=>button.classList.toggle('active',button.dataset.v7Tab===tab));
}
async function settleLeavingDiscover(){
  // Let any setTimeout(0) Discover renderer start, then abort every request it owns
  // before the next tab paints. This prevents stale Discover HTML from winning a race.
  await sleep(0);
  cancelDiscoverRequests();
  await sleep(35);
  cancelDiscoverRequests();
  await sleep(15);
}
function isDiscoverLoading(){
  const host=document.querySelector('#v73BestSection');
  if(!host)return true;
  return /Finding strong matches/i.test(host.textContent||'');
}
async function waitDiscoverSettled(timeout=5500){
  const started=Date.now();
  while(Date.now()-started<timeout){
    if(currentTab!=='discover')return false;
    if(document.querySelector('#v7DiscoverSearch')&&!isDiscoverLoading())return true;
    await sleep(60);
  }
  return Boolean(document.querySelector('#v7DiscoverSearch'));
}
function ensureSearchSummary(text){
  let el=document.getElementById('v77SearchSummary');
  if(!text){el?.remove();return}
  if(!el){
    el=document.createElement('div');
    el.id='v77SearchSummary';
    el.style.cssText='margin:8px 0 10px;font-size:10px;color:#667085';
    const bar=document.querySelector('.v7DiscoverBar');
    bar?.insertAdjacentElement('afterend',el);
  }
  if(el)el.textContent=text;
}
async function captureDiscoverResult(){
  if(currentTab!=='discover')return;
  const settled=await waitDiscoverSettled();
  if(!settled||currentTab!=='discover')return;
  const input=document.getElementById('v7DiscoverSearch');
  const metric=document.getElementById('v7MatchMetric');
  if(!input||!metric)return;
  const query=String(input.value||'').trim();
  const state=readState();
  const currentCount=Number(String(metric.textContent||'').replace(/[^0-9]/g,''));
  if(!query){
    const marketMatches=Number.isFinite(currentCount)?currentCount:(state.marketMatches||null);
    saveState({query:'',page:state.page||1,marketMatches});
    ensureSearchSummary('');
    return;
  }
  const searchCount=Number.isFinite(currentCount)?currentCount:0;
  if(state.marketMatches!=null)metric.textContent=String(state.marketMatches);
  saveState({query,page:state.page||1,searchCount});
  const broader=document.querySelector('#v73BroaderSection .v73BroaderHead p');
  const broaderCount=broader?Number((broader.textContent.match(/\d+/)||[0])[0]):0;
  ensureSearchSummary(`Search results · ${searchCount} strong${broaderCount?` · ${broaderCount} broader`:''}`);
}
function scheduleDiscoverCapture(delay=0){setTimeout(()=>captureDiscoverResult().catch(()=>{}),delay)}

const oldOpenWorkspace=window.openV7Workspace;
if(typeof oldOpenWorkspace==='function'){
  window.openV7Workspace=async function(id,tab='discover'){
    const target=normalizeTab(tab);
    currentWorkspace=String(id||'');
    currentTab=target;
    setVisualTab(target);
    saveState({workspaceId:currentWorkspace,tab:target});
    if(target!=='discover')await settleLeavingDiscover();
    const out=await oldOpenWorkspace.call(this,id,target);
    setVisualTab(currentTab);
    saveState({workspaceId:currentWorkspace,tab:currentTab});
    if(currentTab==='discover')scheduleDiscoverCapture(80);
    return out;
  };
}

const oldSetTab=window.setV7WorkspaceTab;
async function processPendingTabs(){
  if(navigationRunning)return navigationPromise;
  navigationRunning=true;
  navigationPromise=(async()=>{
    try{
      while(pendingTab){
        const target=pendingTab;
        pendingTab=null;
        if(target!=='discover')await settleLeavingDiscover();
        await oldSetTab.call(window,target);
        currentTab=target;
        setVisualTab(target);
        saveState({tab:target});
        if(target==='discover')scheduleDiscoverCapture(80);
      }
    }finally{navigationRunning=false}
  })();
  return navigationPromise;
}
if(typeof oldSetTab==='function'){
  window.setV7WorkspaceTab=function(tab){
    const target=normalizeTab(tab);
    pendingTab=target;
    currentTab=target;
    setVisualTab(target);
    saveState({tab:target});
    return processPendingTabs();
  };
}

const oldGoPage=window.goV73DiscoverPage;
if(typeof oldGoPage==='function'){
  window.goV73DiscoverPage=function(page){
    const safe=Math.max(1,Number(page)||1);
    saveState({page:safe,query:String(document.getElementById('v7DiscoverSearch')?.value||'').trim()});
    const out=oldGoPage.call(this,safe);
    scheduleDiscoverCapture(80);
    return out;
  };
}
const oldRunSearch=window.runV7DiscoverSearch;
if(typeof oldRunSearch==='function'){
  window.runV7DiscoverSearch=function(){
    const query=String(document.getElementById('v7DiscoverSearch')?.value||'').trim();
    saveState({query,page:1});
    const out=oldRunSearch.apply(this,arguments);
    scheduleDiscoverCapture(80);
    return out;
  };
}

document.addEventListener('input',event=>{
  if(event.target?.id!=='v7DiscoverSearch')return;
  saveState({query:String(event.target.value||'').trim(),page:1});
  scheduleDiscoverCapture(650);
},true);

const previousShowWorkspace=window.showWorkspace;
if(typeof previousShowWorkspace==='function'){
  window.showWorkspace=function(view='workspaces'){
    if(view==='workspaces'){
      currentWorkspace=null;currentTab='discover';cancelDiscoverRequests();clearState();
    }
    return previousShowWorkspace.apply(this,arguments);
  };
}

async function restoreState(){
  if(restoreStarted)return;
  restoreStarted=true;
  const state=readState();
  if(!state.workspaceId||typeof window.openV7Workspace!=='function')return;
  currentWorkspace=String(state.workspaceId);
  currentTab=normalizeTab(state.tab||'discover');
  try{
    await window.openV7Workspace(currentWorkspace,currentTab);
    if(currentTab!=='discover')return;
    const started=Date.now();
    while(!document.getElementById('v7DiscoverSearch')&&Date.now()-started<4000)await sleep(50);
    const input=document.getElementById('v7DiscoverSearch');
    if(!input)return;
    const query=String(state.query||'');
    if(query){
      input.value=query;
      window.runV7DiscoverSearch?.();
      await waitDiscoverSettled();
    }
    const page=Math.max(1,Number(state.page)||1);
    if(page>1){
      // renderV73Discover stores its query synchronously when search starts, so paging now
      // preserves the same query without another competing render.
      cancelDiscoverRequests();
      await sleep(25);
      window.goV73DiscoverPage?.(page);
      await waitDiscoverSettled();
    }
    await captureDiscoverResult();
  }catch(err){
    console.debug('LeadScope workspace state restore skipped',err);
    clearState();
  }
}

setTimeout(()=>restoreState(),120);
})();
