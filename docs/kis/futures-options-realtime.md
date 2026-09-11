# [국내선물옵션] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (20개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 215 | WEBSOCKET | 주식옵션 실시간호가 | H0ZOASP0 | POST | `/tryitout/H0ZOASP0` |  |
| 216 | WEBSOCKET | 선물옵션 실시간체결통보 | H0IFCNI0 | POST | `/tryitout/H0IFCNI0` |  |
| 217 | WEBSOCKET | KRX야간선물 실시간종목체결 | H0MFCNT0 | POST | `/tryitout/H0MFCNT0` |  |
| 218 | WEBSOCKET | KRX야간선물 실시간호가 | H0MFASP0 | POST | `/tryitout/H0MFASP0` |  |
| 219 | WEBSOCKET | KRX야간옵션 실시간체결가 | H0EUCNT0 | POST | `/tryitout/H0EUCNT0` |  |
| 220 | WEBSOCKET | KRX야간옵션실시간예상체결 | H0EUANC0 | POST | `/tryitout/H0EUANC0` |  |
| 221 | WEBSOCKET | 지수선물 실시간체결가 | H0IFCNT0 | POST | `/tryitout/H0IFCNT0` |  |
| 222 | WEBSOCKET | 주식선물 실시간예상체결 | H0ZFANC0 | POST | `/tryitout/H0ZFANC0` |  |
| 223 | WEBSOCKET | KRX야간옵션실시간체결통보 | H0MFCNI0 | POST | `/tryitout/H0EUCNI0` |  |
| 224 | WEBSOCKET | KRX야간선물 실시간체결통보 | H0MFCNI0 | POST | `/tryitout/H0MFCNI0` |  |
| 225 | WEBSOCKET | 상품선물 실시간체결가 | H0CFCNT0 | POST | `/tryitout/H0CFCNT0` |  |
| 226 | WEBSOCKET | 지수선물 실시간호가 | H0IFASP0 | POST | `/tryitout/H0IFASP0` |  |
| 227 | WEBSOCKET | 지수옵션  실시간체결가 | H0IOCNT0 | POST | `/tryitout/H0IOCNT0` |  |
| 228 | WEBSOCKET | KRX야간옵션 실시간호가 | H0EUASP0 | POST | `/tryitout/H0EUASP0` |  |
| 229 | WEBSOCKET | 상품선물 실시간호가 | H0CFASP0 | POST | `/tryitout/H0CFASP0` |  |
| 230 | WEBSOCKET | 주식옵션 실시간예상체결 | H0ZOANC0 | POST | `/tryitout/H0ZOANC0` |  |
| 231 | WEBSOCKET | 주식선물 실시간호가 | H0ZFASP0 | POST | `/tryitout/H0ZFASP0` |  |
| 232 | WEBSOCKET | 주식옵션 실시간체결가 | H0ZOCNT0 | POST | `/tryitout/H0ZOCNT0` |  |
| 233 | WEBSOCKET | 지수옵션 실시간호가 | H0IOASP0 | POST | `/tryitout/H0IOASP0` |  |
| 234 | WEBSOCKET | 주식선물 실시간체결가 | H0ZFCNT0 | POST | `/tryitout/H0ZFCNT0` |  |

---

## 상세 명세


### 주식옵션 실시간호가

- **API ID**: 실시간-045
- **실전 TR_ID**: H0ZOASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZOASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0ZOASP0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (68)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `OPTN_ASKP1` | 옵션매도호가1 | string | Y | 8 |  |
| 3 | `OPTN_ASKP2` | 옵션매도호가2 | string | Y | 8 |  |
| 4 | `OPTN_ASKP3` | 옵션매도호가3 | string | Y | 8 |  |
| 5 | `OPTN_ASKP4` | 옵션매도호가4 | string | Y | 8 |  |
| 6 | `OPTN_ASKP5` | 옵션매도호가5 | string | Y | 8 |  |
| 7 | `OPTN_BIDP1` | 옵션매수호가1 | string | Y | 8 |  |
| 8 | `OPTN_BIDP2` | 옵션매수호가2 | string | Y | 8 |  |
| 9 | `OPTN_BIDP3` | 옵션매수호가3 | string | Y | 8 |  |
| 10 | `OPTN_BIDP4` | 옵션매수호가4 | string | Y | 8 |  |
| 11 | `OPTN_BIDP5` | 옵션매수호가5 | string | Y | 8 |  |
| 12 | `ASKP_CSNU1` | 매도호가건수1 | string | Y | 4 |  |
| 13 | `ASKP_CSNU2` | 매도호가건수2 | string | Y | 4 |  |
| 14 | `ASKP_CSNU3` | 매도호가건수3 | string | Y | 4 |  |
| 15 | `ASKP_CSNU4` | 매도호가건수4 | string | Y | 4 |  |
| 16 | `ASKP_CSNU5` | 매도호가건수5 | string | Y | 4 |  |
| 17 | `BIDP_CSNU1` | 매수호가건수1 | string | Y | 4 |  |
| 18 | `BIDP_CSNU2` | 매수호가건수2 | string | Y | 4 |  |
| 19 | `BIDP_CSNU3` | 매수호가건수3 | string | Y | 4 |  |
| 20 | `BIDP_CSNU4` | 매수호가건수4 | string | Y | 4 |  |
| 21 | `BIDP_CSNU5` | 매수호가건수5 | string | Y | 4 |  |
| 22 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 23 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 8 |  |
| 24 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 8 |  |
| 25 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 8 |  |
| 26 | `ASKP_RSQN5` | 매도호가잔량5 | string | Y | 8 |  |
| 27 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 28 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 8 |  |
| 29 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 8 |  |
| 30 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 8 |  |
| 31 | `BIDP_RSQN5` | 매수호가잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총매도호가건수 | string | Y | 4 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총매수호가건수 | string | Y | 4 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총매도호가잔량증감 | string | Y | 4 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총매수호가잔량증감 | string | Y | 4 |  |
| 38 | `OPTN_ASKP6` | 옵션매도호가6 | string | Y | 8 |  |
| 39 | `OPTN_ASKP7` | 옵션매도호가7 | string | Y | 8 |  |
| 40 | `OPTN_ASKP8` | 옵션매도호가8 | string | Y | 8 |  |
| 41 | `OPTN_ASKP9` | 옵션매도호가9 | string | Y | 8 |  |
| 42 | `OPTN_ASKP10` | 옵션매도호가10 | string | Y | 8 |  |
| 43 | `OPTN_BIDP6` | 옵션매수호가6 | string | Y | 8 |  |
| 44 | `OPTN_BIDP7` | 옵션매수호가7 | string | Y | 8 |  |
| 45 | `OPTN_BIDP8` | 옵션매수호가8 | string | Y | 8 |  |
| 46 | `OPTN_BIDP9` | 옵션매수호가9 | string | Y | 8 |  |
| 47 | `OPTN_BIDP10` | 옵션매수호가10 | string | Y | 8 |  |
| 48 | `ASKP_CSNU6` | 매도호가건수6 | string | Y | 4 |  |
| 49 | `ASKP_CSNU7` | 매도호가건수7 | string | Y | 4 |  |
| 50 | `ASKP_CSNU8` | 매도호가건수8 | string | Y | 4 |  |
| 51 | `ASKP_CSNU9` | 매도호가건수9 | string | Y | 4 |  |
| 52 | `ASKP_CSNU10` | 매도호가건수10 | string | Y | 4 |  |
| 53 | `BIDP_CSNU6` | 매수호가건수6 | string | Y | 4 |  |
| 54 | `BIDP_CSNU7` | 매수호가건수7 | string | Y | 4 |  |
| 55 | `BIDP_CSNU8` | 매수호가건수8 | string | Y | 4 |  |
| 56 | `BIDP_CSNU9` | 매수호가건수9 | string | Y | 4 |  |
| 57 | `BIDP_CSNU10` | 매수호가건수10 | string | Y | 4 |  |
| 58 | `ASKP_RSQN6` | 매도호가잔량6 | string | Y | 8 |  |
| 59 | `ASKP_RSQN7` | 매도호가잔량7 | string | Y | 8 |  |
| 60 | `ASKP_RSQN8` | 매도호가잔량8 | string | Y | 8 |  |
| 61 | `ASKP_RSQN9` | 매도호가잔량9 | string | Y | 8 |  |
| 62 | `ASKP_RSQN10` | 매도호가잔량10 | string | Y | 8 |  |
| 63 | `BIDP_RSQN6` | 매수호가잔량6 | string | Y | 8 |  |
| 64 | `BIDP_RSQN7` | 매수호가잔량7 | string | Y | 8 |  |
| 65 | `BIDP_RSQN8` | 매수호가잔량8 | string | Y | 8 |  |
| 66 | `BIDP_RSQN9` | 매수호가잔량9 | string | Y | 8 |  |
| 67 | `BIDP_RSQN10` | 매수호가잔량10 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0ZOASP0",
            "tr_key": "211V05059"
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
        "tr_id": "H0ZOASP0", 
        "tr_key": "211V05059", 
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

# output
0|H0ZOASP0|001|211V05059^091509^1140.00^1160.00^1200.00^1300.00^1400.00^1120
.00^1080.00^620.00^580.00^530.00^2^1^1^1^1^1^2^1^1^1^187^12^10^10^10^12^187^3^3^3^9^6^241^208^
0^0^1500.00^1520.00^1700.00^0.00^0.00^0.00^0.00^0.00^0.00^0.00^1^1^1^0^0^0^0^0^0^0^10^1^1^0^0^
0^0^0^0^0
```

</details>



### 선물옵션 실시간체결통보

- **API ID**: 실시간-012
- **실전 TR_ID**: H0IFCNI0
- **모의 TR_ID**: H0IFCNI9
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0IFCNI0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `ws://ops.koreainvestment.com:31000`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 2 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | [실전투자]<br>H0IFCNI0 : 실시간 선물옵션 체결통보<br>[모의투자]<br>H0IFCNI9 : 실시간 선물옵션 체결통보 |
| 1 | `tr_key` | 코드 | string | Y | 6 | 예:101S12 |

#### Response Body (22)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CUST_ID` | 고객 ID | array | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `ACNT_NO` | 계좌번호 | string | Y | 16 |  |
| 2 | `ODER_NO` | 주문번호 | string | Y | 1 |  |
| 3 | `OODER_NO` | 원주문번호 | string | Y | 8 |  |
| 4 | `SELN_BYOV_CLS` | 매도매수구분 | string | Y | 8 | 01:매도, 02매수 |
| 5 | `RCTF_CLS` | 정정구분 | string | Y | 8 |  |
| 6 | `ODER_KIND2` | 주문종류2 | string | Y | 8 | L: 주문접수통보, 0: 체결통보 |
| 7 | `STCK_SHRN_ISCD` | 주식 단축 종목코드 | string | Y | 8 |  |
| 8 | `CNTG_QTY` | 체결 수량 | string | Y | 8 |  |
| 9 | `CNTG_UNPR` | 체결단가 | string | Y | 8 |  |
| 10 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 8 |  |
| 11 | `RFUS_YN` | 거부여부 | string | Y | 8 |  |
| 12 | `CNTG_YN` | 체결여부 | string | Y | 8 | 1: 주문,정정,취소,거부 통보, 2 체결 |
| 13 | `ACPT_YN` | 접수여부 | string | Y | 8 | 1:주문접수, 2:확인, 3, 취소 |
| 14 | `BRNC_NO` | 지점번호 | string | Y | 8 |  |
| 15 | `ODER_QTY` | 주문수량 | string | Y | 8 |  |
| 16 | `ACNT_NAME` | 계좌명 | string | Y | 8 |  |
| 17 | `CNTG_ISNM` | 체결종목명 | string | Y | 8 |  |
| 18 | `ODER_COND` | 주문조건 | string | Y | 8 |  |
| 19 | `ORD_GRP` | 주문그룹ID | string | Y | 8 |  |
| 20 | `ORD_GRPSEQ` | 주문그룹SEQ | string | Y | 8 |  |
| 21 | `ORDER_PRC` | 주문가격 | string | Y | 8 |  |

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
                           "tr_id":"H0IFCNI0",
                           "tr_key":"HTS ID"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# output - 등록 성공 시
{
    "header": {
        "tr_id": "H0IFCNI0", 
        "tr_key": "HTS ID", 
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

# output (복호화 전) 
1|H0IFCNI0|001|vebQjGIHMgFhxfNfvebQjGIHMgFhxfNfvebQjGIHMgFhxfNfvebQj...hxfNf

# output (복호화 후)
#### 지수선물옵션 체결 통보 ####
고객ID  [abcd1234]
계좌번호  [1234567803]
주문번호  [0000001666]
원주문번호  []
매도매수구분  [02]
정정구분  [0]
주문종류  [0]
단축종목코드  [111V06]
체결수량  [0000000002]
체결단가  [007840000]
체결시간  [095835]
거부여부  [0]
체결여부  [2]
접수여부  [2]
지점번호  [00950]
주문수량  [000000000]
계좌명  [김한국]
체결종목명  [삼성전자   F 2]
주문조건  []
주문그룹ID  []
주문그룹SEQ  []
주문가격  [000000000]
```

</details>



### KRX야간선물 실시간종목체결

- **API ID**: 실시간-064
- **실전 TR_ID**: H0MFCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0MFCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0MFCNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 야간선물 종목코드 |

#### Response Body (49)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `FUTS_PRDY_VRSS` | 선물 전일 대비 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 1 | 1: 상한<br>2: 상승<br>3: 보합<br>4: 하한<br>5: 하락 |
| 4 | `FUTS_PRDY_CTRT` | 선물 전일 대비율 | string | Y | 1 |  |
| 5 | `FUTS_PRPR` | 선물 현재가 | string | Y | 1 |  |
| 6 | `FUTS_OPRC` | 선물 시가2 | string | Y | 1 |  |
| 7 | `FUTS_HGPR` | 선물 최고가 | string | Y | 1 |  |
| 8 | `FUTS_LWPR` | 선물 최저가 | string | Y | 1 |  |
| 9 | `LAST_CNQN` | 최종 거래량 | string | Y | 1 |  |
| 10 | `ACML_VOL` | 누적 거래량 | string | Y | 1 |  |
| 11 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 1 |  |
| 12 | `HTS_THPR` | HTS 이론가 | string | Y | 1 |  |
| 13 | `MRKT_BASIS` | 시장 베이시스 | string | Y | 1 |  |
| 14 | `DPRT` | 괴리율 | string | Y | 1 |  |
| 15 | `NMSC_FCTN_STPL_PRC` | 근월물 약정가 | string | Y | 1 |  |
| 16 | `FMSC_FCTN_STPL_PRC` | 원월물 약정가 | string | Y | 1 |  |
| 17 | `SPEAD_PRC` | 스프레드1 | string | Y | 1 |  |
| 18 | `HTS_OTST_STPL_QTY` | HTS 미결제 약정 수량 | string | Y | 1 |  |
| 19 | `OTST_STPL_QTY_ICDC` | 미결제 약정 수량 증감 | string | Y | 1 |  |
| 20 | `OPRC_HOUR` | 시가 시간 | string | Y | 6 |  |
| 21 | `OPRC_VRSS_PRPR_SIGN` | 시가2 대비 현재가 부호 | string | Y | 1 |  |
| 22 | `OPRC_VRSS_NMIX_PRPR` | 시가 대비 지수 현재가 | string | Y | 1 |  |
| 23 | `HGPR_HOUR` | 최고가 시간 | string | Y | 6 |  |
| 24 | `HGPR_VRSS_PRPR_SIGN` | 최고가 대비 현재가 부호 | string | Y | 1 |  |
| 25 | `HGPR_VRSS_NMIX_PRPR` | 최고가 대비 지수 현재가 | string | Y | 1 |  |
| 26 | `LWPR_HOUR` | 최저가 시간 | string | Y | 6 |  |
| 27 | `LWPR_VRSS_PRPR_SIGN` | 최저가 대비 현재가 부호 | string | Y | 1 |  |
| 28 | `LWPR_VRSS_NMIX_PRPR` | 최저가 대비 지수 현재가 | string | Y | 1 |  |
| 29 | `SHNU_RATE` | 매수2 비율 | string | Y | 1 |  |
| 30 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 31 | `ESDG` | 괴리도 | string | Y | 1 |  |
| 32 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제 약정 직전 수량 증감 | string | Y | 1 |  |
| 33 | `THPR_BASIS` | 이론 베이시스 | string | Y | 1 |  |
| 34 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 1 |  |
| 35 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 1 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 1 |  |
| 38 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 1 |  |
| 39 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 1 |  |
| 40 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 1 |  |
| 41 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 1 |  |
| 42 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 1 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 1 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 1 |  |
| 45 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 1 |  |
| 46 | `DYNM_MXPR` | 실시간상한가 | string | Y | 8 |  |
| 47 | `DYNM_LLAM` | 실시간하한가 | string | Y | 8 |  |
| 48 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0MFCNT0",
            "tr_key": "101V06"
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
        "tr_id": "H0MFCNT0", 
        "tr_key": "101V06", 
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

# output
0|H0MFCNT0|001|101V06^190215^0.75^2^0.20^367.30^367.10^367.60^367.05^2^1596^1465526
87^366.08^1.22^0.33^0.00^0.00^0.00^268223^0^000000^2^0.20^000000^5^-0.30^000000^2^0.25^0.49^96.31^1.2
2^0^0.00^367.35^367.30^0^0^345^358^13^813^783^0^0^0.00
```

</details>



### KRX야간선물 실시간호가

- **API ID**: 실시간-065
- **실전 TR_ID**: H0MFASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0MFASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0MFASP0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 야간선물 종목코드 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 8 |  |
| 3 | `FUTS_ASKP2` | 선물 매도호가2 | string | Y | 8 |  |
| 4 | `FUTS_ASKP3` | 선물 매도호가3 | string | Y | 8 |  |
| 5 | `FUTS_ASKP4` | 선물 매도호가4 | string | Y | 8 |  |
| 6 | `FUTS_ASKP5` | 선물 매도호가5 | string | Y | 8 |  |
| 7 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 8 |  |
| 8 | `FUTS_BIDP2` | 선물 매수호가2 | string | Y | 8 |  |
| 9 | `FUTS_BIDP3` | 선물 매수호가3 | string | Y | 8 |  |
| 10 | `FUTS_BIDP4` | 선물 매수호가4 | string | Y | 8 |  |
| 11 | `FUTS_BIDP5` | 선물 매수호가5 | string | Y | 8 |  |
| 12 | `ASKP_CSNU1` | 매도호가 건수1 | string | Y | 4 |  |
| 13 | `ASKP_CSNU2` | 매도호가 건수2 | string | Y | 4 |  |
| 14 | `ASKP_CSNU3` | 매도호가 건수3 | string | Y | 4 |  |
| 15 | `ASKP_CSNU4` | 매도호가 건수4 | string | Y | 4 |  |
| 16 | `ASKP_CSNU5` | 매도호가 건수5 | string | Y | 4 |  |
| 17 | `BIDP_CSNU1` | 매수호가 건수1 | string | Y | 4 |  |
| 18 | `BIDP_CSNU2` | 매수호가 건수2 | string | Y | 4 |  |
| 19 | `BIDP_CSNU3` | 매수호가 건수3 | string | Y | 4 |  |
| 20 | `BIDP_CSNU4` | 매수호가 건수4 | string | Y | 4 |  |
| 21 | `BIDP_CSNU5` | 매수호가 건수5 | string | Y | 4 |  |
| 22 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 23 | `ASKP_RSQN2` | 매도호가 잔량2 | string | Y | 8 |  |
| 24 | `ASKP_RSQN3` | 매도호가 잔량3 | string | Y | 8 |  |
| 25 | `ASKP_RSQN4` | 매도호가 잔량4 | string | Y | 8 |  |
| 26 | `ASKP_RSQN5` | 매도호가 잔량5 | string | Y | 8 |  |
| 27 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 28 | `BIDP_RSQN2` | 매수호가 잔량2 | string | Y | 8 |  |
| 29 | `BIDP_RSQN3` | 매수호가 잔량3 | string | Y | 8 |  |
| 30 | `BIDP_RSQN4` | 매수호가 잔량4 | string | Y | 8 |  |
| 31 | `BIDP_RSQN5` | 매수호가 잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총 매도호가 건수 | string | Y | 4 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총 매수호가 건수 | string | Y | 4 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | string | Y | 4 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | string | Y | 4 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0MFASP0",
            "tr_key": "101V06"
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
        "tr_id": "H0MFASP0", 
        "tr_key": "101V06", 
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

# output
0|H0MFASP0|001|101V06^190215^367.35^367.40^367.45^0.00^0.00^367.30^367.25^367.20^0.
00^0.00^0^0^0^0^0^0^0^0^0^0^24^21^21^0^0^2^28^20^0^0^0^0^0^0^^0^0^0^0^0^^000000^2^
```

</details>



### KRX야간옵션 실시간체결가

- **API ID**: 실시간-032
- **실전 TR_ID**: H0EUCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EUCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EUCNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 야간옵션 종목코드 |

#### Response Body (56)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `OPTN_PRPR` | 옵션현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `OPTN_PRDY_VRSS` | 옵션전일대비 | string | Y | 1 |  |
| 5 | `PRDY_CTRT` | 전일대비율 | string | Y | 1 |  |
| 6 | `OPTN_OPRC` | 옵션시가2 | string | Y | 1 |  |
| 7 | `OPTN_HGPR` | 옵션최고가 | string | Y | 1 |  |
| 8 | `OPTN_LWPR` | 옵션최저가 | string | Y | 1 |  |
| 9 | `LAST_CNQN` | 최종거래량 | string | Y | 1 |  |
| 10 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 11 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 1 |  |
| 12 | `HTS_THPR` | HTS이론가 | string | Y | 1 |  |
| 13 | `HTS_OTST_STPL_QTY` | HTS미결제약정수량 | string | Y | 1 |  |
| 14 | `OTST_STPL_QTY_ICDC` | 미결제약정수량증감 | string | Y | 1 |  |
| 15 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 16 | `OPRC_VRSS_PRPR_SIGN` | 시가2대비현재가부호 | string | Y | 1 |  |
| 17 | `OPRC_VRSS_NMIX_PRPR` | 시가대비지수현재가 | string | Y | 1 |  |
| 18 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 19 | `HGPR_VRSS_PRPR_SIGN` | 최고가대비현재가부호 | string | Y | 1 |  |
| 20 | `HGPR_VRSS_NMIX_PRPR` | 최고가대비지수현재가 | string | Y | 1 |  |
| 21 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 22 | `LWPR_VRSS_PRPR_SIGN` | 최저가대비현재가부호 | string | Y | 1 |  |
| 23 | `LWPR_VRSS_NMIX_PRPR` | 최저가대비지수현재가 | string | Y | 1 |  |
| 24 | `SHNU_RATE` | 매수2비율 | string | Y | 1 |  |
| 25 | `PRMM_VAL` | 프리미엄값 | string | Y | 1 |  |
| 26 | `INVL_VAL` | 내재가치값 | string | Y | 1 |  |
| 27 | `TMVL_VAL` | 시간가치값 | string | Y | 1 |  |
| 28 | `DELTA` | 델타 | string | Y | 1 |  |
| 29 | `GAMA` | 감마 | string | Y | 1 |  |
| 30 | `VEGA` | 베가 | string | Y | 1 |  |
| 31 | `THETA` | 세타 | string | Y | 1 |  |
| 32 | `RHO` | 로우 | string | Y | 1 |  |
| 33 | `HTS_INTS_VLTL` | HTS내재변동성 | string | Y | 1 |  |
| 34 | `ESDG` | 괴리도 | string | Y | 1 |  |
| 35 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제약정직전수량증감 | string | Y | 1 |  |
| 36 | `THPR_BASIS` | 이론베이시스 | string | Y | 1 |  |
| 37 | `UNAS_HIST_VLTL` | 역사적변동성 | string | Y | 1 |  |
| 38 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 39 | `DPRT` | 괴리율 | string | Y | 1 |  |
| 40 | `MRKT_BASIS` | 시장베이시스 | string | Y | 1 |  |
| 41 | `OPTN_ASKP1` | 옵션매도호가1 | string | Y | 1 |  |
| 42 | `OPTN_BIDP1` | 옵션매수호가1 | string | Y | 1 |  |
| 43 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 44 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 45 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 1 |  |
| 46 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 1 |  |
| 47 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 1 |  |
| 48 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 1 |  |
| 49 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 1 |  |
| 50 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 51 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 52 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 1 |  |
| 53 | `DYNM_MXPR` | 실시간상한가 | string | Y | 8 |  |
| 54 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 1 |  |
| 55 | `DYNM_LLAM` | 실시간하한가 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0EUCNT0",
            "tr_key": "301V06362"
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
        "tr_id": "H0EUCNT0", 
        "tr_key": "301V06362", 
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

# output
0|H0EUCNT0|001|301V06362^190612^2.98^5^-0.35^-10.51^3.06^3.09^2.98^1^106^0^-nan^0^0
^000000^5^-0.08^000000^5^-0.11^000000^3^0.00^0.25^0.00^0.00^2.98^-nan^-nan^-nan^nan^-nan^84.55^-nan^0
^-nan^nan^32.50^-nan^-363.10^3.00^2.98^15^1^33^18^-15^80^26^37^27^0.00

# output - 복호화 후
#### 야간옵션(EUREX) 체결 ####
============================================
### [1 / 1]
옵션단축종목코드     [301V06362]
영업시간         [190612]
옵션현재가        [2.98]
전일대비부호       [5]
옵션전일대비       [-0.35]
전일대비율        [-10.51]
옵션시가2        [3.06]
옵션최고가        [3.09]
옵션최저가        [2.98]
최종거래량        [1]
누적거래량        [106]
누적거래대금       [0]
HTS이론가       [-nan]
HTS미결제약정수량   [0]
미결제약정수량증감    [0]
시가시간         [000000]
시가2대비현재가부호   [5]
시가대비지수현재가    [-0.08]
최고가시간        [000000]
최고가대비현재가부호   [5]
최고가대비지수현재가   [-0.11]
최저가시간        [000000]
최저가대비현재가부호   [3]
최저가대비지수현재가   [0.00]
매수2비율        [0.25]
프리미엄값        [0.00]
내재가치값        [0.00]
시간가치값        [2.98]
델타           [-nan]
감마           [-nan]
베가           [-nan]
세타           [nan]
로우           [-nan]
HTS내재변동성     [84.55]
괴리도          [-nan]
미결제약정직전수량증감  [0]
이론베이시스       [-nan]
역사적변동성       [nan]
체결강도         [32.50]
괴리율          [-nan]
시장베이시스       [-363.10]
옵션매도호가1      [3.00]
옵션매수호가1      [2.98]
매도호가잔량1      [15]
매수호가잔량1      [1]
매도체결건수       [33]
매수체결건수       [18]
순매수체결건수      [-15]
총매도수량        [80]
총매수수량        [26]
총매도호가잔량      [37]
총매수호가잔량      [27]
전일거래량대비등락율   [0.00]
```

</details>



### KRX야간옵션실시간예상체결

- **API ID**: 실시간-034
- **실전 TR_ID**: H0EUANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EUANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EUANC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 야간옵션 종목코드 |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `ANTC_CNPR` | 예상체결가 | string | Y | 8 |  |
| 3 | `ANTC_CNTG_VRSS` | 예상체결대비 | string | Y | 8 |  |
| 4 | `ANTC_CNTG_VRSS_SIGN` | 예상체결대비부호 | string | Y | 1 |  |
| 5 | `ANTC_CNTG_PRDY_CTRT` | 예상체결전일대비율 | string | Y | 8 |  |
| 6 | `ANTC_MKOP_CLS_CODE` | 예상장운영구분코드 | string | Y | 3 |  |
| 7 | `ANTC_CNQN` | 예상체결수량 | number | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0EUANC0",
            "tr_key": "301V06362"
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
        "tr_id": "H0EUANC0", 
        "tr_key": "301V06362", 
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

# output
```

</details>



### 지수선물 실시간체결가

- **API ID**: 실시간-010
- **실전 TR_ID**: H0IFCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0IFCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0IFCNT0 |
| 1 | `tr_key` | 코드 | string | Y | 6 | 예:101S12 |

#### Response Body (50)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | object | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 16 |  |
| 2 | `FUTS_PRDY_VRSS` | 선물 전일 대비 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 8 |  |
| 4 | `FUTS_PRDY_CTRT` | 선물 전일 대비율 | string | Y | 8 |  |
| 5 | `FUTS_PRPR` | 선물 현재가 | string | Y | 8 |  |
| 6 | `FUTS_OPRC` | 선물 시가2 | string | Y | 8 |  |
| 7 | `FUTS_HGPR` | 선물 최고가 | string | Y | 8 |  |
| 8 | `FUTS_LWPR` | 선물 최저가 | string | Y | 8 |  |
| 9 | `LAST_CNQN` | 최종 거래량 | string | Y | 8 | 체결량 |
| 10 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 11 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 8 |  |
| 12 | `HTS_THPR` | HTS 이론가 | string | Y | 8 |  |
| 13 | `MRKT_BASIS` | 시장 베이시스 | string | Y | 8 |  |
| 14 | `DPRT` | 괴리율 | string | Y | 8 |  |
| 15 | `NMSC_FCTN_STPL_PRC` | 근월물 약정가 | string | Y | 8 |  |
| 16 | `FMSC_FCTN_STPL_PRC` | 원월물 약정가 | string | Y | 8 |  |
| 17 | `SPEAD_PRC` | 스프레드1 | string | Y | 8 |  |
| 18 | `HTS_OTST_STPL_QTY` | HTS 미결제 약정 수량 | string | Y | 8 |  |
| 19 | `OTST_STPL_QTY_ICDC` | 미결제 약정 수량 증감 | string | Y | 8 |  |
| 20 | `OPRC_HOUR` | 시가 시간 | string | Y | 8 |  |
| 21 | `OPRC_VRSS_PRPR_SIGN` | 시가2 대비 현재가 부호 | string | Y | 8 |  |
| 22 | `OPRC_VRSS_NMIX_PRPR` | 시가 대비 지수 현재가 | string | Y | 8 |  |
| 23 | `HGPR_HOUR` | 최고가 시간 | string | Y | 8 |  |
| 24 | `HGPR_VRSS_PRPR_SIGN` | 최고가 대비 현재가 부호 | string | Y | 8 |  |
| 25 | `HGPR_VRSS_NMIX_PRPR` | 최고가 대비 지수 현재가 | string | Y | 8 |  |
| 26 | `LWPR_HOUR` | 최저가 시간 | string | Y | 8 |  |
| 27 | `LWPR_VRSS_PRPR_SIGN` | 최저가 대비 현재가 부호 | string | Y | 8 |  |
| 28 | `LWPR_VRSS_NMIX_PRPR` | 최저가 대비 지수 현재가 | string | Y | 8 |  |
| 29 | `SHNU_RATE` | 매수2 비율 | string | Y | 8 |  |
| 30 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 31 | `ESDG` | 괴리도 | string | Y | 8 |  |
| 32 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제 약정 직전 수량 증감 | string | Y | 8 |  |
| 33 | `THPR_BASIS` | 이론 베이시스 | string | Y | 8 |  |
| 34 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 8 |  |
| 35 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 8 |  |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 38 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 6 |  |
| 39 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 6 |  |
| 40 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 6 |  |
| 41 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 6 |  |
| 42 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 6 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 6 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 6 |  |
| 45 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 6 |  |
| 46 | `DSCS_BLTR_ACML_QTY` | 협의 대량 거래량 | string | Y | 6 |  |
| 47 | `DYNM_MXPR` | 실시간상한가 | string | Y | 8 |  |
| 48 | `DYNM_LLAM` | 실시간하한가 | string | Y | 6 |  |
| 49 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 10 |  |


### 주식선물 실시간예상체결

- **API ID**: 실시간-031
- **실전 TR_ID**: H0ZFANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZFANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0ZFANC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 주식선물 종목코드 |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `ANTC_CNPR` | 예상체결가 | string | Y | 8 |  |
| 3 | `ANTC_CNTG_VRSS` | 예상체결대비 | string | Y | 8 |  |
| 4 | `ANTC_CNTG_VRSS_SIGN` | 예상체결대비부호 | string | Y | 1 |  |
| 5 | `ANTC_CNTG_PRDY_CTRT` | 예상체결전일대비율 | string | Y | 8 |  |
| 6 | `ANTC_MKOP_CLS_CODE` | 예상장운영구분코드 | string | Y | 3 |  |
| 7 | `ANTC_CNQN` | 예상체결수량 | string | Y | 8 |  |


### KRX야간옵션실시간체결통보

- **API ID**: 실시간-067
- **실전 TR_ID**: H0MFCNI0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EUCNI0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0MFCNI0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | HTS ID |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CUST_ID` | 고객 ID | string | Y | 8 |  |
| 1 | `ACNT_NO` | 계좌번호 | string | Y | 10 |  |
| 2 | `ODER_NO` | 주문번호 | string | Y | 10 |  |
| 3 | `OODER_NO` | 원주문번호 | string | Y | 10 |  |
| 4 | `SELN_BYOV_CLS` | 매도매수구분 | string | Y | 2 |  |
| 5 | `RCTF_CLS` | 정정구분 | string | Y | 1 |  |
| 6 | `ODER_KIND2` | 주문종류2 | string | Y | 1 |  |
| 7 | `STCK_SHRN_ISCD` | 주식 단축 종목코드 | string | Y | 9 |  |
| 8 | `CNTG_QTY` | 체결 수량 | string | Y | 10 |  |
| 9 | `CNTG_UNPR` | 체결단가 | string | Y | 9 |  |
| 10 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 11 | `RFUS_YN` | 거부여부 | string | Y | 1 |  |
| 12 | `CNTG_YN` | 체결여부 | string | Y | 1 |  |
| 13 | `ACPT_YN` | 접수여부 | string | Y | 1 |  |
| 14 | `BRNC_NO` | 지점번호 | string | Y | 5 |  |
| 15 | `ODER_QTY` | 주문수량 | string | Y | 9 |  |
| 16 | `ACNT_NAME` | 계좌명 | string | Y | 12 |  |
| 17 | `CNTG_ISNM` | 체결종목명 | string | Y | 14 |  |
| 18 | `ODER_COND` | 주문조건 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0EUCNI0",
            "tr_key": "HTS_ID"
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
        "tr_id": "H0EUCNI0", 
        "tr_key": "HTS_ID", 
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

# output
1|H0EUCNI0|001|qWVvLmhf0Iax57SI6HYSTc30qiWTnUjWAT+BxQD4RaljIiBLp3XqzoA0eeEFa7yn8afB
Ufvo32b/Ivf9rxtl1VZU+oouQlH9rwuNjUnC40gkB+2lm2Q8sTkc4wMYKJuOn8SnLrfGjilAIzueLOLCndSy5xkv4qmPAXk+NKC6x
nimfxBoVTVtcrpzOaHPvwvD

# output - 복호화 후
#### 국내선물옵션 주문 접수 통보 ####
고객ID  [HTS_ID]
계좌번호  [1234567803]
주문번호  [0000000021]
원주문번호  [0000000021]
매도매수구분  [02]
정정구분  [0]
주문종류  [L]
단축종목코드  [175V06]
주문수량  [0000000001]
체결단가  [000135900]
체결시간  [100422]
거부여부  [0]
체결여부  [1]
접수여부  [1]
지점번호  [00000]
체결수량  [000000001]
계좌명  [******]
체결종목명  [미국달러F2406]
주문조건  [0]
```

</details>



### KRX야간선물 실시간체결통보

- **API ID**: 실시간-066
- **실전 TR_ID**: H0MFCNI0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0MFCNI0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0MFCNI0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | HTS ID |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CUST_ID` | 고객 ID | string | Y | 8 |  |
| 1 | `ACNT_NO` | 계좌번호 | string | Y | 10 |  |
| 2 | `ODER_NO` | 주문번호 | string | Y | 10 |  |
| 3 | `OODER_NO` | 원주문번호 | string | Y | 10 |  |
| 4 | `SELN_BYOV_CLS` | 매도매수구분 | string | Y | 2 |  |
| 5 | `RCTF_CLS` | 정정구분 | string | Y | 1 |  |
| 6 | `ODER_KIND2` | 주문종류2 | string | Y | 1 |  |
| 7 | `STCK_SHRN_ISCD` | 주식 단축 종목코드 | string | Y | 9 |  |
| 8 | `CNTG_QTY` | 체결 수량 | string | Y | 10 |  |
| 9 | `CNTG_UNPR` | 체결단가 | string | Y | 9 |  |
| 10 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 11 | `RFUS_YN` | 거부여부 | string | Y | 1 |  |
| 12 | `CNTG_YN` | 체결여부 | string | Y | 1 |  |
| 13 | `ACPT_YN` | 접수여부 | string | Y | 1 |  |
| 14 | `BRNC_NO` | 지점번호 | string | Y | 5 |  |
| 15 | `ODER_QTY` | 주문수량 | string | Y | 9 |  |
| 16 | `ACNT_NAME` | 계좌명 | string | Y | 12 |  |
| 17 | `CNTG_ISNM` | 체결종목명 | string | Y | 14 |  |
| 18 | `ODER_COND` | 주문조건 | string | Y | 1 |  |


### 상품선물 실시간체결가

- **API ID**: 실시간-022
- **실전 TR_ID**: H0CFCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0CFCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0CFCNT0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (50)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | object | Y | 32 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 9 |  |
| 2 | `FUTS_PRDY_VRSS` | 선물 전일 대비 | string | Y | 6 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 8 |  |
| 4 | `FUTS_PRDY_CTRT` | 선물 전일 대비율 | string | Y | 1 |  |
| 5 | `FUTS_PRPR` | 선물 현재가 | string | Y | 8 |  |
| 6 | `FUTS_OPRC` | 선물 시가2 | string | Y | 8 |  |
| 7 | `FUTS_HGPR` | 선물 최고가 | string | Y | 8 |  |
| 8 | `FUTS_LWPR` | 선물 최저가 | string | Y | 8 |  |
| 9 | `LAST_CNQN` | 최종 거래량 | string | Y | 8 |  |
| 10 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 11 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 8 |  |
| 12 | `HTS_THPR` | HTS 이론가 | string | Y | 8 |  |
| 13 | `MRKT_BASIS` | 시장 베이시스 | string | Y | 8 |  |
| 14 | `DPRT` | 괴리율 | string | Y | 8 |  |
| 15 | `NMSC_FCTN_STPL_PRC` | 근월물 약정가 | string | Y | 8 |  |
| 16 | `FMSC_FCTN_STPL_PRC` | 원월물 약정가 | string | Y | 8 |  |
| 17 | `SPEAD_PRC` | 스프레드1 | string | Y | 8 |  |
| 18 | `HTS_OTST_STPL_QTY` | HTS 미결제 약정 수량 | string | Y | 8 |  |
| 19 | `OTST_STPL_QTY_ICDC` | 미결제 약정 수량 증감 | string | Y | 8 |  |
| 20 | `OPRC_HOUR` | 시가 시간 | string | Y | 4 |  |
| 21 | `OPRC_VRSS_PRPR_SIGN` | 시가2 대비 현재가 부호 | string | Y | 6 |  |
| 22 | `OPRC_VRSS_NMIX_PRPR` | 시가 대비 지수 현재가 | string | Y | 1 |  |
| 23 | `HGPR_HOUR` | 최고가 시간 | string | Y | 8 |  |
| 24 | `HGPR_VRSS_PRPR_SIGN` | 최고가 대비 현재가 부호 | string | Y | 6 |  |
| 25 | `HGPR_VRSS_NMIX_PRPR` | 최고가 대비 지수 현재가 | string | Y | 1 |  |
| 26 | `LWPR_HOUR` | 최저가 시간 | string | Y | 8 |  |
| 27 | `LWPR_VRSS_PRPR_SIGN` | 최저가 대비 현재가 부호 | string | Y | 6 |  |
| 28 | `LWPR_VRSS_NMIX_PRPR` | 최저가 대비 지수 현재가 | string | Y | 1 |  |
| 29 | `SHNU_RATE` | 매수2 비율 | string | Y | 8 |  |
| 30 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 31 | `ESDG` | 괴리도 | string | Y | 8 |  |
| 32 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제 약정 직전 수량 증감 | string | Y | 8 |  |
| 33 | `THPR_BASIS` | 이론 베이시스 | string | Y | 4 |  |
| 34 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 8 |  |
| 35 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 8 |  |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 38 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 8 |  |
| 39 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 4 |  |
| 40 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 4 |  |
| 41 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 4 |  |
| 42 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 8 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 45 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 8 |  |
| 46 | `DSCS_BLTR_ACML_QTY` | 협의 대량 거래량 | string | Y | 8 |  |
| 47 | `DYNM_MXPR` | 실시간상한가 | string | Y | 8 |  |
| 48 | `DYNM_LLAM` | 실시간하한가 | string | Y | 8 |  |
| 49 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 8 |  |


### 지수선물 실시간호가

- **API ID**: 실시간-011
- **실전 TR_ID**: H0IFASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0IFASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 2 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0IFASP0 |
| 1 | `tr_key` | 코드 | string | Y | 6 | 예:101S12 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | object | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 16 |  |
| 2 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 1 |  |
| 3 | `FUTS_ASKP2` | 선물 매도호가2 | string | Y | 8 |  |
| 4 | `FUTS_ASKP3` | 선물 매도호가3 | string | Y | 8 |  |
| 5 | `FUTS_ASKP4` | 선물 매도호가4 | string | Y | 8 |  |
| 6 | `FUTS_ASKP5` | 선물 매도호가5 | string | Y | 8 |  |
| 7 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 8 |  |
| 8 | `FUTS_BIDP2` | 선물 매수호가2 | string | Y | 8 |  |
| 9 | `FUTS_BIDP3` | 선물 매수호가3 | string | Y | 8 |  |
| 10 | `FUTS_BIDP4` | 선물 매수호가4 | string | Y | 8 |  |
| 11 | `FUTS_BIDP5` | 선물 매수호가5 | string | Y | 8 |  |
| 12 | `ASKP_CSNU1` | 매도호가 건수1 | string | Y | 8 |  |
| 13 | `ASKP_CSNU2` | 매도호가 건수2 | string | Y | 8 |  |
| 14 | `ASKP_CSNU3` | 매도호가 건수3 | string | Y | 8 |  |
| 15 | `ASKP_CSNU4` | 매도호가 건수4 | string | Y | 8 |  |
| 16 | `ASKP_CSNU5` | 매도호가 건수5 | string | Y | 8 |  |
| 17 | `BIDP_CSNU1` | 매수호가 건수1 | string | Y | 8 |  |
| 18 | `BIDP_CSNU2` | 매수호가 건수2 | string | Y | 8 |  |
| 19 | `BIDP_CSNU3` | 매수호가 건수3 | string | Y | 8 |  |
| 20 | `BIDP_CSNU4` | 매수호가 건수4 | string | Y | 8 |  |
| 21 | `BIDP_CSNU5` | 매수호가 건수5 | string | Y | 8 |  |
| 22 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 23 | `ASKP_RSQN2` | 매도호가 잔량2 | string | Y | 8 |  |
| 24 | `ASKP_RSQN3` | 매도호가 잔량3 | string | Y | 8 |  |
| 25 | `ASKP_RSQN4` | 매도호가 잔량4 | string | Y | 8 |  |
| 26 | `ASKP_RSQN5` | 매도호가 잔량5 | string | Y | 8 |  |
| 27 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 28 | `BIDP_RSQN2` | 매수호가 잔량2 | string | Y | 8 |  |
| 29 | `BIDP_RSQN3` | 매수호가 잔량3 | string | Y | 8 |  |
| 30 | `BIDP_RSQN4` | 매수호가 잔량4 | string | Y | 8 |  |
| 31 | `BIDP_RSQN5` | 매수호가 잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총 매도호가 건수 | string | Y | 8 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총 매수호가 건수 | string | Y | 8 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | string | Y | 8 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | string | Y | 8 |  |


### 지수옵션  실시간체결가

- **API ID**: 실시간-014
- **실전 TR_ID**: H0IOCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0IOCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0IOCNT0 |
| 1 | `tr_key` | 코드 | string | Y | 6 | 예:201S11305 |

#### Response Body (58)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션 단축 종목코드 | object | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 16 |  |
| 2 | `OPTN_PRPR` | 옵션 현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 8 |  |
| 4 | `OPTN_PRDY_VRSS` | 옵션 전일 대비 | string | Y | 8 |  |
| 5 | `PRDY_CTRT` | 전일 대비율 | string | Y | 8 |  |
| 6 | `OPTN_OPRC` | 옵션 시가2 | string | Y | 8 |  |
| 7 | `OPTN_HGPR` | 옵션 최고가 | string | Y | 8 |  |
| 8 | `OPTN_LWPR` | 옵션 최저가 | string | Y | 8 |  |
| 9 | `LAST_CNQN` | 최종 거래량 | string | Y | 8 |  |
| 10 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 11 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 8 |  |
| 12 | `HTS_THPR` | HTS 이론가 | string | Y | 8 |  |
| 13 | `HTS_OTST_STPL_QTY` | HTS 미결제 약정 수량 | string | Y | 8 |  |
| 14 | `OTST_STPL_QTY_ICDC` | 미결제 약정 수량 증감 | string | Y | 8 |  |
| 15 | `OPRC_HOUR` | 시가 시간 | string | Y | 8 |  |
| 16 | `OPRC_VRSS_PRPR_SIGN` | 시가2 대비 현재가 부호 | string | Y | 8 |  |
| 17 | `OPRC_VRSS_NMIX_PRPR` | 시가 대비 지수 현재가 | string | Y | 8 |  |
| 18 | `HGPR_HOUR` | 최고가 시간 | string | Y | 8 |  |
| 19 | `HGPR_VRSS_PRPR_SIGN` | 최고가 대비 현재가 부호 | string | Y | 8 |  |
| 20 | `HGPR_VRSS_NMIX_PRPR` | 최고가 대비 지수 현재가 | string | Y | 8 |  |
| 21 | `LWPR_HOUR` | 최저가 시간 | string | Y | 8 |  |
| 22 | `LWPR_VRSS_PRPR_SIGN` | 최저가 대비 현재가 부호 | string | Y | 8 |  |
| 23 | `LWPR_VRSS_NMIX_PRPR` | 최저가 대비 지수 현재가 | string | Y | 8 |  |
| 24 | `SHNU_RATE` | 매수2 비율 | string | Y | 8 |  |
| 25 | `PRMM_VAL` | 프리미엄 값 | string | Y | 8 |  |
| 26 | `INVL_VAL` | 내재가치 값 | string | Y | 8 |  |
| 27 | `TMVL_VAL` | 시간가치 값 | string | Y | 8 |  |
| 28 | `DELTA` | 델타 | string | Y | 8 |  |
| 29 | `GAMA` | 감마 | string | Y | 8 |  |
| 30 | `VEGA` | 베가 | string | Y | 8 |  |
| 31 | `THETA` | 세타 | string | Y | 8 |  |
| 32 | `RHO` | 로우 | string | Y | 8 |  |
| 33 | `HTS_INTS_VLTL` | HTS 내재 변동성 | string | Y | 8 |  |
| 34 | `ESDG` | 괴리도 | string | Y | 8 |  |
| 35 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제 약정 직전 수량 증감 | string | Y | 8 |  |
| 36 | `THPR_BASIS` | 이론 베이시스 | string | Y | 8 |  |
| 37 | `UNAS_HIST_VLTL` | 역사적변동성 | string | Y | 8 |  |
| 38 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 39 | `DPRT` | 괴리율 | string | Y | 8 |  |
| 40 | `MRKT_BASIS` | 시장 베이시스 | string | Y | 8 |  |
| 41 | `OPTN_ASKP1` | 옵션 매도호가1 | string | Y | 8 |  |
| 42 | `OPTN_BIDP1` | 옵션 매수호가1 | string | Y | 8 |  |
| 43 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 44 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 45 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 8 |  |
| 46 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 8 |  |
| 47 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 8 |  |
| 48 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 8 |  |
| 49 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 6 |  |
| 50 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 6 |  |
| 51 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 6 |  |
| 52 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 6 |  |
| 53 | `AVRG_VLTL` | 평균 변동성 | string | Y | 6 |  |
| 54 | `DSCS_LRQN_VOL` | 협의대량누적 거래량 | string | Y | 6 |  |
| 55 | `DYNM_MXPR` | 실시간상한가 | string | Y | 6 |  |
| 56 | `DYNM_LLAM` | 실시간하한가 | string | Y | 6 |  |
| 57 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 6 |  |


### KRX야간옵션 실시간호가

- **API ID**: 실시간-033
- **실전 TR_ID**: H0EUASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EUASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EUASP0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 야간옵션 종목코드 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `OPTN_ASKP1` | 옵션매도호가1 | string | Y | 1 |  |
| 3 | `OPTN_ASKP2` | 옵션매도호가2 | string | Y | 1 |  |
| 4 | `OPTN_ASKP3` | 옵션매도호가3 | string | Y | 1 |  |
| 5 | `OPTN_ASKP4` | 옵션매도호가4 | string | Y | 1 |  |
| 6 | `OPTN_ASKP5` | 옵션매도호가5 | string | Y | 1 |  |
| 7 | `OPTN_BIDP1` | 옵션매수호가1 | string | Y | 1 |  |
| 8 | `OPTN_BIDP2` | 옵션매수호가2 | string | Y | 1 |  |
| 9 | `OPTN_BIDP3` | 옵션매수호가3 | string | Y | 1 |  |
| 10 | `OPTN_BIDP4` | 옵션매수호가4 | string | Y | 1 |  |
| 11 | `OPTN_BIDP5` | 옵션매수호가5 | string | Y | 1 |  |
| 12 | `ASKP_CSNU1` | 매도호가건수1 | string | Y | 1 |  |
| 13 | `ASKP_CSNU2` | 매도호가건수2 | string | Y | 1 |  |
| 14 | `ASKP_CSNU3` | 매도호가건수3 | string | Y | 1 |  |
| 15 | `ASKP_CSNU4` | 매도호가건수4 | string | Y | 1 |  |
| 16 | `ASKP_CSNU5` | 매도호가건수5 | string | Y | 1 |  |
| 17 | `BIDP_CSNU1` | 매수호가건수1 | string | Y | 1 |  |
| 18 | `BIDP_CSNU2` | 매수호가건수2 | string | Y | 1 |  |
| 19 | `BIDP_CSNU3` | 매수호가건수3 | string | Y | 1 |  |
| 20 | `BIDP_CSNU4` | 매수호가건수4 | string | Y | 1 |  |
| 21 | `BIDP_CSNU5` | 매수호가건수5 | string | Y | 1 |  |
| 22 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 23 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 1 |  |
| 24 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 1 |  |
| 25 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 1 |  |
| 26 | `ASKP_RSQN5` | 매도호가잔량5 | string | Y | 1 |  |
| 27 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 28 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 1 |  |
| 29 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 1 |  |
| 30 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 1 |  |
| 31 | `BIDP_RSQN5` | 매수호가잔량5 | string | Y | 1 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총매도호가건수 | string | Y | 1 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총매수호가건수 | string | Y | 1 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총매도호가잔량증감 | string | Y | 1 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총매수호가잔량증감 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0EUASP0",
            "tr_key": "301V06362"
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
        "tr_id": "H0EUASP0", 
        "tr_key": "301V06362", 
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

# output
0|H0EUASP0|001|301V06362^190159^2.98^2.99^3.00^0.00^0.00^2.97^2.96^2.95^0.00^0.00^0
^0^0^0^0^0^0^0^0^0^1^3^12^0^0^9^21^16^0^0^0^0^16^46^5^0

# output - 복호화 후
#### 야간옵션(EUREX) 호가 ####
야간옵션(EUREX)  [301V06362]
영업시간  [190215]
====================================
옵션매도호가1   [2.98],    매도호가건수1        [0],    매도호가잔량1   [1]
옵션매도호가2   [3.00],    매도호가건수2        [0],    매도호가잔량2   [6]
옵션매도호가3   [3.01],    매도호가건수3        [0],    매도호가잔량3   [15]
옵션매도호가4   [0.00],    매도호가건수4        [0],    매도호가잔량4   [0]
옵션매도호가5   [0.00],    매도호가건수5        [0],    매도호가잔량5   [0]
옵션매수호가1   [2.97],    매수호가건수1        [0],    매수호가잔량1   [10]
옵션매수호가2   [2.96],    매수호가건수2        [0],    매수호가잔량2   [21]
옵션매수호가3   [2.95],    매수호가건수3        [0],    매수호가잔량3   [16]
옵션매수호가4   [0.00],   매수호가건수4 [0],    매수호가잔량4   [0]
옵션매수호가5   [0.00],    매수호가건수5        [0],    매수호가잔량5   [0]
====================================
총매도호가건수  [0],    총매도호가잔량  [22],    총매도호가잔량증감     [-1]
총매수호가건수  [0],    총매수호가잔량  [47],    총매수호가잔량증감     [1]
```

</details>



### 상품선물 실시간호가

- **API ID**: 실시간-023
- **실전 TR_ID**: H0CFASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0CFASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
※ 선물옵션 호가 데이터는 0.2초 필터링 옵션이 있습니다.
  필터링 사유는 순간적으로 데이터가 폭증할 경우 서버 뿐만아니라 클라이언트 환경에도 부하를 줄 수 있어 적용된 사항인 점 양해 부탁드립니다.

[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0CFASP0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물 단축 종목코드 | object | Y | 32 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 9 |  |
| 2 | `FUTS_ASKP1` | 선물 매도호가1 | string | Y | 6 |  |
| 3 | `FUTS_ASKP2` | 선물 매도호가2 | string | Y | 8 |  |
| 4 | `FUTS_ASKP3` | 선물 매도호가3 | string | Y | 1 |  |
| 5 | `FUTS_ASKP4` | 선물 매도호가4 | string | Y | 8 |  |
| 6 | `FUTS_ASKP5` | 선물 매도호가5 | string | Y | 8 |  |
| 7 | `FUTS_BIDP1` | 선물 매수호가1 | string | Y | 8 |  |
| 8 | `FUTS_BIDP2` | 선물 매수호가2 | string | Y | 8 |  |
| 9 | `FUTS_BIDP3` | 선물 매수호가3 | string | Y | 8 |  |
| 10 | `FUTS_BIDP4` | 선물 매수호가4 | string | Y | 8 |  |
| 11 | `FUTS_BIDP5` | 선물 매수호가5 | string | Y | 8 |  |
| 12 | `ASKP_CSNU1` | 매도호가 건수1 | string | Y | 8 |  |
| 13 | `ASKP_CSNU2` | 매도호가 건수2 | string | Y | 8 |  |
| 14 | `ASKP_CSNU3` | 매도호가 건수3 | string | Y | 8 |  |
| 15 | `ASKP_CSNU4` | 매도호가 건수4 | string | Y | 8 |  |
| 16 | `ASKP_CSNU5` | 매도호가 건수5 | string | Y | 8 |  |
| 17 | `BIDP_CSNU1` | 매수호가 건수1 | string | Y | 8 |  |
| 18 | `BIDP_CSNU2` | 매수호가 건수2 | string | Y | 8 |  |
| 19 | `BIDP_CSNU3` | 매수호가 건수3 | string | Y | 8 |  |
| 20 | `BIDP_CSNU4` | 매수호가 건수4 | string | Y | 4 |  |
| 21 | `BIDP_CSNU5` | 매수호가 건수5 | string | Y | 6 |  |
| 22 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 1 |  |
| 23 | `ASKP_RSQN2` | 매도호가 잔량2 | string | Y | 8 |  |
| 24 | `ASKP_RSQN3` | 매도호가 잔량3 | string | Y | 6 |  |
| 25 | `ASKP_RSQN4` | 매도호가 잔량4 | string | Y | 1 |  |
| 26 | `ASKP_RSQN5` | 매도호가 잔량5 | string | Y | 8 |  |
| 27 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 6 |  |
| 28 | `BIDP_RSQN2` | 매수호가 잔량2 | string | Y | 1 |  |
| 29 | `BIDP_RSQN3` | 매수호가 잔량3 | string | Y | 8 |  |
| 30 | `BIDP_RSQN4` | 매수호가 잔량4 | string | Y | 8 |  |
| 31 | `BIDP_RSQN5` | 매수호가 잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총 매도호가 건수 | string | Y | 8 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총 매수호가 건수 | string | Y | 4 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | string | Y | 8 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | string | Y | 8 |  |


### 주식옵션 실시간예상체결

- **API ID**: 실시간-046
- **실전 TR_ID**: H0ZOANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZOANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
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
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0ZOANC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 주식옵션 종목코드 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `ANTC_CNPR` | 예상체결가 | string | Y | 8 |  |
| 3 | `ANTC_CNTG_VRSS` | 예상체결대비 | string | Y | 8 |  |
| 4 | `ANTC_CNTG_VRSS_SIGN` | 예상체결대비부호 | string | Y | 1 |  |
| 5 | `ANTC_CNTG_PRDY_CTRT` | 예상체결전일대비율 | string | Y | 8 |  |
| 6 | `ANTC_MKOP_CLS_CODE` | 예상장운영구분코드 | string | Y | 3 |  |


### 주식선물 실시간호가

- **API ID**: 실시간-030
- **실전 TR_ID**: H0ZFASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZFASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
※ 선물옵션 호가 데이터는 0.2초 필터링 옵션이 있습니다.
  필터링 사유는 순간적으로 데이터가 폭증할 경우 서버 뿐만아니라 클라이언트 환경에도 부하를 줄 수 있어 적용된 사항인 점 양해 부탁드립니다.

[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0ZFASP0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (68)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `ASKP1` | 매도호가1 | string | Y | 1 |  |
| 3 | `ASKP2` | 매도호가2 | string | Y | 1 |  |
| 4 | `ASKP3` | 매도호가3 | string | Y | 1 |  |
| 5 | `ASKP4` | 매도호가4 | string | Y | 1 |  |
| 6 | `ASKP5` | 매도호가5 | string | Y | 1 |  |
| 7 | `ASKP6` | 매도호가6 | string | Y | 1 |  |
| 8 | `ASKP7` | 매도호가7 | string | Y | 1 |  |
| 9 | `ASKP8` | 매도호가8 | string | Y | 1 |  |
| 10 | `ASKP9` | 매도호가9 | string | Y | 1 |  |
| 11 | `ASKP10` | 매도호가10 | string | Y | 1 |  |
| 12 | `BIDP1` | 매수호가1 | string | Y | 1 |  |
| 13 | `BIDP2` | 매수호가2 | string | Y | 1 |  |
| 14 | `BIDP3` | 매수호가3 | string | Y | 1 |  |
| 15 | `BIDP4` | 매수호가4 | string | Y | 1 |  |
| 16 | `BIDP5` | 매수호가5 | string | Y | 1 |  |
| 17 | `BIDP6` | 매수호가6 | string | Y | 1 |  |
| 18 | `BIDP7` | 매수호가7 | string | Y | 1 |  |
| 19 | `BIDP8` | 매수호가8 | string | Y | 1 |  |
| 20 | `BIDP9` | 매수호가9 | string | Y | 1 |  |
| 21 | `BIDP10` | 매수호가10 | string | Y | 1 |  |
| 22 | `ASKP_CSNU1` | 매도호가건수1 | string | Y | 1 |  |
| 23 | `ASKP_CSNU2` | 매도호가건수2 | string | Y | 1 |  |
| 24 | `ASKP_CSNU3` | 매도호가건수3 | string | Y | 1 |  |
| 25 | `ASKP_CSNU4` | 매도호가건수4 | string | Y | 1 |  |
| 26 | `ASKP_CSNU5` | 매도호가건수5 | string | Y | 1 |  |
| 27 | `ASKP_CSNU6` | 매도호가건수6 | string | Y | 1 |  |
| 28 | `ASKP_CSNU7` | 매도호가건수7 | string | Y | 1 |  |
| 29 | `ASKP_CSNU8` | 매도호가건수8 | string | Y | 1 |  |
| 30 | `ASKP_CSNU9` | 매도호가건수9 | string | Y | 1 |  |
| 31 | `ASKP_CSNU10` | 매도호가건수10 | string | Y | 1 |  |
| 32 | `BIDP_CSNU1` | 매수호가건수1 | string | Y | 1 |  |
| 33 | `BIDP_CSNU2` | 매수호가건수2 | string | Y | 1 |  |
| 34 | `BIDP_CSNU3` | 매수호가건수3 | string | Y | 1 |  |
| 35 | `BIDP_CSNU4` | 매수호가건수4 | string | Y | 1 |  |
| 36 | `BIDP_CSNU5` | 매수호가건수5 | string | Y | 1 |  |
| 37 | `BIDP_CSNU6` | 매수호가건수6 | string | Y | 1 |  |
| 38 | `BIDP_CSNU7` | 매수호가건수7 | string | Y | 1 |  |
| 39 | `BIDP_CSNU8` | 매수호가건수8 | string | Y | 1 |  |
| 40 | `BIDP_CSNU9` | 매수호가건수9 | string | Y | 1 |  |
| 41 | `BIDP_CSNU10` | 매수호가건수10 | string | Y | 1 |  |
| 42 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 43 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 1 |  |
| 44 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 1 |  |
| 45 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 1 |  |
| 46 | `ASKP_RSQN5` | 매도호가잔량5 | string | Y | 1 |  |
| 47 | `ASKP_RSQN6` | 매도호가잔량6 | string | Y | 1 |  |
| 48 | `ASKP_RSQN7` | 매도호가잔량7 | string | Y | 1 |  |
| 49 | `ASKP_RSQN8` | 매도호가잔량8 | string | Y | 1 |  |
| 50 | `ASKP_RSQN9` | 매도호가잔량9 | string | Y | 1 |  |
| 51 | `ASKP_RSQN10` | 매도호가잔량10 | string | Y | 1 |  |
| 52 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 53 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 1 |  |
| 54 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 1 |  |
| 55 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 1 |  |
| 56 | `BIDP_RSQN5` | 매수호가잔량5 | string | Y | 1 |  |
| 57 | `BIDP_RSQN6` | 매수호가잔량6 | string | Y | 1 |  |
| 58 | `BIDP_RSQN7` | 매수호가잔량7 | string | Y | 1 |  |
| 59 | `BIDP_RSQN8` | 매수호가잔량8 | string | Y | 1 |  |
| 60 | `BIDP_RSQN9` | 매수호가잔량9 | string | Y | 1 |  |
| 61 | `BIDP_RSQN10` | 매수호가잔량10 | string | Y | 1 |  |
| 62 | `TOTAL_ASKP_CSNU` | 총매도호가건수 | string | Y | 1 |  |
| 63 | `TOTAL_BIDP_CSNU` | 총매수호가건수 | string | Y | 1 |  |
| 64 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 65 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 66 | `TOTAL_ASKP_RSQN_ICDC` | 총매도호가잔량증감 | string | Y | 1 |  |
| 67 | `TOTAL_BIDP_RSQN_ICDC` | 총매수호가잔량증감 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0ZFASP0",
            "tr_key": "111V06"
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
        "tr_id": "H0ZFASP0", 
        "tr_key": "111V06", 
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

# output
0|H0ZFASP0|001|111V06^092304^79700^79800^79900^80000^80200^80300^80500^81100^8490
0^85900^79500^79400^79300^79200^79100^79000^78900^78800^78700^78600^1^18^6^2^2^1^3^1^1^1^8^6^4^8^4^
8^7^11^11^3^950^4148^988^6^9^1^3^15^5^10^4404^2277^1321^3440^330^2237^1835^362^83^15^36^97^6135^165
09^950^0
```

</details>



### 주식옵션 실시간체결가

- **API ID**: 실시간-044
- **실전 TR_ID**: H0ZOCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZOCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0ZOCNT0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (53)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `OPTN_PRPR` | 옵션현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `OPTN_PRDY_VRSS` | 옵션전일대비 | string | Y | 1 |  |
| 5 | `PRDY_CTRT` | 전일대비율 | string | Y | 1 |  |
| 6 | `OPTN_OPRC` | 옵션시가2 | string | Y | 1 |  |
| 7 | `OPTN_HGPR` | 옵션최고가 | string | Y | 1 |  |
| 8 | `OPTN_LWPR` | 옵션최저가 | string | Y | 1 |  |
| 9 | `LAST_CNQN` | 최종거래량 | string | Y | 1 |  |
| 10 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 11 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 1 |  |
| 12 | `HTS_THPR` | HTS이론가 | string | Y | 1 |  |
| 13 | `HTS_OTST_STPL_QTY` | HTS미결제약정수량 | string | Y | 1 |  |
| 14 | `OTST_STPL_QTY_ICDC` | 미결제약정수량증감 | string | Y | 1 |  |
| 15 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 16 | `OPRC_VRSS_PRPR_SIGN` | 시가2대비현재가부호 | string | Y | 1 |  |
| 17 | `OPRC_VRSS_NMIX_PRPR` | 시가대비지수현재가 | string | Y | 1 |  |
| 18 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 19 | `HGPR_VRSS_PRPR_SIGN` | 최고가대비현재가부호 | string | Y | 1 |  |
| 20 | `HGPR_VRSS_NMIX_PRPR` | 최고가대비지수현재가 | string | Y | 1 |  |
| 21 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 22 | `LWPR_VRSS_PRPR_SIGN` | 최저가대비현재가부호 | string | Y | 1 |  |
| 23 | `LWPR_VRSS_NMIX_PRPR` | 최저가대비지수현재가 | string | Y | 1 |  |
| 24 | `SHNU_RATE` | 매수2비율 | string | Y | 1 |  |
| 25 | `PRMM_VAL` | 프리미엄값 | string | Y | 1 |  |
| 26 | `INVL_VAL` | 내재가치값 | string | Y | 1 |  |
| 27 | `TMVL_VAL` | 시간가치값 | string | Y | 1 |  |
| 28 | `DELTA` | 델타 | string | Y | 1 |  |
| 29 | `GAMA` | 감마 | string | Y | 1 |  |
| 30 | `VEGA` | 베가 | string | Y | 1 |  |
| 31 | `THETA` | 세타 | string | Y | 1 |  |
| 32 | `RHO` | 로우 | string | Y | 1 |  |
| 33 | `HTS_INTS_VLTL` | HTS내재변동성 | string | Y | 1 |  |
| 34 | `ESDG` | 괴리도 | string | Y | 1 |  |
| 35 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제약정직전수량증감 | string | Y | 1 |  |
| 36 | `THPR_BASIS` | 이론베이시스 | string | Y | 1 |  |
| 37 | `UNAS_HIST_VLTL` | 역사적변동성 | string | Y | 1 |  |
| 38 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 39 | `DPRT` | 괴리율 | string | Y | 1 |  |
| 40 | `MRKT_BASIS` | 시장베이시스 | string | Y | 1 |  |
| 41 | `OPTN_ASKP1` | 옵션매도호가1 | string | Y | 1 |  |
| 42 | `OPTN_BIDP1` | 옵션매수호가1 | string | Y | 1 |  |
| 43 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 44 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 45 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 1 |  |
| 46 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 1 |  |
| 47 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 1 |  |
| 48 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 1 |  |
| 49 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 1 |  |
| 50 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 51 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 52 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0ZOCNT0",
            "tr_key": "211V05059"
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
        "tr_id": "H0ZOCNT0", 
        "tr_key": "211V05059", 
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

# output
0|H0ZOCNT0|001|211V05059^091940^1060.00^5^-120.00^-10.17^970.00^1140.00^970
.00^6^563^5933200^35464.07^1134^-2^000000^2^90.00^000000^5^-80.00^000000^2^90.00^0.43^0.00^0.
00^1060.00^1.00^0.00^0.00^-4.06^20.58^0.31^-34404.07^0^-41735.93^0.26^74.84^-97.01^-76140.00^
1100.00^1040.00^6^175^13^16^3^322^241^241^184^12.33
```

</details>



### 지수옵션 실시간호가

- **API ID**: 실시간-015
- **실전 TR_ID**: H0IOASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0IOASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료][참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 2 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0IOASP0 |
| 1 | `tr_key` | 코드 | string | Y | 6 | 예:201S11305 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `OPTN_SHRN_ISCD` | 옵션 단축 종목코드 | object | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 16 |  |
| 2 | `OPTN_ASKP1` | 옵션 매도호가1 | string | Y | 1 |  |
| 3 | `OPTN_ASKP2` | 옵션 매도호가2 | string | Y | 8 |  |
| 4 | `OPTN_ASKP3` | 옵션 매도호가3 | string | Y | 8 |  |
| 5 | `OPTN_ASKP4` | 옵션 매도호가4 | string | Y | 8 |  |
| 6 | `OPTN_ASKP5` | 옵션 매도호가5 | string | Y | 8 |  |
| 7 | `OPTN_BIDP1` | 옵션 매수호가1 | string | Y | 8 |  |
| 8 | `OPTN_BIDP2` | 옵션 매수호가2 | string | Y | 8 |  |
| 9 | `OPTN_BIDP3` | 옵션 매수호가3 | string | Y | 8 |  |
| 10 | `OPTN_BIDP4` | 옵션 매수호가4 | string | Y | 8 |  |
| 11 | `OPTN_BIDP5` | 옵션 매수호가5 | string | Y | 8 |  |
| 12 | `ASKP_CSNU1` | 매도호가 건수1 | string | Y | 8 |  |
| 13 | `ASKP_CSNU2` | 매도호가 건수2 | string | Y | 8 |  |
| 14 | `ASKP_CSNU3` | 매도호가 건수3 | string | Y | 8 |  |
| 15 | `ASKP_CSNU4` | 매도호가 건수4 | string | Y | 8 |  |
| 16 | `ASKP_CSNU5` | 매도호가 건수5 | string | Y | 8 |  |
| 17 | `BIDP_CSNU1` | 매수호가 건수1 | string | Y | 8 |  |
| 18 | `BIDP_CSNU2` | 매수호가 건수2 | string | Y | 8 |  |
| 19 | `BIDP_CSNU3` | 매수호가 건수3 | string | Y | 8 |  |
| 20 | `BIDP_CSNU4` | 매수호가 건수4 | string | Y | 8 |  |
| 21 | `BIDP_CSNU5` | 매수호가 건수5 | string | Y | 8 |  |
| 22 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 23 | `ASKP_RSQN2` | 매도호가 잔량2 | string | Y | 8 |  |
| 24 | `ASKP_RSQN3` | 매도호가 잔량3 | string | Y | 8 |  |
| 25 | `ASKP_RSQN4` | 매도호가 잔량4 | string | Y | 8 |  |
| 26 | `ASKP_RSQN5` | 매도호가 잔량5 | string | Y | 8 |  |
| 27 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 28 | `BIDP_RSQN2` | 매수호가 잔량2 | string | Y | 8 |  |
| 29 | `BIDP_RSQN3` | 매수호가 잔량3 | string | Y | 8 |  |
| 30 | `BIDP_RSQN4` | 매수호가 잔량4 | string | Y | 8 |  |
| 31 | `BIDP_RSQN5` | 매수호가 잔량5 | string | Y | 8 |  |
| 32 | `TOTAL_ASKP_CSNU` | 총 매도호가 건수 | string | Y | 8 |  |
| 33 | `TOTAL_BIDP_CSNU` | 총 매수호가 건수 | string | Y | 8 |  |
| 34 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 35 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 36 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | string | Y | 8 |  |
| 37 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | string | Y | 8 |  |


### 주식선물 실시간체결가

- **API ID**: 실시간-029
- **실전 TR_ID**: H0ZFCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0ZFCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/examples_user/domestic_futureoption

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식, 해외주식 내용 참고)

시세조회 가능한 종목코드 목록은 API문서 &gt; 종목정보파일 에서 확인하실 수 있습니다. ( 헤더파일 및 정제코드 참고)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0ZFCNT0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (49)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FUTS_SHRN_ISCD` | 선물단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 4 |  |
| 5 | `FUTS_PRDY_CTRT` | 선물전일대비율 | string | Y | 8 |  |
| 6 | `STCK_OPRC` | 주식시가2 | string | Y | 4 |  |
| 7 | `STCK_HGPR` | 주식최고가 | string | Y | 4 |  |
| 8 | `STCK_LWPR` | 주식최저가 | string | Y | 4 |  |
| 9 | `LAST_CNQN` | 최종거래량 | string | Y | 8 |  |
| 10 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 11 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 8 |  |
| 12 | `HTS_THPR` | HTS이론가 | string | Y | 8 |  |
| 13 | `MRKT_BASIS` | 시장베이시스 | string | Y | 8 |  |
| 14 | `DPRT` | 괴리율 | string | Y | 8 |  |
| 15 | `NMSC_FCTN_STPL_PRC` | 근월물약정가 | string | Y | 8 |  |
| 16 | `FMSC_FCTN_STPL_PRC` | 원월물약정가 | string | Y | 8 |  |
| 17 | `SPEAD_PRC` | 스프레드1 | string | Y | 8 |  |
| 18 | `HTS_OTST_STPL_QTY` | HTS미결제약정수량 | string | Y | 8 |  |
| 19 | `OTST_STPL_QTY_ICDC` | 미결제약정수량증감 | string | Y | 4 |  |
| 20 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 21 | `OPRC_VRSS_PRPR_SIGN` | 시가2대비현재가부호 | string | Y | 1 |  |
| 22 | `OPRC_VRSS_PRPR` | 시가2대비현재가 | string | Y | 4 |  |
| 23 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 24 | `HGPR_VRSS_PRPR_SIGN` | 최고가대비현재가부호 | string | Y | 1 |  |
| 25 | `HGPR_VRSS_PRPR` | 최고가대비현재가 | string | Y | 4 |  |
| 26 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 27 | `LWPR_VRSS_PRPR_SIGN` | 최저가대비현재가부호 | string | Y | 1 |  |
| 28 | `LWPR_VRSS_PRPR` | 최저가대비현재가 | string | Y | 4 |  |
| 29 | `SHNU_RATE` | 매수2비율 | string | Y | 8 |  |
| 30 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 31 | `ESDG` | 괴리도 | string | Y | 8 |  |
| 32 | `OTST_STPL_RGBF_QTY_ICDC` | 미결제약정직전수량증감 | string | Y | 4 |  |
| 33 | `THPR_BASIS` | 이론베이시스 | string | Y | 8 |  |
| 34 | `ASKP1` | 매도호가1 | string | Y | 4 |  |
| 35 | `BIDP1` | 매수호가1 | string | Y | 4 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 38 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 4 |  |
| 39 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 4 |  |
| 40 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 4 |  |
| 41 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 8 |  |
| 42 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 8 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 45 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 8 |  |
| 46 | `DYNM_MXPR` | 실시간상한가 | string | Y | 4 |  |
| 47 | `DYNM_LLAM` | 실시간하한가 | string | Y | 4 |  |
| 48 | `DYNM_PRC_LIMT_YN` | 실시간가격제한구분 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0ZFCNT0",
            "tr_key": "111V06"
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
        "tr_id": "H0ZFCNT0", 
        "tr_key": "111V06", 
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

# output
0|H0ZFCNT0|001|111V06^091639^77900^5^-100^-0.13^77900^77900^77300^5^1724^13
37128000^77899.50^400.00^0.00^0.00^0.00^-500.00^32053^219^000000^3^0^000000^3^0^000000^2^600^
0.36^58.23^0.50^-1^399.50^77900^77800^0^0^105^36^-69^1075^626^0^0^6.23^0^0^0
```

</details>


