"""성적표 덧붙임 공통 층 — 사전 등록 ``_workspace/analysis/sb_addons_20261006/prereg.md``.

- ``DDPause``      : 낙폭 정지(§1-2) — 전날 종가 평가액을 받아 그날 신규 매수 허용 여부를 낸다.
- ``gate_function``: 30년 계좌 함수의 「그날 신호 목록」 한 줄 앞에 관문을 끼운 사본을 만든다(원 파일 무수정).
- ``ddp_curve``    : 곡선형 항목의 근사 낙폭 정지(§1-4).
- ``rotation``     : 분기 순환 포트폴리오(§2 · §3) — 편입 전 재정규화 · 떠다니는 비중 · 회전 비용.
- ``live_curve``   : 실거래 왕복 → 근사 단독 계좌 곡선(§2-1).
"""
from __future__ import annotations

import inspect
import re
import textwrap

import numpy as np
import pandas as pd

DD_THR = 0.20
PAUSE_DAYS = 30
COST_RT = 0.0038


# ═════════════════════════════════ 낙폭 정지 ═════════════════════════════════

class DDPause:
    """한 계좌 실행 하나의 낙폭 정지 상태. ``allow(e_prev)`` 를 영업일마다 정확히 한 번 부른다.

    e_prev = 그날 장 시작 시점에 아는 가장 최근 종가 평가액(첫날은 시작 평가액).
    t 종가 E_t ≤ (1−thr)·P → t+1 ~ t+days 금지 → t+days+1(재개일) 허용 · 검사 없음 → 다음 날 P = E_재개일.
    """

    def __init__(self, thr: float = DD_THR, days: int = PAUSE_DAYS):
        self.thr, self.days = thr, days
        self.peak = None
        self.left = 0
        self.resume = False
        self.reset = False
        self.n_days = 0
        self.events: list = []          # (발동을 본 날 색인 = t+1, 그때 평가액, 기준 최고치)
        self.paused_days = 0

    def allow(self, e_prev: float) -> bool:
        i = self.n_days
        self.n_days += 1
        if self.peak is None:
            self.peak = float(e_prev)
        if self.left > 0:
            return self._paused()
        if self.resume:
            self.resume = False
            self.reset = True
            return True
        if self.reset:
            self.peak = float(e_prev)
            self.reset = False
        else:
            self.peak = max(self.peak, float(e_prev))
        if self.peak > 0 and e_prev <= (1.0 - self.thr) * self.peak:
            self.events.append((i, float(e_prev), float(self.peak)))
            self.left = self.days
            return self._paused()
        return True

    def _paused(self) -> bool:
        self.left -= 1
        self.paused_days += 1
        if self.left == 0:
            self.resume = True
        return False


class GateHub:
    """계좌 실행이 여러 번(씨앗 · 창) 이어질 때 실행마다 새 ``DDPause`` 를 만든다.

    새 실행 감지 = 같은 함수 안에서 gd 가 줄거나 같아지면(루프가 처음부터 다시 돈다). 관문이 꺼져 있으면
    항상 허용하되 날 수는 센다(대조용).
    """

    def __init__(self, enabled: bool = True, thr: float = DD_THR, days: int = PAUSE_DAYS):
        self.enabled, self.thr, self.days = enabled, thr, days
        self.runs: list = []
        self._last_gd = None
        self.dropped: list = []          # 실행별 버린 신호 수

    def allow(self, gd: int, e_prev: float, n_sig: int = 0) -> bool:
        if self._last_gd is None or gd <= self._last_gd:
            self.runs.append(DDPause(self.thr, self.days))
            self.dropped.append(0)
        self._last_gd = gd
        ok = self.runs[-1].allow(e_prev)
        if not self.enabled:
            return True
        if not ok:
            self.dropped[-1] += int(n_sig)
        return ok

    def reset(self):
        self.runs, self.dropped, self._last_gd = [], [], None


_LINE = re.compile(r"^(?P<ind>[ \t]*)todays = list\((?P<src>[A-Za-z_][A-Za-z_0-9]*)\.get\(gd, \[\]\)\)[ \t]*$", re.M)


def gate_source(src: str) -> "tuple[str, int]":
    """``todays = list(X.get(gd, []))`` → 관문을 거친 같은 줄. 반환 = (새 소스, 바꾼 줄 수)."""
    def rep(m):
        ind, s = m.group("ind"), m.group("src")
        return (f"{ind}_sbx_raw = list({s}.get(gd, []))\n"
                f"{ind}todays = _sbx_raw if _SB_GATE.allow(gd, eq_prev, len(_sbx_raw)) else []")
    return _LINE.subn(rep, src)


def gate_function(module, name: str, hub: GateHub):
    """``module.name`` 을 관문 사본으로 바꾼다. 반환 = 원 함수(되돌리기용). 바꾼 줄이 정확히 1 이어야 한다."""
    orig = getattr(module, name)
    src = textwrap.dedent(inspect.getsource(orig))
    new, n = gate_source(src)
    if n != 1:
        raise RuntimeError(f"[sb_addons] {module.__name__}.{name}: 신호 줄 {n}개(1 이어야 한다)")
    ns = module.__dict__
    ns["_SB_GATE"] = hub
    code = compile(new, f"<sb_gate {module.__name__}.{name}>", "exec")
    loc: dict = {}
    exec(code, ns, loc)
    setattr(module, name, loc[name])
    return orig


# ═════════════════════════════════ 곡선 근사 낙폭 정지 ═════════════════════════════════

def ddp_curve(v: np.ndarray, rf_ret: np.ndarray, thr: float = DD_THR, days: int = PAUSE_DAYS,
              cost_side: float = COST_RT / 2) -> "tuple[np.ndarray, list]":
    """곡선 v(일별 가치, 첫 값 = 시작) → 근사 DDP 곡선. rf_ret[i] = i 날 현금 일 수익(i ≥ 1).

    t 종가 낙폭 ≤ −thr → t 종가에 현금화(편도 비용) → t+1 ~ t+days 현금 → t+days 종가에 재진입(편도 비용) ·
    재진입 평가액이 새 기준 최고치. 반환 = (곡선, [(현금화 색인, 재진입 색인)]).
    """
    v = np.asarray(v, float)
    r = np.zeros(len(v))
    r[1:] = v[1:] / v[:-1] - 1.0
    out = np.empty(len(v))
    out[0] = v[0]
    peak = out[0]
    in_cash, left, ev, t_out = False, 0, [], None
    for i in range(1, len(v)):
        if in_cash:
            out[i] = out[i - 1] * (1.0 + rf_ret[i])
            left -= 1
            if left == 0:
                out[i] *= (1.0 - cost_side)
                in_cash = False
                peak = out[i]
                ev.append((t_out, i))
            continue
        out[i] = out[i - 1] * (1.0 + r[i])
        peak = max(peak, out[i])
        if out[i] <= (1.0 - thr) * peak:
            out[i] *= (1.0 - cost_side)
            in_cash, left, t_out = True, days, i
    if in_cash:
        ev.append((t_out, None))
    return out, ev


# ═════════════════════════════════ 분기 순환 ═════════════════════════════════

def quarter_ends(dates: pd.DatetimeIndex) -> np.ndarray:
    """각 분기의 마지막 날짜 색인(마지막 분기 = 자료 끝이면 넣지 않는다 — 리밸런싱이 뜻이 없다)."""
    q = dates.to_period("Q")
    last = np.nonzero(np.r_[q[1:] != q[:-1], False])[0]
    return last


def rank_order(rets: dict, order: "list[str]") -> "list[str]":
    """직전 분기 수익 내림차순. 같으면 ``order`` 의 앞쪽."""
    pos = {k: i for i, k in enumerate(order)}
    return sorted(rets, key=lambda k: (-rets[k], pos[k]))


def weights_top(ranked: "list[str]", top_w: float) -> dict:
    """1위 top_w · 나머지 균등. 1개면 100%."""
    n = len(ranked)
    if n == 0:
        return {}
    if n == 1:
        return {ranked[0]: 1.0}
    rest = (1.0 - top_w) / (n - 1)
    return {k: (top_w if i == 0 else rest) for i, k in enumerate(ranked)}


def weights_topk(ranked: "list[str]", k: int, shares: "list[float]") -> dict:
    """상위 k 에 shares(순위 순) — 편입 전략이 k 개 미만이면 있는 만큼만 주고 Σ 로 정규화."""
    sel = ranked[:k]
    w = {s: shares[i] for i, s in enumerate(sel)}
    tot = sum(w.values())
    return {s: x / tot for s, x in w.items()} if tot > 0 else {}


def weights_fixed(avail: "list[str]", base: dict) -> dict:
    """고정 비중을 편입 전략끼리 재정규화(편입 전 전략 몫을 나눈다). 편입 전략 몫 합이 0 이면 빈 dict."""
    w = {s: float(base.get(s, 0.0)) for s in avail}
    tot = sum(w.values())
    return {s: x / tot for s, x in w.items() if x > 0} if tot > 0 else {}


def weights_equal(avail: "list[str]") -> dict:
    return {s: 1.0 / len(avail) for s in avail} if avail else {}


def align(curves: "dict[str, tuple]") -> "tuple[pd.DatetimeIndex, dict, dict]":
    """{id: (dates, values)} → 공통 날짜(합집합) · 일 수익 행렬(편입 전 NaN) · 편입 시작 색인."""
    idx = None
    for d, _ in curves.values():
        idx = pd.DatetimeIndex(d) if idx is None else idx.union(pd.DatetimeIndex(d))
    rets, start = {}, {}
    for k, (d, v) in curves.items():
        s = pd.Series(np.asarray(v, float), index=pd.DatetimeIndex(d))
        s = s[~s.index.duplicated(keep="last")]
        first = s.index[0]
        full = s.reindex(idx).ffill()
        r = full.pct_change().to_numpy()
        i0 = int(idx.searchsorted(first))
        r[: i0 + 1] = np.nan
        r = np.where(np.isfinite(r), r, np.nan)
        r[i0 + 1:] = np.nan_to_num(r[i0 + 1:], nan=0.0)
        rets[k] = r
        start[k] = i0
    return idx, rets, start


def rotation(curves: "dict[str, tuple]", order: "list[str]", rule, *, cost_side: float = COST_RT / 2,
             stop: "dict | None" = None) -> dict:
    """분기 순환 포트폴리오.

    rule(ranked, avail) → 목표 비중 dict. ranked = 직전 분기 수익 순위(편입 전략만) · avail = 편입 전략(order 순).
    첫 리밸런싱(직전 분기 없음) 전에는 편입 전략 균등. 편입 = 그 곡선의 시작점 이후 첫 분기말부터.

    stop(추가 등록 QRX) = {"dd": 0.10, "days": 30, "rf": 일 현금 수익 배열(합집합 달력 길이), "extra": 편도 추가}:
    t 종가 ≤ (1−dd)·P → t+1 종가 전량 매도 → 30영업일 현금 → 31번째 영업일 종가에 그 시점 목표 비중으로 재진입 ·
    재진입 값이 새 P. 현금 중 분기말은 목표만 갱신(거래 없음).
    반환 = dates · value(첫 값 1.0) · 리밸런싱 기록 · (stop 이면) 발동 기록.
    """
    idx, R, start = align(curves)
    n = len(idx)
    ids = [k for k in order if k in R]
    V = np.empty(n)
    V[0] = 1.0
    avail0 = [k for k in ids if start[k] == 0]
    target = weights_equal(avail0)
    h = dict(target)
    qe = set(quarter_ends(idx).tolist())
    lvl = {k: 1.0 for k in ids}                 # 직전 분기말 이후 누적(순위용 · 현금 중에도 섀도로 센다)
    since = {k: (0 if start[k] == 0 else None) for k in ids}
    log, events = [], []
    mode, peak, cash_n, ev = "inv", 1.0, 0, None
    side_x = cost_side + (stop.get("extra", 0.0) if stop else 0.0)
    for i in range(1, n):
        for k in ids:
            if np.isnan(R[k][i]):
                continue
            if since[k] is None:
                since[k] = i
            lvl[k] *= 1.0 + R[k][i]
            if k in h:
                h[k] *= 1.0 + R[k][i]
        if mode == "cash":
            V[i] = V[i - 1] * (1.0 + float(stop["rf"][i]))
            cash_n += 1
        else:
            V[i] = sum(h.values()) if h else V[i - 1]
        if mode == "sell":                           # 발동 다음 날 종가에 전량 매도
            V[i] *= (1.0 - side_x)
            h, mode, cash_n = {}, "cash", 0
            ev["sell"] = i
        if i in qe:
            avail = [k for k in ids if since[k] is not None and start[k] < i]
            rets = {k: lvl[k] - 1.0 for k in avail}
            ranked = rank_order(rets, order)
            target = rule(ranked, avail)
            tot = V[i]
            if mode == "cash":
                turn, cost = 0.0, 0.0
            else:
                drift = {k: h.get(k, 0.0) / tot for k in set(h) | set(target)} if tot > 0 else {}
                turn = sum(abs(target.get(k, 0.0) - drift.get(k, 0.0)) for k in drift)
                cost = tot * turn * cost_side
                V[i] = tot - cost
                h = {k: w * V[i] for k, w in target.items() if w > 0}
            log.append({"date": str(idx[i].date()), "ranked": ranked, "rets": rets,
                        "weights": {k: round(w, 6) for k, w in target.items()}, "turnover": turn,
                        "cost": cost / tot if tot > 0 else 0.0, "in_cash": mode == "cash"})
            lvl = {k: 1.0 for k in ids}
        if stop is None:
            continue
        if mode == "cash" and cash_n == stop["days"] + 1:     # 31번째 영업일 종가 재진입
            V[i] *= (1.0 - side_x)
            h = {k: w * V[i] for k, w in target.items() if w > 0}
            mode, peak = "inv", V[i]
            ev["reenter"] = i
            events.append(ev)
            ev = None
        elif mode == "inv":
            peak = max(peak, V[i])
            if V[i] <= (1.0 - stop["dd"]) * peak:
                mode = "sell"
                ev = {"trigger": i, "peak": peak, "value": V[i]}
    if ev is not None:
        events.append(ev)
    ev_out = [{k: (str(idx[v].date()) if k in ("trigger", "sell", "reenter") else v) for k, v in e.items()}
              for e in events]
    return {"dates": idx, "value": V, "log": log, "events": ev_out,
            "start": {k: str(idx[start[k]].date()) for k in ids}}


# ═════════════════════════════════ 실거래 근사 곡선 ═════════════════════════════════

def live_curve(trips: list, strategy: str, cal: pd.DatetimeIndex, start: str, pos_ratio: float,
               end: "str | None" = None) -> "tuple[pd.DatetimeIndex, np.ndarray, int]":
    """실거래 왕복 → 매도일에 Σ(net × pos_ratio) 만큼 복리로 변하는 곡선. 첫 값 = 시작점(start 직전 거래일) 1.0."""
    st = pd.Timestamp(start)
    days = cal[(cal >= st) & ((cal <= pd.Timestamp(end)) if end else True)]
    pre = cal[cal < st]
    d0 = pre[-1] if len(pre) else st - pd.Timedelta(1, unit="D")
    by = {}
    n = 0
    for t in trips:
        if t["strategy"] != strategy or pd.Timestamp(t["buy_date"]) < st:
            continue
        sd = pd.Timestamp(t["sell_date"])
        by[sd] = by.get(sd, 0.0) + float(t["net"]) * pos_ratio
        n += 1
    v = [1.0]
    for d in days:
        v.append(v[-1] * (1.0 + by.get(d, 0.0)))
    return pd.DatetimeIndex([d0]).append(days), np.asarray(v), n


# ═════════════════════════════════ 대표 씨앗 · 구간 지표 ═════════════════════════════════

def rep_index(finals) -> int:
    """씨앗 최종 평가액 하위 중앙(성적표 ``scoreboard_books.pack`` 과 같다)."""
    order = np.argsort(np.asarray(finals, float), kind="stable")
    return int(order[(len(order) - 1) // 2])


PERIODS = (("학습", "1997-01-01", "2012-12-31"), ("검증", "2013-01-01", "2020-12-31"),
           ("보류", "2021-01-01", "2026-12-31"))


def period_stats(dates: pd.DatetimeIndex, v: np.ndarray, a: str, b: str) -> "dict | None":
    """구간 직전 값을 시작으로 [a, b] 만 잘라 연복리 · 낙폭 · 누적."""
    dates = pd.DatetimeIndex(dates)
    v = np.asarray(v, float)
    m = (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))
    if m.sum() < 2:
        return None
    i0 = int(np.argmax(m))
    i1 = int(len(m) - 1 - np.argmax(m[::-1]))
    j = i0 - 1 if i0 > 0 else i0
    seg = v[j:i1 + 1]
    if seg[0] <= 0:
        return {"cagr": float("nan"), "mdd": float("nan"), "total": float("nan")}
    yrs = max((dates[i1] - dates[j]).days, 1) / 365.25
    tot = seg[-1] / seg[0]
    return {"cagr": float(tot ** (1 / yrs) - 1) if tot > 0 else -1.0,
            "mdd": float((seg / np.maximum.accumulate(seg) - 1).min()), "total": float(tot - 1),
            "start": str(dates[j].date()), "end": str(dates[i1].date())}
