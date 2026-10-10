# 자문 — ⑦-F1 KIS 잔고에만 있는 보유: 누가 맡고 어떻게 처리하나

## 질문 요약
- 사용자 방향(10-10): 「저녁정산이나 오전부팅 때 확인되는거지? 모멘텀이 맡아서 즉시 청산하는게 좋을듯. 비중 0이어도 받는게 가능한가?」
- 추가 질문(10-10): 「바로 청산하는 더미전략을 둬야하나? 이름은 unknown이나 비식별」 → 안 U 로 따로 비교.
- 감지 자리는 둘이다 — `boot_manager.boot()` 2차(07:45 부팅, KIS 잔고 보완 복구) · `scheduler._sync_positions_from_balance`(장중 15분, `_scan_loop` 3회마다 — 20:00 까지 돈다). **21:30 저녁정산은 감지하지 않는다**(`_settle` 은 CTRGA 대사 로그만 남긴다).

## 짧은 답 — 「비중 0이어도 받는 게 가능한가?」
- **장부에 올리는 것은 지금도 된다.** `registry.get` 은 꺼진 전략도 돌려준다.
- **팔지는 못한다.** 꺼진 전략의 보유를 건드리는 자리는 셋 다 막혀 있다.
  - `risk.on_tick` 은 `registry.enabled()` 만 돈다(`risk.py:643`) → 손절·트레일링 0
  - `_execute_next_day_clear` 도 `s.config.enabled` 를 본다(`scheduler.py:1343-1346`) → 익일청산 0
  - 15:20 강제청산 대상은 VB·LTV 뿐이다
- 꺼진 전략의 보유를 파는 길은 지금 둘뿐이다. 관리·단기과열 청산(`status_exit_watch` — `registry.all()`)과 사람.
- **비중 0 + 켜짐** 은 섀도 전략만 가능하다(`strategy_registry.update_weights:54` 예외). 운영 VB 가 지금 그렇다(weight 0 · enabled t · shadow_mode true).

## 실측 (읽기 전용, 2026-10-10 18:08 KST)
| 무엇 | 결과 | 출처 |
|---|---|---|
| 「포지션 동기화 (체결통보 누락 보완)」(15분 경로) | **0건** | system_logs WARNING(09-09 07:45 부터 보존) · EC2 파일 로그 09-19~10-10 · 로컬 사본 09-17~10-07(42파일) |
| 「KIS 잔고 보완 복구」(부팅 경로) | **0건**(같은 창) | 같음 |
| `[boot_recover_strategy_unknown]` · `[sync_strategy_unknown]` | 0건 | 같음(앞의 것은 cycle425 이후분만) |
| 그 전(08-25~09-08) | 부팅 경로 2건, **둘 다 LTV 로 바르게 귀속**(GS 078930 08-27 · 한국콜마 161890 09-01), momentum 폴백 0 | `cycle373_bundleD_S2_measurements.md` §5 |
| 운영 `strategy_config` | momentum = enabled f · weight 0 · **LTV 도 enabled f · weight 0** · VB = 섀도(켜짐·비중 0) | DB |
| 운영 `positions` | donchian 2 · kojiro 6 · vcp 2 — 주인이 전부 켜져 있다 | DB |

해석
- ⑦-F1 은 **46일에 2건, 최근 30일 0건**이다. 급한 결함은 아니다.
- 🔴 다만 과거 2건의 주인 **LTV 도 지금은 꺼져 있다**. 같은 일이 오늘 일어나면 주인을 찾아도 감시가 0 이다. **숨은 결함은 「momentum 폴백」 이 아니라 「꺼진 전략에 장부를 올린다」 이다.**
- 10-08~10-12 는 5전략이 매수를 멈춰서 체결이 적다. 체결통보를 놓칠 기회도 적다.
- **위험이 몰리는 날은 10-13(계좌 이전)** 이다(Q1 확인 항목 ①).

## 코드를 읽다 확인한 사실 (결함 후보)
1. `get_recent_buy_strategy` 는 예외를 삼키고 `None` 을 돌려준다(`trade_history.py:354-382`, debug 로그). 그래서 **DB 오류와 「0건」 을 가를 수 없다.** 부팅의 `except` 분기(`[boot_recover_trade_history_lookup_failed]`)는 실행될 일이 없는 코드다. DB 가 잠깐 끊기면 조용히 momentum 으로 간다.
2. 이 조회는 「그 종목의 마지막 BUY, 상태 무관」 이다. **이미 끝난 왕복도 주인으로 잡는다.** 예를 들어 운영자가 손으로 산 종목을 5월에 kojiro 가 사고판 적이 있으면, 그 보유는 kojiro(켜짐)에게 간다. 그러면 kojiro 손절 규약으로 운영자 주식을 판다.
3. 15분 경로는 장부 추가 뒤 **`save_position` 을 하지 않는다**(메모리만). 재시작하면 부팅 2차가 다시 찾는데, `buy_date` 와 주인 판정이 그때 다시 정해진다.
4. 부팅 경로는 `registry.get(strategy_id)` 가 `None` 이면(지운 전략 id) **폴백 없이 건너뛴다.** 그 보유는 장부에 아예 안 올라간다. 15분 경로는 `or registry.get("momentum")` 으로 떨어진다. 두 경로가 다르게 처리한다.
5. `_sync_orders_to_db`(부팅에서만 호출)는 주인을 모르는 그날 체결을 `strategy="momentum"` 행으로 INSERT 한다(`[sync_strategy_unknown]`). 그 뒤 `get_recent_buy_strategy` 가 「momentum」 을 돌려주므로, **momentum 행이 「진짜 momentum」 인지 「폴백 기록」 인지 가를 수 없다.** 60일 momentum BUY 19/189 행 중 폴백 기록은 0(로그 0건) — 지금은 오염이 없다.

## Q1 — 「주인 모름」 은 언제 확정하나 · 운영자 몫과 어떻게 가르나

### 트레이더 시각
- 「잔고에만 있는 종목」 은 장부상 **진입 가설이 없는 포지션**이다. 손절선도 목표도 없다. 이런 포지션은 들고 있을 이유가 없어서, 데스크 관행은 **「출처를 모르는 재고는 다음 정규장에 턴다」** 다. 사용자 본능이 맞다.
- 단 하나의 예외가 「내 것이 아닐 수 있다」 이다. 같은 계좌에 사람 몫이 섞이면, 「턴다」 는 남의 재고를 파는 일이 된다.

### 정량 권고 — 세 갈래로 가른다
| 판정 | 조건(전부 만족) | 처리 |
|---|---|---|
| **주인 있음** | DB 조회 **성공** ∧ 그 종목의 **열린 왕복** BUY 행이 있다(마지막 BUY 의 시각 > 마지막 SELL 의 시각, `status ∈ {COMPLETED, PARTIAL, PENDING}`) ∧ 주인 전략이 **켜져 있다** | 지금처럼 주인 전략에 올린다 |
| **판정 보류** | DB 조회 **실패** · CTRGA 조회 실패(Q3) · 주인이 꺼진 전략 | 장부에는 올린다(구독·중복 매수 차단 유지). **팔지 않는다** · ERROR 1행 · 다음 15분에 다시 판정 |
| **주인 모름** | 조회 성공 ∧ 열린 왕복 없음(0건 또는 마지막 BUY 가 마지막 SELL 보다 오래됨) ∧ 그날 주문내역의 「우리 주문」 으로 설명 안 됨 ∧ 권리 입고 아님(Q3) | 청산 대상(Q2) |

- 「주인 있음」 에 **「주인이 켜져 있다」** 를 넣는 것이 이번 자문의 핵심이다. 과거 2건(LTV)이 오늘 나면 「판정 보류」 로 간다. 보류는 사람이 보게 ERROR 로 남는다. 「주인 모름」 으로 몰아 즉시 팔지 않는 이유는 둘이다. 주인이 분명하고, 그 전략 규약(익일청산 등)이 따로 있기 때문이다.
  - 꺼진 주인의 보유를 어떻게 할지는 사용자 결정 ④ 다. 권고 = 「주인 모름」 과 같은 청산 경로를 타되 `reason=owner_disabled` 로 구분한다.
- **운영자 몫(cycle433 5분류)과의 경계**:
  - 5분류는 **이미 장부에 있는 종목의 수량 차이**를 본다. F1 은 **장부에 없는 종목 하나 전체**를 본다. 대상이 겹치지 않는다(15분 경로가 F1 채택을 먼저 하고, 그 뒤 `observe_mid_session_sync` 가 돈다 — 채택된 종목은 이미 일치로 보인다).
  - F1 판정에 5분류의 재료를 그대로 쓴다. 그날 주문내역(TTTC0081R)에서 `_split_orders_by_ownership` 으로 「우리 아닌」 매수 순수량이 보유 수량과 같으면 **「오늘 사람이 산 것」** 이다. 이 경우 처리는 확인 항목 ②의 답을 따른다.
  - 어제 이전에 사람이 산 것은 증거가 없다(그날 주문내역만 본다). 그래서 **계좌 전제 없이는 사람 몫과 결함을 가를 수 없다.**

### cycle385 「운영자 몫은 팔지 않는다」 와 충돌하나
- **글자로는 충돌하지 않는다.** 그 불변식은 「우리 주문 합 ≤ 추적 수량」 이다. 채택하면 추적 수량이 되므로 형식상 지켜진다.
- **취지로는 충돌한다.** 채택이 곧 「우리 것이라고 선언하기」 라서, 사람 몫을 채택하면 불변식이 뚫린다.
- 그래서 **「이 계좌는 자동매매 전용이다」 라는 전제가 반드시 있어야 한다.** 이 전제가 서면 「출처 모름 = 결함 잔재」 가 되어 즉시 청산이 맞다. 전제가 없으면 자동 청산을 넣으면 안 된다.

### 사용자에게 확인할 것
1. **10-13 부터 쓸 계좌(끝 5334)에 지금 자동매매와 무관한 보유가 있나?** 있으면 10-13 07:45 부팅 2차가 그 종목을 전부 「잔고에만 있는 보유」 로 본다. 지금 코드에서도 이렇게 된다.
   - 그 종목을 봇이 한 번이라도 사고판 적이 있으면 그 전략(켜져 있으면 손절까지)에게 간다.
   - 아니면 꺼진 momentum 에게 가서 감시 0 이다. 이 경우만은 결과적으로 안전하다.
   - 즉시 청산을 넣은 뒤라면 **그 종목들을 09:00:30 에 시장가로 판다.**
2. **앞으로 이 계좌에서 손으로 사서 들고 있을 일이 있나?** 「없다」 면 즉시 청산을 켠다. 「가끔 있다」 면 끄기 장치(확인 ③)로 그 기간만 끈다. 「자주 있다」 면 자동 청산은 하지 않고 「판정 보류 + ERROR」 까지만 한다.
3. 권리 입고(회사분할 신주·주식배당·무상증자·공모주)는 자동으로 팔지 않고 사람에게 넘길지(권고 = 넘긴다, Q3).

## Q2 — 처리 설계

### 세 안 비교 (사용자 추가 질문 반영)
| 축 | **M** momentum 이 맡고, 꺼진 전략 보유를 직접 파는 별도 패스 | **U** 전용 전략 `unknown`(화면 「비식별 보유」) | **L** 전략 밖 「비식별 큐」(익일청산 큐처럼) |
|---|---|---|---|
| 감시 공백 | 패스가 도는 동안만 닫힌다. 패스 주기(예: 5분)만큼 늦다 | **닫힌다.** 켜져 있으니 `risk.on_tick` 이 매 틱 본다 + 15분 동기화가 받쳐 준다 | 장부 밖이라 `on_tick` 이 안 본다. 큐 패스가 전부 맡는다 |
| 「모르는 보유」 표시가 재시작 뒤에도 남나 | **안 남는다.** `positions.strategy_id=momentum` 으로 저장돼, 다음 부팅부터 보통 momentum 포지션이 된다. 표시를 따로 저장해야 한다 | **남는다.** 전략 id 가 곧 표시다(`positions`·`trade_history`) | 별도 테이블이 필요하다(마이그레이션) |
| 성과 귀인 | momentum 성과에 섞인다(꺼진 전략에 매도 손익이 생긴다) | `daily_performance` 에 `unknown` 행으로 따로 모인다. **오염 0** | trade_history 의 strategy 칸에 무엇을 쓸지가 미정 |
| momentum 을 다시 켜면 | 모르는 보유가 momentum 규약(−5%·익일 시가 갭)을 타고, 패스는 멈춘다 — 규칙이 바뀐다 | 무관 | 무관 |
| 매도 경로 | `execute_sell` 공개 함수(cycle369 선례 그대로) | `on_tick` → `check_exit_signal` → `execute_sell` — **기존 매도 경로를 그대로 탄다** | 🔴 `execute_sell` 이 재시도 직전 `strategy.state.positions.get(ticker)` 를 다시 읽는다. 장부 밖 종목은 `[sell_position_gone]` 으로 중단된다. 체결통보 보유 축도 포지션을 못 찾는다 → **`order_engine` 수정 필수** |
| 중복 매수 차단 | 된다(장부 안) | 된다 | **안 된다** — `is_ticker_held_by_any` 가 모른다. 다른 전략이 그 종목을 살 수 있다 |
| 8영역 접촉 | 0(패스는 leaf, 연결은 `scheduler.py`·`boot_manager.py` — 승인 대상) | `strategy_registry.update_weights` **1줄**(항상 켜짐 예외). `risk.py` 목록은 건드리지 않아도 된다(아래) | `order_engine.py` 다수 |
| 구현 크기 | 작다(leaf 1 + 표시 저장 + 연결 2) | 중간(아래 「U 비용」) | 크다 |

**권고 = U.**
- U 가 이기는 이유는 표시의 지속성과 귀인 둘이다. 모르는 보유를 「따로 보이는 칸」 에 두는 것이 이 문제의 절반이다. 화면에서 「비식별 보유 1건」 이 보이면 사람이 바로 안다. M 은 재시작 한 번에 그 표시를 잃는다.
- M 은 「꺼진 momentum = 모르는 보유 담는 통」 이라는 암묵 규칙에 기대는데, 이 규칙은 momentum 을 다시 켜는 날 깨진다.
- L 은 매도 경로가 장부를 전제하는 이 코드에서 성립하지 않는다. **기각한다.**

### U 비용 — 「전략 하나 추가」 실측
- 기준 = etf_trend 추가 커밋 `5fe758bc`(cycle403): **71파일**(tests 42 · src 15 · frontend 10 · 기타). 다만 대부분은 실제 매매 로직 몫이다.
- U 는 스캔·prepare·매수가 없다. 그래도 「전략이면 다 거쳐야 하는」 칸이 있다. 세면 아래와 같다.

| 묶음 | 파일 | 비고 |
|---|---|---|
| 전략 본체 | `src/engine/strategies/unknown_holding.py`(신규) | `prepare` 빈 몸, `check_buy_signal` = 계좌 SOFT 게이트 1줄 뒤 `NONE`(AST 가 게이트 줄을 요구), `calc_buy_quantity` = `_apply_budget_limit(0)`, `check_exit_signal` = 창 판정 |
| 명부 | `strategy_manifest.py` 행 1 — `eval_driver`는 기존 값 중 `tick_breakout`(매수 평가가 어차피 NONE), `breakout_rank`·`open_price_target`·`close_at_1520`·`market_unit_policy` 전부 끔 | 끝에 붙인다(평가 순서 맨 뒤) |
| 공통 키 | `DEFAULT_PARAMS` 에 `buy_paused`·`shadow_mode`·`max_lot_ratio_mult`·킬스위치 2키·LLM 4키(AST 전수 글롭) + `param_catalog.STRATEGY_IDS` + `_DEFAULT_PARAMS_SHA` 재핀 | 뜻 없는 키지만 가드가 요구한다 |
| DB | `strategy_config` 시드 마이그레이션 1 (`enabled=true, weight=0`) | 가산형 |
| 항상 켜짐 | `strategy_registry.update_weights` 1줄(8영역 — **승인**) · `routes/strategies.py` 비중 PUT·`recommendations` apply 가 `unknown` 에 비중 > 0 을 **422 로 거부** | 비중이 생기면 Σ 정규화로 다른 전략 예산을 깎는다 |
| 제외해야 할 곳 | `recommendation_engine.py` 두 루프(AI 자문이 이 전략 파라미터·비중을 권고하지 않게) · MCP 백테스트 발사(켜진 전략마다 2 job) · `funnel_capture`(켜진 전략 목록) · 진행상황·전략 설정 화면의 비중 슬라이더 | 빠뜨리면 노이즈와 예산 오염이 생긴다 |
| 표시 | `Signal.UNKNOWN_EXIT`(`strategy_base.py`) · `journal_view.py` 문구 · `frontend/src/utils/strategyMeta.ts` · 픽스처 2 재생성 | |
| 테스트 | census `MIN_STRATEGIES` 무관(하한) · 전략 수를 박은 테스트 약 6파일 + 신규 Red | |
| **합계(추정)** | **src 약 12 · frontend 약 4 · migration 1 · tests 약 15~25** | 매매 로직이 없어 etf_trend 의 1/3 안팎 |

- `risk.py:89` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 에는 넣지 않는다. 넣으면 8영역이다. 넣지 않으면 매 틱 `check_buy_signal` 이 즉시 NONE 을 돌려주는 비용만 남는데, 무시할 만하다.

### U 의 청산 규칙
| 시각 | 처리 | 이유 |
|---|---|---|
| 부팅 07:45 감지 | 장부에 올리고 판정만 한다. 발사는 하지 않는다 | 장 전 |
| NXT 프리 08:00~09:00 | **발사 금지.** `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 밖이라 평가 자체가 보류된다 | 호가가 얇다. NXT 지정가로 바뀌면 미체결 `_selling` 이 남는다. KRX 전용 종목은 거부된다 |
| **KRX 정규장 09:00:30 ≤ t < 15:28** | `check_exit_signal` → `UNKNOWN_EXIT` 시장가. 첫 틱에 나간다 | **창 상수는 `status_exit_watch.FIRE_WINDOW_START/END` 를 그대로 쓴다**(같은 성격의 「출처 불문 청산」 이라 창을 하나로 둔다). 09:00:30 = 시가 단일가 직후 연속매매 |
| 15:28~16:00 | 발사 금지, 다음 영업일로 넘긴다 | 마감 동시호가 |
| KRX 애프터 16:00~20:00 | **발사 금지**, 다음 영업일 09:00:30 | 모르는 보유는 손절 비상이 아니다(진입 가설이 없다). 애프터는 시장가 불가(44/41), ETP·단기과열종목 제외, 호가가 얇다. 1주 언저리 랏의 하룻밤 위험보다 얇은 호가의 미끄러짐이 크다 |
| 틱이 안 오는 종목 | 15분 동기화가 받쳐 준다 — 창 안에서 `unknown` 보유를 보면 `execute_sell` 을 직접 부른다 | 체결이 없으면 틱도 없다. 그래도 호가에 매수 잔량은 있을 수 있다 |

- **실패·거부**: 새 규칙을 만들지 않고 `execute_sell` 의 기존 장치를 그대로 쓴다. 시장가 거부 → 5호가 지정가 1회, APBK0918 TTL, 수량 부족 = D1 안 A(지우지 않는다), `SellRejectionTracker`.
  - 더할 것은 cycle369 선례의 **종목당 하루 3회 상한**(`MAX_FIRES_PER_DAY=3`과 같은 값)뿐이다. 3회째 실패면 CRITICAL `[unknown_exit_giveup]` 을 남기고 그날 멈춘다. 다음 영업일에 다시 한다.
- **청산 전 감시**: U 는 켜져 있으므로 `on_tick` 평가 대상이다. 창 밖에서는 NONE 이다. 창 밖에서 따로 손절선을 두지 않는 이유는 둘이다. 진입 가설이 없어 「틀린 가격」 이 없고, 창 밖 시간대는 어차피 손절을 쏘지 않는 시간이다(프리 보류·애프터 금지). 「청산만」 이 맞다.
- **끄기 장치**: `system_config.unknown_exit_mode ∈ off|observe|enforce`.
  - 키가 없으면 **observe** 다. cycle369 의 `status_exit_mode` 는 키가 없으면 enforce 지만 **여기서는 반대로 둔다.** 처음 몇 주는 `[unknown_exit_would_fire]` 만 쌓아 오판이 없는지 본 뒤 사용자가 enforce 로 올린다.
  - 즉시 반영 PUT 1개(cycle369 `PUT /api/integrations/status-exit` 형태).
- **15분 경로도 `save_position(strategy_id="unknown")`** 을 한다(결함 후보 3 해소 — 재시작해도 표시가 남는다).

## Q3 — 예외 (자동 청산에서 뺄 것)
| 경우 | 장부에 어떻게 보이나 | 거르는 법 | 처리 |
|---|---|---|---|
| 회사분할 신주(신설법인) | **새 종목코드**가 잔고에만 있다 → F1 | CTRGA011R 45일 창, `rght_type_cd ∈ {12, 22}` | 판정 보류 + ERROR(사람) |
| 주식배당·무상증자 | 기존 종목이면 수량 차이(cycle431/433 몫) · 우리가 판 뒤 입고되면 F1 | `rght_type_cd ∈ {02, 03}` ∧ `rght_cblc_type_cd ∈ {1, 3, 21, 22}`(입고 계열) | 판정 보류 |
| 합병·주식교환·종목변경 | 새 코드 → F1 | `{11, 13, 16, 21, 23, 26}` | 판정 보류 |
| 공모주·청약 배정 | 새 코드 → F1 | `{91, 92}` · 유상 `{01}` | 판정 보류(사람이 받은 것일 가능성이 크다) |
| 전자증권 일괄입고 | F1 | `{58}` | 판정 보류 |
| 액면병합·분할 직후 | 종목코드가 같아 **F1 이 아니다**(수량 차이 = cycle431) | — | 대상 아님 |
| 계좌 대체 입고(10-13) | DB `positions` 에 있으면 부팅 1차가 복구 → F1 아님. 없으면 trade_history 의 **열린 왕복**으로 주인을 찾는다 | CTRGA 에 안 나온다(권리가 아니다) | 주인 있음 |

- **판정 규칙 하나로 줄이면 이렇다.** 그 종목의 CTRGA 45일 창에 **입고 계열 행이 하나라도 있으면** 자동 청산하지 않는다.
  - 코드는 2자리 문자열이다(`"01"`). `int()` 로 비교한다 — cycle431 의 `_CTRGA_*` 와 같은 방식이다.
  - 응답 키는 실측 `output` 이다(문서는 `output1`). `corporate_actions.fetch_period_rights` 를 그대로 쓴다.
- CTRGA 조회 실패·모의투자(빈 목록) → 실전에서 실패면 **판정 보류**(모름 ≠ 권리 없음)다. 모의투자는 원래 빈 목록이라 「권리 없음」 으로 본다.
- ⚠️ 회사분할 행의 `pdno` 가 옛 코드인지 새 코드인지는 표본이 없다. 새 코드 쪽 행이 없으면 걸러지지 않는다. 그래서 `observe` 기간에 이 경우가 나오는지 지켜봐야 한다(observe 기본값의 이유 중 하나).

## Q4 — 지금 숨은 결함을 따로 막아야 하나
- **코드 응급조치는 권고하지 않는다.** 30일 0건이고, 주인이 켜진 전략인 보유만 있다(10행 전부).
- **대신 10-13 전환 아침에 사람이 두 번 확인한다(코드 0).**
  1. 07:40 전환 직후, 새 계좌 잔고 종목 ⊆ `positions` 종목인지 본다. 넘치는 종목이 있으면 그것이 「사람 몫」 이거나 대체 누락이다.
  2. 07:45 부팅 뒤 `KIS 잔고 보완 복구` · `[boot_recover_strategy_unknown]` 를 grep 한다. 있으면 그 종목은 지금 코드로는 감시가 0 이다 → 사람이 팔거나 둔다.
- 다른 선택지:
  - **안 S — 섀도 momentum(코드 0, 설정만)**: momentum 을 VB 처럼 「켜짐 · 비중 0 · `shadow_mode=true`」 로 둔다. 순서 = `shadow_mode=true` → 비중 0.01 → 비중 0(각주 ⑩). 장외에 한다.
    - 효과: 폴백 보유가 momentum 규약을 탄다 — −5%(운영값) 손절 · 부팅 감지분은 다음 09:00 익일청산(갭 ≥ +10% 면 −2% 트레일링).
    - 비용: `scan_stocks` 는 momentum 이 꺼져 있어도 이미 돌고 있어서 구독 부담은 늘지 않는다. 대신 [shadow_buy] 로그가 생기고, AI 자문이 momentum 을 다시 다룬다.
    - 한계: **LTV 처럼 「주인 있음 + 꺼짐」 인 경우는 못 막는다.** 즉시 청산도 아니다.
  - **안 R — 근본 처방(8영역)**: `risk.on_tick` 이 청산 평가는 「보유가 있는 모든 전략」, 매수 평가는 「켜진 전략」 만 하게 한다. 「끄면 손절이 멈춘다」 함정 자체가 사라지지만, 루트 금기 문장과 `_execute_next_day_clear` 까지 바뀌는 큰 변경이다. **이번 범위가 아니다** — 기록만 해 둔다.

## Q5 — 고칠 자리 · 8영역 · 회귀 시나리오

### 고칠 자리 (안 U 기준)
| 파일 | 내용 | 8영역 |
|---|---|---|
| `src/db/trade_history.py` | 새 함수: 열린 왕복 주인 조회, 세 값 반환(`found` · `none` · `error`). 기존 `get_recent_buy_strategy` 는 둔다(다른 소비처) | 아님 |
| `src/engine/boot_manager.py` 2차 | 세 갈래 판정 · `unknown` 채택 · CTRGA 예외 · 폴백 `FALLBACK_OWNER_ID` → 판정 결과로 바꾼다 | 아님(행위 변경 → 승인) |
| `src/engine/scheduler.py::_sync_positions_from_balance` | 같은 판정(공용 leaf 위임으로 줄 수 증가 최소) + `save_position` + 창 안 `unknown` 백업 발사 | 아님(`<3,900L` 상한 · 승인) |
| 신규 leaf `src/engine/unknown_holding_policy.py` | 판정 순수 함수 + CTRGA 예외 + 모드 해석 + 하루 3회 상한 — 두 호출부가 공유 | 아님 |
| `src/engine/strategies/unknown_holding.py` · `strategy_manifest.py` · `param_catalog.py` · 마이그레이션 | 전략 등록 | 아님 |
| `src/engine/strategy_registry.py::update_weights` | 항상 켜짐 1줄 | **8영역 — 승인 + `_APPROVED_CONTENT_SHA`** |
| `src/routes/strategies.py` · `recommendations.py` · `recommendation_engine.py` · MCP 발사 · `funnel_capture.py` | 비중 > 0 거부 · 제외 | 아님 |
| 문서 | 루트 「핵심 안전 규칙」 1줄 · `strategies/CLAUDE.md` 표 · `00_leader_trading_rules.md` · `src/engine/CLAUDE.md` | — |

- 배포는 full(backend 재시작)이다. 장외 창 · 보유 중 장중 금지(D6) · 20:00~21:35 금지(D8).
- **10-13 전환 전에는 배포하지 않는다**(전환 아침에 판정 규칙이 바뀌면 원인을 가를 수 없다).

### 회귀 시나리오 (tdd-engineer 용)
| # | 상황 | 시각 | 기대 |
|---|---|---|---|
| R1 | 잔고에만 있음, 열린 왕복 BUY(kojiro, 켜짐) | 부팅 | kojiro 채택(현행과 같음) |
| R2 | 잔고에만 있음, BUY 0건, CTRGA 행 0 | 부팅 | `unknown` 채택 · `save_position(unknown)` · 발사 0 |
| R3 | R2 의 다음 틱 | 09:00:10 | 발사 0(창 전) |
| R4 | R2 의 첫 틱 | 09:00:31 | `UNKNOWN_EXIT` 시장가 1회 · enforce 일 때만(observe = `[unknown_exit_would_fire]` · 주문 0) |
| R5 | `get_*` 조회가 DB 예외 | 부팅·15분 | **판정 보류** — 장부 등록, 발사 0, ERROR 1행. momentum 폴백 0 |
| R6 | 마지막 BUY(5월 kojiro) < 마지막 SELL(5월) | 15분 | `unknown`(옛 왕복 상속 금지) |
| R7 | 열린 왕복 주인이 LTV(꺼짐) | 부팅 | 판정 보류 + ERROR `reason=owner_disabled`(결정 ④ 에 따라 청산 경로) |
| R8 | CTRGA 45일 창에 `rght_type_cd="12"` 입고 행 | 15분 | 판정 보류, 발사 0 |
| R9 | CTRGA 조회 실패(실전) | 부팅 | 판정 보류, 발사 0 |
| R10 | 그날 주문내역의 「우리 아닌」 매수 순수량 = 보유 수량 | 11:00 | 「오늘 사람이 산 것」 — 결정 ② 대로(기본 = 판정 보류) |
| R11 | `unknown` 보유 감지 | 16:30(애프터) | 발사 0, 다음 영업일 09:00:30 |
| R12 | `unknown` 보유 감지 | 08:10(프리) | 평가 보류(`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 밖) |
| R13 | 시장가 거부 → 5호가 지정가 → 또 실패 ×3 | 장중 | 3회째 CRITICAL `[unknown_exit_giveup]`, 그날 멈춤 |
| R14 | 수량 부족 거부 | 장중 | D1 안 A 규칙(지우지 않는다) |
| R15 | `PUT weights {"unknown": 0.1}` · AI 자문 apply 의 `unknown` 비중 | 언제든 | 422 / 거부, `enabled` 유지 |
| R16 | `PUT weights {"unknown": 0}` | 언제든 | `enabled` 유지(항상 켜짐) |
| R17 | AI 자문 20:00 | 20:00 | `unknown` 행 INSERT 0 · MCP job 0 |
| R18 | 다른 전략이 `unknown` 보유 종목에 매수 신호 | 장중 | `is_ticker_blocked_for_buy` 로 차단 |
| R19 | 청산 체결 | 장중 | `trade_history.strategy="unknown"` · `daily_performance` `unknown` 행 · `sold_today` · 구독 해제는 다른 전략 보유가 없을 때만 |
| R20 | 재시작(보유 중) | 아무 때 | DB `positions.strategy_id=unknown` 으로 1차 복구, 표시 유지 |
| R21 | 섀도 전략·일반 전략 비중 0 | 언제든 | 기존 규칙과 바이트 동일(update_weights 의 다른 분기 무변경) |

## 반례 / 한계
- 「계좌 전용」 전제가 틀리면 사람 주식을 판다. observe 기본값과 끄기 장치가 이를 줄이지만, enforce 로 올린 뒤에는 사람이 이 계좌에서 사는 순간 ≤ 15분(또는 다음 09:00:30)에 팔린다.
- 어제 이전에 산 사람 몫은 증거가 없다. 전제에 전적으로 기댄다.
- 회사분할 신주 행이 새 코드로 안 잡히면 R8 이 새고, 그 신주를 판다. 표본 0 이다.
- 틱이 없는 종목은 15분 백업이 받쳐도 최대 15분 늦는다.
- 46일 2건이라 이 장치 전체가 한 번도 안 돌 수 있다. 비용(약 30파일) 대비 가치는 「드물지만 나면 감시 0」 이라는 꼬리 위험을 없애는 것뿐이다.
- 🔸 이번 범위 밖, 한 줄 기록: 10-13 대체가 일부 종목에서 실패하면, 부팅 1차가 「KIS 미보유 DB 행」 을 지운다. 그날 아침 확인 ① 이 이것도 함께 잡는다.

## 후속 검증 권고
- 메인 세션(읽기 전용): 10-13 07:40 전 새 계좌 잔고 종목 목록 ↔ `positions` 10행 대조. 07:45 뒤 위 마커 grep.
- tester: 운영 `trade_history` 에서 「마지막 BUY < 마지막 SELL 인데 현재 보유」 종목이 있었는지 소급 조회(결함 후보 2의 실재 여부).
- tdd-engineer: R1~R21 Red. R5·R6·R7 이 현행 코드에서 붉은지 먼저 확인한다.
