import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import app
from complete import CompletionRequest,complete
from invoice import Invoice,check,make_xml,Validator
ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def draft():
 d=json.loads((ROOT/'demo.json').read_text());d['reference']='';d['due']=''
 for key in ('supplier','buyer'):d[key]['scheme']=d[key]['endpoint']=''
 for row in d['lines']:row['unit']=''
 return d

def run(d,defaults=None,text=''):return complete(CompletionRequest(invoice=Invoice(**d),defaults=defaults or {},source_text=text))

def test_safe_defaults_and_validation(draft):
 r=run(draft,{'due_days':14,'reference':'PAS-1','buyer_reg':draft['buyer']['reg'],'unit':'C62'})
 d=r['draft'];assert d['due']=='2026-10-03';assert d['reference']=='PAS-1'
 assert d['supplier']['scheme']=='0218';assert d['buyer']['endpoint']==draft['buyer']['reg']
 assert not r['missing'];assert len(r['changes'])==8
 d['confirmed']=True;checked=check(Invoice(**d));assert not checked[-1];assert Validator().validate(make_xml(*checked[:-1]))==([],[])

def test_no_arbitrary_contract_data(draft):
 r=run(draft);assert r['draft']['due']==r['draft']['reference']==r['draft']['lines'][0]['unit']==''
 assert r['missing'];assert not r['draft']['confirmed']

def test_never_overwrite(draft):
 draft['due']='2026-10-15';draft['reference']='EXISTING';draft['buyer'].update(scheme='9939',endpoint='LV40000000002');draft['lines'][0]['unit']='HUR'
 r=run(draft,{'due_days':7,'reference':'OVERRIDE','buyer_reg':draft['buyer']['reg'],'unit':'C62'})['draft']
 assert r['due']=='2026-10-15';assert r['reference']=='EXISTING';assert r['buyer']['scheme']=='9939';assert r['lines'][0]['unit']=='HUR'

def test_reference_client_scope(draft):
 r=run(draft,{'reference':'OTHER','buyer_reg':'40000000009'});assert r['draft']['reference']=='';assert r['notes']

def test_explicit_terms_and_source_priority(draft):
 r=run(draft,{'due_days':7,'reference':'DEFAULT','buyer_reg':draft['buyer']['reg']},'Apmaksa 30 dienu laikā no rēķina datuma\nPircēja atsauce: SOURCE')
 assert r['draft']['due']=='2026-10-19';assert r['draft']['reference']=='SOURCE'

@pytest.mark.parametrize('text',['Apmaksa 10 darba dienu laikā no rēķina datuma','Apmaksa 14 dienu laikā no piegādes'])
def test_ambiguous_terms_no_fallback(draft,text):
 assert run(draft,{'due_days':7},text)['draft']['due']==''

def test_units_matching_and_normalization(draft):
 draft['lines'][0]['unit']='st.'
 text='Dokumentu sagatavošana ; 1 ; gab. ; 25.00 ; 21'
 r=run(draft,text=text)['draft'];assert r['lines'][0]['unit']=='HUR';assert r['lines'][1]['unit']=='C62'
 draft['lines'][0]['unit']='unknown';assert run(draft,{'unit':'C62'})['draft']['lines'][0]['unit']=='unknown'

def test_foreign_unknown_and_opt_out(draft):
 draft['buyer']['country']='DE';assert run(draft)['draft']['buyer']['endpoint']==''
 assert run(draft,{'auto_endpoint':False})['draft']['supplier']['scheme']==''
 draft['supplier']['endpoint']='different';assert run(draft)['draft']['supplier']['scheme']==''

def test_invalid_issue_and_zero_days(draft):
 assert run(draft,{'due_days':0})['draft']['due']==draft['issue']
 draft['issue']='';assert run(draft,{'due_days':14})['draft']['due']==''

def test_route_and_invalid_options(draft):
 with TestClient(app) as c:
  r=c.post('/api/complete',json={'invoice':draft,'defaults':{'due_days':14}});assert r.status_code==200;assert r.json()['draft']['due']=='2026-10-03'
  assert c.post('/api/complete',json={'invoice':draft,'defaults':{'due_days':-1}}).status_code==422

def test_unknown_printed_unit_not_replaced_by_default(draft):
 r=run(draft,{'unit':'C62'},'Dokumentu sagatavošana ; 1 ; tonna ; 25.00 ; 21')
 assert r['draft']['lines'][1]['unit']=='';assert r['notes']

def test_non_vat_explicit_statement(draft):
 draft['supplier']['vat']=''
 for row in draft['lines']:row['category']='Z';row['rate']='0'
 r=run(draft,text='Saskaņā ar PVN likumu uzņēmums nav PVN maksātājs.')
 assert all(l['category']=='E' for l in r['draft']['lines'])
 assert r['draft']['exemption']
 assert r['draft']['buyer']['vat']==draft['buyer']['vat']

@pytest.mark.parametrize('text',['','Pircējs nav PVN maksātājs.','Pircēja uzņēmums nav PVN maksātājs.'])
def test_no_non_vat_inference_from_absence_or_buyer(draft,text):
 draft['supplier']['vat']=''
 for row in draft['lines']:row['category']='Z';row['rate']='0'
 assert run(draft,text=text)['draft']['lines'][0]['category']=='Z'

def test_non_vat_conflicting_rate_unchanged(draft):
 draft['supplier']['vat']=''
 assert run(draft,text='Pārdevējs nav PVN maksātājs.')['draft']['lines'][0]['category']=='S'
