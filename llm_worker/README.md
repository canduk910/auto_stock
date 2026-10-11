# llm_worker

청산 AI 섀도 기록 워커(cycle446, 사용자 결정 2026-10-11 「히스토리도 남겨두자」). `src/` 밖의
독립 Python 패키지로, 매매 엔진·주문·체결통보 경로를 전혀 모른다. **매매 행위 0** — 여기서
만든 어떤 값도 backend 로 되돌아가지 않는다(워커는 backend 를 GET 만 한다).

멀티데이 보유 5전략(`donchian_swing`·`kojiro`·`vcp_breakout`·`bull_flag_breakout`·`etf_trend`)의
보유 포지션마다 거래일 아침 08:15 KST(재시도 08:35·08:55) 1회 — 「오늘 09:00 시가에 전량
파는 것이 현재 청산 규칙대로 들고 가는 것보다 나을 확률」을 OpenAI 에 묻고 `exit_ai_evaluations`
에 기록만 한다. 어떤 청산 경로에도 들어가지 않는다.

정본 설계 = `_workspace/design/2026-10-11_exit_ai_shadow.md`. 금기·DB 역할·배포 축의 정본은
루트 `CLAUDE.md` 「Docker / 배포」 의 `llm_worker` 항목이다(이 README 가 먼저 쓰여도 그쪽이
정본이다 — 메인 세션이 그 항목을 이 사이클에서 갱신한다).

## 구조

```
lw/config.py      상수(경로·전략 목록·스케줄·캡·모델 기본값) — "/api/..." 리터럴은 이 파일에만
lw/http.py        G0/G1 호출(허용 경로 화이트리스트, journal_worker 와 같은 꼴)
lw/db.py          자동커밋 단문 DB 접근(트랜잭션 금지)
lw/features.py    `src/engine/llm_features.py` 에서 복사한 지표 함수(ema·rsi·atr·macd·hv·
                  compute_technicals). backend 쪽 `tests/unit/engine/test_cycle446_feature_parity.py`
                  가 드리프트를 잡는다
lw/prompt.py      청산 프롬프트(SYSTEM_PROMPT) + 전략별 청산 규약 설명 + 출력 검증(클램프 금지)
lw/targets.py     대상 선정 — 허용 전략 ∧ buy_date<=bar_date ∧ quantity>0
lw/bars.py        확정 일봉 판정 — 헤드 봉은 오늘 06:00 KST, 그 전 봉은 (bas_dd+1일) 06:00 KST
lw/exit_shadow.py Runner — G0/G1 호출 → 사후 채움 → bar_date 결정 → 대상마다 평가/기록
lw/outcome.py     사후 채움 — 다음날 시가(next_open_won) + 실제 결과(outcome_status)
lw/schedule.py    08:15/08:35/08:55 KST 루프(EC2 cron 0 — 컨테이너 재시작에 일정이 안 묶인다)
lw/__main__.py    진입점 `python -m lw`
ops/role.sql      워커 전용 DB 역할 — 마이그레이션이 아니다. migration 050 뒤 사람이 psql 로 1회 실행
```

## 한 회전 (`lw/exit_shadow.Runner.run_once`)

1. `EXIT_AI_MODE=off` 면 `exit_ai_runs.status=disabled` 만 쓰고 끝(G0/G1 호출 0).
2. G0 호출 — 엔진이 멈췄거나 `phase=="idle"` 이면 `status=engine_not_running`(쓰기만, 평가 0).
3. G1 호출 실패 = `status=g1_failed`.
4. **사후 채움 먼저** — `next_open_won`(전날 평가의 반사실 시가) + `outcome_status`(오늘 G1 에
   없는 열린 평가를 `trade_history` 로 닫는다. `trade_journal_orders.source` 로 수동 청산
   여부(`exit_is_manual`)도 함께 판정한다).
5. `069500`(KODEX 200) 일봉으로 `bar_date` 결정(직전 영업일, 휴장일 달력 대신).
6. G1 `items` 를 허용 전략·매수일·수량으로 걸러 대상 목록(`targets.select_targets`).
7. 대상마다 — 이미 `result=ok` 인 행이면 skip · `attempts >= 3` 이면 skip · 확정 안 된 봉이면
   `skipped reason=provisional_bar` · OpenAI 키 없으면 `failed reason=no_key` · 일일 상한
   도달이면 `failed reason=cap_exceeded` · 그 밖은 LLM 호출 → 출력 검증 → `exit_ai_evaluations`
   upsert(종목 단위 예외 격리 — 한 종목 실패가 다른 종목 평가를 막지 않는다).
8. `exit_ai_runs` 하루 1행 upsert(`status` = `done`/`partial`/`no_targets`/…).

## 격리 (journal_worker 와 같은 규약)

- `src` import 0 · KIS 앱키 접두 변수 0 · 메인 `.env` 0 · 체결통보·WebSocket 0 · KIS REST 호출 0.
- 읽는 환경변수 = `LLM_DATABASE_URL`·`OPENAI_API_KEY`(둘 다 `secrets/llm_worker.env`) ·
  `API_REPORTER_KEY`·`EXIT_AI_MODE`·`EXIT_AI_MODEL`(compose `environment:`, 비밀 아님).
- HTTP 허용 경로 = G0 `GET /api/trading/status?include=system,holdings,strategies` ·
  G1 `GET /api/balance/exit-lines` 둘뿐.
- 동시 요청 0 — LLM 호출도 한 건씩 순차(`gather`/`create_task`/`TaskGroup` 0).
- DB = 자동커밋 단문만(트랜잭션 0).
- 가드 = `llm_worker/tests/test_lw_isolation.py`.

## 테스트

```bash
cd llm_worker && python -m pytest tests/ -q      # 워커 자체(격리·대상 선정·확정 판정·출력 검증·오케스트레이터)
python -m pytest tests/unit/engine/test_cycle446_feature_parity.py -q   # backend 지표 동등성
python -m pytest tests/unit/ast/test_cycle446_ast_exit_ai_scope.py -q   # 매매 경로 무접촉
```
