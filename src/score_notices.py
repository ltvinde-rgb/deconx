"""Lag 2: Claude vurderer hver ny kunngjøring mot config/relevance_profile.md.

Leser data/new_notices.json (skrevet av fetch_doffin.py), kaller Claude én gang per
kunngjøring med tvunget tool-use for strukturert output, og skriver
data/scored_notices.json — notice + vurdering slått sammen, brukt av deliver.py.
"""

import json
import os
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
NEW_NOTICES_PATH = DATA_DIR / "new_notices.json"
SCORED_PATH = DATA_DIR / "scored_notices.json"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

ASSESSMENT_TOOL = {
    "name": "submit_assessment",
    "description": "Send inn relevansvurderingen for denne kunngjøringen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Relevans for Decon-X, 0-100.",
            },
            "segment": {
                "type": "string",
                "enum": ["helse", "dyrehelse", "mat", "none"],
            },
            "flag": {
                "type": "string",
                "enum": ["direkte_dx1", "direkte_dx3", "underleverandor", "none"],
            },
            "reasoning": {
                "type": "string",
                "description": "Kort norsk begrunnelse — spesifikt hvorfor, ikke bare hva.",
            },
        },
        "required": ["score", "segment", "flag", "reasoning"],
    },
}


def _build_system_prompt(relevance_profile: str) -> str:
    return (
        "Du vurderer offentlige anbudskunngjøringer fra Doffin for om de er relevante "
        "for Decon-X, basert på relevansprofilen under. Vær presis og skeptisk — de "
        "fleste kunngjøringer som matcher en CPV-kode er IKKE reelle treff, se "
        "diskvalifiserende kriterier og bomtreff-eksemplene i profilen. Begrunnelsen "
        "skal alltid forklare HVORFOR, ikke bare gjenta kunngjøringens innhold.\n\n"
        f"{relevance_profile}"
    )


def _build_user_prompt(notice: dict) -> str:
    return (
        f"Tittel: {notice.get('title', '')}\n"
        f"Oppdragsgiver: {notice.get('buyer_name', '')}\n"
        f"CPV-koder: {', '.join(notice.get('cpv_codes', []))}\n"
        f"Frist: {notice.get('deadline', 'ukjent')}\n"
        f"Funnet via: {notice.get('matched_via', '')}\n\n"
        f"Beskrivelse:\n{notice.get('description', '(ingen beskrivelse)')}\n\n"
        "Vurder relevansen for Decon-X og kall submit_assessment."
    )


def score_notices(notices: list[dict]) -> list[dict]:
    if not notices:
        return []

    relevance_profile = (CONFIG_DIR / "relevance_profile.md").read_text(encoding="utf-8")
    client = anthropic.Anthropic()
    system_prompt = _build_system_prompt(relevance_profile)

    scored: list[dict] = []
    for notice in notices:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=[ASSESSMENT_TOOL],
            tool_choice={"type": "tool", "name": "submit_assessment"},
            messages=[{"role": "user", "content": _build_user_prompt(notice)}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        assessment = tool_use.input
        scored.append({**notice, "assessment": assessment})

    return scored


def main() -> None:
    if not NEW_NOTICES_PATH.exists():
        print(f"{NEW_NOTICES_PATH} finnes ikke — kjør fetch_doffin.py først.")
        return

    with open(NEW_NOTICES_PATH, encoding="utf-8") as f:
        notices = json.load(f)

    scored = score_notices(notices)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCORED_PATH, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)

    print(f"{len(scored)} kunngjøringer vurdert, skrevet til {SCORED_PATH}")


if __name__ == "__main__":
    main()
