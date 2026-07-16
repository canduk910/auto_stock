"""사이클 193 (2026-07-04) Red — system_config task 마커 헬퍼 2개 신규.

`src/db/system_config.py` 에 재시작 immediate run 신선도 게이트용 task 마커 헬퍼 추가:

```python
async def get_task_last_success(task_label: str) -> str | None:
    return await _get_string_or_none(f"task_last_success_{task_label}")

async def set_task_last_success(task_label: str, iso_ts: str) -> None:
    # 키 task_last_success_<label> upsert (JSONB {"value": iso}), retry 미경유 graceful
```

계약:
- get 은 기존 `_get_string_or_none` 재사용 (사이클 189 execute_with_retry 경유 = 자동 수혜).
- set 은 기존 `_upsert` 패턴 (`asyncio.to_thread`) — **retry 미경유** (쓰기 정책 영속, 187/189).

Red 유효성 (현재 코드 = 두 헬퍼 미존재):
- F-11a/b/c: `get_task_last_success` / `set_task_last_success` AttributeError → FAIL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.db.system_config as sc

pytestmark = pytest.mark.unit


def _make_supabase(execute_side_effect):
    """체인 링크 자기 반환 + `.execute()` side_effect 부착 supabase mock (사이클 189 답습)."""
    chain = MagicMock(name="chain")
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.upsert.return_value = chain
    chain.execute.side_effect = execute_side_effect

    mock_sb = MagicMock(name="supabase")
    mock_sb.table.return_value = chain
    return mock_sb, chain


def _result(data):
    r = MagicMock(name="result")
    r.data = data
    return r


# ---------------------------------------------------------------------------
# F-11a — get_task_last_success 는 _get_string_or_none 경유 (키 유도 정합)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F11a_get_uses_get_string_or_none():
    """get_task_last_success(label) → _get_string_or_none("task_last_success_<label>").

    189 execute_with_retry 수혜 (read retry) 자동 상속 = 별도 retry 배선 불필요.
    """
    string_mock = AsyncMock(return_value="2026-07-04T16:10:00+09:00")
    with patch.object(sc, "_get_string_or_none", new=string_mock):
        val = await sc.get_task_last_success("full_universe_load")

    assert val == "2026-07-04T16:10:00+09:00", "저장된 ISO 문자열 반환 의무"
    string_mock.assert_awaited_once_with("task_last_success_full_universe_load"), (
        "_get_string_or_none 을 파생 키로 호출 의무 (189 retry 수혜)"
    )


# ---------------------------------------------------------------------------
# F-11b — get_task_last_success graceful None (키 부재)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F11b_get_returns_none_when_absent():
    """마커 키 부재 → None graceful (_get_string_or_none None 그대로 전파)."""
    string_mock = AsyncMock(return_value=None)
    with patch.object(sc, "_get_string_or_none", new=string_mock):
        val = await sc.get_task_last_success("stock_master_master_load")

    assert val is None, "키 부재 → None 반환 의무 (최초 배포/DB 초기화 안전)"
    string_mock.assert_awaited_once_with("task_last_success_stock_master_master_load")


# ---------------------------------------------------------------------------
# F-11c — set_task_last_success 는 upsert 패턴 + retry 미경유 (쓰기 정책 영속)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F11c_set_upserts_without_retry():
    """set_task_last_success(label, iso) → upsert(key=task_last_success_<label>,
    value={"value": iso}) + retry 미경유 (쓰기 = 멱등 우려, 187/189 영속).

    사이클 M2a (2026-07-16) 의미 전환 — system_config 가 supabase-py → src.db.pg
    전환. upsert 는 `pg.execute` 직접 호출(INSERT ... ON CONFLICT (key) DO UPDATE)로
    바뀌어 supabase 체인(`chain.upsert`) mock 이 무효 → `pg.execute` 인자 캡처로 대체.
    """
    iso = "2026-07-04T16:10:00+09:00"

    execute_calls: list[tuple] = []

    async def _fake_execute(sql, *args):
        execute_calls.append((sql, args))
        return "INSERT 0 1"

    with patch.object(sc, "pg", create=True) as pg_mock:
        pg_mock.execute = _fake_execute
        await sc.set_task_last_success("stock_master_daily_load", iso)

    # upsert payload 검증 — pg.execute(sql, key, value_dict, updated_at_datetime)
    assert len(execute_calls) == 1, "execute(upsert) 1회 호출 의무"
    sql, args = execute_calls[0]
    assert "ON CONFLICT (key)" in sql, "key PK upsert SQL 의무"
    assert args[0] == "task_last_success_stock_master_daily_load", "파생 키 upsert 의무"
    assert args[1] == {"value": iso}, "JSONB {'value': iso} 형태 저장 의무"

    # 쓰기 retry 미경유 (execute 1회, 재시도 없음)
    assert len(execute_calls) == 1, "쓰기 = 재시도 0 (execute 1회)"
