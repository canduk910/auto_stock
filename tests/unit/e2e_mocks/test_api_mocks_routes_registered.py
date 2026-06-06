"""사이클 65 hotfix#2 — e2e api-mocks.ts 에 신규 라우트 등록 영구 가드.

사이클 64 `/api/system/price-filter` + 사이클 65 `/api/system/trade-amount-filter`
가 e2e api-mocks.ts 에 와일드카드 `**/api/system/**` *전* 구체 라우트로 등록되어
있는지 검증. envelope({}) 와일드카드 모킹은 React controlled input 결함 유발
(min_price/min_amount undefined → "uncontrolled → controlled" warning + 슬라이더
미렌더 + settings.spec.ts:5 FAIL).

본 가드는 향후 신규 system_config 카드 추가 시 e2e mock 누락 영구 차단.

사이클 60 hotfix H-2 + G-3 / 사이클 64 hotfix H-2 + G-3 / 사이클 65 hotfix H-3
AST 영구 가드 패턴 답습.
"""
from pathlib import Path


def test_e2e_api_mocks_includes_price_filter_specific_route():
    """e2e/fixtures/api-mocks.ts 가 /api/system/price-filter 구체 라우트를 등록 의무.

    사이클 64 PriceFilterCard 가 useEffect 에서 data.min_price 추출 — envelope({})
    와일드카드 응답은 min_price=undefined → React controlled input 결함.
    """
    mocks_path = Path(__file__).parent.parent.parent.parent / "e2e/fixtures/api-mocks.ts"
    source = mocks_path.read_text()
    assert '"**/api/system/price-filter"' in source, (
        "e2e api-mocks.ts 에 /api/system/price-filter 구체 라우트 등록 누락 — "
        "envelope({}) 와일드카드 모킹은 React controlled input 결함 유발 + "
        "settings.spec.ts:5 FAIL. 와일드카드 `**/api/system/**` *전* 등록 의무."
    )


def test_e2e_api_mocks_includes_trade_amount_filter_specific_route():
    """e2e/fixtures/api-mocks.ts 가 /api/system/trade-amount-filter 구체 라우트를 등록 의무.

    사이클 65 TradeAmountFilterCard 가 useEffect 에서 data.min_amount 추출 —
    envelope({}) 와일드카드 응답은 min_amount=undefined → React controlled input
    결함 + 카드 수 임계 초과로 settings.spec.ts:5 FAIL.
    """
    mocks_path = Path(__file__).parent.parent.parent.parent / "e2e/fixtures/api-mocks.ts"
    source = mocks_path.read_text()
    assert '"**/api/system/trade-amount-filter"' in source, (
        "e2e api-mocks.ts 에 /api/system/trade-amount-filter 구체 라우트 등록 누락 — "
        "envelope({}) 와일드카드 모킹은 React controlled input 결함 유발."
    )


def test_e2e_api_mocks_specific_routes_registered_before_wildcard():
    """구체 라우트가 와일드카드 `**/api/system/**` *전* 등록 의무.

    Playwright route 매칭 = 등록 순서대로. 와일드카드 먼저 등록 시 구체 라우트
    매칭 안 됨 → envelope({}) 반환 → 결함.
    """
    mocks_path = Path(__file__).parent.parent.parent.parent / "e2e/fixtures/api-mocks.ts"
    source = mocks_path.read_text()

    price_filter_pos = source.find('"**/api/system/price-filter"')
    trade_amount_filter_pos = source.find('"**/api/system/trade-amount-filter"')
    wildcard_pos = source.find('"**/api/system/**"')

    assert price_filter_pos > 0, "price-filter 구체 라우트 등록 누락"
    assert trade_amount_filter_pos > 0, "trade-amount-filter 구체 라우트 등록 누락"
    assert wildcard_pos > 0, "와일드카드 `**/api/system/**` 라우트 누락"

    assert price_filter_pos < wildcard_pos, (
        f"price-filter 구체 라우트 (pos={price_filter_pos}) 가 와일드카드 "
        f"(pos={wildcard_pos}) *뒤* 등록 — Playwright 매칭 순서 위반"
    )
    assert trade_amount_filter_pos < wildcard_pos, (
        f"trade-amount-filter 구체 라우트 (pos={trade_amount_filter_pos}) 가 와일드카드 "
        f"(pos={wildcard_pos}) *뒤* 등록 — Playwright 매칭 순서 위반"
    )
