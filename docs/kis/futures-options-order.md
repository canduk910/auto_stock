# [국내선물옵션] 주문/계좌 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (15개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 191 | REST | (야간)선물옵션 증거금 상세 | (구) JTCE6003R (신) CTFN7107R | GET | `/uapi/domestic-futureoption/v1/trading/ngt-margin-detail` |  |
| 192 | REST | 선물옵션 총자산현황 | CTRP6550R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-deposit` |  |
| 193 | REST | 선물옵션기간약정수수료일별 | CTFO6119R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-daily-amount-fee` |  |
| 194 | REST | (야간)선물옵션 잔고현황 | (구) JTCE6001R (신) CTFN6118R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance` |  |
| 195 | REST | 선물옵션 잔고현황 | CTFO6118R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance` | ✓ |
| 196 | REST | 선물옵션 주문 | (주간 매수/매도) TTTO1101U (야간 매수/매도) (구) JTCE1001U (신) STTN1101U | POST | `/uapi/domestic-futureoption/v1/trading/order` | ✓ |
| 197 | REST | 선물옵션 잔고평가손익내역 | CTFO6159R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance-valuation-pl` |  |
| 198 | REST | 선물옵션 증거금률 | TTTO6032R | GET | `/uapi/domestic-futureoption/v1/quotations/margin-rate` |  |
| 199 | REST | 선물옵션 정정취소주문 | (주간 정정/취소) TTTO1103U (야간 정정/취소) (구) JTCE1002U (신) STTN1103U | POST | `/uapi/domestic-futureoption/v1/trading/order-rvsecncl` | ✓ |
| 200 | REST | 선물옵션 주문체결내역조회 | TTTO5201R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ccnl` |  |
| 201 | REST | (야간)선물옵션 주문체결 내역조회 | (구) JTCE5005R (신) STTN5201R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl` |  |
| 202 | REST | (야간)선물옵션 주문가능 조회 | (구) JTCE1004R (신) STTN5105R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order` |  |
| 203 | REST | 선물옵션 잔고정산손익내역 | CTFO6117R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-balance-settlement-pl` |  |
| 204 | REST | 선물옵션 주문가능 | TTTO5105R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-psbl-order` | ✓ |
| 205 | REST | 선물옵션 기준일체결내역 | CTFO5139R | GET | `/uapi/domestic-futureoption/v1/trading/inquire-ccnl-bstime` |  |

---

## 상세 명세


### (야간)선물옵션 증거금 상세

- **API ID**: 국내선물-024
- **실전 TR_ID**: (구) JTCE6003R (신) CTFN7107R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/ngt-margin-detail`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(야간)선물옵션 증거금상세 API입니다.
한국투자 HTS(eFriend Plus) &gt; [2537] 야간선물옵션 증거금상세 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | (구) JTCE6003R (신) CTFN7107R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
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
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 2 | `MGNA_DVSN_CD` | 증거금 구분코드 | string | Y | 2 | 위탁(01), 유지(02) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (89)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array<br>아래 18가지 항목이 순서대로 출력됨<br>(1) A. 신규증거금 - 선물 - 1.개별종목<br>(2) A. 신규증거금 - 선물 - 2.스프레드<br>(3) A. 신규증거금 - 3. ﻿﻿﻿옵션매수증거금<br>﻿﻿(4) A. 신규증거금 - 4. 옵션매도증거금<br>﻿﻿(5) A. 소계(1+2+3+4)<br>(6) B. 순위험증거금 - 1. ﻿﻿가격변동증거금<br>(7) B. 순위험증거금 - 2. ﻿﻿﻿선물스프레드증거금<br>﻿﻿(8) B. 순위험증거금 - 3. 인수수도 증거금 등<br>(9) B. 순위험증거금 - 4. 최소증거금<br>(10) B. 순위험증거금 - 5. 옵션가격증거금<br>(11) B. 순위험증거금 - 6. 총위험증거금<br>(12) B. 소계SUM상품군별MAX[{MAX(1+2+3,4)+5},6]<br>(13) C. 결제예정금액 - 1. ﻿﻿﻿당일옵션매수금액<br>(14) ﻿﻿C. 결제예정금액 - 2. 당일옵션매도금액<br>(15) C. 결제예정금액 - 3. ﻿﻿당일선물손실<br>﻿﻿﻿(16) C. 결제예정금액 - 4. 당일선물이익 <br>(17) C.소계(1-2+3-4)<br>(18) (A)+B+(C) |
| 4 | `cash_amt` | 현금금액 | string | Y | 19 |  |
| 5 | `tot_amt` | 총금액 | string | Y | 19 |  |
| 6 | `output2` | 응답상세 | object array | Y |  | array<br>아래 5가지 항목이 순서대로 출력됨<br>(1) 예수금<br>(2) 인출가능금액<br>(3) 주문가능금액<br>﻿﻿(4) 위탁증거금액<br>﻿﻿(5) 추가증거금액<br>※ 인출가능금액은 정산 후 인출가능 예정 금액입니다.<br>현재 시점 실제 인출 가능금액은 정규장, 야간시장 인출가능금액 중 적은 금액 기준입니다. |
| 7 | `cash_amt` | 현금금액 | string | Y | 19 |  |
| 8 | `sbst_amt` | 대용금액 | string | Y | 19 |  |
| 9 | `tot_amt` | 총금액 | string | Y | 19 |  |
| 10 | `output3` | 응답상세 | object | Y |  |  |
| 11 | `base_dpsa_gdat_grad_cd` | 기본예탁금차등등급코드 | string | Y | 2 |  |
| 12 | `bfdy_sbst_sll_ccld_amt` | 전일대용매도체결금액 | string | Y | 19 |  |
| 13 | `bfdy_sbst_sll_sbst_amt` | 전일대용매도대용금액 | string | Y | 19 |  |
| 14 | `excc_dfpa` | 정산차금 | string | Y | 19 |  |
| 15 | `fee_amt` | 수수료금액 | string | Y | 19 |  |
| 16 | `nxdy_dncl_amt` | 익일예수금액 | string | Y | 19 |  |
| 17 | `opt_base_dpsa_gdat_grad_cd` | 옵션기본예탁금차등등급코드 | string | Y | 2 |  |
| 18 | `opt_buy_exus_acnt_yn` | 옵션매수전용계좌여부 | string | Y | 1 |  |
| 19 | `opt_dfpa` | 옵션차금 | string | Y | 19 |  |
| 20 | `prsm_dpast_amt` | 추정예탁자산금액 | string | Y | 19 |  |
| 21 | `thdt_sbst_sll_ccld_amt` | 당일대용매도체결금액 | string | Y | 19 |  |
| 22 | `thdt_sbst_sll_sbst_amt` | 당일대용매도대용금액 | string | Y | 19 |  |
| 23 | `output1` | 응답상세 | object array | Y |  | Array 신 TR 사용 필드 |
| 24 | `futr_new_mgn_amt` | 선물신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 25 | `futr_sprd_ord_mgna` | 선물스프레드주문증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 26 | `opt_sll_new_mgn_amt` | 옵션매도신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 27 | `opt_buy_new_mgn_amt` | 옵션매수신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 28 | `new_mgn_amt` | 신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 29 | `opt_pric_mgna` | 옵션가격증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 30 | `fuop_pric_altr_mgna` | 선물옵션가격변동증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 31 | `futr_sprd_mgna` | 선물스프레드증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 32 | `uwdl_mgna` | 인수도증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 33 | `ctrt_per_min_mgna` | 계약당최소증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 34 | `tot_risk_mgna` | 총위험증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 35 | `netrisk_brkg_mgna` | 순위험위탁증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 36 | `opt_sll_chgs` | 옵션매도대금 | string | Y | 19 | 신 TR 사용 필드 |
| 37 | `opt_buy_chgs` | 옵션매수대금 | string | Y | 19 | 신 TR 사용 필드 |
| 38 | `futr_loss_amt` | 선물손실금액 | string | Y | 19 | 신 TR 사용 필드 |
| 39 | `futr_prft_amt` | 선물이익금액 | string | Y | 19 | 신 TR 사용 필드 |
| 40 | `thdt_ccld_net_loss_amt` | 당일체결순손실금액 | string | Y | 19 | 신 TR 사용 필드 |
| 41 | `brkg_mgna` | 위탁증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 42 | `output2` | 응답상세 | object array | Y |  | Array 신 TR 사용 필드 |
| 43 | `futr_new_mgn_amt` | 선물신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 44 | `futr_sprd_ord_mgna` | 선물스프레드주문증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 45 | `opt_sll_new_mgn_amt` | 옵션매도신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 46 | `opt_buy_new_mgn_amt` | 옵션매수신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 47 | `new_mgn_amt` | 신규증거금액 | string | Y | 19 | 신 TR 사용 필드 |
| 48 | `opt_pric_mgna` | 옵션가격증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 49 | `fuop_pric_altr_mgna` | 선물옵션가격변동증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 50 | `futr_sprd_mgna` | 선물스프레드증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 51 | `uwdl_mgna` | 인수도증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 52 | `ctrt_per_min_mgna` | 계약당최소증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 53 | `tot_risk_mgna` | 총위험증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 54 | `netrisk_brkg_mgna` | 순위험위탁증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 55 | `opt_sll_chgs` | 옵션매도대금 | string | Y | 19 | 신 TR 사용 필드 |
| 56 | `opt_buy_chgs` | 옵션매수대금 | string | Y | 19 | 신 TR 사용 필드 |
| 57 | `futr_loss_amt` | 선물손실금액 | string | Y | 19 | 신 TR 사용 필드 |
| 58 | `futr_prft_amt` | 선물이익금액 | string | Y | 19 | 신 TR 사용 필드 |
| 59 | `thdt_ccld_net_loss_amt` | 당일체결순손실금액 | string | Y | 19 | 신 TR 사용 필드 |
| 60 | `brkg_mgna` | 위탁증거금 | string | Y | 19 | 신 TR 사용 필드 |
| 61 | `output3` | 응답상세 | object | Y |  | Single 신 TR 사용 필드 |
| 62 | `dnca_cash` | 예수금현금 | string | Y | 19 | 신 TR 사용 필드 |
| 63 | `dnca_sbst` | 예수금대용 | string | Y | 19 | 신 TR 사용 필드 |
| 64 | `dnca_tota` | 예수금총액 | string | Y | 19 | 신 TR 사용 필드 |
| 65 | `wdrw_psbl_cash_amt` | 인출가능현금금액 | string | Y | 19 | 신 TR 사용 필드 |
| 66 | `wdrw_psbl_sbsa` | 인출가능대용금액 | string | Y | 19 | 신 TR 사용 필드 |
| 67 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 | 신 TR 사용 필드 |
| 68 | `ord_psbl_cash_amt` | 주문가능현금금액 | string | Y | 19 | 신 TR 사용 필드 |
| 69 | `ord_psbl_sbsa` | 주문가능대용금액 | string | Y | 19 | 신 TR 사용 필드 |
| 70 | `ord_psbl_tot_amt` | 주문가능총금액 | string | Y | 19 | 신 TR 사용 필드 |
| 71 | `brkg_mgna_cash_amt` | 위탁증거금현금금액 | string | Y | 19 | 신 TR 사용 필드 |
| 72 | `brkg_mgna_sbst` | 위탁증거금대용 | string | Y | 19 | 신 TR 사용 필드 |
| 73 | `brkg_mgna_tot_amt` | 위탁증거금총금액 | string | Y | 19 | 신 TR 사용 필드 |
| 74 | `add_mgna_cash_amt` | 추가증거금현금금액 | string | Y | 19 | 신 TR 사용 필드 |
| 75 | `add_mgna_sbsa` | 추가증거금대용금액 | string | Y | 19 | 신 TR 사용 필드 |
| 76 | `add_mgna_tot_amt` | 추가증거금총금액 | string | Y | 19 | 신 TR 사용 필드 |
| 77 | `bfdy_sbst_sll_sbst_amt` | 전일대용매도대용금액 | string | Y | 19 | 신 TR 사용 필드 |
| 78 | `thdt_sbst_sll_sbst_amt` | 당일대용매도대용금액 | string | Y | 19 | 신 TR 사용 필드 |
| 79 | `bfdy_sbst_sll_ccld_amt` | 전일대용매도체결금액 | string | Y | 19 | 신 TR 사용 필드 |
| 80 | `thdt_sbst_sll_ccld_amt` | 당일대용매도체결금액 | string | Y | 19 | 신 TR 사용 필드 |
| 81 | `opt_dfpa` | 옵션차금 | string | Y | 19 | 신 TR 사용 필드 |
| 82 | `excc_dfpa` | 정산차금 | string | Y | 19 | 신 TR 사용 필드 |
| 83 | `fee_amt` | 수수료금액 | string | Y | 19 | 신 TR 사용 필드 |
| 84 | `nxdy_dncl_amt` | 익일예수금액 | string | Y | 19 | 신 TR 사용 필드 |
| 85 | `prsm_dpast_amt` | 추정예탁자산금액 | string | Y | 19 | 신 TR 사용 필드 |
| 86 | `opt_buy_exus_acnt_yn` | 옵션매수전용계좌여부 | string | Y | 19 | 신 TR 사용 필드 |
| 87 | `base_dpsa_gdat_grad_cd` | 기본예탁금차등등급코드 | string | Y | 19 | 신 TR 사용 필드 |
| 88 | `opt_base_dpsa_gdat_grad_cd` | 옵션기본예탁금차등등급코드 | string | Y | 19 | 신 TR 사용 필드 |

<details><summary>Request Example (Python)</summary>

```text
CANO:12345678
ACNT_PRDT_CD:03
MGNA_DVSN_CD:01
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": [
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "tot_amt": "0"
        }
    ],
    "output2": [
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "100000000",
            "sbst_amt": "0",
            "tot_amt": "100000000"
        },
        {
            "cash_amt": "0",
            "sbst_amt": "0",
            "tot_amt": "0"
        },
        {
            "cash_amt": "0",
            "sbst_amt": "0",
            "tot_amt": "0"
        }
    ],
    "output3": {
        "bfdy_sbst_sll_sbst_amt": "0",
        "thdt_sbst_sll_sbst_amt": "0",
        "bfdy_sbst_sll_ccld_amt": "0",
        "thdt_sbst_sll_ccld_amt": "0",
        "opt_buy_exus_acnt_yn": "N",
        "base_dpsa_gdat_grad_cd": "03",
        "opt_dfpa": "0",
        "excc_dfpa": "0",
        "fee_amt": "0",
        "nxdy_dncl_amt": "100000000",
        "prsm_dpast_amt": "100000000",
        "opt_base_dpsa_gdat_grad_cd": "01"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 선물옵션 총자산현황

- **API ID**: v1_국내선물-014
- **실전 TR_ID**: CTRP6550R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-deposit`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 총자산현황 API 입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTRP6550R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (34)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `dnca_tota` | 예수금총액 | string | Y | 19 |  |
| 5 | `bfdy_chck_amt` | 전일수표금액 | string | Y | 19 |  |
| 6 | `thdt_chck_amt` | 당일수표금액 | string | Y | 19 |  |
| 7 | `rlth_uwdl_dpos_amt` | 실물인수도예치금액 | string | Y | 19 |  |
| 8 | `brkg_mgna_cash` | 위탁증거금현금 | string | Y | 19 |  |
| 9 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 |  |
| 10 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 |  |
| 11 | `ord_psbl_tota` | 주문가능총액 | string | Y | 19 |  |
| 12 | `dnca_sbst` | 예수금대용 | string | Y | 19 |  |
| 13 | `scts_sbst_amt` | 유가증권대용금액 | string | Y | 19 |  |
| 14 | `frcr_evlu_amt` | 외화평가금액 | string | Y | 19 |  |
| 15 | `brkg_mgna_sbst` | 위탁증거금대용 | string | Y | 19 |  |
| 16 | `sbst_rlse_psbl_amt` | 대용해제가능금액 | string | Y | 19 |  |
| 17 | `mtnc_rt` | 유지비율 | string | Y | 238 |  |
| 18 | `add_mgna_tota` | 추가증거금총액 | string | Y | 19 |  |
| 19 | `add_mgna_cash` | 추가증거금현금 | string | Y | 19 |  |
| 20 | `rcva` | 미수금 | string | Y | 19 |  |
| 21 | `futr_trad_pfls` | 선물매매손익 | string | Y | 19 |  |
| 22 | `opt_trad_pfls_amt` | 옵션매매손익금액 | string | Y | 19 |  |
| 23 | `trad_pfls_smtl` | 매매손익합계 | string | Y | 19 |  |
| 24 | `futr_evlu_pfls_amt` | 선물평가손익금액 | string | Y | 19 |  |
| 25 | `opt_evlu_pfls_amt` | 옵션평가손익금액 | string | Y | 19 |  |
| 26 | `evlu_pfls_smtl` | 평가손익합계 | string | Y | 19 |  |
| 27 | `excc_dfpa` | 정산차금 | string | Y | 19 |  |
| 28 | `opt_dfpa` | 옵션차금 | string | Y | 19 |  |
| 29 | `brkg_fee` | 위탁수수료 | string | Y | 19 |  |
| 30 | `nxdy_dnca` | 익일예수금 | string | Y | 19 |  |
| 31 | `prsm_dpast_amt` | 추정예탁자산금액 | string | Y | 19 |  |
| 32 | `cash_mntn_amt` | 현금유지금액 | string | Y | 19 |  |
| 33 | `hack_acdt_acnt_move_amt` | 해킹사고계좌이전금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "dnca_tota": "100000000",
        "bfdy_chck_amt": "0",
        "thdt_chck_amt": "0",
        "rlth_uwdl_dpos_amt": "0",
        "brkg_mgna_cash": "17907612",
        "wdrw_psbl_tot_amt": "34046775",
        "ord_psbl_cash": "64184775",
        "ord_psbl_tota": "64184775",
        "dnca_sbst": "0",
        "scts_sbst_amt": "0",
        "frcr_evlu_amt": "0",
        "brkg_mgna_sbst": "17907613",
        "sbst_rlse_psbl_amt": "0",
        "mtnc_rt": "418.23000000",
        "add_mgna_tota": "0",
        "add_mgna_cash": "0",
        "rcva": "0",
        "futr_trad_pfls": "0",
        "opt_trad_pfls_amt": "0",
        "trad_pfls_smtl": "0",
        "futr_evlu_pfls_amt": "4187500",
        "opt_evlu_pfls_amt": "-697500",
        "evlu_pfls_smtl": "3490000",
        "excc_dfpa": "-30138000",
        "opt_dfpa": "0",
        "brkg_fee": "0",
        "nxdy_dnca": "69862000",
        "prsm_dpast_amt": "69864500",
        "cash_mntn_amt": "0",
        "hack_acdt_acnt_move_amt": "0"
    },
    "rt_cd": "0",
    "msg_cd": "APRP0126",
    "msg1": "조회이(가) 완료되었습니다.                                                      "
}
```

</details>



### 선물옵션기간약정수수료일별

- **API ID**: v1_국내선물-017
- **실전 TR_ID**: CTFO6119R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-daily-amount-fee`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션기간약정수수료일별 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTFO6119R |
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
| 2 | `INQR_STRT_DAY` | 조회시작일 | string | Y | 8 | 조회시작일(YYYYMMDD) |
| 3 | `INQR_END_DAY` | 조회종료일 | string | Y | 8 | 조회종료일(YYYYMMDD) |
| 4 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 연속조회검색조건200 |
| 5 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 연속조회키200 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (39)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | array | Y |  | array |
| 4 | `ord_dt` | 주문일자 | string | Y | 8 |  |
| 5 | `pdno` | 상품번호 | string | Y | 12 |  |
| 6 | `item_name` | 종목명 | string | Y | 60 |  |
| 7 | `sll_agrm_amt` | 매도약정금액 | string | Y | 19 |  |
| 8 | `sll_fee` | 매도수수료 | string | Y | 19 |  |
| 9 | `buy_agrm_amt` | 매수약정금액 | string | Y | 19 |  |
| 10 | `buy_fee` | 매수수수료 | string | Y | 19 |  |
| 11 | `tot_fee_smtl` | 총수수료합계 | string | Y | 19 |  |
| 12 | `trad_pfls` | 매매손익 | string | Y | 19 |  |
| 13 | `output2` | 응답상세2 | object | Y |  |  |
| 14 | `futr_agrm` | 선물약정 | string | Y | 19 |  |
| 15 | `futr_agrm_amt` | 선물약정금액 | string | Y | 19 |  |
| 16 | `futr_agrm_amt_smtl` | 선물약정금액합계 | string | Y | 19 |  |
| 17 | `futr_sll_fee_smtl` | 선물매도수수료합계 | string | Y | 19 |  |
| 18 | `futr_buy_fee_smtl` | 선물매수수수료합계 | string | Y | 19 |  |
| 19 | `futr_fee_smtl` | 선물수수료합계 | string | Y | 19 |  |
| 20 | `opt_agrm` | 옵션약정 | string | Y | 19 |  |
| 21 | `opt_agrm_amt` | 옵션약정금액 | string | Y | 19 |  |
| 22 | `opt_agrm_amt_smtl` | 옵션약정금액합계 | string | Y | 19 |  |
| 23 | `opt_sll_fee_smtl` | 옵션매도수수료합계 | string | Y | 19 |  |
| 24 | `opt_buy_fee_smtl` | 옵션매수수수료합계 | string | Y | 19 |  |
| 25 | `opt_fee_smtl` | 옵션수수료합계 | string | Y | 19 |  |
| 26 | `prdt_futr_agrm` | 상품선물약정 | string | Y | 19 |  |
| 27 | `prdt_fuop` | 상품선물옵션 | string | Y | 19 |  |
| 28 | `prdt_futr_evlu_amt` | 상품선물평가금액 | string | Y | 8 |  |
| 29 | `futr_fee` | 선물수수료 | string | Y | 19 |  |
| 30 | `opt_fee` | 옵션수수료 | string | Y | 19 |  |
| 31 | `fee` | 수수료 | string | Y | 19 |  |
| 32 | `sll_agrm_amt` | 매도약정금액 | string | Y | 19 |  |
| 33 | `buy_agrm_amt` | 매수약정금액 | string | Y | 19 |  |
| 34 | `agrm_amt_smtl` | 약정금액합계 | string | Y | 19 |  |
| 35 | `sll_fee` | 매도수수료 | string | Y | 19 |  |
| 36 | `buy_fee` | 매수수수료 | string | Y | 19 |  |
| 37 | `fee_smtl` | 수수료합계 | string | Y | 19 |  |
| 38 | `trad_pfls_smtl` | 매매손익합계 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"INQR_STRT_DAY":"20230901",
	"INQR_END_DAY":"20230920",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "12345678!^03!^20230901!^20230920                                                                                                                                                                        ",
    "ctx_area_nk200": " !^                                                                                                                                                                                                     ",
    "output1": [
        {
            "ord_dt": "20230901",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230904",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230905",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230906",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230907",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230908",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230911",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230914",
            "pdno": "KR4101T90003",
            "item_name": "F 202309",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "0",
            "buy_fee": "0",
            "tot_fee_smtl": "0",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230920",
            "pdno": "KR4101TC0008",
            "item_name": "F 202312",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "419375000",
            "buy_fee": "41140",
            "tot_fee_smtl": "41140",
            "trad_pfls": "0"
        },
        {
            "ord_dt": "20230920",
            "pdno": "KR4201TA3409",
            "item_name": "C 202310 340.0",
            "sll_agrm_amt": "0",
            "sll_fee": "0",
            "buy_agrm_amt": "700000",
            "buy_fee": "2750",
            "tot_fee_smtl": "2750",
            "trad_pfls": "0"
        }
    ],
    "output2": {
        "futr_agrm": "0",
        "futr_agrm_amt": "419375000",
        "futr_agrm_amt_smtl": "419375000",
        "futr_sll_fee_smtl": "0",
        "futr_buy_fee_smtl": "41140",
        "futr_fee_smtl": "41140",
        "opt_agrm": "0",
        "opt_agrm_amt": "700000",
        "opt_agrm_amt_smtl": "700000",
        "opt_sll_fee_smtl": "0",
        "opt_buy_fee_smtl": "2750",
        "opt_fee_smtl": "2750",
        "prdt_futr_agrm": "0",
        "prdt_fuop": "0",
        "prdt_futr_evlu_amt": "0",
        "futr_fee": "0",
        "opt_fee": "0",
        "fee": "0",
        "sll_agrm_amt": "0",
        "buy_agrm_amt": "420075000",
        "agrm_amt_smtl": "420075000",
        "sll_fee": "0",
        "buy_fee": "43890",
        "fee_smtl": "43890",
        "trad_pfls_smtl": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### (야간)선물옵션 잔고현황

- **API ID**: 국내선물-010
- **실전 TR_ID**: (구) JTCE6001R (신) CTFN6118R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(야간)선물옵션 잔고현황 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | (구) JTCE6001R (신) CTFN6118R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `ACNT_PWD` | 계좌비밀번호 | string | Y | 84 | 공란("")으로 조회 |
| 3 | `MGNA_DVSN` | 증거금구분 | string | Y | 2 | 01 : 개시,  02 : 유지 |
| 4 | `EXCC_STAT_CD` | 정산상태코드 | string | Y | 1 | 1 : 정산 (정산가격으로 잔고 조회)<br>2 : 본정산 (매입가격으로 잔고 조회) |
| 5 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 6 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (56)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세2 | object | Y |  |  |
| 4 | `dnca_cash` | 예수금현금 | string | Y | 19 | 총주문수량 |
| 5 | `frcr_dncl_amt` | 외화예수금액 | string | Y | 19 | 주문채번지점번호 |
| 6 | `dnca_sbst` | 예수금대용 | string | Y | 19 |  |
| 7 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 |  |
| 8 | `cash_mgna` | 현금증거금 | string | Y | 19 |  |
| 9 | `sbst_mgna` | 대용증거금 | string | Y | 19 |  |
| 10 | `mgna_tota` | 증거금총액 | string | Y | 19 |  |
| 11 | `opt_dfpa` | 옵션차금 | string | Y | 19 |  |
| 12 | `thdt_dfpa` | 당일차금 | string | Y | 19 |  |
| 13 | `rnwl_dfpa` | 갱신차금 | string | Y | 19 |  |
| 14 | `fee` | 수수료 | string | Y | 19 |  |
| 15 | `nxdy_dnca` | 익일예수금 | string | Y | 19 |  |
| 16 | `nxdy_dncl_amt` | 익일예수금액 | string | Y | 19 |  |
| 17 | `prsm_dpast` | 추정예탁자산 | string | Y | 19 | 종합계좌번호 |
| 18 | `pprt_ord_psbl_cash` | 적정주문가능현금 | string | Y | 19 | 총체결수량 |
| 19 | `add_mgna_cash` | 추가증거금현금 | string | Y | 19 | 총체결금액 |
| 20 | `add_mgna_tota` | 추가증거금총액 | string | Y | 19 | 종합계좌명 |
| 21 | `futr_trad_pfls_amt` | 선물매매손익금액 | string | Y | 19 | 수수료 |
| 22 | `opt_trad_pfls_amt` | 옵션매매손익금액 | string | Y | 19 | 계좌상품코드 |
| 23 | `futr_evlu_pfls_amt` | 선물평가손익금액 | string | Y | 19 | 주문일자 |
| 24 | `opt_evlu_pfls_amt` | 옵션평가손익금액 | string | Y | 19 | 주문번호 |
| 25 | `trad_pfls_amt_smtl` | 매매손익금액합계 | string | Y | 19 |  |
| 26 | `evlu_pfls_amt_smtl` | 평가손익금액합계 | string | Y | 19 |  |
| 27 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 |  |
| 28 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 |  |
| 29 | `ord_psbl_sbst` | 주문가능대용 | string | Y | 19 |  |
| 30 | `ord_psbl_tota` | 주문가능총액 | string | Y | 19 |  |
| 31 | `mmga_tot_amt` | 유지증거금총금액 | string | Y | 19 | 신규 TR 미사용 필드 |
| 32 | `mmga_cash_amt` | 유지증거금현금금액 | string | Y | 19 | 신규 TR 미사용 필드 |
| 33 | `mtnc_rt` | 유지비율 | string | Y | 32238 | 신규 TR 미사용 필드 |
| 34 | `isfc_amt` | 부족금액 | string | Y | 19 | 신규 TR 미사용 필드 |
| 35 | `pchs_amt_smtl` | 매입금액합계 | string | Y | 19 |  |
| 36 | `evlu_amt_smtl` | 평가금액합계 | string | Y | 19 |  |
| 37 | `output1` | 응답상세2 | object array | Y |  | 시간별체결 정보 |
| 38 | `cano` | 종합계좌번호 | string | Y | 8 |  |
| 39 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 |  |
| 40 | `pdno` | 상품번호 | string | Y | 12 |  |
| 41 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 42 | `shtn_pdno` | 단축상품번호 | string | Y | 12 |  |
| 43 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 44 | `sll_buy_dvsn_name` | 매도매수구분명 | string | Y | 4 | 신규 TR 사용 필드 |
| 45 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 |  |
| 46 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 47 | `cblc_qty` | 잔고수량 | string | Y | 19 |  |
| 48 | `excc_unpr` | 정산단가 | string | Y | 32238 |  |
| 49 | `ccld_avg_unpr1` | 체결평균단가1 | string | Y | 32238 |  |
| 50 | `idx_clpr` | 지수종가 | string | Y | 32238 |  |
| 51 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 52 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 53 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 54 | `trad_pfls_amt` | 매매손익금액 | string | Y | 19 |  |
| 55 | `lqd_psbl_qty` | 청산가능수량 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"ACNT_PWD":"",
	"MGNA_DVSN":"01",
	"EXCC_STAT_CD":"1",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "80012345^03^01^1^                                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [
        {
            "cano": "80012345",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101SC0009",
            "prdt_type_cd": "301",
            "shtn_pdno": "101S12",
            "prdt_name": "F 202212",
            "sll_buy_dvsn_cd": "02",
            "trad_dvsn_name": "매수",
            "cblc_qty": "3",
            "excc_unpr": "309.10000000",
            "ccld_avg_unpr1": "320.50000000",
            "idx_clpr": "307.45000000",
            "pchs_amt": "231825000",
            "evlu_amt": "230587500",
            "evlu_pfls_amt": "-1237500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "3"
        }
    ],
    "output2": {
        "dnca_cash": "10101527360",
        "frcr_dncl_amt": "0",
        "dnca_sbst": "0",
        "tot_dncl_amt": "10101527360",
        "cash_mgna": "108922232",
        "sbst_mgna": "133854708",
        "mgna_tota": "242776940",
        "opt_dfpa": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "-16200000",
        "fee": "0",
        "nxdy_dnca": "10085327360",
        "prsm_dpast": "10085327360",
        "pprt_ord_psbl_cash": "9858750420",
        "add_mgna_cash": "0",
        "add_mgna_tota": "0",
        "futr_trad_pfls_amt": "0",
        "opt_trad_pfls_amt": "0",
        "futr_evlu_pfls_amt": "-1237500",
        "opt_evlu_pfls_amt": "0",
        "trad_pfls_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "-1237500",
        "wdrw_psbl_tot_amt": "9858750420",
        "ord_psbl_cash": "9858750420",
        "ord_psbl_sbst": "0",
        "ord_psbl_tota": "9858750420",
        "mmga_tot_amt": "0",
        "mmga_cash_amt": "0",
        "mtnc_rt": "0.00000000",
        "isfc_amt": "0",
        "pchs_amt_smtl": "231825000",
        "evlu_amt_smtl": "230587500"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 선물옵션 잔고현황

- **API ID**: v1_국내선물-004
- **실전 TR_ID**: CTFO6118R
- **모의 TR_ID**: VTFO6118R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 잔고현황 API입니다. 한 번의 호출에 최대 20건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>CTFO6118R : 선물 옵션 잔고 현황<br>[모의투자] <br>VTFO6118R : 선물 옵션 잔고 현황 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
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
| 2 | `MGNA_DVSN` | 증거금 구분 | string | Y | 2 | 01 : 개시<br>02 : 유지 |
| 3 | `EXCC_STAT_CD` | 정산상태코드 | string | Y | 1 | 1 : 정산 (정산가격으로 잔고 조회)<br>2 : 본정산 (매입가격으로 잔고 조회) |
| 4 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 5 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (54)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output1` | 응답상세1 | array | Y |  |  |
| 6 | `cano` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 7 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 8 | `pdno` | 상품번호 | string | Y | 12 | 선물옵션종목코드 |
| 9 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 10 | `shtn_pdno` | 단축상품번호 | string | Y | 12 | 단축상품번호 (예: 101P09) |
| 11 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 12 | `sll_buy_dvsn_name` | 매도매수구분명 | string | Y | 4 | 매도/매수 구분의 명칭<br>- 매수잔고를 가진 경우, "매수" 혹은 "BUY"로 출력<br>- 매도잔고를 가진 경우, "매도" 혹은 "SLL"로 출력<br>- 당일 잔고를 청산하여 잔고를 가지고 있지 않은 경우 빈칸으로 출력 |
| 13 | `cblc_qty` | 잔고수량 | string | Y | 10 | 보유한 종목의 수량 |
| 14 | `excc_unpr` | 정산단가 | string | Y | 32 | 당일 종가로 정산한 가격 |
| 15 | `ccld_avg_unpr1` | 체결평균단가1 | string | Y | 32 | 보유한 종목의 평균 체결 가격 |
| 16 | `idx_clpr` | 지수종가 | string | Y | 32 |  |
| 17 | `pchs_amt` | 매입금액 | string | Y | 19 | 보유 종목을 매수한 금액 |
| 18 | `evlu_amt` | 평가금액 | string | Y | 19 | 보유 종목을 현재가로 평가하여 산출한 금액 |
| 19 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 | 매입금액과 평가금액을 비교한 손익 |
| 20 | `trad_pfls_amt` | 매매손익금액 | string | Y | 19 | 매수와 매도가 완료된 수량에 대한 실현 손익 |
| 21 | `lqd_psbl_qty` | 청산가능수량 | string | Y | 19 | 청산 가능한 수량 |
| 22 | `output2` | 응답상세2 | object | Y |  |  |
| 23 | `dnca_cash` | 예수금현금 | string | Y | 19 | 원화로 보유한 현금 (현금미수금액, 수수료미수금액 차감) |
| 24 | `frcr_dncl_amt` | 외화예수금액 | string | Y | 19 | 외화로 보유한 현금 |
| 25 | `dnca_sbst` | 예수금대용 | string | Y | 19 | 주식대용금액+채권대용금액+전일대용매도대용금액+당일대용매도대용금액 |
| 26 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 | 상기 3개 예수금 항목의 합계 금액 |
| 27 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 | 체결된 주문의 합계금액 |
| 28 | `cash_mgna` | 현금증거금 | string | Y | 19 | 원화 현금 중 주문증거금으로 사용된 금액 |
| 29 | `sbst_mgna` | 대용증거금 | string | Y | 19 | 대용 예수금 중 주문증거금으로 사용된 금액 |
| 30 | `mgna_tota` | 증거금총액 | string | Y | 19 | 증거금으로 사용된 항목의 합계 금액 |
| 31 | `opt_dfpa` | 옵션차금 | string | Y | 19 | 당일옵션매도금에서 당일옵션매수금을 차감한 금액 |
| 32 | `thdt_dfpa` | 당일차금 | string | Y | 19 | 당일의 각 매수거래에 대하여 1에 의하여 산출한 금액의 합계액과 당일의 각 매도거래에 대하여 2에 의하여 산출한 금액의 합계액을 합산한 금액<br>1. 매수거래수량*(당일의 정산가격-체결가격)*최소가격변동금액*환산승수<br>2. 매도거래수량*(체결가격-당일의 정산가격)*최소가격변동금액*환산승수 |
| 33 | `rnwl_dfpa` | 갱신차금 | string | Y | 19 | 직전 거래일의 매수미결제약정에 대하여 1에 의하여 산출한 금액과 직전거래일의 매도미결제약정에 대하여 2에 의하여 산출한 금액을 합산한 금액<br>1. 매수미결제약정*(당일의 정산가격-직전거래일의 정산가격)*최소가격변동 금액*환산승수<br>2. 매도미결제약정*(직전거래일의 정산가격-당일의 정산가격)*최소가격변동 금액*환산승수 |
| 34 | `fee` | 수수료 | string | Y | 19 | 체결된 주문에 의한 매매수수료 |
| 35 | `nxdy_dnca` | 익일예수금 | string | Y | 19 | 당일 매매내역을 근거로 익일(결제일) 고객님 계좌에 있는 현금 |
| 36 | `nxdy_dncl_amt` | 익일예수금액 | string | Y | 19 |  |
| 37 | `prsm_dpast` | 추정예탁자산 | string | Y | 19 | 보유한 잔고를 정산 기준으로 평가한 금액과 예수금을 합한 금액 |
| 38 | `prsm_dpast_amt` | 추정예탁자산금액 | string | Y | 19 |  |
| 39 | `pprt_ord_psbl_cash` | 적정주문가능현금 | string | Y | 19 | 미수없는 주문가능금액 |
| 40 | `add_mgna_cash` | 추가증거금현금 | string | Y | 19 | 장 종료 후 예탁평가액이 유지증거금을 하회할 경우 또는 예탁현금이 결제금액 보다 적은 경우 고객이 추가적으로 납부해야<br>하는 증거금 |
| 41 | `add_mgna_tota` | 추가증거금총액 | string | Y | 19 |  |
| 42 | `futr_trad_pfls_amt` | 선물매매손익금액 | string | Y | 19 | 선물 매수와 매도가 완료된 수량에 대한 실현 손익 |
| 43 | `opt_trad_pfls_amt` | 옵션매매손익금액 | string | Y | 19 | 옵션 매수와 매도가 완료된 수량에 대한 실현 손익 |
| 44 | `futr_evlu_pfls_amt` | 선물평가손익금액 | string | Y | 19 | 선물 잔고의 매입가격 또는 정산가격과 평가금액을 비교한 손익 |
| 45 | `opt_evlu_pfls_amt` | 옵션평가손익금액 | string | Y | 19 | 옵션 잔고의 매입가격 또는 정산가격과 평가금액을 비교한 손익 |
| 46 | `trad_pfls_amt_smtl` | 매매손익금액합계 | string | Y | 19 | 선물매매손익금액과 옵션매매손익금액을 합한 금액 |
| 47 | `evlu_pfls_amt_smtl` | 평가손익금액합계 | string | Y | 19 | 선물평가손익금액과 옵션평가손익금액을 합한 금액 |
| 48 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 | 출금 가능한 현금(예탁현금+예탁대용-예탁증거금총액) |
| 49 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 | 예수금현금에서 현금증거금을 차감한 금액 |
| 50 | `ord_psbl_sbst` | 주문가능대용 | string | Y | 19 | 예수금대용에서 대용증거금을 차감한 금액 |
| 51 | `ord_psbl_tota` | 주문가능총액 | string | Y | 19 | 주문가능현금과 주문가능대용을 합한 금액 |
| 52 | `pchs_amt_smtl` | 매입금액합계 | string | Y | 19 | 종목별 매입금액의 합계 금액 |
| 53 | `evlu_amt_smtl` | 평가금액합계 | string | Y | 19 | 종목별 평가금액의 합계 금액 |

<details><summary>Request Example (Python)</summary>

```json
{    
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"3",
	"MGNA_DVSN": "01",
	"EXCC_STAT_CD": "1",
	"CTX_AREA_FK200": "",
	"CTX_AREA_NK200": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk200": "연속조회검색조건200을 입력하세요.",
  "output1": {
    "lqd_psbl_qty": [
      "6",
      "133",
      "110",
      "1000",
      "1000",
      "1000",
      "1000",
      "1",
      "25"
    ],
    "pdno": [
      "KR4101RC0000",
      "KR4101S30001",
      "KR4111RA0000",
      "KR41ACRC0005",
      "KR41ACS60004",
      "KR41ADRC0004",
      "KR41ADS30005",
      "KR41AES90007",
      "KR41DRRA0007"
    ],
    "prdt_type_cd": [
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301",
      "301"
    ],
    "pchs_amt": [
      "586950000",
      "12937575000",
      "78980000",
      "3003000000",
      "3012000000",
      "5686000000",
      "5672000000",
      "2610000",
      "21350000"
    ],
    "sll_buy_dvsn_name": [
      "SLL",
      "BUY",
      "BUY",
      "BUY",
      "SLL",
      "BUY",
      "SLL",
      "SLL",
      "BUY"
    ],
    "trad_pfls_amt": [
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0"
    ],
    "shtn_pdno": [
      "101R12",
      "101S03",
      "111R10",
      "1ACR12",
      "1ACS06",
      "1ADR12",
      "1ADS03",
      "1AES09",
      "1DRR10"
    ],
    "acnt_prdt_cd": [
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      ""
    ],
    "cblc_qty": [
      "6",
      "133",
      "110",
      "1000",
      "1000",
      "1000",
      "1000",
      "1",
      "25"
    ],
    "excc_unpr": [
      "391.30000000",
      "389.10000000",
      "71800.00000000",
      "3003.00000000",
      "3012.00000000",
      "5686.00000000",
      "5672.00000000",
      "2610.00000000",
      "85400.00000000"
    ],
    "cano": [
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      ""
    ],
    "idx_clpr": [
      "380.55000000",
      "389.10000000",
      "71800.00000000",
      "3003.00000000",
      "3012.00000000",
      "5686.00000000",
      "5672.00000000",
      "2610.00000000",
      "85400.00000000"
    ],
    "ccld_avg_unpr1": [
      "402.28975400",
      "406.38538995",
      "71618.18181818",
      "4626.00000000",
      "4766.50000000",
      "6992.50000000",
      "5695.50000000",
      "3430.50000000",
      "87700.00000000"
    ],
    "evlu_pfls_amt": [
      "16125000",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0",
      "0"
    ],
    "evlu_amt": [
      "570825000",
      "12937575000",
      "78980000",
      "3003000000",
      "3012000000",
      "5686000000",
      "5672000000",
      "2610000",
      "21350000"
    ],
    "prdt_name": [
      "F 202112",
      "F 202203",
      "SamsungEle F 202110 (  10)",
      "BBIG K-NewDeal     F 202112",
      "BBIG K-NewDeal     F 202206",
      "Battery K-NewDeal  F 202112",
      "Battery K-NewDeal  F 202203",
      "Bio K-NewDeal      F 202209",
      "C2S        F 202110 (  10)"
    ]
  },
  "rt_cd": "0",
  "output2": {
    "nxdy_dnca": "90016125000",
    "sbst_mgna": "1391065523",
    "cash_mgna": "0",
    "ord_psbl_tota": "88608934477",
    "opt_dfpa": "0",
    "fee": "0",
    "pchs_amt_smtl": "31000465000",
    "prsm_dpast": "90016125000",
    "evlu_pfls_amt_smtl": "16125000",
    "thdt_dfpa": "0",
    "prsm_dpast_amt": "90016125000",
    "frcr_dncl_amt": "0",
    "pprt_ord_psbl_cash": "88608934477",
    "evlu_amt_smtl": "30984340000",
    "futr_trad_pfls_amt": "0",
    "rnwl_dfpa": "16125000",
    "futr_evlu_pfls_amt": "16125000",
    "wdrw_psbl_tot_amt": "88608934477",
    "dnca_sbst": "0",
    "opt_evlu_pfls_amt": "0",
    "dnca_cash": "90000000000",
    "tot_dncl_amt": "90000000000",
    "nxdy_dncl_amt": "90016125000",
    "tot_ccld_amt": "0",
    "opt_trad_pfls_amt": "0",
    "trad_pfls_amt_smtl": "0",
    "ord_psbl_cash": "88608934477",
    "mgna_tota": "1391065523",
    "ord_psbl_sbst": "0",
    "add_mgna_tota": "0",
    "add_mgna_cash": "0"
  },
  "msg1": "조회 되었습니다. (마지막 자료) ",
  "msg_cd": "KIOK0460",
  "ctx_area_nk200": ""
}
```

</details>



### 선물옵션 주문

- **API ID**: v1_국내선물-001
- **실전 TR_ID**: (주간 매수/매도) TTTO1101U (야간 매수/매도) (구) JTCE1001U (신) STTN1101U
- **모의 TR_ID**: (주간 매수/매도) VTTO1101U (야간은 모의투자 미제공)
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-futureoption/v1/trading/order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
​선물옵션 주문 API입니다.
* 선물옵션 운영시간 외 API 호출 시 애러가 발생하오니 운영시간을 확인해주세요.

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
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTO1101U : 선물 옵션 매수 매도 주문 주간 <br>(신) STTN1101U : 선물 옵션 매수 매도 주문 야간 <br>[모의투자]<br>VTTO1101U : 선물 옵션 매수 매도 주문 주간 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `ORD_PRCS_DVSN_CD` | 주문처리구분코드 | string | Y | 2 | 02 : 주문전송 |
| 1 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 2 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 3 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 01 : 매도<br>02 : 매수 |
| 4 | `SHTN_PDNO` | 단축상품번호 | string | Y | 12 | 종목번호<br>선물 6자리 (예: A01603)<br>옵션 9자리 (예: B01603955) |
| 5 | `ORD_QTY` | 주문수량 | string | Y | 10 |  |
| 6 | `UNIT_PRICE` | 주문가격1 | string | Y | 23 | 시장가나 최유리 지정가인 경우 0으로 입력 |
| 7 | `NMPR_TYPE_CD` | 호가유형코드 | string | N | 2 | ※ ORD_DVSN_CD(주문구분코드)를 입력한 경우 ""(공란)으로 입력해도 됨<br>01 : 지정가<br>02 : 시장가 <br>03 : 조건부<br>04 : 최유리 |
| 8 | `KRX_NMPR_CNDT_CD` | 한국거래소호가조건코드 | string | N | 1 | ※ ORD_DVSN_CD(주문구분코드)를 입력한 경우 ""(공란)으로 입력해도 됨<br>0 : 없음<br>3 : IOC<br>4 : FOK |
| 9 | `CTAC_TLNO` | 연락전화번호 | string | N | 20 | 고객의 연락 가능한 전화번호 |
| 10 | `FUOP_ITEM_DVSN_CD` | 선물옵션종목구분코드 | string | N | 2 | 공란(Default) |
| 11 | `ORD_DVSN_CD` | 주문구분코드 | string | Y | 2 | 01 : 지정가<br>02 : 시장가<br>03 : 조건부<br>04 : 최유리,<br>10 : 지정가(IOC)<br>11 : 지정가(FOK)<br>12 : 시장가(IOC)<br>13 : 시장가(FOK)<br>14 : 최유리(IOC)<br>15 : 최유리(FOK) |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | array | Y |  |  |
| 4 | `ACNT_NAME` | 계좌명 | string | Y | 60 | 계좌의 고객명 |
| 5 | `TRAD_DVSN_NAME` | 매매구분명 | string | Y | 60 | 매도/매수 등 구분값 |
| 6 | `ITEM_NAME` | 종목명 | string | Y | 60 | 주문 종목 명칭 |
| 7 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문 접수 시간 |
| 8 | `ORD_GNO_BRNO` | 주문채번지점번호 | string | Y | 5 | 계좌 개설 시 관리점으로 선택한 영업점의 고유번호 |
| 9 | `ODNO` | 주문번호 | string | Y | 10 | 접수한 주문의 일련번호 |

<details><summary>Request Example (Python)</summary>

```json
{
	"ORD_PRCS_DVSN_CD":"02",
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",           
	"SLL_BUY_DVSN_CD":"02",
	"SHTN_PDNO":"167R12",
	"ORD_QTY":"1",
	"UNIT_PRICE":"123",
	"NMPR_TYPE_CD":"",
	"KRX_NMPR_CNDT_CD":"",
	"CTAC_TLNO":"",
	"FUOP_ITEM_DVSN_CD":"",
	"ORD_DVSN_CD":"01"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "rt_cd": "0",
  "msg_cd": "APBK0029",
  "msg1": "주문전송이 정상적으로 처리되었습니다.",
  "output": {
    "ACNT_NAME": "류민수",
    "TRAD_DVSN_NAME": "매도",
    "ITEM_NAME": "코스피200 F 202203",
    "ORD_TMD": "131604",
    "ORD_GNO_BRNO": "06010",
    "ODNO": "0000007045"
  }
}
```

</details>



### 선물옵션 잔고평가손익내역

- **API ID**: v1_국내선물-015
- **실전 TR_ID**: CTFO6159R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance-valuation-pl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 잔고평가손익내역 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTFO6159R |
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
| 2 | `MGNA_DVSN` | 증거금구분 | string | Y | 2 | 01 : 개시, 02 : 유지 |
| 3 | `EXCC_STAT_CD` | 정산상태코드 | string | Y | 1 | 1 : 정산 (정산가격으로 잔고 조회)<br>2 : 본정산 (매입가격으로 잔고 조회) |
| 4 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 연속조회검색조건200 |
| 5 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 연속조회키200 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (50)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object | Y |  |  |
| 4 | `dnca_cash` | 예수금현금 | string | Y | 19 |  |
| 5 | `frcr_dncl_amt` | 외화예수금액 | string | Y | 19 |  |
| 6 | `dnca_sbst` | 예수금대용 | string | Y | 19 |  |
| 7 | `tot_dncl_amt` | 총예수금액 | string | Y | 19 |  |
| 8 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 |  |
| 9 | `cash_mgna` | 현금증거금 | string | Y | 19 |  |
| 10 | `sbst_mgna` | 대용증거금 | string | Y | 19 |  |
| 11 | `mgna_tota` | 증거금총액 | string | Y | 19 |  |
| 12 | `opt_dfpa` | 옵션차금 | string | Y | 19 |  |
| 13 | `thdt_dfpa` | 당일차금 | string | Y | 19 |  |
| 14 | `rnwl_dfpa` | 갱신차금 | string | Y | 19 |  |
| 15 | `fee` | 수수료 | string | Y | 19 |  |
| 16 | `nxdy_dnca` | 익일예수금 | string | Y | 19 |  |
| 17 | `nxdy_dncl_amt` | 익일예수금액 | string | Y | 19 |  |
| 18 | `prsm_dpast` | 추정예탁자산 | string | Y | 19 |  |
| 19 | `prsm_dpast_amt` | 추정예탁자산금액 | string | Y | 19 |  |
| 20 | `pprt_ord_psbl_cash` | 적정주문가능현금 | string | Y | 19 |  |
| 21 | `add_mgna_cash` | 추가증거금현금 | string | Y | 19 |  |
| 22 | `add_mgna_tota` | 추가증거금총액 | string | Y | 19 |  |
| 23 | `futr_trad_pfls_amt` | 선물매매손익금액 | string | Y | 19 |  |
| 24 | `opt_trad_pfls_amt` | 옵션매매손익금액 | string | Y | 19 |  |
| 25 | `futr_evlu_pfls_amt` | 선물평가손익금액 | string | Y | 19 |  |
| 26 | `opt_evlu_pfls_amt` | 옵션평가손익금액 | string | Y | 19 |  |
| 27 | `trad_pfls_amt_smtl` | 매매손익금액합계 | string | Y | 19 |  |
| 28 | `evlu_pfls_amt_smtl` | 평가손익금액합계 | string | Y | 19 |  |
| 29 | `wdrw_psbl_tot_amt` | 인출가능총금액 | string | Y | 19 |  |
| 30 | `ord_psbl_cash` | 주문가능현금 | string | Y | 19 |  |
| 31 | `ord_psbl_sbst` | 주문가능대용 | string | Y | 19 |  |
| 32 | `ord_psbl_tota` | 주문가능총액 | string | Y | 19 |  |
| 33 | `output1` | 응답상세2 | array | Y |  | array |
| 34 | `cano` | 종합계좌번호 | string | Y | 8 |  |
| 35 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 |  |
| 36 | `pdno` | 상품번호 | string | Y | 12 |  |
| 37 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 38 | `shtn_pdno` | 단축상품번호 | string | Y | 12 |  |
| 39 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 40 | `sll_buy_dvsn_name` | 매도매수구분명 | string | Y | 4 |  |
| 41 | `cblc_qty1` | 잔고수량1 | string | Y | 10 |  |
| 42 | `excc_unpr` | 정산단가 | string | Y | 24 |  |
| 43 | `ccld_avg_unpr1` | 체결평균단가1 | string | Y | 24 |  |
| 44 | `idx_clpr` | 지수종가 | string | Y | 24 |  |
| 45 | `pchs_amt` | 매입금액 | string | Y | 19 |  |
| 46 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 47 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |
| 48 | `trad_pfls_amt` | 매매손익금액 | string | Y | 19 |  |
| 49 | `lqd_psbl_qty` | 청산가능수량 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"MGNA_DVSN":"02",
	"EXCC_STAT_CD":"1",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "12345678!^03!^02!^1                                                                                                                                                                                     ",
    "ctx_area_nk200": " !^ !^ !^                                                                                                                                                                                               ",
    "output1": [
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101T90003",
            "prdt_type_cd": "301",
            "shtn_pdno": "101T09",
            "prdt_name": "F 202309",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "2",
            "excc_unpr": "340.30000000",
            "ccld_avg_unpr1": "345.50000000",
            "idx_clpr": "0.00000000",
            "pchs_amt": "170150000",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "2"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4101TC0008",
            "prdt_type_cd": "301",
            "shtn_pdno": "101T12",
            "prdt_name": "F 202312",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "5",
            "excc_unpr": "350.00000000",
            "ccld_avg_unpr1": "335.50000000",
            "idx_clpr": "353.35000000",
            "pchs_amt": "437500000",
            "evlu_amt": "441687500",
            "evlu_pfls_amt": "4187500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "5"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4175TA0001",
            "prdt_type_cd": "301",
            "shtn_pdno": "175T10",
            "prdt_name": "미국달러 F 202310",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "1",
            "excc_unpr": "1349.20000000",
            "ccld_avg_unpr1": "1338.60000000",
            "idx_clpr": "0.00000000",
            "pchs_amt": "13492000",
            "evlu_amt": "0",
            "evlu_pfls_amt": "0",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "1"
        },
        {
            "cano": "12345678",
            "acnt_prdt_cd": "03",
            "pdno": "KR4201TA3409",
            "prdt_type_cd": "301",
            "shtn_pdno": "201T10340",
            "prdt_name": "C 202310 340.0",
            "sll_buy_dvsn_name": "매수",
            "cblc_qty1": "1",
            "excc_unpr": "2.80000000",
            "ccld_avg_unpr1": "2.80000000",
            "idx_clpr": "0.01000000",
            "pchs_amt": "700000",
            "evlu_amt": "2500",
            "evlu_pfls_amt": "-697500",
            "trad_pfls_amt": "0",
            "lqd_psbl_qty": "1"
        }
    ],
    "output2": {
        "dnca_cash": "100000000",
        "frcr_dncl_amt": "0",
        "dnca_sbst": "0",
        "tot_dncl_amt": "100000000",
        "tot_ccld_amt": "0",
        "cash_mgna": "0",
        "sbst_mgna": "23910150",
        "mgna_tota": "23910150",
        "opt_dfpa": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "-30138000",
        "fee": "0",
        "nxdy_dnca": "69862000",
        "nxdy_dncl_amt": "69862000",
        "prsm_dpast": "69864500",
        "prsm_dpast_amt": "69864500",
        "pprt_ord_psbl_cash": "64184775",
        "add_mgna_cash": "0",
        "add_mgna_tota": "0",
        "futr_trad_pfls_amt": "0",
        "opt_trad_pfls_amt": "0",
        "futr_evlu_pfls_amt": "4187500",
        "opt_evlu_pfls_amt": "-697500",
        "trad_pfls_amt_smtl": "0",
        "evlu_pfls_amt_smtl": "3490000",
        "wdrw_psbl_tot_amt": "34046775",
        "ord_psbl_cash": "64184775",
        "ord_psbl_sbst": "0",
        "ord_psbl_tota": "64184775"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 선물옵션 증거금률

- **API ID**: 선물옵션 증거금률
- **실전 TR_ID**: TTTO6032R
- **모의 TR_ID**: 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/margin-rate`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
※ 승수, 계약당 선물 증거금은 최근월물 기준으로 표기되며, 월물에 따라 상이할 수 있습니다.
※ 계약당 선물 증거금은 선물 1계약 기준 신규 주문증거금이며 스프레드 증거금은 조회되지 않습니다.
※ 2023.05.24일부터 조회 가능하며, 익영업일 기준 증거금은 17:00~18:00시에 조회됩니다.
※ 데이터는 하루에 한 번 고정된 이후 데이터 변동이 없으므로  조회가 제한되는 점 이용에 참고 부탁드립니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 40 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | TTTO6032R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회 <br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 필수] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `BASS_DT` | 기준일자 | string | Y | 8 | 날짜 입력) ex) 20260313 |
| 1 | `BAST_ID` | 기초자산ID | string | Y | 20 | 공백 입력 |
| 2 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 다음 조회 시 필요, 입력 후 header tr_cont : N 설정 필수 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회 <br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 필수] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | Array |
| 4 | `bast_id` | 기초자산ID | string | Y | 20 |  |
| 5 | `bast_name` | 기초자산명 | string | Y | 60 |  |
| 6 | `brkg_mgna_rt` | 위탁증거금율 | string | Y | 23 | 소수점 8자리까지 표현 |
| 7 | `tr_mgna_rt` | 거래증거금율 | string | Y | 23 | 소수점 8자리까지 표현 |
| 8 | `bast_pric` | 기초자산가격 | string | Y | 18 | 소수점 8자리까지 표현 |
| 9 | `tr_mtpl_idx` | 거래승수지수 | string | Y | 18 | 소수점 8자리까지 표현 |
| 10 | `ctrt_per_futr_mgna` | 계약당선물증거금 | string | Y | 18 | 소수점 8자리까지 표현 |


### 선물옵션 정정취소주문

- **API ID**: v1_국내선물-002
- **실전 TR_ID**: (주간 정정/취소) TTTO1103U (야간 정정/취소) (구) JTCE1002U (신) STTN1103U
- **모의 TR_ID**: (주간 정정/취소) VTTO1103U (야간은 모의투자 미제공)
- **통신방식**: REST · **Method**: POST
- **URL**: `/uapi/domestic-futureoption/v1/trading/order-rvsecncl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 주문 건에 대하여 정정 및 취소하는 API입니다. 단, 이미 체결된 건은 정정 및 취소가 불가합니다.

※ POST API의 경우 BODY값의 key값들을 대문자로 작성하셔야 합니다.
   (EX. "CANO" : "12345678", "ACNT_PRDT_CD": "01",...)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자]<br>TTTO1103U : 선물 옵션 정정 취소 주문 주간<br>(신) STTN1103U : 선물 옵션 정정 취소 주문 야간 <br>[모의투자]<br>VTTO1103U : 선물 옵션 정정 취소 주문 주간 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Body (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `ORD_PRCS_DVSN_CD` | 주문처리구분코드 | string | Y | 2 | 02 : 주문전송 |
| 1 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 2 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 3 | `RVSE_CNCL_DVSN_CD` | 정정취소구분코드 | string | Y | 2 | 01 : 정정<br>02 : 취소 |
| 4 | `ORGN_ODNO` | 원주문번호 | string | Y | 10 | 정정 혹은 취소할 주문의 번호 |
| 5 | `ORD_QTY` | 주문수량 | string | Y | 10 | [Header tr_id TTTO1103U(선물옵션 정정취소 주간)]<br>전량일경우 0으로 입력<br>[Header tr_id JTCE1002U(선물옵션 정정취소 야간)]<br>일부수량 정정 및 취소 불가, 주문수량 반드시 입력 (공백 불가)<br>일부 미체결 시 잔량 전체에 대해서 취소 가능<br>EX) 2개 매수주문 후 1개 체결, 1개 미체결인 상태에서 취소주문 시 ORD_QTY는 1로 입력<br>※ 모의계좌의 경우, 주문수량 반드시 입력 (공백 불가) |
| 6 | `UNIT_PRICE` | 주문가격1 | string | Y | 23 | 시장가나 최유리의 경우 0으로 입력 (취소 시에도 0 입력) |
| 7 | `NMPR_TYPE_CD` | 호가유형코드 | string | Y | 2 | 01 : 지정가<br>02 : 시장가<br>03 : 조건부<br>04 : 최유리 |
| 8 | `KRX_NMPR_CNDT_CD` | 한국거래소호가조건코드 | string | Y | 1 | 취소시 0으로 입력<br>정정시<br>0 : 없음<br>3 : IOC<br>4 : FOK |
| 9 | `RMN_QTY_YN` | 잔여수량여부 | string | Y | 1 | Y : 전량<br>N : 일부 |
| 10 | `FUOP_ITEM_DVSN_CD` | 선물옵션종목구분코드 | string | N | 2 | [Header tr_id TTTO1103U(선물옵션 정정취소 주간)]<br>공란(Default)<br>[Header tr_id JTCE1002U(선물옵션 정정취소 야간)]<br>01 : 선물<br>02 : 콜옵션<br>03 : 풋옵션<br>04 : 스프레드 |
| 11 | `ORD_DVSN_CD` | 주문구분코드 | string | Y | 2 | [정정]<br>01 : 지정가<br>02 : 시장가<br>03 : 조건부<br>04 : 최유리,<br>10 : 지정가(IOC)<br>11 : 지정가(FOK)<br>12 : 시장가(IOC)<br>13 : 시장가(FOK)<br>14 : 최유리(IOC)<br>15 : 최유리(FOK)<br>[취소]<br>01 로 입력 |

#### Response Header (1)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | array | Y |  |  |
| 4 | `ACNT_NAME` | 계좌명 | string | Y | 60 | 계좌의 고객명 |
| 5 | `TRAD_DVSN_NAME` | 매매구분명 | string | Y | 60 | 매도/매수 등 구분값 |
| 6 | `ITEM_NAME` | 종목명 | string | Y | 60 | 주문 종목 명칭 |
| 7 | `ORD_TMD` | 주문시각 | string | Y | 6 | 주문 접수 시간 |
| 8 | `ORD_GNO_BRNO` | 주문채번지점번호 | string | Y | 5 | 계좌 개설 시 관리점으로 선택한 영업점의 고유번호 |
| 9 | `ORGN_ODNO` | 원주문번호 | string | Y | 10 | 정정 또는 취소 대상 주문의 일련번호 |
| 10 | `ODNO` | 주문번호 | string | Y | 10 | 접수한 주문(정정 또는 취소)의 일련번호 |

<details><summary>Request Example (Python)</summary>

```json
{
    "ORD_PRCS_DVSN_CD": "02",
    "CANO": "810XXXXX",
    "ACNT_PRDT_CD": "03",
    "RVSE_CNCL_DVSN_CD": "02",
    "ORGN_ODNO": "0000005605",
    "ORD_QTY": "1",
    "UNIT_PRICE": "460.00",
    "NMPR_TYPE_CD": "",
    "KRX_NMPR_CNDT_CD": "",
    "RMN_QTY_YN": "N",
    "CTAC_TLNO": "000 00000000",
    "FUOP_ITEM_DVSN_CD": "",
    "ORD_DVSN_CD": "01"
}
```

</details>



### 선물옵션 주문체결내역조회

- **API ID**: v1_국내선물-003
- **실전 TR_ID**: TTTO5201R
- **모의 TR_ID**: VTTO5201R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 주문체결내역조회 API입니다. 한 번의 호출에 최대 100건​까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자] <br>TTTO5201R : 선물 옵션 주문 체결 내역 조회<br>[모의투자] <br>VTTO5201R : 선물 옵션 주문 체결 내역 조회 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
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
| 2 | `STRT_ORD_DT` | 시작주문일자 | string | Y | 8 | 주문내역 조회 시작 일자, YYYYMMDD |
| 3 | `END_ORD_DT` | 종료주문일자 | string | Y | 8 | 주문내역 조회 마지막 일자, YYYYMMDD |
| 4 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 00 : 전체<br>01 : 매도<br>02 : 매수 |
| 5 | `CCLD_NCCS_DVSN` | 체결미체결구분 | string | Y | 2 | 00 : 전체<br>01 : 체결<br>02 : 미체결 |
| 6 | `SORT_SQN` | 정렬순서 | string | Y | 2 | AS : 정순<br>DS : 역순 |
| 7 | `STRT_ODNO` | 시작주문번호 | string | Y | 10 | 조회 시작 번호 입력 |
| 8 | `PDNO` | 상품번호 | string | Y | 12 | 공란 시, 전체  조회<br>선물 6자리 (예: 101S03)<br>옵션 9자리 (예: 201S03370) |
| 9 | `MKET_ID_CD` | 시장ID코드 | string | Y | 3 | 공란(Default) |
| 10 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 11 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (39)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `ctx_area_fk200` | 연속조회검색조건200 | string | Y | 200 |  |
| 4 | `ctx_area_nk200` | 연속조회키200 | string | Y | 200 |  |
| 5 | `output1` | 응답상세1 | array | Y |  |  |
| 6 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 | 계좌 개설 시 관리점으로 선택한 영업점의 고유번호 |
| 7 | `cano` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 8 | `csac_name` | 종합계좌명 | string | Y | 60 | 계좌의 고객명 |
| 9 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 10 | `ord_dt` | 주문일자 | string | Y | 8 | 주문의 접수일자 |
| 11 | `odno` | 주문번호 | string | Y | 10 | 접수한 주문의 일련번호 |
| 12 | `orgn_odno` | 원주문번호 | string | Y | 10 | 정정 또는 취소 대상 주문의 일련번호 |
| 13 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 | 00 : 전체 <br>01 : 매도 <br>02 : 매수 |
| 14 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 | 매도/매수 등 구분값 |
| 15 | `nmpr_type_cd` | 호가유형코드 | string | Y | 2 | 01 : 지정가<br>02 : 시장가<br>03 : 조건부<br>04 : 최유리 |
| 16 | `nmpr_type_name` | 호가유형명 | string | Y | 60 | 호가 유형의 명칭 |
| 17 | `pdno` | 상품번호 | string | Y | 12 | 선물옵션종목코드 |
| 18 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 19 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 20 | `ord_qty` | 주문수량 | string | Y | 10 | 주문 수량 |
| 21 | `ord_idx` | 주문지수 | string | Y | 24 | 주문 가격 |
| 22 | `qty` | 잔량 | string | Y | 10 | 주문 체결되지 않고 남은 수량 |
| 23 | `ord_tmd` | 주문시각 | string | Y | 6 | 주문 접수 시간 |
| 24 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 | 주문 체결된 수량 |
| 25 | `avg_idx` | 평균지수 | string | Y | 27 | 체결된 주문 수량의 평균 체결 가격 |
| 26 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 | 체결된 주문의 합계금액 |
| 27 | `rjct_qty` | 거부수량 | string | Y | 10 | 접수된 주문이 정상 처리되지 못하고 거부된 수량 |
| 28 | `ingr_trad_rjct_rson_cd` | 장내매매거부사유코드 | string | Y | 5 | 정상 처리되지 못하고 거부된 주문의 사유코드 |
| 29 | `ingr_trad_rjct_rson_name` | 장내매매거부사유명 | string | Y | 60 | 정상 처리되지 못하고 거부된 주문의 사유 |
| 30 | `ord_stfno` | 주문직원번호 | string | Y | 6 | 주문 접수한 직원의 사번 또는 온라인 주문 시 매체 유형코드 |
| 31 | `sprd_item_yn` | 스프레드종목여부 | string | Y | 1 | 스프레드 종목 여부 구분값 |
| 32 | `ord_ip_addr` | 주문IP주소 | string | Y | 200 | 주문 시 사용한 매체의 IP 주소 |
| 33 | `output2` | 응답상세2 | object | Y |  |  |
| 34 | `tot_ord_qty` | 총주문수량 | string | Y | 10 | 전체 주문 수량 |
| 35 | `tot_ccld_amt_smtl` | 총체결금액합계 | string | Y | 19 | 체결된 주문 전체의 합계 금액 |
| 36 | `tot_ccld_qty_smtl` | 총체결수량합계 | string | Y | 19 | 체결된 주문 전체의 합계 수량 |
| 37 | `fee_smtl` | 수수료합계 | string | Y | 19 | 체결된 주문에 대한 매매수수료의 합계 금액 |
| 38 | `ctac_tlno` | 연락전화번호 | string | Y | 20 | 고객의 연락 가능한 전화번호 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",
	"STRT_ORD_DT": "20211122",
	"END_ORD_DT": "20211122",
	"SLL_BUY_DVSN_CD": "00",
	"CCLD_NCCS_DVSN": "00",
	"SORT_SQN": "DS",
	"STRT_ODNO": "",
	"PDNO": "",
	"MKET_ID_CD": "00",
	"CTX_AREA_FK200": "",
	"CTX_AREA_NK200": ""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "ctx_area_fk200": "81055689^03^20220101^20220114^DS^                                                                                                                                                                       ",
  "ctx_area_nk200": "                                                                                                                                                                                                        ",
  "output1": [
    {
      "ord_gno_brno": "06010",
      "cano": "810XXXXX",
      "csac_name": "",
      "acnt_prdt_cd": "03",
      "ord_dt": "20220113",
      "odno": "0000007045",
      "orgn_odno": "0000000000",
      "sll_buy_dvsn_cd": "01",
      "trad_dvsn_name": "HTS SELL",
      "nmpr_type_cd": "01",
      "nmpr_type_name": "Limit Order",
      "pdno": "101S03",
      "prdt_name": "F 202203",
      "prdt_type_cd": "301",
      "ord_qty": "1",
      "ord_idx": "400.00",
      "qty": "0",
      "ord_tmd": "131604",
      "tot_ccld_qty": "1",
      "avg_idx": "400.00000000",
      "tot_ccld_amt": "100000000",
      "rjct_qty": "0",
      "ingr_trad_rjct_rson_cd": "00000",
      "ingr_trad_rjct_rson_name": "NORMAL",
      "ord_stfno": "Nsmart",
      "sprd_item_yn": "N",
      "ord_ip_addr": "P01032651641"
    },
    {
      "ord_gno_brno": "06010",
      "cano": "810XXXXX",
      "csac_name": "",
      "acnt_prdt_cd": "03",
      "ord_dt": "20220111",
      "odno": "0000007006",
      "orgn_odno": "0000007004",
      "sll_buy_dvsn_cd": "01",
      "trad_dvsn_name": "CANCEL CONFIRM",
      "nmpr_type_cd": "01",
      "nmpr_type_name": "Limit Order",
      "pdno": "101S03",
      "prdt_name": "F 202203",
      "prdt_type_cd": "301",
      "ord_qty": "1",
      "ord_idx": "0.00",
      "qty": "0",
      "ord_tmd": "150233",
      "tot_ccld_qty": "0",
      "avg_idx": "0.00000000",
      "tot_ccld_amt": "0",
      "rjct_qty": "0",
      "ingr_trad_rjct_rson_cd": "00000",
      "ingr_trad_rjct_rson_name": "NORMAL",
      "ord_stfno": "Nsmart",
      "sprd_item_yn": "N",
      "ord_ip_addr": "P01032651641"
    }
  ],
  "output2": {
    "tot_ord_qty": "4",
    "tot_ccld_amt_smtl": "200000000",
    "tot_ccld_qty_smtl": "2",
    "fee_smtl": "28570",
    "ctac_tlno": "01047859775"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### (야간)선물옵션 주문체결 내역조회

- **API ID**: 국내선물-009
- **실전 TR_ID**: (구) JTCE5005R (신) STTN5201R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(야간)선물옵션 주문체결 내역조회 API입니다.

1. 야간 시장이 종료(06:00)된 이후 약 06:10경 야간시장의 주문체결내역이 주간으로 이관됩니다.
      &gt; 주간 API를 사용한다면 야간 장 중 주문체결내역을 실시간으로 조회할 수 없습니다.
      &gt; 주문체결내역의 이관이 완료되는 시점부터 주간 테이블에서 야간의 주문체결내역을 조회할 수 있습니다.

2. KRX야간시장의 경우 주문일자는 (T+1)일 입니다.
      &gt; 금요일의 경우 주문일자는 주말 및 공휴일을 제외하고 익 영업일인 월요일로 설정됩니다.
      &gt; 위 내용은 당사의 기준이 아닌 KRX 거래소의 기준으로 전 회원사 동일한 기준으로 주문체결이 이루어지고 있습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | (구) JTCE5005R (신) STTN5201R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `STRT_ORD_DT` | 시작주문일자 | string | Y | 8 |  |
| 3 | `END_ORD_DT` | 종료주문일자 | string | Y | 8 | 조회하려는 마지막 일자 다음일자로 조회<br>(ex. 20221011 까지의 내역을 조회하고자 할 경우, <br>20221012로 종료주문일자 설정) |
| 4 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 공란 : default (00: 전체 ,01 : 매도, 02 : 매수) |
| 5 | `CCLD_NCCS_DVSN` | 체결미체결구분 | string | Y | 2 | 00 : 전체<br>01 : 체결<br>02 : 미체결 |
| 6 | `SORT_SQN` | 정렬순서 | string | Y | 2 | 공란 : default (DS : 정순, 그외 : 역순) |
| 7 | `STRT_ODNO` | 시작주문번호 | string | Y | 10 | 공란 : default |
| 8 | `PDNO` | 상품번호 | string | Y | 12 | 공란 : default |
| 9 | `MKET_ID_CD` | 시장ID코드 | string | Y | 3 | 공란 : default |
| 10 | `FUOP_DVSN_CD` | 선물옵션구분코드 | string | Y | 2 | 공란 : 전체, 01 : 선물, 02 : 옵션 |
| 11 | `SCRN_DVSN` | 화면구분 | string | Y | 2 | 02(Default) |
| 12 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_FK200값 : 다음페이지 조회시(2번째부터) |
| 13 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 공란 : 최초 조회시<br>이전 조회 Output CTX_AREA_NK200값 : 다음페이지 조회시(2번째부터) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (38)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세1 | object | Y |  |  |
| 4 | `tot_ord_qty` | 총주문수량 | string | Y | 10 |  |
| 5 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 |  |
| 6 | `tot_ccld_qty_SMTL` | 총체결수량 | string | Y | 19 | 신규 TR 사용 필드 |
| 7 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 |  |
| 8 | `tot_ccld_amt_SMTL` | 총체결금액 | string | Y | 11 | 신규 TR 사용 필드 |
| 9 | `fee` | 수수료 | string | Y | 19 |  |
| 10 | `ctac_tlno` | 연락전화번호 | string | Y | 20 | 신규 TR 사용 필드 |
| 11 | `output1` | 응답상세2 | object array | Y |  | 시간별체결 정보 |
| 12 | `ord_gno_brno` | 주문채번지점번호 | string | Y | 5 |  |
| 13 | `cano` | 종합계좌번호 | string | Y | 8 |  |
| 14 | `csac_name` | 종합계좌명 | string | Y | 60 |  |
| 15 | `acnt_prdt_cd` | 계좌상품코드 | string | Y | 2 |  |
| 16 | `ord_dt` | 주문일자 | string | Y | 8 |  |
| 17 | `odno` | 주문번호 | string | Y | 10 |  |
| 18 | `orgn_odno` | 원주문번호 | string | Y | 10 |  |
| 19 | `sll_buy_dvsn_cd` | 매도매수구분코드 | string | Y | 2 |  |
| 20 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 21 | `nmpr_type_name` | 호가유형명 | string | Y | 60 |  |
| 22 | `pdno` | 상품번호 | string | Y | 12 |  |
| 23 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 24 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 25 | `ord_qty` | 주문수량 | string | Y | 10 |  |
| 26 | `ord_idx4` | 주문지수 | string | Y | 20 | 신규 TR 사용 필드 |
| 27 | `qty` | 잔량 | string | Y | 10 |  |
| 28 | `ord_tmd` | 주문시각 | string | Y | 6 |  |
| 29 | `tot_ccld_qty` | 총체결수량 | string | Y | 10 |  |
| 30 | `avg_idx` | 평균지수 | string | Y | 19 |  |
| 31 | `tot_ccld_amt` | 총체결금액 | string | Y | 19 |  |
| 32 | `rjct_qty` | 거부수량 | string | Y | 10 |  |
| 33 | `ingr_trad_rjct_rson_cd` | 장내매매거부사유코드 | string | Y | 5 |  |
| 34 | `ingr_trad_rjct_rson_name` | 장내매매거부사유명 | string | Y | 60 |  |
| 35 | `ord_stfno` | 주문직원번호 | string | Y | 6 |  |
| 36 | `sprd_item_yn` | 스프레드종목여부 | string | Y | 1 |  |
| 37 | `ord_ip_addr` | 주문IP주소 | string | Y | 200 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"STRT_ORD_DT":"20220730",
	"END_ORD_DT":"20221214",
	"SLL_BUY_DVSN_CD":"00",
	"CCLD_NCCS_DVSN":"00",
	"SORT_SQN":"DS",
	"STRT_ODNO":"",
	"PDNO":"",
	"MKET_ID_CD":"00",
	"FUOP_DVSN_CD":"",
	"SCRN_DVSN":"00",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "81012345^03^20221214^20221214^DS^                                                                                                                                                                       ",
    "ctx_area_nk200": "                                                                                                                                                                                                        ",
    "output1": [],
    "output2": {
        "tot_ord_qty": "0",
        "tot_ccld_qty": "0",
        "tot_ccld_amt": "0",
        "fee": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0560",
    "msg1": "조회할 내용이 없습니다                                                          "
}
```

</details>



### (야간)선물옵션 주문가능 조회

- **API ID**: 국내선물-011
- **실전 TR_ID**: (구) JTCE1004R (신) STTN5105R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
(야간)선물옵션 주문가능 조회 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | (구) JTCE1004R (신) STTN5105R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
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
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 |  |
| 2 | `PDNO` | 상품번호 | string | Y | 12 |  |
| 3 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | 301 : 선물옵션 |
| 4 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | Y | 2 | 01 : 매도 , 02 : 매수 |
| 5 | `UNIT_PRICE` | 주문가격1 | string | Y | 23 |  |
| 6 | `ORD_DVSN_CD` | 주문구분코드 | string | Y | 2 | '01 : 지정가        02 : 시장가 <br>03 : 조건부        04 : 최유리, <br>10 : 지정가(IOC) 11 : 지정가(FOK) <br>12 : 시장가(IOC) 13 : 시장가(FOK) <br>14 : 최유리(IOC) 15 : 최유리(FOK)' |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세1 | object | Y |  |  |
| 4 | `max_ord_psbl_qty` | 최대주문가능수량 | string | Y | 19 | 최대주문가능수량 (신규 TR 미사용 필드) |
| 5 | `tot_psbl_qty` | 최대주문가능수량 | string | Y | 19 |  |
| 6 | `lqd_psbl_qty` | 청산가능수량 | string | Y | 19 | 청산가능수량 |
| 7 | `lqd_psbl_qty_1` | 청산가능수량 | string | Y | 19 | 신규 TR 사용 필드 |
| 8 | `ord_psbl_qty` | 주문가능수량 | string | Y | 19 |  |
| 9 | `bass_idx` | 기준지수 | string | Y | 23 | 신규 TR 사용 필드 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"80012345",
	"ACNT_PRDT_CD":"03",
	"PDNO":"101T03",
	"PRDT_TYPE_CD":"301",
	"SLL_BUY_DVSN_CD":"02",
	"UNIT_PRICE":"",
	"ORD_DVSN_CD":"01"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": {
        "max_ord_psbl_qty": "996",
        "lqd_psbl_qty": "0",
        "ord_psbl_qty": "996"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0510",
    "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 선물옵션 잔고정산손익내역

- **API ID**: v1_국내선물-013
- **실전 TR_ID**: CTFO6117R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-balance-settlement-pl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 잔고정산손익내역 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTFO6117R |
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
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `INQR_DT` | 조회일자 | string | Y | 8 | 조회일자(YYYYMMDD) |
| 3 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 연속조회검색조건200 |
| 4 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 연속조회키200 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (29)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output2` | 응답상세 | object | Y |  |  |
| 4 | `nxdy_dnca` | 익일예수금 | string | Y | 19 |  |
| 5 | `mmga_cash` | 유지증거금현금 | string | Y | 19 |  |
| 6 | `brkg_mgna_cash` | 위탁증거금현금 | string | Y | 19 |  |
| 7 | `opt_buy_chgs` | 옵션매수대금 | string | Y | 19 |  |
| 8 | `opt_lqd_evlu_amt` | 옵션청산평가금액 | string | Y | 19 |  |
| 9 | `dnca_sbst` | 예수금대용 | string | Y | 19 |  |
| 10 | `mmga_tota` | 유지증거금총액 | string | Y | 19 |  |
| 11 | `brkg_mgna_tota` | 위탁증거금총액 | string | Y | 19 |  |
| 12 | `opt_sll_chgs` | 옵션매도대금 | string | Y | 19 |  |
| 13 | `fee` | 수수료 | string | Y | 19 |  |
| 14 | `thdt_dfpa` | 당일차금 | string | Y | 19 |  |
| 15 | `rnwl_dfpa` | 갱신차금 | string | Y | 19 |  |
| 16 | `dnca_cash` | 예수금현금 | string | Y | 19 |  |
| 17 | `output1` | 응답상세2 | array | Y |  | array |
| 18 | `pdno` | 상품번호 | string | Y | 12 |  |
| 19 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 20 | `trad_dvsn_name` | 매매구분명 | string | Y | 60 |  |
| 21 | `bfdy_cblc_qty` | 전일잔고수량 | string | Y | 19 |  |
| 22 | `new_qty` | 신규수량 | string | Y | 10 |  |
| 23 | `mnpl_rpch_qty` | 전매환매수량 | string | Y | 10 |  |
| 24 | `cblc_qty` | 잔고수량 | string | Y | 19 |  |
| 25 | `cblc_amt` | 잔고금액 | string | Y | 19 |  |
| 26 | `trad_pfls_amt` | 매매손익금액 | string | Y | 19 |  |
| 27 | `evlu_amt` | 평가금액 | string | Y | 19 |  |
| 28 | `evlu_pfls_amt` | 평가손익금액 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"INQR_DT":"20230906",
	"CTX_AREA_FK200":"",
	"CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "12345678!^03!^20230906                                                                                                                                                                                  ",
    "ctx_area_nk200": " !^                                                                                                                                                                                                     ",
    "output1": [
        {
            "pdno": "101T09",
            "prdt_name": "F 202309",
            "trad_dvsn_name": "매수",
            "bfdy_cblc_qty": "2",
            "new_qty": "0",
            "mnpl_rpch_qty": "0",
            "cblc_qty": "2",
            "cblc_amt": "-425000",
            "trad_pfls_amt": "0",
            "evlu_amt": "149350000",
            "evlu_pfls_amt": "-1675000"
        }
    ],
    "output2": {
        "nxdy_dnca": "0",
        "mmga_cash": "0",
        "brkg_mgna_cash": "0",
        "opt_buy_chgs": "0",
        "opt_lqd_evlu_amt": "0",
        "dnca_sbst": "0",
        "mmga_tota": "0",
        "brkg_mgna_tota": "0",
        "opt_sll_chgs": "0",
        "fee": "0",
        "thdt_dfpa": "0",
        "rnwl_dfpa": "0",
        "dnca_cash": "0"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 선물옵션 주문가능

- **API ID**: v1_국내선물-005
- **실전 TR_ID**: TTTO5105R
- **모의 TR_ID**: VTTO5105R
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-psbl-order`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 주문가능 API입니다. 주문가능 내역과 수량을 확인하실 수 있습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access Token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Credentials Grant 절차를 준용) <br>제휴사(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전투자] <br>TTTO5105R : 선물 옵션 주문 가능<br>[모의투자] <br>VTTO5105R : 선물 옵션 주문 가능 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사 APP을 사용하는 경우 사용자(회원) 핸드폰번호<br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | 제휴사는 사용자(회원)의 IP Address 필수이며 일반고객은 제외 |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | N | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | N | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `PDNO` | 상품번호 | string | N | 12 | 선물옵션종목코드<br>선물 6자리 (예: 101S03)<br>옵션 9자리 (예: 201S03370) |
| 3 | `SLL_BUY_DVSN_CD` | 매도매수구분코드 | string | N | 2 | 01 : 매도<br>02 : 매수 |
| 4 | `UNIT_PRICE` | 주문가격1 | string | N | 23 | 주문가격<br>※ 주문가격 '0'일 경우<br> - 옵션매수 : 현재가<br> - 그 이외   : 기준가 |
| 5 | `ORD_DVSN_CD` | 주문구분코드 | string | N | 2 | 01 : 지정가<br>02 : 시장가<br>03 : 조건부<br>04 : 최유리,<br>10 : 지정가(IOC)<br>11 : 지정가(FOK)<br>12 : 시장가(IOC)<br>13 : 시장가(FOK)<br>14 : 최유리(IOC)<br>15 : 최유리(FOK) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output` | 응답상세 | array | Y |  |  |
| 4 | `tot_psbl_qty` | 총가능수량 | string | Y | 10 | 총가능수량 |
| 5 | `lqd_psbl_qty1` | 청산가능수량1 | string | Y | 10 | 청산가능수량 |
| 6 | `ord_psbl_qty` | 주문가능수량 | string | Y | 10 | 주문가능수량 |
| 7 | `bass_idx` | 기준지수 | string | Y | 32 | 기준지수 |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO": "810XXXXX",
	"ACNT_PRDT_CD":"03",
	"PDNO": "101R12",
	"SLL_BUY_DVSN_CD": "02",
	"UNIT_PRICE": "397.95",
	"ORD_DVSN_CD": "01"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output": {
    "tot_psbl_qty": "11679",
    "lqd_psbl_qty1": "0",
    "ord_psbl_qty": "11665",
    "bass_idx": "379.67000000"
  },
  "rt_cd": "0",
  "msg_cd": "KIOK0510",
  "msg1": "조회가 완료되었습니다                                                           "
}
```

</details>



### 선물옵션 기준일체결내역

- **API ID**: v1_국내선물-016
- **실전 TR_ID**: CTFO5139R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/trading/inquire-ccnl-bstime`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 기준일체결내역 API입니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTFO5139R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | 공백 : 초기 조회<br>N : 다음 데이터 조회 (output header의 tr_cont가 M일 경우) |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CANO` | 종합계좌번호 | string | Y | 8 | 계좌번호 체계(8-2)의 앞 8자리 |
| 1 | `ACNT_PRDT_CD` | 계좌상품코드 | string | Y | 2 | 계좌번호 체계(8-2)의 뒤 2자리 |
| 2 | `ORD_DT` | 주문일자 | string | Y | 8 | 주문일자(YYYYMMDD) |
| 3 | `FUOP_TR_STRT_TMD` | 선물옵션거래시작시각 | string | Y | 6 | 선물옵션거래시작시간(HHMMSS) |
| 4 | `FUOP_TR_END_TMD` | 선물옵션거래종료시각 | string | Y | 6 | 선물옵션거래종료시간(HHMMSS) |
| 5 | `CTX_AREA_FK200` | 연속조회검색조건200 | string | Y | 200 | 연속조회검색조건200 |
| 6 | `CTX_AREA_NK200` | 연속조회키200 | string | Y | 200 | 연속조회키200 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | F or M : 다음 데이터 있음<br>D or E : 마지막 데이터 |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | array | Y |  | array |
| 4 | `pdno` | 상품번호 | string | Y | 12 |  |
| 5 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 6 | `odno` | 주문번호 | string | Y | 10 |  |
| 7 | `tr_type_name` | 거래유형명 | string | Y | 60 |  |
| 8 | `last_sttldt` | 최종결제일 | string | Y | 8 |  |
| 9 | `ccld_idx` | 체결지수 | string | Y | 24 |  |
| 10 | `ccld_qty` | 체결량 | string | Y | 10 |  |
| 11 | `trad_amt` | 매매금액 | string | Y | 19 |  |
| 12 | `fee` | 수수료 | string | Y | 19 |  |
| 13 | `ccld_btwn` | 체결시간 | string | Y | 6 |  |
| 14 | `output2` | 응답상세2 | object | Y |  |  |
| 15 | `tot_ccld_qty_smtl` | 총체결수량합계 | string | Y | 19 |  |
| 16 | `tot_ccld_amt_smtl` | 총체결금액합계 | string | Y | 19 |  |
| 17 | `fee_adjt` | 수수료조정 | string | Y | 19 |  |
| 18 | `fee_smtl` | 수수료합계 | string | Y | 19 |  |

<details><summary>Request Example (Python)</summary>

```json
{
	"CANO":"12345678",
	"ACNT_PRDT_CD":"03",
	"ORD_DT":"20230920",
	"FUOP_TR_STRT_TMD":"000000",
	"FUOP_TR_END_TMD":"240000",
	"CTX_AREA_FK200":"",
	'CTX_AREA_NK200":""
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk200": "12345678!^03!^20230920!^000000!^240000                                                                                                                                                                  ",
    "ctx_area_nk200": " !^ !^ !^                                                                                                                                                                                               ",
    "output1": [
        {
            "pdno": "201T10340",
            "prdt_name": "코스피200 C 202310 340.0",
            "odno": "0000219602",
            "tr_type_name": "지수콜옵션매수",
            "last_sttldt": "20231012",
            "ccld_idx": "2.80000000",
            "ccld_qty": "1",
            "trad_amt": "700000",
            "fee": "2758",
            "ccld_btwn": "140144"
        },
        {
            "pdno": "101T12",
            "prdt_name": "코스피200 F 202312",
            "odno": "0000219606",
            "tr_type_name": "지수선물매수",
            "last_sttldt": "20231214",
            "ccld_idx": "335.50000000",
            "ccld_qty": "5",
            "trad_amt": "419375000",
            "fee": "41144",
            "ccld_btwn": "140121"
        }
    ],
    "output2": {
        "tot_ccld_qty_smtl": "6",
        "tot_ccld_amt_smtl": "420075000",
        "fee_adjt": "43902",
        "fee_smtl": "43890"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>


