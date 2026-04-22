# [국내주식] 업종/기타 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (14개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 71 | REST | 국내주식 예상체결지수 추이 | FHPST01840000 | GET | `/uapi/domestic-stock/v1/quotations/exp-index-trend` |  |
| 72 | REST | 국내주식업종기간별시세(일/주/월/년) | FHKUP03500100 | GET | `/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice` |  |
| 73 | REST | 국내업종 시간별지수(분) | FHPUP02110200 | GET | `/uapi/domestic-stock/v1/quotations/inquire-index-timeprice` |  |
| 74 | REST | 국내업종 구분별전체시세 | FHPUP02140000 | GET | `/uapi/domestic-stock/v1/quotations/inquire-index-category-price` |  |
| 75 | REST | 업종 분봉조회 | FHKUP03500200 | GET | `/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice` |  |
| 76 | REST | 국내휴장일조회 | CTCA0903R | GET | `/uapi/domestic-stock/v1/quotations/chk-holiday` |  |
| 77 | REST | 국내주식 예상체결 전체지수 | FHKUP11750000 | GET | `/uapi/domestic-stock/v1/quotations/exp-total-index` |  |
| 78 | REST | 국내업종 현재지수 | FHPUP02100000 | GET | `/uapi/domestic-stock/v1/quotations/inquire-index-price` |  |
| 79 | REST | 국내선물 영업일조회 | HHMCM000002C0 | GET | `/uapi/domestic-stock/v1/quotations/market-time` |  |
| 80 | REST | 국내업종 시간별지수(초) | FHPUP02110100 | GET | `/uapi/domestic-stock/v1/quotations/inquire-index-tickprice` |  |
| 81 | REST | 국내업종 일자별지수 | FHPUP02120000 | GET | `/uapi/domestic-stock/v1/quotations/inquire-index-daily-price` |  |
| 82 | REST | 금리 종합(국내채권/금리) | FHPST07020000 | GET | `/uapi/domestic-stock/v1/quotations/comp-interest` |  |
| 83 | REST | 변동성완화장치(VI) 현황 | FHPST01390000 | GET | `/uapi/domestic-stock/v1/quotations/inquire-vi-status` |  |
| 84 | REST | 종합 시황/공시(제목) | FHKST01011800 | GET | `/uapi/domestic-stock/v1/quotations/news-title` |  |

---

## 상세 명세

### 국내주식 예상체결지수 추이

- **TR_ID**: FHPST01840000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/exp-index-trend`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:U
fid_input_iscd:0001
fid_input_hour_1:
fid_mkop_cls_code:1 |  |
| Response Example | {
    "output": [
        {
            "stck_cntg_hour": "666666",
            "bstp_nmix_prpr": "2765.30",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "18.67",
            "prdy_ctrt": "0.68",
            "acml_vol": "5951",
            "acml_tr_pbmn": "130953"
        },
        {
            "stck_cntg_hour": "085950",
            "bstp_nmix_prpr": "2766.50",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "19.87",
            "prdy_ctrt": "0.72",
            "acml_vol": "5641",
            "acml_tr_pbmn": "122873"
        },
        {
            "stck_cntg_hour": "085940",
            "bstp_nmix_prpr": "2768.19",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "21.56",
            "prdy_ctrt": "0.78",
            "acml_vol": "5369",
            "acml_tr_pbmn": "115013"
        },
        {
            "stck_cntg_hour": "085930",
            "bstp_nmix_prpr": "2766.70",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.07",
            "prdy_ctrt": "0.73",
            "acml_vol": "5168",
            "acml_tr_pbmn": "107488"
        },
        {
            "stck_cntg_hour": "085920",
            "bstp_nmix_prpr": "2767.01",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.38",
            "prdy_ctrt": "0.74",
            "acml_vol": "5052",
            "acml_tr_pbmn": "103832"
        },
        {
            "stck_cntg_hour": "085910",
            "bstp_nmix_prpr": "2767.09",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.46",
            "prdy_ctrt": "0.74",
            "acml_vol": "4919",
            "acml_tr_pbmn": "101950"
        },
        {
            "stck_cntg_hour": "085900",
            "bstp_nmix_prpr": "2766.91",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.28",
            "prdy_ctrt": "0.74",
            "acml_vol": "4840",
            "acml_tr_pbmn": "99526"
        },
        {
            "stck_cntg_hour": "085850",
            "bstp_nmix_prpr": "2767.06",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.43",
            "prdy_ctrt": "0.74",
            "acml_vol": "4740",
            "acml_tr_pbmn": "93391"
        },
        {
            "stck_cntg_hour": "085840",
            "bstp_nmix_prpr": "2767.12",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.49",
            "prdy_ctrt": "0.75",
            "acml_vol": "4655",
            "acml_tr_pbmn": "92533"
        },
        {
            "stck_cntg_hour": "085830",
            "bstp_nmix_prpr": "2767.27",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.64",
            "prdy_ctrt": "0.75",
            "acml_vol": "4639",
            "acml_tr_pbmn": "91639"
        },
        {
            "stck_cntg_hour": "085820",
            "bstp_nmix_prpr": "2767.35",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.72",
            "prdy_ctrt": "0.75",
            "acml_vol": "4560",
            "acml_tr_pbmn": "90798"
        },
        {
            "stck_cntg_hour": "085810",
            "bstp_nmix_prpr": "2767.22",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.59",
            "prdy_ctrt": "0.75",
            "acml_vol": "4541",
            "acml_tr_pbmn": "93370"
        },
        {
            "stck_cntg_hour": "085800",
            "bstp_nmix_prpr": "2767.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.45",
            "prdy_ctrt": "0.74",
            "acml_vol": "4487",
            "acml_tr_pbmn": "91617"
        },
        {
            "stck_cntg_hour": "085750",
            "bstp_nmix_prpr": "2766.75",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.12",
            "prdy_ctrt": "0.73",
            "acml_vol": "4440",
            "acml_tr_pbmn": "90268"
        },
        {
            "stck_cntg_hour": "085740",
            "bstp_nmix_prpr": "2766.96",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.33",
            "prdy_ctrt": "0.74",
            "acml_vol": "4483",
            "acml_tr_pbmn": "90078"
        },
        {
            "stck_cntg_hour": "085730",
            "bstp_nmix_prpr": "2766.93",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.30",
            "prdy_ctrt": "0.74",
            "acml_vol": "4427",
            "acml_tr_pbmn": "89631"
        },
        {
            "stck_cntg_hour": "085720",
            "bstp_nmix_prpr": "2766.96",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.33",
            "prdy_ctrt": "0.74",
            "acml_vol": "4402",
            "acml_tr_pbmn": "89052"
        },
        {
            "stck_cntg_hour": "085710",
            "bstp_nmix_prpr": "2767.00",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.37",
            "prdy_ctrt": "0.74",
            "acml_vol": "4525",
            "acml_tr_pbmn": "87706"
        },
        {
            "stck_cntg_hour": "085700",
            "bstp_nmix_prpr": "2767.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.45",
            "prdy_ctrt": "0.74",
            "acml_vol": "4660",
            "acml_tr_pbmn": "84754"
        },
        {
            "stck_cntg_hour": "085650",
            "bstp_nmix_prpr": "2767.40",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.77",
            "prdy_ctrt": "0.76",
            "acml_vol": "4636",
            "acml_tr_pbmn": "84339"
        },
        {
            "stck_cntg_hour": "085640",
            "bstp_nmix_prpr": "2767.30",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.67",
            "prdy_ctrt": "0.75",
            "acml_vol": "4569",
            "acml_tr_pbmn": "84041"
        },
        {
            "stck_cntg_hour": "085630",
            "bstp_nmix_prpr": "2767.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.74",
            "prdy_ctrt": "0.76",
            "acml_vol": "4559",
            "acml_tr_pbmn": "83314"
        },
        {
            "stck_cntg_hour": "085620",
            "bstp_nmix_prpr": "2767.43",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.80",
            "prdy_ctrt": "0.76",
            "acml_vol": "4490",
            "acml_tr_pbmn": "83074"
        },
        {
            "stck_cntg_hour": "085610",
            "bstp_nmix_prpr": "2767.74",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "21.11",
            "prdy_ctrt": "0.77",
            "acml_vol": "4436",
            "acml_tr_pbmn": "80274"
        },
        {
            "stck_cntg_hour": "085600",
            "bstp_nmix_prpr": "2766.95",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.32",
            "prdy_ctrt": "0.74",
            "acml_vol": "4032",
            "acml_tr_pbmn": "78386"
        },
        {
            "stck_cntg_hour": "085550",
            "bstp_nmix_prpr": "2766.86",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.23",
            "prdy_ctrt": "0.74",
            "acml_vol": "4026",
            "acml_tr_pbmn": "77796"
        },
        {
            "stck_cntg_hour": "085540",
            "bstp_nmix_prpr": "2766.90",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.27",
            "prdy_ctrt": "0.74",
            "acml_vol": "3946",
            "acml_tr_pbmn": "76794"
        },
        {
            "stck_cntg_hour": "085530",
            "bstp_nmix_prpr": "2767.15",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.52",
            "prdy_ctrt": "0.75",
            "acml_vol": "3932",
            "acml_tr_pbmn": "76859"
        },
        {
            "stck_cntg_hour": "085520",
            "bstp_nmix_prpr": "2766.95",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "20.32",
            "prdy_ctrt": "0.74",
            "acml_vol": "3922",
            "acml_tr_pbmn": "75766"
        },
        {
            "stck_cntg_hour": "085510",
            "bstp_nmix_prpr": "2766.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "19.74",
            "prdy_ctrt": "0.72",
            "acml_vol": "4008",
            "acml_tr_pbmn": "75458"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식업종기간별시세(일/주/월/년)

- **TR_ID**: FHKUP03500100
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 국내업종 시간별지수(분)

- **TR_ID**: FHPUP02110200
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-index-timeprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:U
fid_input_iscd:1001
fid_input_hour_1:120 |  |
| Response Example | {
    "output": [
        {
            "bsop_hour": "100600",
            "bstp_nmix_prpr": "916.77",
            "bstp_nmix_prdy_vrss": "11.27",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3839797",
            "acml_vol": "313374",
            "cntg_vol": "870"
        },
        {
            "bsop_hour": "100400",
            "bstp_nmix_prpr": "916.65",
            "bstp_nmix_prdy_vrss": "11.15",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3829216",
            "acml_vol": "312504",
            "cntg_vol": "4352"
        },
        {
            "bsop_hour": "100200",
            "bstp_nmix_prpr": "916.69",
            "bstp_nmix_prdy_vrss": "11.19",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3779730",
            "acml_vol": "308152",
            "cntg_vol": "4959"
        },
        {
            "bsop_hour": "100000",
            "bstp_nmix_prpr": "916.76",
            "bstp_nmix_prdy_vrss": "11.26",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3716791",
            "acml_vol": "303193",
            "cntg_vol": "5103"
        },
        {
            "bsop_hour": "095800",
            "bstp_nmix_prpr": "916.60",
            "bstp_nmix_prdy_vrss": "11.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3651490",
            "acml_vol": "298090",
            "cntg_vol": "5732"
        },
        {
            "bsop_hour": "095600",
            "bstp_nmix_prpr": "917.37",
            "bstp_nmix_prdy_vrss": "11.87",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3588380",
            "acml_vol": "292358",
            "cntg_vol": "5331"
        },
        {
            "bsop_hour": "095400",
            "bstp_nmix_prpr": "917.64",
            "bstp_nmix_prdy_vrss": "12.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.34",
            "acml_tr_pbmn": "3521010",
            "acml_vol": "287027",
            "cntg_vol": "6827"
        },
        {
            "bsop_hour": "095200",
            "bstp_nmix_prpr": "916.31",
            "bstp_nmix_prdy_vrss": "10.81",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.19",
            "acml_tr_pbmn": "3445942",
            "acml_vol": "280200",
            "cntg_vol": "7263"
        },
        {
            "bsop_hour": "095000",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3373037",
            "acml_vol": "272937",
            "cntg_vol": "5040"
        },
        {
            "bsop_hour": "094800",
            "bstp_nmix_prpr": "916.82",
            "bstp_nmix_prdy_vrss": "11.32",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3304716",
            "acml_vol": "267897",
            "cntg_vol": "6828"
        },
        {
            "bsop_hour": "094600",
            "bstp_nmix_prpr": "916.74",
            "bstp_nmix_prdy_vrss": "11.24",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3222590",
            "acml_vol": "261069",
            "cntg_vol": "8510"
        },
        {
            "bsop_hour": "094400",
            "bstp_nmix_prpr": "914.70",
            "bstp_nmix_prdy_vrss": "9.20",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.02",
            "acml_tr_pbmn": "3137995",
            "acml_vol": "252559",
            "cntg_vol": "6781"
        },
        {
            "bsop_hour": "094200",
            "bstp_nmix_prpr": "914.33",
            "bstp_nmix_prdy_vrss": "8.83",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.98",
            "acml_tr_pbmn": "3073035",
            "acml_vol": "245778",
            "cntg_vol": "7274"
        },
        {
            "bsop_hour": "094000",
            "bstp_nmix_prpr": "914.00",
            "bstp_nmix_prdy_vrss": "8.50",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.94",
            "acml_tr_pbmn": "3001499",
            "acml_vol": "238504",
            "cntg_vol": "7439"
        },
        {
            "bsop_hour": "093800",
            "bstp_nmix_prpr": "913.15",
            "bstp_nmix_prdy_vrss": "7.65",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.84",
            "acml_tr_pbmn": "2908979",
            "acml_vol": "231065",
            "cntg_vol": "8180"
        },
        {
            "bsop_hour": "093600",
            "bstp_nmix_prpr": "912.23",
            "bstp_nmix_prdy_vrss": "6.73",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.74",
            "acml_tr_pbmn": "2815470",
            "acml_vol": "222885",
            "cntg_vol": "7271"
        },
        {
            "bsop_hour": "093400",
            "bstp_nmix_prpr": "911.14",
            "bstp_nmix_prdy_vrss": "5.64",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.62",
            "acml_tr_pbmn": "2729472",
            "acml_vol": "215614",
            "cntg_vol": "6032"
        },
        {
            "bsop_hour": "093200",
            "bstp_nmix_prpr": "911.12",
            "bstp_nmix_prdy_vrss": "5.62",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.62",
            "acml_tr_pbmn": "2640030",
            "acml_vol": "209582",
            "cntg_vol": "7254"
        },
        {
            "bsop_hour": "093000",
            "bstp_nmix_prpr": "910.35",
            "bstp_nmix_prdy_vrss": "4.85",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.54",
            "acml_tr_pbmn": "2542281",
            "acml_vol": "202328",
            "cntg_vol": "7789"
        },
        {
            "bsop_hour": "092800",
            "bstp_nmix_prpr": "911.05",
            "bstp_nmix_prdy_vrss": "5.55",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.61",
            "acml_tr_pbmn": "2420975",
            "acml_vol": "194539",
            "cntg_vol": "8109"
        },
        {
            "bsop_hour": "092600",
            "bstp_nmix_prpr": "911.91",
            "bstp_nmix_prdy_vrss": "6.41",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.71",
            "acml_tr_pbmn": "2312684",
            "acml_vol": "186430",
            "cntg_vol": "8233"
        },
        {
            "bsop_hour": "092400",
            "bstp_nmix_prpr": "912.18",
            "bstp_nmix_prdy_vrss": "6.68",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.74",
            "acml_tr_pbmn": "2210228",
            "acml_vol": "178197",
            "cntg_vol": "8295"
        },
        {
            "bsop_hour": "092200",
            "bstp_nmix_prpr": "912.13",
            "bstp_nmix_prdy_vrss": "6.63",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.73",
            "acml_tr_pbmn": "2106912",
            "acml_vol": "169902",
            "cntg_vol": "9285"
        },
        {
            "bsop_hour": "092000",
            "bstp_nmix_prpr": "910.92",
            "bstp_nmix_prdy_vrss": "5.42",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.60",
            "acml_tr_pbmn": "1980631",
            "acml_vol": "160617",
            "cntg_vol": "10198"
        },
        {
            "bsop_hour": "091800",
            "bstp_nmix_prpr": "910.87",
            "bstp_nmix_prdy_vrss": "5.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.59",
            "acml_tr_pbmn": "1836549",
            "acml_vol": "150419",
            "cntg_vol": "10738"
        },
        {
            "bsop_hour": "091600",
            "bstp_nmix_prpr": "910.99",
            "bstp_nmix_prdy_vrss": "5.49",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.61",
            "acml_tr_pbmn": "1700334",
            "acml_vol": "139681",
            "cntg_vol": "11517"
        },
        {
            "bsop_hour": "091400",
            "bstp_nmix_prpr": "909.83",
            "bstp_nmix_prdy_vrss": "4.33",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.48",
            "acml_tr_pbmn": "1572262",
            "acml_vol": "128164",
            "cntg_vol": "12918"
        },
        {
            "bsop_hour": "091200",
            "bstp_nmix_prpr": "909.84",
            "bstp_nmix_prdy_vrss": "4.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.48",
            "acml_tr_pbmn": "1430578",
            "acml_vol": "115246",
            "cntg_vol": "12623"
        },
        {
            "bsop_hour": "091000",
            "bstp_nmix_prpr": "910.28",
            "bstp_nmix_prdy_vrss": "4.78",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.53",
            "acml_tr_pbmn": "1296270",
            "acml_vol": "102623",
            "cntg_vol": "14403"
        },
        {
            "bsop_hour": "090800",
            "bstp_nmix_prpr": "909.65",
            "bstp_nmix_prdy_vrss": "4.15",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.46",
            "acml_tr_pbmn": "1143581",
            "acml_vol": "88220",
            "cntg_vol": "11854"
        },
        {
            "bsop_hour": "090600",
            "bstp_nmix_prpr": "909.95",
            "bstp_nmix_prdy_vrss": "4.45",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.49",
            "acml_tr_pbmn": "980294",
            "acml_vol": "76366",
            "cntg_vol": "12512"
        },
        {
            "bsop_hour": "090400",
            "bstp_nmix_prpr": "909.15",
            "bstp_nmix_prdy_vrss": "3.65",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.40",
            "acml_tr_pbmn": "805755",
            "acml_vol": "63854",
            "cntg_vol": "14223"
        },
        {
            "bsop_hour": "090200",
            "bstp_nmix_prpr": "908.43",
            "bstp_nmix_prdy_vrss": "2.93",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.32",
            "acml_tr_pbmn": "606769",
            "acml_vol": "49631",
            "cntg_vol": "21310"
        },
        {
            "bsop_hour": "090000",
            "bstp_nmix_prpr": "910.96",
            "bstp_nmix_prdy_vrss": "5.46",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.60",
            "acml_tr_pbmn": "347460",
            "acml_vol": "28321",
            "cntg_vol": "28321"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내업종 구분별전체시세

- **TR_ID**: FHPUP02140000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-index-category-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"U",
"fid_input_iscd":"0001",
"fid_cond_scr_div_code":"20214",
"fid_mrkt_cls_code":"K2",
"fid_blng_cls_code":"0"
} |  |
| Response Example | {
    "output1": {
        "bstp_nmix_prpr": "2648.76",
        "bstp_nmix_prdy_vrss": "34.96",
        "prdy_vrss_sign": "2",
        "bstp_nmix_prdy_ctrt": "1.34",
        "acml_vol": "584715",
        "acml_tr_pbmn": "10001487",
        "bstp_nmix_oprc": "2635.63",
        "bstp_nmix_hgpr": "2648.76",
        "bstp_nmix_lwpr": "2625.01",
        "prdy_vol": "621363",
        "ascn_issu_cnt": "628",
        "down_issu_cnt": "250",
        "stnr_issu_cnt": "58",
        "uplm_issu_cnt": "0",
        "lslm_issu_cnt": "0",
        "prdy_tr_pbmn": "10691024",
        "dryy_bstp_nmix_hgpr_date": "20240102",
        "dryy_bstp_nmix_hgpr": "2675.80",
        "dryy_bstp_nmix_lwpr": "2429.12",
        "dryy_bstp_nmix_lwpr_date": "20240118"
    },
    "output2": [
        {
            "bstp_cls_code": "2001",
            "hts_kor_isnm": "KOSPI200",
            "bstp_nmix_prpr": "355.52",
            "bstp_nmix_prdy_vrss": "4.31",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_vol": "118963",
            "acml_tr_pbmn": "7078909",
            "acml_vol_rlim": "100.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2007",
            "hts_kor_isnm": "KOSPI100",
            "bstp_nmix_prpr": "2691.34",
            "bstp_nmix_prdy_vrss": "33.27",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_vol": "76784",
            "acml_tr_pbmn": "6124444",
            "acml_vol_rlim": "64.54",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2008",
            "hts_kor_isnm": "KOSPI50",
            "bstp_nmix_prpr": "2478.39",
            "bstp_nmix_prdy_vrss": "28.83",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.18",
            "acml_vol": "52269",
            "acml_tr_pbmn": "5222300",
            "acml_vol_rlim": "43.94",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2039",
            "hts_kor_isnm": "K커뮤니케이션서비스",
            "bstp_nmix_prpr": "1850.38",
            "bstp_nmix_prdy_vrss": "3.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.17",
            "acml_vol": "5893",
            "acml_tr_pbmn": "477398",
            "acml_vol_rlim": "4.95",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2009",
            "hts_kor_isnm": "K건설",
            "bstp_nmix_prpr": "325.34",
            "bstp_nmix_prdy_vrss": "8.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.55",
            "acml_vol": "6636",
            "acml_tr_pbmn": "225841",
            "acml_vol_rlim": "5.58",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2010",
            "hts_kor_isnm": "K중공업",
            "bstp_nmix_prpr": "322.92",
            "bstp_nmix_prdy_vrss": "3.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.05",
            "acml_vol": "9613",
            "acml_tr_pbmn": "203930",
            "acml_vol_rlim": "8.08",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2011",
            "hts_kor_isnm": "K철강소재",
            "bstp_nmix_prpr": "884.98",
            "bstp_nmix_prdy_vrss": "35.05",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "4.12",
            "acml_vol": "4814",
            "acml_tr_pbmn": "456186",
            "acml_vol_rlim": "4.05",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2012",
            "hts_kor_isnm": "K에너지화학",
            "bstp_nmix_prpr": "1385.94",
            "bstp_nmix_prdy_vrss": "45.89",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.42",
            "acml_vol": "7623",
            "acml_tr_pbmn": "833756",
            "acml_vol_rlim": "6.41",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2013",
            "hts_kor_isnm": "K정보기술",
            "bstp_nmix_prpr": "3233.61",
            "bstp_nmix_prdy_vrss": "42.48",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.33",
            "acml_vol": "20799",
            "acml_tr_pbmn": "1899061",
            "acml_vol_rlim": "17.48",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2014",
            "hts_kor_isnm": "K금융",
            "bstp_nmix_prpr": "780.59",
            "bstp_nmix_prdy_vrss": "27.94",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.71",
            "acml_vol": "23753",
            "acml_tr_pbmn": "672909",
            "acml_vol_rlim": "19.97",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2015",
            "hts_kor_isnm": "K생활소비재",
            "bstp_nmix_prpr": "793.68",
            "bstp_nmix_prdy_vrss": "12.81",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.64",
            "acml_vol": "4244",
            "acml_tr_pbmn": "288488",
            "acml_vol_rlim": "3.57",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2016",
            "hts_kor_isnm": "K경기소비재",
            "bstp_nmix_prpr": "1724.67",
            "bstp_nmix_prdy_vrss": "42.88",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.55",
            "acml_vol": "10060",
            "acml_tr_pbmn": "1004566",
            "acml_vol_rlim": "8.46",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2017",
            "hts_kor_isnm": "K산업재",
            "bstp_nmix_prpr": "633.49",
            "bstp_nmix_prdy_vrss": "6.82",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.09",
            "acml_vol": "23323",
            "acml_tr_pbmn": "823914",
            "acml_vol_rlim": "19.61",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2018",
            "hts_kor_isnm": "K헬스케어",
            "bstp_nmix_prpr": "1840.09",
            "bstp_nmix_prdy_vrss": "14.36",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.79",
            "acml_vol": "2204",
            "acml_tr_pbmn": "192860",
            "acml_vol_rlim": "1.85",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2019",
            "hts_kor_isnm": "K고배당",
            "bstp_nmix_prpr": "3173.16",
            "bstp_nmix_prdy_vrss": "86.09",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.79",
            "acml_vol": "41569",
            "acml_tr_pbmn": "2859723",
            "acml_vol_rlim": "34.94",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2021",
            "hts_kor_isnm": "K200가치저변동성",
            "bstp_nmix_prpr": "5446.64",
            "bstp_nmix_prdy_vrss": "120.03",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.25",
            "acml_vol": "86859",
            "acml_tr_pbmn": "4469357",
            "acml_vol_rlim": "73.01",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2022",
            "hts_kor_isnm": "K200중소형주",
            "bstp_nmix_prpr": "1221.07",
            "bstp_nmix_prdy_vrss": "22.17",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.85",
            "acml_vol": "42179",
            "acml_tr_pbmn": "954465",
            "acml_vol_rlim": "35.46",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2023",
            "hts_kor_isnm": "K200경기방어소비재",
            "bstp_nmix_prpr": "903.55",
            "bstp_nmix_prdy_vrss": "8.98",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.00",
            "acml_vol": "8450",
            "acml_tr_pbmn": "550010",
            "acml_vol_rlim": "7.10",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2024",
            "hts_kor_isnm": "K200에너지화학 레버리지",
            "bstp_nmix_prpr": "836.53",
            "bstp_nmix_prdy_vrss": "53.55",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "6.84",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2025",
            "hts_kor_isnm": "K200정보기술 레버리지",
            "bstp_nmix_prpr": "4350.42",
            "bstp_nmix_prdy_vrss": "112.40",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.65",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2026",
            "hts_kor_isnm": "K200금융 레버리지",
            "bstp_nmix_prpr": "517.48",
            "bstp_nmix_prdy_vrss": "35.72",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "7.41",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2027",
            "hts_kor_isnm": "K200경기소비재 레버리지",
            "bstp_nmix_prpr": "989.98",
            "bstp_nmix_prdy_vrss": "47.94",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "5.09",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2035",
            "hts_kor_isnm": "코스피200 TR",
            "bstp_nmix_prpr": "449.66",
            "bstp_nmix_prdy_vrss": "5.45",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2036",
            "hts_kor_isnm": "코스피200 NTR",
            "bstp_nmix_prpr": "433.34",
            "bstp_nmix_prdy_vrss": "5.25",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2028",
            "hts_kor_isnm": "K200건설 레버리지",
            "bstp_nmix_prpr": "204.06",
            "bstp_nmix_prdy_vrss": "9.87",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "5.08",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2029",
            "hts_kor_isnm": "K200중공업 레버리지",
            "bstp_nmix_prpr": "169.43",
            "bstp_nmix_prdy_vrss": "3.48",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.10",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2030",
            "hts_kor_isnm": "K200헬스케어 레버리지",
            "bstp_nmix_prpr": "659.07",
            "bstp_nmix_prdy_vrss": "10.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.56",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2040",
            "hts_kor_isnm": "코스피200 초대형 제외지수",
            "bstp_nmix_prpr": "256.52",
            "bstp_nmix_prdy_vrss": "4.70",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.87",
            "acml_vol": "105736",
            "acml_tr_pbmn": "6115607",
            "acml_vol_rlim": "88.88",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2037",
            "hts_kor_isnm": "코스피200 예측 고배당 50",
            "bstp_nmix_prpr": "1989.88",
            "bstp_nmix_prdy_vrss": "49.77",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.57",
            "acml_vol": "22491",
            "acml_tr_pbmn": "1659649",
            "acml_vol_rlim": "18.91",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2038",
            "hts_kor_isnm": "코스피200 예측 배당성장 50",
            "bstp_nmix_prpr": "1661.50",
            "bstp_nmix_prdy_vrss": "33.18",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.04",
            "acml_vol": "39463",
            "acml_tr_pbmn": "2424471",
            "acml_vol_rlim": "33.17",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2041",
            "hts_kor_isnm": "K200 정보기술 TR",
            "bstp_nmix_prpr": "3742.21",
            "bstp_nmix_prdy_vrss": "49.16",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.33",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2042",
            "hts_kor_isnm": "K200 금융 TR",
            "bstp_nmix_prpr": "1192.40",
            "bstp_nmix_prdy_vrss": "42.68",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.71",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2044",
            "hts_kor_isnm": "K200 에너지화학 TR",
            "bstp_nmix_prpr": "1786.68",
            "bstp_nmix_prdy_vrss": "59.16",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.42",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2045",
            "hts_kor_isnm": "K200 생활소비재 TR",
            "bstp_nmix_prpr": "1031.76",
            "bstp_nmix_prdy_vrss": "16.65",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.64",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2046",
            "hts_kor_isnm": "K200 건설 TR",
            "bstp_nmix_prpr": "386.22",
            "bstp_nmix_prdy_vrss": "9.59",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.55",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2047",
            "hts_kor_isnm": "K200 중공업 TR",
            "bstp_nmix_prpr": "356.92",
            "bstp_nmix_prdy_vrss": "3.72",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.05",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2048",
            "hts_kor_isnm": "K200 철강소재 TR",
            "bstp_nmix_prpr": "1172.71",
            "bstp_nmix_prdy_vrss": "46.45",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "4.12",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2049",
            "hts_kor_isnm": "K200 산업재 TR",
            "bstp_nmix_prpr": "753.63",
            "bstp_nmix_prdy_vrss": "8.11",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.09",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2050",
            "hts_kor_isnm": "K200 헬스케어 TR",
            "bstp_nmix_prpr": "1966.27",
            "bstp_nmix_prdy_vrss": "15.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.79",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2051",
            "hts_kor_isnm": "K200 커뮤니케이션서비스 TR",
            "bstp_nmix_prpr": "2355.58",
            "bstp_nmix_prdy_vrss": "4.00",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.17",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2224",
            "hts_kor_isnm": "K200 비중상한 30%",
            "bstp_nmix_prpr": "355.08",
            "bstp_nmix_prdy_vrss": "4.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_vol": "118963",
            "acml_tr_pbmn": "7078909",
            "acml_vol_rlim": "100.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2225",
            "hts_kor_isnm": "K200 비중상한 30%  TR",
            "bstp_nmix_prpr": "449.00",
            "bstp_nmix_prdy_vrss": "5.53",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2226",
            "hts_kor_isnm": "K200 비중상한 30%  NTR",
            "bstp_nmix_prpr": "432.91",
            "bstp_nmix_prdy_vrss": "5.33",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2227",
            "hts_kor_isnm": "K200 비중상한 25%",
            "bstp_nmix_prpr": "351.32",
            "bstp_nmix_prdy_vrss": "4.69",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.35",
            "acml_vol": "118963",
            "acml_tr_pbmn": "7078909",
            "acml_vol_rlim": "100.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2228",
            "hts_kor_isnm": "K200 비중상한 25%  TR",
            "bstp_nmix_prpr": "444.32",
            "bstp_nmix_prdy_vrss": "5.93",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.35",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2230",
            "hts_kor_isnm": "K200 비중상한 25%  NTR",
            "bstp_nmix_prpr": "428.34",
            "bstp_nmix_prdy_vrss": "5.72",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.35",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2232",
            "hts_kor_isnm": "K200 비중상한 20%",
            "bstp_nmix_prpr": "341.02",
            "bstp_nmix_prdy_vrss": "4.89",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.45",
            "acml_vol": "118963",
            "acml_tr_pbmn": "7078909",
            "acml_vol_rlim": "100.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2233",
            "hts_kor_isnm": "K200 비중상한 20%  TR",
            "bstp_nmix_prpr": "430.39",
            "bstp_nmix_prdy_vrss": "6.17",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.45",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2235",
            "hts_kor_isnm": "K200 비중상한 20%  NTR",
            "bstp_nmix_prpr": "415.42",
            "bstp_nmix_prdy_vrss": "5.96",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.46",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2043",
            "hts_kor_isnm": "K200 경기소비재 TR",
            "bstp_nmix_prpr": "2152.99",
            "bstp_nmix_prdy_vrss": "53.53",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.55",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2284",
            "hts_kor_isnm": "코스피 200 선물지수 TWAP형",
            "bstp_nmix_prpr": "1786.47",
            "bstp_nmix_prdy_vrss": "18.33",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.04",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2285",
            "hts_kor_isnm": "코스피 200 선물 TWAP 인버스지수",
            "bstp_nmix_prpr": "2555.41",
            "bstp_nmix_prdy_vrss": "-26.53",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_ctrt": "-1.03",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2286",
            "hts_kor_isnm": "코스피 200 선물 TWAP 레버리지",
            "bstp_nmix_prpr": "1448.92",
            "bstp_nmix_prdy_vrss": "29.55",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.08",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2287",
            "hts_kor_isnm": "코스피 200 선물 TWAP 인버스-2X",
            "bstp_nmix_prpr": "2598.71",
            "bstp_nmix_prdy_vrss": "-54.80",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_ctrt": "-2.07",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2751",
            "hts_kor_isnm": "F-K200 에너지/화학",
            "bstp_nmix_prpr": "1201.20",
            "bstp_nmix_prdy_vrss": "34.48",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.96",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2752",
            "hts_kor_isnm": "F-K200 정보기술",
            "bstp_nmix_prpr": "2051.35",
            "bstp_nmix_prdy_vrss": "18.30",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.90",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2753",
            "hts_kor_isnm": "F-K200 금융",
            "bstp_nmix_prpr": "1291.69",
            "bstp_nmix_prdy_vrss": "40.86",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.27",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2754",
            "hts_kor_isnm": "F-K200 경기소비재",
            "bstp_nmix_prpr": "1121.37",
            "bstp_nmix_prdy_vrss": "17.42",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.58",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2755",
            "hts_kor_isnm": "F-K200 건설",
            "bstp_nmix_prpr": "1218.34",
            "bstp_nmix_prdy_vrss": "25.51",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "2.14",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2756",
            "hts_kor_isnm": "F-K200 중공업",
            "bstp_nmix_prpr": "962.17",
            "bstp_nmix_prdy_vrss": "8.96",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.94",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2757",
            "hts_kor_isnm": "F-K200 헬스케어",
            "bstp_nmix_prpr": "963.71",
            "bstp_nmix_prdy_vrss": "2.84",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.30",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2758",
            "hts_kor_isnm": "F-K200 생활소비재",
            "bstp_nmix_prpr": "637.56",
            "bstp_nmix_prdy_vrss": "1.77",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.28",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2759",
            "hts_kor_isnm": "F-K200 철강/소재",
            "bstp_nmix_prpr": "903.55",
            "bstp_nmix_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "bstp_nmix_prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2760",
            "hts_kor_isnm": "F-K200 산업재",
            "bstp_nmix_prpr": "1031.59",
            "bstp_nmix_prdy_vrss": "7.80",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.76",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2761",
            "hts_kor_isnm": "F-K200 에너지/화학  레버리지",
            "bstp_nmix_prpr": "1039.81",
            "bstp_nmix_prdy_vrss": "58.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "5.92",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2762",
            "hts_kor_isnm": "F-K200 정보기술  레버리지",
            "bstp_nmix_prpr": "3228.56",
            "bstp_nmix_prdy_vrss": "57.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.81",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2763",
            "hts_kor_isnm": "F-K200 금융  레버리지",
            "bstp_nmix_prpr": "1311.74",
            "bstp_nmix_prdy_vrss": "80.53",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "6.54",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2764",
            "hts_kor_isnm": "F-K200 경기소비재  레버리지",
            "bstp_nmix_prpr": "1001.75",
            "bstp_nmix_prdy_vrss": "30.72",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "3.16",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2765",
            "hts_kor_isnm": "F-K200 건설  레버리지",
            "bstp_nmix_prpr": "976.07",
            "bstp_nmix_prdy_vrss": "40.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "4.28",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2766",
            "hts_kor_isnm": "F-K200 중공업  레버리지",
            "bstp_nmix_prpr": "532.58",
            "bstp_nmix_prdy_vrss": "9.86",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.89",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2767",
            "hts_kor_isnm": "F-K200 헬스케어  레버리지",
            "bstp_nmix_prpr": "610.89",
            "bstp_nmix_prdy_vrss": "3.63",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.60",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2768",
            "hts_kor_isnm": "F-K200 생활소비재  레버리지",
            "bstp_nmix_prpr": "376.44",
            "bstp_nmix_prdy_vrss": "2.12",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.57",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2769",
            "hts_kor_isnm": "F-K200 철강/소재  레버리지",
            "bstp_nmix_prpr": "546.02",
            "bstp_nmix_prdy_vrss": "0.04",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.01",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2770",
            "hts_kor_isnm": "F-K200 산업재  레버리지",
            "bstp_nmix_prpr": "868.46",
            "bstp_nmix_prdy_vrss": "13.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.53",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2771",
            "hts_kor_isnm": "F-K200 에너지/화학  인버스",
            "bstp_nmix_prpr": "607.50",
            "bstp_nmix_prdy_vrss": "-18.44",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_ctrt": "-2.95",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2772",
            "hts_kor_isnm": "F-K200 정보기술  인버스",
            "bstp_nmix_prpr": "379.71",
            "bstp_nmix_prdy_vrss": "-3.41",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_ctrt": "-0.89",
            "acml_vol": "0",
            "acml_tr_pbmn": "0",
            "acml_vol_rlim": "0.00",
            "acml_tr_pbmn_rlim": ""
        },
        {
            "bstp_cls_code": "2773",
            "hts_kor_isnm": "F-K200 금융  인버스",
            "bstp_nmix_prpr": "615.73",
            "bstp_nmix_prdy_vrss": "-20.73", |  |


### 업종 분봉조회

- **TR_ID**: FHKUP03500200
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"FID_COND_MRKT_DIV_CODE":"U",
"FID_INPUT_ISCD":"1001",
"FID_INPUT_HOUR_1":"120",
"FID_PW_DATA_INCU_YN":"Y",
"FID_ETC_CLS_CODE":"0"
} |  |
| Response Example | {
    "output1": {
        "bstp_nmix_prdy_vrss": "-3.68",
        "prdy_vrss_sign": "5",
        "bstp_nmix_prdy_ctrt": "-0.44",
        "prdy_nmix": "837.24",
        "acml_vol": "554702",
        "acml_tr_pbmn": "5740155",
        "hts_kor_isnm": "KOSDAQ",
        "bstp_nmix_prpr": "833.56",
        "bstp_cls_code": "1001",
        "prdy_vol": "1238780",
        "bstp_nmix_oprc": "841.21",
        "bstp_nmix_hgpr": "841.21",
        "bstp_nmix_lwpr": "830.09",
        "futs_prdy_oprc": "818.76",
        "futs_prdy_hgpr": "839.52",
        "futs_prdy_lwpr": "817.06"
    },
    "output2": [
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "103200",
            "bstp_nmix_prpr": "833.56",
            "bstp_nmix_oprc": "834.07",
            "bstp_nmix_hgpr": "834.07",
            "bstp_nmix_lwpr": "833.56",
            "cntg_vol": "4618",
            "acml_tr_pbmn": "5740155"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "103000",
            "bstp_nmix_prpr": "833.99",
            "bstp_nmix_oprc": "834.29",
            "bstp_nmix_hgpr": "834.29",
            "bstp_nmix_lwpr": "833.89",
            "cntg_vol": "4601",
            "acml_tr_pbmn": "5689290"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "102800",
            "bstp_nmix_prpr": "834.24",
            "bstp_nmix_oprc": "833.47",
            "bstp_nmix_hgpr": "834.32",
            "bstp_nmix_lwpr": "833.44",
            "cntg_vol": "4978",
            "acml_tr_pbmn": "5635506"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "102600",
            "bstp_nmix_prpr": "833.46",
            "bstp_nmix_oprc": "832.36",
            "bstp_nmix_hgpr": "833.46",
            "bstp_nmix_lwpr": "832.36",
            "cntg_vol": "5033",
            "acml_tr_pbmn": "5581000"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "102400",
            "bstp_nmix_prpr": "832.48",
            "bstp_nmix_oprc": "832.92",
            "bstp_nmix_hgpr": "832.92",
            "bstp_nmix_lwpr": "832.47",
            "cntg_vol": "5239",
            "acml_tr_pbmn": "5518332"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "102200",
            "bstp_nmix_prpr": "832.85",
            "bstp_nmix_oprc": "832.77",
            "bstp_nmix_hgpr": "832.87",
            "bstp_nmix_lwpr": "832.69",
            "cntg_vol": "6042",
            "acml_tr_pbmn": "5455651"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "102000",
            "bstp_nmix_prpr": "832.74",
            "bstp_nmix_oprc": "832.55",
            "bstp_nmix_hgpr": "833.25",
            "bstp_nmix_lwpr": "832.55",
            "cntg_vol": "6301",
            "acml_tr_pbmn": "5372736"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "101800",
            "bstp_nmix_prpr": "832.83",
            "bstp_nmix_oprc": "832.51",
            "bstp_nmix_hgpr": "832.83",
            "bstp_nmix_lwpr": "832.22",
            "cntg_vol": "5676",
            "acml_tr_pbmn": "5284172"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "101600",
            "bstp_nmix_prpr": "832.50",
            "bstp_nmix_oprc": "832.27",
            "bstp_nmix_hgpr": "832.62",
            "bstp_nmix_lwpr": "832.09",
            "cntg_vol": "4771",
            "acml_tr_pbmn": "5219827"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "101400",
            "bstp_nmix_prpr": "832.44",
            "bstp_nmix_oprc": "832.03",
            "bstp_nmix_hgpr": "832.52",
            "bstp_nmix_lwpr": "832.03",
            "cntg_vol": "6639",
            "acml_tr_pbmn": "5167005"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "101200",
            "bstp_nmix_prpr": "832.11",
            "bstp_nmix_oprc": "831.98",
            "bstp_nmix_hgpr": "832.24",
            "bstp_nmix_lwpr": "831.75",
            "cntg_vol": "6946",
            "acml_tr_pbmn": "5093186"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "101000",
            "bstp_nmix_prpr": "832.23",
            "bstp_nmix_oprc": "831.36",
            "bstp_nmix_hgpr": "832.23",
            "bstp_nmix_lwpr": "831.35",
            "cntg_vol": "6579",
            "acml_tr_pbmn": "5011060"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "100800",
            "bstp_nmix_prpr": "831.22",
            "bstp_nmix_oprc": "831.05",
            "bstp_nmix_hgpr": "831.22",
            "bstp_nmix_lwpr": "830.55",
            "cntg_vol": "6837",
            "acml_tr_pbmn": "4928657"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "100600",
            "bstp_nmix_prpr": "830.98",
            "bstp_nmix_oprc": "831.46",
            "bstp_nmix_hgpr": "831.54",
            "bstp_nmix_lwpr": "830.98",
            "cntg_vol": "6694",
            "acml_tr_pbmn": "4854815"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "100400",
            "bstp_nmix_prpr": "831.76",
            "bstp_nmix_oprc": "830.79",
            "bstp_nmix_hgpr": "831.76",
            "bstp_nmix_lwpr": "830.79",
            "cntg_vol": "6839",
            "acml_tr_pbmn": "4781557"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "100200",
            "bstp_nmix_prpr": "830.92",
            "bstp_nmix_oprc": "831.17",
            "bstp_nmix_hgpr": "831.21",
            "bstp_nmix_lwpr": "830.71",
            "cntg_vol": "9589",
            "acml_tr_pbmn": "4724555"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "100000",
            "bstp_nmix_prpr": "831.14",
            "bstp_nmix_oprc": "831.32",
            "bstp_nmix_hgpr": "831.52",
            "bstp_nmix_lwpr": "830.90",
            "cntg_vol": "8688",
            "acml_tr_pbmn": "4652376"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "095800",
            "bstp_nmix_prpr": "831.56",
            "bstp_nmix_oprc": "831.32",
            "bstp_nmix_hgpr": "831.76",
            "bstp_nmix_lwpr": "831.32",
            "cntg_vol": "6519",
            "acml_tr_pbmn": "4568901"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "095600",
            "bstp_nmix_prpr": "831.43",
            "bstp_nmix_oprc": "830.68",
            "bstp_nmix_hgpr": "831.43",
            "bstp_nmix_lwpr": "830.52",
            "cntg_vol": "7474",
            "acml_tr_pbmn": "4497224"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "095400",
            "bstp_nmix_prpr": "830.50",
            "bstp_nmix_oprc": "831.46",
            "bstp_nmix_hgpr": "831.46",
            "bstp_nmix_lwpr": "830.50",
            "cntg_vol": "9190",
            "acml_tr_pbmn": "4423313"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "095200",
            "bstp_nmix_prpr": "831.57",
            "bstp_nmix_oprc": "831.45",
            "bstp_nmix_hgpr": "831.59",
            "bstp_nmix_lwpr": "831.38",
            "cntg_vol": "7701",
            "acml_tr_pbmn": "4324541"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "095000",
            "bstp_nmix_prpr": "831.60",
            "bstp_nmix_oprc": "831.45",
            "bstp_nmix_hgpr": "831.82",
            "bstp_nmix_lwpr": "831.39",
            "cntg_vol": "7529",
            "acml_tr_pbmn": "4247753"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "094800",
            "bstp_nmix_prpr": "831.57",
            "bstp_nmix_oprc": "831.71",
            "bstp_nmix_hgpr": "831.76",
            "bstp_nmix_lwpr": "831.47",
            "cntg_vol": "7754",
            "acml_tr_pbmn": "4165554"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "094600",
            "bstp_nmix_prpr": "831.77",
            "bstp_nmix_oprc": "830.50",
            "bstp_nmix_hgpr": "831.91",
            "bstp_nmix_lwpr": "830.44",
            "cntg_vol": "9213",
            "acml_tr_pbmn": "4076635"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "094400",
            "bstp_nmix_prpr": "830.26",
            "bstp_nmix_oprc": "830.57",
            "bstp_nmix_hgpr": "830.67",
            "bstp_nmix_lwpr": "830.09",
            "cntg_vol": "7201",
            "acml_tr_pbmn": "3971601"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "094200",
            "bstp_nmix_prpr": "830.53",
            "bstp_nmix_oprc": "831.03",
            "bstp_nmix_hgpr": "831.21",
            "bstp_nmix_lwpr": "830.48",
            "cntg_vol": "7992",
            "acml_tr_pbmn": "3886154"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "094000",
            "bstp_nmix_prpr": "830.98",
            "bstp_nmix_oprc": "831.26",
            "bstp_nmix_hgpr": "831.26",
            "bstp_nmix_lwpr": "830.32",
            "cntg_vol": "9912",
            "acml_tr_pbmn": "3790733"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "093800",
            "bstp_nmix_prpr": "831.32",
            "bstp_nmix_oprc": "832.07",
            "bstp_nmix_hgpr": "832.07",
            "bstp_nmix_lwpr": "831.27",
            "cntg_vol": "9575",
            "acml_tr_pbmn": "3663618"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "093600",
            "bstp_nmix_prpr": "832.24",
            "bstp_nmix_oprc": "831.34",
            "bstp_nmix_hgpr": "832.30",
            "bstp_nmix_lwpr": "831.34",
            "cntg_vol": "10164",
            "acml_tr_pbmn": "3561037"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "093400",
            "bstp_nmix_prpr": "831.44",
            "bstp_nmix_oprc": "832.64",
            "bstp_nmix_hgpr": "832.64",
            "bstp_nmix_lwpr": "831.44",
            "cntg_vol": "11415",
            "acml_tr_pbmn": "3447235"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "093200",
            "bstp_nmix_prpr": "832.53",
            "bstp_nmix_oprc": "833.45",
            "bstp_nmix_hgpr": "833.66",
            "bstp_nmix_lwpr": "832.53",
            "cntg_vol": "11522",
            "acml_tr_pbmn": "3316543"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "093000",
            "bstp_nmix_prpr": "833.58",
            "bstp_nmix_oprc": "833.59",
            "bstp_nmix_hgpr": "834.05",
            "bstp_nmix_lwpr": "833.36",
            "cntg_vol": "11105",
            "acml_tr_pbmn": "3203362"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "092800",
            "bstp_nmix_prpr": "833.97",
            "bstp_nmix_oprc": "832.91",
            "bstp_nmix_hgpr": "833.97",
            "bstp_nmix_lwpr": "832.36",
            "cntg_vol": "15502",
            "acml_tr_pbmn": "3071005"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "092600",
            "bstp_nmix_prpr": "833.08",
            "bstp_nmix_oprc": "835.04",
            "bstp_nmix_hgpr": "835.04",
            "bstp_nmix_lwpr": "833.00",
            "cntg_vol": "15656",
            "acml_tr_pbmn": "2928429"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "092400",
            "bstp_nmix_prpr": "834.63",
            "bstp_nmix_oprc": "833.51",
            "bstp_nmix_hgpr": "834.98",
            "bstp_nmix_lwpr": "833.51",
            "cntg_vol": "16851",
            "acml_tr_pbmn": "2747155"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "092200",
            "bstp_nmix_prpr": "833.45",
            "bstp_nmix_oprc": "835.50",
            "bstp_nmix_hgpr": "835.50",
            "bstp_nmix_lwpr": "833.45",
            "cntg_vol": "16696",
            "acml_tr_pbmn": "2583365"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "092000",
            "bstp_nmix_prpr": "835.91",
            "bstp_nmix_oprc": "835.96",
            "bstp_nmix_hgpr": "836.14",
            "bstp_nmix_lwpr": "835.76",
            "cntg_vol": "16008",
            "acml_tr_pbmn": "2424467"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "091800",
            "bstp_nmix_prpr": "836.05",
            "bstp_nmix_oprc": "838.39",
            "bstp_nmix_hgpr": "838.39",
            "bstp_nmix_lwpr": "835.98",
            "cntg_vol": "16778",
            "acml_tr_pbmn": "2260216"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "091600",
            "bstp_nmix_prpr": "838.24",
            "bstp_nmix_oprc": "837.19",
            "bstp_nmix_hgpr": "838.70",
            "bstp_nmix_lwpr": "837.19",
            "cntg_vol": "17379",
            "acml_tr_pbmn": "2098721"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "091400",
            "bstp_nmix_prpr": "836.82",
            "bstp_nmix_oprc": "836.88",
            "bstp_nmix_hgpr": "837.94",
            "bstp_nmix_lwpr": "836.48",
            "cntg_vol": "19020",
            "acml_tr_pbmn": "1934637"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "091200",
            "bstp_nmix_prpr": "836.73",
            "bstp_nmix_oprc": "837.87",
            "bstp_nmix_hgpr": "838.34",
            "bstp_nmix_lwpr": "836.73",
            "cntg_vol": "27881",
            "acml_tr_pbmn": "1781817"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "091000",
            "bstp_nmix_prpr": "837.70",
            "bstp_nmix_oprc": "837.68",
            "bstp_nmix_hgpr": "837.72",
            "bstp_nmix_lwpr": "837.38",
            "cntg_vol": "16983",
            "acml_tr_pbmn": "1606668"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "090800",
            "bstp_nmix_prpr": "837.87",
            "bstp_nmix_oprc": "840.59",
            "bstp_nmix_hgpr": "840.59",
            "bstp_nmix_lwpr": "837.87",
            "cntg_vol": "21991",
            "acml_tr_pbmn": "1441148"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "090600",
            "bstp_nmix_prpr": "840.98",
            "bstp_nmix_oprc": "839.46",
            "bstp_nmix_hgpr": "841.17",
            "bstp_nmix_lwpr": "839.46",
            "cntg_vol": "20366",
            "acml_tr_pbmn": "1234692"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "090400",
            "bstp_nmix_prpr": "839.42",
            "bstp_nmix_oprc": "836.70",
            "bstp_nmix_hgpr": "839.42",
            "bstp_nmix_lwpr": "836.70",
            "cntg_vol": "27395",
            "acml_tr_pbmn": "1007681"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "090200",
            "bstp_nmix_prpr": "836.69",
            "bstp_nmix_oprc": "838.54",
            "bstp_nmix_hgpr": "838.54",
            "bstp_nmix_lwpr": "835.19",
            "cntg_vol": "31941",
            "acml_tr_pbmn": "754939"
        },
        {
            "stck_bsop_date": "20240129",
            "stck_cntg_hour": "090000",
            "bstp_nmix_prpr": "838.62",
            "bstp_nmix_oprc": "841.21",
            "bstp_nmix_hgpr": "841.21",
            "bstp_nmix_lwpr": "838.42",
            "cntg_vol": "33919",
            "acml_tr_pbmn": "422108"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "999999",
            "bstp_nmix_prpr": "837.24",
            "bstp_nmix_oprc": "837.24",
            "bstp_nmix_hgpr": "837.24",
            "bstp_nmix_lwpr": "837.24",
            "cntg_vol": "21566",
            "acml_tr_pbmn": "11242548"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "888888",
            "bstp_nmix_prpr": "837.24",
            "bstp_nmix_oprc": "837.24",
            "bstp_nmix_hgpr": "837.24",
            "bstp_nmix_lwpr": "837.24",
            "cntg_vol": "42",
            "acml_tr_pbmn": "11058431"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "153200",
            "bstp_nmix_prpr": "837.20",
            "bstp_nmix_oprc": "837.19",
            "bstp_nmix_hgpr": "837.20",
            "bstp_nmix_lwpr": "837.19",
            "cntg_vol": "126",
            "acml_tr_pbmn": "11057509"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "153000",
            "bstp_nmix_prpr": "837.19",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "837.25",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "17043",
            "acml_tr_pbmn": "11056788"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "152800",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.97",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "0",
            "acml_tr_pbmn": "10792443"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "152600",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.97",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "0",
            "acml_tr_pbmn": "10792443"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "152400",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.97",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "0",
            "acml_tr_pbmn": "10792443"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "152200",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.97",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "0",
            "acml_tr_pbmn": "10792443"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "152000",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.97",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "1000",
            "acml_tr_pbmn": "10792443"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "151800",
            "bstp_nmix_prpr": "837.01",
            "bstp_nmix_oprc": "836.79",
            "bstp_nmix_hgpr": "837.05",
            "bstp_nmix_lwpr": "836.49",
            "cntg_vol": "8328",
            "acml_tr_pbmn": "10784186"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "151600",
            "bstp_nmix_prpr": "836.90",
            "bstp_nmix_oprc": "836.72",
            "bstp_nmix_hgpr": "836.93",
            "bstp_nmix_lwpr": "836.64",
            "cntg_vol": "6227",
            "acml_tr_pbmn": "10699895"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "151400",
            "bstp_nmix_prpr": "836.86",
            "bstp_nmix_oprc": "836.63",
            "bstp_nmix_hgpr": "836.96",
            "bstp_nmix_lwpr": "836.57",
            "cntg_vol": "5728",
            "acml_tr_pbmn": "10633883"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "151200",
            "bstp_nmix_prpr": "836.70",
            "bstp_nmix_oprc": "836.71",
            "bstp_nmix_hgpr": "836.84",
            "bstp_nmix_lwpr": "836.44",
            "cntg_vol": "6163",
            "acml_tr_pbmn": "10578452"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "151000",
            "bstp_nmix_prpr": "836.83",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "836.98",
            "bstp_nmix_lwpr": "836.69",
            "cntg_vol": "4617",
            "acml_tr_pbmn": "10523064"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "150800",
            "bstp_nmix_prpr": "836.92",
            "bstp_nmix_oprc": "836.97",
            "bstp_nmix_hgpr": "837.02",
            "bstp_nmix_lwpr": "836.70",
            "cntg_vol": "4728",
            "acml_tr_pbmn": "10472083"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "150600",
            "bstp_nmix_prpr": "836.97",
            "bstp_nmix_oprc": "836.70",
            "bstp_nmix_hgpr": "837.06",
            "bstp_nmix_lwpr": "836.70",
            "cntg_vol": "4719",
            "acml_tr_pbmn": "10420811"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "150400",
            "bstp_nmix_prpr": "836.66",
            "bstp_nmix_oprc": "836.19",
            "bstp_nmix_hgpr": "836.92",
            "bstp_nmix_lwpr": "836.19",
            "cntg_vol": "4377",
            "acml_tr_pbmn": "10372366"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "150200",
            "bstp_nmix_prpr": "836.29",
            "bstp_nmix_oprc": "836.18",
            "bstp_nmix_hgpr": "836.38",
            "bstp_nmix_lwpr": "836.18",
            "cntg_vol": "4261",
            "acml_tr_pbmn": "10320188"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "150000",
            "bstp_nmix_prpr": "836.28",
            "bstp_nmix_oprc": "836.24",
            "bstp_nmix_hgpr": "836.44",
            "bstp_nmix_lwpr": "836.20",
            "cntg_vol": "4420",
            "acml_tr_pbmn": "10273218"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "145800",
            "bstp_nmix_prpr": "836.43",
            "bstp_nmix_oprc": "837.13",
            "bstp_nmix_hgpr": "837.18",
            "bstp_nmix_lwpr": "836.43",
            "cntg_vol": "4215",
            "acml_tr_pbmn": "10218137"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "145600",
            "bstp_nmix_prpr": "837.23",
            "bstp_nmix_oprc": "837.95",
            "bstp_nmix_hgpr": "838.01",
            "bstp_nmix_lwpr": "837.23",
            "cntg_vol": "4978",
            "acml_tr_pbmn": "10166106"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "145400",
            "bstp_nmix_prpr": "837.89",
            "bstp_nmix_oprc": "837.66",
            "bstp_nmix_hgpr": "837.96",
            "bstp_nmix_lwpr": "837.66",
            "cntg_vol": "5102",
            "acml_tr_pbmn": "10110923"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "145200",
            "bstp_nmix_prpr": "837.66",
            "bstp_nmix_oprc": "837.41",
            "bstp_nmix_hgpr": "837.66",
            "bstp_nmix_lwpr": "837.22",
            "cntg_vol": "3840",
            "acml_tr_pbmn": "10055054"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "145000",
            "bstp_nmix_prpr": "837.58",
            "bstp_nmix_oprc": "837.24",
            "bstp_nmix_hgpr": "837.71",
            "bstp_nmix_lwpr": "837.24",
            "cntg_vol": "4172",
            "acml_tr_pbmn": "10008690"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "144800",
            "bstp_nmix_prpr": "837.37",
            "bstp_nmix_oprc": "837.80",
            "bstp_nmix_hgpr": "837.80",
            "bstp_nmix_lwpr": "837.23",
            "cntg_vol": "4593",
            "acml_tr_pbmn": "9966720"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "144600",
            "bstp_nmix_prpr": "837.66",
            "bstp_nmix_oprc": "837.72",
            "bstp_nmix_hgpr": "837.89",
            "bstp_nmix_lwpr": "837.61",
            "cntg_vol": "5105",
            "acml_tr_pbmn": "9916624"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "144400",
            "bstp_nmix_prpr": "837.72",
            "bstp_nmix_oprc": "837.55",
            "bstp_nmix_hgpr": "837.72",
            "bstp_nmix_lwpr": "837.42",
            "cntg_vol": "4214",
            "acml_tr_pbmn": "9861241"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "144200",
            "bstp_nmix_prpr": "837.50",
            "bstp_nmix_oprc": "837.55",
            "bstp_nmix_hgpr": "837.68",
            "bstp_nmix_lwpr": "837.35",
            "cntg_vol": "3357",
            "acml_tr_pbmn": "9819268"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "144000",
            "bstp_nmix_prpr": "837.56",
            "bstp_nmix_oprc": "837.93",
            "bstp_nmix_hgpr": "838.04",
            "bstp_nmix_lwpr": "837.56",
            "cntg_vol": "3515",
            "acml_tr_pbmn": "9783824"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "143800",
            "bstp_nmix_prpr": "837.96",
            "bstp_nmix_oprc": "837.49",
            "bstp_nmix_hgpr": "837.96",
            "bstp_nmix_lwpr": "837.49",
            "cntg_vol": "4026",
            "acml_tr_pbmn": "9745091"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "143600",
            "bstp_nmix_prpr": "837.50",
            "bstp_nmix_oprc": "837.47",
            "bstp_nmix_hgpr": "837.59",
            "bstp_nmix_lwpr": "837.25",
            "cntg_vol": "4327",
            "acml_tr_pbmn": "9702397"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "143400",
            "bstp_nmix_prpr": "837.44",
            "bstp_nmix_oprc": "837.19",
            "bstp_nmix_hgpr": "837.44",
            "bstp_nmix_lwpr": "836.97",
            "cntg_vol": "3352",
            "acml_tr_pbmn": "9664056"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "143200",
            "bstp_nmix_prpr": "837.19",
            "bstp_nmix_oprc": "837.00",
            "bstp_nmix_hgpr": "837.19",
            "bstp_nmix_lwpr": "836.85",
            "cntg_vol": "3969",
            "acml_tr_pbmn": "9626091"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "143000",
            "bstp_nmix_prpr": "836.85",
            "bstp_nmix_oprc": "836.27",
            "bstp_nmix_hgpr": "836.85",
            "bstp_nmix_lwpr": "836.10",
            "cntg_vol": "4263",
            "acml_tr_pbmn": "9584077"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "142800",
            "bstp_nmix_prpr": "836.18",
            "bstp_nmix_oprc": "835.52",
            "bstp_nmix_hgpr": "836.24",
            "bstp_nmix_lwpr": "835.52",
            "cntg_vol": "4294",
            "acml_tr_pbmn": "9542286"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "142600",
            "bstp_nmix_prpr": "835.62",
            "bstp_nmix_oprc": "835.41",
            "bstp_nmix_hgpr": "835.66",
            "bstp_nmix_lwpr": "835.41",
            "cntg_vol": "3538",
            "acml_tr_pbmn": "9501271"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "142400",
            "bstp_nmix_prpr": "835.44",
            "bstp_nmix_oprc": "835.54",
            "bstp_nmix_hgpr": "835.68",
            "bstp_nmix_lwpr": "835.37",
            "cntg_vol": "3291",
            "acml_tr_pbmn": "9469724"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "142200",
            "bstp_nmix_prpr": "835.48",
            "bstp_nmix_oprc": "835.60",
            "bstp_nmix_hgpr": "835.60",
            "bstp_nmix_lwpr": "835.28",
            "cntg_vol": "3640",
            "acml_tr_pbmn": "9433016"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "142000",
            "bstp_nmix_prpr": "835.70",
            "bstp_nmix_oprc": "835.57",
            "bstp_nmix_hgpr": "835.72",
            "bstp_nmix_lwpr": "835.51",
            "cntg_vol": "4522",
            "acml_tr_pbmn": "9401939"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "141800",
            "bstp_nmix_prpr": "835.54",
            "bstp_nmix_oprc": "835.99",
            "bstp_nmix_hgpr": "836.00",
            "bstp_nmix_lwpr": "835.34",
            "cntg_vol": "3266",
            "acml_tr_pbmn": "9365741"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "141600",
            "bstp_nmix_prpr": "835.98",
            "bstp_nmix_oprc": "836.29",
            "bstp_nmix_hgpr": "836.37",
            "bstp_nmix_lwpr": "835.98",
            "cntg_vol": "4813",
            "acml_tr_pbmn": "9334612"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "141400",
            "bstp_nmix_prpr": "836.34",
            "bstp_nmix_oprc": "835.77",
            "bstp_nmix_hgpr": "836.34",
            "bstp_nmix_lwpr": "835.77",
            "cntg_vol": "4714",
            "acml_tr_pbmn": "9284831"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "141200",
            "bstp_nmix_prpr": "835.79",
            "bstp_nmix_oprc": "835.74",
            "bstp_nmix_hgpr": "835.98",
            "bstp_nmix_lwpr": "835.58",
            "cntg_vol": "4125",
            "acml_tr_pbmn": "9238577"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "141000",
            "bstp_nmix_prpr": "835.74",
            "bstp_nmix_oprc": "835.45",
            "bstp_nmix_hgpr": "835.74",
            "bstp_nmix_lwpr": "835.45",
            "cntg_vol": "4232",
            "acml_tr_pbmn": "9193950"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "140800",
            "bstp_nmix_prpr": "835.10",
            "bstp_nmix_oprc": "835.07",
            "bstp_nmix_hgpr": "835.32",
            "bstp_nmix_lwpr": "835.00",
            "cntg_vol": "3639",
            "acml_tr_pbmn": "9151925"
        },
        {
            "stck_bsop_date": "20240126",
            "stck_cntg_hour": "140600",
            "bstp_nmix_prpr": "835.10",
            "bstp_nmix_oprc": "835.09",
            "bstp_nmix_hgpr": "835.23",
            "bstp_nmix_lwpr": "834.96",
            "cntg_vol": "4277", |  |


### 국내휴장일조회

- **TR_ID**: CTCA0903R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/chk-holiday`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "BASS_DT":"20221227",
    "CTX_AREA_NK":"",
    "CTX_AREA_FK":""
} |  |
| Response Example | {
    "ctx_area_nk": "20230119            ",
    "ctx_area_fk": "20221227            ",
    "output": [
        {
            "bass_dt": "20221227",
            "wday_dvsn_cd": "03",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20221228",
            "wday_dvsn_cd": "04",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20221229",
            "wday_dvsn_cd": "05",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20221230",
            "wday_dvsn_cd": "06",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20221231",
            "wday_dvsn_cd": "07",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230101",
            "wday_dvsn_cd": "01",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230102",
            "wday_dvsn_cd": "02",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230103",
            "wday_dvsn_cd": "03",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230104",
            "wday_dvsn_cd": "04",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230105",
            "wday_dvsn_cd": "05",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230106",
            "wday_dvsn_cd": "06",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230107",
            "wday_dvsn_cd": "07",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230108",
            "wday_dvsn_cd": "01",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230109",
            "wday_dvsn_cd": "02",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230110",
            "wday_dvsn_cd": "03",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230111",
            "wday_dvsn_cd": "04",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230112",
            "wday_dvsn_cd": "05",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230113",
            "wday_dvsn_cd": "06",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230114",
            "wday_dvsn_cd": "07",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230115",
            "wday_dvsn_cd": "01",
            "bzdy_yn": "N",
            "tr_day_yn": "Y",
            "opnd_yn": "N",
            "sttl_day_yn": "N"
        },
        {
            "bass_dt": "20230116",
            "wday_dvsn_cd": "02",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230117",
            "wday_dvsn_cd": "03",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230118",
            "wday_dvsn_cd": "04",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        },
        {
            "bass_dt": "20230119",
            "wday_dvsn_cd": "05",
            "bzdy_yn": "Y",
            "tr_day_yn": "Y",
            "opnd_yn": "Y",
            "sttl_day_yn": "Y"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0500",
    "msg1": "조회가 계속됩니다..다음버튼을 Click 하십시오.                                   "
} |  |


### 국내주식 예상체결 전체지수

- **TR_ID**: FHKUP11750000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/exp-total-index`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"U",
"fid_cond_scr_div_code":"11175",
"fid_input_iscd":"1001",
"fid_mkop_cls_code":"1",
"fid_mrkt_cls_code":"K"
} |  |
| Response Example | {
    "output1": {
        "bstp_nmix_prpr": "883.03",
        "bstp_nmix_prdy_vrss": "2.57",
        "prdy_vrss_sign": "2",
        "prdy_ctrt": "0.29",
        "acml_vol": "10611",
        "ascn_issu_cnt": "513",
        "down_issu_cnt": "571",
        "stnr_issu_cnt": "498"
    },
    "output2": [
        {
            "bstp_cls_code": "0001",
            "hts_kor_isnm": "종합",
            "bstp_nmix_prpr": "2676.62",
            "bstp_nmix_prdy_vrss": "9.78",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.37",
            "acml_vol": "5151",
            "nmix_sdpr": "2666.84",
            "ascn_issu_cnt": "409",
            "stnr_issu_cnt": "249",
            "down_issu_cnt": "225"
        },
        {
            "bstp_cls_code": "2001",
            "hts_kor_isnm": "KOSPI200",
            "bstp_nmix_prpr": "360.44",
            "bstp_nmix_prdy_vrss": "1.05",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.29",
            "acml_vol": "1687",
            "nmix_sdpr": "359.39",
            "ascn_issu_cnt": "148",
            "stnr_issu_cnt": "35",
            "down_issu_cnt": "17"
        },
        {
            "bstp_cls_code": "2039",
            "hts_kor_isnm": "K커뮤니케이션서비스",
            "bstp_nmix_prpr": "1766.78",
            "bstp_nmix_prdy_vrss": "9.03",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.51",
            "acml_vol": "42",
            "nmix_sdpr": "1757.75",
            "ascn_issu_cnt": "7",
            "stnr_issu_cnt": "2",
            "down_issu_cnt": "1"
        },
        {
            "bstp_cls_code": "2009",
            "hts_kor_isnm": "K건설",
            "bstp_nmix_prpr": "320.87",
            "bstp_nmix_prdy_vrss": "0.09",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.03",
            "acml_vol": "76",
            "nmix_sdpr": "320.78",
            "ascn_issu_cnt": "3",
            "stnr_issu_cnt": "6",
            "down_issu_cnt": "1"
        },
        {
            "bstp_cls_code": "2010",
            "hts_kor_isnm": "K중공업",
            "bstp_nmix_prpr": "366.27",
            "bstp_nmix_prdy_vrss": "5.35",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.48",
            "acml_vol": "457",
            "nmix_sdpr": "360.92",
            "ascn_issu_cnt": "12",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "1"
        },
        {
            "bstp_cls_code": "2011",
            "hts_kor_isnm": "K철강소재",
            "bstp_nmix_prpr": "857.19",
            "bstp_nmix_prdy_vrss": "6.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.75",
            "acml_vol": "45",
            "nmix_sdpr": "850.85",
            "ascn_issu_cnt": "7",
            "stnr_issu_cnt": "3",
            "down_issu_cnt": "1"
        },
        {
            "bstp_cls_code": "2012",
            "hts_kor_isnm": "K에너지화학",
            "bstp_nmix_prpr": "1349.16",
            "bstp_nmix_prdy_vrss": "8.62",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.64",
            "acml_vol": "33",
            "nmix_sdpr": "1340.54",
            "ascn_issu_cnt": "22",
            "stnr_issu_cnt": "4",
            "down_issu_cnt": "2"
        },
        {
            "bstp_cls_code": "2013",
            "hts_kor_isnm": "K정보기술",
            "bstp_nmix_prpr": "3334.19",
            "bstp_nmix_prdy_vrss": "3.80",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.11",
            "acml_vol": "546",
            "nmix_sdpr": "3330.39",
            "ascn_issu_cnt": "8",
            "stnr_issu_cnt": "3",
            "down_issu_cnt": "2"
        },
        {
            "bstp_cls_code": "2014",
            "hts_kor_isnm": "K금융",
            "bstp_nmix_prpr": "832.71",
            "bstp_nmix_prdy_vrss": "-2.77",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_ctrt": "-0.33",
            "acml_vol": "208",
            "nmix_sdpr": "835.48",
            "ascn_issu_cnt": "12",
            "stnr_issu_cnt": "7",
            "down_issu_cnt": "3"
        },
        {
            "bstp_cls_code": "2015",
            "hts_kor_isnm": "K생활소비재",
            "bstp_nmix_prpr": "807.22",
            "bstp_nmix_prdy_vrss": "5.94",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.74",
            "acml_vol": "39",
            "nmix_sdpr": "801.28",
            "ascn_issu_cnt": "20",
            "stnr_issu_cnt": "3",
            "down_issu_cnt": "1"
        },
        {
            "bstp_cls_code": "2016",
            "hts_kor_isnm": "K경기소비재",
            "bstp_nmix_prpr": "1771.78",
            "bstp_nmix_prdy_vrss": "9.87",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.56",
            "acml_vol": "71",
            "nmix_sdpr": "1761.91",
            "ascn_issu_cnt": "26",
            "stnr_issu_cnt": "4",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2017",
            "hts_kor_isnm": "K산업재",
            "bstp_nmix_prpr": "638.85",
            "bstp_nmix_prdy_vrss": "3.52",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.55",
            "acml_vol": "144",
            "nmix_sdpr": "635.33",
            "ascn_issu_cnt": "19",
            "stnr_issu_cnt": "1",
            "down_issu_cnt": "3"
        },
        {
            "bstp_cls_code": "2018",
            "hts_kor_isnm": "K헬스케어",
            "bstp_nmix_prpr": "1880.59",
            "bstp_nmix_prdy_vrss": "7.50",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.40",
            "acml_vol": "25",
            "nmix_sdpr": "1873.09",
            "ascn_issu_cnt": "12",
            "stnr_issu_cnt": "2",
            "down_issu_cnt": "2"
        },
        {
            "bstp_cls_code": "0163",
            "hts_kor_isnm": "고배당50",
            "bstp_nmix_prpr": "3012.54",
            "bstp_nmix_prdy_vrss": "2.40",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.08",
            "acml_vol": "654",
            "nmix_sdpr": "3010.14",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "0164",
            "hts_kor_isnm": "배당성장50",
            "bstp_nmix_prpr": "3697.71",
            "bstp_nmix_prdy_vrss": "14.09",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.38",
            "acml_vol": "557",
            "nmix_sdpr": "3683.62",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "0165",
            "hts_kor_isnm": "우선주",
            "bstp_nmix_prpr": "3159.80",
            "bstp_nmix_prdy_vrss": "3.00",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.10",
            "acml_vol": "27",
            "nmix_sdpr": "3156.80",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2180",
            "hts_kor_isnm": "코스피 200 ESG 지수",
            "bstp_nmix_prpr": "408.37",
            "bstp_nmix_prdy_vrss": "0.89",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.22",
            "acml_vol": "1068",
            "nmix_sdpr": "407.48",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2040",
            "hts_kor_isnm": "코스피200 초대형 제외지수",
            "bstp_nmix_prpr": "261.99",
            "bstp_nmix_prdy_vrss": "0.79",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.30",
            "acml_vol": "1276",
            "nmix_sdpr": "261.20",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2037",
            "hts_kor_isnm": "코스피200 예측 고배당 50",
            "bstp_nmix_prpr": "2034.64",
            "bstp_nmix_prdy_vrss": "7.50",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.37",
            "acml_vol": "227",
            "nmix_sdpr": "2027.14",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2038",
            "hts_kor_isnm": "코스피200 예측 배당성장 50",
            "bstp_nmix_prpr": "1710.41",
            "bstp_nmix_prdy_vrss": "9.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.53",
            "acml_vol": "581",
            "nmix_sdpr": "1701.33",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2224",
            "hts_kor_isnm": "K200 비중상한 30%",
            "bstp_nmix_prpr": "360.08",
            "bstp_nmix_prdy_vrss": "1.06",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.30",
            "acml_vol": "1687",
            "nmix_sdpr": "359.02",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2227",
            "hts_kor_isnm": "K200 비중상한 25%",
            "bstp_nmix_prpr": "356.69",
            "bstp_nmix_prdy_vrss": "1.04",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.29",
            "acml_vol": "1687",
            "nmix_sdpr": "355.65",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2232",
            "hts_kor_isnm": "K200 비중상한 20%",
            "bstp_nmix_prpr": "346.65",
            "bstp_nmix_prdy_vrss": "1.02",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.30",
            "acml_vol": "1687",
            "nmix_sdpr": "345.63",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "0244",
            "hts_kor_isnm": "코스피200제외 코스피지수",
            "bstp_nmix_prpr": "3337.06",
            "bstp_nmix_prdy_vrss": "10.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.31",
            "acml_vol": "3373",
            "nmix_sdpr": "3326.72",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        },
        {
            "bstp_cls_code": "2283",
            "hts_kor_isnm": "코스피 200 기후변화지수",
            "bstp_nmix_prpr": "1580.49",
            "bstp_nmix_prdy_vrss": "4.56",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "0.29",
            "acml_vol": "1639",
            "nmix_sdpr": "1575.93",
            "ascn_issu_cnt": "0",
            "stnr_issu_cnt": "0",
            "down_issu_cnt": "0"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내업종 현재지수

- **TR_ID**: FHPUP02100000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-index-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"U"
"fid_input_iscd":"1001"
} |  |
| Response Example | {
    "output": {
        "bstp_nmix_prpr": "857.60",
        "bstp_nmix_prdy_vrss": "-1.61",
        "prdy_vrss_sign": "5",
        "bstp_nmix_prdy_ctrt": "-0.19",
        "acml_vol": "1312496",
        "prdy_vol": "1222188",
        "acml_tr_pbmn": "11507962",
        "prdy_tr_pbmn": "11203385",
        "bstp_nmix_oprc": "863.69",
        "prdy_nmix_vrss_nmix_oprc": "4.48",
        "oprc_vrss_prpr_sign": "2",
        "bstp_nmix_oprc_prdy_ctrt": "0.52",
        "bstp_nmix_hgpr": "864.24",
        "prdy_nmix_vrss_nmix_hgpr": "5.03",
        "hgpr_vrss_prpr_sign": "2",
        "bstp_nmix_hgpr_prdy_ctrt": "0.59",
        "bstp_nmix_lwpr": "854.72",
        "prdy_clpr_vrss_lwpr": "-4.49",
        "lwpr_vrss_prpr_sign": "5",
        "prdy_clpr_vrss_lwpr_rate": "-0.52",
        "ascn_issu_cnt": "828",
        "uplm_issu_cnt": "5",
        "stnr_issu_cnt": "94",
        "down_issu_cnt": "716",
        "lslm_issu_cnt": "1",
        "dryy_bstp_nmix_hgpr": "890.06",
        "dryy_hgpr_vrss_prpr_rate": "3.65",
        "dryy_bstp_nmix_hgpr_date": "20240109",
        "dryy_bstp_nmix_lwpr": "786.28",
        "dryy_lwpr_vrss_prpr_rate": "-9.07",
        "dryy_bstp_nmix_lwpr_date": "20240201",
        "total_askp_rsqn": "24146999",
        "total_bidp_rsqn": "40450437",
        "seln_rsqn_rate": "37.38",
        "shnu_rsqn_rate": "62.62",
        "ntby_rsqn": "16303438"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내선물 영업일조회

- **TR_ID**: HHMCM000002C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/market-time`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | 없음 |  |
| Response Example | {
    "output1": {
        "date1": "20240909",
        "date2": "20240910",
        "date3": "20240911",
        "date4": "20240912",
        "date5": "20240913",
        "today": "20240911",
        "time": "083523",
        "s_time": "084500",
        "e_time": "154500"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내업종 시간별지수(초)

- **TR_ID**: FHPUP02110100
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-index-tickprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | fid_cond_mrkt_div_code:U
fid_input_iscd:1001 |  |
| Response Example | {
    "output": [
        {
            "stck_cntg_hour": "100520",
            "bstp_nmix_prpr": "916.59",
            "bstp_nmix_prdy_vrss": "11.09",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.22",
            "acml_tr_pbmn": "3818437",
            "acml_vol": "311514",
            "cntg_vol": "378"
        },
        {
            "stck_cntg_hour": "100510",
            "bstp_nmix_prpr": "916.56",
            "bstp_nmix_prdy_vrss": "11.06",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.22",
            "acml_tr_pbmn": "3814862",
            "acml_vol": "311136",
            "cntg_vol": "389"
        },
        {
            "stck_cntg_hour": "100500",
            "bstp_nmix_prpr": "916.60",
            "bstp_nmix_prdy_vrss": "11.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3811191",
            "acml_vol": "310747",
            "cntg_vol": "460"
        },
        {
            "stck_cntg_hour": "100450",
            "bstp_nmix_prpr": "916.71",
            "bstp_nmix_prdy_vrss": "11.21",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3806215",
            "acml_vol": "310287",
            "cntg_vol": "347"
        },
        {
            "stck_cntg_hour": "100440",
            "bstp_nmix_prpr": "916.71",
            "bstp_nmix_prdy_vrss": "11.21",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3802603",
            "acml_vol": "309940",
            "cntg_vol": "378"
        },
        {
            "stck_cntg_hour": "100430",
            "bstp_nmix_prpr": "916.87",
            "bstp_nmix_prdy_vrss": "11.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3798885",
            "acml_vol": "309562",
            "cntg_vol": "390"
        },
        {
            "stck_cntg_hour": "100420",
            "bstp_nmix_prpr": "916.87",
            "bstp_nmix_prdy_vrss": "11.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3793980",
            "acml_vol": "309172",
            "cntg_vol": "331"
        },
        {
            "stck_cntg_hour": "100410",
            "bstp_nmix_prpr": "916.69",
            "bstp_nmix_prdy_vrss": "11.19",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3789649",
            "acml_vol": "308841",
            "cntg_vol": "387"
        },
        {
            "stck_cntg_hour": "100400",
            "bstp_nmix_prpr": "916.47",
            "bstp_nmix_prdy_vrss": "10.97",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3784355",
            "acml_vol": "308454",
            "cntg_vol": "302"
        },
        {
            "stck_cntg_hour": "100350",
            "bstp_nmix_prpr": "916.69",
            "bstp_nmix_prdy_vrss": "11.19",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3779730",
            "acml_vol": "308152",
            "cntg_vol": "389"
        },
        {
            "stck_cntg_hour": "100340",
            "bstp_nmix_prpr": "916.64",
            "bstp_nmix_prdy_vrss": "11.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3774584",
            "acml_vol": "307763",
            "cntg_vol": "359"
        },
        {
            "stck_cntg_hour": "100330",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3769289",
            "acml_vol": "307404",
            "cntg_vol": "590"
        },
        {
            "stck_cntg_hour": "100320",
            "bstp_nmix_prpr": "916.86",
            "bstp_nmix_prdy_vrss": "11.36",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3764728",
            "acml_vol": "306814",
            "cntg_vol": "395"
        },
        {
            "stck_cntg_hour": "100310",
            "bstp_nmix_prpr": "916.76",
            "bstp_nmix_prdy_vrss": "11.26",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3758157",
            "acml_vol": "306419",
            "cntg_vol": "414"
        },
        {
            "stck_cntg_hour": "100300",
            "bstp_nmix_prpr": "917.03",
            "bstp_nmix_prdy_vrss": "11.53",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3753915",
            "acml_vol": "306005",
            "cntg_vol": "351"
        },
        {
            "stck_cntg_hour": "100250",
            "bstp_nmix_prpr": "917.08",
            "bstp_nmix_prdy_vrss": "11.58",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28",
            "acml_tr_pbmn": "3749232",
            "acml_vol": "305654",
            "cntg_vol": "440"
        },
        {
            "stck_cntg_hour": "100240",
            "bstp_nmix_prpr": "917.18",
            "bstp_nmix_prdy_vrss": "11.68",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.29",
            "acml_tr_pbmn": "3741905",
            "acml_vol": "305214",
            "cntg_vol": "324"
        },
        {
            "stck_cntg_hour": "100230",
            "bstp_nmix_prpr": "917.27",
            "bstp_nmix_prdy_vrss": "11.77",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.30",
            "acml_tr_pbmn": "3737983",
            "acml_vol": "304890",
            "cntg_vol": "449"
        },
        {
            "stck_cntg_hour": "100220",
            "bstp_nmix_prpr": "917.31",
            "bstp_nmix_prdy_vrss": "11.81",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.30",
            "acml_tr_pbmn": "3732890",
            "acml_vol": "304441",
            "cntg_vol": "459"
        },
        {
            "stck_cntg_hour": "100210",
            "bstp_nmix_prpr": "916.61",
            "bstp_nmix_prdy_vrss": "11.11",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3725485",
            "acml_vol": "303982",
            "cntg_vol": "424"
        },
        {
            "stck_cntg_hour": "100200",
            "bstp_nmix_prpr": "916.64",
            "bstp_nmix_prdy_vrss": "11.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3720969",
            "acml_vol": "303558",
            "cntg_vol": "365"
        },
        {
            "stck_cntg_hour": "100150",
            "bstp_nmix_prpr": "916.76",
            "bstp_nmix_prdy_vrss": "11.26",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3716791",
            "acml_vol": "303193",
            "cntg_vol": "377"
        },
        {
            "stck_cntg_hour": "100140",
            "bstp_nmix_prpr": "916.49",
            "bstp_nmix_prdy_vrss": "10.99",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3712492",
            "acml_vol": "302816",
            "cntg_vol": "392"
        },
        {
            "stck_cntg_hour": "100130",
            "bstp_nmix_prpr": "916.49",
            "bstp_nmix_prdy_vrss": "10.99",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3707273",
            "acml_vol": "302424",
            "cntg_vol": "324"
        },
        {
            "stck_cntg_hour": "100120",
            "bstp_nmix_prpr": "916.60",
            "bstp_nmix_prdy_vrss": "11.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3702465",
            "acml_vol": "302100",
            "cntg_vol": "430"
        },
        {
            "stck_cntg_hour": "100110",
            "bstp_nmix_prpr": "916.55",
            "bstp_nmix_prdy_vrss": "11.05",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.22",
            "acml_tr_pbmn": "3698004",
            "acml_vol": "301670",
            "cntg_vol": "387"
        },
        {
            "stck_cntg_hour": "100100",
            "bstp_nmix_prpr": "916.33",
            "bstp_nmix_prdy_vrss": "10.83",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.20",
            "acml_tr_pbmn": "3692560",
            "acml_vol": "301283",
            "cntg_vol": "428"
        },
        {
            "stck_cntg_hour": "100050",
            "bstp_nmix_prpr": "916.43",
            "bstp_nmix_prdy_vrss": "10.93",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3687275",
            "acml_vol": "300855",
            "cntg_vol": "437"
        },
        {
            "stck_cntg_hour": "100040",
            "bstp_nmix_prpr": "916.79",
            "bstp_nmix_prdy_vrss": "11.29",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3681346",
            "acml_vol": "300418",
            "cntg_vol": "465"
        },
        {
            "stck_cntg_hour": "100030",
            "bstp_nmix_prpr": "917.01",
            "bstp_nmix_prdy_vrss": "11.51",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3676019",
            "acml_vol": "299953",
            "cntg_vol": "453"
        },
        {
            "stck_cntg_hour": "100020",
            "bstp_nmix_prpr": "916.77",
            "bstp_nmix_prdy_vrss": "11.27",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3669136",
            "acml_vol": "299500",
            "cntg_vol": "443"
        },
        {
            "stck_cntg_hour": "100010",
            "bstp_nmix_prpr": "916.76",
            "bstp_nmix_prdy_vrss": "11.26",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3663148",
            "acml_vol": "299057",
            "cntg_vol": "523"
        },
        {
            "stck_cntg_hour": "100000",
            "bstp_nmix_prpr": "916.49",
            "bstp_nmix_prdy_vrss": "10.99",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3656614",
            "acml_vol": "298534",
            "cntg_vol": "444"
        },
        {
            "stck_cntg_hour": "095950",
            "bstp_nmix_prpr": "916.60",
            "bstp_nmix_prdy_vrss": "11.10",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3651490",
            "acml_vol": "298090",
            "cntg_vol": "388"
        },
        {
            "stck_cntg_hour": "095940",
            "bstp_nmix_prpr": "916.84",
            "bstp_nmix_prdy_vrss": "11.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3646864",
            "acml_vol": "297702",
            "cntg_vol": "446"
        },
        {
            "stck_cntg_hour": "095930",
            "bstp_nmix_prpr": "916.90",
            "bstp_nmix_prdy_vrss": "11.40",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3642503",
            "acml_vol": "297256",
            "cntg_vol": "426"
        },
        {
            "stck_cntg_hour": "095920",
            "bstp_nmix_prpr": "917.04",
            "bstp_nmix_prdy_vrss": "11.54",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3638580",
            "acml_vol": "296830",
            "cntg_vol": "493"
        },
        {
            "stck_cntg_hour": "095910",
            "bstp_nmix_prpr": "916.99",
            "bstp_nmix_prdy_vrss": "11.49",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3634479",
            "acml_vol": "296337",
            "cntg_vol": "456"
        },
        {
            "stck_cntg_hour": "095900",
            "bstp_nmix_prpr": "917.02",
            "bstp_nmix_prdy_vrss": "11.52",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3629148",
            "acml_vol": "295881",
            "cntg_vol": "602"
        },
        {
            "stck_cntg_hour": "095850",
            "bstp_nmix_prpr": "917.16",
            "bstp_nmix_prdy_vrss": "11.66",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.29",
            "acml_tr_pbmn": "3621794",
            "acml_vol": "295279",
            "cntg_vol": "652"
        },
        {
            "stck_cntg_hour": "095840",
            "bstp_nmix_prpr": "917.35",
            "bstp_nmix_prdy_vrss": "11.85",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3616303",
            "acml_vol": "294627",
            "cntg_vol": "361"
        },
        {
            "stck_cntg_hour": "095830",
            "bstp_nmix_prpr": "917.33",
            "bstp_nmix_prdy_vrss": "11.83",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3612169",
            "acml_vol": "294266",
            "cntg_vol": "454"
        },
        {
            "stck_cntg_hour": "095820",
            "bstp_nmix_prpr": "917.37",
            "bstp_nmix_prdy_vrss": "11.87",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3607064",
            "acml_vol": "293812",
            "cntg_vol": "515"
        },
        {
            "stck_cntg_hour": "095810",
            "bstp_nmix_prpr": "917.32",
            "bstp_nmix_prdy_vrss": "11.82",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3601548",
            "acml_vol": "293297",
            "cntg_vol": "545"
        },
        {
            "stck_cntg_hour": "095800",
            "bstp_nmix_prpr": "917.20",
            "bstp_nmix_prdy_vrss": "11.70",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.29",
            "acml_tr_pbmn": "3594204",
            "acml_vol": "292752",
            "cntg_vol": "394"
        },
        {
            "stck_cntg_hour": "095750",
            "bstp_nmix_prpr": "917.37",
            "bstp_nmix_prdy_vrss": "11.87",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.31",
            "acml_tr_pbmn": "3588380",
            "acml_vol": "292358",
            "cntg_vol": "392"
        },
        {
            "stck_cntg_hour": "095740",
            "bstp_nmix_prpr": "917.29",
            "bstp_nmix_prdy_vrss": "11.79",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.30",
            "acml_tr_pbmn": "3583543",
            "acml_vol": "291966",
            "cntg_vol": "383"
        },
        {
            "stck_cntg_hour": "095730",
            "bstp_nmix_prpr": "917.16",
            "bstp_nmix_prdy_vrss": "11.66",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.29",
            "acml_tr_pbmn": "3578536",
            "acml_vol": "291583",
            "cntg_vol": "372"
        },
        {
            "stck_cntg_hour": "095720",
            "bstp_nmix_prpr": "917.09",
            "bstp_nmix_prdy_vrss": "11.59",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28",
            "acml_tr_pbmn": "3573648",
            "acml_vol": "291211",
            "cntg_vol": "387"
        },
        {
            "stck_cntg_hour": "095710",
            "bstp_nmix_prpr": "917.12",
            "bstp_nmix_prdy_vrss": "11.62",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28",
            "acml_tr_pbmn": "3568052",
            "acml_vol": "290824",
            "cntg_vol": "481"
        },
        {
            "stck_cntg_hour": "095700",
            "bstp_nmix_prpr": "916.83",
            "bstp_nmix_prdy_vrss": "11.33",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3562707",
            "acml_vol": "290343",
            "cntg_vol": "376"
        },
        {
            "stck_cntg_hour": "095650",
            "bstp_nmix_prpr": "916.72",
            "bstp_nmix_prdy_vrss": "11.22",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3558237",
            "acml_vol": "289967",
            "cntg_vol": "457"
        },
        {
            "stck_cntg_hour": "095640",
            "bstp_nmix_prpr": "916.76",
            "bstp_nmix_prdy_vrss": "11.26",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3552581",
            "acml_vol": "289510",
            "cntg_vol": "596"
        },
        {
            "stck_cntg_hour": "095630",
            "bstp_nmix_prpr": "917.30",
            "bstp_nmix_prdy_vrss": "11.80",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.30",
            "acml_tr_pbmn": "3544456",
            "acml_vol": "288914",
            "cntg_vol": "406"
        },
        {
            "stck_cntg_hour": "095620",
            "bstp_nmix_prpr": "917.51",
            "bstp_nmix_prdy_vrss": "12.01",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.33",
            "acml_tr_pbmn": "3538246",
            "acml_vol": "288508",
            "cntg_vol": "579"
        },
        {
            "stck_cntg_hour": "095610",
            "bstp_nmix_prpr": "917.52",
            "bstp_nmix_prdy_vrss": "12.02",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.33",
            "acml_tr_pbmn": "3532214",
            "acml_vol": "287929",
            "cntg_vol": "495"
        },
        {
            "stck_cntg_hour": "095600",
            "bstp_nmix_prpr": "917.61",
            "bstp_nmix_prdy_vrss": "12.11",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.34",
            "acml_tr_pbmn": "3526666",
            "acml_vol": "287434",
            "cntg_vol": "407"
        },
        {
            "stck_cntg_hour": "095550",
            "bstp_nmix_prpr": "917.64",
            "bstp_nmix_prdy_vrss": "12.14",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.34",
            "acml_tr_pbmn": "3521010",
            "acml_vol": "287027",
            "cntg_vol": "614"
        },
        {
            "stck_cntg_hour": "095540",
            "bstp_nmix_prpr": "917.58",
            "bstp_nmix_prdy_vrss": "12.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.33",
            "acml_tr_pbmn": "3514113",
            "acml_vol": "286413",
            "cntg_vol": "414"
        },
        {
            "stck_cntg_hour": "095530",
            "bstp_nmix_prpr": "917.70",
            "bstp_nmix_prdy_vrss": "12.20",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.35",
            "acml_tr_pbmn": "3507645",
            "acml_vol": "285999",
            "cntg_vol": "527"
        },
        {
            "stck_cntg_hour": "095520",
            "bstp_nmix_prpr": "917.44",
            "bstp_nmix_prdy_vrss": "11.94",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.32",
            "acml_tr_pbmn": "3501459",
            "acml_vol": "285472",
            "cntg_vol": "556"
        },
        {
            "stck_cntg_hour": "095510",
            "bstp_nmix_prpr": "917.61",
            "bstp_nmix_prdy_vrss": "12.11",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.34",
            "acml_tr_pbmn": "3495215",
            "acml_vol": "284916",
            "cntg_vol": "584"
        },
        {
            "stck_cntg_hour": "095500",
            "bstp_nmix_prpr": "917.09",
            "bstp_nmix_prdy_vrss": "11.59",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28",
            "acml_tr_pbmn": "3485132",
            "acml_vol": "284332",
            "cntg_vol": "657"
        },
        {
            "stck_cntg_hour": "095450",
            "bstp_nmix_prpr": "916.99",
            "bstp_nmix_prdy_vrss": "11.49",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3478768",
            "acml_vol": "283675",
            "cntg_vol": "708"
        },
        {
            "stck_cntg_hour": "095440",
            "bstp_nmix_prpr": "916.84",
            "bstp_nmix_prdy_vrss": "11.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3473716",
            "acml_vol": "282967",
            "cntg_vol": "477"
        },
        {
            "stck_cntg_hour": "095430",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3468638",
            "acml_vol": "282490",
            "cntg_vol": "538"
        },
        {
            "stck_cntg_hour": "095420",
            "bstp_nmix_prpr": "916.65",
            "bstp_nmix_prdy_vrss": "11.15",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3463123",
            "acml_vol": "281952",
            "cntg_vol": "644"
        },
        {
            "stck_cntg_hour": "095410",
            "bstp_nmix_prpr": "916.52",
            "bstp_nmix_prdy_vrss": "11.02",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.22",
            "acml_tr_pbmn": "3456930",
            "acml_vol": "281308",
            "cntg_vol": "557"
        },
        {
            "stck_cntg_hour": "095400",
            "bstp_nmix_prpr": "916.28",
            "bstp_nmix_prdy_vrss": "10.78",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.19",
            "acml_tr_pbmn": "3451089",
            "acml_vol": "280751",
            "cntg_vol": "551"
        },
        {
            "stck_cntg_hour": "095350",
            "bstp_nmix_prpr": "916.31",
            "bstp_nmix_prdy_vrss": "10.81",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.19",
            "acml_tr_pbmn": "3445942",
            "acml_vol": "280200",
            "cntg_vol": "825"
        },
        {
            "stck_cntg_hour": "095340",
            "bstp_nmix_prpr": "916.25",
            "bstp_nmix_prdy_vrss": "10.75",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.19",
            "acml_tr_pbmn": "3440251",
            "acml_vol": "279375",
            "cntg_vol": "594"
        },
        {
            "stck_cntg_hour": "095330",
            "bstp_nmix_prpr": "916.47",
            "bstp_nmix_prdy_vrss": "10.97",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.21",
            "acml_tr_pbmn": "3433966",
            "acml_vol": "278781",
            "cntg_vol": "896"
        },
        {
            "stck_cntg_hour": "095320",
            "bstp_nmix_prpr": "916.56",
            "bstp_nmix_prdy_vrss": "11.06",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.22",
            "acml_tr_pbmn": "3423815",
            "acml_vol": "277885",
            "cntg_vol": "670"
        },
        {
            "stck_cntg_hour": "095310",
            "bstp_nmix_prpr": "916.81",
            "bstp_nmix_prdy_vrss": "11.31",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3416973",
            "acml_vol": "277215",
            "cntg_vol": "818"
        },
        {
            "stck_cntg_hour": "095300",
            "bstp_nmix_prpr": "916.85",
            "bstp_nmix_prdy_vrss": "11.35",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3409854",
            "acml_vol": "276397",
            "cntg_vol": "777"
        },
        {
            "stck_cntg_hour": "095250",
            "bstp_nmix_prpr": "917.09",
            "bstp_nmix_prdy_vrss": "11.59",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28",
            "acml_tr_pbmn": "3404203",
            "acml_vol": "275620",
            "cntg_vol": "474"
        },
        {
            "stck_cntg_hour": "095240",
            "bstp_nmix_prpr": "916.99",
            "bstp_nmix_prdy_vrss": "11.49",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3398691",
            "acml_vol": "275146",
            "cntg_vol": "457"
        },
        {
            "stck_cntg_hour": "095230",
            "bstp_nmix_prpr": "916.96",
            "bstp_nmix_prdy_vrss": "11.46",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3392384",
            "acml_vol": "274689",
            "cntg_vol": "315"
        },
        {
            "stck_cntg_hour": "095220",
            "bstp_nmix_prpr": "916.84",
            "bstp_nmix_prdy_vrss": "11.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3387938",
            "acml_vol": "274374",
            "cntg_vol": "391"
        },
        {
            "stck_cntg_hour": "095210",
            "bstp_nmix_prpr": "916.96",
            "bstp_nmix_prdy_vrss": "11.46",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3383576",
            "acml_vol": "273983",
            "cntg_vol": "543"
        },
        {
            "stck_cntg_hour": "095200",
            "bstp_nmix_prpr": "917.01",
            "bstp_nmix_prdy_vrss": "11.51",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3377596",
            "acml_vol": "273440",
            "cntg_vol": "503"
        },
        {
            "stck_cntg_hour": "095150",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3373037",
            "acml_vol": "272937",
            "cntg_vol": "407"
        },
        {
            "stck_cntg_hour": "095140",
            "bstp_nmix_prpr": "916.73",
            "bstp_nmix_prdy_vrss": "11.23",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3365439",
            "acml_vol": "272530",
            "cntg_vol": "487"
        },
        {
            "stck_cntg_hour": "095130",
            "bstp_nmix_prpr": "916.63",
            "bstp_nmix_prdy_vrss": "11.13",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.23",
            "acml_tr_pbmn": "3359798",
            "acml_vol": "272043",
            "cntg_vol": "418"
        },
        {
            "stck_cntg_hour": "095120",
            "bstp_nmix_prpr": "916.74",
            "bstp_nmix_prdy_vrss": "11.24",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3354130",
            "acml_vol": "271625",
            "cntg_vol": "439"
        },
        {
            "stck_cntg_hour": "095110",
            "bstp_nmix_prpr": "916.73",
            "bstp_nmix_prdy_vrss": "11.23",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.24",
            "acml_tr_pbmn": "3347725",
            "acml_vol": "271186",
            "cntg_vol": "459"
        },
        {
            "stck_cntg_hour": "095100",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3340647",
            "acml_vol": "270727",
            "cntg_vol": "393"
        },
        {
            "stck_cntg_hour": "095050",
            "bstp_nmix_prpr": "916.85",
            "bstp_nmix_prdy_vrss": "11.35",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3335589",
            "acml_vol": "270334",
            "cntg_vol": "358"
        },
        {
            "stck_cntg_hour": "095040",
            "bstp_nmix_prpr": "916.85",
            "bstp_nmix_prdy_vrss": "11.35",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3330288",
            "acml_vol": "269976",
            "cntg_vol": "390"
        },
        {
            "stck_cntg_hour": "095030",
            "bstp_nmix_prpr": "916.88",
            "bstp_nmix_prdy_vrss": "11.38",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3325139",
            "acml_vol": "269586",
            "cntg_vol": "399"
        },
        {
            "stck_cntg_hour": "095020",
            "bstp_nmix_prpr": "916.94",
            "bstp_nmix_prdy_vrss": "11.44",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3320375",
            "acml_vol": "269187",
            "cntg_vol": "463"
        },
        {
            "stck_cntg_hour": "095010",
            "bstp_nmix_prpr": "916.95",
            "bstp_nmix_prdy_vrss": "11.45",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.26",
            "acml_tr_pbmn": "3315297",
            "acml_vol": "268724",
            "cntg_vol": "416"
        },
        {
            "stck_cntg_hour": "095000",
            "bstp_nmix_prpr": "916.97",
            "bstp_nmix_prdy_vrss": "11.47",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3310129",
            "acml_vol": "268308",
            "cntg_vol": "411"
        },
        {
            "stck_cntg_hour": "094950",
            "bstp_nmix_prpr": "916.82",
            "bstp_nmix_prdy_vrss": "11.32",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.25",
            "acml_tr_pbmn": "3304716",
            "acml_vol": "267897",
            "cntg_vol": "505"
        },
        {
            "stck_cntg_hour": "094940",
            "bstp_nmix_prpr": "917.01",
            "bstp_nmix_prdy_vrss": "11.51",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.27",
            "acml_tr_pbmn": "3299470",
            "acml_vol": "267392",
            "cntg_vol": "432"
        },
        {
            "stck_cntg_hour": "094930",
            "bstp_nmix_prpr": "917.16",
            "bstp_nmix_prdy_vrss": "11.66",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.29",
            "acml_tr_pbmn": "3294030",
            "acml_vol": "266960",
            "cntg_vol": "416"
        },
        {
            "stck_cntg_hour": "094920",
            "bstp_nmix_prpr": "917.05",
            "bstp_nmix_prdy_vrss": "11.55",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_ctrt": "1.28", |  |


### 국내업종 일자별지수

- **TR_ID**: FHPUP02120000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-index-daily-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"U"
"fid_input_iscd":"0001"
"fid_input_date_1":"20240125"
"fid_period_div_code":"D"
} |  |
| Response Example | {
    "output1": {
        "bstp_nmix_prpr": "2648.76",
        "bstp_nmix_prdy_vrss": "34.96",
        "prdy_vrss_sign": "2",
        "bstp_nmix_prdy_ctrt": "1.34",
        "acml_vol": "593842",
        "acml_tr_pbmn": "10221804",
        "bstp_nmix_oprc": "2635.63",
        "bstp_nmix_hgpr": "2648.76",
        "bstp_nmix_lwpr": "2625.01",
        "prdy_vol": "621363",
        "ascn_issu_cnt": "628",
        "down_issu_cnt": "250",
        "stnr_issu_cnt": "58",
        "uplm_issu_cnt": "0",
        "lslm_issu_cnt": "0",
        "prdy_tr_pbmn": "10691024",
        "dryy_bstp_nmix_hgpr_date": "20240102",
        "dryy_bstp_nmix_hgpr": "2675.80",
        "dryy_bstp_nmix_lwpr": "2429.12",
        "dryy_bstp_nmix_lwpr_date": "20240118"
    },
    "output2": [
        {
            "stck_bsop_date": "20240125",
            "bstp_nmix_prpr": "2470.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "0.65",
            "bstp_nmix_prdy_ctrt": "0.03",
            "bstp_nmix_oprc": "2467.73",
            "bstp_nmix_hgpr": "2474.01",
            "bstp_nmix_lwpr": "2452.36",
            "acml_vol_rlim": "166.23",
            "acml_vol": "357234",
            "acml_tr_pbmn": "8124338",
            "invt_new_psdg": "-19.94",
            "d20_dsrt": "97.44"
        },
        {
            "stck_bsop_date": "20240124",
            "bstp_nmix_prpr": "2469.69",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-8.92",
            "bstp_nmix_prdy_ctrt": "-0.36",
            "bstp_nmix_oprc": "2476.22",
            "bstp_nmix_hgpr": "2476.22",
            "bstp_nmix_lwpr": "2454.34",
            "acml_vol_rlim": "150.16",
            "acml_vol": "395464",
            "acml_tr_pbmn": "7446527",
            "invt_new_psdg": "-30.49",
            "d20_dsrt": "97.17"
        },
        {
            "stck_bsop_date": "20240123",
            "bstp_nmix_prpr": "2478.61",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "14.26",
            "bstp_nmix_prdy_ctrt": "0.58",
            "bstp_nmix_oprc": "2478.32",
            "bstp_nmix_hgpr": "2482.84",
            "bstp_nmix_lwpr": "2464.24",
            "acml_vol_rlim": "125.74",
            "acml_vol": "472284",
            "acml_tr_pbmn": "8029400",
            "invt_new_psdg": "-32.13",
            "d20_dsrt": "97.27"
        },
        {
            "stck_bsop_date": "20240122",
            "bstp_nmix_prpr": "2464.35",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-8.39",
            "bstp_nmix_prdy_ctrt": "-0.34",
            "bstp_nmix_oprc": "2489.57",
            "bstp_nmix_hgpr": "2490.69",
            "bstp_nmix_lwpr": "2464.35",
            "acml_vol_rlim": "153.03",
            "acml_vol": "388046",
            "acml_tr_pbmn": "8419916",
            "invt_new_psdg": "-48.90",
            "d20_dsrt": "96.48"
        },
        {
            "stck_bsop_date": "20240119",
            "bstp_nmix_prpr": "2472.74",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "32.70",
            "bstp_nmix_prdy_ctrt": "1.34",
            "bstp_nmix_oprc": "2468.43",
            "bstp_nmix_hgpr": "2479.00",
            "bstp_nmix_lwpr": "2455.50",
            "acml_vol_rlim": "114.46",
            "acml_vol": "518807",
            "acml_tr_pbmn": "9174537",
            "invt_new_psdg": "-49.12",
            "d20_dsrt": "96.52"
        },
        {
            "stck_bsop_date": "20240118",
            "bstp_nmix_prpr": "2440.04",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "4.14",
            "bstp_nmix_prdy_ctrt": "0.17",
            "bstp_nmix_oprc": "2439.96",
            "bstp_nmix_hgpr": "2453.97",
            "bstp_nmix_lwpr": "2429.12",
            "acml_vol_rlim": "103.91",
            "acml_vol": "571508",
            "acml_tr_pbmn": "8300178",
            "invt_new_psdg": "-76.77",
            "d20_dsrt": "95.07"
        },
        {
            "stck_bsop_date": "20240117",
            "bstp_nmix_prpr": "2435.90",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-61.69",
            "bstp_nmix_prdy_ctrt": "-2.47",
            "bstp_nmix_oprc": "2501.23",
            "bstp_nmix_hgpr": "2503.91",
            "bstp_nmix_lwpr": "2435.34",
            "acml_vol_rlim": "61.50",
            "acml_vol": "965595",
            "acml_tr_pbmn": "11281598",
            "invt_new_psdg": "-89.46",
            "d20_dsrt": "94.67"
        },
        {
            "stck_bsop_date": "20240116",
            "bstp_nmix_prpr": "2497.59",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-28.40",
            "bstp_nmix_prdy_ctrt": "-1.12",
            "bstp_nmix_oprc": "2516.27",
            "bstp_nmix_hgpr": "2524.35",
            "bstp_nmix_lwpr": "2491.13",
            "acml_vol_rlim": "90.03",
            "acml_vol": "659579",
            "acml_tr_pbmn": "8828509",
            "invt_new_psdg": "-89.46",
            "d20_dsrt": "96.83"
        },
        {
            "stck_bsop_date": "20240115",
            "bstp_nmix_prpr": "2525.99",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "0.94",
            "bstp_nmix_prdy_ctrt": "0.04",
            "bstp_nmix_oprc": "2525.69",
            "bstp_nmix_hgpr": "2536.06",
            "bstp_nmix_lwpr": "2515.84",
            "acml_vol_rlim": "74.04",
            "acml_vol": "802102",
            "acml_tr_pbmn": "8182707",
            "invt_new_psdg": "-70.35",
            "d20_dsrt": "97.84"
        },
        {
            "stck_bsop_date": "20240112",
            "bstp_nmix_prpr": "2525.05",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-15.22",
            "bstp_nmix_prdy_ctrt": "-0.60",
            "bstp_nmix_oprc": "2536.55",
            "bstp_nmix_hgpr": "2543.83",
            "bstp_nmix_lwpr": "2517.76",
            "acml_vol_rlim": "75.15",
            "acml_vol": "790177",
            "acml_tr_pbmn": "8368766",
            "invt_new_psdg": "-51.99",
            "d20_dsrt": "97.84"
        },
        {
            "stck_bsop_date": "20240111",
            "bstp_nmix_prpr": "2540.27",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-1.71",
            "bstp_nmix_prdy_ctrt": "-0.07",
            "bstp_nmix_oprc": "2543.03",
            "bstp_nmix_hgpr": "2557.30",
            "bstp_nmix_lwpr": "2540.27",
            "acml_vol_rlim": "75.32",
            "acml_vol": "788423",
            "acml_tr_pbmn": "13669890",
            "invt_new_psdg": "-35.84",
            "d20_dsrt": "98.41"
        },
        {
            "stck_bsop_date": "20240110",
            "bstp_nmix_prpr": "2541.98",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-19.26",
            "bstp_nmix_prdy_ctrt": "-0.75",
            "bstp_nmix_oprc": "2563.97",
            "bstp_nmix_hgpr": "2568.19",
            "bstp_nmix_lwpr": "2539.82",
            "acml_vol_rlim": "104.18",
            "acml_vol": "570021",
            "acml_tr_pbmn": "8795835",
            "invt_new_psdg": "-24.52",
            "d20_dsrt": "98.50"
        },
        {
            "stck_bsop_date": "20240109",
            "bstp_nmix_prpr": "2561.24",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-6.58",
            "bstp_nmix_prdy_ctrt": "-0.26",
            "bstp_nmix_oprc": "2598.31",
            "bstp_nmix_hgpr": "2599.37",
            "bstp_nmix_lwpr": "2556.00",
            "acml_vol_rlim": "75.05",
            "acml_vol": "791214",
            "acml_tr_pbmn": "8896714",
            "invt_new_psdg": "-20.81",
            "d20_dsrt": "99.29"
        },
        {
            "stck_bsop_date": "20240108",
            "bstp_nmix_prpr": "2567.82",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-10.26",
            "bstp_nmix_prdy_ctrt": "-0.40",
            "bstp_nmix_oprc": "2584.23",
            "bstp_nmix_hgpr": "2591.68",
            "bstp_nmix_lwpr": "2566.34",
            "acml_vol_rlim": "185.49",
            "acml_vol": "320144",
            "acml_tr_pbmn": "6763632",
            "invt_new_psdg": "-22.42",
            "d20_dsrt": "99.68"
        },
        {
            "stck_bsop_date": "20240105",
            "bstp_nmix_prpr": "2578.08",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-8.94",
            "bstp_nmix_prdy_ctrt": "-0.35",
            "bstp_nmix_oprc": "2586.89",
            "bstp_nmix_hgpr": "2592.29",
            "bstp_nmix_lwpr": "2572.60",
            "acml_vol_rlim": "113.70",
            "acml_vol": "522290",
            "acml_tr_pbmn": "8384473",
            "invt_new_psdg": "2.14",
            "d20_dsrt": "100.22"
        },
        {
            "stck_bsop_date": "20240104",
            "bstp_nmix_prpr": "2587.02",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-20.29",
            "bstp_nmix_prdy_ctrt": "-0.78",
            "bstp_nmix_oprc": "2592.44",
            "bstp_nmix_hgpr": "2602.64",
            "bstp_nmix_lwpr": "2580.09",
            "acml_vol_rlim": "77.10",
            "acml_vol": "770176",
            "acml_tr_pbmn": "8992274",
            "invt_new_psdg": "14.68",
            "d20_dsrt": "100.73"
        },
        {
            "stck_bsop_date": "20240103",
            "bstp_nmix_prpr": "2607.31",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-62.50",
            "bstp_nmix_prdy_ctrt": "-2.34",
            "bstp_nmix_oprc": "2643.54",
            "bstp_nmix_hgpr": "2643.72",
            "bstp_nmix_lwpr": "2607.31",
            "acml_vol_rlim": "128.22",
            "acml_vol": "463132",
            "acml_tr_pbmn": "10121578",
            "invt_new_psdg": "31.03",
            "d20_dsrt": "101.67"
        },
        {
            "stck_bsop_date": "20240102",
            "bstp_nmix_prpr": "2669.81",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "14.53",
            "bstp_nmix_prdy_ctrt": "0.55",
            "bstp_nmix_oprc": "2645.47",
            "bstp_nmix_hgpr": "2675.80",
            "bstp_nmix_lwpr": "2641.88",
            "acml_vol_rlim": "144.88",
            "acml_vol": "409872",
            "acml_tr_pbmn": "9628190",
            "invt_new_psdg": "70.47",
            "d20_dsrt": "104.31"
        },
        {
            "stck_bsop_date": "20231228",
            "bstp_nmix_prpr": "2655.28",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "41.78",
            "bstp_nmix_prdy_ctrt": "1.60",
            "bstp_nmix_oprc": "2616.27",
            "bstp_nmix_hgpr": "2655.28",
            "bstp_nmix_lwpr": "2611.72",
            "acml_vol_rlim": "129.07",
            "acml_vol": "460087",
            "acml_tr_pbmn": "9418930",
            "invt_new_psdg": "71.51",
            "d20_dsrt": "104.02"
        },
        {
            "stck_bsop_date": "20231227",
            "bstp_nmix_prpr": "2613.50",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "10.91",
            "bstp_nmix_prdy_ctrt": "0.42",
            "bstp_nmix_oprc": "2599.35",
            "bstp_nmix_hgpr": "2613.50",
            "bstp_nmix_lwpr": "2590.08",
            "acml_vol_rlim": "169.80",
            "acml_vol": "349733",
            "acml_tr_pbmn": "10359764",
            "invt_new_psdg": "44.91",
            "d20_dsrt": "102.65"
        },
        {
            "stck_bsop_date": "20231226",
            "bstp_nmix_prpr": "2602.59",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "3.08",
            "bstp_nmix_prdy_ctrt": "0.12",
            "bstp_nmix_oprc": "2609.44",
            "bstp_nmix_hgpr": "2612.14",
            "bstp_nmix_lwpr": "2594.65",
            "acml_vol_rlim": "134.83",
            "acml_vol": "440428",
            "acml_tr_pbmn": "9582766",
            "invt_new_psdg": "44.75",
            "d20_dsrt": "102.41"
        },
        {
            "stck_bsop_date": "20231222",
            "bstp_nmix_prpr": "2599.51",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-0.51",
            "bstp_nmix_prdy_ctrt": "-0.02",
            "bstp_nmix_oprc": "2617.72",
            "bstp_nmix_hgpr": "2621.37",
            "bstp_nmix_lwpr": "2599.51",
            "acml_vol_rlim": "127.44",
            "acml_vol": "465967",
            "acml_tr_pbmn": "8848288",
            "invt_new_psdg": "45.45",
            "d20_dsrt": "102.50"
        },
        {
            "stck_bsop_date": "20231221",
            "bstp_nmix_prpr": "2600.02",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-14.28",
            "bstp_nmix_prdy_ctrt": "-0.55",
            "bstp_nmix_oprc": "2598.37",
            "bstp_nmix_hgpr": "2610.81",
            "bstp_nmix_lwpr": "2587.16",
            "acml_vol_rlim": "102.68",
            "acml_vol": "578335",
            "acml_tr_pbmn": "9467809",
            "invt_new_psdg": "59.06",
            "d20_dsrt": "102.73"
        },
        {
            "stck_bsop_date": "20231220",
            "bstp_nmix_prpr": "2614.30",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "45.75",
            "bstp_nmix_prdy_ctrt": "1.78",
            "bstp_nmix_oprc": "2586.99",
            "bstp_nmix_hgpr": "2615.38",
            "bstp_nmix_lwpr": "2584.85",
            "acml_vol_rlim": "104.11",
            "acml_vol": "570423",
            "acml_tr_pbmn": "11202543",
            "invt_new_psdg": "64.02",
            "d20_dsrt": "103.47"
        },
        {
            "stck_bsop_date": "20231219",
            "bstp_nmix_prpr": "2568.55",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "1.69",
            "bstp_nmix_prdy_ctrt": "0.07",
            "bstp_nmix_oprc": "2564.81",
            "bstp_nmix_hgpr": "2570.06",
            "bstp_nmix_lwpr": "2556.52",
            "acml_vol_rlim": "151.30",
            "acml_vol": "392497",
            "acml_tr_pbmn": "8418111",
            "invt_new_psdg": "58.54",
            "d20_dsrt": "101.87"
        },
        {
            "stck_bsop_date": "20231218",
            "bstp_nmix_prpr": "2566.86",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "3.30",
            "bstp_nmix_prdy_ctrt": "0.13",
            "bstp_nmix_oprc": "2568.77",
            "bstp_nmix_hgpr": "2573.13",
            "bstp_nmix_lwpr": "2556.05",
            "acml_vol_rlim": "154.31",
            "acml_vol": "384828",
            "acml_tr_pbmn": "10181568",
            "invt_new_psdg": "37.41",
            "d20_dsrt": "101.92"
        },
        {
            "stck_bsop_date": "20231215",
            "bstp_nmix_prpr": "2563.56",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "19.38",
            "bstp_nmix_prdy_ctrt": "0.76",
            "bstp_nmix_oprc": "2558.44",
            "bstp_nmix_hgpr": "2574.23",
            "bstp_nmix_lwpr": "2555.30",
            "acml_vol_rlim": "127.62",
            "acml_vol": "465314",
            "acml_tr_pbmn": "12873295",
            "invt_new_psdg": "38.80",
            "d20_dsrt": "101.94"
        },
        {
            "stck_bsop_date": "20231214",
            "bstp_nmix_prpr": "2544.18",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "33.52",
            "bstp_nmix_prdy_ctrt": "1.34",
            "bstp_nmix_oprc": "2547.74",
            "bstp_nmix_hgpr": "2549.65",
            "bstp_nmix_lwpr": "2532.16",
            "acml_vol_rlim": "112.02",
            "acml_vol": "530124",
            "acml_tr_pbmn": "12960671",
            "invt_new_psdg": "12.67",
            "d20_dsrt": "101.36"
        },
        {
            "stck_bsop_date": "20231213",
            "bstp_nmix_prpr": "2510.66",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-24.61",
            "bstp_nmix_prdy_ctrt": "-0.97",
            "bstp_nmix_oprc": "2531.23",
            "bstp_nmix_hgpr": "2531.23",
            "bstp_nmix_lwpr": "2509.89",
            "acml_vol_rlim": "157.13",
            "acml_vol": "377934",
            "acml_tr_pbmn": "7513617",
            "invt_new_psdg": "6.92",
            "d20_dsrt": "100.13"
        },
        {
            "stck_bsop_date": "20231212",
            "bstp_nmix_prpr": "2535.27",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "9.91",
            "bstp_nmix_prdy_ctrt": "0.39",
            "bstp_nmix_oprc": "2535.11",
            "bstp_nmix_hgpr": "2543.06",
            "bstp_nmix_lwpr": "2529.74",
            "acml_vol_rlim": "157.09",
            "acml_vol": "378034",
            "acml_tr_pbmn": "7732530",
            "invt_new_psdg": "15.36",
            "d20_dsrt": "101.16"
        },
        {
            "stck_bsop_date": "20231211",
            "bstp_nmix_prpr": "2525.36",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "7.51",
            "bstp_nmix_prdy_ctrt": "0.30",
            "bstp_nmix_oprc": "2524.79",
            "bstp_nmix_hgpr": "2528.89",
            "bstp_nmix_lwpr": "2512.45",
            "acml_vol_rlim": "136.51",
            "acml_vol": "435004",
            "acml_tr_pbmn": "8260508",
            "invt_new_psdg": "20.45",
            "d20_dsrt": "100.97"
        },
        {
            "stck_bsop_date": "20231208",
            "bstp_nmix_prpr": "2517.85",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "25.78",
            "bstp_nmix_prdy_ctrt": "1.03",
            "bstp_nmix_oprc": "2510.24",
            "bstp_nmix_hgpr": "2521.58",
            "bstp_nmix_lwpr": "2507.14",
            "acml_vol_rlim": "137.53",
            "acml_vol": "431797",
            "acml_tr_pbmn": "7916793",
            "invt_new_psdg": "7.83",
            "d20_dsrt": "100.92"
        },
        {
            "stck_bsop_date": "20231207",
            "bstp_nmix_prpr": "2492.07",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-3.31",
            "bstp_nmix_prdy_ctrt": "-0.13",
            "bstp_nmix_oprc": "2493.14",
            "bstp_nmix_hgpr": "2499.73",
            "bstp_nmix_lwpr": "2481.00",
            "acml_vol_rlim": "132.89",
            "acml_vol": "446877",
            "acml_tr_pbmn": "8127636",
            "invt_new_psdg": "-18.93",
            "d20_dsrt": "100.10"
        },
        {
            "stck_bsop_date": "20231206",
            "bstp_nmix_prpr": "2495.38",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "1.10",
            "bstp_nmix_prdy_ctrt": "0.04",
            "bstp_nmix_oprc": "2503.57",
            "bstp_nmix_hgpr": "2509.67",
            "bstp_nmix_lwpr": "2495.38",
            "acml_vol_rlim": "151.88",
            "acml_vol": "390989",
            "acml_tr_pbmn": "7685320",
            "invt_new_psdg": "-6.37",
            "d20_dsrt": "100.37"
        },
        {
            "stck_bsop_date": "20231205",
            "bstp_nmix_prpr": "2494.28",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-20.67",
            "bstp_nmix_prdy_ctrt": "-0.82",
            "bstp_nmix_oprc": "2507.45",
            "bstp_nmix_hgpr": "2509.74",
            "bstp_nmix_lwpr": "2492.55",
            "acml_vol_rlim": "139.05",
            "acml_vol": "427067",
            "acml_tr_pbmn": "8300522",
            "invt_new_psdg": "-6.29",
            "d20_dsrt": "100.47"
        },
        {
            "stck_bsop_date": "20231204",
            "bstp_nmix_prpr": "2514.95",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "9.94",
            "bstp_nmix_prdy_ctrt": "0.40",
            "bstp_nmix_oprc": "2522.22",
            "bstp_nmix_hgpr": "2525.63",
            "bstp_nmix_lwpr": "2510.52",
            "acml_vol_rlim": "119.04",
            "acml_vol": "498861",
            "acml_tr_pbmn": "8772367",
            "invt_new_psdg": "19.36",
            "d20_dsrt": "101.41"
        },
        {
            "stck_bsop_date": "20231201",
            "bstp_nmix_prpr": "2505.01",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-30.28",
            "bstp_nmix_prdy_ctrt": "-1.19",
            "bstp_nmix_oprc": "2520.49",
            "bstp_nmix_hgpr": "2520.49",
            "bstp_nmix_lwpr": "2504.06",
            "acml_vol_rlim": "114.95",
            "acml_vol": "516596",
            "acml_tr_pbmn": "8837750",
            "invt_new_psdg": "22.72",
            "d20_dsrt": "101.03"
        },
        {
            "stck_bsop_date": "20231130",
            "bstp_nmix_prpr": "2535.29",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "15.48",
            "bstp_nmix_prdy_ctrt": "0.61",
            "bstp_nmix_oprc": "2512.11",
            "bstp_nmix_hgpr": "2535.29",
            "bstp_nmix_lwpr": "2507.80",
            "acml_vol_rlim": "89.40",
            "acml_vol": "664284",
            "acml_tr_pbmn": "11992488",
            "invt_new_psdg": "28.65",
            "d20_dsrt": "102.54"
        },
        {
            "stck_bsop_date": "20231129",
            "bstp_nmix_prpr": "2519.81",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-1.95",
            "bstp_nmix_prdy_ctrt": "-0.08",
            "bstp_nmix_oprc": "2518.80",
            "bstp_nmix_hgpr": "2523.98",
            "bstp_nmix_lwpr": "2501.44",
            "acml_vol_rlim": "102.52",
            "acml_vol": "579271",
            "acml_tr_pbmn": "9428200",
            "invt_new_psdg": "24.76",
            "d20_dsrt": "102.31"
        },
        {
            "stck_bsop_date": "20231128",
            "bstp_nmix_prpr": "2521.76",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "26.10",
            "bstp_nmix_prdy_ctrt": "1.05",
            "bstp_nmix_oprc": "2506.14",
            "bstp_nmix_hgpr": "2522.45",
            "bstp_nmix_lwpr": "2502.26",
            "acml_vol_rlim": "134.02",
            "acml_vol": "443090",
            "acml_tr_pbmn": "8753424",
            "invt_new_psdg": "47.02",
            "d20_dsrt": "102.84"
        },
        {
            "stck_bsop_date": "20231127",
            "bstp_nmix_prpr": "2495.66",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-0.97",
            "bstp_nmix_prdy_ctrt": "-0.04",
            "bstp_nmix_oprc": "2501.83",
            "bstp_nmix_hgpr": "2511.37",
            "bstp_nmix_lwpr": "2489.18",
            "acml_vol_rlim": "162.81",
            "acml_vol": "364744",
            "acml_tr_pbmn": "8376476",
            "invt_new_psdg": "47.49",
            "d20_dsrt": "102.29"
        },
        {
            "stck_bsop_date": "20231124",
            "bstp_nmix_prpr": "2496.63",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-18.33",
            "bstp_nmix_prdy_ctrt": "-0.73",
            "bstp_nmix_oprc": "2517.88",
            "bstp_nmix_hgpr": "2521.56",
            "bstp_nmix_lwpr": "2496.63",
            "acml_vol_rlim": "165.24",
            "acml_vol": "359383",
            "acml_tr_pbmn": "6537961",
            "invt_new_psdg": "45.27",
            "d20_dsrt": "102.71"
        },
        {
            "stck_bsop_date": "20231123",
            "bstp_nmix_prpr": "2514.96",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "3.26",
            "bstp_nmix_prdy_ctrt": "0.13",
            "bstp_nmix_oprc": "2515.83",
            "bstp_nmix_hgpr": "2522.20",
            "bstp_nmix_lwpr": "2507.30",
            "acml_vol_rlim": "164.56",
            "acml_vol": "360874",
            "acml_tr_pbmn": "6577868",
            "invt_new_psdg": "45.67",
            "d20_dsrt": "103.88"
        },
        {
            "stck_bsop_date": "20231122",
            "bstp_nmix_prpr": "2511.70",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "1.28",
            "bstp_nmix_prdy_ctrt": "0.05",
            "bstp_nmix_oprc": "2493.17",
            "bstp_nmix_hgpr": "2516.72",
            "bstp_nmix_lwpr": "2490.43",
            "acml_vol_rlim": "135.12",
            "acml_vol": "439486",
            "acml_tr_pbmn": "7755316",
            "invt_new_psdg": "45.98",
            "d20_dsrt": "104.21"
        },
        {
            "stck_bsop_date": "20231121",
            "bstp_nmix_prpr": "2510.42",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "19.22",
            "bstp_nmix_prdy_ctrt": "0.77",
            "bstp_nmix_oprc": "2504.70",
            "bstp_nmix_hgpr": "2517.74",
            "bstp_nmix_lwpr": "2500.91",
            "acml_vol_rlim": "172.10",
            "acml_vol": "345055",
            "acml_tr_pbmn": "7713377",
            "invt_new_psdg": "27.09",
            "d20_dsrt": "104.48"
        },
        {
            "stck_bsop_date": "20231120",
            "bstp_nmix_prpr": "2491.20",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "21.35",
            "bstp_nmix_prdy_ctrt": "0.86",
            "bstp_nmix_oprc": "2464.72",
            "bstp_nmix_hgpr": "2499.75",
            "bstp_nmix_lwpr": "2464.04",
            "acml_vol_rlim": "183.39",
            "acml_vol": "323806",
            "acml_tr_pbmn": "6586445",
            "invt_new_psdg": "-2.39",
            "d20_dsrt": "103.96"
        },
        {
            "stck_bsop_date": "20231117",
            "bstp_nmix_prpr": "2469.85",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-18.33",
            "bstp_nmix_prdy_ctrt": "-0.74",
            "bstp_nmix_oprc": "2477.43",
            "bstp_nmix_hgpr": "2481.10",
            "bstp_nmix_lwpr": "2463.59",
            "acml_vol_rlim": "152.67",
            "acml_vol": "388974",
            "acml_tr_pbmn": "8129523",
            "invt_new_psdg": "14.66",
            "d20_dsrt": "103.35"
        },
        {
            "stck_bsop_date": "20231116",
            "bstp_nmix_prpr": "2488.18",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "1.51",
            "bstp_nmix_prdy_ctrt": "0.06",
            "bstp_nmix_oprc": "2483.48",
            "bstp_nmix_hgpr": "2491.98",
            "bstp_nmix_lwpr": "2472.69",
            "acml_vol_rlim": "145.75",
            "acml_vol": "407441",
            "acml_tr_pbmn": "6806414",
            "invt_new_psdg": "30.54",
            "d20_dsrt": "104.33"
        },
        {
            "stck_bsop_date": "20231115",
            "bstp_nmix_prpr": "2486.67",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "53.42",
            "bstp_nmix_prdy_ctrt": "2.20",
            "bstp_nmix_oprc": "2482.21",
            "bstp_nmix_hgpr": "2487.42",
            "bstp_nmix_lwpr": "2468.43",
            "acml_vol_rlim": "141.44",
            "acml_vol": "419843",
            "acml_tr_pbmn": "9328219",
            "invt_new_psdg": "33.54",
            "d20_dsrt": "104.42"
        },
        {
            "stck_bsop_date": "20231114",
            "bstp_nmix_prpr": "2433.25",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "29.49",
            "bstp_nmix_prdy_ctrt": "1.23",
            "bstp_nmix_oprc": "2424.93",
            "bstp_nmix_hgpr": "2442.37",
            "bstp_nmix_lwpr": "2422.97",
            "acml_vol_rlim": "193.46",
            "acml_vol": "306964",
            "acml_tr_pbmn": "6382101",
            "invt_new_psdg": "31.36",
            "d20_dsrt": "102.23"
        },
        {
            "stck_bsop_date": "20231113",
            "bstp_nmix_prpr": "2403.76",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-5.90",
            "bstp_nmix_prdy_ctrt": "-0.24",
            "bstp_nmix_oprc": "2431.24",
            "bstp_nmix_hgpr": "2435.32",
            "bstp_nmix_lwpr": "2399.04",
            "acml_vol_rlim": "193.36",
            "acml_vol": "307123",
            "acml_tr_pbmn": "5934173",
            "invt_new_psdg": "12.72",
            "d20_dsrt": "100.94"
        },
        {
            "stck_bsop_date": "20231110",
            "bstp_nmix_prpr": "2409.66",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-17.42",
            "bstp_nmix_prdy_ctrt": "-0.72",
            "bstp_nmix_oprc": "2406.40",
            "bstp_nmix_hgpr": "2413.62",
            "bstp_nmix_lwpr": "2393.64",
            "acml_vol_rlim": "190.05",
            "acml_vol": "312468",
            "acml_tr_pbmn": "5825602",
            "invt_new_psdg": "24.51",
            "d20_dsrt": "101.12"
        },
        {
            "stck_bsop_date": "20231109",
            "bstp_nmix_prpr": "2427.08",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "5.46",
            "bstp_nmix_prdy_ctrt": "0.23",
            "bstp_nmix_oprc": "2425.93",
            "bstp_nmix_hgpr": "2437.90",
            "bstp_nmix_lwpr": "2413.04",
            "acml_vol_rlim": "150.33",
            "acml_vol": "395031",
            "acml_tr_pbmn": "7288448",
            "invt_new_psdg": "38.05",
            "d20_dsrt": "101.75"
        },
        {
            "stck_bsop_date": "20231108",
            "bstp_nmix_prpr": "2421.62",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-22.34",
            "bstp_nmix_prdy_ctrt": "-0.91",
            "bstp_nmix_oprc": "2460.22",
            "bstp_nmix_hgpr": "2468.43",
            "bstp_nmix_lwpr": "2418.14",
            "acml_vol_rlim": "127.10",
            "acml_vol": "467218",
            "acml_tr_pbmn": "7667332",
            "invt_new_psdg": "17.07",
            "d20_dsrt": "101.41"
        },
        {
            "stck_bsop_date": "20231107",
            "bstp_nmix_prpr": "2443.96",
            "prdy_vrss_sign": "5",
            "bstp_nmix_prdy_vrss": "-58.41",
            "bstp_nmix_prdy_ctrt": "-2.33",
            "bstp_nmix_oprc": "2476.35",
            "bstp_nmix_hgpr": "2476.35",
            "bstp_nmix_lwpr": "2418.74",
            "acml_vol_rlim": "129.75",
            "acml_vol": "457676",
            "acml_tr_pbmn": "12086570",
            "invt_new_psdg": "17.35",
            "d20_dsrt": "102.28"
        },
        {
            "stck_bsop_date": "20231106",
            "bstp_nmix_prpr": "2502.37",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "134.03",
            "bstp_nmix_prdy_ctrt": "5.66",
            "bstp_nmix_oprc": "2399.80",
            "bstp_nmix_hgpr": "2502.37",
            "bstp_nmix_lwpr": "2395.03",
            "acml_vol_rlim": "112.35",
            "acml_vol": "528585",
            "acml_tr_pbmn": "15225480",
            "invt_new_psdg": "39.16",
            "d20_dsrt": "104.82"
        },
        {
            "stck_bsop_date": "20231103",
            "bstp_nmix_prpr": "2368.34",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "25.22",
            "bstp_nmix_prdy_ctrt": "1.08",
            "bstp_nmix_oprc": "2365.59",
            "bstp_nmix_hgpr": "2370.28",
            "bstp_nmix_lwpr": "2351.83",
            "acml_vol_rlim": "102.62",
            "acml_vol": "578662",
            "acml_tr_pbmn": "8040958",
            "invt_new_psdg": "8.74",
            "d20_dsrt": "99.40"
        },
        {
            "stck_bsop_date": "20231102",
            "bstp_nmix_prpr": "2343.12",
            "prdy_vrss_sign": "2",
            "bstp_nmix_prdy_vrss": "41.56",
            "bstp_nmix_prdy_ctrt": "1.81",
            "bstp_nmix_oprc": "2334.96",
            "bstp_nmix_hgpr": "2351.91",
            "bstp_nmix_lwpr": "2333.41",
            "acml_vol_rlim": "157.33",
            "acml_vol": "377462",
            "acml_tr_pbmn": "7679305",
            "invt_new_psdg": "-13.03", |  |


### 금리 종합(국내채권/금리)

- **TR_ID**: FHPST07020000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/comp-interest`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 변동성완화장치(VI) 현황

- **TR_ID**: FHPST01390000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-vi-status`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"fid_cond_scr_div_code":"20139",
	"fid_mrkt_cls_code":"0",
	"fid_input_iscd":"",
	"fid_rank_sort_cls_code":"0",
	"fid_input_date_1":"20240126",
	"fid_trgt_cls_code":"",
	"fid_trgt_exls_cls_code":"",
	"fid_div_cls_code":"0"
} |  |
| Response Example | {
    "output": [
        {
            "hts_kor_isnm": "KODEX Fn멀티팩터",
            "mksc_shrn_iscd": "337120",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "174012",
            "vi_cncl_hour": "174212",
            "vi_kind_code": "2",
            "vi_prc": "12135",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "13275",
            "vi_dmc_dprt": "-8.59",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "루멘스",
            "mksc_shrn_iscd": "038060",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "174008",
            "vi_cncl_hour": "174210",
            "vi_kind_code": "2",
            "vi_prc": "1337",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "1241",
            "vi_dmc_dprt": "7.74",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "DL건설",
            "mksc_shrn_iscd": "001880",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "173030",
            "vi_cncl_hour": "173234",
            "vi_kind_code": "2",
            "vi_prc": "14000",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "14990",
            "vi_dmc_dprt": "-6.60",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "성창기업지주",
            "mksc_shrn_iscd": "000180",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "173030",
            "vi_cncl_hour": "173224",
            "vi_kind_code": "2",
            "vi_prc": "1860",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "1992",
            "vi_dmc_dprt": "-6.63",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "성창기업지주",
            "mksc_shrn_iscd": "000180",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "172030",
            "vi_cncl_hour": "172204",
            "vi_kind_code": "2",
            "vi_prc": "1992",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "1857",
            "vi_dmc_dprt": "7.27",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "유아이디",
            "mksc_shrn_iscd": "069330",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "172030",
            "vi_cncl_hour": "172234",
            "vi_kind_code": "2",
            "vi_prc": "1640",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "1490",
            "vi_dmc_dprt": "10.07",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "뷰웍스",
            "mksc_shrn_iscd": "100120",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "172010",
            "vi_cncl_hour": "172208",
            "vi_kind_code": "2",
            "vi_prc": "27700",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "29700",
            "vi_dmc_dprt": "-6.73",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "TIGER 미국배당+3%프리미엄다우존스",
            "mksc_shrn_iscd": "458750",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "171030",
            "vi_cncl_hour": "171212",
            "vi_kind_code": "2",
            "vi_prc": "11700",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "10675",
            "vi_dmc_dprt": "9.60",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "아스타",
            "mksc_shrn_iscd": "246720",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "171030",
            "vi_cncl_hour": "171253",
            "vi_kind_code": "2",
            "vi_prc": "5100",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "5490",
            "vi_dmc_dprt": "-7.10",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "제일전기공업",
            "mksc_shrn_iscd": "199820",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "170030",
            "vi_cncl_hour": "170232",
            "vi_kind_code": "2",
            "vi_prc": "10050",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "9350",
            "vi_dmc_dprt": "7.49",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "파인디지털",
            "mksc_shrn_iscd": "038950",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "170030",
            "vi_cncl_hour": "170244",
            "vi_kind_code": "2",
            "vi_prc": "5200",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "4800",
            "vi_dmc_dprt": "8.33",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "엔시트론",
            "mksc_shrn_iscd": "101400",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "170013",
            "vi_cncl_hour": "170218",
            "vi_kind_code": "2",
            "vi_prc": "644",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "604",
            "vi_dmc_dprt": "6.62",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "TIGER 2차전지TOP10",
            "mksc_shrn_iscd": "364980",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "165030",
            "vi_cncl_hour": "165250",
            "vi_kind_code": "2",
            "vi_prc": "12450",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "13740",
            "vi_dmc_dprt": "-9.39",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "지니너스",
            "mksc_shrn_iscd": "389030",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "165030",
            "vi_cncl_hour": "165222",
            "vi_kind_code": "2",
            "vi_prc": "2270",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "2125",
            "vi_dmc_dprt": "6.82",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "패션플랫폼",
            "mksc_shrn_iscd": "225590",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "165030",
            "vi_cncl_hour": "165228",
            "vi_kind_code": "2",
            "vi_prc": "1263",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "1153",
            "vi_dmc_dprt": "9.54",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "씨엔플러스",
            "mksc_shrn_iscd": "115530",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "165030",
            "vi_cncl_hour": "165240",
            "vi_kind_code": "2",
            "vi_prc": "344",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "368",
            "vi_dmc_dprt": "-6.52",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "케이비제22호스팩",
            "mksc_shrn_iscd": "436530",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "164030",
            "vi_cncl_hour": "164208",
            "vi_kind_code": "2",
            "vi_prc": "4455",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "4795",
            "vi_dmc_dprt": "-7.09",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "제너셈",
            "mksc_shrn_iscd": "217190",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "164030",
            "vi_cncl_hour": "164230",
            "vi_kind_code": "2",
            "vi_prc": "14980",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "15990",
            "vi_dmc_dprt": "-6.32",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "아스타",
            "mksc_shrn_iscd": "246720",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "163030",
            "vi_cncl_hour": "163220",
            "vi_kind_code": "2",
            "vi_prc": "5550",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "5090",
            "vi_dmc_dprt": "9.04",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "세니젠",
            "mksc_shrn_iscd": "188260",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "163030",
            "vi_cncl_hour": "163252",
            "vi_kind_code": "2",
            "vi_prc": "3955",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "4230",
            "vi_dmc_dprt": "-6.50",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "KODEX Fn멀티팩터",
            "mksc_shrn_iscd": "337120",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "163024",
            "vi_cncl_hour": "163250",
            "vi_kind_code": "2",
            "vi_prc": "13280",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "12075",
            "vi_dmc_dprt": "9.98",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "ES큐브",
            "mksc_shrn_iscd": "050120",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "163017",
            "vi_cncl_hour": "163228",
            "vi_kind_code": "2",
            "vi_prc": "3055",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "2860",
            "vi_dmc_dprt": "6.82",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "무학",
            "mksc_shrn_iscd": "033920",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162241",
            "vi_kind_code": "2",
            "vi_prc": "5220",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "4880",
            "vi_dmc_dprt": "6.97",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "아이씨에이치",
            "mksc_shrn_iscd": "368600",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162210",
            "vi_kind_code": "2",
            "vi_prc": "5860",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "5460",
            "vi_dmc_dprt": "7.33",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "KBSTAR 2차전지TOP10",
            "mksc_shrn_iscd": "465330",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162217",
            "vi_kind_code": "2",
            "vi_prc": "14475",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "13485",
            "vi_dmc_dprt": "7.34",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "제너셈",
            "mksc_shrn_iscd": "217190",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162232",
            "vi_kind_code": "2",
            "vi_prc": "15990",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "14910",
            "vi_dmc_dprt": "7.24",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "알엔투테크놀로지",
            "mksc_shrn_iscd": "148250",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162212",
            "vi_kind_code": "2",
            "vi_prc": "5390",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "4915",
            "vi_dmc_dprt": "9.66",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "엑서지21",
            "mksc_shrn_iscd": "043090",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162030",
            "vi_cncl_hour": "162206",
            "vi_kind_code": "2",
            "vi_prc": "463",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "507",
            "vi_dmc_dprt": "-8.68",
            "vi_count": "2"
        },
        {
            "hts_kor_isnm": "DL건설",
            "mksc_shrn_iscd": "001880",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162028",
            "vi_cncl_hour": "162214",
            "vi_kind_code": "2",
            "vi_prc": "15010",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "14000",
            "vi_dmc_dprt": "7.21",
            "vi_count": "1"
        },
        {
            "hts_kor_isnm": "뷰웍스",
            "mksc_shrn_iscd": "100120",
            "vi_cls_code": "N",
            "bsop_date": "20240126",
            "cntg_vi_hour": "162015",
            "vi_cncl_hour": "162207",
            "vi_kind_code": "2",
            "vi_prc": "27600",
            "vi_stnd_prc": "0",
            "vi_dprt": "0.00",
            "vi_dmc_stnd_prc": "29700",
            "vi_dmc_dprt": "-7.07",
            "vi_count": "1"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 종합 시황/공시(제목)

- **TR_ID**: FHKST01011800
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/news-title`

> ⚠ 원본 엑셀에 상세 명세 시트 없음
