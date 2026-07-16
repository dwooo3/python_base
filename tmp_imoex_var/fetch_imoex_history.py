#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATE_FROM = "2026-07-10"
DATE_TO = "2026-07-16"
OUT = Path("tmp_imoex_var/imoex_update.json")
BASE = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"
UA = "Mozilla/5.0 (compatible; IMOEX-VaR-research/1.0)"


def main():
    query = urllib.parse.urlencode({
        "from": DATE_FROM,
        "till": DATE_TO,
        "iss.meta": "off",
        "iss.only": "history",
        "history.columns": "TRADEDATE,OPEN,HIGH,LOW,CLOSE",
    })
    request = urllib.request.Request(f"{BASE}?{query}", headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        block = json.loads(response.read().decode("utf-8"))["history"]
    columns = block["columns"]
    rows = []
    for raw in block.get("data", []):
        record = dict(zip(columns, raw))
        if record.get("TRADEDATE") and record.get("CLOSE") is not None:
            rows.append({
                "Date": record["TRADEDATE"],
                "Open": record.get("OPEN"),
                "High": record.get("HIGH"),
                "Low": record.get("LOW"),
                "Close": record.get("CLOSE"),
            })
    rows.sort(key=lambda row: row["Date"])
    if not rows or rows[-1]["Date"] != DATE_TO:
        raise RuntimeError(f"Unexpected last date: {rows[-1]['Date'] if rows else None}")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "MOEX ISS official IMOEX history",
        "endpoint": BASE,
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
