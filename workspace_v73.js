(function(){
'use strict';

const INDUSTRIES=[
  'Fintech','Software & SaaS','AI & Data','Cybersecurity','Marketing & AdTech','Sales & RevOps',
  'HR & Recruiting','E-commerce & Retail','Marketplaces','Logistics & Supply Chain','Climate & Energy',
  'Health & Life Sciences','Professional Services','Manufacturing','Real Estate & PropTech',
  'Education & EdTech','Telecom','Travel & Hospitality'
];
const REGIONS=['Europe','Poland','Germany','United Kingdom','France','Netherlands','Sweden','Denmark','Norway','Finland','Spain','Italy','Czechia','Austria','Switzerland','Belgium','Ireland','Estonia','Lithuania','Latvia','Portugal','Romania','Ukraine'];
const SIZES=['1–10','11–50','51–200','201–500','501–1000','1001–5000','5000+'];
let activeContext=null;
let activeCompanyId=null;
let activeWorkspaceId=null;
let discoverPage=1;
let discoverQuery='';
let universeStats=null;

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function shortSource(v){
  const text=String(v||'public data');
  if(/wikidata/i.test(text))return 'Wikidata';
  if(/accelerator/i.test(text))return 'Public startup data';
  if(/legacy_seed/i.test(text))return 'LeadScope seed';
  if(/manual/i.test(text))return 'Manual';
  return text.length>34?text.slice(0,31)+'…':text;
}
function qualityLabel(p){const n=Number(p.completeness||0);return n>=70?'Good':n>=50?'Partial':'Basic'}
function qualityClass(p){const n=Number(p.completeness||0);return n>=70?'good':n>=50?'warn':'neutral'}

function replaceInputWithSelect(id,values,placeholder){
  const el=document.getElementById(id);if(!el||el.tagName==='SELECT')return el;
  const current=el.value||'';
  const select=document.createElement('select');
  select.id=id;select.className=el.className||'';
  const opts=[`<option value="">${esc(placeholder)}</option>`];
  if(current && !values.includes(current))opts.push(`<option value="${esc(current)}">${esc(current)}</option>`);
  values.forEach(v=>opts.push(`<option value="${esc(v)}">${esc(v)}</option>`));
  select.innerHTML=opts.join('');select.value=current;
  el.replaceWith(select);return select;
}
function installTaxonomy(){
  replaceInputWithSelect('v7WsIndustry',INDUSTRIES,'Choose category…');
  replaceInputWithSelect('v7WsRegion',REGIONS,'Choose country / region…');
  replaceInputWithSelect('v7WsSize',SIZES,'Choose company size…');
}

async function fetchContext(workspaceId,companyId){
  const r=await fetch(`/api/workspaces/${workspaceId}/companies/${companyId}/context`);
  if(!r.ok)return null;
  return await r.json();
}
async function getUniverseStats(){
  if(universeStats)return universeStats;
  try{const r=await fetch('/api/company-universe/stats');if(r.ok)universeStats=await r.json()}catch(e){}
  return universeStats||{};
}

function metricRows(items){
  return (items||[]).map(x=>`<div class="scoreRow"><div class="scorePts">${Number(x.points||0)>=0?'+':''}${esc(x.points||0)}/${esc(x.max_points??'')}</div><div class="scoreCrit">${esc(x.criterion||x.label||'Criterion')}</div><div class="scoreReason">${esc(x.reason||'')}</div></div>`).join('');
}
function applyContext(){
  if(!activeContext)return;
  const intel=activeContext.intelligence||{},decision=activeContext.decision||{},workspace=activeContext.workspace||{};
  const metrics=document.querySelector('#reportMetrics .reportMetrics');
  if(metrics){
    const first=metrics.querySelector('.reportMetric');
    if(first){
      const label=first.querySelector('.label'),num=first.querySelector('b'),p=first.querySelector('p');
      if(label)label.textContent='Workspace fit';
      if(num)num.textContent=decision.fit==null?'—':String(decision.fit);
      const suffix=first.querySelector('span');if(suffix)suffix.textContent=decision.fit==null?'':'/100';
      if(p)p.textContent=intel.fit_summary||`Fit to workspace '${workspace.name||'targeting'}'.`;
    }
  }
  const meta=document.querySelector('#reportHeader .reportMeta');
  if(meta && !meta.querySelector('.v73WorkspaceBadge'))meta.insertAdjacentHTML('beforeend',`<span class="badge neutral v73WorkspaceBadge">Workspace · ${esc(workspace.name||'')}</span>`);

  const briefTitle=[...document.querySelectorAll('#reportContent .reportCard h4')].find(x=>x.textContent.trim()==='Company brief');
  if(briefTitle){const card=briefTitle.closest('.reportCard');const p=card?.querySelector('p');if(p)p.textContent=intel.fit_summary||`Workspace-specific analysis for ${workspace.name||'this project'}.`;}

  const scoreTitle=[...document.querySelectorAll('#reportContent .reportCard h3')].find(x=>x.textContent.trim()==='Why this score');
  if(scoreTitle){
    const card=scoreTitle.closest('.reportCard');
    if(card){card.innerHTML=`<h3>Why this workspace fit</h3><div class="scoreList">${metricRows(intel.score_breakdown||[])||'<p>No workspace-specific score breakdown yet.</p>'}</div>`;}
  }

  const opportunity=document.querySelector('#reportContent .opportunityCard');
  if(opportunity){
    const hyp=(intel.hypotheses||[])[0]||{};
    const title=hyp.title||'No workspace-specific opportunity generated yet.';
    const rationale=hyp.rationale||intel.suggested_angle||'Run workspace research to generate an offer-specific opportunity.';
    opportunity.innerHTML=`<h4>Workspace opportunity</h4><div class="opTitle">${esc(title)}</div><p>${esc(rationale)}</p><div class="opportunityMeta">${hyp.confidence?`<span class="badge warn">${esc(hyp.confidence)} confidence</span>`:''}${hyp.target_role?`<span class="badge neutral">${esc(hyp.target_role)}</span>`:''}</div>${hyp.recommended_action?`<div style="margin-top:16px"><h4>Next action</h4><p><strong>${esc(hyp.recommended_action)}</strong></p></div>`:''}`;
  }

  const angleTitle=[...document.querySelectorAll('#reportContent .reportCard h3')].find(x=>x.textContent.trim()==='Recommended angle');
  if(angleTitle){const p=angleTitle.closest('.reportCard')?.querySelector('p');if(p)p.textContent=intel.suggested_angle||'No workspace-specific angle generated yet.';}

  const opener=document.getElementById('openerEdit'),email=document.getElementById('emailEdit');
  if(opener && document.activeElement!==opener)opener.value=intel.personalized_opener||'';
  if(email && document.activeElement!==email)email.value=intel.email_draft||'';

  const refresh=document.querySelector('#reportHeader button.secondary');
  if(refresh){refresh.textContent='Refresh workspace research';refresh.onclick=()=>refreshWorkspaceCompany();}
}

function discoverEmpty(title,text){return `<div class="v7EmptyInline"><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`}
async function renderV73Discover(page=discoverPage,q=discoverQuery){
  if(!activeWorkspaceId)return;
  discoverPage=Math.max(1,Number(page)||1);discoverQuery=String(q||'').trim();
  const body=document.querySelector('#v7TabBody');if(!body)return;
  const stats=await getUniverseStats();
  const sourceText=(stats.sources||[]).slice(0,3).map(x=>`${shortSource(x.source)} ${Number(x.count||0).toLocaleString()}`).join(' · ')||'Public company sources';
  body.innerHTML=`<div class="v73UniverseBar"><div><strong>Company Universe</strong><span>${Number(stats.total||0).toLocaleString()} indexed · ${Number(stats.with_website||0).toLocaleString()} with websites · ${Number(stats.with_description||0).toLocaleString()} described</span></div><small>${esc(sourceText)}</small></div><div class="v7DiscoverBar"><input id="v7DiscoverSearch" placeholder="Search within this market…" value="${esc(discoverQuery)}"><button class="secondary" onclick="runV7DiscoverSearch()">Search</button></div><div class="v7Hint">Discover searches LeadScope's local Company Universe. Profile match is based on the workspace criteria and basic public company data — it is not the deep research Fit score.</div><div class="v7CompanyList"><div class="v7EmptyInline">Finding matching companies…</div></div><div id="v73Pager"></div>`;
  const input=document.getElementById('v7DiscoverSearch');
  let timer=null;input?.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>renderV73Discover(1,input.value),450)});
  try{
    const r=await fetch(`/api/workspaces/${activeWorkspaceId}/discover?limit=40&page=${discoverPage}&q=${encodeURIComponent(discoverQuery)}`);
    if(!r.ok)throw new Error('Could not load Discover results.');
    const data=await r.json();
    const metric=document.querySelector('#v7MatchMetric');if(metric)metric.textContent=String(data.total_candidates||0);
    const list=document.querySelector('#v7TabBody .v7CompanyList');
    const items=data.items||[];
    list.innerHTML=items.length?items.map(p=>{
      const m=p.profile_match||{},reasons=(m.matched||[]).join(' · '),source=shortSource(p.universe_source),quality=qualityLabel(p);
      return `<article class="v7CompanyRow v73CompanyRow"><div><div class="v7CompanyName notranslate" translate="no">${esc(p.company)}</div><div class="v7CompanyMeta">${esc([p.company_type,p.country,p.audience].filter(Boolean).join(' · '))}</div><div class="v73SourceRow"><span class="v7Level">${esc(p.data_level||'Indexed')}</span><span class="v73Source">${esc(source)}</span><span class="badge ${qualityClass(p)} v73Quality">${esc(quality)} data · ${Number(p.completeness||0)}%</span></div></div><div><div class="v7CompanyDescription">${esc(p.description||'Basic company identity is indexed. Select it to research products, customers, proof and signals.')}</div></div><div class="v7Match"><b>${Number(m.score||0)}%</b><span>${esc(m.label||'Profile match')}</span><div class="v7MatchReasons">${esc(reasons||'Basic criteria')}</div></div><div class="v7CompanyActions"><button class="secondary small ${p.selected?'v7SelectedButton':''}" onclick="toggleV73Company(${Number(p.id)},${p.selected?'true':'false'})">${p.selected?'Selected ✓':'Select'}</button></div></article>`;
    }).join(''):discoverEmpty('No matches found','Try broader category, region or keyword settings.');
    const pager=document.getElementById('v73Pager');
    const pages=Math.max(1,Number(data.pages||1)),current=Math.max(1,Number(data.page||1));
    if(pager && pages>1)pager.innerHTML=`<div class="v73Pager"><button class="secondary small" ${current<=1?'disabled':''} onclick="goV73DiscoverPage(${current-1})">← Previous</button><span>Page ${current} of ${pages} · ${Number(data.total_candidates||0)} matches</span><button class="secondary small" ${current>=pages?'disabled':''} onclick="goV73DiscoverPage(${current+1})">Next →</button></div>`;
  }catch(e){const list=document.querySelector('#v7TabBody .v7CompanyList');if(list)list.innerHTML=discoverEmpty('Could not load matches',e.message||'Unknown error')}
}
window.goV73DiscoverPage=function(page){renderV73Discover(page,discoverQuery);window.scrollTo({top:0,behavior:'smooth'})};
window.runV7DiscoverSearch=function(){renderV73Discover(1,document.getElementById('v7DiscoverSearch')?.value||'')};
window.toggleV73Company=async function(companyId,isSelected){
  if(!activeWorkspaceId)return;
  const r=await fetch(`/api/workspaces/${activeWorkspaceId}/selected/${companyId}`,{method:isSelected?'DELETE':'POST'});
  if(!r.ok){alert('Could not update selection.');return}
  await window.openV7Workspace(activeWorkspaceId,'discover');
  setTimeout(()=>renderV73Discover(discoverPage,discoverQuery),0);
};

async function refreshWorkspaceCompany(){
  if(!activeWorkspaceId||!activeCompanyId)return;
  try{
    await fetch(`/api/workspaces/${activeWorkspaceId}/companies/${activeCompanyId}/context`,{method:'DELETE'});
    await window.researchCompany(activeCompanyId);
    await fetch(`/api/workspaces/${activeWorkspaceId}/research`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_ids:[activeCompanyId],provider:'gemini'})});
    const started=Date.now();
    while(Date.now()-started<110000){
      await sleep(1200);
      const r=await fetch(`/api/workspaces/${activeWorkspaceId}/research/status`);if(!r.ok)break;const st=await r.json();
      if(st.status!=='running')break;
    }
    activeContext=await fetchContext(activeWorkspaceId,activeCompanyId);applyContext();
  }catch(e){alert('Workspace refresh error: '+(e?.message||'Unknown error'))}
}
window.refreshWorkspaceCompany=refreshWorkspaceCompany;

const oldOpenModal=window.openV7WorkspaceModal;
if(typeof oldOpenModal==='function')window.openV7WorkspaceModal=function(...args){const out=oldOpenModal.apply(this,args);setTimeout(installTaxonomy,0);return out};
installTaxonomy();

const oldOpenReport=window.openV7Report;
if(typeof oldOpenReport==='function')window.openV7Report=async function(companyId){
  activeCompanyId=Number(companyId);activeContext=null;
  const out=await oldOpenReport.apply(this,arguments);
  activeWorkspaceId=window.__v7ReturnWorkspace||activeWorkspaceId;
  if(activeWorkspaceId){activeContext=await fetchContext(activeWorkspaceId,activeCompanyId);applyContext()}
  return out;
};

const oldRender=window.renderReport;
if(typeof oldRender==='function')window.renderReport=function(...args){const out=oldRender.apply(this,args);setTimeout(applyContext,0);return out};

const oldSaveOutreach=window.saveOutreach;
window.saveOutreach=async function(){
  if(!activeContext||!activeWorkspaceId||!activeCompanyId)return oldSaveOutreach?.();
  const opener=document.getElementById('openerEdit'),email=document.getElementById('emailEdit');
  const r=await fetch(`/api/workspaces/${activeWorkspaceId}/companies/${activeCompanyId}/context`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({personalized_opener:opener?.value||'',email_draft:email?.value||''})});
  if(!r.ok){alert('Could not save workspace outreach.');return}
  activeContext=await r.json();applyContext();
};

const oldOpenWorkspace=window.openV7Workspace;
if(typeof oldOpenWorkspace==='function')window.openV7Workspace=async function(id,tab='discover'){
  activeContext=null;activeCompanyId=null;activeWorkspaceId=id;
  const out=await oldOpenWorkspace.apply(this,arguments);
  installTaxonomy();
  if(tab==='discover')setTimeout(()=>renderV73Discover(discoverPage,discoverQuery),0);
  return out;
};
const oldSetTab=window.setV7WorkspaceTab;
if(typeof oldSetTab==='function')window.setV7WorkspaceTab=async function(tab){
  const out=await oldSetTab.apply(this,arguments);
  if(tab==='discover')setTimeout(()=>renderV73Discover(discoverPage,discoverQuery),0);
  return out;
};
})();
