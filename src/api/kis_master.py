"""사이클 129 — KIS 종목 마스터 파일 다운로드 + cp949 fixed-width 파싱.

사용자 결정 영구 영속:
- Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼 + Q8=A 정본 채택
- Q12 시정 영구 영속: 시총 환산 × 100 (사용자 verbatim 정합)

KIS 정본 (kis-mcp-query 검증 영구 영속):
- KOSPI: https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
- KOSDAQ: https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip
- 인코딩 = cp949 (KIS 정본, utf-8 디코드 silent 결함 차단)
- KOSPI 후미 228 byte + part2 70 컬럼
- KOSDAQ 후미 222 byte + part2 64 컬럼
- 단축코드 9 byte (SZ_SHRNCODE) + 표준코드 12 byte (SZ_STNDCODE) + 한글명 가변

SSL 옵션 C (domain-consult 채택 영구 영속):
- httpx.AsyncClient(verify=True) 우선 시도 → SSL 인증서 영역 안전 영속
- ConnectError + SSL 키워드 영역 → verify=False 폴백 + WARNING 로그
- 운영 보안 가시화 의무 (사이클 88 G-REJECT graceful 영속)

본 모듈은 종목 마스터 영역 한정 — 매매/잔고/체결조회 영역 호출 0건 영구 영속.
"""
from __future__ import annotations

import io
import logging
import struct
import zipfile

import httpx

logger = logging.getLogger(__name__)

# ============================================================
# KIS 정본 상수 영구 영속
# ============================================================

KOSPI_MASTER_URL = (
    "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip"
)
KOSDAQ_MASTER_URL = (
    "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"
)

MASTER_FILE_ENCODING = "cp949"

# 단축코드 9 byte + 표준코드 12 byte (KIS 정본 .h SZ_SHRNCODE/SZ_STNDCODE)
SHORT_CODE_LEN = 9
STND_CODE_LEN = 12

# 후미 byte (part2 fixed-width 영역 시작점)
# KIS 정본 (kis_kospi_code_mst.py / kis_kosdaq_code_mst.py) 영역 = sum(field_specs).
# 사이클 129 진행 중 정밀 검증 영역 발견 = 227/221 (초기 명세 영역 "228/222" 영구 차단).
KOSPI_TAIL_BYTES = 227
KOSDAQ_TAIL_BYTES = 221

# KOSPI part2 field_specs (70 컬럼, 합 = 228 byte)
KOSPI_FIELD_SPECS: list[int] = [
    2, 1, 4, 4, 4,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 9, 5, 5, 1,
    1, 1, 2, 1, 1,
    1, 2, 2, 2, 3,
    1, 3, 12, 12, 8,
    15, 21, 2, 7, 1,
    1, 1, 1, 1, 9,
    9, 9, 5, 9, 8,
    9, 3, 1, 1, 1,
]

KOSPI_FIELD_NAMES: list[str] = [
    "scrt_grp_cls_code", "avls_scal_cls_code", "bstp_larg_div_code",
    "bstp_medm_div_code", "bstp_smal_div_code",
    "mnin_cls_code_yn", "low_current_yn", "sprn_strr_nmix_issu_yn",
    "kospi200_apnt_cls_code", "kospi100_issu_yn",
    "kospi50_issu_yn", "krx_issu_yn", "etp_prod_cls_code",
    "elw_pblc_yn", "krx100_issu_yn",
    "krx_car_yn", "krx_smcn_yn", "krx_bio_yn", "krx_bank_yn", "etpr_undt_objt_co_yn",
    "krx_enrg_chms_yn", "krx_stel_yn", "short_over_cls_code",
    "krx_medi_cmnc_yn", "krx_cnst_yn",
    "non1", "krx_scrt_yn", "krx_ship_yn", "krx_insu_yn", "krx_trnp_yn",
    "sri_nmix_yn", "stck_sdpr", "frml_mrkt_deal_qty_unit",
    "ovtm_mrkt_deal_qty_unit", "trht_yn",
    "sltr_yn", "mang_issu_yn", "mrkt_alrm_cls_code",
    "mrkt_alrm_risk_adnt_yn", "insn_pbnt_yn",
    "byps_lstn_yn", "flng_cls_code", "fcam_mod_cls_code", "icic_cls_code", "marg_rate",
    "crdt_able", "crdt_days", "prdy_vol", "stck_fcam", "stck_lstn_date",
    "lstn_stcn", "cpfn", "stac_month", "po_prc", "prst_cls_code",
    "ssts_hot_yn", "stange_runup_yn", "krx300_issu_yn", "kospi_issu_yn", "sale_account",
    "bsop_prfi", "op_prfi", "thtr_ntin", "roe", "base_date",
    "prdy_avls_scal", "grp_code", "co_crdt_limt_over_yn",
    "secu_lend_able_yn", "stln_able_yn",
]

# KOSDAQ part2 field_specs (64 컬럼, 합 = 222 byte)
KOSDAQ_FIELD_SPECS: list[int] = [
    2, 1,
    4, 4, 4, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 1,
    1, 1, 1, 1, 9,
    5, 5, 1, 1, 1,
    2, 1, 1, 1, 2,
    2, 2, 3, 1, 3,
    12, 12, 8, 15, 21,
    2, 7, 1, 1, 1,
    1, 9, 9, 9, 5,
    9, 8, 9, 3, 1,
    1, 1,
]

KOSDAQ_FIELD_NAMES: list[str] = [
    "scrt_grp_cls_code", "avls_scal_cls_code",
    "bstp_larg_div_code", "bstp_medm_div_code", "bstp_smal_div_code",
    "vntr_issu_yn", "low_current_yn",
    "krx_issu_yn", "etp_prod_cls_code", "krx100_issu_yn",
    "krx_car_yn", "krx_smcn_yn",
    "krx_bio_yn", "krx_bank_yn", "etpr_undt_objt_co_yn",
    "krx_enrg_chms_yn", "krx_stel_yn",
    "short_over_cls_code", "krx_medi_cmnc_yn", "krx_cnst_yn",
    "invt_alrm_yn", "krx_scrt_yn",
    "krx_ship_yn", "krx_insu_yn", "krx_trnp_yn",
    "ksq150_nmix_yn", "stck_sdpr",
    "frml_mrkt_deal_qty_unit", "ovtm_mrkt_deal_qty_unit",
    "trht_yn", "sltr_yn", "mang_issu_yn",
    "mrkt_alrm_cls_code", "mrkt_alrm_risk_adnt_yn",
    "insn_pbnt_yn", "byps_lstn_yn", "flng_cls_code",
    "fcam_mod_cls_code", "icic_cls_code", "marg_rate",
    "crdt_able", "crdt_days",
    "prdy_vol", "stck_fcam", "stck_lstn_date", "lstn_stcn", "cpfn",
    "stac_month", "po_prc", "prst_cls_code",
    "ssts_hot_yn", "stange_runup_yn",
    "krx300_issu_yn", "sale_account", "bsop_prfi", "op_prfi", "thtr_ntin",
    "roe", "base_date", "prdy_avls_scal",
    "grp_code", "co_crdt_limt_over_yn",
    "secu_lend_able_yn", "stln_able_yn",
]


# ============================================================
# 헬퍼 영역
# ============================================================


def decode_korean(raw_bytes: bytes) -> str:
    """cp949 한글 디코드 (KIS 정본 인코딩 영구 영속)."""
    try:
        return raw_bytes.decode(MASTER_FILE_ENCODING).strip()
    except UnicodeDecodeError:
        return raw_bytes.decode(MASTER_FILE_ENCODING, errors="replace").strip()


async def download_master_zip(url: str) -> bytes:
    """KIS 마스터 ZIP 다운로드 (SSL 옵션 C 영구 영속).

    domain-consult 채택 영구 영속:
    1. httpx.AsyncClient(verify=True) 우선 시도 (SSL 인증서 안전 영역)
    2. SSL 영역 ConnectError → verify=False 폴백 + WARNING 로그
    3. 사이클 88 G-REJECT graceful 영속

    Args:
        url: KOSPI_MASTER_URL or KOSDAQ_MASTER_URL

    Returns:
        ZIP bytes (zipfile.ZipFile 인입 영역).
    """
    # 1차 시도: SSL 검증 우선
    try:
        async with httpx.AsyncClient(verify=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.ConnectError as exc:
        exc_str = str(exc)
        # SSL 관련 에러 영역 한정 폴백 (다른 에러 = 전파)
        if "SSL" in exc_str or "certificate" in exc_str.lower():
            logger.warning(
                "[kis_master] SSL 검증 실패 → verify=False 폴백 (운영 보안 영역 가시화). "
                "url=%s reason=%s",
                url, exc_str[:200],
            )
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        raise


def _parse_master_records(
    raw_bytes: bytes,
    tail_bytes: int,
    field_specs: list[int],
    field_names: list[str],
) -> list[dict]:
    """fixed-width 마스터 영역 파싱 (KOSPI 70 / KOSDAQ 64 분기 공통 영역).

    KIS 공식 샘플 (kis_kospi_code_mst.py / kis_kosdaq_code_mst.py) 답습 영구 영속:
    - row 영역 = part1 (단축코드 9 + 표준코드 12 + 한글명 가변) + part2 (후미 tail_bytes fixed-width)
    - 각 라인 영역 = b"\r\n" 영역 (마스터 영역 영구 영속)
    """
    records: list[dict] = []
    # struct format 영역 (각 field_specs byte 별 s 영역)
    struct_fmt = "".join(f"{n}s" for n in field_specs)
    struct_size = struct.calcsize(struct_fmt)
    assert struct_size == tail_bytes, (
        f"field_specs 합 {struct_size} != tail_bytes {tail_bytes} 결함"
    )

    text_buffer = io.BytesIO(raw_bytes)
    for raw_line in text_buffer:
        # 라인 끝 영역 정리 (\r\n / \n)
        line = raw_line.rstrip(b"\r\n")
        if len(line) < tail_bytes + SHORT_CODE_LEN + STND_CODE_LEN:
            continue

        # part1 영역 (단축코드 + 표준코드 + 한글명 가변)
        part1 = line[: len(line) - tail_bytes]
        # part2 영역 (후미 tail_bytes fixed-width)
        part2 = line[-tail_bytes:]

        if len(part2) != tail_bytes:
            continue

        # part1 분해
        short_code = decode_korean(part1[0:SHORT_CODE_LEN])
        stnd_code = decode_korean(part1[SHORT_CODE_LEN : SHORT_CODE_LEN + STND_CODE_LEN])
        hts_kor_isnm = decode_korean(part1[SHORT_CODE_LEN + STND_CODE_LEN :])

        # part2 fixed-width 파싱
        try:
            fields = struct.unpack(struct_fmt, part2)
        except struct.error:
            continue

        record: dict = {
            "mksc_shrn_iscd": short_code,
            "stnd_iscd": stnd_code,
            "hts_kor_isnm": hts_kor_isnm,
        }
        for name, value in zip(field_names, fields):
            record[name] = decode_korean(value)

        records.append(record)

    return records


async def download_kospi_master() -> list[dict]:
    """KOSPI 마스터 다운로드 + cp949 파싱 (70 컬럼 + part1 3 키).

    Returns:
        종목 record 리스트 (mksc_shrn_iscd = 6자리 단축코드 영역).
    """
    zip_bytes = await download_master_zip(KOSPI_MASTER_URL)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # mst 파일명 = kospi_code.mst
            members = [n for n in zf.namelist() if n.endswith(".mst")]
            if not members:
                logger.warning("[kis_master] KOSPI ZIP 영역 .mst 파일 부재")
                return []
            raw_bytes = zf.read(members[0])
    except zipfile.BadZipFile as exc:
        logger.warning("[kis_master] KOSPI ZIP 영역 손상 graceful: %s", exc)
        return []

    return _parse_master_records(
        raw_bytes, KOSPI_TAIL_BYTES, KOSPI_FIELD_SPECS, KOSPI_FIELD_NAMES
    )


async def download_kosdaq_master() -> list[dict]:
    """KOSDAQ 마스터 다운로드 + cp949 파싱 (64 컬럼 + part1 3 키).

    Returns:
        종목 record 리스트 (mksc_shrn_iscd = 6자리 단축코드 영역).
    """
    zip_bytes = await download_master_zip(KOSDAQ_MASTER_URL)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            members = [n for n in zf.namelist() if n.endswith(".mst")]
            if not members:
                logger.warning("[kis_master] KOSDAQ ZIP 영역 .mst 파일 부재")
                return []
            raw_bytes = zf.read(members[0])
    except zipfile.BadZipFile as exc:
        logger.warning("[kis_master] KOSDAQ ZIP 영역 손상 graceful: %s", exc)
        return []

    return _parse_master_records(
        raw_bytes, KOSDAQ_TAIL_BYTES, KOSDAQ_FIELD_SPECS, KOSDAQ_FIELD_NAMES
    )
