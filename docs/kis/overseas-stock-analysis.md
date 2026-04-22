# [해외주식] 시세분석 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (15개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 267 | REST | 해외주식 거래증가율순위 | HHDFS76330000 | GET | `/uapi/overseas-stock/v1/ranking/trade-growth` |  |
| 268 | REST | 해외주식 기간별권리조회 | CTRGT011R | GET | `/uapi/overseas-price/v1/quotations/period-rights` |  |
| 269 | REST | 해외주식 가격급등락 | HHDFS76260000 | GET | `/uapi/overseas-stock/v1/ranking/price-fluct` |  |
| 270 | REST | 해외주식 거래대금순위 | HHDFS76320010 | GET | `/uapi/overseas-stock/v1/ranking/trade-pbmn` |  |
| 271 | REST | 해외주식 거래량급증 | HHDFS76270000 | GET | `/uapi/overseas-stock/v1/ranking/volume-surge` |  |
| 272 | REST | 해외주식 신고/신저가 | HHDFS76300000 | GET | `/uapi/overseas-stock/v1/ranking/new-highlow` |  |
| 273 | REST | 해외주식 매수체결강도상위 | HHDFS76280000 | GET | `/uapi/overseas-stock/v1/ranking/volume-power` |  |
| 274 | REST | 해외주식 거래회전율순위 | HHDFS76340000 | GET | `/uapi/overseas-stock/v1/ranking/trade-turnover` |  |
| 275 | REST | 해외뉴스종합(제목) | HHPSTH60100C1 | GET | `/uapi/overseas-price/v1/quotations/news-title` |  |
| 276 | REST | 당사 해외주식담보대출 가능 종목 | CTLN4050R | GET | `/uapi/overseas-price/v1/quotations/colable-by-company` |  |
| 277 | REST | 해외주식 시가총액순위 | HHDFS76350100 | GET | `/uapi/overseas-stock/v1/ranking/market-cap` |  |
| 278 | REST | 해외속보(제목) | FHKST01011801 | GET | `/uapi/overseas-price/v1/quotations/brknews-title` |  |
| 279 | REST | 해외주식 상승율/하락율 | HHDFS76290000 | GET | `/uapi/overseas-stock/v1/ranking/updown-rate` |  |
| 280 | REST | 해외주식 권리종합 | HHDFS78330900 | GET | `/uapi/overseas-price/v1/quotations/rights-by-ice` |  |
| 281 | REST | 해외주식 거래량순위 | HHDFS76310010 | GET | `/uapi/overseas-stock/v1/ranking/trade-vol` |  |

---

## 상세 명세

### 해외주식 거래증가율순위

- **TR_ID**: HHDFS76330000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-growth`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 기간별권리조회

- **TR_ID**: CTRGT011R
- **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/period-rights`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | RGHT_TYPE_CD:%%
INQR_DVSN_CD:02
INQR_STRT_DT:20240417
INQR_END_DT:20240417
PDNO:
PRDT_TYPE_CD:
CTX_AREA_NK50:
CTX_AREA_FK50: |  |
| Response Example | {
    "ctx_area_nk50": "                                                  ",
    "ctx_area_fk50": "%%!^02!^20240417!^20240417!^!^                    ",
    "output": [
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "000661",
            "prdt_name": "[000661]CHANGCHUN HIGH-TECH INDUSTRY (GROUP",
            "prdt_type_cd": "552",
            "std_pdno": "CNE0000007J8",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "450.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "CNY",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "4.50000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "AIR",
            "prdt_name": "AIRBUS GROUP NV",
            "prdt_type_cd": "542",
            "std_pdno": "NL0000235190",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "180.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "EUR",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "1.80000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "GYLD",
            "prdt_name": "ARROW ETF TR ARROW DOW JONES GLOBAL YIELD ETF",
            "prdt_type_cd": "513",
            "std_pdno": "US04273H1041",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "12.6000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.12600",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "NORAM",
            "prdt_name": "NORAM DRILLING",
            "prdt_type_cd": "525",
            "std_pdno": "NO0010360019",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "43.8000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "NOK",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.43800",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "15",
            "pdno": "BENF",
            "prdt_name": "BENEFICIENT",
            "prdt_type_cd": "512",
            "std_pdno": "US08178Q3092",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "1.250000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "15",
            "pdno": "NCNA",
            "prdt_name": "NUCANA PLC SPON ADR EACH REP 25 ORD SHS(POST SPLIT)",
            "prdt_type_cd": "512",
            "std_pdno": "US67022C2052",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "4.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240415",
            "rght_type_cd": "54",
            "pdno": "WWRSF",
            "prdt_name": "RIVERNORTH CAPITAL AND INCM FD INC",
            "prdt_type_cd": "513",
            "std_pdno": "USX589013472",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240415",
            "sbsc_end_dt": "20240417",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "33.333340000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "15.28000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240411",
            "rght_type_cd": "74",
            "pdno": "FTF",
            "prdt_name": "FRANKLIN LIMITED DURATION INCOME TR",
            "prdt_type_cd": "529",
            "std_pdno": "US35472T1016",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240411",
            "sbsc_end_dt": "20240416",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "USD",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240411",
            "rght_type_cd": "74",
            "pdno": "TEI",
            "prdt_name": "TEMPLETON EMERGING MARKETS INC FD",
            "prdt_type_cd": "513",
            "std_pdno": "US8801921094",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240411",
            "sbsc_end_dt": "20240416",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "USD",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "75",
            "pdno": "AIR",
            "prdt_name": "AIRBUS GROUP NV",
            "prdt_type_cd": "542",
            "std_pdno": "NL0000235190",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "100.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "EUR",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "1.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 해외주식 가격급등락

- **TR_ID**: HHDFS76260000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/price-fluct`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 거래대금순위

- **TR_ID**: HHDFS76320010
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-pbmn`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 거래량급증

- **TR_ID**: HHDFS76270000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/volume-surge`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 신고/신저가

- **TR_ID**: HHDFS76300000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/new-highlow`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 해외주식 매수체결강도상위

- **TR_ID**: HHDFS76280000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/volume-power`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 거래회전율순위

- **TR_ID**: HHDFS76340000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-turnover`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외뉴스종합(제목)

- **TR_ID**: HHPSTH60100C1
- **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/news-title`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | INFO_GB:
CLASS_CD:
NATION_CD:
EXCHANGE_CD:
SYMB:
DATA_DT:
DATA_TM:
CTS: |  |
| Response Example | {
    "outblock1": [
        {
            "info_gb": "t",
            "news_key": "ICH709214",
            "data_dt": "20240503",
            "data_tm": "145447",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "톰 리 “단기 내 금리인하 가능”"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709213",
            "data_dt": "20240503",
            "data_tm": "144451",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 연준, 7월 금리인하 예상 GS 외"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709212",
            "data_dt": "20240503",
            "data_tm": "144313",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NAS",
            "symb": "NFLX",
            "symb_name": "넷플릭스",
            "title": "넷플릭스, 광고 전망 낙관 제프리스"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709215",
            "data_dt": "20240503",
            "data_tm": "143706",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 4월 비농업부문 고용자 수 +24.0만 명 추정 아데코"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709208",
            "data_dt": "20240503",
            "data_tm": "142518",
            "class_cd": "03",
            "class_name": "전략/산업",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 모기지 금리, 5주 연속 상승"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709207",
            "data_dt": "20240503",
            "data_tm": "141851",
            "class_cd": "02",
            "class_name": "정책",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "금리, 현재 정점에 있을 확률 높아 펀드스트랫"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709206",
            "data_dt": "20240503",
            "data_tm": "140506",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "FSLY",
            "symb_name": "패스틀리",
            "title": "패스틀리, 단기 악재 직면 - BofA"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709205",
            "data_dt": "20240503",
            "data_tm": "135416",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "TJX",
            "symb_name": "TJX",
            "title": "TJX, 기존 소매점 위협 중 - UBS"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709204",
            "data_dt": "20240503",
            "data_tm": "134647",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NAS",
            "symb": "TTD",
            "symb_name": "트레이드 데스크",
            "title": "트레이드 데스크, 광고시장 현대화로 수혜 가능 - 제프리스"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709203",
            "data_dt": "20240503",
            "data_tm": "133734",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "MGM",
            "symb_name": "MGM 리조츠 인터내셔널",
            "title": "MGM 리조트, 매출 증가세 가속 중 - 서스퀘하나"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 당사 해외주식담보대출 가능 종목

- **TR_ID**: CTLN4050R
- **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/colable-by-company`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | PDNO:AMD
PRDT_TYPE_CD:
INQR_STRT_DT:
INQR_END_DT:
INQR_DVSN:
NATN_CD:840
INQR_SQN_DVSN:02
RT_DVSN_CD:
RT:
LOAN_PSBL_YN:
CTX_AREA_FK100:
CTX_AREA_NK100: |  |
| Response Example | {
    "ctx_area_fk100": "AMD!^!^!^!^!^840!^02                                                                                ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "pdno": "AMD",
            "ovrs_item_name": "AMD",
            "loan_rt": "50.00000000",
            "mgge_mntn_rt": "170.00000000",
            "mgge_ensu_rt": "170.00000000",
            "loan_exec_psbl_yn": "Y",
            "stff_name": "109477.석재민",
            "erlm_dt": "20221230",
            "tr_mket_name": "나스닥",
            "crcy_cd": "USD",
            "natn_kor_name": "미국",
            "ovrs_excg_cd": "NASD"
        }
    ],
    "output2": {
        "loan_psbl_item_num": "403"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 해외주식 시가총액순위

- **TR_ID**: HHDFS76350100
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/market-cap`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외속보(제목)

- **TR_ID**: FHKST01011801
- **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/brknews-title`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_NEWS_OFER_ENTP_CODE:0
FID_COND_MRKT_CLS_CODE:00
FID_INPUT_ISCD:
FID_TITL_CNTT:
FID_INPUT_DATE_1:
FID_INPUT_HOUR_1:
FID_RANK_SORT_CLS_CODE:
FID_INPUT_SRNO:
FID_COND_SCR_DIV_CODE:11801 |  |
| Response Example | {
    "output": [
        {
            "cntt_usiq_srno": "2024052817340622954",
            "news_ofer_entp_code": "U",
            "data_dt": "20240528",
            "data_tm": "173406",
            "hts_pbnt_titl_cntt": "“시진핑, 기업인들 만나 신에너지 분야 과잉투자 경고”",
            "news_lrdv_code": "38",
            "dorg": "서울경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817332725534",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173327",
            "hts_pbnt_titl_cntt": "군부대 찾은 라이칭더, 中포위훈련 언급하며 \"모두 잘 대응\"",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817332721133",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173327",
            "hts_pbnt_titl_cntt": "적십자 \"기후변화로 '극단적 더위' 일수 1년 새 26일 증가\"",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817312094823",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173120",
            "hts_pbnt_titl_cntt": "미국제재 우려했나…중국 하이크비전, 러시아 사업 중단설",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817304250020",
            "news_ofer_entp_code": "8",
            "data_dt": "20240528",
            "data_tm": "173042",
            "hts_pbnt_titl_cntt": "[유럽개장]장 초반 혼조세…獨 0.25%↑",
            "news_lrdv_code": "10",
            "dorg": "아시아 경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817264510344",
            "news_ofer_entp_code": "A",
            "data_dt": "20240528",
            "data_tm": "172645",
            "hts_pbnt_titl_cntt": "122m 협곡 아래로 떨어졌는데 멀쩡하디니…기적 일어난 美 10대",
            "news_lrdv_code": "10",
            "dorg": "매일경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외주식 상승율/하락율

- **TR_ID**: HHDFS76290000
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/updown-rate`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 해외주식 권리종합

- **TR_ID**: HHDFS78330900
- **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/rights-by-ice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | NCOD:US
SYMB:MAIN
ST_YMD:20240214
ED_YMD:20240514 |  |
| Response Example | {
    "output1": [
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240607",
            "pay_dt": "20240614",
            "record_dt": "20240607",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240405",
            "pay_dt": "20240415",
            "record_dt": "20240408",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240507",
            "pay_dt": "20240515",
            "record_dt": "20240508",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240808",
            "pay_dt": "20240815",
            "record_dt": "20240808",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240708",
            "pay_dt": "20240715",
            "record_dt": "20240708",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240906",
            "pay_dt": "20240913",
            "record_dt": "20240906",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외주식 거래량순위

- **TR_ID**: HHDFS76310010
- **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-vol`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |

