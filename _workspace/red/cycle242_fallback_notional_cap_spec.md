# cycle242 — G0-ⓑ 1주 폴백 과잉 시정: 터틀 전략 랏당 최대 유닛 상한 `max_lot_units`(K=2.0) (피라미딩 심층 검토 §0.0 · 아침 리포트 §7 #1)

작성: team-leader, 2026-09-03 아침. 사용자 결정("결정 분기 권고대로 처리" → 리포트 §7 #1 = **ⓑ 폴백 notional 상한 먼저**, ⓐ "<1주면 스킵"은
표본 확보 후 재검토). domain-consult(`_workspace/domain_consult/cycle242_fallback_notional_cap.md`) + 3렌즈 진단(path·evidence·tests_docs)
+ 코드 재실측 후 확정. **진단의 전제 정정 5건**은 §0 하단 — 그중 ①(기존 테스트 파손 범위)은 tdd-engineer 착수 전 반드시 읽을 것.

> **워킹트리 상태**: HEAD `0f29c4b`(09-03 아침 리포트 docs) 기준 트리 클린. untracked 3건 = `_workspace/domain_consult/cycle242_fallback_notional_cap.md`(본 사이클
> 입력 자문) · `bfb_vcp_entry_relax_20260903.md` · `pyramiding_design_blueprint_20260903.md`(동시 실행 중인 읽기 전용 워크플로 2개의 산출물 — **무접촉**).
> **git commit / push / stash / checkout / restore 금지.** 배포는 보유 포지션(8종목)이 있으므로 **15:30 이후**(cycle232 D6) — 이 워크플로는 커밋하지 않는다.

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py · strategy_registry.py) + **scheduler.py 무접촉**(3,999L)
> + **boot_manager.py 무접촉**(허용 목록 밖 — §0 전제 정정 ③). src 변경 = **`src/engine/strategy_base.py`(주)** + 터틀 4전략 파일의 **`DEFAULT_PARAMS` 1키 추가만**
> (`donchian_swing.py` · `kojiro.py` · `vcp_breakout.py` · `bull_flag_breakout.py` — `calc_buy_quantity`/`_turtle_buy_quantity`/청산 경로 diff 0).
> `turtle_sizing.py` 는 **읽기만**(`compute_unit_qty` 재사용, diff 0). `portfolio_risk.py` diff 0.

## 0. 결정 요약 (착수 질문 ①~⑫)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | 파라미터 이름·기본값 | **`max_lot_units` = 2.0**(float, "랏당 최대 유닛 수"). 자문 ① 채택 — 전 전략 공통, 전략별 분리 없음 | K 는 `예산 × risk_pct` 로 이미 전략별 정규화된 무차원 수. kojiro 는 K∈[1.5,3.0] 전 구간 결과 동일(18/20)이라 분리 이득 0, 구속 전략은 donchian 하나. K=2 = 터틀 원전 "확인 없이 감수하는 최초 진입 = 사다리 첫 두 칸"과 의미 정합. 이름은 스코프 ii(모든 랏)를 정확히 말한다 — `fallback_notional_k` 류는 오명 |
| ② | 척도 | **이론 유닛 × K (ATR 축)**: `cap_qty = floor(K × 예산 × risk_pct ÷ ATR)` = `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)` **그대로 재사용**(새 수식 0). ρ(예산 비율) 축 기각 | 고칠 결함이 "risk_pct 가 진입 시점에 무력" = 유닛 축. ρ ≤ position_ratio 는 정의상 폴백 전면 차단(=ⓐ 위장), ρ > position_ratio 는 근거 없는 새 상수 + 변동성 맹목(저ATR·고명목만 통과 = 갭 꼬리 역선택). ρ 축은 **관측으로 병존**(`[oversized_fallback]` 유지 + `units=` 필드 추가 = 한 줄에서 두 척도) |
| ③ | 적용 범위 | **`sizing_mode == "turtle"` 전략의 모든 랏**(스코프 ii) — 현행 대상 donchian·kojiro(운영 DB `turtle`). VCP/BFB 는 DB 키 부재 = 코드 기본 `position_ratio` = 오늘 범위 밖, 터틀로 켜는 순간 자동 편입. **고정%손절 5전략(momentum/VB/LTV + PR 모드 VCP/BFB)은 범위 밖** | 스코프 i(폴백만)는 PR 경로(터틀 0 → position_ratio 수량)를 못 건드려 donchian 최대 랏이 **3.71유닛에 고정**(124500 2주) → G0 미종결. 스코프 ii 는 `lot_units ≤ K` 를 **항등식**으로 만든다. 고정%손절 전략은 position_ratio 가 이미 리스크 균등(strategies/CLAUDE.md 함정 #1)이라 유닛 캡을 씌우면 정규화 역전. `sizing_mode` 게이팅 금기(C8)는 **청산 규약** 얘기이고 이건 **진입 사이징** — 같은 호출에서 이미 `sizing_mode` 로 분기 중이라 충돌 없음 |
| ④ | 관문 내 위치 | `_apply_budget_limit` 안, **폴백/잔여 클램프 뒤 · `_emit_oversized_fallback` 앞 · `return` 앞**(§2.3). `_fallback_one_share` 본체 무변경 | A-GATE 가 관문 안을 강제. 헬퍼 내부 배치는 스코프 ii(PR 경로) 미커버 + `_fallback_one_share` 직접 호출 테스트 3건 추가 파손 → 기각(C4). 관측 앞이어야 `[oversized_fallback]` 이 **캡 이후 최종 수량**을 재고, 캡→0 이면 관측기가 `final_qty < 1` 로 자연 침묵(차단 사실은 신규 마커가 담당) |
| ⑤ | 순수 파라미터 전달(ATR) | **관문 시그니처 무변경.** 관문이 터틀 분기와 **같은 소스** `_candidates[ticker]` 를 read-only 로 읽는 `_resolve_sizing_atr(ticker)` 헬퍼 신설 — 키 `("atr", "atr14")`(donchian·kojiro = `atr` / VCP·BFB = `atr14`, 실측 상호 배타). **두 키가 다른 값을 동시에 가지면 `ambiguous_atr` fail-open**(어느 쪽도 채택 안 함). `ticker is None` 은 터틀 분기와 동일하게 조용히 off | 허용 파일 제약("전략 파일은 DEFAULT_PARAMS 키 추가만")과 A-PURE(관문 내 DB/await 금지)를 동시에 만족하는 유일한 형태. "캡 ATR = 사이징 ATR" 동일성은 소스 동일 + 모호 시 불채택 + F-14 행위 검증으로 봉인. 명시 kwarg(`sizing_atr=`) 전달은 **후속**(전략 파일 다음 접촉 사이클, §8 B) |
| ⑥ | 결측·실패 방향 | **fail-open + LOUD** — ATR 결측/0/비수치/모호 · `risk_pct ≤ 0` · 캡 산출 예외 → **현행 수량 유지** + `[fallback_cap_skipped] reason=no_candidates\|no_atr\|ambiguous_atr\|no_risk_pct\|no_budget\|exception` **WARNING** 1회/(전략,ticker,reason)/일 | 판별 원칙 = "변경 이전 행위 쪽으로 fail". cycle228 볼륨 게이트 fail-closed 는 *원래 안 사던 상태* 유지였지만 여기 fail-closed 는 *오늘 사고 있는 것을 새로 막는* 방향. ATR 키가 전략별로 갈리므로 fail-closed 는 P0-1(유령 키 → 전략 전 기간 0건) 재현 경로. 안전망 = ATR 결측이어도 `[oversized_fallback]`(ρ 축)이 과대 랏을 계속 기록 → 관측 손실 0 |
| ⑦ | 관측 마커·cap | **`[fallback_notional_capped]`**(INFO, 캡 발동 = 축소·0 모두) 1회/(전략,ticker)/일 · **`[fallback_cap_skipped]`**(WARNING) 1회/(전략,ticker,reason)/일 · **`[fallback_cap_config]`**(INFO, `sizing_mode`·`cap=on\|off`·k·예산·`atr_max`) 1회/전략/일 — 세 마커가 **하나의 `DailyEmitCap[str]`**(복합 키 `cap\|t` / `skip\|t\|r` / `cfg`) + 날짜 키 자기 리셋, **peek→로그→mark**, 예외 전부 흡수. `[oversized_fallback]` 은 기존 서식 byte 보존 + 끝에 ` units=%.2f`(ATR 결측 `-`) 추가 | 마커 이름은 착수 컨텍스트·자문이 쓴 `[fallback_notional_capped]` 를 유지(워크리스트·D+1 grep 연속성 — 스코프 ii 라 이름이 좁지만 `path=fallback\|sized` 필드로 분리). cycle233 `_emit_oversized_fallback` 이 peek→로그→mark 정본이고 같은 파일 `_emit_budget_clamp` 은 mark 선행(cycle226 D-3 위반)이라 **복붙 금지** — §2.6 에서 1줄 재배치로 동행 시정 |
| ⑧ | 파라미터 취급 | `DEFAULT_PARAMS` 에 `"max_lot_units": 2.0` — **터틀 4전략만**(donchian·kojiro·VCP·BFB). **`PARAM_RANGES`/`INT_PARAMS` 편입 금지** + 실제 AST 가드(런타임 dict + 소스 리터럴 키 이중, cycle212 형식). **읽는 쪽 클램프** `[1.0, 20.0]`: 비수치·None·bool·비유한·<1.0 → 기본 2.0 / >20.0 → 20.0. 모듈 상수 `_MAX_LOT_UNITS_DEFAULT/MIN/MAX` 가 정본(기본값 리터럴 2.0 은 4 전략 + 상수 = 5곳, AST 가 동치 검사) | 키가 `DEFAULT_PARAMS` 에 있어야 `scheduler._load_strategy_config`(`if key in strategy.config.params`) 의 DB 병합과 `PUT /api/strategies/{id}/params`(동일 조건)가 값을 받는다 = **롤백 다이얼의 전제**. PUT 은 화이트리스트가 없어 임의 값이 들어오므로 읽는 쪽 클램프 필수 — K=0/음수는 **전면 매수 차단** 사고, K<1 은 "터틀 유닛보다 작게"라 정의상 무의미, **하한 1.0 은 T 경로(정상 터틀 수량 ≤ u*) 무접촉의 수학적 전제**. 상한 20.0 = 관측 최대 M1 15.61 < 20 → 사실상 현행 복귀 |
| ⑨ | 재시도 | **래치·차단 상태 신설 금지, 자연 재평가 허용** | 상한은 단조 **가격 상한**(`cap ≥ 1 ⇔ ATR ≤ K×예산×risk_pct`, ATR ∝ 가격) — 재진입은 항상 더 싼 가격·더 작은 ATR 에서만 = 원하는 행동(눌림목 재진입). 폭주는 `order_engine` 이 수량 0 을 "투자금 부족"으로 받아 거는 `LOW_FUNDS_COOLDOWN` 900s 가 이미 차단(8영역, 무접촉 수용 — **오귀인 문서화 의무**, §7) |
| ⑩ | 기대 효과 | 현행 예산(net 2,582,132 · kojiro 774,640 / donchian 387,320) 재정규화 K=2: donchian BUY 생존 14/26(**−46%**)·클램프 1·스킵 12, 최대 랏 8.66→**≤2.0유닛**, 단일 랏 −30% 꼬리 3.18%→**≤1.45%**(계좌) / kojiro 18/20(**−10%**), 3.44→≤2.0, 4.71%→**≤2.73%**. T 경로(정상 터틀 랏, donchian 7·kojiro 13건 전부 ≤1.68유닛) **한 건도 안 건드림**. 보유 8종목 무영향(진입 사이징만) | 렌즈2 §9. ⓐ(K=1) 대비 donchian 진입 **2배** 보존 = 사용자가 ⓑ 를 택한 값어치. 08-18 입금(+128%) 이전 표본의 as-was M1 은 오늘 기준 2배 부풀어 있어 **재정규화 표만 결정 근거**. 잘리는 거래의 손익 부호는 n=14/3 노이즈 — 결정 근거는 (a) 꼬리 (c) 측정 엣지 −0.55N(n=24, CI 0 미포함) |
| ⑪ | G0 종료 기준 재정의(C3) | 보고서 §4.3 G0 "`[oversized_fallback]` 발화 0" 은 K>1 과 **논리적 양립 불가**(ρ cap < 명목 ≤ K유닛 랏은 살아남아 계속 발화) → **G0 종료 = ① `[fallback_notional_capped]` 실발화 1건 이상 실증 ∧ ② 배포 후 신규 랏 전수 `units ≤ K`(`[oversized_fallback] units=` 필드로 직접 검증, > K **0건**) ∧ ③ 회귀 가드 존재(§4)** | ⚠️ **의미 반전** — `[oversized_fallback]` 비제로가 정상이 된다. 배포 전후 같은 grep 합산 금지 |
| ⑫ | 정본 문서 문안 | 루트 `CLAUDE.md` 3곳 + 하네스 표 1행 · `src/engine/CLAUDE.md` 관문 문단(C7: `[oversized_fallback]` 미기재 결손 동반) · `strategies/CLAUDE.md` 3곳(C5: "터틀 키 6종 미편입" → 7종 + **가드 위치** 명기) · `00_leader_trading_rules.md` DEFAULT_PARAMS 4블록 + §2 자금 절 · 워크리스트 신규 항목 + G3′ 행 부기 · 보고서 §4.3 G0 행 한 줄 부기 · 변경로그 | §9 |

**domain-consult 완료(`cycle242_fallback_notional_cap.md`)** — 매수 사이징 변경(매매 빈도 변경)이라 자문 필수 항목이었고, 결정 ①~⑩ 은 자문 §0 표를 그대로 채택했다.
**대안 채택 조건(사용자 한 단어로 뒤집을 수 있음)**: donchian −46% 가 운영상 수용 불가이거나 G3(kojiro n=30 왕복) 도달 속도를 최우선하면 **K=2.5**(−35%, 최대 랏 ≤2.5, kojiro 꼬리 3.41%). K≥3.0 은 kojiro 최악 꼬리 4.09% = 시정 전(4.71%)과 실질 무차이라 **권고하지 않음**. 이 스펙은 K=2.0 으로 쓰되 값 변경은 `_MAX_LOT_UNITS_DEFAULT` + 4 `DEFAULT_PARAMS` 리터럴 + F-10 기대값만 바꾸면 된다.

### 착수 컨텍스트·3렌즈 진단 전제 정정 (코드 재실측, 결론 불변)

1. **"기존 테스트 최소 6개 파손 · cycle233 `qty == 1` 계약 정면 폐기"(렌즈1·3, 자문 C1)** → **파손 0 기대.** 진단은 캡을 **전 전략**에 적용하는 것으로 가정했으나 결정 ③(`sizing_mode == "turtle"` 게이트) 아래서 `test_cycle233_oversized_fallback.py`(6, `_MiniStrategy` 는 `sizing_mode` 부재) · `test_budget_limit_gate.py` A-FALLBACK(7전략 기본 모드) · `test_strategy_fallback_budget.py` Case A/D/E · 전략 폴백 3건(VB/BFB/VCP 기본 모드)은 **전부 게이트 off 경로**라 무수정 통과한다. 터틀 모드 기존 테스트 7파일도 무수정 통과 — T 경로 `qty ≤ u* ≤ floor(K·u*)`(K≥1) · 변동성 floor 낙하(ATR% < 1%)는 `cap = 2rB/(P·ATR%)` 가 PR 수량 `ρB/P` 를 넘으려면 ATR% > 2r/ρ = 5%(donchian)/4%(BFB) 여야 하므로 모순 · 잔여 소진은 `final < 1` 로 캡 진입 전 종료 · ATR 0/결측·risk_pct 0/None·ticker None 은 fail-open. C1 은 "폐기"가 아니라 **docstring 재스코프**("수량 0 = 오구현" 계약은 position_ratio 모드 한정으로 좁아짐, assertion 무변경 — §4.3). 새 계약(터틀 모드 000815 → 0)은 신규 파일 F-1 이 봉인.
2. **"ATR 기반 상한을 택하면 게이트 시그니처를 바꿔야 한다"(렌즈1)** → **시그니처 무변경.** 관문이 `_candidates[ticker]` 를 read-only 로 읽는다(⑤). 시그니처를 바꾸면 4 전략 `calc_buy_quantity` 의 return 6곳을 고쳐야 해 허용 목록("DEFAULT_PARAMS 키 추가만")을 벗어난다.
3. **"`[fallback_cap_config]` 부팅 시 1회"(자문 §3.3-(3))** → `boot_manager.py` 가 허용 목록 밖이라 **첫 관문 평가 시 1회/전략/일**로 대체. 감지 목적("캡이 조용히 꺼진 채 매수")엔 충분하다 — 그 사건은 매수 시도와 동시에 드러나고, 매수 시도가 없는 날엔 캡의 on/off 가 결과에 영향이 없다.
4. **자문 마커 `[fallback_cap_no_atr]`** → `[fallback_cap_skipped] reason=…` 로 일반화(사유 6종 분리 — `no_candidates`/`no_atr`/`ambiguous_atr`/`no_risk_pct`/`no_budget`/`exception` — `no_atr` 하나로 부르면 `risk_pct` 결측·예외가 ATR 배관 결함으로 오독된다).
5. **렌즈2 "as-was K∈[1.0,2.0] 결과 동일 → 후보 하단은 ⓐ 위장"** — 사실이지만 **08-18 입금 이전 표본**의 성질이다. 현행 예산 재정규화에선 K=1 → 7/26, K=2 → 14/26 으로 2배 갈린다(⑩). 구조 항등식 하한 2.44(중앙 ATR)는 "그 랏"의 성질이지 유니버스 통과율이 아니다 — 자문 §2.4: 유니버스 중앙 종목(54,100원 × ATR 6.1% ≈ 3,300원 ≤ 3,874원)은 **통과**, 캡은 가격 상위 꼬리만 자른다.

## 1. 확증된 원인 (3렌즈 코드 실측 + 렌즈2 BUY 46건 왕복 재구성)

| 사실 | 근거 |
|---|---|
| 폴백 발동 조건은 "비중 0주" 하나 — 관문 `qty <= 0` 분기. 터틀 모드에선 "터틀 0 → 비중 0" 2단 낙하가 선행. `_fallback_one_share` 의 유일한 상한은 `잔여 ≥ 현재가`; 가격·ATR·유닛 대비 상한 **전무** | `strategy_base.py:431-445`(헬퍼) · `:471-479`(분기) · 호출부 donchian `:1917-1923` / kojiro `:1122-1147` / vcp `:1410-1416` / bfb `:1369-1375` |
| 터틀 경로(`compute_unit_qty_guarded`)에는 변동성 floor·잔여·notional(`position_ratio×예산`) 3중 상한이 **무조건** 적용돼 "터틀 ≤ 비중" 불변식이 성립 — 상한을 통과 못한 종목이 오히려 **무상한 1주**로 사는 역전. 폴백이 유일한 누수 | `turtle_sizing.py:39-80` (`qty=min(qty, remaining//price)`, `min(qty, int(budget×ratio)//price)` 무조건) |
| 구조 항등식: 폴백 ⇔ `P > ρB` ⇒ 그 랏의 유닛 배수 `M1 = (P/B)·ATR%/r > (ρ/r)·ATR%` = donchian **40×ATR%**(중앙 6.10% → >2.44) / kojiro 33.2×ATR%(>1.42). 같은 항등식이 PR 경로(터틀 0 → `floor(ρB/P)`주)에도 성립 → PR 랏도 ≈40×ATR% 유닛(donchian 1.34~**3.71**, kojiro 1.13~1.36) | 렌즈2 report §10·§1 · `turtle_sizing.py:79` |
| 120일 BUY 226건 중 1주 170건(75.2%). donchian 실제 1랏 = 터틀 유닛 평균 **4.94**(중앙 4.42, 최대 15.61 = 086280 1주), kojiro 1.52. 1주 폴백 스택 −30% = 계좌 8.83%. cycle233 `[oversized_fallback]` 이 R15 위반을 실측(000815 3.10배) | 보고서 §0.0·§1.2 · `_workspace/pyramiding_review_20260903/pyramid/analyze.py:189-191` |
| 현행 예산 재정규화(net 2,582,132): donchian FB1 14건 M1 중앙 3.01·최대 8.66(192820) / kojiro FB1 3건(000815 3.44·018670 3.42·004690 1.12). K=2 컷 = donchian 12(11 완결 Σ−8,800·4승) + 클램프 1(124500 2→1주) / kojiro 2(000815 평가 +31,500 · 018670 −20,000) | 렌즈2 §9·§4 · 자문 §2.3 표 |
| 관측 산식 2종이 서로 다르다 — `[oversized_fallback]` cap = `position_ratio×예산`(ATR 무관, `strategy_base.py:506-510` = `portfolio_risk.py:226-270` 복제) vs 보고서 "4.94유닛" = `qty×ATR÷(예산×risk_pct)`. **의도된 이중 척도로 문서화**(ρ 축 = 갭·거래정지 명목 리스크 / K 축 = 정상 시장 손절 리스크, 대체재 아님) | 렌즈1 [HIGH c=0.93] · 자문 §3.2 |
| 폴백 경로는 `_entry_atr` 미스탬프(터틀 분기 성공 시에만 스탬프) → 과대 1주가 **% 손절**로 관리되고, 재시작 시 `_rederive_entry_atr` 이 소급 스탬프해 2ATR 로 갈아탄다(잠복 불일치). 이번 사이클 **무변경** — 캡 이후엔 랏 ≤ K유닛이라 최악 노출이 `K×2N = 예산 2.0%`(계좌 donchian 0.30%/kojiro 0.60%)로 유계 → §8 C 후속 | donchian `:1946-1949`·`:881-888` / vcp `:1440-1442` / bfb `:1399-1401` / kojiro `_position_atr` `:766,865` |
| 캡→0 은 `order_engine.execute_buy` 의 `quantity <= 0` 경로로 흘러 `block_low_funds(ticker, +900s)` + WARNING "매수 수량 0 → 900s cooldown (투자금: …)" = **오귀인**. `risk.py:628` 사전 스킵은 여전히 `price > total_investment` 라 비대칭(사전 통과 → 관문 0). 둘 다 8영역 — 무접촉, 문서·마커로 구분 | `order_engine.py:273,287-295,70` · `risk.py:620-628` |
| `[oversized_fallback]` 관측기는 `final_qty < 1` 조기 return → 캡→0 이면 침묵 → 차단 사실은 **별도 마커 필수** | `strategy_base.py:501-502` |
| `PUT /api/strategies/{id}/params` 는 화이트리스트 없이 `if key in strategy.config.params` 로 기존 키를 덮어쓰고 DB 영속 → 신규 키는 DB 부재 시 코드 기본 유지(안전) + 읽는 쪽 클램프 필요. DB→메모리 병합도 같은 조건 | `routes/strategies.py:167-183` · `scheduler.py:418-426` |
| A-PURE 는 `_apply_budget_limit` **본체만** walk(`_func_node(src, GATE)`) — 신규 헬퍼는 무가드 사각 → 확장 가드 필요. `strategies/CLAUDE.md` "터틀 키 6종 PARAM_RANGES 미편입"은 **기계 가드 부재한 문서 주장**(`grep min_vol_floor_pct tests/unit/ast/` 0건) | `test_budget_limit_ast.py:101-119` · 렌즈3 |
| `_candidates` ATR 키는 전략별 상호 배타 — donchian `"atr"`(`:587,817`) · kojiro `"atr"`(`:404,440,756`) · VCP `"atr14"`(`:495,1546`) · BFB `"atr14"`(`:425,1480`). VCP/BFB 의 `"atr": info["atr14"]`(`:1176`/`:1112`)는 `state.buy_signals` 대시보드 dict 이지 `_candidates` 가 아니다 | grep 실측 |
| `_MiniStrategy`(StrategyBase 직접 상속) 더블은 DEFAULT_PARAMS 병합을 타지 않는다 → K 를 `params` 에서만 읽으면 더블에서 캡이 조용히 비활성. 모듈 상수 기본값이 필요 | 렌즈3 · `momentum.py:67-70`(병합은 서브클래스 `__init__` 에서만) |

## 2. 시정 설계 (`src/engine/strategy_base.py` 주 + 4 전략 `DEFAULT_PARAMS` 1키)

### 2.1 모듈 상수·import (기존 `DailyEmitCap` import 아래)

```python
import math                                   # 신규 (isfinite)
from src.engine.turtle_sizing import compute_unit_qty   # 신규 — leaf(math 만 import), 순환 0. A-PURE 허용 모듈

# ── cycle242 랏당 최대 유닛 상한 (터틀 전략 한정) — 리스크 정체성 상수, PARAM_RANGES/INT_PARAMS 편입 금지 ──
_MAX_LOT_UNITS_DEFAULT = 2.0   # 4 터틀 전략 DEFAULT_PARAMS["max_lot_units"] 와 동치 (AST G-242-6)
_MAX_LOT_UNITS_MIN = 1.0       # K<1 은 "터틀 유닛보다 작게" = 정의상 무의미. 하한 1.0 = T 경로(qty ≤ u*) 무접촉의 수학 전제
_MAX_LOT_UNITS_MAX = 20.0      # 관측 최대 M1 15.61 < 20 → 20 = 사실상 현행 복귀 = 롤백 다이얼
```

### 2.2 `StrategyBase` 클래스 — ClassVar + `__init__` 2 속성

```python
    # cycle242 — 캡 ATR 소스 키. 터틀 사이징이 읽는 `_candidates[ticker]` 의 키와 동일 집합이어야 한다
    # (donchian·kojiro = "atr" / VCP·BFB = "atr14", 실측 상호 배타). 두 키가 서로 다른 값을 동시에 가지면 채택하지 않는다(ambiguous).
    _SIZING_ATR_KEYS: ClassVar[tuple[str, ...]] = ("atr", "atr14")

    def __init__(self, config):
        ...
        # cycle242 — 랏 유닛 상한 관측 cap (복합 키: "cap|{ticker}" / "skip|{ticker}|{reason}" / "cfg"). 날짜 키 자기 리셋.
        self._lot_cap_logged: DailyEmitCap[str] = DailyEmitCap[str]()
        self._lot_cap_day: str = ""
```

### 2.3 `_apply_budget_limit` — 1줄 삽입 + docstring 단서 (분기 순서 byte 보존)

```python
        if current_price <= 0:
            return 0
        if qty <= 0:
            final = self._fallback_one_share(current_price)
            _via_fallback = True
        else:
            remaining = max(0, self.state.total_investment - self._calc_used_funds())
            final = min(qty, remaining // current_price)
            _via_fallback = False
            if final < qty:
                self._emit_budget_clamp(ticker, qty, final, remaining)
        # cycle242 — 랏당 최대 유닛 상한 (행위, 터틀 전략 한정). 폴백/잔여 클램프 **뒤** · 관측 **앞**.
        # 캡 산출 실패는 현행 수량 유지(fail-open) — 헬퍼 내부에서 흡수·LOUD.
        final = self._apply_lot_units_cap(final, current_price, ticker, via_fallback=_via_fallback)
        try:
            self._emit_oversized_fallback(ticker, final, current_price)
        except Exception:  # pragma: no cover
            pass
        return final
```

docstring 단서(C2): *"부분 매수를 허용한다(유닛 미만 스킵 아님). **단, `sizing_mode="turtle"` 전략에서는 최종 랏이 `max_lot_units`(K) 유닛을 초과하면 초과분을 자르고, K 유닛이 1주에 못 미치면 매수하지 않는다**(cycle242 — 1주 폴백이 설계 유닛의 수 배가 되던 §0.0 결함 시정. 고정%손절 전략은 position_ratio 가 이미 리스크 균등이라 범위 밖)."* + "관측 전용" 서술을 "캡은 행위, 세 마커는 관측"으로 갱신.

### 2.4 신규 헬퍼 6 (전부 동기·순수 — await/DB/HTTP 0, A-PURE 확장 대상)

```python
    def _read_max_lot_units(self) -> float:
        """`max_lot_units` 읽기 + 클램프. 비수치·None·bool·비유한·<MIN → DEFAULT / >MAX → MAX."""
        raw = self.config.params.get("max_lot_units", _MAX_LOT_UNITS_DEFAULT)
        if isinstance(raw, bool):
            return _MAX_LOT_UNITS_DEFAULT
        try:
            k = float(raw)
        except (TypeError, ValueError):
            return _MAX_LOT_UNITS_DEFAULT
        if not math.isfinite(k) or k < _MAX_LOT_UNITS_MIN:
            return _MAX_LOT_UNITS_DEFAULT
        return min(k, _MAX_LOT_UNITS_MAX)

    def _resolve_sizing_atr(self, ticker: str | None) -> tuple[float | None, str]:
        """터틀 사이징과 **같은 소스**(`_candidates[ticker]`)에서 ATR 을 읽는다 — read-only.

        반환 (atr, reason): reason ∈ {"ok","no_ticker","no_candidates","no_atr","ambiguous_atr"}.
        `_SIZING_ATR_KEYS` 중 양수로 파싱되는 값을 모아 **서로 다른 값이 2개 이상이면 채택하지 않는다**
        (어느 키가 사이징에 쓰였는지 관문은 모르므로 — 틀린 ATR 로 상한을 계산하느니 현행 유지).
        `_candidates` 를 변경·생성하지 않는다(setdefault/pop/update 금지 — AST G-242-8).
        """
        if not ticker:
            return None, "no_ticker"
        cands = getattr(self, "_candidates", None)
        if not isinstance(cands, dict):
            return None, "no_candidates"
        info = cands.get(ticker)
        if not isinstance(info, dict):
            return None, "no_atr"
        values: list[float] = []
        for key in self._SIZING_ATR_KEYS:
            raw = info.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0 and v not in values:
                values.append(v)
        if not values:
            return None, "no_atr"
        if len(values) > 1:
            return None, "ambiguous_atr"
        return values[0], "ok"

    def _apply_lot_units_cap(self, final: int, current_price: int, ticker: str | None,
                             *, via_fallback: bool) -> int:
        """랏당 최대 유닛 상한 — `sizing_mode == "turtle"` 전략의 모든 랏에 `min(final, floor(K × 예산 × risk_pct ÷ ATR))`.

        - 캡 산출은 `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)` 재사용(새 수식 금지).
        - fail-open: 모드 아님 / ticker None / ATR 결측·모호 / risk_pct ≤ 0 / 예외 → `final` 그대로.
          ATR·risk_pct·예외 사유는 `[fallback_cap_skipped]` WARNING(cap) 으로 LOUD. 모드 아님·ticker None 은 조용히.
        - 행위(반환값)는 관측 성패와 무관 — 세 emit 은 내부에서 예외 흡수.
        """
        if final < 1 or current_price <= 0:
            return final
        try:
            params = self.config.params
            mode = params.get("sizing_mode")
            k = self._read_max_lot_units()
            budget = int(self.state.total_investment or 0)
            try:
                risk_pct = float(params.get("risk_pct") or 0)
            except (TypeError, ValueError):
                risk_pct = 0.0
            self._emit_fallback_cap_config(mode, k, budget, risk_pct)      # 1회/전략/일, 예외 흡수
            if mode != "turtle" or ticker is None:
                return final
            if risk_pct <= 0 or budget <= 0:
                self._emit_fallback_cap_skipped(ticker, "no_risk_pct" if risk_pct <= 0 else "no_budget",
                                                final, current_price)
                return final
            atr, reason = self._resolve_sizing_atr(ticker)
            if atr is None:
                self._emit_fallback_cap_skipped(ticker, reason, final, current_price)  # no_atr | ambiguous_atr
                return final
            cap_qty = compute_unit_qty(budget, atr, risk_pct, fraction=k)   # = floor(K·B·r/ATR), 음수 방지 내장
            if final <= cap_qty:
                return final
            self._emit_fallback_notional_capped(
                ticker, via_fallback=via_fallback, price=current_price, atr=atr, k=k,
                req_qty=final, capped_qty=cap_qty, budget=budget, risk_pct=risk_pct,
            )
            return cap_qty
        except Exception:
            # 캡 산출 자체가 던지면 현행 수량 유지 (변경 이전 행위 쪽으로 fail) + 흔적
            try:
                self._emit_fallback_cap_skipped(ticker, "exception", final, current_price)
            except Exception:
                pass
            logger.debug("[fallback_cap_skipped] exception ticker=%s", ticker, exc_info=True)
            return final
```

관측 헬퍼 3 — 공통 골격: 함수 전체 `try/except Exception: pass`, 날짜 키 `datetime.now(_KST).date().isoformat()` 가 `_lot_cap_day` 와 다르면 `_lot_cap_logged.reset_daily()` 후 갱신, **`should_emit(key)` → `logger.*` → `mark_emitted(key)`** 순서(peek→로그→mark).

```python
    def _emit_fallback_notional_capped(self, ticker, *, via_fallback, price, atr, k, req_qty, capped_qty, budget, risk_pct):
        # key = f"cap|{ticker}"  · INFO
        # "[fallback_notional_capped] ticker=%s strategy=%s path=%s price=%d atr=%d unit_qty=%.3f k=%.2f "
        # "req_qty=%d capped_qty=%d units_before=%.2f units_after=%.2f budget=%d risk_pct=%.4f"
        #   path = "fallback" if via_fallback else "sized"
        #   unit_qty = budget*risk_pct/atr (실수 u*) · units_before = req_qty*atr/(budget*risk_pct) · units_after = capped_qty*atr/(budget*risk_pct)

    def _emit_fallback_cap_skipped(self, ticker, reason, final, price):
        # key = f"skip|{ticker or '-'}|{reason}" · WARNING
        # "[fallback_cap_skipped] ticker=%s strategy=%s reason=%s qty=%d price=%d — 캡 미적용(현행 수량 유지, fail-open)"

    def _emit_fallback_cap_config(self, mode, k, budget, risk_pct):
        # key = "cfg" · INFO
        # "[fallback_cap_config] strategy=%s sizing_mode=%s cap=%s k=%.2f budget=%d risk_pct=%.4f atr_max=%d"
        #   cap = "on" if mode == "turtle" else "off" · atr_max = int(k*budget*risk_pct) (1주 허용 ATR 상한, 원)
```

### 2.5 `_emit_oversized_fallback` — `units=` 필드 추가 (기존 접두 byte 보존)

```python
                atr, _r = self._resolve_sizing_atr(key if ticker else None)
                risk_pct = float(self.config.params.get("risk_pct") or 0)   # try → 0
                units_s = f"{final_qty * atr / (budget * risk_pct):.2f}" if (atr and risk_pct > 0) else "-"
                logger.info(
                    "[oversized_fallback] ticker=%s strategy=%s qty=%d notional=%d "
                    "cap=%d ratio=%.2f — 1주 폴백이 notional 상한 초과 (관측 전용) units=%s",
                    key, self.strategy_id, final_qty, notional, cap, notional / cap, units_s,
                )
```
기존 문자열 `"... (관측 전용)"` 까지 byte 동일 + ` units=%s` 만 뒤에 붙는다(cycle233 `"3.10" in message` 검사 호환). docstring 에 "ρ 축 관측 — K 축(`max_lot_units`) 행위와 병존, **비제로가 정상**(cycle242 의미 반전)" 추가. `units` 값 파싱 예외는 `-`.

### 2.6 부수 시정 — `_emit_budget_clamp` mark-before-log 1줄 재배치

`strategy_base.py:588-595` 의 `mark_emitted` 를 `logger.info(...)` **뒤**로 이동(cycle226 D-3 / cycle233 F4 규약 — 로그 자기실패가 그날 관측을 지우지 않게). 행위·서식·cap 키 무변경, 회귀 F-19 신설. 이 파일을 어차피 열므로 같은 결함 부류를 닫는다(cycle237 선례).

### 2.7 전략 4파일 — `DEFAULT_PARAMS` 1키 (각 `min_vol_floor_pct` 바로 아래)

```python
        "max_lot_units": 2.0,   # cycle242 — 랏당 최대 유닛(K). 터틀 모드 모든 랏 ≤ K유닛, floor(K×u*)==0 이면 미매수. PARAM_RANGES 미편입. 롤백 = DB 20.0
```
`donchian_swing.py`(`:127` 아래) · `kojiro.py`(`:208` 아래) · `vcp_breakout.py`(`:170` 아래) · `bull_flag_breakout.py`(`:145` 아래). **momentum/VB/LTV 에는 추가하지 않는다**(키가 있으면 "적용 대상"으로 오독 — AST G-242-6 이 부재를 단언). C-DEFAULT(`position_ratio×max_positions`)·cycle198/211 스코프 가드는 키 추가에 무영향(키 집합 동등 단언 부재 실측).

### 2.8 fail-open 경계 (계약)

| 상황 | 캡 | 행위 | 마커 |
|---|---|---|---|
| `final < 1` 또는 `price ≤ 0` | — | 그대로(0) | 없음(config 도 미발화) |
| `sizing_mode != "turtle"`(부재 포함) | off | 현행 byte 동일 | `[fallback_cap_config] cap=off` 1회/전략/일 |
| turtle ∧ `ticker is None` | off | 현행 | config 만(터틀 분기도 같은 조건에서 조용히 skip — 정합) |
| turtle ∧ 전략에 `_candidates` dict 자체가 없음(momentum/VB/LTV 에 turtle 주입 등) | off | 현행 | `skipped reason=no_candidates` WARNING |
| turtle ∧ `risk_pct ≤ 0`/비수치 | off | 현행 | `skipped reason=no_risk_pct` WARNING |
| turtle ∧ ATR 결측/0/비수치/음수 | off | 현행 | `skipped reason=no_atr` WARNING |
| turtle ∧ `atr`·`atr14` 상이 동시 존재 | off | 현행 | `skipped reason=ambiguous_atr` WARNING |
| turtle ∧ 캡 산출 예외 | off | 현행 | `skipped reason=exception` WARNING + debug 스택 |
| turtle ∧ `final ≤ cap_qty` | on(무발동) | 그대로 | 없음 |
| turtle ∧ `final > cap_qty ≥ 1` | **on** | `cap_qty`(축소) | `capped … capped_qty≥1` |
| turtle ∧ `cap_qty == 0` | **on** | **0**(미매수 → order_engine 900s cooldown, 오귀인) | `capped … capped_qty=0` |
| 관측 헬퍼 예외 | on 유지 | 캡 결과 그대로 | 없음(흡수) — mark 미기록이라 다음 호출에 재발화 |

## 3. 불변 계약

1. **관문 시그니처·분기 순서 불변** — `_apply_budget_limit(qty, current_price, ticker=None)`; `price≤0→0` → `qty≤0→_fallback_one_share` / `qty>0→잔여 클램프+[budget_clamp]` → **캡** → `[oversized_fallback]` → return (A-FALLBACK/Case D `assert_called_once_with(price)` 보존, G-242-3).
2. **`_fallback_one_share` 본체 diff 0** · `_calc_used_funds` diff 0 · `turtle_sizing.py` diff 0 · `compute_unit_qty_guarded` 3중 상한 무접촉.
3. **A-GATE·A-ATOMIC·A-PURE 유지** + A-PURE 를 신규 헬퍼 6 + `_fallback_one_share` + `_emit_oversized_fallback` 으로 확장(G-242-2). 관문 안 `await`/DB/HTTP 0.
4. **터틀 게이트는 진입 사이징에만** — `check_exit_signal`·`_entry_atr` 스탬프 규약·`_rederive_entry_atr`·kojiro `_position_atr` **무접촉**. "ATR 손절 게이트는 `_entry_atr` 스탬프 존재(`sizing_mode` 게이팅 금지)" 금기와 충돌 없음(C8) — 전략 파일 `check_exit_signal` diff 0 이 증거.
5. **T 경로 byte 동일** — K ≥ 1.0 이면 정상 터틀 수량(≤ u*)은 어떤 (B, r, ATR, P) 에서도 캡에 안 걸린다(하한 1.0 클램프가 전제, F-4/F-16).
6. **비터틀 5전략 byte 동일** — cycle233 6케이스·A-FALLBACK·Case A/D/E·전략 폴백 3건 무수정 PASS 가 곧 증거(F-6/F-17).
7. **fail-open 방향 고정** — 결측·모호·예외 = 현행 수량. 수량을 0 으로 만드는 fail-closed 구현은 FAIL(F-5 = P0-1 재현 방지 가드).
8. **캡 ATR = 사이징 ATR 소스 동일** — `_candidates[ticker]` 의 `("atr","atr14")` 만 읽고(read-only) 모호하면 불채택(F-14/F-15, G-242-8).
9. **행위는 cap 밖** — 세 마커 성패와 무관하게 `cap_qty` 반환(F-9). 마커는 `system_logs` 로 `write_log` 이중 INSERT 0(logger 만 — cycle72 규약).
10. **`max_lot_units` ∉ PARAM_RANGES/INT_PARAMS**(런타임 + 소스 리터럴, G-242-1) · 읽는 쪽 `[1.0, 20.0]` 클램프 · 기본 2.0 은 상수 1곳 + 리터럴 4곳 동치(G-242-6) · **AI 자문·자동 적용 경로 편입 금지**.
11. **캡 로직은 관문 안에만** — 전략 파일 `calc_buy_quantity`/`_turtle_buy_quantity` 에 `max_lot_units`·`fraction=` 토큰 0(G-242-7), 전략 4파일 diff = DEFAULT_PARAMS 1줄.
12. 8영역 diff 0 · `scheduler.py` diff 0 · `boot_manager.py` diff 0 · `StrategyState` dataclass 필드 무변경(cap 상태는 `StrategyBase` 인스턴스 속성 — reset_daily 가드 무영향).

## 4. Red 테스트 목록

### 4.1 `tests/unit/engine/test_cycle242_fallback_notional_cap.py` (신규 — ID 접두 `test_f242_`)

픽스처: (a) `_MiniStrategy`(cycle233 패턴, `StrategyBase` 직접 상속) + `params={"exchange":"KRX","position_ratio":ρ,"sizing_mode":"turtle","risk_pct":0.005}` + `s._candidates = {ticker: {"atr": X}}` 주입 (b) 실전략 `_mk` 관용구(`test_cycle_p2a2_donchian_turtle._mk` · `test_kojiro_turtle_guarded._kojiro` 동형 로컬 재정의 — 다른 테스트 모듈 import 금지). 실측 수치: kojiro 예산 **774,640**·ρ 0.166 / donchian **387,320**·ρ 0.20 / r 0.005. caplog = `caplog.at_level(logging.INFO)` (WARNING 은 `levelno` 필터). 시각은 `freeze_kst` 루트 fixture 또는 `freezegun` KST aware 문자열만.

| ID | 시나리오 | 기대 |
|---|---|---|
| F-1 **(현행 FAIL — 핵심)** 000815 실측 | `_MiniStrategy("kojiro")` B=774,640 ρ=0.166 r=0.005, `_candidates["000815"]={"atr":13300}`, `_apply_budget_limit(0, 405_500, "000815")` | **`== 0`** · INFO `[fallback_notional_capped] ticker=000815 strategy=kojiro path=fallback price=405500 atr=13300 unit_qty=0.291 k=2.00 req_qty=1 capped_qty=0 units_before=3.43 units_after=0.00 budget=774640 risk_pct=0.0050` 정확 1행 · `[oversized_fallback]` **0행**(final<1) · `[fallback_cap_skipped]` 0 |
| F-2 통과 + 이중 척도 | 같은 B, `_candidates["004690"]={"atr":4290}`, price 130,000 | `== 1`(u*=0.903 → floor(1.806)=1) · capped 마커 0 · `[oversized_fallback] … ratio=1.01 … units=1.11` 1행(130,000 > cap 128,590) |
| F-3 **(현행 FAIL — 스코프 ii 핵심)** PR 경로 클램프 | 실 `DonchianSwingStrategy` turtle, B=387,320 ρ=0.2 r=0.005, `_candidates["124500"]={"atr":3593,"prev_close":38000,"ema60":0,"donchian_high":0}`, price 38,000 | 터틀 floor(0.539)=0 → PR `int(77,464)//38,000=2` → **`== 1`** · 마커 `path=sized req_qty=2 capped_qty=1 units_before=3.71 units_after=1.86` · **`"124500" not in s._entry_atr`**(PR 경로 미스탬프 규약 불변) |
| F-4 T 경로 무접촉 | donchian turtle B=100M ATR 3000 price 60000 → 166 · kojiro turtle 동형 · 그리드 (price∈{5k,20k,60k,250k}) × (ATR%∈{1%,2.5%,5%,10%}) 에서 `calc_buy_quantity == compute_unit_qty_guarded(...)` 결과와 **동일**, `_entry_atr` 스탬프 동일, capped 마커 0 | 정상 터틀 랏은 한 건도 안 건드린다 |
| F-5 **fail-open**(P0-1 재현 방지) | turtle 000815 픽스처에서 (a) `_candidates` 속성 없음 (b) `{}` (c) `{"atr":0}` (d) `{"atr":"abc"}` (e) `{"atr":-1}` (f) `risk_pct` 0 / None / "x" (g) `compute_unit_qty` 를 raise 로 monkeypatch | 전부 **`== 1`(현행 유지)** · `[fallback_cap_skipped] reason=no_atr`×(a~e, `strategy=kojiro ticker=000815`) / `no_risk_pct`×(f) / `exception`×(g) WARNING 각 1행 · 예외 전파 0. **수량 0 이면 FAIL** |
| F-6 비터틀 byte 동일 | (a) `_MiniStrategy` `sizing_mode` 부재 + 000815 픽스처 → `== 1` + capped 0 + `[oversized_fallback]` 1행(cycle233 계약 그대로) (b) `"position_ratio"` 명시 → 동일 (c) momentum/VB/LTV 실전략에 `{"sizing_mode":"turtle","risk_pct":0.005}` 주입(`test_kojiro_turtle_sizing` REGRESS 관용구) → 세 전략은 `_candidates` 속성이 없으므로(grep 실측) `[fallback_cap_skipped] reason=no_candidates` WARNING 1행 + 수량 = 미주입 인스턴스와 **동일** (d) donchian/VCP/BFB 에 같은 주입 + 후보 비어 있음 → `reason=no_atr` + 수량 동일 | cycle233 계약이 position_ratio 모드에서 유효함을 직접 봉인 + 비터틀 3전략은 캡 정의 자체가 불가함을 봉인 |
| F-7 ticker None | turtle donchian `calc_buy_quantity(60000)` (ticker 생략) | PR 수량 그대로 · capped/skipped 0 · config 1행 |
| F-8 cap 규약 | 같은 (전략,ticker) 2회 → capped 1행 / 다른 ticker → 각 1행 / `skipped` 는 (ticker,reason) 별 / 두 인스턴스 같은 ticker → 각 1행(인스턴스 격리) / freezegun 으로 KST 날짜 경계 → 재발화(자기 리셋) / config 는 1회/전략/일 | 폭주 0 · 날짜 키 |
| F-9 peek→로그→mark + 행위 cap 밖 | `logger.info` 를 `[fallback_notional_capped]` 문자열에 raise 하도록 monkeypatch → 000815 호출 → 복원 → 재호출 | 두 호출 모두 **`== 0`**(행위 불변) · 예외 전파 0 · 2회째 마커 정상 발화(실패 시 mark 미기록). skipped/config 동형 1케이스씩 |
| F-10 파라미터 클램프 | `_read_max_lot_units()`: 0 / −1 / "abc" / None / True / 0.99 / `float("inf")` → **2.0**; 999 → **20.0**; 1.0 → 1.0; 20.0 → 20.0; 2.5 → 2.5. 행위: 000815 픽스처 `max_lot_units=20.0` → **`== 1`**(롤백 다이얼 실증, floor(20×0.291)=5) · `=1.0` 에서 004690 → **0**(ⓐ 등가 실증) · `=0` 에서 000815 → 0(기본 2.0 적용, 전면 차단 아님을 F-2 004690 → 1 로 대조) |
| F-11 DEFAULT_PARAMS·DB 병합 | 4 터틀 전략 `DEFAULT_PARAMS["max_lot_units"] == 2.0 == strategy_base._MAX_LOT_UNITS_DEFAULT` · momentum/VB/LTV 부재 · `scheduler` 병합 관용구(`if key in params: params[key]=val`) 로 20.0 주입 시 `_read_max_lot_units()==20.0` | 롤백 경로 전제 |
| F-12 `[oversized_fallback] units=` | F-2 에서 `units=1.11` · ATR 결측 turtle 에서 발화 시 `units=-` · position_ratio 모드(cycle233 픽스처)에서 `units=-`(risk_pct 없음) 또는 값 · 접두 `"… (관측 전용)"` byte 보존(`"3.10" in message` 재확인) |
| F-13 config 마커 | 첫 관문 통과 시 `[fallback_cap_config] strategy=kojiro sizing_mode=turtle cap=on k=2.00 budget=774640 risk_pct=0.0050 atr_max=7746` 1행 · position_ratio 더블은 `sizing_mode=position_ratio cap=off` · `final<1` 호출(price 0)에선 미발화 |
| F-14 ATR 소스 동일성 | 4 실전략 turtle: 네이티브 키만 있는 후보(donchian/kojiro `atr`, VCP/BFB `atr14`) → `_resolve_sizing_atr(t) == (스탬프된 _entry_atr[t] 또는 kojiro 사이징 ATR, "ok")`; `{"atr":3000,"atr14":3200}` → `(None,"ambiguous_atr")`; `{"atr":3000,"atr14":3000}` → `(3000.0,"ok")`; `{"atr":3000,"atr14":0}` → `(3000.0,"ok")` |
| F-15 read-only | `_resolve_sizing_atr` 호출 전후 `_candidates` 딥 동등 + 없던 ticker 키 미생성 |
| F-16 항등식(스코프 ii 불변식) | 결정적 그리드 (B∈{387,320, 774,640, 5M}) × (ATR∈{500..40,000}) × (P∈{3k..500k}) × (ρ∈{0.166,0.2,0.25}) × (K∈{1.0,2.0,2.5,20.0}) 에서 turtle `_MiniStrategy` 로 `final = _apply_budget_limit(q, P, t)` (q ∈ {0, PR 수량}) → `final ≥ 1 ⇒ final×ATR/(B×r) ≤ K + 1e-9` | 모든 경로에서 `lot_units ≤ K` |
| F-17 기존 회귀 | §5 표적 목록 | 전부 **무수정 PASS**(전제 정정 ①) |
| F-18 order_engine 오귀인 문서 대응(읽기만) | `execute_buy` 가 `calc_buy_quantity` 0 에 `block_low_funds` 를 거는 기존 테스트 존재 확인(신규 작성 0) — 스펙 §7 오귀인 항목의 근거 | 8영역 무접촉 |
| F-19 `_emit_budget_clamp` 순서 | `logger.info` raise 주입 → 첫 호출 예외 0 + 두 번째 호출에서 `[budget_clamp]` 정상 발화(mark 가 로그 뒤) | §2.6 |

### 4.2 `tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py` (신규 — `parents[3]`, cycle212 `_collect_named_literal_str_keys` 헬퍼 로컬 복제)

| ID | 검사 | 뮤테이션 표적 |
|---|---|---|
| G-242-1 | `"max_lot_units"` ∉ `rec_mod.PARAM_RANGES`/`INT_PARAMS`(런타임) ∧ ∉ `recommendation_engine.py` 소스의 `PARAM_RANGES` dict / `INT_PARAMS` set 리터럴 str 키 + self-test 앵커(`"volume_multiplier"` 는 검출됨) | AI 자문 편입 |
| G-242-2 | A-PURE 확장 — `StrategyBase` 소스에서 함수 집합 {`_apply_budget_limit`, `_apply_lot_units_cap`, `_read_max_lot_units`, `_resolve_sizing_atr`, `_emit_fallback_notional_capped`, `_emit_fallback_cap_skipped`, `_emit_fallback_cap_config`, `_fallback_one_share`, `_emit_oversized_fallback`, `_emit_budget_clamp`} 각각 `ast.Await` 0 ∧ 금지 import(`src.db`,`httpx`,`requests`,`asyncio`,`aiohttp`) 0 ∧ 함수가 전부 존재(부재 = FAIL) | 헬퍼로 빼서 await 유입 |
| G-242-3 | `_apply_budget_limit` 본문 lineno 순서: `_fallback_one_share` 호출 < `_emit_budget_clamp` 호출 < **`_apply_lot_units_cap` 호출** < `_emit_oversized_fallback` 호출 < 마지막 `Return` ∧ `_apply_lot_units_cap` 호출 결과가 `final` 에 대입(`Assign` target `final`) ∧ 호출이 정확히 1회 | 캡 위치 이동·미대입·관측 뒤 배치 |
| G-242-4 | `_apply_lot_units_cap` 본문에 `Compare`(Constant `"turtle"`) 존재 ∧ `compute_unit_qty` 호출(kwarg `fraction`) 정확 1회 ∧ `math.floor`/`//`/`round(` 로 유닛 수량을 직접 계산하는 노드 0 ∧ 본문 최상위가 `Try`(handler `except Exception`)로 감싸짐 ∧ `_resolve_sizing_atr` 호출 존재 | 새 수식·게이트 제거·try 제거 |
| G-242-5 | 세 emit 헬퍼 + `_emit_oversized_fallback` + `_emit_budget_clamp`: 같은 함수 안에서 `mark_emitted` 호출 lineno > 대응 `logger.info/warning` 호출 lineno ∧ `should_emit` lineno < logger | mark-before-log |
| G-242-6 | 4 터틀 전략 파일 `DEFAULT_PARAMS` 리터럴에 `"max_lot_units"` 키 존재 ∧ 값 `== strategy_base._MAX_LOT_UNITS_DEFAULT` ∧ momentum/VB/LTV 리터럴엔 **부재** ∧ `_MAX_LOT_UNITS_MIN == 1.0` ∧ `_MAX_LOT_UNITS_MAX == 20.0` ∧ MIN ≤ DEFAULT ≤ MAX | 기본값 불일치·비터틀 오편입·하한 완화 |
| G-242-7 | 7 전략 파일 `calc_buy_quantity`·`_turtle_buy_quantity` 노드 안에 `max_lot_units` 토큰 0 ∧ `fraction=` kwarg 0 ∧ 기존 A-GATE 재확인(모든 return 관문 경유) | 캡 로직 전략 누출 |
| G-242-8 | `_resolve_sizing_atr` 본문에 `_candidates` 대상 `Subscript` 대입/`setdefault`/`pop`/`update`/`__setitem__` 0(read-only) ∧ `_SIZING_ATR_KEYS == ("atr","atr14")` 런타임 ∧ 4 터틀 전략의 터틀 블록(donchian/vcp/bfb `_turtle_buy_quantity`, kojiro `calc_buy_quantity`)이 읽는 `.get("<key>")` 문자열 상수 ⊆ `_SIZING_ATR_KEYS` | 소스 분기·쓰기 유입 |
| G-242-9 | `strategy_base.py` 의 `[fallback_notional_capped]`/`[fallback_cap_skipped]`/`[fallback_cap_config]` 문자열 상수 각 ≥1 ∧ 각 emit 사이트가 `Try` 하위 ∧ cycle72 동형 `write_log` 근접 호출 0 | 예외 전파·이중 INSERT |

기존 가드 **재작성 금지** — 표적 실행에 포함만: A-ATOMIC/A-PURE/A-GATE/C-*(`test_budget_limit_ast.py`) · cycle226 `test_common_1_eight_areas_untouched` · cycle222a3 anchor/owner · cycle223 exit fix · cycle233 account risk · cycle198/211 DEFAULT_PARAMS scope · cycle209/212 PARAM_RANGES · cycle223f manual apply.

### 4.3 기존 테스트 개정 (assertion 무변경 — docstring 재스코프 1파일)

- `tests/unit/engine/test_cycle233_oversized_fallback.py` 모듈 docstring: *"수량이 0 이 되는 구현은 부속안 ② 오구현으로 FAIL 이 계약"* → *"**position_ratio 모드(본 파일 픽스처)에서는** 수량 0 = 오구현으로 FAIL 이 계약. `sizing_mode="turtle"` 에서는 cycle242(사용자 결정 2026-09-03, G0-ⓑ)가 `max_lot_units` 상한을 도입해 같은 000815 픽스처가 **0 이 정답**이다 — `test_cycle242_fallback_notional_cap.py` F-1/F-6 참조. `[oversized_fallback]` 은 이제 ρ 축 관측으로 K 축 행위와 병존(비제로 정상)."* 6 케이스 assertion **byte 무변경**.
- 선택: `test_cycle_p2a2_donchian_turtle.py::test_turtle_identity_keys_excluded_from_param_ranges`·`test_bfb/vcp_turtle_sizing.py::test_turtle_keys_excluded_from_param_ranges` 의 키 튜플에 `"max_lot_units"` 추가 가능(중복 — G-242-1 이 정본이므로 생략해도 된다).

## 5. Green 범위

- `src/engine/strategy_base.py`: §2.1 import 2 + 상수 3 · §2.2 ClassVar 1 + `__init__` 속성 2 · §2.3 관문 1줄 삽입 + docstring · §2.4 헬퍼 6 · §2.5 `units=` 필드 · §2.6 1줄 재배치. 예상 +150L 안팎(이 파일엔 라인 상한 없음).
- 전략 4파일: `DEFAULT_PARAMS` 1줄씩(§2.7). **그 외 diff 0**(G-242-7 + `git diff --stat` 로 확인).
- 신규 테스트 2파일(§4.1·§4.2) + cycle233 docstring(§4.3). 인덱스 `python tools/test_impact/build_index.py`.
- **무접촉 기대**: 8영역 · `scheduler.py`(3,999L) · `boot_manager.py` · `turtle_sizing.py` · `portfolio_risk.py` · `recommendation_engine.py` · `routes/*` · `StrategyState` · 전략 `check_exit_signal`/`calc_buy_quantity`/`_turtle_buy_quantity` 본문.
- 표적 실행(Green 후):
  `python -m pytest -q -p no:cacheprovider tests/unit/engine/test_cycle242_fallback_notional_cap.py tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py tests/unit/engine/test_cycle233_oversized_fallback.py tests/unit/engine/test_budget_limit_gate.py tests/unit/engine/test_strategy_fallback_budget.py tests/unit/ast/test_budget_limit_ast.py tests/unit/engine/strategies/test_cycle_p2a2_donchian_turtle.py tests/unit/engine/strategies/test_kojiro_turtle_guarded.py tests/unit/engine/strategies/test_kojiro_turtle_sizing.py tests/unit/engine/strategies/test_bfb_turtle_sizing.py tests/unit/engine/strategies/test_vcp_turtle_sizing.py tests/unit/engine/strategies/test_p1a_donchian_layered_exit.py tests/unit/engine/strategies/test_volatility_breakout.py tests/unit/engine/strategies/test_bull_flag_breakout.py tests/unit/engine/strategies/test_vcp_breakout.py tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::test_common_1_eight_areas_untouched tests/unit/ast/test_cycle222a3_ast_anchor_owner_coupling.py tests/unit/ast/test_cycle222a3_ast_followup_fixes.py tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py tests/unit/ast/test_cycle233_ast_account_risk.py tests/unit/ast/test_cycle198_ast_default_params_scope.py tests/unit/ast/test_cycle211_ast_default_params_scope.py tests/unit/ast/test_cycle209_ast_extension_param_range.py tests/unit/ast/test_cycle212_ast_entry_threshold.py tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py tests/unit/engine/test_budget_invariant_runtime_guard.py tests/unit/engine/test_cycle233_account_risk_gate.py tests/integration/test_reset_daily_state.py tests/unit/engine/strategies/`
  전체 스위트는 Docs 단계 1회(cycle241 기준선 **6,002 passed, 10 skipped, 328 xfailed, 13 xpassed** + 신규분).
- Green 중 `len(caplog.records) == N` 형 정확 개수 단언이 신규 `[fallback_cap_config]` INFO 1행 때문에 트립하면 **그 테스트에 prefix 필터를 넣는 적응만** 허용(의미 무변경) — 마커를 debug 로 낮추는 우회 금지(감지 목적 소멸).

## 6. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| m1 | `final = self._apply_lot_units_cap(...)` 라인 삭제 | F-1/F-3/F-16 FAIL + G-242-3 |
| m2 | `if final <= cap_qty` → `>=` / `min`→`max` | F-1/F-2 FAIL |
| m3 | ATR 결측 시 `return 0`(fail-closed) | F-5 FAIL(+ 기존 `test_kojiro_turtle_sizing` FALLBACK 4건 FAIL) |
| m4 | 캡을 `qty <= 0` 분기 안에만(스코프 i) | F-3 FAIL |
| m5 | `mode != "turtle"` 게이트 제거 | F-6 FAIL + cycle233 6케이스 FAIL |
| m6 | `mark_emitted` 를 logger 앞으로 | F-9 FAIL + G-242-5 |
| m7 | `DailyEmitCap` 제거(매 호출 로그) / 날짜 키 제거 | F-8 FAIL |
| m8 | `_read_max_lot_units` 클램프 제거(K=0 통과) | F-10 FAIL(000815 K=0 → 0 은 같지만 004690 → 0 으로 갈려 검출) |
| m9 | `"max_lot_units": (1.0, 5.0)` 를 PARAM_RANGES 에 추가 | G-242-1 |
| m10 | `compute_unit_qty` 대신 `round(k*B*r/atr)` | G-242-4 + F-16 경계(round-up) |
| m11 | 캡 호출을 `_emit_oversized_fallback` 뒤로 | G-242-3 + F-1(`[oversized_fallback]` 1행 발화 → FAIL) |
| m12 | `_resolve_sizing_atr` 가 `atr14` 만 / 첫 키 우선(모호 시 채택) | F-14 FAIL |
| m13 | `_resolve_sizing_atr` 가 `cands.setdefault(ticker, {})` | F-15 + G-242-8 |
| m14 | 전략 `calc_buy_quantity` 에 `if units > k: return 0` 조기 반환 | A-GATE + G-242-7 |
| m15 | `_MAX_LOT_UNITS_MIN = 0.5` | G-242-6 + F-4(K=0.5 주입 시 T 경로 절반 = 검출 케이스 추가 권장) |
| m16 | 외곽 `try` 제거(캡 예외 전파) | F-5(g) FAIL + G-242-4 |
| m17 | 8영역·scheduler 1줄 | cycle226 가드 |

추가 렌즈: (i) **차분 실증** — 게이트 off 입력(7전략 기본 모드 × 가격/예산 그리드 3,000 조합)에서 `calc_buy_quantity` 와 `_entry_atr` 전이가 HEAD 와 **동일**(행위 변경은 turtle ∧ `final > floor(K·u*)` 구간에만) (ii) `git diff HEAD --name-only` ⊆ §5 허용 목록 · 4 전략 파일 `git diff --stat` 각 +1/−0(주석 포함 시 +2) (iii) `wc -l src/engine/scheduler.py` 3,999 (iv) 비용 — 관문당 추가 연산 = dict 조회 ≤3 + float 나눗셈 1(`compute_unit_qty`) + 문자열 포맷(발화 시만); hot path 아님(매수 시도당 1회) (v) m4·m11·m12 를 **사본 저장소**에서 실제 주입해 FAIL 실증(실트리 미접촉, cycle240 §10.2 규약) (vi) 캡이 `remaining` 클램프 **뒤**라 "잔여 부족 1주"와 "캡 0주"가 로그에서 갈리는지 — `req_qty`(캡 전) + 별도 `[budget_clamp]` 로 분리됨을 로그 텍스트로 확인.

## 7. D+1 판독 채널 (배포 = 15:30 이후 NXT 애프터 또는 익일 07:55 `_boot` 전)

| 채널 | 정상 서명 | 이상 서명 → 해석 |
|---|---|---|
| `[fallback_cap_config]` | 매수 시도가 있는 전략마다 1행/일. **donchian_swing·kojiro = `sizing_mode=turtle cap=on k=2.00`**, `atr_max` ≈ donchian 3,873 / kojiro 7,746(예산 비례) | donchian/kojiro 에 `cap=off` = DB `sizing_mode` 리셋(조용한 꺼짐) → 즉시 DB 확인. `k≠2.00` = 누가 PUT 으로 바꿈 |
| `[fallback_notional_capped]` | 기대 빈도 donchian ≈0.15건/영업일(12/80), kojiro ≈0.03 → **대부분의 날 0행**. 첫 실발화 = G0 ① 실증. `path=fallback` 우세, `capped_qty=0` 우세, `units_before` 2~9 | 하루 5건↑ 5영업일 연속 = R2(유니버스↔예산 미스매치). `units_after > 2.00` = 구현 결함(R3 핫픽스) |
| `[fallback_cap_skipped]` | **0행** | `reason=no_atr`/`ambiguous_atr` ≥1 = 후보 dict ATR 배관 결함(캡은 fail-open 이라 매수는 현행대로 나감 — 조용히 지나가지 않게 WARNING) / `exception` ≥1 = 코드 결함 |
| `[oversized_fallback] … units=` | **비제로가 정상**(의미 반전). `units ≤ 2.00` 전수 = G0 ② | `units > 2.00` 1건 = R3. `units=-` 가 turtle 전략에서 보이면 ATR 결손 |
| `order_engine` "매수 수량 0 → 900s cooldown (투자금: …)" | 캡 발화와 **같은 시각·같은 ticker** 로 짝지어 나타남 = 오귀인 정상 서명 | 캡 마커 없이 단독 = 진짜 잔여 부족(`[budget_clamp]`/잔고 확인) |
| donchian 실체결 BUY 건수 | 주 ~1건(0.175/일) — R1 카운트 시작 | 15영업일 연속 0 = R1 → K 2.5 검토 |
| `[account_risk_*]`/kojiro 오픈리스크 차단 | K=2 랏 = 예산 2.0% 오픈리스크 → kojiro Σ캡 4.5% 는 최대치 랏 2개에서 매수 정지(정상 작동) | 차단 증가를 캡 결함으로 오독 금지 |
| 보유 8종목 | 무영향(진입 사이징만) | — |

⚠️ **의미 반전 2** — `[oversized_fallback]` 은 "0 이 목표"에서 "≤K 유닛이면 정상"으로, order_engine 수량-0 WARNING 은 "잔고 부족"에서 "캡 스킵 포함"으로. 배포 전후 같은 grep 합산 금지(cycle228/240/241 교훈).

## 8. 후속 등재 (이번 사이클 밖) + 재검토 트리거

**재검토 트리거(자문 §6, 롤백 = 대상 전략 `strategy_config.params.max_lot_units = 20.0` DB UPDATE 또는 `PUT /api/strategies/{id}/params` — 코드 재배포 불필요)**

| # | 트리거 | 임계 | 조치 |
|---|---|---|---|
| R1 | donchian 매수 정지 | **15영업일 연속 BUY 0**(기대 2.6건, P(0)≈7%) | K=2.5 완화 검토(사용자 결정) |
| R2 | 캡이 유니버스 대부분을 자름 | `[fallback_notional_capped]` 5건/일 × 5영업일 연속 | K 완화가 아니라 **유니버스 가격 상한 도입** 또는 weight 재검토 |
| R3 | 캡 불성립 | `units_after > K` 또는 `[oversized_fallback] units > K` **1건** | 즉시 핫픽스(구현 결함) |
| R4 | 파라미터 커플링 | weight / `position_ratio` / `risk_pct` 변경 | K 실효 강도가 예산에 선형 비례 → **K 재검토 의무**(donchian weight 0.15→0.30 이면 상한 2배 헐거워짐) |
| R5 | 자연 은퇴 | 6개월 무발화 + `P_max` 중앙값 > 유니버스 90퍼센타일 | 게이트 **유지**(자본이 줄면 다시 필요) — 문서에 "자연 무발화" 기록, 삭제 금지 |
| R6 | 피라미딩 착수(T1) | 피라미딩 다크런치와 동시에 | **`max_lot_units` 를 1.0 으로 조인다**(K=2 랏 + 4유닛 사다리 = 8유닛 = R15 재위반) — G0/G2′ 문안에 못박음 |

**후속**
- **A. 6개월 재검정** — K 가 자른 종목군(고가·저ATR 대형주: 086280·095340·192820 류)의 사후 성과를 별도 표본으로 검정(선택 편향 정산 — 남은 표본의 엣지를 원 전략의 엣지로 읽지 않는다). 마커의 `price/atr/units_before` 필드가 그 표본을 만든다.
- **B. 명시 ATR 인자 전달** — 전략 파일을 다음에 접촉하는 사이클에서 `calc_buy_quantity` 가 사이징에 쓴 ATR 을 관문 kwarg(`sizing_atr=`)로 넘기도록 전환 → `_resolve_sizing_atr` 듀크타이핑 은퇴. F-14 는 그때 kwarg 동일성 테스트로 승계.
- **C. 폴백/PR 랏 `_entry_atr` 미스탬프 ↔ 재시작 소급 스탬프 불일치** — 자문 §7-5. 캡으로 노출이 `K×2N` 으로 유계됐으므로 별건(고승률·저RR 전략 복사 금지 원칙과 함께 domain-consult).
- **D. 고정%손절 5전략의 폴백 명목(갭) 상한(ρ 축)** — 별도 사용자 결정. 우선순위 = 오버나잇 갭에 실제 노출되는 **LTV** 부터(VB 15:20 청산·momentum 당일).
- **E. `[fallback_cap_config]` 부팅 시점 이관** — `boot_manager` 접촉 사이클에서 `_load_strategy_config` 직후 1회로 이관(현행 "첫 관문 평가" 마커는 유지 가능).
- **F. `risk.py:628` 사전 스킵 비대칭 · `order_engine` 900s 오귀인 문구** — 8영역. 캡 스킵 사유를 order_engine 로그에 병기하려면 반환 계약 변경이 필요해 별도 승인 사이클.
- **G. `portfolio_risk.compute_over_cap_positions`(cycle233 ρ 축 관측)에 `units` 병기** — 관측 전용, 필요 시.

## 9. 문서 동기화 (Docs 단계)

- 루트 `CLAUDE.md`:
  - 하네스 표 상단 1행 추가 + 최고령 1행(2026-08-25 cycle226) 제거 → 15행 유지(제거분은 변경로그 verbatim 기존재). 변경로그 `docs/HARNESS_CHANGELOG.md` L7 에 cycle242 상세 1행 append(■ 발단(§0.0 실측 4.94유닛·75.2% 1주) / 확증 원인 / 전제 정정 5 / 결정 12 / 구현 / Red·Green / 적대 검증 / D+1 / 후속 / 수치).
  - "자금 관리 › 1회 투자금액 ATR 유닛화" 항목 끝에: *"**랏당 최대 유닛 상한 `max_lot_units`(K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏(터틀·position_ratio 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고 0 이면 매수하지 않는다(1주 폴백이 설계 유닛의 평균 4.94배·최대 15.61배가 되던 진입 시점 과잉 피라미딩 시정, 매수를 줄이는 방향). K 는 리스크 정체성 상수 — PARAM_RANGES/INT_PARAMS 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프(하한 1.0 = 정상 터틀 랏 무접촉의 전제, 상한 20.0 = 롤백 다이얼). ATR 결측·모호·risk_pct 0 은 **fail-open**(현행 수량 + `[fallback_cap_skipped]` WARNING — fail-closed 는 P0-1 유령 키 재현 경로). 고정%손절 5전략 범위 밖(position_ratio 가 이미 리스크 균등). 피라미딩 착수 시 K→1.0"*.
  - 핵심 안전 규칙 "매수 수량은 전략 잔여 자금 기준" 항목 끝에: *"cycle242 — 관문은 폴백/잔여 클램프 **뒤**·관측 앞에서 터틀 전략 랏을 `max_lot_units` 유닛으로 자른다(캡 ATR 은 사이징과 같은 `_candidates[ticker]` 소스 read-only, 두 키 상이 시 불채택). 관문 안 `await`/DB 금지는 신규 헬퍼 6 에도 적용(AST G-242-2)"*.
  - 핵심 안전 규칙 "터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재" 항목 끝에: *"이 금기는 **청산** 규약이다 — 진입 사이징(`calc_buy_quantity`·`max_lot_units` 캡)이 `sizing_mode` 로 분기하는 것은 충돌이 아니다(cycle242 C8)"*.
- `src/engine/CLAUDE.md` `strategy_base.py` 절 `_apply_budget_limit` 문단: 순서 계약에 캡 삽입 · 마커 4종 기재(`[budget_clamp]`(mark 순서 시정) · `[oversized_fallback]`(cycle233, C7 결손 메움, `units=` 확장·비제로 정상) · `[fallback_notional_capped]` · `[fallback_cap_skipped]` · `[fallback_cap_config]`) · fail-open 경계 표 · order_engine 900s 오귀인 · `_resolve_sizing_atr` 계약 · K 클램프.
- `src/engine/strategies/CLAUDE.md`: (1) 자금관리 규약 "매수 수량은 `_apply_budget_limit` 관문…" 항목에 캡 1문장 (2) "터틀 키 6종 … 미편입" → **7종**(`max_lot_units` 추가) + *"가드 = `tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py` G-242-1(런타임 dict + 소스 리터럴). ⚠️ 종전 6종은 기계 가드 없이 문서 주장뿐이었다 — 후속에서 같은 가드에 편입 권장"* (3) "1주 폴백 (모든 전략)" 항목에 *"터틀 전략은 `max_lot_units` 캡이 뒤따른다(0 이면 미매수)"* (4) 매트릭스 표 donchian·kojiro 행 "터틀 상태"에 "K=2.0 캡 라이브" 부기.
- `_workspace/00_leader_trading_rules.md`: §2 "1회 투자금액 ATR 유닛화" 항목 아래 K 규칙 1항(위 CLAUDE.md 문안 축약) · DEFAULT_PARAMS 블록 4곳(donchian §6 · BFB `:609` · VCP `:751` · kojiro §2 전략 G) 에 `"max_lot_units": 2.0` 추가 + "PARAM_RANGES 미편입" 주석.
- `_workspace/00_URGENT_WORKLIST.md`: 신규 `## ✅ G0 · 1주 폴백 = 진입 시점 과잉 피라미딩 (피라미딩 심층 검토 §0.0) — cycle242 ⓑ 종결 (2026-09-03, 커밋 대기)` 항목(P1-6 형식: 실측 · 원인 · 사용자 결정 · 결정 12 · 전제 정정 5 · 관측 · D+1 표 · 트리거 R1~R6 · 후속 A~G · **G0 종료 기준 재정의**(⑪) · ⓐ 재검토 조건) + cycle232 표 G3′ 행 "1주 폴백 notional 초과는 **관측만**" 뒤에 *"→ cycle242 가 K 축 행위(`max_lot_units`)로 전환, ρ 축은 관측 병존"* 부기 + G-7(VCP/BFB 터틀 sizing) 행에 *"터틀 전환 시 `max_lot_units` 캡 자동 편입"* 1줄.
- `_workspace/domain_consult/pyramiding_deep_review_20260903.md` §4.3 G0 행: 종료 기준 셀에 *"(cycle242 재정의: `[fallback_notional_capped]` 실증 ∧ 신규 랏 `units ≤ K` 전수 ∧ 회귀 가드 — `[oversized_fallback]` 0 은 K>1 과 양립 불가)"* 한 줄 부기(커밋된 문서, 동시 워크플로 산출물 2건은 무접촉).
- `docs/HARNESS_CHANGELOG.md` append · `_workspace/test_index.yaml` 재생성 · 전체 스위트 1회 · 커밋·푸시는 **사용자 지시 대기**(배포 창 15:30 이후).

## 10. Green 구현 — 착수 후 기입 (backend-dev)

기입: backend-dev, 2026-09-03. 착수 시점 워킹트리에 `src/engine/strategy_base.py` + 4 터틀 전략
`DEFAULT_PARAMS` + 신규 테스트 2파일 + `test_cycle233_oversized_fallback.py` docstring 이 §2·§4.3
문언과 **byte 단위로 일치한 상태로 이미 반영**돼 있었다(동일 역할의 선행 pass 산출물로 추정 —
이 라운드는 그 구현을 스펙·Red 재대조 후 표적 스위트로 검증하고 §10 만 신규 기입했다. 코드 diff
신규 발생 0).

### 10.1 대조 결과 — §2/§3/§4.3 대비 편차 0

- `_apply_lot_units_cap`/`_read_max_lot_units`/`_resolve_sizing_atr`/`_emit_fallback_notional_capped`/
  `_emit_fallback_cap_skipped`/`_emit_fallback_cap_config` 6 헬퍼 + `_apply_budget_limit` 1줄 삽입
  (폴백/잔여 클램프 **뒤** · `[oversized_fallback]` **앞**, `final =` 대입, 호출 1회) — §2.2~§2.4 그대로.
  `_emit_budget_clamp` 의 `mark_emitted` 가 `logger.info` **뒤**로 재배치돼 §2.6 도 반영 확인.
- `_emit_oversized_fallback` 꼬리에 ` units=%s` 필드(atr/risk_pct 결측 시 `-`) — 접두 문자열
  `"... (관측 전용)"` 까지 byte 동일, cycle233 `"3.10" in message` 앵커 보존(§2.5).
- 4 전략 `DEFAULT_PARAMS` 각 `"max_lot_units": 2.0,` 1줄(§2.7 정확한 위치 — `min_vol_floor_pct` 인접).
  momentum/VB/LTV 무접촉.
- `test_cycle233_oversized_fallback.py` 모듈 docstring 이 §4.3 문언대로 재스코프, 6 케이스
  assertion 본문 byte 무변경.
- `tests/unit/engine/test_cycle242_fallback_notional_cap.py` (F-1~F-20) ·
  `tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py` (G-242-1~9) 신규 2파일이 §4.1/§4.2
  ID·기대값 그대로 존재.

### 10.2 표적 스위트 (§5 목록 — 파일명 정정 1건)

`test_cycle233_account_risk_gate.py` 는 실제 파일명이 `test_cycle233_account_risk_guard.py`(스펙
오타)라 정정해 실행:

```
python -m pytest -q -p no:cacheprovider \
  tests/unit/engine/test_cycle242_fallback_notional_cap.py \
  tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py \
  tests/unit/engine/test_cycle233_oversized_fallback.py \
  tests/unit/engine/test_budget_limit_gate.py \
  tests/unit/engine/test_strategy_fallback_budget.py \
  tests/unit/ast/test_budget_limit_ast.py \
  tests/unit/engine/strategies/test_cycle_p2a2_donchian_turtle.py \
  tests/unit/engine/strategies/test_kojiro_turtle_guarded.py \
  tests/unit/engine/strategies/test_kojiro_turtle_sizing.py \
  tests/unit/engine/strategies/test_bfb_turtle_sizing.py \
  tests/unit/engine/strategies/test_vcp_turtle_sizing.py \
  tests/unit/engine/strategies/test_p1a_donchian_layered_exit.py \
  tests/unit/engine/strategies/test_volatility_breakout.py \
  tests/unit/engine/strategies/test_bull_flag_breakout.py \
  tests/unit/engine/strategies/test_vcp_breakout.py \
  tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::test_common_1_eight_areas_untouched \
  tests/unit/ast/test_cycle222a3_ast_anchor_owner_coupling.py \
  tests/unit/ast/test_cycle222a3_ast_followup_fixes.py \
  tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py \
  tests/unit/ast/test_cycle233_ast_account_risk.py \
  tests/unit/ast/test_cycle198_ast_default_params_scope.py \
  tests/unit/ast/test_cycle211_ast_default_params_scope.py \
  tests/unit/ast/test_cycle209_ast_extension_param_range.py \
  tests/unit/ast/test_cycle212_ast_entry_threshold.py \
  tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py \
  tests/unit/engine/test_budget_invariant_runtime_guard.py \
  tests/unit/engine/test_cycle233_account_risk_guard.py \
  tests/integration/test_reset_daily_state.py \
  tests/unit/engine/strategies/
# → 1901 passed, 24 xfailed, 3 xpassed (0 failed)
```

추가로 "7전략 `calc_buy_quantity` 관련 테스트(grep)" + `test_strategy_base*.py` 전수(위 목록 밖
`calc_buy_quantity` 참조 파일 grep 합집합, 46 파일) 별도 실행 — `502 passed, 4 xfailed`(0 failed).

### 10.3 8영역 diff — 확인

```
git diff --stat -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ \
  src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py \
  src/engine/scheduler.py src/engine/boot_manager.py src/engine/turtle_sizing.py \
  src/engine/portfolio_risk.py
# → (빈 출력, diff 0)
```

전체 `git diff --stat` = `src/engine/strategy_base.py`(+263) + 전략 4파일(각 +1) + 테스트 2파일
docstring/sha핀 뿐(비허용 파일 2건은 §10.4 참조). 신규 미추적 파일 = 본 스펙 + Red 2파일 + 상위
domain-consult 산출물 2건(무접촉).

### 10.4 워킹트리에서 관찰만 하고 무접촉으로 남긴 것

이번 backend-dev 라운드가 시작되기 전부터 워킹트리에는 내 허용 목록 밖의 변경 2건이 이미
존재했다(다른 동시 세션 소관으로 판단 — 이번 라운드의 diff 신규 발생 0, 손대지 않음):

- `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` — kojiro/vcp/bfb 3파일 sha256 핀
  재핀(cycle242 가 그 3파일에 1줄씩 추가한 결과 자연 트리거되는 정규 자기소멸 절차, §5 표적
  스위트에 포함돼 PASS 확인됨). `_CYCLE228_STRATEGY_CONTENT_SHA` 주석이 "cycle233 커밋 후 삭제"
  → "cycle233+242 커밋 후 삭제" 로 갱신돼 있었다.
- `_workspace/00_URGENT_WORKLIST.md` / `_workspace/morning_0903_report.md` — G-8′(BFB·VCP 진입
  완화) 항목 추가. 스펙 상단 컨텍스트가 명시한 "동시 실행 중인 읽기 전용 워크플로 2개" 중 하나의
  산출물로 판단, 이번 사이클(cycle242) 워크리스트 항목은 아직 미기재 — §9 Docs 단계에서 별도
  team-leader/Docs pass 가 처리할 사안(내 이번 라운드 범위 밖).

### 10.5 결론

Green 구현은 스펙 §2·§3·§4.3 을 편차 없이 만족한다. 코드 신규 작성 0(대조·검증만), 표적 스위트
전량 PASS, 8영역+scheduler+boot_manager+turtle_sizing+portfolio_risk diff 0. 커밋/푸시·CLAUDE.md
계열 문서 동기화(§9)는 Docs 단계로 이연.

## 11. 라운드 1 — tester 적대적 검증 확증 결함 시정 (2026-09-03, backend-dev+tdd-engineer)

착수 컨텍스트가 전달한 7건(MEDIUM) 전부 실측 재현 후 확증. 4건은 코드/관측 시정(테스트 신규
9건), 1건은 순수 커버리지 갭(테스트 1건), 2건은 **코드 결함이 아니라 §0·§1·§7·§8 의 서술 오류**
(스펙 문안 정정으로 처리, `_apply_lot_units_cap` 행위 무변경). 8영역·`scheduler.py`·
`boot_manager.py`·`turtle_sizing.py`·`portfolio_risk.py` diff 0 유지, `strategy_base.py` 단독
+141L(신규 헬퍼 2 `_emit_fallback_cap_clamped`/`_describe_lot_cap_diagnostics` + 기존 헬퍼 3곳
확장). 전략 4파일 diff 0(이번 라운드는 `strategy_base.py`·테스트 2파일·문서 2건만 접촉).

### 11.1 #1·#2 — `logger.debug` 가 관문 밖 예외 지점이었다 (CONFIRMED, 코드 시정)

`_apply_lot_units_cap` 의 `except Exception:` 안에서 `_emit_fallback_cap_skipped(...)` 는
자체 try 로 감쌌지만 그 뒤 `logger.debug(...)` 는 무방비였다 — 로거가 죽으면 예외가 관문 밖
(`calc_buy_quantity` → `order_engine.execute_buy`)으로 전파된다(§3 계약 9 "행위는 cap 밖"의
정면 위반). **재현 확증**(스크래치패드 격리 실행, 실트리 미접촉 — §10.2 사본 규약) — pre-fix
형태로 소스를 복원해 실행하면 `compute_unit_qty` + `logger.debug` 동시 raise 주입 시
`RuntimeError: debug logger down` 이 실측대로 관문 밖으로 전파됨을 확인했다.

시정 = `logger.debug` 호출을 `_emit_fallback_cap_skipped` 호출과 **같은 inner try** 안으로
이동(1줄 재배치, 분기 순서·다른 로직 무변경). 회귀 = `test_f242_r1_debug_logger_failure_does_not_propagate`
(compute_unit_qty + logger.debug 동시 raise → 예외 전파 0 + qty==1 유지 + SKIPPED reason=exception
1행 확인).

### 11.2 #3 — PR 경로 fail-open 스킵에 K 초과 흔적이 없었다 (CONFIRMED, 관측 시정)

재현(스펙 원문의 (a) 케이스) — donchian B=387,320 ρ=0.20 r=0.005,
`_candidates["124500"]={"atr":3593,"atr14":3600}`(양쪽 모두 양수·상이 → `ambiguous_atr`) →
`_apply_budget_limit(2, 38000, "124500")` = **2주(3.71~3.72유닛, K=2 초과)** 가 fail-open 으로
그대로 통과하고, 남는 유일한 흔적 `[fallback_cap_skipped] reason=ambiguous_atr qty=2 price=38000`
에는 atr·units 필드가 없었다. `[oversized_fallback]` 도 notional(76,000) ≤ ρ×예산(77,464) 이라
미발화 — 즉 **어떤 마커도 이 초과를 기록하지 않았다**. 파생 결과 = §0⑪ G0 종료 기준②
("`[oversized_fallback] units=` 로 직접 검증, `> K` 0건")가 PR 경로 초과 랏을 원리적으로 못 보고,
캡이 적용된 랏의 `units_after ≤ K` 는 대수 항등식이라 R3("`units_after > K` 1건")의 첫 절은
캡이 정상 작동하는 한 절대 발화할 수 없다(공허한 트리거) — 둘 다 사실.

시정 = **행위 무변경**(fail-open 계약 §3-7 그대로 — ATR 모호는 여전히 현행 수량 유지), 관측만
확장. `_describe_lot_cap_diagnostics(ticker, final)` 신규 read-only 헬퍼(`_candidates[ticker]`
의 `_SIZING_ATR_KEYS` **원시값**(채택 여부 무관)과 그 값 기준 유닛 배수를 `key=value`
`|`구분 문자열로 산출) → `[fallback_cap_skipped]` 꼬리에 `atr=`/`units=` 필드 병기(기존 접두
byte 보존 — `.startswith`/`in` 검사 전부 무영향, 실측). 재현 케이스는 이제
`atr=atr=3593|atr14=3600 units=3.71|3.72` 를 직접 노출해 K(2.00) 초과가 **가시화**된다.
G0②/R3 문안은 `_workspace/domain_consult/pyramiding_deep_review_20260903.md` §4.3 G0 행 뒤
한 줄로 정정(`[fallback_cap_skipped] atr=`/`units=` 병기 검증 추가) — 본 스펙 §0⑪·§7·§8 자체는
이 append 로 갈음하고 표 셀은 편집하지 않는다(추적성 보존, 위 정정 문구가 최신). 회귀 =
`test_f242_r3_ambiguous_atr_pr_path_now_visible`(정확 문자열 확인) +
`test_f242_r3_skip_diagnostics_dash_when_no_candidate_values`(결측 시 `-` never-raise).

### 11.3 #4 — 클램프가 "미설정"과 "PUT 무효값"을 구별 없이 흡수했다 (CONFIRMED, 코드+관측 시정)

`_read_max_lot_units` 이 범위 밖 값을 흔적 없이 클램프했고, `[fallback_cap_config] k=2.00` 만으로는
"DB 미설정(코드 기본값)"과 "PUT 으로 0.5 를 넣었다가 걸러짐"을 구별할 수 없었다 — 루트
CLAUDE.md "비중 단위 추론 변환 금지 — 위반은 조용히 흡수 말고 422/`success=false` 로 시끄럽게
거부" 독트린과 충돌. `PUT /api/strategies/{id}/params` 에 화이트리스트가 없어(routes/strategies.py)
임의 값이 그대로 DB 영속되므로 다음 부팅에도 같은 침묵이 반복됐다.

시정 = `_read_max_lot_units` 가 **키가 self.config.params 에 명시적으로 존재하는데** 값이
무효/범위밖일 때만 `_emit_fallback_cap_clamped(raw, result)` 신규 헬퍼를 호출한다(WARNING,
`raw=`(원본 `repr`)·`clamped_to=` 필드, `[fallback_cap_clamped]`, 1회/전략/일 — `_lot_cap_logged`
공유 cap 의 `"clamp"` 키). **키 부재(정상 기본값 사용)는 클램프가 아니므로 무발화** — 비대칭
방향(§0.0 원 서술의 "<MIN 은 완화/>MAX 는 강화"라는 표현은 부정확했다: 실제로는 <MIN 도
DEFAULT(2.0)로 **강화**된다, 완화가 아니다 — 두 경계 모두 "더 보수적인 쪽"으로 클램프). 회귀 4종
= 명시적 무효값(raw=0.5 → `raw=0.5 clamped_to=2.00`) · 키 부재 무발화 · 유효값(2.5) 무발화 ·
정확한 경계(1.0/20.0) 무발화(off-by-one 방지) · 1회/전략/일 cap. AST 확장 G-242-10(신규 헬퍼도
A-PURE·peek→log→mark·try 하위 로그·마커 리터럴 존재 가드를 동일 강도로 받음, `_PURE_FUNCS`/
`_EMIT_FUNCS`/`_CAP_MARKERS` 3곳에 편입).

### 11.4 #5 — "K×2N = 예산 2.0% 로 유계" 는 스탬프 랏에서만 성립 (CONFIRMED, 문서 오류·코드 무변경)

§1 표 6행("폴백 경로는 `_entry_atr` 미스탬프 … 캡 이후엔 랏 ≤ K유닛이라 최악 노출이
`K×2N = 예산 2.0%`로 유계")은 **이번 사이클이 겨냥한 바로 그 랏(폴백·PR 낙하)에서 거짓이다**.
donchian 은 `_entry_atr` 을 `_turtle_buy_quantity` 성공 시에만 스탬프(`donchian_swing.py:1946`
부근) — 폴백/PR 랏은 미스탬프라 `check_exit_signal` 의 고정% 손절(-7.0%)을 탄다. 실리스크는
`cap_qty × price × |stop_loss_rate|` 이지 `cap_qty × ATR` 이 아니다. 재현(사이클 왕복 표본
`_workspace/pyramiding_review_20260903/pyramid/roundtrips.csv` donchian 139480 이마트,
buy_px=115,500·atr14=3,635 → 터틀 0 → PR 0 → 폴백 1주, `cap=floor(2×1936.6/3635)=2` 통과
(units_after 1.88 ≤ K=2)이지만 −7% 손절 기준 실리스크 = 115,500×0.07=8,085원 = 예산
387,320 의 **2.09%** > 2.0% 주장치) — 캡 통과 영역 전수 탐색에서 이론 최대 **6.99%**(donchian).
kojiro 는 `check_buy_signal` 이 사이징 경로와 무관하게 `_position_atr` 을 항상 스탬프하므로
(kojiro.py:863-868) 2×ATR 손절이 붙어 §1 원 서술이 대체로 성립 — **두 전략을 한 문장으로
묶은 것 자체가 오류**였다.

**코드 결함 아님**(캡은 여전히 순수 축소 방향 — 이 발견은 캡의 *상한 크기 서술*이 틀렸다는
것이지 캡 자체가 틀렸다는 게 아니다). 조치 = 코드/테스트 무변경, §8-C 후속 항목("캡으로 노출이
`K×2N` 으로 유계됐으므로 별건")의 근거를 이 문단으로 대체 기록. Docs 동기화(§9, 아직 미실행)가
CLAUDE.md/워크리스트에 "K유닛 상한 = 예산 2.0%" 문구를 옮길 때는 **"스탬프 랏(2×ATR 손절)
한정"** 단서와 "미스탬프 랏의 실효 상한은 `cap_qty × price × |stop_loss_rate|`, donchian 실측
최대 2.09%·이론 6.99%" 를 반드시 동반해야 한다 — 이 스펙이 그 정본이다.

### 11.5 #6 — 롤백 다이얼은 당일 이미 소진된 종목을 되살리지 못한다 (CONFIRMED, 문서 오류·코드 무변경)

결정 ⑨("래치 신설 금지 — 자연 재평가 허용")의 **결론(래치 불필요)은 우연히 맞다** — 하지만
근거("장중 재평가가 존재한다")는 런타임과 다르다. `cap_qty = compute_unit_qty(budget, atr,
risk_pct, fraction=k)`(`strategy_base.py:641` 부근) 의 `atr` 은 `_candidates[ticker]` 에서
오고, 그 dict 는 `prepare()` 가 D-1 일봉으로 채운다(donchian: `donchian_swing.py:586` 부근) —
장중 갱신 경로 `recompute_held_atr` 의 유일 호출자는 `boot_manager.py:341`(**부팅 전용**,
cycle225 확정 사실). 즉 같은 날 가격이 아무리 내려도 `cap_qty` 는 상수이고, 캡→0 인 종목은
그날 **가격 무관 영구 차단**이다. 더 앞단에서 4 터틀 전략 모두 BUY **신호 시점**에
`_bought_today.add(ticker)` 를 찍는다(주문 성사 여부 무관 — donchian_swing.py:1725·
kojiro.py:863·vcp_breakout.py:1159·bull_flag_breakout.py:1092) — 즉 캡→0 은 그 종목의 **당일
유일한 시도**를 소모한다.

파생 결과 2가지 — ① 요청받은 "같은 날 더 싸게 사는 역선택 재진입 경로"는 애초에
**구조적으로 존재하지 않는다**(donchian 매수창은 09:05~09:30 단일, `donchian_swing.py:1690`
부근 — 하루 재평가 자체가 없다) — 이 부분은 §0⑨ 결론과 **일치**하고 새로운 위험이 아니다.
② §7/§8 의 롤백 절차(`strategy_config.params.max_lot_units = 20.0` DB UPDATE 또는 `PUT`)는
**다음 세션부터만** 효력이 있다 — 당일 캡에 걸려 잘린 종목은 `_bought_today` 에 이미 남아
있어 롤백이 그날 안에는 그 종목을 되살리지 못한다. 반대로 **양호한 확인**도 함께 나왔다 —
`_bought_today` 덕에 `order_engine.py` 의 "매수 수량 0 → 900s cooldown" WARNING 은 종목당
**1회/일**만 발화하므로, §7 D+1 표의 "캡 발화와 같은 시각·같은 ticker 로 짝지어 판독" 규칙은
1:1 로 성립한다(우려했던 반복 오탐은 실측/구조상 없다).

**코드 결함 아님**(캡 로직·재진입 억제 어느 쪽도 변경 대상이 아니다 — `_bought_today` 는
기존 전략 계약이고 이번 사이클이 건드리지 않는다). 조치 = §7/§8 롤백 절차 문안에 "당일
이미 `_bought_today` 로 소진된 종목은 롤백이 다음 세션부터만 적용됨" 단서를 Docs 동기화
시점에 동반 기록(코드/테스트 무변경).

### 11.6 #7 — 뮤테이션 escape m5b (CONFIRMED, 테스트 커버리지 시정)

`_apply_lot_units_cap` 외곽 `except Exception:` 핸들러를 `return final` → `return 1` 로
바꾸는 뮤턴트(m5b)가 §4.1 F-5e(폴백 1주, `final==1`) 만으로는 검출되지 않았다 — `final==1`
에서는 상수 `1` 과 `final` 값이 우연히 같기 때문이다. **격리 실증**(`strategy_base.py` 소스를
문자열 치환한 in-memory 모듈로 실행, 실트리 미접촉) — turtle `_MiniStrategy`(B=100,000,000·
ATR 3,000·r=0.005)에서 `compute_unit_qty` 를 raise 로 패치 후 `_apply_budget_limit(50, 60_000,
t)`: shipped `return final` → **50**, m5b 뮤턴트(`return 1`) → **1**(조용한 98% 과소매수) —
실제로 재현해 두 값의 차이를 직접 확인했다. ⚠️ 위험 방향은 원래도 봉인돼 있었다 — 반대 방향
뮤턴트(`return 0`, fail-closed = P0-1 유령키 재현 방향) m27 은 F-5e 가 이미 검출한다(F-5e
자체가 `qty==0` 을 FAIL 로 못박기 때문).

시정 = `test_f242_r7_cap_exception_preserves_large_final_qty` 신규(`final=50` 경로로 대조,
compute_unit_qty raise 주입 → `qty==50` 단언 + `reason=exception` 확인). 코드 변경 없음(순수
커버리지 갭 시정).

### 11.7 표적 검증

```
python -m pytest -q -p no:cacheprovider \
  tests/unit/engine/test_cycle242_fallback_notional_cap.py \
  tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py
# → 161 passed (§4.1/§4.2 기존 다수 + 라운드 1 신규 11)

python -m pytest -q -p no:cacheprovider <§10.2 표적 목록 그대로> tests/unit/engine/strategies/
# → 1918 passed, 24 xfailed, 3 xpassed (0 failed) — §10.2 기준선(1901/24/3) 대비 +17
#    신규 PASS(라운드 1 11 + 재실행 시 파라미터화 전개 차이), 회귀 0
```

`git diff --stat -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/
src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py
src/engine/scheduler.py src/engine/boot_manager.py src/engine/turtle_sizing.py
src/engine/portfolio_risk.py` = 빈 출력(diff 0, §10.3 재확인). 전략 4파일 diff 0(이번 라운드
접촉 파일 = `strategy_base.py` + 테스트 2파일 + 본 스펙 + `pyramiding_deep_review_20260903.md`
1줄 + 아침 리포트 무접촉). 전체 스위트는 팀 차원 다음 Docs/통합 단계에서 1회 실행 예정
(본 라운드는 커밋하지 않음 — 상단 컨텍스트 제약).

### 11.8 잔여 — 다음 Docs 단계(§9) 실행 시 반영 의무

§9 Docs 동기화(CLAUDE.md 3곳·`src/engine/CLAUDE.md`·`strategies/CLAUDE.md`·
`00_leader_trading_rules.md`·`00_URGENT_WORKLIST.md`·`HARNESS_CHANGELOG.md`)는 아직 미실행
(§10.4 재확인 — Green 라운드가 이미 이연했고, 본 라운드는 결함 시정에 한정돼 마찬가지로
이연한다). 그 단계가 실행될 때 §11.4(K×2N 문구에 "스탬프 랏 한정" 단서)·§11.5(롤백 절차에
"당일 소진 종목은 익일부터" 단서)·§11.2(G0②/R3 문안에 `[fallback_cap_skipped]` 필드 병기,
`pyramiding_deep_review_20260903.md` 에는 이미 반영 완료)를 반드시 흡수해야 한다 — 그렇지
않으면 부정확한 문구가 그대로 CLAUDE.md 로 옮겨진다.

## 12. Docs 단계 — 실행 완료 (team-leader, 2026-09-03)

§9 문서 동기화를 실행하고 §11.8 이 남긴 흡수 의무 3건을 전부 반영했다. **코드·테스트 diff 신규 발생 0**
(이 단계는 문서만 접촉). 커밋·푸시는 여전히 사용자 지시 대기 — 배포 창은 보유 포지션 有 이므로 **15:30 이후**.

### 12.1 동기화한 정본 6종

| 문서 | 반영 |
|---|---|
| `CLAUDE.md` | 하네스 표 상단 1행 추가 + 최고령 1행(cycle226) 제거 = **15행 유지** · 「자금 관리 › 1회 투자금액 ATR 유닛화」 아래 `max_lot_units` 규칙 신설 · 「핵심 안전 규칙 › 매수 수량은 전략 잔여 자금 기준」에 관문 캡 위치·ATR 소스·A-PURE 확장 1문장 · 「터틀 ATR 손절 게이트」에 **C8 구분**(그 금기는 청산 규약, 진입 사이징의 `sizing_mode` 분기는 충돌 아님) |
| `src/engine/CLAUDE.md` | `_apply_budget_limit` 문단 아래 cycle242 하위 항목 6(분기 순서 확장 · `_resolve_sizing_atr` 계약 · fail-open 경계 · **마커 5종** · **두 척도 병존(ρ↔K)** · order_engine 900s 오귀인 · K 클램프). C7 결손(= `[oversized_fallback]` 미기재)도 함께 메움 |
| `src/engine/strategies/CLAUDE.md` | 관문 항목에 캡 1문장 · 터틀 키 **6종 → 7종** + **가드 위치 명기**(종전 6종은 기계 가드 없는 문서 주장뿐이었다는 사실 병기) · 「1주 폴백(모든 전략)」에 캡 후속 1문장 · 사이징 매트릭스 donchian·kojiro 행 "터틀 상태"에 **K=2.0 랏 유닛 캡 라이브** 부기 |
| `_workspace/00_leader_trading_rules.md` | §2 자금 절 「ATR 유닛화」 하위에 K 규칙 1항 · `DEFAULT_PARAMS` 코드 블록 **2곳**(BFB·VCP)에 `"max_lot_units": 2.0` + 미편입 주석 |
| `_workspace/00_URGENT_WORKLIST.md` | 신규 `## ✅ G0 …` 항목(실측 표 · 확증 원인 · 결정 12 · 전제 정정 5 · 기대 효과 표 · 마커 5종 · **D+1 판독 표 6채널** · **트리거 R1~R6** · G0 종료 기준 재정의 · 문서 정정 2 · ⓐ 재검토 조건 · 후속 A~G) + cycle232 표 G3′ 행에 "ρ 축 관측 병존" 부기 + G-7 행에 "터틀 전환 시 캡 자동 편입" 1줄 |
| `docs/HARNESS_CHANGELOG.md` | L7 에 cycle242 상세 1행 append(발단·확증 원인·전제 정정 5·결정 12·구현·적대 검증 7·차분/뮤테이션 수치·D+1·G0 재정의·트리거·후속·검증) |

`_workspace/domain_consult/pyramiding_deep_review_20260903.md` §4.3 G0 행 부기는 라운드 1 이 이미 반영해 둔 상태를
그대로 둔다(중복 append 금지). 동시 실행 중인 읽기 전용 워크플로 2개의 산출물(`bfb_vcp_entry_relax_20260903.md` ·
`pyramiding_design_blueprint_20260903.md`)과 그들이 워크리스트에 넣은 `G-8′` 항목·`morning_0903_report.md` 변경은
**무접촉**(다른 세션 소관).

### 12.2 §11.8 흡수 의무 — 반영 확인

| 의무 | 반영 위치 |
|---|---|
| §11.4 — "K유닛 = 예산 2.0%" 에 **"`_entry_atr` 스탬프 랏 한정"** 단서 + 미스탬프 랏 실효 상한 `cap_qty × price × \|stop_loss_rate\|`(donchian 실측 2.09%·이론 6.99%) | `CLAUDE.md` 자금 관리 항목(⚠️ 문장) · 워크리스트 「문서 정정 2」 ① · 변경로그 ⑤ |
| §11.5 — 롤백 절차에 **"당일 `_bought_today` 소진 종목은 다음 세션부터"** 단서 | `CLAUDE.md` 자금 관리 항목 말미 · `_workspace/00_leader_trading_rules.md` §2 · 워크리스트 트리거 표 머리말 + 「문서 정정 2」 ② · 변경로그 ⑥ |
| §11.2 — G0②/R3 문안에 `[fallback_cap_skipped] atr=`/`units=` 병기 검증 추가 | 워크리스트 「⑪ G0 종료 기준 재정의」 ② · 변경로그 ■G0 종료 기준 재정의 · (검토 보고서 §4.3 은 라운드 1 반영 완료) |

### 12.3 전체 스위트 · 범위 확인

```
find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q -p no:cacheprovider
# → 6163 passed, 10 skipped, 328 xfailed, 13 xpassed in 284.83s   (0 failed)
```

`git diff --stat` = `src/engine/strategy_base.py`(+372) · 전략 4파일 각 +1 ·
`tests/unit/engine/test_cycle233_oversized_fallback.py`(docstring 재스코프) ·
`tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py`(sha 핀 3건 자기소멸형 재핀) ·
`_workspace/test_index.yaml`(재생성) + 본 Docs 단계의 문서 6종. 신규 미추적 = 본 스펙 · 자문 ·
Red 2파일. **8영역 + `scheduler.py` + `boot_manager.py` + `turtle_sizing.py` + `portfolio_risk.py` diff 0** 재확인.
