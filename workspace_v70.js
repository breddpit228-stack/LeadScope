(function(){
'use strict';

let v7ActiveWorkspace=null;
let v7ActiveTab='discover';
let v7Detail=null;
let v7Workspaces=[];
let v7MatchCount=null;
let v7ResearchPoll=null;
let v7DiscoverTimer=null;
const previousShowWorkspace=window.showWorkspace;

async function v7Api(url,options={}){
  const response=await fetch(url,options);
  let data={};
  try{data=await response.json()}catch(e){}
  if(!response.ok)throw new Error(data.detail||data.message||`Request failed (${response.status})`);
  return data;
}
function v7Escape(v){return typeof esc==='function'?esc(v):String(v??'')}
function v7HideLegacy(){
  ['companiesPage','activityPage','icpPage','overviewPage','opportunitiesPage','discoverPage','todayV2Page','accountsV2Page','opportunitiesV2Page','monitorV2Page','queueV2Page'].forEach(id=>document.getElementById(id)?.classList.add('hidden'));
}
function v7DecisionClass(value){return value==='CONTACT'?'contact':value==='MONITOR'?'monitor':value==='SKIP'?'skip':'review'}
function v7Criteria(w){
  const values=[];
  if(w.industry)values.push(w.industry);
  if(w.region)values.push(w.region);
  if(w.audience&&w.audience!=='Any')values.push(w.audience);
  if(w.company_size)values.push(w.company_size+' employees');
  if(w.keywords)values.push(w.keywords);
  return values;
}
function v7Meta(p){return [p.company_type,p.country,p.audience].filter(Boolean).join(' · ')}
function v7Empty(title,text,button=''){return `<div class="v7EmptyInline"><h3>${v7Escape(title)}</h3><p>${v7Escape(text)}</p>${button}</div>`}
function v7SetBusy(button,busy,label){if(!button)return;button.disabled=busy;if(label)button.textContent=label}

function v7Install(){
  const view=document.querySelector('#workspaceView'),side=view?.querySelector('.side'),main=view?.querySelector('.main');
  if(!view||!side||!main)return;
  view.classList.add('v7Workspace');
  side.innerHTML=`<div class="v7SideBrand"><strong>Workspaces</strong><span>Find → select → research → decide</span></div><button id="v7AllWorkspaces" class="active" onclick="showWorkspace('workspaces')">All workspaces</button><div id="v7WorkspaceNav" class="v7WorkspaceNav"></div><button class="v7SideCreate" onclick="openV7WorkspaceModal()">+ New workspace</button><div class="v7SideFooter">Company Library, ICP settings and export tools now work behind the workflow instead of competing for navigation.</div>`;
  if(!document.querySelector('#v7HubPage')){
    main.insertAdjacentHTML('afterbegin',`<div id="v7HubPage" class="v7Page hidden"></div><div id="v7ProjectPage" class="v7Page hidden"></div>`);
  }
  v7EnsureModal();
}

function v7EnsureModal(){
  if(document.querySelector('#v7WorkspaceModalBg'))return;
  document.body.insertAdjacentHTML('beforeend',`<div id="v7WorkspaceModalBg" class="v7ModalBg hidden" onclick="if(event.target===this)closeV7WorkspaceModal()"><div class="v7Modal"><div class="v7ModalHead"><div><h2 id="v7ModalTitle">Create workspace</h2><p>Describe the companies you want LeadScope to find. Deep research happens only after you select them.</p></div><button class="secondary small" onclick="closeV7WorkspaceModal()">Close</button></div><div class="v7FormGrid"><div class="v7Field full"><label>Workspace name · optional</label><input id="v7WsName" placeholder="Poland Fintech"></div><div class="v7Field"><label>Industry / category</label><input id="v7WsIndustry" placeholder="Fintech, accounting SaaS"></div><div class="v7Field"><label>Country / region</label><input id="v7WsRegion" placeholder="Poland or Europe"></div><div class="v7Field"><label>Business model</label><select id="v7WsAudience"><option>Any</option><option>B2B</option><option>B2C</option><option>Mixed B2B/B2C</option></select></div><div class="v7Field"><label>Company size · optional</label><input id="v7WsSize" placeholder="20–500"></div><div class="v7Field full"><label>Keywords · optional</label><input id="v7WsKeywords" placeholder="payments, payroll, finance automation"></div><div class="v7Field full"><label>What do you sell? · optional</label><textarea id="v7WsOffer" placeholder="AI-powered account research and prioritization for B2B sales teams"></textarea></div></div><div id="v7ModalError" class="v7Error hidden"></div><div class="v7ModalActions"><button id="v7DeleteWorkspace" class="secondary danger hidden" onclick="deleteV7Workspace()">Delete workspace</button><div class="v7ModalActionsRight"><button class="secondary" onclick="closeV7WorkspaceModal()">Cancel</button><button id="v7SaveWorkspace" class="primary" onclick="saveV7Workspace()">Create workspace</button></div></div></div></div>`);
}

window.openV7WorkspaceModal=function(workspaceId=null){
  const modal=document.querySelector('#v7WorkspaceModalBg');
  modal.dataset.workspaceId=workspaceId||'';
  const w=workspaceId?v7Workspaces.find(x=>x.id===workspaceId)||v7Detail?.workspace:null;
  document.querySelector('#v7ModalTitle').textContent=w?'Edit workspace':'Create workspace';
  document.querySelector('#v7WsName').value=w?.name||'';
  document.querySelector('#v7WsIndustry').value=w?.industry||'';
  document.querySelector('#v7WsRegion').value=w?.region||'';
  document.querySelector('#v7WsAudience').value=w?.audience||'Any';
  document.querySelector('#v7WsSize').value=w?.company_size||'';
  document.querySelector('#v7WsKeywords').value=w?.keywords||'';
  document.querySelector('#v7WsOffer').value=w?.offer||'';
  document.querySelector('#v7ModalError').classList.add('hidden');
  document.querySelector('#v7DeleteWorkspace').classList.toggle('hidden',!w);
  document.querySelector('#v7SaveWorkspace').textContent=w?'Save changes':'Create workspace';
  modal.classList.remove('hidden');
}
window.closeV7WorkspaceModal=function(){document.querySelector('#v7WorkspaceModalBg')?.classList.add('hidden')}
window.saveV7Workspace=async function(){
  const bg=document.querySelector('#v7WorkspaceModalBg'),id=bg.dataset.workspaceId||'';
  const payload={name:document.querySelector('#v7WsName').value.trim(),industry:document.querySelector('#v7WsIndustry').value.trim(),region:document.querySelector('#v7WsRegion').value.trim(),audience:document.querySelector('#v7WsAudience').value,company_size:document.querySelector('#v7WsSize').value.trim(),keywords:document.querySelector('#v7WsKeywords').value.trim(),offer:document.querySelector('#v7WsOffer').value.trim()};
  const btn=document.querySelector('#v7SaveWorkspace'),error=document.querySelector('#v7ModalError');
  v7SetBusy(btn,true,id?'Saving…':'Creating…');error.classList.add('hidden');
  try{
    const item=await v7Api(id?`/api/workspaces/${id}`:'/api/workspaces',{method:id?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeV7WorkspaceModal();await v7LoadWorkspaceNav();await openV7Workspace(item.id,'discover');
  }catch(e){error.textContent=e.message;error.classList.remove('hidden')}finally{v7SetBusy(btn,false,id?'Save changes':'Create workspace')}
}
window.deleteV7Workspace=async function(){
  const id=document.querySelector('#v7WorkspaceModalBg')?.dataset.workspaceId;if(!id)return;
  if(!confirm('Delete this workspace? Company research stays in LeadScope; only this project and its selection are removed.'))return;
  await v7Api(`/api/workspaces/${id}`,{method:'DELETE'});closeV7WorkspaceModal();v7ActiveWorkspace=null;v7Detail=null;await v7LoadWorkspaceNav();await v7ShowHub();
}

async function v7LoadWorkspaceNav(){
  const data=await v7Api('/api/workspaces');v7Workspaces=data.items||[];
  const nav=document.querySelector('#v7WorkspaceNav');
  nav.innerHTML=v7Workspaces.map(w=>`<button class="${v7ActiveWorkspace===w.id?'active':''}" onclick="openV7Workspace('${w.id}','discover')"><span>${v7Escape(w.name)}</span><small class="v7NavCount">${(w.counts||{}).selected||0}</small></button>`).join('');
}
async function v7ShowHub(){
  clearTimeout(v7ResearchPoll);v7ResearchPoll=null;v7ActiveWorkspace=null;v7Detail=null;v7MatchCount=null;
  document.querySelector('#homeView')?.classList.add('hidden');document.querySelector('#workspaceView')?.classList.remove('hidden');v7HideLegacy();
  document.querySelector('#reportPage')?.classList.add('hidden');document.querySelector('#v7ProjectPage')?.classList.add('hidden');document.querySelector('#v7HubPage')?.classList.remove('hidden');
  document.querySelector('#v7AllWorkspaces')?.classList.add('active');
  await v7LoadWorkspaceNav();
  const root=document.querySelector('#v7HubPage');
  root.innerHTML=`<div class="v7HeroHead"><div><h1>Your workspaces</h1><p>Each workspace is one prospecting task. Define a market, select the companies that matter, then research only those accounts.</p></div><button class="primary" onclick="openV7WorkspaceModal()">+ Create workspace</button></div>`+(v7Workspaces.length?`<div class="v7WorkspaceGrid">${v7Workspaces.map(w=>{let c=w.counts||{};let criteria=v7Criteria(w).slice(0,3).join(' · ')||'Targeting not configured';return `<article class="v7WorkspaceCard" onclick="openV7Workspace('${w.id}','discover')"><div class="v7WorkspaceCardTop"><div><h3>${v7Escape(w.name)}</h3><p>${v7Escape(criteria)}</p></div><span class="v7CardArrow">→</span></div><div class="v7WorkspaceCardStats"><div class="v7MiniStat"><b>${c.selected||0}</b><span>Selected</span></div><div class="v7MiniStat"><b>${c.researched||0}</b><span>Researched</span></div><div class="v7MiniStat"><b>${c.recommended||0}</b><span>Recommended</span></div></div></article>`}).join('')}</div>`:`<div class="v7EmptyHero"><div class="v7EmptyIcon"></div><h2>Find companies worth researching</h2><p>Create a workspace around a market such as “Poland Fintech” or “European B2B SaaS”. LeadScope will suggest matching companies before you spend research requests.</p><button class="primary" onclick="openV7WorkspaceModal()">Create your first workspace</button></div>`);
}

async function v7FetchDetail(){if(!v7ActiveWorkspace)return null;v7Detail=await v7Api(`/api/workspaces/${v7ActiveWorkspace}`);return v7Detail}
function v7RenderWorkspaceShell(){
  const root=document.querySelector('#v7ProjectPage'),w=v7Detail.workspace,c=v7Detail.counts||{};
  const criteria=v7Criteria(w);
  root.innerHTML=`<button class="v7Back" onclick="showWorkspace('workspaces')">← All workspaces</button><div class="v7WorkspaceTitleRow"><div><h1>${v7Escape(w.name)}</h1><div class="v7WorkspaceSubtitle">Select the companies you care about, then let LeadScope research only those accounts.</div><div class="v7Criteria">${criteria.map(x=>`<span class="v7Criterion">${v7Escape(x)}</span>`).join('')}${w.offer?'<span class="v7Criterion">Offer defined</span>':''}</div></div><button class="secondary" onclick="openV7WorkspaceModal('${w.id}')">Edit targeting</button></div><div class="v7WorkspaceMetrics"><div class="v7Metric"><span>Matches</span><b id="v7MatchMetric">${v7MatchCount==null?'—':v7MatchCount}</b><small>basic profile candidates</small></div><div class="v7Metric"><span>Selected</span><b>${c.selected||0}</b><small>chosen by you</small></div><div class="v7Metric"><span>Researched</span><b>${c.researched||0}</b><small>deep research complete</small></div><div class="v7Metric"><span>Recommended</span><b>${c.recommended||0}</b><small>fit + timing justify action</small></div></div><div class="v7FlowTabs"><button data-v7-tab="discover" onclick="setV7WorkspaceTab('discover')">Discover</button><button data-v7-tab="selected" onclick="setV7WorkspaceTab('selected')">Selected <span class="v7TabCount">${c.selected||0}</span></button><button data-v7-tab="research" onclick="setV7WorkspaceTab('research')">Research <span class="v7TabCount">${c.waiting||0}</span></button><button data-v7-tab="results" onclick="setV7WorkspaceTab('results')">Results <span class="v7TabCount">${c.researched||0}</span></button></div><div id="v7TabBody"></div>`;
  document.querySelectorAll('[data-v7-tab]').forEach(b=>b.classList.toggle('active',b.dataset.v7Tab===v7ActiveTab));
}
window.openV7Workspace=async function(id,tab='discover'){
  v7ActiveWorkspace=id;v7ActiveTab=tab;v7MatchCount=null;
  document.querySelector('#homeView')?.classList.add('hidden');document.querySelector('#workspaceView')?.classList.remove('hidden');v7HideLegacy();document.querySelector('#reportPage')?.classList.add('hidden');document.querySelector('#v7HubPage')?.classList.add('hidden');document.querySelector('#v7ProjectPage')?.classList.remove('hidden');document.querySelector('#v7AllWorkspaces')?.classList.remove('active');
  await v7FetchDetail();await v7LoadWorkspaceNav();v7RenderWorkspaceShell();await v7RenderTab();window.scrollTo({top:0,behavior:'smooth'});
}
window.setV7WorkspaceTab=async function(tab){v7ActiveTab=tab;document.querySelectorAll('[data-v7-tab]').forEach(b=>b.classList.toggle('active',b.dataset.v7Tab===tab));await v7RenderTab()}
async function v7RenderTab(){
  if(!v7ActiveWorkspace)return;
  if(v7ActiveTab==='discover')return v7RenderDiscover();
  await v7FetchDetail();v7RenderWorkspaceShell();document.querySelectorAll('[data-v7-tab]').forEach(b=>b.classList.toggle('active',b.dataset.v7Tab===v7ActiveTab));
  if(v7ActiveTab==='selected')return v7RenderSelected();
  if(v7ActiveTab==='research')return v7RenderResearch();
  if(v7ActiveTab==='results')return v7RenderResults();
}

async function v7RenderDiscover(q=''){
  const body=document.querySelector('#v7TabBody');if(!body)return;
  body.innerHTML=`<div class="v7DiscoverBar"><input id="v7DiscoverSearch" placeholder="Search within this market…" value="${v7Escape(q)}"><button class="secondary" onclick="runV7DiscoverSearch()">Search</button></div><div class="v7Hint">Profile match uses the workspace criteria and basic company data. It is not the deep research Fit score.</div><div class="v7CompanyList"><div class="v7EmptyInline">Finding matching companies…</div></div>`;
  const input=document.querySelector('#v7DiscoverSearch');input?.addEventListener('input',()=>{clearTimeout(v7DiscoverTimer);v7DiscoverTimer=setTimeout(()=>v7RenderDiscover(input.value.trim()),450)});
  try{
    const data=await v7Api(`/api/workspaces/${v7ActiveWorkspace}/discover?limit=120&q=${encodeURIComponent(q)}`);v7MatchCount=data.total_candidates||0;const metric=document.querySelector('#v7MatchMetric');if(metric)metric.textContent=String(v7MatchCount);
    const list=document.querySelector('#v7TabBody .v7CompanyList');
    const items=data.items||[];
    list.innerHTML=items.length?items.map(p=>{let m=p.profile_match||{},reasons=(m.matched||[]).join(' · ');return `<article class="v7CompanyRow"><div><div class="v7CompanyName notranslate" translate="no">${v7Escape(p.company)}</div><div class="v7CompanyMeta">${v7Escape(v7Meta(p))}</div><span class="v7Level">${v7Escape(p.data_level)}</span></div><div><div class="v7CompanyDescription">${v7Escape(p.description||'Basic company identity is indexed. Select it to research products, customers, proof and signals.')}</div></div><div class="v7Match"><b>${m.score||0}%</b><span>${v7Escape(m.label||'Profile match')}</span><div class="v7MatchReasons">${v7Escape(reasons||'Basic criteria')}</div></div><div class="v7CompanyActions"><button class="secondary small ${p.selected?'v7SelectedButton':''}" onclick="toggleV7Company(${p.id},${p.selected?'true':'false'})">${p.selected?'Selected ✓':'Select'}</button></div></article>`}).join(''):v7Empty('No matches found','Try broader industry, region or keyword settings.','<button class="secondary" onclick="openV7WorkspaceModal(\''+v7ActiveWorkspace+'\')">Edit targeting</button>');
  }catch(e){document.querySelector('#v7TabBody .v7CompanyList').innerHTML=v7Empty('Could not load matches',e.message)}
}
window.runV7DiscoverSearch=function(){v7RenderDiscover(document.querySelector('#v7DiscoverSearch')?.value.trim()||'')}
window.toggleV7Company=async function(companyId,isSelected){
  await v7Api(`/api/workspaces/${v7ActiveWorkspace}/selected/${companyId}`,{method:isSelected?'DELETE':'POST'});await v7FetchDetail();await v7LoadWorkspaceNav();if(v7ActiveTab==='discover')await v7RenderDiscover(document.querySelector('#v7DiscoverSearch')?.value.trim()||'');else await v7RenderTab();
}

function v7SelectedRow(p,researchView=false){
  const source=(p.decision||{}).decision==='SOURCE NEEDED';const status=p.data_level==='Researched'?'Completed':source?'Source needed':'Waiting';
  return `<article class="v7CompanyRow"><div><div class="v7CompanyName notranslate" translate="no">${v7Escape(p.company)}</div><div class="v7CompanyMeta">${v7Escape(v7Meta(p))}</div></div><div><div class="v7CompanyDescription">${v7Escape(p.description||'Selected for deeper research.')}</div>${source?'<div class="v7MatchReasons">This domain is not a reliable source for evidence-backed scoring.</div>':''}</div><div class="v7ResearchStatus"><i class="v7StatusDot ${p.data_level==='Researched'?'done':source?'issue':''}"></i><div><b>${status}</b><div class="v7CompanyMeta">${p.completeness||0}% data complete</div></div></div><div class="v7CompanyActions">${researchView&&source&&typeof window.findBetterSource==='function'?`<button class="secondary small" onclick="findBetterSource(${p.id})">Find source</button>`:p.data_level==='Researched'?`<button class="secondary small" onclick="openV7Report(${p.id})">Open report</button>`:`<button class="secondary small" onclick="toggleV7Company(${p.id},true)">Remove</button>`}</div></article>`;
}
function v7RenderSelected(){
  const body=document.querySelector('#v7TabBody'),items=v7Detail.selected||[],waiting=v7Detail.waiting||[];
  body.innerHTML=`<div class="v7SectionHead"><div><h2>Selected companies</h2><p>Your shortlist. Deep research is only spent on companies you choose.</p></div>${waiting.length?`<button class="primary" onclick="startV7Research()">Research waiting ${waiting.length}</button>`:''}</div>`+(items.length?`<div class="v7SelectionBar"><div><strong>${items.length} selected</strong><span>${(v7Detail.counts||{}).researched||0} already researched</span></div><button class="secondary small" onclick="setV7WorkspaceTab('discover')">+ Add more</button></div><div class="v7CompanyList">${items.map(x=>v7SelectedRow(x,false)).join('')}</div>`:v7Empty('Nothing selected yet','Choose promising companies from Discover before starting research.','<button class="primary" onclick="setV7WorkspaceTab(\'discover\')">Discover companies</button>'));
}

window.startV7Research=async function(){
  const result=await v7Api(`/api/workspaces/${v7ActiveWorkspace}/research`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});v7ActiveTab='research';await v7FetchDetail();v7RenderWorkspaceShell();v7RenderResearch(result);if(result.status==='running')v7PollResearch();
}
async function v7PollResearch(){
  clearTimeout(v7ResearchPoll);if(!v7ActiveWorkspace)return;
  try{const status=await v7Api(`/api/workspaces/${v7ActiveWorkspace}/research/status`);if(v7ActiveTab==='research')v7RenderResearch(status);if(status.status==='running')v7ResearchPoll=setTimeout(v7PollResearch,1600);else{await v7FetchDetail();if(v7ActiveTab==='research'){v7RenderWorkspaceShell();v7RenderResearch(status)}await v7LoadWorkspaceNav()}}catch(e){v7ResearchPoll=setTimeout(v7PollResearch,2500)}
}
function v7RenderResearch(statusOverride=null){
  const body=document.querySelector('#v7TabBody'),items=v7Detail.selected||[],batch=statusOverride||v7Detail.research_batch||{status:'idle',total:0,done:0,failed:0};
  const total=Number(batch.total||0),done=Number(batch.done||0)+Number(batch.failed||0),pct=total?Math.round(done/total*100):0,running=batch.status==='running';
  body.innerHTML=`<div class="v7SectionHead"><div><h2>Research</h2><p>Research runs as a workspace queue, so the interface stays usable while accounts are processed.</p></div>${!running&&(v7Detail.waiting||[]).some(x=>(x.decision||{}).decision!=='SOURCE NEEDED')?'<button class="primary" onclick="startV7Research()">Start research</button>':''}</div><div class="v7ResearchBanner"><div class="v7ResearchBannerTop"><div><h3>${running?'Research running':batch.status==='done'?'Research queue finished':'Research queue'}</h3><p>${running?`${v7Escape(batch.current||'Preparing next company')} · ${batch.done||0} complete · ${batch.failed||0} failed`:batch.status==='done'?`${batch.done||0} completed · ${batch.failed||0} failed`:'Start research when your shortlist is ready.'}</p></div><strong>${running?pct+'%':''}</strong></div>${running?`<div class="v7BatchTrack"><i style="width:${pct}%"></i></div>`:''}${(batch.errors||[]).length?`<div class="v7BatchErrors">${(batch.errors||[]).slice(-3).map(x=>`${v7Escape(x.company)}: ${v7Escape(x.error)}`).join('<br>')}</div>`:''}</div>`+(items.length?`<div class="v7CompanyList">${items.map(x=>v7SelectedRow(x,true)).join('')}</div>`:v7Empty('No companies selected','Go to Discover and build a shortlist first.'));
  if(running&&!v7ResearchPoll)v7PollResearch();
}

function v7ResultRow(p){let d=p.decision||{},m=p.profile_match||{};return `<article class="v7ResultRow"><div><div class="v7CompanyName notranslate" translate="no">${v7Escape(p.company)}</div><div class="v7CompanyMeta">${v7Escape(v7Meta(p))}</div><span class="v7Decision ${v7DecisionClass(d.decision)}">${v7Escape(d.decision||'REVIEW')}</span></div><div class="v7ResultMetric"><span>Fit</span><b>${d.fit==null?'—':d.fit}</b></div><div class="v7ResultMetric"><span>Timing</span><b>${d.timing==null?'—':d.timing}</b></div><div class="v7ResultMetric"><span>Confidence</span><b>${d.confidence==null?'—':d.confidence}</b></div><div class="v7ResultMetric"><span>Priority</span><b>${d.priority==null?'—':d.priority}</b></div><div class="v7Why">${v7Escape(d.reason||m.label||'Review current evidence.')}</div><button class="secondary small" onclick="openV7Report(${p.id})">Open</button></article>`}
function v7ResultGroup(title,items){return `<section class="v7ResultGroup"><div class="v7ResultGroupHead"><h2>${v7Escape(title)}</h2><span>${items.length}</span></div>${items.length?items.map(v7ResultRow).join(''):v7Empty('No '+title.toLowerCase()+' accounts','This group will populate as selected companies finish research.')}</section>`}
function v7RenderResults(){
  const body=document.querySelector('#v7TabBody'),c=v7Detail.counts||{};
  body.innerHTML=`<div class="v7SectionHead"><div><h2>Research results</h2><p>Fit is specific to this workspace. Timing and confidence come from the evidence-backed research.</p></div>${c.waiting?`<button class="secondary" onclick="setV7WorkspaceTab('research')">${c.waiting} still waiting</button>`:''}</div>`+(c.researched?v7ResultGroup('Recommended',v7Detail.recommended||[])+v7ResultGroup('Monitor',v7Detail.monitor||[])+v7ResultGroup('Review',v7Detail.review||[])+v7ResultGroup('Skip',v7Detail.skip||[]):v7Empty('No research results yet','Research your selected companies to turn profile matches into actionable decisions.','<button class="primary" onclick="setV7WorkspaceTab(\'research\')">Go to research</button>'));
}

window.openV7Report=async function(companyId){
  window.__v7ReturnWorkspace=v7ActiveWorkspace;window.__v7ReturnTab='results';
  document.querySelector('#v7HubPage')?.classList.add('hidden');document.querySelector('#v7ProjectPage')?.classList.add('hidden');
  await window.openCompany(companyId);
  setTimeout(()=>{const back=document.querySelector('#reportPage .reportBack');if(back){back.textContent='← Back to results';back.onclick=()=>openV7Workspace(window.__v7ReturnWorkspace,'results')}},0);
}

window.showWorkspace=function(view='workspaces'){
  if(view==='report'){
    document.querySelector('#v7HubPage')?.classList.add('hidden');document.querySelector('#v7ProjectPage')?.classList.add('hidden');return previousShowWorkspace('report');
  }
  if(view==='workspaces'||['companies','overview','today','accounts','opportunities','opportunitiesV2','monitorV2','queueV2','discover','activity','icp'].includes(view))return v7ShowHub();
  return v7ShowHub();
}

v7Install();
setTimeout(()=>{const workspace=document.querySelector('#workspaceView');if(workspace&&!workspace.classList.contains('hidden'))v7ShowHub();else v7LoadWorkspaceNav().catch(()=>{})},0);
})();
