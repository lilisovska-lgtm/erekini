import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from lxml import etree
from app import app
from extract import extract,parse
from invoice import Invoice,check,make_xml,Validator

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def demo():
    data=json.loads((ROOT/'demo.json').read_text());data['confirmed']=True;return data
@pytest.fixture(scope='module')
def validator():return Validator()

def test_demo_official_validation(demo,validator):
    result=check(Invoice(**demo));assert result[-1]==[]
    xml=make_xml(*result[:-1]);assert validator.validate(xml)==([],[])
    root=etree.fromstring(xml)
    assert root.find('.//{*}PayableAmount').text=='151.25'

def test_mismatch_and_review_block(demo):
    demo['source_total']='151.24';demo['confirmed']=False
    errors=check(Invoice(**demo))[-1]
    assert any('nesakrīt' in e for e in errors)
    assert any('Apstipriniet' in e for e in errors)

@pytest.mark.parametrize('value',['NaN','Infinity','-1','1e100','0.1234567'])
def test_invalid_numeric(demo,value):
    demo['lines'][0]['qty']=value
    assert check(Invoice(**demo))[-1]

def test_decimal_rounding_and_mixed_rates(demo,validator):
    demo['lines']=[dict(name='A',qty='3',unit='C62',price='0.335',rate='21',category='S'),dict(name='B',qty='1',unit='C62',price='10',rate='12',category='S')]
    demo['source_total']='12.42'
    r=check(Invoice(**demo));assert not r[-1];assert validator.validate(make_xml(*r[:-1]))==([],[])

@pytest.mark.parametrize('category',['Z','E','O'])
def test_zero_tax_categories(demo,validator,category):
    for l in demo['lines']:l.update(category=category,rate='0')
    demo['source_total']='125.00';demo['exemption']='Piemēra pamatojums'
    if category=='O':demo['supplier']['vat']=demo['buyer']['vat']=''
    r=check(Invoice(**demo));assert not r[-1];assert validator.validate(make_xml(*r[:-1]))==([],[])

def test_xml_escaping(demo,validator):
    demo['supplier']['name']='A & B <Piemērs>'
    r=check(Invoice(**demo));xml=make_xml(*r[:-1]);assert b'&amp;' in xml;assert not validator.validate(xml)[0]

def test_official_validation_catches_missing_endpoint(demo,validator):
    r=check(Invoice(**demo));root=etree.fromstring(make_xml(*r[:-1]));endpoint=root.find('.//{*}EndpointID');endpoint.getparent().remove(endpoint)
    assert validator.validate(etree.tostring(root))[0]

def test_parse_demo_and_no_fabrication():
    d,notes=parse((ROOT/'demo.txt').read_text());assert len(d['lines'])==2;assert d['supplier']['reg']=='40000000001'
    d,notes=parse('This is a document with no invoice data.');assert d['number']=='' and d['source_total']=='' and not d['lines']

def test_pdf_text():
    out=io.BytesIO();c=Canvas(out);c.drawString(50,750,'Invoice No. TEST-01');c.drawString(50,720,'Invoice date: 2026-09-19');c.drawString(50,690,'Total due: 121.00 EUR');c.save()
    text,notes=extract(out.getvalue(),'test.pdf');assert 'TEST-01' in text;assert not notes

def test_docx():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Invoice No. DOCX-01</w:t></w:r></w:p></w:body></w:document>')
    text,_=extract(out.getvalue(),'x.docx');assert 'DOCX-01' in text

def test_image_ocr():
    from PIL import Image,ImageDraw,ImageFont
    im=Image.new('RGB',(1500,350),'white');draw=ImageDraw.Draw(im);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',44)
    draw.text((40,50),'Invoice No. OCR-2026-001',font=font,fill='black');draw.text((40,130),'Total due: 121.00 EUR',font=font,fill='black')
    out=io.BytesIO();im.save(out,format='PNG');text,notes=extract(out.getvalue(),'x.png');assert 'OCR-2026-001' in text;assert notes

def test_routes_and_upload(demo):
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/health').json()['processing']=='local+optional-openai'
        r=client.post('/api/extract',files={'file':('demo.txt',(ROOT/'demo.txt').read_bytes(),'text/plain')});assert r.status_code==200;assert len(r.json()['draft']['lines'])==2
        r=client.post('/api/export',json=demo);assert r.status_code==200;assert 'xml' in r.json()
        demo['source_total']='0';assert client.post('/api/export',json=demo).status_code==422
        assert client.post('/api/extract',files={'file':('x.exe',b'abc')}).status_code==422
        assert client.post('/api/extract',files={'file':('x.pdf',b'bad')}).status_code==422
        assert client.post('/api/export',json={},headers={'Origin':'https://attacker.example'}).status_code==403

def test_scanned_pdf_and_page_limit():
    from PIL import Image,ImageDraw,ImageFont
    from reportlab.lib.utils import ImageReader
    im=Image.new('RGB',(1200,250),'white');draw=ImageDraw.Draw(im)
    draw.text((30,50),'Invoice SCAN-001 total 121.00',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',40),fill='black')
    out=io.BytesIO();c=Canvas(out);c.drawImage(ImageReader(im),30,500,width=540,height=112);c.save()
    text,notes=extract(out.getvalue(),'scan.pdf');assert 'SCAN-001' in text;assert notes
    out=io.BytesIO();c=Canvas(out)
    for i in range(11):c.drawString(30,750,'Page');c.showPage()
    c.save()
    with pytest.raises(ValueError,match='1–10'):extract(out.getvalue(),'many.pdf')

def test_optional_address_components_omitted(demo,validator):
    for who in ('supplier','buyer'):
        for field in ('street','city','postal'):demo[who][field]=''
    result=check(Invoice(**demo))
    assert not result[-1]
    xml=make_xml(*result[:-1])
    assert validator.validate(xml)==([],[])
    assert etree.fromstring(xml).find('.//{*}StreetName') is None

def test_incomplete_draft_preserves_blanks():
    with TestClient(app) as client:
        response=client.post('/api/draft',json={'number':'A & B','reference':'','lines':[{'unit':''}]})
        assert response.status_code==200
        root=etree.fromstring(response.json()['xml'].encode())
        assert root.tag=='{urn:invoice-converter:draft}InvoiceDraft'
        assert root.find('{*}number').text=='A & B'
        assert root.find('{*}reference').text is None
        assert root.find('.//{*}unit').text is None
        assert client.post('/api/export',json={'number':'A & B'}).status_code==422

def test_order_reference_replaces_buyer_reference(demo,validator):
    demo['reference']=''
    demo['order_reference']='ORDER-123'
    result=check(Invoice(**demo))
    assert not result[-1]
    xml=make_xml(*result[:-1])
    assert validator.validate(xml)==([],[])
    root=etree.fromstring(xml)
    assert root.find('{*}BuyerReference') is None
    assert root.find('{*}OrderReference/{*}ID').text=='ORDER-123'
    demo['order_reference']=''
    assert any('pasūtījuma numuru' in e for e in check(Invoice(**demo))[-1])

def test_iban_error_does_not_guess_account(demo):
    demo['iban']='LV00HABA0551045678910'
    result=check(Invoice(**demo))
    assert result[0]['iban']==demo['iban']
    assert any('kontrolsumma' in e and 'oriģinālo' in e for e in result[-1])

def test_iban_spaces_and_case(demo):
    demo['iban']='lv80 bank 0000 4351 9500 1'
    result=check(Invoice(**demo))
    assert result[0]['iban']=='LV80BANK0000435195001'
    assert not any('IBAN' in e for e in result[-1])

def test_non_vat_seller_with_vat_registered_buyer(demo,validator):
    demo['supplier']['vat']=''
    demo['exemption']='Pārdevējs nav PVN maksātājs.'
    for line in demo['lines']:line['category']='O';line['rate']='0'
    demo['source_total']='125.00'
    result=check(Invoice(**demo))
    assert not result[-1]
    xml=make_xml(*result[:-1])
    assert validator.validate(xml)==([],[])
    root=etree.fromstring(xml)
    assert root.find('.//{*}PartyTaxScheme') is None
    assert demo['buyer']['vat']

def test_exempt_non_vat_seller_matches_sample(demo,validator):
    demo['supplier']['vat']=''
    demo['exemption']='Pārdevējs nav reģistrēts PVN maksātājs.'
    for line in demo['lines']:line['category']='E';line['rate']='0'
    demo['source_total']='125.00'
    result=check(Invoice(**demo))
    assert not result[-1]
    xml=make_xml(*result[:-1])
    assert validator.validate(xml)==([],[])
    root=etree.fromstring(xml)
    supplier=root.find('{*}AccountingSupplierParty/{*}Party/{*}PartyTaxScheme')
    assert supplier.find('{*}CompanyID').text==demo['supplier']['reg']
    assert supplier.find('{*}TaxScheme/{*}ID').text=='!=VAT'
    assert root.find('{*}AccountingCustomerParty/{*}Party/{*}PartyTaxScheme/{*}CompanyID').text==demo['buyer']['vat']
