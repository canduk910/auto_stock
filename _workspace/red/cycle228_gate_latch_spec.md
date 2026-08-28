# 사이클 228 명세 — BFB·VCP 거래량 게이트 전환 + 충족 래치 (228-A) / setup 리졸버 계약 복원 (228-B)

> 작성: team-leader, 2026-08-27 16:00 KST
> 자문 정본: `_workspace/domain_consult/cycle228_vol_gate_latch.md` (Q1~Q7 + 실측 정정 2건 + 충돌 1건)
> 선행: cycle227 Stage 0 (`_workspace/red/cycle227_acml_vol_stage0_spec.md`) — 배관·관측은 그대로 재사용
> 사용자 결정 (2026-08-27 확정):
> 1. **래치 설계 = 자문안 그대로** — 후퇴에도 래치 유지, 해제선 = 전략 자신의 §2 손절선(flag_low/base_low), TTL 없음(entry_end 자연 만료), VCP 동일 적용, retention 민감도 무변경, 로그는 상태 전이 + cap.
> 2. **추격 상한 채택** — `max_breakout_extension_pct` BFB **5.0** / VCP **7.5** 리터럴 고정(PARAM_RANGES 미편입), `current_price` 기준 판정(`ticker_prices`/daily_high 커플링 금지).
> 3. **비중·cash 현행 유지** (BFB 0.15 / VCP 0.10).
> 4. **228-B(setup 리졸버) 동반 시정, 별도 커밋** — D+1 귀인 분리용 전용 로그 동반.

## 커밋·개발 순서 (구속력)

같은 두 파일(bull_flag_breakout.py / vcp_breakout.py)을 228-A·228-B 가 모두 건드리므로:
**Red A+B 동시 작성(테스트 파일 분리: `test_cycle228_*` vs `test_cycle228b_*`) → Green A 만 → A 검증 → A 커밋 → Green B → 전체 검증 → B 커밋.** `git stash`/`checkout`/`restore` 절대 금지.

## 실측 정정 (자문 — 명세에 구속력)

- 라이브 DB 파라미터가 코드 기본값과 다르다: BFB `breakout_volume_mult` **1.0**(코드 2.0)·`breakout_retention_minutes` **1**(코드 3)·`flag_lookback_min` 3(코드 2) / VCP mult **1.2**(1.5)·`volume_contraction_ratio` **1.0**(0.70). 테스트는 코드 기본값 기준으로 쓰되 라이브 값 가정을 박지 말 것.
- Stage 0 "게이트 평가 5회"는 고유 종목 5개(cap 때문에 반복 평가 미로그) — 재평가 빈도 가정 금지.

---

## 228-A. 게이트 전환 + 충족 래치 (bull_flag_breakout.py + vcp_breakout.py 한정)

### A1. 게이트 소스 전환

- 거래량 컷이 `tick_volume.get_observed_acml_vol(ticker)` 를 읽는다(함수 내 모듈 경유 호출 — cycle227 관례). 기존 `ticker_prices` 4줄(`from ... import ticker_prices`/`info_price`/`acml_vol`/비교) 제거.
- **미관측(None) = fail-closed**(매수 안 함) + `[bfb_vol_gate_no_data]`/`[vcp_vol_gate_no_data]` 마커(1회/(ticker)/일 cap). `0` sentinel 금지 계약 유지.
- VCP 거울 정합 유지: `vol_threshold <= 0` → 게이트 통과(현행 의미론 보존).

### A2. BFB 충족 래치 (상태 기계)

- 상태: 무장 안 됨 → retention 대기(`_breakout_first_seen`, 현행 그대로) → **래치**(`_vol_latch`) → BUY.
- **retention 완주 시**: 거래량 게이트 평가 → 통과(+A4 상한 통과) → BUY / **미달 → `_vol_latch[ticker] = 래치 등록 시각(KST)` 등록** + `[bfb_latch_armed]`(1회/(ticker)/일 cap). `_breakout_first_seen` pop 은 현행 유지.
- **래치 중 틱**(`ticker in _vol_latch`, edge-crossing 불요):
  - `current_price < flag_low`(§2 손절선과 동일 소스 — `_candidates`/`_effective_setup` 의 flag_low) → **래치 해제** + `[bfb_latch_released] reason=stop_line`(1회/(ticker)/일).
  - `current_price >= flag_high` 인 틱에서만 거래량 게이트 재평가. 통과 + A4 상한 통과 → **BUY**. 매수 로그/신호에 `latch_age_sec`(래치 등록→매수 경과초) 동반(자문 Q2 — N=10 후 실측 판단 데이터).
  - `flag_low <= current_price < flag_high` → 래치 유지, 아무것도 안 함(자문 Q1(b) — 001450 −3.53% 왕복 생존).
- retention 민감도·edge-crossing·쿨다운·`_bought_today` 등 기존 진입 로직 무변경(자문 Q5).
- `_vol_latch` 는 **날짜 키 자기 리셋**(cycle227 tick_volume 패턴 — scheduler.py diff 0). entry_end 이후엔 시간 가드가 앞서므로 자연 만료(released 로그 없음 — 사유는 stop_line 만).

### A3. VCP 충족 래치

- retention 없음(신설 금지 — 자문 Q4): edge-crossing 순간 게이트 평가 → 미달 → 래치 등록 `[vcp_latch_armed]`.
- 래치 중: `current_price < base_low` → 해제(`reason=stop_line`) / `current_price >= base_high` 틱에서 재평가 → 통과+상한 통과 → BUY(`latch_age_sec` 동반).
- 나머지 A2 와 동형(마커 접두사만 vcp).

### A4. 추격 상한 (매수가 보호)

- 게이트 통과 판정 직후: `ext_pct = (current_price - 돌파선) / 돌파선 × 100 > cap` 이면 매수 거부 + `[bfb_vol_gate_reject] reason=extension`(1회/(ticker)/일) — **래치는 유지**(가격이 상한 안으로 복귀하면 그때 매수).
- cap 리터럴: BFB `max_breakout_extension_pct = 5.0` / VCP `7.5` — DEFAULT_PARAMS 등재하되 **PARAM_RANGES/INT_PARAMS 미편입**(donchian 사이클 209 선례 — 진입 정체성 상수). 판정 기준은 **current_price**(daily_high/`ticker_prices` 금지 — donchian 이식 시 커플링 유입 주의, AST 가드).
- **부팅 불변식 WARNING**(자문 충돌 항목 선택지 A): 첫 `prepare()` 시 1회, `(1 + cap/100) × (1 + stop_loss_rate/100) > 1.0` 이면 `[extension_cap_invariant]` WARNING(fail-open, 자동 보정 금지). stop_loss_rate 는 AI 튜닝 대상이라 값 도출은 금지, 관계 검증만.

### A5. 진동 로그 상태 전이화 (P1-3 로그 축)

- 기존 "BFB 돌파 1차 감지"/"BFB 돌파 후퇴" **한글 문구 byte 보존**, emission 만 `(ticker, 전이종류)` 1회/일 cap(날짜 키 자기 리셋).
- cap 무관 `_scan_stats` 카운터: `breakout_seen_count` / `breakout_retreat_count`(총량 관측). 473행/일 → ~20행/일 목표.

### A6. 관측 훅 은퇴 + 마커·카운터 승계 (자문 Q7)

- `_observe_vol_gate`/`[.*_vol_gate_observe]` 마커 **은퇴**(would_pass 의 매매 귀결이 반전되므로 마커 유지 금지). 게이트 본체가 신규 마커로 직접 로그: `[bfb_vol_gate_pass]`(BUY 시)/`[bfb_vol_gate_reject] reason=extension`/`[bfb_vol_gate_no_data]` + `[bfb_latch_armed|released]`(VCP 동형).
- `_scan_stats` 키 교체: `vol_gate_observe_pass/fail/no_obs` → `vol_gate_pass` / `vol_gate_reject_ext` / `vol_gate_no_data` / `latch_armed_count`(+A5 의 2키). `_empty_scan_stats()` 동기 갱신.
- 전환일(2026-08-27)·마커 은퇴를 CLAUDE.md 사이클 행에 명기(과거 로그 해석 단절점).

### A7. 은폐 테스트 3파일 의미 전환

- `test_bull_flag_breakout.py`/`test_bull_flag_breakout_retention.py`/`test_vcp_breakout.py` 의 `ticker_prices["acml_vol"]` 손주입(주석 마커 11곳) → `tick_volume` 주입(`record_acml_vol` 경유)으로 교체. cycle227 주석 마커 제거. 래치 도입으로 기존 케이스의 기대 신호가 바뀌는 경우 **의미 전환 명시**(xfail 아닌 재작성, 사유 주석).

### A8. AST·가드 갱신

- cycle227 AST-2(게이트 블록 byte pin) **의미 전환**: 새 가드 = 게이트가 `tick_volume` 경유 + 게이트/래치 블록에서 `ticker_prices` 참조 0건 + `_vol_latch` 재평가 경로 존재.
- AST-1(전 소스 `ticker_prices` `acml_vol` 대입 0건)·AST-3(handler len<10)·cycle227 e2e 는 **무변경 유지**.
- 8영역 sha 핀: cycle227 잔존 핀 4항목(risk/handler/BFB/VCP — 자기소멸 상태) **삭제**(TODO 이행) + 228 은 8영역 무접촉이므로 `test_g223_10`/`g223f_9` 신규 핀 불요. **전략 파일 가드**(`test_g223_12`·cycle226 `_ALLOWED_CONTENT_SHA`)에만 BFB/VCP 새 내용 sha 재핀(A 커밋 전 워킹트리 기준 → **A 커밋 후 B Green 시 재핀 1회 더**(같은 파일 재수정) — B 커밋 시 자기소멸).
- 추격 상한 AST: cap 값이 PARAM_RANGES 에 미편입 + 판정식에 `daily_high`/`stck_hgpr`/`ticker_prices` 토큰 0건.

---

## 228-B. `_effective_setup` 구조 레벨 계약 복원 (별도 커밋)

### B1. 결함 (자문 발견 — Red 가 현행 재현으로 실증할 것)

`_effective_setup` 이 `_candidates` 를 **통째로 우선**하는데 `prepare()` 는 보유 종목을 후보에서 제외하지 않는다 → 보유 중 익일 새 폴/플래그(베이스) 재검출 시 §2 손절선이 **새 flag_low/base_low**(진입가보다 높을 수 있음)로 갈아타 상승 포지션 조기 손절 가능. `strategies/CLAUDE.md` P1 계약("구조 레벨은 BUY 직전 stamp 후 **불변**, 지표만 매일 갱신")과 정면 충돌.

### B2. 시정

- 보유 종목(= `_position_setup` 에 키 존재)에 한해: **구조 레벨 키**(BFB `flag_low/flag_high/pole_high/pole_start` / VCP `base_low`)는 `_position_setup` 값 우선, **지표 키**(`atr14`, VCP `ema50`)는 기존 우선순위 유지(live 갱신 의도 보존).
- 미보유(폴백 경로)·`_position_setup` 키 결손 시 미발화 계약 등 기존 행위 전부 보존.
- **전용 관측 로그** `[setup_structure_conflict]`(1회/(ticker)/일): live 후보가 존재하고 구조 레벨 값이 stamp 와 다를 때 — 발화 빈도 자체가 이 결함의 실측 규모다(D+1 귀인 분리 목적, 사용자 결정).

### B3. 가드

- Red: 보유 + 재검출(값 상이) 시나리오에서 §2 가 stamp 값을 쓰는지 + 지표는 live 를 쓰는지 + conflict 로그 1회 cap.
- 기존 P1 회귀(`_position_setup`/`_effective_setup` 테스트)와 충돌 시 의미 전환 명시.

---

## 공통 제약

- **수정 파일 = bull_flag_breakout.py / vcp_breakout.py / 테스트 / 가드 핀 / 문서 한정. 8영역·scheduler.py·handler.py·risk.py·tick_volume.py diff 0.**
- 진입 임계 기존 값·비중·DEFAULT_PARAMS 기존 키 무변경(신규 키는 `max_breakout_extension_pct` 2건뿐).
- 로그 폭주 금지(모든 신규 마커 cap + 카운터 병행), 한글 기존 문구 byte 보존(A5), `logger.debug` 단독 금지.
- 커밋·푸시: A/B 별도 커밋(사용자 확정). 푸시는 별도 지시.
- 배포 창: 금일 NXT 애프터(~19:40 푸시 마지노) 또는 익일 07:45 전. **이번 배포로 매수가 실제로 열린다** — D+1 관찰 프로토콜(자문 Q6): 첫 체결 시 진입 임계 재튜닝 금지 유지, 청산 경로 첫 실가동 모니터링(BFB flag_low·measured-move·시간청산 / VCP base_low·ema50·트레일링), `latch_age_sec` 축적.
