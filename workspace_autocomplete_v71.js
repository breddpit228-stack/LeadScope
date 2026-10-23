(function(){
'use strict';

const PICKERS={
  v7WsIndustry:{
    title:'Choose a category',
    options:[
      ['Fintech','Payments, banking, accounting and finance technology'],
      ['Software & SaaS','Cloud software and subscription products'],
      ['AI & Data','AI platforms, analytics, data and automation'],
      ['Cybersecurity','Security, identity, fraud and risk software'],
      ['Marketing & AdTech','Marketing, advertising and growth technology'],
      ['Sales & RevOps','Sales, prospecting, CRM and revenue operations'],
      ['HR & Recruiting','HR, recruiting, payroll and people software'],
      ['E-commerce & Retail','Commerce, retail and shopping technology'],
      ['Marketplace','Two-sided platforms and marketplaces'],
      ['Logistics & Supply Chain','Delivery, freight, warehousing and supply chain'],
      ['Climate & Energy','Energy, climate and sustainability technology'],
      ['Healthcare & Biotech','Healthtech, medical, clinical and life sciences'],
      ['Professional Services','Consulting, agencies and advisory businesses']
    ]
  },
  v7WsRegion:{
    title:'Choose a region',
    options:[
      ['Europe','All supported European countries'],
      ['Poland','Poland'],['Germany','Germany'],['United Kingdom','United Kingdom'],['France','France'],
      ['Netherlands','Netherlands'],['Sweden','Sweden'],['Denmark','Denmark'],['Norway','Norway'],
      ['Finland','Finland'],['Spain','Spain'],['Italy','Italy'],['Czechia','Czechia'],['Austria','Austria'],
      ['Switzerland','Switzerland'],['Belgium','Belgium'],['Ireland','Ireland'],['Estonia','Estonia'],
      ['Lithuania','Lithuania'],['Latvia','Latvia'],['Portugal','Portugal'],['Romania','Romania'],['Ukraine','Ukraine']
    ]
  },
  v7WsSize:{
    title:'Choose company size',
    options:[
      ['1–10','Micro / very early stage'],['11–50','Small company'],['51–200','SMB / scale-up'],
      ['201–500','Mid-market'],['501–1000','Upper mid-market'],['1001–5000','Large company'],['5000+','Enterprise']
    ]
  }
};

let openPicker=null;

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fieldWrap(input){return input?.closest('.v7Field')||null}
function closePickers(){
  document.querySelectorAll('.v7PickerMenu').forEach(x=>x.classList.add('hidden'));
  openPicker=null;
}
function ensureMenu(input){
  const wrap=fieldWrap(input);if(!wrap)return null;
  let menu=wrap.querySelector('.v7PickerMenu');
  if(!menu){menu=document.createElement('div');menu.className='v7PickerMenu hidden';wrap.appendChild(menu)}
  return menu;
}
function updateWorkspaceNameHint(){
  const name=document.querySelector('#v7WsName');if(!name||name.value.trim())return;
  const industry=(document.querySelector('#v7WsIndustry')?.value||'').trim();
  const region=(document.querySelector('#v7WsRegion')?.value||'').trim();
  if(region&&industry)name.placeholder=`${region} ${industry}`;
  else if(industry)name.placeholder=`${industry} prospects`;
  else name.placeholder='Poland Fintech';
}
function choose(input,value){
  input.value=value;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  closePickers();
  updateWorkspaceNameHint();
}
function showPicker(input){
  const config=PICKERS[input.id];if(!config)return;
  closePickers();
  const menu=ensureMenu(input);if(!menu)return;
  menu.innerHTML=`<div class="v7PickerTitle">${esc(config.title)}</div><div class="v7PickerOptions">${config.options.map(([value,desc])=>`<button type="button" class="v7PickerOption${input.value===value?' selected':''}" data-value="${esc(value)}"><span>${esc(value)}</span><small>${esc(desc)}</small></button>`).join('')}</div>`;
  menu.classList.remove('hidden');
  openPicker={input,menu};
  menu.querySelectorAll('.v7PickerOption').forEach(btn=>btn.addEventListener('mousedown',e=>{e.preventDefault();choose(input,btn.dataset.value)}));
}
function bindPicker(id){
  const input=document.getElementById(id);if(!input||input.dataset.v7PickerBound==='1')return;
  input.dataset.v7PickerBound='1';
  input.readOnly=true;
  input.setAttribute('autocomplete','off');
  input.classList.add('v7PickerInput');
  if(id==='v7WsIndustry')input.placeholder='Choose category';
  if(id==='v7WsRegion')input.placeholder='Choose region';
  if(id==='v7WsSize')input.placeholder='Choose size';
  input.addEventListener('focus',()=>showPicker(input));
  input.addEventListener('click',()=>showPicker(input));
  input.addEventListener('keydown',e=>{
    if(e.key==='Enter'||e.key==='ArrowDown'||e.key===' '){e.preventDefault();showPicker(input)}
    if(e.key==='Escape')closePickers();
  });
}
function install(){
  Object.keys(PICKERS).forEach(bindPicker);
  document.getElementById('v7WsAudience')?.addEventListener('change',updateWorkspaceNameHint);
  updateWorkspaceNameHint();
}

document.addEventListener('mousedown',e=>{
  if(!e.target.closest('.v7Field'))closePickers();
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePickers()});

const oldOpen=window.openV7WorkspaceModal;
if(typeof oldOpen==='function'){
  window.openV7WorkspaceModal=function(...args){
    const result=oldOpen.apply(this,args);
    setTimeout(()=>{
      install();
      updateWorkspaceNameHint();
      const isNew=!args[0];
      if(isNew){
        const industry=document.getElementById('v7WsIndustry');
        if(industry){industry.focus();showPicker(industry)}
      }
    },0);
    return result;
  };
}
install();
})();
