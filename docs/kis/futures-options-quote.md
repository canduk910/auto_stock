# [국내선물옵션] 기본시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (9개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 206 | REST | 선물옵션 시세 | FHMIF10000000 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-price` | ✓ |
| 207 | REST | 국내선물 기초자산 시세 | FHPIF05030000 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-top` |  |
| 208 | REST | 선물옵션 일중예상체결추이 | FHPIF05110100 | GET | `/uapi/domestic-futureoption/v1/quotations/exp-price-trend` |  |
| 209 | REST | 선물옵션기간별시세(일/주/월/년) | FHKIF03020100 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice` |  |
| 210 | REST | 국내옵션전광판_선물 | FHPIF05030200 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-futures` |  |
| 211 | REST | 선물옵션 분봉조회 | FHKIF03020200 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice` |  |
| 212 | REST | 국내옵션전광판_옵션월물리스트 | FHPIO056104C0 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-option-list` |  |
| 213 | REST | 선물옵션 시세호가 | FHMIF10010000 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-asking-price` |  |
| 214 | REST | 국내옵션전광판_콜풋 | FHPIF05030100 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-callput` |  |

---

## 상세 명세

### 선물옵션 시세

- **TR_ID**: FHMIF10000000
- **모의 TR_ID**: FHMIF10000000
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-price`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code": "F",
"fid_input_iscd": "101S03"
} |  |
| Response Example | {
  "output1": {
    "hts_kor_isnm": "F 202203",
    "futs_prpr": "395.00",
    "futs_prdy_vrss": "6.70",
    "prdy_vrss_sign": "2",
    "futs_prdy_clpr": "388.30",
    "futs_prdy_ctrt": "1.73",
    "acml_vol": "220924",
    "acml_tr_pbmn": "21741293338",
    "hts_otst_stpl_qty": "247121",
    "otst_stpl_qty_icdc": "-592",
    "futs_oprc": "391.05",
    "futs_hgpr": "395.15",
    "futs_lwpr": "391.00",
    "futs_mxpr": "419.35",
    "futs_llam": "357.25",
    "basis": "0.82",
    "futs_sdpr": "388.30",
    "hts_thpr": "395.48",
    "dprt": "-0.12",
    "crbr_aply_mxpr": "0.00",
    "crbr_aply_llam": "0.00",
    "futs_last_tr_date": "20220310",
    "hts_rmnn_dynu": "58",
    "futs_lstn_medm_hgpr": "434.00",
    "futs_lstn_medm_lwpr": "366.60",
    "delta_val": "1.0000",
    "gama": "0.0000",
    "theta": "0.0000",
    "vega": "0.0000",
    "rho": "0.0000",
    "mrkt_basis": "0.34"
  },
  "output2": {
    "bstp_cls_code": "0001",
    "hts_kor_isnm": "종합",
    "bstp_nmix_prpr": "2972.48",
    "prdy_vrss_sign": "2",
    "bstp_nmix_prdy_vrss": "45.10",
    "bstp_nmix_prdy_ctrt": "1.54"
  },
  "output3": {
    "bstp_cls_code": "2001",
    "hts_kor_isnm": "KOSPI200",
    "bstp_nmix_prpr": "394.66",
    "prdy_vrss_sign": "2",
    "bstp_nmix_prdy_vrss": "5.69",
    "bstp_nmix_prdy_ctrt": "1.46"
  },
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다!"
} |  |


### 국내선물 기초자산 시세

- **TR_ID**: FHPIF05030000
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-top`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:F
fid_input_iscd:101V06
fid_cond_mrkt_div_code1:
fid_cond_scr_div_code:
fid_mtrt_cnt:
fid_cond_mrkt_cls_code: |  |
| Response Example | {
    "output1": {
        "unas_prpr": "367.25",
        "unas_prdy_vrss": "-3.47",
        "unas_prdy_vrss_sign": "5",
        "unas_prdy_ctrt": "-0.94",
        "unas_acml_vol": "161725000",
        "hts_kor_isnm": "F 202406",
        "futs_prpr": "369.35",
        "futs_prdy_vrss": "-3.45",
        "prdy_vrss_sign": "5",
        "futs_prdy_ctrt": "-0.93"
    },
    "output2": [],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 선물옵션 일중예상체결추이

- **TR_ID**: FHPIF05110100
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/exp-price-trend`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:F
FID_INPUT_ISCD:101V06 |  |
| Response Example | {
    "output1": {
        "hts_kor_isnm": "F 202406",
        "futs_antc_cnpr": "0.000",
        "antc_cntg_vrss_sign": "0",
        "futs_antc_cntg_vrss": "0.000",
        "antc_cntg_prdy_ctrt": "0.00",
        "futs_sdpr": "376.95"
    },
    "output2": [
        {
            "stck_cntg_hour": "084500",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.80",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.85",
            "antc_cntg_prdy_ctrt": "0.76"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.80",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.85",
            "antc_cntg_prdy_ctrt": "0.76"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.60",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.65",
            "antc_cntg_prdy_ctrt": "0.70"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.60",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.65",
            "antc_cntg_prdy_ctrt": "0.70"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 선물옵션기간별시세(일/주/월/년)

- **TR_ID**: FHKIF03020100
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 국내옵션전광판_선물

- **TR_ID**: FHPIF05030200
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-futures`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:F
FID_COND_SCR_DIV_CODE:20503
FID_COND_MRKT_CLS_CODE:MKI |  |
| Response Example | {
    "output": [
        {
            "futs_shrn_iscd": "105V05",
            "hts_kor_isnm": "미니F 202405",
            "futs_prpr": "368.28",
            "futs_prdy_vrss": "-3.32",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.89",
            "hts_thpr": "368.26",
            "acml_vol": "91624",
            "futs_askp": "368.28",
            "futs_bidp": "368.26",
            "hts_otst_stpl_qty": "38188",
            "futs_hgpr": "372.86",
            "futs_lwpr": "367.40",
            "hts_rmnn_dynu": "28",
            "total_askp_rsqn": "934",
            "total_bidp_rsqn": "282",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V06",
            "hts_kor_isnm": "미니F 202406",
            "futs_prpr": "369.48",
            "futs_prdy_vrss": "-3.32",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.89",
            "hts_thpr": "369.51",
            "acml_vol": "621",
            "futs_askp": "369.54",
            "futs_bidp": "369.48",
            "hts_otst_stpl_qty": "3433",
            "futs_hgpr": "374.16",
            "futs_lwpr": "368.64",
            "hts_rmnn_dynu": "63",
            "total_askp_rsqn": "68",
            "total_bidp_rsqn": "53",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V07",
            "hts_kor_isnm": "미니F 202407",
            "futs_prpr": "369.00",
            "futs_prdy_vrss": "-3.98",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-1.07",
            "hts_thpr": "369.43",
            "acml_vol": "19",
            "futs_askp": "370.24",
            "futs_bidp": "367.52",
            "hts_otst_stpl_qty": "31",
            "futs_hgpr": "372.00",
            "futs_lwpr": "369.00",
            "hts_rmnn_dynu": "91",
            "total_askp_rsqn": "257",
            "total_bidp_rsqn": "13",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V08",
            "hts_kor_isnm": "미니F 202408",
            "futs_prpr": "373.78",
            "futs_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "futs_prdy_ctrt": "0.00",
            "hts_thpr": "370.41",
            "acml_vol": "0",
            "futs_askp": "403.58",
            "futs_bidp": "344.00",
            "hts_otst_stpl_qty": "1",
            "futs_hgpr": "0.00",
            "futs_lwpr": "0.00",
            "hts_rmnn_dynu": "119",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "5",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V09",
            "hts_kor_isnm": "미니F 202409",
            "futs_prpr": "374.00",
            "futs_prdy_vrss": "-0.50",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.13",
            "hts_thpr": "371.67",
            "acml_vol": "3",
            "futs_askp": "404.36",
            "futs_bidp": "369.82",
            "hts_otst_stpl_qty": "10",
            "futs_hgpr": "374.00",
            "futs_lwpr": "371.00",
            "hts_rmnn_dynu": "154",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "12",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V10",
            "hts_kor_isnm": "미니F 202410",
            "futs_prpr": "375.26",
            "futs_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "futs_prdy_ctrt": "0.00",
            "hts_thpr": "371.72",
            "acml_vol": "0",
            "futs_askp": "405.18",
            "futs_bidp": "345.34",
            "hts_otst_stpl_qty": "0",
            "futs_hgpr": "0.00",
            "futs_lwpr": "0.00",
            "hts_rmnn_dynu": "182",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "4",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 선물옵션 분봉조회

- **TR_ID**: FHKIF03020200
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:F
fid_input_iscd:101V09
fid_hour_cls_code:30
fid_pw_data_incu_yn:N
fid_fake_tick_incu_yn:Y
fid_input_date_1:
fid_input_hour_1: |  |
| Response Example | {
    "output1": {
        "futs_prdy_vrss": "-0.30",
        "prdy_vrss_sign": "5",
        "futs_prdy_ctrt": "-0.08",
        "futs_prdy_clpr": "359.90",
        "prdy_nmix": "359.90",
        "acml_vol": "349",
        "acml_tr_pbmn": "31394925",
        "hts_kor_isnm": "F 202409",
        "futs_prpr": "359.60",
        "futs_shrn_iscd": "101V09",
        "prdy_vol": "721",
        "futs_mxpr": "388.65",
        "futs_llam": "331.15",
        "futs_oprc": "361.50",
        "futs_hgpr": "362.00",
        "futs_lwpr": "357.20",
        "futs_prdy_oprc": "364.95",
        "futs_prdy_hgpr": "365.30",
        "futs_prdy_lwpr": "358.60",
        "futs_askp": "359.65",
        "futs_bidp": "359.50",
        "basis": "4.06",
        "kospi200_nmix": "356.42",
        "hts_otst_stpl_qty": "11529",
        "otst_stpl_qty_icdc": "0",
        "tday_rltv": "78.97",
        "hts_thpr": "360.48",
        "dprt": "-0.25"
    },
    "output2": [
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141500",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141430",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141400",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141330",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내옵션전광판_옵션월물리스트

- **TR_ID**: FHPIO056104C0
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-option-list`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_scr_div_code:509
fid_cond_mrkt_div_code:
fid_cond_mrkt_cls_code: |  |
| Response Example | {
    "output": [
        {
            "mtrt_yymm_code": "0V05",
            "mtrt_yymm": "202405"
        },
        {
            "mtrt_yymm_code": "0V06",
            "mtrt_yymm": "202406"
        },
        {
            "mtrt_yymm_code": "0V07",
            "mtrt_yymm": "202407"
        },
        {
            "mtrt_yymm_code": "0V08",
            "mtrt_yymm": "202408"
        },
        {
            "mtrt_yymm_code": "0V09",
            "mtrt_yymm": "202409"
        },
        {
            "mtrt_yymm_code": "0V10",
            "mtrt_yymm": "202410"
        },
        {
            "mtrt_yymm_code": "0V12",
            "mtrt_yymm": "202412"
        },
        {
            "mtrt_yymm_code": "0W03",
            "mtrt_yymm": "202503"
        },
        {
            "mtrt_yymm_code": "0W06",
            "mtrt_yymm": "202506"
        },
        {
            "mtrt_yymm_code": "0W12",
            "mtrt_yymm": "202512"
        },
        {
            "mtrt_yymm_code": "0612",
            "mtrt_yymm": "202612"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 선물옵션 시세호가

- **TR_ID**: FHMIF10010000
- **모의 TR_ID**: FHMIF10010000
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-asking-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code" : "F",
"fid_input_iscd" : "101S06"
} |  |
| Response Example | {
  "output1": {
    "hts_kor_isnm": "F 202206",
    "futs_prpr": "364.40",
    "prdy_vrss_sign": "2",
    "futs_prdy_vrss": "3.00",
    "futs_prdy_ctrt": "0.83",
    "acml_vol": "193112",
    "futs_prdy_clpr": "361.40",
    "futs_shrn_iscd": "101S06"
  },
  "output2": {
    "futs_askp1": "364.40",
    "futs_askp2": "364.45",
    "futs_askp3": "364.50",
    "futs_askp4": "364.55",
    "futs_askp5": "364.60",
    "futs_bidp1": "364.35",
    "futs_bidp2": "364.30",
    "futs_bidp3": "364.25",
    "futs_bidp4": "364.20",
    "futs_bidp5": "364.15",
    "askp_rsqn1": "35",
    "askp_rsqn2": "47",
    "askp_rsqn3": "32",
    "askp_rsqn4": "56",
    "askp_rsqn5": "88",
    "bidp_rsqn1": "22",
    "bidp_rsqn2": "70",
    "bidp_rsqn3": "68",
    "bidp_rsqn4": "97",
    "bidp_rsqn5": "42",
    "askp_csnu1": "9",
    "askp_csnu2": "19",
    "askp_csnu3": "21",
    "askp_csnu4": "28",
    "askp_csnu5": "20",
    "bidp_csnu1": "9",
    "bidp_csnu2": "45",
    "bidp_csnu3": "26",
    "bidp_csnu4": "31",
    "bidp_csnu5": "22",
    "total_askp_rsqn": "7140",
    "total_bidp_rsqn": "9319",
    "total_askp_csnu": "1091",
    "total_bidp_csnu": "1115",
    "aspr_acpt_hour": "153744"
  },
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다."
} |  |


### 국내옵션전광판_콜풋

- **TR_ID**: FHPIF05030100
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-callput`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:O
fid_cond_scr_div_code:20503
fid_mrkt_cls_code:CO
fid_mtrt_cnt:202405
fid_cond_mrkt_cls_code:
fid_mrkt_cls_code1:PO |  |
| Response Example | {
    "output1": [
        {
            "acpr": "480.00",
            "unch_prpr": "3505.17",
            "optn_shrn_iscd": "201V05480",
            "optn_prpr": "0.01",
            "optn_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "optn_prdy_ctrt": "0.00",
            "optn_bidp": "0.00",
            "optn_askp": "0.01",
            "tmvl_val": "0.01",
            "nmix_sdpr": "0.01",
            "acml_vol": "34",
            "seln_rsqn": "1710",
            "shnu_rsqn": "0",
            "acml_tr_pbmn": "85",
            "hts_otst_stpl_qty": "642",
            "otst_stpl_qty_icdc": "39",
            "delta_val": "0.0000",
            "gama": "0.0000",
            "vega": "0.0000",
            "theta": "-0.0000",
            "rho": "0.0000",
            "hts_ints_vltl": "31.5614",
            "invl_val": "0.00",
            "esdg": "0.01",
            "dprt": "9999.99",
            "hist_vltl": "16.9285",
            "hts_thpr": "0.00",
            "optn_oprc": "0.01",
            "optn_hgpr": "0.01",
            "optn_lwpr": "0.01",
            "optn_mxpr": "5.20",
            "optn_llam": "0.01",
            "atm_cls_name": "OTM",
            "rgbf_vrss_icdc": "1",
            "total_askp_rsqn": "1710",
            "total_bidp_rsqn": "0",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
		...
    ],
    "output2": [
        {
            "acpr": "480.00",
            "unch_prpr": "3505.17",
            "optn_shrn_iscd": "301V05480",
            "optn_prpr": "108.45",
            "optn_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "optn_prdy_ctrt": "0.00",
            "optn_bidp": "78.35",
            "optn_askp": "142.60",
            "tmvl_val": "-4.30",
            "nmix_sdpr": "108.45",
            "acml_vol": "0",
            "seln_rsqn": "10",
            "shnu_rsqn": "10",
            "acml_tr_pbmn": "0",
            "hts_otst_stpl_qty": "48",
            "otst_stpl_qty_icdc": "0",
            "delta_val": "-1.0000",
            "gama": "0.0000",
            "vega": "0.0000",
            "theta": "0.0460",
            "rho": "-0.3541",
            "hts_ints_vltl": "0.0000",
            "invl_val": "112.75",
            "esdg": "-3.06",
            "dprt": "-2.74",
            "hist_vltl": "16.9285",
            "hts_thpr": "111.51",
            "optn_oprc": "0.00",
            "optn_hgpr": "0.00",
            "optn_lwpr": "0.00",
            "optn_mxpr": "142.60",
            "optn_llam": "78.35",
            "atm_cls_name": "ITM",
            "rgbf_vrss_icdc": "0",
            "total_askp_rsqn": "10",
            "total_bidp_rsqn": "10",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |

