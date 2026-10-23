(function(){
let changeIntel=null;
function freshClass(label){label=String(label||'unknown').toLowerCase();return label==='fresh'?'':label==='recent'?'recent':label==='aging'?'aging':label==='historical'?'historical':'unknown'}
function changeDate(v){if(!v)return'Date unknown';try{return new Date(v).toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'})}catch{return String(v)}}
function renderChangeExtension(){
 if(!changeIntel)return;
 let overview=document.querySelector('.reportTabs [data-report-tab="overview"]')?.classList.contains('active');if(!overview)return;
 let content=document.querySelector('#reportContent');if(!content)return;
 content.querySelectorAll('.changeExtension').forEach(x=>x.remove());
 let changes=changeIntel.changes||[],fresh=changeIntel.evidence_freshness||{},committee=changeIntel.buying_committee||[],angles=changeIntel.outreach_angles||[];
 let blocks='';
 blocks+=`<div class="changePanel changeExtension"><div class="changePanelTop"><div><h3>Evidence freshness</h3><p>How recent the observable account evidence is.</p></div><span class="freshnessBadge ${freshClass(fresh.label)}">${esc(fresh.label||'Unknown')}</span></div><div class="freshnessStrip"><span>${fresh.age_days==null?'No reliable evidence date':esc(fresh.age_days)+' days since freshest dated evidence'}</span><span>·</span><span>${fresh.fresh_count||0} fresh</span><span>·</span><span>${fresh.recent_count||0} recent</span>${fresh.historical_count?`<span>·</span><span>${fresh.historical_count} historical</span>`:''}</div></div>`;
 if(changes.length){blocks+=`<div class="changePanel changeExtension"><div class="changePanelTop"><div><h3>What changed since last research</h3><p>Only differences detected between saved research snapshots.</p></div><span class="changeCount">${changes.length}</span></div><div class="changeList">${changes.slice(0,8).map(x=>`<div class="changeItem"><label>${esc(x.label||'Change')}</label><div><strong>${esc(x.title||'')}</strong><time>${esc(changeDate(x.date))}</time></div></div>`).join('')}</div></div>`}
 if(committee.length){blocks+=`<div class="changePanel changeExtension"><div class="changePanelTop"><div><h3>Buying committee</h3><p>Publicly supported roles that may matter for this opportunity — not verified individual contacts.</p></div></div><div class="committeeGrid">${committee.map(x=>`<div class="committeeItem"><strong>${esc(x.role)}</strong><p>${esc(x.why)}</p></div>`).join('')}</div></div>`}
 if(angles.length){blocks+=`<div class="changePanel changeExtension"><div class="changePanelTop"><div><h3>Outreach angles</h3><p>Ranked approaches. The first is the strongest currently supported angle.</p></div></div><div class="angleGrid">${angles.map(x=>`<div class="angleItem ${x.recommended?'recommended':''}"><strong>${x.recommended?'Best · ':''}${esc(x.title)}</strong><p>${esc(x.rationale||'')}</p><div class="angleStrength">Support ${esc(x.strength||0)}/100</div></div>`).join('')}</div></div>`}
 let anchor=content.querySelector('.decisionHero');if(anchor)anchor.insertAdjacentHTML('afterend',blocks);else content.insertAdjacentHTML('afterbegin',blocks);
}
const previousOpen=window.openCompany;window.openCompany=async function(id){let intel=fetch('/api/companies/'+id+'/intelligence').then(r=>r.json()).catch(()=>null);let out=await previousOpen(id);changeIntel=await intel;renderChangeExtension();return out}
const previousRender=window.renderReport;if(previousRender)window.renderReport=function(){let out=previousRender();setTimeout(renderChangeExtension,0);return out}
let todayChangeRequest=null;
function addTodayChanges(){
 let stats=document.querySelector('#todayV2Stats');
 if(!stats||stats.querySelector('[data-change-stat]')||todayChangeRequest)return;
 todayChangeRequest=fetch('/api/workspace-v2').then(r=>r.json()).then(w=>{
   let count=(w.counts||{}).changes||0;
   let current=document.querySelector('#todayV2Stats');
   if(count&&current&&!current.querySelector('[data-change-stat]'))current.insertAdjacentHTML('beforeend',`<div class="workspaceV2Stat" data-change-stat onclick="showWorkspace('accounts')"><span>New changes</span><b>${count}</b><p>Detected since previous research</p></div>`);
 }).catch(()=>{}).finally(()=>{todayChangeRequest=null});
}
function scheduleTodayChanges(){[150,700,1600].forEach(ms=>setTimeout(addTodayChanges,ms))}
const previousShow=window.showWorkspace;
if(previousShow)window.showWorkspace=function(view){let out=previousShow(view);let normalized=view==='overview'?'today':view;if(normalized==='today')scheduleTodayChanges();return out}
setTimeout(scheduleTodayChanges,300);
})();
