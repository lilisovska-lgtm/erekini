import json
from pathlib import Path
import pytest
from invoice import Invoice,check,make_xml,Validator
from xml_import import import_xml
@pytest.mark.parametrize('nonvat',[False,True])
def test_local_roundtrip(nonvat):
 d=json.loads((Path(__file__).resolve().parents[1]/'demo.json').read_text());d['confirmed']=True
 if nonvat:
  d.update(invoice_type='80',note='Projekta piezīme',contract_reference='Līgums 171',exemption='Uzņēmums nav PVN maksātājs.',source_total='125.00')
  d['supplier']['vat']=''
  for l in d['lines']:l.update(category='E',rate='0')
 r=check(Invoice(**d));assert not r[-1]
 imported,notes=import_xml(make_xml(*r[:-1]));imported['confirmed']=True
 r2=check(Invoice(**imported));assert not r2[-1]
 assert Validator().validate(make_xml(*r2[:-1]))==([],[])
 if nonvat:
  assert imported['invoice_type']=='80'
  assert imported['note']==d['note']
  assert imported['contract_reference']==d['contract_reference']
  assert not imported['supplier']['vat']
  assert imported['buyer']['vat']==d['buyer']['vat']
def test_no_external_entities():
 with pytest.raises(ValueError):
  import_xml(b'<!DOCTYPE Invoice [<!ENTITY x SYSTEM "file:///etc/passwd">]><Invoice/>')
