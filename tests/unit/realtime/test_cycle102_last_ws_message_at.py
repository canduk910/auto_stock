"""사이클 102 영역 2-A — `_last_ws_message_at` 세션별 가시화 신규 (Red).

G-WS-MSG1 + G-WS-MSG2 — `KisWebSocket.__init__` 영역 인스턴스 변수 신규 +
`_handle_raw` 진입 시 update 영속 검증.

영역 2-A = 외부 의견 보조 가시화 영역 (사이클 88 G-REJECT-2 종목별 영속 ↔ 세션별
보조 가시화 *책임 분리* 영속).

Red: production 영역 부재 → 2 케이스 모두 FAIL.
Green: backend-dev 시정 후 2 PASS.

영속 의무:
- 사이클 88 G-REJECT-2 영속 (종목별 `ticker_last_tick` 14 사이트 영속)
- 사이클 16 `_aes_iv` 인스턴스 변수 패턴 답습
- 사이클 68 KST 일관성 영속 (`datetime.now(KST_TZ)` 사용)
- 매매 안전성 영향 0 (가시화 영역 한정)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.realtime.websocket import KisWebSocket


pytestmark = pytest.mark.unit


KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# G-WS-MSG2 — `__init__` 인스턴스 변수 신규 (격리 + 초기 = {})
# ---------------------------------------------------------------------------
def test_g_ws_msg2_init_last_ws_message_at_empty_dict():
    """G-WS-MSG2 (MEDIUM): `KisWebSocket.__init__` 영역 `_last_ws_message_at` 인스턴스
    변수 신규 + 초기 = {} (인스턴스 격리, 사이클 16 `_aes_iv` 패턴 답습).

    Red: production 미시정 → FAIL (AttributeError).
    Green: backend-dev `__init__` 영역 + `self._last_ws_message_at = {}` 추가 → PASS.

    검증 매트릭스:
    - 인스턴스 변수 존재 영속 (`hasattr`)
    - 초기 = dict 타입 영속
    - 초기 = empty dict 영속
    - 메인 + 보조 2 인스턴스 격리 영속 (각각 별도 dict)
    """
    main_ws = KisWebSocket(is_main=True, label="main")
    quote_ws = KisWebSocket(
        token_manager=MagicMock(), is_main=False, label="quote-1",
    )

    # 인스턴스 변수 존재 영속
    assert hasattr(main_ws, "_last_ws_message_at"), (
        "G-WS-MSG2 위반 — `KisWebSocket.__init__` 영역 `_last_ws_message_at` 신규 "
        "인스턴스 변수 부재 (사이클 88 G-REJECT-2 책임 분리 영역 침범).\n"
        "  시정: `KisWebSocket.__init__` 영역에\n"
        "  `self._last_ws_message_at: dict[str, datetime] = {}` 추가 (사이클 16 _aes_iv 패턴 답습)."
    )
    assert hasattr(quote_ws, "_last_ws_message_at"), (
        "G-WS-MSG2 위반 — 보조 세션 `_last_ws_message_at` 인스턴스 변수 부재"
    )

    # 타입 + 초기 값 영속
    assert isinstance(main_ws._last_ws_message_at, dict), (
        f"G-WS-MSG2 위반 — `_last_ws_message_at` 타입 결함: "
        f"{type(main_ws._last_ws_message_at).__name__} (dict 영속)"
    )
    assert main_ws._last_ws_message_at == {}, (
        f"G-WS-MSG2 위반 — `_last_ws_message_at` 초기 = empty dict 영속 침범: "
        f"{main_ws._last_ws_message_at}"
    )

    # 인스턴스 격리 영속 (메인 + 보조 별도 dict)
    assert main_ws._last_ws_message_at is not quote_ws._last_ws_message_at, (
        "G-WS-MSG2 위반 — 메인 + 보조 `_last_ws_message_at` 인스턴스 격리 영속 결함 "
        "(공유 dict = silent 결함 위험)"
    )


# ---------------------------------------------------------------------------
# G-WS-MSG1 — `_handle_raw` 진입 시 update 영속 (KST datetime)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_ws_msg1_handle_raw_updates_last_ws_message_at():
    """G-WS-MSG1 (HIGH): `_handle_raw` 진입 시 `self._last_ws_message_at[self.label]`
    KST datetime update 영속 (사이클 68 KST 일관성 영속).

    Red: production 미시정 → 진입 시 update 영역 부재 → FAIL.
    Green: backend-dev `_handle_raw` 진입 부에
      `self._last_ws_message_at[self.label] = datetime.now(KST_TZ)` 추가 → PASS.

    검증 매트릭스:
    - `_handle_raw` 호출 *후* `_last_ws_message_at[label]` 갱신 영속
    - 값 = `datetime` 타입 + KST timezone (`+09:00`) 영속
    - 다중 호출 시 마지막 호출 시점 영속 (덮어쓰기 영속)
    """
    main_ws = KisWebSocket(is_main=True, label="main")

    # 사전 조건: 초기 empty dict
    assert main_ws._last_ws_message_at == {}, "사전조건 침범"

    # Act — `_handle_raw` 호출 (시세 payload 1건)
    sample_raw_msg = "0|H0STCNT0|001|005930^140000^70000^5^500^0.7"
    before = datetime.now(KST)
    await main_ws._handle_raw(sample_raw_msg)
    after = datetime.now(KST)

    # Assert — `_last_ws_message_at["main"]` 갱신 영속
    assert "main" in main_ws._last_ws_message_at, (
        f"G-WS-MSG1 위반 — `_handle_raw` 진입 시 `_last_ws_message_at[label]` update 영역 "
        f"부재 (실측 keys = {list(main_ws._last_ws_message_at.keys())}):\n"
        f"  시정: `_handle_raw` 진입 부 (L601 영역) 에\n"
        f"  `self._last_ws_message_at[self.label] = datetime.now(KST_TZ)` 추가\n"
        f"  (사이클 68 KST 일관성 영속 + 사이클 88 G-REJECT-2 책임 분리 영역)."
    )
    recorded = main_ws._last_ws_message_at["main"]
    assert isinstance(recorded, datetime), (
        f"G-WS-MSG1 위반 — `_last_ws_message_at[label]` 값 타입 결함: "
        f"{type(recorded).__name__} (datetime 영속)"
    )
    assert recorded.tzinfo is not None, (
        f"G-WS-MSG1 위반 — `_last_ws_message_at[label]` timezone-aware 영속 결함 "
        f"(사이클 68 KST 영속 영역 침범): {recorded}"
    )
    # KST timezone 영속 (UTC offset +9h)
    utcoffset = recorded.utcoffset()
    assert utcoffset is not None and utcoffset.total_seconds() == 9 * 3600, (
        f"G-WS-MSG1 위반 — `_last_ws_message_at[label]` KST timezone 영속 결함 "
        f"(사이클 68 영속 영역 침범): {recorded} offset={utcoffset}"
    )
    # 호출 시점 일관성 영속
    assert before <= recorded <= after, (
        f"G-WS-MSG1 위반 — `_last_ws_message_at[label]` 호출 시점 영속 결함: "
        f"before={before} recorded={recorded} after={after}"
    )
