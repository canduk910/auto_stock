"""사이클 56-A — DailyEmitCap 헬퍼 회귀 가드 (G-1 7 케이스).

검증 범위:
    G1-1  신규 인스턴스에서 should_emit 은 True
    G1-2  mark_emitted 후 should_emit 은 False
    G1-3  reset_daily 후 should_emit 이 True 로 복원
    G1-4  str 키 타입 파라미터화 정상 동작
    G1-5  tuple 키 타입 파라미터화 + str 인스턴스와 격리
    G1-6  호환 layer (__contains__ / add / discard / clear) set 동형
    G1-7  다중 인스턴스 격리 (cap_a 변경이 cap_b 에 영향 없음)
"""
import pytest

from src.engine.daily_emit_cap import DailyEmitCap


# ---------------------------------------------------------------------------
# G1-1 — 신규 인스턴스 should_emit=True
# ---------------------------------------------------------------------------
def test_g1_1_fresh_instance_should_emit():
    cap: DailyEmitCap[str] = DailyEmitCap()
    assert cap.should_emit("009150") is True


# ---------------------------------------------------------------------------
# G1-2 — mark_emitted 후 should_emit=False
# ---------------------------------------------------------------------------
def test_g1_2_after_mark_emitted_should_emit_false():
    cap: DailyEmitCap[str] = DailyEmitCap()
    cap.mark_emitted("009150")
    assert cap.should_emit("009150") is False


# ---------------------------------------------------------------------------
# G1-3 — reset_daily 후 should_emit=True 복원
# ---------------------------------------------------------------------------
def test_g1_3_reset_daily_restores_should_emit():
    cap: DailyEmitCap[str] = DailyEmitCap()
    cap.mark_emitted("009150")
    assert cap.should_emit("009150") is False  # 전제 확인

    cap.reset_daily()
    assert cap.should_emit("009150") is True


# ---------------------------------------------------------------------------
# G1-4 — str 키 파라미터화 정상 동작
# ---------------------------------------------------------------------------
def test_g1_4_str_key_generic():
    cap: DailyEmitCap[str] = DailyEmitCap()

    assert cap.should_emit("A") is True
    cap.mark_emitted("A")
    assert cap.should_emit("A") is False
    assert cap.should_emit("B") is True  # 다른 key 영향 없음


# ---------------------------------------------------------------------------
# G1-5 — tuple 키 파라미터화 + str 인스턴스와 격리
# ---------------------------------------------------------------------------
def test_g1_5_tuple_key_generic_and_isolation():
    cap_tuple: DailyEmitCap[tuple] = DailyEmitCap()
    cap_str: DailyEmitCap[str] = DailyEmitCap()

    key_tuple = ("009150", "volatility_breakout")
    key_str = "009150"

    cap_tuple.mark_emitted(key_tuple)
    assert cap_tuple.should_emit(key_tuple) is False

    # str 인스턴스는 tuple 인스턴스의 영향을 받지 않아야 한다
    assert cap_str.should_emit(key_str) is True

    # tuple 인스턴스에서 str 키는 별도 key — 여기서도 영향 없음
    assert cap_tuple.should_emit(("009150", "momentum")) is True


# ---------------------------------------------------------------------------
# G1-6 — 호환 layer: __contains__ / add / discard / clear
# ---------------------------------------------------------------------------
def test_g1_6_compat_layer_set_isomorphic():
    cap: DailyEmitCap[str] = DailyEmitCap()

    # __contains__ — mark_emitted 전
    assert ("009150" in cap) is False

    # add — set.add() 호환
    cap.add("009150")
    assert ("009150" in cap) is True
    assert cap.should_emit("009150") is False  # mark_emitted 와 동형

    # discard — set.discard() 호환 (존재하는 key)
    cap.discard("009150")
    assert ("009150" in cap) is False
    assert cap.should_emit("009150") is True

    # discard — 존재하지 않는 key 는 예외 없이 무시
    cap.discard("NON_EXISTENT")  # 예외 없어야 함

    # clear — set.clear() 호환
    cap.add("AAA")
    cap.add("BBB")
    assert len(cap) == 2
    cap.clear()
    assert len(cap) == 0
    assert cap.should_emit("AAA") is True


# ---------------------------------------------------------------------------
# G1-7 — 다중 인스턴스 격리
# ---------------------------------------------------------------------------
def test_g1_7_multiple_instances_isolated():
    cap_a: DailyEmitCap[str] = DailyEmitCap()
    cap_b: DailyEmitCap[str] = DailyEmitCap()

    cap_a.mark_emitted("X")

    # cap_a 에서 emit 된 key 가 cap_b 에 영향을 주면 안 된다
    assert cap_a.should_emit("X") is False
    assert cap_b.should_emit("X") is True

    # 반대 방향도 격리
    cap_b.mark_emitted("Y")
    assert cap_b.should_emit("Y") is False
    assert cap_a.should_emit("Y") is True

    # reset 도 격리
    cap_a.reset_daily()
    assert cap_a.should_emit("X") is True
    assert cap_b.should_emit("Y") is False  # cap_b 는 영향 없음
