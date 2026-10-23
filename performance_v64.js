(function(){
let suggestionRequestId=0;

function renderSuggestionItems(items){
  const root=document.querySelector('#todaySuggestions');
  if(!root)return;
  if(!items||!items.length){
    root.innerHTML='<div class="emptyV2"><h3>No suggestions yet</h3><p>Open Company Library or adjust your Offer & ICP.</p></div>';
    return;
  }
  root.innerHTML=items.slice(0,6).map(a=>`<article class="suggestionCard"><h3>${esc(a.company)}</h3><div class="meta">${esc([a.company_type,a.country,a.audience].filter(Boolean).join(' · '))}</div><p>${esc(a.description||'Basic public company profile available.')}</p><div class="suggestionScore"><span>${esc((a.icp_prefilter||{}).label||'Basic match')}</span><b>${(a.icp_prefilter||{}).score||0}/100</b></div><div class="suggestionActions"><button class="secondary small" onclick="addToWorkspace(${a.id})">+ Workspace</button><button class="primary small" onclick="researchCompany(${a.id})">Research</button></div></article>`).join('');
}

async function loadTodaySuggestions(){
  const root=document.querySelector('#todaySuggestions');
  if(!root)return;
  const requestId=++suggestionRequestId;
  root.innerHTML='<div class="emptyV2"><h3>Finding suggested accounts…</h3><p>Today is already usable while this small Library query runs.</p></div>';
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),5000);
  try{
    const response=await fetch('/api/workspace-v2/suggestions?limit=6',{signal:controller.signal});
    if(!response.ok)throw new Error('Suggestion request failed');
    const data=await response.json();
    if(requestId!==suggestionRequestId)return;
    renderSuggestionItems(data.items||[]);
  }catch(err){
    if(requestId!==suggestionRequestId)return;
    root.innerHTML='<div class="emptyV2"><h3>Suggestions unavailable</h3><p>Workspace is still ready. Open Company Library when you want to browse more accounts.</p></div>';
  }finally{
    clearTimeout(timer);
  }
}

const previousShow=window.showWorkspace;
if(previousShow){
  window.showWorkspace=function(view='today'){
    const result=previousShow(view);
    const normalized=({overview:'today',companies:'accounts',opportunities:'opportunitiesV2'})[view]||view;
    if(normalized==='today')setTimeout(loadTodaySuggestions,0);
    return result;
  };
}

// If the workspace was already open when this patch loaded, hydrate suggestions safely.
setTimeout(()=>{
  const page=document.querySelector('#todayV2Page');
  if(page&&!page.classList.contains('hidden'))loadTodaySuggestions();
},0);
})();
