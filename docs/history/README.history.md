> 원본: `README.md` · 이관: 2026-10-08

정본은 [`README.md`](../../README.md). 이 파일은 거기서 걷어낸 원문을 **고치지 않고** 옮겨
둔 것이다(append-only). 사이클 축으로 찾으려면 [`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md)
로 간다.

절 제목은 **이관 시점의 정본 절 제목**이다.

---

## API 엔드포인트

### 2026-10-08 cycle411 2차 보완 F14 — 실비용 엔드포인트 행의 사이클 꼬리표·「보완」 표기 제거

정본 원문(실비용 관련 8행, 걷어내기 전):

```
| GET | `/api/balance` | 잔고 조회 (예수금 + 보유종목, 종목별 NXT/KRX 거래시장 정보 join). **cycle411 보완** 보유마다 `buy_fee_paid`·`buy_fee_status` |
| GET | `/api/history?page=&size=` | 거래 내역 (페이징). **cycle411** 체결 행마다 `fee`·`cost_status` + SELL 행 `tax`·`net_profit_loss`. **보완** 배분은 페이지가 아니라 그 날짜 전체 체결로 한다 |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | 매매손익 — 매수/매도 페어 1행 (포지션 0 사이클 단위 가중평균). 보유 중은 open 페어 (미실현 손익은 `ticker_prices` 현재가). **cycle411** 페어마다 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`·`allocated` + summary 순손익 합계. **보완** 분할 매도 뒤 보유 페어에 `partial_fee`·`partial_tax`, 비용 모름은 summary 4칸 `None`(0 아님) |
| GET | `/api/performance/summary` | 실적 요약 (TWR 누적 + 일평균 실현 수익률). **cycle411** `net_total_profit_rate`·`net_avg_daily_profit_rate`(순손익 기준) 추가. **보완** `net_total_profit_rate` 는 조회 창이 아니라 개시 이래 전체로 재누적한다 |
| GET | `/api/performance/daily` | 일별 실적 (실현손익 기반 + TWR 누적 + 외부 입출금). **cycle411** `daily_fee`·`daily_tax`·`daily_net_pnl`·`net_daily_profit_rate`·`net_cumulative_return_rate`·`cost_status` 추가. **보완** `net_cumulative_return_rate` 는 이 창이 아니라 개시 이래 전체 재누적, 전략 필터는 배분 뒤에 건다 |
| GET | `/api/costs/today?strategy=` | **cycle411** 오늘 체결 × (정산 or 추정 요율), 전략별 + total — OrderMonitor 용. **보완** 전략 필터는 배분 뒤에 걸고 요율은 서버 오늘 기준 30일 창 |
| GET | `/api/costs/daily?from=&to=` | **cycle411** 날짜별 비용·슬리피지·`cost_status` 추이. **보완** 요율은 화면 범위가 아니라 서버 오늘 기준 30일 창 |
| GET | `/api/strategies/te?months=3` | cycleF 전략별 TE(트레이딩 예지치)/RR(손익비) 최근 N개월(`months`×30일) 지표 — 관찰 전용, 5분 프로세스 캐시. 전략별 계산 실패는 그 전략만 빈 값으로 격리. **cycle411** 판정은 순손익 기준, 세전은 `*_gross` 칸으로 병기(**보완** 세전 승/패 수 `win_gross`·`loss_gross` 추가) |
```

경위: 루트 `CLAUDE.md` 「문서 규약」(정본은 지금 동작하는 규칙만, 사이클 꼬리표·「보완」
표기는 history 로)을 cycle411 1차·2차 보완이 쌓은 `**cycle411**`·`**보완**` 태그가 어겼다.
2차 통합 검증 F14 가 이를 잡았고, 각 행을 현재형으로 다시 쓰면서 걷어냈다. 값의 출처
괄호(`cycle411, 사용자 결정 10-08 §3 …`)는 규약이 허용해 남긴 곳도 있다.

→ CHANGELOG: cycle411

---

## API 엔드포인트

### 2026-10-08 cycle411 문서 동기화 — `/api/history/pnl` summary 「모름」 칸 수 정정

정본 원문(바뀐 부분):

```
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | … 분할 매도 뒤 보유 페어에 `partial_fee`·`partial_tax`, 비용 모름은 summary 4칸 `None`(0 아님) |
```

경위: 비용 조회가 실패하면 `None` 이 되는 summary 칸은 `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n` 다섯이다(3차 통합 검증 지적). 같은 동기화에서 `/api/balance` 행에 `sell_cost_rate` 를, 「대시보드 화면」 표의 대시보드·거래 내역 행에 세후 기본·세전 토글·실비용 칸을 덧붙였다(덧붙임이라 걷어낸 원문은 없다).

→ CHANGELOG: cycle411 행

---

## 2. 데이터베이스 초기화 · 배포 전 호스트 준비 (하드 게이트) · 프로세스 구성과 분리 로드맵

### 2026-10-08 cycle412 문서 동기화 — migration 목록 001~047 · `journal_worker.env` 결손 효과 정정 · 컨테이너 넷

정본 원문(바뀐 부분):

```
파일 목록 (현재 `001`~`043`, 실제 집합은 디렉터리가 정본):
```

```
- `secrets/journal_worker.env` 가 없으면 `journal_worker` 컨테이너가 기동 실패한다(`env_file` 필수 참조) — 메인 앱 `.env` 를 대신 쓰지 않는다(KIS 앱키·HTS ID·운영 DSN 33개가 그 컨테이너에도 들어간다).
```

```
현재 운영 컨테이너는 3개다 (`docker-compose.prod.yml`) — `backend` · `frontend` · `macro`.
`macro` 는 매크로 화면 API 이고 매매 판단을 하지 않는다. 매매에 관한 일은 전부 `backend` 한 프로세스에 있다.
```

경위:

- migration 목록은 043 에서 멈춰 있었다. 044(etf_trend 시드, cycle403)·045(실비용 정산, 트랙 C)·
  046(`order_price`, cycle409)·047(거래일지 4표, cycle412)을 더하고 범위를 `001`~`047` 로 고쳤다.
  047 뒤에 사람이 한 번 돌리는 `journal_worker/ops/role.sql` 실행 절차를 그 아래에 덧붙였다.
- `journal_worker.env` 결손 문장은 같은 cycle412 의 백엔드 담당이 쓴 것이다. 로컬 compose
  v5.1.1 로 재현하니 `env_file` 결손은 그 서비스 하나의 기동 실패가 아니라 compose 명령 전체의
  오류였다 — 서비스를 지정하지 않은 `docker compose up` 은 종료 코드 1 로 아무것도 만들지 않았고,
  서비스 하나를 지정한 `up` 은 성공했다. 그래서 `full`·`none` 배포 자체가 실패한다는 문장으로
  고치고, `.env` 대용 금지는 별도 줄로 나눴다. `chmod 600` 과 그 이유(nginx 가 `./secrets` 를
  통째로 마운트한다)를 덧붙였다.
- 컨테이너 수는 `journal_worker` 가 compose 본체에 들어와 넷이다. 「운영 컨테이너」 를
  「`docker-compose.prod.yml` 의 컨테이너」 로 바꿨다 — 배포 여부와 무관한 코드 사실만 적는다.

같은 동기화에서 덧붙인 것(걷어낸 원문 없음) = API 표 `/api/balance/exit-lines` 행 · 프로젝트 구조
`journal_worker/` 줄 · 선택적 배포 절의 `journal` 축 설명 줄.

→ CHANGELOG: cycle412 행

---

## 프로세스 구성과 분리 로드맵

### 2026-10-09 cycle412 마무리 문서 동기화 — `journal_worker` 가 `trade_history` 를 읽는다

정본 원문(바뀐 줄):

```
backend 가 남긴 로그와 조회 API 응답을 읽기만 하고, KIS 에는 접속하지 않는다. 매매에 관한 일은 전부
```

```
    JW -->|"trade_journal_* (전용 DB 역할)"| RDS
```

경위: cycle412 보완(`17dbd16c`)이 대사를 루프에 연결해 워커가 60초 간격으로 `trade_history` 를
SELECT 한다(전용 역할에 SELECT 만 있다). 원문은 그 읽기를 빠뜨렸다. 같은 동기화에서 「배포 전 호스트
준비」 에 `journal_worker` 실행 사용자 uid 1000 과 호스트 로그 읽기 권한 문장을 덧붙였다(걷어낸 원문
없음 — 근거 = `journal_worker/Dockerfile` `useradd --uid 1000 … journal` · `USER journal` · compose
`./logs:/app/logs:ro`).

→ CHANGELOG: cycle412 마무리 행

## 매매 전략
### 2026-10-15 문서 동기화 — 전략 9개 반영, donchian 깡토식 반영 (정본에서 옮긴 원문)

- | `donchian_swing` | 09:05~09:30 시장가 | 20일 신고가+추세 | -7% | ATR×2 트레일 · 멀티데이 (5~15일) |
- | 손절 | 매수가 대비 -7% 하드 손절. 터틀 매수(`_entry_atr` 스탬프가 있는 랏)는 대신 **2×ATR 하드손절 + -9% backstop**을 타고, 고점이 `매수가 + 1.5×entry_atr` 에 닿으면 손절선이 매수가로 승격된다(`breakeven_promote_atr`, 좁히는 방향만) |
- | 청산 | 코드 평가 순서대로 ① **시간 청산** — `breakout_fail_n_days`(기본 5 **영업일**) 이상 보유 + 현재가 < 돌파고점 → TIME_EXIT ② **채널 이탈** — 최근 `channel_exit_period`(기본 10)일 저가 하회 → TRAILING_STOP ③ **ATR(14)×2 Chandelier 트레일링**(`high_since_buy − ATR×2`) → TRAILING_STOP |
- AI 매수평가 행: cycle297(2026-09-17)이 **7전략 전부**로 넓혔다
- `_force_clear_main_only` — 대상은 VB·LTV 두 전략이고 각 전략의 `check_force_clear()` 가 목록을 정한다.

## 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)
### 2026-10-15 문서 동기화 — 21:30 일일 로그 분석에서 OpenAI 제거(cycle445) 반영 (정본에서 옮긴 원문)

- 직후 일일 로그 분석 리포트 생성 (OpenAI → `daily_log_reports`).
- 일일 로그 분석 = **21:30** 정산 직후 OpenAI 가 system_logs+trade_history 를 분석한 운영 개선 리포트(영업일 리스트 + findings + 메트릭).

## 프로세스 구성과 분리 로드맵
### 2026-10-15 문서 동기화 — 컨테이너 5개(llm_worker 가동), 1단계 상태 정정 (정본에서 옮긴 원문)

- `docker-compose.prod.yml` 의 컨테이너는 4개다 — `backend` · `frontend` · `macro` · `journal_worker`.
- | 1 | **AI 매수평가** — … 큐는 별도 메시지 브로커가 아니라 `llm_buy_evaluations` 테이블(043) | **진행 중** |

→ CHANGELOG: cycle445 · cycle446 · cycle405 행

## 2026-10-15 — 전략 E·F·G 절 코드 대조 (/sync-docs 후속)

- 전략 E(BFB) 진입·매수 칸에 돌파 유지 3분(`breakout_retention_minutes`)과 만석 중 직전 가격 추적(cycle449)을 더하고, 수량·공통 스위치 칸을 새로 둠.
- 전략 F(VCP) 에 만석 중 직전 가격 추적(cycle449), 수량, 공통 스위치 칸을 더함.
- 전략 G(kojiro) 에 후보 점수 순서, 매수 한도(`max_positions` 5 · 섹터 2 · Σ 오픈리스크 4.5%), 공통 스위치 칸을 더함.
- 걷어낸 문장 없음(README 의 E·F·G 에는 운영 DB 사실 문장이 없었음).

→ CHANGELOG: cycle449 · cycle405 행
