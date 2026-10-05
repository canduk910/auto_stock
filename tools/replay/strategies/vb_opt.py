"""volatility_breakout 효율화 탐색 층 — 전수 점검 재현(``vb.py``) 위에 격자 축만 얹는다.

사전 고정 = ``_workspace/analysis/strategy_opt_20261005/vb/prereg.md``(sha256 동결).

축(prereg §2): ``km``(목표가 배수) · 보유(C 당일 종가 · N 다음 날 시가 · W 이기고 있으면 다음 날 시가) ·
손절% · 필터(F0~F6). 체결가 = 목표가 × ``fill_mult``(기본 1.0008 = VB 실거래 실측 중앙).
같은 날 선후 불명은 두 판(비관 = 저가 · 낙관 = 종가로 손절 판정) — ``vb.exit_px`` 와 같은 뜻.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from . import vb as VB

KM = (0.8, 1.3, 2.0)
HOLDS = ("C", "N", "W")
STOPS = (-3.0, -5.0, -8.0)
FILTERS = ("F0", "F1", "F2", "F3", "F4", "F5", "F6")
CURRENT = (1.3, "C", -5.0, "F0")
FILL_BASE = 1.0008
FILL_BFB = 1.0193
F4_K_MAX = 0.50
F5_RANGE_MIN = 0.05
F6_TOP = 10


def grid() -> "list[tuple]":
    return list(itertools.product(KM, HOLDS, STOPS, FILTERS))


@dataclass
class Cand:
    ticker: str
    i: int
    gd: int
    k: float
    rng_prev: float      # D−1 고가 − 저가(수정)
    tv_prev: float
    trend: bool
    range_pct: float     # D−1 범위 ÷ D−1 종가


def _sma(c: np.ndarray, end: int, n: int = 20) -> float:
    """c[end−n+1 .. end] 평균. 모자라면 NaN."""
    if end - n + 1 < 0:
        return float("nan")
    return float(np.mean(c[end - n + 1:end + 1]))


def trend_flag(c: np.ndarray, i: int) -> bool:
    """F3: D−1 종가 > SMA20(D−1) ∧ SMA20(D−1) > SMA20(D−6)."""
    a, b = _sma(c, i - 1), _sma(c, i - 6)
    if not (np.isfinite(a) and np.isfinite(b)):
        return False
    return bool(c[i - 1] > a and a > b)


def base_candidates(bars: dict, mcap_fn, p: dict = VB.VB_OP) -> dict:
    """{gd: [Cand]} — 운영 후보 자격(``vb.universe_mask``) + k 계산. ``km`` 은 아직 안 곱했다."""
    out: dict = {}
    for t, b in bars.items():
        if not (len(t) == 6 and t.isdigit()):
            continue
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        for i in range(2, len(c)):
            if not VB.universe_mask(b, i, p, mcap_fn(t, b, i)):
                continue
            k = VB.noise_k(o, h, l, c, i, p["k_period"])
            if not np.isfinite(k):
                continue
            rng = h[i - 1] - l[i - 1]
            if not (rng * k > 0) or not (o[i] > 0):
                continue
            rp = rng / c[i - 1] if c[i - 1] > 0 else float("nan")
            out.setdefault(int(b["di"][i]), []).append(
                Cand(t, i, int(b["di"][i]), float(k), float(rng), float(b["tv"][i - 1]), trend_flag(c, i), float(rp)))
    return out


def m_ok(mv: float, filt: str) -> bool:
    x = 1.0 if not np.isfinite(mv) else mv     # 판정 불가 = 운영 fail-open(m = 1)
    if filt == "F1":
        return x >= 1.0
    if filt == "F2":
        return x >= 0.75
    return True


def filter_day(cands: "list[Cand]", filt: str, mv: float) -> "list[Cand]":
    if filt in ("F1", "F2"):
        return cands if m_ok(mv, filt) else []
    if filt == "F3":
        return [x for x in cands if x.trend]
    if filt == "F4":
        return [x for x in cands if x.k <= F4_K_MAX]
    if filt == "F5":
        return [x for x in cands if np.isfinite(x.range_pct) and x.range_pct >= F5_RANGE_MIN]
    if filt == "F6":
        return sorted(cands, key=lambda x: (-x.tv_prev, x.ticker))[:F6_TOP]
    return cands


@dataclass
class OSig:
    ticker: str
    ti: int
    gd: int
    E: float        # 체결가(수정) = 목표가 × fill_mult
    E_raw: float
    target: float
    k: float
    m: float


def signals(base: dict, bars: dict, km: float, filt: str, m_for_day, fill_mult: float = FILL_BASE) -> "list[OSig]":
    out = []
    for gd, lst in base.items():
        mv = float(m_for_day[gd]) if m_for_day is not None else float("nan")
        for x in filter_day(lst, filt, mv):
            b = bars[x.ticker]
            tgt = b["o"][x.i] + x.rng_prev * x.k * km
            if b["h"][x.i] < tgt:
                continue
            E = tgt * fill_mult
            out.append(OSig(x.ticker, x.i, gd, float(E), float(E * b["raw"][x.i]), float(tgt), x.k, mv))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


DISASTER_PCT = -10.0


def outcome(b: dict, i: int, E: float, stop_pct: float, hold: str, version: str,
            stop_mode: str = "intraday") -> "tuple[float, str, int]":
    """(청산가(수정), 사유, 청산 봉 인덱스). D 장중 손절은 두 판, N·W 의 D+1 은 시가 청산.

    ``stop_mode="close"``(사후 판, ``prereg_posthoc.md``) = 장중엔 재난 손절 −10% 만(두 판) ·
    손절%는 D 종가로 판정해 종가 청산 — 일봉으로 완전히 정해진다."""
    H, L, Cc = b["h"][i], b["l"][i], b["c"][i]
    if version not in ("pes", "opt"):
        raise ValueError(version)
    if stop_mode == "intraday":
        line = E * (1.0 + stop_pct / 100.0)
        if (L if version == "pes" else Cc) <= line:
            return line, "STOP_LOSS", i
    elif stop_mode == "close":
        dline = E * (1.0 + DISASTER_PCT / 100.0)
        if (L if version == "pes" else Cc) <= dline:
            return dline, "DISASTER_STOP", i
        if Cc <= E * (1.0 + stop_pct / 100.0):
            return float(Cc), "CLOSE_STOP", i
    else:
        raise ValueError(stop_mode)
    overnight = hold == "N" or (hold == "W" and Cc > E)
    if hold not in ("C", "N", "W"):
        raise ValueError(hold)
    if overnight and i + 1 < len(b["c"]):
        return float(b["o"][i + 1]), "NEXT_OPEN", i + 1
    return float(Cc), "CLOSE", i


def population(sigs: "list[OSig]", bars: dict, hold: str, stop: float, version: str, start_gd: int, end_gd: int,
               cooldown: int = VB.VB_OP["cooldown_days"], stop_mode: str = "intraday") -> list:
    """[(OSig, 청산가, 사유, 청산 gd)] — 예산·슬롯 무관, 종목별 쿨다운(청산일 + N 영업일까지 금지)."""
    last_exit: dict = {}
    out = []
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd:
            continue
        le = last_exit.get(s.ticker)
        if le is not None and s.gd <= le + cooldown:
            continue
        b = bars[s.ticker]
        px, why, xi = outcome(b, s.ti, s.E, stop, hold, version, stop_mode)
        xgd = int(b["di"][xi])
        last_exit[s.ticker] = xgd
        out.append((s, px, why, xgd))
    return out


def week_block_diff(a_ret, a_dates, b_ret, b_dates, *, n_boot: int = 2000, seed: int = 20261005,
                    q: float = 0.05) -> dict:
    """두 판 평균 차(a − b)의 달력 ISO 주 블록 부트스트랩. 같은 주 표본을 두 판에 함께 쓴다."""
    def wk(d):
        y, w, _ = d.isocalendar()
        return (y, w)
    keys = sorted({wk(d) for d in a_dates} | {wk(d) for d in b_dates})
    ix = {k: j for j, k in enumerate(keys)}
    K = len(keys)
    ia = np.array([ix[wk(d)] for d in a_dates], dtype=np.int64)
    ib = np.array([ix[wk(d)] for d in b_dates], dtype=np.int64)
    sa, na = np.bincount(ia, weights=np.asarray(a_ret, float), minlength=K), np.bincount(ia, minlength=K).astype(float)
    sb, nb = np.bincount(ib, weights=np.asarray(b_ret, float), minlength=K), np.bincount(ib, minlength=K).astype(float)
    est = float(sa.sum() / na.sum() - sb.sum() / nb.sum())
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    e = lambda x: np.einsum("ij,j->i", cnt, x)  # noqa: E731  (matmul 은 이 환경에서 허위 경고를 낸다)
    stat = e(sa) / e(na) - e(sb) / e(nb)
    se = float(np.std(stat, ddof=1))
    return {"diff": est, "lo90": float(np.percentile(stat, 100 * q)), "hi90": float(np.percentile(stat, 100 * (1 - q))),
            "se": se, "n_weeks": K}


class OptPos:
    """한 랏 — 당일 또는 다음 날 시가 청산. ``audit.book.run_book`` 인터페이스."""

    def __init__(self, sig: OSig, qty: int, b: dict, hold: str, stop: float, version: str,
                 stop_mode: str = "intraday"):
        self.s, self.qty = sig, qty
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.last_px = sig.E
        self._px, self._why, self._xi = outcome(b, sig.ti, sig.E, stop, hold, version, stop_mode)
        self._xgd = int(b["di"][self._xi])
        self._close = float(b["c"][sig.ti])

    def _exit(self, px, reason, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd

    def cur_ti(self, gd):
        if gd == self.s.gd:
            return self.s.ti
        if gd == self._xgd:
            return self._xi
        return None

    def data_ended(self, gd):
        return gd > self._xgd

    def open_phase(self, ti, gd) -> bool:
        if ti == self._xi and ti != self.s.ti:
            self.last_px = self._px
            self._exit(self._px, self._why, gd)
            return True
        return False

    def intraday_phase(self, ti, gd, is_entry) -> bool:
        if ti != self.s.ti:
            return False
        if self._xi == self.s.ti:
            self.last_px = self._px
            self._exit(self._px, self._why, gd)
            return True
        self.last_px = self._close
        return False

    def value(self) -> float:
        return self.k * self.last_px


def make_book_fns(bars: dict, hold: str, stop: float, version: str, sizer, cooldown: int = VB.VB_OP["cooldown_days"],
                  stop_mode: str = "intraday"):
    """(open_pos, size_fn). 쿨다운은 계좌가 실제로 산 종목에, 청산일 기준으로 건다."""
    last_exit: dict = {}

    def size_fn(s: OSig, B: float, used: float):
        le = last_exit.get(s.ticker)
        if le is not None and s.gd <= le + cooldown:
            return 0, "cooldown"
        P = int(round(s.E_raw))
        if P <= 0:
            return 0, "design"
        q = sizer(P, int(B), int(used))
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    def open_pos(s: OSig, q: int):
        ps = OptPos(s, q, bars[s.ticker], hold, stop, version, stop_mode)
        last_exit[s.ticker] = ps._xgd
        return ps

    return open_pos, size_fn
