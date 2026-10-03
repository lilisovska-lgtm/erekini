"""Local, bounded document extraction. Never calls remote services."""
import re
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from datetime import datetime
from lxml import etree
from PIL import Image

MAX_TEXT = 150_000
Image.MAX_IMAGE_PIXELS = 20_000_000


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=35, check=True)
        return result.stdout.decode('utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise ValueError('Dokumenta nolasīšana aizņēma pārāk ilgu laiku. Sadaliet to mazākos failos.')
    except subprocess.CalledProcessError:
        raise ValueError('Dokumentu nevar nolasīt. Pārbaudiet, vai tas nav bojāts vai aizsargāts ar paroli.')


def extract(data, filename, allow_empty=False):
    suffix = Path(filename).suffix.lower()
    notes = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='invoice-') as folder:
        path = Path(folder) / ('source' + suffix)
        path.write_bytes(data)
        if suffix == '.pdf':
            if not data.startswith(b'%PDF-'):
                raise ValueError('Fails nav derīgs PDF.')
            info = run(['pdfinfo', str(path)])
            count = re.search(r'^Pages:\s+(\d+)', info, re.M)
            if not count or not 1 <= int(count[1]) <= 10:
                raise ValueError('Atļauts PDF ar 1–10 lapām. Sadaliet garāku dokumentu.')
            pages = []
            for page in range(1, int(count[1]) + 1):
                if time.monotonic() - started > 120:
                    raise ValueError("PDF apstrādes laiks pārsniegts. Sadaliet dokumentu mazākos failos.")
                text = run(['pdftotext', '-f', str(page), '-l', str(page), '-layout', str(path), '-'])
                if len(re.sub(r'\s', '', text)) < 40:
                    prefix = str(Path(folder) / f'page-{page}')
                    run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-scale-to', '2200', '-png', str(path), prefix])
                    text = run(['tesseract', prefix+'.png', 'stdout', '-l', 'lav+eng', '--psm', '3'])
                    notes.append(f'{page}. lapai izmantota OCR. Īpaši pārbaudiet ciparus un tabulu.')
                pages.append(text)
            text = '\n'.join(pages)
        elif suffix in ('.png', '.jpg', '.jpeg'):
            try:
                with Image.open(path) as im:
                    if im.width * im.height > 20_000_000:
                        raise ValueError('Attēls ir pārāk liels (maksimums 20 megapikseļi).')
                    im.convert('RGB').save(Path(folder) / 'image.png')
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ValueError('Attēls ir pārāk liels.')
            except (OSError, SyntaxError):
                raise ValueError('Attēls ir bojāts vai neatbalstīts.')
            text = run(['tesseract', str(Path(folder) / 'image.png'), 'stdout', '-l', 'lav+eng', '--psm', '3'])
            notes.append('Izmantota OCR. Pārbaudiet visus ciparus un tabulas kolonnas.')
        elif suffix == '.docx':
            try:
                with zipfile.ZipFile(path) as z:
                    if sum(x.file_size for x in z.infolist()) > 20_000_000:
                        raise ValueError('Atpakots dokuments pārsniedz izmēra ierobežojumu.')
                    root = etree.fromstring(z.read('word/document.xml'), etree.XMLParser(resolve_entities=False, no_network=True))
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    parts = []
                    for block in root.xpath('//w:body/*', namespaces=ns):
                        if block.tag.endswith('}tbl'):
                            for row in block.xpath('./w:tr', namespaces=ns):
                                parts.append(' ; '.join(' '.join(cell.xpath('.//w:t/text()', namespaces=ns)) for cell in row.xpath('./w:tc', namespaces=ns)))
                        else:
                            parts.append(' '.join(block.xpath('.//w:t/text()', namespaces=ns)))
                    text = '\n'.join(parts)
            except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, RuntimeError):
                raise ValueError('Neizdevās nolasīt DOCX. Vecais DOC formāts netiek atbalstīts.')
        elif suffix == '.txt':
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise ValueError('TXT failam jābūt UTF-8 kodējumā.')
        else:
            raise ValueError('Atbalstīti PDF, PNG, JPG, DOCX un UTF-8 TXT faili.')
    if len(text) > MAX_TEXT:
        raise ValueError('Dokumentā ir pārāk daudz teksta. Sadaliet to mazākos failos.')
    if not text.strip() and allow_empty and suffix in ('.pdf','.png','.jpg','.jpeg'):
        notes.append('Lokālā OCR tekstu nenolasīja; MI saņems oriģinālo PDF vai attēlu.')
        return '', notes
    if not text.strip():
        raise ValueError('Dokumentā neizdevās atrast tekstu. Ievadiet datus manuāli vai izmantojiet skaidrāku attēlu.')
    return text, notes


def blank():
    party = dict(name='', reg='', vat='', street='', city='', postal='', country='LV', endpoint='', scheme='0218')
    return dict(number='', issue='', due='', tax_date='', reference='', currency='EUR', iban='',
                supplier=party.copy(), buyer=party.copy(), lines=[], source_total='', exemption='', confirmed=False)


def parse(text):
    """Conservative suggestions only. Missing values stay empty; user must confirm."""
    d = blank()
    def match(pattern, src=text):
        m = re.search(pattern, src, re.I | re.M)
        return m[1].strip() if m else ''
    d['number'] = match(r'^(?:rēķins|rēķina\s+numurs|invoice)\s*(?:nr\.?|no\.?|number|#)?\s*[:\-]?\s*([\w][\w./-]{1,49})\s*$')
    for field, label in [('issue', r'(?:rēķina\s+datums|izrakstīšanas\s+datums|datums|invoice\s+date)'), ('due', r'(?:apmaksas\s+(?:termiņš|datums)|samaksāt\s+līdz|due\s+date)')]:
        value = match(r'^'+label+r'\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})')
        if value:
            try:d[field] = datetime.strptime(value, '%Y-%m-%d' if '-' in value else '%d.%m.%Y').date().isoformat()
            except ValueError:pass
    d['reference'] = match(r'^(?:pircēja\s+atsauce|buyer\s+reference)\s*:\s*(.+)$')
    d['iban'] = re.sub(r'\s+', '', match(r'(?:IBAN|konts)\s*:?\s*(LV\d{2}[A-Z]{4}[\d ]{13,30})')).upper()
    d['source_total'] = match(r'^(?:apmaksai|kopā\s+apmaksai|summa\s+apmaksai|total\s+due)\s*:?\s*([\d ,]+[.,]\d{2})').replace(' ', '').replace(',', '.')
    for key, labels, stop in [('supplier', r'piegādātājs|pārdevējs|seller|supplier', r'pircējs|saņēmējs|buyer|customer'), ('buyer', r'pircējs|saņēmējs|buyer|customer', r'piegādātājs|pārdevējs|seller|supplier')]:
        m = re.search(r'^(?:'+labels+r')\s*:\s*(.*?)(?=^(?:'+stop+r')\s*:|\Z)',text,re.I|re.M|re.S)
        if m:
            block=m[1]; lines=block.splitlines()
            d[key]['name']=lines[0].strip() if lines else ''
            d[key]['reg']=match(r'(?:reģ\.?\s*(?:nr\.?)?|registration)\s*:?\s*(\d{11})',block)
            d[key]['vat']=match(r'PVN\s*(?:nr\.?)?\s*:?\s*(LV\d{11})',block)
            d[key]['street']=match(r'^adrese\s*:\s*(.+)$',block)
            d[key]['city']=match(r'^pilsēta\s*:\s*(.+)$',block)
            d[key]['postal']=match(r'^pasta\s+indekss\s*:\s*(.+)$',block)
            d[key]['endpoint']=match(r'^(?:elektroniskā\s+adrese|endpoint)\s*:\s*(\d{11})',block)
    # Explicit delimited line layout: description ; quantity ; unit ; net price ; VAT rate.
    for line in text.splitlines():
        cols = [x.strip() for x in re.split(r';|\t|\s{2,}', line.strip())]
        if len(cols) not in (5,6):continue
        name, qty, unit, price, rate = cols[:5]
        num=lambda v: bool(re.fullmatch(r'\d+(?:[.,]\d+)?',v))
        if name and num(qty) and num(price) and num(rate.rstrip('%')):
            units={'gab':'C62','gab.':'C62','h':'HUR','st.':'HUR','kg':'KGM','C62':'C62','HUR':'HUR','KGM':'KGM','DAY':'DAY','MON':'MON'}
            d['lines'].append(dict(name=name,qty=qty.replace(',','.'),unit=units.get(unit,unit),price=price.replace(',','.'),rate=rate.rstrip('%').replace(',','.'),category='S' if float(rate.rstrip('%').replace(',','.'))>0 else ''))
    notes=['Automātiski atrastās vērtības ir tikai ieteikumi. Salīdziniet tās ar oriģinālu; neaizpildītie lauki jāievada pašam.']
    if not d['lines']:notes.append('Pozīcijas nevarēja droši atpazīt. Pievienojiet tās no oriģinālā rēķina; summas netiek izdomātas.')
    if re.search(r'atlaide|avans|priekšapmaks|credit\s*note|kredītrēķins',text,re.I):
        notes.append('Atrasta norāde uz atlaidi, avansu vai kredītrēķinu. Šī versija tos neatbalsta; šādu dokumentu neeksportējiet ar šo rīku.')
    from pdf_layouts import enrich
    notes.extend(enrich(text,d))
    return d, notes
