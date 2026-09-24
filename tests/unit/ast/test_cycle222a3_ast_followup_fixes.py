"""cycle222-a3 — 적대적 검증 후속 시정의 AST/가드 봉인.

- G-A3-1 (F-B): 앵커 채택 제외는 **명시 상수**로만 판정 — `tradable_boards` 게이팅 금지
- G-A3-2 (F-C): 관측 로그 두 지점이 hot path 계약(logger 전용)을 지킨다 + 일일 리셋 동행
- G-A3-3 (F-D → G-2): 면제 핀이 **파일 내용 바이트** 해시다 (git config 전 축 면역)
- G-A3-4 (F-F): REST 폴의 KRX 스코프 전제 — `fetch_stock_detail` 이 `"J"`(KRX 단독)를 보낸다
- G-A3-5 (F-G): 모든 git 헬퍼가 `returncode` 를 검사한다 (fail-closed)
- G-A3-6 (F-A): 8영역 접촉은 여전히 `handler.py`·`risk.py` 둘뿐
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
_AST_DIR = _REPO_ROOT / "tests" / "unit" / "ast"

# `_git` / `_diff_sha` 를 정의한 가드 파일 전수
#
# 🔁 2026-09-02 (cycle240) — `test_cycle222a_ast_day_high_scope.py` **제외**.
#    그 파일의 유일한 `_git` 사용처였던 `test_a11b_stale_watcher_core_untouched`
#    (bare `git diff HEAD -- stale_watcher_core.py` **영구 동결**)를 내용 검사
#    (`test_a11b_stale_watcher_core_no_anchor_coupling`)로 재스코프하면서 `_git`
#    헬퍼 자체가 사라졌다. 사이클 한정 스코프 선언이 수명을 넘겨 그 파일의 모든
#    후속 시정을 무조건 RED 로 만들던 것을 끊은 것이라, 여기 목록에 남겨 두면
#    "탐지기 스테일" 로 잘못 경보한다. 남은 2파일은 여전히 sha 핀 기전을 쓴다.
_GIT_HELPER_FILES = [
    _AST_DIR / "test_cycle223_ast_donchian_exit_fix.py",
    _AST_DIR / "test_cycle223f_ast_manual_apply_safeguard.py",
]
_CONTENT_SHA_MODULES = [
    "tests.unit.ast.test_cycle223_ast_donchian_exit_fix",
    "tests.unit.ast.test_cycle223f_ast_manual_apply_safeguard",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ===========================================================================
# G-A3-1 (F-B) — 제외 판정은 명시 상수. `tradable_boards` 커플링 금지
# ===========================================================================

def test_ga3_1_exclusion_constant_exists_at_module_level():
    """`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 선례와 동형 — 모듈 상수 frozenset."""
    tree = ast.parse(_read(_SRC / "engine" / "risk.py"))
    names = {
        t.id for node in tree.body if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name)
    }
    assert "_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES" in names, (
        "앵커 채택 제외 집합이 모듈 상수로 없다 — 인라인 문자열 비교/보드 게이팅 금지"
    )


def test_ga3_1b_exclusion_is_not_gated_by_tradable_boards():
    """`tradable_boards` 는 **매수 진입 전용**(사이클 38 명문화).

    매수 목적의 보드 변경이 청산 앵커 규약을 조용히 바꾸는 커플링을 차단한다 —
    `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 가 같은 이유로 명시 상수인 것과 동형.
    """
    tree = ast.parse(_read(_SRC / "engine" / "risk.py"))
    fn = _func(tree, "_day_high_since_entry")
    assert fn is not None
    body = ast.unparse(fn)
    assert "_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES" in body, (
        "리졸버가 제외 상수를 참조하지 않는다 — F-B 시정 미배선"
    )
    assert "tradable_boards" not in body, (
        "앵커 채택 제외를 `tradable_boards` 로 게이팅했다 — 매수 전용 독트린 위반"
    )


def test_ga3_1c_exclusion_check_precedes_verbatim_adoption():
    """제외 검사가 `buy_date < today → verbatim` 분기보다 **앞** 이어야 한다.

    뒤에 두면 멀티데이 보유가 verbatim 으로 먼저 빠져나가 제외가 무력화된다.

    ## ⚠️ 이 가드는 한때 **항상 통과하는 no-op** 이었다 (cycle222-a3 G-6)

    구 구현은 `src.index("_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES") <
    src.index("return day_high")` 라는 **문자열 위치** 비교였다. 그런데 그 상수의
    첫 등장은 상수 **자기 정의문**(`_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES =
    frozenset(...)`, 모듈 레벨)이고, 모듈 레벨 정의는 `_day_high_since_entry`
    본문보다 **항상 텍스트상 앞**이다. 즉 비교 결과가 **입력과 무관하게 항상
    참**이라 가드가 구조적으로 no-op 이었다.

    실측(배포 트리): 상수 첫 등장 char 4069 / line 102 = 모듈 레벨 정의문
    (앞 구간의 삼중따옴표 개수는 **짝수** = docstring 밖), `return day_high` 는
    char 12511 / line 291. 뮤테이션 M7(제외 검사를 verbatim 분기 **뒤로** 이동)
    이후에도 `excl@4069 < verbatim@12418 -> True` 로 통과해 no-op 이 확증됐고,
    그 때 M7 을 잡은 것은 행위 테스트 6건뿐이었다.

    ⚠️ 이 자리에 두 번 틀린 서술이 있었고 둘 다 실측으로 정정했다.
       (1) "첫 등장은 docstring(char 2524, 앞 삼중따옴표 홀수)" — 재현 안 됨.
       (2) 그 정정문의 "char 2524 는 **다른 상수**의 주석 본문" — 이것도 틀렸다.
       실측: char 2524 = `risk.py` **line 67**, 그리고 그 줄은 `:47`~`:101` 로
       이어지는 연속 `#` 블록 안이며 그 블록이 수식하는 상수가 바로 `:102` 의
       `_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 다 — 즉 **이 상수 자신의 선행
       주석**이다(사이에 다른 대입문 없음). 코드 사실과 어긋나는 서술은 이번
       사이클이 G-4 로 제거한 바로 그 결함이라, 같은 기준을 이 가드 자신에게
       적용한다.

    시정 = **AST 노드 위치**로 본다. `ast.Name` / `ast.Return` 노드는 주석·
    docstring 안에 존재할 수 없고, 상수 정의문의 `ast.Name` 도 함수 밖이라
    `_func(...)` 로 좁힌 서브트리에는 애초에 들어오지 않는다 — 구조적으로
    오탐/누락이 불가능하다. (로직은 그대로 두고 근거 서술만 정정한다.)
    """
    fn = _func(ast.parse(_read(_SRC / "engine" / "risk.py")), "_day_high_since_entry")
    assert fn is not None, "`_day_high_since_entry` 미발견 — 탐지기 스테일"

    # docstring 은 애초에 Name/Return 노드를 만들지 않는다 (G-6 시정의 핵심).
    excl_lines = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Name) and n.id == "_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES"
    ]
    verbatim_lines = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Return)
        and isinstance(n.value, ast.Name) and n.value.id == "day_high"
    ]
    all_returns = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)]

    assert excl_lines, "제외 상수 참조가 **코드**에 없다 — docstring 언급만 있다"
    assert verbatim_lines, (
        "`return day_high`(verbatim 채택) 분기 미발견 — 탐지기 스테일"
    )
    assert min(excl_lines) < min(verbatim_lines), (
        "제외 검사가 verbatim 채택 분기보다 뒤에 있다 — 멀티데이 보유가 먼저 통과한다"
    )
    # 더 강하게: 제외 검사 앞에는 **어떤 return 도** 있으면 안 된다.
    assert min(excl_lines) < min(all_returns), (
        "제외 검사 앞에 다른 return 이 생겼다 — 제외가 조건부로 우회될 수 있다"
    )


# ===========================================================================
# G-A3-2 (F-C) — 관측 로그 hot path 계약 + 일일 리셋 동행
# ===========================================================================

def test_ga3_2_risk_adopted_log_is_logger_only_and_capped():
    from src.engine.risk import RiskManager

    helper = inspect.getsource(RiskManager._maybe_emit_day_high_adopted)
    assert "logger.info" in helper, "`logger` 외 경로 사용 금지 (write_log/DB 금지)"
    reset = inspect.getsource(RiskManager.reset_daily_state)
    assert "_day_high_adopted_logged" in reset, (
        "reset_daily_state 동행 clear 부재 — 정산 후 cap 잔류"
    )


def test_ga3_2b_on_tick_still_has_no_db_paths_after_log_wiring():
    """A-1b 재확인 — 관측 로그 배선이 hot path 계약을 깨지 않았다."""
    tree = ast.parse(_read(_SRC / "engine" / "risk.py"))
    fn = _func(tree, "on_tick")
    body = ast.unparse(fn)
    for banned in ("pg.fetch", "pg.execute", "write_log", "update_high", "insert_"):
        assert banned not in body, f"on_tick 에 `{banned}` 유입"


def test_ga3_2c_handler_scope_skip_is_logger_only_and_daily_reset():
    from src.realtime import handler

    import textwrap

    helper = textwrap.dedent(inspect.getsource(handler._maybe_log_day_high_scope_skip))
    fn = ast.parse(helper).body[0]
    assert not isinstance(fn, ast.AsyncFunctionDef)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    # docstring 오탐 회피 — **코드 노드** 기준 (A-10b 선례)
    code = "\n".join(
        ast.unparse(n) for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    )
    assert "logger.info" in code
    for banned in ("write_log", "pg.fetch", "pg.execute", "insert_"):
        assert banned not in code, f"`{banned}` 유입 — hot path 계약 위반"
    assert "_day_high_scope_skip_day" in helper, (
        "일일 리셋 축(KST 일자 인덱스)이 없다 — cap 이 영구 잔류한다"
    )
    assert hasattr(handler, "reset_day_high_scope_skip"), "명시 리셋 훅 부재"


# ===========================================================================
# G-A3-3 (F-D → cycle222-a3 G-2) — 면제 핀은 **파일 내용 바이트** 해시
# ===========================================================================
#
# 1차 시정(F-D)은 `git diff` 출력에서 `index <abbrev>` 줄만 제거해 **abbrev 축만**
# 막았다. 같은 실패 클래스(코드 변경 0인데 FAIL → "핀 재산출" 유도 → 실제 8영역
# 변경까지 함께 봉인)가 다른 git config 축에 그대로 남아 있었다 — 아래 G-2 실증.

@pytest.mark.parametrize("modname", _CONTENT_SHA_MODULES)
def test_ga3_3_content_sha_is_pure_file_bytes(modname):
    """핀 입력이 **파일 바이트**다 — git 을 아예 거치지 않는다.

    git 을 거치지 않으면 git config 축(포맷 옵션)에 **구조적으로** 면역이다.
    정규화 규칙을 축마다 추가하는 싸움이 필요 없어진다.
    """
    mod = importlib.import_module(modname)
    target = "src/engine/risk.py"
    expected = hashlib.sha256((_REPO_ROOT / target).read_bytes()).hexdigest()
    assert mod._content_sha(target) == expected, (
        "`_content_sha` 가 파일 바이트 해시가 아니다 — `shasum -a 256` 과 일치해야 한다"
    )
    body = inspect.getsource(mod._content_sha) + inspect.getsource(mod._read_bytes)
    for banned in ("_git(", "subprocess"):
        assert banned not in body, (
            f"`_content_sha`/`_read_bytes` 가 `{banned}` 를 쓴다 — git 출력이 입력에 "
            "섞이면 config 축 면역이 깨진다"
        )


@pytest.mark.parametrize("modname", _CONTENT_SHA_MODULES)
def test_ga3_3b_content_sha_still_detects_real_content_change(modname, monkeypatch):
    """탐지력은 그대로 — 내용이 1바이트만 달라져도 sha 가 바뀐다."""
    mod = importlib.import_module(modname)
    target = "src/engine/risk.py"
    before = mod._content_sha(target)
    monkeypatch.setattr(mod, "_read_bytes", lambda path: b"tampered")
    assert mod._content_sha(target) != before


@pytest.mark.parametrize("modname", _CONTENT_SHA_MODULES)
def test_ga3_3c_failure_message_tells_you_to_check_first(modname):
    """실패 메시지가 "무조건 재산출" 로 유도하면 안 된다 (F-D 2차 결함)."""
    src = _read(Path(inspect.getfile(importlib.import_module(modname))))
    assert "핀을 먼저 재산출하지 마라" in src, (
        "실패 메시지가 8영역 실제 변경 확인을 먼저 요구하지 않는다 — "
        "핀 재산출이 실제 변경을 봉인하는 경로가 남는다"
    )


@pytest.mark.parametrize("modname", _CONTENT_SHA_MODULES)
def test_ga3_3d_no_diff_text_hashing_left(modname):
    """`_stabilize_diff` / diff 텍스트 해시 잔존 금지 — 되돌아가면 같은 사각 재발."""
    src = _read(Path(inspect.getfile(importlib.import_module(modname))))
    assert "_stabilize_diff" not in src, (
        "diff **텍스트** 정규화 헬퍼가 남아 있다 — 그 접근은 git config 축마다 "
        "규칙을 추가해야 하고 실제로 `diff.noprefix` 등에서 뚫렸다(G-2)"
    )
    assert "_content_sha" in src and "_read_bytes" in src


def test_ga3_3e_diff_text_hash_breaks_on_git_config_but_content_hash_does_not(tmp_path):
    """★ G-2 실증 — **코드 변경 0인데** diff 텍스트 해시만 갈린다.

    임시 레포에서 같은 워킹트리를 놓고 두 방식을 나란히 잰다. 이 테스트가 없으면
    "왜 diff 텍스트를 버렸나" 가 주장으로만 남고, 다음 사람이 '단순하니까' 로
    되돌린다.
    """
    import subprocess as sp

    def git(*args, config: str | None = None) -> str:
        cmd = ["git"]
        if config:
            cmd += ["-c", config]
        res = sp.run([*cmd, *args], cwd=tmp_path, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        return res.stdout

    git("init", "-q", ".")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    f = tmp_path / "f.py"
    f.write_text("".join(f"line{i}\n" for i in range(1, 9)), encoding="utf-8")
    git("add", "f.py")
    git("commit", "-qm", "init")
    f.write_text(
        "line1\nCHANGED\n" + "".join(f"line{i}\n" for i in range(3, 9)),
        encoding="utf-8",
    )

    def stabilized_diff_sha(config: str | None) -> str:
        raw = git("diff", "HEAD", "--", "f.py", config=config)
        # 구 `_stabilize_diff` 와 동일한 정규화 (abbrev 축만 제거)
        text = "\n".join(l for l in raw.splitlines() if not l.startswith("index "))
        return hashlib.sha256(text.encode()).hexdigest()

    base = stabilized_diff_sha(None)
    absorbed = ["core.abbrev=12", "diff.algorithm=histogram"]
    leaking = ["diff.noprefix=true", "diff.mnemonicPrefix=true",
               "diff.srcPrefix=SRC/", "diff.context=5"]

    for cfg in absorbed:
        assert stabilized_diff_sha(cfg) == base, f"{cfg} 는 F-D 가 흡수하던 축이다"
    for cfg in leaking:
        assert stabilized_diff_sha(cfg) != base, (
            f"{cfg} 에서 diff 텍스트 해시가 흔들리지 않는다 — 실증 전제 재확인 필요"
        )

    # 같은 구간에서 파일 내용 해시는 **단 하나**다 (git config 무관).
    content = {hashlib.sha256(f.read_bytes()).hexdigest() for _ in leaking + absorbed}
    assert len(content) == 1


# ===========================================================================
# G-A3-4 (F-F) — REST 폴의 KRX 스코프 전제
# ===========================================================================

def test_ga3_4_fetch_stock_detail_uses_krx_only_market_code():
    """`fid_cond_mrkt_div_code = "J"`(KRX 단독) 전제를 못박는다.

    ## 왜 load-bearing 인가

    `scheduler._run_swing_rest_poll_once` 는 REST 응답의 `stck_hgpr`(당일고가)를
    **시각 필터 없이** `on_tick(day_high=...)` 에 먹인다. WS 경로에는 `[27]
    HGPR_HOUR` 라는 스코프 판별자가 있지만 **REST 응답에는 대응 필드가 없다** —
    즉 소스 필터 수단 자체가 존재하지 않는다.

    그래서 이 경로의 안전성은 오직 **"응답이 KRX 단독 스코프"** 라는 전제 한 줄에
    걸려 있다. 누군가 "NXT 커버리지 확대" 를 이유로 `"UN"`(통합)으로 바꾸면
    프리장 누적치가 그대로 실려 오고, `buy_date < today` 포지션은 baseline 도
    없어 **첫 폴에서 즉시 앵커에 박힌다**(= 없던 고점 기준 조기 청산).

    바꾸려면 REST 경로의 day_high 배선을 **먼저** 걷어내라.
    """
    tree = ast.parse(_read(_SRC / "api" / "condition.py"))
    fn = _func(tree, "_fetch_stock_detail_and_cache")
    assert fn is not None, (
        "`_fetch_stock_detail_and_cache` 미발견 — 탐지기 스테일(가드 무효화)"
    )
    found: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "fid_cond_mrkt_div_code"
                    and isinstance(v, ast.Constant)):
                found.append(v.value)
    assert found == ["J"], (
        f"fetch_stock_detail 의 시장분류코드가 {found} 다 (기대 ['J']).\n"
        "이 값이 KRX 단독이 아니면 REST 폴 응답의 `stck_hgpr` 에 NXT 프리장 누적치가 "
        "실린다. REST 에는 `[27] HGPR_HOUR` 대응 필드가 없어 **소스 필터 수단이 아예 "
        "없고**, `buy_date < today` 포지션은 risk 계층 baseline 도 없어 첫 폴에서 "
        "즉시 앵커에 박힌다 = 없던 고점 기준 조기 청산.\n"
        "통합 스코프로 넓히려면 `scheduler._run_swing_rest_poll_once` 의 day_high "
        "배선을 **먼저** 제거하라."
    )


def test_ga3_4b_rest_poll_still_feeds_day_high_from_that_response():
    """전제가 load-bearing 임을 실증 — 폴이 실제로 그 응답의 고가를 먹인다.

    배선이 사라지면 위 가드는 무의미해지므로 커플링을 함께 잠근다.
    """
    tree = ast.parse(_read(_SRC / "engine" / "scheduler.py"))
    fn = _func(tree, "_run_swing_rest_poll_once")
    assert fn is not None
    body = ast.unparse(fn)
    assert "fetch_stock_detail" in body, "폴이 fetch_stock_detail 를 쓰지 않는다"
    assert "stck_hgpr" in body and "day_high" in body, (
        "폴이 day_high 를 배선하지 않는다 — F-F 가드의 전제를 재검토하라"
    )


# ===========================================================================
# G-A3-5 (F-G) — git 헬퍼 fail-closed
# ===========================================================================

@pytest.mark.parametrize("path", _GIT_HELPER_FILES, ids=lambda p: p.name)
def test_ga3_5_git_helper_checks_returncode(path):
    """`.stdout` 만 읽으면 git 실패 시 `changed == []` 로 **조용히 통과**한다."""
    tree = ast.parse(_read(path))
    fn = _func(tree, "_git")
    assert fn is not None, f"{path.name} 에 `_git` 헬퍼가 없다 (탐지기 스테일)"
    body = ast.unparse(fn)
    assert "returncode" in body, (
        f"{path.name}::_git 이 returncode 를 검사하지 않는다 — git 실패 시 "
        "stdout='' → 변경 없음 → 가드가 가장 필요한 순간에 초록이 된다(fail-open)"
    )
    assert "raise" in body or "assert" in body, (
        f"{path.name}::_git 이 실패를 **알리지** 않는다 — fail-closed 필요"
    )


@pytest.mark.parametrize("path", _GIT_HELPER_FILES, ids=lambda p: p.name)
def test_ga3_5b_no_bare_stdout_only_subprocess_run_left(path):
    """`subprocess.run(...).stdout` 직접 체이닝이 남아 있으면 같은 사각 재발."""
    src = _read(path)
    assert ").stdout" not in src.replace("res.stdout", ""), (
        f"{path.name} 에 `subprocess.run(...).stdout` 체이닝 잔존 — returncode 미검사"
    )


def test_ga3_5c_git_helper_actually_raises_on_failure(monkeypatch):
    """런타임 실증 — rc≠0 이면 AssertionError."""
    mod = importlib.import_module("tests.unit.ast.test_cycle223_ast_donchian_exit_fix")

    class _R:
        stdout = ""
        stderr = "fatal: not a git repository"
        returncode = 128

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: _R())
    with pytest.raises(AssertionError, match="fail-closed"):
        mod._git("diff", "HEAD", "--name-only")


# ===========================================================================
# G-A3-6 (F-A 범위) — 8영역 접촉은 handler.py · risk.py 둘뿐
#
# ⚠️ 이 문장은 **8영역 한정**이다. cycle222-a 의 실제 소스 footprint 는 **3파일**이고
#    `src/engine/scheduler.py` 가 그 세 번째다 — REST 스윙 폴이 응답의 당일고가를
#    뽑아 `on_tick(..., day_high=...)` 로 넘기는 배선(+ 09:05 확장창·F3)이 거기 있다.
#    `scheduler.py` 는 8영역이 **아니라서** 이 diff-0 가드가 잡지 않는다. 그 경로는
#    대신 `test_cycle222a_ast_day_high_scope.py::test_a11_*` 와 본 파일의
#    `test_ga3_4*`(KRX 전용 market code 전제 + 배선 존치)가 지킨다.
#    "cycle222-a 는 2파일" 로 읽고 scheduler 를 리뷰 범위에서 빼면, **시각 판별자 없이**
#    앵커에 값을 먹이는 유일한 경로가 아무도 읽지 않은 채 배포된다.
# ===========================================================================

_EIGHT_AREAS = [
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/scanner.py",
    "src/engine/session.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
    "src/realtime",
    "src/auth",
]
_ALLOWED = {"src/engine/risk.py", "src/realtime/handler.py"}

# 🔁 2026-08-29 (cycle235) — 파일명 영구 허용(_ALLOWED)과 별개로, **승인 사이클의
#    in-flight 변경**은 내용 sha 로 한시 면제한다(cycle223 계열 자기소멸 기전 이식 —
#    커밋되면 diff 에서 사라져 죽은 값이 되고, 내용이 1 byte 라도 더 바뀌면 FAIL).
#    cycle235 승인 = "N1부터 작업 시작"(handler·order_engine + realtime/CLAUDE.md 문서):
#    체결수량 fields[16]→fields[9] 정본 전환 + overrun 클램프. 명세
#    `_workspace/red/cycle235_fill_qty_spec.md`.
# TODO(cycle235 커밋 후): 아래 dict 를 비운다.
# ✅ 2026-09-11 (cycle276) — AI 매수평가 **주문 발화 시점 이동**. 사용자가
#    `src/engine/order_engine.py` 접촉을 명시 승인했다("매수신호가 실제로 발생하고
#    …실제로 매수주문을 발화하는 시점으로 함"). 변경은 import 1줄 + `execute_buy`
#    두 매수 경로의 관측 훅 2곳(각각 `try` / 1문 / `except Exception` 흡수기)뿐이고,
#    A-ATOMIC 구간(`calc_buy_quantity` ~ `pending_buys.add`)은 byte 동일이다.
#    TODO(cycle276 커밋 후): 아래 dict 를 다시 **비운다**.
# ✅ 2026-09-11 (cycle283) — 저녁 창 재설계. 사용자 명시 승인 범위 = `src/engine/scanner.py`
#    **단독**(커트오프 상수 `_DAILY_LOAD_TODAY_BAR_CUTOFF` 15:40 → 20:00 + 근거 주석·
#    docstring 정직화). 판정식 2줄은 **텍스트 동일**이고 나머지 7영역은 diff 0 이다.
#    자매 가드 **네 곳 전부**에 같은 값으로 핀한다.
# TODO(cycle283 커밋 후): 아래 항목을 **삭제**한다.
# ✅ 2026-09-12 (cycle286, C4-a) — `nxt_tradable=False` 사후 보강의 판정축을 시계
#    단독(`08:00~09:00 ∪ 15:30~20:00`)에서 **거래소(`target_exchange ∈ {"NXT","SOR"}`)
#    ∧ 좁힌 프리장 창(08:00~08:50)** 으로 교체 — 사용자가 8영역 `order_engine.py` 접촉을
#    명시 승인했다. `execute_sell` 의 `is_market_closed_rejection` 분기 안 학습 write
#    조건식만 바뀌고 분류 순서·TTL 등록·positions 보존은 byte 동일이다.
#    TODO(cycle286 커밋 후): 아래 항목을 **삭제**한다.
# ✅ 2026-09-12 (cycle287) — 시각이 거래소·호가유형을 정한다(규칙 1 라우팅 +
#    규칙 2 KRX 애프터마켓 41/44). 사용자 명시 8영역 승인, 범위 =
#    `src/engine/order_engine.py` + `src/api/order.py`(docstring 만, 본문 byte
#    동일). 자매 가드 네 곳 전부 같은 값. TODO(cycle287 커밋 후): 아래 항목을 **삭제**한다.
_APPROVED_CONTENT_SHA: dict[str, str] = {
    # ✅ 2026-09-18 (cycle302) 재핀 — 일봉 backfill 의 **대상**을 지수에서 적재 대상
    #    전부로 확대. 사용자 명시 8영역 승인("전부 담는게 좋을듯한데? VCP평가대상이
    #    어떻게 바뀔지 모르잖아"), 범위 = `src/engine/scanner.py` **단독**이고 이
    #    사이클의 프로덕션 변경은 이 한 파일뿐이다. 바뀐 것 = backfill 분기에서 지수
    #    소속 판정 제거 + 그 판정에만 쓰이던 `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수(`_DAILY_LOAD_VCP_BACKFILL_DAYS`=225)는 그대로다.
    #    나머지 7영역과 `scheduler.py` 는 diff 0.
    #    자매 가드 **네 곳 전부** 같은 값(`test_g3_9b` 계약).
    #    TODO(cycle302 커밋 후): 이 항목을 **삭제**한다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    # 🔁 2026-09-25 (cycle358) 재핀 — 카드 D(관측 전용). `trade_history` PARTIAL/
    #    CANCELLED UPDATE 가 `affected==0` 이어도 무흔적이던 결함에 `[trade_status_
    #    update_miss]` WARNING 을 추가한다(사용자 승인, 워크리스트 ⑨). 매매·상태전이
    #    로직 무변경 — 로그 호출만 추가. 자매 가드 네 곳 전부 같은 값(`test_g3_9b` 계약).
    #    TODO(cycle358 커밋 후): 이 항목을 **삭제**한다.
    "src/engine/order_engine.py":
        "118ebf38fd9004bf37cebf065199b949d9093d98ab9792b710b06345b5a119e3",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # ✅ 2026-09-14 (cycle293) — 시세 채널 리졸버 2단계(속성축 배관). 사용자 승인
    #    8영역 4파일(`scanner`·`websocket`·`websocket_pool`·`order_engine`) +
    #    §3-E B-1 매수 축 보존 게이트 때문에 `risk.py` 1건(별도 승인 대상, 근거는
    #    `test_cycle293_ast_channel_resolver.py::test_a1b` docstring).
    #    자매 가드 **네 곳 전부** 같은 값이어야 한다(`_PIN_GUARD_FILES` 정본).
    #    등록은 승인된 사이클의 Green 이, 비우기는 병합 후속 커밋이 한다.
    "src/engine/risk.py":
        "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 📄 2026-09-14 (cycle293) — **문서 전용 변경**(`src/realtime/**` 이 8영역 디렉터리라
    #    `.md` 도 이 가드에 잡힌다). 「시세 채널」 절이 속성축 리졸버 2단계 착지·프로브
    #    격리 기준 전환·`get_subscribed_tickers()` 합집합 서술을 담도록 갱신됐다.
    #    프로덕션 코드 영향 0. 등록은 Green 이, 비우기는 병합 후속 커밋이 한다.
    # 📄 2026-09-15 (cycle295, A축) — **문서 전용 변경**. 갭 홀드 CRITICAL-1 절이
    #    철회 서술로 재작성됐고(§6-4 — 삭제 아님), 다이얼 표·런북 curl·전환 창
    #    라벨이 「전환 1회」로 되돌아갔다. 프로덕션 코드 영향 0(이 사이클의 코드
    #    영향은 8영역 밖 4파일 — `_APPROVED_CONTENT_SHA` 대상이 아니다).
    # 📄 2026-09-17 — **문서 전용 변경**(덧칠 정리). 경위·실측 수치·폐기 값은
    #    `docs/history/src-realtime-CLAUDE.history.md` 로 verbatim 이관하고 정본엔
    #    현재 계약만 남겼다. 프로덕션 코드 영향 0.
    "src/realtime/CLAUDE.md":
        "7c3d432254a9f71a8341d371cb14bbc8e58112a16cc536301620c7f1ab62f58d",
    # ✅ 2026-09-17 (cycle296) — `TokenManager.issue()` 매니저 단위 in-flight
    #    합류. 사용자 명시 8영역 승인(`src/auth/**`), 범위 = `src/auth/token.py`
    #    `issue()` + `__init__` 신규 필드뿐(`get_token`/`revoke`/`_is_valid` 무접촉).
    #    자매 가드 네 곳 전부 같은 값(`test_g3_9b`/`test_g223f_9`/`test_g223_10` 계약).
    #    TODO(cycle296 커밋 후): 아래 항목을 **삭제**한다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # 📄 2026-09-17 — **문서 전용 변경**(`src/auth/**` 이 8영역 디렉터리라 `.md` 도
    #    이 가드에 잡힌다 — `src/realtime/CLAUDE.md` 와 같은 계열). 소제목의 사이클
    #    번호를 규칙 이름으로 바꾸고, 걷어낸 경위를 `docs/history/src-auth-CLAUDE.history.md`
    #    로 옮겼다(정본 규약 = 루트 `CLAUDE.md` 「문서 규약」 절). 프로덕션 코드 영향 0.
    #    자매 가드 네 곳 전부 같은 값(`test_g3_9b` 계약).
    #    TODO(커밋 후): 아래 항목을 **삭제**한다.
    "src/auth/CLAUDE.md":
        "1d155e95d386b3ecb19f138e966464490ac4912b055f1f8f9da2a154d14ea363",
    # ✅ 2026-09-20 (cycle329) — 체결통보 **주문수량**(`fields[16] ODER_QTY`) 배선.
    #    사용자 결정("체결통보 주문수량 쓰자") + `domain-consult` 선행. 고치는 것 =
    #    `await place_order` 도중 착지한 통보는 `order_no` 매핑이 비어 `ordered_qty` 가
    #    **증분 체결량으로 폴백**되고, `total_filled >= ordered_qty` 가 항상 참이 되어
    #    **부분 체결이 전량으로 오판**된다(매도 = 잔량이 손절 감시 밖으로 소멸,
    #    매수 = `_completed_buy_orders` 무장으로 잔여 통보 소실 + 영구 과소 수량).
    #    `handler.py` 변경은 파싱 1블록 + 콜백 인자 1개뿐이고 체결수량 소스
    #    `fields[9]` 는 무접촉이다(`test_cycle235_ast_execution_qty.py` 봉인 유지).
    #    자매 가드 **네 곳 전부** 같은 값(`test_g3_9b` 계약).
    #    TODO(cycle329 커밋 후): 이 항목을 **삭제**한다.
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
}


def _approved_and_intact(path: str) -> bool:
    pin = _APPROVED_CONTENT_SHA.get(path)
    if pin is None:
        return False
    return hashlib.sha256((_REPO_ROOT / path).read_bytes()).hexdigest() == pin


def _git(*args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if getattr(res, "returncode", 0) != 0:
        raise AssertionError(
            f"git {' '.join(args)} 실패 (rc={res.returncode}) — fail-closed. "
            f"stderr: {(res.stderr or '').strip()}"
        )
    return res.stdout


def test_ga3_6_eight_areas_touched_are_only_handler_and_risk():
    tracked = _git("diff", "HEAD", "--name-only", "--", *_EIGHT_AREAS).split()
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", *_EIGHT_AREAS,
    ).split()
    changed = sorted(set(tracked) | set(untracked))
    unexpected = sorted(
        p for p in set(changed) - _ALLOWED if not _approved_and_intact(p)
    )
    assert unexpected == [], (
        f"8영역 범위 밖 변경 감지: {unexpected} — 파일명 영구 허용(handler.py·risk.py) "
        "또는 승인 사이클 sha 핀(_APPROVED_CONTENT_SHA, 내용 일치 시 한정)만 통과한다"
    )
