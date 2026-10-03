from extract import parse
from complete import CompletionRequest,complete

def test_portal_columns_and_wrapped_nonvat():
 text="""Rēķins Nr. TEST-1
30.09.2025.       Samaksāt līdz: 30.09.2025.
Piegādātājs: Testa pārdevējs       Reģistrācijas nr./Personas kods: 40000000001
Juridiskā adrese: Testa iela 1       Bankas konts: LV80BANK0000435195001
Pasūtītājs: Testa pircējs       Reģistrācijas nr./Personas kods: 40000000002
PVN Nr.: LV40000000002
Papildu informācija
Pircēja atsauce: TEST       Līguma Nr.: L-1
Nodokļa atbrīvojuma pamatojums: uzņēmums nav PVN
maksātājs
Vienības cena
1. Pakalpojums       1,00 gab.       600,00       1,00       0       600.00
Summa apmaksai (EUR)       600.00
Latvija.gov.lv e-rēķinu risinājumā"""
 d,_=parse(text)
 r=complete(CompletionRequest(invoice=d,source_text=text))['draft']
 assert r['supplier']['reg']=='40000000001'
 assert r['buyer']['reg']=='40000000002'
 assert r['lines'][0]['category']=='E'
 assert r['lines'][0]['unit']=='C62'
 assert r['reference']=='TEST'
 assert r['contract_reference']=='L-1'
 assert r['source_total']=='600.00'

def test_rental_missing_unit_stays_blank():
 text="""Rēķins Nr. TEST 2
2026.gada 22. septembris
Piegādātājs: Testa pārdevējs
Reģ. Nr.: 40000000001
PVN Reģ. Nr.: LV40000000001
Saņēmējs: Testa pircējs
Reģ. Nr.: 40000000002
Adrese:
Rēķins jāapmaksā līdz: 07.10.2026
Pakalpojums       Daudzums       Mērv.       Cena       Summa, EUR
1 Pakalpojums       1       150.0000       150.00
PVN 21% (no summas 150.00) : 31.50
Kopā ar PVN: 181.50
Kopā apmaksai, EUR: 181.50"""
 d,_=parse(text)
 assert d['number']=='TEST 2'
 assert d['issue']=='2026-09-22'
 assert d['due']=='2026-10-07'
 assert d['lines'][0]['unit']==''
 assert d['lines'][0]['rate']=='21'
 assert not d['reference']
