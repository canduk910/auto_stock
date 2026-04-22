# [해외선물옵션] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (11개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 286 | REST | 해외선물옵션 주문 | OTFM3001U  | POST | `/uapi/overseas-futureoption/v1/trading/order` |  |
| 287 | REST | 해외선물옵션 정정취소주문 | (정정) OTFM3002U (취소) OTFM3003U | POST | `/uapi/overseas-futureoption/v1/trading/order-rvsecncl` |  |
| 288 | REST | 해외선물옵션 당일주문내역조회 | OTFM3116R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-ccld` |  |
| 289 | REST | 해외선물옵션 미결제내역조회(잔고) | OTFM1412R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-unpd` |  |
| 290 | REST | 해외선물옵션 주문가능조회 | OTFM3304R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-psamount` |  |
| 291 | REST | 해외선물옵션 기간계좌손익 일별 | OTFM3118R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-period-ccld` |  |
| 292 | REST | 해외선물옵션 일별 체결내역 | OTFM3122R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-daily-ccld` |  |
| 293 | REST | 해외선물옵션 예수금현황 | OTFM1411R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-deposit` |  |
| 294 | REST | 해외선물옵션 일별 주문내역 | OTFM3120R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-daily-order` |  |
| 295 | REST | 해외선물옵션 기간계좌거래내역 | OTFM3114R | GET | `/uapi/overseas-futureoption/v1/trading/inquire-period-trans` |  |
| 296 | REST | 해외선물옵션 증거금상세 | OTFM3115R | GET | `/uapi/overseas-futureoption/v1/trading/margin-detail` |  |

---

## 상세 명세

### 해외선물옵션 주문

- **TR_ID**: OTFM3001U 
- **Method**: POST
- **URL**: `/uapi/overseas-futureoption/v1/trading/order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "81012345",
    "ACNT_PRDT_CD": "08",
    "OVRS_FUTR_FX_PDNO": "6BZ22",
    "SLL_BUY_DVSN_CD": "02",
    "FM_LQD_USTL_CCLD_DT": "",
    "FM_LQD_USTL_CCNO": "",
    "PRIC_DVSN_CD": "1",
    "FM_LIMIT_ORD_PRIC": "1.17",
    "FM_STOP_ORD_PRIC": "",
    "FM_ORD_QTY": "1",
    "FM_LQD_LMT_ORD_PRIC": "",
    "FM_LQD_STOP_ORD_PRIC": "",
    "CCLD_CNDT_CD": "6",
    "CPLX_ORD_DVSN_CD": "0",
    "ECIS_RSVN_ORD_YN": "N",
    "FM_HDGE_ORD_SCRN_YN": "N"
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "ORD_DT": "20221214",
        "ODNO": "00298040"
    }
} |  |


### 해외선물옵션 정정취소주문

- **TR_ID**: (정정) OTFM3002U (취소) OTFM3003U
- **Method**: POST
- **URL**: `/uapi/overseas-futureoption/v1/trading/order-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "81012345",
    "ACNT_PRDT_CD": "08",
    "ORGN_ORD_DT": "20221214",
    "ORGN_ODNO": "00298044",
    "FM_MKPR_CVSN_YN": "N",
    "FM_HDGE_ORD_SCRN_YN": "N"
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "ORD_DT": "20221214",
        "ODNO": "00298045"
    }
} |  |


### 해외선물옵션 당일주문내역조회

- **TR_ID**: OTFM3116R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"CCLD_NCCS_DVSN":"01",
	"SLL_BUY_DVSN_CD":"01",
	"FUOP_DVSN":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":"",
} |  |
| Response Example | {
    "ctx_area_fk200": "81012345^08^01^02^00^                                                                                                                                                                                   ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output": [
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ord_dt": "20221214",
            "odno": "00298048",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6BZ22",
            "rcit_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "trad_stgy_dvsn_cd": "00",
            "bass_pric_type_cd": "1",
            "ord_stat_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "1.1700",
            "fm_stop_ord_pric": "0.0000",
            "rsvn_dvsn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.0000",
            "fm_ord_rmn_qty": "1",
            "ord_grp_name": "",
            "erlm_dtl_dtime": "20221214134455791",
            "ccld_dtl_dtime": "",
            "ord_stfno": "invent",
            "rmks1": "",
            "new_lqd_dvsn_cd": "1",
            "fm_lqd_lmt_ord_pric": "0.0000",
            "fm_lqd_stop_pric": "0.0000",
            "ccld_cndt_cd": "6",
            "noti_vald_dt": "",
            "acnt_type_cd": "1",
            "fuop_dvsn": "01"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ord_dt": "20221214",
            "odno": "00298045",
            "orgn_ord_dt": "20221214",
            "orgn_odno": "00298044",
            "ovrs_futr_fx_pdno": "6BZ22",
            "rcit_dvsn_cd": "02",
            "sll_buy_dvsn_cd": "02",
            "trad_stgy_dvsn_cd": "00",
            "bass_pric_type_cd": "1",
            "ord_stat_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "0.0000",
            "fm_stop_ord_pric": "0.0000",
            "rsvn_dvsn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.0000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "erlm_dtl_dtime": "20221214134356649",
            "ccld_dtl_dtime": "",
            "ord_stfno": "invent",
            "rmks1": "",
            "new_lqd_dvsn_cd": "1",
            "fm_lqd_lmt_ord_pric": "0.0000",
            "fm_lqd_stop_pric": "0.0000",
            "ccld_cndt_cd": "6",
            "noti_vald_dt": "",
            "acnt_type_cd": "1",
            "fuop_dvsn": "01"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ord_dt": "20221214",
            "odno": "00298044",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6BZ22",
            "rcit_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "trad_stgy_dvsn_cd": "00",
            "bass_pric_type_cd": "1",
            "ord_stat_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "1.1700",
            "fm_stop_ord_pric": "0.0000",
            "rsvn_dvsn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.0000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "erlm_dtl_dtime": "20221214134351411",
            "ccld_dtl_dtime": "",
            "ord_stfno": "invent",
            "rmks1": "",
            "new_lqd_dvsn_cd": "1",
            "fm_lqd_lmt_ord_pric": "0.0000",
            "fm_lqd_stop_pric": "0.0000",
            "ccld_cndt_cd": "6",
            "noti_vald_dt": "",
            "acnt_type_cd": "1",
            "fuop_dvsn": "01"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ord_dt": "20221214",
            "odno": "00298040",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6BZ22",
            "rcit_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "trad_stgy_dvsn_cd": "00",
            "bass_pric_type_cd": "1",
            "ord_stat_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "1.1700",
            "fm_stop_ord_pric": "0.0000",
            "rsvn_dvsn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.0000",
            "fm_ord_rmn_qty": "1",
            "ord_grp_name": "",
            "erlm_dtl_dtime": "20221214134100992",
            "ccld_dtl_dtime": "",
            "ord_stfno": "invent",
            "rmks1": "",
            "new_lqd_dvsn_cd": "1",
            "fm_lqd_lmt_ord_pric": "0.0000",
            "fm_lqd_stop_pric": "0.0000",
            "ccld_cndt_cd": "6",
            "noti_vald_dt": "",
            "acnt_type_cd": "1",
            "fuop_dvsn": "01"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 미결제내역조회(잔고)

- **TR_ID**: OTFM1412R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-unpd`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"FUOP_DVSN":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":"",
} |  |
| Response Example | {
    "ctx_area_fk100": "81012345^08^00^                                                                                     ",
    "ctx_area_nk100": "                                                                                                    ",
    "output": [
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6AZ22",
            "prdt_type_cd": "600",
            "crcy_cd": "USD",
            "sll_buy_dvsn_cd": "02",
            "fm_ustl_qty": "2",
            "fm_ccld_avg_pric": "0.62950",
            "fm_now_pric": "0.68320",
            "fm_evlu_pfls_amt": "10740.00",
            "fm_opt_evlu_amt": "",
            "fm_otp_evlu_pfls_amt": "",
            "fuop_dvsn": "01",
            "ecis_rsvn_ord_yn": "",
            "fm_lqd_psbl_qty": "2"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6BZ22",
            "prdt_type_cd": "600",
            "crcy_cd": "USD",
            "sll_buy_dvsn_cd": "02",
            "fm_ustl_qty": "2",
            "fm_ccld_avg_pric": "1.1898",
            "fm_now_pric": "1.2350",
            "fm_evlu_pfls_amt": "5656.24",
            "fm_opt_evlu_amt": "",
            "fm_otp_evlu_pfls_amt": "",
            "fuop_dvsn": "01",
            "ecis_rsvn_ord_yn": "",
            "fm_lqd_psbl_qty": "2"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6JZ22",
            "prdt_type_cd": "600",
            "crcy_cd": "USD",
            "sll_buy_dvsn_cd": "02",
            "fm_ustl_qty": "1",
            "fm_ccld_avg_pric": "6925.0",
            "fm_now_pric": "7383.0",
            "fm_evlu_pfls_amt": "5725.00",
            "fm_opt_evlu_amt": "",
            "fm_otp_evlu_pfls_amt": "",
            "fuop_dvsn": "01",
            "ecis_rsvn_ord_yn": "",
            "fm_lqd_psbl_qty": "1"
        },
        {
            "cano": "81012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "ZBZ22",
            "prdt_type_cd": "600",
            "crcy_cd": "USD",
            "sll_buy_dvsn_cd": "01",
            "fm_ustl_qty": "100",
            "fm_ccld_avg_pric": "132.293125",
            "fm_now_pric": "131.218750",
            "fm_evlu_pfls_amt": "107438.00",
            "fm_opt_evlu_amt": "",
            "fm_otp_evlu_pfls_amt": "",
            "fuop_dvsn": "01",
            "ecis_rsvn_ord_yn": "",
            "fm_lqd_psbl_qty": "100"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 주문가능조회

- **TR_ID**: OTFM3304R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-psamount`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"OVRS_FUTR_FX_PDNO":"6AU22",
	"SLL_BUY_DVSN_CD":"02",
	"FM_ORD_PRIC":"",
	"ECIS_RSVN_ORD_YN":""
} |  |
| Response Example | {
    "output": {
        "cano": "80012345",
        "acnt_prdt_cd": "08",
        "ovrs_futr_fx_pdno": "6AU22",
        "crcy_cd": "",
        "sll_buy_dvsn_cd": "02",
        "fm_ustl_qty": "0",
        "fm_lqd_psbl_qty": "0",
        "fm_new_ord_psbl_qty": "3717",
        "fm_tot_ord_psbl_qty": "3717",
        "fm_mkpr_tot_ord_psbl_qty": "3717"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 기간계좌손익 일별

- **TR_ID**: OTFM3118R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-period-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"INQR_TERM_FROM_DT":"20220901",
	"INQR_TERM_TO_DT":"20221117",
	"CRCY_CD":"%%%",
	"WHOL_TRSL_YN":"N",
	"FUOP_DVSN":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":"",
} |  |
| Response Example | {
    "ctx_area_fk200": "                                                                                                                                                                                                        ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [
        {
            "cano": "80012345",
            "acnt_prdt_cd": "08",
            "crcy_cd": "USD",
            "fm_buy_qty": "",
            "fm_sll_qty": "",
            "fm_lqd_pfls_amt": "0.00",
            "fm_fee": "0.00",
            "fm_net_pfls_amt": "129650.00",
            "fm_ustl_buy_qty": "5",
            "fm_ustl_sll_qty": "100",
            "fm_ustl_evlu_pfls_amt": "129650.00",
            "fm_ustl_evlu_pfls_amt2": "0.00",
            "fm_ustl_evlu_pfls_icdc_amt": "129650.00",
            "fm_ustl_agrm_amt": "13590493.75",
            "fm_opt_lqd_amt": "0.00"
        }
    ],
    "output2": [
        {
            "cano": "80012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6AZ22",
            "crcy_cd": "USD",
            "fm_buy_qty": "",
            "fm_sll_qty": "",
            "fm_lqd_pfls_amt": "0.00",
            "fm_fee": "0.00",
            "fm_net_pfls_amt": "10850.00",
            "fm_ustl_buy_qty": "2",
            "fm_ustl_sll_qty": "",
            "fm_ustl_evlu_pfls_amt": "10850.00",
            "fm_ustl_evlu_pfls_amt2": "0.00",
            "fm_ustl_evlu_pfls_icdc_amt": "10850.00",
            "fm_ccld_avg_pric": "0.62950",
            "fm_ustl_agrm_amt": "125900.00",
            "fm_opt_lqd_amt": "0.00"
        },
        {
            "cano": "80012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6BZ22",
            "crcy_cd": "USD",
            "fm_buy_qty": "",
            "fm_sll_qty": "",
            "fm_lqd_pfls_amt": "0.00",
            "fm_fee": "0.00",
            "fm_net_pfls_amt": "5656.25",
            "fm_ustl_buy_qty": "2",
            "fm_ustl_sll_qty": "",
            "fm_ustl_evlu_pfls_amt": "5656.25",
            "fm_ustl_evlu_pfls_amt2": "0.00",
            "fm_ustl_evlu_pfls_icdc_amt": "5656.25",
            "fm_ccld_avg_pric": "1.1898",
            "fm_ustl_agrm_amt": "148718.75",
            "fm_opt_lqd_amt": "0.00"
        },
        {
            "cano": "80012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "6JZ22",
            "crcy_cd": "USD",
            "fm_buy_qty": "",
            "fm_sll_qty": "",
            "fm_lqd_pfls_amt": "0.00",
            "fm_fee": "0.00",
            "fm_net_pfls_amt": "5706.25",
            "fm_ustl_buy_qty": "1",
            "fm_ustl_sll_qty": "",
            "fm_ustl_evlu_pfls_amt": "5706.25",
            "fm_ustl_evlu_pfls_amt2": "0.00",
            "fm_ustl_evlu_pfls_icdc_amt": "5706.25",
            "fm_ccld_avg_pric": "6925.0",
            "fm_ustl_agrm_amt": "86562.50",
            "fm_opt_lqd_amt": "0.00"
        },
        {
            "cano": "80012345",
            "acnt_prdt_cd": "08",
            "ovrs_futr_fx_pdno": "ZBZ22",
            "crcy_cd": "USD",
            "fm_buy_qty": "",
            "fm_sll_qty": "",
            "fm_lqd_pfls_amt": "0.00",
            "fm_fee": "0.00",
            "fm_net_pfls_amt": "107437.50",
            "fm_ustl_buy_qty": "",
            "fm_ustl_sll_qty": "100",
            "fm_ustl_evlu_pfls_amt": "107437.50",
            "fm_ustl_evlu_pfls_amt2": "0.00",
            "fm_ustl_evlu_pfls_icdc_amt": "107437.50",
            "fm_ccld_avg_pric": "132.293125",
            "fm_ustl_agrm_amt": "13229312.50",
            "fm_opt_lqd_amt": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 일별 체결내역

- **TR_ID**: OTFM3122R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-daily-ccld`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"STRT_DT":"20221010",
	"END_DT":"20221216",
	"FUOP_DVSN":"00",
	"FM_PDGR_CD":"",
	"CRCY_CD":"%%%",
	"FM_ITEM_FTNG_YN":"N",
	"SLL_BUY_DVSN_CD":"%%",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":"",
} |  |
| Response Example | {
    "ctx_area_fk200": "80012345^08^20221010^20221216^00^^%%%^N^%%^                                                                                                                                                             ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [
        {
            "dt": "20221020",
            "ccno": "00004090",
            "ovrs_futr_fx_pdno": "6AZ22",
            "sll_buy_dvsn_cd": "02",
            "fm_ccld_qty": "1",
            "fm_ccld_amt": ".62955",
            "fm_futr_ccld_amt": "62955",
            "fm_opt_ccld_amt": "0",
            "crcy_cd": "USD",
            "fm_fee": "12.5",
            "fm_futr_pure_agrm_amt": "62967.5",
            "fm_opt_pure_agrm_amt": "0",
            "ccld_dtl_dtime": "20221020132204282",
            "ord_dt": "20221020",
            "odno": "00284471",
            "ord_mdia_dvsn_name": "일반"
        },
        {
            "dt": "20221020",
            "ccno": "00004089",
            "ovrs_futr_fx_pdno": "6AZ22",
            "sll_buy_dvsn_cd": "02",
            "fm_ccld_qty": "1",
            "fm_ccld_amt": ".62945",
            "fm_futr_ccld_amt": "62945",
            "fm_opt_ccld_amt": "0",
            "crcy_cd": "USD",
            "fm_fee": "12.5",
            "fm_futr_pure_agrm_amt": "62957.5",
            "fm_opt_pure_agrm_amt": "0",
            "ccld_dtl_dtime": "20221020125948252",
            "ord_dt": "20221020",
            "odno": "00284466",
            "ord_mdia_dvsn_name": "일반"
        }
    ],
    "output2": {
        "fm_tot_ccld_qty": "2",
        "fm_tot_futr_agrm_amt": "125900",
        "fm_tot_opt_agrm_amt": "0",
        "fm_fee_smtl": "25"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 예수금현황

- **TR_ID**: OTFM1411R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-deposit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"CRCY_CD":":"KRW",
	"INQR_DT":"20221214"
} |  |
| Response Example | {
    "output": {
        "cano": "81012345",
        "acnt_prdt_cd": "08",
        "crcy_cd": "KRW",
        "resp_dt": "20230104",
        "fm_dnca_rmnd": "9990000012",
        "fm_lqd_pfls_amt": "0",
        "fm_fee": "0",
        "fm_nxdy_dncl_amt": "9990000012",
        "fm_tot_asst_evlu_amt": "9990000012",
        "fm_fuop_evlu_pfls_amt": "0",
        "fm_rcvb_amt": "0",
        "fm_brkg_mgn_amt": "0",
        "fm_mntn_mgn_amt": "0",
        "fm_add_mgn_amt": "0",
        "fm_risk_rt": "0.00",
        "fm_ord_psbl_amt": "9718323936",
        "fm_drwg_psbl_amt": "9704739489",
        "fm_echm_rqrm_amt": "0",
        "fm_drwg_prar_amt": "0",
        "fm_opt_tr_chgs": "0",
        "fm_opt_icld_asst_evlu_amt": "9990000012",
        "fm_opt_evlu_amt": "0",
        "fm_crcy_sbst_amt": "0",
        "fm_crcy_sbst_use_amt": "0",
        "fm_crcy_sbst_stup_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외선물옵션 일별 주문내역

- **TR_ID**: OTFM3120R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-daily-order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO":"12345678",
	"ACNT_PRDT_CD":"08",
	"STRT_DT":"20220101",
	"END_DT":"20221214",
	"FM_PDGR_CD":"",
	"CCLD_NCCS_DVSN":"01",
	"SLL_BUY_DVSN_CD":"%%",
	"FUOP_DVSN":"00",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":"",
} |  |
| Response Example | {
    "ctx_area_fk200": "12345678^08^20231206^20231206^^01^%%^00^                                                                                                                                                                ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output": [
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362398",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6CZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "2",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "3",
            "fm_ord_pric": "0.00000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "3",
            "fm_ccld_pric": "0.73935",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206092306005",
            "ccld_dtl_dtime": "20231206092306005",
            "ordr_emp_no": "109171",
            "rjct_rson_name": "",
            "ccld_cndt_cd": "2",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362397",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6CZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "2",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "0.00000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "1",
            "fm_ccld_pric": "0.73925",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206092247252",
            "ccld_dtl_dtime": "20231206092247252",
            "ordr_emp_no": "109171",
            "rjct_rson_name": "",
            "ccld_cndt_cd": "2",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362396",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6CZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "2",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "0.00000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "1",
            "fm_ccld_pric": "0.73920",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206092123893",
            "ccld_dtl_dtime": "20231206092123893",
            "ordr_emp_no": "109171",
            "rjct_rson_name": "",
            "ccld_cndt_cd": "2",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362395",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6CZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "2",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "1",
            "fm_ord_pric": "0.00000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "1",
            "fm_ccld_pric": "0.73915",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206092039261",
            "ccld_dtl_dtime": "20231206092039261",
            "ordr_emp_no": "109171",
            "rjct_rson_name": "",
            "ccld_cndt_cd": "2",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362394",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "10YZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "2",
            "rcit_dvsn_cd": "03",
            "fm_ord_qty": "1",
            "fm_ord_pric": "0.000",
            "fm_stop_ord_pric": "0.000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "",
            "ccld_dtl_dtime": "",
            "ordr_emp_no": "109171",
            "rjct_rson_name": "[정상적인거부]Text[Order price is outside bands 'Bid of 4269",
            "ccld_cndt_cd": "2",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362393",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6AZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "1",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "2",
            "fm_ord_pric": "0.65000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.00000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206091838237",
            "ccld_dtl_dtime": "",
            "ordr_emp_no": "45TesT",
            "rjct_rson_name": "FCM 거부됨",
            "ccld_cndt_cd": "6",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362392",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6AZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "1",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "2",
            "fm_ord_pric": "0.65000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.00000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206091835180",
            "ccld_dtl_dtime": "",
            "ordr_emp_no": "45TesT",
            "rjct_rson_name": "FCM 거부됨",
            "ccld_cndt_cd": "6",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362391",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6AZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "1",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "2",
            "fm_ord_pric": "0.65000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.00000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206083023955",
            "ccld_dtl_dtime": "",
            "ordr_emp_no": "45TesT",
            "rjct_rson_name": "FCM 거부됨",
            "ccld_cndt_cd": "6",
            "trad_end_dt": ""
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "08",
            "dt": "20231206",
            "ord_dt": "20231206",
            "odno": "00362390",
            "orgn_ord_dt": "",
            "orgn_odno": "",
            "ovrs_futr_fx_pdno": "6AZ23",
            "rvse_cncl_dvsn_cd": "00",
            "sll_buy_dvsn_cd": "02",
            "cplx_ord_dvsn_cd": "0",
            "pric_dvsn_cd": "1",
            "rcit_dvsn_cd": "02",
            "fm_ord_qty": "2",
            "fm_ord_pric": "0.65000",
            "fm_stop_ord_pric": "0.00000",
            "ecis_rsvn_ord_yn": "N",
            "fm_ccld_qty": "0",
            "fm_ccld_pric": "0.00000",
            "fm_ord_rmn_qty": "0",
            "ord_grp_name": "",
            "rcit_dtl_dtime": "20231206082401404",
            "ccld_dtl_dtime": "",
            "ordr_emp_no": "45TesT",
            "rjct_rson_name": "FCM 거부됨",
            "ccld_cndt_cd": "6",
            "trad_end_dt": ""
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510", |  |


### 해외선물옵션 기간계좌거래내역

- **TR_ID**: OTFM3114R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/inquire-period-trans`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"INQR_TERM_FROM_DT":"20220101",
	"INQR_TERM_TO_DT":"20221214",
	"CANO":"80012345",
	"ACNT_PRDT_CD":"08",
	"ACNT_TR_TYPE_CD":"%%",
	"CRCY_CD":"%%%",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":"",
	"PWD_CHK_YN":""
} |  |
| Response Example | {
    "ctx_area_fk100": "20220101^20221214^81012345^08^%%^%%%^                                                               ",
    "ctx_area_nk100": "                                                                                                    ",
    "output": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
} |  |


### 해외선물옵션 증거금상세

- **TR_ID**: OTFM3115R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/trading/margin-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:08
CRCY_CD:TKR
INQR_DT:20240522 |  |
| Response Example | {
    "output": {
        "cano": "12345678",
        "acnt_prdt_cd": "08",
        "crcy_cd": "TKR",
        "resp_dt": "20240522",
        "acnt_net_risk_mgna_aply_yn": "Y",
        "fm_ord_psbl_amt": "86128052",
        "fm_add_mgn_amt": "0",
        "fm_brkg_mgn_amt": "49082990",
        "fm_excc_brkg_mgn_amt": "49082990",
        "fm_ustl_mgn_amt": "49082990",
        "fm_mntn_mgn_amt": "44620900",
        "fm_ord_mgn_amt": "0",
        "fm_futr_ord_mgn_amt": "0",
        "fm_opt_buy_ord_amt": "0",
        "fm_opt_sll_ord_mgn_amt": "0",
        "fm_opt_buy_ord_mgn_amt": "0",
        "fm_ecis_rsvn_mgn_amt": "0",
        "fm_span_brkg_mgn_amt": "49082990",
        "fm_span_pric_altr_mgn_amt": "49082990",
        "fm_span_term_sprd_mgn_amt": "0",
        "fm_span_buy_opt_min_mgn_amt": "0",
        "fm_span_opt_min_mgn_amt": "0",
        "fm_span_tot_risk_mgn_amt": "49082990",
        "fm_span_mntn_mgn_amt": "44620900",
        "fm_span_mntn_pric_altr_mgn_amt": "44620900",
        "fm_span_mntn_term_sprd_mgn_amt": "0",
        "fm_span_mntn_opt_pric_mgn_amt": "0",
        "fm_span_mntn_opt_min_mgn_amt": "0",
        "fm_span_mntn_tot_risk_mgn_amt": "44620900",
        "fm_eurx_brkg_mgn_amt": "0",
        "fm_eurx_pric_altr_mgn_amt": "0",
        "fm_eurx_term_sprd_mgn_amt": "0",
        "fm_eurx_opt_pric_mgn_amt": "0",
        "fm_eurx_buy_opt_min_mgn_amt": "0",
        "fm_eurx_tot_risk_mgn_amt": "0",
        "fm_eurx_mntn_mgn_amt": "0",
        "fm_eurx_mntn_pric_altr_mgn_amt": "0",
        "fm_eurx_mntn_term_sprd_mgn_amt": "0",
        "fm_eurx_mntn_opt_pric_mgn_amt": "0",
        "fm_eurx_mntn_tot_risk_mgn_amt": "0",
        "fm_gnrl_brkg_mgn_amt": "0",
        "fm_futr_ustl_mgn_amt": "0",
        "fm_sll_opt_ustl_mgn_amt": "0",
        "fm_buy_opt_ustl_mgn_amt": "0",
        "fm_sprd_ustl_mgn_amt": "0",
        "fm_avg_dsct_mgn_amt": "0",
        "fm_gnrl_mntn_mgn_amt": "0",
        "fm_futr_mntn_mgn_amt": "0",
        "fm_opt_mntn_mgn_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |

