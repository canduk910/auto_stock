"""cycle270 — 보조 시세 계정 토큰 강제 재발급이 **만료 앵커를 실제로 옮기게** 한다.

## 왜 cycle269 만으로는 부족했나 (메인 세션 09-10 실측)

cycle269(`71b3bc2`, 09-09 배포)는 매일 15:45 KST 에 보조 계정 전부에
`TokenManager.issue()` 를 강제 호출해 만료 앵커를 15:45 로 옮히려 했다. 09-10
운영 로그에서 강제 발급은 **7/7 성공**했는데::

    15:45:00~15:51:07  [quote_token_refresh] label=ISA issued expired=2026-09-11 14:34:38

그 만료시각이 **같은 날 장중 자연 재발급이 남긴 값과 완전히 동일**했다::

    14:34:38  토큰 발급 완료(label=ISA), 만료: 2026-09-11 14:34:38

7계좌 전부 같은 패턴(fire 14:28:19 / gold 14:30:26 / 44606571 14:31:27 /
71513056 14:32:32 / 1004 14:33:35 / ISA 14:34:38 / RIA 14:50:22).

원인은 코드에 있다 — `src/auth/token.py:154-157` 은 만료를 **KIS 응답값 그대로**
대입한다(`data["access_token_token_expired"]`). 즉 KIS `/oauth2/tokenP` 는 유효
토큰이 살아 있으면 **같은 토큰·같은 만료**를 돌려준다. `issue()` 를 아무리 불러도
앵커는 안 움직이고, `_is_valid()`(`token.py:219-222`)의 10분 선제 갱신 마진이
만드는 하루 ≈ −10분 드리프트는 그대로다.

## 이 사이클이 잠그는 계약

- C1 계정별로 `revoke()` **먼저**, 이어서 `issue()`. **계정 단위 페어**이지
     "전부 revoke 뒤 전부 issue" 가 아니다(후자는 7계정을 동시에 무토큰으로
     ~7분 둔다 — 앞 계정의 무토큰 창을 61s 로 묶는 것이 설계다).
- C2 라운드가 끝나면 만료 앵커가 **재발급 시각 기준**으로 옮겨진다.
     (더블이 KIS 동일-토큰 의미론을 그대로 흉내낸다 → 현행 코드에서는 RED)
- C3 `revoke()` 실패 시에도 그 계정에 `issue()` 를 **시도한다**(토큰 없는 상태로
     남기지 않는다 = fail-open 방향). 단 그 계정의 앵커는 안 옮겨지므로 그 사실이
     로그로 드러나야 한다.
- C4 주계정(`label=None`/빈 label)은 revoke 도 issue 도 하지 않는다.
- C5 계정별 로그는 cycle269 접두를 byte 보존하고 끝에 ` revoked=<bool>` 만 붙는다.
     회차 요약 3필드(`accounts/issued/failed`)는 **불변**.
- C7 `get_token()` 금지는 그대로(캐시 hit 면 no-op 이라 앵커를 못 옮긴다).

C6(61s 직렬화 무우회) · C8(호출 순서·심볼 격리)은 AST 가드
`tests/unit/ast/test_cycle270_ast_revoke_then_issue.py` 소관.
C9(15:45 · `immediate_first_run=False`)는 cycle269 c8/c9 가 계속 잠근다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit

MARKER = "[quote_token_refresh]"

# 09-10 실측 서식 그대로 — 장중 자연 재발급이 남긴 만료(= 옮겨지지 않은 앵커).
_NATURAL_EXPIRY = datetime(2026, 9, 11, 14, 34, 38)
# 강제 재발급이 실행되는 시각(당시 15:45 KST — 09-10 밤 cycle270-B 21:30(루프 밖 무발화) → cycle270-C 19:00 이동, 이 픽스처는
# 만료 산술만 검증하므로 값은 그대로 둔다)과 그때 KIS 가 줘야 할 새 만료.
_REFRESH_AT = datetime(2026, 9, 10, 15, 45, 0)
_NEW_EXPIRY = _REFRESH_AT + timedelta(hours=24)


# cycle296 (2026-09-17) — C5 의 "회차 요약 3필드 불변" 은 **이 사이클로 해제됐다**.
# C5-b 가 예고한 "별도 사이클" 이 바로 cycle296 이다(합류 배포 뒤 '정말 줄었는지' 를
# 로그로 읽으려면 강제분만 세는 `issued` 로는 부족하다 — §3-3).
_SUMMARY_KEYS_296 = ("accounts", "issued", "failed", "elapsed_s", "window_issues_total")


def _core(summary: dict) -> dict:
    """cycle296 관측 2키를 성질로 검사한 뒤 떼어 내고 핵심 3키만 돌려준다.

    `_KisLikeMgr` 는 `issue_history` 를 갖지 않으므로 창 집계는 항상 0 이어야 한다
    (관측 배관의 `getattr(..., ())` 폴백이 never-raise 인지의 증거).
    """
    assert set(summary) == set(_SUMMARY_KEYS_296), (
        f"cycle296 회차 요약은 5키다 — 실측 {sorted(summary)}"
    )
    assert isinstance(summary["elapsed_s"], int) and not isinstance(
        summary["elapsed_s"], bool
    )
    assert summary["elapsed_s"] >= 0
    assert summary["window_issues_total"] == 0
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


class _KisLikeMgr:
    """KIS `/oauth2/tokenP` 의 **동일-토큰 의미론**을 심은 토큰 매니저 더블.

    - `issue()` — 유효 토큰이 살아 있으면 같은 토큰·같은 만료를 돌려준다(만료
      필드를 건드리지 않는다). 이것이 09-10 실측의 재현이다. 비어 있는 상태에서만
      `호출 시각 + 24h` 를 새 만료로 준다.
    - `revoke()` — `token.py:178-180` 과 동형으로 `access_token`/`token_expired`
      를 비운다. 단 `token.py:166-167` 처럼 토큰이 없으면 아무것도 하지 않는다.
    """

    def __init__(self, label, calls, clock, *, revoke_fails=False, issue_fails=False):
        self._label = label
        self._calls = calls
        self._clock = clock
        self._revoke_fails = revoke_fails
        self._issue_fails = issue_fails
        # 그날 장중 자연 재발급으로 이미 유효 토큰을 들고 있는 상태에서 시작한다.
        self.access_token = f"TOK-{label}"
        self.token_expired = _NATURAL_EXPIRY

    async def revoke(self) -> None:
        self._calls.append(("revoke", self._label))
        if self._revoke_fails:
            raise RuntimeError("KIS revokeP 500")
        if not self.access_token:
            return
        self.access_token = ""
        self.token_expired = None

    async def issue(self) -> None:
        self._calls.append(("issue", self._label))
        if self._issue_fails:
            raise RuntimeError("KIS tokenP 500")
        if self.access_token and self.token_expired is not None:
            return  # ← KIS 동일-토큰: 만료 불변
        self.access_token = f"TOK-{self._label}-new"
        self.token_expired = self._clock["now"] + timedelta(hours=24)

    async def get_token(self) -> str:
        self._calls.append(("get_token", self._label))
        return self.access_token


def _install(
    monkeypatch,
    accounts,
    *,
    revoke_fail=(),
    issue_fail=(),
    list_raises=False,
    now=_REFRESH_AT,
):
    """`list_accounts` + `get_token_manager` 교체. 호출 순서와 매니저를 돌려준다."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    calls: list[tuple[str, str]] = []
    managers: dict[str, _KisLikeMgr] = {}
    manager_labels: list = []
    clock = {"now": now}

    async def fake_list_accounts(active_only=False):
        if list_raises:
            raise RuntimeError("DB down")
        assert active_only is True, "활성 계정만 대상이어야 한다"
        return accounts

    async def fake_get_token_manager(label=None):
        manager_labels.append(label)
        mgr = _KisLikeMgr(
            label,
            calls,
            clock,
            revoke_fails=label in revoke_fail,
            issue_fails=label in issue_fail,
        )
        managers[label] = mgr
        return mgr

    monkeypatch.setattr(kqa, "list_accounts", fake_list_accounts, raising=False)
    monkeypatch.setattr(
        token_mod, "get_token_manager", fake_get_token_manager, raising=False
    )
    return calls, managers, manager_labels


# ===========================================================================
# C1 — 계정별 revoke → issue 페어
# ===========================================================================

@pytest.mark.asyncio
async def test_c1_revoke_precedes_issue_for_each_account(monkeypatch):
    """C1 — 계정마다 revoke 가 issue 바로 앞에 온다(계정 단위 페어)."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    calls, _, _ = _install(monkeypatch, accounts)

    await mod.refresh_quote_tokens_once()

    assert calls == [
        ("revoke", "fire"), ("issue", "fire"),
        ("revoke", "gold"), ("issue", "gold"),
        ("revoke", "isa"), ("issue", "isa"),
    ], (
        "계정 단위 페어여야 한다 — '전부 revoke 뒤 전부 issue' 는 7계정을 동시에 "
        "무토큰으로 ~7분 두므로 금지"
    )


# ===========================================================================
# C2 — 앵커가 실제로 옮겨진다 (이 사이클의 핵심 RED)
# ===========================================================================

@pytest.mark.asyncio
async def test_c2_round_moves_expiry_anchor_to_refresh_time(monkeypatch):
    """C2 — 라운드 후 모든 보조 계정의 만료가 **재발급 시각 기준**으로 바뀐다.

    현행 코드(`issue()` 단독)에서는 KIS 가 같은 만료를 돌려주므로 라운드 전후가
    동일하다 = RED. `revoke()` 로 앵커를 비운 뒤 발급해야 GREEN 이 된다.
    """
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    _, managers, _ = _install(monkeypatch, accounts)

    summary = await mod.refresh_quote_tokens_once()

    assert summary["issued"] == 3
    for label in ("fire", "gold", "isa"):
        mgr = managers[label]
        assert mgr.token_expired == _NEW_EXPIRY, (
            f"label={label} 만료가 {mgr.token_expired} — 재발급 시각 기준 앵커"
            f"({_NEW_EXPIRY})로 옮겨지지 않았다"
        )
        assert mgr.token_expired != _NATURAL_EXPIRY


@pytest.mark.asyncio
async def test_c2b_issue_alone_cannot_move_anchor():
    """C2-b — 더블 자체의 특성화. `issue()` 만으로는 만료가 절대 안 바뀐다.

    이 단언이 없으면 누군가 더블의 `issue()` 를 '항상 새 만료' 로 느슨하게 바꿔
    C2 를 revoke 없이도 통과시킬 수 있다(가짜 GREEN).
    """
    calls: list[tuple[str, str]] = []
    mgr = _KisLikeMgr("fire", calls, {"now": _REFRESH_AT})

    await mgr.issue()
    assert mgr.token_expired == _NATURAL_EXPIRY, "유효 토큰이 있으면 KIS 는 같은 만료를 준다"

    await mgr.revoke()
    await mgr.issue()
    assert mgr.token_expired == _NEW_EXPIRY, "폐기 후에야 새 만료가 나온다"


# ===========================================================================
# C3 — revoke 실패는 issue 를 막지 않는다 (fail-open 방향)
# ===========================================================================

@pytest.mark.asyncio
async def test_c3_revoke_failure_still_attempts_issue(monkeypatch):
    """C3 — revoke 가 죽어도 그 계정에 issue 를 시도한다(무토큰 방치 금지)."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    calls, managers, _ = _install(monkeypatch, accounts, revoke_fail=("gold",))

    summary = await mod.refresh_quote_tokens_once()

    assert ("issue", "gold") in calls, "revoke 실패 계정을 건너뛰면 토큰 없는 채로 남는다"
    assert calls.index(("revoke", "gold")) < calls.index(("issue", "gold"))
    assert _core(summary) == {"accounts": 3, "issued": 3, "failed": 0}
    # revoke 가 죽었으니 그 계정만 앵커가 그대로다 — 이것이 관측돼야 하는 사실이다.
    assert managers["gold"].token_expired == _NATURAL_EXPIRY
    assert managers["fire"].token_expired == _NEW_EXPIRY


@pytest.mark.asyncio
async def test_c3b_revoke_failure_is_logged_loudly(monkeypatch, caplog):
    """C3-b — revoke 실패는 WARNING 이상으로 남는다(조용히 흡수 금지)."""
    from src.engine import quote_token_refresh as mod

    caplog.set_level(logging.DEBUG, logger="src.engine.quote_token_refresh")
    accounts = [_make_account("fire"), _make_account("gold")]
    _install(monkeypatch, accounts, revoke_fail=("gold",))

    await mod.refresh_quote_tokens_once()

    loud = [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(MARKER)
    ]
    assert any("gold" in m for m in loud), (
        f"revoke 실패가 WARNING 이상으로 남지 않았다 — 실측 {loud}"
    )


@pytest.mark.asyncio
async def test_c3c_issue_failure_absorbed_per_account(monkeypatch):
    """C3-c — issue 실패는 cycle269 c4 계약 그대로 계정 단위 흡수 + `failed`."""
    from src.engine import quote_token_refresh as mod

    accounts = [_make_account("fire"), _make_account("gold"), _make_account("isa")]
    calls, managers, _ = _install(monkeypatch, accounts, issue_fail=("gold",))

    summary = await mod.refresh_quote_tokens_once()

    assert _core(summary) == {"accounts": 3, "issued": 2, "failed": 1}
    assert ("revoke", "isa") in calls and ("issue", "isa") in calls
    assert managers["isa"].token_expired == _NEW_EXPIRY
    # 폐기는 됐는데 발급이 죽은 계정 = 토큰 없음. 다음 시세 요청의 `get_token()` 이
    # 스스로 재발급하므로(=`_is_valid()` False) 자기 치유되지만, 그 사실이 명세에 남아야 한다.
    assert managers["gold"].token_expired is None


# ===========================================================================
# C4 — 주계정 무접촉
# ===========================================================================

@pytest.mark.asyncio
async def test_c4_main_account_never_revoked_or_issued(monkeypatch):
    """C4 — 빈 label 은 매니저 조회조차 하지 않는다(= `get_token_manager(None)` 차단)."""
    from src.engine import quote_token_refresh as mod

    blank = _make_account("gold")
    object.__setattr__(blank, "label", "")
    accounts = [_make_account("fire"), blank, _make_account("isa")]
    calls, _, manager_labels = _install(monkeypatch, accounts)

    summary = await mod.refresh_quote_tokens_once()

    assert manager_labels == ["fire", "isa"]
    assert None not in manager_labels
    assert [c for c in calls if c[1] == ""] == []
    assert _core(summary) == {"accounts": 3, "issued": 2, "failed": 1}


# ===========================================================================
# C5 — 로그 서식 (접두 byte 보존 + revoked 필드)
# ===========================================================================

@pytest.mark.asyncio
async def test_c5_per_account_log_appends_revoked_field(monkeypatch, caplog):
    """C5 — cycle269 접두를 그대로 두고 끝에 ` revoked=<bool>` 만 붙인다."""
    from src.engine import quote_token_refresh as mod

    caplog.set_level(logging.INFO, logger="src.engine.quote_token_refresh")
    accounts = [_make_account("fire"), _make_account("gold")]
    _install(monkeypatch, accounts, revoke_fail=("gold",))

    await mod.refresh_quote_tokens_once()

    issued_lines = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage().startswith(f"{MARKER} label=")
    ]
    assert issued_lines == [
        f"{MARKER} label=fire issued expired={_NEW_EXPIRY} revoked=True",
        f"{MARKER} label=gold issued expired={_NATURAL_EXPIRY} revoked=False",
    ], f"실측 {issued_lines}"


def test_c5b_round_summary_contract_is_now_five_fields():
    """C5-b — 🔁 **cycle296 의미 전환**: 요약이 3필드 → **5필드**가 됐다.

    cycle270 은 "`revoked` 를 요약에 넣지 않는다 — 넣고 싶다면 별도 사이클" 이라고
    적었다. 그 별도 사이클이 cycle296 이고, 넣은 것은 `revoked` 가 아니라 **관측 2키**다:

    - `elapsed_s` — 체인 총 소요(정상 ≈420s, 09-15 실측 최악 14분 40초)
    - `window_issues_total` — 체인 시작 −15분부터 종료까지 그 라벨들의 **모든** 발급 수

    `issued=7 failed=0` 은 09-15 의 실제 21건, 09-16 의 14건 앞에서도 참이었다.
    합류가 배포된 뒤 "정말 줄었는지" 를 읽으려면 강제분 밖도 세야 한다.

    `revoked` 는 여전히 요약에 없다 — 계정별 행(` revoked=`)과 WARNING 이 이미 잰다.
    """
    from src.engine import quote_token_refresh as mod

    assert mod._SUMMARY_KEYS == _SUMMARY_KEYS_296, f"실측 {mod._SUMMARY_KEYS}"
    assert mod._SUMMARY_LOG_FORMAT == (
        f"{MARKER} accounts=%d issued=%d failed=%d "
        "elapsed_s=%d window_issues_total=%d"
    ), f"실측 {mod._SUMMARY_LOG_FORMAT!r}"
    # 양성 대조군 — cycle269/270 의 3필드는 **그대로 살아 있다**(교체가 아니라 추가).
    assert mod._SUMMARY_KEYS[:3] == ("accounts", "issued", "failed")
    assert "revoked" not in mod._SUMMARY_KEYS, (
        "revoke 성패는 계정별 행이 잰다 — 요약에 넣으면 같은 사실이 두 곳으로 갈린다"
    )
    assert mod._SUMMARY_LOG_FORMAT.count("%d") == len(mod._SUMMARY_KEYS)


@pytest.mark.asyncio
async def test_c5c_summary_dict_keys_unchanged(monkeypatch):
    """C5-c — 반환 dict 키도 cycle296 의 5개로 따라간다.

    `_SUMMARY_KEYS` 와 반환 dict 가 갈리면 `run_periodic_task_loop._build_log_args` 의
    `summary.get(key, 0)` 폴백이 **조용히 0** 을 찍는다 — "측정했더니 0" 과 "측정조차
    안 함" 이 구별되지 않는다.
    """
    from src.engine import quote_token_refresh as mod

    _install(monkeypatch, [_make_account("fire")])
    summary = await mod.refresh_quote_tokens_once()

    assert set(summary) == set(mod._SUMMARY_KEYS) == set(_SUMMARY_KEYS_296), (
        f"실측 {sorted(summary)}"
    )


# ===========================================================================
# C7 — get_token 금지 (의미 전환 후에도 불변)
# ===========================================================================

@pytest.mark.asyncio
async def test_c7_get_token_still_never_used(monkeypatch):
    """C7 — `get_token()` 은 캐시 hit 면 no-op 이라 여전히 쓰면 안 된다."""
    from src.engine import quote_token_refresh as mod

    calls, _, _ = _install(monkeypatch, [_make_account("fire"), _make_account("gold")])

    await mod.refresh_quote_tokens_once()

    assert [c for c in calls if c[0] == "get_token"] == []
