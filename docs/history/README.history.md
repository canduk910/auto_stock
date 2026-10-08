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
