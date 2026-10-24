(function(){
let activeResearchId=null;

function setResearchButtonsDisabled(disabled){
  document.querySelectorAll('button').forEach(btn=>{
    const text=String(btn.textContent||'');
    if(/research/i.test(text))btn.disabled=disabled;
  });
}

function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms))}

async function fetchWithTimeout(url,options={},timeoutMs=7000){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    return await fetch(url,{...options,signal:controller.signal});
  }finally{
    clearTimeout(timer);
  }
}

async function hydrateResearchCompanyName(id){
  try{
    const r=await fetchWithTimeout('/api/companies/'+id,{},2200);
    if(!r.ok)return;
    const c=await r.json();
    window.__lsResearchCompany=c.company||'Company';
    if(typeof window.showProgress==='function')window.showProgress('Preparing research…','queued',3);
  }catch(e){}
}

async function pollResearchJob(jobId,companyId){
  const started=Date.now();
  while(Date.now()-started<105000){
    await sleep(1100);
    let response;
    try{
      response=await fetchWithTimeout('/api/jobs/'+jobId,{},6000);
    }catch(err){
      if(err?.name==='AbortError')continue;
      throw err;
    }
    if(!response.ok){
      let detail='Could not read research status.';
      try{const body=await response.json();detail=body.detail||detail}catch(e){}
      throw new Error(detail);
    }
    const job=await response.json();
    if(typeof window.showProgress==='function')window.showProgress(job.message||'Researching…',job.stage||'researching',job.percent||0);
    if(job.status==='done'){
      if(typeof window.hideProgress==='function')window.hideProgress();
      if(typeof window.openCompany==='function')await window.openCompany(companyId);
      return job;
    }
    if(job.status==='error'){
      if(typeof window.hideProgress==='function')window.hideProgress();
      if(typeof window.openCompany==='function')await window.openCompany(companyId);
      throw new Error(job.error||job.message||'Research failed.');
    }
  }
  throw new Error('Research exceeded the UI safety limit.');
}

window.researchCompany=async function(id){
  id=Number(id);
  if(!Number.isFinite(id)||id<=0){alert('Invalid company id.');return null}
  if(activeResearchId!==null)return null;

  activeResearchId=id;
  window.__lsResearchActive=true;
  window.__lsResearchCompany='Company';
  setResearchButtonsDisabled(true);
  if(typeof window.showProgress==='function')window.showProgress('Starting research…','queued',2);
  hydrateResearchCompanyName(id);

  try{
    const response=await fetchWithTimeout('/api/companies/'+id+'/analyze',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({fetch_live:true,provider:'gemini'})
    },10000);
    let data={};
    try{data=await response.json()}catch(e){}
    if(!response.ok)throw new Error(data.detail||'Could not start research.');
    if(!data.job_id)throw new Error('Research job was not created.');
    return await pollResearchJob(data.job_id,id);
  }catch(err){
    if(typeof window.hideProgress==='function')window.hideProgress();
    console.error('LeadScope research failed to start or complete',err);
    alert('Research error: '+(err?.message||'Unknown error'));
    return null;
  }finally{
    activeResearchId=null;
    window.__lsResearchActive=false;
    setResearchButtonsDisabled(false);
  }
};

window.researchAndAddToWorkspace=function(id){
  fetch('/api/workspace-v2/accounts/'+id,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({state:'queue'})
  }).catch(()=>{});
  return window.researchCompany(id);
};
})();

/* Workspace v7 is intentionally loaded last, after all legacy compatibility layers. */
(function(){
  if(document.querySelector('script[data-leadscope-workspace-v7]'))return;

  function installWorkspaceUniverseExpansion(){
    const SESSION_KEY='leadscope_company_universe_expand_started_v74';
    let checked=false;

    function decorate(status){
      const bar=document.querySelector('.v73UniverseBar');
      if(!bar)return;
      let note=bar.querySelector('.v74UniverseStatus');
      if(!note){
        note=document.createElement('div');
        note.className='v74UniverseStatus';
        note.style.cssText='width:100%;margin-top:7px;font-size:10px;color:#667085';
        bar.appendChild(note);
      }
      const current=Number(status.company_count||0),target=Number(status.target||10000);
      const message=String(status.message||'Expanding public company index in the background…');
      note.textContent=current?`${message} · ${current.toLocaleString()} / ${target.toLocaleString()}`:message;
    }

    async function maybeStart(){
      if(checked||!document.querySelector('#v7DiscoverSearch'))return;
      checked=true;
      try{
        const statsResponse=await fetch('/api/company-universe/stats');
        if(!statsResponse.ok)return;
        const stats=await statsResponse.json();
        if(Number(stats.total||0)>=10000)return;

        const statusResponse=await fetch('/api/library/expand/status');
        if(!statusResponse.ok)return;
        const status=await statusResponse.json();
        if(['running','starting'].includes(String(status.status||''))){
          sessionStorage.setItem(SESSION_KEY,'1');decorate(status);return;
        }
        if(sessionStorage.getItem(SESSION_KEY)==='1')return;

        sessionStorage.setItem(SESSION_KEY,'1');
        const startResponse=await fetch('/api/library/expand?target=10000',{method:'POST'});
        if(startResponse.ok)decorate(await startResponse.json());
      }catch(err){console.debug('LeadScope Company Universe expansion skipped',err)}
    }

    function onDiscoverReady(){setTimeout(maybeStart,80)}
    const oldOpen=window.openV7Workspace;
    if(typeof oldOpen==='function')window.openV7Workspace=async function(...args){checked=false;const out=await oldOpen.apply(this,args);onDiscoverReady();return out};
    const oldTab=window.setV7WorkspaceTab;
    if(typeof oldTab==='function')window.setV7WorkspaceTab=async function(...args){checked=false;const out=await oldTab.apply(this,args);onDiscoverReady();return out};
    onDiscoverReady();
  }

  const css=document.createElement('link');
  css.rel='stylesheet';css.href='/assets/workspace-v70.css?v=7.4';document.head.appendChild(css);
  const contextCss=document.createElement('link');
  contextCss.rel='stylesheet';contextCss.href='/assets/workspace-v73.css?v=7.4';document.head.appendChild(contextCss);
  const script=document.createElement('script');
  script.src='/assets/workspace-v70.js?v=7.4';
  script.async=false;
  script.dataset.leadscopeWorkspaceV7='1';
  script.onerror=()=>console.error('LeadScope Workspace v7 UI failed to load.');
  script.onload=()=>{
    const context=document.createElement('script');
    context.src='/assets/workspace-v73.js?v=7.4';
    context.async=false;
    context.onerror=()=>console.error('LeadScope Workspace v7.3 context layer failed to load.');
    context.onload=installWorkspaceUniverseExpansion;
    document.body.appendChild(context);
  };
  document.body.appendChild(script);
})();
