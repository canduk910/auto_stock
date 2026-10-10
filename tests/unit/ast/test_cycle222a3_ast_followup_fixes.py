"""cycle222-a3 — 적대적 검증 후속 시정의 AST/가드 봉인.

- G-A3-1 (F-B): 앵커 채택 제외는 **명시 상수**로만 판정 — `tradable_boards` 게이팅 금지
- G-A3-2 (F-C): 관측 로그 두 지점이 hot path 계약(logger 전용)을 지킨다 + 일일 리셋 동행
- G-A3-3 (F-D → G-2): 승인 핀이 **파일 내용 바이트** 해시다 (git config 전 축 면역)
- G-A3-4 (F-F): REST 폴의 KRX 스코프 전제 — `fetch_stock_detail` 이 `"J"`(KRX 단독)를 보낸다
- G-A3-5 (F-G): 승인 도장 검사는 git 을 거치지 않는다 (fail-closed)
- G-A3-6: **8영역 + `scheduler.py` 승인 도장의 정본** — 파일 내용 sha 를 이 파일
  `_APPROVED_CONTENT_SHA` 한 곳에만 둔다(cycle419). 8영역 파일 하나를 고치면 여기 한 줄을
  (새 sha, 승인 사유) 로 고친다. 절차 = 아래 G-A3-6 절 머리 주석
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"


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

def test_ga3_3_content_sha_is_pure_file_bytes():
    """핀 입력이 **파일 바이트**다 — git 을 아예 거치지 않는다.

    git 을 거치지 않으면 git config 축(포맷 옵션)에 **구조적으로** 면역이다.
    정규화 규칙을 축마다 추가하는 싸움이 필요 없어진다.
    """
    mod = sys.modules[__name__]
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


def test_ga3_3b_content_sha_still_detects_real_content_change(monkeypatch):
    """탐지력은 그대로 — 내용이 1바이트만 달라져도 sha 가 바뀐다."""
    mod = sys.modules[__name__]
    target = "src/engine/risk.py"
    before = mod._content_sha(target)
    monkeypatch.setattr(mod, "_read_bytes", lambda path: b"tampered")
    assert mod._content_sha(target) != before


def test_ga3_3c_failure_message_tells_you_to_check_first():
    """실패 메시지가 "무조건 재산출" 로 유도하면 안 된다 (F-D 2차 결함)."""
    src = inspect.getsource(_check_pin)
    assert "핀을 먼저 재산출하지 마라" in src, (
        "실패 메시지가 8영역 실제 변경 확인을 먼저 요구하지 않는다 — "
        "핀 재산출이 실제 변경을 봉인하는 경로가 남는다"
    )


def test_ga3_3d_no_diff_text_hashing_left():
    """diff 텍스트 해시 잔존 금지 — 되돌아가면 같은 사각 재발."""
    mod = sys.modules[__name__]
    assert not hasattr(mod, "_stabilize_diff"), (
        "diff **텍스트** 정규화 헬퍼가 남아 있다 — 그 접근은 git config 축마다 "
        "규칙을 추가해야 하고 실제로 `diff.noprefix` 등에서 뚫렸다(G-2)"
    )
    src = inspect.getsource(_content_sha)
    assert "_read_bytes(" in src, "`_content_sha` 가 파일 바이트 seam(`_read_bytes`)을 거치지 않는다"


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
# G-A3-5 (F-G) — 승인 도장 검사는 git 을 거치지 않는다 (fail-closed)
# ===========================================================================
#
# 옛 가드는 `git diff HEAD --name-only` 로 「무엇이 바뀌었나」 를 물었고, git 이 실패하면
# stdout="" → 「변경 없음」 → 조용히 통과하는 사각이 있어 `_git` 헬퍼에 returncode 검사를
# 강제했다. cycle419 정본(`_check_pin`·`_check_complete`)은 git 을 아예 부르지 않고 파일
# 바이트를 직접 읽는다 — git 실패가 통과로 바뀌는 길 자체가 없다. 파일을 못 읽으면
# 예외로 붉다.

_PIN_GATE_FUNCS = ("_read_bytes", "_content_sha", "_protected_files_on_disk",
                   "_check_pin", "_check_complete")


@pytest.mark.parametrize("fn_name", _PIN_GATE_FUNCS)
def test_ga3_5_pin_gate_never_shells_out_to_git(fn_name):
    """정본 도장 검사 함수에 `subprocess`·`_git` 호출이 없다."""
    fn = ast.parse(textwrap.dedent(inspect.getsource(globals()[fn_name])))
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    for banned in ("subprocess", "_git", "Popen", "check_output"):
        assert banned not in names, (
            f"`{fn_name}` 이 `{banned}` 를 쓴다 — git 출력에 기대면 실패가 「변경 없음」 으로 "
            "읽혀 조용히 통과한다(fail-open)"
        )


def test_ga3_5b_unreadable_file_fails_loudly(monkeypatch):
    """파일을 못 읽으면 통과가 아니라 예외다(fail-closed)."""
    def boom(path):
        raise OSError("disk gone")

    monkeypatch.setattr(sys.modules[__name__], "_read_bytes", boom)
    with pytest.raises(OSError):
        _check_pin("src/engine/order_engine.py")


# ===========================================================================
# G-A3-6 — 8영역 + `scheduler.py` 승인 도장 (정본 한 곳, cycle419)
#
# 8영역 파일과 `scheduler.py` 의 **파일 내용 sha256 은 이 dict 한 곳에만** 둔다.
# 그중 한 파일이 한 글자라도 바뀌면 이 파일의 `test_ga3_6_*` 만 붉어진다.
# 다른 테스트 파일은 같은 sha 를 복사해 두지 않는다(`test_cycle223g3::test_g3_9b`).
#
# 승인된 8영역·scheduler 변경을 넣는 절차
#   1) `git diff -- <path>` 를 눈으로 읽고 바뀐 것이 승인 범위 안인지 확인한다.
#      ⚠️ 핀을 먼저 재산출하지 마라 — 그 순간 범위 밖 변경까지 승인된 것으로 봉인된다.
#   2) 아래 `_APPROVED_CONTENT_SHA[<path>]` 한 줄을 (새 sha, 승인 사유) 로 고친다.
#      sha = `shasum -a 256 <path>` · 사유 = 사이클 번호 + 승인 날짜 + 한 줄 요약.
#   3) 8영역 디렉터리에 파일이 생기거나 사라졌으면 그 항목을 더하거나 뺀다
#      (`test_ga3_6b` 가 디스크와 dict 의 파일 집합을 대조한다).
#
# 이 검사는 git 을 거치지 않는다 — 파일 바이트를 직접 읽으므로 staged·unstaged·커밋된
# 변경과 미추적 새 파일을 모두 보고, git config 축(diff.noprefix 등)에 면역이다(G-2).
# `scheduler.py` 는 8영역이 아니지만 라인 상한 `<3,900`(cycle257 영구 상한) 때문에 같은
# 승인 대상이라 함께 둔다. 라인 상한 자체는 `test_cycle257_ast_dead_code_removed.py` 가 잰다.
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
#: 8영역은 아니지만 같은 승인 대상 — 라인 상한 `<3,900`(cycle257).
_SAME_APPROVAL_FILES = ["src/engine/scheduler.py"]

#: 경로 → (파일 내용 sha256, 마지막 승인 사유). 승인 도장을 찍는 **유일한** 자리.
_APPROVED_CONTENT_SHA: dict[str, tuple[str, str]] = {
    "src/api/order.py": (
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
        "cycle291(2026-09-13) — NXT 프리장 매수 GTP(27) + 취소 호가유형 배관, 8영역 승인",
    ),
    "src/auth/CLAUDE.md": (
        "1d155e95d386b3ecb19f138e966464490ac4912b055f1f8f9da2a154d14ea363",
        "cycle330(2026-09-20) — 문서 전용(토큰 발급 실패 고아 Future 회수 서술)",
    ),
    "src/auth/__init__.py": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "빈 파일 — 초기 구현 이후 무변경",
    ),
    "src/auth/hashkey.py": (
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
        "초기 구현(2026-04-22) 이후 무변경",
    ),
    "src/auth/token.py": (
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
        "cycle330(2026-09-20) — 합류자 없는 토큰 발급 실패의 고아 Future 회수, 8영역 승인",
    ),
    "src/engine/order_engine.py": (
        "3e47e4cfdd2f5649f2fe170c648d1449b41da9c27809e3e19a33a2689ae4dbe5",
        "cycle429 D1 안A 사용자 승인 2026-10-10",
    ),
    "src/engine/risk.py": (
        "a2187b8270446379988d24dfbe39b902d6ab37b112d4b6ce7330ee171434e222",
        "cycle403(2026-10-03) — etf_trend 를 틱 매수 평가 건너뛰기 목록에 한 줄, 8영역 승인",
    ),
    "src/engine/scanner.py": (
        "b570762dfd92df49471dab261d44ecd364d376300ffe9e2f5b7ac19cceb9efcc",
        "cycle417(2026-10-09) — 일봉 증분 적재 구멍 메우기(증분 창 확대 + 구멍 판정 1회), 8영역 승인",
    ),
    "src/engine/scheduler.py": (
        "96a8c2a1e41f22fcd0d8efe8a7d101405af58de5f9bcb6b0c6b25a6f850aada5",
        "cycle431 사용자 승인 2026-10-10 안1 — 액면병합 대사 관측 호출 2줄"
        "(15분 동기화·21:30 정산, corporate_action_reconcile leaf 위임), 승인",
    ),
    "src/engine/session.py": (
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
        "사이클 182(2026-06-28) — 시가 단일가 코드 분기 시간창 게이트",
    ),
    "src/engine/strategy_registry.py": (
        "3b6366c3cdb6e83907428435b95611880f1b8223e572c361a1cad2d00b13a067",
        "cycle399(2026-10-03, 10-02 R1) — update_weights 섀도 전략 켜짐 유지 한 줄, 8영역 승인",
    ),
    "src/realtime/CLAUDE.md": (
        "45817e18bff13cef49af02704f1fae7a5f73b7b0be49d84a42d409b7fc4237aa",
        "cycle374(2026-09-27) — 문서 전용(handler 「접수 전문 기록」 소절)",
    ),
    "src/realtime/__init__.py": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "빈 파일 — 초기 구현 이후 무변경",
    ),
    "src/realtime/handler.py": (
        "e1a484e9ac82d43f0fa85cba693ea5a206ecfbae1076dfee0f4e6bf6d4f2a2d4",
        "cycle374(2026-09-27) — 접수 전문 [order_notice]·거부 [order_rejected_notice] 기록, 8영역 승인",
    ),
    "src/realtime/websocket.py": (
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
        "cycle292·293·294(2026-09-14) — 시세 채널 KRX/NXT 전용 2채널 분리, 8영역 승인",
    ),
    "src/realtime/websocket_pool.py": (
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
        "cycle292·293·294(2026-09-14) — 시세 채널 KRX/NXT 전용 2채널 분리, 8영역 승인",
    ),
}

def _read_bytes(path: str) -> bytes:
    """`path` 의 **현재 내용 바이트** — 테스트가 이 seam 만 갈아끼워 워킹트리 오염 없이
    「내용이 달라지면 붉은가」 를 확인한다(`test_cycle223g3`)."""
    return (_REPO_ROOT / path).read_bytes()


def _content_sha(path: str) -> str:
    """`path` 파일 내용의 sha256 (`shasum -a 256 <path>` 와 같다)."""
    return hashlib.sha256(_read_bytes(path)).hexdigest()


#: 디렉터리를 훑을 때 파일로 세지 않는 것 — 파이썬 캐시와 OS 부산물뿐이다.
_IGNORED_PARTS = frozenset({"__pycache__"})
_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})
_IGNORED_NAMES = frozenset({".DS_Store"})


def _protected_files_on_disk() -> list[str]:
    """8영역 + `scheduler.py` 의 **디스크 위** 파일 목록 — git 을 거치지 않는다.

    `Path.rglob` 로 훑으므로 미추적 새 파일도 보인다(`git ls-files` 는 추적 파일만 본다 —
    cycle259 S4b). 디렉터리 항목은 그 아래 모든 파일(`.md` 포함)이다.
    """
    out: set[str] = set()
    for entry in [*_EIGHT_AREAS, *_SAME_APPROVAL_FILES]:
        target = _REPO_ROOT / entry
        if target.is_dir():
            for p in target.rglob("*"):
                if not p.is_file():
                    continue
                if _IGNORED_PARTS & set(p.parts):
                    continue
                if p.suffix in _IGNORED_SUFFIXES or p.name in _IGNORED_NAMES:
                    continue
                out.add(p.relative_to(_REPO_ROOT).as_posix())
        elif target.is_file():
            out.add(entry)
    return sorted(out)


def _check_pin(path: str) -> None:
    """`path` 의 현재 내용이 승인 도장과 같은지 — 다르면 AssertionError."""
    assert path in _APPROVED_CONTENT_SHA, f"{path} 는 승인 도장 목록에 없다"
    pinned, reason = _APPROVED_CONTENT_SHA[path]
    assert (_REPO_ROOT / path).is_file(), (
        f"{path} 가 사라졌다 — 승인된 삭제라면 `_APPROVED_CONTENT_SHA` 에서 이 항목을 뺀다"
    )
    actual = _content_sha(path)
    assert actual == pinned, (
        f"8영역/scheduler 파일 `{path}` 가 마지막 승인({reason}) 뒤에 바뀌었다.\n"
        "⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 범위 밖 변경까지 승인된 것으로 봉인된다.\n"
        f"  1) `git diff -- {path}` 를 눈으로 읽어라.\n"
        "  2) 승인 없는 변경이면 되돌려라.\n"
        "  3) 사용자 승인을 받은 변경이면 이 파일 `_APPROVED_CONTENT_SHA` 의 그 한 줄을 "
        f"(새 sha, 승인 사유) 로 고친다. 새 sha = {actual}"
    )


def _check_complete() -> None:
    """디스크의 8영역·scheduler 파일 집합 == 승인 도장 목록 — 다르면 AssertionError."""
    on_disk = set(_protected_files_on_disk())
    pinned = set(_APPROVED_CONTENT_SHA)
    assert on_disk == pinned, (
        f"8영역 파일 집합이 승인 도장 목록과 다르다 — 새 파일 {sorted(on_disk - pinned)} · "
        f"사라진 파일 {sorted(pinned - on_disk)}. 승인된 추가·삭제라면 "
        "`_APPROVED_CONTENT_SHA` 에 항목을 더하거나 뺀다"
    )


@pytest.mark.parametrize("path", sorted(_APPROVED_CONTENT_SHA))
def test_ga3_6_protected_file_matches_its_approval_pin(path):
    """8영역·scheduler 파일 하나가 바뀌면 **이 케이스 하나만** 붉어진다(재핀 자리 = 1줄)."""
    _check_pin(path)


def test_ga3_6b_protected_file_set_matches_disk():
    """8영역 디렉터리에 새 파일이 생기거나 파일이 사라지면 붉어진다(미추적 파일 포함)."""
    _check_complete()


def test_ga3_6c_every_pin_is_a_sha_with_an_approval_reason():
    """도장 = 64자리 sha256 + 비어 있지 않은 승인 사유. 파일명만으로 면제하는 길은 없다."""
    for path, value in _APPROVED_CONTENT_SHA.items():
        assert isinstance(value, tuple) and len(value) == 2, f"{path}: (sha, 사유) 형식이 아니다"
        sha, reason = value
        assert isinstance(sha, str) and len(sha) == 64 and all(
            c in "0123456789abcdef" for c in sha
        ), f"{path}: sha256 16진 64자리가 아니다"
        assert isinstance(reason, str) and reason.strip(), f"{path}: 승인 사유가 비었다"
