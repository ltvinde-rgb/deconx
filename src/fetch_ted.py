"""Lag 1b: henter nye TED-kunngjøringer (hele EU/EØS, over EU-terskel) og slår dem
sammen med det Doffin allerede har funnet i dette kjøreoppsettet.

Kjøres ETTER fetch_doffin.py i samme workflow-steg-rekkefølge — den laster
data/new_notices.json og data/seen_notices.json som fetch_doffin.py allerede har
oppdatert, legger nye TED-treff til, og lagrer begge filene igjen. Ingen API-nøkkel
nødvendig (se src/ted_client.py).

Kun ETT søk: alle CPV-koder i config/cpv_codes.yaml OR-et sammen, ANDet med en
publiseringsdato-grense. Den brede/støyete koden (33100000) er BEVISST utelatt her —
Doffin dekker bare Norge så volumet der er lite, men EU-dekkende søk på en bred
"medisinsk utstyr"-kode ville gitt et mye høyere antall Claude-vurderinger (og dermed
kostnad) per dag enn det er verdt. Fjern filteret i _load_cpv_codes() under om du
likevel vil ha den med.

Norske kunngjøringer over EØS-terskel havner uansett også i Doffin, så du vil se noen
kunngjøringer to ganger (én gang med doffin:-prefiks, én gang med ted:-prefiks) siden
notice-ID-ene ikke er de samme på tvers av kildene — dette er en kjent begrensning, se
README.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models import Notice
from src.ted_client import TedClientError, search

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SEEN_PATH = DATA_DIR / "seen_notices.json"
NEW_NOTICES_PATH = DATA_DIR / "new_notices.json"

MAX_PAGES = 20  # EU-dekkende volum kan være høyere enn Doffin alene
PAGE_SIZE = 250


def _load_cpv_codes() -> list[str]:
    entries = yaml.safe_load(open(CONFIG_DIR / "cpv_codes.yaml", encoding="utf-8"))
    return [e["code"] for e in entries if e.get("weight") != "noisy"]


def _load_seen() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    with open(SEEN_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def _save_seen(seen: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def _load_new_notices() -> list[dict]:
    if not NEW_NOTICES_PATH.exists():
        return []
    with open(NEW_NOTICES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _extract_text(field: Any, prefer: tuple[str, ...] = ("eng",)) -> str:
    """TED-tekstfelt kommer som dict nøklet på 3-bokstavs språkkode, noen ganger med
    liste-verdier (én per lot). Normaliserer alt til én streng."""
    if field is None:
        return ""
    if isinstance(field, list):
        return "; ".join(_extract_text(v, prefer) for v in field)
    if isinstance(field, dict):
        for lang in prefer:
            if lang in field:
                return _extract_text(field[lang], prefer)
        for value in field.values():
            return _extract_text(value, prefer)
        return ""
    return str(field)


def _extract_url(item: dict, publication_number: str) -> str:
    links = item.get("links") or {}
    html_direct = links.get("htmlDirect") or {}
    for lang in ("ENG", "MUL"):
        if lang in html_direct:
            return html_direct[lang]
    if html_direct:
        return next(iter(html_direct.values()))
    return f"https://ted.europa.eu/en/notice/{publication_number}/html"


def _parse_notice(item: dict) -> Optional[Notice]:
    pub_number = item.get("publication-number")
    if not pub_number:
        return None
    countries = item.get("buyer-country") or []
    buyer_name = _extract_text(item.get("buyer-name"))
    if countries:
        buyer_name = f"{buyer_name} ({', '.join(countries)})"
    cpv_codes = list(dict.fromkeys(item.get("classification-cpv") or []))

    return Notice(
        notice_id=f"ted:{pub_number}",
        title=_extract_text(item.get("notice-title")),
        description=_extract_text(item.get("description-lot")),
        buyer_name=buyer_name,
        cpv_codes=cpv_codes,
        published_date=item.get("publication-date"),
        deadline=_extract_text(item.get("deadline-date-lot")) or None,
        url=_extract_url(item, pub_number),
        matched_via="ted:cpv",
        raw=item,
    )


def fetch_new_ted_notices(since_days: int = 1) -> list[Notice]:
    cpv_codes = _load_cpv_codes()
    since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y%m%d")

    cpv_clause = " OR ".join(f"classification-cpv={code}" for code in cpv_codes)
    query = f"({cpv_clause}) AND publication-date>={since_date}"

    seen = _load_seen()
    existing_new = _load_new_notices()
    by_id = {n["notice_id"]: n for n in existing_new}

    raw_hits: list[dict] = []
    page = 1
    total = None
    try:
        while True:
            result = search(query=query, page=page, limit=PAGE_SIZE)
            total = result.get("totalNoticeCount", 0)
            hits = result.get("notices", [])
            raw_hits.extend(hits)
            if len(raw_hits) >= total or page >= MAX_PAGES or not hits:
                if total and len(raw_hits) < total:
                    print(f"ADVARSEL: TED-søk kuttet ved {len(raw_hits)} av {total} treff (MAX_PAGES nådd).")
                break
            page += 1
    except TedClientError as exc:
        print(f"ADVARSEL: TED-søk feilet, fortsetter med det Doffin allerede fant: {exc}")
        raw_hits = []

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dump_path = RAW_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_ted.json"
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(raw_hits, f, ensure_ascii=False, indent=2)

    new_from_ted: list[Notice] = []
    for item in raw_hits:
        notice = _parse_notice(item)
        if not notice or notice.notice_id in seen or notice.notice_id in by_id:
            continue
        by_id[notice.notice_id] = notice.to_dict()
        seen.add(notice.notice_id)
        new_from_ted.append(notice)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(NEW_NOTICES_PATH, "w", encoding="utf-8") as f:
        json.dump(list(by_id.values()), f, ensure_ascii=False, indent=2)
    _save_seen(seen)

    return new_from_ted


def main() -> None:
    parser = argparse.ArgumentParser(description="Hent nye TED-kunngjøringer siste N dager (dato-oppløsning, ikke timer).")
    parser.add_argument("--since-days", type=int, default=1)
    args = parser.parse_args()

    new_notices = fetch_new_ted_notices(since_days=args.since_days)
    print(f"{len(new_notices)} nye TED-kunngjøringer funnet, lagt til i {NEW_NOTICES_PATH}")


if __name__ == "__main__":
    main()
