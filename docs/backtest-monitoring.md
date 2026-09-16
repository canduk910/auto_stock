# 백테스트 통합 — 운영 진단 가이드

> 이력: [`history/docs-backtest-monitoring.history.md`](history/docs-backtest-monitoring.history.md)

외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`, stock-manager) 연동을 운영자가 직접
점검하는 절차. 백테스트는 **20:00 AI 자문에만 붙는 검증 부가물**이고 자동매매 흐름과는 격리돼 있다(§6).

> 코드 정본:
> - enqueue + 폴 루프: `src/engine/backtest_orchestration.py` (`_enqueue_backtest_jobs` / `_backtest_poll_loop`) — `recommendation_engine` 이 자문 INSERT 직후 호출
> - YAML DSL 변환: `src/engine/backtest_yaml.py`
> - MCP 클라이언트: `src/services/mcp_client.py` (JSON-RPC 2.0 · 421 세션 만료 시 1회 재초기화 후 재시도 · connect 5s / read `BACKTEST_TIMEOUT_SECS`(기본 300s))
> - 응답 평탄화: `src/engine/backtest_engine.py` (`_extract_metrics` / `_NESTED_METRIC_MAP`)
> - DB: `supabase/migrations/019_backtest_runs.sql` · `020_parameter_recommendations_backtest.sql`
> - UI: `frontend/src/components/recommendations/BacktestComparisonCard.tsx`

---

## 1. 켜고 끄기

**설정 화면 → 외부 통합 → 「외부 백테스트 서버 (KIS MCP)」 토글**이 유일한 운영 수단이다(확인 모달 1회).
`PUT /api/integrations/kis-mcp` 가 `system_config.kis_mcp_enabled` 를 쓴다. **재시작이 필요 없고**
다음 20:00 자문부터 반영된다.

활성 판정 순서 (`mcp_client._check_enabled_async` · `BacktestEngine.is_enabled_async`):

1. `system_config.kis_mcp_enabled` 가 true/false → **DB 값 채택**
2. 키가 없거나 DB 조회가 실패 → `.env` `KIS_MCP_ENABLED`(기본 false) 로 fallback

⚠️ **`GET /api/backtest/mcp/health` 의 `enabled` 는 `.env` 값만 읽는다**(`settings.kis_mcp_enabled`).
DB 토글로 켠 상태에서도 이 API 는 `enabled=false` 로 보이지만 20:00 enqueue 는 정상 동작한다.
켜졌는지는 `GET /api/integrations/kis-mcp` 로 보고, 이 API 로는 **외부 서버 접속 여부(`reachable`)만** 본다.
이 라우트는 어떤 경우에도 HTTP 200 으로 답한다(graceful — 5xx 를 내지 않는다).

```bash
curl -s http://localhost/api/backtest/mcp/health | jq
```

```json
{
  "success": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "tools_count": 4,
    "error": null
  },
  "message": "ok"
}
```

`reachable=false` 면:

- 외부 EC2(`43.202.187.5:3846`) 다운 가능성 → stock-manager EC2 콘솔 점검
- 자문 자체는 정상 발화한다 — `backtest_summary=null` 로 graceful degrade

---

## 2. 20:00 자문 사이클 확인

자문 INSERT 직후 `_enqueue_backtest_jobs` 가 **활성 전략 수 × 2 kind(current/recommended)** 만큼
`backtest_runs` row 를 INSERT 한다. 행 수는 `registry.enabled()` 크기에 따라 달라진다.

| 전략 | 분류 | 결과 |
|---|---|---|
| `momentum` · `volatility_breakout` · `donchian_swing` | (a) 외부 YAML DSL 지원 | queued → running → completed |
| `long_tail_volatility` · `bull_flag_breakout` · `vcp_breakout` · `kojiro` | (b) 미지원 | 즉시 skipped (`YAML DSL 미지원 (Phase 4-bis 로컬 어댑터 대기)`) |

분류 정본 = `backtest_orchestration._SUPPORTED_STRATEGIES` / `_FALLBACK_STRATEGIES`.
MCP 가 꺼져 있으면 (a) 도 즉시 skipped(`MCP 비활성 (KIS_MCP_ENABLED=false)`).

### 2-1. 로그

화면 「로그」 탭 키워드 검색 또는 psql(RDS):

```sql
SET TIME ZONE 'Asia/Seoul';
select timestamp, log_level, message
from system_logs
where timestamp::date = current_date
  and (message like '[backtest_enqueue]%' or message like '[backtest_poll]%')
order by timestamp desc
limit 50;
```

**폴 루프는 살아 있다는 신호를 주기적으로 남기지 않는다** — 60초마다 도는 동안 조용하고 아래 줄만 찍는다.
따라서 "마지막 폴 로그 시각" 으로 생사를 판정할 수 없다.

| 마커 | 언제 |
|---|---|
| `[backtest_enqueue] target=… submitted=N (a)전략=N (b)전략=N enabled=…` | (a) submit 이 1건 이상 성공 |
| `[backtest_enqueue] target=… submit=0 — 폴 루프 발화 skip (enabled=…)` | submit 0 — 폴 루프 자체가 뜨지 않는다 |
| `[backtest_poll] 모든 row 종료 + summary 동봉 완료 — exit: target=…` | 정상 종료 |
| `[backtest_poll] timeout — exit: target=… pending=N` | 24h(`_BACKTEST_POLL_TIMEOUT_HOURS`) 초과 — 미완료 row 를 failed 로 마킹하고 종료 |
| `[backtest_poll] … 실패` / `[backtest_poll] cancelled` / `[backtest_poll] task failure` | 개별 오류 |

### 2-2. `backtest_runs`

```sql
select strategy_id, params_kind, status, mcp_job_id, error_message,
       created_at, completed_at
from backtest_runs
where target_date = current_date
order by strategy_id, params_kind;
```

status 는 `queued` / `running` / `completed` / `failed` / `skipped` 다섯 가지다(migration 019 CHECK).
UNIQUE `(target_date, strategy_id, params_kind)` 라 같은 자문 사이클을 다시 돌려도 row 가 늘지 않는다.

분포만 빨리 보려면:

```sql
select status, count(*) as cnt
from backtest_runs
where target_date = current_date
group by status
order by cnt desc;
```

### 2-3. `backtest_summary` 동봉

동봉 형식은 전략 3키다 — `{"current": {전략: 메트릭|null}, "recommended": {…}, "diff": {…}}`.
한 전략의 자문 행은 **그 전략의 두 kind 가 모두 종료 상태**에 도달해야 채워진다.

```sql
select strategy_id, status,
       (backtest_summary is null) as null_summary,
       (select count(*) from jsonb_object_keys(
            coalesce(backtest_summary -> 'current', '{}'::jsonb))) as compared_n
from parameter_recommendations
where target_date = current_date
order by strategy_id;
```

자문 INSERT 직후에는 `null_summary=true` 이고, 폴 루프가 끝나면 `false` 로 바뀐다.

### 2-4. 화면

전략 → **전략수정 AI자문**(`/recommendations`) → 영업일 선택 → 자문 카드의 `BacktestComparisonCard`.
카드는 세 갈래로 갈린다.

- `backtest_summary` 가 null → "백테스트 미실행 — 진행중이거나 외부 MCP 비활성"
- 자기 전략의 current·recommended 가 **둘 다** null → (b) "로컬 어댑터 대기"
- 그 밖 → 8 메트릭 좌(현재)/우(추천) 비교 + 차이값 칩 + peer 전략 목록

---

## 3. 트러블슈팅

| 증상 | 1차 확인 | 조치 |
|-----|--------|------|
| 헬스체크 `enabled=false` 인데 백테스트는 돈다 | `GET /api/integrations/kis-mcp` | 정상이다 — health 는 `.env` 만 본다(§1) |
| 헬스체크 `reachable=false` | stock-manager EC2(`43.202.187.5`) 상태 | 그쪽 콘솔에서 `docker ps` 확인 후 재시작 |
| `backtest_runs` 0 row | 자문 자체가 실패 | `system_logs` 에서 `[recommendation_failure]` 검색 → OpenAI 키 만료/할당 초과 가능 |
| (a) 전략 전부 failed | 외부 서버 다운 | 헬스체크 → graceful degrade 확인(자문 row 는 INSERT 됨) |
| `running` 이 20:30 이후에도 남음 | 폴 루프가 죽었거나 외부 job 이 끝나지 않음 | `[backtest_poll] … exit` 이 없으면 폴 루프가 살아 있는 것으로 본다(주기 로그가 없다). 24h 뒤 timeout 이 failed 로 정리하고, 정산(21:30) `_reset_daily_state` 가 진입 가드 `_backtest_poll_loop_running` 을 비운다 |
| `queued` 가 20:30 이후에도 남음 | submit 분기 진입 실패 | `[backtest_enqueue]` 유무 → `recommendation_engine` 예외 확인 |
| UI 카드 미표시 | `backtest_summary IS NULL` | 폴 미완료. 자문 자체는 영속이므로 다음 영업일에 자연 회복 |
| (b) 전략인데 (b) 라벨이 안 뜸 | `summary.current[전략]` / `summary.recommended[전략]` | 둘 다 null 이어야 (b) 폴백 문구가 뜬다 |

```bash
# 외부 서버 도구 목록 직접 확인
curl -X POST http://43.202.187.5:3846/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  -m 10
```

---

## 4. MDD 부호 컨벤션

외부 MCP 는 `max_drawdown` 을 **양수 절대값**으로 준다(예: `16.1`).
그래서 `BacktestComparisonCard.tsx::METRIC_SPECS.max_drawdown` 만 `diffSignInverted = true` 다.

차이값은 `추천 − 현재` 이므로 **양수 diff = MDD 증가 = 손실 악화 → 손실색**, 음수 diff = 손실 완화 → 이익색.
색 값 정본은 `frontend/src/utils/pnlColor.ts`(`PROFIT_HEX`/`LOSS_HEX`)다 — 이 문서에 다시 적지 않는다.
가드 = `BacktestComparisonCard.test.tsx::"H: MDD 양수 컨벤션 …"`.

---

## 5. 외부 응답 스키마

응답은 `data.result.metrics.{basic,risk,trading}` 3단 중첩으로 온다.
`_extract_metrics` 가 `data.metrics` → `data.result.metrics` 순으로 찾고, `_NESTED_METRIC_MAP` 이
`BacktestMetrics` 8키로 평탄화한다.

| 외부 키 | 내부 키 | 비고 |
|---|---|---|
| `basic.total_return` | `total_return_pct` | percent |
| `basic.annual_return` | `cagr` | percent |
| `basic.max_drawdown` | `max_drawdown` | 양수 절대값 |
| `risk.sharpe_ratio` | `sharpe_ratio` | 직매핑 |
| `risk.sortino_ratio` | `sortino_ratio` | 직매핑 |
| `trading.win_rate` | `win_rate` | percent |
| `trading.profit_loss_ratio` | `profit_factor` | 외부 명명 차이 (`profit_factor` 로 와도 받는다) |
| `trading.total_orders` | `total_trades` | 외부 명명 차이 (`total_trades` 로 와도 받는다) |

외부 서버 응답이 바뀐 것 같으면 재확인 도구를 돌린다.

```bash
KIS_MCP_ENABLED=true python scripts/verify_mcp_response_schema.py
```

매핑을 고칠 때는 `_NESTED_METRIC_MAP` 과 아래 가드 3개를 같이 고친다 —
`tests/unit/engine/test_backtest_engine_nested_metrics.py` ·
`tests/unit/services/test_mcp_client_unwrap.py` ·
`tests/unit/engine/test_backtest_yaml_donchian_compat.py`.

---

## 6. 핵심 안전 규칙 (자동매매와의 격리)

- **백테스트 결과는 자동매매 파라미터에 자동 반영 절대 금지** — 운영자 명시 적용만 허용
- **백테스트 task 는 fire-and-forget** — `_enqueue_backtest_jobs` 가 자문 INSERT 보존 후 별도 task 발화
- **settlement(21:30) race 무관** — 자문 INSERT 는 20:00 직후 동기 완료. 폴 task 미완료여도 자문은 영속
- **외부 서버 다운/타임아웃 graceful degrade** — `backtest_summary=null` 로 자연 처리, 운영 영향 0
- **`KIS_MCP_ENABLED=false` 환경** — (a) (b) 전 row 즉시 skipped. UI 는 (b) 폴백 라벨로 노출

### 회귀 가드 매트릭스

| 시나리오 | 가드 위치 |
|---------|---------|
| 20:00 정상 흐름 → backtest_summary 동봉 | `tests/integration/test_recommendation_backtest_flow.py::test_full_flow_20_00_recommendation_backtest` |
| 정산 race — 자문 INSERT 보존 | `test_recommendation_backtest_flow.py::test_settlement_race_preserves_recommendation_insert` |
| `KIS_MCP_ENABLED=false` 전 row skipped | `tests/integration/test_backtest_disabled_and_graceful.py::test_kis_mcp_disabled_marks_all_runs_skipped` |
| 외부 서버 다운 — (a) failed / 자문 보존 | `test_backtest_disabled_and_graceful.py::test_external_server_down_marks_runs_failed_recommendation_preserved` |
| 폴 timeout 24h — 미완료 row failed | `test_backtest_disabled_and_graceful.py::test_backtest_poll_timeout_marks_running_rows_failed` |
| MCP 클라이언트 세션 / 421 재초기화 | `tests/unit/services/test_mcp_client.py` |
| 헬스체크 enabled/reachable/error 분기 | `tests/contract/test_routes_backtest.py` |
| 전략별 YAML 변환 / (b) raise | `tests/unit/engine/test_backtest_yaml.py` |
| BacktestEngine submit/poll 분기 | `tests/unit/engine/test_backtest_engine.py` |
| 자문 시각 20:00(`TIME_RECOMMENDATION`) | `tests/integration/test_recommendation_time_change.py` |
| 자문 화면 카드 3분기 | `frontend/src/components/recommendations/__tests__/BacktestComparisonCard.test.tsx` |

---

## 7. 미구현

- **(b) 전략 로컬 백테스트 어댑터** — `_enqueue_backtest_jobs` 의 `BacktestNotSupportedError` 분기에
  `src/engine/backtest_local_adapter.py` 를 붙이는 자리. 우선순위 LTV → bull_flag → vcp. 별도 사이클
- **백테스트 누적 분석** — 월별 추세 화면. 별도 사이클
- **파라미터 자동 적용 옵션** — 지금은 금지(§6). 사용자가 명시로 요청할 때만 별도 사이클
