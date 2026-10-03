"""cycle405 — donchian 개조(깡토식 청산·사이징) 대 현행 재현. 사전 등록 = prereg.md.

실행:
  python3 c405_sim.py signals     # 신호 개수만(결과 비교 없음) — prereg 전에 돌려도 되는 점검
  python3 c405_sim.py run         # prereg sha 확인 뒤 본 판정 + 보고판
입력 = 스크래치 c405_panel.pkl (c405_data.py). 운영 DB·KIS·KRX 호출 0.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SCR = Path("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
           "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/c405")

COST_SIDE = 0.00175          # 한쪽 0.175% (왕복 0.35%)
START_EQUITY = 743_000       # 10-02 donchian total_asset 743,364 (실측) 근사
SEEDS = list(range(16))
BOOT_SEED = 405_2026
BOOT_N = 2000
W4 = ("2021-10-01", "2025-10-02")
W5 = ("2021-10-01", "2026-09-30")
WH = ("2025-10-10", "2026-09-30")

# ── 현행 운영 파라미터(운영 DB strategy_config 2026-10-03 07:02 KST 실측) ──
CUR = dict(donchian_period=20, long_ma=60, vol_period=20, vol_mult=1.5, atr_period=14,
           gap_skip=3.0, ext_pct=4.0, min_trade=200e8,
           stop_atr=2.0, be_atr=1.5, backstop=-9.0, stop_loss_rate=-6.0,
           bf_days=2, channel=10, trail_mult=1.8,
           risk_pct=0.01, pr=0.2, max_pos=5, K=2.0, Krho=2.5, min_vol=1.0)
# ── 개조안(prereg §2) ──
KK = dict(r_floor=0.08, r_atr=1.5, be_r=3.0, chan_after_r=3.0, channel=10,
          time_bars=20, time_min_r=1.0, max_hold=250,
          risk_pct=0.012, pr=0.15, max_pos=6, daily_cap=3, K=2.0, Krho=2.5)


# ───────────────────────────── 신호 ─────────────────────────────

def ema_fir_weights(n: int) -> np.ndarray:
    """운영 `_ema`: values[0] 에서 시작해 k=2/(n+1) 로 n 개를 누적. 오래된→최신 가중."""
    k = 2.0 / (n + 1)
    w = np.empty(n)
    w[0] = (1 - k) ** (n - 1)
    for j in range(1, n):
        w[j] = k * (1 - k) ** (n - 1 - j)
    return w  # w[0]=가장 오래된


def ticker_features(p: dict) -> dict:
    o, h, l, c, tv = p["o"], p["h"], p["l"], p["c"], p["tv"]
    n = len(c)
    feat = {}
    # ATR14 (SMA of TR, idx i uses c[i-1])
    tr = np.full(n, np.nan)
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    atr = pd.Series(tr).rolling(14).mean().values
    feat["atr"] = atr
    # 직전 20봉 최고가 (j 기준 j-20..j-1)
    ph = pd.Series(h).shift(1).rolling(20).max().values
    feat["prior_high"] = ph
    # EMA60 FIR (j 기준 c[j-59..j]) 와 하루 전
    w = ema_fir_weights(60)
    ema = np.full(n, np.nan)
    if n >= 60:
        conv = np.convolve(c, w[::-1], mode="valid")  # conv[k] = Σ w[i]*c[k+i]
        ema[59:] = conv
    feat["ema"] = ema
    ema_y = np.full(n, np.nan)
    ema_y[1:] = ema[:-1]
    avg_tv = pd.Series(tv).shift(1).rolling(20).mean().values
    feat["cond"] = (
        (np.arange(n) >= 62)
        & (c > ph) & (ph > 0)
        & (ema > ema_y) & (c > ema)
        & (avg_tv > 0) & (tv >= 1.5 * avg_tv)
        & (atr > 0)
        & p["mem"] & (tv >= CUR["min_trade"])
        & ~p["notrade"]
    )
    feat["cond"] = np.nan_to_num(feat["cond"]).astype(bool)
    # 10봉 채널(당일 제외): t 기준 min(l[t-10..t-1])
    feat["chan10"] = pd.Series(l).shift(1).rolling(10).min().values
    return feat


@dataclass
class Sig:
    ticker: str
    ti: int        # 종목 배열 index (진입봉)
    gd: int        # 전역 달력 index (진입일)
    E: float       # 진입가(수정, 시가)
    E_raw: float   # 진입가(원가)
    N: float       # 진입 ATR(수정, D-1)
    bh: float      # 돌파선(수정)
    m: float       # 시장 유닛 배수(그날)


def build_signals(panel: dict, m_for_day: np.ndarray, feats: dict) -> list[Sig]:
    sigs: list[Sig] = []
    for t, p in panel.items():
        f = feats[t]
        cond = f["cond"]
        idx = np.nonzero(cond[:-1])[0]
        for j in idx:
            D = j + 1
            if p["di"][D] != p["di"][j] + 1:
                continue  # 다음 영업일 봉이 없다(거래 정지 등)
            if p["notrade"][D] or p["o"][D] <= 0:
                continue
            prev_c = p["c"][j]
            O = p["o"][D]
            if O >= prev_c * (1 + CUR["gap_skip"] / 100):
                continue
            bh = f["prior_high"][j]
            if O > bh * (1 + CUR["ext_pct"] / 100):
                continue
            mval = m_for_day[p["di"][D]]
            mval = 1.0 if (mval is None or not np.isfinite(mval)) else float(mval)
            sigs.append(Sig(t, int(D), int(p["di"][D]), float(O), float(O * p["raw"][D]),
                            float(f["atr"][j]), float(bh), mval))
    sigs.sort(key=lambda s: (s.gd, s.ticker))
    return sigs


# ───────────────────────────── 포지션 경로 ─────────────────────────────

class Pos:
    """한 랏. rule ∈ {'cur','kk'}. 가격은 수정 기준, 금액은 qty × 원가로 환산."""

    def __init__(self, sig: Sig, rule: str, stamped: bool, p: dict, f: dict, qty: int,
                 kk: dict, time_mode: str = "close20", chan_mode: str = "intraday"):
        self.s = sig
        self.rule = rule
        self.stamped = stamped
        self.p = p
        self.f = f
        self.qty = qty
        self.kk = kk
        self.E = sig.E
        self.hsb = sig.E
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0  # 원화 = k × 수정가
        self.cost_basis = qty * sig.E_raw
        self.exit_px = None
        self.exit_reason = None
        self.exit_gd = None
        self.last_px = sig.E
        self.time_mode = time_mode
        self.chan_mode = chan_mode
        self.pending_open_exit = None
        if rule == "kk":
            self.Rw = max(kk["r_floor"] * sig.E, kk["r_atr"] * sig.N)
            self.stop = sig.E - self.Rw
            self.armed = False
        else:
            self.N = sig.N

    # 현행 규칙 — 그 시점 활성 선(가격이 이 선 이하로 가면 청산)과 사유
    def _cur_lines(self, ti: int, days_held: int):
        lines = []
        if self.stamped:
            base = self.E - CUR["stop_atr"] * self.N
            if self.hsb >= self.E + CUR["be_atr"] * self.N:
                base = max(base, self.E)
            lines.append((max(base, self.E * (1 + CUR["backstop"] / 100)), "STOP_LOSS"))
        else:
            lines.append((self.E * (1 + CUR["stop_loss_rate"] / 100), "STOP_LOSS"))
        if days_held >= CUR["bf_days"] and self.s.bh > 0:
            lines.append((self.s.bh, "TIME_EXIT"))
        if days_held >= 1:
            ch = self.f["chan10"][ti]
            if np.isfinite(ch) and ch > 0:
                lines.append((ch, "TRAILING_STOP"))
        # 샹들리에 ATR: 그날 후보면 D-1 ATR, 아니면 진입 N(미스탬프는 0)
        if ti >= 1 and self.f["cond"][ti - 1]:
            A = self.f["atr"][ti - 1]
        else:
            A = self.N if self.stamped else 0.0
        if A and A > 0:
            lines.append((self.hsb - CUR["trail_mult"] * A, "TRAILING_STOP"))
        best = max(lines, key=lambda x: x[0])
        return best

    def _kk_lines(self, ti: int):
        lines = [(self.stop, "STOP_LOSS")]
        if self.armed and self.chan_mode == "intraday":
            ch = self.f["chan10"][ti]
            if np.isfinite(ch) and ch > 0:
                lines.append((ch, "TRAILING_STOP"))
        return max(lines, key=lambda x: x[0])

    def _on_up(self, px: float):
        if px > self.hsb:
            self.hsb = px
        if self.rule == "kk" and not self.armed and self.hsb >= self.E + self.kk["be_r"] * self.Rw:
            self.armed = True
            self.stop = max(self.stop, self.E)

    def _line(self, ti, days_held):
        return self._cur_lines(ti, days_held) if self.rule == "cur" else self._kk_lines(ti)

    def _exit(self, px, reason, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd

    def open_phase(self, ti: int, gd: int) -> bool:
        """진입 다음 봉부터: 시가 갭 판정. 청산되면 True."""
        p = self.p
        if p["notrade"][ti]:
            return False
        days_held = gd - self.s.gd
        if self.pending_open_exit is not None:
            self._exit(p["o"][ti], self.pending_open_exit, gd)
            return True
        O = p["o"][ti]
        line, why = self._line(ti, days_held)
        if O <= line:
            self._exit(O, why, gd)
            return True
        self._on_up(O)
        return False

    def intraday_phase(self, ti: int, gd: int, is_entry_bar: bool) -> bool:
        p = self.p
        if p["notrade"][ti]:
            self.last_px = p["c"][ti]
            return False
        days_held = gd - self.s.gd
        O, H, L, C = p["o"][ti], p["h"][ti], p["l"][ti], p["c"][ti]
        path = [L, H, C] if C >= O else [H, L, C]
        prev = O
        for px in path:
            if px > prev:
                self._on_up(px)
            elif px < prev:
                line, why = self._line(ti, days_held)
                if px <= line:
                    self._exit(min(prev, line), why, gd)
                    return True
            prev = px
        self.last_px = C
        if self.rule == "kk":
            n_bar = days_held + 1
            if self.chan_mode == "close" and self.armed:
                ch = self.f["chan10"][ti]
                if np.isfinite(ch) and C < ch:
                    self.pending_open_exit = "TRAILING_STOP"
            if n_bar >= self.kk["time_bars"] and self.hsb < self.E + self.kk["time_min_r"] * self.Rw:
                if self.time_mode == "close20":
                    self._exit(C, "TIME_EXIT", gd)
                    return True
                else:
                    self.pending_open_exit = "TIME_EXIT"
            if n_bar >= self.kk["max_hold"]:
                self._exit(C, "TIME_EXIT", gd)
                return True
        return False

    def value(self) -> float:
        return self.k * self.last_px


def run_trade_path(sig: Sig, rule: str, stamped: bool, p, f, kk, end_gd, **kw) -> Pos:
    pos = Pos(sig, rule, stamped, p, f, 1, kk, **kw)
    ti = sig.ti
    if pos.intraday_phase(ti, sig.gd, True):
        return pos
    n = len(p["c"])
    for t in range(ti + 1, n):
        gd = int(p["di"][t])
        if gd > end_gd:
            break
        if pos.open_phase(t, gd):
            return pos
        if pos.intraday_phase(t, gd, False):
            return pos
    pos._exit(pos.last_px, "END", None)  # 자료 끝(상장폐지 포함) — 마지막 종가
    return pos


# ───────────────────────────── 사이징 ─────────────────────────────

def size_cur(B: float, used: float, P: float, N_raw: float, m: float):
    """현행: 터틀 risk 0.01 → PR 낙하 → 1주 폴백, K·ρ 캡, 시장 유닛 enforce. (qty, stamped)"""
    rem = max(0.0, B - used)
    rem_q = int(rem // P)

    def guarded(budget):
        budget = int(budget)
        if N_raw <= 0 or P <= 0 or budget <= 0:
            return 0
        if N_raw / P < CUR["min_vol"] / 100:
            return 0
        q = math.floor(budget * CUR["risk_pct"] / N_raw)
        if q <= 0:
            return 0
        q = min(q, int(max(0, rem) // P))
        q = min(q, int(budget * CUR["pr"]) // P)
        return max(q, 0)

    def caps(q, via_fallback):
        capK = math.floor(int(B) * CUR["risk_pct"] / N_raw * CUR["K"]) if N_raw > 0 else q
        q = min(q, capK)
        cutoff = int(CUR["Krho"] * int(int(B) * CUR["pr"]))
        q = min(q, cutoff // P)
        return max(q, 0)

    if m < 1.0:
        if m <= 0:
            return 0, False
        d_after = guarded(B * m)
        if min(d_after, rem_q) <= 0:
            return 0, False
        q = min(d_after, rem_q)
        return caps(q, False), True
    q = guarded(B)
    if q > 0:
        q = min(q, rem_q)
        return caps(q, False), True
    q2 = int(int(B) * CUR["pr"]) // P
    if q2 > 0:
        q2 = min(q2, rem_q)
        return caps(q2, False), False
    q3 = 1 if rem >= P else 0
    return caps(q3, True), False


def size_kk(B: float, used: float, P: float, N_raw: float, m: float, kk: dict,
            allow_fallback: bool = False):
    rem = max(0.0, B - used)
    rem_q = int(rem // P)
    if m <= 0:
        return 0, True
    Bm = int(B * m)
    Rw = max(kk["r_floor"] * P, kk["r_atr"] * N_raw)
    q = math.floor(Bm * kk["risk_pct"] / Rw)
    q = min(q, rem_q, int(Bm * kk["pr"]) // P)
    if q <= 0 and allow_fallback and m >= 1.0 and rem >= P:
        q = 1
    if q <= 0:
        return 0, True
    capK = math.floor(int(B) * kk["risk_pct"] / N_raw * kk["K"]) if N_raw > 0 else q
    q = min(q, capK)
    cutoff = int(kk["Krho"] * int(int(B) * kk["pr"]))
    q = min(q, cutoff // P)
    return max(q, 0), True


# ───────────────────────────── 포트폴리오 ─────────────────────────────

def run_book(rule: str, sigs_by_gd: dict, panel, feats, cal, start, end, seed,
             kk=None, mu_on=True, max_pos=None, daily_cap=None, allow_fallback=False,
             time_mode="close20", chan_mode="intraday", cost_side=COST_SIDE):
    kk = kk or KK
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(START_EQUITY)
    pos: dict[str, Pos] = {}
    eq_prev = float(START_EQUITY)
    equity = []
    trades = []
    if max_pos is None:
        max_pos = CUR["max_pos"] if rule == "cur" else kk["max_pos"]
    if daily_cap is None:
        daily_cap = None if rule == "cur" else kk["daily_cap"]
    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold_today = set()
        # 1) 보유 시가 갭
        for t in list(pos):
            ps = pos[t]
            p = panel[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                sold_today.add(t)
                del pos[t]
        # 2) 매수 (그날 신호, 무작위 순서)
        todays = list(sigs_by_gd.get(gd, []))
        rng.shuffle(todays)
        n_new = 0
        for s in todays:
            if s.ticker in pos or s.ticker in sold_today:
                continue
            if len(pos) >= max_pos:
                break
            if daily_cap is not None and n_new >= daily_cap:
                break
            m = s.m if mu_on else 1.0
            used = sum(x.cost_basis for x in pos.values())
            P = s.E_raw
            N_raw = s.N * (s.E_raw / s.E)
            if rule == "cur":
                q, stamped = size_cur(B, used, P, N_raw, m)
            else:
                q, stamped = size_kk(B, used, P, N_raw, m, kk, allow_fallback)
            if q <= 0:
                continue
            p = panel[s.ticker]
            ps = Pos(s, rule, stamped, p, feats[s.ticker], q, kk, time_mode=time_mode, chan_mode=chan_mode)
            ps.attach_index()
            cash -= q * P * (1 + cost_side)
            pos[s.ticker] = ps
            n_new += 1
        # 3) 장중 경로 + 15:20 시간청산
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                # 그날 봉 없음: 자료가 끝났으면 마지막 종가로 정리
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    cash += ps.k * ps.exit_px * (1 - cost_side)
                    trades.append(ps)
                    del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    return np.array(equity), trades, cal[g0:g1 + 1]


def _attach(self):
    di = self.p["di"]
    self._di = di
    self._map = None


def _cur_ti(self, gd):
    di = self.p["di"]
    k = int(np.searchsorted(di, gd))
    if k < len(di) and di[k] == gd:
        return k
    return None


def _data_ended(self, gd):
    return self.p["di"][-1] < gd


Pos.attach_index = _attach
Pos.cur_ti = _cur_ti
Pos.data_ended = _data_ended


# ───────────────────────────── 통계 ─────────────────────────────

def cagr(eq: np.ndarray) -> float:
    if len(eq) < 2:
        return float("nan")
    yrs = len(eq) / 252.0
    return (eq[-1] / START_EQUITY) ** (1 / yrs) - 1


def mdd(eq: np.ndarray) -> float:
    e = np.concatenate([[START_EQUITY], eq])
    peak = np.maximum.accumulate(e)
    return float((e / peak - 1).min())


def daily_ret(eq: np.ndarray) -> np.ndarray:
    e = np.concatenate([[START_EQUITY], eq])
    return e[1:] / e[:-1] - 1


def stationary_boot(d: np.ndarray, L: int, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    T = len(d)
    p = 1.0 / L
    out = np.empty(n)
    for b in range(n):
        idx = np.empty(T, dtype=np.int64)
        i = rng.integers(T)
        for k in range(T):
            if k > 0:
                if rng.random() < p:
                    i = rng.integers(T)
                else:
                    i = (i + 1) % T
            idx[k] = i
        out[b] = d[idx].mean()
    return out


def boot_fast(d: np.ndarray, L: int, n: int, seed: int) -> np.ndarray:
    """정상 블록 부트스트랩(벡터화) — 블록 길이 기하분포(평균 L), 원형 이어붙이기."""
    rng = np.random.default_rng(seed)
    T = len(d)
    dd = np.concatenate([d, d])
    out = np.empty(n)
    for b in range(n):
        tot = 0.0
        cnt = 0
        while cnt < T:
            s = rng.integers(T)
            ln = int(rng.geometric(1.0 / L))
            ln = min(ln, T - cnt)
            tot += dd[s:s + ln].sum()
            cnt += ln
        out[b] = tot / T
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load():
    with open(SCR / "c405_panel.pkl", "rb") as fh:
        d = pickle.load(fh)
    feats = {t: ticker_features(p) for t, p in d["panel"].items()}
    sigs = build_signals(d["panel"], d["m_for_day"], feats)
    return d, feats, sigs


def group(sigs):
    g = {}
    for s in sigs:
        g.setdefault(s.gd, []).append(s)
    return g


def trade_unit(sigs, panel, feats, rule, end_gd, start_gd=0, **kw):
    """종목마다 앞 거래가 끝난 뒤에만 다음 진입(한 주 연속 수량)."""
    out = []
    busy_until = {}
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd:
            continue
        if s.m <= 0:
            continue
        if busy_until.get(s.ticker, -1) >= s.gd:
            continue
        p = panel[s.ticker]
        ps = run_trade_path(s, rule, True, p, feats[s.ticker], KK, end_gd, **kw)
        busy_until[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10**9
        out.append(ps)
    return out


def kk_R(ps: Pos, cost_rt=2 * COST_SIDE) -> float:
    return (ps.exit_px / ps.E - 1 - cost_rt) / (ps.Rw / ps.E)



def recon(eq, trades, cost_side=COST_SIDE):
    tot = 0.0
    for ps in trades:
        buy = ps.qty * ps.s.E_raw * (1 + cost_side)
        if ps.exit_reason == "OPEN":
            tot += ps.k * ps.last_px - buy
        else:
            tot += ps.k * ps.exit_px * (1 - cost_side) - buy
    return float(eq[-1] - (START_EQUITY + tot))


def book_stats(rule, sbg, panel, feats, cal, win, **kw):
    eqs, rets, res = [], [], []
    for sd in SEEDS:
        eq, tr, dates = run_book(rule, sbg, panel, feats, cal, win[0], win[1], sd, **kw)
        eqs.append(eq)
        rets.append(daily_ret(eq))
        res.append({"seed": sd, "cagr": cagr(eq), "mdd": mdd(eq), "n_trades": len(tr),
                    "recon": recon(eq, tr, kw.get("cost_side", COST_SIDE)),
                    "max_pos_seen": None,
                    "lots": [ps.qty for ps in tr],
                    "reasons": pd.Series([ps.exit_reason for ps in tr]).value_counts().to_dict(),
                    "final": float(eq[-1])})
    R = np.mean(np.vstack(rets), axis=0)
    out = {
        "cagr_median": float(np.median([r["cagr"] for r in res])),
        "cagr_min": float(np.min([r["cagr"] for r in res])),
        "cagr_max": float(np.max([r["cagr"] for r in res])),
        "mdd_median": float(np.median([r["mdd"] for r in res])),
        "trades_median": float(np.median([r["n_trades"] for r in res])),
        "recon_max_abs": float(np.max([abs(r["recon"]) for r in res])),
        "one_share_lot_share": float(np.mean([q == 1 for r in res for q in r["lots"]])) if res else None,
        "lot_median": float(np.median([q for r in res for q in r["lots"]])) if res else None,
        "reasons_seed0": res[0]["reasons"],
        "per_seed": [{k: v for k, v in r.items() if k != "lots"} for r in res],
    }
    return out, R, dates


def diff_stats(Ra, Rb, seed=BOOT_SEED):
    d = Ra - Rb
    o = {"ann_pp": float(d.mean() * 252 * 100)}
    for L in (20, 60, 120):
        bs = boot_fast(d, L, BOOT_N, seed + L) * 252 * 100
        o[f"b{L}"] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    return o


def tstats(trs, rule):
    if not trs:
        return {}
    w = np.array([ps.s.m for ps in trs])
    if rule == "kk":
        R = np.array([kk_R(ps) for ps in trs])
    else:
        R = np.array([(ps.exit_px / ps.E - 1 - 2 * COST_SIDE) / (2 * ps.s.N / ps.E) for ps in trs])
    ret = np.array([ps.exit_px / ps.E - 1 - 2 * COST_SIDE for ps in trs])
    hold = np.array([((ps.exit_gd if ps.exit_gd is not None else ps.s.gd) - ps.s.gd + 1) for ps in trs])
    k = max(1, int(math.ceil(len(R) * 0.01)))
    order = np.argsort(R)
    keep = order[:-k]
    o = {
        "n": int(len(trs)),
        "R_mweighted": float((w * R).sum() / w.sum()),
        "R_mean": float(R.mean()),
        "R_ex_top1pct_mweighted": float((w[keep] * R[keep]).sum() / w[keep].sum()),
        "ret_mean_pct": float(ret.mean() * 100),
        "win_rate": float((ret > 0).mean()),
        "payoff": float(ret[ret > 0].mean() / -ret[ret <= 0].mean()) if (ret > 0).any() and (ret <= 0).any() else None,
        "hold_mean": float(hold.mean()), "hold_median": float(np.median(hold)),
        "reasons": pd.Series([ps.exit_reason for ps in trs]).value_counts(normalize=True).round(4).to_dict(),
    }
    if rule == "kk":
        o["reach3R"] = float(np.mean([ps.armed for ps in trs]))
        o["reach1R"] = float(np.mean([ps.hsb >= ps.E + ps.Rw for ps in trs]))
        o["R_atr_side_share"] = float(np.mean([1.5 * ps.s.N > 0.08 * ps.E for ps in trs]))
        o["R_pct_p50_p90_p99"] = [float(np.percentile([ps.Rw / ps.E for ps in trs], q)) for q in (50, 90, 99)]
    return o


def lot_geometry(sigs, B=743_000):
    rows = []
    for s in sigs:
        if s.m <= 0:
            continue
        P = s.E_raw
        N_raw = s.N * (s.E_raw / s.E)
        qc, st = size_cur(B, 0, P, N_raw, 1.0)
        qk, _ = size_kk(B, 0, P, N_raw, 1.0, KK)
        rows.append((qc, st, qk))
    a = np.array([(r[0], r[2]) for r in rows])
    def dist(x):
        return {"0": float(np.mean(x == 0)), "1": float(np.mean(x == 1)), "2": float(np.mean(x == 2)), "3+": float(np.mean(x >= 3))}
    return {"n": len(rows), "cur": dist(a[:, 0]), "kk": dist(a[:, 1]),
            "cur_unstamped_share": float(np.mean([not r[1] and r[0] > 0 for r in rows]))}


def main_run():
    want = (HERE / "prereg.sha256").read_text().split()[0]
    got = sha256(HERE / "prereg.md")
    if want != got:
        raise SystemExit(f"prereg sha 불일치 {want} != {got}")
    d, feats, sigs = load()
    cal, panel = d["cal"], d["panel"]
    sbg = group(sigs)
    out = {"prereg_sha": got, "script_sha": sha256(Path(__file__)), "n_signals": len(sigs)}
    # 본 판정 W4
    cur, Rc, _ = book_stats("cur", sbg, panel, feats, cal, W4)
    kk, Rk, _ = book_stats("kk", sbg, panel, feats, cal, W4)
    out["W4"] = {"cur": cur, "kk": kk, "diff": diff_stats(Rk, Rc)}
    g1 = int(cal.searchsorted(pd.Timestamp(W4[1]), side="right")) - 1
    g0 = int(cal.searchsorted(pd.Timestamp(W4[0])))
    tu_kk = trade_unit(sigs, panel, feats, "kk", g1, start_gd=g0)
    tu_cur = []
    busy = {}
    for s in sigs:
        if s.gd < g0 or s.gd > g1 or s.m <= 0 or busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_trade_path(s, "cur", True, panel[s.ticker], feats[s.ticker], KK, g1)
        busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10**9
        tu_cur.append(ps)
    out["W4"]["tu_kk"] = tstats(tu_kk, "kk")
    out["W4"]["tu_cur_stamped"] = tstats(tu_cur, "cur")
    # 관문
    gate = {
        "recon_ok": max(cur["recon_max_abs"], kk["recon_max_abs"]) < 1.0,
    }
    out["gate"] = gate
    J1 = out["W4"]["diff"]["b20"][0] > 0
    J2 = kk["mdd_median"] >= cur["mdd_median"]
    J3 = out["W4"]["tu_kk"]["R_mweighted"] > 0
    out["judge"] = {"J1": bool(J1), "J2": bool(J2), "J3": bool(J3),
                    "pass": bool(J1 and J2 and J3 and gate["recon_ok"])}
    print(json.dumps({"judge": out["judge"], "gate": gate, "diff": out["W4"]["diff"],
                      "cur": {k: cur[k] for k in ("cagr_median", "mdd_median")},
                      "kk": {k: kk[k] for k in ("cagr_median", "mdd_median")},
                      "J3": out["W4"]["tu_kk"]["R_mweighted"]}, ensure_ascii=False), flush=True)
    # 보고판
    rep = {}
    for name, win in (("W5", W5), ("H", WH)):
        c2, R2c, _ = book_stats("cur", sbg, panel, feats, cal, win)
        k2, R2k, _ = book_stats("kk", sbg, panel, feats, cal, win)
        rep[name] = {"cur": c2, "kk": k2, "diff": diff_stats(R2k, R2c)}
    # A·B 기간(W4 일별 차를 날짜로 자름)
    dates = cal[g0:g1 + 1]
    dW = Rk - Rc
    mA = dates <= pd.Timestamp("2022-12-31")
    rep["A_ann_pp"] = float(dW[mA].mean() * 252 * 100)
    rep["B_ann_pp"] = float(dW[~mA].mean() * 252 * 100)
    variants = {
        "V1_fallback": dict(rule="kk", allow_fallback=True),
        "V2_5x02": dict(rule="kk", kk={**KK, "pr": 0.2, "max_pos": 5}),
        "V3_time_open21": dict(rule="kk", time_mode="open21"),
        "V4_no_daily_cap": dict(rule="kk", daily_cap=10**9),
        "V5_mu_off_kk": dict(rule="kk", mu_on=False),
        "V5_mu_off_cur": dict(rule="cur", mu_on=False),
        "V6_chan_close": dict(rule="kk", chan_mode="close"),
        "V7_cost06_kk": dict(rule="kk", cost_side=0.003),
        "V7_cost06_cur": dict(rule="cur", cost_side=0.003),
    }
    Rvs = {}
    for name, kw in variants.items():
        rule = kw.pop("rule")
        st, Rv, _ = book_stats(rule, sbg, panel, feats, cal, W4, **kw)
        Rvs[name] = Rv
        base = Rc if rule == "kk" else Rk
        rep[name] = {"book": {k: st[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median",
                                                  "trades_median", "one_share_lot_share", "lot_median", "recon_max_abs")},
                     "vs_cur_or_kk": diff_stats(Rv, base) if rule == "kk" else diff_stats(Rk, Rv)}
        print(name, json.dumps(rep[name]["book"], ensure_ascii=False), flush=True)
    rep["V5_diff_kk_minus_cur_both_off"] = diff_stats(Rvs["V5_mu_off_kk"], Rvs["V5_mu_off_cur"])
    rep["V7_diff_kk_minus_cur_cost06"] = diff_stats(Rvs["V7_cost06_kk"], Rvs["V7_cost06_cur"])
    rep["lots_W4_H_m1"] = lot_geometry([s for s in sigs if s.gd >= g0])
    out["report"] = rep
    with open(HERE / "results.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    with open(HERE / "runs.log", "a") as fh:
        fh.write(json.dumps({"ts": pd.Timestamp.now(tz="Asia/Seoul").isoformat(), "script_sha": out["script_sha"],
                             "prereg_sha": got, "judge": out["judge"],
                             "core": {"diff_ann": out["W4"]["diff"]["ann_pp"], "b20": out["W4"]["diff"]["b20"],
                                      "mdd_cur": cur["mdd_median"], "mdd_kk": kk["mdd_median"],
                                      "J3": out["W4"]["tu_kk"]["R_mweighted"]}}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "signals"
    d, feats, sigs = load()
    cal = d["cal"]
    if mode == "run":
        main_run()
        sys.exit(0)
    if mode == "signals":
        g0 = int(cal.searchsorted(pd.Timestamp(W4[0])))
        g1 = int(cal.searchsorted(pd.Timestamp(W4[1]), side="right")) - 1
        w4 = [s for s in sigs if g0 <= s.gd <= g1]
        h0 = int(cal.searchsorted(pd.Timestamp(WH[0])))
        wh = [s for s in sigs if s.gd >= h0]
        print(json.dumps({
            "signals_all": len(sigs), "W4": len(w4), "H": len(wh),
            "W4_m0_share": float(np.mean([s.m == 0 for s in w4])),
            "W4_per_year": len(w4) / 4.0,
            "median_price_raw_W4": float(np.median([s.E_raw for s in w4])),
        }, ensure_ascii=False, indent=1))
