"""cycle269 — 보조 시세 계정 토큰 장 마감 후 강제 재발급 leaf 회귀 가드.

정본 = `src/engine/quote_token_refresh.py` 모듈 docstring.

무엇을 잠그는가:
- C1  활성 보조 계정 전부에 `issue()` 가 (순서대로) 불린다.
- C2  `get_token()` 은 쓰지 않는다 — 캐시 hit 면 재발급하지 않아 앵커를 옮기지
      못한다(이 사이클의 목적 자체가 앵커 이동이다).
      ⚠️ **cycle270 의미 전환 (2026-09-10)**: `issue()` **단독**으로도 앵커가
      옮겨진다는 cycle269 의 전제는 09-10 실측으로 반증됐다 — KIS `/oauth2/tokenP`
      는 유효 토큰이 있으면 같은 토큰·같은 만료를 돌려준다. 계약은
      `revoke()` → `issue()` 로 전환됐고(`tests/unit/engine/`
      `test_cycle270_quote_token_revoke_then_issue.py` 가 정본), 이 파일이 잠그는
      것은 그중 **`get_token()` 금지** 부분이다.
- C3  주계정(`label=None`, 매매용)은 대상이 아니다.
- C4  계정 1건 실패는 흡수되고 나머지가 계속 발급된다.
- C5  계정 목록 조회 실패 = 그 회차 skip (예외 미전파, 전부 0 요약).
- C6  활성 계정 0건 = 발급 0회.
- C7  계정별 로그 emit 실패가 발급 cascade 를 끊지 않는다.
- C8  `task_loop` 는 `run_periodic_task_loop` 에 정확한 계약으로 위임한다
      (immediate_first_run=False · wait_time=21:30(cycle270-B, 종전 15:45) · once_callable 동일성).
- C9  시각 불변식 — T 와 T−10분(자연 재발급 문턱)이 **모두** KRX 마감 이후,
      그리고 20:00~20:15(자문/정산 금기 창) 밖.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_account(label: str):
    from src.models.kis_quote_account import KisQuoteAccount

    return KisQuoteAccount(
        id=uuid4(),
        label=label,
        app_key="key-" + label,
        app_secret_masked="****abcd",
        kis_env="vts",
        active=True,
        created_at=datetime.now(),
        updated_at=None,
    )


class _DummyMgr:
    """`issue()` / `get_token()` 호출을 각각 따로 센다.

    cycle270 의미 전환 — `revoke()` 를 더블에 추가한다. 본체가 폐기 후 발급으로
    바뀌어도 이 파일의 계약(대상 계정 · 예외 흡수 · 위임)은 그대로 성립해야 하며,
    더블에 메서드가 없으면 `AttributeError` 가 계정 단위 except 에 먹혀 모든 케이스가
    `failed` 로 뒤집힌다. 폐기 자체의 **행위 계약**은 cycle270 파일이 잠근다.
    """

    def __init__(self, label, issue_calls, get_token_calls, fail: bool = False):
        self._label = label
        self._issue_calls = issue_calls
        self._get_token_calls = get_token_calls
        self._fail = fail
        self.revoke_calls: list[str] = []
        self.token_expired = datetime(2026, 9, 9, 15, 45, 0)

    async def revoke(self) -> None:
        self.revoke_calls.append(self._label)

    async def issue(self) -> None:
        if self._fail:
            raise RuntimeError("KIS 500")
        self._issue_calls.append(self._label)

    async def get_token(self) -> str:
        self._get_token_calls.append(self._label)
        return "TOK"


def _install(monkeypatch, accounts, *, fail_labels=(), list_raises=False):
    """`list_accounts` + `get_token_manager` 를 갈아끼우고 호출 기록을 돌려준다."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    issue_calls: list[str] = []
    get_token_calls: list[str] = []
    manager_labels: list = []

    async def fake_list_accounts(active_only=False):
        if list_raises:
            raise RuntimeError("DB down")
        assert active_only is True, "활성 계정만 대상이어야 한다"
        return accounts

    async def fake_get_token_manager(label=None):
        manager_labels.append(label)
        return _DummyMgr(label, issue_calls, get_token_calls, fail=label in fail_labels)

    monkeypatch.setattr(kqa, "list_accounts", fake_list_accounts, raising=False)
    monkeypatch.setattr(
        token_mod, "get_token_manager", fake_get_token_manager, raising=False
    )
    return issue_calls, get_token_calls, manager_labels


@pytest.mark.asyncio
async def test_c1_issues_all_active_quote_accounts_in_order(monkeypatch):
    """C1 — 활성 보조 계정 전부가 순서대로 강제 재발급된다."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    issue_calls, _, _ = _install(monkeypatch, accounts)

    summary = await mod.refresh_quote_tokens_once()

    assert issue_calls == ["fire", "gold", "isa"]
    assert summary == {"accounts": 3, "issued": 3, "failed": 0}


@pytest.mark.asyncio
async def test_c2_uses_issue_not_get_token(monkeypatch):
    """C2 — `get_token()` 은 캐시 hit 면 no-op 이라 앵커를 못 옮긴다. 0회여야 한다.

    cycle270 이후에도 이 계약은 불변이다(발급 앞에 `revoke()` 가 붙었을 뿐).
    """
    from src.engine import quote_token_refresh as mod

    issue_calls, get_token_calls, _ = _install(
        monkeypatch, [_make_account("fire"), _make_account("gold")]
    )

    await mod.refresh_quote_tokens_once()

    assert issue_calls == ["fire", "gold"]
    assert get_token_calls == [], (
        "`get_token()` 은 유효 토큰이면 재발급을 건너뛴다 — 강제 앵커 이동에 쓸 수 없다"
    )


@pytest.mark.asyncio
async def test_c3_main_trading_account_is_never_touched(monkeypatch):
    """C3 — 주계정(label=None)은 대상이 아니다(매매용 · D6 로 이미 안전)."""
    from src.engine import quote_token_refresh as mod

    _, _, manager_labels = _install(
        monkeypatch, [_make_account("fire"), _make_account("gold")]
    )

    await mod.refresh_quote_tokens_once()

    assert None not in manager_labels
    assert manager_labels == ["fire", "gold"]


@pytest.mark.asyncio
async def test_c3b_blank_label_is_skipped_not_resolved_to_main(monkeypatch):
    """C3-b — label 이 비어 오면 `get_token_manager(None)` = **주계정**이 된다.

    코드 레벨에서 막는다(스키마상 NOT NULL 이지만 조회 계층이 바뀔 수 있고, 이
    한 줄이 뚫리면 매매용 토큰이 장 마감 후 재발급된다).
    """
    from src.engine import quote_token_refresh as mod

    blank = _make_account("gold")
    object.__setattr__(blank, "label", "")
    issue_calls, _, manager_labels = _install(
        monkeypatch, [_make_account("fire"), blank, _make_account("isa")]
    )

    summary = await mod.refresh_quote_tokens_once()

    assert manager_labels == ["fire", "isa"], "빈 label 은 매니저 조회조차 하지 않는다"
    assert issue_calls == ["fire", "isa"]
    assert summary == {"accounts": 3, "issued": 2, "failed": 1}


@pytest.mark.asyncio
async def test_c4_single_account_failure_absorbed(monkeypatch):
    """C4 — 중간 계정 실패가 뒤 계정 발급을 막지 않는다."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    issue_calls, _, _ = _install(monkeypatch, accounts, fail_labels=("gold",))

    summary = await mod.refresh_quote_tokens_once()

    assert issue_calls == ["fire", "isa"]
    assert summary == {"accounts": 3, "issued": 2, "failed": 1}


@pytest.mark.asyncio
async def test_c5_list_accounts_failure_skips_round(monkeypatch):
    """C5 — 계정 목록 조회 실패는 예외를 전파하지 않고 그 회차만 skip 한다."""
    from src.engine import quote_token_refresh as mod

    issue_calls, _, _ = _install(monkeypatch, [], list_raises=True)

    summary = await mod.refresh_quote_tokens_once()

    assert summary == {"accounts": 0, "issued": 0, "failed": 0}
    assert issue_calls == []


@pytest.mark.asyncio
async def test_c6_empty_account_list_issues_nothing(monkeypatch):
    """C6 — 활성 보조 계정이 없으면 발급 0회."""
    from src.engine import quote_token_refresh as mod

    issue_calls, _, manager_labels = _install(monkeypatch, [])

    summary = await mod.refresh_quote_tokens_once()

    assert summary == {"accounts": 0, "issued": 0, "failed": 0}
    assert issue_calls == [] and manager_labels == []


@pytest.mark.asyncio
async def test_c7_emit_failure_does_not_break_cascade(monkeypatch):
    """C7 — 관측 emit 이 죽어도 발급은 끝까지 간다(관측 실패 ≠ 운영 중단)."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold")]
    issue_calls, _, _ = _install(monkeypatch, accounts)

    boom_calls = {"n": 0}

    class _BoomLogger:
        def info(self, *a, **k):
            boom_calls["n"] += 1
            raise RuntimeError("logging broken")

        def exception(self, *a, **k):
            pass

        def debug(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

    monkeypatch.setattr(mod, "logger", _BoomLogger(), raising=False)

    summary = await mod.refresh_quote_tokens_once()

    assert issue_calls == ["fire", "gold"]
    assert summary == {"accounts": 2, "issued": 2, "failed": 0}
    assert boom_calls["n"] >= 2


@pytest.mark.asyncio
async def test_c8_task_loop_delegates_with_expected_contract(monkeypatch):
    """C8 — `task_loop` 가 `run_periodic_task_loop` 에 넘기는 계약을 잠근다."""
    from src.engine import quote_token_refresh as mod

    captured: dict = {}

    async def fake_loop(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(mod, "run_periodic_task_loop", fake_loop, raising=True)

    class _Sched:
        _running = True

    await mod.task_loop(_Sched())

    assert captured["wait_time"] == mod.TIME_QUOTE_TOKEN_REFRESH == time(21, 30)
    assert captured["once_callable"] is mod.refresh_quote_tokens_once
    assert captured["immediate_first_run"] is False, (
        "부팅 즉시 실행하면 부팅 시각이 새 앵커가 되어 '고정 장외 시각' 설계가 무너진다"
    )
    assert captured["task_label"] == "quote_token_refresh"
    assert captured["summary_keys"] == ("accounts", "issued", "failed")
    assert captured["summary_log_format"].startswith("[quote_token_refresh]")
    # metrics collector 가 없는 task — no-op 이어야 하고 예외를 내면 안 된다
    assert captured["record_fn"]({"accounts": 1}) is None
    assert captured["flush_fn"]() is None


def test_c9_schedule_time_invariants():
    """C9 — T 와 자연 재발급 문턱(T−10분)이 **모두** 장외여야 한다.

    `TokenManager._is_valid()` 의 선제 갱신 마진이 10분이므로 정상 상태의 자연
    재발급 문턱은 T−10분에 온다. 사용자의 요구("장마감 후에 받았으면")를 지키려면
    그 문턱도 KRX 마감(15:30) 뒤여야 한다 — 팀장 제안 15:35 는 문턱이 15:25 =
    장중이라 이 단언에 걸린다.
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T
    from src.engine.scheduler import (
        TIME_KRX_MAIN_CLOSE,
        TIME_RECOMMENDATION,
        TIME_SETTLEMENT,
        TIME_STOCK_MASTER_DAILY_LOAD,
    )

    base = datetime(2026, 9, 8)
    t_dt = base.replace(hour=T.hour, minute=T.minute)
    threshold = t_dt - timedelta(minutes=10)
    close_dt = base.replace(
        hour=TIME_KRX_MAIN_CLOSE.hour, minute=TIME_KRX_MAIN_CLOSE.minute
    )

    assert t_dt > close_dt, "강제 재발급 자체가 장중이면 요구 위반"
    assert threshold > close_dt, (
        f"T−10분 문턱({threshold.time()})이 KRX 마감 이전이면 자연 재발급이 장중에 난다"
    )
    # cycle270-B(2026-09-10 사용자 결정 15:45 → 21:30): 16:00 적재 앞에 끝내야 한다는
    # 종전 제약은 소멸. 대신 T−10분 문턱 ~ T+8분(7계정 × 61초 직렬화) 창이
    # 20:00 자문 / 20:00:05 유니버스 / 20:10 정산 창(CLAUDE.md 금기 20:00~20:15)
    # 과 그 밖의 scheduler 예정 시각 어느 것과도 겹치지 않아야 한다.
    assert not (TIME_RECOMMENDATION <= T <= time(TIME_SETTLEMENT.hour, 15))
    assert threshold.time() > time(TIME_SETTLEMENT.hour, 15), (
        "문턱이 20:00~20:15 안이면 자연 재발급이 자문·정산의 REST 와 다툰다"
    )
    import src.engine.scheduler as _sched
    window_lo, window_hi = threshold.time(), (t_dt + timedelta(minutes=8)).time()
    collisions = sorted(
        name for name, val in vars(_sched).items()
        if name.startswith("TIME_") and isinstance(val, time) and window_lo <= val <= window_hi
    )
    assert collisions == [], f"강제 재발급 창 {window_lo}~{window_hi} 와 겹치는 예정 작업: {collisions}"
    assert TIME_STOCK_MASTER_DAILY_LOAD < T, "일봉 적재보다 뒤여야 16:00 적재를 침범하지 않는다"
