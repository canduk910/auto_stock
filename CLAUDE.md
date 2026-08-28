# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + AWS RDS PostgreSQL(DB). 다중 전략 아키텍처.

---

## 🔴 최우선 과제 — 먼저 읽을 것

**[`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md)** 가 현재 최우선 작업 지시서다.
다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.

**P0 요약 (2026-08-25 확정, 실측 검증 완료)** — `bull_flag_breakout` 과 `vcp_breakout` 의
매수 최종 관문이 `scanner.ticker_prices["acml_vol"]` 을 읽는데 그 키의 대입부가 전체 소스에
없었다(`risk.py` 는 4키만 기록). `acml_vol ≡ 0 < vol_threshold` 항상 참 ⇒ `check_buy_signal`
이 **구조적으로 `Signal.BUY` 반환 불가** ⇒ 두 전략만 전 기간 체결 0건(비중 합 25%).
기존 귀인 "진입 조건 미통과 탓"은 반증됐다(2026-08-25 하루만 21회 이상 충족).

**✅ P0-1 종결 (사이클 227 배관 → 사이클 228 게이트 전환, 2026-08-28)**: 사이클 227 이
배관(handler `fields[13]` → `on_tick(*, acml_vol=)` → `tick_volume`)+관측을 배포했고, 이틀
실측 would_pass **0/5**(관측/임계 8%→70% 시각순 상승 = 게이트가 잰 것은 거래량이 아니라
시계)로 래치 선행이 확정돼 사이클 228 이 게이트를 **tick_volume 실측 + 충족 래치 + 추격
상한(BFB 5.0/VCP 7.5)** 으로 전환했다 — **매수 개방**(비중 현행 BFB 0.15/VCP 0.10, 자문
실측 체결률 ≈0.5건/일·만기 위험 순자산 1.45%). 관측 마커 `[*_vol_gate_observe]` 은퇴
(would_pass 의미 반전 — 08-28 전후 로그 합산 금지). 228-B = `_effective_setup` 구조 레벨
stamp 우선 복원(첫 체결이 밟을 청산 경로의 P1 계약 위반 선제 시정). 상세 =
`src/engine/strategies/CLAUDE.md` 배너 + `_workspace/00_URGENT_WORKLIST.md`.

---

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력 (verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
> 시스템 흐름 도식: [`docs/architecture.md`](docs/architecture.md)

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다. *매매 의사결정의 깊이* 는 도메인 전문가의 사전 자문으로 보완하고, *코드 품질 드리프트* 는 리팩토링 전문가의 주기적 검토로 흡수한다.

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})` 로 라우팅한다. team-leader 가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 매매 의사결정 자문 (신규 전략·파라미터·보드 행태·시장 레짐·KIS 거부 해석) → `domain-consult` 스킬 (`domain-expert` 에이전트) — Phase 2.5 명세 분해 *전* 또는 사이클 중 행위 영향 평가 시
- 주기적 리팩토링 검토 (사이클 5회 누적 또는 명시 요청) → `refactor-review` 스킬 (`refactor-expert` 에이전트) — Phase 4.5
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`
- KIS API 정본 스펙 (TR_ID·응답 구조·거부 코드) → `kis-mcp-query` 스킬 (backend-dev / tdd-engineer / tester / refactor-expert 공유)

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 구현 계획·검수·리팩토링 검토 | **fable** | `team-leader`, `tester`, `refactor-expert` |
| 테스트 설계·도메인 자문 | **opus** | `domain-expert`, `tdd-engineer` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 하네스 변경 이력 (요약)

이 표는 **최근 ~15개 사이클의 한 줄 요약만** 유지한다. 각 행은 반드시 한 줄 — verbatim 금지. 신규 사이클 완료 시: (1) 이 표 상단에 한 줄 요약 1행 추가 + 가장 오래된 1행 제거(15행 유지), (2) 사용자 보고 verbatim·회귀 가드·영속 의무·검증 수치 등 상세는 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 에만 append.

| 날짜 | 사이클 | 한 줄 요약 |
|------|--------|-----------|
| 2026-08-29 | kojiro `_held_stage3` 날짜 키 무효화 (cycle231, P2-5 종결) | 발단 = §3 스테이지3 청산(`kojiro.py` — 시스템 유일의 **가격 무관** 청산)이 인메모리 bool 을 날짜 무관 소비 — 프로세스가 며칠 상주하므로 어제 True 가 살아남아 매도 거부 등으로 생존한 포지션을 오늘 아침 가격 무관 청산. domain-consult(`cycle231_kojiro_stage3_stale.md`) **전제 정정 2** = cycle225 게이트는 donchian 것(kojiro recompute 는 보유 전수 순회 — 실스테일 경로는 recompute *이후* 도는 07:59 재-prepare(`scheduler:743`, kojiro strict entry 특성상 후보 빈 날 흔함)+16:20 evening prepare) · prepare held 마킹이 ATR 밴드 게이트 **뒤**라 밴드 상한(>6%) 이탈 = **급등 종목**이 마킹을 못 받음(저승률·고RR 전략의 오른쪽 꼬리를 배관 실패로 자르는 경로). 판정 = 억제(`:649` fail-open 계약을 한 파일 안 두 답에서 통일 — 신설 정책 아님, §1·§2·§4 방어 + §3 는 원래 익일 아침 발화라 하루 지연 내장) + **날짜 키** `(판정 수행일, bool)`(판정 수행일 — 봉 날짜면 연휴 무효화 불가. "매일 prepare 1회" 는 코드로 강제 안 되는 불변식이라 리셋 방식 기각). Red 추가 실증 = 현행 소비처 `if dict.get(t):` 가 **비어 있지 않은 튜플을 전부 참**으로 읽음(`(오늘, False)` 도 발화 — 순진한 마이그레이션의 함정을 테스트가 봉인). 구현 = 기록 6곳 튜플 전환 + 소비처 `오늘 ∧ True` 만 발화(`judged_on` 필드 동반, 억제 시 값 보존) + `[kojiro_stage3_stale_skip]` age 1=INFO/≥2=WARNING cap 1회/ticker/일(날짜 키 자기 리셋) + 부수 방어 `:685` buy_date isinstance 가드(cycle226 L-2 동형 — try 밖 예외가 뒤 보유 종목 ATR/stage3/floor 재계산 통째 유실, 잠복). 의미 전환 4곳(주입 → 튜플 = "오늘 판정이면 발화" 계약 문서화). 자문 한계 명시 = 하루 늦은 청산 실비용은 kojiro 저승률·고RR 라 유리한 교환(**고승률·저RR 전략 복사 금지**) + `[kojiro_stage3_exit]` ~20건 시 §3 존재 가치 재검정. FREEZE 무접촉(진입·파라미터 0)·8영역 diff 0·kojiro.py 단독. 신규 회귀 28, 백엔드 **5,755 PASS** |
| 2026-08-29 | H0UNMKO0(VI) 메인 퇴출·보조 직접 델타 + 메인 점유 계측 (cycle230 — cycle221 잔류 채택) | P3-10 처분 — 08-20 작성 후 워킹트리에 9일 잔류하던 cycle221 을 재평가해 **채택**(사용자 결정). 동기 = 08-19 실사고: 메인 45/41 **KIS 서버 한도** 초과(OPSP0008 117건 중 시세 7건 = 매수 직후 보유 4종목 ~58분 tick blind = 손절 사각), VI 채널이 메인 41 의 ~25% 선점 + **해제 0곳 슬롯 누수** + `bypass_limit=True` 는 로컬 가드만 우회(서버 한도 못 넘음 — cycle214 의 HIGH 승격은 tick 규칙의 오적용, H0UNMKO0 는 매매 게이트 미연계 **관찰** 채널). 시정 = VI 를 메인에 한 건도 안 붙이고 보조 세션 **직접**(풀 API 미경유 — `_ticker_to_session` 이 tr_key 단일 키라 풀 경유 시 TICK 라우팅 오염) **델타**(신규만 SEND/이탈만 해제, `_market_op_subs` 추적 맵 + `_reset_daily_state` 동행 clear) 배치, 대상은 보유+익일청산뿐(후보 VI 는 삭제 — 기존에도 dedup 에 막힌 실질 noop, 되살리면 tick 후보 슬롯 48~60 잠식) + **main_over 상시 계측**(`[market_op_subscribe_summary]` 5분 무조건 + 초과 시 WARNING — 45/41 이 priority_drop 침묵에 묻혔던 관측 공백 봉합) + 보조 만석 시 `[market_op_subscribe_no_slot]` WARNING(관찰 결손 은닉 금지, 메인 폴백 명시 금지 = tick > VI 명시적 교환). **처분 판단 근거** = "슬롯 부족" 전제 반증(08-25)은 *BFB 미구독의 원인* 주장만 반증했고(실원인 P0-2 축출) 08-19 사고 자체는 유효 · 적대적 리뷰 "주 목적 미달성"(LOW tick 이 메인 되채움)은 불완전 지적이지 유해 지적이 아님(누수 차단·계측·퇴출은 독립적으로 옳음) · **압력 재증가 추세**(8/28 구독 144 = 8/25 111 대비 +30%, P0-2 축출 소멸 + cycle228 매수 개방으로 보유 회전 증가 — VI 누수는 회전이 빠를수록 빨리 쌓임). 잔여 후속 = 메인 헤드룸 관리(LOW tick fallback 상한) 워크리스트 등재. 표적 44 PASS, 전체 5,727 PASS 기검증 | 
| 2026-08-28 | VB·momentum 매수 컷 15:20 + [단일가매매] 분류기 편입 (cycle229, P1-5 종결) | 발단 = 매일 15:30:0x~2x `[callback_exception]`→WS 재연결 1~4회(8/20~27 실측 9건). domain-consult(`cycle229_vb_1530_single_price.md`)가 **착수 명세의 전제를 정정** — 15:20~15:30 은 연속매매가 아니라 KRX **장후 동시호가**(`session.py::is_call_auction_now` 가 이미 그렇게 판정, 6/17 fresh=0/10 실측)이고, 15:30 몰림은 **랜덤엔드 확정 종가 1틱**이 15:19 마지막 연속체결가 대비 점프해 허위 edge-crossing 을 만들기 때문. ⚠️ 종가 단일가는 **시장가 호가를 접수**한다(15:20 강제청산 시장가 매도 작동이 방증) — 15:2x VB 매수는 거부가 아니라 **종가 체결→오버나잇**(우연한 안전판 없음, 컷 근거 강화). 시정 = ① VB·momentum `BUY_CUTOFF_KST=15:20` **모듈 상수**(DB override 불가 — OVERNIGHT 금지는 토글로 뚫리면 안 됨, 전략별 자기 소유, PARAM_RANGES 미편입), `check_buy_signal` **최상단·상태 무갱신**(뒤에 두면 종가가 `_prev_price` baseline 이 돼 재시작 거짓 미돌파), **KST 명시**(naive = P2-6 등재 결함, 선례는 kojiro), `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일 관측(사이클 224 교훈). momentum 동일 컷 근거 = 종가 확정 틱 +29% 는 "상한가 잠금 실패 마감" 표본(+30% 제외라 원 가설의 정확한 반대, 표본 0 영역) ② `[단일가매매]` 연속 부분문자열 `_MARKET_ORDER_DISALLOWED_KEYWORDS` 편입 — 기존 "지정가 및 최유리"가 중간 삽입어로 불성립하던 변형. **주 실익 = 매도**(미분류 매도 거부는 3회 재시도 후 무기록 포기·TTL 미등록이라 랜덤엔드 창 청산 실패가 기록조차 안 됐다 — step_down 지정가 폴백은 단일가 세션 유효 주문 = 정확한 처방). 잔여 매수 경로는 LTV 야간뿐이라 폴백 수용. 8영역 diff 0(변경 = volatility_breakout·momentum·balance.py). 부수 = **무-freeze 레거시 테스트 6곳이 벽시계 의존**임이 표면화(16:13 실행에서 실측 — naive freeze "10:00"=UTC 는 KST 19:00) → 장중 KST 동결 적응(행위 불변·스위트 시간 독립 확보). 신규 회귀 50(5파일), 백엔드 **5,727 PASS**. D+1 확인 = 15:30 대 callback_exception **0건이 정상**(의미 반전 — 08-28 전후 합산 금지) + `[selling_reconcile]` 감시. cycle228 과 15:40+ 동반 배포(별도 커밋 — 관찰 축 분리: 시각축 15:30 vs 전략축 BFB/VCP) |
| 2026-08-28 | BFB·VCP 거래량 게이트 tick_volume 전환 + 충족 래치 + 추격 상한 + setup 리졸버 계약 복원 (cycle228-A/B) | P0-1 종결 — Stage 0 이틀 관측 would_pass **0/5**(관측/임계 8%→70% 시각순 상승 = 게이트가 잰 것은 시계)로 "0건 = 래치 선행" 판정 확정. domain-consult(`cycle228_vol_gate_latch.md`) = 래치는 임계를 낮추지 않고 시각 편향만 걷어낸다(무제한 재평가해도 5종목 중 1건만 통과, 그 1건 280360 이 거래량 2.26배 = 정확히 사야 할 종목) · 해제선은 신규 파라미터가 아니라 **전략 자신의 §2 손절선**(001450 실측 −3.53% 왕복 생존, 고정 밴드는 flag 높이 중앙값 15.6% 안에서 무의미) · TTL 불필요(entry_end 가 품질 하한, `latch_age_sec` 기록해 N=10 후 판단) · VCP 동일 적용(순수성 반론은 이론상 옳으나 현행 게이트가 애초에 피벗 거래량을 재고 있지 않음 — RVOL 은 별도 사이클) · retention 무변경(진동↔거래량 품질 역상관 실측: 280360 2회/2.26배 vs 257720 142회/0.60배) · 다크런치 재반대(비중 현행 유지, 체결률 ≈0.5건/일·만기 위험 1.45%). 사용자 결정 4 = 자문안 채택/추격 상한 채택/비중 유지/228-B 동반·별도 커밋. **구현 A** = 게이트 소스 tick_volume 단일(유령 키 4줄 은퇴, no_data=fail-closed WARNING·읽기 예외도 no_data 흡수 = on_tick 보호) + 래치 상태기계(`_vol_latch` 날짜 키 자기 리셋, 무장=완주(BFB)/edge-crossing(VCP), 후퇴 유지, stop_line/level_moved 해제, 재무장은 진짜 재접근 필요) + 추격 상한 리터럴(BFB 5.0/VCP 7.5, PARAM_RANGES 미편입, current_price 단독 — daily_high 금지 AST, 도출 관계 부팅 관찰 `[extension_cap_invariant]` 자동 보정 금지) + 진동 로그 (ticker,전이) 1회/일 cap(한글 문구 byte 보존, 473→~20행/일) + 카운터 6키. **관측 마커 은퇴** — would_pass 의 매매 귀결이 "안 샀다→샀다" 반전이라 `[*_vol_gate_observe]` 유지 시 과거 로그 오독(08-28 전후 합산 금지, 신규 = `[*_vol_gate_pass|reject|no_data]`+`[*_latch_armed|released]`). 은폐 주입 **12곳**(3파일 11 + cycle191 C-7 — Red 목록 밖 1곳 실측 발견) tick_volume 전환, observe 테스트 2파일 은퇴(승계 매핑), AST-2 의미 전환(대체 G-1/G-9), sha 핀 자기소멸분 삭제+재핀(뮤테이션 실증). **구현 B(별도 커밋)** = `_effective_setup` 이 live 통째 우선이라 보유 중 재검출 시 §2 손절선이 새 flag_low/base_low(진입가보다 높을 수 있음)로 갈아타 상승 포지션 조기 손절 — P1 "구조 레벨 불변" 계약을 리졸버가 우회(문서화된 보호가 읽히지 않던 결함, 첫 체결이 처음 밟을 경로) → 구조 키(BFB flag_low/flag_high/pole_* / VCP base_low)는 stamp 우선·지표(atr14/ema50)는 live 우선 병합 + stamp 0 결손 시 live 로 메우지 않음(§2 미발화 계약) + `[setup_structure_conflict]` 1회/(ticker)/일(A 와 같은 날 배포 — D+1 귀인 분리). **프로세스 특이** = 백그라운드 에이전트 3연속 소멸(머신 슬립 "computer went to sleep" 실증) → team-leader 직접 구현 전환, 죽은 에이전트의 부분 편집(BFB check_buy_signal 재구성·테스트 보정)을 감사 후 승계 — 잔여 결함 1건(`_extension_cap_invariant_checked` 미초기화 참조 AttributeError)은 기존 funnel 테스트가 검출해 직접 호출로 시정. 신규 회귀 228-A 82 + 228-B 16, 기존 적응 4(stamp 가드 소스 이동·C-7 주입 전환), 백엔드 **5,677 PASS**. 라이브 실효 임계 주의 = DB `breakout_volume_mult` BFB 1.0/VCP 1.2(코드 2.0/1.5 아님) · retention 1분 · 실효 난이도 BFB 1.43/VCP 1.44. D+1 관찰 = 첫 체결 시 진입 임계 재튜닝 금지(N=10 표본 보호) + 청산 경로 첫 실가동(BFB flag_low·measured-move·시간청산 / VCP base_low·ema50·트레일링) + `latch_age_sec` 분포 + `[setup_structure_conflict]` 빈도 |
| 2026-08-25 | BFB·VCP acml_vol Stage 0 배관·관측 + universe 가드 안전조건 시정 (cycle227) | P0-1(유령 키 `ticker_prices["acml_vol"]` — 대입부 0 으로 두 전략 전 기간 체결 0) 착수. domain-consult(`bfb_vcp_acml_vol_gate.md`) 3판정 = **방향 B(전일 확정치) 폐기**(플래그/베이스는 수축 구간이라 전일 거래량 기준 통과 확률 수학적 ~0 = 결함 재생산) · **A-raw 채택하되 게이트 전환 시 P1-3 충족 래치 동반 필수**(게이트가 돌파 순간 1회만 평가 = 누적이 가장 불리한 시점 심사 후 재무장 불가 → 래치 없이 켜면 BFB 통과율 0% 역선택) · **다크런치 반대**(비중은 Σ 정규화 상대 배분이라 0.01 로 내려도 위험이 kojiro 로 +30% 이전 — 현행 유지가 안전). 사용자 결정 4 = A-raw + 8영역 승인(handler·risk 한정) / **Stage 0 관측 우선**(게이트 행위 변경 0) / 비중 현행(BFB 0.15·VCP 0.10) / P0-2 동반. 구현 = handler `fields[13]`(ACML_VOL, 추가 KIS 호출 0) 파싱 → `on_tick(*, acml_vol=-1)`(cycle222-a day_high 선례) → 신규 leaf `tick_volume.py`(KST 날짜 키 **자기 리셋** — scheduler diff 0 로 cycle221 미커밋 잔류와 커밋 분리, last-write-wins) → BFB/VCP 게이트 **직전** `would_pass` 관측 훅(`[bfb_vol_gate_observe]`/`[vcp_vol_gate_observe]`, cap 1회/(ticker,outcome)/일 + `_scan_stats` 3카운터, **기존 컷 블록 byte 불변** = AST-2 봉인·매수 여전히 차단). **sentinel 0 금지**(0 이 바로 P0 의 그 값 — 미수신 -1/None 타입 분리 + `reason=no_observation` 로그 분리). P0-2 = universe 가드 안전조건(최근 ~30체결 합 `today_volume` → 진짜 당일 누적: tick 관측 우선 → `inquire_acml_vol`(FHKST01010100 — Red 중 KIS 정본 확인으로 FHKST01010300 `acml_vol` 부재 확정, 화이트리스트 diff 0) 폴백 → 둘 다 부재 **보류**), `vol_source=tick\|rest` 병기, 임계·보유/익일청산 보호 불변. 8영역 diff-zero 가드 6건은 정규 절차(내용 sha256 핀, 커밋 시 자기소멸)로 처리 — cycle226 가드는 파일명 면제(영구) 대신 sha 기전 **이식**, 뮤테이션(1줄 변조 → 6 FAIL → 원복)으로 비공허성 실증. 은폐 테스트 3파일 손주입은 Stage 0 유지 + 전환 의무 주석 마커 11곳. tester 적대적 검증 **GO**(차분 실증 4조합 상태 diff ∅·`record_acml_vol` 1.07µs·LOW 4). 신규 회귀 103, 백엔드 **5,617 PASS**. 전환 판정(1~2영업일): 주 3건↑ = 전환 / 0건 = 래치 선행 / 일 10건↑ = 재조사 |
| 2026-08-25 | donchian 돌파선 0 잠복 경로 3중 방어 (cycle226) | 사이클 225 잔여(`_breakout_high[t]==0` 영구 미복구)를 추적하다 **더 위쪽 원인**이 나왔다 — `get_recent_daily_normalized` 의 `_extract_raw` 가 `raw` JSONB 부재 row 를 **row 자체**로 graceful 반환하는데, 그런 row 엔 KIS 원본 키가 없어 `prepare()` 의 `int(c.get("stck_hgpr","0"))` 가 **0** 을 낸다 ⇒ `prior_high=0` ⇒ `prev_close > prior_high` 를 **아무 양수 종가나 통과** = **20일 신고가 돌파를 검증하지 않고 후보 생성** ⇒ `check_buy_signal` 이 무조건 대입해 `_breakout_high[t]=0` ⇒ 시간청산은 `breakout_high>0` 에 막혀 **영구 미발화**, 재도출 게이트는 **멤버십**이라 '무장됨' 으로 오판해 복구 시도조차 안 함. **⚠️ 현재 발화 중 아님(잠복)** — 일봉 writer 가 `"raw": dict(candle)` 를 **항상** 저장하고 `ON CONFLICT ... raw = EXCLUDED.raw` 로 갱신, 라이브 샘플(3종목×30행) 전부 raw 보유 실측. **그래서 매수를 넓히는 시정(`high_price` 도 수용)은 범위 밖으로 명시**하고 **안전 방향 3건**만 닫았다(사용자 취침 중 무승인 구간이라 매매를 넓히는 변경은 사람 결정 사안으로 남김). **D-1** `prior_high<=0` 후보 거부 + `[donchian_zero_breakout_line]` WARNING(매수를 **줄이는** 방향, 탈락 사유 문자열은 정상 미달과 구분). **D-2** 재도출 게이트 값 기준화(**복구 전용** — 매수 미생성). 사이클 225 의 '행위 변경 0' 서술을 값 0 경로 한정으로 갱신하고 `reason=not_called` 주석도 정정 — RED 가 **현행에서 그 사유가 값 0 경로로 실제 도달함**을 실증했다(225 는 '이론상 도달 불가 방어' 로 적어뒀다 = 주석 자체가 결함의 증언). **D-3** `_extract_raw(db_rows, *, ticker=None)` 폴백 가시화 `[daily_raw_missing]`(호출당 1행+1회/ticker/일, 반환값 `is` 동일성 고정, kojiro/VCP/BFB 공유 함수라 폭주 금지). **범위 정정(RED 발견)** = 완전 정규화 row 는 `stck_clpr` 부재로 **기존 `prev_close<=0` 가드가 먼저** 잡으므로 D-1 의 실제 표면은 '종가는 살고 **고가만** 결손' 부분 결손 row 뿐이고, 그 유일 신호가 D-3 다(두 마커 동시=동일 사건 / D-3 단독=타 전략 열화). **적대적 검증 후속 4건** = 스테일 멤버십 서술 3곳(225 K-1 잔재, 잘못된 문서가 AST 가드를 '고쳐야 할 것' 으로 오인시키는 경로) · 게이트의 `int()` 가 **try 밖 예외 지점**을 새로 만들어 던지면 뒤 보유 종목의 `_channel_low`·`_entry_atr`·고점 보정이 통째로 유실(청산 약화 방향) → `isinstance` 정규화 · D-3 cap 등록이 로그 **앞**이라 로그가 던지면 그 종목이 종일 봉인(관측기 자기실패가 관측 대상을 지움) → 로그 뒤로 이동 · CLAUDE.md 정본 동기화. ⚠️ **자기 가드 공허화 재발 방지** — L-2 로 게이트가 지역변수를 경유하자 `If.test` 만 보던 D-2 가드가 거짓 경보를 냈고, 지역 대입을 **전이적**으로 되짚도록 강화했다(한 단계만 보면 `_armed = _bh_raw if ... else 0` 에서 멈춘다). 멤버십 환원 주입 → FAIL, 원복 → PASS 실증. 허용 2파일(`donchian_swing.py`·`stock_master_daily.py`) 단독, 8영역 diff 0, 신규 회귀 35, 백엔드 **5,514 PASS** |
| 2026-08-24 | donchian 복구 경로 침묵 4층 관측화 (cycle225) | 발단 = 장중 재배포(15:58) 직후 cycle224 로그가 `[days_held_observe] ticker=192820 ... breakout_high=0` 을 찍었다 — 09:06 엔 `263000` 이었다. 즉 재시작으로 시간청산 기준선이 소실됐는데 **재도출이 복구하지 못한** 상태다. 규명 결과 **재도출이 실패한 게 아니라 호출조차 되지 않았다** — `recompute_held_atr` 루프의 `if not need_atr and not pos_needs_high_recover: continue` 가 재도출(`:688`)보다 **앞**이고, `192820` 은 매수 당일(`buy_date==today`)이면서 `_candidates` **잔류**라 두 축이 동시에 거짓이었다(실측 `scanned_tickers=['192820']`, 403870 은 둘 다 통과). **라이브 리스크는 없다** — `buy_date==today` ⇒ `days_held=0` 이고 `n_days` 는 라이브 2·기본 5(cycle223 S1 이 PARAM_RANGES 에서 제외)라 게이트가 어차피 닫혀 있다. **진짜 문제는 규명 비용** — 이 경로 전체가 무로그였고 cycle224 의 `breakout_high` 필드가 유일한 흔적이었다. 시정 = 침묵 층마다 사유 로그 신설(1층 `[held_recompute_skip]` · 2·3층 `[...rederive_skip]` · **4층** `reason=no_candles|no_buy_date|no_position`). **적대적 검증이 층수를 정정했다** — 착수 명세는 3층으로 셌는데 **4층**이었다(J-1, HIGH·2렌즈 독립): 게이트를 통과하고도 `candles==[]` 이면 재도출 함수에 진입조차 못 해 A·B 둘 다 침묵하고, **그 경로는 자가치유 논증이 성립하지 않는다**(상위 게이트 통과 = `buy_date<today` ⇒ `days_held` 가 자라는데 `breakout_high>0` 에 막혀 **영구 미발화**). `fetch_daily_candles` 가 빈 `output2` 에 예외 없이 `[]` 를 돌려주고 5분 캐시에 박는다는 실측 동반. 2차 검증이 **한 층 더 깊은 같은 부류**를 냈다(K-1, MEDIUM): 관측기는 무장을 **멤버십**(`ticker in _breakout_high`)으로 보는데 시간청산 게이트와 cycle224 관측기는 **값**(`> 0`)으로 봐서 같은 파일 안에서 축이 갈렸고, `_breakout_high[t]==0` 포지션이 '무장됨'으로 오판돼 흔적 없이 침묵했다 — 도달 경로 실증(`check_buy_signal` 이 `info["donchian_high"]` 를 무조건 대입 + `prepare()` 가 고가 결손 일봉에서 `prior_high=0` 후보 생성). 관측기만 값 기준으로 통일(**재도출 게이트는 무변경** — 그건 행위). 부수 정정 3 = docstring 의 "`recompute_held_atr` 는 60초 폴에서도 돈다" **거짓**(호출부 `scheduler.py:2329` 하나, 유일 호출자 `boot_manager.py:341` = **부팅 전용**) · `no_position` 은 루프 도달 불가가 아니라 **positions dict 레이스로 실제 도달** · A층 note 의 "**반드시** 재무장된다" 단정을 J-1 이 스스로 반증했는데 문구가 미수정이었다. cap 함정도 닫았다 — B 의 cap 키가 `ticker` 단독이라 `insufficient_prior` 가 같은 날 `zero_high` 를 삼켰다(사유별 대응이 백필 vs 데이터품질로 갈리는데 docstring 이 그걸 적어놓고 cap 이 지웠다) → `ticker|reason`. 실패 흔적은 `logger.debug` 단독이면 `_DbLogHandler`(INFO 컷)를 못 넘어 `system_logs` 미도달 = 도입 이전 무음과 구별 불가 → WARNING 1행 병행(3중 try 방어). 뮤테이션 전수 검출(K-1 은 행위 2 + 소스 축 가드 1). **`donchian_swing.py` 단독 +354/-0 순수 추가 = 행위 변경 0**, 8영역 diff 0, 신규 회귀 50, 백엔드 **5,479 PASS** |
| 2026-08-22 | donchian 보유일 상시 관측 (cycle224) | 사이클 223 S3(시간청산 보유일 달력일→**영업일**)를 배포해놓고 **그 변경을 관측할 수단이 없다**는 것을 배포 시점 판단 중 발견. `days_held` 로그 경로가 (a) 폴백 플래그 (b) 시간청산 **실제 발화** 둘뿐이라 *시간 기반 청산인데 발화할 때만 보유일이 보이는* 상태였다. 라이브 실측이 사각을 그대로 드러냈다 — donchian 유일 보유 `403870`(HPSP, 금 08-21 09:05 매수, `breakout_fail_n_days=2`)은 월 08-24 에 `days_held=1`(달력 3)로 게이트 미충족이고 `cache_max == _prev_weekday(today)` 라 폴백도 안 서서 **완전 무음**. 그 무음은 'S3 가 잘 돌았다'·'가격 조건 미충족'·'다른 분기 선발화'를 구분하지 못한다. 시정 = `[days_held_observe]` 신설 — **게이트 충족 여부와 무관하게** 하루 1회, 한 줄에 **영업일·달력일 나란히**(`days_held=1 calendar_days=3` 이 곧 S3 의 직접 확인) + `days_ok`/`price_ok` 분리 표기. **적대적 검증이 목적 무력화 결함 3건 반환** — (F1, MEDIUM) 호출을 §2.5 안에 뒀더니 §1 하드손절이 그날 첫 평가에 발화하면 **도달조차 못 해** 그날 보유일이 영영 기록되지 않았다(donchian 보유가 한 종목뿐인 날엔 관측 목적 통째 소멸, 매도 거부로 포지션 생존 시 **영구 억제**) → `check_exit_signal` **최상단**으로 hoist + 인자를 `(ticker, pos, current_price)` 로만 받아 호출부의 사전 계산 의존 제거 (F2) cap 키 ticker 단독이면 장중 재시작 시 재도출 전 `breakout_high=0` 스냅샷이 **박제**돼 종일 무장 해제로 오독 → `ticker|armed`/`ticker|disarmed` (최대 2행, 무장 행 보장) (F3) `except: pass` 무흔적 흡수는 영구 침묵이 사이클 224 **이전 무음과 구별 불가** → `[days_held_observe_failed]` debug 흔적. **자기 가드 공허성 자체 발견** — F1 을 못박으려 쓴 AST 가드가 `exit_returns` 를 '호출보다 뒤의 return' 으로 정의하고 '호출이 그중 첫째보다 앞이냐'를 물어 **정의상 항상 참**이었다(뮤테이션 전후 모두 통과). 기준선을 호출 위치에서 분리(첫 return 만 제외)해 비-공허화. 뮤테이션 4종(호출 하강·cap 키 환원·흔적 제거·AST 기준선) 전부 검출. `donchian_swing.py` 단독 **+96/-0 순수 추가**, 8영역 diff 0(가드 429 PASS), 신규 회귀 27, 백엔드 **5,429 PASS**. 행위 변경 0 — 관측 전용 |
| 2026-08-21 | donchian 청산 결함 3종 시정 (cycle223) | 발단 = ISC(095340) 복기 — 장중 +10% 넘게 올랐는데 트레일링이 **+4% 에 청산**. 사용자 원질문 "ATR 이 커서인가" → domain-consult(`_workspace/domain_consult/donchian_exit_retune.md`) 실측 19 왕복으로 **반증**: MFE 대비 실현 **−12%**(고점을 보고도 반납)·RR **0.47** vs 손익분기 필요 **2.25**·이익보호 3층 발화 **0회**. ATR 배수는 과대가 아니라 **재튜닝 대상**이고, 진짜로 고칠 것은 그 옆의 결함 3종이었다. **S1** `atr_trail_mult`·`breakout_fail_n_days` 를 `PARAM_RANGES`/`INT_PARAMS` 에서 제외 — 진입이 아닌 **청산 정체성 상수**라 매일 밤 AI 가 흔들 값이 아니다. **S1-F2**(적대적 리뷰 발견) 자동 경로만 막은 것은 제외가 아니었다 — 수동 적용 라우트 `routes/recommendations.py` 가 `PARAM_RANGES` 검증 없이 통과시켜 **라이브 pending 자문 1건**(2026-08-20 donchian `breakout_fail_n_days: 3`)이 실제로 적용 가능한 상태였다 → 자동과 **동일 정본** 참조 + `[manual_apply_safeguard_skip]` + 전 키 차단 시 `success=False`(조용한 성공 금지). **S2** `_rederive_breakout_high` off-by-one — `prior[:period]` → **`prior[1:period+1]`** 로 `prepare()` 의 `max(highs[1:period+1])` 과 같은 창(재시작 전후 청산 임계가 달라지던 것 해소). **S3** 시간청산 보유일 **달력일→영업일** — 주말·연휴가 보유일에 산입돼 청산이 최대 2~3일 앞당겨졌다. `_trading_days` 캐시를 `prepare`/`recompute_held_atr` 가 **이미 fetch 한 일봉으로** union 갱신 = **KIS 추가 호출 0**. 연휴 뒤 과대계상은 갭 기여를 **오늘 하루로 상한**(주말 배제)해 차단. **파라미터 값은 미변경** — S2·S3 만으로 행위가 이미 '보유 연장' 한 방향으로 움직여서, 값까지 같이 바꾸면 D+1 귀인이 불가능해진다(라이브 이탈값 `breakout_fail_n_days=2`·`atr_trail_mult=1.8` 은 DB 에 잔존, 복원 경로는 이제 수동 UPDATE 뿐). 부수 = **8영역 AST 가드가 `git diff` 라 staged 변경을 못 보던 사각** 시정(`git diff HEAD` + untracked 탐지 + 면제를 파일명 아닌 **diff sha** 에 핀 = 자기소멸). 8영역 diff 0, 신규 회귀 10 파일, 백엔드 **5,115 PASS**(cycle223 단독 clean-tree 검증) |
| 2026-08-18 | 전략 비중 단위 계약 확정 (비율 0~1) | `routes/strategies.py` 의 `v / 100 if v > 1 else v`(시정 전 :86, 현재 코드에는 부재 — AST 가드가 부활 차단) 가 **값 크기로 단위를 추측** → 프론트가 보내던 정수 퍼센트 중 **1%(정수 `1`)만 변환되지 않고 비율 1.0(=100%)으로 저장**. 운영 비중의 VB·LTV 가 각 1%(2026-08-04 사이클에서 손절 평가 유지용 극소값 0.03→0.01)라 **저장할 때마다 발동** → DB Σ 가 2.98 이 되고, 프론트 로드 휴리스틱(`Settings.tsx` `totalW <= 1.01 ? round(w*100) : round(w)`)이 그 오염을 "3개 전략 33.3% 균등분배" 화면으로 **위장** — 화면(kojiro 33.3%)과 엔진 실제 배분(kojiro 20.1% / VB·LTV 각 33.6%)이 어긋난 채 매일 부팅마다 재현. ⚠️ 오염 수치는 **관측 역산에 의한 추정**이고 운영 DB 실측은 아직 수행하지 않았다. **시정** = PUT 요청 바디 단위를 **비율(0.0~1.0)로 확정** — 추론 변환 삭제 + `field_validator` 범위 검증(위반 422) + Σ≤1.0 런타임 가드(**초과만** 잡는 비대칭이라 부분 복구 저장은 통과, 거부 시 `registry.update_weights`/`save_weights` **호출 전** early return 으로 메모리·DB 양쪽 미반영) + 부팅 `[weight_config_anomaly]` WARNING(**등록 전략 행만** 집계 = 은퇴 stale row 오탐 차단, `enabled=False` 행은 포함, **자동 클램프 금지**·fail-open) + 프론트 로드 휴리스틱 제거 · **서버 저장값 기준** 합계 경고 배너(편집 중 퍼센트 합을 쓰면 정상 슬라이더 조작과 4dp→정수% 반올림 누적오차를 오염으로 오인) · Σ>1 시 저장 차단(오염 비율을 Σ=1.0 으로 조용히 재정규화하면 백엔드 탐지기가 영구 침묵) · 비율 송신(4dp + 반올림 잔차를 최대 항목에 흡수) · 422 본문 한글 안내 노출. **8영역 diff 0** — `strategy_registry.py` 무접촉(`update_weights` 는 원래 비율을 받고 `allocate_funds` 는 상대 정규화라 입력 정상화만으로 정합). **의미 전환 1** = `test_routes_strategies.py::test_update_weights_when_percentages_then_normalized_and_saved` → `..._when_ratios_then_saved_verbatim`(payload 40/30/20/10 → 0.4/0.3/0.2/0.1). 같은 파일 `{"momentum": 0.1}` 케이스는 비율 계약에서 의미가 그대로 유효해 무변경. **알려진 한계 2** = (a) 단일 전략만 1.0 으로 오염된 경우(Σ=1.0)는 정당한 100% 몰빵과 구분 불가 — 계약상 1.0 이 유효 비율이라 불가피 (b) Σ 가드는 **요청 payload 한정**이라 상태 불변식이 아님(미제출 전략까지 합산하면 부분 복구 저장이 봉쇄되므로 의도적 비대칭). **후속(미해결)** = `risk.py:155` 가 `registry.enabled()` 단일 순회라 `enabled=False` 전략은 on_tick 손절·트레일링이 정지하고, 15:20 강제청산(`scheduler.py:2075`)·익일청산(`:1316`)·스윙 60s 폴(`:2725`/`:2845`)도 **같은 플래그로 동시에** 꺼진다 — 4중 안전망이 이 축에서 중복되지 않는다(`tradable_boards` 축 독트린과 달리 `enabled` 축은 문서·AST 가드 사각). **N1 동반 시정** = 저장 차단이 새 함정을 만들었다 — AI 자문 `apply_weight` 경로에 증액 상한이 없어 Σ 를 1.01 초과로 올리면 Settings 가 잠겨 DB 직접 UPDATE 외 복구가 없었다. `routes/recommendations.py` 에 **증액 한정 Σ 사전 검증**(params 적용 전 early return) 추가, **감액은 Σ 초과 상태에서도 항상 통과**(복구 경로 보존). 자동 경로(`auto_apply_recommendations`)는 증액 SKIP + 50% cap 이라 무가드 증액은 수동 apply 가 유일했다. 신규 회귀 = 백엔드 4파일 27 테스트 + 프론트 3파일 19 테스트 |
| 2026-08-18 | kojiro 브레이크이븐 플로어 다크런치 (cycle220) + 청산손실 심층 리뷰 | 실측 9왕복(-14,450원·승률 11%·RR 3.19 vs 필요 8.0) + domain-consult(`kojiro_exit_loss_review.md`). **판정 = 진입결함 아님**: RR 은 안 깨졌고 승률이 defensive 레짐 세금(손익분기 23.8% vs 관측 11%), 오염 3건(DMS/iM/삼영 -8% 클러스터 = 08-04 `_effective_atr` 시정 전 2ATR 죽음 시기 백스톱 증폭) 보정 시 -2.98%→-2.2~-2.5%. **진짜 갭 = 이익보호 전무** — 08-18 샹들리에 3청산(영원무역 +9.4%→-4.4%·LG생건우 +6.7%→-3.4%·CJ CGV +10.7%→-1.1%) 전부 +1.5N 도달 후 전량 반납. 스테이지3 0발화는 설계 의도(대순환 롤오버 늦은 신호, 샹들리에 선행 정상). 시정 = `breakeven_promote_atr=0.0` **다크런치**(donchian P1 선례) — §2 승격(`high≥buy+mult×ATR`→`eff=max(eff,buy)`→`_stop_floor` tighten-only 래칫 영속) + `recompute_held_atr` 재시작 재도출(H-1 고점 복구 후) + `_position_stop_price` be_line 4선 max read-only 미러(커플링 불변식). **샹들리에 2.5 불변**(domain 금기 — 플로어≠트레일, fat-tail 미절단). AI weight 0.6→0.2 권고(08-13/14 pending) = **채택 반대**(오염데이터 기반+Σ캡 중복 디리스크+0.2 는 1주/0주 양자화로 표본 해상도 파괴) → N=10 재튜닝서 exit 패키지와 재결정(강제 시 0.4). 활성화 = N=10(청산 1건 남음) 시 DB UPDATE(운영 DB 키 부재 실측 확인=다크 확정). kojiro.py 단독 +40/-7, 8영역+scheduler diff 0, 신규 21 + kojiro 227 PASS, 백엔드 4,951 PASS |
| 2026-08-14 | 재구독 안전망 정합화 (cycle215~218) + 세션증설 | 실측 손절 사각 발견→3+1 사이클 시정→D+1 확증. **cycle215** split-brain 복구 — `resubscribe_stale_priority`(5분)의 subscribe *전* `unsubscribe_in_pool` 선행(K watcher 342 패턴). OPSP0008 거부 후 `_ticker_to_session[t]=main` 잔존→풀 dedup 가드가 재SEND 억제→개장러시 매수 보유 종목 온종일 미구독=손절 사각(실측 001450/053800 5h+ 미구독, 스윙폴 60s 보강뿐·非스윙폴이면 완전 사각). 3렌즈 적대적 검증(workflow)으로 근본원인 확정. **cycle216** 동시호가 LOW-scoped skip(HIGH 09:00 갭개장 대비 유지) + LOW-only throttle(`RESUBSCRIBE_THROTTLE_SECS=180 < 300` 불변식·HIGH 면제) — domain-consult(HIGH throttle 오작동=손절사각 vs LMS는 LOW cap10 상주). **cycle217** 배포 후 자가발견 회귀 — cycle215 `unsubscribe_in_pool`이 미구독 stale 후보(`ticker_last_tick` 소스)까지 KIS unsubscribe SEND→OPSP0003 'not found' 766건/일. 구독상태 가드(`get_subscribed_tickers` 스냅샷: 구독→`unsubscribe_in_pool` / 미구독→`_ticker_to_session.pop` 직접)로 D+1 766→0 확증. **cycle218** r 카운터 무한 climb(051905 r=131) 관찰성 — cooldown-skip 분기 `_stale_retry_count=MAX+1` 홀드(r>5 전부 동일 임계경로라 행위 불변, 소비자 전수 감사). **세션증설**(보조 4→6=287슬롯, 틱 OPSP0008 4→0). 전부 `stale_watcher_core.py` 단독·**8영역 diff 0**·백엔드 4,905 PASS. 배포 175612e/f8f5105/6d07d63 (verbatim `docs/HARNESS_CHANGELOG.md`) |
| 2026-08-08 | VCP·BFB 확대 유니버스 (kojiro식 전체 상장) | 사용자 지시 "VCP·BFB 도 kojiro 처럼 전체 상장 중 일부필터 적용한 확대 유니버스". **4개 조사(구독 압력·테스트 영향·일봉 데이터·도메인) + 자문 + EC2 실측 + 적대적 검증(3렌즈)**. **구독 압력 재프레이밍** — 구독은 유니버스가 아니라 **셋업 통과 후보(get_scanned_tickers)에 비례**(VCP≈0→1~2, BFB≈18). VCP/BFB 는 kojiro 와 달리 **REST 폴 경로 없음**(tick 구독 의존) — kojiro 는 후보를 tick 구독 안 하고 REST 로 스캔해 확대를 감당. **일봉 blocker 반증** — daily-load 유니버스(지수∪500억/10억)가 kojiro 확대의 상위집합, EC2 실측 비지수 자격 641종목 중 **95.8%(614) ≥100일 적재·폴백 27종목뿐** → **scanner 무변경**(domain "979 폴백 폭주" HIGH 우려 반증, test-impact 판단 채택). **VCP** = 지수 제거(is_kospi200/kosdaq150=None) + 거래대금 10억 신설(하드코딩 0→실사용) + max_scan 200→4000. **BFB** = 이미 지수 무제약, 거래대금 20억→15억(도메인 B2 — 장중 돌파 추격 슬리피지라 kojiro 10억 회피) + max_scan 100→4000 + return_stage_counts 배선. **시총 100억**(사용자 결정 — kojiro 500억보다 낮게, 소형주 포함). **병목 정직 평가** — VCP 병목은 유니버스가 아니라 추세필터(97.9% 탈락) → 확대는 근본 미해결이나 후보 0→1~2로 **관찰 표본 처음 생성**. 진입 임계=정체성 상수 불변, 체결 확보 후 별도 사이클. **적대적 검증 결함 시정** = F-A(funnel step0/step1 union/trade 배선 — "컷 전" 라벨 collapse) + F1(ScanMonitor VCP 스테일 라벨 시정 + BFB union 노출) + F-D(BFB graceful) / #2(max_scan 4000>PARAM_RANGES cap 500 — pre-existing kojiro 동일·test_cycle212 잔존 의무라 미변경) / F2(daily-load "20억" 스테일 주석 — 런타임 10억 정합·scanner 무변경 보존). **DB strategy_config 동반 갱신 필수**(코드가 DB 에 덮임 실측: VCP/BFB 라이브 mcap 100억·trade 20/50억·scan 500) → VCP trade 10억·BFB trade 15억·둘 다 scan 4000 UPDATE 완료(mcap 100억 유지, 다음 부팅 반영). 8영역 diff 0, 회귀 백엔드 12 신규+의미 전환 3, 백엔드 4,774 PASS + 프론트 35 PASS + build |
| 2026-08-08 | 구독 우선순위·cap 제거 + kojiro 한도 지혈 + 성장 경로 로드맵 | 선결과제 ②④⑤ 종합. **조사에서 ④⑤ 원 진단이 반전**(19+16 에이전트 2회). **⑤ kojiro 일봉 고갈 = 반증** — daily-load 자격 임계(시총500억·거래10억)와 kojiro 스캔 임계가 **완전 동일**이라 이탈 424종목은 kojiro 유니버스에도 없는 임계 미달 종목 = 표본 유실 아님. 지수편입 348 전부 fresh. **현행 유지**. **④ cap = vestigial 반증** — momentum 급등 스캔이 enabled 무관 리스트를 채워 `BREAKOUT_LOW_CAP=25` 가 살아있는 breakout(BFB/VCP) 슬롯을 죽은 momentum 으로 전용시키는 **능동적 손해**. 시정 = (a) cap 제거(breakout 전체 pass-1 최우선) (b) `_collect_breakout_tickers` 순서 VB→LTV→BFB→VCP → **BFB→VCP→VB→LTV**(사용자 결정, BFB 60% 미구독=tail 편중 실측, BFB/VCP 는 폴링 없이 tick 으로만 매수평가라 구독=매수기회) (c) `[priority_drop]` 에 pool_sessions/pool_slots 병기(미구독 진단). **② kojiro 한도 1.2 위반** — `ratio 0.20 × maxp 6 = 1.2 > 1.0`, DB 런타임 값에만(코드 기본 0.20×5=1.0). C-DEFAULT(소스 리터럴)·C-CROSS(AI추천) 가드가 **운영자 수동 DB apply 사각**을 못 막았다. 지혈 = **B′ ratio 0.166**(×6=0.996, 사용자 결정 — 성장 경로상 position_ratio 는 계속 낮아질 값이라 궤적 첫걸음. 자문 권고 0.167 은 ×6=1.002 미세위반이라 0.166 정정, DB 적용 완료) + **런타임 가드 신설**(`portfolio_risk.check_budget_invariant` 순수함수 + boot_manager 배선, 부트 실행값 검증 WARNING, 수동 apply 사각 영구 차단, fail-open). **종목수 제한 vs 유닛 캡 도메인 자문**(사용자 원질문 "유닛 제한 있으니 종목수 제한 걷어낼 수 있나, 피라미딩 빨리?") — **성장 경로(현 117만→500만→1-2억)** 전제 재자문. 결론: 사용자 직관은 **이상적 터틀에서 옳으나** 우리 유닛은 (1주 양자화·hard_stop·혼재로) 깨진 벽돌이라 개수≠리스크. **개수 캡은 걷어내는 게 아니라 역할 진화** — 소액 중복(무해)→중형 load-bearing→대형 상관군 캡 병행, 제거는 로드맵 **마지막**(T4 2억, 옵션). 정량: 피라미딩 해상도 임계 net 500만(현 117만은 1주=노이즈), ②개수천장=1/ratio, ③Σ리스크캡 규모불변(항상 4.5유닛). VCP/BFB 는 피라미딩 부적합(변동성수축/measured-move)이라 개수 캡 load-bearing 영구·활성은 체결+백테스트 게이트. **지금=지혈+문서화+inert 봉인, 나머지 자본/체결 게이트(기제 착수 net 500만)**. FREEZE(N=1·0/4) 표본 보호로 구조 재설계 금지. `strategies/CLAUDE.md` 생애주기 표 + `_workspace/domain_consult/` 성장 경로 개정판. 성과 표시 정직화(합성 total_asset→te 실현손익 병기) 동반. 의미 전환 6(cap 25 행위), 신규 회귀 백엔드 13, scheduler 외 7영역 diff 0 |
| 2026-08-07 | 레짐 관찰 전용 정직화 (자문 payload + buffett 버그 + 프론트 배너) | 선결과제 ③. **착수 전 내 "매핑 깨짐" 진단이 다각도 조사(19에이전트)로 반증됨** — dkstock 은 `raw.cycle`(경기순환=expansion 확장기)과 `raw.regime`(투자레짐=defensive)을 **별개 필드**로 준다("경기 좋지만 밸류에이션 극단이라 방어 권고"). 스냅샷 regime='defensive'는 `raw.regime.regime` 정확 반영 = 매핑 정상. **진짜 문제 = 표시/행위 정반대**: 사이클 I 가 레짐 매수 게이트를 전면 제거(관찰 전용)했는데 `/current` 만 `buy_blocked=False` 정직화했고 **자문 계층 `to_advisor_dict` 만 레거시 `buy_blocked=True`(defensive→block_reason→True) 방출** → SYSTEM_PROMPT 거짓 등가("buy_blocked=True=모든 전략 매수 차단→매수 튜닝 무용")와 결합해 **매일 20:00 자문이 매수 파라미터 권고를 통째 스킵**(엔진은 100% 자유 투입 중인데 AI 엔 "전면 차단" 거짓). 사용자 결정 = **방향 A(관찰 전용 확정, 행위 무변경)**. 시정 = (1) `to_advisor_dict` buy_blocked→False(`/current` 정합, block_reason 은 방어 '권고' 관찰용 유지) (2) SYSTEM_PROMPT 재작성(레짐 미개입·매수 튜닝 유효·block_reason 은 보수적 권고 참고) (3) **buffett_ratio 파싱 버그 F1** — `from_macro_cycle` 이 `params.pbr_max`(PBR상한, 라이브 0=비활성)를 buffett 로 읽어 /current·자문·스냅샷 전 계층 null → `regime.buffett_ratio`(라이브 1.45=방어권고 핵심근거) 정정 (4) 프론트 `MarketRegimeCard` auto_regime_adjust=false 시 "관찰 전용—실제 매매 미반영(cash N% 수동)" 배너 + 경보 "(권고·관찰)" 표기 (5) `CLAUDE.md:798` stale 독트린("buy poll 레짐 매수가드 복제") 정정=유령 게이트 복원 차단. buy_blocked 프로퍼티/is_buy_allowed/스냅샷 감사기록 유지(자문 payload 에서만 False). 의미 전환 2(payload buy_blocked True→False), 신규 회귀 백엔드 10+프론트 2, **8영역 diff 0**(market_regime/recommendation_engine 은 8영역 아님), 백엔드 4,748 PASS + 프론트 build 통과. 잔여(후속): 스냅샷 buy_blocked 재의미화·raw.errors 미검사·확장기/buffett_level 표시 축 — 전부 관찰성 후순위 |

> 사이클 200 이하 및 초기 하네스 구성 전체 이력(verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)

### 테스트 실행

```bash
pip install -r requirements-dev.txt # 1회
python -m pytest -q # 백엔드 전체
cd frontend && npm install && npm test # 프론트엔드 전체
cd.. && npx playwright install && npx playwright test --config=e2e/playwright.config.ts # E2E

# 영향 테스트만 (PR 빠른 피드백)
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
pytest $(python tools/test_impact/affected.py origin/main --target=backend)
```

## 빌드 & 실행

```bash
# Docker (권장)
docker compose up --build # 개발: 프론트 :3000, 백엔드 :8002
docker compose -f docker-compose.prod.yml up --build -d # 프로덕션: Nginx :80

# 로컬
pip install -r requirements.txt && uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
cd frontend && npm install && npm run dev
```

## 환경 변수
`.env` 필수 (`.env.example` 참고).
- `KIS_ENV`: `vts`(모의) | `real`(실전)
- `KIS_APP_KEY_REAL/VTS`, `KIS_APP_SECRET_REAL/VTS`, `KIS_ACCOUNT_NO_REAL/VTS`
- `KIS_HTS_ID`: 실전 체결통보(H0STCNI0) 구독 키
- `DATABASE_URL`: AWS RDS PostgreSQL asyncpg DSN (`?sslmode=require`). **현재 DB 정본** — 전 db 모듈이 `src/db/pg.py` 풀로 사용
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용** (settings/.env 에 잔존하나 어느 db 모듈도 참조 안 함, `src/db/supabase.py` 롤백용 병존)
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `DKSTOCK_REGIME_ENABLED` (기본 false): dkstock.cloud 매크로 레짐 수신 + cash_usage_ratio 자동 조정 활성화 (매수 가드는 사이클 I 제거 — 레짐은 관찰 전용)
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 6 전략 × 2 kind = 12 job fire-and-forget

## 다중 전략 (요약)

7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`).

상세 매수/청산/tradable_boards/exchange 는 **`src/engine/strategies/CLAUDE.md`** 참조.

### 새 전략 추가
1. `src/engine/strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `src/engine/scheduler.py` `__init__` 에서 `registry.register()`
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. `strategies/CLAUDE.md` 표 + `_workspace/00_leader_trading_rules.md` 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- **전략 비중 단위 = 비율 `0.0~1.0` (2026-08-18 확정)** — `PUT /api/strategies/weights` 요청 바디 · `GET /api/strategies` 응답 `weight` · `strategy_config.weight` 컬럼 · AI 자문 `save_weights` 경로가 **모두 같은 단위**라 GET↔PUT 왕복이 항등이다. 라우트가 범위 위반은 422, Σ>1.0 payload 는 `success=false`(저장 미수행)로 거부하고, 부팅 시 `_load_strategy_config` 가 **레지스트리 등록 전략 행**의 개별 `weight > 1.0` 또는 Σ `> 1.001` 을 `[weight_config_anomaly]` WARNING 으로 관찰만 한다 — **자동 클램프·정규화 금지**(오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다), fail-open
- `position_ratio` 는 **전략 할당 자금 기준** — 정확한 식은 `순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio` = 종목당 매수금액. `allocate_funds` 가 **Σ 로 정규화**하므로 Σ≠1 이어도 자산 전액이 배분된다
- **전략별 투자한도 (2026-08-03 이중 → 2026-08-04 kojiro 삼중)** — ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment` + ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 터틀의 유닛 캡이 통제하려던 값은 ③이고 유닛 **개수는 프록시**일 뿐 — 수량 절삭·`hard_stop_pct` 캡·사이징 혼재로 프록시가 헐거워진다(08-04 실측 6포지션=3.2유닛). **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). ②는 ②는 `StrategyBase._apply_budget_limit` 공통 관문이 7 전략 `calc_buy_quantity` 의 모든 return 을 통과시켜 강제하며, 잔여가 부족하면 **부분 매수**(잔여 < 1주 → 0). 불변식 **`position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT)가, AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다: 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 ATR 로 바꾸면 정규화가 깨진다(함정 #1). 현재 배선 = donchian(라이브) · kojiro · VCP/BFB(다크런치, 하드손절 ATR화 동반). momentum/VB/LTV 는 제외(ATR 부재 / 당일 청산 / 상한가 2모드 재설계 선행). `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 순수 축소 방향
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`)

### 외부 통합 (백테스트 + 매크로 레짐)
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 6 전략 × 2 kind = 12 job fire-and-forget → `parameter_recommendations.backtest_summary` JSONB
- 매크로 레짐 (`dkstock.cloud`) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정 (`auto_regime_adjust`, `clamp((100-cash_min)/100)`). **매수 가드는 사이클 I(2026-08-03) 제거** — 레짐은 매수를 차단/축소하지 않는 관찰 지표(`buy_block_mode` 는 표시 전용 잔존, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). ETF 레짐(E-1)·포트폴리오 리스크(사이클 H) 관찰 활성
- 활성화 토글: `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` / `etf_regime_enabled` (Settings UI 즉시 토글). 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 레짐 관찰 비활성
- 운영 가이드: [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:

- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — 무언가를 "미사용/dead/낭비"라고 단정하기 **전에 소비처(consumers)를 전수 확인**하고, 비활성화 **후에는 그 소비처가 여전히 정상 동작하는지 라이브 실측**으로 검증한다. **비활성화는 "제거"가 아니라 "경로 변경"일 수 있다** — 주 경로를 끄면 폴백 경로가 조용히 degrade될 수 있으므로, 배포 후 반드시 실측 점검한다(설정 토글은 CI/Deploy 를 안 타므로 자동 검증도 없다). 실측 없는 비활성화 금지. ⚠️ **재발 방지 사례 (2026-08-08 KRX OpenAPI)**: `krx_open_api_enabled` 를 "무효 키·낭비"로 오판해 비활성화 → 소비처 `scanner._full_universe_load_krx_primary`(20:00/07:48 전체 유니버스 적재 주 소스)가 KIS market-cap 폴백으로 밀려 **full_universe_load 가 3,577→60종목으로 degrade**(D+1 실측 발견). 원인 = (a) 소비처 미확인(주 소스인데 "미사용" 오판) + (b) 비활성화 후 점검 절차 부재. 키는 실제 유효(40자)했고 재활성화로 복원. **끄기 전에 `grep` 으로 소비처를 찾고, 끈 뒤엔 그 소비처의 산출물(예: 적재 종목수)을 라이브로 확인하라.**
- **체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑** (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum" 으로 잘못 INSERT됨
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today 가 다음 날까지 잔류
- **익일 청산** 은 scheduler 에서 시가 수신 후 30s 안정화 처리 — `_pending_next_day_clear` 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지. on_tick 즉시 청산 금지
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비=손절 마비이므로 반드시 해제) + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s 주기, 1~5회 즉시 강제 재등록 + 6회 초과 시 10분 cooldown 기반 시간 기반 force_retry + 시간당 6회 cap, 사이클 102 임계 상향) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단)
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약**이다. 관문 안에서 `await`/DB/HTTP **절대 금지** — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다
- **비중 단위 추론 변환 금지** — 전략 비중은 **어느 계층에서도 값 크기로 단위를 추측하지 않는다**. 폐기된 `v / 100 if v > 1 else v`(라우트)와 `totalW <= 1.01 ? round(w*100) : round(w)`(프론트 로드)는 1%(정수 `1`)를 100%로 저장하고 그 오염을 "균등분배" 화면으로 **위장**했다 — 추론 분기는 오염 시에만 깨어나므로 결함이 아니라 결함 은폐 장치다. 단위는 계약으로 고정(비율 0.0~1.0)하고 위반은 조용히 흡수하지 말고 422 / `success=false` 로 **시끄럽게 거부**한다. AST 가드 = `tests/unit/ast/test_ast_weight_no_magnitude_heuristic.py`(`update_weights` 내 `IfExp` · `/ 100` 0건, Σ 가드가 저장보다 선행 + 사이에 early return) + `frontend/src/components/__tests__/_ast_weight_unit_guard.test.ts`(`Settings.tsx` 내 `1.01` 리터럴 · `Math.round(s.weight)` 0건)
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지. DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다. position_ratio 매수는 미스탬프라 기존 % 손절 경로를 byte 동일하게 탄다. 스탬프 값은 반드시 sizing 에 쓴 ATR 과 동일(커플링 불변식)
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱(전일 상한가 종목 시초가 하한가 형성 등)의 허깨비 손절·트레일링 고점 오염을 차단하고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도로 전환). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정(AST 가드) — 매수 목적 보드 변경이 청산 규약을 바꾸는 커플링 차단. 매도 시장가는 `execute_sell` 이 프리장 단독 구간에서 `step_down(현재가,5)` 지정가로 사전 변환(매수 PR-F 대칭, 실효 대상 LTV). `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수)
- **donchian_swing `_swing_rest_poll_loop`** 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 손절 평가 보강
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트 `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시. `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
- 매매 파라미터 (`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 또는 `kis_get_quote()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID 는 `settings.get_tr_id()` 사용 — 하드코딩 금지
- DB 접근은 `src/db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유. JSONB=raw dict 바인딩(codec) / TIMESTAMPTZ 쓰기=`datetime.fromisoformat(now_kst_iso())`·읽기=`to_char(...,'+09:00')` / DATE=`_kst.to_date()` 강제 (상세 `src/db/CLAUDE.md`)

## DB 스키마 (AWS RDS PostgreSQL)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`. (마이그레이션 디렉토리명은 supabase/ 유지 — 스키마 SQL 정본, RDS 에 순차 적용)

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, cash_usage_ratio, buy_block_mode + 4 임계값, dkstock_regime_enabled, kis_mcp_enabled 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE). `recommended_weight`/`code_review_notes`/`applied_weight`/`weight_reasoning`/`backtest_summary` JSONB |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + **사이클 129 `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` 신규** (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. **사이클 168 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED** (migration 039 — raw.hts_avls/acml_tr_pbmn 가 jsonb *문자열* 로 저장되어 UI `list_paged_by_filter` jsonb numeric gte 가 0건 silent 결함 → 생성 컬럼 numeric 비교 + 인덱스로 시정. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL. raw 읽기만 = 사이클 81 G-AST1 영속) |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (백필 시 T-100일, 이후 D-1 영업일 증분). **사이클 172 — VCP universe (KOSPI200∪KOSDAQ150) backfill** (분할 fetch) + retention `DAILY_RETENTION_DAYS=230`. **사이클 196 (2026-07-07) — VCP backfill target 220→120 수렴** (retention 230cal=154영업일 실측 < 220 → 무한 재backfill churn → target 120 하향 + `fetch_daily_candles_backfill` 윈도우 클램프, VCP prepare 실사용 100일 << 154 보유 무영향). donchian (20일 신고가) / VCP (베이스+Pullback, prepare 100일 cap) / VB (ATR) 전략 활용 |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041, 사이클 C1). PK `(ticker, stac_yymm, div_cls)` (div_cls 0=년/1=분기) + 18 NUMERIC 컬럼(손익 5/대차 7/수익성 2/안정성 2/기타 2) + raw JSONB + refreshed_at. 마법공식(EV/EBITDA·ROC) + F-Score-7 원천 데이터. 주1회 16:40 적재. 매매 hot path 무관 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클) |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷. `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 수동 trigger `POST /api/strategy-funnel/snapshot` (현재 최종 단계 `step_no=99` 만, 자동 hook 은 후속 사이클) |

> **`trade_history` 부분 UNIQUE 인덱스 (migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.

> **`stock_master` / `stock_master_daily` UI 동기화 의무**: stock_master 컬럼 / raw JSONB 키 / stock_master_daily 컬럼 추가 시 UI 동기화 의무 영속. 전략에서 종목마스터 데이터 참고 시점 영역부터 신규 수집 데이터는 UI 노출 의무. 절차 = (1) `frontend/src/types/stock-master.ts` interface 갱신 (2) `frontend/src/api/stock-master.ts` 호출 영역 갱신 (3) `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키 추가 (4) `GET /api/stock-master/stats` 응답에 진단 카운트 추가 + 카드 1개 추가 (5) `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 갱신 (6) 회귀 가드 추가. 상세는 `frontend/CLAUDE.md` 참조.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분. deploy.yml 은 push 후 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용 (`SUPABASE_DB_URL` secret — **이름은 유지하되 값이 RDS DSN**, graceful skip)
- CI (`.github/workflows/ci.yml`): `postgres:15` service 컨테이너 + `DATABASE_URL_TEST` 로 통합 테스트 실행 (`tests/integration/pg_harness.py` 가 migration 001~041 적용)
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL` (값=RDS DSN)
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- 운영 가이드: KRX 메인 시간 (09:00~15:30) 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능. NXT 애프터 (15:30~) 또는 익일 07:55 _boot 전 push 권장

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 20:10 일일 분석 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 6 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `dkstock_client.py` 매크로 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
