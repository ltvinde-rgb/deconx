# Doffin-overvåking for Decon-X

Daglig, automatisert jobb: **hent** nye Doffin-kunngjøringer → **vurder** relevans med
Claude → **lever** en digest på Slack og e-post. Ingen UI, ingen server — kjøres som en
cron-styrt GitHub Action.

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
score → deliver hver dag kl. 05:00 UTC (juster cron for norsk sommertid om du vil ha
eksakt lokal klokketid), og committer `data/seen_notices.json` tilbake til repoet som
dedup-state. Kan også trigges manuelt fra **Actions**-fanen (`workflow_dispatch`).

## Fase 2 (ikke bygget ennå)

- **TED-utvidelse**: TED har et gratis, dokumentert søke-API uten nøkkel
  (`search-api.ted.europa.eu`, v3) — samme CPV-/oppdragsgiver-filtre og samme
  scoring-lag, egen `fetch_ted.py`. Relevant når DX3/Nofima-samarbeidet skal utenfor
  Norge, siden EØS-terskel-kunngjøringer fra Norge uansett går til TED.
- **Tildelings-tracking**: Det bekreftede API-skjemaet har faktisk `lots[].winner`
  rett i søkeresponsen (se `raw`-feltet på hver `Notice`) — filtrer på `status` for
  tildelte kunngjøringer og du har vinner-navn uten noe ekstra scraping. Å matche disse
  mot profilen gir automatisk konkurrentovervåking — hvem vant konkurransene du aldri
  så.
