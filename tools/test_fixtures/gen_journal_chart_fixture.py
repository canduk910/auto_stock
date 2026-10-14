"""cycle457 — 거래일지 차트 MSW·e2e 고정 응답 생성기.

지표 값은 실제 전략 객체(코드 기본값)의 `chart_indicators` + 라우트 `_sanitize` 로 낸다 — 손으로 쓰지 않는다.
실행 = 저장소 루트에서 `python tools/test_fixtures/gen_journal_chart_fixture.py 100000`
(인자 = 변동성 돌파 카드 종목의 기준 가격). 출력 = `frontend/src/test/fixtures/journalChart.fixture.ts`.
"""
import json, math, sys
from datetime import date, timedelta
sys.path.insert(0, '.')
import os
for k in ("KIS_APP_KEY_REAL","KIS_APP_SECRET_REAL","KIS_ACCOUNT_NO_REAL","KIS_APP_KEY_VTS","KIS_APP_SECRET_VTS","KIS_ACCOUNT_NO_VTS","SUPABASE_URL","SUPABASE_KEY","DATABASE_URL","OPENAI_API_KEY"):
    os.environ.setdefault(k, "x")
from src.engine.strategy_base import StrategyConfig
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.routes.journal_chart import _sanitize, _start_index

def weekdays(end, n):
    out=[]; d=end
    while len(out)<n:
        if d.weekday()<5: out.append(d)
        d-=timedelta(days=1)
    return out[::-1]

def bars_for(base):
    out=[]; prev=base
    for i,d in enumerate(weekdays(date(2026,10,9), 200)):
        c=round(base*(1+0.08*math.sin(i/9)+0.0015*(i-150)) + (-base*0.01 if i%3==0 else base*0.006))
        o=round(prev*(1.004 if i%2==0 else 0.996))
        h=max(o,c)+round(base*0.01); l=min(o,c)-round(base*0.01)
        prev=c
        out.append({"date":d.isoformat(),"open":o,"high":h,"low":l,"close":c,"volume":100000+i*1000,"amount":c*(100000+i*1000)})
    return out

specs = {"kojiro":(KojiroStrategy,"035720","카카오",50000,"2026-10-05"),
       "bull_flag_breakout":(BullFlagBreakoutStrategy,"247540","에코프로비엠",12500,"2026-10-05"),
       "volatility_breakout":(VolatilityBreakoutStrategy,"000660","SK하이닉스",int(sys.argv[1]) if len(sys.argv)>1 else 200000,"2026-10-06")}
res = {}
for sid,(cls,t,name,base,frm) in specs.items():
    s=cls(StrategyConfig(strategy_id=sid,name=sid,params={},enabled=True))
    bars=bars_for(base)
    st=_start_index(bars, frm)
    ind=_sanitize(s.chart_indicators(bars, st), len(bars))
    res[sid]={"ticker":t,"name":name,"period":"D","years":5,"adjusted":True,"market":"J",
      "start_date":bars[0]["date"],"end_date":bars[-1]["date"],"bars":bars,"complete":True,"incomplete_reason":None,
      "last_bar_provisional":False,"dropped_bars":0,"kis_calls":1,"cached":False,"fetched_at":"2026-10-09T21:00:00+09:00",
      "strategy":sid,"indicators":ind,"indicator_source":"engine","indicator_start_index":st}
out='''/**
 * cycle457 — `GET /api/journal-chart` 고정 응답(MSW · e2e 공용). 전략별 1건.
 *
 * 손으로 쓴 값이 아니다 — `tools/test_fixtures/gen_journal_chart_fixture.py` 가 합성 일봉 200봉에 **실제 전략 객체**
 * (`KojiroStrategy`·`BullFlagBreakoutStrategy`·`VolatilityBreakoutStrategy`, 코드 기본값)의 `chart_indicators`
 * 와 라우트의 `_sanitize` 를 돌려 만든 것이다. 날짜는 거래일지 고정 카드(10-05~10-08 매매)를 덮는다.
 */
import type { JournalChartData } from '../../types/journal-chart'

export const JOURNAL_CHART_FIXTURE: Record<string, JournalChartData> = ''' + json.dumps(res, ensure_ascii=False) + " as Record<string, JournalChartData>\n"
open('frontend/src/test/fixtures/journalChart.fixture.ts','w').write(out)
print({k:[l["key"] for l in v["indicators"]["lines"]] for k,v in res.items()})
