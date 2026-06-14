"""사이클 129 — KIS 마스터 파일 fixed-width 파싱 Red 회귀 가드.

배경:
- KIS 정본 (kis-mcp-query 검증):
  - KOSPI 70 part2 field_specs (후미 228 byte)
  - KOSDAQ 64 part2 field_specs (후미 222 byte)
  - 단축코드 9 byte + 표준코드 12 byte + 한글명 가변 + part2 fixed-width
- cp949 한글 종목명 디코드 (예: "삼성전자" / "에코프로비엠")

회귀 가드 4 케이스:
- G-PW1: KOSPI 70 field_specs 정확 (총 합 = 228 byte)
- G-PW2: KOSDAQ 64 field_specs 정확 (총 합 = 222 byte)
- G-PW3: 한글 종목명 cp949 디코드 정합
- G-PW4: byte offset 회귀 가드 (단축코드 9 + 표준코드 12)
"""
from __future__ import annotations


def test_g_pw1_kospi_field_specs_sum_227():
    """G-PW1: KOSPI part2 field_specs 70 컬럼 총 합 = 227 byte (KIS 정본 검증).

    KIS 정본 (kis_kospi_code_mst.py) 영역 sum 정밀 검증 (사이클 129 진행 영역):
    sum = 227 byte (team-leader 초기 명세 "228" 결함 영구 차단)
    """
    from src.api import kis_master

    assert hasattr(kis_master, "KOSPI_FIELD_SPECS"), (
        "G-PW1: KOSPI_FIELD_SPECS 상수 부재"
    )
    assert len(kis_master.KOSPI_FIELD_SPECS) == 70, (
        f"G-PW1: KOSPI field_specs 길이 70 위반 (실제 {len(kis_master.KOSPI_FIELD_SPECS)})"
    )
    assert sum(kis_master.KOSPI_FIELD_SPECS) == 227, (
        f"G-PW1: KOSPI field_specs 총 합 227 위반 (실제 {sum(kis_master.KOSPI_FIELD_SPECS)})"
    )


def test_g_pw2_kosdaq_field_specs_sum_221():
    """G-PW2: KOSDAQ part2 field_specs 64 컬럼 총 합 = 221 byte (KIS 정본 검증).

    KIS 정본 (kis_kosdaq_code_mst.py) 영역 sum 정밀 검증 (사이클 129 진행 영역):
    sum = 221 byte (team-leader 초기 명세 "222" 결함 영구 차단)
    """
    from src.api import kis_master

    assert hasattr(kis_master, "KOSDAQ_FIELD_SPECS"), (
        "G-PW2: KOSDAQ_FIELD_SPECS 상수 부재"
    )
    assert len(kis_master.KOSDAQ_FIELD_SPECS) == 64, (
        f"G-PW2: KOSDAQ field_specs 길이 64 위반 (실제 {len(kis_master.KOSDAQ_FIELD_SPECS)})"
    )
    assert sum(kis_master.KOSDAQ_FIELD_SPECS) == 221, (
        f"G-PW2: KOSDAQ field_specs 총 합 221 위반 (실제 {sum(kis_master.KOSDAQ_FIELD_SPECS)})"
    )


def test_g_pw3_korean_cp949_decode():
    """G-PW3: 한글 종목명 cp949 디코드 정합.

    예: "삼성전자" / "에코프로비엠" — cp949 인코딩 후 디코드 동일.
    utf-8 디코드 시 silent 결함 영구 차단.
    """
    from src.api import kis_master

    # 단순 cp949 round-trip 검증 — 파서가 cp949 디코드를 사용해야 함
    sample = "삼성전자"
    encoded_cp949 = sample.encode("cp949")
    decoded_via_master = kis_master.decode_korean(encoded_cp949)
    assert decoded_via_master == sample, (
        f"G-PW3: cp949 한글 디코드 결함 (decoded={decoded_via_master!r})"
    )

    sample2 = "에코프로비엠"
    encoded2 = sample2.encode("cp949")
    decoded2 = kis_master.decode_korean(encoded2)
    assert decoded2 == sample2, (
        f"G-PW3: cp949 한글 디코드 결함 2 (decoded={decoded2!r})"
    )


def test_g_pw4_short_code_byte_offset():
    """G-PW4: 단축코드 9 byte + 표준코드 12 byte byte offset 정본.

    KIS 정본 .h 파일:
        char mksc_shrn_iscd[SZ_SHRNCODE];   // 9 byte (단축코드)
        char stnd_iscd[SZ_STNDCODE];        // 12 byte (표준코드)

    실제 파일 후미 228 byte (KOSPI) / 222 byte (KOSDAQ) 이전 영역.
    """
    from src.api import kis_master

    assert hasattr(kis_master, "KOSPI_TAIL_BYTES"), (
        "G-PW4: KOSPI_TAIL_BYTES 상수 부재"
    )
    assert kis_master.KOSPI_TAIL_BYTES == 227, (
        f"G-PW4: KOSPI 후미 227 byte 위반 (실제 {kis_master.KOSPI_TAIL_BYTES})"
    )
    assert hasattr(kis_master, "KOSDAQ_TAIL_BYTES"), (
        "G-PW4: KOSDAQ_TAIL_BYTES 상수 부재"
    )
    assert kis_master.KOSDAQ_TAIL_BYTES == 221, (
        f"G-PW4: KOSDAQ 후미 221 byte 위반 (실제 {kis_master.KOSDAQ_TAIL_BYTES})"
    )

    # part1 byte offset 영역 (단축코드 9 + 표준코드 12 = 21 byte fixed-width)
    assert hasattr(kis_master, "SHORT_CODE_LEN"), (
        "G-PW4: SHORT_CODE_LEN 상수 부재"
    )
    assert kis_master.SHORT_CODE_LEN == 9, (
        "G-PW4: 단축코드 9 byte 위반 — KIS 정본 SZ_SHRNCODE"
    )
    assert hasattr(kis_master, "STND_CODE_LEN"), (
        "G-PW4: STND_CODE_LEN 상수 부재"
    )
    assert kis_master.STND_CODE_LEN == 12, (
        "G-PW4: 표준코드 12 byte 위반 — KIS 정본 SZ_STNDCODE"
    )
