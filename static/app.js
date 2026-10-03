'use strict';
const $=s=>document.querySelector(s);
const form=$('#invoice-form');
let working=false;
let sourceFilename='';
function invoiceFilename(fallback){
 if(!sourceFilename)return fallback;
 const base=sourceFilename.replace(/\.[^.]+$/,'').replace(/[\x00-\x1f\x7f<>:"/\\|?*]/g,'_').trim().replace(/[. ]+$/,'');
 return base?base+'.xml':fallback;
}
let aiConfig={configured:false,protected:false};
let unsupportedFeatures=[];
const secureTransport=location.protocol==='https:'||['localhost','127.0.0.1','[::1]'].includes(location.hostname);
const partyFields=[['name','Uzņēmuma nosaukums'],['reg','Reģistrācijas numurs'],['vat','PVN numurs (ja ir)'],['street','Iela, mājas / telpas numurs'],['city','Pilsēta / novads'],['postal','Pasta indekss'],['country','Valsts kods'],['scheme','Elektroniskās adreses shēma'],['endpoint','Elektroniskās adreses identifikators']];
for(const who of ['supplier','buyer']){
 for(const [key,title] of partyFields){
  const label=document.createElement('label');label.textContent=title;
  const input=document.createElement(key==='scheme'?'select':'input');input.name=who+'.'+key;
  if(key==='scheme')for(const [v,t] of [['','Izvēlies'],['0218','0218 — Latvijas reģ. numurs'],['9939','9939 — Latvijas PVN numurs']])input.add(new Option(t,v));
  else{input.maxLength=key==='country'?2:key==='name'?200:300;input.required=!['vat','street','city','postal'].includes(key);input.autocomplete='off';if(key==='country')input.defaultValue='LV';}
  label.append(input);
  if(key==='endpoint'){const hint=document.createElement('small');hint.textContent='Ievadi apstiprinātu identifikatoru. Shēmai 0218 — 11 ciparu reģistrācijas numurs; 9939 — PVN numurs ar LV.';label.append(hint);}
  $('#'+who).append(label);
 }
}
const lineFields=[['name','Nosaukums'],['qty','Daudzums'],['unit','Mērvienība'],['price','Cena bez PVN'],['category','PVN kategorija'],['rate','PVN %']];
function addLine(value={}){
 if($('#lines').children.length>=100)return;
 const row=document.createElement('div');row.className='line';
 for(const [key,title] of lineFields){
  const label=document.createElement('label');label.textContent=title;
  const input=document.createElement(['unit','category'].includes(key)?'select':'input');input.dataset.field=key;input.required=true;
  if(key==='unit')for(const [v,t] of [['','Izvēlies'],['C62','gab.'],['H87','gab. (H87)'],['T3','tūkst. gab.'],['HUR','stundas'],['DAY','dienas'],['MON','mēneši'],['KGM','kg'],['MTR','metri']])input.add(new Option(t,v));
  else if(key==='category')for(const [v,t] of [['','Izvēlies'],['S','S — ar PVN'],['Z','Z — 0%'],['E','E — atbrīvots'],['O','O — PVN nepiemēro (arī PVN nemaksātājam)']])input.add(new Option(t,v));
  else{input.maxLength=key==='name'?200:300;if(key!=='name')input.inputMode='decimal';}
  if(input.tagName==='SELECT'&&value[key]&&!Array.from(input.options).some(o=>o.value===value[key]))input.add(new Option('Jāpārbauda: '+value[key],value[key]));
  input.value=value[key]??'';label.append(input);row.append(label);
 }
 const remove=document.createElement('button');remove.type='button';remove.className='remove';remove.textContent='×';remove.setAttribute('aria-label','Dzēst pozīciju');remove.onclick=()=>{row.remove();$('#confirmed').checked=false;};row.append(remove);$('#lines').append(row);
}
function fill(data){
 form.reset();
 unsupportedFeatures=data.unsupported_features||[];
 messages('#blockers',unsupportedFeatures.map(x=>'Eksports bloķēts: '+x));
 for(const [key,value] of Object.entries(data)){
  if(['supplier','buyer'].includes(key)){for(const [k,v] of Object.entries(value))if(form.elements[key+'.'+k]){const el=form.elements[key+'.'+k];if(el.tagName==='SELECT'&&v&&!Array.from(el.options).some(o=>o.value===v))el.add(new Option('Jāpārbauda: '+v,v));el.value=v;}}
  else if(typeof value==='string'&&form.elements[key])form.elements[key].value=value;
 }
 $('#lines').replaceChildren();(data.lines?.length?data.lines:[{}]).forEach(addLine);$('#confirmed').checked=false;
 syncEndpoints(true);
}
function collect(){
 const data={supplier:{},buyer:{},lines:[]};
 for(const [key,value] of new FormData(form)){
  if(key.includes('.')){const [p,k]=key.split('.');data[p][k]=value.trim();}
  else data[key]=value.trim();
 }
 data.lines=[...$('#lines').children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-field]')].map(el=>[el.dataset.field,el.value.trim()])));
 data.confirmed=$('#confirmed').checked;data.unsupported_features=unsupportedFeatures;return data;
}
function messages(id,items){const box=$(id);box.replaceChildren();box.hidden=!items?.length;if(items?.length){const list=document.createElement('ul');for(const text of items){const li=document.createElement('li');li.textContent=text;list.append(li);}box.append(list);}}
function setBusy(flag,text=''){working=flag;for(const el of document.querySelectorAll('button,input,select'))el.disabled=flag;$('#status').textContent=text;form.setAttribute('aria-busy',String(flag));updateMode();}
async function request(url,options={}){let res;try{res=await fetch(url,options);}catch{throw {errors:['Neizdevās savienoties ar serveri. Pārbaudi SSH tuneli un mēģini vēlreiz.']};}let data;try{data=await res.json();}catch{throw {errors:['Serveris neatbildēja paredzētajā formātā. Mēģini ar mazāku failu.']};}if(!res.ok)throw data;return data;}
function fail(error){messages('#errors',error.errors||['Neizdevās apstrādāt datus. Pārlādē lapu un mēģini vēlreiz.']);$('#errors').scrollIntoView({block:'center'});
 if(error.errors?.some(message=>message.includes('IBAN'))){
  const input=form.elements.iban;input.setAttribute('aria-invalid','true');
  input.focus({preventScroll:true});
  const link=document.createElement('a');link.href='#iban-help';link.textContent='Atvērt IBAN lauku';
  link.onclick=event=>{event.preventDefault();input.scrollIntoView({block:'center'});input.focus({preventScroll:true});};
  $('#errors').append(link);
 }}
$('#add-line').onclick=()=>{addLine();$('#confirmed').checked=false;};
form.addEventListener('input',event=>{
 if(event.target.id!=='confirmed')$('#confirmed').checked=false;
 if(event.target.name==='iban')event.target.removeAttribute('aria-invalid');
 if(/^(supplier|buyer)\.(reg|country)$/.test(event.target.name))syncEndpoints();
 if(/^(supplier|buyer)\.(endpoint|scheme)$/.test(event.target.name))delete form.elements[event.target.name.split('.')[0]+'.endpoint'].dataset.automatic;
});
function syncEndpoints(reset=false){
 for(const who of ['supplier','buyer']){
  const reg=form.elements[who+'.reg'].value.trim(),country=form.elements[who+'.country'].value.trim().toUpperCase();
  const endpoint=form.elements[who+'.endpoint'],scheme=form.elements[who+'.scheme'];
  if(reset){
   delete endpoint.dataset.automatic;
   if(endpoint.value===reg&&scheme.value==='0218')endpoint.dataset.automatic='true';
  }
  const managed=endpoint.dataset.automatic==='true';
  if(country==='LV'&&/^\d{11}$/.test(reg)){
   if(managed||(!endpoint.value.trim()&&['','0218'].includes(scheme.value))){
    if(endpoint.value!==reg||scheme.value!=='0218')$('#confirmed').checked=false;
    endpoint.value=reg;scheme.value='0218';endpoint.dataset.automatic='true';
   }
  }else if(managed){endpoint.value='';scheme.value='';}
 }
}
$('#file').onchange=async event=>{
 const file=event.target.files[0];if(!file||working)return;
 if(file.name.toLowerCase().endsWith('.xml')){$('#mode').value='local';updateMode();}
 if(file.size>10000000){fail({errors:['Maksimālais faila izmērs ir 10 MB.']});event.target.value='';return;}
 if($('#mode').value==='ai'&&(!aiConfig.configured||!aiConfig.protected||!secureTransport||!$('#access-password').value)){fail({errors:[$('#ai-status').textContent+' Ievadi rīka piekļuves paroli vai izvēlies lokālo režīmu.']});event.target.value='';return;}
 if(!confirmReplace()){event.target.value='';return;}
 const payload=new FormData();payload.append('file',file);payload.append('mode',$('#mode').value);
 const headers=$('#mode').value==='ai'?{'X-Invoice-Password':$('#access-password').value}:{};
 messages('#errors',[]);messages('#notes',[]);messages('#completion-report',[]);setBusy(true,$('#mode').value==='ai'?'Nolasu dokumentu un nosūtu OpenAI atpazīšanai…':'Nolasu dokumentu lokāli. Skenēta PDF apstrāde var aizņemt vairākas minūtes…');
 try{const data=await request('api/extract',{method:'POST',headers,body:payload});fill(data.draft);sourceFilename=file.name;$('#filename').textContent=file.name;$('#source').textContent=data.text;await completeCurrent(data.draft,data.text);$('#source').dataset.loaded='true';messages('#notes',data.notes);$('#filename').textContent=file.name;}
 catch(e){fail(e);}finally{setBusy(false);event.target.value='';}
};
function confirmReplace(){return !form.elements.number.value&&!$('#source').dataset.loaded||window.confirm('Aizstāt pašreizējos formas datus ar citu dokumentu?');}
$('#demo').onclick=async()=>{
 if(!confirmReplace())return;
 setBusy(true,'Ielādēju paraugu…');messages('#errors',[]);
 try{fill(await request('api/demo'));sourceFilename='';$('#source').textContent=await (await fetch('demo.txt')).text();$('#source').dataset.loaded='true';$('#filename').textContent='Demonstrācijas rēķins — izdomāti uzņēmumi';messages('#notes',['Paraugs satur izdomātus rekvizītus. Tas paredzēts tikai rīka izmēģināšanai.']);}
 catch(e){fail(e);}finally{setBusy(false);}
};
form.onsubmit=async event=>{
 event.preventDefault();if(working)return;
 if(unsupportedFeatures.length){fail({errors:['MI atrada neatbalstītu rēķina veidu vai nosacījumus. Eksports ir bloķēts; izvēlies citu dokumentu.']});return;}
 const payload=collect();messages('#errors',[]);setBusy(true,'Pārbaudu summas, XML struktūru un Peppol noteikumus…');
 let done='';
 try{
  const completed=await completeCurrent(payload,$('#source').dataset.loaded?$('#source').textContent:'');
  if(completed.changes.length)throw {errors:['Trūkstošie lauki papildināti. Pārskati izmaiņas un vēlreiz atzīmē datu apstiprinājumu. Ja informācijas vēl trūkst, vari saglabāt XML melnrakstu.']};
  const data=await request('api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(completed.draft)});
  const url=URL.createObjectURL(new Blob([data.xml],{type:'application/xml'}));const a=document.createElement('a');a.href=url;a.download=invoiceFilename(data.filename);document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
  messages('#notes',data.warnings);done=`Pārbaudes izietas. XML lejupielādēts. Bez PVN: ${data.totals.net} EUR · PVN: ${data.totals.vat} EUR · Apmaksai: ${data.totals.total} EUR.`;
 }catch(e){fail(e);}finally{setBusy(false,done);}
};
$('#reset').onclick=()=>{if(window.confirm('Notīrīt visus rēķina datus?')){fill({});sourceFilename='';form.elements.currency.value='EUR';$('#source').textContent='Dati notīrīti.';delete $('#source').dataset.loaded;$('#filename').textContent='Dokuments vēl nav izvēlēts.';messages('#errors',[]);messages('#notes',[]);$('#status').textContent='';messages('#completion-report',[]);$('#access-password').value='';updateMode();}};
$('#transport').hidden=location.protocol==='https:'||['localhost','127.0.0.1'].includes(location.hostname);
addLine();

function updateMode(){
 const ai=$('#mode').value==='ai';
 $('#password-label').hidden=!ai;$('#ai-privacy').hidden=!ai;
 $('#access-password').disabled=working||!secureTransport||!aiConfig.configured||!aiConfig.protected;
 $('#export').disabled=working||unsupportedFeatures.length>0;
 $('#ai-status').textContent=!ai?'Lokālais režīms: dokumenti netiek sūtīti ārējam MI.':
 !aiConfig.configured?'OpenAI API atslēga vēl nav pievienota serverī. Pieejams paraugs un lokālais režīms.':
 !aiConfig.protected?'Serverī vēl jāiestata rīka piekļuves parole.':
 !secureTransport?'MI konfigurēts. Lietošanai nepieciešams HTTPS vai SSH tunelis; paroli pa publisku HTTP nosūtīt nevar.':
 'OpenAI ir konfigurēts. Ievadi rīka paroli un izvēlies dokumentu. Modelis: '+aiConfig.model;
}
$('#mode').onchange=()=>{if($('#mode').value==='local')$('#access-password').value='';updateMode();};
request('api/config').then(config=>{aiConfig=config;updateMode();}).catch(()=>{$('#ai-status').textContent='Neizdevās pārbaudīt MI konfigurāciju. Pārlādē lapu.';});
updateMode();

function getDefaults(){
 const raw=$('#default-days').value;
 if(raw!==''&&(!Number.isInteger(Number(raw))||Number(raw)<0||Number(raw)>365))throw {errors:['Noklusētais apmaksas termiņš: vesels skaitlis no 0 līdz 365.']};
 return {auto_endpoint:true,due_days:raw===''?null:Number(raw),reference:$('#default-reference').value.trim(),buyer_reg:$('#default-buyer').value.trim(),unit:$('#default-unit').value};
}
function showDefaults(d){$('#default-days').value=d.due_days??'';$('#default-reference').value=d.reference||'';$('#default-buyer').value=d.buyer_reg||'';$('#default-unit').value=d.unit||'';}
async function completeCurrent(draft,text){
 const result=await request('api/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({invoice:draft,source_text:text,defaults:getDefaults()})});
 fill(result.draft);
 result.draft.confirmed=Boolean(draft.confirmed)&&result.changes.length===0;
 $('#confirmed').checked=result.draft.confirmed;
 const labels={exemption:'PVN pamatojums',unsupported_features:'Atrisināts PVN brīdinājums',reference:'Pircēja atsauce',due:'Apmaksas termiņš','supplier.scheme':'Pārdevēja adreses shēma','supplier.endpoint':'Pārdevēja elektroniskā adrese','buyer.scheme':'Pircēja adreses shēma','buyer.endpoint':'Pircēja elektroniskā adrese'};
 const report=result.changes.map(c=>(labels[c.field]||('Pozīcija '+(Number(c.field.split('.')[1])+1)+': '+({unit:'mērvienība',category:'PVN kategorija',rate:'PVN %'}[c.field.split('.')[2]]||'lauks')))+': '+c.value+' — '+c.reason);
 report.push(...result.notes);if(result.missing.length)report.push('Paliek tukši (gatavam e-rēķinam jāpapildina): '+result.missing.join('; ')+'.');
 if(!report.length)report.push('Šie lauki jau ir aizpildīti; nekas netika mainīts.');
 messages('#completion-report',report);
 return result;
}
$('#complete-fields').onclick=async()=>{
 const draft=collect(),text=$('#source').dataset.loaded?$('#source').textContent:'';
 setBusy(true,'Aizpildu trūkstošos laukus bez atkārtota MI pieprasījuma…');
 try{await completeCurrent(draft,text);}catch(e){fail(e);}finally{setBusy(false);}
};
$('#save-defaults').onclick=()=>{try{localStorage.setItem('invoice-defaults-v1',JSON.stringify(getDefaults()));$('#defaults-status').textContent='Iestatījumi saglabāti tikai šajā pārlūkā. API atslēga un parole netiek saglabāta.';}catch(e){fail(e.errors?e:{errors:['Pārlūks neļauj saglabāt iestatījumus.']});}};
$('#clear-defaults').onclick=()=>{try{localStorage.removeItem('invoice-defaults-v1');}catch{}showDefaults({});$('#defaults-status').textContent='Saglabātie noklusējumi dzēsti.';};
try{const saved=JSON.parse(localStorage.getItem('invoice-defaults-v1'));if(saved&&typeof saved==='object')showDefaults(saved);}catch{}

$('#draft-export').onclick=async()=>{
 if(working)return;
 const payload=collect();messages('#errors',[]);setBusy(true,'Sagatavoju XML melnrakstu…');
 try{
  const completed=await completeCurrent(payload,$('#source').dataset.loaded?$('#source').textContent:'');
  const data=await request('api/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(completed.draft)});
  const url=URL.createObjectURL(new Blob([data.xml],{type:'application/xml'}));
  const a=document.createElement('a');a.href=url;a.download=data.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
  messages('#notes',['Saglabāts nepārbaudīts XML melnraksts ar tukšajiem laukiem. Tas nav UBL e-rēķins iesniegšanai klientam.']);
 }catch(e){fail(e);}finally{setBusy(false);}
};

$('#non-vat').onclick=()=>{
 if(form.elements['supplier.vat'].value.trim()){
  fail({errors:['Pārdevējam ir norādīts PVN numurs. Vispirms salīdzini to ar oriģinālu un precizē PVN statusu; numurs netiks automātiski dzēsts.']});return;
 }
 for(const row of $('#lines').children){
  row.querySelector('[data-field="category"]').value='E';
  row.querySelector('[data-field="rate"]').value='0';
 }
 if(!form.elements.exemption.value.trim())form.elements.exemption.value='Pārdevējs nav reģistrēts PVN maksātājs. PVN nepiemēro.';
 // This specific extraction uncertainty is resolved by the user's explicit VAT choice.
 // Keep all other blockers, including unsupported invoice types and payment conditions.
 const resolvedTaxMessage='nav norādīta precīza nodokļa kategorija (z/e/o) pat ja pvn ir 0%, izmantota atbrīvojuma pēdējā frāze';
 unsupportedFeatures=unsupportedFeatures.filter(message=>message.trim().toLocaleLowerCase('lv').replace(/[.!]+$/,'')!==resolvedTaxMessage);
 messages('#blockers',unsupportedFeatures.map(x=>'Eksports bloķēts: '+x));
 updateMode();
 $('#confirmed').checked=false;
 messages('#errors',[]);
 messages('#notes',['Visām pozīcijām izvēlēta kategorija E ar PVN 0 atbilstoši iesniegtajam paraugam. Pārdevēja reģistrācijas numurs XML būs nodokļu identifikators (!=VAT), pircēja PVN numurs saglabāsies. Pārbaudi pamatojumu un kopsummu pret oriģinālu.']);
};
