# 사이클 H — 포트폴리오 전체 리스크·섹터 노출 관찰 훅 (Phase 1, 관찰 전용 다크런치)

작성: team-leader / 2026-08-02
근거: 「터틀 자금관리」 서적 대조 감사 — 구조적 갭 2건 (High)
  1. 포트폴리오 단위 총리스크/총유닛 상한 부재 (7전략×최대5=35 동시보유를 계좌 단위로 묶는 상위 게이트 0)
  2. 전략 간 섹터/상관 집중 무통제 (`is_ticker_blocked_for_buy` 는 동일 종목코드만, kojiro 섹터캡은 자기 전략만)

**Phase 1 = 계량·로그·API 가시화만. 배제 0 · 매수 차단 0 · 매매 행위 byte 동일.**
매수 차단·SOFT 상한은 2주 관찰 후 별도 사이클(Phase 2).

## 절대 준수 — 매매 안전성 8영역 diff 0

```
git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ \
  src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py
```
= **0 라인**. ⚠️ `strategy_registry.py` 가 8영역 포함 — 관찰 훅을 registry 메서드로 추가하면 위반.
반드시 신규 순수함수 모듈 + 호출자 주입(pull) 방식.

## 팀장 확정 판단 2건 (선례 기반 — domain-consult 생략 사유 동봉)

### (A) 하드손절% 프록시 (Phase 1) — `_normalize_stop_loss_rate` 선례 확장
`src/engine/recommendation_metrics.py::_normalize_stop_loss_rate` (Phase A2/사이클 3 정본)가
이미 "후보 키 수집 → 음수만 → min(가장 보수적)" 패턴. 이를 7키로 확장한 **독립 순수 헬퍼**를
`portfolio_risk.py` 에 둔다 (기존 함수는 결측→0.0 반환 = 리스크 관찰 용도와 의미 상충하므로
재사용 아닌 동형 신규 — docstring 에 선례 명시):

- 후보 키 7종: `stop_loss_rate` / `intraday_stop_loss` / `overnight_stop_loss` /
  `stop_loss_main` / `stop_loss_pre_nxt` / `turtle_backstop_pct` / `hard_stop_pct`
- 음수 후보만 → `min(candidates)` = **최대 계획 손실** (worst-case planned loss)
- 후보 0건(결측) → **기본 −7.0 fail-open** (0.0 금지 — 리스크 0 오인 차단)
- 전략 인스턴스 `strategy.params` (DB 운영값 병합본) 기준 추출 — DEFAULT_PARAMS 아님

2026-08-02 DEFAULT 기준 기대값 (운영 DB 값이 있으면 그것이 우선):
| 전략 | 채택 키 | 값 |
|------|--------|-----|
| momentum | stop_loss_rate | −7.5 |
| volatility_breakout | stop_loss_rate(main 부재 시) | −3.0 |
| long_tail_volatility | overnight_stop_loss | −5.0 |
| donchian_swing | turtle_backstop_pct | −9.0 |
| bull_flag_breakout | stop_loss_rate | −5.0 |
| vcp_breakout | stop_loss_rate | −7.0 |
| kojiro | hard_stop_pct | −8.0 |

entry_atr 정밀화(터틀 유닛 리스크 실측)는 **Phase 2 인계** — 지금은 %프록시 통일(단순·견고).

### (B) 섹터 분류 — 이식 금지, 호출자 재사용
`src/engine/strategies/kojiro.py::_kojiro_sector_key(master_raw, ticker)` (모듈 레벨 순수함수,
KRX 산업지수 플래그 12종 → 업종 대분류 → 중분류 → `미분류-{ticker}` 독립) 가 섹터 분류 정본.
- **`portfolio_risk.py` 는 kojiro/stock_master/registry 를 import 하지 않는다** (순수성 유지).
- `sector_of: dict[ticker, sector]` 는 **호출자**(routes/portfolio.py, log_analysis_engine)가
  `_kojiro_sector_key` import + `stock_master.get(ticker).master_raw` 로 빌드해 주입.
- 중복 이식 시 kojiro 섹터캡과 분류 드리프트 위험 → 단일 진실원 유지가 우선.
- 순환 import 실측 의무 (Red 케이스: routes/log_analysis → kojiro import sanity).
- master_raw 미확보 ticker 는 `미분류-{ticker}` 독립 취급 (fail-open, 거짓 클러스터 인플레 차단).

## 구현 명세

### 1) 신규 순수함수 모듈 `src/engine/portfolio_risk.py`
선례 = `quant_score.py` / `te_metrics.py` / `ta_indicators.py`: DB/HTTP/시계 미접촉 순수함수, 8영역 미접촉.

```python
def extract_hard_stop_pct(params: dict | None, *, default: float = -7.0) -> float
def compute_portfolio_risk_snapshot(
    strategies,                      # registry.all() 결과 주입 (모듈이 registry import 금지)
    *,
    net_asset: int | float,          # 순자산 (0 이하 → pct 0)
    hard_stop_pcts: dict[str, float],# {strategy_id: 음수%} — 결측 전략은 default −7.0
    sector_of: dict[str, str],       # {ticker: sector} — 결측 ticker 는 "미분류-{ticker}"
) -> dict
```

- 포지션 리스크 프록시 = `buy_price × quantity × |hard_stop_pct| / 100` (계획 손실 원, int 반올림)
- 반환 dict (관찰 스냅샷):
  - `total_notional_won` (보유 명목 합, buy_price×qty)
  - `total_open_risk_won` (계획 손실 합)
  - `open_risk_pct_of_net` (net_asset>0 → risk/net×100 round 2, 아니면 0.0)
  - `concurrent_positions` (총 동시보유 수)
  - `by_strategy`: 전달된 **모든** 전략 포함 (0 포지션도 `{positions:0, notional_won:0, risk_won:0}`)
  - `by_sector`: 포지션 있는 섹터만 `{sector: {positions, notional_won, risk_won}}`
  - `top_sector`: risk_won 최대 섹터 `{sector, risk_won, risk_share_pct}` — 포지션 0 이면 None
- **배제 0·차단 0** — 순수 집계만. 예외 포지션(필드 결손 등)은 skip + 계속 (graceful).
  빈 strategies / positions 0 → 0 스냅샷 정상 반환.
- `state.positions` 접근은 `getattr` 방어 (mock/스텁 호환 — 사이클 56-D AttributeError 가드 답습).

### 2) 신규 라우트 `src/routes/portfolio.py` — `GET /api/portfolio/risk`
관찰성 pull 방식. `routes/realtime.py::GET /api/realtime/market-operation` 패턴 답습.
- 핸들러: `registry.all()` + `get_balance()` summary.net_asset + 전략별
  `extract_hard_stop_pct(s.params)` + 보유 ticker 합집합 → `stock_master.get` master_raw →
  `_kojiro_sector_key` 로 `sector_of` 빌드 → `compute_portfolio_risk_snapshot` → `ApiResponse`.
- graceful: get_balance/stock_master 실패 → net_asset=0 / 섹터 미분류로 **200 + 스냅샷 반환**
  (500 금지 — 관찰성 실패가 운영 화면 죽이면 안 됨).
- `main.py` 라우터 등록 + `routes/CLAUDE.md` 카탈로그 갱신.
- (선택) 60s~5분 TTL 캐시 — `GET /api/strategies/te` 5분 캐시 선례. backend-dev 재량.

### 3) 20:10 일일 리포트 계량화 `log_analysis_engine.py`
- `generate_daily_log_report` metrics 에 **`portfolio_risk_snapshot`** 키 추가 (정산 시점 1회).
- 스냅샷 빌드 실패 시 graceful — 키 None + 리포트 INSERT 는 보존 (사이클 88 G-REJECT 답습).
- 구조화 로그 `[portfolio_risk] open_risk_won=.. pct_of_net=.. positions=.. top_sector=..` 1행
  (정산 경로에서만 — scheduler hot path 발화 금지).
- net_asset 소스: get_balance 재호출 또는 당일 캐시 — graceful 0 폴백.

### 4) 프론트 — Phase 1 제외 (인계)
백엔드 API 완결 우선. 대시보드 리스크 카드(총 오픈리스크·순자산 대비%·top 섹터·섹터 막대)는
Phase 2 또는 별도 사이클 카드로 인계.

## PARAM_RANGES 금지
신규 리스크 임계·기본 −7.0 등은 **PARAM_RANGES 미편입** (정체성 상수, AI 자동 튜닝 부적합 —
사이클 198/208/209/212 선례).

## TDD 사이클 요구

### tdd-engineer Red (`_workspace/red/cycleH_portfolio_risk.md` 메모 필수)
(a) `extract_hard_stop_pct` — 7키 min 채택 / 양수 무시 / 결측 default −7.0 / None 입력
(b) `compute_portfolio_risk_snapshot` 결정적 검증 — 다전략 집계 정확성(수치 명시),
    by_strategy 0 포함, by_sector 그룹/미분류 독립, top_sector, net_asset 0/음수 → pct 0,
    빈 입력 0 스냅샷, 예외 포지션 skip graceful, **배제 0 (입력 positions 무변경)**
(c) 라우트 응답 스키마 + graceful 200 (get_balance 실패 mock)
(d) log_analysis metrics `portfolio_risk_snapshot` 키 존재 + 실패 시 리포트 보존
(e) AST 가드 — 8영역(risk/order_engine/registry/scanner/session/realtime/auth/api·order)에
    `portfolio_risk` import 0건 + `portfolio_risk.py` 가 registry/kojiro/db/http import 0건
(f) import sanity — routes/log_analysis 의 `_kojiro_sector_key` 재사용 순환 없음

### backend-dev Green
순수함수 + 라우트 + log_analysis 배선 + main.py 등록. 8영역 파일 무접촉.

### tester
8영역 `git diff` 0 실측 + 다전략 동시보유 시나리오 집계 + 배제 0(매수 행위 무변경) +
전체 회귀(백엔드 pytest 전량) + 영향 인덱스 갱신.

## Phase 2 인계 (2주 관찰 게이트)
1. 관찰 데이터 유의성 확인 후 SOFT 상한 (총 오픈리스크 % 상한 / 섹터 동시보유 캡) — 매수 가드 통합
2. entry_atr 정밀화 (터틀 유닛 리스크 실측 — donchian/kojiro `_entry_atr` 활용)
3. 프론트 리스크 카드
4. 커밋 금지 — 사용자 명시 승인 후 (feedback_commit_policy)
