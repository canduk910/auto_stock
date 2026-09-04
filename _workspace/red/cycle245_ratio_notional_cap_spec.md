# cycle245 — 비터틀 전략 랏 명목 상한 ρ축 `max_lot_ratio_mult`(K_ρ=2.5) (09-04 장중 검토 §5 · cycle242 후속 D)

작성: team-leader, 2026-09-04. 사용자 결정("K=2.0 유지하고 cycle245 도 진행해줘" — cycle242 의 터틀 K 는 2.0 그대로 두고,
비터틀 전략의 ρ축 상한을 별도 사이클로 진행). domain-consult(`_workspace/domain_consult/cycle245_ratio_notional_cap.md`)
+ 3렌즈 진단(path·evidence·risk_profile) + **코드 재실측 + 캡 시뮬레이션 전수 실행** 후 확정.
**진단·자문의 전제 정정 4건**은 §0 하단 — 그중 ①(설계 축이 자문안대로면 cycle242 테스트 4건이 깨진다)은 tdd-engineer 착수 전 반드시 읽을 것.

> **워킹트리 상태**: HEAD `3759ddd`. 미푸시 커밋 3(cycle243 `233b663` · CI hotfix `9ce1d9e` · 문서 `3759ddd`) + `_workspace/review_0904_intraday.md` 수정(사전 존재) + untracked `_workspace/domain_consult/cycle245_ratio_notional_cap.md`(본 사이클 입력 자문).
> **git commit / push / stash / checkout / restore 금지.** 배포는 `strategy_base.py` 변경 = 백엔드 재시작 동반이라 **15:30 이후**(cycle232 D6) — 이 워크플로는 커밋하지 않는다.

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py · strategy_registry.py)
> + **scheduler.py 무접촉** + **boot_manager.py 무접촉**. src 변경 = **`src/engine/strategy_base.py`(주)** + **7 전략 파일의 `DEFAULT_PARAMS` 1키 추가만**.
> `turtle_sizing.py` diff 0 · `portfolio_risk.py` diff 0 · **cycle242 `_apply_lot_units_cap` 계열 diff 0**(`_emit_oversized_fallback` 은 docstring 만).

---

## 0. 결정 요약 (착수 질문 ①~⑬)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | 파라미터 이름·기본값 | **`max_lot_ratio_mult` = 2.5**(float, "랏 명목의 `position_ratio` 배수 상한"). 자문 §2.3 채택 | 이름은 cycle242 `max_lot_units`(ATR 유닛 축)와 **grep 으로 갈린다**(`fallback` vs `ratio` 접두 마커도 동일). 값 2.5 = 자문의 정책 축 3개(순자산 노출 ≤10% · 실적 차단 ≤1/4 · 리스크 척도 환산)가 모두 가리키는 구간 [2.5, 3.0] 의 **하단**(안전 방향). ⚠️ **P&L 로 K 를 정하지 않았다** — 자문 §2.2 의 뷰 3개가 서로 다른 K 를 가리켜(LTV 최적이 뷰 D 3.0 / 뷰 B 2.0 / 뷰 C 1.0~2.0) 사후 최적화가 되기 때문 |
| ② | 전략별 차등 | **없음 — 비터틀 전수 균일** | 자문 §2.4: (a) 차등 근거가 LTV 밖에 없다(VB 는 K≥2.5 에서 차단 0, momentum 은 표본 2건) (b) 리스크 정체성 상수가 전략마다 생겨 튜닝 표면적 5배 (c) **진짜 차등은 이미 `weight × position_ratio` 축에 있다**(순자산 대비 VB 5.25% / BFB 3.75% / LTV·VCP 2.00% / MOM 1.25%) — 그 차등이 의도된 것이면 K 는 균일해야 정합. **청산 규약(당일/오버나잇) 근거 차등은 기각** — momentum 은 `check_force_clear` 자체가 없어 구조적 오버나잇이고(코드 실측), LTV 15:20 청산은 `_limit_up_reached` 무영속으로 새며(08-31 161890 실증), VB 오버나잇 0 은 DB `tradable_boards` 한 줄에 의존한다 |
| ③ | 척도 | **ρ축 = `position_ratio × 예산` 명목(원)**. `cutoff = int(K_ρ × int(예산 × position_ratio))`, `cap_qty = cutoff // 현재가`, `final = min(final, cap_qty)` | 비터틀 5전략은 `risk_pct`·진입 ATR 스탬프·`_candidates` 가 **소스에 한 건도 없어**(grep 0 — 렌즈1) ATR 축이 원리적으로 불가. `cap = int(예산×ratio)` 는 `_emit_oversized_fallback`(cycle233) · `portfolio_risk.compute_over_cap_positions` 와 **같은 산식** — 세 번째 복제가 아니라 이미 두 곳이 재고 있는 축에 행위를 얹는 것이고, 그래야 §7 R7 자기검증 불변식(`[oversized_fallback] ratio` ≤ K_ρ)이 성립한다 |
| ④ | 차단 vs 축소 vs 유니버스 | **진입 차단(0주)** — 축소는 원리적으로 불가 | K_ρ ≥ 1 이면 캡은 **`_fallback_one_share` 에서만 바인딩**된다(주 분기 `int(예산×ratio)//price` 는 정의상 notional ≤ ρ상한, 터틀 분기 `compute_unit_qty_guarded` 는 같은 상한을 무조건 적용). 그 경로의 수량은 **항상 1** — 실측 배수>1 인 69랏 중 66건이 qty=1. **1주는 쪼갤 수 없다.** 유니버스 가격 상한안은 기각(§0 정정 ③) |
| ⑤ | 적용 범위 | **`sizing_mode` 로 나누지 않는다 — "K축(cycle242)이 이 랏을 실제로 심사하지 못한 모든 랏"** 에 적용(백스톱 설계). 심사 = `sizing_mode=="turtle"` ∧ `ticker is not None` ∧ `risk_pct>0` ∧ `예산>0` ∧ ATR 해석 성공 | ⚠️ **자문의 "터틀 제외(`mode != turtle`)" 안을 정정**했다(§0 정정 ①) — 그 안은 cycle242 테스트 **4건**을 깨고(F-6c VB·LTV / F-6d donchian·vcp, 시뮬레이션 실측) 절대 제약 "cycle242 무손상"을 위반한다. 백스톱 설계는 그 4건을 **무수정 통과**시키면서 자문의 목적(정상 터틀 랏 무접촉 — kojiro 000815 3.13배·donchian 3.50배 랏을 ρ 로 자르지 않기)을 그대로 달성하고, 추가로 **"터틀인데 ATR 배관이 끊긴 랏 = 양축 무방비"** 사각을 닫는다. 라이브 비용 = **0**(cycle242 배포 후 `[fallback_cap_skipped]` 실측 **0건**) |
| ⑥ | 관문 내 위치 (cycle242 와의 순서) | `_apply_budget_limit` 안, **`_emit_oversized_fallback` 관측 뒤 · `return` 앞**(§2.3). cycle242 `_apply_lot_units_cap` 호출 라인·본체 **무변경** | 유일하게 안전한 자리다. `_apply_lot_units_cap` **앞**이면 `final<1` 조기탈출로 cycle242 마커 3종이 통째로 사라진다(G-242-3 + F242-13 FAIL). `_emit_oversized_fallback` **앞**이면 차단 사건의 ρ 관측이 `final_qty<1` 로 통째로 사라진다(관측 손실). AST G-242-3 은 신규 호출을 그 뒤에 두는 것을 구조적으로 허용한다(`max(Return.lineno) > cap.lineno` 만 요구) |
| ⑦ | 두 캡의 합성 | **상호배타 — `min` 합성 없음.** ⑤의 백스톱 판정이 참이면 ρ축은 `final` 을 그대로 반환한다. 두 캡이 같은 랏에 동시에 걸리는 경로는 **존재하지 않는다**(구조 계약, AST G-8 + 행위 F-7/F-8 이 봉인) | 우선순위 규칙 자체를 불필요하게 만드는 유일한 배치. 만약 장래에 겹치게 만든다면 합성은 **반드시 `min`**(둘 다 감소 방향) — 그 경우 이 계약 문단을 먼저 고쳐야 한다 |
| ⑧ | 순수 인자 전달 | **관문 시그니처 무변경.** ρ축 상한 계산에 필요한 3요소(`position_ratio` = `self.config.params`, 예산 = `self.state.total_investment`, 현재가 = 인자)가 **이미 전부 관문 안**에 있다. `_lot_units_cap_governs` 도 cycle242 가 이미 쓰는 `_resolve_sizing_atr` 을 read-only 재사용 | cycle242 가 ATR 때문에 필요했던 듀크타이핑조차 새로 만들 것이 없다. A-GATE/A-PURE/A-ATOMIC 자동 유지 — 관문 안 `await`/DB/HTTP 0 |
| ⑨ | 키 부재 시 동작 | **키 부재 = OFF**(cycle242 `_read_max_lot_units` 의 "키 부재도 기본값 적용" 관례와 **반대**). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 명시 → 라이브는 항상 ON | (a) 이 캡은 **매수를 막는** 통제다. 설정이 없을 때 매수를 막는 fail-closed 는 **P0-1 재현 경로**(유령 키 → 항상 차단 → 전 기간 체결 0)이고 착수 제약("fail-open + LOUD")과 정면 충돌한다. (b) `_MiniStrategy`(cycle233/242 픽스처)는 `DEFAULT_PARAMS` 병합을 타지 않아 키가 없다 → 두 파일 **무수정 통과**(시뮬레이션 실증). (c) 조용한 꺼짐은 `[ratio_cap_config] cap=off reason=no_key` 카나리아 + AST G-6(전략 파일 **glob 전수** 키 존재)이 감지 |
| ⑩ | 키를 넣는 파일 | **7 전략 전부**(momentum·VB·LTV·BFB·VCP + **donchian·kojiro**) | 5전략 화이트리스트는 "키 부재 = OFF" 를 **사실상 파일 화이트리스트**로 되돌린다(자문 §2.5 가 반대한 형태). 터틀 2전략도 키를 갖되 ⑤의 판정으로 정상 랏은 무접촉이고, 누군가 `sizing_mode` 를 `position_ratio` 로 되돌리면(터틀 롤백) 그 순간 ρ축이 자동으로 받는다 — 양축 무방비 구간이 사라진다 |
| ⑪ | 파라미터 취급 | **`PARAM_RANGES`/`INT_PARAMS` 편입 금지**(런타임 dict + 소스 리터럴 이중 AST, G-1) + **읽는 쪽 클램프** `[1.0, 20.0]`: 비수치·None·bool·비유한·<1.0 → 기본 2.5 / >20.0 → 20.0. 모듈 상수 `_MAX_LOT_RATIO_MULT_DEFAULT/MIN/MAX` 가 정본(리터럴 7곳 + 상수 = 8곳, AST 가 동치 검사) | 리스크 정체성 상수 — 매일 밤 AI 자문이 흔들면 안 된다. `PUT /api/strategies/{id}/params` 는 화이트리스트 없이 기존 키를 덮어쓰므로 읽는 쪽 클램프 필수. **하한 1.0 이 계약** — K<1 이면 주 분기(정상 비중 랏)까지 잘려 **전면 무매매**가 된다. 상한 20.0 = 롤백 다이얼(§8) |
| ⑫ | 관측 마커·cap | **`[ratio_notional_blocked]`**(INFO, 행위 = 차단·축소 모두) 1회/(전략,ticker)/일 · **`[ratio_cap_skipped]`**(WARNING, fail-open) 1회/(전략,ticker,reason)/일 · **`[ratio_cap_config]`**(INFO, 카나리아 — **`cutoff_price` 병기 필수**) 1회/(전략, 값 조합 `cap상태|k|cutoff`)/일 · **`[ratio_cap_clamped]`**(WARNING) 1회/(전략, `raw` 값)/일 *(라운드 1 시정 — 종전 `cfg`/`clamp` 단일 키는 공식 롤백(`PUT …/params`)을 **확인할 채널이 0 개**로 만들고 같은 날 두 번째 범위밖 값을 무음 클램프했다. 정상 운영에선 여전히 1행/일)*. 네 마커가 **하나의 신규 `DailyEmitCap[str]`**(`_ratio_cap_logged` + `_ratio_cap_day`, cycle242 `_lot_cap_logged` 와 **별개 인스턴스**) + 날짜 키 자기 리셋 + **peek→로그→mark** + 예외 전부 흡수 | 접두가 `[ratio_*]` 라 cycle242 `[fallback_*]` · cycle233 `[oversized_fallback]` 과 grep 으로 갈린다. cap 을 **별개 인스턴스**로 두는 이유 = 한쪽 마커의 키 폭주·날짜 리셋이 다른 사이클 관측을 지우지 않게(cycle236 "별개 cap 가드" 선례). `cutoff_price` 는 자문 §8.1 의 명시 요구 — 운영자가 아침에 한 줄로 "오늘 LTV 는 130,100원 넘는 종목을 못 산다"를 읽어야 한다 |
| ⑬ | 재시도 정책 | **래치·차단 상태 신설 금지, 자연 재평가 허용** | 상한은 단조 **가격 상한**(`cap_qty ≥ 1 ⇔ price ≤ cutoff`) — 재진입은 항상 더 싼 가격에서만 통과 = 원하는 행동. 폭주는 `order_engine` 의 `LOW_FUNDS_COOLDOWN` 900s 가 이미 차단(8영역, 무접촉 — **오귀인 문서화 의무**, §7). ⚠️ **cap 은 로그에만** — 차단 행위는 cap 성패와 무관하게 **매 호출 수행**(cycle237 계약, F-12 가 봉인) |

**domain-consult 완료(`cycle245_ratio_notional_cap.md`)** — 매수 사이징 변경(매매 빈도 변경)이라 자문 필수 항목이었고, 결정 ①~④·⑪~⑬ 은 자문 §2·§5 를 그대로 채택했다.
**대안 채택 조건(사용자 한 단어로 뒤집을 수 있음)**: LTV 실적 27% 차단이 운영상 수용 불가하면 **K_ρ = 3.0**(LTV 차단 20%, 회수 +26,600, 순자산 노출 LTV 6.0%/VB 15.75%).
K_ρ = 2.0 은 **반대** — LTV 실적의 47% 를 자르면서 추가 회수가 −1,200원뿐이고 승리 랏 2건을 더 죽인다(자문 §2.3). 값 변경은 `_MAX_LOT_RATIO_MULT_DEFAULT` + 7 `DEFAULT_PARAMS` 리터럴 + F-3/F-15 기대값만 바꾸면 된다.

### 착수 컨텍스트·자문·3렌즈 전제 정정 (코드 재실측 + 캡 시뮬레이션, 결론 불변)

1. **⚠️ 최우선 — 자문 §2.5 "터틀 제외 = `sizing_mode == 'turtle'` 이면 ρ캡 미적용" 은 cycle242 테스트 4건을 깬다.**
   실증: 캡을 pytest 플러그인으로 시뮬레이션해 전수 실행한 결과 `test_cycle242_fallback_notional_cap.py::test_f242_6c_fixed_stop_strategies_have_no_candidates[volatility_breakout, long_tail_volatility]` 와 `::test_f242_6d_turtle_strategy_empty_candidates_fail_open[donchian, vcp]` 가 FAIL 한다.
   원인 = 두 테스트가 **`baseline`(비터틀 인스턴스) 대비 `qty` 동일**을 단언하는데, `mode != turtle` 게이트는 baseline 만 ρ캡에 걸리게 해 비대칭을 만든다(예: VB baseline ratio 0.10 × 774,640 = cap 77,464 → cutoff 193,660 < 405,500 → 0, turtle 주입 인스턴스는 1).
   ⇒ **결정 ⑤의 백스톱 설계로 정정**. 백스톱에서는 turtle 주입 인스턴스도 ATR 부재라 K축이 심사하지 못하므로 ρ캡을 똑같이 받아 **baseline 과 값이 일치**한다 → 4건 전부 **무수정 PASS**(시뮬레이션 실증).
   부수 이득 = 자문 §6-6 이 남긴 "터틀인데 ATR 배관이 끊기면 양축 무방비" 사각이 닫힌다. 라이브 비용 0 — cycle242 배포(09-03) 이후 `[fallback_cap_skipped]` 실측 **0건**(§1).
2. **자문 §9.1 의 경계 수치 130,103 / 130,104 는 산식과 다르다 → 130,100 / 130,101 로 정정.**
   자문은 `2.5 × (260,204 × 0.20)` 을 실수로 계산했으나, 구현은 `cap = int(예산 × ratio)` → `cutoff = int(K × cap)` **정수 절삭 2회**다.
   09-04 실측 예산으로 재계산: LTV `int(260,203×0.20)=52,040` → `int(2.5×52,040)=130,100`. VB `136,606 → 341,515` · BFB `97,576 → 243,940` · VCP `52,040 → 130,100` · momentum `32,525 → 81,312`.
   ⚠️ **Red 테스트에 자문의 130,103 을 하드코딩하지 말 것.** 차이 3원은 자문 §2.3 의 차단 4건 분류를 **한 건도 바꾸지 않는다**(경계 인접값 144,800 차단 / 129,100 통과).
3. **"유니버스 가격 상한" 대안(설계 질문 ②)은 `scanner.py` 가 아니라 `strategy_base.py:1191 _apply_price_filter_in_prepare`(허용 영역) + `system_config.price_filter_max`(현재 500,000, HARD, 활성)에 **이미 존재한다** — 그럼에도 기각.**
   기각 사유 3: (a) 판정이 **전일종가**(`bfdy_clpr`) 기준이라 급등 추격 전략에서 구조적으로 샌다(000500 실측 전일 208,500 → 진입 220,000, +5.5%) (b) **momentum 은 `prepare()` 가 빈 스텁**이라 이 경로를 호출하지 않는다 (c) 계좌 전역 단일 값이라 전략별 ρ상한을 표현 못 한다.
   `price_filter_max` 500,000 → 250,000 조정은 **코드 0줄**이지만 kojiro(예산 780,611)·donchian 의 정상 매수를 동시에 자르므로 **별건 후속**(§8 F-1, 사용자 결정 사항).
4. **렌즈1 "관문 시그니처 무변경으로 충분" 은 맞지만, "`_fallback_one_share` 한 곳만 바꾸면 된다"는 부분은 채택하지 않는다.**
   헬퍼 안에 넣으면 `test_budget_limit_gate.py:163` 의 `patch.object(StrategyBase, "_fallback_one_share")` 가 캡을 **통째로 우회**해 회귀 가드가 공허해지고, 헬퍼 인자를 늘리면 같은 줄의 `assert_called_once_with(100_000_000)` 이 깨진다.
   ⇒ **관문 안 별도 헬퍼**(`_apply_ratio_notional_cap`)로 두고 `self.config.params`/`self.state` 를 직접 읽는다 = cycle242 와 동형. 스코프도 cycle242 와 같은 **"모든 랏"**(주 분기 포함) — K_ρ≥1 이면 주 분기는 정의상 무접촉이지만(F-4), 그것을 **항등식으로 봉인**해야 장래 리팩토링이 조용히 뚫지 못한다.

---

## 1. 확증된 원인 (3렌즈 + EC2 라이브 실측 + 캡 시뮬레이션)

| 사실 | 근거 |
|---|---|
| **09-04 최대 단일 손실이 이 경로에서 나왔다.** 08:12:03 LTV 매수 신호(000500 가온전선 220,000, PRE_NXT) → `int(260,203×0.20)//220,000 = 0` → `_fallback_one_share` → 잔여 260,203 ≥ 220,000 → **1주** = 설계 랏(52,040)의 **4.23배** → 09:32 −5% 손절 **−11,000원**(순자산 0.42%). 설계대로였다면 −2,602원 | EC2 `system_logs` 원문: `[oversized_fallback] ticker=000500 strategy=long_tail_volatility qty=1 notional=220000 cap=52040 ratio=4.23` (09-04 08:12) · `trade_history` |
| **cycle242 캡은 이 경로를 설계대로 지나친다** — `sizing_mode=None` 이라 `cap=off`. 같은 시각 카나리아가 그것을 정확히 기록했다 | `[fallback_cap_config] strategy=long_tail_volatility sizing_mode=None cap=off k=2.00 budget=260203 risk_pct=0.0000 atr_max=0` (09-04 08:12:04) |
| **비터틀 3전략은 ATR 축이 원리적으로 불가** — `long_tail_volatility.py`·`volatility_breakout.py`·`momentum.py` 에 `_entry_atr`·`atr`·`atr14`·`risk_pct`·`sizing_mode`·`_candidates` 토큰이 **한 건도 없다** | grep 실측(렌즈1). `test_cycle242_fallback_notional_cap.py:441` 이 `assert not hasattr(s, "_candidates")` 로 이미 봉인 |
| **1주 폴백은 예외가 아니라 주 경로다** — 90일 매수 중 1주 비율 VB **91%**(71/78) · LTV **79%**(41/52) · momentum **73%**(8/11). ρ상한 초과 랏 69건 중 **66건이 qty=1** | 렌즈2·3 EC2 `trade_history` 90일 |
| **손실이 배수 상위에 집중** — 현행 레짐(08-19~09-04, 12영업일) 51랏 총손실 −122,285원의 **31%** 가 배수 ≥2.11 인 랏 3건(08-19 VB 108490 −16,000 / 08-31 LTV 161890 −11,200 / 09-04 LTV 000500 −11,000) | 렌즈2 뷰 A |
| **기존 5중 통제 중 어느 것도 이 축을 보지 않는다** — ① 잔여 클램프는 Σ축이고 09-04 엔 **역효과**(000500 이 예산의 84.5% 를 먹고 뒤따르는 090460 이 `[budget_clamp] requested=2 clamped=1 remaining=40203` 로 잘림) ② `max_positions` 는 개수축 ③ `risk.py` `price > total_investment` 는 같은 축이지만 상한이 ρ상한의 **5배**(momentum 161890 은 차단, LTV 000500 은 통과) ④ 계좌 SOFT Σ상한은 `account_risk_block_pct` **키 자체가 DB 에 없음**(09-04 재확인) = 다크런치 ⑤ `daily_loss_limit` LTV −7% = −18,214원 → 09-04 −11,000 미도달 | 렌즈3 · EC2 `system_config` 실측(09-04: `cash_usage_ratio` 1.0 / `price_filter_max` 500000 / **`account_risk_block_pct` 부재**) |
| **관측 마커만 읽으면 규모를 1/4 로 과소평가한다** — `[oversized_fallback]` 전수 6건(09-02 1 · 09-03 4 · 09-04 1)이 전부 cycle233 배포 이후 3영업일. 현행 레짐 재구성 실측은 51랏 중 **22건(1.8건/영업일)** 이 ρ초과 | EC2 6일 집계 실측 |
| **cycle242 의 터틀 fail-open 은 라이브에서 아직 한 번도 안 일어났다** — 배포(09-03) 후 `[fallback_cap_skipped]` **0건** · `[fallback_notional_capped]` **0건** · `[fallback_cap_config]` 09-04 4행 | EC2 6일 집계. ⇒ 결정 ⑤ 백스톱의 **라이브 행위 델타 = 0** |
| **라이브 파라미터가 코드 `DEFAULT_PARAMS` 와 다르다 — 판단은 DB 값 기준** | EC2 `strategy_config` 09-04 실측: LTV `ratio 0.20`(코드 0.15) mode **None** · VB `ratio 0.35`(코드 0.10) mode **None** · momentum `ratio 0.25` mode **None** · BFB `0.25` `position_ratio` · VCP `0.20` `position_ratio` · donchian `0.20` **turtle** · kojiro `0.166` **turtle**. `max_lot_units` 는 7전략 전부 DB **None**(코드 기본 2.0 사용). 전부 `enabled=True` |
| **주 분기·터틀 분기는 정의상 ρ상한 이하** — 주: 호출자 `qty = int(예산×ratio)//price` ⇒ notional ≤ `int(예산×ratio)`; 터틀: `compute_unit_qty_guarded` 가 `min(qty, int(예산×ratio)//price)` 를 **무조건** 적용. 무상한인 곳은 `_fallback_one_share`(`잔여 ≥ 현재가` 만 확인) **하나뿐** | `strategy_base.py:450-465`·`:497-503` · `turtle_sizing.py` · 호출부 LTV `:791-793` / VB `:1057-1059` / momentum `:241-243` |
| **캡 시뮬레이션 전수 실행 결과 파손은 정확히 18 케이스·3 파일** — 그 외 전 스위트 무손상 | 백스톱 설계 시뮬레이션: `tests/unit/engine`+`tests/unit/ast`+`test_buy_block_low_funds.py` → **18 failed, 4,260 passed**; 나머지 전 스위트 → **1,968 passed, 0 failed**. 목록·수정안 = §4.3 |

---

## 2. 시정 설계 (`src/engine/strategy_base.py` 주 + 7 전략 `DEFAULT_PARAMS` 1키)

### 2.1 모듈 상수 (기존 `_MAX_LOT_UNITS_MAX` 아래, `:29` 다음)

```python
# ── cycle245 랏 명목 ρ축 상한 (비터틀 = K축이 심사하지 못하는 모든 랏) —
# 리스크 정체성 상수, PARAM_RANGES/INT_PARAMS 편입 금지(AST G-245-1).
# 7 전략 DEFAULT_PARAMS["max_lot_ratio_mult"] 는 _MAX_LOT_RATIO_MULT_DEFAULT 와 동치여야 한다(AST G-245-6).
_MAX_LOT_RATIO_MULT_DEFAULT = 2.5   # K_ρ — 랏 명목 ≤ K_ρ × (position_ratio × 예산)
_MAX_LOT_RATIO_MULT_MIN = 1.0       # K_ρ<1 은 정상 비중 랏까지 잘라 전면 무매매 = 정의상 금지.
                                    # 하한 1.0 = 주 분기(qty>0) 무접촉의 수학적 전제
_MAX_LOT_RATIO_MULT_MAX = 20.0      # 09-04 예산에서 K=20 컷오프가 5전략 전부 price_filter_max(500,000) 초과
                                    # → 사실상 현행 복귀(롤백 다이얼)
```

### 2.2 `StrategyBase.__init__` — cap 속성 2 (cycle242 `_lot_cap_*` 아래, `:255` 다음)

```python
        # cycle245 — ρ축 랏 명목 상한 관측 cap (복합 키: "blk|{ticker}" / "skip|{ticker}|{reason}"
        # / "cfg" / "clamp"). cycle242 `_lot_cap_logged` 와 **별개 인스턴스** — 한 사이클의
        # 키 폭주·날짜 리셋이 다른 사이클 관측을 지우지 않게 한다. 날짜 키 자기 리셋.
        self._ratio_cap_logged: DailyEmitCap[str] = DailyEmitCap[str]()
        self._ratio_cap_day: str = ""
```

### 2.3 `_apply_budget_limit` — 1줄 삽입 (기존 분기·호출 순서 byte 보존)

`strategy_base.py:509-522` 의 `_apply_lot_units_cap` 호출과 `_emit_oversized_fallback` try 블록은 **무변경**. `return final` **직전**에만 삽입한다.

```python
        try:
            self._emit_oversized_fallback(ticker, final, current_price)
        except Exception:  # pragma: no cover — 관측 자기실패 흡수
            pass
        # cycle245 — ρ축 랏 명목 상한 (행위). K축(cycle242)이 이 랏을 실제로 심사하지
        # 못한 경우에만 적용 = 두 캡은 상호배타(min 합성 없음, §3 계약 3).
        # 관측(`[oversized_fallback]`) **뒤**에 두는 것이 계약 — 앞에 두면 차단된 랏의
        # ρ 관측이 `final_qty < 1` 조기탈출로 통째로 사라진다. 캡 산출 실패는 현행
        # 수량 유지(fail-open) — 헬퍼 내부에서 흡수·LOUD.
        final = self._apply_ratio_notional_cap(
            final, current_price, ticker, via_fallback=_via_fallback,
        )
        return final
```

**docstring 단서 추가**(기존 cycle242 문단 뒤): *"**그리고 K축이 심사하지 못한 랏(비터틀 전략 전부 + 터틀이지만 ATR 배관이 끊긴 랏)은 최종 명목이 `max_lot_ratio_mult`(K_ρ) × `position_ratio` × 예산 을 넘으면 그만큼 자르고, 1주도 못 사면 매수하지 않는다**(cycle245 — 1주 폴백 랏 크기가 그 종목의 주가로 결정되던 §5 결함 시정. 09-04 실측 4.23배 랏이 그날 최대 손실을 냈다)."*

### 2.4 신규 헬퍼 6 (전부 동기·순수 — await/DB/HTTP 0, A-PURE 확장 대상)

```python
    # ──────── cycle245 — ρ축 랏 명목 상한 (`max_lot_ratio_mult`) ────────

    def _read_max_lot_ratio_mult(self) -> float | None:
        """`max_lot_ratio_mult` 읽기 + 클램프. **키 부재는 `None`**(= 캡 OFF).

        ⚠️ cycle242 `_read_max_lot_units` 와 **반대 관례**다. 이 캡은 *매수를 막는*
        통제이므로 "설정이 없으면 막는다"(fail-closed)는 P0-1 유령 키 재현 경로다.
        키는 7 전략 `DEFAULT_PARAMS` 에 전부 명시돼 라이브는 항상 ON 이고, 키가 없는
        것은 `StrategyBase` 를 직접 상속한 테스트 더블뿐이다(AST G-245-6 이 전략
        파일 glob 전수로 키 존재를 강제).

        키 존재 + 무효/범위밖 → `_MAX_LOT_RATIO_MULT_DEFAULT` 또는 MAX 로 정규화하고
        `[ratio_cap_clamped]` WARNING 1회/전략/일(`raw=%r` 병기). bool 은 수치로 보지 않는다.
        """
        if "max_lot_ratio_mult" not in self.config.params:
            return None
        raw = self.config.params.get("max_lot_ratio_mult")
        clamped = False
        if isinstance(raw, bool):
            result = _MAX_LOT_RATIO_MULT_DEFAULT
            clamped = True
        else:
            try:
                k = float(raw)
            except (TypeError, ValueError):
                result = _MAX_LOT_RATIO_MULT_DEFAULT
                clamped = True
            else:
                if not math.isfinite(k) or k < _MAX_LOT_RATIO_MULT_MIN:
                    result = _MAX_LOT_RATIO_MULT_DEFAULT
                    clamped = True
                elif k > _MAX_LOT_RATIO_MULT_MAX:
                    result = _MAX_LOT_RATIO_MULT_MAX
                    clamped = True
                else:
                    result = k
        if clamped:
            self._emit_ratio_cap_clamped(raw, result)
        return result

    def _lot_units_cap_governs(self, ticker: str | None) -> tuple[bool, str]:
        """cycle242 K축 캡이 **이 랏을 실제로 심사하는가** — ρ축 미적용 조건 (read-only, 무음).

        반환 `(governs, reason)`. `_apply_lot_units_cap` 의 fail-open 4조건과 **같은
        소스·같은 판정**을 쓴다(`params["sizing_mode"]`/`params["risk_pct"]`/
        `state.total_investment`/`_resolve_sizing_atr`). 로그를 내지 않는다 — 판정기가
        시끄러우면 랏마다 2배로 찍힌다(관측은 `[ratio_cap_config]` 카나리아 담당).

        reason ∈ {"k_axis", "not_turtle", "no_ticker", "no_risk_pct", "no_budget",
                  "no_atr", "probe_error"}.
        - `"k_axis"` → K축이 심사 = ρ축 **미적용**(조용히)
        - `"probe_error"` → 판정 자체가 실패 = **fail-open 방향으로 미적용** + LOUD
        - 그 외 → ρ축 **적용**
        """
        try:
            params = self.config.params
            if params.get("sizing_mode") != "turtle":
                return False, "not_turtle"
            if ticker is None:
                return False, "no_ticker"
            try:
                risk_pct = float(params.get("risk_pct") or 0)
            except (TypeError, ValueError):
                return False, "no_risk_pct"
            if risk_pct <= 0:
                return False, "no_risk_pct"
            if int(self.state.total_investment or 0) <= 0:
                return False, "no_budget"
            atr, _reason = self._resolve_sizing_atr(ticker)
            if atr is None:
                return False, "no_atr"
            return True, "k_axis"
        except Exception:  # pragma: no cover
            # 판정 실패는 "현행 수량 유지" 쪽으로 fail (착수 제약: fail-open + LOUD)
            return True, "probe_error"

    def _apply_ratio_notional_cap(
        self, final: int, current_price: int, ticker: str | None, *, via_fallback: bool,
    ) -> int:
        """랏 명목 ρ축 상한 — `min(final, int(K_ρ × int(예산 × position_ratio)) // 현재가)`.

        - 산식의 `cap = int(예산 × position_ratio)` 는 `_emit_oversized_fallback`(cycle233)
          · `portfolio_risk.compute_over_cap_positions` 와 **동일**(세 번째 복제가 아니라
          같은 축에 행위를 얹는 것) — §7 R7 자기검증 불변식의 전제다.
        - 차단 조건은 `final × price > cutoff` = **경계 포함**(`>=` 아님).
        - K_ρ ≥ 1 이므로 주 분기(`qty > 0`)는 정의상 무접촉이다(F-4/F-5 가 항등식으로 봉인).
        - fail-open: 키 부재 / K축 심사 / `position_ratio` ≤ 0 / 예산 ≤ 0 / cap 0 / 예외
          → `final` 그대로. 사유는 `[ratio_cap_skipped]` WARNING(키 부재·K축 심사는 조용히
          — 정상 구성이고 `[ratio_cap_config]` 가 이미 기록한다).
        - 행위(반환값)는 관측 성패와 무관 — 네 emit 은 내부에서 예외 흡수.
        """
        if final < 1 or current_price <= 0:
            return final
        try:
            params = self.config.params
            k = self._read_max_lot_ratio_mult()        # None = 키 부재 = OFF
            mode = params.get("sizing_mode")
            try:
                pos_ratio = float(params.get("position_ratio") or 0)
            except (TypeError, ValueError):
                pos_ratio = 0.0
            budget = int(self.state.total_investment or 0)
            cap = int(budget * pos_ratio) if (pos_ratio > 0 and budget > 0) else 0
            cutoff = int(k * cap) if (k is not None and cap > 0) else 0
            governs, gov_reason = self._lot_units_cap_governs(ticker)
            # 캡 상태 카나리아 (1회/전략/일) — 조용히 꺼진 채 매수가 나가는 사고 감지
            self._emit_ratio_cap_config(mode, k, budget, pos_ratio, cap, cutoff, governs)
            if k is None:
                return final                                  # 키 부재 = OFF (조용히)
            if governs:
                if gov_reason == "probe_error":
                    self._emit_ratio_cap_skipped(ticker, "k_axis_probe_error",
                                                 final, current_price)
                return final                                  # K축이 심사 = 이중 캡 금지
            if cap <= 0:
                reason = ("no_ratio" if pos_ratio <= 0
                          else "no_budget" if budget <= 0 else "no_cap")
                self._emit_ratio_cap_skipped(ticker, reason, final, current_price)
                return final
            cap_qty = cutoff // current_price
            if final <= cap_qty:
                return final
            self._emit_ratio_notional_blocked(
                ticker, via_fallback=via_fallback, price=current_price, cap=cap,
                cutoff=cutoff, k=k, req_qty=final, capped_qty=cap_qty,
                budget=budget, pos_ratio=pos_ratio,
            )
            return cap_qty
        except Exception:
            # 캡 산출 자체가 던지면 현행 수량 유지 (변경 이전 행위 쪽으로 fail).
            # logger.debug 도 emit 과 **같은 try 안** — cycle242 라운드1 #1/#2 교훈
            # (로거가 죽어도 매수 수량 산출은 살아야 한다).
            try:
                self._emit_ratio_cap_skipped(ticker, "exception", final, current_price)
                logger.debug(
                    "[ratio_cap_skipped] exception ticker=%s", ticker, exc_info=True,
                )
            except Exception:  # pragma: no cover
                pass
            return final
```

관측 헬퍼 4 — 공통 골격: 함수 전체 `try/except Exception: pass`, 날짜 키 `datetime.now(_KST).date().isoformat()` 가 `_ratio_cap_day` 와 다르면 `_ratio_cap_logged.reset_daily()` 후 갱신, **`should_emit(key)` → `logger.*` → `mark_emitted(key)`** 순서(peek→로그→mark, cycle226 D-3).

```python
    def _emit_ratio_notional_blocked(self, ticker, *, via_fallback, price, cap, cutoff,
                                     k, req_qty, capped_qty, budget, pos_ratio):
        # key = f"blk|{ticker or '-'}"  · INFO
        # "[ratio_notional_blocked] ticker=%s strategy=%s path=%s price=%d cap=%d "
        # "cutoff=%d k=%.2f ratio=%.2f req_qty=%d capped_qty=%d budget=%d pos_ratio=%.4f"
        #   path  = "fallback" if via_fallback else "sized"
        #   ratio = (req_qty * price) / cap   ← `[oversized_fallback]` 의 ratio 와 같은 정의

    def _emit_ratio_cap_skipped(self, ticker, reason, final, price):
        # key = f"skip|{ticker or '-'}|{reason}" · WARNING
        # "[ratio_cap_skipped] ticker=%s strategy=%s reason=%s qty=%d price=%d "
        # "— ρ캡 미적용(현행 수량 유지, fail-open)"
        #   reason ∈ {no_ratio, no_budget, no_cap, k_axis_probe_error, exception}

    def _emit_ratio_cap_config(self, mode, k, budget, pos_ratio, cap, cutoff, governs):
        # key = f"cfg|{cap_state}|{k_desc}|{cutoff}"  · INFO  (값-민감 — 라운드 1)
        # "[ratio_cap_config] strategy=%s sizing_mode=%s cap=%s k=%s budget=%d "
        # "pos_ratio=%.4f cap_notional=%d cutoff_price=%d"
        #   cap = "off"      (k is None — 키 부재)
        #       | "backstop" (mode == "turtle" — K축 우선, ρ는 K축이 fail-open 할 때만)
        #       | "on"       (그 외 = ρ축이 주 상한)
        #   k   = "-" if k is None else f"{k:.2f}"
        #   ⚠️ `cutoff_price` 는 필수 필드 — 운영자의 아침 한 줄 판독 근거(자문 §8.1)

    def _emit_ratio_cap_clamped(self, raw, result):
        # key = f"clamp|{raw!r}"[:96]  · WARNING  (raw 별 — 라운드 1)
        # "[ratio_cap_clamped] strategy=%s raw=%r clamped_to=%.2f "
        # "— max_lot_ratio_mult 범위 밖 값이 클램프됨(DB/PUT 확인 필요)"
```

### 2.5 `_emit_oversized_fallback` — **docstring 만** 갱신 (로그 서식 byte 불변)

`strategy_base.py:836-892`. **`logger.info` 포맷 문자열·필드·cap 키·순서 전부 무변경**(AST G-245-10 이 byte 동일성을 핀). docstring 에 아래 문단만 추가:

> *"cycle245 — 이 마커는 ρ캡 **앞**에서 발화하므로 의미가 **'실제로 산 랏' → '사려 했던 랏'** 으로 전환됐다. 차단된 랏(`[ratio_notional_blocked]`)도 여기에 1행 남는다. **자기검증 불변식(R7)**: K축이 심사하지 않는 전략에서 `ratio` 가 `max_lot_ratio_mult` 를 넘는 행이 있으면 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]` 가 **반드시** 짝을 이룬다(양쪽 cap 이 모두 1회/ticker/일이라 성립). 짝이 없으면 캡 우회 = 결함. ⚠️ 배포 전후 같은 grep 합산 금지."*

### 2.6 전략 7파일 — `DEFAULT_PARAMS` 1키

```python
        "max_lot_ratio_mult": 2.5,   # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수. 터틀 모드에선 K축(max_lot_units)이 우선하고 그것이 fail-open 할 때만 백스톱. PARAM_RANGES 미편입. 롤백 = DB 20.0
```

삽입 위치 = 각 파일 `DEFAULT_PARAMS` 리터럴의 **마지막 키 바로 아래**:

| 파일 | 현행 마지막 키(라인) |
|---|---|
| `momentum.py` | `"daily_loss_limit": -5.0,` (`:64`) |
| `volatility_breakout.py` | `"rsi_extreme_max": 85,` (`:119`) |
| `long_tail_volatility.py` | `"daily_loss_limit": -5.0,` (`:99`) |
| `bull_flag_breakout.py` | `"max_lot_units": 2.0,` (`:146`) |
| `vcp_breakout.py` | `"max_lot_units": 2.0,` (`:172`) |
| `donchian_swing.py` | `"max_lot_units": 2.0,` (`:128`) |
| `kojiro.py` | `"max_lot_units": 2.0,` (`:211`) |

**7 전략 전부**(결정 ⑩). 터틀 2전략(donchian·kojiro)에도 넣되 `_lot_units_cap_governs` 가 정상 랏을 무접촉으로 통과시킨다 — 키의 역할은 **`sizing_mode` 를 `position_ratio` 로 되돌릴 때의 안전망**이다.
`DEFAULT_PARAMS` 키 추가는 C-DEFAULT(`position_ratio × max_positions`)·cycle198/211 스코프 가드에 무영향(키 집합 동등 단언 부재 — 시뮬레이션 실증).

### 2.7 fail-open 경계 (계약)

| 상황 | ρ캡 | 행위 | 마커 |
|---|---|---|---|
| `final < 1` 또는 `price ≤ 0` | — | 그대로 | 없음(config 도 미발화) |
| `max_lot_ratio_mult` 키 부재 | off | 현행 byte 동일 | `[ratio_cap_config] cap=off k=-` 1회/전략/일 |
| `sizing_mode=="turtle"` ∧ ticker ∧ `risk_pct>0` ∧ 예산>0 ∧ ATR 해석 성공 | off(K축 담당) | 현행(= cycle242 결과) | `[ratio_cap_config] cap=backstop` 만 |
| `sizing_mode=="turtle"` 인데 위 조건 하나라도 불성립(ticker None·risk_pct 0·ATR 결측/모호) | **on(백스톱)** | ρ 상한 적용 | `[fallback_cap_skipped]`(cycle242) + 필요 시 `[ratio_notional_blocked]` |
| `_lot_units_cap_governs` 자체가 예외 | off | 현행 | `[ratio_cap_skipped] reason=k_axis_probe_error` WARNING |
| `position_ratio` 결측/0/비수치 | off | 현행 | `reason=no_ratio` WARNING |
| 예산 ≤ 0 | off | 현행 | `reason=no_budget` WARNING |
| `int(예산 × ratio) == 0`(초소액) | off | 현행 | `reason=no_cap` WARNING |
| 캡 산출 중 예외 | off | 현행 | `reason=exception` WARNING + `logger.debug(exc_info)` |
| 위 전부 통과 ∧ `final × price ≤ cutoff` | on | 그대로 | 없음 |
| 위 전부 통과 ∧ `final × price > cutoff` | on | `cutoff // price` (실질 0) | `[ratio_notional_blocked]` 1회/(전략,ticker)/일 |

**fail-open 방향이 계약이다** — 어떤 결측·예외도 수량을 0 으로 만들지 않는다(F-10 이 P0-1 재현 방지 가드).

---

## 3. 불변 계약

1. **관문 시그니처·기존 분기 순서 불변** — `_apply_budget_limit(qty, current_price, ticker=None)`; `price≤0→0` → `qty≤0→_fallback_one_share` / `qty>0→잔여 클램프+[budget_clamp]` → `_apply_lot_units_cap`(cycle242) → `[oversized_fallback]`(cycle233) → **ρ캡**(cycle245) → return. (A-FALLBACK `assert_called_once_with(price)` 보존, G-242-3 + G-245-3)
2. **cycle242 무손상** — `_apply_lot_units_cap`·`_read_max_lot_units`·`_resolve_sizing_atr`·`_describe_lot_cap_diagnostics`·`_emit_fallback_*` 4종 **diff 0** · 마커 4종 서식·cap 키·발화 조건 무변경 · `test_cycle242_fallback_notional_cap.py`/`test_cycle245_ast_*` 이전 AST 파일 **무수정 PASS**(시뮬레이션 실증).
3. **두 캡은 상호배타** — `_lot_units_cap_governs` 가 참이면 ρ캡은 `final` 을 그대로 반환한다. 같은 랏에 두 캡이 동시에 걸리는 경로는 존재하지 않는다(F-7/F-8 + G-245-8). 장래에 겹치게 만들면 합성은 **반드시 `min`** 이고, 이 문단을 먼저 고쳐야 한다.
4. **`_fallback_one_share` 본체 diff 0** · `_calc_used_funds` diff 0 · `turtle_sizing.py` diff 0 · `compute_unit_qty_guarded` 무접촉. 캡은 **관문 안 별도 헬퍼**에만 있고 헬퍼 인자를 늘리지 않는다(§0 정정 ④).
5. **A-GATE·A-ATOMIC·A-PURE 유지** + A-PURE 를 신규 헬퍼 6 으로 확장(G-245-2). 관문 안 `await`/DB/HTTP 0.
6. **주 분기 무접촉이 항등식** — `K_ρ ≥ 1.0` 이면 `qty > 0` 분기 결과는 어떤 (예산, ratio, price) 에서도 ρ캡에 걸리지 않는다(하한 1.0 클램프가 전제, F-4/F-5). 하한을 1.0 미만으로 완화하면 전면 무매매 — G-245-6 이 상수를 핀.
7. **모든 랏 스코프(적용 범위)와 항등식은 다른 문장이다 — 뭉치지 마라.** *(라운드 1 정정 — 종전 한 문장은 자기 테스트가 반례였다)*
   - **(7a) 스코프** — 캡은 폴백 랏뿐 아니라 관문을 통과하는 **모든** 랏에 적용된다. `via_fallback` 이나 `final == 1` 같은 특수 케이스로 좁히지 않는다(**F-5b/F-5c** 가 축소 뮤테이션 M13 을 봉인 — 종전엔 `req ∈ {0, sized}` 그리드만 돌아 **캡이 실제로 바인딩되는 non-fallback 랏이 커버리지에 0 건**이었고 M13 이 표적 53 테스트를 통째로 통과했다). 현행 7 전략 호출부는 `qty = int(예산×ratio)//price` 이고 터틀도 `compute_unit_qty_guarded` 가 같은 상한을 강제하므로 **프로덕션 도달은 없다**(F-4 무접촉 항등식 유효) — 이 조항이 지키는 것은 장래 회귀다.
   - **(7b) 항등식** — `notional ≤ K_ρ × int(예산×ratio)` 는 **ρ축이 심사한 랏에 한해** 성립한다(F-5). ⚠️ **K축이 심사한 터틀 랏은 이 항등식 밖이다.** `_apply_lot_units_cap` 은 유닛 축이라 ATR 이 작을수록 `cap_qty` 가 커지고, 그래서 F-7b 가 donchian 명목 300,000(ρ상한 195,150 의 **3.84배**) 랏을 `assert qty == 1` 로 **불변 단언**한다 = 결정 ⑦(상호배타)의 직접 귀결이다. 실측 잔여 노출 = kojiro B=780,611 ρ=0.166 price 500,000 atr∈[5,000, 7,800] → **3.86배** · donchian B=390,300 ρ=0.20 price 390,000 atr≤3,900 → **5.00배**(§8 후속 **F-9**). 두 문장을 뭉치면 장래 리팩토링이 "항등식 위반"을 고치려다 상호배타를 깬다 — 다만 그 대가는 **cycle242 가 아니라 이 사이클 자신의 결정 ⑦**이다. ⚠️ **라운드 2 증거 귀속 정정**(§12-1): 상호배타를 푸는 방향(ρ를 K축 심사 랏에도 `min` 합성)은 `test_cycle242_fallback_notional_cap.py` 를 **97 passed / 0 failed** 로 통과시킨다 — 깨지는 것은 F-7b 하나뿐이다(순진하게 `if governs:` 블록째 지우면 판정 실패 fail-open 까지 함께 사라져 F-10d 도 동반). cycle242 F-6c/6d **4건**을 되살리는 것은 **반대 방향**(자문 원안 = 백스톱 제거)이고 그 실측이 종전 문안이 인용한 "M6 실증 8 FAIL" 이다.
8. **fail-open 방향 고정** — 결측·모호·예외 = 현행 수량. 수량을 0 으로 만드는 fail-closed 구현은 FAIL(F-10 = P0-1 재현 방지 가드).
9. **행위는 cap 밖** — 네 마커의 발화 성패·cap 소진 여부와 무관하게 차단은 **매 호출 수행**(F-12/F-13, cycle237 계약). 마커는 `logger` 만 — `write_log` 이중 INSERT 0(cycle72 규약).
10. **`max_lot_ratio_mult` ∉ PARAM_RANGES/INT_PARAMS**(런타임 + 소스 리터럴, G-245-1) · 읽는 쪽 `[1.0, 20.0]` 클램프 · 기본 2.5 는 상수 1곳 + 리터럴 7곳 동치(G-245-6) · **AI 자문·자동 적용 경로 편입 금지**.
11. **캡 로직은 관문 안에만** — 7 전략 `calc_buy_quantity`/터틀 사이징 함수에 `max_lot_ratio_mult` 토큰 0(G-245-7), 전략 7파일 diff = `DEFAULT_PARAMS` 1줄씩.
12. **`[oversized_fallback]` 로그 서식 byte 불변**(G-245-10) — 의미만 전환하고 문자열은 손대지 않는다(cycle233 `"3.10" in message` 형 검사 호환).
13. 8영역 diff 0 · `scheduler.py` diff 0 · `boot_manager.py` diff 0 · `StrategyState` dataclass 필드 무변경(cap 상태는 `StrategyBase` 인스턴스 속성 — `reset_daily` 가드 무영향).

---

## 4. Red 테스트 목록

### 4.1 `tests/unit/engine/test_cycle245_ratio_notional_cap.py` (신규 — ID 접두 `test_f245_`)

픽스처: (a) `_MiniStrategy`(cycle233 패턴, `StrategyBase` 직접 상속) + `params={"exchange":"KRX","position_ratio":ρ,"max_lot_ratio_mult":K}`(+ 필요 시 `sizing_mode`/`risk_pct`, `_candidates` 주입) (b) 실전략 `_mk` 관용구(다른 테스트 모듈 import 금지 — 로컬 재정의).
**결정적 기준선**: LTV형 예산 **260,200** · `position_ratio` **0.20** → `cap = 52,040` · `cutoff(K=2.5) = 130,100`.
caplog = `caplog.at_level(logging.INFO)`(WARNING 은 `levelno` 필터). 시각은 `freeze_kst` 루트 fixture 또는 `freezegun` KST aware 문자열만.

| ID | 시나리오 | 기대 |
|---|---|---|
| **F-1 (현행 FAIL — 핵심)** 09-04 재현 | `_MiniStrategy("long_tail_volatility")` B=260,200 ρ=0.20 K=2.5, `_apply_budget_limit(0, 220_000, "000500")` | **`== 0`** · INFO `[ratio_notional_blocked] ticker=000500 strategy=long_tail_volatility path=fallback price=220000 cap=52040 cutoff=130100 k=2.50 ratio=4.23 req_qty=1 capped_qty=0 budget=260200 pos_ratio=0.2000` 정확 1행 · **`[oversized_fallback]` 1행**(캡 **앞** 관측 = "사려 했던 랏", `ratio=4.23`) · `[ratio_cap_skipped]` 0 |
| **F-2** 경계 | 같은 픽스처 price **130,100 → `== 1`** / **130,101 → `== 0`** | `final × price > cutoff` 가 차단 조건 — `>=` 로 바꾸면 FAIL. ⚠️ 자문의 130,103/130,104 는 오산(§0 정정 ②) |
| **F-3** 실측 시리즈 | 220,000→0 · 190,300→0 · 171,700→0 · **144,800→0**(08-28 010950 = **승리 랏도 차단**, 비용 봉인) · 129,100→1 · 128,600→1 · 109,600→1 · 86,900→1 · 21,050→1 | 자문 §2.3 표를 그대로 고정 |
| **F-4** 주 분기 무접촉 | (a) `_apply_budget_limit(1, 40_000, "T")` → `== 1`(cap 52,040 → 주 분기 1주, notional 40,000 ≤ 130,100) (b) 결정적 그리드 price∈{1k,5k,20k,60k,250k,500k} × ρ∈{0.05,0.10,0.166,0.20,0.25,0.35,0.50} × K∈{1.0,2.5,20.0} × B∈{130k,260k,390k,780k,5M} 에서 `qty>0` 분기 결과가 **HEAD 와 동일** | K≥1 이면 주 분기는 정의상 무접촉 |
| **F-5** 항등식(스코프 계약) | 같은 그리드 + `qty ∈ {0, 주 분기 수량}` 에서 `final ≥ 1 ⇒ final × price ≤ int(K × int(B × ρ))` | 모든 랏에서 `notional ≤ K_ρ × ρ × B` |
| **F-6 키 부재 = OFF** | `_MiniStrategy` params 에 `max_lot_ratio_mult` **없음** + ρ=0.166 B=789,130 price 405,500(cycle233 000815 픽스처) | **`== 1`** · `[ratio_notional_blocked]` 0 · `[ratio_cap_config] ... cap=off k=-` 1행 · `[ratio_cap_clamped]` 0. **0 이면 FAIL** — cycle233/242 픽스처 무수정 통과의 근거를 명시 테스트로 고정 |
| **F-7** 터틀 무접촉(K축 심사) | donchian/kojiro 실전략 `sizing_mode="turtle"` + `risk_pct=0.005` + `_candidates[t]={"atr":X}` | ρ캡 **미적용** — 수량이 cycle242 결과와 **동일**(kojiro B=774,640 ρ=0.166 `atr=13300` price 405,500 → cycle242 K축이 **0**, ρ캡은 관여 안 함) · `[ratio_notional_blocked]` 0 · `[ratio_cap_config] cap=backstop` 1행 · cycle242 마커 3종 정상 |
| **F-8** 터틀 백스톱(K축 fail-open) | donchian turtle B=390,300 ρ=0.20(cutoff 195,150) + `_candidates` **비어 있음** + price 405,500 | **`== 0`** · `[fallback_cap_skipped] reason=no_atr`(cycle242) 1행 **동시에** `[ratio_notional_blocked]` 1행 · **비터틀 baseline 과 값 동일**(= cycle242 F-6c/6d 계약 정합). `sizing_mode`/`risk_pct` 를 각각 빼도 동일(백스톱 4조건 전수) |
| **F-9** ticker None | (a) `_MiniStrategy` `_apply_budget_limit(0, 405_500, None)` → 캡 적용, 마커 `ticker=-` (b) donchian turtle `calc_buy_quantity(38_000)`(ticker 생략) → cycle242 F-7 과 **같은 값**(2주, notional 76,000 ≤ cutoff 195,150) | K축이 ticker None 에서 조용히 off 하는 구간을 ρ축이 받는다 |
| **F-10 fail-open**(P0-1 재현 방지) | (a) `position_ratio` 0 / None / `"abc"` / 음수 → `reason=no_ratio` (b) `total_investment` 0 → `no_budget` (c) `int(B×ρ)==0`(B=100 ρ=0.001) → `no_cap` (d) `_lot_units_cap_governs` 를 raise 로 monkeypatch → `k_axis_probe_error` (e) `_read_max_lot_ratio_mult` 를 raise 로 monkeypatch → `exception` | 전부 **현행 수량 유지**(폴백이면 1) · `[ratio_cap_skipped]` WARNING 각 1행 · 예외 전파 0. **수량 0 이면 FAIL** |
| **F-11** 클램프 | `_read_max_lot_ratio_mult()`: 키 없음 → **None**(마커 0); 0 / −1 / 0.99 / `"abc"` / None / True / `inf` / `nan` → **2.5** + `[ratio_cap_clamped] raw=…` 1행; 999 → **20.0** + 마커; 1.0 / 2.5 / 20.0 → 그대로 + 마커 **0**. 행위: K=20.0 에서 405,500 → **1**(롤백 다이얼 실증) · K=1.0 에서 129,100 → **0**(=현행 설계 랏 상한) | 하한 제거 뮤테이션(M7) 검출 |
| **F-12** cap 규약 + **행위는 cap 밖** | blocked 같은 (전략,ticker) 2회 → 마커 1행이지만 **두 호출 모두 `== 0`**(cycle237 계약) / 다른 ticker → 각 1행 / skipped 는 (ticker,reason)별 / config·clamped 는 1회/(전략, 값 조합)/일 — 같은 값 반복은 1행이지만 K·예산·`raw` 가 바뀌면 재발화(F-16d/16e/16f) / 두 인스턴스 같은 ticker → 각 1행(인스턴스 격리) / `freeze_time` KST 날짜 경계 → 재발화(자기 리셋) / **cycle242 `_lot_cap_logged` 소진이 cycle245 마커를 막지 않음**(별개 인스턴스) |
| **F-13** peek→로그→mark | `logger.info` 를 `[ratio_notional_blocked]` 문자열에 raise 하도록 monkeypatch → 두 호출 모두 **`== 0`** · 예외 전파 0 · 복원 후 재호출에서 마커 정상 발화(실패 시 mark 미기록). skipped/config/clamped 동형 1케이스씩 |
| **F-14** 폴백 헬퍼 반환값 유통 (기존 Case D 승계) | `_fallback_one_share` 를 **1** 로 patch + price 100,000(≤ cutoff 130,100) → 결과 **1** + `assert_called_once_with(100_000)` · 42 로 patch + price 100,000,000 → **0**(모든 랏 계약 = §3-7) | §4.3 에서 약해지는 커버리지를 여기서 강하게 회복 |
| **F-15** DEFAULT_PARAMS·DB 병합·롤백 | 7전략 `DEFAULT_PARAMS["max_lot_ratio_mult"] == 2.5 == strategy_base._MAX_LOT_RATIO_MULT_DEFAULT` · `scheduler` 병합 관용구(`if key in params: params[key]=val`)로 20.0 주입 → `_read_max_lot_ratio_mult() == 20.0` · 09-04 예산 기준 K=20 컷오프가 5 비터틀 전략 전부 **> 500,000**(`price_filter_max`) | 롤백 다이얼 전제 |
| **F-16** config 마커 | 비터틀 → `[ratio_cap_config] strategy=long_tail_volatility sizing_mode=None cap=on k=2.50 budget=260200 pos_ratio=0.2000 cap_notional=52040 cutoff_price=130100` 1행 · 터틀(ATR 있음) → `cap=backstop` · 키 부재 → `cap=off k=-` · `final<1`(price 0) 호출에선 **미발화** |
| **F-17** `[oversized_fallback]` 의미 전환 + R7 | (a) 차단된 랏도 `[oversized_fallback]` 1행 (b) 포맷 문자열 byte 불변(`"1주 폴백이 notional 상한 초과 (관측 전용)"` 부분문자열 + `"3.10" in message` 형 검사 재확인) (c) **R7 불변식**: 비터틀 그리드 전수에서 살아남은 랏의 `[oversized_fallback] ratio` ≤ K_ρ(=2.50) |
| **F-18** cycle242 마커 생존 | turtle donchian/kojiro 에서 `[fallback_cap_config]`/`[fallback_cap_skipped]`/`[fallback_notional_capped]` 3종이 cycle245 도입 후에도 동일 발화 | 배치를 `_apply_lot_units_cap` 앞으로 옮기는 뮤테이션(M4) 검출 |
| **F-19** 기존 회귀 | §5 표적 목록 | §4.3 3파일 외 **무수정 PASS**(시뮬레이션 실측 4,260 + 1,968) |
| **F-20** order_engine 오귀인(읽기만) | `execute_buy` 가 `calc_buy_quantity` 0 에 `block_low_funds` 900s + "투자금 부족" WARNING 을 거는 기존 테스트 존재 확인(신규 작성 0) — §7 오귀인 항목의 근거 | 8영역 무접촉 |

### 4.2 `tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py` (신규 — `parents[3]`, cycle212 `_collect_named_literal_str_keys` 헬퍼 로컬 복제)

| ID | 검사 | 뮤테이션 표적 |
|---|---|---|
| G-245-1 | `"max_lot_ratio_mult"` ∉ `rec_mod.PARAM_RANGES`/`INT_PARAMS`(런타임) ∧ ∉ `recommendation_engine.py` 소스의 `PARAM_RANGES` dict / `INT_PARAMS` set 리터럴 str 키 + self-test 앵커(`"volume_multiplier"` 는 검출됨) | AI 자문 편입 |
| G-245-2 | A-PURE 확장 — `StrategyBase` 소스의 함수 집합 {`_apply_ratio_notional_cap`, `_read_max_lot_ratio_mult`, `_lot_units_cap_governs`, `_emit_ratio_notional_blocked`, `_emit_ratio_cap_skipped`, `_emit_ratio_cap_config`, `_emit_ratio_cap_clamped`} 각각 `ast.Await` 0 ∧ 금지 import(`src.db`,`httpx`,`requests`,`asyncio`,`aiohttp`) 0 ∧ **함수가 전부 존재**(부재 = FAIL) | 헬퍼로 빼서 await 유입 |
| G-245-3 | `_apply_budget_limit` 본문 lineno 순서: `_fallback_one_share` < `_emit_budget_clamp` < `_apply_lot_units_cap` < `_emit_oversized_fallback` < **`_apply_ratio_notional_cap`** < 마지막 `Return` ∧ `_apply_ratio_notional_cap` 호출 **정확 1회** ∧ 결과가 `final` 에 대입(`Assign` target `final`) | 캡 위치 이동·미대입·중복 호출 |
| G-245-4 | `_apply_ratio_notional_cap` 본문: 최상위가 `Try`(handler `except Exception`) ∧ `_lot_units_cap_governs` 호출 존재 ∧ `_read_max_lot_ratio_mult` 호출 존재 ∧ `"position_ratio"` 상수 존재 ∧ **`compute_unit_qty` 호출 0 ∧ `fraction=` kwarg 0 ∧ `"atr"`/`"atr14"` 상수 0**(K축 수식 혼입 금지) ∧ `>` 비교로 차단(`GtE` 로 바꾸면 F-2 가 잡되 구조도 핀) | 새 수식·try 제거·축 혼입 |
| G-245-5 | 신규 emit 4 + `_emit_oversized_fallback`: 같은 함수 안에서 `should_emit` lineno < `logger.*` lineno < `mark_emitted` lineno | mark-before-log |
| G-245-6 | `src/engine/strategies/*.py`(**glob**, `__init__.py` 제외) **전수**의 `DEFAULT_PARAMS` 리터럴에 `"max_lot_ratio_mult"` 존재 ∧ 값 == `strategy_base._MAX_LOT_RATIO_MULT_DEFAULT` ∧ `_MIN == 1.0` ∧ `_MAX == 20.0` ∧ MIN ≤ DEFAULT ≤ MAX ∧ 파일 수 ≥ 7 | 기본값 불일치·하한 완화·**신규 8번째 전략의 무방비 편입** |
| G-245-7 | 7 전략 파일 `calc_buy_quantity`·터틀 사이징 함수 노드 안에 `max_lot_ratio_mult` 토큰 0 ∧ 기존 A-GATE 재확인(모든 return 관문 경유) | 캡 로직 전략 누출 |
| G-245-8 | `_lot_units_cap_governs` 본문: `_candidates` 대상 쓰기(`Subscript` 대입/`setdefault`/`pop`/`update`) 0 ∧ `logger` 호출 **0**(판정기는 무음) ∧ `"turtle"` 상수 존재 ∧ `_resolve_sizing_atr` 호출 존재 ∧ `"risk_pct"`·`total_investment` 참조 존재(cycle242 4조건 동일 소스) | 판정 드리프트·쓰기 유입·로그 폭주 |
| G-245-9 | `strategy_base.py` 의 `[ratio_notional_blocked]`/`[ratio_cap_skipped]`/`[ratio_cap_config]`/`[ratio_cap_clamped]` 문자열 상수 각 ≥1 ∧ 각 emit 사이트가 `Try` 하위 ∧ cycle72 동형 `write_log` 근접 호출 0 ∧ 네 마커가 `_ratio_cap_logged` 를 쓰고 `_lot_cap_logged` 는 **쓰지 않음**(cap 인스턴스 분리) | 예외 전파·이중 INSERT·cap 혼용 |
| G-245-10 | `_emit_oversized_fallback` 의 `logger.info` 포맷 문자열 리터럴이 **정확히** `"[oversized_fallback] ticker=%s strategy=%s qty=%d notional=%d cap=%d ratio=%.2f — 1주 폴백이 notional 상한 초과 (관측 전용) units=%s"`(암묵 연결 후) ∧ `_emit_oversized_fallback` 호출이 `_apply_ratio_notional_cap` 호출보다 **앞** | 서식 변조·관측 뒤 배치(차단 사건 관측 소실) |

**기존 가드 재작성 금지** — 표적 실행에 포함만: `test_budget_limit_ast.py`(A-ATOMIC/A-PURE/A-GATE/C-*) · `test_cycle242_ast_fallback_notional_cap.py`(G-242-1~9) · cycle226 `test_common_1_eight_areas_untouched` · cycle222a3 anchor/owner · cycle223 exit fix · cycle233 account risk · cycle198/211 DEFAULT_PARAMS scope · cycle209/212 PARAM_RANGES · cycle223f manual apply.

### 4.3 기존 테스트 개정 (**시뮬레이션 실측 18 케이스 · 3 파일** — 그 외 전 스위트 무수정)

> 캡을 pytest 플러그인으로 주입해 전수 실행한 결과다. **cycle233·cycle242 파일은 목록에 없다**(결정 ⑤·⑨ 덕분에 무수정 통과).

**(1) `tests/unit/engine/strategies/test_momentum.py::test_calc_qty_when_ratio_zero_but_total_covers_one_share_then_one`** (1건)
`total_investment = 100_000` → `cap 25,000` → `cutoff 62,500 < 100,000` → 0.
**수정** = `total_investment` **100,000 → 200,000**(주석 `ratio 25% = 50k → 100k 가격 → 0주`). `cap 50,000` · `cutoff 125,000 ≥ 100,000` → 1. 비중 기준 0주(`50,000//100,000 = 0`)·잔여 충분이라는 **테스트 의도 그대로**.

**(2) `tests/unit/engine/strategies/test_volatility_breakout.py::test_calc_qty_when_ratio_zero_but_total_covers_one_share`** (1건)
`total 100,000` → `cutoff 25,000 < 50,000` → 0.
**수정** = `total_investment` **100,000 → 250,000**(주석 `10% = 25k`). `cutoff 62,500 ≥ 50,000` → 1. 의도 보존.

**(3) `tests/unit/engine/test_budget_limit_gate.py::test_fallback_helper_still_invoked_for_zero_ratio_qty`** (7건 — 전 전략 파라미터화)
`_build(total=10_000)` + `_fallback_one_share` → 42 patch + price 100,000,000 → 42 × 1억 = 4.2조 명목이라 어떤 K 로도 차단 → 0.
**수정** = `mock_helper.assert_called_once_with(100_000_000)` **그대로 유지**(이 테스트의 진짜 계약 = 분기 순서/위임)하고 `assert result == sentinel` → `assert result == 0` + 주석:
> *"cycle245 — 위임은 그대로이나 반환값은 ρ캡을 통과한다. 모킹된 42주 × 1억원 = ρ상한의 천문학적 배수라 캡이 0 으로 자른다(§3-7 '모든 랏' 계약의 직접 증거). 헬퍼 반환값이 그대로 유통되는 계약은 `test_cycle245_ratio_notional_cap.py` F-14 가 캡 비바인딩 조건에서 강하게 검증한다."*
⚠️ **`_fallback_one_share` 에 인자를 추가하거나 캡을 그 안에 넣지 말 것** — `assert_called_once_with(100_000_000)` 이 깨지거나 캡이 patch 로 우회된다(§0 정정 ④).

**(4) `tests/unit/engine/test_strategy_fallback_budget.py`** (9건)
- `::test_fallback_when_no_usage_then_returns_one` (4건) — `total 1,000,000` price 800,000 은 momentum(cutoff 625,000)·VB(250,000)·LTV(375,000)·donchian(500,000) 전부 초과.
  **수정** = 가격을 전략 비중에서 도출: `ratio = s.config.params["position_ratio"]; price = int(s.state.total_investment * ratio) + 1` 로 호출.
  검산 — momentum 250,001(cutoff 625,000) · VB 100,001(250,000) · LTV 150,001(375,000) · donchian 200,001(500,000) → **전부 1주**, 비중 기준은 0주(`int(t×r)//price == 0`), 잔여 1,000,000 ≥ price. **"비중계산 0주 + 잔여 충분 → 1주 폴백"이라는 원 의도를 오히려 더 정확히 표현한다.**
- `::test_fallback_uses_common_helper` (4건) — (3)과 동형(sentinel 42 · price 1억). **동일 수정**(`== sentinel` → `== 0`, `assert_called_once_with` 유지, 같은 주석).
- `::test_fallback_isolated_per_strategy_state` (1건) — VB `total 1,000,000` price 600,000 > cutoff 250,000.
  **수정** = price **600,000 → 200,000**(주석 `ratio=10% → amount=100k, qty=0` 유지, 마지막 주석을 `잔여 = 1M >= 200k → 1주 폴백`). 비중 0주(`100,000//200,000=0`) · cutoff 250,000 ≥ 200,000 → 1. **momentum 노이즈 격리라는 원 의도 무손상.**
- 같은 파일 Case B/C(잔여 부족 → 0)·`_calc_used_funds`·`_fallback_one_share` 직접 테스트는 **무수정**(잔여 검사가 먼저 0 을 만든다).

**(5) 모듈 docstring 재스코프 (assertion 무변경, 선택)**
- `test_cycle233_oversized_fallback.py` 모듈 docstring: *"`position_ratio` 모드에서 수량 0 = 오구현"* → *"**관측기(`_emit_oversized_fallback`)가** 수량을 바꾸면 오구현. cycle245(2026-09-04)가 같은 ρ축에 **별도 헬퍼**로 차단 행위를 도입했으나 본 파일 픽스처는 `max_lot_ratio_mult` 키가 없어 캡 OFF 경로라 6 케이스 assertion 은 byte 무변경으로 유효하다. 이 마커의 의미는 '실제로 산 랏' → '사려 했던 랏' 으로 전환됐다."* (자문 §5.1 C2 부수 권고)

---

## 5. Green 범위

- `src/engine/strategy_base.py`: §2.1 상수 3 · §2.2 `__init__` 속성 2 · §2.3 관문 1줄 삽입 + docstring · §2.4 헬퍼 6 · §2.5 docstring. 예상 **+180L 안팎**(이 파일엔 라인 상한 없음).
- 전략 **7파일**: `DEFAULT_PARAMS` 1줄씩(§2.6). **그 외 diff 0**(G-245-7 + `git diff --stat` 각 +1/−0 확인).
- 신규 테스트 2파일(§4.1·§4.2) + 기존 3파일 개정(§4.3). 인덱스 `python tools/test_impact/build_index.py`.
- **무접촉 기대**: 8영역 · `scheduler.py` · `boot_manager.py` · `turtle_sizing.py` · `portfolio_risk.py` · `recommendation_engine.py` · `routes/*` · `StrategyState` · 전략 `check_exit_signal`/`calc_buy_quantity`/터틀 사이징 본문 · **cycle242 헬퍼·마커 전부**.
- 표적 실행(Green 후):
  `python -m pytest -q -p no:cacheprovider tests/unit/engine/test_cycle245_ratio_notional_cap.py tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py tests/unit/engine/test_cycle242_fallback_notional_cap.py tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py tests/unit/engine/test_cycle233_oversized_fallback.py tests/unit/engine/test_budget_limit_gate.py tests/unit/engine/test_strategy_fallback_budget.py tests/unit/ast/test_budget_limit_ast.py tests/unit/engine/test_budget_invariant_runtime_guard.py tests/unit/engine/test_cycle233_account_risk_gate.py tests/unit/engine/strategies/ tests/unit/ast/ tests/integration/test_buy_block_low_funds.py tests/integration/test_reset_daily_state.py`
- **전체 스위트는 Docs 단계 1회.** 기준선 = cycle242 Docs 시점 **6,163 passed, 10 skipped, 328 xfailed, 13 xpassed** + cycle243/244 분 + 신규분.
- Green 중 `len(caplog.records) == N` 형 정확 개수 단언이 신규 `[ratio_cap_config]` INFO 1행 때문에 트립하면 **그 테스트에 prefix 필터를 넣는 적응만** 허용(의미 무변경) — 마커를 `debug` 로 낮추는 우회 금지(감지 목적 소멸). *실측상 그런 단언은 저장소에 0건이다(`grep "len(caplog.records)"` → 무관 1건).*

---

## 6. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| M1 | `final = self._apply_ratio_notional_cap(...)` 라인 삭제 | F-1/F-3/F-5 FAIL + G-245-3 |
| M2 | 차단 비교 `>` → `>=` (경계) | F-2 (130,100 → 0) FAIL + G-245-4 |
| M3 | 캡 호출을 `_emit_oversized_fallback` **앞**으로 이동 | F-1 (`[oversized_fallback]` 0행) FAIL + G-245-3/G-245-10 |
| M4 | 캡 호출을 `_apply_lot_units_cap` **앞**으로 이동 | F-18 + cycle242 F-13/F-1 FAIL + G-245-3 |
| M5 | `_lot_units_cap_governs` 호출 제거(터틀에도 ρ 적용 = `min` 합성) | F-7b FAIL(K축 심사 랏이 잘림) + 블록째 삭제 시 F-10d 동반. ⚠️ **cycle242 는 0 failed**(라운드 2 실측 §12-1 — 종전 이 칸의 "cycle242 F-6c/6d FAIL" 은 M6 의 결과를 잘못 옮긴 것) |
| M6 | `_lot_units_cap_governs` 를 `mode != "turtle"` 단일 조건으로 축소(자문 원안) | F-8 FAIL + **cycle242 F-6c(VB·LTV)/F-6d(donchian·vcp) FAIL** ← §0 정정 ① 의 실증 재현 |
| M7 | `_MAX_LOT_RATIO_MULT_MIN = 0.5` | F-11(0.99 → 2.5) FAIL + G-245-6 |
| M8 | 키 부재 시 기본값 적용(ON) | F-6 FAIL + **cycle233 6케이스 + cycle242 F-6a FAIL** |
| M9 | `cap = int(B*ρ)` → `B*ρ`(float) 또는 `cutoff = K*cap`(float) | F-2 경계 · F-1 마커 정수 필드 FAIL |
| M10 | `mark_emitted` 를 logger 앞으로 | F-13 FAIL + G-245-5 |
| M11 | `DailyEmitCap` 제거(매 호출 로그) / 날짜 키 제거 / cycle242 `_lot_cap_logged` 재사용 | F-12 FAIL + G-245-9 |
| M12 | fail-open 분기를 `return 0` 으로(fail-closed) | F-10 FAIL (P0-1 재현 방지 가드) |
| M13 | 캡을 `via_fallback` 또는 `final == 1` 에만 적용(스코프 축소) | F-5/F-14(42주 케이스) FAIL |
| M14 | 전략 `calc_buy_quantity` 에 `if price > cutoff: return 0` 조기 반환 | A-GATE + G-245-7 |
| M15 | `_lot_units_cap_governs` 에 `logger.warning` 추가 | G-245-8 |
| M16 | `_emit_oversized_fallback` 포맷 문자열 수정 | G-245-10 + cycle233 `"3.10" in message` |
| M17 | 8영역·scheduler 1줄 | cycle226 가드 |

**추가 렌즈**
1. **차분 실증** — 캡 off 입력(키 제거 7전략 × 가격/예산/ratio 그리드 3,000 조합)에서 `calc_buy_quantity` 결과가 HEAD 와 **동일**(행위 변경은 `governs=False ∧ notional > cutoff` 구간에만).
2. **터틀 무접촉 실증** — donchian/kojiro turtle + ATR 있는 그리드에서 결과가 cycle242 HEAD 와 **동일**.
3. `git diff HEAD --name-only` ⊆ §5 허용 목록 · 전략 7파일 `git diff --stat` 각 +1/−0.
4. **8영역 diff 0** · `wc -l src/engine/scheduler.py` 불변.
5. **비용** — 관문당 추가 연산 = dict 조회 ≤4 + 정수 곱/나눗셈 3 + (터틀일 때만) `_resolve_sizing_atr` 1회. hot path 아님(매수 시도당 1회).
6. **M6·M8 을 사본 저장소에서 실제 주입해 FAIL 실증**(실트리 미접촉, cycle240 §10.2 규약) — 특히 M6 은 이 사이클 설계 결정의 근거이므로 재현 필수.
7. **`_calc_used_funds` 상호작용** — 캡이 0 을 반환해도 `pending_buy_amounts` 에 아무것도 안 들어가는지(누수 0) 확인(자문 §9.4).
8. **`order_engine` low-funds 락** — `quantity == 0` 이 900초 락 + "투자금 부족" WARNING 을 유발하는 것이 **기존 행위와 동일**(신규 결함 아님)한지 읽기만으로 확인. 8영역 무접촉.

---

## 7. D+1 판독 채널 (배포 = 15:30 이후 NXT 애프터 또는 익일 07:55 `_boot` 전)

| 채널 | 정상 서명 | 이상 서명 → 해석 |
|---|---|---|
| `[ratio_cap_config]` | 매수 시도가 있는 전략마다 1행/일. **비터틀 5전략 = `cap=on k=2.50`**, `cutoff_price` 가 §0-② 표와 일치(LTV/VCP 130,100 · VB 341,515 · BFB 243,940 · MOM 81,312). donchian/kojiro = `cap=backstop`. cap 키가 **값-민감**(`cap상태\|k\|cutoff`, 라운드 1 시정)이라 K 나 예산이 실제로 바뀐 날에만 2행째가 붙는다 | 비터틀에 `cap=off` = **키가 사라짐**(조용한 꺼짐) → 즉시 DB/코드 확인. `k≠2.50` 2행째 = 누가 PUT 으로 바꿨다(= 롤백을 실행했다면 **여기서 확인한다**). `cutoff_price` 만 바뀐 2행째 = `weight`/`cash_usage_ratio` 변경으로 예산이 재분배됨 |
| `[ratio_notional_blocked]` | **LTV 0~1건/일**(기대 0.33건/일 = 주 1.65건), 나머지 4전략 0. `path=fallback` 우세, `capped_qty=0` 우세, `ratio` 2.5~4.5 | **BFB/VCP 는 배포 전 선반영으로 0 이어야 한다**(아래 §7.1 필수 조치 — 사후 R2 로는 늦다: 두 전략은 차단 시점에 이미 `_bought_today` 가 소진돼 **당일 표본이 영구 소실**된다). LTV 주 3건↑ = R1. **`capped_qty > 0` = 축소 발생** — 현행 7 전략 호출부에서는 도달 불가(F-4 항등식)이므로 구조 이상 → R7 조사. ⚠️ **한 종목이 하루에 여러 번 차단돼도 이 마커는 1행뿐**(cap 1회/(전략,ticker)/일) — 건수를 랏 수로 읽지 마라 |
| `[ratio_cap_skipped]` | **0행** | `reason=no_ratio`/`no_budget`/`no_cap` ≥1 = 예산 배분 결함(캡은 fail-open 이라 매수는 현행대로 나감) / `k_axis_probe_error`·`exception` ≥1 = **코드 결함, 즉시 조사** |
| `[ratio_cap_clamped]` | **0행** | ≥1 = DB/PUT 으로 범위 밖 값 유입. `raw=` 값으로 출처 판정 |
| `[oversized_fallback]` | **0 으로 수렴하지 않는다**(K_ρ≥1 이므로 배수 1.0~K_ρ 구간은 계속 통과·관측). 배포 후 이 마커는 **배수 ≤K_ρ 구간 + 차단된 랏 + K축이 심사한 터틀 랏**만 남는다 | **R7 자기검증(라운드 1 재작성)**: `ratio` 가 **그날 그 전략의 `[ratio_cap_config] k=` 값**(리터럴 2.50 아님 — 롤백으로 20.0 이 될 수 있다)을 넘는데 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` **도** `[ratio_cap_skipped]` **도** 없고 그 전략의 `[ratio_cap_config] cap=on` 이면 **캡 우회 = 결함**. `cap=backstop`(터틀) 행은 **정상**이다 — K축이 심사한 랏은 ρ 항등식 밖이고(§3-7b) 실측 3.86~5.00배가 알려진 잔여 노출(§8 F-9)이다. ⚠️ **09-04 이전 로그와 합산 금지**(의미 전환: "실제로 산 랏" → "사려 했던 랏") |
| cycle242 마커 3종 | `[fallback_cap_config]` donchian/kojiro 2행(`cap=on k=2.00`) + skipped 0 + capped 0 | **사라지면 배치 오류**(§0 결정 ⑥ 위반) — 즉시 롤백 |
| LTV 일별 매수 건수 | 기준선 1.25랏/일 → 예상 **~0.9랏/일** | **10영업일 0 = R3** → K 상향 또는 `position_ratio`/`weight` 재검토. ⚠️ 기대치는 낙관 쪽으로 치우쳐 있다 — LTV·VB·momentum 은 **edge-crossing**(`prev < target ∧ current ≥ target`)이라 차단된 교차는 **소비**되고(`_prev_price` 가 이미 target 위로 갱신됨) `is_low_funds_blocked` 900초 동안 `check_buy_signal` 자체를 건너뛰어 baseline 도 동결된다. 즉 차단은 랏 1건이 아니라 **그 교차 사건**을 없앤다 |
| `order_engine` "매수 수량 0 → 900s cooldown (투자금: …)" | 차단 마커와 같은 (전략,ticker,일자)에 **짝지어** 나타남 = 오귀인 정상 서명. ⚠️ **짝은 1:1 이 아니라 1:N 이다**(라운드 1 정정) | **판독 규칙**: 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` 가 **한 행이라도** 있으면 그날 그 종목의 **모든** 수량-0 WARNING 을 캡 귀속으로 읽는다. `_bought_today` 종목당 1회/일 가드는 **VCP·kojiro·donchian·BFB 에만** 있고 이번 사이클의 표적 3전략(LTV·VB·momentum)에는 **없다** — 900s 만료 또는 `_sync_positions_from_balance`(3회 스캔 ≈15분)의 `clear_low_funds()` 로 같은 종목이 하루 3~4번 재시도한다(EC2 실측: LTV 095610 08-27 **4행** · 131290 08-24 **3행**). 반면 캡 마커는 1회/(전략,ticker)/일이라 2행째부터는 **캡 마커 없이 단독**으로 보인다 — 그걸 "진짜 잔여 부족"으로 분류하면 오귀인이다 |
| 보유 포지션 | **무영향**(진입 사이징만 — 청산·손절 경로 diff 0) | — |
| **20:10 일일 리포트** | 네 마커 중 **어느 것도 리포트에 실리지 않는다** — `log_analysis_engine._aggregate_log_patterns` 는 `{WARNING, ERROR, CRITICAL}` 만 패턴 집계하고 INFO 는 `by_level` 총계에만 +1 한다. `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 **INFO** 라 payload 에 한 글자도 안 들어간다 | ⚠️ **반대로 오귀인의 원인인 "매수 수량 0 → 900s cooldown" 은 WARNING 이라 `top_patterns` 에 오른다** — 리포트만 읽으면 "투자금 부족 급증" 결론이 나고 반증 자료는 보이지 않는다. **이 사이클의 판독은 `system_logs` 직접 조회가 유일 채널이다**(`[ratio_cap_skipped]`·`[ratio_cap_clamped]` 는 WARNING 이라 리포트에 뜬다 = 이상 신호만 리포트에 뜨는 셈). 리포트 집계 편입은 §8 후속 **F-12** |

⚠️ **의미 전환 2** — (1) `[oversized_fallback]` 은 "실제로 산 랏"에서 **"사려 했던 랏"** 으로, (2) `order_engine` 수량-0 WARNING 은 "잔고 부족"에서 **"ρ캡 차단 포함"** 으로. 배포 전후 같은 grep 합산 금지(cycle228/240/241/242 교훈).

### 7.1 배포 전 **필수 조치** — BFB·VCP `max_lot_ratio_mult = 20.0` 선반영 (라운드 1 신설)

배포 직전(같은 창)에 **코드가 아니라 DB 한 줄**로 두 전략만 캡을 사실상 끈다. 코드 기본값을
전략별로 다르게 두는 길은 없다 — 결정 ②(전 전략 균일)와 AST **G-245-6**(전략 파일 glob 전수의
`DEFAULT_PARAMS` 값 == `_MAX_LOT_RATIO_MULT_DEFAULT`)이 그것을 금지한다.

```sql
UPDATE strategy_config
   SET params = jsonb_set(params, '{max_lot_ratio_mult}', '20.0'::jsonb, true)
 WHERE strategy_id IN ('bull_flag_breakout', 'vcp_breakout');
```
⚠️ **배포 전 경로는 이 SQL 하나뿐이다 — `PUT /api/strategies/{id}/params` 는 배포 *전* 에 무음
실패한다**(라운드 2 확증 #3). 라우트가 `if key in strategy.config.params` 로 **미지 키를 조용히
버리고** `success=true` 를 돌려주는데(`src/routes/strategies.py:175-182`, 적용된 키 목록도 경고도
응답에 없다), `max_lot_ratio_mult` 는 이 사이클이 `DEFAULT_PARAMS` 에 **신설**하는 키라 배포 전
구코드의 in-memory params 에는 없다. 게다가 그 뒤 `save_params` 가 `params` JSONB 를 **통째로**
덮으므로(`src/db/strategy_config.py::save` = `params = EXCLUDED.params`) **먼저 넣어둔 SQL 값까지
지운다** ⇒ SQL 선반영 후 배포까지 그 두 전략에 **어떤 PUT 도 하지 마라**(다른 파라미터를 고치는
PUT 이라도 같은 소거가 일어난다).

- **배포 전 확인** = `SELECT params->'max_lot_ratio_mult' FROM strategy_config WHERE strategy_id IN (…)`
  (구코드에는 `[ratio_cap_config]` 마커 자체가 없어 로그로는 확인 불가).
- **배포 후 확인** = 다음 매수 시도의 `[ratio_cap_config] … k=20.00` — cap 키가 값-민감이라
  **변경이 실제로 로그에 남는다**.
- **배포 후**에는 PUT 이 정본 수단이다(§8 롤백 수단 — 장중 실효 경로는 PUT 뿐). 회귀 F-21b/F-21b2.

**근거** — 사후 대응(R2)으로는 늦다.

| 사실 | 실측 |
|---|---|
| 라이브 파라미터가 두 전략을 **ρ캡 ON** 으로 만든다 | `strategy_config` 실측 BFB `pr 0.25 / sizing_mode='position_ratio'` · VCP `pr 0.20 / 'position_ratio'` → `_lot_units_cap_governs` = False. probe 로그 `[ratio_cap_config] strategy=vcp_breakout … cap=on k=2.50 cutoff_price=130100` · `strategy=bull_flag_breakout … cutoff_price=243940` |
| 컷오프가 유니버스를 **가격만으로** 자른다 | VCP/BFB `_scan_universe` 필터 재현(시총≥500억 ∩ 거래대금≥10억 ∩ 6자리 숫자 ∩ price≤500,000) = **913종목**. 컷오프 초과 = VCP(130,100) **91종목 10.0%** / BFB(243,940) **32종목 3.5%**. 설계 랏 초과(= 1주 폴백 경로) VCP 251 종목 기준으로는 **36%(91/251)** 가 매수 불가 |
| 차단이 **표본을 지운다**(랏 1건이 아니라) | BFB `_evaluate_vol_gate` 는 `return Signal.BUY`(`bull_flag_breakout.py:1120`) **이전에** `:1090 _vol_latch.pop` · `:1093 _bought_today.add` · `:1096 _position_setup[ticker]=…` 를 실행한다. VCP 동형(`vcp_breakout.py:1158/1160/1163`). ρ캡이 0 을 돌려주면 주문은 안 나가는데 그 종목은 그날 `:922`/`:1039` 의 `if ticker in self._bought_today: return Signal.NONE` 로 **영구 차단**되고 `_vol_latch` 재무장 상태까지 사라진다. `_position_setup` 은 `on_position_closed` 에서만 pop 되므로 유령 stamp 도 남는다 |
| 두 전략은 **표본 수집 중**이다 | cycle228 이 8사이클 걸려 매수를 연 뒤 실측 체결률 ≈**0.5건/일**, N=10 목표(루트 CLAUDE.md 배너). 10%·3.5% 를 가격만으로 깎으면 그 실험의 결론이 바뀐다 |

⚠️ **VB 는 선반영 대상이 아니다** — 컷오프 341,515 는 같은 유니버스의 **2.2%(20종목)** 만
넘고, 90일 실측 차단 0건(§0-②)과 정합한다. 브리프 ③이 우려한 "VB 재검정 지연"은 실현되지 않는다.

**해제 조건** = BFB·VCP 의 N=10 표본이 모여 완화 실험이 종결되면 `max_lot_ratio_mult` 를 지워
(= DB 키 삭제로 기본 2.5 복귀) 다시 캡을 받게 한다. ⚠️ **DB 키 삭제 역시 다음 재시작에서만 반영된다**
(§8 롤백 표 — 병합 관용구가 `if key in params` 라 키가 없으면 in-memory 기본값이 남고, 그 in-memory 는
프로세스당 1회만 갱신된다). 장중에 즉시 되돌리려면 `PUT … {"max_lot_ratio_mult": 2.5}` 를 함께 친다. 그 전까지 두 전략은 **캡 없는 상태**이므로
`[oversized_fallback] ratio > 2.50` 행이 두 전략에서 계속 나오는 것이 **정상**이다(R7 이 그것을
`[ratio_cap_config] k=20.00` 과 대조해 정상으로 판정한다).

---

## 8. 후속 등재 (이번 사이클 밖) + 재검토 트리거

**롤백 수단** = 대상 전략의 `max_lot_ratio_mult` 를 `20.0` 으로. 둘 다 **코드 재배포는 불필요**하지만
**반영 시점이 다르다**(라운드 2 확증 #2 — 종전 문안은 두 수단을 동등하게 적어 SQL 경로에 대해 거짓이었다).

| 수단 | 반영 시점 | 근거 |
|---|---|---|
| `PUT /api/strategies/{id}/params` (K=20.0) | **즉시** — 다음 랏부터 | 라우트가 `strategy.config.params[key] = value` 로 in-memory 를 덮고 `save_params` 로 영속화(`src/routes/strategies.py:175-182`). **단 배포 후에만** — 배포 전에는 키가 없어 무음 실패(§7.1). 회귀 F-21b2 |
| `UPDATE strategy_config … jsonb_set(…, true)` | **다음 백엔드 재시작에서만** | `_load_strategy_config` 이 `_config_loaded` **프로세스당 1회** 가드이고 리셋 지점이 0 이라(`src/engine/scheduler.py:405-408`, 대입 `:414`/`:458`, 초기화 `:367`) 호출자 2곳(`src/main.py:259` 서버 기동 · `src/engine/boot_manager.py:58` 07:55 `_boot`) 중 **07:55 호출은 no-op** 이다 — DB 를 읽지도 않는다. 회귀 F-21a/F-21a2 |

⚠️ **장중(09:00~15:30) 실효 수단은 PUT 뿐이다.** R1(LTV 주 3건 초과)·R2(BFB/VCP 표본 훼손)는 장중에
발동하는 트리거인데, SQL 경로가 요구하는 재시작을 루트 `CLAUDE.md` 의 cycle232 D6(보유 포지션이 있으면
09:00~15:30 재시작 금지 — 재시작 1~5분 tick blind = 손절 사각)이 금지한다. SQL 은 장 종료 후 반영용으로,
PUT 은 즉시 지혈용으로 쓴다(둘 다 하면 DB 와 in-memory 가 함께 20.0 이라 안전).

K=20 이면 09-04 예산 기준 5 비터틀 전략 컷오프가 전부 `price_filter_max`(500,000) 를 넘어 **사실상 현행 복귀**.
⚠️ 한계 = 순자산이 크게 줄면 momentum 컷오프(20×0.25×예산)가 500,000 아래로 내려올 수 있다 — 그때는 K=20 도 완전 복귀가 아니다.

| # | 트리거 | 임계 | 조치 |
|---|---|---|---|
| **R1** | LTV 과잉 차단 | `[ratio_notional_blocked]` LTV **주 3건 이상**(기대 1.65건/주) | K_ρ 3.0 상향(사용자 결정) |
| **R2** | **완화 실험 표본 훼손** | BFB·VCP 에서 **1건이라도** 차단 | ⚠️ **사후 트리거로는 늦다 — §7.1 배포 전 선반영이 정본 조치다**(라운드 1 정정). 두 전략은 `check_buy_signal` 안에서 **주문 이전에** `_bought_today.add` 를 하므로 차단 1건 = 그 종목 **당일 표본 영구 소실** + `_vol_latch` 재무장 상실이다. R2 가 남는 것은 선반영이 누락됐거나 DB 값이 되돌아간 경우의 **감지 채널**로서다 — 발동 시 즉시 K=20.0 재적용 + 그날 소실된 (전략,ticker) 목록을 `[ratio_notional_blocked]` 로 회수해 실험 표본에서 제외 표시 |
| **R3** | 컷오프가 유니버스를 잘랐다 | LTV **10영업일 매수 0** | K 상향 또는 `position_ratio`/`weight` 재검토. ⚠️ 이 트리거는 스펙이 상정한 것보다 **쉽게 걸린다**(라운드 1) — LTV 는 edge-crossing 이라 차단이 랏이 아니라 **교차 사건**을 소비하고(`_prev_price` 가 target 위로 갱신됨) 900s low-funds 락 동안 `check_buy_signal` 이 아예 건너뛰어져 baseline 도 동결된다. 재진입은 target 아래로 되돌아갔다 다시 위로 교차해야 성립한다 |
| **R4** | momentum 과잉 | 매수 재개 후 차단률 50% 초과 | momentum `weight` 0.05 재검토(K 가 아니라 — ρ상한 32,525 가 유니버스 중앙값의 1.8배뿐) |
| **R5** | 자연 무해화 | **20영업일 발화 0** | 순자산 증가로 컷오프가 자동 상승한 것 = **정상**. 게이트 유지(자본이 줄면 다시 필요), 삭제 금지 |
| **R6** | 오귀인 확대 | ~~"투자금 부족" WARNING 하루 10건 초과~~ → **재정의(라운드 1)**: 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` 가 **한 행도 없는** 수량-0 WARNING 의 **distinct (전략,ticker) 수**가 하루 3 초과 | 종전 절대 건수 임계는 **측정 대상이 어긋나 있었다** — 세는 것이 '차단된 랏 수'가 아니라 '같은 종목의 재시도 반복 수'(LTV·VB·momentum 은 `_bought_today` 가 없어 15분 주기로 재시도, 실측 종목당 3~4행)이고 현행 baseline 이 이미 8건(08-19)이다. 발동 시 사유 분기 후속(아래 F-3) 우선순위 상향 |
| **R7** | **캡 우회 = 결함** | `[oversized_fallback].ratio` > **그날 그 전략의 `[ratio_cap_config] k=` 값** ∧ 그 전략의 `cap=on` ∧ 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` **도** `[ratio_cap_skipped]` **도 없음** — 1건 | 즉시 조사·핫픽스. ⚠️ 리터럴 2.50 을 쓰지 마라(라운드 1 정정) — 이 문서가 처방하는 롤백(R1 K=3.0 / §7.1 BFB·VCP K=20.0)을 실행하는 순간 리터럴 판정은 **상시 오탐 생성기**가 된다. `cap=backstop`(터틀) 행은 판정 대상이 아니다(§3-7b 잔여 노출 = F-9). fail-open 5사유(`no_ratio`/`no_budget`/`no_cap`/`k_axis_probe_error`/`exception`)는 `[ratio_cap_skipped]` 짝으로 제외된다 |
| **R8** | 파라미터 커플링 | `weight` / `position_ratio` / `cash_usage_ratio` 변경 | 컷오프가 예산에 **선형 비례** → K 재검토 의무. 특히 VB `position_ratio` 0.35 조정 시 |

**후속**
- **F-1. `price_filter_max` 500,000 → 250,000 (사용자 결정 사항).** 코드 0줄·재배포 불필요이고 최악 랏을 순자산 19.2% → 9.6% 로 절반 낮춘다(유니버스 추가 배제 ~3%p). **단 전 전략 공통**이라 kojiro(예산 780,611, 보유 000815 405,500)·donchian 의 정상 매수를 동시에 자른다 — **터틀 2전략 영향 평가 선행 필수**.
- **F-2. VB `position_ratio = 0.35` 재검토(별건).** VB 설계 랏이 순자산 **5.25%** 로 유일하게 크고 K=2.5 에서 13.1% 라 **어떤 K 로도 정책선(10%) 안에 못 들어온다.** 코드 기본값 0.10 의 3.5배 = DB 이탈값. 고칠 곳은 K 가 아니라 ratio/weight.
- **F-3. `order_engine` 수량-0 오귀인 사유 분기.** "투자금 부족" WARNING + 900s 락이 ρ캡 차단에도 걸린다. 사유를 넘기려면 `calc_buy_quantity` 반환 계약 변경이 필요해 **8영역 별도 승인 사이클**.
- **F-4. 프리장 한정 더 낮은 K(자문 §6-4).** LTV 최악 랏 2건이 모두 08:1x PRE_NXT 매수이고 프리장 3건이 LTV 손실의 **88%** 를 차지한다. K_ρ 실측 효과의 상당 부분이 사실은 프리장 차단일 수 있다. 더 정확한 처방은 LTV `tradable_boards` 에서 `pre_nxt` 제거(**DB 한 줄**)이지만 그것은 **사용자 의도**(연속 상한가 야간 매수, 루트 CLAUDE.md 명문)라 **사용자 결정 사항**.
- **F-5. LTV 15:20 강제청산 누수** — `_limit_up_reached` 인메모리·`prepare()` 미clear 로 08-31 161890 이 청산을 빠져나가 09-01 −6.5% 갭에 −11,200. 랏 상한은 그 노출의 **크기만** 줄인다. 별도 사이클.
- **F-6. 선택 효과 검정(6개월).** 배수가 높을수록 금액뿐 아니라 **수익률(pnl/notional)도** 나빠진다(뷰 C: ≤1.0 +0.31% · 2.0~2.5 −2.72%). 순수 크기효과라면 수익률은 같아야 한다 → **고가주(대형주) 자체가 이 전략들에 나쁜 매매**일 가능성. 그렇다면 정확한 처방은 랏 상한이 아니라 유니버스/신호 필터다. 마커의 `price/cap/ratio` 필드가 그 표본을 만든다.
- **F-7. 근본 원인 = 자금 규모 대비 전략 수.** ρ×예산 < 1주 가격이 흔한 이유는 순자산 260만원을 7전략에 나눠 전략당 13~78만원이기 때문(LTV 설계 랏 52,040원 = 유니버스 p75 바로 위). **K_ρ 는 증상 상한이고 원인은 배분이다.** 순자산 1,000만원이면 대부분 자연 소멸(컷오프가 순자산 비례 상승).
- **F-8. cycle242 후속 D 종결 표시** — cycle242 §8-D("고정%손절 5전략의 폴백 명목(ρ 축) 상한 — 별도 사용자 결정")가 이 사이클로 종결.

**후속 (라운드 1 신규 등재 — 확증 결함 중 이번 사이클 범위 밖)**

- **F-9. 터틀 1주 폴백 랏의 ρ 잔여 노출(MEDIUM).** 백스톱 판정은 "K축이 랏을 **구속했는가**"가 아니라 "ATR 을 **읽을 수 있는가**"로 정의돼 있다. `_apply_lot_units_cap` 의 `compute_unit_qty(budget, atr, risk_pct, fraction=K)` 는 **무상한 유닛 축**이라 ATR 이 작을수록 `cap_qty` 가 커지고, 1주 폴백이 발생하는 조건(고가 × 저ATR)이 정확히 K축이 느슨한 구간과 겹친다. 실측(실전략 인스턴스 직접 호출) = kojiro B=780,611 ρ=0.166 price 500,000 atr∈[5,000, 7,800] → qty 1, 명목 500,000 = ρ상한 129,581 의 **3.86배** · donchian B=390,300 ρ=0.20 price 390,000 atr≤3,900 → **5.00배**(ATR 이 `예산×risk_pct×K` 를 넘는 순간에만 0). **이번 사이클이 없애려던 4.23배 랏보다 크고, donchian·kojiro 는 라이브 전략이다.** ⚠️ **라운드 2 증거 귀속 정정(§12-1) — 차단 요인은 외부 제약이 아니라 이 사이클 자신의 결정 ⑦이다.** 종전 문안은 "닫으려면 상호배타를 깨야 하고 그 방향은 cycle242 F-6c/6d 를 되살린다(M6 실증 8 FAIL)" 라고 적었으나 라운드 2 실측은 반대다 — (A) `min` 합성(= K축 심사 랏에도 ρ 적용)은 `test_cycle242_fallback_notional_cap.py` **97 passed / 0 failed**, 표적 스위트 고유 실패는 **F-7b 1건**(결정 ⑦을 명시적으로 재확인하는 단언)뿐이고, `if governs:` 블록을 통째로 지우는 순진한 구현이면 판정 실패 fail-open 까지 함께 사라져 F-10d 가 동반된다(= 올바른 합성은 `gov_reason == "probe_error"` 조기 반환을 **남긴다**). cycle242 F-6c/6d **4건**을 깨는 것은 (B) **자문 원안**(백스톱을 없애고 ρ를 `sizing_mode != "turtle"` 전용으로 게이팅)이며 그 실측이 "8 FAIL" 의 정체다(§12-1 표). 즉 이 후속은 cycle242 무손상 제약에 막혀 있는 것이 아니라 **team-leader/사용자의 결정 ⑦ 재검토만으로 열린다.** 후보 = (i) K축 통과 후에도 ρ축을 `min` 합성(계약 §3-3·§3-7b 를 먼저 고치고 F-7b 를 개정 — 비용 실측 1건, probe_error 조기 반환 유지 필수) (ii) `compute_unit_qty` 에 notional 상한 주입 (iii) 터틀 전략의 1주 폴백 자체를 금지. 현행 탐지 채널 = `[oversized_fallback] ratio` + `[ratio_cap_config] cap=backstop`(R7 이 정상으로 분류).
- **F-10. 차단 랏이 BFB/VCP 의 당일 표본을 지운다(HIGH — §7.1 로 지혈, 근본은 미해결).** 4전략(BFB·VCP·donchian·kojiro)이 `check_buy_signal` 경로 안에서 **주문 이전에** `_bought_today.add(ticker)` 를 수행하므로, 관문이 0 을 돌려주면 주문은 안 나가면서 그 종목은 그날 남은 시간 전부 `Signal.NONE` 이다. `_vol_latch` 도 같은 자리에서 pop 되어 재무장 상태가 사라지고, `_position_setup` 은 `on_position_closed` 에서만 pop 되므로 유령 stamp 가 남는다. 정확한 시정은 "수량이 확정된 뒤에 표본 상태를 기록" = `check_buy_signal`/`order_engine` 계약 변경이라 **8영역 별도 승인 사이클**. 같은 결함은 cycle242 K축 차단(donchian·kojiro)에도 이미 존재한다.
- **F-11. cycle233 계좌 SOFT Σ상한 게이트의 LTV 위치 결함(MEDIUM).** cycle233 위치 이원화 규약은 "edge-crossing 2전략(momentum·VB)은 baseline 동결 방지로 **발사 직전**"인데, **LTV 는 `check_buy_signal` 최상단**(`long_tail_volatility.py:635`)이고 baseline 갱신은 `:684`, 교차 판정은 `:690` 으로 **VB 와 완전히 동일한 edge-crossing 구조**다. block 구간 동안 `_prev_price` 가 동결되고 해제 후 첫 틱에서 실제 교차가 block 중에 일어났더라도 신호가 발화한다 = cycle233 이 명시적으로 막았던 C233-F1 재현. 현재는 `system_config.account_risk_block_pct` 키 자체가 없어 다크런치라 잠복 — **그 게이트를 켜기 전에 반드시 처리**. (ρ캡과는 **중복 아님** — Σ 오픈리스크 축 vs 랏 명목 축, ρ캡은 Σ 를 보지 않는다.)
- **F-12. 20:10 일일 리포트에 ρ캡 집계 편입(MEDIUM).** `log_analysis_engine._aggregate_log_patterns` 가 `{WARNING, ERROR, CRITICAL}` 만 패턴 집계하므로 INFO 인 `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 리포트 payload 에 실리지 않는 반면, 오귀인의 원인인 "매수 수량 0 → 900s cooldown" WARNING 은 `top_patterns` 에 오른다 — **리포트만 읽는 경로에서 오귀인이 고착된다.** 시정 = `_aggregate_next_day_clear`(`log_analysis_engine.py:339`) 동형의 `_aggregate_ratio_cap(logs)` 를 추가해 `metrics.ratio_cap = {blocked, skipped, config, clamped}` 를 싣는다(관측 전용, 8영역 무관). 그 전까지 판독은 `system_logs` 직접 조회가 유일 채널(§7 표).
- **F-13. 차단 마커의 랏 수 관측 공백(LOW).** `[ratio_notional_blocked]` 가 1회/(전략,ticker)/일이라 같은 종목이 하루에 몇 번 차단됐는지 알 수 없다(§7 order_engine 행의 1:N 판독이 그 대체재). 필요해지면 일별 카운터를 마커에 병기.
- **F-14. `_quote_5xx_dedupe` 테스트 격리(LOW·선재, Docs 단계 실측 §13.1-2).** 모듈 전역 dedupe dict 를 리셋하는 픽스처가 없어 앞선 부팅 통합 테스트의 실제 KIS 500 잔재가 `test_cycle76_request_5xx_dedupe::test_g_md4` 를 넘어뜨린다 — 로컬 `.token_cache` 보유 시에만 발화하고 CI 는 캐시가 없어 초록이라 잠복. 클린 HEAD 사본에서 동일 재현 = cycle245 무관.

---

## 9. 문서 동기화 (Docs 단계)

- 루트 `CLAUDE.md`:
  - 하네스 표 상단 1행 추가 + 최고령 1행 제거 → 15행 유지. `docs/HARNESS_CHANGELOG.md` L7 에 cycle245 상세 1행 append(■ 발단(09-04 000500 4.23배 −11,000) / 확증 원인 / **전제 정정 4**(특히 ①자문 원안이 cycle242 4건을 깬다는 시뮬레이션 실증) / 결정 13 / 구현 / Red·Green / 적대 검증 / D+1 / 후속 / 수치).
  - ⚠️ **롤백 문안 승계 금지(라운드 2 확증 #2)** — 아래 문안에 롤백 수단을 적을 때 cycle242 줄의
    *"DB UPDATE 또는 `PUT …`(코드 재배포 불필요)"* 를 그대로 복제하지 마라. 두 수단은 **반영 시점이
    다르다**: PUT = 즉시 / SQL = **다음 백엔드 재시작에서만**(`_config_loaded` 프로세스당 1회, 07:55
    `_boot` 재호출은 no-op) — 그리고 cycle232 D6 가 보유 시 장중 재시작을 금지하므로 **장중 실효 수단은
    PUT 뿐**이다(§8 표). 같은 문장이 이미 루트 `CLAUDE.md` 의 cycle242 `max_lot_units` 롤백 줄에 있으므로
    **그 줄도 같은 Docs 단계에서 함께 정정**한다(`max_lot_units` 도 동일 병합 경로다).
  - "자금 관리 › 전략별 투자한도" 항목 끝에: *"**랏 명목 ρ축 상한 `max_lot_ratio_mult`(K_ρ=2.5, cycle245)** — K축(`max_lot_units`)이 심사하지 못하는 **모든 랏**(비터틀 5전략 전부 + 터틀이지만 ATR 배관이 끊긴 랏)의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고 1주도 못 사면 매수하지 않는다(1주 폴백 랏 크기가 그 종목 주가로 결정되던 결함 시정 — 09-04 실측 4.23배 랏이 그날 최대 손실 −11,000원을 냈다. 매수를 줄이는 방향). 두 캡은 **상호배타**(min 합성 없음). K_ρ 는 리스크 정체성 상수 — PARAM_RANGES/INT_PARAMS 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프(하한 1.0 = 정상 비중 랏 무접촉의 전제, 상한 20.0 = 롤백 다이얼 — **`PUT /api/strategies/{id}/params` 는 즉시 반영, `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만 반영**되므로 보유 중 장중 롤백은 PUT 이 유일 경로다). **키 부재 = OFF**(fail-closed 는 P0-1 유령 키 재현 경로) — 키는 7 전략 `DEFAULT_PARAMS` 전수에 명시하고 AST 가 glob 으로 강제."*
  - 핵심 안전 규칙 "매수 수량은 전략 잔여 자금 기준" 항목 끝에: *"cycle245 — 관문은 `[oversized_fallback]` 관측 **뒤**·return 앞에서 ρ축 명목 상한을 적용한다(관측 앞에 두면 차단 사건의 ρ 관측이 사라진다). 관문 안 `await`/DB 금지는 신규 헬퍼 6 에도 적용(AST G-245-2)."*
- `src/engine/CLAUDE.md` `strategy_base.py` 절 `_apply_budget_limit` 문단: 순서 계약에 ρ캡 삽입 · 마커 **8종** 기재(`[budget_clamp]` · `[oversized_fallback]`(**의미 전환** 명기) · cycle242 4종 · cycle245 4종) · fail-open 경계표(§2.7) · 두 캡 상호배타 계약 · `_lot_units_cap_governs` 계약 · K_ρ 클램프 · order_engine 900s 오귀인.
  - ⚠️ **라운드 1 필수 정정 — 기존 cycle242 문장을 그대로 승계하지 마라.** 같은 파일의 *"…`_bought_today` 가 종목당 1회/일이라 이 짝은 **1:1** 로 성립한다"* 는 cycle242 의 표적(donchian·kojiro)에서만 참이다. `_bought_today` 는 `vcp_breakout`·`kojiro`·`donchian_swing`·`bull_flag_breakout` **4파일에만** 있고(grep 실측), cycle245 의 표적 3전략(momentum·VB·LTV)에는 `bought|_traded_today|_signaled|_entered_today` 토큰이 **0건**이다. 그 3전략은 900s 만료 또는 `_sync_positions_from_balance`(≈15분)의 `clear_low_funds()` 로 같은 종목을 하루 3~4번 재시도한다(EC2 실측 LTV 095610 4행·131290 3행). ⇒ cycle242 문장에 **스코프 한정**(터틀 2전략)을 붙이고, cycle245 문단에는 **1:N 판독 규칙**(§7 표)을 쓴다.
  - ρ캡 4마커는 **INFO 2 / WARNING 2** 이고 20:10 리포트는 WARNING 이상만 패턴 집계한다 — `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 리포트에 실리지 않는다(§8 F-12)는 한 줄을 함께 남긴다.
  - `[ratio_cap_config]`/`[ratio_cap_clamped]` 의 cap 키는 **값-민감**(라운드 1 시정: `cfg|cap상태|k|cutoff` · `clamp|raw`)이라 "1회/전략/일"이 아니라 "1회/(전략, 값 조합)/일"이다 — 정상 운영에선 하루 1행, K/예산이 실제로 바뀐 날에만 1행 추가.
- `src/engine/strategies/CLAUDE.md`: (1) 자금관리 규약 "매수 수량은 `_apply_budget_limit` 관문…" 항목에 ρ캡 1문장 (2) "터틀 키 7종 … 미편입" → **8종**(`max_lot_ratio_mult` 는 터틀 키가 아니라 **전 전략 키**임을 구분해 별도 줄) + 가드 위치 `tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py` G-245-1/G-245-6 (3) "1주 폴백 (모든 전략)" 항목에 *"K축이 심사하지 못한 랏은 ρ캡이 뒤따른다(1주도 못 사면 미매수)"* (4) 매트릭스 표 7행 전부에 컷오프 산식 부기.
- `_workspace/00_leader_trading_rules.md`: §2 자금 절에 ρ축 규칙 1항(위 CLAUDE.md 문안 축약 + 컷오프 표) · DEFAULT_PARAMS 블록 **7곳**에 `"max_lot_ratio_mult": 2.5` 추가 + "PARAM_RANGES 미편입" 주석.
- `_workspace/00_URGENT_WORKLIST.md`: 신규 `## ✅ 비터틀 랏 명목 ρ축 상한 — cycle245 종결 (2026-09-04, 커밋 대기)` 항목(실측 · 원인 · 사용자 결정 · 결정 13 · **전제 정정 4** · 관측 4마커 · D+1 표 · 트리거 R1~R8 · 후속 F-1~F-8) + cycle242 항목의 후속 D 행에 *"→ cycle245 로 종결"* 부기.
- `_workspace/review_0904_intraday.md` §5: *"→ cycle245 스펙(`_workspace/red/cycle245_ratio_notional_cap_spec.md`)으로 처리. K_ρ=2.5 비터틀 전수 + 터틀 백스톱."* 한 줄 부기(**이 파일은 사전 수정이 있으므로 append 만**).
- `_workspace/domain_consult/cycle245_ratio_notional_cap.md` §2.5·§9.1: 채택 시 정정 2건 부기(설계축 백스톱 전환 · 경계 130,100/130,101).
- `_workspace/00_URGENT_WORKLIST.md` 의 cycle245 항목에 **§7.1 배포 전 필수 조치**(BFB·VCP `max_lot_ratio_mult=20.0` DB 선반영)를 배포 체크리스트로 옮겨 적는다 — 이것이 누락되면 배포 당일부터 두 전략의 완화 실험 표본이 깎인다.
- `docs/HARNESS_CHANGELOG.md` append · `_workspace/test_index.yaml` 재생성 · **전체 스위트 1회** · 커밋·푸시는 **사용자 지시 대기**(배포 창 15:30 이후).

---

## 10. Green 구현 (backend-dev, 2026-09-04)

### 10.1 구현 — §2 대비 편차 2 (그 외 참조 구현 그대로)

`src/engine/strategy_base.py` **+324/−0**(순수 추가 — 기존 라인 삭제 0. §5 예상 +180 대비
초과분은 전부 docstring·주석이다. 이 파일엔 라인 상한 없음). 전략 **7파일 각 +1/−0**.

| # | 편차 | 사유 |
|---|---|---|
| D-1 | `_emit_ratio_cap_config` 시그니처에서 **`governs` 인자 제거** — `(mode, k, budget, pos_ratio, cap, cutoff)` 6인자 | 참조 구현 §2.4 는 7번째로 `governs` 를 넘기지만 §2.4 의 라벨 규칙 주석 자체가 `cap` 상태를 **`mode` 로만** 결정한다(`off`=키 부재 / `backstop`=`mode=="turtle"` / `on`=그 외) — 넘겨도 쓰이지 않는 죽은 인자가 된다. 라벨을 랏별 `governs` 로 바꾸면 안 되는 이유는 docstring 에 명시했다: 이 마커는 **하루 첫 랏 1회**만 찍히므로 랏 단위 판정을 실으면 그날 나머지를 대표하지 못한다(F-16a/16b 의 고정 서식도 `governs` 필드를 갖지 않는다). 호출부에서 `governs` 는 그대로 계산돼 뒤의 분기에 쓰인다 |
| D-2 | `_lot_units_cap_governs` 의 `except Exception` 에 `# pragma: no cover` 부기 | 참조 구현과 동일 위치. 행위(`(True,"probe_error")` fail-open)는 무변경이고 F-10d 가 그 경로를 **실제로 밟는다**(`_resolve_sizing_atr` 를 raise 시켜 판정기 내부에서 터뜨림) |

그 외 §2.1 상수 3 · §2.2 cap 속성 2 · §2.3 관문 1줄 삽입(+ docstring 단서) · §2.4 헬퍼 6 ·
§2.5 `_emit_oversized_fallback` **docstring 만** · §2.6 7파일 1키 = 참조 구현과 동일.
로그 서식 4종은 §2.4 주석의 필드·순서를 그대로 따랐다(F-1/F-10a/F-16a/F-16b 가 완성 문자열 단언).

### 10.2 §4.3 기존 테스트 개정 — 실측 **18 케이스 · 4 파일**(명세 헤더는 "3 파일", 열거는 4)

시뮬레이션 예측과 **케이스 단위까지 일치**했다. 개정은 전부 §4.3 지시대로:

| 파일 | 케이스 | 개정 |
|---|---|---|
| `strategies/test_momentum.py` | 1 | `total_investment` 100,000 → **200,000** (cap 50,000 · 컷오프 125,000 ≥ 100,000) |
| `strategies/test_volatility_breakout.py` | 1 | 100,000 → **250,000** (cap 25,000 · 컷오프 62,500 ≥ 50,000) |
| `test_budget_limit_gate.py` | 7 | `assert result == sentinel` → `assert sentinel == 42` + `assert result == 0`. **`assert_called_once_with(100_000_000)` 무변경**(이 테스트의 진짜 계약 = 위임/분기 순서) |
| `test_strategy_fallback_budget.py` | 9 | (a) `test_fallback_when_no_usage_then_returns_one` 4건 — 고정가 800k → **비중 도출가** `int(예산×ratio)+1` + `비중 수량 == 0` 사전 단언 (b) `test_fallback_uses_common_helper` 4건 — 위와 동형 (c) `test_fallback_isolated_per_strategy_state` 1건 — price 600,000 → **200,000** |

부수(§4.3-(5), assertion 무변경) = `test_cycle233_oversized_fallback.py` 모듈 docstring 재스코프
("position_ratio 모드에서 수량 0 = 오구현" → **"관측기 자신이** 수량을 바꾸면 오구현" + cycle245
재스코프 문단 = 이 파일 픽스처는 `max_lot_ratio_mult` 키가 없어 캡 OFF 경로).

### 10.3 ⚠️ 명세 밖 필수 개정 1 — `test_cycle223_ast_donchian_exit_fix.py` sha 핀 재산출

§4.3 이 예측하지 못한 FAIL 이 **1건** 나왔다: `G-223-12 test_g223_12_other_strategy_files_diff_zero`.
시뮬레이션이 캡을 **pytest 플러그인으로 주입**했기 때문에 `DEFAULT_PARAMS` 1줄 추가(§2.6)가
워킹트리에 없었고, 이 가드는 **파일 내용 sha256** 을 보므로 시뮬레이션에서 뜨지 않았다.

정규 절차(루트 CLAUDE.md "8영역 diff-zero 가드는 내용 sha256 핀, 커밋 시 자기소멸" — cycle227·228·231·233·242 선례)대로 처리:
1. `git diff HEAD -- src/engine/strategies/` 를 눈으로 확인 → **7 파일 각 +1/−0, 전부 같은 1줄**(가드 절차 1·2 이행).
2. `_CYCLE228_STRATEGY_CONTENT_SHA` 6항목 재산출 + cycle245 재핀 사유 주석 6줄 추가(기존 이력 주석 무삭제).
3. **비공허성 실증** — `momentum.py` 에 1줄 주입 → 해당 가드 **FAIL**, 원복 → **PASS**.

`donchian_swing.py` 는 이 dict 소관이 아니다(자기 가드 별도, 무변경 통과).

### 10.4 실행 결과

| 스위트 | 결과 |
|---|---|
| 신규 2파일 (`test_cycle245_ratio_notional_cap.py` + AST) | **146 passed** |
| §5 표적 목록 전체 (cycle242·cycle233·관문·전략·AST 전수 + `test_buy_block_low_funds` + `test_reset_daily_state`) | **1,751 passed, 24 xfailed, 3 xpassed** |
| `tests/unit` 전체 | **5,944 passed, 8 skipped, 325 xfailed, 13 xpassed** (0 failed) |
| `tests/integration` 전체 | **267 passed, 3 xfailed** (0 failed) |

**뮤테이션 실증 4건**(Green 자기검증 — 실트리 원복 확인 포함):

| 뮤테이션 | 결과 |
|---|---|
| M2 경계 `final <= cap_qty` → `<` | **2 FAIL** (F-2 `[130100-1]` + G-245-4 구조) |
| M5 `_lot_units_cap_governs` 결과 무시(터틀에도 ρ 적용) | **2 FAIL** (F-7a/F-7b — 정상 터틀 랏 값 변경) |
| M12 `no_ratio/no_budget/no_cap` fail-open → `return 0` | **9 FAIL** (F-10 계열 = P0-1 재현 방지 가드) |
| G-223-12 sha 핀 (momentum 1줄 주입) | **1 FAIL** |

### 10.5 8영역 · 범위 확인

- **8영역 diff 0** — `risk.py`·`order_engine.py`·`realtime/`·`auth/`·`api/order.py`·`session.py`·
  `scanner.py`·`strategy_registry.py` + `scheduler.py`·`boot_manager.py`·`turtle_sizing.py`·
  `portfolio_risk.py`·`recommendation_engine.py` 전부 `git diff HEAD --stat` **0 라인**.
- **cycle242 무손상** — `_apply_lot_units_cap`·`_read_max_lot_units`·`_resolve_sizing_atr`·
  `_emit_fallback_*` 4종 **본체 diff 0**(호출 라인·순서도 무변경). `_emit_oversized_fallback` 은
  **docstring 만**(포맷 문자열 byte 불변 — G-245-10 이 핀).
- **관문 순수성** — 신규 헬퍼 6 안에 `await`/DB/HTTP 0 (G-245-2), 관문 시그니처 무변경(F-19b),
  `_fallback_one_share`/`_calc_used_funds` 본체 diff 0.
- **git 무접촉** — commit/push/stash/checkout/restore **0회**. 미푸시 커밋(`233b663`·`9ce1d9e`·
  `3759ddd`·`dd4eeec`) 및 사전 존재하던 `_workspace/review_0904_intraday.md` 수정 **무접촉**.
- 변경 파일 = `strategy_base.py` + 전략 7 + 테스트 6(신규 2·개정 4·docstring 1·sha 핀 1) +
  `_workspace/test_index.yaml`(재생성) + 본 명세 §10.

### 10.6 무접촉으로 남긴 것 (Docs 단계 몫)

루트 `CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` ·
`_workspace/00_leader_trading_rules.md` · `_workspace/00_URGENT_WORKLIST.md` ·
`_workspace/review_0904_intraday.md` · `_workspace/domain_consult/cycle245_ratio_notional_cap.md` ·
`docs/HARNESS_CHANGELOG.md` — 전부 §9 문서 동기화 항목이라 Green 에서 손대지 않았다.

### 10.7 결론

§2 참조 구현을 편차 2(D-1 죽은 인자 제거 · D-2 pragma)로 구현해 신규 146 + 표적 1,751 +
`tests/unit` 5,944 + `tests/integration` 267 이 전부 PASS 한다. 명세가 예측하지 못한 개정은
**sha 핀 1건뿐**이고 정규 절차로 처리했다. 행위 변경은 `governs=False ∧ 명목 > cutoff` 구간에만
있고 그 방향은 **매수 축소**뿐이다.

---

## 11. 적대 검증 라운드 1 — 확증 15 / 시정 (backend-dev + tdd-engineer, 2026-09-04)

3렌즈 적대 검증이 **확증 15건**(HIGH 5 · MEDIUM 10)을 제출했다. 회귀 먼저 → 최소 시정 원칙으로
처리했고, **구현 결함은 2건뿐**(둘 다 관측 계층)이며 나머지는 **테스트 커버리지 공백 3 · 계약
문안 오류 4 · 운영 판독 규칙 오류 6** 이다. 커밋 0회.

### 11.1 처리 요약

| # | 등급 | 확증 내용 | 처분 | 반영 위치 |
|---|---|---|---|---|
| 13 | HIGH | `test_f245_8_…[3 param]` 이 **전체 스위트에서만 FAIL**(순서 의존). `baseline.calc_buy_quantity` 가 `caplog.at_level` **밖**인데 caplog 핸들러는 테스트 전 구간을 수집 → 앞선 테스트가 로거를 INFO 로 올려두면 baseline 의 `[ratio_notional_blocked]` 까지 섞여 `assert 2 == 1` | **테스트 시정** — 캡처 직전 `caplog.clear()` 1줄. cycle240 F-8 과 동일 계열 **픽스처 결함이며 구현은 무결함** | `test_cycle245_ratio_notional_cap.py` F-8 |
| 14·2·5 | HIGH·MEDIUM | 뮤테이션 **escape M13** — ρ캡 스코프를 `via_fallback` 전용으로 좁혀도 표적 53 테스트가 **0 failed**. F-5 그리드가 `req ∈ {0, sized}` 만 도는데 K_ρ≥1 이면 sized 랏은 정의상 무바인딩, F-14b 는 `_fallback_one_share` patch 라 `via_fallback=True` ⇒ **캡이 실제로 바인딩되는 non-fallback 랏이 커버리지 0 건**. §3-7 "모든 랏 스코프"·§6 M13 이 공허 | **회귀 신설** F-5b(10→2 · 3→2 · 경계 2→2) + F-5c(`path=sized capped_qty=2` 마커) | 신규 4 케이스 |
| 15 | HIGH | 뮤테이션 **escape M9b** — `cutoff = int(k*cap)` → `(k*cap)` 이면 관문이 **float 를 반환**하는데 값이 완전히 동일(400,000 조합 무작위 전수 불일치 0). `calc_buy_quantity` ~ `pending_buys.add` 사이 `int()` 강제 변환 0 + `api/order.py` 가 `str(quantity)` ⇒ KIS 바디에 `ORD_QTY="2.0"` | **회귀 신설** F-4c — 반환 **타입** 계약(`type(result) is int`). 파라미터에 **바인딩·비제로 조합 필수**(비바인딩은 공허) | 신규 4 케이스 |
| 12 | MEDIUM | 공식 롤백(`PUT …/params` → 즉시 발효)을 **확인할 관측 채널이 0**. `cfg`/`clamp` 단일 키가 그날 첫 랏에 소진돼 (b) 변경 후 새 `k` 무기록 (c) 같은 날 두 번째 범위밖 값 **무음 클램프** (d) 예산 재분배 시 `cutoff_price` stale | **구현 시정** — cap 키 값-민감화(`cfg\|cap상태\|k\|cutoff` · `clamp\|raw`, 96자 절단). 정상 운영은 여전히 1행/일 | `strategy_base.py` 2곳 + 회귀 F-16d/16e/16f |
| 11 | MEDIUM | R7 자기검증이 **리터럴 2.50 고정** — 같은 문서가 처방한 롤백(R1 K=3.0 / R2 K=20.0)을 실행하는 순간 **상시 오탐 생성기**. fail-open 5사유 제외 절도 없음 | **문안 재작성** — "그날 그 전략의 `[ratio_cap_config] k=`" 기준 + `[ratio_cap_skipped]` 짝 제외 + `cap=backstop` 제외 | §7 표 · §8 R7 · `_emit_oversized_fallback` docstring |
| 6·1 | MEDIUM | §3-7 "모든 랏이 `notional ≤ K_ρ×cap`" 이 §3-3(상호배타)과 **모순**이고 신규 테스트 F-7b(3.84배 랏 불변 단언) 자신이 반례. 잔여 노출 실측 kojiro **3.86배** · donchian **5.00배**(K축은 무상한 유닛 축이라 저ATR 구간에서 느슨) | **계약 문안 분리** — (7a) 스코프(모든 랏, F-5b/5c 봉인) / (7b) 항등식(**ρ축이 심사한 랏 한정**). 잔여 노출은 **§8 F-9 후속 등재**. ⚠️ 이 행이 적은 "상호배타를 푸는 방향 = M6 실증 8 FAIL(cycle242 F-6c/6d)" 은 **라운드 2 가 실측으로 뒤집었다** — 8 FAIL 은 (B) 자문 원안(백스톱 제거)의 값이고 `min` 합성은 cycle242 를 **한 건도** 깨지 않는다(§12-1) | §3-7 · §8 F-9 |
| 3·4 | HIGH | BFB/VCP 가 `check_buy_signal` 안에서 **주문 이전에** `_bought_today.add` + `_vol_latch.pop` 을 수행 ⇒ ρ캡 0 은 랏 1건이 아니라 **당일 표본을 영구 소실**시킨다. 실측 차단률 **VCP 10.0%(91/913) · BFB 3.5%(32/913)**, 1주 폴백 경로 기준 VCP **36%**. 두 전략은 cycle228 이 8사이클 걸려 연 N=10 실험 중(≈0.5건/일) | **배포 전 필수 조치 신설(§7.1)** — BFB·VCP 만 `max_lot_ratio_mult=20.0` **DB 선반영**(코드로는 불가 — 결정 ②·AST G-245-6 이 전략별 기본값 차등을 금지). 사후 R2 는 **감지 채널로 재정의**. 근본(표본 기록 시점)은 **§8 F-10** | §7.1 · §7 표 · §8 R2·F-10 |
| 9 | HIGH | §7 오귀인 판독 규칙(1:1)이 표적 3전략에서 거짓 — `_bought_today` 는 VCP·kojiro·donchian·BFB **4파일에만** 있고 LTV·VB·momentum 엔 없다. 900s 만료 + `_sync_positions_from_balance`(≈15분) `clear_low_funds()` 로 **하루 3~4회 재시도**(실측 LTV 095610 4행·131290 3행). 2행째부터 "캡 마커 없이 단독" = **진짜 잔여 부족으로 오분류** | **판독 규칙 1:N 재작성** + `src/engine/CLAUDE.md` 의 cycle242 1:1 문장에 **스코프 한정 부기**(승계 차단) + R6 임계를 건수 → **캡 마커 없는 distinct (전략,ticker) 수**로 재정의 | §7 표 · §8 R6 · `src/engine/CLAUDE.md` |
| 10 | MEDIUM | INFO 마커 2종이 20:10 리포트에 **구조적으로 도달 불가**(`_aggregate_log_patterns` 는 WARNING↑만 패턴 집계) — 반면 오귀인 원인인 "매수 수량 0" WARNING 은 `top_patterns` 에 오른다. R6 이 리포트로 측정하도록 정의돼 자기모순 | **§7 표에 전용 행 신설**(system_logs 직접 조회가 유일 채널) + 집계 편입은 **§8 F-12** 후속 | §7 표 · §8 F-12 |
| 7 | MEDIUM | "가격이 컷오프 아래로 내려오면 자연 재진입"이 3전략에서 거짓 — 전부 edge-crossing 이라 차단된 교차가 **소비**되고(`_prev_price` 갱신) 900s low-funds 락이 `check_buy_signal` **앞**이라 baseline 도 동결 | **R3 기대치 보정**(스펙 상정보다 쉽게 걸린다) · R6 재정의(위) | §7 표 · §8 R3·R6 |
| 8 | MEDIUM | 계좌 SOFT Σ상한과 ρ캡은 **중복 아님**(Σ 오픈리스크 축 vs 랏 명목 축). 다만 그 게이트 활성 시 **LTV 에서 C233-F1 재현** — cycle233 은 LTV 를 폴/래치형으로 분류했으나 코드는 VB 와 동일한 edge-crossing 이고 게이트가 `check_buy_signal` **최상단**(`:635`, baseline 갱신 `:684` 앞) | **§8 F-11 후속 등재**(그 게이트를 켜기 전 선결). cycle245 범위 밖 | §8 F-11 |

### 11.2 코드 변경 (라운드 1)

`src/engine/strategy_base.py` **only** — 행위(수량) 변경 **0**, 관측 cap 키와 docstring 뿐.

1. `_emit_ratio_cap_config` — `key = "cfg"` → `key = f"cfg|{cap_state}|{k_desc}|{cutoff}"`
   (`cap_state`/`k_desc` 계산을 `should_emit` **앞**으로 이동. peek→로그→mark 순서 불변 = G-245-5 유지).
2. `_emit_ratio_cap_clamped` — `key = "clamp"` → `key = f"clamp|{raw!r}"[:96]`(이상 입력이 cap 사전을 부풀리지 못하게 절단).
3. docstring 3곳 — 두 emit 의 cap 규약("1회/전략/일" → "1회/(전략, 값 조합)/일") + `_emit_oversized_fallback` 의 R7 재정의.

**행위 무변경 근거** — 두 함수는 `logger` 호출만 하고 반환값이 없으며 `_apply_ratio_notional_cap`
의 분기·산술은 diff 0. cycle242 헬퍼·마커 diff 0. 8영역 diff 0.

### 11.3 신규 회귀 11 케이스

| ID | 봉인 대상 |
|---|---|
| F-4c (4) | 관문 반환 **타입 계약** `type(result) is int` — M9b(cutoff 정수 절삭 제거) 검출. 바인딩·비제로 조합 필수 |
| F-5b (3) | **스코프 계약 §3-7a** — sized 랏(10→2 · 3→2 · 경계 2→2)도 캡을 받는다. M13 검출 |
| F-5c (1) | 축소 경로 마커 서식 `path=sized req_qty=10 capped_qty=2 cutoff=250000` |
| F-16d (1) | K 변경(롤백 다이얼 PUT) 시 `[ratio_cap_config]` **재발화** — `k=2.50 cutoff=130100` → `k=20.00 cutoff=1040800` |
| F-16e (1) | 예산 재분배(`weight` PUT) 시 `cutoff_price` 갱신 재발화 |
| F-16f (1) | `raw` 별 클램프 재발화(`0.5` → `25.0`) ∧ 같은 값 반복은 여전히 1행 |

### 11.4 뮤테이션 실증 (사본 `/tmp` 샌드박스, 실트리 무접촉)

| 뮤테이션 | 라운드 0 | 라운드 1 |
|---|---|---|
| M13 `… or not via_fallback` (스코프 축소) | **ESCAPED** (0 failed) | **5 FAIL** (F-4c ×2 · F-5b ×2 · F-5c) |
| M9b `cutoff = (k*cap)` (정수 절삭 제거) | **ESCAPED** (0 failed) | **3 FAIL** (F-4c ×3) |
| cap 키 `cfg` 단일화 (라운드 1 시정 되돌리기) | — | **2 FAIL** (F-16d · F-16e) |
| cap 키 `clamp` 단일화 | — | **1 FAIL** (F-16f) |

### 11.5 실행 결과 (라운드 1 종료 시점)

| 스위트 | 결과 |
|---|---|
| `test_cycle245_ratio_notional_cap.py` (`--log-level=INFO` 포함) | **99 passed** (88 → +11) |
| §5 표적 목록 전체 | **1,762 passed, 24 xfailed, 3 xpassed** (0 failed) |
| `tests/unit` 전체 | **5,960 passed, 8 skipped, 325 xfailed, 13 xpassed** (0 failed — #13 순서 의존 해소 확증) |
| `tests/integration` 전체 | **267 passed, 3 xfailed** (0 failed) |

### 11.6 라운드 1 이후 남은 위험 (전부 §8 후속 등재)

- **F-9** 터틀 1주 폴백 랏의 ρ 잔여 노출 3.86~5.00배 — 설계 결정(⑦ 상호배타) 재검토가 선행이라 코드로 닫지 않았다. 탐지는 `[oversized_fallback]` + `cap=backstop` 대조. **라운드 2 정정** — 이 보류의 대가는 cycle242 파손이 **아니다**(min 합성 실측 = cycle242 97 passed / 0 failed, 고유 실패 F-7b 1건). 재검토 주체는 team-leader/사용자다(§12-1).
- **F-10** 차단이 BFB/VCP 당일 표본을 지우는 근본(기록 시점) — §7.1 DB 선반영으로 **지혈**했을 뿐이다. 같은 결함이 cycle242 K축 차단에도 이미 있다.
- **F-11** 계좌 SOFT Σ상한 활성 전 LTV 게이트 위치 선결.
- **F-12** 20:10 리포트 ρ캡 집계 부재(오귀인 고착 경로).
- **TLS 부재·단일 공유 키**(cycle243 잔여)는 이 사이클과 무관.

---

## 12. 적대 검증 라운드 2 — 확증 3(MEDIUM 3) / 전부 문서 시정 (backend-dev + tdd-engineer, 2026-09-04)

라운드 2 확증 3건은 **전부 문서 결함**(증거 귀속 1 · 운영 절차 2)이고 구현 결함은 **0건**이다 —
`src/**` 변경 **0줄**. 다만 셋 다 "가장 급할 때 읽는 지시"라 그대로 두면 운영 손실로 바뀌므로,
문안 재작성과 함께 **근거가 되는 코드 사실을 회귀로 못박았다**(F-21 4케이스). 커밋 0회.

| # | 등급 | 확증 | 처분 | 반영 위치 |
|---|---|---|---|---|
| 1 | MEDIUM | §8 F-9(이번 사이클 최대 잔여 위험)의 **차단 근거가 사실과 반대**. "상호배타를 깨면 cycle242 F-6c/6d 4건이 되살아난다(M6 실증 8 FAIL)" 로 적혀 있었으나, 8 FAIL 은 **반대 방향**(자문 원안 = 백스톱 제거)의 값이고 `min` 합성은 cycle242 를 **한 건도** 깨지 않는다 | **문안 재작성**(코드 0) — 증거를 (A)/(A′)/(B) 로 분리 귀속 | §3-7b · §6 M5 · §8 F-9 · §11.1(6·1) · §11.6 · §12.1 |
| 2 | MEDIUM | **롤백 두 수단의 전파 의미가 다른데 동등하게 기술**. `_load_strategy_config` 이 `_config_loaded` 프로세스당 1회 가드(리셋 0)라 SQL UPDATE 는 **재시작에서만** 반영된다 — 07:55 `_boot` 재호출은 DB 를 읽지도 않는다. cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **R1/R2 발동 시점에 SQL 롤백은 사용 불가** | **문안 분리 + 회귀** — §8 에 반영 시점 표 신설, §7.1/§9 에 승계 차단 지시 | §7.1 · §8 · §9 · 회귀 F-21a/F-21a2 |
| 3 | MEDIUM | §7.1(HIGH #3/#4 의 유일한 지혈책)이 병기한 대안 `PUT …/params` 가 **배포 전에는 무음 실패**. 라우트가 미지 키를 조용히 버리고 `success=true` 를 돌려주며, 이어지는 `save_params` 가 params JSONB 를 통째로 덮어 **먼저 넣은 SQL 값까지 지운다** | **문안 한정**(배포 후 전용) + 배포 전 확인 채널을 SQL 조회로 명시 + 회귀 | §7.1 · §8 표 · 회귀 F-21b/F-21b2 |

### 12.1 확증 #1 — F-9 차단 근거의 증거 귀속 (실측)

실트리를 건드리지 않고 `src`·`tests`·`tools`·`fixtures`·`pyproject.toml` 사본
(`…/scratchpad/r2repo`)에 두 방향을 각각 주입해 측정했다. 주입·복원마다 `sha256` 로 원본
동일성 확인(`7d40c880…`). 사본 특유의 기준 실패 44건(리포 루트 자산 부재 — `frontend/`·
`.github/`·`.gitignore` 를 읽는 배포 가드)은 baseline 차분으로 제거했다.

| 주입 | 내용 | `test_cycle242_fallback_notional_cap.py` | `tests/unit/engine` + `tests/unit/ast` 고유 실패 |
|---|---|---|---|
| **(A)** min 합성(순진) | `_apply_ratio_notional_cap` 의 `if governs:` 블록에서 `return final` 삭제 | **97 passed · 0 failed** | **2** — `test_f245_7b_turtle_over_rho_cutoff_is_not_cut` · `test_f245_10d_governs_probe_error_is_fail_open` |
| **(A′)** min 합성(정합) | `if governs and gov_reason == "probe_error": … return final` 로 좁혀 **판정 실패만** fail-open 유지, `k_axis` 는 ρ축으로 낙하 | **97 passed · 0 failed** | **1** — `test_f245_7b_…` |
| **(B)** 자문 원안 | `governs, gov_reason = self._lot_units_cap_governs(ticker)` → `governs = (params.get("sizing_mode") == "turtle")` (**터틀 백스톱 제거**) | **4 failed · 93 passed** — `test_f242_6c_…[volatility_breakout]` · `[long_tail_volatility]` · `test_f242_6d_…[donchian]` · `[vcp]` | **8** — 위 4 + `test_f245_8_…[no_atr]` · `[no_risk_pct]` · `test_f245_10d_…` · `test_g245_4_rho_cap_body_structure` |

판독:

1. **8 FAIL 은 (B) 의 값이다.** 라운드 1 이 §6 M6 으로 실증한 그 수치가 §3-7b·§8 F-9·§11.1 에서는
   "상호배타를 깨는 방향(= (A))의 비용" 으로 옮겨 적혀 있었다. 두 증거가 뒤바뀐 것이다.
2. **왜 (B) 만 cycle242 를 깨는가** — F-6c/6d 는 "turtle 파라미터를 주입해도 **비터틀 baseline 과
   수량이 같다**" 는 **동치 단언**이다. 백스톱을 없애면 turtle 쪽만 ρ를 면제받아 두 값이 갈라진다.
   (A)/(A′) 는 양쪽에 똑같이 ρ를 적용하므로 동치가 유지된다 — 즉 cycle242 의 4건을 지키는 것은
   **상호배타가 아니라 백스톱**이다.
3. **F-9 의 실제 비용은 F-7b 1건**(결정 ⑦을 명시적으로 재확인하는 단언)이고, 그것은 외부 제약이
   아니라 **이 사이클 자신의 설계 결정**이다 ⇒ 후속은 cycle242 무손상 제약에 막혀 있지 않고
   **team-leader/사용자의 결정 ⑦ 재검토만으로 열린다**. 잔여 노출은 kojiro **3.86배** · donchian
   **5.00배**로 이번 사이클이 없앤 4.23배보다 크고, 둘 다 **라이브 전략**이다.
4. **부수 확인** — 순진한 (A) 는 `probe_error` fail-open 조기 반환까지 함께 지워 F-10d 를 깬다.
   후속이 `min` 합성을 택하면 **그 조기 반환은 남겨야 한다**((A′) 가 그 형태, §8 F-9 후보 (i) 에 명시).

### 12.2 확증 #2 — 롤백 반영 시점 (SQL = 재시작 / PUT = 즉시)

```python
# src/engine/scheduler.py:405-408
async def _load_strategy_config(self) -> None:
    if self._config_loaded:
        return
```
`_config_loaded` = `:367` False 초기화 · `:414`/`:458` True 대입 · **리셋 지점 0**(`grep -rn
"_config_loaded" src/` 전수 = 이 3곳 + `src/engine/CLAUDE.md` 1행). 호출자는 `src/main.py:259`
(서버 기동)과 `src/engine/boot_manager.py:58`(07:55 `_boot`) **둘뿐**이므로 정상 로드 이후의
07:55 호출은 **no-op**(DB 조회 자체가 없다). 반면 `src/routes/strategies.py:175-182` 의 PUT 은
`strategy.config.params[key] = value` 로 in-memory 를 즉시 덮고 `save_params` 로 영속화한다.

운영 귀결 = R1(LTV 주 3건 초과)·R2(BFB/VCP 표본 훼손)는 **장중** 트리거인데, SQL 경로가 요구하는
재시작을 루트 `CLAUDE.md` 의 cycle232 D6(보유 포지션 시 09:00~15:30 재시작 금지)가 막는다 —
**가장 급할 때 SQL 롤백은 쓸 수 없고 PUT 만이 실효 수단이다.** 같은 오류 문안이 루트 `CLAUDE.md`
의 cycle242 `max_lot_units` 롤백 줄에도 있어 §9 에 **동반 정정 지시**를 넣었다.

### 12.3 확증 #3 — 배포 전 PUT 은 무음 실패 + SQL 값 소거

```python
# src/routes/strategies.py:175-186
for key, value in req.params.items():
    if key in strategy.config.params:      # ← 미지 키는 조용히 탈락
        strategy.config.params[key] = value
await save_params(strategy_id, strategy.config.params)   # 걸러진 dict 로 DB 덮어쓰기
return ApiResponse(success=True, ...)
```
`max_lot_ratio_mult` 는 이 사이클이 `DEFAULT_PARAMS` 에 **신설**하는 키라 배포 전 구코드의
in-memory params 에는 없다 ⇒ 값이 버려지고 `success=true` 가 돌아온다. 더 나쁜 것은
`save_params` → `save` 의 `params = EXCLUDED.params`(`src/db/strategy_config.py:35-57`)가 params
JSONB 를 **통째로** 덮는다는 점이다 — **SQL 로 먼저 넣어둔 20.0 까지 사라진다**(다른 파라미터를
고치는 PUT 이라도 동일). 확인 채널로 제시했던 `[ratio_cap_config] … k=20.00` 도 구코드엔 마커
자체가 없어 성립하지 않는다. ⇒ §7.1 을 **배포 전 = SQL 단일 경로 + SQL 조회로 확인**,
**배포 후 = PUT 정본**으로 갈랐다. 배포 후 SQL 병합 경로(`jsonb_set(…, true)` → 재시작 →
`if key in params` 병합)는 정상 동작하므로 §7.1 의 1차 지시(SQL) 자체는 옳았다.

### 12.4 신규 회귀 4 (F-21) + 뮤테이션 실증

문서만 고치면 같은 오류가 다시 승계되므로, 세 문안의 **근거가 되는 코드 사실**을 회귀로 고정했다
(`tests/unit/engine/test_cycle245_ratio_notional_cap.py` 말미 F-21 그룹).

| ID | 봉인 대상 | 뮤테이션 실증 |
|---|---|---|
| F-21a | SQL 롤백은 재시작에서만 — 2회차 `_load_strategy_config` 이 `load_all` 을 **await 0회**, in-memory K 불변 | `if self._config_loaded: return` 삭제 → **FAIL** |
| F-21a2 | `_config_loaded = False` 대입 위치 = `scheduler.py` 1곳 · `_load_strategy_config` 호출자 = `src/main.py`·`src/engine/boot_manager.py` 뿐(재로드 경로가 생기면 문서 갱신 강제) | (구조 가드) |
| F-21b | 배포 전 PUT = 키 탈락 + `success=true` + `save_params` 인자에 키 부재(= SQL 값 소거 경로) | 라우트 `if key in …` 필터 제거 → **FAIL** |
| F-21b2 | 배포 후 PUT = in-memory 즉시 반영 + 다음 랏의 `_read_max_lot_ratio_mult() == 20.0` | (정방향 계약) |

⚠️ F-21a/F-21a2/F-21b 는 **현행 행위를 고정**하는 가드다 — 장래에 재로드 경로나 키 화이트리스트가
생기면 이 가드가 붉어지고, 그때 §7.1·§8·§9 문안을 함께 고치라는 뜻이다(각 docstring 에 명시).

### 12.5 실행 결과 (라운드 2)

| 스위트 | 결과 |
|---|---|
| `test_cycle245_ratio_notional_cap.py` | **103 passed** (99 → +4) |
| `test_cycle245_*` + `test_cycle242_fallback_notional_cap.py` + AST | **258 passed** |
| `tests/unit/engine` + `tests/unit/ast` + `tests/unit/routes` | **4,568 passed, 3 skipped, 172 xfailed, 5 xpassed** (0 failed) |
| `tests/unit` 전체 | **6,014 passed, 8 skipped, 325 xfailed, 13 xpassed, 1 failed** — 유일 실패 `test_cycle145_deploy_migration.py::test_g_145_migration_4_docker_compose_preserved` 는 **cycle245 무관**(워킹트리의 cycle248 배포 파이프라인 작업이 `.github/workflows/deploy.yml` 의 인라인 `docker compose` 를 `tools/deploy/compose_up_changed.sh` 로 대체한 결과 — 이 사이클은 `.github/**` 무접촉). 라운드 2 착수 전과 동일 |

`src/**` diff **0줄**(8영역 포함) · 변경 파일 = 이 명세 + `tests/unit/engine/test_cycle245_ratio_notional_cap.py` 2개뿐.

### 12.6 라운드 2 이후 남은 위험

- **F-9(재분류)** — 잔여 노출 kojiro 3.86배 · donchian 5.00배는 그대로 남는다. 다만 차단 요인이
  "cycle242 무손상 제약"이 아니라 **결정 ⑦(상호배타)** 임이 확정됐으므로, 후속 착수 판단은
  team-leader/사용자 몫이다. 착수 시 최소 비용 = F-7b 개정 1건 + §3-3/§3-7b 계약 문안 선행 수정,
  구현은 (A′) 형태(`probe_error` 조기 반환 유지).
- **F-10** BFB/VCP 표본 기록 시점(§7.1 로 지혈만) · **F-11** 계좌 SOFT Σ상한 활성 전 LTV 게이트
  위치 · **F-12** 20:10 리포트 ρ캡 집계 부재 — 라운드 1 등재 그대로.
- **운영 절차 위험(신규 관측)** — §7.1 선반영과 배포 사이에 BFB·VCP 로 어떤 PUT 이 들어가면 SQL
  값이 지워진다. 이 창은 코드가 아니라 절차로만 막히므로 워크리스트 체크리스트(§9)에 함께 옮긴다.

---

## 13. Docs 단계 — 문서 동기화 · 전체 스위트 실측 (team-leader, 2026-09-04)

### 13.1 전체 백엔드 스위트 (실측 원문)

`find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q -p no:cacheprovider`

| 실행 | 결과 |
|---|---|
| 트리 전체 (동시 진행 세션의 cycle249 Red 포함) | `105 failed, 6482 passed, 10 skipped, 328 xfailed, 13 xpassed in 205.13s` |
| cycle249 Red 5파일 제외 | `1 failed, 6479 passed, 10 skipped, 328 xfailed, 13 xpassed in 199.45s` |
| cycle245 표적 (`test_cycle245_*` + `test_cycle242_fallback_notional_cap` + 개정 3파일) | **365 passed** (0 failed) |
| 문서 편집 후 재실행 (그사이 cycle249 **Green 이 착지**) | `1 failed, 6587 passed, 10 skipped, 329 xfailed, 12 xpassed in 215.85s` — 유일 실패는 아래 2번 환경 결함 |

**실패 귀속 — cycle245 유래 0건.**

1. **104건 = `test_cycle249_*` 5파일** — 이 세션이 아닌 **동시 진행 세션**이 워킹트리에 남긴 미구현 Red
   (`src/middleware/api_auth.py` 의 `REPORTER_WRITE_PATH_RE` 등 Green 이 아직 없다). `git status` 에 untracked
   5파일 + `tests/unit/middleware/test_cycle243_api_auth.py` 수정(사유 5종 확장)으로 남아 있다.
   cycle245 는 그 파일들을 한 줄도 건드리지 않았다.
2. **1건 = `tests/unit/api/test_cycle76_request_5xx_dedupe.py::test_g_md4_different_keys_tracked_independently`
   — 환경 결함(선재), cycle245 무관.** 단독 실행은 통과하고 `tests/integration tests/unit/api` 조합에서만
   재현된다. 원인 = 로컬에 `.token_cache/main.json` 이 있으면 `test_boot_*` 통합 테스트가 **실제 KIS 호출**을
   내고(각 4초, 통합 스위트 9s → 39s) 그 500 응답이 모듈 전역 `src.api.base._quote_5xx_dedupe` 에 남아
   (`chk-holiday`·`inquire-vi-status` 4엔트리) 뒤따르는 이 테스트의 `len(quote_state) == 0` 단언을 깬다.
   **실증** = `git archive HEAD | tar -x` 로 만든 **클린 HEAD 사본**(cycle245 변경 0)에서
   토큰 캐시 없음 → `547 passed`, 같은 캐시를 복사 → **동일 1 failed 재현**. CI 는 캐시가 없어 초록이므로 잠복.
   ⇒ 후속 **F-14**(모듈 전역 dedupe dict 리셋 픽스처 부재).
3. ⚠️ 라운드 2 시점의 유일 실패였던 `test_cycle145_deploy_migration.py::test_g_145_migration_4_docker_compose_preserved`
   는 **해소**됐다 — 그 사이 cycle248 CI 핫픽스(`6249755`)가 가드를 재스코프해 커밋·푸시됐다.


⚠️ **트리가 이 단계 중에 움직였다** — 첫 실행 시점에 미구현 Red 였던 cycle249 가 문서 편집 사이에 Green 을 워킹트리에 착지시켰다(`src/middleware/api_auth.py`·`src/config.py`·`src/db/log_reports.py`·`src/routes/log_reports.py`·`src/engine/log_analysis_engine.py`·`frontend/nginx.conf.template`·`docker-compose.prod.yml`·`.env.example`·`supabase/migrations/042_*.sql`). 그래서 최종 실행의 6,587 은 **cycle245 + cycle249 합산**이고, cycle245 단독 기준은 cycle249 파일 제외 시의 **6,479** 다. cycle245 산출물은 두 실행 사이 무변경(`src/engine/strategy_base.py` +348, 전략 7파일 각 +1).

### 13.2 수치 정정 (문서 3곳 반영)

| 항목 | 종전 문서 | Docs 단계 실측 |
|---|---|---|
| 신규 회귀 | 150 (행위 103 + AST 47) | **161** (행위 103 + AST **58** — `--collect-only` 실측) |
| 백엔드 PASS | 6,391 (= 6,241 baseline + 150 투영) | **6,479** (cycle249 제외 기준). baseline 이 6,241 보다 큰 이유 = 그 뒤 cycle246·247·248 이 커밋·푸시되며 테스트가 늘었다 |

루트 `CLAUDE.md` L69 · `docs/HARNESS_CHANGELOG.md` L7 · `_workspace/00_URGENT_WORKLIST.md` 세 곳을 실측값으로 교체하고,
귀속 문장(“104 = cycle249 Red / 1 = 환경 결함”)을 함께 적었다.

### 13.3 워킹트리 상태 정정 (이 명세 헤더의 전제가 바뀌었다)

- 헤더는 *“HEAD `3759ddd`, 미푸시 커밋 3”* 이라고 적었으나 **Docs 단계 실측은 `HEAD == origin/main == 6249755`,
  미푸시 커밋 0** 이다 — cycle243 이후의 세 커밋과 cycle246·247·248 이 이 사이클 진행 중 다른 세션에서
  커밋·푸시됐다. cycle245 는 여전히 **워킹트리 미커밋**이다.
- 워킹트리에는 cycle245 산출물과 **cycle249 진행물이 함께** 있다 ⇒ 커밋 시 **분리 필수**.
  - cycle245 = `src/engine/strategy_base.py`(+348) · 전략 7파일(각 +1) · `tests/unit/engine/test_cycle245_ratio_notional_cap.py`(신규 1,225L) ·
    `tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py`(신규 543L) · 개정 5파일 · 이 명세 · 자문 문서.
  - cycle249 = `src/middleware/api_auth.py` · `src/config.py` · `src/db/log_reports.py` · `src/routes/log_reports.py` ·
    `src/engine/log_analysis_engine.py` · `frontend/nginx.conf.template` · `docker-compose.prod.yml` · `.env.example` ·
    `supabase/migrations/042_daily_log_reports_external.sql` · `tests/unit/**/test_cycle249_*.py` · 개정 4파일.
  - ⚠️ **문서 3개는 두 사이클이 같은 파일을 편집했다** — 루트 `CLAUDE.md`(cycle245 = 하네스 표 1행·자금관리 항목·
    '매수 수량' 금기 / cycle249 = `API_REPORTER_KEY` 환경변수 줄·cycle243 인증 항목·nginx 줄), `src/engine/CLAUDE.md`,
    `src/db/CLAUDE.md`·`src/routes/CLAUDE.md`·`frontend/CLAUDE.md`(cycle249 단독). 커밋은 **hunk 단위 선택**이 필요하다.
- `_workspace/test_index.yaml` 은 `tools/test_impact/build_index.py` 로 재생성했다(backend modules 132 / tests 910).
  diff 804행 중 cycle245 204행 · **cycle249 385행** — 인덱스는 트리 상태를 그대로 반영하므로 동시 세션 파일이 함께 매핑됐다.
- 루트 `CLAUDE.md` 하네스 표는 **15행 유지**(cycle245 추가 / 최고령 cycle228 제거). ⚠️ 선재 공백 —
  cycle244·246·247·248 은 커밋됐는데 표에 행이 없다(HEAD 기준). 이 사이클 밖 문서 위생 후속.

### 13.4 이 단계에서 추가된 후속

- **F-14. `_quote_5xx_dedupe` 테스트 격리(LOW·선재).** 모듈 전역 dedupe dict 를 리셋하는 픽스처가 없어
  앞선 통합 테스트의 실제 KIS 500 잔재가 `test_cycle76_request_5xx_dedupe::test_g_md4` 를 넘어뜨린다.
  로컬 `.token_cache` 보유 시에만 발화(= 개발자 머신에서만), CI 는 초록. 시정 = `src/api/base` 의
  `_quote_5xx_dedupe`/`_request_5xx_dedupe` 를 비우는 autouse 픽스처, 또는 통합 부팅 테스트의 네트워크 차단.
