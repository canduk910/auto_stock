# [국내주식] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (23개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 5 | REST | 기간별계좌권리현황조회 | CTRGA011R | GET | `/uapi/domestic-stock/v1/trading/period-rights` |  |
| 6 | REST | 투자계좌자산현황조회 | CTRP6548R | GET | `/uapi/domestic-stock/v1/trading/inquire-account-balance` |  |
| 7 | REST | 퇴직연금 예수금조회 | TTTC0506R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-deposit` |  |
| 8 | REST | 주식예약주문정정취소 | (예약취소) CTSC0009U (예약정정) CTSC0013U | POST | `/uapi/domestic-stock/v1/trading/order-resv-rvsecncl` |  |
| 9 | REST | 신용매수가능조회 | TTTC8909R | GET | `/uapi/domestic-stock/v1/trading/inquire-credit-psamount` |  |
| 10 | REST | 주식통합증거금 현황 | TTTC0869R | GET | `/uapi/domestic-stock/v1/trading/intgr-margin` |  |
| 11 | REST | 퇴직연금 미체결내역 | TTTC2201R(기존 KRX만 가능), TTTC2210R (KRX,NXT/SOR) | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld` |  |
| 12 | REST | 기간별매매손익현황조회 | TTTC8715R | GET | `/uapi/domestic-stock/v1/trading/inquire-period-trade-profit` |  |
| 13 | REST | 주식주문(정정취소) | TTTC0013U | POST | `/uapi/domestic-stock/v1/trading/order-rvsecncl` | ✓ |
| 14 | REST | 주식예약주문조회 | CTSC0004R | GET | `/uapi/domestic-stock/v1/trading/order-resv-ccnl` |  |
| 15 | REST | 퇴직연금 매수가능조회 | TTTC0503R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-psbl-order` |  |
| 16 | REST | 주식잔고조회 | TTTC8434R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance` | ✓ |
| 17 | REST | 퇴직연금 체결기준잔고 | TTTC2202R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-present-balance` |  |
| 18 | REST | 매수가능조회 | TTTC8908R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-order` | ✓ |
| 19 | REST | 기간별손익일별합산조회 | TTTC8708R | GET | `/uapi/domestic-stock/v1/trading/inquire-period-profit` |  |
| 20 | REST | 주식주문(현금) | (매도) TTTC0011U (매수) TTTC0012U | POST | `/uapi/domestic-stock/v1/trading/order-cash` | ✓ |
| 21 | REST | 매도가능수량조회 | TTTC8408R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-sell` |  |
| 22 | REST | 주식일별주문체결조회 | (3개월이내) TTTC0081R (3개월이전) CTSC9215R | GET | `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` |  |
| 23 | REST | 주식정정취소가능주문조회 | TTTC0084R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl` |  |
| 24 | REST | 주식예약주문 | CTSC0008U | POST | `/uapi/domestic-stock/v1/trading/order-resv` |  |
| 25 | REST | 주식주문(신용) | (매도) TTTC0051U (매수) TTTC0052U | POST | `/uapi/domestic-stock/v1/trading/order-credit` |  |
| 26 | REST | 퇴직연금 잔고조회 | TTTC2208R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-balance` |  |
| 27 | REST | 주식잔고조회_실현손익 | TTTC8494R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance-rlz-pl` |  |

---

## 상세 명세

### 기간별계좌권리현황조회

- **TR_ID**: CTRGA011R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/period-rights`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | INQR_DVSN:03
CUST_RNCNO25:
HMID:
CANO:12345678
ACNT_PRDT_CD:01
INQR_STRT_DT:20240508
INQR_END_DT:20241106
RGHT_TYPE_CD:
PDNO:
PRDT_TYPE_CD:
CTX_AREA_NK100:
CTX_AREA_FK100: |  |
| Response Example | {
    "ctx_area_nk100": "                                                                                                    ",
    "ctx_area_fk100": "03!^!^!^12345678!^01!^20240508!^20241106!^!^!^                                                      ",
    "output": [
        {
            "acno10": "1234567801",
            "rght_type_cd": "01",
            "bass_dt": "20240919",
            "rght_cblc_type_cd": "01",
            "rptt_pdno": "00000A357880",
            "pdno": "00000A357880",
            "prdt_type_cd": "300",
            "shtn_pdno": "357880",
            "prdt_name": "비트나인",
            "cblc_qty": "1000",
            "last_alct_qty": "1050",
            "excs_alct_qty": "0",
            "tot_alct_qty": "1050",
            "last_ftsk_qty": "0.0000000000",
            "last_alct_amt": "0",
            "last_ftsk_chgs": "0",
            "rdpt_prca": "0",
            "dlay_int_amt": "0",
            "lstg_dt": "",
            "sbsc_end_dt": "20241011",
            "cash_dfrm_dt": "",
            "rqst_qty": "1000",
            "rqst_amt": "1865000",
            "rqst_dt": "20241011",
            "rfnd_dt": "",
            "rfnd_amt": "0",
            "lstg_stqt": "0",
            "tax_amt": "0",
            "sbsc_unpr": "1865.0000"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 투자계좌자산현황조회

- **TR_ID**: CTRP6548R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-account-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"01",
	"INQR_DVSN_1":"",
	"BSPR_BF_DT_APLY_YN":"",
} |  |
| Response Example | {
    "output1": [
        {
            "pchs_amt": "129105",
            "evlu_amt": "406000",
            "evlu_pfls_amt": "276895",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "406000",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "161026228",
            "evlu_amt": "185144504",
            "evlu_pfls_amt": "24118276",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "185144504",
            "whol_weit_rt": "0.01000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "1651434483743",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "1651434483743",
            "whol_weit_rt": "99.97000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "249855300",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "249855300",
            "whol_weit_rt": "0.01000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "161155333",
            "evlu_amt": "1651869889547",
            "evlu_pfls_amt": "24395171",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "1651869889547",
            "whol_weit_rt": "100.00000000"
        }
    ],
    "output2": {
        "pchs_amt_smtl": "161155333",
        "nass_tot_amt": "185550504",
        "loan_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "24395171",
        "evlu_amt_smtl": "185550504",
        "tot_asst_amt": "1651869889547",
        "tot_lnda_tot_ulst_lnda": "0",
        "cma_auto_loan_amt": "0",
        "tot_mgln_amt": "0",
        "stln_evlu_amt": "0",
        "crdt_fncg_amt": "0",
        "ocl_apl_loan_amt": "0",
        "pldg_stup_amt": "0",
        "frcr_evlu_tota": "1651434483743",
        "tot_dncl_amt": "249855300",
        "cma_evlu_amt": "0",
        "dncl_amt": "249855300",
        "tot_sbst_amt": "0",
        "thdt_rcvb_amt": "0",
        "ovrs_stck_evlu_amt1": "185144504.000000",
        "ovrs_bond_evlu_amt": "0.000000",
        "mmf_cma_mgge_loan_amt": "0",
        "sbsc_dncl_amt": "0",
        "pbst_sbsc_fnds_loan_use_amt": "0",
        "etpr_crdt_grnt_loan_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |


### 퇴직연금 예수금조회

- **TR_ID**: TTTC0506R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-deposit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"ACCA_DVSN_CD":"00"
} |  |
| Response Example | {
    "output": {
        "dnca_tota": "57622382",
        "nxdy_excc_amt": "11054042",
        "nxdy_sttl_amt": "0",
        "nx2_day_sttl_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식예약주문정정취소

- **TR_ID**: (예약취소) CTSC0009U (예약정정) CTSC0013U
- **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | { 
	"_comment": "주식예약주문취소", 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"RSVN_ORD_ORD_DT": "20220427", 
	"RSVN_ORD_SEQ": "39447", 
	"RSVN_ORD_ORGNO": "00" 
} 

{ 
	"_comment": "주식예약주문정정", 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"PDNO": "009150", 
	"ORD_QTY": "10", 
	"ORD_UNPR": "140000", 
	"SLL_BUY_DVSN_CD":"01", 
	"ORD_DVSN_CD":"00", 
	"ORD_OBJT_CBLC_DVSN_CD":"10", 
	"LOAN_DT":"", 
	"RSVN_ORD_END_DT":"", 
	"CTAC_TLNO": "", 
	"RSVN_ORD_SEQ":"39453", 
	"RSVN_ORD_ORGNO":"", 
	"RSVN_ORD_ORD_DT":"20220427" 
} |  |
| Response Example | { 
	"rt_cd": "0", 
	"msg_cd": "KIOK0430", 
	"msg1": "정상적으로 처리되었습니다", 
	"output": { 
		"NRML_PRCS_YN": "Y" 
	} 
} |  |


### 신용매수가능조회

- **TR_ID**: TTTC8909R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-credit-psamount`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "12345678",
"ACNT_PRDT_CD": "01",
"PDNO": "005930",
"ORD_UNPR" : "55000",
"ORD_DVSN": "01",
"CRDT_TYPE": "21",
"CMA_EVLU_AMT_ICLD_YN": "N",
"OVRS_ICLD_YN": "N"
} |  |
| Response Example | {
    "output": {
        "ord_psbl_cash": "99965177664",
        "ord_psbl_sbst": "156772560",
        "ruse_psbl_amt": "0",
        "fund_rpch_chgs": "0",
        "psbl_qty_calc_unpr": "69200",
        "nrcvb_buy_amt": "0",
        "nrcvb_buy_qty": "0",
        "max_buy_amt": "0",
        "max_buy_qty": "0",
        "cma_evlu_amt": "0",
        "ovrs_re_use_amt_wcrc": "0",
        "ord_psbl_frcr_amt_wcrc": "157998704172856"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식통합증거금 현황

- **TR_ID**: TTTC0869R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/intgr-margin`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
CMA_EVLU_AMT_ICLD_YN:N
WCRC_FRCR_DVSN_CD:01
FWEX_CTRT_FRCR_DVSN_CD:01 |  |
| Response Example | {
    "output": {
        "acmga_rt": "100.0000",
        "acmga_pct100_aptm_rson": "고객100%신청",
        "stck_cash_objt_amt": "249855306.0000",
        "stck_sbst_objt_amt": "137816.0000",
        "stck_evlu_objt_amt": "176966.0000",
        "stck_ruse_psbl_objt_amt": "261213.0000",
        "stck_fund_rpch_chgs_objt_amt": "0.0000",
        "stck_fncg_rdpt_objt_atm": "0.0000",
        "bond_ruse_psbl_objt_amt": "1024.0000",
        "stck_cash_use_amt": "240482730.0000",
        "stck_sbst_use_amt": "20295.0000",
        "stck_evlu_use_amt": "20295.0000",
        "stck_ruse_psbl_amt_use_amt": "261213.0000",
        "stck_fund_rpch_chgs_use_amt": "0.0000",
        "stck_fncg_rdpt_amt_use_amt": "0.0000",
        "bond_ruse_psbl_amt_use_amt": "1024.0000",
        "stck_cash_ord_psbl_amt": "9372576.0000",
        "stck_sbst_ord_psbl_amt": "117521.0000",
        "stck_evlu_ord_psbl_amt": "156671.0000",
        "stck_ruse_psbl_ord_psbl_amt": "0.0000",
        "stck_fund_rpch_ord_psbl_amt": "0.0000",
        "bond_ruse_psbl_ord_psbl_amt": "0.0000",
        "rcvb_amt": "0",
        "stck_loan_grta_ruse_psbl_amt": "0.0000",
        "stck_cash20_max_ord_psbl_amt": "8128560.1990",
        "stck_cash30_max_ord_psbl_amt": "8128560.1990",
        "stck_cash40_max_ord_psbl_amt": "8128560.1990",
        "stck_cash50_max_ord_psbl_amt": "8128560.1990",
        "stck_cash60_max_ord_psbl_amt": "8128560.1990",
        "stck_cash100_max_ord_psbl_amt": "8128560.1990",
        "stck_rsip100_max_ord_psbl_amt": "8128560.1990",
        "bond_max_ord_psbl_amt": "9316675.9443",
        "stck_fncg45_max_ord_psbl_amt": "20942905.49",
        "stck_fncg50_max_ord_psbl_amt": "18869350.4950",
        "stck_fncg60_max_ord_psbl_amt": "15750449.5868",
        "stck_fncg70_max_ord_psbl_amt": "13516343.26",
        "stck_stln_max_ord_psbl_amt": "9307424.0318",
        "lmt_amt": "0",
        "ovrs_stck_itgr_mgna_dvsn_name": "",
        "usd_objt_amt": "0.00",
        "usd_use_amt": "0.00",
        "usd_ord_psbl_amt": "0.00",
        "hkd_objt_amt": "0.00",
        "hkd_use_amt": "0.00",
        "hkd_ord_psbl_amt": "0.00",
        "jpy_objt_amt": "0.00",
        "jpy_use_amt": "0.00",
        "jpy_ord_psbl_amt": "0.00",
        "cny_objt_amt": "0.00",
        "cny_use_amt": "0.00",
        "cny_ord_psbl_amt": "0.00",
        "usd_ruse_objt_amt": "0.00",
        "usd_ruse_amt": "0.00",
        "usd_ruse_ord_psbl_amt": "0.00",
        "hkd_ruse_objt_amt": "0.00",
        "hkd_ruse_amt": "0.00",
        "hkd_ruse_ord_psbl_amt": "0.00",
        "jpy_ruse_objt_amt": "0.00",
        "jpy_ruse_amt": "0.00",
        "jpy_ruse_ord_psbl_amt": "0.00",
        "cny_ruse_objt_amt": "0.00",
        "cny_ruse_amt": "0.00",
        "cny_ruse_ord_psbl_amt": "0.00",
        "usd_gnrl_ord_psbl_amt": "0.00",
        "usd_itgr_ord_psbl_amt": "0.00",
        "hkd_gnrl_ord_psbl_amt": "0.00",
        "hkd_itgr_ord_psbl_amt": "0.00",
        "jpy_gnrl_ord_psbl_amt": "0.00",
        "jpy_itgr_ord_psbl_amt": "0.00",
        "cny_gnrl_ord_psbl_amt": "0.00",
        "cny_itgr_ord_psbl_amt": "0.00",
        "stck_itgr_cash20_ord_psbl_amt": "0.00",
        "stck_itgr_cash30_ord_psbl_amt": "0.00",
        "stck_itgr_cash40_ord_psbl_amt": "0.00",
        "stck_itgr_cash50_ord_psbl_amt": "0.00",
        "stck_itgr_cash60_ord_psbl_amt": "0.00",
        "stck_itgr_cash100_ord_psbl_amt": "0.00",
        "stck_itgr_100_ord_psbl_amt": "0.00",
        "stck_itgr_fncg45_ord_psbl_amt": "0.00",
        "stck_itgr_fncg50_ord_psbl_amt": "0.00",
        "stck_itgr_fncg60_ord_psbl_amt": "0.00",
        "stck_itgr_fncg70_ord_psbl_amt": "0.00",
        "stck_itgr_stln_ord_psbl_amt": "0.00",
        "bond_itgr_ord_psbl_amt": "0.00",
        "stck_cash_ovrs_use_amt": "0.00",
        "stck_sbst_ovrs_use_amt": "0.00",
        "stck_evlu_ovrs_use_amt": "0.00",
        "stck_re_use_amt_ovrs_use_amt": "0.00",
        "stck_fund_rpch_ovrs_use_amt": "0.00",
        "stck_fncg_rdpt_ovrs_use_amt": "0.00",
        "bond_re_use_ovrs_use_amt": "0.00",
        "usd_oth_mket_use_amt": "0.00",
        "jpy_oth_mket_use_amt": "0.00",
        "cny_oth_mket_use_amt": "0.00",
        "hkd_oth_mket_use_amt": "0.00",
        "usd_re_use_oth_mket_use_amt": "0.00",
        "jpy_re_use_oth_mket_use_amt": "0.00",
        "cny_re_use_oth_mket_use_amt": "0.00",
        "hkd_re_use_oth_mket_use_amt": "0.00",
        "hgkg_cny_re_use_amt": "0.00",
        "hgkg_cny_re_use_objt_amt": "0.00",
        "hgkg_cny_re_use_ord_psbl_amt": "0.00",
        "hgkg_cny_re_use_oth_use_amt": "0.00"
        "hgkg_cny_re_use_oth_use_amt": "0.00",
        "usd_frst_bltn_exrt": "1467.00000000",
        "hkd_frst_bltn_exrt": "188.61000000",
        "jpy_frst_bltn_exrt": "10.06000000",
        "cny_frst_bltn_exrt": "200.70000000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 퇴직연금 미체결내역

- **TR_ID**: TTTC2201R(기존 KRX만 가능), TTTC2210R (KRX,NXT/SOR)
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"USER_DVSN_CD":"%%",
	"SLL_BUY_DVSN_CD":"00",
	"CCLD_NCCS_DVSN":"%%",
	"INQR_DVSN_3":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "63512345^29^%%^00^%%^00^                                                                            ",
    "ctx_area_nk100": "^^                                                                                                  ",
    "output": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0490",
    "msg1": "조회가 계속됩니다                                                               "
} |  |


### 기간별매매손익현황조회

- **TR_ID**: TTTC8715R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-period-trade-profit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"PDNO":"",
"INQR_STRT_DT":"20240216",
"INQR_END_DT":"20240216",
"SORT_DVSN":"02",
"CBLC_DVSN":"00",
"CTX_AREA_FK100":""
"CTX_AREA_FK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "                                                                                                    ",
    "ctx_area_nk100": "20240216^00000A000120^300^0^00000000^                                                               ",
    "output1": [
        {
            "trad_dt": "20240216",
            "pdno": "000J2552221D",
            "prdt_name": "SG 17WR",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "135",
            "buy_qty": "2",
            "buy_amt": "271",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "000J00532219",
            "prdt_name": "국동 9WR",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "130",
            "buy_qty": "10",
            "buy_amt": "1300",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000Q520057",
            "prdt_name": "미래에셋 인버스 2X 코스닥150 선물 ETN",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "9365",
            "buy_qty": "1",
            "buy_amt": "9365",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A900270",
            "prdt_name": "헝셩그룹",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "66",
            "pchs_unpr": "322",
            "buy_qty": "66",
            "buy_amt": "21252",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A402340",
            "prdt_name": "SK스퀘어",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "59000",
            "buy_qty": "10",
            "buy_amt": "590000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A373220",
            "prdt_name": "LG에너지솔루션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "552000",
            "buy_qty": "10",
            "buy_amt": "5520000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A361610",
            "prdt_name": "SK아이이테크놀로지",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "110000",
            "buy_qty": "10",
            "buy_amt": "1100000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A352820",
            "prdt_name": "하이브",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "383000",
            "buy_qty": "2",
            "buy_amt": "766000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A302440",
            "prdt_name": "SK바이오사이언스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "100000",
            "buy_qty": "10",
            "buy_amt": "1000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A298050",
            "prdt_name": "효성첨단소재",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "480000",
            "buy_qty": "2",
            "buy_amt": "960000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A298020",
            "prdt_name": "효성티앤씨",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "365000",
            "buy_qty": "2",
            "buy_amt": "730000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A285130",
            "prdt_name": "SK케미칼",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "100000",
            "buy_qty": "10",
            "buy_amt": "1000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A136480",
            "prdt_name": "하림",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "220",
            "pchs_unpr": "2893",
            "buy_qty": "226",
            "buy_amt": "526563",
            "sll_pric": "2936",
            "sll_qty": "7",
            "sll_amt": "20555",
            "rlzt_pfls": "304",
            "pfls_rt": "1.50116044",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A114090",
            "prdt_name": "GKL",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "15010",
            "buy_qty": "1",
            "buy_amt": "15010",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A097950",
            "prdt_name": "CJ제일제당",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "210500",
            "buy_qty": "10",
            "buy_amt": "2105000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A096770",
            "prdt_name": "SK이노베이션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "228000",
            "buy_qty": "10",
            "buy_amt": "2280000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A093370",
            "prdt_name": "후성",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "15510",
            "buy_qty": "2",
            "buy_amt": "31020",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A057050",
            "prdt_name": "현대홈쇼핑",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "30100",
            "buy_qty": "2",
            "buy_amt": "60200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A047050",
            "prdt_name": "포스코인터내셔널",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "74400",
            "buy_qty": "2",
            "buy_amt": "148800",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A036460",
            "prdt_name": "한국가스공사",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "27850",
            "buy_qty": "2",
            "buy_amt": "55700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035760",
            "prdt_name": "CJ ENM",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "11",
            "pchs_unpr": "58836",
            "buy_qty": "11",
            "buy_amt": "647200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035420",
            "prdt_name": "NAVER",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "356000",
            "buy_qty": "10",
            "buy_amt": "3560000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035250",
            "prdt_name": "강원랜드",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "20950",
            "buy_qty": "10",
            "buy_amt": "209500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A034730",
            "prdt_name": "SK",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "182700",
            "buy_qty": "10",
            "buy_amt": "1827000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A030200",
            "prdt_name": "KT",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "26050",
            "buy_qty": "10",
            "buy_amt": "260500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A028670",
            "prdt_name": "팬오션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "4865",
            "buy_qty": "2",
            "buy_amt": "9730",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A028260",
            "prdt_name": "삼성물산",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "5",
            "pchs_unpr": "156100",
            "buy_qty": "5",
            "buy_amt": "780500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A018260",
            "prdt_name": "삼성에스디에스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "250000",
            "buy_qty": "2",
            "buy_amt": "500000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A017670",
            "prdt_name": "SK텔레콤",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "50100",
            "buy_qty": "10",
            "buy_amt": "501000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A015760",
            "prdt_name": "한국전력",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "4",
            "pchs_unpr": "8030",
            "buy_qty": "4",
            "buy_amt": "32120",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A011790",
            "prdt_name": "SKC",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "49950",
            "buy_qty": "10",
            "buy_amt": "499500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A011780",
            "prdt_name": "금호석유",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "200000",
            "buy_qty": "10",
            "buy_amt": "2000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A009540",
            "prdt_name": "HD한국조선해양",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "170000",
            "buy_qty": "10",
            "buy_amt": "1700000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A008770",
            "prdt_name": "호텔신라",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "99850",
            "buy_qty": "2",
            "buy_amt": "199700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A006260",
            "prdt_name": "LS",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "122000",
            "buy_qty": "10",
            "buy_amt": "1220000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005940",
            "prdt_name": "NH투자증권",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "11710",
            "buy_qty": "10",
            "buy_amt": "117100",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1414",
            "pchs_unpr": "53213",
            "buy_qty": "1415",
            "buy_amt": "75510700",
            "sll_pric": "75900",
            "sll_qty": "1",
            "sll_amt": "75900",
            "rlzt_pfls": "22687",
            "pfls_rt": "42.63431868",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005490",
            "prdt_name": "POSCO홀딩스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "133500",
            "buy_qty": "10",
            "buy_amt": "1335000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005380",
            "prdt_name": "현대차",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "240500",
            "buy_qty": "2",
            "buy_amt": "481000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A004800",
            "prdt_name": "효성",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "66400",
            "buy_qty": "2",
            "buy_amt": "132800",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A003670",
            "prdt_name": "포스코퓨처엠",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "531000",
            "buy_qty": "2",
            "buy_amt": "1062000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A003550",
            "prdt_name": "LG",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "105600",
            "buy_qty": "2",
            "buy_amt": "211200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A002380",
            "prdt_name": "KCC",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "252000",
            "buy_qty": "1",
            "buy_amt": "252000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A001120",
            "prdt_name": "LX인터내셔널",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "34050",
            "buy_qty": "1",
            "buy_amt": "34050",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000990",
            "prdt_name": "DB하이텍",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "23000",
            "buy_qty": "2",
            "buy_amt": "46000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000670",
            "prdt_name": "영풍",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "4",
            "pchs_unpr": "640750",
            "buy_qty": "4",
            "buy_amt": "2563000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000660",
            "prdt_name": "SK하이닉스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "12",
            "pchs_unpr": "122583",
            "buy_qty": "10",
            "buy_amt": "1345000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000270",
            "prdt_name": "기아",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "84500",
            "buy_qty": "10",
            "buy_amt": "845000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000240",
            "prdt_name": "한국앤컴퍼니",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "23850",
            "buy_qty": "2",
            "buy_amt": "47700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000210",
            "prdt_name": "DL",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "50400",
            "buy_qty": "10",
            "buy_amt": "504000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        }
    ],
    "output2": {
        "sll_qty_smtl": "8",
        "sll_tr_amt_smtl": "96455",
        "sll_fee_smtl": "0",
        "sll_tltx_smtl": "0",
        "sll_excc_amt_smtl": "96455",
        "buyqty_smtl": "2003",
        "buy_tr_amt_smtl": "116697331",
        "buy_fee_smtl": "0",
        "buy_tax_smtl": "0",
        "buy_excc_amt_smtl": "116697331",
        "tot_qty": "2011",
        "tot_tr_amt": "116793786",
        "tot_fee": "0",
        "tot_tltx": "0",
        "tot_excc_amt": "116793786",
        "tot_rlzt_pfls": "22991",
        "loan_int": "0",
        "tot_pftrt": "31.29560057"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0500",
    "msg1": "조회가 계속됩니다..다음버튼을 Click 하십시오.                                   "
} |  |


### 주식주문(정정취소)

- **TR_ID**: TTTC0013U
- **모의 TR_ID**: VTTC0013U
- **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-rvsecncl`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"KRX_FWDG_ORD_ORGNO": "",
"ORGN_ODNO": "0001566017",
"ORD_DVSN": "00",
"RVSE_CNCL_DVSN_CD": "01",
"ORD_QTY": "1",
"ORD_UNPR": "180000",
"QTY_ALL_ORD_YN": "N"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569139",
    "ORD_TMD": "131438"
  }
} |  |


### 주식예약주문조회

- **TR_ID**: CTSC0004R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"RSVN_ORD_ORD_DT":"20220520",
	"RSVN_ORD_END_DT":"20220523",
	"RSVN_ORD_SEQ":"",
	"TMNL_MDIA_KIND_CD":"00",
	"CANO":"81019970",
	"ACNT_PRDT_CD":"01",
	
	"PRCS_DVSN_CD":"0",
	"CNCL_YN":"Y",
	"PDNO":"",
	"SLL_BUY_DVSN_CD":"",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
} |  |
| Response Example | {
    "ctx_area_fk200": "20220520!^null!^0!^Y!^!^                                                                                                                                                                                ",
    "ctx_area_nk200": " !^ !^                                                                                                                                                                                                  ",
    "output": [
        {
            "rsvn_ord_seq": "42401",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "165318",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": "20220523"
        },
        {
            "rsvn_ord_seq": "42405",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "170422",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": ""
        },
        {
            "rsvn_ord_seq": "42406",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "170453",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": "20220523"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 퇴직연금 매수가능조회

- **TR_ID**: TTTC0503R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-psbl-order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"PDNO":"029513",
	"ORD_UNPR":"55000",
	"ORD_DVSN":"00",
	"CMA_EVLU_AMT_ICLD_YN":"N",
	"ACCA_DVSN_CD":"00"
} |  |
| Response Example | {
    "output": {
        "ord_psbl_cash": "11054042",
        "ruse_psbl_amt": "0",
        "psbl_qty_calc_unpr": "55000",
        "max_buy_amt": "11054042",
        "max_buy_qty": "200"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식잔고조회

- **TR_ID**: TTTC8434R
- **모의 TR_ID**: VTTC8434R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-balance`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"AFHR_FLPR_YN": "N",
	"OFL_YN": "",
	"INQR_DVSN": "01",
	"UNPR_DVSN": "01",
	"FUND_STTL_ICLD_YN": "N",
	"FNCG_AMT_AUTO_RDPT_YN": "N",
	"PRCS_DVSN": "01",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": ""
} |  |
| Response Example | {
  "ctx_area_fk100": "81055689^01^N^N^01^01^N^                                                                            ",
  "ctx_area_nk100": "                                                                                                    ",
  "output1": [
    {
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "trad_dvsn_name": "현금",
      "bfdy_buy_qty": "12",
      "bfdy_sll_qty": "0",
      "thdt_buyqty": "1686",
      "thdt_sll_qty": "41",
      "hldg_qty": "1657",
      "ord_psbl_qty": "1611",
      "pchs_avg_pric": "135440.2517",
      "pchs_amt": "224424497",
      "prpr": "0",
      "evlu_amt": "0",
      "evlu_pfls_amt": "0",
      "evlu_pfls_rt": "0.00",
      "evlu_erng_rt": "0.00000000",
      "loan_dt": "",
      "loan_amt": "0",
      "stln_slng_chgs": "0",
      "expd_dt": "",
      "fltt_rt": "-100.00000000",
      "bfdy_cprs_icdc": "-184500",
      "item_mgna_rt_name": "",
      "grta_rt_name": "",
      "sbst_pric": "140220",
      "stck_loan_unpr": "0.0000"
    },
    {
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "trad_dvsn_name": "자기융자",
      "bfdy_buy_qty": "3",
      "bfdy_sll_qty": "0",
      "thdt_buyqty": "0",
      "thdt_sll_qty": "0",
      "hldg_qty": "3",
      "ord_psbl_qty": "3",
      "pchs_avg_pric": "123000.0000",
      "pchs_amt": "369000",
      "prpr": "0",
      "evlu_amt": "0",
      "evlu_pfls_amt": "0",
      "evlu_pfls_rt": "0.00",
      "evlu_erng_rt": "0.00000000",
      "loan_dt": "20211223",
      "loan_amt": "369000",
      "stln_slng_chgs": "0",
      "expd_dt": "",
      "fltt_rt": "-100.00000000",
      "bfdy_cprs_icdc": "-184500",
      "item_mgna_rt_name": "",
      "grta_rt_name": "",
      "sbst_pric": "140220",
      "stck_loan_unpr": "123000.0000"
    }
	  ],
  "output2": [
        {
            "dnca_tot_amt": "346455",
            "nxdy_excc_amt": "346455",
            "prvs_rcdl_excc_amt": "346455",
            "cma_evlu_amt": "0",
            "bfdy_buy_amt": "0",
            "thdt_buy_amt": "0",
            "nxdy_auto_rdpt_amt": "0",
            "bfdy_sll_amt": "0",
            "thdt_sll_amt": "0",
            "d2_auto_rdpt_amt": "0",
            "bfdy_tlex_amt": "0",
            "thdt_tlex_amt": "0",
            "tot_loan_amt": "0",
            "scts_evlu_amt": "1759600",
            "tot_evlu_amt": "2106055",
            "nass_amt": "2106055",
            "fncg_gld_auto_rdpt_yn": "",
            "pchs_amt_smtl_amt": "2516522",
            "evlu_amt_smtl_amt": "1759600",
            "evlu_pfls_smtl_amt": "-756922",
            "tot_stln_slng_chgs": "0",
            "bfdy_tot_asst_evlu_amt": "2142945",
            "asst_icdc_amt": "-36890",
            "asst_icdc_erng_rt": "0.00000000"
        }
    ],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 퇴직연금 체결기준잔고

- **TR_ID**: TTTC2202R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-present-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"USER_DVSN_CD":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "63512345^29^00^                                                                                     ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "cblc_dvsn": "01",
            "cblc_dvsn_name": "사용자",
            "pdno": "069500",
            "prdt_name": "KODEX 200",
            "hldg_qty": "6",
            "slpsb_qty": "6",
            "pchs_avg_pric": "35670.0000",
            "evlu_pfls_amt": "-3330",
            "evlu_pfls_rt": "-1.56",
            "prpr": "35115",
            "evlu_amt": "210690",
            "pchs_amt": "214020",
            "cblc_weit": "53.06651890"
        },
        {
            "cblc_dvsn": "01",
            "cblc_dvsn_name": "사용자",
            "pdno": "091160",
            "prdt_name": "KODEX 반도체",
            "hldg_qty": "7",
            "slpsb_qty": "7",
            "pchs_avg_pric": "35820.0000",
            "evlu_pfls_amt": "-64400",
            "evlu_pfls_rt": "-25.68",
            "prpr": "26620",
            "evlu_amt": "186340",
            "pchs_amt": "250740",
            "cblc_weit": "46.93348110"
        }
    ],
    "output2": [
        {
            "pchs_amt_smtl_amt": "464760",
            "evlu_amt_smtl_amt": "397030",
            "evlu_pfls_smtl_amt": "-67730",
            "trad_pfls_smtl": "0",
            "thdt_tot_pfls_amt": "-67730",
            "pftrt": "-14.57311300"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 매수가능조회

- **TR_ID**: TTTC8908R
- **모의 TR_ID**: VTTC8908R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-order`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"PDNO": "005930",
	"ORD_UNPR": "0",
	"ORD_DVSN": "01",
	"CMA_EVLU_AMT_ICLD_YN": "N",
	"OVRS_ICLD_YN": "N"
} |  |
| Response Example | {
  "output": {
    "ord_psbl_cash": "741191178",
    "ord_psbl_sbst": "0",
    "ruse_psbl_amt": "0",
    "fund_rpch_chgs": "0",
    "psbl_qty_calc_unpr": "70000",
    "nrcvb_buy_amt": "107177377",
    "nrcvb_buy_qty": "1531",
    "max_buy_amt": "1482382356",
    "max_buy_qty": "21176",
    "cma_evlu_amt": "0",
    "ovrs_re_use_amt_wcrc": "0",
    "ord_psbl_frcr_amt_wcrc": "1468797045293"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 기간별손익일별합산조회

- **TR_ID**: TTTC8708R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-period-profit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"PDNO":"",
"INQR_STRT_DT":"20230101",
"INQR_END_DT":"20240220",
"SORT_DVSN":"00",
"INQR_DVSN":"00",
"CBLC_DVSN":"00",
"CTX_AREA_FK100":"",
"CTX_AREA_NK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "                                                                                                    ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "trad_dt": "20240220",
            "buy_amt": "116697331",
            "sll_amt": "96455",
            "rlzt_pfls": "22991",
            "fee": "0",
            "loan_int": "0",
            "tl_tax": "0",
            "pfls_rt": "31.29560057",
            "sll_qty1": "8",
            "buy_qty1": "2003"
        }
    ],
    "output2": {
        "sll_qty_smtl": "8",
        "sll_tr_amt_smtl": "96455",
        "sll_fee_smtl": "0",
        "sll_tltx_smtl": "0",
        "sll_excc_amt_smtl": "96455",
        "buy_qty_smtl": "2003",
        "buy_tr_amt_smtl": "116697331",
        "buy_fee_smtl": "0",
        "buy_tax_smtl": "0",
        "buy_excc_amt_smtl": "116697331",
        "tot_qty": "2011",
        "tot_tr_amt": "116793786",
        "tot_fee": "0",
        "tot_tltx": "0",
        "tot_excc_amt": "116793786",
        "tot_rlzt_pfls": "22991",
        "loan_int": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식주문(현금)

- **TR_ID**: (매도) TTTC0011U (매수) TTTC0012U
- **모의 TR_ID**: (매도) VTTC0011U (매수) VTTC0012U
- **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-cash`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"PDNO": "009150",
	"ORD_DVSN": "00",
	"ORD_QTY": "3",
	"ORD_UNPR": "150000"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569157",
    "ORD_TMD": "155211"
  }
} |  |


### 매도가능수량조회

- **TR_ID**: TTTC8408R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-sell`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
PDNO:005930 |  |
| Response Example | {
    "output": {
        "pdno": "005930",
        "prdt_name": "삼성전자",
        "buy_qty": "1746",
        "sll_qty": "2",
        "cblc_qty": "1744",
        "nsvg_qty": "0",
        "ord_psbl_qty": "1744",
        "pchs_avg_pric": "54388.4874",
        "pchs_amt": "0",
        "now_pric": "75800",
        "evlu_amt": "132195200",
        "evlu_pfls_amt": "37341678",
        "evlu_pfls_rt": "39.36"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0420",
    "msg1": "정상적으로 조회되었습니다                                                       "
} |  |


### 주식일별주문체결조회

- **TR_ID**: (3개월이내) TTTC0081R (3개월이전) CTSC9215R
- **모의 TR_ID**: (3개월이내) VTTC0081R (3개월이전) VTSC9215R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-daily-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "12345678",
	"ACNT_PRDT_CD": "01",
	"INQR_STRT_DT": "20211101",
	"INQR_END_DT": "20211101",
	"SLL_BUY_DVSN_CD": "00",
	"INQR_DVSN": "00",
	"PDNO": "",
	"CCLD_DVSN": "00",
	"ORD_GNO_BRNO": "",
	"ODNO": "",
	"INQR_DVSN_3": "00",
	"INQR_DVSN_1": "",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": ""
} |  |
| Response Example | {
  "ctx_area_fk100": "12345678^01^20220103^20220103^ ^00^00^                                                              ",
  "ctx_area_nk100": "                                                                                                    ",
  "output1": [
    {
      "ord_dt": "20220103",
      "ord_gno_brno": "06010",
      "odno": "0001568197",
      "orgn_odno": "",
      "ord_dvsn_name": "Limit",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "BUY REJECT",
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "ord_qty": "10",
      "ord_unpr": "150000",
      "ord_tmd": "170100",
      "tot_ccld_qty": "0",
      "avg_prvs": "0",
      "cncl_yn": "",
      "tot_ccld_amt": "0",
      "loan_dt": "",
      "ordr_empno": "Nsmart",
      "ord_dvsn_cd": "00",
      "cncl_cfrm_qty": "0",
      "rmn_qty": "0",
      "rjct_qty": "10",
      "ccld_cndt_name": "None",
      "inqr_ip_addr": "...",
      "cpbc_ordp_ord_rcit_dvsn_cd": "",
      "cpbc_ordp_infm_mthd_dvsn_cd": "",
      "infm_tmd": "",
      "ctac_tlno": "01047859775",
      "prdt_type_cd": "300",
      "excg_dvsn_cd": "02",
      "cpbc_ordp_mtrl_dvsn_cd": "11",
      "ord_orgno": "00000",
      "rsvn_ord_end_dt": ""
    },
    {
      "ord_dt": "20220103",
      "ord_gno_brno": "06010",
      "odno": "0001568196",
      "orgn_odno": "",
      "ord_dvsn_name": "Limit",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "BUY REJECT",
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "ord_qty": "10",
      "ord_unpr": "150000",
      "ord_tmd": "170038",
      "tot_ccld_qty": "0",
      "avg_prvs": "0",
      "cncl_yn": "",
      "tot_ccld_amt": "0",
      "loan_dt": "",
      "ordr_empno": "Nsmart",
      "ord_dvsn_cd": "00",
      "cncl_cfrm_qty": "0",
      "rmn_qty": "0",
      "rjct_qty": "10",
      "ccld_cndt_name": "None",
      "inqr_ip_addr": "P01.012.345.678",
      "cpbc_ordp_ord_rcit_dvsn_cd": "",
      "cpbc_ordp_infm_mthd_dvsn_cd": "",
      "infm_tmd": "",
      "ctac_tlno": "01047859775",
      "prdt_type_cd": "300",
      "excg_dvsn_cd": "02",
      "cpbc_ordp_mtrl_dvsn_cd": "11",
      "ord_orgno": "00000",
      "rsvn_ord_end_dt": ""
	}
		],
  "output2": {
    "tot_ord_qty": "281",
    "tot_ccld_qty": "0",
    "tot_ccld_amt": "0",
    "prsm_tlex_smtl": "0",
    "pchs_avg_pric": "0.0000"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식정정취소가능주문조회

- **TR_ID**: TTTC0084R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"ACNT_PRDT_CD": "01",
	"CANO": "810XXXXX",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": "",
	"INQR_DVSN_1": "0",
	"INQR_DVSN_2": "0"
} |  |
| Response Example | {
  "ctx_area_fk100": "81055689^01^                                                                                        ",
  "ctx_area_nk100": "                                                                                                    ",
  "output": [
    {
      "ord_gno_brno": "06010",
      "odno": "0001569139",
      "orgn_odno": "0001569136",
      "ord_dvsn_name": "지정가",
      "pdno": "009150",
      "prdt_name": "SamsungElecMech",
      "rvse_cncl_dvsn_name": "BUY AMEND*",
      "ord_qty": "1",
      "ord_unpr": "140000",
      "ord_tmd": "131438",
      "tot_ccld_qty": "0",
      "tot_ccld_amt": "0",
      "psbl_qty": "1",
      "sll_buy_dvsn_cd": "02",
      "ord_dvsn_cd": "00",
      "mgco_aptm_odno": ""
    },
    {
      "ord_gno_brno": "06010",
      "odno": "0001569138",
      "orgn_odno": "",
      "ord_dvsn_name": "지정가",
      "pdno": "009150",
      "prdt_name": "SamsungElecMech",
      "rvse_cncl_dvsn_name": "",
      "ord_qty": "1",
      "ord_unpr": "200000",
      "ord_tmd": "131421",
      "tot_ccld_qty": "0",
      "tot_ccld_amt": "0",
      "psbl_qty": "1",
      "sll_buy_dvsn_cd": "02",
      "ord_dvsn_cd": "00",
      "mgco_aptm_odno": ""
    }
	],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식예약주문

- **TR_ID**: CTSC0008U
- **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | { 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"PDNO": "009150", 
	"ORD_QTY": "10", 
	"ORD_UNPR": "160000", 
	"SLL_BUY_DVSN_CD":"02", 
	"ORD_DVSN_CD":"00", 
	"ORD_OBJT_CBLC_DVSN_CD":"10", 
	"LOAN_DT":"", 
	"RSVN_ORD_END_DT":""
} |  |
| Response Example | { 
	"rt_cd": "0", 
	"msg_cd": "APBK2938", 
	"msg1": "예약주문이 접수되었습니다.", 
	"output": { 
		"RSVN_ORD_SEQ": "39607" 
	} 
} |  |


### 주식주문(신용)

- **TR_ID**: (매도) TTTC0051U (매수) TTTC0052U
- **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-credit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "810XXXXX",
    "ACNT_PRDT_CD": "01",
    "PDNO": "009150",
    "CRDT_TYPE": "21",
    "LOAN_DT": "20211103",
    "ORD_DVSN": "00",
    "ORD_QTY": "1",
    "ORD_UNPR": "130000",
    "RSVN_ORD_YN": "N"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569138",
    "ORD_TMD": "131421"
  }
} |  |


### 퇴직연금 잔고조회

- **TR_ID**: TTTC2208R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"29",
	"ACCA_DVSN_CD":"00",
	"INQR_DVSN":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "12345678^29^00^00^                                                                                  ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "cblc_dvsn_name": "사용자",
            "prdt_name": "ACE 미국S&P500",
            "pdno": "360200",
            "item_dvsn_name": "현금",
            "thdt_buyqty": "5",
            "thdt_sll_qty": "0",
            "hldg_qty": "5",
            "ord_psbl_qty": "5",
            "pchs_avg_pric": "13235.0000",
            "pchs_amt": "66175",
            "prpr": "13235",
            "evlu_amt": "66175",
            "evlu_pfls_amt": "0",
            "evlu_erng_rt": "0.00000000"
        }
    ],
    "output2": {
        "dnca_tot_amt": "100000",
        "nxdy_excc_amt": "100000",
        "prvs_rcdl_excc_amt": "33825",
        "thdt_buy_amt": "66175",
        "thdt_sll_amt": "0",
        "thdt_tlex_amt": "0",
        "scts_evlu_amt": "66175",
        "tot_evlu_amt": "100000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 주식잔고조회_실현손익

- **TR_ID**: TTTC8494R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-balance-rlz-pl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"AFHR_FLPR_YN":"N",
"OFL_YN":"",
"INQR_DVSN":"02",
"UNPR_DVSN":"01",
"FUND_STTL_ICLD_YN":"N",
"FNCG_AMT_AUTO_RDPT_YN":"N",
"PRCS_DVSN":"01",
"COST_ICLD_YN":"N",
"CTX_AREA_FK100":"",
"CTX_AREA_NK100":""
} |  |
| Response Example | {
    "ctx_area_fk100": "12345678^01^N^N^02^01^N^                                                                            ",
    "ctx_area_nk100": "N^00000A900270^300^00000000^00^                                                                     ",
    "output1": [
        {
            "pdno": "000080",
            "prdt_name": "하이트진로",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "22975.0000",
            "pchs_amt": "45950",
            "prpr": "22600",
            "evlu_amt": "45200",
            "evlu_pfls_amt": "-750",
            "evlu_pfls_rt": "-1.63",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000100",
            "prdt_name": "유한양행",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "64800.0000",
            "pchs_amt": "129600",
            "prpr": "67600",
            "evlu_amt": "135200",
            "evlu_pfls_amt": "5600",
            "evlu_pfls_rt": "4.32",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "2900",
            "fltt_rt": "4.48222566"
        },
        {
            "pdno": "000120",
            "prdt_name": "CJ대한통운",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "116800.0000",
            "pchs_amt": "1168000",
            "prpr": "129500",
            "evlu_amt": "1295000",
            "evlu_pfls_amt": "127000",
            "evlu_pfls_rt": "10.87",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "500",
            "fltt_rt": "0.38759690"
        },
        {
            "pdno": "000210",
            "prdt_name": "DL",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "50400.0000",
            "pchs_amt": "504000",
            "prpr": "45800",
            "evlu_amt": "458000",
            "evlu_pfls_amt": "-46000",
            "evlu_pfls_rt": "-9.12",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-5500",
            "fltt_rt": "-10.72124756"
        },
        {
            "pdno": "000240",
            "prdt_name": "한국앤컴퍼니",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "23850.0000",
            "pchs_amt": "47700",
            "prpr": "17450",
            "evlu_amt": "34900",
            "evlu_pfls_amt": "-12800",
            "evlu_pfls_rt": "-26.83",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000270",
            "prdt_name": "기아",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "84500.0000",
            "pchs_amt": "845000",
            "prpr": "89500",
            "evlu_amt": "895000",
            "evlu_pfls_amt": "50000",
            "evlu_pfls_rt": "5.91",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-35300",
            "fltt_rt": "-28.28525641"
        },
        {
            "pdno": "000660",
            "prdt_name": "SK하이닉스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "12",
            "ord_psbl_qty": "12",
            "pchs_avg_pric": "122583.3333",
            "pchs_amt": "1471000",
            "prpr": "161700",
            "evlu_amt": "1940400",
            "evlu_pfls_amt": "469400",
            "evlu_pfls_rt": "31.91",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1700",
            "fltt_rt": "1.06250000"
        },
        {
            "pdno": "000670",
            "prdt_name": "영풍",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "4",
            "thdt_sll_qty": "0",
            "hldg_qty": "4",
            "ord_psbl_qty": "4",
            "pchs_avg_pric": "640750.0000",
            "pchs_amt": "2563000",
            "prpr": "525000",
            "evlu_amt": "2100000",
            "evlu_pfls_amt": "-463000",
            "evlu_pfls_rt": "-18.06",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000990",
            "prdt_name": "DB하이텍",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "23000.0000",
            "pchs_amt": "46000",
            "prpr": "49600",
            "evlu_amt": "99200",
            "evlu_pfls_amt": "53200",
            "evlu_pfls_rt": "115.65",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "001120",
            "prdt_name": "LX인터내셔널",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "34050.0000",
            "pchs_amt": "34050",
            "prpr": "28950",
            "evlu_amt": "28950",
            "evlu_pfls_amt": "-5100",
            "evlu_pfls_rt": "-14.97",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "002380",
            "prdt_name": "KCC",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "252000.0000",
            "pchs_amt": "252000",
            "prpr": "250000",
            "evlu_amt": "250000",
            "evlu_pfls_amt": "-2000",
            "evlu_pfls_rt": "-0.79",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "003550",
            "prdt_name": "LG",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "105600.0000",
            "pchs_amt": "211200",
            "prpr": "85000",
            "evlu_amt": "170000",
            "evlu_pfls_amt": "-41200",
            "evlu_pfls_rt": "-19.50",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-16200",
            "fltt_rt": "-16.00790514"
        },
        {
            "pdno": "003670",
            "prdt_name": "포스코퓨처엠",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "531000.0000",
            "pchs_amt": "1062000",
            "prpr": "296000",
            "evlu_amt": "592000",
            "evlu_pfls_amt": "-470000",
            "evlu_pfls_rt": "-44.25",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "004800",
            "prdt_name": "효성",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "66400.0000",
            "pchs_amt": "132800",
            "prpr": "64700",
            "evlu_amt": "129400",
            "evlu_pfls_amt": "-3400",
            "evlu_pfls_rt": "-2.56",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "005380",
            "prdt_name": "현대차",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "240500.0000",
            "pchs_amt": "481000",
            "prpr": "244000",
            "evlu_amt": "488000",
            "evlu_pfls_amt": "7000",
            "evlu_pfls_rt": "1.45",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "22000",
            "fltt_rt": "9.90990991"
        },
        {
            "pdno": "005490",
            "prdt_name": "POSCO홀딩스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "133500.0000",
            "pchs_amt": "1335000",
            "prpr": "421500",
            "evlu_amt": "4215000",
            "evlu_pfls_amt": "2880000",
            "evlu_pfls_rt": "215.73",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1417",
            "thdt_sll_qty": "2",
            "hldg_qty": "1415",
            "ord_psbl_qty": "1415",
            "pchs_avg_pric": "53397.8247",
            "pchs_amt": "75557922",
            "prpr": "73900",
            "evlu_amt": "104568500",
            "evlu_pfls_amt": "29010578",
            "evlu_pfls_rt": "38.39",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-400",
            "fltt_rt": "-0.53835801"
        },
        {
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "자기융자",
            "bfdy_buy_qty": "1",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "0",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "45100.0000",
            "pchs_amt": "45100",
            "prpr": "73900",
            "evlu_amt": "73900",
            "evlu_pfls_amt": "28800",
            "evlu_pfls_rt": "63.85",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "45100",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "45100.0000",
            "bfdy_cprs_icdc": "-400",
            "fltt_rt": "-0.53835801"
        },
        {
            "pdno": "005940",
            "prdt_name": "NH투자증권",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "11710.0000",
            "pchs_amt": "117100",
            "prpr": "10650",
            "evlu_amt": "106500",
            "evlu_pfls_amt": "-10600",
            "evlu_pfls_rt": "-9.05",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "006260",
            "prdt_name": "LS",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "122000.0000",
            "pchs_amt": "1220000",
            "prpr": "96600",
            "evlu_amt": "966000",
            "evlu_pfls_amt": "-254000",
            "evlu_pfls_rt": "-20.81",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "008770",
            "prdt_name": "호텔신라",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "99850.0000",
            "pchs_amt": "199700",
            "prpr": "59300",
            "evlu_amt": "118600",
            "evlu_pfls_amt": "-81100",
            "evlu_pfls_rt": "-40.61",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-2100",
            "fltt_rt": "-3.42019544"
        },
        {
            "pdno": "009540",
            "prdt_name": "HD한국조선해양",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "170000.0000",
            "pchs_amt": "1700000",
            "prpr": "126000",
            "evlu_amt": "1260000",
            "evlu_pfls_amt": "-440000",
            "evlu_pfls_rt": "-25.88",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1000",
            "fltt_rt": "0.80000000"
        },
        {
            "pdno": "011780",
            "prdt_name": "금호석유",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "200000.0000",
            "pchs_amt": "2000000",
            "prpr": "151900",
            "evlu_amt": "1519000",
            "evlu_pfls_amt": "-481000",
            "evlu_pfls_rt": "-24.05",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "011790",
            "prdt_name": "SKC",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "49950.0000",
            "pchs_amt": "499500",
            "prpr": "92100",
            "evlu_amt": "921000",
            "evlu_pfls_amt": "421500",
            "evlu_pfls_rt": "84.38",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "015760",
            "prdt_name": "한국전력",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "4",
            "thdt_sll_qty": "0",
            "hldg_qty": "4",
            "ord_psbl_qty": "4",
            "pchs_avg_pric": "8030.0000",
            "pchs_amt": "32120",
            "prpr": "23000",
            "evlu_amt": "92000",
            "evlu_pfls_amt": "59880",
            "evlu_pfls_rt": "186.42",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "017670",
            "prdt_name": "SK텔레콤",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "50100.0000",
            "pchs_amt": "501000",
            "prpr": "53200",
            "evlu_amt": "532000",
            "evlu_pfls_amt": "31000",
            "evlu_pfls_rt": "6.18",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "018260",
            "prdt_name": "삼성에스디에스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "250000.0000",
            "pchs_amt": "500000",
            "prpr": "174000",
            "evlu_amt": "348000",
            "evlu_pfls_amt": "-152000",
            "evlu_pfls_rt": "-30.40",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "3200",
            "fltt_rt": "1.87353630"
        },
        {
            "pdno": "028260",
            "prdt_name": "삼성물산",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "5",
            "thdt_sll_qty": "0",
            "hldg_qty": "5",
            "ord_psbl_qty": "5",
            "pchs_avg_pric": "156100.0000",
            "pchs_amt": "780500",
            "prpr": "128000",
            "evlu_amt": "640000",
            "evlu_pfls_amt": "-140500",
            "evlu_pfls_rt": "-18.00",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "028670",
            "prdt_name": "팬오션",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "4865.0000",
            "pchs_amt": "9730",
            "prpr": "5000",
            "evlu_amt": "10000",
            "evlu_pfls_amt": "270",
            "evlu_pfls_rt": "2.77",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "385",
            "fltt_rt": "8.34236186"
        },
        {
            "pdno": "030200",
            "prdt_name": "KT",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "26050.0000",
            "pchs_amt": "260500",
            "prpr": "40650",
            "evlu_amt": "406500",
            "evlu_pfls_amt": "146000",
            "evlu_pfls_rt": "56.04",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "034730",
            "prdt_name": "SK",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "182700.0000",
            "pchs_amt": "1827000",
            "prpr": "207000",
            "evlu_amt": "2070000",
            "evlu_pfls_amt": "243000",
            "evlu_pfls_rt": "13.30",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "035250",
            "prdt_name": "강원랜드",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "20950.0000",
            "pchs_amt": "209500",
            "prpr": "19000",
            "evlu_amt": "190000",
            "evlu_pfls_amt": "-19500",
            "evlu_pfls_rt": "-9.30",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1230",
            "fltt_rt": "6.92177828"
        },
        {
            "pdno": "035420",
            "prdt_name": "NAVER",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "356000.0000",
            "pchs_amt": "3560000",
            "prpr": "270000",
            "evlu_amt": "2700000",
            "evlu_pfls_amt": "-860000",
            "evlu_pfls_rt": "-24.15",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "61000",
            "fltt_rt": "29.18660287"
        },
        {
            "pdno": "035760",
            "prdt_name": "CJ ENM",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "11",
            "thdt_sll_qty": "0",
            "hldg_qty": "11",
            "ord_psbl_qty": "11",
            "pchs_avg_pric": "58836.3636",
            "pchs_amt": "647199",
            "prpr": "82200",
            "evlu_amt": "904200",
            "evlu_pfls_amt": "257000",
            "evlu_pfls_rt": "39.70",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "036460",
            "prdt_name": "한국가스공사",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "27850.0000",
            "pchs_amt": "55700",
            "prpr": "30400",
            "evlu_amt": "60800",
            "evlu_pfls_amt": "5100",
            "evlu_pfls_rt": "9.15",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "047050",
            "prdt_name": "포스코인터내셔널",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "74400.0000",
            "pchs_amt": "148800",
            "prpr": "58400",
            "evlu_amt": "116800",
            "evlu_pfls_amt": "-32000",
            "evlu_pfls_rt": "-21.50",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "057050",
            "prdt_name": "현대홈쇼핑",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "30100.0000",
            "pchs_amt": "60200",
            "prpr": "46850",
            "evlu_amt": "93700",
            "evlu_pfls_amt": "33500",
            "evlu_pfls_rt": "55.64",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "093370",
            "prdt_name": "후성",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "15510.0000",
            "pchs_amt": "31020",
            "prpr": "9000",
            "evlu_amt": "18000",
            "evlu_pfls_amt": "-13020",
            "evlu_pfls_rt": "-41.97",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "096770",
            "prdt_name": "SK이노베이션",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "228000.0000",
            "pchs_amt": "2280000",
            "prpr": "124100",
            "evlu_amt": "1241000",
            "evlu_pfls_amt": "-1039000",
            "evlu_pfls_rt": "-45.57",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt |  |

