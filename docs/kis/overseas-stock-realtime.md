# [해외주식] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (4개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 282 | WEBSOCKET | 해외주식 실시간호가 | HDFSASP0 | POST | `/tryitout/HDFSASP0` |  |
| 283 | WEBSOCKET | 해외주식 지연호가(아시아) | HDFSASP1 | POST | `/tryitout/HDFSASP1` |  |
| 284 | WEBSOCKET | 해외주식 실시간지연체결가 | HDFSCNT0 | POST | `/tryitout/HDFSCNT0` |  |
| 285 | WEBSOCKET | 해외주식 실시간체결통보 | H0GSCNI0 | POST | `/tryitout/H0GSCNI0` |  |

---

## 상세 명세

### 해외주식 실시간호가

- **TR_ID**: HDFSASP0
- **Method**: POST
- **URL**: `/tryitout/HDFSASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "HDFSASP0",
            "tr_key": "RBAQAAPL"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "HDFSASP0", 
        "tr_key": "RBAQAAPL", 
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
0|HDFSASP0|001|RBAQAAPL^AAPL^4^20240506^202223^20240507^092223^1482^381^0^-10^182.8500^182.8700^350^57^0^-10^182.8400^182.9000^1^10^0^0^182.8300^182.9100^6^54^0^0^182.7900^182.9500^54^5^0^0^182.7500^182.9600^309^3^0^0^182.7300^182.9700^20^81^0^0^182.7000^182.9800^124^3^0^0^182.6600^182.9900^397^1^0^0^182.6500^183.0000^20^69^0^0^182.6300^183.0100^201^98^0^0 |  |


### 해외주식 지연호가(아시아)

- **TR_ID**: HDFSASP1
- **Method**: POST
- **URL**: `/tryitout/HDFSASP1`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 실시간지연체결가

- **TR_ID**: HDFSCNT0
- **Method**: POST
- **URL**: `/tryitout/HDFSCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 해외주식 실시간체결통보

- **TR_ID**: H0GSCNI0
- **모의 TR_ID**: H0GSCNI9
- **Method**: POST
- **URL**: `/tryitout/H0GSCNI0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
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
                           "tr_id":"H0GSCNI0",
                           "tr_key":"HTS ID"
                  }
         }
} |  |
| Response Example | # output - 등록 성공 시
{
    "header": {
        "tr_id": "H0GSCNI0", 
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
1|H0GSCNI0|001|vebQjGIHMgFhxfNfvebQjGIHMgFhxfNfvebQjGIHMgFhxfNfvebQj...hxfNf

# output (복호화 후)
#### 해외주식 주문·정정·취소·거부 접수 통보 ####
고객 ID  [abcd1234]
계좌번호  [12345678]
주문번호  [3567]
원주문번호  []
매도매수구분  [02]
정정구분  [0]
주문종류2  [1]
단축종목코드  [7203]
주문수량  [0000000100]
체결단가  [000032200]
체결시간  []
거부여부  [0]
체결여부  [1]
접수여부  [1]
지점번호  []
체결수량  []
계좌명  [******]
체결종목명  [도요타자동차]
해외종목구분  [D]
담보유형코드  [10]
담보대출일자  []
분할매수매도시작시간  []
분할매수매도종료시간  []
시간분할타입유형  [] |  |

