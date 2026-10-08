# 거래일지 D1 대안: 관찰자 방식 설계안 (최종)

## 요약
1. **된다.** 체결통보를 새로 구독하지 않는다. 별도 컨테이너 워커가 주 프로세스가 이미 남기는 세 가지(`trade_history`, 파일 로그, 상태 조회 GET)를 **읽기만** 한다. 그래서 주문·청산 판단 경로, 8영역, `scheduler.py` 모두 0줄이다.
2. 로그를 실측했다(09-17~10-07, 매수 75건·매도 70건). 매도 70/70건과 매수 75/75건이 주문번호가 찍힌 접수 줄로 짝지어진다. 청산 이유도 70/70건에서 얻는다.
3. 진입 신호·파라미터·엔진 상태는 기존 `GET /api/trading/status`에서 읽는다. 대시보드가 이미 5초마다 부르는 경로라 src는 0줄이다. 새로 만드는 것은 손절선·ATR·무장가를 주는 GET 1개뿐이다(`balance.py` 약 30줄, KIS 호출 0).
4. 리팩토링은 필요 없다. 기존 계획의 D1·R1·R6·R7·R9를 철회한다.
5. 잃는 것은 세 가지다. 청산 순간 **유효 손절선**이 최대 15초 전 스냅샷 값이 된다(26건 전부, 스냅샷 나이를 함께 남긴다). 매도 판단가는 정확 10건·역산 13건·상한만 3건이다. 과거분 58건은 주문구분이 빈칸이다. 대신 **발동한 선**을 15건 정확히 얻고, LTV 5건은 D1에서 빈칸이던 값이 새로 계산된다.
6. 체결통보 추가 구독(C안)과 워커의 KIS REST 폴링은 권하지 않는다. 같은 앱키를 쓰면 메인의 재연결이 거부돼 체결통보가 끊길 수 있고, 얻는 정보도 없다.
7. 안전 조건은 모두 테스트로 고정한다. 워커 전용 DB 역할(`kis_quote_accounts` 차단, `trade_history`는 읽기만, 타임아웃), 워커의 `src` import 0, KIS 변수 0, G1의 변이 금지, 호출 빈도 상한이다.
8. 결정할 것은 세 가지다. E1a(워커 + 기존 GET, src 0줄), E1b(G1 GET), E1c(운영 DB에 워커 역할 생성). D2는 그대로이고, D3는 「로컬 사본을 파싱해 장외 창에 1회 적재」로 바뀐다.
9. 첫 배포는 full 1회다(10-13 21:35 이후). 그 뒤에도 compose를 고치는 배포는 full이므로, 자원 상한은 첫 배포에 넣는다.

- **기준**: main `9a3c1d3b`. 코드는 읽기만 했다. 운영 서버와 DB에는 접속하지 않았다.
- **로그 실측**: EC2 로그 사본 09-17~10-07. 매매가 있던 날은 12일이다.

---

## 1. 결론

### 「별도 프로세스에서 체결을 받아 기록하면 어떨까?」
된다. 체결 사실과 거래 이유가 이미 세 곳에 쌓이고 있다.

| 출처 | 담긴 것 | 쓰는 쪽 |
|---|---|---|
| `trade_history` | 체결 사실, 주문번호, 전략, `order_price`(cycle409 주문가 기록, 10-07~) | 주 프로세스(체결통보로 갱신) |
| 파일 로그 `./logs/auto_stock.log` | 접수 줄(주문번호·전략·신호 이름), 전략 사유 줄, 접수 전문 `[order_notice]` | 주 프로세스 |
| 상태 조회 GET | 진입 신호 링버퍼·파라미터·phase·보유 현황(기존 G0), 손절선·ATR·무장가(새 G1) | 주 프로세스가 메모리 값을 보여 준다 |

로그 실측 결과는 다음과 같다.
- **매도 70/70건**에 `"<신호> 매도 주문 접수: … (주문번호: N, 전략: S)"` 줄이 있다(`order_engine.py:2009-2012`).
  - 모든 매도 발사는 `"SELL 주문 완료 … (주문번호: N)"` 줄도 남긴다(`api/order.py:99-106`). 이 줄도 70건이고, 두 줄의 주문번호가 70/70 일치한다.
- **매수 75/75건**에 `"매수 주문 접수: … @ 가격 (주문번호, 전략)"` 줄이 있다(`order_engine.py:1643-1644`).
  - 75건 모두 같은 (전략, 종목) 신호 줄이 1초 안에 있다. 신호 줄만 세면 0초가 49건, 1초가 26건이다.
- **체결통보(H0STCNI0/9) 추가 구독은 하지 않는다**(8절).

### 「리팩토링과 함께 해야 하나?」
아니다. 기존 코드 리팩토링은 0이다. 새로 정하는 경계는 하나뿐이다.
- 엔진은 메모리 값을 보여 주기만 한다(캡처).
- 워커가 읽고 조립해서 쓴다(수확).
- `docs/architecture.md` 15.3의 「퍼널: 캡처는 엔진, 적재는 워커」와 같은 꼴이다.

### D1과 비교

| | D1(기존 계획) | 관찰자 방식 |
|---|---|---|
| 주문 경로 접촉 | `order_engine.py` 약 27줄 | **0줄** |
| 청산 이유 | 주문번호에 정확히 묶임 | 70/70. 폴백·재주문은 결합으로 추정(이 기간 실측 0건) |
| **발동한** 손절선 | 남기지 않음 | 정확 15/26(로그). LTV 5건은 사유 줄의 모드와 스냅샷 파라미터로 계산 |
| 청산 순간 **유효** 손절선 | 주문 직후 정확값(LTV는 빈칸) | 26/26 모두 최대 15초 전 스냅샷 값 + `snapshot_age_s` |
| 매도 판단가 | R2 신호 틱 시세 | 정확 10, 역산 13(±0.05%p), 상한만 3 |

---

## 2. 항목별 출처 표

- 대상은 기존 계획에서 주문 경로 기록(R1~R6)에 기대던 항목이다.
- ①②③④⑤⑩은 기존 계획대로 화면이 읽을 때 계산한다. 바뀌지 않는다.

| 항목 | 기존 계획 | 관찰자 방식의 출처 | 정확도·공백 (로그 실측) |
|---|---|---|---|
| ⑧ 진입 이유 | R1 `note_entry` | ① G0 응답의 `strategies.<id>.buy_signals`(최근 10건, `strategy_registry.py:157`). R1이 고르던 것과 같은 dict다. 워커가 스냅샷마다 메모리 링(TTL 10분)에 쌓아 둔다. ② 같은 응답의 `params`(`:149`). ③ 주문번호는 「매수 주문 접수」 줄에서 얻는다. **폴백 매수**는 접수 줄이 없다. 그래서 `BUY 주문 완료`(종목·가격·주문번호), 폴백 WARNING(`order_engine.py:1746-1749`, 종목·가격), `trade_history.strategy`(주문번호로 조회)를 묶어 쓴다 | 75/75건이 짝지어진다. 규칙은 「같은 (전략, 종목) 신호 중 주문 시각 이전의 마지막 것」이다. 접수 줄을 본 회전에 링에 신호가 없으면 한 회전 더 기다린다. 그래도 없으면 로그 신호 줄로 쓰고 「로그만」으로 표시한다. 이런 경우는 신호 뒤 15초 안에 엔진이 재시작한 경우뿐이다. BFB·VCP는 로그 줄이 `*_vol_gate_pass`뿐이라 구조값(깃발 상단·목표·기준 고점)이 빈다. 이 기간 재시작 4회는 모두 15:30 뒤였고, 직전 60초 안 주문은 0건이었다. 폴백 매수 실측도 0건이다 |
| 판단가 (매수) | R1 `current_price_won` | `buy_signals[].price`(신호 틱 가격) + 접수 줄의 `@ 가격` | D1과 같다 |
| ⑧ 청산 이유 | R3·R4·R5(D1), R6(수동) | 접수 줄의 신호 이름 + 같은 종목 10초 안의 전략 사유 줄 + (익일청산) 08:00 보류 줄 | **신호 이름 70/70.** 분포는 FORCE_CLEAR 26(VB 17 + LTV 9) · NEXT_DAY_CLEAR 11 · STOP_LOSS 25 · TRAILING_STOP 8. 가격·전략 청산 33/33건에 사유 줄이 있다. 시각 청산 37건은 이름이 곧 사유다. **익일청산 11건은 모두 보류 줄이 있고, 사유가 셋으로 나뉜다** — `reason_sub`로 저장한다. `gap_below`(갭률 기록, 4건, `scheduler.py:1518`), `krx_only`(KRX 전용이라 갭 판정 없이 09:00 청산, 7건, `:1415`), `nxt_open_missing`(`:1457`, 0건). **7/70건은 이름과 실제 사유가 다르다**(시간청산 5 · 스테이지3 1 · 측정 목표 익절 1). cycle402(청산 사유 이름 정리, 10-06 22:11 배포) 전 이름 체계 때문이며, 7건 모두 사유 줄에 실제 사유가 있다. **경로별**: 수동은 `routes/trading.py:220-222` 「수동 매도 주문 접수」 줄이다. 이 문구는 `<신호> 매도 주문 접수` 꼴과 겹치므로 **로거 이름**(`src.routes.trading`)으로 가른다. 종목상태는 `[status_exit_fire]` + `STATUS_EXIT`, 폴백·재주문은 결합 추정(8절 한계 5), 외부 MTS는 `[order_notice]`만 있다. 외부 주문은 **체결된 것만** 「외부」 행으로 만든다 |
| 청산 순간 손절선 | R3·R4가 주문 직후 `resolve_exit_lines` 1회(유효선만) | **두 칸으로 나눠 저장한다.** `fired_line` = 발동한 선(사유 줄). `effective_line` = `resolve_exit_lines`의 유효선. 유효선은 매도 접수 직전 G1 스냅샷 값이고 `snapshot_age_s`를 함께 남긴다 | **발동선**(손절·트레일링 26건): 선 가격이 적힌 것 7건(kojiro 트레일 2 · kojiro ATR 손절 3 · donchian 트레일 2)과 임계 %가 적힌 것 8건(momentum 4 · BFB 받침선 2 · kojiro 하드 2)은 매수가로 계산해 **정확 15건**이다. LTV 5건은 사유 줄이 모드를 드러낸다. 「당일 손절」이면 `intraday_stop_loss`(`long_tail_volatility.py:1109-1111`), 「손절(상한가 모드)」이면 `overnight_stop_loss`(`:1102-1104`)다. 그래서 매수가 × (1 + 비율/100)로 **계산된다**(비율은 스냅샷 파라미터, PUT이 없으면 정확). D1에서는 빈칸이던 값이다. 나머지 6건(BFB 눌림목 4 · VB 2)은 스냅샷 값으로 계산한다. VB는 고정%라 PUT이 없으면 정확하다. **유효선**은 26건 모두 스냅샷이다. 발동선은 유효선보다 낮을 수 있다. kojiro 유효선은 max(pct, 바닥선, 샹들리에, 본전)인데 검사는 하드 → 2ATR → 샹들리에 순서다(`kojiro.py:1053-1122`). BFB 유효선은 `bull_flag_breakout.py:1420-1456`이고, backstop은 §1에서 먼저 나간다(`:1265-1271`). 이 기간에도 띄엄띄엄 판정된 표본이 있다. 09-23 `[no_feed_held]`(REST 60초 폴만) 목록에 000520(ATR 손절 12:51:45)과 036540(트레일 09:05:55)이 들어 있다. 052710 BFB는 임계 −5%인데 −6.0%에서 발동했다(09-28 11:23:18). 유효선 스냅샷이 주문 순간 값과 다른 경우는 그 15초 안에 고점·무장·래치·파라미터가 바뀐 경우뿐이다. 과거분에는 스냅샷이 없어 몇 건인지 **셀 수 없다**. 앞으로는 `snapshot_age_s`로 잰다. 시각·시간·추세 청산 44건은 계획대로 「미발동, 참고값」이다. 과거 복원(D3)은 발동선만 얻는다 |
| 판단가 (매도) | R2(신호 틱 시세) | 사유 줄의 「현재가」 → 없으면 사유 줄의 %로 매수가에서 역산 → 없으면 `trade_history.order_price` | 26건 중 **정확 10**(momentum 4 · VB 2 · kojiro 트레일 2 · donchian 트레일 2), **역산 13**(LTV 5 · BFB 눌림목 4 · BFB 받침선 2 · kojiro 하드 2, % 소수 한 자리라 ±0.05%p), **상한만 3**(kojiro ATR 손절은 판단가 ≤ 선). 상한만 아는 3건은 09-21·09-23 거래라서, `order_price`(10-07~)로 보충할 수 **없다**. 시각 청산 37건 중 34건도 복원 범위에서는 판단가가 없다. 26건 분포는 cycle405(donchian 사유 줄 없음) 전과 BFB turtle 전환(09-29) 전이 섞인 것이라 앞으로의 비율과 다르다 |
| 주문구분 | R1·R3이 메모리 `_order_division`을 읽음 | `[order_notice] kind=` 줄(`realtime/handler.py:716-726`, 접수 전문 원본 값) | 09-28 이후 매도 42/42건(01 41건 · 44 1건), 매수 45/45건(01). `[order_notice]`는 09-28 08:08:33에 처음 나온다. 그래서 09-17~09-23 거래 58건(매도 28 · 매수 30)은 빈칸이고, 과거 복원 범위 확보율은 **87/145(60%)**다 |
| 거래소 | R3 `target_exchange` | 매수: `llm_buy_evaluations.exchange`(`043_llm_buy_evaluations.sql:74`, 행이 있는 주문만). 매수·매도: `[order_channel] … exchange=`(`order_engine.py:652`) | **일부만 확보한다.** `[order_channel]`은 (종목, 매수/매도, 사유)마다 하루 1회만 남는다. 나머지는 빈칸이다. 필수 10항목은 아니다 |
| ⑥⑦ 손절선 변화 · ⑨ 익절목표 | R8(엔진 안 60초 루프) | 워커가 G1 스냅샷을 **15초**마다 받아 R8 규칙(문턱·`eod`·`boot`·`paused`)대로 기록한다 | 값은 같은 leaf에서 나오므로 같다. 한 주기 안에 사고판 거래는 최초 손절이 빈다(「관측 전 청산」). **E1b를 거절하면 이 칸들은 빈다** |

**자기 점검** (60초마다 + 하루 1회)
- `SELL 주문 완료` 수 = 매도 일지 행 수(접수 + 폴백 + 재주문 + 수동). 이 기간에는 70 = 70 + 0 + 0 + 0이었다.
- `BUY 주문 완료` 수 = 매수 일지 행 수(접수 + 폴백). 이 기간에는 75 = 75 + 0이었다.
- 사유를 모르는 매도 수 = 0. 이 기간에도 0이었다.
- 하나라도 어긋나면 `[journal_gap]` WARNING을 1줄 남긴다.

---

## 3. 구조 권고: **B (별도 컨테이너 워커)**

### 세 안 비교

| | A. 엔진 안 별도 태스크 | **B. 별도 컨테이너 워커** | C. 체결통보 추가 구독 |
|---|---|---|---|
| 주문·청산 경로 코드 | 0 | 0 | 0 |
| 엔진과 함께 쓰는 것 | 이벤트 루프·DB 풀(최대 10, `pg.py:81-86`). 파싱 쪽 동기 버그가 틱 처리를 멈출 수 있다 | GET 처리 시간(로컬 ASGI 전체 경로 중앙값 0.50ms, p99 0.78ms, 31KB 응답 기준)과 RDS 잠금 대기열(5절 ④) | KIS 세션·IP |
| 일지를 고칠 때 배포 | 매번 full(backend 재시작) | 워커 코드만 바뀌면 워커만 다시 만든다. compose를 고치면 full이다 | — |
| 주문 능력 | 엔진 내부라 무엇이든 부를 수 있다 | KIS 환경변수·토큰 캐시·`src` import가 없다(테스트로 고정). DB는 최소 권한이다. API는 리포터 키라 GET/HEAD 전부와 `POST /api/log-reports/{date}/external` 1경로만 통과하고(`api_auth.py:262-269`), 워커는 POST를 쓰지 않는다 | KIS 자격·HTS ID를 다뤄야 한다 |
| 판정 | 차선(E1c를 거절할 때) | **권고** | **비권고**(8절) |

### 구성 요소

| # | 구성 요소 | 하는 일 | 근거·비용 |
|---|---|---|---|
| G0 | 기존 `GET /api/trading/status?include=system,holdings,strategies` | `running`·`phase`, 보유(`buy_price`·`quantity`·`high_since_buy`·`buy_date`), 전략별 `params`·`buy_signals[-10:]`를 준다 | **src 0줄.** `routes/trading.py:58-76` → `scheduler.get_status`(`scheduler.py:1244`, `strategies`는 `:1321` → `strategy_registry.py:145-170`). 동기 함수라 await가 없고 KIS 호출도 0이다. 대시보드가 이미 5초마다 부르므로(`TradingStatusContext.tsx:25`) 워커의 15초 폴링은 열린 탭 하나의 1/3이다. `include`를 줘도 전체를 계산한 뒤 자르므로(`trading.py:65`) 계산 비용은 같다 |
| G1 | 새 `GET /api/balance/exit-lines` (`balance.py` 약 30줄) | 보유 종목마다 `build_exit_line_map` 결과를 준다(`position_exit_lines.py:223-256`). 잔고 라우트가 이미 쓰는 never-raise leaf다. 여기에 같은 순간의 `buy_price`·`quantity`·`high_since_buy` 값, `_entry_atr` 값, donchian `_kk_exit_lines` 무장 여부·무장가, `running`·`as_of`(KST)를 붙인다 | KIS·DB 호출 0. 직전 응답 뒤 5초 안의 재호출에는 캐시를 돌려준다 |
| W1 | 워커: 로그 수확 | 호스트 `./logs`를 `:ro`로 마운트해 이어 읽는다. 커서(파일·inode·offset)는 DB에 두고 청크마다 저장한다. 1회 읽기량에 상한(20MB)을 둔다 | 로그 회전은 이름 바꾸기 방식이고 압축하지 않는다(`main.py:102-107`·`:116-127`). 그래서 옛 inode를 끝까지 읽은 뒤 새 파일로 넘어간다 |
| W2 | 워커: 스냅샷 | G0·G1 응답을 직전 값과 비교해 `trade_journal_stops`에 사건을 쓴다. `buy_signals`는 메모리 링에 보관한다. 매도 접수가 보이면 그 직전 스냅샷으로 `exit` 사건을 쓰고 `snapshot_age_s`를 남긴다 | |
| W3 | 워커: 대사 | 당일 `trade_history`와 주문번호를 맞추고, 짝이 없으면 `unmatched`·`external` 행을 쓴다. 2절의 항등식 셋을 확인한다 | 60초마다 + 매일 20:10에 1회 |

**한 회전** (15초 고정 주기, sleep은 `finally`에 둔다)
1. G0 호출
2. G1 호출
3. 로그 이어 읽기
4. 짝짓기
5. DB 쓰기(자동 커밋 단문)

엔진이 정지했거나 `engine_idle`(21:30~07:45)이면 5분 주기로 돌고, 아무것도 쓰지 않는다.

### 데이터 흐름

```
backend(엔진) ── 파일 로그 ./logs (기존) ─── 읽기 전용 마운트 ──▶ journal_worker
backend(엔진) ── trade_history (기존, RDS) ── SELECT(전용 역할) ──▶ journal_worker
backend(엔진) ◀─ GET /api/trading/status (기존, 리포터 키, 15초) ── journal_worker
backend(엔진) ◀─ GET /api/balance/exit-lines (새 G1, 리포터 키, 15초) ── journal_worker
journal_worker ── INSERT/UPDATE ──▶ trade_journal_orders / _stops / _cursor
backend routes/history.py ── SELECT ──▶ 거래일지 화면 (1b, 계획 그대로)
```

### 세부 규칙
- **매수 행 쓰기**
  - 접수 줄을 보면 링에서 신호를 찾는다.
  - 없으면 한 회전 더 기다린다. 그래도 없으면 로그 신호 줄로 쓰고 「로그만」으로 표시한다(`ON CONFLICT DO NOTHING`).
  - 재시작으로 신호를 잃는 창은 최대 15초다. 스냅샷과 로그 읽기를 한 회전에 묶었기 때문이다.
- **부팅 처리**
  - `phase`가 `booting`을 벗어난 뒤 한 회전은 `boot` 사건을 쓰지 않는다. 계획 R8의 「첫 회 60초 쉼」을 대신하는 규칙이다.
  - 실제 표본이 하나 있다. 09-29 16:00:26에 재시작했고, 2분 뒤 16:02:21에 donchian TRAILING_STOP 매도(030530)가 나갔다. 이 표본을 골든 테스트에 넣는다.
  - `engine_idle`이면 쓰지 않는다. 21:30 `positions.clear()`를 청산으로 보지 않는 규칙은 계획 4-2 그대로다.
- **파서**
  - 줄을 **로거 이름 + 접두 비교**로 거른다.
  - 종목 표기는 두 가지 꼴을 모두 받는다. `t()`는 이름이 없으면 코드만 돌려주기 때문이다(`scanner.py:1372-1375`). 꼴은 `이름(코드)`과 `코드`다.
  - 종목코드는 끝 쪽에서 읽는다. 이름에 괄호가 들어간 사례가 있다: `인제니아테라퓨틱스(Reg.S)(950260)`.
  - 문법은 모듈 1곳에 모은다.
- **로그 원천으로 파일을 쓰는 이유**
  - `system_logs`에는 빠질 수 있는 지점이 있다. 큐가 차면 조용히 버리고(`main.py:146`·`:218-219`), DB 쓰기 실패도 삼킨다(`:163-164`).
  - `system_logs`의 시각은 로그 시각이 아니라 DB에 넣은 시각이다(`:161`). INFO는 2일만 보관한다(`system_logs.py:32`).
  - 파일은 20일 보관이고(`main.py:108`), 로그 시각이 정확하다.
  - 파일을 못 읽으면 `system_logs` `id` 커서로 바꾼다. 이때는 역할에 `system_logs` SELECT만 더한다.
- **과거분(D3)**
  - 로컬 사본(09-17~10-07)은 로컬에서 파싱해 결과 파일을 만들고, 장외 창에 EC2에서 1회 적재한다.
  - 사본에 없는 10-08~배포일분은 장외 창에 1회성 명령(`docker compose run --rm journal_worker backfill`)으로 돌린다. 읽기 속도에 상한을 두고, **컨테이너 기동 경로에서는 뺀다**.
  - 적재한 행은 `source='log_restore'`로 구분한다.
- **워커 컨테이너**
  - `docker-compose.prod.yml` **본체**에 정의한다. 오버레이에만 두면 `--remove-orphans`가 지운다(`architecture.md` 15.7).
  - 코드는 `src/` 밖 `journal_worker/`에 둔다(`macro/` 선례). `src/` 아래에 두면 `BACKEND_RE`(`compose_up_changed.sh:113`)에 걸려 워커만 고쳐도 backend가 재시작된다.
  - build context는 `./journal_worker`로 한다.
  - 자원 상한은 **첫 배포에 넣는다**: `mem_limit: 160m`, `cpus: 0.25`, `logging: json-file max-size 10m, max-file 3`. 메모리 값은 추정이다(Python + asyncpg + httpx 상주분을 넉넉히 잡음, 미측정). 나중에 고치면 그 배포도 full이라서 첫 배포에 넣는다.
  - 환경 값과 마운트 규칙은 5절 ①·⑤에 있다.

**A를 고를 경우(차선, E1c를 거절할 때)**
- backend의 DB 풀을 쓰므로 새 DSN이 필요 없다.
- 같은 파서와 같은 테이블을 쓴다. 수확 코드는 registry·8영역 import를 0으로 AST 고정한다.
- `boot_manager`가 +6줄이고, 일지를 고칠 때마다 full 배포다.

---

## 4. 8영역·scheduler·주문 경로 접촉

| 대상 | 변경 |
|---|---|
| 8영역(`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`api/order.py`·`realtime/**`·`auth/**`) | **0줄** |
| `scheduler.py` | **0줄** |
| 주문·청산 판단 경로(`execute_sell`·`execute_buy`·전략 `check_*`·`llm_buy_gate.observe_order`·`routes/trading.py` 수동 매도) | **0줄** |
| `boot_manager.py` | 0줄(R7 철회) |
| `src/routes/balance.py` | E1a는 0줄. E1b는 **+약 30줄**(G1 + 5초 캐시) |
| `docker-compose.prod.yml` | +약 20줄(서비스·자원 상한·로그 회전) |
| `tools/deploy/compose_up_changed.sh` | +약 20줄. `JOURNAL_RE='^journal_worker/'` 축을 추가하고, 선택 배포 조합을 일반화한다(지금은 `frontend\|macro\|frontend+macro` 리터럴, `:271`). 가드 G-248-2·G-248-5를 갱신해야 한다 |
| 새로 만드는 것 | `supabase/migrations/047_trade_journal.sql`, `journal_worker/`(약 500줄 + Dockerfile + requirements 2개 고정 + `ops/role.sql`), 테스트 |

**G1이 필요한 이유**
- 손절선 계산 입력은 엔진 메모리에만 있다. `_entry_atr`, kojiro 바닥선, BFB·VCP 래치·구조선, donchian 무장 여부가 그렇다.
- `positions` 테이블에는 ATR·래치·손절선 칸이 없다(`src/db/positions.py:21-31`). G0에도 청산선은 없다.
- `/api/balance`는 청산선을 주지만, 부를 때마다 KIS 잔고조회를 1회 한다(`balance.py:35`). 그러면 주문과 같은 초당 20건 세마포(`api/base.py:29`)를 나눠 쓰게 된다. 그래서 비권고다.
- E1b를 거절해도 E1a는 성립한다. 빈칸이 되는 것은 ⑥⑦⑨와 청산 순간 유효선뿐이다.

**핀**
- 8영역 sha 재핀은 0이다. `order_engine.py` 통째 핀 11개 파일도 그대로다.
- E1b를 하면 `_SRC_TREE_DIGEST`만 다시 계산한다(`balance.py`).
- `src/`에 새 파일이 없으므로 `_SRC_TREE_FILES`·`_PINNED_DIR_FILE_COUNTS`·cycle291 `82`는 변하지 않는다.

---

## 5. 안전 조건 (모두 1a의 Red 테스트로 고정)

### ① 워커 전용 DB 역할 — 운영 DSN을 함께 쓰지 않는다
- **이유**
  - 운영 DSN은 `kis_quote_accounts.app_key/app_secret`를 평문으로 읽을 수 있다(`026_kis_quote_accounts.sql:10,19-20`). 운영 시세 세션 7개가 실제로 이 표에서 자격을 읽는다(`websocket_pool.py:130,175`, `token.py:469-490`).
  - HTS ID는 파일 로그에 평문으로 남는다(10-07 07:47:10 H0STCNI0 구독 응답의 `tr_key`). 그래서 워커 안에서 DB 조회 한 번이면 C안 경로나 시세 세션을 빼앗는 경로가 열린다.
  - 운영 DSN은 `positions`·`pending_next_day_clear`(부팅 때 복원)와 `strategy_config`·`system_config`(매매 행위)에 쓸 수 있다. `SELECT … FOR UPDATE`로 행 잠금도 걸 수 있다.
- **권한**
  - `trade_history`·`llm_buy_evaluations`: SELECT
  - `trade_journal_*`: SELECT·INSERT·UPDATE
  - `system_logs`: SELECT(대체 경로를 쓸 때만)
  - 그 밖의 테이블은 권한 0이다.
- **역할 수준 고정 값**: `statement_timeout=5s` · `lock_timeout=1s` · `idle_in_transaction_session_timeout=5s`.
- **만드는 방법**
  - 비밀번호가 git에 들어가지 않도록 마이그레이션이 아니라 1회성 운영 스크립트로 만든다(`journal_worker/ops/role.sql`, 비밀번호는 psql 변수로 넘긴다). 실행은 047 적용 뒤다.
  - DSN은 `./secrets/journal_worker.env`(git 밖)에 둔다.
  - `.env`에 두지 않는 이유는 `.env`를 편집하면 `env_file: .env`인 backend가 재생성되기 때문이다(`docker-compose.prod.yml:50-51` 주석, 실측).
- **테스트(pg 하네스)**
  - `kis_quote_accounts`·`strategy_config`·`positions`의 SELECT/UPDATE가 거부되는지 확인한다.
  - `trade_history`의 UPDATE와 `SELECT … FOR UPDATE`가 거부되는지 확인한다.

### ② G1 변이 금지 — 엔진 안에서 도는 유일한 새 코드
- **범위를 줄였다.** params·신호·phase는 대시보드가 이미 5초마다 부르는 기존 코드(G0)가 준다. 그래서 G1은 청산선 leaf와 값 몇 개만 다룬다.
- **허용 호출**(계획 5절 그대로): `build_exit_line_map`·`resolve_exit_lines`, `_kk_exit_lines`·`_kk("kk_breakeven_r")`, `getattr`·`dict.get`.
- **금지 호출**: `check_*`·`on_*`·`prepare`·`calc_*`·`_apply_budget_limit`·`_market_unit_*`·`_effective_setup`.
  - 이유: `calc_buy_quantity`는 `_entry_atr`를 덮어써 보유분 손절을 바꾼다. `check_exit_signal`은 LTV 모드를 바꾼다.
- **AST 추가 금지**
  - 대입·삭제 대상은 지역 이름만 허용한다(`x[k]=…`·`obj.a=…`·`del`은 호출 목록 검사에 걸리지 않으므로 따로 막는다).
  - `vars`·`__dict__`를 금지한다.
  - 변이 메서드(`pop`·`popitem`·`clear`·`update`·`setdefault`·`sort`·`append`·`extend`·`remove`·`insert`)를 금지한다.
  - 사본은 값을 새 dict에 옮겨 만든다.
- **막으려는 실패 예**
  - `vars(pos)["buy_date"] = ….isoformat()`를 하면 운영 Position의 `buy_date`가 문자열이 된다(`strategy_base.py:75-84`). 그러면 `is_next_day`에서 TypeError가 나서 익일청산 판정(`scheduler.py:1353`)이 깨진다. donchian `_business_days_held`(`donchian_swing.py:1740`·`:1800`)도 깨진다.
  - `params.pop(...)`를 하면 BFB `params["stop_loss_rate"]`(`bull_flag_breakout.py:1274`)와 VCP(`vcp_breakout.py:1659`) 청산에서 KeyError가 난다.
- **행위 테스트**
  - 보유·래치·params·`_entry_atr`·`buy_signals`가 든 registry를 deepcopy해 둔다.
  - G1 호출 전후로 값이 같은지(`==`), 각 dict·list가 같은 객체인지를 확인한다.
- **응답 처리**
  - 직렬화는 핸들러 try 안에서 끝낸다(`json.dumps(..., default=str)` → Response). 예외가 나면 `success=false`를 돌려주고, INFO 로그는 남기지 않는다.
  - `async def`로 쓰고, 스냅샷 구간 안에 `await`를 두지 않는다. 그래서 한 번에 읽힌다.

### ③ 호출 빈도 상한
- **이유**
  - 백엔드에는 인증만 있고 빈도 제한이 없다(`api_auth.py:241-271`). 워커는 nginx를 거치지 않고 `backend:8000`에 직접 붙는다.
  - 예외 경로에서 sleep을 빠뜨리거나 요청이 겹쳐 쌓이면 uvicorn 단일 워커의 루프를 점유한다. 그러면 틱·체결통보 처리가 밀린다.
- **G1 쪽**: 직전 응답 후 5초 안의 재호출에는 캐시 응답을 준다. 상수 시간이고 `balance.py` 안에서 끝난다.
- **워커 쪽**
  - 동시 요청은 1개만 둔다.
  - 고정 주기로 돌리고, sleep은 `finally`에 둔다.
  - 실패하면 지수 백오프한다(상한 5분).
  - 「예외 경로에서도 sleep한다」를 테스트로 고정한다.
- **URL**
  - G0·G1 두 경로만 상수로 두고, 허용 집합 테스트를 둔다. 리다이렉트는 따라가지 않는다.
  - 이유: 리포터 키는 GET이면 경로를 가리지 않고 통과한다(`api_auth.py:262-264`). 그래서 경로 오타 하나면 KIS를 부르는 GET을 15초마다 치게 된다. 해당 경로는 `/api/balance`(`balance.py:35`), `/api/balance/buyable`(`:126`), `/api/portfolio/risk`다.

### ④ RDS 잠금 대기열
- **시나리오**
  1. `deploy.yml`은 배포 때마다 마이그레이션 전부를 다시 실행하고, `lock_timeout`이 없다(`deploy.yml:49-56`). 002·003·046에는 `ALTER TABLE trade_history`가 있다.
  2. 워커 트랜잭션이 열린 채로 있으면 ALTER가 그 뒤에서 기다린다.
  3. 그 뒤로 backend의 `trade_history` 쓰기가 모두 줄을 선다.
  4. 체결통보 처리는 `await update_trade_status`를 메인 세션 수신 루프 안에서 직렬로 기다린다(`order_engine.py:2939,3284`, `websocket.py:965` → `handler.py:759-761`). 최대 30초씩 멈출 수 있다(`pg.py:86`).
  - 로컬 재현에서 다음 UPDATE가 6.0초 기다렸다.
  - 워커만 배포해도 `deploy.yml`을 타므로 ALTER가 다시 돈다.
- **대책**
  - 워커는 자동 커밋 단문만 쓴다. 트랜잭션 안에 HTTP·sleep을 두지 않는다. 둘 다 테스트로 고정한다.
  - 여기에 ①의 역할 타임아웃과 `trade_history` SELECT 전용 권한을 더한다.
  - `lock_timeout=1s` 때문에, ALTER가 대기 중이면 워커의 새 SELECT는 줄을 늘리지 않고 1초 안에 포기한다.

### ⑤ KIS 자격 격리
- **이유**
  - `src.config.Settings`의 KIS 키는 기본값 없는 필수 칸이다(`config.py:26-28`). 워커가 `src`를 import하면 키를 요구하고, 가장 쉬운 해결이 `env_file: .env`다. 그러면 메인 앱키와 HTS ID가 전부 들어간다.
  - import만 해도 `kis_ws`·`kis_ws_pool`·`token_manager` 싱글턴이 생긴다(`websocket.py:975`, `websocket_pool.py:955`, `token.py:438`).
  - 루트 `.dockerignore`에는 `.token_cache`가 없다.
- **테스트 셋**
  1. AST: `journal_worker/**`의 `src` import 0건.
  2. compose 정적 검사(journal_worker 서비스):
     - `env_file`은 `./secrets/journal_worker.env` 하나뿐이고 `.env`는 금지한다. 그 파일의 키는 DSN 하나다.
     - `environment:`는 `TZ`와 `API_REPORTER_KEY=${API_REPORTER_KEY}`(보간, frontend 선례 `docker-compose.prod.yml:46-52`)뿐이다.
     - `KIS_` 0개, `.token_cache` 마운트 없음, `./logs`는 `:ro`, build context는 `./journal_worker`, `ports:` 없음(macro 선례 `:74-76`).
  3. 이미지 환경에 `KIS_` 변수 0개.

---

## 6. 기존 계획서에서 바뀌는 절

**4절 저장 구조**
- 테이블 셋은 그대로 두고 `trade_journal_cursor`(파일 이름·inode·offset)를 더한다.
- `source` 값을 `log_harvest`·`log_restore`·`fallback_inferred`·`reorder_inferred`·`manual_api`·`external`·`unmatched`로 바꾼다.
- `orders`에 칸을 더한다.
  - `fired_line`·`effective_line`
  - `reason_sub`(`gap_below`·`krx_only`·`nxt_open_missing` 등)
  - `signal` JSONB: 사유 줄 원문, 파싱한 숫자, `judge_src`(`log_price`·`log_pct`·`order_price`). kojiro `[kojiro_atr_stop]`은 식 문구가 실제 계산과 달라 숫자만 쓴다.
- `stops.inputs`에 `snapshot_age_s`를 넣는다. `exchange`는 확보한 것만 채운다.

**5절 기록 지점**
- R1~R7·R9를 지운다. R8의 규칙은 W2로 옮긴다(문턱·`eod`·`boot`·`paused`·21:30 규칙 그대로).
- G0·G1·W1·W2·W3와 5절 안전 조건을 새로 적는다.
- A-PURE·A-ATOMIC은 접촉이 0이라 「해당 없음」이 된다.

**7절 개발 단계 — Red 목록**
- **빠지는 것**: ②(호출 자리 AST) · ③(예외 주입) · ④(R5 순서·A3) · ⑥(`note_entry`) · ⑩(엔진 루프 테스트 위생).
- **바꿔 남기는 것**
  - ①은 G1 순수성 검사로 바꾸고, 대입·변이 금지와 deepcopy 테스트를 더한다.
  - ⑤는 G1 허용·금지 호출 목록으로 바꾼다.
  - ⑦ 무장가 차분 테스트, ⑧ 워커 규칙, ⑨ 마이그레이션은 그대로 남는다.
- **더하는 것**
  - **문법 골든 테스트**
    - 사본의 매도 70건·매수 75건.
    - 종목 표기 두 꼴과 `(Reg.S)` 이름.
    - `수동 매도 주문 접수` 꼴 구분.
    - 익일청산 보류 줄 세 문구.
    - 09-29 16:02:21 재시작 직후 매도.
    - 음성 사례: 09-28 HTS 외부 매수 접수 전문 5건(199800, `0000042300`·`0000340300`·`0000345900`·`0000549100`·`0001402000`). 미체결이므로 행을 만들지 않아야 한다.
  - **생산 쪽 문구 고정**: 소스를 읽기만 하므로 런타임 변경은 0이다.
    - 접수·완료 줄: `order_engine.py:2010`·`:1643`, `api/order.py:100`, `routes/trading.py:220`, `handler.py:726` 접두, `[status_exit_fire]`.
    - 폴백 WARNING `order_engine.py:1747`, 재주문 `:3750`.
    - **소비하는 사유 줄 전부**: `[kojiro_hard_stop]`·`[kojiro_atr_stop]`·`[kojiro_trailing]`·`[bfb_turtle_stop]`·`[bfb_turtle_backstop]`·「눌림목 손절」·「롱테일VB 당일 손절」·「롱테일VB 손절(상한가 모드)」·「변동성돌파 손절」·「손절 신호」·`[donchian_time_exit]`.
    - scheduler 보류 줄 3종(`:1415`·`:1457`·`:1518`).
  - **대사 항등식 셋**(2절).
  - **5절 ①~⑤의 테스트 전부.**
  - **배포 분류 테스트**: `test_cycle303_macro_deploy_classification.py` 선례, G-248-2·G-248-5 갱신.

**7절 배포**
- 첫 배포는 full 1회다. 창은 계획대로 10-13 21:35 이후다.
- 순서
  1. 047 마이그레이션
  2. 운영 스크립트로 역할 생성
  3. `./secrets/journal_worker.env` 사전 생성 — 없으면 compose 전체가 실패한다. 사람이 먼저 만드는 규약은 `secrets/.htpasswd`와 같다.
  4. push
- 워커 코드만 바뀌면 그 뒤로는 `journal` 선택 배포다. 빌드 메모리 때문에 장외 창을 권한다(09-18 동시 빌드 장애).
- compose를 고치는 배포는 계속 full이다.

**8절 과거분 복원**
- 워커 파서로 적재한다(3절 「과거분」). 복원분에는 발동선·사유·주문구분(09-28~)만 있고, 유효선은 없다.

**9절 결정**
- D1은 철회하고 E1a·E1b·E1c로 바꾼다(7절). D2는 그대로다. D3의 권고가 바뀐다.

**10절 위험**
- D1 실패 모양 두 가지(R3 재발사, R2·R4 관통)와 R6 이중 매도 위험이 사라진다. 대신 8절의 위험이 들어간다.

---

## 7. 남는 결정

| # | 결정 | 권고 | 이유 |
|---|---|---|---|
| **E1a** (D1 대체) | 구조 B 채택. `journal_worker/`(src 밖) + 기존 G0 사용 + 배포 축 `journal` 신설. D1·R1·R6·R7·R9 철회. **src 0줄** | **승인** | 주문 경로 0줄로 ⑧ 진입·청산 이유, 발동선, 판단가, 주문구분을 얻는다. 일지를 고쳐도 backend를 재시작하지 않는다(compose를 고칠 때는 예외). 이 결정은 `llm_worker`(cycle279)의 미결 항목 「워커 경로·배포 축」(`architecture.md` 15.7)의 첫 선례가 된다 |
| **E1b** | G1 `GET /api/balance/exit-lines`(`balance.py` 약 30줄, KIS·DB 0) | **승인** | ⑥⑦⑨, 청산 순간 유효선, ATR, 무장가를 얻는 유일한 길이다(4절). 거절하면 이 칸들은 빈다 |
| **E1c** | 운영 DB에 워커 전용 역할을 만든다(1회성, 비밀번호는 `./secrets/journal_worker.env`). `DROP ROLE`로 되돌릴 수 있지만 운영 DB 조치라 승인을 받는다 | **승인** | 운영 DSN을 함께 쓰면 앱키 평문과 매매 제어 테이블이 열린다(5절 ①). 거절하면 워커를 띄우지 않고 A안으로 간다 |
| D2 | 메모 저장 위치 | 그대로 DB 테이블 | 변화 없음 |
| D3 | 과거 청산 사유 복원 | **로컬 사본을 파싱해 장외 창에 1회 적재한다. EC2분(10-08~배포일)은 장외 1회성 명령으로 돌린다** | 사본은 확보돼 있다. 파서가 실시간 수확과 같아서 추가 비용이 작다. EC2에서는 대량 파싱을 하지 않는다 |

**지금 정하지 않는 것**
- 폴백·재주문 로그 줄에 `signal.value`와 원주문번호를 넣는 일. `order_engine.py` 2줄이라 8영역 승인 대상이다. 실측이 0/70이라 보류한다. 일지에 「추정」 행이 실제로 생기면 다시 꺼낸다.
- `deploy.yml` 마이그레이션 루프에 `PGOPTIONS='-c lock_timeout=3s'`를 넣는 일. 이 설계 이전부터 있던 위험이라 워크리스트 후속으로 둔다.

---

## 8. 위험·한계

### 체결통보 추가 구독(C안) — 비권고 근거
- **같은 앱키로 붙는 경우**
  - KIS 규칙은 「1계좌(앱키)당 1세션」이다(`docs/kis/rate-limits.md:31`). 거부 코드는 `OPSP8996 ALREADY IN USE appkey`다(`docs/kis/error-codes.md:121`). src 안에는 이 코드를 처리하는 곳이 0건이다.
  - 두 번째 접속을 하면 새 쪽이 거부될 가능성이 높다. 그러면 실제 위험은 이렇다. 워커가 붙어 있는 동안 메인이 재연결하는 순간(F1 재연결, silent inactive 강제 재연결 세션당 시간당 2회, 루트 CLAUDE.md 「세션 단위 silent inactive 자동 reconnect」) 메인이 `OPSP8996`으로 거부된다.
  - 그동안 체결통보가 끊기고, 포지션 등록과 손절이 불가능해진다(`src/realtime/CLAUDE.md:397`).
  - 토큰 발급 분당 1건 잠금이 프로세스 안에만 있다(`src/auth/token.py:77`). 루트 CLAUDE.md도 「로컬과 EC2 동시 실행 금지 — KIS 동일 계정 동시 접속 충돌」을 적고 있다.
- **다른 앱키로 붙는 경우**
  - 앱키 8개가 이미 모두 쓰이고 있다(10-07 `[pool_start] 완료: main=1 quotes=7`). 9번째 앱키는 새로 등록해야 한다(외부 조치).
  - 체결통보는 HTS ID 단위로, 묶인 모든 계좌의 통보가 함께 온다(`rate-limits.md:30`, `src/realtime/CLAUDE.md:287`). 같은 HTS ID를 두 세션에 동시 등록했을 때의 동작은 문서에 없다.
  - EC2 IP를 함께 쓰므로 재연결이 폭주하면 차단 공지 대상이 된다(`rate-limits.md:158`).
  - 우리 코드도 보조 세션의 체결통보를 막는다(`websocket_pool.py:109-118`). 05-19에는 세션 간 AES 키가 섞이는 사고가 있었다.
- **얻는 것이 없다.** 체결통보 26필드에는 사유·손절선이 없다(`src/realtime/CLAUDE.md:286`). 나머지 필드는 `trade_history`와 `[order_notice]`에 이미 있다.
- **워커의 KIS 주문체결조회 REST 폴링도 비권고다.** 초당 20건 제한(`api/base.py:29`)이 프로세스 안에만 있어서, 두 프로세스의 호출이 합쳐지면 주문이 거부될 수 있다.

### 관찰자 방식의 한계
1. **로그 문구가 사실상 계약이 된다.**
   - 파일 통째 sha 핀은 「값만 이동」 재핀이 일상이라 파서를 지키지 못한다(`test_cycle291_ast_scope.py:127-150`).
   - 방어는 두 겹이다. 소비하는 줄 전부의 문구 고정 테스트(6절)와 매일 대사(사유 미상 매도 수 포함)다.
2. **cycle402 전후로 이름별 합산을 하지 않는다.** 10-06 22:11 이전 7/70건은 사유 줄로 보정해 저장한다.
3. **스냅샷 지연**
   - 유효선은 최대 15초 전 값이다.
   - 한 주기 안에 끝난 거래는 최초 손절이 빈다.
   - 재시작 직전 15초 안의 신호는 로그 줄로만 남고, BFB·VCP는 구조값이 빈다.
4. **매도 판단가**는 26건 중 정확 10 · 역산 13 · 상한만 3이다. 과거분은 주문가로 보충할 수 없다(2절).
5. **결합 추정 경로는 실측 표본이 0건이다.** 코드로만 확인했다.
   - 폴백 매도: 같은 종목의 10초 안 사유 줄과 묶는다.
   - 폴백 매수: 2절 ⑧ 진입 이유 칸의 규칙.
   - 재주문
     - 표지는 `손절 잔여 재주문: %s %d주`(`order_engine.py:3750`)다. `[after_cancel_result]`는 세 곳(`:3491`·`:3653`·`:3837`)에서 나와 유일하지 않아 쓰지 않는다.
     - 「`SELL 주문 완료` → 같은 종목·같은 수량의 `손절 잔여 재주문`」 순서와 「접수 줄 없음」을 함께 조건으로 둔다.
     - 원주문은 같은 종목의 직전 매도 접수로 잇는다.
   - 외부: 체결된 것만 행을 만든다.
6. **현행 donchian 가격 청산은 판정 줄이 없다**(`donchian_swing.py:1752-1758`).
   - 이름은 접수 줄에서, 선은 스냅샷에서 얻는다.
   - donchian 손절선은 부팅 때와 무장 순간에만 바뀐다. 그래서 무장 직후 15초 안에 청산된 경우만 어긋난다.
7. **G1은 엔진 이벤트 루프에서 돈다.**
   - 비용은 로컬 ASGI 측정 0.50ms(지금보다 넓은 G1 기준)이고, 분당 4회다.
   - 방어는 5절 ②의 AST와 deepcopy 테스트다.
8. **리포터 키와 묶인다.**
   - 키를 회전하면 워커 컨테이너도 다시 만들어야 한다.
   - 키가 비면 G0·G1이 401을 받아 스냅샷이 멈춘다. 로그 수확은 계속 돈다.
9. **자원 — 2GB 박스, 디스크 19GB**
   - 로그는 거래일 하루 235~376MB이고 14거래일 합이 3.59GB다. 10-07은 2,442,338줄 중 2,404,855줄이 `websockets.client` DEBUG다.
   - 백필은 컨테이너 기동 경로에서 뺀다. 커서는 청크마다 저장해서, 재시작이 반복돼도 처음부터 다시 읽지 않는다.
10. **배포 결합**
    - full 모드는 이미지 4개를 굽는다. 09-18 동시 빌드 장애 계열이고, 현재 `COMPOSE_PARALLEL_LIMIT=1`이 반영돼 있다.
    - **워커 빌드가 실패하면 backend 핫픽스 배포도 막힌다**(`compose_up_changed.sh:265`의 `up --build`). 실패하면 마커가 안 써져 다음 배포도 full이다.
    - 완화: 의존성 2개를 고정하고, push 전에 로컬에서 이미지 빌드를 확인한다.
    - `./secrets/journal_worker.env`가 없으면 compose 전체가 실패한다. 그래서 사전 생성 규약을 둔다.
11. **HTS ID가 워커가 읽는 파일 로그에 평문으로 있다.** 앱키 없이 HTS ID만으로는 구독할 수 없고, 앱키에 닿는 길(`kis_quote_accounts`)은 5절 ①로 막는다.

### 확인 못 함
- EC2 `./logs` 파일을 워커 컨테이너의 uid가 읽을 수 있는지(권한).
- G0·G1의 EC2 실행 시간. 0.50ms는 로컬 측정이고, G0는 측정하지 않았다.
- 워커 메모리 실측값, RDS 연결 수 한도, EC2 docker compose 버전(`env_file` `required: false` 지원 여부).
- RDS 마스터 계정으로 `CREATE ROLE`과 역할 수준 설정을 할 수 있는지.
- `API_REPORTER_KEY` 운영 설정 여부. 20:20 루틴이 쓰므로 설정돼 있다고 가정했다.
- 같은 HTS ID를 두 세션에 동시 등록했을 때 KIS 동작.
- 이 기간 표본이 0건이라 실제 로그를 못 본 것: 폴백 매수·매도, 재주문, 수동, 종목상태 매도, 체결된 외부 주문, `nxt_open_missing` 익일청산, VCP·etf·현행 donchian(cycle405 후) 청산.

**실측 스크립트·추출 파일**: `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/` 아래 `obs/chk.py`·`obs/chk2.py`·`review/bench_g1.py`·`rv/orders.txt`·`rv/strat.txt`

**기존 계획서**: `/Users/koscom/Projects/auto_stock/_workspace/design/2026-10-08_trade_journal_plan.md`

---

## 검토 지적 처리

모든 지적을 수용했다. 일부는 형태를 바꿔 수용했고, 그 이유를 적었다.

| 출처 | 지적 | 처리 |
|---|---|---|
| 안전 1 [높음] | 운영 DSN을 함께 쓰면 앱키 평문·매매 제어 테이블·행 잠금이 열린다 | **수용.** 5절 ①(전용 역할·권한·타임아웃·권한 거부 테스트), 결정 E1c를 신설했다. 비교표 「주문 능력」 문구도 고쳤다 |
| 안전 2 [중간] | G1 허용 목록 AST가 대입·변이를 못 본다 | **수용.** 5절 ②(대입·삭제 대상 제한, `vars`·`__dict__`·변이 메서드 금지, deepcopy 테스트, try 안 직렬화)를 넣었다. 사실 중7을 수용해 G1 범위를 청산선과 값 몇 개로 줄여 변이 면적도 줄였다 |
| 안전 3 [중간] | 호출 빈도 상한 없음, 비용 과소 | **수용.** 5절 ③을 넣었다. 서버 쪽은 429 대신 **5초 캐시**를 골랐다. 429는 워커를 오류·백오프 경로로 자주 보내고, 캐시는 상수 시간에 같은 효과를 낸다. 비용은 0.50ms로 고쳤다 |
| 안전 4 [중간] | 워커 트랜잭션과 `ALTER TABLE trade_history`가 겹치면 체결 처리가 멈춘다 | **수용.** 5절 ④(자동 커밋 단문, 트랜잭션 안 HTTP·sleep 금지 테스트, 역할 타임아웃)를 넣었다. `deploy.yml` `lock_timeout`은 기존 위험이라 검토자 제안대로 워크리스트 후속(7절)으로 뒀다 |
| 안전 5 [중간] | 「KIS 자격 없음」이 문장뿐이다 | **형태를 바꿔 수용.** 테스트 3개를 넣었다(5절 ⑤). 「`env_file` 없음」은 「`.env` 금지, 워커 전용 파일 하나만 허용」으로 바꿨다. 안전 1의 DSN 분리(전용 파일)와 같이 쓰려면 env_file 한 줄이 필요하고, 막아야 할 대상은 `.env`이기 때문이다 |
| 안전 6 [낮음] | 백필·재시작·도커 로그·배포 결합 | **수용.** 백필은 로컬 파싱 + 장외 1회 적재로 하고 기동 경로에서 뺐다. 자원 상한·로그 회전은 첫 배포에 넣는다. 청크마다 커서를 저장하고 1회 읽기량에 상한을 둔다. 워커 빌드 실패가 backend 배포를 막는 결합은 8절 한계 10에 적었다 |
| 안전 7 [낮음] | 근거 문장 세 곳 정정 | **수용.** 리포터 키는 `:262-269`이고 GET/HEAD + POST 1경로다. 비용은 0.50ms다. C안은 「워커가 붙은 동안 메인 재연결이 거부된다」로 작동 원리를 고쳤다(8절) |
| 사실 중1 | 익일청산 갭률은 4/11건뿐이다 | **수용.** 로그를 다시 확인했다(갭 4 · nxt 변형 7). `reason_sub` 세 값과 세 문구 문법을 넣었다 |
| 사실 중2 | cycle374 전 거래가 있다(58건) | **수용.** 「09-28 이후 매도 42/42·매수 45/45, 그 전 58건 빈칸, 복원 범위 87/145」로 고쳤다 |
| 사실 중3 | 발동선 ≠ 유효선 | **수용.** `fired_line`과 `effective_line`을 따로 저장한다. 「D1과 다른 것」을 다시 셌다: 유효선은 26/26 스냅샷, 발동선은 15건 정확 + LTV 5건 계산. 과거분은 차이 건수를 셀 수 없다고 적었다 |
| 사실 중4 | 매수 폴백 경로와 자기 점검이 빠졌다 | **수용.** 결합 규칙(`BUY 주문 완료` + WARNING + `trade_history.strategy`)과 매수 항등식을 넣었다 |
| 사실 중5 | 재주문 표지가 유일하지 않다 | **수용.** 표지를 `손절 잔여 재주문`(`:3750`) + 순서 + 접수 줄 없음으로 바꿨다(8절 한계 5) |
| 사실 중6 | 문구 고정이 사유 줄을 덮지 않는다 | **수용.** 소비하는 사유 줄과 보류 줄 전부를 고정 대상에 넣고, 「사유 미상 매도 수」 대사를 더했다 |
| 사실 중7 | 기존 0줄 GET 두 곳을 빠뜨렸다 | **수용.** G0(`/api/trading/status`)를 진입 신호·파라미터·phase 출처로 쓰고, G1을 청산선 + ATR + 무장가로 줄였다. 결정을 E1a(src 0줄)와 E1b(G1)로 나눴다. `/api/strategies`는 같은 `get_strategies_status`를 주므로 G0 하나로 충분하다. 비용은 「대시보드 5초 폴링의 1/3」로 비교했고, EC2 실측은 「확인 못 함」에 넣었다 |
| 사실 하1 | 「첫 배포만 full」이 아니다 | **수용.** compose를 고치면 full이라고 적고, 자원 상한을 첫 배포에 넣었다. 이미지 4개도 적었다 |
| 사실 하2 | 리포터 키 범위와 DB 권한 | **수용.** 안전 1·7과 함께 처리했다 |
| 사실 하3 | 종목명 없는 꼴에서 정규식 실패 | **수용.** 두 꼴을 받는 파서 규칙과 골든 사례를 넣었다 |
| 사실 하4 | 0초 51·1초 24는 신호 줄 기준이 아니다 | **수용.** 0초 49 · 1초 26으로 고쳤다 |
| 사실 하5 | 과거분은 주문가로 보충할 수 없다, 분포가 섞였다 | **수용.** 2절 판단가 칸과 8절 한계 4에 반영했다 |
| 사실 하6 | 외부 표본이 0건이 아니다 | **수용.** 09-28 미체결 외부 접수 5건을 음성 골든으로 넣고, 「체결된 외부 표본 0건」으로 고쳤다 |
| 사실 하7 | 거래소 「어디에도 없다」는 과장이다 | **수용.** 「일부만 확보」(`llm_buy_evaluations.exchange`, `[order_channel]`)로 고쳤다 |
| 사실 하8 | 재시작 직후 매도 표본 | **수용.** 09-29 16:02:21 030530을 골든에 넣었다(3절 부팅 처리) |
| 사실 하9 | 링버퍼 손실 창 30초, 인용 줄, LTV 개선 여지 | **수용.** 스냅샷과 로그 읽기를 한 회전에 묶고 신호를 링에 보관해 창을 15초로 줄였다. 인용을 고쳤다(20건 상한은 각 전략 append 자리, 예 `volatility_breakout.py:1046-1047`; `main.py:163-164`). LTV는 **청산 순간** 발동선만 계산한다. 보유 중 ⑥⑦의 LTV는 계획대로 빈칸으로 둔다. `_limit_up_reached`를 G1으로 내보내는 것은 새 제안이라 넣지 않았다 |