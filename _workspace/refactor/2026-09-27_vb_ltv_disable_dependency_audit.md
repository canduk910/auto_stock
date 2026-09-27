# VB·LTV 비중 0 퇴출 — 딸린 경로 전수 감사 (2026-09-27)

> 역할: refactor-expert, 감사만 한다(코드·설정·DB 무변경). 사용자 결정(09-27): 「퇴출은 비중을 0으로 줄이는 방식. 모멘텀은 보류하고 유지」
> → 대상은 `volatility_breakout`(VB)·`long_tail_volatility`(LTV) 둘이다. 코드와 DB 행은 그대로 두고 `weight=0 ⇒ enabled=False` 만 바뀐다.
>
> 표기: **[실측]** = 운영 DB·로그를 읽기 전용으로 조회 · **[코드]** = HEAD `d644ea6`(EC2 `.deployed_sha` 와 같다) 읽기 · **[추론]** = 코드에서 유도했고 아직 재지 않았다.
> 줄 번호는 HEAD 기준이다. 작업 트리에 다른 에이전트의 미커밋 편집(cycle380 ETF 판정)이 VB `:447~` · LTV `:518~` 에 있지만 여기서 인용한 줄보다 뒤라 번호가 어긋나지 않는다.

---

## 0. 결론

1. **비중 0 만으로 퇴출해도 안전하다. 필수 코드 수정은 없다.** 전제는 셋이다. 보유 0, 장 밖에서 실행, SQL 이 아니라 API(`PUT /api/strategies/weights`)로 바꾼다. 셋 다 지금 충족된다. 오늘은 일요일이고 VB·LTV 보유·미체결·익일청산 예약이 전부 0 이다 **[실측]**.
2. 매매 경로(손절·익일청산·15:20 청산·시가 확정·구독·매수 평가·AI 자문)는 전부 `enabled` 로 걸러진다. 꺼지면 조용히 빠진다 **[코드]**.
3. **꺼도 계속 도는 것이 세 가지 있다.** 셋 다 매매 위험은 없고 비용만 남는다.
   - 매일 두 번(부팅 +600초 레거시 재준비, 21:00 저녁 미리보기) VB·LTV `prepare` 가 돈다. `registry.all()` 을 쓰기 때문이고, cycle364 설계가 의도한 동작이다.
   - 그렇게 채워진 `_targets` 를 대상으로 09:00:35 REST 시가 확보가 **80~120콜** 을 계속 쏜다. `open_price_rest.select_strategies` 가 `enabled` 를 일부러 보지 않는다(D-9).
   - 같은 준비가 `ticker_prev_close` 를 채운다. 그래서 관리·단기과열 매수차단(cycle369) 조회 대상이 줄지 않는다.
4. **화면과 로그 몇 곳이 꺼진 전략을 켜진 것처럼 보인다.** 대시보드 탭, ScanMonitor 목표가 표, 깔때기 스냅샷, 구독 로그의 `vb=`·`ltv=` 숫자가 그렇다. `daily_performance` 에는 VB·LTV 행이 자산이 멈춘 채로 매일 쌓인다. 행을 합산하면 순자산이 약 10% 부풀려진다.
5. **모멘텀은 VB·LTV 에 기대지 않는다.** 깔때기 기록이 있는 07-13~09-23 구간에서 모멘텀 매수 9건 중 VB·LTV 후보에만 있던 종목은 **0건** 이다 **[실측]**. 부팅 복구의 「주인 모를 보유 → momentum」 기본값도 모멘텀이 켜져 있으니 안전하다.
6. 장중에 실행하면 두 가지 틈이 열린다.
   - 체결 대기 중인 매수를 비중 0 가드가 보지 않는다. 그 체결은 꺼진 전략에 등록돼 아무도 손절을 보지 않는다.
   - 같은 날 비중을 한 번 더 바꾸면 전략 예산이 약 10% 부풀려진다.
   - 둘 다 **주말이나 21:35~07:44 에 실행하면 생기지 않는다.**
7. 지금 VB·LTV 에서 사라지는 표본: AI 매수평가(LLM shadow) 표본의 **60%**(35건 중 21건, 09-14 이후) **[실측]**.
8. 되돌리기는 비중을 다시 올리는 PUT 한 번이다. 다음 부팅부터 정상으로 돈다. `max_lot_ratio_mult=1.0`(09-25 D6③)은 그대로 남아 있으니 되살릴 때 따로 정한다.

---

## 1. 출발 사실 [실측, 2026-09-27 조회]

| 항목 | 값 |
|---|---|
| `strategy_config` 비중 | kojiro 0.40 · BFB/donchian/VCP 각 0.15 · momentum/VB/LTV 각 0.05 (Σ 1.00, 전부 `enabled=True`) |
| `tradable_boards`(DB) | **7전략 전부 `['main']`**. LTV 도 이미 `main` 단독이라 프리장 NXT 매수 창은 **지금도 꺼져 있다**. 과제 목록의 「프리장 NXT 매수 창」은 퇴출과 무관하다 |
| VB·LTV `max_lot_ratio_mult` | 1.0 (둘 다) · `open_price_scope_mode` = `enforce` (둘 다) · `exchange` = KRX |
| `positions` 행 | BFB 3 · donchian 3 · kojiro 4 · momentum 2 · **VB 0 · LTV 0** |
| `trade_history` PENDING/PARTIAL (30일) | momentum 1건(09-15)뿐. **VB·LTV 0** |
| `pending_next_day_clear` | 0행 |
| VB·LTV 마지막 체결 | VB 09-23 15:20 · LTV 09-22 15:20 (둘 다 15:20 일괄청산) |
| 마지막 영업일 순자산 | 4,981,063원 (09-23 07:45 부팅 로그 `[cash_usage_ratio]`) |
| EC2 배포본 | `d644ea6` = 로컬 HEAD |
| 선례 | VB·LTV 는 09-10 17:07 에 한 번 `enabled=False weight=0` 이었다가 되살아났다(`_workspace/red/cycle272_rest_open_basis_spec.md:337`). D-9(꺼진 전략도 REST 스윕)가 그때 만든 예외다 |

---

## 2. 스위치 하나가 바꾸는 것

- `registry.update_weights` 가 `config.enabled = weight > 0` 을 세운다(`src/engine/strategy_registry.py:47-60`). `save_weights` 도 DB 에 `enabled = weight > 0` 을 쓴다(`src/db/strategy_config.py:62-72`). 파라미터는 그대로다.
- 다음 재시작에 `_load_strategy_config` 가 그 행을 읽어 `enabled=False` 로 복원한다(`src/engine/scheduler.py:432-458`).
- 코드가 전략을 고르는 방식은 두 가지다.
  - **`registry.enabled()`** — 꺼진 전략이 빠진다. 매수·청산 평가(`risk.py:642`), 부팅 준비(`boot_manager.py:262-263`), 자금 배분(`strategy_registry.py:36-45`), AI 자문(`recommendation_engine.py:415,430`), 매수차단 후보(`status_exit_watch.py:452`)가 여기에 속한다.
  - **`registry.all()`** — 꺼진 전략도 포함한다. 대부분 **보유 종목**만 모으는 곳이라(구독 HIGH, 손절 보호, 정리 대상 보호) 보유 0 인 VB·LTV 에는 영향이 없다. 예외는 §4 의 F1·F2·F6·F7 이다.
  - 이름으로 직접 부르는 곳(`("volatility_breakout", "long_tail_volatility")` 튜플)은 하나를 빼고 전부 `config.enabled` 를 직접 확인한다. 빠진 하나가 `open_price_rest` 다(F2).

---

## 3. 딸린 경로 전수표

분류: **무해**(아무 일 없음 또는 오히려 줄어듦) · **낭비·안전**(돌지만 매매 영향 0) · **설정**(설정 변경이 필요하거나 권장) · **코드**(코드 없이는 못 막음) · **절차**(실행 시점·방법으로 피함)

### 3.1 매매 경로

| 경로 | 위치 | 꺼졌을 때 | 비용·영향 | 분류 |
|---|---|---|---|---|
| 틱 매수·청산 평가 | `risk.py:642` (`enabled()` 단일 순회) | VB·LTV 평가 0 | 보유 0 이라 손절 공백 없음. 틱당 순회 7→5 | 무해 |
| 부팅 준비 | `boot_manager.py:262-263` | VB·LTV 준비 안 함 | — | 무해 |
| 07:59 재준비(유니버스 빈 경우) | `scheduler.py:779-787` | `enabled` 확인으로 건너뜀 | BFB·VCP 후보가 있으면 애초에 안 탄다 | 무해 |
| 08:00 프리 · 09:00:05 · 15:40 시가 확정 | `scheduler.py:1671-1679` | `enabled` 확인으로 대상 0 | WS 폴링·REST 폴백 0 | 무해 |
| 09:05 이후 시가 재시도 | `scheduler.py:2624-2627` | 건너뜀 | — | 무해 |
| 5분 빈 후보 재준비 | `scheduler.py:2665-2669` | 건너뜀 | — | 무해 |
| 익일 청산 | `scheduler.py:1387-1392`(`enabled` 전략만 수집) · LTV 분기 `:1529` | 대상 제외 | 보유 0 이라 무해. **보유가 있는 채로 꺼지면 이 경로가 그 보유를 버린다**(F5) | 무해(전제: 보유 0) |
| VB 15:20 일괄청산 | `scheduler.py:2038-2041` | 건너뜀 | 위와 같은 전제 | 무해(전제: 보유 0) |
| 19:50 매수 중단 | `scheduler.py:905` | 대상 제외 | — | 무해 |
| 프리장 청산 평가 보류 예외(LTV) | `risk.py:79` `_PRE_MARKET_EXIT_EVAL_STRATEGIES` | LTV 보유 0 이라 발동 대상 없음 | 되살리면 그대로 다시 작동 | 무해 |
| 당일 고가 앵커 예외(LTV) | `risk.py:232` | 보유 없음 | — | 무해 |
| 매수 체결 등록 | `order_engine.py:2629` (`registry.get`, `enabled` 확인 없음) | 꺼진 전략에도 등록된다 | **장중에 끄는데 VB 매수가 체결 대기 중이면 그 포지션은 고아가 된다**(F5) | 절차 |
| 부팅 포지션 복구 | `boot_manager.py:293` (`get(sid) or momentum`) | DB 행이 VB 면 꺼진 VB 에 붙는다 | 지금 VB·LTV 행 0 → 무해. SQL 로 끄면 이 경로가 열린다(F5) | 절차 |
| 주인 모를 보유 → momentum | `boot_manager.py:293,444` · `order_engine.py:2622` | momentum 이 켜져 있어 안전 | **momentum 을 남기는 결정이 이 경로를 지킨다** | 무해 |
| 관리·단기과열 보유 청산 | `status_exit_watch.py:663-665` (`all()`) | 꺼진 전략 보유도 본다 | 보유 0 → 대상 없음 | 무해 |
| 체결 0 매수 회수(cycle379) | `buying_reconcile.py:221,249` (`all()`) | 꺼진 전략 pending 도 정리 | 오히려 안전망 | 무해 |
| 매도 후 구독 정리 건너뛰기 | `order_engine.py:2466-2477` (`all()` 의 `get_scanned_tickers`) | 꺼진 VB·LTV 의 준비 목록에 있는 종목은 매도 뒤 구독 해제를 건너뛴다 | 슬롯 하나가 다음 5분 구독 갱신까지 남는다 [추론] | 낭비·안전 |

### 3.2 준비·시세·REST

| 경로 | 위치 | 꺼졌을 때 | 비용·영향 | 분류 |
|---|---|---|---|---|
| **부팅 +600초 레거시 재준비** | `funnel_capture.py:242-243` (`list(registry.all())`) · 호출 `data_load_tasks.py:306` | **VB·LTV 도 `prepare()` 한다** | 09-23 실측: 07:56 에 7전략 전부 재준비. VB 약 4초 · LTV 약 0.5초. 대부분 DB 읽기(일봉 DB 우선, KIS 폴백 횟수는 DEBUG 로그라 잴 수 없다) | 낭비·안전(F1) |
| **21:00 저녁 미리보기** | `funnel_capture.py:316` (`_ordered(registry.all())`, 꺼진 전략은 뒤로) | VB·LTV 도 다음 거래일 기준으로 준비 | 설계 의도다 — `cycle364_a1_as_of_design.md:159` 「비활성 전략의 funnel 도 계속 채운다」. 테스트가 순서를 고정한다(`test_cycle364_evening_capture.py:583-592`) | 낭비·안전(F1) |
| **09:00:35 REST 시가 확보** | `open_price_rest.py:374-397` `select_strategies` — **`config.enabled` 를 보지 않는다**(D-9, 테스트 `test_cycle272_open_price_rest_leaf.py:402` 가 고정) | F1 이 채운 `_targets` 로 계속 스윕한다 | 켜져 있던 날 실측: R1 **120콜(09-22) · 79콜(09-23)**, 9.3초. 로그 INFO `[main_rest_basis_round]` 38행/일 + `[main_rest_basis_confirmed]` 98~149행/일. 꺼진 뒤에도 같다고 본다 [추론] | 낭비·안전 → 설정으로 끌 수 있음(F2) |
| 09:05:30 시가 3자 대조 | `open_price_observe.py:177-183, 207-209` | `enabled` 확인으로 대상 0. 90초 기다린 뒤 `skipped reason=no_confirmed_target` INFO 1행/일 | REST 0 | 무해 |
| WS 구독 — 돌파 그룹 | `scheduler.py:1826-1829` (`enabled` 확인) | VB·LTV 후보 구독 제외 | 09-23 실측: 총 116~125 중 `vb=61, ltv=37`(겹침 포함), 세션 8개에 10~17개씩. 빠지면 대략 절반으로 줄어든다 [추론] → 틱 처리 CPU 감소 | 무해(오히려 가벼워짐). 관찰 항목 1개(F8) |
| 구독 출처 로그 | `scheduler.py:1889-1900` (`registry.get`, `enabled` 확인 없음) | F1 이 채운 목록 크기를 `vb=`·`ltv=` 로 계속 찍는다 | 실제로는 구독하지 않는데 숫자가 남는다. 관측이 거짓말을 한다 | 낭비·안전(F6) |
| `ticker_prev_close` 채움 | VB `volatility_breakout.py:387-391` · LTV `long_tail_volatility.py:440-445`. 21:30 `scheduler.py:3695` 에서 비움 | F1 준비 때 계속 채운다 | 아래 두 줄의 원인 | — |
| 모멘텀 매수 평가 | `momentum.py:153` (`ticker_prev_close` 로 등락률 계산) | 구독된 종목만 틱이 오므로 VB·LTV 후보 종목은 모멘텀 평가에서도 빠진다 | 실측: 모멘텀 매수 60건 중 09:30 전 2건. 깔때기 기록 구간(07-13~) 9건 중 VB·LTV 후보에만 있던 종목 **0건** | 무해 |
| 관리·단기과열 매수차단 후보(cycle369) | `status_exit_watch.py:441-495` — momentum 이 켜져 있으면 `ticker_prev_close` 전체를 momentum 그룹(0)으로 넣는다(`:470-474`) | F1 이 채운 VB·LTV 후보(최대 약 100)가 그룹 1 에서 그룹 0 으로 옮겨 **그대로 조회된다** | 조회 수는 줄지 않는다. cycle369 은 09-26 커밋이라 영업일 실측이 아직 없다 [추론] | 낭비·안전(F3) |
| P0 시각(프리장 전략이 있으면 07:59) | `status_exit_watch.py:552-563` | DB 보드가 전부 `main` 이라 이미 08:45 | 변화 없음 | 무해 |
| 공유 채널·VI·stale 감시·TLS 등 | `tick_channel_switch.py:146` · `market_op_subscribe.py:83` · `stale_watcher_core.py:89,468,808` · `stale_diagnostics.py:264` · `data_load_tasks.py:327` | 전부 **보유** 종목만 모은다 | 보유 0 → 영향 없음 | 무해 |

### 3.3 관측·정산·보고

| 경로 | 위치 | 꺼졌을 때 | 비용·영향 | 분류 |
|---|---|---|---|---|
| 09:30 확정 깔때기 캡처 | `scheduler.py:243` (`registry.all()` + `capture_skip_reason`) | F1 레거시 준비의 meta(`as_of`=오늘, ok)가 통과해 **VB·LTV 깔때기 행이 계속 저장된다** | 화면 「전략 깔때기」가 꺼진 전략을 산 것처럼 보여 준다. 되살릴 때 참고 자료로는 쓸모가 있다 | 낭비·안전(F6) |
| 21:30 정산 `daily_performance` | `scheduler.py:3538-3565` (`all()`) | 꺼진 전략의 `total_investment=0` → 직전 `total_asset` 으로 대체해 **손익 0, 자산 고정 행을 매일 쓴다** | VB 250,553 · LTV 249,053 (09-23 값)이 멈춘 채 쌓인다. 전략 행을 합산하면 순자산이 약 50만(+10%) 부풀려진다. 비중으로 나눠 검산하면 0 으로 나누게 된다 | 낭비·안전(F7, 측정 함정) |
| 20:05·21:30 지표(funnel 합계) | `log_metrics_collector.py:677` (`all()`) | VB·LTV 행이 0 으로 나온다 | 21:30 분석·20:20 클라우드 루틴이 「VB·LTV 신호 0」을 이상으로 볼 수 있다 [추론] | 무해 |
| 부팅 관찰(param_drift·예산 불변식) | `boot_manager.py:160,178` (`all()`) | 꺼진 전략도 관찰 로그에 들어간다 | 로그 몇 행 | 무해 |
| 대시보드 상태 합계 | `scheduler.py:1294-1310` (`all()` 의 `total_investment` 합) | 같은 날 두 번째 비중 변경 뒤에는 부풀려진다(F4) | 표시 | 절차 |
| `min_weight`·Settings 가용금액 추정 | `strategy_registry.py:104` · `Settings.tsx:101-104` | 위와 같다 | 표시 | 절차 |

### 3.4 AI·LLM·백테스트

| 경로 | 위치 | 꺼졌을 때 | 비용·영향 | 분류 |
|---|---|---|---|---|
| 20:00 AI 자문 | `recommendation_engine.py:415,430` (`enabled()`) | VB·LTV 자문 생성 0. peer 비중에서도 빠진다 | LLM 호출이 하루 2건 준다. 비중 합을 0.90 으로 두면 AI 가 받는 peer 비중 합도 0.90 이다 — Σ=1.00 으로 저장하길 권한다(§6) | 무해(설정 권장) |
| 자문 자동 적용 | `recommendation_engine.py:551-640` (감액만, 50% 하한) | VB·LTV 추천 자체가 없다. 증액은 자동 적용이 원래 안 한다 → **자동으로 되살아나지 않는다** | — | 무해 |
| AI 매수평가 게이트(LLM shadow) | `llm_buy_gate.py:285-287, 390-396, 482-483` · `llm_features.py:494-510` | 매수 순간에만 불리므로 0 | **표본 손실**: 09-14 이후 35건 중 VB 8 + LTV 13 = 60% | 무해(연구 표본만 준다) |
| 백테스트 | `backtest_orchestration.py:46-55` · `backtest_yaml.py:65-110` | 자문 대상만 넣는다. 게다가 `kis_mcp_enabled=false` | 0 | 무해 |
| 파라미터 카탈로그·PUT params | `param_catalog.py` 여러 곳 · `routes/strategies.py:351-397` | 꺼진 전략도 파라미터 저장 가능. `save_params` 가 기존 `enabled/weight` 를 유지한다(`strategy_config.py:74-84`) → 파라미터를 바꿔도 켜지지 않는다 | — | 무해 |
| 상태 게이트 후보 상수 | `strategy_base.py:45` | `check_buy_signal` 안에서만 쓴다 | — | 무해 |

### 3.5 프론트

| 화면 | 위치 | 꺼졌을 때 | 분류 |
|---|---|---|---|
| 대시보드 전략 탭 | `Dashboard.tsx:79-99` (전 전략, 비활성 표시 없음) | VB·LTV 탭이 그대로 보인다 | 낭비·안전 |
| ScanMonitor 목표가 표·깔때기 | `ScanMonitor.tsx:273-281, 313` | F1 이 채운 목록과 REST 로 확정된 목표가를 **켜진 것처럼** 보여 준다 | 낭비·안전(F6) |
| 설정 — 비중 | `Settings.tsx:123-135`(저장 시 전 키를 Σ=1 로 정규화) · `:96, 194-201`(Σ≠1 이면 붉은 배너) · `:493`(「비활성」 배지) | 설정 화면으로 저장하면 자동으로 Σ=1.00 이 된다. API 로 일부만 보내면 Σ=0.90 배너가 뜬다 | 설정 |
| 전략 깔때기 페이지 | `StrategyFunnel.tsx:31-32` | 계속 행이 쌓인다(F6) | 낭비·안전 |

---

## 4. 자세히 볼 발견

**F1. 꺼진 전략도 하루 두 번 준비된다** [코드 + 실측]
- 레거시 재준비(`funnel_capture.py:242-243`)와 21:00 저녁 미리보기(`:316`)가 `registry.all()` 을 돈다.
- 09-22·09-23 실측: 07:56 레거시 재준비가 `prepared=7` 로 7전략을 모두 준비했다(`[evening_funnel_capture_summary] prepared=7 saved=59`).
- 저녁 미리보기에 꺼진 전략을 넣는 것은 설계 문서 `cycle364_a1_as_of_design.md:159` 가 정했다. 되살리기 판단에 쓸 후보 기록을 남기려는 것이다. 이 자체를 고치라고 권하지 않는다.
- 문제는 이 준비가 **살아 있는 경로 두 곳에 흘러든다**는 것이다(F2·F3).

**F2. REST 시가 확보가 꺼진 VB·LTV 를 위해 매일 80~120콜을 쏜다** [코드 + 실측 + 추론]
- `select_strategies`(`open_price_rest.py:374-397`)는 D-9 에 따라 `enabled` 를 보지 않는다.
- D-9 의 목적은 「09-10 VB·LTV 가 꺼진 동안에도 금요일에 스윕을 검증한다」(같은 docstring)였다. cycle272 는 이미 끝났으니 그 목적은 다했다.
- 켜져 있던 날 R1 은 120콜·79콜이었고 09:00:35~09:00:45 에 몰린다. 꺼진 뒤에도 F1 이 `_targets` 와 `_open_confirmed` 를 매일 새로 채우므로 같은 양이 나간다고 본다.
- 매매 위험은 0 이다. 확정된 목표가를 읽는 `check_buy_signal` 이 불리지 않는다.
- **코드 없이 끄는 방법:** VB·LTV 에 `open_price_scope_mode="off"` 를 `PUT /api/strategies/{id}/params` 로 넣는다.
  - `select_strategies` 가 `mode==enforce` 만 고르므로 스윕 대상에서 빠진다.
  - PUT params 는 `enabled` 를 건드리지 않는다.
  - 대가: 되살릴 때 `enforce` 로 되돌리는 단계가 하나 는다. 이것도 파라미터라 **사용자 결정 항목**이다.

**F3. 관리·단기과열 매수차단의 조회 수가 줄지 않는다** [코드, 영업일 실측 없음]
- `buy_targets`(`status_exit_watch.py:441-495`)는 momentum 이 켜져 있으면 `ticker_prev_close` 의 모든 키를 momentum 그룹으로 넣는다.
- F1 준비가 VB·LTV 후보의 전일종가를 채운다. 그래서 그 종목들이 VB·LTV 그룹에서 빠지는 대신 momentum 그룹으로 옮겨 **계속 읽힌다**.
- 켜져 있을 때와 조회 수가 같다. 늘지는 않는다.
- 월요일 `[status_block_pass] kind=p1 ... truncated=` 가 0 이면 문제없다. 1 이면 25초 상한에 걸려 BFB·VCP 후보 조회가 잘린 것이니 그때 카드를 연다.

**F4. 장중에 끄면 같은 날 두 번째 비중 변경이 예산을 약 10% 부풀린다** [코드]
- 라우트가 `total_asset = Σ total_investment`(`routes/strategies.py:312`)를 **모든 전략**에서 더한다.
- `allocate_funds` 는 **켜진 전략**의 예산만 다시 쓴다(`strategy_registry.py:36-45`). 꺼진 VB·LTV 의 `total_investment` 는 옛 값(각 약 24.9만)으로 남는다.
- 그래서 그날 한 번 더 비중을 바꾸면 순자산 약 498만 + 49.8만 = 약 548만을 켜진 전략에 나눠 준다.
- 21:30 `_reset_daily_state` 가 전부 0 으로 되돌리므로(`scheduler.py:3600`) 하루짜리 창이다.
- 주말에는 `Σ total_investment = 0` 이라(라우트 주석 `:228-230`, 09-20 실측) 배분을 아예 건너뛴다. 이 창이 열리지 않는다.
- 제대로 고치려면 `allocate_funds` 가 꺼진 전략을 0 으로 만들어야 한다. 그런데 그 파일이 8영역이다 → 절차로 피한다.

**F5. 비중 0 가드가 보는 것은 「보유」뿐이다** [코드]
- 가드(`routes/strategies.py:284-309`)는 DB `positions` 와 메모리 `positions` 만 확인한다. `pending_buys`(체결 대기 매수)는 보지 않는다.
- 장중에 VB 매수 주문이 나간 직후 비중을 0 으로 내리면 이렇게 된다.
  1. 체결이 `registry.get` 으로 꺼진 VB 에 등록된다(`order_engine.py:2629`).
  2. 손절(`risk.py:642`) · 15:20 청산(`scheduler.py:2038-2041`) · 익일청산(`:1387-1392`)이 전부 그 포지션을 건너뛴다.
- `strategy_config` 를 SQL UPDATE 로 끄면 가드 자체를 우회한다. 다음 재시작에 `boot_manager.py:293` 이 VB 행을 꺼진 VB 에 붙인다.
- 둘 다 **장 밖 + API** 로 하면 생기지 않는다.

**F6. 꺼진 전략이 켜진 것처럼 보이는 자리가 넷 있다** [코드]
- 구독 로그 `vb=`·`ltv=`(`scheduler.py:1889-1900`)
- ScanMonitor 목표가 표
- 09:30·21:00 깔때기 스냅샷
- 대시보드 탭(비활성 표시 없음)
- 매매는 틀리지 않는다. 다만 월요일 로그를 볼 때 `vb=61` 같은 숫자를 「VB 가 아직 구독 중」으로 읽으면 틀린다. **구독 여부는 `total=` 과 `[tick_coverage_session]` 으로 판단한다.**

**F7. `daily_performance` 에 자산이 멈춘 행이 쌓인다 — 측정 함정** [코드 + 실측]
- 정산(`scheduler.py:3538-3565`)이 꺼진 전략에도 매일 행을 쓴다. `total_investment=0` 이면 직전 `total_asset` 을 대체값으로 쓴다.
- VB 250,553 · LTV 249,053 이 고정된 채 쌓인다.
- 메모리의 「`strategy='total'` 합계 행이 섞여 2배」 함정과 같은 계열의 두 번째 함정이다. 전략 행 합 ≠ 순자산.
- 성과 집계에서는 `enabled` 전략만 합치거나 `total` 행을 써야 한다.

**F8. 세션당 구독 수가 줄어 무활동 세션 감지가 판정 불가가 되는 세션이 생길 수 있다** [추론 — 월요일 실측 항목]
- 세션 무활동 감지는 세션당 구독 5개 이상일 때만 판정한다(루트 `CLAUDE.md` 「세션 단위 silent inactive」).
- 09-23 09:35 실측으로 세션 8개에 10~17개씩(최소 44606571 세션 10개)이었다. VB·LTV 후보가 빠지면 대략 절반으로 줄어 일부 세션이 5개 아래로 내려갈 수 있다.
- 그래도 종목 단위 stale watcher(120초)와 5분 재구독, F1 재연결은 그대로라 손절 감시가 끊기지는 않는다.
- 월요일 `[tick_coverage_session]` 의 `sub=` 최솟값을 본다.

**F9. 모멘텀 결합은 실측 0** [실측]
- 모멘텀은 후보 목록 없이 **구독된 아무 종목**에서나 +29% 를 잡는다(`risk.py` 매수 분기, `momentum.py:153`). 그래서 VB·LTV 후보 구독이 모멘텀의 사냥터를 넓혀 줄 수 있었다.
- 실측으로는 그 효과가 없다. 깔때기 기록 구간 매수 9건 중 VB·LTV 후보에만 있던 종목은 0건이다.
- 07-13 이전 51건은 깔때기 기록이 없어 판단하지 못한다.

---

## 5. 비중 0 을 받아 주는 조건 — 라우트 검증 [코드 + 실측]

`PUT /api/strategies/weights`(`routes/strategies.py:251-348`)를 위에서부터 순서대로 통과해야 한다.

1. 각 값이 0.0~1.0 인가 — 모델 검증(`:43-53`). 0 은 통과한다.
2. Σ ≤ 1.001 인가(`:268-282`, `_WEIGHT_SUM_TOLERANCE=1e-3`). Σ<1 인 부분 payload 도 통과한다.
3. **비중 0 가드**(`:284-309`): 0 인 전략마다 DB 보유 ∪ 메모리 보유가 있으면 거부한다. VB·LTV 는 DB 0행, 오늘 메모리도 비었다(주말이라 부팅 전) → **통과**.
4. 매수금액 하한선(`:311-332`): `total_asset > 0` 일 때만 검사한다. 주말은 0 이라 건너뛴다.
5. `registry.update_weights` → VB·LTV `enabled=False`. `total_asset > 0` 이면 즉시 재배분한다(주말엔 안 함). `save_weights` → DB `enabled=false, weight=0`.

결과: **지금(주말) 보내면 받아 준다.** 월요일 07:45 부팅이 `allocate_funds(순자산 × 1.0)` 을 켜진 5전략에만 나눈다.

비율 예시(순자산 4,981,063 기준):

| 저장 방식 | momentum | donchian·BFB·VCP 각 | kojiro |
|---|---|---|---|
| 0.10 을 비례로 흡수(Σ 0.90 그대로 또는 설정 화면 정규화) | 약 276,700 | 약 830,200 | 약 2,213,800 |

어느 쪽이든 켜진 전략의 예산이 ×1.11 로 커진다. K축·ρ축 캡과 kojiro 오픈리스크 상한도 예산에 비례해 같이 커진다. **다른 전략의 랏이 커지는 행위 변화**이고, 비중 배분 자체는 사용자 결정이다.

---

## 6. 안전한 퇴출 절차

| 순서 | 할 일 | 확인 |
|---|---|---|
| 0 | 사전 점검(읽기 전용) | VB·LTV `positions` 0 · `trade_history` PENDING 0 · `pending_next_day_clear` 0. 오늘 셋 다 0 **[실측]** |
| 1 | **시점** = 주말, 또는 영업일 21:35~익일 07:44. 월요일 07:45 부팅 **전**이 가장 깨끗하다 | 이 창에서는 `Σ total_investment = 0`(F4 없음)이고 체결 대기 매수도 없다(F5 없음) |
| 2 | **방법** = 설정 화면의 비중 저장 또는 `PUT /api/strategies/weights`. **SQL UPDATE 금지**(F5 가드 우회). payload 는 7전략 전부, VB=0 · LTV=0 · **Σ=1.00**(설정 화면은 자동). 나머지 배분은 사용자 결정 | 응답 `success=true`. `GET /api/strategies` 에서 VB·LTV `enabled=false weight=0`. DB `strategy_config` 두 행 `enabled=false` |
| 3 | (선택, 사용자 결정) F2 를 끄려면 VB·LTV 에 `open_price_scope_mode="off"` 를 PUT params 로 넣는다 | 응답 `applied`. `enabled` 는 그대로 false |
| 4 | 월요일 라이브 실측(비활성화 심층 검증 의무) | §8 목록 |

하지 말 것:
- **보유가 생긴 뒤에 끄지 않는다.** 가드가 막지만 SQL 은 못 막는다.
- **장중에 끄지 않는다.** F4·F5 때문이다.
- **VB·LTV 코드나 DB 행을 지우지 않는다.** 되살리기가 불가능해지고, 포지션 규약이 momentum 으로 넘어간다(`2026-09-27_strategy_add_remove_structure.md` §4.6).

---

## 7. 되돌리기(다시 켜기)

1. **같은 창**(주말 또는 21:35~07:44)에 VB·LTV 비중을 0 보다 크게 하고 나머지를 줄여 Σ ≤ 1.00 으로 PUT 한다. 메모리 `enabled=True` 는 즉시, 자금 배분·준비는 다음 07:45 부팅부터 적용된다.
2. §6-3 을 했다면 `open_price_scope_mode="enforce"` 를 **먼저** 되돌린다. 안 하면 main 목표가 기준이 REST 확정 없이 남는다.
3. `max_lot_ratio_mult=1.0`(09-25 D6③)은 끄는 동안 그대로 남는다. 켤 때 유지할지 따로 정한다.
4. 장중에 다시 켜면 이렇게 된다 [추론].
   - 준비와 REST 확정은 F1·F2 덕에 이미 돼 있을 수 있다.
   - 구독은 다음 `_scan_loop` 주기(09:30 시작, 5분 간격)에 들어온다. 그 전에는 틱이 없어 매수 평가가 없다.
   - 예산은 `total_asset` 에 꺼진 전략 몫이 0 이라 부풀지 않는다.
5. 코드 되돌림은 없다. 꺼진 동안의 깔때기 행(F6)은 되살릴지 판단하는 자료로 쓸 수 있다.

---

## 8. 월요일(09-28) 확인 목록

| 시각 | 볼 것 | 기대 |
|---|---|---|
| 07:45 | `DB 전략 설정 로드: volatility_breakout (enabled=False, weight=0%)` · LTV 같음 | 두 행 |
| 07:45 | `자금 분배:` 행 | **5행**(VB·LTV 없음). `[weight_config_anomaly]` 없음 |
| 07:56 | `[evening_funnel_capture_summary] prepared=` | 7(F1 — 정상, 설계 의도) |
| 07:59·09:30 | `실시간 시세 구독 완료: total=` | 09-23 의 116~125 보다 뚜렷이 작다. **`vb=`·`ltv=` 숫자는 무시**(F6) |
| 09:00:44 | `[main_rest_basis_round] round=1/19 ... calls=` | §6-3 을 안 했으면 80~120(F2), 했으면 행 없음 |
| 09:00:30 | `[status_block_pass] kind=p1 ... truncated=` | 0(F3) |
| 09:35 | `[tick_coverage_session]` 세션별 `sub=` 최솟값 | 5 이상인지(F8) |
| 종일 | `trade_history` 에 VB·LTV 행 | 0 |
| 20:00 | AI 자문 행 | 5전략(VB·LTV 없음) |
| 21:30 | `daily_performance` VB·LTV 행 | 손익 0 · 자산 고정(F7 — 정상, 합산 금지) |

---

## 9. 코드 카드 후보 — 전부 선택이다(퇴출에 필수 아님)

| # | 의도 | 위치 | 등급 | 효과(0계명 순) | 판단 |
|---|---|---|---|---|---|
| 1 | 비중 0 가드가 `pending_buys` 도 본다 | `routes/strategies.py:284-309` (8영역 아님) | LOW | 장중 퇴출 틈(F5) 하나를 막는다. 회귀 가드: 기존 cycle325 가드 테스트 + 신규 1(pending 만 있을 때 거부) | 절차로 피할 수 있다 → **보류** |
| 2 | REST 스윕에 `enabled` 게이트(D-9 해제) | `open_price_rest.py:374-397` + 테스트 `test_cycle272_open_price_rest_leaf.py:402` 반전 | LOW~MEDIUM | 하루 80~120콜 절감. 같은 효과를 §6-3 설정으로 코드 없이 얻는다 | **비권고** — 설정이 먼저 |
| 3 | `allocate_funds` 가 꺼진 전략 예산을 0 으로 | `strategy_registry.py:36-45` (**8영역**) | MEDIUM | F4 를 뿌리에서 막는다 | 8영역 승인 대상이고 절차로 피한다 → **보류** |
| 4 | 구독 출처 로그 `vb`·`ltv` 에 `enabled` 게이트 | `scheduler.py:1889-1900` (라인 상한 승인 대상) | LOW | 관측 거짓말 하나(F6)를 없앤다 | 표시 문제뿐 → **비권고** |
| 5 | `buy_targets` momentum 그룹에서 꺼진 전략의 전일종가 제외 | `status_exit_watch.py:470-474` | MEDIUM | F3 조회 절감 | `ticker_prev_close` 는 출처를 모른다(모멘텀 스캔도 같은 dict 에 쓴다). 월요일 `truncated=1` 이 나오기 전에는 **비권고** |

HIGH 카드는 없다. 켜진 전략의 매매 행위를 바꾸는 카드가 없으므로 domain-expert 행위 영향 평가는 붙이지 않았다.

## 10. 비권고 — 검토했으나 권하지 않음

- **저녁 미리보기·레거시 재준비를 `enabled()` 로 좁히기.** 꺼진 전략의 후보 기록은 cycle364 가 의도한 산출물이다. 레거시 분기는 S2 가 없애기로 돼 있다(`funnel_capture.py` docstring S1/S2 경계).
- **대시보드 탭·ScanMonitor 에 비활성 표시 추가.** 표시 문제뿐이고 설정 화면이 이미 「비활성」 배지를 단다. 같은 요구가 한 번 더 나오면 연다.
- **VB·LTV 전용 상수 정리**(`risk.py:79,232` · `session.py:76-83` · `status_exit_watch.py:75-79` · `open_price_rest.py:82` · `open_price_observe.py:101` 등). 비중 0 은 되돌릴 수 있는 퇴출이라 딸린 코드가 살아 있어야 되살릴 수 있다. 코드를 지우는 결정이 날 때 `2026-09-27_strategy_add_remove_structure.md` 카드들과 함께 본다.
- **LTV 프리장 설정 정리.** DB `tradable_boards` 가 이미 `['main']` 이라 정리할 것이 없다.

---

조회 스크립트(읽기 전용, `SET default_transaction_read_only = on`)는 세션 scratchpad 에 있고 리포에는 남기지 않았다.
