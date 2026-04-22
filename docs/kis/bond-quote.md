# [장내채권] 기본시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (8개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 328 | REST | 장내채권현재가(호가) | FHKBJ773401C0 | GET | `/uapi/domestic-bond/v1/quotations/inquire-asking-price` |  |
| 329 | REST | 장내채권현재가(시세) | FHKBJ773400C0 | GET | `/uapi/domestic-bond/v1/quotations/inquire-price` |  |
| 330 | REST | 장내채권현재가(체결) | FHKBJ773403C0 | GET | `/uapi/domestic-bond/v1/quotations/inquire-ccnl` |  |
| 331 | REST | 장내채권현재가(일별) | FHKBJ773404C0 | GET | `/uapi/domestic-bond/v1/quotations/inquire-daily-price` |  |
| 332 | REST | 장내채권 기간별시세(일) | FHKBJ773701C0 | GET | `/uapi/domestic-bond/v1/quotations/inquire-daily-itemchartprice` |  |
| 333 | REST | 장내채권 평균단가조회 | CTPF2005R | GET | `/uapi/domestic-bond/v1/quotations/avg-unit` |  |
| 334 | REST | 장내채권 발행정보 | CTPF1101R | GET | `/uapi/domestic-bond/v1/quotations/issue-info` |  |
| 335 | REST | 장내채권 기본조회 | CTPF1114R | GET | `/uapi/domestic-bond/v1/quotations/search-bond-info` |  |

---

## 상세 명세

### 장내채권현재가(호가)

- **TR_ID**: FHKBJ773401C0
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/inquire-asking-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:B
FID_INPUT_ISCD:KR2088012A16 |  |
| Response Example | {
    "output": {
        "aspr_acpt_hour": "094618",
        "bond_askp1": "0.00",
        "bond_askp2": "0.00",
        "bond_askp3": "0.00",
        "bond_askp4": "0.00",
        "bond_askp5": "0.00",
        "bond_bidp1": "10190.20",
        "bond_bidp2": "10189.70",
        "bond_bidp3": "10189.40",
        "bond_bidp4": "10188.90",
        "bond_bidp5": "10188.60",
        "askp_rsqn1": "0",
        "askp_rsqn2": "0",
        "askp_rsqn3": "0",
        "askp_rsqn4": "0",
        "askp_rsqn5": "0",
        "bidp_rsqn1": "320138",
        "bidp_rsqn2": "53685",
        "bidp_rsqn3": "9081",
        "bidp_rsqn4": "8232",
        "bidp_rsqn5": "4020",
        "total_askp_rsqn": "0",
        "total_bidp_rsqn": "425156",
        "ntby_aspr_rsqn": "425156",
        "seln_ernn_rate1": "0.000",
        "seln_ernn_rate2": "0.000",
        "seln_ernn_rate3": "0.000",
        "seln_ernn_rate4": "0.000",
        "seln_ernn_rate5": "0.000",
        "shnu_ernn_rate1": "4.549",
        "shnu_ernn_rate2": "4.556",
        "shnu_ernn_rate3": "4.560",
        "shnu_ernn_rate4": "4.567",
        "shnu_ernn_rate5": "4.571"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 장내채권현재가(시세)

- **TR_ID**: FHKBJ773400C0
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/inquire-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:B
FID_INPUT_ISCD:KR6095572D81 |  |
| Response Example | {
    "output": {
        "stnd_iscd": "KR6095572D81",
        "hts_kor_isnm": "AJ네트웍스63-2",
        "bond_prpr": "10265.00",
        "prdy_vrss_sign": "5",
        "bond_prdy_vrss": "-15.00",
        "prdy_ctrt": "-0.15",
        "acml_vol": "110000",
        "bond_prdy_clpr": "10280.00",
        "bond_oprc": "10265.00",
        "bond_hgpr": "10265.00",
        "bond_lwpr": "10265.00",
        "ernn_rate": "4.478",
        "oprc_ert": "4.478",
        "hgpr_ert": "4.478",
        "lwpr_ert": "4.478",
        "bond_mxpr": "13364.00",
        "bond_llam": "7196.00"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 장내채권현재가(체결)

- **TR_ID**: FHKBJ773403C0
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/inquire-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:B
FID_INPUT_ISCD:KR6095572D81 |  |
| Response Example | {
    "output": [
        {
            "stck_cntg_hour": "091632",
            "bond_prpr": "10265.00",
            "bond_prdy_vrss": "-15.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.15",
            "cntg_vol": "110000",
            "acml_vol": "110000"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 장내채권현재가(일별)

- **TR_ID**: FHKBJ773404C0
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/inquire-daily-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:B
FID_INPUT_ISCD:KR6095572D81 |  |
| Response Example | {
    "output": [
        {
            "stck_bsop_date": "20240503",
            "bond_prpr": "10265.00",
            "bond_prdy_vrss": "-15.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.15",
            "acml_vol": "110000",
            "bond_oprc": "10265.00",
            "bond_hgpr": "10265.00",
            "bond_lwpr": "10265.00"
        },
        {
            "stck_bsop_date": "20240502",
            "bond_prpr": "10280.00",
            "bond_prdy_vrss": "-145.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-1.39",
            "acml_vol": "61278",
            "bond_oprc": "10280.00",
            "bond_hgpr": "10280.00",
            "bond_lwpr": "10280.00"
        },
        {
            "stck_bsop_date": "20240430",
            "bond_prpr": "10425.00",
            "bond_prdy_vrss": "5.00",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.05",
            "acml_vol": "5012",
            "bond_oprc": "10425.00",
            "bond_hgpr": "10425.00",
            "bond_lwpr": "10425.00"
        },
        {
            "stck_bsop_date": "20240429",
            "bond_prpr": "10420.00",
            "bond_prdy_vrss": "-30.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.29",
            "acml_vol": "9999",
            "bond_oprc": "10420.00",
            "bond_hgpr": "10420.00",
            "bond_lwpr": "10420.00"
        },
        {
            "stck_bsop_date": "20240426",
            "bond_prpr": "10450.00",
            "bond_prdy_vrss": "10.30",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.10",
            "acml_vol": "102001",
            "bond_oprc": "10430.00",
            "bond_hgpr": "10450.00",
            "bond_lwpr": "10430.00"
        },
        {
            "stck_bsop_date": "20240425",
            "bond_prpr": "10439.70",
            "bond_prdy_vrss": "39.70",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.38",
            "acml_vol": "5718",
            "bond_oprc": "10290.00",
            "bond_hgpr": "10439.70",
            "bond_lwpr": "10290.00"
        },
        {
            "stck_bsop_date": "20240424",
            "bond_prpr": "10400.00",
            "bond_prdy_vrss": "-100.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.95",
            "acml_vol": "3000",
            "bond_oprc": "10400.00",
            "bond_hgpr": "10400.00",
            "bond_lwpr": "10400.00"
        },
        {
            "stck_bsop_date": "20240423",
            "bond_prpr": "10500.00",
            "bond_prdy_vrss": "50.00",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.48",
            "acml_vol": "10023",
            "bond_oprc": "10400.00",
            "bond_hgpr": "10500.00",
            "bond_lwpr": "10400.00"
        },
        {
            "stck_bsop_date": "20240422",
            "bond_prpr": "10450.00",
            "bond_prdy_vrss": "50.00",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.48",
            "acml_vol": "185887",
            "bond_oprc": "10450.00",
            "bond_hgpr": "10500.00",
            "bond_lwpr": "10449.90"
        },
        {
            "stck_bsop_date": "20240416",
            "bond_prpr": "10400.00",
            "bond_prdy_vrss": "41.00",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.40",
            "acml_vol": "16204",
            "bond_oprc": "10270.10",
            "bond_hgpr": "10400.00",
            "bond_lwpr": "10270.10"
        },
        {
            "stck_bsop_date": "20240409",
            "bond_prpr": "10359.00",
            "bond_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "25500",
            "bond_oprc": "10270.00",
            "bond_hgpr": "10359.00",
            "bond_lwpr": "10270.00"
        },
        {
            "stck_bsop_date": "20240408",
            "bond_prpr": "10359.00",
            "bond_prdy_vrss": "98.90",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.96",
            "acml_vol": "3908",
            "bond_oprc": "10270.00",
            "bond_hgpr": "10359.00",
            "bond_lwpr": "10201.40"
        },
        {
            "stck_bsop_date": "20240405",
            "bond_prpr": "10260.10",
            "bond_prdy_vrss": "10.10",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.10",
            "acml_vol": "86102",
            "bond_oprc": "10260.00",
            "bond_hgpr": "10369.70",
            "bond_lwpr": "10260.00"
        },
        {
            "stck_bsop_date": "20240404",
            "bond_prpr": "10250.00",
            "bond_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "160002",
            "bond_oprc": "10370.00",
            "bond_hgpr": "10370.00",
            "bond_lwpr": "10250.00"
        },
        {
            "stck_bsop_date": "20240403",
            "bond_prpr": "10250.00",
            "bond_prdy_vrss": "-10.00",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.10",
            "acml_vol": "15003",
            "bond_oprc": "10200.00",
            "bond_hgpr": "10250.00",
            "bond_lwpr": "10200.00"
        },
        {
            "stck_bsop_date": "20240402",
            "bond_prpr": "10260.00",
            "bond_prdy_vrss": "120.00",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "1.18",
            "acml_vol": "50000",
            "bond_oprc": "10260.00",
            "bond_hgpr": "10260.00",
            "bond_lwpr": "10260.00"
        },
		...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 장내채권 기간별시세(일)

- **TR_ID**: FHKBJ773701C0
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/inquire-daily-itemchartprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:B
FID_INPUT_ISCD:KR101501D967 |  |
| Response Example | {
    "output": [
        {
            "stck_bsop_date": "20240610",
            "bond_oprc": "0.00",
            "bond_hgpr": "0.00",
            "bond_lwpr": "0.00",
            "bond_prpr": "10997.10",
            "acml_vol": "0"
        },
        {
            "stck_bsop_date": "20240607",
            "bond_oprc": "10997.10",
            "bond_hgpr": "10997.10",
            "bond_lwpr": "10997.10",
            "bond_prpr": "10997.10",
            "acml_vol": "119"
        },
        {
            "stck_bsop_date": "20240605",
            "bond_oprc": "10997.50",
            "bond_hgpr": "10997.50",
            "bond_lwpr": "10997.50",
            "bond_prpr": "10997.50",
            "acml_vol": "97"
        },
        {
            "stck_bsop_date": "20240530",
            "bond_oprc": "10860.00",
            "bond_hgpr": "10860.00",
            "bond_lwpr": "10860.00",
            "bond_prpr": "10860.00",
            "acml_vol": "46"
        },
        {
            "stck_bsop_date": "20240529",
            "bond_oprc": "10873.00",
            "bond_hgpr": "10873.00",
            "bond_lwpr": "10873.00",
            "bond_prpr": "10873.00",
            "acml_vol": "3"
        },
        {
            "stck_bsop_date": "20240528",
            "bond_oprc": "8540.00",
            "bond_hgpr": "10700.00",
            "bond_lwpr": "8540.00",
            "bond_prpr": "10700.00",
            "acml_vol": "49"
        },
        {
            "stck_bsop_date": "20240520",
            "bond_oprc": "10867.70",
            "bond_hgpr": "10867.70",
            "bond_lwpr": "10867.70",
            "bond_prpr": "10867.70",
            "acml_vol": "14"
        },
        {
            "stck_bsop_date": "20240517",
            "bond_oprc": "10850.40",
            "bond_hgpr": "10850.40",
            "bond_lwpr": "10850.40",
            "bond_prpr": "10850.40",
            "acml_vol": "1015"
        },
        {
            "stck_bsop_date": "20240514",
            "bond_oprc": "10861.80",
            "bond_hgpr": "10863.50",
            "bond_lwpr": "10861.80",
            "bond_prpr": "10863.50",
            "acml_vol": "17549"
        },
        {
            "stck_bsop_date": "20240513",
            "bond_oprc": "10844.30",
            "bond_hgpr": "10861.10",
            "bond_lwpr": "10844.30",
            "bond_prpr": "10861.10",
            "acml_vol": "1963"
        },
        {
            "stck_bsop_date": "20240510",
            "bond_oprc": "10858.00",
            "bond_hgpr": "10858.00",
            "bond_lwpr": "10858.00",
            "bond_prpr": "10858.00",
            "acml_vol": "12"
        },
        {
            "stck_bsop_date": "20240509",
            "bond_oprc": "10857.00",
            "bond_hgpr": "10857.00",
            "bond_lwpr": "10857.00",
            "bond_prpr": "10857.00",
            "acml_vol": "2"
        },
        {
            "stck_bsop_date": "20240508",
            "bond_oprc": "10856.20",
            "bond_hgpr": "10856.20",
            "bond_lwpr": "10856.20",
            "bond_prpr": "10856.20",
            "acml_vol": "11"
        },
        {
            "stck_bsop_date": "20240424",
            "bond_oprc": "10820.70",
            "bond_hgpr": "10820.70",
            "bond_lwpr": "10820.70",
            "bond_prpr": "10820.70",
            "acml_vol": "931"
        },
        {
            "stck_bsop_date": "20240423",
            "bond_oprc": "10818.60",
            "bond_hgpr": "10819.00",
            "bond_lwpr": "10818.60",
            "bond_prpr": "10819.00",
            "acml_vol": "3708"
        },
        {
            "stck_bsop_date": "20240422",
            "bond_oprc": "10817.60",
            "bond_hgpr": "10823.00",
            "bond_lwpr": "10817.60",
            "bond_prpr": "10823.00",
            "acml_vol": "13959"
        },
        {
            "stck_bsop_date": "20240308",
            "bond_oprc": "10756.00",
            "bond_hgpr": "10788.00",
            "bond_lwpr": "10756.00",
            "bond_prpr": "10788.00",
            "acml_vol": "20"
        },
        {
            "stck_bsop_date": "20231108",
            "bond_oprc": "10600.00",
            "bond_hgpr": "10600.00",
            "bond_lwpr": "10600.00",
            "bond_prpr": "10600.00",
            "acml_vol": "949"
        },
        {
            "stck_bsop_date": "20231018",
            "bond_oprc": "10570.00",
            "bond_hgpr": "10620.00",
            "bond_lwpr": "10570.00",
            "bond_prpr": "10620.00",
            "acml_vol": "1890"
        },
        {
            "stck_bsop_date": "20231013",
            "bond_oprc": "10592.00",
            "bond_hgpr": "10630.00",
            "bond_lwpr": "10592.00",
            "bond_prpr": "10630.00",
            "acml_vol": "10714"
        },
        {
            "stck_bsop_date": "20231012",
            "bond_oprc": "10541.00",
            "bond_hgpr": "10592.00",
            "bond_lwpr": "10541.00",
            "bond_prpr": "10592.00",
            "acml_vol": "5691"
        },
        {
            "stck_bsop_date": "20230926",
            "bond_oprc": "10615.70",
            "bond_hgpr": "10615.70",
            "bond_lwpr": "10615.70",
            "bond_prpr": "10615.70",
            "acml_vol": "4731"
        },
        {
            "stck_bsop_date": "20230914",
            "bond_oprc": "10579.00",
            "bond_hgpr": "10579.00",
            "bond_lwpr": "10579.00",
            "bond_prpr": "10579.00",
            "acml_vol": "10"
        },
        {
            "stck_bsop_date": "20230913",
            "bond_oprc": "10501.00",
            "bond_hgpr": "10501.00",
            "bond_lwpr": "10501.00",
            "bond_prpr": "10501.00",
            "acml_vol": "9"
        },
        {
            "stck_bsop_date": "20230912",
            "bond_oprc": "10499.10",
            "bond_hgpr": "10540.00",
            "bond_lwpr": "10499.10",
            "bond_prpr": "10499.10",
            "acml_vol": "30"
        },
        {
            "stck_bsop_date": "20230829",
            "bond_oprc": "10389.00",
            "bond_hgpr": "10389.00",
            "bond_lwpr": "10389.00",
            "bond_prpr": "10389.00",
            "acml_vol": "4761"
        },
        {
            "stck_bsop_date": "20230825",
            "bond_oprc": "10550.00",
            "bond_hgpr": "10550.00",
            "bond_lwpr": "10550.00",
            "bond_prpr": "10550.00",
            "acml_vol": "12555"
        },
        {
            "stck_bsop_date": "20230818",
            "bond_oprc": "10299.20",
            "bond_hgpr": "10299.20",
            "bond_lwpr": "10299.20",
            "bond_prpr": "10299.20",
            "acml_vol": "2838"
        },
        {
            "stck_bsop_date": "20230814",
            "bond_oprc": "10350.00",
            "bond_hgpr": "10450.00",
            "bond_lwpr": "10350.00",
            "bond_prpr": "10450.00",
            "acml_vol": "2838"
        },
        {
            "stck_bsop_date": "20230720",
            "bond_oprc": "10527.00",
            "bond_hgpr": "10527.00",
            "bond_lwpr": "10527.00",
            "bond_prpr": "10527.00",
            "acml_vol": "18"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 장내채권 평균단가조회

- **TR_ID**: CTPF2005R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/avg-unit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | INQR_STRT_DT:20240101
INQR_END_DT:20240425
PDNO:KR2033022D33
PRDT_TYPE_CD:302
VRFC_KIND_CD:00
CTX_AREA_NK30:
CTX_AREA_FK100: |  |
| Response Example | {
    "ctx_area_nk30": "20240406!^KR2033022D33!^302   ",
    "ctx_area_fk100": "20240101!^20240425!^KR2033022D33!^302!^00                                                           ",
    "output1": [
        {
            "evlu_dt": "20240425",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9745.69000000",
            "kbp_unpr": "9760.39000000",
            "nice_evlu_unpr": "9767.78000000",
            "fnp_unpr": "9760.76",
            "avg_evlu_unpr": "9758.65000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.87000000",
            "kbp_erng_rt": "3.83000000",
            "nice_evlu_erng_rt": "3.810000000",
            "fnp_erng_rt": "3.82900000",
            "avg_evlu_erng_rt": "3.83480",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240424",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9757.62000000",
            "kbp_unpr": "9771.98000000",
            "nice_evlu_unpr": "9780.14000000",
            "fnp_unpr": "9773.46",
            "avg_evlu_unpr": "9770.80000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.83500000",
            "kbp_erng_rt": "3.79600000",
            "nice_evlu_erng_rt": "3.774000000",
            "fnp_erng_rt": "3.79200000",
            "avg_evlu_erng_rt": "3.79930",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240423",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9764.04000000",
            "kbp_unpr": "9778.42000000",
            "nice_evlu_unpr": "9785.84000000",
            "fnp_unpr": "9779.90",
            "avg_evlu_unpr": "9777.05000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.81500000",
            "kbp_erng_rt": "3.77600000",
            "nice_evlu_erng_rt": "3.756000000",
            "fnp_erng_rt": "3.77200000",
            "avg_evlu_erng_rt": "3.77980",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240422",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9753.79000000",
            "kbp_unpr": "9768.17000000",
            "nice_evlu_unpr": "9777.44000000",
            "fnp_unpr": "9769.65",
            "avg_evlu_unpr": "9767.26000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.84000000",
            "kbp_erng_rt": "3.80100000",
            "nice_evlu_erng_rt": "3.776000000",
            "fnp_erng_rt": "3.79700000",
            "avg_evlu_erng_rt": "3.80350",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240421",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9765.77000000",
            "kbp_unpr": "9780.18000000",
            "nice_evlu_unpr": "9789.47000000",
            "fnp_unpr": "9781.66",
            "avg_evlu_unpr": "9779.27000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.80500000",
            "kbp_erng_rt": "3.76600000",
            "nice_evlu_erng_rt": "3.741000000",
            "fnp_erng_rt": "3.76200000",
            "avg_evlu_erng_rt": "3.76850",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240420",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9764.79000000",
            "kbp_unpr": "9779.20000000",
            "nice_evlu_unpr": "9788.50000000",
            "fnp_unpr": "9780.69",
            "avg_evlu_unpr": "9778.29000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.80500000",
            "kbp_erng_rt": "3.76600000",
            "nice_evlu_erng_rt": "3.741000000",
            "fnp_erng_rt": "3.76200000",
            "avg_evlu_erng_rt": "3.76850",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240419",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9763.81000000",
            "kbp_unpr": "9778.23000000",
            "nice_evlu_unpr": "9787.53000000",
            "fnp_unpr": "9779.72",
            "avg_evlu_unpr": "9777.32000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.80500000",
            "kbp_erng_rt": "3.76600000",
            "nice_evlu_erng_rt": "3.741000000",
            "fnp_erng_rt": "3.76200000",
            "avg_evlu_erng_rt": "3.76850",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240418",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9782.54000000",
            "kbp_unpr": "9793.65000000",
            "nice_evlu_unpr": "9805.22000000",
            "fnp_unpr": "9798.50",
            "avg_evlu_unpr": "9794.97000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.75200000",
            "kbp_erng_rt": "3.72200000",
            "nice_evlu_erng_rt": "3.691000000",
            "fnp_erng_rt": "3.70900000",
            "avg_evlu_erng_rt": "3.71850",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240417",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9770.02000000",
            "kbp_unpr": "9777.77000000",
            "nice_evlu_unpr": "9791.94000000",
            "fnp_unpr": "9784.10",
            "avg_evlu_unpr": "9780.95000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.78300000",
            "kbp_erng_rt": "3.76200000",
            "nice_evlu_erng_rt": "3.724000000",
            "fnp_erng_rt": "3.74500000",
            "avg_evlu_erng_rt": "3.75350",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240416",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9767.18000000",
            "kbp_unpr": "9774.93000000",
            "nice_evlu_unpr": "9788.73000000",
            "fnp_unpr": "9782.02",
            "avg_evlu_unpr": "9778.21000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.78800000",
            "kbp_erng_rt": "3.76700000",
            "nice_evlu_erng_rt": "3.730000000",
            "fnp_erng_rt": "3.74800000",
            "avg_evlu_erng_rt": "3.75830",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240415",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9778.13000000",
            "kbp_unpr": "9787.02000000",
            "nice_evlu_unpr": "9798.98000000",
            "fnp_unpr": "9794.12",
            "avg_evlu_unpr": "9789.56000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.75600000",
            "kbp_erng_rt": "3.73200000",
            "nice_evlu_erng_rt": "3.700000000",
            "fnp_erng_rt": "3.71300000",
            "avg_evlu_erng_rt": "3.72530",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240414",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9795.10000000",
            "kbp_unpr": "9802.13000000",
            "nice_evlu_unpr": "9812.25000000",
            "fnp_unpr": "9808.13",
            "avg_evlu_unpr": "9804.40000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.70800000",
            "kbp_erng_rt": "3.68900000",
            "nice_evlu_erng_rt": "3.662000000",
            "fnp_erng_rt": "3.67300000",
            "avg_evlu_erng_rt": "3.68300",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240413",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9794.13000000",
            "kbp_unpr": "9801.18000000",
            "nice_evlu_unpr": "9811.30000000",
            "fnp_unpr": "9807.17",
            "avg_evlu_unpr": "9803.44000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.70800000",
            "kbp_erng_rt": "3.68900000",
            "nice_evlu_erng_rt": "3.662000000",
            "fnp_erng_rt": "3.67300000",
            "avg_evlu_erng_rt": "3.68300",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240412",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9793.17000000",
            "kbp_unpr": "9800.22000000",
            "nice_evlu_unpr": "9810.35000000",
            "fnp_unpr": "9806.22",
            "avg_evlu_unpr": "9802.49000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.70800000",
            "kbp_erng_rt": "3.68900000",
            "nice_evlu_erng_rt": "3.662000000",
            "fnp_erng_rt": "3.67300000",
            "avg_evlu_erng_rt": "3.68300",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240411",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9764.91000000",
            "kbp_unpr": "9773.80000000",
            "nice_evlu_unpr": "9783.16000000",
            "fnp_unpr": "9778.67",
            "avg_evlu_unpr": "9775.13000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.78100000",
            "kbp_erng_rt": "3.75700000",
            "nice_evlu_erng_rt": "3.732000000",
            "fnp_erng_rt": "3.74400000",
            "avg_evlu_erng_rt": "3.75350",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240410",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9793.13000000",
            "kbp_unpr": "9799.81000000",
            "nice_evlu_unpr": "9809.20000000",
            "fnp_unpr": "9804.69",
            "avg_evlu_unpr": "9801.70000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.70300000",
            "kbp_erng_rt": "3.68500000",
            "nice_evlu_erng_rt": "3.660000000",
            "fnp_erng_rt": "3.67200000",
            "avg_evlu_erng_rt": "3.68000",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240409",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9792.17000000",
            "kbp_unpr": "9798.85000000",
            "nice_evlu_unpr": "9808.25000000",
            "fnp_unpr": "9803.74",
            "avg_evlu_unpr": "9800.75000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.70300000",
            "kbp_erng_rt": "3.68500000",
            "nice_evlu_erng_rt": "3.660000000",
            "fnp_erng_rt": "3.67200000",
            "avg_evlu_erng_rt": "3.68000",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240408",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9796.84000000",
            "kbp_unpr": "9802.41000000",
            "nice_evlu_unpr": "9812.94000000",
            "fnp_unpr": "9806.92",
            "avg_evlu_unpr": "9804.77000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.68800000",
            "kbp_erng_rt": "3.67300000",
            "nice_evlu_erng_rt": "3.645000000",
            "fnp_erng_rt": "3.66100000",
            "avg_evlu_erng_rt": "3.66680",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240407",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9814.71000000",
            "kbp_unpr": "9818.40000000",
            "nice_evlu_unpr": "9830.10000000",
            "fnp_unpr": "9822.93",
            "avg_evlu_unpr": "9821.53000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.63800000",
            "kbp_erng_rt": "3.62800000",
            "nice_evlu_erng_rt": "3.597000000",
            "fnp_erng_rt": "3.61600000",
            "avg_evlu_erng_rt": "3.61980",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        },
        {
            "evlu_dt": "20240406",
            "pdno": "KR2033022D33",
            "prdt_type_cd": "302",
            "prdt_name": "충북지역개발채권23-03",
            "kis_unpr": "9813.76000000",
            "kbp_unpr": "9817.46000000",
            "nice_evlu_unpr": "9829.16000000",
            "fnp_unpr": "9821.99",
            "avg_evlu_unpr": "9820.59000000",
            "kis_crdt_grad_text": "",
            "kbp_crdt_grad_text": "",
            "nice_crdt_grad_text": "",
            "fnp_crdt_grad_text": "",
            "chng_yn": "N",
            "kis_erng_rt": "3.63800000",
            "kbp_erng_rt": "3.62800000",
            "nice_evlu_erng_rt": "3.597000000",
            "fnp_erng_rt": "3.61600000",
            "avg_evlu_erng_rt": "3.61980",
            "kis_rf_unpr": "0.00",
            "kbp_rf_unpr": "0.00",
            "nice_evlu_rf_unpr": "0.00",
            "avg_evlu_rf_unpr": "0.00"
        }
    ],
    "output2": [],
    "output3": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0500",
    "msg1": "조회가 계속됩니다..다음버튼을 Click 하십시오.                                   "
} |  |


### 장내채권 발행정보

- **TR_ID**: CTPF1101R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/issue-info`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | PDNO:KR6449111CB8
PRDT_TYPE_CD:302 |  |
| Response Example | {
    "output": {
        "pdno": "KR6449111CB8",
        "prdt_type_cd": "302",
        "prdt_name": "2022기보제일차유동화전문1-1(사)",
        "prdt_eng_name": "2022 KIBO 1st Securitization Specialty1-1(S)",
        "ivst_heed_prdt_yn": "N",
        "exts_yn": "N",
        "bond_clsf_cd": "116100",
        "bond_clsf_kor_name": "일반사채",
        "papr": "10000",
        "int_mned_dvsn_cd": "1",
        "rvnu_shap_cd": "2",
        "issu_amt": "77839700000",
        "lstg_rmnd": "77839700000",
        "int_dfrm_mcnt": "3",
        "bond_int_dfrm_mthd_cd": "03",
        "splt_rdpt_rcnt": "0",
        "prca_dfmt_term_mcnt": "0",
        "int_anap_dvsn_cd": "2",
        "bond_rght_dvsn_cd": "",
        "prdt_pclc_text": "",
        "prdt_abrv_name": "2022기보제일차유1-1(사)",
        "prdt_eng_abrv_name": "2022 KIBO 1st SEC1-1(S)",
        "sprx_psbl_yn": "N",
        "pbff_pplc_ofrg_mthd_cd": "01",
        "cmco_cd": "2117",
        "issu_istt_cd": "44911",
        "issu_istt_name": "2022기보제일차유동화전문 유한회사",
        "pnia_dfrm_agcy_istt_cd": "1105",
        "dsct_ec_rt": "0.000000",
        "srfc_inrt": "5.931000",
        "expd_rdpt_rt": "0.000000",
        "expd_asrc_erng_rt": "0.000000",
        "bond_grte_istt_name": "2022기보제일차유동화전문 유한회사",
        "int_dfrm_day_type_cd": "01",
        "ksd_int_calc_unit_cd": "1",
        "int_wunt_uder_prcs_dvsn_cd": "1",
        "rvnu_dt": "",
        "issu_dt": "20221116",
        "lstg_dt": "20221116",
        "expd_dt": "20241116",
        "rdpt_dt": "20241116",
        "sbst_pric": "8900",
        "rgbf_int_dfrm_dt": "20240516",
        "nxtm_int_dfrm_dt": "20240816",
        "frst_int_dfrm_dt": "",
        "ecis_pric": "0",
        "rght_stck_std_pdno": "",
        "ecis_opng_dt": "",
        "ecis_end_dt": "",
        "bond_rvnu_mthd_cd": "",
        "oprt_stfno": "BATCH",
        "oprt_stff_name": "",
        "rgbf_int_dfrm_wday": "05",
        "nxtm_int_dfrm_wday": "06",
        "kis_crdt_grad_text": "AAA",
        "kbp_crdt_grad_text": "AAA",
        "nice_crdt_grad_text": "AAA",
        "fnp_crdt_grad_text": "AAA",
        "dpsi_psbl_yn": "Y",
        "pnia_int_calc_unpr": "0",
        "prcm_idx_bond_yn": "N",
        "expd_exts_srdp_rcnt": "0",
        "expd_exts_srdp_rt": "0",
        "loan_psbl_yn": "N",
        "grte_dvsn_cd": "4",
        "fnrr_rank_dvsn_cd": "1",
        "krx_lstg_abol_dvsn_cd": "Y",
        "asst_rqdi_dvsn_cd": "11",
        "opcb_dvsn_cd": "",
        "crfd_item_yn": "N",
        "crfd_item_rstc_cclc_dt": "",
        "bond_nmpr_unit_pric": "0.100000",
        "ivst_heed_bond_dvsn_name": "",
        "add_erng_rt": "0.000000",
        "add_erng_rt_aply_dt": "",
        "bond_tr_stop_dvsn_cd": "N",
        "ivst_heed_bond_dvsn_cd": "0",
        "pclr_cndt_text": "",
        "hbbd_yn": "N",
        "cdtl_cptl_scty_type_cd": "",
        "elec_scty_yn": "Y",
        "sq1_clop_ecis_opng_dt": "",
        "frst_erlm_stfno": "",
        "frst_erlm_dt": "",
        "frst_erlm_tmd": ""
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |


### 장내채권 기본조회

- **TR_ID**: CTPF1114R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/quotations/search-bond-info`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | PDNO:KR2033022D33
PRDT_TYPE_CD:302 |  |
| Response Example | {
    "output": {
        "pdno": "KR2033022D33",
        "prdt_type_cd": "302",
        "ksd_bond_item_name": "충북지역개발채권 23-03",
        "ksd_bond_item_eng_name": "CHUNGBUK PROVINCIAL DEVELOPMENT 23-03",
        "ksd_bond_lstg_type_cd": "11",
        "ksd_ofrg_dvsn_cd": "11",
        "ksd_bond_int_dfrm_dvsn_cd": "3",
        "issu_dt": "20230331",
        "rdpt_dt": "20280331",
        "rvnu_dt": "20230302",
        "iso_crcy_cd": "KRW",
        "mdwy_rdpt_dt": "00000000",
        "ksd_rcvg_bond_dsct_rt": "0.000000000000",
        "ksd_rcvg_bond_srfc_inrt": "2.500000000000",
        "bond_expd_rdpt_rt": "100.000000000000",
        "ksd_prca_rdpt_mthd_cd": "11",
        "int_caltm_mcnt": "12",
        "ksd_int_calc_unit_cd": "1",
        "uval_cut_dvsn_cd": "2",
        "uval_cut_dcpt_dgit": "0",
        "ksd_dydv_caltm_aply_dvsn_cd": "1",
        "dydv_calc_dcnt": "0",
        "bond_expd_asrc_erng_rt": "0.000000000000",
        "padf_plac_hdof_name": "농협은행",
        "lstg_dt": "20230302",
        "lstg_abol_dt": "20280401",
        "ksd_bond_issu_mthd_cd": "2",
        "laps_indf_yn": "Y",
        "ksd_lhdy_pnia_dfrm_mthd_cd": "2",
        "frst_int_dfrm_dt": "00000000",
        "ksd_prcm_lnkg_gvbd_yn": "N",
        "dpsi_end_dt": "20280401",
        "dpsi_strt_dt": "20230302",
        "dpsi_psbl_yn": "Y",
        "atyp_rdpt_bond_erlm_yn": "N",
        "dshn_occr_yn": "N",
        "expd_exts_yn": "N",
        "pclr_ptcr_text": "",
        "dpsi_psbl_excp_stat_cd": "",
        "expd_exts_srdp_rcnt": "0",
        "expd_exts_srdp_rt": "0.000000000000",
        "expd_rdpt_rt": "0.00000000",
        "expd_asrc_erng_rt": "0.00000000",
        "bond_int_dfrm_mthd_cd": "02",
        "int_dfrm_day_type_cd": "02",
        "prca_dfmt_term_mcnt": "0",
        "splt_rdpt_rcnt": "0",
        "rgbf_int_dfrm_dt": "",
        "nxtm_int_dfrm_dt": "20280331",
        "sprx_psbl_yn": "N",
        "ictx_rt_dvsn_cd": "",
        "bond_clsf_cd": "112555",
        "bond_clsf_kor_name": "충북지역개발채권",
        "int_mned_dvsn_cd": "2",
        "pnia_int_calc_unpr": "0.0000",
        "frn_intr": "0.000000000000",
        "aply_day_prcm_idx_lnkg_cefc": "0.0000000000",
        "ksd_expd_dydv_calc_bass_cd": "",
        "expd_dydv_calc_dcnt": "0",
        "ksd_cbbw_dvsn_cd": "9",
        "crfd_item_yn": "N",
        "pnia_bank_ofdy_dfrm_mthd_cd": "1",
        "qib_yn": "N",
        "qib_cclc_dt": "00000000",
        "csbd_yn": "N",
        "csbd_cclc_dt": "00000000",
        "ksd_opcb_yn": "N",
        "ksd_sodn_yn": "N",
        "ksd_rqdi_scty_yn": "N",
        "elec_scty_yn": "Y",
        "rght_ecis_mbdy_dvsn_cd": "1",
        "int_rkng_mthd_dvsn_cd": "1",
        "ofrg_dvsn_cd": "",
        "ksd_tot_issu_amt": "17303560000.00",
        "next_indf_chk_ecls_yn": "N",
        "ksd_bond_intr_dvsn_cd": "1",
        "ksd_inrt_aply_dvsn_cd": "1",
        "krx_issu_istt_cd": "MB033",
        "ksd_indf_frqc_uder_calc_cd": "1",
        "ksd_indf_frqc_uder_calc_dcnt": "0",
        "tlg_rcvg_dtl_dtime": "20240625060514023"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |

