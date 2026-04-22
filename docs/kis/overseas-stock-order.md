# [해외주식] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (18개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 235 | REST | 해외주식 잔고 | TTTS3012R | GET | `/uapi/overseas-stock/v1/trading/inquire-balance` | ✓ |
| 236 | REST | 해외주식 체결기준현재잔고 | CTRP6504R | GET | `/uapi/overseas-stock/v1/trading/inquire-present-balance` | ✓ |
| 237 | REST | 해외주식 지정가체결내역조회 | TTTS6059R | GET | `/uapi/overseas-stock/v1/trading/inquire-algo-ccnl` |  |
| 238 | REST | 해외주식 기간손익 | TTTS3039R | GET | `/uapi/overseas-stock/v1/trading/inquire-period-profit` |  |
| 239 | REST | 해외주식 매수가능금액조회 | TTTS3007R | GET | `/uapi/overseas-stock/v1/trading/inquire-psamount` | ✓ |
| 240 | REST | 해외주식 정정취소주문 | (미국 정정·취소) TTTT1004U (아시아 국가 하단 규격서 참고) | POST | `/uapi/overseas-stock/v1/trading/order-rvsecncl` |  |
| 241 | REST | 해외주식 예약주문접수 | (미국예약매수) TTTT3014U  (미국예약매도) TTTT3016U   (중국/홍콩/일본/베트남 예약주문) TTTS3013U | POST | `/uapi/overseas-stock/v1/trading/order-resv` |  |
| 242 | REST | 해외주식 미체결내역 | TTTS3018R | GET | `/uapi/overseas-stock/v1/trading/inquire-nccs` | ✓ |
| 243 | REST | 해외주식 미국주간정정취소 | TTTS6038U | POST | `/uapi/overseas-stock/v1/trading/daytime-order-rvsecncl` |  |
| 244 | REST | 해외주식 주문체결내역 | TTTS3035R | GET | `/uapi/overseas-stock/v1/trading/inquire-ccnl` |  |
| 245 | REST | 해외주식 결제기준잔고 | CTRP6010R | GET | `/uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance` |  |
| 246 | REST | 해외주식 일별거래내역 | CTOS4001R | GET | `/uapi/overseas-stock/v1/trading/inquire-period-trans` |  |
| 247 | REST | 해외주식 미국주간주문 | (주간매수) TTTS6036U (주간매도) TTTS6037U | POST | `/uapi/overseas-stock/v1/trading/daytime-order` |  |
| 248 | REST | 해외주식 예약주문조회 | (미국) TTTT3039R (일본/중국/홍콩/베트남) TTTS3014R | GET | `/uapi/overseas-stock/v1/trading/order-resv-list` |  |
| 249 | REST | 해외주식 주문 | (미국매수) TTTT1002U  (미국매도) TTTT1006U (아시아 국가 하단 규격서 참고) | POST | `/uapi/overseas-stock/v1/trading/order` |  |
| 250 | REST | 해외주식 예약주문접수취소 | (미국 예약주문 취소접수) TTTT3017U (아시아국가 미제공) | POST | `/uapi/overseas-stock/v1/trading/order-resv-ccnl` |  |
| 251 | REST | 해외주식 지정가주문번호조회 | TTTS6058R | GET | `/uapi/overseas-stock/v1/trading/algo-ordno` |  |
| 252 | REST | 해외증거금 통화별조회 | TTTC2101R | GET | `/uapi/overseas-stock/v1/trading/foreign-margin` |  |

---

## 상세 명세

### 해외주식 잔고

- **TR_ID**: TTTS3012R
- **모의 TR_ID**: VTTS3012R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-balance`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"OVRS_EXCG_CD": "NASD",
"TR_CRCY_CD": "USD",
"CTX_AREA_FK200": "",
"CTX_AREA_NK200": ""
} |  |
| Response Example | {
  "ctx_area_fk200": "                                                                                                                                                                                                        ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output1": [
    {
      "cano": "810XXXXX",
      "acnt_prdt_cd": "01",
      "prdt_type_cd": "512",
      "ovrs_pdno": "TSLA",
      "ovrs_item_name": "테슬라",
      "frcr_evlu_pfls_amt": "-3547254.185235",
      "evlu_pfls_rt": "-81.75",
      "pchs_avg_pric": "5832.2148",
      "ovrs_cblc_qty": "744",
      "ord_psbl_qty": "744",
      "frcr_pchs_amt1": "4339167.78523",
      "ovrs_stck_evlu_amt": "791913.60000000",
      "now_pric2": "1064.400000",
      "tr_crcy_cd": "USD",
      "ovrs_excg_cd": "NASD",
      "loan_type_cd": "10",
      "loan_dt": "",
      "expd_dt": ""
    },
    {
      "cano": "",
      "acnt_prdt_cd": "",
      "prdt_type_cd": "",
      "ovrs_pdno": "",
      "ovrs_item_name": "",
      "frcr_evlu_pfls_amt": "0.000000",
      "evlu_pfls_rt": "0.00",
      "pchs_avg_pric": "0.0000",
      "ovrs_cblc_qty": "0",
      "ord_psbl_qty": "0",
      "frcr_pchs_amt1": "0.00000",
      "ovrs_stck_evlu_amt": "0.00000000",
      "now_pric2": "0.000000",
      "tr_crcy_cd": "",
      "ovrs_excg_cd": "",
      "loan_type_cd": "",
      "loan_dt": "",
      "expd_dt": ""
    }
  ],
  "output2": {
    "frcr_pchs_amt1": "4339167.78523",
    "ovrs_rlzt_pfls_amt": "-4836.71476",
    "ovrs_tot_pfls": "-3547254.18524",
    "rlzt_erng_rt": "-82.93101266",
    "tot_evlu_pfls_amt": "791913.60000000",
    "tot_pftrt": "-81.74964327",
    "frcr_buy_amt_smtl1": "5832.214765",
    "ovrs_rlzt_pfls_amt2": "-5780841.48713",
    "frcr_buy_amt_smtl2": "6970663.087128"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외주식 체결기준현재잔고

- **TR_ID**: CTRP6504R
- **모의 TR_ID**: VTRP6504R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-present-balance`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"WCRC_FRCR_DVSN_CD": "01",
"TR_MKET_CD": "00",
"NATN_CD": "000",
"INQR_DVSN_CD": "00"
} |  |
| Response Example | {
  "output1": [
    {
      "prdt_name": "애플",
      "cblc_qty13": "40.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "40.00000000",
      "ord_psbl_qty1": "40.00000000",
      "frcr_pchs_amt": "6411629.00000",
      "frcr_evlu_amt2": "8491110.000000",
      "evlu_pfls_amt2": "2079481.00000",
      "evlu_pfls_rt1": "32.43000000",
      "pdno": "AAPL",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "212277.75600",
      "avg_unpr3": "160290.7250",
      "tr_mket_name": "나스닥",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "5986768",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US0378331005",
      "prdt_type_cd": "512",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NASD",
      "item_lnkg_excg_cd": "NAS"
    },
    {
      "prdt_name": "테슬라",
      "cblc_qty13": "5.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "5.00000000",
      "ord_psbl_qty1": "5.00000000",
      "frcr_pchs_amt": "4665399.00000",
      "frcr_evlu_amt2": "6616309.000000",
      "evlu_pfls_amt2": "1950910.00000",
      "evlu_pfls_rt1": "41.81000000",
      "pdno": "TSLA",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "1323261.87600",
      "avg_unpr3": "933079.8000",
      "tr_mket_name": "나스닥",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "4560861",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US88160R1014",
      "prdt_type_cd": "512",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NASD",
      "item_lnkg_excg_cd": "NAS"
    },
    {
      "prdt_name": "월트디즈니",
      "cblc_qty13": "24.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "24.00000000",
      "ord_psbl_qty1": "24.00000000",
      "frcr_pchs_amt": "5039237.00000",
      "frcr_evlu_amt2": "3946867.000000",
      "evlu_pfls_amt2": "-1092370.00000",
      "evlu_pfls_rt1": "-21.67000000",
      "pdno": "DIS",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "164452.81200",
      "avg_unpr3": "209968.2080",
      "tr_mket_name": "뉴욕거래소",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "4766780",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US2546871060",
      "prdt_type_cd": "513",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NYSE",
      "item_lnkg_excg_cd": "NYS"
    },
    {
      "prdt_name": "[4689]Z홀딩스",
      "cblc_qty13": "1300.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "1300.00000000",
      "ord_psbl_qty1": "1300.00000000",
      "frcr_pchs_amt": "8556162.00000",
      "frcr_evlu_amt2": "6618273.000000",
      "evlu_pfls_amt2": "-1937889.00000",
      "evlu_pfls_rt1": "-22.64000000",
      "pdno": "4689",
      "bass_exrt": "981.11000000",
      "buy_crcy_cd": "JPY",
      "ovrs_now_pric1": "5090.97900",
      "avg_unpr3": "6581.6630",
      "tr_mket_name": "일본",
      "natn_kor_name": "일본",
      "pchs_rmnd_wcrc_amt": "9196585",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "100",
      "std_pdno": "JP3933800009",
      "prdt_type_cd": "515",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "TKSE",
      "item_lnkg_excg_cd": "TSE"
    },
    {
      "prdt_name": "ARK GENOMIC REVOLUTION ETF",
      "cblc_qty13": "36.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "36.00000000",
      "ord_psbl_qty1": "36.00000000",
      "frcr_pchs_amt": "3746679.00000",
      "frcr_evlu_amt2": "2022471.000000",
      "evlu_pfls_amt2": "-1724208.00000",
      "evlu_pfls_rt1": "-46.01000000",
      "pdno": "ARKG",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "56179.75800",
      "avg_unpr3": "104074.4160",
      "tr_mket_name": "아멕스",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "3533904",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US00214Q3020",
      "prdt_type_cd": "529",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "AMEX",
      "item_lnkg_excg_cd": "AMS"
    },
    {
      "prdt_name": "[002747]애사돈자동화",
      "cblc_qty13": "400.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "400.00000000",
      "ord_psbl_qty1": "400.00000000",
      "frcr_pchs_amt": "2327369.00000",
      "frcr_evlu_amt2": "1525444.000000",
      "evlu_pfls_amt2": "-801925.00000",
      "evlu_pfls_rt1": "-34.45000000",
      "pdno": "002747",
      "bass_exrt": "190.30000000",
      "buy_crcy_cd": "CNY",
      "ovrs_now_pric1": "3813.61200",
      "avg_unpr3": "5818.4220",
      "tr_mket_name": "심천A",
      "natn_kor_name": "중화인민공화국",
      "pchs_rmnd_wcrc_amt": "2121990",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "CNE100001X35",
      "prdt_type_cd": "552",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "SZAA",
      "item_lnkg_excg_c |  |


### 해외주식 지정가체결내역조회

- **TR_ID**: TTTS6059R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-algo-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
ORD_DT:20250523
ORD_GNO_BRNO:
ODNO:0031112345
TTLZ_ICLD_YN:
CTX_AREA_NK200:
CTX_AREA_FK200: |  |
| Response Example | {
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "ctx_area_fk200": "20250523^^0031112345^                                                                                                                                                                                   ",
    "output1": [],
    "output2": {
        "odno": "0031112345",
        "trad_dvsn_name": "TWAP지정가매수",
        "pdno": "AAPL",
        "item_name": "애플",
        "ft_ord_qty": "10",
        "ft_ord_unpr3": "10.00000000",
        "ord_tmd": "173904",
        "splt_buy_attr_name": "00:00~04:00",
        "ft_ccld_qty": "0",
        "tr_crcy": "",
        "ft_ccld_unpr3": "0.00000000",
        "ft_ccld_amt3": "0.00000",
        "ccld_cnt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
} |  |


### 해외주식 기간손익

- **TR_ID**: TTTS3039R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-period-profit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 매수가능금액조회

- **TR_ID**: TTTS3007R
- **모의 TR_ID**: VTTS3007R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-psamount`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | "input": {
            "ACNT_PRDT_CD": "01",
            "CANO": "81019777",
            "ITEM_CD": "00011",
            "OVRS_EXCG_CD": "SEHK",
            "OVRS_ORD_UNPR": "133.200"
        } |  |
| Response Example | "output": {
            "echm_af_ord_psbl_amt": "0.00",
            "echm_af_ord_psbl_qty": "0",
            "exrt": "165.5400000000",
            "frcr_ord_psbl_amt1": "955**.12",
            "max_ord_psbl_qty": "744**",
            "ord_psbl_frcr_amt": "999**.52",
            "ord_psbl_qty": "744**",
            "ovrs_max_ord_psbl_qty": "717**",
            "ovrs_ord_psbl_amt": "992**.35",
            "sll_ruse_psbl_amt": "0.00",
            "tr_crcy_cd": "HKD"
        } |  |


### 해외주식 정정취소주문

- **TR_ID**: (미국 정정·취소) TTTT1004U (아시아 국가 하단 규격서 참고)
- **모의 TR_ID**: (미국 정정·취소) VTTT1004U (아시아 국가 하단 규격서 참고)
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"OVRS_EXCG_CD": "NYSE",
"PDNO": "BA",
"ORGN_ODNO": "30135009",
"RVSE_CNCL_DVSN_CD": "01",
"ORD_QTY": "1",
"OVRS_ORD_UNPR": "226.00",
"CTAC_TLNO": "",
"MGCO_APTM_ODNO": "",
"ORD_SVR_DVSN_CD": "0"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "01790",
    "ODNO": "0000004338",
    "ORD_TMD": "160710"
  }
} |  |


### 해외주식 예약주문접수

- **TR_ID**: (미국예약매수) TTTT3014U  (미국예약매도) TTTT3016U   (중국/홍콩/일본/베트남 예약주문) TTTS3013U
- **모의 TR_ID**: (미국예약매수) VTTT3014U  (미국예약매도) VTTT3016U   (중국/홍콩/일본/베트남 예약주문) VTTS3013U
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"AAPL",
"PDNO": "AAPL",
"OVRS_EXCG_CD": "NASD",
"FT_ORD_QTY": "1",
"FT_ORD_UNPR3": "148.00"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "ODNO": "0030138295"
  }
} |  |


### 해외주식 미체결내역

- **TR_ID**: TTTS3018R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-nccs`
- **프로젝트 사용**: ✓

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"OVRS_EXCG_CD": "NYSE",
"SORT_SQN": "DS",
"CTX_AREA_FK200": "",
"CTX_AREA_NK200": ""
} |  |
| Response Example | {
  "ctx_area_fk200": "81055689^01^NYSE^DS^                                                                                                                                                                                    ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output": [
    {
      "ord_dt": "20220112",
      "ord_gno_brno": "01790",
      "odno": "0030138112",
      "orgn_odno": "",
      "pdno": "BA",
      "prdt_name": "보잉",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "매수",
      "rvse_cncl_dvsn_cd": "00",
      "rvse_cncl_dvsn_cd_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "163209",
      "tr_mket_name": "뉴욕거래소",
      "tr_crcy_cd": "USD",
      "natn_cd": "840",
      "natn_kor_name": "미국",
      "ft_ord_qty": "1",
      "ft_ccld_qty": "0",
      "nccs_qty": "1",
      "ft_ord_unpr3": "200.00000000",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "ovrs_excg_cd": "NYSE",
      "prcs_stat_name": "",
      "loan_type_cd": "10",
      "loan_dt": ""
    },
    {
      "ord_dt": "20220112",
      "ord_gno_brno": "01790",
      "odno": "0030138113",
      "orgn_odno": "",
      "pdno": "BA",
      "prdt_name": "보잉",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "매수",
      "rvse_cncl_dvsn_cd": "00",
      "rvse_cncl_dvsn_cd_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "163211",
      "tr_mket_name": "뉴욕거래소",
      "tr_crcy_cd": "USD",
      "natn_cd": "840",
      "natn_kor_name": "미국",
      "ft_ord_qty": "1",
      "ft_ccld_qty": "0",
      "nccs_qty": "1",
      "ft_ord_unpr3": "200.00000000",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "ovrs_excg_cd": "NYSE",
      "prcs_stat_name": "",
      "loan_type_cd": "10",
      "loan_dt": "",
      "loan_dt": ""
    }
  ],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외주식 미국주간정정취소

- **TR_ID**: TTTS6038U
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/daytime-order-rvsecncl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "OVRS_EXCG_CD": "NASD",
    "PDNO": "AMZN",
    "ORGN_ODNO": "0000034436",
    "RVSE_CNCL_DVSN_CD": "01",
    "ORD_QTY": "111",
    "OVRS_ORD_UNPR": "1.9",
    "CTAC_TLNO": "",
    "MGCO_APTM_ODNO": "",
    "ORD_SVR_DVSN_CD": "0"
} |  |
| Response Example | {
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "KRX_FWDG_ORD_ORGNO": "01790",
        "ODNO": "0000034437",
        "ORD_TMD": "104202"
    }
} |  |


### 해외주식 주문체결내역

- **TR_ID**: TTTS3035R
- **모의 TR_ID**: VTTS3035R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"01",
	"PDNO": ""%,
	"ORD_STRT_DT": "20211027",
	"ORD_END_DT": "20211027",
	"SLL_BUY_DVSN": "00",
	"CCLD_NCCS_DVSN": "00",
	"OVRS_EXCG_CD": "%",
	"SORT_SQN": "DS",
	"ORD_DT": "",
	"ORD_GNO_BRNO":"02111",
	"ODNO": "",
	"CTX_AREA_NK200": "",
	"CTX_AREA_FK200": ""
} |  |
| Response Example | {
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "ctx_area_fk200": "12345678^01^^20211027^20211027^00^00^NASD^^                                                                                                                                                             ",
  "output": {
      "ord_dt": "",
      "ord_gno_brno": "",
      "odno": "",
      "orgn_odno": "",
      "sll_buy_dvsn_cd": "",
      "sll_buy_dvsn_cd_name": "",
      "rvse_cncl_dvsn": "",
      "rvse_cncl_dvsn_name": "",
      "pdno": "",
      "prdt_name": "",
      "ft_ord_qty": "0",
      "ft_ord_unpr3": "0.00000000",
      "ft_ccld_qty": "0",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "nccs_qty": "0",
      "prcs_stat_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "",
      "tr_mket_name": "",
      "tr_natn": "",
      "tr_natn_name": "",
      "ovrs_excg_cd": "",
      "tr_crcy_cd": "",
      "dmst_ord_dt": "",
      "thco_ord_tmd": "",
      "loan_type_cd": "",
      "loan_dt": "",
      "mdia_dvsn_name": "OpenAPI",
      "usa_amk_exts_rqst_yn": "N",
      "splt_buy_attr_name": "00:00~04:00"    },
  "rt_cd": "0",
  "msg_cd": "KIOK0560",
  "msg1": "조회할 내용이 없습니다                                                          "
} |  |


### 해외주식 결제기준잔고

- **TR_ID**: CTRP6010R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
BASS_DT:20240524
WCRC_FRCR_DVSN_CD:01
INQR_DVSN_CD:00 |  |
| Response Example | {
    "output1": [
        {
            "pdno": "ACVA",
            "prdt_name": "ACV 옥션스",
            "cblc_qty13": "5.00000000",
            "ord_psbl_qty1": "5.00000000",
            "avg_unpr3": "11137.2000",
            "ovrs_now_pric1": "26065.48600",
            "frcr_pchs_amt": "55686.00000",
            "frcr_evlu_amt2": "130327.000000",
            "evlu_pfls_amt2": "74641.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240525104030326",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "134.03000000",
            "tr_mket_name": "나스닥",
            "natn_kor_name": "미국",
            "std_pdno": "US00091G1040",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "512",
            "ovrs_excg_cd": "NASD",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "DLPN",
            "prdt_name": "돌핀 엔터테인먼트",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "2279.0000",
            "ovrs_now_pric1": "1529.24800",
            "frcr_pchs_amt": "2279.00000",
            "frcr_evlu_amt2": "1529.000000",
            "evlu_pfls_amt2": "-750.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240525104052328",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-32.90000000",
            "tr_mket_name": "나스닥",
            "natn_kor_name": "미국",
            "std_pdno": "US25686H2094",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "512",
            "ovrs_excg_cd": "NASD",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "NIO",
            "prdt_name": "니오(ADR)",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "14316.0000",
            "ovrs_now_pric1": "6854.30800",
            "frcr_pchs_amt": "14316.00000",
            "frcr_evlu_amt2": "6854.000000",
            "evlu_pfls_amt2": "-7462.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240528185338061",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-52.12000000",
            "tr_mket_name": "뉴욕거래소",
            "natn_kor_name": "미국",
            "std_pdno": "US62914V1061",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "513",
            "ovrs_excg_cd": "NYSE",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "6731",
            "prdt_name": "[6731]픽셀라",
            "cblc_qty13": "4.00000000",
            "ord_psbl_qty1": "4.00000000",
            "avg_unpr3": "8851.7500",
            "ovrs_now_pric1": "922.30600",
            "frcr_pchs_amt": "35407.00000",
            "frcr_evlu_amt2": "3689.000000",
            "evlu_pfls_amt2": "-31718.00000",
            "bass_exrt": "870.10000000",
            "oprt_dtl_dtime": "20240528170115625",
            "buy_crcy_cd": "JPY",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-89.58000000",
            "tr_mket_name": "일본",
            "natn_kor_name": "일본",
            "std_pdno": "JP3801620000",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "515",
            "ovrs_excg_cd": "TKSE",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "CEI",
            "prdt_name": "캠버 에너지",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "2255.0000",
            "ovrs_now_pric1": "238.94500",
            "frcr_pchs_amt": "2255.00000",
            "frcr_evlu_amt2": "238.000000",
            "evlu_pfls_amt2": "-2017.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240528185356653",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-89.44000000",
            "tr_mket_name": "아멕스",
            "natn_kor_name": "미국",
            "std_pdno": "US13200M6075",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "529",
            "ovrs_excg_cd": "AMEX",
            "scts_dvsn_name": "현금"
        }
    ],
    "output2": [
        {
            "crcy_cd": "CNY",
            "crcy_cd_name": "중국위안",
            "frcr_dncl_amt_2": "1459.110000",
            "frst_bltn_exrt": "188.15000000",
            "frcr_evlu_amt2": "274531.000000"
        },
        {
            "crcy_cd": "USD",
            "crcy_cd_name": "미국달러",
            "frcr_dncl_amt_2": "698.190000",
            "frst_bltn_exrt": "1365.40000000",
            "frcr_evlu_amt2": "953308.000000"
        },
        {
            "crcy_cd": "VND",
            "crcy_cd_name": "베트남 동",
            "frcr_dncl_amt_2": "377568.000000",
            "frst_bltn_exrt": "5.36000000",
            "frcr_evlu_amt2": "20237.000000"
        }
    ],
    "output3": {
        "pchs_amt_smtl_amt": "109943",
        "tot_evlu_pfls_amt": "32694.00000000",
        "evlu_erng_rt1": "29.7300000000",
        "tot_dncl_amt": "296967",
        "wcrc_evlu_amt_smtl": "142637.000000",
        "tot_asst_amt2": "1687680.000000",
        "frcr_cblc_wcrc_evlu_amt_smtl": "1248076.000000",
        "tot_loan_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |


### 해외주식 일별거래내역

- **TR_ID**: CTOS4001R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-period-trans`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
ERLM_STRT_DT:20240101
ERLM_END_DT:20240528
OVRS_EXCG_CD:
PDNO:
SLL_BUY_DVSN_CD:00
LOAN_DVSN_CD:
CTX_AREA_FK100:
CTX_AREA_NK100: |  |
| Response Example | {
    "ctx_area_fk100": "12345678!^01!^20240101!^20240528!^!^                                                                ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "trad_dt": "20240116",
            "sttl_dt": "20240118",
            "sll_buy_dvsn_cd": "01",
            "sll_buy_dvsn_name": "매도",
            "pdno": "AAPL",
            "ovrs_item_name": "애플",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "2.94000000",
            "ovrs_stck_ccld_unpr": "0.00000000",
            "tr_frcr_amt2": "2.940000",
            "tr_amt": "0",
            "frcr_excc_amt_1": "2.940000",
            "wcrc_excc_amt": "0",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US0378331005",
            "erlm_exrt": "0.00000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240116",
            "sttl_dt": "20240118",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "USAS",
            "ovrs_item_name": "아메리카스 골드 앤드 실버",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "0.62000000",
            "ovrs_stck_ccld_unpr": "0.00000000",
            "tr_frcr_amt2": "0.620000",
            "tr_amt": "0",
            "frcr_excc_amt_1": "0.620000",
            "wcrc_excc_amt": "0",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "CA03062D1006",
            "erlm_exrt": "0.00000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "TSLA",
            "ovrs_item_name": "테슬라",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "12.20000000",
            "ovrs_stck_ccld_unpr": "16283.34000000",
            "tr_frcr_amt2": "12.200000",
            "tr_amt": "16283",
            "frcr_excc_amt_1": "12.200000",
            "wcrc_excc_amt": "16283",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US88160R1014",
            "erlm_exrt": "1334.70000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "PG",
            "ovrs_item_name": "프록터 앤드 갬블",
            "ccld_qty": "5",
            "amt_unit_ccld_qty": "5.00000000",
            "ft_ccld_unpr2": "149.20000000",
            "ovrs_stck_ccld_unpr": "199137.24000000",
            "tr_frcr_amt2": "746.000000",
            "tr_amt": "995686",
            "frcr_excc_amt_1": "746.000000",
            "wcrc_excc_amt": "995686",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US7427181091",
            "erlm_exrt": "1334.70000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "6758",
            "ovrs_item_name": "[6758]소니",
            "ccld_qty": "99",
            "amt_unit_ccld_qty": "99.00000000",
            "ft_ccld_unpr2": "14260.50000000",
            "ovrs_stck_ccld_unpr": "129281.41480000",
            "tr_frcr_amt2": "1411789.000000",
            "tr_amt": "12798855",
            "frcr_excc_amt_1": "1415742.000000",
            "wcrc_excc_amt": "12834691",
            "dmst_frcr_fee1": "2824.00000",
            "frcr_fee1": "1129.000000",
            "dmst_wcrc_fee": "25601",
            "ovrs_wcrc_fee": "10235",
            "crcy_cd": "JPY",
            "std_pdno": "JP3435000009",
            "erlm_exrt": "9.06570000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        }
    ],
    "output2": {
        "frcr_buy_amt_smtl": "13810824.000000",
        "frcr_sll_amt_smtl": "0.000000",
        "dmst_fee_smtl": "25601.000000",
        "ovrs_fee_smtl": "10235.000000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 해외주식 미국주간주문

- **TR_ID**: (주간매수) TTTS6036U (주간매도) TTTS6037U
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/daytime-order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 예약주문조회

- **TR_ID**: (미국) TTTT3039R (일본/중국/홍콩/베트남) TTTS3014R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv-list`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | "input": {
            "ACNT_PRDT_CD": "01",
            "CANO": "12345678",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
            "INQR_DVSN_CD": "00",
            "INQR_END_DT": "20220709",
            "INQR_STRT_DT": "20220705",
            "OVRS_EXCG_CD": "SEHK",
            "PRDT_TYPE_CD": "501"
        } |  |
| Response Example | {
    "ctx_area_fk200": "12345678^01^20220809^20220830^00^                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output": [
        {
            "cncl_yn": "N",
            "rsvn_ord_rcit_dt": "20250523",
            "ovrs_rsvn_odno": "0031111234",
            "ord_dt": "",
            "ord_gno_brno": "",
            "odno": "",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_cd_name": "TWAP지정가매수",
            "ovrs_rsvn_ord_stat_cd": "01",
            "ovrs_rsvn_ord_stat_cd_name": "접수",
            "pdno": "AAPL",
            "prdt_name": "애플",
            "ord_rcit_tmd": "161928",
            "ord_fwdg_tmd": "",
            "tr_dvsn_name": "접수",
            "ovrs_excg_cd": "NASD",
            "tr_mket_name": "NASDAQ",
            "ord_stfno": "999999",
            "ft_ord_qty": "100",
            "ft_ord_unpr3": "150.00000000",
            "ft_ccld_qty": "0",
            "ft_ccld_unpr3": "0.00000000",
            "nprc_rson_text": "",
            "splt_buy_attr_name": "00:00~04:00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |


### 해외주식 주문

- **TR_ID**: (미국매수) TTTT1002U  (미국매도) TTTT1006U (아시아 국가 하단 규격서 참고)
- **모의 TR_ID**: (미국매수) VTTT1002U  (미국매도) VTTT1001U  (아시아 국가 하단 규격서 참고)
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"OVRS_EXCG_CD": "NASD",
"PDNO": "AAPL",
"ORD_QTY": "1",
"OVRS_ORD_UNPR": "145.00",
"CTAC_TLNO": "",
"MGCO_APTM_ODNO": "",
"ORD_SVR_DVSN_CD": "0",
"ORD_DVSN": "00"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "01790",
    "ODNO": "0000004336",
    "ORD_TMD": "160524"
  }
} |  |


### 해외주식 예약주문접수취소

- **TR_ID**: (미국 예약주문 취소접수) TTTT3017U (아시아국가 미제공)
- **모의 TR_ID**: (미국 예약주문 취소접수) VTTT3017U (아시아국가 미제공)
- **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"RSVN_ORD_RCIT_DT": "20211124",
"OVRS_RSVN_ODNO": "30135682"
} |  |
| Response Example | {
  "rt_cd": "0",
  "msg_cd": "APBK1711",
  "msg1": "취소주문이 접수되었습니다.",
  "output": {
    "OVRS_RSVN_ODNO": "0030138295"
  }
} |  |


### 해외주식 지정가주문번호조회

- **TR_ID**: TTTS6058R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/algo-ordno`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01
TRAD_DT:20250523
CTX_AREA_NK200:
CTX_AREA_FK200: |  |
| Response Example | {
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "ctx_area_fk200": "20250523^12345678^01^                                                                                                                                                                                   ",
    "output": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
} |  |


### 해외증거금 통화별조회

- **TR_ID**: TTTC2101R
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/foreign-margin`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | CANO:12345678
ACNT_PRDT_CD:01 |  |
| Response Example | {
    "output": [
        {
            "natn_name": "미국",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "694.37",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "홍콩",
            "crcy_cd": "HKD",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "8247.35",
            "bass_exrt": "172.97000000"
        },
        {
            "natn_name": "홍콩",
            "crcy_cd": "CNY",
            "frcr_dncl_amt1": "1459.110000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "7705.45",
            "bass_exrt": "186.89000000"
        },
        {
            "natn_name": "중화인민공화국",
            "crcy_cd": "CNY",
            "frcr_dncl_amt1": "1459.110000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "1448.97",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "7713.10",
            "bass_exrt": "186.89000000"
        },
        {
            "natn_name": "일본",
            "crcy_cd": "JPY",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "164359.92",
            "bass_exrt": "8.68370000"
        },
        {
            "natn_name": "베트남",
            "crcy_cd": "VND",
            "frcr_dncl_amt1": "377568.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "네덜란드",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "프랑스",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "영국",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "스위스",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "싱가포르",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "독일",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
} |  |

