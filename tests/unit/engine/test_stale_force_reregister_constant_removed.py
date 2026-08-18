"""2026-08-19 정리 사이클 ④ Red — `STALE_FORCE_REREGISTER_AFTER` dead 상수 제거.

배경
----
`src/engine/scheduler.py:99` 의 ``STALE_FORCE_REREGISTER_AFTER = 5`` 는 production
소비처가 0건이다. 유일한 참조는 ``tests/unit/engine/test_stale_watcher_thresholds.py``
의 ``test_stale_force_reregister_after_is_5`` 가 ``== 5`` 를 단언하는 것뿐 —
자기 자신만 지키는 순환 가드.

CLAUDE.md 금기("비활성화·dead 판정 시 심층 검증 의무") 이행
----------------------------------------------------------
이 상수가 대리하던 **사이클 17 독트린**("1~5회 재SEND 분기 폐기 —
`pool.resend_subscribe_for_ticker` 재도입 금지", KIS 공식 답변 "기등록한 사항을
재등록하지 않도록 … LMS + 앱정보 이용중지") 은 상수가 아니라 아래 **행위 가드**가
지킨다(소비처 전수 확인 결과):

- ``tests/unit/engine/test_stale_watcher_thresholds.py`` retry=1 / retry=5 / retry=6
  세 분기 모두 ``pool_mock.resend_subscribe_for_ticker.assert_not_called()``
- ``tests/integration/test_stale_watcher_pool.py`` D-1/D-3/D-4/D-6 (pool_resend_spy 0건)
- ``tests/integration/test_stale_watcher.py`` K-2/K-3/K-6 (`_send_subscribe`/재SEND 0건)
- ``tests/unit/engine/test_cycle63_phase2A3_force_resubscribe.py`` G-1/G-2
  (첫 stale·retry=5 모두 unsubscribe_in_pool + subscribe 강제 재등록 = KIS 신규 등록 패턴)

즉 상수는 **분기 임계가 아니라 주석**이고, 실제 임계는 ``MAX_STALE_RETRIES``
(``stale_watcher_core.py:272`` ``if retry > MAX_STALE_RETRIES``) 다.

다만 위 행위 가드는 전부 **`check_and_resubscribe_stale` 경로 한정 mock 단언**이라,
다른 모듈(예: `resubscribe_stale_priority`, `_scan_loop`)에서 재SEND 가 부활하면
아무도 못 잡는다. 그 사각을 메우는 소스-레벨 가드를 여기 신설한다(G-DEAD-2).

케이스
------
- G-DEAD-1 (Red): ``scheduler.STALE_FORCE_REREGISTER_AFTER`` 부재.
- G-DEAD-2 (독트린 실효 가드, 신설): production ``src/engine/`` + ``src/realtime/`` 전체에
  ``resend_subscribe_for_ticker`` **호출부 0건** (websocket_pool 의 정의 자체는 허용 —
  운영 도구 후보로 사이클 17 이 의도적으로 보존).
- G-DEAD-3: 실제 stale 임계 상수 ``MAX_STALE_RETRIES`` 는 살아 있고 소비된다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[3] / "src"


# ---------------------------------------------------------------------------
# G-DEAD-1 (Red) — dead 상수 제거
# ---------------------------------------------------------------------------
def test_stale_force_reregister_after_constant_removed():
    """`STALE_FORCE_REREGISTER_AFTER` 는 소비처 0건 dead 상수 — 제거 의무."""
    from src.engine import scheduler

    assert not hasattr(scheduler, "STALE_FORCE_REREGISTER_AFTER"), (
        "STALE_FORCE_REREGISTER_AFTER 는 production 소비처 0건(분기는 MAX_STALE_RETRIES "
        "가 담당). 사이클 17 독트린은 재SEND 행위 가드 + G-DEAD-2 소스 가드가 지킨다"
    )


# ---------------------------------------------------------------------------
# G-DEAD-2 — 사이클 17 독트린 소스 가드 (상수 제거의 전제)
# ---------------------------------------------------------------------------
def test_no_resend_subscribe_call_sites_in_production():
    """production 코드에 `resend_subscribe_for_ticker` 호출부 0건.

    KIS 공식 답변(2026-05-19): "기 요청된 목록을 관리하여 기등록한 사항을 재등록하지
    않도록 부탁드립니다. (당사 서버 부담 시 LMS + 앱정보 이용중지 처리)"
    → 같은 종목 재SEND 는 어떤 경로에서도 부활 금지. 정상 회복 패턴은
    `unsubscribe_in_pool` + `subscribe` (신규 등록).
    """
    violations: list[str] = []

    for pyfile in sorted(
        [*(_SRC / "engine").rglob("*.py"), *(_SRC / "realtime").rglob("*.py")]
    ):
        tree = ast.parse(pyfile.read_text(encoding="utf-8"), filename=str(pyfile))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            if name == "resend_subscribe_for_ticker":
                violations.append(f"{pyfile.relative_to(_SRC.parent)}:{node.lineno}")

    assert violations == [], (
        "사이클 17 독트린 위반 — `resend_subscribe_for_ticker` 재SEND 호출 부활: "
        f"{violations}. 회복은 unsubscribe_in_pool + subscribe(신규 등록) 로만."
    )


# ---------------------------------------------------------------------------
# G-DEAD-3 — 살아있는 임계는 MAX_STALE_RETRIES
# ---------------------------------------------------------------------------
def test_max_stale_retries_is_the_live_threshold():
    """`MAX_STALE_RETRIES` 는 존재하고 `stale_watcher_core` 가 실제로 소비한다."""
    from src.engine import scheduler

    assert scheduler.MAX_STALE_RETRIES == 5

    core = (_SRC / "engine" / "stale_watcher_core.py").read_text(encoding="utf-8")
    assert "retry > MAX_STALE_RETRIES" in core, (
        "stale watcher 의 실제 분기 임계는 MAX_STALE_RETRIES"
    )
