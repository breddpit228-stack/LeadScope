(function(){
'use strict';

const INDUSTRIES=[
  ['Fintech','Financial technology, payments, banking, accounting'],
  ['Accounting SaaS','Bookkeeping, invoicing, payroll and finance software'],
  ['Payments','Payment infrastructure, PSPs and merchant tools'],
  ['Banking software','Digital banking and financial infrastructure'],
  ['B2B SaaS','Software products sold to business teams'],
  ['AI / data software','AI platforms, analytics and data products'],
  ['Cybersecurity','Security software, identity and fraud prevention'],
  ['MarTech','Marketing, advertising and growth software'],
  ['SalesTech','Sales, prospecting and revenue software'],
  ['HR Tech','HR, payroll, recruiting and people software'],
  ['E-commerce','Online commerce and retail technology'],
  ['Marketplace','Two-sided platforms and marketplaces'],
  ['Logistics tech','Supply chain, delivery and logistics software'],
  ['Climate tech','Energy, climate and sustainability technology'],
  ['Healthtech','Healthcare, medical and life-science technology'],
  ['Professional services','Consulting, agencies and advisory businesses']
];

const REGIONS=[
  ['Europe','Companies across European countries'],
  ['Poland','Poland'],['Germany','Germany'],['United Kingdom','United Kingdom'],['France','France'],
  ['Netherlands','Netherlands'],['Sweden','Sweden'],['Denmark','Denmark'],['Norway','Norway'],
  ['Finland','Finland'],['Spain','Spain'],['Italy','Italy'],['Czechia','Czechia'],['Austria','Austria'],
  ['Switzerland','Switzerland'],['Belgium','Belgium'],['Ireland','Ireland'],['Estonia','Estonia'],
  ['Lithuania','Lithuania'],['Latvia','Latvia'],['Portugal','Portugal'],['Romania','Romania'],['Ukraine','Ukraine']
];

const SIZES=[
  ['1–10','Micro / very early stage'],['11–50','Small company'],['51–200','SMB / scale-up'],
  ['201–500','Mid-market'],['501–1000','Upper mid-market'],['1001–5000','Large company'],['5000+','Enterprise']
];

const KEYWORDS={
  fintech:['payments','payroll','accounting automation','invoicing','spend management','banking','fraud prevention','lending','finance automation'],
  accounting:['bookkeeping','invoicing','payroll','expense management','tax','finance automation','SMB accounting'],
  payments:['merchant payments','payment infrastructure','fraud prevention','checkout','acquiring','payment orchestration'],
  'b2b saas':['CRM','RevOps','sales automation','workflow automation','customer success','lead generation','data enrichment'],
  ai:['AI agents','LLM','machine learning','analytics','automation','data platform','decision intelligence'],
  cybersecurity:['identity','fraud prevention','risk','compliance','cloud security','threat detection'],
  martech:['marketing automation','campaigns','attribution','advertising','CRM','lead generation','content'],
  salestech:['prospecting','sales automation','CRM','RevOps','lead generation','data enrichment','account intelligence'],
  hr:['recruiting','payroll','workforce management','HRIS','employee engagement','talent'],
  ecommerce:['commerce platform','checkout','retail','payments','fulfillment','customer experience'],
  logistics:['supply chain','delivery','fleet','warehouse','route optimization','freight'],
  climate:['energy','carbon','sustainability','renewables','climate intelligence','ESG'],
  health:['healthcare','clinical','medical','biotech','patient data','life sciences']
};

const GENERIC_KEYWORDS=['automation','workflow','analytics','data platform','growth','sales','operations','enterprise','SMB','API'];
const OFFERS=[
  ['AI-powered account research and prioritization for B2B sales teams','Research / sales intelligence'],
  ['Marketing automation and lead-generation services for B2B companies','Marketing automation'],
  ['CRM and RevOps workflow automation for growing sales teams','RevOps automation'],
  ['Data enrichment and prospecting workflow automation','Prospecting infrastructure'],
  ['Custom software and workflow automation for business teams','Software / automation']
];

let active=null;
let highlighted=-1;

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function normalize(v){return String(v||'').trim().toLowerCase()}
function currentToken(value){const parts=String(value||'').split(',');return normalize(parts[parts.length-1])}
function fieldWrap(input){return input?.closest('.v7Field')||null}
function ensureBox(input){
  const wrap=fieldWrap(input);if(!wrap)return null;
  let box=wrap.querySelector('.v7SuggestBox');
  if(!box){box=document.createElement('div');box.className='v7SuggestBox hidden';wrap.appendChild(box)}
  return box;
}
function closeAll(){document.querySelectorAll('.v7SuggestBox').forEach(x=>x.classList.add('hidden'));active=null;highlighted=-1}
function keywordOptions(){
  const industry=normalize(document.querySelector('#v7WsIndustry')?.value);
  let values=[];
  Object.entries(KEYWORDS).forEach(([key,list])=>{if(industry.includes(key)||key.includes(industry))values.push(...list)});
  if(!values.length)values=GENERIC_KEYWORDS;
  return [...new Set(values)].map(v=>[v,'Suggested for '+(industry||'this workspace')]);
}
function nameOptions(){
  const industry=(document.querySelector('#v7WsIndustry')?.value||'').trim();
  const region=(document.querySelector('#v7WsRegion')?.value||'').trim();
  const audience=(document.querySelector('#v7WsAudience')?.value||'').trim();
  const out=[];
  if(region&&industry)out.push([`${region} ${industry}`, 'Clear market-based workspace name']);
  if(industry)out.push([`${industry} prospects`, 'Simple prospecting workspace']);
  if(region&&industry)out.push([`${region} ${industry} prospects`, 'Region + category']);
  if(audience&&audience!=='Any'&&industry)out.push([`${audience} ${industry}`, 'Business model + category']);
  return out.length?out:[['European B2B prospects','Example workspace name'],['Poland Fintech','Example workspace name']];
}
function optionsFor(id){
  if(id==='v7WsIndustry')return INDUSTRIES;
  if(id==='v7WsRegion')return REGIONS;
  if(id==='v7WsSize')return SIZES;
  if(id==='v7WsKeywords')return keywordOptions();
  if(id==='v7WsOffer')return OFFERS;
  if(id==='v7WsName')return nameOptions();
  return [];
}
function filterOptions(input){
  const all=optionsFor(input.id);
  const query=input.id==='v7WsKeywords'?currentToken(input.value):normalize(input.value);
  if(!query)return all.slice(0,8);
  return all.filter(([value,desc])=>normalize(value).includes(query)||normalize(desc).includes(query)).slice(0,8);
}
function render(input){
  const box=ensureBox(input);if(!box)return;
  const opts=filterOptions(input);highlighted=-1;
  if(!opts.length){box.classList.add('hidden');return}
  const contextual=input.id==='v7WsKeywords'?'<div class="v7SuggestCaption">Suggested keywords — click to add</div>':'';
  box.innerHTML=contextual+opts.map(([value,desc],i)=>`<button type="button" class="v7SuggestItem" data-index="${i}" data-value="${esc(value)}"><span>${esc(value)}</span><small>${esc(desc||'')}</small></button>`).join('');
  box.classList.remove('hidden');active={input,box,opts};
  box.querySelectorAll('.v7SuggestItem').forEach(btn=>btn.addEventListener('mousedown',e=>{e.preventDefault();choose(input,btn.dataset.value)}));
}
function choose(input,value){
  if(input.id==='v7WsKeywords'){
    const parts=input.value.split(',').map(x=>x.trim()).filter(Boolean);
    const token=currentToken(input.value);
    if(token&&parts.length)parts.pop();
    if(!parts.some(x=>normalize(x)===normalize(value)))parts.push(value);
    input.value=parts.join(', ')+(parts.length?', ':'');
  }else input.value=value;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  if(input.id==='v7WsIndustry'||input.id==='v7WsRegion'||input.id==='v7WsAudience')updateNameHint();
  closeAll();input.focus();
}
function updateHighlight(next){
  if(!active)return;
  const items=[...active.box.querySelectorAll('.v7SuggestItem')];if(!items.length)return;
  highlighted=(next+items.length)%items.length;
  items.forEach((x,i)=>x.classList.toggle('active',i===highlighted));
  items[highlighted]?.scrollIntoView({block:'nearest'});
}
function updateNameHint(){
  const name=document.querySelector('#v7WsName');if(!name||name.value.trim())return;
  const industry=(document.querySelector('#v7WsIndustry')?.value||'').trim();
  const region=(document.querySelector('#v7WsRegion')?.value||'').trim();
  name.placeholder=(region&&industry)?`${region} ${industry}`:(industry?`${industry} prospects`:'Poland Fintech');
}
function bind(input){
  if(!input||input.dataset.v7SuggestBound==='1')return;
  input.dataset.v7SuggestBound='1';
  input.setAttribute('autocomplete','off');
  input.addEventListener('focus',()=>render(input));
  input.addEventListener('input',()=>render(input));
  input.addEventListener('keydown',e=>{
    if(!active||active.input!==input)return;
    if(e.key==='ArrowDown'){e.preventDefault();updateHighlight(highlighted+1)}
    else if(e.key==='ArrowUp'){e.preventDefault();updateHighlight(highlighted-1)}
    else if(e.key==='Enter'&&highlighted>=0){e.preventDefault();choose(input,active.opts[highlighted][0])}
    else if(e.key==='Escape'){closeAll()}
  });
}
function install(){
  ['v7WsName','v7WsIndustry','v7WsRegion','v7WsSize','v7WsKeywords','v7WsOffer'].forEach(id=>bind(document.getElementById(id)));
  document.getElementById('v7WsAudience')?.addEventListener('change',updateNameHint);
}

document.addEventListener('mousedown',e=>{if(!e.target.closest('.v7Field'))closeAll()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeAll()});

const oldOpen=window.openV7WorkspaceModal;
if(typeof oldOpen==='function'){
  window.openV7WorkspaceModal=function(...args){const result=oldOpen.apply(this,args);setTimeout(()=>{install();updateNameHint()},0);return result};
}
install();
})();
