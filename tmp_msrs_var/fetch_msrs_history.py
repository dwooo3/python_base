#!/usr/bin/env python3
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATE_FROM='2022-07-15'
DATE_TO='2026-07-17'
OUT=Path('tmp_msrs_var/moex_var_history.json')
BASE='https://iss.moex.com/iss'
UA='Mozilla/5.0 (compatible; MOEX-VaR-research/1.0)'

INDEXES={'IMOEX':'SNDX','IMOEX2':'SNDX'}
BONDS={
    'OFZ_PD':['SU26225RMFS1','SU26230RMFS1','SU26233RMFS5','SU26238RMFS4','SU26240RMFS0'],
    'OFZ_PK':['SU29007RMFS0','SU29008RMFS8','SU29009RMFS6','SU29010RMFS4','SU29013RMFS8'],
}

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

def fetch_history(market, board, secid, columns):
    rows=[]; start=0
    while True:
        q=urllib.parse.urlencode({
            'from':DATE_FROM,'till':DATE_TO,'start':start,
            'iss.meta':'off','iss.only':'history',
            'history.columns':columns
        })
        url=(f'{BASE}/history/engines/stock/markets/{market}/boards/{board}/'
             f'securities/{secid}.json?{q}')
        p=get_json(url)['history']; data=p.get('data',[])
        if not data: break
        for raw in data:
            rec=dict(zip(p['columns'],raw)); d=str(rec.get('TRADEDATE',''))[:10]
            if d and rec.get('CLOSE') is not None:
                rows.append({k.title():v for k,v in rec.items()})
                rows[-1]['Date']=d
        start += len(data)
        if len(data)<100: break
        time.sleep(0.1)
    by_date={r['Date']:r for r in rows}
    return [by_date[d] for d in sorted(by_date)]

def main():
    out={'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
         'source':'MOEX ISS official history','date_from':DATE_FROM,
         'requested_date_to':DATE_TO,'indexes':{},'bonds':{}}
    for secid,board in INDEXES.items():
        rows=fetch_history('index',board,secid,'TRADEDATE,OPEN,HIGH,LOW,CLOSE')
        if len(rows)<900: raise RuntimeError(f'Insufficient {secid} rows={len(rows)}')
        out['indexes'][secid]={'secid':secid,'board':board,'actual_date_to':rows[-1]['Date'],'rows':rows}
        print(secid,len(rows),rows[0]['Date'],rows[-1]['Date'],rows[-1]['Close'])
    for group,secids in BONDS.items():
        out['bonds'][group]={}
        for secid in secids:
            rows=fetch_history('bonds','TQOB',secid,'TRADEDATE,OPEN,HIGH,LOW,CLOSE,VALUE,VOLUME,NUMTRADES')
            if len(rows)<850: raise RuntimeError(f'Insufficient {secid} rows={len(rows)}')
            out['bonds'][group][secid]={'secid':secid,'board':'TQOB','actual_date_to':rows[-1]['Date'],'rows':rows}
            print(group,secid,len(rows),rows[0]['Date'],rows[-1]['Date'],rows[-1]['Close'])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

if __name__=='__main__': main()
