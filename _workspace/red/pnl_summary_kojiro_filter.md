# pnl_summary_kojiro_filter — 매매손익 실현손익 요약 바 + 전략 필터 kojiro 추가

**명세 출처**: team-lead 메시지 (tdd-red2 과업) — 「매매손익 (1) 실현손익 요약 바 + (2) 전략 필터에 kojiro 추가」
**작성**: tdd-red2 (Red only, production 무접촉)
**행위(2)**:
1. `GET /api/history/pnl` 응답 `data` 에 신규 `summary` dict — 슬라이스 전 전체 pairs 중 closed 만 집계.
2. `TradePnLGrid` 에 요약 바 렌더 + 전략 select 에 kojiro option 추가.

---

## 계약 (backend-dev / frontend-dev 인계)

### 백엔드 — `src/routes/history.py::trade_pnl`
기존 `pairs/page/size/total/total_pages` **불변**. `data["summary"]` 신규:

| 키 | 타입 | 정의 |
|----|------|------|
| `realized_total_krw` | float | closed `profit_loss` 합 (원) |
| `realized_rate_pct` | float(round 2) | 가중 = realized_total / Σ(buy_price×buy_qty of closed) × 100. 분모 0 → 0.0 |
| `win_count` / `loss_count` / `even_count` | int | closed 중 `profit_loss` > / < / == 0 |
| `win_rate_pct` | float(round 1) | wins/(wins+losses)×100. 분모 0 → 0.0 |
| `closed_count` | int | closed 페어 수 |

- **집계 대상**: `get_trade_pairs(strategy, ticker)` 반환 전체 중 `status == 'closed'` 만 (**슬라이스 `pairs[offset:offset+size]` 전**). 필터는 `get_trade_pairs` 가 이미 반영 — 라우트는 `strategy`/`ticker` 를 그대로 전달만.
- **open 페어 제외** (미실현 미포함). open 은 `profit_loss` None 가능 → 접근 전 제외.
- **Decimal/float 혼용 안전** — 최종 값은 float 로 정규화 (`realized_total_krw` isinstance float).
- 빈 결과 → summary 전부 0.

### 프론트 — `frontend/src/components/TradePnLGrid.tsx`
- **요약 바** `data-testid="pnl-summary"` — `실현 합계 {realized_total_krw}원` · `손익율 {realized_rate_pct}%` · `승 {win}/패 {loss}/보합 {even}` · `승률 {win_rate_pct}%` + 현재 전략 필터 라벨(기본 "전체").
  - 실현값 `data-testid="pnl-summary-realized"` — 부호별 색상: 이익=`text-red-*`(빨강) / 손실=`text-blue-*`(파랑) — 기존 `pnlClass` 컨벤션 재사용.
  - 데이터는 `data.summary`.
- 전략 select 에 `<option value="kojiro">고지로 대순환</option>` 추가 (현재 6전략, kojiro 누락).
- `getTradePnL` 응답 타입(`TradePnLData`)에 `summary` 필드.
- MSW 기본 핸들러(`src/test/handlers.ts`)가 `pairs` + `summary` 포함 응답 반환하도록 정합(현재 `{items:[],total:0}` = 계약 불일치).

---

## Red

### 백엔드 — `tests/unit/routes/test_pnl_summary.py` (8 케이스, route-direct-await)
`get_trade_pairs` monkeypatch 로 합성 페어 주입, TestClient 지양 (사이클 127 anyio hang 차단).
- `test_summary_aggregates_closed_pairs` (a): closed 3건(+1000/−400/0) → 합 600·승1/패1/보합1·승률50.0·가중율 2.0
- `test_summary_decimal_and_float_mixed` (a'): Decimal/float 혼용 → realized 1000.0(float)·rate 2.5
- `test_summary_reflects_strategy_filter` (b): strategy=kojiro → 라우트 인자 전달 + kojiro 2건만 집계
- `test_summary_excludes_open_pairs` (c): open(profit_loss 큰값·None) 제외 → closed 1건만
- `test_summary_empty_all_zero` (d): 페어 0 → summary 전부 0
- `test_summary_zero_denominator_rate_is_zero` (d'): buy_price 0 → rate 0.0
- `test_summary_win_rate_zero_when_no_win_loss` (d''): 전부 보합 → win_rate 0.0
- `test_existing_pairs_pagination_contract_unchanged` (e): 150건 page2/size50 → 기존 계약 불변 + summary 전체 기준

실행 결과:
```
python -m pytest tests/unit/routes/test_pnl_summary.py -q
> 8 failed  (전부 KeyError: 'summary')
```
→ pagination(page/size/total/total_pages/pairs) 단언은 통과, `summary` 부재만 실패 = 기존 계약 불변 정합 확인.

### 프론트 — `frontend/src/components/__tests__/TradePnLGrid.test.tsx` (4 케이스, vitest+RTL+MSW)
- (a) 요약 바 값 렌더 (실현/손익율/승·패·보합/승률/전략 라벨)
- (b) 실현손익 부호별 색상 (양수 text-red / 음수 text-blue)
- (c) kojiro(고지로 대순환) option 존재
- (d) 전략 kojiro 변경 시 strategy=kojiro 재조회 (요청 쿼리 캡처)

실행 결과:
```
cd frontend && npx vitest run src/components/__tests__/TradePnLGrid.test.tsx
> 4 failed
  (a) Unable to find [data-testid="pnl-summary"]
  (b) Unable to find [data-testid="pnl-summary-realized"]
  (c) Unable to find option name "고지로 대순환"
  (d) Unable to find [data-testid="pnl-summary"]
```
→ 의도한 RED (요약 바·kojiro option 부재). 부수 컴파일/import 오류 없음.

## Green (대기 — backend-dev / frontend-dev)
- 백엔드: `trade_pnl` 에 summary 산출 추가 (슬라이스 전 전체 pairs, closed 필터, Decimal→float).
- 프론트: 요약 바 렌더 + kojiro option + `TradePnLData.summary` 타입 + MSW 기본 핸들러 정합.

## Refactor / 인덱스
- 사이클 종료(Green 후) 시 `build_index.py` / `build_index_frontend.mjs` 재생성.
