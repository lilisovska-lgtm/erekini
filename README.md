# Rēķinu darbnīca

Pirmā strādājošā versija: http://141.144.207.29/rekini/
Ir divi atpazīšanas režīmi: lokāls OCR un OpenAI MI. MI režīmā PDF/attēls vai DOCX/TXT teksts tiek nosūtīts OpenAI. XML aprēķini un validācija vienmēr notiek šajā serverī. Rīks XML nenosūta saņēmējam.

## Lietošana
1. Nospied **Izmēģini ar paraugu** vai izvēlies dokumentu.
2. Salīdzini nolasīto tekstu un aizpildītos laukus ar oriģinālu; labo vai papildini tos, īpaši pozīcijas un PVN kategorijas.
3. Ievadi/apstiprini oriģinālā rēķina apmaksas summu un elektronisko adrešu identifikatorus.
4. Atzīmē pārskatīšanas apstiprinājumu un lejupielādē XML. Kļūdaini dati vai nesakrītošas summas bloķē eksportu.

**Pašlaik publiskajai adresei ir tikai HTTP. Izmanto paraugus vai anonimizētus dokumentus. Pirms īstu rēķinu augšupielādes nepieciešams domēns un HTTPS.** Nav lietotāju kontu vai rēķinu vēstures; maksas MI režīmam ir kopīga piekļuves parole un HTTPS/lokāla tuneļa prasība.

## Atbalsts un robežas
- PDF (teksts vai OCR), PNG/JPG, DOCX un UTF-8 TXT; līdz 10 MB, 10 PDF lapām, 20 megapikseļu attēlam, 100 pozīcijām.
- Lokāls Poppler un Tesseract OCR (`lav+eng`). PDF lapas ar maz teksta tiek atpazītas ar OCR. Daļēji skenētā lapā, kurai jau ir teksta slānis, daļa attēlā esošā satura var netikt nolasīta.
- Lokālā režīma lauku atpazīšana ir piesardzīga un balstīta teksta marķieros, nevis MI; vispārīgām vai sarežģītām tabulām bieži būs jāievada dati manuāli. Optimizācija konkrētiem rēķinu izkārtojumiem gaida lietotāja paraugus.
- Pozīciju atpazīšanas sākotnējais izkārtojums: `nosaukums ; daudzums ; mērvienība ; vienības cena bez PVN ; PVN %` (arī tabulatori vai vairākas atstarpes). Piemērs `demo.txt`.
- Parasti EUR rēķini starp Latvijas uzņēmumiem, PVN S (5/12/21%), Z, E un O. PVN kategorija ir jānosaka atbilstoši darījumam, nevis tikai procentu likmei.
- Nav atbalstīti kredītrēķini, atlaides, papildmaksas, avansi, jau apmaksāti rēķini, citas valūtas, ārvalstu puses, reverse charge, XLSX vai vecais DOC formāts.
- Decimal aprēķini: katras pozīcijas neto noapaļots līdz centiem; PVN aprēķināts atsevišķi pa kategorijas/likmes grupām; obligāta precīza kopsummas salīdzināšana.
- Elektroniskās adreses shēmas 0218 (LV reģistrācijas numurs) un 9939 (LV PVN numurs). Reģistru eksistence un sasniedzamība Peppol tīklā netiek pārbaudīta.

## Validācija
Eksports iziet OASIS UBL 2.1 XSD, EN 16931 un OpenPeppol BIS Billing 3.0 Schematron pārbaudes. Oficiālās kārtulas glabājas `vendor/`, kompilētas ar ISO Schematron XSLT2 skeleton un izpildītas ar SaxonC. Avoti: `vendor/SOURCES.md`, kontrolsummas: `vendor/SHA256SUMS`. Lejupielādes datums: 2026-09-19. Kārtulu nākamās versijas jāatjauno apzināti un jāpārtestē.
Tas nepierāda, ka automātiski nolasītie dati sakrīt ar dokumentu, vai klients pieņem tieši šo formātu.

## Darbināšana
- Projekts: `/home/kursants/workspace/invoice-converter/`.
- Python venv: `.venv/`, atkarību versijas: `requirements.txt`.
- Serviss: `~/.config/systemd/user/invoice-converter.service`, localhost TCP 8010, nginx ceļš `/rekini/` esošajā noklusējuma vietnē.
- Nginx sākotnējās konfigurācijas kopija: `nginx-default.before`.
- Dokumenti tikai pieprasījuma atmiņā un pagaidu direktorijās, kuras tiek izdzēstas pēc apstrādes; nav datubāzes. Procesa avārijas gadījumā pagaidu faili var palikt privātajā systemd /tmp līdz servisa apturēšanai. Nav pilnas kriptogrāfiskas atmiņas/diska dzēšanas garantijas.
- Nav rēķinu satura pieprasījumu žurnālos. Nginx saglabā parastos piekļuves metadatus. Uvicorn access log atslēgts, nav trešo pušu skriptu vai fontu.
- Vienlaikus viena nolasīšana/eksporta validācija; OCR komandu laika ierobežojumi, systemd 1 GB atmiņas un 150% CPU ierobežojums.

```sh
systemctl --user status invoice-converter
systemctl --user restart invoice-converter
curl --fail http://127.0.0.1:8010/api/health
.venv/bin/pytest tests -q
.venv/bin/python tests/browser_check.py
```
Pārlūka pārbaude prasa Playwright Chromium (`.venv/bin/playwright install chromium`). Sistēmas pakotnes: python3-venv, poppler-utils, tesseract-ocr, tesseract-ocr-lav, tesseract-ocr-eng.

## Pārbaudes
Automātiski pārbaudīti XML noteikumi, PVN grupas un noapaļošana, nederīgi skaitļi, XML escaping, kopsummu nesakritības, manuālais apstiprinājums, PDF/DOCX/TXT nolasīšana, attēlu un skenēta PDF OCR, PDF lapu limits un API kļūdu atbildes. Pārlūkā pārbaudīta parauga lejupielāde, labojumi, apstiprinājuma atiestatīšana, TXT augšupielāde un 390px mobilais izkārtojums.


## OpenAI pieslēgšana (2026-09-20)
Integrācija ir ieviesta un pārbaudīta ar imitētām API atbildēm. Reāls maksas pieprasījums vēl nav veikts: lietotājs nav pievienojis atslēgu.

Serverī, interaktīvā SSH terminālī:
```sh
cd /home/kursants/workspace/invoice-converter
.venv/bin/python configure_ai.py
```
Skripts ar paslēptu ievadi prasa API atslēgu un divreiz rīka paroli, saglabā `.env` ar 600 tiesībām un pārstartē tikai šo servisu. Atslēgu neievieto čatā, Git, komandā vai pārlūka formā. `.env` atslēgu nosaukumi: `OPENAI_API_KEY`, `OPENAI_MODEL`, `INVOICE_ACCESS_PASSWORD`. Konfigurācijas skripts aizstāj šī projekta trīs vērtības; citas konfigurācijas šobrīd nav.

Noklusējuma modelis: `gpt-4.1-mini-2025-04-14` (var mainīt konfigurācijā). OpenAI Responses API ar stingru JSON shēmu; `store=false`, bez Files API, ārējiem rīkiem, dokumentā norādītu saišu atvēršanas vai automātiskiem atkārtotiem pieprasījumiem. `store=false` nav garantija, ka pakalpojuma sniedzējs neveic drošības žurnālu glabāšanu; jāņem vērā tā datu politika.

Kamēr nav HTTPS, no sava datora izveido SSH tuneli:
```sh
ssh -N -L 8010:127.0.0.1:8010 kursants@141.144.207.29
```
Tad atver `http://127.0.0.1:8010/` savā datorā. Izvēlies OpenAI režīmu un ievadi rīka piekļuves paroli (ne API atslēgu). Publiskā HTTP adresē MI parole netiek nosūtīta un backend MI pieprasījumus noraida. Arī pēc HTTPS ieviešanas paliek rīka paroles prasība.

`/api/config` atklāj tikai modeļa nosaukumu un konfigurācijas esamības pazīmes. Publiskie paraugi un lokālais režīms paliek pieejami bez maksas. MI pieprasījumiem limits 20 stundā kopā, nepareiziem paroles mēģinājumiem 10 minūtē; limiti ir procesa atmiņā un atiestatās pēc restarta. Piekļuves parole tiek turēta tikai pārlūka ievades laukā, ne localStorage/cookies; poga Notīrīt to dzēš.

MI kļūmes, atteikumi, nepabeigta atbilde un nederīga shēma nenoved pie klusas pārejas uz lokālu vai izdomātu rezultātu. `confirmed` vienmēr tiek atiestatīts. Neatbalstīti nosacījumi tiek saglabāti draft laukā `unsupported_features`, parādīti saskarnē un bloķē eksportu. PVN, cenu, dokumenta semantikas atpazīšana joprojām jāpārskata cilvēkam.

Oficiālie Latvija.gov.lv piemēri un salīdzinājums: `examples/README.md`. Abi oriģinālie paraugi iztur mūsu XSD un Schematron validāciju.

API dokumentācija:
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/file-inputs
- https://developers.openai.com/api/docs/models/gpt-4.1-mini

## Trūkstošo lauku automātiska aizpildīšana (2026-09-20)
Jaunā sadaļa “Automātiskā aizpildīšana” darbojas pēc augšupielādes un ar pogu jau atvērtam rēķinam. Tā izmanto `/api/complete` un neveic ārējus MI pieprasījumus.
- Ja ieslēgta elektroniskās adreses atvasināšana, Latvijas pusei ar 11 ciparu reģistrācijas numuru aizpilda tukšu EndpointID ar šo numuru un tukšu shēmu ar 0218. Izvēlētai 9939 shēmai izmanto esošu LV PVN numuru. Esošas atšķirīgas adreses nepārraksta; piegādi/reģistrāciju Peppol tīklā nepārbauda.
- Tukšu apmaksas termiņu vispirms nolasa no dokumenta. Viennozīmīgu kalendāro dienu skaitu ar norādi “no rēķina datuma/izrakstīšanas” aprēķina no izrakstīšanas datuma. Ja dokumentā nosacījumu nav, var lietot lietotāja norādīto 0–365 dienu noklusējumu. Darba dienu un piegādes/saņemšanas nosacījumus neinterpretē kā kalendārās dienas.
- Tukšu pircēja atsauci papildina no dokumenta vai lietotāja noklusējuma tikai tad, ja pircēja reģistrācijas numurs sakrīt ar iestatījumā norādīto. Neizmanto rēķina numuru vai izdomātu atsauci.
- Mērvienību apzīmējumus (gab., pcs, st., h, kg u.c.) normalizē uz UBL kodiem. Tukšām vērtībām izmanto viennozīmīgi atbilstošu dokumenta rindu vai lietotāja izvēlētu noklusējumu. Neatpazītu, bet norādītu mērvienību nepaslēpj un nepārraksta ar noklusējumu.
- Lapa uzrāda mainītos laukus, vērtības, pamatojumus un vēl trūkstošos laukus. Apstiprinājums pēc aizpildīšanas jāveic atkārtoti.
- Iestatījumi saglabājas `localStorage` tikai pēc pogas “Saglabāt iestatījumus šajā pārlūkā”; atsevišķa poga tos dzēš. API atslēga, piekļuves parole un rēķina dokumenti tur netiek glabāti. Viena saglabāta pircēja atsauce; nav pilnas klientu adrešu grāmatas.

Noteikumu avoti: https://docs.peppol.eu/poacc/billing/3.0/codelist/eas/ un https://docs.peppol.eu/poacc/billing/3.0/syntax/ubl-invoice/cbc-BuyerReference/ . Formā šobrīd jāaizpilda BuyerReference; alternatīvs OrderReference lauks vēl nav ieviests.
Pārbaude: `.venv/bin/python tests/browser_complete_check.py` (izmanto tikai parauga datus, bez ārēja MI).

Eksporta poga vispirms papildina trūkstošos laukus ar esošajiem automātiskās aizpildīšanas noteikumiem. Ja dati mainās, tie jāpārskata un jāapstiprina vēlreiz. Nezināmie dati netiek izdomāti. Tukšus neobligātos adreses komponentus UBL izlaiž; standarta obligātos laukus joprojām pārbauda. Atsevišķa poga saglabā nepilnus datus kā `rekina-melnraksts.xml` (`urn:invoice-converter:draft`); tas nav UBL un nav paredzēts iesniegšanai klientam. Melnraksts neveic atbilstības pārbaudi un saglabā arī tukšos laukus.

Elektroniskās adreses laukus pārlūks papildina uzreiz, ielādējot rēķinu vai ievadot Latvijas 11 ciparu reģistrācijas numuru. Automātiski izveidotā adrese seko reģistrācijas numura izmaiņām; nepilnam numuram to notīra. Manuāli norādītu citu adresi neaizstāj. Šī darbība vienmēr ieslēgta un neprasa MI pieprasījumu.

Pircēja atsauce nav individuāli obligāta: tās vietā var norādīt pasūtījuma numuru (UBL OrderReference). Peppol R003 prasa vismaz vienu no abiem; tukšus elementus XML neiekļauj. Melnrakstā abi var palikt tukši.

Publiskā HTTPS adrese: https://liene.opik.net (nginx → 127.0.0.1:8010). SSH tunelis nav nepieciešams. MI atpazīšanai saglabājas rīka piekļuves parole. Let’s Encrypt sertifikātu automātiski atjauno acme.sh cron.

PVN nemaksātāja rēķinam pievienota lietotāja izvēlēta poga: visām pozīcijām O, aprēķinā PVN 0, tukšam pamatojumam teksts par nereģistrētu pārdevēju. Esošu pārdevēja PVN numuru automātiski nedzēš. O rēķina XML izlaiž pircēja PartyTaxScheme atbilstoši BR-O-02; formas PVN numurs saglabājas. Izvēle pati par sevi nepārbauda reģistrācijas statusu vai nodokļu režīma piemērotību.

Precizējums pēc lietotāja e-rekins_171.xml parauga: PVN nemaksātāja poga iestata E, nevis O; pārdevējam bez PVN numura E eksportā izveido PartyTaxScheme ar reģistrācijas numuru un TaxScheme ID !=VAT. Pircēja PVN numurs saglabājas. O joprojām pieejams atsevišķi. Paraugs un jaunais E eksports iztur lokālās UBL/EN16931/Peppol pārbaudes; tas pats par sevi nav nodokļu režīma juridisks novērtējums.

Automātiskā papildināšana atpazīst skaidru latviešu teksta norādi, ka pārdevējs/piegādātājs/uzņēmums nav PVN maksātājs. Ja nav pārdevēja PVN numura un pozīciju likmes ir tukšas vai nulle, izvēlas E, 0 un aizpilda tukšu pamatojumu; tikai PVN numura trūkums nav pierādījums. Pircēja norādes un pretrunīgas pozitīvas likmes automātisku maiņu neizraisa. Tā ir dokumenta teksta atpazīšana, nevis VID reģistra pārbaude.

Lokāls UBL Invoice XML imports: bez paroles un bez MI pieprasījumiem. Pārnes galvenos rekvizītus, pozīcijas, PVN, līguma atsauci un piezīmi; atbalstīti tipu kodi 380 un 80. Ievadē XML vienmēr izmanto lokālo režīmu. Atlaides, nenulles avansi, neatbalstīta cenas bāze un vairākas nodokļu grupas importā bloķē atkārtotu eksportu. Papildu elementi (piemēram, bankas BIC un maksātāja konts) netiek pārnesti; imports nav pilnīgi identiska XML kopija. Vecie lietotāja pielikumi vairs nebija pieejami; izmantoti sintētiski struktūras testi.

Lokālajai PDF atpazīšanai pievienoti divi novērotie izkārtojumi: Latvija.gov.lv cilvēklasāmais rēķins un nomas rēķins ar divām rekvizītu kolonnām. Atpazīst tekstā esošos datumus (arī mēneša nosaukumu), pārdevēja kontu atsevišķi no pircēja, pozīcijas un apmaksas summu. Trūkstošās mērvienības/atsauces atstāj tukšas. Pārbaudīts ar abiem lietotāja PDF; personu/uzņēmumu dati nav pievienoti testa failiem.
