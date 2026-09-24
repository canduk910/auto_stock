"""cycle351 — 피라미딩 단계 1 「S0 과거 재현」 (읽기 전용, 프로덕션 코드 아님).

명세 = `_workspace/red/cycle351_pyramid_shadow_spec.md` §3.
결과 = `_workspace/domain_consult/cycle351_pyramid_s0_replay.md`.

두 모드로 나뉜다(cycle348 방식). 운영 박스(t4g.small)에서는 **SELECT 만** 하고 계산은 로컬에서 한다.

  dump     (운영 backend 컨테이너 안, DB = os.environ DATABASE_URL):
           python x.py dump /tmp/cycle351_s0_dump.jsonl.gz
           - 세션을 `default_transaction_read_only = on` 으로 연다(쓰기 0건).
           - stock_master(유니버스 판정 필드) · strategy_config · system_config(cash_usage_ratio)
             · daily_performance(total 최근 5행) · kojiro/donchian 실체결 페어(`get_trade_pairs`
             그대로 호출 — 페어링 규약을 재구현하지 않는다) · stock_master_daily(100종목 청크, 전 행)
  analyze  (로컬):
           python x.py analyze <dump> [--leaf src/engine/pyramid_shadow.py] [--json out.json]
           - 새 leaf(`overlay_ladder`·`no_add_flags`·`LadderConfig`·`LADDER_C`·`_build_record`)를
             **파일 경로로** import 한다(운영 이미지에는 아직 없다). S0 Δ 와 S1 Δ 의 정의가 같아진다.
           - 지표 = 저장소 정본 `src.engine.kojiro_indicators.enrich`.
  ladder345 (로컬, 연속성):
           python x.py ladder345 <dump> <cycle345 ladder.py>
           - cycle345 `ladder.py` 원본을 **한 글자도 고치지 않고** `runpy` 로 돌린다. 그 스크립트가
             부르는 `asyncpg.connect` 만 덤프를 읽는 가짜 모듈로 바꿔 끼운다(같은 두 SQL 에 같은 행).

표본 A (문턱 판정용) — kojiro 진입 **대리 조건** = cycle345 `ladder.py` 와 같은 정의
  유니버스 `hts_avls_eok >= 500 ∧ 6자리 숫자` · o/h/l/c > 0 봉만 · 80봉 이상 · 신호봉 i(60 ≤ i < n−1):
  stage==1 ∧ EMA5/20/40 우상향 ∧ 최근 5봉 안 6→1 ∧ ATR/종가 ∈ [1%,6%] ∧ 종가 > EMA5
  ∧ 거래대금 21봉 중앙 ≥ 10억 ∧ 다음 날 갭 ∈ (−4%, +5%) → 진입 = i+1 시가, N = ATR[i](Wilder, 전 이력)
  · 같은 종목 10봉 안 재진입 제거.
1랏 기준선 = kojiro 청산 규약 일봉 재현(cycle346 `simulate` 그대로 + 최대 60봉):
  hard −8% · 2ATR tighten-only floor(D-1 ATR) · 본전 승격 1.5ATR(래치 없음 — cycle346 그대로)
  · 스테이지3 = D-1 완성봉 stage==3 → 당일 시가(진입일 제외) · 2.5ATR 샹들리에 · 60봉째 종가.
  시가가 선 아래면 시가(갭), 아니면 저가가 선에 닿으면 선 가격. 선은 전일까지의 정보로 정한다.

앵커 모드 = 1랏 기준선의 청산(봉·가격)을 앵커로 leaf `overlay_ladder` 를 돌린다 → S1 과 같은 정의의 Δ.
  앵커 날 추가 허용 = 1랏 청산이 장중(선 적중·60봉 종가)일 때만. 스테이지3·갭 청산(시가)이면 False.
  봉은 앵커 봉까지만 넘긴다(S1 이 `bas_dd <= target_date` 로 자르는 것과 같다 → 마지막 봉 추가금지 규칙 동일).
자유 모드 = 스크립트 자체 전체 모의(설계 §4-1): 실효 손절선 = max(세트선 last−2N(k≥2), 평단−2ATR 래칫,
  평단×0.92, 평단 본전 승격(고점 ≥ 평단+1.5ATR), 샹들리에 고점−2.5ATR) + 스테이지3 + 60봉.
  사다리 규칙(D0 금지·추가금지일·갭 스킵 1.05·눈금 = 마지막 체결가 + step×N, N 고정)은 앵커 모드와 같다.
  k=1 이면 1랏 기준선과 한 글자도 다르지 않다(검산으로 확인한다).

R = 1u 랏이 2N 에 손절됐을 때의 손실(= r_unit = 2 × N). virtual_R = Σ size × (청산가 − 체결가) ÷ r_unit.
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import importlib.util
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

STRATS = ("kojiro", "donchian_swing")
CHUNK = 100


# ═══════════════════════════════════ dump (컨테이너) ═══════════════════════════════════

def _jd(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    return str(v)


async def _dump(out_path: str) -> None:
    import asyncpg
    sys.path.insert(0, "/app")

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    # 🔴 timezone 은 운영 풀(`src/db/pg.py::init_pool`)과 같은 Asia/Seoul 로 연다 — `get_trade_pairs` 의
    # `to_char(..., '+09:00')` 는 세션 타임존으로 렌더링한 뒤 +09:00 을 **글자로** 붙인다. UTC 세션이면
    # 체결 시각이 9시간 이르게 찍힌다(이 스크립트 첫 덤프가 실제로 그랬다 — 매도 시각 12:51 이 03:51).
    conn = await asyncpg.connect(dsn, server_settings={"timezone": "Asia/Seoul"})
    await conn.execute("SET default_transaction_read_only = on")
    fh = gzip.open(out_path, "wt", encoding="utf-8")

    def w(obj):
        fh.write(json.dumps(obj, ensure_ascii=False, default=_jd) + "\n")

    try:
        latest = await conn.fetchval("select max(bas_dd) from stock_master_daily")
        w({"kind": "meta", "latest_bas_dd": latest, "dumped_at_kst": datetime.now().isoformat()})

        sc = await conn.fetch("select strategy_id, enabled, weight, params from strategy_config")
        rows = []
        for r in sc:
            p = r["params"]
            if isinstance(p, str):
                p = json.loads(p)
            rows.append({"strategy_id": r["strategy_id"], "enabled": r["enabled"],
                         "weight": float(r["weight"]) if r["weight"] is not None else None,
                         "params": p})
        w({"kind": "strategy_config", "rows": rows})

        sy = await conn.fetch(
            "select key, value from system_config where key in ('cash_usage_ratio','auto_regime_adjust')")
        w({"kind": "system_config",
           "rows": {r["key"]: (json.loads(r["value"]) if isinstance(r["value"], str) else r["value"])
                    for r in sy}})

        dp = await conn.fetch("select * from daily_performance where strategy = 'total'")
        dp = sorted([dict(r) for r in dp], key=lambda d: str(d.get("date") or d.get("trade_date") or ""),
                    reverse=True)[:5]
        w({"kind": "daily_perf_total", "rows": dp})

        ms = await conn.fetch(
            "select ticker, name, hts_avls_eok, acml_tr_pbmn_won from stock_master "
            "where ticker ~ '^[0-9]{6}$'")
        w({"kind": "master", "rows": [[r["ticker"], r["name"], r["hts_avls_eok"], r["acml_tr_pbmn_won"]]
                                      for r in ms]})
        uni = sorted({r["ticker"] for r in ms if (r["hts_avls_eok"] or 0) >= 500})

        # 실체결 페어 — 운영 정본 함수를 그대로 부른다(페어링 규약 재구현 금지).
        # `get_trade_pairs` 는 open 페어 미실현 손익용으로 scanner 를 import 한다 — 한 번 쓰고 버리는
        # 이 프로세스에서 매매 모듈을 끌어오지 않도록 빈 시세 dict 를 가진 가짜 모듈로 막는다.
        # 그 함수의 `pg.fetch` 는 풀을 만들지 않고 **이 읽기 전용 세션**으로 돌린다.
        import types
        stub = types.ModuleType("src.engine.scanner")
        stub.ticker_prices = {}
        sys.modules["src.engine.scanner"] = stub
        from src.db import pg
        from src.db.trade_history import get_trade_pairs

        async def _ro_fetch(sql, *args):
            return [dict(r) for r in await conn.fetch(sql, *args)]

        pg.fetch = _ro_fetch
        ro = await conn.fetchval("show default_transaction_read_only")
        tz = await conn.fetchval("show timezone")
        assert tz == "Asia/Seoul", tz
        pair_tickers = set()
        for sid in STRATS:
            prs = await get_trade_pairs(strategy=sid)
            w({"kind": "pairs", "strategy": sid, "rows": prs})
            pair_tickers |= {p["ticker"] for p in prs if p.get("ticker")}

        tickers = sorted(set(uni) | pair_tickers)
        n_rows = 0
        for ci in range(0, len(tickers), CHUNK):
            chunk = tickers[ci:ci + CHUNK]
            rows = await conn.fetch(
                "select ticker, bas_dd, open_price, high_price, low_price, close_price, volume, "
                "trade_value, flng_cls_code, prtt_rate from stock_master_daily "
                "where ticker = any($1::text[]) order by ticker, bas_dd", chunk)
            by = defaultdict(list)
            for r in rows:
                by[r["ticker"]].append([r["bas_dd"].isoformat(), r["open_price"], r["high_price"],
                                        r["low_price"], r["close_price"], r["volume"], r["trade_value"],
                                        r["flng_cls_code"], float(r["prtt_rate"] or 0)])
            for t in chunk:
                if by.get(t):
                    w({"kind": "daily", "t": t, "rows": by[t]})
                    n_rows += len(by[t])
    finally:
        await conn.close()
    w({"kind": "end", "tickers": len(tickers), "universe_500": len(uni), "pair_tickers": len(pair_tickers),
       "daily_rows": n_rows, "session_read_only": ro, "session_timezone": tz})
    fh.close()
    print(json.dumps({"ok": True, "tickers": len(tickers), "rows": n_rows, "latest": str(latest)}))


# ═══════════════════════════════════ 로딩 ═══════════════════════════════════

def load_dump(path):
    d = {"daily": {}, "pairs": {}}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            k = o["kind"]
            if k == "daily":
                d["daily"][o["t"]] = o["rows"]
            elif k == "pairs":
                d["pairs"][o["strategy"]] = o["rows"]
            else:
                d[k] = o
    return d


def load_leaf(path):
    sys.path.insert(0, REPO)
    spec = importlib.util.spec_from_file_location("pyramid_shadow_s0", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pyramid_shadow_s0"] = mod   # dataclass 가 자기 모듈을 찾는다
    spec.loader.exec_module(mod)
    with open(path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    return mod, sha


# ═══════════════════════════════════ 표본 A 대리 진입 ═══════════════════════════════════

WARM_I = 60
MAXH = 60
HARD = -8.0
STOP_ATR = 2.0
TRAIL = 2.5
BE = 1.5
GAP_SKIP = 1.05


def build_series(dump):
    """ladder.py 와 같은 유니버스(현재 hts_avls_eok ≥ 500) · o/h/l/c>0 봉만 · 80봉 이상."""
    import numpy as np
    import pandas as pd
    from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich
    cfg = KojiroIndicatorConfig(ema_short=5, ema_mid=20, ema_long=40, macd_signal=9, atr_period=20,
                                slope_lookback=1)
    uni = {r[0] for r in dump["master"]["rows"] if (r[2] or 0) >= 500}
    series = {}
    for t in sorted(uni):
        rows = dump["daily"].get(t)
        if not rows:
            continue
        rows = [r for r in rows if r[1] > 0 and r[2] > 0 and r[3] > 0 and r[4] > 0]
        if len(rows) < 80:
            continue
        g = pd.DataFrame({"open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
                          "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows]})
        e = enrich(g, cfg)
        series[t] = dict(
            dates=[date.fromisoformat(r[0]) for r in rows],
            o=g["open"].values, h=g["high"].values, l=g["low"].values, c=g["close"].values,
            tv=np.array([float(r[6]) for r in rows]),
            st=e["stage"].fillna(0).astype(int).values,
            up=(e["ema_s_up"] & e["ema_m_up"] & e["ema_l_up"]).values,
            ema_s=e["ema_s"].values, atr=e["atr"].values,
        )
    return series


def proxy_entries(series):
    import numpy as np
    entries = []
    for t, s in series.items():
        st, up, atr, cl, tv, o = s["st"], s["up"], s["atr"], s["c"], s["tv"], s["o"]
        n = len(cl)
        for i in range(WARM_I, n - 1):
            if st[i] != 1 or not up[i]:
                continue
            if not any(st[k] == 6 and st[k + 1] == 1 for k in range(max(0, i - 5), i)):
                continue
            ar = atr[i] / cl[i]
            if not (0.01 <= ar <= 0.06):
                continue
            if cl[i] <= s["ema_s"][i]:
                continue
            if np.median(tv[max(0, i - 20):i + 1]) < 1e9:
                continue
            gap = (o[i + 1] / cl[i] - 1) * 100
            if gap >= 5 or gap <= -4:
                continue
            entries.append((t, i + 1, float(atr[i])))
    ded, last = [], {}
    for t, i, N in entries:
        if t in last and i - last[t] < 10:
            continue
        last[t] = i
        ded.append((t, i, N))
    return ded, len(entries)


def window_n(s, i0, period=20, window=100):
    """S1 어댑터 방식 진입 N — 매수일 이전 ≤100봉만으로 Wilder ATR(검산용)."""
    import pandas as pd
    lo = max(0, i0 - window)
    h, l, c = s["h"][lo:i0], s["l"][lo:i0], s["c"][lo:i0]
    if len(c) < 2:
        return None
    df = pd.DataFrame({"high": h, "low": l, "close": c})
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


# ═══════════════════════════════════ 1랏 기준선 (cycle346 simulate + 60봉) ═══════════════════════════════════

def baseline(s, t0, a0):
    """cycle346 `simulate` 를 신호봉 t=t0−1, 진입봉 t0 로 옮긴 것 + 최대 60봉(진입봉 포함).

    반환 = (exit_j, exit_px, why) — why ∈ stage3 · gap · line · time · open.
    """
    o, h, l, c, atr, stg = s["o"], s["h"], s["l"], s["c"], s["atr"], s["st"]
    n = len(o)
    t = t0 - 1
    E = float(o[t0])
    pct_line = E * (1 + HARD / 100)
    floor = E - STOP_ATR * a0
    hsb = E
    last_j = min(t0 + MAXH - 1, n - 1)
    for j in range(t0, last_j + 1):
        a = float(atr[j - 1]) if j - 1 >= t else a0
        if j > t0:
            floor = max(floor, E - STOP_ATR * a)
            if stg[j - 1] == 3:
                return j, float(o[j]), "stage3"
        be = E if hsb >= E + BE * a else -1e18
        chand = hsb - TRAIL * a
        lvl = max(pct_line, floor, be, chand)
        if o[j] <= lvl and j > t0:
            return j, float(o[j]), "gap"
        if l[j] <= lvl:
            px = float(min(lvl, o[j])) if j > t0 else float(lvl)
            return j, px, "line"
        hsb = max(hsb, float(h[j]))
    if last_j == t0 + MAXH - 1:
        return last_j, float(c[last_j]), "time"
    return last_j, float(c[last_j]), "open"


# ═══════════════════════════════════ 앵커 모드 — 독립 구현(검산) ═══════════════════════════════════

_STOP_KINDS = {"gap", "set_line", "avg_backstop", "avg_breakeven", "stop_after_add"}


def indep_overlay(bars, E, N, step, sizes, stop_atr, hard_pct, be_mult, be_atr, no_add,
                  anchor_idx, anchor_price, anchor_add_allowed, gap_mult=GAP_SKIP):
    """명세 §1-2 를 문장 그대로 다시 쓴 것 — leaf 코드를 보지 않고 명세만으로 구현한다."""
    r_unit = stop_atr * N
    fills = [(0, E, sizes[0])]
    last, k = E, 1
    hsb = bars[0][2]

    def avg_now():
        q = sum(f[2] for f in fills)
        return sum(f[1] * f[2] for f in fills) / q

    def ladder_line(d):
        av = avg_now()
        A = be_atr[d - 1] if be_atr is not None else N
        terms = [("set_line", last - stop_atr * N), ("avg_backstop", av * (1 + hard_pct / 100.0))]
        if be_mult > 0 and hsb >= av + be_mult * A:
            terms.append(("avg_breakeven", av))
        best = terms[0]
        for tm in terms[1:]:
            if tm[1] > best[1]:
                best = tm
        return best[1], best[0]

    def risk_now():
        ln = (last - stop_atr * N) if k >= 2 else (E - stop_atr * N)
        return sum(f[2] * (f[1] - ln) for f in fills) / r_unit

    peak = risk_now()
    ex = None
    if anchor_idx == 0:
        ex = (0, float(anchor_price), "anchor")
    d = 1
    while ex is None and d < len(bars):
        _, o, h, lo, cl = bars[d]
        is_anchor = anchor_idx is not None and d == anchor_idx
        if k >= 2:
            ln, kind = ladder_line(d)
            px = None
            if o <= ln:
                px, kd = o, "gap"
            elif lo <= ln:
                px, kd = ln, kind
            if px is not None:
                if is_anchor and anchor_price > px:
                    px, kd = anchor_price, "anchor"
                ex = (d, px, kd)
        if ex is None and not no_add[d] and not (is_anchor and not anchor_add_allowed):
            while k < len(sizes):
                lvl = last + step * N
                if o >= lvl * gap_mult:
                    break
                if h < lvl:
                    break
                fp = max(lvl, o)
                fills.append((d, fp, sizes[k]))
                last = fp
                k += 1
                peak = max(peak, risk_now())
                ln2, _ = ladder_line(d)
                if lo <= ln2:
                    px, kd = ln2, "stop_after_add"
                    if is_anchor and anchor_price > px:
                        px, kd = anchor_price, "anchor"
                    ex = (d, px, kd)
                    break
        if ex is None and is_anchor:
            ex = (d, float(anchor_price), "anchor")
        hsb = max(hsb, h)
        d += 1
    if ex is None:
        ex = (len(bars) - 1, float(bars[-1][4]), "open")
    vR = sum(f[2] * (ex[1] - f[1]) for f in fills) / r_unit
    killed = int(k >= 2 and ex[2] in _STOP_KINDS and (anchor_idx is None or ex[0] < anchor_idx))
    return dict(tranches=k, fills=fills, exit_idx=ex[0], exit_price=ex[1], exit_kind=ex[2],
                virtual_R=vR, killed=killed, peak_risk_R=peak,
                set_stop=(last - stop_atr * N) if k >= 2 else None, avg=avg_now())


def _cmp(a, b):
    """leaf `overlay_ladder` 출력과 독립 구현 출력의 레코드 단위 비교 — 다른 필드 이름 목록."""
    bad = [k for k in ("tranches", "exit_idx", "exit_kind", "killed") if a[k] != b[k]]
    for k in ("exit_price", "virtual_R", "peak_risk_R", "avg"):
        if abs(float(a[k]) - float(b[k])) > 1e-6:
            bad.append(k)
    if [(f[0], round(f[1], 6), round(f[2], 9)) for f in a["fills"]] != \
       [(f[0], round(f[1], 6), round(f[2], 9)) for f in b["fills"]]:
        bad.append("fills")
    if (a["set_stop"] is None) != (b["set_stop"] is None) or \
       (a["set_stop"] is not None and abs(a["set_stop"] - b["set_stop"]) > 1e-6):
        bad.append("set_stop")
    return bad


# ═══════════════════════════════════ 자유 모드 ═══════════════════════════════════

def free_sim(s, t0, a0, N, step, sizes, no_add_full):
    """설계 §4-1 전체 모의. k=1 이면 `baseline` 과 같은 결과를 내야 한다.

    a0 = 기준선과 같은 D-1 ATR(래칫 초기값), N = 사다리 고정 N(= a0).
    반환 = dict(exit_j, exit_px, why, fills, tranches, peak_risk_R, virtual_R, set_stop).
    """
    o, h, l, c, atr, stg = s["o"], s["h"], s["l"], s["c"], s["atr"], s["st"]
    n = len(o)
    t = t0 - 1
    E = float(o[t0])
    r_unit = STOP_ATR * N
    fills = [(t0, E, sizes[0])]
    last, k = E, 1

    def avg_now():
        q = sum(f[2] for f in fills)
        return sum(f[1] * f[2] for f in fills) / q

    def risk_now():
        ln = (last - STOP_ATR * N) if k >= 2 else (E - STOP_ATR * N)
        return sum(f[2] * (f[1] - ln) for f in fills) / r_unit

    peak = risk_now()
    floor = E - STOP_ATR * a0
    hsb = E
    last_j = min(t0 + MAXH - 1, n - 1)
    ex = None

    def line(a, av):
        be = av if hsb >= av + BE * a else -1e18
        terms = [av * (1 + HARD / 100), floor, be, hsb - TRAIL * a]
        if k >= 2:
            terms.append(last - STOP_ATR * N)
        return max(terms)

    for j in range(t0, last_j + 1):
        a = float(atr[j - 1]) if j - 1 >= t else a0
        av = avg_now()
        if j > t0:
            floor = max(floor, av - STOP_ATR * a)
            if stg[j - 1] == 3:
                ex = (j, float(o[j]), "stage3")
                break
        lvl = line(a, av)
        if o[j] <= lvl and j > t0:
            ex = (j, float(o[j]), "gap")
            break
        if l[j] <= lvl:
            ex = (j, float(min(lvl, o[j])) if j > t0 else float(lvl), "line")
            break
        if j > t0 and not no_add_full[j]:
            stop_add = False
            while k < len(sizes):
                lv = last + step * N
                if o[j] >= lv * GAP_SKIP or h[j] < lv:
                    break
                fp = max(lv, float(o[j]))
                if not (fp > avg_now() and fp > line(a, avg_now())):   # §3-4 ①③ (구조상 항상 참)
                    break
                fills.append((j, fp, sizes[k]))
                last = fp
                k += 1
                peak = max(peak, risk_now())
                av = avg_now()
                floor = max(floor, av - STOP_ATR * a)
                lv2 = line(a, av)
                if l[j] <= lv2:
                    ex = (j, float(lv2), "stop_after_add")
                    stop_add = True
                    break
            if stop_add:
                break
        hsb = max(hsb, float(h[j]))
    if ex is None:
        ex = (last_j, float(c[last_j]), "time" if last_j == t0 + MAXH - 1 else "open")
    vR = sum(f[2] * (ex[1] - f[1]) for f in fills) / r_unit
    return dict(exit_j=ex[0], exit_px=ex[1], why=ex[2], fills=fills, tranches=k, peak_risk_R=peak,
                virtual_R=vR, set_stop=(last - STOP_ATR * N) if k >= 2 else None)


# ═══════════════════════════════════ 통계 ═══════════════════════════════════

def theo_peak(step, sizes, stop_atr=STOP_ATR):
    """눈금에 정확히 체결됐을 때의 손절 기준 위험 최고치(R) — ladder.py `peak_risk` ÷ 2."""
    pk = 0.0
    for k in range(1, len(sizes) + 1):
        stop = -stop_atr if k == 1 else (k - 1) * step - stop_atr
        pk = max(pk, sum(sizes[j] * (j * step - stop) for j in range(k)))
    return pk / stop_atr


def ci_iid(d, rng, B=4000):
    import numpy as np
    d = np.asarray(d, float)
    bs = d[rng.integers(0, len(d), size=(B, len(d)))].mean(axis=1)
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def ci_cluster(d, keys, rng, B=4000):
    import numpy as np
    g = defaultdict(lambda: [0.0, 0])
    for x, kk in zip(d, keys):
        g[kk][0] += x
        g[kk][1] += 1
    s = np.array([v[0] for v in g.values()])
    c = np.array([v[1] for v in g.values()])
    idx = rng.integers(0, len(s), size=(B, len(s)))
    m = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], int(len(s))


def summarize(recs, base, keys, cost_v, cost_b, peak_theory, rng):
    import numpy as np
    R = np.array([r["virtual_R"] for r in recs])
    B = np.array(base)
    d = R - B
    n = len(R)
    k5 = max(1, n // 20)
    tr = np.array([r["tranches"] for r in recs])
    cl, n_days = ci_cluster(d, keys, rng)
    dc = (R - np.array(cost_v)) - (B - np.array(cost_b))
    scale = 1.0 / peak_theory if peak_theory > 0 else 1.0
    dn = R * scale - B
    return dict(
        n=int(n), mean=float(R.mean()), median=float(np.median(R)), win=float((R > 0).mean()),
        p_le_m1=float((R <= -1).mean()), cvar5=float(np.sort(R)[:k5].mean()), min=float(R.min()),
        tranches_avg=float(tr.mean()), reach2=float((tr >= 2).mean()), reach3=float((tr >= 3).mean()),
        peak_theory=float(peak_theory), peak_obs_mean=float(np.mean([r["peak_risk_R"] for r in recs])),
        peak_obs_max=float(np.max([r["peak_risk_R"] for r in recs])),
        delta=float(d.mean()), ci_iid=ci_iid(d, rng), ci_cluster=cl, cluster_days=n_days,
        conv_base_win_to_loss=float(((B > 0) & (R < 0)).mean()),
        killed=float(np.mean([r["killed"] for r in recs])),
        delta_cost=float(dc.mean()), ci_cluster_cost=ci_cluster(dc, keys, rng)[0],
        delta_norm=float(dn.mean()), ci_cluster_norm=ci_cluster(dn, keys, rng)[0],
    )


def base_summary(base, keys, rng):
    import numpy as np
    B = np.array(base)
    n = len(B)
    return dict(n=int(n), mean=float(B.mean()), median=float(np.median(B)), win=float((B > 0).mean()),
                p_le_m1=float((B <= -1).mean()), cvar5=float(np.sort(B)[:max(1, n // 20)].mean()),
                min=float(B.min()), ci_iid_mean=ci_iid(B, rng), ci_cluster_mean=ci_cluster(B, keys, rng)[0])


def grid():
    out = []
    for step in (0.5, 1.0):
        for ntr in (2, 3):
            for shape in ("eq", "dec"):
                for f in (1 / 3, 2 / 3, 1.0):
                    sizes = tuple(f for _ in range(ntr)) if shape == "eq" else tuple(f / (2 ** j) for j in range(ntr))
                    name = f"s{step:g}N_t{ntr}_{shape}_f{round(f, 2)}"
                    out.append((name, step, sizes))
    return out


# ═══════════════════════════════════ 표본 B — S1 소급 ═══════════════════════════════════

class _FakeDaily:
    """`src.db.stock_master_daily.get_recent_daily(ticker, 400)` 대역 — 덤프의 전 행을 DESC 로 400개."""

    def __init__(self, dump):
        self.d = dump["daily"]

    async def get_recent_daily(self, ticker, days=20):
        rows = self.d.get(ticker) or []
        out = []
        for r in reversed(rows):
            out.append({"ticker": ticker, "bas_dd": date.fromisoformat(r[0]), "open_price": r[1],
                        "high_price": r[2], "low_price": r[3], "close_price": r[4], "volume": r[5],
                        "trade_value": r[6]})
            if len(out) >= min(days, 400):
                break
        return out


def budgets(dump):
    sc = {r["strategy_id"]: r for r in dump["strategy_config"]["rows"]}
    tot = dump["daily_perf_total"]["rows"][0]
    net = None
    for k in ("total_asset", "net_asset", "total_assets", "asset"):
        if tot.get(k) not in (None, ""):
            net = float(tot[k])
            break
    cu = dump["system_config"]["rows"].get("cash_usage_ratio")
    if isinstance(cu, dict):
        cu = cu.get("value")
    cu = float(cu) if cu is not None else 1.0
    wsum = sum(float(r["weight"] or 0) for r in sc.values() if r["enabled"])
    out = {sid: (net * cu * float(sc[sid]["weight"] or 0) / wsum if (net and wsum) else None) for sid in STRATS}
    return out, dict(net=net, cash_usage_ratio=cu, weight_sum_enabled=wsum, perf_row=tot)


def sample_b(dump, leaf):
    sc = {r["strategy_id"]: r for r in dump["strategy_config"]["rows"]}
    params_by_sid = {sid: dict(sc[sid]["params"]) for sid in STRATS if sid in sc}
    bud, bmeta = budgets(dump)
    fake = _FakeDaily(dump)
    latest = date.fromisoformat(str(dump["meta"]["latest_bas_dd"])[:10])
    recs = []
    for sid in STRATS:
        for p in dump["pairs"].get(sid, []):
            if not p.get("buy_date"):
                continue
            bd = date.fromisoformat(str(p["buy_date"]))
            if p.get("status") == "closed" and p.get("sell_date"):
                td = date.fromisoformat(str(p["sell_date"]))
            elif p.get("status") == "open":
                td = latest
            else:
                continue
            rec = asyncio.run(leaf._build_record(sid, p, bd, td, params_by_sid, bud, fake))
            rec = leaf._sanitize(rec)
            rec["_target_date"] = td.isoformat()
            recs.append(rec)
    return recs, params_by_sid, bud, bmeta


def indep_sample_b(dump, rec, params):
    """표본 B 레코드를 명세 §2-2 로 독립 재계산 — 진입 N · 앵커 · 오버레이."""
    import pandas as pd
    sid, tk = rec["strategy"], rec["ticker"]
    bd = date.fromisoformat(rec["buy_date"])
    td = date.fromisoformat(rec["_target_date"])
    rows = [r for r in (dump["daily"].get(tk) or [])][-400:]
    rows = [r for r in rows if date.fromisoformat(r[0]) <= td]
    idx = next((i for i, r in enumerate(rows) if date.fromisoformat(r[0]) == bd), None)
    if idx is None:
        return None
    prior = rows[:idx]
    sim = rows[idx:]
    per = int(params.get("atr_period", 20 if sid == "kojiro" else 14))
    if sid == "kojiro":
        win = prior[-100:]
        allr = win + sim
        df = pd.DataFrame({"high": [float(r[2]) for r in allr], "low": [float(r[3]) for r in allr],
                           "close": [float(r[4]) for r in allr]})
        pc = df["close"].shift(1)
        trr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
        ser = trr.ewm(alpha=1 / per, adjust=False).mean()
        N = float(ser.iloc[len(win) - 1])
        be_atr = [float(x) for x in ser.iloc[len(win):]]
        hard = float(params.get("hard_stop_pct", -8.0))
    else:
        rv = list(reversed(prior))
        if len(rv) <= per + 1:
            return None
        trs = [max(rv[i][2] - rv[i][3], abs(rv[i][2] - rv[i + 1][4]), abs(rv[i][3] - rv[i + 1][4]))
               for i in range(per)]
        N = float(int(sum(trs) / per))
        be_atr = None
        hard = float(params.get("turtle_backstop_pct", -9.0))
    if not N or N <= 0:
        return None
    E = float(rec["entry_price"])
    bars = [(date.fromisoformat(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in sim]
    dates = [b[0] for b in bars]
    no_add = [(dates[i + 1] - dates[i]).days >= 3 for i in range(len(dates) - 1)] + [dates[-1].weekday() == 4]
    a_idx = a_px = None
    allow = True
    if rec["status"] == "closed":
        sd = date.fromisoformat(rec["exit_date"])
        a_idx = next((i for i, b in enumerate(bars) if b[0] == sd), None)
        if a_idx is not None:
            a_px = float(rec["exit_price"])
            allow = str(rec.get("exit_time") or "") >= "09:30:00"
    out = indep_overlay(bars, E, N, 1.0, (2 / 3, 2 / 3, 2 / 3), float(params.get("stop_atr", 2.0)), hard,
                        float(params.get("breakeven_promote_atr", 1.5)), be_atr, no_add, a_idx, a_px, allow)
    out["N"] = N
    return out


# ═══════════════════════════════════ analyze ═══════════════════════════════════

def analyze(dump_path, leaf_path, json_out):
    import numpy as np
    dump = load_dump(dump_path)
    leaf, leaf_sha = load_leaf(leaf_path)
    rng = np.random.default_rng(351)
    series = build_series(dump)
    entries, raw_n = proxy_entries(series)
    res = dict(leaf_path=leaf_path, leaf_sha256=leaf_sha, dump=os.path.basename(dump_path),
               latest_bas_dd=dump["meta"]["latest_bas_dd"], series_tickers=len(series),
               proxy_raw=raw_n, proxy_n=len(entries), proxy_tickers=len({e[0] for e in entries}))
    dates_all = [d for s in series.values() for d in s["dates"]]
    res["period"] = [min(dates_all).isoformat(), max(dates_all).isoformat()]

    # ── 1랏 기준선 + 공통 재료
    E_list, base_R, keys, cost_b, base_ex, rN, winN_diff = [], [], [], [], [], [], []
    for t, i0, N in entries:
        s = series[t]
        j, px, why = baseline(s, i0, N)
        E = float(s["o"][i0])
        E_list.append(E)
        base_R.append((px - E) / (STOP_ATR * N))
        keys.append(s["dates"][i0].isoformat())
        cost_b.append(0.0025 * E / (STOP_ATR * N))
        base_ex.append((j, px, why))
        wn = window_n(s, i0)
        if wn:
            winN_diff.append(abs(wn - N) / N)
    res["base"] = base_summary(base_R, keys, rng)
    res["base_exit_kinds"] = dict(Counter(b[2] for b in base_ex))
    res["windowN_vs_fullN_rel_diff"] = dict(max=float(max(winN_diff)), median=float(np.median(winN_diff)))
    res["entry_days"] = len(set(keys))

    # ── 앵커 모드 (leaf overlay_ladder) + 자유 모드, 격자 전부
    anchor_res, free_res = {}, {}
    cstar_leaf, cstar_meta, cstar_free = [], [], []
    xc_total, xc_bad = 0, []
    free_k1_mismatch = 0
    for name, step, sizes in grid():
        cfg = leaf.LadderConfig(step_n=step, sizes=sizes, gap_skip_mult=GAP_SKIP)
        a_recs, f_recs, cost_va, cost_vf = [], [], [], []
        for (t, i0, N), (j, px, why) in zip(entries, base_ex):
            s = series[t]
            E = float(s["o"][i0])
            bars = [(s["dates"][x], float(s["o"][x]), float(s["h"][x]), float(s["l"][x]), float(s["c"][x]))
                    for x in range(i0, j + 1)]
            flags = leaf.no_add_flags([b[0] for b in bars])
            be_atr = [float(s["atr"][x]) for x in range(i0, j + 1)]
            anchored = why != "open"
            a_idx = (j - i0) if anchored else None
            a_px = px if anchored else None
            allow = why in ("line", "time")
            out = leaf.overlay_ladder(bars, 0, E, N, cfg=cfg, stop_atr=STOP_ATR, hard_stop_pct=HARD,
                                      be_mult=BE, be_atr=be_atr, no_add=flags, anchor_idx=a_idx,
                                      anchor_price=a_px, anchor_add_allowed=allow)
            a_recs.append(out)
            cost_va.append(0.0025 * sum(sz * p for _, p, sz in out["fills"]) / (STOP_ATR * N))
            ind = indep_overlay(bars, E, N, step, sizes, STOP_ATR, HARD, BE, be_atr, flags, a_idx, a_px, allow)
            bad = _cmp(out, ind)
            xc_total += 1
            if bad:
                xc_bad.append(dict(config=name, ticker=t, entry=s["dates"][i0].isoformat(), fields=bad))
            if name == "s1N_t3_eq_f0.67":
                cstar_leaf.append(out)
                cstar_meta.append((t, i0, N, j, px, why, bars, be_atr, a_idx, a_px, allow))
            # 자유 모드 — 추가금지일은 전 이력의 실제 다음 날짜로
            if "flags" not in s:
                s["flags"] = leaf.no_add_flags(s["dates"])
            fr = free_sim(s, i0, N, N, step, sizes, s["flags"])
            base_j = j
            fr["killed"] = int(fr["tranches"] >= 2 and fr["why"] in ("gap", "line", "stop_after_add")
                               and fr["exit_j"] < base_j)
            f_recs.append(fr)
            cost_vf.append(0.0025 * sum(sz * p for _, p, sz in fr["fills"]) / (STOP_ATR * N))
            if name == "s1N_t3_eq_f0.67":
                cstar_free.append(fr)
        pk = theo_peak(step, sizes)
        anchor_res[name] = summarize(a_recs, base_R, keys, cost_va, cost_b, pk, rng)
        anchor_res[name]["exit_kinds"] = dict(Counter(r["exit_kind"] for r in a_recs))
        free_res[name] = summarize(f_recs, base_R, keys, cost_vf, cost_b, pk, rng)
        free_res[name]["exit_kinds"] = dict(Counter(r["why"] for r in f_recs))
        free_res[name]["later_than_base"] = float(np.mean([fr["exit_j"] > b[0] for fr, b in zip(f_recs, base_ex)]))
    res["anchor"] = anchor_res
    res["free"] = free_res

    # ── 자유 모드 k=1 == 기준선 검산
    for (t, i0, N), (j, px, why) in zip(entries, base_ex):
        fr = free_sim(series[t], i0, N, N, 1.0, (1.0,), series[t]["flags"])
        if (fr["exit_j"], round(fr["exit_px"], 6), fr["why"]) != (j, round(px, 6), why):
            free_k1_mismatch += 1
    res["free_k1_vs_base_mismatch"] = free_k1_mismatch

    # ── 독립 검산: 앵커 모드 leaf vs 명세 재구현 (격자 24구성 × 855건 전부)
    res["crosscheck_all"] = dict(records=xc_total, mismatched=len(xc_bad), sample=xc_bad[:10])

    # ── C* 보조 분석
    d_c = np.array([r["virtual_R"] for r in cstar_leaf]) - np.array(base_R)
    d_f = np.array([r["virtual_R"] for r in cstar_free]) - np.array(base_R)
    res["cstar_killed_by_kind"] = dict(Counter(r["exit_kind"] for r in cstar_leaf if r["killed"]))
    res["cstar_ladder_stop_on_anchor_day"] = int(sum(1 for r in cstar_leaf if r["tranches"] >= 2 and
                                                     r["exit_kind"] in _STOP_KINDS and not r["killed"]))
    # (가) 오늘 kojiro 예산으로 사다리가 서는가 — floor(2/3 × 예산 × risk_pct ÷ N) ≥ 2
    bud, _bm = budgets(dump)
    Bk = bud["kojiro"]
    rk = float({r["strategy_id"]: r for r in dump["strategy_config"]["rows"]}["kojiro"]["params"]["risk_pct"])
    elig = np.array([math.floor((2 / 3) * Bk * rk / N) >= 2 for (_t, _i, N) in entries])
    res["cstar_eligible"] = dict(
        budget=round(Bk), risk_pct=rk, share=float(elig.mean()),
        anchor_delta_eligible=float(d_c[elig].mean()),
        anchor_ci_cluster_eligible=ci_cluster(d_c[elig], [k for k, e in zip(keys, elig) if e], rng)[0],
        anchor_delta_blended=float(np.where(elig, d_c, 0.0).mean()),
        anchor_ci_cluster_blended=ci_cluster(np.where(elig, d_c, 0.0), keys, rng)[0],
        free_delta_eligible=float(d_f[elig].mean()),
        free_delta_blended=float(np.where(elig, d_f, 0.0).mean()),
        free_ci_cluster_blended=ci_cluster(np.where(elig, d_f, 0.0), keys, rng)[0],
        killed_eligible=float(np.mean([r["killed"] for r, e in zip(cstar_leaf, elig) if e])))
    # (나) 앵커 봉의 「추가 금지일」을 실제 다음 거래일로 판정했다면(셰도는 요일 근사)
    cfgc = leaf.LADDER_C
    diff_n, dv = 0, []
    kill_true = []
    for (t, i0, N, j, px, why, bars, be_atr, a_idx, a_px, allow), r0 in zip(cstar_meta, cstar_leaf):
        s = series[t]
        true_flags = [s["flags"][x] for x in range(i0, j + 1)]
        out = leaf.overlay_ladder(bars, 0, float(s["o"][i0]), N, cfg=cfgc, stop_atr=STOP_ATR, hard_stop_pct=HARD,
                                  be_mult=BE, be_atr=be_atr, no_add=true_flags, anchor_idx=a_idx,
                                  anchor_price=a_px, anchor_add_allowed=allow)
        dv.append(out["virtual_R"])
        kill_true.append(out["killed"])
        if abs(out["virtual_R"] - r0["virtual_R"]) > 1e-9 or out["tranches"] != r0["tranches"]:
            diff_n += 1
    dvt = np.array(dv) - np.array(base_R)
    res["cstar_true_holiday_flags"] = dict(records_changed=diff_n, delta=float(dvt.mean()),
                                           ci_cluster=ci_cluster(dvt, keys, rng)[0],
                                           killed=float(np.mean(kill_true)))
    # (다) 진입 N 을 S1 어댑터처럼 매수일 이전 ≤100봉으로 잡았다면
    dvw, killw = [], []
    for (t, i0, N, j, px, why, bars, be_atr, a_idx, a_px, allow) in cstar_meta:
        s = series[t]
        wn = window_n(s, i0) or N
        out = leaf.overlay_ladder(bars, 0, float(s["o"][i0]), wn, cfg=cfgc, stop_atr=STOP_ATR, hard_stop_pct=HARD,
                                  be_mult=BE, be_atr=be_atr, no_add=leaf.no_add_flags([b[0] for b in bars]),
                                  anchor_idx=a_idx, anchor_price=a_px, anchor_add_allowed=allow)
        dvw.append(out["virtual_R"] - out["base_R"])
        killw.append(out["killed"])
    res["cstar_windowN"] = dict(delta=float(np.mean(dvw)), ci_cluster=ci_cluster(np.array(dvw), keys, rng)[0],
                                killed=float(np.mean(killw)))
    # (라) 반기 안정성 — 진입일 기준 앞·뒤 절반
    order = np.argsort(keys)
    half = len(order) // 2
    res["cstar_halves"] = {
        nm: dict(n=int(len(ix)), first=keys[ix[0]], last=keys[ix[-1]], anchor_delta=float(d_c[ix].mean()),
                 free_delta=float(d_f[ix].mean()),
                 killed=float(np.mean([cstar_leaf[i]["killed"] for i in ix])))
        for nm, ix in (("early", order[:half]), ("late", order[half:]))}

    # ── 표본 B (실체결 소급) — leaf 어댑터 `_build_record` 그대로 + 독립 재계산 대조
    recs, params_by_sid, bud, bmeta = sample_b(dump, leaf)
    res["B_params"] = {sid: {k: params_by_sid.get(sid, {}).get(k) for k in
                             ("stop_atr", "hard_stop_pct", "turtle_backstop_pct", "breakeven_promote_atr",
                              "atr_period", "risk_pct")} for sid in STRATS}
    res["B_budget"] = {k: (round(v) if v else v) for k, v in bud.items()}
    res["B_budget_meta"] = {k: v for k, v in bmeta.items() if k != "perf_row"}
    res["B_budget_meta"]["perf_row_date"] = bmeta["perf_row"].get("date")
    bstat = {}
    b_mism = []
    for sid in STRATS:
        rr = [r for r in recs if r["strategy"] == sid]
        ok = [r for r in rr if r["error"] is None]
        cf = [r for r in ok if r["status"] == "closed" and r["final"] == 1]
        errs = Counter(r["error"] for r in rr if r["error"] is not None)
        entry = dict(pairs=len(rr), ok=len(ok), errors=dict(errs),
                     open=sum(1 for r in ok if r["status"] == "open"),
                     closed_final=len(cf), killed=sum(r["killed"] for r in cf),
                     tranches=dict(Counter(r["tranches"] for r in cf)),
                     eligible=dict(Counter(str(r["eligible"]) for r in ok)),
                     v_exit_kinds=dict(Counter(r["v_exit_kind"] for r in cf)))
        if cf:
            d = np.array([r["delta_R"] for r in cf])
            A = np.array([r["actual_R"] for r in cf])
            V = np.array([r["virtual_R"] for r in cf])
            entry.update(actual_mean=float(A.mean()), virtual_mean=float(V.mean()), delta_mean=float(d.mean()),
                         delta_ci_iid=ci_iid(d, rng),
                         delta_ci_cluster=ci_cluster(d, [r["buy_date"] for r in cf], rng)[0],
                         delta_pos=int((d > 0).sum()), delta_neg=int((d < 0).sum()), delta_zero=int((d == 0).sum()))
            el = [r for r in cf if r["eligible"] == 1]
            if el:
                de = np.array([r["delta_R"] for r in el])
                entry.update(eligible_closed=len(el), eligible_delta_mean=float(de.mean()))
        bstat[sid] = entry
        for r in ok:
            ind = indep_sample_b(dump, r, params_by_sid[sid])
            if ind is None:
                b_mism.append(dict(ticker=r["ticker"], buy_date=r["buy_date"], why="indep_none"))
                continue
            vr = round(ind["virtual_R"], 4)
            probs = []
            if abs(round(ind["N"], 4) - r["n_entry"]) > 1e-3:
                probs.append(f"n_entry {r['n_entry']} vs {round(ind['N'], 4)}")
            if ind["tranches"] != r["tranches"]:
                probs.append(f"tranches {r['tranches']} vs {ind['tranches']}")
            if abs(vr - r["virtual_R"]) > 2e-4:
                probs.append(f"virtual_R {r['virtual_R']} vs {vr}")
            if ind["exit_kind"] != r["v_exit_kind"]:
                probs.append(f"kind {r['v_exit_kind']} vs {ind['exit_kind']}")
            if ind["killed"] != r["killed"]:
                probs.append(f"killed {r['killed']} vs {ind['killed']}")
            if probs:
                b_mism.append(dict(strategy=sid, ticker=r["ticker"], buy_date=r["buy_date"], diff=probs))
    # ── 표본 B′ — 같은 실체결 kojiro 진입을 S0 1랏 기준선 모형으로 청산시켰다면(청산 모형 대 진입 표본 분리)
    bm = []
    for p in dump["pairs"].get("kojiro", []):
        if p.get("status") != "closed" or p["ticker"] not in series:
            continue
        s_ = series[p["ticker"]]
        bd = date.fromisoformat(p["buy_date"])
        if bd not in s_["dates"]:
            continue
        i0 = s_["dates"].index(bd)
        if i0 < 1:
            continue
        a0 = float(s_["atr"][i0 - 1])
        j, px, why = baseline(s_, i0, a0)
        E = float(s_["o"][i0])
        bars = [(s_["dates"][x], float(s_["o"][x]), float(s_["h"][x]), float(s_["l"][x]), float(s_["c"][x]))
                for x in range(i0, j + 1)]
        anch = why != "open"
        out = leaf.overlay_ladder(bars, 0, E, a0, cfg=leaf.LADDER_C, stop_atr=STOP_ATR, hard_stop_pct=HARD,
                                  be_mult=BE, be_atr=[float(s_["atr"][x]) for x in range(i0, j + 1)],
                                  no_add=leaf.no_add_flags([b[0] for b in bars]),
                                  anchor_idx=(j - i0) if anch else None, anchor_price=px if anch else None,
                                  anchor_add_allowed=why in ("line", "time"))
        bm.append(dict(ticker=p["ticker"], buy_date=p["buy_date"], real_sell=p["sell_date"],
                       model_exit=s_["dates"][j].isoformat(), model_why=why,
                       real_R=(float(p["sell_price"]) - float(p["buy_price"])) / (STOP_ATR * a0),
                       model_base_R=out["base_R"], model_virtual_R=out["virtual_R"],
                       model_delta=out["virtual_R"] - out["base_R"], killed=out["killed"],
                       tranches=out["tranches"]))
    if bm:
        res["B_model"] = dict(
            n=len(bm), same_exit_day=sum(1 for x in bm if x["model_exit"] == x["real_sell"]),
            model_exit_earlier=sum(1 for x in bm if x["model_exit"] < x["real_sell"]),
            model_exit_later=sum(1 for x in bm if x["model_exit"] > x["real_sell"]),
            real_R_mean=float(np.mean([x["real_R"] for x in bm])),
            model_base_R_mean=float(np.mean([x["model_base_R"] for x in bm])),
            model_delta_mean=float(np.mean([x["model_delta"] for x in bm])),
            model_killed=int(sum(x["killed"] for x in bm)), rows=bm)
    res["B_nonfinal_closed"] = [dict(strategy=r["strategy"], ticker=r["ticker"], sell_date=r["exit_date"],
                                     bars_through=r["bars_through"]) for r in recs
                                if r["error"] is None and r["status"] == "closed" and r["final"] != 1]
    res["B"] = bstat
    res["B_crosscheck"] = dict(checked=sum(1 for r in recs if r["error"] is None), mismatched=len(b_mism),
                               sample=b_mism[:15])
    res["B_records"] = [{k: r[k] for k in ("strategy", "ticker", "buy_date", "status", "exit_date", "final",
                                           "n_entry", "actual_R", "virtual_R", "delta_R", "tranches", "add_dates",
                                           "v_exit_kind", "killed", "tranche_shares", "eligible", "error")}
                        for r in recs]
    # JSON 직렬화 가능성(allow_nan=False) — 21:30 INSERT 계약과 같은 검사
    json.dumps([leaf._sanitize(r) for r in recs], allow_nan=False, default=str)
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("proxy_n", "proxy_tickers", "period", "crosscheck_all",
                                          "free_k1_vs_base_mismatch", "B_crosscheck")}, default=str))


# ═══════════════════════════════════ ladder345 (연속성) ═══════════════════════════════════

def ladder345(dump_path, ladder_path):
    import runpy
    import types
    dump = load_dump(dump_path)
    uni = [r[0] for r in dump["master"]["rows"] if (r[2] or 0) >= 500]

    class _Conn:
        async def fetch(self, sql, *args):
            if "from stock_master where" in sql:
                return [{"ticker": t} for t in uni]
            want = set(args[0])
            out = []
            for t in sorted(want):
                for r in dump["daily"].get(t) or []:
                    out.append({"ticker": t, "bas_dd": date.fromisoformat(r[0]), "o": r[1], "h": r[2],
                                "l": r[3], "c": r[4], "tv": r[6]})
            return out

        async def close(self):
            return None

    fake = types.ModuleType("asyncpg")

    async def connect(*_a, **_k):
        return _Conn()

    fake.connect = connect
    sys.modules["asyncpg"] = fake
    sys.path.insert(0, REPO)
    os.environ.setdefault("DATABASE_URL", "postgresql://offline/replay")
    with open(ladder_path, "rb") as fh:
        print("ladder.py sha256", hashlib.sha256(fh.read()).hexdigest())
    runpy.run_path(ladder_path, run_name="__main__")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "dump":
        asyncio.run(_dump(sys.argv[2]))
    elif mode == "analyze":
        leaf_p = os.path.join(REPO, "src", "engine", "pyramid_shadow.py")
        js = "cycle351_s0_result.json"
        a = sys.argv[3:]
        if "--leaf" in a:
            leaf_p = a[a.index("--leaf") + 1]
        if "--json" in a:
            js = a[a.index("--json") + 1]
        sys.path.insert(0, REPO)
        analyze(sys.argv[2], leaf_p, js)
    elif mode == "ladder345":
        ladder345(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown mode {mode}")
