"""cycle273 D3 (2026-09-10) — `[kojiro_band_observe]` 고지로 후보 순위 shadow 관측 leaf.

**행위 변경 0.** 구조는 형제 leaf(cycle268, 갭 판정 shadow 관측) 그대로, 이름만
band 계열이다(이름 충돌 실측 — spec §4.2). 정본 명세 =
`_workspace/red/cycle273c_kojiro_rank_restore_spec.md` §4.

## 왜 이 관측이 필요한가

`KojiroStrategy._rank_candidate_components`(cycle273-D3)가 후보 순위 성분①②를
원설계 식으로 복원했다. 이 leaf 는 그 복원 전후 두 식(현행 `exp1`/`slope_raw` 과
복원 `exp5`/`slope_pct`)을 **한 행에 나란히** 남겨, 배포 후 순위 변화가 실제로
그 시정에서 왔는지를 grep 한 번으로 대조할 수 있게 한다.

## leaf 계약 (cycle264 시가 관측 leaf / cycle268 갭 판정 관측 leaf 선례)

- **never-raise** — `observe_band`/`absorb_band_call_failure` 본체 전체가
  `try`/`except Exception` 하나. 반환값은 항상 `None`.
- **read-only** — 넘겨받은 `band_raw`/`ranked_final`/`held_only`/`scores` 를
  읽기만 한다. 어떤 공유 dict 도 생성·변경하지 않는다(cycle242 G-242-8 동형).
- **`await`/DB/HTTP 0건** — `prepare` 의 동기 구간(점수 확정 직후)에서 불린다.
- **`_score_candidates` 를 복제하지 않는다** — 본체가 바뀌는 날 복제본이 조용히
  어긋나 판독이 거짓말을 하므로, 원자료(`exp1`/`exp5`/`slope_raw`/`slope_pct`)만
  남기고 반사실 순위(`rank_if_cur`)는 넣지 않는다(오프라인 재계산으로 얻는다).
- **임계 판정·차단 플래그를 넣지 않는다**(cycle228 `would_pass` 의미 반전 선례).
- cap = `KstDailyEmitCap`(자기 날짜 리셋), 키 = `(ticker, role)` — 같은 종목이
  후보이면서 동시에 보유(청산 감시)라는 사실이 ticker 단독 키로는 지워진다.
- 실패는 `observer_trace.trace_observer_failure(MARKER, key, _cap)` — 무흔적
  `pass` 금지(cycle258 카드 #5).

## 한 행의 서식 (필드 순서 = 파싱 계약)

    [kojiro_band_observe] ticker= name= role= rank= bar= close= atr= atr_pct=
                          bw= bw_close_pct= bw_atr= bw_prev1= bw_prev5=
                          exp1= exp5= slope_raw= slope_pct= dist61= score=

`atr_pct`(=atr/close×100) · `bw_close_pct`(=bw/close×100) · `bw_atr`(=bw/atr) 는
**leaf 가 계산**한다(본체는 원자료 12원소만 stash). 분모가 0/None/비수치면 `-`.
`rank` 는 `ranked_final` 의 0-base 인덱스(held 는 `-`), `score` 미상도 `-`
(0.0 위장 금지).
"""
from __future__ import annotations

import logging

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger(__name__)

MARKER = "[kojiro_band_observe]"

# 키 = (ticker, role) — 명세 §4.1. 날짜 리셋은 `KstDailyEmitCap` 자기 리셋에
# 맡긴다(호출부에 날짜 블록을 두지 않는다 — cycle258 표준).
_cap: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()


def reset_kojiro_band_observe_cap() -> None:
    """cap 강제 초기화 (테스트·운영 훅 — 형제 leaf(cycle268)의 동형 리셋 훅 선례)."""
    global _cap
    _cap = KstDailyEmitCap()


def absorb_band_call_failure(caller) -> None:
    """호출 지점(`kojiro.prepare`)의 `observe_band` 호출 자체가 터졌을 때의 흔적.

    **never-raise.** 무흔적 `pass` 로 두면 관측기가 죽어도 아무도 모르고, 그러면
    이 마커의 결측이 '변화 없음' 으로 오독된다(cycle258 카드 #5 가 금지한 형태).
    """
    try:
        trace_observer_failure(MARKER, str(caller), _cap)
    except Exception:  # pragma: no cover — 2차 예외도 흡수(cycle258 J-3 계약)
        pass


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def _safe_pct(num, den) -> str:
    """`num/den*100` 을 소수 2자리 문자열로. 분모 0/None/비수치는 `-`."""
    try:
        if den is None or float(den) == 0:
            return "-"
        return f"{float(num) / float(den) * 100:.2f}"
    except Exception:
        return "-"


def _safe_ratio(num, den) -> str:
    """`num/den` 을 소수 2자리 문자열로(×100 없음). 분모 0/None/비수치는 `-`."""
    try:
        if den is None or float(den) == 0:
            return "-"
        return f"{float(num) / float(den):.2f}"
    except Exception:
        return "-"


def observe_band(
    band_raw,
    ranked_final,
    held_only,
    scores=None,
) -> None:
    """`[kojiro_band_observe]` — `ranked_final + held_only` 순서로 행마다 1건 방출.

    cap 1회/(ticker,role)/일. **never-raise** — 본체 전체가 단일 `try`.
    개별 ticker 의 stash 가 계약(12원소 튜플)을 어겨도 그 ticker 만 건너뛰고
    나머지는 계속 처리한다(한 종목의 결손이 전체 배치를 죽이지 않는다).
    """
    try:
        scores_map = scores or {}
        entries = [(t, "candidate", i) for i, t in enumerate(ranked_final or [])]
        entries += [(t, "held", None) for t in (held_only or [])]
        for ticker, role, idx in entries:
            try:
                key = (str(ticker), role)
                if not _cap.should_emit(key):
                    continue
                row = band_raw.get(ticker) if isinstance(band_raw, dict) else None
                if not (isinstance(row, tuple) and len(row) == 12):
                    continue
                (name, bar, close, atr, bw, bw_prev1, bw_prev5,
                 exp1, exp5, slope_raw, slope_pct, dist61) = row
                rank_str = str(idx) if idx is not None else "-"
                score = scores_map.get(ticker)
                logger.info(
                    "%s ticker=%s name=%s role=%s rank=%s bar=%s close=%s atr=%s "
                    "atr_pct=%s bw=%s bw_close_pct=%s bw_atr=%s bw_prev1=%s bw_prev5=%s "
                    "exp1=%s exp5=%s slope_raw=%s slope_pct=%s dist61=%s score=%s",
                    MARKER, ticker, _fmt(name), role, rank_str, _fmt(bar), _fmt(close),
                    _fmt(atr), _safe_pct(atr, close), _fmt(bw), _safe_pct(bw, close),
                    _safe_ratio(bw, atr), _fmt(bw_prev1), _fmt(bw_prev5),
                    _fmt(exp1), _fmt(exp5), _fmt(slope_raw), _fmt(slope_pct),
                    _fmt(dist61), _fmt(score),
                )
                _cap.mark_emitted(key)
            except Exception:
                continue
    except Exception:
        trace_observer_failure(MARKER, "batch", _cap)
