#!/usr/bin/env python3
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATE_FROM='2022-07-15'
DATE_TO='2026-07-16'
OUT=Path('tmp_imoex2_var/imoex2_history.json')
BASE='https://iss.moex.com/iss'
UA='Mozilla/5.0 (compatible; MOEX-VaR-research/1.0)'
INDICES=['IMOEX','IMOEX2']
BONDS={
 'OFZ_PD':['SU26225RMFS1','SU26230RMFS1','SU26233RMFS5','SU26238RMFS4','SU26240RMFS0'],
 'OFZ_PK':['SU29007RMFS0','SU29008RMFS8','SU29009RMFS6','SU29010RMFS4','SU29013RMFS8'],
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
    raise RuntimeError(f'Failed: {url}: {last}')

def paged(url_base,params):
    rows=[]; start=0
    while True:
        q=dict(params); q['start']=start; q['iss.meta']='off'; q['iss.only']='history'
        p=get_json(url_base+'?'+urllib.parse.urlencode(q))['history']
        data=p.get('data',[])
        if not data: break
        rows.extend(dict(zip(p['columns'],raw)) for raw in data)
        start += len(data)
        if len(data)<100: break
        time.sleep(0.12)
    return rows

def fetch_index(secid):
    url=f'{BASE}/history/engines/stock/markets/index/securities/{secid}.json'
    raw=paged(url,{'from':DATE_FROM,'till':DATE_TO})
    out=[]
    for rec in raw:
        d=str(rec.get('TRADEDATE',''))[:10]; close=rec.get('CLOSE')
        if d and close is not None:
            out.append({'Date':d,'Open':rec.get('OPEN'),'High':rec.get('HIGH'),'Low':rec.get('LOW'),'Close':close,'Value':rec.get('VALUE')})
    return sorted({r['Date']:r for r in out}.values(),key=lambda r:r['Date'])

def fetch_bond(secid):
    url=f'{BASE}/history/engines/stock/markets/bonds/boards/TQOB/securities/{secid}.json'
    raw=paged(url,{'from':DATE_FROM,'till':DATE_TO})
    out=[]
    for rec in raw:
        d=str(rec.get('TRADEDATE',''))[:10]
        close=rec.get('CLOSE'); legal=rec.get('LEGALCLOSEPRICE'); wap=rec.get('WAPRICE')
        clean=close if close is not None else (legal if legal is not None else wap)
        if d and clean is not None:
            out.append({'Date':d,'Close':close,'LegalClose':legal,'WAPrice':wap,'CleanPrice':clean,'FaceValue':rec.get('FACEVALUE') or 1000})
    return sorted({r['Date']:r for r in out}.values(),key=lambda r:r['Date'])

def main():
    indices={s:fetch_index(s) for s in INDICES}
    bonds={group:{s:fetch_bond(s) for s in secs} for group,secs in BONDS.items()}
    latest={s:(rows[-1]['Date'] if rows else None) for s,rows in indices.items()}
    for group,items in bonds.items():
        latest[group]={s:(rows[-1]['Date'] if rows else None) for s,rows in items.items()}
    payload={'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source':'MOEX ISS official history','date_from':DATE_FROM,'requested_date_to':DATE_TO,'indices':indices,'bonds':bonds,'latest':latest}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(latest,ensure_ascii=False))

if __name__=='__main__': main()
