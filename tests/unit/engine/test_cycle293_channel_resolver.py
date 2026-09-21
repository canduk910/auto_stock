"""cycle293 Red (2단계 · 속성축 배관) — 행위 가드.

명세 = `_workspace/red/cycle293_tick_channel_resolver_spec.md`
회귀 가드 목록 = 그 문서 §10 (G1~G10) · 불변식 = §7-D (INV-1~4)
AST 자매 = `tests/unit/ast/test_cycle293_ast_channel_resolver.py`

## 종착지 (재론 금지)

통합 채널 `H0UNCNT0` 폐기. KRX 전용(`H0STCNT0`) + NXT 전용(`H0NXCNT0`) 2채널.
2026-09-07 사용자 결정 + 2026-09-14 재확인. 이 사이클은 그 **2단계**(배관)만 했다 —
`tick_tr_id_for()` 도입 + 등가 비교 집합화. **전환은 넣지 않았다**(§3-C).

## 🔴 cycle294(3단계)가 이 파일의 일부를 **의미 전환**했다 — 삭제가 아니다

cycle293 스스로 "아래 fail-open `H0UNCNT0` 는 **2단계 한정 과도기 장치**"라고
못박았다(§3-D). 3단계는 통합을 반환 경로에서 지우므로 그 폴백이 **성립하지
않는다**. 그래서 아래 셋이 술어를 바꿨고, **잠그는 위험은 그대로다**:

| 테스트 | 2단계 술어 | cycle294 이후 |
|---|---|---|
| `test_g2_*`(fail-open) | 판정 실패 → 통합 | **프리 창 → NXT · KRX 창 → KRX**. "구독을 안 한다" 는 여전히 금지(P0-1) |
| `test_g1_*`·`test_g7*`·`test_inv4` | `nxt_true` → 통합 | `nxt_true` → **시각축**(프리 창 NXT / KRX 창 KRX) |
| `test_g9*`(매수 축) | 채널 축 술어 | **코호트 축**(`tick_buy_cohort_blocked`) — 전 종목 전용 채널이 되어 채널 축은 5전략 매수를 통째로 죽인다 |

🔴 **이 파일을 지워서 초록을 만들지 마라.** cycle293 이 잰 위험(유니버스 64%
신규 노출 · W2 도장 창의 420종목 오배치 · 킬스위치 `off` 가 매수를 여는 경로)은
3단계에서도 살아 있고 술어만 바뀐다.

## 이 파일이 잠그는 것

| ID | §10 | 잠그는 것 |
|----|-----|-----------|
| G2 | fail-open | 미지 · 미적재 · 예외 · `None` · 출처 미확인 → **전부 `H0UNCNT0`** |
| G1 | 반환 도메인 | no_feed ∧ 출처 확인 → `H0STCNT0` |
| KS | §8-B | 킬스위치 `off` = 현행 동일 · `observe` = 행위 0 · 재조회가 재시작 불요 |
| G3 | 이중 채널 | 같은 종목 두 채널 동시 등록 0 + `[tick_channel_dual_detected]` |
| G5 | 집합화 | `H0STCNT0`/`H0NXCNT0` 종목이 집계 분모에 **남는다** |
| G6 | grace 키 | `H0STCNT0` 종목의 180초 구독 grace 가 산다(SEND 폭주 부활 차단) |
| G7 | 플리커 | 래치 없음(양방향) · 출처 미확인으로는 안 옮김 · 같은 날 재전환 0 |
| G8 | 해제 정합 | 해제가 그 종목의 **실제** 채널로 나간다(OPSP0003 차단) |
| G9 | 🔴 매수 축 | `nxt_false` 종목이 5전략 매수 평가에 도달하지 않는다 (+ 수단 무관 불변식 `열렸다 ⟹ 매수 0`) |
| G4 | INV-2 | HIGH(보유·익일청산) `bypass_limit=True` 보장 |

## 🔴 G9 와 `risk.py` diff 0 은 동시에 만족되지 않는다

오케스트레이션 지시는 (a) `risk.py` **diff 0** 과 (b) `nxt_false` 종목이 5전략
매수 평가에 **도달하지 않음**을 동시에 요구한다. (b)의 유일한 자리가
`risk.on_tick` 의 매수 분기라 둘은 동시에 성립하지 않는다. 선택지 둘은 AST 자매
파일의 `test_a1b_risk_py_pin_is_the_open_decision` docstring 에 적혀 있다.

그래서 매수 축은 **두 층**으로 잠근다 —

* `test_g9_ticker_axis_gate_*` (5케이스) = 지시대로의 행위 단언. 선택지 (가)
  `risk.py` 1행 게이트가 있어야 초록이 된다.
* **`test_g9b_opening_a_channel_never_opens_the_buy_axis`** = `채널이 열렸다 ⟹
  매수 평가 0` 이라는 **수단 무관 불변식**. 선택지 (가)든 (나)든 초록이고,
  **위험한 조합(LOW 이동 + 게이트 없음)에서만** 붉다. 어느 쪽을 골라도 이
  테스트는 뒤집지 않는다.

`test_g9b_*` 가 붉은 채로 배포하지 말 것 — 그때 시총 1,000억↑ 유니버스의 64%가
5전략 매수 평가에 새로 노출된다(= 승인받지 않은 매매 행위 변경, §3-E).

## 이 파일이 고정한 이름

`scanner.TICK_TR_IDS` · `scanner.tick_tr_id_for(ticker, *, priority="LOW")` ·
`src/engine/tick_channel_mode.py`(`current_mode`/`refresh_mode`/`set_mode_for_test`) ·
`no_feed_registry.is_provenance_ok(ticker)` · `websocket_pool._ticker_to_tr_id`.
근거·경위는 AST 자매 파일 docstring 참조.
"""

from __future__ import annotations

import datetime as _datetime_module
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.strategy_base import (
    Position, Signal, StrategyBase, StrategyConfig,
)

pytestmark = pytest.mark.unit

KST = _datetime_module.timezone(_datetime_module.timedelta(hours=9))

UNIFIED = "H0UNCNT0"
KRX_ONLY = "H0STCNT0"
NXT_ONLY = "H0NXCNT0"

#: 09-14 실측 보유 `nxt_false` 4종목 중 둘 + 포렌식 유동주 표본.
NO_FEED = "003470"        # 유안타증권 — kojiro 보유, nxt_tradable=False
NO_FEED_2 = "005935"      # 삼성전자우 — 포렌식 유동주 표본(stale 15/15 중 하나)
NXT_TRUE = "005930"       # 삼성전자 — nxt_tradable=True

_DUAL_MARKER = "[tick_channel_dual_detected]"
_DENIED_MARKER = "[tick_channel_request_denied]"
_RESOLVE_MARKER = "[tick_channel_resolve]"
_FLIP_MARKER = "[tick_channel_flip]"
_CONFIG_MARKER = "[tick_channel_config]"


# ===========================================================================
# 헬퍼 — 모듈 부재는 SKIP 이 아니라 FAIL (Red 는 붉어야 한다)
# ===========================================================================
def _scanner():
    from src.engine import scanner

    return scanner


def _resolver():
    scanner = _scanner()
    fn = getattr(scanner, "tick_tr_id_for", None)
    if fn is None:
        pytest.fail(
            "§3-A — `scanner.tick_tr_id_for` 미존재. `TICK_TR_ID`/`_KRX`/`_NXT` "
            "상수 3줄 바로 아래에 동기 순수 함수로 넣어라"
        )
    return fn


def _tick_tr_ids() -> frozenset[str]:
    scanner = _scanner()
    s = getattr(scanner, "TICK_TR_IDS", None)
    if s is None:
        pytest.fail(
            "§5-B — `scanner.TICK_TR_IDS` 미존재. `stale_diagnostics.py:76` 의 "
            "함수 지역 `_TICK_TR_IDS` 를 모듈 레벨 단일 정본으로 승격하라"
        )
    return s


def _mode_mod():
    try:
        from src.engine import tick_channel_mode  # type: ignore[attr-defined]
    except ImportError as exc:  # pragma: no cover - Red 경로
        pytest.fail(
            "§8-B — 킬스위치 leaf `src/engine/tick_channel_mode.py` 미존재. "
            "cycle287 은 킬스위치를 같은 커밋에 넣지 않아 장중에 끌 수 없었다. "
            f"import 실패: {exc}"
        )
    return tick_channel_mode


def _registry():
    from src.engine import no_feed_registry

    return no_feed_registry


#: cycle294 의미 전환 — 시각축이 생겨 판정이 **시각에 따라** 달라진다. 두 창을
#: 고정 시각으로 잰다(달력 벽시계에 의존하면 CI 가 도는 시각에 따라 갈린다 —
#: 메모리 교훈 「시각 창 게이트 테스트는 시각 고정」).
#: 표 유효일자는 **09-14 이후**여야 한다(K6 애프터마켓 `effective_from=2026-09-14`).
_STAGE3_DAY = _datetime_module.date(2026, 9, 15)


def _pre_window() -> "_datetime_module.datetime":
    """프리 창(전환 시각 이전) — 속성축이 살아 있는 유일한 구간."""
    return _datetime_module.datetime.combine(
        _STAGE3_DAY, _datetime_module.time(8, 10), tzinfo=KST,
    )


def _krx_window() -> "_datetime_module.datetime":
    """KRX 창(정규장) — 속성축을 보지 않는다(09-14 실측 §7-C)."""
    return _datetime_module.datetime.combine(
        _STAGE3_DAY, _datetime_module.time(10, 0), tzinfo=KST,
    )


@pytest.fixture(autouse=True)
def _isolate_registry_and_mode(monkeypatch):
    """레지스트리·모드·채널 판정 이력을 테스트마다 초기화한다.

    cycle294 — `scanner` 의 채널 적용 이력(`_channel_applied`/`_channel_flipped_today`)
    과 코호트 스탬프(`_channel_cohort`)까지 비운다. 비우지 않으면 §6-D 하루 1회 전환
    예산이 파일 내 실행 순서에 따라 앞 테스트에 소모돼 뒤 테스트가 조용히 갈린다.
    """
    reg = _registry()
    reset = getattr(reg, "reset_state_for_test", None)
    reset_scanner = getattr(_scanner(), "reset_tick_channel_state_for_test", None)
    for fn in (reset, reset_scanner):
        if callable(fn):
            fn()
    yield
    for fn in (reset, reset_scanner):
        if callable(fn):
            fn()


def _set_mode(monkeypatch, mode: str) -> None:
    """모드를 강제한다. `set_mode_for_test` 가 없으면 Red 메시지로 실패."""
    mod = _mode_mod()
    setter = getattr(mod, "set_mode_for_test", None)
    if not callable(setter):
        pytest.fail(
            "§8-B — `tick_channel_mode.set_mode_for_test(mode)` 테스트 seam 필요"
        )
    setter(mode)


def _patch_classification(
    monkeypatch, *, no_feed=(), provenance_ok=(), is_no_feed_raises=None,
    classified=None,
):
    """`no_feed_registry` 의 세 판정을 주입한다.

    `provenance_ok` = 출처(§6-C `raw ? 'cptt_trad_tr_psbl_yn'`)가 확인된 종목.
    `classified` = 레지스트리가 **분류한 적 있는** 종목(미지정 시 `no_feed ∪
    provenance_ok`). cycle293 Green — `is_no_feed()` 의 "모르면 False" 가 **미지**와
    **송출 정상**을 같은 값으로 접어 INV-4("판정 실패 + 보유 = WARNING")가
    구조적으로 성립하지 않던 것을 `is_classified()` 로 갈랐다.
    """
    reg = _registry()
    nf = set(no_feed)
    prov = set(provenance_ok)
    known = set(classified) if classified is not None else (nf | prov)

    def _is_no_feed(ticker: str) -> bool:
        if is_no_feed_raises is not None:
            raise is_no_feed_raises
        return ticker in nf

    monkeypatch.setattr(reg, "is_no_feed", _is_no_feed)
    if not hasattr(reg, "is_classified"):
        pytest.fail(
            "cycle293 Green — `no_feed_registry.is_classified(ticker)` 미존재. "
            "미지(레지스트리 미적재)와 송출 정상을 가르지 못하면 INV-4 가 성립하지 "
            "않는다(07:59 사전 구독 시점 전 종목이 조용히 '판정 성공' 으로 기록된다)"
        )
    monkeypatch.setattr(reg, "is_classified", lambda t: t in known)
    if not hasattr(reg, "is_provenance_ok"):
        pytest.fail(
            "§6-C — `no_feed_registry.is_provenance_ok(ticker)` 미존재. "
            "W2 도장 창(07:45~08:08)에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어 "
            "`nxt_tradable` 값을 그대로 믿으면 진짜 NXT 종목 ≈420개가 "
            "NXT 체결을 실을 수 없는 채널로 간다"
        )
    monkeypatch.setattr(reg, "is_provenance_ok", lambda t: t in prov)
    return reg


# ===========================================================================
# G2 — 🔴 fail-open 방향: 판정 실패는 전부 현행 유지(H0UNCNT0)
# ===========================================================================
@pytest.mark.parametrize(
    ("case", "kwargs"),
    [
        # 미지 ticker — 레지스트리가 분류한 적 없다
        ("unknown_ticker", {"no_feed": (), "provenance_ok": ()}),
        # 레지스트리 미적재 = 공집합 (부팅 직후 / DB 실패)
        ("registry_empty", {"no_feed": (), "provenance_ok": (NO_FEED,)}),
        # no_feed 인데 출처 미확인 (W2 도장 창) — 🔴 여기서 옮기면 420종목 오배치
        ("provenance_unknown", {"no_feed": (NO_FEED,), "provenance_ok": ()}),
        # 조회 예외
        ("lookup_raises", {"no_feed": (NO_FEED,), "provenance_ok": (NO_FEED,),
                           "is_no_feed_raises": RuntimeError("boom")}),
    ],
)
def test_g2_fail_open_always_returns_current_channel(monkeypatch, case, kwargs):
    """🔴 G2 — 판정 실패는 **구독을 막지 않는다** (cycle294 §3-B 로 방향 전환).

    ## 2단계 술어와 그것이 3단계에서 성립하지 않게 된 이유

    cycle293 은 "판정 실패 → 전부 `H0UNCNT0`(현행 유지)" 로 잠갔고, 그 문서
    스스로 그것을 **2단계 한정 과도기 장치**라고 못박았다(§3-D). cycle294 는
    통합 채널을 **반환 경로에서 지운다** — 그래서 "현행 유지" 라는 폴백이 가리킬
    대상이 없다.

    ## 3단계의 fail-open — 층마다 다르다 (cycle294 §3-B)

    * **L2 속성축 실패**(이 테스트) → **프리 창에서 `H0NXCNT0`**. 비대칭이
      방향을 정한다: 모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을
      **새로 잃지만**(INV-1 위반), NXT 로 보내면 진짜 `nxt_false` 는 그 구간에
      시장 자체가 없어 **잃을 것이 0** 이다. ⇒ 잃을 수 있는 쪽을 보존한다.
      부수 효과로 W2 도장 창(07:59 에 65.4% 오염)의 420종목이 **정답인 NXT** 로
      간다 — 2단계에서 "KRX 오배치" 였던 실패 비용이 3단계에서는 0 이다.
    * **KRX 창**에서는 속성축을 아예 보지 않는다 → 판정 실패와 무관하게 KRX.

    ## 바뀌지 않은 것 (이 테스트가 계속 잠그는 위험)

    **구독을 안 하는 방향으로는 여전히 가지 않는다** — 그것은 P0-1(유령 키
    `acml_vol` 이 두 전략을 전 기간 체결 0건으로 만든 사고)의 재현 방향이고,
    금기 5 가 `fail-closed 금지` 로 명문화한 그것이다. 반환은 항상 정본 집합의
    **전용 2채널 중 하나**다.

    ⚠️ 보유 종목에서 판정이 실패하면 그 종목의 채널이 추측으로 정해진다 — 그래서
    INV-4 가 그 경우를 WARNING 으로 사람에게 올린다(`test_inv4_*`).
    """
    _patch_classification(monkeypatch, **kwargs)
    _set_mode(monkeypatch, "enforce")
    resolve = _resolver()

    got_pre = resolve(NO_FEED, now=_pre_window())
    assert got_pre == NXT_ONLY, (
        f"[{case}] 프리 창 판정 실패가 {got_pre!r} 로 갔다 — L2 fail-open 은 "
        f"{NXT_ONLY!r}(잃을 수 있는 쪽 보존)여야 한다(cycle294 §3-B)"
    )

    got_krx = resolve(NO_FEED, now=_krx_window())
    assert got_krx == KRX_ONLY, (
        f"[{case}] KRX 창에서 {got_krx!r} 가 나왔다 — 그 창은 속성축을 보지 않는다"
    )

    for got in (got_pre, got_krx):
        assert got in _tick_tr_ids() and got != UNIFIED, (
            f"[{case}] 3단계에서 통합 채널({UNIFIED})은 정상 경로의 반환값이 아니다 "
            "— 유일한 통합 반환 경로는 킬스위치 `off` 뿐이다(cycle294 절대 규칙 1)"
        )


def test_g2b_resolver_never_returns_none_or_empty(monkeypatch):
    """G2b — 리졸버가 `None`/빈 문자열을 돌려주면 `subscribe()` 가 조용히 망친다."""
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=())
    _set_mode(monkeypatch, "enforce")
    resolve = _resolver()

    for ticker in ("", "999999", NXT_TRUE, NO_FEED):
        got = resolve(ticker)
        assert got in _tick_tr_ids(), (
            f"ticker={ticker!r} → {got!r} 가 정본 집합 밖이다 (G1 반환 도메인)"
        )


# ===========================================================================
# G1 — 본체: no_feed ∧ 출처 확인 → KRX 전용
# ===========================================================================
def test_g1_no_feed_with_authoritative_source_goes_krx(monkeypatch):
    """G1 — 무송출 확정 + 출처 권위 확인 → `H0STCNT0`.

    근거 = 064550 양방향 자연 실험(09-01 `nxt_true` 32,806 프레임 → 09-02 16:06
    `nxt_false` 전환 → 프레임 **0**) + 포렌식 나흘 × ~200종목 예외 0 +
    09-14 `stale_sample` **15/15 전부 `nxt_tradable=False`**.
    """
    _patch_classification(
        monkeypatch, no_feed=(NO_FEED, NO_FEED_2), provenance_ok=(NO_FEED, NO_FEED_2),
    )
    _set_mode(monkeypatch, "enforce")
    resolve = _resolver()

    # 프리 창 — 속성축이 살아 있는 유일한 구간. 무송출 확정 종목만 KRX 로 내린다.
    assert resolve(NO_FEED, now=_pre_window()) == KRX_ONLY
    assert resolve(NO_FEED_2, now=_pre_window()) == KRX_ONLY
    # 🔴 cycle294 의미 전환 — 2단계에서 `nxt_true` 의 답은 통합이었다. 3단계는
    #    통합을 없애고 **시각축**이 답을 정한다: 프리 창엔 NXT 만 열려 있으므로 NXT.
    assert resolve(NXT_TRUE, now=_pre_window()) == NXT_ONLY, (
        "`nxt_true` 종목은 프리 창에 NXT 전용 채널로 간다 — 그 시각 NXT 만 "
        "연속 체결을 싣는다(cycle294 §0 구간표)"
    )
    # KRX 창 — 속성축을 보지 않는다. 09-14 16:39 라이브 실측이 `H0STCNT0` 의
    # **종목 속성 무관 수신**을 확정했다(nxt_false·nxt_true 전부 체결 수신).
    for ticker in (NO_FEED, NO_FEED_2, NXT_TRUE):
        assert resolve(ticker, now=_krx_window()) == KRX_ONLY


# ===========================================================================
# 킬스위치 (§8-B)
# ===========================================================================
def test_ks_off_is_byte_identical_to_today(monkeypatch):
    """🔴 KS-1 — `off` 면 리졸버가 **전 종목 `H0UNCNT0`** 를 돌려준다(현행 동일).

    롤백 경로가 코드 revert 가 아니어야 한다 — 1커밋 revert 는 재배포 = 재시작이고
    D6(보유 중 장중 재시작 금지) · D8(20:00~21:35 금지)이 그것을 막는다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "off")
    resolve = _resolver()

    assert resolve(NO_FEED) == UNIFIED
    assert resolve(NO_FEED, priority="HIGH") == UNIFIED


def test_ks_observe_is_behaviourally_zero(monkeypatch, caplog):
    """KS-2 (§8-A S0) — `observe` 는 판정만 로그로 남기고 채널은 바꾸지 않는다.

    다크런치 진행 게이트 = `resolved_krx` 가 0이 아니고, `[tick_coverage]` ·
    `[stale_watcher_summary] no_feed_skipped=` · `[priority_drop]` 이 **전부 불변**.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "observe")
    resolve = _resolver()
    caplog.set_level(logging.INFO)

    got = resolve(NO_FEED)

    assert got == UNIFIED, "`observe` 모드가 실제로 채널을 바꿨다 = 행위 0 위반"
    assert any(_RESOLVE_MARKER in r.message % r.args if r.args else _RESOLVE_MARKER in r.message
               for r in caplog.records), (
        f"{_RESOLVE_MARKER} 관측이 없다 — 다크런치의 카나리아가 사라지면 "
        "`resolved_krx` 를 볼 수 없어 S1 진행 판단이 불가능하다"
    )


def test_ks_enforce_low_excludes_high(monkeypatch):
    """KS-3 (§8-A S1) — `enforce_low` 는 **HIGH(보유·익일청산)를 제외**한다.

    가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 **손절 커버리지**다
    (cycle252 가 `no_feed` skip 에서 HIGH 를 byte 동일로 남긴 것과 같은 판단).

    ⚠️ 이 단계표(LOW 먼저)는 §3-E B-1(매수 축 보존)과 **긴장 관계**다 — LOW
    코호트가 곧 매수 후보이기 때문이다. `risk.py` 종목 축 게이트를 승인하지
    않기로 하면 이 테스트의 기대를 뒤집고(HIGH 먼저) 명세 §8-A 를 고쳐야 한다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce_low")
    resolve = _resolver()

    assert resolve(NO_FEED, priority="LOW") == KRX_ONLY
    assert resolve(NO_FEED, priority="HIGH") == UNIFIED, (
        "`enforce_low` 에서 HIGH 가 이동했다 — S1 은 보유 종목을 건드리지 않는다"
    )


async def test_ks_refresh_takes_effect_without_restart(monkeypatch):
    """🔴 KS-4 (§8-B) — 모드 재조회가 **반복해서** 먹힌다(once-latch 금지).

    `_load_strategy_config` 의 `_config_loaded` 처럼 프로세스당 1회로 만들면
    `off` 가 다음 재시작에만 닿는다 = 킬스위치가 아니다. 그리고 D6 때문에
    보유 중에는 그 재시작이 오지 않는다.
    """
    mod = _mode_mod()
    reset = getattr(mod, "reset_state_for_test", None)
    if callable(reset):
        reset()

    values = iter(["enforce_low", "off", "observe"])
    import src.db.system_config as sysconf

    async def _fake_get(*_a, **_kw):
        return next(values)

    key = getattr(mod, "CONFIG_KEY", "tick_channel_resolver_mode")
    assert key == "tick_channel_resolver_mode", (
        f"킬스위치 키가 {key!r} 다 — 명세 §8-B 권고는 "
        "`tick_channel_resolver_mode` 이고 운영 문서·루틴이 그 이름을 쓴다"
    )
    monkeypatch.setattr(
        sysconf, "get_tick_channel_resolver_mode", _fake_get, raising=False,
    )

    first = await mod.refresh_mode()
    assert first == "enforce_low"
    assert mod.current_mode() == "enforce_low"

    second = await mod.refresh_mode()
    assert second == "off", (
        "두 번째 재조회가 값을 갱신하지 않았다 — 프로세스당 1회 래치가 있으면 "
        "장중에 끌 수 없다(§8-B)"
    )
    assert mod.current_mode() == "off"

    third = await mod.refresh_mode()
    assert third == "observe" and mod.current_mode() == "observe"


async def test_ks_invalid_db_value_falls_back_not_crashes(monkeypatch):
    """KS-5 — DB 에 미지 값이 들어와도 예외를 던지지 않고 안전 모드로 떨어진다."""
    mod = _mode_mod()
    import src.db.system_config as sysconf

    async def _fake_get(*_a, **_kw):
        return "ENFORCE_EVERYTHING"

    monkeypatch.setattr(
        sysconf, "get_tick_channel_resolver_mode", _fake_get, raising=False,
    )
    got = await mod.refresh_mode()
    assert got in mod.VALID_MODES, f"미지 값이 그대로 통과했다: {got!r}"


# ===========================================================================
# G5 — 집계 집합화: 분모가 줄지 않는다
# ===========================================================================
def _fake_ws(subs, acked=None, label="main"):
    ws = MagicMock()
    ws._subscriptions = set(subs)
    ws._subscriptions_acked = set(acked if acked is not None else subs)
    ws._subscribed_at = {}
    ws._label = label
    ws._ws = object()
    ws._reconnect_count = 0
    return ws


def test_g5_pool_aggregation_keeps_all_three_channels(monkeypatch):
    """🔴 G5 — `H0STCNT0`/`H0NXCNT0` 종목이 집계에서 **사라지지 않는다**.

    등가 비교를 하나라도 남기면(§5-B):
      * K stale watcher 가 그 종목을 영원히 못 본다
      * `delta_unsubscribe_dropped` 가 못 봐서 **영구 슬롯 누수**
      * `already_in_pool` 미포함 → **매 5분 재SEND** = cycle252 churn 의 은폐된 부활
      * `[tick_coverage] subscribed=` **분모 감소 = 숫자만 좋아진다**(은폐 금지 위반)
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    pool._main = _fake_ws({(UNIFIED, NXT_TRUE), ("H0STCNI0", "hts")})
    pool._quotes = [
        _fake_ws({(KRX_ONLY, NO_FEED)}, label="ISA"),
        _fake_ws({(NXT_ONLY, NO_FEED_2)}, label="gold"),
    ]
    pool._ticker_to_session = {}

    subscribed = pool.get_subscribed_tickers()
    acked = pool.get_acked_tickers()

    assert subscribed == {NXT_TRUE, NO_FEED, NO_FEED_2}, (
        f"집계가 통합 채널만 센다 — actual={sorted(subscribed)}. 세 채널 전부가 "
        "`TICK_TR_IDS` 멤버십으로 잡혀야 한다"
    )
    assert acked == {NXT_TRUE, NO_FEED, NO_FEED_2}
    assert "hts" not in subscribed, "체결통보(H0STCNI0)는 시세 집계에서 제외한다"

    per_session = {s["label"]: s["subscribed"] for s in pool.get_session_status()}
    assert per_session["ISA"] == 1, (
        f"세션 슬롯 판독이 붕괴했다 — ISA sub={per_session['ISA']} (기대 1). "
        "대시보드가 20종목 세션을 `sub=0/41` 로 보여주면 운영자가 슬롯을 못 읽는다"
    )
    assert per_session["gold"] == 1


def test_g5b_single_session_aggregation_keeps_all_three_channels():
    """G5b — 세션 단독 `get_subscribed_tickers`/`get_acked_tickers` 도 같다.

    `websocket.py:503`/`:513` — `scanner.subscribe_filtered_stocks` 의
    `already_in_pool` · F1 재검증 대상 추출이 이 둘을 원천으로 쓴다.
    """
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket.__new__(KisWebSocket)
    ws._subscriptions = {(UNIFIED, NXT_TRUE), (KRX_ONLY, NO_FEED), ("H0UNMKO0", "005930")}
    ws._subscriptions_acked = {(KRX_ONLY, NO_FEED)}

    assert ws.get_subscribed_tickers() == {NXT_TRUE, NO_FEED}
    assert ws.get_acked_tickers() == {NO_FEED}


# ===========================================================================
# G3 — 이중 채널 금지
# ===========================================================================
async def test_g3_second_channel_for_same_ticker_is_refused_and_logged(monkeypatch, caplog):
    """🔴 G3 — 같은 종목에 **다른 채널** 구독 요청이 오면 무음 통과시키지 않는다.

    현행 `subscribe()` 중복 분기(`websocket_pool.py:309-329`)는 `tr_id` 를
    **보지 않는다** — 이미 구독 중인 종목에 다른 채널로 subscribe 하면 SEND 없이
    `return "main"`/`return label` 로 빠져나가고 **호출자는 성공으로 읽는다.**
    cycle221 이 종목별 VI 구독에서 정확히 이 함정을 밟아 "실질 noop" 이 됐고,
    cycle253 프로브가 `_PROBE_ALLOWED_TR_IDS` 에서 `H0UNCNT0` 를 배제한 이유도
    이것이다.

    ⚠️ **마커가 갈렸다(적대 검증 MEDIUM-1).** 이 분기는 "요청을 거부하고 현행
    채널을 유지했다" 는 기록이라 `[tick_channel_request_denied]` 이고, **정상
    운영 경로에서도 뜬다**(`enforce` 에서 보유 종목의 HIGH always-call 이 5분마다
    통합을 요청한다). §4-C 의 풀 우회 2곳(`scheduler.py:1382`·`:2728`)은
    `_ticker_to_session` 을 건드리지 않아 이 분기에 **영원히 도달하지 못하므로**,
    진짜 이중 구독은 `detect_dual_tick_channels()` 전 세션 전수 대조가 잡는다
    (`test_g3e`). 두 마커를 합치면 S1 진행 게이트 "dual 0건" 이 달성 불가가 된다.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    main = _fake_ws(set())
    main.subscribe = AsyncMock()
    main.unsubscribe = AsyncMock()
    pool._main = main
    pool._quotes = []
    pool._ticker_to_session = {}
    pool._round_robin_idx = 0
    if not hasattr(pool, "_ticker_to_tr_id"):
        pool._ticker_to_tr_id = {}
    caplog.set_level(logging.WARNING)

    await pool.subscribe(KRX_ONLY, NO_FEED, priority="LOW", bypass_limit=False)
    main.subscribe.reset_mock()

    # 같은 종목을 통합 채널로 — `scheduler.py:2728` 우회가 하는 일
    await pool.subscribe(UNIFIED, NO_FEED, priority="LOW", bypass_limit=False)

    assert pool._ticker_to_tr_id.get(NO_FEED) == KRX_ONLY, (
        "병행 dict 가 채널을 놓쳤다 — 이중 등록을 판별할 수단이 없어진다"
    )
    assert main.subscribe.await_count == 0, (
        "두 번째 채널로 실제 SEND 가 나갔다 = 같은 종목 2슬롯 + `tick_volume` "
        "last-write-wins 비결정론(§5-A 2)"
    )
    messages = [r.getMessage() for r in caplog.records]
    assert any(_DENIED_MARKER in m for m in messages), (
        f"{_DENIED_MARKER} WARNING 이 없다 — 무음 통과는 cycle221 의 '실질 noop' 재현"
    )
    assert not any(_DUAL_MARKER in m for m in messages), (
        f"요청 거부를 {_DUAL_MARKER} 로 보고했다 — 그 마커는 '실제로 두 채널에 "
        "동시 구독돼 있다' 전용이고, 정상 경로의 거부가 섞이면 S1 진행 게이트 "
        "'dual 0건' 이 달성 불가가 된다"
    )


async def test_g3b_parallel_dict_pops_with_ticker_to_session(monkeypatch):
    """G3b — `_ticker_to_tr_id` 가 `_ticker_to_session` 과 같은 시점에 pop 된다.

    한쪽만 남으면 유령 항목이 (a) 이중 채널 오탐 (b) 진짜 이중 채널 미탐을
    동시에 만든다.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    ws = _fake_ws({(KRX_ONLY, NO_FEED)})
    ws.subscribe = AsyncMock()
    ws.unsubscribe = AsyncMock()
    pool._main = ws
    pool._quotes = []
    pool._ticker_to_session = {NO_FEED: ws}
    pool._ticker_to_tr_id = {NO_FEED: KRX_ONLY}

    await pool.unsubscribe(KRX_ONLY, NO_FEED)

    assert NO_FEED not in pool._ticker_to_session
    assert NO_FEED not in pool._ticker_to_tr_id, (
        "`_ticker_to_session` 만 pop 됐다 — 병행 dict 동행 pop 누락(§5-C)"
    )


async def test_g3c_unsubscribe_all_clears_both_dicts():
    """G3c — `unsubscribe_all` 이 두 dict 를 모두 비운다(20:00 단일 해제 지점)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    ws = _fake_ws({(KRX_ONLY, NO_FEED), (UNIFIED, NXT_TRUE)})
    ws.unsubscribe = AsyncMock()
    pool._main = ws
    pool._quotes = []
    pool._ticker_to_session = {NO_FEED: ws, NXT_TRUE: ws}
    pool._ticker_to_tr_id = {NO_FEED: KRX_ONLY, NXT_TRUE: UNIFIED}

    await pool.unsubscribe_all()

    assert pool._ticker_to_session == {}
    assert pool._ticker_to_tr_id == {}, "병행 dict 가 20:00 해제 후에도 남았다"


# ===========================================================================
# G6 — grace 키 정합 (cycle252 SEND 폭주의 조용한 부활 차단)
# ===========================================================================
def _stale_watcher_env(monkeypatch, *, subscribed, ack_map, last_tick):
    """`check_and_resubscribe_stale` 최소 환경 (cycle252 테스트 하네스 답습).

    ⚠️ 시각은 **실시계 상대 오프셋**으로 만든다 — `stale_watcher_core` 의 `_dt_mod` 는
    함수 지역 import(`:163-165`)라 모듈 속성 patch 가 닿지 않는다(실측).
    """
    from src.engine import stale_watcher_core as core
    import src.realtime.websocket_pool as wp_mod
    import src.engine.scanner as scanner_mod

    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock()
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = dict(ack_map)
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", dict(last_tick))

    class _Sleep:
        async def sleep(self, _s):
            return None

    monkeypatch.setattr(core, "asyncio", _Sleep())
    return core, pool


async def test_g6_krx_channel_ticker_keeps_180s_subscribe_grace(monkeypatch):
    """🔴 G6 — `H0STCNT0` 종목의 180초 구독 grace 가 산다.

    `_subscribed_at` 는 `(tr_id, tr_key)` 키다(`websocket.py:186`). `H0STCNT0` ACK 은
    `("H0STCNT0", t)` 에 심기므로 조회 키를 `(TICK_TR_ID, t)` 로 두면
    **`nxt_false` 종목에만 grace 가 영구 miss** 되어 구독 직후 stale 판정 →
    즉시 강제 재등록 = cycle252 가 없앤 하루 ≈14,600 SEND 의 부활.

    ⚠️ **표본은 HIGH(보유) 종목이다** — LOW 라면 cycle252 no_feed skip 이 SEND 를
    먼저 삼켜 이 테스트가 **공허하게 초록**이 된다(첫 실행에서 실제로 그랬다).
    HIGH 는 그 skip 대상이 아니라 grace 만 남아 결함이 드러난다.
    """
    now = _datetime_module.datetime.now(KST)
    core, pool = _stale_watcher_env(
        monkeypatch,
        subscribed=[NO_FEED],
        # ACK 은 30초 전 — grace(180s) 안. 단 키는 **KRX 전용 채널**이다.
        ack_map={(KRX_ONLY, NO_FEED): now - _datetime_module.timedelta(seconds=30)},
        last_tick={},          # 첫 시세 미수신 = grace 판정 대상
    )
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    sched = _make_sched(positions=[NO_FEED])

    await core.check_and_resubscribe_stale(sched)

    pool.unsubscribe_in_pool.assert_not_awaited()
    pool.subscribe.assert_not_awaited()
    assert NO_FEED not in sched._stale_last_resubscribe_at, (
        "grace 안인데 강제 재등록이 나갔다 — ACK 조회 키가 그 종목의 실제 "
        "채널과 다르다(G6). cycle252 가 없앤 SEND 폭주가 조용히 돌아온다"
    )


async def test_g6b_no_feed_skip_narrows_to_the_unified_channel(monkeypatch):
    """🔴 G6b (§9-B) — cycle252 의 no_feed skip 은 **`H0UNCNT0` 구독 중인 LOW** 로 좁혀진다.

    cycle252 계약에서 `no_feed_skipped` 는 "회복 가치 0" 이었다. 리졸버가 그 종목을
    실제로 프레임이 오는 채널로 옮기면 **회복 가치가 생긴다** — skip 을 그대로 두면
    새 채널의 진짜 stale 을 영원히 못 고친다.

    표본 = LOW no_feed, `H0STCNT0` 구독, ACK 10분 전(grace 밖), 시세 0 ⇒ 재등록돼야 한다.
    """
    now = _datetime_module.datetime.now(KST)
    core, pool = _stale_watcher_env(
        monkeypatch,
        subscribed=[NO_FEED_2],
        ack_map={(KRX_ONLY, NO_FEED_2): now - _datetime_module.timedelta(seconds=600)},
        last_tick={NO_FEED_2: now - _datetime_module.timedelta(seconds=600)},
    )
    _patch_classification(monkeypatch, no_feed=(NO_FEED_2,), provenance_ok=(NO_FEED_2,))
    _set_mode(monkeypatch, "enforce")
    sched = _make_sched()

    await core.check_and_resubscribe_stale(sched)

    assert pool.subscribe.await_count == 1, (
        "`H0STCNT0` 로 옮긴 LOW 종목이 여전히 no_feed skip 에 걸린다 — 그 채널의 "
        "진짜 stale 을 영원히 못 고친다(§9-B). skip 조건을 채널로 좁혀라"
    )
    tr_id, ticker = pool.subscribe.await_args.args[:2]
    assert ticker == NO_FEED_2
    assert tr_id == KRX_ONLY, (
        f"재등록이 {tr_id!r} 로 나갔다 — 그 종목의 실제 채널({KRX_ONLY})이어야 한다"
    )


def _make_sched(*, positions=(), next_day_clear=()):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set(next_day_clear)
    sched._running = True
    sched._STALE_DETAIL_TICKER_CAP = 20

    state = MagicMock()
    state.positions = {t: MagicMock() for t in positions}
    strategy = MagicMock()
    strategy.state = state
    registry = MagicMock()
    registry.all = MagicMock(return_value=[strategy])
    sched.registry = registry
    return sched


# ===========================================================================
# G7 — 플리커: 래치 없음 · 출처 · 같은 날 재전환
# ===========================================================================
def test_g7_no_latch_ticker_returning_to_nxt_goes_back_to_unified(monkeypatch):
    """🔴 G7 ④ — 래치 금지. 이동은 **양방향**이다.

    "한 번 no_feed 면 영구 `H0STCNT0`" 로 만들면 064550 처럼 NXT 재편입한 종목을
    NXT 체결 못 받는 채널에 **영구 좌초**시킨다(09-14 07:59:09 재편입이 전환이
    양방향임을 증명했다 — 09-02 16:06 False, 09-14 True).
    """
    _set_mode(monkeypatch, "enforce")
    _patch_classification(monkeypatch, no_feed=("064550",), provenance_ok=("064550",))
    resolve = _resolver()
    assert resolve("064550", now=_pre_window()) == KRX_ONLY

    # NXT 재편입 — 레지스트리 재적재
    # 🔴 cycle294 의미 전환 — 2단계의 되돌림 대상은 통합이었다. 3단계는 통합을
    #    없앴으므로 프리 창의 되돌림 대상이 **NXT 전용**이다. 잠그는 위험(영구 좌초)
    #    은 그대로다 — 오히려 더 정확해진다(그 종목은 이제 NXT 체결을 실제로 받는다).
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=("064550",))
    assert resolve("064550", now=_pre_window()) == NXT_ONLY, (
        "래치가 걸렸다 — NXT 재편입 종목이 NXT 체결을 못 받는 채널에 좌초한다(§6-D)"
    )


def test_g7b_same_day_reflip_is_blocked_and_logged(monkeypatch, caplog):
    """G7 ③ — 같은 종목 **같은 날 재전환 금지**(값싼 백스톱, §6-D).

    출처 검사가 놓친 경로를 막는다. ⚠️ **시간 창 리터럴은 두지 않는다**(C-2) —
    오염 창의 양끝(07:45~08:08)이 일정 파생값이고 그 일정은 이미 두 번 움직였다.
    키는 KST **날짜**다.
    """
    _set_mode(monkeypatch, "enforce")
    resolve = _resolver()
    caplog.set_level(logging.WARNING)

    # ⚠️ cycle293 Green — 이 테스트는 **자기 안에서** 하루치 전환 예산을 소모한다.
    #    종전에는 같은 파일의 앞선 테스트들이 남긴 `_channel_applied`/
    #    `_channel_flipped_today` 잔재에 기대 초록이었고(모듈 전역이 테스트 사이에
    #    살아남았다), 실행 순서가 바뀌면 붉어졌다. 이제 격리 fixture 가 그 상태를
    #    비우므로 전환을 두 번 명시적으로 일으킨다.
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    assert resolve(NO_FEED, now=_pre_window()) == KRX_ONLY   # None → KRX (첫 배정, 예산 미소모)

    # 전환 1 — 프리 창의 기본값(NXT)으로 되돌아간다(래치 금지, §6-D). 이때 예산을 쓴다.
    # cycle294 의미 전환 — 되돌림 대상이 통합 → **NXT 전용**.
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NO_FEED,))
    assert resolve(NO_FEED, now=_pre_window()) == NXT_ONLY

    # 전환 2 — 같은 날 두 번째 전환. 되돌리지 않고 WARNING 으로 올린다.
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    second = resolve(NO_FEED, now=_pre_window())

    assert second == NXT_ONLY, (
        "같은 날 두 번째 전환이 통과했다 — 채널 왕복(KIS 공지 '비정상 케이스 2: "
        "무한 등록/해제')을 막는 백스톱이 없다(§6-D)"
    )
    blocked = [
        r.getMessage() for r in caplog.records
        if _FLIP_MARKER in r.getMessage() and "same_day_blocked=1" in r.getMessage()
    ]
    assert blocked, f"{_FLIP_MARKER} same_day_blocked=1 관측이 없다"


def test_g7c_provenance_unknown_does_not_move_channel(monkeypatch, caplog):
    """G7 ② — 출처 미확인 값으로는 채널을 옮기지 않고, 그 수를 남긴다.

    09-14 실측 — 07:59:01(사전 구독 발화 순간) 아직 W2 도장 상태인 행이
    **2,344/3,583(65.4%)**, 그중 실제로는 `nxt_tradable=True` 인 것이 **420**.
    NXT 지정 유니버스(602) 중 **420/602 = 69.8%** 가 그 순간 `False` 로 읽혔다.
    """
    _set_mode(monkeypatch, "enforce")
    _patch_classification(monkeypatch, no_feed=(NO_FEED, NXT_TRUE), provenance_ok=())
    resolve = _resolver()
    caplog.set_level(logging.WARNING)

    # cycle294 의미 전환 — 출처 미확인의 프리 창 착지점이 통합 → **NXT 전용**.
    # 이 방향이 W2 오염(07:59 에 65.4%)을 **자동으로 무해화한다**: 오염으로
    # `nxt_false` 로 잘못 읽힌 420종목이 정답인 NXT 로 간다(cycle294 §3-D).
    assert resolve(NO_FEED, now=_pre_window()) == NXT_ONLY
    assert resolve(NXT_TRUE, now=_pre_window()) == NXT_ONLY
    assert any(
        "[tick_channel_provenance_unknown]" in r.getMessage() for r in caplog.records
    ), (
        "[tick_channel_provenance_unknown] 관측이 없다 — W2 오염 창에 걸린 판정 "
        "수를 못 세면 07:59 사전 구독이 얼마나 미끄러졌는지 알 수 없다"
    )


# ===========================================================================
# G8 — 해제 정합: 해제가 그 종목의 실제 채널로 나간다
# ===========================================================================
async def test_g8_sell_unsubscribe_uses_the_tickers_actual_channel(monkeypatch):
    """G8 — 매도 전량 체결 뒤 구독 정리가 **그 종목의 채널**로 나간다.

    `order_engine._unsubscribe_if_no_other_strategy`(`:1949-1951`). 틀린 채널로
    해제하면 `OPSP0003 UNSUBSCRIBE ERROR not found!` 스팸 = cycle215~218 이 잡은
    그 ERROR 이고, 구 채널 튜플이 **영구 고아**로 41 을 잠식한다.

    ⚠️ 원안이 적은 `order_engine.py:1104` 는 2026-09-05 줄번호다 — HEAD 의 그
    자리는 cycle276 LLM 평가 배선(`:1080-1110`)이다.

    🔴 **하네스 결함 시정 (Green 단계, 2026-09-14)** — 이 픽스처는 `registry.all`
    만 채웠는데 `_unsubscribe_if_no_other_strategy` 는 **3중 게이트**(사이클 15-A)
    의 첫 문장에서 `registry.is_ticker_held_by_any(ticker)` 를 본다. `MagicMock`
    의 자동 자식은 **truthy** 라 그 게이트가 항상 조기 반환했고, 그래서 이 테스트는
    구현이 무엇이든 `await_count == 0` 이었다(채널 판정과 무관한 실패). 세 게이트는
    "다른 전략이 아직 보유/후보로 쓰는 종목의 시세를 끊지 않는다" 는 안전 규약이라
    **프로덕션을 느슨하게 하지 않고 픽스처를 정직하게** 만든다.
    """
    from src.engine.order_engine import OrderEngine
    import src.realtime.websocket_pool as wp_mod

    pool = MagicMock()
    pool.unsubscribe = AsyncMock()
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")

    oe = OrderEngine.__new__(OrderEngine)
    registry = MagicMock()
    registry.all = MagicMock(return_value=[])
    # 3중 게이트 전부 통과시켜야 해제 지점에 도달한다(위 docstring 참조).
    registry.is_ticker_held_by_any = MagicMock(return_value=False)
    oe.registry = registry
    oe._pending_next_day_clear_provider = lambda: set()

    await oe._unsubscribe_if_no_other_strategy(NO_FEED)

    assert pool.unsubscribe.await_count == 1, "해제 호출이 없다"
    tr_id = pool.unsubscribe.await_args.args[0]
    assert tr_id == KRX_ONLY, (
        f"해제가 {tr_id!r} 로 나갔다 — 그 종목은 {KRX_ONLY!r} 에 구독돼 있다. "
        "틀린 채널 해제 = OPSP0003 + 영구 고아 튜플(G8)"
    )


# ===========================================================================
# G4 / INV-2 · INV-4 — 보유 커버리지 불변식
# ===========================================================================
async def test_inv2_high_path_keeps_bypass_limit(monkeypatch):
    """INV-2 (G4) — HIGH(보유·익일청산) 구독의 `bypass_limit=True` 는 불변이다.

    가설이 어떤 보유 종목에 틀렸을 때 잃는 것이 손절 커버리지다. 리졸버는
    **tr_id 인자만** 바꾼다.
    """
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    pool = MagicMock()
    pool.subscribe = AsyncMock(return_value="main")
    pool.get_subscribed_tickers = MagicMock(return_value=set())
    pool.get_session_status = MagicMock(return_value=[{"label": "main"}])
    pool._subscriptions = set()
    pool.unsubscribe_all = AsyncMock()
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    monkeypatch.setattr(scanner_mod, "kis_ws_pool", pool, raising=False)
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")

    await scanner_mod.subscribe_filtered_stocks(
        [], priority_groups={"positions": [NO_FEED], "next_day_clear": [NO_FEED_2]},
    )

    calls = pool.subscribe.await_args_list
    high = [c for c in calls if c.kwargs.get("priority") == "HIGH"]
    assert len(high) == 2, f"HIGH 구독 2건이 아니다 — actual={len(high)}"
    for c in high:
        assert c.kwargs.get("bypass_limit") is True, (
            "HIGH 구독에서 `bypass_limit=True` 가 사라졌다 (INV-2)"
        )


def test_inv4_held_ticker_with_failed_classification_is_surfaced(monkeypatch, caplog):
    """INV-4 — 판정 실패 + **보유**는 사람에게 올린다(결정 카드 D-3).

    fail-open 은 "모르면 blind 유지" 라서 보수적이지 않다. 보유 종목에서 판정이
    실패하면 그 종목은 계속 blind 이고, 그 사실이 로그에 없으면 아무도 모른다.
    """
    _set_mode(monkeypatch, "enforce")
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=())
    resolve = _resolver()
    caplog.set_level(logging.WARNING)

    # 🔴 cycle294 의미 전환 — 판정 실패의 착지점이 통합 → **프리 창 NXT**(§3-B L2).
    #    잠그는 것은 착지점이 아니라 **무음이 아닐 것**이다. 그리고 판정 불가라는
    #    상태는 속성축을 실제로 보는 구간(= 프리 창)에서만 존재한다 — KRX 창은
    #    속성축을 아예 보지 않으므로 거기서 "모른다" 는 채널을 하나도 바꾸지 않는다.
    got = resolve(NO_FEED, priority="HIGH", now=_pre_window())

    assert got == NXT_ONLY
    messages = [r.getMessage() for r in caplog.records]
    assert any("[no_feed_held]" in m or "[tick_channel_provenance_unknown]" in m
               for m in messages), (
        "보유 종목의 판정 실패가 무음이다 — INV-4 위반. 그 종목은 손절을 "
        "REST 폴에만 의존하고, REST 폴은 donchian·kojiro 두 전략만 덮는다"
        "(BFB/VCP 가 잡으면 종일 손절 평가 0)"
    )


def test_config_marker_is_the_deploy_canary(monkeypatch, caplog):
    """§9-A — `[tick_channel_config]` 부팅 1행 = 배포 반영 카나리아.

    `mode=` · `resolved_krx=N` · `resolved_unified=M` · `provenance_ok=P` ·
    `provenance_unknown=Q`. 이 행이 없으면 배포가 실제로 반영됐는지 알 수 없다.
    """
    scanner = _scanner()
    emit = getattr(scanner, "emit_tick_channel_config", None)
    if emit is None:
        pytest.fail(
            f"{_CONFIG_MARKER} 를 내는 진입점(`scanner.emit_tick_channel_config`) 미존재 "
            "(§9-A 카나리아)"
        )
    _set_mode(monkeypatch, "observe")
    _patch_classification(
        monkeypatch, no_feed=(NO_FEED, NO_FEED_2), provenance_ok=(NO_FEED,),
    )
    caplog.set_level(logging.INFO)

    emit([NO_FEED, NO_FEED_2, NXT_TRUE])

    line = next(
        (r.getMessage() for r in caplog.records if _CONFIG_MARKER in r.getMessage()),
        None,
    )
    assert line is not None, f"{_CONFIG_MARKER} 미발화"
    for field in ("mode=", "resolved_krx=", "resolved_unified=",
                  "provenance_ok=", "provenance_unknown="):
        assert field in line, f"{_CONFIG_MARKER} 에 `{field}` 누락 — actual={line!r}"


# ===========================================================================
# G9 — 🔴 매수 축 보존 (§3-E B-1)
# ===========================================================================
_TICK_BUY_STRATEGIES = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "bull_flag_breakout",
    "vcp_breakout",
)


class _SpyStrategy(StrategyBase):
    """`check_buy_signal` / `check_exit_signal` 호출 추적 스파이 (cycle273e 하네스 답습)."""

    def __init__(self, strategy_id: str):
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id, name=strategy_id, weight=1.0, enabled=True,
                params={"tradable_boards": ["main"]},
            )
        )
        self.buy_calls: list[str] = []
        self.exit_calls: list[str] = []
        self.state.total_investment = 100_000_000

    async def prepare(self):
        pass

    def get_scanned_tickers(self):
        return []

    def check_buy_signal(self, ticker, current_price, open_price):
        self.buy_calls.append(ticker)
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        self.exit_calls.append(ticker)
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


def _route_channel(monkeypatch, **mapping):
    """풀의 병행 dict `_ticker_to_tr_id` 를 주입한다 = "이 종목은 실제로 이 채널에 있다".

    cycle293 Green — 매수 축 게이트의 술어가 **리졸버 재호출**이 아니라 **구독
    사실**이다. 둘이 갈리는 순간(킬스위치 `off` · 모드 하강 · `nxt_tradable`
    복귀 · 출처 후퇴) 프레임은 계속 전용 채널로 오는데 게이트만 풀려 5전략의
    매수가 그 코호트에 열린다 — 그래서 테스트도 구독 사실을 세운다.
    """
    from src.realtime.websocket_pool import kis_ws_pool

    monkeypatch.setattr(kis_ws_pool, "_ticker_to_tr_id", dict(mapping), raising=False)


def _stamp_cohort(ticker: str, *, priority: str = "LOW", now=None) -> str:
    """구독 발사 경로(`tick_tr_id_for`)를 그대로 타서 **코호트 스탬프**를 심는다.

    🔴 cycle294 의미 전환 — 매수 축 게이트의 술어가 채널(`_ticker_to_tr_id`)이
    아니라 **코호트**(`scanner.tick_buy_cohort_blocked`)다. 3단계는 통합 채널을
    없애고 `nxt_true` 까지 전 종목을 전용 채널로 보내므로, 채널 축 술어는 전
    종목에 참이 되어 5전략 매수를 통째로 죽인다(cycle294 §6-C).

    스탬프를 심는 자리는 프로덕션에 **하나뿐**이다 — `tick_tr_id_for` 안,
    `_apply_channel_decision` 직전. 그래서 테스트도 그 함수를 탄다(dict 를 직접
    주입하면 "스탬프가 실제 구독과 1:1 인가" 라는 계약을 건너뛴다).
    """
    return _resolver()(ticker, priority=priority, now=now or _pre_window())


@pytest.fixture
def _risk_env(monkeypatch):
    """`risk.on_tick` 을 결정론적으로 만드는 최소 환경."""
    import src.engine.scanner as scanner_mod
    from src.engine import risk as risk_mod
    from src.engine.session import MarketBoard, session_tracker

    _route_channel(monkeypatch)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NO_FEED: 10_000, NXT_TRUE: 70_000})
    monkeypatch.setattr(scanner_mod, "ticker_prices", {})
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {})
    pinned = _datetime_module.datetime(2026, 9, 14, 10, 30, 0, tzinfo=KST)
    monkeypatch.setattr(risk_mod, "_now_kst", lambda: pinned, raising=False)
    yield


def _risk_manager(strategies):
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    for s in strategies:
        registry.register(s)

    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    return RiskManager(registry, oe), oe


@pytest.mark.parametrize("strategy_id", _TICK_BUY_STRATEGIES)
async def test_g9_cohort_is_buy_evaluated_after_gate_removal(
    monkeypatch, _risk_env, strategy_id,
):
    """🔴 G9 (cycle336 이 뒤집음) — 코호트도 **매수 평가를 받는다**.

    지금 `nxt_false` 종목은 프레임 0 이라 이 5전략의 매수 평가에서 **구조적으로
    배제**돼 있다(30일 실측: 5전략의 `nxt_false` 매수 0건 / donchian 8건 ·
    kojiro 3건 — 그 둘은 `_TICK_BUY_EVAL_SKIP_STRATEGIES` 로 이미 skip 이고
    REST 폴이 매수를 담당한다). 채널을 열면 시총 1,000억↑ 유니버스의 **64%** 가
    매수 평가에 새로 노출된다 = **매매 행위 변경이고 승인받지 않았다.**

    특히 BFB/VCP 는 `tick_volume.get_observed_acml_vol()` → `None` →
    `vol_gate_no_data` **fail-closed** 로 닫혀 있는데, 실측 `acml_vol` 이 들어오면
    그 게이트가 **열린다**. 게다가 `H0STCNT0` 의 `ACML_VOL` 스코프가
    `H0UNCNT0` 과 같은지 **아직 모른다**(U-3) — 좁아지면 게이트가 조용히 더
    엄격해진다. B-2(매수 개방)는 별도 승인 + `domain-consult` + U-3 대조 1일이
    선행 조건이다.

    ## 🔴 계약이 뒤집힌 이유 (cycle336, 사용자 결정 2026-09-21)

    위 서술은 **cycle293 시점의 계약**이고 지금은 거짓이다. 게이트가 막던 것은
    「`nxt_tradable=False`」 코호트인데, 사이클 156 Q0 가 이미 그 기준을
    **「주문 시점 분기용으로만」** 으로 폐기했다(`strategies/volatility_breakout.py:450`
    · `long_tail_volatility.py:501` · `bull_flag_breakout.py:709`). cycle293 게이트는
    그 폐기된 기준을 **다른 계층에서** 되살린 것이었다.

    `ACML_VOL` 스코프 우려(U-3)도 해소됐다 — 이 코호트는 08:00~20:00 `H0STCNT0`
    고정(하루 전환 0회)이고 비교 대상 `avg_volume_20` 도 KRX 일봉이라 **KRX↔KRX 정합**이다.

    🔴 **이 단언이 0 이면 게이트가 부활한 것이다.** 이 저장소에서 그 자리는
    `risk.on_tick` 의 `check_buy_signal` 바로 앞이고, 되살리는 순간 구독 158 중
    **77(49%)** 의 매수 평가가 다시 사라진다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    _stamp_cohort(NO_FEED)      # 구독 발사 = 코호트 확정(cycle294 §6-C)
    spy = _SpyStrategy(strategy_id)
    risk, oe = _risk_manager([spy])

    await risk.on_tick(NO_FEED, current_price=11_000, open_price=10_000,
                       change_rate=10.0, acml_vol=5_000_000)

    assert spy.buy_calls == [NO_FEED], (
        f"{strategy_id} 가 `nxt_false` 종목({NO_FEED})의 매수 평가에 **도달하지 못했다** — "
        "cycle336 이 걷은 코호트 게이트가 되살아났거나, 채널 축 회귀로 프레임이 "
        "끊겼다. 둘은 다른 결함이다: 게이트 부활이면 다른 전략도 함께 0 이고, "
        "채널 회귀면 이 종목만 0 이다"
    )
    # 🔴 **판정은 살아 있어야 한다** — 게이트를 걷은 것이지 계측기를 지운 것이 아니다.
    #    이 값이 False 가 되면 `[tick_buy_gate]` 집계와 `_note_pre_window_krx_frame`
    #    게이팅이 함께 죽어, 개방의 효과를 D+1 에 셀 분모가 사라진다.
    from src.engine.scanner import tick_buy_cohort_blocked
    assert tick_buy_cohort_blocked(NO_FEED) is True, (
        "코호트 판정까지 함께 지워졌다 — 관측 분모가 사라진다"
    )


async def test_g9_exit_axis_still_evaluated_for_no_feed(monkeypatch, _risk_env):
    """G9 대칭 — 매수 축 게이트는 **청산보다 뒤**다(깨지면 손절이 죽는다).

    이 사이클의 목적 자체가 청산 축 복구다. 게이트를 청산 앞으로 옮기는
    뮤테이션을 KILL 한다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    _stamp_cohort(NO_FEED)
    spy = _SpyStrategy("vcp_breakout")
    spy.state.positions[NO_FEED] = Position(
        ticker=NO_FEED, buy_price=10_000, quantity=10,
        order_no="O-1", strategy_id="vcp_breakout",
    )
    risk, _oe = _risk_manager([spy])

    await risk.on_tick(NO_FEED, current_price=9_000, open_price=10_000, change_rate=-10.0)

    assert spy.exit_calls == [NO_FEED], (
        "보유 중 `nxt_false` 종목의 청산 평가가 사라졌다 — 이 사이클이 고치려던 "
        "바로 그것이다(16:00~20:00 에 손절을 평가할 수 있는 주체는 WS 틱 단독)"
    )
    assert spy.buy_calls == []


async def test_g9_nxt_true_ticker_buy_eval_unchanged(monkeypatch, _risk_env):
    """G9 회귀 — 종목 축 게이트가 `nxt_true` 종목을 잡아먹지 않는다.

    게이트가 넓으면 오늘 정상으로 매수되던 종목의 매수가 멈춘다 = 반대 방향
    행위 변경.
    """
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NXT_TRUE: 70_000})
    _patch_classification(
        monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,),
        classified=(NO_FEED, NXT_TRUE),
    )
    _set_mode(monkeypatch, "enforce")
    # 🔴 cycle294 절대 규칙 5 의 정면 증명 — 둘 다 **전용 채널**로 구독되지만
    #    (3단계는 통합을 없앴다) 코호트는 갈린다: `nxt_false` 만 닫히고
    #    `nxt_true` 는 열린 채로 남는다. 채널 축 술어로 되돌리는 뮤테이션은
    #    여기서 `buy_calls == []` 가 되어 죽는다.
    stamped_no_feed = _stamp_cohort(NO_FEED)
    stamped_nxt_true = _stamp_cohort(NXT_TRUE)
    assert stamped_no_feed in (KRX_ONLY, NXT_ONLY) and stamped_no_feed != UNIFIED
    assert stamped_nxt_true in (KRX_ONLY, NXT_ONLY) and stamped_nxt_true != UNIFIED
    spy = _SpyStrategy("volatility_breakout")
    risk, _oe = _risk_manager([spy])

    await risk.on_tick(NXT_TRUE, current_price=77_000, open_price=70_000, change_rate=10.0)

    assert spy.buy_calls == [NXT_TRUE], (
        "종목 축 게이트가 `nxt_true` 종목까지 막았다 — 오늘 매수되던 코호트의 "
        "행위가 바뀐다. 3단계에서 이 오분류는 5전략 매수를 **통째로** 죽인다"
    )


async def test_g9b_opening_a_channel_now_opens_the_buy_axis(monkeypatch, _risk_env):
    """🔴 G9b (cycle336 이 뒤집음) — `채널이 열렸다 ⟹ 매수 평가도 열린다`.

    `test_g9_*` 는 `risk.py` 종목 축 게이트(선택지 가)를 전제하지만, 오케스트레이션
    지시는 `risk.py` diff 0 도 함께 요구한다. 이 테스트는 둘 중 어느 수단을 골라도
    성립하는 형태로 같은 위험을 막는다:

    cycle293 은 이 자리에서 「채널을 열어도 매수는 닫는다」를 잠갔다. cycle336 이
    그 게이트를 걷었으므로 계약이 정확히 **반대**가 된다 — 채널이 열려 프레임이
    오면 매수 평가도 열린다. 🔴 단언을 지우지 않고 **뒤집는** 이유 = 지우면
    「채널은 열렸는데 매수는 안 열리는」 상태(= 게이트 부활 또는 채널 축 회귀)를
    아무도 안 보게 된다.

    ⚠️ LOW 채널이 통합으로 남는 판본(선택지 나)에서는 프레임이 0 이라 이 단언이
    성립할 수 없다 — 그 경우는 조기 반환으로 남겨 둔다(통합 채널은 cycle294 가
    없앴으므로 현행에서는 도달하지 않는다).
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce_low")
    resolve = _resolver()

    low_channel = resolve(NO_FEED, priority="LOW")
    if low_channel == UNIFIED:
        # 선택지 (나) — 매수 후보 코호트의 채널이 오늘과 같다 = 프레임 0 = 구조적 보존.
        return

    spy = _SpyStrategy("vcp_breakout")
    risk, oe = _risk_manager([spy])
    await risk.on_tick(NO_FEED, current_price=11_000, open_price=10_000,
                       change_rate=10.0, acml_vol=5_000_000)

    assert spy.buy_calls == [NO_FEED], (
        f"LOW 후보 {NO_FEED} 를 {low_channel} 로 열었는데 매수 평가가 도달하지 못했다 — "
        "cycle336 이 걷은 코호트 게이트가 되살아났다"
    )


# ===========================================================================
# G9c — 🔴 게이트는 「판정」이 아니라 「구독 사실」을 본다 (적대 검증 CRITICAL)
# ===========================================================================
@pytest.mark.parametrize(
    ("case", "after"),
    [
        # 킬스위치 `off` — §8-B 가 지정한 롤백 수단. 그런데 `off` 는 이미 전용
        # 채널에 올라간 구독을 **되돌리지 않는다**(다음 `_boot` 까지 남는다).
        ("kill_switch_off", lambda mp, set_mode, patch_cls: set_mode(mp, "off")),
        # 모드 하강 — 같은 이유.
        ("mode_downgrade_observe", lambda mp, set_mode, patch_cls: set_mode(mp, "observe")),
        # `nxt_tradable` 복귀(064550 계열) — 판정이 통합으로 뒤집힌다.
        ("nxt_tradable_returned", lambda mp, set_mode, patch_cls: patch_cls(
            mp, no_feed=(), provenance_ok=(NO_FEED,))),
        # 출처 후퇴(W2 도장이 raw 를 덮는 창) — 판정 불가로 떨어진다.
        ("provenance_regressed", lambda mp, set_mode, patch_cls: patch_cls(
            mp, no_feed=(NO_FEED,), provenance_ok=())),
    ],
)
async def test_g9c_gate_survives_resolver_divergence(monkeypatch, _risk_env, case, after):
    """🔴 G9c — **코호트 스탬프**는 판정이 통합으로 돌아가도 그날 내내 살아남는다.

    cycle336 이 매수 차단을 걷었으므로 이 케이스가 지키는 것은 「매수가 닫힌다」가
    아니라 **「스탬프가 리졸버 재판정에 흔들리지 않는다」**로 옮겨간다. 그 성질이
    여전히 필요한 이유 = 스탬프가 `[tick_buy_gate]` 집계와
    `_note_pre_window_krx_frame` 게이팅의 **분모**이고, 킬스위치를 누르거나
    `nxt_tradable` 이 장중에 뒤집혔다고 그날 계측이 반으로 갈라지면 D+1 판독이 깨진다.

    적대 검증이 찾았던 CRITICAL(술어가 `tick_tr_id_for()` 재호출이면 네 경로에서
    조용히 풀린다)은 **그대로 유효하다** — 대상이 「매수 차단」에서 「계측 분모」로
    바뀌었을 뿐이다. 🔴 스탬프는 **구독 사실**을 따르지 리졸버 재판정을 따르지 않는다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    _stamp_cohort(NO_FEED)      # 구독 발사 = 그날 코호트 확정

    after(monkeypatch, _set_mode, _patch_classification)

    from src.engine.scanner import tick_buy_cohort_blocked

    assert tick_buy_cohort_blocked(NO_FEED) is True, (
        f"{case}: 판정이 통합으로 돌아갔다고 코호트 스탬프가 풀렸다 — 그러나 그 종목은 "
        f"아직 {KRX_ONLY} 에 구독돼 있어 프레임이 계속 온다. 스탬프 술어가 "
        "구독 사실이 아니라 리졸버 재호출이다(적대 검증 CRITICAL). 풀리면 그날 "
        "`[tick_buy_gate]` 분모가 갈라져 개방 효과를 셀 수 없다"
    )

    # 매수는 cycle336 이후 **열려 있다** — 스탬프 생존과 매수 개방은 이제 독립이다.
    spy = _SpyStrategy("vcp_breakout")
    risk, _oe = _risk_manager([spy])
    await risk.on_tick(NO_FEED, current_price=11_000, open_price=10_000,
                       change_rate=10.0, acml_vol=5_000_000)
    assert spy.buy_calls == [NO_FEED], f"{case}: 매수 평가가 막혔다 — 게이트 부활"


async def test_g9d_gate_is_pure_no_flip_budget_consumed(monkeypatch, _risk_env):
    """G9d — 틱 경로의 게이트가 §6-D **하루 1회 전환 예산**을 먹지 않는다.

    `tick_tr_id_for` 는 순수 함수가 아니다(`_channel_applied`/`_channel_flipped_today`
    를 변이한다). 그것을 매 틱 부르면 구독이 하나도 바뀌지 않았는데 그날의 재전환이
    조용히 차단되고 `[tick_channel_flip] same_day_blocked=1` 이 폭주한다.
    """
    scanner = _scanner()
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    _stamp_cohort(NO_FEED)
    # 구독 경로가 남긴 이력을 스냅샷한다 — 틱 경로가 그것을 **더 건드리면** 안 된다.
    applied_before = dict(scanner._channel_applied)
    flipped_before = dict(scanner._channel_flipped_today)

    spy = _SpyStrategy("vcp_breakout")
    risk, _oe = _risk_manager([spy])
    for _ in range(5):
        await risk.on_tick(NO_FEED, current_price=11_000, open_price=10_000,
                           change_rate=10.0, acml_vol=5_000_000)

    assert scanner._channel_applied == applied_before, (
        "틱 경로의 게이트가 채널 적용 이력을 바꿨다 — 구독 경로가 아닌 호출자가 "
        f"§6-D 전환 예산을 소모한다: {scanner._channel_applied} != {applied_before}"
    )
    assert scanner._channel_flipped_today == flipped_before


async def test_g9e_unrouted_ticker_keeps_today_behaviour(monkeypatch, _risk_env):
    """G9e — **스탬프가 없으면 열어 둔다**(fail-open 방향, cycle294 §6-D).

    cycle293 은 이 자리를 "풀 라우팅 기록 부재 = 오늘과 동일" 로 읽었다. 3단계의
    술어는 코호트이고, 스탬프는 구독을 실제로 발사한 종목에만 심긴다 — 그러므로
    이 테스트는 "아직 분류·구독되지 않은 종목" 을 잰다.

    🔴 방향의 근거(§6-D 비대칭) — **닫힘 오류는 레지스트리 전체 실패 한 번으로
    전 종목에 동시에 일어난다**(상관된 실패 = 그날 5전략 매수 0). 열림 오류는
    종목별로 독립이다. 오케스트레이션 절대 규칙 5 가 이 사이클 최대 위험으로
    지목한 것이 전자다. 그 상태는 조용하지 않다 — `[tick_buy_gate] unstamped=`
    가 하루 1행 WARNING 으로 규모를 남긴다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")
    _route_channel(monkeypatch)   # 라우팅 비어 있음
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NXT_TRUE: 70_000})
    spy = _SpyStrategy("volatility_breakout")
    risk, _oe = _risk_manager([spy])
    await risk.on_tick(NXT_TRUE, current_price=77_000, open_price=70_000, change_rate=10.0)

    assert spy.buy_calls == [NXT_TRUE]


# ===========================================================================
# G3b — 🔴 이중 채널은 **전 세션 전수 대조**로 잡는다 (적대 검증 CRITICAL)
# ===========================================================================
async def test_g3e_pool_bypass_dual_subscription_is_detected(monkeypatch, caplog):
    """🔴 G3b — `kis_ws.subscribe` **직접 호출**(풀 우회)이 만든 이중 채널을 잡는다.

    §4-C 는 `[tick_channel_dual_detected]` 를 "`scheduler.py:1382`(익일청산 시가
    수신)·`:2728`(스윙 매수 직후) 풀 우회 2곳을 드러내는 **유일한 수단**" 으로
    지정한다. 그 두 줄은 `_ticker_to_session` 을 건드리지 않으므로
    `WebsocketPool.subscribe` 의 중복 분기에 **영원히 도달하지 못한다** — 종전
    검출기는 자기가 지킨다고 적은 것을 지키지 못했다.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    main = _fake_ws(set(), label="main")
    main.subscribe = AsyncMock()
    main.unsubscribe = AsyncMock()
    pool._main = main
    pool._quotes = []
    pool._ticker_to_session = {}
    pool._ticker_to_tr_id = {}
    pool._round_robin_idx = 0

    # 1) 풀 경유 구독 — 전용 채널 (`main.subscribe` 는 AsyncMock 이라 튜플은 직접 심는다)
    await pool.subscribe(KRX_ONLY, NO_FEED, priority="LOW")
    main._subscriptions.add((KRX_ONLY, NO_FEED))
    # 2) 풀 **우회** 직접 구독 — scheduler.py:1382/:2728 이 하는 일
    main._subscriptions.add((UNIFIED, NO_FEED))

    caplog.set_level(logging.WARNING)
    found = pool.detect_dual_tick_channels()

    assert NO_FEED in found, (
        "전 세션 전수 대조가 풀 우회 이중 채널을 못 봤다 — §4-C 가 이 관측에 맡긴 "
        "임무가 통째로 공허해진다"
    )
    assert sorted(found[NO_FEED]) == sorted([KRX_ONLY, UNIFIED])
    assert any(_DUAL_MARKER in r.getMessage() for r in caplog.records)


async def test_g3f_dual_detector_is_silent_when_healthy(monkeypatch, caplog):
    """G3c — 정상 상태(종목당 채널 1개)에서는 침묵한다(오탐 0)."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    main = _fake_ws({(UNIFIED, "000001"), (KRX_ONLY, "000002")}, label="main")
    pool._main = main
    pool._quotes = []
    pool._ticker_to_tr_id = {}

    caplog.set_level(logging.WARNING)
    assert pool.detect_dual_tick_channels() == {}
    assert not any(_DUAL_MARKER in r.getMessage() for r in caplog.records)


async def test_g3g_probe_tuple_is_not_a_dual_channel(monkeypatch, caplog):
    """G3d — 진단 프로브(cycle253)는 이중 채널로 잡지 않는다.

    프로브가 이중으로 잡히면 §7 저녁 측정이 매 사이클 WARNING 을 낳고, 운영자가
    진짜 이중 구독과 구별할 수 없게 된다.
    """
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket_pool import WebsocketPool

    ws_mod.reset_probe_exclusions()
    pool = WebsocketPool.__new__(WebsocketPool)
    main = _fake_ws({(UNIFIED, NO_FEED), (KRX_ONLY, NO_FEED)}, label="main")
    pool._main = main
    pool._quotes = []
    pool._ticker_to_tr_id = {}
    ws_mod.register_probe_exclusion(KRX_ONLY, NO_FEED)
    try:
        caplog.set_level(logging.WARNING)
        assert pool.detect_dual_tick_channels() == {}
    finally:
        ws_mod.reset_probe_exclusions()


# ===========================================================================
# G10 — 적대 검증 ESCAPED 뮤테이션 봉인 (M13 / M18 / M19 / M1c)
# ===========================================================================
async def test_g10_unsubscribe_self_corrects_to_tracked_channel():
    """M13 — `unsubscribe` 가 **추적된 실제 채널**로 해제한다(호출자가 틀려도).

    틀린 채널로 UNSUBSCRIBE 하면 KIS 가 `OPSP0003 UNSUBSCRIBE ERROR not found!`
    를 돌려주고 구 채널 튜플이 **영구 고아**로 41 슬롯을 잠식한다.
    """
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool.__new__(WebsocketPool)
    ws = _fake_ws({(KRX_ONLY, NO_FEED)})
    ws.unsubscribe = AsyncMock()
    pool._main = ws
    pool._quotes = []
    pool._ticker_to_session = {NO_FEED: ws}
    pool._ticker_to_tr_id = {NO_FEED: KRX_ONLY}

    await pool.unsubscribe(UNIFIED, NO_FEED)   # 호출자가 통합으로 잘못 요청

    assert ws.unsubscribe.await_args.args[0] == KRX_ONLY, (
        "추적된 채널이 아니라 호출자 인자로 해제했다 — OPSP0003 + 영구 고아 튜플"
    )


def test_g10b_actual_or_desired_prefers_the_subscription_fact(monkeypatch):
    """M18 — `_actual_or_desired_tick_tr_id` 는 **실제 구독 채널**을 1순위로 쓴다.

    §3-C "살아 있는 구독의 전환 경로를 만들지 않는다" 의 핵심 장치다. 리졸버
    판정만 쓰면 장중에 모드를 올린 순간 stale 재등록이 곧 전환이 된다.
    """
    from src.engine import stale_watcher_core as swc

    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode(monkeypatch, "enforce")

    pool = MagicMock()
    pool._ticker_to_tr_id = {NO_FEED: UNIFIED}   # 사실 = 아직 통합
    got = swc._actual_or_desired_tick_tr_id(pool, NO_FEED, "LOW")

    assert got == UNIFIED, (
        "리졸버 판정이 구독 사실을 이겼다 — unsub/sub 쌍이 서로 다른 채널을 써서 "
        "그 자체가 장중 전환이 된다(§3-C 위반)"
    )


def test_g10c_probe_tuples_never_leak_into_tick_views(monkeypatch):
    """M19 — 프로브 튜플은 TICK 집계(세션·풀 양쪽)에서 빠진다.

    새면 5분 `_scan_loop` delta 가 `current - new_set` 으로 프로브를 해제해
    §7 저녁 측정을 끊는다.
    """
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket_pool import WebsocketPool

    ws_mod.reset_probe_exclusions()
    real = ws_mod.KisWebSocket.__new__(ws_mod.KisWebSocket)
    real._subscriptions = {(UNIFIED, "000001"), (KRX_ONLY, "900001")}
    real._subscriptions_acked = set(real._subscriptions)
    try:
        assert real.get_subscribed_tickers() == {"000001", "900001"}
        ws_mod.register_probe_exclusion(KRX_ONLY, "900001")
        assert real.get_subscribed_tickers() == {"000001"}
        assert real.get_acked_tickers() == {"000001"}

        pool = WebsocketPool.__new__(WebsocketPool)
        pool._main = real
        pool._quotes = []
        assert pool.get_subscribed_tickers() == {"000001"}
        assert pool.get_acked_tickers() == {"000001"}
        row = next(r for r in pool.get_session_status() if r["label"] == "main")
        assert row["tickers"]["subscribed"] == ["000001"]
        assert row["tickers"]["acked"] == ["000001"], (
            "M1c — `acked` 만 등가 비교로 되돌리는 위장 뮤테이션이 산다"
        )
        assert row["subscribed"] == 1 and row["acked"] == 1
    finally:
        ws_mod.reset_probe_exclusions()


def test_g10d_session_status_acked_keeps_all_three_channels():
    """M1c — `get_session_status().acked` 도 세 채널 합집합이다(`subscribed` 만 보면 샌다)."""
    from src.realtime.websocket_pool import WebsocketPool

    subs = {(UNIFIED, "000001"), (KRX_ONLY, "000002"), ("H0NXCNT0", "000003")}
    pool = WebsocketPool.__new__(WebsocketPool)
    pool._main = _fake_ws(subs)
    pool._quotes = []
    row = next(r for r in pool.get_session_status() if r["label"] == "main")
    assert row["tickers"]["acked"] == ["000001", "000002", "000003"]
    assert row["tickers"]["subscribed"] == ["000001", "000002", "000003"]
    assert row["subscribed"] == 3 and row["acked"] == 3


# ===========================================================================
# G11 — 프로브 제외 등록의 **수명** (적대 검증 HIGH)
# ===========================================================================
async def test_g11_unsubscribe_all_clears_probe_exclusions():
    """G11 — 20:00 `unsubscribe_all` 이 프로브 제외 등록을 회수한다.

    종전 주석은 이 집합의 수명이 "20:00 `unsubscribe_all` 과 같다" 고 적었지만
    **그 함수는 집합을 비우지 않았다**. 남은 `(tr_id, ticker)` 는 cycle293 이
    같은 채널을 실 구독에 쓰기 시작한 뒤 **라이브 구독을 은폐**한다.
    """
    from src.realtime import websocket as ws_mod
    from src.realtime.websocket_pool import WebsocketPool

    ws_mod.reset_probe_exclusions()
    ws_mod.register_probe_exclusion(KRX_ONLY, NO_FEED)
    pool = WebsocketPool.__new__(WebsocketPool)
    ws = _fake_ws({(KRX_ONLY, NO_FEED)})
    ws.unsubscribe = AsyncMock()
    pool._main = ws
    pool._quotes = []
    pool._ticker_to_session = {NO_FEED: ws}
    pool._ticker_to_tr_id = {NO_FEED: KRX_ONLY}

    await pool.unsubscribe_all()

    assert ws_mod.PROBE_EXCLUDED_TUPLES == set(), (
        "20:00 해제가 프로브 제외 등록을 남겼다 — 다음 사이클의 실 구독이 그 "
        "튜플과 같은 식별자라 집계에서 조용히 사라진다"
    )


def test_g11b_probe_exclusion_self_expires_on_day_change(monkeypatch):
    """G11b — 전날 잔존 제외 항목은 **판정 시점에 스스로 회수**된다.

    회수 지점이 `_evict_stale_probes`(다음 POST 진입 시에만) 하나뿐이면 프로브를
    stop 없이 둔 종목이 프로세스 수명 내내 집계 밖에 남는다.
    """
    from src.realtime import websocket as ws_mod

    ws_mod.reset_probe_exclusions()
    try:
        ws_mod.register_probe_exclusion(KRX_ONLY, NO_FEED)
        assert ws_mod.is_probe_excluded(KRX_ONLY, NO_FEED) is True
        monkeypatch.setattr(ws_mod, "_probe_exclusion_today", lambda: "2099-01-01")
        assert ws_mod.is_probe_excluded(KRX_ONLY, NO_FEED) is False
        assert (KRX_ONLY, NO_FEED) not in ws_mod.PROBE_EXCLUDED_TUPLES
    finally:
        ws_mod.reset_probe_exclusions()

