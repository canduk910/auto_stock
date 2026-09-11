# [해외주식] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


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

- **API ID**: 실시간-021
- **실전 TR_ID**: HDFSASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/HDFSASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 실시간호가 API를 이용하여 미국 실시간 10호가(매수/매도) 시세가 무료로 제공됩니다. (미국은 유료시세 제공 X)

아시아 국가의 경우, HTS(efriend Plus) [7781] 시세신청(실시간) 화면에서 유료 서비스 신청 시, 
"해외주식 실시간호가 HDFSASP0" 을 이용하여 아시아국가 유료시세(실시간호가)를 받아보실 수 있습니다. (24.11.29 반영)
(아시아 국가 무료시세는 "해외주식 지연호가(아시아) HDFSASP1" 를 이용하시기 바랍니다.)

※ 미국 : 실시간 무료, 매수/매도 각 10호가 (0분지연, 나스닥 마켓센터에서 거래되는 호가 및 호가 잔량 정보)
※ 아시아(홍콩, 베트남, 중국, 일본) : 실시간 유료 (단, 중국은 HTS[7781]에서 실시간시세 무료로 신청 후 이용 가능)

해당 API로 미국주간거래(10:00~16:00) 시세 조회도 가능합니다.
※ 미국주간거래 실시간 조회 시, 맨 앞자리(R), tr_key 중 시장구분 값을 다음과 같이 입력 → 나스닥: BAQ, 뉴욕: BAY, 아멕스: BAA

[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

​[미국주식시세 이용시 유의사항]

■ 무료 실시간 시세(나스닥 토탈뷰)를 별도 신청없이 제공하고 있으며, 유료 시세 서비스를 신청하시더라도 OpenAPI의 경우 무료 시세로만 제공하고있습니다. 
 
※ 무료(매수/매도 각 10호가) : 나스닥 마켓센터에서 거래되는 호가 및 호가 잔량 정보
※ 유료(매수/매도 각 1호가) : OpenAPI 서비스 미제공

■ 무료 실시간 시세 서비스는 유료 실시간 시세 서비스 대비 평균 50% 수준에 해당하는 정보이므로 현재가/호가/순간체결량/차트 등에서 일시적·부분적 차이가 
있을 수 있으며 이로 인해 발생하는 손실에 대해서 당사가 책임지지 않습니다.

■ 무료 실시간 시세 서비스의 시가, 저가, 고가, 종가는 유료 실시간 시세 서비스와 다를 수 있으며, 
종목별 과거 데이터(거래량, 시가, 종가, 고가, 차트 데이터 등)는 장 종료 후(오후 12시경) 유료 실시간 시세 서비스 데이터와 동일하게 업데이트됩니다.
(출처: 한국투자증권 외화증권 거래설명서 - https://securities.koreainvestment.com/main/customer/guide/Guide.jsp?&cmd=TF04ag010002¤tPage=1&num=64)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | HDFSASP0 |
| 1 | `tr_key` | R거래소명종목코드 | string | Y | 6 | <미국 야간거래 - 무료시세><br>D+시장구분(3자리)+종목코드<br>예) DNASAAPL : D+NAS(나스닥)+AAPL(애플)<br>[시장구분]<br>NYS : 뉴욕, NAS : 나스닥, AMS : 아멕스<br><미국 주간거래><br>R+시장구분(3자리)+종목코드<br>예) RBAQAAPL : R+BAQ(나스닥)+AAPL(애플)<br>[시장구분]<br>BAY : 뉴욕(주간), BAQ : 나스닥(주간). BAA : 아멕스(주간)<br><아시아국가 - 유료시세><br>※ 유료시세 신청시에만 유료시세 수신가능<br>"포럼 > FAQ > 해외주식 유료시세 신청방법" 참고<br>R+시장구분(3자리)+종목코드<br>예) RHKS00003 : R+HKS(홍콩)+00003(홍콩중화가스)<br>[시장구분]<br>TSE : 도쿄, HKS : 홍콩,<br>SHS : 상해, SZS : 심천<br>HSX : 호치민, HNX : 하노이 |

#### Response Body (71)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `RSYM` | 실시간종목코드 | object | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `SYMB` | 종목코드 | string | Y | 16 |  |
| 2 | `ZDIV` | 소숫점자리수 | string | Y | 1 |  |
| 3 | `XYMD` | 현지일자 | string | Y | 8 |  |
| 4 | `XHMS` | 현지시간 | string | Y | 6 |  |
| 5 | `KYMD` | 한국일자 | string | Y | 8 |  |
| 6 | `KHMS` | 한국시간 | string | Y | 6 |  |
| 7 | `BVOL` | 매수총잔량 | string | Y | 10 |  |
| 8 | `AVOL` | 매도총잔량 | string | Y | 10 |  |
| 9 | `BDVL` | 매수총잔량대비 | string | Y | 10 |  |
| 10 | `ADVL` | 매도총잔량대비 | string | Y | 10 |  |
| 11 | `PBID1` | 매수호가1 | string | Y | 12 |  |
| 12 | `PASK1` | 매도호가1 | string | Y | 12 |  |
| 13 | `VBID1` | 매수잔량1 | string | Y | 10 |  |
| 14 | `VASK1` | 매도잔량1 | string | Y | 10 |  |
| 15 | `DBID1` | 매수잔량대비1 | string | Y | 10 |  |
| 16 | `DASK1` | 매도잔량대비1 | string | Y | 10 |  |
| 17 | `PBID2` | 매수호가2 | string | Y | 12 |  |
| 18 | `PASK2` | 매도호가2 | string | Y | 12 |  |
| 19 | `VBID2` | 매수잔량2 | string | Y | 10 |  |
| 20 | `VASK2` | 매도잔량2 | string | Y | 10 |  |
| 21 | `DBID2` | 매수잔량대비2 | string | Y | 10 |  |
| 22 | `DASK2` | 매도잔량대비2 | string | Y | 10 |  |
| 23 | `PBID3` | 매수호가3 | string | Y | 12 |  |
| 24 | `PASK3` | 매도호가3 | string | Y | 12 |  |
| 25 | `VBID3` | 매수잔량3 | string | Y | 10 |  |
| 26 | `VASK3` | 매도잔량3 | string | Y | 10 |  |
| 27 | `DBID3` | 매수잔량대비3 | string | Y | 10 |  |
| 28 | `DASK3` | 매도잔량대비3 | string | Y | 10 |  |
| 29 | `PBID4` | 매수호가4 | string | Y | 12 |  |
| 30 | `PASK4` | 매도호가4 | string | Y | 12 |  |
| 31 | `VBID4` | 매수잔량4 | string | Y | 10 |  |
| 32 | `VASK4` | 매도잔량4 | string | Y | 10 |  |
| 33 | `DBID4` | 매수잔량대비4 | string | Y | 10 |  |
| 34 | `DASK4` | 매도잔량대비4 | string | Y | 10 |  |
| 35 | `PBID5` | 매수호가5 | string | Y | 12 |  |
| 36 | `PASK5` | 매도호가5 | string | Y | 12 |  |
| 37 | `VBID5` | 매수잔량5 | string | Y | 10 |  |
| 38 | `VASK5` | 매도잔량5 | string | Y | 10 |  |
| 39 | `DBID5` | 매수잔량대비5 | string | Y | 10 |  |
| 40 | `DASK5` | 매도잔량대비5 | string | Y | 10 |  |
| 41 | `PBID6` | 매수호가6 | string | Y | 12 |  |
| 42 | `PASK6` | 매도호가6 | string | Y | 12 |  |
| 43 | `VBID6` | 매수잔량6 | string | Y | 10 |  |
| 44 | `VASK6` | 매도잔량6 | string | Y | 10 |  |
| 45 | `DBID6` | 매수잔량대비6 | string | Y | 10 |  |
| 46 | `DASK6` | 매도잔량대비6 | string | Y | 10 |  |
| 47 | `PBID7` | 매수호가7 | string | Y | 12 |  |
| 48 | `PASK7` | 매도호가7 | string | Y | 12 |  |
| 49 | `VBID7` | 매수잔량7 | string | Y | 10 |  |
| 50 | `VASK7` | 매도잔량7 | string | Y | 10 |  |
| 51 | `DBID7` | 매수잔량대비7 | string | Y | 10 |  |
| 52 | `DASK7` | 매도잔량대비7 | string | Y | 10 |  |
| 53 | `PBID8` | 매수호가8 | string | Y | 12 |  |
| 54 | `PASK8` | 매도호가8 | string | Y | 12 |  |
| 55 | `VBID8` | 매수잔량8 | string | Y | 10 |  |
| 56 | `VASK8` | 매도잔량8 | string | Y | 10 |  |
| 57 | `DBID8` | 매수잔량대비8 | string | Y | 10 |  |
| 58 | `DASK8` | 매도잔량대비8 | string | Y | 10 |  |
| 59 | `PBID9` | 매수호가9 | string | Y | 12 |  |
| 60 | `PASK9` | 매도호가9 | string | Y | 12 |  |
| 61 | `VBID9` | 매수잔량9 | string | Y | 10 |  |
| 62 | `VASK9` | 매도잔량9 | string | Y | 10 |  |
| 63 | `DBID9` | 매수잔량대비9 | string | Y | 10 |  |
| 64 | `DASK9` | 매도잔량대비9 | string | Y | 10 |  |
| 65 | `PBID10` | 매수호가10 | string | Y | 12 |  |
| 66 | `PASK10` | 매도호가10 | string | Y | 12 |  |
| 67 | `VBID10` | 매수잔량10 | string | Y | 10 |  |
| 68 | `VASK10` | 매도잔량10 | string | Y | 10 |  |
| 69 | `DBID10` | 매수잔량대비10 | string | Y | 10 |  |
| 70 | `DASK10` | 매도잔량대비10 | string | Y | 10 |  |

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
            "tr_id": "HDFSASP0",
            "tr_key": "RBAQAAPL"
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
0|HDFSASP0|001|RBAQAAPL^AAPL^4^20240506^202223^20240507^092223^1482^381^0^-10^182.8500^182.8700^350^57^0^-10^182.8400^182.9000^1^10^0^0^182.8300^182.9100^6^54^0^0^182.7900^182.9500^54^5^0^0^182.7500^182.9600^309^3^0^0^182.7300^182.9700^20^81^0^0^182.7000^182.9800^124^3^0^0^182.6600^182.9900^397^1^0^0^182.6500^183.0000^20^69^0^0^182.6300^183.0100^201^98^0^0
```

</details>



### 해외주식 지연호가(아시아)

- **API ID**: 실시간-008
- **실전 TR_ID**: HDFSASP1
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/HDFSASP1`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `제공 안함`

<details><summary>개요</summary>

```text
해외주식 지연호가(아시아)의 경우 아시아 무료시세(지연호가)가 제공됩니다.

HTS(efriend Plus) [7781] 시세신청(실시간) 화면에서 유료 서비스 신청 시, 
"해외주식 실시간호가 HDFSASP0" 을 이용하여 아시아국가 유료시세(실시간호가)를 받아보실 수 있습니다. (24.11.29 반영)

※ 지연시세 지연시간 : 홍콩, 베트남, 중국, 일본 - 15분지연

[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | HDFSASP1 |
| 1 | `tr_key` | D거래소명종목코드 | string | Y | 6 | <아시아국가 - 무료시세><br>D+시장구분(3자리)+종목코드<br>예) DHKS00003 : D+HKS(홍콩)+00003(홍콩중화가스)<br>[시장구분]<br>TSE : 도쿄, HKS : 홍콩,<br>SHS : 상해, SZS : 심천<br>HSX : 호치민, HNX : 하노이 |

#### Response Body (17)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `RSYM` | 실시간종목코드 | string | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `SYMB` | 종목코드 | string | Y | 16 |  |
| 2 | `ZDIV` | 소수점자리수 | string | Y | 1 |  |
| 3 | `XYMD` | 현지일자 | string | Y | 8 |  |
| 4 | `XHMS` | 현지시간 | string | Y | 6 |  |
| 5 | `KYMD` | 한국일자 | string | Y | 8 |  |
| 6 | `KHMS` | 한국시간 | string | Y | 6 |  |
| 7 | `BVOL` | 매수총잔량 | string | Y | 10 |  |
| 8 | `AVOL` | 매도총잔량 | string | Y | 10 |  |
| 9 | `BDVL` | 매수총잔량대비 | string | Y | 10 |  |
| 10 | `ADVL` | 매도총잔량대비 | string | Y | 10 |  |
| 11 | `PBID1` | 매수호가1 | string | Y | 12 |  |
| 12 | `PASK1` | 매도호가1 | string | Y | 12 |  |
| 13 | `VBID1` | 매수잔량1 | string | Y | 10 |  |
| 14 | `VASK1` | 매도잔량1 | string | Y | 10 |  |
| 15 | `DBID1` | 매수잔량대비1 | string | Y | 10 |  |
| 16 | `DASK1` | 매도잔량대비1 | string | Y | 10 |  |


### 해외주식 실시간지연체결가

- **API ID**: 실시간-007
- **실전 TR_ID**: HDFSCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/HDFSCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 실시간지연체결가의 경우 기본적으로 무료시세(지연체결가)가 제공되며, 
아시아 국가의 경우 HTS(efriend Plus) [7781] 시세신청(실시간) 화면에서 유료 서비스 신청 시 API로도 유료시세(실시간체결가)를 받아보실 수 있습니다. (24.11.29 반영)

※ 지연시세 지연시간 : 미국 - 실시간무료(0분지연) / 홍콩, 베트남, 중국, 일본 - 15분지연 (중국은 실시간시세 신청 시 무료실시간시세 제공)
   미국의 경우 0분지연시세로 제공되나, 장중 당일 시가는 상이할 수 있으며, 익일 정정 표시됩니다.

해당 API로 미국주간거래(10:00~16:00) 시세 조회도 가능합니다. 
※ 미국주간거래 실시간 조회 시, 맨 앞자리(R), tr_key 중 시장구분 값을 다음과 같이 입력 → 나스닥: BAQ, 뉴욕: BAY, 아멕스: BAA

[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 2 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | HDFSCNT0 |
| 1 | `tr_key` | D거래소명종목코드 | string | Y | 6 | <미국 야간거래/아시아 주간거래 - 무료시세><br>D+시장구분(3자리)+종목코드<br>예) DNASAAPL : D+NAS(나스닥)+AAPL(애플)<br>[시장구분]<br>NYS : 뉴욕, NAS : 나스닥, AMS : 아멕스 ,<br>TSE : 도쿄, HKS : 홍콩,<br>SHS : 상해, SZS : 심천<br>HSX : 호치민, HNX : 하노이<br><미국 야간거래/아시아 주간거래 - 유료시세><br>※ 유료시세 신청시에만 유료시세 수신가능<br>"포럼 > FAQ > 해외주식 유료시세 신청방법" 참고<br>R+시장구분(3자리)+종목코드<br>예) RNASAAPL : R+NAS(나스닥)+AAPL(애플)<br>[시장구분]<br>NYS : 뉴욕, NAS : 나스닥, AMS : 아멕스 ,<br>TSE : 도쿄, HKS : 홍콩,<br>SHS : 상해, SZS : 심천<br>HSX : 호치민, HNX : 하노이<br><미국 주간거래><br>R+시장구분(3자리)+종목코드<br>예) RBAQAAPL : R+BAQ(나스닥)+AAPL(애플)<br>[시장구분]<br>BAY : 뉴욕(주간), BAQ : 나스닥(주간). BAA : 아멕스(주간) |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `RSYM` | 실시간종목코드 | string | Y | 16 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `SYMB` | 종목코드 | string | Y | 16 |  |
| 2 | `ZDIV` | 수수점자리수 | string | Y | 1 |  |
| 3 | `TYMD` | 현지영업일자 | string | Y | 8 |  |
| 4 | `XYMD` | 현지일자 | string | Y | 6 |  |
| 5 | `XHMS` | 현지시간 | string | Y | 6 |  |
| 6 | `KYMD` | 한국일자 | string | Y | 6 |  |
| 7 | `KHMS` | 한국시간 | string | Y | 6 |  |
| 8 | `OPEN` | 시가 | string | Y | 6 |  |
| 9 | `HIGH` | 고가 | string | Y | 6 |  |
| 10 | `LOW` | 저가 | string | Y | 6 |  |
| 11 | `LAST` | 현재가 | string | Y | 6 |  |
| 12 | `SIGN` | 대비구분 | string | Y | 6 |  |
| 13 | `DIFF` | 전일대비 | string | Y | 8 |  |
| 14 | `RATE` | 등락율 | string | Y | 6 |  |
| 15 | `PBID` | 매수호가 | string | Y | 10 |  |
| 16 | `PASK` | 매도호가 | string | Y | 10 |  |
| 17 | `VBID` | 매수잔량 | string | Y | 10 |  |
| 18 | `VASK` | 매도잔량 | string | Y | 10 |  |
| 19 | `EVOL` | 체결량 | string | Y | 12 |  |
| 20 | `TVOL` | 거래량 | string | Y | 12 |  |
| 21 | `TAMT` | 거래대금 | string | Y | 10 |  |
| 22 | `BIVL` | 매도체결량 | string | Y | 10 | 매수호가가 매도주문 수량을 따라가서 체결된것을 표현하여 BIVL 이라는 표현을 사용 |
| 23 | `ASVL` | 매수체결량 | string | Y | 10 | 매도호가가 매수주문 수량을 따라가서 체결된것을 표현하여 ASVL 이라는 표현을 사용 |
| 24 | `STRN` | 체결강도 | string | Y | 10 |  |
| 25 | `MTYP` | 시장구분 1:장중,2:장전,3:장후 | string | Y | 10 |  |


### 해외주식 실시간체결통보

- **API ID**: 실시간-009
- **실전 TR_ID**: H0GSCNI0
- **모의 TR_ID**: H0GSCNI9
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0GSCNI0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `ws://ops.koreainvestment.com:31000`

<details><summary>개요</summary>

```text
[참고자료]

실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 2 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | [실전투자]<br>H0GSCNI0 : 실시간 해외주식 체결통보<br>[모의투자]<br>H0GSCNI9 : 실시간 해외주식 체결통보 |
| 1 | `tr_key` | HTSID | string | Y | 8 | HTSID |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CUST_ID` | 고객 ID | string | Y | 8 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `ACNT_NO` | 계좌번호 | string | Y | 10 |  |
| 2 | `ODER_NO` | 주문번호 | string | Y | 10 |  |
| 3 | `OODER_NO` | 원주문번호 | string | Y | 10 |  |
| 4 | `SELN_BYOV_CLS` | 매도매수구분 | string | Y | 2 | 01:매도 02:매수 03:전매도 04:환매수 |
| 5 | `RCTF_CLS` | 정정구분 | string | Y | 1 | 0:정상 1:정정 2:취소 |
| 6 | `ODER_KIND2` | 주문종류2 | string | Y | 1 | 1:시장가 2:지정자 6:단주시장가 7:단주지정가<br>A:MOO B:LOO C:MOC D:LOC |
| 7 | `STCK_SHRN_ISCD` | 주식 단축 종목코드 | string | Y | 9 |  |
| 8 | `CNTG_QTY` | 체결수량 | string | Y | 10 | - 주문통보의 경우 해당 위치에 주문수량이 출력<br>- 체결통보인 경우 해당 위치에 체결수량이 출력 |
| 9 | `CNTG_UNPR` | 체결단가 | string | Y | 9 | ※ 주문통보 시에는 주문단가가, 체결통보 시에는 체결단가가 수신 됩니다.<br>※ 체결단가의 경우, 국가에 따라 소수점 생략 위치가 상이합니다.<br>미국 4 일본 1 중국 3 홍콩 3 베트남 0<br>EX) 미국 AAPL(현재가 : 148.0100)의 경우 001480100으로 체결단가가 오는데, <br>4번째 자리에 소수점을 찍어 148.01로 해석하시면 됩니다. |
| 10 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 | 특정 거래소의 체결시간 데이터는 수신되지 않습니다. <br>체결시간 데이터가 필요할 경우, 체결통보 데이터 수신 시 타임스탬프를 찍는 것으로 대체하시길 바랍니다. |
| 11 | `RFUS_YN` | 거부여부 | string | Y | 1 | 0:정상 1:거부 |
| 12 | `CNTG_YN` | 체결여부 | string | Y | 1 | 1:주문,정정,취소,거부 2:체결 |
| 13 | `ACPT_YN` | 접수여부 | string | Y | 1 | 1:주문접수 2:확인 3:취소(FOK/IOC) |
| 14 | `BRNC_NO` | 지점번호 | string | Y | 5 |  |
| 15 | `ODER_QTY` | 주문 수량 | string | Y | 9 | - 주문통보인 경우 해당 위치 미출력 (주문통보의 주문수량은 CNTG_QTY 위치에 출력)<br>- 체결통보인 경우 해당 위치에 주문수량이 출력 |
| 16 | `ACNT_NAME` | 계좌명 | string | Y | 12 |  |
| 17 | `CNTG_ISNM` | 체결종목명 | string | Y | 14 |  |
| 18 | `ODER_COND` | 해외종목구분 | string | Y | 1 | 4:홍콩(HKD) 5:상해B(USD) <br>6:NASDAQ 7:NYSE 8:AMEX 9:OTCB<br>C:홍콩(CNY) A:상해A(CNY) B:심천B(HKD)<br>D:도쿄 E:하노이 F:호치민 |
| 19 | `DEBT_GB` | 담보유형코드 | string | Y | 2 | 10:현금 15:해외주식담보대출 |
| 20 | `DEBT_DATE` | 담보대출일자 | string | Y | 8 | 대출일(YYYYMMDD) |
| 21 | `START_TM` | 분할매수/매도 시작시간 | string | Y | 6 | HHMMSS |
| 22 | `END_TM` | 분할매수/매도 종료시간 | string | Y | 6 | HHMMSS |
| 23 | `TM_DIV_TP` | 시간분할타입유형 | string | Y | 2 | 00 시간직접설정, 02 : 정규장까지 |
| 24 | `CNTG_UNPR12` | 체결단가12 | string | Y | 12 |  |

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
                           "tr_id":"H0GSCNI0",
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
시간분할타입유형  []
```

</details>


