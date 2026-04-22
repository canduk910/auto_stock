# [국내선물옵션] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (15개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 191 | REST | (야간)선물옵션 증거금 상세 | (구) JTCE6003R (신) CTFN7107R | GET | `/uapi/domestic-futureoption/v1/trading/ngt-margin-detail` |  |
| 192 | REST | 선물옵션 총자산현황 | CTRP6550R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-deposit` |  |
| 193 | REST | 선물옵션기간약정수수료일별 | CTFO6119R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-daily-amount-fee` |  |
| 194 | REST | (야간)선물옵션 잔고현황 | (구) JTCE6001R (신) CTFN6118R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance` |  |
| 195 | REST | 선물옵션 잔고현황 | CTFO6118R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance` | ✓ |
| 196 | REST | 선물옵션 주문 | (주간 매수/매도) TTTO1101U (야간 매수/매도) (구) JTCE1001U (신) STTN1101U | POST | `/uapi/domestic-futureoption/v1/trading/order` | ✓ |
| 197 | REST | 선물옵션 잔고평가손익내역 | CTFO6159R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance-valuation-pl` |  |
| 198 | REST | 선물옵션 증거금률 | TTTO6032R | GET | `/uapi/domestic-futureoption/v1/quotations/margin-rate` |  |
| 199 | REST | 선물옵션 정정취소주문 | (주간 정정/취소) TTTO1103U (야간 정정/취소) (구) JTCE1002U (신) STTN1103U | POST | `/uapi/domestic-futureoption/v1/trading/order-rvsecncl` | ✓ |
| 200 | REST | 선물옵션 주문체결내역조회 | TTTO5201R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ccnl` |  |
| 201 | REST | (야간)선물옵션 주문체결 내역조회 | (구) JTCE5005R (신) STTN5201R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl` |  |
| 202 | REST | (야간)선물옵션 주문가능 조회 | (구) JTCE1004R (신) STTN5105R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order` |  |
| 203 | REST | 선물옵션 잔고정산손익내역 | CTFO6117R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance-settlement-pl` |  |
| 204 | REST | 선물옵션 주문가능 | TTTO5105R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-psbl-order` | ✓ |
| 205 | REST | 선물옵션 기준일체결내역 | CTFO5139R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ccnl-bstime` |  |

---

## 상세 명세

### (야간)선물옵션 증거금 상세

- **TR_ID**: (구) JTCE6003R (신) CTFN7107R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/ngt-margin-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:03
MGNA_DVSN_CD:01 |  |
| Response Example | {
    "output1": [
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        }
    ],
    "output2": [
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "0",
            "sbst_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "sbst_amt": "0",
            "tot_amt": "0"
        }
    ],
    "output3": {
        "bfdy_sbst_sll_sbst_amt": "0",
        "thdt_sbst_sll_sbst_amt": "0",
        "bfdy_sbst_sll_ccld_amt": "0",
        "thdt_sbst_sll_ccld_amt": "0",
        "opt_buy_exus_acnt_yn": "N",
        "base_dpsa_gdat_grad_cd": "03",
        "opt_dfpa": "0",
        "excc_dfpa": "0",
        "fee_amt": "0",
        "nxdy_dncl_amt": "100000000",
        "prsm_dpast_amt": "100000000",
        "opt_base_dpsa_gdat_grad_cd": "01"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 선물옵션 총자산현황

- **TR_ID**: CTRP6550R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-deposit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
} |  |
| Response Example | {
    "output": {
        "dnca_tota": "100000000",
        "bfdy_chck_amt": "0",
        "thdt_chck_amt": "0",
        "rlth_uwdl_dpos_amt": "0",
        "brkg_mgna_cash": "17907612",
        "wdrw_psbl_tot_amt": "34046775",
        "ord_psbl_cash": "64184775",
        "ord_psbl_tota": "64184775",
        "dnca_sbst": "0",
        "scts_sbst_amt": "0",
        "frcr_evlu_amt": "0",
        "brkg_mgna_sbst": "17907613",
        "sbst_rlse_psbl_amt": "0",
        "mtnc_rt": "418.23000000",
        "add_mgna_tota": "0",
        "add_mgna_cash": "0",
        "rcva": "0",
        "futr_trad_pfls": "0",
        "opt_trad_pfls_amt": "0",
        "trad_pfls_smtl": "0",
        "futr_evlu_pfls_amt": "4187500",
        "opt_evlu_pfls_amt": "-697500",
        "evlu_pfls_smtl": "3490000",
        "excc_dfpa": "-30138000",
        "opt_dfpa": "0",
        "brkg_fee": "0",
        "nxdy_dnca": "69862000",
        "prsm_dpast_amt": "69864500",
        "cash_mntn_amt": "0",
        "hack_acdt_acnt_move_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "APRP0126",
    "msg1": "조회이(가) 완료되었습니다.                                                      "
} |  |


### 선물옵션기간약정수수료일별

- **TR_ID**: CTFO6119R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-daily-amount-fee`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"INQR_STRT_DAY":"20230901",
	"INQR_END_DAY":"20230920",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "12345678!^03!^20230901!^20230920                                                                                                                                                                        ",
    "ctx_area_nk200": " !^                                                                                                                                                                                                     ",
    "output1": [
        {
            "ord_dt": "20230901",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230904",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230905",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230906",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230907",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230908",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230911",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230914",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230920",
            "pdno": "KR4101TC0008",
            "item_name": "F 202312",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "419375000",
            "buy_fee": "41140",
            "tot_fee_smtl": "41140",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230920",
            "pdno": "KR4201TA3409",
            "item_name": "C 202310 340.0",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "700000",
            "buy_fee": "2750",
            "tot_fee_smtl": "2750",
            "trad_pfls": "0"
        }
    ],
    "output2": {
        "futr_agrm": "0",
        "futr_agrm_amt": "419375000",
        "futr_agrm_amt_smtl": "419375000",
        "futr_sll_fee_smtl": "0",
        "futr_buy_fee_smtl": "41140",
        "futr_fee_smtl": "41140",
        "opt_agrm": "0",
        "opt_agrm_amt": "700000",
        "opt_agrm_amt_smtl": "700000",
        "opt_sll_fee_smtl": "0",
        "opt_buy_fee_smtl": "2750",
        "opt_fee_smtl": "2750",
        "prdt_futr_agrm": "0",
        "prdt_fuop": "0",
        "prdt_futr_evlu_amt": "0",
        "futr_fee": "0",
        "opt_fee": "0",
        "fee": "0",
        "sll_agrm_amt": "0",
        "buy_agrm_amt": "420075000",
        "agrm_amt_smtl": "420075000",
        "sll_fee": "0",
        "buy_fee": "43890",
        "fee_smtl": "43890",
        "trad_pfls_smtl": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### (야간)선물옵션 잔고현황

- **TR_ID**: (구) JTCE6001R (신) CTFN6118R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"ACNT_PWD":"",
	"MGNA_DVSN":"01",
	"EXCC_STAT_CD":"1",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "80012345^03^01^1^                                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [
        {
            "cano": "80012345",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101SC0009",
            "prdt_type_cd": "301",
            "shtn_pdno": "101S12",
            "prdt_name": "F 202212",
            "sll_buy_dvsn_cd": "02",
            "trad_dvsn_name": "매수",
            "cblc_qty": "3",
            "excc_unpr": "309.10000000",
            "ccld_avg_unpr1": "320.50000000",
            "idx_clpr": "307.45000000",
            "pchs_amt": "231825000",
            "evlu_amt": "230587500",
            "evlu_pfls_amt": "-1237500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "3"
        }
    ],
    "output2": {
        "dnca_cash": "10101527360",
        "frcr_dncl_amt": "0",
        "dnca_sbst": "0",
        "tot_dncl_amt": "10101527360",
        "cash_mgna": "108922232",
        "sbst_mgna": "133854708",
        "mgna_tota": "242776940",
        "opt_dfpa": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "-16200000",
        "fee": "0",
        "nxdy_dnca": "10085327360",
        "prsm_dpast": "10085327360",
        "pprt_ord_psbl_cash": "9858750420",
        "add_mgna_cash": "0",
        "add_mgna_tota": "0",
        "futr_trad_pfls_amt": "0",
        "opt_trad_pfls_amt": "0",
        "futr_evlu_pfls_amt": "-1237500",
        "opt_evlu_pfls_amt": "0",
        "trad_pfls_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "-1237500",
        "wdrw_psbl_tot_amt": "9858750420",
        "ord_psbl_cash": "9858750420",
        "ord_psbl_sbst": "0",
        "ord_psbl_tota": "9858750420",
        "mmga_tot_amt": "0",
        "mmga_cash_amt": "0",
        "mtnc_rt": "0.00000000",
        "isfc_amt": "0",
        "pchs_amt_smtl": "231825000",
        "evlu_amt_smtl": "230587500"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 선물옵션 잔고현황

- **TR_ID**: CTFO6118R
- **모의 TR_ID**: VTFO6118R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {    
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"3",
	"MGNA_DVSN": "01",
	"EXCC_STAT_CD": "1",
	"CTX_AREA_FK200": "",
	"CTX_AREA_NK200": ""
} |  |
| Response Example | {
  "ctx_area_fk200": "연속조회검색조건200을 입력하세요.",
  "output1": {
    "lqd_psbl_qty": [
      "6",
      "133",
      "110",
      "1000",
      "1000",
      "1000",
      "1000",
      "1",
      "25"
    ],
    "pdno": [
      "KR4101RC0000",
      "KR4101S30001",
      "KR4111RA0000",
      "KR41ACRC0005",
      "KR41ACS60004",
      "KR41ADRC0004",
      "KR41ADS30005",
      "KR41AES90007",
      "KR41DRRA0007"
    ],
    "prdt_type_cd": [
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301"
    ],
    "pchs_amt": [
      "586950000",
      "12937575000",
      "78980000",
      "3003000000",
      "3012000000",
      "5686000000",
      "5672000000",
      "2610000",
      "21350000"
    ],
    "sll_buy_dvsn_name": [
      "SLL",
      "BUY",
      "BUY",
      "BUY",
      "SLL",
      "BUY",
      "SLL",
      "SLL",
      "BUY"
    ],
    "trad_pfls_amt": [
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0"
    ],
    "shtn_pdno": [
      "101R12",
      "101S03",
      "111R10",
      "1ACR12",
      "1ACS06",
      "1ADR12",
      "1ADS03",
      "1AES09",
      "1DRR10"
    ],
    "acnt_prdt_cd": [
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      ""
    ],
    "cblc_qty": [
      "6",
      "133",
      "110",
      "1000",
      "1000",
      "1000",
      "1000",
      "1",
      "25"
    ],
    "excc_unpr": [
      "391.30000000",
      "389.10000000",
      "71800.00000000",
      "3003.00000000",
      "3012.00000000",
      "5686.00000000",
      "5672.00000000",
      "2610.00000000",
      "85400.00000000"
    ],
    "cano": [
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      ""
    ],
    "idx_clpr": [
      "380.55000000",
      "389.10000000",
      "71800.00000000",
      "3003.00000000",
      "3012.00000000",
      "5686.00000000",
      "5672.00000000",
      "2610.00000000",
      "85400.00000000"
    ],
    "ccld_avg_unpr1": [
      "402.28975400",
      "406.38538995",
      "71618.18181818",
      "4626.00000000",
      "4766.50000000",
      "6992.50000000",
      "5695.50000000",
      "3430.50000000",
      "87700.00000000"
    ],
    "evlu_pfls_amt": [
      "16125000",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0"
    ],
    "evlu_amt": [
      "570825000",
      "12937575000",
      "78980000",
      "3003000000",
      "3012000000",
      "5686000000",
      "5672000000",
      "2610000",
      "21350000"
    ],
    "prdt_name": [
      "F 202112",
      "F 202203",
      "SamsungEle F 202110 (  10)",
      "BBIG K-NewDeal     F 202112",
      "BBIG K-NewDeal     F 202206",
      "Battery K-NewDeal  F 202112",
      "Battery K-NewDeal  F 202203",
      "Bio K-NewDeal      F 202209",
      "C2S        F 202110 (  10)"
    ]
  },
  "rt_cd": "0",
  "output2": {
    "nxdy_dnca": "90016125000",
    "sbst_mgna": "1391065523",
    "cash_mgna": "0",
    "ord_psbl_tota": "88608934477",
    "opt_dfpa": "0",
    "fee": "0",
    "pchs_amt_smtl": "31000465000",
    "prsm_dpast": "90016125000",
    "evlu_pfls_amt_smtl": "16125000",
    "thdt_dfpa": "0",
    "prsm_dpast_amt": "90016125000",
    "frcr_dncl_amt": "0",
    "pprt_ord_psbl_cash": "88608934477",
    "evlu_amt_smtl": "30984340000",
    "futr_trad_pfls_amt": "0",
    "rnwl_dfpa": "16125000",
    "futr_evlu_pfls_amt": "16125000",
    "wdrw_psbl_tot_amt": "88608934477",
    "dnca_sbst": "0",
    "opt_evlu_pfls_amt": "0",
    "dnca_cash": "90000000000",
    "tot_dncl_amt": "90000000000",
    "nxdy_dncl_amt": "90016125000",
    "tot_ccld_amt": "0",
    "opt_trad_pfls_amt": "0",
    "trad_pfls_amt_smtl": "0",
    "ord_psbl_cash": "88608934477",
    "mgna_tota": "1391065523",
    "ord_psbl_sbst": "0",
    "add_mgna_tota": "0",
    "add_mgna_cash": "0"
  },
  "msg1": "조회 되었습니다. (마지막 자료) ",
  "msg_cd": "KIOK0460",
  "ctx_area_nk200": ""
} |  |


### 선물옵션 주문

- **TR_ID**: (주간 매수/매도) TTTO1101U (야간 매수/매도) (구) JTCE1001U (신) STTN1101U
- **모의 TR_ID**: (주간 매수/매도) VTTO1101U (야간은 모의투자 미제공)
- **Method**: POST
- **URL**: `/uapi/domestic-futureoption/v1/trading/order`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"ORD_PRCS_DVSN_CD":"02",
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",           
	"SLL_BUY_DVSN_CD":"02",
	"SHTN_PDNO":"167R12",
	"ORD_QTY":"1",
	"UNIT_PRICE":"123",
	"NMPR_TYPE_CD":"",
	"KRX_NMPR_CNDT_CD":"",
	"CTAC_TLNO":"",
	"FUOP_ITEM_DVSN_CD":"",
	"ORD_DVSN_CD":"01"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0029",
  "msg1": "주문전송이 정상적으로 처리되었습니다.",
  "output": {
    "ACNT_NAME": "류민수",
    "TRAD_DVSN_NAME": "매도",
    "ITEM_NAME": "코스피200 F 202203",
    "ORD_TMD": "131604",
    "ORD_GNO_BRNO": "06010",
    "ODNO": "0000007045"
  }
} |  |


### 선물옵션 잔고평가손익내역

- **TR_ID**: CTFO6159R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance-valuation-pl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"MGNA_DVSN":"02",
	"EXCC_STAT_CD":"1",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "12345678!^03!^02!^1                                                                                                                                                                                     ",
    "ctx_area_nk200": " !^ !^ !^                                                                                                                                                                                               ",
    "output1": [
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101T90003",
            "prdt_type_cd": "301",
            "shtn_pdno": "101T09",
            "prdt_name": "F 202309",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "2",
            "excc_unpr": "340.30000000",
            "ccld_avg_unpr1": "345.50000000",
            "idx_clpr": "0.00000000",
            "pchs_amt": "170150000",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "2"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101TC0008",
            "prdt_type_cd": "301",
            "shtn_pdno": "101T12",
            "prdt_name": "F 202312",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "5",
            "excc_unpr": "350.00000000",
            "ccld_avg_unpr1": "335.50000000",
            "idx_clpr": "353.35000000",
            "pchs_amt": "437500000",
            "evlu_amt": "441687500",
            "evlu_pfls_amt": "4187500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "5"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4175TA0001",
            "prdt_type_cd": "301",
            "shtn_pdno": "175T10",
            "prdt_name": "미국달러 F 202310",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "1",
            "excc_unpr": "1349.20000000",
            "ccld_avg_unpr1": "1338.60000000",
            "idx_clpr": "0.00000000",
            "pchs_amt": "13492000",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "1"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4201TA3409",
            "prdt_type_cd": "301",
            "shtn_pdno": "201T10340",
            "prdt_name": "C 202310 340.0",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "1",
            "excc_unpr": "2.80000000",
            "ccld_avg_unpr1": "2.80000000",
            "idx_clpr": "0.01000000",
            "pchs_amt": "700000",
            "evlu_amt": "2500",
            "evlu_pfls_amt": "-697500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "1"
        }
    ],
    "output2": {
        "dnca_cash": "100000000",
        "frcr_dncl_amt": "0",
        "dnca_sbst": "0",
        "tot_dncl_amt": "100000000",
        "tot_ccld_amt": "0",
        "cash_mgna": "0",
        "sbst_mgna": "23910150",
        "mgna_tota": "23910150",
        "opt_dfpa": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "-30138000",
        "fee": "0",
        "nxdy_dnca": "69862000",
        "nxdy_dncl_amt": "69862000",
        "prsm_dpast": "69864500",
        "prsm_dpast_amt": "69864500",
        "pprt_ord_psbl_cash": "64184775",
        "add_mgna_cash": "0",
        "add_mgna_tota": "0",
        "futr_trad_pfls_amt": "0",
        "opt_trad_pfls_amt": "0",
        "futr_evlu_pfls_amt": "4187500",
        "opt_evlu_pfls_amt": "-697500",
        "trad_pfls_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "3490000",
        "wdrw_psbl_tot_amt": "34046775",
        "ord_psbl_cash": "64184775",
        "ord_psbl_sbst": "0",
        "ord_psbl_tota": "64184775"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 선물옵션 증거금률

- **TR_ID**: TTTO6032R
- **모의 TR_ID**: 미지원
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/margin-rate`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 선물옵션 정정취소주문

- **TR_ID**: (주간 정정/취소) TTTO1103U (야간 정정/취소) (구) JTCE1002U (신) STTN1103U
- **모의 TR_ID**: (주간 정정/취소) VTTO1103U (야간은 모의투자 미제공)
- **Method**: POST
- **URL**: `/uapi/domestic-futureoption/v1/trading/order-rvsecncl`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "ORD_PRCS_DVSN_CD": "02",
    "CANO": "810XXXXX",
    "ACNT_PRDT_CD": "03",
    "RVSE_CNCL_DVSN_CD": "02",
    "ORGN_ODNO": "0000005605",
    "ORD_QTY": "1",
    "UNIT_PRICE": "460.00",
    "NMPR_TYPE_CD": "",
    "KRX_NMPR_CNDT_CD": "",
    "RMN_QTY_YN": "N",
    "CTAC_TLNO": "000 00000000",
    "FUOP_ITEM_DVSN_CD": "",
    "ORD_DVSN_CD": "01"
} |  |
| Response Example |  |  |


### 선물옵션 주문체결내역조회

- **TR_ID**: TTTO5201R
- **모의 TR_ID**: VTTO5201R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",
	"STRT_ORD_DT": "20211122",
	"END_ORD_DT": "20211122",
	"SLL_BUY_DVSN_CD": "00",
	"CCLD_NCCS_DVSN": "00",
	"SORT_SQN": "DS",
	"STRT_ODNO": "",
	"PDNO": "",
	"MKET_ID_CD": "00",
	"CTX_AREA_FK200": "",
	"CTX_AREA_NK200": ""
} |  |
| Response Example | {
  "ctx_area_fk200": "81055689^03^20220101^20220114^DS^                                                                                                                                                                       ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output1": [
    {
      "ord_gno_brno": "06010",
      "cano": "810XXXXX",
      "csac_name": "",
      "acnt_prdt_cd": "03",
      "ord_dt": "20220113",
      "odno": "0000007045",
      "orgn_odno": "0000000000",
      "sll_buy_dvsn_cd": "01",
      "trad_dvsn_name": "HTS SELL",
      "nmpr_type_cd": "01",
      "nmpr_type_name": "Limit Order",
      "pdno": "101S03",
      "prdt_name": "F 202203",
      "prdt_type_cd": "301",
      "ord_qty": "1",
      "ord_idx": "400.00",
      "qty": "0",
      "ord_tmd": "131604",
      "tot_ccld_qty": "1",
      "avg_idx": "400.00000000",
      "tot_ccld_amt": "100000000",
      "rjct_qty": "0",
      "ingr_trad_rjct_rson_cd": "00000",
      "ingr_trad_rjct_rson_name": "NORMAL",
      "ord_stfno": "Nsmart",
      "sprd_item_yn": "N",
      "ord_ip_addr": "P01032651641"
    },
    {
      "ord_gno_brno": "06010",
      "cano": "810XXXXX",
      "csac_name": "",
      "acnt_prdt_cd": "03",
      "ord_dt": "20220111",
      "odno": "0000007006",
      "orgn_odno": "0000007004",
      "sll_buy_dvsn_cd": "01",
      "trad_dvsn_name": "CANCEL CONFIRM",
      "nmpr_type_cd": "01",
      "nmpr_type_name": "Limit Order",
      "pdno": "101S03",
      "prdt_name": "F 202203",
      "prdt_type_cd": "301",
      "ord_qty": "1",
      "ord_idx": "0.00",
      "qty": "0",
      "ord_tmd": "150233",
      "tot_ccld_qty": "0",
      "avg_idx": "0.00000000",
      "tot_ccld_amt": "0",
      "rjct_qty": "0",
      "ingr_trad_rjct_rson_cd": "00000",
      "ingr_trad_rjct_rson_name": "NORMAL",
      "ord_stfno": "Nsmart",
      "sprd_item_yn": "N",
      "ord_ip_addr": "P01032651641"
    }
  ],
  "output2": {
    "tot_ord_qty": "4",
    "tot_ccld_amt_smtl": "200000000",
    "tot_ccld_qty_smtl": "2",
    "fee_smtl": "28570",
    "ctac_tlno": "01047859775"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### (야간)선물옵션 주문체결 내역조회

- **TR_ID**: (구) JTCE5005R (신) STTN5201R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"STRT_ORD_DT":"20220730",
	"END_ORD_DT":"20221214",
	"SLL_BUY_DVSN_CD":"00",
	"CCLD_NCCS_DVSN":"00",
	"SORT_SQN":"DS",
	"STRT_ODNO":"",
	"PDNO":"",
	"MKET_ID_CD":"00",
	"FUOP_DVSN_CD":"",
	"SCRN_DVSN":"00",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "81012345^03^20221214^20221214^DS^                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [],
    "output2": {
        "tot_ord_qty": "0",
        "tot_ccld_qty": "0",
        "tot_ccld_amt": "0",
        "fee": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
} |  |


### (야간)선물옵션 주문가능 조회

- **TR_ID**: (구) JTCE1004R (신) STTN5105R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"PDNO":"101T03",
	"PRDT_TYPE_CD":"301",
	"SLL_BUY_DVSN_CD":"02",
	"UNIT_PRICE":"",
	"ORD_DVSN_CD":"01"
} |  |
| Response Example | {
    "output": {
        "max_ord_psbl_qty": "996",
        "lqd_psbl_qty": "0",
        "ord_psbl_qty": "996"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 선물옵션 잔고정산손익내역

- **TR_ID**: CTFO6117R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance-settlement-pl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"INQR_DT":"20230906",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "12345678!^03!^20230906                                                                                                                                                                                  ",
    "ctx_area_nk200": " !^                                                                                                                                                                                                     ",
    "output1": [
        {
            "pdno": "101T09",
            "prdt_name": "F 202309",
            "trad_dvsn_name": "매수",
            "bfdy_cblc_qty": "2",
            "new_qty": "0",
            "mnpl_rpch_qty": "0",
            "cblc_qty": "2",
            "cblc_amt": "-425000",
            "trad_pfls_amt": "0",
            "evlu_amt": "149350000",
            "evlu_pfls_amt": "-1675000"
        }
    ],
    "output2": {
        "nxdy_dnca": "0",
        "mmga_cash": "0",
        "brkg_mgna_cash": "0",
        "opt_buy_chgs": "0",
        "opt_lqd_evlu_amt": "0",
        "dnca_sbst": "0",
        "mmga_tota": "0",
        "brkg_mgna_tota": "0",
        "opt_sll_chgs": "0",
        "fee": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "0",
        "dnca_cash": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 선물옵션 주문가능

- **TR_ID**: TTTO5105R
- **모의 TR_ID**: VTTO5105R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-psbl-order`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",
	"PDNO": "101R12",
	"SLL_BUY_DVSN_CD": "02",
	"UNIT_PRICE": "397.95",
	"ORD_DVSN_CD": "01"
} |  |
| Response Example | {
  "output": {
    "tot_psbl_qty": "11679",
    "lqd_psbl_qty1": "0",
    "ord_psbl_qty": "11665",
    "bass_idx": "379.67000000"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 선물옵션 기준일체결내역

- **TR_ID**: CTFO5139R
- **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ccnl-bstime`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"ORD_DT":"20230920",
	"FUOP_TR_STRT_TMD":"000000",
	"FUOP_TR_END_TMD":"240000",
	"CTX_AREA_FK200":"",
	'CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "12345678!^03!^20230920!^000000!^240000                                                                                                                                                                  ",
    "ctx_area_nk200": " !^ !^ !^                                                                                                                                                                                               ",
    "output1": [
        {
            "pdno": "201T10340",
            "prdt_name": "코스피200 C 202310 340.0",
            "odno": "0000219602",
            "tr_type_name": "지수콜옵션매수",
            "last_sttldt": "20231012",
            "ccld_idx": "2.80000000",
            "ccld_qty": "1",
            "trad_amt": "700000",
            "fee": "2758",
            "ccld_btwn": "140144"
        },
        {
            "pdno": "101T12",
            "prdt_name": "코스피200 F 202312",
            "odno": "0000219606",
            "tr_type_name": "지수선물매수",
            "last_sttldt": "20231214",
            "ccld_idx": "335.50000000",
            "ccld_qty": "5",
            "trad_amt": "419375000",
            "fee": "41144",
            "ccld_btwn": "140121"
        }
    ],
    "output2": {
        "tot_ccld_qty_smtl": "6",
        "tot_ccld_amt_smtl": "420075000",
        "fee_adjt": "43902",
        "fee_smtl": "43890"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |

