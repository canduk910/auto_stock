# [국내주식] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (23개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 4 | REST | 기간별계좌권리현황조회 | CTRGA011R | GET | `/uapi/domestic-stock/v1/trading/period-rights` |  |
| 5 | REST | 투자계좌자산현황조회 | CTRP6548R | GET | `/uapi/domestic-stock/v1/trading/inquire-account-balance` |  |
| 6 | REST | 퇴직연금 예수금조회 | TTTC0506R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-deposit` |  |
| 7 | REST | 주식예약주문정정취소 | (예약취소) CTSC0009U (예약정정) CTSC0013U | POST | `/uapi/domestic-stock/v1/trading/order-resv-rvsecncl` |  |
| 8 | REST | 신용매수가능조회 | TTTC8909R | GET | `/uapi/domestic-stock/v1/trading/inquire-credit-psamount` |  |
| 9 | REST | 주식통합증거금 현황 | TTTC0869R | GET | `/uapi/domestic-stock/v1/trading/intgr-margin` |  |
| 10 | REST | 퇴직연금 미체결내역 | TTTC2201R(기존 KRX만 가능), TTTC2210R (KRX,NXT/SOR) | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld` |  |
| 11 | REST | 기간별매매손익현황조회 | TTTC8715R | GET | `/uapi/domestic-stock/v1/trading/inquire-period-trade-profit` |  |
| 12 | REST | 주식주문(정정취소) | TTTC0013U | POST | `/uapi/domestic-stock/v1/trading/order-rvsecncl` | ✓ |
| 13 | REST | 주식예약주문조회 | CTSC0004R | GET | `/uapi/domestic-stock/v1/trading/order-resv-ccnl` |  |
| 14 | REST | 퇴직연금 매수가능조회 | TTTC0503R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-psbl-order` |  |
| 15 | REST | 주식잔고조회 | TTTC8434R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance` | ✓ |
| 16 | REST | 퇴직연금 체결기준잔고 | TTTC2202R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-present-balance` |  |
| 17 | REST | 매수가능조회 | TTTC8908R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-order` | ✓ |
| 18 | REST | 기간별손익일별합산조회 | TTTC8708R | GET | `/uapi/domestic-stock/v1/trading/inquire-period-profit` |  |
| 19 | REST | 주식주문(현금) | (매도) TTTC0011U (매수) TTTC0012U | POST | `/uapi/domestic-stock/v1/trading/order-cash` | ✓ |
| 20 | REST | 매도가능수량조회 | TTTC8408R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-sell` |  |
| 21 | REST | 주식일별주문체결조회 | (3개월이내) TTTC0081R (3개월이전) CTSC9215R | GET | `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` |  |
| 22 | REST | 주식정정취소가능주문조회 | TTTC0084R | GET | `/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl` |  |
| 23 | REST | 주식예약주문 | CTSC0008U | POST | `/uapi/domestic-stock/v1/trading/order-resv` |  |
| 24 | REST | 주식주문(신용) | (매도) TTTC0051U (매수) TTTC0052U | POST | `/uapi/domestic-stock/v1/trading/order-credit` |  |
| 25 | REST | 퇴직연금 잔고조회 | TTTC2208R | GET | `/uapi/domestic-stock/v1/trading/pension/inquire-balance` |  |
| 26 | REST | 주식잔고조회_실현손익 | TTTC8494R | GET | `/uapi/domestic-stock/v1/trading/inquire-balance-rlz-pl` |  |

---

## 상세 명세


### 기간별계좌권리현황조회

- **API ID**: 국내주식-211
- **실전 TR_ID**: CTRGA011R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/period-rights`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
기간별계좌권리현황조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7344] 권리유형별 현황조회 화면을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTRGA011R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 03 입력 |
| 1 | `CUST_RNCNO25` | 고객실명확인번호25 | string | Y | 25 | 공란 |
| 2 | `HMID` | 홈넷ID | string | Y | 8 | 공란 |
| 3 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 8자리 입력 (ex.12345678) |
| 4 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 상품계좌번호 2자리 입력(ex. 01 or 22) |
| 5 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 | 조회시작일자(YYYYMMDD) |
| 6 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 | 조회종료일자(YYYYMMDD) |
| 7 | `RGHT_TYPE_CD` | 권리유형코드 | string | Y | 2 | 공란 |
| 8 | `PDNO` | 상품번호 | string | Y | 12 | 공란 |
| 9 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | 공란 |
| 10 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | 다음조회시 입력 |
| 11 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | 다음조회시 입력 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (33)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `acno10` | 계좌번호10 | string | Y | 10 |  |
| 5 | `rght_type_cd` | 권리유형코드 | string | Y | 2 | 1	유상<br>2	무상<br>3	배당<br>4	매수청구<br>5	공개매수<br>6	주주총회<br>7	신주인수권증서<br>8	반대의사<br>9	신주인수권증권<br>11	합병<br>12	회사분할<br>13	주식교환<br>14	액면분할<br>15	액면병합<br>16	종목변경<br>17	감자<br>18	신구주합병<br>21	후합병<br>22	후회사분할<br>23	후주식교환<br>24	후액면분할<br>25	후액면병합<br>26	후종목변경<br>27	후감자<br>28	후신구주합병<br>31	뮤츄얼펀드<br>32	ETF<br>33	선박투자회사<br>34	투융자회사<br>35	해외자원<br>36	부동산신탁(Ritz)<br>37	상장수익증권<br>41	ELW만기<br>42	ELS분배<br>43	DLS분배<br>44	하일드펀드<br>45	ETN<br>51	전환청구<br>52	교환청구<br>53	BW청구<br>54	WRT청구<br>55	채권풋옵션청구<br>56	전환우선주청구<br>57	전환조건부청구<br>58	전자증권일괄입고<br>59	클라우드펀딩일괄입고<br>61	원리금상환<br>62	스트립채권<br>71	WRT소멸<br>72	WRT증권<br>73	DR전환<br>74	배당옵션<br>75	특별배당<br>76	ISINCODE변경<br>77	실권주청약<br>81	해외분배금(청산)<br>82	해외분배금(조기상환)<br>83	해외분배금(상장폐지)<br>84	DR FEE<br>85	SECTION 871M<br>86	종목전환<br>87	재매수<br>88	종목교환<br>89	기타이벤트<br>91	공모주<br>92	청약<br>93	환매<br>99	기타권리사유 |
| 6 | `bass_dt` | 기준일자 | string | Y | 8 |  |
| 7 | `rght_cblc_type_cd` | 권리잔고유형코드 | string | Y | 2 | 1	입고<br>2	출고<br>3	출고입고<br>4	출고입금<br>5	출고출금<br>10	현금입금<br>11	단수주대금입금<br>12	교부금입금<br>13	유상감자대금입금<br>14	지연이자입금<br>15	이자지급<br>16	대주권리금출금<br>17	분할상환<br>18	만기상환<br>19	조기상환<br>20	출금<br>21	입고&입금<br>22	입고&입금&단수주대금입금<br>25	유상환불금입금<br>26	중도상환<br>27	분할합병세금출금 |
| 8 | `rptt_pdno` | 대표상품번호 | string | Y | 12 |  |
| 9 | `pdno` | 상품번호 | string | Y | 12 |  |
| 10 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 11 | `shtn_pdno` | 단축상품번호 | string | Y | 12 |  |
| 12 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 13 | `cblc_qty` | 잔고수량 | string | Y | 19 |  |
| 14 | `last_alct_qty` | 최종배정수량 | string | Y | 19 |  |
| 15 | `excs_alct_qty` | 초과배정수량 | string | Y | 19 |  |
| 16 | `tot_alct_qty` | 총배정수량 | string | Y | 19 |  |
| 17 | `last_ftsk_qty` | 최종단수주수량 | string | Y | 191 |  |
| 18 | `last_alct_amt` | 최종배정금액 | string | Y | 19 |  |
| 19 | `last_ftsk_chgs` | 최종단수주대금 | string | Y | 19 |  |
| 20 | `rdpt_prca` | 상환원금 | string | Y | 19 |  |
| 21 | `dlay_int_amt` | 지연이자금액 | string | Y | 19 |  |
| 22 | `lstg_dt` | 상장일자 | string | Y | 8 |  |
| 23 | `sbsc_end_dt` | 청약종료일자 | string | Y | 8 |  |
| 24 | `cash_dfrm_dt` | 현금지급일자 | string | Y | 8 |  |
| 25 | `rqst_qty` | 신청수량 | string | Y | 19 |  |
| 26 | `rqst_amt` | 신청금액 | string | Y | 19 |  |
| 27 | `rqst_dt` | 신청일자 | string | Y | 8 |  |
| 28 | `rfnd_dt` | 환불일자 | string | Y | 8 |  |
| 29 | `rfnd_amt` | 환불금액 | string | Y | 19 |  |
| 30 | `lstg_stqt` | 상장주수 | string | Y | 19 |  |
| 31 | `tax_amt` | 세금금액 | string | Y | 19 |  |
| 32 | `sbsc_unpr` | 청약단가 | string | Y | 224 |  |

<details><summary>Request Example (Python)</summary>

```text
INQR_DVSN:03
CUST_RNCNO25:
HMID:
CANO:12345678
ACNT_PRDT_CD:01
INQR_STRT_DT:20240508
INQR_END_DT:20241106
RGHT_TYPE_CD:
PDNO:
PRDT_TYPE_CD:
CTX_AREA_NK100:
CTX_AREA_FK100:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_nk100": "                                                                                                    ",
    "ctx_area_fk100": "03!^!^!^12345678!^01!^20240508!^20241106!^!^!^                                                      ",
    "output": [
        {
            "acno10": "1234567801",
            "rght_type_cd": "01",
            "bass_dt": "20240919",
            "rght_cblc_type_cd": "01",
            "rptt_pdno": "00000A357880",
            "pdno": "00000A357880",
            "prdt_type_cd": "300",
            "shtn_pdno": "357880",
            "prdt_name": "비트나인",
            "cblc_qty": "1000",
            "last_alct_qty": "1050",
            "excs_alct_qty": "0",
            "tot_alct_qty": "1050",
            "last_ftsk_qty": "0.0000000000",
            "last_alct_amt": "0",
            "last_ftsk_chgs": "0",
            "rdpt_prca": "0",
            "dlay_int_amt": "0",
            "lstg_dt": "",
            "sbsc_end_dt": "20241011",
            "cash_dfrm_dt": "",
            "rqst_qty": "1000",
            "rqst_amt": "1865000",
            "rqst_dt": "20241011",
            "rfnd_dt": "",
            "rfnd_amt": "0",
            "lstg_stqt": "0",
            "tax_amt": "0",
            "sbsc_unpr": "1865.0000"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 투자계좌자산현황조회

- **API ID**: v1_국내주식-048
- **실전 TR_ID**: CTRP6548R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-account-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
투자계좌자산현황조회 API입니다.

output1은 한국투자 HTS(eFriend Plus) &gt; [0891] 계좌 자산비중(결제기준) 화면 아래 테이블의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTRP6548R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `INQR_DVSN_1` | 조회구분1 | string | Y | 1 | 공백입력 |
| 3 | `BSPR_BF_DT_APLY_YN` | 기준가이전일자적용여부 | string | Y | 1 | 공백입력 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (36)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `Output1` | 응답상세 | object array | Y |  | Array [아래 순서대로 출력 : 20항목]<br>1: 주식<br>2: 펀드/MMW<br>3: IMA<br>4: 채권<br>5: ELS/DLS<br>6: WRAP<br>7: 신탁<br>8: RP/발행어음<br>9: 해외주식<br>10: 해외채권<br>11: 금현물<br>12: CD/CP<br>13: 전자단기사채<br>14: 타사상품<br>15: 외화전자단기사채<br>16: 외화 ELS/DLS<br>17: 외화<br>18: 예수금<br>19: 청약자예수금<br>20: 합계<br>[21번 계좌일 경우 : 17항목]<br>1: 수익증권<br>2: IMA<br>3: 채권<br>4: ELS/DLS<br>5: WRAP<br>6: 신탁<br>7: RP<br>8: 외화rp<br>9: 해외채권<br>10: CD/CP<br>11: 전자단기사채<br>12: 외화전자단기사채<br>13: 외화ELS/DLS<br>14: 외화평가금액<br>15: 예수금+cma<br>16: 청약자예수금<br>17: 합계 |
| 4 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 5 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 6 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 7 | `crdt_lnd_amt` | 신용대출금액 | string | Y | 19 |  |
| 8 | `real_nass_amt` | 실제순자산금액 | string | Y | 19 |  |
| 9 | `whol_weit_rt` | 전체비중율 | string | Y | 228 |  |
| 10 | `Output2` | 응답상세2 | object | Y |  |  |
| 11 | `pchs_amt_smtl` | 매입금액합계 | string | Y | 19 | 유가매입금액 |
| 12 | `nass_tot_amt` | 순자산총금액 | string | Y | 19 |  |
| 13 | `loan_amt_smtl` | 대출금액합계 | string | Y | 19 |  |
| 14 | `evlu_pfls_amt_smtl` | 평가손익금액합계 | string | Y | 19 | 평가손익금액 |
| 15 | `evlu_amt_smtl` | 평가금액합계 | string | Y | 19 | 유가평가금액 |
| 16 | `tot_asst_amt` | 총자산금액 | string | Y | 19 | 총 자산금액 |
| 17 | `tot_lnda_tot_ulst_lnda` | 총대출금액총융자대출금액 | string | Y | 19 |  |
| 18 | `cma_auto_loan_amt` | CMA자동대출금액 | string | Y | 19 |  |
| 19 | `tot_mgln_amt` | 총담보대출금액 | string | Y | 19 |  |
| 20 | `stln_evlu_amt` | 대주평가금액 | string | Y | 19 |  |
| 21 | `crdt_fncg_amt` | 신용융자금액 | string | Y | 19 |  |
| 22 | `ocl_apl_loan_amt` | OCL_APL대출금액 | string | Y | 19 |  |
| 23 | `pldg_stup_amt` | 질권설정금액 | string | Y | 19 |  |
| 24 | `frcr_evlu_tota` | 외화평가총액 | string | Y | 19 |  |
| 25 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 |  |
| 26 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 27 | `dncl_amt` | 예수금액 | string | Y | 19 |  |
| 28 | `tot_sbst_amt` | 총대용금액 | string | Y | 19 |  |
| 29 | `thdt_rcvb_amt` | 당일미수금액 | string | Y | 20 |  |
| 30 | `ovrs_stck_evlu_amt1` | 해외주식평가금액1 | string | Y | 236 |  |
| 31 | `ovrs_bond_evlu_amt` | 해외채권평가금액 | string | Y | 236 |  |
| 32 | `mmf_cma_mgge_loan_amt` | MMFCMA담보대출금액 | string | Y | 19 |  |
| 33 | `sbsc_dncl_amt` | 청약예수금액 | string | Y | 19 |  |
| 34 | `pbst_sbsc_fnds_loan_use_amt` | 공모주청약자금대출사용금액 | string | Y | 20 |  |
| 35 | `etpr_crdt_grnt_loan_amt` | 기업신용공여대출금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"01",
	"INQR_DVSN_1":"",
	"BSPR_BF_DT_APLY_YN":"",
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": [
        {
            "pchs_amt": "129105",
            "evlu_amt": "406000",
            "evlu_pfls_amt": "276895",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "406000",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "161026228",
            "evlu_amt": "185144504",
            "evlu_pfls_amt": "24118276",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "185144504",
            "whol_weit_rt": "0.01000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "1651434483743",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "1651434483743",
            "whol_weit_rt": "99.97000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "249855300",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "249855300",
            "whol_weit_rt": "0.01000000"
        },
        {
            "pchs_amt": "0",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "0",
            "whol_weit_rt": "0.00000000"
        },
        {
            "pchs_amt": "161155333",
            "evlu_amt": "1651869889547",
            "evlu_pfls_amt": "24395171",
            "crdt_lnd_amt": "0",
            "real_nass_amt": "1651869889547",
            "whol_weit_rt": "100.00000000"
        }
    ],
    "output2": {
        "pchs_amt_smtl": "161155333",
        "nass_tot_amt": "185550504",
        "loan_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "24395171",
        "evlu_amt_smtl": "185550504",
        "tot_asst_amt": "1651869889547",
        "tot_lnda_tot_ulst_lnda": "0",
        "cma_auto_loan_amt": "0",
        "tot_mgln_amt": "0",
        "stln_evlu_amt": "0",
        "crdt_fncg_amt": "0",
        "ocl_apl_loan_amt": "0",
        "pldg_stup_amt": "0",
        "frcr_evlu_tota": "1651434483743",
        "tot_dncl_amt": "249855300",
        "cma_evlu_amt": "0",
        "dncl_amt": "249855300",
        "tot_sbst_amt": "0",
        "thdt_rcvb_amt": "0",
        "ovrs_stck_evlu_amt1": "185144504.000000",
        "ovrs_bond_evlu_amt": "0.000000",
        "mmf_cma_mgge_loan_amt": "0",
        "sbsc_dncl_amt": "0",
        "pbst_sbsc_fnds_loan_use_amt": "0",
        "etpr_crdt_grnt_loan_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
}
```

</details>



### 퇴직연금 예수금조회

- **API ID**: v1_국내주식-035
- **실전 TR_ID**: TTTC0506R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-deposit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
​※ 55번 계좌(DC가입자계좌)의 경우 해당 API 이용이 불가합니다.
KIS Developers API의 경우 HTS ID에 반드시 연결되어있어야만 API 신청 및 앱정보 발급이 가능한 서비스로 개발되어서 실물계좌가 아닌 55번 계좌는 API 이용이 불가능한 점 양해 부탁드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC0506R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 29 |
| 2 | `ACCA_DVSN_CD` | 적립금구분코드 | string | Y | 2 | 00 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세1 | object | Y |  |  |
| 4 | `dnca_tota` | 예수금총액 | string | Y | 19 |  |
| 5 | `nxdy_excc_amt` | 익일정산액 | string | Y | 19 |  |
| 6 | `nxdy_sttl_amt` | 익일결제금액 | string | Y | 19 |  |
| 7 | `nx2_day_sttl_amt` | 2익일결제금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"ACCA_DVSN_CD":"00"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "dnca_tota": "57622382",
        "nxdy_excc_amt": "11054042",
        "nxdy_sttl_amt": "0",
        "nx2_day_sttl_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식예약주문정정취소

- **API ID**: v1_국내주식-018,019
- **실전 TR_ID**: (예약취소) CTSC0009U (예약정정) CTSC0013U
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 예약주문 정정/취소 API 입니다.
*  정정주문은 취소주문에 비해 필수 입력값이 추가 됩니다. 
   하단의 입력값을 참조하시기 바랍니다.

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>CTSC0009U : 국내주식예약취소주문<br>CTSC0013U : 국내주식예약정정주문<br>* 모의투자 사용 불가 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | [정정/취소] 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | [정정/취소] 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 종목코드(6자리) | string | Y | 12 | [정정] |
| 3 | `ORD_QTY` | 주문수량 | string | Y | 10 | [정정] 주문주식수 |
| 4 | `ORD_UNPR` | 주문단가 | string | Y | 19 | [정정] 1주당 가격 <br>* 장전 시간외, 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 권고 |
| 5 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | [정정]<br>01 : 매도<br>02 : 매수 |
| 6 | `ORD_DVSN_CD` | 주문구분코드 | string | Y | 2 | [정정]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>05 : 장전 시간외 |
| 7 | `ORD_OBJT_CBLC_DVSN_CD` | 주문대상잔고구분코드 | string | Y | 2 | [정정]<br>10 : 현금<br>12 : 주식담보대출<br>14 : 대여상환<br>21 : 자기융자신규<br>22 : 유통대주신규<br>23 : 유통융자신규<br>24 : 자기대주신규<br>25 : 자기융자상환<br>26 : 유통대주상환<br>27 : 유통융자상환<br>28 : 자기대주상환 |
| 8 | `LOAN_DT` | 대출일자 | string | N | 8 | [정정] |
| 9 | `RSVN_ORD_END_DT` | 예약주문종료일자 | string | N | 8 | [정정] |
| 10 | `CTAL_TLNO` | 연락전화번호 | string | N | 20 | [정정] |
| 11 | `RSVN_ORD_SEQ` | 예약주문순번 | string | Y | 10 | [정정/취소] |
| 12 | `RSVN_ORD_ORGNO` | 예약주문조직번호 | string | N | 5 | [정정/취소] |
| 13 | `RSVN_ORD_ORD_DT` | 예약주문주문일자 | string | N | 8 | [정정/취소] |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | array | Y |  |  |
| 4 | `nrml_prcs_yn` | 정상처리여부 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{ 
	"_comment": "주식예약주문취소", 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"RSVN_ORD_ORD_DT": "20220427", 
	"RSVN_ORD_SEQ": "39447", 
	"RSVN_ORD_ORGNO": "00" 
} 

{ 
	"_comment": "주식예약주문정정", 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"PDNO": "009150", 
	"ORD_QTY": "10", 
	"ORD_UNPR": "140000", 
	"SLL_BUY_DVSN_CD":"01", 
	"ORD_DVSN_CD":"00", 
	"ORD_OBJT_CBLC_DVSN_CD":"10", 
	"LOAN_DT":"", 
	"RSVN_ORD_END_DT":"", 
	"CTAC_TLNO": "", 
	"RSVN_ORD_SEQ":"39453", 
	"RSVN_ORD_ORGNO":"", 
	"RSVN_ORD_ORD_DT":"20220427" 
}
```

</details>


<details><summary>Response Example</summary>

```json
{ 
	"rt_cd": "0", 
	"msg_cd": "KIOK0430", 
	"msg1": "정상적으로 처리되었습니다", 
	"output": { 
		"NRML_PRCS_YN": "Y" 
	} 
}
```

</details>



### 신용매수가능조회

- **API ID**: v1_국내주식-042
- **실전 TR_ID**: TTTC8909R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-credit-psamount`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
신용매수가능조회 API입니다.
신용매수주문 시 주문가능수량과 금액을 확인하실 수 있습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC8909R |
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
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드(6자리) |
| 3 | `ORD_UNPR` | 주문단가 | string | Y | 19 | 1주당 가격 <br>* 장전 시간외, 장후 시간외, 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 권고 |
| 4 | `ORD_DVSN` | 주문구분 | string | Y | 2 | 00 : 지정가 <br>01 : 시장가 <br>02 : 조건부지정가 <br>03 : 최유리지정가 <br>04 : 최우선지정가 <br>05 : 장전 시간외 <br>06 : 장후 시간외 <br>07 : 시간외 단일가  등 |
| 5 | `CRDT_TYPE` | 신용유형 | string | Y | 2 | 21 : 자기융자신규 <br>23 : 유통융자신규 <br>26 : 유통대주상환 <br>28 : 자기대주상환 <br>25 : 자기융자상환 <br>27 : 유통융자상환 <br>22 : 유통대주신규 <br>24 : 자기대주신규 |
| 6 | `CMA_EVLU_AMT_ICLD_YN` | CMA평가금액포함여부 | string | Y | 1 | Y/N |
| 7 | `OVRS_ICLD_YN` | 해외포함여부 | string | Y | 1 | Y/N |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (16)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메시지 |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 |  |
| 5 | `ord_psbl_sbst` | 주문가능대용 | string | Y | 19 |  |
| 6 | `ruse_psbl_amt` | 재사용가능금액 | string | Y | 19 |  |
| 7 | `fund_rpch_chgs` | 펀드환매대금 | string | Y | 19 |  |
| 8 | `psbl_qty_calc_unpr` | 가능수량계산단가 | string | Y | 19 |  |
| 9 | `nrcvb_buy_amt` | 미수없는매수금액 | string | Y | 19 |  |
| 10 | `nrcvb_buy_qty` | 미수없는매수수량 | string | Y | 10 |  |
| 11 | `max_buy_amt` | 최대매수금액 | string | Y | 19 |  |
| 12 | `max_buy_qty` | 최대매수수량 | string | Y | 10 |  |
| 13 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 14 | `ovrs_re_use_amt_wcrc` | 해외재사용금액원화 | string | Y | 19 |  |
| 15 | `ord_psbl_frcr_amt_wcrc` | 주문가능외화금액원화 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "12345678",
"ACNT_PRDT_CD": "01",
"PDNO": "005930",
"ORD_UNPR" : "55000",
"ORD_DVSN": "01",
"CRDT_TYPE": "21",
"CMA_EVLU_AMT_ICLD_YN": "N",
"OVRS_ICLD_YN": "N"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "ord_psbl_cash": "99965177664",
        "ord_psbl_sbst": "156772560",
        "ruse_psbl_amt": "0",
        "fund_rpch_chgs": "0",
        "psbl_qty_calc_unpr": "69200",
        "nrcvb_buy_amt": "0",
        "nrcvb_buy_qty": "0",
        "max_buy_amt": "0",
        "max_buy_qty": "0",
        "cma_evlu_amt": "0",
        "ovrs_re_use_amt_wcrc": "0",
        "ord_psbl_frcr_amt_wcrc": "157998704172856"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식통합증거금 현황

- **API ID**: 국내주식-191
- **실전 TR_ID**: TTTC0869R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/intgr-margin`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
주식통합증거금 현황 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0867] 통합증거금조회 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ 해당 화면은 일반계좌와 통합증거금 신청계좌에 대해서 국내 및 해외 주문가능금액을 간단하게 조회하는 화면입니다.
※ 해외 국가별 상세한 증거금현황을 원하시면 [해외주식] 주문/계좌 &gt; 해외증거금 통화별조회 API를 이용하여 주시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC0869R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `CMA_EVLU_AMT_ICLD_YN` | CMA평가금액포함여부 | string | Y | 1 | N 입력 |
| 3 | `WCRC_FRCR_DVSN_CD` | 원화외화구분코드 | string | Y | 2 | 01(외화기준),02(원화기준) |
| 4 | `FWEX_CTRT_FRCR_DVSN_CD` | 선도환계약외화구분코드 | string | Y | 2 | 01(외화기준),02(원화기준) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (108)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `acmga_rt` | 계좌증거금율 | string | Y | 114 |  |
| 5 | `acmga_pct100_aptm_rson` | 계좌증거금100퍼센트지정사유 | string | Y | 100 |  |
| 6 | `stck_cash_objt_amt` | 주식현금대상금액 | string | Y | 184 |  |
| 7 | `stck_sbst_objt_amt` | 주식대용대상금액 | string | Y | 184 |  |
| 8 | `stck_evlu_objt_amt` | 주식평가대상금액 | string | Y | 184 |  |
| 9 | `stck_ruse_psbl_objt_amt` | 주식재사용가능대상금액 | string | Y | 184 |  |
| 10 | `stck_fund_rpch_chgs_objt_amt` | 주식펀드환매대금대상금액 | string | Y | 184 |  |
| 11 | `stck_fncg_rdpt_objt_atm` | 주식융자상환금대상금액 | string | Y | 184 |  |
| 12 | `bond_ruse_psbl_objt_amt` | 채권재사용가능대상금액 | string | Y | 184 |  |
| 13 | `stck_cash_use_amt` | 주식현금사용금액 | string | Y | 184 |  |
| 14 | `stck_sbst_use_amt` | 주식대용사용금액 | string | Y | 184 |  |
| 15 | `stck_evlu_use_amt` | 주식평가사용금액 | string | Y | 184 |  |
| 16 | `stck_ruse_psbl_amt_use_amt` | 주식재사용가능금사용금액 | string | Y | 184 |  |
| 17 | `stck_fund_rpch_chgs_use_amt` | 주식펀드환매대금사용금액 | string | Y | 184 |  |
| 18 | `stck_fncg_rdpt_amt_use_amt` | 주식융자상환금사용금액 | string | Y | 184 |  |
| 19 | `bond_ruse_psbl_amt_use_amt` | 채권재사용가능금사용금액 | string | Y | 184 |  |
| 20 | `stck_cash_ord_psbl_amt` | 주식현금주문가능금액 | string | Y | 184 |  |
| 21 | `stck_sbst_ord_psbl_amt` | 주식대용주문가능금액 | string | Y | 184 |  |
| 22 | `stck_evlu_ord_psbl_amt` | 주식평가주문가능금액 | string | Y | 184 |  |
| 23 | `stck_ruse_psbl_ord_psbl_amt` | 주식재사용가능주문가능금액 | string | Y | 184 |  |
| 24 | `stck_fund_rpch_ord_psbl_amt` | 주식펀드환매주문가능금액 | string | Y | 184 |  |
| 25 | `bond_ruse_psbl_ord_psbl_amt` | 채권재사용가능주문가능금액 | string | Y | 184 |  |
| 26 | `rcvb_amt` | 미수금액 | string | Y | 19 |  |
| 27 | `stck_loan_grta_ruse_psbl_amt` | 주식대출보증금재사용가능금액 | string | Y | 184 |  |
| 28 | `stck_cash20_max_ord_psbl_amt` | 주식현금20최대주문가능금액 | string | Y | 184 |  |
| 29 | `stck_cash30_max_ord_psbl_amt` | 주식현금30최대주문가능금액 | string | Y | 184 |  |
| 30 | `stck_cash40_max_ord_psbl_amt` | 주식현금40최대주문가능금액 | string | Y | 184 |  |
| 31 | `stck_cash50_max_ord_psbl_amt` | 주식현금50최대주문가능금액 | string | Y | 184 |  |
| 32 | `stck_cash60_max_ord_psbl_amt` | 주식현금60최대주문가능금액 | string | Y | 184 |  |
| 33 | `stck_cash100_max_ord_psbl_amt` | 주식현금100최대주문가능금액 | string | Y | 184 |  |
| 34 | `stck_rsip100_max_ord_psbl_amt` | 주식재사용불가100최대주문가능 | string | Y | 184 |  |
| 35 | `bond_max_ord_psbl_amt` | 채권최대주문가능금액 | string | Y | 184 |  |
| 36 | `stck_fncg45_max_ord_psbl_amt` | 주식융자45최대주문가능금액 | string | Y | 182 |  |
| 37 | `stck_fncg50_max_ord_psbl_amt` | 주식융자50최대주문가능금액 | string | Y | 184 |  |
| 38 | `stck_fncg60_max_ord_psbl_amt` | 주식융자60최대주문가능금액 | string | Y | 184 |  |
| 39 | `stck_fncg70_max_ord_psbl_amt` | 주식융자70최대주문가능금액 | string | Y | 182 |  |
| 40 | `stck_stln_max_ord_psbl_amt` | 주식대주최대주문가능금액 | string | Y | 184 |  |
| 41 | `lmt_amt` | 한도금액 | string | Y | 19 |  |
| 42 | `ovrs_stck_itgr_mgna_dvsn_name` | 해외주식통합증거금구분명 | string | Y | 40 |  |
| 43 | `usd_objt_amt` | 미화대상금액 | string | Y | 182 |  |
| 44 | `usd_use_amt` | 미화사용금액 | string | Y | 182 |  |
| 45 | `usd_ord_psbl_amt` | 미화주문가능금액 | string | Y | 182 |  |
| 46 | `hkd_objt_amt` | 홍콩달러대상금액 | string | Y | 182 |  |
| 47 | `hkd_use_amt` | 홍콩달러사용금액 | string | Y | 182 |  |
| 48 | `hkd_ord_psbl_amt` | 홍콩달러주문가능금액 | string | Y | 182 |  |
| 49 | `jpy_objt_amt` | 엔화대상금액 | string | Y | 182 |  |
| 50 | `jpy_use_amt` | 엔화사용금액 | string | Y | 182 |  |
| 51 | `jpy_ord_psbl_amt` | 엔화주문가능금액 | string | Y | 182 |  |
| 52 | `cny_objt_amt` | 위안화대상금액 | string | Y | 182 |  |
| 53 | `cny_use_amt` | 위안화사용금액 | string | Y | 182 |  |
| 54 | `cny_ord_psbl_amt` | 위안화주문가능금액 | string | Y | 182 |  |
| 55 | `usd_ruse_objt_amt` | 미화재사용대상금액 | string | Y | 182 |  |
| 56 | `usd_ruse_amt` | 미화재사용금액 | string | Y | 182 |  |
| 57 | `usd_ruse_ord_psbl_amt` | 미화재사용주문가능금액 | string | Y | 182 |  |
| 58 | `hkd_ruse_objt_amt` | 홍콩달러재사용대상금액 | string | Y | 182 |  |
| 59 | `hkd_ruse_amt` | 홍콩달러재사용금액 | string | Y | 182 |  |
| 60 | `hkd_ruse_ord_psbl_amt` | 홍콩달러재사용주문가능금액 | string | Y | 172 |  |
| 61 | `jpy_ruse_objt_amt` | 엔화재사용대상금액 | string | Y | 182 |  |
| 62 | `jpy_ruse_amt` | 엔화재사용금액 | string | Y | 182 |  |
| 63 | `jpy_ruse_ord_psbl_amt` | 엔화재사용주문가능금액 | string | Y | 182 |  |
| 64 | `cny_ruse_objt_amt` | 위안화재사용대상금액 | string | Y | 182 |  |
| 65 | `cny_ruse_amt` | 위안화재사용금액 | string | Y | 182 |  |
| 66 | `cny_ruse_ord_psbl_amt` | 위안화재사용주문가능금액 | string | Y | 182 |  |
| 67 | `usd_gnrl_ord_psbl_amt` | 미화일반주문가능금액 | string | Y | 182 |  |
| 68 | `usd_itgr_ord_psbl_amt` | 미화통합주문가능금액 | string | Y | 182 |  |
| 69 | `hkd_gnrl_ord_psbl_amt` | 홍콩달러일반주문가능금액 | string | Y | 182 |  |
| 70 | `hkd_itgr_ord_psbl_amt` | 홍콩달러통합주문가능금액 | string | Y | 182 |  |
| 71 | `jpy_gnrl_ord_psbl_amt` | 엔화일반주문가능금액 | string | Y | 182 |  |
| 72 | `jpy_itgr_ord_psbl_amt` | 엔화통합주문가능금액 | string | Y | 182 |  |
| 73 | `cny_gnrl_ord_psbl_amt` | 위안화일반주문가능금액 | string | Y | 182 |  |
| 74 | `cny_itgr_ord_psbl_amt` | 위안화통합주문가능금액 | string | Y | 182 |  |
| 75 | `stck_itgr_cash20_ord_psbl_amt` | 주식통합현금20주문가능금액 | string | Y | 182 |  |
| 76 | `stck_itgr_cash30_ord_psbl_amt` | 주식통합현금30주문가능금액 | string | Y | 182 |  |
| 77 | `stck_itgr_cash40_ord_psbl_amt` | 주식통합현금40주문가능금액 | string | Y | 182 |  |
| 78 | `stck_itgr_cash50_ord_psbl_amt` | 주식통합현금50주문가능금액 | string | Y | 182 |  |
| 79 | `stck_itgr_cash60_ord_psbl_amt` | 주식통합현금60주문가능금액 | string | Y | 182 |  |
| 80 | `stck_itgr_cash100_ord_psbl_amt` | 주식통합현금100주문가능금액 | string | Y | 182 |  |
| 81 | `stck_itgr_100_ord_psbl_amt` | 주식통합100주문가능금액 | string | Y | 182 |  |
| 82 | `stck_itgr_fncg45_ord_psbl_amt` | 주식통합융자45주문가능금액 | string | Y | 182 |  |
| 83 | `stck_itgr_fncg50_ord_psbl_amt` | 주식통합융자50주문가능금액 | string | Y | 182 |  |
| 84 | `stck_itgr_fncg60_ord_psbl_amt` | 주식통합융자60주문가능금액 | string | Y | 182 |  |
| 85 | `stck_itgr_fncg70_ord_psbl_amt` | 주식통합융자70주문가능금액 | string | Y | 182 |  |
| 86 | `stck_itgr_stln_ord_psbl_amt` | 주식통합대주주문가능금액 | string | Y | 182 |  |
| 87 | `bond_itgr_ord_psbl_amt` | 채권통합주문가능금액 | string | Y | 182 |  |
| 88 | `stck_cash_ovrs_use_amt` | 주식현금해외사용금액 | string | Y | 182 |  |
| 89 | `stck_sbst_ovrs_use_amt` | 주식대용해외사용금액 | string | Y | 182 |  |
| 90 | `stck_evlu_ovrs_use_amt` | 주식평가해외사용금액 | string | Y | 182 |  |
| 91 | `stck_re_use_amt_ovrs_use_amt` | 주식재사용금액해외사용금액 | string | Y | 182 |  |
| 92 | `stck_fund_rpch_ovrs_use_amt` | 주식펀드환매해외사용금액 | string | Y | 182 |  |
| 93 | `stck_fncg_rdpt_ovrs_use_amt` | 주식융자상환해외사용금액 | string | Y | 182 |  |
| 94 | `bond_re_use_ovrs_use_amt` | 채권재사용해외사용금액 | string | Y | 182 |  |
| 95 | `usd_oth_mket_use_amt` | 미화타시장사용금액 | string | Y | 182 |  |
| 96 | `jpy_oth_mket_use_amt` | 엔화타시장사용금액 | string | Y | 182 |  |
| 97 | `cny_oth_mket_use_amt` | 위안화타시장사용금액 | string | Y | 182 |  |
| 98 | `hkd_oth_mket_use_amt` | 홍콩달러타시장사용금액 | string | Y | 182 |  |
| 99 | `usd_re_use_oth_mket_use_amt` | 미화재사용타시장사용금액 | string | Y | 182 |  |
| 100 | `jpy_re_use_oth_mket_use_amt` | 엔화재사용타시장사용금액 | string | Y | 182 |  |
| 101 | `cny_re_use_oth_mket_use_amt` | 위안화재사용타시장사용금액 | string | Y | 182 |  |
| 102 | `hkd_re_use_oth_mket_use_amt` | 홍콩달러재사용타시장사용금액 | string | Y | 182 |  |
| 103 | `hgkg_cny_re_use_amt` | 홍콩위안화재사용금액 | string | Y | 182 |  |
| 104 | `usd_frst_bltn_exrt` | 미국달러최초고시환율 | string | Y | 23 |  |
| 105 | `hkd_frst_bltn_exrt` | 홍콩달러최초고시환율 | string | Y | 23 |  |
| 106 | `jpy_frst_bltn_exrt` | 일본엔화최초고시환율 | string | Y | 23 |  |
| 107 | `cny_frst_bltn_exrt` | 중국위안화최초고시환율 | string | Y | 23 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
CMA_EVLU_AMT_ICLD_YN:N
WCRC_FRCR_DVSN_CD:01
FWEX_CTRT_FRCR_DVSN_CD:01
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "acmga_rt": "100.0000",
        "acmga_pct100_aptm_rson": "고객100%신청",
        "stck_cash_objt_amt": "249855306.0000",
        "stck_sbst_objt_amt": "137816.0000",
        "stck_evlu_objt_amt": "176966.0000",
        "stck_ruse_psbl_objt_amt": "261213.0000",
        "stck_fund_rpch_chgs_objt_amt": "0.0000",
        "stck_fncg_rdpt_objt_atm": "0.0000",
        "bond_ruse_psbl_objt_amt": "1024.0000",
        "stck_cash_use_amt": "240482730.0000",
        "stck_sbst_use_amt": "20295.0000",
        "stck_evlu_use_amt": "20295.0000",
        "stck_ruse_psbl_amt_use_amt": "261213.0000",
        "stck_fund_rpch_chgs_use_amt": "0.0000",
        "stck_fncg_rdpt_amt_use_amt": "0.0000",
        "bond_ruse_psbl_amt_use_amt": "1024.0000",
        "stck_cash_ord_psbl_amt": "9372576.0000",
        "stck_sbst_ord_psbl_amt": "117521.0000",
        "stck_evlu_ord_psbl_amt": "156671.0000",
        "stck_ruse_psbl_ord_psbl_amt": "0.0000",
        "stck_fund_rpch_ord_psbl_amt": "0.0000",
        "bond_ruse_psbl_ord_psbl_amt": "0.0000",
        "rcvb_amt": "0",
        "stck_loan_grta_ruse_psbl_amt": "0.0000",
        "stck_cash20_max_ord_psbl_amt": "8128560.1990",
        "stck_cash30_max_ord_psbl_amt": "8128560.1990",
        "stck_cash40_max_ord_psbl_amt": "8128560.1990",
        "stck_cash50_max_ord_psbl_amt": "8128560.1990",
        "stck_cash60_max_ord_psbl_amt": "8128560.1990",
        "stck_cash100_max_ord_psbl_amt": "8128560.1990",
        "stck_rsip100_max_ord_psbl_amt": "8128560.1990",
        "bond_max_ord_psbl_amt": "9316675.9443",
        "stck_fncg45_max_ord_psbl_amt": "20942905.49",
        "stck_fncg50_max_ord_psbl_amt": "18869350.4950",
        "stck_fncg60_max_ord_psbl_amt": "15750449.5868",
        "stck_fncg70_max_ord_psbl_amt": "13516343.26",
        "stck_stln_max_ord_psbl_amt": "9307424.0318",
        "lmt_amt": "0",
        "ovrs_stck_itgr_mgna_dvsn_name": "",
        "usd_objt_amt": "0.00",
        "usd_use_amt": "0.00",
        "usd_ord_psbl_amt": "0.00",
        "hkd_objt_amt": "0.00",
        "hkd_use_amt": "0.00",
        "hkd_ord_psbl_amt": "0.00",
        "jpy_objt_amt": "0.00",
        "jpy_use_amt": "0.00",
        "jpy_ord_psbl_amt": "0.00",
        "cny_objt_amt": "0.00",
        "cny_use_amt": "0.00",
        "cny_ord_psbl_amt": "0.00",
        "usd_ruse_objt_amt": "0.00",
        "usd_ruse_amt": "0.00",
        "usd_ruse_ord_psbl_amt": "0.00",
        "hkd_ruse_objt_amt": "0.00",
        "hkd_ruse_amt": "0.00",
        "hkd_ruse_ord_psbl_amt": "0.00",
        "jpy_ruse_objt_amt": "0.00",
        "jpy_ruse_amt": "0.00",
        "jpy_ruse_ord_psbl_amt": "0.00",
        "cny_ruse_objt_amt": "0.00",
        "cny_ruse_amt": "0.00",
        "cny_ruse_ord_psbl_amt": "0.00",
        "usd_gnrl_ord_psbl_amt": "0.00",
        "usd_itgr_ord_psbl_amt": "0.00",
        "hkd_gnrl_ord_psbl_amt": "0.00",
        "hkd_itgr_ord_psbl_amt": "0.00",
        "jpy_gnrl_ord_psbl_amt": "0.00",
        "jpy_itgr_ord_psbl_amt": "0.00",
        "cny_gnrl_ord_psbl_amt": "0.00",
        "cny_itgr_ord_psbl_amt": "0.00",
        "stck_itgr_cash20_ord_psbl_amt": "0.00",
        "stck_itgr_cash30_ord_psbl_amt": "0.00",
        "stck_itgr_cash40_ord_psbl_amt": "0.00",
        "stck_itgr_cash50_ord_psbl_amt": "0.00",
        "stck_itgr_cash60_ord_psbl_amt": "0.00",
        "stck_itgr_cash100_ord_psbl_amt": "0.00",
        "stck_itgr_100_ord_psbl_amt": "0.00",
        "stck_itgr_fncg45_ord_psbl_amt": "0.00",
        "stck_itgr_fncg50_ord_psbl_amt": "0.00",
        "stck_itgr_fncg60_ord_psbl_amt": "0.00",
        "stck_itgr_fncg70_ord_psbl_amt": "0.00",
        "stck_itgr_stln_ord_psbl_amt": "0.00",
        "bond_itgr_ord_psbl_amt": "0.00",
        "stck_cash_ovrs_use_amt": "0.00",
        "stck_sbst_ovrs_use_amt": "0.00",
        "stck_evlu_ovrs_use_amt": "0.00",
        "stck_re_use_amt_ovrs_use_amt": "0.00",
        "stck_fund_rpch_ovrs_use_amt": "0.00",
        "stck_fncg_rdpt_ovrs_use_amt": "0.00",
        "bond_re_use_ovrs_use_amt": "0.00",
        "usd_oth_mket_use_amt": "0.00",
        "jpy_oth_mket_use_amt": "0.00",
        "cny_oth_mket_use_amt": "0.00",
        "hkd_oth_mket_use_amt": "0.00",
        "usd_re_use_oth_mket_use_amt": "0.00",
        "jpy_re_use_oth_mket_use_amt": "0.00",
        "cny_re_use_oth_mket_use_amt": "0.00",
        "hkd_re_use_oth_mket_use_amt": "0.00",
        "hgkg_cny_re_use_amt": "0.00",
        "hgkg_cny_re_use_objt_amt": "0.00",
        "hgkg_cny_re_use_ord_psbl_amt": "0.00",
        "hgkg_cny_re_use_oth_use_amt": "0.00"
        "hgkg_cny_re_use_oth_use_amt": "0.00",
        "usd_frst_bltn_exrt": "1467.00000000",
        "hkd_frst_bltn_exrt": "188.61000000",
        "jpy_frst_bltn_exrt": "10.06000000",
        "cny_frst_bltn_exrt": "200.70000000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 퇴직연금 미체결내역

- **API ID**: v1_국내주식-033
- **실전 TR_ID**: TTTC2201R(기존 KRX만 가능), TTTC2210R (KRX,NXT/SOR)
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
​※ 55번 계좌(DC가입자계좌)의 경우 해당 API 이용이 불가합니다.
KIS Developers API의 경우 HTS ID에 반드시 연결되어있어야만 API 신청 및 앱정보 발급이 가능한 서비스로 개발되어서 실물계좌가 아닌 55번 계좌는 API 이용이 불가능한 점 양해 부탁드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC2201R(기존 KRX만 가능), TTTC2210R (KRX,NXT/SOR) |
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
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 29 |
| 2 | `USER_DVSN_CD` | 사용자구분코드 | string | Y | 2 | %% |
| 3 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 00 : 전체 / 01 : 매도 / 02 : 매수 |
| 4 | `CCLD_NCCS_DVSN` | 체결미체결구분 | string | Y | 2 | %% : 전체 / 01 : 체결 / 02 : 미체결 |
| 5 | `INQR_DVSN_3` | 조회구분3 | string | Y | 2 | 00 : 전체 |
| 6 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 |  |
| 7 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (24)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세1 | object array | Y |  | Array |
| 4 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 |  |
| 5 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 |  |
| 6 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 7 | `odno` | 주문번호 | string | Y | 10 |  |
| 8 | `pdno` | 상품번호 | string | Y | 12 |  |
| 9 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 10 | `ord_unpr` | 주문단가 | string | Y | 19 |  |
| 11 | `ord_qty` | 주문수량 | string | Y | 10 |  |
| 12 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 |  |
| 13 | `nccs_qty` | 미체결수량 | string | Y | 10 |  |
| 14 | `ord_dvsn_cd` | 주문구분코드 | string | Y | 2 |  |
| 15 | `ord_dvsn_name` | 주문구분명 | string | Y | 60 |  |
| 16 | `orgn_odno` | 원주문번호 | string | Y | 10 |  |
| 17 | `ord_tmd` | 주문시각 | string | Y | 6 |  |
| 18 | `objt_cust_dvsn_name` | 대상고객구분명 | string | Y | 10 |  |
| 19 | `pchs_avg_pric` | 매입평균가격 | string | Y | 184 |  |
| 20 | `stpm_cndt_pric` | 스톱지정가조건가격 | string | Y | 9 | 신규 API용 필드 |
| 21 | `stpm_efct_occr_dtmd` | 스톱지정가효력발생상세시각 | string | Y | 9 | 신규 API용 필드 |
| 22 | `stpm_efct_occr_yn` | 스톱지정가효력발생여부 | string | Y | 1 | 신규 API용 필드 |
| 23 | `excg_id_dvsn_cd` | 거래소ID구분코드 | string | Y | 3 | 신규 API용 필드 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"USER_DVSN_CD":"%%",
	"SLL_BUY_DVSN_CD":"00",
	"CCLD_NCCS_DVSN":"%%",
	"INQR_DVSN_3":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "63512345^29^%%^00^%%^00^                                                                            ",
    "ctx_area_nk100": "^^                                                                                                  ",
    "output": [],
    "rt_cd": "0",
    "msg_cd": "KIOK0490",
    "msg1": "조회가 계속됩니다                                                               "
}
```

</details>



### 기간별매매손익현황조회

- **API ID**: v1_국내주식-060
- **실전 TR_ID**: TTTC8715R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-period-trade-profit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
기간별매매손익현황조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0856] 기간별 매매손익 화면 에서 "종목별" 클릭 시의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC8715R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (9)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `SORT_DVSN` | 정렬구분 | string | Y | 2 | 00: 최근 순, 01: 과거 순, 02: 최근 순 |
| 2 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 3 | `PDNO` | 상품번호 | string | Y | 12 | ""공란입력 시, 전체 |
| 4 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 |  |
| 5 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 |  |
| 6 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 |  |
| 7 | `CBLC_DVSN` | 잔고구분 | string | Y | 2 | 00: 전체 |
| 8 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (42)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `ctx_area_nk100` | 연속조회키100 | string | Y | 100 |  |
| 4 | `ctx_area_fk100` | 연속조회검색조건100 | string | Y | 100 |  |
| 5 | `output1` | 응답상세 | object array | Y |  | array |
| 6 | `trad_dt` | 매매일자 | string | Y | 8 |  |
| 7 | `pdno` | 상품번호 | string | Y | 12 | 종목번호(뒤 6자리만 해당) |
| 8 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 9 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 10 | `loan_dt` | 대출일자 | string | Y | 8 |  |
| 11 | `hldg_qty` | 보유수량 | string | Y | 19 |  |
| 12 | `pchs_unpr` | 매입단가 | string | Y | 19 |  |
| 13 | `buy_qty` | 매수수량 | string | Y | 10 |  |
| 14 | `buy_amt` | 매수금액 | string | Y | 19 |  |
| 15 | `sll_pric` | 매도가격 | string | Y | 10 |  |
| 16 | `sll_qty` | 매도수량 | string | Y | 10 |  |
| 17 | `sll_amt` | 매도금액 | string | Y | 19 |  |
| 18 | `rlzt_pfls` | 실현손익 | string | Y | 19 |  |
| 19 | `pfls_rt` | 손익률 | string | Y | 238 |  |
| 20 | `fee` | 수수료 | string | Y | 19 |  |
| 21 | `tl_tax` | 제세금 | string | Y | 19 |  |
| 22 | `loan_int` | 대출이자 | string | Y | 19 |  |
| 23 | `output2` | 응답상세2 | object | Y |  |  |
| 24 | `sll_qty_smtl` | 매도수량합계 | string | Y | 19 |  |
| 25 | `sll_tr_amt_smtl` | 매도거래금액합계 | string | Y | 19 |  |
| 26 | `sll_fee_smtl` | 매도수수료합계 | string | Y | 19 |  |
| 27 | `sll_tltx_smtl` | 매도제세금합계 | string | Y | 19 |  |
| 28 | `sll_excc_amt_smtl` | 매도정산금액합계 | string | Y | 19 |  |
| 29 | `buyqty_smtl` | 매수수량합계 | string | Y | 8 |  |
| 30 | `buy_tr_amt_smtl` | 매수거래금액합계 | string | Y | 19 |  |
| 31 | `buy_fee_smtl` | 매수수수료합계 | string | Y | 19 |  |
| 32 | `buy_tax_smtl` | 매수제세금합계 | string | Y | 19 |  |
| 33 | `buy_excc_amt_smtl` | 매수정산금액합계 | string | Y | 19 |  |
| 34 | `tot_qty` | 총수량 | string | Y | 10 |  |
| 35 | `tot_tr_amt` | 총거래금액 | string | Y | 19 |  |
| 36 | `tot_fee` | 총수수료 | string | Y | 19 |  |
| 37 | `tot_tltx` | 총제세금 | string | Y | 19 |  |
| 38 | `tot_excc_amt` | 총정산금액 | string | Y | 19 |  |
| 39 | `tot_rlzt_pfls` | 총실현손익 | string | Y | 19 |  |
| 40 | `loan_int` | 대출이자 | string | Y | 19 |  |
| 41 | `tot_pftrt` | 총수익률 | string | Y | 238 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"PDNO":"",
"INQR_STRT_DT":"20240216",
"INQR_END_DT":"20240216",
"SORT_DVSN":"02",
"CBLC_DVSN":"00",
"CTX_AREA_FK100":""
"CTX_AREA_FK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "                                                                                                    ",
    "ctx_area_nk100": "20240216^00000A000120^300^0^00000000^                                                               ",
    "output1": [
        {
            "trad_dt": "20240216",
            "pdno": "000J2552221D",
            "prdt_name": "SG 17WR",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "135",
            "buy_qty": "2",
            "buy_amt": "271",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "000J00532219",
            "prdt_name": "국동 9WR",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "130",
            "buy_qty": "10",
            "buy_amt": "1300",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000Q520057",
            "prdt_name": "미래에셋 인버스 2X 코스닥150 선물 ETN",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "9365",
            "buy_qty": "1",
            "buy_amt": "9365",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A900270",
            "prdt_name": "헝셩그룹",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "66",
            "pchs_unpr": "322",
            "buy_qty": "66",
            "buy_amt": "21252",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A402340",
            "prdt_name": "SK스퀘어",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "59000",
            "buy_qty": "10",
            "buy_amt": "590000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A373220",
            "prdt_name": "LG에너지솔루션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "552000",
            "buy_qty": "10",
            "buy_amt": "5520000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A361610",
            "prdt_name": "SK아이이테크놀로지",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "110000",
            "buy_qty": "10",
            "buy_amt": "1100000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A352820",
            "prdt_name": "하이브",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "383000",
            "buy_qty": "2",
            "buy_amt": "766000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A302440",
            "prdt_name": "SK바이오사이언스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "100000",
            "buy_qty": "10",
            "buy_amt": "1000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A298050",
            "prdt_name": "효성첨단소재",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "480000",
            "buy_qty": "2",
            "buy_amt": "960000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A298020",
            "prdt_name": "효성티앤씨",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "365000",
            "buy_qty": "2",
            "buy_amt": "730000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A285130",
            "prdt_name": "SK케미칼",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "100000",
            "buy_qty": "10",
            "buy_amt": "1000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A136480",
            "prdt_name": "하림",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "220",
            "pchs_unpr": "2893",
            "buy_qty": "226",
            "buy_amt": "526563",
            "sll_pric": "2936",
            "sll_qty": "7",
            "sll_amt": "20555",
            "rlzt_pfls": "304",
            "pfls_rt": "1.50116044",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A114090",
            "prdt_name": "GKL",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "15010",
            "buy_qty": "1",
            "buy_amt": "15010",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A097950",
            "prdt_name": "CJ제일제당",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "210500",
            "buy_qty": "10",
            "buy_amt": "2105000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A096770",
            "prdt_name": "SK이노베이션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "228000",
            "buy_qty": "10",
            "buy_amt": "2280000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A093370",
            "prdt_name": "후성",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "15510",
            "buy_qty": "2",
            "buy_amt": "31020",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A057050",
            "prdt_name": "현대홈쇼핑",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "30100",
            "buy_qty": "2",
            "buy_amt": "60200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A047050",
            "prdt_name": "포스코인터내셔널",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "74400",
            "buy_qty": "2",
            "buy_amt": "148800",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A036460",
            "prdt_name": "한국가스공사",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "27850",
            "buy_qty": "2",
            "buy_amt": "55700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035760",
            "prdt_name": "CJ ENM",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "11",
            "pchs_unpr": "58836",
            "buy_qty": "11",
            "buy_amt": "647200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035420",
            "prdt_name": "NAVER",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "356000",
            "buy_qty": "10",
            "buy_amt": "3560000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A035250",
            "prdt_name": "강원랜드",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "20950",
            "buy_qty": "10",
            "buy_amt": "209500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A034730",
            "prdt_name": "SK",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "182700",
            "buy_qty": "10",
            "buy_amt": "1827000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A030200",
            "prdt_name": "KT",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "26050",
            "buy_qty": "10",
            "buy_amt": "260500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A028670",
            "prdt_name": "팬오션",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "4865",
            "buy_qty": "2",
            "buy_amt": "9730",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A028260",
            "prdt_name": "삼성물산",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "5",
            "pchs_unpr": "156100",
            "buy_qty": "5",
            "buy_amt": "780500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A018260",
            "prdt_name": "삼성에스디에스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "250000",
            "buy_qty": "2",
            "buy_amt": "500000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A017670",
            "prdt_name": "SK텔레콤",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "50100",
            "buy_qty": "10",
            "buy_amt": "501000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A015760",
            "prdt_name": "한국전력",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "4",
            "pchs_unpr": "8030",
            "buy_qty": "4",
            "buy_amt": "32120",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A011790",
            "prdt_name": "SKC",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "49950",
            "buy_qty": "10",
            "buy_amt": "499500",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A011780",
            "prdt_name": "금호석유",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "200000",
            "buy_qty": "10",
            "buy_amt": "2000000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A009540",
            "prdt_name": "HD한국조선해양",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "170000",
            "buy_qty": "10",
            "buy_amt": "1700000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A008770",
            "prdt_name": "호텔신라",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "99850",
            "buy_qty": "2",
            "buy_amt": "199700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A006260",
            "prdt_name": "LS",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "122000",
            "buy_qty": "10",
            "buy_amt": "1220000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005940",
            "prdt_name": "NH투자증권",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "11710",
            "buy_qty": "10",
            "buy_amt": "117100",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1414",
            "pchs_unpr": "53213",
            "buy_qty": "1415",
            "buy_amt": "75510700",
            "sll_pric": "75900",
            "sll_qty": "1",
            "sll_amt": "75900",
            "rlzt_pfls": "22687",
            "pfls_rt": "42.63431868",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005490",
            "prdt_name": "POSCO홀딩스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "133500",
            "buy_qty": "10",
            "buy_amt": "1335000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A005380",
            "prdt_name": "현대차",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "240500",
            "buy_qty": "2",
            "buy_amt": "481000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A004800",
            "prdt_name": "효성",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "66400",
            "buy_qty": "2",
            "buy_amt": "132800",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A003670",
            "prdt_name": "포스코퓨처엠",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "531000",
            "buy_qty": "2",
            "buy_amt": "1062000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A003550",
            "prdt_name": "LG",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "105600",
            "buy_qty": "2",
            "buy_amt": "211200",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A002380",
            "prdt_name": "KCC",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "252000",
            "buy_qty": "1",
            "buy_amt": "252000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A001120",
            "prdt_name": "LX인터내셔널",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "1",
            "pchs_unpr": "34050",
            "buy_qty": "1",
            "buy_amt": "34050",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000990",
            "prdt_name": "DB하이텍",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "23000",
            "buy_qty": "2",
            "buy_amt": "46000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000670",
            "prdt_name": "영풍",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "4",
            "pchs_unpr": "640750",
            "buy_qty": "4",
            "buy_amt": "2563000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000660",
            "prdt_name": "SK하이닉스",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "12",
            "pchs_unpr": "122583",
            "buy_qty": "10",
            "buy_amt": "1345000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000270",
            "prdt_name": "기아",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "84500",
            "buy_qty": "10",
            "buy_amt": "845000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000240",
            "prdt_name": "한국앤컴퍼니",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "2",
            "pchs_unpr": "23850",
            "buy_qty": "2",
            "buy_amt": "47700",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        },
        {
            "trad_dt": "20240216",
            "pdno": "00000A000210",
            "prdt_name": "DL",
            "trad_dvsn_name": "현금",
            "loan_dt": "",
            "hldg_qty": "10",
            "pchs_unpr": "50400",
            "buy_qty": "10",
            "buy_amt": "504000",
            "sll_pric": "0",
            "sll_qty": "0",
            "sll_amt": "0",
            "rlzt_pfls": "0",
            "pfls_rt": "0.00000000",
            "fee": "0",
            "tl_tax": "0",
            "loan_int": "0"
        }
    ],
    "output2": {
        "sll_qty_smtl": "8",
        "sll_tr_amt_smtl": "96455",
        "sll_fee_smtl": "0",
        "sll_tltx_smtl": "0",
        "sll_excc_amt_smtl": "96455",
        "buyqty_smtl": "2003",
        "buy_tr_amt_smtl": "116697331",
        "buy_fee_smtl": "0",
        "buy_tax_smtl": "0",
        "buy_excc_amt_smtl": "116697331",
        "tot_qty": "2011",
        "tot_tr_amt": "116793786",
        "tot_fee": "0",
        "tot_tltx": "0",
        "tot_excc_amt": "116793786",
        "tot_rlzt_pfls": "22991",
        "loan_int": "0",
        "tot_pftrt": "31.29560057"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0500",
    "msg1": "조회가 계속됩니다..다음버튼을 Click 하십시오.                                   "
}
```

</details>



### 주식주문(정정취소)

- **API ID**: v1_국내주식-003
- **실전 TR_ID**: TTTC0013U
- **모의 TR_ID**: VTTC0013U
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
주문 건에 대하여 정정 및 취소하는 API입니다. 단, 이미 체결된 건은 정정 및 취소가 불가합니다.

※ 정정은 원주문에 대한 주문단가 혹은 주문구분을 변경하는 사항으로, 정정이 가능한 수량은 원주문수량을 초과 할 수 없습니다.

※ 주식주문(정정취소) 호출 전에 반드시 주식정정취소가능주문조회 호출을 통해 정정취소가능수량(output &gt; psbl_qty)을 확인하신 후 정정취소주문 내시기 바랍니다.

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | ※ 구TR은 사전고지 없이 막힐 수 있으므로 반드시 신TR로 변경이용 부탁드립니다.<br>[실전투자]<br>정정/취소 (구)TTTC0803U → (신)TTTC0013U<br>정정/취소 (모의투자) (구)VTTC0803U → (신)VTTC0013U |
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
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 종합계좌번호 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 상품유형코드 |
| 2 | `KRX_FWDG_ORD_ORGNO` | 한국거래소전송주문조직번호 | string | Y | 5 |  |
| 3 | `ORGN_ODNO` | 원주문번호 | string | Y | 10 | 원주문번호 |
| 4 | `ORD_DVSN` | 주문구분 | string | Y | 2 | [KRX]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[NXT]<br>00 : 지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[SOR]<br>00 : 지정가<br>01 : 시장가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br><br>**▼ 아래는 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월) 반영분**<br>[KRX 애프터마켓] 16:00~20:00 · KRX 정규장과 **분리된 시장**이라 호가유형 선택 **필수** · **ETP(ETF/ETN) 거래 불가**<br>41 : KRX애프터마켓지정가<br>42 : KRX애프터마켓지정가IOC<br>43 : KRX애프터마켓지정가FOK<br>44 : KRX애프터마켓최유리지정가<br>45 : KRX애프터마켓최유리지정가IOC<br>46 : KRX애프터마켓최유리지정가FOK<br>47 : KRX애프터마켓최우선지정가<br>[NXT 프리마켓 GTP] Good Till Pre-Market — 미체결잔량은 **프리마켓 종료(08:50) 일괄 취소**<br>27 : NXT GTP지정가<br>28 : NXT GTP최유리<br>29 : NXT GTP최우선<br>※ 같은 공지로 **시간외단일가가 폐지**되므로 위 `07 : 시간외 단일가` 는 2026-09-14 부터 무효다<br>※ 애프터마켓에 **시장가(`01`)는 없다** — 지정가 계열 7종만 접수된다 |
| 5 | `RVSE_CNCL_DVSN_CD` | 정정취소구분코드 | string | Y | 2 | 01@정정<br>02@취소 |
| 6 | `ORD_QTY` | 주문수량 | string | Y | 10 | 주문수량 |
| 7 | `ORD_UNPR` | 주문단가 | string | Y | 19 | 주문단가 |
| 8 | `QTY_ALL_ORD_YN` | 잔량전부주문여부 | string | Y | 1 | 'Y@전량<br>N@일부' |
| 9 | `CNDT_PRIC` | 조건가격 | string | N | 19 | 스탑지정가호가에서 사용 |
| 10 | `EXCG_ID_DVSN_CD` | 거래소ID구분코드 | string | N | 3 | 한국거래소 : KRX<br>대체거래소 (넥스트레이드) : NXT<br>SOR (Smart Order Routing) : SOR<br>→ 미입력시 KRX로 진행되며, 모의투자는 KRX만 가능 |

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
| 3 | `output` | 응답상세 | object array | Y |  | single |
| 4 | `krx_fwdg_ord_orgno` | 한국거래소전송주문조직번호 | string | Y | 5 |  |
| 5 | `odno` | 주문번호 | string | Y | 10 |  |
| 6 | `ord_tmd` | 주문시각 | string | Y | 6 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO": "810XXXXX",
"ACNT_PRDT_CD": "01",
"KRX_FWDG_ORD_ORGNO": "",
"ORGN_ODNO": "0001566017",
"ORD_DVSN": "00",
"RVSE_CNCL_DVSN_CD": "01",
"ORD_QTY": "1",
"ORD_UNPR": "180000",
"QTY_ALL_ORD_YN": "N"
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
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569139",
    "ORD_TMD": "131438"
  }
}
```

</details>



### 주식예약주문조회

- **API ID**: v1_국내주식-020
- **실전 TR_ID**: CTSC0004R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내예약주문 처리내역 조회 API 입니다.
실전계좌/모의계좌의 경우, 한 번의 호출에 최대 20건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>CTSC0004R : 국내주식예약주문조회<br>* 모의투자 사용 불가 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `RSVN_ORD_ORD_DT` | 예약주문시작일자 | string | Y | 8 |  |
| 1 | `RSVN_ORD_END_DT` | 예약주문종료일자 | string | Y | 8 |  |
| 2 | `RSVN_ORD_SEQ` | 예약주문순번 | string | Y | 10 |  |
| 3 | `TMNL_MDIA_KIND_CD` | 단말매체종류코드 | string | Y | 2 | "00" 입력 |
| 4 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 5 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 6 | `PRCS_DVSN_CD` | 처리구분코드 | string | Y | 2 | 0: 전체<br>1: 처리내역<br>2: 미처리내역 |
| 7 | `CNCL_YN` | 취소여부 | string | Y | 1 | "Y" 유효한 주문만 조회 |
| 8 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드(6자리) (공백 입력 시 전체 조회) |
| 9 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 |  |
| 10 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 다음 페이지 조회시 사용 |
| 11 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 다음 페이지 조회시 사용 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (27)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | array | Y |  |  |
| 4 | `rsvn_ord_seq` | 예약주문 순번 | string | N | 10 |  |
| 5 | `rsvn_ord_ord_dt` | 예약주문주문일자 | string | N | 8 |  |
| 6 | `rsvn_ord_rcit_dt` | 예약주문접수일자 | string | N | 8 |  |
| 7 | `pdno` | 상품번호 | string | N | 12 |  |
| 8 | `ord_dvsn_cd` | 주문구분코드 | string | N | 2 |  |
| 9 | `ord_rsvn_qty` | 주문예약수량 | string | N | 10 |  |
| 10 | `tot_ccld_qty` | 총체결수량 | string | N | 10 |  |
| 11 | `cncl_ord_dt` | 취소주문일자 | string | N | 8 |  |
| 12 | `ord_tmd` | 주문시각 | string | N | 6 |  |
| 13 | `ctac_tlno` | 연락전화번호 | string | N | 20 |  |
| 14 | `rjct_rson2` | 거부사유2 | string | N | 200 |  |
| 15 | `odno` | 주문번호 | string | N | 10 |  |
| 16 | `rsvn_ord_rcit_tmd` | 예약주문접수시각 | string | N | 6 |  |
| 17 | `kor_item_shtn_name` | 한글종목단축명 | string | N | 60 |  |
| 18 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | N | 2 |  |
| 19 | `ord_rsvn_unpr` | 주문예약단가 | string | N | 19 |  |
| 20 | `tot_ccld_amt` | 총체결금액 | string | N | 19 |  |
| 21 | `loan_dt` | 대출일자 | string | N | 8 |  |
| 22 | `cncl_rcit_tmd` | 취소접수시각 | string | N | 6 |  |
| 23 | `prcs_rslt` | 처리결과 | string | N | 60 |  |
| 24 | `ord_dvsn_name` | 주문구분명 | string | N | 60 |  |
| 25 | `tmnl_mdia_kind_cd` | 단말매체종류코드 | string | N | 2 |  |
| 26 | `rsvn_end_dt` | 예약종료일자 | string | N | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"RSVN_ORD_ORD_DT":"20220520",
	"RSVN_ORD_END_DT":"20220523",
	"RSVN_ORD_SEQ":"",
	"TMNL_MDIA_KIND_CD":"00",
	"CANO":"81019970",
	"ACNT_PRDT_CD":"01",
	
	"PRCS_DVSN_CD":"0",
	"CNCL_YN":"Y",
	"PDNO":"",
	"SLL_BUY_DVSN_CD":"",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "20220520!^null!^0!^Y!^!^                                                                                                                                                                                ",
    "ctx_area_nk200": " !^ !^                                                                                                                                                                                                  ",
    "output": [
        {
            "rsvn_ord_seq": "42401",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "165318",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": "20220523"
        },
        {
            "rsvn_ord_seq": "42405",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "170422",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": ""
        },
        {
            "rsvn_ord_seq": "42406",
            "rsvn_ord_ord_dt": "20220523",
            "rsvn_ord_rcit_dt": "20220520",
            "pdno": "005940",
            "ord_dvsn_cd": "01",
            "ord_rsvn_qty": "1",
            "tot_ccld_qty": "0",
            "cncl_ord_dt": "",
            "ord_tmd": "",
            "ctac_tlno": "0",
            "rjct_rson2": "",
            "odno": "",
            "rsvn_ord_rcit_tmd": "170453",
            "kor_item_shtn_name": "NH투자증권",
            "sll_buy_dvsn_cd": "02",
            "ord_rsvn_unpr": "6000",
            "tot_ccld_amt": "0",
            "loan_dt": "",
            "cncl_rcit_tmd": "",
            "prcs_rslt": "미처리",
            "ord_dvsn_name": "현금매수",
            "tmnl_mdia_kind_cd": "31",
            "rsvn_end_dt": "20220523"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 퇴직연금 매수가능조회

- **API ID**: v1_국내주식-034
- **실전 TR_ID**: TTTC0503R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-psbl-order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
​※ 55번 계좌(DC가입자계좌)의 경우 해당 API 이용이 불가합니다.
KIS Developers API의 경우 HTS ID에 반드시 연결되어있어야만 API 신청 및 앱정보 발급이 가능한 서비스로 개발되어서 실물계좌가 아닌 55번 계좌는 API 이용이 불가능한 점 양해 부탁드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC0503R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 29 |
| 2 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 3 | `ACCA_DVSN_CD` | 적립금구분코드 | string | Y | 2 | 00 |
| 4 | `CMA_EVLU_AMT_ICLD_YN` | CMA평가금액포함여부 | string | Y | 1 |  |
| 5 | `ORD_DVSN` | 주문구분 | string | Y | 2 | 00 : 지정가 / 01 : 시장가 |
| 6 | `ORD_UNPR` | 주문단가 | string | Y | 19 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (9)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세1 | object | Y |  |  |
| 4 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 |  |
| 5 | `ruse_psbl_amt` | 재사용가능금액 | string | Y | 19 |  |
| 6 | `psbl_qty_calc_unpr` | 가능수량계산단가 | string | Y | 19 |  |
| 7 | `max_buy_amt` | 최대매수금액 | string | Y | 19 |  |
| 8 | `max_buy_qty` | 최대매수수량 | string | Y | 10 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"PDNO":"029513",
	"ORD_UNPR":"55000",
	"ORD_DVSN":"00",
	"CMA_EVLU_AMT_ICLD_YN":"N",
	"ACCA_DVSN_CD":"00"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "ord_psbl_cash": "11054042",
        "ruse_psbl_amt": "0",
        "psbl_qty_calc_unpr": "55000",
        "max_buy_amt": "11054042",
        "max_buy_qty": "200"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식잔고조회

- **API ID**: v1_국내주식-006
- **실전 TR_ID**: TTTC8434R
- **모의 TR_ID**: VTTC8434R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
주식 잔고조회 API입니다. 
실전계좌의 경우, 한 번의 호출에 최대 50건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 
모의계좌의 경우, 한 번의 호출에 최대 20건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 

* 당일 전량매도한 잔고도 보유수량 0으로 보여질 수 있으나, 해당 보유수량 0인 잔고는 최종 D-2일 이후에는 잔고에서 사라집니다.

※ 중요 
1) 해당 API는 제공 정보량이 많아 조회속도가 느린 API입니다. 주문 준비를 위해서는 주식매수/매도가능수량 조회 TR 사용을 권장 드립니다.
2) 해당 API는 과도한 트래픽이 몰릴 시 당사 시스템에 큰 제약사항을 줄 수 있는 TR로 원장 유량정책에 의거, 개인 고객 유량 무관하게 초당 120 TPS로 제한되어 있습니다.
   "EGW00215 원장에서 허용 가능한 초당 거래건수를 초과하였습니다." 메시지는 해당 사유에 의해 발생한 건이오니, 이 경우에는 재시도 처리 부탁드리겠습니다.
   * 원장 언급이 없는 "초당 거래건수를 초과하였습니다." 메시지는 개인 유량 초과 시 발생하는 메시지로 착오 없으시길 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTC8434R : 주식 잔고 조회<br>[모의투자]<br>VTTC8434R : 주식 잔고 조회 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `AFHR_FLPR_YN` | 시간외단일가, 거래소여부 | string | Y | 1 | N : 기본값,<br>Y : 시간외단일가,<br>X : NXT 정규장 (프리마켓, 메인, 애프터마켓)<br>※ NXT 선택 시 : NXT 거래종목만 시세 등 정보가 NXT 기준으로 변동됩니다. KRX 종목들은 그대로 유지<br><br>**▼ 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월) 로 값 의미가 아래와 같이 변경**<br>N : KRX정규장종가<br>X : NXT<br>Y : KRX+NXT 통합시세<br>※ 종전 `Y : 시간외단일가` 의미는 시간외단일가 폐지와 함께 사라진다 |
| 3 | `OFL_YN` | 오프라인여부 | string | N | 1 | 공란(Default) |
| 4 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 01 : 대출일별 |
| 5 | `UNPR_DVSN` | 단가구분 | string | Y | 2 | 01 : 기본값 |
| 6 | `FUND_STTL_ICLD_YN` | 펀드결제분포함여부 | string | Y | 1 | N : 포함하지 않음<br>Y :  포함 |
| 7 | `FNCG_AMT_AUTO_RDPT_YN` | 융자금액자동상환여부 | string | Y | 1 | N : 기본값 |
| 8 | `PRCS_DVSN` | 처리구분 | string | Y | 2 | 00 :  전일매매포함<br>01 : 전일매매미포함 |
| 9 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | N | 100 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK100 값 : 다음페이지 조회시(2번째부터) |
| 10 | `CTX_AREA_NK100` | 연속조회키100 | string | N | 100 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK100 값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (57)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk100` | 연속조회검색조건100 | string | Y | 100 |  |
| 4 | `ctx_area_nk100` | 연속조회키100 | string | Y | 100 |  |
| 5 | `output1` | 응답상세1 | object array | Y |  | Array |
| 6 | `pdno` | 상품번호 | string | Y | 12 | 종목번호(뒷 6자리) |
| 7 | `prdt_name` | 상품명 | string | Y | 60 | 종목명 |
| 8 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 | 매수매도구분 |
| 9 | `bfdy_buy_qty` | 전일매수수량 | string | Y | 10 |  |
| 10 | `bfdy_sll_qty` | 전일매도수량 | string | Y | 10 |  |
| 11 | `thdt_buyqty` | 금일매수수량 | string | Y | 10 |  |
| 12 | `thdt_sll_qty` | 금일매도수량 | string | Y | 10 |  |
| 13 | `hldg_qty` | 보유수량 | string | Y | 19 |  |
| 14 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 |  |
| 15 | `pchs_avg_pric` | 매입평균가격 | string | Y | 22 | 매입금액 / 보유수량 |
| 16 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 17 | `prpr` | 현재가 | string | Y | 19 |  |
| 18 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 19 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 | 평가금액 - 매입금액 |
| 20 | `evlu_pfls_rt` | 평가손익율 | string | Y | 9 |  |
| 21 | `evlu_erng_rt` | 평가수익율 | string | Y | 31 | 미사용항목(0으로 출력) |
| 22 | `loan_dt` | 대출일자 | string | Y | 8 | INQR_DVSN(조회구분)을 01(대출일별)로 설정해야 값이 나옴 |
| 23 | `loan_amt` | 대출금액 | string | Y | 19 |  |
| 24 | `stln_slng_chgs` | 대주매각대금 | string | Y | 19 |  |
| 25 | `expd_dt` | 만기일자 | string | Y | 8 |  |
| 26 | `fltt_rt` | 등락율 | string | Y | 31 |  |
| 27 | `bfdy_cprs_icdc` | 전일대비증감 | string | Y | 19 |  |
| 28 | `item_mgna_rt_name` | 종목증거금율명 | string | Y | 20 |  |
| 29 | `grta_rt_name` | 보증금율명 | string | Y | 20 |  |
| 30 | `sbst_pric` | 대용가격 | string | Y | 19 | 증권매매의 위탁보증금으로서 현금 대신에 사용되는 유가증권 가격 |
| 31 | `stck_loan_unpr` | 주식대출단가 | string | Y | 22 |  |
| 32 | `output2` | 응답상세2 | object array | Y |  | Array |
| 33 | `dnca_tot_amt` | 예수금총금액 | string | Y | 19 | 예수금 |
| 34 | `nxdy_excc_amt` | 익일정산금액 | string | Y | 19 | D+1 예수금 |
| 35 | `prvs_rcdl_excc_amt` | 가수도정산금액 | string | Y | 19 | D+2 예수금 |
| 36 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 37 | `bfdy_buy_amt` | 전일매수금액 | string | Y | 19 |  |
| 38 | `thdt_buy_amt` | 금일매수금액 | string | Y | 19 |  |
| 39 | `nxdy_auto_rdpt_amt` | 익일자동상환금액 | string | Y | 19 |  |
| 40 | `bfdy_sll_amt` | 전일매도금액 | string | Y | 19 |  |
| 41 | `thdt_sll_amt` | 금일매도금액 | string | Y | 19 |  |
| 42 | `d2_auto_rdpt_amt` | D+2자동상환금액 | string | Y | 19 |  |
| 43 | `bfdy_tlex_amt` | 전일제비용금액 | string | Y | 19 |  |
| 44 | `thdt_tlex_amt` | 금일제비용금액 | string | Y | 19 |  |
| 45 | `tot_loan_amt` | 총대출금액 | string | Y | 19 |  |
| 46 | `scts_evlu_amt` | 유가평가금액 | string | Y | 19 |  |
| 47 | `tot_evlu_amt` | 총평가금액 | string | Y | 19 | 유가증권 평가금액 합계금액 + D+2 예수금 |
| 48 | `nass_amt` | 순자산금액 | string | Y | 19 |  |
| 49 | `fncg_gld_auto_rdpt_yn` | 융자금자동상환여부 | string | Y | 1 | 보유현금에 대한 융자금만 차감여부<br>신용융자 매수체결 시점에서는 융자비율을 매매대금 100%로 계산 하였다가 수도결제일에 보증금에 해당하는 금액을 고객의 현금으로 충당하여 융자금을 감소시키는 업무 |
| 50 | `pchs_amt_smtl_amt` | 매입금액합계금액 | string | Y | 19 |  |
| 51 | `evlu_amt_smtl_amt` | 평가금액합계금액 | string | Y | 19 | 유가증권 평가금액 합계금액 |
| 52 | `evlu_pfls_smtl_amt` | 평가손익합계금액 | string | Y | 19 |  |
| 53 | `tot_stln_slng_chgs` | 총대주매각대금 | string | Y | 19 |  |
| 54 | `bfdy_tot_asst_evlu_amt` | 전일총자산평가금액 | string | Y | 19 |  |
| 55 | `asst_icdc_amt` | 자산증감액 | string | Y | 19 |  |
| 56 | `asst_icdc_erng_rt` | 자산증감수익율 | string | Y | 31 | 데이터 미제공 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"AFHR_FLPR_YN": "N",
	"OFL_YN": "",
	"INQR_DVSN": "01",
	"UNPR_DVSN": "01",
	"FUND_STTL_ICLD_YN": "N",
	"FNCG_AMT_AUTO_RDPT_YN": "N",
	"PRCS_DVSN": "01",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk100": "81055689^01^N^N^01^01^N^                                                                            ",
  "ctx_area_nk100": "                                                                                                    ",
  "output1": [
    {
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "trad_dvsn_name": "현금",
      "bfdy_buy_qty": "12",
      "bfdy_sll_qty": "0",
      "thdt_buyqty": "1686",
      "thdt_sll_qty": "41",
      "hldg_qty": "1657",
      "ord_psbl_qty": "1611",
      "pchs_avg_pric": "135440.2517",
      "pchs_amt": "224424497",
      "prpr": "0",
      "evlu_amt": "0",
      "evlu_pfls_amt": "0",
      "evlu_pfls_rt": "0.00",
      "evlu_erng_rt": "0.00000000",
      "loan_dt": "",
      "loan_amt": "0",
      "stln_slng_chgs": "0",
      "expd_dt": "",
      "fltt_rt": "-100.00000000",
      "bfdy_cprs_icdc": "-184500",
      "item_mgna_rt_name": "",
      "grta_rt_name": "",
      "sbst_pric": "140220",
      "stck_loan_unpr": "0.0000"
    },
    {
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "trad_dvsn_name": "자기융자",
      "bfdy_buy_qty": "3",
      "bfdy_sll_qty": "0",
      "thdt_buyqty": "0",
      "thdt_sll_qty": "0",
      "hldg_qty": "3",
      "ord_psbl_qty": "3",
      "pchs_avg_pric": "123000.0000",
      "pchs_amt": "369000",
      "prpr": "0",
      "evlu_amt": "0",
      "evlu_pfls_amt": "0",
      "evlu_pfls_rt": "0.00",
      "evlu_erng_rt": "0.00000000",
      "loan_dt": "20211223",
      "loan_amt": "369000",
      "stln_slng_chgs": "0",
      "expd_dt": "",
      "fltt_rt": "-100.00000000",
      "bfdy_cprs_icdc": "-184500",
      "item_mgna_rt_name": "",
      "grta_rt_name": "",
      "sbst_pric": "140220",
      "stck_loan_unpr": "123000.0000"
    }
	  ],
  "output2": [
        {
            "dnca_tot_amt": "346455",
            "nxdy_excc_amt": "346455",
            "prvs_rcdl_excc_amt": "346455",
            "cma_evlu_amt": "0",
            "bfdy_buy_amt": "0",
            "thdt_buy_amt": "0",
            "nxdy_auto_rdpt_amt": "0",
            "bfdy_sll_amt": "0",
            "thdt_sll_amt": "0",
            "d2_auto_rdpt_amt": "0",
            "bfdy_tlex_amt": "0",
            "thdt_tlex_amt": "0",
            "tot_loan_amt": "0",
            "scts_evlu_amt": "1759600",
            "tot_evlu_amt": "2106055",
            "nass_amt": "2106055",
            "fncg_gld_auto_rdpt_yn": "",
            "pchs_amt_smtl_amt": "2516522",
            "evlu_amt_smtl_amt": "1759600",
            "evlu_pfls_smtl_amt": "-756922",
            "tot_stln_slng_chgs": "0",
            "bfdy_tot_asst_evlu_amt": "2142945",
            "asst_icdc_amt": "-36890",
            "asst_icdc_erng_rt": "0.00000000"
        }
    ],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 퇴직연금 체결기준잔고

- **API ID**: v1_국내주식-032
- **실전 TR_ID**: TTTC2202R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-present-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
​※ 55번 계좌(DC가입자계좌)의 경우 해당 API 이용이 불가합니다.
KIS Developers API의 경우 HTS ID에 반드시 연결되어있어야만 API 신청 및 앱정보 발급이 가능한 서비스로 개발되어서 실물계좌가 아닌 55번 계좌는 API 이용이 불가능한 점 양해 부탁드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC2202R |
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
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 29 |
| 2 | `USER_DVSN_CD` | 사용자구분코드 | string | Y | 2 | 00 |
| 3 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 |  |
| 4 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 |  |
| 5 | `PRCS_DVSN_CD` | 처리구분코드 | string | N | 2 | 00 : 보유 주식 전체 조회<br>01 : 보유 주식 중 0주 주식 숨김 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (24)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세1 | object array | Y |  | Array |
| 4 | `cblc_dvsn` | 잔고구분 | string | Y | 2 |  |
| 5 | `cblc_dvsn_name` | 잔고구분명 | string | Y | 60 |  |
| 6 | `pdno` | 상품번호 | string | Y | 12 |  |
| 7 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 8 | `hldg_qty` | 보유수량 | string | Y | 19 |  |
| 9 | `slpsb_qty` | 매도가능수량 | string | Y | 10 |  |
| 10 | `pchs_avg_pric` | 매입평균가격 | string | Y | 184 |  |
| 11 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 12 | `evlu_pfls_rt` | 평가손익율 | string | Y | 72 |  |
| 13 | `prpr` | 현재가 | string | Y | 19 |  |
| 14 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 15 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 16 | `cblc_weit` | 잔고비중 | string | Y | 238 |  |
| 17 | `output2` | 응답상세2 | object array | Y |  | Array |
| 18 | `pchs_amt_smtl_amt` | 매입금액합계금액 | string | Y | 19 |  |
| 19 | `evlu_amt_smtl_amt` | 평가금액합계금액 | string | Y | 19 |  |
| 20 | `evlu_pfls_smtl_amt` | 평가손익합계금액 | string | Y | 19 |  |
| 21 | `trad_pfls_smtl` | 매매손익합계 | string | Y | 19 |  |
| 22 | `thdt_tot_pfls_amt` | 당일총손익금액 | string | Y | 19 |  |
| 23 | `pftrt` | 수익률 | string | Y | 238 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"63512345",
	"ACNT_PRDT_CD":"29",
	"USER_DVSN_CD":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "63512345^29^00^                                                                                     ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "cblc_dvsn": "01",
            "cblc_dvsn_name": "사용자",
            "pdno": "069500",
            "prdt_name": "KODEX 200",
            "hldg_qty": "6",
            "slpsb_qty": "6",
            "pchs_avg_pric": "35670.0000",
            "evlu_pfls_amt": "-3330",
            "evlu_pfls_rt": "-1.56",
            "prpr": "35115",
            "evlu_amt": "210690",
            "pchs_amt": "214020",
            "cblc_weit": "53.06651890"
        },
        {
            "cblc_dvsn": "01",
            "cblc_dvsn_name": "사용자",
            "pdno": "091160",
            "prdt_name": "KODEX 반도체",
            "hldg_qty": "7",
            "slpsb_qty": "7",
            "pchs_avg_pric": "35820.0000",
            "evlu_pfls_amt": "-64400",
            "evlu_pfls_rt": "-25.68",
            "prpr": "26620",
            "evlu_amt": "186340",
            "pchs_amt": "250740",
            "cblc_weit": "46.93348110"
        }
    ],
    "output2": [
        {
            "pchs_amt_smtl_amt": "464760",
            "evlu_amt_smtl_amt": "397030",
            "evlu_pfls_smtl_amt": "-67730",
            "trad_pfls_smtl": "0",
            "thdt_tot_pfls_amt": "-67730",
            "pftrt": "-14.57311300"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 매수가능조회

- **API ID**: v1_국내주식-007
- **실전 TR_ID**: TTTC8908R
- **모의 TR_ID**: VTTC8908R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
매수가능 조회 API입니다. 
실전계좌/모의계좌의 경우, 한 번의 호출에 최대 1건까지 확인 가능합니다.


1) 매수가능금액 확인
 . 미수 사용 X: nrcvb_buy_amt(미수없는매수금액) 확인
 . 미수 사용 O: max_buy_amt(최대매수금액) 확인


2) 매수가능수량 확인
 . 특정 종목 전량매수 시 가능수량을 확인하실 경우 ORD_DVSN:00(지정가)는 종목증거금율이 반영되지 않습니다. 
   따라서 "반드시" ORD_DVSN:01(시장가)로 지정하여 종목증거금율이 반영된 가능수량을 확인하시기 바랍니다. 

   (다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력하여 가능수량 확인)

 . 미수 사용 X: ORD_DVSN:01(시장가) or 특정 주문구분(ex.IOC)로 지정하여 nrcvb_buy_qty(미수없는매수수량) 확인
 . 미수 사용 O: ORD_DVSN:01(시장가) or 특정 주문구분(ex.IOC)로 지정하여 max_buy_qty(최대매수수량) 확인
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTC8908R : 매수 가능 조회<br>[모의투자]<br>VTTC8908R : 매수 가능 조회 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 상품번호 | string | Y | 12 | 종목번호(6자리)<br>* PDNO, ORD_UNPR 공란 입력 시, 매수수량 없이 매수금액만 조회됨 |
| 3 | `ORD_UNPR` | 주문단가 | string | Y | 19 | 1주당 가격<br>* 시장가(ORD_DVSN:01)로 조회 시, 공란으로 입력<br>* PDNO, ORD_UNPR 공란 입력 시, 매수수량 없이 매수금액만 조회됨 |
| 4 | `ORD_DVSN` | 주문구분 | string | Y | 2 | * 특정 종목 전량매수 시 가능수량을 확인할 경우<br>    00:지정가는 증거금율이 반영되지 않으므로<br>    증거금율이 반영되는 01: 시장가로 조회<br>* 다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력하여 가능수량 확인<br>* 종목별 매수가능수량 조회 없이 매수금액만 조회하고자 할 경우 임의값(00) 입력<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>08 : 자기주식<br>09 : 자기주식S-Option<br>10 : 자기주식금전신탁<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>51 : 장중대량<br>52 : 장중바스켓<br>62 : 장개시전 시간외대량<br>63 : 장개시전 시간외바스켓<br>67 : 장개시전 금전신탁자사주<br>69 : 장개시전 자기주식<br>72 : 시간외대량<br>77 : 시간외자사주신탁<br>79 : 시간외대량자기주식<br>80 : 바스켓 |
| 5 | `CMA_EVLU_AMT_ICLD_YN` | CMA평가금액포함여부 | string | Y | 1 | Y : 포함<br>N : 포함하지 않음 |
| 6 | `OVRS_ICLD_YN` | 해외포함여부 | string | Y | 1 | Y : 포함<br>N : 포함하지 않음 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (16)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | object | Y |  | Single |
| 4 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 | 예수금으로 계산된 주문가능금액 |
| 5 | `ord_psbl_sbst` | 주문가능대용 | string | Y | 19 |  |
| 6 | `ruse_psbl_amt` | 재사용가능금액 | string | Y | 19 | 전일/금일 매도대금으로 계산된 주문가능금액 |
| 7 | `fund_rpch_chgs` | 펀드환매대금 | string | Y | 19 |  |
| 8 | `psbl_qty_calc_unpr` | 가능수량계산단가 | string | Y | 19 |  |
| 9 | `nrcvb_buy_amt` | 미수없는매수금액 | string | Y | 19 | 미수를 사용하지 않으실 경우 nrcvb_buy_amt(미수없는매수금액)을 확인 |
| 10 | `nrcvb_buy_qty` | 미수없는매수수량 | string | Y | 10 | 미수를 사용하지 않으실 경우 nrcvb_buy_qty(미수없는매수수량)을 확인<br>* 특정 종목 전량매수 시 가능수량을 확인하실 경우<br>  조회 시 ORD_DVSN:01(시장가)로 지정 필수<br>* 다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력 |
| 11 | `max_buy_amt` | 최대매수금액 | string | Y | 19 | 미수를 사용하시는 경우 max_buy_amt(최대매수금액)를 확인 |
| 12 | `max_buy_qty` | 최대매수수량 | string | Y | 10 | 미수를 사용하시는 경우 max_buy_qty(최대매수수량)를 확인<br>* 특정 종목 전량매수 시 가능수량을 확인하실 경우<br>  조회 시 ORD_DVSN:01(시장가)로 지정 필수<br>* 다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력 |
| 13 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 14 | `ovrs_re_use_amt_wcrc` | 해외재사용금액원화 | string | Y | 19 |  |
| 15 | `ord_psbl_frcr_amt_wcrc` | 주문가능외화금액원화 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"PDNO": "005930",
	"ORD_UNPR": "0",
	"ORD_DVSN": "01",
	"CMA_EVLU_AMT_ICLD_YN": "N",
	"OVRS_ICLD_YN": "N"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output": {
    "ord_psbl_cash": "741191178",
    "ord_psbl_sbst": "0",
    "ruse_psbl_amt": "0",
    "fund_rpch_chgs": "0",
    "psbl_qty_calc_unpr": "70000",
    "nrcvb_buy_amt": "107177377",
    "nrcvb_buy_qty": "1531",
    "max_buy_amt": "1482382356",
    "max_buy_qty": "21176",
    "cma_evlu_amt": "0",
    "ovrs_re_use_amt_wcrc": "0",
    "ord_psbl_frcr_amt_wcrc": "1468797045293"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 기간별손익일별합산조회

- **API ID**: v1_국내주식-052
- **실전 TR_ID**: TTTC8708R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-period-profit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
기간별손익일별합산조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0856] 기간별 매매손익 화면 에서 "일별" 클릭 시의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC8708R |
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
| 0 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 1 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 2 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 |  |
| 3 | `PDNO` | 상품번호 | string | Y | 12 | ""공란입력 시, 전체 |
| 4 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 |  |
| 5 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 |  |
| 6 | `SORT_DVSN` | 정렬구분 | string | Y | 2 | 00: 최근 순, 01: 과거 순, 02: 최근 순 |
| 7 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 00 입력 |
| 8 | `CBLC_DVSN` | 잔고구분 | string | Y | 2 | 00: 전체 |
| 9 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (32)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `trad_dt` | 매매일자 | string | Y | 8 |  |
| 5 | `buy_amt` | 매수금액 | string | Y | 19 |  |
| 6 | `sll_amt` | 매도금액 | string | Y | 19 |  |
| 7 | `rlzt_pfls` | 실현손익 | string | Y | 19 |  |
| 8 | `fee` | 수수료 | string | Y | 19 |  |
| 9 | `loan_int` | 대출이자 | string | Y | 19 |  |
| 10 | `tl_tax` | 제세금 | string | Y | 19 |  |
| 11 | `pfls_rt` | 손익률 | string | Y | 238 |  |
| 12 | `sll_qty1` | 매도수량1 | string | Y | 19 |  |
| 13 | `buy_qty1` | 매수수량1 | string | Y | 9 |  |
| 14 | `output2` | 응답상세2 | object | Y |  |  |
| 15 | `sll_qty_smtl` | 매도수량합계 | string | Y | 19 |  |
| 16 | `sll_tr_amt_smtl` | 매도거래금액합계 | string | Y | 19 |  |
| 17 | `sll_fee_smtl` | 매도수수료합계 | string | Y | 19 |  |
| 18 | `sll_tltx_smtl` | 매도제세금합계 | string | Y | 19 |  |
| 19 | `sll_excc_amt_smtl` | 매도정산금액합계 | string | Y | 19 |  |
| 20 | `buy_qty_smtl` | 매수수량합계 | string | Y | 19 |  |
| 21 | `buy_tr_amt_smtl` | 매수거래금액합계 | string | Y | 19 |  |
| 22 | `buy_fee_smtl` | 매수수수료합계 | string | Y | 19 |  |
| 23 | `buy_tax_smtl` | 매수제세금합계 | string | Y | 19 |  |
| 24 | `buy_excc_amt_smtl` | 매수정산금액합계 | string | Y | 19 |  |
| 25 | `tot_qty` | 총수량 | string | Y | 10 |  |
| 26 | `tot_tr_amt` | 총거래금액 | string | Y | 19 |  |
| 27 | `tot_fee` | 총수수료 | string | Y | 19 |  |
| 28 | `tot_tltx` | 총제세금 | string | Y | 19 |  |
| 29 | `tot_excc_amt` | 총정산금액 | string | Y | 19 |  |
| 30 | `tot_rlzt_pfls` | 총실현손익 | string | Y | 19 | ※ HTS[0856] 기간별 매매손익 '일별' 화면의 우측 하단 '총손익률' 항목은 <br>기간별매매손익현황조회(TTTC8715R) > output2 > tot_pftrt(총수익률) 으로 확인 가능 |
| 31 | `loan_int` | 대출이자 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"PDNO":"",
"INQR_STRT_DT":"20230101",
"INQR_END_DT":"20240220",
"SORT_DVSN":"00",
"INQR_DVSN":"00",
"CBLC_DVSN":"00",
"CTX_AREA_FK100":"",
"CTX_AREA_NK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "                                                                                                    ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "trad_dt": "20240220",
            "buy_amt": "116697331",
            "sll_amt": "96455",
            "rlzt_pfls": "22991",
            "fee": "0",
            "loan_int": "0",
            "tl_tax": "0",
            "pfls_rt": "31.29560057",
            "sll_qty1": "8",
            "buy_qty1": "2003"
        }
    ],
    "output2": {
        "sll_qty_smtl": "8",
        "sll_tr_amt_smtl": "96455",
        "sll_fee_smtl": "0",
        "sll_tltx_smtl": "0",
        "sll_excc_amt_smtl": "96455",
        "buy_qty_smtl": "2003",
        "buy_tr_amt_smtl": "116697331",
        "buy_fee_smtl": "0",
        "buy_tax_smtl": "0",
        "buy_excc_amt_smtl": "116697331",
        "tot_qty": "2011",
        "tot_tr_amt": "116793786",
        "tot_fee": "0",
        "tot_tltx": "0",
        "tot_excc_amt": "116793786",
        "tot_rlzt_pfls": "22991",
        "loan_int": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식주문(현금)

- **API ID**: v1_국내주식-001
- **실전 TR_ID**: (매도) TTTC0011U (매수) TTTC0012U
- **모의 TR_ID**: (매도) VTTC0011U (매수) VTTC0012U
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-cash`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
국내주식주문(현금) API 입니다. 

※ TTC0012U(현금매수) 사용하셔서 미수매수 가능합니다. 단, 거래하시는 계좌가 증거금40%계좌로 신청이 되어있어야 가능합니다. 
※ 신용매수는 별도의 API가 준비되어 있습니다.

※ ORD_QTY(주문수량), ORD_UNPR(주문단가) 등을 String으로 전달해야 함에 유의 부탁드립니다.

※ ORD_UNPR(주문단가)가 없는 주문은 상한가로 주문금액을 선정하고 이후 체결이되면 체결금액로 정산됩니다.

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
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | '※ 구TR은 사전고지 없이 막힐 수 있으므로 반드시 신TR로 변경이용 부탁드립니다.<br>[실전투자]<br>국내주식주문 매도 : (구)TTTC0801U → (신)TTTC0011U<br>국내주식주문 매도(모의투자) : (구)VTTC0801U → (신)VTTC0011U<br>국내주식주문 매수 : (구)TTTC0802U → (신)TTTC0012U<br>국내주식주문 매수(모의투자) : (구)VTTC0802U → (신)VTTC0012U' |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (9)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 종합계좌번호 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 상품유형코드 |
| 2 | `PDNO` | 상품번호 | string | Y | 12 | 종목코드(6자리) , ETN의 경우 7자리 입력 |
| 3 | `SLL_TYPE` | 매도유형 (매도주문 시) | string | N | 2 | 01@일반매도<br>02@임의매매<br>05@대차매도<br>→ 미입력시 01 일반매도로 진행 |
| 4 | `ORD_DVSN` | 주문구분 | string | Y | 2 | [KRX]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[NXT]<br>00 : 지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[SOR]<br>00 : 지정가<br>01 : 시장가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br><br>**▼ 아래는 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월) 반영분**<br>[KRX 애프터마켓] 16:00~20:00 · KRX 정규장과 **분리된 시장**이라 호가유형 선택 **필수** · **ETP(ETF/ETN) 거래 불가**<br>41 : KRX애프터마켓지정가<br>42 : KRX애프터마켓지정가IOC<br>43 : KRX애프터마켓지정가FOK<br>44 : KRX애프터마켓최유리지정가<br>45 : KRX애프터마켓최유리지정가IOC<br>46 : KRX애프터마켓최유리지정가FOK<br>47 : KRX애프터마켓최우선지정가<br>[NXT 프리마켓 GTP] Good Till Pre-Market — 미체결잔량은 **프리마켓 종료(08:50) 일괄 취소**<br>27 : NXT GTP지정가<br>28 : NXT GTP최유리<br>29 : NXT GTP최우선<br>※ 같은 공지로 **시간외단일가가 폐지**되므로 위 `07 : 시간외 단일가` 는 2026-09-14 부터 무효다<br>※ 애프터마켓에 **시장가(`01`)는 없다** — 지정가 계열 7종만 접수된다 |
| 5 | `ORD_QTY` | 주문수량 | string | Y | 10 | 주문수량 |
| 6 | `ORD_UNPR` | 주문단가 | string | Y | 19 | 주문단가<br>시장가 등 주문시, "0"으로 입력 |
| 7 | `CNDT_PRIC` | 조건가격 | string | N | 19 | 스탑지정가호가 주문 (ORD_DVSN이 22) 사용 시에만 필수 |
| 8 | `EXCG_ID_DVSN_CD` | 거래소ID구분코드 | string | N | 3 | 한국거래소 : KRX<br>대체거래소 (넥스트레이드) : NXT<br>SOR (Smart Order Routing) : SOR<br>→ 미입력시 KRX로 진행되며, 모의투자는 KRX만 가능 |

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
| 3 | `output` | 응답상세 | object array | Y |  | single |
| 4 | `KRX_FWDG_ORD_ORGNO` | 계좌관리점코드 | string | Y | 5 |  |
| 5 | `ODNO` | 주문번호 | string | Y | 10 |  |
| 6 | `ORD_TMD` | 주문시간 | string | Y | 6 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD": "01",
	"PDNO": "009150",
	"ORD_DVSN": "00",
	"ORD_QTY": "3",
	"ORD_UNPR": "150000"
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
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569157",
    "ORD_TMD": "155211"
  }
}
```

</details>



### 매도가능수량조회

- **API ID**: 국내주식-165
- **실전 TR_ID**: TTTC8408R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-sell`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
매도가능수량조회 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0971] 주식 매도 화면에서 종목코드 입력 후 "가능" 클릭 시 매도가능수량이 확인되는 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

특정종목 매도가능수량 확인 시, 매도주문 내시려는 주문종목(PDNO)으로 API 호출 후 
output &gt; ord_psbl_qty(주문가능수량) 확인하실 수 있습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC8408R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 종합계좌번호 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌상품코드 |
| 2 | `PDNO` | 종목번호 | string | Y | 12 | 보유종목 코드 ex)000660 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (17)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `pdno` | 상품번호 | string | Y | 12 |  |
| 5 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 6 | `buy_qty` | 매수수량 | string | Y | 10 |  |
| 7 | `sll_qty` | 매도수량 | string | Y | 10 |  |
| 8 | `cblc_qty` | 잔고수량 | string | Y | 19 |  |
| 9 | `nsvg_qty` | 비저축수량 | string | Y | 19 |  |
| 10 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 |  |
| 11 | `pchs_avg_pric` | 매입평균가격 | string | Y | 184 |  |
| 12 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 13 | `now_pric` | 현재가 | string | Y | 8 |  |
| 14 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 15 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 16 | `evlu_pfls_rt` | 평가손익율 | string | Y | 72 |  |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:01
PDNO:005930
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "pdno": "005930",
        "prdt_name": "삼성전자",
        "buy_qty": "1746",
        "sll_qty": "2",
        "cblc_qty": "1744",
        "nsvg_qty": "0",
        "ord_psbl_qty": "1744",
        "pchs_avg_pric": "54388.4874",
        "pchs_amt": "0",
        "now_pric": "75800",
        "evlu_amt": "132195200",
        "evlu_pfls_amt": "37341678",
        "evlu_pfls_rt": "39.36"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0420",
    "msg1": "정상적으로 조회되었습니다                                                       "
}
```

</details>



### 주식일별주문체결조회

- **API ID**: v1_국내주식-005
- **실전 TR_ID**: (3개월이내) TTTC0081R (3개월이전) CTSC9215R
- **모의 TR_ID**: (3개월이내) VTTC0081R (3개월이전) VTSC9215R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-daily-ccld`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
주식일별주문체결조회 API입니다. 
실전계좌의 경우, 한 번의 호출에 최대 100건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 
모의계좌의 경우, 한 번의 호출에 최대 15건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 

* 다만, 3개월 이전 체결내역 조회(CTSC9115R, CTSC9215R) 의 경우, 
장중에는 많은 거래량으로 인해 순간적으로 DB가 밀렸거나 응답을 늦게 받거나 하는 등의 이슈가 있을 수 있어
① 가급적 장 종료 이후(15:30 이후) 조회하시고 
② 조회기간(INQR_STRT_DT와 INQR_END_DT 사이의 간격)을 보다 짧게 해서 조회하는 것을
권유드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | ※ 구TR은 사전고지 없이 막힐 수 있으므로 반드시 신TR로 변경이용 부탁드립니다.<br>[실전투자]<br>3개월이내 (구)TTTC8001R → (신)TTTC0081R <br>3개월이전 (구)CTSC9115R → (신)CTSC9215R<br>[모의투자]<br>3개월이내 (구)VTTC8001R → (신)VTTC0081R <br>3개월이전 (구)VTSC9115R → (신)VTSC9215R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 | YYYYMMDD |
| 3 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 | YYYYMMDD |
| 4 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 00 : 전체 / 01 : 매도 / 02 : 매수 |
| 5 | `PDNO` | 상품번호 | string | N | 12 | 종목번호(6자리) |
| 6 | `ORD_GNO_BRNO` | 주문채번지점번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 7 | `ODNO` | 주문번호 | string | N | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 8 | `CCLD_DVSN` | 체결구분 | string | Y | 2 | '00 전체<br>01 체결<br>02 미체결' |
| 9 | `INQR_DVSN` | 조회구분 | string | Y | 2 | '00 역순<br>01 정순' |
| 10 | `INQR_DVSN_1` | 조회구분1 | string | Y | 1 | '없음: 전체<br>1: ELW<br>2: 프리보드' |
| 11 | `INQR_DVSN_3` | 조회구분3 | string | Y | 2 | '00 전체<br>01 현금<br>02 신용<br>03 담보<br>04 대주<br>05 대여<br>06 자기융자신규/상환<br>07 유통융자신규/상환' |
| 12 | `EXCG_ID_DVSN_CD` | 거래소ID구분코드 | string | Y | 3 | 한국거래소 : KRX<br>대체거래소 (NXT) : NXT<br>SOR (Smart Order Routing) : SOR<br>ALL : 전체<br>※ 모의투자는 KRX만 제공 |
| 13 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | '공란 : 최초 조회시는 <br>이전 조회 Output CTX_AREA_FK100 값 : 다음페이지 조회시(2번째부터)' |
| 14 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | '공란 : 최초 조회시 <br>이전 조회 Output CTX_AREA_NK100 값 : 다음페이지 조회시(2번째부터)' |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (46)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `ord_dt` | 주문일자 | string | Y | 8 |  |
| 5 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 |  |
| 6 | `odno` | 주문번호 | string | Y | 10 |  |
| 7 | `orgn_odno` | 원주문번호 | string | Y | 10 |  |
| 8 | `ord_dvsn_name` | 주문구분명 | string | Y | 60 |  |
| 9 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 |  |
| 10 | `sll_buy_dvsn_cd_name` | 매도매수구분코드명 | string | Y | 60 |  |
| 11 | `pdno` | 상품번호 | string | Y | 12 |  |
| 12 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 13 | `ord_qty` | 주문수량 | string | Y | 10 |  |
| 14 | `ord_unpr` | 주문단가 | string | Y | 19 |  |
| 15 | `ord_tmd` | 주문시각 | string | Y | 6 |  |
| 16 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 |  |
| 17 | `avg_prvs` | 평균가 | string | Y | 19 |  |
| 18 | `cncl_yn` | 취소여부 | string | Y | 1 |  |
| 19 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 |  |
| 20 | `loan_dt` | 대출일자 | string | Y | 8 |  |
| 21 | `ordr_empno` | 주문자사번 | string | Y | 60 |  |
| 22 | `ord_dvsn_cd` | 주문구분코드 | string | Y | 2 |  |
| 23 | `cncl_cfrm_qty` | 취소확인수량 | string | Y | 10 |  |
| 24 | `rmn_qty` | 잔여수량 | string | Y | 10 |  |
| 25 | `rjct_qty` | 거부수량 | string | Y | 10 |  |
| 26 | `ccld_cndt_name` | 체결조건명 | string | Y | 10 |  |
| 27 | `inqr_ip_addr` | 조회IP주소 | string | Y | 15 |  |
| 28 | `cpbc_ordp_ord_rcit_dvsn_cd` | 전산주문표주문접수구분코드 | string | Y | 2 |  |
| 29 | `cpbc_ordp_infm_mthd_dvsn_cd` | 전산주문표통보방법구분코드 | string | Y | 2 |  |
| 30 | `infm_tmd` | 통보시각 | string | Y | 6 |  |
| 31 | `ctac_tlno` | 연락전화번호 | string | Y | 20 |  |
| 32 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 33 | `excg_dvsn_cd` | 거래소구분코드 | string | Y | 2 |  |
| 34 | `cpbc_ordp_mtrl_dvsn_cd` | 전산주문표자료구분코드 | string | Y | 2 |  |
| 35 | `ord_orgno` | 주문조직번호 | string | Y | 5 |  |
| 36 | `rsvn_ord_end_dt` | 예약주문종료일자 | string | Y | 8 |  |
| 37 | `excg_id_dvsn_Cd` | 거래소ID구분코드 | string | Y | 3 |  |
| 38 | `stpm_cndt_pric` | 스톱지정가조건가격 | string | Y | 9 |  |
| 39 | `stpm_efct_occr_dtmd` | 스톱지정가효력발생상세시각 | string | Y | 9 |  |
| 40 | `output2` | 응답상세 | object | Y |  | single |
| 41 | `tot_ord_qty` | 총주문수량 | string | Y | 10 |  |
| 42 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 |  |
| 43 | `tot_ccld_amt` | 매입평균가격 | string | Y | 19 |  |
| 44 | `prsm_tlex_smtl` | 총체결금액 | string | Y | 19 |  |
| 45 | `pchs_avg_pric` | 추정제비용합계 | string | Y | 184 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "12345678",
	"ACNT_PRDT_CD": "01",
	"INQR_STRT_DT": "20211101",
	"INQR_END_DT": "20211101",
	"SLL_BUY_DVSN_CD": "00",
	"INQR_DVSN": "00",
	"PDNO": "",
	"CCLD_DVSN": "00",
	"ORD_GNO_BRNO": "",
	"ODNO": "",
	"INQR_DVSN_3": "00",
	"INQR_DVSN_1": "",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk100": "12345678^01^20220103^20220103^ ^00^00^                                                              ",
  "ctx_area_nk100": "                                                                                                    ",
  "output1": [
    {
      "ord_dt": "20220103",
      "ord_gno_brno": "06010",
      "odno": "0001568197",
      "orgn_odno": "",
      "ord_dvsn_name": "Limit",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "BUY REJECT",
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "ord_qty": "10",
      "ord_unpr": "150000",
      "ord_tmd": "170100",
      "tot_ccld_qty": "0",
      "avg_prvs": "0",
      "cncl_yn": "",
      "tot_ccld_amt": "0",
      "loan_dt": "",
      "ordr_empno": "Nsmart",
      "ord_dvsn_cd": "00",
      "cncl_cfrm_qty": "0",
      "rmn_qty": "0",
      "rjct_qty": "10",
      "ccld_cndt_name": "None",
      "inqr_ip_addr": "...",
      "cpbc_ordp_ord_rcit_dvsn_cd": "",
      "cpbc_ordp_infm_mthd_dvsn_cd": "",
      "infm_tmd": "",
      "ctac_tlno": "01047859775",
      "prdt_type_cd": "300",
      "excg_dvsn_cd": "02",
      "cpbc_ordp_mtrl_dvsn_cd": "11",
      "ord_orgno": "00000",
      "rsvn_ord_end_dt": ""
    },
    {
      "ord_dt": "20220103",
      "ord_gno_brno": "06010",
      "odno": "0001568196",
      "orgn_odno": "",
      "ord_dvsn_name": "Limit",
      "sll_buy_dvsn_cd": "02",
      "sll_buy_dvsn_cd_name": "BUY REJECT",
      "pdno": "009150",
      "prdt_name": "삼성전기",
      "ord_qty": "10",
      "ord_unpr": "150000",
      "ord_tmd": "170038",
      "tot_ccld_qty": "0",
      "avg_prvs": "0",
      "cncl_yn": "",
      "tot_ccld_amt": "0",
      "loan_dt": "",
      "ordr_empno": "Nsmart",
      "ord_dvsn_cd": "00",
      "cncl_cfrm_qty": "0",
      "rmn_qty": "0",
      "rjct_qty": "10",
      "ccld_cndt_name": "None",
      "inqr_ip_addr": "P01.012.345.678",
      "cpbc_ordp_ord_rcit_dvsn_cd": "",
      "cpbc_ordp_infm_mthd_dvsn_cd": "",
      "infm_tmd": "",
      "ctac_tlno": "01047859775",
      "prdt_type_cd": "300",
      "excg_dvsn_cd": "02",
      "cpbc_ordp_mtrl_dvsn_cd": "11",
      "ord_orgno": "00000",
      "rsvn_ord_end_dt": ""
	}
		],
  "output2": {
    "tot_ord_qty": "281",
    "tot_ccld_qty": "0",
    "tot_ccld_amt": "0",
    "prsm_tlex_smtl": "0",
    "pchs_avg_pric": "0.0000"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식정정취소가능주문조회

- **API ID**: v1_국내주식-004
- **실전 TR_ID**: TTTC0084R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
주식정정취소가능주문조회 API입니다. 한 번의 호출에 최대 50건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다.

※ 주식주문(정정취소) 호출 전에 반드시 주식정정취소가능주문조회 호출을 통해 정정취소가능수량(output &gt; psbl_qty)을 확인하신 후 정정취소주문 내시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | ※ 구TR은 사전고지 없이 막힐 수 있으므로 반드시 신TR로 변경이용 부탁드립니다.<br>[실전투자]<br>(구)TTTC8036R → (신)TTTC0084R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | '공란 : 최초 조회시는 <br>이전 조회 Output CTX_AREA_FK100 값 : 다음페이지 조회시(2번째부터)' |
| 3 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | '공란 : 최초 조회시 <br>이전 조회 Output CTX_AREA_NK100 값 : 다음페이지 조회시(2번째부터)' |
| 4 | `INQR_DVSN_1` | 조회구분1 | string | Y | 1 | '0 주문<br>1 종목' |
| 5 | `INQR_DVSN_2` | 조회구분2 | string | Y | 1 | '0 전체<br>1 매도<br>2 매수' |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 | 주문시 한국투자증권 시스템에서 지정된 영업점코드 |
| 5 | `odno` | 주문번호 | string | Y | 10 | 주문시 한국투자증권 시스템에서 채번된 주문번호 |
| 6 | `orgn_odno` | 원주문번호 | string | Y | 6 | 정정/취소주문 인경우 원주문번호 |
| 7 | `ord_dvsn_name` | 주문구분명 | string | Y | 5 |  |
| 8 | `pdno` | 상품번호 | string | Y | 10 | 종목번호(뒤 6자리만 해당) |
| 9 | `prdt_name` | 상품명 | string | Y | 6 | 종목명 |
| 10 | `rvse_cncl_dvsn_name` | 정정취소구분명 | string | Y | 5 | 정정 또는 취소 여부 표시 |
| 11 | `ord_qty` | 주문수량 | string | Y | 10 |  |
| 12 | `ord_unpr` | 주문단가 | string | Y | 6 | 1주당 주문가격 |
| 13 | `ord_tmd` | 주문시각 | string | Y | 5 | 주문시각(시분초HHMMSS) |
| 14 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 | 주문 수량 중 체결된 수량 |
| 15 | `tot_ccld_amt` | 총체결금액 | string | Y | 6 | 주문금액 중 체결금액 |
| 16 | `psbl_qty` | 가능수량 | string | Y | 5 | 정정/취소 주문 가능 수량 |
| 17 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 10 | 01 : 매도 / 02 : 매수 |
| 18 | `ord_dvsn_cd` | 주문구분코드 | string | Y | 6 | [KRX]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[NXT]<br>00 : 지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[SOR]<br>00 : 지정가<br>01 : 시장가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소) |
| 19 | `mgco_aptm_odno` | 운용사지정주문번호 | string | Y | 5 |  |
| 20 | `excg_dvsn_cd` | 거래소구분코드 | string | Y | 2 |  |
| 21 | `excg_id_dvsn_cd` | 거래소ID구분코드 | string | Y | 3 |  |
| 22 | `excg_id_dvsn_name` | 거래소ID구분명 | string | Y | 100 |  |
| 23 | `stpm_cndt_pric` | 스톱지정가조건가격 | string | Y | 9 |  |
| 24 | `stpm_efct_occr_yn` | 스톱지정가효력발생여부 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"ACNT_PRDT_CD": "01",
	"CANO": "810XXXXX",
	"CTX_AREA_FK100": "",
	"CTX_AREA_NK100": "",
	"INQR_DVSN_1": "0",
	"INQR_DVSN_2": "0"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk100": "81055689^01^                                                                                        ",
  "ctx_area_nk100": "                                                                                                    ",
  "output": [
    {
      "ord_gno_brno": "06010",
      "odno": "0001569139",
      "orgn_odno": "0001569136",
      "ord_dvsn_name": "지정가",
      "pdno": "009150",
      "prdt_name": "SamsungElecMech",
      "rvse_cncl_dvsn_name": "BUY AMEND*",
      "ord_qty": "1",
      "ord_unpr": "140000",
      "ord_tmd": "131438",
      "tot_ccld_qty": "0",
      "tot_ccld_amt": "0",
      "psbl_qty": "1",
      "sll_buy_dvsn_cd": "02",
      "ord_dvsn_cd": "00",
      "mgco_aptm_odno": ""
    },
    {
      "ord_gno_brno": "06010",
      "odno": "0001569138",
      "orgn_odno": "",
      "ord_dvsn_name": "지정가",
      "pdno": "009150",
      "prdt_name": "SamsungElecMech",
      "rvse_cncl_dvsn_name": "",
      "ord_qty": "1",
      "ord_unpr": "200000",
      "ord_tmd": "131421",
      "tot_ccld_qty": "0",
      "tot_ccld_amt": "0",
      "psbl_qty": "1",
      "sll_buy_dvsn_cd": "02",
      "ord_dvsn_cd": "00",
      "mgco_aptm_odno": ""
    }
	],
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식예약주문

- **API ID**: v1_국내주식-017
- **실전 TR_ID**: CTSC0008U
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-resv`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 예약주문 매수/매도 API 입니다.

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)

※ 유의사항
 1. 예약주문 가능시간 : 15시 40분 ~ 다음 영업일 7시 30분 
    (단, 서버 초기화 작업 시 예약주문 불가 : 23시 40분 ~ 00시 10분)
    ※ 예약주문 처리내역은 통보되지 않으므로 주문처리일 장 시작전에 반드시 주문처리 결과를 확인하시기 바랍니다.

 2. 예약주문 안내
   - 예약종료일 미입력 시 일반예약주문으로 최초 도래하는 영업일에 주문 전송됩니다.
   - 예약종료일 입력 시 기간예약주문으로 최초 예약주문수량 중 미체결 된 수량에 대해 예약종료일까지 매 영업일 주문이
      실행됩니다. (예약종료일은 익영업일부터 달력일 기준으로 공휴일 포함하여 최대 30일이 되는 일자까지 입력가능)
   - 예약주문 접수 처리순서는 일반/기간예약주문 중 신청일자가 빠른 주문이 우선합니다.
      단, 기간예약주문 자동배치시간(약 15시35분 ~ 15시55분)사이 접수되는 주문의 경우 당일에 한해 순서와 상관없이
      처리될 수 있습니다.
   - 기간예약주문 자동배치시간(약 15시35분 ~ 15시55분)에는 예약주문 조회가 제한 될 수 있습니다.
   - 기간예약주문은 계좌 당 주문건수 최대 1,000건으로 제한됩니다.

3. 예약주문 접수내역 중 아래의 사유 등으로 인해 주문이 거부될 수 있사오니, 주문처리일 장 시작전에 반드시
    주문처리 결과를 확인하시기 바랍니다.
    * 주문처리일 기준 : 매수가능금액 부족, 매도가능수량 부족, 주문수량/호가단위 오류, 대주 호가제한, 
                              신용/대주가능종목 변경, 상/하한폭 변경, 시가형성 종목(신규상장 등)의 시장가, 거래서비스 미신청 등

 4. 익일 예상 상/하한가는 조회시점의 현재가로 계산되며 익일의 유/무상증자, 배당, 감자, 합병, 액면변경 등에 의해
    변동될 수 있으며 이로 인해 상/하한가를 벗어나 주문이 거부되는 경우가 발생할 수 있사오니, 주문처리일 장 시작전에
    반드시 주문처리결과를 확인하시기 바랍니다.

 5. 정리매매종목, ELW, 신주인수권증권, 신주인수권증서 등은 가격제한폭(상/하한가) 적용 제외됩니다.

 6. 영업일 장 시작 후 [기간예약주문] 내역 취소는 해당시점 이후의 예약주문이 취소되는 것으로, 
    일반주문으로 이미 전환된 주문에는 영향을 미치지 않습니다. 반드시 장 시작전 주문처리결과를 확인하시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>CTSC0008U : 국내예약매수입력/주문예약매도입력 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
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
| 2 | `PDNO` | 종목코드(6자리) | string | Y | 12 |  |
| 3 | `ORD_QTY` | 주문수량 | string | Y | 10 | 주문주식수 |
| 4 | `ORD_UNPR` | 주문단가 | string | Y | 19 | 1주당 가격 <br>* 장전 시간외, 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 권고 |
| 5 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 01 : 매도<br>02 : 매수 |
| 6 | `ORD_DVSN_CD` | 주문구분코드 | string | Y | 2 | 00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>05 : 장전 시간외 |
| 7 | `ORD_OBJT_CBLC_DVSN_CD` | 주문대상잔고구분코드 | string | Y | 2 | [매도매수구분코드 01:매도/02:매수시 사용]<br>10 : 현금 <br>[매도매수구분코드 01:매도시 사용]<br>12 : 주식담보대출 <br>14 : 대여상환<br>21 : 자기융자신규<br>22 : 유통대주신규<br>23 : 유통융자신규<br>24 : 자기대주신규<br>25 : 자기융자상환<br>26 : 유통대주상환<br>27 : 유통융자상환<br>28 : 자기대주상환 |
| 8 | `LOAN_DT` | 대출일자 | string | N | 8 |  |
| 9 | `RSVN_ORD_END_DT` | 예약주문종료일자 | string | N | 8 | (YYYYMMDD) 현재 일자보다 이후로 설정해야 함<br>* RSVN_ORD_END_DT(예약주문종료일자)를 안 넣으면 다음날 주문처리되고 예약주문은 종료됨<br>* RSVN_ORD_END_DT(예약주문종료일자)는 익영업일부터 달력일 기준으로 공휴일 포함하여 최대 30일이 되는 일자까지 입력 가능 |
| 10 | `LDNG_DT` | 대여일자 | string | N | 8 |  |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | Array |
| 4 | `rsvn_ord_seq` | 예약주문 순번 | string | N | 10 |  |

<details><summary>Request Example (Python)</summary>

```json
{ 
	"CANO": "810XXXXX", 
	"ACNT_PRDT_CD": "01", 
	"PDNO": "009150", 
	"ORD_QTY": "10", 
	"ORD_UNPR": "160000", 
	"SLL_BUY_DVSN_CD":"02", 
	"ORD_DVSN_CD":"00", 
	"ORD_OBJT_CBLC_DVSN_CD":"10", 
	"LOAN_DT":"", 
	"RSVN_ORD_END_DT":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{ 
	"rt_cd": "0", 
	"msg_cd": "APBK2938", 
	"msg1": "예약주문이 접수되었습니다.", 
	"output": { 
		"RSVN_ORD_SEQ": "39607" 
	} 
}
```

</details>



### 주식주문(신용)

- **API ID**: v1_국내주식-002
- **실전 TR_ID**: (매도) TTTC0051U (매수) TTTC0052U
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-stock/v1/trading/order-credit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식주문(신용) API입니다. 
※ 모의투자는 사용 불가합니다.

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | '※ 구TR은 사전고지 없이 막힐 수 있으므로 반드시 신TR로 변경이용 부탁드립니다.<br>[실전투자]<br>매도 : (구)TTTC0851U → (신)TTTC0051U<br>매수 : (구)TTTC0852U → (신)TTTC0052U<br>' |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (24)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 상품번호 | string | Y | 5 | 종목코드(6자리) |
| 3 | `SLL_TYPE` | 매도유형 | string | N | 10 | 공란 입력 |
| 4 | `CRDT_TYPE` | 신용유형 | string | Y | 2 | [매도] 22 : 유통대주신규, 24 : 자기대주신규, 25 : 자기융자상환, 27 : 유통융자상환<br>[매수] 21 : 자기융자신규, 23 : 유통융자신규 , 26 : 유통대주상환, 28 : 자기대주상환 |
| 5 | `LOAN_DT` | 대출일자 | string | Y | 2 | [신용매수] <br>신규 대출로, 오늘날짜(yyyyMMdd)) 입력 <br>[신용매도] <br>매도할 종목의 대출일자(yyyyMMdd)) 입력 |
| 6 | `ORD_DVSN` | 주문구분 | string | Y | 8 | [KRX]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[NXT]<br>00 : 지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[SOR]<br>00 : 지정가<br>01 : 시장가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br><br>**▼ 아래는 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월) 반영분**<br>[KRX 애프터마켓] 16:00~20:00 · KRX 정규장과 **분리된 시장**이라 호가유형 선택 **필수** · **ETP(ETF/ETN) 거래 불가**<br>41 : KRX애프터마켓지정가<br>42 : KRX애프터마켓지정가IOC<br>43 : KRX애프터마켓지정가FOK<br>44 : KRX애프터마켓최유리지정가<br>45 : KRX애프터마켓최유리지정가IOC<br>46 : KRX애프터마켓최유리지정가FOK<br>47 : KRX애프터마켓최우선지정가<br>[NXT 프리마켓 GTP] Good Till Pre-Market — 미체결잔량은 **프리마켓 종료(08:50) 일괄 취소**<br>27 : NXT GTP지정가<br>28 : NXT GTP최유리<br>29 : NXT GTP최우선<br>※ 같은 공지로 **시간외단일가가 폐지**되므로 위 `07 : 시간외 단일가` 는 2026-09-14 부터 무효다<br>※ 애프터마켓에 **시장가(`01`)는 없다** — 지정가 계열 7종만 접수된다 |
| 7 | `ORD_QTY` | 주문수량 | string | Y | 2 |  |
| 8 | `ORD_UNPR` | 주문단가 | string | Y | 5 | 1주당 가격 <br>* 장전 시간외, 장후 시간외, 시장가의 경우 1주당 가격을 공란으로 비우지 않음 "0"으로 입력 권고 |
| 9 | `RSVN_ORD_YN` | 예약주문여부 | string | N | 2 | 정규 증권시장이 열리지 않는 시간 (15:10분 ~ 익일 7:30분) 에 주문을 미리 설정 하여 다음 영업일 또는 설정한 기간 동안 아침 동시 호가에 주문하는 것 <br>Y : 예약주문 <br>N : 신용주문 |
| 10 | `EMGC_ORD_YN` | 비상주문여부 | string | N | 2 |  |
| 11 | `PGTR_DVSN` | 프로그램매매구분 | string | N | 10 |  |
| 12 | `MGCO_APTM_ODNO` | 운용사지정주문번호 | string | N | 19 |  |
| 13 | `LQTY_TR_NGTN_DTL_NO` | 대량거래협상상세번호 | string | N | 1 |  |
| 14 | `LQTY_TR_AGMT_NO` | 대량거래협정번호 | string | N | 20 |  |
| 15 | `LQTY_TR_NGTN_ID` | 대량거래협상자Id | string | N | 19 |  |
| 16 | `LP_ORD_YN` | LP주문여부 | string | N | 3 |  |
| 17 | `MDIA_ODNO` | 매체주문번호 | string | N | 10 |  |
| 18 | `ORD_SVR_DVSN_CD` | 주문서버구분코드 | string | N | 19 |  |
| 19 | `PGM_NMPR_STMT_DVSN_CD` | 프로그램호가신고구분코드 | string | N | 1 |  |
| 20 | `CVRG_SLCT_RSON_CD` | 반대매매선정사유코드 | string | N | 20 |  |
| 21 | `CVRG_SEQ` | 반대매매순번 | string | N | 19 |  |
| 22 | `EXCG_ID_DVSN_CD` | 거래소ID구분코드 | string | N | 3 | 한국거래소 : KRX<br>대체거래소 (넥스트레이드) : NXT<br>SOR (Smart Order Routing) : SOR<br>→ 미입력시 KRX로 진행되며, 모의투자는 KRX만 가능 |
| 23 | `CNDT_PRIC` | 조건가격 | string | N | 19 | 스탑지정가호가에서 사용 |

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
| 3 | `output` | 응답상세 | object | Y |  | single |
| 4 | `krx_fwdg_ord_orgno` | 한국거래소전송주문조직번호 | string | Y | 5 |  |
| 5 | `odno` | 주문번호 | string | Y | 10 |  |
| 6 | `ord_tmd` | 주문시간 | string | Y | 6 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "CANO": "810XXXXX",
    "ACNT_PRDT_CD": "01",
    "PDNO": "009150",
    "CRDT_TYPE": "21",
    "LOAN_DT": "20211103",
    "ORD_DVSN": "00",
    "ORD_QTY": "1",
    "ORD_UNPR": "130000",
    "RSVN_ORD_YN": "N"
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
    "KRX_FWDG_ORD_ORGNO": "06010",
    "ODNO": "0001569138",
    "ORD_TMD": "131421"
  }
}
```

</details>



### 퇴직연금 잔고조회

- **API ID**: v1_국내주식-036
- **실전 TR_ID**: TTTC2208R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/pension/inquire-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
주식, ETF, ETN만 조회 가능하며 펀드는 조회 불가합니다.

​※ 55번 계좌(DC가입자계좌)의 경우 해당 API 이용이 불가합니다.
KIS Developers API의 경우 HTS ID에 반드시 연결되어있어야만 API 신청 및 앱정보 발급이 가능한 서비스로 개발되어서 실물계좌가 아닌 55번 계좌는 API 이용이 불가능한 점 양해 부탁드립니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC2208R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 |  |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 29 |
| 2 | `ACCA_DVSN_CD` | 적립금구분코드 | string | Y | 2 | 00 |
| 3 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 00 : 전체 |
| 4 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 |  |
| 5 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 |  |

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
| 3 | `output1` | 응답상세 | object array | Y |  | Array |
| 4 | `cblc_dvsn_name` | 잔고구분명 | string | Y | 60 |  |
| 5 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 6 | `pdno` | 상품번호 | string | Y | 12 |  |
| 7 | `item_dvsn_name` | 종목구분명 | string | Y | 60 |  |
| 8 | `thdt_buyqty` | 금일매수수량 | string | Y | 10 |  |
| 9 | `thdt_sll_qty` | 금일매도수량 | string | Y | 10 |  |
| 10 | `hldg_qty` | 보유수량 | string | Y | 19 |  |
| 11 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 |  |
| 12 | `pchs_avg_pric` | 매입평균가격 | string | Y | 184 |  |
| 13 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 14 | `prpr` | 현재가 | string | Y | 19 |  |
| 15 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 16 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 17 | `evlu_erng_rt` | 평가수익율 | string | Y | 238 |  |
| 18 | `output2` | 응답상세2 | object | Y |  |  |
| 19 | `dnca_tot_amt` | 예수금총금액 | string | Y | 19 |  |
| 20 | `nxdy_excc_amt` | 익일정산금액 | string | Y | 19 |  |
| 21 | `prvs_rcdl_excc_amt` | 가수도정산금액 | string | Y | 19 |  |
| 22 | `thdt_buy_amt` | 금일매수금액 | string | Y | 19 |  |
| 23 | `thdt_sll_amt` | 금일매도금액 | string | Y | 19 |  |
| 24 | `thdt_tlex_amt` | 금일제비용금액 | string | Y | 19 |  |
| 25 | `scts_evlu_amt` | 유가평가금액 | string | Y | 19 |  |
| 26 | `tot_evlu_amt` | 총평가금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"29",
	"ACCA_DVSN_CD":"00",
	"INQR_DVSN":"00",
	"CTX_AREA_FK100":"",
	"CTX_AREA_NK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "12345678^29^00^00^                                                                                  ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "cblc_dvsn_name": "사용자",
            "prdt_name": "ACE 미국S&P500",
            "pdno": "360200",
            "item_dvsn_name": "현금",
            "thdt_buyqty": "5",
            "thdt_sll_qty": "0",
            "hldg_qty": "5",
            "ord_psbl_qty": "5",
            "pchs_avg_pric": "13235.0000",
            "pchs_amt": "66175",
            "prpr": "13235",
            "evlu_amt": "66175",
            "evlu_pfls_amt": "0",
            "evlu_erng_rt": "0.00000000"
        }
    ],
    "output2": {
        "dnca_tot_amt": "100000",
        "nxdy_excc_amt": "100000",
        "prvs_rcdl_excc_amt": "33825",
        "thdt_buy_amt": "66175",
        "thdt_sll_amt": "0",
        "thdt_tlex_amt": "0",
        "scts_evlu_amt": "66175",
        "tot_evlu_amt": "100000"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 주식잔고조회_실현손익

- **API ID**: v1_국내주식-041
- **실전 TR_ID**: TTTC8494R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/trading/inquire-balance-rlz-pl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
주식잔고조회_실현손익 API입니다.
한국투자 HTS(eFriend Plus) [0800] 국내 체결기준잔고 화면을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
(참고: 포럼 - 공지사항 - 신규 API 추가 안내(주식잔고조회_실현손익 외 1건))
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTC8494R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `AFHR_FLPR_YN` | 시간외단일가여부 | string | Y | 1 | 'N : 기본값 <br>Y : 시간외단일가'<br><br>**▼ 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월) 로 값 의미가 아래와 같이 변경**<br>N : KRX정규장종가<br>X : NXT<br>Y : KRX+NXT 통합시세<br>※ 종전 `Y : 시간외단일가` 의미는 시간외단일가 폐지와 함께 사라진다 |
| 3 | `OFL_YN` | 오프라인여부 | string | Y | 1 | 공란 |
| 4 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 00 : 전체 |
| 5 | `UNPR_DVSN` | 단가구분 | string | Y | 2 | 01 : 기본값 |
| 6 | `FUND_STTL_ICLD_YN` | 펀드결제포함여부 | string | Y | 1 | N : 포함하지 않음 <br>Y : 포함 |
| 7 | `FNCG_AMT_AUTO_RDPT_YN` | 융자금액자동상환여부 | string | Y | 1 | N : 기본값 |
| 8 | `PRCS_DVSN` | PRCS_DVSN | string | Y | 2 | 00 : 전일매매포함 <br>01 : 전일매매미포함 |
| 9 | `COST_ICLD_YN` | 비용포함여부 | string | Y | 1 |  |
| 10 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | 공란 : 최초 조회시 <br>이전 조회 Output CTX_AREA_FK100 값 : 다음페이지 조회시(2번째부터) |
| 11 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | 공란 : 최초 조회시 <br>이전 조회 Output CTX_AREA_NK100 값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (56)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | Array |
| 4 | `pdno` | 상품번호 | string | Y | 12 | 종목번호(뒷 6자리) |
| 5 | `prdt_name` | 상품명 | string | Y | 60 | 종목명 |
| 6 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 | 매수매도구분 |
| 7 | `bfdy_buy_qty` | 전일매수수량 | string | Y | 10 |  |
| 8 | `bfdy_sll_qty` | 전일매도수량 | string | Y | 10 |  |
| 9 | `thdt_buyqty` | 금일매수수량 | string | Y | 10 |  |
| 10 | `thdt_sll_qty` | 금일매도수량 | string | Y | 10 |  |
| 11 | `hldg_qty` | 보유수량 | string | Y | 19 |  |
| 12 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 |  |
| 13 | `pchs_avg_pric` | 매입평균가격 | string | Y | 23 | 매입금액 / 보유수량 |
| 14 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 15 | `prpr` | 현재가 | string | Y | 19 |  |
| 16 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 17 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 | 평가금액 - 매입금액 |
| 18 | `evlu_pfls_rt` | 평가손익율 | string | Y | 10 |  |
| 19 | `evlu_erng_rt` | 평가수익율 | string | Y | 32 |  |
| 20 | `loan_dt` | 대출일자 | string | Y | 8 |  |
| 21 | `loan_amt` | 대출금액 | string | Y | 19 |  |
| 22 | `stln_slng_chgs` | 대주매각대금 | string | Y | 19 | 신용 거래에서, 고객이 증권 회사로부터 대부받은 주식의 매각 대금 |
| 23 | `expd_dt` | 만기일자 | string | Y | 8 |  |
| 24 | `stck_loan_unpr` | 주식대출단가 | string | Y | 23 |  |
| 25 | `bfdy_cprs_icdc` | 전일대비증감 | string | Y | 19 |  |
| 26 | `fltt_rt` | 등락율 | string | Y | 32 |  |
| 27 | `output2` | 응답상세2 | object array | Y |  | Array |
| 28 | `dnca_tot_amt` | 예수금총금액 | string | Y | 19 |  |
| 29 | `nxdy_excc_amt` | 익일정산금액 | string | Y | 19 |  |
| 30 | `prvs_rcdl_excc_amt` | 가수도정산금액 | string | Y | 19 |  |
| 31 | `cma_evlu_amt` | CMA평가금액 | string | Y | 19 |  |
| 32 | `bfdy_buy_amt` | 전일매수금액 | string | Y | 19 |  |
| 33 | `thdt_buy_amt` | 금일매수금액 | string | Y | 19 |  |
| 34 | `nxdy_auto_rdpt_amt` | 익일자동상환금액 | string | Y | 19 |  |
| 35 | `bfdy_sll_amt` | 전일매도금액 | string | Y | 19 |  |
| 36 | `thdt_sll_amt` | 금일매도금액 | string | Y | 19 |  |
| 37 | `d2_auto_rdpt_amt` | D+2자동상환금액 | string | Y | 19 |  |
| 38 | `bfdy_tlex_amt` | 전일제비용금액 | string | Y | 19 |  |
| 39 | `thdt_tlex_amt` | 금일제비용금액 | string | Y | 19 |  |
| 40 | `tot_loan_amt` | 총대출금액 | string | Y | 19 |  |
| 41 | `scts_evlu_amt` | 유가평가금액 | string | Y | 19 |  |
| 42 | `tot_evlu_amt` | 총평가금액 | string | Y | 19 |  |
| 43 | `nass_amt` | 순자산금액 | string | Y | 19 |  |
| 44 | `fncg_gld_auto_rdpt_yn` | 융자금자동상환여부 | string | Y | 1 |  |
| 45 | `pchs_amt_smtl_amt` | 매입금액합계금액 | string | Y | 19 |  |
| 46 | `evlu_amt_smtl_amt` | 평가금액합계금액 | string | Y | 19 |  |
| 47 | `evlu_pfls_smtl_amt` | 평가손익합계금액 | string | Y | 19 |  |
| 48 | `tot_stln_slng_chgs` | 총대주매각대금 | string | Y | 19 |  |
| 49 | `bfdy_tot_asst_evlu_amt` | 전일총자산평가금액 | string | Y | 19 |  |
| 50 | `asst_icdc_amt` | 자산증감액 | string | Y | 19 |  |
| 51 | `asst_icdc_erng_rt` | 자산증감수익율 | string | Y | 32 |  |
| 52 | `rlzt_pfls` | 실현손익 | string | Y | 19 |  |
| 53 | `rlzt_erng_rt` | 실현수익율 | string | Y | 32 |  |
| 54 | `real_evlu_pfls` | 실평가손익 | string | Y | 19 |  |
| 55 | `real_evlu_pfls_erng_rt` | 실평가손익수익율 | string | Y | 32 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"CANO":"12345678",
"ACNT_PRDT_CD":"01",
"AFHR_FLPR_YN":"N",
"OFL_YN":"",
"INQR_DVSN":"02",
"UNPR_DVSN":"01",
"FUND_STTL_ICLD_YN":"N",
"FNCG_AMT_AUTO_RDPT_YN":"N",
"PRCS_DVSN":"01",
"COST_ICLD_YN":"N",
"CTX_AREA_FK100":"",
"CTX_AREA_NK100":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "12345678^01^N^N^02^01^N^                                                                            ",
    "ctx_area_nk100": "N^00000A900270^300^00000000^00^                                                                     ",
    "output1": [
        {
            "pdno": "000080",
            "prdt_name": "하이트진로",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "22975.0000",
            "pchs_amt": "45950",
            "prpr": "22600",
            "evlu_amt": "45200",
            "evlu_pfls_amt": "-750",
            "evlu_pfls_rt": "-1.63",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000100",
            "prdt_name": "유한양행",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "64800.0000",
            "pchs_amt": "129600",
            "prpr": "67600",
            "evlu_amt": "135200",
            "evlu_pfls_amt": "5600",
            "evlu_pfls_rt": "4.32",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "2900",
            "fltt_rt": "4.48222566"
        },
        {
            "pdno": "000120",
            "prdt_name": "CJ대한통운",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "116800.0000",
            "pchs_amt": "1168000",
            "prpr": "129500",
            "evlu_amt": "1295000",
            "evlu_pfls_amt": "127000",
            "evlu_pfls_rt": "10.87",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "500",
            "fltt_rt": "0.38759690"
        },
        {
            "pdno": "000210",
            "prdt_name": "DL",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "50400.0000",
            "pchs_amt": "504000",
            "prpr": "45800",
            "evlu_amt": "458000",
            "evlu_pfls_amt": "-46000",
            "evlu_pfls_rt": "-9.12",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-5500",
            "fltt_rt": "-10.72124756"
        },
        {
            "pdno": "000240",
            "prdt_name": "한국앤컴퍼니",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "23850.0000",
            "pchs_amt": "47700",
            "prpr": "17450",
            "evlu_amt": "34900",
            "evlu_pfls_amt": "-12800",
            "evlu_pfls_rt": "-26.83",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000270",
            "prdt_name": "기아",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "84500.0000",
            "pchs_amt": "845000",
            "prpr": "89500",
            "evlu_amt": "895000",
            "evlu_pfls_amt": "50000",
            "evlu_pfls_rt": "5.91",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-35300",
            "fltt_rt": "-28.28525641"
        },
        {
            "pdno": "000660",
            "prdt_name": "SK하이닉스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "12",
            "ord_psbl_qty": "12",
            "pchs_avg_pric": "122583.3333",
            "pchs_amt": "1471000",
            "prpr": "161700",
            "evlu_amt": "1940400",
            "evlu_pfls_amt": "469400",
            "evlu_pfls_rt": "31.91",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1700",
            "fltt_rt": "1.06250000"
        },
        {
            "pdno": "000670",
            "prdt_name": "영풍",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "4",
            "thdt_sll_qty": "0",
            "hldg_qty": "4",
            "ord_psbl_qty": "4",
            "pchs_avg_pric": "640750.0000",
            "pchs_amt": "2563000",
            "prpr": "525000",
            "evlu_amt": "2100000",
            "evlu_pfls_amt": "-463000",
            "evlu_pfls_rt": "-18.06",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "000990",
            "prdt_name": "DB하이텍",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "23000.0000",
            "pchs_amt": "46000",
            "prpr": "49600",
            "evlu_amt": "99200",
            "evlu_pfls_amt": "53200",
            "evlu_pfls_rt": "115.65",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "001120",
            "prdt_name": "LX인터내셔널",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "34050.0000",
            "pchs_amt": "34050",
            "prpr": "28950",
            "evlu_amt": "28950",
            "evlu_pfls_amt": "-5100",
            "evlu_pfls_rt": "-14.97",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "002380",
            "prdt_name": "KCC",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "252000.0000",
            "pchs_amt": "252000",
            "prpr": "250000",
            "evlu_amt": "250000",
            "evlu_pfls_amt": "-2000",
            "evlu_pfls_rt": "-0.79",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "003550",
            "prdt_name": "LG",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "105600.0000",
            "pchs_amt": "211200",
            "prpr": "85000",
            "evlu_amt": "170000",
            "evlu_pfls_amt": "-41200",
            "evlu_pfls_rt": "-19.50",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-16200",
            "fltt_rt": "-16.00790514"
        },
        {
            "pdno": "003670",
            "prdt_name": "포스코퓨처엠",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "531000.0000",
            "pchs_amt": "1062000",
            "prpr": "296000",
            "evlu_amt": "592000",
            "evlu_pfls_amt": "-470000",
            "evlu_pfls_rt": "-44.25",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "004800",
            "prdt_name": "효성",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "66400.0000",
            "pchs_amt": "132800",
            "prpr": "64700",
            "evlu_amt": "129400",
            "evlu_pfls_amt": "-3400",
            "evlu_pfls_rt": "-2.56",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "005380",
            "prdt_name": "현대차",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "240500.0000",
            "pchs_amt": "481000",
            "prpr": "244000",
            "evlu_amt": "488000",
            "evlu_pfls_amt": "7000",
            "evlu_pfls_rt": "1.45",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "22000",
            "fltt_rt": "9.90990991"
        },
        {
            "pdno": "005490",
            "prdt_name": "POSCO홀딩스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "133500.0000",
            "pchs_amt": "1335000",
            "prpr": "421500",
            "evlu_amt": "4215000",
            "evlu_pfls_amt": "2880000",
            "evlu_pfls_rt": "215.73",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "1417",
            "thdt_sll_qty": "2",
            "hldg_qty": "1415",
            "ord_psbl_qty": "1415",
            "pchs_avg_pric": "53397.8247",
            "pchs_amt": "75557922",
            "prpr": "73900",
            "evlu_amt": "104568500",
            "evlu_pfls_amt": "29010578",
            "evlu_pfls_rt": "38.39",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-400",
            "fltt_rt": "-0.53835801"
        },
        {
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "trad_dvsn_name": "자기융자",
            "bfdy_buy_qty": "1",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "0",
            "thdt_sll_qty": "0",
            "hldg_qty": "1",
            "ord_psbl_qty": "1",
            "pchs_avg_pric": "45100.0000",
            "pchs_amt": "45100",
            "prpr": "73900",
            "evlu_amt": "73900",
            "evlu_pfls_amt": "28800",
            "evlu_pfls_rt": "63.85",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "45100",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "45100.0000",
            "bfdy_cprs_icdc": "-400",
            "fltt_rt": "-0.53835801"
        },
        {
            "pdno": "005940",
            "prdt_name": "NH투자증권",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "11710.0000",
            "pchs_amt": "117100",
            "prpr": "10650",
            "evlu_amt": "106500",
            "evlu_pfls_amt": "-10600",
            "evlu_pfls_rt": "-9.05",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "006260",
            "prdt_name": "LS",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "122000.0000",
            "pchs_amt": "1220000",
            "prpr": "96600",
            "evlu_amt": "966000",
            "evlu_pfls_amt": "-254000",
            "evlu_pfls_rt": "-20.81",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "008770",
            "prdt_name": "호텔신라",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "99850.0000",
            "pchs_amt": "199700",
            "prpr": "59300",
            "evlu_amt": "118600",
            "evlu_pfls_amt": "-81100",
            "evlu_pfls_rt": "-40.61",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "-2100",
            "fltt_rt": "-3.42019544"
        },
        {
            "pdno": "009540",
            "prdt_name": "HD한국조선해양",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "170000.0000",
            "pchs_amt": "1700000",
            "prpr": "126000",
            "evlu_amt": "1260000",
            "evlu_pfls_amt": "-440000",
            "evlu_pfls_rt": "-25.88",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1000",
            "fltt_rt": "0.80000000"
        },
        {
            "pdno": "011780",
            "prdt_name": "금호석유",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "200000.0000",
            "pchs_amt": "2000000",
            "prpr": "151900",
            "evlu_amt": "1519000",
            "evlu_pfls_amt": "-481000",
            "evlu_pfls_rt": "-24.05",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "011790",
            "prdt_name": "SKC",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "49950.0000",
            "pchs_amt": "499500",
            "prpr": "92100",
            "evlu_amt": "921000",
            "evlu_pfls_amt": "421500",
            "evlu_pfls_rt": "84.38",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "015760",
            "prdt_name": "한국전력",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "4",
            "thdt_sll_qty": "0",
            "hldg_qty": "4",
            "ord_psbl_qty": "4",
            "pchs_avg_pric": "8030.0000",
            "pchs_amt": "32120",
            "prpr": "23000",
            "evlu_amt": "92000",
            "evlu_pfls_amt": "59880",
            "evlu_pfls_rt": "186.42",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "017670",
            "prdt_name": "SK텔레콤",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "50100.0000",
            "pchs_amt": "501000",
            "prpr": "53200",
            "evlu_amt": "532000",
            "evlu_pfls_amt": "31000",
            "evlu_pfls_rt": "6.18",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "018260",
            "prdt_name": "삼성에스디에스",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "250000.0000",
            "pchs_amt": "500000",
            "prpr": "174000",
            "evlu_amt": "348000",
            "evlu_pfls_amt": "-152000",
            "evlu_pfls_rt": "-30.40",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "3200",
            "fltt_rt": "1.87353630"
        },
        {
            "pdno": "028260",
            "prdt_name": "삼성물산",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "5",
            "thdt_sll_qty": "0",
            "hldg_qty": "5",
            "ord_psbl_qty": "5",
            "pchs_avg_pric": "156100.0000",
            "pchs_amt": "780500",
            "prpr": "128000",
            "evlu_amt": "640000",
            "evlu_pfls_amt": "-140500",
            "evlu_pfls_rt": "-18.00",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "028670",
            "prdt_name": "팬오션",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "4865.0000",
            "pchs_amt": "9730",
            "prpr": "5000",
            "evlu_amt": "10000",
            "evlu_pfls_amt": "270",
            "evlu_pfls_rt": "2.77",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "385",
            "fltt_rt": "8.34236186"
        },
        {
            "pdno": "030200",
            "prdt_name": "KT",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "26050.0000",
            "pchs_amt": "260500",
            "prpr": "40650",
            "evlu_amt": "406500",
            "evlu_pfls_amt": "146000",
            "evlu_pfls_rt": "56.04",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "034730",
            "prdt_name": "SK",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "182700.0000",
            "pchs_amt": "1827000",
            "prpr": "207000",
            "evlu_amt": "2070000",
            "evlu_pfls_amt": "243000",
            "evlu_pfls_rt": "13.30",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "035250",
            "prdt_name": "강원랜드",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "20950.0000",
            "pchs_amt": "209500",
            "prpr": "19000",
            "evlu_amt": "190000",
            "evlu_pfls_amt": "-19500",
            "evlu_pfls_rt": "-9.30",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "1230",
            "fltt_rt": "6.92177828"
        },
        {
            "pdno": "035420",
            "prdt_name": "NAVER",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "356000.0000",
            "pchs_amt": "3560000",
            "prpr": "270000",
            "evlu_amt": "2700000",
            "evlu_pfls_amt": "-860000",
            "evlu_pfls_rt": "-24.15",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "61000",
            "fltt_rt": "29.18660287"
        },
        {
            "pdno": "035760",
            "prdt_name": "CJ ENM",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "11",
            "thdt_sll_qty": "0",
            "hldg_qty": "11",
            "ord_psbl_qty": "11",
            "pchs_avg_pric": "58836.3636",
            "pchs_amt": "647199",
            "prpr": "82200",
            "evlu_amt": "904200",
            "evlu_pfls_amt": "257000",
            "evlu_pfls_rt": "39.70",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "036460",
            "prdt_name": "한국가스공사",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "27850.0000",
            "pchs_amt": "55700",
            "prpr": "30400",
            "evlu_amt": "60800",
            "evlu_pfls_amt": "5100",
            "evlu_pfls_rt": "9.15",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "047050",
            "prdt_name": "포스코인터내셔널",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "74400.0000",
            "pchs_amt": "148800",
            "prpr": "58400",
            "evlu_amt": "116800",
            "evlu_pfls_amt": "-32000",
            "evlu_pfls_rt": "-21.50",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "057050",
            "prdt_name": "현대홈쇼핑",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "30100.0000",
            "pchs_amt": "60200",
            "prpr": "46850",
            "evlu_amt": "93700",
            "evlu_pfls_amt": "33500",
            "evlu_pfls_rt": "55.64",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "093370",
            "prdt_name": "후성",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "2",
            "thdt_sll_qty": "0",
            "hldg_qty": "2",
            "ord_psbl_qty": "2",
            "pchs_avg_pric": "15510.0000",
            "pchs_amt": "31020",
            "prpr": "9000",
            "evlu_amt": "18000",
            "evlu_pfls_amt": "-13020",
            "evlu_pfls_rt": "-41.97",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt": "",
            "stck_loan_unpr": "0.0000",
            "bfdy_cprs_icdc": "0",
            "fltt_rt": "0.00000000"
        },
        {
            "pdno": "096770",
            "prdt_name": "SK이노베이션",
            "trad_dvsn_name": "현금",
            "bfdy_buy_qty": "0",
            "bfdy_sll_qty": "0",
            "thdt_buyqty": "10",
            "thdt_sll_qty": "0",
            "hldg_qty": "10",
            "ord_psbl_qty": "10",
            "pchs_avg_pric": "228000.0000",
            "pchs_amt": "2280000",
            "prpr": "124100",
            "evlu_amt": "1241000",
            "evlu_pfls_amt": "-1039000",
            "evlu_pfls_rt": "-45.57",
            "evlu_erng_rt": "0.00000000",
            "loan_dt": "",
            "loan_amt": "0",
            "stln_slng_chgs": "0",
            "expd_dt
```

</details>


