# 2026-09-03 아침 리포트 — 09-02 야간 작업 내용과 분기 사항

> 작성 주체: 메인 세션(야간 자율 진행, 사용자 위임 "대부분의 결정요소는 직접 권장하는대로 진행").
> 이 파일은 야간 진행 중 갱신된다 — 마지막 갱신 시각은 문서 맨 아래.
> 웹 버전(아티팩트): https://claude.ai/code/artifact/69740ef3-3064-426c-9235-d372ae36f1c1

## 0. 한눈에

| 항목 | 상태 | 비고 |
|---|---|---|
| cycle237 donchian 청산 로그 cap | ✅ 배포 (b985938, 15:40) | EC2 15:48 재부팅 클린 |
| cycle238 프리장 게이트 30초 구멍 (P1-6 A안) | ✅ 배포 (4cbea99, 20:26) | EC2 20:32 재기동, 07:45 부팅 대기 — **오늘 08:00 D+1 판독** |
| cycle239 계좌 게이트 신선도 fail-open (233 선결) | ✅ 커밋·푸시 (756be67, 21:08) | CI/Deploy 결과 아래 §2 |
| cycle240 재구독 핑퐁 | ✅ 배포 (`140a79a`, 06:15 푸시 → 06:22 EC2 반영) | §3 |
| cycle241 silent_inactive 세션 상대 판정 | ✅ 배포 (`6ac2bc2`, 06:15 푸시 → 06:22 EC2 반영) | §4 |
| 피라미딩 심층 검토 | ✅ 보고서 완성 · docs 커밋 `89fe8e3` | §5 · 권고 = 옵션 A + G0 1주 폴백 별건 |
| G-8 VCP 브레이크이븐 | 이미 활성 확인 | 운영 DB 1.5 (08-18~), BFB 대기 |

## 1. 낮 작업 (사용자 재석 중 완료분, 요약)

- 08-31 시세 두절 재발 없음(09-01·09-02 재등록실패 0·priority_drop 0). 09-01 07:52 부팅으로 회복, 장중 사각 0초.
- cycle238: `risk._defers_pre_market_exit` 를 `by_active OR by_clock` 로 전환. 신규 회귀 21, 5,899 PASS 독립 재확인. 적대 검증 뮤테이션 18종 escape 4 → 전부 봉인.
- cycle239: `is_soft_gated()` 900초 신선도 + fail-open + 소비자 전용 stale WARNING + 루프 종료 콜백. 신규 회귀 36, 5,940 PASS 독립 재확인. 적대 검증 수렴 5건 시정(기록자 원시값 환원·전 트리 AST 가드 삭제·escape 2 봉인).
- 문서 정정: 워크리스트 G-8(VCP 이미 활성)·cycle233 배포 상태, 8/31 가이드 포트 8002→8000.

## 2. cycle239 배포 결과 — ✅ 완료

- 커밋 `756be67` 21:08 푸시 → CI success → Deploy success → EC2 `HEAD=756be67`, 컨테이너 21:26:33 재기동, 토큰·전략 7종 로드 정상, "장 종료 — 내일 09-03 07:45까지 대기" 진입. ERROR 0.
- 다크런치(`account_risk_block_pct=None`)라 매매 행위 변화 0. 오늘부터 `[account_risk_watch_loop_exit] reason=running_false`(20:10 직후 1건/일) 이 liveness 표본으로 쌓인다.
- 활성화 게이트(AND): 배포 후 2영업일 `reason=stale` 0 ∧ `loop_exit running_false` 매일 1 ∧ 장중 `age_secs ≤ 600` ∧ cycle233 2주 창(~09-12) 만료 → 사용자 결정으로 DB `account_risk_block_pct=6.0` 한 줄.

### 2.1 새벽 푸시 (cycle240 + 피라미딩 docs + cycle241)
- `756be67..6ac2bc2` 06:15 푸시. CI/Deploy 결과 및 EC2 재기동 실측은 아래 갱신.

- **CI success · Deploy success(06:22)** → EC2 `HEAD=6ac2bc2`, 컨테이너 06:22:01 재기동, "매매 자동 시작 대기: 07:45" 진입. ERROR 0. 07:45 부팅부터 cycle240(09:30~ `_scan_loop`)·cycle241(08:51~ 첫 에피소드) 실효.

## 3. cycle240 — 재구독 핑퐁 (08-31 포렌식 결함 ⓑ) — ✅ 구현·검증 완료

- **원인 확증**: `resubscribe_stale_priority`(5분, `_scan_loop`)의 LOW 후보 소스가 `ticker_last_tick` **전수**라 매도·후보 이탈 종목이 20:10 정산까지 stale 자격을 유지 → 같은 이터레이션 안에서 `delta_unsubscribe_dropped`(빼기) ↔ 되살리기 무한 핑퐁. 기준선 실측: 09-01 `[stale_priority_resubscribe]` 종목 언급 993건/115행, 09-02 843/108행, 034020 은 09:00 매도 후 19:59 까지 **35회 재구독**.
- **시정**(`stale_watcher_core.py` 단독 +65L, 8영역·scheduler.py diff 0): priority 분리 직후·동시호가 skip·throttle·cap **앞**에서 `low_targets` 만 desired 집합(breakout 후보 ∪ momentum 스캔 결과)과 교집합. HIGH(보유·익일청산)는 구조적 면제 + HIGH 수집 실패 시 필터 off 이중 보호. 게이트 = breakout desired 비어 있지 않음 ∧ HIGH 수집 무예외 → off 면 현행 byte 동일(fail-open). 관측 = 기존 INFO 1행에 `desired_low= filtered_not_desired= filtered_sample=` 3필드 확장(신규 마커·cap 0).
- **검증**: 신규 회귀 25(엔진 + AST), 뮤테이션 21종 20 검출 · escape 1(m5a = cycle240 diff **밖** 기존 루프의 subscribe 성공 전 stamp — 후속 H 등재), 차분 2,300 조합 0 불일치(HIGH 탈락 0), 전체 **5,963 PASS**(워크플로) — 메인 세션 독립 재실행 결과는 §3.1.
- **부수**: cycle222-a AST 가드 `test_a11b`(stale_watcher_core `git diff HEAD` 공집합 **영구 동결**)가 모든 후속 시정을 차단하던 것을 내용 검사(앵커 토큰 0건)로 재스코프. 동형 영구 동결 2건(cycle223f:236·cycle223:325)은 후속 C.
- **D+1 판독(의미 반전 주의 — 배포 전후 같은 grep 합산 금지)**: `[stale_priority_resubscribe]` 종목 언급 993 → **<50/일** 기대, 장중 `desired_low>0`, RESUB↔5분 뒤 DELTA 1:1 페어링 0, `[stale_watcher_detail] stale=` 감소, `cap_exceeded` 0 유지. **롤백 기준** = 보유 종목 stale 증가(HIGH 경로 훼손 서명). `desired_low=0` 장중 지속은 조사 사안(4 돌파 전략 후보 0 또는 registry 이상).
- **후속 A~H**: A `ticker_last_tick` 매도 시 pop(order_engine 8영역, P3) · B `_scan_loop` new_set 에 NDC 부재(부팅 창 잠재) · C 영구 동결 가드 수명 감사 · D/E 관측 축 · F K watcher 120s 형제 경로(D+1 불변 시) · G `_last_scan_result` 접근자 · H m5a 순서 보정.
- **배포 권고(team-leader)**: 야간 푸시 안전 — 변경 경로는 09:30~ `_scan_loop` 에서만 호출, 부팅 직후엔 게이트 off = byte 동일, HIGH 는 강화 방향, 롤백 기준 명시.

### 3.1 메인 세션 독립 검증·커밋
- 전체 스위트 독립 재실행 **5,963 PASS**(10 skipped·328 xfailed·13 xpassed, 3분 15초) — 워크플로 보고와 일치. 구현 diff·AST 가드 재스코프 diff 직접 검토.
- 커밋 `140a79a` (23:05, 경로 명시 — 피라미딩 산출물·본 리포트는 제외). **푸시는 cycle241 과 묶어 07:15 이전 1회** 예정(§7 참조).

## 4. cycle241 — silent_inactive 세션 상대 판정 (08-31 포렌식 결함 ⓐ · P1-4) — 구현·적대 검증 완료, 문서 단계 진행 중

- **원인 확증**: `detect_silent_inactive_sessions` 가 세션마다 독립 판정(fresh_ratio<0.2 ∧ subscribed≥5 ∧ 5분)이라 시장 전체가 조용한 시각에 8/8 세션 동시 침묵을 "세션 8개 동시 고장" 으로 오판 → 하루 ~24회 강제 재연결 = 접속키 24건. **전제 정정(실측)**: 동시호가 게이트만으로 닫히는 비율은 4% 가 아니라 54.4%, 잔여 45.6% 중 D 슬롯(15:30~15:40) 22.4% 는 세션 비교만이 닫는다. 재연결의 회복 가치는 0(08-31 88회·08-12 40회 모두 익일 부팅으로만 회복, 정규장 발화 30일 0건).
- **시정**(`stale_session_recovery.py` 단독 +196/−9, 8영역·scheduler.py diff 0): 함수를 2-pass 로 재구성 — pass1 판정 재료 계산 → **상대 판정 게이트**(판정 가능 세션 ≥2 ∧ 침묵 == 판정 가능 전부 → 시장 침묵으로 기각 + 현재 세션 first_seen 전부 pop + `[]`) → pass2 기존 누적 루프 byte 동일. 판정 가능 세션 <2 면 현행 byte 동일(fail-open). 설계 불변식 = 결과 집합 ⊆ 현행(순수 축소, 새 발화 경로 0). 시간당 2회 cap·dict 동일성·상수 SoT·Q1 import 표면 불변.
- **관측**: `[silent_inactive_market_wide_skip] transition=entered|persisting|exited`(에피소드 상태기계, persisting 은 30분 이상 지속 시 30분마다 WARNING, 날짜 키 자기 리셋, peek→로그→mark, 실패 흔적 마커 별도). 진단 필드 `connected=`/`reconnects=` 병기 — 적대 검증이 두 필드 모두 "소켓 생존" 을 뜻하지 않음을 밝혀 docstring·판독표를 정정(소켓 생존 판별은 `[ws_heartbeat]`).
- **적대 검증**: 3렌즈 반박 + tester 뮤테이션 26종(23 검출) → 확증 HIGH 4·MEDIUM 2 → 라운드 1 시정 4(AST 가드 자체 결함 `_resolve` tuple−set, `connected=` 의미, escape M06a/b·M19 회귀 봉인) + 라운드 2 시정 1(`reconnects=` 서술 반전) → 잔여 HIGH/MEDIUM 0. 처분 보류 1 = 저녁 시간대 main 세션이 구조적으로 침묵해 "개장 증인" 역할을 못 하는 변형(후속 A, domain-consult 대상).
- **D+1 판독**: `[silent_inactive_force_reconnect]` 24/일 → **0~3건/일**(main 단독 잔여는 설계상 정당 발화, 후속 A 별개 축), `market_wide_skip transition=entered` 는 ≈08:51~53·≈15:21~23(+간헐 07:59) 에 **2~3행/일**. 접속키 발급 일 건수 동반 감소.
- **후속**: A main 단독 위양성(MIN_SUBSCRIBED 상향 또는 절대 fresh 하한 — 임계 변경이라 domain-consult) · `reconnects=` 필드 유지/폐기(team-leader 결정) · 08-31 형 전 세션 실두절 재검토 트리거(§8 E).

### 4.1 메인 세션 독립 검증
- 06:02 현재 트리(Green + 시정 라운드 2 반영) 전체 스위트 **6,002 PASS**(10 skipped·328 xfailed·13 xpassed, 2분 14초) — Docs 단계 워크플로 수치와 일치.

### 4.2 최종 수치·커밋·푸시
- 신규 회귀 **39**(행위 25 + AST 14), `stale_session_recovery.py` +205/−9 단독, 8영역·scheduler.py diff 0. 문서 동기화 = 워크리스트 P1-4 ✅ · CLAUDE.md 표 1행 + 핵심 안전 규칙 항목 갱신 · CHANGELOG · engine/CLAUDE.md 4곳.
- 커밋 `6ac2bc2` → **06:15 푸시**(`756be67..6ac2bc2` = cycle240 `140a79a` + 피라미딩 docs `89fe8e3` + cycle241). CI/Deploy 결과는 §2.1.
- 배포 권고(team-leader) = GO: 순수 축소 방향(결과 집합 ⊆ 현행), 매수·매도·손절 경로 무접촉, 보유 시세 보장 강화 방향. 수용한 트레이드오프 = 08-31 형 전 세션 실두절 시 자동 재연결 소멸(실측 회복 가치 0, 가시성은 `[tick_coverage] ratio=0.0%` + `persisting` WARNING, 대응 = `POST /api/trading/restart`).
- **롤백 기준**(단일 커밋 `git revert`): (a) 보유 종목 HIGH stale 증가·시세 공백 (b) 정규장에 `entered` + `persisting` 이 찍히는데 `[tick_coverage]` 가 자가 회복하지 않음.

## 5. 피라미딩 심층 검토 — ✅ 보고서 완성 (`_workspace/domain_consult/pyramiding_deep_review_20260903.md`, 577행)

절차 = 6렌즈 병렬 사실조사(사이징 수학 · 아키텍처 · 전략 적합성 · KIS 실행 · **EC2 운영 DB 실측 시뮬** · 도메인) → domain-expert 종합 → 3인 적대 비판(지적 38건, HIGH 8) → 전 수치 재검산 최종본. 시뮬 스크립트·CSV 는 `_workspace/pyramiding_review_20260903/` 에 영속화.

**권고 = 옵션 A: 피라미딩 코드 착수 보류 + 착수(T1)/활성(T2) 게이트 명문화.** 단 그 앞에 더 급한 별건 하나 — **"1주 폴백 = 진입 시점 과잉 피라미딩"** 을 독립 사이클로 시정(G0).

핵심 근거(전부 실측):
- **as-built 시뮬이 반대**: 완결 왕복 38건(120일)에 터틀 1/2N 사다리를 **시스템이 실제 강제하는 사이징**(이론 유닛 + 예산 클램프)으로 얹으면 kojiro Δ **−23,927원**(적격 9/14, 개선 2·악화 7), donchian Δ 0(이론 유닛 <1주라 추가 자체가 무발화). 8개 변형 전부 음수.
- **진입 시점이 이미 과잉**: donchian 실제 1랏 = 터틀 유닛 환산 평균 **4.94유닛**(최대 15.61 — 현대글로비스 1주). 책의 완성 피라미드(4유닛)보다 첫 진입이 크다. kojiro 1.52유닛.
- **유닛당 손익**: kojiro 초기 유닛 −0.65R vs 추가 유닛 −1.52R(2.3배 나쁨) — "피라미딩은 증폭기일 뿐" 이 현 청산 규약에선 거짓.
- **N단위 기대값**: donchian −0.55N(n=24, 95% CI 0 미포함) / kojiro −0.43N(n=14, CI 0 포함). 실측 승률·RR = donchian 29.2%/0.565, kojiro 21.4%/1.717.
- **꼬리 위험**: kojiro 4유닛 스택 −30% 하한가 시 계좌 3.72%(계획 5N 의 5배), 1주 폴백 스택이면 계좌 8.83% = kojiro 일일 손실한도의 3.7배를 단일 사건으로 초과.
- **실효 구속**: 예산이 아니라 `max_open_risk_pct` 4.5% — 4유닛 스택 5N=2.5% 라 **1.8개 스택에서 매수 정지**(6종목 분산 → 실질 1.8종목 집중). donchian 은 이 캡 자체가 부재.
- **구현 비용(옵션 C)**: 8영역 3곳 + scheduler 3,999/4,000 라인 상한 + 매수 게이트 8종 우회 위험 + positions 단일 랏 PK + 1차 유닛 소멸(P-1)·부분체결 이중주문(P-1b) 등 배관 결함 → 4~6사이클.
- 1/2N vs 1N: 총 Δ 는 1N 이 작지만 **유닛당은 1N 이 더 나쁨**(−3,193 vs −2,190원) — "규칙 선택" 이 아니라 "용량 선택".

옵션 정리: **A(권고)** 보류+게이트 / **B** 틱 관측 would_add 다크런치(남은 기각 근거 = 표본 미달, +0.3N 검출에 n≈117 ≈ 3~4년) / **B-lite** 20:10 리포트 일봉 배치 would_add(핫패스 무접촉, 채택 권고) / **C** kojiro 한정 실구현(반대) / **G0 별건(권고, A 와 병행)** 1주 폴백 과잉 시정 — ⓐ 이론 유닛 <1주면 스킵(donchian 거래 ~79% 감소) 또는 ⓑ 폴백 notional 상한.

게이트(요지): T1 = G0 1주 폴백 시정 · G1′ 순자산 ≥500만 5영업일 · G4 Σ상한 6.0 활성+2주 무오탐 · G6 장중 레벨 크로싱 실행 경로 확정 · G7 kojiro 한정 확정. T2 = G1″ 5,000만 또는 G2′(유닛 ≥2주일 때만 추가) · G3 kojiro 30왕복 N기대값 CI 하한>0(MDE +0.59N 주의) · G3′ 충실 사이징 시뮬 Δ>0 · G5 배관 결함 동시 시정 · G8 매수 게이트 8종 재판정 · G9 entry_atr 영속 · G10 추가 경로 1주 폴백 금지 · G11 상관군 유닛 캡 · G12 결합 백테스트(청산 규약 × 간격) — **A 를 뒤집을 수 있는 유일한 증거 경로**.

## 6. 오늘 아침 확인 항목 (D+1 판독)

- **08:00:0x** `[pre_market_exit_deferred]` 첫 발화 + 같은 시각 `[pre_market_exit_gate_divergence] reason=clock_fallback` 동반 → cycle238 구멍 닫힘. `도치안 시간 기반 청산` 첫 발화가 09:00 이전이면 회귀. (보유 종목 틱이 있어야 계량됨 — 부재 ≠ 정상)
- **09:00:00~29** `reason=active_stale_hold` 건수 → clock-primary 후속 판단 분자.
- cycle239: `[account_risk_watch_loop_exit] reason=running_false` 는 20:10 직후 1건이 정상, `released reason=stale` 0건, `[account_risk_watch_loop_died]` 0건, 장중 `GET /api/portfolio/risk` 의 `account_gate.age_secs ≤ 600`.
- 07:45 부팅 `[tick_blind_boot] market_blind_secs=0` (야간 재시작 2회분 downtime 은 정상).

## 7. 사용자 결정이 필요한 분기

야간에는 "권장안대로 진행" 위임에 따라 **배관·안전 방향** 결정만 제가 내렸습니다(cycle240·241 배포, 피라미딩 옵션 A 권고, 시뮬 스크립트 영속화, G-8 문서 정정). 아래는 **매매 행위·자본·임계**에 닿아 사용자 결정으로 남긴 항목입니다.

| # | 분기 | 제 권고 | 근거·비고 |
|---|---|---|---|
| 1 | **G0 — 1주 폴백 = 진입 시점 과잉 피라미딩** 시정안 | ⓑ 폴백 notional 상한(1유닛 초과분 캡) 을 먼저, ⓐ(<1주 스킵)는 표본 확보 후 | ⓐ 는 donchian 거래 ~79% 감소로 표본 해상도 파괴. ⓑ 는 매수를 줄이는 안전 방향이지만 매매 빈도가 바뀌므로 사용자 결정. 접촉면 `strategy_base.py` 한 곳(비8영역) |
| 2 | 피라미딩 **옵션 A 채택 + B-lite(20:10 리포트 would_add 일봉 배치)** 여부 | A 채택 · B-lite 채택 · G12 외부 백테스트(청산 규약 × 간격 격자)는 MCP 스윕 가능 시 | 보고서 §4 게이트 T1/T2. G12 는 A 를 뒤집을 수 있는 유일한 증거 경로 |
| 3 | cycle233 활성화(`account_risk_block_pct=6.0`) 시점 | ~09-12 이후, cycle239 D+2 게이트 충족 확인 후 | 활성화 D+1 첫 확인 = `transition=entered` 시 대시보드 `effective_gated=true` |
| 4 | cycle241 후속 A — main 세션 저녁 단독 위양성 (`SILENT_INACTIVE_MIN_SUBSCRIBED` 상향 또는 절대 fresh 하한) | D+2 실측(16시 이후 main 단독 발화 건수) 후 domain-consult 착수 | 임계 변경 = 저유동 보유 종목 시세 감시 사각 vs 재연결 소음 교환 |
| 5 | cycle239 후속 A — 감시 평가 `asyncio.wait_for(300s)` 타임아웃 | 다음 배관 사이클 우선순위 1 로 착수 권고 | hang 이 동결의 진짜 경로. stale 규칙은 ≤900s 거짓 차단 완화책 |
| 6 | cycle238 후속 — clock-primary 09:00 정확 해제 | `reason=active_stale_hold` 1주 계량 후 판단 | 안전 방향 유지 중 |
| 7 | 3군 잔여 착수 순서 — cycle235 후속(잔여취소 타이머·1차 UPDATE PARTIAL 포괄·`_completed_orders` 리셋) · cycle236 LOW(대출일별 잔고 집계·manual-sell 분류) · cycle237 잔여(손절/채널/트레일링 로그 4종 cap) | cycle235 후속 → 237 잔여 → 236 LOW 순 | 235 후속은 order_engine 8영역 승인 필요 |
| 8 | kojiro `max_units_per_stock`(DB=2, 소비처 0, 책의 4 와 불일치) 처분 | 삭제 또는 4 로 정정 + 봉인 주석 | 피라미딩 검토 열린 질문 |
| 9 | 수수료·세금 관측 배선(라이브 손익이 gross — `daily_loss_limit` 도 비용을 못 봄) | 회전율을 바꾸는 어떤 변경보다 먼저 최소 비용 모델 권고 | 피라미딩 검토 열린 질문 |
| 10 | G-8 BFB 브레이크이븐 활성 | VCP 첫 체결·승격 관찰 후 | VCP 는 이미 1.5 활성 |

야간 자율 결정 목록(사후 승인용): cycle240·241 커밋·푸시(권장안 "검증 깨끗하면 푸시") · 피라미딩 시뮬 스크립트 `_workspace/` 영속화 · cycle240 에서 cycle222-a 영구 동결 AST 가드 재스코프 · cycle241 에서 사이클 61/67 "본체 변경 0" 산문 계약 재스코프 · 8/31 가이드 포트 정정.

---
마지막 갱신: 2026-09-03 06:25 KST (08:07 D+1 자동 실측 결과가 이 아래에 추가됨)
