"""cycle296 — 강제 재발급 T=20:45 + 회차 요약 관측 2키(`elapsed_s`/`window_issues_total`) RED.

정본 = `_workspace/red/cycle296_token_refresh_coalesce_spec.md` §3-2 / §3-3 / §5-3.

## 왜 관측을 늘리나

지금 요약은 `accounts=7 issued=7 failed=0` 이다. **참이면서** 09-15 의 실제 21건,
09-16 의 14건을 전혀 드러내지 못했다 — 강제 발급만 세기 때문이다. 합류가 배포된
뒤에도 같은 눈이면 "정말 줄었는지" 를 로그로 못 읽는다.

- `elapsed_s` — 체인 총 소요(7계정 × 61s ≈ 420s 가 정상, 09-15 실측 14분 40초까지 밀린 적 있다)
- `window_issues_total` — 체인 시작 **−15분**부터 종료까지 그 라벨들에 실제로 나간
  **모든** 발급 수. 강제분(7)과 자연 문턱분이 합산되므로 `issued` 와 갈리면 그 즉시
  "문턱 창이 조용하지 않다"(R6) 또는 "합류 미작동" 이 드러난다.

성공 서명 = `issued=7 window_issues_total=7 elapsed_s≈420`.
🔴 **첫 실행일 예외** — T 를 옮긴 첫날은 전날 앵커(19:0x)의 자연 문턱 18:5x 에 7건이
먼저 나고 20:45 강제 7건이 또 난다 ⇒ 하루 총 발급 **14건**. 단 창이 [T−15분, 종료]
라 `window_issues_total` 은 그날도 **7** 이다(18:5x 는 창 밖). 결함이 아니다.
"""
from __future__ import annotations

import time as _time_mod
from datetime import datetime, time
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit

MARKER = "[quote_token_refresh]"

_EXPECTED_KEYS = {"accounts", "issued", "failed", "elapsed_s", "window_issues_total"}


# ===========================================================================
# 하네스
# ===========================================================================

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


class _StepClock:
    """`time.monotonic` 더블. `advance_on_issue` 가 참이면 첫 발급에서 한 번 점프한다.

    ⚠️ 고정값 클록을 쓰는 이유 — 운영 코드가 `monotonic()` 을 몇 번 부르든 `t0` 가
    같은 값이어야 창 경계 단언이 호출 횟수에 흔들리지 않는다.
    """

    def __init__(self, start: float, jump: float = 0.0) -> None:
        self._now = start
        self._jump = jump
        self._jumped = False

    def __call__(self) -> float:
        return self._now

    def jump(self) -> None:
        if self._jump and not self._jumped:
            self._jumped = True
            self._now += self._jump


class _DummyMgr:
    """cycle269 `_DummyMgr` + `issue_history`(cycle296 관측 원천)."""

    def __init__(self, label, issued, clock, *, history=None, omit_history=False):
        self._label = label
        self._issued = issued
        self._clock = clock
        self.token_expired = datetime(2026, 9, 18, 20, 45, 0)
        if not omit_history:
            self.issue_history = list(history or [])

    async def revoke(self) -> None:
        return None

    async def issue(self) -> None:
        self._issued.append(self._label)
        if isinstance(getattr(self, "issue_history", None), list):
            self.issue_history.append(self._clock())
        self._clock.jump()


def _install(monkeypatch, accounts, *, histories=None, omit=(), list_raises=False,
             clock=None):
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    histories = histories or {}
    issued: list[str] = []
    managers: dict[str, _DummyMgr] = {}
    clock = clock or _StepClock(10_000.0)
    monkeypatch.setattr(_time_mod, "monotonic", clock)

    async def fake_list_accounts(active_only=False):
        if list_raises:
            raise RuntimeError("DB down")
        assert active_only is True
        return accounts

    async def fake_get_token_manager(label=None):
        mgr = _DummyMgr(
            label, issued, clock,
            history=histories.get(label), omit_history=label in omit,
        )
        managers[label] = mgr
        return mgr

    monkeypatch.setattr(kqa, "list_accounts", fake_list_accounts, raising=False)
    monkeypatch.setattr(
        token_mod, "get_token_manager", fake_get_token_manager, raising=False
    )
    return issued, managers, clock


def _require_keys(summary: dict) -> None:
    assert set(summary) == _EXPECTED_KEYS, (
        f"회차 요약 키가 5개가 아니다 — 실측 {sorted(summary)}. "
        "`accounts/issued/failed` 만으로는 09-15 21건·09-16 14건을 못 드러낸다"
    )


# ===========================================================================
# L0 — T = 20:45 (사용자 확정값)
# ===========================================================================

def test_l0_refresh_time_is_2045_exactly():
    """L0 — 사용자가 두 후보(15:30~16:00 · 20:45~21:00) 중 **20:45 로 확정**했다.

    범위 단언(`T+15 ≤ 21:30` 등)만으로는 21:00 같은 이웃값을 못 막는다 — 그것들도
    유효한 후보였기 때문이다. 확정값 자체를 핀으로 둔다.

    19:00 이 틀렸던 이유(`test_c9` 가 구조로 잰다): 문턱 T−10 이 정규장 밖이어도
    보조 풀은 **종일** REST 를 쓰므로 자연 재발급이 항상 강제보다 먼저 온다
    (09-16 실측 7/7 산술 일치 — ISA 문턱 18:51:25 → 실발화 18:55:03).
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T

    assert T == time(20, 45), (
        f"실측 {T} — 19:00 은 문턱(18:50)이 보조 풀 REST 창 한복판이라 매일 자연 "
        "재발급이 먼저 났다. 20:35~20:55 는 보조 풀 REST 0건(09-16 실측)."
    )


# ===========================================================================
# L1 — window_issues_total: 창 [t0 − 15분, ∞) 의 발급을 매니저 전부 합산
# ===========================================================================

@pytest.mark.asyncio
async def test_l1_window_counts_issues_across_managers_with_15min_lookback(
    monkeypatch,
):
    """L1 — 창은 **체인 시작 −15분**부터다.

    −15분인 이유: 정상 상태의 자연 문턱은 T−10(=20:35)에 온다. 그 창에서 발급이
    났다면(R6 — 20:30 일봉 적재가 길어져 20:35 를 넘긴 경우 등) 요약 한 줄로
    바로 드러나야 한다. 창을 그날 00:00 로 넓히면 지표가 "하루 총량" 이 되어
    그 신호가 흐려진다.
    """
    from src.engine import quote_token_refresh as mod

    clock = _StepClock(10_000.0)  # t0 = 10000.0 → 창 하한 9100.0
    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    histories = {
        "fire": [9_000.0, 9_100.0],   # 9000=창 밖 / 9100=경계 **포함**
        "gold": [9_900.0],
        "isa": [],
    }
    issued, managers, _ = _install(
        monkeypatch, accounts, histories=histories, clock=clock
    )

    summary = await mod.refresh_quote_tokens_once()

    _require_keys(summary)
    # 양성 대조군 — 발급 자체는 정상으로 돌았다.
    assert issued == ["fire", "gold", "isa"]
    assert summary["accounts"] == 3 and summary["issued"] == 3 and summary["failed"] == 0

    # 창 하한 = t0 − 900 = 9100.0.
    #   fire  [9000(밖), 9100(경계=포함)] + 강제 10000 → 2
    #   gold  [9900] + 강제 10000                      → 2
    #   isa   [] + 강제 10000                           → 1
    # 합 5. 9000.0 하나만 −15분 밖이라 빠진다.
    assert summary["window_issues_total"] == 5, (
        f"실측 {summary['window_issues_total']} — 기대 5 "
        f"(창 하한 {clock() - 900}: 9100 포함 / 9000 제외, 강제 3건 포함). "
        "창을 0 으로 좁히면 3, 하루 전체로 넓히면 6 이 나온다"
    )


# ===========================================================================
# L2 — issue_history 가 없는 매니저는 never-raise
# ===========================================================================

@pytest.mark.asyncio
async def test_l2_manager_without_issue_history_is_counted_as_zero(monkeypatch):
    """L2 — 테스트 더블·미래의 매니저 교체에 대해 관측이 체인을 막으면 안 된다.

    `getattr(manager, "issue_history", ())` 폴백. 관측 실패가 토큰 발급을
    실패시키는 방향은 금지다(관측은 hot path 밖이다).
    """
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold")]
    issued, _, _ = _install(monkeypatch, accounts, omit=("fire", "gold"))

    summary = await mod.refresh_quote_tokens_once()

    _require_keys(summary)
    assert issued == ["fire", "gold"], "관측 결손이 발급을 막았다"
    assert summary["issued"] == 2 and summary["failed"] == 0
    assert summary["window_issues_total"] == 0


@pytest.mark.asyncio
async def test_l2b_broken_issue_history_does_not_break_the_round(monkeypatch):
    """L2-b — `issue_history` 가 **터지는** 객체여도 회차는 정상 종료한다."""
    from src.engine import quote_token_refresh as mod

    class _Boom:
        def __iter__(self):
            raise RuntimeError("history broken")

    accounts = [_make_account("fire")]
    issued, managers, _ = _install(monkeypatch, accounts)
    # 발급이 끝난 뒤 산출 단계에서만 터지도록, 매니저 생성 훅을 감싼다.
    from src.auth import token as token_mod

    original = token_mod.get_token_manager

    async def wrapped(label=None):
        mgr = await original(label)
        mgr.issue_history = _Boom()
        return mgr

    monkeypatch.setattr(token_mod, "get_token_manager", wrapped, raising=False)

    summary = await mod.refresh_quote_tokens_once()

    _require_keys(summary)
    assert issued == ["fire"], "관측 산출 예외가 발급 결과를 뒤집었다"
    assert summary["issued"] == 1 and summary["failed"] == 0
    assert summary["window_issues_total"] == 0, "산출 실패는 0 으로 떨어져야 한다"


# ===========================================================================
# L3 — elapsed_s
# ===========================================================================

@pytest.mark.asyncio
async def test_l3_elapsed_seconds_is_an_int_measured_by_monotonic(monkeypatch):
    """L3 — 체인 총 소요. **monotonic** 이어야 한다.

    `token.py` 는 naive `datetime.now()`(컨테이너 TZ=KST)를 쓰고 leaf 는 KST aware 를
    쓸 수 있어 섞이면 9시간이 어긋난다. 창 산술만 필요하므로 tz 개념이 없는
    monotonic 이 맞다. `%d` 포맷이라 **정수**여야 한다.
    """
    from src.engine import quote_token_refresh as mod

    clock = _StepClock(10_000.0, jump=420.0)  # 첫 발급에서 +7분
    accounts = [_make_account("fire")]
    issued, _, _ = _install(monkeypatch, accounts, clock=clock)

    summary = await mod.refresh_quote_tokens_once()

    _require_keys(summary)
    assert issued == ["fire"]
    assert isinstance(summary["elapsed_s"], int) and not isinstance(
        summary["elapsed_s"], bool
    ), (
        f"`elapsed_s` 타입 실측 {type(summary['elapsed_s'])} — "
        "`_build_log_args` 가 `%d` 에 넣는다"
    )
    assert summary["elapsed_s"] == 420, (
        f"실측 {summary['elapsed_s']} — 체인 시작 monotonic 과 종료 monotonic 의 차"
    )


# ===========================================================================
# L4 — 조기 return 경로도 5키
# ===========================================================================

@pytest.mark.asyncio
async def test_l4_early_return_paths_also_carry_five_keys(monkeypatch):
    """L4 — 계정 목록 조회 실패 / 활성 계정 0건 경로가 3키 dict 를 돌려주면
    `_build_log_args` 의 `summary.get(key, 0)` 폴백에 가려져 **조용히** 0 이 찍힌다.
    그건 "측정했더니 0" 과 "측정조차 안 함" 을 구별 못 하게 만든다.
    """
    from src.engine import quote_token_refresh as mod

    _install(monkeypatch, [], list_raises=True)
    summary = await mod.refresh_quote_tokens_once()
    _require_keys(summary)
    assert summary == dict.fromkeys(sorted(_EXPECTED_KEYS), 0) or all(
        v == 0 for v in summary.values()
    ), f"실측 {summary}"

    _install(monkeypatch, [])
    summary2 = await mod.refresh_quote_tokens_once()
    _require_keys(summary2)
    assert summary2["accounts"] == 0 and summary2["window_issues_total"] == 0


# ===========================================================================
# L5 — 요약 1행이 실제로 렌더된다 (양성 대조군)
# ===========================================================================

@pytest.mark.asyncio
async def test_l5_summary_line_renders_with_both_new_fields(monkeypatch):
    """L5 — `run_periodic_task_loop` 가 하는 일을 그대로 재현한다.

    키/포맷이 어긋나면 여기서 `TypeError` 가 난다 — 운영에서는 그 예외가 task loop 의
    graceful 에 먹혀 **요약 1행이 매일 조용히 사라진다**(무증상 관측 소실).
    """
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold")]
    _install(monkeypatch, accounts, histories={"fire": [9_500.0]})
    summary = await mod.refresh_quote_tokens_once()

    args = tuple(summary.get(k, 0) for k in mod._SUMMARY_KEYS)
    line = mod._SUMMARY_LOG_FORMAT % args

    assert line.startswith(MARKER)
    assert "elapsed_s=" in line and "window_issues_total=" in line, f"실측 {line!r}"
    assert line == (
        f"{MARKER} accounts=2 issued=2 failed=0 elapsed_s=0 window_issues_total=3"
    ), f"실측 {line!r}"
