"""Lag 1: henter rå kunngjøringer fra Doffin siste N timer.

To spor, per config/cpv_codes.yaml og config/buyers.yaml:
  1. Ett søk per CPV-kode (fanger opp korrekt taggede kunngjøringer).
  2. Ett fritekst-søk (searchString) per navngitt oppdragsgiver, uten CPV-filter
     (fanger opp slurvete taggede underterskel-kunngjøringer fra oppdragsgivere vi
     uansett følger — searchString er ikke bekreftet å treffe eksakt på buyer-feltet,
     bare at det er det nærmeste fritekst-alternativet API-et har).

Resultatet deduperes på notice-ID, kryssjekkes mot data/seen_notices.json, og de nye
skrives til data/new_notices.json for score_notices.py. Alt rått dumpes uendret til
data/raw/{dato}.json for å kunne se når filteret bommer.

Feltnavnene i _parse_notice matcher det bekreftede skjemaet fra api.doffin.no/public/v2/search
(se src/doffin_client.py) — hits[].heading/description/buyer/cpvCodes/issueDate/deadline/doffinClassicUrl.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from src.doffin_client import DoffinClient
from src.models import Notice

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SEEN_PATH = DATA_DIR / "seen_notices.json"
NEW_NOTICES_PATH = DATA_DIR / "new_notices.json"

MAX_PAGES = 10  # sikkerhetstak — 24-timers-vinduet bør aldri nærme seg 10*100 treff


def _search_all_pages(client: DoffinClient, **search_kwargs: Any) -> list[dict]:
    """Henter alle sider for ett søk, opp til MAX_PAGES. Logger hvis vi bommer noe."""
    hits: list[dict] = []
    page = 1
    total = None
    while True:
        raw = client.search(page=page, **search_kwargs)
        total = raw.get("numHitsTotal", 0)
        hits.extend(raw.get("hits", []))
        if len(hits) >= total or page >= MAX_PAGES:
            if len(hits) < total:
                print(f"ADVARSEL: kuttet ved {len(hits)} av {total} treff for {search_kwargs} (MAX_PAGES nådd).")
            break
        page += 1
    return hits


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_seen() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    with open(SEEN_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def _save_seen(seen: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def _parse_notice(item: dict, matched_via: str) -> Optional[Notice]:
    notice_id = item.get("id")
    if not notice_id:
        return None
    buyer_names = ", ".join(b.get("name", "") for b in item.get("buyer", []) if b.get("name"))
    return Notice(
        notice_id=str(notice_id),
        title=item.get("heading") or "",
        description=item.get("description") or "",
        buyer_name=buyer_names,
        cpv_codes=list(item.get("cpvCodes") or []),
        published_date=item.get("publicationDate") or item.get("issueDate"),
        deadline=item.get("deadline"),
        url=item.get("doffinClassicUrl") or f"https://doffin.no/notices/{notice_id}",
        matched_via=matched_via,
        raw=item,
    )


def fetch_new_notices(since_hours: int = 24) -> list[Notice]:
    client = DoffinClient()
    issue_date_from = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    cpv_config = _load_yaml(CONFIG_DIR / "cpv_codes.yaml")
    buyers_config = _load_yaml(CONFIG_DIR / "buyers.yaml")

    raw_dump: list[dict] = []
    by_id: dict[str, Notice] = {}

    for entry in cpv_config:
        code = entry["code"]
        hits = _search_all_pages(client, cpv_codes=[code], issue_date_from=issue_date_from)
        raw_dump.append({"pass": "cpv", "cpv_code": code, "hits": hits})
        for item in hits:
            notice = _parse_notice(item, matched_via=f"cpv:{code}")
            if notice and notice.notice_id not in by_id:
                by_id[notice.notice_id] = notice

    all_buyer_names = [name for group in buyers_config.values() for name in group]
    for buyer_name in all_buyer_names:
        hits = _search_all_pages(client, search_string=buyer_name, issue_date_from=issue_date_from)
        raw_dump.append({"pass": "buyer", "buyer": buyer_name, "hits": hits})
        for item in hits:
            notice = _parse_notice(item, matched_via=f"buyer:{buyer_name}")
            if notice and notice.notice_id not in by_id:
                by_id[notice.notice_id] = notice

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dump_path = RAW_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(raw_dump, f, ensure_ascii=False, indent=2)

    seen = _load_seen()
    new_notices = [n for n in by_id.values() if n.notice_id not in seen]

    seen.update(by_id.keys())
    _save_seen(seen)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(NEW_NOTICES_PATH, "w", encoding="utf-8") as f:
        json.dump([n.to_dict() for n in new_notices], f, ensure_ascii=False, indent=2)

    return new_notices


def main() -> None:
    parser = argparse.ArgumentParser(description="Hent nye Doffin-kunngjøringer siste N timer.")
    parser.add_argument("--since-hours", type=int, default=24)
    args = parser.parse_args()

    new_notices = fetch_new_notices(since_hours=args.since_hours)
    print(f"{len(new_notices)} nye kunngjøringer funnet, skrevet til {NEW_NOTICES_PATH}")


if __name__ == "__main__":
    main()
