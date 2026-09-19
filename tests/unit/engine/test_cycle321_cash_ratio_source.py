"""cycle321 — 자금 사용률이 **왜 그 값인지** 로그가 답하게 한다 (D1 항목 I·J).

## 왜 필요한가 (I)

`scheduler._resolve_cash_usage_ratio` 는 반환 경로가 **넷**인데 성공 경로에 로그가
한 줄도 없다. 그래서 운영자가 「오늘 자금 사용률이 왜 이 값인가」를 로그로 답할 수 없다.

| 경로 | 조건 | 결과 | 지금까지 |
|---|---|---|---|
| ⓐ | `get_auto_regime_adjust()` 예외 | 수동값 | `logger.exception` 있음 |
| ⓑ | 자동조정 꺼짐 | 수동값 | **로그 0줄** |
| ⓒ | 레짐 산출 불가(`computed is None`) | 수동값 | **로그 0줄** |
| ⓓ | 정상 | 계산값 | 저장 실패 시만 로그 |

🔴 이게 위험한 이유 = cycle316 이 밝힌 대로, 우리 macro 가 `cash_min=75` 를 내므로
계산값은 **0.25** 가 실재한다. 예산이 4분의 1로 접히면 터틀 유닛·ρ축 cutoff·K축 cap 이
함께 접혀 고가 종목은 1주 폴백까지 막히는데, 로그에는 「매수 수량 0 → 900s cooldown」
으로만 남아 **「투자금 부족」으로 오귀인**된다. 어느 경로가 이겼는지가 그 오귀인을 끊는다.

## 마커를 새로 파는 이유

기존 `[cash_usage_ratio]` 는 이미 **다른 뜻**으로 쓰인다 —
`boot_manager.py` 의 결과 값 줄, `system_config.py` 의 조회 실패·대폭 축소 경보.
거기에 얹으면 한 마커가 네 가지를 뜻하게 된다. 그래서 `[cash_usage_ratio_source]` 를 판다.

🔴 값 필드는 `ratio=` 가 아니라 **`applied=`** 다. 월요일 확인 목록이
`[cash_usage_ratio] ratio=1.00` 을 기대하는데, 같은 `ratio=1.00` 토큰이 두 줄에 생기면
느슨한 grep 이 한 줄을 두 줄로 센다.

## J — 거짓 주석

같은 파일의 주석 셋이 사실과 다르다. 주석은 행위를 바꾸지 않지만, **다음 사람이 그것을
읽고 판단한다.** 특히 `fresh=0` 은 실제(`fresh_ratio < 0.2`)보다 **좁게** 읽혀서,
fresh=2/25(8%) 같은 실측 결함을 「fresh 가 0이 아니니 정상」으로 오판하게 만든다.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SCHEDULER = ROOT / "src/engine/scheduler.py"

#: 새 마커 — 기존 `[cash_usage_ratio]` 와 **닫는 대괄호까지** 달라야 구분된다.
MARKER = "[cash_usage_ratio_source]"


def _src() -> str:
    return SCHEDULER.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# I — 네 경로가 각각 자기 이름을 남기는가
# ──────────────────────────────────────────────────────────────────────────


class _Regime:
    def __init__(self, computed):
        self._computed = computed

    def computed_cash_usage_ratio(self):
        return self._computed


async def _run(monkeypatch, *, auto, computed, manual=1.0, auto_raises=False):
    """`_resolve_cash_usage_ratio` 를 경로별로 태운다.

    실제 클래스를 만들지 않고 언바운드 함수를 부른다 — 이 함수는 `self` 를 쓰지 않는다.
    (쓰게 되면 이 헬퍼가 `TypeError` 로 붉어져 계약 변경을 알린다.)
    """
    from src.db import system_config as sc
    from src.engine import market_regime as mr
    from src.engine.scheduler import TradingScheduler

    async def _get_manual():
        return manual

    async def _get_auto():
        if auto_raises:
            raise RuntimeError("DB 조회 실패 (테스트)")
        return auto

    async def _set(_v):
        return None

    monkeypatch.setattr(sc, "get_auto_regime_adjust", _get_auto, raising=False)
    monkeypatch.setattr(sc, "set_cash_usage_ratio", _set, raising=False)
    monkeypatch.setattr(mr, "get_current_regime", lambda: _Regime(computed), raising=False)

    import src.engine.scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "get_cash_usage_ratio", _get_manual, raising=False)

    return await TradingScheduler._resolve_cash_usage_ratio(object())


@pytest.mark.asyncio
async def test_manual_path_when_auto_disabled_then_logs_source(monkeypatch, caplog):
    """ⓑ 자동조정이 꺼져 있으면 **수동값이 이겼다**고 남긴다.

    막는 회귀 = 이 경로의 침묵. 운영 DB 가 `auto_regime_adjust=false` 이므로
    **이 경로가 평상시 경로**다. 여기가 조용하면 평소엔 아무 근거도 안 남는다.
    """
    with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
        got = await _run(monkeypatch, auto=False, computed=0.25, manual=1.0)

    assert got == 1.0, "자동조정이 꺼졌으면 수동값이어야 한다"
    msgs = [r.getMessage() for r in caplog.records if MARKER in r.getMessage()]
    assert msgs, f"{MARKER} 가 없다 — 평상시 경로가 침묵한다"
    assert any("source=manual" in m and "reason=auto_disabled" in m for m in msgs), msgs
    assert any("applied=1.00" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_manual_path_when_regime_empty_then_logs_reason(monkeypatch, caplog):
    """ⓒ 레짐을 못 받으면 **왜** 수동값으로 갔는지 남긴다.

    막는 회귀 = ⓑ 와 ⓒ 가 같은 문장으로 찍히는 것. 둘은 운영자가 할 일이 다르다 —
    ⓑ 는 설정대로고, ⓒ 는 **매크로 수신이 끊긴 것**이라 고칠 것이 있다.
    """
    with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
        got = await _run(monkeypatch, auto=True, computed=None, manual=0.8)

    assert got == 0.8
    msgs = [r.getMessage() for r in caplog.records if MARKER in r.getMessage()]
    assert any("source=manual" in m and "reason=regime_unavailable" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_auto_path_when_computed_then_logs_both_values(monkeypatch, caplog):
    """ⓓ 계산값이 이겼으면 **버려진 수동값도 함께** 남긴다.

    🔴 이 경로가 자금을 1.00 → 0.25 로 접는 그 경로다. 수동값을 같이 적어야
    운영자가 "내가 1.00 으로 둔 것이 덮였다"를 한 줄로 안다.
    """
    with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
        got = await _run(monkeypatch, auto=True, computed=0.25, manual=1.0)

    assert got == 0.25
    msgs = [r.getMessage() for r in caplog.records if MARKER in r.getMessage()]
    assert any("source=regime" in m for m in msgs), msgs
    assert any("applied=0.25" in m and "manual=1.00" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_exception_path_still_returns_manual_and_names_itself(monkeypatch, caplog):
    """ⓐ 조회가 터져도 수동값으로 살아남고, 그 경로임을 남긴다.

    막는 회귀 = fail-open 이 조용해지는 것. cycle316 의 교훈이 그대로다 —
    **안전의 반대는 손실이 아니라 운영자가 모르는 상태**다.
    """
    with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
        got = await _run(monkeypatch, auto=True, computed=0.25, manual=1.0, auto_raises=True)

    assert got == 1.0, "조회 실패는 수동값 폴백이어야 한다"
    msgs = [r.getMessage() for r in caplog.records if MARKER in r.getMessage()]
    assert any("source=manual" in m and "reason=probe_error" in m for m in msgs), msgs


def test_marker_is_distinct_from_existing_one() -> None:
    """새 마커가 기존 `[cash_usage_ratio]` 와 **구분되는가**.

    막는 회귀 = 값 필드를 `ratio=` 로 쓰는 것. 월요일 확인 목록이
    `[cash_usage_ratio] ratio=1.00` 을 세는데, 같은 토큰이 두 줄에 생기면 숫자가 부풀려진다.
    """
    src = _src()
    assert MARKER in src, f"{MARKER} 가 scheduler.py 에 없다"
    # 새 마커 줄에 `ratio=` 를 쓰지 않는다 (`applied=` 를 쓴다).
    for line in src.splitlines():
        if MARKER in line:
            assert " ratio=" not in line, (
                f"새 마커 줄에 ` ratio=` 가 있다 — 기존 마커의 grep 을 오염시킨다: {line.strip()}"
            )


# ──────────────────────────────────────────────────────────────────────────
# J — 거짓 주석이 사라졌는가
# ──────────────────────────────────────────────────────────────────────────


def test_stale_watcher_interval_comment_says_120s() -> None:
    """K stale watcher 주기를 `30s` 로 적은 주석이 없는가.

    실제는 `STALE_WATCHER_INTERVAL_SECS = 120`(사이클 9 가 30 → 120). 같은 파일 안
    다른 다섯 곳이 이미 120s 인데 이 줄만 옛 값에 멈춰 있었다.
    """
    src = _src()
    assert "STALE_WATCHER_INTERVAL_SECS = 120" in src, "상수 자체가 바뀌었다면 이 가드부터 재검토"

    offenders = [
        ln.strip()
        for ln in src.splitlines()
        if re.search(r"K\s*\(\s*30s\s*\)|silent inactive 30s", ln)
    ]
    assert not offenders, (
        "K stale watcher 주기를 30s 로 적은 주석이 남아 있다 (실제 120s):\n  "
        + "\n  ".join(offenders)
    )


def test_safety_net_comments_say_four_not_three() -> None:
    """WebSocket 안전망을 `3중` 으로 적은 주석이 없는가.

    네 번째 `_resubscribe_stale_priority` 가 실재한다(정의 · `_scan_loop` 안에서 5분 주기 호출).
    정본 넷(루트 `CLAUDE.md` · `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` ·
    `stale_watcher_core.py`)이 전부 **4중**이라, 이 파일만 3중이면 정본이 갈라진다.
    """
    src = _src()
    assert "_resubscribe_stale_priority" in src, "네 번째 안전망이 사라졌다면 이 가드부터 재검토"

    offenders = [ln.strip() for ln in src.splitlines() if "3중 안전망" in ln]
    assert not offenders, (
        "안전망을 3중으로 적은 주석이 남아 있다 (실제 4중):\n  " + "\n  ".join(offenders)
    )


def test_silent_inactive_comment_uses_ratio_not_zero() -> None:
    """silent inactive 판정을 `fresh=0` 으로 적은 주석이 없는가.

    실제는 `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)`.
    🔴 `fresh=0` 은 실제보다 **좁게** 읽혀서, fresh=2/25(8%) 같은 실측 결함을
    「fresh 가 0이 아니니 정상」으로 오판하게 만든다 — 그 오판이 이 규칙이 생긴 이유다.

    ⚠️ **실측 기록과 판정식을 구별한다.** 같은 파일에
    `# 2026-05-20 14:58 운영 결함: 메인 세션 sub=11 ack=11 fresh=0 stale=11 대응.` 이 있는데
    그건 그날 **실제로 관측된 값**이라 사실이 맞다. 지우면 사고 기록이 사라진다.
    그래서 「판정식 모양」(다른 조건과 `+` 로 이어지고 `subscribed` 비교를 동반)만 겨냥한다.
    """
    src = _src()
    offenders = [
        ln.strip()
        for ln in src.splitlines()
        if re.search(r"fresh\s*=\s*0\b", ln)
        and re.search(r"subscribed\s*>=", ln)  # 판정식 모양: 다른 조건과 함께 나열된다
        and "ratio" not in ln
    ]
    assert not offenders, (
        "silent inactive 판정을 fresh=0 으로 적은 주석이 남아 있다 (실제 fresh_ratio < 0.2):\n  "
        + "\n  ".join(offenders)
    )
