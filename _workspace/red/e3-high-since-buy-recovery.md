# E3 — high_since_buy 일봉 폴백 보정 (donchian_swing)

## 의도
시세 미수신 누적으로 `pos.high_since_buy` 가 매수가 부근에 동결되어 chandelier 트레일링 손절선이 첫 갭다운에 즉시 청산되는 결함 차단. `_boot()` → `recompute_held_atr()` 시점에 KIS 일봉으로 매수일~전영업일 일별 high max 로 보정.

## Red 테스트 파일
`tests/unit/engine/test_high_since_buy_recovery.py` (총 9 테스트)

| Case | 상태 | 검증 |
|------|------|------|
| A | RED | 어제 high > buy_price → 보정 + update_high 호출 |
| B | RED | buy_date=today → skip (fetch도 안 함) |
| C | RED | 빈 candles → skip |
| D | RED | fetch raise → 1종목 skip, 나머지 정상 |
| E | RED | 모든 high < buy_price → 보정 안 함 |
| F | RED | candles[0]=오늘, candles[-1]=매수일 → 둘 다 제외 |
| G | RED | buy_date > today → skip + WARNING |
| H | RED | 3종목 sequential, 1종목 실패 격리 |
| 추가 | RED | recompute_held_atr 통합 — ATR + high_since_buy 동시 보정 |

## Red 첫 실행 결과
```
AttributeError: 'DonchianSwingStrategy' object has no attribute 'recompute_high_since_buy'
```
신규 메서드 미구현 — 정상 Red.

## Green 구현 계획
1. `DonchianSwingStrategy.recompute_high_since_buy()` async 메서드 신설
   - 보유 종목 순회 (sequential)
   - `pos.buy_date < today` 가드 (당일/미래 skip + 미래는 WARNING)
   - `fetch_daily_candles(ticker, days=N)` — N = max(days_held + 5, 10)
   - candles 필터: `buy_date < bsop_date < today` 만
   - `max(eligible_highs)` 가 기존 `high_since_buy` 초과 시 갱신
   - DB UPDATE: `update_high(ticker, new_high)`
   - `system_logs` `[high_since_buy_recover]` prefix 1행
   - fetch 예외 → exception 로그 + 해당 종목 skip, 다른 포지션은 계속
2. `recompute_held_atr()` 안에서 같은 일봉 fetch 결과로 high_since_buy 보정도 동시 수행 (fetch 비용 절반)
3. `scheduler._boot()` 는 변경 없음 — 이미 `recompute_held_atr()` 호출 중

## 절대 금지 (사용자 명세)
- git commit/add/push 금지
- 다른 전략(momentum/VB/LTV)으로 호출 확장 금지
- `risk.py:72` 실시간 시세 갱신 로직 변경 금지
- 일봉 fetch 병렬 호출 금지 (`asyncio.gather` 금지) — KIS Rate Limit 안전
- 매수일 당일 보정 금지 (buy_price 덮어쓸 위험)
