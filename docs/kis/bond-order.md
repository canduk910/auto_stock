# [장내채권] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (7개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 321 | REST | 장내채권 매수주문 | TTTC0952U | POST | `/uapi/domestic-bond/v1/trading/buy` |  |
| 322 | REST | 장내채권 매도주문 | TTTC0958U | POST | `/uapi/domestic-bond/v1/trading/sell` |  |
| 323 | REST | 장내채권 정정취소주문 | TTTC0953U | POST | `/uapi/domestic-bond/v1/trading/order-rvsecncl` |  |
| 324 | REST | 채권정정취소가능주문조회 | CTSC8035R | GET | `/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl` |  |
| 325 | REST | 장내채권 주문체결내역 | CTSC8013R | GET | `/uapi/domestic-bond/v1/trading/inquire-daily-ccld` |  |
| 326 | REST | 장내채권 잔고조회 | CTSC8407R | GET | `/uapi/domestic-bond/v1/trading/inquire-balance` |  |
| 327 | REST | 장내채권 매수가능조회 | TTTC8910R | GET | `/uapi/domestic-bond/v1/trading/inquire-psbl-order` |  |

---

## 상세 명세

### 장내채권 매수주문

- **TR_ID**: TTTC0952U
- **Method**: POST
- **URL**: `/uapi/domestic-bond/v1/trading/buy`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "PDNO": "KR6095572D81",
    "ORD_QTY2": "1",
    "BOND_ORD_UNPR":"10000",
    "SAMT_MKET_PTCI_YN":"N",
    "BOND_RTL_MKET_YN":"N",
    "IDCR_STFNO":"",
    "MGCO_APTM_ODNO":"",
    "ORD_SVR_DVSN_CD":"0",
    "CTAC_TLNO":""
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "KRX_FWDG_ORD_ORGNO": "01790",
        "ODNO": "0000015401",
        "ORD_TMD": "104258"
    }
} |  |


### 장내채권 매도주문

- **TR_ID**: TTTC0958U
- **Method**: POST
- **URL**: `/uapi/domestic-bond/v1/trading/sell`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "ORD_DVSN":"01",
    "PDNO":"KR6095572D81",
    "ORD_QTY2":"1",
    "BOND_ORD_UNPR":"10450",
    "SPRX_YN":"N",
    "BUY_DT":"",
    "BUY_SEQ":"",
    "SAMT_MKET_PTCI_YN":"N",
    "SLL_AGCO_OPPS_SLL_YN":"N",
    "BOND_RTL_MKET_YN":"N",
    "MGCO_APTM_ODNO":"",
    "ORD_SVR_DVSN_CD":"0",
    "CTAC_TLNO":""
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "KRX_FWDG_ORD_ORGNO": "01790",
        "ODNO": "0000015402",
        "ORD_TMD": "104347"
    }
} |  |


### 장내채권 정정취소주문

- **TR_ID**: TTTC0953U
- **Method**: POST
- **URL**: `/uapi/domestic-bond/v1/trading/order-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "PDNO": "KR6095572D81",
    "ORGN_ODNO": "0000015402",
    "ORD_QTY2": "2",
    "BOND_ORD_UNPR": "10460",
    "QTY_ALL_ORD_YN": "Y",
    "RVSE_CNCL_DVSN_CD": "01",
    "MGCO_APTM_ODNO": "",
    "ORD_SVR_DVSN_CD": "0",
    "CTAC_TLNO": ""
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "KRX_FWDG_ORD_ORGNO": "01790",
        "ODNO": "0000015403",
        "ORD_TMD": "104448"
    }
} |  |


### 채권정정취소가능주문조회

- **TR_ID**: CTSC8035R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
ORD_DT:
ODNO:
CTX_AREA_FK200:
CTX_AREA_NK200: |  |
| Response Example | {
    "ctx_area_fk200": "0!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null                                                                                                                   ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output": [
        {
            "odno": "0000015401",
            "pdno": "KR6095572D81",
            "rvse_cncl_dvsn_name": "현금매수",
            "ord_qty": "1",
            "bond_ord_unpr": "10000.00",
            "ord_tmd": "104258",
            "tot_ccld_qty": "0",
            "tot_ccld_amt": "0",
            "ord_psbl_qty": "1",
            "orgn_odno": "",
            "sll_buy_dvsn_cd": "02",
            "ord_dvsn_cd": "01",
            "mgco_aptm_odno": "",
            "samt_mket_ptci_yn": "N",
            "prdt_abrv_name": "AJ네트웍스63-2"
        },
        {
            "odno": "0000015403",
            "pdno": "KR6095572D81",
            "rvse_cncl_dvsn_name": "현금매도",
            "ord_qty": "1",
            "bond_ord_unpr": "10460.00",
            "ord_tmd": "104448",
            "tot_ccld_qty": "0",
            "tot_ccld_amt": "0",
            "ord_psbl_qty": "1",
            "orgn_odno": "0000015402",
            "sll_buy_dvsn_cd": "01",
            "ord_dvsn_cd": "01",
            "mgco_aptm_odno": "",
            "samt_mket_ptci_yn": "N",
            "prdt_abrv_name": "AJ네트웍스63-2"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 장내채권 주문체결내역

- **TR_ID**: CTSC8013R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/trading/inquire-daily-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
INQR_STRT_DT:20240401
INQR_END_DT:20240425
SLL_BUY_DVSN_CD:%
SORT_SQN_DVSN:01
PDNO:
NCCS_YN:N
CTX_AREA_FK200:
CTX_AREA_NK200: |  |
| Response Example | {
    "ctx_area_nk200": " !^                                                                                                                                                                                                     ",
    "ctx_area_fk200": "null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^null!^%!^null                                                                                     ",
    "output1": [
        {
            "ord_dt": "20240425",
            "odno": "0000015201",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "1",
            "bond_ord_unpr": "10450.00",
            "ord_tmd": "102033",
            "tot_ccld_qty": "1",
            "bond_avg_unpr": "10250.00",
            "tot_ccld_amt": "1025",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015202",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "1",
            "bond_ord_unpr": "10450.00",
            "ord_tmd": "135029",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015203",
            "orgn_odno": "0000015202",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "매수취소*",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "1",
            "bond_ord_unpr": "0.00",
            "ord_tmd": "135108",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015204",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR101501D942",
            "prdt_abrv_name": "국민주택1종19-04",
            "ord_qty": "1",
            "bond_ord_unpr": "10929.90",
            "ord_tmd": "163441",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "1",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015205",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR103502G990",
            "prdt_abrv_name": "국고01125-3909(19-6)",
            "ord_qty": "1",
            "bond_ord_unpr": "7299.00",
            "ord_tmd": "163612",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "1",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015206",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR103502G990",
            "prdt_abrv_name": "국고01125-3909(19-6)",
            "ord_qty": "1",
            "bond_ord_unpr": "7299.00",
            "ord_tmd": "163618",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "1",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015207",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR2088012A16",
            "prdt_abrv_name": "경남지역개발20-01",
            "ord_qty": "1",
            "bond_ord_unpr": "10206.60",
            "ord_tmd": "163922",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "1",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015208",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수",
            "shtn_pdno": "KR2088012A16",
            "prdt_abrv_name": "경남지역개발20-01",
            "ord_qty": "1",
            "bond_ord_unpr": "10206.60",
            "ord_tmd": "164006",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "1",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015209",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수거부",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "2",
            "bond_ord_unpr": "10450.00",
            "ord_tmd": "170002",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015210",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수거부",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "1",
            "bond_ord_unpr": "10400.00",
            "ord_tmd": "170010",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015211",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수거부",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "5",
            "bond_ord_unpr": "10400.00",
            "ord_tmd": "170015",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        },
        {
            "ord_dt": "20240425",
            "odno": "0000015212",
            "orgn_odno": "",
            "ord_dvsn_name": "보통",
            "sll_buy_dvsn_cd_name": "현금매수거부",
            "shtn_pdno": "KR6095572D81",
            "prdt_abrv_name": "AJ네트웍스63-2",
            "ord_qty": "5",
            "bond_ord_unpr": "10200.00",
            "ord_tmd": "170019",
            "tot_ccld_qty": "0",
            "bond_avg_unpr": "0.00",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "buy_dt": "",
            "samt_mket_ptci_yn_name": "일반시장",
            "sprx_psbl_yn_ifom": "종합과세",
            "ord_mdia_dvsn_name": "33",
            "sll_buy_dvsn_cd": "02",
            "nccs_qty": "0",
            "ord_gno_brno": "01790"
        }
    ],
    "output2": {
        "tot_ord_qty": "6",
        "tot_ccld_qty_smtl": "1",
        "tot_bond_ccld_avg_unpr": "10250.00",
        "tot_ccld_amt_smtl": "1025"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 장내채권 잔고조회

- **TR_ID**: CTSC8407R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/trading/inquire-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
INQR_CNDT:00
PDNO:
BUY_DT:
CTX_AREA_FK200:
CTX_AREA_NK200: |  |
| Response Example | {
    "ctx_area_fk200": "!^!^null                                                                                                                                                                                                ",
    "ctx_area_nk200": " !^ !^                                                                                                                                                                                                  ",
    "output": [
        {
            "pdno": "KR101501D942",
            "prdt_name": "국민주택1종19-04",
            "buy_dt": "20240426",
            "buy_sqno": "1",
            "cblc_qty": "4",
            "agrx_qty": "4",
            "sprx_qty": "0",
            "exdt": "20240430",
            "buy_erng_rt": "0.00000000",
            "buy_unpr": "0",
            "buy_amt": "0",
            "ord_psbl_qty": "4"
        },
        {
            "pdno": "KR2088012A16",
            "prdt_name": "경남지역개발20-01",
            "buy_dt": "20240426",
            "buy_sqno": "1",
            "cblc_qty": "6",
            "agrx_qty": "5",
            "sprx_qty": "0",
            "exdt": "20250131",
            "buy_erng_rt": "0.00000000",
            "buy_unpr": "0",
            "buy_amt": "0",
            "ord_psbl_qty": "5"
        },
        {
            "pdno": "KR6003492D41",
            "prdt_name": "대한항공102-2",
            "buy_dt": "20240426",
            "buy_sqno": "1",
            "cblc_qty": "9",
            "agrx_qty": "9",
            "sprx_qty": "0",
            "exdt": "20260424",
            "buy_erng_rt": "0.00000000",
            "buy_unpr": "0",
            "buy_amt": "0",
            "ord_psbl_qty": "9"
        },
        {
            "pdno": "KR6095572D81",
            "prdt_name": "AJ네트웍스63-2",
            "buy_dt": "20240426",
            "buy_sqno": "1",
            "cblc_qty": "23",
            "agrx_qty": "22",
            "sprx_qty": "0",
            "exdt": "20250801",
            "buy_erng_rt": "0.00000000",
            "buy_unpr": "0",
            "buy_amt": "0",
            "ord_psbl_qty": "22"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 장내채권 매수가능조회

- **TR_ID**: TTTC8910R
- **Method**: GET
- **URL**: `/uapi/domestic-bond/v1/trading/inquire-psbl-order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
PDNO:KR6095572D81
BOND_ORD_UNPR:10450.0 |  |
| Response Example | {
    "output": {
        "ord_psbl_cash": "9285653",
        "ord_psbl_sbst": "117521",
        "ruse_psbl_amt": "0",
        "bond_ord_unpr2": "10450.00",
        "buy_psbl_amt": "9230271",
        "buy_psbl_qty": "8832",
        "cma_evlu_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |

