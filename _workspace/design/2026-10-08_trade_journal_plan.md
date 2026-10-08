# 거래일지 세부 실행 계획서 (최종)

## 요약

1. 「거래내역」 메뉴에 세 번째 탭 「거래일지」를 둔다. 보유 한 번(진입부터 청산까지)을 카드 한 장에 보이고, 필수 10개 항목을 모두 담는다.
2. 새로 기록하는 것은 네 가지다: 진입 이유, 청산 이유, 보유 중 손절선 변화, 메모. 일자·가격·수수료/세금·체결오차(주문가 기준)·최대 평가손익은 기존 데이터를 읽을 때 계산한다.
3. 손절선과 목표가는 잔고 화면이 이미 쓰는 `position_exit_lines.resolve_exit_lines`(cycle339 — 잔고 화면 손절가·목표가 표시)를 그대로 쓴다. 그래서 두 화면의 값이 같다. 전략 식을 복제하는 곳은 donchian 무장가 한 줄뿐이다.
4. 매매 행위는 바뀌지 않는다. DB 쓰기는 별도 60초 루프에만 있다. 매매 경로의 기록 호출은 모두 「함수 내부 try + 호출 자리 try」 이중 보호로 감싼다.
5. 1a(기록)는 8영역·scheduler를 0줄 고치고도 할 수 있다. 다만 청산 사유를 주문번호에 정확히 묶으려면 `order_engine.py` 약 27줄이 필요하다(D1 승인 필요).
6. 검토 결과 실패 모양이 두 가지로 확인됐다.
   - 주 경로의 기록 호출이 예외를 내면 **매도가 다시 나간다**.
   - R2 위치와 폴백 경로에서 예외가 나면 `execute_sell` 밖으로 샌다. 그러면 `_selling` 좀비가 생겨 손절이 최대 약 15분 멈추고, 그 틱의 처리와 15:20 강제청산 루프도 중단된다.
   - 그래서 호출 자리마다 `except Exception` 하나만 둔 try를 AST 테스트와 행위 테스트로 강제한다.
7. 배포 시점:
   - 1a는 10-13 주계좌 전환을 확인한 뒤 첫 장외 창에 배포한다(권고: 10-13 21:35 이후).
   - 1b(화면)는 c411 실비용 기능이 병합·배포된 뒤에 한다.
8. 결정할 것은 세 가지다: D1(`order_engine.py` 약 27줄) · D2(메모를 DB에 저장) · D3(EC2 로그 사본 확보 — 보관 기간이 20일이라 시한이 있다).

---

- **기준**
  - main: `669170d5`(2026-10-08).
  - 실비용 기능: `/Users/koscom/Projects/auto_stock_c411`(feat/cost-overlay) HEAD `72cb53fd`.
    - 10-08에 다시 확인했다. 보완분까지 커밋됐고, 작업 트리에는 추적하지 않는 진행 로그 1개만 남아 있다.
    - 이 문서의 c411 인용 줄은 모두 이 HEAD 기준이다.
- **읽기만 했다**
  - 코드와 DB는 읽기만 했고 테스트는 돌리지 않았다. 운영 DB에도 접속하지 않았다.
  - 운영 파라미터 값은 메모리 실측표(09-20)와 워크리스트에서 옮긴 것이고, 오늘 값은 확인하지 못했다.
- **앞선 설계에서 바꾼 점**
  1. 진입 기록은 `trade_history.insert_trade` 훅이 아니라, 이미 있는 주문 시점 훅 `llm_buy_gate.observe_order`에 붙인다. 그러면 c411도 고치는 `src/db/trade_history.py`를 건드리지 않는다.
  2. 수량 산정 근거(`strategy_base.py` +15~20줄)는 10개 필수 항목에 없으므로 2단계로 미룬다. 1단계에서 `strategy_base.py`는 0줄이다.
  3. 손절선 계산을 새로 만들지 않는다. 잔고 화면 leaf `position_exit_lines`를 재사용한다. 그래서 momentum·VB·LTV 식 복제와 그 차분 테스트를 없앤다.
  4. `order_engine.py` 변경은 약 27줄이다. 기록 호출이 실패하는 모양이 위치마다 다르기 때문이다(5절). 주 경로에서는 재발사가 되고, R2·폴백에서는 `execute_sell`을 뚫고 나간다.

---

## 1. 한눈에 보기

**만드는 것**
- 「거래내역」 메뉴에 세 번째 탭 「거래일지」를 둔다. 지금 탭은 `orders`·`pnl` 두 개다(`frontend/src/pages/History.tsx:5`).
- 진입부터 청산까지 보유 한 번을 카드 한 장으로 보인다. 묶는 단위는 「매매손익」 탭과 같은 `get_trade_pairs()` 페어다(`src/db/trade_history.py:649`).

**새로 기록하는 것 (네 가지)**
1. **진입 이유**: 신호 값, 판단가, 주문구분, 진입 시점 파라미터 사본. 주문 1건에 1행.
2. **청산 이유**: 청산 신호, 판단가, 청산 순간 손절선. 주문 1건에 1행. 결정 D1이 필요하다.
3. **보유 중 손절선 변화**: 잔고 화면과 같은 leaf로 읽는다. BFB 목표가(도달 여부 포함)와 donchian 무장가도 함께 남긴다. 값이 바뀔 때, 장마감 때, 부팅 때 기록한다.
4. **사용자 메모**: 페어 1건에 1개.

**읽을 때 계산하는 것 (새 기록 없음)**
- 일자·가격: `trade_history`.
- 수수료/세금: c411 `cost_overlay.trade_costs()`·`overlay_pairs()`.
- 체결오차(주문가 기준): `trade_history.order_price`. 공식은 c411과 같다.
- 최대 평가이익/손실: `stock_master_daily` 종가.

**매매 행위 변경은 0이다.**
- 기록 함수는 예외를 밖으로 내지 않고, 결과를 기다리지 않는다.
- 손절 주문이 나가기 **전**에 더하는 일은 R2의 dict 조회 몇 번뿐이다. 손절선 계산은 주문이 나간 **뒤**(R3·R4) 또는 별도 루프(R8)에서 한다.

**8영역·scheduler 접촉**

| 파일 | 1단계 | 2단계(선택) |
|---|---|---|
| `src/engine/scheduler.py` (3,737줄, 상한 <3,900) | **0줄** | 0줄 |
| `src/engine/risk.py` | **0줄** | 0줄 |
| `src/engine/order_engine.py` (3,845줄) | **D1 승인 시 약 27줄**: `execute_sell` 3곳(R2 `:1817` 뒤 · R3 `:1995` 뒤 · R4 `:2417` 뒤) + `_cancel_and_reorder` 1곳(R5 `:3749` 뒤). 모듈 최상단 import는 0이고, 함수 안에서 지연 import한다. 승인하지 않으면 0줄 | `execute_buy` `:1395`·`:1428`(수량 클램프 기록). A-ATOMIC 구간 안이라 별도 승인과 `_ATOMIC_SEGMENT_SHA` 재핀이 필요하다(7절) |
| `session.py`·`scanner.py`·`strategy_registry.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**` | 0줄 | 0줄 |

- **8영역 밖에서 고치는 파일**: `src/engine/llm_buy_gate.py`(약 7줄), `src/engine/boot_manager.py`(약 6줄), `src/routes/trading.py`(약 6줄).
- **새로 만드는 파일**: 마이그레이션 1개, `src/engine/trade_journal.py`, `src/db/trade_journal.py`. 화면 단계에서 `src/engine/journal_view.py`를 더한다.

---

## 2. 10개 필수 항목

출처 표기: **있음** = 이미 DB에 있음 · **기록** = 새로 기록 · **계산** = 읽을 때 계산.

| 항목 | 출처 | 기록·계산 위치 | 과거 거래 복원 범위 | 주의점 |
|---|---|---|---|---|
| ① 일자(진입) | 있음 | `trade_history.timestamp`(`001_init.sql:4`). INSERT 때 `datetime.now(KST)`로 찍는다(`trade_history.py:96`). 페어의 `buy_date`·`buy_time` | 전체(2026-04-22~) | 대부분은 PENDING INSERT 시각, 곧 **주문 접수 직후 시각**이다. 체결 UPDATE는 이 칸을 바꾸지 않는다. 예외가 둘 있다. (a) 체결통보가 PENDING보다 먼저 와서 넣은 **보정 INSERT 행에는 체결통보 처리 시각**이 찍힌다. (b) 부팅 동기화 행(HTS 수동 매매·누락분)에는 **부팅 시각**이 찍힌다(`scheduler.py:2277-2375`) |
| ② 일자(청산) | 있음 | 위와 같음. `sell_date`·`sell_time` | 전체 | 위와 같다. 분할 매도면 페어는 마지막 매도 시각만 준다 |
| ③ 가격 | 있음 | `trade_history.price`. 페어의 `buy_price`/`sell_price`(주문들의 가중평균) | 전체 | 매수는 **마지막 체결통보 가격**이다(`order_engine.py:2913-2914`). 매도는 주문 단위 가중평균을 원 단위로 내린 값이다(`order_engine.py:347-357`). `mark_pending_buys_completed` 행에는 주문가가 그대로 남는다(`trade_history.py:340`) |
| ④ 체결오차 | 있음 + 기록 + 계산 | 두 기준을 함께 보인다(아래 표 밖 설명 참고). 표시는 「불리하면 +」, 원과 bp를 함께 쓴다 | 아래 설명 참고 | 아래 설명 참고 |
| ⑤ 수수료/세금 | 계산 | c411 `trade_costs()`(`cost_overlay.py:127-189`)를 페어의 **세 묶음** `buy_trade_ids` / `sell_trade_ids` / `partial_sell_trade_ids`(c411 `src/db/trade_history.py:788-791·872-876`)로 나눠 합친다. 진입 = buy. 청산 = sell(닫힌 페어) 또는 partial_sell(보유 중 분할 매도). 페어 합계와 세후 손익은 c411 `overlay_pairs()`(`cost_overlay.py:247-371`) 값을 그대로 쓴다. 그래서 「매매손익」 탭과 같은 숫자가 나온다 | 정산값: 08-21~ + 매일 대사분. 그 전은 추정 | 주문 단위 원천이 없어서 (날짜·종목) 정산값을 금액 비율로 나눈 값이다. 추정값은 다음 영업일 21:10 대사 뒤 자동으로 정산값으로 바뀐다. 그래서 **값을 저장하지 않는다**. 비용 조회가 실패하면 0이 아니라 `None`이다(c411 M4, `src/routes/history.py:159-163`). 10-12 체결분은 정산이 빈칸으로 남을 수 있다(c411 조사) |
| ⑥ 손절 가격(최초) | 기록 | `trade_journal_stops`의 `first` 사건(R8, 60초 주기). 값은 `resolve_exit_lines([전략], 종목)`(`position_exit_lines.py:179-220`)이 준다. 잔고 화면과 같은 값이다. 루프가 보기 전에 끝난 거래는 청산 순간 값(R3·R4)으로 채운다 | **복원 불가**. 당시 파라미터 이력이 없다 | 체결 뒤 60초 안 첫 관측값이다. 출처는 셋이다: 5전략 = `effective`, momentum·VB = `hard_pct`(고정% 근사), LTV = 빈칸(`mode_dependent`, 3절). 과거 거래를 지금 파라미터로 계산하지 않는다. 손절률이 여러 번 바뀌어 와서(메모리 실측표) 틀린 값이 된다 |
| ⑦ 조정한 손절가격 | 기록 | `trade_journal_stops`의 `change`·`eod`·`boot`·`paused` 사건(R8) | 복원 불가 | **손절선은 내려갈 수도 있다.** 밤사이 재구성, 재시작, ATR 변화, 파라미터 PUT, 분할 체결이 원인이다. 내려간 값도 원인 입력과 함께 남긴다. `hard_pct` 근사는 트레일을 담지 못한다(momentum D+1 트레일 등) |
| ⑧ 이유(진입/청산) | 기록 | 진입: R1 `note_entry`(신호 dict 원본 + 파라미터 사본). 청산: R3·R4·R5(신호 + 경로, D1). 수동 API 매도: R6 | 진입: 09-11 이후 `llm_buy_evaluations` 일부(파생 칸만 있음). 청산: `system_logs` INFO는 2일 보관이다(`system_logs.py:32`). EC2 파일 로그는 20일 + 당일 보관이다(`src/main.py:108·116-121`, 호스트 bind mount `docker-compose.prod.yml:14`). 이것을 쓸지가 D3이다 | VB·LTV의 `target_price`는 매수 트리거 가격이다. 익절가로 쓰지 않는다. HTS 외부 매도와 잔고부족 정리는 사유가 없다(「외부·매핑 없음」으로 표시) |
| ⑨ 익절목표가 | 기록 | BFB: `get_effective_target_price`(`bull_flag_breakout.py:1363`). 반환값이 `(target, already_hit)`이라 `target_price`와 `target_hit`로 나눠 저장한다. 진입 메모의 신호 `target_price`(측정 목표)도 남긴다. donchian: 「3R 무장가」를 **별도 칸**에 둔다 | BFB 과거분은 불가. `llm_buy_evaluations.target_won`은 `flag_high`라 측정 목표가가 아니다 | 숫자가 들어가는 전략은 BFB 하나다. 나머지는 「없음 — 트레일링/추세/시간 청산」으로 표시한다(3절). BFB는 목표에 닿으면 **전량** 매도한다. 신호가 `TAKE_PROFIT`이고(`bull_flag_breakout.py:1334` 주석 「1차 구현: 전량 청산 신호」), `execute_sell`이 `send_qty = pos.quantity`로 판다(`order_engine.py:1974`). `position_exit_lines.py:31-33` 문서는 「부분 익절 트리거」라고 적혀 있지만, 화면 문구는 코드 기준으로 쓴다 |
| ⑩ 최대 평가이익·손실(일별 종가) | 계산 | `stock_master_daily` 날짜 범위 읽기 함수(새로 만듦) + `journal_view` | 06-12(테이블 생성, migration 033) 이후 거래는 대체로 가능. **04-22~06-11 거래는 확인 못 함**: 최초 적재는 T-100 + 점진 적재였는데(`033_stock_master_daily.sql:1-4`), 그 종목이 적재 대상이었는지는 코드로 알 수 없다. 착수 전에 페어별 종가 보유율을 실측한다(읽기 SELECT) | 15:30에 들고 있던 날의 종가만 쓴다. VB·LTV는 대부분 「해당 없음」이다(보유 중 종가 0개). 종가는 수정주가라 액면분할이 끼면 표시만 한다. 2027-05-17부터 390일 보관 기간에 걸려 지워지기 시작한다 |

**④ 체결오차 — 두 기준**

- **주문가 기준** = `trade_history.order_price`(migration 046, cycle409 — 주문가 기록).
  - 공식은 c411 `overlay_pairs`(`cost_overlay.py:356-369`)와 같다. 불리하면 +: 매수는 체결가 − 주문가, 매도는 주문가 − 체결가.
  - 일지는 진입과 청산을 나눠 보인다. 닫힌 페어의 진입 + 청산 합은 c411 `slippage_won`과 같아야 한다. 이것을 패리티 테스트로 묶는다.
- **판단가 기준** = 매수는 R1 `current_price_won`, 매도는 R2(신호 시점 시세).
  - 시장가 매수는 주문가가 곧 판단가라 두 기준의 값이 같다(`order_engine.py:1568-1571`, `trade_history.py:65-80`).
  - 차이가 나는 경우는 셋이다.
    - 지정가로 바꿔 낸 매수(프리장 변환, 5호가 폴백).
    - 체결통보가 먼저 와서 생긴 보정 행. `order_price`가 NULL이다.
    - 매도. `order_price`는 `await place_order` **뒤** 시세다(`order_engine.py:222-236`, 호출 `:1307`).
- **과거 범위**
  - 매수 주문가: 10-07 거래부터 모든 자동 매수에 있다(cycle409는 10-06 22:11 배포, 워크리스트 「10-06 밤 실행 결과」). 보정 행은 빠진다. 09-11~10-06은 `llm_buy_evaluations` 행이 있는 주문만 된다.
  - 매도 주문가: 10-07~.
  - 판단가: 1a 배포 뒤부터.
- **주의점**
  - 주문구분은 `trade_history`에 없다. 지금은 메모리 `_order_division`(`order_engine.py:1995`)에만 있어서 R1·R3이 기록한다.
  - 폴백 매수는 `observe_order(order_division="LIMIT")`로 넘어온다(`order_engine.py:1718`). R1은 이 값을 `OrderDivision.LIMIT.value`로 바꿔 저장한다.
  - 5호가 폴백은 「쿠션 안 개선폭」이라 시장가와 따로 표시한다.
  - D1을 승인하지 않으면 매도 판단가는 없고, 주문가 기준만 보인다.

---

## 3. 전략별 표

- 식은 코드 기본값이다. 괄호 안 「운영」은 메모리 실측표(09-20, `memory/project_live_db_param_deltas.md`) 값이고, 오늘 값은 확인하지 못했다.
- E = 체결 매수가(`pos.buy_price`, 분할 체결이면 마지막 체결가). N = 진입 때 스탬프한 ATR.
- 「일지 손절선 출처」는 `resolve_exit_lines`의 `stop_source`다.

| 전략 (현재 운용) | 최초 손절 식 | 손절이 바뀌는 길 · 가격과 무관한 청산 | 익절 목표 | 일지 손절선 출처 | 진입 이유 키 (`buy_signals`) |
|---|---|---|---|---|---|
| momentum (비중 0.03) | `E×(1+stop_loss_rate/100)`. 코드 −7.5 / 운영 −5 (`momentum.py:211-219`) | D+1 08:00:30에 갭 ≥ `gap_up_threshold`이면 트레일 `고점×(1+trailing_stop_rate/100)`(코드 −2 / 운영 −1.3)이 생기고, 유효선은 둘 중 높은 쪽이다(`:246-255`). 갭이 작으면 09:00 `NEXT_DAY_CLEAR`(`scheduler.py:1498-1525`). 갭 모드는 저장되지 않는다. 파라미터 PUT은 즉시 반영된다 | 없음 | `hard_pct`(고정선만. 트레일은 청산 신호로 사후 확인) | `price`·`prev_close`·`change_rate`·`time`(`momentum.py:187-194`) + 파라미터 `buy_threshold` |
| volatility_breakout (10-06부터 섀도·비중 0) | `E×(1+s/100)`, s = 보드별 `stop_loss_{board}`. 운영은 셋 다 −5, 코드 −3 (`volatility_breakout.py:1170-1207`) | 트레일 없음. 실패 돌파 조기청산(기본 꺼짐)도 같은 `STOP_LOSS`(`:1242-1276`). 15:20 `FORCE_CLEAR`. **D+1 `NEXT_DAY_CLEAR` 안전망**(`:1285-1292`. 익일청산 대상에 VB 포함 `scheduler.py:1343-1347`) | 없음. `target_price`는 매수 트리거 가격이다 | `hard_pct` | `price`·`target_price`·`k`·`board`·`change_rate`·`time`(`:1036-1045`) |
| long_tail_volatility (비중 0) | 당일 모드 `E×(1+intraday_stop_loss/100)`. 코드 −3 / 운영 −5 (`long_tail_volatility.py:1108-1112`) | ① 전일 대비 +29%에 닿으면 상한가 모드로 바뀌고 선은 `overnight_stop_loss`가 된다. 운영값(−5 → −3.5)으로는 **조여진다**(`:1101-1124`). ② D+1: 갭 < 문턱이면 `NEXT_DAY_CLEAR`(`:1090-1092`), 갭 ≥ 7(운영)이면 앵커를 당일 시가로 다시 넣고 트레일한다(`scheduler.py:1478-1488`). D+2에 다시 넣으면 **내려갈 수 있다**. ③ **15:20 강제청산**: 당일 모드 전부 + 상한가 모드 ∧ 당일 매수 ∧ 15:20 등락률 < 문턱(cycle352 — 상한가 유지 확인, `limit_up_close_hold_mode` 기본 `enforce`, `:180`·`:1254-1262`). ④ `_limit_up_reached`는 메모리 전용(`:196`)이다. 재시작하면 비어서 **당일 모드로 돌아간다**. 다시 들어가는 길은 +29% 재도달(`:1120`)과 D+1 갭 경로뿐이다 | 없음 | **빈칸**(`mode_dependent`). 잔고 화면과 같다(9절 기본값) | VB와 같다(`:930-939`) |
| donchian_swing (0.25) | `E − R`, R = `max(kk_r_floor_pct 8% × E, kk_r_atr_mult 1.5 × N)` (`donchian_swing.py:1692-1716`) | 고점 ≥ `E + kk_breakeven_r(3.0)×R`이면 손절선이 본전이 된다. 래치가 없어 매번 다시 계산한다. 무장 뒤에는 10일 저가 채널을 본다. 채널은 부팅 때 하루 1번 바뀐다(`:833-837`). **15:20 `TIME_EXIT`**: 20봉째에 +1R 미도달이거나 250봉이면 청산한다(`kk_time_exit_bars`·`kk_time_exit_min_r`·`kk_max_hold_bars`, `:166-168`·`:1779-1831`). `kk_*` PUT은 즉시 반영된다 | **없음.** 3R 무장가 `E+3R`과 1R 시간청산 면제선 `E+R`은 별도 칸에 둔다(5절) | `effective` | `price`·`donchian_high`·`atr`·`time`(`:1657-1665`). 신호 `atr`(`:1662`)과 스탬프 N(`_kk_design_lot` `:1833~`)은 같은 원천이다 |
| kojiro (0.30) | `max(E×(1+hard_stop_pct(−8)/100), E − stop_atr(2.0)×ATR)` (`kojiro.py:1057`, `:1071`) | 2ATR 바닥선은 오르기만 한다(`:1068-1075`). 다만 **재시작하면 현재 ATR로 다시 계산돼 낮아질 수 있다**(`:872-874`). 본전 승격(코드 0 / 운영 1.5, `:1077-1088`). 2.5ATR 샹들리에(`:1115-1122`)는 오르기만 하는 선이 아니다 | 없음. 스테이지3에서 `TREND_EXIT` | `effective` | `name`·`price`·`stage`·`atr`·`time`(KST)(`:1033-1038`) |
| vcp_breakout (0.20, 운영 turtle) | 스탬프가 있으면 `min(E−2N, E×(1+turtle_min_stop_pct(−5)/100))` + 받침선 `E×(1+turtle_backstop_pct(−9)/100)`. 없으면 `E×(1+stop_loss_rate(−7)/100)`. 처음부터 `base_low`·샹들리에·ema50 선도 함께 걸린다(`vcp_breakout.py:1628-1724`) | 본전 승격, 샹들리에(고점 따라 움직임), atr14·ema50(하루 1번). 재시작 때 `base_low`를 다시 찾지 못하면 그 선이 사라진다 | 없음 | `effective` | `price`·`base_high`·`atr`(`:1555-1563`). `base_low`·`ema50`은 없다 |
| bull_flag_breakout (0.20, 운영 turtle) | 스탬프가 있으면 `min(E−2N, E×(1−4%))` + 받침선 `E×(1−7%)`. 없으면 `E×(1−5%)`. 처음부터 `flag_low`·샹들리에도 걸린다(`bull_flag_breakout.py:1244-1348`) | 본전 승격(운영 1.5), 샹들리에 atr14(하루 1번). **`TIME_EXIT`**: `max_hold_days` 5(`:132`)를 달력일 + 2일로 센다(`:1350-1359`) | **있음.** `flag_high + (pole_high − pole_start)`. 신호 순간에 정해지고, 닿으면 **전량** `TAKE_PROFIT`(`:1316-1335`). 재시작 뒤에는 다시 찾은 값이 될 수 있다 | `effective` + 목표·도달 여부 | `price`·`flag_high`·`target_price`(측정 목표)·`atr`(`:1165-1174`) |
| etf_trend (10-06 21:37부터 실매수 0.02) | `max(E − 2N, E×(1−9%))`. 조이는 쪽이다(`etf_trend_core.py:112-116`) | **부팅 때만** 바뀐다. 매수일을 포함한 완성 일봉 고가로 본전(E+1.5N), 트레일 `hsb−1.8N`, 10일 저가 채널을 정한다(`etf_trend.py:363-371`, `:802-822`) | 없음. 15:20 돌파 실패 시 `TREND_EXIT` | `effective` | `price`·`open_price`·`line`·`atr`(`:225-234`) |

**지금 유효한 손절선을 읽는 방법**
- 일지는 잔고 화면 leaf `position_exit_lines.resolve_exit_lines`(cycle339)를 그대로 부른다. 이 leaf는 read-only이고 예외를 내지 않으며 await·DB·HTTP가 0이다(`position_exit_lines.py:1-50`).
- 5전략(BFB `:1409`, etf `:404`, donchian `:1761`, kojiro `:1247`, VCP `:1727`)은 `get_effective_stop_price` 값을 쓴다(`effective`).
- momentum·VB는 기본 구현이 `None`이라(`strategy_base.py:1387`) `hard_pct` 근사로 물러난다(`position_exit_lines.py:119-150`).
- LTV는 모드가 메모리에만 있어서 숫자를 내지 않는다(`_MODE_DEPENDENT_STOP_STRATEGIES`, `:75`). 이 leaf의 원칙은 「틀린 손절가는 없는 것보다 나쁘다」이다.
- 같은 이름(`get_effective_stop_price`)을 전략에 새로 만들면 계좌 SOFT 게이트(`account_risk_watcher.py:406-420`)가 그 값을 집어 가서 매수 행위가 바뀐다. 그래서 일지 leaf는 이 이름을 정의하지 않는다.

---

## 4. 저장 구조

마이그레이션은 `supabase/migrations/047_trade_journal.sql` 하나다.
- main과 c411 모두 마지막 번호가 046이다. 착수할 때 번호를 다시 확인한다.
- 전부 `CREATE TABLE IF NOT EXISTS`·`CREATE INDEX IF NOT EXISTS`로 쓴다. **기존 테이블은 바꾸지 않는다.**
- `trade_history`에 칸을 더하지 않는 이유는 두 가지다.
  - 배포가 마이그레이션 실패를 건너뛴다. 칸 추가가 실패한 채 코드가 그 칸을 쓰면 거래기록 INSERT 자체가 깨질 수 있다.
  - c411이 `src/db/trade_history.py`를 고치고 있어서 충돌하기 쉽다.

### 4-1. `trade_journal_orders` — 주문 1건에 1행 (진입·청산 메모)

| 칸 | 형식 | 뜻 |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `order_date` | DATE NOT NULL | 주문일(KST) |
| `order_no` | TEXT NOT NULL | KIS 주문번호 |
| `side` | TEXT NOT NULL | `BUY`/`SELL` |
| `strategy`, `ticker` | TEXT NOT NULL | |
| `source` | TEXT NOT NULL | `auto`·`fallback`·`reorder`·`manual_api`·`log_tap`·`log_restore` |
| `reason_code` | TEXT | 매수 `ENTRY` · 매도 `Signal.value`(`STOP_LOSS` 등) · `MANUAL` |
| `judge_price` | INTEGER NULL | 판단가(매수 = `current_price_won`, 매도 = R2 신호 시점 시세) |
| `order_price` | INTEGER NULL | 주문가 |
| `order_division` | TEXT NULL | `01`·`00`·`27`·`41`·`44` 같은 코드값만. 폴백 매수의 `"LIMIT"` 문자열은 `OrderDivision.LIMIT.value`로 바꿔 넣는다 |
| `exchange` | TEXT NULL | |
| `parent_order_no` | TEXT NULL | 재주문이면 원 주문번호 |
| `signal` | JSONB NULL | 매수: 그 종목의 최신 신호 dict 원본. 매도: R2 원시값(E·고점·수량·`_entry_atr`·시세) + R3 시점 손절선·목표가·`stop_source` |
| `params` | JSONB NULL | 진입 시 전략 파라미터 사본 |
| `noted_at` | TIMESTAMPTZ NOT NULL | 메모 시각 |

- `UNIQUE (order_date, order_no, side)`를 둔다. KIS 주문번호는 하루 단위로만 유일하다. 10-13 계좌 전환은 날짜 경계에서 일어나므로 충돌하지 않는다.
- 쓰기는 `ON CONFLICT DO NOTHING`이다. 처음 쓴 값을 지킨다.
- 「이유 한 줄」 문장은 저장하지 않는다. 읽을 때 `signal`·`params`로 만든다. 그래야 문구를 나중에 고쳐도 과거 행이 따라온다.

### 4-2. `trade_journal_stops` — 손절선 사건

| 칸 | 형식 | 뜻 |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `strategy`, `ticker` | TEXT NOT NULL | |
| `buy_date` | DATE NULL | `Position.buy_date`(`strategy_base.py:83`). **보조 키**다(아래 주의) |
| `pos_order_no` | TEXT NULL | `Position.order_no`(`:81`). 부팅 복구분은 비어 있을 수 있다 |
| `observed_at` | TIMESTAMPTZ NOT NULL | |
| `event` | TEXT NOT NULL | `first`·`change`·`boot`·`eod`·`paused`·`exit`(`exit` = R3·R4의 청산 주문 순간 값) |
| `stop_price` | INTEGER NULL | NULL이면 계산 불가 또는 모드 의존 |
| `stop_kind` | TEXT NULL | `resolve_exit_lines`의 `stop_source` 그대로: `effective`·`hard_pct`·`mode_dependent`. 2단계에서 「걸린 선」 이름이 들어간다 |
| `target_price` | INTEGER NULL | BFB 측정 목표 |
| `target_hit` | BOOLEAN NULL | BFB `already_hit`(`_partial_exit` 래치, 읽기만) |
| `arm_price` | INTEGER NULL | donchian 3R 무장가 |
| `inputs` | JSONB | E·N/ATR·고점·바닥선·무장 여부·래치·관련 파라미터·당시 가격 |

- 인덱스는 `(strategy, ticker, observed_at)`이다.
- **페어와 잇는 기준**은 `(strategy, ticker)` + 기간 겹침이다. `buy_date`는 보조로만 쓴다. 부팅 복구분의 `buy_date`는 추정값일 수 있기 때문이다.
  - DB `buy_date`가 NULL이면 **어제**로 채운다(`boot_manager.py:311`).
  - KIS 잔고에만 있는 포지션은 어제 또는 오늘로 정한다(`boot_manager.py:352-387`).
  - 잔고 동기화로 만든 포지션은 기본값 **오늘**이다(`scheduler.py:3398-3404` → `strategy_base.py:83`).
- 같은 날 같은 종목을 팔고 다시 사는 것은 막혀 있다(`strategy_registry.py:94-97`). 전략끼리 같은 종목을 함께 사는 것도 막혀 있다. 그래서 `(strategy, ticker)`와 기간으로 보유 1회를 가를 수 있다.

**손절선을 언제 기록할까 — 권고: 「바뀔 때만 + 장마감 1번 + 부팅 1번」, 60초마다 확인**
- **틱마다 기록하지 않는 이유**: `risk.on_tick`(8영역)을 고쳐야 한다. 그리고 샹들리에가 고점을 따라 매 틱 움직여 행이 크게 늘어난다.
- **하루 1번만 기록하지 않는 이유**: 장중 본전 승격과 청산 직전 선을 놓친다. 복기의 핵심이 이 두 가지다.
- **문턱**
  - 내려가면 1원이라도 기록한다. 하락은 그 자체가 복기 대상이다.
  - 올라가면 직전 기록보다 0.5% 이상이거나 `stop_kind`가 바뀔 때 기록한다.
  - 15:30 이후 첫 확인 때 `eod`를 1번 남긴다.
- **행 수 어림**: 보유 15종목 × 하루 5행 안팎이면 하루 약 75행, 1년 약 2만 행이다.
- **부팅 뒤 이어 붙이기**
  - 루프는 보유 중인 `(strategy, ticker)`마다 마지막 행을 SELECT 1회로 읽는다.
  - 그 행 **뒤에** 그 보유를 닫는 매도(페어 종료)가 `trade_history`에 있으면 새 보유로 보고 `first`를 쓴다.
  - 없으면 같은 보유로 이어 보고, 값이 다르면 `boot`를 쓴다.
  - 분할 매도는 페어를 닫지 않으므로 이어진다.
- **21:30 처리**: `positions.clear()`(`scheduler.py:3546`)로 포지션이 사라져도 **청산으로 해석하지 않는다.** 청산 여부는 `trade_history`로 판단한다.

### 4-3. `trade_journal_notes` — 메모 (D2)

| 칸 | 형식 | 뜻 |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `anchor_trade_id` | UUID NOT NULL UNIQUE | 페어의 첫 매수 `trade_history.id`. 외래키는 걸지 않는다 |
| `strategy`, `ticker`, `buy_date` | 중복 칸 | 페어 묶음 규칙이 바뀌었을 때 다시 연결하는 용도 |
| `body` | TEXT NOT NULL | API에서 4,000자 이하로 검증 |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

페어 1건에 메모 1개이고, 덮어쓰기(upsert)로 저장한다.

---

## 5. 기록 지점 상세

| # | 무엇 | 파일·함수·위치 | 동기/비동기 | 예외가 새면 생기는 일 · 처리 | 8영역 |
|---|---|---|---|---|---|
| R1 | 진입 메모 | `src/engine/llm_buy_gate.py` `observe_order`(`:841`). 카나리아 `_emit_config_canary`(`:868`) 뒤, `if mode != "shadow"`(`:870`) **앞**. 이렇게 두면 LLM 모드·하루 상한과 상관없이 모든 자동 매수 주문이 잡힌다(주 경로 `order_engine.py:1600`, 폴백 `:1710`. 매수 발사는 이 두 곳뿐 — `:1557`·`:1682`). 신호 dict는 기존 `_match_signal`(`:699`)로 고른다. `"LIMIT"`은 코드값으로 바꾼다 | 동기. **메모리 dict에 복사만** 한다. `create_task`가 없어서 `test_c19_1`(mode=off면 task 0건, `test_cycle276_order_time_hook.py:730-747`)이 그대로 통과한다. `trade_journal`은 **함수 안에서 지연 import**한다. 최상단에서 import하면 허용 목록 `_ALLOWED_LEAF_IMPORTS`(`test_cycle274_ast_llm_gate.py:323-345`)에 걸린다 | 자체 try + 호출 자리 try(`except Exception` 하나). `observe_order` 전체도 이미 바깥 try로 감싸져 있다(`llm_buy_gate.py:1007` 부근). 실패해도 LLM 경로는 계속 돈다 | 아님 |
| R2 | 청산 기준 원시값 | `order_engine.py` `execute_sell`(`:1767`). 포지션 확인(`:1813-1817`) 직후, 첫 await(`:1836` `_strategy_exchange_async`) 앞. 담는 것: 신호, `_sell_order_price(ticker, 0)`(`:222-236`)로 읽은 그 순간 시세, `pos.buy_price`·`high_since_buy`·`quantity`, `_entry_atr` 값. **dict 조회만 하고 손절선은 계산하지 않는다** | 동기. 값을 지역변수로 돌려받기만 한다. 틱 경로에서는 `risk.on_tick`이 첫머리에서 `ticker_prices`를 그 틱 값으로 덮어쓰므로(`risk.py:592-597`), 이 자리의 시세가 곧 신호 틱 가격이다. 틱이 아닌 경로(09:00 익일청산·15:20 등)에서는 최신 캐시 값이다 | **반드시 try.** 이 자리는 try 밖이다. 새면 `execute_sell`을 통째로 빠져나간다. 그러면 `_selling`(`:1785`)이 남아 손절이 멈추고, 호출자도 중단된다. 확인한 호출자 두 곳은 try가 없다: `risk.py:703-704` → `realtime/handler.py:631-640`이 예외를 다시 던져 WS가 재연결되고, `scheduler.py:2014-2016` 15:20 루프는 같은 전략의 나머지 종목 청산이 그 회차에 빠진다 | **D1** |
| R3 | 청산 메모(주 경로) | 같은 함수. 매핑 등록(`:1989-1995`) 뒤, `_persist_sell_pending_after_send`(`:1999`) 앞. R2 값 + `result.order_no`·`send_qty`·`order_division.value`·`target_exchange`를 넘긴다. 손절선·목표가는 여기서 `resolve_exit_lines([strategy], ticker)` **1회**로 구한다. 주문이 이미 나간 뒤라 이 매도를 늦추지 않는다. 포지션이 이미 사라졌으면 `None` → R2 원시값과 R8 마지막 값으로 대신한다. **`pos.*`를 직접 읽지 않는다**(A3, `test_cycle385_ast_b7.py:179-229`) | 동기. await 0 | **반드시 try.** 이 자리는 주 경로 try 안이다. 새면 `except Exception as e`(`:2516`) → 재시도 → **같은 종목 매도 재발사**다(`:1290-1293` docstring의 「실측 3회 발사」) | **D1** |
| R4 | 청산 메모(폴백) | 같은 함수. 폴백 매핑(`:2412-2417`) 뒤, 폴백 persist(`:2421`) 앞. 넘기는 값은 R3과 같다 | 동기 | **반드시 try.** 이 자리는 바깥 `except KisApiError as e:`(`:2015`) 핸들러 **안**의 중첩 try(`:2398`)다. 이 try는 `except KisApiError as fb_err`(`:2454`) 하나만 받는다. 그래서 새면 형제 핸들러(`:2516`)로 가지 않고 `execute_sell`을 관통한다. 피해는 R2와 같고, 30초 TTL 등록(`:2448`)도 빠진다 | **D1** |
| R5 | 재주문 사유 이어받기 | `_cancel_and_reorder`(`:3597`). `_manual_sell_orders` 이어받기(`:3748-3749`) **뒤**. 순서는 AST로 고정한다 | 동기 | try. 새어도 `except Exception`(`:3753`)에 잡히고, 그 시점 `_place_state="accepted"`라 `_selling` 해제 판단은 바뀌지 않는다(`:3738`, `:3755-3768`). 이어받기 **앞**에 두면 예외 때 이어받기가 빠져, 새 주문의 수동 여부 판단이 바뀐다 | **D1** |
| R6 | 수동 API 매도 | `src/routes/trading.py`. 매핑 등록(`:199-202`, `_manual_sell_orders` 포함) 바로 뒤, `await insert_trade(record)`(`:217`) **앞** | 동기(메모리만) | 자체 try. 새면 라우트의 `except`(`:236-250`)가 주문이 이미 나간 뒤(`_sent=True`, `:193`) 「매도 주문 실패」를 돌려준다. 운영자가 다시 누르면 **두 번 판다**. `insert_trade` 앞에 두므로 DB 실패 때도 메모가 남는다 | 아님 |
| R7 | 일지 루프 띄우기 + 미리 import | `src/engine/boot_manager.py` `ensure_heartbeat_loop` 블록(`:574-580`) 뒤. 여기서 `trade_journal`을 import해 `sys.modules`에 올려 둔다. 그러면 첫 매수·매도 때 지연 import 비용이 매매 경로에 걸리지 않는다. 그다음 `ensure_journal_loop(scheduler)`를 부른다. 꼴은 `account_risk_watcher.ensure_watch_loop`(`:567`, 정의 `account_risk_watcher.py:146-175`)와 같다 | 띄우기만 하고 기다리지 않는다 | try. 부팅은 계속된다 | 아님 |
| R8 | 루프 본체 | 새 `src/engine/trade_journal.py` `journal_loop`. **첫 회는 60초를 먼저 쉰다.** 부팅 재구성(kojiro 바닥선·VCP `base_low` 등, `boot_manager.py:542-579`)이 끝나기 전 값으로 가짜 `boot` 하락 행이 생기는 것을 막기 위해서다. 그 뒤 60초마다 ① 메모 dict를 DB에 쓰고 ② `registry.all()`(`strategy_registry.py:30`)의 보유분을 `list(...items())`로 **스냅샷**한 다음, 손절선·목표·무장가를 계산해 바뀌었으면 행을 넣고 ③ 15:30 이후 `eod`를 남긴다. 꺼진 전략에 보유가 있으면 `paused`를 1번 남긴다. 손절 평가가 멈춰 있다는 뜻이다(`risk.py:643` 순회가 `enabled()`만 돈다). `scheduler._running`이 False면 스스로 끝난다 | 비동기(매매 루프와 다른 task) | 예외는 모두 삼키고 WARNING은 하루 1번으로 제한한다. DB가 죽어 있으면 메모 dict가 상한(500건)을 넘을 때 오래된 것부터 버린다. 테이블이 없으면(마이그레이션 실패) 건너뛴다 | 아님 |
| R9 | (D1을 승인하지 않을 때만) 로그 탭 | 루프 시작 때 `src.engine.order_engine` 로거에 핸들러를 붙인다. 주 경로 INFO 로그(`:2009-2012`, 인자에 `signal.value`·주문번호·전략이 있다)를 구조화해 메모로 만든다 | 동기. `logger.info` 호출 **안에서** 돈다 | **위험 등급은 D1과 같다.** 표준 `Handler.handle`은 `filter`·`emit` 예외를 잡지 않는다(로컬 Python 3.13 `logging/__init__.py:1011-1028`). 그리고 핸들러는 그 로거의 **모든** 레코드에서 실행된다. 주 경로 로그(try 안)에서 새면 재발사, 폴백 로그(`:2431-2436`)에서 새면 관통이다. 그래서 `handle()`을 오버라이드해 `filter`+`emit` 전체를 `except Exception`으로 감싸고, 파싱은 접두 문자열 비교 1회로 제한한다 | 아님(실행 위험은 8영역과 같은 등급) |

**손절선·목표·무장가 계산 (R3·R8 공용)**
- `position_exit_lines.resolve_exit_lines([strategy], ticker)`를 그대로 쓴다. `stop_source`는 `stop_kind`가 되고, `target_source == "measured_move_hit"`이면 `target_hit`가 된다.
- **donchian 무장가**
  - `_kk_exit_lines(ticker, pos)`(`donchian_swing.py:1702-1717`)로 `(손절선, 무장 여부, 채널)`을 얻는다.
  - 미무장이면 R = E − 손절선이고, 무장가 = E + `kk_breakeven_r` × R이다. `_kk("kk_breakeven_r")`는 1회만 읽는다.
  - 무장 뒤에는 마지막 무장가를 그대로 둔다.
  - 「E + k×R」 조합식 한 줄은 leaf가 **복제한다.** 이 부분은 이중화 금지 가드 G-405-4(`test_cycle405_ast_donchian_kk.py:239-251`)가 지키는 헬퍼 바깥이다. 그래서 차분 테스트로 묶는다: 고점이 계산한 무장가 바로 위면 `_kk_exit_lines`의 무장 여부가 True, 바로 아래면 False여야 한다.
  - `_kk`를 거치면 `[donchian_kk_param_invalid]`의 하루 1회 발화 한도(`:1670-1690`)를 일지가 먼저 쓸 수 있다. 로그가 어디서 났는지만 바뀌고 매매와는 무관하다. 계좌 SOFT 게이트도 이미 같은 경로를 부른다(`account_risk_watcher.py:406-414`).
- **허용 호출 목록** (AST로 강제)
  - 허용: `get_effective_stop_price` · `get_effective_target_price` · `_kk_exit_lines` · `_kk("kk_breakeven_r")` · `position_exit_lines` 공개 함수.
  - **금지**: `check_*` · `on_*` · `prepare` · `calc_*` · `_effective_setup` 직접 호출.
  - 금지하는 이유: `check_exit_signal`은 상태를 바꾼다. LTV는 `pos.high_since_buy`를 갱신하고 `_limit_up_reached.add`로 모드를 바꾼다(`long_tail_volatility.py:1095`, `:1116-1121`). BFB `_effective_setup`은 `observe=False`가 필수다(`bull_flag_breakout.py:1382-1383`).
- leaf는 8영역 모듈을 import하지 않는다. 필요한 객체는 인자로 받는다.

**A-PURE·A-ATOMIC에 영향이 없는 근거**
- `calc_buy_quantity`와 `_apply_budget_limit`이 있는 `strategy_base.py`·전략 파일을 1단계에서 **한 줄도 고치지 않는다.** 그래서 A-PURE(관문 안 await·DB·HTTP 금지)의 대상 코드가 그대로다.
- A-ATOMIC 구간은 `execute_buy`의 `:1390`(`calc_buy_quantity`)부터 `:1440`(`pending_buys.add`)까지다. R1은 `await place_order`(`:1564`)보다 **뒤**인 `:1600`·`:1710`에서 불리는 함수 안에 있다. `execute_buy` 본문은 0줄이다.
- R2~R5는 매도 경로라 두 규칙과 관계없다. await를 하나도 더하지 않는다.
  - R3은 매핑과 PENDING 헬퍼 사이에 await 없이 들어간다. 그래서 「최초 양보점 = `await insert_trade`」 전제와 `_persist_sell_pending_after_send`의 「본문 앞 await 추가 금지」(`:1297-1299`)를 건드리지 않는다.
  - `_handle_sell_fill`을 건드리지 않으므로 매도 체결의 두 축 판정은 그대로다.
- DB 쓰기는 모두 R8 루프에만 있다. 매매 경로에는 DB가 0이다.
- 공용 DB 풀(최대 10)에는 분당 SELECT·INSERT 2건 안팎만 더한다.

**새로 둘 가드(테스트)** — 상세는 7절 Red 목록이다.
- `trade_journal`의 동기 함수 본문은 통째로 `try/except Exception` 안에 둔다. 그 안에 `await`·`create_task`·DB·HTTP를 두지 않는다.
- R1~R6 호출 자리마다 `ast.Try`의 모양을 고정하고, 예외를 주입하는 행위 테스트를 둔다.
- 허용 호출 목록을 둔다. R5는 이어받기 뒤에 둔다. leaf에 `get_effective_stop_price`라는 이름을 정의하지 않는다. leaf는 8영역을 import하지 않는다.

---

## 6. 화면 — 거래내역 > 거래일지

**API** (`src/routes/history.py`, c411 수정본 위에 쌓는다)
- `GET /api/history/journal?from&to&strategy&ticker&status&page&size`
  - 조립은 순수 함수 `src/engine/journal_view.py`가 한다.
  - 원천마다 1번씩 읽는다: 페어, 거래 행, 일지 행, 손절선 행, 메모, 비용(c411 `overlay_pairs`·`trade_costs`), 종가.
- `PUT /api/history/journal/notes/{anchor_trade_id}`
  - 리포터 키는 GET만 통과하고 PUT은 403이다. 기존 인증 규칙 그대로다.

**카드 한 장의 구성**
1. **머리**: 종목명(코드) · 전략 · 보유중/청산 · 보유 일수 · 세전 손익 · 세후 손익.
2. **진입 줄**
   - 일자·접수 시각.
   - 체결가(가중평균)·수량.
   - 체결오차: 주문가 기준(「매매손익 탭과 같은 값」) + 판단가 기준(값이 다를 때만). 원·bp로 보이고, 주문구분 배지(시장가/지정가 쿠션)를 단다.
   - 진입 이유 한 줄. 예: 「깃발 상단 12,300 돌파 — 측정 목표 13,450 (ATR 410)」.
   - 최초 손절. `hard_pct`면 「근사」 배지, LTV면 「모드 의존 —」.
   - 익절 목표. BFB는 숫자와 도달 여부, donchian은 「없음 · 3R 무장가 x」, 나머지는 「없음 — 트레일링/추세/시간 청산」.
3. **보유 중 손절선 변화**: 접을 수 있는 작은 표.
   - 칸: 시각 · 사건 · 손절선 · 직전 대비(올라감/내려감) · 원인 추정.
   - 원인 추정은 `inputs`를 비교해서 「고점 갱신 / ATR 변화 / 파라미터 변경 / 재시작 / 본전 승격」을 가린다. LTV는 「재시작 = 상한가 모드 소실」도 후보에 넣는다.
   - `paused`면 빨간 경고 「손절 평가 정지」를 띄운다.
4. **청산 줄**
   - 일자·시각.
   - 체결가.
   - 판단가·체결오차.
   - 청산 이유: 신호의 한글 이름 + 경로(주 경로/폴백/재주문/수동/외부).
   - 청산 순간 손절선. 가격과 무관한 청산(`TIME_EXIT`·`FORCE_CLEAR`·`NEXT_DAY_CLEAR`·`TREND_EXIT`)이면 「미발동, 참고값」으로 적는다.
5. **비용**: 진입 수수료 · 청산 수수료 · 세금 · 합계 + 배지(정산/추정/배분). 분할 매도는 매도 주문마다 한 줄씩 보인다(`sell_trade_ids` 또는 `partial_sell_trade_ids`).
6. **최대 평가이익/손실**: 각각 %·원·날짜. 「종가 k/n일」을 함께 보이고, 배지는 잠정 봉 · 락(액면분할 등) · 「해당 없음(당일 청산)」을 쓴다.
7. **메모**: 입력칸과 저장 버튼.
8. **값의 출처 배지**: 기록 / 계산 / 복원(AI평가·로그) / 없음(기록 시작 전).

**필터**: 기간(기본 최근 30일) · 전략 · 종목 · 보유중/청산 · 이익/손실. 화면 머리에 「일지 기록 시작일」을 보인다.

**세전과 세후**
- 세전은 지금 「매매손익」과 같은 값(`trade_history` 기준)이다.
- 세후와 페어 비용 합계는 c411 `overlay_pairs`의 `net_profit_loss`·`fee`·`tax`를 그대로 쓴다. 보유 중 페어의 예상 매도비용도 c411 규칙 그대로다.
- 비용을 모르면 0으로 계산하지 않고 「비용 모름」으로 보인다. c411이 이미 그렇게 구현했고(M4 — `src/routes/history.py:159-163`, `cost_overlay.py:261-262`), 일지는 그 `None` 규약을 따른다.

**프론트엔드 규칙**: 시각은 `src/utils/kst.ts`만 쓴다. 타입은 `frontend/src/types/`에 둔다.

---

## 7. 개발 단계

### 1a단계 — 기록 시작 (새 기록이 필요한 ④⑥⑦⑧⑨)

| 순서 | 내용 |
|---|---|
| Red (tdd-engineer) | ① 동기 함수 AST: 본문 통째 `try/except Exception`, `await`·`create_task`·DB·HTTP 0.<br>② **호출 자리 AST**(R1~R6). 각 `ast.Try`가 다음 셋을 만족해야 한다. (i) body = [선택: `from src.engine import trade_journal`] + 일지 호출 1문장(R2만 대입문, 나머지는 `Expr`). (ii) handler는 정확히 `except Exception` 하나(튜플·하위 타입 금지). (iii) handler 안에 `raise`가 없다. 선례는 `test_g328_3b`(`test_cycle328_sell_pending_helper.py:317`).<br>③ **행위 테스트**: 일지 함수가 raise하도록 바꿔 놓고 확인한다. 주 경로·폴백·재주문에서 `place_order`가 1회만 불린다 · `_selling`이 정상이다 · `execute_sell`이 예외를 밖으로 내지 않는다 · 15:20 `_force_clear_main_only`가 다음 종목으로 넘어간다 · 수동 매도 라우트가 `success=True`를 준다.<br>④ R5 호출 줄이 이어받기 줄보다 뒤다. R3 구간의 `pos.quantity` 읽기는 0이다(기존 A3 통과).<br>⑤ 허용 호출 목록 AST.<br>⑥ `note_entry`가 mode=off에서도 메모를 남기고 task는 0건이다. `"LIMIT"`이 코드값으로 바뀐다.<br>⑦ donchian 무장가 차분 테스트. 일지 손절선이 같은 상태에서 잔고 화면 `resolve_exit_lines`와 같다.<br>⑧ 루프: 변화 감지 문턱·`eod`·`boot`·`paused` · 21:30 clear를 청산으로 보지 않음 · 첫 회 sleep 먼저 · 순회 스냅샷 · 부팅 이어 붙이기 규칙(4-2).<br>⑨ 마이그레이션 적용과 `ON CONFLICT DO NOTHING`(pg 하네스). 테이블이 없을 때 건너뜀.<br>⑩ **테스트 위생**: `boot()`를 도는 기존 테스트는 MagicMock scheduler라 `_running`이 참으로 평가돼 루프가 계속 돈다. 그래서 부팅 경로 중립화 픽스처(선례 `tests/conftest.py:642-675`, cycle386)와 옵트아웃 마커 `real_trade_journal`을 만든다. 마커는 `pyproject.toml` markers에 등록한다(`filterwarnings = error`라 미등록 마커는 즉시 실패). 메모 dict는 테스트마다 reset한다 |
| Green (backend-dev) | 새 파일: `047_trade_journal.sql`, `src/engine/trade_journal.py`, `src/db/trade_journal.py`. 수정: `llm_buy_gate.py`, `boot_manager.py`, `routes/trading.py`, (D1) `order_engine.py`. `trade_journal.py` 최상단 import는 표준 라이브러리와 logging만 둔다. DB 모듈은 R8 flush 함수 안에서 지연 import한다 |
| 검증 (tester) | 전체 스위트를 다시 돌리고 `--log-level=DEBUG`로 한 번 더 돌린다. 시각 창 테스트는 시각을 고정한다. 매매 행위 동등성은 기존 cycle276·327·328·335·385 회귀로 확인한다. R3의 `resolve_exit_lines` 1회 실행 시간을 전략별로 잰다 |
| 문서 | `/sync-docs`(report-writer): `src/engine/CLAUDE.md` 모듈 맵, `src/db/CLAUDE.md` 새 절, 루트 `CLAUDE.md` DB 표에 3테이블, (D1) 「접수 후 PENDING 영속화」 절 |
| 배포 | `src/`를 바꾸므로 full(backend 재시작). 장외 창(15:30~16:00 · 21:35~07:45 · 주말·공휴일)에만 한다. 보유가 있으면 09:00~15:30에는 하지 않고, 20:00~21:35에는 어떤 경우에도 하지 않는다 |

**다시 맞춰야 할 핀**

파일 수 핀은 배포 순서에 따라 값이 다르다. 마지막 값은 순서와 상관없이 같다.

| 핀 | 지금 main | c411 HEAD | 1a → c411 → 1b 순서 | c411 → 1a → 1b 순서 |
|---|---|---|---|---|
| `_SRC_TREE_FILES` (`test_cycle287_ast_scope.py:273`, c411 `:278`) | 178 | 179 | 180 → 181 → **182** | 179 → 181 → **182** |
| `_PINNED_DIR_FILE_COUNTS["src/engine"]` (`:823`, c411 `:836`) | 93 | 94 | 94 → 95 → **96** | 94 → 95 → **96** |
| `src/engine/*.py` 수 (`test_cycle291_ast_scope.py:482`, c411 `:486`) | 82 | 83 | 83 → 84 → **85** | 83 → 84 → **85** |
| `_SRC_TREE_DIGEST` | — | — | 단계마다 재계산 | 단계마다 재계산 |

- 1a는 `src/`에 2파일(`engine` 1, `db` 1)을 더하고, 1b는 `src/engine`에 1파일을 더한다. c411은 `cost_overlay.py` 1파일을 더한다.
- `test_cycle290_ast_scope.py`의 leaf 목록(`:412-436`)에 새 leaf를 넣는다.
- **`llm_buy_gate.py`**
  - 파일 통째 sha 핀은 0건이다.
  - 최상단 import 허용 목록(`test_cycle274_ast_llm_gate.py:323-345`)이 있다. 그래서 R1은 함수 안 지연 import로 한다.
  - C5(await 0, DB/HTTP 흔적 0, `test_cycle274_ast_llm_gate.py:158-180`)와 C22(8영역 참조 0, `test_cycle276_order_time_hook.py:700-713`)는 설계상 통과해야 한다.
  - 이 파일을 참조하는 테스트는 29개 파일이고, 그중 AST가 최소 9개다(233·274·276·278·286·287·290·297·363 + `tests/unit/engine/test_cycle297_llm_strategy_context.py`). Red 단계에서 전수 확인한다.
- **`boot_manager.py`·`routes/trading.py`**: 파일 통째 sha 핀은 0건이라 digest 재계산만 하면 된다. 세그먼트 핀이 있는지는 Red 단계에서 전수 확인한다.
- **(D1) `order_engine.py`**
  - `_EIGHT_AREAS`(`test_cycle222a3_ast_followup_fixes.py:430`)의 sha 핀 절차를 따른다.
  - 파일 통째 sha(`08c47984…`)를 고정한 **11개 파일**을 다시 맞춘다:
    - `test_cycle222a3_ast_followup_fixes.py`
    - `test_cycle223_ast_donchian_exit_fix.py`
    - `test_cycle223f_ast_manual_apply_safeguard.py`
    - `test_cycle274_ast_llm_gate.py`
    - `test_cycle278_ast_catalog_guards.py`
    - `test_cycle282_ast_purity.py`
    - `test_cycle290_ast_scope.py`
    - `test_cycle294_ast_stage3.py`
    - `test_cycle297_ast_scope.py`
    - `test_cycle405_ast_donchian_kk.py`(G-405-6 — 주석상 「cycle405 커밋 뒤 삭제」인 사이클 한정 핀이 아직 남아 있다)
    - `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py`
  - 목록은 `grep -rl <sha> tests`로 기계적으로 다시 뽑는다.
  - 최상단 import는 바꾸지 않으므로 C10(`test_cycle276_ast_order_hook.py:320-345·771-780` — 증가분은 `llm_buy_gate` 하나)은 그대로 통과해야 한다.
  - `execute_sell`·`_cancel_and_reorder` 세그먼트를 고정한 핀은 Red 단계에서 전수 작성한다.

### 1b단계 — 화면 (①②③⑤⑩ 계산 + 카드)

| 순서 | 내용 |
|---|---|
| 선결 | **c411 실비용 기능 병합·배포.** 일지에는 `trade_costs()`·`overlay_pairs()`와 페어의 `buy_trade_ids`/`sell_trade_ids`/`partial_sell_trade_ids`가 필요하다. c411도 `routes/history.py`를 고친다 |
| 착수 전 실측 | 04-22~06-11 페어의 `stock_master_daily` 종가 보유율(읽기 SELECT) |
| Red | `journal_view` 순수 함수 테스트를 쓴다. 대상: 체결오차 부호, 주문가 기준 진입+청산 합 = c411 `slippage_won`(닫힌 페어 패리티), MFE/MAE 포함 규칙과 결측·잠정·락 표시, 비용의 진입/청산 분리(세 묶음), 「모름 ≠ 0」. 라우트 테스트와 프론트 vitest + RTL + MSW 테스트도 쓴다 |
| Green | `src/engine/journal_view.py`(새 파일), `src/db/stock_master_daily.py` 날짜 범위 **읽기** 함수(쓰기 SQL 0이라 cycle386 G5와 충돌하지 않음), `src/routes/history.py`, `History.tsx` 탭, 새 카드 컴포넌트, 타입, `frontend/src/test/handlers.ts` |
| 핀 | 위 표의 마지막 열 값(182 / 96 / 85) |
| 배포 | full. 창은 1a와 같다 |

### 2단계 — 신호 세부·수량 산정 근거 (1b를 써 본 뒤 따로 승인)

- **청산 세부 사유**
  - 전략 파일에 읽기 전용 `get_stop_components()`를 둔다. 예를 들어 STOP_LOSS 5종이 서로 구분된다. 패리티 테스트로 `max(components) == get_effective_stop_price`를 확인한다.
  - donchian은 read-only `get_arm_price`를 함께 두면 1a의 무장가 조합식 복제를 없앨 수 있다.
  - 전략 파일 통째 sha 핀이 파일마다 3~10개 테스트 파일에 있다(실측: BFB·kojiro·momentum·VCP 10, donchian·VB 9, LTV 8, etf_trend 3). 모두 다시 맞춰야 한다.
  - `check_exit_signal`은 고치지 않으므로 S2 28핀은 유지된다.
- **세부 사유를 남길 자리**
  - 종목상태 청산의 세부 사유: `status_exit_watch.py:979-994`.
  - 익일청산 예약 사유: `src/db/pending_next_day_clear.py:42`의 `save_pending_ndc`.
  - donchian 시간 청산 세부: 전략 파일.
- **수량 산정 근거**
  - `strategy_base._apply_budget_limit`의 단계 값(risk_pct·ATR·설계 랏·시장 유닛 m·잔여 클램프·1주 폴백·K축·ρ축)을 순수 dict 쓰기로 남긴다. 약 +15~20줄이다. 반환값은 바꾸지 않고, await·DB는 0이다.
  - `strategy_base.py` 파일 통째 sha 핀이 11개 테스트 파일에 있다. 다시 맞춘다.
  - SOFT·매수가능 클램프 자리는 `execute_buy` `:1395`·`:1428`이다. **A-ATOMIC 구간(`:1390`~`:1440`) 안**이라 두 가지가 함께 필요하다.
    - 8영역 추가 승인.
    - A-ATOMIC 바이트 핀 `_ATOMIC_SEGMENT_SHA`(`test_cycle276_ast_order_hook.py:317`, 검사 `:720-733`) 재조정.
  - 승인 때 고를 대안: 구간을 건드리지 않고, 발사 뒤 `observe_order(ordered_qty=…, budget_*)`로 재구성할 수 있는 값만 남긴다.
- **선택 항목**
  - KIS 주문 원장 적재: `TTTC0081R`/`CTSC9215R`로 평균 체결가·주문 시각·주문구분 과거분을 채운다. `src/api/balance.py` 연속조회 확장 + 새 테이블 + `trade_cost_reconcile_task.py`. 8영역은 0이다.
  - 체결 처리 시각 칸.

### 배포 순서 (10-13 주계좌 전환과 실비용 기능)

| 시점 | 일 |
|---|---|
| 10-08(목)~10-12(월) | 1a 개발(Red → Green → 검증). **배포하지 않는다.** 10-09(금)는 한글날 공휴일이라 휴장으로 가정했다. 코드로는 확인하지 못했다(휴장일은 런타임 조회, `trading_calendar.py:61`). 10-08·10-12는 신규 매수를 멈춘 날이다(워크리스트 「주계좌 전환 진행 중」) |
| 10-13(화) 07:00~07:40 | 주계좌 전환(backend 재생성). 일지 배포를 이 일정과 섞지 않는다. 문제가 생겼을 때 원인을 가르기 어려워진다 |
| 전환 확인과 `buy_paused` 해제 뒤 첫 장외 창 (권고: 10-13 21:35 이후) | **1a 배포.** 기록은 이 순간부터 쌓인다. 미루는 날만큼 새 거래의 손절선·사유 기록이 빈다. 핀 값은 위 표에서 그때 c411이 병합됐는지에 맞는 열을 쓴다 |
| c411 배포 + 1a 기록 1~2일 확인 뒤 장외 창 | **1b 배포** |
| 1b 사용 뒤 | 2단계 승인 여부 결정 |

---

## 8. 과거분 복원 계획

| 항목 | 자동(읽을 때) | 1회 복원(선택) | 불가 |
|---|---|---|---|
| 일자·가격 | 전체(04-22~) | — | 체결 시각 |
| 체결오차 | 매수 주문가: 10-07~ 모든 자동 매수(보정 행 제외). 09-11~10-06은 `llm_buy_evaluations` 행이 있는 주문. 매도 주문가: 10-07~(「주문 접수 뒤 시세」) | KIS 원장(2단계)으로 주문구분 보강 | 판단가 기준 전부(1a 배포 전). 매도 주문가(10-06 이전) |
| 수수료/세금 | 정산 08-21~, 그 전은 추정 | c411 계획의 전체 기간 대사 | — |
| 최대 평가이익/손실 | 06-12 이후 거래는 대체로 가능(결측 k/n 표시). 04-22~06-11은 착수 전 실측 결과에 따른다 | — | 결측일 종가 |
| 진입 이유 | 09-11 이후 AI평가 행의 파생 칸(돌파선·k·신호가). 「복원(AI평가)」 배지 | — | 그 전 전부 |
| 청산 이유 | — | **D3**: EC2 파일 로그의 「매도 주문 접수」 줄을 파싱해 `source='log_restore'`로 넣는다. 로그는 20일 + 당일 보관이고 자정마다 가장 오래된 날이 지워진다(`src/main.py:108·116-121`). 오늘(10-08) 기준으로 계산하면 대략 09-18 이후분만 남아 있다. cycle402 전후로 사유명이 섞여 있어 이름별로 합산하지 않는다 | 로그 보관 기간 이전 전부 |
| 최초·조정 손절, 익절 목표 | — | — | 전부. 당시 파라미터·메모리 상태가 남아 있지 않다 |

**옛 계좌(끝 1589) 원장**
- 전환 뒤에는 지금 코드로 옛 계좌를 조회하지 못한다(`api/trade_profit.py:65`는 현재 주계좌만 본다).
- EC2의 `.env.rollback_20261007`(옛 4값, 워크리스트 「주계좌 전환 진행 중」)을 **지우지 않고** 옛 앱키도 폐기하지 않으면, 2단계에서 옛 원장을 채울 길이 남는다. 따로 할 일은 없고 보존만 하면 된다.

**화면 표시**
- 값마다 출처 배지(기록/계산/복원/없음)를 단다.
- 일지 기록 시작일 이전 카드에는 「기록 시작 전 거래 — 일자·가격·비용·평가손익만」이라고 한 줄 안내한다.

---

## 9. 사용자 결정 항목

| # | 결정 | 권고 | 이유 |
|---|---|---|---|
| D1 | `src/engine/order_engine.py` 기록 호출 약 27줄 승인. `execute_sell`의 `:1817` 뒤(R2 원시값), `:1995` 뒤(R3 주 경로 메모), `:2417` 뒤(R4 폴백 메모), `_cancel_and_reorder`의 `:3749` 뒤(R5 이어받기). 4곳 모두 「함수 안 지연 import + 일지 호출 1문장」을 `except Exception` 하나로 감싼 try다. 모듈 최상단 import는 0이다 | **승인** | 청산 사유, 매도 판단가, 청산 순간 손절선을 주문번호와 **정확히** 묶는 길은 이것뿐이다. 매매 행위는 0이고 await 추가도 0이다. 선례는 cycle409(주문가 기록) `order_engine.py` +23 승인이다. **승인하지 않으면** 로그 탭(R9)으로 대신한다. 이때 폴백·재주문 매도는 「사유 미상」이 되고 매도 판단가는 없다. 그리고 **R9도 매도 경로 안에서 동기로 실행되므로 재발사·관통 위험 등급이 D1과 같다**(5절 R9). 「8영역 0줄이라 더 안전」하지 않다 |
| D2 | 메모 저장 위치 | **DB 테이블**(`trade_journal_notes`) | 브라우저 저장은 기기를 바꾸거나 저장소를 지우면 사라진다. 메모는 복기의 원본이다 |
| D3 | 과거 청산 사유 로그 복원 | **EC2 로그 파일 사본만 지금 확보(읽기만)하고, 파싱 여부는 1b 화면을 본 뒤에 정한다** | 로그는 20일 보관이라 하루 지날 때마다 가장 오래된 날이 사라진다(`src/main.py:108`). 사본이 없으면 선택지 자체가 없어진다. 파싱·적재는 새 테이블 INSERT뿐이라 되돌리기 쉽지만, 할 가치가 있는지는 화면을 보고 판단하는 편이 낫다 |

**정해 둔 기본값 (바꾸고 싶으면 말씀하시면 된다)**
- 체결오차 부호: 불리하면 +. 매수는 체결가 − 기준가, 매도는 기준가 − 체결가. 주문가 기준과 판단가 기준을 함께 보이고, 주문가 기준은 「매매손익」 탭(c411)과 같은 값이다.
- 손절선 출처: 잔고 화면과 같은 leaf를 쓴다. momentum·VB는 「근사」 배지를 단다.
- LTV 손절선: 잔고 화면과 같이 「모드 의존 —」으로 비워 둔다. 숫자를 내려면 두 화면을 함께 바꾸는 별도 결정이 필요하다(`position_exit_lines.py:58-74` — `get_effective_stop_price` 미러를 붙이면 계좌 SOFT 게이트 입력이 바뀌어 `domain-consult` 선행 대상이다). LTV는 지금 비중 0이다.
- MFE/MAE 포함 규칙: 15:30에 들고 있던 날의 종가만 쓴다. 기준가는 평균 매수가다.
- 손실 구간이 한 번도 없던 거래: 「손실 구간 없음(최저 +x%)」으로 표시한다.
- 종가 결측: 있는 종가로 계산하고 「k/n일」을 표시한다.
- 락 행(액면분할 등): 보정하지 않고 표시만 한다.
- 390일 보관: 지금은 그대로 둔다. 2027-04 전에 다시 정한다.
- 과거 거래의 최초 손절: 빈칸으로 둔다. 지금 파라미터로 계산하지 않는다.
- 손절선 기록 문턱: 하락은 전부, 상승은 0.5% 이상, 장마감 1회.

---

## 10. 위험과 한계

- **기록 실패의 두 모양(D1)**
  - **R3(주 경로)**: `place_order` 성공 뒤, 주 경로 try 안이다. 예외가 새면 `except Exception as e`(`:2516`)가 재시도해 **같은 종목을 다시 판다.**
  - **R2·R4**: R2는 try 밖이고, R4는 `except KisApiError` 핸들러 안의 중첩 try다(`:2015`·`:2398`·`:2454`). 예외가 새면 `execute_sell`을 관통한다. 그 결과는 이렇다.
    - `_selling` 좀비가 생겨 그 종목의 손절이 멈춘다. 이 좀비는 15분 주기 잔고 동기화(`scheduler.py:2520-2526`) 때, 180초 이상 지난 것만 풀린다(`SELLING_RECONCILE_MIN_AGE_S`, `:79`·`:3420-3427`). 그래서 **최대 약 15분 이상** 손절이 멈출 수 있다.
    - 그 틱의 다른 전략 청산 평가가 사라지고 WS가 재연결된다.
    - 15:20 강제청산 루프의 나머지 종목이 그 회차에 빠진다.
    - 폴백이면 30초 TTL 등록도 빠진다.
  - 그래서 셋을 갖춘다: 함수 본문 try, 호출 자리 try의 모양 AST, 예외 주입 행위 테스트. **이 셋이 빠지면 D1은 하지 않는다.**
- **R6 실패 = 이중 매도 위험**: 라우트가 주문이 나간 뒤 실패를 응답하기 때문이다. 그래서 자체 try로 감싼다. 참고로 `insert_trade` 자체가 실패할 때도 같은 응답이 나가는데, 이것은 기존 동작이고 이 계획은 바꾸지 않는다(`routes/trading.py:217·236-250`).
- **60초 지연**: 체결 직후 60초 안에 끝난 거래는 루프가 포지션을 보지 못한다. D1이 있으면 R3·R4의 청산 순간 값으로 채우고, 없으면 최초 손절이 빈다.
- **`hard_pct` 근사의 한계**: momentum D+1 트레일, VB 실패 돌파 조기청산처럼 고정%로 접히지 않는 선은 담지 못한다. 잔고 화면도 같은 한계를 가진다. 실제로 어떤 선이 걸렸는지는 청산 신호(`TRAILING_STOP` 등)로 사후 확인한다.
- **donchian 무장가 조합식 1줄 복제**: 차분 테스트로 묶지만, `_kk_exit_lines`의 무장 조건이 바뀌면 테스트를 함께 고쳐야 한다. 2단계 `get_arm_price`로 없앨 수 있다.
- **매수가 정확도**: 매수 `price`는 마지막 체결가라서, 분할 체결 매수에서는 가격·MFE/MAE·비용 배분이 조금 어긋난다. KIS 원장 평균가(2단계)로만 고칠 수 있다.
- **주문 접수 시각 ≠ 체결 시각**: 보정 INSERT 행은 체결 처리 시각, 부팅 동기화 행은 부팅 시각이다.
- **외부 매도**: HTS 매도, 잔고부족 메모리 정리(`order_engine.py:2526-2545`), 재기동으로 매핑을 잃은 경우에는 사유가 없다. 「외부·매핑 없음」으로 표시하고, 외부 매도라고 단정하지 않는다.
- **c411 의존**: 비용 칸과 페어 행 id는 c411 병합 전에는 없다. 그래서 1b는 c411 뒤에 한다. `test_cycle287`·`test_cycle291`·`routes/history.py`에서 병합 충돌이 예상된다.
- **비용 숫자는 움직인다**: 추정에서 정산으로 바뀌고, 추정 요율도 날마다 바뀐다. 메모에 숫자를 옮겨 적으면 낡을 수 있다.
- **마이그레이션 실패**: 배포는 실패를 건너뛰고 진행한다. 이때 일지는 기록을 건너뛰고 WARNING만 남긴다. 매매에는 영향이 없지만 그 기간의 기록은 빈다.
- **재시작은 엔진 상태를 바꾼다**: kojiro 바닥선, VCP·BFB 래치·구조선, LTV 상한가 모드(`_limit_up_reached`)가 달라질 수 있다. 일지는 이것을 `boot` 사건으로 「바뀐 값」 그대로 남긴다. 이것은 기록의 결함이 아니라 엔진의 실제 동작이고, 복기에 그대로 보여야 한다. 부팅 직후 재구성 전 값은 첫 회 sleep으로 피한다.
- **일봉 한계**: 청산 뒤 적재 대상에서 빠져 생긴 결측, 07-11~09-10 소형주 구멍, 09-14~09-28 잠정 봉, 수정주가 기준 혼재, 06-12 이전 적재 범위 미상이 있다. 모두 표시로 드러내고 숨기지 않는다.
- **2027-05-17부터** 2026-04-22 거래의 종가가 지워지기 시작한다. 그 뒤로는 그 거래의 MFE/MAE가 빈다.
- **8영역 sha 핀 재조정은 CI가 붉어지기 쉬운 지점이다.** 파일 통째 핀만 11개 파일이다. 고친 뒤에는 반드시 전체 스위트를 다시 돌린다.

### 확인 못 함
- 운영 DB의 오늘 파라미터 값. 3절은 09-20 실측표 기준이다.
- 전략별 `llm_gate_mode` 운영값. 09-11~10-06 매수의 복원 범위가 이 값에 달려 있다.
- cycle276·cycle402의 배포일.
- `boot_manager.py`·`routes/trading.py`의 세그먼트 핀 유무(파일 통째 핀 0건은 확인했다).
- `order_engine.py`의 `execute_sell`·`_cancel_and_reorder` 세그먼트를 고정한 핀의 정확한 수. Red 단계에서 전수 작성한다.
- 04-22~06-11 거래 종목의 `stock_master_daily` 종가 보유율.
- 10-09 휴장 여부(공휴일이라 휴장으로 가정).
- R3의 `resolve_exit_lines` 1회 실행 시간(검증 단계에서 잰다).
- 운영 이미지 Python 3.12(`Dockerfile:1`)의 `Handler.handle` 구조. 로컬 3.13 소스로만 확인했다.
- `test_cycle276_ast_order_hook` C10이 지금 초록인지. 테스트를 돌리지 않았다.

---

## 검토 지적 처리

**사실 대조 렌즈**

| # | 지적 | 처리 |
|---|---|---|
| 1 | R4 실패는 재발사가 아니라 `execute_sell` 관통이다 | **수용.** 5절 R2·R4 행, 10절, 요약 6을 고쳤다. Red ③에 행위 테스트를 더했다. 직접 대조로 `:2015`·`:2398`·`:2454`·`:2516`과 docstring `:1287-1295`를 확인했다 |
| 2 | 기존 leaf `position_exit_lines.py`를 빠뜨렸다 | **수용.** 손절선·목표 계산을 `resolve_exit_lines` 재사용으로 바꾸고, momentum·VB·LTV 식 복제를 없앴다. `target_hit`를 추가했다. LTV는 잔고 화면과 같게 빈칸으로 두는 것을 기본값으로 했다(9절). 「결정 항목으로 올린다」는 제안은 결정 카드 대신 기본값 + 「바꾸려면 두 화면 함께 별도 결정」으로 처리했다. LTV는 비중 0이라 지금 결정할 실익이 작다 |
| 3 | 매수 `order_price`와 c411 `slippage_won`을 빠뜨렸다 | **수용(일부 조정).** ④·8절 범위를 고쳤다. 「c411 값 재사용」은 그대로 하지 않았다. c411 값은 페어 단위로 진입·청산을 합친 원 총액이라 일지의 진입/청산 분리 표시에 쓸 수 없다(`cost_overlay.py:356-369`). 대신 같은 공식으로 나눠 계산하고, 합계가 c411 값과 같다는 패리티 테스트로 묶었다. R1이 새로 더하는 가치(지정가로 바꿔 낸 주문의 판단가, 보정 행)도 명시했다 |
| 4 | 복구 포지션 `buy_date` 불일치 | **수용.** 4-2를 `(strategy, ticker)` + 기간 연결로 바꾸고 `buy_date`는 보조 키로 내렸다. `buy_date`를 NULL 허용으로 바꾸고, 부팅 이어 붙이기 규칙을 「마지막 행 뒤 페어 종료 여부」로 정했다 |
| 5 | 3절 청산 경로 누락 | **수용.** VB D+1 안전망, BFB `TIME_EXIT`, donchian 15:20 `TIME_EXIT`, LTV 15:20(cycle352)·D+1 `NEXT_DAY_CLEAR`·재시작 모드 소실을 더했다. 소실은 6절 원인 후보에도 넣었다 |
| 6 | M4는 이미 구현돼 있다 | **수용.** 지금은 c411 HEAD `72cb53fd`에 커밋까지 됐다(`51356fa5`). 6절을 고쳤다 |
| 7 | 분할 매도 id 누락, 인용 기준 불일치 | **수용.** 세 묶음으로 고쳤다. c411은 그사이 커밋돼서 인용 기준을 HEAD `72cb53fd` 하나로 맞췄다 |
| 8 | cycle392 A6 이유가 틀렸다 | **수용.** 4절 이유를 두 가지로 줄였다 |
| 9 | 핀 수치 모순·누락, import 1줄 문제 | **수용.** 7절 핀 표를 배포 순서별 기대값으로 다시 썼다. 최상단 import를 없애고 함수 안 지연 import로 바꿔 C10을 건드리지 않게 했다 |
| 10 | R6 위치 | **수용.** `await insert_trade` 앞, 매핑 직후로 옮겼다 |
| 11 | 04-22 이후 MFE/MAE 근거 없음 | **수용.** 「확인 못 함 + 착수 전 실측」으로 고쳤다(2절 ⑩, 7절 1b, 8절) |
| 12 | 보정 INSERT 행 시각 예외 | **수용.** 2절 ①에 더했다 |
| 13 | donchian 무장가는 일부 복제다 | **수용.** 「조합식 1줄 복제 + 차분 테스트」로 정직하게 적고, 2단계 `get_arm_price`로 없앨 길을 적었다 |
| 14 | 「확인 못 함」 중 코드로 확인되는 것 | **수용.** 로그 20일 보관, `llm_buy_gate` import 허용 목록, donchian `atr`·N 같은 원천을 본문에 반영하고 목록에서 뺐다 |
| 15 | 줄 번호 어긋남 | **수용.** `_sell_order_price` `:222-236`, 첫 await `:1836`, `llm_buy_gate` 참조 테스트 수를 고쳤다 |

**안전 렌즈**

| # | 지적 | 처리 |
|---|---|---|
| 1 | R2·R4 실패 모양, try 가드가 handler 좁히기를 못 막는다 | **수용(대안 4는 불수용).** 실패 모양, AST 세 조건(지연 import 1줄 허용으로 조정), 행위 테스트를 반영했다. 대안 4(R3·R4를 `_persist_sell_pending_after_send`의 try 안에 넣기)는 받지 않았다. 일지 호출을 그 try의 PENDING INSERT **앞**에 두면, 일지 예외 때 PENDING 기록이 빠진다. **뒤**에 두면 운영 경보 마커 `[sell_post_send_error]`(무cap ERROR)가 일지 실패로 오염된다. 그리고 헬퍼 시그니처 변경과 cycle328 가드 7개 재확인이 따라온다 |
| 2 | R9도 같은 위험이다 | **수용.** 5절 R9와 D1 카드에 「위험 등급 같음」을 적고, `handle()` 오버라이드·접두 비교 1회를 조건으로 걸었다 |
| 3 | R2가 손절 발사 직전에 있고, 컷 시간대에 틱마다 돈다 | **부분 수용.** 「원시값만 O(1)로 모으고 손절선 계산은 발사 뒤 R3로」는 수용했다. 「`:1953` 앞으로 옮기기」는 받지 않았다. `:1836` await 뒤에는 다른 틱이 `ticker_prices`를 덮어써서(`risk.py:592-597`), 판단가가 신호 틱 가격이 아니게 된다. `:1817` 자리는 첫 await 전이라 그 틱 값이 남아 있는 마지막 지점이다. 컷 시간대에 반복되는 비용은 dict 조회 몇 번이다 |
| 4 | 핀 재조정 과소평가 | **수용.** 파일 통째 핀 11개 파일을 이름으로 적었다. C10은 지연 import로 피한다. `_ALLOWED_LEAF_IMPORTS`, `_PINNED_DIR_FILE_COUNTS`, `test_cycle291`의 82, 수정한 `_SRC_TREE_FILES`, 세 파일의 통째 핀 0건을 반영했다 |
| 5 | 2단계 클램프 기록이 A-ATOMIC 바이트 핀 구간 안이다 | **수용.** 1절 표와 2단계에 `_ATOMIC_SEGMENT_SHA` 재핀을 명시하고, 전략·`strategy_base` 통째 핀 수를 실측해 적었다. 대안(구간 밖 사후 재구성)은 2단계 승인 때 고를 선택지로 남겼다 |
| 6 | 전략 메서드 호출 허용 목록이 없다 | **수용.** 허용·금지 목록 AST를 두었다. 무장가는 `_kk_exit_lines` + `_kk("kk_breakeven_r")` 1회로 구한다. `_kk` 발화 한도를 함께 쓰는 점(로그가 어디서 났는지만 바뀜)도 적었다 |
| 7 | `position_exit_lines`와 겹치고 LTV 방침이 반대다 | **수용.** 사실 대조 2와 함께 처리했다 |
| 8 | 폴백 매수 주문구분 `"LIMIT"` | **수용.** R1과 4-1에서 코드값으로 바꾼다 |
| 9 | R3의 `pos.quantity` 읽기 | **수용.** R3은 `send_qty`·주문번호·R2 값만 쓰고, 손절선은 leaf 호출로 구한다. A3 통과를 Red ④에 넣었다 |
| 10 | R5 순서 고정 | **수용.** 「이어받기 뒤」를 AST로 고정한다(Red ④) |
| 11 | R6 실패 = 이중 매도 | **수용.** 자체 try와 `insert_trade` 앞 배치(사실 대조 10과 같은 처리) |
| 12 | R8 순회 스냅샷·첫 회 sleep | **수용.** R8 행과 Red ⑧에 반영했다 |
| 13 | 테스트 위생 | **수용.** 중립화 픽스처, `real_trade_journal` 마커 등록, 메모 reset을 Red ⑩에 넣었다 |
| 14 | 지연 import 첫 호출 비용 | **수용.** R7에서 미리 import한다 |
| 확인 못 함 | `selling_reconcile` 해제 시간 | **해소.** 180초 이상 + 15분 주기 동기화 때 푼다(`scheduler.py:79·2520-2526·3420-3427`). 10절에 반영했다. Python 버전은 운영 이미지가 3.12(`Dockerfile:1`)인 것까지만 확인했고, 3.12 소스 대조는 「확인 못 함」에 남겼다 |