# OAuth인증 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (4개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 1 | REST | Hashkey | - | POST | `/uapi/hashkey` |  |
| 2 | WEBSOCKET | 실시간 (웹소켓) 접속키 발급 | - | POST | `/oauth2/Approval` |  |
| 3 | REST | 접근토큰폐기(P) | - | POST | `/oauth2/revokeP` |  |
| 4 | REST | 접근토큰발급(P) | - | POST | `/oauth2/tokenP` |  |

---

## 상세 명세

### Hashkey

- **TR_ID**: -
- **Method**: POST
- **URL**: `/uapi/hashkey`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"ORD_PRCS_DVSN_CD": "02",
	"CANO": "계좌번호",
	"ACNT_PRDT_CD": "03",
	"SLL_BUY_DVSN_CD": "02",
	"SHTN_PDNO": "101S06",
	"ORD_QTY": "1",
	"UNIT_PRICE": "370",
	"NMPR_TYPE_CD": "",
	"KRX_NMPR_CNDT_CD": "",
	"CTAC_TLNO": "",
	"FUOP_ITEM_DVSN_CD": "",
	"ORD_DVSN_CD": "02"
} |  |
| Response Example | {
  "BODY": {
    "ORD_PRCS_DVSN_CD": "02",
    "CANO": "계좌번호",
    "ACNT_PRDT_CD": "03",
    "SLL_BUY_DVSN_CD": "02",
    "SHTN_PDNO": "101S06",
    "ORD_QTY": "1",
    "UNIT_PRICE": "370",
    "NMPR_TYPE_CD": "",
    "KRX_NMPR_CNDT_CD": "",
    "CTAC_TLNO": "",
    "FUOP_ITEM_DVSN_CD": "",
    "ORD_DVSN_CD": "02"
  },
  "HASH": "8b84068222a49302f7ef58226d90403f62e216828f8103465f900de0e7be2f0f"
} |  |


### 실시간 (웹소켓) 접속키 발급

- **TR_ID**: -
- **Method**: POST
- **URL**: `/oauth2/Approval`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"grant_type": "client_credentials",
	"appkey": "PSg5dctL9dKPo727J13Ur405OSXXXXXXXXXX",
	"secretkey": "yo2t8zS68zpdjGuWvFyM9VikjXE0i0CbgPEamnqPA00G0bIfrdfQb2RUD1xP7SqatQXr1cD1fGUNsb78MMXoq6o4lAYt9YTtHAjbMoFy+c72kbq5owQY1Pvp39/x6ejpJlXCj7gE3yVOB/h25Hvl+URmYeBTfrQeOqIAOYc/OIXXXXXXXXXX"
} |  |
| Response Example | {
    "approval_key": "a2585daf-8c09-4587-9fce-8ab893XXXXX"
} |  |


### 접근토큰폐기(P)

- **TR_ID**: -
- **Method**: POST
- **URL**: `/oauth2/revokeP`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
  "appkey" : "PSw2UvBQCpoZFc7nZpIfIrOttmXXXXXXXXXX",
  "appsecret" : "/g84gaZp7W3DJEZhamiTH8ZdJkUJ8603rjo3HcOm5PvIc1YC3YmyJOQoW1H0kNjo4IbHwGUdi3+9oEbH4RKKl8GnEu3n/khxm0OrwHkQur+wbA74fcFXxaUnEbftu0X72Eaw9dEBMuK3rODeeOanrsJ1kZ9oKWykIG04F0nmgdXXXXXXXXXX",
  "token" : "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0b2tlbiIsImF1ZCI6IjZmNDgxMjBiLTlmMDItNGI5ZS05MGExLTRiNDk2MGM5ZWY2MyIsImlzcyI6InVub2d3IiwiZXhwIjoxNjQzMjg2MDUzLCJpYXQiOjE2NDMxOTk2NTMsImp0aSI6IlBTdzJVdkJRQ3dvWkZhOG5acElmSXJPdHRtZUtLUGZCclNKcyJ9.6Z-UvArobBfXbnpSFbFhd9WPVEM3ZQa5NEpqfmQ6rrZBISCi-P9CEamfVReIduTVYbafF02Pl6EPXXXXXXXXXX"
} |  |
| Response Example | {
  "code" : 200,
  "message" : "접근토큰 폐기에 성공하였습니다"
} |  |


### 접근토큰발급(P)

- **TR_ID**: -
- **Method**: POST
- **URL**: `/oauth2/tokenP`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
  "grant_type": "client_credentials",
  "appkey": "PSg5dctL9dKPo727J13Ur405OSXXXXXXXXXX",
  "appsecret":  "yo2t8zS68zpdjGuWvFyM9VikjXE0i0CbgPEamnqPA00G0bIfrdfQb2RUD1xP7SqatQXr1cD1fGUNsb78MMXoq6o4lAYt9YTtHAjbMoFy+c72kbq5owQY1Pvp39/x6ejpJlXCj7gE3yVOB/h25Hvl+URmYeBTfrQeOqIAOYc/OIXXXXXXXXXX"
} |  |
| Response Example | {
	"access_token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0b2tlbiIsImF1ZCI6ImMwNzM1NTYzLTA1MjctNDNhZS05ODRiLTJiNWI1ZWZmOWYyMyIsImlzcyI6InVub2d3IiwiZXhwIjoxNjQ5NzUxMTAwLCJpYXQiOjE2NDE5NzUxMDAsImp0aSI6IkJTZlM0QUtSSnpRVGpmdHRtdXZlenVQUTlKajc3cHZGdjBZVyJ9.Oyt_C639yUjWmRhymlszgt6jDo8fvIKkkxH1mMngunV1T15SCC4I3Xe6MXxcY23DXunzBfR1uI0KXXXXXXXXXX",
	"access_token_token_expired":"2023-12-22 08:16:59",
	"token_type":"Bearer",
	"expires_in":86400
} |  |

