"""Kalibrering: kjør scoring-laget mot historiske Doffin-kunngjøringer.

Laster ned DFØs årlige CSV-dump (bekreftet nedlastbar uten API-nøkkel), mapper
kolonnene til samme Notice-form som fetch_doffin.py produserer, og kjører
score_notices.py sin logikk offline i batch — ingen Doffin-API eller ferske secrets
nødvendig, bare ANTHROPIC_API_KEY.

Output er en CSV du fyller inn "utfall"-kolonnen på manuelt (vunnet / tapt / aldri_sett)
for et utvalg saker — det gir et konkret grunnlag for å sette DIGEST_THRESHOLD og for
å bytte ut illustrasjonene i config/relevance_profile.md med ekte saker.

CSV-kolonnenavn er IKKE bekreftet 1:1 mot det som faktisk ligger i filene — sjekk
_COLUMN_CANDIDATES under mot en nedlastet fil og juster ved avvik.
"""

import argparse
import csv
from pathlib import Path

import requests

from src.score_notices import score_notices

ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_DIR = ROOT / "data" / "calibration"

CSV_URL_TEMPLATE = "https://adaapnedataprodst.blob.core.windows.net/kunngjoringer/{year}/Kunngjoringer_{year}.csv"

_COLUMN_CANDIDATES = {
    "notice_id": ["doffin_referanse", "referanse", "id"],
    "title": ["navn", "tittel", "title"],
    "description": ["beskrivelse", "description"],
    "buyer_name": ["publisert_av", "oppdragsgiver", "buyer_name"],
    "cpv": ["cpv", "cpv_koder"],
    "published_date": ["kunngjoring_dato", "publisert_dato"],
    "deadline": ["frist", "tilbudsfrist"],
}


def _pick(row: dict, candidates: list[str]) -> str:
    for c in candidates:
        if c in row and row[c]:
            return row[c]
    return ""


def download_year(year: int) -> Path:
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    dest = CALIBRATION_DIR / f"Kunngjoringer_{year}.csv"
    if dest.exists():
        return dest
    url = CSV_URL_TEMPLATE.format(year=year)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def load_notices_from_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)

    notices = []
    for row in rows:
        cpv_raw = _pick(row, _COLUMN_CANDIDATES["cpv"])
        notices.append(
            {
                "notice_id": _pick(row, _COLUMN_CANDIDATES["notice_id"]),
                "title": _pick(row, _COLUMN_CANDIDATES["title"]),
                "description": _pick(row, _COLUMN_CANDIDATES["description"]),
                "buyer_name": _pick(row, _COLUMN_CANDIDATES["buyer_name"]),
                "cpv_codes": [c.strip() for c in cpv_raw.split(",") if c.strip()],
                "published_date": _pick(row, _COLUMN_CANDIDATES["published_date"]),
                "deadline": _pick(row, _COLUMN_CANDIDATES["deadline"]),
                "url": "",
                "matched_via": "calibration",
            }
        )
    return [n for n in notices if n["notice_id"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalibrer scoring mot historiske Doffin-CSV-er.")
    parser.add_argument("--years", type=str, default="2023,2024,2025", help="Kommaseparert liste, f.eks. 2023,2024")
    parser.add_argument("--limit", type=int, default=200, help="Maks antall kunngjøringer å score (kostnadskontroll)")
    parser.add_argument("--out", type=str, default="calibration_output.csv")
    args = parser.parse_args()

    all_notices: list[dict] = []
    for year in args.years.split(","):
        path = download_year(int(year))
        notices = load_notices_from_csv(path)
        print(f"{year}: {len(notices)} kunngjøringer lastet fra {path}")
        all_notices.extend(notices)

    if len(all_notices) > args.limit:
        print(f"Begrenser til {args.limit} av {len(all_notices)} for kostnadskontroll (juster med --limit).")
        all_notices = all_notices[: args.limit]

    scored = score_notices(all_notices)

    out_path = ROOT / args.out
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["score", "segment", "flag", "title", "buyer_name", "published_date", "reasoning", "utfall"])
        for n in sorted(scored, key=lambda x: x["assessment"]["score"], reverse=True):
            a = n["assessment"]
            writer.writerow(
                [a["score"], a["segment"], a["flag"], n["title"], n["buyer_name"], n["published_date"], a["reasoning"], ""]
            )

    print(f"Skrev {len(scored)} vurderinger til {out_path}. Fyll inn 'utfall'-kolonnen manuelt (vunnet/tapt/aldri_sett).")


if __name__ == "__main__":
    main()
