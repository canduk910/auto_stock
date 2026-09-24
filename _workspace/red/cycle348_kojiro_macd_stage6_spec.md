# cycle348 — `[kojiro_macd_observe]` 를 국면6 크로스(role=stage6_gc)까지 확장 (명세)

사용자 결정 2026-09-24: 「MACD 관측기를 국면6까지 기록하도록 확장」. **관측 전용 — 매매 행위 0.**

## 왜
cycle344 관측기는 보유(held)·strict entry 최종 후보(candidate)만 기록한다. 국면6 종목은 strict entry(국면1)를
못 넘으므로 한 줄도 안 남는다. cycle346 의 B6 규칙(= **ATR 밴드 ∧ 국면6 ∧ gc3**, 64건·CI 0 포함·한 종목 의존)을
실매매 유니버스에서 **앞으로** 재려면 그 사건을 기록해야 한다(`_workspace/domain_consult/cycle346_macd_early_entry_paired.md` 끝 「메인 세션 정정」).

## 행위 명세

B1. **수집 위치** — `KojiroStrategy.prepare()` ticker 루프에서 step6(스테이지 판별 가능, `stage_valid_t.append(ticker)`) **직후**,
    보유 stamp 블록 **앞**. step5(ATR 밴드)를 이미 통과한 종목만 대상이 된다 = B6 정의와 같다.
B2. **조건** — `stage == 6` 이고 마지막 봉(D-1 완성봉 = `enriched.iloc[-1]`)에서 `gc3` 사건.
    `gc3` 정의는 cycle344 `_macd_observe_row` 와 **동일**(직전봉 `macd3 <= sig3` ∧ 이번봉 `macd3 > sig3`) — 새 정의를 쓰지 말고
    `_macd_observe_row(enriched, stage)` 의 결과 `row[7]` 을 재사용한다. **상태(`m3 > s3`)로 바꾸는 것 금지.**
    `stage != 6` 이면 `_macd_observe_row` 를 **부르지 않는다**(추가 계산 최소).
B3. **stash** — 새 로컬 dict(예: `macd_s6_raw: dict[str, tuple]`)에 **15원소** 튜플 = 기존 12원소 행 + `(bar_date, prev_close, atr_val)`.
    기존 `macd_raw` 의 12원소 계약과 `observe_macd` 시그니처·held/candidate 행 서식은 **무변경**(기존 테스트가 그대로 초록이어야 한다).
B4. **수집은 자기 try** — 수집 코드(헬퍼 메서드로 분리 권장, 예: `_stage6_gc_observe_row(enriched, stage, bar_date, prev_close, atr_val) -> tuple | None`)가
    어떤 예외를 던져도 그 ticker 의 이후 처리(held stamp·step7·step8·후보 등록)는 **그대로** 진행한다. 루프 바깥 try 로 떨어지면 안 된다
    (떨어지면 보유 stamp·후보 등록이 스킵 = 행위 변경).
B5. **emit** — leaf `src/engine/kojiro_band_observe.py` 에 새 함수(예: `observe_macd_stage6(macd_s6_raw)`)를 두고,
    `prepare` 에서 `observe_macd` 호출 **다음**, `self._scanned_tickers = ...` **앞**에 **별도 try** 로 부른다.
    호출 실패 흡수는 `absorb_macd_call_failure(...)` (MACD 마커로 흔적 — band 흡수기 재사용 금지).
B6. **행 서식** — 같은 마커 `[kojiro_macd_observe]`, **WARNING**. 기존 held/candidate 행과 **같은 필드를 같은 순서**로 쓰고(`role=stage6_gc`),
    끝에 `bar=<YYYYMMDD> close=<int> atr=<소수2자리>` 를 **덧붙인다**. `rule6/5/4` 도 기존과 같은 계산(stage6 행이면 `rule6=gc3∧all_up`).
    값 서식은 기존 `_num`/`_fmt` 규칙(비수치 `-`).
B7. **cap** — (a) 키 `(ticker, "macd:stage6_gc")` 1회/일(`_cap` KstDailyEmitCap 공유, held/candidate 슬롯과 안 다툼)
    (b) **일일 상한 60줄**(모듈 상수, 예: `STAGE6_GC_DAILY_LIMIT = 60`). KST 날짜가 바뀌면 카운트 리셋.
    상한을 넘는 종목은 기록하지 않고, 그 배치 끝에 **요약 한 줄**(WARNING, 같은 마커):
    `[kojiro_macd_observe] role=stage6_gc cap_reached=1 limit=60 suppressed=<N>` — 하루 1회만(재실행 prepare 에서 중복 금지).
    `reset_kojiro_band_observe_cap()` 가 이 카운터도 초기화한다(테스트 격리).
    방출 순서 = stash 삽입 순서(유니버스 순회 순서).
B8. **never-raise** — leaf 본체 전체 try, 개별 ticker 실패는 그 ticker 만 건너뜀, 15원소가 아니면 skip.
B9. **매매 무변경(핵심)** — `_candidates`·`_scanned_tickers`·`ranked_final`·`held_only`·`stats`(모든 키)·funnel 기록(`_record_funnel_pipeline_step`
    인자)·`_held_stage3`·`_bought_today` 가 확장 전과 **완전 동일**. 테스트로: (i) 수집 헬퍼를 raise 스텁 (ii) leaf 를 raise 스텁
    각각에서 `stats`/`get_scanned_tickers()`/`_candidates` repr 이 정상 실행과 동일. 국면6 종목은 여전히 step7 에서 `stage1_up_ex` 로 탈락한다.
B10. **추가 I/O 0** — `await`/DB/HTTP 추가 없음. 이미 계산된 `enriched` 만 읽는다. `DEFAULT_PARAMS` 신규 키 0.

## 가드·핀
- `kojiro.py` 를 sha/세그먼트로 핀하는 AST 가드 전수 재핀(cycle344 = 전체 sha 10곳 + `prepare` 세그먼트 1곳 + `_SRC_TREE_DIGEST`, `test_cycle287` 은 2곳).
  `grep -rln "kojiro" tests/unit/ast tests/unit/deploy` 로 찾는다. 재핀은 **값만** 바꾸고 가드 논리는 무접촉.
- 기존 구조 가드(예: `test_g273_17b` 흡수기 호출 횟수, cycle344 의 `_macd_observe_row` 호출 지점 수 등)가 붉어지면 **가드를 느슨하게
  하지 말고** 그 가드의 의도를 확인해 team-leader 에 보고 → 명세 조정 후 갱신.
- `scheduler.py`·8영역 무접촉.

## 돌연변이 (최소 5종, 전부 KILL 이어야 한다)
M1 gc3 정의 뒤집기(상태 `m3>s3` 로) · M2 `stage == 6` → `stage != 6`/`>=5` · M3 role 문자열 누락/오기(stage6_gc→candidate) ·
M4 15원소 계약 파괴(끝 3필드 누락 or 12원소로) · M5 매매 경로 오염(수집 헬퍼 예외가 루프 try 로 새게 — 자기 try 제거) ·
M6 일일 상한 제거 · M7 요약 줄 중복(하루 2회) · M8 leaf 호출이 `observe_macd` 와 같은 try 에 합쳐짐.

## 문서
`src/engine/strategies/CLAUDE.md`(kojiro 행 관측기 서술) · `src/engine/CLAUDE.md`(`kojiro_band_observe.py` 절) 현재형 갱신 ·
`docs/HARNESS_CHANGELOG.md` 상단 cycle348 한 항목.

## 명세 조정 (team-leader, Red 후)
- B7 카운터는 **새 가변 모듈 전역을 두지 않는다**(`test_c12b_leaf_writes_only_its_own_cap` 의도 = 가변 공유 상태 금지).
  일일 카운트 = 오늘 `_cap` 에 기록된 `(ticker, "macd:stage6_gc")` 키 수, 요약 1회/일 = 별도 cap 키 `("-", "macd:stage6_gc:summary")`.
  날짜 리셋·테스트 격리는 `KstDailyEmitCap` 자기 리셋과 `reset_kojiro_band_observe_cap()` 의 `_cap` 교체로 얻는다.
  `KstDailyEmitCap` 에 키 열람 수단이 없으면 **leaf 쪽에서** 세지 말고, `daily_emit_cap.py` 에 읽기 전용 헬퍼를 가산하는 것은 허용
  (기존 동작 무변경 · 그 파일을 핀하는 가드가 있으면 재핀).
- `STAGE6_GC_DAILY_LIMIT` 는 불변 상수라 `test_c12b` 허용 집합에 **그 이름 하나만** 추가한다(cycle340 `MACD_MARKER`/`_RULE_STAGES` 추가와 같은 종류).
- `test_c12c` 공개 함수 목록에 `observe_macd_stage6` 추가.
