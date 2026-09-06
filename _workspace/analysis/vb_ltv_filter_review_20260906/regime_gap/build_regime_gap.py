#!/usr/bin/env python3
"""VB/LTV 레짐·갭 검정용 **룩어헤드 없는** 관측 테이블 빌더.

읽기 전용 — 운영 DB 는 `ssh auto-stock` 경유 psql SELECT 만, 리포·DB 무수정.

핵심 원칙
---------
1. **특징량(feature)은 D-1 종가까지의 정보 또는 D 09:00 에 확정된 값만** 쓴다.
   D 종가·D 고저·D 거래대금은 성과(outcome) 계산에만 쓰고 컬럼명에 `_D_` 또는
   `ret_`/`px_`/`high`/`low`/`close` 접두·접미로 구분한다.
2. 저장된 funnel 최종 후보(VB step6 / LTV step7)는 **16:20 저녁 캡처**라 그날 거래대금으로
   걸러진 풀이다(verify_report.md [HIGH]). 그래서 표본을 셋으로 나눠 라벨링한다:
     - `sample_stored_eligible`      : 저장 풀 ∩ (D-1 거래대금 ≥ 전략 임계)  = 적격 부분집합(표본 i)
     - `sample_stored_contaminated`  : 저장 풀 ∩ (D-1 거래대금 < 전략 임계)  = **오염, 대조 전용**
     - `sample_recon_d1`             : D-1 정보만으로 재구성한 풀            = 표본 (ii)
3. 지수·매크로 레짐은 D-1 종가까지, 갭은 D 09:00 시가로만 만든다.

산출
----
  data/index_features.csv   지수 레짐 특징량 (거래일 × 지수)
  data/obs_regime_gap.csv   관측 (전략 × 거래일 × 종목)
  data/trades_features.csv  실체결 FIFO 왕복 + 매수일 레짐·갭 특징량
  data/columns.md           컬럼 사전 (정보 확정 시각 명시)
  data/build_meta.json      표본 수·거래일 수·스킵 사유 등 빌드 메타
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import shlex
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")
os.makedirs(RAW, exist_ok=True)
SEP = "\x1f"

# ---------------------------------------------------------------- 상수 (라이브 설정 = strategy_config 09-06 실측)
COST_BP = 28.0        # 왕복: 수수료 0.015%×2 + 거래세 0.15% + 슬리피지 10bp
FEE_RT = 0.00015      # 편도 수수료 (실체결 net)
TAX = 0.0015          # 매도 거래세
NOTIONAL_WON = 140_547.0   # 명목 왕복 기준 (원 환산 병기용)

STRATS = {
    "volatility_breakout": dict(
        step=6, k_period=15, k_value=1.3, position_ratio=0.35,
        min_trade_amount=50_000_000_000,   # 500억
        min_market_cap=50_000_000_000,     # 500억 (과거 재구성 불가 — columns.md 참조)
        max_scan=100, stop_pct=-5.0, min_prdy_rate=None,
        boards=("main",),
    ),
    "long_tail_volatility": dict(
        step=7, k_period=20, k_value=1.0, position_ratio=0.20,
        min_trade_amount=20_000_000_000,   # 200억
        min_market_cap=50_000_000_000,
        max_scan=100, stop_pct=-5.0, min_prdy_rate=5.0,
        boards=("main", "pre_nxt"),
    ),
}
LIMIT_UP_THRESHOLD = 29.0     # LTV 상한가 모드 전환 (전일대비 %)
PRICE_MIN, PRICE_MAX = 3_000, 500_000   # system_config price_filter (HARD)
MIN_REAL_ROWS_FOR_TRADING_DAY = 500

INDEXES = {"kospi200": ("069500", "102110"), "kosdaq150": ("229200", "232080")}
ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")

DAILY_FROM = "2026-05-01"     # 종목 일봉 (noise 20일 + 5일 수익률 여유)
INDEX_FROM = "2026-01-01"     # 지수 일봉 (MA60 여유)
TRADES_FROM = "2026-04-01"


# ---------------------------------------------------------------- DB 추출 (SELECT only)
def run_sql(sql: str, out_path: str) -> int:
    assert sql.lstrip().upper().startswith("SELECT"), "SELECT only"
    remote = (
        "cd ~/auto_stock && "
        "DSN=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '\"') && "
        "psql \"$DSN\" -X -q -At -F $'\\x1f' -c " + shlex.quote(sql)
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(["ssh", "auto-stock", "bash", "-s"],
                              input=remote, text=True, stdout=fh, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed: {out_path}")
    with open(out_path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


QUERIES = {
    "funnel_final.usv": (
        "SELECT strategy_id, target_date, step_no, "
        "to_char(snapshot_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'), "
        "is_provisional, survived_count, survived_tickers::text "
        "FROM strategy_funnel_snapshots "
        "WHERE (strategy_id='volatility_breakout' AND step_no=6) "
        "   OR (strategy_id='long_tail_volatility' AND step_no=7) "
        "ORDER BY strategy_id, target_date"
    ),
    "daily.usv": (
        "SELECT ticker, bas_dd::text, open_price, high_price, low_price, close_price, "
        "volume, trade_value FROM stock_master_daily "
        f"WHERE bas_dd >= '{DAILY_FROM}' ORDER BY ticker, bas_dd"
    ),
    "index_daily.usv": (
        "SELECT ticker, bas_dd::text, open_price, high_price, low_price, close_price, "
        "volume, trade_value FROM stock_master_daily "
        "WHERE ticker IN ('069500','102110','229200','232080') "
        f"AND bas_dd >= '{INDEX_FROM}' ORDER BY ticker, bas_dd"
    ),
    "trades.usv": (
        "SELECT id, to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'), "
        "ticker, ticker_name, trade_type, price, quantity, profit_loss, status, strategy, order_no "
        "FROM trade_history WHERE strategy IN ('volatility_breakout','long_tail_volatility') "
        f"AND timestamp >= '{TRADES_FROM} 00:00:00+09' ORDER BY timestamp, id"
    ),
    "regime.usv": (
        "SELECT snapshot_date::text, regime, cycle_phase, vix, fear_greed_score, buffett_ratio, "
        "computed_cash_usage_ratio, buy_blocked, "
        "COALESCE(raw_response->'regime'->'params'->>'cash_min','') "
        "FROM market_regime_snapshots ORDER BY snapshot_date"
    ),
    "names.usv": "SELECT ticker, COALESCE(name,'') FROM stock_master ORDER BY ticker",
}


def extract(force: bool = False) -> None:
    for fname, sql in QUERIES.items():
        path = os.path.join(RAW, fname)
        if os.path.exists(path) and not force:
            print(f"  reuse {fname} ({os.path.getsize(path)}B)")
            continue
        n = run_sql(sql, path)
        print(f"  {fname}: {n} rows")


# ---------------------------------------------------------------- 로드
def _f(x):
    x = (x or "").strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _i(x):
    v = _f(x)
    return int(v) if v is not None else None


def load_daily(fname: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    with open(os.path.join(RAW, fname), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split(SEP)
            if len(p) < 8:
                continue
            out[p[0]].append(dict(
                d=p[1], o=_i(p[2]), h=_i(p[3]), l=_i(p[4]), c=_i(p[5]),
                v=_i(p[6]), tv=_f(p[7]),
            ))
    for rows in out.values():
        rows.sort(key=lambda r: r["d"])
    return out


def is_real(r) -> bool:
    """실봉 = 거래량 > 0 ∧ h ≥ l ∧ o > 0. (D 행은 D 07:57 스텁으로 만들어져 D+1 07:57 에 실값이 됨)"""
    return bool(r and r["v"] and r["v"] > 0 and r["h"] and r["l"] and r["o"]
                and r["h"] >= r["l"] and r["o"] > 0)


def load_funnel() -> dict[str, dict[str, set[str]]]:
    """{strategy: {target_date: set(ticker)}}  (최종 step 의 저장 후보)"""
    out: dict[str, dict[str, set[str]]] = collections.defaultdict(dict)
    with open(os.path.join(RAW, "funnel_final.usv"), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            sid, tdate, step, snap, prov, cnt, js = line.split(SEP, 6)
            items = json.loads(js) if js else []
            tickers = {str(it.get("ticker", "")).strip() for it in items if it.get("ticker")}
            out[sid][tdate] = tickers
    return out


def load_names() -> dict[str, str]:
    out = {}
    with open(os.path.join(RAW, "names.usv"), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split(SEP)
            if len(p) >= 2:
                out[p[0]] = p[1]
    return out


def load_regime() -> list[dict]:
    out = []
    with open(os.path.join(RAW, "regime.usv"), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split(SEP)
            out.append(dict(date=p[0], regime=p[1], cycle_phase=p[2], vix=_f(p[3]),
                            fear_greed=_f(p[4]), buffett=_f(p[5]),
                            cash_usage=_f(p[6]), buy_blocked=(p[7] == "t"),
                            cash_min=_f(p[8]) if len(p) > 8 else None))
    out.sort(key=lambda r: r["date"])
    return out


def load_trades() -> list[dict]:
    out = []
    with open(os.path.join(RAW, "trades.usv"), encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split(SEP)
            if len(p) < 11:
                continue
            out.append(dict(id=p[0], ts=p[1], ticker=p[2], name=p[3], ttype=p[4],
                            px=_f(p[5]), qty=_i(p[6]), pl=_f(p[7]), status=p[8],
                            strategy=p[9], order_no=p[10]))
    out.sort(key=lambda r: (r["ts"], r["id"]))
    return out


# ---------------------------------------------------------------- 공통 계산
def bp(a, b):
    return (a / b - 1.0) * 1e4 if (a is not None and b) else None


def noise_k(rows) -> float | None:
    """일별 noise = 1 − |close−open|/(high−low), range>0 인 날만 평균."""
    vals = []
    for r in rows:
        rng = r["h"] - r["l"]
        if rng > 0:
            vals.append(1 - abs(r["c"] - r["o"]) / rng)
    return (sum(vals) / len(vals)) if vals else None


def trade_value(r) -> float | None:
    """거래대금 — trade_value 컬럼 우선, 결측/0 이면 close×volume 대체."""
    if r["tv"] and r["tv"] > 0:
        return r["tv"]
    if r["c"] and r["v"]:
        return float(r["c"]) * float(r["v"])
    return None


# ---------------------------------------------------------------- 지수 레짐 특징량
def build_index_features(idx_daily, trading_days):
    """거래일 D 마다 D-1 종가까지의 정보로 만든 지수 레짐 특징량.

    반환 {(D, label): {...}}.  MA/변동성/상승일비율 창은 전부 P=D-1 에서 끝난다.
    """
    feats: dict[tuple[str, str], dict] = {}
    resolved: dict[str, str] = {}
    for label, cands in INDEXES.items():
        chosen = None
        for tk in cands:
            rows = [r for r in idx_daily.get(tk, []) if is_real(r)]
            if len(rows) >= 80:
                chosen = tk
                break
        if chosen is None:
            continue
        resolved[label] = chosen
        rows = [r for r in idx_daily.get(chosen, []) if is_real(r)]
        by_d = {r["d"]: i for i, r in enumerate(rows)}
        closes = [r["c"] for r in rows]
        for i, d in enumerate(trading_days):
            prev_d = trading_days[i - 1] if i > 0 else None
            if prev_d is None or prev_d not in by_d:
                continue
            j = by_d[prev_d]           # P 의 인덱스
            if j < 1:
                continue
            rets = [closes[k] / closes[k - 1] - 1.0 for k in range(1, j + 1)]
            cp = closes[j]

            def ma(n):
                return statistics.fmean(closes[j - n + 1:j + 1]) if j + 1 >= n else None

            ma5, ma20, ma60 = ma(5), ma(20), ma(60)
            r20 = rets[-20:] if len(rets) >= 20 else None
            vol20 = (statistics.stdev(r20) * math.sqrt(252) * 100) if r20 and len(r20) >= 2 else None
            ret5 = (closes[j] / closes[j - 5] - 1.0) * 1e4 if j >= 5 else None
            row_d = rows[by_d[d]] if d in by_d else None
            feats[(d, label)] = dict(
                index_ticker=chosen, prev_date=prev_d, prev_close=cp,
                prev_ret_bp=round(rets[-1] * 1e4, 2) if rets else None,
                ma5_pos_pct=round((cp / ma5 - 1) * 100, 4) if ma5 else None,
                ma20_pos_pct=round((cp / ma20 - 1) * 100, 4) if ma20 else None,
                ma60_pos_pct=round((cp / ma60 - 1) * 100, 4) if ma60 else None,
                vol20_ann_pct=round(vol20, 4) if vol20 is not None else None,
                ret5_bp=round(ret5, 2) if ret5 is not None else None,
                ma5_gt_ma20=(1 if (ma5 and ma20 and ma5 > ma20) else 0) if (ma5 and ma20) else None,
                updays20_ratio=round(sum(1 for x in r20 if x > 0) / len(r20), 4) if r20 else None,
                # D 09:00 확정 (시장 전체 갭)
                gap_bp_D0900=round(bp(row_d["o"], cp), 2) if row_d else None,
                # 성과·문맥 전용 (D 종가 정보 — 특징량 금지)
                oc_bp_Dclose=round(bp(row_d["c"], row_d["o"]), 2) if row_d else None,
                cc_bp_Dclose=round(bp(row_d["c"], cp), 2) if row_d else None,
            )
    return feats, resolved


def regime_asof(regime_rows, prev_date):
    """D-1 이하의 마지막 매크로 스냅샷 (없으면 None)."""
    best = None
    for r in regime_rows:
        if r["date"] <= prev_date:
            best = r
        else:
            break
    return best


def _days_between(a: str, b: str) -> int:
    import datetime as _dt
    return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days


# ---------------------------------------------------------------- 관측 빌드
def build_observations(daily, funnel, names, idx_feats, regime_rows, trading_days):
    tset = {d: i for i, d in enumerate(trading_days)}
    skipped = collections.Counter()
    rows_out = []

    # 종목별 실봉 + 날짜 인덱스 (사전 계산)
    real_rows = {}
    pos_of = {}
    for t, rs in daily.items():
        rr = [r for r in rs if is_real(r)]
        if rr:
            real_rows[t] = rr
            pos_of[t] = {r["d"]: i for i, r in enumerate(rr)}
    tradable_ticker = {t for t in real_rows
                       if len(t) == 6 and t.isdigit()
                       and not any(kw in names.get(t, "") for kw in ETF_KEYWORDS)}

    for strat, cfg in STRATS.items():
        stored_by_date = funnel.get(strat, {})
        fdates = set(stored_by_date)
        dates = sorted(fdates | set(trading_days))
        for d in dates:
            if d not in tset:
                if d in stored_by_date:
                    skipped[f"{strat}:non_trading_or_stub_day:{d}"] += len(stored_by_date[d])
                continue
            i = tset[d]
            if i == 0:
                skipped[f"{strat}:no_prev_trading_day"] += len(stored_by_date.get(d, ()))
                continue
            prev_d = trading_days[i - 1]
            next_d = trading_days[i + 1] if i + 1 < len(trading_days) else None
            stored = stored_by_date.get(d, set())
            in_fw = int(d in fdates)

            # ---- D-1 재구성 풀 (D-1 실봉만으로 판정: 거래대금 + 가격필터 + ETF/6자리)
            recon: dict[str, float] = {}
            for t in tradable_ticker:
                k = pos_of[t].get(prev_d)
                if k is None:
                    continue
                pr = real_rows[t][k]
                tv = trade_value(pr)
                if tv is None or tv < cfg["min_trade_amount"]:
                    continue
                if not (PRICE_MIN <= pr["c"] <= PRICE_MAX):
                    continue
                recon[t] = tv
            recon_rank = {t: k + 1 for k, (t, _) in
                          enumerate(sorted(recon.items(), key=lambda kv: (-kv[1], kv[0])))}

            universe = set(stored) | set(recon)
            mac = regime_asof(regime_rows, prev_d)
            ik = idx_feats.get((d, "kospi200"), {})
            iq = idx_feats.get((d, "kosdaq150"), {})

            for t in sorted(universe):
                rr = real_rows.get(t)
                in_stored = t in stored
                tag = ":stored" if in_stored else ":recon"
                if not rr:
                    skipped[f"{strat}:no_daily_rows{tag}"] += 1
                    continue
                pmap = pos_of[t]
                di = pmap.get(d)
                if di is None:
                    skipped[f"{strat}:no_real_D_row{tag}"] += 1
                    continue
                rd = rr[di]
                if di == 0:
                    skipped[f"{strat}:no_prev_row{tag}"] += 1
                    continue
                pr = rr[di - 1]                       # 종목별 직전 실봉 (거래정지 등으로 D-1 이 아닐 수 있음)
                prev_gap_flag = int(pr["d"] != prev_d)
                prev_range = pr["h"] - pr["l"]
                if prev_range <= 0:
                    skipped[f"{strat}:prev_range_le0"] += 1
                    continue
                nwin = rr[max(0, di - 1 - cfg["k_period"]):di - 1]   # prev 이전 k_period 일
                kn = noise_k(nwin) if len(nwin) >= 3 else None
                prev_prev = rr[di - 2] if di >= 2 else None
                prev5 = rr[di - 6] if di >= 6 else None

                o, h, l, c = rd["o"], rd["h"], rd["l"], rd["c"]
                pc = pr["c"]
                gap_pct = (o - pc) / pc * 100.0
                gap_over_range = (o - pc) / prev_range if prev_range else None

                tv_prev = trade_value(pr)
                elig = bool(tv_prev is not None and tv_prev >= cfg["min_trade_amount"])

                # LTV 연속 상한가 배제 (D-1 정보) — prev 부터 2일 연속 (close-open)/open >= +25%
                consec = 0
                for r in reversed(rr[max(0, di - cfg.get("consec_n", 2)):di]):
                    if r["o"] and (r["c"] - r["o"]) / r["o"] >= 0.25:
                        consec += 1
                    else:
                        break
                consec_excl = int(consec >= 2)

                # ---- 목표가 (D 09:00 시가 확정 시점에 계산 가능)
                tgt_live = (o + int(int(prev_range * kn) * cfg["k_value"])) if kn is not None else None
                tgt_simple = o + cfg["k_value"] * prev_range
                eff_k = (int(int(prev_range * kn) * cfg["k_value"]) / prev_range) if kn is not None else None

                rec = dict(
                    strategy=strat, target_date=d, ticker=t, name=names.get(t, ""),
                    in_funnel_window=in_fw,
                    prev_date=pr["d"], prev_trading_day=prev_d, prev_gap_flag=prev_gap_flag,
                    next_date=next_d or "",
                    # ---- 표본 라벨
                    in_stored_pool=int(in_stored),
                    prev_tv_won=round(tv_prev, 0) if tv_prev is not None else None,
                    prev_tv_source=("trade_value" if (pr["tv"] and pr["tv"] > 0) else "close_x_volume"),
                    prev_tv_eligible=int(elig),
                    sample_stored_eligible=int(in_stored and elig),
                    sample_stored_contaminated=int(in_stored and not elig),
                    sample_recon_d1=int(t in recon),
                    recon_rank_prev_tv=recon_rank.get(t),
                    sample_recon_d1_top100=int(recon_rank.get(t, 10**9) <= cfg["max_scan"]),
                    ltv_consec_limitup_excl=consec_excl,
                    # ---- D-1 종가 확정 특징량 (종목)
                    prev_open=pr["o"], prev_high=pr["h"], prev_low=pr["l"], prev_close=pc,
                    prev_range=prev_range,
                    prev_range_pct=round(prev_range / pc * 100, 4) if pc else None,
                    prev_ret_bp=round(bp(pc, prev_prev["c"]), 2) if prev_prev else None,
                    prev_ret5_bp=round(bp(pc, prev5["c"]), 2) if prev5 else None,
                    k_noise=round(kn, 6) if kn is not None else None,
                    k_noise_n=len(nwin),
                    k_noise_full=int(len(nwin) >= cfg["k_period"]),
                    eff_k_mult=round(eff_k, 4) if eff_k is not None else None,
                    # ---- D 09:00 확정 특징량
                    open_D=o,
                    gap_pct=round(gap_pct, 4),
                    gap_bp=round(gap_pct * 100, 2),
                    gap_over_prev_range=round(gap_over_range, 4) if gap_over_range is not None else None,
                    target_live=tgt_live, target_simple=round(tgt_simple, 2),
                    ltv_prdy_gate_at_open=(int(o >= pc * (1 + cfg["min_prdy_rate"] / 100.0))
                                           if cfg["min_prdy_rate"] else None),
                    # ---- 지수 레짐 (D-1 종가 확정) + 지수 갭 (D 09:00)
                    idx_k200_ticker=ik.get("index_ticker"),
                    idx_k200_prev_ret_bp=ik.get("prev_ret_bp"),
                    idx_k200_ma5_pos_pct=ik.get("ma5_pos_pct"),
                    idx_k200_ma20_pos_pct=ik.get("ma20_pos_pct"),
                    idx_k200_ma60_pos_pct=ik.get("ma60_pos_pct"),
                    idx_k200_vol20_ann_pct=ik.get("vol20_ann_pct"),
                    idx_k200_ret5_bp=ik.get("ret5_bp"),
                    idx_k200_ma5_gt_ma20=ik.get("ma5_gt_ma20"),
                    idx_k200_updays20_ratio=ik.get("updays20_ratio"),
                    idx_k200_gap_bp_D0900=ik.get("gap_bp_D0900"),
                    idx_kq150_ticker=iq.get("index_ticker"),
                    idx_kq150_prev_ret_bp=iq.get("prev_ret_bp"),
                    idx_kq150_ma5_pos_pct=iq.get("ma5_pos_pct"),
                    idx_kq150_ma20_pos_pct=iq.get("ma20_pos_pct"),
                    idx_kq150_ma60_pos_pct=iq.get("ma60_pos_pct"),
                    idx_kq150_vol20_ann_pct=iq.get("vol20_ann_pct"),
                    idx_kq150_ret5_bp=iq.get("ret5_bp"),
                    idx_kq150_ma5_gt_ma20=iq.get("ma5_gt_ma20"),
                    idx_kq150_updays20_ratio=iq.get("updays20_ratio"),
                    idx_kq150_gap_bp_D0900=iq.get("gap_bp_D0900"),
                    # ---- 매크로 (D-1 이하 마지막 스냅샷)
                    mac_snapshot_date=(mac or {}).get("date"),
                    mac_stale_days=_days_between(mac["date"], prev_d) if mac else None,
                    mac_regime=(mac or {}).get("regime"),
                    mac_vix=(mac or {}).get("vix"),
                    mac_fear_greed=(mac or {}).get("fear_greed"),
                    mac_cash_min=(mac or {}).get("cash_min"),
                    mac_cash_usage_ratio=(mac or {}).get("cash_usage"),
                    # ---- 성과 원자료 (D 종가·고저 = 특징량 금지)
                    high_D=h, low_D=l, close_D=c, volume_D=rd["v"],
                    tv_won_D=round(trade_value(rd), 0) if trade_value(rd) is not None else None,
                    idx_k200_oc_bp_Dclose=ik.get("oc_bp_Dclose"),
                    idx_k200_cc_bp_Dclose=ik.get("cc_bp_Dclose"),
                )

                # ---- 성과 (a) 무조건 시가→종가
                rec["ret_oc_bp"] = round(bp(c, o), 2)
                rec["ret_oc_net_bp"] = round(bp(c, o) - COST_BP, 2)
                rec["ret_oc_won_on_140k"] = round(bp(c, o) / 1e4 * NOTIONAL_WON, 0)

                # ---- 성과 (b) 라이브 목표가 돌파 조건부
                stop_frac = cfg["stop_pct"] / 100.0
                rec["breakout_live"] = None
                rec["entry_px_live"] = None
                if tgt_live is not None and tgt_live > o:
                    bo = h >= tgt_live
                    rec["breakout_live"] = int(bo)
                    if bo:
                        entry = float(tgt_live)
                        stop_px = entry * (1 + stop_frac)
                        st_ub = l <= stop_px          # 상한 정의: 저가 터치 = 손절 (진입 전 터치 포함)
                        st_lb = c <= stop_px          # 하한 정의: 종가가 손절선 이하
                        raw = bp(c, entry)
                        rec.update(
                            entry_px_live=entry,
                            low_to_entry_bp=round(bp(l, entry), 2),
                            high_to_entry_bp=round(bp(h, entry), 2),
                            ret_bo_live_bp=round(raw, 2),
                            ret_bo_live_net_bp=round(raw - COST_BP, 2),
                            stopped_live_ub=int(st_ub), stopped_live_lb=int(st_lb),
                            ret_bo_live_stopub_bp=round(stop_frac * 1e4 if st_ub else raw, 2),
                            ret_bo_live_stoplb_bp=round(stop_frac * 1e4 if st_lb else raw, 2),
                            ret_bo_live_stopub_net_bp=round((stop_frac * 1e4 if st_ub else raw) - COST_BP, 2),
                            ret_bo_live_stoplb_net_bp=round((stop_frac * 1e4 if st_lb else raw) - COST_BP, 2),
                            ret_bo_live_stoplb_won_on_140k=round(
                                ((stop_frac * 1e4 if st_lb else raw) - COST_BP) / 1e4 * NOTIONAL_WON, 0),
                        )

                # ---- LTV 전용: 전일대비 +5% 게이트 + 익일 시가 청산 변형
                if cfg["min_prdy_rate"] is not None:
                    gate_px = pc * (1 + cfg["min_prdy_rate"] / 100.0)
                    rec["ltv_gate_px"] = round(gate_px, 2)
                    rec["ltv_gate_pass_D"] = int(h >= gate_px)
                    ent = None
                    if tgt_live is not None and tgt_live > o and h >= max(float(tgt_live), gate_px):
                        ent = max(float(tgt_live), gate_px)
                    rec["ltv_entry_px"] = round(ent, 2) if ent is not None else None
                    rec["ltv_entry_binding"] = (None if ent is None
                                                else ("gate" if gate_px > float(tgt_live) else "target"))
                    if ent:
                        stop_px = ent * (1 + stop_frac)
                        st_ub = l <= stop_px
                        st_lb = c <= stop_px
                        raw = bp(c, ent)
                        limit_up = int(h >= pc * (1 + LIMIT_UP_THRESHOLD / 100.0))
                        rec.update(
                            ltv_low_to_entry_bp=round(bp(l, ent), 2),
                            ltv_stopped_ub=int(st_ub), ltv_stopped_lb=int(st_lb),
                            ret_ltv_close_bp=round(raw, 2),
                            ret_ltv_close_net_bp=round(raw - COST_BP, 2),
                            ret_ltv_close_stoplb_bp=round(stop_frac * 1e4 if st_lb else raw, 2),
                            ret_ltv_close_stopub_bp=round(stop_frac * 1e4 if st_ub else raw, 2),
                            ret_ltv_close_stoplb_net_bp=round(
                                (stop_frac * 1e4 if st_lb else raw) - COST_BP, 2),
                            ltv_limit_up_D=limit_up,
                        )
                        nxt = rr[di + 1] if di + 1 < len(rr) else None
                        if nxt is not None and next_d and nxt["d"] == next_d:
                            on = bp(nxt["o"], ent)
                            rec.update(
                                next_open=nxt["o"],
                                ret_ltv_overnight_bp=round(on, 2),
                                ret_ltv_overnight_net_bp=round(on - COST_BP, 2),
                                ret_ltv_overnight_stopub_bp=round(stop_frac * 1e4 if st_ub else on, 2),
                                ret_ltv_livemode_bp=round(on if limit_up else raw, 2),
                                ret_ltv_livemode_net_bp=round((on if limit_up else raw) - COST_BP, 2),
                            )
                        else:
                            rec["next_open"] = None

                rows_out.append(rec)
    return rows_out, skipped


# ---------------------------------------------------------------- 실체결 왕복
def build_roundtrips(trades, obs_index, idx_feats, regime_rows, trading_days):
    tset = {d: i for i, d in enumerate(trading_days)}
    open_lots: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    rts = []
    for tr in trades:
        if tr["status"] in ("CANCELLED",):
            continue
        key = (tr["strategy"], tr["ticker"])
        if tr["ttype"] == "BUY":
            if tr["status"] not in ("COMPLETED", "PARTIAL"):
                continue
            open_lots[key].append(dict(ts=tr["ts"], px=tr["px"], qty=tr["qty"] or 0,
                                       name=tr["name"], id=tr["id"]))
        elif tr["ttype"] == "SELL":
            if tr["status"] not in ("COMPLETED", "PARTIAL"):
                continue
            remain = tr["qty"] or 0
            while remain > 0 and open_lots[key]:
                lot = open_lots[key][0]
                take = min(remain, lot["qty"])
                if take <= 0:
                    open_lots[key].pop(0)
                    continue
                rts.append(dict(strategy=tr["strategy"], ticker=tr["ticker"],
                                name=lot["name"] or tr["name"],
                                buy_ts_kst=lot["ts"], sell_ts_kst=tr["ts"],
                                buy_px=lot["px"], sell_px=tr["px"], qty=take,
                                buy_trade_id=lot["id"], sell_trade_id=tr["id"],
                                sell_pl_db=tr["pl"]))
                lot["qty"] -= take
                remain -= take
                if lot["qty"] <= 0:
                    open_lots[key].pop(0)

    out = []
    for r in rts:
        bdate = r["buy_ts_kst"][:10]
        btime = r["buy_ts_kst"][11:]
        gross_bp = bp(r["sell_px"], r["buy_px"])
        net_bp = None
        if gross_bp is not None:
            gross = r["sell_px"] / r["buy_px"] - 1.0
            net = gross - (FEE_RT * 2 + TAX)
            net_bp = net * 1e4
        ob = obs_index.get((r["strategy"], bdate, r["ticker"]))
        ik = idx_feats.get((bdate, "kospi200"), {})
        iq = idx_feats.get((bdate, "kosdaq150"), {})
        prev_d = trading_days[tset[bdate] - 1] if (bdate in tset and tset[bdate] > 0) else None
        mac = regime_asof(regime_rows, prev_d) if prev_d else None
        row = dict(
            strategy=r["strategy"], ticker=r["ticker"], name=r["name"],
            buy_date=bdate, buy_time_kst=btime, sell_ts_kst=r["sell_ts_kst"],
            buy_px=r["buy_px"], sell_px=r["sell_px"], qty=r["qty"],
            notional_won=round(r["buy_px"] * r["qty"], 0) if r["buy_px"] else None,
            ret_gross_bp=round(gross_bp, 2) if gross_bp is not None else None,
            ret_net_bp=round(net_bp, 2) if net_bp is not None else None,
            pnl_gross_won=round((r["sell_px"] - r["buy_px"]) * r["qty"], 0),
            pnl_net_on_140k_won=round(net_bp / 1e4 * NOTIONAL_WON, 0) if net_bp is not None else None,
            sell_pl_db=r["sell_pl_db"],
            entry_0900_0901_30=int("09:00:00" <= btime <= "09:01:30"),
            entry_before_0900=int(btime < "09:00:00"),
            entry_hour=int(btime[:2]) if btime else None,
            buy_trade_id=r["buy_trade_id"], sell_trade_id=r["sell_trade_id"],
            in_obs=int(ob is not None),
        )
        # 매수일 D 의 레짐(=D-1 확정)·갭(=D 09:00) 특징량
        for k in ("in_funnel_window", "prev_date", "prev_gap_flag", "prev_close", "prev_range",
                  "prev_range_pct", "prev_ret_bp", "prev_ret5_bp", "k_noise", "k_noise_full",
                  "eff_k_mult", "open_D", "gap_pct", "gap_bp",
                  "gap_over_prev_range", "target_live", "prev_tv_won", "prev_tv_eligible",
                  "in_stored_pool", "sample_stored_eligible", "sample_stored_contaminated",
                  "sample_recon_d1", "recon_rank_prev_tv", "ltv_consec_limitup_excl",
                  "high_D", "low_D", "close_D",
                  "breakout_live", "entry_px_live", "ret_bo_live_bp",
                  "ret_bo_live_stoplb_bp", "ret_bo_live_stopub_bp", "ret_bo_live_stoplb_net_bp",
                  "ltv_gate_pass_D", "ltv_entry_px", "ret_ltv_close_bp",
                  "ret_ltv_overnight_bp", "ret_ltv_livemode_bp", "ltv_limit_up_D"):
            row[k] = ob.get(k) if ob else None
        if ob and ob.get("entry_px_live"):
            row["entry_vs_target_live_bp"] = round(bp(r["buy_px"], ob["entry_px_live"]), 2)
        else:
            row["entry_vs_target_live_bp"] = None
        if ob and ob.get("target_live"):
            row["entry_vs_target_any_bp"] = round(bp(r["buy_px"], ob["target_live"]), 2)
        else:
            row["entry_vs_target_any_bp"] = None
        if ob and ob.get("open_D"):
            row["entry_vs_open_bp"] = round(bp(r["buy_px"], ob["open_D"]), 2)
        else:
            row["entry_vs_open_bp"] = None
        for pfx, src in (("idx_k200", ik), ("idx_kq150", iq)):
            for k in ("prev_ret_bp", "ma5_pos_pct", "ma20_pos_pct", "ma60_pos_pct",
                      "vol20_ann_pct", "ret5_bp", "ma5_gt_ma20", "updays20_ratio",
                      "gap_bp_D0900"):
                row[f"{pfx}_{k}"] = src.get(k)
        row["mac_snapshot_date"] = (mac or {}).get("date")
        row["mac_stale_days"] = _days_between(mac["date"], prev_d) if (mac and prev_d) else None
        row["mac_regime"] = (mac or {}).get("regime")
        row["mac_vix"] = (mac or {}).get("vix")
        row["mac_fear_greed"] = (mac or {}).get("fear_greed")
        row["mac_cash_min"] = (mac or {}).get("cash_min")
        out.append(row)
    out.sort(key=lambda r: (r["strategy"], r["buy_date"], r["buy_time_kst"], r["ticker"]))
    return out


# ---------------------------------------------------------------- 컬럼 사전
# 정보 확정 시각(when) 코드
#   KEY   = 키/라벨 (정보 아님)
#   D-1   = D-1 종가(15:30 KST)까지의 정보 — 특징량으로 사용 가능
#   D0900 = D 09:00 시가로 확정 — 특징량으로 사용 가능
#   DCLS  = D 고저/종가/거래대금 — **성과 전용, 특징량 금지**
#   D+1   = D+1 시가 — **성과 전용(오버나잇 청산), 특징량 금지**
#   FILL  = 실체결(trade_history) 사실
#   META  = 빌드 메타
COLUMN_DOC = {
    # --- 키/라벨
    "strategy": ("KEY", "volatility_breakout | long_tail_volatility"),
    "target_date": ("KEY", "거래일 D (KST)"),
    "ticker": ("KEY", "종목코드 6자리"),
    "name": ("KEY", "종목명 (stock_master 현재 스냅샷)"),
    "in_funnel_window": ("KEY", "1 = 그 전략의 저장 funnel 행이 존재하는 날 (VB/LTV 07-13~09-03)"),
    "prev_date": ("KEY", "특징량 기준일 = 그 종목의 D 직전 실봉 날짜"),
    "prev_trading_day": ("KEY", "시장 기준 D-1 거래일"),
    "prev_gap_flag": ("KEY", "1 = prev_date != prev_trading_day (거래정지 등으로 D-1 봉 결측)"),
    "next_date": ("KEY", "D+1 거래일 (오버나잇 청산 기준일)"),
    "index_label": ("KEY", "kospi200 | kosdaq150"),
    "index_ticker": ("KEY", "지수 프록시 ETF 티커 (069500 / 229200)"),
    "trade_date": ("KEY", "거래일 D"),
    # --- 표본 라벨
    "in_stored_pool": ("META", "1 = 저장 funnel 최종 후보(VB step6 / LTV step7)에 있음. "
                               "저장 내용은 16:20 저녁 캡처 = D 당일 거래대금으로 걸러진 풀(룩어헤드 원천)"),
    "prev_tv_won": ("D-1", "D-1 거래대금(원). stock_master_daily.trade_value 우선, 결측 시 close×volume"),
    "prev_tv_source": ("D-1", "trade_value | close_x_volume"),
    "prev_tv_eligible": ("D-1", "1 = prev_tv_won >= 전략 min_trade_amount (VB 500억 / LTV 200억)"),
    "sample_stored_eligible": ("META", "**표본 (i) 적격 부분집합** = in_stored_pool ∧ prev_tv_eligible"),
    "sample_stored_contaminated": ("META", "저장 풀이지만 D-1 거래대금 미달 = 룩어헤드 오염. **대조 전용**"),
    "sample_recon_d1": ("META", "**표본 (ii) D-1 재구성 풀** = D-1 거래대금 임계 ∧ D-1 종가 3,000~500,000 "
                                "∧ 6자리 숫자 ∧ ETF 키워드 제외"),
    "recon_rank_prev_tv": ("D-1", "그날 재구성 풀 안에서 D-1 거래대금 내림차순 순위"),
    "sample_recon_d1_top100": ("META", "recon_rank_prev_tv <= max_scan_stocks(100) — 라이브 limit 근사"),
    "ltv_consec_limitup_excl": ("D-1", "1 = prev 부터 2일 연속 (종가-시가)/시가 >= +25% (LTV 연속상한가 배제 재현)"),
    # --- D-1 확정 종목 특징량
    "prev_open": ("D-1", "직전 실봉 시가"),
    "prev_high": ("D-1", "직전 실봉 고가"),
    "prev_low": ("D-1", "직전 실봉 저가"),
    "prev_close": ("D-1", "직전 실봉 종가 (갭·목표가·LTV 게이트의 분모)"),
    "prev_range": ("D-1", "prev_high - prev_low"),
    "prev_range_pct": ("D-1", "prev_range / prev_close × 100"),
    "prev_ret_bp": ("D-1", "(c) D-1 종가 수익률 = prev_close / prev_prev_close - 1 (bp)"),
    "prev_ret5_bp": ("D-1", "(c) 5일 수익률 = prev_close / (5봉 전 종가) - 1 (bp)"),
    "k_noise": ("D-1", "prev 이전 k_period 일 평균 noise = mean(1 - |c-o|/(h-l)). VB k_period=15 / LTV=20"),
    "k_noise_n": ("D-1", "noise 평균에 쓰인 봉 수"),
    "k_noise_full": ("D-1", "1 = k_noise_n >= k_period (창이 온전)"),
    "eff_k_mult": ("D0900", "실효 배수 = int(int(prev_range×k_noise)×k_value) / prev_range "
                            "(VB k_value=1.3 → 실측 ≈0.73)"),
    # --- D 09:00 확정
    "open_D": ("D0900", "D 시가"),
    "gap_pct": ("D0900", "**갭** = (D 시가 - prev_close) / prev_close × 100"),
    "gap_bp": ("D0900", "gap_pct × 100 (bp)"),
    "gap_over_prev_range": ("D0900", "(a) D 시가의 prev_close 대비 위치를 전일 range 로 나눈 배수"),
    "target_live": ("D0900", "라이브 목표가 = open + int(int(prev_range × k_noise) × k_value)"),
    "target_simple": ("D0900", "단순 목표가 = open + k_value × prev_range (참고)"),
    "ltv_prdy_gate_at_open": ("D0900", "LTV: 1 = 시가가 이미 prev_close×1.05 이상"),
    "ltv_gate_px": ("D0900", "LTV 전일대비 +5% 게이트 가격 = prev_close × 1.05"),
    # --- 지수 레짐 (D-1 확정) / 지수 갭 (D 09:00)
    "ma5_pos_pct": ("D-1", "(b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝"),
    "ma20_pos_pct": ("D-1", "(b) MA20 대비 위치 %"),
    "ma60_pos_pct": ("D-1", "(b) MA60 대비 위치 %"),
    "vol20_ann_pct": ("D-1", "(c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %)"),
    "ret5_bp": ("D-1", "(d) 5일 누적 수익률 (bp)"),
    "ma5_gt_ma20": ("D-1", "(e) 1 = MA5 > MA20"),
    "updays20_ratio": ("D-1", "(f) 최근 20일 중 상승일 비율"),
    "gap_bp_D0900": ("D0900", "지수 갭 = D 시가 / D-1 종가 - 1 (bp)"),
    "oc_bp_Dclose": ("DCLS", "지수 D 시가→종가 (bp) — 문맥 전용"),
    "cc_bp_Dclose": ("DCLS", "지수 D-1 종가→D 종가 (bp) — 문맥 전용"),
    # --- 매크로 (dkstock market_regime_snapshots)
    "mac_snapshot_date": ("D-1", "D-1 이하의 마지막 매크로 스냅샷 날짜 (없으면 공란)"),
    "mac_stale_days": ("D-1", "prev_trading_day - mac_snapshot_date (일). 0 = 당일치"),
    "mac_regime": ("D-1", "dkstock regime 라벨 (표본 전 구간 defensive)"),
    "mac_vix": ("D-1", "VIX"),
    "mac_fear_greed": ("D-1", "Fear & Greed 점수"),
    "mac_cash_min": ("D-1", "raw_response.regime.params.cash_min"),
    "mac_cash_usage_ratio": ("D-1", "computed_cash_usage_ratio"),
    # --- 성과 원자료 (특징량 금지)
    "high_D": ("DCLS", "D 고가 — 돌파 판정"),
    "low_D": ("DCLS", "D 저가 — 손절 판정"),
    "close_D": ("DCLS", "D 종가 — 15:20 청산 근사"),
    "volume_D": ("DCLS", "D 거래량"),
    "tv_won_D": ("DCLS", "D 거래대금(원) — 저장 풀 룩어헤드의 원인 축"),
    "next_open": ("D+1", "D+1 시가 — 오버나잇 청산가"),
    # --- 성과 지표
    "ret_oc_bp": ("DCLS", "(a) 무조건 시가→종가 (bp, gross)"),
    "ret_oc_net_bp": ("DCLS", "(a) net = gross - 28bp"),
    "ret_oc_won_on_140k": ("DCLS", "(a) gross 를 명목 140,547원에 적용한 원 환산"),
    "breakout_live": ("DCLS", "1 = high_D >= target_live (그리고 target_live > open_D). "
                              "None = k_noise 결측 또는 목표가가 시가 이하(갭 관통)"),
    "entry_px_live": ("DCLS", "돌파 시 가정 진입가 = target_live"),
    "low_to_entry_bp": ("DCLS", "(low_D/entry - 1) bp — 임의 손절 임계 재적용용"),
    "high_to_entry_bp": ("DCLS", "(high_D/entry - 1) bp"),
    "ret_bo_live_bp": ("DCLS", "(b) 라이브 목표가 돌파 조건부 진입→종가 (bp, gross)"),
    "ret_bo_live_net_bp": ("DCLS", "(b) net"),
    "stopped_live_ub": ("DCLS", "상한 손절 정의: low_D <= entry×(1-5%) (진입 전 터치 포함 = 손절 과다계상)"),
    "stopped_live_lb": ("DCLS", "하한 손절 정의: close_D <= entry×(1-5%) (확실한 손절만)"),
    "ret_bo_live_stopub_bp": ("DCLS", "(b+stop 상한) 손절 시 -500bp 확정"),
    "ret_bo_live_stoplb_bp": ("DCLS", "(b+stop 하한) 손절 시 -500bp 확정 — **주 성과 지표**"),
    "ret_bo_live_stopub_net_bp": ("DCLS", "위의 net"),
    "ret_bo_live_stoplb_net_bp": ("DCLS", "위의 net — **주 성과 지표(net)**"),
    "ret_bo_live_stoplb_won_on_140k": ("DCLS", "주 성과 net 의 원 환산 (명목 140,547원)"),
    # --- LTV 전용 성과
    "ltv_gate_pass_D": ("DCLS", "1 = high_D >= prev_close×1.05 (전일대비 +5% 게이트가 D 중 성립)"),
    "ltv_entry_px": ("DCLS", "LTV 가정 진입가 = max(target_live, gate_px), high_D 가 그 값에 도달할 때만"),
    "ltv_entry_binding": ("DCLS", "gate | target — 진입가를 결정한 쪽"),
    "ltv_low_to_entry_bp": ("DCLS", "(low_D/ltv_entry - 1) bp"),
    "ltv_stopped_ub": ("DCLS", "LTV 상한 손절 정의"),
    "ltv_stopped_lb": ("DCLS", "LTV 하한 손절 정의"),
    "ret_ltv_close_bp": ("DCLS", "LTV 진입→D 종가 (bp, gross) = 15:20 강제청산 근사"),
    "ret_ltv_close_net_bp": ("DCLS", "위의 net"),
    "ret_ltv_close_stoplb_bp": ("DCLS", "LTV 종가청산 + 하한 손절(-5%) — **LTV 주 성과 지표**"),
    "ret_ltv_close_stopub_bp": ("DCLS", "LTV 종가청산 + 상한 손절"),
    "ret_ltv_close_stoplb_net_bp": ("DCLS", "위의 net"),
    "ltv_limit_up_D": ("DCLS", "1 = high_D >= prev_close×1.29 (라이브 상한가 모드 전환 = 익일 청산)"),
    "ret_ltv_overnight_bp": ("D+1", "LTV 진입→D+1 시가 (bp, gross) — 오버나잇 근사(전 진입 대상)"),
    "ret_ltv_overnight_net_bp": ("D+1", "위의 net"),
    "ret_ltv_overnight_stopub_bp": ("D+1", "D 중 손절선 터치면 -500bp, 아니면 D+1 시가 청산"),
    "ret_ltv_livemode_bp": ("D+1", "라이브 근사: ltv_limit_up_D=1 이면 D+1 시가, 아니면 D 종가"),
    "ret_ltv_livemode_net_bp": ("D+1", "위의 net"),
    # --- 실체결
    "buy_date": ("FILL", "매수 체결일 D (KST)"),
    "buy_time_kst": ("FILL", "매수 체결 시각 HH:MM:SS (KST)"),
    "sell_ts_kst": ("FILL", "매도 체결 시각 (KST)"),
    "buy_px": ("FILL", "매수 체결가"),
    "sell_px": ("FILL", "매도 체결가"),
    "qty": ("FILL", "FIFO 짝지은 수량"),
    "notional_won": ("FILL", "buy_px × qty"),
    "ret_gross_bp": ("FILL", "(sell_px/buy_px - 1) bp"),
    "ret_net_bp": ("FILL", "gross - (수수료 0.015%×2 + 세금 0.15%). 슬리피지는 체결가에 내재"),
    "pnl_gross_won": ("FILL", "(sell_px - buy_px) × qty"),
    "pnl_net_on_140k_won": ("FILL", "ret_net_bp 를 명목 140,547원에 적용"),
    "sell_pl_db": ("FILL", "trade_history.profit_loss (매도행, gross)"),
    "entry_0900_0901_30": ("FILL", "1 = 09:00:00~09:01:30 진입 (VB 09:00 직후 진입 가설 플래그)"),
    "entry_before_0900": ("FILL", "1 = 09:00 이전 진입 (LTV PRE_NXT 보드)"),
    "entry_hour": ("FILL", "매수 시각의 시(hour)"),
    "buy_trade_id": ("FILL", "trade_history.id (매수)"),
    "sell_trade_id": ("FILL", "trade_history.id (매도)"),
    "in_obs": ("META", "1 = obs_regime_gap.csv 에 같은 (strategy, buy_date, ticker) 행이 있어 특징량이 붙음"),
    "entry_vs_target_live_bp": ("FILL", "실체결 매수가 vs 돌파 가정 진입가 (bp)"),
    "entry_vs_target_any_bp": ("FILL", "실체결 매수가 vs target_live (돌파 여부 무관, bp)"),
    "entry_vs_open_bp": ("FILL", "실체결 매수가 vs D 시가 (bp)"),
}
_IDX_PREFIXED = ("idx_k200_", "idx_kq150_")


def _doc_for(col: str):
    if col in COLUMN_DOC:
        return COLUMN_DOC[col]
    for pfx in _IDX_PREFIXED:
        if col.startswith(pfx):
            base = col[len(pfx):]
            label = "KOSPI200(069500)" if pfx == "idx_k200_" else "KOSDAQ150(229200)"
            if base == "ticker":
                return ("KEY", f"{label} 프록시 ETF 티커")
            if base == "prev_ret_bp":
                return ("D-1", f"(a) {label} 전일 수익률 (bp)")
            if base in COLUMN_DOC:
                w, d = COLUMN_DOC[base]
                return (w, f"{label} — {d}")
    return None


def write_columns_md(obs, rts, idx_rows, meta):
    order = ["KEY", "META", "D-1", "D0900", "DCLS", "D+1", "FILL"]
    tables = {
        "obs_regime_gap.csv": obs,
        "trades_features.csv": rts,
        "index_features.csv": idx_rows,
    }
    undocumented = []
    lines = ["# 컬럼 사전 — 정보 확정 시각 명시", "",
             "정보 확정 시각(when) 코드", "",
             "| 코드 | 뜻 | 특징량 사용 |", "|---|---|---|",
             "| `KEY` | 키·라벨 | — |",
             "| `META` | 표본 구성 라벨(빌드 산물) | 층화에만 |",
             "| `D-1` | **D-1 종가(15:30 KST)까지의 정보** | ✅ |",
             "| `D0900` | **D 09:00 시가로 확정** | ✅ |",
             "| `DCLS` | D 고저·종가·거래대금 | ❌ **성과 전용** |",
             "| `D+1` | D+1 시가 | ❌ **성과 전용(오버나잇)** |",
             "| `FILL` | 실체결(trade_history) 사실 | ❌ |",
             ""]
    for tname, rows in tables.items():
        if not rows:
            continue
        cols = []
        seen = set()
        for r in rows:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
        lines += [f"## `{tname}` — {len(cols)} 컬럼 / {len(rows)} 행", "",
                  "| 컬럼 | 확정 시각 | 설명 |", "|---|---|---|"]
        docs = []
        for c in cols:
            d = _doc_for(c)
            if d is None:
                undocumented.append(f"{tname}:{c}")
                d = ("?", "(미문서화)")
            docs.append((c, d[0], d[1]))
        docs.sort(key=lambda x: (order.index(x[1]) if x[1] in order else 99, cols.index(x[0])))
        for c, w, dsc in docs:
            lines.append(f"| `{c}` | `{w}` | {dsc.replace('|', '\\|')} |")
        lines.append("")
    if undocumented:
        lines += ["## ⚠️ 미문서화 컬럼", ""] + [f"- `{u}`" for u in undocumented] + [""]
    with open(os.path.join(DATA, "columns.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    if undocumented:
        print(f"    !! undocumented columns: {undocumented}")
    else:
        print("    columns.md: 전 컬럼 문서화 완료")


# ---------------------------------------------------------------- 저장
def write_csv(path, rows, fieldnames=None):
    if not rows:
        open(path, "w").close()
        return 0
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
        seen = set(fieldnames)
        for r in rows:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def main():
    force = "--force" in sys.argv
    print("[1] DB 추출 (SELECT only)")
    extract(force=force)

    print("[2] 로드")
    daily = load_daily("daily.usv")
    idx_daily = load_daily("index_daily.usv")
    funnel = load_funnel()
    names = load_names()
    regime_rows = load_regime()
    trades = load_trades()
    print(f"    daily tickers={len(daily)} idx={len(idx_daily)} "
          f"funnel_strats={len(funnel)} names={len(names)} regime={len(regime_rows)} trades={len(trades)}")

    # 거래일 = 실봉 행이 충분한 날 (스텁일·휴장일 배제)
    per_date_real = collections.Counter()
    for rs in daily.values():
        for r in rs:
            if is_real(r):
                per_date_real[r["d"]] += 1
    trading_days = sorted(d for d, n in per_date_real.items() if n >= MIN_REAL_ROWS_FOR_TRADING_DAY)
    print(f"    trading_days={len(trading_days)} {trading_days[0]}~{trading_days[-1]}")

    print("[3] 지수 레짐 특징량")
    idx_feats, resolved = build_index_features(idx_daily, trading_days)
    print(f"    resolved={resolved}")
    idx_rows = []
    for (d, label), v in sorted(idx_feats.items()):
        idx_rows.append(dict(trade_date=d, index_label=label, **v))
    n = write_csv(os.path.join(DATA, "index_features.csv"), idx_rows)
    print(f"    index_features.csv rows={n}")

    print("[4] 관측 빌드")
    obs, skipped = build_observations(daily, funnel, names, idx_feats, regime_rows, trading_days)
    n = write_csv(os.path.join(DATA, "obs_regime_gap.csv"), obs)
    print(f"    obs_regime_gap.csv rows={n}")
    for k, v in sorted(skipped.items())[:20]:
        print(f"      skip {k}: {v}")

    print("[5] 실체결 왕복")
    obs_index = {(o["strategy"], o["target_date"], o["ticker"]): o for o in obs}
    rts = build_roundtrips(trades, obs_index, idx_feats, regime_rows, trading_days)
    n = write_csv(os.path.join(DATA, "trades_features.csv"), rts)
    print(f"    trades_features.csv rows={n}")

    # ---- 메타
    def cnt(pred):
        return sum(1 for o in obs if pred(o))

    meta = dict(
        built_at_kst=subprocess.run(["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True,
                                    text=True).stdout.strip(),
        trading_days=len(trading_days), first_day=trading_days[0], last_day=trading_days[-1],
        index_resolved=resolved,
        daily_last_real_day=trading_days[-1],
        regime_snapshots=len(regime_rows),
        strategies={},
        skipped={k: v for k, v in sorted(skipped.items())},
    )
    for s in STRATS:
        sub = [o for o in obs if o["strategy"] == s]
        fw = [o for o in sub if o["in_funnel_window"]]
        st = [o for o in sub if o["in_stored_pool"]]
        rec_fw = [o for o in fw if o["sample_recon_d1"]]
        srt = [r for r in rts if r["strategy"] == s]
        meta["strategies"][s] = dict(
            obs_rows=len(sub),
            dates=len({o["target_date"] for o in sub}),
            date_min=min((o["target_date"] for o in sub), default=None),
            date_max=max((o["target_date"] for o in sub), default=None),
            tickers=len({o["ticker"] for o in sub}),
            funnel_window_dates=len({o["target_date"] for o in fw}),
            funnel_window_date_min=min((o["target_date"] for o in fw), default=None),
            funnel_window_date_max=max((o["target_date"] for o in fw), default=None),
            stored_pool=len(st),
            stored_pool_tickers=len({o["ticker"] for o in st}),
            stored_eligible=sum(o["sample_stored_eligible"] for o in sub),
            stored_contaminated=sum(o["sample_stored_contaminated"] for o in sub),
            contaminated_share=round(sum(o["sample_stored_contaminated"] for o in sub) /
                                     max(1, len(st)), 4),
            recon_d1_all=sum(o["sample_recon_d1"] for o in sub),
            recon_d1_in_funnel_window=len(rec_fw),
            recon_d1_top100_all=sum(o["sample_recon_d1_top100"] for o in sub),
            recon_d1_top100_in_funnel_window=sum(o["sample_recon_d1_top100"] for o in fw),
            recon_tickers=len({o["ticker"] for o in sub if o["sample_recon_d1"]}),
            recon_per_day_median=(statistics.median(
                collections.Counter(o["target_date"] for o in sub if o["sample_recon_d1"]).values())
                if any(o["sample_recon_d1"] for o in sub) else None),
            stored_per_day_median=(statistics.median(
                collections.Counter(o["target_date"] for o in st).values()) if st else None),
            k_noise_full_share=round(
                sum(o["k_noise_full"] for o in sub) / max(1, len(sub)), 4),
            breakout_live_n_stored_eligible=sum(
                1 for o in sub if o["sample_stored_eligible"] and o.get("breakout_live")),
            trades_roundtrips=len(srt),
            trades_roundtrips_from_0701=sum(1 for r in srt if r["buy_date"] >= "2026-07-01"),
            trades_roundtrips_in_funnel_window=sum(
                1 for r in srt if "2026-07-13" <= r["buy_date"] <= "2026-09-03"),
            trades_joined_to_obs=sum(1 for r in srt if r["in_obs"]),
        )
    with open(os.path.join(DATA, "build_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    write_columns_md(obs, rts, idx_rows, meta)
    print(json.dumps(meta["strategies"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
