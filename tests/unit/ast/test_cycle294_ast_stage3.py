"""cycle294 Red (3단계 · 시간축 전환 · **통합 채널 소멸**) — AST/정적 가드.

명세 = `_workspace/red/cycle294_stage3_time_axis_spec.md` (§12 G-294-1~15)
행위 자매 = `tests/unit/engine/test_cycle294_stage3.py`
선행 = cycle292(장운영 구독 leaf) + cycle293(2단계 속성축 배관) — 둘 다 **미커밋
워크트리**. 이 파일의 모든 sha 는 **그 워크트리** 기준으로 산출했다.

## 이 사이클이 뒤집는 것 (재론 금지)

`H0UNCNT0`(통합) 구독을 **0** 으로 만든다. 09-15 07:45 부팅부터 `H0STCNT0`(KRX
전용) + `H0NXCNT0`(NXT 전용) 2채널이다. 근거 = 2026-09-07 사용자 결정 +
2026-09-14 재확인 + 09-14 16:39~16:41 라이브 실측(`H0STCNT0` 이 `nxt_false`·
`nxt_true` 가릴 것 없이 KRX 애프터마켓 체결을 실었다).

```
08:00~08:50  프리장        → H0NXCNT0
08:50~09:00  전환 창        → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
09:00~20:00  정규장+애프터  → H0STCNT0   (전환 0회, 연속)
```

## 이 파일이 잠그는 것

| ID | §12 | 잠그는 것 |
|----|-----|-----------|
| A1~A2 | G-294-12/13 | 금지 파일 byte 동일 · `scheduler.py` 3,726L · 앞 두 사이클 미회귀 |
| A3~A7 | G-294-1/2 | 시각축 leaf 존재·순수 · **시각 리터럴 0건** · `get_market_table` 공개 API · `match_kind` 질의 · **통합 반환 0건** |
| A8~A10 | §1-E | `_resolve_channel` 합성 · `_classify_channel` byte 동일 · `now` 주입구 |
| A11~A15 | 🔴 G-294-6 | **매수 축 코호트** — 게이트가 채널이 아니라 코호트를 읽는다 |
| A16~A19 | G-294-4/5/7 | 전환 leaf · **make-before-break** · 세션 고정 · 120초 트리거 |
| A20 | G-294-11 | 레거시 재라우팅 스코프(통합만) |
| A21~A22 | G-294-15 | 파라미터 4키 = `system_config` 축 · 180초 = `SUBSCRIBE_GRACE_SECS` 재사용 |
| A23~A25 | §11-A · G-294-14 | 마커 12종 존재 · 순수성 |
| A26 | 금기 1 | `TICK_TR_ID` **상수는 보존**(반환 경로에서만 사라진다) |

## 🔴 공허 가드 금지 — 모듈 부재는 SKIP 이 아니라 FAIL

신규 leaf 2파일(`tick_channel_clock.py` · `tick_channel_switch.py`)이 없으면
`_require()` 가 **FAIL** 한다. `pathlib.exists()` 로 감싸 조용히 통과시키면
그 가드는 구현이 끝날 때까지 초록이고, 끝난 뒤에도 아무도 붉게 만들지 못한다.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

_SCANNER_REL = "src/engine/scanner.py"
_RISK_REL = "src/engine/risk.py"
_WS_REL = "src/realtime/websocket.py"
_POOL_REL = "src/realtime/websocket_pool.py"
_SWC_REL = "src/engine/stale_watcher_core.py"
_MODE_REL = "src/engine/tick_channel_mode.py"
_DIAG_REL = "src/engine/stale_diagnostics.py"
_SYSCONF_REL = "src/db/system_config.py"
_ROUTES_REL = "src/routes/realtime.py"

#: 🔴 신규 leaf 2파일 (§10-A). 8영역 **밖**이라 승인 불요.
_CLOCK_REL = "src/engine/tick_channel_clock.py"
_SWITCH_REL = "src/engine/tick_channel_switch.py"

#: 자매 파일 — cycle293 `test_a18` 은 **삭제가 아니라 본문 교체**다(§6-E ⚠️).
_C293_AST_REL = "tests/unit/ast/test_cycle293_ast_channel_resolver.py"

UNIFIED = "H0UNCNT0"
KRX_ONLY = "H0STCNT0"
NXT_ONLY = "H0NXCNT0"


# ===========================================================================
# 헬퍼
# ===========================================================================
def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree(rel: str) -> ast.Module:
    return ast.parse(_src(rel))


def _require(rel: str, why: str) -> str:
    """파일이 없으면 **FAIL**(SKIP 금지 — Red 는 붉어야 한다)."""
    path = _ROOT / rel
    if not path.exists():
        pytest.fail(f"{rel} 미존재 — {why}")
    return path.read_text(encoding="utf-8")


def _function(rel: str, name: str):
    for node in ast.walk(_tree(rel)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _function_in(src: str, name: str):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _code_only(fn) -> str:
    """docstring 을 제외한 함수 **코드**만 unparse (주석·설명이 판정에 섞이지 않게)."""
    clone = copy.deepcopy(fn)
    if (
        clone.body
        and isinstance(clone.body[0], ast.Expr)
        and isinstance(clone.body[0].value, ast.Constant)
        and isinstance(clone.body[0].value.value, str)
    ):
        clone.body = clone.body[1:] or [ast.Pass()]
    return ast.unparse(clone)


def _segment_sha(rel: str, name: str) -> str:
    """소스 **세그먼트** sha — `ast.dump` 가 아니다(3.12 vs 3.13 표현 차, 메모리 교훈)."""
    text = _src(rel)
    fn = _function_in(text, name)
    assert fn is not None, f"{rel} 에 `{name}` 미존재"
    seg = ast.get_source_segment(text, fn)
    assert seg is not None
    return _sha(seg)


def _production_py_files() -> list[pathlib.Path]:
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _doc_node_ids(tree: ast.AST) -> set[int]:
    """docstring 상수 노드의 id 집합 — **설명문은 판정에서 제외**한다.

    명세 §1-D 의 참조 구현 자체가 docstring 에 「통합 채널(`TICK_TR_ID`)을 절대
    반환하지 않는다」 라고 쓴다. 설명을 금지하면 가드가 **문서를 지우는 방향**으로
    구현을 몰아간다 — 잠글 것은 **코드**다.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (
                body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _names_used(src: str) -> set[str]:
    """모듈이 **코드로** 쓰는 식별자 전부 (Name·Attribute·import 이름)."""
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.update(a.name.split("."))
                if a.asname:
                    out.add(a.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.update(node.module.split("."))
            for a in node.names:
                out.add(a.name)
                if a.asname:
                    out.add(a.asname)
    return out


def _str_constants(src: str) -> list[str]:
    """docstring 을 뺀 문자열 상수 전부."""
    tree = ast.parse(src)
    skip = _doc_node_ids(tree)
    return [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def _num_constants(src: str) -> list:
    tree = ast.parse(src)
    return [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
        and not isinstance(n.value, bool)
    ]


# ===========================================================================
# A1 (G-294-13) — 금지 파일 sha (착수 시점 = cycle292+293 워크트리, 2026-09-14)
# ===========================================================================
#: 접촉 **허용** = 8영역 4파일(`scanner.py`·`risk.py`·`websocket.py`·
#: `websocket_pool.py`) + 8영역 밖 보조(`stale_watcher_core`·`tick_channel_mode`·
#: `db/system_config`·`routes/realtime`) + 신규 leaf 2파일.
#: 승인받은 5파일 중 `order_engine.py` 는 **쓰지 않는다**(§10-A) — 아래 별도 핀.
_BASE_SHA: dict[str, str] = {
    # 8영역 — 미승인
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "bfbdcfbe2bd595055bcc38f5e094e2815ef67854f2153aa20c40629c9e4e6764",
    # 🔴 `handler.py` = N-4. tr_id 를 `_handle_tick` 에 넘기는 근본 시정은
    #    미승인 8영역이라 이 사이클 밖이다(이중 채널 **금지**로만 닫는다).
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    # 🔴 `scheduler.py` 무접촉 (절대 규칙 7). `:1382`/`:2728` 두 줄은 §7-B
    #    레거시 재라우팅이 흡수한다. 근본 시정(2줄 치환)은 결정 카드 D-4.
    "src/engine/scheduler.py":
        "9bf05ccae11bd0c12d5275f36be70863decd83f1f34d77352f505bc15e549d8a",
    "src/engine/market_op_subscribe.py":
        "7d58f9464c1ed35e4fa8706d801beb5a6b5c062d5a2941f0db6482d028d3d4ac",
    # 전략 7파일 + 베이스 — 매매 행위 변경 0 의 구조적 증거
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
        "bbebddd45780a9e19f8bb3c69557d4db50fffc61e8e9da20564476a1be9598a0",
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
    # 파라미터 축 — 리졸버 5키는 `system_config` 다(§9-E). 전략 축으로 새지 않는다.
    "src/engine/param_catalog.py":
        "81a7685b32f689b101db88f26d22d2f102859e29be770a201b26b52cfe8a350a",
    "src/engine/param_validation.py":
        "b4c5c029800191523bcc511919d6de3774e9ab49ca2fc0a0558ee3907868ee17",
    # 🔴 시각·거래소 표의 유일 정본 — 3단계는 이 표를 **읽기만** 한다(§1-A).
    #    `_is_effective` 는 private 이고 `get_market_table(on_date)` 이 공개 API 다.
    "src/engine/market_state.py":
        "7cef2efeb55a7184391ac2cc447c90102fdd7ba507fd6e3834d24a8ad9ce006b",
    # last-write-wins 거래량 기록기 — 이중 채널이면 비결정론이 된다(N-4).
    "src/engine/tick_volume.py":
        "457bd43d80e3cb46c64ae33cb6c1c5d0c12df54246c383bb3d81292d013ef267",
}

#: 승인은 받았지만 **쓰지 않는다**(§10-A) — 해제가 이미 `subscribed_tick_tr_id`
#: (구독 사실)를 거치므로 3단계에 할 일이 없다. 붉어지면 "왜 필요해졌는가" 를
#: 먼저 적고 나서 핀을 옮겨라.
_PIN_APPROVED_BUT_UNUSED: dict[str, str] = {
    "src/engine/order_engine.py":
        "f13519d6429c5b79698fe2607f5eb76262f803a16fb8d58addd1558cfcf264c7",
}

#: cycle293 착지 값(= cycle294 **착수 시점**) — 기록용이다. 이 두 파일은 이 사이클의
#: 접촉 대상이라 byte 동일 핀을 걸 수 없고, "되돌리지 않았다" 는 `test_a2b` 의 내용
#: 핀과 `test_a2c` 의 `_classify_channel` 세그먼트 sha 가 지킨다.
#: ⚠️ 이 값을 현재 워크트리 sha 로 덮지 마라 — 그러면 "어디서 출발했는가" 가 사라져
#: 다음 사람이 cycle293 배관이 살아 있는지 되짚을 좌표를 잃는다.
_CYCLE293_LANDING_SHA: dict[str, str] = {
    "src/engine/risk.py":
        "8737effb71f505fbcb05f5ca284ae7ee8ca1b2f1c1d8e4b6255b09ac3907e916",
    "src/engine/scanner.py":
        "1ebfb0d8b0cd355cf360dfe7d017302b6a327b7a846070c57bb628a48f94a556",
}

#: §1-E — cycle293 의 속성축 판정은 **byte 동일**로 남긴다(출처 검사·극성·
#: fail-open 근거를 재작성하지 않는다). 소스 **세그먼트** sha.
_CLASSIFY_CHANNEL_SEGMENT_SHA = (
    "9e36c8a54ce695c73f104dcd3342477fe9d9b3593f63c1916a3acdc08538be99"
)

_SCHEDULER_LINES = 3726
_SCHEDULER_LINE_CAP = 3900


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_a1_forbidden_files_are_byte_identical(rel: str) -> None:
    """A1 (G-294-13) — 금지 파일이 착수 시점과 byte 동일하다.

    붉어지면 핀을 옮기지 말고 **변경을 되돌려라.**
    """
    got = _sha(_src(rel))
    assert got == _BASE_SHA[rel], (
        f"{rel} 가 바뀌었다 — cycle294 접촉 허용 밖이다(§10-A). 현재 sha={got}"
    )


@pytest.mark.parametrize("rel", sorted(_PIN_APPROVED_BUT_UNUSED))
def test_a1b_approved_but_unused_file_stays_untouched(rel: str) -> None:
    """A1b (§10-A) — `order_engine.py` 는 승인 5파일 중 **유일하게 diff 0** 이다.

    해제 경로가 이미 `scanner.subscribed_tick_tr_id`(구독 **사실**)를 읽으므로
    (`order_engine.py:1952` 부근) 채널이 시각축으로 갈려도 해제는 스스로
    맞는다. 승인은 "필요하면 써도 된다" 이지 "쓴다" 가 아니다.
    """
    got = _sha(_src(rel))
    assert got == _PIN_APPROVED_BUT_UNUSED[rel], (
        f"{rel} 가 바뀌었다 — §10-A 는 diff 0 을 선언했다. 현재 sha={got}"
    )


def test_a2_scheduler_untouched_line_count() -> None:
    """A2 (G-294-12 · 절대 규칙 7) — `scheduler.py` 라인 수 정확 일치.

    cycle292 가 3,897→3,726 으로 만든 여유 171줄은 이 사이클의 예산이 아니다.
    `:1382`/`:2728` 의 통합 구독 2곳은 `websocket.py` 재라우팅이 흡수한다.
    """
    lines = len(_src("src/engine/scheduler.py").splitlines())
    assert lines == _SCHEDULER_LINES, (
        f"scheduler.py = {lines}L (착수 시점 {_SCHEDULER_LINES}L) — 무접촉 계약 위반"
    )
    assert lines < _SCHEDULER_LINE_CAP


def test_a2b_prior_cycles_are_not_reverted() -> None:
    """A2b — cycle292/293 의 미커밋 변경을 **되돌리지 않았다.**

    이 사이클은 그 둘 **위에** 쌓는다. 아래 넷 중 하나라도 사라지면 3단계가
    2단계의 배관 위가 아니라 그 자리에 덮어쓰는 것이다.
    """
    scanner = _src(_SCANNER_REL)
    assert "TICK_TR_IDS" in scanner, "cycle293 의 3채널 단일 정본 집합이 사라졌다"
    assert "no_feed_registry.is_provenance_ok" in scanner or "is_provenance_ok" in scanner, (
        "cycle293 §6-C 출처(provenance) 검사가 사라졌다 — W2 도장 창(07:45~08:08)에 "
        "`TIME_PRESUBSCRIBE`(07:59)가 들어 있다"
    )
    _require(_MODE_REL, "cycle293 킬스위치 leaf 가 사라졌다 — 장중에 끌 수단이 없어진다")
    _require(
        "src/engine/market_op_subscribe.py",
        "cycle292 장운영 구독 leaf 가 사라졌다 — `scheduler.py` 171줄 축소의 근거다",
    )


def test_a2c_classify_channel_is_byte_identical() -> None:
    """A2c (§1-E) — cycle293 `_classify_channel` 은 **byte 동일**로 재사용한다.

    3단계는 그 위에 시각축을 **합성**한다(`_resolve_channel`). 속성축 본문을
    다시 쓰면 출처 검사·극성·fail-open 근거가 cycle293 의 실측(2,674/2,674
    도장 일치 · 420종목 오배치)에서 분리된다.
    """
    got = _segment_sha(_SCANNER_REL, "_classify_channel")
    assert got == _CLASSIFY_CHANNEL_SEGMENT_SHA, (
        "`scanner._classify_channel` 본문이 바뀌었다 — 3단계는 이 함수를 **호출**해 "
        f"합성한다(§1-E). 새 판정이 필요하면 `_resolve_channel` 쪽에 둬라. 현재 {got}"
    )


# ===========================================================================
# A3~A7 (G-294-1 · G-294-2) — 시각축 leaf
# ===========================================================================
_CLOCK_MISSING = (
    "§1-D 시각축 판정 leaf 다. `clock_channel(now, *, offset_secs) -> (tr_id, reason)` "
    "를 순수·never-raise 로 넣어라. `market_state.get_market_table(on_date)` **공개 "
    "API** 만 읽고 시각 리터럴은 0건이어야 한다"
)
_SWITCH_MISSING = (
    "§4·§5 전환 실행 + 자동 원복 leaf 다. `run_switch_cycle(scheduler, pool, *, now)` "
    "를 never-raise async 로 넣고 `stale_watcher_core`(120초)에서 부른다"
)


def test_a3_clock_leaf_exists_and_is_sync_pure() -> None:
    """A3 (§1-D) — 시각축 leaf 는 **동기 순수** 함수다.

    `risk.on_tick`·`subscribe_filtered_stocks` 같은 hot path 가 이 판정을
    읽는다. async 로 만들면 호출자 전부가 await 경로로 바뀌고, 그 경로에
    `scanner` 의 A-PURE 계약(관문 안 await 금지)과 같은 계열의 구멍이 난다.
    """
    src = _require(_CLOCK_REL, _CLOCK_MISSING)
    fn = _function_in(src, "clock_channel")
    assert fn is not None, (
        f"{_CLOCK_REL} 에 `clock_channel` 미존재 — §1-D 의 이름 계약이다"
    )
    assert isinstance(fn, ast.FunctionDef), "`clock_channel` 이 async 다 — 동기여야 한다"
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Await)], (
        f"{_CLOCK_REL} 에 `await` 가 있다 — 시각축 판정은 순수여야 한다(G-294-14)"
    )
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)], (
        f"{_CLOCK_REL} 에 async 함수가 있다"
    )


_IO_TOKENS = ("pg.fetch", "pg.execute", "httpx", "aiohttp", "requests.", "kis_request")


def test_a4_clock_leaf_has_no_io() -> None:
    """A4 (G-294-14) — 시각축 leaf 에 DB·HTTP 0."""
    src = _require(_CLOCK_REL, _CLOCK_MISSING)
    for token in _IO_TOKENS:
        assert token not in src, (
            f"{_CLOCK_REL} 에 `{token}` — 시각축 판정에 I/O 를 넣으면 hot path 가 막힌다"
        )


_TIME_CALL_RE = re.compile(r"\btime\s*\(\s*\d+\s*,")
_CLOCK_STR_RE = re.compile(r"[\"'](?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?[\"']")
_COMBINE_RE = re.compile(r"datetime\.combine\s*\([^)]*\btime\s*\(\s*\d")


@pytest.mark.parametrize("rel", [_CLOCK_REL, _SWITCH_REL, _MODE_REL])
def test_a5_no_clock_literals_in_the_new_leaves(rel: str) -> None:
    """🔴 A5 (G-294-1 · 절대 규칙 「시각 리터럴 0건」) — 판정은 표에서만 나온다.

    경계 셋(`nxt_pre_end` 08:50 · `krx_regular_open` 09:00 · `krx_continuous_end`
    20:00)은 전부 `get_market_table(on_date)` 파생이고, 전환 시각은 **파라미터**
    (`nxt_pre_end + offset`)다. 리터럴을 넣으면 표가 또 움직이는 날(09-14 가
    두 번째다) 조용히 틀린다 — cycle285 가 `TIME_*` 상수 인용으로 같은 계약을
    세웠고 cycle287 은 `order_engine.py` 안 시각 리터럴 0건을 달성했다.

    주석의 `08:55` 류도 **상수명 인용**(`nxt_pre_end + offset`)으로 쓴다.
    """
    why = _CLOCK_MISSING if rel == _CLOCK_REL else _SWITCH_MISSING
    src = _require(rel, why) if rel != _MODE_REL else _src(rel)
    assert not _TIME_CALL_RE.search(src), (
        f"{rel} 에 `time(H, M)` 시각 리터럴이 있다 — 경계는 "
        "`market_state.get_market_table(on_date)` 에서만 파생하라(§1-B)"
    )
    assert not _CLOCK_STR_RE.search(src), (
        f"{rel} 에 `\"HH:MM\"` 시각 문자열이 있다 — 주석·로그 문구에도 두지 않는다"
        "(상수명으로 인용하라, cycle285 선례)"
    )
    assert not _COMBINE_RE.search(src), (
        f"{rel} 에 `datetime.combine(..., time(H, M))` 이 있다"
    )


def test_a6_clock_reads_the_public_table_api_only() -> None:
    """A6 (§1-A) — `get_market_table(on_date)` **공개 API** 만 읽는다.

    `MARKET_TABLE` 을 직접 순회하면 `effective_from`/`effective_to` 를 스스로
    해석해야 하는데 `_is_effective` 는 **private** 이다. K6(애프터마켓)은
    `effective_from=2026-09-14`, K7(시간외 단일가)은 `effective_to=2026-09-12`
    라 날짜 해석을 빠뜨리면 09-13 이전 날짜에서 20:00 이 나오고 그건 거짓이다.
    """
    src = _require(_CLOCK_REL, _CLOCK_MISSING)
    names = _names_used(src)
    assert "get_market_table" in names, (
        f"{_CLOCK_REL} 가 `get_market_table` 을 읽지 않는다 — 경계를 어디서 가져오나"
    )
    assert "MARKET_TABLE" not in names, (
        f"{_CLOCK_REL} 가 `MARKET_TABLE` 을 **직접** 순회한다 — 날짜 해석이 "
        "`_is_effective`(private) 에 있다. 공개 API 를 써라(§1-A)"
    )
    assert "_is_effective" not in names, (
        f"{_CLOCK_REL} 가 private `_is_effective` 를 부른다 — 캡슐 위반"
    )


def test_a6b_continuous_end_is_selected_by_match_kind() -> None:
    """A6b (§1-B ⚠️) — `krx_continuous_end` 는 `match_kind=="continuous"` 로 고른다.

    `phase` 로 고르면 `REGULAR`(15:20)와 `AFTER_MARKET`(20:00)을 **둘 다 열거**
    해야 하고, KRX 가 연속 구간을 하나 더 신설하면 그 열거가 조용히 낡는다.
    `match_kind` 는 "실시간 접속매매인가" 라는 성질이라 신설 구간을 자동으로
    흡수한다. 그리고 K7(`periodic_auction`)이 이 질의에 걸리지 않는 것이
    `effective_to` 해석과 **이중으로** 18:00 오염을 막는다.
    """
    src = _require(_CLOCK_REL, _CLOCK_MISSING)
    names = _names_used(src)
    strings = _str_constants(src)
    assert "match_kind" in names, (
        f"{_CLOCK_REL} 가 `match_kind` 를 읽지 않는다(§1-B)"
    )
    assert "continuous" in strings, (
        f"{_CLOCK_REL} 에 `match_kind == \"continuous\"` 질의가 없다 — "
        "`krx_continuous_end` 를 무엇으로 고르나(§1-B)"
    )
    assert "AFTER_MARKET" not in names, (
        f"{_CLOCK_REL} 가 `MarketPhase.AFTER_MARKET` 을 열거한다 — 그 열거는 KRX 가 "
        "연속 구간을 신설하는 날 낡는다. `match_kind` 로 골라라(§1-B ⚠️)"
    )
    assert "PRE_MARKET" in names, (
        f"{_CLOCK_REL} 가 `MarketPhase.PRE_MARKET`(= N1 프리장 종료)을 질의하지 "
        "않는다 — `nxt_pre_end` 는 어디서 나오나(§1-B)"
    )
    assert "REGULAR" in names, (
        f"{_CLOCK_REL} 가 `MarketPhase.REGULAR`(= K3 정규장 개장)를 질의하지 "
        "않는다 — `krx_regular_open` 은 어디서 나오나(§1-B)"
    )


_BARE_UNIFIED_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])TICK_TR_ID(?![A-Za-z0-9_])")


@pytest.mark.parametrize("rel", [_CLOCK_REL, _SWITCH_REL])
def test_a7_new_leaves_never_name_the_unified_channel(rel: str) -> None:
    """🔴 A7 (G-294-2 · 절대 규칙 1) — 신규 leaf 는 **통합 채널을 이름조차 쓰지 않는다.**

    정상 경로에서 `H0UNCNT0` 를 반환하지 않는 것이 이 사이클의 목표다. 통합을
    반환할 수 있는 유일한 자리는 킬스위치 `off`(§3-B L3)이고 그것은
    `scanner.tick_tr_id_for` 안에 있다 — 시각축·전환 leaf 에는 그 값을 다룰
    이유가 없다.

    ⚠️ 상수 `TICK_TR_ID` **자체는 삭제하지 않는다**(`test_cycle257_ast_dead_code_
    removed.py::_PRESERVED_TICK_CONSTS` 가 리터럴로 핀한다). 사라지는 것은
    **반환 경로**뿐이다(A26 이 그 보존을 지킨다).
    """
    why = _CLOCK_MISSING if rel == _CLOCK_REL else _SWITCH_MISSING
    src = _require(rel, why)
    assert UNIFIED not in _str_constants(src), (
        f"{rel} 에 통합 채널 리터럴 `{UNIFIED}` 가 **코드로** 있다 — 3단계의 목표는 "
        "그 채널의 **소멸**이다(절대 규칙 1). docstring 설명은 판정에서 제외된다"
    )
    assert "TICK_TR_ID" not in _names_used(src), (
        f"{rel} 가 `TICK_TR_ID`(통합 상수)를 참조한다 — 전용 2채널만 다뤄야 한다. "
        "`TICK_TR_ID_KRX` / `TICK_TR_ID_NXT` 는 **다른 이름**이라 통과한다"
    )


# ===========================================================================
# A8~A10 (§1-E) — scanner 합성
# ===========================================================================
def test_a8_resolve_channel_composes_clock_and_attribute_axes() -> None:
    """A8 (§1-E) — `scanner._resolve_channel(ticker, now, *, offset_secs)` 합성.

    시각축이 KRX 창을 돌려주면 속성축을 **보지 않는다**(KRX 창에는 L2 층이 존재
    하지 않는다). 프리 창에서만 `_classify_channel` 로 `nxt_false` 를 KRX 로
    내린다 — 그 종목은 08:00~08:50 에 **시장이 없어** 어느 채널이든 프레임이
    0 이고(§2-A), KRX 에 두면 09:00:00 첫 체결을 **전환 없이** 받는다(§2-C).
    """
    fn = _function(_SCANNER_REL, "_resolve_channel")
    assert fn is not None, (
        "§1-E — `scanner._resolve_channel` 미존재. `_classify_channel`(속성축)을 "
        "`tick_channel_clock.clock_channel`(시각축)과 합성하는 자리다"
    )
    body = _code_only(fn)
    assert "clock_channel" in body, (
        "`_resolve_channel` 이 시각축을 부르지 않는다 — 속성축만으로는 프리장/"
        "정규장을 가를 수 없다"
    )
    assert "_classify_channel" in body, (
        "`_resolve_channel` 이 속성축을 부르지 않는다 — 프리 창의 `nxt_false` 가 "
        "NXT 로 가서 전환 폭이 40% 늘어난다(§2-C)"
    )
    assert not _BARE_UNIFIED_NAME_RE.search(body), (
        "🔴 `_resolve_channel` 이 통합 채널을 반환 후보로 다룬다 — `_classify_channel` "
        "의 통합 반환은 여기서 **전부 NXT 로 흡수**돼야 한다(§1-E 🔴 절). 그것이 "
        "절대 규칙 1(통합 반환 0)의 구조적 보증이다"
    )
    assert not _TIME_CALL_RE.search(body), (
        "`_resolve_channel` 에 시각 리터럴이 있다 — 판정은 `market_state` 경유다"
    )


@pytest.mark.parametrize(
    "name", ["tick_tr_id_for", "desired_tick_tr_id", "subscribed_tick_tr_id"],
)
def test_a9_resolver_entry_points_take_an_injectable_now(name: str) -> None:
    """A9 (§1-E 소비 지점 4곳) — `now=None` 키워드가 있고 **기본 인자에 `now()` 가 없다.**

    기본 인자는 모듈 로드 시각에 **한 번** 평가된다. `def f(now=datetime.now())`
    로 쓰면 07:45 부팅 프로세스가 20:00까지 07:45 를 본다 = 전 종목이 프리 창에
    영구 고착된다. 그래서 `None` 센티넬 + 함수 안 `datetime.now(KST_TZ)` 다.
    """
    fn = _function(_SCANNER_REL, name)
    assert fn is not None, f"`scanner.{name}` 미존재"
    kwonly = {a.arg: d for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults)}
    plain = {a.arg for a in fn.args.args}
    assert "now" in kwonly or "now" in plain, (
        f"`scanner.{name}` 에 `now` 주입구가 없다 — 시각축 판정을 테스트에서 고정할 "
        "수 없고 호출자마다 다른 시계를 볼 수 있다(§1-E)"
    )
    default = kwonly.get("now")
    if default is not None:
        assert isinstance(default, ast.Constant) and default.value is None, (
            f"`scanner.{name}` 의 `now` 기본값이 상수 `None` 이 아니다 — 기본 인자는 "
            "모듈 로드 시각에 **한 번** 평가된다(§1-E ⚠️)"
        )


def test_a10_resolver_still_returns_unified_only_for_the_kill_switch() -> None:
    """A10 (§3-B L3) — 통합 반환은 `tick_tr_id_for` 의 **킬스위치 분기 하나**뿐이다.

    `off` 의 정의가 "오늘 배포 전과 동일" 이므로(절대 규칙 8) 그 한 경로는
    남아야 한다. 대신 그 밖의 어떤 분기도 통합으로 떨어지면 안 된다 — 행위
    전수 확인은 자매 파일의 `test_b1`(24h × 1분 격자)이 한다.
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    assert fn is not None
    body = _code_only(fn)
    assert "MODE_OFF" in body, (
        "`tick_tr_id_for` 에 킬스위치 `off` 분기가 없다 — 롤백 수단이 코드 revert "
        "밖에 없어지고 그 재배포는 D6/D8 이 막는다"
    )
    assert "_resolve_channel" in body, (
        "`tick_tr_id_for` 가 3단계 합성(`_resolve_channel`)을 거치지 않는다 — "
        "속성축 단독이면 프리장에서 `nxt_true` 가 KRX 로 가 프레임 0 이 된다"
    )
    # 🔴 통합 반환은 **모드 분기 안**에서만 허용된다.
    #
    # 개수로 세지 않는다 — §9-A 의 모드 표는 `off`(롤백) · `observe`(다크런치) ·
    # `enforce_low`×HIGH 셋이 전부 통합을 돌려주도록 정의한다. 잠글 것은 개수가
    # 아니라 **「판정 실패가 통합으로 떨어지는 경로」의 부재**다 — cycle293 의
    # fail-open(`not decided → TICK_TR_ID`)이 그 형태였고, 3단계에서 그 자리는
    # `_resolve_channel` 의 프리 창 NXT 로 바뀐다(§3-B L2).
    tree = ast.parse(body)
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Return) and node.value is not None):
            continue
        if not _BARE_UNIFIED_NAME_RE.search(ast.unparse(node.value)):
            continue
        cur, gated = parents.get(id(node)), False
        while cur is not None:
            if isinstance(cur, ast.If) and (
                "MODE_" in ast.unparse(cur.test) or "mode" in ast.unparse(cur.test)
            ):
                gated = True
                break
            cur = parents.get(id(cur))
        if not gated:
            offenders.append(ast.unparse(node))
    assert not offenders, (
        f"🔴 `tick_tr_id_for` 에 **모드와 무관한** 통합 반환이 있다: {offenders}. "
        "판정 실패의 폴백은 통합이 아니라 시각 기반 기본값이다(프리 창 NXT / 그 외 "
        "KRX — §3-B). 통합 반환은 `off`/`observe`/`enforce_low`×HIGH 분기 안에서만 "
        "허용된다(§9-A)"
    )


# ===========================================================================
# A11~A15 (🔴 G-294-6) — 매수 축 코호트
# ===========================================================================
def test_a11_buy_gate_reads_the_cohort_not_the_channel() -> None:
    """🔴 A11 (§6-C · 절대 규칙 5) — 게이트 술어 = **코호트**, 채널이 아니다.

    cycle293 의 술어는 「이 종목이 **전용 채널**에 구독돼 있는가」
    (`applied in DEDICATED_TICK_TR_IDS`)였다. 3단계는 **모든** 종목을 전용
    채널로 보내므로 그 술어는 **전 종목 참**이 되고 momentum·volatility_breakout·
    long_tail_volatility·bull_flag_breakout·vcp_breakout **5전략의 틱 매수가
    통째로 죽는다**(그 5전략은 틱이 유일 매수 경로다 — donchian/kojiro 는
    `_TICK_BUY_EVAL_SKIP_STRATEGIES` 로 이미 skip 이고 REST 폴이 담당한다).

    술어의 원래 의도는 「**통합 채널에서 프레임이 0건이던 코호트**(`nxt_false`
    ∧ 출처 권위)인가」였다(§6-B). `nxt_true` 는 어제도 프레임을 받았고 매수
    평가를 이미 받고 있었다 — 3단계는 그들에게 **채널만 바꾼다.**

    🔴 그리고 **모드를 읽지 않는다.** 킬스위치 `off` 는 이미 전용 채널에 올라간
    구독을 되돌리지 않으므로(§9-B), 모드를 보면 「사고 중에 누르는 안전 조치가
    5전략의 매수를 그 코호트에 열어 준다」 = cycle293 적대 검증 CRITICAL 의
    재현이다. 스탬프는 모드와 무관하게 구독 사실을 따른다.
    """
    fn = _function(_RISK_REL, "_tick_buy_eval_blocked_by_channel")
    assert fn is not None, (
        "`risk._tick_buy_eval_blocked_by_channel` 미존재 — cycle293 게이트를 "
        "**삭제하지 말고 본문을 교체**하라(§6-C)"
    )
    body = _code_only(fn)
    assert "tick_buy_cohort_blocked" in body, (
        "게이트가 `scanner.tick_buy_cohort_blocked(ticker)` 를 읽지 않는다 — "
        "술어를 채널에서 **코호트**로 바꾸는 것이 §6 의 전부다"
    )
    assert "DEDICATED_TICK_TR_IDS" not in body, (
        "🔴 게이트가 아직 `DEDICATED_TICK_TR_IDS` 멤버십(= 전용 채널인가)을 읽는다. "
        "3단계는 전 종목을 전용 채널로 보내므로 이 술어는 **전 종목 참**이 되어 "
        "내일 아침 5전략 매수가 0 이 된다(절대 규칙 5 의 최대 위험)"
    )
    assert "tick_tr_id_for(" not in body, (
        "게이트가 적용형 리졸버를 부른다 — 틱마다 전환 예산(`_channel_flipped_today`)"
        "을 관측이 먹는다(cycle293 적대 검증 MEDIUM-3)"
    )
    assert "current_mode" not in body, (
        "🔴 게이트가 킬스위치 모드를 읽는다 — `off` 가 매수를 **여는** 경로가 "
        "되살아난다(§6-C 🔴 절 · 금기 9)"
    )
    assert "_ticker_to_tr_id" not in body, (
        "게이트가 아직 풀의 병행 dict(= 실제 구독 채널)를 읽는다 — 3단계에서 그 "
        "값은 전 종목 전용 채널이라 술어가 항상 참이 된다"
    )


def test_a12_cohort_stamp_and_reader_exist_and_are_pure() -> None:
    """A12 (§6-C) — 구독 시점 스탬프 + 읽기 전용 판독기.

    매 틱 레지스트리를 재조회하지 않는다(판정과 구독 사실이 갈리면 게이트만
    풀린다). **구독을 발사하는 시점에 코호트를 심고, 게이트는 그 스탬프만 읽는다.**
    """
    scanner_src = _src(_SCANNER_REL)
    assert "_channel_cohort" in scanner_src, (
        "§6-C — `scanner._channel_cohort: dict[str, bool]` 미존재(구독 시점 코호트 스탬프)"
    )
    stamp = _function(_SCANNER_REL, "_stamp_cohort")
    assert stamp is not None, "§6-C — `scanner._stamp_cohort(ticker)` 미존재"
    reader = _function(_SCANNER_REL, "tick_buy_cohort_blocked")
    assert reader is not None, (
        "§6-C — `scanner.tick_buy_cohort_blocked(ticker)` 미존재. `risk` 게이트가 "
        "읽을 유일한 공개 술어다"
    )
    for fn, label in ((stamp, "_stamp_cohort"), (reader, "tick_buy_cohort_blocked")):
        assert isinstance(fn, ast.FunctionDef), f"`{label}` 이 async 다 — 틱 경로다"
        assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
            f"`{label}` 에 await 가 있다 — `risk.on_tick` 이 틱마다 부른다(G-294-14)"
        )
    rbody = _code_only(reader)
    assert "_channel_cohort" in rbody, "판독기가 스탬프 dict 를 읽지 않는다"
    assert "_channel_cohort[" not in rbody, (
        "🔴 판독기가 스탬프를 **쓴다** — 읽기 전용이어야 한다(§6-C: 날짜 경계 "
        "자기 정리 `_sync_channel_day` 만이 예외다)"
    )


def test_a13_stamp_is_fired_at_the_subscription_entry_point() -> None:
    """A13 (§6-C) — 스탬프는 `tick_tr_id_for` 안, `_apply_channel_decision` **직전**.

    거기가 구독을 실제로 발사하는 **유일한 적용형 진입점**이라 스탬프가 구독과
    1:1 이 된다. 판정 전용 경로(`desired_tick_tr_id`)에 심으면 해제·집계·진단이
    코호트를 만들어 버린다.
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    assert fn is not None
    body = _code_only(fn)
    assert "_stamp_cohort(" in body, (
        "§6-C — `tick_tr_id_for` 가 `_stamp_cohort(ticker)` 를 부르지 않는다. "
        "스탬프가 없으면 게이트가 **전 종목 열림**으로 fail-open 하고, 그건 "
        "`nxt_false` 코호트(유니버스 64%)를 5전략 매수에 여는 미승인 행위 변경이다"
    )
    lines = body.splitlines()
    stamp_at = next((i for i, ln in enumerate(lines) if "_stamp_cohort(" in ln), None)
    apply_at = next(
        (i for i, ln in enumerate(lines) if "_apply_channel_decision(" in ln), None,
    )
    assert stamp_at is not None and apply_at is not None
    assert stamp_at < apply_at, (
        "`_stamp_cohort` 가 `_apply_channel_decision` 뒤에 있다 — 적용이 예외로 "
        "빠지면 스탬프가 없는 채로 구독이 나간다"
    )
    pure = _function(_SCANNER_REL, "desired_tick_tr_id")
    assert pure is not None
    assert "_stamp_cohort(" not in _code_only(pure), (
        "순수 판정 경로(`desired_tick_tr_id`)가 스탬프를 심는다 — 해제·집계·진단이 "
        "코호트를 만든다(cycle293 이 전환 예산에서 같은 함정을 밟았다)"
    )


def test_a14_cohort_is_cleared_at_the_kst_day_boundary() -> None:
    """A14 (§6-C) — 코호트 스탬프는 **하루 수명**이다.

    `_channel_cohort` 는 「닫힘 우세」 단방향 래치다(§6-C). 날짜 경계에서 비우지
    않으면 cycle293 §6-D 가 금지한 **영구 좌초 래치**가 되어, NXT 에 재편입한
    종목(064550 계열 — 09-02 `False` → 09-14 `True` 실측)의 매수가 영원히 막힌다.
    """
    fn = _function(_SCANNER_REL, "_sync_channel_day")
    assert fn is not None
    body = _code_only(fn)
    assert "_channel_cohort" in body, (
        "§6-C — `_sync_channel_day` 가 `_channel_cohort` 를 비우지 않는다. 하루 "
        "단방향 래치가 날짜를 넘기면 **영구 좌초**가 된다(cycle293 §6-D 금지 사항)"
    )
    reset = _function(_SCANNER_REL, "reset_tick_channel_state_for_test")
    assert reset is not None
    assert "_channel_cohort" in _code_only(reset), (
        "테스트 seam 이 코호트를 비우지 않는다 — 파일 내 실행 순서에 따라 앞 "
        "테스트의 스탬프가 다음 테스트의 매수 축 판정을 바꾼다(cycle293 적대 검증)"
    )


def test_a15_cycle293_a18_is_superseded_not_deleted() -> None:
    """A15 (§6-E ⚠️) — cycle293 `test_a18` 은 **삭제가 아니라 본문 교체**다.

    지우면 다음 사람이 "구독 사실을 읽어라" 를 되살려 5전략 매수를 다시 죽인다.
    구 단언이 왜 틀리게 됐는지가 그 docstring 에 남아 있어야 한다.
    """
    src = _require(_C293_AST_REL, "cycle293 AST 자매 파일이 사라졌다")
    fn = _function_in(src, "test_a18_buy_gate_reads_the_subscription_fact_not_the_resolver")
    assert fn is not None, (
        "cycle293 `test_a18_*` 가 삭제됐다 — 본문을 교체하고 구 단언이 3단계에서 "
        "왜 틀리게 됐는지를 docstring 에 남겨라(§6-E ⚠️)"
    )
    seg = ast.get_source_segment(src, fn) or ""
    assert "tick_buy_cohort_blocked" in seg, (
        "cycle293 `test_a18_*` 가 아직 채널 축 술어를 단언한다 — 3단계에서 그 단언은 "
        "**틀렸다**(전 종목 전용 채널 ⇒ 전 종목 매수 skip). 코호트 술어로 교체하라"
    )


# ===========================================================================
# A16~A19 (G-294-4/5/7) — 전환
# ===========================================================================
_SWITCH_FN_NAMES = ("switch_channel_same_session", "_switch_high")


def _switch_candidates() -> list[tuple[str, ast.AST]]:
    found: list[tuple[str, ast.AST]] = []
    for rel in (_POOL_REL, _SWITCH_REL):
        path = _ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for name in _SWITCH_FN_NAMES:
            fn = _function_in(src, name)
            if fn is not None:
                found.append((f"{rel}::{name}", fn))
    return found


def test_a16_switch_leaf_exists_and_never_raises() -> None:
    """A16 (§4-B) — 전환 사이클은 never-raise 다.

    전환 실패가 4중 안전망의 한 축(120초 stale watcher)을 끊으면 손절 커버리지가
    통째로 죽는다. cycle252/293 의 `try/except + logger.debug` 관례 그대로다.
    """
    src = _require(_SWITCH_REL, _SWITCH_MISSING)
    fn = _function_in(src, "run_switch_cycle")
    assert fn is not None, (
        f"{_SWITCH_REL} 에 `run_switch_cycle` 미존재 — §4-B 의 이름 계약이다"
    )
    assert isinstance(fn, ast.AsyncFunctionDef), "`run_switch_cycle` 은 async 다"
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, (
        "`run_switch_cycle` 에 예외 흡수가 없다 — 전환 실패가 120초 stale watcher "
        "루프를 끊으면 재구독 안전망이 죽는다(§4-B never-raise)"
    )
    names = _names_used(src)
    # ⚠️ 의미 전환(cycle294 적대 검증 CRITICAL-1·HIGH-3) — 종전 단언은
    #    `switch_at` / `krx_regular_open` **두 이름**이 이 파일에 나타나는지를
    #    봤다. 그때는 전환 창이 아침 1개뿐이라 그 두 경계를 직접 조립하는 것이
    #    창 게이트의 전부였기 때문이다. 지금은 창이 세 개다(아침 + NXT 단독
    #    연속 구간의 두 경계) — 그 목록은 시각축 leaf 의 `switch_windows()` 가
    #    표에서 파생하고, 이 파일은 `active_switch_window()` 로 "지금 어느 창
    #    안인가" 를 묻는다. 그래서 `switch_at` 이라는 **이름**은 더 이상 여기에
    #    없지만 그 값은 여전히 게이트를 정한다.
    #
    #    구 단언을 그대로 두면 창을 표에서 파생시킨 **더 강한** 구현이 붉어지고,
    #    통과시키려면 쓰지도 않는 이름을 억지로 남겨야 한다. 그래서 단언을
    #    ① 창 질의(`active_switch_window`) ② 사이클 안 **경계 재확인**
    #    (`win_end`) 두 가지로 옮긴다 — ②는 종전 구현에 아예 없던 계약이다
    #    (120초 루프가 창 끝 직전에 진입하면 예산이 찰 때까지 창을 넘겨 계속
    #    옮겼다 = 개장 직후 LOW break-before-make 의 실제 blind).
    assert "active_switch_window" in names, (
        f"{_SWITCH_REL} 가 전환 창을 시각축 leaf 에 묻지 않는다 — 창 밖 전환 "
        "금지(§4-A)를 강제할 수 없다"
    )
    assert "krx_regular_open" in names, (
        f"{_SWITCH_REL} 가 정규장 개장 경계를 읽지 않는다 — 자동 원복 측정 시점"
        "(§5-A)이 성립하지 않는다"
    )
    body = ast.dump(fn)
    assert "win_end" in body, (
        f"{_SWITCH_REL}::run_switch_cycle 가 종목 루프 안에서 창 끝을 재확인하지 "
        "않는다 — 창 끝 직전에 진입한 사이클이 예산이 찰 때까지 창을 넘겨 계속 "
        "옮긴다(적대 검증 HIGH-3)"
    )


def test_a17_high_switch_subscribes_before_it_unsubscribes() -> None:
    """🔴 A17 (G-294-5 · 절대 규칙 2) — HIGH 는 **make-before-break** 다.

    보유·익일청산 종목은 신 채널 **ACK 을 확인한 뒤에** 구 채널을 해제한다.
    순서를 뒤집으면 그 사이 구간이 blind 이고, 그 구간에 손절이 걸리면 되돌릴
    수 없다. 자문 §7-⑤ 는 이 순서를 생략하면 **자문이 기각으로 바뀐다**고 했다.

    ACK 술어는 `(new, ticker) ∈ _subscriptions ∧ ∈ _subscriptions_acked` 다 —
    `_subscriptions` 만 보면 SEND 직후 무응답도 성공으로 읽힌다(cycle14-C 가
    `_subscribed=0/_acked=N` 격차로 잡은 그 계열).
    """
    cands = _switch_candidates()
    assert cands, (
        "§4-C — make-before-break 구현이 없다. `websocket_pool.switch_channel_"
        f"same_session()` 또는 `{_SWITCH_REL}::_switch_high` 로 넣어라"
    )
    checked = 0
    for label, fn in cands:
        awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
        subs = [
            n.lineno for n in awaits
            if isinstance(n.value, ast.Call) and "subscribe" in ast.unparse(n.value.func)
            and "unsubscribe" not in ast.unparse(n.value.func)
        ]
        unsubs = [
            n.lineno for n in awaits
            if isinstance(n.value, ast.Call) and "unsubscribe" in ast.unparse(n.value.func)
        ]
        if not (subs and unsubs):
            continue
        checked += 1
        assert min(subs) < min(unsubs), (
            f"🔴 {label} — `unsubscribe` 가 `subscribe` 보다 **앞**이다 = "
            "break-before-make. 보유 종목이 그 사이 blind 가 된다(절대 규칙 2)"
        )
        seg = _code_only(fn)
        assert "_subscriptions_acked" in seg, (
            f"{label} — ACK 술어에 `_subscriptions_acked` 가 없다. `_subscriptions` "
            "만 보면 SEND 직후 무응답을 성공으로 읽고 구 채널을 끊는다"
        )
    assert checked, (
        "make-before-break 함수를 찾았지만 그 안에 subscribe/unsubscribe await 쌍이 "
        "없다 — §4-C 의 S2·S5 가 구현되지 않았다"
    )


def test_a18_switch_never_redraws_the_session() -> None:
    """🔴 A18 (G-294-7 · §4-D) — 전환은 **세션 안 채널 교체**다.

    `pool.unsubscribe` 는 `_ticker_to_session.pop(tr_key)` 로 찾은 **한 세션**만
    본다. 신규 구독을 라운드로빈으로 다른 세션에 떨어뜨리면 `_ticker_to_session`
    이 새 세션으로 덮이고, 구 채널 해제가 새 세션에서 `(old, ticker)` 를 찾다가
    실패해 **구 세션 튜플이 영구 고아**로 41 슬롯을 잠식한다(cycle253 프로브가
    밟아 `_unsubscribe_probe_everywhere()` + `_release_routing_if_orphaned()` 두
    헬퍼를 만든 그 함정).
    """
    cands = _switch_candidates()
    assert cands, "§4-C 구현 부재 — A17 선행 실패"
    for label, fn in cands:
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Subscript) and "_ticker_to_session" in ast.unparse(tgt):
                        pytest.fail(
                            f"🔴 {label}:{node.lineno} — 전환이 `_ticker_to_session` 을 "
                            "재키잉한다. 구 세션의 `(old, ticker)` 가 영구 고아가 된다(§4-D)"
                        )
        seg = _code_only(fn)
        assert "_pick_session" not in seg and "round_robin" not in seg, (
            f"{label} — 전환이 세션을 **재추첨**한다. HIGH 는 정의상 메인 세션 + "
            "`bypass_limit=True` 라 슬롯 부족이 구조적으로 없다(§4-D)"
        )


def test_a19_switch_is_driven_by_the_120s_stale_watcher() -> None:
    """A19 (§4-B) — 전환 트리거는 `stale_watcher_core.check_and_resubscribe_stale`.

    `_scan_loop`(300초)은 `TIME_SCAN_START`(09:30)에 생성되므로 08:00~09:30 에
    **존재하지 않는다** — 08:55 전환 창을 덮는 루프는 사실상 이것 하나다.
    호출 자리는 `no_feed_registry.ensure_fresh(...)` **직후**여야 한다(레지스트리
    가 더워진 뒤라야 §1-E 합성이 성립한다).
    """
    fn = _function(_SWC_REL, "check_and_resubscribe_stale")
    assert fn is not None, "`stale_watcher_core.check_and_resubscribe_stale` 미존재"
    body = _code_only(fn)
    assert "run_switch_cycle" in body, (
        "§4-B — 120초 루프가 `run_switch_cycle` 을 부르지 않는다. `_scan_loop` 은 "
        "09:30 에 생성돼 08:55 창에 존재하지 않으므로 전환이 **영원히 일어나지 않는다**"
    )
    lines = body.splitlines()
    warm = next((i for i, ln in enumerate(lines) if "ensure_fresh" in ln), None)
    switch = next((i for i, ln in enumerate(lines) if "run_switch_cycle" in ln), None)
    assert warm is not None and switch is not None
    assert warm < switch, (
        "전환이 `ensure_fresh` 보다 **앞**에 있다 — 차가운 레지스트리로 목표 채널을 "
        "정하면 프리 창의 `nxt_false` 판정이 전부 미분류로 떨어진다(§4-B)"
    )


# ===========================================================================
# A20 (G-294-11) — 레거시 재라우팅 스코프
# ===========================================================================
def test_a20_legacy_reroute_touches_only_the_unified_channel() -> None:
    """A20 (§7-B) — `scheduler.py` 의 통합 구독 2곳을 `websocket.py` 가 흡수한다.

    `scheduler.py:1382`(익일청산 시가 수신) · `:2728`(스윙 매수 직후)은 무접촉
    제약 때문에 계속 `TICK_TR_ID` 로 **풀을 우회해** 직접 구독한다. 그 둘을
    그대로 두면 "통합 채널 구독 0" 이 성립하지 않는다.

    🔴 재라우팅 조건은 **`tr_id` 가 정확히 통합일 때** 하나뿐이다. 체결통보
    (`H0STCNI0`/`H0STCNI9`)·장운영정보(`H0UNMKO0`)·전용 2채널 요청은 **byte
    동일**로 통과해야 한다 — 그 넷 중 하나라도 재라우팅되면 체결통보가 끊기거나
    (포지션 등록·손절 불가) 이중 채널이 생긴다.

    ⚠️ 이것은 **증상 차단**이다(N-3). 근본 시정 = `scheduler.py` 2줄 치환(결정
    카드 D-4).
    """
    src = _src(_WS_REL)
    fn = _function_in(src, "_reroute_legacy_unified")
    assert fn is not None, (
        "§7-B — `websocket._reroute_legacy_unified(tr_id, tr_key)` 미존재. "
        "`scheduler.py` 무접촉을 지키면서 통합 구독을 0 으로 만드는 유일한 자리다"
    )
    body = _code_only(fn)
    assert "MODE_OFF" in body and "MODE_OBSERVE" in body, (
        "재라우팅이 `off`/`observe` 에서 통과하지 않는다 — 롤백·다크런치가 "
        "**오늘과 byte 동일**이어야 한다(절대 규칙 8 · G-294-11)"
    )
    assert "subscribed_tick_tr_id" in body, (
        "재라우팅이 구독 **사실**(`_ticker_to_tr_id` 1순위)을 읽지 않는다 — 판정으로 "
        "고르면 이미 풀에 있는 종목에 다른 채널을 심어 **이중 채널**을 만든다(§7-B)"
    )
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, (
        "재라우팅에 예외 흡수가 없다 — 재라우팅 실패가 **구독 자체를 막으면** "
        "안 된다(never-raise, §7-B)"
    )
    sub = _function_in(src, "subscribe")
    assert sub is not None, "`KisWebSocket.subscribe` 미존재"
    sub_body = _code_only(sub)
    assert "_reroute_legacy_unified" in sub_body, (
        "§7-B — `KisWebSocket.subscribe` 첫 문장에서 재라우팅을 거치지 않는다. "
        "`scheduler.py` 두 줄은 풀을 **우회**하므로 여기 말고는 잡을 자리가 없다"
    )


# ===========================================================================
# A21~A22 (G-294-15) — 파라미터 축
# ===========================================================================
_NEW_PARAM_KEYS = (
    "tick_channel_switch_enabled",
    "tick_channel_switch_offset_secs",
    "tick_channel_switch_ack_timeout_secs",
    "tick_channel_revert_probe_secs",
)


@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_a21_new_keys_live_on_the_system_config_axis(key: str) -> None:
    """A21 (§9-E) — 신규 4키는 `system_config` 축이다.

    🔴 전략 `DEFAULT_PARAMS`·`param_catalog`·`PARAM_RANGES`·`INT_PARAMS` **편입
    금지** — 리졸버는 인프라 축이고 7전략에 넣으면 7곳이 갈린다. cycle287 이
    킬스위치를 `param_catalog` 미등재로 만들어 `PUT /api/strategies/{id}/params`
    가 `unknown_key` 422 를 돌려준 그 실패의 반대 방향 잘못이다.
    """
    sysconf = _src(_SYSCONF_REL)
    assert key in sysconf, (
        f"§9-E — `{key}` 가 `{_SYSCONF_REL}` 에 없다. 리졸버 파라미터는 "
        "`system_config` 한 축에서만 온다"
    )
    for rel in ("src/engine/param_catalog.py", "src/engine/param_validation.py"):
        assert key not in _src(rel), (
            f"🔴 `{key}` 가 {rel} 에 있다 — 전략 파라미터 축 편입 금지(§9-E · 금기 8)"
        )
    for path in sorted((_SRC / "engine" / "strategies").glob("*.py")):
        assert key not in path.read_text(encoding="utf-8"), (
            f"🔴 `{key}` 가 {path.name} 의 `DEFAULT_PARAMS` 축에 새어 들었다"
        )


def test_a21b_switch_dial_is_separate_from_the_mode_enum() -> None:
    """A21b (§9-D · 결정 카드 D-5) — 「채널이 문제」와 「전환이 문제」는 다른 결정.

    모드 enum 을 늘리지 않고 불리언 키 하나를 더 둔다. 전환만 끄면 종목은 첫
    구독 채널에 머물고(`nxt_true` → NXT 종일 = NXT 정규장·애프터 프레임 수신 =
    **blind 아님**) 위험이 즉시 동결된다. 이것이 §5 자동 원복의 수동 대응물이다.
    """
    mode_src = _src(_MODE_REL)
    valid = _function_in(mode_src, "current_mode")
    assert valid is not None
    assert "MODE_SWITCH" not in mode_src, (
        "전환 다이얼을 모드 enum 에 태웠다 — 운영자가 「전환만」 끌 수 없게 된다(§9-D)"
    )
    assert "tick_channel_switch_enabled" in mode_src, (
        "§9-D — `tick_channel_switch_enabled` 를 읽는 자리가 없다. 사고 중에 쓸 "
        "카드가 `off` 하나뿐이면 146종목 대량 전환을 장중에 실행하게 된다"
    )
    routes = _src(_ROUTES_REL)
    assert "switch_enabled" in routes, (
        "§9-D — `PUT /api/realtime/tick-channel-mode` 바디에 선택 필드 "
        "`switch_enabled` 가 없다(신규 엔드포인트 0 이 계약이다)"
    )


def test_a22_revert_probe_reuses_the_existing_grace_constant() -> None:
    """A22 (§5-A · 금기 13 「새 숫자를 짓지 말 것」) — 180초는 재사용이다.

    `stale_diagnostics.SUBSCRIBE_GRACE_SECS = 180`(구독 ACK grace, 사이클 135
    사용자 결정 Q2)와 의미가 같다 — "구독이 살아났다고 인정하기까지 주는 시간".
    두 번째 정의를 만들면 사이클 135 의 단일 정의처 계약이 깨진다.
    """
    src = _require(_SWITCH_REL, _SWITCH_MISSING)
    assert "SUBSCRIBE_GRACE_SECS" in _names_used(src), (
        f"{_SWITCH_REL} 가 `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 를 재사용하지 "
        "않는다 — 180 을 새로 적으면 두 정의가 갈린다(§5-A 🔴)"
    )
    assert 180 not in _num_constants(src), (
        f"{_SWITCH_REL} 에 숫자 리터럴 `180` 이 있다 — 상수를 import 해서 쓰라(금기 13)"
    )
    assigned = {
        t.id
        for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
    } | {
        n.target.id
        for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
    }
    assert "SUBSCRIBE_GRACE_SECS" not in assigned, (
        f"{_SWITCH_REL} 가 `SUBSCRIBE_GRACE_SECS` 를 **재정의**한다 — 단일 정의처는 "
        f"{_DIAG_REL} 다(사이클 135 G-AST-CONST)"
    )


# ===========================================================================
# A23~A25 (§11-A · G-294-14) — 관측 · 순수성
# ===========================================================================
_NEW_MARKERS = (
    "[tick_channel_clock]",
    "[tick_channel_switch]",
    "[tick_channel_switch_summary]",
    "[tick_channel_switch_failed]",
    "[tick_channel_switch_orphan]",
    "[tick_channel_switch_window_missed]",
    "[tick_channel_auto_revert]",
    "[tick_channel_revert_skipped]",
    "[tick_channel_legacy_reroute]",
    "[tick_buy_gate]",
    "[tick_channel_pre_krx_frame]",
    "[tick_channel_param_invalid]",
)


@pytest.mark.parametrize("marker", _NEW_MARKERS)
def test_a23_new_markers_exist_in_production(marker: str) -> None:
    """A23 (§11-A) — 신규 마커 12종이 프로덕션 소스에 실재한다.

    관측이 없으면 D+1 판독이 불가능하고, 판독이 불가능하면 "되돌릴 수 있다" 가
    말뿐이 된다. 특히 `[tick_channel_auto_revert]` 는 **ERROR** 레벨이어야
    21:30 리포트 `top_patterns` 에 들어간다(cycle245 `[ratio_cap_config]` 함정).
    """
    hits = [p for p in _production_py_files() if marker in p.read_text(encoding="utf-8")]
    assert hits, f"§11-A — 마커 `{marker}` 가 프로덕션 소스에 없다"


def test_a23b_auto_revert_marker_is_error_level() -> None:
    """A23b (§5-B 4) — `[tick_channel_auto_revert]` 는 ERROR 다.

    되돌렸다는 것은 §0 의 설계 가정(`H0STCNT0` 가 종목 속성 무관 수신)이
    **틀렸다**는 뜻이다. `log_metrics_collector.pattern_by_level` 이 WARNING
    이상만 21:30 리포트에 넣으므로 INFO 면 리포트에 한 글자도 안 뜬다.
    """
    src = _require(_SWITCH_REL, _SWITCH_MISSING)
    idx = src.find("[tick_channel_auto_revert]")
    assert idx >= 0, "§5-B — `[tick_channel_auto_revert]` 마커 부재"
    window = src[max(0, idx - 400):idx + 200]
    assert "logger.error" in window or "logger.critical" in window, (
        "`[tick_channel_auto_revert]` 가 ERROR 레벨이 아니다 — 21:30 리포트 "
        "`top_patterns` 는 WARNING 이상만 담는다(§5-B 4)"
    )


@pytest.mark.parametrize("name", ["_stamp_cohort", "tick_buy_cohort_blocked", "_resolve_channel"])
def test_a24_new_scanner_helpers_have_no_io(name: str) -> None:
    """A24 (G-294-14) — scanner 신규 헬퍼에 await/DB/HTTP 0.

    셋 다 `risk.on_tick`(틱 경로) 또는 구독 발사 경로에서 동기로 불린다.
    """
    fn = _function(_SCANNER_REL, name)
    assert fn is not None, f"`scanner.{name}` 미존재"
    assert isinstance(fn, ast.FunctionDef), f"`{name}` 이 async 다"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        f"`scanner.{name}` 에 await 가 있다"
    )
    seg = ast.unparse(fn)
    for token in _IO_TOKENS:
        assert token not in seg, f"`scanner.{name}` 에 `{token}` I/O 가 있다"


def test_a25_switch_leaf_does_not_touch_tick_volume() -> None:
    """A25 (N-4 · 금기 8) — 전환 leaf 가 `tick_volume` 을 건드리지 않는다.

    이중 채널 창의 `record_acml_vol` last-write-wins 비결정론은 이 사이클에서
    **근본 시정 불가**다(`handler.py` 가 미승인 8영역이라 tr_id 를 못 넘긴다).
    닫는 방법은 이중 채널 **금지** + 전환 창 프레임 0 뿐이고, 거기에 손을 대면
    BFB/VCP 거래량 게이트가 조용히 움직인다 = 미승인 매매 행위 변경.
    """
    src = _require(_SWITCH_REL, _SWITCH_MISSING)
    assert "tick_volume" not in _names_used(src), (
        f"{_SWITCH_REL} 가 `tick_volume` 을 **코드로** 참조한다 — 거래량 기록기는 "
        "이 사이클의 스코프 밖이다(N-4 · 금기 8)"
    )


# ===========================================================================
# A26 (금기 1) — 상수 보존
# ===========================================================================
@pytest.mark.parametrize(
    ("name", "expected"),
    [("TICK_TR_ID", UNIFIED), ("TICK_TR_ID_KRX", KRX_ONLY), ("TICK_TR_ID_NXT", NXT_ONLY)],
)
def test_a26_tick_constants_are_preserved(name: str, expected: str) -> None:
    """A26 (금기 1) — 상수 3개는 **삭제하지 않는다.** 사라지는 것은 반환 경로뿐.

    `test_cycle257_ast_dead_code_removed.py::_PRESERVED_TICK_CONSTS` 가 같은 값을
    리터럴로 핀한다. 통합 상수를 지우면 킬스위치 `off`(= 배포 전과 동일)와
    `TICK_TR_IDS` 멤버십(집계 분모 보존, cycle252 은폐 금지)이 함께 무너진다.
    """
    tree = _tree(_SCANNER_REL)
    values = {
        t.id: n.value.value
        for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
    }
    assert name in values, f"`scanner.{name}` 상수가 사라졌다 — 보존 계약(금기 1)"
    assert values[name] == expected


def test_a26b_unified_stays_in_the_canonical_set() -> None:
    """A26b (cycle252 은폐 금지) — `TICK_TR_IDS` 에서 통합을 빼지 않는다.

    빼면 `off` 로 되돌린 구독과 §7-B 재라우팅 전 레거시 구독이 집계 분모에서
    **조용히 사라진다** — `[tick_coverage] subscribed=` 가 줄어 숫자만 좋아진다.
    """
    src = _src(_SCANNER_REL)
    fn_free = re.search(
        r"TICK_TR_IDS\s*:\s*frozenset\[str\]\s*=\s*frozenset\(\{([^}]*)\}\)", src,
    )
    assert fn_free is not None, "`scanner.TICK_TR_IDS` 정본 집합 리터럴을 찾지 못했다"
    members = fn_free.group(1)
    for value in (UNIFIED, KRX_ONLY, NXT_ONLY):
        assert value in members, (
            f"`TICK_TR_IDS` 에서 `{value}` 가 빠졌다 — 집계 분모가 줄면 그것은 "
            "시정이 아니라 은폐다(cycle252 계약)"
        )
