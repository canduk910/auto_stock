"""volatility_breakout(S5) — 일봉 근사 재현 층 (공용 층 위에 얹은 전략 층).

규칙 정본 = ``src/engine/strategies/volatility_breakout.py`` + 운영 DB ``strategy_config``(2026-10-05 추출).
동결본 §3.5 · §1.4 · K1 차이 표 = ``_workspace/analysis/strategy_audit_20261005/vb/result.md``.

후보(그날 D 아침 ``prepare``, :209·:427):
  전일 거래대금 ≥ ``min_trade_amount``(500억) ∧ 전일 시총 ≥ ``min_market_cap``(500억)
  ∧ 전일 종가 3,000 ~ 500,000(``system_config.price_filter_*``, :2012) ∧ 6자리 숫자 코드 · ETF 제외
목표가(:330-346 · :888-890):
  k = 직전 봉(D−1)을 뺀 그 앞 ``k_period + 1`` 봉(D−2 … D−(k_period+2))의 noise 평균
      (noise = 1 − |종가 − 시가| ÷ (고가 − 저가), 범위 0 인 봉은 뺀다)
  target = D 시가(KRX REST) + (D−1 고가 − D−1 저가) × k × ``k_value_krx_main``(1.3)
진입: D 고가 ≥ target → 체결가 = target(§1.4 장중 돌파 = max(시가, 돌파선), 시가 < target 이 항상 성립)
청산(당일): 손절 매수가 × (1 + ``stop_loss_main``/100) — 두 판(§3.5 ②)
  · 비관판 = D 저가 ≤ 손절선이면 손절선 가격
  · 낙관판 = D 종가 ≤ 손절선일 때만 손절선 가격(돌파 뒤 종가까지 내려왔으면 손절은 확실히 났다).
    저가만 손절선 아래인 날은 「저가가 돌파 전에 왔다」 고 보고 손절 없음
  · 아니면 15:20 일괄 청산 = D 종가(§1.4 근사)
재진입 쿨다운: 청산일 D 뒤 ``reentry_cooldown_days`` 영업일까지 금지(:1310 · base :1950 —
  ``cooldown_until = D + N 영업일`` · ``cd_until >= today`` 면 막는다) → D+N+1 영업일부터
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# 운영값(DB ``strategy_config`` 2026-10-05 추출 · 코드 기본과 다른 키는 K1 표)
VB_OP = dict(k_period=15, k_mult=1.3, stop_pct=-5.0, min_mcap=50_000_000_000, min_tv=50_000_000_000,
             max_scan=100, price_min=3_000, price_max=500_000, cooldown_days=2, max_pos=2, pr=0.35)
VERSIONS = ("pes", "opt")


def noise_k(o, h, l, c, i: int, k_period: int) -> float:
    """봉 i(=D) 아침의 k. 직전 봉 i−1 은 빼고 i−2 … i−(k_period+2) 의 noise 평균. 없으면 NaN.

    운영은 ``get_recent_daily_normalized(days=k_period+2)`` 로 최신순 17봉을 받아 ``candles[1:]`` 의 noise 를
    평균한다(장 전이라 ``candles[0]`` = D−1). 범위 0 인 봉은 평균에서 빠진다.
    """
    lo = max(0, i - k_period - 2)
    vals = []
    for j in range(i - 2, lo - 1, -1):
        rng = h[j] - l[j]
        if rng > 0:
            vals.append(1.0 - abs(c[j] - o[j]) / rng)
    return float(np.mean(vals)) if vals else float("nan")


def target_offset(h_prev: float, l_prev: float, k: float, k_mult: float) -> float:
    """목표가 − 시가. 운영 = ``int(int(range × k) × k_mult)`` 원 — 여기서는 수정가 단위라 정수 절삭을 하지 않는다."""
    return (h_prev - l_prev) * k * k_mult


def exit_px(E: float, h: float, l: float, c: float, stop_pct: float, version: str) -> "tuple[float, str]":
    """당일 청산 (가격, 사유). ``version`` = "pes"(비관) | "opt"(낙관)."""
    line = E * (1.0 + stop_pct / 100.0)
    if version == "pes":
        hit = l <= line
    elif version == "opt":
        hit = c <= line
    else:
        raise ValueError(version)
    if hit:
        return line, "STOP_LOSS"
    return c, "FORCE_CLEAR_1520"


@dataclass
class Sig:
    ticker: str
    ti: int          # 종목 봉 인덱스(D)
    gd: int          # 전역 달력 인덱스(D)
    E: float         # 진입가(수정) = target
    E_raw: float     # 진입가(원)
    O: float
    H: float
    L: float
    Cc: float
    k: float
    off: float
    m: float = 1.0   # 시장 유닛(VB 는 쓰지 않는다 — 보고 칸 나누기용)


def universe_mask(b: dict, i: int, p: dict, mcap_prev: float) -> bool:
    """봉 i(=D) 아침의 후보 자격. 전일 봉 = 달력상 바로 앞 거래일이어야 한다(거래정지 다음 날은 전일 거래대금 0)."""
    if i < 2 or b["di"][i - 1] != b["di"][i] - 1:
        return False
    if b["notrade"][i - 1] or b["notrade"][i]:
        return False
    if not (b["tv"][i - 1] >= p["min_tv"]):
        return False
    if not (np.isfinite(mcap_prev) and mcap_prev >= p["min_mcap"]):
        return False
    pc = b["c_raw"][i - 1]
    return bool(p["price_min"] <= pc <= p["price_max"])


def day_candidates(bars: dict, mcap_fn, p: dict = VB_OP, gd_range: "tuple[int, int] | None" = None) -> dict:
    """{gd: [(ticker, i, k, off)]} — 그날 아침 후보(목표가까지 계산된 것). ``mcap_fn(ticker, b, i)`` = 전일 시총(원)."""
    out: dict = {}
    for t, b in bars.items():
        if not (len(t) == 6 and t.isdigit()):
            continue
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        for i in range(2, len(c)):
            gd = int(b["di"][i])
            if gd_range is not None and not (gd_range[0] <= gd <= gd_range[1]):
                continue
            if not universe_mask(b, i, p, mcap_fn(t, b, i)):
                continue
            k = noise_k(o, h, l, c, i, p["k_period"])
            if not np.isfinite(k):
                continue
            off = target_offset(h[i - 1], l[i - 1], k, p["k_mult"])
            if not (off > 0) or not (o[i] > 0):
                continue
            out.setdefault(gd, []).append((t, i, k, off))
    return out


def signals_from_candidates(cands: dict, bars: dict, m_for_day=None) -> "list[Sig]":
    """후보 중 그날 고가가 목표가에 닿은 것 = 돌파 신호."""
    out = []
    for gd, lst in cands.items():
        for t, i, k, off in lst:
            b = bars[t]
            O = b["o"][i]
            E = O + off
            if b["h"][i] < E:
                continue
            mv = 1.0
            if m_for_day is not None:
                x = m_for_day[gd]
                mv = float(x) if np.isfinite(x) else float("nan")
            out.append(Sig(t, i, gd, float(E), float(E * b["raw"][i]), float(O), float(b["h"][i]),
                           float(b["l"][i]), float(b["c"][i]), float(k), float(off), mv))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


def population(sigs: "list[Sig]", version: str, start_gd: int, end_gd: int, p: dict = VB_OP) -> list:
    """P1 신호 모집단 — 예산·슬롯 무관. 종목마다 쿨다운(청산일 + N 영업일까지 금지)만 지킨다.
    반환 = [(Sig, 청산가, 사유)]."""
    last_exit: dict = {}
    out = []
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd:
            continue
        le = last_exit.get(s.ticker)
        if le is not None and s.gd <= le + p["cooldown_days"]:
            continue
        px, why = exit_px(s.E, s.H, s.L, s.Cc, p["stop_pct"], version)
        last_exit[s.ticker] = s.gd
        out.append((s, px, why))
    return out


class VBPos:
    """한 랏(당일 청산). ``audit.book.run_book`` 인터페이스."""

    def __init__(self, sig: Sig, qty: int, version: str, p: dict = VB_OP):
        self.s, self.qty, self.version, self.p = sig, qty, version, p
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.last_px = sig.E

    def _exit(self, px, reason, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd

    def cur_ti(self, gd):
        return self.s.ti if gd == self.s.gd else None

    def data_ended(self, gd):
        return gd > self.s.gd

    def open_phase(self, ti, gd) -> bool:
        return False

    def intraday_phase(self, ti, gd, is_entry) -> bool:
        px, why = exit_px(self.s.E, self.s.H, self.s.L, self.s.Cc, self.p["stop_pct"], self.version)
        self.last_px = px
        self._exit(px, why, gd)
        return True

    def value(self) -> float:
        return self.k * self.last_px


def make_book_fns(version: str, sizer, p: dict = VB_OP):
    """씨앗 하나 분량의 (open_pos, size_fn). 쿨다운은 계좌가 실제로 산 종목에만 걸린다."""
    last_exit: dict = {}

    def size_fn(s: Sig, B: float, used: float):
        le = last_exit.get(s.ticker)
        if le is not None and s.gd <= le + p["cooldown_days"]:
            return 0, "cooldown"
        P = int(round(s.E_raw))
        if P <= 0:
            return 0, "design"
        q = sizer(P, int(B), int(used))
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    def open_pos(s: Sig, q: int):
        last_exit[s.ticker] = s.gd
        return VBPos(s, q, version, p)

    return open_pos, size_fn


def net_ret(entry: float, exit_: float, cost_rt: float) -> float:
    return exit_ / entry - 1.0 - cost_rt


def random_control(cands: dict, sigs: "list[Sig]", bars: dict, version: str, start_gd: int, end_gd: int,
                   seed: int, p: dict = VB_OP) -> list:
    """보고판 ③ 무작위 진입 대조군 — 그날 신호 수만큼 그날 후보에서 무작위로 골라 **시가에** 산다.
    청산 규칙(손절 −5% 두 판 · 종가)은 같다. 반환 = [(ticker, gd, 순수익 전 비율)]."""
    rng = np.random.default_rng(seed)
    n_by = {}
    for s in sigs:
        if start_gd <= s.gd <= end_gd:
            n_by[s.gd] = n_by.get(s.gd, 0) + 1
    out = []
    for gd, n in sorted(n_by.items()):
        lst = cands.get(gd, [])
        if not lst:
            continue
        pick = rng.choice(len(lst), size=min(n, len(lst)), replace=False)
        for j in pick:
            t, i, _k, _off = lst[j]
            b = bars[t]
            O = b["o"][i]
            px, _why = exit_px(O, b["h"][i], b["l"][i], b["c"][i], p["stop_pct"], version)
            out.append((t, gd, px / O - 1.0))
    return out


def provisional_flags(daily_cols: list, daily_rows: list, cutoff: str = "2026-09-28") -> set:
    """D-6 — DB 잠정 종가 의심 (ticker, 'YYYY-MM-DD'). close_t vs close_{t+1} ÷ (1 + chg_{t+1}/100) 차 > 1틱."""
    from replay.data import krx_tick
    ix = {c: i for i, c in enumerate(daily_cols)}
    by: dict = {}
    for r in daily_rows:
        by.setdefault(r[ix["ticker"]], []).append(r)
    out = set()
    for t, rs in by.items():
        rs.sort(key=lambda r: r[ix["bas_dd"]])
        for a, b2 in zip(rs[:-1], rs[1:]):
            d = a[ix["bas_dd"]][:10]
            if d >= cutoff:
                break
            ca, cb, chg = a[ix["close_price"]], b2[ix["close_price"]], b2[ix["change_rate"]]
            if not ca or not cb or chg is None:
                continue
            implied = cb / (1.0 + float(chg) / 100.0)
            if abs(ca - implied) > max(krx_tick(ca), abs(implied) * 5e-7 + cb * 5e-7 + 1e-9):
                out.add((t, d))
    return out


def lot_qty_operating(op_sizer, m: float = 1.0):
    """``OpSizer`` → ``sizer(P, B, used)``. VB 는 시장 유닛을 쓰지 않으므로 m 은 의미 없다(1.0)."""
    def sizer(P: int, B: int, used: int) -> int:
        return op_sizer.qty(P, 0.0, budget=B, used=used, m=m)
    return sizer


def spec_qty(P: int, B: int, used: int, pr: float = 0.35, krho: float = 1.0) -> int:
    """운영 식의 손 복제(테스트 대조용) — floor(B×pr ÷ P), 잔여 클램프, 0 이면 1주 폴백(잔여 ≥ P ∧ P ≤ ρ×pr×B)."""
    amount = int(B * pr)
    q = amount // P
    rem = max(0, B - used)
    if q <= 0:
        if rem >= P and P <= int(krho * int(B * pr)):
            return 1
        return 0
    q = min(q, rem // P)
    return max(q, 0)


def isfinite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)
