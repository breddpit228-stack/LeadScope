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

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}

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

async function decorateDiscover(){
  const search=document.querySelector('#v7DiscoverSearch');if(!search)return;
  if(document.querySelector('.v73UniverseBar'))return;
  try{
    const r=await fetch('/api/company-universe/stats');if(!r.ok)return;const s=await r.json();
    const sources=(s.sources||[]).slice(0,3).map(x=>String(x.source||'').replace('Wikidata · European businesses with official websites','Wikidata')).join(' · ');
    search.closest('.v7DiscoverBar')?.insertAdjacentHTML('beforebegin',`<div class="v73UniverseBar"><div><strong>Company Universe</strong><span>${Number(s.total||0).toLocaleString()} indexed · ${Number(s.with_website||0).toLocaleString()} with websites · ${Number(s.with_description||0).toLocaleString()} described</span></div><small>${esc(sources||'Public company sources')}</small></div>`);
  }catch(e){}
}

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
  activeWorkspaceId=window.__v7ReturnWorkspace||null;
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
if(typeof oldOpenWorkspace==='function')window.openV7Workspace=async function(...args){activeContext=null;activeCompanyId=null;const out=await oldOpenWorkspace.apply(this,args);setTimeout(decorateDiscover,0);return out};
const oldSetTab=window.setV7WorkspaceTab;
if(typeof oldSetTab==='function')window.setV7WorkspaceTab=async function(...args){const out=await oldSetTab.apply(this,args);setTimeout(decorateDiscover,0);return out};
})();
