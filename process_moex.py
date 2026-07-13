from __future__ import annotations

import csv
import json
import math
from bisect import bisect_left
from collections import defaultdict
from datetime import date
from pathlib import Path

import statistics

DATA = Path("moex_data")
END = date(2026, 7, 10)
TARGET_DMOD = 0.60
PRICE_FIELDS = ["LEGALCLOSEPRICE", "CLOSE", "WAPRICE", "MARKETPRICE3", "MARKETPRICE2", "ADMITTEDQUOTE"]


def f(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def d(value):
    if not value or str(value)[:10] == "0000-00-00":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def lower_row(row):
    return {str(k).lower(): v for k, v in row.items()}


def desc_map(rows):
    result = {}
    for row in rows:
        key = row.get("name") or row.get("NAME")
        value = row.get("value") if "value" in row else row.get("VALUE")
        if key:
            result[str(key)] = value
    return result


def cashflows(payload):
    flows = defaultdict(float)
    for row in payload["bondization"].get("coupons", []):
        r = lower_row(row)
        dt = d(r.get("coupondate"))
        value = f(r.get("value"))
        if dt and value is not None:
            flows[dt] += value
    for row in payload["bondization"].get("amortizations", []):
        r = lower_row(row)
        dt = d(r.get("amortdate"))
        value = f(r.get("value"))
        if dt and value is not None:
            flows[dt] += value
    return dict(flows)


def future_cashflows(payload):
    flows = defaultdict(float)
    for row in payload["bondization"].get("coupons", []):
        r = lower_row(row)
        dt = d(r.get("coupondate"))
        value = f(r.get("value"))
        if dt and dt > END and value is not None:
            flows[dt] += value
    for row in payload["bondization"].get("amortizations", []):
        r = lower_row(row)
        dt = d(r.get("amortdate"))
        value = f(r.get("value"))
        if dt and dt > END and value is not None:
            flows[dt] += value
    return dict(flows)


def select_clean(row):
    for field in PRICE_FIELDS:
        value = f(row.get(field))
        if value is not None and value > 0:
            return value, field
    return None, None


def last_positive(rows, fields):
    for row in reversed(rows):
        for field in fields:
            value = f(row.get(field))
            if value is not None and value > 0:
                return value
    return None


def fixed_duration(payload, ytm, frequency):
    flows = future_cashflows(payload)
    pv_rows = []
    for dt, amount in sorted(flows.items()):
        t = (dt - END).days / 365.0
        pv = amount / (1 + ytm / frequency) ** (frequency * t)
        pv_rows.append((t, pv))
    price = sum(x[1] for x in pv_rows)
    macaulay = sum(t * pv for t, pv in pv_rows) / price
    return macaulay / (1 + ytm / frequency)


def next_coupon(payload):
    dates = []
    for row in payload["bondization"].get("coupons", []):
        dt = d(lower_row(row).get("coupondate"))
        if dt and dt >= END:
            dates.append(dt)
    return min(dates) if dates else None


def main():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    payloads = {}
    calendar_set = set()
    last_coupon_rates = []

    for item in manifest["bonds"]:
        secid = item["secid"]
        payload = json.loads((DATA / f"{secid}.json").read_text(encoding="utf-8"))
        payloads[secid] = payload
        for row in payload["history"]:
            dt = d(row.get("TRADEDATE"))
            if dt:
                calendar_set.add(dt)
        if item["kind"] == "floater":
            rate = last_positive(payload["history"], ["COUPONPERCENT"])
            if rate:
                last_coupon_rates.append(rate / 100)

    calendar = sorted(calendar_set)
    short_rate = statistics.median(last_coupon_rates) if last_coupon_rates else 0.15
    durations = {}
    ytms = {}
    metadata = {}

    for item in manifest["bonds"]:
        secid = item["secid"]
        payload = payloads[secid]
        description = desc_map(payload["description"])
        if item["kind"] == "floater":
            reset = next_coupon(payload)
            t = max((reset - END).days / 365.0, 1 / 365) if reset else 1 / 365
            durations[secid] = t / (1 + short_rate * t)
            ytms[secid] = None
        else:
            ytm_pct = last_positive(payload["history"], ["YIELDCLOSE", "YIELDATWAP"])
            ytm = ytm_pct / 100 if ytm_pct else 0.15
            frequency = int(f(description.get("COUPONFREQUENCY")) or 2)
            durations[secid] = fixed_duration(payload, ytm, frequency)
            ytms[secid] = ytm
        metadata[secid] = {
            "name": item["name"],
            "kind": item["kind"],
            "isin": description.get("ISIN"),
            "maturity": description.get("MATDATE"),
            "coupon_frequency": f(description.get("COUPONFREQUENCY")),
            "duration": durations[secid],
            "ytm": ytms[secid],
        }

    floaters = [x["secid"] for x in manifest["bonds"] if x["kind"] == "floater"]
    fixed = [x["secid"] for x in manifest["bonds"] if x["kind"] == "fixed"]
    avg_float = statistics.mean(durations[x] for x in floaters)
    avg_fixed = statistics.mean(durations[x] for x in fixed)
    fixed_share = (TARGET_DMOD - avg_float) / (avg_fixed - avg_float)
    weights = {x: (1 - fixed_share) / len(floaters) for x in floaters}
    weights.update({x: fixed_share / len(fixed) for x in fixed})

    aligned = {}
    quality = {}
    for item in manifest["bonds"]:
        secid = item["secid"]
        payload = payloads[secid]
        by_date = {}
        for row in payload["history"]:
            dt = d(row.get("TRADEDATE"))
            if not dt:
                continue
            clean, source = select_clean(row)
            face = f(row.get("FACEVALUE")) or 1000.0
            accint = f(row.get("ACCINT")) or 0.0
            by_date[dt] = {
                "clean": clean,
                "dirty": clean * face / 100 + accint if clean is not None else None,
                "cashflow": 0.0,
                "numtrades": int(f(row.get("NUMTRADES")) or 0),
                "source": source,
                "stale": False,
            }
        shifted = defaultdict(float)
        for payment_date, amount in cashflows(payload).items():
            pos = bisect_left(calendar, payment_date)
            if pos < len(calendar):
                shifted[calendar[pos]] += amount
        rows_out = []
        last = None
        stale_count = 0
        for dt in calendar:
            current = by_date.get(dt)
            if current and current["clean"] is not None:
                last = dict(current)
                last["cashflow"] = shifted.get(dt, 0.0)
                rows_out.append(last)
            elif last is not None:
                stale = dict(last)
                stale["cashflow"] = shifted.get(dt, 0.0)
                stale["numtrades"] = 0
                stale["source"] = "FFILL"
                stale["stale"] = True
                stale_count += 1
                rows_out.append(stale)
            else:
                stale_count += 1
                rows_out.append({"clean": None, "dirty": None, "cashflow": shifted.get(dt, 0.0), "numtrades": 0, "source": None, "stale": True})
        aligned[secid] = rows_out
        quality[secid] = {"observations": len(calendar), "stale_days": stale_count, "stale_share": stale_count / len(calendar)}

    headers = ["Date"]
    for item in manifest["bonds"]:
        secid = item["secid"]
        headers += [f"{secid}_clean", f"{secid}_dirty", f"{secid}_cashflow", f"{secid}_numtrades", f"{secid}_stale"]
    with (DATA / "processed.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for i, dt in enumerate(calendar):
            row = [dt.isoformat()]
            for item in manifest["bonds"]:
                x = aligned[item["secid"]][i]
                row += [x["clean"], x["dirty"], x["cashflow"], x["numtrades"], int(x["stale"])]
            writer.writerow(row)

    result = {
        "start": calendar[0].isoformat(),
        "end": calendar[-1].isoformat(),
        "observations": len(calendar),
        "target_dmod": TARGET_DMOD,
        "portfolio_dmod": sum(weights[x] * durations[x] for x in weights),
        "short_rate": short_rate,
        "fixed_share": fixed_share,
        "weights": weights,
        "metadata": metadata,
        "quality": quality,
        "sources": {
            x["secid"]: f"https://iss.moex.com/iss/history/engines/stock/markets/bonds/boards/TQOB/securities/{x['secid']}.json?from={manifest['start']}&till={manifest['end']}"
            for x in manifest["bonds"]
        },
    }
    (DATA / "portfolio_metadata.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
