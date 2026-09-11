# [해외선물옵션] 기본시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


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

- **API ID**: v1_해외선물-009
- **실전 TR_ID**: HHDFC55010000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석


[참고자료]
※ 종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
   https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
   
※ 모의투자는 실전투자계좌를 활용하여 조회 부탁드립니다.

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55010000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | 법인 : "001" / default   개인: "" |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) CNHU24<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수선물" 참고 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (36)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세1 | object | N |  |  |
| 4 | `proc_date` | 최종처리일자 | string | N | 8 | 최종처리일자 |
| 5 | `high_price` | 고가 | string | N | 15 | 고가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 6 | `proc_time` | 최종처리시각 | string | N | 6 | 최종처리시각 |
| 7 | `open_price` | 시가 | string | N | 15 | 시가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 8 | `trst_mgn` | 증거금 | string | N | 19 | 증거금 |
| 9 | `low_price` | 저가 | string | N | 15 | 저가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 10 | `last_price` | 현재가 | string | N | 15 | 현재가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 11 | `vol` | 누적거래수량 | string | N | 10 | 누적거래수량 |
| 12 | `prev_diff_flag` | 전일대비구분 | string | N | 1 | 전일대비구분<br>'1':상한 '2':상승 '3':보합 '4':하한 '5':하락 |
| 13 | `prev_diff_price` | 전일대비가격 | string | N | 15 | 전일대비가격 |
| 14 | `prev_diff_rate` | 전일대비율 | string | N | 10 | 전일대비율 |
| 15 | `bid_qntt` | 매수1수량 | string | N | 10 | 매수1수량 |
| 16 | `bid_price` | 매수1호가 | string | N | 15 | 매수1호가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 17 | `ask_qntt` | 매도1수량 | string | N | 10 | 매도1수량 |
| 18 | `ask_price` | 매도1호가 | string | N | 15 | 매도1호가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 19 | `prev_price` | 전일종가 | string | N | 15 | 전일종가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 20 | `exch_cd` | 거래소코드 | string | N | 10 | 거래소코드 |
| 21 | `crc_cd` | 거래통화 | string | N | 10 | 거래통화 |
| 22 | `trd_fr_date` | 상장일 | string | N | 8 | 상장일 |
| 23 | `expr_date` | 만기일 | string | N | 8 | 만기일 |
| 24 | `trd_to_date` | 최종거래일 | string | N | 8 | 최종거래일 |
| 25 | `remn_cnt` | 잔존일수 | string | N | 4 | 잔존일수 |
| 26 | `last_qntt` | 체결량 | string | N | 10 | 체결량 |
| 27 | `tot_ask_qntt` | 총매도잔량 | string | N | 10 | 총매도잔량 |
| 28 | `tot_bid_qntt` | 총매수잔량 | string | N | 10 | 총매수잔량 |
| 29 | `tick_size` | 틱사이즈 | string | N | 19 | 틱사이즈 |
| 30 | `open_date` | 장개시일자 | string | N | 8 | 장개시일자 |
| 31 | `open_time` | 장개시시각 | string | N | 6 | 장개시시각 |
| 32 | `close_date` | 장종료일자 | string | N | 8 | 장종료일자 |
| 33 | `close_time` | 장종료시각 | string | N | 6 | 장종료시각 |
| 34 | `sbsnsdate` | 영업일자 | string | N | 8 | 영업일자 |
| 35 | `sttl_price` | 정산가 | string | N | 15 | 정산가 |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:BRNF25
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물종목상세

- **API ID**: v1_해외선물-008
- **실전 TR_ID**: HHDFC55010100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/stock-detail`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석.
	   

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55010100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | 법인 : "001" / default   개인: "" |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) CNHU24<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수선물" 참고 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (27)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세1 | object | N |  |  |
| 4 | `exch_cd` | 거래소코드 | string | N | 10 | 거래소코드 |
| 5 | `tick_sz` | 틱사이즈 | string | N | 19 | 틱사이즈 |
| 6 | `disp_digit` | 가격표시진법 | string | N | 10 | 가격표시진법 |
| 7 | `trst_mgn` | 증거금 | string | N | 19 | 증거금 |
| 8 | `sttl_date` | 정산일 | string | N | 8 | 정산일 |
| 9 | `prev_price` | 전일종가 | string | N | 15 | 전일종가<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 10 | `crc_cd` | 거래통화 | string | N | 10 | 거래통화 |
| 11 | `clas_cd` | 품목종류 | string | N | 3 | 품목종류 |
| 12 | `tick_val` | 틱가치 | string | N | 19 | 틱가치 |
| 13 | `mrkt_open_date` | 장개시일자 | string | N | 8 | 장개시일자 |
| 14 | `mrkt_open_time` | 장개시시각 | string | N | 6 | 장개시시각 |
| 15 | `mrkt_close_date` | 장마감일자 | string | N | 8 | 장마감일자 |
| 16 | `mrkt_close_time` | 장마감시각 | string | N | 6 | 장마감시각 |
| 17 | `trd_fr_date` | 상장일 | string | N | 8 | 상장일 |
| 18 | `expr_date` | 만기일 | string | N | 8 | 만기일 |
| 19 | `trd_to_date` | 최종거래일 | string | N | 8 | 최종거래일 |
| 20 | `remn_cnt` | 잔존일수 | string | N | 4 | 잔존일수 |
| 21 | `stat_tp` | 매매여부 | string | N | 1 | 매매여부 |
| 22 | `ctrt_size` | 계약크기 | string | N | 19 | 계약크기 |
| 23 | `stl_tp` | 최종결제구분 | string | N | 20 | 최종결제구분 |
| 24 | `frst_noti_date` | 최초식별일 | string | N | 8 | 최초식별일 |
| 25 | `sprd_srs_cd1` | 스프레드 종목 #1 | string | N | 32 |  |
| 26 | `sprd_srs_cd2` | 스프레드 종목 #2 | string | N | 32 |  |

<details><summary>Request Example (Python)</summary>

```json
{
     "SRS_CD": "6AU22"
 }
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 호가

- **API ID**: 해외선물-031
- **실전 TR_ID**: HHDFC86000000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-asking-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물 호가 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [8602] 해외선물옵션 종합주문(Ⅰ) 화면에서 "왼쪽 호가 창" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외선물옵션시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드 - 해외선물옵션 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물옵션정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석


[참고자료]
※ 종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
   https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC86000000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목명 | string | Y | 32 | 종목코드 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (21)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `open_price` | 시가 | string | Y | 15 |  |
| 5 | `high_price` | 고가 | string | Y | 15 |  |
| 6 | `lowp_rice` | 저가 | string | Y | 15 |  |
| 7 | `last_price` | 현재가 | string | Y | 15 |  |
| 8 | `prev_price` | 전일종가 | string | Y | 15 |  |
| 9 | `vol` | 거래량 | string | Y | 10 |  |
| 10 | `prev_diff_price` | 전일대비가 | string | Y | 15 |  |
| 11 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |
| 12 | `quot_date` | 호가수신일자 | string | Y | 8 |  |
| 13 | `quot_time` | 호가수신시각 | string | Y | 6 |  |
| 14 | `output2` | 응답상세 | object array | Y |  | array |
| 15 | `bid_qntt` | 매수수량 | string | Y | 10 |  |
| 16 | `bid_num` | 매수번호 | string | Y | 10 |  |
| 17 | `bid_price` | 매수호가 | string | Y | 15 |  |
| 18 | `ask_qntt` | 매도수량 | string | Y | 10 |  |
| 19 | `ask_num` | 매도번호 | string | Y | 10 |  |
| 20 | `ask_price` | 매도호가 | string | Y | 15 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:6AM24
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 분봉조회

- **API ID**: 해외선물-016
- **실전 TR_ID**: HHDFC55020400
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-time-futurechartprice`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물분봉조회 API입니다. ★ 반드시 아래 호출방법을 확인하시고 호출 사용하시기 바랍니다.
한국투자 HTS(eFriend Plus) &gt; [5502] 해외선물옵션 체결추이 화면에서 "분" 선택 시 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.


※ 해외선물분봉조회 조회 방법
params
. START_DATE_TIME: 공란 입력 ("")
. CLOSE_DATE_TIME: 조회일자 입력 ("20231214")
. QRY_CNT: 120 입력 시, 가장 최근 분봉 120건 조회( 한번에 최대 120건 조회 가능)
                240 입력 시, 240 이전 분봉 ~ 120 이전 분봉 조회
                360 입력 시, 360 이전 분봉 ~ 240 이전 분봉 조회
. QRY_TP: 처음조회시, 공백 입력
              다음조회시, P 입력
. INDEX_KEY: 처음조회시, 공백 입력
                  다음조회시, 이전 조회 응답의 output2 &gt; index_key 값 입력

* 따라서 분봉데이터를 기간별로 수집하고자 하실 경우 QRY_TP, INDEX_KEY 값을 이용하시면서 다음조회하시면 됩니다.

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55020400 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) CNHU24<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수선물" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | 공백 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | ex) 20230823 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 120 (조회갯수) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 5 (분간격) |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 다음조회(QRY_TP를 P로 입력) 시, 이전 호출의 "output1 > index_key" 기입하여 조회 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output1` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시각 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:BRNQ24
EXCH_CD:ICE
START_DATE_TIME:
CLOSE_DATE_TIME:20231212
QRY_TP:P
QRY_CNT:500
QRY_GAP:1
INDEX_KEY:20231211       128
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 체결추이(틱)

- **API ID**: 해외선물-019
- **실전 TR_ID**: HHDFC55020200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/tick-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물옵션 체결추이(틱) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [5502] 해외선물옵션 체결추이 화면에서 "Tick" 선택 시 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55020200 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | 예) 6AM24 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 예) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | 공백 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | 예) 20240402 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 30 (최대 40) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 공백 (분만 사용) |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `tret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시각 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240423
QRY_TP:Q
QRY_CNT:40
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 체결추이(주간)

- **API ID**: 해외선물-017
- **실전 TR_ID**: HHDFC55020000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/weekly-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물옵션 체결추이(주간) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [5502] 해외선물옵션 체결추이 화면에서 "주간" 선택 시 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55020000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | 예) 6AM24 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 예) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | 공백 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | 예) 20240402 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 30 (최대 40) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 공백 (분만 사용) |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시각 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 |  |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240424
QRY_TP:
QRY_CNT:40
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 체결추이(일간)

- **API ID**: 해외선물-018
- **실전 TR_ID**: HHDFC55020100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/daily-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물옵션 체결추이(일간) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [5502] 해외선물옵션 체결추이 화면에서 "일간" 선택 시 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55020100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | 예) 6AM24 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 예) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | 공백 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | 예) 20240402 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 30 (최대 40) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 공백 (분만 사용) |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `tret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시각 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 |  |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240424
QRY_TP:
QRY_CNT:40
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 체결추이(월간)

- **API ID**: 해외선물-020
- **실전 TR_ID**: HHDFC55020300
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/monthly-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물옵션 체결추이(월간) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [5502] 해외선물옵션 체결추이 화면에서 "월간" 선택 시 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외선물시세 출력값을 해석하실 때 ffcode.mst(해외선물종목마스터 파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- ffcode.mst(해외선물종목마스터 파일) 다운로드 방법 2가지
  1) 한국투자증권 Github의 파이썬 샘플코드를 사용하여 mst 파일 다운로드 및 excel 파일로 정제   
     https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/overseas_future_code.py
   
  2) 혹은 포럼 - FAQ - 종목정보 다운로드(해외) - 해외지수선물 클릭하셔서 ffcode.mst(해외선물종목마스터 파일)을 다운로드 후
     Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외선물정보.h)를 참고하여 해석

- 소수점 계산 시, ffcode.mst(해외선물종목마스터 파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) ffcode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 6A 계산소수점 -4 → 시세 6882.5 수신 시 0.68825 로 해석
       품목코드 GC 계산소수점 -1 → 시세 19225 수신 시 1922.5 로 해석

※ CME, SGX 거래소 API시세는 유료시세로 HTS/MTS에서 유료가입 후 익일부터 시세 이용 가능합니다.
포럼 &gt; FAQ &gt; 해외선물옵션 API 유료시세 신청방법(CME, SGX 거래소)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55020300 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | 예) 6AM24 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 예) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | 공백 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | 예) 20240402 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 30 (최대 40) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 공백 (분만 사용) |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `tret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시각 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 |  |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:6AM24
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:20240423
QRY_TP:
QRY_CNT:30
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 상품기본정보

- **API ID**: 해외선물-023
- **실전 TR_ID**: HHDFC55200000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/search-contract-detail`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물옵션 상품기본정보 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0054] 해외선물옵션 상품기본정보 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

QRY_CNT에 SRS_CD 요청 개수 입력, SRS_CD_01 ~SRS_CD_32 까지 최대 32건의 상품코드 추가 입력하여 해외선물옵션 상품기본정보 확인이 가능합니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFC55200000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `QRY_CNT` | 요청개수 | string | Y | 4 | 입력한 코드 개수 |
| 1 | `SRS_CD_01` | 품목종류 | string | Y | 32 | 최대 32개 까지 가능 |
| 2 | `SRS_CD_02…` | 품목종류… | string | Y | 32 |  |
| 3 | `SRS_CD_32` | 품목종류 | string | Y | 32 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object array | Y |  | array |
| 4 | `exch_cd` | 거래소코드 | string | Y | 10 |  |
| 5 | `clas_cd` | 품목종류 | string | Y | 3 |  |
| 6 | `crc_cd` | 거래통화 | string | Y | 10 |  |
| 7 | `sttl_price` | 정산가 | string | Y | 15 |  |
| 8 | `sttl_date` | 정산일 | string | Y | 8 |  |
| 9 | `trst_mgn` | 증거금 | string | Y | 19 |  |
| 10 | `disp_digit` | 가격표시진법 | string | Y | 10 |  |
| 11 | `tick_sz` | 틱사이즈 | string | Y | 19 |  |
| 12 | `tick_val` | 틱가치 | string | Y | 19 |  |
| 13 | `mrkt_open_date` | 장개시일자 | string | Y | 8 |  |
| 14 | `mrkt_open_time` | 장개시시각 | string | Y | 6 |  |
| 15 | `mrkt_close_date` | 장마감일자 | string | Y | 8 |  |
| 16 | `mrkt_close_time` | 장마감시각 | string | Y | 6 |  |
| 17 | `trd_fr_date` | 상장일 | string | Y | 8 |  |
| 18 | `expr_date` | 만기일 | string | Y | 8 |  |
| 19 | `trd_to_date` | 최종거래일 | string | Y | 8 |  |
| 20 | `remn_cnt` | 잔존일수 | string | Y | 4 |  |
| 21 | `stat_tp` | 매매여부 | string | Y | 1 |  |
| 22 | `ctrt_size` | 계약크기 | string | Y | 19 |  |
| 23 | `stl_tp` | 최종결제구분 | string | Y | 20 |  |
| 24 | `frst_noti_date` | 최초식별일 | string | Y | 8 |  |
| 25 | `sub_exch_nm` | 서브거래소코드 | string | Y | 32 |  |

<details><summary>Request Example (Python)</summary>

```text
QRY_CNT:2
SRS_CD_01:6AM24
SRS_CD_02:10YK24
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물 미결제추이

- **API ID**: 해외선물-029
- **실전 TR_ID**: HHDDB95030000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/investor-unpd-trend`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물 미결제추이 API입니다.
한국투자 HTS(eFriend Plus) &gt; [1959] 해외선물 미결제추이의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDDB95030000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `PROD_ISCD` | 상품 | string | Y | 5 | 금리 (GE, ZB, ZF,ZN,ZT), 금속(GC, PA, PL,SI, HG), 농산물(CC, CT,KC, OJ, SB, ZC,ZL, ZM, ZO, ZR, ZS, ZW), 에너지(CL, HO, NG, WBS), 지수(ES, NQ, TF, YM, VX), 축산물(GF, HE, LE), 통화(6A, 6B, 6C, 6E, 6J, 6N, 6S, DX) |
| 1 | `BSOP_DATE` | 일자 | string | Y | 8 | 기준일(ex)20240513) |
| 2 | `UPMU_GUBUN` | 구분 | string | Y | 1 | 0(수량), 1(증감) |
| 3 | `CTS_KEY` | CTS_KEY | string | Y | 16 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (23)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `row_cnt` | 응답레코드카운트 | string | Y | 4 |  |
| 5 | `output2` | 응답상세 | object array | Y |  | array |
| 6 | `prod_iscd` | 상품 | string | Y | 5 |  |
| 7 | `cftc_iscd` | CFTC코드 | string | Y | 10 |  |
| 8 | `bsop_date` | 일자 | string | Y | 8 |  |
| 9 | `bidp_spec` | 매수투기 | string | Y | 10 |  |
| 10 | `askp_spec` | 매도투기 | string | Y | 10 |  |
| 11 | `spread_spec` | 스프레드투기 | string | Y | 10 |  |
| 12 | `bidp_hedge` | 매수헤지 | string | Y | 10 |  |
| 13 | `askp_hedge` | 매도헤지 | string | Y | 10 |  |
| 14 | `hts_otst_smtn` | 미결제합계 | string | Y | 10 |  |
| 15 | `bidp_missing` | 매수누락 | string | Y | 10 |  |
| 16 | `askp_missing` | 매도누락 | string | Y | 10 |  |
| 17 | `bidp_spec_cust` | 매수투기고객 | string | Y | 10 |  |
| 18 | `askp_spec_cust` | 매도투기고객 | string | Y | 10 |  |
| 19 | `spread_spec_cust` | 스프레드투기고객 | string | Y | 10 |  |
| 20 | `bidp_hedge_cust` | 매수헤지고객 | string | Y | 10 |  |
| 21 | `askp_hedge_cust` | 매도헤지고객 | string | Y | 10 |  |
| 22 | `cust_smtn` | 고객합계 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
PROD_ISCD:ES
BSOP_DATE:20240624
UPMU_GUBUN:0
CTS_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션종목현재가

- **API ID**: 해외선물-035
- **실전 TR_ID**: HHDFO55010000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션종목현재가 API입니다.

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55010000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목명 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (35)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `proc_date` | 최종처리일자 | string | Y | 8 |  |
| 5 | `proc_time` | 최종처리시각 | string | Y | 6 |  |
| 6 | `open_price` | 시가 | string | Y | 15 |  |
| 7 | `high_price` | 고가 | string | Y | 15 |  |
| 8 | `low_price` | 저가 | string | Y | 15 |  |
| 9 | `last_price` | 현재가 | string | Y | 15 | 현재가<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 10 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 11 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 12 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 13 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |
| 14 | `bid_qntt` | 매수1수량 | string | Y | 10 |  |
| 15 | `bid_price` | 매수1호가 | string | Y | 15 |  |
| 16 | `ask_qntt` | 매도1수량 | string | Y | 10 |  |
| 17 | `ask_price` | 매도1호가 | string | Y | 15 |  |
| 18 | `trst_mgn` | 증거금 | string | Y | 19 |  |
| 19 | `exch_cd` | 거래소코드 | string | Y | 10 |  |
| 20 | `crc_cd` | 거래통화 | string | Y | 10 |  |
| 21 | `trd_fr_date` | 상장일 | string | Y | 8 |  |
| 22 | `expr_date` | 만기일 | string | Y | 8 |  |
| 23 | `trd_to_date` | 최종거래일 | string | Y | 8 |  |
| 24 | `remn_cnt` | 잔존일수 | string | Y | 4 |  |
| 25 | `last_qntt` | 체결량 | string | Y | 10 |  |
| 26 | `tot_ask_qntt` | 총매도잔량 | string | Y | 10 |  |
| 27 | `tot_bid_qntt` | 총매수잔량 | string | Y | 10 |  |
| 28 | `tick_size` | 틱사이즈 | string | Y | 19 |  |
| 29 | `open_date` | 장개시일자 | string | Y | 8 |  |
| 30 | `open_time` | 장개시시각 | string | Y | 6 |  |
| 31 | `close_date` | 장종료일자 | string | Y | 8 |  |
| 32 | `close_time` | 장종료시각 | string | Y | 6 |  |
| 33 | `sbsnsdate` | 영업일자 | string | Y | 8 |  |
| 34 | `sttl_price` | 정산가 | string | N | 15 | 정산가 |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OGXX24 C19500
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션종목상세

- **API ID**: 해외선물-034
- **실전 TR_ID**: HHDFO55010100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-detail`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션종목상세 API입니다.

(주의) sstl_price 자리에 정산가 X 전일종가 O 가 수신되는 점 유의 부탁드립니다.

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55010100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목명 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `exch_cd` | 거래소코드 | string | Y | 10 |  |
| 5 | `clas_cd` | 품목종류 | string | Y | 1 |  |
| 6 | `crc_cd` | 거래통화 | string | Y | 10 |  |
| 7 | `sttl_price` | 전일종가 | string | Y | 15 | (★주의) 정산가 X 전일종가 O 가 수신됨<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 8 | `sttl_date` | 정산일 | string | Y | 8 |  |
| 9 | `trst_mgn` | 증거금 | string | Y | 19 |  |
| 10 | `disp_digit` | 가격표시진법 | string | Y | 10 |  |
| 11 | `tick_sz` | 틱사이즈 | string | Y | 19 |  |
| 12 | `tick_val` | 틱가치 | string | Y | 19 |  |
| 13 | `mrkt_open_date` | 장개시일자 | string | Y | 8 |  |
| 14 | `mrkt_open_time` | 장개시시각 | string | Y | 6 |  |
| 15 | `mrkt_close_date` | 장마감일자 | string | Y | 8 |  |
| 16 | `mrkt_close_time` | 장마감시각 | string | Y | 6 |  |
| 17 | `trd_fr_date` | 상장일 | string | Y | 8 |  |
| 18 | `expr_date` | 만기일 | string | Y | 8 |  |
| 19 | `trd_to_date` | 최종거래일 | string | Y | 8 |  |
| 20 | `remn_cnt` | 잔존일수 | string | Y | 4 |  |
| 21 | `stat_tp` | 매매여부 | string | Y | 1 |  |
| 22 | `ctrt_size` | 계약크기 | string | Y | 19 |  |
| 23 | `stl_tp` | 최종결제구분 | string | Y | 20 |  |
| 24 | `frst_noti_date` | 최초식별일 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 P5650
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 호가

- **API ID**: 해외선물-033
- **실전 TR_ID**: HHDFO86000000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-asking-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 호가 API입니다.
한국투자 HTS(eFriend Plus) &gt; [5501] 해외선물옵션 현재가 화면 의 "왼쪽 상단 현재가" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO86000000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목명 | string | Y | 8 | 예)OESM24 C5340 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (21)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `open_price` | 시가 | string | Y | 15 |  |
| 5 | `high_price` | 고가 | string | Y | 15 |  |
| 6 | `lowp_rice` | 저가 | string | Y | 15 |  |
| 7 | `last_price` | 현재가 | string | Y | 15 |  |
| 8 | `sttl_price` | 정산가 | string | Y | 15 |  |
| 9 | `vol` | 거래량 | string | Y | 10 |  |
| 10 | `prev_diff_price` | 전일대비가 | string | Y | 15 |  |
| 11 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |
| 12 | `quot_date` | 호가수신일자 | string | Y | 8 |  |
| 13 | `quot_time` | 호가수신시각 | string | Y | 6 |  |
| 14 | `output2` | 응답상세 | object array | Y |  | array (1호가~ 5호가 순서대로 표시) |
| 15 | `bid_qntt` | 매수수량 | string | Y | 10 |  |
| 16 | `bid_num` | 매수번호 | string | Y | 10 |  |
| 17 | `bid_price` | 매수호가 | string | Y | 15 |  |
| 18 | `ask_qntt` | 매도수량 | string | Y | 10 |  |
| 19 | `ask_num` | 매도번호 | string | Y | 10 |  |
| 20 | `ask_price` | 매도호가 | string | Y | 15 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OTXM24 C22000
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 분봉조회

- **API ID**: 해외선물-040
- **실전 TR_ID**: HHDFO55020400
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/inquire-time-optchartprice`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 분봉조회 API입니다. 
한 번의 호출에 120건까지 확인 가능하며, QRY_TP, INDEX_KEY 를 이용하여 다음조회 가능합니다.

※ 다음조회 방법
(처음조회) "QRY_TP":"Q", "QRY_CNT":"120", "INDEX_KEY":""
(다음조회) "QRY_TP":"P", "QRY_CNT":"120", "INDEX_KEY":"20240902         5"  ◀ 이전 호출의 "output1 &gt; index_key" 기입

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55020400 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 종목코드에 맞는 거래소 코드 ex) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | "" 공란 입력 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | "" 공란 입력<br>※ 날짜 입력해도 처리 안됨 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 120 (최대 120) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 1: 1분봉, 5: 5분봉 ... |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 다음조회(QRY_TP를 P로 입력) 시, 이전 호출의 "output1 > index_key" 기입하여 조회 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output1` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 |  |
| 9 | `data_time` | 시간 | string | Y | 6 |  |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 C5660
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:120
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 체결추이(틱)

- **API ID**: 해외선물-038
- **실전 TR_ID**: HHDFO55020200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-tick-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 체결추이(틱) API입니다. 
한 번의 호출에 40건까지 확인 가능하며, QRY_TP, INDEX_KEY 를 이용하여 다음조회 가능합니다.

※ 다음조회 방법
(처음조회) "QRY_TP":"Q", "QRY_CNT":"40", "INDEX_KEY":""
(다음조회) "QRY_TP":"P", "QRY_CNT":"40", "INDEX_KEY":"20240906       221"  ◀ 이전 호출의 "output1 &gt; index_key" 기입

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55020200 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 종목코드에 맞는 거래소 코드 ex) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | "" 공란 입력 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | "" 공란 입력<br>※ 날짜 입력해도 처리 안됨 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q : 최초조회시 , P : 다음키(INDEX_KEY) 입력하여 조회시 |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 30 (최대 40) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | 공백 |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | 다음조회(QRY_TP를 P로 입력) 시, 이전 호출의 "output1 > index_key" 기입하여 조회 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 | 과거일자 ~ 최근일자 순으로 조회됨 |
| 9 | `data_time` | 시간 | string | Y | 6 | HHMMSS |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:30
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 체결추이(일간)

- **API ID**: 해외선물-037
- **실전 TR_ID**: HHDFO55020100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-daily-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 체결추이(일간) API입니다.
최근 120건까지 데이터 확인이 가능합니다. ("QRY_CNT: 119 입력", START_DATE_TIME, CLOSE_DATE_TIME은 공란)

※ 호출 시 유의사항
 : START_DATE_TIME, CLOSE_DATE_TIME은 공란 입력, QRY_CNT는 확인 데이터 개수의 -1 개 입력
ex) "START_DATE_TIME":"","CLOSE_DATE_TIME":"","QRY_CNT":"119" → 최근 120건 데이터 조회

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55020100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 종목코드에 맞는 거래소 코드 ex) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | "" 공란 입력 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | "" 공란 입력 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 100 (최대 119)<br>※ QRY_CNT 입력값의 +1 개 데이터가 조회됩니다. |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | "" 공란 입력 |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | "" 공란 입력<br>※ 다음조회 불가 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 | ※ "input > QRY_CNT" +1 개 만큼 조회됨 |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 | 과거일자 ~ 최근일자 순으로 조회됨 |
| 9 | `data_time` | 시간 | string | Y | 6 | "" |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 C5500
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:119
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 체결추이(주간)

- **API ID**: 해외선물-036
- **실전 TR_ID**: HHDFO55020000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-weekly-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 체결추이(주간) API입니다.
최근 120건까지 데이터 확인이 가능합니다. (START_DATE_TIME, CLOSE_DATE_TIME은 공란 입력)

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55020000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 종목코드에 맞는 거래소 코드 ex) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | "" 공란 입력 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | "" 공란 입력 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 20 (최대 120) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | "" 공란 입력 |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | "" 공란 입력 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 | 과거일자 ~ 최근일자 순으로 조회됨 |
| 9 | `data_time` | 시간 | string | Y | 6 | "" |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:100
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 체결추이(월간)

- **API ID**: 해외선물-039
- **실전 TR_ID**: HHDFO55020300
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/opt-monthly-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 체결추이(월간) API입니다. 
최근 120건까지 데이터 확인이 가능합니다. (START_DATE_TIME, CLOSE_DATE_TIME은 공란 입력)

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55020300 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `SRS_CD` | 종목코드 | string | Y | 32 | ex) OESU24 C5500<br>※ 종목코드 "포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션" 참고 |
| 1 | `EXCH_CD` | 거래소코드 | string | Y | 10 | 종목코드에 맞는 거래소 코드 ex) CME |
| 2 | `START_DATE_TIME` | 조회시작일시 | string | Y | 12 | "" 공란 입력 |
| 3 | `CLOSE_DATE_TIME` | 조회종료일시 | string | Y | 12 | "" 공란 입력 |
| 4 | `QRY_TP` | 조회구분 | string | Y | 1 | Q |
| 5 | `QRY_CNT` | 요청개수 | string | Y | 4 | 예) 20 (최대 120) |
| 6 | `QRY_GAP` | 묶음개수 | string | Y | 3 | "" 공란 입력 |
| 7 | `INDEX_KEY` | 이전조회KEY | string | Y | 30 | "" 공란 입력 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `ret_cnt` | 자료개수 | string | Y | 4 |  |
| 5 | `last_n_cnt` | N틱최종개수 | string | Y | 4 |  |
| 6 | `index_key` | 이전조회KEY | string | Y | 30 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `data_date` | 일자 | string | Y | 8 | 과거일자 ~ 최근일자 순으로 조회됨 |
| 9 | `data_time` | 시간 | string | Y | 6 | "" |
| 10 | `open_price` | 시가 | string | Y | 15 |  |
| 11 | `high_price` | 고가 | string | Y | 15 |  |
| 12 | `low_price` | 저가 | string | Y | 15 |  |
| 13 | `last_price` | 체결가격 | string | Y | 15 | 체결가격<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 14 | `last_qntt` | 체결수량 | string | Y | 10 |  |
| 15 | `vol` | 누적거래수량 | string | Y | 10 |  |
| 16 | `prev_diff_flag` | 전일대비구분 | string | Y | 1 |  |
| 17 | `prev_diff_price` | 전일대비가격 | string | Y | 15 |  |
| 18 | `prev_diff_rate` | 전일대비율 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```text
SRS_CD:OESU24 C5600
EXCH_CD:CME
START_DATE_TIME:
CLOSE_DATE_TIME:
QRY_TP:Q
QRY_CNT:20
QRY_GAP:
INDEX_KEY:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외옵션 상품기본정보

- **API ID**: 해외선물-041
- **실전 TR_ID**: HHDFO55200000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/search-opt-detail`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외옵션 상품기본정보 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0054] 관심종목 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

(중요) 해외옵션시세 출력값을 해석하실 때 focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)에 있는 sCalcDesz(계산 소수점) 값을 활용하셔야 정확한 값을 받아오실 수 있습니다.

- focode.mst(해외지수옵션 종목마스터파일), (해외주식옵션 종목마스터파일) 다운로드 방법
  1) focode.mst(해외지수옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외지수옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외옵션정보.h)를 참고하여 해석
  2) fostkcode.mst(해외주식옵션 종목마스터파일)
     : 포럼 &gt; FAQ &gt; 종목정보 다운로드(해외) - 해외주식옵션 클릭하여 다운로드 후
       Github의 헤더정보(https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/해외주식옵션정보.h)를 참고하여 해석

- 소수점 계산 시, focode.mst(해외지수옵션 종목마스터파일), fostkcode.mst(해외주식옵션 종목마스터파일)의 sCalcDesz(계산 소수점) 값 참고
  EX) focode.mst 파일의 sCalcDesz(계산 소수점) 값
       품목코드 OES 계산소수점 -2 → 시세 7525 수신 시 75.25 로 해석
       품목코드 O6E 계산소수점 -4 → 시세 54.0 수신 시 0.0054 로 해석
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFO55200000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `QRY_CNT` | 요청개수 | string | Y | 32 | 입력한 코드 개수 |
| 1 | `SRS_CD_01` | 종목코드1 | string | Y | 32 | SRS_CD_01부터 차례로 입력(ex ) OESU24 C5500<br>최대 30개 까지 가능 |
| 2 | `SRS_CD_02...` | 종목코드2 | string | Y | 32 |  |
| 3 | `SRS_CD_30` | 종목코드30 | string | Y | 32 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object array | Y |  | array |
| 4 | `exch_cd` | 거래소코드 | string | Y | 10 |  |
| 5 | `clas_cd` | 품목종류 | string | Y | 1 |  |
| 6 | `crc_cd` | 거래통화 | string | Y | 10 |  |
| 7 | `sttl_price` | 정산가 | string | Y | 15 | 정산가<br>※ focode.mst, fostkcode.mst* 의 sCalcDesz(계산 소수점) 값 참고<br>* 포럼 > FAQ > 종목정보 다운로드(해외) - 해외지수옵션/해외주식옵션 |
| 8 | `sttl_date` | 정산일 | string | Y | 8 |  |
| 9 | `trst_mgn` | 증거금 | string | Y | 19 |  |
| 10 | `disp_digit` | 가격표시진법 | string | Y | 10 |  |
| 11 | `tick_sz` | 틱사이즈 | string | Y | 19 |  |
| 12 | `tick_val` | 틱가치 | string | Y | 19 |  |
| 13 | `mrkt_open_date` | 장개시일자 | string | Y | 8 |  |
| 14 | `mrkt_open_time` | 장개시시각 | string | Y | 6 |  |
| 15 | `mrkt_close_date` | 장마감일자 | string | Y | 8 |  |
| 16 | `mrkt_close_time` | 장마감시각 | string | Y | 6 |  |
| 17 | `trd_fr_date` | 상장일 | string | Y | 8 |  |
| 18 | `expr_date` | 만기일 | string | Y | 8 |  |
| 19 | `trd_to_date` | 최종거래일 | string | Y | 8 |  |
| 20 | `remn_cnt` | 잔존일수 | string | Y | 4 |  |
| 21 | `stat_tp` | 매매여부 | string | Y | 1 |  |
| 22 | `ctrt_size` | 계약크기 | string | Y | 19 |  |
| 23 | `stl_tp` | 최종결제구분 | string | Y | 20 |  |
| 24 | `frst_noti_date` | 최초식별일 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```text
QRY_CNT:3
SRS_CD_01:OESU24 C5600
SRS_CD_02:OESU24 C5590
SRS_CD_03:OESU24 C5580
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>



### 해외선물옵션 장운영시간

- **API ID**: 해외선물-030
- **실전 TR_ID**: OTFM2229R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-futureoption/v1/quotations/market-time`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외선물 장운영시간 API입니다.
한국투자 HTS(eFriend Plus) &gt; [6773] 해외선물 장운영시간 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | OTFM2229R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FM_PDGR_CD` | FM상품군코드 | string | Y | 10 | 공백 |
| 1 | `FM_CLAS_CD` | FM클래스코드 | string | Y | 3 | '공백(전체), 001(통화), 002(금리), 003(지수),<br>004(농산물),005(축산물),006(금속),007(에너지)' |
| 2 | `FM_EXCG_CD` | FM거래소코드 | string | Y | 10 | 'CME(CME), EUREX(EUREX), HKEx(HKEx),<br>ICE(ICE), SGX(SGX), OSE(OSE), ASX(ASX),<br>CBOE(CBOE), MDEX(MDEX), NYSE(NYSE),<br>BMF(BMF),FTX(FTX), HNX(HNX), ETC(기타)' |
| 3 | `OPT_YN` | 옵션여부 | string | Y | 1 | %(전체), N(선물), Y(옵션) |
| 4 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  |  |
| 4 | `fm_pdgr_cd` | FM상품군코드 | string | Y | 10 |  |
| 5 | `fm_pdgr_name` | FM상품군명 | string | Y | 60 |  |
| 6 | `fm_excg_cd` | FM거래소코드 | string | Y | 10 |  |
| 7 | `fm_excg_name` | FM거래소명 | string | Y | 60 |  |
| 8 | `fuop_dvsn_name` | 선물옵션구분명 | string | Y | 60 |  |
| 9 | `fm_clas_cd` | FM클래스코드 | string | Y | 3 |  |
| 10 | `fm_clas_name` | FM클래스명 | string | Y | 30 |  |
| 11 | `am_mkmn_strt_tmd` | 오전장운영시작시각 | string | Y | 6 |  |
| 12 | `am_mkmn_end_tmd` | 오전장운영종료시각 | string | Y | 6 |  |
| 13 | `pm_mkmn_strt_tmd` | 오후장운영시작시각 | string | Y | 6 |  |
| 14 | `pm_mkmn_end_tmd` | 오후장운영종료시각 | string | Y | 6 |  |
| 15 | `mkmn_nxdy_strt_tmd` | 장운영익일시작시각 | string | Y | 6 |  |
| 16 | `mkmn_nxdy_end_tmd` | 장운영익일종료시각 | string | Y | 6 |  |
| 17 | `base_mket_strt_tmd` | 기본시장시작시각 | string | Y | 6 |  |
| 18 | `base_mket_end_tmd` | 기본시장종료시각 | string | Y | 6 |  |

<details><summary>Request Example (Python)</summary>

```text
FM_PDGR_CD:
FM_CLAS_CD:
FM_EXCG_CD:CME
OPT_YN:%
CTX_AREA_NK200:
CTX_AREA_FK200:
```

</details>


<details><summary>Response Example</summary>

```json
{
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
}
```

</details>


