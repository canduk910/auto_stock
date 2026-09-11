# [해외주식] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (18개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 235 | REST | 해외주식 잔고 | TTTS3012R | GET | `/uapi/overseas-stock/v1/trading/inquire-balance` | ✓ |
| 236 | REST | 해외주식 체결기준현재잔고 | CTRP6504R | GET | `/uapi/overseas-stock/v1/trading/inquire-present-balance` | ✓ |
| 237 | REST | 해외주식 지정가체결내역조회 | TTTS6059R | GET | `/uapi/overseas-stock/v1/trading/inquire-algo-ccnl` |  |
| 238 | REST | 해외주식 기간손익 | TTTS3039R | GET | `/uapi/overseas-stock/v1/trading/inquire-period-profit` |  |
| 239 | REST | 해외주식 매수가능금액조회 | TTTS3007R | GET | `/uapi/overseas-stock/v1/trading/inquire-psamount` | ✓ |
| 240 | REST | 해외주식 정정취소주문 | (미국 정정·취소) TTTT1004U (아시아 국가 하단 규격서 참고) | POST | `/uapi/overseas-stock/v1/trading/order-rvsecncl` |  |
| 241 | REST | 해외주식 예약주문접수 | (미국예약매수) TTTT3014U  (미국예약매도) TTTT3016U   (중국/홍콩/일본/베트남 예약주문) TTTS3013U | POST | `/uapi/overseas-stock/v1/trading/order-resv` |  |
| 242 | REST | 해외주식 미체결내역 | TTTS3018R | GET | `/uapi/overseas-stock/v1/trading/inquire-nccs` | ✓ |
| 243 | REST | 해외주식 미국주간정정취소 | TTTS6038U | POST | `/uapi/overseas-stock/v1/trading/daytime-order-rvsecncl` |  |
| 244 | REST | 해외주식 주문체결내역 | TTTS3035R | GET | `/uapi/overseas-stock/v1/trading/inquire-ccnl` |  |
| 245 | REST | 해외주식 결제기준잔고 | CTRP6010R | GET | `/uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance` |  |
| 246 | REST | 해외주식 일별거래내역 | CTOS4001R | GET | `/uapi/overseas-stock/v1/trading/inquire-period-trans` |  |
| 247 | REST | 해외주식 미국주간주문 | (주간매수) TTTS6036U (주간매도) TTTS6037U | POST | `/uapi/overseas-stock/v1/trading/daytime-order` |  |
| 248 | REST | 해외주식 예약주문조회 | (미국) TTTT3039R (일본/중국/홍콩/베트남) TTTS3014R | GET | `/uapi/overseas-stock/v1/trading/order-resv-list` |  |
| 249 | REST | 해외주식 주문 | (미국매수) TTTT1002U  (미국매도) TTTT1006U (아시아 국가 하단 규격서 참고) | POST | `/uapi/overseas-stock/v1/trading/order` |  |
| 250 | REST | 해외주식 예약주문접수취소 | (미국 예약주문 취소접수) TTTT3017U (아시아국가 미제공) | POST | `/uapi/overseas-stock/v1/trading/order-resv-ccnl` |  |
| 251 | REST | 해외주식 지정가주문번호조회 | TTTS6058R | GET | `/uapi/overseas-stock/v1/trading/algo-ordno` |  |
| 252 | REST | 해외증거금 통화별조회 | TTTC2101R | GET | `/uapi/overseas-stock/v1/trading/foreign-margin` |  |

---

## 상세 명세


### 해외주식 잔고

- **API ID**: v1_해외주식-006
- **실전 TR_ID**: TTTS3012R
- **모의 TR_ID**: VTTS3012R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
해외주식 잔고를 조회하는 API 입니다.
한국투자 HTS(eFriend Plus) &gt; [7600] 해외주식 종합주문 화면의 좌측 하단 '실시간잔고' 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다. 
다만 미국주간거래 가능종목에 대해서는 frcr_evlu_pfls_amt(외화평가손익금액), evlu_pfls_rt(평가손익율), ovrs_stck_evlu_amt(해외주식평가금액), now_pric2(현재가격2) 값이 HTS와는 상이하게 표출될 수 있습니다.
(주간시간 시간대에 HTS는 주간시세로 노출, API로는 야간시세로 노출)

실전계좌의 경우, 한 번의 호출에 최대 100건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 미니스탁 잔고는 해당 API로 확인이 불가합니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, Oauth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTS3012R<br>[모의투자]<br>VTTS3012R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | [모의]<br>NASD : 나스닥<br>NYSE : 뉴욕 <br>AMEX : 아멕스<br>[실전]<br>NASD : 미국전체<br>NAS : 나스닥<br>NYSE : 뉴욕 <br>AMEX : 아멕스<br>[모의/실전 공통]<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 3 | `TR_CRCY_CD` | 거래통화코드 | string | Y | 3 | USD : 미국달러<br>HKD : 홍콩달러<br>CNY : 중국위안화<br>JPY : 일본엔화<br>VND : 베트남동 |
| 4 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | N | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 5 | `CTX_AREA_NK200` | 연속조회키200 | string | N | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (34)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output1` | 응답상세1 | array | Y |  |  |
| 6 | `cano` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 7 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 | 계좌상품코드 |
| 8 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 9 | `ovrs_pdno` | 해외상품번호 | string | Y | 12 |  |
| 10 | `ovrs_item_name` | 해외종목명 | string | Y | 60 |  |
| 11 | `frcr_evlu_pfls_amt` | 외화평가손익금액 | string | Y | 30 | 해당 종목의 매입금액과 평가금액의 외회기준 비교 손익 |
| 12 | `evlu_pfls_rt` | 평가손익율 | string | Y | 10 | 해당 종목의 평가손익을 기준으로 한 수익률 |
| 13 | `pchs_avg_pric` | 매입평균가격 | string | Y | 23 | 해당 종목의 매수 평균 단가 |
| 14 | `ovrs_cblc_qty` | 해외잔고수량 | string | Y | 19 |  |
| 15 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 | 매도 가능한 주문 수량 |
| 16 | `frcr_pchs_amt1` | 외화매입금액1 | string | Y | 23 | 해당 종목의 외화 기준 매입금액 |
| 17 | `ovrs_stck_evlu_amt` | 해외주식평가금액 | string | Y | 32 | 해당 종목의 외화 기준 평가금액 |
| 18 | `now_pric2` | 현재가격2 | string | Y | 25 | 해당 종목의 현재가 |
| 19 | `tr_crcy_cd` | 거래통화코드 | string | Y | 3 | USD : 미국달러<br>HKD : 홍콩달러<br>CNY : 중국위안화<br>JPY : 일본엔화<br>VND : 베트남동 |
| 20 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 하노이거래소<br>VNSE : 호치민거래소 |
| 21 | `loan_type_cd` | 대출유형코드 | string | Y | 2 | 00 : 해당사항없음<br>01 : 자기융자일반형<br>03 : 자기융자투자형<br>05 : 유통융자일반형<br>06 : 유통융자투자형<br>07 : 자기대주<br>09 : 유통대주<br>10 : 현금<br>11 : 주식담보대출<br>12 : 수익증권담보대출<br>13 : ELS담보대출<br>14 : 채권담보대출<br>15 : 해외주식담보대출<br>16 : 기업신용공여<br>31 : 소액자동담보대출<br>41 : 매도담보대출<br>42 : 환매자금대출<br>43 : 매입환매자금대출<br>44 : 대여매도담보대출<br>81 : 대차거래<br>82 : 법인CMA론<br>91 : 공모주청약자금대출<br>92 : 매입자금<br>93 : 미수론서비스<br>94 : 대여 |
| 22 | `loan_dt` | 대출일자 | string | Y | 8 | 대출 실행일자 |
| 23 | `expd_dt` | 만기일자 | string | Y | 8 | 대출 만기일자 |
| 24 | `output2` | 응답상세2 | object | Y |  |  |
| 25 | `frcr_pchs_amt1` | 외화매입금액1 | string | Y | 24 |  |
| 26 | `ovrs_rlzt_pfls_amt` | 해외실현손익금액 | string | Y | 20 |  |
| 27 | `ovrs_tot_pfls` | 해외총손익 | string | Y | 24 |  |
| 28 | `rlzt_erng_rt` | 실현수익율 | string | Y | 32 |  |
| 29 | `tot_evlu_pfls_amt` | 총평가손익금액 | string | Y | 32 |  |
| 30 | `tot_pftrt` | 총수익률 | string | Y | 32 |  |
| 31 | `frcr_buy_amt_smtl1` | 외화매수금액합계1 | string | Y | 25 |  |
| 32 | `ovrs_rlzt_pfls_amt2` | 해외실현손익금액2 | string | Y | 24 |  |
| 33 | `frcr_buy_amt_smtl2` | 외화매수금액합계2 | string | Y | 25 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"OVRS_EXCG_CD": "NASD",
"TR_CRCY_CD": "USD",
"CTX_AREA_FK200": "",
"CTX_AREA_NK200": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk200": "                                                                                                                                                                                                        ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output1": [
    {
      "cano": "810XXXXX",
      "acnt_prdt_cd": "01",
      "prdt_type_cd": "512",
      "ovrs_pdno": "TSLA",
      "ovrs_item_name": "테슬라",
      "frcr_evlu_pfls_amt": "-3547254.185235",
      "evlu_pfls_rt": "-81.75",
      "pchs_avg_pric": "5832.2148",
      "ovrs_cblc_qty": "744",
      "ord_psbl_qty": "744",
      "frcr_pchs_amt1": "4339167.78523",
      "ovrs_stck_evlu_amt": "791913.60000000",
      "now_pric2": "1064.400000",
      "tr_crcy_cd": "USD",
      "ovrs_excg_cd": "NASD",
      "loan_type_cd": "10",
      "loan_dt": "",
      "expd_dt": ""
    },
    {
      "cano": "",
      "acnt_prdt_cd": "",
      "prdt_type_cd": "",
      "ovrs_pdno": "",
      "ovrs_item_name": "",
      "frcr_evlu_pfls_amt": "0.000000",
      "evlu_pfls_rt": "0.00",
      "pchs_avg_pric": "0.0000",
      "ovrs_cblc_qty": "0",
      "ord_psbl_qty": "0",
      "frcr_pchs_amt1": "0.00000",
      "ovrs_stck_evlu_amt": "0.00000000",
      "now_pric2": "0.000000",
      "tr_crcy_cd": "",
      "ovrs_excg_cd": "",
      "loan_type_cd": "",
      "loan_dt": "",
      "expd_dt": ""
    }
  ],
  "output2": {
    "frcr_pchs_amt1": "4339167.78523",
    "ovrs_rlzt_pfls_amt": "-4836.71476",
    "ovrs_tot_pfls": "-3547254.18524",
    "rlzt_erng_rt": "-82.93101266",
    "tot_evlu_pfls_amt": "791913.60000000",
    "tot_pftrt": "-81.74964327",
    "frcr_buy_amt_smtl1": "5832.214765",
    "ovrs_rlzt_pfls_amt2": "-5780841.48713",
    "frcr_buy_amt_smtl2": "6970663.087128"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 해외주식 체결기준현재잔고

- **API ID**: v1_해외주식-008
- **실전 TR_ID**: CTRP6504R
- **모의 TR_ID**: VTRP6504R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-present-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443    (output3만 이용 가능)`

<details><summary>개요</summary>

```text
해외주식 잔고를 체결 기준으로 확인하는 API 입니다. 

HTS(eFriend Plus) [0839] 해외 체결기준잔고 화면을 API로 구현한 사항으로 화면을 함께 보시면 기능 이해가 쉽습니다.

(※모의계좌의 경우 output3(외화평가총액 등 확인 가능)만 정상 출력됩니다. 
잔고 확인을 원하실 경우에는 해외주식 잔고[v1_해외주식-006] API 사용을 부탁드립니다.)

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

해외주식 체결기준현재잔고 유의사항
1. 해외증권 체결기준 잔고현황을 조회하는 화면입니다.
2. 온라인국가는 수수료(국내/해외)가 반영된 최종 정산금액으로 잔고가 변동되며, 결제작업 지연등으로 인해 조회시간은 차이가 발생할 수 있습니다.
   - 아시아 온라인국가 : 매매일 익일    08:40 ~ 08:45분 경
   - 미국 온라인국가   : 당일 장 종료후 08:40 ~ 08:45분 경
  ※ 단, 애프터연장 참여 신청계좌는 10:30 ~ 10:35분 경(Summer Time : 09:30 ~ 09:35분 경)에 최종 정산금액으로 변동됩니다.
3. 미국 현재가 항목은 주간시세 및 애프터시세는 반영하지 않으며, 정규장 마감 후에는 종가로 조회됩니다.
4. 온라인국가를 제외한 국가의 현재가는 실시간 시세가 아니므로 주문화면의 잔고 평가금액 등과 차이가 발생할 수 있습니다.
5. 해외주식 담보대출 매도상환 체결내역은 해당 잔고화면에 반영되지 않습니다.
   결제가 완료된 이후 외화잔고에 포함되어 반영되오니 참고하여 주시기 바랍니다.
6. 외화평가금액은 당일 최초고시환율이 적용된 금액으로 실제 환전금액과는 차이가 있습니다. 
7. 미국은 메인 시스템이 아닌 별도 시스템을 통해 거래되므로, 18시 10~15분 이후 발생하는 미국 매매내역은 해당 화면에 실시간으로 반영되지 않으니 하단 내용을 참고하여 안내하여 주시기 바랍니다. 
   [외화잔고 및 해외 유가증권 현황 조회]
   - 일반/통합증거금 계좌 : 미국장 종료 + 30분 후 부터 조회 가능
                            단, 통합증거금 계좌에 한해 주문금액은 외화잔고 항목에 실시간 반영되며, 해외 유가증권 현황은 반영되지
                            않아 해외 유가증권 평가금액이 과다 또는 과소 평가될 수 있습니다. 
   - 애프터연장 신청계좌  : 실시간 반영 
                            단, 시스템정산작업시간(23:40~00:10) 및 거래량이 많은 경우 메인시스템에 반영되는 시간으로 인해 차이가 
                            발생할 수 있습니다.
   ※ 배치작업시간에 따라 시간은 변동될 수 있습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, Oauth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>CTRP6504R<br>[모의투자]<br>VTRP6504R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `WCRC_FRCR_DVSN_CD` | 원화외화구분코드 | string | Y | 2 | 01 : 원화 <br>02 : 외화 |
| 3 | `NATN_CD` | 국가코드 | string | Y | 3 | 000 전체<br>840 미국<br>344 홍콩<br>156 중국<br>392 일본<br>704 베트남 |
| 4 | `TR_MKET_CD` | 거래시장코드 | string | Y | 2 | [Request body NATN_CD 000 설정]<br>00 : 전체<br>[Request body NATN_CD 840 설정]<br>00 : 전체<br>01 : 나스닥(NASD)<br>02 : 뉴욕거래소(NYSE)<br>03 : 미국(PINK SHEETS)<br>04 : 미국(OTCBB)<br>05 : 아멕스(AMEX)<br>[Request body NATN_CD 156 설정]<br>00 : 전체<br>01 : 상해B<br>02 : 심천B<br>03 : 상해A<br>04 : 심천A<br>[Request body NATN_CD 392 설정]<br>01 : 일본<br>[Request body NATN_CD 704 설정]<br>01 : 하노이거래<br>02 : 호치민거래소<br>[Request body NATN_CD 344 설정]<br>01 : 홍콩<br>02 : 홍콩CNY<br>03 : 홍콩USD |
| 5 | `INQR_DVSN_CD` | 조회구분코드 | string | Y | 2 | 00 : 전체 <br>01 : 일반해외주식 <br>02 : 미니스탁 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (68)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output1` | 응답상세1 (체결기준 잔고) | array | Y |  | 체결기준현재잔고 없으면 빈값으로 출력 |
| 4 | `prdt_name` | 상품명 | string | Y | 60 | 종목명 |
| 5 | `cblc_qty13` | 잔고수량13 | string | Y | 32 | 결제보유수량 |
| 6 | `thdt_buy_ccld_qty1` | 당일매수체결수량1 | string | Y | 32 | 당일 매수 체결 완료 수량 |
| 7 | `thdt_sll_ccld_qty1` | 당일매도체결수량1 | string | Y | 32 | 당일 매도 체결 완료 수량 |
| 8 | `ccld_qty_smtl1` | 체결수량합계1 | string | Y | 32 | 체결기준 현재 보유수량 |
| 9 | `ord_psbl_qty1` | 주문가능수량1 | string | Y | 32 | 주문 가능한 주문 수량 |
| 10 | `frcr_pchs_amt` | 외화매입금액 | string | Y | 29 | 해당 종목의 외화 기준 매입금액 |
| 11 | `frcr_evlu_amt2` | 외화평가금액2 | string | Y | 30 | 해당 종목의 외화 기준 평가금액 |
| 12 | `evlu_pfls_amt2` | 평가손익금액2 | string | Y | 31 | 해당 종목의 매입금액과 평가금액의 외회기준 비교 손익 |
| 13 | `evlu_pfls_rt1` | 평가손익율1 | string | Y | 32 | 해당 종목의 평가손익을 기준으로 한 수익률 |
| 14 | `pdno` | 상품번호 | string | Y | 12 | 종목코드 |
| 15 | `bass_exrt` | 기준환율 | string | Y | 31 | 원화 평가 시 적용 환율 |
| 16 | `buy_crcy_cd` | 매수통화코드 | string | Y | 3 | USD : 미국달러<br>HKD : 홍콩달러<br>CNY : 중국위안화<br>JPY : 일본엔화<br>VND : 베트남동 |
| 17 | `ovrs_now_pric1` | 해외현재가격1 | string | Y | 29 | 해당 종목의 현재가 |
| 18 | `avg_unpr3` | 평균단가3 | string | Y | 29 | 해당 종목의 매수 평균 단가 |
| 19 | `tr_mket_name` | 거래시장명 | string | Y | 60 | 해당 종목의 거래시장명 |
| 20 | `natn_kor_name` | 국가한글명 | string | Y | 60 | 거래 국가명 |
| 21 | `pchs_rmnd_wcrc_amt` | 매입잔액원화금액 | string | Y | 19 |  |
| 22 | `thdt_buy_ccld_frcr_amt` | 당일매수체결외화금액 | object | Y | 30 | 당일 매수 외화금액<br>(Type: Object X String O) |
| 23 | `thdt_sll_ccld_frcr_amt` | 당일매도체결외화금액 | string | Y | 30 | 당일 매도 외화금액 |
| 24 | `unit_amt` | 단위금액 | string | Y | 19 |  |
| 25 | `std_pdno` | 표준상품번호 | string | Y | 12 |  |
| 26 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 27 | `scts_dvsn_name` | 유가증권구분명 | string | Y | 60 |  |
| 28 | `loan_rmnd` | 대출잔액 | string | Y | 19 | 대출 미상환 금액 |
| 29 | `loan_dt` | 대출일자 | string | Y | 8 | 대출 실행일자 |
| 30 | `loan_expd_dt` | 대출만기일자 | string | Y | 8 | 대출 만기일자 |
| 31 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 하노이거래소<br>VNSE : 호치민거래소 |
| 32 | `item_lnkg_excg_cd` | 종목연동거래소코드 | string | Y | 4 | prdt_dvsn(상품구분) : 직원용 데이터(Type: String, Length:2) |
| 33 | `output2` | 응답상세2 | array | Y |  |  |
| 34 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 35 | `crcy_cd_name` | 통화코드명 | string | Y | 60 |  |
| 36 | `frcr_buy_amt_smtl` | 외화매수금액합계 | string | Y | 29 | 해당 통화로 매수한 종목 전체의 매수금액 |
| 37 | `frcr_sll_amt_smtl` | 외화매도금액합계 | string | Y | 29 | 해당 통화로 매도한 종목 전체의 매수금액 |
| 38 | `frcr_dncl_amt_2` | 외화예수금액2 | string | Y | 29 | 외화로 표시된 외화사용가능금액 |
| 39 | `frst_bltn_exrt` | 최초고시환율 | string | Y | 31 |  |
| 40 | `frcr_buy_mgn_amt` | 외화매수증거금액 | string | Y | 31 | 매수증거금으로 사용된 외화금액 |
| 41 | `frcr_etc_mgna` | 외화기타증거금 | string | Y | 31 |  |
| 42 | `frcr_drwg_psbl_amt_1` | 외화출금가능금액1 | string | Y | 29 | 출금가능한 외화금액 |
| 43 | `frcr_evlu_amt2` | 출금가능원화금액 | string | Y | 29 | 출금가능한 원화금액 |
| 44 | `acpl_cstd_crcy_yn` | 현지보관통화여부 | string | Y | 1 |  |
| 45 | `nxdy_frcr_drwg_psbl_amt` | 익일외화출금가능금액 | string | Y | 31 |  |
| 46 | `output3` | 응답상세3 | object | Y |  |  |
| 47 | `pchs_amt_smtl` | 매입금액합계 | string | Y | 19 | 해외유가증권 매수금액의 원화 환산 금액 |
| 48 | `evlu_amt_smtl` | 평가금액합계 | string | Y | 19 | 해외유가증권 평가금액의 원화 환산 금액 |
| 49 | `evlu_pfls_amt_smtl` | 평가손익금액합계 | string | Y | 19 | 해외유가증권 평가손익의 원화 환산 금액 |
| 50 | `dncl_amt` | 예수금액 | string | Y | 19 |  |
| 51 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 52 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 |  |
| 53 | `etc_mgna` | 기타증거금 | string | Y | 19 |  |
| 54 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 |  |
| 55 | `frcr_evlu_tota` | 외화평가총액 | string | Y | 19 |  |
| 56 | `evlu_erng_rt1` | 평가수익율1 | string | Y | 31 |  |
| 57 | `pchs_amt_smtl_amt` | 매입금액합계금액 | string | Y | 19 |  |
| 58 | `evlu_amt_smtl_amt` | 평가금액합계금액 | string | Y | 19 |  |
| 59 | `tot_evlu_pfls_amt` | 총평가손익금액 | string | Y | 31 |  |
| 60 | `tot_asst_amt` | 총자산금액 | string | Y | 19 |  |
| 61 | `buy_mgn_amt` | 매수증거금액 | string | Y | 19 |  |
| 62 | `mgna_tota` | 증거금총액 | string | Y | 19 |  |
| 63 | `frcr_use_psbl_amt` | 외화사용가능금액 | string | Y | 20 |  |
| 64 | `ustl_sll_amt_smtl` | 미결제매도금액합계 | string | Y | 19 |  |
| 65 | `ustl_buy_amt_smtl` | 미결제매수금액합계 | string | Y | 19 |  |
| 66 | `tot_frcr_cblc_smtl` | 총외화잔고합계 | string | Y | 29 |  |
| 67 | `tot_loan_amt` | 총대출금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"WCRC_FRCR_DVSN_CD": "01",
"TR_MKET_CD": "00",
"NATN_CD": "000",
"INQR_DVSN_CD": "00"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output1": [
    {
      "prdt_name": "애플",
      "cblc_qty13": "40.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "40.00000000",
      "ord_psbl_qty1": "40.00000000",
      "frcr_pchs_amt": "6411629.00000",
      "frcr_evlu_amt2": "8491110.000000",
      "evlu_pfls_amt2": "2079481.00000",
      "evlu_pfls_rt1": "32.43000000",
      "pdno": "AAPL",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "212277.75600",
      "avg_unpr3": "160290.7250",
      "tr_mket_name": "나스닥",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "5986768",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US0378331005",
      "prdt_type_cd": "512",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NASD",
      "item_lnkg_excg_cd": "NAS"
    },
    {
      "prdt_name": "테슬라",
      "cblc_qty13": "5.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "5.00000000",
      "ord_psbl_qty1": "5.00000000",
      "frcr_pchs_amt": "4665399.00000",
      "frcr_evlu_amt2": "6616309.000000",
      "evlu_pfls_amt2": "1950910.00000",
      "evlu_pfls_rt1": "41.81000000",
      "pdno": "TSLA",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "1323261.87600",
      "avg_unpr3": "933079.8000",
      "tr_mket_name": "나스닥",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "4560861",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US88160R1014",
      "prdt_type_cd": "512",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NASD",
      "item_lnkg_excg_cd": "NAS"
    },
    {
      "prdt_name": "월트디즈니",
      "cblc_qty13": "24.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "24.00000000",
      "ord_psbl_qty1": "24.00000000",
      "frcr_pchs_amt": "5039237.00000",
      "frcr_evlu_amt2": "3946867.000000",
      "evlu_pfls_amt2": "-1092370.00000",
      "evlu_pfls_rt1": "-21.67000000",
      "pdno": "DIS",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "164452.81200",
      "avg_unpr3": "209968.2080",
      "tr_mket_name": "뉴욕거래소",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "4766780",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US2546871060",
      "prdt_type_cd": "513",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "NYSE",
      "item_lnkg_excg_cd": "NYS"
    },
    {
      "prdt_name": "[4689]Z홀딩스",
      "cblc_qty13": "1300.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "1300.00000000",
      "ord_psbl_qty1": "1300.00000000",
      "frcr_pchs_amt": "8556162.00000",
      "frcr_evlu_amt2": "6618273.000000",
      "evlu_pfls_amt2": "-1937889.00000",
      "evlu_pfls_rt1": "-22.64000000",
      "pdno": "4689",
      "bass_exrt": "981.11000000",
      "buy_crcy_cd": "JPY",
      "ovrs_now_pric1": "5090.97900",
      "avg_unpr3": "6581.6630",
      "tr_mket_name": "일본",
      "natn_kor_name": "일본",
      "pchs_rmnd_wcrc_amt": "9196585",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "100",
      "std_pdno": "JP3933800009",
      "prdt_type_cd": "515",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "TKSE",
      "item_lnkg_excg_cd": "TSE"
    },
    {
      "prdt_name": "ARK GENOMIC REVOLUTION ETF",
      "cblc_qty13": "36.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "36.00000000",
      "ord_psbl_qty1": "36.00000000",
      "frcr_pchs_amt": "3746679.00000",
      "frcr_evlu_amt2": "2022471.000000",
      "evlu_pfls_amt2": "-1724208.00000",
      "evlu_pfls_rt1": "-46.01000000",
      "pdno": "ARKG",
      "bass_exrt": "1212.60000000",
      "buy_crcy_cd": "USD",
      "ovrs_now_pric1": "56179.75800",
      "avg_unpr3": "104074.4160",
      "tr_mket_name": "아멕스",
      "natn_kor_name": "미국",
      "pchs_rmnd_wcrc_amt": "3533904",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "US00214Q3020",
      "prdt_type_cd": "529",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "AMEX",
      "item_lnkg_excg_cd": "AMS"
    },
    {
      "prdt_name": "[002747]애사돈자동화",
      "cblc_qty13": "400.00000000",
      "thdt_buy_ccld_qty1": "0.00000000",
      "thdt_sll_ccld_qty1": "0.00000000",
      "ccld_qty_smtl1": "400.00000000",
      "ord_psbl_qty1": "400.00000000",
      "frcr_pchs_amt": "2327369.00000",
      "frcr_evlu_amt2": "1525444.000000",
      "evlu_pfls_amt2": "-801925.00000",
      "evlu_pfls_rt1": "-34.45000000",
      "pdno": "002747",
      "bass_exrt": "190.30000000",
      "buy_crcy_cd": "CNY",
      "ovrs_now_pric1": "3813.61200",
      "avg_unpr3": "5818.4220",
      "tr_mket_name": "심천A",
      "natn_kor_name": "중화인민공화국",
      "pchs_rmnd_wcrc_amt": "2121990",
      "thdt_buy_ccld_frcr_amt": "0.000000",
      "thdt_sll_ccld_frcr_amt": "0.000000",
      "unit_amt": "1",
      "std_pdno": "CNE100001X35",
      "prdt_type_cd": "552",
      "scts_dvsn_name": "현금",
      "loan_rmnd": "0",
      "loan_dt": "",
      "loan_expd_dt": "",
      "ovrs_excg_cd": "SZAA",
      "item_lnkg_excg_c
```

</details>



### 해외주식 지정가체결내역조회

- **API ID**: 해외주식-070
- **실전 TR_ID**: TTTS6059R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-algo-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 TWAP, VWAP 주문에 대한 체결내역 조회 API로 지정가 주문번호조회 API를 수행 후 조회해야합니다
```

</details>


#### Request Header (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, Oauth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTS6059R |
| 6 | `tr_cont` | 연속거래여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | Y | 1 | P : 개인 / B : 법인 |
| 8 | `seq_no` | 일련번호 | string | N | 3 | 법인 필수 : 001 |
| 9 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 10 | `ip_addr` | IP주소 | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 11 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 계좌번호 | string | Y | 8 | 종합계좌번호 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 상품코드 2자리 (주식계좌 : 01) |
| 2 | `ORD_DT` | 주문일자 | string | Y | 8 | 주문일자 (YYYYMMDD) |
| 3 | `ORD_GNO_BRNO` | 주문채번지점번호 | string | N | 5 | TTS6058R 조회 시 해당 주문번호(odno)의 ord_gno_brno 입력 |
| 4 | `ODNO` | 주문번호 | string | Y | 10 | 지정가주문번호 (TTTS6058R)에서 조회된 주문번호 입력 |
| 5 | `TTLZ_ICLD_YN` | 집계포함여부 | string | N | 1 |  |
| 6 | `CTX_AREA_NK200` | 연속조회키200 | string | N | 200 | 연속조회 시 사용 |
| 7 | `CTX_AREA_FK200` | 연속조회조건200 | string | N | 200 | 연속조회 시 사용 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 거래ID |
| 2 | `tr_cont` | 연속거래여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메시지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  |  |
| 4 | `CCLD_SEQ` | 체결순번 | string | Y | 4 |  |
| 5 | `CCLD_BTWN` | 체결시간 | string | Y | 6 | HHMMSS |
| 6 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 7 | `ITEM_NAME` | 종목명 | string | Y | 60 |  |
| 8 | `FT_CCLD_QTY` | FT체결수량 | string | N | 4 |  |
| 9 | `FT_CCLD_UNPR3` | FT체결단가 | string | Y | 8 |  |
| 10 | `FT_CCLD_AMT3` | FT체결금액 | string | N | 8 |  |
| 11 | `output3` | 응답상세3 | object array | Y |  |  |
| 12 | `ODNO` | 주문번호 | string | Y | 10 |  |
| 13 | `TRAD_DVSN_NAME` | 매매구분명 | string | Y | 60 |  |
| 14 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 15 | `ITEM_NAME` | 종목명 | string | Y | 60 |  |
| 16 | `FT_ORD_QTY` | FT주문수량 | string | Y | 4 |  |
| 17 | `FT_ORD_UNPR3` | FT주문단가 | string | Y | 8 |  |
| 18 | `ORD_TMD` | 주문시각 | string | Y | 6 |  |
| 19 | `SPLT_BUY_ATTR_NAME` | 분할매수속성명 | string | Y | 60 |  |
| 20 | `FT_CCLD_QTY` | FT체결수량 | string | Y | 4 |  |
| 21 | `TR_CRCY` | 거래통화 | string | Y | 3 |  |
| 22 | `FT_CCLD_UNPR3` | FT체결단가 | string | Y | 8 |  |
| 23 | `FT_CCLD_AMT3` | FT체결금액 | string | Y | 8 |  |
| 24 | `CCLD_CNT` | 체결건수 | string | Y | 4 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
ORD_DT:20250523
ORD_GNO_BRNO:
ODNO:0031112345
TTLZ_ICLD_YN:
CTX_AREA_NK200:
CTX_AREA_FK200:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "ctx_area_fk200": "20250523^^0031112345^                                                                                                                                                                                   ",
    "output1": [],
    "output2": {
        "odno": "0031112345",
        "trad_dvsn_name": "TWAP지정가매수",
        "pdno": "AAPL",
        "item_name": "애플",
        "ft_ord_qty": "10",
        "ft_ord_unpr3": "10.00000000",
        "ord_tmd": "173904",
        "splt_buy_attr_name": "00:00~04:00",
        "ft_ccld_qty": "0",
        "tr_crcy": "",
        "ft_ccld_unpr3": "0.00000000",
        "ft_ccld_amt3": "0.00000",
        "ccld_cnt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
}
```

</details>



### 해외주식 기간손익

- **API ID**: v1_해외주식-032
- **실전 TR_ID**: TTTS3039R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-period-profit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 기간손익 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7717] 해외 기간손익 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

[해외 기간손익 유의 사항]
■ 단순 매체결내역을 기초로 만든 화면으로 매도체결시점의 체결기준 매입단가와 비교하여 손익이 계산됩니다.
  결제일의 환율과 금액을 기준으로 산출하는 해외주식 양도소득세 계산방식과는 상이하오니, 참고용으로만 활용하여 주시기 바랍니다.
■ 기간손익은 매매일 익일부터 조회가능합니다.
﻿﻿■ 매입금액/매도금액 원화 환산 시 매도일의 환율이 적용되어있습니다.
﻿﻿■ 손익금액의 비용은 "매도비용" 만 포함되어있습니다. 단, 동일 종목의 매수/매도가 동시에 있는 경우에는 해당일 발생한 매수비용도 함께 계산됩니다.
﻿﻿■ 담보상환내역은 기간손익화면에 표시되지 많으니 참고하여 주시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTS3039R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 2 | 공란 : 전체, <br>NASD : 미국, SEHK : 홍콩,<br>SHAA : 중국, TKSE : 일본, HASE : 베트남 |
| 3 | `NATN_CD` | 국가코드 | string | Y | 2 | 공란(Default) |
| 4 | `CRCY_CD` | 통화코드 | string | Y | 2 | 공란 : 전체<br>USD : 미국달러, HKD : 홍콩달러,<br>CNY : 중국위안화,  JPY : 일본엔화, VND : 베트남동 |
| 5 | `PDNO` | 상품번호 | string | Y | 2 | 공란 : 전체 |
| 6 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 2 | YYYYMMDD |
| 7 | `INQR_END_DT` | 조회종료일자 | string | Y | 2 | YYYYMMDD |
| 8 | `WCRC_FRCR_DVSN_CD` | 원화외화구분코드 | string | Y | 2 | 01 : 외화, 02 : 원화 |
| 9 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 2 |  |
| 10 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 2 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (27)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `Output1` | 응답상세 | object array | Y |  | array |
| 4 | `trad_day` | 매매일 | string | Y | 8 |  |
| 5 | `ovrs_pdno` | 해외상품번호 | string | Y | 12 |  |
| 6 | `ovrs_item_name` | 해외종목명 | string | Y | 60 |  |
| 7 | `slcl_qty` | 매도청산수량 | string | Y | 10 |  |
| 8 | `pchs_avg_pric` | 매입평균가격 | string | Y | 184 |  |
| 9 | `frcr_pchs_amt1` | 외화매입금액1 | string | Y | 185 |  |
| 10 | `avg_sll_unpr` | 평균매도단가 | string | Y | 238 |  |
| 11 | `frcr_sll_amt_smtl1` | 외화매도금액합계1 | string | Y | 186 |  |
| 12 | `stck_sll_tlex` | 주식매도제비용 | string | Y | 184 |  |
| 13 | `ovrs_rlzt_pfls_amt` | 해외실현손익금액 | string | Y | 145 |  |
| 14 | `pftrt` | 수익률 | string | Y | 238 |  |
| 15 | `exrt` | 환율 | string | Y | 201 |  |
| 16 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 |  |
| 17 | `frst_bltn_exrt` | 최초고시환율 | string | Y | 238 |  |
| 18 | `Output2` | 응답상세2 | object | Y |  |  |
| 19 | `stck_sll_amt_smtl` | 주식매도금액합계 | string | Y | 184 | WCRC_FRCR_DVSN_CD(원화외화구분코드)가 01(외화)이고<br>OVRS_EXCG_CD(해외거래소코드)가 공란(전체)인 경우<br>출력값 무시 |
| 20 | `stck_buy_amt_smtl` | 주식매수금액합계 | string | Y | 184 | WCRC_FRCR_DVSN_CD(원화외화구분코드)가 01(외화)이고<br>OVRS_EXCG_CD(해외거래소코드)가 공란(전체)인 경우<br>출력값 무시 |
| 21 | `smtl_fee1` | 합계수수료1 | string | Y | 138 | WCRC_FRCR_DVSN_CD(원화외화구분코드)가 01(외화)이고<br>OVRS_EXCG_CD(해외거래소코드)가 공란(전체)인 경우<br>출력값 무시 |
| 22 | `excc_dfrm_amt` | 정산지급금액 | string | Y | 205 | WCRC_FRCR_DVSN_CD(원화외화구분코드)가 01(외화)이고<br>OVRS_EXCG_CD(해외거래소코드)가 공란(전체)인 경우<br>출력값 무시 |
| 23 | `ovrs_rlzt_pfls_tot_amt` | 해외실현손익총금액 | string | Y | 145 | WCRC_FRCR_DVSN_CD(원화외화구분코드)가 01(외화)이고<br>OVRS_EXCG_CD(해외거래소코드)가 공란(전체)인 경우<br>출력값 무시 |
| 24 | `tot_pftrt` | 총수익률 | string | Y | 238 |  |
| 25 | `bass_dt` | 기준일자 | string | Y | 8 |  |
| 26 | `exrt` | 환율 | string | Y | 201 |  |


### 해외주식 매수가능금액조회

- **API ID**: v1_해외주식-014
- **실전 TR_ID**: TTTS3007R
- **모의 TR_ID**: VTTS3007R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-psamount`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
해외주식 매수가능금액조회 API입니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTS3007R<br>[모의투자]<br>VTTS3007R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | N | 1 | B : 법인 / P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | 법인 : "001" / 개인: ""(Default) |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥 / NYSE : 뉴욕 / AMEX : 아멕스<br>SEHK : 홍콩 / SHAA : 중국상해 / SZAA : 중국심천<br>TKSE : 일본 / HASE : 하노이거래소 / VNSE : 호치민거래소 |
| 3 | `OVRS_ORD_UNPR` | 해외주문단가 | string | Y | 27 | 해외주문단가 (23.8) 정수부분 23자리, 소수부분 8자리 |
| 4 | `ITEM_CD` | 종목코드 | string | Y | 12 | 종목코드 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세1 | object | N |  |  |
| 4 | `tr_crcy_cd` | 거래통화코드 | string | N | 3 | 18.2 |
| 5 | `ord_psbl_frcr_amt` | 주문가능외화금액 | string | N | 21 | 18.2 |
| 6 | `sll_ruse_psbl_amt` | 매도재사용가능금액 | string | N | 21 | 가능금액 산정 시 사용 |
| 7 | `ovrs_ord_psbl_amt` | 해외주문가능금액 | string | N | 21 | - 한국투자 앱 해외주식 주문화면내 "외화" 인경우 주문가능금액 |
| 8 | `max_ord_psbl_qty` | 최대주문가능수량 | string | N | 19 | - 한국투자 앱 해외주식 주문화면내 "외화" 인경우 주문가능수량<br>- 매수 시 수량단위 절사해서 사용 <br>   예 : (100주단위) 545 주 -> 500 주 / (10주단위) 545 주 -> 540 주 |
| 9 | `echm_af_ord_psbl_amt` | 환전이후주문가능금액 | string | N | 21 | 사용되지 않는 사항(0으로 출력) |
| 10 | `echm_af_ord_psbl_qty` | 환전이후주문가능수량 | string | N | 19 | 사용되지 않는 사항(0으로 출력) |
| 11 | `ord_psbl_qty` | 주문가능수량 | string | N | 10 | 22(20.1) |
| 12 | `exrt` | 환율 | string | N | 22 | 25(18.6) |
| 13 | `frcr_ord_psbl_amt1` | 외화주문가능금액1 | string | N | 25 | - 한국투자 앱 해외주식 주문화면내 "통합" 인경우 주문가능금액 |
| 14 | `ovrs_max_ord_psbl_qty` | 해외최대주문가능수량 | string | N | 19 | - 한국투자 앱 해외주식 주문화면내 "통합" 인경우 주문가능수량<br>- 매수 시 수량단위 절사해서 사용 <br>   예 : (100주단위) 545 주 -> 500 주 / (10주단위) 545 주 -> 540 주 |

<details><summary>Request Example (Python)</summary>

```text
"input": {
            "ACNT_PRDT_CD": "01",
            "CANO": "81019777",
            "ITEM_CD": "00011",
            "OVRS_EXCG_CD": "SEHK",
            "OVRS_ORD_UNPR": "133.200"
        }
```

</details>


<details><summary>Response Example</summary>

```text
"output": {
            "echm_af_ord_psbl_amt": "0.00",
            "echm_af_ord_psbl_qty": "0",
            "exrt": "165.5400000000",
            "frcr_ord_psbl_amt1": "955**.12",
            "max_ord_psbl_qty": "744**",
            "ord_psbl_frcr_amt": "999**.52",
            "ord_psbl_qty": "744**",
            "ovrs_max_ord_psbl_qty": "717**",
            "ovrs_ord_psbl_amt": "992**.35",
            "sll_ruse_psbl_amt": "0.00",
            "tr_crcy_cd": "HKD"
        }
```

</details>



### 해외주식 정정취소주문

- **API ID**: v1_해외주식-003
- **실전 TR_ID**: (미국 정정·취소) TTTT1004U (아시아 국가 하단 규격서 참고)
- **모의 TR_ID**: (미국 정정·취소) VTTT1004U (아시아 국가 하단 규격서 참고)
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
접수된 해외주식 주문을 정정하거나 취소하기 위한 API입니다.
(해외주식주문 시 Return 받은 ODNO를 참고하여 API를 호출하세요.)

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 해외 거래소 운영시간 외 API 호출 시 에러가 발생하오니 운영시간을 확인해주세요.
* 해외 거래소 운영시간(한국시간 기준)
1) 미국 : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00) 
   * 프리마켓(18:00 ~ 23:30, Summer Time : 17:00 ~ 22:30), 애프터마켓(06:00 ~ 07:00, Summer Time : 05:00 ~ 07:00) 시간대에도 주문 가능
2) 일본 : (오전) 09:00 ~ 11:30, (오후) 12:30 ~ 15:00
3) 상해 : 10:30 ~ 16:00
4) 홍콩 : (오전) 10:30 ~ 13:00, (오후) 14:00 ~ 17:00

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTT1004U : 미국 정정 취소 주문<br>TTTS1003U : 홍콩 정정 취소 주문<br>TTTS0309U : 일본 정정 취소 주문<br>TTTS0302U : 상해 취소 주문<br>TTTS0306U : 심천 취소 주문<br>TTTS0312U : 베트남 취소 주문 <br>[모의투자]<br>VTTT1004U : 미국 정정 취소 주문<br>VTTS1003U : 홍콩 정정 취소 주문<br>VTTS0309U : 일본 정정 취소 주문<br>VTTS0302U : 상해 취소 주문<br>VTTS0306U : 심천 취소 주문<br>VTTS0312U : 베트남 취소 주문 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥 <br>NYSE : 뉴욕 <br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 3 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 4 | `ORGN_ODNO` | 원주문번호 | string | Y | 10 | 정정 또는 취소할 원주문번호<br>(해외주식_주문 API ouput ODNO <br>or 해외주식 미체결내역 API output ODNO 참고) |
| 5 | `RVSE_CNCL_DVSN_CD` | 정정취소구분코드 | string | Y | 2 | 01 : 정정 <br>02 : 취소 |
| 6 | `ORD_QTY` | 주문수량 | string | Y | 10 |  |
| 7 | `OVRS_ORD_UNPR` | 해외주문단가 | string | Y | 32 | 취소주문 시, "0" 입력 |
| 8 | `MGCO_APTM_ODNO` | 운용사지정주문번호 | string | N | 12 |  |
| 9 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | N | 1 | "0"(Default) |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `KRX_FWDG_ORD_ORGNO` | 한국거래소전송주문조직번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 5 | `ODNO` | 주문번호 | string | Y | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 6 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문시각(시분초HHMMSS) |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"OVRS_EXCG_CD": "NYSE",
"PDNO": "BA",
"ORGN_ODNO": "30135009",
"RVSE_CNCL_DVSN_CD": "01",
"ORD_QTY": "1",
"OVRS_ORD_UNPR": "226.00",
"CTAC_TLNO": "",
"MGCO_APTM_ODNO": "",
"ORD_SVR_DVSN_CD": "0"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "01790",
    "ODNO": "0000004338",
    "ORD_TMD": "160710"
  }
}
```

</details>



### 해외주식 예약주문접수

- **API ID**: v1_해외주식-002
- **실전 TR_ID**: (미국예약매수) TTTT3014U  (미국예약매도) TTTT3016U   (중국/홍콩/일본/베트남 예약주문) TTTS3013U
- **모의 TR_ID**: (미국예약매수) VTTT3014U  (미국예약매도) VTTT3016U   (중국/홍콩/일본/베트남 예약주문) VTTS3013U
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
미국거래소 운영시간 외 미국주식을 예약 매매하기 위한 API입니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)

* 아래 각 국가의 시장별 예약주문 접수 가능 시간을 확인하시길 바랍니다.

미국 예약주문 접수시간
1) 10:00 ~ 23:20 / 10:00 ~ 22:20 (서머타임 시)
2) 주문제한 : 16:30 ~ 16:45 경까지 (사유 : 시스템 정산작업시간)
3) 23:30 정규장으로 주문 전송 (서머타임 시 22:30 정규장 주문 전송)
4) 미국 거래소 운영시간(한국시간 기준) : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00)

홍콩 예약주문 접수시간
1) 09:00 ~ 10:20 접수, 10:30 주문전송
2) 10:40 ~ 13:50 접수, 14:00 주문전송

중국 예약주문 접수시간
1) 09:00 ~ 10:20 접수, 10:30 주문전송
2) 10:40 ~ 13:50 접수, 14:00 주문전송

일본 예약주문 접수시간
1) 09:10 ~ 12:20 까지 접수, 12:30 주문전송

베트남 예약주문 접수시간
1) 09:00 ~ 11:00 까지 접수, 11:15 주문전송
2) 11:20 ~ 14:50 까지 접수, 15:00 주문전송

* 예약주문 유의사항
1) 예약주문 유효기간 : 당일
 - 미국장 마감 후, 미체결주문은 자동취소
 - 미국휴장 시, 익 영업일로 이전
   (미국예약주문화면에서 취소 가능)
2) 증거금 및 잔고보유 : 체크 안함
3) 주문전송 불가사유
 - 매수증거금 부족: 수수료 포함 매수금액부족, 환전, 시세이용료 출금, 인출에 의한 증거금 부족
 - 기타 매수증거금 부족, 매도가능수량 부족, 주권변경 등 권리발생으로 인한 주문불가사유 발생
4) 지정가주문만 가능
* 단 미국 예약매도주문(TTTT3016U)의 경우, MOO(장개시시장가)로 주문 접수 가능
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTT3016U : 미국 매도 예약 주문<br>TTTT3014U : 미국 매수 예약 주문<br>TTTS3013U : 중국/홍콩/일본/베트남 예약 매수/매도/취소 주문<br>[모의투자]<br>VTTT3016U : 미국 매도 예약 주문<br>VTTT3014U : 미국 매수 예약 주문<br>VTTS3013U : 중국/홍콩/일본/베트남 예약 매수/매도/취소 주문 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | N | 2 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 사용<br>01 : 매도<br>02 : 매수 |
| 3 | `RVSE_CNCL_DVSN_CD` | 정정취소구분코드 | string | Y | 2 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 사용<br>00 : "매도/매수 주문"시 필수 항목<br>02 : 취소 |
| 4 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 5 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 사용<br>515 : 일본<br>501 : 홍콩 / 543 : 홍콩CNY / 558 : 홍콩USD<br>507 : 베트남 하노이거래소 / 508 : 베트남 호치민거래소<br>551 : 중국 상해A / 552 : 중국 심천A |
| 6 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 7 | `FT_ORD_QTY` | FT주문수량 | string | Y | 10 |  |
| 8 | `FT_ORD_UNPR3` | FT주문단가3 | string | Y | 27 |  |
| 9 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | N | 1 | "0"(Default) |
| 10 | `RSVN_ORD_RCIT_DT` | 예약주문접수일자 | string | N | 8 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 사용 |
| 11 | `ORD_DVSN` | 주문구분 | string | N | 20 | tr_id가 TTTT3014U(미국 예약 매수 주문)인 경우만 사용<br>00 : 지정가<br>35 : TWAP<br>36 : VWAP<br>tr_id가 TTTT3016U(미국 예약 매도 주문)인 경우만 사용<br>00 : 지정가<br>31 : MOO(장개시시장가)<br>35 : TWAP<br>36 : VWAP |
| 12 | `OVRS_RSVN_ODNO` | 해외예약주문번호 | string | N | 10 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 사용 |
| 13 | `ALGO_ORD_TMD_DVSN_CD` | 알고리즘주문시간구분코드 | string | N | 2 | ※ TWAP, VWAP 주문에서만 사용. 예약주문은 시간입력 불가하여 02로 값 고정<br>※ 정규장 종료 10분전까지 가능 |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `ODNO` | 한국거래소전송주문조직번호 | string | Y | 10 | tr_id가 TTTT3016U(미국 예약 매도 주문) / TTTT3014U(미국 예약 매수 주문)인 경우만 출력 |
| 5 | `RSVN_ORD_RCIT_DT` | 예약주문접수일자 | string | Y | 8 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 출력 |
| 6 | `OVRS_RSVN_ODNO` | 해외예약주문번호 | string | Y | 10 | tr_id가 TTTS3013U(중국/홍콩/일본/베트남 예약 주문)인 경우만 출력 |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"AAPL",
"PDNO": "AAPL",
"OVRS_EXCG_CD": "NASD",
"FT_ORD_QTY": "1",
"FT_ORD_UNPR3": "148.00"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "ODNO": "0030138295"
  }
}
```

</details>



### 해외주식 미체결내역

- **API ID**: v1_해외주식-005
- **실전 TR_ID**: TTTS3018R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-nccs`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
접수된 해외주식 주문 중 체결되지 않은 미체결 내역을 조회하는 API입니다.
실전계좌의 경우, 한 번의 호출에 최대 40건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 

※ 해외주식 미체결내역 API 모의투자에서는 사용이 불가합니다. 
   모의투자로 해외주식 미체결내역 확인시에는 해외주식 주문체결내역[v1_해외주식-007] API 조회하셔서 nccs_qty(미체결수량)으로 해외주식 미체결수량을 조회하실 수 있습니다.


* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 해외 거래소 운영시간(한국시간 기준)
1) 미국 : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00) 
   * 프리마켓(18:00 ~ 23:30, Summer Time : 17:00 ~ 22:30), 애프터마켓(06:00 ~ 07:00, Summer Time : 05:00 ~ 07:00)
2) 일본 : (오전) 09:00 ~ 11:30, (오후) 12:30 ~ 15:00
3) 상해 : 10:30 ~ 16:00
4) 홍콩 : (오전) 10:30 ~ 13:00, (오후) 14:00 ~ 17:00
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, Oauth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTS3018R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕 <br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민<br>* NASD 인 경우만 미국전체로 조회되며 나머지 거래소 코드는 해당 거래소만 조회됨<br>* 공백 입력 시 다음조회가 불가능하므로, 반드시 거래소코드 입력해야 함 |
| 3 | `SORT_SQN` | 정렬순서 | string | Y | 2 | DS : 정순<br>그외 : 역순<br>[header tr_id: TTTS3018R]<br>""(공란) |
| 4 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 5 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (35)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output` | 응답상세 | array | Y |  |  |
| 6 | `ord_dt` | 주문일자 | string | Y | 8 | 주문접수 일자 |
| 7 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 | 계좌 개설 시 관리점으로 선택한 영업점의 고유번호 |
| 8 | `odno` | 주문번호 | string | Y | 10 | 접수한 주문의 일련번호 |
| 9 | `orgn_odno` | 원주문번호 | string | Y | 10 | 정정 또는 취소 대상 주문의 일련번호 |
| 10 | `pdno` | 상품번호 | string | Y | 12 | 종목코드 |
| 11 | `prdt_name` | 상품명 | string | Y | 60 | 종목명 |
| 12 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 | 01 : 매도<br>02 : 매수 |
| 13 | `sll_buy_dvsn_cd_name` | 매도매수구분코드명 | string | Y | 60 | 매수매도구분명 |
| 14 | `rvse_cncl_dvsn_cd` | 정정취소구분코드 | string | Y | 2 | 01 : 정정<br>02 : 취소 |
| 15 | `rvse_cncl_dvsn_cd_name` | 정정취소구분코드명 | string | Y | 60 | 정정취소구분명 |
| 16 | `rjct_rson` | 거부사유 | string | Y | 60 | 정상 처리되지 못하고 거부된 주문의 사유 |
| 17 | `rjct_rson_name` | 거부사유명 | string | Y | 60 | 정상 처리되지 못하고 거부된 주문의 사유명 |
| 18 | `ord_tmd` | 주문시각 | string | Y | 6 | 주문 접수 시간 |
| 19 | `tr_mket_name` | 거래시장명 | string | Y | 60 |  |
| 20 | `tr_crcy_cd` | 거래통화코드 | string | Y | 3 | USD : 미국달러<br>HKD : 홍콩달러<br>CNY : 중국위안화<br>JPY : 일본엔화<br>VND : 베트남동 |
| 21 | `natn_cd` | 국가코드 | string | Y | 3 |  |
| 22 | `natn_kor_name` | 국가한글명 | string | Y | 60 |  |
| 23 | `ft_ord_qty` | FT주문수량 | string | Y | 10 | 주문수량 |
| 24 | `ft_ccld_qty` | FT체결수량 | string | Y | 10 | 체결된 수량 |
| 25 | `nccs_qty` | 미체결수량 | string | Y | 10 | 미체결수량 |
| 26 | `ft_ord_unpr3` | FT주문단가3 | string | Y | 26 | 주문가격 |
| 27 | `ft_ccld_unpr3` | FT체결단가3 | string | Y | 26 | 체결된 가격 |
| 28 | `ft_ccld_amt3` | FT체결금액3 | string | Y | 23 | 체결된 금액 |
| 29 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 30 | `prcs_stat_name` | 처리상태명 | string | Y | 60 | "" |
| 31 | `loan_type_cd` | 대출유형코드 | string | Y | 2 | 00 해당사항없음<br>01 자기융자일반형<br>03 자기융자투자형<br>05 유통융자일반형<br>06 유통융자투자형<br>07 자기대주<br>09 유통대주<br>10 현금<br>11 주식담보대출<br>12 수익증권담보대출<br>13 ELS담보대출<br>14 채권담보대출<br>15 해외주식담보대출<br>16 기업신용공여<br>31 소액자동담보대출<br>41 매도담보대출<br>42 환매자금대출<br>43 매입환매자금대출<br>44 대여매도담보대출<br>81 대차거래<br>82 법인CMA론<br>91 공모주청약자금대출<br>92 매입자금<br>93 미수론서비스<br>94 대여 |
| 32 | `loan_dt` | 대출일자 | string | Y | 8 | 대출 실행일자 |
| 33 | `usa_amk_exts_rqst_yn` | 미국애프터마켓연장신청여부 | string | Y | 1 | Y/N |
| 34 | `splt_buy_attr_name` | 분할매수속성명 | string | Y | 60 | 정규장 종료 주문 시에는 '정규장 종료', 시간 입력 시에는 from ~ to 시간 표시됨 |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD":"01",
"OVRS_EXCG_CD": "NYSE",
"SORT_SQN": "DS",
"CTX_AREA_FK200": "",
"CTX_AREA_NK200": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk200": "81055689^01^NYSE^DS^                                                                                                                                                                                    ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output": [
    {
      "ord_dt": "20220112",
      "ord_gno_brno": "01790",
      "odno": "0030138112",
      "orgn_odno": "",
      "pdno": "BA",
      "prdt_name": "보잉",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "매수",
      "rvse_cncl_dvsn_cd": "00",
      "rvse_cncl_dvsn_cd_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "163209",
      "tr_mket_name": "뉴욕거래소",
      "tr_crcy_cd": "USD",
      "natn_cd": "840",
      "natn_kor_name": "미국",
      "ft_ord_qty": "1",
      "ft_ccld_qty": "0",
      "nccs_qty": "1",
      "ft_ord_unpr3": "200.00000000",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "ovrs_excg_cd": "NYSE",
      "prcs_stat_name": "",
      "loan_type_cd": "10",
      "loan_dt": ""
    },
    {
      "ord_dt": "20220112",
      "ord_gno_brno": "01790",
      "odno": "0030138113",
      "orgn_odno": "",
      "pdno": "BA",
      "prdt_name": "보잉",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "매수",
      "rvse_cncl_dvsn_cd": "00",
      "rvse_cncl_dvsn_cd_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "163211",
      "tr_mket_name": "뉴욕거래소",
      "tr_crcy_cd": "USD",
      "natn_cd": "840",
      "natn_kor_name": "미국",
      "ft_ord_qty": "1",
      "ft_ccld_qty": "0",
      "nccs_qty": "1",
      "ft_ord_unpr3": "200.00000000",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "ovrs_excg_cd": "NYSE",
      "prcs_stat_name": "",
      "loan_type_cd": "10",
      "loan_dt": "",
      "loan_dt": ""
    }
  ],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 해외주식 미국주간정정취소

- **API ID**: v1_해외주식-027
- **실전 TR_ID**: TTTS6038U
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/daytime-order-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 미국주간정정취소 API입니다.

* 미국주식 주간거래 시 아래 참고 부탁드립니다.
. 포럼 &gt; FAQ &gt; 미국주식 주간거래 시 어떤 API를 사용해야 하나요?

* 미국주간거래의 경우, 모든 미국 종목 매매가 지원되지 않습니다. 일부 종목만 매매 가능한 점 유의 부탁드립니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 미국주간거래시간 외 API 호출 시 에러가 발생하오니 운영시간을 확인해주세요.
. 주간거래(장전거래)(한국시간 기준) : 10:00 ~ 18:00 (Summer Time 동일)

* 한국투자증권 해외주식 시장별 매매안내(매매수수료, 거래시간 안내, 결제일 정보, 환전안내)
   https://securities.koreainvestment.com/main/bond/research/_static/TF03ca050000.jsp

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)

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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>미국주간 정정취소 : TTTS6038U |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD:나스닥 / NYSE:뉴욕 / AMEX:아멕스 |
| 3 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드 |
| 4 | `ORGN_ODNO` | 원주문번호 | string | Y | 10 | '정정 또는 취소할 원주문번호(매매 TR의 주문번호)<br>- 해외주식 주문체결내역api (/uapi/overseas-stock/v1/trading/inquire-nccs)에서 odno(주문번호) 참조' |
| 5 | `RVSE_CNCL_DVSN_CD` | 정정취소구분코드 | string | Y | 2 | '01 : 정정 <br>02 : 취소' |
| 6 | `ORD_QTY` | 주문수량 | string | Y | 10 |  |
| 7 | `OVRS_ORD_UNPR` | 해외주문단가 | string | Y | 32 | 소수점 포함, 1주당 가격 |
| 8 | `CTAC_TLNO` | 연락전화번호 | string | Y | 20 | " " |
| 9 | `MGCO_APTM_ODNO` | 운용사지정주문번호 | string | Y | 12 | " " |
| 10 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | Y | 1 | "0" |

#### Response Header (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object | N |  |  |
| 4 | `KRX_FWDG_ORD_ORGNO` | 한국거래소전송주문조직번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 5 | `ODNO` | 주문번호 | string | Y | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 6 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문시각(시분초HHMMSS) |

<details><summary>Request Example (Python)</summary>

```json
{
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "OVRS_EXCG_CD": "NASD",
    "PDNO": "AMZN",
    "ORGN_ODNO": "0000034436",
    "RVSE_CNCL_DVSN_CD": "01",
    "ORD_QTY": "111",
    "OVRS_ORD_UNPR": "1.9",
    "CTAC_TLNO": "",
    "MGCO_APTM_ODNO": "",
    "ORD_SVR_DVSN_CD": "0"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "rt_cd": "0",
    "msg_cd": "APBK0013",
    "msg1": "주문 전송 완료 되었습니다.",
    "output": {
        "KRX_FWDG_ORD_ORGNO": "01790",
        "ODNO": "0000034437",
        "ORD_TMD": "104202"
    }
}
```

</details>



### 해외주식 주문체결내역

- **API ID**: v1_해외주식-007
- **실전 TR_ID**: TTTS3035R
- **모의 TR_ID**: VTTS3035R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
일정 기간의 해외주식 주문 체결 내역을 확인하는 API입니다.
실전계좌의 경우, 한 번의 호출에 최대 20건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 
모의계좌의 경우, 한 번의 호출에 최대 15건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp


* 해외 거래소 운영시간(한국시간 기준)
1) 미국 : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00) 
   * 프리마켓(18:00 ~ 23:30, Summer Time : 17:00 ~ 22:30), 애프터마켓(06:00 ~ 07:00, Summer Time : 05:00 ~ 07:00)
2) 일본 : (오전) 09:00 ~ 11:30, (오후) 12:30 ~ 15:00
3) 상해 : 10:30 ~ 16:00
4) 홍콩 : (오전) 10:30 ~ 13:00, (오후) 14:00 ~ 17:00

해외소수점 매매 내역은 조회 안되는 점 이용에 참고 부탁드립니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTS3035R<br>[모의투자]<br>VTTS3035R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 상품번호 | string | Y | 12 | 전종목일 경우 "%" 입력<br>※ 모의투자계좌의 경우 ""(전체 조회)만 가능 |
| 3 | `ORD_STRT_DT` | 주문시작일자 | string | Y | 8 | YYYYMMDD 형식 (현지시각 기준) |
| 4 | `ORD_END_DT` | 주문종료일자 | string | Y | 8 | YYYYMMDD 형식 (현지시각 기준) |
| 5 | `SLL_BUY_DVSN` | 매도매수구분 | string | Y | 2 | 00 : 전체 <br>01 : 매도 <br>02 : 매수<br>※ 모의투자계좌의 경우 "00"(전체 조회)만 가능 |
| 6 | `CCLD_NCCS_DVSN` | 체결미체결구분 | string | Y | 2 | 00 : 전체 <br>01 : 체결 <br>02 : 미체결<br>※ 모의투자계좌의 경우 "00"(전체 조회)만 가능 |
| 7 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | 전종목일 경우 "%" 입력<br>NASD : 미국시장 전체(나스닥, 뉴욕, 아멕스)<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩 <br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민<br>※ 모의투자계좌의 경우 ""(전체 조회)만 가능 |
| 8 | `SORT_SQN` | 정렬순서 | string | Y | 2 | DS : 정순<br>AS : 역순 <br>※ 모의투자계좌의 경우 정렬순서 사용불가(Default : DS(정순)) |
| 9 | `ORD_DT` | 주문일자 | string | Y | 8 | "" (Null 값 설정) |
| 10 | `ORD_GNO_BRNO` | 주문채번지점번호 | string | Y | 5 | "" (Null 값 설정) |
| 11 | `ODNO` | 주문번호 | string | Y | 10 | "" (Null 값 설정)<br>※ 주문번호로 검색 불가능합니다. 반드시 ""(Null 값 설정) 바랍니다. |
| 12 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |
| 13 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output` | 응답상세 | array | Y |  |  |
| 6 | `ord_dt` | 주문일자 | string | Y | 8 | 주문접수 일자 (현지시각 기준) |
| 7 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 | 계좌 개설 시 관리점으로 선택한 영업점의 고유번호 |
| 8 | `odno` | 주문번호 | string | Y | 10 | 접수한 주문의 일련번호<br>※ 정정취소주문 시, 해당 값 odno(주문번호) 넣어서 사용 |
| 9 | `orgn_odno` | 원주문번호 | string | Y | 10 | 정정 또는 취소 대상 주문의 일련번호 |
| 10 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 | 01 : 매도 <br>02 : 매수 |
| 11 | `sll_buy_dvsn_cd_name` | 매도매수구분코드명 | string | Y | 60 |  |
| 12 | `rvse_cncl_dvsn` | 정정취소구분 | string | Y | 2 | 01 : 정정 <br>02 : 취소 |
| 13 | `rvse_cncl_dvsn_name` | 정정취소구분명 | string | Y | 60 |  |
| 14 | `pdno` | 상품번호 | string | Y | 12 |  |
| 15 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 16 | `ft_ord_qty` | FT주문수량 | string | Y | 10 | 주문수량 |
| 17 | `ft_ord_unpr3` | FT주문단가3 | string | Y | 26 | 주문가격 |
| 18 | `ft_ccld_qty` | FT체결수량 | string | Y | 10 | 체결된 수량 |
| 19 | `ft_ccld_unpr3` | FT체결단가3 | string | Y | 26 | 체결된 가격 |
| 20 | `ft_ccld_amt3` | FT체결금액3 | string | Y | 23 | 체결된 금액 |
| 21 | `nccs_qty` | 미체결수량 | string | Y | 10 | 미체결수량 |
| 22 | `prcs_stat_name` | 처리상태명 | string | Y | 60 | 완료, 거부, 전송 |
| 23 | `rjct_rson` | 거부사유 | string | Y | 60 | 정상 처리되지 못하고 거부된 주문의 사유 |
| 24 | `rjct_rson_name` | 거부사유명 | string | Y | 60 |  |
| 25 | `ord_tmd` | 주문시각 | string | Y | 6 | 주문 접수 시간 |
| 26 | `tr_mket_name` | 거래시장명 | string | Y | 60 |  |
| 27 | `tr_natn` | 거래국가 | string | Y | 3 |  |
| 28 | `tr_natn_name` | 거래국가명 | string | Y | 3 |  |
| 29 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩 <br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 30 | `tr_crcy_cd` | 거래통화코드 | string | Y | 60 |  |
| 31 | `dmst_ord_dt` | 국내주문일자 | string | Y | 8 |  |
| 32 | `thco_ord_tmd` | 당사주문시각 | string | Y | 6 |  |
| 33 | `loan_type_cd` | 대출유형코드 | string | Y | 2 | 00 : 해당사항없음<br>01 : 자기융자일반형<br>03 : 자기융자투자형<br>05 : 유통융자일반형<br>06 : 유통융자투자형<br>07 : 자기대주<br>09 : 유통대주<br>10 : 현금<br>11 : 주식담보대출<br>12 : 수익증권담보대출<br>13 : ELS담보대출<br>14 : 채권담보대출<br>15 : 해외주식담보대출<br>16 : 기업신용공여<br>31 : 소액자동담보대출<br>41 : 매도담보대출<br>42 : 환매자금대출<br>43 : 매입환매자금대출<br>44 : 대여매도담보대출<br>81 : 대차거래<br>82 : 법인CMA론<br>91 : 공모주청약자금대출<br>92 : 매입자금<br>93 : 미수론서비스<br>94 : 대여 |
| 34 | `loan_dt` | 대출일자 | string | Y | 8 |  |
| 35 | `mdia_dvsn_name` | 매체구분명 | string | Y | 60 | ex) OpenAPI, 모바일 |
| 36 | `usa_amk_exts_rqst_yn` | 미국애프터마켓연장신청여부 | string | Y | 1 | Y/N |
| 37 | `splt_buy_attr_name` | 분할매수/매도속성명 | string | Y | 60 | 정규장 종료 주문 시에는 '정규장 종료', 시간 입력 시에는 from ~ to 시간 표시 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"01",
	"PDNO": ""%,
	"ORD_STRT_DT": "20211027",
	"ORD_END_DT": "20211027",
	"SLL_BUY_DVSN": "00",
	"CCLD_NCCS_DVSN": "00",
	"OVRS_EXCG_CD": "%",
	"SORT_SQN": "DS",
	"ORD_DT": "",
	"ORD_GNO_BRNO":"02111",
	"ODNO": "",
	"CTX_AREA_NK200": "",
	"CTX_AREA_FK200": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "ctx_area_fk200": "12345678^01^^20211027^20211027^00^00^NASD^^                                                                                                                                                             ",
  "output": {
      "ord_dt": "",
      "ord_gno_brno": "",
      "odno": "",
      "orgn_odno": "",
      "sll_buy_dvsn_cd": "",
      "sll_buy_dvsn_cd_name": "",
      "rvse_cncl_dvsn": "",
      "rvse_cncl_dvsn_name": "",
      "pdno": "",
      "prdt_name": "",
      "ft_ord_qty": "0",
      "ft_ord_unpr3": "0.00000000",
      "ft_ccld_qty": "0",
      "ft_ccld_unpr3": "0.00000000",
      "ft_ccld_amt3": "0.00000",
      "nccs_qty": "0",
      "prcs_stat_name": "",
      "rjct_rson": "",
      "rjct_rson_name": "",
      "ord_tmd": "",
      "tr_mket_name": "",
      "tr_natn": "",
      "tr_natn_name": "",
      "ovrs_excg_cd": "",
      "tr_crcy_cd": "",
      "dmst_ord_dt": "",
      "thco_ord_tmd": "",
      "loan_type_cd": "",
      "loan_dt": "",
      "mdia_dvsn_name": "OpenAPI",
      "usa_amk_exts_rqst_yn": "N",
      "splt_buy_attr_name": "00:00~04:00"    },
  "rt_cd": "0",
  "msg_cd": "KIOK0560",
  "msg1": "조회할 내용이 없습니다                                                          "
}
```

</details>



### 해외주식 결제기준잔고

- **API ID**: 해외주식-064
- **실전 TR_ID**: CTRP6010R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-paymt-stdr-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 결제기준잔고 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0829] 해외 결제기준잔고 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ 적용환율은 당일 매매기준이며, 현재가의 경우 지연된 시세로 평가되므로 실제매도금액과 상이할 수 있습니다.
※ 주문가능수량 : 보유수량 - 미결제 매도수량
※ 매입금액 계산 시 결제일의 최초고시환율을 적용하므로, 금일 최초고시환율을 적용하는 체결기준 잔고와는 상이합니다.
※ 해외증권 투자 및 업무문의 안내: 한국투자증권 해외투자지원부 02)3276-5300
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTRP6010R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 2 | `BASS_DT` | 기준일자 | string | Y | 8 |  |
| 3 | `WCRC_FRCR_DVSN_CD` | 원화외화구분코드 | string | Y | 2 | 01(원화기준),02(외화기준) |
| 4 | `INQR_DVSN_CD` | 조회구분코드 | string | Y | 2 | 00(전체), 01(일반), 02(미니스탁) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (44)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `pdno` | 상품번호 | string | Y | 12 |  |
| 5 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 6 | `cblc_qty13` | 잔고수량13 | string | Y | 238 |  |
| 7 | `ord_psbl_qty1` | 주문가능수량1 | string | Y | 238 |  |
| 8 | `avg_unpr3` | 평균단가3 | string | Y | 244 |  |
| 9 | `ovrs_now_pric1` | 해외현재가격1 | string | Y | 235 |  |
| 10 | `frcr_pchs_amt` | 외화매입금액 | string | Y | 235 |  |
| 11 | `frcr_evlu_amt2` | 외화평가금액2 | string | Y | 236 |  |
| 12 | `evlu_pfls_amt2` | 평가손익금액2 | string | Y | 255 |  |
| 13 | `bass_exrt` | 기준환율 | string | Y | 238 |  |
| 14 | `oprt_dtl_dtime` | 조작상세일시 | string | Y | 17 |  |
| 15 | `buy_crcy_cd` | 매수통화코드 | string | Y | 3 |  |
| 16 | `thdt_sll_ccld_qty1` | 당일매도체결수량1 | string | Y | 238 |  |
| 17 | `thdt_buy_ccld_qty1` | 당일매수체결수량1 | string | Y | 238 |  |
| 18 | `evlu_pfls_rt1` | 평가손익율1 | string | Y | 238 |  |
| 19 | `tr_mket_name` | 거래시장명 | string | Y | 60 |  |
| 20 | `natn_kor_name` | 국가한글명 | string | Y | 60 |  |
| 21 | `std_pdno` | 표준상품번호 | string | Y | 12 |  |
| 22 | `mgge_qty` | 담보수량 | string | Y | 19 |  |
| 23 | `loan_rmnd` | 대출잔액 | string | Y | 19 |  |
| 24 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 25 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 |  |
| 26 | `scts_dvsn_name` | 유가증권구분명 | string | Y | 60 |  |
| 27 | `ldng_cblc_qty` | 대여잔고수량 | string | Y | 19 |  |
| 28 | `output2` | 응답상세 | object array | Y |  | array |
| 29 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 30 | `crcy_cd_name` | 통화코드명 | string | Y | 60 |  |
| 31 | `frcr_dncl_amt_2` | 외화예수금액2 | string | Y | 236 |  |
| 32 | `frst_bltn_exrt` | 최초고시환율 | string | Y | 238 |  |
| 33 | `frcr_evlu_amt2` | 외화평가금액2 | string | Y | 236 |  |
| 34 | `output3` | 응답상세 | object | Y |  |  |
| 35 | `pchs_amt_smtl_amt` | 매입금액합계금액 | string | Y | 19 |  |
| 36 | `tot_evlu_pfls_amt` | 총평가손익금액 | string | Y | 238 |  |
| 37 | `evlu_erng_rt1` | 평가수익율1 | string | Y | 201 |  |
| 38 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 |  |
| 39 | `wcrc_evlu_amt_smtl` | 원화평가금액합계 | string | Y | 236 |  |
| 40 | `tot_asst_amt2` | 총자산금액2 | string | Y | 236 |  |
| 41 | `frcr_cblc_wcrc_evlu_amt_smtl` | 외화잔고원화평가금액합계 | string | Y | 236 |  |
| 42 | `tot_loan_amt` | 총대출금액 | string | Y | 19 |  |
| 43 | `tot_ldng_evlu_amt` | 총대여평가금액 | string | Y | 9 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
BASS_DT:20240524
WCRC_FRCR_DVSN_CD:01
INQR_DVSN_CD:00
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": [
        {
            "pdno": "ACVA",
            "prdt_name": "ACV 옥션스",
            "cblc_qty13": "5.00000000",
            "ord_psbl_qty1": "5.00000000",
            "avg_unpr3": "11137.2000",
            "ovrs_now_pric1": "26065.48600",
            "frcr_pchs_amt": "55686.00000",
            "frcr_evlu_amt2": "130327.000000",
            "evlu_pfls_amt2": "74641.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240525104030326",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "134.03000000",
            "tr_mket_name": "나스닥",
            "natn_kor_name": "미국",
            "std_pdno": "US00091G1040",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "512",
            "ovrs_excg_cd": "NASD",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "DLPN",
            "prdt_name": "돌핀 엔터테인먼트",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "2279.0000",
            "ovrs_now_pric1": "1529.24800",
            "frcr_pchs_amt": "2279.00000",
            "frcr_evlu_amt2": "1529.000000",
            "evlu_pfls_amt2": "-750.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240525104052328",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-32.90000000",
            "tr_mket_name": "나스닥",
            "natn_kor_name": "미국",
            "std_pdno": "US25686H2094",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "512",
            "ovrs_excg_cd": "NASD",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "NIO",
            "prdt_name": "니오(ADR)",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "14316.0000",
            "ovrs_now_pric1": "6854.30800",
            "frcr_pchs_amt": "14316.00000",
            "frcr_evlu_amt2": "6854.000000",
            "evlu_pfls_amt2": "-7462.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240528185338061",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-52.12000000",
            "tr_mket_name": "뉴욕거래소",
            "natn_kor_name": "미국",
            "std_pdno": "US62914V1061",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "513",
            "ovrs_excg_cd": "NYSE",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "6731",
            "prdt_name": "[6731]픽셀라",
            "cblc_qty13": "4.00000000",
            "ord_psbl_qty1": "4.00000000",
            "avg_unpr3": "8851.7500",
            "ovrs_now_pric1": "922.30600",
            "frcr_pchs_amt": "35407.00000",
            "frcr_evlu_amt2": "3689.000000",
            "evlu_pfls_amt2": "-31718.00000",
            "bass_exrt": "870.10000000",
            "oprt_dtl_dtime": "20240528170115625",
            "buy_crcy_cd": "JPY",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-89.58000000",
            "tr_mket_name": "일본",
            "natn_kor_name": "일본",
            "std_pdno": "JP3801620000",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "515",
            "ovrs_excg_cd": "TKSE",
            "scts_dvsn_name": "현금"
        },
        {
            "pdno": "CEI",
            "prdt_name": "캠버 에너지",
            "cblc_qty13": "1.00000000",
            "ord_psbl_qty1": "1.00000000",
            "avg_unpr3": "2255.0000",
            "ovrs_now_pric1": "238.94500",
            "frcr_pchs_amt": "2255.00000",
            "frcr_evlu_amt2": "238.000000",
            "evlu_pfls_amt2": "-2017.00000",
            "bass_exrt": "1365.40000000",
            "oprt_dtl_dtime": "20240528185356653",
            "buy_crcy_cd": "USD",
            "thdt_sll_ccld_qty1": "0.00000000",
            "thdt_buy_ccld_qty1": "0.00000000",
            "evlu_pfls_rt1": "-89.44000000",
            "tr_mket_name": "아멕스",
            "natn_kor_name": "미국",
            "std_pdno": "US13200M6075",
            "mgge_qty": "0",
            "loan_rmnd": "0",
            "prdt_type_cd": "529",
            "ovrs_excg_cd": "AMEX",
            "scts_dvsn_name": "현금"
        }
    ],
    "output2": [
        {
            "crcy_cd": "CNY",
            "crcy_cd_name": "중국위안",
            "frcr_dncl_amt_2": "1459.110000",
            "frst_bltn_exrt": "188.15000000",
            "frcr_evlu_amt2": "274531.000000"
        },
        {
            "crcy_cd": "USD",
            "crcy_cd_name": "미국달러",
            "frcr_dncl_amt_2": "698.190000",
            "frst_bltn_exrt": "1365.40000000",
            "frcr_evlu_amt2": "953308.000000"
        },
        {
            "crcy_cd": "VND",
            "crcy_cd_name": "베트남 동",
            "frcr_dncl_amt_2": "377568.000000",
            "frst_bltn_exrt": "5.36000000",
            "frcr_evlu_amt2": "20237.000000"
        }
    ],
    "output3": {
        "pchs_amt_smtl_amt": "109943",
        "tot_evlu_pfls_amt": "32694.00000000",
        "evlu_erng_rt1": "29.7300000000",
        "tot_dncl_amt": "296967",
        "wcrc_evlu_amt_smtl": "142637.000000",
        "tot_asst_amt2": "1687680.000000",
        "frcr_cblc_wcrc_evlu_amt_smtl": "1248076.000000",
        "tot_loan_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
}
```

</details>



### 해외주식 일별거래내역

- **API ID**: 해외주식-063
- **실전 TR_ID**: CTOS4001R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/inquire-period-trans`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 일별거래내역 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0828] 해외증권 일별거래내역 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ 체결가격, 매매금액, 정산금액, 수수료 원화금액은 국내 결제일까지는 예상환율로 적용되고, 국내 결제일 익일부터 확정환율로 적용됨으로 금액이 변경될 수 있습니다.
※ 해외증권 투자 및 업무문의 안내: 한국투자증권 해외투자지원부 02)3276-5300
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTOS4001R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 2 | `ERLM_STRT_DT` | 등록시작일자 | string | Y | 8 | 입력날짜 ~ (ex) 20240420) |
| 3 | `ERLM_END_DT` | 등록종료일자 | string | Y | 8 | ~입력날짜 (ex) 20240520) |
| 4 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | 공백 |
| 5 | `PDNO` | 상품번호 | string | Y | 12 | 공백 (전체조회), 개별종목 조회는 상품번호입력 |
| 6 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 00(전체), 01(매도), 02(매수) |
| 7 | `LOAN_DVSN_CD` | 대출구분코드 | string | Y | 2 | 공백 |
| 8 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | 공백 |
| 9 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (34)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `ctx_area_fk100` | 연속조회검색조건100 | string | Y | 100 |  |
| 4 | `ctx_area_nk100` | 연속조회키100 | string | Y | 100 |  |
| 5 | `output1` | 응답상세 | object array | Y |  | array |
| 6 | `trad_dt` | 매매일자 | string | Y | 8 |  |
| 7 | `sttl_dt` | 결제일자 | string | Y | 8 |  |
| 8 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 |  |
| 9 | `sll_buy_dvsn_name` | 매도매수구분명 | string | Y | 4 |  |
| 10 | `pdno` | 상품번호 | string | Y | 12 |  |
| 11 | `ovrs_item_name` | 해외종목명 | string | Y | 60 |  |
| 12 | `ccld_qty` | 체결수량 | string | Y | 10 |  |
| 13 | `amt_unit_ccld_qty` | 금액단위체결수량 | string | Y | 188 |  |
| 14 | `ft_ccld_unpr2` | FT체결단가2 | string | Y | 238 |  |
| 15 | `ovrs_stck_ccld_unpr` | 해외주식체결단가 | string | Y | 238 |  |
| 16 | `tr_frcr_amt2` | 거래외화금액2 | string | Y | 236 |  |
| 17 | `tr_amt` | 거래금액 | string | Y | 19 |  |
| 18 | `frcr_excc_amt_1` | 외화정산금액1 | string | Y | 236 |  |
| 19 | `wcrc_excc_amt` | 원화정산금액 | string | Y | 19 |  |
| 20 | `dmst_frcr_fee1` | 국내외화수수료1 | string | Y | 235 |  |
| 21 | `frcr_fee1` | 외화수수료1 | string | Y | 236 |  |
| 22 | `dmst_wcrc_fee` | 국내원화수수료 | string | Y | 19 |  |
| 23 | `ovrs_wcrc_fee` | 해외원화수수료 | string | Y | 19 |  |
| 24 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 25 | `std_pdno` | 표준상품번호 | string | Y | 12 |  |
| 26 | `erlm_exrt` | 등록환율 | string | Y | 238 |  |
| 27 | `loan_dvsn_cd` | 대출구분코드 | string | Y | 2 |  |
| 28 | `loan_dvsn_name` | 대출구분명 | string | Y | 60 |  |
| 29 | `output2` | 응답상세 | object | Y |  |  |
| 30 | `frcr_buy_amt_smtl` | 외화매수금액합계 | string | Y | 236 |  |
| 31 | `frcr_sll_amt_smtl` | 외화매도금액합계 | string | Y | 236 |  |
| 32 | `dmst_fee_smtl` | 국내수수료합계 | string | Y | 256 |  |
| 33 | `ovrs_fee_smtl` | 해외수수료합계 | string | Y | 236 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
ERLM_STRT_DT:20240101
ERLM_END_DT:20240528
OVRS_EXCG_CD:
PDNO:
SLL_BUY_DVSN_CD:00
LOAN_DVSN_CD:
CTX_AREA_FK100:
CTX_AREA_NK100:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "12345678!^01!^20240101!^20240528!^!^                                                                ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "trad_dt": "20240116",
            "sttl_dt": "20240118",
            "sll_buy_dvsn_cd": "01",
            "sll_buy_dvsn_name": "매도",
            "pdno": "AAPL",
            "ovrs_item_name": "애플",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "2.94000000",
            "ovrs_stck_ccld_unpr": "0.00000000",
            "tr_frcr_amt2": "2.940000",
            "tr_amt": "0",
            "frcr_excc_amt_1": "2.940000",
            "wcrc_excc_amt": "0",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US0378331005",
            "erlm_exrt": "0.00000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240116",
            "sttl_dt": "20240118",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "USAS",
            "ovrs_item_name": "아메리카스 골드 앤드 실버",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "0.62000000",
            "ovrs_stck_ccld_unpr": "0.00000000",
            "tr_frcr_amt2": "0.620000",
            "tr_amt": "0",
            "frcr_excc_amt_1": "0.620000",
            "wcrc_excc_amt": "0",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "CA03062D1006",
            "erlm_exrt": "0.00000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "TSLA",
            "ovrs_item_name": "테슬라",
            "ccld_qty": "1",
            "amt_unit_ccld_qty": "1.00000000",
            "ft_ccld_unpr2": "12.20000000",
            "ovrs_stck_ccld_unpr": "16283.34000000",
            "tr_frcr_amt2": "12.200000",
            "tr_amt": "16283",
            "frcr_excc_amt_1": "12.200000",
            "wcrc_excc_amt": "16283",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US88160R1014",
            "erlm_exrt": "1334.70000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "PG",
            "ovrs_item_name": "프록터 앤드 갬블",
            "ccld_qty": "5",
            "amt_unit_ccld_qty": "5.00000000",
            "ft_ccld_unpr2": "149.20000000",
            "ovrs_stck_ccld_unpr": "199137.24000000",
            "tr_frcr_amt2": "746.000000",
            "tr_amt": "995686",
            "frcr_excc_amt_1": "746.000000",
            "wcrc_excc_amt": "995686",
            "dmst_frcr_fee1": "0.00000",
            "frcr_fee1": "0.000000",
            "dmst_wcrc_fee": "0",
            "ovrs_wcrc_fee": "0",
            "crcy_cd": "USD",
            "std_pdno": "US7427181091",
            "erlm_exrt": "1334.70000000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        },
        {
            "trad_dt": "20240118",
            "sttl_dt": "20240122",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_name": "매수",
            "pdno": "6758",
            "ovrs_item_name": "[6758]소니",
            "ccld_qty": "99",
            "amt_unit_ccld_qty": "99.00000000",
            "ft_ccld_unpr2": "14260.50000000",
            "ovrs_stck_ccld_unpr": "129281.41480000",
            "tr_frcr_amt2": "1411789.000000",
            "tr_amt": "12798855",
            "frcr_excc_amt_1": "1415742.000000",
            "wcrc_excc_amt": "12834691",
            "dmst_frcr_fee1": "2824.00000",
            "frcr_fee1": "1129.000000",
            "dmst_wcrc_fee": "25601",
            "ovrs_wcrc_fee": "10235",
            "crcy_cd": "JPY",
            "std_pdno": "JP3435000009",
            "erlm_exrt": "9.06570000",
            "loan_dvsn_cd": "01",
            "loan_dvsn_name": "현금"
        }
    ],
    "output2": {
        "frcr_buy_amt_smtl": "13810824.000000",
        "frcr_sll_amt_smtl": "0.000000",
        "dmst_fee_smtl": "25601.000000",
        "ovrs_fee_smtl": "10235.000000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 해외주식 미국주간주문

- **API ID**: v1_해외주식-026
- **실전 TR_ID**: (주간매수) TTTS6036U (주간매도) TTTS6037U
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/daytime-order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 미국주간주문 API입니다.

* 미국주식 주간거래 시 아래 참고 부탁드립니다.
. 포럼 &gt; FAQ &gt; 미국주식 주간거래 시 어떤 API를 사용해야 하나요?

* 미국주간거래의 경우, 모든 미국 종목 매매가 지원되지 않습니다. 일부 종목만 매매 가능한 점 유의 부탁드립니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 미국주간거래시간 외 API 호출 시 에러가 발생하오니 운영시간을 확인해주세요.
. 주간거래(장전거래)(한국시간 기준) : 10:00 ~ 18:00 (Summer Time 동일)

* 한국투자증권 해외주식 시장별 매매안내(매매수수료, 거래시간 안내, 결제일 정보, 환전안내)
   https://securities.koreainvestment.com/main/bond/research/_static/TF03ca050000.jsp

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)

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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>미국주간매수 : TTTS6036U<br>미국주간매도 : TTTS6037U |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD:나스닥 / NYSE:뉴욕 / AMEX:아멕스 |
| 3 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드 |
| 4 | `ORD_QTY` | 주문수량 | string | Y | 10 | 해외거래소 별 최소 주문수량 및 주문단위 확인 필요 |
| 5 | `OVRS_ORD_UNPR` | 해외주문단가 | string | Y | 32 | 소수점 포함, 1주당 가격<br>* 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 |
| 6 | `CTAC_TLNO` | 연락전화번호 | string | N | 20 | " " |
| 7 | `MGCO_APTM_ODNO` | 운용사지정주문번호 | string | N | 12 | " " |
| 8 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | Y | 1 | "0" |
| 9 | `ORD_DVSN` | 주문구분 | string | Y | 2 | [미국 매수/매도 주문] <br>00 : 지정가 <br>* 주간거래는 지정가만 가능 |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object | N |  |  |
| 4 | `KRX_FWDG_ORD_ORGNO` | 한국거래소전송주문조직번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 5 | `ODNO` | 주문번호 | string | Y | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 6 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문시각(시분초HHMMSS) |


### 해외주식 예약주문조회

- **API ID**: v1_해외주식-013
- **실전 TR_ID**: (미국) TTTT3039R (일본/중국/홍콩/베트남) TTTS3014R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv-list`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 예약주문 조회 API입니다.
※ 모의투자는 사용 불가합니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>미국 : TTTT3039R<br>일본, 중국, 홍콩, 베트남 : TTTS3014R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | N | 1 | B : 법인 / P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | 법인 : "001" / 개인: ""(Default) |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (9)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 | 조회시작일자(YYYYMMDD) |
| 3 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 | 조회종료일자(YYYYMMDD) |
| 4 | `INQR_DVSN_CD` | 조회구분코드 | string | Y | 2 | 00 : 전체<br>01 : 일반해외주식 <br>02 : 미니스탁 |
| 5 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | [tr_id=TTTT3039R인 경우]<br>공백 입력 시 미국주식 전체조회<br>[tr_id=TTTS3014R인 경우]<br>공백 입력 시 아시아주식 전체조회<br>512 : 미국 나스닥 / 513 : 미국 뉴욕거래소 / 529 : 미국 아멕스 <br>515 : 일본<br>501 : 홍콩 / 543 : 홍콩CNY / 558 : 홍콩USD<br>507 : 베트남 하노이거래소 / 508 : 베트남 호치민거래소<br>551 : 중국 상해A / 552 : 중국 심천A |
| 6 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | [tr_id=TTTT3039R인 경우]<br>공백 입력 시 미국주식 전체조회<br>[tr_id=TTTS3014R인 경우]<br>공백 입력 시 아시아주식 전체조회<br>NASD : 나스닥 / NYSE : 뉴욕 / AMEX : 아멕스<br>SEHK : 홍콩 / SHAA : 중국상해 / SZAA : 중국심천<br>TKSE : 일본 / HASE : 하노이거래소 / VNSE : 호치민거래소 |
| 7 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 8 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (30)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output` | 응답상세1 | object | N |  |  |
| 6 | `cncl_yn` | 취소여부 | string | N | 1 |  |
| 7 | `rsvn_ord_rcit_dt` | 예약주문접수일자 | string | N | 8 |  |
| 8 | `ovrs_rsvn_odno` | 해외예약주문번호 | string | N | 10 |  |
| 9 | `ord_dt` | 주문일자 | string | N | 8 |  |
| 10 | `ord_gno_brno` | 주문채번지점번호 | string | N | 5 |  |
| 11 | `odno` | 주문번호 | string | N | 10 |  |
| 12 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | N | 2 |  |
| 13 | `sll_buy_dvsn_cd_name` | 매도매수구분명 | string | N | 60 |  |
| 14 | `ovrs_rsvn_ord_stat_cd` | 해외예약주문상태코드 | string | N | 2 |  |
| 15 | `ovrs_rsvn_ord_stat_cd_name` | 해외예약주문상태코드명 | string | N | 60 |  |
| 16 | `pdno` | 상품번호 | string | N | 12 |  |
| 17 | `prdt_type_cd` | 상품유형코드 | string | N | 3 |  |
| 18 | `prdt_name` | 상품명 | string | N | 60 |  |
| 19 | `ord_rcit_tmd` | 주문접수시각 | string | N | 6 |  |
| 20 | `ord_fwdg_tmd` | 주문전송시각 | string | N | 6 |  |
| 21 | `tr_dvsn_name` | 거래구분명 | string | N | 60 |  |
| 22 | `ovrs_excg_cd` | 해외거래소코드 | string | N | 4 |  |
| 23 | `tr_mket_name` | 거래시장명 | string | N | 60 |  |
| 24 | `ord_stfno` | 주문직원번호 | string | N | 6 |  |
| 25 | `ft_ord_qty` | FT주문수량 | string | N | 10 |  |
| 26 | `ft_ord_unpr3` | FT주문단가3 | string | N | 27 |  |
| 27 | `ft_ccld_qty` | FT체결수량 | string | N | 10 |  |
| 28 | `nprc_rson_text` | 미처리사유내용 | string | N | 500 |  |
| 29 | `splt_buy_attr_name` | 분할매수속성명 | string | N | 60 | 정규장 종료 주문 시에는 '정규장 종료', 시간 입력 시에는 from ~ to 시간 표시 |

<details><summary>Request Example (Python)</summary>

```text
"input": {
            "ACNT_PRDT_CD": "01",
            "CANO": "12345678",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
            "INQR_DVSN_CD": "00",
            "INQR_END_DT": "20220709",
            "INQR_STRT_DT": "20220705",
            "OVRS_EXCG_CD": "SEHK",
            "PRDT_TYPE_CD": "501"
        }
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "12345678^01^20220809^20220830^00^                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output": [
        {
            "cncl_yn": "N",
            "rsvn_ord_rcit_dt": "20250523",
            "ovrs_rsvn_odno": "0031111234",
            "ord_dt": "",
            "ord_gno_brno": "",
            "odno": "",
            "sll_buy_dvsn_cd": "02",
            "sll_buy_dvsn_cd_name": "TWAP지정가매수",
            "ovrs_rsvn_ord_stat_cd": "01",
            "ovrs_rsvn_ord_stat_cd_name": "접수",
            "pdno": "AAPL",
            "prdt_name": "애플",
            "ord_rcit_tmd": "161928",
            "ord_fwdg_tmd": "",
            "tr_dvsn_name": "접수",
            "ovrs_excg_cd": "NASD",
            "tr_mket_name": "NASDAQ",
            "ord_stfno": "999999",
            "ft_ord_qty": "100",
            "ft_ord_unpr3": "150.00000000",
            "ft_ccld_qty": "0",
            "ft_ccld_unpr3": "0.00000000",
            "nprc_rson_text": "",
            "splt_buy_attr_name": "00:00~04:00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 해외주식 주문

- **API ID**: v1_해외주식-001
- **실전 TR_ID**: (미국매수) TTTT1002U  (미국매도) TTTT1006U (아시아 국가 하단 규격서 참고)
- **모의 TR_ID**: (미국매수) VTTT1002U  (미국매도) VTTT1001U  (아시아 국가 하단 규격서 참고)
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
해외주식 주문 API입니다.

* 모의투자의 경우, 모든 해외 종목 매매가 지원되지 않습니다. 일부 종목만 매매 가능한 점 유의 부탁드립니다.

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

* 해외 거래소 운영시간 외 API 호출 시 에러가 발생하오니 운영시간을 확인해주세요. (미국주식 주간주문은 "해외주식 미국주간주문"을 이용)
* 해외 거래소 운영시간(한국시간 기준)
1) 미국 : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00) 
   * 프리마켓(18:00 ~ 23:30, Summer Time : 17:00 ~ 22:30), 애프터마켓(06:00 ~ 07:00, Summer Time : 05:00 ~ 07:00) 시간대에도 주문 가능
2) 일본 : (오전) 09:00 ~ 11:30, (오후) 12:30 ~ 15:00
3) 상해 : 10:30 ~ 16:00
4) 홍콩 : (오전) 10:30 ~ 13:00, (오후) 14:00 ~ 17:00

* 기존에는 내부통제 요건에 따라 상장주식수의 1%를 초과하는 주문은 접수할 수 없었으나, 2025.08.14 시행 이후부터는 접수가 가능합니다. 단, 타 매체(HTS 등)는 안내 팝업 확인 후 주문이 가능하지만, Open API는 별도의 안내 화면 없이 주문이 바로 접수되므로 유의하시기 바랍니다.


※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)

※ 종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
   https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTT1002U : 미국 매수 주문<br>TTTT1006U : 미국 매도 주문<br>TTTS0308U : 일본 매수 주문<br>TTTS0307U : 일본 매도 주문 <br>TTTS0202U : 상해 매수 주문<br>TTTS1005U : 상해 매도 주문<br>TTTS1002U : 홍콩 매수 주문<br>TTTS1001U : 홍콩 매도 주문<br>TTTS0305U : 심천 매수 주문<br>TTTS0304U : 심천 매도 주문<br>TTTS0311U : 베트남 매수 주문 <br>TTTS0310U : 베트남 매도 주문 <br>[모의투자]<br>VTTT1002U : 미국 매수 주문<br>VTTT1001U : 미국 매도 주문<br>VTTS0308U : 일본 매수 주문<br>VTTS0307U : 일본 매도 주문 <br>VTTS0202U : 상해 매수 주문<br>VTTS1005U : 상해 매도 주문<br>VTTS1002U : 홍콩 매수 주문<br>VTTS1001U : 홍콩 매도 주문<br>VTTS0305U : 심천 매수 주문<br>VTTS0304U : 심천 매도 주문<br>VTTS0311U : 베트남 매수 주문 <br>VTTS0310U : 베트남 매도 주문 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `OVRS_EXCG_CD` | 해외거래소코드 | string | Y | 4 | NASD : 나스닥<br>NYSE : 뉴욕<br>AMEX : 아멕스<br>SEHK : 홍콩<br>SHAA : 중국상해<br>SZAA : 중국심천<br>TKSE : 일본<br>HASE : 베트남 하노이<br>VNSE : 베트남 호치민 |
| 3 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드 |
| 4 | `ORD_QTY` | 주문수량 | string | Y | 10 | 주문수량 (해외거래소 별 최소 주문수량 및 주문단위 확인 필요) |
| 5 | `OVRS_ORD_UNPR` | 해외주문단가 | string | Y | 31 | 1주당 가격<br>* 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 |
| 6 | `CTAC_TLNO` | 연락전화번호 | string | N | 20 |  |
| 7 | `MGCO_APTM_ODNO` | 운용사지정주문번호 | string | N | 12 |  |
| 8 | `SLL_TYPE` | 판매유형 | string | N | 2 | 제거 : 매수<br>00 : 매도 |
| 9 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | Y | 1 | "0"(Default) |
| 10 | `ORD_DVSN` | 주문구분 | string | Y | 2 | [Header tr_id TTTT1002U(미국 매수 주문)]<br>00 : 지정가<br>32 : LOO(장개시지정가)<br>34 : LOC(장마감지정가)<br>35 : TWAP (시간가중평균)<br>36 : VWAP (거래량가중평균)<br>* 모의투자 VTTT1002U(미국 매수 주문)로는 00:지정가만 가능<br>* TWAP, VWAP 주문은 분할시간 주문 입력 필수<br>[Header tr_id TTTT1006U(미국 매도 주문)]<br>00 : 지정가<br>31 : MOO(장개시시장가)<br>32 : LOO(장개시지정가)<br>33 : MOC(장마감시장가)<br>34 : LOC(장마감지정가)<br>35 : TWAP (시간가중평균)<br>36 : VWAP (거래량가중평균)<br>* 모의투자 VTTT1006U(미국 매도 주문)로는 00:지정가만 가능<br>* TWAP, VWAP 주문은 분할시간 주문 입력 필수<br>[Header tr_id TTTS1001U(홍콩 매도 주문)]<br>00 : 지정가<br>50 : 단주지정가<br>* 모의투자 VTTS1001U(홍콩 매도 주문)로는 00:지정가만 가능<br>[그외 tr_id]<br>제거<br>※ TWAP, VWAP 주문은 정정 불가 |
| 11 | `START_TIME` | 시작시간 | string | N | 6 | ※ TWAP, VWAP 주문유형이고 알고리즘주문시간구분코드가 00일때 사용<br>※ YYMMDD 형태로 입력<br>※ 시간 입력 시 정규장 종료 5분전까지 입력 가능 |
| 12 | `END_TIME` | 종료시간 | string | N | 6 | ※ TWAP, VWAP 주문유형이고 알고리즘주문시간구분코드가 00일때 사용<br>※ YYMMDD 형태로 입력<br>※ 시간 입력 시 정규장 종료 5분전까지 입력 가능 |
| 13 | `ALGO_ORD_TMD_DVSN_CD` | 알고리즘주문시간구분코드 | string | N | 2 | 00 : 분할주문 시간 직접입력 , 02 : 정규장 종료시까지 |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `KRX_FWDG_ORD_ORGNO` | 한국거래소전송주문조직번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 5 | `ODNO` | 주문번호 | string | Y | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 6 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문시각(시분초HHMMSS) |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"OVRS_EXCG_CD": "NASD",
"PDNO": "AAPL",
"ORD_QTY": "1",
"OVRS_ORD_UNPR": "145.00",
"CTAC_TLNO": "",
"MGCO_APTM_ODNO": "",
"ORD_SVR_DVSN_CD": "0",
"ORD_DVSN": "00"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "rt_cd": "0",
  "msg_cd": "APBK0013",
  "msg1": "주문 전송 완료 되었습니다.",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "01790",
    "ODNO": "0000004336",
    "ORD_TMD": "160524"
  }
}
```

</details>



### 해외주식 예약주문접수취소

- **API ID**: v1_해외주식-004
- **실전 TR_ID**: (미국 예약주문 취소접수) TTTT3017U (아시아국가 미제공)
- **모의 TR_ID**: (미국 예약주문 취소접수) VTTT3017U (아시아국가 미제공)
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/overseas-stock/v1/trading/order-resv-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
접수된 미국주식 예약주문을 취소하기 위한 API입니다.
(해외주식 예약주문접수 시 Return 받은 ODNO를 참고하여 API를 호출하세요.)

* 해외주식 서비스 신청 후 이용 가능합니다. (아래 링크 3번 해외증권 거래신청 참고)
https://securities.koreainvestment.com/main/bond/research/_static/TF03ca010001.jsp

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTT3017U : 미국예약주문접수 취소<br>[모의투자]<br>VTTT3017U : 미국예약주문접수 취소<br>(일본, 홍콩 등 타국가 개발 진행 예정) |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `RSYN_ORD_RCIT_DT` | 해외주문접수일자 | string | Y | 8 |  |
| 3 | `OVRS_RSVN_ODNO` | 해외예약주문번호 | string | Y | 10 | 해외주식_예약주문접수 API Output ODNO(주문번호) 참고 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `OVRS_RSVN_ODNO` | 해외예약주문번호 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"RSVN_ORD_RCIT_DT": "20211124",
"OVRS_RSVN_ODNO": "30135682"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "rt_cd": "0",
  "msg_cd": "APBK1711",
  "msg1": "취소주문이 접수되었습니다.",
  "output": {
    "OVRS_RSVN_ODNO": "0030138295"
  }
}
```

</details>



### 해외주식 지정가주문번호조회

- **API ID**: 해외주식-071
- **실전 TR_ID**: TTTS6058R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/algo-ordno`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
TWAP, VWAP 주문에 대한 주문번호를 조회하는 API
```

</details>


#### Request Header (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | Y | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTS6058R |
| 6 | `tr_cont` | 연속거래여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | Y | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 3 | [법인 필수] 001 |
| 9 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 10 | `ip_addr` | IP주소 | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 11 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `TRAD_DT` | 거래일자 | string | Y | 8 | YYYYMMDD |
| 1 | `CANO` | 계좌번호 | string | Y | 8 | 종합계좌번호 (8자리) |
| 2 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌상품코드 (2자리) : 주식계좌는 01 |
| 3 | `CTX_AREA_NK200` | 연속조회키200 | string | N | 200 |  |
| 4 | `CTX_AREA_FK200` | 연속조회조건200 | string | N | 200 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 |  |
| 2 | `tr_cont` | 연속거래여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `output` | 응답상세 | object array | Y |  |  |
| 1 | `odno` | 주문번호 | string | Y | 10 |  |
| 2 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 3 | `pdno` | 상품번호 | string | Y | 12 |  |
| 4 | `item_name` | 종목명 | string | Y | 60 |  |
| 5 | `ft_ord_qty` | FT주문수량 | string | Y | 4 |  |
| 6 | `ft_ord_unpr3` | FT주문단가 | string | Y | 8 |  |
| 7 | `splt_buy_attr_name` | 분할매수속성명 | string | Y | 60 |  |
| 8 | `ft_ccld_qty` | FT체결수량 | string | Y | 4 |  |
| 9 | `ord_gno_brno` | 주문채번지점번호 | string | N | 5 |  |
| 10 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 11 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 12 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 13 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 14 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
TRAD_DT:20250523
CTX_AREA_NK200:
CTX_AREA_FK200:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "ctx_area_fk200": "20250523^12345678^01^                                                                                                                                                                                   ",
    "output": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
}
```

</details>



### 해외증거금 통화별조회

- **API ID**: 해외주식-035
- **실전 TR_ID**: TTTC2101R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/trading/foreign-margin`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외증거금 통화별조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7718] 해외주식 증거금상세 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC2101R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `natn_name` | 국가명 | string | Y | 60 |  |
| 5 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 6 | `frcr_dncl_amt1` | 외화예수금액 | string | Y | 186 |  |
| 7 | `ustl_buy_amt` | 미결제매수금액 | string | Y | 182 |  |
| 8 | `ustl_sll_amt` | 미결제매도금액 | string | Y | 182 |  |
| 9 | `frcr_rcvb_amt` | 외화미수금액 | string | Y | 182 |  |
| 10 | `frcr_mgn_amt` | 외화증거금액 | string | Y | 186 |  |
| 11 | `frcr_gnrl_ord_psbl_amt` | 외화일반주문가능금액 | string | Y | 182 |  |
| 12 | `frcr_ord_psbl_amt1` | 외화주문가능금액 | string | Y | 186 | 원화주문가능환산금액 |
| 13 | `itgr_ord_psbl_amt` | 통합주문가능금액 | string | Y | 182 |  |
| 14 | `bass_exrt` | 기준환율 | string | Y | 238 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "natn_name": "미국",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "694.37",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "홍콩",
            "crcy_cd": "HKD",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "8247.35",
            "bass_exrt": "172.97000000"
        },
        {
            "natn_name": "홍콩",
            "crcy_cd": "CNY",
            "frcr_dncl_amt1": "1459.110000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "7705.45",
            "bass_exrt": "186.89000000"
        },
        {
            "natn_name": "중화인민공화국",
            "crcy_cd": "CNY",
            "frcr_dncl_amt1": "1459.110000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "1448.97",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "7713.10",
            "bass_exrt": "186.89000000"
        },
        {
            "natn_name": "일본",
            "crcy_cd": "JPY",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "164359.92",
            "bass_exrt": "8.68370000"
        },
        {
            "natn_name": "베트남",
            "crcy_cd": "VND",
            "frcr_dncl_amt1": "377568.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "네덜란드",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "프랑스",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "영국",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "스위스",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "싱가포르",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "독일",
            "crcy_cd": "USD",
            "frcr_dncl_amt1": "698.190000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "1094.52",
            "bass_exrt": "1349.40000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        },
        {
            "natn_name": "",
            "crcy_cd": "",
            "frcr_dncl_amt1": "0.000000",
            "ustl_buy_amt": "0.00",
            "ustl_sll_amt": "0.00",
            "frcr_rcvb_amt": "0.00",
            "frcr_mgn_amt": "0.000000",
            "frcr_gnrl_ord_psbl_amt": "0.00",
            "frcr_ord_psbl_amt1": "0.000000",
            "itgr_ord_psbl_amt": "0.00",
            "bass_exrt": "0.00000000"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>


