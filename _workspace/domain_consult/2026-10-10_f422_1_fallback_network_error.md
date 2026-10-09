# F-422-1 — 지정가 재주문(폴백) 중 네트워크 오류: 「살아 있는 주문으로 보고 기다리기」 를 코드로

- 기준: HEAD `952f22d7` 의 코드를 읽기만 했다. 운영 DB·로그는 조회하지 않았다. 아래 「발생 빈도」 는 코드 분석이다.
- 읽은 자리: `order_engine.py` `execute_sell`(1790~2421) · `_handle_sell_market_disallowed`(2485~) · `_handle_sell_fill`(3215~ 주인 찾기) · `api/base.py::_request`(504~) · `scheduler.py` `_force_clear_main_only`(1954~2017)·`_scan_loop` 동기화(2518~)·`_sync_positions_from_balance`(3418~) · `selling_reconcile.py` · `buying_reconcile.py` 머리말 · `realtime/CLAUDE.md` 「접수 전문 기록」 · `risk.py:696~704`

## 질문 요약
폴백 `place_order` 가 `KisApiError` 가 아닌 예외를 내면 `execute_sell` 밖으로 나간다. 사용자는 「거부가 오지 않았으면 살아 있는 주문으로 보고 기다리고, 필요하면 주문내역을 조회해 확인하자」고 했다. 이 생각이 맞는지 판정하고, 코드로 옮긴 모양, 고칠 자리, 시나리오를 정한다.

## 트레이더 시각

### 1. 사용자 관점 판정 = **방향은 맞다. 다만 「기다린다」 에 시한과 확인 수단을 붙여야 완성된다**
- 맞는 부분: 주문 창에서 응답만 안 왔을 때 트레이더는 같은 주문을 다시 넣지 않는다. 주문내역 창부터 본다. 다시 넣으면 「두 장이 걸리는」 사고가 난다. cycle327 「주문이 나간 뒤 재발사 금지」 와 같은 원칙이다.
- 보완 ①: **「접수됐는지 모른다」 는 「접수됐다」 가 아니다.** 연결 단계에서 거부되면(`ConnectError`·`ConnectTimeout`) 주문은 서버에 닿지 않았다. 다만 `_request` 가 3번 재시도한 뒤의 **마지막 예외 종류만** 올라오므로, 마지막이 ConnectError 라도 앞선 시도가 ReadTimeout 이면 접수됐을 수 있다. 예외 종류로 접수 여부를 가를 수 없다. 그래서 반드시 조회로 확인한다.
- 보완 ②: 접수가 안 됐는데 계속 기다리면 **손절이 끝내 나가지 않는다.** 기다림에는 끝이 있어야 한다. 끝은 시간이 아니라 **증거**로 정한다. 「보유 > 0 이고 열린 매도 주문이 없다(나이 ≥ 180초)」 이면 접수되지 않았거나 이미 끝난 주문이다. 이때 `_selling` 을 풀고 다음 틱에서 손절을 다시 평가한다. 이 판정은 재발사가 아니라 새 발사다.
- 보완 ③: 「연결이 끊겼다가 재접속할 때」 — 주문(REST)은 요청마다 연결을 새로 맺는다. 웹소켓처럼 「재접속」 시점이 따로 없다. 그래서 조회 시점은 **「결과 모름이 생긴 순간부터 N초 뒤」** 로 잡는다. 웹소켓 재연결은 지금 예외가 퍼지면서 생기는 부작용일 뿐이고, 고치면 없어진다.

### 2. 「기다림」 이 기다리는 것 세 가지 — 주문번호를 몰라도 된다
| 신호 | 지금 코드 | 주문번호 없이 되나 |
|---|---|---|
| ① 체결통보(H0STCNI0, `CNTG_YN=2`) | `_handle_sell_fill` 이 매핑에 없는 주문을 trade_history → 보유자 1명(`_ticker_holders`) 순서로 찾고, 수량은 체결통보 `fields[16]`(`qty_src=payload`)으로 읽는다. 주문이 끝나면 `_selling` 을 푼다. PENDING 행이 없으면 race 가드의 보정 INSERT 가 쓴다 | **된다**(이미 있음) |
| ② 접수·거부 전문(`CNTG_YN=1`, `[order_notice]`/`[order_rejected_notice]`) | 기록만 한다. 상태는 바꾸지 않는다 | 이 전문에 주문번호가 있다. 가장 빠른 「접수됨」 증거지만 `src/realtime`(8영역·sha 핀)을 바꿔야 한다 → 이번에는 쓰지 않는다 |
| ③ 주문내역 조회(TTTC0081R `get_daily_orders`) | `selling_reconcile` 이 15분 잔고 동기화 끝에서 정확히 이 판정을 한다(보유 0 → 유지 · 열린 매도 있음 → 유지 · 180초 미만 → 유지 · 그 밖 → 해제). 조회 실패면 유지 | **된다** — 종목 단위로 판정한다 |

→ **사용자가 말한 「주문내역 조회」 는 이미 `selling_reconcile` 로 있다.** 빠진 것은 세 가지다. (a) 주기가 15분이라 최악의 경우 손절이 15분 넘게 멈춘다. (b) `_scan_loop` 가 15:20~15:30 에 꺼져 있어 15:20 강제청산 직후에는 돌지 않는다. (c) 지금은 예외가 퍼지므로 이 판정까지 가지도 못한다(15:20 이면 엔진이 그날 멈춘다).

### 3. 위험 시나리오(지금 행위)
- 15:20: `_force_clear_main_only` 종목 루프에 `try` 가 없다 → 남은 종목은 오버나잇 → 15:30 `_scan_loop` 재기동·20:00 자문·21:30 정산·`_reset_daily_state` 를 모두 잃는다.
- 장중: `risk.on_tick` 그 틱의 남은 전략 평가가 빠진다 → `handler._on_tick` 이 다시 raise 해 **WS 세션을 재연결**한다(그 세션의 모든 종목 시세가 끊긴다) → `_selling` 이 남아 최대 15분 동안 손절이 멈춘다.
- 🔴 **이웃 자리(같은 원리)**: 1차 주문(`execute_sell` 루프 안의 `place_order`)의 비 KisApiError 는 형제 `except Exception` 이 받아 **1초·2초 뒤 다시 보낸다.** 응답만 유실된 경우라면 이것이 재발사다. `_request` 의 POST 재시도(D2)까지 겹치면 최대 3×3=9번 보낼 수 있다. 매도는 KIS 매도가능수량 검사가 초과분을 막지만(APBK0400 → `sell_qty_locked`), **운영자가 같은 종목을 따로 들고 있으면 그 몫까지 팔린다.** 불변식 「우리 주문 합 ≤ 추적 수량」 이 깨진다.

## 정량 권고

### 4. 권고안 = **(나) + 사용자안(확인 조회) + (가) 방어망.** D2 는 같은 사이클의 별도 커밋으로 닫는다
1. **(나) 결과 모름 = 멈춤** — `_handle_sell_market_disallowed` 의 폴백 `try` 에 `except Exception` 을 더해 `SellFallbackOutcome.UNKNOWN` 을 돌려준다. 호출부는 이미 「NO_PRICE 가 아니면 return」 이라 바꿀 것이 없다.
   - UNKNOWN 이 할 일: `_selling` **유지**(discard 금지) · `_selling_since` 를 폴백 발사 시각으로 갱신(180초 나이를 여기서부터 잰다) · 매핑·PENDING 은 쓰지 않는다(주문번호가 없다) · 포지션·DB 그대로 · TTL·`_bump_after_exit_fails`·익일청산 큐 등록 없음(거부의 증거가 없다) · `[sell_send_unknown] ticker= strategy= path=fallback exc=<type>` **ERROR, 횟수 제한 없음**.
2. **사용자안 = 그 종목만 확인 조회** — UNKNOWN 이 나면 `create_task` 로 한 번 예약한다. **180초 뒤**(`SELLING_RECONCILE_MIN_AGE_S` 와 같은 값. KIS 주문내역 반영 지연을 막는다) `get_daily_orders(pdno=ticker)` + 잔고로 `selling_reconcile` 과 **같은 3사유 판정**을 그 종목에 한 번 한다. 해제하면 `[sell_send_unknown_resolved] result=not_accepted|closed|open_order|lookup_failed` 를 남긴다. **조회 실패의 기본값 = 유지**(15분 `selling_reconcile` 로 넘긴다. 재발사보다 지연이 낫다). 판정 함수는 `selling_reconcile.py` leaf 에 단일 종목용으로 두어 두 경로가 같은 규칙을 쓰게 한다(규칙이 둘이 되면 안 된다).
   - 손절이 멈추는 최악 시간: 지금 15분 → 약 3.5분(재시도 소진 ~32초 + 180초).
3. **(가) 15:20 종목별 `try`** — UNKNOWN 이 생기면 폴백 예외는 더 이상 퍼지지 않는다. 그래도 `execute_sell` 의 다른 예상 밖 예외 하나가 그날 엔진 전체를 세우는 구조는 남는다. 종목별로 `except Exception` → ERROR `[force_clear_ticker_error]` → 다음 종목으로 간다. **그 종목은 다시 보내지 않는다.** 6줄 안팎이고 `scheduler.py` 3,737줄이라 상한 3,900줄 안이다.
4. **D2 = 주문 POST 의 「보냈을 수 있는」 실패는 `_request` 가 재시도하지 않는다** — 주문 경로(order-cash·order-rvsecncl)에 한해 `ConnectError`·`ConnectTimeout`·`PoolTimeout`(서버에 닿지 않음)만 재시도한다. `ReadTimeout`·`ReadError`·`WriteError`·`RemoteProtocolError`·5xx 는 첫 회에 바로 올린다. KIS 주문에는 중복을 막는 클라이언트 키가 없어서 거래소 쪽에서 막을 길이 없다. ⚠️ 매수 쪽(`execute_buy` 의 예외 처리·`pending_buys`)에도 영향이 가므로 매수 경로는 이 사이클에서 **행위를 핀만** 하고, 처리 변경은 따로 자문한다.
5. **이웃 자리(1차 주문 `except Exception` 재발사)** — 같은 원리라 UNKNOWN 처리(멈춤 + 확인 조회)로 바꾸기를 권한다. 다만 지금 「네트워크 순단이면 1~2초 뒤 바로 다시 판다」 를 「약 3.5분 뒤 확인하고 판다」 로 바꾸는 **행위 변경**이다. 순단 중에는 다시 보내도 대개 같은 이유로 실패하므로 잃는 것이 작다고 본다. **포함 여부는 사용자가 정한다.**
6. (선택, 사용자 결정) **15:25 2차 스윕** — 15:20 에서 「접수 안 됨」 으로 확인된 VB 종목은 on_tick 에 15:20 청산 신호가 없어(`volatility_breakout.py` 는 `check_force_clear` 를 scheduler 가 한 번만 부른다) 확인 조회로 풀려도 그날 다시 팔리지 않는다 → 오버나잇. 15:25 에 「아직 보유 ∧ `_selling` 아님」 인 close_at_1520 종목만 한 번 더 `execute_sell` 하면 KisApiError REJECTED 경우까지 함께 닫힌다. 하지 않으면 남는 결과 = VB 당일청산 위반 1건(다음 날 손절·15:20 이 처리).

### 고칠 자리 · 승인
| 항목 | 파일 | 승인 |
|---|---|---|
| 1·2·5 | `src/engine/order_engine.py`(8영역) + `src/engine/selling_reconcile.py`(leaf) | **8영역 승인 + 매매 행위 변경** |
| 3·6 | `src/engine/scheduler.py` | **scheduler 승인**(라인 상한 대상) |
| 4 | `src/api/base.py`(8영역 아님) | **매매 행위 변경이라 승인** — 주문 발사 횟수가 바뀐다 |
| 핀 뒤집기 | `tests/unit/engine/test_cycle422_sell_fallback_net.py::test_f07_*` | 고치는 사이클이 의도적으로 뒤집는다 |

## 현 코드와의 정합성
- **충돌 1**: `SellFallbackOutcome` docstring과 `_handle_sell_market_disallowed` docstring의 「비 KisApiError 는 enum 으로 표현하지 않는다」 → 이 결정이 뒤집힌다. 「호출부에 추가 `try` 금지」 는 **그대로 둔다**(잡는 자리는 메서드 **안**이다).
- **충돌 2**: 1차 주문 `except Exception` 재시도(항목 5) — 현행 유지냐 변경이냐는 사용자가 고른다.
- 지키는 것: 체결통보 구독 · race 가드 보정 INSERT · `_selling` 단일 잠금(15:20·익일청산·종목상태 청산이 모두 `execute_sell` 입구에서 막힌다) · 「주문이 끝나면 `_selling` 을 푼다」(보유 축) · `CancelledError` 는 `except Exception` 밖이라 종료 신호를 삼키지 않는다.

## 회귀 시나리오 (고친 뒤 기대 행위)
| # | 결과 | 시간대 | 체결통보 | 기대 |
|---|---|---|---|---|
| S1 | 접수됨(응답 유실) | 정규장 | 옴 | 발사 2회(1차+폴백), 재발사 0 · 매핑 없는 통보 → 보유자 1명에게 귀속 · `_selling` 해제 · 보정 INSERT 1행 · 예외 전파 0 · WS 재연결 0 |
| S2 | 접수됨 → 체결 | 정규장 | 안 옴 | 180초 확인: 보유 0 → 유지(`closed`) · 15분 sync 가 포지션 정리 · 재발사 0 |
| S3 | 접수됨 → 미체결 걸림 | 정규장 | 안 옴 | 확인: 열린 매도 → 유지(`open_order`) · 15:30 자동취소 뒤 애프터 reconcile 이 해제 · 재발사 0 |
| S4 | 접수 안 됨(ConnectError) | 정규장 | — | 확인: 보유>0·열린 주문 0·180초 경과 → 해제 → 다음 틱 손절 재평가 = 새 발사 1회 |
| S5 | 아무것이나 | 정규장 | — | 확인 조회 예외 → 유지(`lookup_failed`) → 15분 reconcile 이 같은 규칙으로 판정 |
| S6 | 접수됨 | 15:20 | 옴(15:30 단일가) | 다음 종목 청산 계속 · 15:30 `_scan_loop` 재기동 · 정산 정상 |
| S7 | 접수 안 됨 | 15:20 | — | 루프 계속 · ~15:23:30 해제 · (6을 채택하면) 15:25 재청산 / (안 하면) 오버나잇 1건, 엔진은 산다 |
| S8 | 다른 예외(가짜 RuntimeError) | 15:20 | — | (가) `[force_clear_ticker_error]` · 그 종목 재발사 0 · 다음 종목 진행 |
| S9 | 접수됨 | 애프터(41) | 옴/안 옴 | S1~S3 와 같음 · 애프터 포기 래치 카운터 증가 0 |
| S10 | 접수 안 됨 | 애프터(41) | — | S4 와 같음(새 발사는 다시 44→41 경로) |
| S11 | D2 ReadTimeout | 주문 POST | — | `_request` 발사 1회 후 바로 예외 · ConnectError 는 최대 3회 |
| S12 | D2 5xx | 주문 POST | — | 발사 1회 · 재시도 0 |
| S13 | 1차 주문 결과 모름(항목 5 채택 시) | 정규장 | 옴/안 옴 | 폴백·재시도 없이 UNKNOWN 과 같은 흐름 |
- 공통 확인: `place_order` 호출 횟수 · `_selling`/`_selling_since` · 매핑 5종이 비어 있는지 · 마커 횟수 · `risk.on_tick` 이 같은 틱의 다음 전략을 계속 평가하는지 · `handler._on_tick` 에서 raise 가 0인지. 시각은 `freeze_time` 으로 고정한다(정규장 10:30 · 15:20:05 · 애프터 16:05).

## 반례 / 한계
- 180초 확인도 「열린 주문 없음」 이라는 부재를 근거로 쓴다. KIS 주문내역 반영이 180초보다 늦으면 이중 매도가 될 수 있다. 다만 매도는 KIS 매도가능수량이 초과분을 막는다. 남는 위험은 운영자 별도 보유분뿐이다. 이 기준은 `selling_reconcile` 이 이미 받아들인 위험과 같다.
- `get_daily_orders` 는 다음 쪽을 넘기지 않는다(첫 쪽만 본다). 종목 필터(`pdno`)로 좁히면 이 위험도 줄어든다. 전체 목록을 쓰는 15분 reconcile 은 주문이 많은 날 잘릴 수 있다(역순 조회라 최근 주문은 앞쪽에 있다).
- 폴백이 접수됐는데 가격이 5호가 밑으로 계속 빠지면 걸린 주문 때문에 손절이 멈춘다. SENT 경우와 같은 기존 한계라 이번 범위 밖이다.
- 「접수 전문 ②」 를 쓰면 확인이 몇 초로 줄지만 8영역 `src/realtime` 이 바뀌고, 거부 전문의 실제 값이 아직 실측 대기다. 이번에는 권하지 않는다.

## 후속 검증 권고
- 메인 세션(운영 로그 조회): `[api_retry_exhausted] path=…order-cash` 와 `네트워크 오류 (attempt` 가 주문 경로에서 몇 번 났는지 본다. D2·F-422-1 의 실제 빈도이고, 항목 5 결정의 근거가 된다.
- tdd-engineer: 위 S1~S13 을 Red 로 만든다. `test_f07_*` 은 「전파」 → 「UNKNOWN + 유지 + 발사 2회」 로 뒤집는다. 돌연변이 = `except Exception` 삭제 · `_selling.discard` 삽입 · 확인 조회 실패 기본값을 해제로 바꾸기.
- tester: 15:20 루프 통합 시나리오(S6~S8)에서 15:30 `_scan_loop` 재기동과 21:30 정산이 이어지는지 본다.
