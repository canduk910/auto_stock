# KIS OpenAPI 전체 레퍼런스

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`
> 총 API: 338개 (REST 278 + WebSocket 60) · 필드 14,746개 **전수 수록**
> 재생성 도구: 워크북 → `docs/kis/*.md` 자동 생성. 상세 명세는 손으로 고치지 않는다(목록 표의 `사용` 표시만 보존).
> **예외 = 아래 「제도 변경 공지 반영」 절에 열거한 항목.** 워크북보다 나중에 나온 공지라 자동 생성분에 없고, 손으로 넣었다. **재생성 시 이 절을 보고 다시 넣어야 한다.**

## 카테고리별 명세 파일

| 카테고리 | API 수 | 파일 |
|---------|:-----:|------|
| OAuth인증 | 3 | [oauth.md](oauth.md) |
| [국내주식] 주문/계좌 | 23 | [domestic-stock-order.md](domestic-stock-order.md) |
| [국내주식] 기본시세 | 22 | [domestic-stock-quote.md](domestic-stock-quote.md) |
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
| [rate-limits.md](rate-limits.md) | KIS API 호출 유량 정책 (2026-04-20 기준 REST 18건/초 + WS 41건) + 본 시스템 적용 현황 + 잠재 결함 3건 |

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

## 제도 변경 공지 반영 (워크북 이후 · 손으로 넣은 항목)

원본 워크북(`20260911`)에는 없고 KIS 공지에만 있는 내용이다. **`docs/kis/*.md` 를 재생성하면 사라지므로
아래 표를 보고 다시 넣는다.** 공지 원문의 요약이 아니라 원문 값을 그대로 옮긴 것이다.

### 공지 ① 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 — 시행 2026-09-14(월)

출처: <https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000001/post/26dfe350-eb72-48e5-8175-34eb27970f3e>

| 반영 파일 | 반영 위치 | 넣은 내용 |
|---|---|---|
| [domestic-stock-order.md](domestic-stock-order.md) | 주식주문(현금) · 주식주문(신용) · 주식주문(정정취소) 의 `ORD_DVSN` | KRX 애프터마켓 `41`~`47` 7종 + NXT 프리마켓 GTP `27`~`29` 3종. 애프터마켓은 정규장과 분리된 시장이라 호가유형 선택 필수 · **ETP 거래 불가** · **시장가 없음**. `07`(시간외 단일가)은 폐지로 무효 |
| [domestic-stock-order.md](domestic-stock-order.md) | 주식잔고조회 · 주식잔고조회_실현손익 의 `AFHR_FLPR_YN` | 값 의미 변경 — `N` KRX정규장종가 / `X` NXT / `Y` KRX+NXT 통합시세 |
| [domestic-stock-realtime.md](domestic-stock-realtime.md) | 실시간체결가 KRX(`H0STCNT0`) · 통합(`H0UNCNT0`) · NXT(`H0NXCNT0`) · 실시간호가 KRX(`H0STASP0`) | output `MARKET_CLS_CODE`(장 구분 코드) 신규 — `1`프리 `2`정규 `3`애프터 `5`종가 |
| [domestic-stock-realtime.md](domestic-stock-realtime.md) | 실시간호가 통합(`H0UNASP0`) | output `ANTC_EXCH_CLS_CODE`(예상체결 거래소구분) 신규 — `1`KRX `2`NXT |
| [domestic-stock-realtime.md](domestic-stock-realtime.md) | 시간외 실시간체결가(`H0STOUP0`) · 시간외 실시간호가(`H0STOAA0`) · 시간외 실시간예상체결(`H0STOAC0`) | 🔴 시간외단일가 폐지로 **대상 시장이 사라진다**는 주의문. 애프터마켓은 이 채널이 아니라 정규 채널로 온다 |
| [domestic-stock-realtime.md](domestic-stock-realtime.md) | 장운영정보 NXT(`H0NXMKO0`) | NXT 단일가 도입(정지 후 재개, 호가접수 30초) · VI 발동 시 단일가매매(2분) + 정적 VI 신규 · 프리마켓 GTP(08:50 일괄취소) |

**아직 공지에 없어 실측이 필요한 것** (2026-09-14 첫 장에서 확인)

| 미확인 항목 | 왜 중요한가 |
|---|---|
| `MARKET_CLS_CODE` · `ANTC_EXCH_CLS_CODE` 의 **payload 안 위치(index)** | 공지는 "추가됩니다" 만 밝혔다. 우리 핸들러는 파이프 구분 payload 를 **위치로** 파싱하므로, 중간에 끼면 뒤 필드가 전부 밀린다 |
| 시간외 전용 채널 3종이 실제로 폐지되는지 | 구독이 계속 ACK 되는지 · 프레임이 오는지 |
| 애프터마켓 주문 거부 시 `msg1` 원문 | 우리 폴백 분기(`is_market_order_disallowed` vs `is_market_closed_rejection`)가 어느 쪽으로 떨어지는지가 여기서 갈린다 |

## 도메인 정보

| 환경 | URL |
|------|-----|
| 실전 | `https://openapi.koreainvestment.com:9443` |
| 모의 | `https://openapivts.koreainvestment.com:29443` |