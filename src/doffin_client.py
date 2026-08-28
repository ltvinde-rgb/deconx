"""Klient mot Doffins offentlige søke-API — BEKREFTET med ekte data 2026-08-28.

    GET https://api.doffin.no/public/v2/search

Nøkkelen ligger under produktet "Public API" på utviklerportalen
(dof-notices-prod-api.developer.azure-api.net → profil → Subscriptions), adskilt fra
produktet "Notices - API" (som er for eSendere som sjekker status på innsendte
kunngjøringer via search-esentool-endepunktet — ikke nødvendig for oss lenger, se under).

Verifisert direkte med ekte subscription-key:
  - `page` er 1-indeksert — page=0 gir 400 "Parameter page must be >= 1".
  - Responsen matcher nøyaktig det som ble funnet i kildekoden til tredjeparts-verktøyet
    `doffinmcp` (som kaller en beslektet dev-instans, betaapi.doffin.no) — samme
    kontrakt, nå bekreftet på PROD-verten med et ekte, aktivt nøkkel.
  - `lots[].winner` er reelt fylt ut i praksis — et faktisk søk på cpvCode=33191000
    ga bl.a. en tildelt kunngjøring der Decon-X International AS selv står som
    vinner. Dette gir oss tapt/vunnet-tracking (fase 2) helt gratis, uten noe eget
    endepunkt.
  - `doffinClassicUrl` er ofte `null` i praksis — bygg lenken selv som
    `https://doffin.no/notices/{id}` (bekreftet å gi en gyldig side).

Bekreftede query-parametere: searchString, cpvCode (repeterbar), status (repeterbar),
type (repeterbar), location (repeterbar), issueDateFrom, issueDateTo,
estimatedValueFrom, estimatedValueTo, page (1-indeksert), numHitsPerPage, sortBy.

Respons: {"numHitsTotal": int, "numHitsAccessible": int, "hits": [{"id", "heading",
"description", "buyer": [{"name", ...}], "cpvCodes": [...], "issueDate",
"publicationDate", "deadline", "status", "estimatedValue", "lots": [{"winner": [...]}],
"doffinClassicUrl", ...}]}

Det separate, offisielle "Notices - API"-endepunktet
(api.doffin.no/api/v2/notice/notices/search-esentool, funnet i Doffins egen
Swagger-dokumentasjon) er ikke lenger nødvendig for kjernebruken vår — det API-et som
faktisk trengs (fritekst/CPV-søk med fullt innhold) er dette. Den koden er fjernet for
å ikke holde på en ubrukt og ubekreftet kontrakt; se git-historikk om den skulle bli
aktuell igjen (f.eks. om Doffin skulle fjerne CPV-filtrering fra public/v2/search).
"""

import os
import time
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "https://api.doffin.no/public/v2"
DEFAULT_SEARCH_PATH = "/search"

TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class DoffinClientError(RuntimeError):
    pass


def _get_with_retries(url: str, headers: dict, params: dict) -> dict:
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise DoffinClientError(f"Doffin-søk mot {url} feilet etter {MAX_RETRIES} forsøk: {last_error}")


class DoffinClient:
    def __init__(
        self,
        subscription_key: Optional[str] = None,
        base_url: Optional[str] = None,
        search_path: Optional[str] = None,
    ):
        self.subscription_key = subscription_key or os.environ.get("DOFFIN_SUBSCRIPTION_KEY")
        if not self.subscription_key:
            raise DoffinClientError(
                "DOFFIN_SUBSCRIPTION_KEY er ikke satt. Hent den fra 'Public API'-subscriptionen "
                "på https://dof-notices-prod-api.developer.azure-api.net (profil → Subscriptions)."
            )
        self.base_url = (base_url or os.environ.get("DOFFIN_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.search_path = search_path or os.environ.get("DOFFIN_SEARCH_PATH") or DEFAULT_SEARCH_PATH

    def _headers(self) -> dict:
        return {
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Accept": "application/json",
            "User-Agent": "decon-x-doffin-sokjer/1.0",
        }

    def search(
        self,
        search_string: Optional[str] = None,
        cpv_codes: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        types: Optional[list[str]] = None,
        locations: Optional[list[str]] = None,
        issue_date_from: Optional[str] = None,
        issue_date_to: Optional[str] = None,
        estimated_value_from: Optional[float] = None,
        estimated_value_to: Optional[float] = None,
        page: int = 1,
        num_hits_per_page: int = 100,
        sort_by: Optional[str] = None,
    ) -> dict:
        """Ett kall mot søke-endepunktet. Returnerer rå JSON (se modulens docstring for form).

        issue_date_from/issue_date_to forventes som ISO 8601-datoer og filtrerer på
        `issueDate`, ikke `publicationDate` — det er det eneste dato-filteret API-et
        bekreftet støtter. `page` er 1-indeksert.
        """
        params: dict[str, Any] = {"page": page, "numHitsPerPage": num_hits_per_page}
        if search_string:
            params["searchString"] = search_string
        if cpv_codes:
            params["cpvCode"] = cpv_codes
        if statuses:
            params["status"] = statuses
        if types:
            params["type"] = types
        if locations:
            params["location"] = locations
        if issue_date_from:
            params["issueDateFrom"] = issue_date_from
        if issue_date_to:
            params["issueDateTo"] = issue_date_to
        if estimated_value_from is not None:
            params["estimatedValueFrom"] = estimated_value_from
        if estimated_value_to is not None:
            params["estimatedValueTo"] = estimated_value_to
        if sort_by:
            params["sortBy"] = sort_by

        url = f"{self.base_url}{self.search_path}"
        return _get_with_retries(url, self._headers(), params)


def smoke_test() -> None:
    """Kjør dette manuelt (`python -m src.doffin_client`) for en rask, levende sjekk av
    at kontrakten fortsatt stemmer."""
    client = DoffinClient()
    print(f"Base URL: {client.base_url}{client.search_path}")
    result = client.search(cpv_codes=["33191000"], num_hits_per_page=5)
    print(f"numHitsTotal={result.get('numHitsTotal')}, hits i denne siden={len(result.get('hits', []))}")
    for hit in result.get("hits", []):
        print(f"- [{hit.get('id')}] {hit.get('heading')} — {[b.get('name') for b in hit.get('buyer', [])]}")


if __name__ == "__main__":
    smoke_test()
