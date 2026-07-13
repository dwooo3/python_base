#!/usr/bin/env python3
# Temporary PR run used only to export official MOEX data as an artifact.
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SECIDS=["SU29007RMFS0","SU29008RMFS8","SU29009RMFS6","SU29010RMFS4","SU29013RMFS8"]
DATE_FROM="2022-07-07"
DATE_TO="2026-07-10"
OUT=Path("tmp_ofz_var/ofz_pk_history.json")
BASE="https://iss.moex.com/iss"
UA="Mozilla/5.0 (compatible; OFZ-PK-VaR-research/1.0)"

def get_json(url,retries=6):
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA})
            with urllib.request.urlopen(req,timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            last=exc; time.sleep(min(2**attempt,20))
    raise RuntimeError(f"Failed: {url}: {last}")

def fetch_description(secid):
    q=urllib.parse.urlencode({"iss.meta":"off","iss.only":"description"})
    p=get_json(f"{BASE}/securities/{secid}.json?{q}")["description"]
    vals={}
    for row in p["data"]:
        rec=dict(zip(p["columns"],row)); vals[str(rec.get("name"))]=rec.get("value")
    keys=["NAME","SHORTNAME","ISIN","ISSUEDATE","STARTDATEMOEX","MATDATE","FACEVALUE","COUPONFREQUENCY","TYPE"]
    return {"SECID":secid,**{k:vals.get(k) for k in keys}}

def fetch_candles(secid):
    rows=[]; start=0
    while True:
        q=urllib.parse.urlencode({"from":DATE_FROM,"till":DATE_TO,"interval":24,"start":start,"iss.meta":"off","iss.only":"candles"})
        p=get_json(f"{BASE}/engines/stock/markets/bonds/securities/{secid}/candles.json?{q}")["candles"]
        data=p.get("data",[])
        if not data: break
        for raw in data:
            rec=dict(zip(p["columns"],raw)); d=str(rec.get("begin", ""))[:10]
            if d and rec.get("close") is not None:
                rows.append({"Date":d,"Open":rec.get("open"),"High":rec.get("high"),"Low":rec.get("low"),"Close":rec.get("close"),"Value":rec.get("value"),"Volume":rec.get("volume")})
        start+=len(data)
        if len(data)<500: break
        time.sleep(0.2)
    by_date={r["Date"]:r for r in rows}
    return [by_date[d] for d in sorted(by_date)]

def main():
    out={"generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"source":"MOEX ISS official market-level daily candles","date_from":DATE_FROM,"date_to":DATE_TO,"interval":24,"securities":{}}
    for secid in SECIDS:
        meta=fetch_description(secid); rows=fetch_candles(secid)
        if len(rows)<375 or rows[-1]["Date"]!=DATE_TO:
            raise RuntimeError(f"{secid}: rows={len(rows)}, last={rows[-1]['Date'] if rows else None}")
        out["securities"][secid]={"meta":meta,"rows":rows}
        print(secid,len(rows),rows[0]["Date"],rows[-1]["Date"],rows[-1]["Close"])
        time.sleep(0.3)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Wrote",OUT,OUT.stat().st_size)

if __name__=="__main__": main()
