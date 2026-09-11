# cycle285 — 장운영상태 화면 확장: **야간작업 현황 + 실시간 장운영(VI·CB)**

> 상태: **명세만.** 착수는 cycle283 배포 뒤(신규 작업·시각이 이 화면의 입력이다) + cycle282 병합 뒤.
> 발의 = 2026-09-12 사용자 — *"우리 배포할 장운영상황 UI에 이런 매매 외 작업들 완료현황도 함께
> 있었으면 좋겠네. 실시간상태의 장운영상태(VI, 서킷브레이커 상태 등)까지 가져올 수 있으면 더 좋고."*

---

## 1. 왜 — 표가 말하는 것과 실제가 갈릴 때를 본다

cycle282 가 만든 장운영상태 표는 **시각 기반 정적 표**다("지금 몇 시니까 어떤 상태여야 한다").
거기에 실측을 얹으면 **예정 대 실제**를 한 화면에서 대조할 수 있다.

- 표는 "정규장 연속매매" 인데 실제로는 서킷브레이커로 멈춰 있다 → 불일치가 즉시 보인다
- 표는 "20:30 일봉 적재" 인데 마지막 성공이 어제다 → 그날 적재가 없었다는 뜻이다

지금 이걸 알려면 EC2 에 붙어 `system_logs` 를 grep 해야 한다. 이번 세션에서만 그 작업을 여러 번 했다.

---

## 2. 재료 — 거의 다 있다 (신규 수집 로직 0 목표)

### 2.1 실시간 장운영 (①)

| 재료 | 위치 | 내용 |
|---|---|---|
| VI 활성 종목 | `market_operation_monitor._vi_active_tickers` | set |
| 거래정지·종목상태 이상 | `_halt_active_tickers` | set |
| 요약 | `get_market_op_state_summary()` | + `iscd_stat_active_count` |
| 서킷브레이커 | `get_circuit_breaker_state()` | `suspected` / `halted` / `observed` / `halt_reasons_sample` / `representative_mkop_cls_code` |
| 기존 노출 | `GET /api/realtime/market-operation` (`src/routes/realtime.py:576`) | RealtimeHealth 5번째 카드 |

⇒ **백엔드 신규 0.** MarketState 화면이 이 엔드포인트를 같이 부르면 된다.

### 2.2 야간작업 현황 (②)

| 재료 | 위치 | 내용 |
|---|---|---|
| 예정 시각 | `scheduler.TIME_*` | **상수에서 읽는다 — 하드코딩 금지** (§4-1) |
| 마지막 성공 | `system_config.get_task_last_success(label)` (`src/db/system_config.py:835`) | ISO 문자열 |
| 진행 중 | `refresh_progress.get_all_progress()` | 5키 · status/total/processed/updated/skipped/failed/elapsed_ms |
| 산출물 확인 | DB 직접 | 아래 표 |

**`task_label` 전수 8개** (`data_load_tasks.py` + `quote_token_refresh.py`):
`full_universe_load` · `stock_master_daily_load` · `stock_master_basics_refresh` ·
`stock_master_master_load` · `stock_master_financial_load` · `evening_funnel_capture` ·
`stock_master_daily_purge` · `quote_token_refresh`
(+ cycle283 이 추가하는 1차 적재 라벨 — 착수 시점에 확정)

**마커가 없는 작업**은 산출물로 판정한다:

| 작업 | 판정 소스 |
|---|---|
| 20:00 AI 자문 | `parameter_recommendations` 오늘 행 수 |
| 20:05 metrics 1차 저장 (cycle283) | `daily_log_reports` 오늘 행 + `metrics.snapshot_pass` |
| 정산 (`_settle`) | `daily_performance` 오늘 행 |
| 일일 로그 분석 | `daily_log_reports` 오늘 행의 `summary`/`model` |
| 20:20 클라우드 루틴 | 같은 행의 `ext_created_at` |
| 일봉 적재 실적 | `stock_master_daily` 의 `max(bas_dd)` + 오늘 봉 행 수 |

---

## 3. 화면 구성 (제안 — 착수 시 frontend-dev 와 확정)

cycle282 `MarketState.tsx` 에 섹션 2개를 더한다. 기존 표·커서는 **무접촉**.

```
[기존] 장운영상태 표 (13행) + 현재 행 커서 + 사용 가능 호가유형
   ↓
[신규 A] 지금 시장은  — VI n종목 · 거래정지 n종목 · 서킷브레이커 (추정) · 대표 장운영코드
[신규 B] 오늘 야간작업 — 시각순 타임라인. 각 행 = 예정시각 / 작업 / 상태 / 마지막성공 / 요약수치
```

상태 값: `예정` · `진행중` · `완료` · `실패` · `건너뜀(신선)` · `미발화`

---

## 4. 반드시 지킬 것

### 4-1 🔴 시각을 하드코딩하지 않는다

예정 시각은 `scheduler.TIME_*` 에서 **읽는다**. 화면이나 프론트에 `"20:30"` 같은 리터럴을 적으면
cycle283·284 가 시각을 바꾸는 순간 **거짓을 보여 주는 화면**이 된다. cycle282 가 장운영 표를
함수화한 것과 같은 원칙이고, 이 프로젝트에서 시각 리터럴 드리프트는 반복 사고다
(`src/engine/CLAUDE.md` 가 `18:10`/`16:00` 을 동시에 말하던 상태가 cycle283 검증에서 발견됐다).
회귀 가드 = 프론트·라우트 소스에 시각 리터럴 0건(AST/텍스트).

### 4-2 🔴 VI·거래정지 커버리지 한계를 화면에 적는다

`H0UNMKO0` 장운영정보는 **전 종목 구독이 아니다** — 005930(대표) + 보유·익일청산 종목만이고
후보는 미배치다(cycle230). 그래서 **"VI 0건" 은 "VI 없음" 이 아니라 "관측 대상 안에 없음"** 이다.
화면에 `관측 n종목 기준` 을 반드시 병기한다. 이걸 빼면 운영자가 없는 안전을 믿는다.

### 4-3 🔴 서킷브레이커는 추정이다

KIS `H0UNMKO0` 에 CB 전용 필드가 없어 cycle186 이 휴리스틱으로 판정한다 — (R) 거래정지 사유
키워드(`서킷`/`매매거래중단`/`circuit`) **또는** (W) `halted >= 5 ∧ halted/observed >= 0.8`.
화면에 **"추정"** 을 표기하고 판정 근거(사유 표본·halted/observed)를 같이 보여 준다.
실제 CB 를 관측하면 정식 코드로 승격하는 것이 cycle186 의 인계 사항이다.

### 4-4 정산 후에는 비어 있는 게 정상이다

`_reset_daily_state`(cycle283 이후 21:30)가 메모리 상태를 지우므로 그 뒤 VI·거래정지 집계는 0 이 된다.
"세션 종료" 를 별도 상태로 구분해 표시하고, 그걸 "이상 없음" 으로 읽지 않게 한다.

### 4-5 읽기 전용

이 화면은 **관측 전용**이다. 재적재·재실행 버튼을 붙이지 않는다(기존 종목마스터 화면에 이미 있고,
cycle283 이 `POST /api/log-reports/run` 에 `force` 가드를 넣은 맥락과 충돌한다).

---

## 5. 범위·제약

- **8영역 무접촉.** 신규는 `src/routes/` + `frontend/` + (필요 시) 얇은 집계 leaf 하나.
  `market_operation_monitor` 는 **읽기만** 한다(상태 dict 를 변형하지 않는다).
- `scheduler.py` 무접촉(라인 상한 3,900, 현재 3,897 — 여유 1행).
- 매매 행위 변경 **0**. `domain-consult` 불요(관측 전용).
- 프론트 동기화 의무 = `frontend/src/types/` 정의 + `handlers.ts`(MSW) + `e2e/fixtures/api-mocks.ts`.

## 6. 선행 조건

1. **cycle282 병합** — 이 화면이 붙을 자리다(브랜치 `cycle282-market-state`, `f37a639`, 미병합).
2. **cycle283 배포** — 신규 작업(1차 적재·metrics 스냅샷)과 바뀐 시각이 이 화면의 입력이다.
3. cycle284(마스터 조건부 GET)가 들어오면 `last_modified` 도 이 화면의 한 행이 된다 — 그때 추가.
