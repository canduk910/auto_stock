"""cycle266 C-3 — 목 3곳이 **실제 응답 모양**(문자열 등락률)을 담는지 영구 가드.

⚠️ **이 파일은 백엔드 테스트지만 프론트엔드 파일을 읽는다** —
`frontend/src/test/handlers.ts` · `frontend/src/pages/__tests__/StockMaster.test.tsx` ·
`e2e/fixtures/api-mocks.ts`. 따라서 프론트 전용 사이클의 검증 목록
(`grep -rl 'frontend/' tests/unit`)에 반드시 포함되어야 한다(cycle256 g251_2/3 관례).

## 왜 이 가드가 필요한가

`GET /api/stock-master/{ticker}/daily` 의 `change_rate` 는 `NUMERIC(8,4)` →
asyncpg `Decimal` → pydantic v2 JSON 모드에서 **문자열**로 나간다. 그런데 목 셋이
전부 `change_rate: parseFloat(...)` 로 **진짜 number** 를 만들어 두어
*의도한 계약*만 검증했고 *실제 응답*은 한 번도 검증하지 않았다.

⇒ 세 목이 나란히 초록인 채로 프로덕션 일봉 탭은 3개월 넘게 흰 화면이었다
(도입 = dc66026, 2026-06-13, 사이클 124).

이 가드는 "목이 실제 응답 모양을 최소 한 케이스라도 담고 있는가" 를 잰다.
**숫자 케이스도 함께 남아 있어야 한다**(cycle266 §C-2 — 백엔드 시정 후의 모양과
방어 변환 전의 모양이 양쪽 다 통과해야 프론트가 스스로 버틴다는 뜻이다).

정본 가드는 백엔드 직렬화 계약
(`tests/unit/routes/test_cycle266_daily_route_serialization.py`)이고, 이 파일은
**목이 다시 거짓말하기 시작하는 것**을 막는 두 번째 방벽이다.

⚠️ Playwright route 는 **LIFO**(사이클 80 hotfix #3) — 이 파일은 라우트 **순서**는
건드리지 않는다. 순서 가드는 `test_cycle85_api_mocks_stock_master_lifo.py` +
`test_cycle124_api_mocks_daily_route.py` 소관이며 그대로 유지된다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]

MSW_HANDLERS = ROOT / "frontend/src/test/handlers.ts"
E2E_MOCKS = ROOT / "e2e/fixtures/api-mocks.ts"
UNIT_MOCK = ROOT / "frontend/src/pages/__tests__/StockMaster.test.tsx"

_MOCK_SITES = pytest.mark.parametrize(
    "path",
    [
        pytest.param(MSW_HANDLERS, id="msw-handlers"),
        pytest.param(E2E_MOCKS, id="e2e-api-mocks"),
        pytest.param(UNIT_MOCK, id="unit-StockMaster.test.tsx"),
    ],
)

# `change_rate: '0.0000'` / `change_rate: "-1.2300"` — 따옴표로 열리는 값
_STRING_CHANGE_RATE = re.compile(r"""change_rate\s*:\s*['"`]""")
# `change_rate: 1.23` / `change_rate: parseFloat(...)` / `change_rate: -0.5`
_NUMERIC_CHANGE_RATE = re.compile(r"""change_rate\s*:\s*(?!['"`])[-+\w(]""")


@_MOCK_SITES
def test_c266_c3_mock_has_string_change_rate(path: Path):
    """C-3: 목 3곳 각각이 `change_rate` **문자열** 케이스를 최소 1건 담는다.

    운영 응답이 바로 그 모양이다. 목이 숫자만 담으면 프론트의 `.toFixed(2)` 크래시가
    영원히 테스트에 안 잡힌다 — 실제로 3개월간 그랬다.
    """
    src = path.read_text(encoding="utf-8")
    assert "change_rate" in src, f"{path} 에 change_rate 목 자체가 없다"
    assert _STRING_CHANGE_RATE.search(src), (
        f"{path.relative_to(ROOT)} 의 change_rate 목이 전부 숫자다 — "
        f"운영 응답은 `\"0.0000\"` 문자열(NUMERIC(8,4) → Decimal → pydantic v2)이다. "
        f"문자열 케이스를 최소 1건 추가하라 (cycle266 §C-3)."
    )


@_MOCK_SITES
def test_c266_c3_mock_keeps_numeric_change_rate(path: Path):
    """C-3: 숫자 케이스도 **함께** 남는다 — 양쪽 다 통과해야 방어가 진짜다.

    백엔드 시정(A-1) 후의 모양이 숫자이므로, 문자열로 통째로 갈아치우면
    시정 후 계약을 아무도 검증하지 않게 된다.
    """
    src = path.read_text(encoding="utf-8")
    assert _NUMERIC_CHANGE_RATE.search(src), (
        f"{path.relative_to(ROOT)} 의 change_rate 목이 전부 문자열이다 — "
        f"백엔드 시정 후 모양(숫자) 케이스도 남겨야 한다 (cycle266 §C-2)."
    )


@_MOCK_SITES
def test_c266_c3_mock_bas_dd_uses_date_format(path: Path):
    """C-3: `bas_dd` 는 `DATE` 컬럼이라 직렬화가 `YYYY-MM-DD` 다 — 목이 그 모양을 담는다.

    세 목 모두 `bas_dd: '20260613'`(YYYYMMDD)을 쓰는데 그것은 KIS 원본 필드 모양이지
    우리 응답 모양이 아니다(migration 033: `bas_dd DATE NOT NULL`).
    프론트 타입 주석의 `YYYYMMDD` 도 같은 거짓말이며 B-2 에서 함께 시정한다.
    """
    src = path.read_text(encoding="utf-8")
    assert "bas_dd" in src, f"{path} 에 bas_dd 목 자체가 없다"
    assert re.search(r"""bas_dd\s*:\s*['"`]\d{4}-\d{2}-\d{2}""", src), (
        f"{path.relative_to(ROOT)} 의 bas_dd 목에 `YYYY-MM-DD` 케이스가 없다 — "
        f"`stock_master_daily.bas_dd` 는 DATE 컬럼이고 응답은 `\"2026-09-05\"` 다."
    )


# ─────────────────────────────────────────────────────────────────────────────
# D-3 (마무리 라운드, tester 적대 검토) — E2E 레인이 일봉 탭을 **실제로 연다**
#
# 종전 8 케이스는 일봉 탭을 한 번도 열지 않았다(`grep -n "daily" e2e/*.spec.ts` = 0건).
# 그래서 목이 정직해져도 E2E 33 초록은 이 결함에 대해 아무 증거도 주지 않는다.
# 아래 가드는 커버리지가 조용히 사라지는 것을 막는다.
#
# ⚠️ 이 블록도 프론트/E2E 파일을 읽는 백엔드 가드다(파일 헤더의 경고와 동일 취지) —
#    `e2e/stock-master.spec.ts`.
# ─────────────────────────────────────────────────────────────────────────────

E2E_SPEC = ROOT / "e2e/stock-master.spec.ts"


def test_c266_d3_e2e_spec_opens_the_daily_tab():
    """D-3: E2E spec 이 일봉 탭 전환 + 표 가시성을 실제로 잰다."""
    src = E2E_SPEC.read_text(encoding="utf-8")

    for token in ("stock-master-tab-daily", "stock-master-daily-table"):
        assert token in src, (
            f"E2E spec 이 `{token}` 을 쓰지 않는다 — 일봉 탭을 열지 않는 E2E 는 "
            f"이 결함에 대해 초록 거짓말만 한다(D-3)."
        )


def test_c266_d3_e2e_spec_asserts_string_change_rate_rendering():
    """D-3: 문자열 등락률(`"1.2000"`)의 **렌더 결과**까지 단언한다.

    표가 보이기만 하는 단언은 `'—'` 로 전부 퉁치는 구현도 통과시킨다.
    """
    src = E2E_SPEC.read_text(encoding="utf-8")

    assert "+1.20%" in src, (
        "E2E 가 문자열 등락률의 렌더 결과를 재지 않는다 — 목 첫 행 "
        '`change_rate: "1.2000"` 이 `+1.20%` 로 나오는지가 흰 화면 재발의 신호다(D-3).'
    )
    assert "+0.90%" in src, (
        "숫자 등락률(A-1 시정 후의 모양)도 함께 통과해야 한다(§C-2)."
    )
