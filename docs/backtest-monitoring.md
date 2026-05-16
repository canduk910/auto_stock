# 백테스트 통합 — 운영 모니터링 가이드

외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`, stock-manager) 연동의 운영자
직접 진단 절차. 본 문서는 **Phase 5 까지 완료된 상태에서 운영자가 Phase 5b 실측 검증을
혼자 수행할 수 있도록** 정리한다.

> 코드 동작 명세는 다음을 참조:
> - 자문 ↔ 백테스트 합류 흐름: `src/engine/recommendation_engine.py` `_enqueue_backtest_jobs / _backtest_poll_loop`
> - YAML DSL 변환: `src/engine/backtest_yaml.py` (6 전략 — (a) 3종 / (b) 3종)
> - MCP 클라이언트: `src/services/mcp_client.py`
> - DB 마이그레이션: `supabase/migrations/019_backtest_runs.sql`, `020_parameter_recommendations_backtest.sql`
> - UI: `frontend/src/components/recommendations/BacktestComparisonCard.tsx`
> - 회귀 가드: `tests/integration/test_recommendation_backtest_flow.py` + `test_backtest_disabled_and_graceful.py`

---

## 1. 운영 활성화 절차

### Case A — `KIS_MCP_ENABLED=true` 활성화 (예정 2026-05-18 월 20:00 전)

월요일 20:00 첫 자문 사이클 발화 전까지 다음 절차 수행:

```bash
ssh ec2-user@<auto_stock-ec2>
cd ~/auto_stock

# 1) .env 의 KIS_MCP_ENABLED 값 확인
grep KIS_MCP_ENABLED .env

# 2) false → true 토글
sed -i 's/^KIS_MCP_ENABLED=false$/KIS_MCP_ENABLED=true/' .env
grep KIS_MCP_ENABLED .env   # KIS_MCP_ENABLED=true 출력 확인

# 3) 컨테이너 재시작 (운영 중 자동매매 무중단 영향은 KRX 마감 후 ~15:30 이후 권장)
docker compose -f docker-compose.prod.yml restart

# 4) 헬스체크
curl -s http://localhost/api/backtest/mcp/health | jq
```

기대 응답:
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
- 자문 자체는 정상 발화 — `backtest_summary=null` 로 graceful degrade

### Case B — Phase 4-bis 진입 (LTV/bull_flag/vcp 로컬 어댑터, 별도 사이클)

본 Phase 에서는 placeholder 만. 결정 시점은 사용자 별도 사이클.

진입 게이트 (가이드라인):
1. 외부 MCP 서버 + (a) 3종 전략 백테스트가 1주일 이상 안정 발화 확인
2. `backtest_runs.status='failed'` 비율 5% 미만 안정화
3. (a) 메트릭 부호/스케일/이름 매핑 (Section 6) 확정

진입 시 구현 위치:
- `src/engine/backtest_local_adapter.py` 신설 (참조 패턴 — stock-manager `services/local_backtest/strategies/long_tail_volatility.py`)
- `_enqueue_backtest_jobs` 의 `BacktestNotSupportedError` 분기에서 로컬 어댑터 호출
- 우선순위: LTV → bull_flag → vcp

---

## 2. Phase 5b 사용자 검증 절차 (월요일 20:00 후)

### 2-1. 실 발화 즉시 확인 (20:00 ~ 20:05)

#### 시스템 로그 패턴 검색
```sql
-- Supabase SQL 콘솔
select created_at, level, message
from system_logs
where created_at::date = current_date
  and (message like '[backtest_enqueue]%' or message like '[backtest_poll]%')
order by created_at desc
limit 50;
```

기대 패턴:
- 20:00 직후: `[backtest_enqueue] target=2026-05-18 submitted=6 (a)전략=3 (b)전략=3 enabled=True`
  - submitted=6 = (a) 3 전략 × 2 kind(current/recommended)
- 매 60초: `[backtest_poll] ...` (폴 루프 진행)
- 종료 시: `[backtest_poll] 모든 row 종료 + summary 동봉 완료 — exit: target=2026-05-18`

#### backtest_runs 12 row INSERT 확인
```sql
select strategy_id, params_kind, status, mcp_job_id, error_message,
       created_at, completed_at
from backtest_runs
where target_date = current_date
order by strategy_id, params_kind;
```

기대 결과 (활성화 + 외부 서버 정상 케이스):

| strategy_id | params_kind | status (초기) | status (완료) |
|------------|------------|--------------|--------------|
| bull_flag_breakout | current/recommended | skipped | skipped |
| donchian_swing | current/recommended | queued → running | completed |
| long_tail_volatility | current/recommended | skipped | skipped |
| momentum | current/recommended | queued → running | completed |
| vcp_breakout | current/recommended | skipped | skipped |
| volatility_breakout | current/recommended | queued → running | completed |

총 12 row. (b) 6 row 는 즉시 skipped (Phase 4-bis 대기). (a) 6 row 는 running → completed.

#### parameter_recommendations.backtest_summary 전이 확인
```sql
select strategy_id, status,
       (backtest_summary is null) as null_summary,
       jsonb_array_length(jsonb_path_query_array(backtest_summary, '$.compared_strategies')) as compared
from parameter_recommendations
where target_date = current_date
order by strategy_id;
```

기대:
- 자문 INSERT 직후 (20:00:00): `null_summary=true` 6 row
- 폴 루프 완료 후 (~20:01~20:05): `null_summary=false` 6 row, compared 키 노출

#### UI 카드 확인 (Recommendations 페이지)
- `/recommendations` 진입
- 좌측 영업일 선택 → 우측 자문 카드 영역
- `BacktestComparisonCard` 컴포넌트:
  - (a) 전략(momentum/VB/donchian): 좌(현재) / 우(추천) 메트릭 비교 + 차이값 칩
  - (b) 전략(LTV/bull_flag/vcp): "외부 백테스트 서버 미지원 (Phase 4-bis 대기)" 안내
- 데이터 미도착 시: 로딩 스피너 (`status=running` 분기)

### 2-2. 사후 진단 (20:30 이후)

#### 백테스트 status 분포
```sql
select status, count(*) as cnt
from backtest_runs
where target_date = current_date
group by status
order by cnt desc;
```

이상 신호:
- `failed > 0`: 외부 서버 오류/타임아웃 — `error_message` 분포 확인
- `running > 0` (20:30 이후): 폴 루프 좀비 — 시스템 로그 `[backtest_poll]` 마지막 timestamp 확인
- `queued > 0` (20:30 이후): submit 분기 진입 자체 실패 — `recommendation_engine` 예외 확인

#### 폴 task 좀비 의심 시
```sql
select max(created_at) as last_poll_log
from system_logs
where created_at::date = current_date
  and message like '[backtest_poll]%';
```

`last_poll_log` 가 20:30 이후 갱신 없으면:
- `_backtest_poll_loop_running` set 에 target_date 잔류 가능성 — settlement 20:10 의 `_reset_daily_state()` 가 task cancel + set discard 처리 (현재 구현 확인)
- 다음 영업일 09:00 부터 `_boot()` 재발화 안 됨 (자문은 20:00 만 발화)
- 수동 회복: `select id, mcp_job_id from backtest_runs where status='running' and target_date=current_date;` 으로 job_id 추출 후 `curl -X POST $MCP/.../get_backtest_result_tool` 수동 호출 가능 (운영자 작업)

---

## 3. 트러블슈팅 체크리스트

| 증상 | 1차 확인 | 조치 |
|-----|--------|------|
| 헬스체크 `enabled=false` | EC2 `.env` `KIS_MCP_ENABLED` 값 | 위 Case A 토글 |
| 헬스체크 `reachable=false` | stock-manager EC2 (`43.202.187.5`) 상태 | stock-manager 콘솔에서 docker ps 확인. 재시작 필요 |
| `backtest_runs` 0 row INSERT | `recommendation_engine` 자문 자체 실패 | `system_logs` `[recommendation_failure]` prefix 검색 → OpenAI 키 만료/할당 초과 가능 |
| `(a) 전략 all failed` | 외부 서버 다운 | 헬스체크 확인 → graceful degrade 작동 검증 (자문 6 row 는 INSERT 됨) |
| `running 좀비` | 폴 루프 task cancel 누락 | settlement 로그 확인 → 수동 재실행 가능 (UI 영향 없음, 다음 영업일 자연 회복) |
| UI 카드 미표시 | `backtest_summary IS NULL` | DB 직접 확인 → null 이면 폴 미완료. 운영자가 영업일 종료 후 강제 표시 원하면 별도 처리 |
| (b) 전략 카드 (b) 라벨 미표시 | 프론트 `BacktestComparisonCard.tsx` 분기 | `compared_strategies` 내 키 존재 + value=null 이면 (b) 폴백 표시 |

### 외부 서버 헬스 확인 명령
```bash
# Phase 1 헬스 API (graceful — 5xx 절대 안 냄)
curl -s http://<auto_stock-ec2>/api/backtest/mcp/health | jq

# stock-manager 직접 확인 (도구 목록)
curl -X POST http://43.202.187.5:3846/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  -m 10
```

---

## 4. MDD 부호 컨벤션 확정 절차 (Phase 6.1 — 2026-05-17 확정 완료)

`BacktestComparisonCard.tsx` 가 차이값 컬러 칩(이익색 빨강 / 손실색 파랑)을 표시할 때
`max_drawdown` 의 부호 컨벤션에 의존한다. 외부 서버 응답 데이터로 확정 후 코드 반영.

**최종 결론 (Phase 6.1)**: 외부 MCP 서버는 `max_drawdown` 을 **양수 절대값** 으로 반환 (`16.1`, `8.5` 등). `BacktestComparisonCard.tsx::METRIC_SPECS.max_drawdown.diffSignInverted = true` 적용 완료 — 양수 diff(추천 MDD 더 큼) = 손실 악화 = 파랑(`#3366FF`), 음수 diff = 손실 완화 = 빨강(`#FF3333`). 회귀 가드 `BacktestComparisonCard.test.tsx::Phase 4 > H` 1 케이스.

### 4-1. 첫 실 데이터 부호 확인
```sql
select strategy_id, params_kind,
       metrics->>'max_drawdown' as mdd,
       metrics->>'total_return_pct' as tr_pct
from backtest_runs
where target_date = current_date
  and status = 'completed'
  and metrics is not null
order by strategy_id, params_kind;
```

기대:
- `mdd` 가 **음수** (예: `-12.34`): "최대 낙폭은 음수로 표시" 컨벤션 (현재 구현 가정)
- `mdd` 가 **양수** (예: `12.34`): "절대값 양수" 컨벤션 — 별도 처리 필요

### 4-2. 부호별 처리 (Phase 6.1 — Case B 확정 적용 완료)

**Case A — 음수 (가정 폐기)**:
- ~~추천 mdd 가 현재 mdd 보다 크면(예: -5% → -3%) 추천이 더 좋음~~
- 실측 검증 결과 외부 MCP 는 양수 절대값으로만 반환. 본 케이스는 미사용.

**Case B — 양수 (절대값) — 적용 완료**:
- 추천 mdd 가 현재 mdd 보다 작으면(예: 10.0 → 8.0) 추천이 더 좋음 → diff 음수 → 빨강 칩
- 추천 mdd 가 현재 mdd 보다 크면(예: 10.0 → 15.0) 추천이 더 나쁨 → diff 양수 → 파랑 칩
- `BacktestComparisonCard.tsx::METRIC_SPECS.max_drawdown.diffSignInverted = true` 적용됨 (Phase 6.1).

### 4-3. 컨벤션 영구 명시 (Phase 6.1 완료)

- `frontend/CLAUDE.md` — `BacktestComparisonCard` 라인 갱신 (양수 컨벤션 확정 명시)
- `docs/backtest-monitoring.md` Section 4 — 본 섹션 (확정 완료 표기)
- 컴포넌트 헤더 주석 — Phase 6.1 양수 컨벤션 + signInverted 의미 명시

---

## 5. 백테스트 응답 키 검증 체크리스트 (Phase 5b)

외부 서버 stock-manager 응답이 다음 dict 구조를 반환하는 것으로 알려져 있음:
```
metrics.basic: { total_return, annual_return, max_drawdown }
metrics.risk: { sharpe_ratio, sortino_ratio }
metrics.trading: { win_rate, profit_loss_ratio, total_orders }
```

`src/engine/backtest_engine.py::_extract_metrics()` 가 평탄화하여 `BacktestMetrics`
8 메트릭으로 정규화한다. 실 데이터에서 다음 1차 결함 가능성을 검증:

### 5-1. `max_drawdown` 부호
- 음수형(예: `-12.34`) vs 절대값 양수형(예: `12.34`)
- 4-1 SQL 결과로 확정
- 부호 따라 `BacktestComparisonCard` 의 `diffSignInverted` 또는 별도 처리

### 5-2. `profit_loss_ratio` ↔ `profit_factor` 이름 매핑
- stock-manager 응답이 `profit_loss_ratio` 인지 `profit_factor` 인지 확인
- `BacktestMetrics` 의 필드명 (`profit_factor`) 과 일치하는지 검증
- 불일치 시 `_extract_metrics` 매핑 추가

### 5-3. `total_orders` 단위
- 거래 단위(매수+매도 별도 카운트) vs round-trip 단위(매수-매도 페어 1 카운트)
- 우리 시스템 trade_history 는 단위 거래 — round-trip 단위면 ×2 환산 필요
- 직접 확인 SQL:
  ```sql
  select metrics->>'total_orders' as orders,
         metrics->>'total_trades' as trades,
         metrics->>'win_rate' as wr
  from backtest_runs
  where status = 'completed'
  limit 5;
  ```

### 5-4. `annual_return` vs `cagr`
- stock-manager `annual_return` 이 산술 연환산 vs 기하 CAGR 차이
- 90일 데이터에서 (1+total_return)^(365/90) - 1 로 역산 비교

### 5-5. 검증 후 결함 발견 시
- `src/engine/backtest_engine.py::_extract_metrics()` 에 매핑 추가
- `src/models/backtest.py::BacktestMetrics` 정합성 보존
- 회귀 가드: `tests/unit/engine/test_backtest_engine.py` 에 케이스 추가

### 5-6. Phase 6 실측 검증 결과 (2026-05-16)

`KIS_MCP_ENABLED=true python scripts/verify_mcp_response_schema.py` 실행으로 외부 서버 응답 확정. `sma_crossover` preset × 005930 × 90일 백테스트 응답 raw 캡처 결과:

| 항목 | 실측 값 / 위치 | 우리 매핑 |
|------|---------------|----------|
| 응답 위치 | `data.result.metrics.{basic,risk,trading}` 3단 중첩 | `_extract_metrics` 가 `data.metrics` → `data.result.metrics` 폴 |
| `max_drawdown` 부호 | **양수 (16.1)** — 절대값 컨벤션 | `BacktestComparisonCard.signInverted: true` 권장 |
| `basic.total_return` | `-7.447` (percent) | → `total_return_pct` |
| `basic.annual_return` | `-27.468` (percent) | → `cagr` |
| `risk.sharpe_ratio` | `-0.796` | → `sharpe_ratio` (직매핑) |
| `trading.profit_loss_ratio` | `1.18` | → `profit_factor` (명명 차이 매핑) |
| `trading.total_orders` | `6` | → `total_trades` (명명 차이 매핑) |
| `trading.win_rate` | `33.0` (percent) | → `win_rate` (직매핑) |

**Phase 6 평탄화 검증** — verify 스크립트 Section [6] 결과: 8/8 키 모두 채집 성공:
```
total_return_pct=-7.447  cagr=-27.468  sharpe_ratio=-0.796  sortino_ratio=-0.42
max_drawdown=16.1  win_rate=33.0  profit_factor=1.18  total_trades=6
```

**donchian_swing YAML 외부 호환** — verify 스크립트 Section [7]: `validate_yaml_tool` 응답 `{"valid":true,"errors":[],"warnings":[]}` → **(a) 분류 유지**, `_FALLBACK_STRATEGIES` 변경 불필요.

회귀 가드:
- `tests/unit/engine/test_backtest_engine_nested_metrics.py` 4 케이스 — 실측 응답 fixture 그대로 평탄화 검증
- `tests/unit/services/test_mcp_client_unwrap.py` 9 케이스 — MCP content 2겹 래핑 unwrap
- `tests/unit/engine/test_backtest_yaml_donchian_compat.py` 6 케이스 — donchian YAML 외부 DSL 정합성

---

## 6. 핵심 안전 규칙 (자동매매와의 격리)

- **백테스트 결과는 자동매매 파라미터에 자동 반영 절대 금지** — 운영자 명시 적용만 허용
- **백테스트 task 는 fire-and-forget** — `_enqueue_backtest_jobs` 가 자문 INSERT 보존 후 별도 task 발화
- **settlement 20:10 race 무관** — 자문 INSERT 는 20:00 직후 동기 완료. 폴 task 미완료여도 자문은 영속
- **외부 서버 다운/타임아웃 graceful degrade** — `backtest_summary=null` 로 자연 처리, 운영 영향 0
- **`KIS_MCP_ENABLED=false` 환경** — (a) (b) 12 row 모두 즉시 skipped. UI 는 (b) 폴백 라벨로 노출

### 회귀 가드 매트릭스

| 시나리오 | 가드 위치 |
|---------|---------|
| 20:00 정상 흐름 → backtest_summary 동봉 | `tests/integration/test_recommendation_backtest_flow.py::test_full_flow_20_00_recommendation_backtest` |
| settlement 20:10 race — 자문 INSERT 보존 | `test_recommendation_backtest_flow.py::test_settlement_race_preserves_recommendation_insert` |
| `KIS_MCP_ENABLED=false` 모든 row skipped | `tests/integration/test_backtest_disabled_and_graceful.py::test_kis_mcp_disabled_marks_all_runs_skipped` |
| 외부 서버 다운 — (a) failed / 자문 보존 | `test_backtest_disabled_and_graceful.py::test_external_server_down_marks_runs_failed_recommendation_preserved` |
| 폴 timeout 24h — 미완료 row failed | `test_backtest_disabled_and_graceful.py::test_backtest_poll_timeout_marks_running_rows_failed` |
| MCP 클라이언트 세션 / 421 재초기화 | `tests/unit/services/test_mcp_client.py` (16 케이스) |
| 헬스체크 enabled/reachable/error 분기 | `tests/contract/test_routes_backtest.py` |
| 6 전략 YAML 변환 / (b) raise | `tests/unit/engine/test_backtest_yaml.py` |
| BacktestEngine submit/poll 분기 | `tests/unit/engine/test_backtest_engine.py` |
| Phase 0 시간 이동 (19:50→20:00) | `tests/integration/test_recommendation_time_change.py` |
| Recommendations UI 카드 분기 | `frontend/src/components/__tests__/BacktestComparisonCard.test.tsx` |

---

## 7. 향후 작업 (Phase 5b+)

1. **MDD 부호 확정** — Section 4 절차
2. **응답 키 매핑 검증** — Section 5 절차
3. **Phase 4-bis LTV 로컬 어댑터** — stock-manager 패턴 이식
4. **백테스트 historical 누적 분석** — 월별 추세 페이지 (별도 사이클)
5. **자동매매 백테스트 파라미터 자동 적용 옵션** — 현재 절대 금지, 사용자 명시 요청 시 별도 사이클
