(function(){
'use strict';

let activeWorkspace=null;
let shortlistPoll=null;
let shortlistBusy=false;

function esc75(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function api75(url,options={}){return fetch(url,options).then(async r=>{let data={};try{data=await r.json()}catch(e){}if(!r.ok)throw new Error(data.detail||data.message||`Request failed (${r.status})`);return data})}
function sleep75(ms){return new Promise(r=>setTimeout(r,ms))}

function installStyles(){
  if(document.getElementById('workspace-v75-style'))return;
  const style=document.createElement('style');
  style.id='workspace-v75-style';
  style.textContent=`
    .v75ShortlistTop{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:14px}
    .v75ShortlistTop h2{margin:0 0 4px;font-size:18px}.v75ShortlistTop p{margin:0;color:#667085;font-size:11px;max-width:650px;line-height:1.55}
    .v75Summary{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 16px}.v75Summary span{border:1px solid #e6eaf0;background:#fff;border-radius:999px;padding:6px 9px;font-size:10px;color:#667085}.v75Summary b{color:#101828;margin-right:4px}
    .v75ResearchProgress{border:1px solid #d9e2ff;background:#f8faff;border-radius:14px;padding:13px 14px;margin-bottom:16px}.v75ResearchProgressTop{display:flex;justify-content:space-between;gap:14px}.v75ResearchProgress h3{font-size:12px;margin:0 0 3px}.v75ResearchProgress p{font-size:10px;color:#667085;margin:0}.v75ResearchProgress strong{font-size:12px}.v75Track{height:5px;background:#e7ebf4;border-radius:99px;overflow:hidden;margin-top:10px}.v75Track i{display:block;height:100%;background:#315efb;border-radius:99px;transition:width .25s ease}
    .v75Group{margin-top:18px}.v75GroupHead{display:flex;align-items:center;gap:8px;margin-bottom:8px}.v75GroupHead h3{font-size:12px;margin:0}.v75GroupHead span{font-size:9px;color:#667085;border:1px solid #e6eaf0;border-radius:999px;padding:2px 6px}.v75GroupHead p{font-size:10px;color:#98a2b3;margin:0 0 0 4px}
    .v75Row{display:grid;grid-template-columns:minmax(180px,1.05fr) minmax(260px,1.7fr) 150px 140px;align-items:center;gap:14px;border:1px solid #e7eaf0;background:#fff;border-radius:12px;padding:11px 12px;margin-bottom:7px}.v75Row.current{border-color:#9eb2ff;background:#fbfcff}.v75Name{font-weight:700;font-size:11px;color:#101828}.v75Meta,.v75Desc,.v75Small{font-size:9.5px;color:#667085;line-height:1.45}.v75Desc{font-size:10px}.v75State{display:flex;align-items:center;gap:7px}.v75Dot{width:7px;height:7px;border-radius:50%;background:#98a2b3;flex:0 0 auto}.v75Dot.ready{background:#315efb}.v75Dot.running{background:#7c3aed}.v75Dot.done{background:#12b76a}.v75Dot.issue{background:#f04438}.v75State b{display:block;font-size:10px}.v75Actions{display:flex;justify-content:flex-end;gap:6px;flex-wrap:wrap}.v75Actions button{white-space:nowrap}
    .v75Issues{margin-top:7px;color:#b42318;font-size:9.5px}
    .v75Broader{margin-top:22px;border-top:1px solid #e7eaf0;padding-top:16px}.v75BroaderHead{display:flex;justify-content:space-between;align-items:end;margin-bottom:8px}.v75BroaderHead h3{font-size:12px;margin:0}.v75BroaderHead p{font-size:9.5px;color:#98a2b3;margin:3px 0 0}.v75Broader .v7CompanyRow{opacity:.88}
    .v75UniverseStatus{display:inline-flex!important;align-items:center;gap:5px;margin-left:8px;color:#315efb!important}.v75UniverseStatus.done{color:#027a48!important}.v75UniverseStatus.error{color:#b42318!important}
    @media(max-width:1000px){.v75Row{grid-template-columns:1fr 1.5fr}.v75Actions{justify-content:flex-start}}@media(max-width:700px){.v75Row{grid-template-columns:1fr}.v75ShortlistTop{flex-direction:column}}
  `;
  document.head.appendChild(style);
}

function decorateShell(){
  const tabs=document.querySelector('.v7FlowTabs');
  if(!tabs)return;
  const selected=tabs.querySelector('[data-v7-tab="selected"]');
  const research=tabs.querySelector('[data-v7-tab="research"]');
  let shortlist=tabs.querySelector('[data-v75-tab="shortlist"]');
  if(!shortlist){
    shortlist=document.createElement('button');
    shortlist.dataset.v75Tab='shortlist';
    shortlist.onclick=()=>window.setV7WorkspaceTab('shortlist');
    if(selected)tabs.insertBefore(shortlist,selected);else tabs.appendChild(shortlist);
  }
  const selectedCount=(selected?.querySelector('.v7TabCount')?.textContent||'0').trim();
  shortlist.innerHTML=`Shortlist <span class="v7TabCount">${esc75(selectedCount)}</span>`;
  selected?.remove();research?.remove();
  const metrics=document.querySelectorAll('.v7WorkspaceMetrics .v7Metric');
  if(metrics[1]){const label=metrics[1].querySelector('span'),small=metrics[1].querySelector('small');if(label)label.textContent='Shortlisted';if(small)small.textContent='chosen for evaluation'}
}

function setActiveTab(tab){
  document.querySelectorAll('.v7FlowTabs button').forEach(btn=>{
    const key=btn.dataset.v75Tab||btn.dataset.v7Tab;
    btn.classList.toggle('active',key===tab);
  });
}

function statusInfo(p,batch){
  const decision=String((p.decision||{}).decision||'');
  const current=String(batch?.current||'').trim().toLowerCase();
  const isCurrent=batch?.status==='running'&&String(p.company||'').trim().toLowerCase()===current;
  if(isCurrent)return {label:'Researching',cls:'running',note:'Deep research is running now.'};
  if(decision==='SOURCE NEEDED')return {label:'Source issue',cls:'issue',note:'A stronger public corporate source is required.'};
  if(p.workspace_intelligence&&Object.keys(p.workspace_intelligence).length)return {label:'Completed',cls:'done',note:'Workspace-specific research is ready.'};
  return {label:'Ready',cls:'ready',note:'Selected and ready for deep research.'};
}

function row75(p,batch){
  const s=statusInfo(p,batch),match=p.profile_match||{},source=s.cls==='issue';
  let actions='';
  if(s.cls==='done')actions=`<button class="secondary small" onclick="openV7Report(${Number(p.id)})">Open report</button><button class="secondary small" onclick="removeV75(${Number(p.id)})">Remove</button>`;
  else if(source)actions=`${typeof window.findBetterSource==='function'?`<button class="secondary small" onclick="findBetterSource(${Number(p.id)})">Find source</button>`:''}<button class="secondary small" onclick="removeV75(${Number(p.id)})">Remove</button>`;
  else actions=`<button class="secondary small" onclick="removeV75(${Number(p.id)})">Remove</button>`;
  return `<article class="v75Row ${s.cls==='running'?'current':''}"><div><div class="v75Name notranslate" translate="no">${esc75(p.company)}</div><div class="v75Meta">${esc75([p.company_type,p.country,p.audience].filter(Boolean).join(' · '))}</div></div><div><div class="v75Desc">${esc75(p.description||'Selected for evidence-backed company research.')}</div><div class="v75Small">Profile match ${Number(match.score||0)}%${(match.gaps||[]).length?' · '+esc75(match.gaps[0]):''}</div></div><div class="v75State"><i class="v75Dot ${s.cls}"></i><div><b>${esc75(s.label)}</b><span class="v75Small">${esc75(s.note)}</span></div></div><div class="v75Actions">${actions}</div></article>`;
}

function group75(title,items,batch,help=''){
  if(!items.length)return '';
  return `<section class="v75Group"><div class="v75GroupHead"><h3>${esc75(title)}</h3><span>${items.length}</span>${help?`<p>${esc75(help)}</p>`:''}</div>${items.map(x=>row75(x,batch)).join('')}</section>`;
}

async function renderShortlist(batchOverride=null){
  if(!activeWorkspace)return;
  clearTimeout(shortlistPoll);shortlistPoll=null;
  let detail;
  try{detail=await api75(`/api/workspaces/${activeWorkspace}`)}catch(e){return}
  const body=document.getElementById('v7TabBody');if(!body)return;
  decorateShell();setActiveTab('shortlist');
  const batch=batchOverride||detail.research_batch||{status:'idle',total:0,done:0,failed:0};
  const selected=detail.selected||[],ready=detail.ready||[],issues=detail.source_issues||[],completed=detail.researched||[];
  const running=batch.status==='running',total=Number(batch.total||0),processed=Number(batch.done||0)+Number(batch.failed||0),pct=total?Math.round(processed/total*100):0;
  const progress=running||batch.status==='done'?`<div class="v75ResearchProgress"><div class="v75ResearchProgressTop"><div><h3>${running?'Research in progress':'Last research run finished'}</h3><p>${running?`${esc75(batch.current||'Preparing next company')} · ${batch.done||0} completed · ${batch.failed||0} failed`:`${batch.done||0} completed · ${batch.failed||0} failed`}</p></div><strong>${running?pct+'%':'Done'}</strong></div>${running?`<div class="v75Track"><i style="width:${pct}%"></i></div>`:''}${(batch.errors||[]).length?`<div class="v75Issues">${(batch.errors||[]).slice(-3).map(x=>`${esc75(x.company||'Company')}: ${esc75(x.error||'Research failed')}`).join('<br>')}</div>`:''}</div>`:'';
  body.innerHTML=`<div class="v75ShortlistTop"><div><h2>Shortlist</h2><p>This is the only research queue for this workspace. Add companies in Discover, then research the ready accounts here. Completed accounts stay visible so you always know what happened.</p></div><div>${ready.length&&!running?`<button class="primary" onclick="startV75Research()">Research all ready · ${ready.length}</button>`:''}</div></div><div class="v75Summary"><span><b>${selected.length}</b> shortlisted</span><span><b>${ready.length}</b> ready</span><span><b>${completed.length}</b> completed</span><span><b>${issues.length}</b> source issues</span><button class="secondary small" onclick="setV7WorkspaceTab('discover')">+ Add companies</button></div>${progress}${selected.length?group75('Ready to research',ready,batch,'These accounts will use research credits.')+group75('Completed',completed,batch,'Open a report or remove the account from this workspace.')+group75('Source issues',issues,batch,'Research is blocked until a better company source is found.'): `<div class="v7EmptyInline"><h3>Your shortlist is empty</h3><p>Select promising companies in Discover first.</p><button class="primary" onclick="setV7WorkspaceTab('discover')">Discover companies</button></div>`;
  if(running)shortlistPoll=setTimeout(pollShortlist,1500);
}

async function pollShortlist(){
  if(!activeWorkspace)return;
  try{
    const status=await api75(`/api/workspaces/${activeWorkspace}/research/status`);
    await renderShortlist(status);
    if(status.status!=='running'){
      const oldOpen=window.openV7Workspace;
      // Refresh navigation counts without moving the user away from Shortlist.
      if(typeof oldOpen==='function'){}
    }
  }catch(e){shortlistPoll=setTimeout(pollShortlist,2500)}
}

window.startV75Research=async function(){
  if(shortlistBusy||!activeWorkspace)return;
  shortlistBusy=true;
  try{
    const result=await api75(`/api/workspaces/${activeWorkspace}/research`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    await renderShortlist(result);
  }catch(e){alert('Could not start workspace research: '+e.message)}finally{shortlistBusy=false}
};
// Keep old buttons/links compatible while the product now exposes a single Shortlist step.
window.startV7Research=window.startV75Research;

window.removeV75=async function(companyId){
  if(!activeWorkspace)return;
  try{await api75(`/api/workspaces/${activeWorkspace}/selected/${Number(companyId)}`,{method:'DELETE'});await renderShortlist()}catch(e){alert('Could not remove company: '+e.message)}
};

async function renderBroaderCandidates(){
  if(!activeWorkspace)return;
  const body=document.getElementById('v7TabBody');if(!body||!document.getElementById('v7DiscoverSearch'))return;
  document.querySelector('.v75Broader')?.remove();
  const q=document.getElementById('v7DiscoverSearch')?.value||'';
  try{
    const data=await api75(`/api/workspaces/${activeWorkspace}/discover?limit=40&page=1&q=${encodeURIComponent(q)}`);
    const broader=data.broader_items||[];
    if(!broader.length)return;
    const host=document.getElementById('v73Pager')||body;
    const section=document.createElement('section');section.className='v75Broader';
    section.innerHTML=`<div class="v75BroaderHead"><div><h3>Broader candidates</h3><p>${Number(data.broader_candidates||broader.length)} companies have weaker category evidence. They are shown separately and are not counted as Matches.</p></div></div><div class="v7CompanyList">${broader.map(p=>{const m=p.profile_match||{},reasons=(m.matched||[]).join(' · ');return `<article class="v7CompanyRow"><div><div class="v7CompanyName notranslate" translate="no">${esc75(p.company)}</div><div class="v7CompanyMeta">${esc75([p.company_type,p.country,p.audience].filter(Boolean).join(' · '))}</div><span class="v7Level">${esc75(p.data_level||'Indexed')}</span></div><div><div class="v7CompanyDescription">${esc75(p.description||'Basic public company profile.')}</div></div><div class="v7Match"><b>${Number(m.score||0)}%</b><span>${esc75(m.label||'Possible match')}</span><div class="v7MatchReasons">${esc75(reasons||'Weaker category evidence')}</div></div><div class="v7CompanyActions"><button class="secondary small ${p.selected?'v7SelectedButton':''}" onclick="toggleV73Company(${Number(p.id)},${p.selected?'true':'false'})">${p.selected?'Selected ✓':'Select'}</button></div></article>`}).join('')}</div>`;
    host.insertAdjacentElement('afterend',section);
  }catch(e){}
}

async function decorateUniverseStatus(){
  const bar=document.querySelector('.v73UniverseBar');if(!bar)return;
  bar.querySelector('.v75UniverseStatus')?.remove();
  try{
    const status=await api75('/api/library/expand/status');
    const total=Number(status.company_count||0),target=Number(status.target||10000),state=String(status.status||'idle');
    const el=document.createElement('span');el.className='v75UniverseStatus '+(state==='done'?'done':state==='error'?'error':'');
    el.textContent=state==='running'||state==='starting'?`Indexing ${total.toLocaleString()} / ${target.toLocaleString()}…`:total>=target?`${total.toLocaleString()} indexed`:(state==='error'?`Indexing paused · ${total.toLocaleString()}`:`${total.toLocaleString()} indexed`);
    bar.querySelector('div')?.appendChild(el);
  }catch(e){}
}

const previousOpen=window.openV7Workspace;
if(typeof previousOpen==='function')window.openV7Workspace=async function(id,tab='discover'){
  activeWorkspace=id;
  const mapped=(tab==='selected'||tab==='research')?'shortlist':tab;
  const out=await previousOpen.call(this,id,mapped==='shortlist'?'selected':mapped);
  decorateShell();
  if(mapped==='shortlist')await renderShortlist();
  if(mapped==='discover'){setTimeout(()=>{decorateShell();renderBroaderCandidates();decorateUniverseStatus()},80)}
  return out;
};

const previousSet=window.setV7WorkspaceTab;
if(typeof previousSet==='function')window.setV7WorkspaceTab=async function(tab){
  const mapped=(tab==='selected'||tab==='research')?'shortlist':tab;
  if(mapped==='shortlist'){await renderShortlist();return}
  const out=await previousSet.call(this,mapped);
  decorateShell();setActiveTab(mapped);
  if(mapped==='discover')setTimeout(()=>{renderBroaderCandidates();decorateUniverseStatus()},80);
  return out;
};

// Discover search/page helpers belong to v7.3; decorate their output after they finish.
for(const name of ['runV7DiscoverSearch','goV73DiscoverPage']){
  const fn=window[name];if(typeof fn==='function')window[name]=async function(...args){const out=await fn.apply(this,args);setTimeout(()=>{decorateShell();renderBroaderCandidates();decorateUniverseStatus()},120);return out}
}

installStyles();
setTimeout(()=>{decorateShell();if(document.getElementById('v7DiscoverSearch')){renderBroaderCandidates();decorateUniverseStatus()}},120);
})();
