from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1/rekini/')
    page.get_by_role('button',name='Izmēģini ar paraugu').click()
    page.locator('[name="number"]').wait_for()
    expect(page.locator('[name="number"]')).to_have_value("DEMO-2026-001")
    page.locator('#confirmed').check()
    with page.expect_download() as download:
        page.locator('#export').click()
    assert download.value.suggested_filename=='e-rekins.xml'
    assert '151.25' in page.locator('#status').inner_text()
    page.locator('[name="source_total"]').fill('1.00')
    assert not page.locator('#confirmed').is_checked()
    page.locator('#confirmed').check();page.locator('#export').click()
    page.locator('#errors').wait_for(state='visible')
    assert 'nesakrīt' in page.locator('#errors').inner_text()
    page.on('dialog',lambda d:d.accept())
    page.locator('#mode').select_option('local')
    page.locator('#file').set_input_files(ROOT/'demo.txt')
    expect(page.locator('[name="source_total"]')).to_have_value("151.25")
    assert page.locator('#lines .line').count()==2
    assert 'DEMO-2026-001' in page.locator('#source').text_content()
    page.screenshot(path='/tmp/invoice-desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path='/tmp/invoice-mobile.png',full_page=True)
    assert not errors,errors
    browser.close()
    print('Browser: demo export, total mismatch, review reset, TXT upload, mobile layout passed.')
