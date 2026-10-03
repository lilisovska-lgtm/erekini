# Oficiālie Latvija.gov.lv e-rēķinu paraugi

Lejupielādēti 2026-09-20 bez pārveidošanas.
Avota lapa: https://www.vdaa.gov.lv/lv/e-rekini (Latvija.gov.lv portāla pārziņa oficiālā e-rēķinu sadaļa, atjaunināta 2026-02-11).
Latvija.gov.lv lapa tieši neatbildēja servera HTTP un pārlūka pieprasījumiem; izmantotas VDAA publicētās saites uz tā portāla CDN.

- `einvoice_shema_nePVN2.xml`: https://cdn.viss.gov.lv/LVP3/media/einvoice_shema_nePVN2.xml
- `creditnote_shema_PVN1.xml`: https://cdn.viss.gov.lv/LVP3/media/creditnote_shema_PVN1.xml

Abi oriģināli pārbaudīti ar attiecīgo UBL 2.1 XSD un projektā esošajām EN 16931 / Peppol kārtulām; rezultāti un SHA256 ir `validation-report.json`. Šīs pārbaudes nav reāla iesniegšana portālā.

## Izmantošana rīkā
- Eksports izmanto to pašu UBL Invoice namespace, CustomizationID, ProfileID un EUR kodu. Latvijas reģistrācijas numura elektroniskās adreses shēma 0218 sakrīt ar paraugu.
- Ieviesti paraugā norādītie formas garuma limiti rēķina numuram (35), pircēja atsaucei (200), pušu nosaukumiem (200), pozīciju nosaukumiem (200).
- Pievienotas paraugā izmantotās H87 un T3 mērvienības.
- Nepārkopējam izdomātus banku rekvizītus vai komplicētu rēķinu datus. Oficiālajā Invoice paraugā ir kods 386, iepriekšēja samaksa un pozīciju atlaides/piemaksas. Esošais rīks eksportē parastu 380 rēķinu; MI identificētus neatbalstītus nosacījumus bloķē.
- Kredītpaziņojuma paraugs pieejams atsaucei, bet tā eksports nav ieviests.
