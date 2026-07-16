#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PORTFOLIOS = {
    "long_fixed": [
        "SU26225RMFS1",
        "SU26230RMFS1",
        "SU26233RMFS5",
        "SU26238RMFS4",
        "SU26240RMFS0",
    ],
    "floaters": [
        "SU29007RMFS0",
        "SU29008RMFS8",
        "SU29009RMFS6",
        "SU29010RMFS4",
        "SU29013RMFS8",
    ],
}
DATE_FROM = "2022-07-14"
DATE_TO = "2026-07-16"
BASE = "https://iss.moex.com/iss"
OUT = Path("tmp_ofz_portfolios/ofz_portfolios_history.json")
UA = "Mozilla/5.0 (compatible; OFZ-Portfolio-VaR/1.0)"


def get_json(url: str, retries: int = 6):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"Failed URL {url}: {last}")


def fetch_description(secid: str):
    query = urllib.parse.urlencode({"iss.meta": "off", "iss.only": "description"})
    block = get_json(f"{BASE}/securities/{secid}.json?{query}")["description"]
    values = {}
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        values[str(rec.get("name"))] = rec.get("value")
    keys = [
        "NAME", "SHORTNAME", "ISIN", "ISSUEDATE", "STARTDATEMOEX", "MATDATE",
        "FACEVALUE", "COUPONFREQUENCY", "COUPONPERCENT", "TYPE"
    ]
    return {"SECID": secid, **{key: values.get(key) for key in keys}}


def fetch_candles(secid: str):
    rows = []
    start = 0
    while True:
        query = urllib.parse.urlencode({
            "from": DATE_FROM,
            "till": DATE_TO,
            "interval": 24,
            "start": start,
            "iss.meta": "off",
            "iss.only": "candles",
        })
        block = get_json(
            f"{BASE}/engines/stock/markets/bonds/securities/{secid}/candles.json?{query}"
        )["candles"]
        data = block.get("data", [])
        if not data:
            break
        for raw in data:
            rec = dict(zip(block["columns"], raw))
            date = str(rec.get("begin", ""))[:10]
            if date and rec.get("close") is not None:
                rows.append({
                    "Date": date,
                    "Open": rec.get("open"),
                    "High": rec.get("high"),
                    "Low": rec.get("low"),
                    "Close": rec.get("close"),
                    "Value": rec.get("value"),
                    "Volume": rec.get("volume"),
                })
        start += len(data)
        if len(data) < 500:
            break
        time.sleep(0.15)
    by_date = {row["Date"]: row for row in rows}
    result = [by_date[date] for date in sorted(by_date)]
    if len(result) < 900:
        raise RuntimeError(f"{secid}: insufficient observations: {len(result)}")
    if result[-1]["Date"] != DATE_TO:
        raise RuntimeError(f"{secid}: final date is {result[-1]['Date']}, expected {DATE_TO}")
    return result


def main():
    all_secids = []
    for names in PORTFOLIOS.values():
        for secid in names:
            if secid not in all_secids:
                all_secids.append(secid)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "MOEX ISS official market-level daily candles",
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "interval": 24,
        "portfolios": PORTFOLIOS,
        "securities": {},
    }
    for secid in all_secids:
        meta = fetch_description(secid)
        rows = fetch_candles(secid)
        output["securities"][secid] = {"meta": meta, "rows": rows}
        print(secid, len(rows), rows[0]["Date"], rows[-1]["Date"], rows[-1]["Close"])
        time.sleep(0.25)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("Wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
