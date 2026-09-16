"""cycle294 Red (3단계 · 시간축 전환 · **통합 채널 소멸**) — 행위 가드.

명세 = `_workspace/red/cycle294_stage3_time_axis_spec.md`
AST 자매 = `tests/unit/ast/test_cycle294_ast_stage3.py`
선행 = cycle292(장운영 구독 leaf) + cycle293(2단계 속성축 배관) — 둘 다 미커밋 워크트리.

## 종착지 (재론 금지)

`H0UNCNT0` 구독을 **0** 으로 만든다. 09-15 07:45 부팅부터 `H0STCNT0`(KRX 전용) +
`H0NXCNT0`(NXT 전용) 2채널이다.

```
08:00~08:50  프리장        → H0NXCNT0
08:50~09:00  전환 창        → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
09:00~20:00  정규장+애프터  → H0STCNT0   (전환 0회, 연속)
```

09-14 16:39~16:41 라이브 실측 — `000815`(nxt_false)·`005385`(nxt_false)·
`000660`(**nxt_true**) 전부 `H0STCNT0` 에서 KRX 애프터마켓 체결 수신. 즉
`H0STCNT0` 은 종목 속성과 무관하게 09:00~20:00 을 **연속**으로 덮는다.

## 이 파일이 잠그는 것

| ID | 절대 규칙 | 잠그는 것 |
|----|-----------|-----------|
| B1~B7 | 1·2 | 🔴 **통합 반환 0건**(24h×1분 격자) · 구간 배치 · 경계 양쪽 · 표 유효일자 |
| C1~C4 | 1 | fail-open 3층 — L1 표 실패→KRX · L2 속성 실패→프리 창 NXT · L3 `off`→통합 |
| D1~D8 | 🔴 5 | **매수 축 코호트** — `nxt_true` 는 매수를 **받고** `nxt_false` 는 안 받는다 |
| E1~E8 | 2·3 | 전환 창 게이트 · **make-before-break** · 세션 고정 · 무공백 · 전환 스위치 |
| F1~F5 | 4 | 자동 원복 — 표본 하한 · 교차 확인 · 속성축 존중 · 그날 재시도 0 |
| G1~G3 | 1 | 레거시 재라우팅 스코프(통합만) |
| H1 | 8 | 킬스위치 `off` = **배포 전과 동일** |

## 🔴 이 사이클 최대 위험 — `test_d3`

3단계는 **모든** 종목을 전용 채널로 보낸다. cycle293 의 매수 축 술어(「전용
채널에 구독돼 있는가」)를 그대로 두면 **전 종목 참**이 되어 momentum·
volatility_breakout·long_tail_volatility·bull_flag_breakout·vcp_breakout 5전략의
틱 매수가 통째로 죽는다(그 5전략은 틱이 **유일** 매수 경로다).

`test_d3` 은 100종목 전원 전용 채널에서 `check_buy_signal` 호출 집합이
`nxt_true` 60종목과 **정확히** 같기를 요구한다 — cycle293 술어로 되돌리는
뮤테이션은 **0종목**이 되어 RED 다.

## ⚠️ cycle293 자매 파일 **20건**이 의미 전환된다 (삭제 금지 · 실측 목록)

3단계는 cycle293 이 세운 두 계약을 **의도적으로 뒤집는다** — (a) fail-open 이
통합이 아니라 시각 기반 기본값이고 (b) 매수 축 술어가 채널이 아니라 코호트다.
그래서 충실한 구현을 얹으면 아래 20건이 붉어진다(프로토타입 실측):

    ast/test_cycle293_ast_channel_resolver.py
      · test_a1b_risk_py_pin_is_the_open_decision      ← `risk.py` 핀 이동(§10-B 1)
      · test_a18_buy_gate_reads_the_subscription_fact_not_the_resolver
                                                        ← **본문 교체**(§6-E ⚠️)
    engine/test_cycle293_channel_resolver.py
      · test_g2_fail_open_always_returns_current_channel  ×4  ← §3-B 로 기대 전환
      · test_g1_no_feed_with_authoritative_source_goes_krx    ← 시각축이 섞인다
      · test_g7 / test_g7b / test_g7c / test_inv4            ← 같은 이유
      · test_g9_ticker_axis_gate_blocks_buy_eval_for_no_feed ×5
      · test_g9c_gate_survives_resolver_divergence           ×4
                                                        ← 셋업이 `_ticker_to_tr_id`
                                                          주입이라 스탬프가 없다.
                                                          `tick_tr_id_for` 경유로
                                                          바꾸면 그대로 성립한다

🔴 **이 20건을 삭제해 초록을 만들지 마라.** cycle293 이 잰 위험(유니버스 64% 신규
노출 · 출처 미확인 420종목 오배치 · `off` 가 매수를 여는 경로)은 3단계에서도
그대로 살아 있고, 술어만 바뀐다. 기대를 옮기고 **왜 옮겼는지**를 각 docstring 에
남겨라 — 지우면 다음 사람이 옛 계약을 되살린다.

## 🔴 공허 가드 금지 — 모듈·인자 부재는 SKIP 이 아니라 FAIL

신규 leaf 2파일과 `now` 주입구가 없으면 헬퍼가 **FAIL** 한다. `hasattr` 로 감싸
조용히 통과시키면 구현이 끝날 때까지 초록이다.
"""

from __future__ import annotations

import datetime as _dt
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

KST = _dt.timezone(_dt.timedelta(hours=9))

UNIFIED = "H0UNCNT0"
KRX_ONLY = "H0STCNT0"
NXT_ONLY = "H0NXCNT0"

#: 09-15(화) — 09-14 제도 변경(KRX 애프터마켓 16:00~20:00) 시행 **이후** 첫 영업일.
DAY = _dt.date(2026, 9, 15)
#: 09-12(토) 이전 = K6 미유효 · K7(시간외 단일가) 유효. 표 유효일자 검증용.
DAY_BEFORE_REFORM = _dt.date(2026, 9, 11)

NXT_TRUE = "005930"       # 삼성전자 — nxt_tradable=True
NXT_TRUE_2 = "000660"     # SK하이닉스 — 09-14 16:39 프로브 실측 표본
NO_FEED = "000815"        # 09-14 16:39 프로브 실측 nxt_false 표본
NO_FEED_2 = "005385"      # 09-14 16:39 프로브 실측 nxt_false 표본
UNKNOWN = "999999"        # 레지스트리 미적재

#: 틱이 **유일** 매수 경로인 5전략. donchian/kojiro 는 전략 축 skip + REST 폴 담당.
_TICK_BUY_STRATEGIES = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "bull_flag_breakout",
    "vcp_breakout",
)

_MARKER_AUTO_REVERT = "[tick_channel_auto_revert]"
_MARKER_WINDOW_MISSED = "[tick_channel_switch_window_missed]"
_MARKER_LEGACY_REROUTE = "[tick_channel_legacy_reroute]"


def _at(h: int, m: int, s: int = 0, *, day: _dt.date = DAY) -> _dt.datetime:
    return _dt.datetime.combine(day, _dt.time(h, m, s), tzinfo=KST)


# ===========================================================================
# 헬퍼 — 부재는 SKIP 이 아니라 FAIL
# ===========================================================================
def _scanner():
    from src.engine import scanner

    return scanner


def _mode_mod():
    from src.engine import tick_channel_mode

    return tick_channel_mode


def _registry():
    from src.engine import no_feed_registry

    return no_feed_registry


def _clock():
    try:
        from src.engine import tick_channel_clock  # type: ignore[attr-defined]
    except ImportError as exc:
        pytest.fail(
            "§1-D — 시각축 leaf `src/engine/tick_channel_clock.py` 미존재. "
            "`clock_channel(now, *, offset_secs) -> (tr_id, reason)` 를 순수·"
            "never-raise 로 넣고, 경계 셋은 `market_state.get_market_table(on_date)` "
            f"공개 API 에서만 파생하라(시각 리터럴 0건). import 실패: {exc}"
        )
    return tick_channel_clock


def _switch_mod():
    try:
        from src.engine import tick_channel_switch  # type: ignore[attr-defined]
    except ImportError as exc:
        pytest.fail(
            "§4·§5 — 전환 leaf `src/engine/tick_channel_switch.py` 미존재. "
            "`async run_switch_cycle(scheduler, pool, *, now)` 를 never-raise 로 "
            "넣고 `stale_watcher_core.check_and_resubscribe_stale`(120초)에서 "
            f"부르라. import 실패: {exc}"
        )
    return tick_channel_switch


def _clock_channel(now, *, offset_secs: int = 300) -> tuple[str, str]:
    fn = getattr(_clock(), "clock_channel", None)
    if fn is None:
        pytest.fail("§1-D — `tick_channel_clock.clock_channel` 미존재")
    try:
        return fn(now, offset_secs=offset_secs)
    except TypeError as exc:
        pytest.fail(
            "§1-C — `clock_channel(now, *, offset_secs)` 시그니처가 아니다. 전환 "
            f"시각은 **파라미터**여야 한다(리터럴 금지). {exc}"
        )


def _desired(ticker: str, now, *, priority: str = "LOW") -> str:
    """`scanner.desired_tick_tr_id(ticker, *, priority, now)` — 순수 판정."""
    fn = _scanner().desired_tick_tr_id
    try:
        return fn(ticker, priority=priority, now=now)
    except TypeError as exc:
        pytest.fail(
            "§1-E — `desired_tick_tr_id` 가 `now` 를 받지 않는다. 시각축을 합성하려면 "
            "소비 지점 4곳 전부에 `now=None` 주입구가 필요하다(기본 인자에 "
            f"`datetime.now()` 를 넣지 말 것 — 모듈 로드 시각 동결). {exc}"
        )


def _applied(ticker: str, now, *, priority: str = "LOW") -> str:
    """`scanner.tick_tr_id_for(...)` — 적용형(구독 발사 시점). 코호트 스탬프가 여기서 심긴다."""
    fn = _scanner().tick_tr_id_for
    try:
        return fn(ticker, priority=priority, now=now)
    except TypeError as exc:
        pytest.fail(f"§1-E — `tick_tr_id_for` 가 `now` 를 받지 않는다. {exc}")


def _cohort_blocked(ticker: str) -> bool:
    fn = getattr(_scanner(), "tick_buy_cohort_blocked", None)
    if fn is None:
        pytest.fail(
            "§6-C — `scanner.tick_buy_cohort_blocked(ticker)` 미존재. 매수 축 술어를 "
            "채널에서 **코호트**로 바꾸는 것이 §6 의 전부다"
        )
    return bool(fn(ticker))


def _set_mode(mode: str) -> None:
    _mode_mod().set_mode_for_test(mode)


def _set_switch_params(**kwargs) -> None:
    """전환 파라미터 4키 테스트 seam (§9-E)."""
    mod = _mode_mod()
    setter = getattr(mod, "set_switch_params_for_test", None)
    if not callable(setter):
        pytest.fail(
            "§9-E — `tick_channel_mode.set_switch_params_for_test(*, switch_enabled=, "
            "offset_secs=, ack_timeout_secs=, revert_probe_secs=)` 테스트 seam 미존재. "
            "네 키는 `system_config` 축이고 전략 `DEFAULT_PARAMS` 로 새면 안 된다"
        )
    setter(**kwargs)


def _patch_classification(monkeypatch, *, no_feed=(), provenance_ok=(), classified=None,
                          is_classified_raises=None, is_no_feed_raises=None):
    """`no_feed_registry` 3판정 주입 (cycle293 헬퍼 답습)."""
    reg = _registry()
    nf, prov = set(no_feed), set(provenance_ok)
    known = set(classified) if classified is not None else (nf | prov)

    def _is_classified(t: str) -> bool:
        if is_classified_raises is not None:
            raise is_classified_raises
        return t in known

    def _is_no_feed(t: str) -> bool:
        if is_no_feed_raises is not None:
            raise is_no_feed_raises
        return t in nf

    monkeypatch.setattr(reg, "is_classified", _is_classified)
    monkeypatch.setattr(reg, "is_no_feed", _is_no_feed)
    monkeypatch.setattr(reg, "is_provenance_ok", lambda t: t in prov)
    return reg


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """레지스트리·모드·채널 판정 이력·코호트 스탬프를 테스트마다 초기화한다."""
    reg = _registry()
    reset_reg = getattr(reg, "reset_state_for_test", None)
    mode = _mode_mod()
    reset_mode = getattr(mode, "reset_state_for_test", None)
    for fn in (reset_reg, reset_mode):
        if callable(fn):
            fn()
    reset_switch = getattr(_maybe_switch_mod(), "reset_state_for_test", None)
    if callable(reset_switch):
        reset_switch()
    yield
    for fn in (reset_reg, reset_mode):
        if callable(fn):
            fn()
    reset_switch = getattr(_maybe_switch_mod(), "reset_state_for_test", None)
    if callable(reset_switch):
        reset_switch()


def _maybe_switch_mod():
    """전환 leaf 가 아직 없을 수 있는 **픽스처 전용** 관대 접근(테스트 본문은 `_switch_mod`)."""
    try:
        from src.engine import tick_channel_switch  # type: ignore[attr-defined]

        return tick_channel_switch
    except ImportError:
        return object()


# ===========================================================================
# B1~B7 (절대 규칙 1·2) — 🔴 통합 반환 0건 · 구간 배치
# ===========================================================================
@pytest.mark.parametrize(
    ("cohort", "kwargs"),
    [
        ("nxt_true", {"no_feed": (), "provenance_ok": (NXT_TRUE,), "classified": (NXT_TRUE,)}),
        ("nxt_false", {"no_feed": (NXT_TRUE,), "provenance_ok": (NXT_TRUE,)}),
        ("unclassified", {"no_feed": (), "provenance_ok": (), "classified": ()}),
    ],
)
def test_b1_unified_is_never_returned_over_the_whole_day(monkeypatch, cohort, kwargs):
    """🔴 B1 (절대 규칙 1 · G-294-2) — 정상 경로에서 통합 채널을 **절대 반환하지 않는다.**

    24시간 × 1분 격자 1,440점 × 3코호트 전수. 단 하나라도 `H0UNCNT0` 가 나오면
    그날 그 종목은 통합 채널에 구독되고, 그러면 "통합 구독 0" 이 성립하지 않는다.

    ⚠️ 유일한 예외는 킬스위치 `off`(§3-B L3)이고 그것은 `test_c3` 가 따로 잠근다.
    """
    _patch_classification(monkeypatch, **kwargs)
    _set_mode("enforce")

    offenders: list[str] = []
    for minute in range(24 * 60):
        now = _dt.datetime.combine(
            DAY, _dt.time(minute // 60, minute % 60), tzinfo=KST,
        )
        got = _desired(NXT_TRUE, now)
        if got not in (KRX_ONLY, NXT_ONLY):
            offenders.append(f"{now:%H:%M}→{got}")

    assert not offenders, (
        f"[{cohort}] 통합 채널(또는 미지 값)이 {len(offenders)}개 시각에서 반환됐다. "
        f"표본 {offenders[:8]} — 3단계의 목표는 `{UNIFIED}` 의 **소멸**이다(절대 규칙 1). "
        "fail-open 은 '구독을 안 한다' 가 아니라 **시각 기반 기본값**(프리 창 NXT / "
        "그 외 KRX)으로 간다"
    )


@pytest.mark.parametrize("hh_mm_ss", [(8, 0, 0), (8, 20, 0), (8, 49, 59), (8, 50, 0), (8, 54, 59)])
def test_b2_pre_window_goes_to_nxt(monkeypatch, hh_mm_ss):
    """B2 (구간표) — 08:00~08:55 프리 창은 `H0NXCNT0` 다.

    그 시각 NXT(N1 프리마켓 08:00~08:50)만 연속 체결을 싣는다. KRX 는 K1 시가
    단일가(08:20~09:00)라 09:00 일괄 체결 전까지 체결이 0 이다.
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    h, m, s = hh_mm_ss

    assert _desired(NXT_TRUE, _at(h, m, s)) == NXT_ONLY, (
        f"{h:02d}:{m:02d}:{s:02d} 에 `nxt_true` 종목이 NXT 전용 채널에 있지 않다 — "
        "프리장 체결의 유일 출처를 놓친다(INV-1)"
    )


@pytest.mark.parametrize(
    "hh_mm_ss",
    [(8, 55, 0), (9, 0, 0), (9, 0, 1), (12, 0, 0), (15, 25, 0), (16, 30, 0), (19, 59, 59)],
)
def test_b3_krx_window_goes_to_krx(monkeypatch, hh_mm_ss):
    """B3 (구간표) — 08:55~20:00 은 `H0STCNT0` 다. 전환 0회, 연속.

    09-14 16:39~16:41 라이브 실측이 `H0STCNT0` 의 **종목 속성 무관 수신**을
    확정했다. 15:34 NXT 애프터 전환은 **넣지 않는다** — cycle287 이 애프터 주문을
    KRX 로 보내므로 그 구간에 KRX 가격을 보는 것이 정합이다(평가 가격 = 체결 가격).
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    h, m, s = hh_mm_ss

    assert _desired(NXT_TRUE, _at(h, m, s)) == KRX_ONLY, (
        f"{h:02d}:{m:02d}:{s:02d} 에 KRX 전용 채널이 아니다 — 정규장+애프터는 "
        "전환 0회의 연속 구간이다(§0)"
    )


def test_b4_the_switch_boundary_flips_exactly_once(monkeypatch):
    """B4 (§1-C) — 전환 시각 경계 **양쪽**. offset 은 파라미터다.

    `switch_at = clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`,
    기본 offset 300초 ⇒ 08:50 + 300s = 08:55. 경계 직전은 NXT, 경계 당시는 KRX.
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")

    assert _clock_channel(_at(8, 54, 59), offset_secs=300)[0] == NXT_ONLY
    assert _clock_channel(_at(8, 55, 0), offset_secs=300)[0] == KRX_ONLY

    # offset 을 0 으로 내리면 프리장 종료(08:50)와 동시에 전환된다.
    assert _clock_channel(_at(8, 50, 0), offset_secs=0)[0] == KRX_ONLY
    assert _clock_channel(_at(8, 49, 59), offset_secs=0)[0] == NXT_ONLY

    # 🔴 클램프 — offset 이 창(600초)을 넘어도 정규장 개장을 넘지 않는다.
    assert _clock_channel(_at(8, 59, 59), offset_secs=99_999)[0] == NXT_ONLY
    assert _clock_channel(_at(9, 0, 0), offset_secs=99_999)[0] == KRX_ONLY, (
        "🔴 offset 클램프 실패 — 09:00 정규장 개장 이후에도 NXT 를 본다면 그 종목은 "
        "KRX 정규장 체결을 통째로 놓친다(§1-C clamp 상한 = krx_regular_open)"
    )


def test_b5_pre_window_nxt_false_stays_on_krx(monkeypatch):
    """B5 (§2-C 채택안 (가)) — 프리 창의 `nxt_false` 는 **KRX 유지**다.

    08:00~08:50 에 그 종목은 NXT 에서 거래되지 않고 KRX 는 단일가라 **어느
    채널이든 프레임 0** 이다(§2-A). 세 선택지의 손절 커버리지가 동일하게 0 이므로
    남는 축은 전환 비용이고, (가)만 **전환 0회** + 09:00:00 첫 체결을 전환 없이
    받는다. 부수 효과로 08:55 전환 폭이 ~40% 줄어든다(= 이 사이클 유일한 새 위험의 크기).
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")

    assert _desired(NO_FEED, _at(8, 10)) == KRX_ONLY, (
        "프리 창의 `nxt_false` 가 NXT 로 갔다 — 그 종목은 NXT 에서 거래되지 않으므로 "
        "이득이 0 이고 08:55 전환 대상만 늘어난다(§2-B (다))"
    )
    assert _desired(NO_FEED, _at(9, 30)) == KRX_ONLY


def test_b6_after_the_continuous_end_it_is_still_never_unified(monkeypatch):
    """B6 (절대 규칙 1) — 20:00 이후·07:59 에도 통합으로 떨어지지 않는다.

    20:00 `unsubscribe_all()` 로 구독이 0 이 되지만, 그 전후에 판정이 불리는
    경로(07:59 `TIME_PRESUBSCRIBE` 사전 구독 포함)가 통합을 돌려주면 그 순간
    통합 구독이 부활한다.
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")

    assert _desired(NXT_TRUE, _at(7, 59)) == NXT_ONLY, (
        "07:59 사전 구독이 NXT 전용이 아니다 — 08:00 프리장 첫 틱을 놓친다(§8-B)"
    )
    for hh, mm in ((20, 0), (20, 30), (23, 59)):
        assert _desired(NXT_TRUE, _at(hh, mm)) in (KRX_ONLY, NXT_ONLY)


def test_b7_table_effective_dates_decide_the_continuous_end(monkeypatch):
    """B7 (§1-A · §1-B) — 경계는 **날짜 해석을 마친 표**에서 나온다.

    K6(애프터마켓 16:00~20:00)은 `effective_from=2026-09-14`, K7(시간외 단일가
    16:00~18:00)은 `effective_to=2026-09-12` 다. 날짜를 빼고 표를 읽으면 09-11 에
    20:00 이 나오거나(거짓) 18:00 이 섞인다(`periodic_auction` 이라 `match_kind`
    필터가 이중으로 막는다).
    """
    clock = _clock()
    windows = getattr(clock, "_windows", None)
    if windows is None:
        pytest.fail(
            "§1-D — `tick_channel_clock._windows(on_date)` 미존재. "
            "`(krx_regular_open, nxt_pre_end, krx_continuous_end)` 를 "
            "`get_market_table(on_date)` 에서 파생하라"
        )

    krx_open, nxt_end, krx_end = windows(DAY)
    assert krx_open == _dt.time(9, 0)
    assert nxt_end == _dt.time(8, 50)
    assert krx_end == _dt.time(20, 0), (
        f"09-15 의 `krx_continuous_end` 가 {krx_end} 다 — K6(애프터마켓 20:00)을 "
        "`match_kind==\"continuous\"` 로 집지 못했다(§1-B)"
    )

    _krx_open_b, _nxt_end_b, krx_end_before = windows(DAY_BEFORE_REFORM)
    assert krx_end_before == _dt.time(15, 20), (
        f"09-11 의 `krx_continuous_end` 가 {krx_end_before} 다 — K6 는 그날 "
        "`effective_from` 밖이라 15:20(K3)이어야 하고, K7(18:00)은 "
        "`periodic_auction` 이라 애초에 걸리면 안 된다(§1-B ⚠️)"
    )


# ===========================================================================
# C1~C4 (절대 규칙 1 · §3-B) — 새 fail-open 3층
# ===========================================================================
def test_c1_clock_failure_falls_back_to_krx(monkeypatch):
    """🔴 C1 (§3-B L1) — 시각축 실패 → **KRX**.

    근거 셋: ① 09-14 16:39 실측이 `H0STCNT0` 의 종목 속성 무관 수신을 확정했다
    ② 구독 수명 07:59~20:00 중 KRX 창이 11시간 5분 = **92%**(NXT 유일 출처는
    08:00~08:50 의 50분뿐) ③ `H0STCNT0` 은 **모의(VTS) 지원** TR_ID 다
    (`H0UNCNT0`/`H0NXCNT0` 는 미지원) — 폴백이 KRX 여야 VTS 환경이 산다.

    🔴 어떤 경우에도 "구독을 안 한다" 로 가지 않는다(P0-1 재현 방향).
    """
    from src.engine import market_state

    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")

    def _boom(*_a, **_kw):
        raise RuntimeError("market table exploded")

    monkeypatch.setattr(market_state, "get_market_table", _boom)

    got, reason = _clock_channel(_at(8, 10))
    assert got == KRX_ONLY, (
        f"표 조회 실패 시 {got!r} 로 떨어졌다 — L1 fail-open 은 KRX 다(§3-B). "
        "통합으로 가면 절대 규칙 1 위반이고, 미구독으로 가면 P0-1 재현이다"
    )
    assert isinstance(reason, str) and reason, "reason 라벨이 비었다 — 판독 불가"

    # 종목 축 진입점도 같은 방향으로 떨어진다.
    assert _desired(NXT_TRUE, _at(8, 10)) in (KRX_ONLY, NXT_ONLY)


def test_c2_registry_failure_in_the_pre_window_falls_back_to_nxt(monkeypatch):
    """🔴 C2 (§3-B L2) — 속성축 실패 → **프리 창에서 NXT**. 비대칭이 방향을 정한다.

    모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 **새로 잃는다**
    (오늘은 통합 채널이 그것을 준다 ⇒ INV-1 위반). NXT 로 보내면 진짜
    `nxt_false` 가 프레임 0 이 되는데 **그 구간엔 그 종목의 시장이 없어 잃을 것이
    0** 이다(§2-A). ⇒ 잃을 수 있는 쪽을 보존한다.

    부수 효과(§3-D) — cycle293 이 출처 검사로 막던 **W2 도장 오염**(07:59 에
    2,344/3,583 = 65.4%, 그중 420종목이 실제로는 `nxt_true`)의 **실패 비용이
    3단계에서 0** 이 된다. 오염된 420종목이 정답인 NXT 로 간다.
    """
    _set_mode("enforce")

    # (가) 레지스트리 예외
    _patch_classification(monkeypatch, no_feed=(NXT_TRUE,), provenance_ok=(NXT_TRUE,),
                          is_classified_raises=RuntimeError("registry down"))
    assert _desired(NXT_TRUE, _at(8, 10)) == NXT_ONLY, (
        "레지스트리 예외인데 프리 창에서 KRX 로 갔다 — 진짜 `nxt_true` 의 프리장 "
        "체결을 새로 잃는다(§3-B L2)"
    )

    # (나) 미분류
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(), classified=())
    assert _desired(UNKNOWN, _at(8, 10)) == NXT_ONLY

    # (다) 출처 미확인 = W2 도장 창의 그 420종목
    _patch_classification(monkeypatch, no_feed=(NXT_TRUE,), provenance_ok=())
    assert _desired(NXT_TRUE, _at(8, 10)) == NXT_ONLY, (
        "출처 미확인 종목이 프리 창에서 KRX 로 갔다 — W2 도장(07:45~08:08)에 걸린 "
        "≈420종목이 NXT 체결을 못 받는 채널로 간다(§3-D)"
    )

    # KRX 창에서는 L2 층이 존재하지 않는다 — 속성축을 아예 보지 않는다.
    assert _desired(UNKNOWN, _at(10, 0)) == KRX_ONLY


def test_c3_kill_switch_off_is_the_only_unified_path(monkeypatch):
    """C3 (§3-B L3 · 절대 규칙 8) — `off` 는 **유일한** 통합 반환 경로다.

    `off` 의 정의 = "오늘 배포 전과 동일". 롤백이 코드 revert 여선 안 된다 —
    그 재배포는 D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지)이 막는다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("off")

    for hh, mm in ((7, 59), (8, 10), (8, 56), (9, 30), (16, 30), (19, 59)):
        for ticker in (NXT_TRUE, NO_FEED, UNKNOWN):
            assert _desired(ticker, _at(hh, mm)) == UNIFIED, (
                f"`off` 인데 {hh:02d}:{mm:02d} {ticker} 가 전용 채널로 갔다 — "
                "`off` = 배포 전과 동일이어야 한다"
            )


def test_c4_naive_or_missing_now_still_resolves_to_a_dedicated_channel(monkeypatch):
    """C4 (§3-C) — tz-naive `now` 도 예외 없이 전용 채널로 떨어진다.

    "시각도 모를 때" 의 답은 L1 과 같다(= KRX). **never-raise** 가 계약이다 —
    여기서 던지면 `subscribe_filtered_stocks` 가 그 사이클의 구독을 통째로 잃는다.
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")

    naive = _dt.datetime(2026, 9, 15, 10, 0, 0)   # tz 없음
    got, _reason = _clock_channel(naive)
    assert got in (KRX_ONLY, NXT_ONLY), f"tz-naive now 에서 {got!r} 가 나왔다"

    # `now` 미지정(None) = 현재 시각. 값은 실행 시각에 따르지만 도메인은 고정이다.
    assert _scanner().desired_tick_tr_id(NXT_TRUE, priority="LOW") in (KRX_ONLY, NXT_ONLY)


# ===========================================================================
# D1~D8 (🔴 절대 규칙 5 · §6) — 매수 축 코호트
# ===========================================================================
class _SpyStrategy(StrategyBase):
    """`check_buy_signal` / `check_exit_signal` 호출 추적 스파이 (cycle293 하네스 답습)."""

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


@pytest.fixture
def _risk_env(monkeypatch):
    """`risk.on_tick` 을 결정론적으로 만드는 최소 환경 (KRX 정규장 10:30 고정)."""
    import src.engine.scanner as scanner_mod
    from src.engine import risk as risk_mod
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))
    monkeypatch.setattr(scanner_mod, "ticker_prices", {})
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {})
    pinned = _at(10, 30)
    monkeypatch.setattr(risk_mod, "_now_kst", lambda: pinned, raising=False)
    yield pinned


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
async def test_d1_nxt_true_keeps_buy_eval_on_a_dedicated_channel(
    monkeypatch, _risk_env, strategy_id,
):
    """🔴 D1 (절대 규칙 5 정면 증명) — 전용 채널인데 매수는 **열려 있다.**

    `nxt_true` 종목은 **어제도 통합 채널에서 프레임을 받았고** 5전략의 매수 평가를
    이미 받고 있었다. 3단계는 그들에게 **채널만 바꾼다** ⇒ 매수 평가가 계속돼야
    한다. 이 단언을 빠뜨리면 내일 아침 전 전략 매수 0 을 못 잡는다.
    """
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NXT_TRUE: 70_000})
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")

    # 구독 발사 = 코호트 스탬프가 심기는 유일한 자리(§6-C).
    assert _applied(NXT_TRUE, _at(10, 30)) == KRX_ONLY
    assert _cohort_blocked(NXT_TRUE) is False, (
        "🔴 `nxt_true` 종목이 무송출 코호트로 스탬프됐다 — 그 종목은 어제도 프레임을 "
        "받았다. 술어가 아직 **채널**을 읽고 있다(§6-A)"
    )

    spy = _SpyStrategy(strategy_id)
    risk, oe = _risk_manager([spy])
    await risk.on_tick(NXT_TRUE, current_price=77_000, open_price=70_000,
                       change_rate=10.0, acml_vol=5_000_000)

    assert spy.buy_calls == [NXT_TRUE], (
        f"🔴 {strategy_id} 가 `nxt_true` 종목의 매수 평가에 도달하지 못했다. "
        "3단계는 전 종목을 전용 채널로 보내므로 cycle293 술어(「전용 채널인가」)를 "
        "그대로 두면 **5전략 매수가 통째로 0** 이 된다 — 이 사이클 최대 위험이다"
    )
    assert oe.execute_buy.await_count == 0   # Signal.NONE


async def test_d2_no_feed_cohort_is_still_blocked_but_exit_is_not(monkeypatch, _risk_env):
    """D2 (§6-B) — `nxt_false` 코호트는 여전히 매수 skip, **청산은 평가된다.**

    cycle293 이 막으려던 것은 「오늘까지 통합 채널에서 프레임이 **0건**이던 종목에
    프레임이 새로 들어와 5전략의 매수 평가가 유니버스 64% 를 새로 잡는 것」이다.
    그 코호트는 `nxt_tradable=False` ∧ 출처 권위 확인이고, 3단계도 그대로 닫는다.
    """
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NO_FEED: 10_000})
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")

    assert _applied(NO_FEED, _at(10, 30)) == KRX_ONLY
    assert _cohort_blocked(NO_FEED) is True, (
        "`nxt_false` ∧ 출처 권위 종목이 코호트로 스탬프되지 않았다 — 유니버스 64% 가 "
        "5전략 매수 평가에 새로 노출된다(미승인 매매 행위 변경)"
    )

    spy = _SpyStrategy("vcp_breakout")
    spy.state.positions[NO_FEED] = Position(
        ticker=NO_FEED, buy_price=10_000, quantity=10,
        order_no="O-1", strategy_id="vcp_breakout",
    )
    risk, _oe = _risk_manager([spy])
    await risk.on_tick(NO_FEED, current_price=9_000, open_price=10_000, change_rate=-10.0)

    assert spy.buy_calls == []
    assert spy.exit_calls == [NO_FEED], (
        "보유 중 `nxt_false` 종목의 **청산** 평가가 사라졌다 — 이 사이클 전체가 "
        "고치려던 바로 그것이다(16:00~20:00 손절 평가 주체는 WS 틱 단독)"
    )


async def test_d3_all_dedicated_does_not_kill_all_buys(monkeypatch, _risk_env):
    """🔴 D3 — **이 사이클 최대 위험의 직접 재현.**

    100종목 전원 전용 채널(3단계의 정상 상태). `check_buy_signal` 이 불린 종목
    집합이 `nxt_true` 60종목과 **정확히** 같아야 한다.

    🔴 뮤테이션: 술어를 cycle293 것(`applied in DEDICATED_TICK_TR_IDS`)으로
    되돌리면 **0종목** → RED. 이 한 케이스가 회귀를 영구 봉인한다.
    """
    import src.engine.scanner as scanner_mod

    nxt_true = [f"1{i:05d}" for i in range(60)]
    no_feed = [f"2{i:05d}" for i in range(40)]
    all_tickers = nxt_true + no_feed

    monkeypatch.setattr(
        scanner_mod, "ticker_prev_close", {t: 10_000 for t in all_tickers},
    )
    _patch_classification(
        monkeypatch, no_feed=tuple(no_feed), provenance_ok=tuple(all_tickers),
        classified=tuple(all_tickers),
    )
    _set_mode("enforce")

    channels = {t: _applied(t, _at(10, 30)) for t in all_tickers}
    assert set(channels.values()) == {KRX_ONLY}, (
        f"전 종목 전용 채널(KRX)이 아니다 — 실제 {sorted(set(channels.values()))}. "
        "3단계의 정상 상태를 재현하지 못하면 이 테스트는 위험을 재지 못한다"
    )

    spy = _SpyStrategy("momentum")
    risk, _oe = _risk_manager([spy])
    for ticker in all_tickers:
        await risk.on_tick(ticker, current_price=11_000, open_price=10_000,
                           change_rate=10.0, acml_vol=5_000_000)

    assert set(spy.buy_calls) == set(nxt_true), (
        f"🔴 매수 평가를 받은 종목이 {len(set(spy.buy_calls))}개다(기대 60). "
        "0개면 술어가 아직 **채널**이고(= 내일 아침 5전략 매수 0), 100개면 게이트가 "
        "통째로 사라진 것이다(= 유니버스 64% 신규 노출, 미승인 행위 변경)"
    )


def test_d4_unstamped_ticker_is_open(monkeypatch):
    """D4 (§6-D) — 스탬프 **부재는 열어 둔다**(오늘과 동일).

    비대칭이 방향을 정한다: 닫힘 오류는 **레지스트리 전체 실패 한 번**으로 전
    종목에 동시에 일어나고(상관된 실패 = 전 전략 매수 0), 열림 오류는 종목별로
    독립이다. 절대 규칙 5 가 이 사이클 최대 위험으로 지목한 것이 전자다.
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(), classified=())
    _set_mode("enforce")

    _applied(UNKNOWN, _at(10, 30))
    assert _cohort_blocked(UNKNOWN) is False, (
        "미분류 종목이 매수 축에서 닫혔다 — 레지스트리가 차가운 첫 사이클에 "
        "**전 종목이 동시에** 닫히면 그날 5전략 매수가 0 이 된다(§6-D)"
    )


def test_d5_provenance_unknown_is_open(monkeypatch):
    """D5 (§6-C) — 출처 미확인(`no_feed=True` ∧ `provenance_ok=False`)도 **열어 둔다.**

    W2 도장 창(07:45~08:08)에 걸린 종목은 `nxt_tradable=False` 가 KRX raw 도장이라
    그 값을 근거로 매수를 닫으면 **진짜 `nxt_true` 420종목의 매수**까지 막는다.
    """
    _patch_classification(monkeypatch, no_feed=(NXT_TRUE,), provenance_ok=())
    _set_mode("enforce")

    _applied(NXT_TRUE, _at(10, 30))
    assert _cohort_blocked(NXT_TRUE) is False


async def test_d6_kill_switch_off_does_not_open_the_cohort(monkeypatch, _risk_env):
    """🔴 D6 (§6-C 🔴 · 금기 9) — `off` 가 매수를 **열지 않는다.**

    cycle293 적대 검증 CRITICAL 의 승계 — `off` 는 이미 전용 채널에 올라간 구독을
    **되돌리지 않으므로**(§9-B), 게이트가 모드를 보면 「사고 중에 누르는 안전
    조치가 5전략의 매수를 그 코호트에 열어 준다」.

    ⚠️ 판정은 **두 층 모두** 잰다 — `scanner` 술어(스탬프)와 `risk` 게이트(실제
    매수 분기). 술어만 재면 게이트 쪽에 `if current_mode() == off: return False`
    를 넣는 뮤테이션이 살아남는다(실측 ESCAPED → 이 케이스로 봉인).
    """
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {NO_FEED: 10_000})
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")
    _applied(NO_FEED, _at(10, 30))
    assert _cohort_blocked(NO_FEED) is True

    _set_mode("off")
    assert _cohort_blocked(NO_FEED) is True, (
        "🔴 킬스위치 `off` 가 무송출 코호트의 매수를 **열었다**. 스탬프는 모드와 "
        "무관하게 구독 사실을 따라야 한다(§6-C)"
    )

    spy = _SpyStrategy("momentum")
    risk, _oe = _risk_manager([spy])
    await risk.on_tick(NO_FEED, current_price=11_000, open_price=10_000,
                       change_rate=10.0, acml_vol=5_000_000)

    assert spy.buy_calls == [], (
        "🔴 `off` 를 누른 뒤 무송출 코호트의 매수 평가가 열렸다 — 사고 중에 누르는 "
        "안전 조치가 유니버스 64% 를 5전략 매수에 여는 것이 된다(금기 9)"
    )


def test_d7_stamp_is_a_one_way_latch_within_the_day(monkeypatch):
    """D7 (§6-C) — 스탬프는 **하루 단방향(닫힘 우세)** 래치다.

    매수를 **여는** 방향의 하루 중 변화는 다음 날로 미룬다. 수명이 하루라
    cycle293 §6-D 가 금지한 '영구 좌초 래치' 와 다르다(그건 채널 축이고 이건
    매수 축이다).
    """
    scanner = _scanner()
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")
    _applied(NO_FEED, _at(10, 30))
    assert _cohort_blocked(NO_FEED) is True

    # 하루 중 레지스트리가 뒤집혀도 그날은 닫힌 채 유지된다.
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    _applied(NO_FEED, _at(11, 0))
    assert _cohort_blocked(NO_FEED) is True, (
        "스탬프가 하루 중에 **열림 방향**으로 뒤집혔다 — 단방향 래치가 아니다(§6-C)"
    )

    # 날짜 경계에서는 비워진다(영구 좌초 금지).
    scanner.reset_tick_channel_state_for_test()
    _applied(NO_FEED, _at(11, 5))
    assert _cohort_blocked(NO_FEED) is False, (
        "날짜 경계(또는 리셋) 후에도 스탬프가 남는다 — 064550 처럼 NXT 에 재편입한 "
        "종목의 매수가 영원히 막힌다(cycle293 §6-D 금지 사항)"
    )


def test_d8_gate_does_not_mutate_the_switch_budget(monkeypatch):
    """D8 (§6-C) — 게이트는 **읽기 전용**이다.

    `risk.on_tick` 이 틱마다 부르므로 여기서 상태를 변이하면 관측이 §6-D 하루 1회
    전환 예산(`_channel_flipped_today`)을 먹어 실제 구독 전환이 조용히 차단된다
    (cycle293 적대 검증 MEDIUM-3).
    """
    scanner = _scanner()
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")
    _applied(NO_FEED, _at(10, 30))

    before_applied = dict(scanner._channel_applied)
    before_flip = dict(scanner._channel_flipped_today)
    before_cohort = dict(getattr(scanner, "_channel_cohort", {}))

    for _ in range(1_000):
        _cohort_blocked(NO_FEED)

    assert dict(scanner._channel_applied) == before_applied
    assert dict(scanner._channel_flipped_today) == before_flip, (
        "게이트 호출이 하루 1회 전환 예산을 소모했다 — 같은 날 실제 구독 전환이 "
        "조용히 차단된다"
    )
    assert dict(getattr(scanner, "_channel_cohort", {})) == before_cohort


# ===========================================================================
# E1~E8 (절대 규칙 2·3) — 전환
# ===========================================================================
class _FakeSession:
    """세션 스텁 — `_subscriptions` / `_subscriptions_acked` 2집합이 ACK 술어의 정본."""

    def __init__(self, label: str = "main", *, auto_ack: bool = True):
        self._label = label
        self.label = label
        self._subscriptions: set[tuple[str, str]] = set()
        self._subscriptions_acked: set[tuple[str, str]] = set()
        self.auto_ack = auto_ack
        self.calls: list[tuple[str, str, str]] = []
        #: `unsubscribe` 가 불린 **그 순간**의 구독 스냅샷 (E5 무공백 판정용).
        self.unsub_snapshots: list[tuple[tuple[str, str], frozenset, frozenset]] = []

    async def subscribe(self, tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        self.calls.append(("subscribe", tr_id, tr_key))
        self._subscriptions.add((tr_id, tr_key))
        if self.auto_ack:
            self._subscriptions_acked.add((tr_id, tr_key))

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        self.unsub_snapshots.append((
            (tr_id, tr_key),
            frozenset(self._subscriptions),
            frozenset(self._subscriptions_acked),
        ))
        self.calls.append(("unsubscribe", tr_id, tr_key))
        self._subscriptions.discard((tr_id, tr_key))
        self._subscriptions_acked.discard((tr_id, tr_key))


def _fake_scheduler(held: set[str]):
    """`stale_watcher_core._collect_protected_for_classification` 과 같은 모양."""
    strategy = MagicMock()
    strategy.state.positions = {t: MagicMock() for t in held}
    scheduler = MagicMock()
    scheduler.registry.all.return_value = [strategy]
    scheduler._pending_next_day_clear = set()
    return scheduler


@pytest.fixture
def _pool_env(monkeypatch):
    """실제 `kis_ws_pool` 에 스텁 세션을 꽂는다 — 풀의 병행 dict 규약을 그대로 쓴다."""
    from src.realtime.websocket_pool import kis_ws_pool

    session = _FakeSession("main")
    monkeypatch.setattr(kis_ws_pool, "_main", session, raising=False)
    monkeypatch.setattr(kis_ws_pool, "_quotes", [], raising=False)
    monkeypatch.setattr(kis_ws_pool, "_ticker_to_session", {}, raising=False)
    monkeypatch.setattr(kis_ws_pool, "_ticker_to_tr_id", {}, raising=False)
    return kis_ws_pool, session


def _seed_subscription(pool, session, ticker: str, tr_id: str) -> None:
    session._subscriptions.add((tr_id, ticker))
    session._subscriptions_acked.add((tr_id, ticker))
    pool._ticker_to_session[ticker] = session
    pool._ticker_to_tr_id[ticker] = tr_id


async def _run_switch(scheduler, pool, now):
    fn = getattr(_switch_mod(), "run_switch_cycle", None)
    if fn is None:
        pytest.fail("§4-B — `tick_channel_switch.run_switch_cycle` 미존재")
    try:
        return await fn(scheduler, pool, now=now)
    except TypeError as exc:
        pytest.fail(
            f"§4-B — `run_switch_cycle(scheduler, pool, *, now)` 시그니처가 아니다. {exc}"
        )


@pytest.mark.parametrize(
    "hh_mm", [(7, 59), (8, 30), (8, 54), (9, 1), (12, 0), (16, 30), (19, 59)],
)
async def test_e1_no_switching_outside_the_window(monkeypatch, _pool_env, hh_mm):
    """🔴 E1 (§4-A · G-294-4) — **창 밖에서는 어떤 경로도 살아 있는 구독을 바꾸지 않는다.**

    창(08:55~09:00) 안에서만 하는 근거 셋이 동시에 성립한다:
      1. 그 창에만 프레임이 구조적으로 0(N2 휴장 + K1 단일가) ⇒ 이중 채널 창의
         `tick_volume` last-write-wins 비결정론이 **노출되지 않는다.**
      2. 그 창에 주문이 0건(설계 + cycle241 시장 침묵 실측 — 정규장 0건).
      3. 못 옮겨도 blind 가 아니다 — 미전환 잔여는 NXT 에 남고 NXT 는 정규장
         (N3)·애프터(N6)에 체결을 싣는다. 비용은 「KRX 가격 대신 NXT 가격」뿐이다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(*hh_mm))

    assert session.calls == [], (
        f"{hh_mm[0]:02d}:{hh_mm[1]:02d} 에 전환이 실행됐다 — 창 밖 전환은 정규장 "
        "중 이중 채널을 열어 BFB/VCP 거래량 게이트를 도착 순서에 좌우시킨다(§4-A)"
    )
    assert pool._ticker_to_tr_id[NXT_TRUE] == NXT_ONLY


async def test_e2_high_switch_is_make_before_break(monkeypatch, _pool_env):
    """🔴 E2 (절대 규칙 2 · G-294-5) — HIGH 는 subscribe **성공 후** unsubscribe.

    자문 §7-⑤ 는 이 순서를 생략하면 **자문이 기각으로 바뀐다**고 했다. 순서를
    뒤집는 뮤테이션이 여기서 붉어진다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    kinds = [c[0] for c in session.calls]
    assert "subscribe" in kinds, (
        "전환 창 안인데 신 채널 구독이 없다 — HIGH 목표는 09:00~20:00 의 KRX 다"
    )
    assert "unsubscribe" in kinds, "구 채널이 해제되지 않았다 — 이중 채널이 남는다"
    assert kinds.index("subscribe") < kinds.index("unsubscribe"), (
        f"🔴 break-before-make 다(호출 순서 {kinds}). 보유 종목이 그 사이 blind 가 "
        "되고, 그 구간에 손절이 걸리면 되돌릴 수 없다(절대 규칙 2)"
    )
    assert session.calls[kinds.index("subscribe")][1] == KRX_ONLY
    assert session.calls[kinds.index("unsubscribe")][1] == NXT_ONLY


async def test_e3_ack_timeout_keeps_the_old_channel_and_spends_no_budget(
    monkeypatch, _pool_env,
):
    """🔴 E3 (§4-C S4 · §4-F) — ACK 실패 = **구 채널 유지 + blind 0 + 예산 미소모.**

    ACK 확인 술어는 `(new, ticker) ∈ _subscriptions ∧ ∈ _subscriptions_acked` 다.
    `_subscriptions` 만 보면 SEND 직후 무응답을 성공으로 읽고 구 채널을 끊는다.

    실패가 전환 예산(`_channel_flipped_today`)을 먹으면 그날 재시도가 막힌다 —
    cycle293 §6-D 는 **성공 전환만** 센다.
    """
    scanner = _scanner()
    pool, session = _pool_env
    session.auto_ack = False                    # SEND 는 되지만 ACK 이 오지 않는다
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300, ack_timeout_secs=1.0)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    unsubs = [c for c in session.calls if c[0] == "unsubscribe"]
    assert all(c[1] == KRX_ONLY for c in unsubs), (
        f"🔴 ACK 을 못 받았는데 **구 채널**을 해제했다(해제 목록 {unsubs}). 그 종목은 "
        "그 순간부터 blind 다(§4-C S4: 신 채널만 즉시 회수하고 구 채널은 유지)"
    )
    assert len(unsubs) == 1, (
        "ACK 실패 시 신 채널 고아 튜플을 회수하지 않았다 — 41 슬롯을 잠식한다(S4)"
    )
    assert (NXT_ONLY, NXT_TRUE) in session._subscriptions, "구 채널 구독이 사라졌다"
    assert pool._ticker_to_tr_id[NXT_TRUE] == NXT_ONLY, (
        "병행 dict 가 신 채널로 갱신됐다 — 해제가 틀린 채널로 나가 OPSP0003 을 부른다"
    )
    assert not scanner._channel_flipped_today.get(NXT_TRUE), (
        "전환 **실패**가 하루 1회 전환 예산을 소모했다 — 그날 재시도가 막힌다(§4-C S4)"
    )


async def test_e4_switch_never_redraws_the_session(monkeypatch, _pool_env):
    """🔴 E4 (§4-D · G-294-7) — 전환은 **세션 안 채널 교체**다.

    다른 세션에 떨어뜨리면 `_ticker_to_session[ticker]` 가 덮이고, 구 채널 해제가
    새 세션에서 `(old, ticker)` 를 찾다가 실패해 **구 세션 튜플이 영구 고아**로
    41 슬롯을 잠식한다(cycle253 프로브가 밟은 그 함정).
    """
    pool, session = _pool_env
    other = _FakeSession("quote-1")
    pool._quotes.append(other)
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    assert pool._ticker_to_session[NXT_TRUE] is session, (
        "🔴 전환이 세션을 재추첨했다 — 구 세션의 `(old, ticker)` 가 영구 고아가 된다(§4-D)"
    )
    assert other.calls == [], "다른 세션에 구독이 나갔다 — 라운드로빈 재추첨 금지(§4-D)"


async def test_e5_price_path_is_never_empty_during_the_switch(monkeypatch, _pool_env):
    """🔴 E5 (절대 규칙 3) — 전환 도중 **가격 갱신 경로가 비는 순간이 없다.**

    전환 창(08:55~09:00)은 NXT 휴장 + KRX 시가 단일가라 WS 로도 REST 로도 **새
    체결가가 존재하지 않는다** — REST `stck_prpr` 는 전일 종가/예상체결가를 주고
    그걸 손절 판정에 넣는 것은 프리장 왜곡 틱 문제(2026-08-06 사용자 결정)의
    재현이다. 그래서 백스톱은 **REST 호출이 아니라** make-before-break 로
    구현한다(KIS 호출 증가 0).

    이 테스트는 그 계약을 **구독 상태의 불변식**으로 잰다: 구 채널을 끊는 그
    순간에 신 채널이 이미 **등록 ∧ ACK** 돼 있어야 한다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    old_unsubs = [
        snap for snap in session.unsub_snapshots if snap[0] == (NXT_ONLY, NXT_TRUE)
    ]
    assert old_unsubs, "구 채널 해제가 없었다 — 전환이 완료되지 않았다"
    for _key, subs, acked in old_unsubs:
        assert (KRX_ONLY, NXT_TRUE) in subs, (
            "🔴 구 채널을 끊는 순간 신 채널이 **등록돼 있지 않았다** = 가격 공백"
        )
        assert (KRX_ONLY, NXT_TRUE) in acked, (
            "🔴 구 채널을 끊는 순간 신 채널 **ACK 이 없었다** — SEND 만으로 구 채널을 "
            "끊으면 KIS 가 거절했을 때 그 종목은 무구독이 된다(§4-C S3)"
        )


async def test_e6_switch_dial_off_freezes_the_switching_only(monkeypatch, _pool_env):
    """E6 (§9-D · 결정 카드 D-5) — `tick_channel_switch_enabled=false` = **전환만** 정지.

    신규 구독의 시각축 판정은 유지된다. 종목은 첫 구독 채널에 머물고
    (`nxt_true` → NXT 종일 = NXT 정규장·애프터 프레임 수신 = **blind 아님**)
    위험이 즉시 동결된다. 이것이 §5 자동 원복의 수동 대응물이다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=False, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    assert session.calls == [], "전환 다이얼이 꺼졌는데 전환이 실행됐다(§9-D)"
    # 신규 구독의 시각축은 살아 있다 — 「채널이 문제」와 「전환이 문제」는 다른 결정.
    assert _desired(NXT_TRUE, _at(10, 0)) == KRX_ONLY


async def test_e7_kill_switch_off_stops_switching_too(monkeypatch, _pool_env):
    """E7 (절대 규칙 8) — `off` 에서는 전환도 0건이다."""
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("off")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    assert session.calls == []


async def test_e8_parallel_dicts_agree_after_a_successful_switch(monkeypatch, _pool_env):
    """E8 (G-294-8) — 전환 후 `_ticker_to_tr_id` == 세션의 **실제** 튜플.

    둘이 갈리면 해제가 틀린 채널로 나가 `OPSP0003 UNSUBSCRIBE ERROR not found!`
    가 뜨고 구 채널 튜플이 영구 고아가 된다(cycle215~218 이 잡은 그 ERROR).
    이중 튜플도 0 이어야 한다 — 전환은 **종목 단위 완료 후 다음**(순차 계약).
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE})

    await _run_switch(scheduler, pool, _at(8, 56))

    assert pool._ticker_to_tr_id[NXT_TRUE] == KRX_ONLY
    live = {tr for tr, tk in session._subscriptions if tk == NXT_TRUE}
    assert live == {KRX_ONLY}, (
        f"전환 후 이 종목의 살아 있는 채널이 {sorted(live)} 다 — 두 개면 이중 채널이고 "
        "`tick_volume.record_acml_vol` 이 도착 순서에 좌우된다(N-4)"
    )


# ===========================================================================
# F1~F5 (절대 규칙 4 · §5) — 자동 원복
# ===========================================================================
async def _switch_then_probe(monkeypatch, pool, session, tickers, *, fresh=(),
                             silent=(), probe_at=None):
    """08:56 전환 → `probe_at`(기본 09:03) 원복 판정 사이클."""
    import src.engine.scanner as scanner_mod

    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300, revert_probe_secs=180)
    for t in tickers:
        _seed_subscription(pool, session, t, NXT_ONLY)
    scheduler = _fake_scheduler(set(tickers))
    await _run_switch(scheduler, pool, _at(8, 56))

    last_tick = {t: _at(9, 2, 30) for t in fresh}
    for t in silent:
        last_tick.pop(t, None)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", last_tick)
    return await _run_switch(scheduler, pool, probe_at or _at(9, 3))


async def test_f1_revert_needs_at_least_two_samples(monkeypatch, _pool_env):
    """F1 (§5-A 최소 표본) — 표본 **1종목**으로는 되돌리지 않는다.

    cycle241 선례 — 판정 가능 세션 < 2 면 fail-open. 저유동 1종목이 시스템 전체를
    되돌리면 안 된다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    await _switch_then_probe(
        monkeypatch, pool, session, [NXT_TRUE],
        fresh=(NO_FEED, NO_FEED_2), silent=(NXT_TRUE,),
    )
    assert pool._ticker_to_tr_id[NXT_TRUE] == KRX_ONLY, (
        "표본 1종목으로 원복했다 — 저유동 1종목이 시스템 전체를 되돌린다(§5-A)"
    )


async def test_f2_market_wide_silence_does_not_trigger_a_revert(monkeypatch, _pool_env, caplog):
    """F2 (§5-A 교차 확인) — **전체 침묵**은 채널 문제가 아니다.

    같은 순간 **미전환 코호트**(프리 창부터 KRX 였던 `nxt_false` 또는 LOW) 중
    ≥2 가 fresh 여야 원복이 성립한다. 전체가 침묵이면 세션·시장 문제이고
    `_detect_silent_inactive_sessions` 경로가 그쪽을 담당한다(cycle241).
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    caplog.set_level(logging.INFO)

    await _switch_then_probe(
        monkeypatch, pool, session, [NXT_TRUE, NXT_TRUE_2],
        fresh=(), silent=(NXT_TRUE, NXT_TRUE_2),
    )

    assert pool._ticker_to_tr_id[NXT_TRUE] == KRX_ONLY, (
        "교차 확인 없이 원복했다 — 시장 전체 침묵을 채널 결함으로 오독한다(§5-A)"
    )


async def test_f3_no_frames_after_open_triggers_an_error_level_revert(
    monkeypatch, _pool_env, caplog,
):
    """🔴 F3 (절대 규칙 4 · §5-B) — 새 채널 무프레임 지속 → **스스로 되돌린다.**

    측정 시점 = `krx_regular_open + 180초`(=09:03). 180 은 새 숫자가 아니라
    `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 의 **재사용**이다(금기 13).
    08:55~09:00 은 시장이 없어 프레임 0 이 정상이라 거기서 재면 100% 오탐이다.

    마커는 **ERROR** 다 — 되돌렸다는 것은 설계 가정(`H0STCNT0` 가 종목 속성 무관
    수신)이 틀렸다는 뜻이고, INFO 면 21:30 리포트 `top_patterns` 에 한 글자도
    안 뜬다(cycle245 `[ratio_cap_config]` 함정).
    """
    pool, session = _pool_env
    _patch_classification(
        monkeypatch, no_feed=(NO_FEED, NO_FEED_2),
        provenance_ok=(NXT_TRUE, NXT_TRUE_2, NO_FEED, NO_FEED_2),
        classified=(NXT_TRUE, NXT_TRUE_2, NO_FEED, NO_FEED_2),
    )
    caplog.set_level(logging.INFO)

    await _switch_then_probe(
        monkeypatch, pool, session, [NXT_TRUE, NXT_TRUE_2],
        fresh=(NO_FEED, NO_FEED_2), silent=(NXT_TRUE, NXT_TRUE_2),
    )

    assert pool._ticker_to_tr_id[NXT_TRUE] == NXT_ONLY, (
        "🔴 전환한 HIGH 2종목이 09:03 까지 프레임 0 인데 되돌리지 않았다 — 그 종목의 "
        "손절 평가가 그날 종일 죽는다(절대 규칙 4)"
    )
    revert_records = [r for r in caplog.records if _MARKER_AUTO_REVERT in r.getMessage()]
    assert revert_records, f"{_MARKER_AUTO_REVERT} 관측이 없다 — 사람이 알 수 없다"
    assert any(r.levelno >= logging.ERROR for r in revert_records), (
        f"{_MARKER_AUTO_REVERT} 가 ERROR 미만이다 — 21:30 리포트 `top_patterns` 는 "
        "WARNING 이상만 담는다(§5-B 4)"
    )


async def test_f4_revert_respects_the_attribute_axis(monkeypatch, _pool_env):
    """🔴 F4 (§5-B 1 · G-294-10) — 되돌림은 **전원 NXT 가 아니다.**

    단순히 "전원 NXT" 로 되돌리면 `nxt_false` 종목이 NXT 에서 프레임 0 이 되어
    **원복이 새 blind 를 만든다.** `day_reverted` 는 그날 나머지 시간 동안
    **프리 창 규칙**을 쓴다 — `nxt_true` → NXT · `nxt_false` → **KRX 유지**.
    """
    clock = _clock()
    setter = getattr(clock, "set_day_revert", None)
    if setter is None:
        pytest.fail(
            "§5-B 1 — `tick_channel_clock.set_day_revert()` 미존재. 원복은 그날 "
            "나머지 시간의 **프리 창 규칙 전환**이지 '전원 NXT' 가 아니다"
        )
    _patch_classification(monkeypatch, no_feed=(NO_FEED,),
                          provenance_ok=(NO_FEED, NXT_TRUE), classified=(NO_FEED, NXT_TRUE))
    _set_mode("enforce")
    # 🔴 시각 드리프트 시정(cycle295 적대 검증) — 인자 없는 `setter()` 는 **벽시계
    # 오늘**로 래치를 심는데 아래 판정은 `DAY`(2026-09-15) 로 묻는다.
    # `day_reverted(now)` 는 `now.date() < _revert_for` 면 되돌림을 보지 않으므로,
    # 이 테스트는 **실행일이 DAY 를 넘긴 다음 날부터 영구히 붉었다**(2026-09-16
    # 실측 — cycle295 착수 전 baseline 에서도 동일 재현 = 선재 결함).
    # 자매 파일 `test_cycle294b_adversarial_fixes.py:761` 은 처음부터 `DAY` 를
    # 명시한다. 메모리 「시각 창 게이트 테스트는 시각 고정」 답습.
    setter(DAY)

    assert _desired(NXT_TRUE, _at(10, 0)) == NXT_ONLY, (
        "원복 뒤 `nxt_true` 가 NXT 로 돌아가지 않았다"
    )
    assert _desired(NO_FEED, _at(10, 0)) == KRX_ONLY, (
        "🔴 원복이 `nxt_false` 까지 NXT 로 보냈다 — 그 종목은 NXT 에서 프레임 0 이라 "
        "**원복 자체가 새 blind 를 만든다**(§5-B 1)"
    )


async def test_f5_no_retry_on_the_same_day(monkeypatch, _pool_env):
    """F5 (§5-C · 금기 12) — 되돌린 뒤 **그날은 재시도하지 않는다.**

    재시도가 왕복을 만들고 그것이 KIS 공지 「비정상 케이스 2: 무한 등록/해제」다.
    다음 영업일 07:59 신규 구독부터 자연 재시도한다.
    """
    pool, session = _pool_env
    _patch_classification(
        monkeypatch, no_feed=(NO_FEED, NO_FEED_2),
        provenance_ok=(NXT_TRUE, NXT_TRUE_2, NO_FEED, NO_FEED_2),
        classified=(NXT_TRUE, NXT_TRUE_2, NO_FEED, NO_FEED_2),
    )
    await _switch_then_probe(
        monkeypatch, pool, session, [NXT_TRUE, NXT_TRUE_2],
        fresh=(NO_FEED, NO_FEED_2), silent=(NXT_TRUE, NXT_TRUE_2),
    )
    session.calls.clear()
    scheduler = _fake_scheduler({NXT_TRUE, NXT_TRUE_2})

    await _run_switch(scheduler, pool, _at(9, 6))
    await _run_switch(scheduler, pool, _at(9, 9))

    assert session.calls == [], (
        "원복 뒤 같은 날 다시 전환했다 — 채널 왕복은 KIS 「비정상 케이스 2: 무한 "
        "등록/해제」다(§5-C)"
    )


# ===========================================================================
# G1~G3 (절대 규칙 1 · §7-B) — 레거시 재라우팅
# ===========================================================================
def _fresh_socket():
    """네트워크 없는 `KisWebSocket` 1개.

    🔴 `_reroute_legacy_unified` 부재를 **여기서** FAIL 시킨다. 그러지 않으면
    G2/G3(「통합이 아닌 요청은 byte 동일 통과」)가 재라우팅이 아예 없는 오늘도
    초록이라 **공허 가드**가 된다 — 스코프를 재는 가드는 재라우팅이 실재할 때만
    의미가 있다.
    """
    import src.realtime.websocket as ws_mod
    from src.realtime.websocket import KisWebSocket

    if getattr(ws_mod, "_reroute_legacy_unified", None) is None:
        pytest.fail(
            "§7-B — `websocket._reroute_legacy_unified(tr_id, tr_key)` 미존재. "
            "`scheduler.py:1382`/`:2728` 이 풀을 우회해 `TICK_TR_ID` 로 직접 구독하는 "
            "한 「통합 구독 0」 은 성립하지 않는다. `KisWebSocket.subscribe` 첫 문장에 "
            "넣고, 재라우팅 조건은 **tr_id 가 정확히 통합일 때** 하나뿐이어야 한다"
        )
    ws = KisWebSocket(is_main=True, label="main")
    ws._ws = None            # 네트워크 없음 — `_send_subscribe` 미발사
    return ws


async def test_g1_legacy_unified_request_is_rerouted(monkeypatch, _pool_env, caplog):
    """🔴 G1 (§7-B) — `scheduler.py` 의 통합 구독 2곳을 `websocket.py` 가 흡수한다.

    `scheduler.py:1382`(익일청산 시가 수신)·`:2728`(스윙 매수 직후)은 무접촉
    제약 때문에 계속 `TICK_TR_ID` 로 **풀을 우회해** 직접 구독한다. 그 둘을 두면
    "통합 구독 0" 이 성립하지 않는다.

    ⚠️ 이것은 **증상 차단**이다(N-3). 근본 시정 = 그 2줄 치환(결정 카드 D-4).
    """
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    caplog.set_level(logging.INFO)
    ws = _fresh_socket()

    await ws.subscribe(UNIFIED, NXT_TRUE, bypass_limit=True)

    live = {tr for tr, tk in ws._subscriptions if tk == NXT_TRUE}
    assert UNIFIED not in live, (
        f"🔴 레거시 호출이 통합 채널로 구독됐다(현재 {sorted(live)}) — 그 종목은 "
        "`nxt_false` 면 프레임 0 이고, 「통합 구독 0」 이 무너진다(§7-B)"
    )
    assert live and live <= {KRX_ONLY, NXT_ONLY}
    assert any(_MARKER_LEGACY_REROUTE in r.getMessage() for r in caplog.records), (
        f"{_MARKER_LEGACY_REROUTE} 관측이 없다 — `scheduler.py` 두 줄의 실제 발화 "
        "빈도를 처음으로 재는 유일한 마커다(§7-B)"
    )


@pytest.mark.parametrize(
    "tr_id",
    ["H0STCNI0", "H0STCNI9", "H0UNMKO0", KRX_ONLY, NXT_ONLY],
)
async def test_g2_non_unified_requests_pass_through_byte_identical(
    monkeypatch, _pool_env, tr_id,
):
    """🔴 G2 (G-294-11) — 재라우팅 스코프는 **통합 하나**뿐이다.

    체결통보(`H0STCNI0`/`H0STCNI9`)가 재라우팅되면 포지션 등록·손절이 죽고
    (핵심 안전 규칙 「체결통보 구독 제거 금지」), 장운영정보(`H0UNMKO0`)가
    재라우팅되면 cycle292 의 구독 leaf 가 깨진다. 전용 2채널이 재라우팅되면
    이중 채널이 생긴다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_mode("enforce")
    ws = _fresh_socket()

    await ws.subscribe(tr_id, NO_FEED, bypass_limit=True)

    assert (tr_id, NO_FEED) in ws._subscriptions, (
        f"🔴 `{tr_id}` 요청이 재라우팅됐다 — 재라우팅 조건은 **tr_id 가 정확히 "
        f"`{UNIFIED}` 일 때** 하나뿐이다(§7-B)"
    )


@pytest.mark.parametrize("mode", ["off", "observe"])
async def test_g3_reroute_is_inert_in_rollback_and_darklaunch(monkeypatch, _pool_env, mode):
    """G3 (§7-B · 절대 규칙 8) — `off`/`observe` 는 **오늘과 byte 동일**이다."""
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode(mode)
    ws = _fresh_socket()

    await ws.subscribe(UNIFIED, NXT_TRUE, bypass_limit=True)

    assert (UNIFIED, NXT_TRUE) in ws._subscriptions, (
        f"`{mode}` 인데 레거시 통합 요청이 재라우팅됐다 — 롤백·다크런치는 행위 0 이다"
    )


# ===========================================================================
# H1 (절대 규칙 8) — 킬스위치 `off` = 배포 전과 동일
# ===========================================================================
async def test_h1_off_is_indistinguishable_from_the_pre_deploy_world(
    monkeypatch, _pool_env,
):
    """H1 (절대 규칙 8) — `off` 면 판정·전환·재라우팅이 **전부** 오늘과 같다.

    ⚠️ `off` 는 **이미 전용 채널에 올라간 구독을 되돌리지 않는다**(§9-B). 장중에
    146종목을 대량 전환하는 것이 더 위험하고, 되돌림 대상인 통합은 `nxt_false`
    에게 프레임 0 이라 **킬스위치가 손절을 악화시킨다**. 완전 복귀는 다음 `_boot`.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,))
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _set_mode("off")
    _seed_subscription(pool, session, NXT_TRUE, UNIFIED)
    scheduler = _fake_scheduler({NXT_TRUE})

    assert _desired(NXT_TRUE, _at(8, 10)) == UNIFIED
    assert _desired(NO_FEED, _at(16, 30)) == UNIFIED
    await _run_switch(scheduler, pool, _at(8, 56))
    assert session.calls == []

    ws = _fresh_socket()
    await ws.subscribe(UNIFIED, NXT_TRUE, bypass_limit=True)
    assert (UNIFIED, NXT_TRUE) in ws._subscriptions


# ===========================================================================
# 스코프 (G-294-12) — 행위 파일에서도 한 번 더 못박는다
# ===========================================================================
def test_scope_scheduler_and_strategies_are_untouched() -> None:
    """스코프 — `scheduler.py` 3,726L · 전략 7파일 무접촉.

    상세 sha 핀은 AST 자매 파일(A1/A2)에 있다. 여기 한 줄을 둔 이유는 행위 파일만
    돌린 사람도 스코프 위반을 즉시 보게 하기 위해서다.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    lines = len((root / "src/engine/scheduler.py").read_text(encoding="utf-8").splitlines())
    assert lines == 3726, (
        f"scheduler.py = {lines}L (착수 시점 3,726L) — 무접촉 계약 위반(절대 규칙 7)"
    )
