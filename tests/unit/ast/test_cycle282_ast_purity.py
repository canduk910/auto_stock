"""cycle282 Red — 구조 가드 (H1~H8): leaf 순수성 · 무접촉 · 봉인.

정본 = `_workspace/red/cycle282_market_state_spec.md` §6(M8·M12·M13·M14) · §7.1 H.

## 이 사이클의 제1 계약

**매매 행위를 한 글자도 바꾸지 않는다.** 읽기 전용 조회 기능이고, 어떤 전략도 이 함수를
아직 호출하지 않는다. 그 주장을 사람의 선언이 아니라 **sha** 로 증명한다(H3).

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI) / 3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment` 의 sha256 으로만 잰다.

## 왜 `git grep` / `git ls-files` 로 스캔하지 않는가

추적 파일만 보므로 Green 이 새로 만든 **미추적** 파일을 로컬에서 못 보고 CI(커밋 후)에서만
잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob("*.py")` + AST 로 한다.
`bare git diff HEAD` 도 영구 가드로 두지 않는다(cycle240 A11b · cycle252 G-252-5b).

## ⚠️ 사이클 한정 — **커밋 후 삭제/갱신 의무**

`_BASE_SHA`(8영역 5파일 + `src/api/order.py` + `src/realtime/**` + `src/auth/**` +
`scheduler.py` + `strategy_base.py` + 전략 7파일)와 `_SEGMENT_SHA`
(`is_market_open` · `next_trading_day` 본체)는 **브랜치 base `34f662f` 의 blob** 을 고정한
것이라 cycle282 의 무접촉 증거로만 유효하다. 그 파일들을 **정당하게** 바꾸는 다음 사이클이
이 dict 를 갱신하거나 이 테스트를 삭제한다(고아 가드 방지).

## Red 상태 (작성 시점)

`src/engine/market_state.py` · `src/routes/market_state.py` · `condition.is_trading_day`
가 없다 → H1·H2·H4·H6·H7·H8 과 H5 의 신규 함수 절반이 FAIL.
H3 과 H5 의 기존 두 함수 핀은 **작성 시점에 초록**이며, Green 이 무접촉 선을 넘는 순간 붉어진다.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_LEAF_REL = "src/engine/market_state.py"
_ROUTE_REL = "src/routes/market_state.py"
_CONDITION_REL = "src/api/condition.py"


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _read_or_fail(rel: str) -> str:
    path = _ROOT / rel
    if not path.exists():
        pytest.fail(f"{rel} 이 없다 (Red) — Green 이 만든다")
    return path.read_text(encoding="utf-8")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_read_or_fail(rel))


def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _docstring_nodes(tree: ast.AST) -> set:
    """모듈/클래스/함수의 docstring Constant 노드 id 집합(검사에서 제외)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    out.add(id(body[0].value))
    return out


def _string_constants(tree: ast.AST) -> list:
    """docstring 을 뺀 문자열 리터럴 전부 (주석은 AST 에 없다)."""
    skip = _docstring_nodes(tree)
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def _imported_roots(tree: ast.AST) -> set:
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 상대 import
                roots.add(".")
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _func_segment_sha(rel: str, name: str) -> str:
    src = _read_or_fail(rel)
    tree = ast.parse(src)
    hits = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(hits) == 1, f"{rel}: {name} 정의 {len(hits)}개 (1개여야 한다)"
    segment = ast.get_source_segment(src, hits[0])
    assert segment, f"{rel}: {name} 소스 세그먼트를 얻지 못했다"
    return hashlib.sha256(segment.encode("utf-8")).hexdigest()


# ===========================================================================
# H1 · H2 — leaf 순수성 (M13)
# ===========================================================================
def test_h1_leaf_imports_no_src_module():
    """H1 (M13) — leaf 는 `src.*` 를 import 하지 않는다(의존 0 = 어디서나 부를 수 있다)."""
    tree = _tree(_LEAF_REL)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.split(".")[0] == "src"]
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module and node.module.split(".")[0] == "src"):
                bad.append(node.module or f"(relative level={node.level})")
    assert not bad, (
        f"{_LEAF_REL}: src.* import {bad} — 순수 leaf 계약 위반. "
        "휴장일 결합 같은 I/O 는 **라우트**에서 한다"
    )


def test_h2_leaf_has_no_io_await_or_logging():
    """H2 (M13) — I/O·await·로깅 0. 표를 읽는 일이 외부 상태에 물리면 안 된다."""
    src = _read_or_fail(_LEAF_REL)
    tree = ast.parse(src)

    banned_roots = {
        "httpx", "requests", "urllib", "urllib3", "aiohttp", "socket",
        "asyncio", "logging", "subprocess", "sqlite3", "os", "sys",
        "pathlib", "io", "time", "random", "asyncpg", "supabase",
    }
    hit = _imported_roots(tree) & banned_roots
    assert not hit, f"{_LEAF_REL}: 금지 import {sorted(hit)} — leaf 는 I/O·로깅을 하지 않는다"

    awaits = [n for n in ast.walk(tree) if isinstance(n, ast.Await)]
    assert not awaits, f"{_LEAF_REL}: await {len(awaits)}건 — 순수 동기 함수여야 한다"
    async_defs = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    assert not async_defs, f"{_LEAF_REL}: async 함수 {async_defs}"

    opens = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open"
    ]
    assert not opens, f"{_LEAF_REL}: open() 호출 {len(opens)}건"


def test_h2b_leaf_forces_kst_and_never_reads_local_clock_naively():
    """H2b (M5 구조면) — `datetime.now()` 를 인자 없이 부르지 않는다(m9).

    `datetime.now()` 는 컨테이너 로컬 TZ 를 따른다. TZ 가 바뀌는 날 조용히 틀리므로
    이 리포는 **항상** tz 를 명시한다(루트 CLAUDE.md KST 강제 규약).
    """
    tree = _tree(_LEAF_REL)
    naked = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name in ("now", "utcnow", "today") and not node.args and not node.keywords:
            naked.append(name)
        if name == "utcnow":
            naked.append("utcnow")
    assert not naked, (
        f"{_LEAF_REL}: 무인자 {sorted(set(naked))}() 호출 — KST 를 명시하지 않으면 "
        "컨테이너 TZ 가 바뀌는 날 표 판정이 통째로 틀린다"
    )


def test_h7_leaf_import_has_no_side_effects():
    """H7 (M13) — 모듈 로드가 `src.*` 를 끌어오지 않고 파일/네트워크도 건드리지 않는다.

    같은 프로세스에서 재면 앞선 테스트의 import 가 섞이므로 **별도 프로세스**에서 잰다.
    """
    if not (_ROOT / _LEAF_REL).exists():
        pytest.fail(f"{_LEAF_REL} 이 없다 (Red) — Green 이 만든다")

    script = (
        "import builtins, json, socket, sys\n"
        "_opened = []\n"
        "_real_open = builtins.open\n"
        "def _guard(*a, **kw):\n"
        "    if a:\n"
        "        _opened.append(str(a[0]))\n"
        "    return _real_open(*a, **kw)\n"
        "builtins.open = _guard\n"
        "def _no_socket(*a, **kw):\n"
        "    raise RuntimeError('import 시점 네트워크 접근')\n"
        "socket.socket = _no_socket\n"
        "before = set(sys.modules)\n"
        "import src.engine.market_state as m\n"
        "after = set(sys.modules)\n"
        "print(json.dumps({'delta': sorted(x for x in after - before if x.startswith('src')),\n"
        "                  'opened': _opened, 'rows': len(getattr(m, 'MARKET_TABLE', ()))}))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, cwd=str(_ROOT), timeout=45,
    )
    assert proc.returncode == 0, (
        f"leaf import 실패 — rc={proc.returncode}\nstderr={proc.stderr[-800:]}"
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert set(payload["delta"]) <= {"src", "src.engine", "src.engine.market_state"}, (
        f"import 부작용 — 딸려 온 src 모듈 {payload['delta']}"
    )
    assert payload["opened"] == [], f"import 시점 파일 열기 {payload['opened']}"
    assert payload["rows"] == 13, f"MARKET_TABLE {payload['rows']}행"


# ===========================================================================
# H4 — `decided_by="code"` 봉인 (M12)
# ===========================================================================
def test_h4_leaf_has_no_code_literal():
    """H4 (M12) — leaf 에 `"code"` 리터럴 0.

    `decided_by="code"`(MARKET_CLS_CODE 실측 판정)는 09-14 이후 데이터가 쌓인 뒤의
    **별도 사이클**이다. 지금 만들면 검증할 수 없는 분기가 생긴다.
    """
    hits = [s for s in _string_constants(_tree(_LEAF_REL)) if s == "code"]
    assert not hits, (
        f'{_LEAF_REL}: "code" 리터럴 {len(hits)}건 — 이 사이클은 시각으로만 판정한다'
    )


def test_h4b_route_never_assigns_decided_by_code():
    """H4b (M12) — 라우트도 `decided_by` 에 `"code"` 를 넣지 않는다.

    라우트는 카탈로그 JSON 키로 `"code"` 를 **정당하게** 쓰므로(§3.1 `order_divisions[].code`)
    리터럴 전면 금지는 Green 을 막는다. 봉인 대상은 `decided_by` 자리 하나다.
    """
    tree = _tree(_ROUTE_REL)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant) and k.value == "decided_by"
                    and isinstance(v, ast.Constant) and v.value == "code"
                ):
                    bad.append("dict")
        if isinstance(node, ast.keyword) and node.arg == "decided_by":
            if isinstance(node.value, ast.Constant) and node.value.value == "code":
                bad.append("kwarg")
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if node.value.value == "code":
                for t in node.targets:
                    if getattr(t, "attr", None) == "decided_by" or getattr(t, "id", "") == "decided_by":
                        bad.append("assign")
    assert not bad, f"{_ROUTE_REL}: decided_by 에 'code' 주입 {bad} — M12 봉인 위반"


# ===========================================================================
# H6 · H8 — 라우트 구조
# ===========================================================================
def test_h6_route_reads_the_clock_exactly_once():
    """H6 (m11) — 라우트의 `datetime.now(` 호출은 **정확히 1회**.

    시장마다 다시 읽으면 자정·경계에서 두 커서가 다른 순간을 본다(G5 의 구조면).
    """
    tree = _tree(_ROUTE_REL)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) in ("now", "utcnow")
    ]
    assert len(calls) == 1, (
        f"{_ROUTE_REL}: 현재시각 호출 {len(calls)}회 — 정확히 1회여야 한다(하나의 as_of)"
    )
    only = calls[0]
    assert getattr(only.func, "attr", None) == "now", "utcnow 금지 — KST aware 를 만든다"
    assert only.args or only.keywords, (
        "datetime.now() 가 무인자다 — 컨테이너 TZ 를 따르게 된다(KST 강제 위반)"
    )


def test_h8_route_has_no_clock_time_literals():
    """H8 — 라우트에 시각 리터럴 0. 시각은 **전부 leaf 표에서** 온다."""
    pattern = re.compile(r"\b\d{1,2}:\d{2}\b")
    hits = [s for s in _string_constants(_tree(_ROUTE_REL)) if pattern.search(s)]
    assert not hits, (
        f"{_ROUTE_REL}: 시각 리터럴 {hits} — 표가 바뀌면 라우트가 조용히 거짓말한다"
    )


# ===========================================================================
# H5 — `condition.py` 기존 함수 무변경 + 신규 함수 (M14)
# ===========================================================================
#: base `34f662f` 의 `ast.get_source_segment` sha256. ⚠️ 사이클 한정 핀.
_SEGMENT_SHA = {
    "is_market_open": "09e99a2c72c8d83f551b36708fe9e055bee39bd312aa35904a3f07772e175691",
    "next_trading_day": "5de20abe09f1528ef5436dc9cb678251d7289216c518abfbd15816ecf2c28012",
}


@pytest.mark.parametrize("name", sorted(_SEGMENT_SHA))
def test_h5_existing_holiday_functions_are_byte_identical(name):
    """H5 (M14) — `is_market_open` / `next_trading_day` 는 한 글자도 안 바뀐다.

    그 둘의 fail-open **True** 는 scheduler·strategy_funnel 의 **매매 경로** 계약이다.
    화면의 '모른다' 를 위해 그 계약을 고치면 이 사이클의 무접촉 범위가 매매 경로로 넓어진다.
    그래서 3상태 `is_trading_day` 를 **따로** 만든다(명세 추가-7).
    """
    got = _func_segment_sha(_CONDITION_REL, name)
    assert got == _SEGMENT_SHA[name], (
        f"{_CONDITION_REL}::{name} 본체가 변경됐다 — {got} != {_SEGMENT_SHA[name]}. "
        "cycle282 는 이 두 함수를 무접촉으로 둔다"
    )


def test_h5b_new_is_trading_day_reuses_same_url_and_tr_id():
    """H5b — 신규 `is_trading_day` 는 같은 `HOLIDAY_URL`·`CTCA0903R` 을 쓰고 3상태를 반환한다."""
    src = _read_or_fail(_CONDITION_REL)
    tree = ast.parse(src)
    hits = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "is_trading_day"
    ]
    assert len(hits) == 1, (
        "src/api/condition.py::is_trading_day 미구현 (Red) — "
        "명세 추가-7: 조회 실패를 None 으로 돌려주는 3상태 래퍼"
    )
    fn = hits[0]
    assert isinstance(fn, ast.AsyncFunctionDef), "is_trading_day 는 async 여야 한다"
    segment = ast.get_source_segment(src, fn) or ""
    assert "HOLIDAY_URL" in segment, "기존 HOLIDAY_URL 상수를 재사용해야 한다(URL 재기입 금지)"
    assert "CTCA0903R" in segment, "TR_ID 는 기존과 같은 CTCA0903R 이다"
    assert "kis_get_quote" in segment, "호출은 시세 풀(`kis_get_quote`) 경유 계약이다"
    returns = [
        n.value for n in ast.walk(fn)
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
    ]
    literal_returns = {r.value for r in returns}
    assert None in literal_returns or any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None
        for n in ast.walk(fn)
    ), (
        "`return None` 경로가 없다 — 조회 실패를 True/False 로 단정하면 M10 위반"
    )
    assert True not in literal_returns or False in literal_returns, (
        "True 만 돌려주는 fail-open 형태다 — `is_market_open` 의 결함을 그대로 복제한 것이다"
    )


# ===========================================================================
# H3 — 무접촉 sha 핀 (M8) · ⚠️ 사이클 한정
# ===========================================================================
#: base `34f662f` blob 의 파일 내용 sha256.
# 🔁 2026-09-12 (cycle286) 재핀 — `order_engine.py`(C4-a, 8영역 사용자 승인)·
#    `long_tail_volatility.py`(C2-a, 전략 7파일 목록 대상) 2건. 값만 현재
#    워킹트리로 재산출했다.
_BASE_SHA = {
    # 8영역 — 엔진 5파일
    "src/engine/risk.py":
        "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
    "src/engine/order_engine.py":
        "fe9886c8e2e3cccd03370f3470cc73449bf3a7c615c177c8ea87bd399949a8b2",
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
    # 8영역 — 주문 API
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # 8영역 — realtime 전부 (⚠️ wt280 시세 전환 사이클과 겹치는 영역이라 특히 중요)
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
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
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # ⚠️ cycle292(2026-09-14) 재핀 — `_subscribe_market_operation_tickers` 176줄을
    # 신규 leaf `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임
    # wrapper · 3,897→3,726L, 사용자 승인). 여섯 자매 핀(cycle274/276/278/282/290/291)
    # 을 **한 값으로 동시에** 옮겼다 — 한 곳만 넣으면 나머지가 "코드를 되돌려라" 로
    # 붉어져 승인된 변경을 되돌리도록 오도한다. 직전 값 =
    # `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`.
    # 8영역은 아니지만 이 사이클이 무접촉을 약속한 파일
    "src/engine/scheduler.py":
        "4b9c8ac94706ae622d3404fa10bfa805a69a4b36485787c388dff3aa6e76763d",
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 전략 7파일 — 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀. `DEFAULT_PARAMS`
    # 말미 2키 추가뿐, 그 외 diff 0.
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
}

#: 디렉터리 통째로 잠그는 영역 — 새 파일이 조용히 들어오는 것도 접촉이다.
_PINNED_DIRS = ("src/realtime", "src/auth", "src/engine/strategies")


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_h3_eight_areas_untouched(rel):
    """H3 (M8) — 8영역·scheduler·strategy_base·전략 7파일 **diff 0**.

    이 사이클은 읽기 전용 조회 기능이다. 이 중 한 파일이라도 바뀌면 '매매 행위 변경 0' 이
    더 이상 참이 아니고, 승인 절차(8영역 승인 + domain-consult 선행)가 필요하다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 사라졌다 — 무접촉 계약 위반"
    got = _content_sha(rel)
    assert got == _BASE_SHA[rel], (
        f"{rel} 이 base(main 병합 시점 = cycle283 배포분 fc82697) 에서 바뀌었다 — {got} != {_BASE_SHA[rel]}. "
        "cycle282 는 8영역 무접촉이다(M8). 의도된 변경이라면 별도 승인 대상이다"
    )


@pytest.mark.parametrize("rel_dir", _PINNED_DIRS)
def test_h3b_no_new_files_slip_into_pinned_dirs(rel_dir):
    """H3b (M8) — 잠근 디렉터리에 **새 .py 가 생기는 것**도 접촉이다.

    `git ls-files` 를 쓰지 않는다 — 미추적 신규 파일을 로컬에서 못 보고 CI 에서만 잡는다.
    """
    found = {
        str(p.relative_to(_ROOT)).replace(os.sep, "/")
        for p in (_ROOT / rel_dir).rglob("*.py")
    }
    pinned = {rel for rel in _BASE_SHA if rel.startswith(rel_dir + "/")}
    assert found == pinned, (
        f"{rel_dir}: 신규 {sorted(found - pinned)} / 삭제 {sorted(pinned - found)} — "
        "무접촉 영역의 파일 구성이 바뀌었다"
    )


def test_h3c_new_artifacts_live_outside_the_pinned_areas():
    """H3c — 이 사이클의 신규 산출물은 전부 잠근 영역 **밖**이다(롤백 = 단일 revert)."""
    produced = (_LEAF_REL, _ROUTE_REL)
    for rel in produced:
        assert rel not in _BASE_SHA, f"{rel} 이 무접촉 핀 목록 안이다 — 범위 설계 오류"
        assert not any(rel.startswith(d + "/") for d in _PINNED_DIRS), (
            f"{rel} 이 잠근 디렉터리 안이다 — leaf 는 `src/engine/` 최상위, 라우트는 `src/routes/`"
        )
