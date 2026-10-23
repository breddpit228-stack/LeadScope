(function(){
function isLimited(c){let s=String(c?.quality_status||'').toLowerCase();return s.includes('limited public access')||s.includes('insufficient evidence')}
function reason(c){return c?.quality_reason||c?.fit_summary||'This source did not expose enough reliable public company information for evidence-backed scoring.'}
function notice(c){return `<div class="sourceQualityNotice"><div class="sourceQualityIcon">i</div><div><strong>Fit score unavailable</strong><p>${esc(reason(c))}</p><span>Try an official corporate, newsroom, investor-relations, or company-information source.</span></div></div>`}
function applyHome(c){if(!isLimited(c))return;let root=document.querySelector('#homeResult');if(!root)return;let score=root.querySelector('.score strong'),denom=root.querySelector('.score span');if(score)score.textContent='N/A';if(denom)denom.textContent='';let fit=root.querySelector('.fitBox p');if(fit)fit.textContent=reason(c);let card=root.querySelector('.resultCard');if(card&&!card.querySelector('.sourceQualityNotice')){let top=card.querySelector('.resultTop');if(top)top.insertAdjacentHTML('afterend',notice(c))}}
const oldHome=window.renderHomeResult;if(oldHome)window.renderHomeResult=function(c){oldHome(c);applyHome(c)};

function applyReport(c){if(!isLimited(c))return;let metrics=document.querySelector('#reportMetrics');if(metrics){let first=metrics.querySelector('.reportMetric');if(first){let b=first.querySelector('b'),span=first.querySelector('span');if(b)b.textContent='N/A';if(span)span.textContent='';let p=first.querySelector('p');if(p)p.textContent=reason(c)}}let content=document.querySelector('#reportContent');if(content&&!content.querySelector('.sourceQualityNotice'))content.insertAdjacentHTML('afterbegin',notice(c));}
const oldShell=window.renderReportShell;if(oldShell)window.renderReportShell=function(){oldShell();applyReport(window.currentCompany)};
const oldReport=window.renderReport;if(oldReport)window.renderReport=function(){oldReport();applyReport(window.currentCompany)};

function patchTable(){document.querySelectorAll('#companyRows tr').forEach(tr=>{let text=tr.textContent.toLowerCase();if(!text.includes('limited public access')&&!text.includes('insufficient evidence'))return;let cells=tr.querySelectorAll('td');if(cells.length>=4)cells[3].innerHTML='<strong class="tableFit naFit">N/A</strong>'})}
const oldLoad=window.loadCompanies;if(oldLoad)window.loadCompanies=async function(){let v=await oldLoad();patchTable();return v};

const obs=new MutationObserver(()=>{if(window.currentCompany&&isLimited(window.currentCompany))applyReport(window.currentCompany);patchTable()});
obs.observe(document.body,{subtree:true,childList:true});
})();
