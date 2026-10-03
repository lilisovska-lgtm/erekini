import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
message='Nav norādīta precīza nodokļa kategorija (Z/E/O) pat ja PVN ir 0%, izmantota atbrīvojuma pēdējā frāze.'
with sync_playwright() as p:
    b=p.chromium.launch()
    for other in ([],['Rēķinā ir avansa maksājums.']):
        page=b.new_page()
        page.goto('http://127.0.0.1:8010/')
        data=json.loads((root/'demo.json').read_text())
        data['supplier']['vat']=''
        data['source_total']='125.00'
        data['unsupported_features']=[message]+other
        page.route('**/api/extract',lambda route:route.fulfill(json={'draft':data,'text':'','notes':[]}))
        page.locator('#mode').select_option('local')
        page.locator('#file').set_input_files({'name':'test.txt','mimeType':'text/plain','buffer':b'test'})
        expect(page.locator('#blockers')).to_contain_text(message)
        page.locator('#non-vat').click()
        if other:
            expect(page.locator('#blockers')).to_contain_text(other[0])
            expect(page.locator('#export')).to_be_disabled()
        else:
            expect(page.locator('#blockers')).to_be_hidden()
            expect(page.locator('#export')).to_be_enabled()
            page.locator('#confirmed').check()
            with page.expect_download():page.locator('#export').click()
        page.close()
    b.close()
    print('Resolved VAT uncertainty exports; unrelated advance blocker retained.')
