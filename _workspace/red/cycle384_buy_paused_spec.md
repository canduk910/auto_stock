# cycle384 Red 명세 — 공통 `buy_paused`(신규 매수 신호만 멈춤) · 돈키언 매수 멈춤

- 작성: domain-expert · 2026-09-27(일) 13:40 KST
- 결정 원문: 워크리스트 「09-27 결정 세트」 — 「돈키언 신규매수 중지」(보유분은 원래 청산 규약대로 자연 소진, 개조는 전용 브랜치에서 뒤에). 설정으로는 불가(돈키언 매수 창 09:05~09:30 코드 고정) → **7전략 공통 `DEFAULT_PARAMS["buy_paused"]=False` 신설 후 donchian 만 PUT true**. 사용자 지시 「새 제안 금지 — 이대로 구현」 → 범위 밖은 §16 한 줄 후속으로만
- 무접촉: 8영역(`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`api/order`·`realtime/**`·`auth/**`) · `scheduler.py` · `boot_manager.py`

---

## 0. 결론 (한눈에)

| 항목 | 정한 것 |
|---|---|
| 막는 자리 | `StrategyBase._account_soft_gate_blocked` 의 **두 번째 문장**(첫 문장 = cycle369 상태 차단, J25 불변). 7전략 `check_buy_signal` 이 전부 이 게이트를 지나므로 전략 7파일에는 **`DEFAULT_PARAMS` 한 줄 말고 손대지 않는다** |
| 막는 방식 | 신호 단계에서 `Signal.NONE`. 수량 0·`buy_disabled`·`enabled`·`weight` 어느 것도 쓰지 않는다 |
| 값 읽기 | 매 호출 `self.config.params.get("buy_paused")` — **`is True` 일 때만 멈춘다**. 부재·`False`·그 밖의 모양(문자열 `"true"`·`1`·`None`)은 멈추지 않음 + 모양이 틀리면 WARNING |
| 막을 때 지우는 것 | ① cycle369 과 **같은** `_clear_edge_baseline_on_block(ticker)`(모양 기반 — BFB·VCP 평평한 `_prev_price` 는 안 건드림) ② 새 `_clear_entry_latches_on_pause(ticker)` = BFB `_breakout_first_seen` · BFB/VCP `_vol_latch` 의 그 종목만 pop |
| 안 지우는 것 | `_bought_today` · `_position_setup` · `_entry_atr` · `_cooldown_until` · `_breakout_watch` · 평평한 `_prev_price` · 시장 유닛 스냅샷 |
| 마커 | `[buy_paused_config]` 1회/(전략,값)/일 — paused=1·모양 오류 WARNING, paused=0 INFO · `[buy_paused_skip]` 1회/(종목,전략)/일 **INFO**, 후보 종목만 |
| 카탈로그 | `buy_paused` bool · `editable` · `risk="identity"` · `auto_tunable=False` · 그룹 `entry` · 7전략 · `range_src="enum"` · 키 104→105 · identity 17→18 · `CATALOG_VERSION="cycle384.1"` |
| AI 차단 | `PARAM_RANGES`/`INT_PARAMS` 편입 금지 → 수동·자동 자문 적용 경로가 둘 다 화이트리스트로 거른다(코드 추가 0) |
| 배포 | `src/` 변경 = **full**(backend 재시작). 창 = 오늘(일) 종일 또는 21:35~09-28 07:45 |
| 09-28 조작 | 배포 → **설정이 DB 에서 로드됐는지 먼저 확인** → `PUT /api/strategies/donchian_swing/params {"params":{"buy_paused":true}}` → GET·DB 로 확인. 09:05 전 |
| 롤백 | 같은 PUT 에 `false` — 즉시(다음 1분 폴). 🔴 코드 되돌림은 곧 **조용한 해제**다 |

---

## 1. 트레이더 시각

**가설** — 돈키언의 진입 신호(20일 신고가 돌파 + EMA60 위)는 그대로 두되, 청산·사이징을 깡토식으로 바꾸기 전까지 **새 표본을 옛 규약으로 쌓지 않는다**. 이미 들고 있는 종목은 원래 규약(2ATR 하드손절 · 브레이크이븐 승격 · 채널 이탈 · 돌파 실패 · 트레일링)으로 자연히 나가게 둔다. 「손은 떼되 손절은 계속 건다」— 트레이더 말로 **신규 진입 동결, 포지션 관리는 정상**이다.

**이 도구여야 하는 이유(깨지면 무엇이 나나)**

| 흔한 대안 | 무엇이 깨지나 |
|---|---|
| 전략 끄기(`enabled=False`) / 비중 0 | 🔴 `risk.on_tick` 이 `registry.enabled()` 만 돈다 → 돈키언 보유분 **손절·트레일링 전부 정지**(루트 금기). 비중 0 은 `update_weights` 가 `enabled` 를 자동으로 끈다 |
| 수량 0 반환(`calc_buy_quantity`) | 신호는 BUY 로 나가 `execute_buy` 가 돌고, 0주 → **900초 「투자금 부족」 쿨다운**으로 오귀인. 21:30 분석이 「돈키언 자금 부족」을 결함으로 보고한다 |
| `state.buy_disabled=True` | 일일 손실 래치다 — `_reset_daily_state` 가 밤에 풀고, 화면·로그가 「일일 손실 한도 도달」로 읽힌다(cycle233 G4 가 이 필드를 다른 용도로 쓰지 못하게 막는 이유) |
| `max_positions` 로 막기 | 리스크 정체성 상수 + 예산 불변식 짝 — 멈춤 용도로 쓰면 해제 때 원래 값 복원이 사람 기억에 달린다 |

**위험 시나리오(이 명세가 막는 것)**
1. 해제 첫 틱이 **거짓 돌파** — 첫 문장 게이트 전략(LTV·BFB·VCP)은 막힌 동안 기준가 갱신이 멈춘다(§4).
2. 멈춘 사이 **죽은 셋업이 되살아나 매수** — BFB/VCP 래치는 멈춘 동안 `flag_low`/`base_low` 이탈 해제 판정을 못 받는다(§4).
3. **잊어버림** — 개조가 몇 주 걸리면 「돈키언은 왜 안 사지」가 결함으로 오진된다 → 매일 WARNING 1줄(§5).
4. **PUT 이 운영 DB 를 코드 기본값으로 덮음** — 설정 로드 전의 PUT 은 메모리의 코드 기본값 전체를 `save_params` 로 저장한다(§11 사전 점검).
5. **코드 되돌림 = 조용한 해제** — DB 의 `buy_paused:true` 는 코드에 키가 없으면 `_load_strategy_config` 가 버린다(§12).

---

## 2. 게이트 자리 — 7전략 전수

### 2.1 공통 게이트를 지나는 7개 호출부 (현재 HEAD `f5df838`)

| 전략 | `check_buy_signal` 정의 | 게이트 호출 | 자리 | 호출원 |
|---|---|---|---|---|
| momentum | `strategies/momentum.py:126` | `:176` | **발사 직전** — 돌파 if(`:172`) 안, 기준가 갱신(`:169`) 뒤 | `risk.on_tick` (`risk.py:770`) |
| VB | `strategies/volatility_breakout.py:903` | `:980` | **발사 직전** — 돌파 if(`:973`) 안, 기준가 갱신(`:967`) 뒤, 09:00 보류 블록 앞 | `risk.on_tick` |
| LTV | `strategies/long_tail_volatility.py:761` | `:773` | **첫 문장** | `risk.on_tick` |
| donchian | `strategies/donchian_swing.py:1626` | `:1631` | **첫 문장** | `scheduler._swing_buy_poll_loop` (`scheduler.py:2809`) **만** — WS 틱 매수 평가는 `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 로 skip |
| BFB | `strategies/bull_flag_breakout.py:956` | `:958` | **첫 문장** | `risk.on_tick` |
| VCP | `strategies/vcp_breakout.py:1396` | `:1398` | **첫 문장** (바로 뒤 `:1401` `_observe_breakout_tick`) | `risk.on_tick` |
| kojiro | `strategies/kojiro.py:891` | `:898` | **첫 문장** | `_swing_buy_poll_loop` 만 |

- 배치 규약 정본 = `tests/unit/ast/test_cycle233_ast_account_risk.py:28-32`(`GATE_FIRST_FILES` 5 · `GATE_PRE_BUY_FILES` 2). 이 사이클은 **호출부를 하나도 옮기지 않는다** — 멈춤을 게이트 **안**에 넣으므로 두 배치 규약이 그대로 멈춤에도 적용된다.
- 게이트 소비처가 `check_buy_signal` 뿐이라는 사실(`account_risk_watcher.py:12` 주석)이 「청산 무접촉」의 구조적 근거다 — §9 A06 가 봉인한다.

### 2.2 `_account_soft_gate_blocked` 의 새 모양 (`strategy_base.py:1336`)

```python
def _account_soft_gate_blocked(self, ticker: str | None = None) -> bool:
    """(docstring — cycle384 한 단락 추가: 순서 = 상태 차단 → buy_paused → 계좌 SOFT)"""
    if self._status_buy_blocked(ticker):      # 1번째 문장 — cycle369 J25, 변경 금지
        return True
    if self._buy_paused_blocked(ticker):      # 2번째 문장 — cycle384
        return True
    try:                                      # 3번째 — 기존 계좌 SOFT 게이트 byte 동일
        ...
```

**순서의 이유**
- 상태 차단이 먼저(J25) — 관리·단기과열 종목은 멈춤 여부와 무관하게 막히고, 그 skip 은 cycle369 이 센다.
- 멈춤이 계좌 SOFT 보다 먼저 — 멈춘 전략에서 `[account_gate_skip]` 이 찍히면 원인이 「계좌 오픈리스크」로 **오귀인**된다. 멈춤은 운영자가 정한 결정적 상태라 먼저 판정한다.

### 2.3 새 헬퍼 — `strategy_base.py` (전부 동기 · `await`/DB/HTTP/`write_log` 0 · never-raise)

```python
#: cycle384 — 신규 매수 멈춤 키. PARAM_RANGES/INT_PARAMS 편입 금지(AI 가 켜고 끄면 안 된다).
BUY_PAUSED_KEY = "buy_paused"
_BUY_PAUSED_ABSENT = object()
#: 멈춘 종목에서 지우는 진입 래치 — 이 두 이름뿐(§4). 모양으로 판정(dict 일 때만).
_PAUSE_ENTRY_LATCH_ATTRS: tuple[str, ...] = ("_breakout_first_seen", "_vol_latch")

# __init__ (market unit caps 뒤):
self._buy_paused_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()

def _buy_paused_blocked(self, ticker: str | None) -> bool:
    try:
        raw = self.config.params.get(BUY_PAUSED_KEY, _BUY_PAUSED_ABSENT)   # 매 호출 읽기
    except Exception:
        logger.debug("[buy_paused_gate_failed] ...", exc_info=True)
        return False                                   # fail-open (게이트 관례)
    paused = raw is True
    valid = raw is _BUY_PAUSED_ABSENT or isinstance(raw, bool)
    self._emit_buy_paused_config(raw, paused, valid)   # 관측 — 행위 밖
    if not paused:
        return False
    if ticker:
        self._clear_edge_baseline_on_block(ticker)     # cycle369 헬퍼 그대로 재사용
        dropped = self._clear_entry_latches_on_pause(ticker)
        self._emit_buy_paused_skip(ticker, dropped)    # 관측 — 행위 밖
    return True                                        # ticker 가 비어도 멈춤(전략 단위)
```

- **`is True` 만 멈춤** — `bool(raw)` 로 읽으면 문자열 `"false"` 가 멈춤이 된다. PUT 은 bool 이 아니면 422 로 거부하므로(`param_validation.py:304-307`) 모양 오류는 DB 직접 수정·구버전 행에서만 생긴다 → 멈추지 않음 + WARNING(`max_lot_ratio_mult` 「키 부재 = OFF」 관례와 같은 방향 — 설정이 없거나 이상하면 **매수를 조용히 막지 않는다**).
- **캐시 금지** — `prepare()`·`__init__` 에서 값을 복사해 두면 PUT 이 다음 재시작까지 안 먹는다. PUT 라우트는 `strategy.config.params.update(...)`(`routes/strategies.py:385`)로 같은 dict 를 고치므로 매 호출 읽기면 **다음 틱·다음 1분 폴**에 반영된다.
- `_clear_entry_latches_on_pause(ticker) -> tuple[str, ...]` — `_PAUSE_ENTRY_LATCH_ATTRS` 의 속성이 `dict` 이면 `pop(ticker, None)`, 실제로 뺀 속성 이름(앞 `_` 제거)을 돌려준다. 예외 흡수(debug). 다른 속성 접근 0.
- `_clear_edge_baseline_on_block` 은 **본문 무변경**(상태 차단 경로의 행위가 바뀌면 안 된다).

---

## 3. 값 해석표

| DB/메모리 값 | 멈춤 | 카나리아 | 비고 |
|---|---|---|---|
| `true` (JSON bool) | **예** | WARNING `paused=1 valid=1 raw=True` | 정상 멈춤 |
| `false` | 아니오 | INFO `paused=0 valid=1 raw=False` | 기본 |
| 키 부재 | 아니오 | INFO `paused=0 valid=1 raw=absent` | 코드 배포 뒤엔 `DEFAULT_PARAMS` 병합으로 사실상 없음(테스트 전략·수동 생성 config) |
| `"true"` · `"True"` · `1` · `0` · `null` · `"false"` · `[]` | 아니오 | WARNING `paused=0 valid=0 raw='true'` 등 | PUT 은 422. DB 직접 수정 흔적 |

---

## 4. 막을 때 지우는 것 · 풀 때 · 이유

「멈춤」은 게이트 안이라 **첫 문장 전략은 멈춘 동안 신호 함수 본문이 통째로 안 돈다**(기준가·래치가 얼어붙는다). **발사 직전 전략(momentum·VB)은 돌파 순간에만** 게이트에 닿는다(기준가는 계속 갱신).

| 전략 | 얼어붙는 진입 상태 | 막을 때 | 해제 뒤 첫 틱 | 근거 |
|---|---|---|---|---|
| momentum | `_prev_prdy_rate[t]` (발사 직전이라 계속 갱신됨) | 돌파 틱에서 pop (cycle369 헬퍼) | 기록만 → NONE | 첫 틱은 기록만(`momentum.py:163-166`) |
| VB | `_prev_price[t][board]` 중첩 (계속 갱신됨) | 돌파 틱에서 pop | `prev==0` → NONE | 추격 상한 없는 추격 매수 방지(C233-F1) |
| LTV | `_prev_price[t][board]` 중첩 — **얼어붙음** | 매 멈춤 틱 pop | `prev==0` → NONE | cycle369 R2 탐침과 같은 병리(목표 10,500 · 옛 기준 10,400 · 해제 첫 틱 11,900 → BUY +13%) |
| donchian | 기준가 없음. `_bought_today` | **안 건드림** | 창(09:05~09:30) 안이면 곧바로 정상 평가 | 후보는 전일 종가 기준 고정 · 갭 판정은 오늘 시가 · 추격 상한(`max_breakout_extension_pct`)은 당일 고가로 — 창 중간 해제 = 창 중간 재기동과 같다. `_bought_today` 에 넣으면 같은 날 해제가 무의미해진다 |
| kojiro | 기준가 없음. `_bought_today` | **안 건드림** | 위와 같음 | 같음 |
| BFB | 평평한 `_prev_price[t]` · `_breakout_first_seen[t]` · `_vol_latch[t]` — 얼어붙음 | `_prev_price` **안 건드림** · `_breakout_first_seen[t]`·`_vol_latch[t]` pop | 래치·유지 대기 없음 → 새 edge-crossing 만 인정 | 아래 ① ② ③ |
| VCP | 평평한 `_prev_price[t]` · `_vol_latch[t]` — 얼어붙음 | `_prev_price` **안 건드림** · `_vol_latch[t]` pop | 위와 같음 | 아래 ② ③ |

① **`_breakout_first_seen`(BFB 유지 대기)** — 멈추기 전에 1차 돌파가 감지돼 있으면, 멈춘 사이 가격이 `flag_high` 아래로 물러나 대기가 끝났어야 할 것도 얼어붙은 채 남는다. 해제 첫 틱이 `flag_high` 위이고 경과가 `breakout_retention_minutes` 를 넘었으면 **연속 유지 확인 없이** 곧장 거래량 게이트로 간다 = 낡은 유지 완주. → 지운다.

② **`_vol_latch`(BFB/VCP 거래량 대기 래치)** — 래치 경로는 `flag_low`/`base_low` 이탈(`stop_line`)·레벨 이동(`level_moved`)을 **평가될 때만** 해제한다. 멈춘 사이 베이스가 무너졌다 돌아오면 해제 첫 틱에 **죽은 셋업을 산다** — cycle228 이 래치 설계에서 명시적으로 금지한 001450 역선택 그대로다. → 지운다. 지운 뒤 해제 첫 틱은 신선 경로(`_prev_price` 비교)로 가는데, 래치를 무장했던 마지막 신선 평가가 `_prev_price` 를 레벨 **이상**으로 남겼으므로 교차가 성립하지 않는다 — 가격이 레벨 아래로 내려갔다 다시 뚫어야 한다(보수적 포기).

③ **평평한 `_prev_price`(BFB/VCP)는 건드리지 않는다** — 없는 값이 `0` 으로 읽혀 `0 < level <= current` 가 참이 되는 **새** 거짓 교차를 만든다(cycle369 `_clear_edge_baseline_on_block` docstring · `test_cycle369_r2_edge_baseline.py` 마지막 두 테스트). 대신 **잔여 위험**이 남는다: 멈추기 전 기준가가 레벨 아래이고 멈춘 사이 가격이 레벨을 넘었으면, 해제 첫 틱이 그 교차를 **늦게** 본다. 이것은 가짜 교차가 아니라 멈춘 동안 실제로 일어난 교차이고(가격이 아래→위로 간 것은 사실), BFB 는 유지 대기가 해제 시점부터 새로 시작되며 VCP 는 추격 상한(7.5%)이 추격 폭을 묶는다. 게다가 BFB/VCP 의 `_prev_price` 는 **밤을 넘겨서도 지워지지 않는다**(BFB `_reset_daily_state` 는 `_breakout_first_seen` 만 비운다, `bull_flag_breakout.py:1529`) — 즉 이 「늦은 교차」는 멈춤이 새로 만든 위험이 아니라 WS 공백·밤사이 갭과 같은 기존 의미론이다. 특성화 테스트 T21 로 못박는다.

**안 지우는 것(이유)**
- `_position_setup` · `_entry_atr` · `_breakeven_latched` · `_stop_floor` 류 — **청산** 상태다. 건드리면 보유분 손절선이 바뀐다.
- VCP `_breakout_watch`(cycle349 관측) — 매수 상태가 아니다. 멈춘 동안 그 종목 틱 기록이 멈추는 것은 §15 한계.
- 시장 유닛 스냅샷(`_market_unit_snaps`) — `prepare()` 가 채우고 멈춤과 무관(§6).
- `_cooldown_until` — 청산이 만드는 재진입 금지라 멈춤과 독립.

---

## 5. 마커 (로거 `src.engine.strategy_base` · peek → log → mark · 실패는 `trace_observer_failure` · 행위는 cap 밖)

🔴 `write_log` 병행 금지 — 루트 `_DbLogHandler` 가 `src.*` INFO 이상을 `system_logs` 에 `[src.engine.strategy_base] <메시지>` 형태로 이미 넣는다(`main.py:196-215`).

### 5.1 `[buy_paused_config]` — 설정 카나리아

```
[buy_paused_config] strategy=%s paused=%d valid=%d raw=%s note='%s'
```
- cap = `_buy_paused_logged`, 키 상수 3개 `cfg|1|1` · `cfg|0|1` · `cfg|0|0` → **1회/(전략, 값)/일**. 같은 날 true→false→true 로 바꾸면 줄은 2개(두 번째 true 는 이미 찍힘).
- 레벨: `paused=1 ∧ valid=1` → **WARNING** · `valid=0` → **WARNING** · `paused=0 ∧ valid=1` → INFO. `logger.warning`/`logger.info` 를 **따로** 부른다(`logger.log(level,…)` 금지 — cycle258 로거-사망 계측이 두 이름을 죽인다).
- note: paused=1 「신규 매수 신호만 멈춤 — 손절·트레일링·익일청산·강제청산·종목상태 청산은 그대로」 · paused=0 「멈춤 아님」 · valid=0 「참/거짓이 아닌 값 — 멈추지 않음으로 읽음(PUT 은 거부하므로 DB 직접 수정 흔적)」.
- `raw` 는 `repr(raw)[:40]`, 부재면 `absent`.
- **WARNING 인 이유(paused=1)** — 21:30 일일 분석은 「상위 WARNING 패턴」을 모델에 준다(`log_analysis_engine.py` 집계). 멈춘 전략은 무매매가 **정상**인데, 개조가 몇 주 걸리면 그 무매매가 결함으로 오진된다. 하루 1줄 WARNING 이 「돈키언은 일부러 멈춰 있다」를 매일 보고서에 올린다 — 잊음 방지가 이 줄의 유일한 목적이다.
- 닿는 조건(= 줄이 안 찍혀도 결함이 아닌 경우): 그 전략의 게이트가 그날 한 번이라도 불려야 한다. momentum·VB 는 **돌파가 있어야**, donchian·kojiro 는 **09:05 이후 스윙 폴에 후보가 1개 이상**이어야 닿는다. 그래서 운영 확인의 정본은 로그가 아니라 GET·DB 다(§11).

### 5.2 `[buy_paused_skip]` — 멈춘 동안 평가된 후보

```
[buy_paused_skip] strategy=%s ticker=%s cand=1 dropped=%s note='buy_paused — 신규 매수 신호 보류(청산·손절 무관)'
```
- cap = 같은 인스턴스, 키 `skip|{ticker}` → **1회/(종목, 전략)/일**. 순서: `should_emit` 로 먼저 엿보고 → 엿보기 통과일 때만 후보 판정 → 후보면 로그 → mark. **후보가 아니면 mark 하지 않는다**(장중 `prepare()` 재실행으로 뒤늦게 후보가 된 종목도 기록되게).
- 후보 판정 = cycle369 `_is_status_gate_candidate(ticker)` **재사용**(momentum·VB 는 항상 참 — 게이트가 발사 직전이라 닿는 것 자체가 돌파 증거; 나머지는 `get_scanned_tickers()`·`_targets`·`_candidates` 멤버십). 후보가 아닌 종목은 **줄 없이 막는다**(LTV·BFB·VCP 는 구독 종목 ~158개 전부의 틱에서 게이트가 불린다 — 전부 찍으면 소음).
- `dropped` = `_clear_entry_latches_on_pause` 반환(`breakout_first_seen,vol_latch` 또는 `-`). 첫 멈춤 틱에서만 값이 생긴다(멈춘 동안에는 래치가 새로 생길 수 없다) — 1회/일 줄이 그 순간을 정확히 담는다.
- **INFO 인 이유** — 운영자가 정한 상태의 결과이지 이상이 아니다. WARNING 이면 후보 수만큼 매일 21:30 상위 WARNING 을 채워 진짜 경고를 밀어낸다. 「멈춰 있다」는 사실은 §5.1 WARNING 1줄로 충분하다.
- 줄의 뜻이 전략마다 다르다(§15): momentum·VB = **실제 돌파가 났다** / 나머지 = **후보가 평가됐다**(창·갭·거래량 판정 전).

### 5.3 흔적

- 판정 실패 `[buy_paused_gate_failed]` DEBUG(게이트 관례 — hot path 에서 INFO 이상 금지).
- 관측 실패 = `trace_observer_failure("[buy_paused_config]"|"[buy_paused_skip]", key, cap)` — WARNING 1회/(marker,key)/일.
- 래치 정리 실패 `[buy_paused_latch_clear_failed]` DEBUG.

---

## 6. 다른 관문과의 관계

| 관문 | 관계 |
|---|---|
| **종목상태 차단(cycle369)** | 먼저 판정(J25). 둘 다 걸리면 `[status_block_buy_skip]` 만 찍히고 멈춤은 평가되지 않는다. 기준가 비우기는 둘이 같은 헬퍼 |
| **계좌 SOFT(cycle233)** | 멈춤이 먼저 — 멈춘 전략에서 `[account_gate_skip]` 은 0줄(귀인 보존). 계좌 게이트 본문 byte 동일(J25b) |
| **시장 유닛(cycle382)** | 신호 필터 `_market_unit_blocks_entry`(donchian `:1689` · kojiro `:1009` · BFB `:1135` · VCP `:1528`)와 calc 분기 `_market_unit_sizing` 이 전부 **게이트 뒤**다 → 멈춘 전략에서는 `[market_unit] where=signal·calc` 가 0. `prepare()` 의 `_refresh_market_unit` → `[market_unit_state]` 와 `[market_unit_daily]`(calc_attempts=0)는 그대로. **돈키언은 멈춘 동안 시장 유닛 shadow 표본 0** — 1주 shadow 뒤 enforce 판단은 kojiro·BFB·VCP 표본만으로 한다(돈키언 enforce 여부는 개조 합칠 때 함께) |
| **09:00 진입 보류(cycle262)** | VB 는 게이트(`:980`)가 보류 블록 앞 → 멈춘 VB 는 `[open_entry_hold_blocked]` 0. LTV 는 첫 문장 게이트 뒤라 `[open_entry_hold_config]` 도 0(기존 F-6 한계와 같다) |
| **LLM 매수평가 shadow(cycle274·297)** | 주문 시점 기록이라 멈춘 전략은 `llm_buy_evaluations` 0행 — 비용도 0 |
| **kojiro 갭 관측(cycle268)** | 게이트 뒤 → 멈춘 kojiro 는 관측 0(이번 운영 대상 아님) |
| **VCP 돌파 관측(cycle349)** | `_observe_breakout_tick` 이 게이트 뒤 → 멈춘 VCP 는 watch 틱 0(이번 운영 대상 아님) |
| **스윙 매수 폴(`scheduler._swing_buy_poll_loop`)** | 무접촉. 멈춘 돈키언 후보는 `_bought_today` 에 안 들어가므로 09:05~09:30 **매 분 REST 조회가 계속된다**(후보 N × 최대 26회). 멈추지 않았다면 갭 스킵·매수로 빠졌을 종목도 창 끝까지 조회된다 — 비용 증가분만 있고 행위 영향은 없다 |
| **스윙 REST 폴(`_swing_rest_poll_loop`, 09:30~15:20)** | 무접촉 — 보유분 손절 평가 보강은 그대로 |
| **피라미딩 shadow(cycle351)** | 실거래 앵커 기반 — 멈춘 동안 돈키언의 **새** 앵커 0(보유분은 청산 때 앵커가 생긴다) |
| **퍼널·후보 준비·구독** | `prepare()`·09:30 퍼널 캡처·21:00 저녁 미리보기·구독은 키를 읽지 않는다(A04) — 그대로 돈다 |
| **param_drift(cycle326)** | 운영 DB `true` ≠ 코드 `False` 로 부팅 드리프트 목록에 오른다 — 또 하나의 가시 채널(정상) |

---

## 7. 카탈로그 · AI 차단

`param_catalog.py` 1행(그룹 `entry` 끝, 또는 그룹 내 정렬 규칙이 있으면 그 자리):

```python
_s(
    key="buy_paused", label_ko="신규 매수 멈춤", group="entry",
    type="bool", min=None, max=None, step=None, unit="",
    editable=True, risk="identity", auto_tunable=False, deprecated=False,
    applies_to=_ALL7, range_src="enum",
    help="cycle384 — 켜면(true) 이 전략의 **신규 매수 신호만** 멈춘다. 보유 종목의"
         " 손절·트레일링·익일청산·15:20 강제청산·종목상태 청산·시간 청산은 그대로 돈다."
         " 전략을 끄거나 비중을 0 으로 하는 것과 다르다 — 그 둘은 보유분의 손절까지"
         " 멈춘다. 후보 준비·퍼널 기록·시세 구독도 계속된다. 멈춘 동안 그 전략의 매수"
         " 신호 뒤쪽 관측(시장 유닛 기록·LLM 매수평가·갭/돌파 관측)은 함께 멈춘다."
         " 기본 false. 키 부재·참/거짓이 아닌 값은 **멈추지 않음**으로 읽는다(+ WARNING)."
         " `PUT /api/strategies/{id}/params` 로 즉시 반영되고 DB 에도 저장돼 재시작 뒤에도"
         " 유지된다. 멈춰 있는 동안 매일 WARNING 1줄(`[buy_paused_config]`)이 남는다."
         " AI 자동 튜닝 대상이 아니다(`PARAM_RANGES`/`INT_PARAMS` 편입 금지).",
),
```
- `range_src="enum"` — 편집 가능한 bool 선례 `failed_breakout_exit_enabled`(`param_catalog.py:1020-1027`). `"none"` 이면 PUT 마다 `range_unbounded` 경고가 붙는다.
- 모듈 docstring 의 「합집합 103 키」·identity 「16 키」 목록 서술을 현재 수(105 · 18)로 고치고 `buy_paused` 를 identity 목록에 넣는다.
- `CATALOG_VERSION = "cycle384.1"`.
- **AI 차단은 코드 추가 없이 성립한다** — 수동 적용 `routes/recommendations.py:136`(`valid_keys = {k … if k in PARAM_RANGES}`)과 자동 적용 `auto_apply_recommendations` 가 둘 다 `PARAM_RANGES` 화이트리스트다. 이 사이클의 의무는 **넣지 않는 것**과 그것을 가드(A11)로 봉인하는 것.

---

## 8. 파일 · 무접촉 · 재핀

### 8.1 바뀌는 파일

| 파일 | 내용 |
|---|---|
| `src/engine/strategy_base.py` | §2.2 게이트 2번째 문장 · §2.3 상수 3개 + 헬퍼 4개(`_buy_paused_blocked` · `_clear_entry_latches_on_pause` · `_emit_buy_paused_config` · `_emit_buy_paused_skip`) · `__init__` cap 1개 · 게이트 docstring 한 단락 |
| `src/engine/strategies/*.py` 7개 | `DEFAULT_PARAMS` 의 `"max_lot_ratio_mult": 2.5,` **다음 줄**에 `"buy_paused": False,` + 주석(`# cycle384 — 신규 매수 신호만 멈춤(청산 무관). 부재·비bool = 멈추지 않음. PARAM_RANGES/INT_PARAMS 편입 금지. 켜고 끄기 = PUT 즉시`). 그 밖의 줄 0 |
| `src/engine/param_catalog.py` | §7 |
| `frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts` | `tools/test_fixtures/gen_param_schema_fixture.py` 재생성분(손으로 고치지 않는다) |
| `frontend/src/components/__tests__/_ast_param_key_hardcode.test.ts` | 104→105 값만 + 이력 문구 「· cycle384 104→105」 |

### 8.2 무접촉 (확인 대상)
8영역 · `scheduler.py` · `boot_manager.py` · `status_exit_watch.py` · `account_risk_watcher.py` · `market_unit.py` · `recommendation_engine.py`(`PARAM_RANGES`·`INT_PARAMS` 핀 그대로) · `routes/strategies.py`·`routes/recommendations.py`(행위 무변경 — 기존 검증이 bool 을 받는다) · `_clear_edge_baseline_on_block` 본문.

### 8.3 예상 재핀 (값만 · 주석 `🔁 cycle384 재핀 — buy_paused 공통 파라미터(사용자 결정 09-27 「돈키언 신규매수 중지」)`)
- `tests/unit/ast/test_cycle278_ast_catalog_guards.py` — `_DEFAULT_PARAMS_SHA` **7개** · `_BASE_SHA`(strategy_base + 7전략) · 카탈로그 핀
- `tests/unit/ast/test_cycle287_ast_scope.py` `_SRC_TREE_DIGEST`
- sha 핀이 걸린 나머지(현재 `strategy_base.py`·전략 7파일·`param_catalog.py` 를 덮는 파일): `test_cycle223_ast_donchian_exit_fix` · `test_cycle223f_ast_manual_apply_safeguard` · `test_cycle272_ast_main_rest_basis` · `test_cycle273_ast_kojiro_rank` · `test_cycle274_ast_llm_gate` · `test_cycle276_ast_order_hook` · `test_cycle282_ast_purity` · `test_cycle286_ast_scope` · `test_cycle290_ast_scope` · `test_cycle291_ast_scope` · `test_cycle293_ast_channel_resolver` · `test_cycle294_ast_stage3` · `test_cycle297_ast_scope` · `test_cycle352_ast_ltv_close_hold` · `test_cycle382_ast_market_unit` · `engine/strategies/test_cycle226_zero_breakout_defense` · `engine/test_cycle297_llm_strategy_context` — **전체 스위트가 붉힌 것만**
- 수 핀: `test_cycle278_param_catalog.py:204·208`(104→105) + `_BRIEF_IDENTITY_KEYS` 에 `buy_paused`(주석 「cycle384 — 신규 매수 멈춤. 매수 행위를 바꾸는 스위치라 2단계 확인」) · `test_cycle290_killswitch_registration.py:787-789` · `routes/test_cycle278_params_schema.py:148` · `contract/test_routes_strategies.py:168`
- 🔴 재핀 전에 diff 가 §8.1 자리뿐인지 눈으로 본다(핀을 먼저 재산출하지 않는다). 백엔드 인덱스 `tools/test_impact/build_index.py` 는 **Green 단계에서만** 재생성.

---

## 9. 테스트 목록 (Red)

파일: `tests/unit/engine/test_cycle384_buy_paused_gate.py`(T01~T13 · T24~T32) · `tests/unit/engine/strategies/test_cycle384_buy_paused_unpause.py`(T14~T23) · `tests/unit/routes/test_cycle384_buy_paused_params_route.py`(R01~R06) · `tests/unit/ast/test_cycle384_ast_buy_paused.py`(A01~A15) · `tests/integration/test_cycle384_buy_paused_pg.py`(P01).
픽스처 참고: 전략별 「사는 순간」 합성은 `tests/unit/engine/_cycle369_support.py`(시계 `pin_module_clock`·`kst`) · `strategies/test_cycle382_market_unit_signal.py` · 스윙 폴은 `test_swing_poll_loop.py` · `risk.on_tick` 은 `test_risk_donchian_skip_buy.py` 하네스. 시각 창 테스트는 **freezegun 으로 창 안·밖 두 시각**(메모리 규약).

### 9.1 게이트 · 배선
| # | 무엇 |
|---|---|
| T01 | 7전략 `DEFAULT_PARAMS["buy_paused"] is False`(값·타입 bool) |
| T02 | 상태 차단 ∧ 멈춤 → `_account_soft_gate_blocked` True 이고 `_buy_paused_blocked` **미호출**(spy) |
| T03 | 멈춤 ∧ 계좌 SOFT → True · `[account_gate_skip]` **0줄** · `[buy_paused_skip]` 1줄 |
| T04 | 멈춤 아님 ∧ 계좌 SOFT → 기존대로 `[account_gate_skip]`(회귀) |
| T05 | **7전략 파라미터화** — 멈추지 않으면 BUY 가 나는 합성 입력에서 멈추면 `Signal.NONE` · `state.buy_signals` 무증가. donchian·kojiro = 09:10 창 안 후보(갭<임계) · momentum = 28.9%→29.1% 교차 · VB·LTV = 09:10 목표가 교차 · BFB = `breakout_retention_minutes=0` + 관측 거래량 ≥ 임계 · VCP = 교차 + 거래량 |
| T06 | 같은 인스턴스에서 `config.params["buy_paused"]` 를 True→False 로 바꾸면 **다음 호출**이 BUY(donchian, 재시작·prepare 없이) — 반대 방향도 |
| T07 | `calc_buy_quantity` 산출이 멈춤 여부와 무관하게 같다(donchian·kojiro·momentum) — 멈춤이 수량 단계에 없다 |
| T08 | 멈춘 채 30회 호출 뒤에도 `state.buy_disabled is False` · `pending_buys` 불변 · `_bought_today` 불변(donchian·kojiro·BFB·VCP) · `is_low_funds_blocked` 미등록 |
| T09 | §3 해석표 전수 — `True` 만 멈춤, 나머지는 멈추지 않음 + `valid=0` WARNING 1회/일 |
| T10 | 멈춤 + `ticker=None`/`""` → True(전략 단위), 비우기·skip 줄 0 |

### 9.2 청산 무접촉
| # | 무엇 |
|---|---|
| T11 | **7전략 차분** — 같은 보유·같은 가격 경로(손절선 관통 · 트레일링 되밀림 포함)에서 멈춤 False/True 두 인스턴스의 `check_exit_signal` 시퀀스와 청산 상태(`pos.high_since_buy`·전략별 손절 상태 dict)가 동일 |
| T12 | `RiskManager.on_tick` — LTV 멈춤 + 보유 종목 손절가 틱 → `execute_sell` 1회, `execute_buy` 0회. donchian 멈춤 + 보유 종목 손절가 틱 → `execute_sell` 1회 |
| T13 | 스윙 폴 하네스 — donchian 멈춤 · kojiro 정상, 둘 다 살 수 있는 후보 → `execute_buy` 는 kojiro 만. 다음 분에도 donchian 후보가 `filtered` 에 남는다 |

### 9.3 해제 첫 틱 (거짓 돌파·낡은 매수 금지)
| # | 무엇 |
|---|---|
| T14 | LTV — 목표 10,500 · 멈추기 전 기준가 10,400 · 멈춤 틱들 · 해제 첫 틱 11,900 → **NONE**. 그 뒤 10,400→10,600 진짜 교차 → BUY |
| T15 | VB — 멈춘 채 교차 틱에서 중첩 기준가 pop · 해제 다음 틱(목표 위 그대로) → NONE |
| T16 | momentum — 멈춘 채 교차 틱 pop · 해제 다음 틱 29.3% → NONE |
| T17 | BFB 낡은 래치 — 멈추기 전 래치(flag_high 10,000 · flag_low 9,500) · 첫 멈춤 틱 뒤 `_vol_latch` 에 종목 없음 · 해제 첫 틱 10,100 + 거래량 충족 → **NONE**(정리가 없으면 BUY — M15 가 이걸로 잡힌다) |
| T18 | BFB 낡은 유지 대기 — `_breakout_first_seen[t]=now−10분` · 멈춤 틱에서 pop · 해제 첫 틱 10,100 → NONE(거래량 게이트로 직행하지 않음) |
| T19 | VCP 낡은 래치 — T17 의 VCP 판 |
| T20 | 평평한 `_prev_price`(BFB·VCP)는 멈춤 전후 **값이 같다**(pop 금지 — 0 이 새 거짓 교차를 만든다) |
| T21 | **특성화(잔여 위험 문서화)** — VCP 기준가 9,900 < base_high 10,000 로 멈춤 · 해제 첫 틱 10,300(+3% < 추격 상한 7.5%) + 거래량 충족 → BUY(늦은 교차 = WS 공백·밤사이 갭과 같은 기존 의미론). BFB 같은 조건 → 그 틱은 NONE + `_breakout_first_seen` 새로 등록 |
| T22 | donchian·kojiro 창 중간 해제 — 09:20 해제 → 첫 평가 BUY(재기동과 동치) |
| T23 | 래치 정리는 두 속성만 — `_position_setup`·`_entry_atr`·`_breakout_watch`·`_cooldown_until`·`_breakeven_latched` 불변 |

### 9.4 마커
| # | 무엇 |
|---|---|
| T24 | donchian 멈춤, 후보 종목 50회 → `[buy_paused_skip] strategy=donchian_swing ticker=… cand=1 dropped=-` **정확히 1줄** · 비후보 종목 → 0줄(그래도 NONE) · 다음 KST 날짜 → 다시 1줄 |
| T25 | skip 은 INFO(`levelno == logging.INFO`), 로거 `src.engine.strategy_base` |
| T26 | 카나리아 — 멈춤 → WARNING `paused=1 valid=1 raw=True` 1줄 · 같은 날 해제 → INFO `paused=0` 1줄 · 다시 멈춤 → 새 줄 0 |
| T27 | 로거 사망(`logger.info`·`logger.warning` 이 예외) → 게이트 결과 불변(True) · 예외가 `check_buy_signal` 밖으로 안 샌다 · 다음 호출이 다시 시도(peek→log→mark) · debug 흔적 존재 |
| T28 | `src.db.system_logs.write_log` 호출 0(spy) |
| T29 | BFB — 래치·유지 대기가 있던 종목의 첫 멈춤 틱 → `dropped=breakout_first_seen,vol_latch` |

### 9.5 상호작용
| # | 무엇 |
|---|---|
| T30 | donchian 멈춤 + `market_unit_mode=enforce` + m=0 스냅샷 → `[market_unit] where=signal` 0줄. `prepare()` 는 `[market_unit_state]` 를 그대로 낸다 |
| T31 | (`real_status_watch`) 상태 차단 ∧ 멈춤 → `[status_block_buy_skip]` 있음 · `[buy_paused_skip]` 없음 |
| T32 | donchian 멈춤이 kojiro 에 번지지 않는다(인스턴스별 params) |

### 9.6 라우트 · 카탈로그 · DB
| # | 무엇 |
|---|---|
| R01 | `PUT /api/strategies/donchian_swing/params {"params":{"buy_paused":true}}` → 200 · `data.applied == {"buy_paused": True}` · `warnings == []` · `save_params` 가 **병합 전체 dict**(기존 운영값 보존)로 1회 |
| R02 | `"true"`·`1`·`null` → 422(type) · 저장 0 |
| R03 | R01 직후 같은 레지스트리의 donchian 이 창 안 후보에 NONE — 재시작 없이 |
| R04 | 자문 적용 — `recommended_params={"buy_paused": false, <PARAM_RANGES 키>}` → `buy_paused` 는 `[manual_apply_safeguard_skip] key=buy_paused` 로 제외, 나머지는 적용 · 자동 적용 경로도 제외 |
| R05 | `GET /api/strategies/params-schema` 에 `buy_paused`(bool · identity · editable · entry · 7전략) |
| R06 | 카탈로그 105키 · identity 18 · `CATALOG_VERSION == "cycle384.1"` |
| P01 | (실 Postgres) `save_params` → `load_all` → `jsonb_typeof(params->'buy_paused')='boolean'` · Python `True` → 새 스케줄러의 `_load_strategy_config` 가 메모리에 True 로 덮는다(재시작 뒤 유지) |

### 9.7 AST 가드 (`Path.read_text` + AST · 소스 세그먼트 · `git grep` 금지 · `ast.dump` sha 금지)
| # | 무엇 |
|---|---|
| A01 | J25 그대로(기존 가드 — 첫 문장 = 상태 차단) |
| A02 | 게이트 2번째 문장 = `if self._buy_paused_blocked(ticker): return True`(orelse 없음), 3번째 = 기존 `Try` |
| A03 | 헬퍼 4개 = 동기 `FunctionDef` · `Await`/`AsyncFor`/`AsyncWith` 0 · 호출명 `write_log`·`safe_write_log`·`kis_*`·`fetch_*`·`create_task`·`ensure_future` 0 · `pg.` 0 · 모듈 최상위 import 추가 0 |
| A04 | 문자열 `"buy_paused"` 위치 = `strategy_base.py` 1(상수 정의) · `strategies/*.py` 각 1(클래스 `DEFAULT_PARAMS` dict 의 키, 값 `False` 상수) · `param_catalog.py` 1. 그 밖 `src/**` 0 |
| A05 | `BUY_PAUSED_KEY` 참조는 정의 + `_buy_paused_blocked` 안뿐 |
| A06 | `_buy_paused_blocked` 호출은 `src/` 전체에서 1곳(`_account_soft_gate_blocked`). `_account_soft_gate_blocked` 호출은 `strategies/*.py` 의 `check_buy_signal` 안 7곳뿐 |
| A07 | 캐시 금지 — `self.<…paused…>` 대입은 `__init__` 의 `_buy_paused_logged` 하나뿐 · `_buy_paused_blocked` 에 `self.config.params` 속성 사슬 존재 |
| A08 | `_buy_paused_blocked` 토큰에 `buy_disabled`·`enabled`·`weight`·`pending_buys`·`_bought_today`·`low_funds`·`calc_buy_quantity`·`total_investment` 0 |
| A09 | `_PAUSE_ENTRY_LATCH_ATTRS == ("_breakout_first_seen", "_vol_latch")`(리터럴 튜플) · `_clear_entry_latches_on_pause` 는 `.pop(ticker, None)` 만 · `_clear_edge_baseline_on_block` 에 `_vol_latch`/`_breakout_first_seen` 0(상태 차단 경로 무변경) |
| A10 | 멈춤 분기(`if ticker:` 안)에 `_clear_edge_baseline_on_block(ticker)` → `_clear_entry_latches_on_pause(ticker)` 순서로 호출 |
| A11 | `buy_paused` ∉ `PARAM_RANGES` · ∉ `INT_PARAMS` — 런타임 dict + `recommendation_engine.py` 소스 리터럴 이중(G-245-1 방식) |
| A12 | glob `src/engine/strategies/*.py` — `DEFAULT_PARAMS` 를 가진 모든 파일에 `"buy_paused": False`(8번째 전략이 들어와도 자동으로 잡힌다) |
| A13 | `[buy_paused_` 마커를 내는 함수에 `write_log` 쌍 0(F3b 방식) |
| A14 | 8영역 · `scheduler.py` · `boot_manager.py` 에 `buy_paused`·`_buy_paused_blocked` 토큰 0 |
| A15 | `_emit_buy_paused_skip` 의 `[buy_paused_skip]` 은 `logger.info` 로만(`logger.warning` 0) |

---

## 10. 돌연변이 (tester — 각 항목을 잡는 곳)

| # | 돌연변이 | 잡는 곳 |
|---|---|---|
| M01 | 멈춤 검사 삭제 | T05 |
| M02 | 멈춤 검사를 상태 차단 **앞**으로 | A01(J25) · T02 |
| M03 | 멈춤 검사를 계좌 SOFT **뒤**로 | T03 · A02 |
| M04 | `calc_buy_quantity` 에서 0 반환으로 구현 | T05 · T07 |
| M05 | `state.buy_disabled = True` 로 구현 | T08 · A08 |
| M06 | `config.enabled = False`/`weight=0` 로 구현 | T11 · T12 · A08 |
| M07 | `prepare()`/`__init__` 에서 값 캐시 | T06 · R03 · A07 |
| M08 | `bool(raw)` 판정(`"false"` 가 멈춤) | T09 |
| M09 | 모양 오류 = 멈춤(fail-closed) | T09 |
| M10 | 한 전략 `DEFAULT_PARAMS` 기본값 True | T01 |
| M11 | 한 전략 `DEFAULT_PARAMS` 에서 키 누락 | T01 · A12 · R01(해당 전략 unknown_key) |
| M12 | `PARAM_RANGES`(또는 `INT_PARAMS`)에 편입 | A11 · R04 |
| M13 | 멈춤 분기의 `_clear_edge_baseline_on_block` 호출 삭제 | T14 · A10 |
| M14 | 평평한 `_prev_price` 까지 pop | T20 · T21(BFB·VCP 가 0 기준 교차로 즉시 반응) |
| M15 | 래치 정리 삭제 | T17 · T18 · T19 |
| M16 | 래치 정리가 `_position_setup`/`_entry_atr` 도 비움 | T23 · A09 · T11 |
| M17 | 멈춤 때 `_bought_today.add(ticker)` | T08 · T22 |
| M18 | skip 줄을 비후보에도 | T24 |
| M19 | skip cap 삭제 | T24(정확히 1줄) |
| M20 | mark → log 순서(로그 실패 시 그날 관측 소실) | T27 |
| M21 | 관측 예외를 흡수하지 않음 | T27 |
| M22 | 카나리아 paused=1 을 INFO 로 | T26 |
| M23 | skip 을 WARNING 으로 | T25 · A15 |
| M24 | 같은 줄을 `write_log` 로도 | T28 · A13 |
| M25 | `self.DEFAULT_PARAMS` 에서 읽음 | T06 · R03 |
| M26 | 돈키언 `check_exit_signal` 에 멈춤 검사 추가 | T11 · A04 |
| M27 | `CATALOG_VERSION` 미갱신 | R06 |
| M28 | 멈춘 전략의 `_refresh_market_unit` 건너뜀 | T30 |
| M29 | 돈키언 파일에만 구현(공통 게이트 아님) | T05 의 나머지 6전략 · A06 |
| M30 | `ticker` 가 비면 False(멈춤 누락) | T10 |
| M31 | 후보가 아닐 때도 mark(뒤늦게 후보가 된 종목 기록 소실) | T24 의 「장중 후보 편입」 변형 |

---

## 11. 09-28(월) 운영 절차

### 11.1 순서
1. **배포(full)** — 창: 오늘(일) 종일 또는 21:35~09-28 07:45(20:00~21:35 는 주말이 아니면 금지). push 뒤 `gh run list` 로 CI·Deploy 초록 · `/health` 200. 🔴 배포가 PUT 보다 **먼저**다(코드에 키가 없으면 PUT 은 `unknown_key` 422).
2. `TZ=Asia/Seoul date` — **09:05 전**인지. 권장 = 배포 확인 직후(일요일 밤). 늦어도 09-28 08:55 BFB `entry_end` 확인 때 같이.
3. **사전 점검 — 설정이 DB 에서 로드됐나(위험 시나리오 4)**
   ```bash
   curl -s -u "$BASIC_USER:$BASIC_PASS" https://auto.dkstock.cloud/api/strategies \
     | jq '.data.donchian_swing | {enabled, weight, positions, position_tickers,
            buy_paused: .params.buy_paused, sizing_mode: .params.sizing_mode,
            max_positions: .params.max_positions, stop_loss_rate: .params.stop_loss_rate}'
   ```
   ```sql
   SELECT params->>'sizing_mode' sm, params->>'max_positions' mp, params->>'stop_loss_rate' sl
   FROM strategy_config WHERE strategy_id = 'donchian_swing';
   ```
   두 결과의 `sizing_mode`·`max_positions`·`stop_loss_rate` 가 **같아야** 한다(09-20 실측 운영값 = `turtle` · `3` · `-6.0`, 코드 기본값 = `position_ratio` · `5` · `-7.0`). GET 이 코드 기본값을 보이면 **PUT 하지 않는다** — 설정 로드가 실패한 상태의 PUT 은 `save_params` 가 코드 기본값 전체를 DB 에 써서 돈키언 사이징·손절이 바뀐다. 이때는 backend 로그의 「전략 설정 초기 로드 실패」를 먼저 본다.
4. **PUT**
   ```bash
   curl -s -u "$BASIC_USER:$BASIC_PASS" -X PUT -H 'Content-Type: application/json' \
     https://auto.dkstock.cloud/api/strategies/donchian_swing/params \
     -d '{"params":{"buy_paused":true}}' | jq '{success, applied: .data.applied, warnings: .data.warnings}'
   ```
   기대: `success=true` · `applied={"buy_paused":true}` · `warnings=[]`. (화면 Settings 로 해도 된다 — identity 라 2단계 확인이 뜬다.) 🔴 `enabled`·`weight` 는 건드리지 않는다.
5. **사후 확인 — GET**: 3번 명령 재실행 → `buy_paused: true` · `enabled: true` · `weight`·`positions`·`sizing_mode`·`max_positions`·`stop_loss_rate` **전과 같음**.
6. **사후 확인 — DB**:
   ```sql
   SELECT params->'buy_paused' v, jsonb_typeof(params->'buy_paused') t,
          params->>'sizing_mode' sm, params->>'max_positions' mp, updated_at
   FROM strategy_config WHERE strategy_id = 'donchian_swing';
   -- 기대: v=true · t=boolean · sm/mp 가 3번과 같음
   SELECT strategy_id, params->'buy_paused' FROM strategy_config ORDER BY 1;
   -- 기대: donchian_swing 만 true. 나머지는 false 또는 NULL(키 없음 = 코드 기본 false — 정상)
   ```

### 11.2 09-28 기대 로그 (`system_logs`, 메시지 앞에 `[src.engine.strategy_base] ` 가 붙는다)
```sql
SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS') t, log_level, message
FROM system_logs
WHERE timestamp >= '2026-09-28 07:40+09' AND timestamp < '2026-09-28 21:35+09'
  AND (strpos(message, '[buy_paused_') > 0 OR strpos(message, '[swing_poll]') > 0
       OR strpos(message, '도치안 스윙') > 0 OR strpos(message, 'strategy=donchian_swing') > 0)
ORDER BY timestamp;
```

| 시각 | 있어야 하는 것 | 없어야 하는 것 |
|---|---|---|
| 07:45~ `prepare()` | `[market_unit_state] strategy=donchian_swing …`(시장 유닛 기록 계속) | — |
| 08:00~09:05 | 다른 6전략 `[buy_paused_config] … paused=0 valid=1` INFO(각 전략 게이트가 처음 닿을 때, momentum·VB 는 돌파가 있어야) | donchian 의 `[buy_paused_*]`(돈키언 매수 평가는 09:05 스윙 폴에서만 시작 — 정상) |
| **09:05:0x 첫 스윙 폴** | 돈키언 후보가 1개 이상이면: `[buy_paused_config] strategy=donchian_swing paused=1 valid=1 raw=True` **WARNING 1줄** + 후보마다 `[buy_paused_skip] strategy=donchian_swing ticker=XXXXXX cand=1 dropped=-` INFO 1줄 | 돈키언 후보 0개면 두 줄 모두 없음 — **결함 아님**(확인은 GET·DB) |
| 09:05~09:30 매 분 | `[swing_poll] candidates=… filtered=… bought=…` — `bought` 는 kojiro 몫만. 돈키언 후보는 창 끝까지 `filtered` 에 남는다(매 분 REST 조회) | `도치안 스윙 매수 신호` · `도치안 스윙 갭 스킵` · `[donchian_extension_skip]` · `[market_unit] strategy=donchian_swing … where=signal\|calc` · `[account_gate_skip] strategy=donchian_swing` · 돈키언 매수 `[order_notice]` |
| 09:30 | 퍼널 스냅샷에 돈키언 행(후보 기록 계속) | — |
| 장중 내내 | 돈키언 **보유분 청산**은 가격대로(`[donchian_turtle_stop]` · 트레일링 · 채널 이탈 등) · 09:30~15:20 스윙 REST 폴 | — |
| 21:30 분석 | 상위 WARNING 에 `[buy_paused_config] … donchian_swing paused=1` 1건 | — |

**당일 거래 확인**
```sql
SELECT count(*) FROM trade_history
WHERE strategy = 'donchian_swing' AND trade_type = 'BUY'
  AND timestamp >= '2026-09-28 00:00+09' AND timestamp < '2026-09-29 00:00+09';
-- 기대: 0. 돈키언 SELL 행은 가격에 따라 있을 수 있다(정상)
SELECT count(*) FROM llm_buy_evaluations WHERE trade_date = '2026-09-28'
  AND order_no IN (SELECT order_no FROM trade_history WHERE strategy='donchian_swing'
                   AND timestamp >= '2026-09-28 00:00+09');
-- 기대: 0
```

---

## 12. 롤백 · 해제

| 수단 | 반영 | 언제 | 주의 |
|---|---|---|---|
| `PUT /api/strategies/donchian_swing/params {"params":{"buy_paused":false}}` | **즉시**(다음 1분 스윙 폴) | 언제나. 1순위 | 창(09:05~09:30) 중간 해제도 안전 — 돈키언은 기준가·래치가 없다(§4) |
| 계획된 해제 | 같은 PUT | 개조 합침·배포 뒤, **돈키언 보유 0 이 된 첫 장외 창** | 해제 날 `[buy_paused_config] … paused=0` INFO 1줄로 확인(게이트가 닿는 날) |
| `strategy_config` SQL UPDATE | 다음 재시작에서만 | 쓰지 않는다(cycle232 D6) | — |
| 코드 되돌림(full) | 배포 뒤 | 🔴 **멈춤이 필요한 동안 금지** | 코드에서 키가 사라지면 `_load_strategy_config` 의 `if key in strategy.config.params`(`scheduler.py:452`)가 DB 의 `true` 를 버린다 = **조용한 해제**. 되돌려야 하면 그 전에 돈키언 보유·매수 계획부터 다시 정한다 |

🔴 **`enabled=False`·`weight=0` 으로 되돌리거나 대체하지 않는다** — 보유분 손절이 멈춘다(루트 금기).

---

## 13. 현 코드·문서와의 정합성

- **충돌 없음(코드)**: J25(첫 문장) · cycle233 배치 규약(첫 문장 5 / 발사 직전 2) · A-PURE/A-ATOMIC(게이트는 `calc_buy_quantity`↔`pending_buys.add` 구간 밖, 동기) · `tradable_boards` 매수 전용 규약 · 청산 경로 전부 무접촉.
- **충돌(문서) — 사실이 바뀐다**: 루트 `CLAUDE.md:173` 「🔴 **한 전략을 「보유한 채로」 멈추는 수단은 없다**」·「보유한 채로 신규 유입만 줄이려면 `position_ratio`·`max_positions` 를 쓴다」 → 이 사이클 뒤에는 **`buy_paused` 가 그 수단**이다. docs 단계에서 반드시 고친다(§14). 「`weight=0` 은 더 나쁘다」 경고는 그대로 유지.
- **비대칭(의도)**: 상태 차단(cycle369) 경로는 기준가만 비우고 래치는 안 비운다. 멈춤은 래치까지 비운다. 상태 차단 경로를 이 사이클에서 바꾸지 않는 이유 = 사용자 지시(「상태 차단과 똑같이 재사용」·새 제안 금지) — §16 한 줄 후속.

---

## 14. 문서 동기화 (docs 단계 · `/sync-docs` 목록)

| 문서 | 바꿀 것 |
|---|---|
| 루트 `CLAUDE.md` :173 | 「보유한 채로 멈추는 수단은 없다」 → 「보유한 채로 **신규 매수만** 멈추는 수단 = `buy_paused`(cycle384, PUT 즉시, 청산 무관)」. `weight=0`·`enabled` 경고 유지 |
| `src/engine/CLAUDE.md` | 공통 매수 게이트 순서 = 상태 차단 → `buy_paused` → 계좌 SOFT · 멈춤 때 비우는 상태(§4) · 마커 2종 |
| `src/engine/strategies/CLAUDE.md` | 7전략 공통 키 `buy_paused`(기본 false) · 돈키언 행에 「09-28 부터 운영 DB true — 개조 합침 뒤 해제」 |
| `_workspace/00_leader_trading_rules.md` | 공통 파라미터 표에 `buy_paused` + 운영값(donchian true) |
| `docs/architecture.md` 매수 흐름 | 게이트 순서 한 줄 |
| `src/routes/CLAUDE.md` | PUT params 즉시 반영 예시에 `buy_paused`(롤백 표) |
| `_workspace/00_URGENT_WORKLIST.md` | 09-28 확인 표에 11.2 행 · 진행 순서 2번 갱신 |
| `docs/history/*.history.md` · `docs/HARNESS_CHANGELOG.md` | 경위(사용자 결정 09-27) append |

---

## 15. 반례 · 한계

- **멈춘 전략의 신호 뒤쪽 관측이 함께 멈춘다** — 돈키언: 시장 유닛 shadow 표본 0 · LLM 매수평가 0 · 피라미딩 shadow 새 앵커 0. 「실거래 재채점 표본이 끊긴다」(워크리스트 26행)는 이 사이클이 없애지 못한다 — 멈춤의 본질적 대가다.
- **skip 줄의 뜻이 전략마다 다르다** — momentum·VB 는 「돌파가 실제로 났다」, 첫 문장 전략은 「후보가 평가됐다」(창·갭·거래량 판정 전). 돈키언의 「살 뻔한 종목」은 퍼널 후보 + 그날 시가·고가로 사후 재구성해야 한다.
- **로그가 안 찍혀도 멈춰 있을 수 있다** — 후보 0·돌파 0 인 날은 두 마커 모두 0. 확인 정본은 GET·DB.
- **REST 조회 증가** — 멈춘 돈키언 후보는 09:05~09:30 매 분 조회된다(후보 N × 최대 26).
- **돈키언 예산은 놀고 있다** — 비중을 그대로 두므로 `allocate_funds` 가 돈키언 몫을 계속 배정하고, 보유가 빠질수록 그 현금은 쓰이지 않는다(09-28 21:35 LTV 퇴출·`cash_usage_ratio` 0.95 와 별개).
- **BFB·VCP 늦은 교차**(§4 ③) — 멈춤을 이 두 전략에 쓸 때만 해당. 이번 운영 대상 아님.
- **이미 나간 주문은 취소하지 않는다** — 멈춤은 신호만 막는다. 09:05 전 PUT 이면 해당 없음.
- **설정 로드 전 PUT** 은 DB 를 코드 기본값으로 덮는다(§11.1-3) — 절차가 막는다, 코드가 막지 않는다.

---

## 16. 후속 (한 줄씩 — 이번 범위 밖)

- 상태 차단(cycle369) 경로도 BFB·VCP 래치를 비울지 — 같은 날 차단 해제 시 낡은 래치 매수 가능(발생 조건: 장중 킬스위치 해제).
- 대시보드 전략 카드에 「신규 매수 멈춤」 표시(새 칸은 값이 찍히는지까지 실측).
- 개조 브랜치 합칠 때 돈키언 DB `params` 가 새 기본값을 덮는다(PUT 이 전체 dict 를 저장) — 키별 정리 목록을 개조 명세에 넣을 것. 브랜치는 cycle384 뒤 `main` 에서 떠야 `buy_paused` 키를 잃지 않는다.
