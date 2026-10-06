"""kojiro(고지로 대순환 스윙) — 대리 진입 재구축 + 포지션 경로 (공용 층 위에 얹은 전략 층).

규칙 정본 = 운영 ``src/engine/strategies/kojiro.py`` · 지표 = ``src/engine/kojiro_indicators.py``.
cycle375·377 재현 스크립트는 스크래치와 함께 사라져(동결본 §3.1 ②) 여기서 새로 짠다.

운영 prepare(08시 전, D−1 확정 봉까지)를 봉 i(= D−1)마다 벡터로 다시 낸다.

- 창: 운영은 종목의 **최근 100봉**(``KOJIRO_FETCH_DAYS``)을 ``enrich`` 한다. EMA·Wilder ATR 는 pandas
  ``ewm(adjust=False)`` 라 **창 첫 봉에서 다시 시작**한다 — 전 구간 EMA 와 다르다. 그래서 창 길이 L 의
  FIR(첫 항 가중 (1−a)^(L−1))로 같은 값을 낸다(``ewm_window``). 창 안 위치 j(마지막에서 d 봉 앞)의 값은
  길이 L−d 의 FIR 이다. 봉 수가 100 미만(80 이상)이면 창이 0 번 봉에서 시작하므로 전 구간 ewm 과 같다.
- 스테이지 = 운영 ``stage_of`` 표(동가면 직전 스테이지 유지 — 창 안 앞 봉으로 거슬러 간다).
- 후보(봉 i): 봉 수 ≥ 80 ∧ ATR/종가 ∈ [1%, 6%] ∧ 스테이지(i)=1 ∧ EMA 5/20/40 우상향(i vs i−1, 같은 창)
  ∧ 최근 5봉 안 6→1 인접 전환(창 안 마지막 6개 스테이지) ∧ int(종가) > EMA5.
- 유니버스(봉 i): 시총 ≥ 500억 ∧ 거래대금 ≥ 10억(``stock_master`` 스냅샷 = 직전 거래일 값) ∧
  원본 전일 종가 ∈ [3,000, 500,000](운영 ``price_filter`` HARD) ∧ 6자리 숫자 코드.
- 진입(D = i+1, 다음 거래일): 시가 갭 (O−int(C_i))/int(C_i) ≥ +5% 또는 ≤ −4% 면 스킵. 체결 = D 시가(§1.4).
  「현재가 < 시가 스킵」(장중 붕괴)은 일봉으로 재현 불가 — 빼고 K1 차이 표에 적는다.

청산(운영 ``check_exit_signal`` 우선순위 그대로, 가격은 수정가 기준):
1. 고정 % 받침 E × (1 − 8%)
2. 2ATR 바닥 E − 2 × ATR_live — tighten-only(``_stop_floor``). ATR_live(봉 t) = 봉 t−1 창의 ATR(매일 아침
   ``recompute_held_atr``). 진입일 ATR_live = 진입 ATR(봉 i).
2.5 본전 승격: 고점 ≥ E + 1.5 × ATR_live 면 바닥 ≥ E(바닥에 저장 — 끈적)
3. 스테이지3: 봉 t−1 창 스테이지 = 3 이면 봉 t 시가에 ``TREND_EXIT``(위 선이 시가에 이미 깨졌으면 그 선 사유)
4. 2.5ATR 샹들리에: 고점 − 2.5 × ATR_live(끈적 아님 — ATR 이 커지면 내려간다)
고점(``high_since_buy``)은 봉 안에서 즉시 오른다(운영 틱 경로 — ``ratchet="intrabar"``).
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

from replay.audit import bars as BR

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import kojiro_indicators as KI  # noqa: E402  (운영 지표 — 정의를 여기서 읽는다)
from src.engine.strategies import kojiro as KS  # noqa: E402

WINDOW = KS.KOJIRO_FETCH_DAYS          # 100
MIN_BARS = KS.KOJIRO_MIN_REQUIRED      # 80
PRICE_FILTER = (3_000, 500_000)        # system_config price_filter_min/max · mode HARD [실측 추출본]
STAGE_LOOK = 6                         # _stage_recently(within=5) 가 보는 스테이지 수


def op_params(strategy_config_row: dict) -> dict:
    """운영 DB ``strategy_config.params`` + 코드 기본값 병합(운영 ``__init__`` 과 같다)."""
    p = strategy_config_row["params"]
    p = json.loads(p) if isinstance(p, str) else dict(p)
    return {**KS.KojiroStrategy.DEFAULT_PARAMS, **p}


# ── 지표 (창 FIR) ─────────────────────────────────────────────────────────

def _fir(x: np.ndarray, alpha: float, L: int, first: "np.ndarray | None" = None) -> np.ndarray:
    """out[i] = ewm(adjust=False) of x[i−L+1..i] 의 마지막 값(첫 항은 ``first`` 로 바꿀 수 있다). i < L−1 = NaN."""
    n = len(x)
    out = np.full(n, np.nan)
    if n < L:
        return out
    q = 1.0 - alpha
    w = alpha * q ** np.arange(L - 2, -1, -1)          # 가중: 창 안 j=1..L−1
    body = np.convolve(np.nan_to_num(x, nan=0.0), w[::-1], mode="valid")  # 길이 n−(L−1)+1, x[j..j+L−2]
    head = x if first is None else first
    # 창 i: 첫 항 = head[i−L+1] · 나머지 = x[i−L+2..i]
    out[L - 1:] = q ** (L - 1) * head[: n - L + 1] + body[1:]
    return out


def _ewm_full(x: np.ndarray, alpha: float, first: "np.ndarray | None" = None) -> np.ndarray:
    out = np.empty(len(x))
    q = 1.0 - alpha
    acc = np.nan
    for j in range(len(x)):
        acc = (first[j] if first is not None else x[j]) if j == 0 else q * acc + alpha * x[j]
        out[j] = acc
    return out


def window_values(x: np.ndarray, alpha: float, d_max: int, first: "np.ndarray | None" = None) -> np.ndarray:
    """V[d, i] = 봉 i 로 끝나는 운영 창(길이 min(100, i+1))에서 위치 i−d 의 ewm 값.

    i ≥ 99: 창 시작 s = i−99 → 위치 i−d 의 값 = 길이 100−d 의 FIR 를 i−d 에서 읽음.
    i < 99: 창 시작 0 → 전 구간 ewm(i−d).
    """
    n = len(x)
    V = np.full((d_max + 1, n), np.nan)
    full = _ewm_full(x, alpha, first)
    for d in range(d_max + 1):
        L = WINDOW - d
        f = _fir(x, alpha, L, first)
        v = np.full(n, np.nan)
        if n > d:
            v[d:] = f[: n - d]                 # 봉 i 의 값 = f[i−d]
            short = np.arange(n) < WINDOW - 1
            idx = np.nonzero(short & (np.arange(n) >= d))[0]
            v[idx] = full[idx - d]
        V[d] = v
    return V


_STAGE_TABLE = KI._STAGE_MAP


def _stage_vec(s: np.ndarray, m: np.ndarray, l: np.ndarray) -> np.ndarray:
    """운영 ``stage_of`` 의 벡터판. 동가·NaN = 0(직전 유지는 호출자가 채운다)."""
    out = np.zeros(len(s), dtype=np.int8)
    ok = np.isfinite(s) & np.isfinite(m) & np.isfinite(l) & (s != m) & (m != l) & (s != l)
    out[ok & (s > m) & (m > l)] = 1
    out[ok & (m > s) & (s > l)] = 2
    out[ok & (m > l) & (l > s)] = 3
    out[ok & (l > m) & (m > s)] = 4
    out[ok & (l > s) & (s > m)] = 5
    out[ok & (s > l) & (l > m)] = 6
    return out


def features(b: dict, p: dict) -> dict:
    """봉 i(= D−1 확정 봉) 마다 운영 prepare 판정 재료."""
    h, l, c = b["h"].astype(float), b["l"].astype(float), b["c"].astype(float)
    n = len(c)
    a_s, a_m, a_l = (2.0 / (p["ema_short"] + 1), 2.0 / (p["ema_mid"] + 1), 2.0 / (p["ema_long"] + 1))
    D = STAGE_LOOK - 1
    Es, Em, El = (window_values(c, a, D) for a in (a_s, a_m, a_l))
    # Wilder ATR — 창 첫 봉 TR = 고가 − 저가(전일 종가 없음), 나머지는 창 안 전일 종가
    prev = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev), np.abs(l - prev)]), axis=0)
    hl = h - l
    a_atr = 1.0 / p["atr_period"]
    full_atr = _ewm_full(tr, a_atr, first=hl)
    atr = _fir(tr, a_atr, WINDOW, first=hl)
    short = np.arange(n) < WINDOW - 1
    atr[short] = full_atr[short]
    # 스테이지 — 창 안 위치 i−d (d=0..5). 동가면 앞 위치 값(운영: 직전 스테이지 유지)
    st = np.zeros((D + 1, n), dtype=np.int8)
    for d in range(D + 1):
        st[d] = _stage_vec(Es[d], Em[d], El[d])
    ties = 0
    for d in range(D - 1, -1, -1):
        z = (st[d] == 0) & np.isfinite(Es[d])
        ties += int(z.sum())
        st[d][z] = st[d + 1][z]
    within = int(p["stage1_freshness"])
    fresh = np.zeros(n, dtype=bool)
    # _stage_recently: 마지막 within+1 개 스테이지에서 인접 (6 → 1)
    for d in range(within, 0, -1):
        fresh |= (st[d] == 6) & (st[d - 1] == 1)
    up = (Es[0] > Es[1]) & (Em[0] > Em[1]) & (El[0] > El[1])
    prev_close = np.floor(c)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = atr / np.where(prev_close > 0, prev_close, np.nan)
    nbars = np.arange(1, n + 1)
    tech = ((nbars >= MIN_BARS) & (prev_close > 0) & np.isfinite(ratio)
            & (ratio >= p["atr_ratio_min"]) & (ratio <= p["atr_ratio_max"])
            & (st[0] == 1) & up & fresh & (prev_close > Es[0]))
    # 후보 점수 3성분(운영 _rank_candidate_components) — 창 안 위치값으로
    m3 = Em - El
    bw = np.abs(Em - El)
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = np.where(c > 0, (m3[0] - m3[3]) / 3.0 / c, 0.0)
        cnt = np.isfinite(bw[1:6]).sum(axis=0)
        bprev = np.where(cnt > 0, np.nansum(bw[1:6], axis=0) / np.maximum(cnt, 1), np.nan)
        band = np.where(bprev > 0, bw[0] / bprev - 1.0, 0.0)
    slope = np.where(np.isfinite(slope), slope, 0.0)
    band = np.where(np.isfinite(band), band, 0.0)
    dist = np.full(n, -1)
    for d in range(within, 0, -1):            # 가장 가까운 전환(작은 d)이 마지막에 덮는다
        dist = np.where((st[d] == 6) & (st[d - 1] == 1), d - 1, dist)
    fresh_sc = np.where(dist >= 0, within - dist, 0.0).astype(float)
    return {"atr": atr, "stage": st[0], "tech": tech, "ema_s": Es[0], "ratio": ratio,
            "prev_close": prev_close, "ties": ties, "nbars": nbars,
            "rank": np.vstack([slope, band, fresh_sc])}


def universe(b: dict, p: dict, mktcap: "np.ndarray | None" = None) -> np.ndarray:
    """봉 i 스냅샷 기준 유니버스(시총 · 거래대금 · 가격 필터). ``mktcap`` 로 시총 열을 바꿀 수 있다(보고판 ①)."""
    mc = b["mktcap"] if mktcap is None else mktcap
    craw = b["c_raw"].astype(float)
    with np.errstate(invalid="ignore"):
        return (np.nan_to_num(mc) >= p["min_market_cap"]) & (np.nan_to_num(b["tv"]) >= p["min_trade_amount"]) \
            & (craw >= PRICE_FILTER[0]) & (craw <= PRICE_FILTER[1]) & ~b["notrade"]


# ── 신호 ─────────────────────────────────────────────────────────────────

@dataclass
class Sig:
    ticker: str
    ti: int          # 진입 봉(D) 인덱스
    gd: int          # 진입일 전역 달력
    E: float
    E_raw: float
    N: float         # 진입 ATR(수정가 척도, 봉 i)
    m: float
    sector: str = ""
    gap: float = 0.0
    score: float = 0.0
    extra: dict = field(default_factory=dict)


def candidates(bars: dict, feats: dict, univ: dict) -> "list[tuple[str, int]]":
    """(종목, 봉 i) — 운영 prepare 후보(유니버스 ∧ tech). 진입일 갭 판정 전."""
    out = []
    for t, f in feats.items():
        ok = f["tech"] & univ[t]
        for i in np.nonzero(ok)[0]:
            out.append((t, int(i)))
    return out


def build_signals(bars: dict, feats: dict, univ: dict, m_for_day: np.ndarray, p: dict,
                  sectors: "dict | None" = None, *, gap_filter: bool = True) -> "tuple[list[Sig], dict]":
    """후보 → 진입 신호(갭 필터 · 다음 거래일 시가). 반환 = (신호, 집계)."""
    out, cnt = [], {"cand": 0, "no_next_day": 0, "notrade_D": 0, "gap_up": 0, "gap_down": 0}
    gu, gdn = float(p["gap_up_skip_pct"]), float(p["gap_down_skip_pct"])
    cands = candidates(bars, feats, univ)
    # 운영 prepare 의 후보 점수 — 같은 날(봉 i 의 전역 달력) 후보 풀 min-max(운영 _score_candidates 그대로)
    by_day: dict = {}
    for t, i in cands:
        by_day.setdefault(int(bars[t]["di"][i]), {})[t] = tuple(float(x) for x in feats[t]["rank"][:, i])
    scores = {}
    for g, raw in by_day.items():
        for t, sc in KS.KojiroStrategy._score_candidates(None, raw, p).items():
            scores[(t, g)] = sc
    for t, i in cands:
        b, f = bars[t], feats[t]
        cnt["cand"] += 1
        D = i + 1
        if D >= len(b["c"]) or b["di"][D] != b["di"][i] + 1:
            cnt["no_next_day"] += 1
            continue
        if b["notrade"][D] or b["o"][D] <= 0:
            cnt["notrade_D"] += 1
            continue
        pc = f["prev_close"][i]
        O = float(b["o"][D])
        gap = (O - pc) / pc * 100.0
        if gap_filter and gap >= gu:
            cnt["gap_up"] += 1
            continue
        if gap_filter and gap <= gdn:
            cnt["gap_down"] += 1
            continue
        mv = m_for_day[b["di"][D]]
        mv = 1.0 if (mv is None or not np.isfinite(mv)) else float(mv)
        out.append(Sig(t, int(D), int(b["di"][D]), O, float(O * b["raw"][D]), float(f["atr"][i]), mv,
                       sector=(sectors or {}).get(t, f"미분류-{t}"), gap=gap,
                       score=scores.get((t, int(b["di"][i])), 0.0), extra={"i": i}))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out, cnt


# ── 포지션 경로 ───────────────────────────────────────────────────────────

class KJPos:
    """한 랏. 가격 = 수정 기준, 원화 = k × 수정가. 봉 걷기 = ``audit.bars.walk_bar``."""

    def __init__(self, sig: Sig, b: dict, f: dict, qty: int, p: dict, *, mode: str = "color",
                 locks: bool = True):
        self.s, self.b, self.f, self.qty, self.p, self.mode, self.locks = sig, b, f, qty, p, mode, locks
        self.E = sig.E
        self.hsb = sig.E
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.exit_phase = None
        self.last_px = sig.E
        self.pct_line = sig.E * (1.0 + float(p["hard_stop_pct"]) / 100.0)
        self.atr_live = sig.N
        self.floor = sig.E - float(p["stop_atr"]) * sig.N
        self.be = float(p.get("breakeven_promote_atr", 0) or 0)
        self.be_hit = False
        self.locked_days = 0

    # 운영 check_exit_signal 의 선들
    def _promote(self):
        a = self.atr_live
        if self.be > 0 and a > 0 and self.hsb >= self.E + self.be * a:
            if self.floor < self.E:
                self.floor = self.E
            self.be_hit = True

    def _set_live_atr(self, ti: int):
        a = self.f["atr"][ti - 1] if ti - 1 >= 0 else np.nan
        if np.isfinite(a) and a > 0:
            self.atr_live = float(a)
        self.floor = max(self.floor, self.E - float(self.p["stop_atr"]) * self.atr_live)
        self._promote()

    def stop_line(self) -> float:
        return max(self.pct_line, self.floor)

    def trail_line(self) -> float:
        return self.hsb - float(self.p["trail_atr"]) * self.atr_live if self.atr_live > 0 else -math.inf

    def _lines(self):
        return [BR.Line(self.stop_line(), "STOP_LOSS"), BR.Line(self.trail_line(), "TRAILING_STOP")]

    def _on_up(self, px: float):
        if px > self.hsb:
            self.hsb = px
        self._promote()

    def risk_raw(self) -> float:
        """운영 ``_open_risk_won`` 한 종목분(원) — 실효 손절선 = max(받침, 바닥, 샹들리에, 본전)."""
        stop = max(self.stop_line(), self.trail_line())
        if 0 < stop < self.E:
            return self.k * (self.E - stop)
        return 0.0

    def _exit(self, px, reason, gd, phase=None):
        self.exit_px, self.exit_reason, self.exit_gd, self.exit_phase = px, reason, gd, phase

    def cur_ti(self, gd):
        di = self.b["di"]
        k = int(np.searchsorted(di, gd))
        return k if (k < len(di) and di[k] == gd) else None

    def data_ended(self, gd):
        return self.b["di"][-1] < gd

    def _locked(self, ti: int) -> bool:
        if not self.locks or ti <= 0:
            return False
        b = self.b
        return BR.locked_limit_down(b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti - 1])

    def open_phase(self, ti: int, gd: int) -> bool:
        if self.b["notrade"][ti]:
            return False
        self._set_live_atr(ti)
        O = self.b["o"][ti]
        stop = self.stop_line()
        stage3 = int(self.f["stage"][ti - 1]) == 3 if ti >= 1 else False
        reason = None
        if O <= stop:
            reason = "STOP_LOSS"
        elif stage3:
            reason = "TREND_EXIT"
        elif O <= self.trail_line():
            reason = "TRAILING_STOP"
        if reason is not None:
            if self._locked(ti):
                self.locked_days += 1
                return False
            self._exit(O, reason, gd, "open")
            return True
        self._on_up(O)
        return False

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        b = self.b
        if b["notrade"][ti]:
            self.last_px = b["c"][ti]
            return False
        if self._locked(ti) and not is_entry:
            self.last_px = b["c"][ti]
            return False
        O, H, L, Cc = b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti]
        ex = BR.walk_bar(O, H, L, Cc, lines_fn=self._lines, on_up=self._on_up, mode=self.mode,
                         ratchet="intrabar", gap_check=False)
        if ex is not None:
            self._exit(ex.px, ex.reason, gd, "intra")
            return True
        self.last_px = Cc
        return False

    def value(self) -> float:
        return self.k * self.last_px


def run_path(sig: Sig, b: dict, f: dict, p: dict, end_gd: int, mode: str = "color") -> KJPos:
    """자금 제약 없는 한 거래(1주 연속) — P1 모집단용."""
    ps = KJPos(sig, b, f, 1, p, mode=mode)
    if ps.intraday_phase(sig.ti, sig.gd, True):
        return ps
    for t in range(sig.ti + 1, len(b["c"])):
        gd = int(b["di"][t])
        if gd > end_gd:
            break
        if ps.open_phase(t, gd) or ps.intraday_phase(t, gd, False):
            return ps
    ps._exit(ps.last_px, "END", None)
    return ps


def population(sigs: "list[Sig]", bars: dict, feats: dict, p: dict, start_gd: int, end_gd: int,
               mode: str = "color") -> "list[KJPos]":
    """P1 신호 모집단 — 종목마다 앞 거래 청산 뒤에만 다음 진입 · m ≤ 0 은 진입 없음 · 예산 무관."""
    out, busy = [], {}
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd or s.m <= 0:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_path(s, bars[s.ticker], feats[s.ticker], p, end_gd, mode)
        busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out


def net_ret(ps: KJPos, cost_rt: float) -> float:
    return ps.exit_px / ps.E - 1.0 - cost_rt


# ── 계좌 게이트(운영 check_buy_signal 의 포트폴리오 게이트) ─────────────────

class Gates:
    """``book.run_book`` 의 ``size_fn`` 안에서 운영 매수 게이트를 돈다.

    보유 목록은 ``open_pos`` 로 연 랏 중 아직 청산되지 않은 것(``exit_reason is None``)이다 — book 이 그날
    시가 단계 청산을 매수보다 먼저 처리하므로 매수 시점의 보유와 같다.
    순서(운영): 일 손실 한도 → Σ 오픈리스크 캡 → 섹터 캡 → (시간·갭은 신호 단계) → 시장 유닛 거름 → 수량.
    """

    def __init__(self, p: dict, sizer, *, sector_cap: bool = True, risk_cap: bool = True,
                 daily_loss: bool = True):
        self.p, self.sizer = p, sizer
        self.sector_cap, self.risk_cap, self.daily_loss = sector_cap, risk_cap, daily_loss
        self.opened: list[KJPos] = []
        from collections import Counter
        self.hits = Counter()

    def held(self):
        return [x for x in self.opened if x.exit_reason is None]

    def size(self, s: Sig, B: float, used: float) -> "tuple[int, str]":
        held = self.held()
        if self.daily_loss:
            pnl = sum(x.k * x.exit_px - x.cost_basis for x in self.opened
                      if x.exit_gd == s.gd and x.exit_phase == "open")
            if B > 0 and pnl / B * 100.0 <= float(self.p["daily_loss_limit"]):
                self.hits["daily_loss"] += 1
                return 0, "dailyloss"
        if self.risk_cap:
            cap = float(self.p.get("max_open_risk_pct", 0) or 0)
            if cap > 0 and int(B) > 0 and sum(x.risk_raw() for x in held) >= int(B) * cap / 100.0:
                self.hits["open_risk_cap"] += 1
                return 0, "riskcap"
        if self.sector_cap:
            cap = int(self.p.get("max_positions_per_sector", 0) or 0)
            if cap > 0 and s.sector and not s.sector.startswith("미분류"):
                same = sum(1 for x in held if x.s.sector == s.sector)
                if same >= cap:
                    self.hits["sector_cap"] += 1
                    return 0, "sector"
        P = int(round(s.E_raw))
        N_raw = s.N * (s.E_raw / s.E)
        if s.m <= 0:
            return 0, "mu"
        if self.sizer.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m):
            return 0, "mu"
        q = self.sizer.qty(P, N_raw, budget=int(B), used=int(used), m=s.m)
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")


def sectors_from_master(master_cols: list, master_rows: list) -> dict:
    """운영 ``_kojiro_sector_key`` 를 현재 ``stock_master.master_raw`` 에 소급 적용(동결본 §3.1 ② 근사)."""
    out = {}
    ci, cr = master_cols.index("ticker"), master_cols.index("master_raw")
    for r in master_rows:
        raw = r[cr]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = None
        out[r[ci]] = KS._kojiro_sector_key(raw if isinstance(raw, dict) else None, r[ci])
    return out
