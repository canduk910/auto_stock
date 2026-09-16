> 원본: `docs/backtest-monitoring.md` · 이관: 2026-09-17

외부 MCP 백테스트 연동 정본에서 걷어낸 경위·실측 수치·결정 근거. 규약 = [`README.md`](README.md).
원문 그대로 옮긴다(append-only). 사이클별 보고 원문은 [`../HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 에 있다.

이 문서는 2026-05-15~05-17 에 「2026-05-18(월) 20:00 첫 실 발화를 앞둔 검증 계획서」로 쓰였다.
그때의 Phase 번호·예정일·아직 답이 없던 질문이 아래에 있다. 이관 블록은 `---` 두 줄 사이가 원문이고,
그 안의 소제목·번호도 원문 그대로라 이 파일의 목차와 겹쳐 보인다.

---

## (머리말)

### 2026-05-16 Phase 5 — 문서의 목적을 「Phase 5b 실측 검증」으로 규정한 서술

원문(`docs/backtest-monitoring.md:3-5`, 2026-09-17 이관):

---

외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`, stock-manager) 연동의 운영자
직접 진단 절차. 본 문서는 **Phase 5 까지 완료된 상태에서 운영자가 Phase 5b 실측 검증을
혼자 수행할 수 있도록** 정리한다.

---

→ CHANGELOG: 2026-05-16 「백테스트 통합 사이클 Phase 5」 행

## 1. 운영 활성화 절차

### 2026-05-16 Phase 5 — `.env` sed + 컨테이너 재시작 활성화 절차 (Case A)

2026-05-17 사이클 5 가 활성 판정을 DB 우선(`system_config.kis_mcp_enabled`)으로 바꾸고
Settings 화면에 토글을 붙이면서 이 절차는 쓰이지 않게 됐다.

원문(`docs/backtest-monitoring.md:19-39`, 2026-09-17 이관):

---

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

---

→ CHANGELOG: 2026-05-16 Phase 5 행 · 2026-07-24 「backtest 엔큐 게이트 KIS_MCP DB 토글 인식(결함 d)」 행

### 2026-05-16 Phase 5 — Case B(Phase 4-bis 로컬 어댑터) 진입 게이트

진입 게이트 3조건 중 3번(메트릭 매핑 확정)은 2026-05-16 실측으로 충족됐다.

원문(`docs/backtest-monitoring.md:59-71`, 2026-09-17 이관):

---

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

→ CHANGELOG: 2026-05-15 Phase 2 행((b) 폴백 3종 명시 raise) · 2026-05-16 Phase 6 행(매핑 확정)

## 2. 20:00 자문 사이클 확인

### 2026-05-16 Phase 5 — 절 제목이 「Phase 5b 사용자 검증 절차 (월요일 20:00 후)」 였다

원문(`docs/backtest-monitoring.md:75-77`, 2026-09-17 이관):

---

## 2. Phase 5b 사용자 검증 절차 (월요일 20:00 후)

### 2-1. 실 발화 즉시 확인 (20:00 ~ 20:05)

---

→ CHANGELOG: 2026-05-16 Phase 5 행

### 2026-05-16 Phase 5 — 폴 루프가 60초마다 로그를 남긴다는 기대 패턴

`_backtest_poll_loop` 는 주기 로그를 남기지 않는다 — 종료·오류 시점에만 찍는다.
`submitted=6 (a)전략=3 (b)전략=3` 은 전략 7개·kojiro (b) 편입 전의 값이다.

원문(`docs/backtest-monitoring.md:90-94`, 2026-09-17 이관):

---

기대 패턴:
- 20:00 직후: `[backtest_enqueue] target=2026-05-18 submitted=6 (a)전략=3 (b)전략=3 enabled=True`
  - submitted=6 = (a) 3 전략 × 2 kind(current/recommended)
- 매 60초: `[backtest_poll] ...` (폴 루프 진행)
- 종료 시: `[backtest_poll] 모든 row 종료 + summary 동봉 완료 — exit: target=2026-05-18`

---

→ CHANGELOG: 2026-05-15 Phase 3 행

### 2026-05-16 Phase 5 — `backtest_runs` 12 row 기대표(6 전략 × 2 kind)

행 수는 고정이 아니라 **활성 전략 수 × 2** 이고, kojiro 가 (b) 로 들어오면서 전략은 7개가 됐다.

원문(`docs/backtest-monitoring.md:105-116`, 2026-09-17 이관):

---

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

---

→ CHANGELOG: 2026-05-15 Phase 3 행

### 2026-05-16 Phase 5 — `backtest_summary` 를 `$.compared_strategies` 로 읽던 SQL 과 UI 확인 절차

실제 동봉 형식은 `{current, recommended, diff}` 3키이고 `compared_strategies` 키는 코드 어디에도 없다.

원문(`docs/backtest-monitoring.md:118-138`, 2026-09-17 이관):

---

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

---

→ CHANGELOG: 2026-05-15 Phase 3 행 · 2026-05-15 Phase 4 행

### 2026-05-16 Phase 5 — 폴 task 좀비 수동 회복 절차

정산 시각이 20:10 이던 시절의 서술이다(cycle283 D3 로 21:30).

원문(`docs/backtest-monitoring.md:164-167`, 2026-09-17 이관):

---

`last_poll_log` 가 20:30 이후 갱신 없으면:
- `_backtest_poll_loop_running` set 에 target_date 잔류 가능성 — settlement 21:30(cycle283 D3, 종전 20:10)의 `_reset_daily_state()` 가 task cancel + set discard 처리 (현재 구현 확인)
- 다음 영업일 09:00 부터 `_boot()` 재발화 안 됨 (자문은 20:00 만 발화)
- 수동 회복: `select id, mcp_job_id from backtest_runs where status='running' and target_date=current_date;` 으로 job_id 추출 후 `curl -X POST $MCP/.../get_backtest_result_tool` 수동 호출 가능 (운영자 작업)

---

→ CHANGELOG: 2026-05-15 Phase 3 행 · cycle283 행

## 4. MDD 부호 컨벤션

### 2026-05-16~05-17 Phase 6.1 — 부호 확정 절차와 Case A(음수) 가정의 폐기

확정 전에는 음수/양수 두 컨벤션을 모두 열어 두고 첫 실 데이터로 고르기로 했다.
색 값 `#FF3333`/`#3366FF` 도 이 시절 값이다(현재 색 정본 = `frontend/src/utils/pnlColor.ts`).

원문(`docs/backtest-monitoring.md:198-236`, 2026-09-17 이관):

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

→ CHANGELOG: 2026-05-16 Phase 6 행

## 5. 외부 응답 스키마

### 2026-05-16 Phase 5b~6 — 응답 키 검증 체크리스트(질문 목록)와 05-16 실측 확정 표

5-1~5-5 는 답을 찾기 전의 질문 목록이고, 5-6 이 그 답을 낸 실측 기록이다.

원문(`docs/backtest-monitoring.md:240-311`, 2026-09-17 이관):

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

→ CHANGELOG: 2026-05-16 Phase 6 행

## 6. 핵심 안전 규칙 (자동매매와의 격리)

### 2026-05-15 Phase 0 — 자문 시각 19:50 → 20:00 이동이 가드 매트릭스 행 제목에 남아 있었다

원문(`docs/backtest-monitoring.md:335-335`, 2026-09-17 이관):

---

| Phase 0 시간 이동 (19:50→20:00) | `tests/integration/test_recommendation_time_change.py` |

---

→ CHANGELOG: 2026-05-15 「백테스트 통합 사이클 Phase 0」 행

## 7. 미구현

### 2026-05-16 Phase 5 — 향후 작업 5항목(1·2 는 05-16~17 에 끝났다)

원문(`docs/backtest-monitoring.md:340-346`, 2026-09-17 이관):

---

## 7. 향후 작업 (Phase 5b+)

1. **MDD 부호 확정** — Section 4 절차
2. **응답 키 매핑 검증** — Section 5 절차
3. **Phase 4-bis LTV 로컬 어댑터** — stock-manager 패턴 이식
4. **백테스트 historical 누적 분석** — 월별 추세 페이지 (별도 사이클)
5. **자동매매 백테스트 파라미터 자동 적용 옵션** — 현재 절대 금지, 사용자 명시 요청 시 별도 사이클

---

→ CHANGELOG: 2026-05-16 Phase 6 행(1·2 완결)
