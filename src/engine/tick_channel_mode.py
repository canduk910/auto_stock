"""cycle293 — 시세 채널 리졸버 킬스위치 모드 leaf.

`scanner.tick_tr_id_for()` 가 **얼마나** 적용될지를 고르는 단일 상태다. 값은
`system_config.tick_channel_resolver_mode` 한 키에서 온다(전략 파라미터 축이
아니다 — 리졸버는 인프라 축이고, 7전략 `DEFAULT_PARAMS` 에 넣으면 7곳이 갈릴
수 있다. 명세 §8-B).

| 모드 | 뜻 |
|---|---|
| ``off`` | 리졸버가 전 종목 `TICK_TR_ID`(통합) 반환 = **오늘과 동일**. 롤백 위치 |
| ``observe`` | 판정은 하고 로그만 남긴다. 반환은 통합 = **행위 0**(다크런치 S0) |
| ``enforce_low`` | LOW(스캐닝 후보)만 전용 채널로. HIGH(보유·익일청산) 제외(S1) |
| ``enforce`` | HIGH 포함 전면(S2) |

## 🔴 재시작을 요구하지 않는다 (cycle287 의 실패를 반복하지 않는다)

cycle287 은 킬스위치 2개를 `param_catalog` 미등재로 만들어 `PUT
/api/strategies/{id}/params` 가 `unknown_key` 422 를 돌려줬다 = **장중에 끌 수
없었다**. 그리고 D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지) 때문에
"다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다.

그래서 `refresh_mode()` 는 **몇 번이든 다시 읽는다** — `_load_strategy_config`
가 쓰는 "프로세스당 1회" 래치 같은 것을 두지 않는다(회귀 가드가 그 래치 이름의
출현 0건을 이 파일에 강제한다). 재조회 배선은 두 곳이고 둘 다 스케줄러
무접촉이다:

  * `scanner.subscribe_filtered_stocks` (5분 `_scan_loop`)
  * `stale_watcher_core.check_and_resubscribe_stale` (120초)

즉시(≤1초) 끄려면 `PUT /api/realtime/tick-channel-mode {"mode": "off"}` —
그 라우트가 DB 에 쓰고 이 모듈의 메모리 값까지 같은 요청에서 덮는다.

## 실패 방향

- DB 조회 실패·키 부재(`None`) = **현재 값 유지**. 기본값으로 되돌리지 않는다
  (운영자가 `off` 로 내려놓은 뒤 조회가 한 번 실패했다고 다시 켜지면 안 된다).
- 미지 값(예: DB 에 `"ENFORCE_EVERYTHING"`) = 현재 값 유지 + WARNING 1행.

## 시각 리터럴 0건 (명세 C-2)

이 모듈에 `time(H, M)` 류 시각 창을 두지 않는다. 플리커 백스톱은 시간 창이
아니라 출처(provenance) 검사 + KST **날짜** 키다 — 오염 창의 양끝(07:45~08:08)이
일정 파생값이고 그 일정은 이미 두 번 움직였다(일봉 16:00→18:10→20:30).
"""
from __future__ import annotations

import logging

from src.engine.daily_emit_cap import KstDailyEmitCap

# 🔴 로거 이름은 이 모듈 자신이다(적대 검증 L2 — 정직화).
#
# 종전에는 `"src.engine.scheduler"` 로 고정하고 "사이클 60 I1 — `system_logs`
# 접두 연속성" 을 근거로 적었는데, **이 파일의 마커는 전부 신규**라 연속시킬
# 과거가 없다(그 관례는 기존 마커가 접두를 바꾸면 운영 grep 이 깨지는 경우를
# 위한 것이다). 대신 운영 grep 의 정본은 **마커 문자열**임을 여기 적어 둔다 —
# `[tick_channel_*]` 5종은 `scanner`·`websocket_pool`·이 모듈 세 로거로 나뉘므로
# 로거 접두가 아니라 마커로 찾는다.
logger = logging.getLogger(__name__)

#: `system_config` 키 (명세 §8-B 권고 이름 — 운영 문서·루틴이 이 이름을 쓴다).
CONFIG_KEY = "tick_channel_resolver_mode"

MODE_OFF = "off"
MODE_OBSERVE = "observe"
MODE_ENFORCE_LOW = "enforce_low"
MODE_ENFORCE = "enforce"

VALID_MODES: frozenset[str] = frozenset(
    {MODE_OFF, MODE_OBSERVE, MODE_ENFORCE_LOW, MODE_ENFORCE}
)

#: 배포 기본값 = 명세 §8-A 의 S0(다크런치) = 행위 0.
DEFAULT_MODE = MODE_OBSERVE

_MARKER_INVALID = "[tick_channel_mode_invalid]"
_MARKER_PARAM_INVALID = "[tick_channel_param_invalid]"

# ── cycle294 §9-E — 3단계 전환 파라미터 4키 (전부 `system_config` 축) ────────
#
# 🔴 모드 enum 을 늘리지 않는다(절대 규칙 8). 「채널이 문제다」와 「전환이
#    문제다」는 다른 결정이고, 하나의 enum 에 태우면 운영자가 후자만 끌 수 없다.
#    `tick_channel_switch_enabled=false` 는 **살아 있는 구독의 전환만** 멈춘다 —
#    신규 구독의 시각축 판정은 유지된다. 이것이 자동 원복의 수동 대응물이다.
#
# 클램프는 **읽는 쪽**에서 한다. 조회 실패·키 부재·범위 밖은 전부 현재 값
# 유지 + `[tick_channel_param_invalid]` 1회/(key)/일 (기본값 되돌림 금지).
SWITCH_ENABLED_KEY = "tick_channel_switch_enabled"
SWITCH_OFFSET_SECS_KEY = "tick_channel_switch_offset_secs"
SWITCH_ACK_TIMEOUT_SECS_KEY = "tick_channel_switch_ack_timeout_secs"
REVERT_PROBE_SECS_KEY = "tick_channel_revert_probe_secs"
#: 🔴 적대 검증 CRITICAL-1 — NXT 단독 연속 구간(09-15 = 15:40~16:00) 커버리지.
GAP_HOLD_ENABLED_KEY = "tick_channel_gap_hold_enabled"

DEFAULT_SWITCH_ENABLED = True
#: 기본 **켜짐** — 꺼짐이 기본이면 INV-1 위반(매일 20분 손절 blind)이 기본이 된다.
DEFAULT_GAP_HOLD_ENABLED = True
#: 전환 offset 기본값의 정본은 `tick_channel_clock.DEFAULT_SWITCH_OFFSET_SECS` 다.
DEFAULT_SWITCH_ACK_TIMEOUT_SECS = 5.0
_ACK_TIMEOUT_RANGE = (1.0, 30.0)
_REVERT_PROBE_RANGE = (60.0, 900.0)

# ── 모듈 전역 상태 ──────────────────────────────────────────────────────────
_mode: str = DEFAULT_MODE
_switch_enabled: bool = DEFAULT_SWITCH_ENABLED
_gap_hold_enabled: bool = DEFAULT_GAP_HOLD_ENABLED
_switch_offset_secs: int | None = None
_switch_ack_timeout_secs: float = DEFAULT_SWITCH_ACK_TIMEOUT_SECS
_revert_probe_secs: float | None = None
#: 🔴 적대 검증 LOW(부팅) 시정 — 종전에는 평범한 set 이라 경고가 **프로세스당
#: 1회/키** 였다(§11-A 는 "1회/(key)/일" 을 요구한다). `system_config` 에 범위 밖
#: 값을 넣어 두면 첫 WARNING 뒤 영영 리포트에 뜨지 않았다.
_param_warned: "KstDailyEmitCap[str]" = KstDailyEmitCap()


def switch_enabled() -> bool:
    """살아 있는 구독의 전환을 실행해도 되는가 (§9-D)."""
    return _switch_enabled


def gap_hold_enabled() -> bool:
    """NXT 단독 연속 구간에서 HIGH 가 NXT 를 따라가는가 (CRITICAL-1 다이얼)."""
    return _gap_hold_enabled


def switch_offset_secs() -> int:
    """프리장 종료 뒤 전환까지의 offset (초). 상한 클램프는 시각축 leaf 가 한다."""
    if _switch_offset_secs is None:
        from src.engine.tick_channel_clock import DEFAULT_SWITCH_OFFSET_SECS

        return DEFAULT_SWITCH_OFFSET_SECS
    return _switch_offset_secs


def switch_ack_timeout_secs() -> float:
    """make-before-break 의 신 채널 ACK 대기 상한 (초)."""
    return _switch_ack_timeout_secs


def revert_probe_secs() -> float | None:
    """자동 원복 측정 offset (초). `None` = 호출자가 기존 grace 상수를 재사용한다."""
    return _revert_probe_secs


def _clamp(value, low: float, high: float) -> float:
    return max(low, min(high, value))


def _warn_param(key: str, stored) -> None:
    try:
        _param_warned.emit_once(
            key, logger.warning, f"{_MARKER_PARAM_INVALID} key={key} stored={stored!r}",
        )
    except Exception:  # pragma: no cover — never-raise
        pass


def current_mode() -> str:
    """현재 모드 (동기 — 리졸버가 hot path 에서 읽는다)."""
    return _mode


def _set_mode(mode: str) -> bool:
    """내부 전환기. 값이 실제로 바뀌면 관측 cap 을 리셋하고 True 를 돌려준다."""
    global _mode
    if mode not in VALID_MODES or mode == _mode:
        return False
    _mode = mode
    _reset_observation_caps()
    return True


def _reset_observation_caps() -> None:
    """모드가 바뀌면 새 모드의 판정이 **다시 한 번** 로그에 남아야 한다.

    관측 cap 은 하루 1회라 모드를 바꾼 뒤에도 그대로면 그날의 나머지 시간 동안
    "무엇이 바뀌었는지" 를 볼 수 없다(배포 카나리아 상실).
    """
    try:
        from src.engine import scanner  # lazy — 순환 import 회피(scanner → 이 모듈)

        scanner.reset_tick_channel_observation_caps()
    except Exception:  # pragma: no cover — never-raise (관측 실패가 모드를 막지 않는다)
        pass


async def refresh_mode() -> str:
    """`system_config` 를 다시 읽어 모드를 갱신하고 결과를 반환한다.

    **반복 호출 가능**(once-latch 금지, §8-B). 실패·키 부재·미지 값은 현재 값 유지.
    """
    raw = None
    try:
        import src.db.system_config as sysconf  # lazy — 테스트 patch seam

        getter = getattr(sysconf, "get_tick_channel_resolver_mode", None)
        if getter is not None:
            raw = await getter()
    except Exception:
        logger.debug("[tick_channel_mode] system_config 조회 실패 — 현재 모드 유지", exc_info=True)
        return _mode

    if raw is None:
        # 키 부재 또는 조회 graceful None — 현재 값 유지(기본값 되돌림 금지).
        return _mode
    candidate = str(raw).strip()
    if candidate not in VALID_MODES:
        logger.warning(
            "%s stored=%r — 유효 모드 %s 밖. 현재 모드 %s 유지",
            _MARKER_INVALID, raw, sorted(VALID_MODES), _mode,
        )
        return _mode
    _set_mode(candidate)
    return _mode


async def refresh_switch_params() -> None:
    """전환 파라미터 4키를 다시 읽는다 — **반복 호출 가능**(once-latch 금지).

    `refresh_mode()` 와 같은 배선(5분 `subscribe_filtered_stocks` · 120초
    `stale_watcher_core`)에서 불린다. 실패·키 부재·범위 밖은 현재 값 유지.
    """
    global _switch_enabled, _switch_offset_secs, _switch_ack_timeout_secs
    global _revert_probe_secs, _gap_hold_enabled
    try:
        import src.db.system_config as sysconf  # lazy — 테스트 patch seam
    except Exception:  # pragma: no cover — never-raise
        return
    try:
        raw = await sysconf.get_tick_channel_switch_enabled()
        if raw is not None:
            _switch_enabled = bool(raw)
    except Exception:
        logger.debug("[tick_channel_mode] switch_enabled 조회 실패 — 현재 값 유지")
    try:
        getter = getattr(sysconf, "get_tick_channel_gap_hold_enabled", None)
        if getter is not None:
            raw = await getter()
            if raw is not None:
                _gap_hold_enabled = bool(raw)
    except Exception:
        logger.debug("[tick_channel_mode] gap_hold 조회 실패 — 현재 값 유지")
    try:
        raw = await sysconf.get_tick_channel_switch_offset_secs()
        if raw is not None:
            if float(raw) < 0:
                _warn_param(SWITCH_OFFSET_SECS_KEY, raw)
            else:
                _switch_offset_secs = int(float(raw))
    except Exception:
        logger.debug("[tick_channel_mode] switch_offset 조회 실패 — 현재 값 유지")
    try:
        raw = await sysconf.get_tick_channel_switch_ack_timeout_secs()
        if raw is not None:
            low, high = _ACK_TIMEOUT_RANGE
            if not (low <= float(raw) <= high):
                _warn_param(SWITCH_ACK_TIMEOUT_SECS_KEY, raw)
            _switch_ack_timeout_secs = _clamp(float(raw), low, high)
    except Exception:
        logger.debug("[tick_channel_mode] ack_timeout 조회 실패 — 현재 값 유지")
    try:
        raw = await sysconf.get_tick_channel_revert_probe_secs()
        if raw is not None:
            low, high = _REVERT_PROBE_RANGE
            if not (low <= float(raw) <= high):
                _warn_param(REVERT_PROBE_SECS_KEY, raw)
            _revert_probe_secs = _clamp(float(raw), low, high)
    except Exception:
        logger.debug("[tick_channel_mode] revert_probe 조회 실패 — 현재 값 유지")


def apply_switch_enabled(enabled: bool) -> bool:
    """라우트용 즉시 반영 진입점 — DB 쓰기는 호출자 책임(§9-D)."""
    global _switch_enabled
    _switch_enabled = bool(enabled)
    return _switch_enabled


def apply_gap_hold_enabled(enabled: bool) -> bool:
    """라우트용 즉시 반영 진입점 — DB 쓰기는 호출자 책임(CRITICAL-1 다이얼)."""
    global _gap_hold_enabled
    _gap_hold_enabled = bool(enabled)
    return _gap_hold_enabled


def apply_mode(mode: str) -> str:
    """라우트(`PUT /api/realtime/tick-channel-mode`)용 즉시 반영 진입점.

    DB 쓰기는 호출자 책임 — 이 함수는 **메모리 값만** 덮어 같은 요청 안에서
    킬스위치가 듣게 한다(재시작·다음 폴링 대기 없음).
    """
    if mode not in VALID_MODES:
        raise ValueError(f"tick_channel_resolver_mode must be one of {sorted(VALID_MODES)}")
    _set_mode(mode)
    return _mode


# ── 테스트 seam ────────────────────────────────────────────────────────────
def set_mode_for_test(mode: str) -> None:
    """테스트에서 모드를 강제한다(미지 값도 그대로 심어 폴백 경로를 검증)."""
    global _mode
    changed = mode != _mode
    _mode = mode
    if changed:
        _reset_observation_caps()


def reset_state_for_test() -> None:
    """모듈 전역 상태 초기화 (테스트 격리 seam).

    cycle293 Green — `scanner` 의 **채널 판정 이력**(`_channel_applied` /
    `_channel_flipped_today` = §6-D 하루 1회 전환 예산)까지 함께 비운다. 종전에는
    관측 cap 만 비워서 그 이력이 테스트 사이에 살아남았고, `test_g7b`(같은 날
    재전환 차단)가 **앞선 테스트가 소모해 둔 예산**에 의존해 파일 내 실행 순서에
    좌우됐다(적대 검증 지적). 이력이 남으면 `risk` 의 매수 축 게이트 테스트도
    앞 테스트의 잔재를 본다.
    """
    global _mode, _switch_enabled, _switch_offset_secs, _switch_ack_timeout_secs
    global _revert_probe_secs, _gap_hold_enabled
    _mode = DEFAULT_MODE
    _switch_enabled = DEFAULT_SWITCH_ENABLED
    _gap_hold_enabled = DEFAULT_GAP_HOLD_ENABLED
    _switch_offset_secs = None
    _switch_ack_timeout_secs = DEFAULT_SWITCH_ACK_TIMEOUT_SECS
    _revert_probe_secs = None
    _param_warned.clear()
    try:
        from src.engine import tick_channel_switch

        tick_channel_switch.reset_state_for_test()
    except Exception:  # pragma: no cover — never-raise
        pass
    try:
        from src.engine import scanner  # lazy — 순환 import 회피

        scanner.reset_tick_channel_state_for_test()
    except Exception:  # pragma: no cover — never-raise
        _reset_observation_caps()


def set_switch_params_for_test(
    *,
    switch_enabled: bool | None = None,
    offset_secs: int | None = None,
    ack_timeout_secs: float | None = None,
    revert_probe_secs: float | None = None,
    gap_hold_enabled: bool | None = None,
) -> None:
    """전환 파라미터 5키 테스트 seam (§9-E + CRITICAL-1). 준 것만 덮는다."""
    global _switch_enabled, _switch_offset_secs, _switch_ack_timeout_secs
    global _revert_probe_secs, _gap_hold_enabled
    if switch_enabled is not None:
        _switch_enabled = bool(switch_enabled)
    if gap_hold_enabled is not None:
        _gap_hold_enabled = bool(gap_hold_enabled)
    if offset_secs is not None:
        _switch_offset_secs = int(offset_secs)
    if ack_timeout_secs is not None:
        _switch_ack_timeout_secs = float(ack_timeout_secs)
    if revert_probe_secs is not None:
        _revert_probe_secs = float(revert_probe_secs)
