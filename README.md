# Doffin-overvåking for Decon-X

Automatisert jobb: **hent** nye kunngjøringer daglig fra Doffin (Norge) og TED
(hele EU/EØS over EU-terskel) → **vurder** relevans med Claude → **lever** én samlet
oppsummering på Slack (og e-post) én gang i uken. Ingen UI, ingen server — kjøres som
en cron-styrt GitHub Action.

Se [`config/relevance_profile.md`](config/relevance_profile.md) for hva som faktisk
avgjør om dette blir bra — den må fylles ut med ekte produkt-/pris-/bomtreff-detaljer
før du stoler på scorene.

## Status akkurat nå — les dette først

**Løst og verifisert med ekte data (2026-08-28).** Endepunktet er
`https://api.doffin.no/public/v2/search`, nøkkelen ligger under subscription-produktet
**"Public API"** på utviklerportalen (ikke "Notices - API", som er noe annet — se
under). Bekreftet direkte: CPV-/fritekst-/dato-filtre virker, full notice-tekst kommer
tilbake, og `lots[].winner` er reelt fylt ut — et testsøk fant faktisk en tildelt
kunngjøring der **Decon-X International AS selv er registrert vinner**. Se toppen av
[`src/doffin_client.py`](src/doffin_client.py) for detaljene, inkl. at `page` er
1-indeksert (ikke 0).

Det andre kandidat-endepunktet vi vurderte (`.../notice/notices/search-esentool`,
under produktet "Notices - API") trengs ikke lenger — det er bygget for eSendere som
sjekker status på innsendte kunngjøringer, mangler CPV-filter, og alt vi trenger
(fritekst-/CPV-søk, tildelingsdata) ligger allerede i `public/v2/search`. Den
subscriptionen kan bli stående på "Submitted" uten at det blokkerer noe.

## Oppsett (gjør i denne rekkefølgen)

### 1. Doffin API-nøkkel ✅ (du har allerede denne)

Nøkkelen fra **"Public API"**-subscriptionen din (profil → Subscriptions på
<https://dof-notices-prod-api.developer.azure-api.net>) er det som trengs. Sett
`DOFFIN_SUBSCRIPTION_KEY` lokalt (i en `.env`, kopiert fra `.env.example`), og kjør:
```bash
python -m src.doffin_client
```
for en rask, levende sjekk av at kontrakten fortsatt stemmer.

### TED (EU/EØS-dekkende) — ingen nøkkel nødvendig ✅

[`src/ted_client.py`](src/ted_client.py) kaller `api.ted.europa.eu/v3/notices/search`
direkte, uten autentisering — bekreftet med ekte, levende kall 2026-08-31 (se
modulens docstring for query-syntaks og responsskjema). `src/fetch_ted.py` kjører ett
CPV-søk over hele EU/EØS og slår resultatet sammen med det Doffin allerede fant samme
kjøring.

To ting å vite:
- Den brede/støyete CPV-koden (33100000) er **bevisst utelatt** fra TED-søket —
  EU-dekkende volum på en så bred kode ville gitt mye høyere Claude-kostnad per dag
  enn Norge-alene-volumet fra Doffin. Se `_load_cpv_codes()` i `fetch_ted.py` om du
  vil ha den med likevel.
- Norske kunngjøringer over EØS-terskel havner uansett også i Doffin, så du vil av og
  til se samme reelle anskaffelse to ganger i digesten — én gang med `kilde: DOFFIN`,
  én gang med `kilde: TED` — siden notice-ID-ene er ulike på tvers av kildene og ikke
  kan deduperes automatisk uten videre arbeid.

### 2. Anthropic API-nøkkel

Skaff en nøkkel fra [console.anthropic.com](https://console.anthropic.com), sett
`ANTHROPIC_API_KEY`.

### 3. Slack Incoming Webhook

Opprett en webhook for kanalen du vil ha digesten i, sett `SLACK_WEBHOOK_URL`.

### 4. E-post (SMTP)

Skaff SMTP-credentials (app-passord fra Microsoft 365/Gmail, eller en tjeneste som
Resend/SendGrid), sett `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`,
`DIGEST_EMAIL_TO`.

### 5. GitHub-repo og secrets

Dette repoet er `git init`-et lokalt, men ikke pushet noe sted. Opprett et repo på
GitHub og push:

```bash
git remote add origin <din-repo-url>
git add .
git commit -m "Initial scaffold"
git push -u origin main
```

Legg deretter inn secrets under **Settings → Secrets and variables → Actions** i
GitHub-repoet: `DOFFIN_SUBSCRIPTION_KEY`, `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL`,
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `DIGEST_EMAIL_TO`.
Valgfritt: en repo-**variable** `DIGEST_THRESHOLD` (default 50 hvis ikke satt).

## Lokal testing

```bash
python -m venv .venv && source .venv/bin/activate   # eller .venv\Scripts\activate på Windows
pip install -r requirements.txt
cp .env.example .env   # fyll inn nøklene dine, .env commites aldri

python -m src.fetch_doffin --since-hours 24     # se data/raw/{dato}.json og data/new_notices.json
python -m src.fetch_ted --since-days 1          # legger TED-treff til i samme new_notices.json
python -m src.score_notices                     # se data/scored_notices.json
python -m src.deliver --dry-run                 # printer digest uten å sende noe
python -m src.deliver                            # sender faktisk til Slack/e-post
```

## Kalibrering mot historiske data

```bash
python -m scripts.calibrate --years 2023,2024,2025 --limit 200
```

Laster ned DFØs årlige CSV-dumper, kjører samme scoring offline, og skriver
`calibration_output.csv` sortert på score. Fyll inn `utfall`-kolonnen manuelt
(vunnet/tapt/aldri_sett) for et utvalg saker — det er grunnlaget for å:

- Sette `DIGEST_THRESHOLD` riktig.
- Bytte ut illustrasjonene i `config/relevance_profile.md` med ekte
  treff/bomtreff-eksempler. **Bomtreffene er viktigst.**

## GitHub Action

[`.github/workflows/daily-scan.yml`](.github/workflows/daily-scan.yml) kjører fetch →
score → deliver hver dag kl. 15:00 Europe/Oslo (`0 13 * * *` UTC — kalibrert for
sommertid/CEST, juster til `0 14 * * *` når Norge går over til vintertid i slutten av
oktober). Fetch og score kjører daglig som før; **deliver** akkumulerer dagens treff i
`data/weekly_accumulator.json` (committes tilbake til repoet, samme mønster som
`data/seen_notices.json`), og sender først den samlede ukesoppsummeringen til Slack/
e-post på ukedagen satt i repo-**variabelen** `WEEKLY_DIGEST_DAY` (ISO-ukedag, 1=mandag
... 7=søndag — default 5=fredag hvis ikke satt).

Trigges også manuelt fra **Actions**-fanen (`workflow_dispatch`) — kryss av
**"Send ukesdigest nå"** der for å teste selve utsendingen med det som er akkumulert
så langt, uten å vente til fredag.

## Fase 2 (ikke bygget ennå)

- **Tildelings-tracking**: Både Doffin (`lots[].winner`) og TED (`winner-name`,
  `notice-type=can-standard`) har faktisk vinner-data rett i søkeresponsen (se
  `raw`-feltet på hver `Notice`) — filtrer på status/type for tildelte kunngjøringer og
  du har vinner-navn uten noe ekstra scraping. Å matche disse mot profilen gir
  automatisk konkurrentovervåking — hvem vant konkurransene du aldri så.
- **Kryssdeduplisering Doffin/TED**: samme norske anskaffelse over EØS-terskel dukker
  opp i begge kilder med ulik ID — å matche dem (på f.eks. tittel + oppdragsgiver +
  dato) ville fjernet dobbeltoppføringer i digesten.
