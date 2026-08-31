"""Lag 3: samler daglige treff og leverer én ukentlig oppsummering på Slack og/eller e-post.

Kjøres daglig av GitHub Action: leser dagens data/scored_notices.json (skrevet av
score_notices.py) og legger dem inn i data/weekly_accumulator.json (committes tilbake
til repoet, se .github/workflows/daily-scan.yml — samme mønster som seen_notices.json).
Selve utsendingen skjer kun på ukedagen satt i WEEKLY_DIGEST_DAY (ISO-ukedag, 1=mandag
... 7=søndag, default 5=fredag) — da filtreres HELE ukens akkumulerte treff på terskel,
sendes, og akkumulatoren tømmes for neste uke.

--dry-run printer digesten (uansett ukedag) i stedet for å sende, og tømmer ikke
akkumulatoren — bruk den til å teste formattering.
--force-send sender uansett ukedag (brukes typisk sammen med workflow_dispatch for å
teste utsendingen uten å vente til riktig ukedag).
"""

import argparse
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCORED_PATH = DATA_DIR / "scored_notices.json"
ACCUMULATOR_PATH = DATA_DIR / "weekly_accumulator.json"

DEFAULT_THRESHOLD = int(os.environ.get("DIGEST_THRESHOLD") or "50")
WEEKLY_DIGEST_DAY = int(os.environ.get("WEEKLY_DIGEST_DAY") or "5")  # ISO-ukedag, 5 = fredag


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_accumulator(notices: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACCUMULATOR_PATH, "w", encoding="utf-8") as f:
        json.dump(notices, f, ensure_ascii=False, indent=2)


def _accumulate_today() -> list[dict]:
    """Legger dagens scored_notices.json inn i akkumulatoren (dedupert på notice_id),
    lagrer den, og returnerer hele den oppdaterte akkumulatoren."""
    today = _load_json_list(SCORED_PATH)
    accumulated = _load_json_list(ACCUMULATOR_PATH)

    by_id = {n["notice_id"]: n for n in accumulated}
    for n in today:
        by_id[n["notice_id"]] = n

    merged = list(by_id.values())
    _save_accumulator(merged)
    return merged


def _filter_and_sort(notices: list[dict], threshold: int) -> list[dict]:
    above = [n for n in notices if n["assessment"]["score"] >= threshold]
    return sorted(above, key=lambda n: n["assessment"]["score"], reverse=True)


def _source_label(notice: dict) -> str:
    return (notice.get("matched_via") or "").split(":")[0].upper() or "?"


def _format_slack_blocks(notices: list[dict]) -> dict:
    if not notices:
        return {"text": "Ingen kunngjøringer over terskelen denne uken."}

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Ukesoppsummering — {len(notices)} treff"}}]
    for n in notices:
        a = n["assessment"]
        link = n.get("url") or "(ingen lenke funnet)"
        text = (
            f"*{n['title']}*  —  score {a['score']} · {a['segment']} · {a['flag']} · kilde: {_source_label(n)}\n"
            f"Oppdragsgiver: {n['buyer_name']} · Frist: {n.get('deadline') or 'ukjent'}\n"
            f"{link}\n"
            f"_{a['reasoning']}_"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        blocks.append({"type": "divider"})
    return {"blocks": blocks}


def _format_email_html(notices: list[dict]) -> str:
    if not notices:
        return "<p>Ingen kunngjøringer over terskelen denne uken.</p>"

    rows = ""
    for n in notices:
        a = n["assessment"]
        link = n.get("url") or ""
        rows += (
            "<tr>"
            f"<td>{a['score']}</td>"
            f"<td>{a['segment']}</td>"
            f"<td>{a['flag']}</td>"
            f"<td>{_source_label(n)}</td>"
            f"<td><a href='{link}'>{n['title']}</a></td>"
            f"<td>{n['buyer_name']}</td>"
            f"<td>{n.get('deadline') or 'ukjent'}</td>"
            f"<td>{a['reasoning']}</td>"
            "</tr>"
        )
    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Score</th><th>Segment</th><th>Flagg</th><th>Kilde</th><th>Tittel</th>"
        "<th>Oppdragsgiver</th><th>Frist</th><th>Begrunnelse</th></tr>"
        f"{rows}</table>"
    )


def send_slack(notices: list[dict]) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL ikke satt — hopper over Slack-levering.")
        return
    payload = _format_slack_blocks(notices)
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    print("Slack-melding sendt.")


def send_email(notices: list[dict]) -> None:
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("DIGEST_EMAIL_TO")
    if not host or not to_addr:
        print("SMTP_HOST/DIGEST_EMAIL_TO ikke satt — hopper over e-post-levering.")
        return

    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("SMTP_FROM") or user or "doffin-digest@localhost"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Ukesoppsummering (Doffin + TED) — {len(notices)} treff"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(_format_email_html(notices), "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
    print("E-post sendt.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Akkumuler dagens treff, og send ukentlig digest på riktig ukedag.")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-send", action="store_true", help="Send nå uansett ukedag (tømmer ikke akkumulatoren ved --dry-run).")
    args = parser.parse_args()

    accumulated = _accumulate_today()
    today_isoweekday = datetime.now(timezone.utc).isoweekday()
    is_send_day = args.force_send or today_isoweekday == WEEKLY_DIGEST_DAY

    if not is_send_day and not args.dry_run:
        print(
            f"{len(accumulated)} kunngjøringer akkumulert så langt denne uken. "
            f"Sender først på ISO-ukedag {WEEKLY_DIGEST_DAY} (i dag er dag {today_isoweekday})."
        )
        return

    notices = _filter_and_sort(accumulated, args.threshold)
    print(f"{len(notices)} av {len(accumulated)} akkumulerte kunngjøringer er over terskel {args.threshold}.")

    if args.dry_run:
        print(json.dumps(_format_slack_blocks(notices), ensure_ascii=False, indent=2))
        print(_format_email_html(notices))
        return

    send_slack(notices)
    send_email(notices)
    _save_accumulator([])  # ny uke starter tomt


if __name__ == "__main__":
    main()
