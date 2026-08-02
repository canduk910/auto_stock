# 사이클 F — TE/RR 전략 대시보드 (트레이딩 예지치 + 손익비, 관찰 전용)

자문: `_workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md` (TE Q1-7 + RR Q8-12 + 통합 카드)
실측 검증(2026-08-02 EC2, get_trade_pairs): momentum N36 TE+0.82%(RR3.23>필요2.50 우위) / VB N65 TE−0.63%(RR1.35<필요1.83 열위·정상표본) / LTV N42 +1.05% / donchian N9 −4.42%(표본부족) / BFB·VCP N0 / kojiro N3 −7.07%(표본부족)

## 개념 (서적)
- **TE(예지치)** = 승률×평균수익 − 패율×평균손실 = **전체 청산 왕복 수익률의 단순 평균** (거래당 기대손익, 크기)
- **RR비율** = 평균수익 ÷ |평균손실| (손익비, 구조)
- **필요RR** = 패수÷승수(L/W) — 서적 (1−승률)/승률 은 보합=0 특수해. 손절=매수가 청산 보합 존재 → L/W 일반형
- **동치**: TE>0 ⟺ 실제RR>필요RR
- 배지 = TE 부호(우위/열위), 옆에 안전마진(여유=실제RR−필요RR)

## 범위 = 순수 관찰 (매매 8영역 diff 0)
읽기 전용 `get_trade_pairs` 나눗셈만. risk/order_engine/realtime/auth/api.order/scheduler 매매 hot path·주문·손절 무접촉. `/strategies` 페이지 표시.

---

## 백엔드 (F-B*)

- **F-B1** 신규 순수 함수 `te_metrics.compute_te_rr(pairs, *, now, window_days=90) -> TeRrMetrics`. 입력 = `get_trade_pairs(strategy)` 출력. 청산 왕복(`status=='closed'`) 中 `sell_date`(청산일) 가 `now − window_days` 이후만 모집단. **get_trade_pairs 는 날짜 인자 없음 → 전체 페어링 후 sell_date 윈도우 필터**(경계 왕복 미절단, 자문 §119).
- **F-B2 (소스·기준, HIGH)**: TE% = 모집단 `profit_rate`(진입가 기준, get_trade_pairs) 단순평균. **compute_metrics(매도가 기준 pnl/gross) 재사용 금지**. TE₩ = `profit_loss` 평균 + 3개월 실현손익 합계. 회귀 = 매수1만→매도1.1만 왕복 TE=+10.0%(≠+9.09%).
- **F-B3 (분해)**: N(전체 왕복) / W(profit_rate>0) / L(<0) / E(보합=0). win_rate=W/N. avg_win=승 profit_rate 평균(양수) / avg_loss=패 profit_rate 평균(음수). **승률 분모=N(보합포함), TE=net/N 정합**(자문 충돌2).
- **F-B4 (RR)**: RR비율=avg_win/|avg_loss|. 필요RR=L/W(W=0→None). margin=RR−필요RR. **avg_loss==0(전승) 또는 min(W,L)<5 → RR=None(산정불가)**. 단일거래 의존 플래그 = 최대 승 profit_loss > 총 이익합 ×0.5 → `single_trade_dominant=True`.
- **F-B5 (표본 게이트)**: `sample_tier` = N<20 'insufficient' / 20≤N<50 'low' / N≥50 'normal'. `rr_available` = (min(W,L)≥5 AND avg_loss≠0). `verdict` = N<20 → 'undecided' / else TE>0 'superior' | TE<0 'inferior' | TE==0 'flat'.
- **F-B6 (구조 태그)**: N≥20 시만. 4분면(승률 0.5 / RR 1.0): 저승률(<0.5)·고RR(≥1.0) → 'robust'(견고형) / 고승률(≥0.5)·저RR(<1.0) → 'fragile'(취약형) / 그 외 'balanced'(균형형). N<20 또는 rr_available=False → None.
- **F-B7 (엔드포인트+캐시)**: `GET /api/strategies/te?months=3` → 전략별(7전략) TeRrMetrics 리스트. **전용 엔드포인트 + 5분 TTL 프로세스 캐시**(장중 DB 부하, 자문 §138 — `time.monotonic`, months 키). `/api/strategies`(빈번 폴링) 미변경.
- **F-B8 (안전/graceful)**: 전략별 계산 예외 격리(1개 실패→그 전략 None, 나머지 진행). `git diff risk.py order_engine.py realtime/ auth/ api/order.py scheduler(매매 hot path)` = 0.
- **F-B9 (모집단 규칙)**: `status=='open'`(미실현) 제외. 부분체결은 get_trade_pairs 가 보유수량 0 시점 왕복 1건으로 접음(PARTIAL 이중카운트 부재, N 정확).

TeRrMetrics 필드(안): strategy_id, n, win, loss, even, win_rate, avg_win_pct, avg_loss_pct, te_pct, te_krw_avg, realized_sum_krw, rr, required_rr, rr_margin, rr_available, sample_tier, verdict, structure_tag, single_trade_dominant.

---

## 프론트 (F-FE*) — `/strategies` 전략 카드 + 하단 참조

- **F-FE1** 타입 `TeRrMetrics` (백엔드 1:1) + api `getStrategyTeRr(months=3)` (`useQuery retry:1`, staleTime 5분 — 사이클 65 H3).
- **F-FE2** `Strategies.tsx` 전략 카드 기존 4임계 그리드 *아래* "성과 (최근 3개월)" 5행 섹션(`data-testid="te-section-{key}"`):
  - A: 우위/열위/판정유보 배지(`te-verdict-{key}`) + TE 헤드라인 %(`te-value-{key}`) + 보조 3개월 실현 ₩
  - B: RR 컴팩트 게이지(`rr-gauge-{key}`) — 실제RR 채움 + 필요RR 마커 + 안전마진. 채움≥마커 이익색/미만 손실색
  - C: 승률 W/L · 평균수익 · 평균손실 · 거래 N
  - D: 구조 태그(`te-structure-{key}`, 견고형/취약형/균형형)
  - E: 표본 캡션(조건부)
- **F-FE3 (표본 게이트 렌더)** 자문 표 §226:
  - N<20 → TE/배지 회색 뮤트 "판정 유보" + 게이지·구조 숨김 + 승/패/N raw + "표본 부족 (N건) — 참고 불가"
  - 20≤N<50, min(W,L)≥5 → 정상 + amber "표본 적음 — 추세 참고용"
  - 20≤N<50, min(W,L)<5 → RR 게이지 "RR 참고 불가" + 구조 숨김
  - N≥50 → 정상 (single_trade_dominant 시 "RR 과대 가능" 플래그)
- **F-FE4** 색상 = 이익 `#FF3333` / 손실 `#3366FF`(frontend/CLAUDE.md). TE·평균수익·RR우위=이익색, 평균손실·RR열위=손실색.
- **F-FE5** 페이지 하단 1회: 표 1-2 참조(승률→필요RR 9행) + 교육 캡션(자문 §234 문구 그대로).
- **F-FE6** MSW handlers.ts + e2e api-mocks.ts `/api/strategies/te` mock (Playwright LIFO, 사이클 80#3).

## 회귀 가드 (자문 §266-276)
합성 왕복 시리즈: 진입가 기준 +10%≠+9.09% / 분할매도 1왕복 N=1 / 보합 TE=net/N / open 제외 / 표본경계 19·20·49·50 / 청산일윈도우 D-100매수·D-30매도 포함 / 필요RR=L/W 보합분기 / TE>0⟺RR>필요RR 동치 / 전승 RR산정불가 / min(W,L)=4·5 RR게이트 / 구조태그 4분면 / 배지=TE부호∧게이트.

## 매매 안전성 diff 0 의무
`src/engine/risk.py order_engine.py src/realtime/ src/auth/ src/api/order.py` + scheduler 매매 hot path. 변경 = te_metrics.py(신규) + routes/strategies.py(엔드포인트) + 프론트. get_trade_pairs read-only.
