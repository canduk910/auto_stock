"""cycle290 Red — 범위 가드: **전략 7파일 `DEFAULT_PARAMS` + `param_catalog` 외 diff 0**.

정본 = cycle290 도메인 자문 §S1·§S3·§S4 (2026-09-13) + 브리프 제약.

## 이 사이클의 제1 계약

**프로덕션 코드는 `src/engine/strategies/*.py` 7파일의 `DEFAULT_PARAMS` 와
`src/engine/param_catalog.py` 만 바뀐다.**

`order_engine.py` 는 이미 두 키를 읽는 코드를 갖고 있으므로 **손댈 이유가 없다**.
`param_validation.py` 도 무접촉이다 — **등재만으로 판정이 통해야** 한다.

8영역 + `scheduler.py` 파일 내용 sha 는 정본 `test_cycle222a3_ast_followup_fixes.py::
_APPROVED_CONTENT_SHA` 한 곳에만 둔다(cycle419 — 이 파일의 S1 파일 핀·정확 줄 수 핀·S3
`src/engine` 파일 이름 목록은 걷었다. 새 `.py` 를 짚는 파일 수 핀은 cycle287 S1d 한 곳이다).

## 왜 세그먼트 sha 를 따로 잠그는가 (S2)

`DEFAULT_PARAMS` 는 클래스 **속성**이라 메서드 세그먼트에 포함되지 않는다. 따라서
7 전략의 `check_buy_signal`·`check_exit_signal`·`calc_buy_quantity`·`prepare` 28
세그먼트는 이 사이클에서 **하나도 깨지지 않아야** 한다. 하나라도 붉어지면 핀을 옮기지
말고 **코드를 되돌려라** — `DEFAULT_PARAMS` 밖을 건드렸다는 신호다.

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI)/3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment` 의 sha256 으로만 잰다.

## 왜 `git grep`/`git ls-files`/bare `git diff HEAD` 를 쓰지 않는가

추적 파일만 보므로 Green 이 만든 **미추적** 파일을 로컬에서 못 보고 CI 에서만 잡는다
(cycle259 S4b). bare `git diff HEAD` 는 커밋 직후 공허해지고 다음 편집에서 무조건 RED 가
된다(cycle240 A11b · cycle252 G-252-5b). 스캔은 `Path(...).rglob("*.py")` + AST.

## 핀의 자리

`_SEGMENT_SHA`(S2, 전략 메서드 세그먼트 28핀)는 이 파일의 내용 계약이다 — 그 메서드를
정당하게 바꾸는 사이클이 값을 옮긴다. `scheduler.py` 라인 **상한**(`< 3,900`, cycle257)은
S1b 가 계속 복창한다.
"""

from __future__ import annotations

import ast
import hashlib
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_STRATEGY_META: tuple[tuple[str, str], ...] = (
    ("momentum", "MomentumStrategy"),
    ("volatility_breakout", "VolatilityBreakoutStrategy"),
    ("long_tail_volatility", "LongTailVolatilityStrategy"),
    ("donchian_swing", "DonchianSwingStrategy"),
    ("bull_flag_breakout", "BullFlagBreakoutStrategy"),
    ("vcp_breakout", "VcpBreakoutStrategy"),
    ("kojiro", "KojiroStrategy"),
)

#: cycle287 이 만들고 cycle290 이 등재하는 두 키.
_NEW_PARAM_KEYS: tuple[str, ...] = (
    "order_exchange_clock_mode",
    "after_market_exit_division",
)


@lru_cache(maxsize=64)
def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# S1 — `scheduler.py` 라인 상한 (cycle257 영구 상한 복창)
# ===========================================================================
#: cycle257 이 세운 영구 상한(정본). 종전 표기 `4,000` 은 느슨한 쪽이라 폐기됐다.
_SCHEDULER_LINE_CAP = 3900


def test_g290_1b_scheduler_line_count_is_under_the_permanent_cap() -> None:
    """S1 — `scheduler.py` 라인 상한(cycle257 정본 3,900) 유지."""
    lines = len(_src("src/engine/scheduler.py").splitlines())
    assert lines < _SCHEDULER_LINE_CAP, f"라인 상한 {_SCHEDULER_LINE_CAP} 초과: {lines}"


# ===========================================================================
# S2 — 전략 7파일의 진입·청산·사이징·준비 메서드 세그먼트 sha (28핀)
#
# 🔴 이 핀들은 cycle290 에서 **하나도 깨지지 않아야 한다.** 깨지면 핀을 옮기지 말고
#    코드를 되돌려라 — `DEFAULT_PARAMS`(클래스 속성) 밖을 건드린 것이다.
# ===========================================================================
_FROZEN_METHODS: tuple[str, ...] = (
    "check_buy_signal", "check_exit_signal", "calc_buy_quantity", "prepare",
)

_SEGMENT_SHA: dict[tuple[str, str], str] = {
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    ("momentum", "check_buy_signal"):
        "2e90bcb3605dba3a16917ce99e42b15aa33604ec369b30066a5a859f1bde33dc",
    ("momentum", "check_exit_signal"):
        "33c06df9546f40e91b1857300f0da8480eb671c1c8778454691248c9e90b9ef1",
    ("momentum", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
    # 🔁 cycle364(2026-09-26) 재핀 — `prepare(as_of=)` 시그니처 확장(사용자 승인 D3).
    ("momentum", "prepare"):
        "eff5452d07567436585a498aedeb45deeac9c4fc913a9782b00242beef288085",
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    ("volatility_breakout", "check_buy_signal"):
        "5424dc5b23fb3b382174098b4a964c7a76a6ffb7ab3ed9597e0774b03e31c2da",
    ("volatility_breakout", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("volatility_breakout", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    # 🔁 cycle364 재핀 — `prepare(as_of=)` 시그니처 확장.
    ("volatility_breakout", "prepare"):
        "0a378b804169ed99843eca465f404fbe136184b436cd627aa1af2c2268e98ab7",
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    ("long_tail_volatility", "check_buy_signal"):
        "be76217bf4634a401bb73564d41bcb25b6bed74e7f6ec95b1775941f9676293b",
    ("long_tail_volatility", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("long_tail_volatility", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
    # 🔁 cycle364 재핀 — `prepare(as_of=)` 시그니처 확장.
    ("long_tail_volatility", "prepare"):
        "8837076acd413ed97127a7a74ebbb4e62b7000fa9495727ad268bfedcd13b73a",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) 신호 필터 삽입(추격 상한 블록 뒤 ·
    # `_breakout_high` 스탬프 앞, 사용자 결정 09-27).
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    # 🔁 cycle405 재핀 — 깡토식 신호 거름 2종(`_kk_lot_zero_blocks`·`_kk_daily_cap_blocks`)
    # 삽입. 직전 값(cycle399) = `124c5eb1257fdd14b58738e738cc534bd7a4ec2d25d24d2111704c88368278f6`.
    ("donchian_swing", "check_buy_signal"):
        "2b9659703762fdf1e5b49eb132b008829399fd1f651bb84bcc76ca8d08ca01ef",
    # 🔁 cycle405 재핀 — 깡토식 청산 개조(§2) — R 손절·3R 본전 승격·무장 후 채널만 본다.
    # 직전 값(cycle399) = `171c7654632500358cffb4c542e0ee5d8f4218c1101faf72a668f24ffd8606bd`.
    ("donchian_swing", "check_exit_signal"):
        "2bb55db9d8c6917b666d51e6a31bf2b2dfeb61257e33d1dee9fae014f5352ea7",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) `_market_unit_sizing` 진입 훅.
    # 🔁 cycle405 재핀 — 깡토식 R 기반 설계 랏(§5) — 1주 폴백·비중 낙하 제거.
    # 직전 값(cycle382) = `cc3e622d232ff38adff20d03f3efa89c99b93337b5b4dd08bd26e68c059a9ef5`.
    ("donchian_swing", "calc_buy_quantity"):
        "091bfb43b6a01ea9604d451332a4c770cf9200db22a20a1985507f122c9e36d5",
    # 🔁 cycle364 재핀 — `prepare(as_of=)` + PV-1(보유·익일청산 종목 보존).
    # 🔁 cycle364 round 2 재핀 — keep(자기 보유∪자기 익일청산) / skip(자기 ∪ 전 전략
    # 보호 종목) 두 집합으로 분리(R1) — 남의 보유 엔트리를 보존·재구성 어느 쪽도 하지
    # 않는다.
    # 🔁 cycle382 재핀 — `_refresh_market_unit` 호출 삽입(`_resolve_prepare_as_of` 직후).
    ("donchian_swing", "prepare"):
        "a2c018d3fa4e416bb7c92325d325d9fad7c88f86a62328500e410c3c455d930a",
    ("bull_flag_breakout", "check_buy_signal"):
        "b39b26fb398ca352edaf91816b4aed04cd50f47aef29d13a8b82af0f6580ed7d",
    ("bull_flag_breakout", "check_exit_signal"):
        "850f503be242249b164d44cbb6100f2f764cfa23fa8e95a669b422c22d95daed",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) `_market_unit_sizing` 진입 훅.
    ("bull_flag_breakout", "calc_buy_quantity"):
        "772cf9ffda83e9abfaeb44f4f8e4a67eb8543fab58a961d3919d4b41bdd0f1ad",
    # 🔁 cycle364 재핀 — `prepare(as_of=)` 시그니처 확장.
    # 🔁 cycle364 round 2 재핀 — PV-1 을 BFB 로 확대(keep/skip 분리, R1) — 미리보기가
    # 보유 종목의 `_candidates`(청산 입력 `atr14`·구조 레벨)를 더 이상 지우지 않는다.
    # 🔁 cycle382 재핀 — `_refresh_market_unit` 호출 삽입(`_resolve_prepare_as_of` 직후).
    ("bull_flag_breakout", "prepare"):
        "6427201942a700b6409918f62c1a41d3e5f463c4036b7a70e2202a96dca35db3",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) 신호 필터는 `_evaluate_vol_gate` 안(추격
    # 상한 거부 블록 뒤 · `latch_age_sec = 0` 앞)이라 `check_buy_signal` 세그먼트
    # 자체는 무변경이다.
    ("vcp_breakout", "check_buy_signal"):
        # cycle349 재핀 — VCP 관측 ①③(돌파선 거리 줄 · 틱 관측 훅 · watch). 매매 경로 diff 0
        # = 확장 전 HEAD 산출 골든 G1(prepare)·G2(check_buy_signal) 완전 일치로 확인.
        "e50969e3ffcdd8f7b5f8ce0bd61e67852436e4ead7130c54006a2f22c11adb6f",
    ("vcp_breakout", "check_exit_signal"):
        "abfb25485f91e18aa4a1297002575990ef58aa4b4f3db791efbb29bfe4cdc877",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) `_market_unit_sizing` 진입 훅.
    ("vcp_breakout", "calc_buy_quantity"):
        "43d2e682051cd9a4653b972aab6c3706dc2144b082ae73e34c8c38f5cb3f8010",
    ("vcp_breakout", "prepare"):
        # cycle349 재핀 — VCP 관측 ①③(돌파선 거리 줄 · 틱 관측 훅 · watch). 매매 경로 diff 0
        # = 확장 전 HEAD 산출 골든 G1(prepare)·G2(check_buy_signal) 완전 일치로 확인.
        # 🔁 cycle364 재핀 — `prepare(as_of=)` + P3(미리보기에서 `_observe_breakout_distance` 생략).
        # 🔁 cycle364 round 2 재핀 — PV-1 을 VCP 로 확대(keep/skip 분리, R1) — 미리보기가
        # 보유 종목의 `_candidates`(청산 입력 `atr14`·`ema50`·`base_low`)를 더 이상
        # 지우지 않는다(round-1 적대 검토 trading-safety medium 반영).
        # 🔁 cycle382 재핀 — `_refresh_market_unit` 호출 삽입(`_resolve_prepare_as_of` 직후).
        "29280134b44040ae4187fb7eb95d0308885ff904a61f60e1ca4b6a061f1d416e",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) 신호 필터(`observe_gap(...,"pass",...)`
    # 뒤 · `_bought_today.add` 앞).
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    ("kojiro", "check_buy_signal"):
        "c3dd4541133b3788d2ff46787ce5545d15cc33f4e2e51e29484b0839724f2216",
    ("kojiro", "check_exit_signal"):
        "84220e4133cf76f9ea1c74335919d22a245a899b0833057f20f24a27f38913e6",
    # 🔁 cycle382 재핀 — 시장 유닛(단계형) `_market_unit_sizing` 진입 훅.
    ("kojiro", "calc_buy_quantity"):
        "c144f15de94a9f7069ac6cf650066dc12472cffdc3280a63e840b31aa544f84d",
    ("kojiro", "prepare"):
        # cycle348 재핀 — `[kojiro_macd_observe]` role=stage6_gc 확장(step6 직후
        # 자기 try 수집 + observe_macd 뒤 별도 try emit). 매매 경로 diff 0.
        # 🔁 cycle364 재핀 — `prepare(as_of=)` + PV-1(보유 종목 보존, stage3 미스탬프) +
        # P3(미리보기에서 observe_band/observe_macd/observe_macd_stage6 생략).
        # 🔁 cycle364 round 2 재핀 — keep/skip 분리(R1) — 남의 보유가 `held_only` 로
        # 새지 않는다(round-1 적대 검토 low 반영).
        # 🔁 cycle382 재핀 — `_refresh_market_unit` 호출 삽입(`_resolve_prepare_as_of` 직후).
        "d07d25c094d47bb81e2b14194bf3ed7818e9b63397794e01bfa11af0fda0f7a0",
}


def _class_node(module: str, cls_name: str) -> tuple[str, ast.ClassDef]:
    rel = f"src/engine/strategies/{module}.py"
    src = _src(rel)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            return src, node
    raise AssertionError(f"{rel} 에 클래스 {cls_name} 부재")


@pytest.mark.parametrize("module, cls_name", _STRATEGY_META)
@pytest.mark.parametrize("method", _FROZEN_METHODS)
def test_g290_2_strategy_entry_exit_segments_are_byte_identical(
    module: str, cls_name: str, method: str
) -> None:
    """S2 — 진입·청산·사이징·준비 세그먼트 **28개** 전부 무변경.

    `DEFAULT_PARAMS` 는 클래스 속성이라 이 세그먼트 안에 없다 ⇒ 두 키 등재는 이
    핀들을 건드리지 않는다. **붉어지면 핀을 옮기지 말고 코드를 되돌려라.**
    """
    src, cls = _class_node(module, cls_name)
    fns = [
        s for s in cls.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == method
    ]
    assert fns, f"{module}.{cls_name}.{method} 부재"
    seg = ast.get_source_segment(src, fns[0]) or ""
    got = _sha(seg)
    assert got == _SEGMENT_SHA[(module, method)], (
        f"{module}.{method} 세그먼트가 바뀌었다 — cycle290 은 `DEFAULT_PARAMS` 만 "
        f"건드린다. 🔴 핀을 갱신하지 말고 코드를 되돌려라. 현재 sha={got}"
    )


# ===========================================================================
# S4 — 두 키는 `PARAM_RANGES`/`INT_PARAMS` 소스 리터럴로도 등장하지 않는다
#
# cycle287 `test_s5` 는 **런타임 dict** 를 검사한다. 여기서는 소스 텍스트로 이중
# 봉인한다(cycle242 G-242-1 · cycle245 G-245-1 관례). AI 자문이 청산 수단을 끄는
# 스위치를 뒤집는 경로는 열려서는 안 된다.
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_4_new_keys_absent_from_recommendation_engine_source(key: str) -> None:
    """S4 — `recommendation_engine.py` 소스에 두 키 문자열이 0건.

    `PARAM_RANGES`/`INT_PARAMS`/`_CONSERVATIVE_KEYS` 어디에도 넣지 않는다 —
    `_validate_recommendations`·`auto_apply`·수동 적용 4중 차단의 상류가 이것이다.
    """
    src = _src("src/engine/recommendation_engine.py")
    assert key not in src, (
        f"`{key}` 가 recommendation_engine.py 에 들어왔다 — AI 자문이 킬스위치를 "
        f"뒤집을 수 있게 된다"
    )


@pytest.mark.parametrize("dict_name", ["PARAM_RANGES", "INT_PARAMS"])
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_4b_new_keys_absent_from_param_ranges_literals(
    dict_name: str, key: str
) -> None:
    """S4 — 소스 AST 로도 두 dict 리터럴의 키 집합에 없다(문자열 grep 보완)."""
    src = _src("src/engine/recommendation_engine.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # `PARAM_RANGES: dict[...] = {...}` 는 `AnnAssign`, `INT_PARAMS = {...}` 는
        # **set 리터럴**이다 — 둘 다 잡아야 가드가 공허해지지 않는다.
        if isinstance(node, ast.AnnAssign):
            names = [getattr(node.target, "id", None)]
        elif isinstance(node, ast.Assign):
            names = [getattr(t, "id", None) for t in node.targets]
        else:
            continue
        if dict_name not in names:
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            literals = {
                k.value for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
        elif isinstance(value, ast.Set):
            literals = {
                e.value for e in value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
        else:
            pytest.fail(
                f"{dict_name} 의 값이 dict/set 리터럴이 아니다 ({type(value).__name__}) "
                f"— 이 가드의 전제가 깨졌다"
            )
        assert literals, f"{dict_name} 리터럴이 비었다 — 가드가 공허해졌다"
        assert key not in literals, f"`{key}` 가 {dict_name} 리터럴에 있다"
        return
    pytest.fail(f"{dict_name} 대입문을 찾지 못했다 — 가드가 공허해졌다")


# ===========================================================================
# S5 — 문서 동기화 의무 (cycle272 `test_g272_28f` 패턴)
# ===========================================================================
_DOC_TARGETS: tuple[str, ...] = (
    "_workspace/00_leader_trading_rules.md",
    "src/engine/CLAUDE.md",
    "src/engine/strategies/CLAUDE.md",
)


@pytest.mark.parametrize("rel", _DOC_TARGETS)
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_5_docs_declare_the_two_keys(rel: str, key: str) -> None:
    """S5 (RED) — 신규 `DEFAULT_PARAMS` 키는 문서 3곳에 기재된다.

    루트 CLAUDE.md 금기: "`DEFAULT_PARAMS` 변경 시
    `_workspace/00_leader_trading_rules.md` 동기화". cycle272 가 세운 선례는
    `src/engine/strategies/CLAUDE.md` 까지 요구한다. `src/engine/CLAUDE.md` 는
    「장중 킬스위치 없음」 절이 **거짓이 되는** 곳이라 함께 잠근다.
    """
    assert key in _src(rel), f"{rel} 에 `{key}` 기재 없음"


def test_g290_5b_engine_doc_no_longer_claims_the_killswitch_is_absent() -> None:
    """S5 (RED) — `src/engine/CLAUDE.md` 가 두 키의 **미등재**를 말하지 않는다.

    cycle287 이 정직하게 적어 둔 「장중 킬스위치 없음」 은 cycle290 으로 **거짓**이
    됐다. 거짓 서술 자체는 그때도 지금도 금지다.

    🔄 **2026-09-17 반전** — 종전 계약은 "지우지 말고 「cycle290 이 등재로 열었다 +
    그 전까지 왜 없었는지」 로 전환하라" 였고, 그래서 **「미등재」 가 나오는 줄마다
    `cycle290` 동반**을 요구했다. 그 동반 조건이 곧 신·구 병존(덧칠) 통로다 —
    정본은 지금 동작하는 규칙만 적고 "그 전까지 왜 없었는지" 는
    `docs/history/src-engine-CLAUDE.history.md` 가 받는다(루트 `CLAUDE.md`
    「문서 규약」 절, 2026-09-17 사용자 결정). 그래서 단언을 **「미등재」 부재**로
    뒤집었다.

    공허 가드 방지 — 종전 우려("`cycle290` 전수 검사는 이 사이클 자신의 다른 언급
    때문에 항상 참" · 검증 발견 LOW-5)는 부재 단언에서 사라진다. 대신 파일이 실제로
    읽혔는지를 `_src` 반환 길이로, 어휘가 실재 문자열인지를 history 쪽 자매 케이스로
    확인한다.
    """
    doc = _src("src/engine/CLAUDE.md")
    assert len(doc) > 500, "🔵 양성 대조군 실패 — src/engine/CLAUDE.md 이 비었다"
    assert "장중 킬스위치 없음" not in doc, (
        "cycle287 의 「장중 킬스위치 없음」 표제가 그대로 남아 있다 — cycle290 이후 "
        "거짓이다. 그 서술은 `docs/history/src-engine-CLAUDE.history.md` 로 보내라"
    )
    stale = [
        (i, line.strip()[:120])
        for i, line in enumerate(doc.splitlines(), 1)
        if "미등재" in line
    ]
    assert not stale, (
        "`src/engine/CLAUDE.md` 이 두 킬스위치 키의 「미등재」를 말한다 — cycle290 "
        "등재 이후 거짓이고, 등재 전 상태의 서술은 정본이 아니라 "
        "`docs/history/src-engine-CLAUDE.history.md` 의 몫이다:\n  "
        + "\n  ".join(f"L{i} {s}" for i, s in stale)
    )


def test_g290_5c_history_keeps_the_pre_registration_story() -> None:
    """🔵 양성 대조군 — 「미등재」 서술이 **사라진 것이 아니라 옮겨졌음**을 증명한다.

    부재 단언만 두면 이력이 통째로 유실돼도 초록이다. 같은 어휘로 `docs/history/**`
    를 긁어 (a) 검사기가 실제로 그 문자열을 잡고 (b) 등재 전 경위가 보존됐음을
    함께 보인다.
    """
    hist = _ROOT / "docs" / "history"
    assert hist.is_dir(), "docs/history/ 가 없다 — 이관 대상지가 사라졌다"
    found = sorted(
        p.name for p in hist.glob("*.history.md")
        if "미등재" in p.read_text(encoding="utf-8")
    )
    assert found, (
        "🔵 양성 대조군 실패 — 「미등재」 서술이 `docs/history/*.history.md` 어디에도 "
        "없다. 정본에서 걷어낸 등재 전 경위가 이관되지 않았거나(이력 소실) 이 가드의 "
        "어휘가 낡았다. 어느 쪽이든 위의 부재 단언은 공허하다"
    )


# ===========================================================================
# S6 — cycle287 이 예고한 계약 반전 (그 파일을 갱신하지 않으면 붉어진다)
# ===========================================================================
_CYCLE287_SCOPE = "tests/unit/ast/test_cycle287_ast_scope.py"


@pytest.mark.parametrize("rel", [f"src/engine/strategies/{m}.py" for m, _ in _STRATEGY_META])
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_6_two_keys_present_in_every_strategy_source(rel: str, key: str) -> None:
    """S6 (RED) — 두 키가 전략 **7파일 소스 전부**에 있다.

    cycle287 `test_s5b` 의 정반대다(그쪽은 "어느 전략 파일에도 없다"를 단언했다).
    라우팅·애프터 청산은 `strategy_id` 로 params 를 조회하는 **전 전략 공통 경로**라
    일부만 등재하면 나머지 전략은 여전히 `unknown_key` 422 = 그 전략 포지션의 장중
    롤백 수단이 없다.
    """
    assert key in _src(rel), f"{rel} 에 `{key}` 부재 — 그 전략은 장중에 끌 수 없다"


def test_g290_6b_cycle287_scope_guard_was_updated() -> None:
    """S6 (RED) — cycle287 범위 가드의 낡은 계약 문구가 갱신됐다.

    🔴 `test_s7_new_keys_cannot_be_put_at_runtime` 은 **초록인 채로 거짓이 된다** —
    합성 dict `{"exchange": ..., "tradable_boards": ...}` 를 `current_params` 로 넘기고
    `param_validation` 의 판정이 `key not in current_params **or** spec is None` 이라,
    등재와 무관하게 영원히 `unknown_key` 다. 즉 그 가드는 등재 후에도 실패하지 않으면서
    "장중 킬스위치는 존재하지 않는다" 는 거짓 주장을 계속 지킨다.

    Green 은 그 테스트를 **실 `DEFAULT_PARAMS` 기반 "PUT 이 통한다" 가드로 재작성**하고
    (단언을 지우거나 skip 하지 말고 **강화 방향으로 반전**), `test_s5b` 도 존재 단언으로
    뒤집고, 파일 배너의 그 문장을 정직화해야 한다. 이 테스트가 그 의무의 forcing
    function 이다.
    """
    src = _src(_CYCLE287_SCOPE)
    assert "장중 킬스위치는 존재하지 않는다" not in src, (
        "cycle287 배너/S7 docstring 의 「장중 킬스위치는 존재하지 않는다」 가 남아 있다 "
        "— cycle290 이 열었으므로 거짓이다"
    )
    assert '(key, "unknown_key") in codes' not in src, (
        "`test_s7` 이 여전히 `unknown_key` 를 단언한다 — 그 단언은 합성 dict 때문에 "
        "등재 후에도 **초록인 채로 거짓**이다. 실 `DEFAULT_PARAMS` 를 current_params 로 "
        "넘기고 200 + accepted 를 단언하는 방향으로 재작성하라"
    )
