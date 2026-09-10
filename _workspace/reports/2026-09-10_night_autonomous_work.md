# 09-11(금) 새벽 리포트 — 목요일 밤 자율 작업 (09-10 20:25 ~ 09-11 03:30 KST)

> 사용자 지시(09-10 20:1x): "오늘 작업 모두 진행하고나서 9/8 자문 브랜치 내용 가져와서 읽어보고
> 추가진행. 수면 중이니 승인 없이 권고대로 진행한 다음 모두 통합해서 리포트로 보고."
> 사용자 지시(20:0x): "병렬로 진행해 / 대신 커밋은 분리해서 해."
> 사용자 취침 선언 20:25 "끝나면 통합 리포트 올려줘. 난 이제 자러갈게. 오전 7시쯤 기상예정."
>
> **낮 구간(09-10 16:17~21:00 일부)은 이미 보고됨** — `_workspace/reports/2026-09-10_thursday_autonomous_work.md`.
> 이 리포트는 그 뒤(20:25 이후)의 밤 작업만 다룬다. 중복 서술 없음.

---

## 0. 집계 창과 세는 기준

| 항목 | 값 |
|---|---|
| 집계 창 | **2026-09-10 20:25 ~ 2026-09-11 03:30 KST** |
| 커밋 범위 | `149030e..c782b9c` (main) |
| 커밋 총계 | **25건** = 코드 11 · 테스트 2 · 문서 8 · 병합 4 |
| EC2 backend 재기동 | **6회** (21:07 · 21:27 · 22:40 · 00:17 · 02:26 · 03:26) — 전부 장외 |
| 서버에 올린 작업 묶음 | **11** = cycle270-C · 272 · 273-pre · 273b-F7 · 273a · 273b(I3) · 273c · 273d · 273e · 273f · 274 — 21:07 에 올린 cycle270-B 는 **같은 밤 cycle270-C 로 대체돼 11 에 세지 않았다**(배포 이력 표 §1 에는 실행 사실로 남긴다) |
| 장중 중단·매매 사고·기동 오류 | **0** |
| 최종 테스트 | 전체 스위트 **8,228 PASS**(12 skip · 328 xfail · 13 xpass, 4분 20초) — 측정 시점은 **마지막 코드 병합 `477449b`**. 이후 `be8cfc2`(문서)·`c782b9c`(핀 비우기)는 전체 스위트를 다시 돌리지 않고 관련 가드 **211건**만 재확인했다 |
| 최종 EC2 상태 | 마커 `c782b9c`, 03:26 재기동, 6분 창 ERROR/CRITICAL 0 |
| scheduler.py | 3,898 → **3,872L** (상한 3,900) |

### 0.1 커밋 분류 (한 창으로 전수)

- **코드 11** — `45e91f6`(273-pre) · `0638e53`(270-C) · `407cf01`(273d) · `f7395a7`(272) ·
  `a60f43e`(273b-F7) · `a3349e6`(273c) · `b7b3d28`(273f) · `dad24bc`(273a) · `39db6c0`(273b I3) ·
  `2c1f190`(273e) · `3d4a19b`(274)
- **테스트 2** — `c8932d0`(CI 시각 의존 핫픽스) · `c782b9c`(8영역 sha 핀 4곳 비우기)
- **문서 8** — `9ac74b2` · `0fb2a88` · `4ca3463` · `aa31761` · `be8cfc2` +
  주간 자문 v2/v3 3건(`41a9d24` · `01ef3fa` · `b8545b3`, **작성 시각은 09-10 12:05~12:17 로 창 밖**,
  23:40 PR #22 병합으로 창 안에 들어옴)
- **병합 4** — `dc2ecbd`(PR #22 주간 자문) · `46c10cd`(그룹 2) · `133d6bc`(그룹 1) · `477449b`(cycle274)

### 0.2 창 밖이지만 기록할 것

- **20:57 커밋 `1df6d7d`(cycle270-B, 토큰 재발급 21:30) → 21:07 배포.** 커밋 범위(`149030e..`)
  **앞**이라 25건 집계에 들어가지 않는다. 같은 밤 무발화로 판명돼 cycle270-C 가 대체했다(§2).
- **09-10 낮 배포 2회**(17:45 cycle270 · 18:58 cycle271)는 낮 리포트 소관.

---

## 1. 배포 이력 (전부 EC2 실측 검증)

| 시각(KST) | 커밋 | 내용 | CI / Deploy | EC2 |
|---|---|---|---|---|
| 21:07 | `1df6d7d` | cycle270-B — 보조 시세계정 토큰 강제 재발급 15:45 → **21:30** | CI `34474080978` success · Deploy success | 재시작. 밤 재기동이라 포지션 복구·풀 시작 로그 없음(정상) |
| 21:27:31 | `0638e53`+`9ac74b2` | cycle270-C — 같은 시각 **21:30 → 19:00** 재이동 + cycle273 정본 문서 13파일 | CI `34476065693` success · Deploy `34476797141` success | 마커 `9ac74b2`, ERROR/CRITICAL 0, 주계정 토큰 재발급(만료 09-11 21:27) |
| 22:40:3x | `f7395a7` | **cycle272** — VB·LTV `main` 목표가 기준 시가를 KRX REST 단일 출처로 교체 | CI `34483250736` success(22:40) · Deploy `34484099386` success(22:40:54) | 마커 `f7395a7`, backend·frontend 재생성, `Application startup complete`, 4분 창 ERROR/CRITICAL 0, 컨테이너 안 `import src.engine.open_price_rest` OK(`MODE_ENFORCE="enforce"`) |
| 23:58 | `46c10cd` | 그룹 2 병합(273d·273c·273f) | CI `34492553474` **failure**(00:04) · Deploy **skipped** | **미배포** — EC2 는 `f7395a7` 유지 |
| 00:17:4x | `c8932d0` | 위 그룹 2 + 시각 의존 테스트 핫픽스 | CI `34493691372` success(00:16:49) · Deploy `34494583890` success | 마커 `c8932d0`, ERROR/CRITICAL 0, 컨테이너 안 `daily_load=18:10:00` · `mode=enforce` 확인 |
| 02:26 | `aa31761` | 그룹 1 병합(273-pre·273b-F7·273a·273b I3·273e) + 문서 | CI `34507403202` success · Deploy `34508239998` success(full) | 마커 `aa31761`, backend·frontend 재생성, 6분 창 ERROR/CRITICAL 0, 컨테이너 안 `import src.engine.selling_reconcile` OK + `risk._TICK_BUY_EVAL_SKIP_STRATEGIES == {donchian_swing, kojiro}` |
| 03:26 | `c782b9c` | **cycle274** — VB·LTV 매수 신호 LLM 평가 게이트 **shadow** + 문서 + 핀 정리 | CI `34513501773` success · Deploy `34514363454` success(full) | 마커 `c782b9c`, backend·frontend 재생성, 6분 창 ERROR/CRITICAL 0, 컨테이너 안 `import llm_buy_gate/llm_features` OK · `settings.openai_buy_gate_model=gpt-5.6-luna` · `openai_api_key` 설정됨 · VB/LTV `DEFAULT_PARAMS.llm_gate_mode=shadow` |

- **재기동 6회 전부 장외**(20:10 정산 이후). 장중 재시작 0, `market_blind_secs` 발생 없음.
- 문서 전용 커밋(주간 자문 3건 등)은 CI `paths-ignore` 로 배포 자체가 없다.
- 밤 재기동은 07:55 `_boot` 전이라 포지션 복구·풀 시작 로그가 없는 것이 정상이다.
  **모든 사이클은 09-11 07:55 부팅부터 유효**하다.

---

## 2. cycle270-B → cycle270-C — 토큰 재발급 시각 재이동 (내 제안 오류의 시정)

### 2.1 무슨 일이 있었나

- 09-10 20:0x 사용자: "토큰 재발급 20:00 이후로 옮겨도 되지 않아?" → 내가 **21:30** 을 제안 →
  사용자 **"21:30 좋아"** → 커밋 `1df6d7d` → 20:57:56 푸시 → 21:07 배포.
- 같은 밤 D8(cycle273f) 명세 §7 이 지적: `scheduler.start()` 는 20:10 정산 뒤 `finally` 가
  `_quote_token_refresh_task` 를 포함한 task 를 **전부 cancel**(`scheduler.py:1013`)하고
  `_running=False`(`:1045`) 로 만든다. `_wait_until(21:30)` 은 **영원히 깨어나지 않는다.**
- 09-10 20:10:15 운영 로그 "매매 시스템 종료" 가 실측 근거다.
- 무발화의 **확정 근거는 코드**다(20:10 정산 뒤 `finally` 가 `_quote_token_refresh_task` 를 cancel,
  `scheduler.py:1013` / `:1045`). ⚠️ **21:39 까지 `[quote_token_refresh]` 0행은 실측 증명이 아니다** —
  cycle270-C(19:00)가 **21:27:31 에 이미 배포·재기동**돼 21:30 시점의 코드에는 21:30 이 없었다.
  그 0행은 "21:30 이 안 깨어난다" 와 "21:30 코드가 이미 없다" 를 구별하지 못하므로,
  **반증이 없다는 정도의 보조 증거**로만 읽는다.

### 2.2 왜 못 잡았나 (원인)

- 제안 단계에서 메모리 정본 "23:00/05:00 은 루프 밖이라 불가"(`project_daily_load_schedule.md`)와
  **대조하지 않았다.**
- 종전 `test_c9` 의 단언 "**문턱 > 20:15**" 이 오히려 T 를 루프 사망 뒤로 밀어냈다.
  **가드가 결함을 승인한 사례**다.

### 2.3 시정 (cycle270-C, `0638e53`)

- `quote_token_refresh.py:118` `TIME_QUOTE_TOKEN_REFRESH = time(19, 0)`.
  루프 안에서 가장 늦고 가장 조용한 시각이다 — 창 `[18:50, 19:08]` 예정 작업 0,
  19:50 NXT 매수 중단·20:00 자문 앞.
- `test_c9` 재정의: "T < TIME_SETTLEMENT" · "T+8분 < 20:00".
  종전의 "문턱 > 20:15" 단언은 **삭제**했다(그것이 결함의 통로였다).
- **신규 영속 가드 `test_c10`** — 주기 루프 시각 7종 전수가 20:10(정산) 미만임을 강제.
  23:00/05:00 기각에 이은 **두 번째 재발 차단 장치**다.
- 8영역·`scheduler.py` diff 0.

### 2.4 사용자 승인과의 편차 (사후 통지 대상)

- 사용자가 승인한 값은 **21:30**, 실제 배포된 값은 **19:00** 이다.
- 사용자 요구 "20:00 이후"는 **스케줄러 루프 수명 구조를 바꾸지 않는 한 불가능**하다.
  구조 변경은 별도 사이클이고 8영역·`scheduler.py` 승인 대상이다.
- → 결정 카드 D9(사후 통지·이의 접수).

---

## 3. cycle272 — VB·LTV `main` 목표가 기준 시가를 KRX REST 단일 출처로 교체 (사용자 결정 D1)

### 3.1 무엇을 했나

- 좁은 목 `on_open_price_confirmed(..., board="main", *, source="ws")` — `source` 신뢰 목록은
  `("rest",)` 뿐이고 기본값이 불신 `"ws"` 라 WS 확정 경로는 조용히 거부된다.
- 킬스위치 `open_price_scope_mode`(전략별 `DEFAULT_PARAMS`, 기본 `"enforce"`, `"off"` 만 롤백,
  PUT 즉시 반영).
- 신규 행위 leaf `src/engine/open_price_rest.py` — R1 **09:00:35** + 30초 간격 9라운드 →
  5분 간격 슬로우 ~15:20, 종목 간 0.05s, `rest_zero`/`rest_error`/`no_tick` 분리, `owns_board` ~09:05.
- 마커 4종 `[main_rest_basis_config|round|confirmed|unresolved]`.
- `pre_nxt`/`post_nxt` 보드는 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉.

### 3.2 사용자 질문 "장 시작 시점 REST 확보 가능한가" 에 대한 답

| 축 | 실측 |
|---|---|
| 시간 | N=75~140 종목 직렬 **12~28초**, 09:01:13 이전 종료 |
| 한도 | KIS 20건/초 한도의 **30~45%** |
| 충돌 | 09:00~09:01:30 매수 주문 실측 **0건**(09-08·09-09) |
| 값의 준비 | 09:00:05 에 **1/3**, 09:00:30 넘기면 **97%** |

→ R1 을 **09:00:35** 로 확정했다.

### 3.3 진입 영향 (예상, 실측 아님)

- 후보-레벨 3영업일 실측: 09-08 **−24.4%** · 09-09 **−3.6%** · 09-10 **+17.1%**(합 −4.8%).
  **날마다 부호가 바뀐다.**
- 목표가 이동폭 중앙값 **+85.3bp**, 평균 +196.1bp, 상승(= 진입 어려워짐) 방향 68%.
- ⚠️ 자문 §9 의 단일값 "**−27.6%**" 와 나란히 놓지 말 것 — 레짐별 분포로 읽어야 한다.

### 3.4 검증

- Verify **GO**: 뮤테이션 27종(행위 KILLED 26 · 등가 1 · **ESCAPED 0**), 전체 **7,745 PASS**,
  8영역 diff 0, scheduler 3,898→3,897L, cycle264 핀 6개 불변
  (`check_buy`/`check_exit`/`calc_buy` byte 동일 = 여섯 가지 무접촉의 기계적 증거).
- tester 비차단 6건:
  - **MEDIUM #1** 준비 폴링 타임아웃이 task 를 종결시켜 07:59 재-prepare 뒤에도 leaf 가 사망 →
    **커밋 전 반영**(일정 루프 낙하 + `test_c19_2` 낙하 단언, 뮤테이션 KILLED, 258 PASS).
  - **MEDIUM #2** 재시작이 `_targets` 를 지운다 → **금요일 07:45 부팅 시 VB·LTV enabled 유지 필수**
    (현재 enabled).
  - LOW 3(round 마커 mode 상수 고정 · 전략별 2행 중복 calls · 벽시계 45s > 간격 30s) → 판독 규칙으로 이관.
  - INFO 1(`[breakout_open_confirm] main` 09:00:1x 의도된 침묵).

---

## 4. cycle273 그룹 2 — D5·D3·D8 (커밋 `46c10cd` → 핫픽스 `c8932d0`, 00:17 배포)

### 4.1 J1 = cycle273d (D5) `407cf01` — 보유·익일청산 종목 일봉 강제 포함

- `scanner._stock_master_daily_load_once` 에 보호 집합(보유 ∪ 익일청산,
  `_collect_protected_tickers_for_scanner` 재사용) OR 포함 + `list_all` 실패 대비 `forced_extra` 합집합.
- 실행당 1행 `[daily_load_protected_forced] protected= forced_in_universe= forced_extra= tickers=`.
- 신선도 게이트·15:40 오늘봉 필터 무접촉, VCP backfill 비오염.
- Verify GO. 신규 47케이스 PASS · 뮤테이션 11/13 KILLED(2건은 기존 가드가 방어).
- `scanner.py` 8영역 sha 핀 등록 `f999183c…`(후속 커밋 `c782b9c` 로 비움).
- 후속 등재: `forced_in_universe` 의미 가드 · F-D5-a docstring 10억 정정.

### 4.2 J2 = cycle273c (D3) `a3349e6` — 고지로 후보 순위 성분 원설계 복원 + shadow

- 성분① `(macd3[li] − macd3[pi]) / 3 / close` — `/종가` 누락이 순위표를 **주가 순위표**로 만들고 있었다(ρ=+0.853).
- 성분② `bw[-1] / mean(bw[-6:-1]) − 1` — 단일봉 + `1e-9` 분모가 6→1 전환 직후 상시 폭발하고 있었다.
- 성분③(신선도) 비복원 · nan/inf 중립화 · 가중치 무접촉 · **매수 후보 집합/순서 무접촉(C9)**.
- shadow leaf `kojiro_band_observe.py` — `[kojiro_band_observe]` bar/exp1/exp5/slope_pct/score,
  12원소 stash, never-raise.
- Verify 2라운드 NO-GO(r1 isfinite 가드 무검정·관측 원자료 무커버·leaf 배치 except 무검정 /
  r2 헬퍼 except 폴백·bar 원천·scores 배선 무검정) → **테스트 4건 추가로 봉인**.
  뮤테이션 3종 KILLED 재확인, `kojiro.py` sha 불변 `bfc61480…`.
- 문서 6곳 동기화(순위 식에 분모 명시 = 재발 방지).
- **투명 공개**: Green r2 중 `git checkout` 으로 라운드 1 구현이 유실돼 수기 복원했다. sha 일치 확인함.

### 4.3 J3 = cycle273f (D8) `b7b3d28` — 일봉 적재 16:00 → 18:10

- `scheduler.py:66` 리터럴 1개 + 주석 정직화 7곳. 라인 3,898 유지, 8영역 diff 0.
- 시간외 단일가(~18:00) 물량이 그날 봉에 들어온다.
- 겹침 0 — 16:1x~16:40 작업은 일봉보다 먼저, 19:00 토큰 문턱(18:50)보다 앞.
- **부수 효과**: 유니버스 판정이 오늘치 raw 로 바뀌어 회전 위상이 하루 당겨진다 → D5 와 함께 배포했다.
- 워크플로가 J2 NO-GO 로 중단돼 **메인 세션이 직접 구현**(명세·보류 테스트 그대로).
  `g273f_6` 은 cycle270-C `test_c10` 채택으로 삭제, `test_cycle122` 상수 단언 18:10.

### 4.4 CI 실패 → 핫픽스 (`c8932d0`)

- `46c10cd` CI `34492553474` **failure** — `test_cycle264_open_source_compare.py::test_c2_source_label_never_breaks_confirm_loop`
  1건, 00:04 KST. Deploy skipped.
- 로컬 23:5x 전체 스위트는 통과했다 → **시각 의존 결함**.
  cycle272 의 `owns_board = now < 09:05` 때문에 00:00~09:05 KST 에 실행되면 백스톱 루프가
  VB·LTV 를 건너뛰어 확정 0 이 된다.
- 창 안에서 확정 루프 12파일 재실행 → 실패 2건(위 + `tests/integration/test_confirm_open_prices.py::test_confirm_falls_back_to_kis_api_when_open_price_missing`).
- 핫픽스 = 두 테스트에 `owns_board=False` 고정(백스톱 경로가 계약). 179 PASS.
- **교훈(영속 후보)**: 시각 창 게이트(`owns_board`·`open_entry_hold`)를 도입하는 사이클은
  그 창에 걸리는 기존 테스트를 freezegun/seam 으로 고정해야 한다.
  로컬 실행 시각이 CI 실행 시각과 다르면 초록이 거짓 양성이다.

---

## 5. cycle273 그룹 1 — 5항목 (병합 `133d6bc` + `aa31761`, 02:26 배포)

### 5.1 I0 = 273-pre `45e91f6` — `kojiro_gap_observe` 반사실 필드 `ws_collapse`

- 14번째 필드로 **순수 append**(기존 13필드 byte 불변), `kojiro.py`·8영역 무접촉.
- 어휘 판정 이력: `clear` 는 이 리포에서 "청산" 이라 기각 → `allowed`.
  `ws_open<=0` 은 `-`(false-safe 방지).
- 경로 B(`on_tick`) 행은 동어반복 — **경로 A 행만 오염 판정에 유효**(계약 테스트로 고정).
- Verify GO(뮤테이션 9/9 KILLED).

### 5.2 I1 = 273b-F7 `a60f43e` — stale `_selling` 재대조 블록을 leaf 로 위임

- `scheduler.py` 3,898 → **3,871L**(−27). `[selling_hold]` 3분기 가시화.
- Verify 2라운드 NO-GO(r1 1-ticker 관측 격리 테스트 공허·logger 정체성·AST 파일 미이관·경계 /
  r2 logger 정체성 뮤테이션 M12 ESCAPED·AST 파일·rmn=0 M13)
  → **메인 세션이 테스트만으로 닫음** — logger `src.engine.scheduler` 고정 가드, rmn=0 해제 가드,
  AST 가드 이관 + AST3 매처를 cycle258 `emit_once` 표준 형태까지 확장.
- 뮤테이션 M12·M13 KILLED 재확인, ast+engine **5,203 PASS**.

### 5.3 I2 = 273a (D2 가) `dad24bc` — 잔여취소 타이머 order_no 게이트

- `_pending_cancel_order_no[ticker]=order_no` 신설 — 매수·매도 전량 체결 분기에서
  **order_no 일치 시에만** cancel+pop. `_pending_cancel_tasks` 가 ticker 키·매수매도 공유라
  그대로 pop 하면 매도 전량체결이 매수 잔량취소 타이머를 죽인다(U-A).
- `update_trade_status(*, match_partial=False)` opt-in 2곳 + KST 당일 하한.
- **Verify r2 NO-GO HIGH = 진짜 결함**: Green 이 KST 하한을 `str` 로 TIMESTAMPTZ 에 바인딩 →
  실 asyncpg+postgres 에서 `DataError`. 매수축 3단 우회 전건 재현, 매도축 `_handle_sell_fill`
  중단 = PENDING 영구 잔존.
  스위트 7,612 전건이 초록이던 이유는 **실 PG 로 그 경로를 통과시키는 테스트가 0건**이었기 때문이다
  (사이클 M6 DATE str 사고와 같은 계열).
- 메인 세션 시정: `datetime.fromisoformat` + `test_b2d` 타입·값 단언 + 실 PG 왕복 테스트(docker, 12 PASS)
  + AST5 영속 가드 + 역방향 뮤테이션(str 복원 시 2건 RED) 확인.
- **교훈(규약 추가)**: 새 DB 경로는 **실 PG 왕복 테스트 필수**.

### 5.4 I3 = 273b (D2 다) `39db6c0` — `update_trade_status` WHERE 에 `order_no`

- 이 사이클의 **가장 중요한 발견의 시정**이다 — §7 참조.
- `update_trade_status(*, order_no=None, match_partial=False)` keyword-only.
  미전달 시 SQL **byte 동일**(opt-in), 전달하면 `AND order_no = $n`.
- `order_engine.py` C1~C6 호출부 **6곳 전부**가 지역 변수 `order_no` 를 그대로 전달.
  가장 위험한 곳은 C5/C6(CANCELLED 분기) — 같은 ticker 의 매수 A 잔여취소와 매도 B 잔여취소가 겹치면
  order_no 없는 WHERE 가 A 를 노리다 B 를 CANCELLED 로 뒤집을 수 있었다.
- `affected > 1` 이면 `[trade_status_multi_update]` WARNING 1행 — F-1 과 같은 커밋이라
  order_no 가 있는 호출은 부분 UNIQUE 인덱스(migration 029) 때문에 **구조적으로 발화 불가능**해진다.
  즉 과거를 재는 측정기가 아니라 **WHERE·인덱스 후퇴를 잡는 영구 감시자**다.
- 검증 GO(라운드 2). NO-GO 5건 처리 — HIGH = AST1 이 키워드 **이름**만 보고 `order_no=ticker`
  같은 오배선을 통과시키던 결함(뮤테이션 M12 ESCAPED 실측) → **값 검사 + 행위 테스트**로 강화.
- 표적 46 + 실 PG 왕복 32 PASS · AST 926 PASS · 뮤테이션 프로덕션 14종 KILLED / ESCAPED 0.
- 잔여 LOW 3 중 2건은 `aa31761` 로 처리, 테스트 더블 seam(M12)은 후속 **F-273b-4**.

### 5.5 I4 = 273e (D2 나) `2c1f190` — kojiro WS 틱 매수 평가 skip

- `risk.py:79` 근처 모듈 상수 `_TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})`
  신설 + `:646` 기존 donchian 전용 `continue` 를 멤버십 판정으로 in-place 치환(자리·순서 불변).
- 근거(자문 `cycle273_kojiro_gap_gate_20260910.md`): 09-07 코호트 N=103 에서
  **WS 시가 ≠ KRX 확정 시가 95.1%**, 진짜 갭업 탐지 **0/8**, 최대 오차 6.77%p.
- kojiro 매수는 경로 A(`_swing_buy_poll_loop`, REST `stck_oprc`, 09:05~09:30 분당 1회×25회)만 남는다.
  후보 집합 무손실은 코드 레벨로 증명(`_scanned_tickers ⊇ _candidates.keys()`).
- 킬스위치 없음(자문 §3.3 — 실패 방향이 매수 감소 단방향, 롤백은 1행 revert).
- Verify GO. 뮤테이션 12/12 KILLED. 8영역 `risk.py` **단독**, `scheduler.py`(3,873L) diff 0.
- MEDIUM 1 = 명세 §8.1 표는 테스트 1건 교체만 열거했는데 사전 존재 테스트 2건이 추가 반전됨
  (**승인 범위 초과 기록**). LOW 2 = 반전 테스트의 양성 대조 부재 · 틱 갱신 순서 간접 관측 소실.
- **사용자 결정(22:5x) "F-3도 오늘 밤에 같이 올려"** → 금요일 이월 계획을 폐기하고 같은 밤 배포.
  D+1 귀인 분리는 전략별로 나눠 읽으면 된다(cycle272 = VB·LTV, F-3 = kojiro).

### 5.6 병합

- `133d6bc`(--no-ff, 충돌 7파일: sha 핀 4파일 합집합 · 하네스 표 15행 유지(cycle270-B 21:30 행 제거) ·
  changelog·워크리스트 양쪽 보존) → scheduler **3,872L**.
- 전체 스위트 **7,906 PASS**(12 skip · 328 xfail · 13 xpass, 4분 15초).

---

## 6. cycle274 — VB·LTV 매수 신호 LLM 평가 게이트 **shadow** 배선 (03:26 배포)

### 6.1 발의와 지시

- 사용자 21:5x: "매수신호가 나올 때마다 OpenAI API를 GPT-5.6-luna모델로 호출해서 … 기술지표들과
  30일 일봉을 함께 넘겨서 매수평가 … 1~100점 … 70점 이상일 때만 매수."
- 내 답 = 가능, 5요소 설계 → 사용자 **"그 순서로 진행해. 큐 끝나면 자문부터 시작하고 shadow 로 배선해줘."**

### 6.2 도메인 자문 (00:39 완료, `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md` 851줄)

| 결정 | 내용 |
|---|---|
| 가능성 | 가능 — 8영역 접촉 0, leaf 2 + 전략 2파일 3줄 |
| 트리거 | **신호 시점 단독**(pre-warm 은 호출 17배·표본 불변이라 shadow 에서 제외) |
| 평가 자리 | `return Signal.BUY` 직전(cycle262 자리 계약) |
| 동기 hot path | `await` **0**(`create_task`) |
| 래치 | 1회/(전략,종목)/일 **필수** — 09-10 DB하이텍 하루 6콜 실측 |
| 타임아웃 | 4~5초는 **반증**됨(같은 모델 이 리포 내 실측 6.1~11.3초, 중앙값 9.8초) → shadow **20초** |
| 비용 | 신호 시점이면 **월 $0.41~1.06**(574~1,484원 = 순자산의 0.02~0.06%). cap 20/전략 최악 월 $8.45 |
| enforce 의 진짜 비용 | **진입 지연** → `slip_bp` 실측 필수(핵심 신설) |
| 판정 기간 | **2주로는 임계 70 검증 불가** — 10영업일 왕복 24건, 구간당 8건이면 승률 표준오차 ±17%p. **2주 배관 + 추가 4주(총 6주) 임계**(자문 Q4·§628 표기와 일치) |
| 선결 | VB·LTV 켜져 있음(운영 DB enabled=true·비중 0.05). 09-10 자문 문서의 "꺼짐" 기술은 stale |

- 열린 질문 Q1~Q10 → 결정 카드 D2·D3.
- **부수 발견(§8.5, 범위 밖)**: 운영 DB VB `k_period=15` → `days=17 < min_required=22` 로
  아침 prepare 의 일봉 DB 경로가 전 후보 구조적으로 죽고 KIS 폴백으로만 읽힌다.
  행위 결함은 아니나 별도 티켓(**F-274-2**).
- EC2 `.env` `OPENAI_API_KEY` 설정 확인(값 미열람, 존재만) · `OPENAI_RECOMMEND_MODEL=gpt-5.6-luna`.

### 6.3 구현 (`3d4a19b` → 병합 `477449b`)

- 신규 leaf `src/engine/llm_buy_gate.py` — `observe_signal` 동기 never-raise.
  비용 순서 = mode → 카나리아 → off return → 래치 peek → cap peek → 값 복사 → 래치 mark → `create_task` 1회.
  `_evaluate` 세마포어 2 · 일봉 캐시 `(ticker, KST date)` 상한 400 · 당일 봉 폐기 ·
  `AsyncOpenAI` json_object · `wait_for` · 출력 검증 클램프 금지 · `CancelledError` re-raise.
- 마커 = `[llm_gate_config]`(off-return **앞** 카나리아) ·
  `[llm_buy_score]`(score/would_block/slip_bp/verdict_lag_ms/latency_ms/rationale 60자) ·
  `[llm_buy_score_failed] reason=timeout|api_error|parse_error|schema_error|payload_error|no_bars|no_key|disabled_model` ·
  `[llm_gate_daily_cap]`.
- 신규 leaf `src/engine/llm_features.py` — EMA/RSI/MACD/ATR/HV/채널/거래량 정규화 순수 함수,
  §3.3 **24필드 화이트리스트** 스냅샷, `json.dumps` **try 밖**.
- VB·LTV 3곳(import · `DEFAULT_PARAMS` 4키 · 호출부 try/except) · `config.openai_buy_gate_model="gpt-5.6-luna"`.
- 킬스위치 = `PUT /api/strategies/{vb|ltv}/params {"llm_gate_mode":"off"}`(즉시).

### 6.4 검증이 잡은 것 (이 사이클의 가치)

- **Red 312케이스(RED 270, C1~C18 전부 배치)**, 자문과의 이견 14건 기록.
- **검증 r1 NO-GO 10건**:
  - **CRITICAL** — payload 의 `now_kst` datetime 이 `json.dumps` 에서 터지고 `except: "{}"` 가 삼켜
    **운영의 모든 호출이 빈 페이로드로 나갈 뻔했다**(실패 마커조차 0행).
  - **HIGH** — 거래량 축 5필드 미산출(`normalize_volume_ratio` 호출자 0).
  - **HIGH** — 스냅샷이 min_score·mode·model·cap·timeout 을 모델에 노출(**합격선 유출**).
  - MEDIUM 2 · LOW 4. 뮤테이션 19 KILLED / 0 ESCAPED(등가 2).
- **검증 r2 NO-GO 5건**: HIGH 래치 순서 AST 가드가 cap 경고 mark 미끼에 속아 필수 뮤테이션 M3 ESCAPED ·
  MEDIUM `{}` 폴백 부재 직접 가드 없음 · LOW 3. 뮤테이션 11 KILLED / 3 ESCAPED. 전체 8,143 PASS.
- **메인 세션 봉인(03:0x, 테스트 가드 2 + 소스 1줄)**: `test_c5_5` 를 `_latch.mark_emitted` 한정 +
  전량 선행으로 조임 · `build_messages` 직렬화 실패 전파 테스트 + 소스 텍스트 가드(`"{}"` 0건,
  `json.dumps` try 밖) 신설 · rationale 120→60자(`_DbLogHandler` 500자 컷 대응 — 구조화 필드가
  rationale 앞이라 컷에도 생존, 꼬리는 잘릴 수 있음 → **F-274-1** 2행 분리 후속).
- 신규 4파일 **322 PASS** · 워크트리 ast+engine **5,758 PASS**.

### 6.5 shadow 기본값 (행위 0 이라 결정 불요 — 통지)

Q1 켜진 상태 유지 · Q2 LTV 프리장 포함 · Q6 cap 20/전략 · Q7 `system_logs` + EC2 덤프 스크립트 마커 등재 ·
Q9 래치 1/일 · Q10 temperature 미지정.

### 6.6 승인이 필요한 것 (→ 결정 카드 D3)

- **호출부 try/except 흡수기** — 자문 §5.1 의 "1줄" 원안은 C2(관측 예외에도 반환 동일)와 충돌한다.
- **cycle233 C233-F1 가드 최소 확장** — try 양 분기 BUY 귀결 인정.
- 승인이 안 나면 원안 1줄로 되돌리고 핀을 재산출한다.

---

## 7. 가장 중요한 발견 — 손익 정의 2종 불일치의 원인은 산식이 아니라 **데이터 오염**

정본 = `_workspace/analysis/2026-09-10_pnl_definition_mismatch.md`(읽기 전용 조사).

### 7.1 증상

D8(v3 자문)이 지적한 두 가지 손익 집계 값이 서로 달랐다.
차이는 5월 **−72,620원** · 6월 **−5,290원** · 06-18 이후 잔여 **−670원**(5건)이다.

### 7.2 원인

- `update_trade_status` 의 UPDATE 가 `order_no` 없이 `(ticker, trade_type, PENDING, strategy)` 로
  매칭하고 **LIMIT 도 없다**(`trade_history.py:110-117`).
- 그래서 한 체결통보가 **여러 PENDING 행에 같은 price·profit_loss 를 도배**했다.

### 7.3 물증

삼천당제약 SELL 3행이 **서로 다른 날짜인데** `price=306,000` · `profit_loss=−8,500` 으로 동일했다.

### 7.4 시정

- 같은 밤 **cycle273b I3**(§5.4)가 WHERE 에 `order_no` 를 넣어 닫았다.
- `[trade_status_multi_update]` WARNING 이 재발 탐지기로 남는다.

### 7.5 남는 것

- 도배가 지금도 나는지는 확인 불가 — 마지막 물증이 07-22 이고 `system_logs` 는 08-11 부터만 남아 있다.
- 5월 오염 행의 참값은 **복원 불가**.
- 06-18 이후 잔여 −670원(5건)은 밤 넘긴 포지션의 매수가가 증권사 평균매입가에서 오기 때문이다.
  그 값이 손절 기준가라 전환은 **매매 행위 변경**이다 → 별도 결정.
- **`nass_amt`(total_asset) 도 T+2 지연인지 미확인** — 그렇다면 일별 수익률 분모가 흔들린다(D5 후속).
  T+2 가설은 `deposit == total_asset 2영업일 지연` 원 단위 일치로 재확인했다.

---

## 8. 조사 3건 (전부 읽기 전용, 코드 무접촉)

### 8.1 입출금 기록(`net_external_cashflow`) 산식 결함 — 확정

사용자: "입출금은 없었어, 산식 점검해줘."

- 현재 산식(`scheduler.py:3620-3632`):
  `net_ext = (오늘 dnca_tot_amt − 어제 dnca_tot_amt) − (오늘 매도금 − 오늘 매수금)`.
- `dnca_tot_amt` 는 **D+0 예수금**(`src/api/balance.py:214`)이다. 국내주식은 T+2 결제라
  오늘 Δ예수금은 실제로는 **D−2 매매의 결제**를 반영한다.
  거기서 오늘 매매를 빼면 `(D−2 매매 − D 매매)` 크기의 허수가 남는다.

| 모델 | 잔차 절대값 중앙값 (16영업일, 08-20~09-10) |
|---|---|
| `Δdeposit(D) − net_trade(D−2)` (T+2 정합) | **2,813원** (수수료·세금 크기) |
| 현재 기록값 `net_external_cashflow` | **367,270원** |

- 일자별: 09-08 −367,270 → 잔차 −2,870 · 09-09 −603,545 → −2,415 · 09-10 +489,647 → −2,813.
- **결론: T+2 시점 불일치로 확정. 입출금이 아니다.**(스크립트 `scratchpad/cashflow_check.py`, 읽기 전용)
- **영향 범위**: `daily_profit_rate`·`cumulative_return_rate` 는 이 값을 쓰지 않는다
  (분모 = 전일 total_asset) → **수익률은 무해**. 이 필드와 그것을 보는 화면·자문만 오염된다.
- 시정안 = **cycle275**(명세 완료, 구현 안 함) — §9.

### 8.2 VCP 단조 수축 조건 정량화 (D3′) — 완화 4안 전부 **비권고**

정본 = `_workspace/analysis/2026-09-10_vcp_monotonic_quantification.md`(domain-expert).

- 모집단을 자문의 `excluded_sample` 23행이 아니라 **step7 탈락 전수 135행**(5영업일)으로 복원했다.
  재현 4중 대조 전부 통과.
- **자문 전제 반증** — "등호도 거부해 폭이 같기만 해도 탈락" 은 사실이 아니다.
  단조 위반 56행 중 반등 배수 =1.00 **0건** · ≤1.05 **0건** · ≤1.10 **2건**,
  중앙값 **1.58배**(수축이 아니라 **확장**이다).
- **진짜 병목 = 수열 길이**. strict 통과율 n=2 **50%**(동전던지기) · n=3 **11%** · n≥4 **0%**.
  통과 16행 중 14행이 회수 2회 → 옵션 ③ `pullback_count_max` 확대는 정확히 **0행**.
- 완화안별 5영업일 실질 신규(피벗 근접·우선주/펀드 제외 후):
  (a) 등호 **0** · (b) +5% **0** · (c) +10% **0**(확장 베이스 합법화 반례 251970) ·
  (d) 마지막<첫 **2종목**(0.4/일, 하나는 strict 가 나흘 뒤 스스로 잡음, 우선주·리츠·하락추세 동반).
- `last_pullback_max` 는 **0.12 에서 이미 비구속**(0.15 의 추가 효과 0 재확인).
- **1순위 권고 = 관측 전용 변경**(`vcp_breakout.py` 단일, 순증 8줄: step7 탈락 사유에
  `[fail=count|monotonic|width seq=…]` 병기, 행위 0, 테스트 계약 10건 초안) → **결정 카드 D5**.
- 2순위 우선주·리츠·인프라펀드 유니버스 제외(행위 변경, 자문 선행).
  3순위 `_detect_base` 창 선택 안정화(010955 하루 만에 75일→51일, 15종목 흔들림).
  `min_swing_atr_mult` 튜닝은 봉우리형 반응 + 집합 교체라 **금지 명문화** 권고.
- 열린 질문: 표본 5영업일 단일 레짐 · step5 EMA 앞단 배제 상한/하한 · 079940 재적재 불일치.

### 8.3 포지션 한도 초과 7/7 원인 분류 — 척도 불일치, **캡 관통 0건**

정본 = `_workspace/analysis/2026-09-10_position_over_cap_classification.md`.

- 분류: **(a) 1주 폴백 7 / (b) ATR 배관 0 / (c) 중복 보유 0 / (d) 비중 재조정 0**.
  초과 7건 전부 수량 1주이고 진입일 예산 기준 설계 수량 0주다.
  `[fallback_cap_skipped]`·`[ratio_cap_skipped]` 08-11~09-10 **0행** = ATR 배관 결함 반증.
- **척도 불일치** — 리포트의 "한도 초과" = 관측기 **1.0× 상한**, 실제 차단 문턱 = **K_ρ 2.5배**.
  7일 18행 중 13행이 그 사이(설계상 차단하지 않는 구간)다.
  K_ρ 초과 5행은 전부 kojiro 000815 한 보유(캡 배포 이전 진입)다. **캡이 뚫린 사례 0건.**
- 스냅샷 과소 계수: 20:08 스냅샷은 잔존 포지션만 세어 당일 청산 전략(VB·momentum·LTV)의
  초과 랏을 못 잡는다(09-09 실제 4건 vs 스냅샷 1). 정본은 `[oversized_fallback]` 이다.
- **v3 자문 D2′ 전제와 반대** — BFB·VCP 는 09-09~09-10 내내 **K_ρ 2.5 로 돌았다**
  (실측 3건: 09-09 09:05 BFB `k=2.50` · 09-10 09:18 BFB `k=2.50` · 09-10 12:16 VCP `k=2.50`).
  → 어젯밤의 20 은 "복원"이 아니라 **2.5 → 20 완화**다.
- **내일(금) 방향 = 증가 예상**:
  momentum·VB·LTV 재활성 0.05(상한 25,533~44,684원인데 일봉 모집단 33~49%가 더 비싸다) ·
  BFB·VCP K_ρ 20 = ρ축 상한 실효 소멸(상한 = 잔여예산 383,009원 = 순자산 15%).
  09-10 12:16 차단됐던 VCP 095610(2.80배)이 오늘은 통과한다.
- 인프라 triage: 잔고 500 = KIS 서버측·재시도 흡수·조치 불요(단 `api_metrics` 가 날마다 못 세는 것이
  진짜 결함) · 레짐 실패 = 매매 영향 0, 로그 문구 없는 가드라 리포트 오탐 ·
  틱 신선도 = cycle252 기지, stale 10종목 중 5가 현재 보유.

---

## 9. cycle275 명세 작성 완료 (00:3x, 코드 무접촉 — 승인 대기)

정본 = `_workspace/red/cycle275_net_external_cashflow_spec.md`(§0~§7).

- 설계: KIS output2 `prvs_rcdl_excc_amt`(가수도정산금액)를 `AccountSummary.settled_deposit_d2`(기본 0)로
  파싱(`balance.py` 1줄) → 마이그레이션 043 가산형 컬럼 `daily_performance.settled_deposit` →
  leaf `settlement_cashflow.py` 순수 함수 → `net_ext = Δsettled − net_trade(D)`(잔차 ≈ 수수료·세금).
- 전환 첫날은 prev 가 없으므로 0 + 마커. 구 행은 NULL(구 산식 값 표시 주의).
- **`prvs_rcdl_excc_amt` 의 산식 정의는 미확정**(§2.2) — KIS 공식 예제에서 한글명만 확인했고,
  배포 후 실측으로만 간접 검증할 수 있다. 실제 16일 재현은 이 필드 이력이 DB 에 없어 불가 → 합성 시나리오.
- **scheduler 접점 4~6행 때문에 사이클 전체가 승인 대상**(§4) → 오늘 밤 구현하지 않았다.
- Red 17건 목록(§5), `nass_amt` T+2 판별 읽기 전용 SQL(§7) 준비 완료.
- **매매 행위 변경 0** — 순수하게 정산 기록 로직이다.

---

## 10. 주간 자문 반영 (PR #20 09-08 · PR #21 09-10 · PR #22 v2/v3 후속)

### 10.1 적용한 파라미터 (사용자 "PUT허용" 승인 후 21:31:14)

| 전략 | 키 | 전 | 후 | 근거 |
|---|---|---|---|---|
| long_tail_volatility | `trailing_stop_rate` | −1.2 | **−2.0** | 09-08 자문 권고 |
| long_tail_volatility | `overnight_stop_loss` | −2.0 | **−3.5** | 09-08 자문 권고 |
| vcp_breakout | `last_pullback_max` | 0.10 | **0.12** | 09-10 자문 — "0.15 는 선택지가 아니다"(폭 단독 위반 6행이 0.12 에서 통과, 0.15 추가 통과 0) |

- 첫 시도 422 = 바디에 `params` 래퍼 누락(라우트 `ParamsRequest`), 재시도 성공.
- 라이브·DB 동시 확인, `strategy_config.updated_at` 21:31:14. 비중·enabled 무접촉.
- 효과 관측 기준선(09-08 자문 §6): LTV avgW 1.97% / WR 27.8% / RR 0.65 → 15왕복 뒤 비교 ·
  VCP step7 survived 기준 1/1/1/1/2 → 5영업일 중 3일 ≥3(0.12 는 +약 1.2건/일 기대).

### 10.2 K_ρ 20 임시 복원 (사용자 "K_ρ는 20으로 표본수집을 위해 임시복원", 21:32:40)

- `PUT` BFB·VCP `max_lot_ratio_mult` = **20.0** success. 나머지 5전략 2.5. DB `updated_at` 21:32:40.
- ⚠️ §8.3 실측이 **이것을 "복원"이 아니라 "완화"로 재정의**한다(09-09~10 은 2.5 로 돌고 있었다).
- 2.5 로 덮인 경위는 미조사 — `[ratio_cap_config]` 는 전략별 첫 랏 산출 시 1행이라 09-08 덤프에
  BFB·VCP 행이 0건이고, 09-09 09:05 행은 이미 `k=2.50` 이다. **09-05~09-09 사이**에 덮였고
  정확한 시점은 INFO 2일 보존 만료로 특정 불가.
- 유력 원인 = `PUT /api/strategies/{id}/params` 가 기존 키 병합 후 in-memory params **전체**를 저장
  (`routes/strategies.py:176-182`) → UI 폼이 낡은 값(2.5)을 실어 보내면 덮인다.
- 후속 권고 = 설정 변경 감사 로그(`[params_updated]` 키·전후값) 부재 → 워크리스트 등재.

### 10.3 BFB 브레이크이븐 승격 활성 (사용자 "BFB도 켜보자", 21:45:29)

- VCP 는 08-18 부터 `breakeven_promote_atr=1.5` 활성이나 체결 0건이라 미발화였다.
  BFB 는 0.0(G-8 게이트 "첫 체결 뒤 재평가") 이었고 보유 3건으로 조건이 충족됐다.
- `PUT` BFB `breakeven_promote_atr` = **1.5** success. 코드 경로 `bull_flag_breakout.py:1231-1244`.
- 영향: 오늘 07:55 부팅에서 BFB 보유 3건(성광벤드·가온전선·티에프이) 복구 시
  고점 ≥ 매수가 + 1.5×ATR 인 종목부터 래치.

### 10.4 자문 항목별 반영 현황 (09-10 자문 기준)

| 자문 항목 | 반영 |
|---|---|
| 권고 1건 VCP `last_pullback_max` 0.10→0.12 | ✅ 21:31 PUT |
| D1 비중 감사 공백 + VCP 20% | ✅ 사용자 20:39 재조정(7전략 활성) |
| D2 0.12 적용 | ✅ |
| D3′ VCP strict 단조 수축(탈락 88%) | 🔎 §8.2 정량화 완료 → 결정 카드 D5 |
| D3 포지션 한도 초과 7/7 | 🔎 §8.3 분류 완료 → 결정 카드 D6 |
| D4 cycle265 착수 | ✅ cycle272 배포(22:40) |
| D5 `net_external_cashflow` | ✅ §8.1 산식 결함 확정 → cycle275 명세(D4) |
| D6 momentum/VB/LTV 비활성 사유 | ✅ 사용자 재활성(20:39) |
| D7 일일 튜너 auto_apply OFF 유지 | ✅ 현행 유지 |
| §4 인프라 반복(잔고 500 · 레짐 실패 · 틱 신선도) | 🔎 §8.3 triage(수정 없음) |
| §6 V1~V7 다음 주 검증 | D+1 확인 목록에 편입 |
| 수집 실패(`strategy-funnel/recent` 인자 필수) | ✅ 루틴 프롬프트 명시(21:01) |

### 10.5 D9 루틴 프롬프트 정정 (21:01)

주간 자문 트리거 프롬프트 갱신 — 편향 재실측(98.1%) 반영 · `/api/history` days 없음 ·
`strategy-funnel/recent` strategy_id 필수 · K_ρ "라이브가 정본 + 불일치 조사 중" ·
kojiro 0.19 삭제 → "비중·enabled 는 라이브 값만 인용" + 09-10 20:39 참고값 · cycle272 REST 기준가 사실.
일일 리포트 프롬프트에는 낡은 수치가 없어 변경 0.

---

## 11. 운영 파일 변경 (EC2, git 밖)

`~/auto_stock/_observation_dumps/dump_daily_observations.sh`(20:00 cron) 마커 목록:

| 시점 | 마커 수 | 백업 |
|---|---|---|
| 밤 시작 전 | 4 | — |
| 21:0x | 12 | `.bak-0910` |
| 03:2x | **20** | `.bak-0911` |

추가된 것: `[main_rest_basis_config|round|confirmed|unresolved]`(cycle272) ·
`[bfb_breakeven_promote]` · `[vcp_breakeven_promote]` · `[quote_token_refresh]` ·
`[llm_buy_score]` · `[llm_gate_config]` · `[llm_buy_score_failed]` · `[llm_gate_daily_cap]` ·
`[kojiro_band_observe]` · `[selling_hold]` · `[trade_status_multi_update]` · `[daily_load_protected_forced]`.
`bash -n` OK. INFO 2일 보존 대응 — 09-11 20:00 첫 덤프가 D+1 판독 정본이다.

---

## 12. D7 Basic 자격 회전 — 실행 완료 (09-11 03:28, 밤의 마지막 조치)

- EC2 `tools/ops/rotate_basic_auth.sh` 실행. `secrets/.htpasswd` 교체
  (백업 `secrets/.htpasswd.bak-20260910182818`).
- **새 비밀번호는 EC2 `secrets/.rotated-20260910182818`(권한 600) 파일에만 있다.**
  화면·로그·이 보고서 어디에도 적지 않았다.
- nginx reload 불필요(파일 bind mount). 사용자 계정 2개 모두 회전 —
  `ubuntu`(대시보드) · `reporter`(20:20 루틴).
- **사용자 즉시 할 일 (오늘 20:20 전 필수)**:
  1. EC2 에서 `cat ~/auto_stock/secrets/.rotated-20260910182818` 로 새 값 확인
  2. 클라우드 루틴 환경의 `REPORTER_BASIC_PASSWORD` 갱신
     (일일 리포트 `trig_01E6XNiNTxaLWNn7jeTXR9qZ` · 주간 자문 `trig_01H1TtfhP52CXKuyxwG2KnBW`)
  3. 대시보드 `https://auto.dkstock.cloud` 재로그인(`ubuntu` 새 비밀번호)
  4. 확인 뒤 `.rotated-*` 파일 삭제
- 갱신 전에는 20:20 리포트가 **401 로 실패한다** — 회전의 예정된 부작용이다.

---

## 13. 결정 항목 10건 (급한 순)

| # | 제목 | 무엇인가 | 권고 | 안 하면 |
|---|---|---|---|---|
| **D0** | **Basic 비밀번호 회전 후속** | 새 비밀번호가 EC2 파일에만 있다. 클라우드 루틴과 브라우저가 아직 옛 값을 쓴다 | 오늘 20:20 전에 4단계 처리(§12) | 오늘 20:20 일일 리포트가 401 로 실패한다 |
| **D1** | **BFB·VCP K_ρ 20 의 만료 조건** | 09-09~10 실측은 2.5 로 돌고 있었으므로 20 은 복원이 아니라 완화다(§8.3). ρ축 상한이 실효 소멸 상태다 | **첫 VCP 체결 확인 직후 2.5 복귀**(PUT 즉시). 표본 수집 목적이면 종료 시점을 정해 달라 | v3 자문 D2′ 와 충돌한 채로 상한이 계속 열려 있다 |
| **D2** | **cycle274 enforce 규약 3문** | Q3 실패 시 규약(fail-open / fail-closed / 자동 낙하) · Q4 판정 기간(2주 / 2주+4주) · Q7 보존(system_logs+덤프 / 신규 테이블) | Q3 **fail-open**(발의 문장 "70점 이상만"과 다르므로 명시 확인 필요) · Q4 **2주 배관 + 4주 임계** · Q7 현행 유지 | shadow 관측이 끝나도 enforce 로 못 넘어간다 |
| **D3** | **cycle274 범위 + 구현 승인 2건** | Q8 donchian 추가 검토(유일한 유의 음 기대값 t=−2.95, 폴링 경로라 지연 비용 0) · Q2 enforce 시 LTV 프리장 포함 · Q9 enforce 래치. 그리고 호출부 try/except 흡수기 + cycle233 가드 최소 확장 | Q8 **검토 착수** · Q2·Q9 shadow 기본값 유지 · 흡수기 **승인** | 흡수기 미승인 시 원안 1줄로 되돌리고 핀을 재산출해야 한다 |
| **D4** | **cycle275 입출금 산식(T+2) 승인** | 명세 완료, 코드 무접촉. `scheduler.py` 접점 4~6행이라 승인 대상. 매매 행위 변경 0 | 승인 시 금요일 저녁 구현·배포(**20:10 정산 전 배포 금지 → 20:20 이후**) | 입출금 기록이 매일 수십만 원대 허수를 계속 쓴다(수익률은 무해) |
| **D5** | **VCP 관측 로그 변경 승인** | step7 탈락 사유를 술어별로 병기(`vcp_breakout.py` 단일, 순증 8줄, 행위 0) | **승인 권고.** 완화 4안 자체는 **비권고** | 다음 자문이 같은 완화안을 다시 권고한다 |
| **D6** | **한도 초과 척도 정렬** | 리포트의 "한도 초과"(1.0×)와 실제 차단 문턱(K_ρ)이 다르다 | 1.0× 목록 유지 + `k_rho`·`cutoff_won`·`blocked` **병기**. 1주 폴백 → 스킵 전환은 **시기상조** | 매주 자문이 "한도 초과 7/7" 을 집행 실패로 오독한다 |
| **D7** | **B안 채널 분리(8영역 4파일)** | cycle272 는 A안(REST 기준가)이다. B안은 구독 채널 자체를 종목 속성으로 나눈다 | **오늘(금) cycle272 12서명 실측 뒤** 결정 | 통합 채널 오염의 근본은 열린 채로 남는다 |
| **D8** | **후속 티켓 5건 착수 순서** | F-273b-4(cycle271 테스트 더블 seam M12, LOW·테스트만) · F-274-1(`[llm_buy_score]` 2행 분리) · F-274-2(VB `k_period=15` → `days=17<22` 로 일봉 DB 경로 사망) · F-274-3(단가 상수 이원화) · F-274-4(CancelledError 핸들러 AST 가드) | F-274-2 를 먼저(운영 영향 있음), 나머지는 다음 리팩토링 창 | 조용히 쌓인다 |
| **D9** | **토큰 재발급 19:00 사후 통지** | 사용자가 승인한 값은 21:30, 배포된 값은 19:00 이다(§2.4). "20:00 이후"는 루프 수명 구조 변경 없이는 불가하다 | **19:00 유지.** 20:00 이후가 꼭 필요하면 별도 사이클(8영역·scheduler 승인) | 오늘 19:00 에 예상과 다른 시각으로 발화한다 |

---

## 14. 오늘(금 09-11) 확인 목록

부팅은 07:55, 확인은 **제가**(메인 세션) 합니다. 하나라도 어긋나면 항목 번호만 알려 주세요.

### 14.1 부팅 직후 (07:45~08:00)

- [ ] cycle270-C — `[quote_token_refresh] scheduled at=19:00` 1행(배선 확인)
- [ ] cycle272 — `[main_rest_basis_config]` **2행**(VB·LTV), `mode=enforce`
- [ ] cycle274 — `[llm_gate_config]` VB·LTV **각 1행**, 첫 행 `src=default`
      (운영 DB `strategy_config.params` 에 4키가 없으면 `DEFAULT_PARAMS` 로 채워진다)
- [ ] `[ratio_cap_config]` BFB·VCP `mult=20.0`, 나머지 5전략 2.5
- [ ] **VB·LTV `enabled` 유지 확인** — 재시작이 `_targets` 를 지우므로 필수(cycle272 MEDIUM #2)

### 14.2 장중 (09:00~15:30)

- [ ] cycle272 12서명(정본 = changelog 행) — 09:00:35 R1, `[main_rest_basis_round]`,
      `[main_rest_basis_confirmed]`, `[main_rest_basis_unresolved]`, `rest_zero`/`rest_error` 분리
- [ ] cycle273e — `[kojiro_gap_observe] caller=on_tick` **0행** +
      `caller=_swing_buy_poll_loop` **≥6행**(양성 대조 짝)
- [ ] cycle273b — `[trade_status_multi_update]` **0행이 정상**
- [ ] cycle273a — `[cancel_timer_released]` / `[partial_cancel_timer_cleared]`
- [ ] cycle271 — 09:05 `[swing_poll] execute_buy 실패` 오탐 **0**
- [ ] cycle273b-F7 — `[selling_hold]` 3분기 출현
- [ ] cycle274 — `[llm_buy_score]` **4~6행**, score 1~100, `[llm_buy_score_failed]` **<10%**,
      `[llm_gate_daily_cap]` **0행**, VB·LTV 매수 패턴 불변, `verdict_lag_ms` p50/p95 기록
- [ ] BFB — `[bfb_breakeven_promote]` 발화 여부와 직후 whipsaw(판정은 사용자 몫, N 작음)
- [ ] 자문 V3 09:00~09:01:30 체결 0 유지 · V4 race finding 소멸 · V6 over_cap 감소

### 14.3 장후

- [ ] cycle273d — `[daily_load_protected_forced]` 1행
- [ ] cycle273f — **18:10** `[stock_master_daily_load_begin]`·`_summary` 발화.
      `[evening_funnel_capture]` 16:20 정상. ⚠️ 이동 전후 total/fetched **합산 금지**
- [ ] cycle273c — `[kojiro_band_observe]` 발화
- [ ] cycle270-C — **19:00** 계정별 `revoked=True` **7행** + 요약 `accounts=7 issued=7 failed=0` **≤19:08**.
      `expired` 는 09-12 19:0x. **09-12 이후 장중 자연 재발급 0** 이 성공 서명
- [ ] 20:00 첫 20마커 덤프(cron) 생성 확인
- [ ] **20:20 리포트** — D0 회전 후속 전이면 **401 실패가 정상**이다

---

## 15. HTML 에서 단순화한 곳 (대응표)

아티팩트 HTML 에 실제로 쓴 표현만 싣는다. 그 밖의 수치는 HTML 에서 원문 값 그대로 썼다.

| HTML 표현 | 원문 정확값 |
|---|---|
| 약 37만 원 | 367,270원 (16영업일 `net_external_cashflow` 절대값 중앙값) |
| 약 2,800원 | 2,813원 (같은 창 `Δdeposit(D) − net_trade(D−2)` 잔차 절대값 중앙값) |
| 전체 검사 약 8,200개 통과 | 8,228 PASS (12 skip · 328 xfail · 13 xpass) |
| 조정 두 번이면 통과율이 절반쯤 | n=2 **50%** (28행 중 14행) |
| 세 번이면 열에 하나 | n=3 **11%** (18행 중 2행) |
| 새로 통과하는 종목이 0~2개뿐 | 완화 4안 5영업일 실질 신규 = (a) 0 · (b) 0 · (c) 0 · (d) 2종목 |
| 설계 금액의 2.5배 → 20배 | `max_lot_ratio_mult` K_ρ = 2.5 → 20.0 (랏 명목 ρ축 상한 배수) |
| 꺼짐 → 1.5×ATR (손절선을 본전까지 올리는 기준) | `breakeven_promote_atr` 0.0 → 1.5 (BFB) |
| 트레일링 손절 폭 / 밤 넘긴 포지션의 손절선 | LTV `trailing_stop_rate` / `overnight_stop_loss` |
| 마지막 조정의 최대 폭 | VCP `last_pullback_max` |
| 인공지능 매수 평가 | LLM 매수 평가 게이트(cycle274, 모델 `gpt-5.6-luna`) |
| 보조 시세 계정 7개 | `kis_quote_accounts` active 7계정 |
| 서버의 하루 일정표 | `scheduler.py` 의 주기 루프 (`scheduler.start()` ~ 20:10 정산 `finally`) |
| 1분마다 조회 | donchian·kojiro 매수 경로 `_swing_buy_poll_loop` (REST, 09:05~09:30 분당 1회×25회) |
| 파일이 바뀌지 않았음을 확인하는 대조값 | 8영역 소스 세그먼트 sha 핀 |
| 관련 검사 211건 | `be8cfc2`·`c782b9c` 에서 재확인한 가드 211 PASS (전체 스위트 미실행) |

**독자가 오해할 수 있는 지점 4곳** — HTML 본문에도 같은 단서를 넣었다(문구 위치를 함께 적는다).

1. "새로 통과하는 종목이 0~2개뿐" 은 **피벗 근접·우선주/펀드 제외 후**의 실질 신규다.
   원자료 통과 수는 이보다 크다(§8.2). HTML §2 "함께 밝힌 것 셋" 세 번째 항목에
   "우선주·펀드류와 이미 목표가에 붙은 종목을 뺀 실질 신규 기준" 한 문장을 붙였다.
2. "오늘은 통과할 것으로 봅니다" 는 **예상**이다. 실측은 09-11 장중에 나온다(HTML D1 마지막 문장).
3. "매수 상한 20배" 는 두 전략(BFB·VCP)에만 적용된 값이다. 나머지 5전략은 2.5배 그대로다
   (HTML §1 "서버 설정만 바꾼 것" 소표 아래 주석 + 확인 목록 2번 항목).
4. **전체 검사 약 8,200개**는 마지막 코드 병합 시점 측정이다. 그 뒤 두 커밋에서는 가드 211건만
   재확인했다(HTML 바닥글 둘째 줄에 명시).

---

## 16. 배운 점 (영속 후보)

1. **시각 창 게이트를 도입하는 사이클은 그 창에 걸리는 기존 테스트를 시각 고정해야 한다.**
   `owns_board = now < 09:05` 가 CI 00:04 실행에서만 두 테스트를 깼다.
   로컬 23:5x 초록은 거짓 양성이었다.
2. **새 DB 경로는 실 PostgreSQL 왕복 테스트가 필수다.**
   KST 하한을 `str` 로 바인딩한 결함이 7,612 전건 초록을 뚫고 나갔다(사이클 M6 DATE 사고 재발).
3. **시각을 제안하기 전에 스케줄러 루프 수명과 대조한다.**
   21:30 은 20:10 정산 뒤라 영원히 발화하지 않는다. 메모리에 이미 같은 계열 기록이 있었다.
4. **가드가 결함을 승인할 수 있다.** 종전 `test_c9` 의 "문턱 > 20:15" 가 바로 그것이었다.
   시정과 함께 반대 방향 영속 가드(`test_c10`)를 세웠다.
5. **적대 검증은 배포 직전에 가장 비싼 것을 잡는다.**
   cycle274 의 CRITICAL(빈 페이로드 무음)은 운영의 모든 호출을 무의미하게 만들 뻔했다.
6. **워크플로가 중단돼도 메인 세션이 이어받아 닫는 편이 빠를 때가 있다.**
   이번 밤에 3건(273b-F7 · 273f · 273a HIGH 시정)이 그 경로로 종결됐다.

---

## 17. 산출물 목록

### 코드 (신규 leaf 5)
- `src/engine/open_price_rest.py`(cycle272) · `src/engine/selling_reconcile.py`(273b-F7) ·
  `src/engine/kojiro_band_observe.py`(273c) · `src/engine/llm_buy_gate.py`·`src/engine/llm_features.py`(274)

### 자문
- `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`(851줄)
- `_workspace/domain_consult/cycle273_kojiro_gap_gate_20260910.md`
- `_workspace/domain_consult/cycle273_kojiro_rank_restore_20260910.md`
- `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`

### 조사 (읽기 전용)
- `_workspace/analysis/2026-09-10_pnl_definition_mismatch.md`
- `_workspace/analysis/2026-09-10_vcp_monotonic_quantification.md`
- `_workspace/analysis/2026-09-10_position_over_cap_classification.md`
- `_workspace/analysis/2026-09-10_cycle273_U{A,B,C,D}_*.md`(4건)

### 명세
- `_workspace/red/cycle275_net_external_cashflow_spec.md`
- `_workspace/red/cycle273{a,b,c,d,e,f,g}_*.md`(7건)

### 하네스 문서
- 루트 `CLAUDE.md` 표 15행 유지 · `docs/HARNESS_CHANGELOG.md` 상단 append ·
  `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `_workspace/00_leader_trading_rules.md` ·
  `_workspace/00_URGENT_WORKLIST.md`

---

## 18. 남은 상태

- 워킹트리 클린. 8영역 sha 핀 4곳(`scanner`·`kojiro`·`order_engine`·`risk`) **비움 완료**(`c782b9c`).
- EC2 마커 `c782b9c` = main HEAD. 03:26 재기동 이후 재기동 없음.
- 미배포 코드 없음. 대기 중인 승인 = 결정 항목 D0~D9(§13).

---

## 19. 정본 문서의 알려진 불일치 (이 리포트에서 쓰지 않은 값)

- 자문 `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md` 의 **§0 요약(19행)이 표본 크기를
  "10영업일 왕복 15건" 으로 적었으나 §7.6(805행)은 "24건"** 이다. 같은 문서 안의 불일치다.
  이 리포트와 HTML 은 **§7.6 의 24건**(구간당 8건, 승률 표준오차 ±17%p)을 쓴다 —
  후속 계산(24 ÷ 3구간 = 8)이 24 와만 정합한다. **자문 문서 자체는 수정하지 않았다**(읽기 전용 정본).
- 밤 재기동 횟수는 **6회**(21:07 · 21:27 · 22:40 · 00:17 · 02:26 · 03:26)가 정본이다.
  입력 꾸러미가 한때 5회로 셌던 것은 cycle270-B/C 를 한 항목으로 묶은 계수 오류이며 이미 시정됐다.

---
아티팩트(쉬운 말 보고서): https://claude.ai/code/artifact/42b980a4-d35b-4ab2-8621-fb5ed7f6f929 (초판 09-11 새벽)
