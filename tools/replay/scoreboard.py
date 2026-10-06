#!/usr/bin/env python3
"""30년 전략 성적표 — 같은 잣대로 숫자를 한 표에 모은다(판정·최적화·선택 없음).

입력 목록은 ``REGISTRY`` 한 곳이다. 새 전략(예: 주기적 재조정 결과)을 붙일 때는 그 목록에 한 줄을 더하고,
일별 가치 곡선을 돌려주는 로더를 ``LOADERS`` 에 이어 붙인다. 지표 계산은 전부 ``compute_metrics`` 하나가 한다.

곡선의 출처는 셋이다.
- 여러 나라 자산배분(``global_alloc`` · ``global_alloc_b``) — 원화 총수익 지수 모형 · 비용 왕복 0.38% · 보수 차감 · 세전
- 바탕 층(``y30_etfbase_run``) — 069500 연속 계열 · 정수 주 계좌 4,707,820원 · 시기별 비용 표
- 개별 매매 전략 계좌(``scoreboard_books`` 가 미리 만든 ``books/*.npz``) — 운영 사이저 · 4,707,820원 단독 풀 ·
  씨앗 16 중 최종 평가액 하위 중앙(8번째) 씨앗의 곡선

실행::

    python tools/replay/scoreboard_books.py <out_dir>/books        # 개별 전략 계좌 곡선(전략당 수 분)
    python tools/replay/scoreboard.py <out_dir>                     # 성적표(json · md)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MAIN_REPO = "/Users/koscom/Projects/auto_stock"
GLOBAL_PARQUET = os.path.join(MAIN_REPO, "data/archive/global_long/global_daily_krw.parquet")
MONTH_CUTOFF = pd.Period("2026-09", "M")      # 월말 계열의 마지막 달(10월은 이틀뿐이라 뺀다)
FULL_YEAR_MIN_DAYS = 330                       # 연도 수익을 「온전한 해」 로 세는 최소 달력 일수
INVEST = 10_000_000                            # 「1천만 원 투자 시 최종 금액」
STATUSES = ("기준선", "통과", "실패", "보류", "참고")
MIN_EXCESS_VOL = 0.005                         # 연 초과수익 변동이 0.5% 미만이면 샤프·소르티노를 내지 않는다


# ═════════════════════════════════ 지표 ═════════════════════════════════

def _dd(v: np.ndarray) -> np.ndarray:
    return v / np.maximum.accumulate(v) - 1.0


def max_drawdown(dates: pd.DatetimeIndex, v: np.ndarray) -> dict:
    """최대 낙폭과 그 고점·바닥·회복일(회복 = 바닥 뒤 처음으로 고점 값 이상). 미회복이면 recovery=None."""
    dd = _dd(v)
    k = int(np.argmin(dd))
    if dd[k] >= 0:
        return {"mdd": 0.0, "peak": str(dates[0].date()), "trough": str(dates[0].date()), "recovery": str(dates[0].date())}
    p = int(np.argmax(v[:k + 1]))
    rec = np.where(v[k:] >= v[p])[0]
    return {"mdd": float(dd[k]), "peak": str(dates[p].date()), "trough": str(dates[k].date()),
            "recovery": str(dates[k + int(rec[0])].date()) if len(rec) else None}


def longest_underwater(dates: pd.DatetimeIndex, v: np.ndarray) -> dict:
    """고점에서 그 고점을 되찾기까지 가장 긴 달력 일수. 끝까지 못 되찾은 구간은 끝 날까지 세고 ongoing=True."""
    peak, p_i, best, best_on, best_from = v[0], 0, 0, False, None
    for i in range(1, len(v)):
        if v[i] >= peak:
            span = (dates[i] - dates[p_i]).days
            if span > best:
                best, best_on, best_from = span, False, p_i
            peak, p_i = v[i], i
    span = (dates[-1] - dates[p_i]).days
    if v[-1] < peak and span > best:
        best, best_on, best_from = span, True, p_i
    return {"days": int(best), "ongoing": bool(best_on),
            "from": str(dates[best_from].date()) if best_from is not None else None}


def ulcer_index(v: np.ndarray) -> float:
    """울서 지수 = √(평균(낙폭%²)) — 낙폭의 깊이와 길이를 함께 잰다(단위 %)."""
    return float(np.sqrt(np.mean((_dd(v) * 100.0) ** 2)))


def month_points(dates: pd.DatetimeIndex, v: np.ndarray, cutoff: pd.Period = MONTH_CUTOFF) -> pd.Series:
    """시작점 + 각 달의 마지막 관측(cutoff 달까지). 색인 = 실제 날짜."""
    s = pd.Series(v, index=dates)
    last = s.groupby(dates.to_period("M")).tail(1)
    last = last[last.index.to_period("M") <= cutoff]
    if last.index[0] == dates[0]:
        return last
    return pd.concat([s.iloc[:1], last])


def cagr(v0: float, v1: float, d0: pd.Timestamp, d1: pd.Timestamp) -> float:
    yrs = (d1 - d0).days / 365.25
    if yrs <= 0:
        return float("nan")
    if v1 <= 0:
        return -1.0
    return float((v1 / v0) ** (1.0 / yrs) - 1.0)


def yearly_returns(dates: pd.DatetimeIndex, v: np.ndarray) -> dict:
    """연도 → {ret, days, full}. 그해 마지막 값 ÷ 직전 해 마지막 값(첫해는 시작값). days = 덮은 달력 일수."""
    s = pd.Series(v, index=dates)
    out, prev_v, prev_d = {}, float(v[0]), dates[0]
    for y, g in s.groupby(dates.year):
        if y == dates[0].year and len(g) == 1:
            continue
        end_v, end_d = float(g.iloc[-1]), g.index[-1]
        start_d = max(prev_d, pd.Timestamp(f"{y - 1}-12-31"))
        days = (end_d - start_d).days
        out[int(y)] = {"ret": end_v / prev_v - 1.0, "days": int(days), "full": bool(days >= FULL_YEAR_MIN_DAYS)}
        prev_v, prev_d = end_v, end_d
    return out


def sharpe_sortino(r: np.ndarray, rf: np.ndarray) -> tuple[float, float]:
    """월 초과수익 기준 연율. 샤프 = 평균/표준편차·√12. 소르티노 = 연 평균 초과 ÷ (√평균(min(초과,0)²)·√12)."""
    ex = r - rf
    sd = ex.std(ddof=1) if len(ex) > 1 else 0.0
    if sd * math.sqrt(12) < MIN_EXCESS_VOL:                # 현금처럼 무위험과 거의 같은 곡선 — 비율이 뜻이 없다
        return float("nan"), float("nan")
    sh = float(ex.mean() / sd * math.sqrt(12))
    down = math.sqrt(float(np.mean(np.minimum(ex, 0.0) ** 2))) * math.sqrt(12)
    so = float(ex.mean() * 12 / down) if down > 0 else float("nan")
    return sh, so


def compute_metrics(dates: pd.DatetimeIndex, v: np.ndarray, rf_index: pd.Series, bench: "pd.Series | None" = None,
                    *, invest: float = INVEST) -> dict:
    """일별 가치 v(첫 값 = 시작점) 하나로 모든 지표를 낸다.

    낙폭·회복·울서·CAGR = 일별, 변동성·샤프·소르티노·상관·최악 12개월 = 월말(시장마다 마감 시각이 달라
    일별 상관·변동성이 왜곡되는 것을 피한다). 무위험 = ``rf_index``(원화 단기금리 누적 지수)의 같은 날 값.
    """
    dates = pd.DatetimeIndex(dates)
    v = np.asarray(v, dtype=float)
    d0, d1 = dates[0], dates[-1]
    g = cagr(v[0], v[-1], d0, d1)
    md = max_drawdown(dates, v)
    uw = longest_underwater(dates, v)
    me = month_points(dates, v)
    r_m = me.pct_change().dropna().to_numpy()
    rf_me = rf_index.reindex(rf_index.index.union(me.index)).ffill().reindex(me.index)
    rf_m = rf_me.pct_change().dropna().to_numpy()
    sh, so = sharpe_sortino(r_m, rf_m)
    yr = yearly_returns(dates, v)
    full = {y: x["ret"] for y, x in yr.items() if x["full"]}
    best_y = max(full, key=full.get) if full else None
    worst_y = min(full, key=full.get) if full else None
    vm = me.to_numpy()
    roll12 = vm[12:] / vm[:-12] - 1.0 if len(vm) > 12 else np.array([])
    out = {"start": str(d0.date()), "end": str(d1.date()), "years": (d1 - d0).days / 365.25,
           "total_return": float(v[-1] / v[0] - 1.0), "cagr": g,
           "best_year": {"year": best_y, "ret": full[best_y]} if best_y else None,
           "worst_year": {"year": worst_y, "ret": full[worst_y]} if worst_y else None,
           "mdd": md["mdd"], "mdd_peak": md["peak"], "mdd_trough": md["trough"], "mdd_recovery": md["recovery"],
           "longest_underwater_days": uw["days"], "longest_underwater_ongoing": uw["ongoing"],
           "longest_underwater_from": uw["from"],
           "vol": float(r_m.std(ddof=1) * math.sqrt(12)) if len(r_m) > 1 else float("nan"),
           "sharpe": sh, "sortino": so, "mar": g / abs(md["mdd"]) if md["mdd"] < 0 else float("nan"),
           "pos_year_ratio": float(np.mean([x > 0 for x in full.values()])) if full else float("nan"),
           "n_full_years": len(full),
           "worst_12m": float(roll12.min()) if len(roll12) else float("nan"),
           "worst_12m_end": str(me.index[12 + int(np.argmin(roll12))].date()) if len(roll12) else None,
           "ulcer": ulcer_index(v), "final_value_10m": float(invest * v[-1] / v[0]), "n_months": int(len(r_m))}
    if bench is not None:
        b = bench.reindex(bench.index.union(dates)).ffill()
        b0, b1 = b.get(d0), b.get(d1)
        if b0 is not None and np.isfinite(b0) and np.isfinite(b1):
            out["k200_cagr_same_window"] = cagr(b0, b1, d0, d1)
            out["excess_vs_k200"] = g - out["k200_cagr_same_window"]
            b_me = b.reindex(me.index).to_numpy()
            ok = np.isfinite(b_me)
            if ok.sum() > 13:
                rb = pd.Series(b_me[ok]).pct_change().dropna().to_numpy()
                rs = pd.Series(vm[ok]).pct_change().dropna().to_numpy()
                out["corr_k200"] = float(np.corrcoef(rs, rb)[0, 1]) if rs.std() > 0 else float("nan")
    out["yearly"] = {str(y): x for y, x in yr.items()}
    return out


def curves(dates: pd.DatetimeIndex, v: np.ndarray) -> dict:
    """차트용 월말 누적 곡선(시작 = 1)과 월말 낙폭."""
    me = month_points(pd.DatetimeIndex(dates), np.asarray(v, float))
    s = pd.Series(np.asarray(v, float), index=pd.DatetimeIndex(dates))
    dd_d = pd.Series(_dd(np.asarray(v, float)), index=s.index)
    dd_me = dd_d.groupby(dd_d.index.to_period("M")).min()
    dd_me = dd_me[dd_me.index <= MONTH_CUTOFF]
    return {"month_end": [str(d.date()) for d in me.index], "cum": [float(x / v[0]) for x in me.to_numpy()],
            "dd_month": [str(p) for p in dd_me.index], "dd_min": [float(x) for x in dd_me.to_numpy()]}


# ═════════════════════════════════ 입력 목록 ═════════════════════════════════

GA = "_workspace/analysis/global_alloc_20261006"
S30 = "_workspace/analysis/strategy_30y_20261006"


@dataclass
class Entry:
    id: str
    name: str
    desc: str
    group: str                 # global · global_wf · base · strategy
    status: str
    status_ref: str            # 판정 근거(문서 · 절)
    tax_note: str = ""
    extra: dict = field(default_factory=dict)


_OL_REF = "이 성적표에서 추가(같은 2배 모형 `global_alloc_b.lev_returns` · 상품 대응표 = " + GA + "/result_b.md §4)"

REGISTRY: list[Entry] = [
    # ── 단일 자산 보유(원화 총수익 · 1995~) ──
    Entry("K200", "KOSPI200 단순 보유", "KOSPI200 지수(배당 연 1.6% 근사)를 처음에 사서 끝까지 보유", "global", "기준선",
          f"{GA}/result_b.md §2.3 B0", "국내 주식 ETF — 매매차익 비과세(분배금만 15.4%)"),
    Entry("SPX", "S&P500 단순 보유(환노출)", "S&P500 총수익지수 원화 환산, 보유", "global", "기준선",
          f"{GA}/result.md §1(자산 표)", "국내 상장 해외 ETF — 차익 15.4%"),
    Entry("NDX", "나스닥100 단순 보유(환노출)", "나스닥100(배당 0.8% 근사) 원화 환산, 보유", "global", "기준선",
          f"{GA}/result.md §1", "차익 15.4%"),
    Entry("NKY", "닛케이225 단순 보유(환노출)", "닛케이225(배당 1.3% 근사) 원화 환산, 보유", "global", "참고",
          f"{GA}/result.md §1", "차익 15.4%"),
    Entry("HSCEI", "항셍중국기업 단순 보유(환노출)", "HSCEI(배당 3.0% 근사) 원화 환산, 보유", "global", "참고",
          f"{GA}/result.md §1", "차익 15.4%"),
    Entry("UST10", "미국채 10년 보유(환노출)", "만기 10년 액면채 모형 원화 환산, 보유", "global", "기준선",
          f"{GA}/result.md §1", "차익 15.4%"),
    Entry("USD", "달러 보유(원화 기준)", "원/달러 환율 변화 + 미국 3개월 금리", "global", "기준선",
          f"{GA}/result.md §1", "차익 15.4%"),
    Entry("CASH", "원화 현금(단기금리)", "원화 3개월 금리를 받는 현금", "global", "기준선",
          f"{GA}/result.md §1", "이자소득 15.4%"),
    # ── 정적 배분 ──
    Entry("B1", "60/40 (KOSPI200 60 · 미국채10년 40)", "원화 · 월말 결정 · 다음 종가 되돌림", "global", "기준선",
          f"{GA}/result_b.md §2.3 B1", "미국채 몫 차익 15.4%"),
    Entry("B", "7자산 동일 비중 · 월 되돌림", "한·미·나스닥·일·중 주식 · 미국채10년 · 달러 각 1/7 · 환노출",
          "global", "실패", f"{GA}/result_b.md §1(1995–2005 G1·G2·G4 실패)", "해외 몫 차익 15.4%"),
    Entry("B-A", "7자산 동일 비중 · 연 1회 되돌림", "B 와 같은 비중, 매년 마지막 거래일에만 되돌림", "global", "실패",
          f"{GA}/result_b.md §2.1(변형 6개 모두 불통과)", "해외 몫 차익 15.4%"),
    Entry("B-Q", "7자산 동일 비중 · 분기 되돌림", "B 와 같은 비중, 분기 말 되돌림", "global", "실패",
          f"{GA}/result_b.md §2.1", "해외 몫 차익 15.4%"),
    Entry("B-Band", "7자산 동일 비중 · 밴드 ±5%p", "어느 자산이든 목표에서 5%p 벗어나면 다음 종가에 되돌림", "global", "실패",
          f"{GA}/result_b.md §2.1", "해외 몫 차익 15.4%"),
    Entry("B-EQ", "5개 나라 주식만 동일 비중", "한·미·나스닥·일·중 각 20% · 월 되돌림", "global", "실패",
          f"{GA}/result_b.md §2.1", "해외 몫 차익 15.4%"),
    Entry("B-ERC", "7자산 위험 동일 기여", "126일 공분산으로 위험 기여가 같아지는 비중 · 월 되돌림", "global", "실패",
          f"{GA}/result_b.md §2.1", "해외 몫 차익 15.4%"),
    Entry("B-H", "7자산 동일 비중 · 환헤지", "해외 주식·미국채를 환헤지(금리차만 반영), 달러는 그대로", "global", "실패",
          f"{GA}/result_b.md §2.1", "해외 몫 차익 15.4%"),
    Entry("B3", "세계 60/40", "5개 나라 주식 각 12% · 미국채 40% · 월 되돌림", "global", "보류",
          f"{GA}/result.md §2·§6.2(사후 비교 — 판정 후보 아님)", "해외 몫 차익 15.4%"),
    # ── 레버리지(일일 2배 모형 · 환 1배) ──
    Entry("LEV3", "레버리지 2배 전부", "7자산 2배 상품을 1/7 씩 · 월 되돌림(총 노출 200%)", "global", "참고",
          f"{GA}/result_b.md §3(사전 규칙상 판정 근거 아님)", "국내 상장 레버리지 — KOSPI200 2배만 비과세"),
    Entry("LEV2a", "레버리지 50% + 현금 50%", "7자산 2배 상품 1/14 씩 + 원화 현금 50%(총 노출 100%)", "global", "참고",
          f"{GA}/result_b.md §3", "해외 2배 몫 차익 15.4%"),
    Entry("LEV2b", "레버리지 50% + 미국채·달러 50%", "7자산 2배 1/14 씩 + 미국채 25% + 달러 25%(총 노출 150%)",
          "global", "참고", f"{GA}/result_b.md §3", "해외 몫 차익 15.4%"),
    Entry("LEV4", "주식만 레버리지", "주식 5개는 2배 상품 1/7 씩 · 미국채·달러는 1배 1/7 씩", "global", "참고",
          f"{GA}/result_b.md §3", "해외 몫 차익 15.4%"),
    Entry("LK200", "KOSPI200 2배 단순 보유", "KOSPI200 일일 2배 모형(조달 = 한국 3개월 금리 + 연 0.8%)을 보유",
          "global", "참고", "이 성적표에서 추가(같은 2배 모형 `global_alloc_b.lev_returns`)", "국내 주식 지수 기반 — 도입 전 확인"),
    # ── 해외지수 레버리지(일일 2배 리셋 모형 · U = 지수 2배 + 환 1배(환노출) · H = 지수 2배 + 금리차(환헤지)) ──
    # 조달 = 그 나라 단기금리 + 연 0.8%(보수 포함) · 비용 왕복 0.38% · 상장 전 구간은 모형이다
    Entry("OL_SPX_U", "S&P500 2배 단순 보유(환노출)", "일일 2배 리셋 모형 · 국내 상장 상품 없음(환노출 S&P500 2배 없음) · 전 구간 모형",
          "global", "참고", _OL_REF, "국내 상장 해외 2배 — 차익 15.4%"),
    Entry("OL_SPX_H", "S&P500 2배 단순 보유(환헤지)", "일일 2배 리셋 모형 · 국내 상장 = TIGER 미국S&P500레버리지(합성 H) `225040` "
          "· 2015-07-29 상장 · 환헤지 · 상장 전 구간은 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_NDX_U", "나스닥100 2배 단순 보유(환노출)", "일일 2배 리셋 모형 · 국내 상장 = TIGER 미국나스닥100레버리지(합성) `418660` "
          "· 2022-02-22 상장 · 환노출 · 상장 전 구간은 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_NDX_H", "나스닥100 2배 단순 보유(환헤지)", "일일 2배 리셋 모형 · 국내 상장 = KODEX 미국나스닥100레버리지(합성 H) `409820` "
          "· 2021-12-09 상장 · 환헤지 · 상장 전 구간은 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_NKY_U", "닛케이225 2배 단순 보유(환노출)", "일일 2배 리셋 모형 · 국내 상장 상품 없음(닛케이225 2배 없음) · 전 구간 모형",
          "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_NKY_H", "닛케이225 2배 단순 보유(환헤지)", "일일 2배 리셋 모형 · 국내 상장 상품 없음(닛케이225 2배 없음 — 가장 가까운 것은 "
          "다른 지수인 ACE 일본TOPIX레버리지(H) `196030` · 2014-06-16 상장) · 전 구간 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_HSCEI_U", "HSCEI(중국) 2배 단순 보유(환노출)", "일일 2배 리셋 모형 · 국내 상장 상품 없음(환노출 HSCEI 2배 없음) · 전 구간 모형",
          "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_HSCEI_H", "HSCEI(중국) 2배 단순 보유(환헤지)", "일일 2배 리셋 모형 · 국내 상장 = KODEX 차이나H레버리지(H) `204450` "
          "· 2014-09-12 상장 · 환헤지 · 상장 전 구간은 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    Entry("OL_SPX_U50", "S&P500 2배 50% + 현금 50%(환노출)", "일일 2배 리셋 모형 50% + 원화 현금 50% · 월말 결정 · 다음 종가 되돌림 "
          "(총 노출 100%) · 국내 상장 상품 없음(환노출 S&P500 2배 없음) · 전 구간 모형", "global", "참고", _OL_REF,
          "2배 몫 차익 15.4% · 현금 이자 15.4%"),
    Entry("OL_NDX_U50", "나스닥100 2배 50% + 현금 50%(환노출)", "일일 2배 리셋 모형 50% + 원화 현금 50% · 월말 결정 · 다음 종가 되돌림 "
          "(총 노출 100%) · 국내 상장 = TIGER 미국나스닥100레버리지(합성) `418660` · 2022-02-22 상장 · 상장 전 구간은 모형",
          "global", "참고", _OL_REF, "2배 몫 차익 15.4% · 현금 이자 15.4%"),
    Entry("OL_EQ4_U", "해외 4지수 2배 동일 비중(환노출)", "S&P500·나스닥100·닛케이225·HSCEI 일일 2배 리셋 모형 각 25% · 월말 결정 · "
          "다음 종가 되돌림(총 노출 200%) · 국내 상장 환노출 2배는 나스닥100 `418660`(2022-02-22) 하나뿐, 나머지 셋은 없음 · "
          "상장 전·없는 상품 구간은 모형", "global", "참고", _OL_REF, "차익 15.4%"),
    # ── 1차 후보(걷기 전진 · 2006~) ──
    Entry("F1", "시계열 추세", "자산마다 최근 수익(또는 평균선 위)이면 1/7, 아니면 현금·미국채 · 해마다 직전 10년 최적 조합",
          "global_wf", "실패", f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    Entry("F2", "상대 모멘텀", "최근 수익 상위 N 개 자산만 균등 · 해마다 직전 10년 최적", "global_wf", "실패",
          f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    Entry("F3", "이중 모멘텀", "상위 N 개 중 현금보다 나은 것만, 나머지 현금·미국채", "global_wf", "실패",
          f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    Entry("F4", "역변동성(변동성 목표)", "덜 흔들린 자산일수록 많이 · 선택적 변동성 목표", "global_wf", "실패",
          f"{GA}/result.md §3·§6.1(가장 가까움)", "해외 몫 차익 15.4%"),
    Entry("F5", "결합 + 시장 유닛", "모멘텀 상위 + 역변동성 + 주식에 시장 유닛 배수", "global_wf", "실패",
          f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    Entry("F6", "장세 조건부", "자산별 방향·변동 라벨로 하락·변동이면 줄임", "global_wf", "실패",
          f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    Entry("W", "걷기 전진 W(전체 후보 중 선택)", "해마다 직전 10년 샤프 최고 조합을 모든 후보 중에서 골라 1년 사용",
          "global_wf", "실패", f"{GA}/result.md §3", "해외 몫 차익 15.4%"),
    # ── 바탕 층(069500 연속 계열 · 정수 주 계좌 · 1997~) ──
    Entry("BL_B0", "069500 단순 보유(바탕 층 계좌)", "069500(2002-10 전 = KOSPI200 가격지수, 배당 없음) 정수 주 보유",
          "base", "기준선", f"{S30}/etf_base/result.md §2.1 B0", "비과세"),
    Entry("BL_A2", "시장 유닛 m 비례 KOSPI200 · 남는 돈 현금", "069500 × m(1/0.75/0.5/0) 매일 맞춤 · 나머지 현금",
          "base", "보류", f"{S30}/etf_base/result.md §2.2 A2(세 구간 부호 갈림)", "비과세"),
    Entry("BL_A3", "시장 유닛 m 비례 KOSPI200 · 남는 돈 단기채", "069500 × m · 나머지 단기채 · 주 1회 · m 변화 0.5 이상일 때만",
          "base", "보류", f"{S30}/etf_base/result.md §2.2 A3(V 하한 < 0)", "단기채 몫 이자 15.4%"),
    Entry("BL_CH", "−10% 절반 덧씌움(30년 고른 판)", "069500 보유 · 60일 고점 −10% 에서 절반 · 새 20일 고가에 복귀 · 빠진 몫 달러·국고 반반",
          "base", "보류", f"{S30}/etf_base/result.md §2.1(J1 실패 → 도입 보류)", "달러·국고 몫 차익 15.4%"),
    Entry("BL_A5", "방어 교대(m=0 이면 달러·국고)", "069500 × m · m=0 이면 달러·국고 반반, 아니면 남는 몫 단기채 · 월 1회 · band 0.5",
          "base", "보류", f"{S30}/etf_base/result.md §2.2 A5(V 하한 < 0)", "달러·국고 몫 차익 15.4%"),
    Entry("BL_A1", "−15% 절반 덧씌움(5년 고른 판)", "069500 보유 · −15% 에서 절반 · m 회복에 복귀 · 빠진 몫 단기채",
          "base", "보류", f"{S30}/etf_base/result.md §2.2 A1", "단기채 몫 이자 15.4%"),
    Entry("BL_M1", "m=1 일 때만 전액(나머지 현금)", "069500 을 m=1 인 날만 전액, 아니면 현금", "base", "참고",
          f"{S30}/etf_base/result.md §1.2(비교 기준선)", "비과세"),
    # ── 개별 매매 전략(계좌 · 1997~) ──
    Entry("kojiro", "kojiro(고지로 대순환 스윙) 현행", "운영 DB 파라미터 · 시가 체결 · 시기별 비용 · 6슬롯 터틀", "strategy",
          "실패", f"{S30}/kojiro/result.md 「한 줄 판정」"),
    Entry("donchian", "donchian_swing 현행", "운영 파라미터 · 시기별 비용 · 계좌 C7", "strategy", "실패",
          f"{S30}/donchian/result.md 「결론」 A"),
    Entry("vcp", "vcp_breakout 현행(기본판)", "체결가 보정 +1.93% · 시기별 비용 + 0.15%p", "strategy", "실패",
          f"{S30}/vcp/result.md 표 A"),
    Entry("bfb", "bull_flag_breakout 현행(기본판)", "체결가 보정 +1.93% · 시기별 비용 + 0.15%p", "strategy", "실패",
          f"{S30}/bfb/result.md 표 A"),
    Entry("vb", "volatility_breakout 현행(기본판 낙관)", "체결 = 목표가 × 1.0193 · 시기별 비용 · 2슬롯 · 35%", "strategy",
          "실패", f"{S30}/vb/result.md 「결론」 1"),
    Entry("etf_trend", "etf_trend 현행", "ETF 추세 · 4슬롯 · 운영 사이저 · 시기별 비용 표", "strategy", "통과",
          f"{S30}/etf_base/result.md §1.2(현행 유지 — V'·H 통과, 2015 년부터 판정)"),
    Entry("mr_band", "평균회귀 — 볼린저 현행(5년 고른 판)", "F-liq · 30일 · 2.5σ · 밴드 닿으면 진입 · 중심선 청산 · 5슬롯 × 20%",
          "strategy", "실패", f"{S30}/mr_regime/result.md §2.1(V P1 실패 → 폐기)"),
    Entry("mr_fkeep", "평균회귀 — 볼린저 횡보장 고른 판(F-keep)", "횡보장만 · 20일 · 2.5σ · 재진입 · 중심선 청산 · 5슬롯 × 20%",
          "strategy", "실패", f"{S30}/mr_regime/result.md §2.2(폐기 — 계좌)"),
]


# ═════════════════════════════════ 로더 ═════════════════════════════════

@dataclass
class Curve:
    dates: pd.DatetimeIndex
    value: np.ndarray
    turnover_yr: "float | None" = None
    cost_yr: "float | None" = None
    after_tax_cagr: "float | None" = None
    source: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)


def load_global(parquet: str = GLOBAL_PARQUET) -> "tuple[dict[str, Curve], pd.Series]":
    """여러 나라 자산배분 — 2차 모듈의 전 기간(1995-01 첫 월말 결정일 ~ 마지막 거래일) 그대로."""
    from replay import global_alloc as G
    from replay import global_alloc_b as GB
    df = pd.read_parquet(parquet)
    m = GB.load(df, "U")
    a, b = GB.periods(m)["full"]
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    out: dict[str, Curve] = {}

    def one(w_name: str) -> np.ndarray:
        w = np.zeros(GB.N)
        w[GB.COLS.index(w_name)] = 1.0
        return w

    def run(mk, sched, tag, band_target=None):
        s = GB.simulate(mk, sched, a, b, band_target=band_target)
        st = GB.simulate(mk, sched, a, b, tax=True, band_target=band_target)
        v = s.value[a:b + 1]
        vt = st.value[a:b + 1]
        return Curve(m.dates[a:b + 1], v, s.turnover / yrs, s.cost / yrs,
                     cagr(vt[0], vt[-1], m.dates[a], m.dates[b]), source=f"global_alloc_b {tag}")

    for nm in ("B0", "B1", "B", "B-A", "B-Q", "B-Band", "B-EQ", "B-ERC", "LEV2a", "LEV2b", "LEV3", "LEV4"):
        out["K200" if nm == "B0" else nm] = run(m, GB.schedule(m, nm, a, b), nm)
    mh = GB.load(df, "U", hedged=True)
    out["B-H"] = run(mh, GB.schedule(mh, "B", a, b), "B hedged")
    for asset in ("SPX", "NDX", "NKY", "HSCEI", "UST10", "USD", "CASH", "LK200"):
        out[asset] = run(m, {a: one(asset)}, f"hold {asset}")
    dps = [int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b]
    w3 = np.zeros(GB.N)
    for x in G.EQUITY:
        w3[GB.COLS.index(x)] = 0.12
    w3[GB.COLS.index("UST10")] = 0.40
    out["B3"] = run(m, {i: w3 for i in dps}, "B3 세계 60/40")
    # 해외지수 2배 — m 의 L* 열 = U(환노출), mlh 의 L* 열 = H(환헤지). 1배 행(SPX·NDX …)과 같은 원천 열을 쓴다
    mlh = GB.load(df, "H")
    for x in ("SPX", "NDX", "NKY", "HSCEI"):
        out[f"OL_{x}_U"] = run(m, {a: one("L" + x)}, f"hold L{x} U")
        out[f"OL_{x}_H"] = run(mlh, {a: one("L" + x)}, f"hold L{x} H")
    for x in ("SPX", "NDX"):
        w = np.zeros(GB.N)
        w[GB.COLS.index("L" + x)] = 0.5
        w[GB.I_CASH] = 0.5
        out[f"OL_{x}_U50"] = run(m, {i: w for i in dps}, f"L{x} U 50 + CASH 50 월")
    w4 = np.zeros(GB.N)
    for x in ("SPX", "NDX", "NKY", "HSCEI"):
        w4[GB.COLS.index("L" + x)] = 0.25
    out["OL_EQ4_U"] = run(m, {i: w4 for i in dps}, "L4지수 U 동일 월")
    rf = pd.Series(np.cumprod(1 + m.ret[:, GB.I_CASH]), index=m.dates)
    return out, rf


def load_global_wf(parquet: str = GLOBAL_PARQUET) -> dict[str, Curve]:
    """1차 후보 F1~F6 · W — 걷기 전진이라 검증 구간(2005-12-29 ~)만 있다."""
    from replay import global_alloc as G
    df = pd.read_parquet(parquet)
    m = G.load_market(df)
    res = G.run_all(m, "M", tax=True, boot=False)
    a, b = res["_ab"]
    out = {}
    for nm in G.FAMILIES + ("W",):
        c = res["cands"][nm]
        v = res["_vals"][nm][a:b + 1]
        out[nm] = Curve(m.dates[a:b + 1], v, c["turnover_yr"], c["cost_yr"], c["after_tax"]["cagr"],
                        source="global_alloc.run_all(M)",
                        extra={"picks": res["picks"][nm]})
    return out


BL_START, BL_END = "1997-01-02", "2026-10-02"


def load_base() -> dict[str, Curve]:
    """바탕 층 — 30년 재검증과 같은 입력 · 같은 계좌(``run_account30``) · 1997-01-02 ~ 2026-10-02 한 번에."""
    from replay import base_layer as BL
    from replay import y30_etfbase_run as YR
    B = YR.base_inputs()
    cal, O, Cl, m, dd, c = B["cal"], B["O"], B["Cl"], B["m"], B["dd"], B["c"]
    g0, g1 = YR.win_idx(cal, (BL_START, BL_END))
    budget = float(YR.C.BUDGET_C7)
    combos = {"BL_B0": {"fam": "B0"},
              "BL_A2": YR.A_CANDS["A2"], "BL_A3": YR.A_CANDS["A3"], "BL_A5": YR.A_CANDS["A5"],
              "BL_A1": YR.A_CANDS["A1"],
              "BL_CH": {"fam": "B3", "base": "hold", "X": 0.10, "a": 0.5, "Y": "Y3", "park": "usdktb"}}
    t0, t1 = YR.win_idx(cal, YR.T_WIN)
    out = {}
    paths = {k: BL.weights_path(cb, cal, m, dd, c) for k, cb in combos.items()}
    paths["BL_M1"] = YR.m1_only_path(cal, m)
    for k, W in paths.items():
        r = YR.run_account30(W, O, Cl, g0, g1, B["cs"]["table"], cal)
        src = "y30_etfbase_run.m1_only_path" if k == "BL_M1" else f"run_account30 {BL.name(combos[k])}"
        out[k] = _account_curve(cal, g0, r, budget, src)
        rt = YR.run_account30(W, O, Cl, t0, t1, B["cs"]["table"], cal)       # 공표값 대조용 T 창(새 계좌)
        out[k].extra["check_T"] = {"cagr": rt["cagr"], "mdd": rt["mdd"]}
    return out


def _account_curve(cal, g0, r, budget, src) -> Curve:
    d_start = cal[g0 - 1] if g0 > 0 else cal[g0] - pd.Timedelta(1, unit="D")
    dates = pd.DatetimeIndex([d_start]).append(cal[g0:g0 + len(r["equity"])])
    return Curve(dates, np.r_[budget, r["equity"]], r.get("turnover_per_year"),
                 (r["cost_per_year_pct"] / 100.0) if r.get("cost_per_year_pct") is not None else None,
                 source=src, extra={"orders_per_year": r.get("orders_per_year"),
                                    "avg_stock_share": r.get("avg_stock_share")})


def load_books(book_dir: str) -> dict[str, Curve]:
    """``scoreboard_books`` 가 만든 개별 전략 계좌 곡선(대표 씨앗 일별 평가액 + 씨앗별 요약)."""
    out = {}
    if not os.path.isdir(book_dir):
        return out
    for fn in sorted(os.listdir(book_dir)):
        if not fn.endswith(".npz"):
            continue
        z = np.load(os.path.join(book_dir, fn), allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        dates = pd.DatetimeIndex(pd.to_datetime(z["dates"].astype(str)))
        out[fn[:-4]] = Curve(dates, z["equity"].astype(float), meta.get("turnover_yr"), meta.get("cost_yr"),
                             source=meta.get("source", ""), note=meta.get("note", ""), extra=meta)
    return out


# 외부 연구가 내는 성적표 항목 — 같은 지표 함수로 합친다(형식 = ``scoreboard.md`` §8 · ``EXTERNAL_FORMAT``).
# 상대 경로는 이 작업 트리 → 아래 후보 작업 트리 순으로 찾고, 어디에도 없으면 조용히 건너뛴다.
EXTERNAL_ENTRIES = [
    "_workspace/analysis/regime_gate_20261006/scoreboard_entries.json",   # 장세별 매매 중단 · 60/40 안정상승 레버리지 V1~V3
    "_workspace/analysis/regime_v2_20261006/scoreboard_entries.json",     # 장세 판단 재설계(가·나·다·라)
    "_workspace/analysis/sb_addons_20261006/scoreboard_entries.json",     # 낙폭 정지 DDP · 분기 순환 QR · 상위 5 QR5 · 재조정 WF
    "_workspace/analysis/sector_rs_20261006/scoreboard_entries.json",     # 섹터 RS 하위 30% 배제 SRS(전략별 · 민감도 · 균등 병행)
    "_workspace/analysis/gold_20261006/scoreboard_entries.json",          # 금 GOLD·AU_ · 나스닥100·2배·금·현금 NQG_(global 묶음)
    "_workspace/analysis/ra_us_20261006/scoreboard_entries.json",         # (라) 장세 규칙 미국 이식 RAUS_(S&P500·나스닥100 · 한국 폭 없음)
    "_workspace/analysis/ra_us_breadth_20261006/scoreboard_entries.json", # (라) 미국 이식 + 무료 시장 폭(진짜 폭 S5FI·NDFI · 상승 비율 · 동일가중) RAUSB_
]
EXTERNAL_ROOTS = (_ROOT, MAIN_REPO, "/Users/koscom/Projects/auto_stock_rgate", "/Users/koscom/Projects/auto_stock_regv2")
EXTERNAL_FORMAT = {
    "source": "만든 연구·코드 한 줄(필수)",
    "entries[].id": "고유 id — 기존 REGISTRY id 와 겹치면 안 된다(필수)",
    "entries[].name": "표에 쓸 이름(필수)",
    "entries[].desc": "설명 한 줄(필수)",
    "entries[].period": "[시작일, 끝일] YYYY-MM-DD(필수 — 곡선 첫·끝 날짜와 같아야 한다)",
    "entries[].curve.dates": "날짜 목록 — 첫 값은 시작점(투자 전날 · 누적 1.0). 일별이면 더 좋고 월말만이어도 된다(필수)",
    "entries[].curve.cum": "누적 가치(시작 = 1.0, 비용 차감 후 · 세전)(필수)",
    "entries[].yearly": "{연도: 수익률(소수)} — 성적표가 곡선에서 다시 낸 값과 대조한다(선택)",
    "entries[].status": "기준선 · 통과 · 실패 · 보류 · 참고 중 하나(선택, 기본 참고)",
    "entries[].status_ref": "판정 근거 문서·절(선택)",
    "entries[].group_title": "표 묶음 제목(선택, 기본 = 파일의 source)",
    "entries[].turnover_yr · cost_yr · after_tax_cagr": "연 회전 · 연 비용(소수) · 세후 연복리(선택)",
    "entries[].tax_note · source": "세금 메모 · 곡선 출처(선택)",
}
REQUIRED_EXT = ("id", "name", "desc", "period", "curve")


def _ext_path(rel: str) -> "str | None":
    if os.path.isabs(rel):
        return rel if os.path.exists(rel) else None
    for root in EXTERNAL_ROOTS:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            return p
    return None


def load_external(paths: "list[str] | None" = None, known_ids: "set | None" = None) -> "tuple[list[dict], list[str]]":
    """외부 entries json → [{entry, curve: Curve}] · 경고 목록. 없는 파일 · 형식이 어긋난 항목은 건너뛰고 경고로 남긴다."""
    out, warn = [], []
    known = set(known_ids or ())
    for rel in (paths if paths is not None else EXTERNAL_ENTRIES):
        p = _ext_path(rel)
        if p is None:
            warn.append(f"{rel} 없음 — 건너뜀")
            continue
        doc = json.load(open(p))
        for e in doc.get("entries", []):
            miss = [k for k in REQUIRED_EXT if k not in e]
            if miss or "dates" not in e.get("curve", {}) or "cum" not in e.get("curve", {}):
                warn.append(f"{p}: {e.get('id')} 필수 칸 없음 {miss or 'curve.dates/cum'} — 건너뜀")
                continue
            if e["id"] in known:
                warn.append(f"{p}: {e['id']} id 중복 — 건너뜀")
                continue
            dates = pd.DatetimeIndex(pd.to_datetime(e["curve"]["dates"]))
            v = np.asarray(e["curve"]["cum"], float)
            if len(dates) != len(v) or len(v) < 2 or not dates.is_monotonic_increasing or v[0] <= 0:
                warn.append(f"{p}: {e['id']} 곡선 길이·순서·시작값 이상 — 건너뜀")
                continue
            if [str(dates[0].date()), str(dates[-1].date())] != list(e["period"]):
                warn.append(f"{p}: {e['id']} period {e['period']} ≠ 곡선 {dates[0].date()}~{dates[-1].date()} — 곡선을 따른다")
            freq = "일별" if np.median(np.diff(dates.values).astype("timedelta64[D]").astype(int)) <= 3 else "월말"
            known.add(e["id"])
            c = Curve(dates, v, e.get("turnover_yr"), e.get("cost_yr"), e.get("after_tax_cagr"),
                      source=e.get("source") or doc.get("source", ""),
                      note=("" if freq == "일별" else "곡선이 월말뿐 — 낙폭·회복·울서가 월말 해상도"),
                      extra={"curve_freq": freq, "file": p, "yearly_given": e.get("yearly")})
            out.append({"entry": Entry(e["id"], e["name"], e["desc"], "external",
                                       e.get("status", "참고") if e.get("status", "참고") in STATUSES else "참고",
                                       e.get("status_ref", p), e.get("tax_note", ""),
                                       extra={"group_title": e.get("group_title") or doc.get("source", "외부 항목")}),
                        "curve": c})
    return out, warn


# ═════════════════════════════════ 조립 ═════════════════════════════════

def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _jload(rel: str) -> dict:
    p = os.path.join(_ROOT, rel)
    return json.load(open(p)) if os.path.exists(p) else {}


def reconcile(rows: list[dict]) -> list[dict]:
    """같은 경로로 다시 낸 값 ↔ 기존 결과 문서 원자료. 다르면 안 되는 값(같은 기간·같은 정의)만 대조한다."""
    by = {r["id"]: r for r in rows}
    out = []

    def add(item, ours, pub, ref, why="", unit="pct", src=""):
        if ours is None or pub is None:
            return
        out.append({"item": item, "ours": ours, "published": pub, "diff": ours - pub, "ref": ref, "unit": unit,
                    "src": src, "match": bool(abs(ours - pub) < 5e-4), "why": why})
    rb = _jload(f"{GA}/results_b.json").get("full", {}).get("metrics", {})
    for sid, key in (("K200", "B0"), ("B1", "B1"), ("B", "B"), ("B-A", "B-A"), ("B-Q", "B-Q"), ("B-Band", "B-Band"),
                     ("B-EQ", "B-EQ"), ("B-ERC", "B-ERC"), ("B-H", "B-H"), ("LEV2a", "LEV2a"), ("LEV2b", "LEV2b"),
                     ("LEV3", "LEV3"), ("LEV4", "LEV4")):
        if sid in by and key in rb:
            m = by[sid]["metrics"]
            add(f"{sid} 연복리(1995~2026)", m["cagr"], rb[key]["cagr"], f"{GA}/results_b.json full.metrics.{key}")
            add(f"{sid} 최대 낙폭", m["mdd"], rb[key]["mdd"], f"{GA}/results_b.json full.metrics.{key}")
            add(f"{sid} 최장 회복(일)", float(m["longest_underwater_days"]), float(rb[key]["recovery_days"]),
                f"{GA}/results_b.json full.metrics.{key}", unit="days")
            add(f"{sid} 세후 연복리", m["after_tax_cagr"], rb[key].get("after_tax"),
                f"{GA}/results_b.json full.metrics.{key}")
    r1 = _jload(f"{GA}/results.json").get("M", {}).get("cands", {})
    for sid in ("F1", "F2", "F3", "F4", "F5", "F6", "W"):
        if sid in by and sid in r1:
            m = by[sid]["metrics"]
            add(f"{sid} 연복리(2006~2026)", m["cagr"], r1[sid]["cagr"], f"{GA}/results.json M.cands.{sid}")
            add(f"{sid} 최대 낙폭", m["mdd"], r1[sid]["mdd"], f"{GA}/results.json M.cands.{sid}")
            add(f"{sid} 연 회전", m["turnover_yr"], r1[sid]["turnover_yr"], f"{GA}/results.json M.cands.{sid}", unit="x")
    eb = _jload(f"{S30}/etf_base/result.json").get("base", {})
    pub_T = {"BL_B0": eb.get("B0", {}).get("T"), "BL_CH": eb.get("chosen", {}).get("T"),
             "BL_M1": eb.get("m1_only", {}).get("T")}
    for an, sid in (("A1", "BL_A1"), ("A2", "BL_A2"), ("A3", "BL_A3"), ("A5", "BL_A5")):
        pub_T[sid] = eb.get("A", {}).get(an, {}).get("T")
    for sid, p in pub_T.items():
        if sid in by and p and "check_T" in by[sid]["extra"]:
            ck = by[sid]["extra"]["check_T"]
            add(f"{sid} T 창(1997~2012, 새 계좌) 연복리", ck["cagr"], p["cagr"], f"{S30}/etf_base/result.json base")
            add(f"{sid} T 창 최대 낙폭", ck["mdd"], p["mdd"], f"{S30}/etf_base/result.json base")
    for r in rows:
        ck = r["extra"].get("check_H") if r["group"] == "strategy" else None
        if not ck:
            continue
        same_252 = ck.get("published_ann") == "252"
        note = ck.get("note", "")
        add(f"{r['id']} H 창(2021~2026, 새 계좌) 연복리 씨앗 중앙", ck["cagr_median_252"] if same_252 else ck["cagr_median"],
            ck["published_cagr"], ck["published_ref"],
            note or ("공표값은 거래일 252일 = 1년 연율(성적표 본문은 달력 연율) — 같은 곡선을 252일 연율로 잰 값" if same_252 else ""))
        add(f"{r['id']} H 창 최대 낙폭 씨앗 중앙", ck["mdd_median"], ck["published_mdd"], ck["published_ref"],
            note or "공표값이 소수 셋째 자리까지라 ±0.0006 안이면 같다")
    for x in out:
        if x["unit"] == "days":
            x["match"] = abs(x["diff"]) < 0.5
        elif not x["match"] and "소수 셋째" in x["why"]:
            x["match"] = abs(x["diff"]) <= 0.0006
    return out


# ═════════════════════════════════ 문서 ═════════════════════════════════

def _p(x, d=1, sign=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    s = f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"
    return s.replace("-", "−")


def _f(x, d=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{d}f}".replace("-", "−")


def _won(x):
    if x is None:
        return "—"
    man = int(round(x / 1e4))
    if man >= 10_000:
        return f"{man // 10_000:,}억 {man % 10_000:,}만"
    return f"{man:,}만"


GROUP_TITLE = {"global": "여러 나라 자산배분 · 단일 자산(원화 총수익 지수 모형 · 1995-01 ~ 2026-10)",
               "global_wf": "1차 후보 — 걷기 전진(2005-12 ~ 2026-10 · 앞 10년은 학습에 썼다)",
               "base": "바탕 층 — 069500 연속 계열 · 정수 주 계좌 4,707,820원(1997-01 ~ 2026-10)",
               "strategy": "개별 매매 전략 — 계좌 4,707,820원 단독 풀 · 한 계좌로 이어서(1997-01 ~ 2026-10)"}
YEAR_COLS = ("K200", "B1", "B", "B-A", "LEV2a", "LEV3", "SPX", "NDX", "UST10", "USD", "F4", "W", "BL_A3", "BL_CH",
             "kojiro", "donchian", "etf_trend")


def write_md(res: dict, out_dir: str) -> str:
    rows = res["rows"]
    L = []
    a = L.append
    a("# 30년 전략 성적표 — 같은 잣대로 한 표에")
    a("")
    a(f"> 생성 {res['generated_kst']} KST · `tools/replay/scoreboard.py` · 원자료 `scoreboard.json`(전략 메타 · 지표 · 연도별 · "
      "월말 누적 · 월말 낙폭) · 연도 행렬 전체 `yearly_matrix.csv`")
    a("")
    a("**이 문서는 판정이 아니다.** 이미 끝난 연구들의 곡선을 같은 지표 함수 하나로 다시 쟀다. 새 최적화·새 선택은 없다. "
      "판정 칸은 각 결과 문서의 결론을 옮겨 적은 것이다.")
    a("")
    a("## 읽기 전에 — 주의")
    a("")
    a("- 🔴 **기간이 다른 전략끼리 숫자를 그대로 비교하지 않는다.** 1차 후보(F·W)는 2006 년부터, 바탕 층·개별 전략은 1997 년부터, "
      "자산배분·단일 자산은 1995 년부터다. 같은 창의 KOSPI200 과 비교하려면 「KOSPI200 대비 연 초과」 칸(그 전략의 기간으로 잘라 잰 값)을 본다.")
    a("- 🔴 **곡선 모형이 셋이다.** ① 자산배분·단일 자산 = 지수 일 수익(배당 근사 · ETF 보수 · 왕복 0.38%)으로 만든 비율 계좌, "
      "② 바탕 층 = 069500 연속 계열 정수 주 계좌(2002-10 전 KOSPI200 **가격** 지수 = 배당 없음 · 시기별 비용 표), "
      "③ 개별 전략 = 종목 일봉 신호 · 운영 사이저 · 시기별 비용. 그래서 「KOSPI200 단순 보유」 가 두 줄이다(K200 은 배당 1.6% 근사 포함 · BL_B0 은 1997~2002 배당 없음).")
    a("- 개별 전략은 30년 재검증이 창마다 새 계좌로 잰 것과 달리 **한 계좌로 30년을 이어서** 돌렸다. 계좌가 녹은 전략(VB · BFB · VCP · 평균회귀)은 "
      "녹은 뒤 1주도 못 사는 상태로 남아 그 뒤 해의 수익이 0 근처다 — 「그 해에 전략이 쉬었다」 가 아니라 「돈이 없었다」 다.")
    a("- 개별 전략 곡선은 씨앗 16 중 **최종 평가액 하위 중앙(8번째) 씨앗** 하나다. 씨앗 범위는 「씨앗 연복리 범위」 칸.")
    a("- 세전이다(「세후 연복리」 칸만 세후). 해외 ETF 차익 15.4% 를 넣는 세후판은 자산배분 모형만 있다. 국내 주식·KOSPI200 ETF 차익은 비과세라 "
      "개별 주식 전략·069500 보유는 세전 = 세후(거래세는 비용에 이미 들어 있다).")
    a("- 2025~2026 KOSPI200 급등(2025 +94% · 2026 9월까지 +85%)이 모든 기간 끝에 몰려 있어 KOSPI200 이 섞인 판의 연복리를 끌어올린다.")
    a("")
    groups = list(GROUP_TITLE.items()) + [("external", "외부 연구 항목 — 곡선을 다른 연구가 낸 것(형식 = §8)")]
    a("## 1. 수익 요약")
    a("")
    for grp, title in groups:
        g = [r for r in rows if r["group"] == grp]
        if not g:
            continue
        a(f"### {title}")
        a("")
        a("| 전략 | 판정 | 기간 | 최종 누적 | 연복리 | 최고 연간(연도) | 최악 연간(연도) | 1천만 원 → | KOSPI200 대비 연 초과 |")
        a("|---|---|---|---|---|---|---|---|---|")
        for r in g:
            m = r["metrics"]
            by, wy = m.get("best_year"), m.get("worst_year")
            a(f"| {r['name']} | {r['status']} | {m['start'][:7]} ~ {m['end'][:7]} | {_p(m['total_return'], 0, True)} | "
              f"**{_p(m['cagr'], 2, True)}** | {_p(by['ret'], 1, True) if by else '—'} ({by['year'] if by else ''}) | "
              f"{_p(wy['ret'], 1, True) if wy else '—'} ({wy['year'] if wy else ''}) | {_won(m['final_value_10m'])} | "
              f"{_p(m.get('excess_vs_k200'), 2, True)} |")
        a("")
    a("## 2. 위험")
    a("")
    for grp, title in groups:
        g = [r for r in rows if r["group"] == grp]
        if not g:
            continue
        a(f"### {title}")
        a("")
        a("| 전략 | 최대 낙폭 | 고점 → 바닥 → 회복 | 최장 회복 | 연 변동성 | 샤프 | 소르티노 | MAR | 울서 | 최악 12개월 | 플러스 해 |")
        a("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in g:
            m = r["metrics"]
            rec = m["mdd_recovery"] or "미회복"
            uw = f"{m['longest_underwater_days'] / 365.25:.1f}년" + (" (진행 중)" if m["longest_underwater_ongoing"] else "")
            a(f"| {r['name']} | **{_p(m['mdd'], 1, True)}** | {m['mdd_peak']} → {m['mdd_trough']} → {rec} | {uw} | "
              f"{_p(m['vol'], 1)} | {_f(m['sharpe'])} | {_f(m['sortino'])} | {_f(m['mar'])} | {_f(m['ulcer'], 1)} | "
              f"{_p(m['worst_12m'], 1, True)} | {_p(m['pos_year_ratio'], 0)} ({m['n_full_years']}해) |")
        a("")
    a("## 3. 비용 · 세금 · 관계")
    a("")
    a("| 전략 | 연 회전 | 연 비용 | 세후 연복리 | KOSPI200 과 월 상관 | 씨앗 연복리 범위 · 연 체결 | 세금 메모 |")
    a("|---|---|---|---|---|---|---|")
    for r in rows:
        m, ex = r["metrics"], r["extra"]
        seed = (f"{_p(ex.get('seed_cagr_min'), 1, True)} ~ {_p(ex.get('seed_cagr_max'), 1, True)} · "
                f"{ex.get('fills_per_year', 0):.0f}회" if r["group"] == "strategy" else "")
        a(f"| {r['name']} | {_f(m['turnover_yr'])} | {_p(m['cost_yr'], 2)} | {_p(m['after_tax_cagr'], 2, True)} | "
          f"{_f(m.get('corr_k200'))} | {seed} | {r['tax_note']} |")
    a("")
    a("- 연 회전 = 한쪽 매매 금액 ÷ 평균 평가액 ÷ 연수(1.0 = 1년에 전체를 한 번 갈아탐 · 단순 보유는 첫 매수만). "
      "개별 전략은 회전 대신 연 체결 수를 적는다(포지션 클래스마다 매매 금액 집계가 달라 같은 정의로 모으지 못했다).")
    a("")
    a("## 4. 연도별 수익률 (주요 전략 · %)")
    a("")
    cols = [c for c in YEAR_COLS if any(r["id"] == c for r in rows)]
    by_id = {r["id"]: r for r in rows}
    years = sorted({int(y) for r in rows for y in r["metrics"]["yearly"]})
    a("| 연 | " + " | ".join(cols) + " |")
    a("|---|" + "---|" * len(cols))
    for y in years:
        cells = []
        for c in cols:
            yy = by_id[c]["metrics"]["yearly"].get(str(y))
            cells.append("" if yy is None else (f"{yy['ret'] * 100:+.1f}".replace("-", "−") + ("" if yy["full"] else "ᵖ")))
        a(f"| {y} | " + " | ".join(cells) + " |")
    a("")
    a("ᵖ = 부분 연도(덮은 날 330일 미만 — 최고·최악 연간 계산에서 뺐다). 전 전략 행렬 = `yearly_matrix.csv`.")
    a("")
    a("## 5. 기존 결과 문서와의 대조")
    a("")
    rc = res["reconcile"]
    n_ok = sum(x["match"] for x in rc)
    a(f"같은 기간 · 같은 정의로 다시 낸 값 {len(rc)}개 중 **{n_ok}개 일치**(연복리·낙폭 차 < 0.05%p · 회전 차 < 0.0005 · "
      "회복 일수 같음). 전 항목 = `scoreboard.json` `reconcile`.")
    a("")
    srcs = {}
    for x in rc:
        srcs.setdefault(x["ref"].split(" ")[0], []).append(x)
    a("| 원자료 | 대조 수 | 일치 |")
    a("|---|---|---|")
    for k, xs in srcs.items():
        a(f"| `{k}` | {len(xs)} | {sum(x['match'] for x in xs)} |")
    a("")

    def fmt(x, key):
        v = x[key]
        if x["unit"] == "days":
            return f"{v:+.0f}" if key == "diff" else f"{v:.0f}"
        if x["unit"] == "x":
            return f"{v:+.4f}" if key == "diff" else f"{v:.2f}"
        return f"{v * 100:+.2f}%p".replace("-", "−") if key == "diff" else _p(v, 2, True)
    show = [x for x in rc if (not x["match"]) or "H 창" in x["item"] or "T 창" in x["item"]]
    a("개별 전략 · 바탕 층 대조(전부)와 불일치 항목:")
    a("")
    a("| 항목 | 성적표 | 원자료 | 차 | 일치 | 원인 |")
    a("|---|---|---|---|---|---|")
    for x in show:
        a(f"| {x['item']} | {fmt(x, 'ours')} | {fmt(x, 'published')} | {fmt(x, 'diff')} | "
          f"{'예' if x['match'] else '**아니오**'} | {x['why']} |")
    a("")
    a("- **다른 잣대라 맞추지 않은 것**: 샤프·변동성은 성적표가 **월** 수익 기준이다(자산배분 결과 문서의 「샤프(일)」 과 다르다 — "
      "시장마다 마감 시각이 달라 일 상관이 낮게 잡혀 분산 판에 유리해지는 것을 피했다). 30년 재검증의 개별 전략 연복리는 창마다 새 계좌라 "
      "한 계좌로 이은 성적표 값과 다른 숫자다(그래서 대조는 같은 창(H)을 따로 다시 돌린 값으로 했다).")
    a("")
    a("## 6. 지표 정의")
    a("")
    a("| 지표 | 정의 |")
    a("|---|---|")
    a("| 최종 누적 | 마지막 평가액 ÷ 시작 평가액 − 1 |")
    a("| 연복리(CAGR) | (마지막 ÷ 시작)^(1 ÷ 연수) − 1 · 연수 = 시작일~끝일 달력 일수 ÷ 365.25 |")
    a("| 최고 · 최악 연간 | 그해 마지막 평가액 ÷ 직전 해 마지막(첫해는 시작) − 1 · 덮은 날 330일 이상인 해만 |")
    a("| 최대 낙폭(MDD) | 일별 평가액이 직전 최고점 대비 가장 많이 내려간 비율 · 고점 · 바닥 · 회복(바닥 뒤 고점 값을 처음 되찾은 날) |")
    a("| 최장 회복 | 고점에서 그 고점을 되찾기까지 가장 긴 달력 기간(끝까지 못 되찾았으면 끝 날까지 · 「진행 중」) |")
    a("| 연 변동성 | 월말 수익의 표준편차 × √12 |")
    a(f"| 샤프 | 월 초과수익(전략 − 원화 단기금리) 평균 ÷ 표준편차 × √12 · 초과수익 연 변동 {MIN_EXCESS_VOL:.1%} 미만이면 「—」 |")
    a("| 소르티노 | 월 초과수익 평균 × 12 ÷ (√(평균(min(월 초과수익, 0)²)) × √12) — 하방 편차는 전체 달 수로 나눈다 |")
    a("| MAR | 연복리 ÷ |최대 낙폭| |")
    a("| 울서 지수 | √(일별 낙폭(%)² 의 평균) — 낙폭의 깊이와 머문 시간을 함께 잰다 |")
    a("| 최악 12개월 | 월말 평가액 12개월 이동 수익의 최솟값 |")
    a("| 플러스 해 | 온전한 해 중 연간 수익 > 0 인 비율 |")
    a("| KOSPI200 대비 연 초과 | 전략 연복리 − 같은 시작·끝일의 K200 행 연복리 |")
    a("| KOSPI200 과 월 상관 | 같은 월말 날짜의 월 수익 상관(K200 행) |")
    a("| 1천만 원 → | 1천만 원 × 마지막 ÷ 시작 |")
    a("| 무위험 | 원화 3개월 금리(FRED `IR3TIB01KRM156N`, 한 달 미룸) 누적 — `global_daily_krw.parquet` `CASH_ret` |")
    a("")
    a("## 7. 전략 설명 · 출처")
    a("")
    a("| id | 전략 | 설명 | 판정 근거 | 곡선 출처 |")
    a("|---|---|---|---|---|")
    for r in rows:
        a(f"| `{r['id']}` | {r['name']} | {r['desc']}{(' — ' + r['note']) if r['note'] else ''} | `{r['status_ref']}` | "
          f"`{r['source']}` |")
    a("")
    a("## 8. 다시 돌리기 · 전략 덧붙이기")
    a("")
    a("```")
    a("python tools/replay/scoreboard_books.py <out_dir>/books        # 개별 전략 계좌 곡선(전략당 수 초 ~ 수 분)")
    a("python tools/replay/scoreboard.py <out_dir>                     # json · md · csv")
    a("```")
    a("")
    a("- 새 전략(예: 주기적 재조정 결과)은 `scoreboard.py` 의 `REGISTRY` 에 `Entry` 한 줄 + 일별 가치 곡선을 돌려주는 로더 한 개를 붙인다. "
      "곡선이 다른 연구에서 나오면 `books/<id>.npz`(키 `dates` · `equity` · `meta`) 로 떨어뜨리면 `load_books` 가 읽는다.")
    a(f"- 빠진 행: {', '.join(res['missing']) or '없음'}")
    a("")
    a("### 외부 연구 항목 붙이기 — `scoreboard_entries.json` 형식")
    a("")
    a("다른 연구(장세별 매매 중단 · 60/40 안정상승 레버리지 V1~V3 · 나중의 주기적 재조정 결과)는 곡선을 아래 json 으로 내고, "
      "`scoreboard.py` 의 `EXTERNAL_ENTRIES` 목록에 그 경로를 한 줄 더한다(또는 `build(..., external=[경로])`). "
      "상대 경로는 이 작업 트리 → 본 작업 트리 → `auto_stock_rgate` 순으로 찾고, **파일이 없으면 건너뛴다**(경고만 `scoreboard.json` "
      "`external_warnings` 에 남는다). 지표는 기존 행과 같은 `compute_metrics` 로 곡선에서 다시 낸다 — 파일의 숫자를 옮겨 적지 않는다.")
    a("")
    a("```json")
    a('{"source": "regime_gate 2026-10-06 · tools/replay/<코드>.py",')
    a(' "entries": [')
    a('  {"id": "RG_60_40_V1", "name": "60/40 안정상승 레버리지 V1", "desc": "설명 한 줄",')
    a('   "period": ["1995-01-27", "2026-10-02"],')
    a('   "curve": {"dates": ["1995-01-27", "1995-01-31", "..."], "cum": [1.0, 1.004, "..."]},')
    a('   "yearly": {"1995": 0.048, "1996": -0.16},')
    a('   "status": "참고", "status_ref": "_workspace/analysis/regime_gate_20261006/result.md §2",')
    a('   "turnover_yr": 0.8, "cost_yr": 0.0015, "after_tax_cagr": 0.081, "tax_note": "해외 몫 차익 15.4%",')
    a('   "source": "곡선을 만든 함수"}')
    a(' ]}')
    a("```")
    a("")
    a("| 칸 | 뜻 |")
    a("|---|---|")
    for k, v in EXTERNAL_FORMAT.items():
        a(f"| `{k}` | {v} |")
    a("")
    a("- 곡선은 **시작점(누적 1.0)을 첫 값으로** 넣는다(투자 직전 날짜). 비용 차감 후 · 세전 · 원화.")
    a("- 월말 곡선만 주면 낙폭 · 회복 · 울서가 월말 해상도로 잡혀 일별 곡선 행보다 얕게 나온다 — 행 메모에 「곡선이 월말뿐」 이 붙는다. "
      "가능하면 일별 곡선을 준다.")
    a("- `yearly` 를 주면 성적표가 곡선에서 다시 낸 연도 수익과의 최대 차이를 `metrics.yearly_given_diff_max` 에 적는다(0 이 아니면 곡선과 표가 어긋난 것).")
    a("- 같은 잣대를 위해 무위험 = 원화 3개월 금리, 기준 = K200 행(1995~)을 쓴다. 기간이 다르면 「KOSPI200 대비 연 초과」 칸으로 본다.")
    ew = res.get("external_warnings") or []
    a(f"- 이번 실행의 외부 파일: {', '.join('`' + x + '`' for x in res.get('external_files', [])) or '없음'} · "
      f"경고: {'; '.join(ew) or '없음'}")
    path = os.path.join(out_dir, "scoreboard.md")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def write_yearly_csv(rows: list[dict], out_dir: str) -> str:
    years = sorted({int(y) for r in rows for y in r["metrics"]["yearly"]})
    df = pd.DataFrame(index=years)
    for r in rows:
        df[r["id"]] = [r["metrics"]["yearly"].get(str(y), {}).get("ret") for y in years]
    df.index.name = "year"
    path = os.path.join(out_dir, "yearly_matrix.csv")
    df.to_csv(path, float_format="%.6f")
    return path


def build(out_dir: str, book_dir: "str | None" = None, parquet: str = GLOBAL_PARQUET,
          external: "list[str] | None" = None) -> dict:
    t0 = time.time()
    curves_all, rf = load_global(parquet)
    print(f"[scoreboard] global {time.time() - t0:.0f}s", flush=True)
    curves_all.update(load_global_wf(parquet))
    print(f"[scoreboard] global_wf {time.time() - t0:.0f}s", flush=True)
    curves_all.update(load_base())
    print(f"[scoreboard] base {time.time() - t0:.0f}s", flush=True)
    curves_all.update(load_books(book_dir or os.path.join(out_dir, "books")))
    print(f"[scoreboard] books {sorted(k for k in curves_all if k in {e.id for e in REGISTRY if e.group == 'strategy'})}",
          flush=True)
    ext, ext_warn = load_external(external, {e.id for e in REGISTRY})
    for x in ext:
        curves_all[x["entry"].id] = x["curve"]
    print(f"[scoreboard] external {[x['entry'].id for x in ext]} · {ext_warn}", flush=True)
    k = curves_all["K200"]
    bench = pd.Series(k.value, index=k.dates)
    rows, missing = [], []
    for e in REGISTRY + [x["entry"] for x in ext]:
        assert e.status in STATUSES, e.status
        c = curves_all.get(e.id)
        if c is None:
            missing.append(e.id)
            continue
        mt = compute_metrics(c.dates, c.value, rf, bench)
        mt["turnover_yr"] = c.turnover_yr
        mt["cost_yr"] = c.cost_yr
        mt["after_tax_cagr"] = c.after_tax_cagr
        if e.group == "external" and c.extra.get("yearly_given"):
            mt["yearly_given_diff_max"] = max((abs(mt["yearly"][str(y)]["ret"] - float(r))
                                               for y, r in c.extra["yearly_given"].items() if str(y) in mt["yearly"]),
                                              default=None)
        rows.append({"id": e.id, "name": e.name, "desc": e.desc, "group": e.group, "status": e.status,
                     "status_ref": e.status_ref, "tax_note": e.tax_note, "source": c.source, "note": c.note,
                     "extra": c.extra, "metrics": mt, "curves": curves(c.dates, c.value)})
    res = {"generated_kst": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"),
           "rules": {"invest": INVEST, "month_cutoff": str(MONTH_CUTOFF), "full_year_min_days": FULL_YEAR_MIN_DAYS,
                     "rf": "원화 3개월 금리(FRED IR3TIB01KRM156N, 한 달 미룸) 누적 — global_daily_krw CASH_ret",
                     "bench": "K200 행(원화 총수익 지수 모형, 1995~)"},
           "missing": missing, "external_files": list(EXTERNAL_ENTRIES if external is None else external),
           "external_warnings": ext_warn, "rows": rows}
    res["reconcile"] = reconcile(rows)
    res = _clean(res)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scoreboard.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    write_yearly_csv(res["rows"], out_dir)
    write_md(res, out_dir)
    print(f"[scoreboard] done {len(rows)} rows · missing {missing} · {time.time() - t0:.0f}s", flush=True)
    return res


if __name__ == "__main__":
    od = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "_workspace/analysis/scoreboard_20261006")
    build(od, sys.argv[2] if len(sys.argv) > 2 else None)
