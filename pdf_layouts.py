"""Conservative extraction for the two observed Latvian invoice layouts."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
def enrich(text,d):
    notes=[]
    is_portal='Latvija.gov.lv e-rēķinu risinājumā' in text
    is_rental=all(x in text for x in ('Pakalpojums','Mērv.','Kopā ar PVN:','Piegādātājs:'))
    if not (is_portal or is_rental):return notes
    def find(pattern,src=text):
        m=re.search(pattern,src,re.I|re.M)
        return m.group(1).strip() if m else ''
    def amount(v):return v.replace(' ','').replace(',','.')
    def iso(v):
        try:
            day,month,year=map(int,v.rstrip('.').split('.'));return date(year,month,day).isoformat()
        except ValueError:return ''
    d['number']=find(r'^\s*Rēķins\s+Nr\.\s*(.+?)\s*$')
    issued=find(r'^\s*(\d{2}\.\d{2}\.\d{4})\.')
    if issued:d['issue']=iso(issued)
    else:
        m=re.search(r'(\d{4})\.gada\s+(\d{1,2})\.\s*(\w+)',text)
        months=['janvāris','februāris','marts','aprīlis','maijs','jūnijs','jūlijs','augusts','septembris','oktobris','novembris','decembris']
        if m and m[3].lower() in months:
            try:d['issue']=date(int(m[1]),months.index(m[3].lower())+1,int(m[2])).isoformat()
            except ValueError:pass
    d['due']=iso(find(r'(?:Samaksāt līdz|Rēķins jāapmaksā līdz):\s*(\d{2}\.\d{2}\.\d{4})'))
    supplier=re.search(r'Piegādātājs:\s*(.*?)(?=Pasūtītājs:|Saņēmējs:)',text,re.S)
    buyer=re.search(r'(?:Pasūtītājs|Saņēmējs):\s*(.*?)(?=Papildu informācija|^Adrese:|Pakalpojuma sniegšanas periods:|\Z)',text,re.S|re.M)
    for who,match in [('supplier',supplier),('buyer',buyer)]:
        if not match:continue
        block=match[1];p=d[who]
        p['name']=re.split(r'\s{2,}',block.splitlines()[0].strip())[0]
        p['reg']=find(r'(?:Reģistrācijas nr\./Personas kods|Vienotais reģ\. Nr\./NMR kods|Reģ\. Nr\.):\s*(\d{11})',block)
        p['vat']=find(r'PVN\s+(?:Reģ\.\s*)?Nr\.:\s*(LV\d{11})',block)
        p['street']=re.split(r'\s{2,}',find(r'Juridiskā adrese:\s*(.+)',block))[0]
        p['postal']=find(r'\b(LV-\d{4})\b',p['street'])
        if who=='supplier':d['iban']=find(r'Bankas konts:\s*([A-Z]{2}\d{2}[A-Z0-9]+)',block)
    d['reference']=re.split(r'\s{2,}',find(r'Pircēja atsauce:\s*(.+)'))[0]
    d['contract_reference']=find(r'Līguma Nr\.:\s*(.+)')
    d['source_total']=amount(find(r'(?:Summa apmaksai \(EUR\)|Kopā apmaksai, EUR):?\s*([\d.,]+)'))
    d['lines']=[]
    num=r'(\d+(?:[.,]\d+)?)'
    pattern=(r'^\s*\d+\.\s+(.+?)\s{2,}'+num+r'\s+(\S+)\s+'+num+r'\s+'+num+r'\s+'+num+r'\s+'+num+r'\s*$') if is_portal else (r'^\s*\d+\s+(.+?)\s{2,}'+num+r'\s+(?:(\S+)\s+)?'+num+r'\s+'+num+r'\s*$')
    global_rate=find(r'PVN\s+(\d+(?:[.,]\d+)?)%\s*\(no summas')
    for m in re.finditer(pattern,text,re.M):
        if is_portal:
            name,qty,unit,price,base,rate,total=m.groups()
            if Decimal(amount(base))!=1:
                d.setdefault('unsupported_features',[]).append('Cenas bāzes daudzums nav 1.')
        else:
            name,qty,unit,price,total=m.groups();rate=global_rate;unit=unit or ''
        qty,price,total=map(amount,(qty,price,total))
        rate=amount(rate)
        if Decimal(qty)*Decimal(price)!=Decimal(total):
            notes.append('Pozīcijas summa nesakrīt ar daudzumu un cenu; pārbaudiet oriģinālu.')
            d.setdefault('unsupported_features',[]).append('Nesakrīt dokumentā norādītā pozīcijas summa.')
        d['lines'].append(dict(name=name.strip(),qty=qty,unit={'gab.':'C62','gab':'C62'}.get(unit,unit),price=price,rate=rate,category='S' if rate and Decimal(rate)>0 else ''))
    if is_portal:
        normalized=re.sub(r'\s+',' ',text)
        reason=find(r'Nodokļa atbrīvojuma pamatojums:\s*(.*?)(?=Vienības|Nosaukums)',normalized)
        d['exemption']=reason
        d['note']=find(r'Papildinformācija:\s*(.*?)(?=Nodokļa atbrīvojuma pamatojums:|Vienības|Nosaukums)',normalized)
        prepaid=find(r'Avansā samaksāts \(EUR\)\s*([\d.,]+)')
        if prepaid and Decimal(amount(prepaid))!=0:d.setdefault('unsupported_features',[]).append('Rēķinā ir nenulles avansa maksājums.')
    notes.append('Lokāli atpazīts dokumenta izkārtojums. Trūkstošās atsauces un mērvienības netiek izdomātas.')
    return notes
