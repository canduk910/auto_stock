"""cycle258 Red — `KstDailyEmitCap` (리팩토링 카드 #4).

명세: `_workspace/red/`(작성 예정) / 스크래치패드 `spec_cycle258_emit_cap_observer_trace.md` §1
근거: `_workspace/refactor/2026-09-05_review.md` 카드 #4 (22 사이트 / 5 파일 실측)

## 고칠 것 (한 문장)

`DailyEmitCap`(사이클 56)은 `should_emit/mark_emitted/reset_daily` 세 메서드뿐이라
그 위에 (a) KST 날짜 키 자기 리셋 (b) peek→로그→mark 순서 (c) 예외 흡수를
**매 호출부가 손으로** 감싼다 — `src/engine` 22 사이트, 그중 순서 드리프트
(mark-before-log)가 6곳. 서브클래스 `KstDailyEmitCap` 하나가 이 셋을 흡수한다.

## 이 파일이 봉인하는 것

- K-1  상속 계약 — 기존 `DailyEmitCap` API/호환 layer 가 그대로 산다.
- K-2  `now=` 주입 결정성 (벽시계 무관 — 테스트 seam).
- K-3  날짜 경계 자기 리셋 (`now=` 주입 축).
- K-4  **KST** 판정 — UTC 로 재면 통과 못 하는 경계(14:59Z↔15:01Z)로 핀.
- K-5  같은 날 반복 호출이 cap 을 되살리지 않는다(리셋은 날짜가 바뀔 때만).
- K-6  `emit_once` 성공 = peek → `log_fn(msg, *args)` → mark → True.
- K-7  `emit_once` 는 cap 소진 시 `log_fn` 을 **부르지 않는다** + False.
- K-8  `log_fn` 예외 = mark **미소비**(cycle226 D-3) + 예외 전파 0 + False.
- K-9  never-raise — cap 내부(키 해시 실패 등)에서 터져도 호출부로 안 샌다.
- K-10 `emit_once` 자기실패도 **흔적**을 남긴다(무흔적 `pass` 금지 — 카드 #5 정책).
- K-11 `reset_daily()` 직접 호출 호환 (기존 정산/픽스처 경로).
- K-12 기존 `DailyEmitCap` **byte 불변** (리터럴 sha 핀 — 56-B/C/D 호환 layer 보존).
- K-13 같은 날 `mark_emitted` 선점이 이후 `should_emit` 에 지워지지 않는다
       — 기존 픽스처가 `_x_day = today` 선세팅으로 얻던 성질(예:
       `test_cycle224_donchian_days_held_observe.py::OB-11`)의 후계 계약.

## Red 판정 기준

`KstDailyEmitCap` 미구현 상태에서 K-1~K-11·K-13 은 FAIL, K-12(sha 핀)만 PASS
(기존 클래스가 아직 무변경이므로) — 이것이 "Red 인데 기존 계약은 산다"의 실증이다.
"""

from __future__ import annotations

import ast
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine import daily_emit_cap as dec_mod
from src.engine.daily_emit_cap import DailyEmitCap

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_SRC = Path(__file__).resolve().parents[3] / "src" / "engine" / "daily_emit_cap.py"

# 카드 #4 "기존 클래스 byte 불변" 의 리터럴 핀 (2026-09-05 HEAD 1b30dd6 실측).
# ⚠️ bare `git show HEAD:` 비교 금지 — 커밋 순간 공허해지고 다음 편집에서 동결이
# 된다(2026-09-05 리뷰 축 4 결론). 정당한 변경 시 이 리터럴 1줄을 갱신한다.
_DAILY_EMIT_CAP_SEGMENT_SHA = (
    "c96397c4f18700d16cb649af65cc6416394f31251e807764db19516cc80e7bf6"
)


# ---------------------------------------------------------------------------
# 헬퍼 (로컬 — 타 테스트 모듈 import 금지)
# ---------------------------------------------------------------------------
def _cls():
    """`KstDailyEmitCap` 해석. 미구현이면 그 자리에서 RED (collection error 회피)."""
    cls = getattr(dec_mod, "KstDailyEmitCap", None)
    if cls is None:
        pytest.fail(
            "`src.engine.daily_emit_cap.KstDailyEmitCap` 미구현 — 카드 #4 의 "
            "KST 날짜 자기 리셋 + peek→로그→mark 표준 진입점이 없습니다"
        )
    return cls


def _cap():
    return _cls()()


def _dt(y: int, m: int, d: int, hh: int = 10, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_KST)


class _Recorder:
    """`log_fn` 대역 — 호출 인자를 그대로 기록하고 필요 시 폭발한다."""

    def __init__(self, boom: bool = False) -> None:
        self.calls: list[tuple] = []
        self.boom = boom

    def __call__(self, msg, *args):
        self.calls.append((msg, args))
        if self.boom:
            raise RuntimeError("logger down")


# ===========================================================================
# K-1 — 상속 계약 (기존 API + 호환 layer 유지)
# ===========================================================================
def test_k1_subclass_keeps_base_api_and_compat_layer():
    cap = _cap()
    assert isinstance(cap, DailyEmitCap), (
        "`KstDailyEmitCap` 이 `DailyEmitCap` 서브클래스가 아닙니다 — 56-B/C/D "
        "호환 layer(=set 비교·add/discard/__contains__)를 잃습니다"
    )
    assert cap.should_emit("005930") is True
    cap.mark_emitted("005930")
    assert cap.should_emit("005930") is False
    assert "005930" in cap
    assert len(cap) == 1
    cap.add("000660")
    assert len(cap) == 2
    cap.discard("000660")
    assert len(cap) == 1
    cap.clear()
    assert len(cap) == 0
    assert cap == set()


# ===========================================================================
# K-2 — `now=` 주입 결정성 (벽시계 무관)
# ===========================================================================
@freeze_time("2030-01-01 00:00:00+09:00")
def test_k2_now_injection_governs_not_wall_clock():
    """주입한 `now` 만 날짜 판정에 쓰인다 — 벽시계(2030)는 관여하지 않는다."""
    cap = _cap()
    d1 = _dt(2026, 9, 5)
    assert cap.should_emit("k", now=d1) is True
    cap.mark_emitted("k")
    assert cap.should_emit("k", now=d1) is False, (
        "같은 `now` 인데 cap 이 리셋됐다 — 주입 seam 이 벽시계에 오염됩니다"
    )
    # 같은 `now` 를 몇 번 넣어도 결과가 흔들리지 않는다.
    assert [cap.should_emit("k", now=d1) for _ in range(3)] == [False, False, False]


# ===========================================================================
# K-3 — 날짜 경계 자기 리셋 (`now=` 축)
# ===========================================================================
def test_k3_day_rollover_resets_itself():
    cap = _cap()
    d1, d2 = _dt(2026, 9, 5, 23, 59), _dt(2026, 9, 6, 0, 1)
    assert cap.should_emit("k", now=d1) is True
    cap.mark_emitted("k")
    assert cap.should_emit("k", now=d1) is False
    assert cap.should_emit("k", now=d2) is True, (
        "KST 날짜가 바뀌었는데 cap 이 자기 리셋을 안 했다 — `_reset_daily_state` "
        "훅에 의존하지 않는 것이 이 클래스의 존재 이유입니다"
    )


def test_k3b_rollover_clears_every_key_not_just_the_probed_one():
    """리셋은 `reset_daily()` 의미 그대로 — 조회한 키만 지우는 게 아니다."""
    cap = _cap()
    d1, d2 = _dt(2026, 9, 5), _dt(2026, 9, 6)
    cap.should_emit("a", now=d1)
    cap.mark_emitted("a")
    cap.mark_emitted("b")
    assert cap.should_emit("a", now=d2) is True
    assert cap.should_emit("b", now=d2) is True, (
        "날짜 리셋이 조회한 키만 지웠다 — `reset_daily()` 위임이 아닙니다"
    )


# ===========================================================================
# K-4 — **KST** 판정 (UTC 로 재면 통과 못 하는 경계)
# ===========================================================================
def test_k4_boundary_is_kst_not_utc():
    """14:59Z(=09-05 23:59 KST) → 15:01Z(=09-06 00:01 KST).

    UTC 날짜로 판정하면 두 시각 모두 09-05 라 리셋이 안 일어난다 = FAIL.
    """
    cap = _cap()
    with freeze_time("2026-09-05 14:59:00+00:00"):
        assert cap.should_emit("k") is True
        cap.mark_emitted("k")
        assert cap.should_emit("k") is False
    with freeze_time("2026-09-05 15:01:00+00:00"):
        assert cap.should_emit("k") is True, (
            "UTC 날짜로 판정하고 있습니다 — 이 프로젝트의 모든 일일 cap 은 KST 경계"
        )


def test_k4b_same_kst_day_across_utc_midnight_does_not_reset():
    """역방향 핀 — UTC 자정을 넘어도 같은 KST 날짜면 리셋 금지(09-05 09:00~10:00 KST)."""
    cap = _cap()
    with freeze_time("2026-09-05 00:30:00+09:00"):
        assert cap.should_emit("k") is True
        cap.mark_emitted("k")
    with freeze_time("2026-09-05 23:30:00+09:00"):
        assert cap.should_emit("k") is False, (
            "같은 KST 날짜 안에서 cap 이 리셋됐다 — 1회/일 계약이 깨집니다"
        )


# ===========================================================================
# K-5 — 리셋은 날짜가 바뀔 때만 (같은 날 반복 호출이 cap 을 되살리지 않는다)
# ===========================================================================
def test_k5_repeated_calls_same_day_do_not_revive_cap():
    """`should_emit` 이 매번 `reset_daily()` 를 부르면 cap 이 통째로 무력화된다."""
    cap = _cap()
    d = _dt(2026, 9, 5)
    for i in range(5):
        cap.should_emit(f"probe{i}", now=d)
    cap.mark_emitted("k")
    for i in range(5):
        cap.should_emit(f"probe{i}", now=d)
    assert cap.should_emit("k", now=d) is False, (
        "같은 날 반복 조회가 mark 를 지웠다 — 날짜 비교 없이 매번 리셋하고 있습니다"
    )


# ===========================================================================
# K-6 — `emit_once` 성공 경로 (peek → log_fn(msg,*args) → mark → True)
# ===========================================================================
def test_k6_emit_once_success_logs_then_marks():
    cap = _cap()
    rec = _Recorder()
    d = _dt(2026, 9, 5)

    assert cap.emit_once("k", rec, "[marker] a=%s b=%d", "x", 7, now=d) is True
    assert rec.calls == [("[marker] a=%s b=%d", ("x", 7))], (
        "포맷 문자열/가변 인자가 그대로 전달되지 않았습니다 — 로그 서식 byte 불변 "
        "계약(G-245-10)이 깨집니다"
    )
    assert cap.should_emit("k", now=d) is False, "성공 후 mark 가 안 됐습니다"


def test_k6b_emit_once_second_call_same_day_is_capped():
    cap = _cap()
    rec = _Recorder()
    d = _dt(2026, 9, 5)
    assert cap.emit_once("k", rec, "m") is True
    assert cap.emit_once("k", rec, "m") is False
    assert len(rec.calls) == 1, "1회/(key)/일 cap 이 안 걸렸습니다"
    assert cap.emit_once("k", rec, "m", now=_dt(2026, 9, 6)) is True, (
        "날짜가 바뀌었는데 재발화하지 않습니다"
    )
    assert len(rec.calls) == 2


# ===========================================================================
# K-7 — cap 소진 시 `log_fn` 미호출 (인자 평가 비용/사이드이펙트 0)
# ===========================================================================
def test_k7_capped_call_does_not_invoke_log_fn():
    cap = _cap()
    rec = _Recorder()
    d = _dt(2026, 9, 5)
    cap.should_emit("k", now=d)
    cap.mark_emitted("k")
    assert cap.emit_once("k", rec, "m", now=d) is False
    assert rec.calls == [], "cap 소진 상태인데 `log_fn` 이 호출됐습니다"


# ===========================================================================
# K-8 — `log_fn` 예외 = mark 미소비 (cycle226 D-3) + 전파 0 + False
# ===========================================================================
def test_k8_log_fn_failure_does_not_consume_cap():
    """로그 자기실패가 그날 관측을 통째로 지우면 안 된다 (peek→로그→mark)."""
    cap = _cap()
    boom = _Recorder(boom=True)
    ok = _Recorder()
    d = _dt(2026, 9, 5)

    assert cap.emit_once("k", boom, "m", now=d) is False, "실패인데 True 를 반환했습니다"
    assert cap.should_emit("k", now=d) is True, (
        "mark-before-log 입니다 — 로그가 던진 그 순간 그날의 관측이 사라집니다 "
        "(cycle226 D-3 / cycle233 F4 규약)"
    )
    assert cap.emit_once("k", ok, "m", now=d) is True, "다음 호출이 재시도되지 않습니다"
    assert len(ok.calls) == 1


def test_k8b_log_fn_failure_never_propagates():
    cap = _cap()
    boom = _Recorder(boom=True)
    try:
        cap.emit_once("k", boom, "m")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"관측 실패가 호출부로 전파됐습니다: {exc!r} — 행위는 cap 밖 계약")


# ===========================================================================
# K-9 — never-raise (cap 내부 자기실패도 흡수)
# ===========================================================================
def test_k9_unhashable_key_is_absorbed():
    """키가 unhashable 이면 `should_emit` 내부에서 TypeError — 그래도 안 샌다."""
    cap = _cap()
    rec = _Recorder()
    try:
        result = cap.emit_once(["unhashable"], rec, "m")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"cap 내부 예외가 전파됐습니다: {exc!r}")
    assert result is False


def test_k9b_should_emit_with_broken_now_is_absorbed_or_defaults():
    """`now` 가 datetime 이 아니어도 호출부를 죽이지 않는다."""
    cap = _cap()
    rec = _Recorder()
    try:
        cap.emit_once("k", rec, "m", now="2026-09-05")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"잘못된 `now` 가 호출부로 전파됐습니다: {exc!r}")


# ===========================================================================
# K-10 — `emit_once` 자기실패도 흔적을 남긴다 (무흔적 `pass` 금지)
# ===========================================================================
def test_k10_emit_once_failure_leaves_a_trace(caplog):
    """카드 #5 정책 — 조용히 삼키면 "관측기가 영구히 깨졌는데 아무도 모르는" 사각.

    구현 수단(모듈 함수 `trace_observer_failure` 경유 등)은 핀하지 않고
    **관측 가능한 사실**만 본다: 스택트레이스가 실린 로그 레코드 1건 이상.
    """
    cap = _cap()
    boom = _Recorder(boom=True)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        cap.emit_once("k", boom, "[some_marker] x=%s", "1")
    assert any(r.exc_info for r in caplog.records), (
        "관측기 자기실패가 무흔적으로 삼켜졌습니다 — 도입 이전 무음과 구별 불가"
        f" (기록된 레코드: {[r.getMessage() for r in caplog.records]})"
    )


# ===========================================================================
# K-11 — `reset_daily()` 직접 호출 호환 (기존 정산/픽스처 경로)
# ===========================================================================
def test_k11_reset_daily_still_works_directly():
    cap = _cap()
    d = _dt(2026, 9, 5)
    cap.should_emit("k", now=d)
    cap.mark_emitted("k")
    assert cap.should_emit("k", now=d) is False
    cap.reset_daily()
    assert cap.should_emit("k", now=d) is True, (
        "`reset_daily()` 직접 호출이 무력화됐습니다 — 기존 정산 훅/픽스처가 깨집니다"
    )


# ===========================================================================
# K-12 — 기존 `DailyEmitCap` byte 불변 (리터럴 sha 핀)
# ===========================================================================
def test_k12_daily_emit_cap_class_is_byte_stable():
    src = _SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(
        (n for n in tree.body
         if isinstance(n, ast.ClassDef) and n.name == "DailyEmitCap"),
        None,
    )
    assert node is not None, "`DailyEmitCap` 클래스가 사라졌습니다"
    seg = ast.get_source_segment(src, node)
    assert seg is not None
    got = hashlib.sha256(seg.encode("utf-8")).hexdigest()
    assert got == _DAILY_EMIT_CAP_SEGMENT_SHA, (
        "기존 `DailyEmitCap` 클래스 본문이 변경됐습니다 — cycle258 은 **서브클래스 "
        f"추가만** 이 범위입니다(56-B/C/D 호환 layer 보존). 실측 sha={got}"
    )


def test_k12b_subclass_is_additive_only():
    """서브클래스가 기존 메서드의 **시그니처 계약**을 좁히지 않는다."""
    cls = _cls()
    base_only = DailyEmitCap[str]()
    sub = cls()
    # 기존 호출 형태(키워드 없음)가 그대로 통한다.
    assert base_only.should_emit("x") is True
    assert sub.should_emit("x") is True
    sub.mark_emitted("x")
    assert sub.should_emit("x") is False


# ===========================================================================
# K-13 — 같은 날 `mark_emitted` 선점이 지워지지 않는다 (픽스처 계약 후계)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
def test_k13_same_day_preseed_survives_first_should_emit():
    """기존 픽스처는 `_x_day = today` 를 **먼저** 세팅해 선점을 지켰다.

    day 필드가 클래스 안으로 들어가면 그 선세팅 수단이 사라진다. 선점이 첫
    `should_emit` 의 날짜 프라이밍에 지워지면
    `test_cycle224_donchian_days_held_observe.py::OB-11`(폴백 cap 선점) ·
    `test_cycle245_ratio_notional_cap.py::F-12f`(cycle242 cap 소진) 같은
    기존 회귀가 조용히 의미를 잃는다.
    """
    cap = _cap()
    d = _dt(2026, 9, 5)
    cap.mark_emitted("005930")          # 프로덕션이 아직 아무것도 안 읽은 상태에서 선점
    assert cap.should_emit("005930", now=d) is False, (
        "첫 `should_emit` 의 날짜 프라이밍이 같은 날 선점을 지웠습니다 — "
        "`__init__` 또는 `mark_emitted` 에서 날짜를 프라이밍해야 합니다"
    )


@freeze_time("2026-09-05 10:00:00+09:00")
def test_k13b_preseed_still_expires_next_day():
    """K-13 이 '영원히 안 지워진다'로 과교정되지 않았는지 — 익일에는 리셋된다."""
    cap = _cap()
    cap.mark_emitted("005930")
    assert cap.should_emit("005930", now=_dt(2026, 9, 5)) is False
    assert cap.should_emit("005930", now=_dt(2026, 9, 6)) is True
