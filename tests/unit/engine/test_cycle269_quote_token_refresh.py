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
      (immediate_first_run=False · wait_time=19:00(cycle270-C; 이력 15:45→21:30 무발화→19:00) · once_callable 동일성).
- C9  시각 불변식 — T 와 T−10분(자연 재발급 문턱)이 **모두** KRX 마감 이후,
      그리고 20:00~20:15(자문/정산 금기 창) 밖.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# cycle296 — 회차 요약이 3키 → 5키(`elapsed_s`·`window_issues_total`)로 늘었다.
# 등식 단언을 5키로 통째로 옮기면 실행 시간 의존(`elapsed_s`)이 들어오므로, 핵심 3키만
# 등식으로 재고 관측 2키는 성질로 잰다.
_SUMMARY_KEYS_296 = ("accounts", "issued", "failed", "elapsed_s", "window_issues_total")


def _core(summary: dict) -> dict:
    """cycle296 관측 2키를 검사한 뒤 떼어 내고 핵심 3키만 돌려준다.

    - `elapsed_s` — `%d` 포맷이라 **정수**여야 하고 음수일 수 없다.
    - `window_issues_total` — 이 파일의 더블(`_DummyMgr`)은 `issue_history` 가 없다.
      관측 배관이 더블에 대해 never-raise 인지(폴백 `getattr(..., ())`)의 증거다.
    """
    assert set(summary) == set(_SUMMARY_KEYS_296), (
        f"cycle296 회차 요약은 5키다 — 실측 {sorted(summary)}"
    )
    assert isinstance(summary["elapsed_s"], int) and not isinstance(
        summary["elapsed_s"], bool
    ), f"elapsed_s 타입 실측 {type(summary['elapsed_s'])}"
    assert summary["elapsed_s"] >= 0
    assert summary["window_issues_total"] == 0, (
        "`issue_history` 없는 더블인데 창 집계가 0 이 아니다 — 폴백이 깨졌다"
    )
    return {k: summary[k] for k in ("accounts", "issued", "failed")}


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
    assert _core(summary) == {"accounts": 3, "issued": 3, "failed": 0}


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
    assert _core(summary) == {"accounts": 3, "issued": 2, "failed": 1}


@pytest.mark.asyncio
async def test_c4_single_account_failure_absorbed(monkeypatch):
    """C4 — 중간 계정 실패가 뒤 계정 발급을 막지 않는다."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    issue_calls, _, _ = _install(monkeypatch, accounts, fail_labels=("gold",))

    summary = await mod.refresh_quote_tokens_once()

    assert issue_calls == ["fire", "isa"]
    assert _core(summary) == {"accounts": 3, "issued": 2, "failed": 1}


@pytest.mark.asyncio
async def test_c5_list_accounts_failure_skips_round(monkeypatch):
    """C5 — 계정 목록 조회 실패는 예외를 전파하지 않고 그 회차만 skip 한다."""
    from src.engine import quote_token_refresh as mod

    issue_calls, _, _ = _install(monkeypatch, [], list_raises=True)

    summary = await mod.refresh_quote_tokens_once()

    assert _core(summary) == {"accounts": 0, "issued": 0, "failed": 0}
    assert issue_calls == []


@pytest.mark.asyncio
async def test_c6_empty_account_list_issues_nothing(monkeypatch):
    """C6 — 활성 보조 계정이 없으면 발급 0회."""
    from src.engine import quote_token_refresh as mod

    issue_calls, _, manager_labels = _install(monkeypatch, [])

    summary = await mod.refresh_quote_tokens_once()

    assert _core(summary) == {"accounts": 0, "issued": 0, "failed": 0}
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
    assert _core(summary) == {"accounts": 2, "issued": 2, "failed": 0}
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

    assert captured["wait_time"] == mod.TIME_QUOTE_TOKEN_REFRESH == time(20, 45)
    assert captured["once_callable"] is mod.refresh_quote_tokens_once
    assert captured["immediate_first_run"] is False, (
        "부팅 즉시 실행하면 부팅 시각이 새 앵커가 되어 '고정 장외 시각' 설계가 무너진다"
    )
    assert captured["task_label"] == "quote_token_refresh"
    assert captured["summary_keys"] == _SUMMARY_KEYS_296
    assert captured["summary_log_format"].startswith("[quote_token_refresh]")
    # metrics collector 가 없는 task — no-op 이어야 하고 예외를 내면 안 된다
    assert captured["record_fn"]({"accounts": 1}) is None
    assert captured["flush_fn"]() is None


def test_c9_schedule_time_invariants():
    """C9 — T 와 자연 재발급 문턱(T−10분)이 **모두** 조용한 창이어야 한다.

    🔁 **cycle296 재표현 (2026-09-17) — 19:00 이 왜 틀렸나.**
    종전 이 단언은 "문턱이 KRX 마감(15:30) 뒤인가" 만 물었다. 그건 **필요조건이었지
    충분조건이 아니었다** — 보조 시세 계정은 장외에도 종일 REST 를 쓴다(5분 주기 stale
    가드 · 15:40 NXT 애프터 등). 그래서 19:00 앵커의 다음 날 문턱 18:50 창에 `get_token()`
    이 들어와 자연 재발급이 **항상 강제보다 먼저** 났다(09-16 실측 7/7 산술 일치 — ISA
    문턱 18:51:25 → 실발화 18:55:03). 하루 발급이 설계 7건 대신 14~21건이었다.

    ⇒ T−10 창의 요건은 "장외" 가 아니라 **"보조 풀 REST 가 없는 창"** 이다. 09-16 실측:
    20:2x~21:0x 보조 풀 REST 14행 균일(5분 주기 로그뿐) · `quote_pool` 마커 0건 ·
    20:30 일봉 적재는 20:31:50 종료(메인 계정). ⇒ 20:35~20:55 가 비어 있다.

    새 단언 (iv)(v) 가 M9/M10 뮤테이션을 잡는다:
    - (iv) `T + 15분 ≤ TIME_SETTLEMENT` — 체인이 09-15 처럼 14분 40초로 밀려도 정산 전 종료
    - (v)  `T − 10분 ≥ 일봉 적재 + 5분` — **19:00 으로 되돌리는 뮤테이션이 여기서 죽는다**
      (18:50 < 20:35). 문턱이 일봉 적재가 끝난 뒤에 와야 그 창이 조용하다.

    **삭제**: `(T + 8분) < TIME_RECOMMENDATION`. 그 단언의 의도("20:00 REST 집중 창
    침범 금지")를 **정확히** 재는 것은 아래 `collisions` 전수 스캔이고, 부등식은 "T 가
    20:00 앞" 을 강제하던 프록시였다 — 20:00 블록이 끝난 **뒤**의 시각도 기각한다.

    확정값 자체의 핀은 `test_cycle296_quote_token_refresh_observe.py::test_l0` 가 든다.
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T
    from src.engine.scheduler import (
        TIME_KRX_MAIN_CLOSE,
        TIME_SETTLEMENT,
        TIME_STOCK_MASTER_DAILY_LOAD,
    )

    base = datetime(2026, 9, 17)
    t_dt = base.replace(hour=T.hour, minute=T.minute)
    threshold = t_dt - timedelta(minutes=10)
    close_dt = base.replace(
        hour=TIME_KRX_MAIN_CLOSE.hour, minute=TIME_KRX_MAIN_CLOSE.minute
    )

    # (i)(ii) — 장중 침범 0 (종전 계약 유지)
    assert t_dt > close_dt, "강제 재발급 자체가 장중이면 요구 위반"
    assert threshold > close_dt, (
        f"T−10분 문턱({threshold.time()})이 KRX 마감 이전이면 자연 재발급이 장중에 난다"
    )

    # (iii) — 루프 생존 창 (cycle270-C: start() 의 finally 가 정산 뒤 task 를 cancel 한다)
    assert T < TIME_SETTLEMENT, "루프 사망(정산) 뒤 시각은 매일 0회 발화한다"

    # (iv) — 체인 지연 마진. 09-15 실측 최악 14분 40초.
    assert (t_dt + timedelta(minutes=15)).time() <= TIME_SETTLEMENT, (
        f"T({T}) + 15분이 정산({TIME_SETTLEMENT})을 넘는다 — 체인이 밀리면 도중에 cancel 된다"
    )

    # (v) — 문턱이 일봉 적재가 끝난 뒤에 온다(= 문턱 창이 조용하다는 구조적 근거).
    load_end = base.replace(
        hour=TIME_STOCK_MASTER_DAILY_LOAD.hour,
        minute=TIME_STOCK_MASTER_DAILY_LOAD.minute,
    ) + timedelta(minutes=5)
    assert threshold >= load_end, (
        f"자연 재발급 문턱({threshold.time()})이 일봉 적재 종료 추정({load_end.time()}) "
        "이전이다 — 그 창에 REST 가 있으면 자연 재발급이 강제보다 먼저 나서 하루 "
        "발급이 두 배가 된다(19:00 이 정확히 이 이유로 실패했다)"
    )

    # (vi) — 직렬화 창 [T−10, T+8] 전수 충돌 스캔 (T 를 옮기는 사이클은 이 창을 다시 계산한다)
    import src.engine.scheduler as _sched
    window_lo, window_hi = threshold.time(), (t_dt + timedelta(minutes=8)).time()
    collisions = sorted(
        name for name, val in vars(_sched).items()
        if name.startswith("TIME_") and isinstance(val, time) and window_lo <= val <= window_hi
    )
    assert collisions == [], f"강제 재발급 창 {window_lo}~{window_hi} 와 겹치는 예정 작업: {collisions}"

    # 양성 대조군 — 창 검사가 공허하지 않다(스캔 대상이 실제로 존재한다).
    all_times = [
        v for n, v in vars(_sched).items()
        if n.startswith("TIME_") and isinstance(v, time)
    ]
    assert len(all_times) >= 20, (
        f"`vars(scheduler)` 의 TIME_* 가 {len(all_times)}개뿐 — 충돌 스캔이 공허하다"
    )

    assert TIME_STOCK_MASTER_DAILY_LOAD not in (
        v for n, v in vars(_sched).items()
        if n.startswith("TIME_") and isinstance(v, time) and window_lo <= v <= window_hi
    ), "일봉 적재가 강제 재발급 직렬화 창 안이다 — 두 KIS 집중 작업이 겹친다"

    # (vii) — 두 KIS 집중 작업의 간격. cycle296 에서 10분 → **15분**(적재 실측 ~121초 +
    # 마진, 그리고 (v) 의 5분 여유와 정합).
    _load_min = (
        TIME_STOCK_MASTER_DAILY_LOAD.hour * 60 + TIME_STOCK_MASTER_DAILY_LOAD.minute
    )
    _t_min = t_dt.hour * 60 + t_dt.minute
    assert abs(_load_min - _t_min) >= 15, (
        f"토큰 강제 재발급(T={T})과 일봉 적재({TIME_STOCK_MASTER_DAILY_LOAD})가 "
        f"15분 이내다 — 어느 쪽이 앞이든 KIS 호출이 겹친다"
    )


def test_c10_periodic_wait_times_must_be_inside_the_loop_lifetime():
    """C10(영속 가드, cycle270-C) — 주기 루프 `wait_time` 은 전부 `TIME_SETTLEMENT` 이전.

    `run_periodic_task_loop` 는 `while scheduler._running` 안에서 잠들고, `start()` 의
    finally 가 20:10 정산 뒤 task 를 cancel 한다. 그 뒤 시각은 매일 0회 발화한다.
    이 계열("루프 밖 시각")은 일봉 적재 23:00/05:00 안이 같은 이유로 기각됐고,
    cycle270-B(21:30)가 두 번째 재발이었다 — 세 번째를 막는다.

    🔁 cycle283 주의 — `TIME_SETTLEMENT` 이 20:10 → **21:30** 으로 옮겨지면서 이 상한이
    90분 늘었다. **상한이 늘어난 것은 정산 시각 자체가 옮겨졌기 때문이지, "루프 밖
    시각을 다시 제안해도 된다" 는 뜻이 아니다.** 이 가드가 재는 것은 절대 시각이 아니라
    **`TIME_SETTLEMENT` 과의 상대 관계**이고, 그 관계는 불변이다 — `run_daily` 의
    finally 가 정산 직후 모든 주기 task 를 cancel 한다는 구조가 그대로이기 때문이다.
    (아이러니하게도 cycle270-B 가 기각당한 그 값 21:30 이 이제 정산 시각이다. 그때
    21:30 이 죽었던 이유는 "21:30 이라서" 가 아니라 "정산 뒤라서" 였다.)
    """
    from src.engine import scheduler as sched
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH

    periodic = {
        "TIME_STOCK_MASTER_DAILY_LOAD": sched.TIME_STOCK_MASTER_DAILY_LOAD,
        "TIME_STOCK_MASTER_BASICS_REFRESH": sched.TIME_STOCK_MASTER_BASICS_REFRESH,
        "TIME_STOCK_MASTER_MASTER_LOAD": sched.TIME_STOCK_MASTER_MASTER_LOAD,
        "TIME_STOCK_MASTER_FINANCIAL_LOAD": sched.TIME_STOCK_MASTER_FINANCIAL_LOAD,
        "TIME_STOCK_MASTER_DAILY_PURGE": sched.TIME_STOCK_MASTER_DAILY_PURGE,
        "TIME_FULL_UNIVERSE_LOAD": sched.TIME_FULL_UNIVERSE_LOAD,
        "TIME_QUOTE_TOKEN_REFRESH": TIME_QUOTE_TOKEN_REFRESH,
    }
    dead = {k: v for k, v in periodic.items() if v >= sched.TIME_SETTLEMENT}
    assert not dead, f"루프 사망({sched.TIME_SETTLEMENT}) 뒤 시각 — 매일 0회 발화한다: {dead}"
