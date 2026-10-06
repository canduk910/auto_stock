"""(라) 장세 문을 운용 전략에 고정 규칙으로 — 순수 층(사전 등록 ``_workspace/analysis/ra_gate_20261006/prereg.md``).

- 칸 정의 ``ALLOW`` · ``BLOCK`` · 날짜 조회 ``AsOf``(D 보다 **엄격히 앞선** 마지막 날의 값 — D−1 종가 상태)
- 시장 유닛 날짜 조회 ``mu_asof``(운영 ``classify`` 경유 ``audit.market_unit.m_at_bars`` + 묵음 10일 규칙)
- 관문 ``RaGate`` — ``sector_rs_core.SectorGate`` 의 실행 기록 틀을 물려받아 「그날 칸이 중단이면 신호 전부 버림」 ·
  시장 유닛 끔(m = 1 사본) · 비터틀 시장 유닛 적용(m = 0 버림 · 랏 배수 ``mult``)을 한다.
- 소스 끼우기 ``gate_source`` · ``gate_function`` — sector_rs 의 「섞기 뒤 한 줄」 + 평균회귀 랏 식의 ``× mult`` 한 자리.
"""
from __future__ import annotations

import copy
import dataclasses
import inspect
import math
import re
import textwrap
from collections import Counter

import numpy as np
import pandas as pd

from replay import sector_rs_core as R

ALLOW = frozenset({"10", "01"})        # 기울기 오름·폭 > 0.3 · 기울기 내림·폭 ≤ 0.3
BLOCK = frozenset({"00", "11"})
CELLS = ("10", "01", "00", "11")
CELL_NAMES = {"10": "오름·폭 넓음(허용)", "01": "내림·폭 좁음(허용)", "00": "내림·폭 넓음(중단)", "11": "오름·폭 좁음(중단)"}
STALE_DAYS = 10
TURTLE = frozenset({"kojiro", "donchian", "vcp", "bfb"})


def allowed(cell) -> bool:
    """칸 없음(None) = 허용. 중단 칸만 막는다."""
    return cell not in BLOCK


class AsOf:
    """정렬된 날짜 · 값 → 날짜 d 보다 엄격히 앞선 마지막 날의 값(없으면 default)."""

    def __init__(self, dates, values, default=None, stale_days: "int | None" = None):
        self.ns = pd.DatetimeIndex(dates).asi8
        self.values = list(values)
        self.default = default
        self.stale_ns = None if stale_days is None else int(stale_days) * 86_400_000_000_000
        if len(self.ns) > 1 and not np.all(np.diff(self.ns) > 0):
            raise ValueError("AsOf: 날짜가 오름차순·중복 없음이어야 한다")
        self._cache: dict = {}

    def __call__(self, d):
        v = pd.Timestamp(d).value
        hit = self._cache.get(v)
        if hit is not None or v in self._cache:
            return hit
        p = int(np.searchsorted(self.ns, v, side="left")) - 1
        if p < 0 or (self.stale_ns is not None and v - self.ns[p] > self.stale_ns):
            out = self.default
        else:
            out = self.values[p]
        self._cache[v] = out
        return out


def mu_asof(bar_dates, closes) -> AsOf:
    """체결일 d → m(d) = d 보다 앞선 마지막 069500 봉까지로 운영 classify 판정(판정 불가·묵음 = NaN)."""
    from replay.audit import market_unit as MU
    mk = MU.m_at_bars(np.asarray(closes, float))
    return AsOf(bar_dates, mk.tolist(), default=float("nan"), stale_days=STALE_DAYS)


def m1(m) -> float:
    """운영 fail-open — NaN·None = 1.0."""
    if m is None:
        return 1.0
    m = float(m)
    return 1.0 if not math.isfinite(m) else m


def with_m(s, m: float):
    """신호 사본의 m 만 바꾼다(dataclass · namedtuple · 일반 객체)."""
    if dataclasses.is_dataclass(s) and not isinstance(s, type):
        return dataclasses.replace(s, m=m)
    if hasattr(s, "_replace"):
        return s._replace(m=m)
    s2 = copy.copy(s)
    s2.m = m
    return s2


class RaGate(R.SectorGate):
    """그날(D) 신호 목록 관문.

    cell_of(d) = D−1 종가 칸 키 · m_of(d) = D−1 시장 유닛(NaN 가능).
    block = 중단 칸이면 그날 신호 전부 버림.
    mu = "native"(신호를 건드리지 않음) · "off"(터틀 — 모든 신호 m = 1 사본) · "apply"(비터틀 — m = 0 이면 그날 신호 버림,
    아니면 ``mult`` = m 을 사이저가 읽는다).
    check_m = 원판 신호의 m 이 m_of(d) 와 같은지 센다(터틀 native).
    """

    def __init__(self, cal_krx=None, cell_of=None, m_of=None, *, block: bool = False, mu: str = "native",
                 check_m: bool = False):
        super().__init__(cal_krx if cal_krx is not None else pd.DatetimeIndex([]), None, lambda t, d: None,
                         enabled=block)
        self.cell_of = cell_of or (lambda d: None)
        self.m_of = m_of or (lambda d: float("nan"))
        self.block = block
        self.mu = mu
        self.check_m = check_m
        self.mult = 1.0
        self.mr_names = None

    def _new_run(self):
        super()._new_run()
        r = self.runs[-1]
        r.update({"dropped_mu": [], "cell_days": Counter(), "cell_sigs": Counter(), "m_checked": 0,
                  "m_mismatch": 0, "m_mismatch_ex": [], "mult_days": Counter()})

    def scale(self, q):
        """비터틀 랏 × m(m < 1 일 때만 · 내림)."""
        if self.mult >= 1.0:
            return q
        return int(math.floor(q * self.mult))

    def filter(self, gd: int, todays: list, loc: dict) -> list:
        if self._last_gd is None or gd <= self._last_gd:
            self._new_run()
        self._last_gd = gd
        run = self.runs[-1]
        run["days"] += 1
        if "trades" in loc and isinstance(loc["trades"], list):
            run["trades_ref"] = loc["trades"]
        if run.get("cal") is None and "cal" in loc:
            run["cal"] = loc["cal"]
        d = self.date_of(gd, loc)
        cell = self.cell_of(d)
        run["cell_days"][cell] += 1
        self.mult = 1.0
        m = self.m_of(d)
        if self.mu == "apply":
            self.mult = m1(m)
            run["mult_days"][self.mult] += 1
        if not todays:
            return todays
        run["cell_sigs"][cell] += len(todays)
        run["seen"] += len(todays)
        yb = run["by_year"].setdefault(d.year, [0, 0, 0])
        yb[0] += len(todays)
        if self.check_m:
            for s in todays:
                run["m_checked"] += 1
                a, b = m1(getattr(s, "m", None)), m1(m)
                if abs(a - b) > 1e-12:
                    run["m_mismatch"] += 1
                    if len(run["m_mismatch_ex"]) < 20:
                        run["m_mismatch_ex"].append((str(d.date()), str(self.key(s)), a, b))
        if self.block and not allowed(cell):
            ds = str(d.date())
            run["dropped"].extend((ds, str(self.key(s)), cell) for s in todays)
            yb[2] += len(todays)
            return []
        if self.mu == "off":
            return [with_m(s, 1.0) for s in todays]
        if self.mu == "apply" and self.mult <= 0:
            ds = str(d.date())
            run["dropped_mu"].extend((ds, str(self.key(s)), cell) for s in todays)
            return []
        return todays


# ═════════════════════════════════ 소스 끼우기 ═════════════════════════════════

_MR_LOT = "B * pos_ratio / cd.E_raw"


def gate_source(src: str, mr: bool = False) -> "tuple[str, int]":
    """sector_rs 의 「섞기 뒤 관문 한 줄」(+ 평균회귀 체결 기록) · 평균회귀는 랏 식에 ``× _SRS_GATE.mult``.

    반환 = (새 소스, 관문 줄 수). 평균회귀 랏 자리가 정확히 1 이 아니면 −1.
    """
    new, n = R.gate_source(src, mr=mr)
    if mr:
        k = new.count(_MR_LOT)
        if k != 1:
            return new, -1
        new = new.replace(_MR_LOT, "B * pos_ratio * _SRS_GATE.mult / cd.E_raw")
    return new, n


def gate_function(module, name: str, gate, mr: bool = False):
    """``module.name`` 을 관문 사본으로 바꾼다. 반환 = 원 함수. 관문 줄이 정확히 1 이어야 한다."""
    orig = getattr(module, name)
    src = textwrap.dedent(inspect.getsource(orig))
    new, n = gate_source(src, mr=mr)
    if n != 1:
        raise RuntimeError(f"[ra_gate] {module.__name__}.{name}: 끼울 자리 {n}개(1 이어야 한다)")
    ns = module.__dict__
    ns["_SRS_GATE"] = gate
    loc: dict = {}
    exec(compile(new, f"<ra_gate {module.__name__}.{name}>", "exec"), ns, loc)
    setattr(module, name, loc[name])
    return orig


# ═════════════════════════════════ 칸 · 거래 표 ═════════════════════════════════

def cell_share(dates, cell_of, a: str, b: str) -> dict:
    """[a, b] 세션 중 칸 비율."""
    ds = [d for d in pd.DatetimeIndex(dates) if pd.Timestamp(a) <= d <= pd.Timestamp(b)]
    c = Counter(cell_of(d) for d in ds)
    n = len(ds)
    return {k: (c.get(k, 0) / n if n else float("nan")) for k in CELLS} | {"none": c.get(None, 0) / n if n else 0.0,
                                                                           "n": n}


def in_period(date_str: str, a: str, b: str) -> bool:
    return a <= date_str <= b
