"""Klient mot TEDs offentlige søke-API (EU/EØS-dekkende utlysninger over EU-terskel).

Verifisert direkte med ekte live-kall 2026-08-31:
  POST https://api.ted.europa.eu/v3/notices/search
Ingen API-nøkkel nødvendig — bekreftet ved at uautentiserte kall returnerer ekte data.
En nøkkel trengs kun for Doffin/TEDs PUBLISERINGS-API (sende inn kunngjøringer), ikke
for søk/lesing, som er det vi trenger her.

Body er JSON, ikke query-parametere:
  {"query": "<expert query>", "fields": [...], "page": 1, "limit": 250}

Query-språket er felt-navn-basert (IKKE de gamle 2-bokstavskodene som eldre
TED-klienter i naturen bruker, f.eks. "PD"/"ND" — de treffer en annen, eldre
API-generasjon på et annet vertsnavn og virker ikke her). Bekreftede operatorer:
  - CPV: classification-cpv=33191000 (eksakt kode, kan også wildcardes: 33*)
  - Dato: publication-date>=20260101 (format YYYYMMDD, ingen bindestrek)
  - Boolsk: AND / OR, med parenteser for gruppering
  - Fritekst/fuzzy: felt~"tekst" (bekreftet på notice-title, antatt samme på andre
    tekstfelt som buyer-name, men ikke selv verifisert)

Respons: {"notices": [...], "totalNoticeCount": int, "iterationNextToken": str|None}.
Per kunngjøring er de fleste tekstfelt (tittel, oppdragsgivernavn, beskrivelse per lot)
en dict nøklet på 3-bokstavs språkkode, noen ganger med liste-verdier (én per lot) —
se _extract_text() i fetch_ted.py for hvordan dette normaliseres.

Rate limits er IKKE dokumentert med konkrete tall (TEDs eget svar: "under
forberedelse") — behandl det forsiktig med backoff, samme mønster som doffin_client.
"""

import time
from typing import Any, Optional

import requests

BASE_URL = "https://api.ted.europa.eu"
SEARCH_PATH = "/v3/notices/search"

TIMEOUT_SECONDS = 30
MAX_RETRIES = 4

DEFAULT_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "description-lot",
    "publication-date",
    "deadline-date-lot",
    "links",
    "notice-type",
    "winner-name",
]


class TedClientError(RuntimeError):
    pass


def search(query: str, page: int = 1, limit: int = 250, fields: Optional[list[str]] = None) -> dict:
    """Ett kall mot TED søke-API. Returnerer rå JSON. `page` er 1-indeksert."""
    body: dict[str, Any] = {
        "query": query,
        "fields": fields or DEFAULT_FIELDS,
        "page": page,
        "limit": limit,
    }
    url = f"{BASE_URL}{SEARCH_PATH}"
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=TIMEOUT_SECONDS,
            )
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = resp.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 15 * attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise TedClientError(f"TED-søk feilet etter {MAX_RETRIES} forsøk: {last_error}")


def smoke_test() -> None:
    """Kjør `python -m src.ted_client` for en rask, levende sjekk uten noen nøkkel."""
    result = search(query="classification-cpv=33191000 AND publication-date>=20260101", limit=3)
    print(f"totalNoticeCount={result.get('totalNoticeCount')}")
    for notice in result.get("notices", []):
        print(f"- [{notice.get('publication-number')}] {notice.get('notice-title')}")


if __name__ == "__main__":
    smoke_test()
