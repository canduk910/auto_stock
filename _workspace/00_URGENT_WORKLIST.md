# 🔴 최우선 과제 — BFB·VCP 매수 전면 차단 (2026-08-25 확정)

> **이 파일이 현재 최우선 작업 지시서다.** 새 세션은 다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.
> 근거 보고서: https://claude.ai/code/artifact/75081207-15a8-4d43-9574-2352dae049b2
> 작성 시점 상태 = 미푸시 커밋 0 · 워킹트리에 미커밋 cycle221 잔류.
>
> **✅ P0-1 종결 (2026-08-28 사이클 228 게이트 전환 — 커밋 A `4e7b302` + B, 배포 대기)**
> 사이클 227 배포(a7245af) → 이틀 관측 would_pass 0/5 → 래치 선행 확정 → 사이클 228 이
> 게이트를 tick_volume 실측 + 충족 래치 + 추격 상한으로 전환(**매수 개방**, 비중 현행).
> 228-B = `_effective_setup` 구조 레벨 stamp 우선 복원(별도 커밋, D+1 귀인 분리).
> 다음 액션 = **15:30 NXT 애프터 이후 푸시**(KRX 장중 자제) → D+1 관찰(첫 체결·청산 경로
> 첫 실가동·`latch_age_sec`·`[setup_structure_conflict]`·진입 임계 재튜닝 금지 N=10).
> ⚠️ `[*_vol_gate_observe]` 마커 은퇴 — 08-28 전후 로그 같은 grep 합산 금지.
> tester 조건부 GO(`_workspace/test_report_cycle228.md`, 결함 6) → 228-C 로 D-1(C-6 가드
> 공허화, 뮤테이션 실증)·D-2(죽은 필드+invariant 경고 1회/일 cap)·D-3(release cap reason 축)
> 시정 완료. **이관 잔여**: D-4(read 예외 debug 단독 — no_data WARNING 동반이라 LOW 수용) ·
> D-5(대시보드 래치 상태 미노출 — 후속 사이클 후보, `get_targets_status` 키 추가만으로 가능).

---

## 📋 활성화 게이트 4건 (구 `monday_activation_guide.md` 에서 이전, 2026-09-02)

> 원본은 2026-08-10 대상 가이드라 날짜는 지났으나 **게이트 조건 자체는 날짜 무관**이라
> 삭제 전 여기로 옮긴다. §6(포트폴리오 SOFT 상한)은 cycle233 으로 **완료**되어 제외.

### ▶ G-8. VCP/BFB 브레이크이븐 승격 — ✅ **VCP 는 이미 활성 (2026-09-02 운영 DB 실측)** · BFB 대기

> **09-02 정정** — 사용자 결정 "G-8 진행" 후 운영 DB 를 읽어 보니 `vcp_breakout.params` 에
> **`breakeven_promote_atr: 1.5` 가 이미 들어 있다**(`strategy_config.updated_at` 2026-08-18
> 08:10 UTC 이후 변경 없음 — 사이클 C(07-30) default-off 배포 후 어느 시점에 DB 로 켜진 값).
> BFB 는 `0.0`(비활성, 코드 기본값). 따라서 아래 UPDATE 는 **실행 불필요·실행 금지**(중복
> 적용은 무해하나 "이날 활성화했다"는 오귀인을 만든다). `[vcp_breakeven_promote]` 로그는
> **0건** — 활성 상태지만 VCP 체결이 전 기간 0건이라 발화할 포지션이 없었을 뿐이다.
> **남은 액션** = VCP 첫 체결 후 래치/승격 발화 관찰 → BFB 활성 여부 재평가(NO-GO 시 2.0N).

- **게이트 정의**(원본): donchian `[donchian_breakeven_promote]` **발화** + 이후 whipsaw
  (승격 직후 손절) **부재**. 원본 작성 시점(08-08)엔 "21일간 0발화·SELL 0건"이라 미충족이었다.
- **09-01 실측 = 첫 발화**: `192820` 고점 306,500 ≥ 매수가 273,500 + 1.5×ATR(16,778) →
  손절선 **239,944 → 273,500** 승격. 이후 18:09:50 애프터에 **275,500 원 매도(+2,000)**.
  시장가 거부(APBK3013)를 지정가 폴백이 받아냈다.
- ⚠️ **whipsaw 판정은 사용자 몫**이다. 두 해석이 다 성립한다 —
  (a) **clean**: 승격이 없었으면 손절선이 239,944 라 훨씬 아래까지 끌려갔을 것이고,
      실제로는 **손실 없이(+2,000)** 빠져나왔다 = 플로어가 의도대로 작동.
  (b) **whipsaw 성격**: 고점 306,500 대비 **−10.1% 반납** 후 승격선 부근에서 청산 =
      cycle220 자문이 지적한 "MFE 대비 반납" 패턴의 재현.
  표본이 **N=1** 이라 어느 쪽도 통계적 근거는 아니다.
- ~~**활성화 시(장 마감 후 DB)**~~ — **VCP 는 이미 적용됨(09-02 실측), 실행하지 않는다.**
  BFB 활성화 시에만 아래를 `strategy_id='bull_flag_breakout'` 로 바꿔 사용:
  ```sql
  -- BFB 전용 (VCP 관찰 후 GO 판정 시). VCP 는 이미 1.5 — 재실행 금지
  UPDATE strategy_config SET params = params || '{"breakeven_promote_atr": 1.5}'::jsonb
   WHERE strategy_id='bull_flag_breakout';
  ```
- ⚠️ VCP/BFB 는 **체결 0건**이라 활성 상태여도 당장 검증할 포지션이 없다.
  BFB 는 09-01 래치 첫 무장(`001450`)까지 갔으므로 첫 체결 후 재검토가 순서다.
- 확인 명령(읽기 전용): `SELECT strategy_id, params->>'breakeven_promote_atr' FROM strategy_config
  WHERE strategy_id IN ('vcp_breakout','bull_flag_breakout');` → 기대 `1.5` / `null|0`.

### ▶ G-9B4. VB 실패돌파 조기청산 — 백테스트 스윕 대기

`failed_breakout_buffer_pct` / `failed_breakout_confirm_ticks` 외부 MCP 스윕(VB 는 YAML DSL 지원)
→ avg_loss↓·RR↑ 확인 → `failed_breakout_exit_enabled=true` DB 활성 → te_metrics 재측정.
VB 는 사이클 F 실측 **유일 열위**(승률 35%·RR 1.35 < 필요 1.83)라 우선순위가 높다.

### ▶ G-9B5. VB RS/RSI 진입 품질 필터 — 유의성 검정 대기

사이클 G(08-02) 관찰 시작. 고RS/저RSI극단 vs 저RS/고RSI 승률·RR 유의성 검정 → 유의 시
RS(B2) 실배제 우선 활성. ⚠️ 별도 실측(`project_vb_observation_hooks_verdict` 메모리)에서
**1,498 관측 전부 무신호·RS 는 역방향**으로 나와 **무기한 보류** 상태 — 재개는 레짐 전환 후.

### ▶ G-7. VCP/BFB 터틀 sizing — 구조적 봉인

외부 백테스트 스윕이 게이트인데 **VCP/BFB ∈ `_FALLBACK_STRATEGIES`**(recommendation_engine.py)
라 MCP YAML DSL 미지원 ⇒ 스윕 자체가 불가. 대안 = (a) 로컬 백테스트 어댑터 구현 또는
(b) 확대 유니버스로 라이브 체결 축적 후 실측.

---


## ✅ P1-6 · donchian 프리장 청산 보류 게이트에 **매일 ~30초 구멍** — **cycle238 종결 (2026-09-02, 시정안 A, 커밋 대기)**

**발단** — cycle237(청산 로그 cap) 적대 검증이 "08:00~09:00 68건은 프리장 게이트와 모순"이라
지적 → EC2 실측으로 판별한 결과 **게이트는 작동하지만 08:00 정각에 늦게 걸린다**.

**실측 (09-02)**
```
08:00:00  도치안 시간 기반 청산: 034020 ...          ← 청산 평가 통과 (게이트 미적용)
08:00:00  APBK0918 [프리마켓] 시장가 매매 불가        ← 실제 매도 주문이 나갔다
08:00:00  매도 거부 — positions 보존
08:00:29  [pre_market_exit_deferred] donchian_swing  ← 이제서야 게이트 적용
```
같은 패턴이 08-31(08:00:28) · 09-01(08:00:01) 에도 있다.

**원인 가설** — `risk._defers_pre_market_exit` 는 `MarketBoard.PRE_NXT in session_tracker.active`
를 요구하는데, `_session_loop` 가 **30초 주기**라 08:00:00 시점엔 `active` 가 아직 갱신되지
않았다 ⇒ 게이트가 **fail-open**(판정 불가 시 평가 유지)으로 떨어진다. 08:00 은 익일 청산
task 가 도는 시각이라 tick 이 몰린다.

**위험** — 2026-08-06 에 "프리장 왜곡 틱(전일 상한가 종목 시초 하한가 형성 등)의 허깨비 손절·
트레일링 고점 오염 차단" 목적으로 세운 게이트가 **매일 30초 무력**하다. 09-02 엔
`nxt_tradable=False` 라 APBK0918 로 막혔지만, **NXT 거래가능 종목이었으면 체결**됐을 수 있다.
대상은 donchian·kojiro·VCP·BFB·momentum·VB(= LTV 제외 전 전략)의 **멀티데이 보유 포지션**.

**✅ cycle238 시정 (2026-09-02, 사용자 결정 "P1-6 은 A 로 진행", 8영역 승인 `risk.py` 단독)**
- **원인 확증** = 가설 그대로. `active` 의 유일 기록자는 `SessionTracker.tick()` 이고 `_session_loop`
  가 30초 주기로만 호출(`SESSION_TICK_INTERVAL=30`), H0UNMKO0 는 `_last_nxt_mkop_code` 에만 기록
  (`active` 미관여). 07:55 사전구독 첫 틱이 08:00:00 에 오면 `boards_at(07:59)`=∅ 스냅샷이 살아
  있어 게이트 fail-open. 매수측은 2026-05-15 "결함 A" 가 같은 race 를 `board=` 명시로 우회했지만
  청산측 게이트는 그 우회를 받지 못했다.
- **시정** = `_defers_pre_market_exit` 를 `by_active`(기존) **OR** `by_clock`(`session.boards_at(
  _now_kst().time())` fresh — 08:00/09:00 리터럴 신설 금지, 스케줄 표 단일 소스, `_KST` 명시)로
  전환. 화이트리스트 LTV 최상단·평가 보류(주문 보류 아님)·`tradable_boards` 미독 불변. fail-open
  은 **두 소스 모두** 예외일 때만. `by_active` 가 False 인 **모든** 경우(∅뿐 아니라 MAIN/POST
  stale 포함)에 시각이 PRE 면 보류 — tracker 가 1시간 이상 죽어야 도달하는 안전 방향.
- **09:00 정각 판단(team-leader)** = stale `active`={PRE} 잔존 ≤30초는 OR 라 보류 유지 = 현행 라이브
  동일. 안전 방향 + 한 사이클 한 엣지(D+1 귀인) + 개장 30초 스프레드. `reason=active_stale_hold`
  로 계량하고 clock-primary(09:00:00 정확 해제)는 후속 후보.
- **관측** = `[pre_market_exit_gate_divergence] strategy= reason=clock_fallback|active_stale_hold
  active= clock_kst=` 1회/(전략,사유)/일(날짜 키 `_now_kst` 자기 리셋 + `reset_daily_state` 동행
  + peek→로그→mark). 기존 `[pre_market_exit_deferred]` 서식·cap 무변경.
- **결정성** = 루트 `tests/conftest.py` autouse `_pin_pre_market_clock`(`risk._now_kst` 를 MAIN
  10:30 으로 핀, 옵트아웃 마커 `real_pre_market_clock`). 2026-08-06 의 "wall-clock 아님" 계약은
  폐기(08:00 라이브와 테스트 기본이 둘 다 `active`=∅ 라 벽시계 의존이 불가피).
- **검증** = Red 12 FAIL → Green → 적대 검증 뮤테이션 18종 중 escape 4 → 전부 테스트 보강(F1 active
  사망+clock PRE → True · F2 `boards_at` **호출** AST · F3 일치 시 divergence 0 · F4 화이트리스트
  단락) + T-8 가드 과잉(`.time()` 추출까지 금지해 `timetz().replace` 우회 유발) 정밀화. 차분
  3,000×7 `active` 정상 갱신 시 판정 차이 0. hot path +0.3µs/틱. 8영역 sha 핀 3가드 재핀(cycle235
  죽은 핀 삭제).
- **D+1 판독 채널** = `[pre_market_exit_deferred]` 첫 타임스탬프가 08:00:0x 로 당겨지고 같은 시각
  `reason=clock_fallback` 이 동반되면 구멍이 닫힌 것. `도치안 시간 기반 청산` 첫 발화가 09:00 이전
  이면 여전히 결함. ⚠️ divergence 는 **보유 종목 틱이 있을 때만** 계량 — 부재 ≠ 구멍 없음.
- **남긴 후속** = ① clock-primary 09:00 정확 해제(계량 후 판단) ② `_adopts_day_high` 도 `active`
  단독(stale 30초, fail-closed 라 무해 — docstring 만 정정) ③ 형제 관측기 `_maybe_emit_pre_market_
  defer` 의 mark-before-log(관측 전용, 8영역 재승인 필요) ④ T-8 리터럴 가드는 별칭(`time as _t`)
  미검출(기지 한계).

**시정 후보 (기록 — A 채택 / B·C 기각)**
- (A) `_defers_pre_market_exit` 를 **시각 기반 폴백**과 결합 — `active` 가 비어 있고 현재 KST 가
  08:00~09:00 이면 보류로 판정(fail-**closed** 방향). 게이트 목적이 "왜곡 틱 회피"라 보류가
  안전 방향이다. ⚠️ 8영역(`risk.py`) 이라 승인 필요.
- (B) `_boot()` 말미 또는 08:00 task 진입 직전에 `session_tracker.tick()` 강제 1회 — scheduler
  변경이라 라인 상한 가드 확인 필요.
- (C) 관측만 — 첫 청산 로그 타임스탬프가 09:00 이전이면 WARNING(현행 cap 이 이미 시각을 남김).

**판독 채널** — cycle237 cap 이후에도 `도치안 시간 기반 청산` 의 **첫 발화 시각**이 그대로
남으므로 09:00 이전이면 이 결함의 증거다(버스트 크기는 잃지만 시각은 남는다).

---


## 🔴 월요일(2026-08-31) 아침 최우선 — `257720` VB 주말 오버나잇 (cycle232 자문 부속 발견)

`257720`(실리콘투, VB 2주/51,050원, 08-28 09:15 매수, `status=PARTIAL`)이 **주말 오버나잇 보유 중**.
VB 는 15:20 전량청산 전략이라 **오버나잇 손절 규약이 설계에 없다** = 무통제 포지션(계좌 3.9%).
1차 판단 = cycle229 가 시정한 `[단일가매매]` 미분류 매도 거부(3회 재시도 후 **무기록** 포기)의
시정 **전** 마지막 희생자 — 08-28 15:20 청산 시도가 cycle229 배포(15:40+) 직전이었다.

**사용자 결정(08-29): 월요일 09:00 즉시 청산 — 절차 정본 = `_workspace/monday_0831_guide.md`.**

**⚠️ 08-29(토) 로그 실측으로 자문 §5 가설 반증** — 15:20 강제청산은 정상 발화했고("대상:
['035420','257720']"), 실패 원인은 `[단일가매매]` 가 아니라 **APBK0400 "주문 가능한 수량
초과" ×3 → CRITICAL**. 근본 = BUY `0000411400` 이 **PARTIAL 2주** 체결인데
`positions.quantity=3`(주문수량) 잔존 → 3주 매도 시도 → 실보유 2주라 거부.
**월요일 15:20 자동 재청산도 같은 이유로 재실패 확정** → `manual-sell {"ticker":"257720",
"quantity":2}` (실보유 수량!) 이 유일 확실. 사후 = positions 잔량 1 유령 정리 확인.

**신규 결함 2건**:
- **N1 — ✅ cycle235 시정 완료(08-29, 커밋 대기)**. 근본 = handler 가 체결수량을
  `fields[16]`(ODER_QTY 주문수량)으로 오독(주석이 KIS 정본과 반대) — 단일 전량 체결에선
  잠복, 부분/분할에서 positions 과대. 시정 = ①`fields[9]`(CNTG_QTY) 정본 전환 ②엔진
  overrun 클램프(`[fill_qty_overrun]`, 증분 동반 캡 = 손익 정합) + `quantity<=0` drop
  (`[fill_qty_zero]`) ③강제 UPDATE WHERE PENDING+PARTIAL 포괄(N1-b). 적대 검증 확증 4
  전부 시정. 8영역 승인 = handler·order_engine 한정(sha 핀 4가드, 커밋 시 자기소멸).
  **후속 후보(행위 결정 사안)** = 전량 체결 분기의 잔여취소 타이머 해제 + 1차
  update_trade_status 의 PARTIAL 포괄(C235-V2) · `_completed_orders` 일일 리셋 확인(C235-R3).
- **N2 — ✅ cycle236 시정 완료(08-29, 커밋 대기)**. `is_sell_qty_exceeded`(APBK0400 ∧
  "수량"·"초과") + `execute_sell` #1.5 잔고 재대조 4분기(오염=held 보정 자기 치유 /
  잠김=보존+`_selling` 유지 / 실보유0=insufficient / 실패=graceful). insufficient 흡수
  금지가 계약(부분 보유 감시 이탈 차단). 적대 검증 확증 4 전부 시정(C236-F1 held 대조).
  스펙 `_workspace/red/cycle236_sell_qty_exceeded_spec.md`. **잔여 LOW 후속 후보** =
  대출일별 다중 row 잔고 집계(C236-F4) · manual-sell 라우트 분류 미적용(N2-R5, 수동
  매도는 실보유 지정이라 실위험 낮음).

---

## cycle232 · 리스크 통제 3의제 검토 — ✅ 사용자 결정 완료 (2026-08-29, 구현 대기)

터틀 원전 대사 보고서(https://claude.ai/code/artifact/5cd3fe2d-e405-4911-866c-74f03c1bf3a2)의 액션 1·2·3 을
검토(사실 조사 3축 + domain-consult `_workspace/domain_consult/cycle232_risk_control_review.md`) 후 **전부 자문 권고안 채택**.

| 의제 | 결정 | 구현 |
|---|---|---|
| **G3′ 계좌 통합 통제** | **자문 권고 패키지 착수** — ⓪척도 병기(프록시+실효, 관찰 전용) ①SOFT Σ상한 다크런치(관측 4%/차단 6%, 임계 비활성→2주 후 DB 활성, HARD 금지). Σ상한=순간 게이트/드로다운=일 래칫 **이원 설계**(D1). fail-open+LOUD(D2). 1주 폴백 notional 초과는 **관측만** `[oversized_fallback]`(D3). 드로다운 3층은 **다음 사이클**(입출금 보정 선행) | **✅ cycle233 구현 완료 (2026-08-29) — 커밋 80f164c·배포 완료(08-29, EC2 반영).** 스펙 `_workspace/red/cycle233_account_risk_spec.md` · 적대 검증 21→확증 6 전부 시정(HIGH 2 = 자기 가드 공허, 뮤테이션 실증) · 백엔드 **5,818 PASS** · 8영역+scheduler diff 0(라인 상한 가드로 감시자를 자기 종료 루프로 설계). 활성화 = 2주 관측 후 DB `account_risk_block_pct=6.0` 한 줄. **✅ cycle239 선결(신선도) 시정 (2026-09-02) — 활성화 게이트 충족**: `is_soft_gated()` 가 `_gate_active` 만 돌려줘 감시 루프(5분) 사멸·hang 시 마지막 판정이 **동결**(block 로 얼면 7전략 신규 매수 영구 차단)되던 결함을 **900s(=3×주기) 초과 stale → fail-open(False) + `[account_risk_gate] released reason=stale` WARNING 1회/일**(cap `gate_stale`, peek→로그→mark) 로 닫았다 — 스펙 `_workspace/red/cycle239_gate_freshness_spec.md`. `get_gate_state` 4키(`stale/age_secs/stale_max_secs/effective_gated`, `level` 은 마지막 평가값 보존 = 동결 서명 `level=block ∧ stale ∧ !effective_gated`) + `ensure_watch_loop` done_callback LOUD(`[account_risk_watch_loop_died]` WARNING / `_loop_exit] reason=running_false` INFO 매일 1건). 적대 검증 확증 10(실질 4) 전부 시정(R1 = 기록자 `was_active` 원시값 환원(매 아침 부팅 거짓 stale WARNING + cap 선소비 차단) · `gate_stale` cap 키 독립 F-8c · G-239-7 전 트리 diff 가드 삭제 · 판정 예외 fail-closed 변조 검출 F-5b) · 뮤테이션 23종 21 검출 + escape 2 → 신규 회귀로 봉인 · 3,000틱 fresh 차분 0 · 신규 회귀 36 · 8영역+scheduler diff 0 · `account_risk_watcher.py` 단독. **활성화 잔여 조건(AND)** = 배포 후 2영업일 `reason=stale` 0 ∧ `loop_exit reason=running_false` 매일 1 ∧ 장중 `GET /api/portfolio/risk` `account_gate.age_secs ≤ 600` ∧ cycle233 2주 관측 창(~09-12) 만료 → 사용자 결정으로 DB 한 줄. 활성화 D+1 첫 확인 = `transition=entered` 시 대시보드 `effective_gated=true`(행위-관측 정합) |
| **G2 역지정가** | **보류 + 대체 조치** — 착수 게이트 3(스탑지정가 `ORD_DVSN` 스펙 확정 · 모의/소액 실주문 검증 · T1 자본) AND 충족 전 도입 금지. 근거 = KIS 는 스탑**지정가**만(`CNDT_PRIC` 정본) — 갭 관통 미체결 = Defect 2 재현 + 다일 잔존 주문의 체결통보 오귀속("momentum" INSERT 경로). 지금 할 것 = tick blind 총시간/일 계측 + 부팅 직후 청산 평가 우선순위 확인 + **D6 운영 규약 승격**(보유 포지션 有 시 09:00~15:30 push 금지) | 대체 조치 진행(08-29): **D6 승격 완료**(CLAUDE.md 운영 가이드) · **청산 우선순위 확인 완료** — 청산 평가는 tick 기반(`risk.on_tick` 첫 tick 즉시)이라 매수 스캔(09:30) 비의존 + 보유는 07:59 HIGH 사전구독 = 현행 충족, 실사각은 재구독 지연의 tick blind 자체 → **✅ ① tick blind 계측 완료(cycle234, 08-29)** — `uptime_monitor.py`(60s 하트비트 + `[tick_blind_boot]` + 20:10 `tick_blind` metrics). **G2 대체 조치 3건 전부 종결.** G2 재검토 = `market_blind_secs_total` 주간 분포 실측 후. 재검토 트리거 = `_pending_next_day_clear` 미집행 실측 1회 |
| **G1 risk_pct 0.5→1.0%** | **보류 — T2 재분류.** 해제 게이트(AND) = net≥500만 ∧ kojiro·donchian 각 N≥20 TE>0 ∧ 상관군 캡 활성(`max_open_risk_pct` 4.5→9 동반 — 로드맵 규칙 4). 근거 = 체결 ~70% 1주 폴백 무관 + 효과 비단조(저가주 편향) + kojiro 동시 유닛 4.5→2.25 반토막 | 코드 변경 0 — 문서 등재만 |

**자문의 전제 정정 3**(보고서 반영 완료): ①"1유닛 고정=R15 초과달성" 불성립(1주 폴백이 4유닛 초과 생성)
②리스크 척도 이원(프록시 60,713 vs 정밀 미측정 — 월요일 장중 `GET /api/portfolio/risk` 실측 필요)
③머신 슬립은 로컬 사건(EC2 사각 과대평가 금지).

**cycle239 후속 등재 (신선도 시정 범위 밖, 2026-09-02 — 스펙 §8)** — **A. 평가 타임아웃(우선순위 1)**: `run_account_risk_watch_once` 본체를 `asyncio.wait_for(…, timeout=300)` 로 감싸 hang → TimeoutError → 기존 fail-open+스탬프 갱신+`watch_failed`, 루프 생존. stale 규칙은 ≤900s 거짓 차단을 허용하는 완화책이지 hang 자체를 못 푼다. 선행 검토 = cancel 시 KIS `_semaphore`·토큰 락·`pg._pool.acquire()` cancel 안전성 · **B. 재스폰 경로**: `ensure_watch_loop` 2번째 호출 지점(`uptime_monitor.heartbeat_loop` idempotent 호출 또는 done_callback 내 일 cap 3) — hang(done()=False)엔 무력, A 선행 · **C. `uptime_monitor` 동형 결함**: 하트비트 루프도 무감시 태스크 — 동일 done_callback 적용 · **D. `scheduler.py:962-985` cycle146 주석 거짓**: `except` 안 `return` 도 `finally` 를 탄다 → 장중 KIS 5xx 1회 = 전면 teardown → run_daily 60s 재부팅(1~5분 tick blind, cycle234 `[tick_blind_boot]` 로 실측 가능). scheduler 소관 별도 결정 · **E. `pg._pool.acquire()` 타임아웃 미지정**(`db/pg.py:128`) — hang 의 공통 뿌리 · **F. 프론트 `PortfolioRiskCard`** `account_gate` 미표시 → `stale`/`effective_gated` 배지 + `age_secs`(`types/portfolio.ts` 동기 의무) · **G. 20:10 리포트 `account_gate` 병기**(`log_analysis_engine._build_portfolio_risk_snapshot` 1줄, 장중 liveness 결정 표본 — 이번 미채택).

---

## P0-1 · BFB·VCP 가 존재하지 않는 키를 읽어 매수가 구조적으로 불가능하다

### ✅ 시정 현황 (2026-08-25 사이클 227 — Stage 0 구현 완료·미커밋)

- **결정 (사용자, 2026-08-25)**: ① 방향 **A-raw** + 8영역 승인(handler.py·risk.py 한정)
  ② **Stage 0 관측 우선** — 게이트 행위 변경 0, 배관+`would_pass` 로그만 ③ 비중 현행 유지
  (BFB 0.15/VCP 0.10 — 다크런치는 Σ 정규화 위험 이전이라 반대, 자문) ④ P0-2 동반.
- **자문 판정** (`_workspace/domain_consult/bfb_vcp_acml_vol_gate.md`): 방향 B(전일 확정치)
  **폐기** — 전일은 플래그/베이스 수축 구간이라 통과 확률 ~0 = 결함 재생산. **게이트 전환 시
  P1-3 충족 래치 동반 필수** — 래치 없이 A-raw 만 켜면 BFB 통과율 0% 예상(역선택).
- **구현** (명세 `_workspace/red/cycle227_acml_vol_stage0_spec.md`, 검증
  `_workspace/test_report_cycle227.md` **GO**): handler `fields[13]`(ACML_VOL) 파싱 →
  `on_tick(*, acml_vol=-1)` → 신규 leaf `src/engine/tick_volume.py`(KST 날짜 자기 리셋,
  미관측 None — sentinel 0 금지). BFB/VCP 게이트 **직전** 관측 훅
  `[bfb_vol_gate_observe]`/`[vcp_vol_gate_observe]` (cap 1회/(ticker,outcome)/일 +
  `_scan_stats` 3카운터). **기존 게이트 블록 byte 불변**(AST-2 봉인) — 매수는 여전히 차단.
  백엔드 5,617 PASS/실패 0.
- **게이트 전환 판정 기준** (1~2영업일 관측 후): 주 3건↑ would_pass = 전환 진행 /
  **0건 = P1-3 래치 선행 필수** / 일 10건↑ = 스코프 불일치 등 재조사.
- **✅ 관측 결과 (2026-08-26~27 이틀 실측, 2026-08-27 16:00 판정)**:
  배관 정상 — 게이트 평가 5회 전부 실측 acml_vol 관측(no_obs **0**), `observe_failed` 0, ERROR 0(cycle227 기인분).
  **would_pass = 0/5** ⇒ 판정 기준상 **P1-3 충족 래치 선행 확정**(자문 예측 그대로 — A-raw 단독은 역선택).
  정량 근거 = 관측치/임계 비율: 280360 8%(09:08) · 257720 19%(09:19) · 161890 25%(09:26) ·
  001450 40%(10:00) · **357780 70%(12:25)** — 시각이 늦을수록 임계에 접근 = 래치(완주 후 재평가 유지) 도입 시
  통과 발생이 정량적으로 예고된다. 컨텍스트 = 8/26 돌파 1차 감지 247 vs retention 완주 4(진동이 완주를 깎음 — P1-3 동일 뿌리).
  VCP 는 후보 0(final_prepared=0)이라 관측 0 — 자문 예측 범위("몇 주 무체결 가능"), 관측 계획은 BFB 중심 유지.
  Stage 0 불변식 확인 = BFB·VCP 8/26 이후 체결 **0건**(게이트 byte 불변 정상 작동).
- **전환 사이클 의무**: 은폐 테스트 3파일 손주입 → tick_volume 주입 의미 전환(주석 마커
  11곳) + AST-2 pin 의미 전환 + 8영역 sha 핀 4항목 자기소멸 확인 + 비중/디리스크 재확인.
- 인지된 노이즈원(자문 §B): H0UNCNT0 통합 누적(NXT 프리 포함) vs 일봉 J(KRX 단독) 스코프
  불일치 + 다중 레코드 프레임 첫-레코드 과소 계상 — 정합화는 행위 변경이라 별도 사이클.

### 사실 (직접 재확인 완료)

```python
# src/engine/strategies/bull_flag_breakout.py:846-850
info_price    = ticker_prices.get(ticker, {})
acml_vol      = int(info_price.get("acml_vol", 0) or 0)              # ← 항상 0
vol_threshold = int(info["flag_avg_volume"] * breakout_volume_mult)  # ← 항상 ≥ 1
if acml_vol < vol_threshold:
    return Signal.NONE                                                # ← 무조건 실행
```

`src/engine/strategies/vcp_breakout.py:955-961` 동형.

- `scanner.ticker_prices` 에 값을 넣는 **유일한 대입부**는 `src/engine/risk.py:397` 이고
  **4키만** 쓴다 — `current_price` / `open_price` / `change_rate` / `prdy_ctrt`.
- **`acml_vol` 을 `ticker_prices` 에 쓰는 코드가 전체 소스에 없다.**
  WS 핸들러(`src/realtime/handler.py`)도 체결 payload 의 누적거래량 필드를 파싱하지 않는다.
- `prepare()` 가 `flag_avg_volume > 0` 을 강제하므로 임계는 항상 1 이상
  (2026-08-25 실측 48건 = 12,775 ~ 3,628,183).
- 라이브 API 응답 키 출현: `acml_vol` **0회** vs `current_price` **115회**.

⇒ `0 < threshold` 가 **항상 참** ⇒ `check_buy_signal` 이 **구조적으로 `Signal.BUY` 를 반환할 수 없다.**

### 실측 증거

- 7전략 중 이 키를 읽는 **두 전략만 정확히 전 기간 체결 0건** (BFB 0 / VCP 0, 나머지 31~203).
- 2026-08-25 BFB: 후보 **48건** 준비, retention **21회 이상 완주**, 매수 신호 **0**.
  완주 경로(`:829` pop)가 무로그라 그동안 보이지 않았다.
- `CLAUDE.md` 의 기존 귀인 **"BFB·VCP 체결 0 = 진입 조건 미통과 탓"은 반증됐다.**
  조건은 오늘 하루만 21회 이상 충족됐다.

### ⚠️ 왜 지금까지 안 잡혔나

**회귀 테스트가 결함을 은폐하고 있다.** 아래 테스트들이 `ticker_prices` 에 `acml_vol` 을
**손으로 주입**해서, 테스트는 통과하는데 프로덕션은 절대 매수하지 못한다.

- `tests/unit/engine/strategies/test_bull_flag_breakout.py` (:118-124, :147-150, :196-197, :209-210)
- `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py` (:59-60, :82-83, :109-110)
- `tests/unit/engine/strategies/test_vcp_breakout.py` (:145, :167, :215, :228)

**시정 시 테스트도 반드시 함께 고친다.** 그러지 않으면 시정이 검증되지 않는다.

### 시정 방향 (택1 또는 병행)

**A. 실시간 누적거래량을 흘린다**
핸들러가 체결 payload 의 누적거래량을 파싱해 `on_tick` **키워드 인자**로 전달
(사이클 222-a 의 `day_high` 가 정확히 같은 패턴 — 그 선례를 따르라).

> ⚠️ **`ticker_prices` 에 주입 금지.** `donchian_swing.py` 가 같은 dict 에서 고가 키를 읽고 있어
> (`daily_high = max(stck_hgpr, high_price, current_price, open_price)`),
> 키가 채워지면 `ext_pct` 과열 가드가 켜져 **donchian 매수 행위가 바뀐다.**
> `risk.py` 의 관련 주석과 AST 가드가 이미 이 커플링을 경고하고 있다.

**B. 컷을 전일 확정치 기준으로 재정의**
`stock_master.raw.acml_vol` / `stock_master_daily` 기준. 장중 누적 vs 일평균 비교는
09:05 시점엔 구조적으로 불리하다(하루가 시작도 안 했는데 일평균과 비교).

### 🚨 배포 전 반드시 결정할 것

**이걸 고치면 두 전략(비중 합 25%)이 갑자기 매수를 시작한다.**
실체결 표본이 **전 기간 0건**이라 검증된 적이 없는 전략이 한 번에 열린다.

- 한 번에 열 것인가, **다크런치(비중 극소)로 관찰부터** 할 것인가?
- ⚠️ 비중을 **0 으로 내리지 말 것** — `registry.enabled()` 이탈로 손절 평가가 정지한다
  (`enabled` 축 독트린, 아래 참조).
- 체결 확보 전까지 **진입 임계 재튜닝 금지** — 표본 해상도가 파괴된다.

---

## P0-2 · stale universe 가드가 후보 40%를 당일 영구 축출한다

### ✅ 시정 현황 (2026-08-25 사이클 227 — 구현 완료·미커밋)

안전조건 소스를 진짜 당일 누적으로 교체: ① tick 관측(`tick_volume`) 우선 ② 부재 시
`inquire_acml_vol`(FHKST01010100, 화이트리스트 기존재 — FHKST01010300 응답엔 `acml_vol`
부재 확인) REST 폴백 ③ 둘 다 부재 → **제외 보류**. `[universe_excluded]` 에
`acml_vol=… vol_source=tick|rest` 병기. 임계 10,000·보유/익일청산 절대 보호 불변.
**✅ D+1·D+2 실측 확증 (2026-08-27)**: 축출 **85건(8/25) → 1건(8/26) → 0건(8/27)**.
8/26 유일 1건(004800)은 `vol_source=tick acml_vol=3,442` = 진짜 저유동 — 가드가 설계
의도("거래가 실제로 빈약한 종목만 축출")대로 복원됐다. BFB 후보 구독 상실 축도 소멸
= would_pass 관측이 "게이트 탈락" 단일 축으로 해석 가능해졌다.

### 사실

- 2026-08-25 BFB 후보 48 중 **20건(41.7%) 미구독**.
- 원인은 슬롯 부족이 **아니다**(아래 반증 참조). `_universe_excluded_today` 축출이다.
- `[universe_excluded]` 로그 46건 중 이 20건 전부 매칭 (`reason=stale_6plus_low_volume`, ~10:01,
  `today_volume` 254~6,197).
- 필터링 지점 = `src/engine/scheduler.py:1740-1745`
  (`if excluded: tickers = [t for t in tickers if t not in excluded]`).
- **BFB·VCP 는 `_SWING_POLL_STRATEGIES` 비멤버**라 REST 폴 보강이 없다
  (`scheduler.py:144` = `("donchian_swing", "kojiro")`).
  ⇒ **미구독 = 매수 평가 완전 상실**(donchian/kojiro 는 60초 REST 폴이 받쳐준다).

### 근본 결함

가드의 "거래량 빈약" **안전조건이 실질 무력화**돼 있다.
`today_volume` 이 최근 ~30 체결의 합이라 임계 `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 을
사실상 항상 충족한다 ⇒ 가드가 **"스테일 6회 → 무조건 축출"** 로 퇴화했다.

### 시정 방향

안전조건을 **진짜 당일 누적거래량**으로 교체(`stock_master.raw.acml_vol` 또는 `FHKST01010100`).
대량 동시 축출 버스트는 배관 장애 신호로 보고 별도 판단.

---

## P1 · 관측을 가리거나 자원을 낭비함

### P1-3 · BFB retention 진동 — 로그의 42% 점유

- 2026-08-25 2시간 로그 1,753행 중 **738행**이 한 종목(`001450`)의 왕복.
  `BFB 돌파 1차 감지` 374 / `BFB 돌파 후퇴` 364.
- **오늘 실제로 진단을 방해했다** — 로그 상위를 전부 덮었다.
- 원인 셋:
  1. retention 이 **연속 유지** 요구 — 대기 중 한 틱만 `flag_high` 미만이면 즉시 취소
     (`bull_flag_breakout.py:818-822`). 돌파선이 전일종가 근처면 노이즈만으로 무한 재시작
     (001450: `flag_high` 50,800 vs `prev_close` 50,600 = +0.40%).
  2. **완주 후 재무장 불가** — `:829` pop 직후 `_prev_price ≥ flag_high` 라
     `:832` edge-crossing(`prev < flag_high <= current`)이 재성립하지 않는다.
     가격이 돌파선 아래로 내려갔다 와야만 재평가된다.
  3. `_prev_price` 가 `_reset_daily_state`(`:1094-1100`)에서 **청소되지 않아** 일 경계를 넘어 잔존.
- 시정: 완주 후 거래량 탈락 시 `first_seen` 을 pop 하지 말고 **충족 래치**로 유지 +
  `_prev_price` 일일 청소 + 히스테리시스 밴드 검토.

### P1-4 · `silent_inactive` 오판 — 하루 16~24 접속키 낭비

- **매일 08:57 · 15:27 에 8개 세션 동시 강제 재연결.**
  `[silent_inactive_force_reconnect]` — 08-24 3회, 08-21 9회(애프터 포함).
- 가드 조건 = `fresh_ratio < 0.2` + `subscribed >= 5` + **5분 지속**
  (`src/engine/stale_session_recovery.py:24-31`).
  그 두 시각은 **하루 중 거래가 가장 없는 순간**이라, 가드가
  "거래가 없어 조용한 것"과 "세션이 죽어 조용한 것"을 구분하지 못한다.
- 접속키에 **캐시가 없다** — `src/auth/token.py:183` 이 호출마다 `POST /oauth2/Approval`,
  그 호출이 **재연결 루프 안**(`src/realtime/websocket.py:213`)이라 재연결 = 접속키 1개 무조건.
- 시정: 장 상태를 판정에 반영(프리장 단독·마감 직후 제외 또는 임계 완화).
- **2026-08-27 실측 갱신 — 지속·확대 중**: 8/26·8/27 각각 **24건/일**
  (08:58 ×8세션 + 15:27~28 ×8 + **15:39 ×8** — 종전 서술의 2슬롯이 아니라 **3슬롯**).
- ℹ️ **2026-08-25 KIS 메일 폭주의 원인은 이것이 아니다** —
  같은 KIS 계정에 묶인 **다른 계좌 앱키의 외부 배치**였음이 사용자 확인으로 판명.
  이 시스템의 12시간 인증 호출은 토큰 7 + 접속키 17 = **24건**뿐(DB·컨테이너 로그 일치).

### P1-5 · VB 15:30 종가 매수 발사 + APBK3013 [단일가매매] 미분류 — ✅ cycle229 종결 (2026-08-28)

> 시정 = VB·momentum 매수 컷 **15:20**(`BUY_CUTOFF_KST` 모듈 상수·KST 명시·check_buy_signal
> 최상단·상태 무갱신, `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일) + `[단일가매매]`
> 변형 `is_market_order_disallowed` 편입(주 실익 = 매도 무기록 포기 경로 → step_down
> 지정가 폴백+TTL). 부수 = 무-freeze 레거시 테스트 6곳 장중 KST 동결(벽시계 독립 확보).
> D+1(월) 확인: `[callback_exception]` 15:30 대 0건(의미 반전 — 있음→없음이 정상) +
> `[selling_reconcile]` 빈도(지정가 매도 미체결 잔존 감시). 상세 자문 = 아래 정정 블록.

- **실측**: 8/20 ×2 · 8/21 ×1 · 8/25 ×4 · 8/27 ×2 — 전부 **15:30:0x~2x**. 체인 =
  VB 매수 신호(예: 8/27 15:30:20 에코프로 086520 "현재가 92,000 ≥ 목표가 90,050") →
  시장가 SOR 1주 매수 → APBK3013 `[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선
  취소 주문만 가능합니다` → **이 msg1 변형이 `is_market_order_disallowed` 키워드 미매칭**
  (기존 키워드 "지정가 및 최유리"가 중간 "(신규/정정/취소)" 삽입으로 substring 미성립) →
  KisApiError 가 `on_tick` 밖으로 전파 → `[callback_exception]` → **WS 재연결**(G-REJECT-1
  설계상 의도된 전파이나, 15:30 마다 1~4회 재연결 churn + 그 순간 보유 종목 시세 감시 공백).
- **⚠️ cycle227 무관 확증** — 8/20 부터 존재(8/25 발생분은 cycle227 배포 19:30 *이전* 15:30).
  8/26 15:40 `[애프터마켓]` 변형은 기존 키워드에 매칭돼 정상 폴백(무예외) — 변형별 갈림 실증.
- **🚨 단순 키워드 추가 금지 — 시간 가드 선행** (자문 `cycle229_vb_1530_single_price.md`,
  2026-08-28 **전제 정정 포함**): ~~"15:20~15:29 연속매매에서 우연히 K-돌파가 없었다"~~ 는
  **반증** — 그 구간은 KRX **장후 동시호가(종가 단일가)** 다(`session.py::is_call_auction_now`
  사이클 162/182 가 이미 그렇게 판정, 6/17 15:21:48 `fresh=0/10` 실측 = 평가할 틱 자체가
  구조적으로 희박). 15:30:0x~2x 에 몰린 9건은 **랜덤엔드 체결로 확정 종가 1틱이 흐르며
  15:19 마지막 연속체결가 대비 점프 → edge-crossing** 생성이 원인. ⚠️ 종가 단일가는
  **시장가 호가를 접수**한다(15:20 강제청산 시장가 매도가 작동 중인 것이 방증) — 15:2x
  VB 매수는 "거부되는" 게 아니라 **종가로 체결돼 오버나잇**된다(우연한 안전판 없음).
  시정 = (a) VB·momentum 매수 컷 **15:20**(명시 시각 모듈 상수·KST — 보드 결합 금지,
  momentum 종가 확정 틱 +29% 는 "상한가 잠금 실패 마감" 표본이라 원 가설의 반대) +
  (b) `[단일가매매]` 변형 `is_market_order_disallowed` 편입(정당화 축은 **매도** —
  미분류 매도 거부는 3회 재시도 후 무기록 포기(`order_engine:815~828`)라 랜덤엔드 창
  청산 실패가 기록조차 안 됨. 낮은 매도 지정가는 단일가 세션 유효 주문 = 폴백이 정확한
  처방. 잔여 매수 경로는 LTV 야간 다운그레이드→시간외단일가뿐). 8영역 무접촉 달성 가능.
- 부수 미규명 1건: 8/24 09:46:49 `[callback_exception] ticker=377300` — 15:30 패턴과 다른
  시각. 별도 규명 필요(단발).

### P1-7 · 5분 우선 재구독 핑퐁 (08-31 포렌식 확정 결함 ⓑ, MEDIUM) — ✅ cycle240 종결 (2026-09-02, 커밋 대기)

> 시정 = `resubscribe_stale_priority`(`_scan_loop` 5분, cap=10)의 **LOW 후보만** desired 집합
> (breakout `_collect_breakout_tickers()` ∪ momentum `scanner._last_scan_result`)과 교집합.
> HIGH(보유 ∪ 익일청산)는 `low_targets` 에 애초에 없어 필터 경로를 지나지 않는다(구조적 면제)
> + HIGH 수집 예외 시 게이트 off(이중). 활성 게이트 = breakout 비어있지 않음 ∧ HIGH 수집 무예외
> — off 면 **현행 byte 동일(fail-open)**. `src/engine/stale_watcher_core.py` 단독(+61/-4),
> 8영역·scheduler.py(3,999L)·facade diff 0. 스펙 = `_workspace/red/cycle240_resubscribe_desired_filter_spec.md`.

- **실측(EC2 read-only, UTC 저장 +9h)**: 09-02 09:40 `[stale_priority_resubscribe]` 9종목 →
  09:45 `[scan_loop_delta] unsubscribed=` **동일 9** → 10:00 RESUB → 10:05 DELTA … 1:1 무한 페어링.
  `034020` 은 09:00:29 매도 후 **19:59 까지 35회** 재구독. 종목언급/행수 = 09-01 **993/115**,
  09-02 **843/108**. `[scan_loop_delta]` 09-02 **222행**. `cap_exceeded` 0건(HIGH 가 cap 을 넘은 적 없음).
- **원인**: stale 후보 소스가 `scanner.ticker_last_tick.items()` **전수**(`stale_watcher_core.py:449`)
  — 그 dict 는 per-ticker pop/del 이 src 전체 0건, 유일 정리 = 20:10 정산 `_reset_daily_state` 의
  `clear()`. 09:00 에 한 번 tick 받은 종목은 매도·후보 이탈 후에도 20:10 까지 stale 자격 유지.
  형제 `check_and_resubscribe_stale`(120s)은 소스가 `get_subscribed_tickers()`(구독 집합 한정)라
  같은 결함 없음 = **비대칭이 뿌리**. cycle216 LOW throttle 180s < 300s 주기라 구조적으로 못 막고,
  universe 가드 평가 대상이 `new_set` 한정이라 되살아난 종목엔 자동 수렴 경로 0.
  LOW 라 메인 41 하드리밋은 안 깨지지만 구독 슬롯·KIS SEND 낭비 + 로그 오염 +
  `_stale_last_resubscribe_at`(throttle/force_retry 타임스탬프) 오염.
- **설계 결정(사용자 위임 — team-leader 권장안)**: ① desired = `new_set ∪ NDC` 동치 정의(같은
  try 블록·같은 이터레이션 — 필터가 `_scan_loop` 자신이 구독하려는 종목을 자를 수 없다) ②
  `kis_ws_pool.get_subscribed_tickers()` 는 desired **부적격**(cycle215/217 "미구독 split-brain
  종목 재구독" 계약 무력화 — F-12 실증) ③ 스윙 후보 **제외**(넣는 순간 대표 피해자 매도 완료
  donchian/kojiro 가 desired 로 부활) ④ momentum 은 **가산 전용·게이트 불참**(모듈 전역 잔여값이
  기존 LOW 회귀 23파일을 순서 의존으로 깨는 방향 = 덜 허용적, 활성 판정은 scheduler 소유 소스에만)
  ⑤ `ticker_last_tick` 잔존은 이번 무접촉(소비처 8곳, pop 자연 위치 = `order_engine` 8영역 → 후속 A)
  ⑥ 순서 = 분리 → **필터** → cycle216 A(동시호가) → B(throttle) → cap(유령이 cap 10 을 소비 못 함).
- **관측**: `[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d filtered_not_desired=%d
  filtered_sample=%s`(기존 INFO 1행 확장, `count=` 첫 필드 byte 보존, sample ≤10, 신규 마커 0·cap 0
  — 행 빈도 5분 1행 불변). `filtered_not_desired` 는 하루 누적 유령 수(30~80 이 **정상**).
- **부수 시정**: cycle222a `test_a11b_stale_watcher_core_untouched`(bare `git diff HEAD` **영구 동결**
  — 사이클 한정 스코프 가드가 수명을 넘겨 stale watcher 의 모든 후속 시정을 무조건 RED)를 내용 검사
  `test_a11b_stale_watcher_core_no_anchor_coupling`(앵커 토큰 `day_high`/`stck_hgpr`/`high_price` 0)로
  재스코프 + cycle222a3 `_GIT_HELPER_FILES` 목록 동기(`_git` 헬퍼 삭제 반영).
- **적대 검증**: 3렌즈 발견 5 → 실질 1 = F-8 **테스트 픽스처 결함**(`_capture_scheduler_warnings()`
  가 `src.engine.scheduler` 로거 레벨을 WARNING 으로 올려 caplog INFO 를 삼킴 → `IndexError`;
  **구현은 무결함** — 캡처된 `low=1` 이 이미 필터 통과분으로 정확) → caplog 단일 캡처로 교체(src 변경 0).
  뮤테이션 **21종 중 20 KILLED / 1 ESCAPED**(m5a — `resubscribed.append`/`_stale_last_resubscribe_at`
  가 `subscribe` 성공 **전** 스탬프: cycle240 diff **밖** 사이클 28/216 기존 루프 = 기존 커버리지 공백,
  후속 H). 차분 실증 **2,300 조합 0 불일치**(A 게이트 off·desired ⊇ LOW 1,000 조합 HEAD byte 동일 /
  B 무작위 1,000 조합 차이는 desired 밖 종목뿐·HIGH 탈락 0 / C 게이트 off 300 조합 HEAD 동일).
- **D+1 판독 채널**(⚠️ **의미 반전** — `count` **감소가 정상**, 배포 전후 같은 grep 합산 금지):
  | 채널 | 정상 서명 | 이상 서명 |
  |---|---|---|
  | `[stale_priority_resubscribe]` | 장중 `desired_low>0` · `filtered_not_desired≥1` 대부분 사이클 · 종목언급 09-01 993 → **<50/일**, 대부분 `count=0` | 장중 `desired_low=0` 지속 = 게이트 off(4 돌파 전략 후보 0 또는 registry 이상) / `count` 종전 수준 = 필터 미작동 |
  | `[scan_loop_delta] unsubscribed=` | 매도·후보 이탈 시점에만(09-02 222행 → 수십 행), 직전 RESUB 와 1:1 페어링 **0** | 페어링 재출현 = desired 소스 누락(어떤 전략 후보가 desired 밖) |
  | 페어링 SQL | RESUB tickers ∩ 5분 뒤 DELTA tickers = ∅ | ≠ ∅ → 해당 종목 소속(전략·상태) 추적 |
  | `[stale_watcher_detail]` | `stale=`/`r=` 감소(유령의 5분 점유 소멸) | 불변 = 120s 형제 경로 독립 결함(후속 F) |
  | `[stale_priority_resubscribe_cap_exceeded]` | 0 유지 | ≥1 = HIGH>10(필터 무관, 보유 급증) |
  | HIGH 회귀 | `/api/realtime/subscriptions` 보유 종목 fresh 비율 불변 · 매도 후 `[unsubscribe]` 정상 | 보유 종목 stale 증가 = HIGH 경로 훼손 → **즉시 롤백** |
- **후속(이번 사이클 밖)**: A `ticker_last_tick` 매도 시 pop(`order_engine._unsubscribe_if_no_other_strategy`
  8영역 승인 + 소비처 8곳 영향 평가, 이번 시정으로 무해화 = P3) · B `_scan_loop` `new_set` 에 NDC 부재
  (`scheduler.py:2457`, 부팅 복구 창 delta 해제 잠재 — 순증 0 편집 필요) · C 사이클 한정 bare `git diff`
  영구 동결 가드 수명 감사(`test_cycle223f:236`·`test_cycle223:325` 잔존 → sha 핀 자기소멸 또는 내용 검사)
  · D `[scan_loop_delta]` `reason` 축 · E universe 가드 평가 대상 `new_set` 한정(관측) · F K watcher(120s)
  subscribed∖desired 재등록(≤5분 창, `[stale_watcher_detail]` 불변 시 카드) · G `scanner._last_scan_result`
  공개 접근자(8영역) · **H** m5a 순서 보정(`resubscribed.append`/타임스탬프를 `subscribe` 성공 이후로 —
  다음 `stale_watcher_core` 접촉 사이클, tester 사본 테스트 `test_cycle240_tester_m5a_stamp_after_success.py`
  실트리 미추가).

---

## P2 · 정확성 · 잠재 위험

### P2-5 · kojiro `_held_stage3` stale True — ✅ cycle231 종결 (2026-08-29)

> 시정 = 플래그를 `(판정 수행일, bool)` 로 전환, 소비처는 **오늘 판정만** 인정(stale True
> 억제 + `[kojiro_stage3_stale_skip]` age 1=INFO/≥2=WARNING, cap 1회/ticker/일).
> `:649` fail-open 계약을 prepare·소비 축까지 통일한 것 — §1·§2·§4 가 방어. 자문 정정 2 =
> cycle225 게이트는 donchian 것(kojiro recompute 는 전수 순회, 실스테일 경로 = 07:59/16:20
> 재-prepare) + ATR 밴드 **상한** 이탈(급등 종목)이 마킹을 못 받는 경로. 부수 방어 =
> `:685` buy_date 비교 try 밖(cycle226 L-2 동형, 잠복) isinstance 가드. Red 가 추가 실증한
> 현행 결함 = 소비처가 비어 있지 않은 튜플을 전부 참으로 읽음(`(오늘, False)` 도 발화).
> 자문 한계 명시 = 다수 케이스에서 하루 늦은 청산 실비용(kojiro 저승률·고RR 라 유리한
> 교환 — **고승률·저RR 전략에 복사 금지**) + `[kojiro_stage3_exit]` 표본 ~20건 시 §3
> 존재 가치 재검정. 자문 = `cycle231_kojiro_stage3_stale.md`.

`prepare()` 경로는 실패 시 `False` 를 **쓰지 않는다**. ATR 밴드 이탈·스테이지 판별 불가로
중간에 걸리면 **직전 값이 그대로 남는다**(`kojiro.py:393-401` vs `:664-668`, `:701-703`, `:742`).
어제 `True` 였던 종목이 오늘 데이터 열화로 재판정되지 못하면
**가격과 무관하게 즉시 `TRAILING_STOP`** 이 나간다. fail-open 이 아니다.

### P2-6 · BFB 진입창 naive 시각 + 좀비 타이머 — ⚠️ 좀비 타이머 축은 cycle228 부분 종결

> cycle228 이 `_breakout_first_seen` 에 일 경계 스테일 자기 방어(진짜 롤오버 시 clear,
> `_roll_gate_day_if_needed`)를 넣어 "익일 09:05 elapsed 수만 초 → retention 즉시 충족
> 우회" 축은 닫혔다. **잔여 = naive 시각 비대칭**(`:794` `datetime.now().time()` vs
> `:801` KST — 컨테이너 TZ 의존)과 `scheduler.py:2984` 스윙 폴 시간 가드 동형.

- `bull_flag_breakout.py:794` 가 `datetime.now().time()`(naive), 두 줄 뒤 `:801` 은
  `datetime.now(KST)` — **같은 함수 안에서 비대칭**. 컨테이너 `TZ=Asia/Seoul` 에 의존.
- 시간 가드가 retention 블록보다 **앞**이라 12:59:58 등록분이 영구 동결된다.
  익일 09:05 에 `elapsed` 가 수만 초라 retention 이 즉시 "충족" 처리되는 **우회**가 생긴다.
- `scheduler.py:2984-2989` 의 스윙 REST 폴 시간 가드도 동일하게 naive.

### P2-7 · `[day_high_scope_skip]` 문구가 grep 을 모호하게 함

note 본문이 교차 판별자로 `[day_high_adopted]` 를 언급해, 단순 substring grep 이
두 마커를 구분하지 못한다. **2026-08-25 실제로 4건을 114건으로 오집계**했다.
정밀 매칭은 `'[day_high_adopted] strategy='` / `'[day_high_scope_skip] ticker='`.

### P2-8 · F-E 잔여 코호트 관측

2026-08-25 실측: **110종목**이 첫 MAIN 관측 시 당일고가가 프리장(`hgpr_hour=08시대`)에 있었고,
09:47 시점 **3종목만** 전환. 보유 7종 중 4종이 걸렸고 3종 미전환 =
그 시간 동안 사이클 222-a 의 blind 내성이 꺼져 있었다.
며칠 관측해 규모를 확정한 뒤 대응을 정한다(현재는 fail-closed = 안전 방향).

---

## P3 · 사람 결정이 필요함

### P3-9 · `prepare()` 관용 읽기 — 매수를 넓히는 방향

`prepare()` 가 `stck_hgpr` 만 읽어서, `_extract_raw` 가 `raw` 없는 row 를 그대로 반환하면
(`src/db/stock_master_daily.py`) `0` 을 읽는다. `high_price` 도 수용하면 해결되나
**매수를 넓히는 방향**이라 사람 결정 사안으로 남겼다.
현재 **잠복** — 일봉 writer 가 `raw` 를 항상 저장하고 라이브 샘플도 전부 보유였다.
사이클 226 이 안전 방향 3중 방어(후보 거부 · 재도출 자가치유 · 폴백 가시화)만 닫았다.

### P3-10 · cycle221 슬롯 축 — ✅ cycle230 으로 채택·종결 (2026-08-29)

> 재평가 결론(사용자 결정) = **채택·커밋**. "슬롯 부족" 반증(08-25)은 *BFB 미구독 원인*
> 주장만 반증(실원인 = P0-2 축출), 08-19 실사고(메인 45/41 서버 한도·VI 누수·보유 4종목
> tick blind)는 유효. 적대적 리뷰 "주 목적 미달성"은 불완전 지적일 뿐 — 누수 차단·main_over
> 계측·VI 메인 퇴출은 독립적으로 옳고, P0-2 시정+cycle228 매수 개방으로 구독·보유 압력이
> **재증가 추세**(8/28 구독 144 = 8/25 대비 +30%)라 가치 회복. **잔여 후속(신규)** =
> 메인 헤드룸 관리 — LOW tick 후보의 메인 fallback 이 VI 퇴출로 빈 슬롯을 되채우는 축
> (적대적 리뷰의 미달성 지적 그 자체). 관측 = 신규 `main_over` 필드로 실측 후 판단.

- 미커밋 잔류: `src/engine/scheduler.py +135/-46` + 테스트 6파일.
- 적대적 리뷰 **주 목적 미달성** 판정(VI 를 main 에서 빼도 LOW tick 후보가 슬롯을 되채움).
- **⚠️ 2026-08-25 BFB 조사에서 "슬롯 부족" 전제 자체가 반증됐다** —
  라이브 구독 111/328 = **34% 사용**, 217슬롯 유휴, `[priority_drop]` 08-20 이후 **0건**.
  이 사이클을 계속할지부터 재검토하라.

### P3-11 · donchian 라이브 이탈값 재튜닝

`breakout_fail_n_days=2`(코드 5) · `atr_trail_mult=1.8`(코드 2.0).
사이클 223 S1 봉인 후 **복원 경로는 운영자 수동 DB UPDATE 뿐**.
2026-08-25 에 S1·S2·S3 전부 실측 확증됐으므로, 표본이 쌓이면 재튜닝 판단 가능.

---

## 이번 조사에서 반증된 가설 (다시 파지 말 것)

| 가설 | 판정 근거 |
|---|---|
| "retention 을 못 버텨서 매수 0" | **반증** — 2026-08-25 **21회 이상 완주**. 완주 경로가 무로그라 안 보였을 뿐 |
| "구독 슬롯 부족" | **반증** — 111/328 = 34% 사용, 217 유휴, `[priority_drop]` 0건 |
| "후보 48이 과다해 구독 압력" | **반증** — 08-08 확대 이후 **최저치**(08-13 142 / 08-18 146 → 48) |
| "BFB 가 구독 대기열 후순위라 tail 절단" | **반증** — 병합 순서 **최선두**, `BREAKOUT_LOW_CAP` 은 08-08 제거 |
| "같은 dict 를 읽는 donchian 도 동일 결함" | **반증** — donchian 은 `max(...)` 라 **fail-open**. BFB·VCP 만 fail-closed |
| "수량 산출·예산 클램프가 병목" | **반증** — 애초에 BUY 분기에 도달하지 못해 `calc_buy_quantity` 가 호출조차 안 됨 |

---

## 작업 시 지켜야 할 제약

- **8영역 무단 수정 금지** — `risk.py` · `order_engine.py` · `src/realtime/` · `src/auth/` ·
  `api/order.py` · `session.py` · `scanner.py` · `strategy_registry.py`.
  P0-1 방향 A 는 `handler.py`(8영역) 수정이 필요하니 **명시적 승인** 후 진행.
- **워킹트리에 미커밋 cycle221 잔류** — `git checkout` / `stash` / `restore` **절대 금지**.
- **배포 창** — NXT 애프터(15:30~) 또는 익일 07:45 부팅 전. KRX 메인(09:00~15:30)과
  20:00 자문 / 20:10 로그분석 회피.
- **커밋·푸시는 사용자 명시 지시가 있을 때만.** 푸시 후 `gh run list` 로 CI/Deploy 확인 의무.
- **`enabled=False` 금지** — `risk.on_tick` 이 `registry.enabled()` 만 순회해
  보유 포지션의 손절·트레일링이 **전부 정지**한다. 비중 축소는 극소값(0.01)으로.

## 검증에 쓸 명령

```bash
# 유령 키 확인 (대입부는 risk.py:397 하나뿐, acml_vol 없음)
grep -rn "ticker_prices\[" src/ | grep -v CLAUDE.md

# 라이브 키 출현 대조
curl -s "http://3.38.228.74/api/trading/status" | grep -o '"acml_vol"' | wc -l   # → 0

# BFB 상태
curl -s "http://3.38.228.74/api/strategies" | python3 -c \
  "import sys,json;r=json.load(sys.stdin)['data']['bull_flag_breakout'];print(r['scan_stats'],r['positions'],r['buy_signals'])"

# 전체 회귀
find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q
```
