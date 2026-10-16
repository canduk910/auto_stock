"""공용 — 요약 함수 감싸기(runs 받아 두기) · 씨앗별 자산곡선·투입 비율 추출 · 위약 이동량 (prereg §1·§4)."""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

SHIFTS = (126, 252, 378, 504, 756, 1008, 1260, 1512)
CAP: list = []


def wrap(mod, name):
    """mod.name(runs, ...) 를 감싸 runs 를 CAP 에 쌓는다. 반환값 무접촉."""
    orig = getattr(mod, name)

    def f(runs, *a, **k):
        CAP.append(runs)
        return orig(runs, *a, **k)
    setattr(mod, name, f)


def take():
    assert len(CAP) == 1, len(CAP)
    return CAP.pop()


def curves(runs, cal, win):
    """씨앗별 {dates, eq, inv(보유 원가 ÷ 자산), npos}."""
    g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
    g1 = int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
    out = []
    for r in runs:
        eq = np.asarray(r["equity"], float)
        assert len(eq) == g1 - g0 + 1, (len(eq), g0, g1)
        cb = np.zeros(len(eq))
        npos = np.zeros(len(eq), int)
        for ps in r["trades"]:
            a = int(ps.s.gd) - g0
            e = ps.exit_gd
            b = (g1 - g0 + 1) if e is None else int(e) - g0      # exit 날 종가 자산에는 없다
            if b <= a:
                continue
            a2, b2 = max(a, 0), min(b, len(eq))
            cb[a2:b2] += float(ps.cost_basis)
            npos[a2:b2] += 1
        out.append({"dates": np.asarray(cal[g0:g1 + 1]), "eq": eq, "inv": cb / np.maximum(eq, 1.0), "npos": npos})
    return out


def shifted(arr, k):
    return np.roll(np.asarray(arr, float), k % len(arr))


def mval(v):
    return 1.0 if (v is None or not np.isfinite(v)) else float(v)


def dump(path, obj):
    with open(path, "wb") as fh:
        pickle.dump(obj, fh, protocol=4)
