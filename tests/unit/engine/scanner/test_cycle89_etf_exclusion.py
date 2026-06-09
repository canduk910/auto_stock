"""사이클 89 H-2 — ETF/리츠/SPAC 자동 제외 검증.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- A2 권고 영속: ETF/리츠/우선주/SPAC 자동 제외 의무
- KIS CTPF1002R `prdt_type_cd` 키 활용 (보통주 = "300" / ETF = "301" / 리츠 = "302")
  또는 종목코드 패턴 (KODEX/TIGER prefix)
- 신규 헬퍼 `_universe_filter_securities_only(rows)` 도입

기대 동작 (Green, 사이클 90):
- mock 응답 = 보통주 495건 + ETF 5건 → 결과 = 495건 (ETF 0건)
- mock 응답 = 보통주 + KODEX 200 + TIGER + 리츠 + SPAC → 보통주만 통과

Red 단계 (사이클 89): 신규 헬퍼 `_universe_filter_securities_only` 미존재
→ ImportError → FAIL.

영속 의무:
- A2 권고 (ETF/리츠/우선주/SPAC 자동 제외 의무)
- 6 전략 부적합 종목 차단 (momentum 상한가 / VB 변동성 / VCP 수렴 모두 부적합)
- 매매 안전성 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_h2_universe_filter_excludes_etf_reits_spac():
    """H-2: `_universe_filter_securities_only` 가 ETF/리츠/SPAC 자동 제외.

    검증 매트릭스:
    - mock 응답: 보통주 5건 + ETF 5건 + 리츠 2건 + SPAC 1건
    - 결과: 보통주 5건만 통과 (ETF/리츠/SPAC 0건)

    Red 상태 (사이클 89): 신규 헬퍼 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 헬퍼 도입 → PASS.

    영속 의무:
    - A2 권고 (ETF/리츠/우선주/SPAC 제외 의무)
    - 6 전략 부적합 종목 자동 차단
    """
    try:
        from src.engine.scanner import _universe_filter_securities_only
    except ImportError:
        pytest.fail(
            "\n사이클 89 H-2 Red 상태 — `_universe_filter_securities_only` 헬퍼 미존재.\n"
            "  Green (사이클 90): backend-dev 가 신규 헬퍼 도입 의무.\n"
            "  - scanner.py: _universe_filter_securities_only(rows: list[dict]) -> list[dict]\n"
            "  - A2 권고: ETF/리츠/SPAC 자동 제외"
        )

    # 보통주 5건 + ETF 5건 + 리츠 2건 + SPAC 1건 mock fixture
    rows = [
        # 보통주 5건 (정상 종목)
        {"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자",
         "prdt_type_cd": "300", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "000660", "hts_kor_isnm": "SK하이닉스",
         "prdt_type_cd": "300", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "035720", "hts_kor_isnm": "카카오",
         "prdt_type_cd": "300", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "035420", "hts_kor_isnm": "NAVER",
         "prdt_type_cd": "300", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "066570", "hts_kor_isnm": "LG전자",
         "prdt_type_cd": "300", "scts_mket_cls_code": "Y"},
        # ETF 5건 — 부적합
        {"mksc_shrn_iscd": "069500", "hts_kor_isnm": "KODEX 200",
         "prdt_type_cd": "301", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "102110", "hts_kor_isnm": "TIGER 200",
         "prdt_type_cd": "301", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "278530", "hts_kor_isnm": "KODEX 200TR",
         "prdt_type_cd": "301", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "229200", "hts_kor_isnm": "KODEX 코스닥150",
         "prdt_type_cd": "301", "scts_mket_cls_code": "N"},
        {"mksc_shrn_iscd": "233740", "hts_kor_isnm": "KODEX 코스닥150 레버리지",
         "prdt_type_cd": "301", "scts_mket_cls_code": "N"},
        # 리츠 2건 — 부적합
        {"mksc_shrn_iscd": "330590", "hts_kor_isnm": "롯데리츠",
         "prdt_type_cd": "302", "scts_mket_cls_code": "Y"},
        {"mksc_shrn_iscd": "395400", "hts_kor_isnm": "SK리츠",
         "prdt_type_cd": "302", "scts_mket_cls_code": "Y"},
        # SPAC 1건 — 부적합
        {"mksc_shrn_iscd": "385170", "hts_kor_isnm": "IBKS제17호스팩",
         "prdt_type_cd": "309", "scts_mket_cls_code": "N"},
    ]

    filtered = _universe_filter_securities_only(rows)

    # 가드 1: 결과 5건 (보통주만)
    assert len(filtered) == 5, (
        f"\n사이클 89 H-2 위반 — 보통주만 통과 의무:\n"
        f"  기대: 5건 (보통주 5건만)\n"
        f"  실제: {len(filtered)}건\n"
        f"  결과: {[r.get('hts_kor_isnm', r.get('mksc_shrn_iscd')) for r in filtered]}\n"
        f"  A2 권고: ETF/리츠/SPAC 자동 제외 의무"
    )

    # 가드 2: ETF 0건
    etf_tickers = {"069500", "102110", "278530", "229200", "233740"}
    result_tickers = {r["mksc_shrn_iscd"] for r in filtered}
    etf_in_result = etf_tickers & result_tickers
    assert not etf_in_result, (
        f"\n사이클 89 H-2 위반 — ETF 통과 발견:\n"
        f"  결과에 포함된 ETF: {sorted(etf_in_result)}\n"
        f"  A2 권고: ETF 자동 제외 (`prdt_type_cd=301`)"
    )

    # 가드 3: 리츠 0건
    reits_tickers = {"330590", "395400"}
    reits_in_result = reits_tickers & result_tickers
    assert not reits_in_result, (
        f"\n사이클 89 H-2 위반 — 리츠 통과 발견:\n"
        f"  결과에 포함된 리츠: {sorted(reits_in_result)}\n"
        f"  A2 권고: 리츠 자동 제외 (`prdt_type_cd=302`)"
    )

    # 가드 4: SPAC 0건
    spac_tickers = {"385170"}
    spac_in_result = spac_tickers & result_tickers
    assert not spac_in_result, (
        f"\n사이클 89 H-2 위반 — SPAC 통과 발견:\n"
        f"  결과에 포함된 SPAC: {sorted(spac_in_result)}\n"
        f"  A2 권고: SPAC 자동 제외"
    )
