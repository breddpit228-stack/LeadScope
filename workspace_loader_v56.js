(function(){
function installWorkspaceResearchLoader(){
  const overlay=document.querySelector('#progress');if(!overlay)return;
  const card=overlay.querySelector('.progressCard');if(!card)return;
  card.innerHTML=`<div class="wsResearchLoader"><div class="wsResearchHead"><div class="wsResearchIdentity"><div class="wsResearchOrb"></div><div style="min-width:0"><div class="wsResearchBadge">Live research</div><h3 class="wsResearchTitle" id="wsResearchTitle">Researching company</h3><p class="wsResearchSub" id="wsResearchText">Preparing research…</p></div></div><div class="wsResearchPct"><span id="wsResearchPctValue">0</span><span>%</span></div></div><div class="wsResearchProgress"><i id="wsResearchBar"></i></div><div class="wsResearchMeta"><strong id="wsResearchStage">queued</strong><span>Evidence-backed company intelligence</span></div><div class="wsResearchGrid"><section class="wsResearchPanel"><div class="wsResearchPanelLabel">Analysis pipeline</div><div class="wsResearchSteps"><div class="wsResearchStep active" data-ws-stage="queued"><span class="wsResearchStepDot"></span><div><b>Prepare research</b><small>Creating an analysis job</small></div></div><div class="wsResearchStep" data-ws-stage="fetching"><span class="wsResearchStepDot"></span><div><b>Scan public pages</b><small>Opening relevant company pages</small></div></div><div class="wsResearchStep" data-ws-stage="researching"><span class="wsResearchStepDot"></span><div><b>Extract evidence</b><small>Building verified facts and signals</small></div></div><div class="wsResearchStep" data-ws-stage="scoring"><span class="wsResearchStepDot"></span><div><b>Calculate fit</b><small>Matching evidence against your offer</small></div></div><div class="wsResearchStep" data-ws-stage="outreach"><span class="wsResearchStepDot"></span><div><b>Prepare report</b><small>Turning research into actionable intelligence</small></div></div></div></section><aside class="wsResearchPanel"><div class="wsResearchPreviewTop"><b>Company report preview</b><span class="wsPreviewLive"><i></i> building live</span></div><div class="wsPreviewHeader"><div class="wsPreviewHeaderLeft"><div class="wsSkel title"></div><div class="wsSkel line mid"></div></div><div class="wsPreviewScore wsSkel"></div></div><div class="wsPreviewCards"><div class="wsPreviewCard"><div class="wsSkel label"></div><div class="wsSkel line"></div><div class="wsSkel line mid"></div></div><div class="wsPreviewCard"><div class="wsSkel label"></div><div class="wsSkel line"></div><div class="wsSkel line short"></div></div><div class="wsPreviewCard"><div class="wsSkel label"></div><div class="wsSkel line mid"></div><div class="wsSkel line"></div></div><div class="wsPreviewCard"><div class="wsSkel label"></div><div class="wsSkel line"></div><div class="wsSkel line mid"></div></div></div><div class="wsResearchFoot"><i></i><span>Sources stay attached to the final research.</span></div></aside></div></div>`;
}
function workspaceStageKey(stage){stage=String(stage||'').toLowerCase();if(stage.includes('fetch')||stage.includes('crawl')||stage.includes('open'))return'fetching';if(stage.includes('research')||stage.includes('extract')||stage.includes('validat'))return'researching';if(stage.includes('score'))return'scoring';if(stage.includes('outreach')||stage.includes('report')||stage.includes('done')||stage.includes('complete'))return'outreach';return'queued'}
function updateWorkspaceSteps(stage){const order=['queued','fetching','researching','scoring','outreach'],active=workspaceStageKey(stage),activeIndex=order.indexOf(active);document.querySelectorAll('.wsResearchStep').forEach(el=>{const idx=order.indexOf(el.dataset.wsStage);el.classList.toggle('done',idx<activeIndex);el.classList.toggle('active',idx===activeIndex)})}
installWorkspaceResearchLoader();
window.showProgress=function(text,stage,pct){const overlay=document.querySelector('#progress');if(!overlay)return;overlay.classList.add('workspaceSaasProgress');overlay.classList.remove('hidden');document.querySelector('#workspaceView')?.classList.add('workspaceResearching');const company=window.__lsResearchCompany||'Company';const title=document.querySelector('#wsResearchTitle');if(title&&title.textContent!==`Researching ${company}`)title.textContent=`Researching ${company}`;const msg=document.querySelector('#wsResearchText');if(msg&&msg.textContent!==(text||'Researching…'))msg.textContent=text||'Researching…';const st=document.querySelector('#wsResearchStage');if(st&&st.textContent!==(stage||'queued'))st.textContent=stage||'queued';const value=Math.max(0,Math.min(100,Math.round(Number(pct)||0)));const val=document.querySelector('#wsResearchPctValue');if(val&&val.textContent!==String(value))val.textContent=String(value);const bar=document.querySelector('#wsResearchBar');if(bar)bar.style.width=Math.max(3,value)+'%';updateWorkspaceSteps(stage)};
window.hideProgress=function(){const overlay=document.querySelector('#progress');if(overlay){overlay.classList.add('hidden');overlay.classList.remove('workspaceSaasProgress')}document.querySelector('#workspaceView')?.classList.remove('workspaceResearching')};
const baseResearchCompany=window.researchCompany;
if(baseResearchCompany)window.researchCompany=async function(id){
  if(window.__lsResearchActive)return;
  window.__lsResearchActive=true;
  window.__lsResearchCompany='Company';
  showProgress('Starting research…','queued',2);
  document.querySelectorAll('button').forEach(b=>{if(/research/i.test(b.textContent||''))b.disabled=true});
  try{
    try{
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),2500);
      const response=await fetch('/api/companies/'+id,{signal:controller.signal});
      clearTimeout(timer);
      if(response.ok){const c=await response.json();window.__lsResearchCompany=c.company||'Company';showProgress('Preparing research…','queued',3)}
    }catch(e){}
    return await baseResearchCompany(id);
  }catch(err){
    hideProgress();
    console.error('LeadScope research start failed',err);
    alert('Research could not start: '+(err?.message||'Unknown error'));
    return null;
  }finally{
    window.__lsResearchActive=false;
    document.querySelectorAll('button').forEach(b=>{if(/research/i.test(b.textContent||''))b.disabled=false});
  }
};
})();
