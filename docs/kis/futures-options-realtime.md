# [국내선물옵션] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


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

- **TR_ID**: H0ZOASP0
- **Method**: POST
- **URL**: `/tryitout/H0ZOASP0`

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
            "tr_id": "H0ZOASP0",
            "tr_key": "211V05059"
        }
    }
} |  |
| Response Example | # 연결 확인
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
0^0^0^0^0 |  |


### 선물옵션 실시간체결통보

- **TR_ID**: H0IFCNI0
- **모의 TR_ID**: H0IFCNI9
- **Method**: POST
- **URL**: `/tryitout/H0IFCNI0`

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
                           "tr_id":"H0IFCNI0",
                           "tr_key":"HTS ID"
                  }
         }
} |  |
| Response Example | # output - 등록 성공 시
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
주문가격  [000000000] |  |


### KRX야간선물 실시간종목체결

- **TR_ID**: H0MFCNT0
- **Method**: POST
- **URL**: `/tryitout/H0MFCNT0`

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
            "tr_id": "H0MFCNT0",
            "tr_key": "101V06"
        }
    }
} |  |
| Response Example | # 연결 확인
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
2^0^0.00^367.35^367.30^0^0^345^358^13^813^783^0^0^0.00 |  |


### KRX야간선물 실시간호가

- **TR_ID**: H0MFASP0
- **Method**: POST
- **URL**: `/tryitout/H0MFASP0`

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
            "tr_id": "H0MFASP0",
            "tr_key": "101V06"
        }
    }
} |  |
| Response Example | # 연결 확인
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
00^0.00^0^0^0^0^0^0^0^0^0^0^24^21^21^0^0^2^28^20^0^0^0^0^0^0^^0^0^0^0^0^^000000^2^ |  |


### KRX야간옵션 실시간체결가

- **TR_ID**: H0EUCNT0
- **Method**: POST
- **URL**: `/tryitout/H0EUCNT0`

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
            "tr_id": "H0EUCNT0",
            "tr_key": "301V06362"
        }
    }
} |  |
| Response Example | # 연결 확인
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
전일거래량대비등락율   [0.00] |  |


### KRX야간옵션실시간예상체결

- **TR_ID**: H0EUANC0
- **Method**: POST
- **URL**: `/tryitout/H0EUANC0`

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
            "tr_id": "H0EUANC0",
            "tr_key": "301V06362"
        }
    }
} |  |
| Response Example | # 연결 확인
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

# output |  |


### 지수선물 실시간체결가

- **TR_ID**: H0IFCNT0
- **Method**: POST
- **URL**: `/tryitout/H0IFCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 주식선물 실시간예상체결

- **TR_ID**: H0ZFANC0
- **Method**: POST
- **URL**: `/tryitout/H0ZFANC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### KRX야간옵션실시간체결통보

- **TR_ID**: H0MFCNI0
- **Method**: POST
- **URL**: `/tryitout/H0EUCNI0`

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
            "tr_id": "H0EUCNI0",
            "tr_key": "HTS_ID"
        }
    }
} |  |
| Response Example | # 연결 확인
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
주문조건  [0] |  |


### KRX야간선물 실시간체결통보

- **TR_ID**: H0MFCNI0
- **Method**: POST
- **URL**: `/tryitout/H0MFCNI0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 상품선물 실시간체결가

- **TR_ID**: H0CFCNT0
- **Method**: POST
- **URL**: `/tryitout/H0CFCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 지수선물 실시간호가

- **TR_ID**: H0IFASP0
- **Method**: POST
- **URL**: `/tryitout/H0IFASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 지수옵션  실시간체결가

- **TR_ID**: H0IOCNT0
- **Method**: POST
- **URL**: `/tryitout/H0IOCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### KRX야간옵션 실시간호가

- **TR_ID**: H0EUASP0
- **Method**: POST
- **URL**: `/tryitout/H0EUASP0`

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
            "tr_id": "H0EUASP0",
            "tr_key": "301V06362"
        }
    }
} |  |
| Response Example | # 연결 확인
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
총매수호가건수  [0],    총매수호가잔량  [47],    총매수호가잔량증감     [1] |  |


### 상품선물 실시간호가

- **TR_ID**: H0CFASP0
- **Method**: POST
- **URL**: `/tryitout/H0CFASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 주식옵션 실시간예상체결

- **TR_ID**: H0ZOANC0
- **Method**: POST
- **URL**: `/tryitout/H0ZOANC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 주식선물 실시간호가

- **TR_ID**: H0ZFASP0
- **Method**: POST
- **URL**: `/tryitout/H0ZFASP0`

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
            "tr_id": "H0ZFASP0",
            "tr_key": "111V06"
        }
    }
} |  |
| Response Example | # 연결 확인
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
09^950^0 |  |


### 주식옵션 실시간체결가

- **TR_ID**: H0ZOCNT0
- **Method**: POST
- **URL**: `/tryitout/H0ZOCNT0`

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
            "tr_id": "H0ZOCNT0",
            "tr_key": "211V05059"
        }
    }
} |  |
| Response Example | # 연결 확인
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
1100.00^1040.00^6^175^13^16^3^322^241^241^184^12.33 |  |


### 지수옵션 실시간호가

- **TR_ID**: H0IOASP0
- **Method**: POST
- **URL**: `/tryitout/H0IOASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 주식선물 실시간체결가

- **TR_ID**: H0ZFCNT0
- **Method**: POST
- **URL**: `/tryitout/H0ZFCNT0`

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
            "tr_id": "H0ZFCNT0",
            "tr_key": "111V06"
        }
    }
} |  |
| Response Example | # 연결 확인
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
0.36^58.23^0.50^-1^399.50^77900^77800^0^0^105^36^-69^1075^626^0^0^6.23^0^0^0 |  |

