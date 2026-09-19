"""cycle291 Red — 범위 가드. 금지 파일 diff 0 + GTP 게이트의 구조 계약.

정본 = cycle291 도메인 자문(2026-09-13). 접촉 허용 프로덕션 파일 =
`src/models/order.py` · `src/engine/order_engine.py` · `src/api/order.py` 셋뿐
(뒤 둘은 8영역, 사용자 승인).

## 이 파일이 지키는 것

* **A1** 금지 파일의 내용 sha — 특히 `scheduler.py`(cycle291 착수 시점 3,897L · 상한
  3,900 · 여유 3줄. 예고한 cycle292 리팩터가 실제로 수행돼 **3,726L / 여유 174줄**이
  됐고, 그 사이클이 A1·A2 핀을 새 기준선으로 옮겼다)와 전략 7파일(cycle290 이 방금
  `DEFAULT_PARAMS` 에 키 2개를 넣었다 — 또 건드리면 그 "+8/-0" 증명이 무너진다).
* **A2** `scheduler.py` 라인 수 정확 일치 + 영구 상한.
* **A3** cycle287 frozen 세그먼트 중 **매도** 프리장 사전변환은 자문 판정대로 **불변**
  (`execute_buy_prf` 는 이 사이클이 정당하게 바꾸므로 여기서 재지 않는다 — cycle287
  쪽 핀을 새 sha 로 **교체**하는 것이 Green 의 일이다).
* **A4** cycle290 킬스위치 읽기 지점 보존(`after_market_exit_division` 등장 횟수).
* **A5** `execute_buy` 의 화이트리스트 제거 — `== OrderDivision.LIMIT` 열거가 GTP 를
  조용히 삼키는 함정이다(`place_kwargs` 게이트 + `record_price` 게이트 두 곳).
* **A6** GTP 게이트에 **날짜·시각 리터럴 금지** — `market_state` 표를 읽는다.
* **A7** `order_engine.py` 최상단 `src.*` import 집합 불변(신규 import 는 함수 지역).
* **A8** `src/engine/*.py` 신규 leaf 금지.
* **A9** `_SENDABLE_DIVISIONS` 가 enum 파생이고, `27`(및 `28`/`29`)을 더해도
  `_route_exchange_by_clock` 판정이 **diff 0** 이다(사전조사 실증을 봉인).
* **A10** `_order_division` 의 선언·clear 자리 + `scheduler.py` 무참조.
* **A11** 취소 축 Stage A — `cancel_order` 본문 문장 수 8 유지(cycle287 `test_s4c2`
  와 같은 계약) · 화이트리스트 금지.

⚠️ 이 파일의 sha dict 이름은 **`_BASE_SHA`** 다(`*_CONTENT_SHA` 금지 —
`test_cycle223g3::test_g3_9a` 의 `_PIN_GUARD_FILES` 4개가 고정 목록이다).
⚠️ `src/models/order.py` 를 sha 핀 dict 키로 쓰지 않는다(cycle287 `test_s4b`).
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_ORDER_ENGINE_REL = "src/engine/order_engine.py"
_API_ORDER_REL = "src/api/order.py"

KST_TZ = timezone(timedelta(hours=9))
#: 제도 변경 시행일 — `market_state._REFORM_DAY` 와 같은 값(리터럴은 테스트에만 둔다).
_REFORM = date(2026, 9, 14)


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _function(rel: str, name: str) -> tuple[str, ast.AST]:
    src = _src(rel)
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel} 에 `{name}` 부재")


# ===========================================================================
# A1 — 금지 파일 내용 sha (착수 시점 = cycle290 배포분 `d4cfdec`)
# ===========================================================================
_BASE_SHA: dict[str, str] = {
    # 8영역 — 엔진 (order_engine 은 이 사이클의 접촉 대상이라 **제외**)
    "src/engine/risk.py":
        "e8614235cc0bea638f8c349b2f6910c94f5f9a5b849f5d65bef0583f959d81c9",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle302(2026-09-18) 재핀 — 사용자 승인 일봉 backfill **대상** 확대
    #    (분기에서 지수 소속 판정 제거 · `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수는 불변). 값만 옮긴다 — 단언은 그대로다.
    #    구 값은 cycle299 기준선(3b7366cc…)이다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    # 8영역 — realtime 전부
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 8영역 — auth 전부
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "bfbdcfbe2bd595055bcc38f5e094e2815ef67854f2153aa20c40629c9e4e6764",
    # ⚠️ cycle292(2026-09-14) 재핀 — `_subscribe_market_operation_tickers` 176줄을
    # 신규 leaf `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임
    # wrapper · 3,897→3,726L, 사용자 승인). 여섯 자매 핀(cycle274/276/278/282/290/291)
    # 을 **한 값으로 동시에** 옮겼다 — 한 곳만 넣으면 나머지가 "코드를 되돌려라" 로
    # 붉어져 승인된 변경을 되돌리도록 오도한다. 직전 값 =
    # `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`.
    # 🔴 cycle291 시점: 라인 상한 3,900 에 3줄 남아 한 줄도 금지였다. cycle292 가
    # 예고대로 리팩터해 3,726L 이 됐다(아래 핀 = 그 결과).
    "src/engine/scheduler.py":
        "088d54efc4927899c1048d01ea7c15265ce87858da25447ac28a1ffaa56f3c23",
    # 🔴 cycle290 이 방금 `DEFAULT_PARAMS` 를 건드렸다 — 또 건드리면 그 증명이 무너진다.
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    "src/engine/strategies/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py":
        "0feb3b629bab5ad08ad589315ca12e76b57a73950b948570a78dfe84ba792595",
    "src/engine/strategies/donchian_swing.py":
        "cc57e5673f9982aca97f61677084e040171fff307483fedf10459b567a4679e3",
    "src/engine/strategies/kojiro.py":
        "9477790e9d20eb6d17f36fc7586ada77ac5e2e4b0136a334888244afdb7e9cbc",
    "src/engine/strategies/long_tail_volatility.py":
        "51b50560a1240df3fc6085da7253438605079d7d453ff3e77a806e814473be25",
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/vcp_breakout.py":
        "5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228",
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
    # 파라미터 축 — 킬스위치를 임의로 추가하지 않는다(자문 §5: 파라미터 없음).
    "src/engine/param_catalog.py":
        "babaf208053331a9a8487b7b1f79b0d8b569225d0e694370510ce7633cf318c1",
    "src/engine/param_validation.py":
        "b4c5c029800191523bcc511919d6de3774e9ab49ca2fc0a0558ee3907868ee17",
    # 시각·호가유형 표의 유일 정본 — GTP 게이트는 이 표를 **읽는다**(수정 금지).
    "src/engine/market_state.py":
        "7cef2efeb55a7184391ac2cc447c90102fdd7ba507fd6e3834d24a8ad9ce006b",
}

#: ⚠️ cycle292(2026-09-14) 가 `_subscribe_market_operation_tickers` 176줄을
#: 신규 leaf `src/engine/market_op_subscribe.py` 로 추출해(행위 변경 0 · 5줄
#: 위임 wrapper) 3,897 → 3,726 이 됐다. 값만 옮긴다 — 정확 핀을 상한 핀으로
#: 완화하면 cycle291 의 무접촉 대리 지표가 사라진다.
_SCHEDULER_LINES = 3785
_SCHEDULER_LINE_CAP = 3900


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_a1_forbidden_files_are_byte_identical(rel: str) -> None:
    """A1 — 금지 파일의 내용 sha 가 착수 시점과 같다.

    붉어지면 핀을 옮기지 말고 **변경을 되돌려라**. `order_engine.py`·`api/order.py`·
    `models/order.py` 세 파일만이 이 사이클의 접촉 대상이다.
    """
    got = _sha(_src(rel))
    assert got == _BASE_SHA[rel], (
        f"{rel} 가 바뀌었다 — cycle291 의 접촉 범위는 `order_engine.py`·`api/order.py`·"
        f"`models/order.py` 뿐이다. 현재 sha={got}"
    )


def test_a2_scheduler_line_count_is_pinned_under_the_permanent_cap() -> None:
    """A2 — `scheduler.py` 라인 수 정확 일치 + cycle257 영구 상한 3,900.

    여유가 **3줄**이고 오늘 cycle292 가 이 파일을 리팩터한다. `_order_division` 의
    clear 를 `scheduler._reset_daily_state` 에 두면 여기가 붉어진다 —
    `OrderEngine.reset_daily_state()` 위임 쪽이 정답이다.
    """
    lines = len(_src("src/engine/scheduler.py").splitlines())
    assert lines == _SCHEDULER_LINES, f"scheduler.py = {lines}L (착수 시점 {_SCHEDULER_LINES}L)"
    assert lines < _SCHEDULER_LINE_CAP, f"라인 상한 {_SCHEDULER_LINE_CAP} 초과: {lines}"


# ===========================================================================
# A3 — cycle287 frozen 세그먼트: **매도** 프리장 사전변환은 불변 (자문 §2)
# ===========================================================================
#: (시작 부분문자열, 끝 부분문자열, sha256) — cycle287 `_FROZEN_SEGMENTS` 와 같은 값.
_SELL_PRECONVERT_SEGMENT = (
    "        if order_division == OrderDivision.MARKET:\n            try:\n"
    "                from src.engine.scanner import ticker_prices as _tp",
    "                    ticker, exc_info=True,\n                )\n",
    "768b9f144b95bcfcfb7f3110b20e71d6588f36e8aa93af3e28a77f141922ecaf",
)


def test_a3_sell_pre_nxt_preconvert_block_is_byte_identical() -> None:
    """A3 — 프리장 **매도** 사전 지정가 변환 블록 byte 동일 (매수만 바꾼다).

    자문 §2-b: GTP 매도는 08:50 거래소 취소가 `_selling` 을 ≈09:45 까지 잠가 손절
    재평가를 억제한다(거래소발 취소는 체결통보를 만들지 않아 어느 해제 경로에도
    안 걸린다). 루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상
    작동」 에 저촉하므로 이 블록은 이 사이클에서 **손대지 않는다**.
    """
    start, end, want = _SELL_PRECONVERT_SEGMENT
    src = _src(_ORDER_ENGINE_REL)
    i = src.find(start)
    assert i >= 0, "매도 프리장 사전변환 블록의 시작 앵커가 사라졌다"
    j = src.find(end, i)
    assert j >= 0, "매도 프리장 사전변환 블록의 끝 앵커가 사라졌다"
    got = _sha(src[i:j + len(end)])
    assert got == want, (
        f"매도 프리장 사전변환 블록이 바뀌었다 — 자문 판정은 **매수만**이다. sha={got}"
    )


def test_a4_cycle290_killswitch_read_sites_are_preserved() -> None:
    """A4 — cycle290 킬스위치(`after_market_exit_division`) 읽기 지점 보존.

    애프터 청산 경로를 건드리지 않았다는 것의 가벼운 증언이다(세밀한 봉인은
    cycle287/290 쪽 가드가 한다).
    """
    src = _src(_ORDER_ENGINE_REL)
    assert src.count("after_market_exit_division") == 4, (
        f"킬스위치 읽기 지점 수가 {src.count('after_market_exit_division')} 로 바뀌었다"
    )
    assert "_AFTER_EXIT_DIVISION_ALLOWED" in src
    assert "_AFTER_EXIT_DIVISION_DEFAULT" in src


# ===========================================================================
# A5 — `execute_buy` 화이트리스트 제거 (GTP 를 조용히 삼키는 함정)
# ===========================================================================
def test_a5_execute_buy_has_no_limit_equality_whitelist() -> None:
    """A5 (RED) — `execute_buy` 에 `== OrderDivision.LIMIT` 열거가 **없다**.

    현재 두 곳이 그 열거다:

    * `place_kwargs["order_division"]` 게이트 — GTP 면 조건이 false 라 키가 빠지고
      `place_order` 기본값 **시장가 `01`** 로 나간다 = 프리장 100% 거부(APBK0918).
    * `record_price` 게이트 — GTP 면 `current_price`(변환 **전**)가 기록된다.

    둘 다 `!= OrderDivision.MARKET` 로 뒤집으면 새 호가유형이 자동으로 따라온다
    (cycle287 `test_s4d` 의 화이트리스트 금지 원칙과 같은 규율).
    """
    src, fn = _function(_ORDER_ENGINE_REL, "execute_buy")
    seg = ast.get_source_segment(src, fn) or ""
    hits = seg.count("== OrderDivision.LIMIT")
    assert hits == 0, (
        f"`execute_buy` 에 `== OrderDivision.LIMIT` 화이트리스트가 {hits}곳 남았다 — "
        "GTP 가 조용히 시장가로 떨어지거나 기록 가격이 변환 전 값으로 샌다"
    )


def test_a5b_execute_buy_passes_the_division_variable_not_a_literal() -> None:
    """A5 (RED) — `place_kwargs["order_division"]` 에 **변수**를 넣는다.

    리터럴 `OrderDivision.LIMIT` 재지정이 남아 있으면 GTP 대입이 무효화된다.
    """
    src, fn = _function(_ORDER_ENGINE_REL, "execute_buy")
    seg = ast.get_source_segment(src, fn) or ""
    assert 'place_kwargs["order_division"] = OrderDivision.LIMIT' not in seg, (
        "`place_kwargs` 에 리터럴이 재지정된다 — GTP 승격이 무효화된다"
    )
    assert 'place_kwargs["order_division"] = order_division' in seg, (
        "`place_kwargs` 가 `order_division` 변수를 그대로 싣지 않는다"
    )


def test_a6_gtp_gate_has_no_date_or_time_literals() -> None:
    """A6 (RED) — GTP 게이트는 날짜·시각 리터럴을 새로 적지 않는다.

    시행일(2026-09-14)과 프리마켓 종료(08:50)는 `market_state.MARKET_TABLE` 의
    유일 정본에 있고, 게이트는 그 표의 `order_divisions` 에 `27` 이 있는지만 본다.
    리터럴을 복제하면 다음 제도 변경에서 두 곳이 갈린다.
    """
    src, fn = _function(_ORDER_ENGINE_REL, "execute_buy")
    # docstring(사이클 이력에 날짜가 잔뜩 있다)과 `#` 주석을 걷어낸 **코드만** 본다.
    stmts = [
        n for n in fn.body
        if not (
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
    ]
    code = "\n".join(
        line.split("#", 1)[0]
        for stmt in stmts
        for line in (ast.get_source_segment(src, stmt) or "").splitlines()
    )
    for needle in ("2026", "date(", "time(8", "08:50", "8, 50"):
        assert needle not in code, (
            f"`execute_buy` 코드에 시각·날짜 리터럴 {needle!r} 이 들어왔다 — "
            "판정은 `market_state` 표를 읽어야 한다"
        )
    assert "get_market_state" in code, (
        "GTP 게이트가 `market_state` 표를 읽지 않는다 — 날짜·시각 차원이 공짜가 아니다"
    )


def test_a7_order_engine_top_level_src_imports_are_unchanged() -> None:
    """A7 (RED) — `order_engine.py` 최상단 `src.*` import 집합 불변.

    신규 import(`market_state`·`settings`)는 전부 **함수 안 지역 import** 다
    (cycle276 `_BASE_ORDER_ENGINE_SRC_IMPORTS` · cycle286 `test_g4` · cycle287
    `test_s3e` 와 같은 계약 — 최상단에 올리면 순환 import 와 부팅 순서가 흔들린다).
    """
    tree = ast.parse(_src(_ORDER_ENGINE_REL))
    got = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
            got.add(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src"):
                    got.add(alias.name)
    assert got == {
        "src.api.balance", "src.api.base", "src.api.order", "src.db.system_logs",
        "src.db.trade_history", "src.engine", "src.engine.daily_emit_cap",
        "src.engine.scanner", "src.engine.sell_rejection", "src.engine.strategy_base",
        "src.engine.strategy_registry", "src.engine.util.tick_size",
        "src.models.order", "src.models.trade",
    }, f"최상단 src import 집합이 바뀌었다: {sorted(got)}"


def test_a8_no_new_leaf_in_src_engine() -> None:
    """A8 — `src/engine/*.py` 신규 파일 금지(cycle291 은 leaf 를 만들지 않았다).

    ⚠️ cycle292(2026-09-14)가 `market_op_subscribe.py` 를 **승인 하에** 신설해 60 → 61
    이 됐다(`scheduler.py` 라인 상한 3,900 예산 확보 — 176줄 추출, 행위 변경 0).
    값만 새 기준선으로 옮긴다 — 단언 형태는 그대로라 다음 사이클의 무단 신규 파일은
    여전히 붉어진다. 이름 축 가드는
    `test_cycle290_ast_scope.py::test_g290_3_no_new_module_under_src_engine` 다.

    ⚠️ cycle293(2026-09-14)이 킬스위치 leaf `tick_channel_mode.py` 를 **승인 하에**
    신설해 61 → 62 가 됐다. 리졸버 모드를 전략 `DEFAULT_PARAMS` 가 아니라 인프라 축
    (`system_config` 한 키)에 두기로 한 결정의 산물이고(cycle287 이 킬스위치를
    `param_catalog` 미등재로 만들어 장중에 끌 수 없었던 실패의 시정), `scheduler.py`
    는 무접촉이다.

    ⚠️ cycle294(2026-09-14, 시세 채널 3단계)가 leaf 2개를 **승인 하에** 신설해
    62 → **64** 가 됐다 — `tick_channel_clock.py`(시각축 판정: 구간 경계 셋을
    `market_state.get_market_table` 에서만 파생, 시각 리터럴 0건)와
    `tick_channel_switch.py`(전환 창 안의 HIGH make-before-break 전환 + 09:03
    자동 원복). `scheduler.py` 무접촉 계약이 그 둘을 기존 주기 루프
    (`stale_watcher_core.check_and_resubscribe_stale`, 120초)에 얹게 만들었다.

    ⚠️ cycle297(2026-09-17, LLM 매수평가 5전략 shadow 확대)이 leaf 1개
    `llm_retrospective.py` 를 신설해 64 → **65** 가 됐다 — 주간 회고 조인·집계
    순수 함수(`src.*` import 0). "매수 시점 점수 ↔ 청산 손익" 조인 정의를 라우트·
    SQL 뷰가 아니라 이 leaf 하나로 둔다(명세 §3.5 기각안 참조). `scheduler.py`
    무접촉.
    """
    got = len(list((_ROOT / "src" / "engine").glob("*.py")))
    assert got == 65, f"`src/engine/*.py` 파일 수 {got} (cycle297 기준선 65)"


# ===========================================================================
# A9 — `_SENDABLE_DIVISIONS` 확장의 라우팅 무영향 (사전조사 실증 봉인)
# ===========================================================================
def test_a9_sendable_divisions_is_derived_from_the_enum() -> None:
    """A9 — `_SENDABLE_DIVISIONS` 는 enum 파생이다(수동 열거 금지).

    수동 열거면 enum 에 `27` 을 더해도 집합이 안 커져 두 정본이 조용히 갈린다.
    """
    from src.engine.order_engine import _SENDABLE_DIVISIONS
    from src.models.order import OrderDivision

    assert set(_SENDABLE_DIVISIONS) == {d.value for d in OrderDivision}, (
        f"{sorted(_SENDABLE_DIVISIONS)} != {sorted(d.value for d in OrderDivision)}"
    )


@pytest.mark.parametrize("extra", [("27",), ("27", "28", "29")])
def test_a9b_adding_gtp_codes_does_not_change_any_routing_verdict(
    monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    """A9 (봉인) — `_SENDABLE_DIVISIONS` 에 GTP 코드를 더해도 라우팅 판정 **diff 0**.

    사전조사 실증: 09-14 하루 1,440분 × base{NXT, SOR} × side{buy, sell} 전수 스윕에서
    `(routed, reason)` 이 한 건도 달라지지 않는다 — `27/28/29` 를 갖는 유일한 행이
    N1(08:00~08:50)이고 그 구간은 clause 4 `pre_nxt_keep` 이 먼저 반환하며, KRX 어느
    행에도 GTP 가 없어 clause 5(거래소를 바꾸는 유일한 절)가 불변이기 때문이다.
    미래에 `_SENDABLE_DIVISIONS` 나 보드표를 손대면 이 가드가 알려 준다.

    적대 검증 시정(spec 렌즈 MEDIUM) — `_SENDABLE_DIVISIONS` 는 enum 파생이라
    **이미 `27`(및 `28`/`29`)을 담고 있다**. `before` 를 손대지 않은 현재값에서
    재면 `before == after` 가 그 자체로 항등이 되어 이 사이클이 실제로 추가한
    값의 라우팅 무영향이 측정되지 않는다(28/29 만 실측되던 결함). `before` 를
    **`extra` 를 뺀 09-13 이전 세계**로 계산해야 "27 추가 전 ↔ 후" 가 진짜로
    갈린다.
    """
    from src.engine import order_engine as _oe
    from src.engine.session import boards_at, session_tracker

    base_fn = _oe._route_exchange_by_clock
    baseline = frozenset(set(_oe._SENDABLE_DIVISIONS) - set(extra))
    assert baseline != frozenset(_oe._SENDABLE_DIVISIONS), (
        "baseline 이 현재값과 같다 — extra 제거가 공회전했다(가드 자체가 무력화)"
    )
    before: dict = {}
    after: dict = {}

    def _sweep(sink: dict) -> None:
        for minute in range(0, 24 * 60):
            moment = datetime(
                _REFORM.year, _REFORM.month, _REFORM.day,
                minute // 60, minute % 60, tzinfo=KST_TZ,
            )
            session_tracker._active = boards_at(moment.time())
            for base in ("NXT", "SOR"):
                for side in ("buy", "sell"):
                    sink[(minute, base, side)] = base_fn(base, side=side, now=moment)

    original_active = session_tracker._active
    try:
        monkeypatch.setattr(_oe, "_SENDABLE_DIVISIONS", baseline)
        _sweep(before)
        monkeypatch.setattr(_oe, "_SENDABLE_DIVISIONS", frozenset(baseline | set(extra)))
        _sweep(after)
    finally:
        session_tracker._active = original_active

    diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert diff == {}, f"GTP 코드 추가가 라우팅을 바꿨다: {sorted(diff)[:5]} (총 {len(diff)})"


# ===========================================================================
# A10 — `_order_division` 의 자리
# ===========================================================================
def test_a10_order_division_is_declared_in_init_and_cleared_in_reset() -> None:
    """A10 (RED) — 선언은 `__init__`, clear 는 `OrderEngine.reset_daily_state()`.

    `_order_exchange`(cycle287) 와 **같은 자리·같은 정리 주기**여야 한다 — order_no 는
    하루 단위로만 유일하므로 clear 를 빼면 무한 성장이다.
    """
    src, init = _function(_ORDER_ENGINE_REL, "__init__")
    init_seg = ast.get_source_segment(src, init) or ""
    assert "self._order_division" in init_seg, (
        "`_order_division` 이 `__init__` 에 선언되지 않았다"
    )
    assert "self._order_exchange" in init_seg, "선례 선언이 사라졌다"

    _s, reset = _function(_ORDER_ENGINE_REL, "reset_daily_state")
    reset_seg = ast.get_source_segment(src, reset) or ""
    assert "self._order_division.clear()" in reset_seg, (
        "`reset_daily_state()` 가 `_order_division` 을 clear 하지 않는다"
    )
    assert "self._order_exchange.clear()" in reset_seg, "선례 clear 가 사라졌다"


def test_a10a_buy_main_registration_reads_from_place_kwargs_not_a_local_name() -> None:
    """A10 (봉인, 적대 검증 시정 — 테스트 렌즈 LOW #7) — 매수 주 경로 등록문의
    우변이 `place_kwargs` 에서 뽑은 변수를 읽는다(지역변수 `order_division` 을
    직접 읽지 않는다).

    "전송한 것만 기록한다" 계약은 B2 화이트리스트 게이트가 정상일 때는 두 값이
    같아 **행위로는 구별되지 않는다**(등가 변이) — B2 가 회귀했을 때만 갈라진다.
    그 미래 회귀를 지금 봉인하려면 소스 구조 자체가 `place_kwargs` 를 읽는지
    확인해야 한다: `self._order_division[result.order_no] = <X>.value` 에서
    `<X>` 는 그 위에서 `place_kwargs.get(` 호출로 대입된 이름이어야 한다.
    """
    src, fn = _function(_ORDER_ENGINE_REL, "execute_buy")
    candidates = [
        node for node in ast.walk(fn)
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Attribute)
            and node.targets[0].value.attr == "_order_division"
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
        )
    ]
    assert candidates, (
        "`self._order_division[...] = <name>.value` 형태의 등록문을 찾지 못했다"
    )
    # 등록 지점이 여럿(주 경로 + 폴백)일 수 있다 — 소스상 **가장 먼저** 나오는 것이
    # "주 경로" 다(`ast.walk` 은 BFS 라 line 순서를 보장하지 않으므로 직접 정렬한다).
    assign_target = min(candidates, key=lambda n: n.lineno)
    rhs_name = assign_target.value.value
    assert isinstance(rhs_name, ast.Name), (
        f"우변이 이름이 아니다: {ast.dump(assign_target.value)}"
    )
    var_name = rhs_name.id
    assert var_name != "order_division", (
        "매수 주 경로가 지역변수 `order_division` 을 직접 읽는다 — "
        "`place_kwargs` 에서 뽑은 별도 변수를 거쳐야 B2 회귀와 매핑이 함께 갈라진다"
    )
    # 그 변수가 실제로 `place_kwargs.get(` 대입에서 왔는지 확인한다.
    source_assign = None
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == var_name
        ):
            source_assign = node
            break
    assert source_assign is not None, f"`{var_name}` 대입문을 찾지 못했다"
    seg = ast.get_source_segment(src, source_assign) or ""
    assert "place_kwargs.get(" in seg, (
        f"`{var_name}` 이 `place_kwargs.get(...)` 에서 대입되지 않았다: {seg!r}"
    )


def test_a10ab_cancel_order_call_sites_never_pass_order_division_yet() -> None:
    """A10 (봉인, 적대 검증 시정 — 테스트 HIGH #1) — 취소 호출 3곳 전부 `order_division`
    키워드를 전달하지 않는다(Stage A).

    `test_c9` 는 런타임으로 `_cancel_after_wait` **한 곳만** 잰다. 실측 뮤테이션
    — `_cancel_and_reorder`(정규장 부분체결 손절 잔여, **실적 있는 유일한 취소
    경로군**)나 `cancel_remaining` 에 `order_division=<매핑값>` 을 몰래 추가해도
    그 런타임 테스트는 통과했다. 소스 전수로 3곳을 함께 잠근다 — 호출부 수가
    3에서 벗어나도(신규 취소 경로 추가) 이 가드가 먼저 반응한다.
    """
    tree = ast.parse(_src(_ORDER_ENGINE_REL))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == "cancel_order"
    ]
    assert len(calls) == 3, (
        f"`cancel_order(` 호출부 수가 {len(calls)} — 3(`_cancel_after_wait`/"
        "`_cancel_and_reorder`/`cancel_remaining`)에서 벗어났다. 새 취소 경로라면 "
        "이 가드에 그 경로도 명시적으로 포함하라"
    )
    for call in calls:
        kw_names = {kw.arg for kw in call.keywords}
        assert "order_division" not in kw_names, (
            f"L{call.lineno} 의 `cancel_order` 호출이 `order_division` 을 전달한다 — "
            "Stage A 계약 위반(정본에 승계 규약이 없고, 전송을 켜면 실적 있는 "
            "정규장 부분체결 취소의 `ORD_DVSN` 이 `00`→`01` 로 바뀐다)"
        )


def test_a10b_scheduler_never_touches_the_new_mapping() -> None:
    """A10 — `scheduler.py` 는 `_order_division` 을 언급하지 않는다(diff 0 의 이면)."""
    assert "_order_division" not in _src("src/engine/scheduler.py"), (
        "`scheduler.py` 가 새 매핑을 참조한다 — clear 는 `reset_daily_state()` 위임이다"
    )


def test_a10c_mapping_is_registered_at_every_place_order_success_site() -> None:
    """A10 (RED) — 등록은 `_order_exchange` 와 **같은 횟수**(cycle295 부터 5곳)다.

    매수 주 경로 · 매수 지정가 폴백 · 매도 주 경로 · 매도 폴백 · (cycle295 D,
    §2-0b) 손절 잔여 재주문(`_cancel_and_reorder`). 다섯 번째 자리 전에는
    그 재주문이 매핑을 남기지 않아 체결통보가 `_order_strategy` miss →
    `trade_history` miss → `"momentum"` 오귀속으로 흘렀다(D 축 실측). 한 곳만
    빠뜨리면 그 경로의 취소 관측이 조용히 `dvsn_src=absent` 로 퇴화한다.
    """
    src = _src(_ORDER_ENGINE_REL)
    ex_sets = src.count("self._order_exchange[")
    div_sets = src.count("self._order_division[")
    assert ex_sets == 5, f"선례 등록 지점 수가 {ex_sets} 로 바뀌었다"
    assert div_sets == ex_sets, (
        f"`_order_division` 등록 {div_sets}곳 / `_order_exchange` {ex_sets}곳 — "
        "같은 자리여야 한다"
    )
    assert src.count("self._order_division.pop(") == src.count(
        "self._order_exchange.pop("
    ), "pop 지점 수가 선례와 다르다(전량 체결 2곳)"


# ===========================================================================
# A11 — 취소 축 Stage A
# ===========================================================================
def test_a11_cancel_order_body_statement_count_is_unchanged() -> None:
    """A11 — `cancel_order` 본문 문장 수 **8** 유지(cycle287 `test_s4c2` 와 같은 계약).

    `ORD_DVSN` 은 body dict **안의 조건식 하나**로만 표현한다 — 문장을 늘리면 그
    자매 가드가 붉어진다.
    """
    _s, fn = _function(_API_ORDER_REL, "cancel_order")
    body = [
        n for n in fn.body
        if not (
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
    ]
    assert len(body) == 8, (
        f"`cancel_order` 본문 문장 수 {len(body)} (base 8) — dict 안 조건식 하나로 표현하라"
    )


def test_a11b_cancel_order_has_no_value_whitelist() -> None:
    """A11 (RED) — `cancel_order` 에 호가유형 값 화이트리스트가 없다.

    `if order_division in ("00", "01", ...)` 류를 끼워 넣으면 다음 코드가 조용히
    `"00"` 으로 되돌아간다(cycle287 `test_s4d` 원칙 승계). 허용되는 판정은 falsy
    검사 하나뿐이다.
    """
    src, fn = _function(_API_ORDER_REL, "cancel_order")
    seg = ast.get_source_segment(src, fn) or ""
    for needle in ('order_division in (', 'order_division in [', 'order_division in {',
                   'order_division not in (', 'order_division not in [',
                   'order_division not in {',
                   'order_division ==', 'order_division !='):
        assert needle not in seg, (
            f"`cancel_order` 에 값 비교 {needle!r} 가 들어왔다 — 화이트리스트 금지"
        )


def test_a11c_place_order_still_passes_the_value_through() -> None:
    """A11 — `place_order` 는 `ORD_DVSN` 을 값 그대로 흘려보낸다(무접촉 확인)."""
    src, fn = _function(_API_ORDER_REL, "place_order")
    seg = ast.get_source_segment(src, fn) or ""
    assert '"ORD_DVSN": order_division.value' in seg
    body = [
        n for n in fn.body
        if not (
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
    ]
    assert len(body) == 9, f"`place_order` 본문 문장 수 {len(body)} (base 9)"


def test_a11d_cancel_docstring_still_records_the_unknown() -> None:
    """A11 (RED) — `cancel_order` docstring 이 **Stage A/B** 와 미지 상태를 적는다.

    다음 사람이 opt-in 인자를 보고 "검증됐다" 고 오독하지 않게 한다 — 정본에 승계
    규약이 **없고**(선물옵션은 `[취소] 01 로 입력` 고정값), 전환은 매매 행위 변경 =
    별도 승인이라는 사실이 함수 옆에 있어야 한다.
    """
    _s, fn = _function(_API_ORDER_REL, "cancel_order")
    doc = ast.get_docstring(fn) or ""
    assert "order_division" in doc, "opt-in 인자 설명이 docstring 에 없다"
    for needle in ("미검증", "미실측", "미확인"):
        if needle in doc:
            break
    else:
        raise AssertionError(f"미지 상태 표기가 사라졌다 — {doc!r}")
    assert "byte 동일" in doc or "byte동일" in doc, (
        "미전달 시 현행 byte 동일이라는 계약이 docstring 에 없다"
    )
