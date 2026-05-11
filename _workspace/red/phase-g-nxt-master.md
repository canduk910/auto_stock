# Phase G — NXT 거래가능 사전 판별 (CTPF1002R + stock_master)

## 명세 출처

KIS MCP 4질의 결과(2026-05-11):
- (Q1) `CTPF1002R` 단건 조회로 NXT 등록 여부 사전 조회 가능
- (Q2) `cptt_trad_tr_psbl_yn` + `nxt_tr_stop_yn` 두 필드로 `nxt_tradable` 파생
- (Q3) 마스터 일괄 다운로드 API 없음 → 24h 캐시 운영
- (Q4) 단일 멀티 거래소 필드 없음 → 두 필드 조합으로 추론

이전 결함:
- `7712e0c` 매수 시장가 거부 → 지정가 폴백 (사후 대응)
- `68cfaa4` NXT 프리 매도 거부 좀비 차단 (사후 대응)
- 본 Phase G — 위 두 결함의 **사전 차단**

## 재현 조건

- NXT 미상장 종목(예: 012200 계양전기, ETF·SPAC 일부)에 대해 모멘텀 전략 `exchange=NXT` 또는 `SOR`로 라우팅
- 사후 차단(`7712e0c`/`68cfaa4`)은 KIS 거부 응답 수신 후 트리거 → 호가 5단계 폴백 또는 좀비 보존
- Phase G 사전 차단은 **주문 송신 전** stock_master 조회로 KRX 다운그레이드 → KIS 거부 자체 발생 0건

## 테스트 파일 경로

- `tests/unit/api/test_condition_stock_basics.py` — CTPF1002R 응답 파싱 (Y/N 4조합)
- `tests/unit/db/test_stock_master.py` — upsert/get/is_stale 24h TTL
- `tests/unit/engine/test_strategy_exchange_nxt_downgrade.py` — `_strategy_exchange_async` 다운그레이드 + 로그
- `tests/integration/test_next_day_clear_stock_master.py` — scheduler 익일 청산 사전 차단

## 변경 파일

- 신규: `src/models/stock.py`, `src/db/stock_master.py`, `supabase/migrations/015_stock_master.sql`
- 수정: `src/api/condition.py` (+ `inquire_stock_basics`), `src/engine/order_engine.py` (+ `_strategy_exchange_async`, execute_buy/sell 호출부, 거부 사후 보강), `src/engine/scheduler.py` (`_execute_next_day_clear` 사전 분기)
- 문서: 루트 `CLAUDE.md`, `src/CLAUDE.md`(간접), `src/api/CLAUDE.md`, `src/db/CLAUDE.md`, `src/engine/CLAUDE.md`, `docs/kis/error-codes.md` (5-3절), `_workspace/00_leader_trading_rules.md`

## 안전 불변식 보존 검증

- 매수 진입 ticker `isdigit()` 6자리 — 변경 없음
- 주문번호 매핑 동기 등록 (`place_order` 응답 직후, `await insert_trade` 전) — `_strategy_exchange_async`는 `place_order` 호출 *전* 결정으로 매핑 등록 순서 영향 없음
- 체결통보 race 가드 (`_completed_orders` + UPDATE 0건 보정 INSERT) — 변경 없음
- 09:00 KRX 시장가 일괄 청산 (`_drain_pending_next_day_clear`) — 변경 없음
- `is_market_closed_rejection` positions 보존 — 변경 없음 + stock_master 사후 보강 추가
- 익일 청산 NXT 지정가(`limit_price>0`) 분기는 `exchange="NXT"` 강제 유지 (사전 차단 적용 안 함, 호출자 책임)

## 마이그레이션 적용 상태

- 파일 작성 완료: `supabase/migrations/015_stock_master.sql`
- Supabase 운영 인스턴스 적용: **미적용** (user confirmation 필요 — `mcp__claude_ai_Supabase__apply_migration` 호출 권한 필요)
- 단위/통합 테스트는 `FakeSupabase` (인메모리 dict) 로 격리되어 마이그레이션 미적용 상태에서도 PASS

## 미해결 / 운영 권고

1. **운영 적용**: `migrations/015_stock_master.sql` 을 Supabase 운영 인스턴스에 적용 필요. CLI 또는 MCP `apply_migration` 호출 시 사용자 컨펌 필요
2. **VTS 통합 시나리오**: 모의계좌(VTS)에서 NXT 미등록 종목(예: ETF) 매수 시도 → KRX 자동 다운그레이드 + `[nxt_downgrade]` 로그 1행 → 다음 영업일 운영 trace 회수 후 확인
3. **Eager 갱신(향후)**: 현재는 Lazy 만 구현. 매수 후보 수가 늘어나면 07:50 `_boot()` 에서 후보 일괄 사전 갱신 옵션 추가 검토
4. **운영 모니터링 (7영업일)**: `daily_log_reports.findings` 에서 `APBK0918` NXT 거부 빈도 추이 → 사전 차단 효과 확인

## 회귀 커밋

(이 자리 — 커밋 시 SHA 기록)
