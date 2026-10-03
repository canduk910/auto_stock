# cycle405 명세 — 돈키언(donchian_swing) 개조: 깡토식 청산·사이징

- 작성: team-leader · 2026-10-03 KST · 브랜치 `feat/donchian-kkangto-exit`(worktree `auto_stock_c405`)
- 사용자 결정(09-27, 10-03): 진입·유니버스 유지 + 깡토식 청산·사이징. 피라미딩·연승연패 크기 조절은 넣지 않는다. 청산 카드 2(오늘 ATR)는 개조에 흡수한다.
- 선행 자문: [`_workspace/domain_consult/cycle405_donchian_kkangto.md`](../domain_consult/cycle405_donchian_kkangto.md). 재현·사전 등록은 `_workspace/domain_consult/c405/`. 이 명세는 그 자문의 §2·§3·§6 을 구현 계약으로 옮긴 것이다. 숫자 근거는 자문을 본다.
- 범위: `src/engine/strategies/donchian_swing.py` 가 중심이다. 보조로 `strategy_manifest.py`(칸 1개) · `strategy_base.py`(시장 유닛 설계 랏 훅이 필요할 때만, 좁게) · `param_catalog.py`(새 키 등록·자동 튜닝 불가) · `llm_buy_gate.py`·`portfolio_risk.py`(donchian 손절 서술·산식 갱신)를 고친다.
- 🔴 **8영역**(`risk/order_engine/session/scanner/strategy_registry.py` · `api/order.py` · `realtime/**` · `auth/**`)과 **`scheduler.py`** 는 건드리지 않는다. 필요해지면 작업을 멈추고 team-leader 에게 보고한다.
- 🔴 `buy_paused` 키는 지우지 않는다(멈춰 둔 동안 키가 사라지면 조용히 풀린다).

---

## 1. 용어

| 기호 | 뜻 |
|---|---|
| E | `pos.buy_price` |
| N | `self._entry_atr[ticker]`. 매수 사이징에 쓴 ATR 스탬프(`_atr` SMA14, D−1 창). 그대로 쓴다 |
| R | 1R 폭(원). `R = max(kk_r_floor_pct/100 × E, kk_r_atr_mult × N)`. N 이 없거나 0 이하이면 ATR 항을 0 으로 본다. 그러면 `R = 0.08 × E` 다(조이는 쪽) |
| H | `pos.high_since_buy` |
| 무장(armed) | `H ≥ E + kk_breakeven_r × R` (3R 도달) |
| 1R 도달 | `H ≥ E + kk_time_exit_min_r × R` |
| days_held | `self._business_days_held(pos.buy_date, today)[0]`. 매수일 = 0 이다. 진입봉 포함 n 번째 봉은 `days_held = n − 1` 이다 |

R 은 매수 시점 값(E·N)으로만 정하고, 보유 중에는 바꾸지 않는다. 그래서 「오늘 ATR」(카드 2)은 쓸 곳이 없어진다. 샹들리에가 사라지기 때문이다. `_position_atr` 같은 새 사전은 만들지 않는다.

## 2. 청산 — `check_exit_signal`(장중 틱 + 60초 REST 폴, 지금 경로 그대로)

평가 순서와 반환값은 아래와 같다. 보유일 관측(`_emit_days_held_observation`)은 지금처럼 맨 앞에 둔다.

1. **손절선** `stop = E − R`. 무장이면 `stop = max(E − R, E) = E`(본전). 현재가 ≤ stop 이면 `Signal.STOP_LOSS` 다. 본전 손절도 `STOP_LOSS` 다(새 사유 이름을 만들지 않는다).
2. **10일 저가 채널** — 무장일 때만 본다. `channel_exit_period > 0` ∧ `_channel_low[t] > 0` ∧ 현재가 < `_channel_low[t]` 이면 `Signal.TRAILING_STOP` 이다. 무장 전에는 채널을 보지 않는다(→ `NONE`).
3. 그 밖이면 `Signal.NONE` 이다.

**끄는 것**(donchian 청산이 더 읽지 않는다): 2×N 하드손절(`stop_atr`) · −9% 받침선(`turtle_backstop_pct`) · 미스탬프 고정% 손절(`stop_loss_rate`) · 1.5N 본전 승격(`breakeven_promote_atr`) · 샹들리에(`atr_trail_mult`) · 돌파 실패 시간 청산(`breakout_fail_n_days`, `check_exit_signal` 의 §2.5 블록 전체).

**시간 청산은 `check_exit_signal` 에 두지 않는다.** 15:20 경로(§3) 하나만 쓴다. 다음 날 첫 틱(08:00 프리장 얇은 호가)에 시장가가 나가는 것을 막기 위해서다.

**스탬프 게이트 원칙은 유지한다.** 손절 산식을 `sizing_mode` 로 가르지 않는다. 스탬프가 있으면 ATR 항이 살고, 없으면 8% 하한만 남는다.

## 3. 15:20 시간 청산 — `check_force_clear` / `force_clear_signal`

- `strategy_manifest.py` 의 donchian 행 `close_at_1520=True` 로 바꾼다. 다른 칸·다른 행은 건드리지 않는다. `scheduler.py` 의 15:20 루프는 `CLOSE_AT_1520_IDS` 를 돌 뿐이라 무접촉이다.
- `check_force_clear()` 는 **그날 끝내야 할 종목만** 돌려준다. 전량 반환은 금지다(멀티데이 소멸). 보유 종목마다 아래 둘 중 하나가 참이면 넣는다.
  - (a) `days_held ≥ kk_time_exit_bars − 1`(기본 19) ∧ 1R 미도달(`H < E + kk_time_exit_min_r × R`)
  - (b) `days_held ≥ kk_max_hold_bars − 1`(기본 249)
- 가격 시세를 읽지 않는다. 고점·보유일·스탬프만 쓴다. 그래서 etf_trend 의 「15:20 시세 stale」 문제가 없다.
- never-raise 다. 종목 하나의 예외는 그 종목만 건너뛰고 WARNING 을 남긴다. 전체 예외는 `[]` + WARNING 이다(etf_trend 선례).
- `buy_date` 가 없는 포지션은 넣지 않는다(판정 불가 = 팔지 않음). 마커는 1회/종목/일이다.
- 관측 마커 `[donchian_time_exit] ticker=… reason=no_1r|max_hold days_held=… high=… target_1r=…`(INFO)와 요약 `[donchian_1520_check] held=… due=…`(INFO)를 남긴다.
- `force_clear_signal(ticker)` → `Signal.TIME_EXIT`.
- 15:20 을 놓치면(재시작·매도 거부) 다음 날 15:20 에 조건이 계속 참이라 다시 잡힌다. 별도 안전망은 두지 않는다.

## 4. 화면 손절가 미러 — `get_effective_stop_price`

- `check_exit_signal` 과 **같은 헬퍼**를 쓴다. 예: `_kk_exit_lines(ticker, pos) -> (stop: float, armed: bool, channel: float | None)`. 두 경로가 산식을 따로 갖지 않는다.
- 미러 = `max(stop, 무장일 때 channel)` 의 양수 값을 `int` 로 돌려준다. 시간 청산은 가격선이 아니라 뺀다. read-only · 로그 없음 · 예외 = `None`(지금 규약).

## 5. 사이징 — `calc_buy_quantity`

- B = `self.state.total_investment`, m = 시장 유닛 배수(enforce 일 때만 1 미만, 그 밖은 1), P = 현재가, N = `_candidates[t]["atr"]`(`_MARKET_UNIT_ATR_KEY`).
- `R_buy = max(0.08 × P, 1.5 × N)`(키 `kk_r_floor_pct`·`kk_r_atr_mult`).
- **설계 랏** `q = floor(B × m × risk_pct ÷ R_buy)`. 그 뒤 `q = min(q, int(B × m × position_ratio) // P)`.
- q > 0 이면 `_apply_budget_limit(q, P, ticker)` 에 넘긴다. 관문 본문·순서는 그대로다. 잔여 클램프가 부분 매수를 만든다.
- q = 0 이면 상수 `return 0` 이다(A-GATE 허용 형태). **1주 폴백도, `position_ratio` 낙하도 없다**(어느 날이든).
- 스탬프: q > 0 이면 사이징에 쓴 그 N 을 `_entry_atr[t]` 에 넣는다. 지금과 같은 커플링이다. N 이 없거나 0 이하이면 사지 않는다(q = 0). 스탬프 없는 랏이 생기지 않는다.
- `calc_buy_quantity` 의 첫 줄 시장 유닛 호출 규약(cycle382 A10)을 지킨다. 지금 `_market_unit_sizing` 의 터틀 경로(`compute_unit_qty_guarded`)는 R 기반이 아니다. 그래서 donchian 이 설계 랏을 자기 식으로 내도록 좁은 훅을 쓰거나 덮어쓴다. `[market_unit]` 기록(lot_before·lot_after)은 계속 남아야 한다(m=1 판과 m 판의 q).
- K축(`max_lot_units` 2.0)·ρ축(`max_lot_ratio_mult` 2.5)은 그대로 둔다. 설계 랏은 둘 다에 항등적으로 닿지 않는다(자문 §3). 키를 지우지 않는다(AST glob 가드).
- `sizing_mode` 코드 기본값을 `"turtle"` 로 바꾼다. 개조 사이징은 이 값을 보지 않는다. 재시작 재도출 게이트(`_entry_atr_rederive_allowed`, cycle355)만 이 값을 본다.

## 6. 신호 단계 거름 — `check_buy_signal`

수량 0 을 `execute_buy` 로 흘리지 않는다. 흘리면 `order_engine` 이 「투자금 부족 900초 쿨다운」 으로 오귀인한다(cycle382 와 같은 이유). 시장 유닛 거름과 같은 자리에서 걸러 `Signal.NONE` 을 돌려준다.

1. **설계 랏 0** — §5 의 q(잔여 클램프 전)가 0 이면 `NONE` + `[donchian_kk_lot_zero] ticker=… price=… r=… budget=… m=…`(INFO, 1회/종목/일). 잔여 부족(`funds`)은 거르지 않는다. 기존 자금 경로가 맞는 귀인이다.
2. **하루 신규 상한** `max_daily_entries`(기본 3) — 이 전략의 「오늘 매수일인 보유 수 + 주문 중(`pending_buys`) 수」 가 상한 이상이면 `NONE` + `[donchian_daily_entry_cap] ticker=… count=… cap=…`(INFO, 1회/종목/일). 재시작 뒤에도 보유의 `buy_date` 로 다시 센다.
- 순수 메모리 조회다. `await`·DB·HTTP 금지(hot path).
- 거름 순서: 공통 게이트(종목상태 → `buy_paused` → 계좌 SOFT) → 기존 진입 조건 → 시장 유닛 거름 → 설계 랏 0 → 하루 상한. `buy_paused=true` 이면 지금처럼 맨 앞에서 멈춘다.

## 7. 키 (`DEFAULT_PARAMS`)

### 7.1 새 키 — 전부 `PARAM_RANGES`/`INT_PARAMS` · AI 자문 자동 적용 **편입 금지**(리스크 정체성 상수)

| 키 | 기본 | 읽는 쪽 범위(벗어나거나 숫자가 아니면 기본값 + WARNING 1회/일) |
|---|---|---|
| `kk_r_floor_pct` | 8.0 | [4, 20] |
| `kk_r_atr_mult` | 1.5 | [0.5, 4] |
| `kk_breakeven_r` | 3.0 | [1, 10] |
| `kk_time_exit_bars` | 20 | [5, 60] 정수 |
| `kk_time_exit_min_r` | 1.0 | [0, 3] |
| `kk_max_hold_bars` | 250 | [20, 500] 정수 |
| `max_daily_entries` | 3 | [1, 10] 정수 |

`param_catalog.py` 에 등록한다(화면 라벨·그룹). 자동 튜닝 불가로 표시한다.

### 7.2 값을 바꾸는 기존 키

| 키 | 코드 기본 → |
|---|---|
| `risk_pct` | 0.005 → **0.012**(뜻: 1R 손실 = 예산 1.2%) |
| `position_ratio` | 0.20 → **0.15** |
| `max_positions` | 5 → **6**(0.15 × 6 = 0.9 ≤ 1.0) |
| `sizing_mode` | position_ratio → **turtle** |
| `channel_exit_period` | 10 그대로(뜻: 무장 뒤에만) |

운영 DB 값이 코드 기본값을 이긴다. 그래서 배포 뒤 PUT 이 필요하다(§10).

### 7.3 끄는 키

`stop_atr` · `atr_trail_mult` · `breakeven_promote_atr` · `breakout_fail_n_days` · `turtle_backstop_pct` · `stop_loss_rate` · `min_vol_floor_pct` 를 donchian 청산·사이징이 더 읽지 않는다. **이번 사이클에서는 `DEFAULT_PARAMS` 에서 지우지 않는다.** 소비처(`pyramid_shadow.py` · `portfolio_risk.py` · `llm_buy_gate.py` · `param_catalog.py` · 프론트 fixture · AI 자문)가 넓어서 지우는 일은 따로 한다(「결정 필요」 D7). 대신 donchian 이 이 키들을 읽지 않는다는 것을 AST 로 묶는다(§9 G-405-3).

## 8. 주변 서술·산식 갱신 (관측·자문 경로, 매매 행위 무관)

- `llm_buy_gate.py` — donchian 손절 산식(`_resolve_stop_loss_pct` 의 donchian 분기)과 청산 서술 문장을 새 규칙으로 바꾼다. 손절 % = `−max(kk_r_floor_pct, kk_r_atr_mult × atr14_pct)`. 서술 = 「−1R 손절(R=max(8%, 1.5×ATR)) · 3R 도달 시 본전 · 3R 뒤 10일 저가 이탈 · 20봉째 15:20 에 +1R 미도달이면 정리 · 최대 250봉」.
- `portfolio_risk.py` — donchian 포지션의 손절 % 가 옛 키(`turtle_backstop_pct`)로 잡히면 새 R 손절로 바꾼다. 가능하면 전략의 `get_effective_stop_price` 를 쓴다. 범위가 커지면 donchian 분기만 R 하한(`kk_r_floor_pct`)으로 바꾸고 보고한다.
- `pyramid_shadow.py` 의 donchian 가상 사다리는 이번에 손대지 않는다(관측 전용, 피라미딩 제외 결정). 후속 목록에 올린다.

## 9. 테스트 계약 (tdd-engineer)

결정적 입력 시리즈(자문 §10 기반). 시각은 freezegun 으로 고정한다.

1. **R 두 갈래** — E=100,000 · N=4,000 → R=8,000, 손절 92,000(92,000 → STOP_LOSS, 92,001 → NONE). N=6,000 → R=9,000, 손절 91,000.
2. **스탬프 없음** — `_entry_atr` 없음 → R=0.08E.
3. **무장 경계** — H = E+3R−1: 채널 이탈해도 NONE, 손절은 E−R. H = E+3R: 손절선 = E(E 에서 STOP_LOSS), 채널 이탈 → TRAILING_STOP.
4. **옛 청산이 죽었다** — 샹들리에선 아래 · 2일 돌파 실패 조건 · −9% 받침선 · 1.5N 승격 조건을 각각 만들어도 NONE(새 손절선 위일 때).
5. **15:20 시간 청산** — days_held 19 ∧ H < E+R → 포함 · H = E+R → 제외 · days_held 18 → 제외 · days_held 249 → H 와 무관하게 포함 · `buy_date` 없음 → 제외 · 한 종목 예외가 다른 종목 판정을 막지 않음 · 전체 예외 → `[]`. `force_clear_signal` → `TIME_EXIT`. 놓친 다음 날도 포함.
6. **명부** — `CLOSE_AT_1520_IDS` 에 `donchian_swing` 이 들어간다. 다른 칸·다른 전략은 golden 그대로.
7. **미러 일치** — 같은 상태에서 `get_effective_stop_price` 가 `check_exit_signal` 의 가격선 max 와 같다(무장 전/후 각각).
8. **사이징** — B=743,000 · m=1 · N 작음: P=111,450 → 1주, P=111,451 → q=0. q=0 이면 `check_buy_signal` 이 `NONE` + 마커, `calc_buy_quantity` 는 0(폴백 없음). m=0.5 → 설계 랏이 절반(폴백 없음). 스탬프 = 사이징 N. N 없음 → 0.
9. **하루 3종목** — 오늘 매수일 보유 2 + pending 1 → 네 번째 신호 NONE + 마커. 어제 매수 보유는 세지 않는다.
10. **관문 무접촉** — `_apply_budget_limit` 본문 sha 불변 · K축·ρ축이 설계 랏 수량을 바꾸지 않음.
11. **AST 가드(신규 `tests/unit/ast/test_cycle405_ast_donchian_kk.py`)**
   - G-405-1: 새 키 7개와 바꾼 키가 `PARAM_RANGES`/`INT_PARAMS`(런타임 dict + 소스 리터럴)에 없다.
   - G-405-2: `check_exit_signal`·`get_effective_stop_price`·`check_force_clear` 본문에 `await`·DB·HTTP 심볼이 없다. 시장 유닛 토큰이 청산 경로에 없다(cycle382 A07 유지).
   - G-405-3: donchian 청산·사이징 함수 본문이 `stop_atr`·`atr_trail_mult`·`breakeven_promote_atr`·`breakout_fail_n_days`·`turtle_backstop_pct`·`stop_loss_rate`·`min_vol_floor_pct` 를 읽지 않는다.
   - G-405-4: `check_exit_signal` 과 `get_effective_stop_price` 가 같은 헬퍼를 부른다.
   - G-405-5: `DEFAULT_PARAMS` 에 `buy_paused` 가 있다. 불변식 `position_ratio × max_positions ≤ 1.0` 이 성립한다.
   - G-405-6: 8영역·`scheduler.py` diff 0(기존 sha 핀 방식).
12. 기존 donchian 테스트 중 옛 청산·사이징을 단언하는 것은 새 계약으로 고치거나 지운다. 지운 테스트와 이유를 목록으로 남긴다. 옛 규칙을 지키던 sha 핀은 재핀한다. 행위 단언을 공허하게 만들지 않는다.

## 10. 배포·전환 (메인 세션 몫, 이 사이클은 하지 않는다)

1. donchian 보유 0 확인(10-03 실측 0).
2. 장외 창에 합치고 배포. `buy_paused=true` 그대로.
3. `PUT /api/strategies/donchian_swing/params {"params":{"risk_pct":0.012,"position_ratio":0.15,"max_positions":6}}` → GET·DB 확인. 잊으면 1.0%·0.2·5 로 돈다(더 작은 쪽).
4. `PUT {"params":{"buy_paused":false}}`.
5. 첫날 확인: `[donchian_kk_lot_zero]`·`[donchian_daily_entry_cap]`·`[donchian_1520_check]` 마커 · 매수 랏 크기 · 15:20 루프에 donchian 이 돈다.
- 전환 방식 = 구 규칙 대체(모드 키 없음). 비상 브레이크 = `buy_paused`. 되돌리기 = 커밋 되돌림 + 장외 배포(가능하면 보유 0 에서).

## 11. 결정 필요 (권고값으로 진행)

| # | 질문 | 이번 구현 |
|---|---|---|
| D1 | 사전 등록 판정 미통과(J1 하한 −0.64%p, 점추정 +13%p · 낙폭·R 통과). 계획대로 진행할까 | 진행(사용자 09-27·10-03 결정). 합치기 전에 사용자가 이 결과를 본다 |
| D2 | 1주 폴백 없음(지금 예산에서 신호 34% 무매수) | 없음 |
| D3 | 하루 신규 3종목 상한 | 3 |
| D4 | 슬롯 6 × 0.15 | 6 × 0.15 |
| D5 | 전환 방식 | 구 규칙 대체, 모드 키 없음 |
| D6 | 시간 청산 시점 | 15:20 |
| D7 | 끄는 키 삭제 | 이번엔 남긴다(소비처 정리를 따로) |
