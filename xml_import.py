"""Local UBL import; reject DTDs and block features the editor cannot preserve."""
from lxml import etree as E
from extract import blank
NS={'i':'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2','cac':'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2','cbc':'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'}
def import_xml(data):
    try:root=E.fromstring(data,E.XMLParser(resolve_entities=False,no_network=True))
    except E.XMLSyntaxError:raise ValueError('XML fails nav derīgs.')
    if root.getroottree().docinfo.doctype:raise ValueError('XML DTD deklarācijas nav atļautas.')
    if root.tag!='{'+NS['i']+'}Invoice':raise ValueError('Atbalstīts UBL Invoice XML.')
    def get(path,node=root):
        el=node.find(path,NS)
        return (el.text or '').strip() if el is not None else ''
    d=blank();block=[];notes=['UBL XML nolasīts lokāli bez MI. Pārskatiet datus pirms eksporta.']
    for key,tag in [('number','ID'),('issue','IssueDate'),('due','DueDate'),('tax_date','TaxPointDate'),('reference','BuyerReference'),('currency','DocumentCurrencyCode'),('invoice_type','InvoiceTypeCode'),('note','Note')]:d[key]=get('cbc:'+tag)
    d['order_reference']=get('cac:OrderReference/cbc:ID')
    d['contract_reference']=get('cac:ContractDocumentReference/cbc:ID')
    d['iban']=get('cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID')
    d['source_total']=get('cac:LegalMonetaryTotal/cbc:PayableAmount')
    d['exemption']=get('cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReason')
    for who,tag in [('supplier','AccountingSupplierParty'),('buyer','AccountingCustomerParty')]:
        party=root.find('cac:'+tag+'/cac:Party',NS)
        if party is None:raise ValueError('XML trūkst pārdevēja vai pircēja.')
        p=d[who]
        p['name']=get('cac:PartyLegalEntity/cbc:RegistrationName',party) or get('cac:PartyName/cbc:Name',party)
        reg=get('cac:PartyLegalEntity/cbc:CompanyID',party) or get('cac:PartyIdentification/cbc:ID',party)
        p['reg']=reg[2:] if reg.startswith('LV') and len(reg)==13 else reg
        for tax in party.findall('cac:PartyTaxScheme',NS):
            if get('cac:TaxScheme/cbc:ID',tax)=='VAT':p['vat']=get('cbc:CompanyID',tax)
        for key,tag in [('street','StreetName'),('city','CityName'),('postal','PostalZone')]:p[key]=get('cac:PostalAddress/cbc:'+tag,party)
        p['street']=p['street'] or get('cac:PostalAddress/cac:AddressLine/cbc:Line',party)
        p['country']=get('cac:PostalAddress/cac:Country/cbc:IdentificationCode',party)
        p['endpoint']=get('cbc:EndpointID',party)
        endpoint=party.find('cbc:EndpointID',NS);p['scheme']=endpoint.get('schemeID','') if endpoint is not None else ''
        if p['scheme']=='9939' and p['endpoint']==p['reg'] and p['vat']=='LV'+p['reg']:
            p['endpoint']=p['vat'];notes.append('9939 elektroniskajai adresei pievienots LV prefikss no dokumentā esošā PVN numura.')
    for line in root.findall('cac:InvoiceLine',NS):
        q=line.find('cbc:InvoicedQuantity',NS)
        d['lines'].append(dict(name=get('cac:Item/cbc:Name',line),qty=get('cbc:InvoicedQuantity',line),unit=q.get('unitCode','') if q is not None else '',price=get('cac:Price/cbc:PriceAmount',line),category=get('cac:Item/cac:ClassifiedTaxCategory/cbc:ID',line),rate=get('cac:Item/cac:ClassifiedTaxCategory/cbc:Percent',line) or ('0' if get('cac:Item/cac:ClassifiedTaxCategory/cbc:ID',line)=='O' else '')))
        base=get('cac:Price/cbc:BaseQuantity',line)
        if base and base not in ('1','1.0','1.00'):block.append('Cenas bāzes daudzums nav 1.')
    if d['invoice_type'] not in ('380','80'):block.append('Neatbalstīts rēķina tipa kods.')
    for tag in ('AllowanceCharge','PrepaidPayment','BillingReference'):
        if root.findall('.//cac:'+tag,NS):block.append('Neatbalstīta XML sadaļa: '+tag)
    for tag in ('PrepaidAmount','PayableRoundingAmount'):
        value=get('cac:LegalMonetaryTotal/cbc:'+tag)
        if value and value not in ('0','0.0','0.00'):block.append('Neatbalstīta summa: '+tag)
    if len(root.findall('cac:TaxTotal/cac:TaxSubtotal',NS))>1:block.append('XML imports ar vairākām nodokļu grupām jāpārskata ārpus šī importa.')
    notes.append('Imports pārnes redaktorā atbalstītos laukus; papildu rekvizīti, piemēram, BIC un maksātāja konts, netiek pārnesti.')
    d['unsupported_features']=block
    return d,notes
