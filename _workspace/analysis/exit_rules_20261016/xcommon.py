"""청산 규칙 점검 공용 (prereg §2·§4·§6).

- 모집단 덤프(M1~M5 입력): 거래마다 진입·청산·봉 조각
- 청산 덮개(급락 D-C · 정체 D-N): 포지션 클래스의 open_phase 를 감싼다(클래스 단위 패치, 실행 중 설정 dict 하나)
- 청산 순간 가장 높던 선 기록(M6 갭 분해) · 계좌 거래 요약(기대값 · 휩쏘)
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SPAN_AFTER = 45          # 청산 뒤로 더 담는 봉 수(H ≤ 40 + 여유)
SPAN_MIN = 160           # 진입 뒤 최소 봉 수(첫 닿음·되돌림 사건 뒤 H 봉)


# ── 지수 상태 (달력 인덱스마다, 그날 종가까지 알려진 값) ───────────────────────────
def index_state(cal, ser_csv):
    ser = pd.read_csv(ser_csv, index_col=0, parse_dates=True)
    out = {}
    for mk in ("kospi", "kosdaq"):
        s = ser[mk].dropna()
        c = s.to_numpy(float)
        sma60 = pd.Series(c).rolling(60, min_periods=60).mean().to_numpy()
        pos = np.log(c) - np.log(sma60)
        slp = np.full(len(c), np.nan)
        slp[20:] = np.log(sma60[20:] / sma60[:-20])
        mx20 = pd.Series(c).rolling(20, min_periods=20).max().to_numpy()
        dd20 = c / mx20 - 1.0
        r5 = np.full(len(c), np.nan)
        r5[5:] = c[5:] / c[:-5] - 1.0
        r = np.diff(np.log(c), prepend=np.nan)
        sg = pd.Series(r).rolling(20, min_periods=20).std(ddof=1).to_numpy()
        vp = np.full(len(c), np.nan)
        for k in range(len(c)):
            if np.isfinite(sg[k]):
                h = sg[max(0, k - 1000):k]
                h = h[np.isfinite(h)]
                if len(h) >= 250:
                    vp[k] = np.mean(h < sg[k])
        st = np.where(~(np.isfinite(pos) & np.isfinite(slp)), -1,
                      np.where(pos >= 0, np.where(slp >= 0, 0, 1), np.where(slp >= 0, 2, 3)))
        p = s.index.searchsorted(cal, side="right") - 1
        ok = (p >= 0)
        stale = np.array([(cal[i] - s.index[j]).days > 10 if j >= 0 else True for i, j in enumerate(p)])
        def take(a, fill=np.nan):
            v = np.where(ok, a[np.clip(p, 0, None)], fill).astype(float)
            v[stale] = fill
            return v
        out[mk] = {"state": take(st.astype(float), -1).astype(int), "dd20": take(dd20), "r5": take(r5),
                   "volp": take(vp), "pos60": take(pos)}
    return out


# ── 모집단 덤프 ────────────────────────────────────────────────────────────────
def pop_record(ps, b, kq, win):
    s = ps.s
    di = b["di"]
    ti = int(s.ti)
    if ps.exit_gd is None:
        xti = len(di) - 1
    else:
        k = int(np.searchsorted(di, ps.exit_gd))
        xti = k if (k < len(di) and di[k] == ps.exit_gd) else len(di) - 1
    t1 = min(len(di), max(xti, ti + SPAN_MIN) + SPAN_AFTER)
    sl = slice(ti, t1)
    return {"t": s.ticker, "ti": ti, "gd": int(s.gd), "E": float(ps.E), "N": float(s.N), "kq": bool(kq), "win": win,
            "xti": xti - ti, "xpx": float(ps.exit_px), "why": str(ps.exit_reason),
            "o": np.asarray(b["o"][sl], np.float32), "h": np.asarray(b["h"][sl], np.float32),
            "l": np.asarray(b["l"][sl], np.float32), "c": np.asarray(b["c"][sl], np.float32),
            "di": np.asarray(di[sl], np.int32)}


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh, protocol=4)


# ── 청산 덮개 ─────────────────────────────────────────────────────────────────
CFG = {"crash": None, "stall": None}   # crash = {"on": {mk: bool[cal]}, "start": {mk: int[cal]}} · stall = n*


def crash_flags(cal, ist, theta, shift=0):
    """D-C 국면: 전일 종가 DD20 ≤ θ 로 켜짐, DD20 > θ/2 로 꺼짐. 반환 = 날 gd 의 켜짐·국면 시작 gd(전일 판정)."""
    out = {}
    for mk in ("kospi", "kosdaq"):
        dd = ist[mk]["dd20"]
        on = np.zeros(len(cal), bool)
        st = np.full(len(cal), -1, int)
        cur, s0 = False, -1
        for i in range(len(cal)):
            x = dd[i]
            if np.isfinite(x):
                if not cur and x <= theta:
                    cur, s0 = True, i + 1
                elif cur and x > theta / 2.0:
                    cur = False
            if i + 1 < len(cal):
                on[i + 1] = cur
                st[i + 1] = s0 if cur else -1
        if shift:
            on = np.roll(on, shift % len(on))
            # 이동 계열의 국면 시작 = 이동된 켜짐 구간의 첫날
            st = np.full(len(cal), -1, int)
            s0 = -1
            for i in range(len(cal)):
                if on[i] and (i == 0 or not on[i - 1]):
                    s0 = i
                st[i] = s0 if on[i] else -1
        out[mk] = {"on": on, "start": st}
    return out


def _kq_of(s):
    kq = getattr(s, "kq", None)
    if kq is None and hasattr(s, "extra"):
        kq = s.extra.get("kq")
    return bool(kq)


def _is_locked(ps, ti):
    if hasattr(ps, "_locked"):
        try:
            return bool(ps._locked(ti))
        except TypeError:
            pass
    b = getattr(ps, "b", None) or getattr(ps, "d")
    if ti <= 0:
        return False
    pc = b["c"][ti - 1]
    return bool(pc > 0 and b["h"][ti] == b["l"][ti] and b["o"][ti] < pc * 0.88)


def patch_overlay(cls, bars_key="b"):
    if getattr(cls, "_xr_patched", False):
        return
    orig = cls.open_phase

    def open_phase(self, ti, gd):
        b = getattr(self, bars_key)
        if not b["notrade"][ti] if "notrade" in b else True:
            why = None
            cr = CFG["crash"]
            if cr is not None:
                mk = "kosdaq" if _kq_of(self.s) else "kospi"
                if cr[mk]["on"][gd] and int(self.s.gd) < cr[mk]["start"][gd]:
                    why = "CRASH_EXIT"
            n = CFG["stall"]
            if why is None and n is not None and ti >= 1 and (ti - int(self.s.ti)) >= n and b["c"][ti - 1] <= self.E:
                why = "STALL_EXIT"
            if why is not None:
                if _is_locked(self, ti):
                    return False
                O = b["o"][ti]
                self._xline = None
                ex = self._exit
                try:
                    ex(O, why, gd)
                except TypeError:
                    ex(O, why, gd, "open")
                return True
        return orig(self, ti, gd)
    cls.open_phase = open_phase
    cls._xr_patched = True


def patch_exit_line(cls, line_fn):
    """_exit 직전 가장 높던 청산선을 self._xline 에 남긴다(M6)."""
    if getattr(cls, "_xr_line", False):
        return
    orig = cls._exit

    def _exit(self, px, reason, gd, *a, **k):
        if not hasattr(self, "_xline") or reason not in ("CRASH_EXIT", "STALL_EXIT"):
            try:
                self._xline = float(line_fn(self))
            except Exception:
                self._xline = None
        return orig(self, px, reason, gd, *a, **k)
    cls._exit = _exit
    cls._xr_line = True


def patch_init_params(cls, attr, ovr_ref):
    """__init__ 의 파라미터 dict(키워드 attr 또는 위치 인자 p)에 OVR 을 덧씌운다 — 청산 키만."""
    if getattr(cls, "_xr_init", False):
        return
    orig = cls.__init__

    def __init__(self, *a, **k):
        ov = ovr_ref.get("ovr") or {}
        if ov:
            if attr in k:
                k[attr] = {**k[attr], **ov}
            else:
                a = list(a)
                idx = ovr_ref["pos"]
                a[idx] = {**a[idx], **ov}
        orig(self, *a, **k)
        post = ovr_ref.get("post")
        if post is not None:
            post(self)
    cls.__init__ = __init__
    cls._xr_init = True


# ── 계좌 거래 요약 ─────────────────────────────────────────────────────────────
def trade_rows(runs, bars, cost_rt, cal):
    """씨앗별 거래 → (seed, ticker, gd, xgd, E, xpx, k, cost_basis, why, line, kq, net, whip)."""
    rows = []
    for sd, r in enumerate(runs):
        for ps in r["trades"]:
            s = ps.s
            b = bars[s.ticker]
            E = float(ps.E)
            xp = ps.exit_px
            if xp is None or E <= 0:
                continue
            net = float(xp) / E - 1.0 - cost_rt
            whip = np.nan
            if ps.exit_gd is not None and net < 0 and ps.exit_reason not in ("END", "OPEN"):
                di = b["di"]
                k = int(np.searchsorted(di, ps.exit_gd))
                if k < len(di) and di[k] == ps.exit_gd and k + 1 < len(di):
                    seg = b["c"][k + 1:k + 21]
                    whip = float(len(seg) > 0 and np.max(seg) >= E)
            rows.append((sd, s.ticker, int(s.gd), None if ps.exit_gd is None else int(ps.exit_gd), E, float(xp),
                         float(getattr(ps, "k", 0.0)), float(ps.cost_basis), str(ps.exit_reason),
                         getattr(ps, "_xline", None), _kq_of(s), net, whip))
    return pd.DataFrame(rows, columns=["seed", "ticker", "gd", "xgd", "E", "xpx", "k", "cb", "why", "line", "kq", "net", "whip"])


# ── M6 급락장 손실 분해 ─────────────────────────────────────────────────────────
def crash_spells(cal, ser_csv):
    ser = pd.read_csv(ser_csv, index_col=0, parse_dates=True)
    ks = ser["kospi"].dropna()
    k20 = ks / ks.shift(20) - 1.0
    mark = pd.Series(False, index=ks.index)
    for i in np.nonzero((k20 <= -0.10).to_numpy())[0]:
        mark.iloc[max(0, i - 19):i + 1] = True
    cd = set(mark.index[mark.to_numpy()])
    isc = np.array([d in cd for d in cal])
    sp, i = [], 0
    while i < len(cal):
        if isc[i]:
            j = i
            while j < len(cal) and isc[j]:
                j += 1
            sp.append((i, j - 1))
            i = j
        else:
            i += 1
    return sp


def _close_at(b, gd):
    di = b["di"]
    k = int(np.searchsorted(di, gd, side="right")) - 1
    return float(b["c"][k]) if k >= 0 else np.nan


def m6(runs, curves, bars, cal, spells, g0):
    """씨앗별·구간별 분해. 반환 = list(seed) of list(dict per spell)."""
    out = []
    for sd, r in enumerate(runs):
        eq = curves[sd]["eq"]
        rows = []
        for (a, z) in spells:
            if a - 1 < g0 or z - g0 >= len(eq):
                continue
            e0 = float(eq[a - 1 - g0])
            acc = {"a": a, "z": z, "eq0": e0, "pre_line": 0.0, "pre_gap": 0.0, "pre_other": 0.0, "pre_open": 0.0,
                   "pre_hold": 0.0, "new_line": 0.0, "new_gap": 0.0, "new_other": 0.0, "new_open": 0.0, "n_pre": 0, "n_new": 0}
            for ps in r["trades"]:
                s = ps.s
                eg = int(s.gd)
                xg = ps.exit_gd
                if eg > z or (xg is not None and xg < a):
                    continue
                if xg is not None and xg == a - 1:
                    continue
                b = bars[s.ticker]
                k = float(getattr(ps, "k", 0.0))
                pre = eg < a
                ref = _close_at(b, a - 1) if pre else float(ps.E)
                if not np.isfinite(ref):
                    continue
                tag = "pre" if pre else "new"
                acc["n_" + tag] += 1
                if pre:
                    cz = _close_at(b, z)
                    if np.isfinite(cz):
                        acc["pre_hold"] += k * (cz - ref)
                if xg is not None and xg <= z:
                    xp = float(ps.exit_px)
                    ln = getattr(ps, "_xline", None)
                    if ps.exit_reason in ("CRASH_EXIT", "STALL_EXIT", "TIME_EXIT", "TREND_EXIT", "END") or ln is None or not np.isfinite(ln):
                        acc[tag + "_other"] += k * (xp - ref)
                    elif xp < ln - 1e-9:
                        acc[tag + "_line"] += k * (ln - ref)
                        acc[tag + "_gap"] += k * (xp - ln)
                    else:
                        acc[tag + "_line"] += k * (xp - ref)
                else:
                    cz = _close_at(b, z)
                    if np.isfinite(cz):
                        acc[tag + "_open"] += k * (cz - ref)
            rows.append(acc)
        out.append(rows)
    return out
