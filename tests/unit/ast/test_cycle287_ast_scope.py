"""cycle287 Red — 범위 가드: **세 파일 외 프로덕션 diff 0** + 불변 봉인 + 구조 계약.

정본 = cycle287 도메인 자문 §9-J·§제약 (2026-09-12) + 브리프 제약.

## 이 사이클의 제1 계약

**프로덕션 코드는 딱 세 파일만 바뀐다.**

- `src/models/order.py`      (K1 — `OrderDivision` 에 `41`/`44` 추가, sha 핀 **0곳**)
- `src/engine/order_engine.py` (R·K — 라우팅 + 애프터 변환 + 봉인, **8영역 승인**)
- `src/api/order.py`         (§S7 — **docstring 만**, 본문 byte 동일, **8영역 승인**)

그 주장을 사람의 선언이 아니라 **sha** 로 증명한다(S1/S2). 세 파일은 정당하게 바뀌므로
핀 목록에서 **의도적으로 빠져 있고**(S1d), 대신 손대지 않기로 한 구간은 세그먼트 sha 로
따로 잠근다(S3).

## ⚠️ 브리프가 자문 §9-F 를 덮는다 — 전략 7파일은 diff 0

자문 §9-F 는 두 신규 파라미터(`order_exchange_clock_mode`·`after_market_exit_division`)를
7 전략 `DEFAULT_PARAMS` 에 명시하라고 했지만, **브리프 제약이 전략 7파일·`strategy_base.py`
를 diff 0 으로 못 박는다.** 그래서 이 사이클의 계약은:

* 두 키는 **어느 전략 `DEFAULT_PARAMS` 에도 없다**(S5).
* 기본값은 `order_engine` 의 **모듈 상수**가 정본이고, 키 부재 = `enforce` / `44` 다(S5).
* 🔴 **장중 킬스위치는 존재하지 않는다**(S7, 자문 §5-B). 종전 Red 헤더는 "롤백 경로는
  PUT 하나뿐" 이라고 적었지만 그것은 **사실이 아니다** — 두 키가 `param_catalog` 에도
  `current_params` 에도 없으므로 `validate_params` 가 `unknown_key` 로 만들고 라우트가
  422 + all-or-nothing 이다(실측). 롤백은 **1커밋 revert + 장외 배포**뿐이고, 급성
  상황의 우회는 기존 키 `PUT {"exchange":"KRX"}`(라우팅 전면 정지)인데 **프리장 청산과
  `stock_master` 프로브가 함께 꺼지는** 부작용이 있다.
* `DEFAULT_PARAMS`·`param_catalog` 등재와 화면 문구(자문 §3·§9-K)는 **cycle287b** 이며,
  그때 비로소 정식 킬스위치가 생긴다 — 그 사이클이 S5·S7 을 함께 갱신한다.

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI)/3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment`/원문 부분문자열의 sha256 으로만 잰다.

## 왜 `git grep`/`git ls-files`/bare `git diff HEAD` 를 쓰지 않는가

추적 파일만 보므로 Green 이 만든 **미추적** 파일을 로컬에서 못 보고 CI 에서만 잡는다
(cycle259 S4b). bare `git diff HEAD` 는 커밋 직후 공허해지고 다음 편집에서 무조건 RED 가
된다(cycle240 A11b · cycle252 G-252-5b). 스캔은 `Path(...).rglob("*.py")` + AST.

## ⚠️ 사이클 한정 — 커밋 후 갱신/삭제 의무

`_BASE_SHA` · `_SRC_TREE_DIGEST` · `_FROZEN_SEGMENTS` 는 base `a42f519` 의 blob 을 고정한
것이라 cycle287 의 무접촉 증거로만 유효하다. 그 파일들을 **정당하게** 바꾸는 다음 사이클이
이 dict 를 갱신하거나 이 테스트를 삭제한다(고아 가드 방지).

⚠️ dict 이름을 `*_CONTENT_SHA` 로 **짓지 않았다** — `test_cycle223g3_ast_guard_sees_staged.py`
의 `test_g3_9a` 가 모듈 레벨 `*_CONTENT_SHA` dict 를 가진 테스트 파일 집합을
`_PIN_GUARD_FILES`(4개)로 고정한다. cycle274/278/282/286 관례대로 `_BASE_SHA` 를 쓴다.

## Green 이 함께 해야 하는 핀 갱신 (이 파일 밖, 자문 §9-J)

`order_engine.py` 내용 sha **7곳** — 자매 4곳(`test_cycle222a3`:469 · `test_cycle223`:452 ·
`test_cycle223f`:364 · `test_cycle226`:1157, `test_g3_9b` 계약상 **넷 전부 같은 값**) +
무조건 3곳(`test_cycle274`:563 · `test_cycle278`:198 · `test_cycle282`:379).
`src/api/order.py` **9곳** — 무조건 5곳(`test_cycle274`:570 · `test_cycle276`:346 ·
`test_cycle278`:205 · `test_cycle282`:388 · `test_cycle286`:82) + **자매 4곳에 신규 등록**
(현재 dict 에 없어 `unexpected` 로 붉어진다).  `src/models/order.py` 는 **0곳**.
"""

from __future__ import annotations

import ast
import hashlib
import os
from datetime import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_ORDER_ENGINE_REL = "src/engine/order_engine.py"
_API_ORDER_REL = "src/api/order.py"
_MODELS_ORDER_REL = "src/models/order.py"

#: 이 사이클이 정당하게 바꾸는 세 파일 — 핀 목록에서 의도적으로 제외한다.
_CHANGED = (_MODELS_ORDER_REL, _ORDER_ENGINE_REL, _API_ORDER_REL)

#: base `a42f519` blob 의 파일 내용 sha256. **세 변경 파일은 없다**(S1d).
_BASE_SHA = {
    # 8영역 — 엔진 4파일 (order_engine 은 승인된 변경 대상이라 제외)
    "src/engine/risk.py":
        "19f48b4a4f7c3b4aa47b99a1426d22ec26884277a9f711c279753d6d7452dcc7",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/scanner.py":
        "fa8c0377f850b031d1983923957eb92ea593dc0eb9c1423359d8561efde78fb9",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    # 8영역 — realtime 전부
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/websocket.py":
        "1589cffb955e5af28ad0f145860bcc127ea8fda2b25d6817bd79c079472d5c4f",
    "src/realtime/websocket_pool.py":
        "bd1108dd40da4e72eab10581485b1b032e58af7c06754a9118fc7fafc20c8de7",
    # 8영역 — auth 전부
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py":
        "049341c7286b57a06337b6bc73ff4b0269efffad8f4554d97f275e7b8ec30a54",
    # 8영역은 아니지만 이 사이클이 무접촉을 약속한 파일
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 시각 표의 **유일 정본** — 읽기만 한다. 바꾸면 픽스처 동기 사슬
    # (`tools/test_fixtures/gen_market_state_fixture.py` + 프론트/E2E 픽스처 2)이
    # 통째로 딸려 오고, cycle282 `test_i1/i2/i3` 가 즉시 RED 다.
    "src/engine/market_state.py":
        "7594ccadec61aacc6a47b0ef7be46d96d9a82912235622edd790694209d0b48c",
    # TTL 축 — 호출부가 넘기는 **인자의 의미**만 바꾸고 이 파일은 손대지 않는다(K9-g/h).
    "src/engine/sell_rejection.py":
        "6df3a6c697019f0d0a35e4870d0fc115171d1504f11fb3e43ae16aea4883fdec",
    # 거부 분류기 — 키워드 집합을 늘리지 않는다(미분류 봉인이 정면 대응이다).
    "src/api/balance.py":
        "d8f3da874b3e2623695935d768cf5a502a3756e3425c41185e42576c27f6aa35",
    # 전략 7파일 (+ 패키지) — 브리프 제약: **전원 diff 0**
    "src/engine/strategies/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py":
        "0b7cfe745c6f437a7f55b7c6773e549c5c545f0c5b6c85be51623221a3b6afb0",
    "src/engine/strategies/donchian_swing.py":
        "107246d21feeac07ed6556269897b60d61ab1b617746d3c2f6aacd3d1385dfa0",
    "src/engine/strategies/kojiro.py":
        "bfc614808831b7a50664f8d4b7a7e168c3a77fd70fa51f55289cea78b5a84a47",
    "src/engine/strategies/long_tail_volatility.py":
        "728fc2d51edd6db9c0a6f6448b60d8b15872c273e5158caae3f814dd4394a8ee",
    "src/engine/strategies/momentum.py":
        "5bfc25a183a13ec0e00bdce7ff0e1727d323bd62f1ba8b8937561a4eb74c0da1",
    "src/engine/strategies/vcp_breakout.py":
        "f77ffc1896037692c47a6611a6d3b8aecf66bf17f3c6161a1cf52bc96f0ce3dd",
    "src/engine/strategies/volatility_breakout.py":
        "9034476410029bc14622cbf8ec32e0647406cf470e91b9aa740a3f7d5b6cd5e3",
}

#: `src/**/*.py` 전수(세 변경 파일 제외)의 (경로, 내용sha) 누적 digest.
#: 명시 dict 가 못 보는 나머지 ~120 파일의 **diff 0** 을 한 줄로 잠근다 —
#: `routes/`·`services/`·`db/`·`middleware/`·`workers/` 가 조용히 바뀌는 것도 접촉이다.
_SRC_TREE_FILES = 147
_SRC_TREE_DIGEST = (
    "01e200a2e2214f8cf8864b98bb0828b867688c48b8e8e39a644d31e3d8483e56"
)

#: 디렉터리 통째로 잠그는 영역 — 새 파일이 조용히 들어오는 것도 접촉이다.
#: ⚠️ 자문 §9-B 는 신규 leaf 를 `src/engine/` 최상위에 두는 것을 허용했지만
#: 브리프 제약("세 파일뿐")이 그것을 막는다 — 라우터는 `order_engine.py` 안에 둔다.
_PINNED_DIRS = ("src/realtime", "src/auth", "src/engine/strategies", "src/engine")

#: `scheduler.py` 정확 라인 수 + cycle257 영구 상한.
_SCHEDULER_LINES = 3897
_SCHEDULER_LINE_CAP = 3900

#: 손대지 않기로 한 **원문 구간**의 sha256 (base `a42f519`).
#: 키 = 구간 이름 / 값 = (시작 부분문자열, 끝 부분문자열, sha256).
_FROZEN_SEGMENTS = {
    # 매수 PR-F 사전 변환 — 브리프: "로직 자체는 byte 동일해야 한다".
    "execute_buy_prf": (
        "        order_division = OrderDivision.MARKET\n        order_price = 0\n",
        "            order_price = 0\n",
        "e08d54fc2bd52080360b1e6cd1157f3528216279c5ae274957a9eb171ecee11d",
    ),
    # 매도 프리장 사전 지정가 변환 — 애프터 분기는 이 블록 **뒤**에 순수 추가한다.
    "execute_sell_pre_nxt_preconvert": (
        "        if order_division == OrderDivision.MARKET:\n            try:\n"
        "                from src.engine.scanner import ticker_prices as _tp",
        "                    ticker, exc_info=True,\n                )\n",
        "768b9f144b95bcfcfb7f3110b20e71d6588f36e8aa93af3e28a77f141922ecaf",
    ),
    # cycle286 C4-a 판정 3줄 — 되돌리지 않는다.
    "cycle286_nxt_evidence": (
        '                        _exchange_ok = target_exchange in ("NXT", "SOR")',
        "                        _nxt_evidence = _exchange_ok and _window_ok\n",
        "9fc283054484b408e8055ce75cb090df103a7d8149d01a9cef0a0a41660d4b0a",
    ),
}

#: 라우팅 판정 함수 이름 (자문 §9-B).
_ROUTER = "_route_exchange_by_clock"

#: 신규 파라미터 2키 — `PARAM_RANGES`/`INT_PARAMS` 편입 **금지**(리스크 정체성 상수).
_NEW_PARAM_KEYS = ("order_exchange_clock_mode", "after_market_exit_division")

_STRATEGY_FILES = tuple(
    rel for rel in _BASE_SHA if rel.startswith("src/engine/strategies/")
    and not rel.endswith("__init__.py")
)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _tree_digest() -> tuple[int, str, list[str]]:
    changed = set(_CHANGED)
    h = hashlib.sha256()
    rels: list[str] = []
    for path in sorted(_ROOT.glob("src/**/*.py")):
        rel = str(path.relative_to(_ROOT)).replace(os.sep, "/")
        if rel in changed:
            continue
        rels.append(rel)
        h.update(rel.encode())
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return len(rels), h.hexdigest(), rels


def _function(rel: str, name: str):
    src = _src(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel}: 함수 `{name}` 부재")


def _method(rel: str, cls_name: str, name: str):
    src = _src(rel)
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel}: `{cls_name}.{name}` 부재")


# ===========================================================================
# S1 — 세 파일 외 프로덕션 diff 0
# ===========================================================================
@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_s1_pinned_files_are_byte_identical(rel: str) -> None:
    """S1 — 8영역(order/api 제외)·전략 7파일·`strategy_base`·`market_state`·
    `sell_rejection`·`balance` **diff 0**.

    한 파일이라도 바뀌면 "cycle287 은 세 파일만 바꾼다" 가 거짓이고, 별도 승인
    (8영역 승인 + `domain-consult` 선행)이 필요하다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 사라졌다 — 무접촉 계약 위반"
    got = _content_sha(rel)
    assert got == _BASE_SHA[rel], (
        f"{rel} 이 base(a42f519) 에서 바뀌었다 — {got} != {_BASE_SHA[rel]}. "
        "cycle287 의 프로덕션 범위는 models/order · order_engine · api/order 셋뿐이다"
    )


def test_s1b_whole_src_tree_is_byte_identical_except_the_three() -> None:
    """S1 — `src/**/*.py` **전수** 무접촉(세 파일 제외).

    명시 dict 가 못 보는 `routes/`·`services/`·`db/`·`middleware/`·`config.py` 가 조용히
    바뀌는 것도 접촉이다. 자문 §9-K 의 후속(param_catalog·Settings·manual-sell·
    sell_rejection 정식 인자·`excg_id_dvsn_Cd` 수집)은 **이 사이클 밖**이고, 이 가드가
    그 경계를 지킨다.
    """
    count, digest, rels = _tree_digest()
    assert count == _SRC_TREE_FILES, (
        f"`src/` 아래 .py 파일 수가 {count} (기대 {_SRC_TREE_FILES}) — "
        f"신규/삭제가 있다. 세 파일 외 신규 모듈은 이 사이클 범위 밖이다"
    )
    assert digest == _SRC_TREE_DIGEST, (
        "세 파일 외 `src/` 프로덕션 코드가 바뀌었다. 범인 찾기:\n"
        "  python3 -c \"import hashlib,pathlib;[print(hashlib.sha256(p.read_bytes())"
        ".hexdigest(), p) for p in sorted(pathlib.Path('src').rglob('*.py'))]\"\n"
        f"  기대 digest {_SRC_TREE_DIGEST} / 실제 {digest}"
    )


def test_s1c_scheduler_line_count_is_exact_and_under_cap() -> None:
    """S1 — `scheduler.py` 무접촉의 대리 지표 = 정확 라인 수 + 영구 상한 **< 3,900**.

    익일청산·15:20 강제청산이 `execute_sell` 경유라 규칙 1 을 `scheduler.py` 무접촉으로
    물려받는 것이 계약이다(자문 §I).
    """
    n = len(_src("src/engine/scheduler.py").splitlines())
    assert n < _SCHEDULER_LINE_CAP, (
        f"`scheduler.py` 가 {n}L — cycle257 영구 상한 {_SCHEDULER_LINE_CAP} 위반"
    )
    assert n == _SCHEDULER_LINES, (
        f"`scheduler.py` 가 {n}L 로 바뀌었다 (기대 {_SCHEDULER_LINES}L)"
    )


@pytest.mark.parametrize("rel_dir", _PINNED_DIRS)
def test_s1d_no_new_files_slip_into_pinned_dirs(rel_dir: str) -> None:
    """S1 — 잠근 디렉터리에 **새 .py 가 생기는 것**도 접촉이다.

    ⚠️ `src/engine` 도 잠겄다 — 자문 §9-B 는 신규 leaf 를 허용했지만 브리프 제약이
    "세 파일뿐" 이다. 라우터·봉인·애프터 변환은 전부 `order_engine.py` 안에 둔다.
    """
    found = {
        str(p.relative_to(_ROOT)).replace(os.sep, "/")
        for p in (_ROOT / rel_dir).rglob("*.py")
    }
    _count, _digest, all_rels = _tree_digest()
    pinned = {rel for rel in all_rels if rel.startswith(rel_dir + "/")}
    pinned |= {rel for rel in _CHANGED if rel.startswith(rel_dir + "/")}
    assert found == pinned, (
        f"{rel_dir}: 신규 {sorted(found - pinned)} / 삭제 {sorted(pinned - found)}"
    )


def test_s1e_changed_files_are_excluded_from_the_pin_on_purpose() -> None:
    """S1 — 변경 대상 세 파일은 `_BASE_SHA` 에 **없다**.

    있으면 정당한 변경이 이 가드에 막혀 Green 이 "핀을 재산출하지 마라" 문구를 만나고,
    그 문구가 승인된 변경을 되돌리도록 오도한다(cycle263 실측 사고 계열).
    """
    for rel in _CHANGED:
        assert (_ROOT / rel).exists(), f"{rel} 경로 오류"
        assert rel not in _BASE_SHA, f"{rel} 이 무접촉 핀 목록 안이다 — 범위 설계 오류"


# ===========================================================================
# S2 — 불변 구간 세그먼트 봉인
# ===========================================================================
@pytest.mark.parametrize("name", sorted(_FROZEN_SEGMENTS))
def test_s2_frozen_source_segments_are_byte_identical(name: str) -> None:
    """S2 — 손대지 않기로 한 원문 구간 3종의 sha256 불변.

    * `execute_buy_prf` — 브리프: "매수 시장가 사전 변환(PR-F) 로직 자체는 byte 동일"
    * `execute_sell_pre_nxt_preconvert` — 애프터 분기는 이 블록 **뒤**에 순수 추가
    * `cycle286_nxt_evidence` — cycle286 판정을 되돌리지 않는다

    ⚠️ `_window_ok` 를 지우지 말 것 — 라우팅을 `off` 로 내리면 16:05 의 `target_exchange`
    가 base 로 복귀해 `_exchange_ok` 가 참이 된다. 그때 오염을 막는 **유일한 방어**가
    `_window_ok` 다(두 축의 논리적 중복은 enforce 모드에서만 성립한다).
    """
    head, tail, expected = _FROZEN_SEGMENTS[name]
    src = _src(_ORDER_ENGINE_REL)
    assert head in src, f"`{name}` 시작 구간이 사라졌다"
    start = src.index(head)
    idx = src.index(tail, start)
    seg = src[start: idx + len(tail)]
    got = hashlib.sha256(seg.encode()).hexdigest()
    assert got == expected, (
        f"구간 `{name}` 이 바뀌었다 — {got} != {expected}\n--- 현재 ---\n{seg}"
    )


def test_s2b_ttl_axis_window_is_not_narrowed() -> None:
    """S2 — `is_nxt_session_hours` 의 `15:30~20:00` 을 **좁히지 않는다**.

    TTL 축 재정의(K9-g)는 `sell_rejection.py` 를 고치는 것이 아니라 **호출부가 넘기는
    인자의 의미**를 "매도 가능 창 안인가" 로 바꾸는 방식이다. 그래야 그 파일이
    diff 0 이고, 그 사실을 여기서 리터럴 존재로 복창한다(cycle286 `test_g4_2` 답습).
    """
    src = _src("src/engine/sell_rejection.py")
    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "is_nxt_session_hours"
    )
    seg = ast.get_source_segment(src, fn) or ""
    for token in ("15, 30", "20, 0", "8, 0", "9, 0"):
        assert token in seg, f"`is_nxt_session_hours` 에서 `time({token})` 가 사라졌다"


def test_s2c_ltv_main_buy_cutoff_is_unchanged() -> None:
    """S2 — cycle286 `MAIN_BUY_CUTOFF_KST` == 15:20 불변(브리프 제약).

    `long_tail_volatility.py` 는 `_BASE_SHA` 로 이미 잠겨 있지만, 값 자체를 한 번 더
    복창해 "이 상수는 cycle287 의 접촉 대상이 아니다" 를 사람이 읽을 수 있게 한다.
    """
    from src.engine.strategies import long_tail_volatility as ltv_mod

    assert getattr(ltv_mod, "MAIN_BUY_CUTOFF_KST", None) == time(15, 20)


def test_s2d_sell_market_preconvert_marker_is_still_emitted() -> None:
    """S2 — `[sell_market_preconvert_pre_nxt]` 마커가 소스에 존재한다.

    프리장 청산 경로를 좁히지 않는다는 계약의 텍스트 증거(행위 증거는
    `test_cycle287_krx_after_exit.py::test_k3d`).
    """
    assert "[sell_market_preconvert_pre_nxt]" in _src(_ORDER_ENGINE_REL)


# ===========================================================================
# S3 — 라우터 구조 계약
# ===========================================================================
def test_s3_router_exists_with_the_specified_signature() -> None:
    """S3 (RED) — `_route_exchange_by_clock(base, *, side, mode, now)` 존재.

    `side`/`mode`/`now` 는 **키워드 전용**이어야 한다 — 위치 인자로 열어 두면
    호출부가 `side`/`mode` 순서를 뒤바꿔 `sell_only` 가 조용히 반대로 동작한다.
    """
    _src_text, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    assert [a.arg for a in fn.args.args] == ["base"], (
        f"위치 인자는 `base` 하나여야 한다: {[a.arg for a in fn.args.args]}"
    )
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    for name in ("side", "mode", "now"):
        assert name in kwonly, f"키워드 전용 인자 `{name}` 부재: {kwonly}"
    assert not isinstance(fn, ast.AsyncFunctionDef), (
        "라우터는 **동기** 함수다 — `await` 를 늘리면 A-ATOMIC 구간 계약과 "
        "매수 원자성 논증이 흔들린다"
    )


def test_s3b_router_has_no_time_literals() -> None:
    """S3 (RED) — 라우터 안에 **시각 리터럴 0건**.

    경계는 `market_state.MARKET_TABLE`(유일 정본)에서 나온다. 여기에 `time(16, 0)` 을
    적으면 두 번째 정본이 생기고, KIS 가 시간표를 옮기는 날 둘이 갈라진다
    (cycle283 이 커트오프를 15:40 → 20:00 로 옮긴 것이 정확히 그 종류의 변경이다).
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    bad = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if fname in ("time", "dtime", "_dtime") and node.args:
                bad.append(ast.dump(node)[:80])
    assert bad == [], f"라우터가 시각 리터럴을 만든다: {bad}"


def test_s3c_router_is_never_raise() -> None:
    """S3 (RED) — 라우터는 `except Exception` 으로 **전부 흡수**하고 base 를 돌려준다.

    fail-safe 방향(브리프): 판정 실패가 주문 자체를 막아서는 안 된다.
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    handlers = [
        h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers
    ]
    assert handlers, "라우터에 `try/except` 가 없다 — 판정 예외가 주문을 막는다"
    caught = {
        (h.type.id if isinstance(h.type, ast.Name) else getattr(h.type, "attr", None))
        for h in handlers
    }
    assert "Exception" in caught, f"`except Exception` 부재: {caught}"
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert raises == [], "라우터가 예외를 던진다 — never-raise 계약 위반"


def test_s3d_router_reads_market_state_and_session_lazily() -> None:
    """S3 (RED) — `market_state`·`session` 은 **함수 안 lazy import**.

    최상단에 넣으면 cycle286 `test_g4_3`(최상단 `src.*` import 집합 14개 고정)과
    cycle276 `test_c4_2`(증가분 = `{src.engine.llm_buy_gate}`)가 즉시 RED 다.
    cycle286 자신이 `_dtime`·`stock_master` 를 그렇게 했다.
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    modules = {
        n.module
        for n in ast.walk(fn)
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert "src.engine.market_state" in modules, (
        f"라우터가 `market_state` 를 함수 안에서 import 하지 않는다: {sorted(modules)}"
    )
    assert "src.engine.session" in modules, (
        "프리장 판정은 `session_tracker.active`(PR-F 와 같은 출처)를 써야 한다 — "
        f"{sorted(modules)}"
    )


def test_s3e_order_engine_top_level_src_imports_are_unchanged() -> None:
    """S3 (RED) — `order_engine.py` **모듈 최상단** `src.*` import 집합 불변.

    cycle286 `test_g4_3` 이 이 집합을 정확히 고정한다. 새 의존(`market_state`·`session`·
    `config`)은 전부 **함수 안 lazy import** 여야 한다.
    """
    tree = ast.parse(_src(_ORDER_ENGINE_REL))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            top.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    top.add(alias.name)
    expected = {
        "src.api.balance",
        "src.api.base",
        "src.api.order",
        "src.db.system_logs",
        "src.db.trade_history",
        "src.engine",
        "src.engine.daily_emit_cap",
        "src.engine.scanner",
        "src.engine.sell_rejection",
        "src.engine.strategy_base",
        "src.engine.strategy_registry",
        "src.engine.util.tick_size",
        "src.models.order",
        "src.models.trade",
    }
    assert top == expected, (
        f"최상단 `src.*` import 가 바뀌었다 — 신규 {sorted(top - expected)} / "
        f"삭제 {sorted(expected - top)}. 새 의존은 함수 안 lazy import 로 둔다"
    )


def test_s3f_sendable_divisions_agree_with_the_market_table() -> None:
    """S3 (RED) — `_SENDABLE_DIVISIONS` 가 `market_state` 표와 정합한다.

    `41`/`44` 는 K6(KRX 애프터), `00`/`01` 은 K3(KRX 정규장) 에 있어야 한다.
    이 정합이 깨지면 16:00~20:00 이 `both_unsupported_keep` 으로 떨어져 애프터
    청산이 통째로 열리지 않는다(무음 실패).
    """
    from src.engine import order_engine as _oe
    from src.engine.market_state import MARKET_TABLE

    sendable = set(getattr(_oe, "_SENDABLE_DIVISIONS", ()))
    assert sendable, "`_SENDABLE_DIVISIONS` 부재"
    rows = {r.row_id: set(r.order_divisions) for r in MARKET_TABLE}
    assert {"41", "44"} <= rows["K6"], "K6(KRX 애프터)에 41/44 가 없다"
    assert {"41", "44"} <= sendable, f"`_SENDABLE_DIVISIONS` 에 41/44 가 없다: {sendable}"
    assert {"00", "01"} <= rows["K3"] & sendable


def test_s3g_router_is_applied_inside_strategy_exchange_async() -> None:
    """S3 (RED) — 라우팅은 `_strategy_exchange_async` **안**에서 적용된다.

    * 호출부 2곳(`:361` 매수 · `:666` 매도)을 한 번에 덮는다.
    * cycle286 판정보다 **앞**이라 `target_exchange` = "실제로 보낸 거래소" 의미 보존.
    * `[nxt_downgrade]`/`[stock_master_miss]` 가 라우팅 **전**에 발화해 관측 회귀 0.
    * G-MKT1/G-MKT2(`test_cycle100_*`)가 요구하는 소스 문자열이 그대로 남는다.
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", "_strategy_exchange_async")
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and (
            getattr(n.func, "id", None) == _ROUTER
            or getattr(n.func, "attr", None) == _ROUTER
        )
    ]
    assert calls, f"`_strategy_exchange_async` 가 `{_ROUTER}` 를 부르지 않는다"


def test_s3h_limit_price_nxt_branch_is_still_present() -> None:
    """S3 — `limit_price > 0` 분기를 **지우지 않는다**.

    `test_cycle100_strategy_exchange_persistence_sell.py:96` 이 이 문자열을 영속
    단정한다. 호출자가 0곳(dead)이지만 지우면 그 가드가 RED 다 — 대신 그 분기의
    결과에도 라우팅을 씌운다(`test_r7_*`).
    """
    src = _src(_ORDER_ENGINE_REL)
    assert "limit_price > 0" in src
    assert "await self._strategy_exchange_async" in src


# ===========================================================================
# S4 — enum · cancel_order
# ===========================================================================
def test_s4_order_division_members_are_exactly_four() -> None:
    """S4 (RED) — `OrderDivision` 값 집합 == `{00, 01, 41, 44}`.

    IOC/FOK(42/43/45/46)는 잔량 자동취소라 손절 잔여를 잃고, 47(최우선지정가)은
    크로스하지 않아 체결 보장이 없다 = 손절 수단이 아니다(자문 §3-A).
    """
    from src.models.order import OrderDivision

    assert {d.value for d in OrderDivision} == {"00", "01", "41", "44"}
    assert OrderDivision.LIMIT.value == "00"
    assert OrderDivision.MARKET.value == "01"


def test_s4b_models_order_is_not_pinned_anywhere() -> None:
    """S4 — `src/models/order.py` 는 어느 sha 핀에도 없다(자문 §8-4 실측).

    enum 멤버 추가의 가드 비용이 0 이라는 사실을 고정한다 — 누가 이 파일을
    `_BASE_SHA` 류에 넣으면 다음 enum 확장이 이유 없이 막힌다.
    """
    needle = f'"{_MODELS_ORDER_REL}":'   # sha 핀 dict 의 키 형태만 찾는다
    hits = []
    for path in (_ROOT / "tests").rglob("*.py"):
        if path.name.startswith("test_cycle287_"):
            continue  # 이 사이클의 산출물(산문 인용)은 핀이 아니다
        if needle in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path.relative_to(_ROOT)))
    assert hits == [], f"`{_MODELS_ORDER_REL}` 가 sha 핀 dict 키로 등장한다: {hits}"


def test_s4c_cancel_order_ord_dvsn_stays_hardcoded_00() -> None:
    """S4 — 취소의 `ORD_DVSN` 은 **`"00"` 하드코딩 유지 · 인자 추가 없음**.

    ⚠️ 이 테스트는 종전 Red 를 **뒤집은** 것이다(자문 §4-C1·§S7 우선). 종전 Red 는
    `cancel_order(..., order_division="00")` opt-in 인자를 요구했지만 자문이 그것을
    이 사이클 밖으로 밀어냈다. 근거 셋:

    * KIS **공식 취소 샘플**이 `ord_dvsn="00"` + 0 아닌 `ord_unpr` 를 쓴다.
    * 국내주식 스펙에 "취소 시 원주문 호가유형을 실어라" 는 규약이 **없다**
      (선물옵션 API 는 "[취소] 01 로 입력" 이라 명시하는데, 국내주식엔 그 문장이 없다).
    * 16:00~20:00 의 취소·부분체결 실적이 **all-time 0건** — 지금 바꿀 근거가 0이고,
      추측으로 바꾸면 **작동 중인 정규장 취소**를 위험에 넣는다.

    그래서 배관을 열지 않고 `[after_cancel_result]` 관측만 붙여 첫날 실측으로
    판정한다(`result=error` 가 나오면 그때 opt-in 을 넣는다).
    """
    body_src = ast.get_source_segment(
        _src(_API_ORDER_REL), _function(_API_ORDER_REL, "cancel_order")[1]
    ) or ""
    assert '"ORD_DVSN": "00"' in body_src, (
        "취소의 `ORD_DVSN` 하드코딩이 사라졌다 — 이 사이클은 그 값을 바꾸지 않는다"
    )
    _s2, fn = _function(_API_ORDER_REL, "cancel_order")
    names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "order_division" not in names, (
        f"`cancel_order` 에 `order_division` 인자가 들어왔다: {names}. "
        "쓰지 않는 인자를 먼저 넣지 않는다 — 첫날 실측(`[after_cancel_result]`) 뒤다"
    )


def test_s4c2_api_order_change_is_documentation_only() -> None:
    """S4 (RED) — `src/api/order.py` 의 변경은 **docstring 뿐**이다(자문 §S7).

    `place_order` docstring 이 `ORD_DVSN` 표(00·01·41·44 + 애프터 시장가 없음 +
    ETP 불가)와 거래소 규칙을 담고, `cancel_order` docstring 이 "애프터 원주문 취소는
    미검증" 을 명시한다. 그래야 다음 사람이 `"00"` 하드코딩을 보고 "검증됐다" 고
    오독하지 않는다.

    본문 byte 동일은 이 사이클의 계약이므로, docstring 을 제외한 **AST 구조**가
    base 와 같은지를 함수별 인자·본문 문장 수로 잰다(`ast.dump` sha 는 3.12/3.13
    출력차 때문에 금지 — cycle256 G-250-5).
    """
    src = _src(_API_ORDER_REL)
    place_doc = ast.get_docstring(_function(_API_ORDER_REL, "place_order")[1]) or ""
    cancel_doc = ast.get_docstring(_function(_API_ORDER_REL, "cancel_order")[1]) or ""

    for token in ("41", "44"):
        assert token in place_doc, (
            f"`place_order` docstring 에 애프터 호가코드 `{token}` 설명이 없다"
        )
    assert "ETP" in place_doc or "ETF" in place_doc, (
        "`place_order` docstring 에 애프터 ETP 불가 경고가 없다"
    )
    for needle in ("미검증", "미실측", "미확인"):
        if needle in cancel_doc:
            break
    else:
        raise AssertionError(
            "`cancel_order` docstring 이 애프터 원주문 취소의 **미지** 상태를 적지 않았다 "
            f"— {cancel_doc!r}"
        )
    # 본문(문장 수)은 불변 — docstring 만 늘어난다.
    for fname, stmts in (("place_order", 9), ("cancel_order", 8)):
        _s3, fn = _function(_API_ORDER_REL, fname)
        body = [n for n in fn.body if not (
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )]
        assert len(body) == stmts, (
            f"`{fname}` 본문 문장 수가 {len(body)} (base {stmts}) — "
            "이 사이클의 `api/order.py` 변경은 docstring 뿐이다"
        )
    del src


def test_s4d_place_order_still_passes_the_value_through() -> None:
    """S4 — `place_order` 가 `ORD_DVSN` 을 값 그대로 흘려보낸다(화이트리스트 금지).

    누가 `if order_division in (LIMIT, MARKET)` 류 검증을 끼워 넣으면 `44` 가
    조용히 사라진다(`execute_buy:410` 의 화이트리스트가 정확히 그 함정이다).
    """
    body_src = ast.get_source_segment(
        _src(_API_ORDER_REL), _function(_API_ORDER_REL, "place_order")[1]
    ) or ""
    assert '"ORD_DVSN": order_division.value' in body_src


# ===========================================================================
# S5 — 파라미터 (브리프 제약: 전략 7파일 diff 0)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s5_new_keys_are_not_in_param_ranges_or_int_params(key: str) -> None:
    """S5 (RED) — 두 신규 키는 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**.

    리스크·라우팅 정체성 상수이고 AI 자문 자동 적용 경로 밖이다
    (cycle242 `max_lot_units` · cycle245 `max_lot_ratio_mult` 관례).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES, f"`{key}` 가 PARAM_RANGES 에 들어왔다"
    assert key not in INT_PARAMS, f"`{key}` 가 INT_PARAMS 에 들어왔다"


@pytest.mark.parametrize("rel", sorted(_STRATEGY_FILES))
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s5b_new_keys_are_absent_from_strategy_defaults(rel: str, key: str) -> None:
    """S5 — 두 키는 **어느 전략 파일에도 없다**(브리프 제약 = 전략 7파일 diff 0).

    ⚠️ 자문 §9-F 는 `DEFAULT_PARAMS` 등재를 요구했지만 브리프가 그것을 막는다.
    따라서 **키 부재 = `enforce` / `44`** 가 유일한 운영 기본이고, 등재·`param_catalog`·
    화면 문구는 후속 사이클이다. 그 사이클이 이 테스트를 갱신한다.
    """
    assert key not in _src(rel), (
        f"{rel} 에 `{key}` 가 들어왔다 — 전략 7파일 diff 0 계약 위반"
    )


@pytest.mark.parametrize(
    "const, value",
    [
        ("_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT", "enforce"),
        ("_AFTER_EXIT_DIVISION_DEFAULT", "44"),
    ],
)
def test_s5c_default_constants_live_in_order_engine(const: str, value: str) -> None:
    """S5 (RED) — 기본값의 정본은 `order_engine` **모듈 상수**다.

    전략 `DEFAULT_PARAMS` 가 비어 있으므로 상수가 유일한 정본이다. 리터럴을 판정
    지점마다 흩뿌리면 롤백 PUT 이 한쪽만 바꾸는 사고가 난다.
    """
    from src.engine import order_engine as _oe

    got = getattr(_oe, const, None)
    assert got == value, f"`order_engine.{const}` = {got!r} (기대 {value!r})"


def test_s5d_after_exit_division_whitelist_is_exactly_44_and_41() -> None:
    """S5 (RED) — dial 허용 집합 == `{"44", "41"}`.

    클램프가 아니라 **화이트리스트**다 — 집합 밖은 `44` 로 폴백해 청산을 여는
    방향으로 떨어진다(`test_k5c_*`). `47`·IOC/FOK 가 조용히 나가는 것도 막는다.
    """
    from src.engine import order_engine as _oe

    allowed = getattr(_oe, "_AFTER_EXIT_DIVISION_ALLOWED", None)
    assert allowed is not None, "`_AFTER_EXIT_DIVISION_ALLOWED` 부재"
    assert set(allowed) == {"44", "41"}, f"허용 집합 {sorted(allowed)}"


# ===========================================================================
# S6 — 자문 §S2 상수 전수 + `_apply_clock` 적용 지점 (cycle287 추가)
# ===========================================================================
def test_s6_clock_routed_bases_are_exactly_nxt_and_sor() -> None:
    """S6 (RED) — `_CLOCK_ROUTED_BASES == ("NXT", "SOR")`.

    `KRX` 가 이 집합에 들어오면 `base_krx` 조기통과가 사라져 `nxt_tradable=False`
    다운그레이드가 내린 `KRX` 를 라우터가 다시 판정한다 — 프리장에서 그 값이 base 로
    "복귀" 하면 NXT 비대상 종목에 NXT 주문이 나간다.
    """
    from src.engine import order_engine as _oe

    got = getattr(_oe, "_CLOCK_ROUTED_BASES", None)
    assert got is not None, "`_CLOCK_ROUTED_BASES` 부재"
    assert tuple(got) == ("NXT", "SOR"), got


def test_s6b_giveup_threshold_is_five() -> None:
    """S6 (RED) — `_AFTER_EXIT_GIVEUP_THRESHOLD == 5` (자문 §1-E 봉인 2).

    상한 검산: 종목당 ≤10 주문(5회 × 1차+폴백) / 보유 7종목 전건 실패 ≤70 주문/저녁.
    KIS 20/s 한도 대비 무해하고, 30초 TTL 만으로 남는 ticker 당 ≈1,440 요청을
    ≈10 으로 수렴시킨다.
    """
    from src.engine import order_engine as _oe

    assert getattr(_oe, "_AFTER_EXIT_GIVEUP_THRESHOLD", None) == 5


def test_s6c_exit_capable_krx_phases_are_the_three_sendable_ones() -> None:
    """S6 (RED) — `_EXIT_CAPABLE_KRX_PHASES == {REGULAR, CLOSE_AUCTION, AFTER_MARKET}`.

    TTL 축(자문 §4-I)의 정의 = "그 시각 KRX 가 우리 청산 호가를 받는가". 09-14 **전**에는
    이 술어가 `is_krx_main_hours` 와 **완전히 일치**하고(AFTER_SINGLE K7 은 집합 밖),
    09-14 부터 `AFTER_MARKET` 하나만 늘어난다 — 그래서 `sell_rejection.py` 를 고치지
    않고 호출부 인자의 **의미**만 바꾸는 것이 성립한다.

    ⚠️ `PRE_AUCTION`(시가 단일가)을 넣으면 안 된다 — 그 창의 거부는 09:00 재평가를
    기다리는 것이 옳고, 5분 TTL 로 줄이면 단일가에 시장가를 반복 발사한다.
    """
    from src.engine import order_engine as _oe
    from src.engine.market_state import MarketPhase

    got = getattr(_oe, "_EXIT_CAPABLE_KRX_PHASES", None)
    assert got is not None, "`_EXIT_CAPABLE_KRX_PHASES` 부재"
    assert set(got) == {
        MarketPhase.REGULAR, MarketPhase.CLOSE_AUCTION, MarketPhase.AFTER_MARKET,
    }, sorted(p.name for p in got)
    assert MarketPhase.PRE_AUCTION not in set(got), (
        "시가 단일가를 '청산 가능' 으로 보면 그 창의 TTL 이 5분으로 줄어 "
        "단일가에 시장가를 반복 발사한다"
    )


def test_s6d_apply_clock_is_the_single_application_seam() -> None:
    """S6 (RED) — 적용은 `_apply_clock` **하나**를 경유한다(자문 §S4).

    라우터를 호출부마다 직접 부르면 마커·mode 조회·예외 흡수가 네 군데로 복제되고,
    한 곳을 빠뜨리면 그 경로만 조용히 라우팅을 비켜간다. `_apply_clock` 은 **동기**여야
    한다 — 동기 취소 3경로(`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`)가
    같은 seam 을 쓰기 때문이다(자문 §4-C2).
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", "_apply_clock")
    assert not isinstance(fn, ast.AsyncFunctionDef), (
        "`_apply_clock` 이 async 다 — 동기 취소 3경로가 이 seam 을 쓸 수 없다"
    )
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert "side" in kwonly, f"`side` 키워드 전용 인자 부재: {kwonly}"


@pytest.mark.parametrize(
    "method",
    ["_cancel_after_wait", "_cancel_and_reorder", "cancel_remaining"],
)
def test_s6e_sync_cancel_paths_go_through_apply_clock(method: str) -> None:
    """S6 (RED) — 동기 취소·재주문 3경로가 `_apply_clock` 을 경유한다(자문 §4-C2).

    셋은 `self._strategy_exchange(strategy_id)`(DB 값 직독 = 전부 `SOR`)를 쓴다.
    라우팅을 async 관문에만 넣으면 **주문은 KRX, 취소는 SOR** 로 갈린다.
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", method)
    calls = {
        getattr(n.func, "attr", None)
        for n in ast.walk(fn) if isinstance(n, ast.Call)
    }
    assert "_apply_clock" in calls, (
        f"`{method}` 가 `_apply_clock` 을 경유하지 않는다 — 취소 거래소가 원주문과 "
        f"갈린다. 현재 호출: {sorted(c for c in calls if c)}"
    )


# ===========================================================================
# S7 — 🔴 장중 킬스위치는 **없다** (자문 §5-B — 종전 Red 의 S5 주장을 뒤집는다)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s7_new_keys_cannot_be_put_at_runtime(key: str) -> None:
    """S7 — 두 신규 키는 `PUT /api/strategies/{id}/params` 로 **바꿀 수 없다**.

    ⚠️ 종전 Red 헤더는 "장중 롤백 경로는 PUT 하나뿐" 이라고 적었지만 그것은 **사실이
    아니다**(자문 §5-B). `validate_params` 는 `key not in current_params or spec is None`
    을 `unknown_key` **오류**로 만들고, 라우트가 오류 1건에 422 + all-or-nothing 이다.
    두 키는 (브리프 제약 때문에) 어느 전략 `DEFAULT_PARAMS` 에도 없고 `param_catalog`
    에도 없으므로 **항상** `unknown_key` 다.

    ⇒ **이 사이클에 장중 킬스위치는 존재하지 않는다.** 롤백은 1커밋 revert + 장외
    배포(15:30~19:55 · 21:35~07:45 · 주말)뿐이고, 급성 시에는 기존 키
    `PUT {"exchange":"KRX"}` 가 라우팅을 전면 정지시키지만 **프리장 청산과
    `stock_master` 프로브가 함께 꺼지는** 부작용이 있다.

    이 테스트는 그 불편한 사실을 **고정**한다 — 두 키를 `param_catalog` +
    `DEFAULT_PARAMS` 에 등재하는 cycle287b 가 이 테스트를 갱신하고, 그때 비로소
    정식 킬스위치가 생긴다. (그 전에 누가 "PUT 으로 끄면 된다" 고 적으면 거짓이다.)
    """
    from src.engine.param_validation import validate_params

    current = {"exchange": "SOR", "tradable_boards": ["main"]}
    result = validate_params("long_tail_volatility", current, {key: "off"})
    codes = {(e.key, e.code) for e in result.errors}
    assert (key, "unknown_key") in codes, (
        f"`{key}` 가 PUT 으로 통과한다 — 킬스위치가 생겼다면 이 테스트와 "
        f"`_NEW_PARAM_KEYS` 주석, 그리고 cycle287 보고서의 롤백 절을 함께 갱신하라. "
        f"실제 오류: {codes}"
    )
    assert result.accepted == {}, result.accepted
