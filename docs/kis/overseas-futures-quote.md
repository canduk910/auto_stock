# [해외선물옵션] 기본시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (20개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 297 | REST | 해외선물종목현재가 | HHDFC55010000 | GET | `/uapi/overseas-futureoption/v1/quotations/inquire-price` |  |
| 298 | REST | 해외선물종목상세 | HHDFC55010100 | GET | `/uapi/overseas-futureoption/v1/quotations/stock-detail` |  |
| 299 | REST | 해외선물 호가 | HHDFC86000000 | GET | `/uapi/overseas-futureoption/v1/quotations/inquire-asking-price` |  |
| 300 | REST | 해외선물 분봉조회 | HHDFC55020400 | GET | `/uapi/overseas-futureoption/v1/quotations/inquire-time-futurechartprice` |  |
| 301 | REST | 해외선물 체결추이(틱) | HHDFC55020200 | GET | `/uapi/overseas-futureoption/v1/quotations/tick-ccnl` |  |
| 302 | REST | 해외선물 체결추이(주간) | HHDFC55020000 | GET | `/uapi/overseas-futureoption/v1/quotations/weekly-ccnl` |  |
| 303 | REST | 해외선물 체결추이(일간) | HHDFC55020100 | GET | `/uapi/overseas-futureoption/v1/quotations/daily-ccnl` |  |
| 304 | REST | 해외선물 체결추이(월간) | HHDFC55020300 | GET | `/uapi/overseas-futureoption/v1/quotations/monthly-ccnl` |  |
| 305 | REST | 해외선물 상품기본정보 | HHDFC55200000 | GET | `/uapi/overseas-futureoption/v1/quotations/search-contract-detail` |  |
| 306 | REST | 해외선물 미결제추이 | HHDDB95030000 | GET | `/uapi/overseas-futureoption/v1/quotations/investor-unpd-trend` |  |
| 307 | REST | 해외옵션종목현재가 | HHDFO55010000 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-price` |  |
| 308 | REST | 해외옵션종목상세 | HHDFO55010100 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-detail` |  |
| 309 | REST | 해외옵션 호가 | HHDFO86000000 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-asking-price` |  |
| 310 | REST | 해외옵션 분봉조회 | HHDFO55020400 | GET | `/uapi/overseas-futureoption/v1/quotations/inquire-time-optchartprice` |  |
| 311 | REST | 해외옵션 체결추이(틱) | HHDFO55020200 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-tick-ccnl` |  |
| 312 | REST | 해외옵션 체결추이(일간) | HHDFO55020100 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-daily-ccnl` |  |
| 313 | REST | 해외옵션 체결추이(주간) | HHDFO55020000 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-weekly-ccnl` |  |
| 314 | REST | 해외옵션 체결추이(월간) | HHDFO55020300 | GET | `/uapi/overseas-futureoption/v1/quotations/opt-monthly-ccnl` |  |
| 315 | REST | 해외옵션 상품기본정보 | HHDFO55200000 | GET | `/uapi/overseas-futureoption/v1/quotations/search-opt-detail` |  |
| 316 | REST | 해외선물옵션 장운영시간 | OTFM2229R | GET | `/uapi/overseas-futureoption/v1/quotations/market-time` |  |

---

## 상세 명세

### 해외선물종목현재가

- **TR_ID**: HHDFC55010000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:BRNF25 |  |
| Response Example | {
    "output1": {
        "proc_date": "20241108",
        "proc_time": "173937",
        "open_price": "          75.55",
        "high_price": "          75.61",
        "low_price": "          74.66",
        "last_price": "          74.90",
        "vol": "33004",
        "prev_diff_flag": "5",
        "prev_diff_price": "           0.67",
        "prev_diff_rate": "     -0.89",
        "bid_qntt": "         7",
        "bid_price": "          74.89",
        "ask_qntt": "         4",
        "ask_price": "          74.90",
        "prev_price": "          75.57",
        "trst_mgn": "               3670",
        "exch_cd": "ICE",
        "crc_cd": "USD",
        "trd_fr_date": "20180110",
        "expr_date": "20241129",
        "trd_to_date": "20241129",
        "remn_cnt": "  22",
        "last_qntt": "1",
        "tot_ask_qntt": "       115",
        "tot_bid_qntt": "       157",
        "tick_size": "               0.01",
        "open_date": "20241108",
        "open_time": "100000",
        "close_date": "20241109",
        "close_time": "080000",
        "sbsnsdate": "20241108",
        "sttl_price": "  75.6300000000"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물종목상세

- **TR_ID**: HHDFC55010100
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/stock-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
     "SRS_CD": "6AU22"
 } |  |
| Response Example | {
    "output1": {
        "exch_cd": "CME",
        "clas_cd": "001",
        "crc_cd": "USD",
        "prev_price": "         6722.0",
        "sttl_date": "20220919",
        "trst_mgn": "               2200",
        "disp_digit": "        10",
        "tick_sz": "            0.00005",
        "tick_val": "                  5",
        "mrkt_open_date": "20220919",
        "mrkt_open_time": "070000",
        "mrkt_close_date": "20220920",
        "mrkt_close_time": "060000",
        "trd_fr_date": "20170906",
        "expr_date": "20220919",
        "trd_to_date": "20220919",
        "remn_cnt": "   0",
        "stat_tp": "2",
        "ctrt_size": "             100000",
        "stl_tp": "실물인수도",
        "frst_noti_date": "20220919",
        "sprd_srs_cd1": "",
        "sprd_srs_cd2": ""
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 호가

- **TR_ID**: HHDFC86000000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-asking-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:6AM24 |  |
| Response Example | {
    "output1": {
        "open_price": "         6430.0",
        "high_price": "         6466.5",
        "lowp_rice": "         6425.0",
        "last_price": "         6443.5",
        "prev_price": "         6428.5",
        "vol": "27383",
        "prev_diff_price": "             15",
        "prev_diff_rate": "      0.23",
        "quot_date": "20240422",
        "quot_time": "160201"
    },
    "output2": [
        {
            "bid_qntt": "        35",
            "bid_num": "        11",
            "bid_price": "         6443.0",
            "ask_qntt": "        11",
            "ask_num": "         7",
            "ask_price": "         6443.5"
        },
        {
            "bid_qntt": "       108",
            "bid_num": "        25",
            "bid_price": "         6442.5",
            "ask_qntt": "       137",
            "ask_num": "        23",
            "ask_price": "         6444.0"
        },
        {
            "bid_qntt": "       145",
            "bid_num": "        28",
            "bid_price": "         6442.0",
            "ask_qntt": "       120",
            "ask_num": "        24",
            "ask_price": "         6444.5"
        },
        {
            "bid_qntt": "       139",
            "bid_num": "        29",
            "bid_price": "         6441.5",
            "ask_qntt": "       142",
            "ask_num": "        21",
            "ask_price": "         6445.0"
        },
        {
            "bid_qntt": "       128",
            "bid_num": "        25",
            "bid_price": "         6441.0",
            "ask_qntt": "       127",
            "ask_num": "        20",
            "ask_price": "         6445.5"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 분봉조회

- **TR_ID**: HHDFC55020400
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-time-futurechartprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:BRNQ24
EXCH_CD:ICE
START_DATE_TIME:
CLOSE_DATE_TIME:20231212
QRY_TP:P
QRY_CNT:500
QRY_GAP:1
INDEX_KEY:20231211       128 |  |
| Response Example | {
    "output2": {
        "ret_cnt": "0500",
        "last_n_cnt": "",
        "index_key": "20231208       246"
    },
    "output1": [
        {
            "data_date": "20231208",
            "data_time": "202100",
            "open_price": "75.41",
            "high_price": "75.41",
            "low_price": "75.41",
            "last_price": "75.41",
            "last_qntt": "5",
            "vol": "3985",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0"
        },
        {
            "data_date": "20231208",
            "data_time": "202200",
            "open_price": "75.41",
            "high_price": "75.43",
            "low_price": "75.41",
            "last_price": "75.43",
            "last_qntt": "3",
            "vol": "3988",
            "prev_diff_flag": "2",
            "prev_diff_price": "0.02",
            "prev_diff_rate": "0.02652168"
        },
        {
            "data_date": "20231208",
            "data_time": "202300",
            "open_price": "75.45",
            "high_price": "75.45",
            "low_price": "75.45",
            "last_price": "75.45",
            "last_qntt": "19",
            "vol": "4007",
            "prev_diff_flag": "2",
            "prev_diff_price": "0.02",
            "prev_diff_rate": "0.02651464"
        },
        {
            "data_date": "20231208",
            "data_time": "202400",
            "open_price": "75.45",
            "high_price": "75.45",
            "low_price": "75.45",
            "last_price": "75.45",
            "last_qntt": "2",
            "vol": "4009",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0"
        },
        {
            "data_date": "20231208",
            "data_time": "202600",
            "open_price": "75.45",
            "high_price": "75.47",
            "low_price": "75.45",
            "last_price": "75.47",
            "last_qntt": "4",
            "vol": "4013",
            "prev_diff_flag": "2",
            "prev_diff_price": "0.02",
            "prev_diff_rate": "0.02650762"
        },
        {
            "data_date": "20231208",
            "data_time": "202700",
            "open_price": "75.49",
            "high_price": "75.49",
            "low_price": "75.48",
            "last_price": "75.48",
            "last_qntt": "3",
            "vol": "4016",
            "prev_diff_flag": "2",
            "prev_diff_price": "0.01",
            "prev_diff_rate": "0.01325029"
        },
        {
            "data_date": "20231208",
            "data_time": "202800",
            "open_price": "75.45",
            "high_price": "75.46",
            "low_price": "75.45",
            "last_price": "75.46",
            "last_qntt": "3",
            "vol": "4019",
            "prev_diff_flag": "5",
            "prev_diff_price": "0.02",
            "prev_diff_rate": "-0.0264970"
        },
        {
            "data_date": "20231208",
            "data_time": "203100",
            "open_price": "75.46",
            "high_price": "75.46",
            "low_price": "75.46",
            "last_price": "75.46",
            "last_qntt": "1",
            "vol": "4020",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0"
        },
        {
            "data_date": "20231208",
            "data_time": "203300",
            "open_price": "75.43",
            "high_price": "75.43",
            "low_price": "75.43",
            "last_price": "75.43",
            "last_qntt": "1",
            "vol": "4021",
            "prev_diff_flag": "5",
            "prev_diff_price": "0.03",
            "prev_diff_rate": "-0.0397561"
        },
        {
            "data_date": "20231208",
            "data_time": "203400",
            "open_price": "75.41",
            "high_price": "75.41",
            "low_price": "75.4",
            "last_price": "75.4",
            "last_qntt": "6",
            "vol": "4027",
            "prev_diff_flag": "5",
            "prev_diff_price": "0.03",
            "prev_diff_rate": "-0.0397719"
        },
        {
            "data_date": "20231208",
            "data_time": "203500",
            "open_price": "75.41",
            "high_price": "75.41",
            "low_price": "75.41",
            "last_price": "75.41",
            "last_qntt": "2",
            "vol": "4029",
            "prev_diff_flag": "2",
            "prev_diff_price": "0.01",
            "prev_diff_rate": "0.01326259"
        },
        {
            "data_date": "20231208",
            "data_time": "203700",
            "open_price": "75.43",
            "high_price": "75.43",
            "low_price": "75.41",
            "last_price": "75.41",
            "last_qntt": "30",
            "vol": "4060",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0"
        },
        {
            "data_date": "20231208",
            "data_time": "204000",
            "open_price": "75.41",
            "high_price": "75.41",
            "low_price": "75.41",
            "last_price": "75.41",
            "last_qntt": "54",
            "vol": "4113",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0"
        },
        {
            "data_date": "20231208",
            "data_time": "204200",
            "open_price": "75.37",
            "high_price": "75.38",
            "low_price": "75.37",
            "last_price": "75.38",
            "last_qntt": "2",
            "vol": "4118",
            "prev_diff_flag": "5",
            "prev_diff_price": "0.03",
            "prev_diff_rate": "-0.0397825"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 체결추이(틱)

- **TR_ID**: HHDFC55020200
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/tick-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240423
QRY_TP:Q
QRY_CNT:40
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0040",
        "last_n_cnt": "0001",
        "index_key": "20240423      6445"
    },
    "output2": [
        {
            "data_date": "20240423",
            "data_time": "164434",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         4",
            "vol": "27806",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164434",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "27807",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164450",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         5",
            "vol": "27812",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164501",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         2",
            "vol": "27814",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164503",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         9",
            "vol": "27823",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164503",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "27824",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164507",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "27825",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164517",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "27826",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164517",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         2",
            "vol": "27828",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164526",
            "open_price": "           6465",
            "high_price": "           6465",
            "low_price": "           6465",
            "last_price": "           6465",
            "last_qntt": "         2",
            "vol": "27830",
            "prev_diff_flag": "2",
            "prev_diff_price": "              5",
            "prev_diff_rate": "      0.08"
        },
        {
            "data_date": "20240423",
            "data_time": "164542",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "27831",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164551",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "         1",
            "vol": "27832",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164555",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "         1",
            "vol": "27833",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164611",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         1",
            "vol": "27834",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164613",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         1",
            "vol": "27835",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164620",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         2",
            "vol": "27837",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164620",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         1",
            "vol": "27838",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164634",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "        10",
            "vol": "27848",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164634",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "         1",
            "vol": "27849",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164634",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "         1",
            "vol": "27850",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164634",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "        25",
            "vol": "27875",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164634",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "         5",
            "vol": "27880",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164650",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "         2",
            "vol": "27882",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164658",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "       400",
            "vol": "28282",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164658",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "         3",
            "vol": "28285",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164707",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         2",
            "vol": "28287",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164714",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         1",
            "vol": "28288",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164714",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         2",
            "vol": "28290",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164715",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         4",
            "vol": "28294",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164716",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "       315",
            "vol": "28609",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164735",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         2",
            "vol": "28611",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164735",
            "open_price": "         6464.5",
            "high_price": "         6464.5",
            "low_price": "         6464.5",
            "last_price": "         6464.5",
            "last_qntt": "         3",
            "vol": "28614",
            "prev_diff_flag": "2",
            "prev_diff_price": "            4.5",
            "prev_diff_rate": "      0.07"
        },
        {
            "data_date": "20240423",
            "data_time": "164817",
            "open_price": "           6464",
            "high_price": "           6464",
            "low_price": "           6464",
            "last_price": "           6464",
            "last_qntt": "         7",
            "vol": "28621",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240423",
            "data_time": "164828",
            "open_price": "         6463.5",
            "high_price": "         6463.5",
            "low_price": "         6463.5",
            "last_price": "         6463.5",
            "last_qntt": "         2",
            "vol": "28623",
            "prev_diff_flag": "2",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164837",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         1",
            "vol": "28624",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164838",
            "open_price": "           6463",
            "high_price": "           6463",
            "low_price": "           6463",
            "last_price": "           6463",
            "last_qntt": "         1",
            "vol": "28625",
            "prev_diff_flag": "2",
            "prev_diff_price": "              3",
            "prev_diff_rate": "      0.05"
        },
        {
            "data_date": "20240423",
            "data_time": "164856",
            "open_price": "         6462.5",
            "high_price": "         6462.5",
            "low_price": "         6462.5",
            "last_price": "         6462.5",
            "last_qntt": "         2",
            "vol": "28627",
            "prev_diff_flag": "2",
            "prev_diff_price": "            2.5",
            "prev_diff_rate": "      0.04"
        },
        {
            "data_date": "20240423",
            "data_time": "164856",
            "open_price": "         6462.5",
            "high_price": "         6462.5",
            "low_price": "         6462.5",
            "last_price": "         6462.5",
            "last_qntt": "         5",
            "vol": "28632",
            "prev_diff_flag": "2",
            "prev_diff_price": "            2.5",
            "prev_diff_rate": "      0.04"
        },
        {
            "data_date": "20240423",
            "data_time": "164856",
            "open_price": "         6462.5",
            "high_price": "         6462.5",
            "low_price": "         6462.5",
            "last_price": "         6462.5",
            "last_qntt": "        10",
            "vol": "28642",
            "prev_diff_flag": "2",
            "prev_diff_price": "            2.5",
            "prev_diff_rate": "      0.04"
        },
        {
            "data_date": "20240423",
            "data_time": "164856",
            "open_price": "         6462.5",
            "high_price": "         6462.5",
            "low_price": "         6462.5",
            "last_price": "         6462.5",
            "last_qntt": "         2",
            "vol": "28644",
            "prev_diff_flag": "2",
            "prev_diff_price": "            2.5",
            "prev_diff_rate": "      0.04"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 체결추이(주간)

- **TR_ID**: HHDFC55020000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/weekly-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240424
QRY_TP:
QRY_CNT:40
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0040",
        "last_n_cnt": "",
        "index_key": "20230522"
    },
    "output2": [
        {
            "data_date": "20230522",
            "data_time": "",
            "open_price": "         6713.0",
            "high_price": "         6713.0",
            "low_price": "         6620.0",
            "last_price": "         6620.0",
            "last_qntt": "",
            "vol": "        10",
            "prev_diff_flag": "5",
            "prev_diff_price": "             93",
            "prev_diff_rate": "     -1.39"
        },
        {
            "data_date": "20230612",
            "data_time": "",
            "open_price": "         6809.5",
            "high_price": "         6817.0",
            "low_price": "         6809.0",
            "last_price": "         6817.0",
            "last_qntt": "",
            "vol": "        20",
            "prev_diff_flag": "2",
            "prev_diff_price": "            197",
            "prev_diff_rate": "      2.98"
        },
        {
            "data_date": "20230626",
            "data_time": "",
            "open_price": "         6692.0",
            "high_price": "         6692.0",
            "low_price": "         6692.0",
            "last_price": "         6692.0",
            "last_qntt": "",
            "vol": "5         ",
            "prev_diff_flag": "5",
            "prev_diff_price": "            125",
            "prev_diff_rate": "     -1.83"
        },
        {
            "data_date": "20230710",
            "data_time": "",
            "open_price": "         6840.5",
            "high_price": "         6840.5",
            "low_price": "         6840.0",
            "last_price": "         6840.0",
            "last_qntt": "",
            "vol": "5         ",
            "prev_diff_flag": "2",
            "prev_diff_price": "            148",
            "prev_diff_rate": "      2.21"
        },
        {
            "data_date": "20230731",
            "data_time": "",
            "open_price": "         6702.0",
            "high_price": "         6702.0",
            "low_price": "         6605.0",
            "last_price": "         6605.0",
            "last_qntt": "",
            "vol": "        11",
            "prev_diff_flag": "5",
            "prev_diff_price": "            235",
            "prev_diff_rate": "     -3.44"
        },
        {
            "data_date": "20230807",
            "data_time": "",
            "open_price": "         6594.5",
            "high_price": "         6594.5",
            "low_price": "         6594.5",
            "last_price": "         6594.5",
            "last_qntt": "",
            "vol": "5         ",
            "prev_diff_flag": "5",
            "prev_diff_price": "           10.5",
            "prev_diff_rate": "     -0.16"
        },
        {
            "data_date": "20230904",
            "data_time": "",
            "open_price": "         6535.0",
            "high_price": "         6535.0",
            "low_price": "         6535.0",
            "last_price": "         6535.0",
            "last_qntt": "",
            "vol": "1         ",
            "prev_diff_flag": "5",
            "prev_diff_price": "           59.5",
            "prev_diff_rate": "     -0.90"
        },
        {
            "data_date": "20230911",
            "data_time": "",
            "open_price": "         6494.0",
            "high_price": "         6512.5",
            "low_price": "         6470.0",
            "last_price": "         6512.5",
            "last_qntt": "",
            "vol": "         8",
            "prev_diff_flag": "5",
            "prev_diff_price": "           22.5",
            "prev_diff_rate": "     -0.34"
        },
        {
            "data_date": "20230918",
            "data_time": "",
            "open_price": "         6500.5",
            "high_price": "         6558.5",
            "low_price": "         6459.5",
            "last_price": "         6479.5",
            "last_qntt": "",
            "vol": "        43",
            "prev_diff_flag": "5",
            "prev_diff_price": "             33",
            "prev_diff_rate": "     -0.51"
        },
        {
            "data_date": "20230925",
            "data_time": "",
            "open_price": "         6439.5",
            "high_price": "         6450.5",
            "low_price": "         6430.0",
            "last_price": "         6450.5",
            "last_qntt": "",
            "vol": "         3",
            "prev_diff_flag": "5",
            "prev_diff_price": "             29",
            "prev_diff_rate": "     -0.45"
        },
        {
            "data_date": "20231002",
            "data_time": "",
            "open_price": "         6480.5",
            "high_price": "         6480.5",
            "low_price": "         6360.0",
            "last_price": "         6406.0",
            "last_qntt": "",
            "vol": "        40",
            "prev_diff_flag": "5",
            "prev_diff_price": "           44.5",
            "prev_diff_rate": "     -0.69"
        },
        {
            "data_date": "20231009",
            "data_time": "",
            "open_price": "         6410.0",
            "high_price": "         6471.5",
            "low_price": "         6388.5",
            "last_price": "         6388.5",
            "last_qntt": "",
            "vol": "        21",
            "prev_diff_flag": "5",
            "prev_diff_price": "           17.5",
            "prev_diff_rate": "     -0.27"
        },
        {
            "data_date": "20231016",
            "data_time": "",
            "open_price": "         6381.0",
            "high_price": "         6423.0",
            "low_price": "         6345.0",
            "last_price": "         6360.0",
            "last_qntt": "",
            "vol": "        16",
            "prev_diff_flag": "5",
            "prev_diff_price": "           28.5",
            "prev_diff_rate": "     -0.45"
        },
        {
            "data_date": "20231023",
            "data_time": "",
            "open_price": "         6361.5",
            "high_price": "         6366.0",
            "low_price": "         6361.5",
            "last_price": "         6366.0",
            "last_qntt": "",
            "vol": "6         ",
            "prev_diff_flag": "2",
            "prev_diff_price": "              6",
            "prev_diff_rate": "      0.09"
        },
        {
            "data_date": "20231030",
            "data_time": "",
            "open_price": "         6460.5",
            "high_price": "         6547.0",
            "low_price": "         6460.5",
            "last_price": "         6530.0",
            "last_qntt": "",
            "vol": "       102",
            "prev_diff_flag": "2",
            "prev_diff_price": "            164",
            "prev_diff_rate": "      2.58"
        },
        {
            "data_date": "20231106",
            "data_time": "",
            "open_price": "         6502.0",
            "high_price": "         6502.0",
            "low_price": "         6395.0",
            "last_price": "         6395.0",
            "last_qntt": "",
            "vol": "        34",
            "prev_diff_flag": "5",
            "prev_diff_price": "            135",
            "prev_diff_rate": "     -2.07"
        },
        {
            "data_date": "20231113",
            "data_time": "",
            "open_price": "         6410.0",
            "high_price": "         6548.0",
            "low_price": "         6410.0",
            "last_price": "         6529.5",
            "last_qntt": "",
            "vol": "        18",
            "prev_diff_flag": "2",
            "prev_diff_price": "          134.5",
            "prev_diff_rate": "      2.10"
        },
        {
            "data_date": "20231120",
            "data_time": "",
            "open_price": "         6564.0",
            "high_price": "         6622.0",
            "low_price": "         6561.0",
            "last_price": "         6620.5",
            "last_qntt": "",
            "vol": "       190",
            "prev_diff_flag": "2",
            "prev_diff_price": "             91",
            "prev_diff_rate": "      1.39"
        },
        {
            "data_date": "20231127",
            "data_time": "",
            "open_price": "         6610.0",
            "high_price": "         6703.0",
            "low_price": "         6610.0",
            "last_price": "         6702.0",
            "last_qntt": "",
            "vol": "       326",
            "prev_diff_flag": "2",
            "prev_diff_price": "           81.5",
            "prev_diff_rate": "      1.23"
        },
        {
            "data_date": "20231204",
            "data_time": "",
            "open_price": "         6697.5",
            "high_price": "         6697.5",
            "low_price": "         6565.0",
            "last_price": "         6614.0",
            "last_qntt": "",
            "vol": "       296",
            "prev_diff_flag": "5",
            "prev_diff_price": "             88",
            "prev_diff_rate": "     -1.31"
        },
        {
            "data_date": "20231211",
            "data_time": "",
            "open_price": "         6605.0",
            "high_price": "         6760.5",
            "low_price": "         6578.0",
            "last_price": "         6730.0",
            "last_qntt": "",
            "vol": "       510",
            "prev_diff_flag": "2",
            "prev_diff_price": "            116",
            "prev_diff_rate": "      1.75"
        },
        {
            "data_date": "20231218",
            "data_time": "",
            "open_price": "         6731.0",
            "high_price": "         6855.5",
            "low_price": "         6725.0",
            "last_price": "         6827.0",
            "last_qntt": "",
            "vol": "       617",
            "prev_diff_flag": "2",
            "prev_diff_price": "             97",
            "prev_diff_rate": "      1.44"
        },
        {
            "data_date": "20231225",
            "data_time": "",
            "open_price": "         6834.0",
            "high_price": "         6900.0",
            "low_price": "         6811.5",
            "last_price": "         6858.5",
            "last_qntt": "",
            "vol": "       353",
            "prev_diff_flag": "2",
            "prev_diff_price": "           31.5",
            "prev_diff_rate": "      0.46"
        },
        {
            "data_date": "20240101",
            "data_time": "",
            "open_price": "         6841.0",
            "high_price": "         6864.5",
            "low_price": "         6683.0",
            "last_price": "         6742.0",
            "last_qntt": "",
            "vol": "       325",
            "prev_diff_flag": "5",
            "prev_diff_price": "          116.5",
            "prev_diff_rate": "     -1.70"
        },
        {
            "data_date": "20240108",
            "data_time": "",
            "open_price": "         6762.0",
            "high_price": "         6762.0",
            "low_price": "         6678.0",
            "last_price": "         6711.0",
            "last_qntt": "",
            "vol": "       310",
            "prev_diff_flag": "5",
            "prev_diff_price": "             31",
            "prev_diff_rate": "     -0.46"
        },
        {
            "data_date": "20240115",
            "data_time": "",
            "open_price": "         6709.5",
            "high_price": "         6728.0",
            "low_price": "         6556.0",
            "last_price": "         6624.5",
            "last_qntt": "",
            "vol": "       900",
            "prev_diff_flag": "5",
            "prev_diff_price": "           86.5",
            "prev_diff_rate": "     -1.29"
        },
        {
            "data_date": "20240122",
            "data_time": "",
            "open_price": "         6622.0",
            "high_price": "         6643.0",
            "low_price": "         6579.5",
            "last_price": "         6600.0",
            "last_qntt": "",
            "vol": "       389",
            "prev_diff_flag": "5",
            "prev_diff_price": "           24.5",
            "prev_diff_rate": "     -0.37"
        },
        {
            "data_date": "20240129",
            "data_time": "",
            "open_price": "         6598.0",
            "high_price": "         6646.5",
            "low_price": "         6529.0",
            "last_price": "         6539.5",
            "last_qntt": "",
            "vol": "       962",
            "prev_diff_flag": "5",
            "prev_diff_price": "           60.5",
            "prev_diff_rate": "     -0.92"
        },
        {
            "data_date": "20240205",
            "data_time": "",
            "open_price": "         6520.5",
            "high_price": "         6563.5",
            "low_price": "         6494.5",
            "last_price": "         6549.5",
            "last_qntt": "",
            "vol": "      1019",
            "prev_diff_flag": "2",
            "prev_diff_price": "             10",
            "prev_diff_rate": "      0.15"
        },
        {
            "data_date": "20240212",
            "data_time": "",
            "open_price": "         6553.0",
            "high_price": "         6568.0",
            "low_price": "         6469.0",
            "last_price": "         6557.5",
            "last_qntt": "",
            "vol": "       891",
            "prev_diff_flag": "2",
            "prev_diff_price": "              8",
            "prev_diff_rate": "      0.12"
        },
        {
            "data_date": "20240219",
            "data_time": "",
            "open_price": "         6564.0",
            "high_price": "         6616.5",
            "low_price": "         6544.5",
            "last_price": "         6584.0",
            "last_qntt": "",
            "vol": "      1773",
            "prev_diff_flag": "2",
            "prev_diff_price": "           26.5",
            "prev_diff_rate": "      0.40"
        },
        {
            "data_date": "20240226",
            "data_time": "",
            "open_price": "         6588.5",
            "high_price": "         6588.5",
            "low_price": "         6509.5",
            "last_price": "         6546.0",
            "last_qntt": "",
            "vol": "      3428",
            "prev_diff_flag": "5",
            "prev_diff_price": "             38",
            "prev_diff_rate": "     -0.58"
        },
        {
            "data_date": "20240304",
            "data_time": "",
            "open_price": "         6546.0",
            "high_price": "         6686.5",
            "low_price": "         6498.0",
            "last_price": "         6644.0",
            "last_qntt": "",
            "vol": "     35069",
            "prev_diff_flag": "2",
            "prev_diff_price": "             98",
            "prev_diff_rate": "      1.50"
        },
        {
            "data_date": "20240311",
            "data_time": "",
            "open_price": "         6645.0",
            "high_price": "         6646.0",
            "low_price": "        0.66235",
            "last_price": "         6577.5",
            "last_qntt": "",
            "vol": "    115245",
            "prev_diff_flag": "5",
            "prev_diff_price": "           66.5",
            "prev_diff_rate": "     -1.00"
        },
        {
            "data_date": "20240318",
            "data_time": "",
            "open_price": "         6576.5",
            "high_price": "         6650.5",
            "low_price": "         6525.5",
            "last_price": "         6530.5",
            "last_qntt": "",
            "vol": "    328691",
            "prev_diff_flag": "5",
            "prev_diff_price": "             47",
            "prev_diff_rate": "     -0.71"
        },
        {
            "data_date": "20240325",
            "data_time": "",
            "open_price": "           6530",
            "high_price": "         6574.5",
            "low_price": "         6499.5",
            "last_price": "           6530",
            "last_qntt": "",
            "vol": "    301604",
            "prev_diff_flag": "5",
            "prev_diff_price": "            0.5",
            "prev_diff_rate": "     -0.01"
        },
        {
            "data_date": "20240401",
            "data_time": "",
            "open_price": "         6531.5",
            "high_price": "           6633",
            "low_price": "         6495.0",
            "last_price": "           6593",
            "last_qntt": "",
            "vol": "    474911",
            "prev_diff_flag": "2",
            "prev_diff_price": "             63",
            "prev_diff_rate": "      0.96"
        },
        {
            "data_date": "20240408",
            "data_time": "",
            "open_price": "           6590",
            "high_price": "         6657.5",
            "low_price": "         6468.0",
            "last_price": "         6474.0",
            "last_qntt": "",
            "vol": "    594239",
            "prev_diff_flag": "5",
            "prev_diff_price": "            119",
            "prev_diff_rate": "     -1.80"
        },
        {
            "data_date": "20240415",
            "data_time": "",
            "open_price": "         6475.5",
            "high_price": "         6505.0",
            "low_price": "         6373.0",
            "last_price": "         6428.5",
            "last_qntt": "",
            "vol": "    540988",
            "prev_diff_flag": "5",
            "prev_diff_price": "           45.5",
            "prev_diff_rate": "     -0.70"
        },
        {
            "data_date": "20240422",
            "data_time": "",
            "open_price": "         6430.0",
            "high_price": "         6466.5",
            "low_price": "         6425.0",
            "last_price": "         6460.0",
            "last_qntt": "",
            "vol": "82245     ",
            "prev_diff_flag": "2",
            "prev_diff_price": "           31.5",
            "prev_diff_rate": "      0.49"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 체결추이(일간)

- **TR_ID**: HHDFC55020100
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/daily-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240424
QRY_TP:
QRY_CNT:40
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0040",
        "last_n_cnt": "",
        "index_key": "20240226"
    },
    "output2": [
        {
            "data_date": "20240226",
            "data_time": "",
            "open_price": "         6588.5",
            "high_price": "         6588.5",
            "low_price": "         6555.0",
            "last_price": "         6562.5",
            "last_qntt": "",
            "vol": "       639",
            "prev_diff_flag": "5",
            "prev_diff_price": "           21.5",
            "prev_diff_rate": "     -0.33"
        },
        {
            "data_date": "20240227",
            "data_time": "",
            "open_price": "         6555.0",
            "high_price": "         6577.5",
            "low_price": "         6549.0",
            "last_price": "         6565.0",
            "last_qntt": "",
            "vol": "       134",
            "prev_diff_flag": "2",
            "prev_diff_price": "            2.5",
            "prev_diff_rate": "      0.04"
        },
        {
            "data_date": "20240228",
            "data_time": "",
            "open_price": "         6567.0",
            "high_price": "         6568.5",
            "low_price": "         6511.0",
            "last_price": "         6515.0",
            "last_qntt": "",
            "vol": "      1210",
            "prev_diff_flag": "5",
            "prev_diff_price": "             50",
            "prev_diff_rate": "     -0.76"
        },
        {
            "data_date": "20240229",
            "data_time": "",
            "open_price": "         6516.0",
            "high_price": "         6551.0",
            "low_price": "         6509.5",
            "last_price": "         6519.0",
            "last_qntt": "",
            "vol": "       503",
            "prev_diff_flag": "2",
            "prev_diff_price": "              4",
            "prev_diff_rate": "      0.06"
        },
        {
            "data_date": "20240301",
            "data_time": "",
            "open_price": "         6517.5",
            "high_price": "         6554.5",
            "low_price": "         6510.5",
            "last_price": "         6546.0",
            "last_qntt": "",
            "vol": "       942",
            "prev_diff_flag": "2",
            "prev_diff_price": "             27",
            "prev_diff_rate": "      0.41"
        },
        {
            "data_date": "20240304",
            "data_time": "",
            "open_price": "         6546.0",
            "high_price": "         6549.0",
            "low_price": "         6528.5",
            "last_price": "         6528.5",
            "last_qntt": "",
            "vol": "      2298",
            "prev_diff_flag": "5",
            "prev_diff_price": "           17.5",
            "prev_diff_rate": "     -0.27"
        },
        {
            "data_date": "20240305",
            "data_time": "",
            "open_price": "         6530.5",
            "high_price": "         6541.0",
            "low_price": "         6498.0",
            "last_price": "         6523.5",
            "last_qntt": "",
            "vol": "     13778",
            "prev_diff_flag": "5",
            "prev_diff_price": "              5",
            "prev_diff_rate": "     -0.08"
        },
        {
            "data_date": "20240306",
            "data_time": "",
            "open_price": "         6522.0",
            "high_price": "         6600.5",
            "low_price": "         6512.5",
            "last_price": "         6584.5",
            "last_qntt": "",
            "vol": "      3269",
            "prev_diff_flag": "2",
            "prev_diff_price": "             61",
            "prev_diff_rate": "      0.94"
        },
        {
            "data_date": "20240307",
            "data_time": "",
            "open_price": "         6582.0",
            "high_price": "         6643.5",
            "low_price": "         6582.0",
            "last_price": "         6639.0",
            "last_qntt": "",
            "vol": "     10466",
            "prev_diff_flag": "2",
            "prev_diff_price": "           54.5",
            "prev_diff_rate": "      0.83"
        },
        {
            "data_date": "20240308",
            "data_time": "",
            "open_price": "         6637.0",
            "high_price": "         6686.5",
            "low_price": "         6632.5",
            "last_price": "         6644.0",
            "last_qntt": "",
            "vol": "      5258",
            "prev_diff_flag": "2",
            "prev_diff_price": "              5",
            "prev_diff_rate": "      0.08"
        },
        {
            "data_date": "20240311",
            "data_time": "",
            "open_price": "         6645.0",
            "high_price": "         6646.0",
            "low_price": "         6616.0",
            "last_price": "         6633.0",
            "last_qntt": "",
            "vol": "     39035",
            "prev_diff_flag": "5",
            "prev_diff_price": "             11",
            "prev_diff_rate": "     -0.17"
        },
        {
            "data_date": "20240312",
            "data_time": "",
            "open_price": "         0.6624",
            "high_price": "         0.6624",
            "low_price": "        0.66235",
            "last_price": "         0.6625",
            "last_qntt": "",
            "vol": "        11",
            "prev_diff_flag": "5",
            "prev_diff_price": "      6632.3375",
            "prev_diff_rate": "    -99.99"
        },
        {
            "data_date": "20240313",
            "data_time": "",
            "open_price": "          0.664",
            "high_price": "         0.6641",
            "low_price": "          0.664",
            "last_price": "          0.664",
            "last_qntt": "",
            "vol": "        50",
            "prev_diff_flag": "2",
            "prev_diff_price": "         0.0015",
            "prev_diff_rate": "      0.23"
        },
        {
            "data_date": "20240314",
            "data_time": "",
            "open_price": "         6598.5",
            "high_price": "         6598.5",
            "low_price": "         6598.5",
            "last_price": "         6598.5",
            "last_qntt": "",
            "vol": "        83",
            "prev_diff_flag": "2",
            "prev_diff_price": "       6597.836",
            "prev_diff_rate": " 993650.00"
        },
        {
            "data_date": "20240315",
            "data_time": "",
            "open_price": "         6598.5",
            "high_price": "         6599.5",
            "low_price": "         6569.5",
            "last_price": "         6577.5",
            "last_qntt": "",
            "vol": "     76056",
            "prev_diff_flag": "5",
            "prev_diff_price": "             21",
            "prev_diff_rate": "     -0.32"
        },
        {
            "data_date": "20240318",
            "data_time": "",
            "open_price": "         6576.5",
            "high_price": "         6576.5",
            "low_price": "         6576.5",
            "last_price": "         6576.5",
            "last_qntt": "",
            "vol": "         1",
            "prev_diff_flag": "5",
            "prev_diff_price": "              1",
            "prev_diff_rate": "     -0.02"
        },
        {
            "data_date": "20240319",
            "data_time": "",
            "open_price": "           6548",
            "high_price": "           6549",
            "low_price": "           6548",
            "last_price": "         6548.5",
            "last_qntt": "",
            "vol": "        44",
            "prev_diff_flag": "5",
            "prev_diff_price": "             28",
            "prev_diff_rate": "     -0.43"
        },
        {
            "data_date": "20240320",
            "data_time": "",
            "open_price": "         6548.0",
            "high_price": "         6603.5",
            "low_price": "         6528.0",
            "last_price": "         6602.5",
            "last_qntt": "",
            "vol": "    100506",
            "prev_diff_flag": "2",
            "prev_diff_price": "             54",
            "prev_diff_rate": "      0.82"
        },
        {
            "data_date": "20240321",
            "data_time": "",
            "open_price": "         6598.0",
            "high_price": "         6650.5",
            "low_price": "         6577.0",
            "last_price": "         6586.0",
            "last_qntt": "",
            "vol": "    126413",
            "prev_diff_flag": "5",
            "prev_diff_price": "           16.5",
            "prev_diff_rate": "     -0.25"
        },
        {
            "data_date": "20240322",
            "data_time": "",
            "open_price": "         6585.5",
            "high_price": "         6592.5",
            "low_price": "         6525.5",
            "last_price": "         6530.5",
            "last_qntt": "",
            "vol": "    101727",
            "prev_diff_flag": "5",
            "prev_diff_price": "           55.5",
            "prev_diff_rate": "     -0.84"
        },
        {
            "data_date": "20240325",
            "data_time": "",
            "open_price": "           6530",
            "high_price": "         6562.5",
            "low_price": "           6525",
            "last_price": "         6555.5",
            "last_qntt": "",
            "vol": "     70152",
            "prev_diff_flag": "2",
            "prev_diff_price": "             25",
            "prev_diff_rate": "      0.38"
        },
        {
            "data_date": "20240326",
            "data_time": "",
            "open_price": "         6555.5",
            "high_price": "         6574.5",
            "low_price": "         6545.5",
            "last_price": "         6548.5",
            "last_qntt": "",
            "vol": "     58147",
            "prev_diff_flag": "5",
            "prev_diff_price": "              7",
            "prev_diff_rate": "     -0.11"
        },
        {
            "data_date": "20240327",
            "data_time": "",
            "open_price": "           6548",
            "high_price": "           6553",
            "low_price": "         6525.5",
            "last_price": "           6549",
            "last_qntt": "",
            "vol": "     68767",
            "prev_diff_flag": "2",
            "prev_diff_price": "            0.5",
            "prev_diff_rate": "      0.01"
        },
        {
            "data_date": "20240328",
            "data_time": "",
            "open_price": "         6548.5",
            "high_price": "         6555.5",
            "low_price": "         6499.5",
            "last_price": "           6530",
            "last_qntt": "",
            "vol": "    104538",
            "prev_diff_flag": "5",
            "prev_diff_price": "             19",
            "prev_diff_rate": "     -0.29"
        },
        {
            "data_date": "20240401",
            "data_time": "",
            "open_price": "         6531.5",
            "high_price": "         6554.0",
            "low_price": "         6495.0",
            "last_price": "         6504.0",
            "last_qntt": "",
            "vol": "     74942",
            "prev_diff_flag": "5",
            "prev_diff_price": "             26",
            "prev_diff_rate": "     -0.40"
        },
        {
            "data_date": "20240402",
            "data_time": "",
            "open_price": "         6504.0",
            "high_price": "         6538.0",
            "low_price": "         6496.5",
            "last_price": "         6531.5",
            "last_qntt": "",
            "vol": "     83996",
            "prev_diff_flag": "2",
            "prev_diff_price": "           27.5",
            "prev_diff_rate": "      0.42"
        },
        {
            "data_date": "20240403",
            "data_time": "",
            "open_price": "           6532",
            "high_price": "           6584",
            "low_price": "         6517.5",
            "last_price": "         6579.5",
            "last_qntt": "",
            "vol": "     94108",
            "prev_diff_flag": "2",
            "prev_diff_price": "             48",
            "prev_diff_rate": "      0.73"
        },
        {
            "data_date": "20240404",
            "data_time": "",
            "open_price": "           6577",
            "high_price": "           6633",
            "low_price": "           6577",
            "last_price": "         6601.5",
            "last_qntt": "",
            "vol": "    115253",
            "prev_diff_flag": "2",
            "prev_diff_price": "             22",
            "prev_diff_rate": "      0.33"
        },
        {
            "data_date": "20240405",
            "data_time": "",
            "open_price": "         6601.5",
            "high_price": "         6606.5",
            "low_price": "           6563",
            "last_price": "           6593",
            "last_qntt": "",
            "vol": "    106612",
            "prev_diff_flag": "5",
            "prev_diff_price": "            8.5",
            "prev_diff_rate": "     -0.13"
        },
        {
            "data_date": "20240408",
            "data_time": "",
            "open_price": "           6590",
            "high_price": "         6623.5",
            "low_price": "           6573",
            "last_price": "         6617.5",
            "last_qntt": "",
            "vol": "     71474",
            "prev_diff_flag": "2",
            "prev_diff_price": "           24.5",
            "prev_diff_rate": "      0.37"
        },
        {
            "data_date": "20240409",
            "data_time": "",
            "open_price": "           6617",
            "high_price": "         6657.5",
            "low_price": "           6612",
            "last_price": "         6641.5",
            "last_qntt": "",
            "vol": "     88858",
            "prev_diff_flag": "2",
            "prev_diff_price": "             24",
            "prev_diff_rate": "      0.36"
        },
        {
            "data_date": "20240410",
            "data_time": "",
            "open_price": "         6641.5",
            "high_price": "         6644.5",
            "low_price": "         6512.0",
            "last_price": "         6525.0",
            "last_qntt": "",
            "vol": "    186665",
            "prev_diff_flag": "5",
            "prev_diff_price": "          116.5",
            "prev_diff_rate": "     -1.75"
        },
        {
            "data_date": "20240411",
            "data_time": "",
            "open_price": "         6524.5",
            "high_price": "         6565.0",
            "low_price": "         6514.5",
            "last_price": "         6550.5",
            "last_qntt": "",
            "vol": "    121379",
            "prev_diff_flag": "2",
            "prev_diff_price": "           25.5",
            "prev_diff_rate": "      0.39"
        },
        {
            "data_date": "20240412",
            "data_time": "",
            "open_price": "         6550.5",
            "high_price": "         6555.5",
            "low_price": "         6468.0",
            "last_price": "         6474.0",
            "last_qntt": "",
            "vol": "    125863",
            "prev_diff_flag": "5",
            "prev_diff_price": "           76.5",
            "prev_diff_rate": "     -1.17"
        },
        {
            "data_date": "20240415",
            "data_time": "",
            "open_price": "         6475.5",
            "high_price": "         6505.0",
            "low_price": "         6449.0",
            "last_price": "         6453.5",
            "last_qntt": "",
            "vol": "    113834",
            "prev_diff_flag": "5",
            "prev_diff_price": "           20.5",
            "prev_diff_rate": "     -0.32"
        },
        {
            "data_date": "20240416",
            "data_time": "",
            "open_price": "         6456.5",
            "high_price": "         6456.5",
            "low_price": "         6401.0",
            "last_price": "         6414.0",
            "last_qntt": "",
            "vol": "    120271",
            "prev_diff_flag": "5",
            "prev_diff_price": "           39.5",
            "prev_diff_rate": "     -0.61"
        },
        {
            "data_date": "20240417",
            "data_time": "",
            "open_price": "         6413.5",
            "high_price": "         6457.5",
            "low_price": "         6411.5",
            "last_price": "         6446.0",
            "last_qntt": "",
            "vol": "    110152",
            "prev_diff_flag": "2",
            "prev_diff_price": "             32",
            "prev_diff_rate": "      0.50"
        },
        {
            "data_date": "20240418",
            "data_time": "",
            "open_price": "         6446.0",
            "high_price": "         6467.0",
            "low_price": "         6427.5",
            "last_price": "         6432.0",
            "last_qntt": "",
            "vol": "     76120",
            "prev_diff_flag": "5",
            "prev_diff_price": "             14",
            "prev_diff_rate": "     -0.22"
        },
        {
            "data_date": "20240419",
            "data_time": "",
            "open_price": "         6431.5",
            "high_price": "         6444.0",
            "low_price": "         6373.0",
            "last_price": "         6428.5",
            "last_qntt": "",
            "vol": "    120611",
            "prev_diff_flag": "5",
            "prev_diff_price": "            3.5",
            "prev_diff_rate": "     -0.05"
        },
        {
            "data_date": "20240422",
            "data_time": "",
            "open_price": "         6430.0",
            "high_price": "         6466.5",
            "low_price": "         6425.0",
            "last_price": "         6460.0",
            "last_qntt": "",
            "vol": "     82245",
            "prev_diff_flag": "2",
            "prev_diff_price": "           31.5",
            "prev_diff_rate": "      0.49"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 체결추이(월간)

- **TR_ID**: HHDFC55020300
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/monthly-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240423
QRY_TP:
QRY_CNT:30
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0013",
        "last_n_cnt": "",
        "index_key": ""
    },
    "output2": [
        {
            "data_date": "20230401",
            "data_time": "",
            "open_price": "         6770.0",
            "high_price": "         6770.0",
            "low_price": "         6770.0",
            "last_price": "         6770.0",
            "last_qntt": "",
            "vol": "3",
            "prev_diff_flag": "3",
            "prev_diff_price": "      0.0000000",
            "prev_diff_rate": "      0.00"
        },
        {
            "data_date": "20230501",
            "data_time": "",
            "open_price": "         6795.0",
            "high_price": "         6800.0",
            "low_price": "         6620.0",
            "last_price": "         6620.0",
            "last_qntt": "",
            "vol": "        16",
            "prev_diff_flag": "5",
            "prev_diff_price": "    150.0000000",
            "prev_diff_rate": "     -2.22"
        },
        {
            "data_date": "20230601",
            "data_time": "",
            "open_price": "         6809.5",
            "high_price": "         6817.0",
            "low_price": "         6692.0",
            "last_price": "         6692.0",
            "last_qntt": "",
            "vol": "        25",
            "prev_diff_flag": "2",
            "prev_diff_price": "     72.0000000",
            "prev_diff_rate": "      1.09"
        },
        {
            "data_date": "20230701",
            "data_time": "",
            "open_price": "         6840.5",
            "high_price": "         6840.5",
            "low_price": "         6840.0",
            "last_price": "         6840.0",
            "last_qntt": "",
            "vol": "5",
            "prev_diff_flag": "2",
            "prev_diff_price": "    148.0000000",
            "prev_diff_rate": "      2.21"
        },
        {
            "data_date": "20230801",
            "data_time": "",
            "open_price": "         6702.0",
            "high_price": "         6702.0",
            "low_price": "         6594.5",
            "last_price": "         6594.5",
            "last_qntt": "",
            "vol": "        16",
            "prev_diff_flag": "5",
            "prev_diff_price": "    245.5000000",
            "prev_diff_rate": "     -3.59"
        },
        {
            "data_date": "20230901",
            "data_time": "",
            "open_price": "         6535.0",
            "high_price": "         6558.5",
            "low_price": "         6430.0",
            "last_price": "         6450.5",
            "last_qntt": "",
            "vol": "        55",
            "prev_diff_flag": "5",
            "prev_diff_price": "    144.0000000",
            "prev_diff_rate": "     -2.18"
        },
        {
            "data_date": "20231001",
            "data_time": "",
            "open_price": "         6480.5",
            "high_price": "         6480.5",
            "low_price": "         6345.0",
            "last_price": "         6366.0",
            "last_qntt": "",
            "vol": "        83",
            "prev_diff_flag": "5",
            "prev_diff_price": "     84.5000000",
            "prev_diff_rate": "     -1.31"
        },
        {
            "data_date": "20231101",
            "data_time": "",
            "open_price": "         6460.5",
            "high_price": "         6675.0",
            "low_price": "         6395.0",
            "last_price": "         6640.0",
            "last_qntt": "",
            "vol": "       532",
            "prev_diff_flag": "2",
            "prev_diff_price": "    274.0000000",
            "prev_diff_rate": "      4.30"
        },
        {
            "data_date": "20231201",
            "data_time": "",
            "open_price": "         6642.0",
            "high_price": "         6900.0",
            "low_price": "         6565.0",
            "last_price": "         6858.5",
            "last_qntt": "",
            "vol": "      1914",
            "prev_diff_flag": "2",
            "prev_diff_price": "    218.5000000",
            "prev_diff_rate": "      3.29"
        },
        {
            "data_date": "20240101",
            "data_time": "",
            "open_price": "         6841.0",
            "high_price": "         6864.5",
            "low_price": "         6556.0",
            "last_price": "         6591.0",
            "last_qntt": "",
            "vol": "      2302",
            "prev_diff_flag": "5",
            "prev_diff_price": "    267.5000000",
            "prev_diff_rate": "     -3.90"
        },
        {
            "data_date": "20240201",
            "data_time": "",
            "open_price": "         6588.0",
            "high_price": "         6629.0",
            "low_price": "         6469.0",
            "last_price": "         6519.0",
            "last_qntt": "",
            "vol": "      6753",
            "prev_diff_flag": "5",
            "prev_diff_price": "     72.0000000",
            "prev_diff_rate": "     -1.09"
        },
        {
            "data_date": "20240301",
            "data_time": "",
            "open_price": "         6517.5",
            "high_price": "         6686.5",
            "low_price": "        0.66235",
            "last_price": "           6530",
            "last_qntt": "",
            "vol": "    781551",
            "prev_diff_flag": "2",
            "prev_diff_price": "     11.0000000",
            "prev_diff_rate": "      0.17"
        },
        {
            "data_date": "20240401",
            "data_time": "",
            "open_price": "         6531.5",
            "high_price": "         6657.5",
            "low_price": "         6373.0",
            "last_price": "         6460.0",
            "last_qntt": "",
            "vol": "   1692383",
            "prev_diff_flag": "5",
            "prev_diff_price": "     70.0000000",
            "prev_diff_rate": "     -1.07"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 상품기본정보

- **TR_ID**: HHDFC55200000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/search-contract-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | QRY_CNT:2
SRS_CD_01:6AM24
SRS_CD_02:10YK24 |  |
| Response Example | {
    "output2": [
        {
            "exch_cd": "CME",
            "clas_cd": "001",
            "crc_cd": "USD",
            "sttl_price": "         6684.5",
            "sttl_date": "20240516",
            "trst_mgn": "               1595",
            "disp_digit": "        10",
            "tick_sz": "            0.00005",
            "tick_val": "                  5",
            "mrkt_open_date": "20240517",
            "mrkt_open_time": "070000",
            "mrkt_close_date": "20240518",
            "mrkt_close_time": "060000",
            "trd_fr_date": "20190604",
            "expr_date": "20240617",
            "trd_to_date": "20240617",
            "remn_cnt": "  29",
            "stat_tp": "1",
            "ctrt_size": "             100000",
            "stl_tp": "실물인수도",
            "frst_noti_date": "20240617",
            "sub_exch_nm": "CME"
        },
        {
            "exch_cd": "CME",
            "clas_cd": "002",
            "crc_cd": "USD",
            "sttl_price": "           4375",
            "sttl_date": "20240516",
            "trst_mgn": "                352",
            "disp_digit": "        10",
            "tick_sz": "              0.001",
            "tick_val": "                  1",
            "mrkt_open_date": "20240517",
            "mrkt_open_time": "070000",
            "mrkt_close_date": "20240518",
            "mrkt_close_time": "060000",
            "trd_fr_date": "20240315",
            "expr_date": "20240531",
            "trd_to_date": "20240531",
            "remn_cnt": "  15",
            "stat_tp": "1",
            "ctrt_size": "               1000",
            "stl_tp": "현금결제",
            "frst_noti_date": "20240531",
            "sub_exch_nm": "CBOT"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물 미결제추이

- **TR_ID**: HHDDB95030000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/investor-unpd-trend`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | PROD_ISCD:ES
BSOP_DATE:20240624
UPMU_GUBUN:0
CTS_KEY: |  |
| Response Example | {
    "output1": {
        "row_cnt": "0100"
    },
    "output2": [
        {
            "prod_iscd": "ES",
            "cftc_iscd": "13874A",
            "bsop_date": "20240611",
            "bidp_spec": "270380",
            "askp_spec": "381794",
            "spread_spec": "0",
            "bidp_hedge": "1606798",
            "askp_hedge": "1617849",
            "hts_otst_smtn": "2266096",
            "bidp_missing": "297310",
            "askp_missing": "174845",
            "bidp_spec_cust": "80",
            "askp_spec_cust": "68",
            "spread_spec_cust": "55",
            "bidp_hedge_cust": "253",
            "askp_hedge_cust": "205",
            "cust_smtn": "472"
        },
        {
            "prod_iscd": "ES",
            "cftc_iscd": "13874A",
            "bsop_date": "20240604",
            "bidp_spec": "265433",
            "askp_spec": "330433",
            "spread_spec": "0",
            "bidp_hedge": "1534557",
            "askp_hedge": "1581649",
            "hts_otst_smtn": "2160026",
            "bidp_missing": "287673",
            "askp_missing": "175581",
            "bidp_spec_cust": "76",
            "askp_spec_cust": "68",
            "spread_spec_cust": "45",
            "bidp_hedge_cust": "262",
            "askp_hedge_cust": "207",
            "cust_smtn": "474"
        },
        {
            "prod_iscd": "ES",
            "cftc_iscd": "13874A",
            "bsop_date": "20240528",
            "bidp_spec": "330937",
            "askp_spec": "333145",
            "spread_spec": "0",
            "bidp_hedge": "1503708",
            "askp_hedge": "1609652",
            "hts_otst_smtn": "2179731",
            "bidp_missing": "289071",
            "askp_missing": "180919",
            "bidp_spec_cust": "80",
            "askp_spec_cust": "63",
            "spread_spec_cust": "39",
            "bidp_hedge_cust": "251",
            "askp_hedge_cust": "203",
            "cust_smtn": "469"
        },
        {
            "prod_iscd": "ES",
            "cftc_iscd": "13874A",
            "bsop_date": "20240521",
            "bidp_spec": "304226",
            "askp_spec": "327000",
            "spread_spec": "0",
            "bidp_hedge": "1501724",
            "askp_hedge": "1593706",
            "hts_otst_smtn": "2148201",
            "bidp_missing": "288496",
            "askp_missing": "173740",
            "bidp_spec_cust": "78",
            "askp_spec_cust": "66",
            "spread_spec_cust": "42",
            "bidp_hedge_cust": "249",
            "askp_hedge_cust": "205",
            "cust_smtn": "470"
        },
        {
            "prod_iscd": "ES",
            "cftc_iscd": "13874A",
            "bsop_date": "20240514",
            "bidp_spec": "273398",
            "askp_spec": "298682",
            "spread_spec": "0",
            "bidp_hedge": "1477881",
            "askp_hedge": "1550928",
            "hts_otst_smtn": "2081097",
            "bidp_missing": "278004",
            "askp_missing": "179673",
            "bidp_spec_cust": "83",
            "askp_spec_cust": "67",
            "spread_spec_cust": "45",
            "bidp_hedge_cust": "248",
            "askp_hedge_cust": "201",
            "cust_smtn": "470"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "",
    "msg1": "정상 조회되었습니다."
} |  |


### 해외옵션종목현재가

- **TR_ID**: HHDFO55010000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OGXX24 C19500 |  |
| Response Example | {
    "output1": {
        "proc_date": "20241108",
        "proc_time": "173441",
        "open_price": "           84.0",
        "high_price": "           84.0",
        "low_price": "           83.0",
        "last_price": "           83.0",
        "vol": "         3",
        "prev_diff_flag": "5",
        "prev_diff_price": "           38.0",
        "prev_diff_rate": "    -31.40",
        "bid_qntt": "       275",
        "bid_price": "           83.0",
        "ask_qntt": "       425",
        "ask_price": "           87.0",
        "prev_price": "          121.0",
        "trst_mgn": "               4101",
        "exch_cd": "EUREX",
        "crc_cd": "EUR",
        "trd_fr_date": "20240816",
        "expr_date": "20240816",
        "trd_to_date": "20241115",
        "remn_cnt": "0008",
        "last_qntt": "         2",
        "tot_ask_qntt": "       952",
        "tot_bid_qntt": "       726",
        "tick_size": "                0.1",
        "open_date": "20241108",
        "open_time": "150000",
        "close_date": "20241109",
        "close_time": "013000",
        "sbsnsdate": "20241108",
        "sttl_price": "          102.2"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션종목상세

- **TR_ID**: HHDFO55010100
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 P5650 |  |
| Response Example | {
    "output1": {
        "exch_cd": "CME",
        "clas_cd": "4",
        "crc_cd": "USD",
        "sttl_price": "           7525",
        "sttl_date": "20240826",
        "trst_mgn": "               7788",
        "disp_digit": "        10",
        "tick_sz": "                  0",
        "tick_val": "                2.5",
        "mrkt_open_date": "20240826",
        "mrkt_open_time": "070000",
        "mrkt_close_date": "20240827",
        "mrkt_close_time": "060000",
        "trd_fr_date": "20240610",
        "expr_date": "20240920",
        "trd_to_date": "20240920",
        "remn_cnt": "  26",
        "stat_tp": "1",
        "ctrt_size": "                 50",
        "stl_tp": "현금결제",
        "frst_noti_date": "20240920"
    },
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 호가

- **TR_ID**: HHDFO86000000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-asking-price`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OTXM24 C22000 |  |
| Response Example | {
    "output1": {
        "open_price": "          282.0",
        "high_price": "          295.0",
        "lowp_rice": "          280.0",
        "last_price": "          290.0",
        "sttl_price": "          288.0",
        "vol": "       100",
        "prev_diff_price": "            2.0",
        "prev_diff_rate": "      0.69",
        "quot_date": "20240528",
        "quot_time": "184601"
    },
    "output2": [
        {
            "bid_qntt": "        37",
            "bid_num": "         0",
            "bid_price": "          288.0",
            "ask_qntt": "         4",
            "ask_num": "         0",
            "ask_price": "          290.0"
        },
        {
            "bid_qntt": "        43",
            "bid_num": "         0",
            "bid_price": "          287.0",
            "ask_qntt": "         8",
            "ask_num": "         0",
            "ask_price": "          291.0"
        },
        {
            "bid_qntt": "        20",
            "bid_num": "         0",
            "bid_price": "          285.0",
            "ask_qntt": "        54",
            "ask_num": "         0",
            "ask_price": "          292.0"
        },
        {
            "bid_qntt": "         4",
            "bid_num": "         0",
            "bid_price": "          280.0",
            "ask_qntt": "        21",
            "ask_num": "         0",
            "ask_price": "          295.0"
        },
        {
            "bid_qntt": "         5",
            "bid_num": "         0",
            "bid_price": "          276.0",
            "ask_qntt": "         1",
            "ask_num": "         0",
            "ask_price": "          296.0"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 분봉조회

- **TR_ID**: HHDFO55020400
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-time-optchartprice`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 C5660
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:120
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output2": {
        "ret_cnt": "0120",
        "last_n_cnt": "",
        "index_key": "20240820        29"
    },
    "output1": [
        {
            "data_date": "20240821",
            "data_time": "031600",
            "open_price": "6375",
            "high_price": "6425",
            "low_price": "6375",
            "last_price": "6425",
            "last_qntt": "18",
            "vol": "251",
            "prev_diff_flag": "2",
            "prev_diff_price": "75",
            "prev_diff_rate": "1.18"
        },
        {
            "data_date": "20240821",
            "data_time": "043400",
            "open_price": "6000",
            "high_price": "6000",
            "low_price": "6000",
            "last_price": "6000",
            "last_qntt": "2",
            "vol": "253",
            "prev_diff_flag": "5",
            "prev_diff_price": "-425",
            "prev_diff_rate": "-6.61"
        },
        {
            "data_date": "20240821",
            "data_time": "044100",
            "open_price": "6025",
            "high_price": "6025",
            "low_price": "6000",
            "last_price": "6000",
            "last_qntt": "4",
            "vol": "257",
            "prev_diff_flag": "3",
            "prev_diff_price": "0",
            "prev_diff_rate": "0.00"
        },
        {
            "data_date": "20240821",
            "data_time": "044700",
            "open_price": "6025",
            "high_price": "6025",
            "low_price": "6025",
            "last_price": "6025",
            "last_qntt": "10",
            "vol": "267",
            "prev_diff_flag": "2",
            "prev_diff_price": "25",
            "prev_diff_rate": "0.42"
        },...
        {
            "data_date": "20240826",
            "data_time": "141000",
            "open_price": "6950",
            "high_price": "6950",
            "low_price": "6950",
            "last_price": "6950",
            "last_qntt": "1",
            "vol": "1",
            "prev_diff_flag": "5",
            "prev_diff_price": "-125",
            "prev_diff_rate": "-1.77"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 체결추이(틱)

- **TR_ID**: HHDFO55020200
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-tick-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:30
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0030",
        "last_n_cnt": "0001",
        "index_key": "20240823       146"
    },
    "output2": [
        {
            "data_date": "20240824",
            "data_time": "024037",
            "open_price": "9900",
            "high_price": "9900",
            "low_price": "9900",
            "last_price": "9900",
            "last_qntt": "6",
            "vol": "343",
            "prev_diff_flag": "2",
            "prev_diff_price": "1700",
            "prev_diff_rate": "20.73"
        },
        {
            "data_date": "20240824",
            "data_time": "024417",
            "open_price": "10050",
            "high_price": "10050",
            "low_price": "10050",
            "last_price": "10050",
            "last_qntt": "6",
            "vol": "349",
            "prev_diff_flag": "2",
            "prev_diff_price": "1850",
            "prev_diff_rate": "22.56"
        },...
        {
            "data_date": "20240826",
            "data_time": "081707",
            "open_price": "10375",
            "high_price": "10375",
            "low_price": "10375",
            "last_price": "10375",
            "last_qntt": "1",
            "vol": "7",
            "prev_diff_flag": "5",
            "prev_diff_price": "-400",
            "prev_diff_rate": "-3.71"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 체결추이(일간)

- **TR_ID**: HHDFO55020100
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-daily-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 C5500
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:119
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0120",
        "last_n_cnt": "",
        "index_key": "20240308"
    },
    "output2": [
        {
            "data_date": "20240308",
            "data_time": "",
            "open_price": "           6600",
            "high_price": "           6675",
            "low_price": "           6600",
            "last_price": "           6675",
            "last_qntt": "",
            "vol": "        20",
            "prev_diff_flag": "2",
            "prev_diff_price": "            800",
            "prev_diff_rate": "     13.62"
        },
        {
            "data_date": "20240311",
            "data_time": "",
            "open_price": "           5075",
            "high_price": "           5100",
            "low_price": "           5000",
            "last_price": "           5100",
            "last_qntt": "",
            "vol": "        17",
            "prev_diff_flag": "5",
            "prev_diff_price": "           1575",
            "prev_diff_rate": "    -23.60"
        },
		...
        {
            "data_date": "20240909",
            "data_time": "",
            "open_price": "            400",
            "high_price": "            400",
            "low_price": "            385",
            "last_price": "            385",
            "last_qntt": "",
            "vol": "         2",
            "prev_diff_flag": "2",
            "prev_diff_price": "             50",
            "prev_diff_rate": "     14.93"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 체결추이(주간)

- **TR_ID**: HHDFO55020000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-weekly-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:100
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0052",
        "last_n_cnt": "",
        "index_key": ""
    },
    "output2": [
        {
            "data_date": "20221128",
            "data_time": "",
            "open_price": "           5525",
            "high_price": "           5550",
            "low_price": "           5525",
            "last_price": "           5525",
            "last_qntt": "",
            "vol": "       150",
            "prev_diff_flag": "5",
            "prev_diff_price": "            425",
            "prev_diff_rate": "     -7.14"
        },
        {
            "data_date": "20221219",
            "data_time": "",
            "open_price": "           3650",
            "high_price": "           3650",
            "low_price": "           3650",
            "last_price": "           3650",
            "last_qntt": "",
            "vol": "        25",
            "prev_diff_flag": "5",
            "prev_diff_price": "           1875",
            "prev_diff_rate": "    -33.94"
        },
        {
            "data_date": "20230102",
            "data_time": "",
            "open_price": "           2900",
            "high_price": "           2900",
            "low_price": "           2825",
            "last_price": "           2875",
            "last_qntt": "",
            "vol": "       225",
            "prev_diff_flag": "5",
            "prev_diff_price": "            775",
            "prev_diff_rate": "    -21.23"
        },
		...
        {
            "data_date": "20240909",
            "data_time": "",
            "open_price": "            900",
            "high_price": "            950",
            "low_price": "            900",
            "last_price": "            950",
            "last_qntt": "",
            "vol": "        26",
            "prev_diff_flag": "2",
            "prev_diff_price": "            145",
            "prev_diff_rate": "     18.01"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 체결추이(월간)

- **TR_ID**: HHDFO55020300
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-monthly-ccnl`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:20
QRY_GAP:
INDEX_KEY: |  |
| Response Example | {
    "output1": {
        "ret_cnt": "0016",
        "last_n_cnt": "",
        "index_key": ""
    },
    "output2": [
        {
            "data_date": "20221101",
            "data_time": "",
            "open_price": "5525",
            "high_price": "5550",
            "low_price": "5525",
            "last_price": "5525",
            "last_qntt": "",
            "vol": "150",
            "prev_diff_flag": "5",
            "prev_diff_price": "425",
            "prev_diff_rate": "-7.14"
        },
        {
            "data_date": "20221201",
            "data_time": "",
            "open_price": "3650",
            "high_price": "3650",
            "low_price": "3650",
            "last_price": "3650",
            "last_qntt": "",
            "vol": "25",
            "prev_diff_flag": "5",
            "prev_diff_price": "1875",
            "prev_diff_rate": "-33.94"
        },
        {
            "data_date": "20230101",
            "data_time": "",
            "open_price": "2900",
            "high_price": "2900",
            "low_price": "2825",
            "last_price": "2875",
            "last_qntt": "",
            "vol": "225",
            "prev_diff_flag": "5",
            "prev_diff_price": "775",
            "prev_diff_rate": "-21.23"
        },
        {
            "data_date": "20230901",
            "data_time": "",
            "open_price": "750",
            "high_price": "750",
            "low_price": "750",
            "last_price": "750",
            "last_qntt": "",
            "vol": "2",
            "prev_diff_flag": "5",
            "prev_diff_price": "2125",
            "prev_diff_rate": "-73.91"
        },
        {
            "data_date": "20231001",
            "data_time": "",
            "open_price": "630",
            "high_price": "645",
            "low_price": "320",
            "last_price": "330",
            "last_qntt": "",
            "vol": "357",
            "prev_diff_flag": "5",
            "prev_diff_price": "420",
            "prev_diff_rate": "-56.00"
        },
        {
            "data_date": "20231101",
            "data_time": "",
            "open_price": "360",
            "high_price": "815",
            "low_price": "360",
            "last_price": "800",
            "last_qntt": "",
            "vol": "1230",
            "prev_diff_flag": "2",
            "prev_diff_price": "470",
            "prev_diff_rate": "142.42"
        },
		...
        {
            "data_date": "20240901",
            "data_time": "",
            "open_price": "9400",
            "high_price": "10250",
            "low_price": "805",
            "last_price": "900",
            "last_qntt": "",
            "vol": "3985",
            "prev_diff_flag": "5",
            "prev_diff_price": "9000",
            "prev_diff_rate": "-90.91"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외옵션 상품기본정보

- **TR_ID**: HHDFO55200000
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/search-opt-detail`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | QRY_CNT:3
SRS_CD_01:OESU24 C5600
SRS_CD_02:OESU24 C5590
SRS_CD_03:OESU24 C5580 |  |
| Response Example | {
    "output2": [
        {
            "exch_cd": "CME",
            "clas_cd": "4",
            "crc_cd": "USD",
            "sttl_price": "          11000",
            "sttl_date": "20240826",
            "trst_mgn": "               7788",
            "disp_digit": "        10",
            "tick_sz": "                  0",
            "tick_val": "                2.5",
            "mrkt_open_date": "20240826",
            "mrkt_open_time": "000700",
            "mrkt_close_date": "20240827",
            "mrkt_close_time": "000600",
            "trd_fr_date": "20240610",
            "expr_date": "20240920",
            "trd_to_date": "20240920",
            "remn_cnt": "0026",
            "stat_tp": "",
            "ctrt_size": "                 50",
            "stl_tp": "현금결제",
            "frst_noti_date": ""
        },
        {
            "exch_cd": "CME",
            "clas_cd": "4",
            "crc_cd": "USD",
            "sttl_price": "          11675",
            "sttl_date": "20240826",
            "trst_mgn": "               7788",
            "disp_digit": "        10",
            "tick_sz": "                  0",
            "tick_val": "                2.5",
            "mrkt_open_date": "20240826",
            "mrkt_open_time": "000700",
            "mrkt_close_date": "20240827",
            "mrkt_close_time": "000600",
            "trd_fr_date": "20240610",
            "expr_date": "20240920",
            "trd_to_date": "20240920",
            "remn_cnt": "0026",
            "stat_tp": "",
            "ctrt_size": "                 50",
            "stl_tp": "현금결제",
            "frst_noti_date": ""
        },
        {
            "exch_cd": "CME",
            "clas_cd": "4",
            "crc_cd": "USD",
            "sttl_price": "          12400",
            "sttl_date": "20240826",
            "trst_mgn": "               7788",
            "disp_digit": "        10",
            "tick_sz": "                  0",
            "tick_val": "                2.5",
            "mrkt_open_date": "20240826",
            "mrkt_open_time": "000700",
            "mrkt_close_date": "20240827",
            "mrkt_close_time": "000600",
            "trd_fr_date": "20240718",
            "expr_date": "20240920",
            "trd_to_date": "20240920",
            "remn_cnt": "0026",
            "stat_tp": "",
            "ctrt_size": "                 50",
            "stl_tp": "현금결제",
            "frst_noti_date": ""
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 해외선물옵션 장운영시간

- **TR_ID**: OTFM2229R
- **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/market-time`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FM_PDGR_CD:
FM_CLAS_CD:
FM_EXCG_CD:CME
OPT_YN:%
CTX_AREA_NK200:
CTX_AREA_FK200: |  |
| Response Example | {
    "ctx_area_nk200": "CME^003^2ES^                                                                                                                                                                                            ",
    "ctx_area_fk200": "^CME^%^                                                                                                                                                                                                 ",
    "output": [
        {
            "fm_pdgr_cd": "6A",
            "fm_pdgr_name": "Australian Dollar",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6B",
            "fm_pdgr_name": "British pounds",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6C",
            "fm_pdgr_name": "Canadian Dollar",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6E",
            "fm_pdgr_name": "Euro FX",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6J",
            "fm_pdgr_name": "Japanese Yen",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6L",
            "fm_pdgr_name": "Brazilian Real",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6M",
            "fm_pdgr_name": "Mexican PESO",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6N",
            "fm_pdgr_name": "NewZealand Dollars",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6S",
            "fm_pdgr_name": "Swiss Franc",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "6Z",
            "fm_pdgr_name": "South African Rand",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "E7",
            "fm_pdgr_name": "E-mini Euro FX",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "J7",
            "fm_pdgr_name": "E-Mini YEN",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "M6A",
            "fm_pdgr_name": "E-micro AUD",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "M6B",
            "fm_pdgr_name": "E-micro GBP",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "M6E",
            "fm_pdgr_name": "E-micro EUR",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "MCD",
            "fm_pdgr_name": "E-micro CAD",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },
        {
            "fm_pdgr_cd": "MJY",
            "fm_pdgr_name": "E-micro JPY",
            "fm_excg_cd": "CME",
            "fm_excg_name": "Chicago Mercantile Exchange",
            "fuop_dvsn_name": "선물",
            "fm_clas_cd": "001",
            "fm_clas_name": "통화",
            "am_mkmn_strt_tmd": "070000",
            "am_mkmn_end_tmd": "060000",
            "pm_mkmn_strt_tmd": "",
            "pm_mkmn_end_tmd": "",
            "mkmn_nxdy_strt_tmd": "",
            "mkmn_nxdy_end_tmd": "",
            "base_mket_strt_tmd": "070000",
            "base_mket_end_tmd": "060000"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0500",
    "msg1": "조회가 계속됩니다..다음버튼을 Click 하십시오.                                   "
} |  |

