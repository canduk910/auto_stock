# RS · 재무 · 목표가 리비전 — 1단계 명세 (매매 무관 leaf)

> 출처: 2026-10-13 사용자 결정(CAN SLIM 턴어라운드 검토 후속). 자문 = 이 세션 domain-expert 2회(재무 필터 적합성 · forward/RS 후속).
> 범위 = **새 파일만**. `src/engine/scanner.py`·`scheduler.py`·8영역·전략 파일·`DEFAULT_PARAMS` 무접촉. 배선(적재 스케줄·전략 기록)은 2단계 — 별도 승인.

## 사용자 결정 (2026-10-13 20:4x KST)

1. 목표가 리비전 TR `FHKST663300C0` 연동 + 추정실적 `HHKST668300C0` 월초 스냅샷 저장 = **한다**
2. RS 정의 = **IBD-lite**(0.4×63일 + 0.3×126일 + 0.3×189일 수익률) → 모집단(일봉 적재 유니버스) 안 백분위 0~99, **순위(정렬)로 쓴다**
3. 적용 대상 = **4 전략**(`donchian_swing` 주 · `vcp_breakout`·`kojiro`·`etf_trend` 보조). 나머지 5전략 미적용
4. 성공 기준·기간 = 아래 「사전 등록」 값으로 **동결**
5. 관찰 통과 뒤 실매매 반영 = **한다**(반영 자체는 그때 전략별 별도 승인)
6. 섹터 RS(B: 섹터 대비 종목 · C: 상위 섹터 × 섹터 내 상위) = **기록 항목으로 둔다**

## 1단계 산출물

### A. `src/engine/rs_score.py` (순수 함수, I/O 0)
- `ibd_lite_return(closes) -> float | None` — 종가 시계열(오래된→최신). 189봉+1 미만이면 `None`. r_n = close[-1]/close[-1-n] − 1, 점수 = 0.4·r63 + 0.3·r126 + 0.3·r189. 0 이하 가격은 `None`.
- `percentile_ranks(scores: dict[str, float|None]) -> dict[str, int|None]` — `None` 은 순위 계산에서 빼고 `None` 유지. 값이 있는 종목 수 n: n==1 → 99. 그 외 `floor(99 × (순위-1)/(n-1))`(최저 0, 최고 99), 동점은 같은 순위(평균 아닌 최소 순위 = 보수적).
- `sector_relative(scores, sector_of, min_members=5) -> dict` — 섹터별 동일가중 평균 점수 → (B) 종목 점수 − 섹터 평균, (C) 섹터 평균의 섹터 간 백분위 + 섹터 내 백분위. 「미분류」로 시작하는 키 · 구성 < `min_members` 섹터는 `None`(결측 = 중립).
- 결측은 감점하지 않는다(소비처가 fail-open 으로 다룬다).

### B. `src/engine/fundamental_score.py` (순수 함수, I/O 0)
- `available_from(stac_yymm: str, is_annual_or_q4: bool) -> date` — 결산월 말일 + 45일(분기) / + 90일(4분기·연간). 공시일 칸이 없어서 이 규칙이 「그때 알 수 있던 값」의 정본.
- `known_as_of(rows, as_of: date) -> list` — `available_from <= as_of` 인 행만.
- `quarterly_from_cumulative(rows) -> dict[stac_yymm, value]` — KIS 분기 손익은 연초 누적(`docs/kis/domestic-stock-info.md` 분기 누적 주석). 같은 회계연도 직전 분기를 뺀다. 직전 분기 결측이면 그 분기 = `None`(추정 금지). 1분기는 그대로.
- `turnaround_flags(q_now, q_yoy) -> dict` — 영업이익 흑자전환(yoy ≤ 0 ∧ now > 0) · YoY 증가율(yoy > 0 일 때만, 아니면 `None`) · 0 경계 포함.
- `target_revision_breadth(opinions, as_of, window_bd=60) -> float | None` — 증권사별로 창 안 가장 최근 목표가와 그 직전 목표가 비교 → (상향 수 − 하향 수) ÷ 의견 낸 증권사 수(−1~+1). 의견 0건 = `None`. 목표가 0/결측 행은 제외. 보조 = 목표가 중앙값 변화율.

### C. `src/api/invest_opinion.py` (KIS 래퍼, 시세 풀 경유)
- `inquire_invest_opinion(ticker, date_from, date_to)` — `FHKST663300C0` `/uapi/domestic-stock/v1/quotations/invest-opinion`. 한 번 100건. 반환 = 정규화 dict 목록(영업일자·증권사명·의견·직전의견·목표가 `hts_goal_prc`·전일종가·괴리율). 필드는 `docs/kis/domestic-stock-info.md` 정본 확인.
- `inquire_estimate_perform(ticker)` — `HHKST668300C0` `/uapi/domestic-stock/v1/quotations/estimate-perform`. **실전 전용(모의 미지원)**. `output1` 한글명이 문서에서 ELW 용으로 잘못 붙어 있으니 raw 를 통째로 보관하고 확정된 칸만 꺼낸다.
- 두 path 를 `src/api/base.py::_QUOTE_ALLOWED_PATHS` 에 등재. TR_ID 는 실전 값.

### D. `src/db/invest_opinion.py` + 마이그레이션(가산형 신규 테이블 2)
- `invest_opinion_history` — PK `(ticker, bsop_date, mbcr_name)`, 칸 = 의견·직전의견·목표가·전일종가·괴리율·`raw` JSONB·`fetched_at`.
- `estimate_perform_snapshot` — PK `(ticker, snapshot_month)`, `raw` JSONB + 확정 칸 · `fetched_at`.
- 🔴 마이그레이션 번호는 병합 직전에 main 의 마지막 번호 + 1 로 다시 확정한다(로컬 세션과 충돌 방지). 작성 시점 main 마지막 = 050.

## 사전 등록 (동결 — 관찰 성공 기준)

- 대상: `donchian_swing` 모든 매수 신호(슬롯 포화로 못 산 신호 포함) — 신호 시점 RS(A)·섹터 RS(B·C)·목표가 리비전·확정 재무 점수. 그 시점에 알 수 있던 값만(공시 지연 규칙).
- 보조: `vcp_breakout`·`kojiro`·`etf_trend` 후보에 RS(A) 기록. etf_trend 는 같은 기초지수 ETF 를 대표 1종목으로 묶은 뒤.
- 결과 지표: 깡토식 청산 규약을 반사실로 적용한 신호별 R. 보조 = +1R 전 손절 비율(돌파 실패율).
- 기간: 6개월 또는 그룹(상·하위 1/3)당 60신호 중 늦은 쪽.
- 성공 기준(항목별, 모두 충족해야 그 항목 채택):
  1. 상위 1/3 − 하위 1/3 평균 R ≥ +0.3R, 부트스트랩 95% 하한 > 0
  2. 돌파 실패율 차 ≥ 5%p (상위가 낮음)
  3. 상위 10% 수익 거래 중 하위 1/3 비중 < 40% (큰 꼬리 보존)
  4. 정렬 뒤 6칸 채움률이 현행 대비 떨어지지 않음
  5. (B)·(C) 는 (A) 에 더했을 때 평균 R 개선 ≥ +0.1R ∧ 하한 > 0 일 때만 채택
  6. 목표가 리비전 항은 커버리지 ≥ 60% ∧ 기준 1 충족 시에만 채택
- 실패 = 그 항목 관찰 종료, 점수에서 제외. 정렬·배제 모두 하지 않음.
- 생존편향: 목표가 리비전 2~4년 재생 백테스트는 병행하되 판정 근거로 쓰지 않는다.

## 2단계 (승인 대기 — 이 문서 범위 밖)
- 적재 스케줄(주 1회 장후, 16:40 재무 적재와 겹치지 않게 · 20:30~20:45 불변식 창 회피) — `scheduler.py` 또는 `scanner.py` 접촉 → 승인 필요
- 분기 재무(`div_cls="1"`) 적재 — `scanner.py` 접촉 → 승인 필요
- 4 전략 prepare 에 점수 기록(funnel/섀도) — 새 `DEFAULT_PARAMS` 키면 승인 + domain-consult
