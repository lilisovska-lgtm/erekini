from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import Lock
import re
from lxml import etree as E
from pydantic import BaseModel, ConfigDict, Field
from saxonche import PySaxonProcessor

class Party(BaseModel):
    model_config=ConfigDict(extra='forbid',str_max_length=300)
    name:str='';reg:str='';vat:str='';street:str='';city:str='';postal:str='';country:str='LV';endpoint:str='';scheme:str='0218'
class Line(BaseModel):
    model_config=ConfigDict(extra='forbid',str_max_length=300)
    name:str='';qty:str='';unit:str='';price:str='';rate:str='';category:str=''
class Invoice(BaseModel):
    model_config=ConfigDict(extra='forbid',str_max_length=500)
    invoice_type:str='380';note:str='';contract_reference:str='';number:str='';issue:str='';due:str='';tax_date:str='';reference:str='';order_reference:str=Field(default='',max_length=200);currency:str='EUR';iban:str=''
    supplier:Party=Field(default_factory=Party);buyer:Party=Field(default_factory=Party)
    lines:list[Line]=Field(default_factory=list,max_length=100)
    source_total:str='';exemption:str='';confirmed:bool=False
    unsupported_features:list[str]=Field(default_factory=list,max_length=40)

CENT=Decimal('.01')
def money(n):return n.quantize(CENT,rounding=ROUND_HALF_UP)
def dec(s):
    v=Decimal(s.strip().replace(',','.'))
    if not v.is_finite() or abs(v)>Decimal('1000000000') or v.as_tuple().exponent < -6:raise ValueError()
    return v

def check(inv):
    d=inv.model_dump();errors=[];groups={};items=[]
    for feature in d['unsupported_features']:errors.append('Neatbalstīts dokuments: '+feature)
    if len(d['number'])>35:errors.append('Rēķina numurs: Latvija.gov.lv paraugā limits ir 35 rakstzīmes.')
    if len(d['reference'])>200:errors.append('Pircēja atsauce: maksimāli 200 rakstzīmes.')
    if not d['confirmed']:errors.append('Apstipriniet, ka salīdzinājāt datus ar oriģinālu un tas ir atbalstīts rēķins.')
    for key,label in [('number','Rēķina numurs')]:
        if not d[key].strip():errors.append(label+': obligāts lauks.')
    if not d['reference'].strip() and not d['order_reference'].strip():errors.append('Gatavam Peppol e-rēķinam norādiet pircēja atsauci vai pasūtījuma numuru. Ja abi nav zināmi, saglabājiet XML melnrakstu.')
    if d['invoice_type'] not in ('380','80'):errors.append('Neatbalstīts rēķina tipa kods.')
    dates={}
    for key,label in [('issue','Izrakstīšanas datums'),('due','Apmaksas termiņš'),('tax_date','PVN datums')]:
        if key=='tax_date' and not d[key]:continue
        try:dates[key]=date.fromisoformat(d[key])
        except ValueError:errors.append(label+': ievadiet derīgu datumu.')
    if dates.get('issue') and dates.get('due') and dates['due']<dates['issue']:errors.append('Apmaksas termiņš nedrīkst būt pirms izrakstīšanas datuma.')
    if d['currency']!='EUR':errors.append('Šī versija atbalsta tikai EUR.')
    for key,label in [('supplier','Pārdevējs'),('buyer','Pircējs')]:
        p=d[key]
        if p['country']!='LV':errors.append(f'{label}: šī versija atbalsta Latvijas uzņēmumus; pārbaudiet valsti.')
        if len(p['name'])>200:errors.append(f'{label}: nosaukumam maksimāli 200 rakstzīmes.')
        for field,fl in [('name','nosaukums')]:
            if not p[field].strip():errors.append(f'{label}: {fl} ir obligāts.')
        if not re.fullmatch(r'\d{11}',p['reg']):errors.append(f'{label}: vajadzīgs Latvijas 11 ciparu reģistrācijas numurs.')
        if p['vat'] and not re.fullmatch(r'LV\d{11}',p['vat']):errors.append(f'{label}: PVN numura formāts ir LV un 11 cipari.')
        if p['scheme'] not in ('0218','9939'):errors.append(f'{label}: neatbalstīta elektroniskās adreses shēma.')
        if not re.fullmatch(r'\d{11}' if p['scheme']=='0218' else r'LV\d{11}',p['endpoint']):errors.append(f'{label}: pārbaudiet elektronisko adresi atbilstoši izvēlētajai shēmai.')
    iban=re.sub(r'\s','',d['iban']).upper();d['iban']=iban
    if iban:
        if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}',iban):errors.append('Pārdevēja IBAN formāts nav derīgs. Salīdziniet konta numuru ar oriģinālo rēķinu un izlabojiet lauku “Pārdevēja IBAN”.')
        else:
            n=''.join(str(ord(c)-55) if c.isalpha() else c for c in iban[4:]+iban[:4])
            if int(n)%97!=1:errors.append('Pārdevēja IBAN kontrolsumma nav derīga. Salīdziniet katru simbolu ar oriģinālo rēķinu un izlabojiet lauku “Pārdevēja IBAN”. Konta numurs netiek automātiski minēts; līdz precizēšanai varat saglabāt XML melnrakstu.')
    if not d['lines']:errors.append('Pievienojiet vismaz vienu rēķina pozīciju.')
    for i,line in enumerate(d['lines'],1):
        prefix=f'Pozīcija {i}: '
        if len(line['name'])>200:errors.append(prefix+'nosaukumam maksimāli 200 rakstzīmes.')
        if not line['name'].strip():errors.append(prefix+'trūkst nosaukuma.')
        if line['unit'] not in ('C62','H87','HUR','DAY','MON','KGM','MTR','T3'):errors.append(prefix+'izvēlieties mērvienību.')
        try:
            qty,price,rate=map(dec,(line['qty'],line['price'],line['rate']))
            if qty<=0 or price<0 or not 0<=rate<=100:raise ValueError()
            category=line['category']
            if category not in ('S','Z','E','O'):errors.append(prefix+'izvēlieties PVN kategoriju.')
            elif category=='S' and rate not in (Decimal(5),Decimal(12),Decimal(21)):errors.append(prefix+'atbalstītās PVN likmes ir 5, 12 un 21%.')
            elif category!='S' and rate!=0:errors.append(prefix+'šai PVN kategorijai likmei jābūt 0%.')
            net=money(qty*price)
            groups[(category,rate)]=groups.get((category,rate),Decimal(0))+net
            items.append(dict(**line,net=net,qty_d=qty,price_d=price,rate_d=rate))
        except (InvalidOperation,ValueError):errors.append(prefix+'pārbaudiet daudzumu, cenu un PVN likmi (līdz 6 zīmēm aiz komata).')
    cats={k[0] for k in groups}
    if cats & {'S','Z'} and not d['supplier']['vat']:errors.append('Pārdevēja PVN numurs ir vajadzīgs izvēlētajai PVN kategorijai.')
    if 'O' in cats:
        if len(cats)>1:errors.append('PVN kategoriju O nevar apvienot ar citām kategorijām.')
        if d['supplier']['vat']:errors.append('Izvēlēts “PVN nepiemēro”, bet pārdevējam norādīts PVN numurs. Pārbaudiet pārdevēja statusu un kategoriju.')
    if cats & {'E','O'} and not d['exemption'].strip():errors.append('Norādiet PVN atbrīvojuma vai nepiemērošanas pamatojumu.')
    net=sum(groups.values(),Decimal(0));tax=sum((money(v*k[1]/100) for k,v in groups.items()),Decimal(0));total=net+tax
    try:
        source=dec(d['source_total'])
        if source<0 or source!=money(source):raise ValueError()
        if source!=total:errors.append(f'Kopsumma nesakrīt: no pozīcijām {total:.2f} EUR, oriģinālā {source:.2f} EUR.')
    except (ValueError,InvalidOperation):errors.append('Ievadiet oriģinālā rēķina apmaksas summu ar ne vairāk kā 2 zīmēm aiz komata.')
    return d,items,groups,net,tax,total,errors

NS={'inv':'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2','cac':'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2','cbc':'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'}
def el(parent,kind,name,text=None,**attrs):
    child=E.SubElement(parent,E.QName(NS[kind],name),**attrs)
    if text is not None:child.text=str(text)
    return child

def make_xml(d,items,groups,net,tax,total):
    root=E.Element(E.QName(NS['inv'],'Invoice'),nsmap={None:NS['inv'],'cac':NS['cac'],'cbc':NS['cbc']})
    def b(p,n,t,**attrs):return el(p,'cbc',n,t,**attrs)
    def a(p,n):return el(p,'cac',n)
    def amt(p,n,t):return b(p,n,f'{t:.2f}',currencyID='EUR')
    b(root,'CustomizationID','urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')
    b(root,'ProfileID','urn:fdc:peppol.eu:2017:poacc:billing:01:1.0')
    b(root,'ID',d['number']);b(root,'IssueDate',d['issue']);b(root,'DueDate',d['due']);b(root,'InvoiceTypeCode',d['invoice_type'])
    if d['note']:b(root,'Note',d['note'])
    if d['tax_date']:b(root,'TaxPointDate',d['tax_date'])
    b(root,'DocumentCurrencyCode','EUR')
    if d['reference'].strip():b(root,'BuyerReference',d['reference'])
    if d['order_reference'].strip():b(a(root,'OrderReference'),'ID',d['order_reference'])
    if d['contract_reference']:b(a(root,'ContractDocumentReference'),'ID',d['contract_reference'])
    for key,tag in [('supplier','AccountingSupplierParty'),('buyer','AccountingCustomerParty')]:
        p=d[key];party=a(a(root,tag),'Party');b(party,'EndpointID',p['endpoint'],schemeID=p['scheme'])
        addr=a(party,'PostalAddress')
        for field,tag in [('street','StreetName'),('city','CityName'),('postal','PostalZone')]:
            if p[field].strip():b(addr,tag,p[field])
        b(a(addr,'Country'),'IdentificationCode','LV')
        if p['vat'] and not (key=='buyer' and any(cat=='O' for cat,rate in groups)):
            pt=a(party,'PartyTaxScheme');b(pt,'CompanyID',p['vat']);b(a(pt,'TaxScheme'),'ID','VAT')
        if key=='supplier' and not p['vat'] and any(cat=='E' for cat,rate in groups):
            pt=a(party,'PartyTaxScheme');b(pt,'CompanyID',p['reg']);b(a(pt,'TaxScheme'),'ID','!=VAT')
        legal=a(party,'PartyLegalEntity');b(legal,'RegistrationName',p['name']);b(legal,'CompanyID',p['reg'])
    if d['iban']:
        payment=a(root,'PaymentMeans');b(payment,'PaymentMeansCode','30');b(payment,'PaymentID',d['number']);b(a(payment,'PayeeFinancialAccount'),'ID',d['iban'])
    tx=a(root,'TaxTotal');amt(tx,'TaxAmount',tax)
    for (cat,rate),value in groups.items():
        sub=a(tx,'TaxSubtotal');amt(sub,'TaxableAmount',value);amt(sub,'TaxAmount',money(value*rate/100));tc=a(sub,'TaxCategory');b(tc,'ID',cat)
        if cat!='O':b(tc,'Percent',rate)
        if cat in ('E','O'):b(tc,'TaxExemptionReason',d['exemption'])
        b(a(tc,'TaxScheme'),'ID','VAT')
    monetary=a(root,'LegalMonetaryTotal');amt(monetary,'LineExtensionAmount',net);amt(monetary,'TaxExclusiveAmount',net);amt(monetary,'TaxInclusiveAmount',total);amt(monetary,'PayableAmount',total)
    for i,l in enumerate(items,1):
        line=a(root,'InvoiceLine');b(line,'ID',i);b(line,'InvoicedQuantity',l['qty_d'],unitCode=l['unit']);amt(line,'LineExtensionAmount',l['net'])
        item=a(line,'Item');b(item,'Name',l['name']);tc=a(item,'ClassifiedTaxCategory');b(tc,'ID',l['category'])
        if l['category']!='O':b(tc,'Percent',l['rate_d'])
        b(a(tc,'TaxScheme'),'ID','VAT');b(a(line,'Price'),'PriceAmount',l['price_d'],currencyID='EUR')
    return E.tostring(root,encoding='UTF-8',xml_declaration=True,pretty_print=True)

class Validator:
    def __init__(self):
        p=Path(__file__).parent/'vendor'
        self.schema=E.XMLSchema(E.parse(str(p/'xsd/maindoc/UBL-Invoice-2.1.xsd')))
        self.proc=PySaxonProcessor(license=False)
        xslt=self.proc.new_xslt30_processor()
        self.rules=[xslt.compile_stylesheet(stylesheet_file=str(p/(x+'.xslt'))) for x in ('cen','peppol')]
        self.lock=Lock()
    def validate(self,xml):
        with self.lock:
            root=E.fromstring(xml)
            if not self.schema.validate(root):return [f'UBL struktūra: {e.message}' for e in self.schema.error_log],[]
            errors=[];warnings=[]
            node=self.proc.parse_xml(xml_text=xml.decode())
            for rule in self.rules:
                report=E.fromstring(rule.transform_to_string(xdm_node=node).encode())
                for failure in report.findall('.//{http://purl.oclc.org/dsdl/svrl}failed-assert'):
                    message=f"{failure.get('id')}: {''.join(failure.itertext()).strip()}"
                    (warnings if failure.get('flag')=='warning' else errors).append(message)
            return errors,warnings


def make_draft(inv):
    root=E.Element('InvoiceDraft',nsmap={None:'urn:invoice-converter:draft'},status='unvalidated')
    def append(parent, values):
        for key,value in values.items():
            node=E.SubElement(parent,key)
            if isinstance(value,dict):append(node,value)
            elif isinstance(value,list):
                for entry in value:
                    child=E.SubElement(node,'item')
                    if isinstance(entry,dict):append(child,entry)
                    else:child.text=str(entry)
            else:node.text=str(value).lower() if isinstance(value,bool) else str(value)
    append(root,inv.model_dump())
    return E.tostring(root,encoding='UTF-8',xml_declaration=True,pretty_print=True)
