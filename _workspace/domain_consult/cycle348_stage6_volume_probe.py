"""cycle348 — `[kojiro_macd_observe] role=stage6_gc` 기록량 오프라인 추정 (읽기 전용).

두 모드로 나뉜다. 운영 박스(t4g.small)에서는 **SELECT 만** 하고, 지표 계산은 로컬에서 한다
— 장중(애프터마켓 16:00~20:00 포함) 실매매 프로세스와 CPU 를 다투지 않기 위해서다.
prepare() 나 KIS 호출은 어느 모드에서도 하지 않는다.

  dump    (운영 backend 컨테이너 안, DB=os.environ DATABASE_URL):
          python x.py dump /tmp/cycle348_dump.jsonl.gz
          - strategy_config(kojiro).params · system_config(price_filter_*) · stock_master(유니버스
            판정 필드) · stock_master_daily(최근 ~180 영업일 OHLCV + 락 표시 + 거래대금)
            · strategy_funnel_snapshots(kojiro, 단계별 survived_count — 재현 정합 대조용)
  analyze (로컬, 저장소 정본 `src.engine.kojiro_indicators.enrich` 사용):
          python x.py analyze <dump> [--days 60]

재현 규칙 (`KojiroStrategy.prepare` 대응)
- 창 = 그 봉 날짜 d 까지의 **최근 100행**(`get_recent_daily(ticker, 100)`), 80행 미만이면 제외
  (운영은 KIS 폴백을 타지만 KIS 도 상장 이력이 짧으면 80 미만이라 같은 결과).
- OHLC = raw JSONB `stck_*` (없으면 컬럼), open 0 이면 close (`_build_ohlc_df` 와 같다).
- step5 = ATR/종가 ∈ [atr_ratio_min, atr_ratio_max] (운영 DB 값), step6 = stage 판별 가능.
- 조건 = stage == 6 ∧ gc3(직전봉 macd3 <= sig3 ∧ 이번봉 macd3 > sig3, `_macd_observe_row` 와 같은 식).
- 유니버스 두 변형(과거 시점의 stock_master 가 남아 있지 않아 근사할 수밖에 없다):
    U_static  = 지금 stock_master 로 판정(시총 억 ≥ ceil(min_market_cap/1e8) ∧ acml_tr_pbmn_won
                ≥ min_trade_amount) — 모든 날짜에 같은 집합
    U_dynamic = 날짜별 판정(시총_d ≈ 지금 시총 × close_d / close_최신, 거래대금_d = 그 봉의
                acml_tr_pbmn ≥ min_trade_amount)
  공통 = 6자리 숫자 · ETF 키워드 제외 · exclude_tickers · 1단계 진입 차단(지금 플래그) ·
         가격 필터(price_filter_min/max, 지금 값).
- 락 행(flng_cls_code≠00 or prtt_rate≠0)이 창 안에 있으면 운영은 KIS(수정주가) 폴백을 탄다.
  DB 행으로 계산하되 31% 초과 불연속이 창 안에 있으면 그 종목-날짜는 제외하고 따로 센다.
- 일일 cap = 60 (STAGE6_GC_DAILY_LIMIT). 줄 수 = min(사건 수, 60) + (초과 시 요약 1줄).
"""
from __future__ import annotations

import gzip
import json
import math
import os
import sys
from collections import Counter, defaultdict

ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")  # = src/engine/scanner.py:494

WINDOW = 100          # KOJIRO_FETCH_DAYS
MIN_REQ = 80          # KOJIRO_MIN_REQUIRED
DAILY_LIMIT = 60      # STAGE6_GC_DAILY_LIMIT
HIST_TRADING_DAYS = 185   # 60 목표일 + 100 창 + 여유


# ───────────────────────────── dump (컨테이너) ─────────────────────────────

async def _dump(out_path: str) -> None:
    import asyncpg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET default_transaction_read_only = on")
        sc = await conn.fetchrow("select params, enabled, weight from strategy_config where strategy_id='kojiro'")
        params = sc["params"] if sc else {}
        if isinstance(params, str):
            params = json.loads(params)
        pf = await conn.fetch("select key, value from system_config where key like 'price_filter%'")
        pf_d = {r["key"]: (json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]) for r in pf}

        masters = await conn.fetch(
            "select ticker, COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') as name, "
            "hts_avls_eok, acml_tr_pbmn_won, "
            "raw->>'bfdy_clpr' as bfdy_clpr, raw->>'mrkt_warn_cls_code' as mrkt_warn_cls_code, "
            "raw->>'short_over_yn' as short_over_yn, raw->>'sltr_yn' as r_sltr_yn, "
            "raw->>'temp_stop_yn' as temp_stop_yn, "
            "master_raw->>'trht_yn' as trht_yn, master_raw->>'sltr_yn' as m_sltr_yn, "
            "master_raw->>'mang_issu_yn' as mang_issu_yn, master_raw->>'ssts_hot_yn' as ssts_hot_yn, "
            "master_raw->>'stange_runup_yn' as stange_runup_yn, "
            "master_raw->>'mrkt_alrm_cls_code' as mrkt_alrm_cls_code, "
            "master_raw->>'invt_alrm_yn' as invt_alrm_yn "
            "from stock_master")
        latest = await conn.fetchval("select max(bas_dd) from stock_master_daily")
        cal = await conn.fetch(
            "select bas_dd, count(*) n from stock_master_daily where bas_dd > $1::date - 400 "
            "group by bas_dd order by bas_dd", latest)
        cal = [r for r in cal if r["n"] >= 300]
        cutoff = cal[-HIST_TRADING_DAYS]["bas_dd"] if len(cal) >= HIST_TRADING_DAYS else cal[0]["bas_dd"]

        # 데이터 대상 = 6자리 숫자 · ETF 제외 · 시총 ≥ 임계의 절반(과거 시총 변동 여유)
        thr_eok = (int(params.get("min_market_cap", 50_000_000_000)) + 99_999_999) // 100_000_000
        want = []
        for m in masters:
            t = m["ticker"] or ""
            if not (len(t) == 6 and t.isdigit()):
                continue
            if any(k in (m["name"] or "") for k in ETF_KEYWORDS):
                continue
            if (m["hts_avls_eok"] or 0) < thr_eok // 2:
                continue
            want.append(t)

        funnel = await conn.fetch(
            "select target_date, step_no, survived_count, snapshot_at, is_provisional "
            "from strategy_funnel_snapshots where strategy_id='kojiro' and target_date >= $1 "
            "order by target_date, step_no, snapshot_at", cutoff)

        n_rows = 0
        with gzip.open(out_path, "wt", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "meta", "params": params, "enabled": sc["enabled"] if sc else None,
                                "weight": float(sc["weight"]) if sc and sc["weight"] is not None else None,
                                "price_filter": pf_d, "latest": str(latest), "cutoff": str(cutoff),
                                "calendar": [[str(r["bas_dd"]), r["n"]] for r in cal]},
                               ensure_ascii=False, default=str) + "\n")
            for m in masters:
                f.write(json.dumps({"kind": "master", **{k: m[k] for k in m.keys()}},
                                   ensure_ascii=False, default=str) + "\n")
            for r in funnel:
                f.write(json.dumps({"kind": "funnel", **{k: r[k] for k in r.keys()}},
                                   ensure_ascii=False, default=str) + "\n")
            CH = 150
            for i in range(0, len(want), CH):
                chunk = want[i:i + CH]
                rows = await conn.fetch(
                    "select ticker, bas_dd, raw->>'stck_oprc' o, raw->>'stck_hgpr' h, raw->>'stck_lwpr' l, "
                    "raw->>'stck_clpr' c, raw->>'acml_tr_pbmn' tv, open_price, high_price, low_price, "
                    "close_price, trade_value, flng_cls_code, prtt_rate "
                    "from stock_master_daily where ticker = any($1::text[]) and bas_dd >= $2 "
                    "order by ticker, bas_dd", chunk, cutoff)
                by = defaultdict(list)
                for r in rows:
                    def _i(v, fb):
                        try:
                            return int(v) if v not in (None, "") else int(fb or 0)
                        except (TypeError, ValueError):
                            return int(fb or 0)
                    lock = (str(r["flng_cls_code"] or "").strip() not in ("", "00")) or \
                        abs(float(r["prtt_rate"] or 0)) > 1e-9
                    by[r["ticker"]].append([
                        r["bas_dd"].strftime("%Y%m%d"),
                        _i(r["o"], r["open_price"]), _i(r["h"], r["high_price"]),
                        _i(r["l"], r["low_price"]), _i(r["c"], r["close_price"]),
                        _i(r["tv"], r["trade_value"]), int(lock),
                    ])
                for t, lst in by.items():
                    f.write(json.dumps({"kind": "daily", "t": t, "rows": lst}, separators=(",", ":")) + "\n")
                    n_rows += len(lst)
        print(json.dumps({"out": out_path, "masters": len(masters), "want": len(want), "daily_rows": n_rows,
                          "latest": str(latest), "cutoff": str(cutoff), "funnel_rows": len(funnel),
                          "params_keys": sorted(params.keys())}, ensure_ascii=False))
    finally:
        await conn.close()


# ───────────────────────────── analyze (로컬) ─────────────────────────────

def _blocked(m: dict) -> bool:
    """= src/engine/scanner.py::_is_master_blocked_for_entry (지금 플래그)."""
    if (m.get("trht_yn") == "Y" or m.get("m_sltr_yn") == "Y" or m.get("mang_issu_yn") == "Y"
            or m.get("ssts_hot_yn") == "Y" or m.get("stange_runup_yn") == "Y"):
        return True
    ma = m.get("mrkt_alrm_cls_code")
    if isinstance(ma, str) and ma >= "02":
        return True
    if m.get("invt_alrm_yn") == "Y":
        return True
    mw = m.get("mrkt_warn_cls_code")
    if isinstance(mw, str) and mw >= "02":
        return True
    for k in ("short_over_yn", "r_sltr_yn", "temp_stop_yn"):
        if (m.get(k) or "").strip().upper() == "Y":
            return True
    return False


def _analyze(path: str, n_days: int) -> None:
    import numpy as np
    import pandas as pd

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich

    meta, masters, funnel, daily = None, {}, [], {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            k = o.pop("kind")
            if k == "meta":
                meta = o
            elif k == "master":
                masters[o["ticker"]] = o
            elif k == "funnel":
                funnel.append(o)
            elif k == "daily":
                daily[o["t"]] = o["rows"]

    p = meta["params"]
    atr_min = float(p.get("atr_ratio_min", 0.01))
    atr_max = float(p.get("atr_ratio_max", 0.06))
    mcap_thr = (int(p.get("min_market_cap", 50_000_000_000)) + 99_999_999) // 100_000_000
    trade_thr = int(p.get("min_trade_amount", 1_000_000_000))
    excl = set(p.get("exclude_tickers") or [])
    pf = meta.get("price_filter") or {}

    def _pf(key):
        v = pf.get(key)
        if isinstance(v, dict):
            v = v.get("value")
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0
    pmin, pmax = _pf("price_filter_min"), _pf("price_filter_max")
    # _ind_cfg 는 __init__ 의 코드 기본값 병합으로 만들어진다(DB params 로 재생성하지 않음).
    cfg = KojiroIndicatorConfig()
    cal = [d.replace("-", "") for d, n in meta["calendar"]]
    targets = cal[-n_days:]
    tset = set(targets)

    def price_ok(px):
        if px <= 0:
            return True
        if pmin > 0 and px < pmin:
            return False
        if pmax > 0 and px > pmax:
            return False
        return True

    # 공통 정적 게이트
    base_ok = {}
    for t, m in masters.items():
        if not (len(t) == 6 and t.isdigit()):
            continue
        if any(kw in (m.get("name") or "") for kw in ETF_KEYWORDS):
            continue
        if t in excl:
            continue
        base_ok[t] = not _blocked(m)
    static_uni = {t for t, m in masters.items() if t in base_ok and base_ok[t]
                  and (m.get("hts_avls_eok") or 0) >= mcap_thr
                  and (m.get("acml_tr_pbmn_won") or 0) >= trade_thr
                  and price_ok(int(m.get("bfdy_clpr") or 0))}

    per_day = {d: dict(static=[], dynamic=[], loose=[], s_band=0, s_stage6=0, d_band=0, d_stage6=0,
                       d_uni=0, s_uni_eval=0, jump_skip=0, lock_win_events=0, short=0)
               for d in targets}
    diag = Counter()
    for t, rows in daily.items():
        if t not in base_ok:
            continue
        if not base_ok[t]:
            diag["blocked_now"] += 1
            continue
        m = masters[t]
        dates = [r[0] for r in rows]
        idx_of = {d: i for i, d in enumerate(dates)}
        o = np.array([r[1] for r in rows], float)
        h = np.array([r[2] for r in rows], float)
        l = np.array([r[3] for r in rows], float)
        c = np.array([r[4] for r in rows], float)
        tv = np.array([r[5] for r in rows], float)
        lk = np.array([r[6] for r in rows], int)
        o = np.where(o > 0, o, c)
        last_close = c[-1] if c[-1] > 0 else None
        mcap_now = float(m.get("hts_avls_eok") or 0)
        for d in targets:
            i = idx_of.get(d)
            if i is None:
                diag["no_row_on_day"] += 1
                continue
            lo = max(0, i - WINDOW + 1)
            if i - lo + 1 < MIN_REQ:
                per_day[d]["short"] += 1
                continue
            cw = c[lo:i + 1]
            if cw[-1] <= 0:
                continue
            in_static = t in static_uni
            mcap_d = mcap_now * (cw[-1] / last_close) if last_close else 0.0
            in_dyn = (mcap_d >= mcap_thr) and (tv[i] >= trade_thr) and price_ok(int(c[i]))
            if in_dyn:
                per_day[d]["d_uni"] += 1
            if in_static:
                per_day[d]["s_uni_eval"] += 1
            prev = cw[:-1]
            with np.errstate(divide="ignore", invalid="ignore"):
                jump = np.nanmax(np.abs(cw[1:] / np.where(prev > 0, prev, np.nan) - 1)) if len(cw) > 1 else 0
            df = pd.DataFrame({"open": o[lo:i + 1].astype(int), "high": h[lo:i + 1].astype(int),
                               "low": l[lo:i + 1].astype(int), "close": cw.astype(int),
                               "volume": np.zeros(i - lo + 1, int)})
            e = enrich(df, cfg)
            last = e.iloc[-1]
            prev_close = int(last["close"])
            if prev_close <= 0:
                continue
            atr_val = float(last["atr"])
            ratio = atr_val / prev_close
            if not (atr_min <= ratio <= atr_max):
                continue
            stage = last["stage"]
            if stage is None or (isinstance(stage, float) and math.isnan(stage)):
                continue
            stage = int(stage)
            if in_static:
                per_day[d]["s_band"] += 1
            if in_dyn:
                per_day[d]["d_band"] += 1
            if stage != 6:
                continue
            if in_static:
                per_day[d]["s_stage6"] += 1
            if in_dyn:
                per_day[d]["d_stage6"] += 1
            m3 = e["macd3"]
            s3 = e["macd3_sig"]
            li = len(m3) - 1
            gc3 = (not (float(m3.iloc[li - 1]) > float(s3.iloc[li - 1]))) and (float(m3.iloc[li]) > float(s3.iloc[li]))
            if not gc3:
                continue
            if jump > 0.31:
                per_day[d]["jump_skip"] += 1
                continue
            if lk[lo:i + 1].any():
                per_day[d]["lock_win_events"] += 1
            per_day[d]["loose"].append(t)
            if in_static:
                per_day[d]["static"].append(t)
            if in_dyn:
                per_day[d]["dynamic"].append(t)

    # 운영 funnel 대조 (target_date = prepare 날짜 P, 봉 = P 직전 영업일)
    fun = defaultdict(dict)
    for r in funnel:
        td = str(r["target_date"]).replace("-", "")
        fun[td][int(r["step_no"])] = int(r["survived_count"])  # 같은 날 여러 스냅샷이면 마지막(정렬 순)
    next_day = {cal[i]: cal[i + 1] for i in range(len(cal) - 1)}

    def lines(n):
        return min(n, DAILY_LIMIT) + (1 if n > DAILY_LIMIT else 0)

    table = []
    for d in targets:
        x = per_day[d]
        P = next_day.get(d)
        fp = fun.get(P or "", {})
        table.append(dict(bar=d, prepare=P, static=len(x["static"]), dynamic=len(x["dynamic"]),
                          loose=len(x["loose"]), s_band=x["s_band"], d_band=x["d_band"],
                          s_stage6=x["s_stage6"], d_stage6=x["d_stage6"], d_uni=x["d_uni"],
                          s_uni_eval=x["s_uni_eval"], jump_skip=x["jump_skip"],
                          lock_win_events=x["lock_win_events"], short=x["short"],
                          funnel_step3=fp.get(3), funnel_step5=fp.get(5), funnel_step6=fp.get(6),
                          funnel_step7=fp.get(7), lines_static=lines(len(x["static"])),
                          lines_dynamic=lines(len(x["dynamic"])),
                          tickers_dynamic=x["dynamic"]))

    def dist(key):
        a = np.array([r[key] for r in table], float)
        return dict(median=float(np.median(a)), mean=round(float(a.mean()), 2), p90=float(np.percentile(a, 90)),
                    max=int(a.max()), min=int(a.min()), over60=int((a > DAILY_LIMIT).sum()),
                    over30=int((a > 30).sum()), zero=int((a == 0).sum()))

    out = dict(params=dict(atr_ratio_min=atr_min, atr_ratio_max=atr_max, mcap_thr_eok=mcap_thr,
                           trade_thr=trade_thr, exclude=len(excl), price_min=pmin, price_max=pmax,
                           ema=[cfg.ema_short, cfg.ema_mid, cfg.ema_long, cfg.macd_signal, cfg.atr_period],
                           enabled=meta.get("enabled"), weight=meta.get("weight")),
               latest=meta["latest"], n_days=len(targets), first=targets[0], last=targets[-1],
               static_universe=len(static_uni), diag=dict(diag),
               dist=dict(static=dist("static"), dynamic=dist("dynamic"), loose=dist("loose")),
               table=table)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dump":
        import asyncio
        asyncio.run(_dump(sys.argv[2] if len(sys.argv) > 2 else "/tmp/cycle348_dump.jsonl.gz"))
    elif mode == "analyze":
        nd = 60
        if "--days" in sys.argv:
            nd = int(sys.argv[sys.argv.index("--days") + 1])
        _analyze(sys.argv[2], nd)
    else:
        print(__doc__)
        sys.exit(2)
