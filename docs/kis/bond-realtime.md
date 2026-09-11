# [장내채권] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (3개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 336 | WEBSOCKET | 일반채권 실시간체결가 | H0BJCNT0 | POST | `/tryitout/H0BJCNT0` |  |
| 337 | WEBSOCKET | 일반채권 실시간호가 | H0BJCNT0 | POST | `/tryitout/H0BJASP0` |  |
| 338 | WEBSOCKET | 채권지수 실시간체결가 | H0BICNT0 | POST | `/tryitout/H0BICNT0` |  |

---

## 상세 명세


### 일반채권 실시간체결가

- **API ID**: 실시간-052
- **실전 TR_ID**: H0BJCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0BJCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
일반채권 실시간체결가 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

채권 종목코드 마스터파일은 "포럼 &gt;  FAQ &gt; 종목정보 다운로드(국내) &gt; 장내채권 - 채권코드" 참고 부탁드립니다.

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0BJCNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 채권 종목코드 (ex. KR103502GA34) |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `STND_ISCD` | 표준종목코드 | string | Y | 12 |  |
| 1 | `BOND_ISNM` | 채권종목명 | string | Y | 80 |  |
| 2 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 8 |  |
| 5 | `PRDY_CTRT` | 전일대비율 | string | Y | 8 |  |
| 6 | `STCK_PRPR` | 현재가 | string | Y | 8 |  |
| 7 | `CNTG_VOL` | 체결거래량 | string | Y | 8 |  |
| 8 | `STCK_OPRC` | 시가 | string | Y | 8 |  |
| 9 | `STCK_HGPR` | 고가 | string | Y | 8 |  |
| 10 | `STCK_LWPR` | 저가 | string | Y | 8 |  |
| 11 | `STCK_PRDY_CLPR` | 전일종가 | string | Y | 8 |  |
| 12 | `BOND_CNTG_ERT` | 현재수익률 | string | Y | 10 |  |
| 13 | `OPRC_ERT` | 시가수익률 | string | Y | 10 |  |
| 14 | `HGPR_ERT` | 고가수익률 | string | Y | 10 |  |
| 15 | `LWPR_ERT` | 저가수익률 | string | Y | 10 |  |
| 16 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 17 | `PRDY_VOL` | 전일거래량 | string | Y | 8 |  |
| 18 | `CNTG_TYPE_CLS_CODE` | 체결유형코드 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0BJCNT0",
                           "tr_key":"KR103502GD31"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0BJCNT0", 
        "tr_key": "KR103502GD31", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output - 정제 전
0|H0BJCNT0|001|KR103502GD31^국고03250-5303(23-2)^131743^2^5.00^0.05^10575.00^1^10525.00^10578.00^10525.00^0.00^3.012^3.037^3.010^3.037^659
4124^9874082^2

# output - 정제 후
#### 장내채권 체결 ####
============================================
### [1 / 1]
표준종목코드       [KR103502GD31]
채권종목명        [국고03250-5303(23-2)]
주식체결시간       [131743]
전일대비부호       [2]
전일대비         [5.00]
전일대비율        [0.05]
현재가          [10575.00]
체결거래량        [1]
시가           [10525.00]
고가           [10578.00]
저가           [10525.00]
전일종가         [0.00]
현재수익률        [3.012]
시가수익률        [3.037]
고가수익률        [3.010]
저가수익률        [3.037]
누적거래량        [6594124]
전일거래량        [9874082]
체결유형코드       [2]
```

</details>



### 일반채권 실시간호가

- **API ID**: 실시간-053
- **실전 TR_ID**: H0BJCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0BJASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
일반채권 실시간호가 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

채권 종목코드 마스터파일은 "포럼 &gt;  FAQ &gt; 종목정보 다운로드(국내) &gt; 장내채권 - 채권코드" 참고 부탁드립니다.

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `custtype` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0BJCNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 채권 종목코드 (ex. KR103502GA34) |

#### Response Body (34)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `STND_ISCD` | 표준종목코드 | string | Y | 12 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `ASKP_ERT1` | 매도호가수익률 | string | Y | 10 |  |
| 3 | `BIDP_ERT1` | 매수호가수익률1 | string | Y | 10 |  |
| 4 | `ASKP1` | 매도호가1 | string | Y | 8 |  |
| 5 | `BIDP1` | 매수호가1 | string | Y | 8 |  |
| 6 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 7 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 8 | `ASKP_ERT2` | 매도호가수익률2 | string | Y | 10 |  |
| 9 | `BIDP_ERT2` | 매수호가수익률2 | string | Y | 10 |  |
| 10 | `ASKP2` | 매도호가2 | string | Y | 8 |  |
| 11 | `BIDP2` | 매수호가2 | string | Y | 8 |  |
| 12 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 8 |  |
| 13 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 8 |  |
| 14 | `ASKP_ERT3` | 매도호가수익률3 | string | Y | 10 |  |
| 15 | `BIDP_ERT3` | 매수호가수익률3 | string | Y | 10 |  |
| 16 | `ASKP3` | 매도호가3 | string | Y | 8 |  |
| 17 | `BIDP3` | 매수호가3 | string | Y | 8 |  |
| 18 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 8 |  |
| 19 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 8 |  |
| 20 | `ASKP_ERT4` | 매도호가수익률4 | string | Y | 10 |  |
| 21 | `BIDP_ERT4` | 매수호가수익률4 | string | Y | 10 |  |
| 22 | `ASKP4` | 매도호가4 | string | Y | 8 |  |
| 23 | `BIDP4` | 매수호가4 | string | Y | 8 |  |
| 24 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 8 |  |
| 25 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 8 |  |
| 26 | `ASKP_ERT5` | 매도호가수익률5 | string | Y | 10 |  |
| 27 | `BIDP_ERT5` | 매수호가수익률5 | string | Y | 10 |  |
| 28 | `ASKP5` | 매도호가5 | string | Y | 8 |  |
| 29 | `BIDP5` | 매수호가5 | string | Y | 8 |  |
| 30 | `ASKP_RSQN52` | 매도호가잔량5 | string | Y | 8 |  |
| 31 | `BIDP_RSQN53` | 매수호가잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 33 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0BJASP0",
                           "tr_key":"KR103502GD31"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0BJASP0", 
        "tr_key": "KR103502GD31", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output - 정제 전
0|H0BJASP0|001|KR103502GD31^131743^3.012^3.020^10575.00^10560.00^416090^323813^3.011^3.022^10576.00^10556.00^405284^57^3.010^3.022^10578.0
0^10555.00^177098^500000^3.009^3.024^10580.00^10551.00^97637^363079^3.001^3.025^10597.00^10550.00^80000^379920^1698609^4112382

# output - 정제 후
#### 장내채권 호가 ####
채권종목코드  [KR103502GD31]
영업시간  [131743]
====================================
채권매도호가1   [10575.00],    매도호가수익률1  [3.012],    매도호가잔량1      [416090]
채권매도호가2   [10576.00],    매도호가수익률2  [3.011],    매도호가잔량2      [405284]
채권매도호가3   [10578.00],    매도호가수익률3  [3.010],    매도호가잔량3      [177098]
채권매도호가4   [10580.00],    매도호가수익률4  [3.009],    매도호가잔량4      [97637]
채권매도호가5   [10597.00],    매도호가수익률5  [3.001],    매도호가잔량5      [80000]
채권매수호가1   [10560.00],    매수호가수익률1  [3.020],    매수호가잔량1      [323813]
채권매수호가2   [10556.00],    매수호가수익률2  [3.022],    매수호가잔량2      [57]
채권매수호가3   [10555.00],    매수호가수익률3  [3.022],    매수호가잔량3      [500000]
채권매수호가4   [10551.00],   매수호가수익률4   [3.024],    매수호가잔량4      [363079]
채권매수호가5   [10550.00],    매수호가수익률5  [3.025],    매수호가잔량5      [379920]
====================================
총매도호가잔량  [1698609]
총매수호가잔량  [4112382]
```

</details>



### 채권지수 실시간체결가

- **API ID**: 실시간-060
- **실전 TR_ID**: H0BICNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0BICNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
채권지수 실시간체결가 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

채권 종목코드 마스터파일은 "포럼 &gt; FAQ &gt; 종목정보 다운로드(국내) &gt; 장내채권 - 채권코드" 참고 부탁드립니다.

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0BICNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 채권 종목코드 (ex. KR103502GA34) |

#### Response Body (20)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `NMIX_ID` | 지수ID | string | Y | 6 |  |
| 1 | `STND_DATE1` | 기준일자1 | string | Y | 8 |  |
| 2 | `TRNM_HOUR` | 전송시간 | string | Y | 6 |  |
| 3 | `TOTL_ERNN_NMIX_OPRC` | 총수익지수시가지수 | string | Y | 1 |  |
| 4 | `TOTL_ERNN_NMIX_HGPR` | 총수익지수최고가 | string | Y | 1 |  |
| 5 | `TOTL_ERNN_NMIX_LWPR` | 총수익지수최저가 | string | Y | 1 |  |
| 6 | `TOTL_ERNN_NMIX` | 총수익지수 | string | Y | 1 |  |
| 7 | `PRDY_TOTL_ERNN_NMIX` | 전일총수익지수 | string | Y | 1 |  |
| 8 | `TOTL_ERNN_NMIX_PRDY_VRSS` | 총수익지수전일대비 | string | Y | 1 |  |
| 9 | `TOTL_ERNN_NMIX_PRDY_VRSS_SIGN` | 총수익지수전일대비부호 | string | Y | 1 |  |
| 10 | `TOTL_ERNN_NMIX_PRDY_CTRT` | 총수익지수전일대비율 | string | Y | 1 |  |
| 11 | `CLEN_PRC_NMIX` | 순가격지수 | string | Y | 1 |  |
| 12 | `MRKT_PRC_NMIX` | 시장가격지수 | string | Y | 1 |  |
| 13 | `BOND_CALL_RNVS_NMIX` | Call재투자지수 | string | Y | 1 |  |
| 14 | `BOND_ZERO_RNVS_NMIX` | Zero재투자지수 | string | Y | 1 |  |
| 15 | `BOND_FUTS_THPR` | 선물이론가격 | string | Y | 1 |  |
| 16 | `BOND_AVRG_DRTN_VAL` | 평균듀레이션 | string | Y | 1 |  |
| 17 | `BOND_AVRG_CNVX_VAL` | 평균컨벡서티 | string | Y | 1 |  |
| 18 | `BOND_AVRG_YTM_VAL` | 평균YTM | string | Y | 1 |  |
| 19 | `BOND_AVRG_FRDL_YTM_VAL` | 평균선도YTM | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0BICNT0",
                           "tr_key":"KBPR01"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0BICNT0", 
        "tr_key": "KBPR01", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output - 정제 전
0|H0BICNT0|001|KBPR01^20240726^131500^163.55^163.56^163.52^163.54^163.53^0.00^2^0.00^98.92^99.50^163.54^161.83^0.00^9.45^181.22^3.07^0.00

# output - 정제 후
#### 채권지수 체결 ####
============================================
### [1 / 1]
지수ID         [KBPR01]
기준일자1        [20240726]
전송시간         [131500]
총수익지수시가지수    [163.55]
총수익지수최고가     [163.56]
총수익지수최저가     [163.52]
총수익지수        [163.54]
전일총수익지수      [163.53]
총수익지수전일대비    [0.00]
총수익지수전일대비부호  [2]
총수익지수전일대비율   [0.00]
순가격지수        [98.92]
시장가격지수       [99.50]
Call재투자지수    [163.54]
Zero재투자지수    [161.83]
선물이론가격       [0.00]
평균듀레이션       [9.45]
평균컨벡서티       [181.22]
평균YTM        [3.07]
평균선도YTM      [0.00]
```

</details>


