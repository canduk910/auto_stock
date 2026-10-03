"""재현 틀 — 유니버스 층.

라이브 상수를 import 한다(재현 쪽에서 유니버스를 따로 정의하다 ETF 가 섞인 cycle375 사고를
되풀이하지 않는다 — 지시서 §3.1). ``src.engine.etf_like`` 는 표준 라이브러리만 쓰는 leaf 다.

- ① today: 보관소 마지막 날 살아 있고 시총 ≥ 500억 ∧ 거래대금 ≥ 10억(kojiro 일봉 적재 자격선
  ``scanner._DAILY_LOAD_MIN_TRADE_WON`` = 10억과 같은 값) — 생존편향이 있는 쪽.
- ② asof: 그날(t) 시총 ≥ 500억 — t 일 진입 자격만 가른다. 상장폐지 종목 포함.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine.etf_like import is_etf_like  # noqa: E402  (라이브 판정 그대로)

MIN_MKTCAP_WON = 50_000_000_000      # 500억 (보관소 mktcap 은 원 단위)
MIN_TRADE_WON = 1_000_000_000        # 10억
MAX_MISSING_RATIO = 0.01             # §3.2 결측률 > 1% 종목 제외


def base_exclusions(panel, group_codes: "dict | None" = None) -> "dict[str, str]":
    """제외 사유 = {ticker: reason}. ETF류 · 6자리 숫자 아님 · 결측률 > 1%."""
    out = {}
    for j, t in enumerate(panel.tickers):
        raw = {"scty_grp_id_cd": group_codes.get(t)} if group_codes and group_codes.get(t) else None
        if not (len(t) == 6 and t.isdigit()):
            out[t] = "code"
            continue
        if is_etf_like(raw, panel.names.get(t, "")):
            out[t] = "etf_like"
            continue
        c = panel.c[:, j]
        fin = np.where(np.isfinite(c))[0]
        if len(fin) == 0:
            out[t] = "empty"
            continue
        span = slice(fin[0], fin[-1] + 1)
        seg_c = panel.c[span, j]
        seg_v = panel.vol[span, j]
        missing = np.mean(~np.isfinite(seg_c) | ~(np.nan_to_num(seg_v) > 0))
        if missing > MAX_MISSING_RATIO:
            out[t] = "missing"
    return out


def today_set(panel) -> "set[str]":
    i = len(panel.dates) - 1
    cap, tv = panel.mktcap[i], panel.tv[i]
    return {t for j, t in enumerate(panel.tickers)
            if np.isfinite(cap[j]) and cap[j] >= MIN_MKTCAP_WON and np.nan_to_num(tv[j]) >= MIN_TRADE_WON}


def asof_mask(panel) -> np.ndarray:
    """(날짜 × 종목) bool — 그날 시총 ≥ 500억."""
    return np.nan_to_num(panel.mktcap) >= MIN_MKTCAP_WON
