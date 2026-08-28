"""Lag 3: leverer alt over terskel som Slack-melding og/eller e-post.

Leser data/scored_notices.json (skrevet av score_notices.py). --dry-run printer
digesten i stedet for å sende — bruk den til å teste formattering før
SLACK_WEBHOOK_URL / SMTP_* er lagt inn som secrets.
"""

import argparse
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCORED_PATH = DATA_DIR / "scored_notices.json"

DEFAULT_THRESHOLD = int(os.environ.get("DIGEST_THRESHOLD", "50"))


def _load_scored() -> list[dict]:
    if not SCORED_PATH.exists():
        return []
    with open(SCORED_PATH, encoding="utf-8") as f:
        return json.load(f)


def _filter_and_sort(notices: list[dict], threshold: int) -> list[dict]:
    above = [n for n in notices if n["assessment"]["score"] >= threshold]
    return sorted(above, key=lambda n: n["assessment"]["score"], reverse=True)


def _format_slack_blocks(notices: list[dict]) -> dict:
    if not notices:
        return {"text": "Ingen Doffin-kunngjøringer over terskelen i dag."}

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Doffin-digest — {len(notices)} treff"}}]
    for n in notices:
        a = n["assessment"]
        link = n.get("url") or "(ingen lenke funnet)"
        text = (
            f"*{n['title']}*  —  score {a['score']} · {a['segment']} · {a['flag']}\n"
            f"Oppdragsgiver: {n['buyer_name']} · Frist: {n.get('deadline', 'ukjent')}\n"
            f"{link}\n"
            f"_{a['reasoning']}_"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        blocks.append({"type": "divider"})
    return {"blocks": blocks}


def _format_email_html(notices: list[dict]) -> str:
    if not notices:
        return "<p>Ingen Doffin-kunngjøringer over terskelen i dag.</p>"

    rows = ""
    for n in notices:
        a = n["assessment"]
        link = n.get("url") or ""
        rows += (
            "<tr>"
            f"<td>{a['score']}</td>"
            f"<td>{a['segment']}</td>"
            f"<td>{a['flag']}</td>"
            f"<td><a href='{link}'>{n['title']}</a></td>"
            f"<td>{n['buyer_name']}</td>"
            f"<td>{n.get('deadline', 'ukjent')}</td>"
            f"<td>{a['reasoning']}</td>"
            "</tr>"
        )
    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Score</th><th>Segment</th><th>Flagg</th><th>Tittel</th>"
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

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("SMTP_FROM", user or "doffin-digest@localhost")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Doffin-digest — {len(notices)} treff"
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
    parser = argparse.ArgumentParser(description="Lever Doffin-digest over Slack og/eller e-post.")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    all_notices = _load_scored()
    notices = _filter_and_sort(all_notices, args.threshold)
    print(f"{len(notices)} av {len(all_notices)} kunngjøringer er over terskel {args.threshold}.")

    if args.dry_run:
        print(json.dumps(_format_slack_blocks(notices), ensure_ascii=False, indent=2))
        print(_format_email_html(notices))
        return

    send_slack(notices)
    send_email(notices)


if __name__ == "__main__":
    main()
