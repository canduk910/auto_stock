# 사이클 53 — B-2 + B-4 통합 시정 (log_analysis 데이터 수집 결함)

**발주일**: 2026-06-02
**원천**: `_workspace/2026-06-01_log_analysis.md` B-2 (HIGH) + B-4 (MEDIUM)
**판정**: 둘 다 `log_analysis_engine` 데이터 수집 결함 / *집계·관찰성* 결함 / 매매 안전성 직접 영향 없음 / domain-expert 자문 불필요.
**범위**: 백엔드 단독 (프론트엔드 무관).

---

## 진단 결과 (메인 세션 확정)

### B-2 (HIGH) — `[next_day_clear_drained]` 집계 누락
- **실측**: `system_logs` 에 064400 `[next_day_clear_deferred]` 2026-05-31T23:00:37 UTC + `[next_day_clear_drained]` 2026-06-01T00:00:18 UTC `result=success` *정상 발화*. 윈도우 안 (KST 2026-06-01 00:00~now).
- **자동 리포트 오집계**: `deferred=1 / drained_success=0`.
- **Root cause**: `src/engine/log_analysis_engine.py::_fetch_logs_in_range` 가 `limit=5000` 전달하지만 **Supabase PostgREST default 1000 페이지 한도** 에 잘림. `log_metrics.total_logs=1000` 이 증거. drained 가 *최신* 로그라 `order asc` 1000 cap 에서 끝부분 잘려나감.

### B-4 (MEDIUM) — `trade_metrics` 064400 SELL 누락
- **실측**: `trade_history` 064400 SELL `timestamp=2026-05-31T23:20:00 UTC` (=KST 2026-06-01 08:20) COMPLETED +30,100원 *정상 INSERT*.
- **자동 리포트 오집계**: `trades_total=4` (VB 4건만, 064400 momentum 제외).
- **Root cause**: `src/db/trade_history.py::get_trades_in_range(start_date, end_date)` 가 `start_iso = f"{start_date.isoformat()}T00:00:00"` (TZ 없음). PostgREST가 UTC 해석 → KST `target_date 00:00~09:00` (UTC 전날 15:00~24:00) 거래 누락.
- **영향 확장**: `recommendation_engine` 도 동일 함수 사용 → 동일 결함 영향 추정 (회귀 가드 PASS 로 검증).

---

## 시정 명세

### S-1: `_fetch_logs_in_range` 페이지네이션
- 파일: `src/engine/log_analysis_engine.py`
- `.range(offset, offset+999)` 루프로 1000건 단위 fetch 후 합산.
- `limit` 파라미터는 *총* 한도 의미로 보존 (예: limit=5000 → 최대 5000건까지 페이지네이션).
- 빈 페이지 또는 < 1000건 페이지 도달 시 종료.

### S-2: `get_trades_in_range` KST timezone 명시
- 파일: `src/db/trade_history.py`
- `start_iso = f"{start_date.isoformat()}T00:00:00+09:00"`
- `end_iso = f"{end_date.isoformat()}T23:59:59.999999+09:00"`
- 또는 `datetime.combine(date, time.min, KST).isoformat()` 명시 변환 (선호).

### S-3: 호출처 회귀 확인
- `recommendation_engine` 등 `get_trades_in_range` 호출처 *기존 테스트 PASS* 만 검증.
- 기능 회귀 없음 — 오히려 누락 거래 포함되어 메트릭 *정확*해짐.

---

## TDD 사이클

### Red (tdd-engineer)
- 신규 파일: `tests/unit/engine/test_b2_b4_log_analysis_data_collection.py`
- 시나리오 5개:
  1. **B-2 / `_fetch_logs_in_range` 페이지네이션** — Supabase mock 이 1001+ 건 반환 시 limit=5000 호출에서 *모든* 건 합산 (1000 cap 회귀 가드).
  2. **B-2 / next_day_clear 집계** — logs 1500건 중 1001~1500 위치에 `[next_day_clear_drained]…result=success` 포함 시 자동 리포트가 `drained_success` 정확 카운트.
  3. **B-4 / `get_trades_in_range` KST 경계** — `trade_history` 의 UTC 23:20 (= KST 익일 08:20) timestamp 거래가 `target_date=KST 익일` 윈도우에 포함됨.
  4. **B-4 / 회귀 가드** — UTC 자정 직전/직후 거래의 KST 00:00~23:59 boundary 정확성.
  5. **integration** — `generate_daily_log_report` 가 064400 시나리오 mock 데이터로 호출 시 `next_day_clear.drained_success=1` AND `trades.trades_total=5` 정확.

### Green (backend-dev)
- S-1 / S-2 구현.
- 기존 호출처 (`recommendation_engine` 등) 기존 테스트 PASS 확인.
- 영향 인덱스 갱신 (`tools/test_impact/build_index.py`).

### Verify (tester)
- 회귀 가드 PASS + 백엔드 1766 → 1771 (+5).
- 실제 2026-06-01 데이터로 `generate_daily_log_report()` 재실행 시 `next_day_clear.drained_success=1`, `trades.trades_total=5`, `realized_pnl=56,100` (기존 26,000 → +30,100) 정확 집계 확인.
- **단**: `daily_log_reports` UNIQUE (target_date) 충돌 — DB 재INSERT 보류, **사용자 의사 확인 후 진행**.
- domain-expert 자문 불필요.

---

## 문서 동기화

- `src/engine/CLAUDE.md` — `log_analysis_engine.py` 섹션에 페이지네이션 + KST timezone 명시.
- `src/db/CLAUDE.md` 가 있으면 `get_trades_in_range` 의 timezone 동작 명시.
- `docs/HARNESS_CHANGELOG.md` — 사이클 53 행 추가 (종료 검수에서).
- `_workspace/2026-06-01_log_analysis.md` — B-2 / B-4 섹션 종결 표시 (사이클 53 종결 노트 prepend, 사이클 52 / 49 패턴 동일).

---

## 제약

- 커밋/푸시는 사용자 명시 지시 시.
- B-2 / B-4 모두 *집계·관찰성* 결함 — 매매 안전성 직접 영향 없음.
- `recommendation_engine` 의 기존 동작이 *잘못된 것* (TZ 누락은 결함이지 정책 아님).
- 결정 포인트 발생 시 메인 세션에게 보고.
