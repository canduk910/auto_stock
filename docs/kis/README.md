# KIS OpenAPI 전체 레퍼런스

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`
> 총 API: 338개 (REST + WebSocket)

## 카테고리별 명세 파일

| 카테고리 | API 수 | 파일 |
|---------|:-----:|------|
| OAuth인증 | 4 | [oauth.md](oauth.md) |
| [국내주식] 주문/계좌 | 23 | [domestic-stock-order.md](domestic-stock-order.md) |
| [국내주식] 기본시세 | 21 | [domestic-stock-quote.md](domestic-stock-quote.md) |
| [국내주식] ELW 시세 | 22 | [domestic-stock-elw.md](domestic-stock-elw.md) |
| [국내주식] 업종/기타 | 14 | [domestic-stock-industry.md](domestic-stock-industry.md) |
| [국내주식] 종목정보 | 26 | [domestic-stock-info.md](domestic-stock-info.md) |
| [국내주식] 시세분석 | 29 | [domestic-stock-analysis.md](domestic-stock-analysis.md) |
| [국내주식] 순위분석 | 22 | [domestic-stock-ranking.md](domestic-stock-ranking.md) |
| [국내주식] 실시간시세 | 29 | [domestic-stock-realtime.md](domestic-stock-realtime.md) |
| [국내선물옵션] 주문/계좌 | 15 | [futures-options-order.md](futures-options-order.md) |
| [국내선물옵션] 기본시세 | 9 | [futures-options-quote.md](futures-options-quote.md) |
| [국내선물옵션] 실시간시세 | 20 | [futures-options-realtime.md](futures-options-realtime.md) |
| [해외주식] 주문/계좌 | 18 | [overseas-stock-order.md](overseas-stock-order.md) |
| [해외주식] 기본시세 | 14 | [overseas-stock-quote.md](overseas-stock-quote.md) |
| [해외주식] 시세분석 | 15 | [overseas-stock-analysis.md](overseas-stock-analysis.md) |
| [해외주식] 실시간시세 | 4 | [overseas-stock-realtime.md](overseas-stock-realtime.md) |
| [해외선물옵션] 주문/계좌 | 11 | [overseas-futures-order.md](overseas-futures-order.md) |
| [해외선물옵션] 기본시세 | 20 | [overseas-futures-quote.md](overseas-futures-quote.md) |
| [해외선물옵션]실시간시세 | 4 | [overseas-futures-realtime.md](overseas-futures-realtime.md) |
| [장내채권] 주문/계좌 | 7 | [bond-order.md](bond-order.md) |
| [장내채권] 기본시세 | 8 | [bond-quote.md](bond-quote.md) |
| [장내채권] 실시간시세 | 3 | [bond-realtime.md](bond-realtime.md) |

## 운영 부속 문서

| 문서 | 설명 |
|------|------|
| [error-codes.md](error-codes.md) | KIS 오류 코드 통합 표 (EGW/OPSQ/OPSP + APBK 실측) + 거부 분류·후속 조치 매핑 |

## 프로젝트 사용 중 API

| TR_ID | API명 | 카테고리 | URL |
|-------|------|---------|-----|
| TTTC0013U | 주식주문(정정취소) | [국내주식] 주문/계좌 | `/uapi/domestic-stock/v1/trading/order-rvsecncl` |
| TTTC8434R | 주식잔고조회 | [국내주식] 주문/계좌 | `/uapi/domestic-stock/v1/trading/inquire-balance` |
| TTTC8908R | 매수가능조회 | [국내주식] 주문/계좌 | `/uapi/domestic-stock/v1/trading/inquire-psbl-order` |
| (매도) TTTC0011U (매수) TTTC0012U | 주식주문(현금) | [국내주식] 주문/계좌 | `/uapi/domestic-stock/v1/trading/order-cash` |
| H0STCNI0 | 국내주식 실시간체결통보 | [국내주식] 실시간시세 | `/tryitout/H0STCNI0` |
| CTFO6118R | 선물옵션 잔고현황 | [국내선물옵션] 주문/계좌 | `/uapi/domestic-futureoption/v1/trading/inquire-balance` |
| (주간 매수/매도) TTTO1101U (야간 매수/매도) (구) JTCE1001U (신) STTN1101U | 선물옵션 주문 | [국내선물옵션] 주문/계좌 | `/uapi/domestic-futureoption/v1/trading/order` |
| (주간 정정/취소) TTTO1103U (야간 정정/취소) (구) JTCE1002U (신) STTN1103U | 선물옵션 정정취소주문 | [국내선물옵션] 주문/계좌 | `/uapi/domestic-futureoption/v1/trading/order-rvsecncl` |
| TTTO5105R | 선물옵션 주문가능 | [국내선물옵션] 주문/계좌 | `/uapi/domestic-futureoption/v1/trading/inquire-psbl-order` |
| FHMIF10000000 | 선물옵션 시세 | [국내선물옵션] 기본시세 | `/uapi/domestic-futureoption/v1/quotations/inquire-price` |
| TTTS3012R | 해외주식 잔고 | [해외주식] 주문/계좌 | `/uapi/overseas-stock/v1/trading/inquire-balance` |
| CTRP6504R | 해외주식 체결기준현재잔고 | [해외주식] 주문/계좌 | `/uapi/overseas-stock/v1/trading/inquire-present-balance` |
| TTTS3007R | 해외주식 매수가능금액조회 | [해외주식] 주문/계좌 | `/uapi/overseas-stock/v1/trading/inquire-psamount` |
| TTTS3018R | 해외주식 미체결내역 | [해외주식] 주문/계좌 | `/uapi/overseas-stock/v1/trading/inquire-nccs` |

## 도메인 정보

| 환경 | URL |
|------|-----|
| 실전 | `https://openapi.koreainvestment.com:9443` |
| 모의 | `https://openapivts.koreainvestment.com:29443` |