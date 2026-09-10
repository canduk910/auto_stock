# cycle273e Red 명세 — D2(나) F-3: 고지로 갭 게이트 **+ 붕괴 가드** 오염 차단 (`risk.py:646` skip 에 kojiro 추가)

- 작성 2026-09-10 · tdd-engineer · **기준 HEAD `1df6d7d`**
- 사용자 결정 원문(09-10 목) = "**2. D2 주문/청산 안전 3건 — 가, 다, 나 순서로 진행하자.**" ⇒ 이 문서가 **(나)**
- **매매 행위 변경** ⇒ `domain-consult` 선행 완료:
  `_workspace/domain_consult/cycle273_kojiro_gap_gate_20260910.md`(자문 K1)
- 코드 정본 = `_workspace/analysis/2026-09-10_cycle273_UB_risk_gap.md`(U-B) ·
  판독 `_workspace/analysis/2026-09-10_kojiro_gap_readout.md` ·
  코호트 실측 `_workspace/consult/2026-09-07_kojiro_gap_contamination.md`(N=103)
- ⚠️ 이름 충돌 주의 — 워크리스트의 **필옵틱스 F-3**(`[trade_status_multi_update]`)은
  별개 항목이다(`cycle273b_philoptics_no_behavior_3_spec.md`).

---

## 0. 자문 결론 — **착수한다** (보류 권고 아님)

자문 K1 §0/§1.1 은 "**F-3 은 필요하다. cycle272(REST 기준가)가 닫지 않는다.
'보류하고 D+1 로 확인' 은 권고하지 않는다**" 로 결론했다. 따라서 이 명세는
**보류 조건 명세가 아니라 정규 Red 명세**다.

보류를 권고하지 않는 이유(자문 §1.3):
- 관측 채널이 곧 사라진다 — `[kojiro_gap_observe]` 는 INFO 라 `system_logs` **2일 보존**,
  경로 B 가 창 안에 들어온 날은 이틀 표본 중 **하루(09-10, 2건)**. "한 주 더" 는 "한 주 뒤에도 N=2~4".
- 게이트 오작동 base rate 는 **09-07 에 N=103 으로 이미 측정**됐다(§1-b). 남은 미지는
  "kojiro 후보가 경로 B 에 노출되는 빈도" 인데 그것은 **F-3 이 0 으로 만드는 게 목적**이라 대기로 얻을 게 없다.

---

## 1. 사실관계

### 1-a. 네 관문이 같은 인자 하나에 매달려 있다

```
kojiro.py:866  prev_close = info["prev_close"]                       ← 일봉(오염 없음, 11/11 DB 일치)
        :868  gap_rate = (open_price - prev_close) / prev_close*100  ← ★ 인자
        :871  gap_rate >= 5.0  → skip_up   + :878 _bought_today.add  = 당일 영구 스킵
        :880  gap_rate <= -4.0 → skip_down + :887 _bought_today.add  = 당일 영구 스킵
        :891  open_price > 0 and current_price < open_price → collapse  ← ★ 같은 인자, 창 내 재시도
        :901  pass → :905 _bought_today.add → Signal.BUY
```

> ⚠️ **명칭 경고** — "F-3 = 갭 판정 오염" 이라는 이름 탓에 **붕괴 가드가 논의에서 빠질 위험**이 있다.
> 판독에서 실제로 뒤집힌 유일한 관문이 **붕괴 가드**다. 커밋 메시지·주석에 **"갭 게이트 + 붕괴 가드"** 병기.

### 1-b. 두 경로와 오염의 구조적 원인

| | 경로 A `_swing_buy_poll_loop` | 경로 B `risk.on_tick` |
|---|---|---|
| 시가 출처 | `fetch_stock_detail(t)["stck_oprc"]`(`scheduler.py:2669`) = KIS REST 당일 KRX 시가 | `int(fields[7])`(`handler.py:417`) = 통합채널 `H0UNCNT0` `[7] STCK_OPRC` |
| 스코프 필터 | 불필요 | **없음** ← 오염의 구조적 원인 |
| 주기 | 09:05~09:30 **분당 1회 × 25회** | 틱마다 |
| 커버리지 | 후보 전체(`get_scanned_tickers()` ⊇ `_candidates`) | 부분(다른 전략 후보이거나 보유 중인 종목만) |

형제 필드 `[8] 고가`는 `[27] HGPR_HOUR` MAIN 창 필터를 갖는데(`_parse_day_high`),
`[7]` 에 대응하는 `[24] OPRC_HOUR` 는 cycle264 가 **관측만** 심었을 뿐 파싱→필터 경로가 없다.

**09-07 실측(N=103)**: WS 시가 ≠ KRX 확정 시가 **98/103(95.1%)** · 갭률 오차 최대 **6.77%p** ·
진짜 갭업(≥5%) **탐지율 0/8** · 반대 방향(`skip_up → pass`) 0.
교과서적 실례 `131290` — WS 시가 = 전일 종가 ⇒ 갭률 **0.00%**, KRX 확정 시가 기준 **+6.77%**.
**"갭업 스킵" 이 갭업을 못 본다.**

### 1-c. 래치가 오염을 위험 쪽으로 정류한다

`skip_up`/`skip_down`/`pass` 는 전부 `_bought_today.add(ticker)` = 당일 영구다.
그리고 `_swing_buy_poll_loop` 가 `if t in strategy._bought_today: continue` 로 그 래치를 존중한다.

```
오염된 경로 B 가 먼저 "pass" → 그대로 매수까지 간다. 깨끗한 경로 A 는 이미 늦다.
오염된 경로 B 가 먼저 "skip" → 래치가 걸려 깨끗한 경로 A 가 그날 차례를 못 받는다.
```
⇒ **틀린 답이 맞는 답을 당일 영구히 밀어낸다.**

### 1-d. cycle272 가 닫지 않는다 (증거 4 — U-B §4.2)

1. 착지점이 다르다 — cycle272 의 REST 기준가는 `_confirm_breakout_open_prices` →
   `on_open_price_confirmed` → 전략 `_targets` 이고, 그 루프는
   `("volatility_breakout","long_tail_volatility")` **하드코딩**(`scheduler.py:1616`) +
   `_targets`/`on_open_price_confirmed` 속성 요구(`:1618`). **kojiro 는 둘 다 없다.**
2. kojiro 가 읽는 값은 `_targets` 도 `ticker_prices` 도 아닌 **함수 인자**다.
3. 자문 `2026-09-07_open_price_scope_filter.md` §3.2 가 kojiro 를 명시적으로 범위 밖 선언.
4. `risk.on_tick:495-500` 이 매 틱 `ticker_prices` 를 통째 교체하고, kojiro 판정은 그 dict 를 읽지도 않는다.

**유일한 반전 조건** = cycle272 가 `handler._parse_tick_prices` 또는 `risk.on_tick` 의
`check_*_signal` **호출 인자**를 바꿨을 때. 병합 전 §7 3줄 확인으로 확정한다.

### 1-e. 이 skip 은 새 정책이 아니라 **2026-07-17 에 미룬 배선의 완성**

`35a08eb`(2026-05-12) 커밋 메시지가 donchian skip 을 "**이중 안전망**"으로 명시한다
(주 기전은 `swing: []` 미구독). kojiro 를 `_SWING_POLL_STRATEGIES` 에 넣은 `24b8b5c`
(2026-07-17)는 `risk.py` 를 **한 줄도 건드리지 않았다** — 커밋 메시지가 이유를 적었다:
"enabled=False 다크런치로 병합 — **매매 안전성 8영역 diff 0**". 즉 폴 루프 절반만 상속하고
이중 안전망 절반은 **행위 판단이 아니라 승인 범위** 때문에 미적용으로 남았다.

---

## 2. 행위 영향 — 딱 한 문장

> **WebSocket 틱을 통한 kojiro 신규 매수 = 0.**

**바뀌는 것 (전부)**
- 경로 B 를 통한 kojiro `check_buy_signal` 호출 = 0 ⇒ 오염된 시가로 내려지던 판정 소멸
- 경로 B 발 `_bought_today` 오염 래치 소멸(§1-c)
- `[kojiro_gap_observe]` 의 `caller=on_tick` 행 = 0 (D+1 서명 #1)

**바뀌지 않는 것** (전부 skip 지점보다 **앞** — U-B §1.1 표)

| | 무접촉 |
|---|---|
| 청산·손절·트레일링·익일청산·15:20 강제청산 | ✅ `risk.py:589-597` |
| `day_high` 앵커 병합 | ✅ `:558-586` |
| `[tradable_skip]`·`[risk_silent_skip]` 카운터 | ✅ `:603`·`:625` |
| `is_ticker_blocked_for_buy` 호출 횟수 | ✅ `:617` |
| 경로 A 전부(판정·임계·수량 관문 K/K_ρ) | ✅ |
| donchian·타 전략 | ✅ |
| 후보 **집합** | ✅ 무변(`ranked_final ∪ held_only` ⊇ `_candidates`) |

**대가 — 평가 빈도뿐(정보 손실 0)**
`[7]` 이 *맞는* 경우(프리장 체결 없음)는 103 중 5건(4.9%)이고 **그 5건도 경로 A 가 같은 값을 준다.**
잃는 것은 최악 **≤60초** 지연 하나다. 자문 §3.2 판정: 09:05~09:30 은 노이즈가 가장 큰 구간이고,
붕괴 가드는 경계 판정이라 1분 샘플링 자체가 얕은 필터다. 대형주 1분 드리프트 0.1~0.3% vs
kojiro 손절 2ATR = 2~12% ⇒ 손익비 영향은 소수점 아래. 반대편 저울은 "갭업 미탐 1건 =
진입 즉시 손절폭 상당 부분 소진".

> **`risk.py:644` 주석을 복붙하지 말 것.** "일봉 전략이라 실시간 tick 평가가 구조적 낭비" 는
> 2026-05-12 donchian 에 대한 판단이고 kojiro 에 대해 검증된 명제가 아니다(판독 정정 K-6).
> kojiro 용 근거는 **경계 판정 × 노이즈 구간 × 손절폭 대비 타이밍 비용** 세 줄이다.

---

## 3. 설계 결정 (자문 권고 반영)

| 축 | 결정 | 근거 |
|---|---|---|
| 구현 형태 | **(나) 명시 상수** `_TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing","kojiro"})` (모듈 상수, `risk.py:79` `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 관례 동형) | 자문 §3.6. 행위는 리터럴 확장과 **완전 동일** — 스타일 결정(§9 O-E2) |
| 삽입 위치 | **반드시 현행 skip 과 같은 자리**(`:646`, `check_buy_signal` 직전) | 앞으로 옮기면 `[tradable_skip]`·`[risk_silent_skip]` 카운터와 `is_ticker_blocked_for_buy` 호출 횟수가 바뀐다 = 관측 지표 드리프트 = 행위 변경 범위 확대 |
| 판정 축 | **`strategy_id` 문자열만.** `tradable_boards`/`sizing_mode`/`config.params` 참조 0건 | 설정 하나가 매수 평가 경로를 바꾸는 커플링 차단(청산 축 AST 금기와 **동형의 반대 방향**) |
| 킬스위치 | **두지 않는다.** 1행 revert 로만 롤백 | 자문 §3.3 — ① 실패 방향이 단방향(매수 감소)이고 그게 설계 의도 ② kojiro 매수 창은 09:05~09:30 뿐이라 장중 롤백 수요가 **구조적으로 없다**(장 마감 후 되돌리면 다음 영업일 09:05 원복) ③ `DEFAULT_PARAMS` 키는 8영역이 전략 params 를 읽어 매수 경로를 분기하게 만든다 ④ donchian 이 4개월째 킬스위치 없이 운영 중 |
| 관측 | 신규 마커 **0개.** 기존 `[kojiro_gap_observe]` 의 **caller 분포**를 D+1 서명으로 쓴다 | 자문 §3.4 (나) — 8영역 hot path 에 관측 추가 금지 |
| `ws_collapse` 필드 | **F-3 보다 먼저, 별도 커밋** (비8영역 leaf `kojiro_gap_observe.py`, 행위 0) | 자문 §3.4 (다) — `_verdict_for_gap` 은 **갭 게이트만** 재현하고 **붕괴 가드는 제외**한다. 그런데 이번에 실제로 뒤집힌 유일한 관문이 붕괴 가드다. F-3 이후 "WS 값이었으면 붕괴로 걸렸을까" 가 관측에서 사라진다. 이 필드가 F-2(근본 시정)의 비용/편익을 계속 재는 유일한 채널이다 |
| 배포일 | **cycle272 와 분리.** cycle272 배포 → 그 D+1 판독 종료 → **그 다음** F-3 | 자문 §3.7 — kojiro 는 체결 0~1건/일이라 신호가 약하다. VB 진입 −27.6% 급 변화와 섞이면 kojiro 귀인이 통째로 죽는다 |

권고 순서: **① `ws_collapse` leaf(행위 0) → ② cycle272 → ③ cycle272 D+1 판독 → ④ F-3**
(사용자가 지정한 `(가)→(다)→(나)` 는 **작업 순서**이고 배포 묶음은 미지정 — §9 O-E4)

---

## 4. 계약 (Red) — 자문 §4 의 R1~R11

| # | 계약 | HEAD | 파일 |
|---|---|---|---|
| R1 | kojiro 후보(미보유) 틱 → `check_buy_signal` **호출 0회** + `execute_buy` 0회 | **RED** | 행위 |
| R2 | 같은 틱에서 **보유 중**이면 `check_exit_signal` 은 **호출된다** | GREEN(계약) | 행위 |
| R3 | 보유 + `check_exit_signal` 이 `STOP_LOSS` → `execute_sell(ticker, STOP_LOSS, "kojiro")` **호출된다** | GREEN(계약) | 행위 |
| R4 | 보드 밖 틱 → `_tradable_skip_count["kojiro"] == 1` (불변) | GREEN(위치) | 행위 |
| R4b | 자금 가드 → `[risk_silent_skip] … strategy=kojiro` INFO 발화(불변) | GREEN(위치) | 행위 |
| R5 | `is_ticker_blocked_for_buy` 호출 횟수 **동일**(1회) | GREEN(위치) | 행위 |
| R6 | 실 `_swing_buy_poll_loop` 는 kojiro `check_buy_signal` 을 **계속 호출**하고 시가는 REST `stck_oprc` | GREEN(경로 A) | 행위 |
| R7 | donchian skip 불변 (기존 4케이스 `test_risk_donchian_skip_buy.py` 그대로 통과) | GREEN | 행위 |
| R8 | kojiro skip **과 동시에** 제3 전략(momentum)은 평가된다 | **RED** | 행위 |
| R9 | AST — skip 판정이 `strategy_id` 문자열만 쓴다(`tradable_boards`/`sizing_mode`/`params`/`config` 참조 0건) | **RED** | AST |
| R10a/b | AST — 상수명·frozenset·멤버 `{donchian_swing, kojiro}` 동결 (**런타임 + 소스 리터럴 이중**, cycle262 G-262-1 관례) | **RED** | AST |
| R-pos | AST — skip 이 `is_ticker_blocked_for_buy` **뒤** ∧ `check_buy_signal` **앞** ∧ `check_exit_signal` **뒤** | **RED** | AST |
| R-sep | AST — `_PRE_MARKET_EXIT_EVAL_STRATEGIES`(청산 축)는 무접촉(`{"long_tail_volatility"}`) | GREEN(영구) | AST |
| R-kill | AST — 킬스위치 `DEFAULT_PARAMS` 키 0개 | GREEN(영구) | AST |
| R11 | `test_cycle268_tester_real_call_paths.py::test_real_risk_on_tick_yields_caller_on_tick` **계약 반전** — 실 `RiskManager.on_tick` 에서 kojiro 마커 **0행**, **양성 대조**(별도 인스턴스 직접 호출은 행이 나온다)와 짝 | **RED** | 교체 |

**테스트하지 않는 것** — "붕괴 가드 재시도 빈도가 1분". 시간 의존이라 계약에 넣지 않는다.
R6 이 폴 루프 **1사이클**만 검증하고, 빈도는 운영 로그 서명 #2 에 맡긴다(자문 §4 하단).

### R11 — 원저자 의도를 뒤집는 결정 (§9 O-E1)

원 가드 docstring 은 "**삭제하지 마라**" 로 끝난다. 목적은 `observe_gap(depth=2)` 프레임
오프셋을 **두 실경로로** 봉인하는 것이었다. F-3 이후 경로 B 는 프로덕션에 없다.

- (b) 삭제 → F-3 회귀 가드까지 버린다. **반대**
- (c) 합성 shim 으로 되살리기 → 그 파일이 없애려던 바로 그것. **반대**
- (a) **0행 단언으로 반전** → F-3 의 회귀 가드가 된다. depth=2 봉인 A팔은
  `test_real_swing_poll_loop_yields_caller_swing_buy_poll_loop` 가 계속 진다. **채택**

재작성 시 **docstring 에 "왜 B팔 봉인이 사라졌는지" 를 남긴다** — 다음 사람이 "합성 shim 으로
되살리자" 고 하면 그건 이 파일이 없애려던 바로 그것이다. 보류 Red 파일이 그 문구를 포함한다.

---

## 5. 최소 diff 계획

### `src/engine/risk.py` (🔴 **8영역 — 승인 필요**, D2 (나) 로 지시됨)

| # | 위치 | 변경 | 행 |
|---|---|---|---|
| E1 | `:79` 근처(모듈 상수 블록) | `_TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})` + 근거 주석(§2 세 줄) | +8~10 |
| E2 | `:643-647` | 주석 갱신(§2 경고) + `if strategy.strategy_id in _TICK_BUY_EVAL_SKIP_STRATEGIES: continue` | ±3 |

**그 밖 diff 0.** `check_exit_signal` 분기·보드 가드·중복 가드·자금 가드·`ticker_prices` 갱신
무접촉. 전략 파일 7개 diff 0. `scheduler.py` diff 0.

### 선행 별도 커밋 — `src/engine/kojiro_gap_observe.py` (비8영역 leaf, 행위 0)
`ws_collapse` 반사실 필드 1개 추가(= `ws_open > 0 and cur < ws_open`). 기존 필드·서식 **보존**
(과거 로그 대조 유지). 이 커밋을 **먼저** 배포해야 F-3 전후를 같은 필드로 비교할 수 있다.

---

## 6. 검증 게이트 · 뮤테이션 · D+1 판독

### 게이트
1. 보류 Red 7건 GREEN 전환 + 기존 4케이스(`test_risk_donchian_skip_buy.py`) 그대로 통과
2. `pytest tests/unit/engine tests/unit/engine/strategies tests/unit/ast` 회귀 0
3. `pytest tests/unit/engine/test_cycle268_tester_real_call_paths.py` — 경로 A 테스트 **불변** 확인
4. 백엔드 전체 PASS(기준선 7,548) + `--log-level=DEBUG` 재실행
5. **cycle272 병합 후 §7 3줄 확인**(하나라도 거짓이면 §1-d 결론 재평가)

### 뮤테이션 — 전부 KILLED (자문 §8 이 지정한 두 축 포함)
| # | 뮤테이션 | 잡는 가드 |
|---|---|---|
| P1 | skip 을 **청산 분기 앞**으로 이동 | R2 · R3 · **R-pos**(`check_exit_signal` 뒤 단언) |
| P2 | `continue` → `pass` | R1 · **R8** |
| P3 | 상수에서 `"kojiro"` 제거 | R1 · R10a/b |
| P4 | 상수에 세 번째 멤버 추가 | R10a/b |
| P5 | skip 을 `is_ticker_blocked_for_buy` **앞**으로 이동 | R5 · R-pos |
| P6 | 판정을 `tradable_boards`/`sizing_mode` 로 교체 | R9 |
| P7 | skip 을 `continue` 대신 `break`(루프 전체 중단) | R8 |
| P8 | kojiro 를 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 에 잘못 추가 | R-sep |

### D+1 판독 규칙 — ⚠️ **의미 반전. 배포 전후 grep 합산 금지**(cycle263 선례 동형)

| # | 서명 | 배포 전(09-09 / 09-10) | 기대 | 어긋나면 |
|---|---|---|---|---|
| 1 | `[kojiro_gap_observe] … caller=on_tick` | 0 / **2** | **0행** | 1행이라도 있으면 **미적용**(배포 실패 또는 삽입 위치 오류) |
| 2 | `[kojiro_gap_observe] … caller=_swing_buy_poll_loop` | 8 / 8 | **≥6행 유지**(양성 대조) | 급감 = 경로 A 고장 → **F-3 과 무관한 결함**, 즉시 조사 |
| 3 | `[swing_poll] candidates=N filtered=M` | — | **불변** | 감소 = 후보 집합 소실 |
| 4 | kojiro 체결 | 1 / 1 | **단일일 판정 불가** — 5영업일 누계로 본다 | 5일 0건 → revert 검토 |
| 5 | kojiro 청산 마커(손절·트레일링·breakeven) | — | **불변** | 변하면 삽입 위치가 청산보다 앞 = **즉시 revert** |
| 6 | `[tradable_skip]` · `[risk_silent_skip]` | — | **불변** | 삽입 위치 오류 |
| 7 | `[kojiro_sector_cap]` | — | 불변 또는 감소 | — |

🔴 **#1 은 단독으로는 증거가 약하다** — "F-3 이 작동했다" 와 "그날 kojiro 후보에 틱이 안 왔다"
를 구별하지 못한다(09-09 가 정확히 후자였다). **반드시 #2 와 짝으로 읽는다.**

### 롤백 트리거 (킬스위치가 없으므로 명문화)
- #2 가 baseline(8행/일) 대비 **급감** → 즉시 조사(F-3 무관 결함일 수 있다)
- #5 가 변함 → **즉시 1행 revert**
- kojiro 체결 **5영업일 연속 0** → revert 검토

---

## 7. cycle272 병합 시 재확인 3줄 (U-B §7)

```bash
# 1) 인자 배관이 그대로인가 (여기가 바뀌면 kojiro 도 영향을 받는다)
git diff <cycle272 base>..HEAD -- src/realtime/handler.py | grep -n "fields\[7\]\|_parse_tick_prices\|_on_tick("
git diff <cycle272 base>..HEAD -- src/engine/risk.py     | grep -n "check_buy_signal\|check_exit_signal\|open_price"
# 기대: 빈 출력 (= 호출 인자 byte 동일)

# 2) REST 기준가의 착지점이 VB/LTV 전용인가
git diff <cycle272 base>..HEAD -- src/engine/scheduler.py | grep -n "on_open_price_confirmed\|volatility_breakout\", \"long_tail_volatility"
# 기대: 두 전략 하드코딩 루프 안에서만 변경

# 3) kojiro 가 새 속성을 얻지 않았는가
git show HEAD:src/engine/strategies/kojiro.py | grep -c "_targets\|on_open_price_confirmed"
# 기대: 0
```
하나라도 거짓이면 **§1-d 결론(자동 해소 없음)을 재평가**해야 한다.

---

## 8. 보류 Red 파일 · 8영역 절차

### 8.1 보류 Red

| 보류 경로 | → 최종 목적지 | RED/GREEN(HEAD) |
|---|---|---|
| `…/cycle273e/test_cycle273e_risk_kojiro_skip_buy.py` | `tests/unit/engine/test_cycle273e_risk_kojiro_skip_buy.py` | 2 RED / 7 GREEN |
| `…/cycle273e/test_cycle273e_ast_tick_buy_skip_constant.py` | `tests/unit/ast/test_cycle273e_ast_tick_buy_skip_constant.py` | 4 RED / 2 GREEN |
| `…/cycle273e/test_cycle273e_real_call_paths_contract_flip.py` | `tests/unit/engine/test_cycle268_tester_real_call_paths.py` ⚠️ **신규 파일 아님 — 그 파일 안의 `test_real_risk_on_tick_yields_caller_on_tick` 을 교체**(헬퍼 사본은 삭제하고 기존 것 사용, 경로 A 테스트는 그대로 둔다) | 1 RED / 0 |
| **합계** | | **7 RED / 9 GREEN** |

GREEN 9건은 전부 **계약·위치 가드**다 — 오늘도 초록이지만 Green 구현이 잘못된 자리에
skip 을 넣으면 **붉어지는 것이 목적**이다(뮤테이션 P1/P5/P7/P8).

### 8.2 8영역 sha 핀
`src/engine/risk.py` = 8영역. **4곳 전부**에 같은 값으로 등록 → 커밋 → **후속 커밋으로 비움**:

| # | 파일 | 변수 |
|---|---|---|
| 1 | `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` | `_APPROVED_CONTENT_SHA` |
| 2 | `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` | `_PREEXISTING_CONTENT_SHA` |
| 3 | `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` | `_PREEXISTING_CONTENT_SHA` |
| 4 | `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` | `_ALLOWED_CONTENT_SHA` |

⚠️ 같은 파일의 `test_ga3_6`(**파일명** 허용 `_ALLOWED = {"src/engine/risk.py", "src/realtime/handler.py"}`)
과 `_APPROVED_CONTENT_SHA`(**내용** 핀)는 **다른 가드**다 — 핀은 4곳이 맞다(자문 §5.4 가 U-B §5.3 의 "3곳" 표기를 정정).

### 8.3 배포
모드 **full**. 창 = 15:30~19:55 / 20:20~익일 07:45 / 주말·공휴일. **20:00~20:15 금지.**
보유 중 KRX 메인 push 금지(D6). 배포일은 §3 표(cycle272 D+1 판독 이후).

---

## 9. Open questions (team-leader/사용자 결정 — 재해석 금지)

| # | 질문 | 권고 |
|---|---|---|
| **O-E1** | `test_real_risk_on_tick_yields_caller_on_tick`(docstring "삭제하지 마라") 처리 방침 | **계약 반전 재작성**(자문 §5.1, tdd-engineer 동의). 원저자 의도를 뒤집는 결정이라 승인 필요 |
| **O-E2** | 구현 형태 (가) 리터럴 확장 vs **(나) 명시 상수** | **(나)**. 행위는 동일, 문서·가드 비용만 다르다. 보류 Red 의 R10 은 (나)를 전제한다 — (가) 채택 시 R10 삭제 + R9/R-pos 의 기준선 탐색을 리터럴 기준으로 수정 |
| **O-E3** | `ws_collapse` leaf 필드를 F-3 **앞** 별도 커밋으로 넣는가 | **넣는다**(자문 §3.4 (다)). 행위 0 · 배포 위험 0 · F-3 전후 같은 필드 비교 성립 |
| **O-E4** | 배포일 분리(cycle272 D+1 판독 이후) | **분리**(자문 §3.7) |
| **O-E5** | `risk.py:644` 주석을 §2 세 줄로 대체 | **대체**. 기존 문장은 donchian 에 대한 판단이고 kojiro 에 대해 검증되지 않았다(판독 정정 K-6) |

---

## 10. F-3b (momentum·LTV 익일청산 갭률) — **미착수, 의견만**

사용자는 F-3b 에 답하지 않았다 ⇒ **착수 제안이 아니다.** 자문 §6 의견을 요약한다.

### 10-a. 🔴 momentum 과 LTV 를 한 덩어리로 보면 틀린다 (자문의 핵심 지적)

| | momentum | LTV |
|---|---|---|
| 프리장 매도 가능? | **불가** — `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 비멤버 ⇒ 08:00~09:00 `defer_exit` | **가능** — 화이트리스트 멤버 + `tradable_boards` 에 `pre_nxt` |
| 프리장 시가는 그 전략에게 | **체결 불가능한 참고가** | **실제로 팔 수 있었던 가격** |
| 그 값을 갭 기준으로 쓰는 것은 | **오류** | **정합** |
| 트레일링 앵커(`high_since_buy = today_open`) | 해당 없음 | **정합** |

> "내가 팔 수 있었던 가격이면 그게 오늘의 시작가다. 못 파는 가격이면 그건 남의 시장 가격일 뿐이다."

⇒ **F-3b 의 실질 범위는 momentum 한 전략이고, LTV 는 범위에서 뺀다.**

### 10-b. momentum 도 "오염" 이 아니라 **설계 질문**이다

08:00 `_execute_next_day_clear` 가 같은 식으로 먼저 판정하고, `gap < 10` 이면 즉시 매도가
아니라 `_pending_next_day_clear` 보류 → **09:00:05 `_drain` 에서 KRX 시장가 청산**이다.
그리고 `open_price` 는 일-스코프 상수라 MAIN `on_tick` 재판정은 **항상 같은 답**을 낸다
⇒ 08:00 판정과 MAIN 재판정은 "2차 방어" 가 아니라 **중복**이다. 다만 `_drain` 이 실패·보류한
종목에게는 그것이 유일한 재시도 경로라 **닫으면 안 된다**. 닫는 대신 기준값을 고치는 쪽이 맞다.

> 진짜 질문 = **momentum 익일청산 갭 판정의 기준가는 "오늘 첫 가격(NXT 프리장 시가)" 인가,
> "그 결정이 실제로 체결될 가격(KRX 09:00 시가)" 인가?** — 트레이더 답은 **후자**.

한 가지 위안 — 08:00 에 시가 미수신이면 `[next_day_clear_deferred] reason=nxt_open_missing`
로 보류되고 MAIN 에서 KRX 시가로 판정된다. **오염이 무는 것은 "프리장 체결이 있었던 종목" 뿐이다.**

### 10-c. 착수 권고 — **지금은 하지 않는다. 관측 선행.**

임계 10.0% 는 오염 크기(중앙값 0.97%p, 95퍼센타일 ≈3%p)의 **10배 거리**다. 뒤집히려면
진짜 갭이 **[10%, 13%]** 구간에 있어야 하는데 그 base rate 를 아무도 모른다.
익일청산 대상은 전일 급등주라 10%+ 갭이 드물지 않을 **가능성**이 있고, 그러면 우선순위가
올라간다. 반대로 희박하면 F-2 를 기다리는 게 맞다. **어느 쪽인지 모르는 상태에서 8영역·전략
파일을 여는 것은 kojiro 때 우리가 안 했던 일이다.**

권고 = `[next_day_gap_observe]` shadow 관측 선행(F-3 배포 이후 별도 사이클) →
**최소 20 이벤트 또는 4주 중 더 긴 쪽** → 그 다음 설계 결정.
마커 형태(제안) = momentum·LTV 익일 분기 진입 시 1회/ticker/일(`KstDailyEmitCap`),
필드 `arg_open`·`buy_price`·`gap_rate`·`threshold`·`verdict(clear|trailing)`·`strategy`,
KRX 확정 시가 대조는 **hot path 밖**(cycle264 `[open_source_compare]` 형태, 09:05:30 백그라운드
leaf, 실패도 `reason=` 로 행을 남긴다 — 못 받은 종목이야말로 오염 확률이 높은 코호트다).

**F-3 도 cycle272 도 F-3b 를 닫지 않는다** — 청산 분기는 `risk.py:595` 로 skip(`:646`)보다 **앞**이고,
cycle272 는 `check_*_signal` 호출 인자 byte 동일을 검증 항목으로 못박았다.
