# cycle266 — 종목마스터 "일봉 (30일)" 탭 결함 3건 시정 명세

작성 = team-leader / 2026-09-07 / 진단은 메인 세션 운영 실측 확정본(재조사 금지)

## 0. 성격

**매매 행위 변경 0.** HTTP 직렬화 경계 + UI 렌더 방어 + 테스트 목의 계약 검증력 회복.
`domain-consult` 대상 아님(진입·청산·수량·사이징·손절 규약 무접촉).

## 1. 확정된 진단 (사실로 받는다)

| # | 증상 | 원인 | 위치 |
|---|------|------|------|
| 1 | 일봉 탭 흰 화면 | `change_rate` `NUMERIC(8,4)` → asyncpg `Decimal` → JSON **문자열**. `"0.0000".toFixed` 없음 → `TypeError` → StockMaster 에 ErrorBoundary 부재 → React 루트까지 전파 → 트리 언마운트 | `frontend/src/pages/StockMaster.tsx` `DailyTab` (약 393행) |
| 2 | "일봉 데이터 조회 실패" | 일봉은 전 종목 적재가 아님(운영 실측 3,583 중 보유 1,810 / 없음 1,773 = 49.5%). 미적재 → 404 → `isError` → **오류 문구** | 라우트 404 + `DailyTab` `isError` 분기 |
| 3 | 진짜 DB 장애 은폐 | `except Exception: rows = []` → 404 "데이터 없음" | `src/routes/stock_master.py:298-301` |

도입 시점 = `dc66026`(2026-06-13, 사이클 124). **이 탭은 처음부터 동작한 적이 없다.**
오늘 배포분(cycle262/263/264)과 무관.

## 2. 🔴 절대 제약 — 수정 지점은 라우트 경계 한 곳

**`src/db/stock_master_daily.py::get_recent_daily` 를 고치지 않는다.** 소비처 전수:
`get_recent_daily_normalized` → **6 전략 전부의 `prepare()`** / `get_atr` → **터틀 사이징 ATR** /
`get_donchian_high` / `_row_has_lock`(수정주가 락 게이트, `abs(float(prtt_rate)) > 0`) /
`market_regime.compute_etf_stage_signal` / VB `_apply_rs_rsi_observe_in_prepare`.
여기서 타입을 바꾸면 **매매 행위 변경**이다(사용자 승인 + `domain-consult` 선행 대상).

⇒ 백엔드 수정 = `src/routes/stock_master.py::get_stock_master_daily` **단독**.
⇒ `get_recent_daily` 반환값은 **읽기 전용**. 원본 dict 를 변형하지 않는다(같은 객체가
   다른 소비자에게 갈 수 있다) — **새 dict 를 만든다**.

### 무접촉 실증 의무
`git diff --name-only` 로 아래 diff 0 을 실증한다:
- 8영역: `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**`
- `src/engine/scheduler.py`
- `src/engine/strategies/*.py` (7파일)
- `src/db/stock_master_daily.py`

## 3. 행위 명세

### A. 백엔드 — `src/routes/stock_master.py::get_stock_master_daily` 단독

**A-1. Decimal → JSON 숫자 (필드명 하드코딩 금지)**
- `get_recent_daily` 가 돌려준 각 row 를 **새 dict** 로 사영하며, 값이 `decimal.Decimal`
  이면 `float()` 으로 바꾼다. 필드명(`change_rate`/`prtt_rate`)을 열거하지 않는다 —
  향후 `NUMERIC` 컬럼이 늘어나도 자동으로 덮인다.
- **`raw` 키는 값을 그대로 전달한다**(재귀 변환 금지). 사이클 81 G-AST1 "raw 변형 0" 영속 의무.
- 그 밖의 타입(`date`/`datetime`/`int`/`str`/`None`)은 **손대지 않는다** — 기존 직렬화 계약 보존.
- 변환 실패(예: `float()` 예외)는 **fail-open** = 원값 유지(응답이 사라지는 것보다 낫다).

**A-2. 결함 3 — DB 예외 은폐 중단**
- 라우트의 `except Exception: rows = []` 를 제거한다. 예외는 **로그로 남기고**(ERROR,
  `logger.exception`) `HTTPException(500)` 으로 올린다. 404("없음")와 500("실패")를 분리.
- ⚠️ **알려진 한계(반드시 보고서에 명시)**: `get_recent_daily` **자신이** 내부에서
  `except Exception → return []` 로 이미 삼킨다(`src/db/stock_master_daily.py:283-289`).
  따라서 이 500 경로는 **오늘 실질적으로 도달하지 않는다**. 완전한 구분은 db 모듈 변경이
  필요하고, 그 모듈은 6 전략 prepare + 터틀 ATR 공유라 **별도 승인 + 행위 영향 평가**
  대상이다 → 후속 F-1 로 남긴다. 이번 사이클은 **라우트가 더 이상 은폐하지 않는 상태**까지.

**A-3. 404 문구 — "오류" 가 아니라 "적재 대상 아님"**
- `detail` 을 미적재 취지로 다듬는다(예: `"ticker={ticker} 일봉 미적재 — 일봉은 전 종목이
  아니라 전략 유니버스 대상만 적재됩니다 (days={days})"`). 최종 문구는 tdd-engineer 와 협의.
- **상태코드는 404 유지**(프론트가 이미 `error.response?.status === 404` 로 판별 가능 —
  `DetailModal` 의 `is404` 선례). 구조를 dict 로 바꾸지 않는다(응답 형태 변경 최소화).

### B. 프론트 — `StockMaster.tsx` + `types/stock-master.ts`

**B-1. `DailyTab` 방어 변환** — 백엔드가 고쳐져도 프론트가 **스스로 버틴다**(사용자 결정 ③).
- 숫자 필드(`open_price`/`high_price`/`low_price`/`close_price`/`volume`/`change_rate`)를
  렌더 전에 안전 변환한다(문자열 숫자 → number, 그 외/`NaN`/`null`/`undefined` → 표시 대체).
- 변환 불가는 **크래시 대신** `'—'` 등 대체 표기. 등락률 색상 분기도 변환 후 값 기준.
- `toFixed`/`toLocaleString` 을 **미검증 값에 직접 호출하지 않는다**.

**B-2. 타입 정합** — `StockMasterDailyRow.change_rate` 가 `number` 라는 거짓말을 시정한다
(실제 계약을 반영: 백엔드가 숫자로 내보내되 프론트는 문자열도 허용). `prtt_rate` 등
응답에 실재하나 타입에 없는 필드는 선택 필드로 추가하거나 주석으로 명시.
⚠️ `bas_dd` 주석은 `YYYYMMDD` 로 적혀 있으나 컬럼이 `DATE` 라 실제 직렬화는 `YYYY-MM-DD`
다 — **주석만** 사실에 맞춘다(렌더 무변경).

**B-3. 404 = 안내, 그 외 = 오류**
- `useQuery` 에러가 404 면 **안내 문구**(회색), 그 외(500·네트워크)는 오류 문구(빨강).
- `axios.isAxiosError(error) && error.response?.status === 404` 판별(`DetailModal` 선례 답습).
- ⚠️ `retry: 1` 유지 의무(사이클 65 H3 + AST 가드 `_ast_useQuery_retry_required.test.ts`).

**B-4. ErrorBoundary 는 이번에 넣지 않는다** — 범위 확대. 리뷰 메모에 후속으로 남긴다
(현행 ErrorBoundary 는 프로젝트 전체에서 `components/DailyReportTab.tsx` 한 곳뿐).

### C. 목 3곳 — 이번 사이클의 **핵심 재발 방지**

목 셋이 전부 `change_rate` 를 진짜 숫자로 만들어 **의도한 계약**만 담고 **실제 응답**을
담지 않았다 — 그래서 3개월 넘게 초록이었다.
- `frontend/src/test/handlers.ts:257` · `e2e/fixtures/api-mocks.ts:462` ·
  `frontend/src/pages/__tests__/StockMaster.test.tsx:839`

**C-1(정본 가드). 백엔드 직렬화 계약** — 라우트를 **실제로 태워** 직렬화된 JSON 에서
`change_rate` 가 **문자열이 아니라 숫자**임을 단언한다. `Decimal` 을 반환하는 가짜 DB
(`get_recent_daily` 를 monkeypatch)로 태운다. `raw` 안쪽은 **변형되지 않았음**도 함께 단언.
이게 유일한 진짜 계약 가드다.

**C-2. 프론트 방어 가드** — API 가 `change_rate` 를 **문자열로 주는** 케이스를 목에 추가하고
렌더가 크래시하지 않음을 단언한다. **현행 숫자 케이스는 유지**(양쪽 다 통과해야 한다).

**C-3. 목 3곳 정합** — MSW ↔ Playwright ↔ 단위 목이 서로 어긋나지 않게 유지.
`frontend/CLAUDE.md` 의 stock_master UI 동기화 의무 절차(8단계) + 사이클 80 hotfix #3
Playwright **LIFO** 규약을 따른다.

## 4. 검증 게이트

- 백엔드 `python -m pytest -q` — 회귀 0
- 프론트 `cd frontend && npx tsc -b && npm test` (⚠️ `tsc --noEmit` 은 0파일 검사 = 공허, cycle256 교훈)
- e2e `npx playwright test --config=e2e/playwright.config.ts`
- **프론트 파일을 읽는 백엔드 가드**도 함께 실행(`grep -rl 'frontend/' tests/unit`)
- `git diff --name-only` 로 §2 무접촉 실증
- **뮤테이션**: 방어 변환(B-1)을 지웠을 때 프론트 가드가 붉어져야 한다. 초록이면 가드가 공허하다.
  A-1 Decimal 변환을 지웠을 때 C-1 이 붉어져야 한다.

## 5. 산출물 · 금지

- **커밋·push 금지.** 산출물 경로 + 검증 수치를 team-leader 에 보고 → 메인 세션이 결정.
- 문서 동기화는 Phase 4.8 `/sync-docs`. ⚠️ `src/*/CLAUDE.md` 를 고치면 배포가 **full 모드**
  (backend 재시작)가 된다 — 보고에 명시.
- 파라미터·전략 설정·매매 행위는 **한 글자도** 건드리지 않는다.
- 보고는 **예상과 실측을 구분**해서 적는다.
