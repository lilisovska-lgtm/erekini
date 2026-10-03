from playwright.sync_api import sync_playwright,expect
with sync_playwright() as p:
    b=p.chromium.launch()
    page=b.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8010/')
    page.locator('#demo').click()
    expect(page.locator('[name="number"]')).to_have_value('DEMO-2026-001')
    page.locator('[name="buyer.endpoint"]').fill('')
    page.locator('#confirmed').check()
    page.locator('#export').click()
    expect(page.locator('[name="buyer.endpoint"]')).to_have_value('40000000002')
    expect(page.locator('#confirmed')).not_to_be_checked()
    page.locator('#confirmed').check()
    with page.expect_download():page.locator('#export').click()
    page.evaluate("document.querySelector('#source').textContent=''")
    page.locator('[name="reference"]').fill('')
    with page.expect_download() as download:page.locator('#draft-export').click()
    assert download.value.suggested_filename=='rekina-melnraksts.xml'
    expect(page.locator('[name="reference"]')).to_have_value('')
    expect(page.locator('#notes')).to_contain_text('nav UBL')
    assert not errors,errors
    b.close()
    print('Export auto-completion, review, valid export and incomplete draft passed.')
