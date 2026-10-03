import json
import secrets
from copy import deepcopy
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
import ai
import app as server
from invoice import Invoice, check, make_xml, Validator

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def recognized():
    d=json.loads((ROOT/'demo.json').read_text());d.pop('confirmed')
    return {'is_invoice':True,'draft':d,'warnings':['Pārbaudiet rekvizītus.'],'unsupported_features':[]}

@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sk-'+secrets.token_urlsafe(30))
    password=secrets.token_urlsafe(30)
    monkeypatch.setenv('INVOICE_ACCESS_PASSWORD',password)
    server.ai_attempts.clear();server.auth_attempts.clear()
    return password

def stub(monkeypatch,body,status=200):
    calls=[]
    class Client:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            calls.append((url,kwargs['json']))
            return httpx.Response(status,json=body)
    monkeypatch.setattr(ai.httpx,'Client',Client)
    return calls

def response(result):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}

def test_request_contract_and_result(monkeypatch,credentials,recognized):
    calls=stub(monkeypatch,response(recognized))
    draft,notes=ai.recognize(b'%PDF-test','private-name.pdf','Invoice sample')
    assert not draft['confirmed'];assert len(draft['lines'])==2
    url,body=calls[0];assert url=='https://api.openai.com/v1/responses';assert body['store'] is False
    assert body['text']['format']['strict'] is True
    assert body['input'][0]['content'][1]['filename']=='invoice.pdf'
    assert body['input'][0]['content'][1]['file_data'].startswith('data:application/pdf;base64,')
    assert 'private-name' not in json.dumps(body)
    draft['confirmed']=True;r=check(Invoice(**draft));assert not r[-1];assert Validator().validate(make_xml(*r[:-1]))==([],[])

@pytest.mark.parametrize('code',[401,403,429,500])
def test_provider_errors_redacted(monkeypatch,credentials,code):
    secret=secrets.token_urlsafe(32);stub(monkeypatch,{'error':secret},code)
    with pytest.raises(ai.AIError) as e:ai.recognize(b'a','x.txt','test')
    assert secret not in str(e.value)

@pytest.mark.parametrize('mutation',['incomplete','refusal','invalid','missing','foreign','unsupported'])
def test_response_edge_cases(monkeypatch,credentials,recognized,mutation):
    result=deepcopy(recognized);body=response(result)
    if mutation=='incomplete':body['status']='incomplete'
    if mutation=='refusal':body['output'][0]['content']=[{'type':'refusal','refusal':'no'}]
    if mutation=='invalid':body['output'][0]['content'][0]['text']='not json'
    if mutation=='missing':del result['draft']['source_total'];body=response(result)
    if mutation=='foreign':result['draft']['supplier']['country']='DE';body=response(result)
    if mutation=='unsupported':result['unsupported_features']=['Avansa rēķins'];body=response(result)
    stub(monkeypatch,body)
    if mutation in ('foreign','unsupported'):
        d,_=ai.recognize(b'a','x.txt','t');d['confirmed']=True;assert check(Invoice(**d))[-1]
    else:
        with pytest.raises(ai.AIError):ai.recognize(b'a','x.txt','t')

def test_raw_images_but_docx_text_only():
    content=ai.request_body(b'image','x.png','OCR')['input'][0]['content'];assert content[1]['type']=='input_image'
    content=ai.request_body(b'private-docx','x.docx','EXTRACTED')['input'][0]['content'];assert len(content)==1;assert 'EXTRACTED' in content[0]['text']

def test_missing_key_no_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    def no_call(*a,**kw):raise AssertionError('Unexpected external call')
    monkeypatch.setattr(ai.httpx,'Client',no_call)
    with pytest.raises(ai.AIError,match='atslēga'):ai.recognize(b'a','x.txt','t')

def test_mode_authorization_and_rate_limit(monkeypatch,credentials,recognized):
    calls=[]
    def mocked(*args):
        calls.append(True)
        return {**deepcopy(recognized['draft']),'confirmed':False,'unsupported_features':[]},[]
    monkeypatch.setattr(server,'recognize',mocked)
    def post(c,**kw):return c.post('/api/extract',data={'mode':'ai'},files={'file':('x.txt',b'Invoice example')},**kw)
    with TestClient(server.app,base_url='https://testserver') as c:
        assert post(c).status_code==401
        assert not calls
        assert post(c,headers={'X-Invoice-Password':credentials}).status_code==200
        assert len(calls)==1
        server.ai_attempts.extend([server.time.monotonic()]*20)
        assert post(c,headers={'X-Invoice-Password':credentials}).status_code==429
        server.ai_attempts.clear()
        cfg=c.get('/api/config').json();assert cfg['configured'];assert credentials not in json.dumps(cfg)
        # The local route never invokes external recognition.
        c.post('/api/extract',files={'file':('x.txt',b'Invoice example')});assert len(calls)==1
    with TestClient(server.app,base_url='http://public.example') as c:
        assert post(c,headers={'X-Invoice-Password':credentials}).status_code==403

def test_official_invoice_sample_and_export_alignment():
    from lxml import etree
    v=Validator();sample=(ROOT/'examples/einvoice_shema_nePVN2.xml').read_bytes()
    assert v.validate(sample)==([],[])
    data=json.loads((ROOT/'demo.json').read_text());data['confirmed']=True
    exported=etree.fromstring(make_xml(*check(Invoice(**data))[:-1]));official=etree.fromstring(sample)
    for field in ('CustomizationID','ProfileID','DocumentCurrencyCode'):
        assert exported.find('{*}'+field).text==official.find('{*}'+field).text
    assert exported.find('.//{*}EndpointID').get('schemeID')==official.find('.//{*}EndpointID').get('schemeID')
    # Do not copy the sample's advance type, prepaid amount, allowances or dummy bank details.
    assert exported.find('{*}InvoiceTypeCode').text=='380'
    assert exported.find('.//{*}PrepaidAmount') is None

def test_latvija_field_limits():
    d=json.loads((ROOT/'demo.json').read_text());d['confirmed']=True;d['number']='X'*36
    assert any('35' in x for x in check(Invoice(**d))[-1])
