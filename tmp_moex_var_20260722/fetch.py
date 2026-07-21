#!/usr/bin/env python3
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from pathlib import Path

DATE_FROM='2022-07-15'
DATE_TO='2026-07-21'
OUT=Path('tmp_moex_var_20260722/history.json')
BASE='https://iss.moex.com/iss'
UA='Mozilla/5.0 (compatible; MOEX-VaR-automation/1.0)'
INDEXES=['IMOEX','IMOEX2']
BONDS={
 'OFZ_PD':['SU26225RMFS1','SU26230RMFS1','SU26233RMFS5','SU26238RMFS4','SU26240RMFS0'],
 'OFZ_PK':['SU29007RMFS0','SU29008RMFS8','SU29009RMFS6','SU29010RMFS4','SU29013RMFS8']
}

def get_json(url,retries=8):
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA})
            with urllib.request.urlopen(req,timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            last=exc; time.sleep(min(2**attempt,20))
    raise RuntimeError(f'Failed {url}: {last}')

def fetch(endpoint):
    rows=[]; start=0
    while True:
        q=urllib.parse.urlencode({'from':DATE_FROM,'till':DATE_TO,'start':start,'iss.meta':'off','iss.only':'history'})
        p=get_json(f'{BASE}/{endpoint}.json?{q}')['history']
        data=p.get('data',[])
        if not data: break
        for raw in data:
            rec=dict(zip(p['columns'],raw)); d=str(rec.get('TRADEDATE',''))[:10]
            close=rec.get('CLOSE')
            if d and close is not None:
                rows.append({'Date':d,'Open':rec.get('OPEN'),'High':rec.get('HIGH'),'Low':rec.get('LOW'),'Close':close,'Value':rec.get('VALUE'),'Volume':rec.get('VOLUME')})
        start += len(data)
        if len(data)<100: break
        time.sleep(0.1)
    by={r['Date']:r for r in rows}
    return [by[d] for d in sorted(by)]

def main():
    out={'requested_to':DATE_TO,'indexes':{},'bonds':{}}
    for secid in INDEXES:
        rows=fetch(f'history/engines/stock/markets/index/securities/{secid}')
        if len(rows)<900: raise RuntimeError(f'{secid}: only {len(rows)} rows')
        out['indexes'][secid]={'rows':rows,'actual_to':rows[-1]['Date']}
        print(secid,len(rows),rows[-1]['Date'],rows[-1]['Close'])
    for group,secids in BONDS.items():
        out['bonds'][group]={}
        for secid in secids:
            rows=fetch(f'history/engines/stock/markets/bonds/boards/TQOB/securities/{secid}')
            if len(rows)<900: raise RuntimeError(f'{secid}: only {len(rows)} rows')
            out['bonds'][group][secid]={'rows':rows,'actual_to':rows[-1]['Date']}
            print(secid,len(rows),rows[-1]['Date'],rows[-1]['Close'])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

if __name__=='__main__': main()
