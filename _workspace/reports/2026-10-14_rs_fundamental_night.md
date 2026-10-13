# 10-14(수) 아침 리포트 — RS·재무 관찰 개편 밤 작업 (10-13 20:4x ~ 10-14 01:10 KST)

> 집계 창 = 2026-10-13 20:4x KST(1단계 결정) ~ 2026-10-14 01:10 KST · git `0f4e7aa9..dd588bdd`(origin/main).
> 사용자 승인 = 10-13 20:4x 1단계 결정 ①~⑥ · 22:5x 「2단계 승인 · 5시간 자율 · 승인요청 없이 진행 · 자세한 보고」.
> 사이클 = cycle452(1단계) · cycle453(2단계). 이 문서가 정본, 쉬운 말 아티팩트는 이 문서의 축약이다.
> 창 밖 항목 1건 = 01:27 KST `afc9934b`(추가 적재 속도 상한) — **작업 브랜치에만** 커밋·push, main 미반영(§1.1). 타일·커밋 집계에 넣지 않는다.

## 0. 한눈에

| 항목 | 값 | 출처 |
|---|---|---|
| 커밋 | 14건 = 코드 4(feat 2·fix 2) · 테스트 2(test 1·chore 영향 인덱스 재생성 1 — 변경 파일 `_workspace/test_index.yaml` 하나) · 문서 6 · 병합 2 | `git log 0f4e7aa9..dd588bdd` |
| 서버에 올린 묶음 | 2(cycle452 · cycle453), 둘 다 full(backend 재시작) | GitHub Actions Deploy run 592 · 593 |
| 미배포 1회 | 13250728 push 22:04 → CI run 669 실패 1건 → 배포 건너뜀 → 3f6c34ab 로 해소 | GitHub Actions |
| 사고·중단 | 0 — 재시작 2회 모두 장외 창(21:35~익일 07:45) 안 | Deploy 완료 22:50 · 01:03 |
| 매매 행위 변경 | 0 — `scheduler.py`·`scanner.py`·8영역·전략 파일·`strategy_base.py`·`DEFAULT_PARAMS` git diff 0 | `git diff 0f4e7aa9 dd588bdd -- <해당 경로>` = 빈 출력 |
| 변경 규모 | 41 파일 · +19,964 / −2,527 (그중 `src/` 15 파일 +1,344/−8 · `tests/` 14 파일 +3,007/−4) | `git diff --stat` |
| 결정 항목 | 4(카드 4장, 그 외 없음) | 호출자 목록 |

## 1. 배포 이력

| 시각(KST) | 무엇 | 결과 | 서버 |
|---|---|---|---|
| 22:04 | `13250728` merge cycle452 push | CI run 669 실패 1건 `tests/unit/db/test_cycle276_llm_evaluations_db.py::test_m11` — `tests/integration/pg_harness.py` docstring 에 "043" 문구가 있어야 하는데 문서 정리(1단계 ⑤) 중 지웠다 | 미배포 |
| 22:30 | `3f6c34ab` test: pg_harness 문면에 적용 migration 예시(043·…·051) 복원 | CI 성공 → Deploy run 592 성공 22:50, migration 051 적용 | 재시작(full) |
| 00:40 | `dd588bdd` merge cycle453 push | CI run 671 성공 → Deploy run 593 성공 01:03 | 재시작(full) |

- Deploy run 593 로그(메인 세션이 직접 읽어 확인): `mode=full reason=backend_inputs_changed` · `apply: 051_invest_opinion.sql` · `apply: 052_candidate_score_snapshots.sql → CREATE TABLE · CREATE INDEX` · backend 컨테이너 Recreated/Started · 01:03:08 마커(`.deployed_sha`) 기록.
- 문서 전용 커밋 6건(c7b796d9 · 41a0eac6 · 951826d8 · d21381cf · f08e3513 · 65fcb631)은 위 병합 두 건에 함께 실렸다. 따로 배포된 것은 없다.
- 확인 못 함: `/health` 직접 확인 · 재시작 뒤 첫 부팅 로그. 근거는 GitHub Actions 결과와 Deploy 로그뿐이다.
- 서버 마지막 상태(창 끝 01:10) = dd588bdd 배포 완료, backend 재시작 뒤. 창 밖 배포 없음(§1.1 의 수정은 main 에 없다).

### 1.1 창 밖 — 속도 상한 수정 (01:27 KST, main 미반영)
- 발단 = 사실 대조 검토 F2: 초안의 「주문·잔고는 다른 창구라 무관」 은 **틀렸다**. `src/api/base.py` 의 초당 20건 상한(`_rate_limit()` / `_semaphore = asyncio.Semaphore(20)`)은 전역 하나이고, 주문·잔고(`kis_get`/`kis_post`)와 시세 풀(`kis_get_quote`)이 함께 쓴다(세마포어만 다르다).
- 대응 = 메인 세션이 `afc9934b` `fix: 추가 적재 속도 상한 — 시세 한도는 주문과 공유라 평균 초당 약 2회 이하(애프터마켓 보호)` 를 **작업 브랜치에만** 커밋·push.
  - `src/engine/fundamental_load_tasks.py`: `_QUARTERLY_TICKER_SLEEP_SECS = 2.5`(분기 재무 종목당 5 TR 뒤) · `_CALL_SLEEP_SECS = 0.5`(투자의견 창·추정실적 1회 호출 뒤).
  - 효과(예상) = 평균 초당 약 2회 이하 = 한도 20 의 약 10%. 첫 실행이 50분 상한에 걸리면 다음 날 이어 받는다.
  - 테스트 130 passed(새 가드 `tests/unit/engine/test_rs_phase2_extra_load_pacing.py` 포함). 변경 4 파일 +52/−4.
- **main 에는 아직 없다** — 01:3x 에 main push 를 시도했으나 자동 권한 검사가 막았다(승인 필요). 그래서 이대로면 오늘(10-14) 16:40 에는 서버에 있는 이번 변경 전 속도(평균 초당 약 7~8회, 한도의 약 40% — 예상, 실측 없음)로 돈다.
- 다음 배포 가능 창 = 오늘 15:30~16:00(07:45 이후는 장중 배포 금지 구간). → 결정 D1.

## 2. 무엇을 만들었나

### 2.1 cycle452 — 1단계: 계산 부품·KIS 래퍼·저장소 (배선 없음)
명세 `_workspace/design/2026-10-13_rs_fundamental_phase1.md`(sha256 동결) + 개정 `…_amend1.md`.
- `src/engine/rs_score.py` — `ibd_lite_return`(0.4·r63 + 0.3·r126 + 0.3·r189, 190봉 미만·0 이하 가격 `None`) · `percentile_ranks`(0~99, 동점 최소 순위, n==1 → 99) · `sector_relative`(`min_members=5`, `미분류` 섹터 제외).
- `src/engine/fundamental_score.py` — `available_from`/`known_as_of`(결산월 말일 + 90일(회계연도 마지막 달) / + 45일, `fiscal_end_month` 기본 12) · `quarterly_from_cumulative` · `turnaround_flags` · `target_revision_breadth`(창 60평일, 직전값은 창 밖 250평일 허용) · `target_median_change`.
- `src/api/invest_opinion.py` — `FHKST663300C0`(투자의견, 100행 상한 `[invest_opinion_truncated]`) · `HHKST668300C0`(추정실적, raw 통째) — **둘 다 실전 전용**(모의면 호출 0) · `kis_get_quote` 경유 · `_QUOTE_ALLOWED_PATHS` 2 path 등재.
- `src/db/invest_opinion.py` + migration 051(`invest_opinion_history` · `estimate_perform_snapshot`).
- tester 검증 결함 D1~D4 수정(`f21de749`): D1 투자의견 모의 미지원 가드 · D2 저장 결측 행 필터 · D3 비12월 결산(`fiscal_end_month`) · D4 목표가 직전값 창 밖 허용.

### 2.2 cycle453 — 2단계: 적재 배선 + 4전략 부팅 점수 관찰 기록 (매매 행위 0)
명세 `_workspace/design/2026-10-13_rs_fundamental_phase2.md`.
- **추가 적재** `src/engine/fundamental_load_tasks.py` — 매일 16:40 재무 적재 task 의 `once_callable` 을 `data_load_tasks._financial_load_with_extras` 로 바꿔 연간 적재 뒤 `run_extra_loads_once()` 3갈래를 잇는다. 실행은 **매일 확인**하고, 실제로 받는 주기는 갈래마다 다르다.
  - 분기 재무 `div_cls="1"` — 그 분기를 이미 가진 종목은 skip(새 분기가 나올 때만 받는다).
  - 투자의견 `FHKST663300C0` — 주 1회. 최신일 −14일 겹쳐 재개. 최신일 없으면 400일 백필(90일마다 1회). 90일 창, 100건이면 반으로 1회 분할.
  - 추정실적 `HHKST668300C0` — 월 1회 스냅샷. 빈 응답 종목은 그 달 재조회 생략(커버리지 약 160종목 — 명세 §A.3).
  - 시작 창 `16:00 <= now < 19:00` 밖이면 전부 skip(`mode=out_of_window`). 마감 = min(3,000초, 19:30 − 시작 시각). 16:40 시작이면 3,000초(50분)가 먼저라 실효 마감 ≈ 17:30. 멈춤은 종목 경계에서 일어나고 `truncated=1` 을 남긴다. 「반드시 19:30 에 멈춘다」 는 정확하지 않다 — 19:30 은 늦게 시작한 경우의 상한이다.
  - 요일 가드 없음 — 엔진이 켜져 있으면 주말에도 16:40 에 돈다(F6).
  - 킬스위치 `system_config.fundamental_extra_load_mode`(키 없음 = on, `off` = 끔). 마커 `[fundamental_extra_load]` / `[fundamental_extra_load_failed]`.
- **관찰 기록** `src/engine/rs_fundamental_observe.py` — `boot_manager.boot()` 의 `account_cluster.spawn_boot_assign` 바로 뒤에서 await 없이 띄운다. 60초 뒤 4전략(`donchian_swing`·`vcp_breakout`·`kojiro`·`etf_trend`) 부팅 prepare 완료를 최대 600초 기다린다. 후보∪보유 종목별 RS·섹터 RS·재무·목표가 리비전 점수를 `candidate_score_snapshots` 에 upsert. 상한 300초 · 엔진 정지 시 쓰기 없이 종료 · `_BG_TASKS` 보관 · KIS 호출 0. `etf_trend` 는 RS 만 기록(재무·목표가 NULL).
  - 킬스위치 `system_config.rs_fundamental_observe_mode`(키 없음 = record, `off` = 끔). 마커 `[rs_observe]` / `[rs_observe_failed]`.
- 저장소 `src/db/candidate_scores.py` · `src/db/score_inputs.py` · `src/db/invest_opinion.py` 함수 2개 추가. migration 052 `candidate_score_snapshots`(PK `(target_date, strategy_id, ticker)`, 점수 칸 전부 NULL 허용).
- tester 중간 검증 1건 수정(`0febc149`): 연휴 뒤 부팅 즉시 실행 경로에서 추가 적재가 장전·09시대와 겹칠 수 있었다 → 16:00~19:00 시작 창 + 19:30 마감. 낮음 다수 수정: 헛호출 감소 · 의견 14일 겹침 · 관찰 60초 지연 · 투자의견 DB 조회 동시성 3 · 태스크 참조 보관.
- 설계 제약: `scheduler.py` 3,898줄(상한 `<3,900`)이라 여유 1줄 → 새 task 대신 기존 16:40 task 에 얹었다(`d21381cf`).

### 2.3 테스트
- 새 테스트 = 2단계 121 passed · 3 skipped(로컬 PG 없음) + 1단계 121(별도) — 밤 전체 242(약 240). 출처 = changelog cycle452·453 행.
- 로컬 전체 17,144 passed · 9 failed. 9건 = `test_cycle222a3::test_ga3_3e` 1 + `test_c2_suite_isolation` 8. **9건 전부 이번 변경 전 main 에서도 같은 실패를 확인**(호출자 전달, `test_ga3_3e` 포함) — 환경 의존으로 닫는다. CI run 671 은 성공.

## 3. 사전 등록 (동결, 1단계 명세 「사전 등록」 절 그대로)
- 기간: 6개월 또는 그룹(점수 상위 1/3 · 하위 1/3)당 60신호 중 늦은 쪽 — 즉 「6개월 이상, 신호가 모자라면 더」.
- 성공 기준 6항(모두 충족해야 그 항목 채택): ① 상위 1/3 − 하위 1/3 평균 R ≥ +0.3R ∧ 부트스트랩 95% 하한 > 0 ② 돌파 실패율 차 ≥ 5%p ③ 상위 10% 수익 거래 중 하위 1/3 비중 < 40% ④ 6칸 채움률 비하락 ⑤ 섹터 RS(B·C)는 (A)에 더해 +0.1R ∧ 하한 > 0 ⑥ 목표가 리비전은 커버리지 ≥ 60% ∧ ①.
- 실패 = 그 항목 관찰 종료. 통과 뒤 실매매 반영은 전략별 별도 승인(사용자 결정 ⑤).

## 4. 분기·결정 필요 항목 (급한 순)

| # | 내용 | 선택지 | 제안 |
|---|---|---|---|
| D1 | **기한 오늘 16:00.** 추가 적재 첫 실행(10-14 16:40)이 서버에 있는 이번 변경 전 속도로 돌면 평균 초당 약 7~8회 = 한도 20 의 약 40%(예상, 실측 없음)를 최대 50분 쓴다. 이 한도는 주문·잔고와 **공유**한다(§1.1). 속도 상한 수정 `afc9934b` 는 작업 브랜치에만 있다 | (가) 15:30~16:00 에 `afc9934b` 를 main 에 올려 배포 — backend 1~5분 재시작(장 마감 뒤 허용 창이라 보유가 있어도 가능) · (나) 오늘만 끄기 — `system_config.fundamental_extra_load_mode=off`(운영 DB 쓰기라 승인 필요), 수정은 다음 장외 창에 배포 · (다) 그대로 둔다 | (가) 권장. 16:00 까지 답이 없으면 (다) 상태로 두고 16:40 이후 `[fundamental_extra_load]` 요약과 `[kis_rejection]` 을 확인해 보고(자동으로 끄지 않는다 — 끄기는 승인 대상) |
| D2 | 관찰 판정 시점 = 사전 등록 기준(§3) 동결. 그때 판정 보고서 | 확인만 | 지금 할 일 없음 |
| D3 | `etf_trend` 는 RS 만 기록 — 지금 전역 백분위(재무·목표가 NULL, ETF 가 일봉 적재 대상이 아니면 RS 도 NULL). 사전 등록은 「같은 기초지수 ETF 를 대표 1종목으로 묶은 뒤」 | 판독 단계에서 묶기 / 기록 단계부터 묶기 | 판독 단계(워크리스트 기존 방향). 원자료는 종목별로 남는다 |
| D4 | 실적을 쓸 수 있는 날 = 결산월 말일 + 45일(분기) / + 90일(회계연도 마지막 달). leaf 는 `fiscal_end_month` 를 받지만 결산월 입력 출처가 없어 전부 12월로 가정 → 3월·6월 결산 회사는 날짜가 어긋날 수 있다. 해당 종목 수는 세지 않았다 | 소수 편향 허용 / 결산월 데이터 연동 | 우선 허용. 판독 전에 해당 종목 수를 세어 많으면 연동 |

## 5. 다음 확인 체크리스트
| 언제 | 무엇 | 정상 기준 | 누가 |
|---|---|---|---|
| 10-14 07:45 부팅 1~16분 뒤 | `system_logs` `[rs_observe] strategy=…` | 켜진 전략 수만큼(최대 4, 전략당 1). `skipped=prepare_not_done` 이면 그 전략 prepare 지연 | 메인 세션 |
| 같은 날 | `candidate_score_snapshots` `target_date=2026-10-14` 행 수 | > 0, 전략별 후보+보유 수와 맞음 | 메인 세션 |
| 10-14 16:00 전 | D1 답 확인 · (가)면 15:30~16:00 배포 후 Deploy 로그 | (가)면 `afc9934b` 가 main 에 있고 배포 성공 | 메인 세션 |
| 10-14 16:40 이후 | `[fundamental_extra_load]` `mode=on` 요약 1행 · `elapsed_ms` · `truncated` · `[kis_rejection]` 증가 여부 | 1행. 부팅 즉시 실행이 `mode=out_of_window` 1행을 먼저 남길 수 있다 — 그것은 별개 | 메인 세션 |
| 같은 날 | `invest_opinion_history` · `stock_master_financial div_cls='1'` · `estimate_perform_snapshot` 행 수 | 각 > 0, 추정실적 약 160종목 | 메인 세션 |

이상 시: 추가 적재가 매매를 방해하는 징후(시세 조회 지연·`[kis_rejection]` 급증)가 보이면 `fundamental_extra_load_mode=off` 를 승인 요청한다. 관찰 기록 이상은 `rs_fundamental_observe_mode=off`. 둘 다 매매 행위와 무관하다.

## 6. 후속 항목 (범위 밖)
- F11: `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §56 「2단계 (승인 대기 — 이 문서 범위 밖)」 절은 설계 전 예상이다 — `…_phase2.md` 가 대체. 정본 정리 후속.
- `scheduler.py` 3,898줄(상한 `<3,900`) · 다음 번호 cycle454 · migration 053 · 이 범위(RS·재무 관찰)는 클라우드 세션 몫.

## 부록 A. 커밋 목록 (구→신, KST)
| 시각 | sha | 분류 | 제목 |
|---|---|---|---|
| 20:52 | c7b796d9 | 문서 | RS·재무·목표가 리비전 1단계 명세 + 사전 등록 동결(sha256) |
| 21:19 | 4ecab07d | 코드 | RS(IBD-lite)·재무 점수 순수 모듈 + 투자의견·추정실적 KIS 래퍼·저장소 |
| 21:23 | 5f690989 | 테스트 | 영향 인덱스 재생성 |
| 21:56 | f21de749 | 코드 | 1단계 검증 반영(D1~D4) |
| 22:00 | 41a0eac6 | 문서 | 1단계 문서 동기화 |
| 22:04 | 951826d8 | 문서 | migration 051 · cycle452 번호 확정 |
| 22:04 | 13250728 | 병합 | cycle452 |
| 22:30 | 3f6c34ab | 테스트 | pg_harness 문면 043 문구 복원 |
| 22:55 | d21381cf | 문서 | 2단계 적재 일정 제약 · 세션 분담 |
| 22:59 | f08e3513 | 문서 | 2단계 명세 |
| 23:31 | 0aec9fd5 | 코드 | 2단계 적재 + 관찰 기록 |
| 23:51 | 0febc149 | 코드 | 2단계 검증 반영 |
| 00:09 | 65fcb631 | 문서 | 2단계 문서 동기화 |
| 00:40 | dd588bdd | 병합 | cycle453 |
| (창 밖 01:27) | afc9934b | 코드 | 추가 적재 속도 상한 — 작업 브랜치만, main 미반영 |

## 부록 B. 쉬운 말 리포트(아티팩트)에서 단순화한 곳 — 정확값 대응표
| 아티팩트 표기 | 정확값(출처) |
|---|---|
| 「한도의 약 40%」 「초당 약 7~8회」 | 이번 변경 전 속도의 예상치(호출자 전달). 실측 아님 |
| 「약 10%」 「초당 약 2회 이하」 | `afc9934b` 의 쉼(분기 종목당 2.5초 · 호출당 0.5초)에서 나온 예상 평균 |
| 「시세 조회 한도(초당 20번)」 | `src/api/base.py` 전역 초당 20건 상한 — 주문·잔고와 시세 풀이 공유(세마포어만 다름) |
| 「최대 50분」 「16:40 에 시작하면 17:30 쯤」 | 마감 = min(3,000초, 19:30 − 시작). 종목 경계에서 멈춤, `truncated=1` |
| 「약 160종목」 | 명세 phase2 §A.3 「커버리지 약 160종목」 — 예상 |
| 「새 시험 약 240개」 | 1단계 121 + 2단계 121 = 242 (2단계 skip 3 별도) |
| 「커밋 14건」 | 코드 4 · 테스트 2(chore 1 포함) · 문서 6 · 병합 2 |
| 「매매는 그대로」 | 지정 경로 git diff 0. `boot_manager.py`·`data_load_tasks.py`·`src/api/base.py`(허용 path 2개)는 바뀌었다 — 8영역 아님 |
| 「달리기 기록 백분위」(RS 비유) | IBD-lite = 0.4·63일 + 0.3·126일 + 0.3·189일 수익률, 모집단 백분위 0~99 |
| 「최근 약 9개월(거래일 189일)」 | r189 — 거래일 기준이라 달력 9개월과 정확히 같지 않다 |
| 「점수표(관찰 기록)」 | `candidate_score_snapshots` upsert, 전략 객체 쓰기 0 · KIS 호출 0(AST 가드) |
| 「상위 1/3 · 하위 1/3」 「손절폭의 0.3배 이상」 | 사전 등록 그룹 정의 · 기준 ①: 상위−하위 평균 R ≥ +0.3R(R = 진입 때 손절폭 1단위) ∧ 부트스트랩 하한 > 0. 아티팩트는 하한 조건을 생략 |
| 「서버 기록」 | `system_logs` |
