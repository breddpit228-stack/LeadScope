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
  const script=document.createElement('script');
  script.src='/assets/workspace-v70.js?v=7.0';
  script.async=false;
  script.dataset.leadscopeWorkspaceV7='1';
  script.onerror=()=>console.error('LeadScope Workspace v7 UI failed to load.');
  document.body.appendChild(script);
})();
