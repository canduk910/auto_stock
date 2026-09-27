"""cycle380 Red — ETF 판정 단일 헬퍼 `is_etf_like(raw, name)` 표 검증.

명세 = `_workspace/red/cycle380_etf_group_code.md` §2 (사용자 결정 2026-09-27
「운영db 조회 허용 및 판정 변경 채택」).

계약:
- 모듈 = **신규 leaf** `src/engine/etf_like.py` (표준 라이브러리만 import — `src.db.stock_master`
  SQL 빌더도 같은 상수를 읽어야 하므로 scanner(8영역·무거운 import)에 두지 않는다).
- `ETF_GROUP_CODES == frozenset({"EF", "EN", "FE"})` — KIS CTPF1002R #7 `scty_grp_id_cd`
  (EF=ETF · EN=ETN · FE=해외ETF). `order_engine._observe_after_exit_etp` 와 같은 집합.
- `ETF_KEYWORDS` = scanner 에 있던 25개 이름 키워드 **그대로**(이번 사이클은 폴백 규칙을 바꾸지 않는다).
- `is_etf_like(raw, name) -> bool`:
    * `raw` 가 dict 이고 `raw["scty_grp_id_cd"]` 가 None 이 아니며 `str(v).strip()` 가 비어 있지
      않으면 → `str(v).strip().upper() in ETF_GROUP_CODES` 로 **코드만** 판정한다(이름 무시).
    * 그 밖(raw None·dict 아님·키 없음·None·빈 문자열·공백) → 기존 이름 규칙
      `any(kw in (name or "") for kw in ETF_KEYWORDS)` (대소문자 구분 부분일치 = 현행 그대로).

운영 DB 실측(2026-09-27 읽기 전용, 3,583행 전부 채워짐): ST 2661 · EF 873 · RT 24 · FS 12 · DR 10 ·
IF 2 · MF 1. 이름 규칙이 놓치는 EF 87종(KIWOOM·TIME·1Q·MIDAS·UNICORN·에셋플러스·파워·KCGI…),
이름 규칙이 잘못 막는 ST 2종(YG PLUS·BNK금융지주). 아래 표본은 그 실측 행 그대로다.

## HEAD 기준

전부 RED — `src.engine.etf_like` 부재(ImportError).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_LEAF_REL = "src/engine/etf_like.py"

# scanner.py:494-497 (HEAD d644ea68) 의 25개 — 폴백 규칙의 정본 스냅숏.
_OLD_KEYWORDS = (
    "KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
    "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
    "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
    "ETN", "선물", "인버스", "레버리지", "채권", "혼합",
)


def _old_rule(name: str | None) -> bool:
    return any(kw in (name or "") for kw in _OLD_KEYWORDS)


def _helper():
    from src.engine.etf_like import is_etf_like

    return is_etf_like


# ---------------------------------------------------------------------------
# 1. 상수
# ---------------------------------------------------------------------------
def test_group_codes_are_exactly_ef_en_fe():
    from src.engine.etf_like import ETF_GROUP_CODES

    assert isinstance(ETF_GROUP_CODES, frozenset)
    assert ETF_GROUP_CODES == frozenset({"EF", "EN", "FE"})


def test_fallback_keywords_unchanged_this_cycle():
    """폴백 키워드는 이번 사이클에 한 글자도 바뀌지 않는다(순서 포함) — 폴백 = 기존 규칙."""
    from src.engine.etf_like import ETF_KEYWORDS

    assert tuple(ETF_KEYWORDS) == _OLD_KEYWORDS


# ---------------------------------------------------------------------------
# 2. 코드가 있으면 코드만 본다
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", ["EF", "EN", "FE"])
def test_etf_codes_are_etf_even_with_plain_stock_name(code):
    is_etf_like = _helper()
    assert is_etf_like({"scty_grp_id_cd": code}, "삼성전자") is True


@pytest.mark.parametrize("code", ["ST", "RT", "FS", "DR", "IF", "MF"])
def test_non_etf_codes_are_not_etf_even_with_etf_keyword_name(code):
    """이름에 ETF 키워드가 있어도 코드가 주식류면 ETF 가 아니다(코드 > 이름)."""
    is_etf_like = _helper()
    assert is_etf_like({"scty_grp_id_cd": code}, "KODEX 200 PLUS 레버리지") is False


@pytest.mark.parametrize(
    "code",
    ["ef", "Ef", " EF ", "\tEN\n", " fe", "en ", "fE"],
)
def test_code_is_stripped_and_uppercased(code):
    is_etf_like = _helper()
    assert is_etf_like({"scty_grp_id_cd": code}, "삼성전자") is True


@pytest.mark.parametrize("code", ["st", " ST ", "rt\n", " if "])
def test_non_etf_code_variants_stay_non_etf(code):
    is_etf_like = _helper()
    assert is_etf_like({"scty_grp_id_cd": code}, "KODEX 200") is False


# ---------------------------------------------------------------------------
# 3. 코드가 없으면 기존 이름 규칙(폴백)
# ---------------------------------------------------------------------------
_MISSING_RAWS = [
    None,
    {},
    {"hts_avls": "1000"},
    {"scty_grp_id_cd": None},
    {"scty_grp_id_cd": ""},
    {"scty_grp_id_cd": "   "},
    {"scty_grp_id_cd": "\n"},
    "not-a-dict",
    ["EF"],
]


@pytest.mark.parametrize("raw", _MISSING_RAWS, ids=repr)
def test_missing_code_falls_back_to_name_keyword_etf(raw):
    is_etf_like = _helper()
    assert is_etf_like(raw, "TIGER 200") is True


@pytest.mark.parametrize("raw", _MISSING_RAWS, ids=repr)
def test_missing_code_falls_back_to_name_keyword_stock(raw):
    is_etf_like = _helper()
    assert is_etf_like(raw, "삼성전자") is False


@pytest.mark.parametrize("name", [None, ""])
def test_missing_code_and_missing_name_is_not_etf(name):
    is_etf_like = _helper()
    assert is_etf_like(None, name) is False
    assert is_etf_like({}, name) is False


_FALLBACK_NAMES = [
    *[f"샘플{kw}종목" for kw in _OLD_KEYWORDS],       # 25개 키워드 각각 부분일치
    "kodex 200",                                      # 대소문자 구분(현행 그대로 = 미적중)
    "Kodex 200",
    "koact 배당",
    "YG PLUS",
    "BNK금융지주",
    "KIWOOM 코스피100",
    "TIME 미국나스닥100액티브",
    "삼성전자",
    "SK리츠",
    "",
]


@pytest.mark.parametrize("name", _FALLBACK_NAMES)
def test_fallback_equals_old_rule_exactly(name):
    """폴백은 기존 `any(kw in name for kw in ETF_KEYWORDS)` 와 한 이름도 다르지 않다."""
    is_etf_like = _helper()
    assert is_etf_like(None, name) is _old_rule(name)
    assert is_etf_like({}, name) is _old_rule(name)


# ---------------------------------------------------------------------------
# 4. 운영 DB 실측 행(2026-09-27) — 새던 ETF 는 막히고, 잘못 막히던 주식은 풀린다
# ---------------------------------------------------------------------------
_LEAKED_EF = [
    ("491610", "1Q CD금리액티브(합성)"),
    ("153270", "KIWOOM 코스피100"),
    ("426030", "TIME 미국나스닥100액티브"),
    ("438740", "MIDAS 중소형액티브"),
    ("472720", "TRUSTON 주주가치액티브"),
    ("476000", "UNICORN 포스트IPO액티브"),
    ("451150", "에셋플러스 글로벌영에이지액티브"),
    ("152870", "파워 200"),
    ("483570", "KCGI 미국S&P500 TOP10"),
]


@pytest.mark.parametrize("ticker,name", _LEAKED_EF)
def test_rebranded_etf_is_excluded_by_code(ticker, name):
    is_etf_like = _helper()
    assert _old_rule(name) is False, f"표본 전제: 이름 규칙이 {name} 을 놓친다"
    assert is_etf_like({"scty_grp_id_cd": "EF"}, name) is True


@pytest.mark.parametrize("ticker,name", [("037270", "YG PLUS"), ("138930", "BNK금융지주")])
def test_stock_with_etf_keyword_in_name_is_allowed_by_code(ticker, name):
    is_etf_like = _helper()
    assert _old_rule(name) is True, f"표본 전제: 이름 규칙이 {name} 을 잘못 막는다"
    assert is_etf_like({"scty_grp_id_cd": "ST"}, name) is False


@pytest.mark.parametrize(
    "grp,name",
    [
        ("RT", "SK리츠"),
        ("RT", "KB스타리츠"),
        ("IF", "맥쿼리인프라"),
        ("DR", "인제니아테라퓨틱스(Reg.S)"),
        ("FS", "로스웰"),
        ("MF", "맵스리얼티"),
    ],
)
def test_other_groups_unchanged_not_etf(grp, name):
    """RT/FS/DR/IF/MF 는 이번 사이클 범위 밖 — 전과 같이 ETF 로 보지 않는다."""
    is_etf_like = _helper()
    assert _old_rule(name) is False
    assert is_etf_like({"scty_grp_id_cd": grp}, name) is False


def test_returns_real_bool():
    is_etf_like = _helper()
    for raw, name in [({"scty_grp_id_cd": "EF"}, "x"), ({"scty_grp_id_cd": "ST"}, "x"),
                      (None, "KODEX"), (None, "삼성전자")]:
        assert type(is_etf_like(raw, name)) is bool


def test_does_not_mutate_raw():
    is_etf_like = _helper()
    raw = {"scty_grp_id_cd": " ef ", "hts_avls": "1"}
    snapshot = dict(raw)
    is_etf_like(raw, "삼성전자")
    assert raw == snapshot


# ---------------------------------------------------------------------------
# 5. leaf 순수성 — db 계층이 import 해도 무겁지 않고 순환이 없다
# ---------------------------------------------------------------------------
def test_leaf_imports_stdlib_only_and_is_sync():
    path = _ROOT / _LEAF_REL
    assert path.exists(), f"{_LEAF_REL} 이 없다"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("src"), f"leaf 가 {mod} 를 import 한다"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("src"), f"leaf 가 {alias.name} 를 import 한다"
        assert not isinstance(node, (ast.AsyncFunctionDef, ast.Await)), "leaf 는 동기 순수 함수만"
