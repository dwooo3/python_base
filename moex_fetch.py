from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "https://iss.moex.com/iss"
START = "2022-07-07"
END = "2026-07-10"
OUT = Path("moex_data")
BONDS = [
    ("SU29007RMFS0", "ОФЗ 29007", "floater"),
    ("SU29008RMFS8", "ОФЗ 29008", "floater"),
    ("SU29009RMFS6", "ОФЗ 29009", "floater"),
    ("SU29010RMFS4", "ОФЗ 29010", "floater"),
    ("SU29013RMFS8", "ОФЗ 29013", "floater"),
    ("SU29015RMFS3", "ОФЗ 29015", "floater"),
    ("SU29017RMFS9", "ОФЗ 29017", "floater"),
    ("SU29018RMFS7", "ОФЗ 29018", "floater"),
    ("SU26228RMFS5", "ОФЗ 26228", "fixed"),
    ("SU26233RMFS5", "ОФЗ 26233", "fixed"),
]

session = requests.Session()
session.headers.update({"User-Agent": "MOEX-OFZ-VaR/1.0", "Accept": "application/json"})


def get_json(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}/{path.lstrip('/')}"
    params = dict(params or {})
    params.setdefault("iss.meta", "off")
    error = None
    for attempt in range(6):
        try:
            response = session.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            error = exc
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Request failed: {url}; {error}")


def rows(payload: dict, block: str) -> list[dict]:
    section = payload.get(block, {})
    columns = section.get("columns", [])
    return [dict(zip(columns, row)) for row in section.get("data", [])]


def history(secid: str) -> list[dict]:
    path = f"history/engines/stock/markets/bonds/boards/TQOB/securities/{secid}.json"
    columns = (
        "TRADEDATE,SECID,BOARDID,OPEN,HIGH,LOW,CLOSE,LEGALCLOSEPRICE,WAPRICE,"
        "MARKETPRICE2,MARKETPRICE3,ADMITTEDQUOTE,ACCINT,FACEVALUE,COUPONVALUE,"
        "COUPONPERCENT,YIELDCLOSE,YIELDATWAP,NUMTRADES,VALUE,VOLUME"
    )
    result = []
    start = 0
    while True:
        payload = get_json(path, {
            "from": START,
            "till": END,
            "start": start,
            "limit": 100,
            "history.columns": columns,
            "sort_column": "TRADEDATE",
            "sort_order": "asc",
        })
        page = rows(payload, "history")
        if not page:
            break
        result.extend(page)
        if len(page) < 100:
            break
        start += 100
    return result


def main() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = {"start": START, "end": END, "source": BASE, "bonds": []}
    for index, (secid, name, kind) in enumerate(BONDS, start=1):
        print(f"[{index}/{len(BONDS)}] {secid}", flush=True)
        description = rows(get_json(f"securities/{secid}.json"), "description")
        bondization_payload = get_json(f"securities/{secid}/bondization.json")
        bondization = {
            block: rows(bondization_payload, block)
            for block in ("coupons", "amortizations", "offers")
        }
        hist = history(secid)
        payload = {
            "secid": secid,
            "name": name,
            "kind": kind,
            "description": description,
            "bondization": bondization,
            "history": hist,
        }
        (OUT / f"{secid}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        manifest["bonds"].append({
            "secid": secid,
            "name": name,
            "kind": kind,
            "observations": len(hist),
            "first_date": hist[0].get("TRADEDATE") if hist else None,
            "last_date": hist[-1].get("TRADEDATE") if hist else None,
        })
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
