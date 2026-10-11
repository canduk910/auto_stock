"""나스닥2배-위험회피(ndx2x_riskoff) 순수 leaf — 규칙 C 신호·상태·KIS 파서.

정본 = `_workspace/domain_consult/2026-10-06_ndx2x_risk_off.md` + 연구 규칙 원본
`tools/replay/ra_us.py::feats_from_close`. 운영 신호 함수는 그 연구 함수와 날짜별로
**완전히 일치**해야 한다(자문 「후속 검증 권고」 1). 새 규칙·새 최적화·평활·손절 추가 금지.

표준 라이브러리(`dataclasses`·`datetime`·`typing`)만 import — `src.*` import 0,
I/O 0, `await` 0, 로깅 0 (다른 전략의 `*_core.py` leaf 관례, 예: `etf_trend_core.py`).

규칙 C (동결, 나스닥100 환노출):
- T7 = SMA120(t) / SMA120(t-20) - 1   (120일선의 20영업일 기울기)
- R4 = close(t) / max(close[t-249..t]) - 1   (종가 기준 250일 최고 종가, 당일 포함)
- 칸 = f"{int(T7>0)}{int(R4<=-0.20)}". 칸 "01"(기울기 하락 ∧ 고점 −20% 넘게 하락) → 현금.
  그 외(00·10·11) → 2배 100%.
- 경계: `R4 == -0.20` 은 `<=` 라 조건 성립(현금 쪽 성분). `T7 == 0` 은 `> 0` 이 아니므로
  조건1 거짓(기울기 하락 성립, "0" 비트).
- 연구 규약(결측=조건 거짓 → 칸 00 → 2배)은 **이력 시작점 처리용**이다. 운영에서
  이력 부족·특징 NaN 은 연구 규약을 따르지 않고 **fail-closed**(매매 없음 + 경보,
  직전 상태 유지) 한다 — 아래 `decide_daily` 의 `reason != "ok"` 분기.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Literal

#: SMA 기간(T7) — `ra_us.feats_from_close` T7 정의와 동치. 바꾸면 규칙 C 가 아니다.
T7_SMA_WINDOW = 120
#: T7 기울기 시차(영업일) — 바꾸면 규칙 C 가 아니다.
T7_LAG = 20
#: R4 250일 고점 창(당일 포함) — 바꾸면 규칙 C 가 아니다.
R4_WINDOW = 250
#: R4 임계 — `<=` (경계 포함, 현금 쪽). 바꾸면 규칙 C 가 아니다.
R4_THRESHOLD = -0.20

#: 운영 최소 이력(영업일) — R4 가 묶는 상한(250)과 동일. 자문 §3 "최소 250, 권고 300".
MIN_HISTORY_DAYS = R4_WINDOW

State = Literal["2x", "cash"]
Reason = Literal["ok", "insufficient_history", "nan_feature"]

#: 집행 창(KST, 양끝 포함) — 자문 §1(a) 권고 A. 시장가 금지(호출자 책임).
EXECUTION_WINDOW_START = time(9, 30)
EXECUTION_WINDOW_END = time(10, 30)


# ─────────────────────────── 지표(연구 함수와 날짜별 완전 일치) ───────────────────────────

def _sma(closes: list[float], window: int, i: int) -> float | None:
    """`closes[i]` 를 끝으로 하는 `window`일 단순이동평균. 이력 부족 시 None."""
    if i - window + 1 < 0:
        return None
    w = closes[i - window + 1: i + 1]
    return sum(w) / window


def compute_t7(closes: list[float], i: int) -> float | None:
    """T7 = SMA120(t)/SMA120(t-20) - 1. 두 SMA 중 하나라도 이력 부족이면 None."""
    if i - T7_LAG < 0:
        return None
    s_t = _sma(closes, T7_SMA_WINDOW, i)
    s_lag = _sma(closes, T7_SMA_WINDOW, i - T7_LAG)
    if s_t is None or s_lag is None or s_lag == 0:
        return None
    return s_t / s_lag - 1.0


def compute_r4(closes: list[float], i: int) -> float | None:
    """R4 = close(t)/max(close[t-249..t]) - 1 (당일 포함 250일 최고 종가). 이력 부족 시 None."""
    if i - R4_WINDOW + 1 < 0:
        return None
    w = closes[i - R4_WINDOW + 1: i + 1]
    peak = max(w)
    if peak <= 0:
        return None
    return closes[i] / peak - 1.0


# ─────────────────────────── 칸 행동(연구 규약 — 결측=조건 거짓) ───────────────────────────

def research_cell(t7: float | None, r4: float | None) -> str:
    """연구 규약 그대로의 칸(결측=조건 거짓). `decide_daily` 의 fail-closed 와는 다른 함수다
    — 이 함수는 `tools/replay/ra_us.py` 와의 1:1 재현 비교에만 쓴다(운영 판단에 직접 쓰지 않는다)."""
    cond1 = t7 is not None and t7 > 0
    cond2 = r4 is not None and r4 <= R4_THRESHOLD
    return f"{int(cond1)}{int(cond2)}"


def state_for_cell(cell: str) -> State:
    """칸 "01" → 현금, 그 외(00·10·11) → 2배."""
    return "cash" if cell == "01" else "2x"


# ─────────────────────────── 운영 판단(fail-closed) ───────────────────────────

@dataclass(frozen=True)
class DailyDecision:
    t7: float | None
    r4: float | None
    cell: str | None          # None = 결측/이력부족(fail-closed, 판단 보류)
    desired_state: State | None  # None = 판단 보류(직전 상태 유지, 매매 없음)
    reason: Reason


def decide_daily(closes_asc: list[float]) -> DailyDecision:
    """가장 최근 종가(`closes_asc[-1]`) 기준 하루 판단 — fail-closed.

    `closes_asc` 는 **오래된 → 최신** 오름차순(미국 거래일 달력)이어야 한다.
    이력이 `MIN_HISTORY_DAYS` 미만이거나 T7/R4 가 결측이면 판단을 보류한다
    (연구 규약의 "결측→2배" 로 새지 않는다 — 자문 §3 「이력 길이·계산 규약」).
    """
    n = len(closes_asc)
    if n < MIN_HISTORY_DAYS:
        return DailyDecision(None, None, None, None, "insufficient_history")
    i = n - 1
    t7 = compute_t7(closes_asc, i)
    r4 = compute_r4(closes_asc, i)
    if t7 is None or r4 is None:
        return DailyDecision(t7, r4, None, None, "nan_feature")
    cell = research_cell(t7, r4)
    return DailyDecision(t7, r4, cell, state_for_cell(cell), "ok")


# ─────────────────────────── 집행 창·상태 전이 ───────────────────────────

def in_execution_window(now_time: time) -> bool:
    """09:30~10:30 KST, 양끝 포함(자문 §1(a) 권고 A). 시각은 호출자가 KST 로 넘긴다."""
    return EXECUTION_WINDOW_START <= now_time <= EXECUTION_WINDOW_END


Action = Literal["BUY", "SELL", "NONE"]


def plan_action(held_state: State | None, desired_state: State | None) -> Action:
    """현재 보유 상태 → 원하는 상태의 전이 행동.

    `held_state is None`(포지션 없음 — 실보유 기준 "현금" 과 동치)은 `"cash"` 로
    간주한다. `desired_state is None`(fail-closed 보류) → 항상 "NONE"(직전 상태 유지).
    같은 상태면 "NONE"(상태 변화 없을 때 추가 매수·부분 매도 하지 않는다 — 자문 §3).
    """
    if desired_state is None:
        return "NONE"
    effective_held = held_state if held_state is not None else "cash"
    if effective_held == desired_state:
        return "NONE"
    return "BUY" if desired_state == "2x" else "SELL"


# ─────────────────────────── KIS FHKST03030100 파서 ───────────────────────────

class MalformedRowError(ValueError):
    """KIS `output2` 행 하나가 날짜·종가로 파싱되지 않음 — fail-loud(조용히 skip 금지)."""


def parse_kis_row(row: dict) -> tuple[str, float]:
    """`output2` 원소 1개 → (YYYYMMDD 문자열, 종가). 파싱 실패는 예외로 올린다."""
    bsop = str(row.get("stck_bsop_date") or "").strip()
    if not (len(bsop) == 8 and bsop.isdigit()):
        raise MalformedRowError(f"stck_bsop_date 형식 오류: {row.get('stck_bsop_date')!r}")
    try:
        close = float(row.get("ovrs_nmix_prpr"))
    except (TypeError, ValueError) as e:
        raise MalformedRowError(f"ovrs_nmix_prpr 파싱 실패: {row.get('ovrs_nmix_prpr')!r}") from e
    if close <= 0:
        raise MalformedRowError(f"ovrs_nmix_prpr <= 0: {close!r}")
    return bsop, close


def assert_latest_first(rows: list[dict]) -> None:
    """`output2` 가 최신순(날짜 내림차순)인지 검증 — KIS 계약 drift 조기 감지."""
    dates = [str(r.get("stck_bsop_date") or "") for r in rows]
    for a, b in zip(dates, dates[1:]):
        if a < b:
            raise MalformedRowError(
                f"output2 가 최신순이 아니다(KIS 계약 drift 의심): {a!r} 다음에 {b!r}"
            )


def parse_kis_rows(rows: list[dict]) -> list[tuple[str, float]]:
    """`output2` 전체(최신순) → [(YYYYMMDD, 종가), ...] 최신순 그대로. 0행은 호출자(I/O
    래퍼)가 `OverseasIndexEmptyResponseError` 로 먼저 걸러낸다(이 함수는 비어도 통과)."""
    assert_latest_first(rows)
    return [parse_kis_row(r) for r in rows]


def merge_batches(batches: list[list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """여러 번 겹치게 받은 배치를 날짜 오름차순 단일 계열로 합친다.

    `batches` 는 수신 순서(최신 구간 먼저, 과거로 커서를 당기며 호출한 순서)로 넘긴다.
    같은 날짜가 여러 배치에 나오면 **먼저 받은(더 최근을 다룬) 배치 값을 유지**한다
    (겹치는 날은 두 배치 모두 같은 값이어야 정상이고, 그렇지 않을 선택은 임의성보다
    "더 최근 호출이 그 날짜의 경계가 아니었던 쪽" 을 우선한다 — 자문 §3 "겹치게 이어붙인다").
    """
    merged: dict[str, float] = {}
    for batch in batches:
        for d, c in batch:
            merged.setdefault(d, c)
    return sorted(merged.items(), key=lambda kv: kv[0])
