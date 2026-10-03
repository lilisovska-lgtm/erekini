from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1280,'height':900});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8010/')
 page.locator('#demo').click();expect(page.locator('[name="number"]')).to_have_value('DEMO-2026-001')
 page.locator('[name="reference"]').fill('')
 page.locator('[name="due"]').fill('')
 page.locator('[name="supplier.scheme"]').select_option('')
 page.locator('[name="supplier.endpoint"]').fill('')
 page.locator('#lines select[data-field="unit"]').first.select_option('')
 # Remove original text so explicit preferences are used for missing fields.
 page.evaluate("document.querySelector('#source').textContent=''")
 page.locator('#default-days').fill('14');page.locator('#default-buyer').fill('40000000002');page.locator('#default-reference').fill('ORDER-42');page.locator('#default-unit').select_option('HUR')
 page.locator('#complete-fields').click()
 expect(page.locator('[name="due"]')).to_have_value('2026-10-03')
 expect(page.locator('[name="reference"]')).to_have_value('ORDER-42')
 expect(page.locator('[name="supplier.scheme"]')).to_have_value('0218')
 expect(page.locator('[name="supplier.endpoint"]')).to_have_value('40000000001')
 expect(page.locator('#lines select[data-field="unit"]').first).to_have_value('HUR')
 expect(page.locator('#completion-report')).to_contain_text('Lietotāja noklusējums')
 page.locator('#confirmed').check()
 with page.expect_download():page.locator('#export').click()
 page.locator('#save-defaults').click();page.reload()
 expect(page.locator('#default-reference')).to_have_value('ORDER-42')
 page.locator('#mode').select_option('local')
 d=json.loads((ROOT/'demo.json').read_text());d['due']='';d['reference']=''
 for who in ['supplier','buyer']:d[who]['scheme']=d[who]['endpoint']=''
 for l in d['lines']:l['unit']=''
 page.route('**/api/extract',lambda route:route.fulfill(json={'draft':d,'text':'Rēķina paraugs','notes':[]}))
 page.locator('#file').set_input_files(ROOT/'demo.txt')
 expect(page.locator('[name="reference"]')).to_have_value('ORDER-42')
 expect(page.locator('[name="buyer.endpoint"]')).to_have_value('40000000002')
 page.locator('#clear-defaults').click();page.reload();expect(page.locator('#default-days')).to_have_value('')
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 b.close();print('Completion UI: manual+automatic fill, provenance, valid XML, saved defaults, clearing, mobile passed.')
