from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Notice:
    notice_id: str
    title: str
    description: str
    buyer_name: str
    cpv_codes: list[str]
    published_date: Optional[str]
    deadline: Optional[str]
    url: Optional[str]
    matched_via: str  # "cpv:<code>" eller "buyer:<navn>" — hvilket søk som fant den
    raw: dict

    def to_dict(self) -> dict:
        return asdict(self)
