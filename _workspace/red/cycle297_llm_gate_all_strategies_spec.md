# cycle297 — LLM 매수평가 5전략 shadow 확대 + 전략별 컨텍스트 + 주간 회고 조회 (Red 명세)

- 작성 2026-09-17 04:5x KST · base = `5421a90`(cycle295, 01:03 Deploy 성공)
- **매매 행위 변경 0.** shadow 는 `place_order` 성공 **뒤** `create_task` 로 점수만 기록한다(cycle276 규약).
  `check_buy_signal`·`calc_buy_quantity`·`execute_buy` 주문 경로 **byte 동일**, A-ATOMIC 무접촉, 8영역 무접촉,
  `scheduler.py` 무접촉(3,726L).
- 사용자 승인 범위 = "결정 2 진행"(5전략 `DEFAULT_PARAMS` 4키 추가 = 매매 파라미터 신규 키 승인 완료) +
  결정 3(주간 회고는 **목요일 20:30 루틴**에서).
- 상대 갈래(cycle296 — `src/auth/token.py`·`src/engine/quote_token_refresh.py`)와 파일이 겹치지 않는다.
  `tests/unit/ast/test_cycle287_ast_scope.py::_SRC_TREE_DIGEST`·`_SRC_TREE_FILES` 는 **Final 단계**가 한 번에 갱신한다
  (`test_s1b` 붉은 상태는 Final 전까지 예상된 상태).
- 표기: 값이 붙은 것은 실측, `[추론]` 은 추측, `[브리프]` 는 호출자 브리프에서 받은 수치(이 세션에서 재실측하지 않음).

---

## §1 왜

### 1.1 사용자 결정 원문 (2026-09-17)

> "LLM 매수평가를 모든 전략에 걸어볼까 … 일단 최대한 데이터를 쌓고 전략별로 하나씩 적용해나가는걸로. 주간분석에서
> 주간동안 있었던 매도건들에 대해서 자문한 내용에 대해서 회고도 하고, 자문프롬프트도 지속적으로 재귀개선했으면 해.
> 그러다 품질이 확인되는대로 매수에 직접 사용하는걸로." → "결정 2 진행". 주간 회고 = 목요일 20:30 루틴(결정 3).

### 1.2 근거 실측

| # | 사실 | 출처 |
|---|---|---|
| F1 | `llm_gate_mode="shadow"` 4키는 VB·LTV 두 파일에만 있다(`volatility_breakout.py:155-158` · `long_tail_volatility.py:153-156`). 나머지 5전략은 키 부재 = `_read_mode` 가 `off` 로 낙하(`llm_buy_gate.py:113-116`, `:189-`) | 소스 |
| F2 | cycle276 이 평가 훅을 `order_engine.execute_buy` 의 `place_order` 성공 직후로 옮겨 **전략 무관**이 됐다 — 주 경로 `order_engine.py:1156-1162`·지정가 폴백 `:1275-1282` 가 `params_snapshot=dict(strategy.config.params)` 를 넘긴다. 즉 5전략 매수는 지금 훅까지 왔다가 `mode=off` 로 조용히 돌아간다(`[llm_gate_config] mode=off` 카나리아 1행만 남음, `llm_buy_gate.py:632-637`) | 소스 |
| F3 | 09-15 실증(워크리스트 「AI 매수평가(shadow) 3/3 적중」): LTV 프리장 매수 3건 124500(score **36**, would_block True, −1,850) · 000670(**48**, True, −2,700) · 101730(**44**, True, −1,200) → 전건 손실 합 **−5,750**. 셋 다 1주 폴백 랏이라 금액은 작다 | `_workspace/00_URGENT_WORKLIST.md:58-70` |
| F4 | 09-16 표본 0건 — 유일한 매수가 donchian 이라 평가가 붙지 않았다 | `[브리프]` |
| F5 | 🔴 `llm_features._STRATEGY_META`(`:486-503`)에 VB·LTV 2개뿐. `build_messages`(`:566`)는 미등재 전략을 `{"name": sid, "entry_rule": "", "matters": ""}` 로 폴백한다 → **빈 컨텍스트로 채점** | 소스 |
| F6 | 🔴 `llm_buy_gate._read_stop_loss_pct`(`:280-288`)·`_read_exit_rule`(`:291-312`)도 VB·LTV 분기뿐 — 5전략은 `stop_loss_pct=0.0`·`exit_rule=""` 이 실린다. SYSTEM_PROMPT 판단 기준 4("`stop_loss_pct` 절대값이 `atr14_pct` 보다 작으면 낮게 매긴다", `llm_features.py:454-455`)에 **0.0 은 항상 걸린다** | 소스 |
| F7 | 🔴 `_SNAPSHOT_KEYS`(`:534-543`, 20키) 중 `target_won`·`k`·`breakout_excess_bp` 는 `buy_signals` 의 `target_price`/`k` 에서 온다. 그 키를 `buy_signals.append` 에 넣는 전략은 VB(`:1021-1029`, 둘 다)·BFB(`:1116-1124`, `target_price` 만)뿐이고 momentum(`:171`)·donchian(`:1659`)·VCP(`:1181`)·kojiro(`:948`)는 `ticker/price/time` 뿐이다 → 4전략은 시작부터 **null 3개**. SYSTEM_PROMPT "결측 필드가 3개 이상이면 score 는 50 을 넘기지 않는다"(`:446`) 가 구조적으로 발동 → `would_block=True` 상시 = **데이터가 전략이 아니라 잣대 오류를 잰다** | 소스 |
| F8 | `_prompt_version()`(`llm_buy_gate.py:541-567`) 해시 blob = `SYSTEM_PROMPT + _USER_PREAMBLE + "|".join(_SNAPSHOT_KEYS)`. `_STRATEGY_META` 는 **해시에 없다** → 전략별 컨텍스트를 고쳐도 `prompt_version` 이 안 바뀌어 "프롬프트 변경 전후 행 섞기 금지"(자문 §7-1) 가 전략 컨텍스트 축에서 뚫린다. `input_payload` 도 `build_messages` 의 3인자(`payload/tech/bars30`)라 렌더된 META 본문을 담지 않는다 | 소스 |
| F9 | `param_catalog.py:1273-1310` 의 4키 `applies_to=_VBLTV`. `tests/unit/engine/test_cycle278_param_catalog.py::test_applies_to_when_compared_then_matches_default_params_exactly` 가 "`applies_to` ≡ 그 키를 가진 전략 집합" 을 강제한다 → 5전략에 키를 넣으면 **카탈로그를 안 고치면 붉다** | 소스·테스트 |
| F10 | 배관은 있다 — `llm_buy_evaluations`(migration 043, `prompt_version`·`feature_version`·`input_payload`·`raw_response`) · `get_trade_pairs` 의 `buy_order_nos`(list)·`pair_key`(`trade_history.py:645-656`, 한 페어 매수 2건 이상 실측 9건) · `list_by_order_nos` 가 `(trade_date, order_no)` 쌍 전부 반환(`llm_buy_evaluations.py:226-`) | 소스 |
| F11 | 목요일 20:30 루틴 = 주간 파라미터 자문 `trig_01H1TtfhP52CXKuyxwG2KnBW`(cron `30 11 * * 4`, 리포터 자격 = GET/HEAD 경로 무관 통과, `api_auth.py:88·236`) | 메모리 `reference_claude_routines.md` · 소스 |

**결론** — ② 키 추가만으로는 5전략 표본이 쌓이되 **쓸 수 없는 표본**이다(F5·F6·F7). 컨텍스트(①)와 결측 처리(§3.2)·손절/청산 규약 배선(§3.3)이
선결이고, 그것들을 고치면 `prompt_version` 축(F8)도 전략별로 갈라야 회고가 성립한다.

---

## §2 무엇을 바꾸나 (파일별)

| # | 파일 | 변경 | 예상 행수 | 8영역 |
|---|---|---|---|---|
| A | `src/engine/llm_features.py` | `_STRATEGY_META` 5전략 추가(§3.1) · `_SNAPSHOT_NA_KEYS`(전략별 **해당 없음** 키, §3.2) · `snapshot_keys_for(sid)` 공개 함수 · `build_messages` 의 `strategy_block` 에 `not_applicable` 문구(5전략만) | +70 ~ +90 | 밖 |
| B | `src/engine/llm_buy_gate.py` | `_read_stop_loss_pct`·`_read_exit_rule` 5전략 분기(§3.3) · `_resolve_stop_loss_pct(strategy_id, params, tech)` 를 `_evaluate` 의 `compute_technicals` **뒤**에 1곳(ATR 손절 전략) · `_prompt_version(strategy_id)` 전략별 해시 + dict 캐시(§3.4) · `_persist_evaluation` 호출부 1줄 | +60 ~ +80 | 밖 |
| C | `src/engine/strategies/{momentum,donchian_swing,bull_flag_breakout,vcp_breakout,kojiro}.py` | `DEFAULT_PARAMS` 말미(`after_market_exit_division` 다음)에 VB 와 **같은 4키·같은 값** + VB `:147-154` 주석 블록 복사(사이클 번호만 297). **그 외 diff 0** | 각 +12 | 전략 파일(사용자 승인 완료) |
| D | `src/engine/param_catalog.py` | 4키 `applies_to=_VBLTV` → `_ALL7`(`:415`) · `help` 문구에서 "VB·LTV" 한정 표현 제거 | 4×1 + 문구 | 밖 |
| E | `frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts` | 실응답 재생성(`test_fixture_matches_live_schema_response` 가 강제) | 재생성 | — |
| F | `src/db/llm_buy_evaluations.py` | `list_by_order_nos` 재사용. 신규 없음(청크 500 단위 호출은 라우트/leaf 가 한다) | 0 ~ +10 | 밖 |
| G | **신규** `src/engine/llm_retrospective.py` | 순수 함수 leaf(`src.*` import 0, I/O 0): `join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date)` · `aggregate(rows, *, cost_pct)` (§3.5) | +150 ~ +200 | 밖 |
| H | `src/routes/llm_evaluations.py` | `GET /api/llm-evaluations/retrospective?days=7&strategy=&cost_pct=0.25` **읽기 전용** — `get_trade_pairs()` + `list_by_order_nos()` → leaf 로 조인·집계. ⚠️ **`/{order_no}` 보다 앞에 등록**(안 그러면 `retrospective` 가 주문번호로 해석돼 404) | +60 ~ +80 | 밖 |
| I | 테스트 신규 5파일 + 기존 가드 재핀/반전(§5) | | | |
| — | **무접촉** | `order_engine.py`·`risk.py`·`scanner.py`·`session.py`·`strategy_registry.py`·`api/order.py`·`realtime/**`·`auth/**`·`scheduler.py`(3,726L)·`strategy_base.py`·VB·LTV 2파일·`recommendation_engine.py`·마이그레이션(신규 없음)·`main.py`(라우터 이미 등록 `:351`) | diff 0 | |

행수 합계 [추론] 프로덕션 +420 ~ +520. `SYSTEM_PROMPT`(`llm_features.py:432-476`)·`_USER_PREAMBLE`·`_SNAPSHOT_KEYS` 튜플은 **한 글자도 바꾸지 않는다** — VB·LTV 의 user payload 를 byte 동일로 유지하기 위해서다(§3.4 의 버전 단절을 "형식 변경" 하나로 한정).

---

## §3 설계

### 3.1 ① 전략별 컨텍스트 — `_STRATEGY_META` 5건

원칙 = `entry_rule` 은 "왜 지금 사는가" 한 문장, `matters` 는 "무엇으로 좋은/나쁜 진입을 가르나". 멀티데이 3전략은 보유 기간·손절 규약(ATR)을 쓰고
"당일 청산" 전제를 두지 않는다. `exit_rule` 은 여기 쓰지 않는다(호출자가 라이브 params 로 만든다 — `test_f3_10`). **문서에 있는 규칙만** —
출처를 각 항목 끝에 적는다. 문구는 Green 이 다듬되 **수치·조건은 아래 출처와 일치**해야 한다(§5 G1-4 가 수치 토큰을 대조).

| 전략 | `name` | `entry_rule` (요지) | `matters` (요지) | 출처 |
|---|---|---|---|---|
| `momentum` | 상한가 모멘텀 | 전일종가 대비 **+29%** 상향 돌파 순간 진입(이미 **+30%** 상한가 잠긴 종목 제외). KRX 시가단일가·정규장, **15:20** 이후 매수 없음 | 상한가 잠금을 노린다 — 못 잠그면 **−7.5%** 손절 또는 익일 시가 청산(갭 **+10%** 이상이면 트레일링 **−2%**, 아니면 즉시 매도). 이익은 사실상 익일 시가 갭 하나에 달렸고, 장 후반 돌파는 잠글 시간이 없다(15:20 이후 +29% 는 잠금 실패 마감 표본) | `momentum.py:1-7`·`:21-28`·`:59-64` |
| `donchian_swing` | 20일 신고가 스윙 돌파(Donchian) | 전일 종가가 **20일** 최고가 돌파 + **60일** EMA 우상향·종가>EMA60 + 거래대금 20일 평균 **1.5배** 이상 종목을 **다음 영업일 09:05~09:30** 시장가 진입. 시가 갭 **+3%** 이상 스킵, 기준가 대비 **+4%** 초과 추격 금지 | 평균 **5~15영업일** 보유. 청산 = ATR(14)×**2** 샹들리에 트레일링 + 하드손절(터틀 = 진입ATR×2 + **−9%** 백스톱 / 비율 모드 = **−7%**) + **5영업일** 돌파 실패 청산 + **10일** 저가 채널 이탈. 당일 남은 시간은 점수에 거의 무관 — 신고가 위 안착·거래량 확인·확장폭·손절폭 대비 ATR 이 핵심 | `donchian_swing.py:1-16`·`:79-138`, `strategies/CLAUDE.md:156·170` |
| `bull_flag_breakout` | 눌림목 돌파(Bull Flag) | 직전 **3~10영업일 +15%** 이상 폴(음봉 ≤45%) 뒤 **2~10영업일** 플래그(조정 ≤ 폴 폭 **50%**, 거래량 < 폴 평균 **60%**) 상단 `flag_high` 를 **09:05~13:00** 돌파 + 당일 거래량 ≥ 플래그 평균 **2배**. 돌파선 대비 **+5%** 초과 추격 금지 | 목표 = 측정된 이동(`flag_high` + 폴 높이) 도달. 청산 = **−5%** 손절 / `flag_low` 이탈 / ATR×2 트레일링 / **5영업일** 시간 청산. 5영업일 안에 2차 상승이 나와야 하므로 돌파 거래량과 플래그의 질(얕고 조용한 조정)이 핵심, 폴이 소진된 늦은 돌파를 낮게 본다 | `bull_flag_breakout.py:1-27`·`:98-168`, `strategies/CLAUDE.md:157` |
| `vcp_breakout` | 변동성 수축 돌파(VCP, 미네르비니) | **50/60/120** EMA 정배열 + 장기 EMA **1개월** 우상향 종목이 **5~15주** 베이스(깊이 ≤**30%**) 안에서 **2~4회** 점진 수축 조정(마지막 ≤**12%**)과 거래량 수축(마지막 5일 < 직전 20일 평균 **70%**)을 거친 뒤 **09:05~14:30** `base_high` 돌파 + 거래량 ≥ 20일 평균 **1.5배**. 돌파선 대비 **+7.5%** 초과 추격 금지 | 멀티데이·시간 청산 없음. 청산 = **−7%** 손절 / `base_low` 이탈 / ATR×2 트레일링 / **50일** EMA 이탈. 진입 시점 ATR 이 수축 구간이라 작다 — 손절폭 대비 ATR 비교가 "정상 잡음에 손절이 맞는가" 의 핵심. 수축의 질(가격·거래량 모두 마름)과 돌파 거래량으로 가른다 | `vcp_breakout.py:1-27`·`:103-193`, `strategies/CLAUDE.md:158` |
| `kojiro` | 고지로 대순환 스윙(EMA 5/20/40) | EMA **5>20>40** 스테이지1 이 최근 **5영업일** 안에 **6→1** 로 갓 전환 + 세 EMA 우상향 + 전일 종가 > EMA5 + ATR/종가 **1.0~6.0%** 종목을 **다음 영업일 09:05~09:30** 시장가 진입. 갭업 ≥**5%**·갭다운 ≤**−4%**·장중 붕괴(현재가<시가) 스킵 | 추세 끝까지 보유(시간·15:20 청산 없음). 청산 우선순위 = 고정 **−8%** 백스톱 → 진입가−**2**×ATR(20) 하드손절(tighten-only) → 스테이지3 진입 → 고점−**2.5**×ATR 샹들리에. 갓 정렬된 추세의 신선도와 ATR 밴드 안의 질서정연함으로 가른다 — 당일 남은 시간은 무관 | `kojiro.py:1-20`·`:140-224`, `strategies/CLAUDE.md:159` |

기각한 선택지 — (a) SYSTEM_PROMPT 를 전략별로 쪼개기: 자문 §4.1 "전략 무관 공통·재작문 금지" + `prompt_version` 전 전략 동시 단절 + 판단 기준 6항이 이미 조건부("당일 청산 전략에서")라 불필요. (b) 5전략에 VB 문구를 복사: F5 의 "잣대 오류" 그대로.

### 3.2 ② 결측과 「해당 없음」의 분리 — `_SNAPSHOT_NA_KEYS`

F7 의 구조적 ≤50 을 없애되 **VB·LTV 페이로드는 byte 동일**로 둔다.

🔴 **아래 표는 §10-B 가 뒤집었다** — donchian·VCP 는 돌파선(`donchian_high`·`base_high`)을
`buy_signals` 에 이미 싣고 있었고, BFB 의 `target_price` 는 **돌파선이 아니라 측정 이동
목표가**였다. 착지 코드는 `("k",)` 3건 + 전 3키 2건이다. 이 블록은 Red 시점 기록으로 읽는다.

```python
# llm_features.py — 전략에 존재하지 않는 개념은 null 로 싣지 않고 키 자체를 뺀다(결측 ≠ 해당 없음).
# ⚠️ Red 시점 안(§10-B 로 폐기). 착지본은 momentum·kojiro 만 3키, 나머지 셋은 ("k",).
_SNAPSHOT_NA_KEYS = {
    "momentum":            ("target_won", "k", "breakout_excess_bp"),
    "donchian_swing":      ("target_won", "k", "breakout_excess_bp"),
    "vcp_breakout":        ("target_won", "k", "breakout_excess_bp"),
    "kojiro":              ("target_won", "k", "breakout_excess_bp"),
    "bull_flag_breakout":  ("k",),                     # target_price 는 buy_signals 에 있다(:1121)
}
def snapshot_keys_for(sid) -> tuple[str, ...]:
    na = set(_SNAPSHOT_NA_KEYS.get(sid, ()))
    return tuple(k for k in _SNAPSHOT_KEYS if k not in na)   # 순서 = _SNAPSHOT_KEYS 그대로
```

- `build_messages` 는 `snapshot = {k: payload.get(k) for k in snapshot_keys_for(sid)}`. VB·LTV 는 `_SNAPSHOT_NA_KEYS` 에 없으므로 결과가 종전과 **동일**(`test_f4_3` 그대로 초록).
- 5전략의 `strategy_block` 에만 `"not_applicable": "이 전략에는 목표가(k·target_won·breakout_excess_bp) 개념이 없다 — 결측이 아니라 해당 없음이다. 판단 기준 1(돌파의 질)은 채널 위치·거래량·확장폭으로 대신 본다."`(BFB 는 `k` 만). VB·LTV 블록에는 이 키를 **넣지 않는다**(byte 동일 유지).
- 기각 — (a) null 그대로 두고 SYSTEM_PROMPT 의 "3개 이상" 문구 수정: 프롬프트 재작문 금지 + 전 전략 버전 단절. (b) 전략 파일의 `buy_signals` 에 `target_price`(base_high/돌파선) 추가: 진입 정보로는 옳지만 `check_buy_signal` 세그먼트 변경 = cycle290 28핀 위반 + 이 사이클 승인 범위("4키 외 diff 0") 밖 → **후속 카드**(§8-4).

### 3.3 ③ 손절·청산 규약 배선 — `llm_buy_gate.py`

`_read_stop_loss_pct`·`_read_exit_rule` 에 5분기 추가. 값은 **라이브 params** 에서 읽는다(`params_snapshot` = `dict(strategy.config.params)`, DB 오버라이드 반영).

| 전략 | `stop_loss_pct`(observe 시점) | ATR 손절이면 `_evaluate` 에서 재해석(`tech["atr14_pct"]` 가용 시) | `exit_rule` 문구 소스 |
|---|---|---|---|
| momentum | `stop_loss_rate`(−7.5) | — | `stop_loss_rate`·`gap_up_threshold`·`trailing_stop_rate` + "익일 청산" |
| donchian_swing | `stop_loss_rate`(−7.0) | `sizing_mode=="turtle"` 이면 `max(-(stop_atr×atr14_pct), turtle_backstop_pct)`(둘 중 **타이트한** 쪽) | `atr_trail_mult`·`stop_atr`·`turtle_backstop_pct`·`breakout_fail_n_days`·`channel_exit_period` |
| bull_flag_breakout | `stop_loss_rate`(−5.0) | turtle 이면 `clamp(-(stop_atr×atr14_pct), turtle_backstop_pct, turtle_min_stop_pct)` | `stop_loss_rate`·`atr_trail_mult`·`max_hold_days` + "flag_low 이탈 / 측정 이동 도달" |
| vcp_breakout | `stop_loss_rate`(−7.0) | 위와 동일 3단 밴드 | `stop_loss_rate`·`atr_trail_mult` + "base_low 이탈 / 50일 EMA 이탈" |
| kojiro | `hard_stop_pct`(−8.0) | 항상 `max(hard_stop_pct, -(stop_atr×atr14_pct))`(타이트한 쪽) | `hard_stop_pct`·`stop_atr`·`trail_atr` + "스테이지3 진입" |

- 근거 = `strategies/CLAUDE.md:161-173` 매트릭스(donchian 운영 DB `turtle` 라이브 · VCP/BFB 다크런치 · kojiro `_stop_floor` 단일 메커니즘). 재해석은 `payload["stop_loss_pct"]` 를 **task 전용 복사본** 안에서 덮는 것이라 read-only 계약과 무관(`vol_ratio_*` 와 같은 자리, `llm_buy_gate.py:1129-1141` 직후).
- ⚠️ 근사임을 `exit_rule` 문구에 밝힌다 — tech 의 ATR 은 **14일 Wilder**이고 kojiro 는 ATR(20), donchian 은 진입 시점 `_entry_atr` 스탬프라 정확히 같지 않다. 프롬프트가 읽는 것은 "손절폭이 잡음보다 넓은가" 이므로 근사로 충분하다 [추론]. `atr14_pct` 결측이면 고정 % 값 그대로(0.0 위장 금지).

### 3.4 ④ `prompt_version` 을 전략별로

```python
def _prompt_version(strategy_id) -> str:   # 캐시 dict[str, str]
    blob = SYSTEM_PROMPT + _USER_PREAMBLE + "|".join(snapshot_keys_for(sid)) \
         + json.dumps(_STRATEGY_META.get(sid, {}), sort_keys=True, ensure_ascii=False)
    return sha256(blob)[:12]
```

- 이제 "어떤 전략의 컨텍스트를 고쳤는가" 가 그 전략 행의 버전에만 반영된다 — 사용자가 원한 **재귀 개선**의 단위가 전략이므로 버전 축도 전략이어야 한다.
- 🔴 **1회성 단절**: VB·LTV 의 값도 바뀐다(blob 에 META 가 새로 들어간다). 09-11~09-16 VB·LTV 행(현행 `prompt_version` = 배포 전 값 X)과 배포 후 행(Y)은 **user payload 가 byte 동일**함에도 버전이 갈린다. 회고 집계가 `prompt_version` 별로 나뉘므로 Green 은 배포 직후 X·Y 두 값을 `HARNESS_CHANGELOG`(메인 세션) 에 "X ≡ Y (VB·LTV, 형식 변경)" 로 남기고, 회고 라우트 응답의 `prompt_version_aliases` 에 이 등가를 **상수로** 넣어 목요일 루틴이 합산할 수 있게 한다. 기각 — META 를 해시 밖에 두기(F8 결함 방치) · VB·LTV 만 옛 식 유지(전략마다 식이 다르면 다음 사람이 두 번 속는다).
- `feature_version`(`compute_technicals` 키 집합)은 무변경 — 이 사이클은 지표 키를 안 늘린다(`vol_ratio_*`·`stop_loss_pct` 는 payload 축).

### 3.5 ⑤ 주간 회고 조회 — 조인·집계·라우트

**조인 (순수 함수, leaf `llm_retrospective.join_pairs_with_evaluations`)**

1. 입력 = `get_trade_pairs()` 결과 중 `status=="closed"` ∧ `sell_date ∈ [today−(days−1), today]`(KST 날짜 문자열, `_to_kst` 산출 그대로) — `days` 는 1~90.
   🔴 **`days` 일 포함 창**이다(§10-D). 종전 표기 `[today−days, today]` 는 8일 창이라 매주 목요일 루틴이 하루를 두 번 집계한다. 가드 = `test_g4_10`.
2. 후보 주문번호 = 그 페어들의 `buy_order_nos` 합집합 → `list_by_order_nos(chunk)` 500개 단위(라우트 200 상한은 UI 배치용이고 DB 함수엔 상한이 없다).
3. 매칭 축 = **`(order_no, trade_date)`**. KIS ODNO 는 하루 단위로만 유일하므로(`llm_buy_evaluations.py:6-8`) 주문번호 단독 매칭 금지 — 같은 `order_no` 의 평가 행이 여러 날짜면 `buy_date ≤ trade_date ≤ sell_date` 인 행만, 그중 `trade_date == buy_date` 우선.
4. 출력 = 페어 1행: `strategy·ticker·ticker_name·pair_key·buy_date·sell_date·buy_price·sell_price·buy_qty·profit_loss·profit_rate·buy_order_nos` + `evaluations: [{order_no, trade_date, score, min_score, would_block, result, reason, prompt_version, feature_version, model}]` + `primary`(= 첫 매수 주문의 평가 또는 `null`) + `outcome`(§집계의 손실 정의 적용).
   - 한 페어에 매수 2건 이상(실측 9건)은 `evaluations` 가 2개 이상이고 집계는 **`primary` 기준**(첫 매수가 사이클을 연 판단), 나머지는 노출만.
   - 평가 행이 없는 페어(배포 전 매수·`mode=off` 시절·cap 초과)는 `primary=null` 로 **남긴다**(빼면 분모가 사라져 커버리지를 못 잰다).
5. `account_no` 는 어디에도 싣지 않는다(응답 화이트리스트 = 위 키만). 기존 `_detail` 의 화이트리스트 관례와 같은 이유(리포터 키가 GET 을 경로 무관 통과).

**집계 (`llm_retrospective.aggregate`)** — 그룹 = `overall` · `by_strategy[sid]` · `by_prompt_version[(sid, pv)]`, 각각:

| 필드 | 정의 |
|---|---|
| `n_pairs` / `n_scored` / `n_unscored` | 페어 수 / `primary.score` 비-null / null |
| `n_block` · `n_block_loss` · `block_hit_rate` | `would_block=True` 수 · 그중 손실 · 비율("막았어야 했다" 의 적중) |
| `n_pass` · `n_pass_loss` · `pass_loss_rate` | `would_block=False` 수 · 그중 손실 · 비율(통과시킨 것의 손실 = false-pass) |
| `pnl_block_sum` · `pnl_pass_sum` | 두 코호트 실현손익 합 — `−pnl_block_sum` 이 "enforce 였다면 피했을 금액" 의 1차 근사(반사실 대체매수는 무시, 043 주석) |
| `avg_score_win` · `avg_score_loss` | 결과별 평균 점수(두 분포가 갈리면 게이트 유효) |
| `buckets` | 10점 버킷 `{lo, hi, n, loss_rate}` 10칸 — 자문 §7.5-B 보정 곡선 원자료(단조성 검정은 루틴 몫) |
| `coverage_pass_rate` | `n_pass / n_scored` — 자문 §7.5-C 커버리지 게이트(20~70%) |

- **손실 정의** = `profit_rate < cost_pct`(기본 `0.25`, 쿼리로 변경 가능) — `get_trade_pairs` 의 `profit_loss` 는 수수료·세금 **전** 값이고(`trade_history.py:725`) SYSTEM_PROMPT 의 점수 정의는 "수수료·세금 차감 후 플러스 확률"(`llm_features.py:438`)이라 0 을 기준으로 삼으면 정의가 어긋난다. 0.25 는 [추론](§8-2).
- 순수 함수라 실 PG 없이 표만 넣어 단위 테스트한다(§5 G3).

**라우트** `GET /api/llm-evaluations/retrospective` — 쿼리 `days`(1~90, 기본 7)·`strategy`(선택)·`cost_pct`(0~5, 기본 0.25). 범위 위반 **422**, DB 예외 **500**(+`[llm_eval_route_error]`), 페어 0건은 **200 + 빈 집계**(404 아님 — "이번 주 청산 없음" 은 오류가 아니다). `Decimal→float` 사영은 기존 `_num` 재사용. 응답에 `window: {since, until, days}`·`cost_pct`·`prompt_version_aliases`·`generated_at`(KST ISO) 포함. **쓰기 0**.

기각 — (a) SQL 뷰: 페어링이 Python(`get_trade_pairs`)이라 SQL 로 다시 쓰면 정의가 둘이 된다(자문 §7.3 "판정은 한 정의로만"). (b) `system_logs` 정규식 파싱(자문 §7.3 원안): 043 이 그걸 대체하려고 만든 테이블이다. (c) 라우트 안에 조인·집계 헬퍼: 테스트는 되지만 신규 leaf 가 cycle290 `_ENGINE_PY_FILES`·cycle287 파일 수 핀을 건드린다는 이유만으로 라우트에 분석 로직을 두는 건 구조를 되판다 — 핀 갱신은 Final 이 296 의 신규 leaf 와 함께 한다(§5 F).

### 3.6 ⑥ enforce 전환 정량 기준 — **틀만 고정**(숫자는 후속 `domain-consult`)

판정 단위 = **(전략, prompt_version)**. 모두 충족해야 그 전략만 `enforce` 후보(전략 하나씩 — 사용자 결정 "전략별로 하나씩").

| 축 | 지표(회고 응답 필드) | 브리프 초안 | 자문 cycle274 §7.7 |
|---|---|---|---|
| 표본 | `n_scored` | ≥ 30 | 실체결 왕복 ≥ 40(구간당 ≥ 12) |
| 적중 | `block_hit_rate` | ≥ 70% | TE 분리 부트스트랩 95% CI 하한 > 0 |
| 오차단 | `n_block − n_block_loss` 비율 | ≤ 20% | — |
| 단조 | `buckets` Spearman ρ | — | ρ > 0, p < 0.10(단조 아니면 임계 자체 무의미) |
| 커버리지 | `coverage_pass_rate` | — | 20~70% |
| 안정 | 같은 `prompt_version` 지속 | 프롬프트 변경 후 **2주** | — |
| 배관 | `[llm_buy_score_failed]` 비율 · p95 `verdict_lag_ms` | — | < 10% · ≤ 8s |
| 비용 | 월 `cost_usd` 합 | — | 순자산 0.5% 미만 |

이 사이클은 표의 **행(축)** 만 고정하고 열(수치)은 자문이 정한다. enforce 자체·fail-open/closed 규약(자문 §6.1 3안)은 별도 승인.

---

## §4 잃는 것 · 위험

| # | 위험 | 크기 | 완화 |
|---|---|---|---|
| R1 | **비용** — 7전략 × `daily_call_cap=20` = 140/일 이론 상한. 실제 매수 3~5건/일 `[브리프]`, 건당 ≈$0.006 `[브리프]` → 월 ≈$0.4~0.7 [추론]. donchian·kojiro 는 `max_positions` 5 라 09:05~09:30 에 최대 10건 버스트 | 낮음 | cap 은 전략별 그대로(20). 세마포어 2·타임아웃 20s 는 무변경 — 버스트는 큐잉될 뿐 주문 경로와 무관(평가는 `create_task` 뒤) |
| R2 | **`no_bars` 실패 증가** — `_evaluate` 는 `stock_master_daily` 에서 일봉을 읽는다. momentum(전 상장 상한가 후보)·소형주는 일봉 적재 유니버스 밖일 수 있다 → `[llm_buy_score_failed] reason=no_bars` 행이 늘고 그 주문은 점수 없이 1행(`score=NULL`) | 중 | 정상 사유로 분류돼 있고 DB 행이 남아 커버리지 분모에 잡힌다. D+1 에서 전략별 `no_bars` 비율을 읽고 20% 를 넘는 전략은 §8-6 후속 |
| R3 | **VB·LTV `prompt_version` 1회 단절**(§3.4) | 낮음 | 등가 상수 `prompt_version_aliases` + changelog 기록. 표본 [추론] ≤ 20행 |
| R4 | 5전략 첫 표본이 컨텍스트 문구 품질에 좌우된다 — 문구가 틀리면 그 전략의 첫 `prompt_version` 표본이 통째로 오염 | 중 | §3.1 은 문서 인용만. 문구 수정은 그 전략 버전만 새로 갈리므로(§3.4) 오염이 격리된다 — 이것이 전략별 버전의 존재 이유 |
| R5 | ATR 손절 근사(§3.3)가 실제 손절선과 다르다(ATR14 vs ATR20·entry_atr) | 낮음 | 근사임을 `exit_rule` 에 명시. 모델이 읽는 건 "손절폭 vs 잡음" 이지 정확한 가격이 아니다 |
| R6 | `applies_to` 확대로 **Settings 화면**에 5전략 각각 LLM 4키 편집란이 생긴다(`GET /api/strategies/params-schema`) — 운영자가 실수로 `daily_call_cap` 을 200 으로 올릴 수 있다 | 낮음 | 카탈로그 `max=200` 그대로(cycle278 값). `PARAM_RANGES` 미편입이라 AI 자문은 못 건드린다 |
| R7 | 회고 라우트가 `get_trade_pairs()` **전량**(strategy/ticker 필터 없이)을 계산한다 — 운영 DB `trade_history` 규모에서 응답 시간 | 낮음 [추론] | 기존 `/api/history/pnl` 이 같은 함수를 매 호출 실행한다. 루틴 1회/주 + 사람 수회. 문제 시 `strategy` 필터로 좁힌다 |
| R8 | 라우트 등록 순서 — `/{order_no}` 뒤에 두면 `retrospective` 가 주문번호로 잡혀 404 | 확실 | §2-H, 가드 G4-1 |
| R9 | Final 단계 충돌 — 신규 engine leaf 2개(297 `llm_retrospective.py` + 296 `quote_token_refresh.py`)가 cycle290 `_ENGINE_PY_FILES`·cycle287 `_SRC_TREE_FILES=152`·`_SRC_TREE_DIGEST` 를 같이 건드린다 | 중 | 297 은 cycle290 목록에 **자기 파일만** 추가하고 287 의 세 상수는 손대지 않는다(Final). 296 도 같은 규칙이면 병합 충돌은 290 목록 한 곳뿐 |
| R10 | 목요일 루틴이 새 엔드포인트를 읽으려면 **루틴 프롬프트 변경**이 필요하다 — 외부 조치 = 승인 대상 | — | 결정 카드(§8-5). 오늘(09-17 목) 20:30 실행에는 못 들어가고 첫 회고는 09-24 |

**잃지 않는 것** — 주문 지연 0(평가는 접수 뒤), VB·LTV 프롬프트 byte 동일, 매수/청산/수량 산식 diff 0(cycle290 세그먼트 28핀이 초록인 채로 증명), 마이그레이션 0.

---

## §5 회귀 가드 + 뮤테이션 대조표

### 5.1 신규 테스트

**G1 `tests/unit/engine/test_cycle297_llm_strategy_context.py`**
- G1-1 `_STRATEGY_META` 키 집합 == `param_catalog.STRATEGY_IDS`(7, 순서 무관) — 양성 대조군: 하나라도 빠지면 붉다.
- G1-2 7건 모두 `name`·`entry_rule`·`matters` 가 공백 제거 후 길이 ≥ 20, `exit_rule` 키 **없음**.
- G1-3 폴백 도달 불가 — `build_messages` 의 `_STRATEGY_META.get(sid, {...})` 폴백 리터럴은 남겨도 되나, `STRATEGY_IDS` 전수에 대해 `strategy_block["entry_rule"] != ""`.
- G1-4 수치 토큰 대조 — 전략별로 §3.1 의 굵은 수치 중 최소 3개가 `entry_rule+matters` 문자열에 포함(예: donchian `"20일"`·`"60일"`·`"−9%"`).
- G1-5 `snapshot_keys_for("volatility_breakout") == _SNAPSHOT_KEYS` 이고 LTV 도 동일; donchian 은 `{"target_won","k","breakout_excess_bp"}` 가 **키 자체로 없다**(`"k" not in snapshot`, `snapshot.get("k") is None` 만으로는 통과 불가).
- G1-6 VB·LTV user payload **byte 동일** — cycle276 픽스처(`test_cycle274_llm_features.py::_payload`)로 만든 `messages[1]["content"]` 의 sha 를 이 사이클 착수 시점 값으로 핀(테스트 파일 상수). 5전략 확대가 두 전략 프롬프트를 한 글자도 안 바꿨다는 기계 증거.
- G1-7 5전략 `strategy_block["not_applicable"]` 존재, VB·LTV 에는 그 키 **부재**.
- G1-8 `_read_exit_rule(sid, DEFAULT_PARAMS)` 7전략 전부 비공백, `_read_stop_loss_pct` 7전략 전부 `< 0`(0.0 금지). kojiro 는 `hard_stop_pct` 값.
- G1-9 `_resolve_stop_loss_pct("donchian_swing", {"sizing_mode":"turtle","stop_atr":2.0,"turtle_backstop_pct":-9.0,...}, {"atr14_pct": 3.0}) == -6.0`; `atr14_pct=6.0` → `-9.0`; `atr14_pct=None` → 고정값 `-7.0`; `sizing_mode="position_ratio"` → `-7.0`. BFB 밴드(`-4.0 ≤ x ≤ -7.0`) · kojiro `max(-8.0, -2×atr)` 각 1케이스.
- G1-10 `_prompt_version("donchian_swing") != _prompt_version("kojiro")`, 같은 sid 두 번 호출 동일(캐시), META 문구 1자 변경(monkeypatch) 시 그 sid 만 변한다.

**G2 `tests/unit/ast/test_cycle297_ast_scope.py`**
- G2-1 4키(`llm_gate_mode/min_score/daily_call_cap/timeout_secs`)를 `DEFAULT_PARAMS` 에 가진 전략 파일 = **정확히 7파일**(cycle274 `test_c10_3`·cycle276 `test_c6_3a` 의 반전 — 강화 방향).
- G2-2 5전략 각 `DEFAULT_PARAMS` 키 목록 == (cycle290 기준 키 목록) + 4키, 값은 VB 와 동일(`"shadow"`,70,20,20).
- G2-3 5전략 파일의 `check_buy_signal/check_exit_signal/calc_buy_quantity/prepare` 세그먼트 sha == cycle290 `_SEGMENT_SHA`(그 테스트를 import 해 재사용, 리터럴 복제 금지).
- G2-4 4키 ∉ `PARAM_RANGES`·`INT_PARAMS`(런타임) + `recommendation_engine.py` 소스 리터럴 0건(기존 두 가드와 동형, 7전략 문맥).
- G2-5 `param_catalog` 4키 `applies_to == STRATEGY_IDS`.
- G2-6 `_SNAPSHOT_KEYS` 튜플 소스 세그먼트 sha 불변 · `SYSTEM_PROMPT`·`_USER_PREAMBLE` 세그먼트 sha 불변(착수 시점 값 핀).
- G2-7 `_prompt_version` 함수 시그니처에 인자 1개 + `_persist_evaluation` 호출부가 `strategy_id` 를 넘긴다(AST).
- G2-8 신규 leaf `llm_retrospective.py`: `src.*` import 0 · `await`/`pg`/`httpx` 0 · 최상단 부작용 0.
- G2-9 8영역 6파일 + `scheduler.py`(정확 3,726L) + `strategy_base.py` + VB·LTV 2파일 + `order_engine.py` **byte 동일**(착수 시점 sha 핀, `_BASE_SHA` 이름 관례).
- G2-10 `src/routes/llm_evaluations.py` 에서 `retrospective` 라우트 데코레이터의 lineno < `/{order_no}` 데코레이터 lineno.

**G3 `tests/unit/engine/test_cycle297_llm_retrospective.py`** (순수 함수 표 테스트)
- 한 페어 매수 2건 → `evaluations` 2개, `primary` = 첫 `buy_order_nos[0]` · 같은 `order_no` 가 두 날짜 → `buy_date` 와 같은 날짜 행 채택 · 평가 없는 페어 → `primary=null` 이면서 `n_pairs` 에 포함 · `profit_rate=+0.1` 는 `cost_pct=0.25` 에서 **손실**, `cost_pct=0` 에서 이익 · 버킷 10칸 합 == `n_scored` · `open` 페어 제외 · `sell_date` 창 밖 제외 · 빈 입력 → 전 필드 0/빈 리스트(예외 없음).

**G4 `tests/unit/routes/test_cycle297_llm_retrospective_route.py`**
- 200 형태(`window/cost_pct/pairs/aggregate/prompt_version_aliases`) · `days=0`/`91`·`cost_pct=-1` → 422 · DB 예외 → 500 + 마커 · 응답 직렬화 문자열에 `account_no` 부재 · `Decimal` 이 `float` 로 · 페어 0건 → 200 빈 집계 · `GET /api/llm-evaluations/retrospective` 가 `/{order_no}` 에 먹히지 않음(실 라우터 매칭).

**G5 `tests/integration/test_cycle297_llm_retrospective_pg.py`** (실 PG, `pg_harness` — docker 가용)
- `trade_history` 매수 2건(다른 `order_no`, 같은 날) + 매도 1건 + `llm_buy_evaluations` 2행 → `get_trade_pairs` 1페어 → 조인 결과 `evaluations` 2개 · 같은 `order_no` 를 다른 날짜에 한 번 더 심어 잘못된 날짜 행이 붙지 않음 · 라우트 왕복(TestClient + 실 풀) 200.

### 5.2 기존 가드 재핀·반전 (Green 이 **코드 변경 뒤** 실측값으로 — 먼저 재산출 금지)

| 대상 | 무엇 | 파일 |
|---|---|---|
| 전략 5파일 내용 sha | 재핀(각 파일 주석에 "cycle297 — DEFAULT_PARAMS 말미 4키") | `test_cycle223_ast_donchian_exit_fix.py:615-622` · `274:593-601` · `276:369-377` · `278_ast_catalog_guards.py:235-` · `282:421-431` · `286:107-115` · `287:140-150` · `291:114-124` · `293:175-185` · `294:244-254` (**10곳**) |
| `DEFAULT_PARAMS` 세그먼트 sha 5건 | 재핀(cycle290 관례대로 "정당한 갱신" 주석) | `test_cycle278_ast_catalog_guards.py::_DEFAULT_PARAMS_SHA` |
| `param_catalog.py` 내용 sha | 재핀 | `291`·`293`·`294` `_BASE_SHA`(**3곳**) |
| 4키 소유 = {VB, LTV} | **반전 → 7파일 전부**(단언 삭제·skip 금지) | `274::test_c10_3` · `276::test_c6_3a` |
| `_ENGINE_PY_FILES` | `llm_retrospective.py` 추가 | `test_cycle290_ast_scope.py:288` |
| 스키마 픽스처 2개 | 재생성 | `frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts` |
| **Final 전용** | `_SRC_TREE_FILES`(152 → +2)·`_SRC_TREE_DIGEST` | `test_cycle287_ast_scope.py:177·223` — 297 은 건드리지 않는다 |

무변경 확인 = cycle264 `_STRATEGY_PINS`(VB·LTV 6핀) · cycle290 `_SEGMENT_SHA` 28핀 · cycle274/276 `order_engine` 훅 계약(C1~C10) 전부 **그대로 초록**이어야 한다 — 하나라도 붉으면 이 사이클 범위 밖 변경.

### 5.3 뮤테이션 대조표 (Green 은 전수 KILLED 을 보고한다)

| # | 뮤테이션 | 죽이는 가드 |
|---|---|---|
| M1 | `_STRATEGY_META` 에서 kojiro 제거 | G1-1, G1-3 |
| M2 | donchian `matters` 를 `""` 로 | G1-2 |
| M3 | donchian `matters` 에 "당일 15:20 청산" 삽입(VB 잣대 오염) | G1-4 (수치 토큰 `"5~15영업일"` 부재) [추론: 토큰 선택에 따라] — 보강: `matters` 에 `"15:20"` 포함 금지 단언(멀티데이 3전략) |
| M4 | `_SNAPSHOT_NA_KEYS["donchian_swing"]` 를 `()` 로 | G1-5 |
| M5 | NA 키를 빼는 대신 `None` 으로 채움 | G1-5 (`not in`) |
| M6 | `build_messages` 가 VB 에도 `not_applicable` 추가 | G1-6, G1-7 |
| M7 | `_read_exit_rule` 의 donchian 분기 삭제 | G1-8 |
| M8 | `_read_stop_loss_pct` 가 kojiro 에 `0.0` | G1-8 |
| M9 | `_resolve_stop_loss_pct` 가 `min`(느슨한 쪽) | G1-9 |
| M10 | `_prompt_version` 이 `strategy_id` 무시 | G1-10, G2-7 |
| M11 | `_prompt_version` blob 에서 META 제외 | G1-10 (문구 변경 불감지) |
| M12 | 5전략 중 momentum 에만 키 누락 | G2-1, G2-2, cycle278 `test_applies_to_*` |
| M13 | `applies_to=_VBLTV` 유지 | G2-5, cycle278 C3 |
| M14 | `llm_gate_daily_call_cap` 을 kojiro 에 `0` | G2-2 |
| M15 | 4키를 `PARAM_RANGES` 에 추가 | G2-4, cycle274 `test_c10_1` |
| M16 | `check_buy_signal` 에 한 줄 추가 | G2-3, cycle290 S2 |
| M17 | 조인을 `order_no` 단독으로 | G3 두 날짜 케이스, G5 |
| M18 | `primary` 를 마지막 매수로 | G3 |
| M19 | 평가 없는 페어를 drop | G3 (`n_pairs`) |
| M20 | 손실 정의 `profit_loss < 0` 고정 | G3 (`cost_pct`) |
| M21 | 응답에 `account_no` 포함 | G4 |
| M22 | 라우트를 `/{order_no}` 뒤에 등록 | G2-10, G4 |
| M23 | `days=91` 허용 | G4 |
| M24 | leaf 가 `src.db.pg` import | G2-8 |
| M25 | `_SNAPSHOT_KEYS` 에 키 추가 | G2-6, G1-6 |

실행 = `tests/unit/ast/` · `tests/unit/engine/` · 나머지 세 덩어리, caplog 는 WARNING 이상 + 마커 prefix, 시각 고정 freezegun, 마지막에 `TZ=UTC` 재실행.

---

## §6 문서 동기화 목록 (메인 세션 `/sync-docs`)

| 문서 | 무엇이 거짓이 되나 / 무엇을 넣나 |
|---|---|
| 루트 `CLAUDE.md` | 하네스 표 1행(cycle297) · 「디렉토리 역할」 `src/engine/` 줄에 `llm_retrospective.py` · P0 요약은 무관 |
| `docs/HARNESS_CHANGELOG.md` | verbatim + **VB·LTV `prompt_version` X→Y 등가 기록**(§3.4) |
| `_workspace/00_URGENT_WORKLIST.md` | 배포·D+1 판독 항목 · enforce 결정 카드에 §3.6 틀 링크 |
| `src/engine/CLAUDE.md` | `llm_buy_gate.py` 절 "VB·LTV 매수 주문 접수 시점" → 7전략 · `_prompt_version(strategy_id)` · `llm_features.py` 절 `_SNAPSHOT_NA_KEYS`/`snapshot_keys_for` · **신규 leaf `llm_retrospective.py` 절**(`/sync-docs` 모듈 누락 자가 점검이 `.py` 단어 경계로 잡는다) |
| `src/engine/strategies/CLAUDE.md` | 배너(`:97-125`) "VB·LTV" 한정 표현 · 「키 부재 의미가 셋으로 갈린다」 절은 유지하되 "5전략은 키 부재" 문장 삭제 · 카탈로그 표 7행 마지막 열에 `cycle297 — LLM shadow` · 3.1 컨텍스트 원문 링크 |
| `src/routes/CLAUDE.md` | `GET /api/llm-evaluations/retrospective` 행(`:46-47` 옆) — 읽기 전용·계좌 미노출·`/{order_no}` 앞 등록 |
| `src/db/CLAUDE.md` | `llm_buy_evaluations.py` 절에 회고 소비처(leaf) 1줄 · `get_trade_pairs` 절에 회고 조인 축 언급 |
| `docs/architecture.md` | `:947` "llm_buy_gate (AI 매수평가 — VB·LTV 만)" · `:967` "나머지 5 전략은 키 부재 = off" — **둘 다 거짓이 된다** · 15.2 도식 라벨 |
| `_workspace/00_leader_trading_rules.md` | `:651` 절 제목·본문 "VB·LTV" → 7전략, D+1 서명(`:671`) "5전략은 mode=off 행" 삭제 |
| `frontend/CLAUDE.md` | 스키마 픽스처 재생성 사실(파라미터 편집 화면에 5전략 LLM 4키 노출) |
| `param_catalog.py` help 문구 | 코드 안 docstring 이라 이 갈래가 직접 고친다(예외 2) |

---

## §7 D+1 판독 기준

배포 = `src/**` 변경이라 **full**(backend 재시작). 창 = 15:30~19:55 · 21:35~익일 07:45(보유 중 정규장 push 금지, 20:00~21:35 금지). 기본 모드가 `shadow` 라 **배포만으로 5전략 평가가 켜진다**(cycle294 와 달리 DB 선반영 없음) — 끄려면 `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}` 즉시.

**성공 서명**

| 시각 | 무엇 | 기대 |
|---|---|---|
| 첫 매수 시 | `[llm_gate_config] strategy=<sid> mode=shadow min_score=70 daily_cap=20 timeout_s=20` | 7전략 각 1행(종전 5전략은 `mode=off`) — 매수가 없는 전략은 행이 없다(카나리아는 주문 시점 발화) |
| 매수 주문마다 | `[llm_buy_score] strategy=<sid> … score=N` + `[llm_eval_persist] … result=ok` | 전략 무관 주문당 1쌍 |
| 5전략 첫 행들 | `score` 분포 | **전건 ≤ 50 이 아니다**(그러면 §3.2 결측 처리 실패). `input_payload.payload` 의 snapshot 에 `k` 키 부재(4전략) |
| 5전략 첫 행들 | `stop_loss_pct` | `< 0`(0.0 이면 §3.3 회귀) · donchian(turtle) 은 `-(2×atr14_pct)` 와 `-9` 사이 |
| 배포 후 첫 VB·LTV 행 | `prompt_version` | 새 값 Y(X 와 다름 — 예상된 1회 단절) · `input_payload` 는 배포 전 행과 키 집합 동일 |
| 어느 때나 | `GET /api/llm-evaluations/retrospective?days=7` | 200, `aggregate.overall.n_pairs` ≥ 0, `account_no` 문자열 부재 |
| 09-24(목) 20:30 | 루틴 첫 회고(프롬프트 갱신 승인 시) | 응답을 읽고 (전략, prompt_version) 표를 낸다 |

**실패 서명** — `[llm_buy_score_failed] reason=payload_error`(`build_messages` 예외 = §3.2 변경 회귀) · 5전략에 `[llm_gate_config] mode=off` 잔존(키 미반영) · `reason=no_bars` 가 특정 전략 50% 초과(R2 후속) · `[llm_gate_daily_cap]` 발화(하루 20건 매수는 비정상) · `verdict_lag_ms` p95 가 종전(09-11~16)보다 2배 이상 [추론: 버스트 큐잉].

**첫날 예외** — donchian·kojiro 는 09:05~09:30 창에서만, VCP·BFB·momentum 은 실측 체결이 드물다(BFB/VCP ≈0.5건/일 `[루트 CLAUDE.md P0-1]`) → 전략별 첫 행이 **0건인 날이 정상**이다. "매수가 있었는데 행이 없다" 만 실패다. 09-11~09-16 행과 배포 후 행의 `prompt_version` 은 **합산하지 않는다**(등가 상수로만 합친다).

---

## §8 열린 질문 (결정 카드 후보)

1. **VB·LTV `prompt_version` 1회 단절 수용 여부**(§3.4). 대안 = META 를 해시 밖에 두기 → 전략 컨텍스트 개선이 버전에 안 잡힘. 권고 = 수용 + 등가 상수.
2. **손실 정의 `cost_pct` 기본값 0.25**(수수료·세금 근사, [추론]). 실제 왕복 비용(증권거래세·수수료율)은 `_workspace/00_leader_trading_rules.md` 에서 확인 후 상수화 — 그때까지 쿼리 인자.
3. **ATR 손절 근사**(§3.3) — atr14 로 kojiro ATR(20)·donchian `_entry_atr` 를 대신하는 것을 받아들일지, 아니면 `payload` 에 전략의 실제 손절선을 실어 보내는 8영역 밖 배선(전략 객체 read-only 조회)을 후속으로 둘지.
4. **VCP·donchian·kojiro 돌파선을 `buy_signals` 에 싣기**(`base_high`·20일 고가·EMA5) — `breakout_excess_bp` 를 그 전략에도 채워 판단 기준 1 을 살린다. `check_buy_signal` 세그먼트 변경이라 cycle290 28핀 갱신 + 별도 승인.
5. **목요일 20:30 루틴 프롬프트 갱신**(외부 조치) — `GET /api/llm-evaluations/retrospective?days=7` 을 읽고 (전략, prompt_version) 별 표 + 컨텍스트 개선 제안을 PR 로 내게 한다. 자동 적용은 없음(현행 루틴 관례). 첫 실행 09-24.
6. **`no_bars` 대응** — momentum/소형주 일봉 결측이 크면 (a) `_evaluate` 가 KIS 일봉 REST 폴백을 쓰거나 (b) momentum 만 `off` 로 두기. D+1 실측 뒤 결정.
7. **enforce 수치**(§3.6 열) — `domain-consult` 대상. 브리프 초안(N≥30·적중≥70%·오차단≤20%·2주 안정)과 자문 §7.7(왕복≥40·CI·단조·커버리지 20~70%) 중 어느 틀을 정본으로 할지.
8. **`llm_gate_daily_call_cap` 전략별 차등** — donchian·kojiro 는 `max_positions=5` 라 20 이 과하다. 비용 상한이 낮아 균일 20 을 권고하되, 사용자 선택.
9. **회고에 자문 §7.4 L3(미체결 신호 반사실)** 포함 여부 — 이 사이클은 L1(체결군)만. 043 `eval_kind='blocked'` 는 enforce 이후 축.

---

## §9 Red 실행 로그 (tdd-engineer, 2026-09-17 새벽)

`src/` **무변경**. 신규 테스트 4파일만 추가했다.

| 파일 | 대응 | 실측 |
|---|---|---|
| `tests/unit/engine/test_cycle297_llm_strategy_context.py` | G1-1~G1-10 | **64 failed / 14 passed** |
| `tests/unit/ast/test_cycle297_ast_scope.py` | G2-1~G2-10 (+G2-1b 신설) | **24 failed / 48 passed** |
| `tests/unit/engine/test_cycle297_llm_retrospective.py` | G3 | **23 failed / 0 passed** |
| `tests/unit/routes/test_cycle297_llm_retrospective_route.py` | G4 | **20 failed / 2 passed** |
| `tests/integration/test_cycle297_llm_retrospective_pg.py` | G5 | **3 failed**(docker 가용, 실제 실행됨) |

### 실행 명령

```bash
python -m pytest tests/unit/ast/   -q -p no:randomly      # 29 failed(297: 24 · 296: 5) / 1,717 passed
python -m pytest tests/unit/engine/ -q -p no:randomly     # 107 failed(297: 87 · 296 계열: 20) / 6,056 passed
python -m pytest tests/ -q -p no:randomly \
  --ignore=tests/unit/ast --ignore=tests/unit/engine      # 31 failed(297: 23 · 296: 8) / 2,834 passed
TZ=UTC python -m pytest <297 단위 4파일> -q --log-level=DEBUG   # 131 failed / 64 passed (KST 실행과 **동일**)
```

**297 밖 실패는 전부 상대 갈래(cycle296 — `cycle269`/`cycle270`/`cycle296` 토큰 축) 것이고,
내가 건드린 파일 때문에 붉어진 기존 테스트는 0 이다.** TZ 의존·로그레벨 의존 없음(위 대조).

### 초록인 채로 남아야 하는 것 (invariant 핀 — Green 이 붉히면 범위 밖 변경이다)

| 가드 | 무엇 |
|---|---|
| G1-6 | VB·LTV user payload sha `cb6f843cdb1d1d9e` / `b095a46c416ba13e` |
| G1-7b · G1-8a(VB·LTV) | VB·LTV 블록에 `not_applicable` 부재 · 기존 손절 계약 −3.0 |
| G2-3b | 5전략 `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity`/`prepare` = cycle290 28핀 |
| G2-4 | 4키 ∉ `PARAM_RANGES`/`INT_PARAMS` + `recommendation_engine.py` 리터럴 0 |
| G2-6 | `SYSTEM_PROMPT`·`_USER_PREAMBLE`·`_SNAPSHOT_KEYS` 세그먼트 sha |
| G2-9 | 무접촉 13파일 byte 동일 + `scheduler.py` 3,726L |
| G2-1b | cycle274 `test_c10_3` · cycle276 `test_c6_3a` **존재 + 미skip** |
| G4-6b · G4-7 | 기존 `/{order_no}` 상세 404 경로 생존 · 라우트 GET 전용 |

### 명세에서 벗어난 판단 3건 (Green·검증이 알아야 할 것)

1. **G1-4b 의 「멀티데이」를 4전략으로 넓혔다.** §5.3 M3 은 donchian·VCP·kojiro 셋을 들지만
   BFB 도 `max_hold_days=5` 시간 청산이라 15:20 규약이 없다(`strategies/CLAUDE.md:157`).
   VB 잣대 오염 차단이 이 단언의 목적이므로 넷 다 막는 쪽이 좁고 정확하다.
2. **G2-9 `_BASE_SHA` 에서 `src/auth/**` 와 `src/engine/quote_token_refresh.py` 를 제외했다.**
   상대 갈래(cycle296)가 그 두 축을 고친다 — 핀하면 정당한 변경이 이 파일을 붉힌다.
   제외가 **의도**임을 `test_g2_9b` 가 명시적으로 단언한다(조용한 구멍 금지).
3. **G3 의 `by_prompt_version` 키를 `f"{strategy}|{prompt_version}"` 문자열로 못박았다.**
   §3.5 는 `(sid, pv)` 튜플로 적었지만 JSON 키는 문자열이어야 한다. 두 값 어디에도 `|` 가
   나타나지 않아(sid=식별자, pv=sha256 앞 12자) 충돌이 없다 — cycle276 `summary_key()` 관례 답습.

### Green 이 반드시 읽어야 할 계약 (Red 가 못박은 것)

- `snapshot_keys_for(sid) -> tuple[str, ...]` — 순서는 `_SNAPSHOT_KEYS` 그대로, NA 키는 **제거**(None 금지)
- `_resolve_stop_loss_pct(strategy_id, params, tech) -> float` — 항상 **음수**, 골든 표는 G1-9a
- `_prompt_version(strategy_id) -> str` — 12자, 전략별 상이, 같은 sid 는 캐시 동일, blob 에 META 포함
- `join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date, cost_pct=DEFAULT_COST_PCT) -> list[dict]`
  (§10-C — `cost_pct` 는 행 `outcome` 을 집계와 **같은 정의**로 매기려고 추가됐다. 기본값이 있어 Red 계약 호출은 그대로 성립한다)
- `aggregate(rows, *, cost_pct) -> {"overall", "by_strategy", "by_prompt_version"}`
- 버킷 = 10칸, `lo=i*10+1`·`hi=i*10+10`, Σn == `n_scored`
- 회고 실패 로그는 `[llm_eval_route_error]` + `retrospective` 를 포함하고 `order_no=` 문면을
  **쓰지 않는다** — 상세 핸들러의 500 과 구별되어야 한다(G4-4b 의 거짓 초록 차단 장치)

### 알려진 후속 (Final 단계 몫)

- `tests/unit/ast/test_cycle287_ast_scope.py` `_SRC_TREE_FILES`(152 → +2)·`_SRC_TREE_DIGEST` —
  297 `llm_retrospective.py` + 296 신규 leaf. **이 갈래는 손대지 않았다**(현재 초록).
- `tests/unit/ast/test_cycle290_ast_scope.py::_ENGINE_PY_FILES` 에 `llm_retrospective.py` 추가 = Green.
- cycle274 `test_c10_3` · cycle276 `test_c6_3a` 기대값 반전 = Green(삭제·skip 금지, G2-1b 가 봉인).

---

## §10 검증 후속 시정 (2026-09-17, backend-dev)

적대 검증 2렌즈(사실 대조·뮤테이션)의 CRITICAL/HIGH 를 근거 재확인 후 시정했다.
**매매 행위 변경은 여전히 0** — 접촉 파일은 `llm_buy_gate.py` · `llm_features.py` ·
`llm_retrospective.py` · `routes/llm_evaluations.py` 넷이고 8영역·`scheduler.py`(3,726L)·
전략 7파일·`strategy_base.py` 는 diff 0 이다.

### A. HIGH — `_resolve_stop_loss_pct` 가 프로덕션에서 **한 번도 불리지 않았다** (2렌즈 공통)

- **확인** — `grep -rn "_resolve_stop_loss_pct(" src/` 가 `def` 한 줄만. `observe_order` 의
  `payload["stop_loss_pct"]` 는 여전히 `_read_stop_loss_pct` 고정값이었고, §3.3 이 요구한
  "`_evaluate` 의 `compute_technicals` 뒤 1곳" 이 없었다. G1-9 가 그 함수를 **직접** 부르므로
  전수 초록이었다 — 순수 함수 테스트는 "계산이 맞는가" 는 잡아도 "그 계산이 쓰이는가" 는
  구조적으로 못 잡는다.
- **영향** — 운영 DB 에서 donchian 이 `sizing_mode="turtle"` 라이브다. 배선이 없으면 그
  전략의 첫 표본부터 실제 손절(`max(-(2×ATR), -9%)`)과 다른 −7.0 으로 채점되고,
  SYSTEM_PROMPT 판단 기준 4(손절폭 vs `atr14_pct`)가 틀린 수치로 발동·미발동한다.
  §7 D+1 판독 항목("donchian(turtle) 은 −(2×atr14) 와 −9 사이")이 배포 첫날 실패했을 것이다.
- **시정** — `_evaluate_core` 의 `vol_ratio_*` 블록 **직후**(= 명세가 지정한 자리)에
  `payload["stop_loss_pct"] = _resolve_stop_loss_pct(...)` 1곳. `_evaluate_core` 는 params 를
  못 보므로 `observe_order` 가 `_read_stop_params(params)`(7키 화이트리스트)를
  `payload["_stop_params"]` 로 실어 보낸다.
- **`_stop_params` 는 프롬프트에도 DB 에도 안 실린다** — 프롬프트는 `snapshot_keys_for`
  화이트리스트가, `input_payload` 는 `_PAYLOAD_EXCLUDED_KEYS` 가 막는다. 후자를 택한 이유 =
  넣으면 VB·LTV 의 `input_payload` 키 집합이 배포 전후로 갈려 §7 D+1 대조("키 집합 동일")가
  무너진다. 감사 가치는 잃지 않는다 — 재해석 **결과**(`stop_loss_pct`)와 그 근거
  (`tech.atr14_pct`)가 같은 행에 이미 담긴다(`test_w1b`).
- **`exit_rule` 근사 표기** — donchian·BFB·VCP·kojiro 문구 끝에 "입력의 stop_loss_pct 는
  ATR(14) 기준 근사다" 를 붙였다(§3.3 이 요구했는데 빠져 있었다).

### B. HIGH — BFB 의 `target_price` 는 돌파선이 아니라 **측정 이동 목표가**였다

- **확인** — `bull_flag_breakout.py` 의 `buy_signals.append` 는
  `"flag_high": flag_high` 와 `"target_price": flag_high + (pole_high - pole_start)` 를 **둘 다**
  싣는다. 게이트는 `sig.get("target_price")` 만 읽었으므로 BFB 의 모든 주문이 큰 음수
  `breakout_excess_bp` 로 나갔다(돌파선 10,000·목표 11,500 에 10,050 매수 → **−1,261bp**).
  SYSTEM_PROMPT 판단 기준 1 은 그 값을 "돌파의 질" 로 읽으므로, VB 에서 "+bp = 추격" 이던
  잣대가 BFB 에서 정확히 뒤집힌다 — 이 사이클이 없애려던 §1.2 F5 잣대 오염이 BFB 에서
  새로 생길 참이었다.
- **덤으로 드러난 모순** — donchian(`donchian_high`)·VCP(`base_high`)도 돌파선을 이미
  싣는데 §3.2 가 "목표가 개념이 없다" 로 분류했다. 그래서 같은 프롬프트 안에서
  `entry_rule`("기준가 대비 +4% 초과 추격은 하지 않는다")과 `not_applicable`("목표가 개념이
  없다")이 정면으로 모순됐고, "대신 확장폭으로 보라" 는 그 확장폭이 payload 에 없었다.
- **시정** — 전략 파일 무접촉. `llm_buy_gate._BREAKOUT_LINE_KEYS`(7전략 **명시 매핑**) +
  `_read_breakout_line(strategy_id, sig)` 를 두고 `target_won` 산출을 그것으로 교체했다.
  `or` 폴백 체인을 쓰지 않은 이유 = 키 부재에 우연히 기대는 설계라, 어느 전략이 나중에
  같은 이름의 키를 추가하면 조용히 뜻이 바뀐다. `_SNAPSHOT_NA_KEYS` 는
  momentum·kojiro 만 3키, donchian·VCP·BFB 는 `("k",)` 가 됐고 `_NOT_APPLICABLE_NOTES` 도
  그에 맞춰 갈렸다(문구에서 payload 에 없는 "확장폭" 을 빼고 실제 필드명으로 교체).
- **미등록 전략은 `target_price` 폴백** — 신규 전략이 추가돼도 종전 동작을 유지한다.

### C. MEDIUM — 손실 정의가 응답 안에 둘이었다

행 `outcome` 은 `profit_rate < 0`, 집계는 `<= cost_pct` 였다(모듈 docstring 은 `<` 라고 적혀
있었고 코드는 `<=` 였다). `0 < profit_rate <= cost_pct` 페어가 표에서는 `win`, 같은 응답의
집계에서는 손실이라 목요일 루틴이 둘을 나란히 읽으면 숫자가 맞지 않는다. `_row_outcome`
을 **삭제**하고 `_resolve_outcome` 하나로 통일, `join_pairs_with_evaluations` 에
`cost_pct` 키워드(기본 `DEFAULT_COST_PCT=0.25`)를 추가해 라우트가 쿼리값을 그대로 넘긴다.

### D. MEDIUM — 라우트가 쿼리를 실제로 쓰는지 아무도 재지 않았다

뮤테이션 렌즈가 `aggregate(rows, cost_pct=0.0)` 고정과 `since = until - days`(8일 창)를 둘 다
ESCAPED 로 잡았다. 원인은 픽스처의 `profit_rate` 가 −3.5 하나뿐이라 `cost_pct` 가 결과를
바꿀 표본이 없었고 `window.since` 를 아무도 단언하지 않았던 것. 창 정의는 **`days` 일 포함**
으로 확정하고(주간 비중첩) `test_g4_8`/`test_g4_10` 으로 고정했다.

### E. LOW — 그 밖

| | 무엇 | 시정 |
|---|---|---|
| E1 | `_pick_primary` 가 입력 순서 의존(호출자가 `ORDER BY trade_date DESC` 라 **가장 늦은 날짜**가 primary) | §3.5-3 대로 `trade_date == buy_date` 우선 |
| E2 | `test_g4_5` Decimal 가드가 **공허**(검사 키 `cost_usd`·`k` 를 `_EVAL_WHITELIST` 가 이미 떼어낸다) | 화이트리스트 키(`score`·`min_score`)로 교체 + `primary` 포함 |
| E3 | 라우트가 창 밖·open 페어의 주문번호까지 전부 모아 평가 테이블을 조회 | 주문번호 수집 **앞**에 창·상태 필터(leaf 필터는 그대로 — 다른 호출자 방어) |
| E4 | `_prompt_version` 오배선(`payload["ticker"]` 등)·전체 `_SNAPSHOT_KEYS` 해싱이 무가드 | `test_w3a`/`test_w3b` |
| E5 | `_read_stop_loss_pct` 의 DB 오버라이드 전파 무가드 | `test_w4` 7전략 전수 |
| E6 | `result != "ok"` 검사·`status=="closed"` 필터가 운영 데이터에서 동치라 무가드 | `test_g3_9`/`test_g3_10` |
| E7 | `_PROMPT_VERSION_ALIASES` 가 빈 dict | VB·LTV 배포 전→후 키 2쌍을 채웠다(아래) |

**등가표(E7)** — 배포 중인 커밋(`5421a90`)의 `llm_features.py` 가 HEAD 와 byte 동일이고 구
`_prompt_version()` 은 인자가 없어 전 전략 공통이었다. 그 blob 을 구 소스로 재계산한 값이
`4162dc5fcea0` 이고, 새 값은 VB `9c45283a49c1` · LTV `7a9c45983c0d` 다(둘 다 이 사이클의
NA 키 변경에 영향받지 않는다 — VB·LTV 는 `_SNAPSHOT_NA_KEYS` 밖). 🔴 **합산은 소비자(목요일
루틴)가 한다** — `aggregate` 안에서 조용히 접지 않는다. 표가 틀렸을 때 집계가 두 모집단을
말없이 섞으면 그 오류를 볼 방법이 없다. 배포 후 운영 DB 에서
`SELECT DISTINCT prompt_version FROM llm_buy_evaluations WHERE trade_date < '<배포일>'` 로
1회 대조하고, 다르면 **표를 지운다**(틀린 합산이 빈 표보다 나쁘다).

### F. 고치지 않은 지적과 이유

- **"`aggregate` 가 alias 를 적용해야 한다"** — 채택하지 않았다. 위 E7 사유. 표는 응답에
  노출만 하고 합산 판단은 소비자에게 남긴다.
- **"`consumed` 소비 규칙은 순서 의존이니 없애라"** — 남겼다. 운영에서는 한 매수 주문이
  정확히 한 페어에만 속해(`get_trade_pairs` 가 포지션 0 복귀 시점마다 emit) 그 규칙이
  발화할 데이터가 없고, 규칙을 빼면 픽스처·데이터 오염 시 한 평가가 두 페어에 이중
  계상된다. 지금은 **데이터 오염을 이중 계상보다 낫게** 처리하는 쪽이 맞다.

### G. 신규·변경 가드

| 파일 | 무엇 |
|---|---|
| `tests/unit/engine/test_cycle297_gate_wiring.py` (신규 38) | W1 배선(프롬프트·`input_payload`·AST) · W2 돌파선(매핑↔`buy_signals` AST 대조 · BFB 측정이동 증거 · NA 정합 · end-to-end 2) · W3 `prompt_version` · W4 라이브 params |
| `tests/unit/engine/test_cycle297_llm_retrospective.py` (+4) | 행/집계 손실 정의 일치 · `buy_date` 우선 primary · 실패 평가 미채점 · open 페어 제외 |
| `tests/unit/routes/test_cycle297_llm_retrospective_route.py` (+4, 1 수정) | `cost_pct` 왕복 · 행/집계 정의 일치 · 창 경계 freezegun · 등가표 형식+값 · Decimal 가드 실질화 |
| `tests/unit/engine/test_cycle297_llm_strategy_context.py` (표 1건) | G1-5b 의 donchian·VCP 분류를 `("k",)` 로 정정(사유 주석 동반) |

뮤테이션 전수 KILLED(8종) — 배선 제거 / `target_price` 회귀 / 행 outcome 고정 / `status`
필터 제거 / `result=="ok"` 제거 / primary 첫 매칭 / 라우트 `cost_pct` 고정 / 라우트 창 off-by-one.
