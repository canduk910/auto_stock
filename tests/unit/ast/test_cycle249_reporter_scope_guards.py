"""cycle249 Red (H) — 리포터 스코프의 **구조** 가드(AST · 배포 자산 텍스트).

명세: `_workspace/red/cycle249_reporter_scope_spec.md` §B/§D/§E/§F · §H(AST)

## 행위 가드만으로 부족한 이유

미들웨어 행위 테스트는 "지금 이 판정이 옳다" 를 말하지만, **왜 그 순서여야 하는지**는
말하지 못한다. 이 사이클의 위험은 전부 *순서와 앵커*에 있다:

* 리포터 분기가 운영자 분기 **앞**으로 가면 → 운영 키와 리포터 키가 같은 값일 때
  운영자가 403 이 된다(그리고 그 상태는 평소엔 안 드러난다).
* 빈 리포터 키 선분기가 사라지면 → `compare_digest("", "")` 가 True 라 **기본 설정**
  (리포터 키 미설정)에서 빈 헤더가 리포터로 승격된다.
* 경로 정규식의 `^`/`$` 앵커가 빠지면 → `…/external/../trading/manual-sell` 이 통과한다.
* 라우트 `bundle` 이 `{target_date}` **뒤**에 선언되면 → 조용히 "날짜 형식 오류" 200.
* nginx map 의 default/reporter 가 뒤바뀌면 → 리포터 사용자가 **운영 키**를 받는다
  (= 스코프가 통째로 사라지는데 모든 요청이 정상 200 이라 아무도 모른다).

## 이 파일의 자기 규율

nginx 템플릿을 검사하는 절은 치환 구문(달러+중괄호)을 **문자 단위로 조립**한다 —
cycle246 이 못박은 관례(가드 자신이 위반 사례가 되지 않게)를 따른다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_MIDDLEWARE = _ROOT / "src" / "middleware" / "api_auth.py"
_CONFIG = _ROOT / "src" / "config.py"
_ROUTES = _ROOT / "src" / "routes" / "log_reports.py"
_ENV_EXAMPLE = _ROOT / ".env.example"
_COMPOSE = _ROOT / "docker-compose.prod.yml"
_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_MIGRATION = _ROOT / "supabase" / "migrations" / "042_daily_log_reports_external.sql"

# 치환 구문은 조립한다(위 "자기 규율" 참조).
_D = chr(36)
_SUBST_AUTH = _D + "{API_AUTH_KEY}"
_SUBST_REPORTER = _D + "{API_REPORTER_KEY}"
_VAR_PER_USER = _D + "api_key_for_user"
_VAR_REMOTE_USER = _D + "remote_user"

EXT_COLUMNS = [
    "ext_provider",
    "ext_model",
    "ext_summary",
    "ext_findings",
    "ext_report_md",
    "ext_created_at",
]


def _read(path: Path) -> str:
    assert path.is_file(), f"Red — 파일이 없다: {path}"
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_read(path))


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node  # type: ignore[return-value]
    pytest.fail(f"Red — 모듈 레벨 함수 `{name}` 이 없다")


def _module_assign(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return node.value
    pytest.fail(f"Red — 모듈 레벨 상수 `{name}` 이 없다")


# ---------------------------------------------------------------------------
# G-249-1 ~ G-249-4 — 미들웨어 구조
# ---------------------------------------------------------------------------
def test_reporter_write_path_re_when_declared_then_single_anchored_pattern():
    """G-249-1 — `REPORTER_WRITE_PATH_RE` = 앵커된 **단일** 경로 패턴.

    `^` 가 없으면 접두 삽입(`/x/api/log-reports/…/external`)이, `\\Z` 가 없으면 접미
    확장(`…/external/../trading/manual-sell`)이 통과한다. `|` 로 경로를 늘리는 변경은
    "유일한 쓰기 경로" 라는 이 스코프의 근거 자체를 무너뜨리므로 여기서 막는다.

    cycle249 위생 시정 — 종전 `$` 는 문자열 끝의 **개행 직전**도 허용해(re 모듈 기본
    동작) `…/external\\n` 류가 매치될 여지를 남겼고, `\\d` 는 ASCII 외 유니코드 십진
    숫자(전각 등)까지 삼켰다. `\\Z` + `[0-9]` 로 두 여지를 모두 막는다.
    """
    value = _module_assign(_tree(_MIDDLEWARE), "REPORTER_WRITE_PATH_RE")
    src = ast.unparse(value)
    assert "re.compile(" in src, f"re.compile 로 미리 컴파일해야 한다: {src}"

    literals = [n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert len(literals) == 1, f"패턴 문자열이 1개가 아니다: {literals}"
    pattern = literals[0]
    assert pattern.startswith("^"), f"`^` 앵커 없음: {pattern!r}"
    assert pattern.endswith("\\Z"), f"`\\Z` 앵커 없음(또는 `$` 잔존): {pattern!r}"
    assert not pattern.endswith("$"), f"`$` 로 되돌아갔다(개행 직전 매치 여지): {pattern!r}"
    assert "\\d" not in pattern, f"`\\d` 가 남아 있다(유니코드 숫자 매치 여지): {pattern!r}"
    assert "[0-9]" in pattern, f"ASCII 숫자 클래스 `[0-9]` 가 없다: {pattern!r}"
    assert "|" not in pattern, f"대안(|)으로 경로를 늘렸다: {pattern!r}"

    compiled = re.compile(pattern)
    assert compiled.fullmatch("/api/log-reports/2026-09-04/external")
    for bad in (
        "/api/log-reports/2026-09-04/external/",
        "/api/log-reports/2026-09-04/externalx",
        "/x/api/log-reports/2026-09-04/external",
        "/api/log-reports/20260904/external",
        "/api/log-reports/2026-09-04/external\n",  # 후행 개행 — 옛 `$` 함정
        "/api/log-reports/２０２６-09-04/external",  # 전각 숫자 — 옛 `\d` 함정
    ):
        assert not compiled.fullmatch(bad), f"경로 변형이 매치됐다: {bad!r}"
        assert not compiled.match(bad), f"경로 변형이 `.match()` 로도 매치됐다: {bad!r}"


def test_reporter_write_path_when_used_then_guarded_by_post():
    """G-249-2 — 경로 정규식은 **POST 검사 아래**에서만 쓰인다.

    메서드 조건 없이 경로만 보면 같은 경로의 PUT/DELETE 가 함께 열린다.
    중첩(`if method == "POST": if RE.match(...)`)과 평면(`and`) 두 형태 모두 허용하되,
    조상 `if` 중 하나에는 반드시 `POST` 가 있어야 한다.
    """
    tree = _tree(_MIDDLEWARE)
    fn = _func(tree, "authorize")

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    hits = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Name) and n.id == "REPORTER_WRITE_PATH_RE"
    ]
    assert hits, "Red — authorize 안에서 REPORTER_WRITE_PATH_RE 를 쓰지 않는다"

    for hit in hits:
        node: ast.AST | None = hit
        tests: list[str] = []
        while node is not None and node is not fn:
            parent = parents.get(id(node))
            if isinstance(parent, ast.If):
                tests.append(ast.unparse(parent.test))
            node = parent
        # 평면 형태: 자기 자신이 속한 If 의 test 에 POST 가 함께 있다.
        assert any("POST" in t for t in tests), (
            f"경로 검사가 POST 조건 없이 쓰인다(조상 if 테스트: {tests})"
        )


def test_reporter_write_path_when_matched_then_uses_fullmatch_on_bare_path():
    """G-249-15 (M03b 봉인) — 경로 검사는 `REPORTER_WRITE_PATH_RE.fullmatch(path)` **단 1회**.

    `REPORTER_WRITE_PATH_RE` 는 `^…\\Z` 양끝 앵커라 `.search()` 로 바꿔도 매치 결과는
    똑같다(행위 등가) — 그래서 R-9 류 행위 테스트로는 이 뮤테이션이 안 죽는다.
    docstring 은 `.fullmatch()` 를 계약으로 적어 두면서도 코드에는 앵커·메서드 이름
    둘 중 하나만 살아도 안전하다는 이중 방어가 없었다(cycle249 뮤테이션 렌즈 M03b
    escape). 여기서 **구조**를 못박는다 — `authorize` 안에서 `REPORTER_WRITE_PATH_RE`
    를 참조하는 호출은 정확히 1개이고, 그 호출은 `.fullmatch(path)` 여야 한다(인자는
    가공 없는 `path` 그대로 — `path.rstrip(...)`/`path.lower()` 류 전처리도 함께
    막는다, M58 동형).
    """
    fn = _func(_tree(_MIDDLEWARE), "authorize")

    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and any(
            isinstance(m, ast.Name) and m.id == "REPORTER_WRITE_PATH_RE"
            for m in ast.walk(n.func)
        )
    ]
    assert len(calls) == 1, (
        f"REPORTER_WRITE_PATH_RE 를 참조하는 호출이 1개가 아니다: "
        f"{[ast.unparse(c) for c in calls]}"
    )
    call = calls[0]

    func = call.func
    assert isinstance(func, ast.Attribute), f"메서드 호출 형태가 아니다: {ast.unparse(call)}"
    assert isinstance(func.value, ast.Name) and func.value.id == "REPORTER_WRITE_PATH_RE", (
        f"수신자가 REPORTER_WRITE_PATH_RE 가 아니다: {ast.unparse(call)}"
    )
    assert func.attr == "fullmatch", (
        f"`.fullmatch` 가 아니라 `.{func.attr}` 를 쓴다(`.search`/`.match` 는 앵커에만 "
        f"기댄 무가드 등가 치환이다): {ast.unparse(call)}"
    )

    assert len(call.args) == 1 and not call.keywords, (
        f"인자 형태가 `(path)` 단일이 아니다: {ast.unparse(call)}"
    )
    arg = call.args[0]
    assert isinstance(arg, ast.Name) and arg.id == "path", (
        f"인자가 가공 없는 `path` 가 아니다(전처리 삽입 여지): {ast.unparse(call)}"
    )

    fn_src = ast.unparse(fn)
    assert ".search(" not in fn_src, f".search 잔존: {fn_src}"
    assert ".match(" not in fn_src, f".match 잔존(앵커 없는 부분매치 여지): {fn_src}"


def _authorize_body_source(fn: ast.FunctionDef) -> str:
    """`authorize` 함수 본문을 **docstring 없이** 소스로 되돌린다.

    cycle249 뮤테이션 렌즈 확증(MEDIUM) — `ast.unparse(fn)` 은 함수의 docstring 도
    문자열 리터럴 `Expr` 로 포함하는데, `authorize` 의 docstring 자체가 §2 설명 중
    예시로 `compare_digest("", "")` 라는 리터럴을 담고 있다. 옛 검사는 "`reporter` 를
    포함하지 않는 첫 `compare_digest(...)` 호출" 을 운영 키 비교로 오인했는데, 그
    docstring 리터럴이 실제 코드보다 **앞**에 위치해 항상 `op_cmp` 로 뽑혀 리포터
    분기를 통째로 앞으로 옮기는 뮤테이션(M01)이 걸리지 않았다(standalone 재현 —
    `op_cmp=380`(docstring) `< rep_cmp` 가 실제 코드 순서와 무관하게 항상 참).
    docstring 을 명시적으로 잘라내 이 함정을 구조적으로 제거한다.
    """
    body = fn.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


def _reporter_branch_positions(body_src: str) -> tuple[int, int]:
    """(운영 키 비교 위치, 리포터 키 비교 위치) — `provided,` 인자로 대상을 특정한다.

    `[^)]*` 전수 매치 대신 `compare_digest\\(provided,\\s*key\\.encode` /
    `…reporter_key\\.encode` 로 **어느 변수와 비교하는지** 를 정규식 자체에 새겨,
    docstring 이든 주석이든 실제 비교 호출이 아니면 애초에 매치되지 않게 한다.
    """
    op = re.search(r"compare_digest\(provided,\s*key\.encode", body_src)
    rep = re.search(r"compare_digest\(provided,\s*reporter_key\.encode", body_src)
    assert op, f"운영 키 비교(`compare_digest(provided, key.encode…)`)를 찾지 못했다: {body_src}"
    assert rep, f"리포터 키 비교(`compare_digest(provided, reporter_key.encode…)`)를 찾지 못했다: {body_src}"
    return op.start(), rep.start()


def test_reporter_branch_when_ordered_then_after_operator_branch():
    """G-249-3 — 리포터 판정은 운영자 판정 **뒤**.

    순서가 뒤집히면 (a) 두 키가 같은 값일 때 운영자가 403 이 되고 (b) 운영자 요청도
    리포터 규칙을 먼저 통과해야 해 판정 비용·표면이 늘어난다. 명세 §B 의 판정 순서
    5단계가 코드 순서로 남아야 한다.
    """
    fn = _func(_tree(_MIDDLEWARE), "authorize")
    fn_src_full = ast.unparse(fn)
    assert "api_reporter_key" in fn_src_full, "Red — authorize 가 settings.api_reporter_key 를 읽지 않는다"

    # docstring 을 배제한 본문만 본다(위 헬퍼 docstring 참조 — decoy 리터럴 함정 시정).
    body_src = _authorize_body_source(fn)
    op_cmp, rep_cmp = _reporter_branch_positions(body_src)
    assert op_cmp < rep_cmp, (
        "리포터 분기가 운영자 분기보다 앞에 있다 — 두 키가 같은 값이면 운영자가 403 이 된다"
    )

    # 경로 검사는 리포터 키 비교 **뒤**에 있어야 한다(스코프가 키와 분리되면 안 된다).
    path_pos = body_src.find("REPORTER_WRITE_PATH_RE")
    assert path_pos > rep_cmp, "경로 스코프 검사가 리포터 키 판정보다 앞에 있다"


def test_reporter_branch_guard_when_docstring_has_decoy_literal_then_not_fooled():
    """G-249-3 회귀 — 뮤테이션 렌즈 M01 escape 재현 + 시정 확인.

    `authorize` 의 실제 docstring 이 `compare_digest("", "")` 리터럴을 담고 있음을
    먼저 확인한다(전제 성립 — 이 규약이 사라지면 아래 반증도 의미를 잃는다). 그 다음
    (a) **옛 방식**(docstring 포함 전체 unparse 에서 `reporter` 미포함 첫 매치를 운영
    비교로 오인)은 리포터 분기가 실제로 **앞**에 있는 뮤테이션에서도 순서가 옳다고
    오판함을 재현하고, (b) 이 파일이 실제로 쓰는 `_authorize_body_source` +
    `_reporter_branch_positions`(docstring 배제 + `provided,` 특정)는 같은 입력에서
    위반을 정확히 검출함을 증명한다.
    """
    real_docstring = ast.get_docstring(_func(_tree(_MIDDLEWARE), "authorize")) or ""
    assert 'compare_digest("", "")' in real_docstring, (
        "전제 붕괴 — authorize docstring 이 더 이상 decoy 리터럴을 담지 않는다"
        "(이 회귀 테스트를 재검토하라)"
    )

    # 뮤테이션 M01 모양 — 리포터 분기가 운영자 분기보다 **앞**. docstring 에는 실제
    # docstring 과 동형의 decoy 리터럴을 심는다(standalone 재현).
    mutated_src = (
        "def authorize(scope):\n"
        '    """decoy: `compare_digest("", "")` 는 True 다."""\n'
        "    reporter_key = settings.api_reporter_key\n"
        "    if reporter_key and secrets.compare_digest(provided, reporter_key.encode('utf-8')):\n"
        "        return ''\n"
        "    if secrets.compare_digest(provided, key.encode('utf-8')):\n"
        "        return ''\n"
        "    return REASON_BAD_KEY\n"
    )
    fn = ast.parse(mutated_src).body[0]
    assert isinstance(fn, ast.FunctionDef)

    # (a) 옛 방식 재현 — decoy 에 속아 "운영 비교가 먼저"라고 오판한다(원래 escape).
    naive_src = ast.unparse(fn)
    naive_compares = [
        (m.start(), m.group(0)) for m in re.finditer(r"compare_digest\([^)]*\)", naive_src)
    ]
    naive_op = next((pos for pos, s in naive_compares if "reporter" not in s), None)
    naive_rep = next((pos for pos, s in naive_compares if "reporter" in s), None)
    assert naive_op is not None and naive_rep is not None, naive_compares
    assert naive_op < naive_rep, (
        "반증 전제 붕괴 — naive 방식이 더 이상 decoy 에 속지 않는다(재확인 필요)"
    )

    # (b) 이 파일이 실제로 쓰는 방식 — 같은 뮤테이션에서 위반을 정확히 잡는다.
    body_src = _authorize_body_source(fn)
    op_pos, rep_pos = _reporter_branch_positions(body_src)
    assert rep_pos < op_pos, (
        "고쳐진 추출도 decoy 에 속았다 — G-249-3 이 다시 공허해졌다(회귀)"
    )


def test_reporter_key_when_empty_then_short_circuited_before_compare():
    """G-249-4 — 빈 리포터 키는 **비교 자체를 하지 않는다**.

    `secrets.compare_digest("", "")` 는 True 다. 기본값이 빈 문자열이므로 이 선분기가
    없으면 **아무것도 설정하지 않은 운영 상태**에서 빈 `X-API-Key` 헤더가 리포터로
    승격된다(cycle243 §2.3.3 의 운영 키 함정과 정확히 동형).
    """
    fn_src = ast.unparse(_func(_tree(_MIDDLEWARE), "authorize"))

    cmp_match = re.search(r"compare_digest\([^)]*reporter[^)]*\)", fn_src)
    assert cmp_match, (
        "Red — 리포터 키를 compare_digest 로 상수시간 비교하는 곳이 없다"
        "(`==` 는 타이밍 사이드채널이다)"
    )

    guards = [
        m.start()
        for m in re.finditer(r"not\s+\w*reporter\w*|\w*reporter\w*\w*\s+and\s+", fn_src)
    ]
    guards = [g for g in guards if g < cmp_match.start()]
    assert guards, (
        "빈 리포터 키 선분기가 비교보다 앞에 없다 — compare_digest('','') 함정"
    )


def test_reason_set_when_extended_then_five_including_reporter_scope():
    """G-249-5 — `REASONS` 5종 + `REASON_REPORTER_SCOPE` 상수.

    사유 집합이 열리면 `_log_reject` 의 cap 키가 무제한으로 늘어난다(인터넷 노출면).
    """
    tree = _tree(_MIDDLEWARE)
    src = _read(_MIDDLEWARE)
    assert re.search(r'REASON_REPORTER_SCOPE\s*=\s*"reporter_scope"', src), src[:0] or "상수 없음"

    reasons_src = ast.unparse(_module_assign(tree, "REASONS"))
    for name in (
        "REASON_NO_KEY",
        "REASON_MISSING_HEADER",
        "REASON_BAD_KEY",
        "REASON_CROSS_ORIGIN",
        "REASON_REPORTER_SCOPE",
    ):
        assert name in reasons_src, f"REASONS 에 {name} 누락: {reasons_src}"
    assert reasons_src.count(",") >= 4, reasons_src


def test_reporter_read_methods_when_declared_then_no_post():
    """G-249-6 — `REPORTER_READ_METHODS` 리터럴에 POST 가 없다.

    여기 POST 를 넣는 한 줄이 스코프 전체를 무력화한다(모든 상태변경 통과).
    """
    value_src = ast.unparse(_module_assign(_tree(_MIDDLEWARE), "REPORTER_READ_METHODS"))
    assert "'GET'" in value_src or '"GET"' in value_src, value_src
    assert "'HEAD'" in value_src or '"HEAD"' in value_src, value_src
    assert "POST" not in value_src, f"READ 집합에 POST 가 있다: {value_src}"
    assert "frozenset" in value_src, f"가변 집합은 런타임 오염 표면이다: {value_src}"


def test_reporter_scope_when_rejected_then_403_not_401():
    """G-249-7 — `reporter_scope` 만 403 으로 갈라진다.

    401 로 뭉개면 루틴 운영자가 "키가 틀렸나 / 권한이 없나" 를 구분하지 못한다. 반대로
    모르는 키에까지 403 을 주면 **유효 키 보유**를 공격자에게 알려 준다 — 그래서 이
    사유 하나만 403 이다.
    """
    tree = _tree(_MIDDLEWARE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ApiAuthMiddleware":
            cls_src = ast.unparse(node)
            break
    else:  # pragma: no cover
        pytest.fail("ApiAuthMiddleware 클래스가 없다")

    assert "403" in cls_src, "403 분기가 없다"
    assert "REASON_REPORTER_SCOPE" in cls_src, "403 분기가 사유 상수와 묶여 있지 않다"
    assert "forbidden" in _read(_MIDDLEWARE), '403 바디 message="forbidden" 누락'


def test_authorize_when_scoped_then_still_module_level_seam():
    """G-249-8 — `authorize` 는 여전히 **모듈 레벨 함수**(cycle243 D-12 계약 유지).

    스코프 추가를 핑계로 메서드로 감추면 `tests/conftest.py::_neutralize_api_auth` 가
    갈아끼울 대상이 사라져 스위트 수백 케이스가 401 로 전멸한다.
    """
    _func(_tree(_MIDDLEWARE), "authorize")


def test_config_when_extended_then_reporter_key_defaults_empty():
    """G-249-9 — `api_reporter_key: str = ""` — 기본값 = 리포터 역할 **비활성**.

    커밋된 개발용 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값이다(cycle243 금기 d).
    """
    src = _read(_CONFIG)
    assert re.search(r'api_reporter_key\s*:\s*str\s*=\s*""', src), (
        "Red — src/config.py 에 `api_reporter_key: str = \"\"` 가 없다"
    )


# ---------------------------------------------------------------------------
# G-249-10 — 라우트 선언 순서
# ---------------------------------------------------------------------------
def test_routes_when_declared_then_bundle_before_target_date():
    """G-249-10 — `/bundle` 이 `/{target_date}` 보다 **먼저** 선언된다.

    FastAPI 는 선언 순서로 매칭한다. 뒤에 두면 `get_report("bundle")` 이 실행돼
    `success=False, "날짜 형식 오류"` 라는 **그럴듯한 200** 이 나가고, 루틴은 매일
    빈손으로 돌아간다(HTTP 오류가 아니라 재시도도 안 걸린다).
    """
    tree = _tree(_ROUTES)
    decorated: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                src = ast.unparse(deco)
                m = re.search(r'\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]*)', src)
                if m:
                    decorated.append((deco.lineno, m.group(2)))
    decorated.sort()
    paths = [p for _, p in decorated]

    assert "/bundle" in paths, "Red — GET /api/log-reports/bundle 미구현"
    assert "/{target_date}" in paths, paths
    assert paths.index("/bundle") < paths.index("/{target_date}"), (
        f"선언 순서 위반 — bundle 이 {{target_date}} 뒤에 있다: {paths}"
    )
    assert "/{target_date}/external" in paths, "Red — POST external 라우트 미구현"


# ---------------------------------------------------------------------------
# G-249-11 ~ G-249-13 — 배포 자산
# ---------------------------------------------------------------------------
def test_env_example_when_updated_then_reporter_key_present_and_empty():
    """G-249-11 — `.env.example` 에 `API_REPORTER_KEY=`(빈 값).

    값을 적어 두면 그게 곧 프로덕션에 시도될 기본키다. 이름만 남겨 운영자가 존재를
    알게 하고, 채우는 것은 배포 절차의 몫이다.
    """
    lines = [ln.strip() for ln in _read(_ENV_EXAMPLE).splitlines()]
    assert "API_REPORTER_KEY=" in lines, (
        "Red — .env.example 에 `API_REPORTER_KEY=` 줄이 없다(값 없이 이름만)"
    )


def test_compose_when_updated_then_frontend_gets_reporter_key_only():
    """G-249-12 — compose frontend 만 `API_REPORTER_KEY` 를 받고, FILTER 가 2변수 앵커.

    * backend 블록 무접촉이 계약이다(cycle243 D-5/D-16 — backend 를 건드리면 컨테이너가
      재생성돼 장중 배포가 tick blind 를 만든다).
    * `NGINX_ENVSUBST_FILTER` 는 앵커된 형태여야 한다 — 앵커가 없으면 부분 일치로
      `API_AUTH_KEY_OLD` 류까지 치환 대상이 되어 유출 표면이 넓어진다.
    """
    text = _read(_COMPOSE)

    m = re.search(r"NGINX_ENVSUBST_FILTER=(\S+)", text)
    assert m, "docker-compose.prod.yml 에 NGINX_ENVSUBST_FILTER 가 없다"
    assert m.group(1) == "^API_(AUTH|REPORTER)_KEY" + _D, (
        f"FILTER 가 앵커된 2변수 형태가 아니다: {m.group(1)!r}"
    )

    # 서비스 블록 분리 — backend 에 리포터 키가 새지 않았는지 본다.
    fe_idx = text.find("\n  frontend:")
    be_idx = text.find("\n  backend:")
    assert fe_idx > 0 and be_idx >= 0, text[:200]
    backend_block = text[be_idx:fe_idx] if be_idx < fe_idx else text[be_idx:]
    frontend_block = text[fe_idx:]

    assert "API_REPORTER_KEY=" + _D + "{API_REPORTER_KEY}" in frontend_block, (
        "Red — frontend environment 에 API_REPORTER_KEY 전달 줄이 없다"
    )
    assert "API_REPORTER_KEY" not in backend_block, (
        "backend 블록이 오염됐다 — 컨테이너 재생성(장중 tick blind) 위험"
    )


def test_nginx_template_when_mapped_then_per_user_key_injection():
    """G-249-13 — `map $remote_user $api_key_for_user` 가 사용자별 키를 고른다.

    nginx 가 클라이언트의 `X-API-Key` 를 **치환**하므로(cycle243) "루틴이 스코프 키를
    보낸다" 는 설계는 성립하지 않는다. 스코프의 출발점은 Basic 사용자다.
    default/reporter 가 뒤바뀌면 리포터 사용자가 **운영 키**를 받아 스코프가 통째로
    사라지는데, 모든 요청이 정상 200 이라 관측으로는 절대 드러나지 않는다.

    치환 구문 총량 규약(cycle246)도 함께 지킨다 — 각 변수는 **정확히 1회**, 그리고
    그 1회는 map 블록 안이다(렌더된 설정 주석에 키가 평문으로 박히는 유출 재발 방지).
    """
    text = _read(_TEMPLATE)
    lines = text.splitlines()

    map_start = next(
        (
            i
            for i, ln in enumerate(lines)
            if re.match(
                r"\s*map\s+" + re.escape(_VAR_REMOTE_USER) + r"\s+" + re.escape(_VAR_PER_USER) + r"\s*\{",
                ln,
            )
        ),
        None,
    )
    assert map_start is not None, (
        "Red — nginx 템플릿에 `map (remote_user) (api_key_for_user) {` 블록이 없다"
    )

    server_idx = next((i for i, ln in enumerate(lines) if re.match(r"\s*server\s*\{", ln)), None)
    assert server_idx is not None and map_start < server_idx, (
        "map 은 http 컨텍스트(server 블록 밖·앞)에 있어야 한다"
    )

    map_end = next(
        (i for i in range(map_start + 1, len(lines)) if lines[i].strip() == "}"), None
    )
    assert map_end is not None, "map 블록이 닫히지 않았다"
    block = lines[map_start : map_end + 1]

    default_lines = [ln for ln in block if ln.strip().startswith("default")]
    reporter_lines = [ln for ln in block if ln.strip().startswith("reporter")]
    assert len(default_lines) == 1, f"map default 줄이 1개가 아니다: {default_lines}"
    assert len(reporter_lines) == 1, f"map reporter 줄이 1개가 아니다: {reporter_lines}"
    assert _SUBST_AUTH in default_lines[0] and _SUBST_REPORTER not in default_lines[0], (
        f"default 가 운영 키를 가리키지 않는다: {default_lines[0]!r}"
    )
    assert _SUBST_REPORTER in reporter_lines[0] and _SUBST_AUTH not in reporter_lines[0], (
        f"reporter 가 리포터 키를 가리키지 않는다: {reporter_lines[0]!r}"
    )

    # 치환 구문 총량 — 각 1회, 그리고 그 1회는 map 블록 안.
    for subst in (_SUBST_AUTH, _SUBST_REPORTER):
        hits = [(i + 1, ln) for i, ln in enumerate(lines) if subst in ln]
        assert len(hits) == 1, f"치환 구문이 1회가 아니다(cycle246 유출): {hits}"
        assert map_start + 1 <= hits[0][0] <= map_end + 1, (
            f"치환 구문이 map 블록 밖에 있다: {hits}"
        )

    header_lines = [ln for ln in lines if "proxy_set_header X-API-Key" in ln]
    assert len(header_lines) == 1, f"X-API-Key 주입 줄이 1개가 아니다: {header_lines}"
    assert _VAR_PER_USER in header_lines[0], (
        f"주입 줄이 사용자별 변수를 쓰지 않는다: {header_lines[0]!r}"
    )
    assert _D + "{" not in header_lines[0], (
        f"주입 줄에 치환 구문이 남아 있다(렌더 결과에 키가 박힌다): {header_lines[0]!r}"
    )


# ---------------------------------------------------------------------------
# G-249-14 — 마이그레이션 042
# ---------------------------------------------------------------------------
def test_migration_042_when_added_then_six_nullable_columns():
    """G-249-14 — 042 는 `ADD COLUMN IF NOT EXISTS` 6개 · **전부 NULL 허용**.

    기존 행(과거 전 영업일)은 ext_* 가 없다. NOT NULL 을 붙이면 DEFAULT 없이는
    마이그레이션 자체가 실패하고, DEFAULT 를 붙이면 "외부 분석이 있었다" 는 거짓
    사실이 전 과거 행에 심긴다. `IF NOT EXISTS` 는 deploy.yml 이 매 push 마다 전
    마이그레이션을 재적용하기 때문에 필수다(031 선례).
    """
    sql = _read(_MIGRATION)
    upper = sql.upper()

    assert "DAILY_LOG_REPORTS" in upper, sql
    for col in EXT_COLUMNS:
        pat = re.compile(
            r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+" + col + r"\s+([A-Z]+(?:\s*\([^)]*\))?)\s*(NULL)?",
            re.I,
        )
        m = pat.search(sql)
        assert m, f"`ADD COLUMN IF NOT EXISTS {col} …` 이 없다"

    assert not re.search(r"NOT\s+NULL", sql, re.I), (
        "NOT NULL 컬럼은 기존 행 보존을 깨뜨린다(전부 NULL 허용이 계약)"
    )
    assert not re.search(r"\bDROP\b", sql, re.I), "042 는 추가 전용이다"

    # 타입 계약 — findings 는 JSONB, created_at 은 TIMESTAMPTZ.
    assert re.search(r"ext_findings\s+JSONB", sql, re.I), sql
    assert re.search(r"ext_created_at\s+TIMESTAMPTZ", sql, re.I), sql
