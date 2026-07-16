#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATE_FROM = "2022-07-15"
DATE_TO = "2026-07-16"
OUT = Path("tmp_imoex_var/imoex_history.json")
BASE = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"
UA = "Mozilla/5.0 (compatible; IMOEX-VaR-research/1.0)"


def get_json(url: str, retries: int = 6):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Failed to download {url}: {last}")


def main():
    rows = []
    start = 0
    while True:
        query = urllib.parse.urlencode({
            "from": DATE_FROM,
            "till": DATE_TO,
            "start": start,
            "iss.meta": "off",
            "iss.only": "history",
            "history.columns": "TRADEDATE,OPEN,HIGH,LOW,CLOSE",
        })
        block = get_json(f"{BASE}?{query}")["history"]
        data = block.get("data", [])
        if not data:
            break
        columns = block["columns"]
        for raw in data:
            record = dict(zip(columns, raw))
            if record.get("TRADEDATE") and record.get("CLOSE") is not None:
                rows.append({
                    "Date": record["TRADEDATE"],
                    "Open": record.get("OPEN"),
                    "High": record.get("HIGH"),
                    "Low": record.get("LOW"),
                    "Close": record.get("CLOSE"),
                })
        start += len(data)
        if len(data) < 100:
            break
        time.sleep(0.2)

    by_date = {row["Date"]: row for row in rows}
    rows = [by_date[d] for d in sorted(by_date)]
    if not rows or rows[-1]["Date"] != DATE_TO:
        raise RuntimeError(f"Unexpected last date: {rows[-1]['Date'] if rows else None}")
    if len(rows) < 375:
        raise RuntimeError(f"Insufficient observations: {len(rows)}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "MOEX ISS official IMOEX history",
        "endpoint": BASE,
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Rows:", len(rows), "first:", rows[0], "last:", rows[-1])
    print("Wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
