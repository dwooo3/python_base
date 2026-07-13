from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

DATA = Path("moex_data")
PORTFOLIO_SIZE = 100_000_000.0
WINDOW = 375
START = date(2022, 7, 11)
PART_SIZE = 100


def percentile_inc(values: list[float], p: float) -> float:
    xs = sorted(values)
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return xs[lo]
    weight = rank - lo
    return xs[lo] * (1 - weight) + xs[hi] * weight


def main() -> None:
    meta = json.loads((DATA / "portfolio_metadata.json").read_text(encoding="utf-8"))
    weights = meta["weights"]
    secids = list(weights)
    rows = list(csv.DictReader((DATA / "processed.csv").open(encoding="utf-8")))

    results = []
    clean_value = PORTFOLIO_SIZE
    total_value = PORTFOLIO_SIZE
    clean_returns = []
    total_returns = []
    current = {}

    for i in range(1, len(rows)):
        today = date.fromisoformat(rows[i]["Date"])
        prev = rows[i - 1]
        row = rows[i]
        clean_ret = 0.0
        total_ret = 0.0
        valid = True
        for secid in secids:
            pc = float(prev[f"{secid}_clean"])
            pd = float(prev[f"{secid}_dirty"])
            cc = float(row[f"{secid}_clean"])
            cd = float(row[f"{secid}_dirty"])
            cf = float(row[f"{secid}_cashflow"])
            if pc <= 0 or pd <= 0 or cc <= 0 or cd <= 0:
                valid = False
                break
            clean_ret += weights[secid] * (cc / pc - 1.0)
            total_ret += weights[secid] * ((cd + cf) / pd - 1.0)
        if not valid or today < START:
            continue

        clean_returns.append(clean_ret)
        total_returns.append(total_ret)
        clean_pnl = clean_value * clean_ret
        total_pnl = total_value * total_ret
        clean_value += clean_pnl
        total_value += total_pnl

        var_clean_linear = var_total_linear = None
        var_clean_discrete = var_total_discrete = None
        q_clean_linear = q_total_linear = None
        q_clean_discrete = q_total_discrete = None
        if len(clean_returns) >= WINDOW:
            wc = clean_returns[-WINDOW:]
            wt = total_returns[-WINDOW:]
            q_clean_linear = percentile_inc(wc, 0.01)
            q_total_linear = percentile_inc(wt, 0.01)
            q_clean_discrete = sorted(wc)[3]
            q_total_discrete = sorted(wt)[3]
            var_clean_linear = max(0.0, -q_clean_linear) * PORTFOLIO_SIZE
            var_total_linear = max(0.0, -q_total_linear) * PORTFOLIO_SIZE
            var_clean_discrete = max(0.0, -q_clean_discrete) * PORTFOLIO_SIZE
            var_total_discrete = max(0.0, -q_total_discrete) * PORTFOLIO_SIZE

        results.append({
            "Date": today.isoformat(),
            "CleanReturn": clean_ret,
            "TotalReturn": total_ret,
            "CleanPnL": clean_pnl,
            "TotalPnL": total_pnl,
            "CleanValue": clean_value,
            "TotalValue": total_value,
            "CleanVaRLinear": var_clean_linear,
            "TotalVaRLinear": var_total_linear,
            "CleanVaRDiscrete": var_clean_discrete,
            "TotalVaRDiscrete": var_total_discrete,
            "CleanQuantileLinear": q_clean_linear,
            "TotalQuantileLinear": q_total_linear,
            "CleanExceedance": int(var_clean_linear is not None and clean_ret < -(var_clean_linear / PORTFOLIO_SIZE)),
            "TotalExceedance": int(var_total_linear is not None and total_ret < -(var_total_linear / PORTFOLIO_SIZE)),
        })

    final_row = rows[-1]
    for secid in secids:
        trades = [int(float(r[f"{secid}_numtrades"])) for r in rows]
        current[secid] = {
            **meta["metadata"][secid],
            "weight": weights[secid],
            "target_mv": PORTFOLIO_SIZE * weights[secid],
            "clean": float(final_row[f"{secid}_clean"]),
            "dirty": float(final_row[f"{secid}_dirty"]),
            "avg_numtrades": sum(trades) / len(trades),
            "min_numtrades": min(trades),
            "zero_trade_days": sum(1 for x in trades if x == 0),
            "stale_share": meta["quality"][secid]["stale_share"],
            "source": meta["sources"][secid],
        }

    out_headers = list(results[0].keys())
    for old in DATA.glob("backtest_part_*.csv"):
        old.unlink()
    for part_no, start in enumerate(range(0, len(results), PART_SIZE), start=1):
        part = results[start:start + PART_SIZE]
        path = DATA / f"backtest_part_{part_no:02d}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=out_headers)
            writer.writeheader()
            writer.writerows(part)

    summary = {
        "portfolio_size": PORTFOLIO_SIZE,
        "confidence": 0.99,
        "window": WINDOW,
        "start": results[0]["Date"],
        "end": results[-1]["Date"],
        "return_observations": len(results),
        "var_observations": sum(1 for x in results if x["TotalVaRLinear"] is not None),
        "portfolio_dmod": meta["portfolio_dmod"],
        "fixed_share": meta["fixed_share"],
        "short_rate": meta["short_rate"],
        "current_clean_var_linear": results[-1]["CleanVaRLinear"],
        "current_total_var_linear": results[-1]["TotalVaRLinear"],
        "current_clean_var_discrete": results[-1]["CleanVaRDiscrete"],
        "current_total_var_discrete": results[-1]["TotalVaRDiscrete"],
        "current_clean_value": results[-1]["CleanValue"],
        "current_total_value": results[-1]["TotalValue"],
        "max_clean_var_linear": max(x["CleanVaRLinear"] for x in results if x["CleanVaRLinear"] is not None),
        "max_total_var_linear": max(x["TotalVaRLinear"] for x in results if x["TotalVaRLinear"] is not None),
        "max_clean_var_date": max((x for x in results if x["CleanVaRLinear"] is not None), key=lambda x: x["CleanVaRLinear"])["Date"],
        "max_total_var_date": max((x for x in results if x["TotalVaRLinear"] is not None), key=lambda x: x["TotalVaRLinear"])["Date"],
        "clean_exceedances": sum(x["CleanExceedance"] for x in results),
        "total_exceedances": sum(x["TotalExceedance"] for x in results),
        "parts": math.ceil(len(results) / PART_SIZE),
    }
    (DATA / "backtest_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "current_positions.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
