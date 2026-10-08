"""cycle412 — 거래일지 워커가 읽는 **로그 문구** 고정(설계 관찰자안 6절 「생산 쪽 문구 고정」 · 8절 한계 1).

관찰자 방식에서는 로그 문구가 사실상 계약이다. 파일 통째 sha 핀은 「값만 이동」 재핀이 일상이라
파서를 지키지 못한다(`test_cycle291_ast_scope.py:127-150`). 그래서 **소비하는 줄의 포맷 문자열만**
소스 AST 의 문자열 상수로 고정한다(인접 리터럴은 AST 가 이어 붙인다). 소스를 읽기만 하므로 런타임 변경 0.

문구를 바꾸면 이 테스트가 붉어진다 → 같은 사이클에 `journal_worker/jw/grammar.py` 와 골든
(`journal_worker/tests/test_jw_grammar.py`)을 함께 고친다. 옛 문구 2개(`도치안 시간 기반 청산`·
`도치안 스윙 트레일링`)는 소스에서 이미 사라졌고 과거 로그 복원용으로만 grammar 에 남는다 — 여기서 고정하지 않는다.

이 파일은 소스를 읽기만 하고 src 를 import 하지 않는다. 지금 초록이어야 하는 가드다(Red 아님).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_PINS: dict[str, list[str]] = {
    "src/engine/order_engine.py": [
        "매수 주문 접수: %s %d주 @ %d (주문번호: %s, 전략: %s)",
        "%s 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)",
        "시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s)",
        "매도 시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s, 주문번호: %s, 전략: %s)",
        "손절 잔여 재주문: %s %d주",
    ],
    "src/api/order.py": ["%s 주문 완료: %s %s주 @ %s (주문번호: %s)"],
    "src/routes/trading.py": ["수동 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)%s"],
    "src/realtime/handler.py": [
        "[order_notice] ",
        "order_no=%s orig_order_no=%s side=%s rctf=%s kind=%s cond=%s "
        "ticker=%s qty=%s price=%s hour=%s rfus=%s acpt=%s ord_qty=%s",
    ],
    "src/engine/scheduler.py": [
        "stock_master nxt_tradable=False — 익일 청산 보류 (09:00 KRX 시장가 청산 예약): %s (전략: %s)",
        "NXT 시가 미수신 — 익일 청산 보류 (KRX 시가 확정 후 재시도): %s (전략: %s)",
        "익일 청산 보류 (갭 %.1f%% < 임계 %.1f%%, 09:00 KRX 시장가 청산 예약): %s (전략: %s)",
    ],
    "src/engine/strategies/kojiro.py": [
        "[kojiro_hard_stop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
        "[kojiro_atr_stop] %s 손절선(%d) = 매수가(%d) - %.1f×ATR(%.1f)",
        "[kojiro_trailing] %s 고점(%d) - %.1f×ATR(%.1f) = %d / 현재가 %d",
        "[kojiro_stage3_exit] %s 스테이지3 진입 (추세 종료) judged_on=%s",
        "고지로 매수 신호: %s 현재가(%d) — 스테이지1(6→1) + EMA정배열 + ATR(%.1f)",
    ],
    "src/engine/strategies/bull_flag_breakout.py": [
        "[bfb_turtle_stop] %s 손절선(%d) = 매수가(%d) − %.1f×entry_atr(%.1f)",
        "[bfb_turtle_backstop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
        "눌림목 손절: %s 매수가(%d) 대비 %.1f%%",
        "눌림목 측정된 이동 도달: %s 현재가(%d) ≥ 타겟(%d) — 익절 신호",
        "눌림목 시간 청산: %s buy_date=%s today=%s 보유일수 초과",
        "[bfb_vol_gate_pass] ticker=%s observed=%d threshold=%d latch_age_sec=%d",
    ],
    "src/engine/strategies/long_tail_volatility.py": [
        "롱테일VB 당일 손절: %s %.1f%%",
        "롱테일VB 손절(상한가 모드): %s %.1f%%",
        "롱테일 변동성 돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), K=%.4f",
    ],
    "src/engine/strategies/volatility_breakout.py": [
        "변동성돌파 손절: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
        "변동성돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), 이전가(%d), K=%.4f",
    ],
    "src/engine/strategies/momentum.py": [
        "손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)",
        "매수 신호: %s 전일종가(%d) 대비 %.1f%% (현재가: %d, 직전: %.1f%%)",
    ],
    "src/engine/strategies/donchian_swing.py": [
        "[donchian_time_exit] ticker=%s reason=%s days_held=%d high=%d target_1r=%d",
        "도치안 스윙 매수 신호: %s 현재가(%d) — 신고가(%d) 돌파 + EMA60(%d) 위 + ATR(%d)",
    ],
    "src/engine/strategies/vcp_breakout.py": [
        "[vcp_vol_gate_pass] ticker=%s observed=%d threshold=%d latch_age_sec=%d",
    ],
}


def _constants(rel: str) -> set[str]:
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


@pytest.mark.parametrize("rel,literal", [(r, lit) for r, lits in _PINS.items() for lit in lits])
def test_producer_format_literal_is_unchanged(rel, literal):
    assert literal in _constants(rel), (
        f"{rel} 에서 거래일지 워커가 읽는 로그 포맷이 바뀌었거나 사라졌다: {literal!r} — "
        "journal_worker/jw/grammar.py 와 골든 테스트를 같은 사이클에 고친다"
    )


def test_status_exit_fire_fstring_head_is_unchanged():
    tree = ast.parse((_ROOT / "src/engine/status_exit_watch.py").read_text(encoding="utf-8"))
    heads = []
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            parts = [v.value for v in n.values if isinstance(v, ast.Constant)]
            if parts and parts[0] == "[status_exit_fire] ticker=":
                heads.append(parts)
    assert heads, "`[status_exit_fire] ticker=` f-string 이 없다"
    assert any(" strategy=" in p and " reason=" in "".join(ps) for ps in heads for p in ps)


def test_order_notice_is_logged_at_info_with_the_pinned_prefix():
    """`[order_notice] ` + 포맷 이 `logger.info` 첫 인자로 이어 붙는 꼴이 그대로다."""
    tree = ast.parse((_ROOT / "src/realtime/handler.py").read_text(encoding="utf-8"))
    ok = False
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "info"
                and n.args and isinstance(n.args[0], ast.BinOp)
                and isinstance(n.args[0].left, ast.Constant) and n.args[0].left.value == "[order_notice] "):
            ok = True
    assert ok
