"""실시간 계층의 **호출 가능 표면**을 핀한다 (2026-09-14 실사고 대응).

## 왜 sha 핀으로 부족한가

cycle294 작업 중 `src/realtime/websocket.py` 가 **구조적으로 파괴**된 상태가 워크트리에
남았다 — 모듈 레벨에 두어야 할 58줄 블록이 `class KisWebSocket:` **본문 안**에 들여쓰기 0
으로 삽입돼, 뒤따르던 `    async def subscribe(...)` 부터가 그 함수의 **중첩 함수**로
파싱됐다. 결과는 메서드 **19개 → 10개**:

    소실: subscribe · unsubscribe · get_subscribed_tickers · get_acked_tickers
          _send_subscribe · _receive_loop · _handle_raw
          _restore_subscriptions_after_reconnect · _verify_subscriptions_after_reconnect

**파이썬은 이것을 문법 오류로 잡지 않는다.** `import` 도 성공한다. 구독·해제·수신 루프·
체결통보 처리가 통째로 사라진 클래스가 정상으로 보인다. 배포됐다면 WS 전체가 죽고
그 순간 보유 종목 손절이 전부 멈춘다.

sha 핀(`_BASE_SHA` 계열)은 "파일이 바뀌었다" 만 말한다 — 승인된 변경 중에는 늘 바뀌므로
그 신호가 이 사고를 구별해 주지 못한다. 이 가드는 **무엇이 사라졌는지**를 말한다.

## 규약

정당하게 메서드를 추가/삭제하면 이 핀도 **같이 갱신한다**. 갱신할 때는 diff 를 눈으로 보고
"내가 의도한 추가/삭제인가" 를 확인한다 — 그 1초가 이 가드의 전부다.
핀 재산출: `python tools/test_fixtures/gen_ws_surface.py` 가 없으므로 아래 dict 를 손으로 맞춘다.
"""

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]

# 2026-09-14 기준 (cycle292 leaf 추출 + cycle293 2단계 + cycle294 3단계 착지 후)
_EXPECTED: dict[str, list[str]] = {
    "src/realtime/websocket.py::KisWebSocket": [
        "__init__",
        "_flush_ws_action_collector",
        "_handle_raw",
        "_heartbeat_metrics_emit_once",
        "_receive_loop",
        "_record_action",
        "_restore_subscriptions_after_reconnect",
        "_send_subscribe",
        "_trigger_auto_restart",
        "_verify_subscriptions_after_reconnect",
        "_ws_action_metrics_loop",
        "connect",
        "disconnect",
        "get_acked_tickers",
        "get_subscribed_tickers",
        "start",
        "stop",
        "subscribe",
        "unsubscribe"
    ],
    "src/realtime/websocket.py::<module>": [
        "_emit_legacy_reroute",
        "_is_rejection_response",
        "_probe_exclusion_today",
        "_reroute_legacy_unified",
        "is_probe_excluded",
        "register_probe_exclusion",
        "reset_probe_exclusions",
        "unregister_probe_exclusion"
    ],
    "src/realtime/websocket_pool.py::QuoteSessionExecutionNoticeError": [],
    "src/realtime/websocket_pool.py::WebsocketPool": [
        "__init__",
        "_available_quotes",
        "_emit_tick_channel_request_denied",
        "_reconnect_count",
        "_release_switch_routing",
        "_select_session",
        "_session_label",
        "_subscribed_at",
        "_subscriptions",
        "_subscriptions_acked",
        "_ws",
        "detect_dual_tick_channels",
        "disable_quote_session",
        "get_acked_tickers",
        "get_session_status",
        "get_subscribed_tickers",
        "get_subscriptions_by_session",
        "resend_subscribe_for_ticker",
        "session_of",
        "start",
        "stop",
        "subscribe",
        "switch_channel_same_session",
        "unsubscribe",
        "unsubscribe_all",
        "unsubscribe_in_pool"
    ],
    "src/realtime/websocket_pool.py::<module>": [
        "_cap_once",
        "_enforce_main_only_execution_notice",
        "_kst_today_str"
    ],
    "src/realtime/handler.py::<module>": [
        "_handle_execution",
        "_handle_market_op",
        "_handle_tick",
        "_kst_day_index",
        "_maybe_log_day_high_scope_skip",
        "_maybe_log_open_scope_observe",
        "_parse_acml_vol",
        "_parse_day_high",
        "_parse_tick_prices",
        "_tick_field_raw",
        "decrypt_aes_cbc",
        "dispatch_message",
        "flush_silent_drop_count",
        "register_board_handler",
        "register_execution_handler",
        "register_tick_handler",
        "reset_day_high_scope_skip",
        "reset_open_scope_observe",
        "set_aes_keys"
    ]
}


def _surface(rel: str) -> dict[str, list[str]]:
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out[f"{rel}::{node.name}"] = sorted(
                m.name for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    out[f"{rel}::<module>"] = sorted(
        n.name for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return out


@pytest.mark.parametrize("rel", sorted({k.split("::")[0] for k in _EXPECTED}))
def test_realtime_callable_surface_is_pinned(rel: str) -> None:
    actual = _surface(rel)
    expected = {k: v for k, v in _EXPECTED.items() if k.startswith(rel + "::")}
    assert set(actual) == set(expected), (
        f"{rel}: 클래스 집합이 바뀌었다 — "
        f"신규 {sorted(set(actual) - set(expected))} / 소실 {sorted(set(expected) - set(actual))}"
    )
    for key in sorted(expected):
        got, want = actual[key], expected[key]
        lost = sorted(set(want) - set(got))
        added = sorted(set(got) - set(want))
        assert not lost, (
            f"{key}: 메서드 {len(lost)}개가 **사라졌다** {lost}\n"
            "  ⚠️ 들여쓰기 사고로 뒤 메서드가 중첩 함수로 파싱됐을 수 있다"
            "(2026-09-14 실사고 — 이 파일 docstring 참조).\n"
            "  의도한 삭제라면 이 파일의 `_EXPECTED` 를 갱신하라."
        )
        assert not added, (
            f"{key}: 메서드 {len(added)}개 신규 {added} — 의도한 추가면 `_EXPECTED` 를 갱신하라."
        )


def test_kis_websocket_keeps_the_nine_that_matter() -> None:
    """🔴 이 아홉은 사라지면 매매가 죽는다 — 핀 갱신으로도 지울 수 없게 따로 못박는다."""
    must = (
        "subscribe", "unsubscribe",
        "get_subscribed_tickers", "get_acked_tickers",
        "_send_subscribe", "_receive_loop", "_handle_raw",
        "_restore_subscriptions_after_reconnect",
        "_verify_subscriptions_after_reconnect",
    )
    got = set(_surface("src/realtime/websocket.py")["src/realtime/websocket.py::KisWebSocket"])
    missing = [m for m in must if m not in got]
    assert not missing, (
        f"KisWebSocket 필수 메서드 소실: {missing} — "
        "구독/해제/수신/체결통보 중 하나가 죽으면 손절이 멈춘다"
    )
