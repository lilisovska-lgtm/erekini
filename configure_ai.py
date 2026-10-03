"""Run interactively over SSH. Never send an API key through chat or HTTP."""
from pathlib import Path
import getpass
import os
import re
import subprocess

ROOT=Path(__file__).resolve().parent

def main():
    key=getpass.getpass('OpenAI API atslēga (ievade paslēpta): ').strip()
    if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,}',key):raise SystemExit('Nederīgs API atslēgas formāts; nekas nav saglabāts.')
    password=getpass.getpass('Izvēlies rīka piekļuves paroli (vismaz 20 burti/cipari vai -_): ')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',password):raise SystemExit('Parole neatbilst nosacījumiem; nekas nav saglabāts.')
    if password!=getpass.getpass('Atkārto rīka paroli: '):raise SystemExit('Paroles nesakrīt; nekas nav saglabāts.')
    model=input('OpenAI modelis [gpt-4.1-mini-2025-04-14]: ').strip() or 'gpt-4.1-mini-2025-04-14'
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',model):raise SystemExit('Nederīgs modeļa nosaukums.')
    temp=ROOT/'.setup.env'
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(f'OPENAI_API_KEY={key}\nOPENAI_MODEL={model}\nINVOICE_ACCESS_PASSWORD={password}\n')
        os.replace(temp,ROOT/'.env')
    finally:
        if temp.exists():temp.unlink()
    subprocess.run(['systemctl','--user','restart','invoice-converter.service'],check=True)
    print('MI konfigurācija saglabāta .env ar 600 tiesībām; serviss pārstartēts. Atslēga netiek izvadīta.')
    print('Rīka paroli ievadi tikai HTTPS lapā vai caur SSH tuneli. API atslēga paliek serverī.')

if __name__=='__main__':main()
