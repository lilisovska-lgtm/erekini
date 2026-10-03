"""Deterministic completion with provenance. Never invent contractual terms."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from invoice import Invoice
from extract import parse

UNITS={'gab':'C62','gab.':'C62','gabal':'C62','gabali':'C62','pcs':'C62','pc':'C62','piece':'C62','pieces':'C62','st':'HUR','st.':'HUR','stunda':'HUR','stundas':'HUR','h':'HUR','hr':'HUR','hours':'HUR','diena':'DAY','dienas':'DAY','day':'DAY','mēn':'MON','mēn.':'MON','mēnesis':'MON','month':'MON','kg':'KGM','kilograms':'KGM','m':'MTR','metri':'MTR','tūkst. gab.':'T3'}
CODES={'C62','H87','HUR','DAY','MON','KGM','MTR','T3'}
class Defaults(BaseModel):
    model_config=ConfigDict(extra='forbid')
    auto_endpoint:bool=True
    due_days:int|None=Field(default=None,ge=0,le=365,strict=True)
    reference:str=Field(default='',max_length=200)
    buyer_reg:str=Field(default='',max_length=11)
    unit:Literal['','C62','H87','HUR','DAY','MON','KGM','MTR','T3']=''
class CompletionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    invoice:Invoice
    defaults:Defaults=Field(default_factory=Defaults)
    source_text:str=Field(default='',max_length=150000)

def canonical(unit):
    raw=unit.strip()
    return raw.upper() if raw.upper() in CODES else UNITS.get(raw.lower(),'')

def complete(req):
    d=req.invoice.model_dump();changes=[];notes=[]
    def assign(container,key,value,path,reason):
        container[key]=value;changes.append({'field':path,'value':value,'reason':reason})

    # Infer only from an explicit seller statement, never a missing VAT identifier.
    statement=None
    for sentence in re.split(r'[.;]',re.sub(r'\s+',' ',req.source_text)):
        if re.search(r'\b(pircēj\w*|saņēmēj\w*|buyer|customer)\b',sentence,re.I):
            continue
        match=re.search(r'\b(?:pārdevējs|piegādātājs|uzņēmums|sabiedrība)\s+nav\s+(?:(?:reģistrēts|reģistrēta)\s+)?(?:PVN|pievienotās\s+vērtības\s+nodokļa)\s+maksātāj[sa]\b',sentence,re.I)
        if match:
            statement=match.group(0)
            break
    if statement:
        def zero_or_blank(value):
            try:return not value.strip() or Decimal(value.replace(',','.'))==0
            except InvalidOperation:return False
        safe=not d['supplier']['vat'].strip() and d['lines'] and all(zero_or_blank(row['rate']) for row in d['lines'])
        if safe:
            reason='Dokumentā skaidri norādīts: '+statement+'.'
            for i,row in enumerate(d['lines']):
                for key,value in [('category','E'),('rate','0')]:
                    if row[key]!=value:assign(row,key,value,f'lines.{i}.{key}',reason)
            if not d['exemption'].strip():assign(d,'exemption',statement+'. PVN nepiemēro.','exemption',reason)
            resolved='nav norādīta precīza nodokļa kategorija (z/e/o) pat ja pvn ir 0%, izmantota atbrīvojuma pēdējā frāze'
            remaining=[x for x in d['unsupported_features'] if x.strip().lower().rstrip('.!')!=resolved]
            if remaining!=d['unsupported_features']:
                assign(d,'unsupported_features',remaining,'unsupported_features','Nodokļa kategorijas nenoteiktība atrisināta pēc dokumenta teksta.')
            notes.append('Pārdevēja PVN nemaksātāja statuss atpazīts no dokumenta; izmantota paraugam atbilstoša kategorija E. Reģistra pārbaude nav veikta.')
        else:
            notes.append('Dokumentā norādīts PVN nemaksātāja statuss, bet dati ir pretrunīgi vai trūkst pozīciju. PVN kategorija automātiski netika mainīta.')

    source,_=parse(req.source_text)
    for field in ('reference','due'):
        if not d[field].strip() and source[field]:
            assign(d,field,source[field],field,'Nolasīts no dokumenta teksta.')
    for who in ('supplier','buyer'):
        p=d[who]
        if req.defaults.auto_endpoint and p['country'].strip().upper()=='LV':
            scheme=p['scheme'].strip();endpoint=p['endpoint'].strip();reg=p['reg'].strip();vat=p['vat'].strip()
            # Never overwrite or reinterpret a different explicit electronic address.
            if not endpoint:
                if scheme in ('','0218') and re.fullmatch(r'\d{11}',reg):
                    if not scheme:assign(p,'scheme','0218',who+'.scheme','Latvijas reģistrācijas numura shēma.')
                    assign(p,'endpoint',reg,who+'.endpoint','Atvasināts no Latvijas reģistrācijas numura; pārbaudiet ar saņēmēju.')
                elif scheme=='9939' and re.fullmatch(r'LV\d{11}',vat):
                    assign(p,'endpoint',vat,who+'.endpoint','Atvasināts no PVN numura izvēlētajai 9939 shēmai.')
            elif not scheme:
                if endpoint==reg and re.fullmatch(r'\d{11}',reg):assign(p,'scheme','0218',who+'.scheme','Identifikators sakrīt ar Latvijas reģistrācijas numuru.')
                elif endpoint==vat and re.fullmatch(r'LV\d{11}',vat):assign(p,'scheme','9939',who+'.scheme','Identifikators sakrīt ar Latvijas PVN numuru.')
    if not d['due'].strip():
        # Require an explicit invoice-date anchor; never interpret delivery/workday terms as calendar days.
        matches=re.findall(r'(?:apmaks\w*|samaks\w*)[^\n]{0,25}?\b(\d{1,3})\s+(?:kalendār\w*\s+)?dien\w*[^\n]{0,20}?no\s+rēķina\s+(?:izrakstīšanas|datuma)',req.source_text,re.I)
        days=None;reason=''
        if len(set(matches))==1:
            days=int(matches[0]);reason='Aprēķināts pēc dokumentā norādītā termiņa no rēķina datuma.'
        elif not matches and req.defaults.due_days is not None:
            # Do not replace unhandled printed payment terms with a chosen fallback.
            if re.search(r'(?:apmaks\w*|samaks\w*|payment|due)[^\n]{0,70}(?:dien|day|saņem|piegād)',req.source_text,re.I):
                notes.append('Dokumentā ir apmaksas nosacījumi, kurus nevar droši aprēķināt. Termiņš jāievada manuāli.')
            else:days=req.defaults.due_days;reason='Lietotāja noklusējums: '+str(days)+' kalendārās dienas no rēķina datuma.'
        if days is not None and 0<=days<=365:
            try:due=(date.fromisoformat(d['issue'])+timedelta(days=days)).isoformat()
            except (ValueError,OverflowError):notes.append('Apmaksas datuma aprēķinam nepieciešams derīgs rēķina datums.')
            else:assign(d,'due',due,'due',reason)
    if not d['reference'].strip() and req.defaults.reference.strip():
        if req.defaults.buyer_reg and req.defaults.buyer_reg==d['buyer']['reg'].strip():
            assign(d,'reference',req.defaults.reference.strip(),'reference','Lietotāja saglabātā atsauce šim pircēja reģistrācijas numuram.')
        else:notes.append('Noklusētā atsauce nav izmantota: pircēja reģistrācijas numurs nesakrīt ar iestatījumu.')
    for i,l in enumerate(d['lines']):
        unit=canonical(l['unit'])
        reason='Dokumenta mērvienības apzīmējums pārvērsts standarta kodā.'
        if not l['unit'].strip():
            candidates=[];unknown_source=False
            for row in source['lines']:
                try:same=row['name'].strip().casefold()==l['name'].strip().casefold() and Decimal(row['qty'].replace(',','.'))==Decimal(l['qty'].replace(',','.')) and Decimal(row['price'].replace(',','.'))==Decimal(l['price'].replace(',','.'))
                except InvalidOperation:same=False
                if same and canonical(row['unit']):candidates.append(canonical(row['unit']))
                elif same and row['unit'].strip():unknown_source=True
            if unknown_source:notes.append(f'{i+1}. pozīcijai dokumentā ir neatpazīta mērvienība; noklusējums netiek izmantots.')
            if candidates and not unknown_source and len(set(candidates))==1:unit=candidates[0];reason='Mērvienība no dokumenta rindas ar tādu pašu nosaukumu, daudzumu un cenu.'
            elif not candidates and not unknown_source and req.defaults.unit:unit=req.defaults.unit;reason='Lietotāja noklusētā mērvienība; pārbaudiet šo pozīciju.'
        if unit and unit!=l['unit']:assign(l,'unit',unit,f'lines.{i}.unit',reason)
    if changes:d['confirmed']=False
    missing=[]
    for f,label in [('reference','Pircēja atsauce'),('due','Apmaksas termiņš')]:
        if not d[f].strip() and not (f=='reference' and d['order_reference'].strip()):missing.append('Pircēja atsauce vai pasūtījuma numurs' if f=='reference' else label)
    for who,label in [('supplier','Pārdevējs'),('buyer','Pircējs')]:
        for f,title in [('scheme','elektroniskās adreses shēma'),('endpoint','elektroniskās adreses identifikators')]:
            if not d[who][f].strip():missing.append(label+': '+title)
    for i,l in enumerate(d['lines'],1):
        if not canonical(l['unit']):missing.append(f'{i}. pozīcijas mērvienība')
    return {'draft':d,'changes':changes,'notes':notes,'missing':missing}
