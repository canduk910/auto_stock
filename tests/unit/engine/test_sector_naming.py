"""보유 종목 섹터명 해석 단일 진실원 — 회귀 가드.

배경: 섹터명 해석(basics raw `bstp_kor_isnm` 우선 → `_kojiro_sector_key(master_raw)`
폴백 → `미분류-{ticker}`)이 `routes/portfolio.py::_sector_of_graceful` 과
`log_analysis_engine::_build_portfolio_risk_snapshot` 에 **이미 중복**돼 있었다.
잔고 응답에도 섹터가 필요해지면서 세 번째 복사본이 생길 상황이라 단일 모듈로 추출한다.

우선순위 계약(사이클 H Phase 2a + 사이클 I 후속에서 확정, 행위 보존):
  1. `bstp_kor_isnm` — basics raw(CTPF1002R). 전 종목에 채워지는 사람이 읽는 명칭
     ("유통"/"금융"/"전기·전자").
  2. `_kojiro_sector_key(master_raw)` — KRX 산업지수 플래그(반도체/바이오…) →
     업종 대분류코드 → 중분류. kojiro 섹터 캡과 동일 소스(함수 무변경).
  3. `미분류-{ticker}` — 독립 키(클러스터 미포함 = fail-open).

⚠️ `idx_bztp_lcls_cd_name`("시가총액규모중")은 섹터가 아니다 — 사용 금지.
"""

from __future__ import annotations

import pytest

from src.engine import sector_naming

pytestmark = pytest.mark.unit


class _Basics:
    def __init__(self, raw):
        self.raw = raw


@pytest.fixture
def stub(monkeypatch):
    calls = {"get": [], "master": []}

    async def fake_get(ticker):
        calls["get"].append(ticker)
        return _Basics(stub.basics_raw)

    async def fake_master(ticker):
        calls["master"].append(ticker)
        return stub.master_raw

    monkeypatch.setattr(sector_naming.stock_master, "get", fake_get)
    monkeypatch.setattr(sector_naming.stock_master, "get_master_raw", fake_master)
    stub.basics_raw = None
    stub.master_raw = None
    stub.calls = calls
    return stub


# ---------------------------------------------------------------------------
# S-1 — 우선순위 1: bstp_kor_isnm
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prefers_bstp_kor_isnm(stub):
    stub.basics_raw = {"bstp_kor_isnm": "전기·전자"}
    stub.master_raw = {"krx_smcn_yn": "Y"}          # 폴백이 있어도 무시돼야 함
    assert await sector_naming.resolve_sector_name("005930") == "전기·전자"
    assert stub.calls["master"] == [], "1순위 적중 시 master_raw 조회 불필요"


@pytest.mark.asyncio
async def test_blank_isnm_falls_through(stub):
    stub.basics_raw = {"bstp_kor_isnm": "   "}      # 공백만 = 부재 취급
    stub.master_raw = {"krx_bio_yn": "Y"}
    assert await sector_naming.resolve_sector_name("068270") == "바이오"


# ---------------------------------------------------------------------------
# S-2 — 우선순위 2: master_raw → _kojiro_sector_key
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_falls_back_to_krx_flag(stub):
    stub.basics_raw = {}
    stub.master_raw = {"krx_smcn_yn": "Y"}
    assert await sector_naming.resolve_sector_name("000660") == "반도체"


@pytest.mark.asyncio
async def test_falls_back_to_industry_code(stub):
    stub.basics_raw = None
    stub.master_raw = {"bstp_larg_div_code": "0027"}
    assert await sector_naming.resolve_sector_name("002790") == "업종-0027"


# ---------------------------------------------------------------------------
# S-3 — 우선순위 3: 미분류 (fail-open, 독립 키)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unclassified_when_nothing_available(stub):
    stub.basics_raw = None
    stub.master_raw = None
    assert await sector_naming.resolve_sector_name("999999") == "미분류-999999"


@pytest.mark.asyncio
async def test_exception_is_graceful(stub, monkeypatch):
    async def boom(ticker):
        raise RuntimeError("db down")

    monkeypatch.setattr(sector_naming.stock_master, "get", boom)
    assert await sector_naming.resolve_sector_name("005930") == "미분류-005930"


# ---------------------------------------------------------------------------
# S-4 — basics_raw 주입 시 중복 fetch 차단 (잔고 라우트가 이미 조회한 값 재사용)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_injected_basics_raw_skips_refetch(stub):
    stub.master_raw = None
    got = await sector_naming.resolve_sector_name(
        "005930", basics_raw={"bstp_kor_isnm": "유통"},
    )
    assert got == "유통"
    assert stub.calls["get"] == [], "주입된 raw 가 있으면 stock_master.get 재조회 금지"


@pytest.mark.asyncio
async def test_injected_empty_raw_still_uses_master_fallback(stub):
    stub.master_raw = {"krx_bank_yn": "Y"}
    got = await sector_naming.resolve_sector_name("105560", basics_raw={})
    assert got == "은행"
    assert stub.calls["get"] == [], "주입 시엔 basics 재조회 없이 master 폴백만"


# ---------------------------------------------------------------------------
# S-5 — 복수 조회 (기존 `_sector_of_graceful` 계약)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_many_returns_dict(stub):
    stub.basics_raw = {"bstp_kor_isnm": "금융"}
    out = await sector_naming.resolve_sector_names(["105560", "086790"])
    assert out == {"105560": "금융", "086790": "금융"}


@pytest.mark.asyncio
async def test_resolve_many_empty_input(stub):
    assert await sector_naming.resolve_sector_names([]) == {}


# ---------------------------------------------------------------------------
# S-6 — 기존 소비처가 공용 모듈에 위임 (중복 재발 차단)
# ---------------------------------------------------------------------------
def _code_without_docstring(fn) -> str:
    """함수 본문 코드만 (docstring 제외) — 설명 문구가 중복 판정에 걸리지 않게."""
    import ast
    import inspect
    import textwrap

    node = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]      # docstring 제거
    return "\n".join(ast.unparse(stmt) for stmt in body)


def test_portfolio_route_delegates():
    from src.routes import portfolio
    code = _code_without_docstring(portfolio._sector_of_graceful)
    assert "resolve_sector_names" in code, "portfolio 라우트는 공용 모듈에 위임해야 한다"
    assert "bstp_kor_isnm" not in code, "우선순위 로직 중복 금지 (docstring 설명은 허용)"


def test_log_analysis_delegates():
    from src.engine import log_analysis_engine
    code = _code_without_docstring(log_analysis_engine._build_portfolio_risk_snapshot)
    assert "resolve_sector_names" in code, "일일 리포트도 공용 모듈에 위임해야 한다"
    assert "bstp_kor_isnm" not in code, "우선순위 로직 중복 금지 (docstring 설명은 허용)"
