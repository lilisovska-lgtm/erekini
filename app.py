from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlparse
import json
import os
import secrets
import time
from collections import deque
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from extract import extract, parse
from xml_import import import_xml
from invoice import Invoice, check, make_xml, make_draft, Validator
from ai import config, recognize, AIError
from complete import CompletionRequest, complete

ROOT=Path(__file__).parent
busy=BoundedSemaphore(1)
ai_attempts=deque()
auth_attempts=deque()

@asynccontextmanager
async def lifespan(app):
    app.state.validator=Validator()
    yield

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def protect(request,call_next):
    if request.method=='POST':
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'errors':['Nepareiza pieprasījuma izcelsme.']},status_code=403)
        try:length=int(request.headers.get('content-length','0'))
        except ValueError:length=20_000_000
        if length>11_000_000:return JSONResponse({'errors':['Fails ir pārāk liels. Maksimums 10 MB.']},status_code=413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return response

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    return JSONResponse({'errors':['Nepareiza datu struktūra vai pārsniegts lauka garums. Pārbaudiet formu (līdz 100 pozīcijām).']},status_code=422)

@app.get('/')
def index():return FileResponse(ROOT/'static/index.html')

@app.get('/api/health')
def health():return {'status':'ok','processing':'local+optional-openai','validation':['UBL 2.1 XSD','EN16931','Peppol BIS Billing 3.0']}

@app.get('/api/config')
def public_config():return config()

def authorize_ai(request):
    cfg=config()
    if not cfg['configured'] or not cfg['protected']:
        raise AIError('MI režīms vēl nav aktivizēts. Serverī jāiestata OpenAI API atslēga un rīka piekļuves parole.',503)
    # Uvicorn accepts forwarded protocol only from the local trusted nginx proxy.
    # HTTP with loopback Host is permitted only via direct local/SSH-tunnel access.
    peer=request.client.host if request.client else ''
    local=request.url.hostname in ('localhost','127.0.0.1','::1') and peer in ('127.0.0.1','::1')
    if request.url.scheme!='https' and not local:
        raise AIError('MI piekļuvei nepieciešams HTTPS vai lokāls SSH tunelis. Paroli pa publisku HTTP nesūtiet.',403)
    now=time.monotonic()
    while auth_attempts and auth_attempts[0]<now-60:auth_attempts.popleft()
    if len(auth_attempts)>=10:raise AIError('Pārāk daudz piekļuves mēģinājumu. Mēģiniet pēc minūtes.',429)
    provided=request.headers.get('x-invoice-password','')
    if not secrets.compare_digest(provided.encode(),os.environ['INVOICE_ACCESS_PASSWORD'].encode()):
        auth_attempts.append(now)
        raise AIError('Nepareiza rīka piekļuves parole. Šeit nav jāievada OpenAI API atslēga.',401)
    while ai_attempts and ai_attempts[0]<now-3600:ai_attempts.popleft()
    if len(ai_attempts)>=20:raise AIError('Sasniegts rīka limits — 20 MI pieprasījumi stundā. Mēģiniet vēlāk.',429)

@app.get('/api/demo')
def demo():return json.loads((ROOT/'demo.json').read_text())

@app.get('/demo.txt')
def demo_file():return FileResponse(ROOT/'demo.txt',media_type='text/plain',filename='parauga-rekins.txt')

@app.post('/api/extract')
async def upload(request:Request,file:UploadFile=File(...),mode:str=Form('local')):
    if not busy.acquire(blocking=False):
        await file.close()
        return JSONResponse({'errors':['Pašlaik tiek apstrādāts cits dokuments. Mēģiniet pēc brīža.']},status_code=429)
    try:
        if mode not in ('local','ai'):raise AIError('Izvēlieties lokālo vai MI atpazīšanu.',422)
        if (file.filename or '').lower().endswith('.xml'):mode='local'
        if mode=='ai':authorize_ai(request)
        data=await file.read(10_000_001)
        if len(data)>10_000_000:return JSONResponse({'errors':['Maksimālais faila izmērs ir 10 MB.']},status_code=413)
        if (file.filename or '').lower().endswith('.xml'):
            draft,notes=await run_in_threadpool(import_xml,data)
            return {'draft':draft,'text':'','notes':notes}
        text,notes=await run_in_threadpool(extract,data,file.filename or '',mode=='ai')
        if mode=='ai':
            ai_attempts.append(time.monotonic())
            draft,warnings=await run_in_threadpool(recognize,data,file.filename or '',text)
        else:
            draft,warnings=parse(text)
        return {'draft':draft,'text':text,'notes':notes+warnings}
    except AIError as e:return JSONResponse({'errors':[str(e)]},status_code=e.status)
    except ValueError as e:return JSONResponse({'errors':[str(e)]},status_code=422)
    finally:
        await file.close()
        busy.release()

@app.post('/api/complete')
def complete_invoice(req:CompletionRequest):
    return complete(req)

@app.post('/api/draft')
def draft_export(inv:Invoice):
    try:xml=make_draft(inv)
    except (ValueError,TypeError):return JSONResponse({'errors':['Dati satur neatļautas rakstzīmes. Pārbaudiet teksta laukus.']},status_code=422)
    return {'xml':xml.decode(),'filename':'rekina-melnraksts.xml'}

@app.post('/api/export')
def export(inv:Invoice):
    if not busy.acquire(blocking=False):return JSONResponse({'errors':['Pašlaik notiek cita pārbaude. Mēģiniet pēc brīža.']},status_code=429)
    try:
        d,items,groups,net,tax,total,errors=check(inv)
        if errors:return JSONResponse({'errors':errors},status_code=422)
        try:xml=make_xml(d,items,groups,net,tax,total)
        except (ValueError,TypeError):return JSONResponse({'errors':['Dati satur neatļautas rakstzīmes. Pārbaudiet teksta laukus.']},status_code=422)
        errors,warnings=app.state.validator.validate(xml)
        if errors:return JSONResponse({'errors':errors,'warnings':warnings},status_code=422)
        return {'xml':xml.decode(),'filename':'e-rekins.xml','warnings':warnings,'totals':{'net':str(net),'vat':str(tax),'total':str(total)}}
    finally:busy.release()

app.mount('/examples',StaticFiles(directory=ROOT/'examples'),name='examples')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
