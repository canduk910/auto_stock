# [국내주식] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (29개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 162 | WEBSOCKET | 국내지수 실시간예상체결 | H0UPANC0 | POST | `/tryitout/H0UPANC0` |  |
| 163 | REST | 국내주식 장운영정보 (통합) | H0UNMKO0 | POST | `/tryitout/H0UNMKO0` |  |
| 164 | WEBSOCKET | 국내주식 실시간회원사 (NXT) | H0NXMBC0 | POST | `/tryitout/H0NXMBC0` |  |
| 165 | WEBSOCKET | 국내주식 실시간체결통보 | H0STCNI0 | POST | `/tryitout/H0STCNI0` | ✓ |
| 166 | WEBSOCKET | 국내주식 시간외 실시간예상체결 (KRX) | H0STOAC0 | POST | `/tryitout/H0STOAC0` |  |
| 167 | WEBSOCKET | 국내주식 시간외 실시간호가 (KRX) | H0STOAA0 | POST | `/tryitout/H0STOAA0` |  |
| 168 | WEBSOCKET | 국내주식 실시간프로그램매매 (통합) | H0UNPGM0 | POST | `/tryitout/H0UNPGM0` |  |
| 169 | WEBSOCKET | 국내주식 실시간호가 (통합) | H0UNASP0 | POST | `/tryitout/H0UNASP0` |  |
| 170 | WEBSOCKET | 국내주식 실시간프로그램매매 (KRX) | H0STPGM0 | POST | `/tryitout/H0STPGM0` |  |
| 171 | WEBSOCKET | 국내주식 장운영정보 (KRX) | H0STMKO0 | POST | `/tryitout/H0STMKO0` |  |
| 172 | WEBSOCKET | 국내주식 실시간체결가 (KRX) | H0STCNT0 | POST | `/tryitout/H0STCNT0` |  |
| 173 | WEBSOCKET | 국내지수 실시간프로그램매매 | H0UPPGM0 | POST | `/tryitout/H0UPPGM0` |  |
| 174 | WEBSOCKET | 국내주식 실시간회원사 (통합) | H0UNMBC0 | POST | `/tryitout/H0UNMBC0` |  |
| 175 | WEBSOCKET | 국내지수 실시간체결 | H0UPCNT0 | POST | `/tryitout/H0UPCNT0` |  |
| 176 | WEBSOCKET | 국내주식 실시간예상체결 (KRX) | H0STANC0 | POST | `/tryitout/H0STANC0` |  |
| 177 | WEBSOCKET | ELW 실시간호가 | H0EWASP0 | POST | `/tryitout/H0EWASP0` |  |
| 178 | WEBSOCKET | 국내주식 실시간호가 (KRX) | H0STASP0 | POST | `/tryitout/H0STASP0` |  |
| 179 | WEBSOCKET | 국내주식 실시간체결가 (통합) | H0UNCNT0 | POST | `/tryitout/H0UNCNT0` |  |
| 180 | WEBSOCKET | 국내주식 실시간호가 (NXT) | H0NXASP0 | POST | `/tryitout/H0NXASP0` |  |
| 181 | WEBSOCKET | 국내주식 실시간프로그램매매 (NXT) | H0NXPGM0 | POST | `/tryitout/H0NXPGM0` |  |
| 182 | WEBSOCKET | 국내주식 실시간체결가 (NXT) | H0NXCNT0 | POST | `/tryitout/H0NXCNT0` |  |
| 183 | WEBSOCKET | ELW 실시간체결가 | H0EWCNT0 | POST | `/tryitout/H0EWCNT0` |  |
| 184 | WEBSOCKET | ELW 실시간예상체결 | H0EWANC0 | POST | `/tryitout/H0EWANC0` |  |
| 185 | WEBSOCKET | 국내주식 실시간예상체결 (NXT) | H0NXANC0 | POST | `/tryitout/H0NXANC0` |  |
| 186 | WEBSOCKET | 국내주식 실시간회원사 (KRX) | H0STMBC0 | POST | `/tryitout/H0STMBC0` |  |
| 187 | WEBSOCKET | 국내주식 실시간예상체결 (통합) | H0UNANC0 | POST | `/tryitout/H0UNANC0` |  |
| 188 | REST | 국내주식 장운영정보 (NXT) | H0NXMKO0 | POST | `/tryitout/H0NXMKO0` |  |
| 189 | WEBSOCKET | 국내ETF NAV추이 | H0STNAV0 | POST | `/tryitout/H0STNAV0` |  |
| 190 | WEBSOCKET | 국내주식 시간외 실시간체결가 (KRX) | H0STOUP0 | POST | `/tryitout/H0STOUP0` |  |

---

## 상세 명세

### 국내지수 실시간예상체결

- **TR_ID**: H0UPANC0
- **Method**: POST
- **URL**: `/tryitout/H0UPANC0`

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
            "tr_id": "H0UPANC0",
            "tr_key": "0001"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0UPANC0", 
        "tr_key": "0001", 
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
0|H0UPANC0|001|0001^085910^2607.71^2^15.85^5424^192338^5424^192338^0.61^0^43
9^201^251^201 |  |


### 국내주식 장운영정보 (통합)

- **TR_ID**: H0UNMKO0
- **Method**: POST
- **URL**: `/tryitout/H0UNMKO0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간회원사 (NXT)

- **TR_ID**: H0NXMBC0
- **Method**: POST
- **URL**: `/tryitout/H0NXMBC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간체결통보

- **TR_ID**: H0STCNI0
- **모의 TR_ID**: H0STCNI9
- **Method**: POST
- **URL**: `/tryitout/H0STCNI0`
- **프로젝트 사용**: ✓

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
                           "tr_id":"H0STCNI0",
                           "tr_key":"HTS ID"
                  }
         }
} |  |
| Response Example | {
    "header": {
        "tr_id": "H0STCNI0", 
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

# output - 주문·정정·취소·거부 접수 통보
HTS ID^1234567801^0000002891^^02^0^01^0^136480^0000000001^000000000^094941^0
^1^1^06010^000000001^김한투^하림^10^^하림^

# output - 체결 통보
HTS ID^1234567801^0000002891^^02^0^00^0^136480^0000000001^000003190^094941^0
^2^2^06010^000000001^김한투^하림^10^^하림^000000000 |  |


### 국내주식 시간외 실시간예상체결 (KRX)

- **TR_ID**: H0STOAC0
- **Method**: POST
- **URL**: `/tryitout/H0STOAC0`

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
                           "tr_id":"H0STOAC0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STOAC0", 
        "tr_key": "005930", 
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
0|H0STOAC0|001|005930^164128^77700^2^100^0.13^78209.85^77600^77800^77
600^77800^77700^82^82^6371400^2^2^0^71.12^6995^5511^1^0.38^69.15^161015^3^100^162004^5^
-100^161015^3^100^20240503^49^N^71160^6882^24644^30955^0.00^0^0.00 |  |


### 국내주식 시간외 실시간호가 (KRX)

- **TR_ID**: H0STOAA0
- **Method**: POST
- **URL**: `/tryitout/H0STOAA0`

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
                           "tr_id":"H0STOAA0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STOAA0", 
        "tr_key": "005930", 
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
0|H0STOAA0|001|005930^164128^B^77800^77900^78000^0^0^0^0^0^0^0^77700^
77600^77500^0^0^0^0^0^0^0^8005^7355^9284^0^0^0^0^0^0^0^4^16654^14297^0^0^0^0^0^0^0^2464
4^30955^0^37426^77700^82^82^100^2^0.13^13069425^-1^0^0^0 |  |


### 국내주식 실시간프로그램매매 (통합)

- **TR_ID**: H0UNPGM0
- **Method**: POST
- **URL**: `/tryitout/H0UNPGM0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간호가 (통합)

- **TR_ID**: H0UNASP0
- **Method**: POST
- **URL**: `/tryitout/H0UNASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간프로그램매매 (KRX)

- **TR_ID**: H0STPGM0
- **Method**: POST
- **URL**: `/tryitout/H0STPGM0`

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
            "tr_id": "H0STPGM0",
            "tr_key": "005930"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STPGM0", 
        "tr_key": "005930", 
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
0|H0STPGM0|001|005930^092237^1413444^109159646900^1189408^91931710200^-2240
36^-17227936700^65033^15475^-49558 |  |


### 국내주식 장운영정보 (KRX)

- **TR_ID**: H0STMKO0
- **Method**: POST
- **URL**: `/tryitout/H0STMKO0`

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
            "tr_id": "H0STMKO0",
            "tr_key": "396300"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STMKO0", 
        "tr_key": "396300", 
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
0|H0STMKO0|001|396300^N^(null)^^311^^^55^N^N |  |


### 국내주식 실시간체결가 (KRX)

- **TR_ID**: H0STCNT0
- **모의 TR_ID**: H0STCNT0
- **Method**: POST
- **URL**: `/tryitout/H0STCNT0`

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
                           "tr_id":"H0STCNT0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STCNT0", 
        "tr_key": "005930", 
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
005930^093354^71900^5^-100^-0.14^72023.83^72100^72400^71700^71900^71800^1^3052
507^219853241700^5105^6937^1832^84.90^1366314^1159996^1^0.39^20.28^090020^5^-2
00^090820^5^-500^092619^2^200^20230612^20^N^65945^216924^1118750^2199206^0.05^
2424142^125.92^0^^72100 |  |


### 국내지수 실시간프로그램매매

- **TR_ID**: H0UPPGM0
- **Method**: POST
- **URL**: `/tryitout/H0UPPGM0`

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
            "tr_id": "H0UPPGM0",
            "tr_key": "0001"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0UPPGM0", 
        "tr_key": "0001", 
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
0|H0UPPGM0|001|0001^085913^0^0^0^0^0^0^1^0^0^0^0^0^1^0^10^0^0^0.00^0^0.00^0^
0.00^0^0.00^0^0.00^0^0.00^0^0.00^1^0.00^1^0.00^10^0.00^1^0.00^9^0.00^0^0.00^1^0.00^1^0.00^10^0
.00^1^0.00^9^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^1^0.00^1^0.00^10^0.00^1^0.0
0^9^0.00^0^0^0^0^1^9^0^0^0^0 |  |


### 국내주식 실시간회원사 (통합)

- **TR_ID**: H0UNMBC0
- **Method**: POST
- **URL**: `/tryitout/H0UNMBC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내지수 실시간체결

- **TR_ID**: H0UPCNT0
- **Method**: POST
- **URL**: `/tryitout/H0UPCNT0`

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
            "tr_id": "H0UPCNT0",
            "tr_key": "0001"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0UPCNT0", 
        "tr_key": "0001", 
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
0|H0UPCNT0|001|0001^091240^2624.54^2^32.68^63952^1650684^439^10335^1.26^2615
.72^2624.82^2610.00^23.86^2^32.96^2^18.14^2^0.92^1.27^0.70^0^670^72^177^0^0^0^19 |  |


### 국내주식 실시간예상체결 (KRX)

- **TR_ID**: H0STANC0
- **Method**: POST
- **URL**: `/tryitout/H0STANC0`

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
                           "tr_id":"H0STANC0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STANC0", 
        "tr_key": "005930", 
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
0|H0STANC0|001|005930^084945^77600^2^1300^1.70^0.00^0^0^0^77600^77
500^64^221986^17226113600^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^
0^20240426^00^N^11591^2878^41034^6265^0.00^0^0.00^B^ |  |


### ELW 실시간호가

- **TR_ID**: H0EWASP0
- **Method**: POST
- **URL**: `/tryitout/H0EWASP0`

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
                           "tr_id":"H0EWASP0",
                           "tr_key":"57JN53"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0EWASP0", 
        "tr_key": "57JN53", 
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
0|H0EWASP0|001|57JN53^090333^0^270^275^280^285^290^295^300^305^310
^315^265^260^255^250^245^240^235^230^225^220^132730^144770^53560^139510^104910^16386
0^111580^41530^66600^41040^119950^176460^142150^218620^148250^160210^154250^141660^1
40270^160640^1000090^1562460^0^0^3^0^0.00^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^
0^0 |  |


### 국내주식 실시간호가 (KRX)

- **TR_ID**: H0STASP0
- **모의 TR_ID**: H0STASP0
- **Method**: POST
- **URL**: `/tryitout/H0STASP0`

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
                           "tr_id":"H0STASP0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STASP0", 
        "tr_key": "005930", 
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
005930^093730^0^71900^72000^72100^72200^72300^72400^72500^72600^72700^72800^71
800^71700^71600^71500^71400^71300^71200^71100^71000^70900^91918^117942^92673^7
9708^106729^141988^176192^113906^134077^104229^95221^159371^220746^284657^2127
42^195370^182710^209747^376432^158171^1159362^2095167^0^0^0^0^525579^-72000^5^
-100.00^3159115^0^8^0^0^0 |  |


### 국내주식 실시간체결가 (통합)

- **TR_ID**: H0UNCNT0
- **Method**: POST
- **URL**: `/tryitout/H0UNCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간호가 (NXT)

- **TR_ID**: H0NXASP0
- **Method**: POST
- **URL**: `/tryitout/H0NXASP0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간프로그램매매 (NXT)

- **TR_ID**: H0NXPGM0
- **Method**: POST
- **URL**: `/tryitout/H0NXPGM0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간체결가 (NXT)

- **TR_ID**: H0NXCNT0
- **Method**: POST
- **URL**: `/tryitout/H0NXCNT0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### ELW 실시간체결가

- **TR_ID**: H0EWCNT0
- **Method**: POST
- **URL**: `/tryitout/H0EWCNT0`

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
                           "tr_id":"H0EWCNT0",
                           "tr_key":"57JN53"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0EWCNT0", 
        "tr_key": "57JN53", 
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
0|H0EWCNT0|001|57JN53^090333^265^2^50^23.26^285.39^305^310^255^265
^260^50^5071350^1447312100^560^310^-250^78.69^2650440^2085570^1^0.42^11.49^090019^5^
-40^090019^5^-45^090316^2^10^20240426^20^N^33300^181460^992350^1655180^265.00^98.62^
1.99^133.32^2.14^0.00^0.00^2.15^49.09^0.37^0.03^24.30^29.04^4.15^17.94^293.24^50.71^
0^0.00^0.00^0^0.00^0 |  |


### ELW 실시간예상체결

- **TR_ID**: H0EWANC0
- **Method**: POST
- **URL**: `/tryitout/H0EWANC0`

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
                           "tr_id":"H0EWANC0",
                           "tr_key":"57JN53"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0EWANC0", 
        "tr_key": "57JN53", 
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


### 국내주식 실시간예상체결 (NXT)

- **TR_ID**: H0NXANC0
- **Method**: POST
- **URL**: `/tryitout/H0NXANC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 실시간회원사 (KRX)

- **TR_ID**: H0STMBC0
- **Method**: POST
- **URL**: `/tryitout/H0STMBC0`

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
            "tr_id": "H0STMBC0",
            "tr_key": "005930"
        }
    }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STMBC0", 
        "tr_key": "005930", 
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
0|H0STMBC0|001|005930^씨티그룹^미래에셋증권^모간서울^BNK증권^키움증권^미래
에셋증권^BNK증권^맥쿼리^NH투자증권^한국증권^903482^703873^484082^471203^246578^946273^571760^
343109^313536^311982^Y^N^Y^N^N^N^N^Y^N^N^00037^00005^00036^00086^00050^00005^00086^00035^0001
2^00003^19.06^14.85^10.21^9.94^5.20^19.96^12.06^7.24^6.61^6.58^14913^5054^7240^80000^3532^280
24^42986^0^5612^3043^1387564^681749^22153^0^-705815^29.27^14.38^^^^^^^^^^ |  |


### 국내주식 실시간예상체결 (통합)

- **TR_ID**: H0UNANC0
- **Method**: POST
- **URL**: `/tryitout/H0UNANC0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내주식 장운영정보 (NXT)

- **TR_ID**: H0NXMKO0
- **Method**: POST
- **URL**: `/tryitout/H0NXMKO0`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) |  |  |
| Response Example |  |  |


### 국내ETF NAV추이

- **TR_ID**: H0STNAV0
- **Method**: POST
- **URL**: `/tryitout/H0STNAV0`

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
                           "tr_id":"H0STNAV0",
                           "tr_key":"069500"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STNAV0", 
        "tr_key": "069500", 
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
0|H0STNAV0|001|069500^37235.46^5^-381.26^-1.01^37646.25^37646.25^37202.10 |  |


### 국내주식 시간외 실시간체결가 (KRX)

- **TR_ID**: H0STOUP0
- **Method**: POST
- **URL**: `/tryitout/H0STOUP0`

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
                           "tr_id":"H0STOUP0",
                           "tr_key":"005930"
                  }
         }
} |  |
| Response Example | # 연결 확인
{
    "header": {
        "tr_id": "H0STOUP0", 
        "tr_key": "005930", 
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
0|H0STOUP0|001|005930^165020^77700^2^100^0.13^78209.85^77600^77800^77
600^77800^77700^1034^13540^1052379900^3^2^-1^71.12^8029^5511^5^0.37^69.15^161015^3^100^
162004^5^-100^161015^3^100^20240503^40^N^7898^6461^24577^38548^0.00^18636724^0.07 |  |

