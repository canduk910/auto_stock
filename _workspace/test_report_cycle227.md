# 사이클 227 Phase 4 통합·적대적 검증 리포트

> 작성: tester, 2026-08-25
> 대상: P0-1 Stage 0 (acml_vol 배관 + would_pass 관측) + P0-2 (universe 가드 안전조건 시정)
> 근거 문서: `_workspace/red/cycle227_acml_vol_stage0_spec.md` · `cycle227_behaviors.md` · `cycle227_red_result.md`

## 판정: **GO**

Stage 0 불변식(BFB·VCP 매수 행위 변경 0)은 소스 정독 + 차분 스크래치 실증 + 이중 봉인(AST-2
소스 pin + 8영역 sha 핀) 어느 축에서도 반증되지 않았다. HIGH/MEDIUM 결함 **0건**.
LOW/관찰 노트 4건 + 프로세스 잔여 1건(W8 문서 동기화)은 아래에 기재 — 배포 차단 사유 아님.

검증 수치:

| 스위트 | 결과 |
|---|---|
| cycle227 신규 8파일 + 가드 핀 3파일 + g3 + 적응/은폐/cycle226 | **244 PASS** |
| 전체 백엔드 | **5,617 PASS / 실패 0** (9 skip, 328 xfail, 13 xpass, 122s) — red_result §6.5 와 정확 일치 |
| tester 스크래치 (차분 상태 비교 + 자기실패 + hot path 비용) | **7 PASS** |

---

## V1. Stage 0 불변식 적대적 검증 — 반증 실패 (= 봉인 확인)

**"이번 변경으로 BFB/VCP 가 BUY 를 반환할 수 있게 되는 경로" 는 0건이다.**

- **훅 호출부 threshold 식의 예외 표면 = 기존과 동일.** 착수 시 최대 의심 지점은
  `_observe_vol_gate` 호출 인자(`int(info[...] × params[...])`)가 try/except **밖**(호출자
  스택)에서 평가된다는 것이었다(cycle226 "try 밖 예외 지점" 부류). 실측 결과 무해 —
  BFB 호출부 식(`bull_flag_breakout.py:919`)은 AST-2 로 봉인된 기존 게이트 라인(`:926`)과
  **byte 동일**하고, VCP(`vcp_breakout.py:1032`)도 봉인 블록(`:1039-1040`)과 의미 동일하다.
  호출부에서 예외가 날 입력이면 7줄 아래 기존 게이트에서 똑같이 났다 — 새 예외 지점 0.
- **차분 실증(스크래치)**: 동일 입력·동일 호출을 "관측 없음" 인스턴스와 "관측 있음"(미달
  1 / 초과 10,000,000) 인스턴스에 태워 사후 상태 전체(관측 전용 필드 제외)와 반환 신호를
  비교 — BFB·VCP × 2관측 = 4조합 전부 상태 diff ∅ + 양쪽 `Signal.NONE`. 관측기 자기실패
  (`get_observed_acml_vol` 가 raise)도 2전략 모두 예외 미전파 + `NONE` 유지.
- 훅이 만지는 상태는 `_scan_stats` 관측 카운터 3키 + cap 필드 2개뿐 —
  `_prev_price`/`_breakout_first_seen`/`_bought_today`/`_candidates`/`_cooldown_until` 무접촉.
- 훅 위치 = BFB retention 완주 **직후**·게이트 **직전** (W4-12 테스트가 retention 대기 중
  로그 0행을 별도 고정). 게이트 평가 순서 무변경.
- risk.on_tick 의 record 는 `ticker_last_tick` 갱신 직후 1지점, leaf 모듈 기록만 —
  `ticker_prices` 는 E2E-2 가 런타임에서 정확히 4키임을 검증. 매수/청산 분기 무접촉.

## V2. hot path 안전성 — 통과

- `record_acml_vol` 실측 **1.07µs/call** (100k 호출) — dict assign + KST strftime 뿐,
  락/I/O/예외 생성 0. `_observed` 는 구독 종목 수(수백)로 상한 + 날짜 전환 시 전체 clear.
- 날짜 자기 리셋 = `timezone(+9)` 고정 오프셋의 날짜 문자열 비교 — UTC 자정이 아니라
  **KST 날짜 전환에서만** clear (W3-9 가 UTC 15:00 경계 직접 검증).
- handler `_parse_acml_vol` 실패 → `-1` sentinel + 틱 생존 (W1-7/8), `len(fields) < 10`
  가드 byte 불변 (AST-3 + W1-6). 9필드 payload 는 기존대로 silent drop.
- risk.on_tick 의 `from src.engine import tick_volume` 은 sys.modules 캐시 조회 — 무시 가능.

## V3. 경계면 — KIS 정본 payload 형상 재확인

- **KIS MCP 정본 재확인 완료**: `ccnl_total`(H0UNCNT0)·`ccnl_krx`(H0STCNT0) 공식 컬럼
  리스트 둘 다 **46컬럼**, **index 13 = `ACML_VOL`(누적 거래량)** — 구현·명세와 정확 일치.
  ([12]=`CNTG_VOL` 체결 거래량과 구분 정확.)
- 4형상 전수는 신규 테스트가 이미 커버(중복 작성 안 함): (a) 정상 46컬럼 → int 전달
  (b) 10~13컬럼 → 틱 생존 + `-1` (c) 다중 레코드 프레임(46×2) → **첫 레코드** 값 계약 고정
  (W1-10, 과소 계상 = fail-closed 방향 노이즈원 명시) (d) 비숫자/음수/공백/과학표기 → `-1`.
- E2E 는 payload 문자열 → `handler._handle_tick` → 프로덕션 `RiskManager.on_tick` →
  `tick_volume` 을 **중간 mock 0** 으로 통과 — P0 를 처음부터 잡았을 그 테스트가 실재함 확인.

## V4. P0-2 universe 가드 경계면 — 통과

- 판정 순서 = ccnl None 보류 → tick 관측(`vol_source=tick`, REST 미호출) → REST 폴백
  (`inquire_acml_vol`, FHKST01010100) → 둘 다 부재 보류. 구현(`stale_universe_guard.py:93-146`)
  ·테스트(W6-1~8)·명세 3자 일치.
- REST 폴백 = target 당 최대 1회 + 각 경로 50ms sleep (None 보류 `:140` / 충분 `:145` /
  제외 `:179`). 이중 graceful (호출부 try/except + `inquire_acml_vol` 내부 흡수 → None).
- 보유/익일청산/이미 제외/stale≤5 사전 가드(`:68-88`) **byte 무변경**. 임계 10,000 불변.
- `inquire_acml_vol` 은 `base.py::_QUOTE_ALLOWED_PATHS` **기존재 path**(`base.py:79` 첫 항목)
  사용 — **base.py diff 0** (화이트리스트 무변경) 실측 확인.

## V5. 산출물 감사 — 통과

- (a) `test_universe_guard.py`: **어서션 변경 0** — `inquire_acml_vol` AsyncMock 추가 +
  `tick_volume.reset_for_test()` + docstring/주석만.
- (b) 가드 핀 3파일: sha 핀 dict 추가 + 자기소멸 TODO. `test_g223_12` 와 cycle226
  `test_common_1` 은 면제 **기전 이식**(파일명 면제 → 내용 sha 핀)으로 검사 로직이 확장됐으나
  강도는 유지(핀 외 파일 즉시 FAIL + 핀 파일도 1byte 변경 시 FAIL) — red_result §6.4 뮤테이션
  검증(주석 1줄 → 6 FAIL → 원복 일치) 이력과 정합. **핀 4값을 워킹트리 shasum 으로 실측
  대조 — 전부 일치** (risk `58d7ce…` / handler `d43b6a…` / BFB `a8ec2a…` / VCP `a9338a…`).
- (c) 은폐 테스트 3파일: `⚠️ cycle227 Stage 0 유지 — 게이트 전환 사이클에서 tick_volume
  주입으로 의미 전환 의무` **주석만 추가** (코드 변경 0). BFB 4 + retention 3 + VCP 4 곳.
- (d) 총 변경 표면 = 승인 목록과 일치. **scheduler.py diff 에 cycle227 지문
  (acml/tick_volume/vol_gate) 0건** — cycle221 잔류만 존재. cycle221 잔류 테스트 4파일도
  지문 0건. 승인 밖 8영역(base.py/order_engine/scanner/…) diff 0.

## V6. 관측 로그 운영성 — 통과

- 마커 substring 안전: `[bfb_vol_gate_observe]`(닫는 대괄호 포함 grep)는
  `[bfb_vol_gate_observe_failed]` 와 충돌하지 않음(observe 뒤가 `_` vs `]`). VCP 동일.
  로그 본문에 타 마커 문자열 미포함.
- 관측 = `logger.info`(→ `_DbLogHandler` INFO 컷 통과, 기존 전략 마커와 동일 로거),
  자기실패 = `logger.warning` 1행 + `exc_info`.
- cap 축 = `(ticker, outcome)` 1회/일, outcome ∈ {pass, fail, no_obs} — 최대 3행/종목/일.
  카운터는 cap 무관 누적(`get_scan_stats` 3키 상시 존재, W4-13).

---

## 발견 사항 (전부 LOW / 관찰 — 수정 불요, 인지용)

| # | 심각도 | 내용 |
|---|---|---|
| L-1 | LOW (관찰 표기) | VCP `vol_threshold <= 0` + **미관측** 조합에서 카운터는 `pass` 로 집계되나 로그 행은 `reason=no_observation` 형태로 나간다(`would_pass=True` 미표기). cap 키도 `(ticker,"pass")` 로 선점돼 이후 실관측 pass 로그가 그날 억제된다. 도달 조건 = `avg_volume_20 == 0`(극단)이라 실질 영향 미미 — 관측 데이터 해석 시 인지만 |
| L-2 | LOW (하드닝 노트) | `risk.on_tick` 의 `record_acml_vol` 호출은 try/except 미포위(명세 W2 대로). record 본체는 순수 dict/strftime 이라 현실적 예외 경로 없음 + handler 가 항상 int 전달. 게이트 전환 사이클에서 소비가 늘면 재평가 |
| L-3 | LOW (가드 한계) | AST-1 은 별칭 경유 대입(`d = ticker_prices[t]; d["acml_vol"] = v`)을 못 잡는다(직접 subscript/dict-리터럴/update 만 탐지). 단 E2E-2 + W2-6 이 런타임 4키를 검증해 이중 방어 — cycle226 "지역 대입 전이 추적" 교훈과 같은 부류, 게이트 전환 사이클에서 참고 |
| L-4 | LOW (테스트 위생) | 적응된 `test_universe_guard.py` 의 사후 `tick_volume.reset_for_test()` 가 try/finally 미보장 — 어서션 실패 시 상태 누수 가능. 각 테스트 시작부 reset 이 있어 실해 없음 |

## 프로세스 잔여 (배포 전 완료 권고)

- **W8 문서 동기화 미수행**: (1) `CLAUDE.md` 하네스 표 cycle227 행 미추가
  (2) `src/engine/strategies/CLAUDE.md` 상단 배너의 "WS 핸들러도 체결 payload 의
  누적거래량을 파싱하지 않는다" 서술이 **이제 거짓**(cycle227 이 파싱함) — Stage 0 상태
  ("관측 중·게이트 미전환·매수 여전히 차단")로 갱신 필요 (3) `_workspace/00_URGENT_WORKLIST.md`
  P0-1(Stage 0 완료·전환 판정 기준)·P0-2(시정 완료) 미갱신. 명세상 "구현 완료 후" 의무 —
  스테일 문서가 다음 세션을 오도하기 전에 커밋 전 완료 권고.

## 게이트 전환 사이클 인계 메모

- 은폐 3파일 손주입 → `tick_volume` 주입 의미 전환 (주석 마커 11곳).
- AST-2 pin 의미 전환 + 8영역/전략 sha 핀 4항목 삭제(커밋 후 자기소멸 TODO).
- 관측 판정 기준(자문): 주 3건↑ would_pass = 게이트 전환 / 0건 = P1-3 래치 선행 /
  일 10건↑ = 스코프 재조사. 다중 레코드 첫-레코드 과소 계상(W1-10)과 H0UNCNT0 통합
  스코프 vs 일봉 J 스코프 불일치는 인지된 노이즈원.
