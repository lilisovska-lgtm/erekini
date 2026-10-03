from pathlib import Path
import json,secrets
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1280,'height':900})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1/rekini/')
 expect(page.locator('#ai-status')).to_contain_text('atslēga vēl nav')
 expect(page.locator('#access-password')).to_be_disabled()
 page.locator('#file').set_input_files(ROOT/'demo.txt')
 expect(page.locator('#errors')).to_be_visible()
 assert page.locator('[name="number"]').input_value()==''
 # Simulate a configured server and provider answer without a paid network request.
 page.route('**/api/config',lambda route:route.fulfill(json={'configured':True,'protected':True,'provider':'OpenAI','model':'test-model'}))
 page.reload();expect(page.locator('#access-password')).to_be_enabled()
 page.locator('#access-password').fill(secrets.token_urlsafe(30))
 d=json.loads((ROOT/'demo.json').read_text());d['unsupported_features']=['Avanss nav atbalstīts'];d['confirmed']=False
 captured=[]
 def upload(route):
  captured.append(route.request)
  route.fulfill(json={'draft':d,'notes':['MI parauga atbilde'],'text':'Rēķina paraugs'})
 page.route('**/api/extract',upload)
 page.locator('#file').set_input_files(ROOT/'demo.txt')
 expect(page.locator('#blockers')).to_contain_text('Avanss')
 expect(page.locator('#export')).to_be_disabled()
 assert len(captured)==1 and captured[0].headers.get('x-invoice-password')
 page.on('dialog',lambda dialog:dialog.accept())
 page.locator('#reset').click()
 expect(page.locator('#access-password')).to_have_value('')
 expect(page.locator('#blockers')).to_be_hidden()
 expect(page.locator('#export')).to_be_enabled()
 page.screenshot(path='/tmp/invoice-ai-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
 assert not errors,errors
 b.close();print('AI UI: missing key, protected upload, unsupported blocking, reset, mobile passed.')
