"""RS(상대강도) 점수 — 순수 함수, I/O 0 (명세 `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §A).

- `ibd_lite_return` : 0.4·r63 + 0.3·r126 + 0.3·r189 (종가 시계열은 오래된→최신).
- `percentile_ranks` : 모집단 안 백분위 0~99 (동점 = 최소 순위, None 은 빼고 None 유지).
- `sector_relative`  : 섹터 동일가중 평균 대비 상대값 + 섹터 간/섹터 내 백분위.

결측은 감점하지 않는다 — None 을 돌려주고 소비처가 fail-open 으로 다룬다.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

_LOOKBACKS: tuple[tuple[int, float], ...] = ((63, 0.4), (126, 0.3), (189, 0.3))
_MIN_BARS = 190  # 189봉 + 1
_UNCLASSIFIED_PREFIX = "미분류"
_NONE_ENTRY = {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}


def ibd_lite_return(closes: Sequence[float]) -> float | None:
    """IBD-lite 가중 수익률. 190봉 미만 또는 쓰는 가격이 0 이하면 None."""
    if len(closes) < _MIN_BARS:
        return None
    last = closes[-1]
    if last <= 0:
        return None
    total = 0.0
    for n, w in _LOOKBACKS:
        base = closes[-1 - n]
        if base <= 0:
            return None
        total += w * (last / base - 1.0)
    return total


def percentile_ranks(scores: Mapping[str, float | None]) -> dict[str, int | None]:
    """오름차순 백분위 0~99. n==1 → 99, 동점은 최소 순위."""
    vals = sorted(v for v in scores.values() if v is not None)
    n = len(vals)
    out: dict[str, int | None] = {}
    first_rank: dict[float, int] = {}
    for i, v in enumerate(vals):
        first_rank.setdefault(v, i + 1)
    for k, v in scores.items():
        if v is None:
            out[k] = None
        elif n == 1:
            out[k] = 99
        else:
            out[k] = int(99 * (first_rank[v] - 1) // (n - 1))
    return out


def sector_relative(
    scores: Mapping[str, float | None],
    sector_of: Mapping[str, str],
    min_members: int = 5,
) -> dict[str, dict]:
    """종목별 {"vs_sector", "sector_pct", "in_sector_pct"} — 자격 없으면 전부 None."""
    members: dict[str, list[str]] = defaultdict(list)
    for t, v in scores.items():
        sec = sector_of.get(t)
        if v is None or sec is None or sec.startswith(_UNCLASSIFIED_PREFIX):
            continue
        members[sec].append(t)
    eligible = {s: ts for s, ts in members.items() if len(ts) >= min_members}
    means = {s: sum(scores[t] for t in ts) / len(ts) for s, ts in eligible.items()}  # type: ignore[misc]
    sector_pcts = percentile_ranks(means)
    out: dict[str, dict] = {t: dict(_NONE_ENTRY) for t in scores}
    for sec, ts in eligible.items():
        in_pcts = percentile_ranks({t: scores[t] for t in ts})
        for t in ts:
            out[t] = {
                "vs_sector": scores[t] - means[sec],  # type: ignore[operator]
                "sector_pct": sector_pcts[sec],
                "in_sector_pct": in_pcts[t],
            }
    return out
