#!/usr/bin/env python3
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SECID='IMOEX2'
DATE_FROM='2022-07-15'
DATE_TO='2026-07-16'
OUT=Path('tmp_imoex2_var/imoex2_history.json')
BASE='https://iss.moex.com/iss'
UA='Mozilla/5.0 (compatible; IMOEX2-VaR-research/1.0)'


def get_json(url, retries=8):
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA})
            with urllib.request.urlopen(req,timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            last=exc
            time.sleep(min(2**attempt,20))
    raise RuntimeError(f'Failed: {url}: {last}')


def fetch_history():
    rows=[]
    start=0
    while True:
        q=urllib.parse.urlencode({
            'from':DATE_FROM,'till':DATE_TO,'start':start,
            'iss.meta':'off','iss.only':'history'
        })
        url=f'{BASE}/history/engines/stock/markets/index/securities/{SECID}.json?{q}'
        p=get_json(url)['history']
        data=p.get('data',[])
        if not data:
            break
        for raw in data:
            rec=dict(zip(p['columns'],raw))
            d=str(rec.get('TRADEDATE',''))[:10]
            close=rec.get('CLOSE')
            if d and close is not None:
                rows.append({
                    'Date':d,'Open':rec.get('OPEN'),'High':rec.get('HIGH'),
                    'Low':rec.get('LOW'),'Close':close,'Value':rec.get('VALUE')
                })
        start += len(data)
        if len(data) < 100:
            break
        time.sleep(0.15)
    by_date={r['Date']:r for r in rows}
    return [by_date[d] for d in sorted(by_date)]


def main():
    rows=fetch_history()
    if len(rows)<900 or rows[-1]['Date']!=DATE_TO:
        raise RuntimeError(f'rows={len(rows)}, last={rows[-1]["Date"] if rows else None}')
    out={
        'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source':'MOEX ISS official index history','secid':SECID,
        'date_from':DATE_FROM,'date_to':DATE_TO,'rows':rows
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(SECID,len(rows),rows[0]['Date'],rows[-1]['Date'],rows[-1]['Close'])

if __name__=='__main__':
    main()
