# 사이클 D — 레짐 가드 silent inert 가시화 (관찰성, 매매 행위 무변경)

## 배경 (2026-07-31 진단)
dkstock.cloud Let's Encrypt 인증서 07-27 만료(`certificate has expired`) → httpx verify=True 거부(정상) → `refresh_from_dkstock()` 가 `MarketRegime.empty()` 반환 → 07-27~31 4일간 매수 가드(mode=SOFT) 무력화됐으나 **아무 경보 없이 대시보드는 "정상+평온"으로 표시**.

## 근본 결함
`get_buy_block_state()` 가 두 상태를 동일 결과로 반환:
- (정상) 데이터 있음 + 임계 미발동 → `blocked=False, reasons=[]`
- (위험) 데이터 없음(empty regime) → `blocked=False, reasons=[]`
운영자 구분 불가 = "false sense of protection".

## 시정 방침
**관찰성만 추가. 매매 행위(blocked/soft_multiplier) byte 동일 = fail-open 보존.** "데이터 없을 때 매수 차단(fail-safe)" 전환 및 "수동 방어 오버라이드"는 **범위 외 — 별도 도메인/사용자 결정**으로 인계(트레이딩 행위 변경 + dkstock 다운 시 전량 매수 차단 위험).

## 행위

- **D-1** `MarketRegime.has_regime_data` 프로퍼티 신규 — 실제 매크로 데이터 보유 시 True, `empty()` 폴백 시 False. 판정 = `regime/vix/fear_greed_score` 중 1개라도 not None 또는 `bool(raw)` (persist_snapshot 의 `regime is None` empty 판정과 정합).
- **D-2** `BuyBlockState` 에 `data_available: bool = True` 필드 추가 (default True — 기존 생성/테스트 회귀 0).
- **D-3** `get_buy_block_state()` 가 반환 state 의 `data_available = self.has_regime_data` 세팅. **blocked/soft_multiplier/reasons 로직 완전 무변경** (OFF/HARD/WARN/SOFT/unknown/db-fallback 전 분기). 60s TTL 캐시 상호작용 보존.
- **D-4** boot 매크로 경로: `refresh_from_dkstock()` 결과가 empty(has_regime_data=False) **AND** 설정 `buy_block_mode != OFF` 이면 `logger.warning("[regime_guard_inert] mode=%s 설정됐으나 매크로 데이터 미유입 → 가드 무력, 데이터 복구 전까지 매수 무제한 통과", mode)` 발화 (boot 1회/일, cap 불요, _DbLogHandler 로 system_logs 자동 영속). OFF 이거나 데이터 유입 시 미발화.
- **D-5** `BuyBlockStatusResponse` 에 `data_available: bool` + `guard_inert: bool`(= `mode != "OFF" and not data_available`) 추가. `_build_buy_block_status` 가 state + mode 로 채움. 프론트 degraded 배너는 후속(frontend-dev).
- **D-6 (안전/회귀)** risk.on_tick 매수 차단 거동 무변경 — `blocked`/`soft_multiplier` 동일. 기존 buy-block/regime 테스트 전량 PASS. **매매 안전성 8영역 diff 0** (blocked 평가 무변경, 신규 필드는 로깅/표시용).

## 매매 안전성 diff 0 의무
`src/engine/risk.py`(blocked/soft_multiplier 소비 로직) · `src/engine/order_engine.py` · `src/realtime/` · `src/auth/` · `src/api/order.py` — 매수 차단 실행 경로 무변경. 변경 = `market_regime.py`(프로퍼티+필드+세팅) + boot 경보 1줄 + 라우트/모델 필드 + 테스트.

## 인계 (별도 결정)
1. fail-open → fail-safe (데이터 없을 때 활성 가드가 매수 차단) — domain-expert 자문 필요, dkstock 다운 = 전량 매수 차단 위험
2. 수동 방어 오버라이드 (운영자가 매크로 무관 강제 방어 posture) — 신규 기능, 사용자 결정
3. dkstock.cloud 인증서 갱신 — **서버측 운영 조치(사용자/운영자)**, 코드 무관. 갱신 후 다음 boot 또는 dkstock-regime 토글 재발화로 자동 회복
4. 장중 매크로 재시도 (현재 boot 1회만 fetch, 실패 시 종일 무력) — 후속 검토

---

## 사이클 D-FE — 프론트 가시화 (frontend, tester DEF-1 봉합)
백엔드 `guard_inert` 필드가 어떤 UI 에도 안 떠서 운영자는 여전히 "정상+평온" 오인 = 사이클 목적 미달. BuyBlockSection 에 무력 배너 추가.

앵커 (tester 확인):
- 타입: `frontend/src/types/integrations.ts::BuyBlockState`(L44-50, 필드 mode/thresholds/blocked/reasons/soft_multiplier)
- 컴포넌트: `frontend/src/components/IntegrationToggleCard.tsx::BuyBlockSection`(L181~), mode 렌더 L301-306 + reasons L318-336(amber 패턴)
- e2e mock: `e2e/fixtures/api-mocks.ts` buy-block 라우트 L244-258
- vitest: `frontend/src/components/__tests__/IntegrationToggleCard.test.tsx`(인라인 `server.use(http.get('/api/integrations/buy-block',...))`)

행위:
- **D-FE1** `BuyBlockState` 타입에 `data_available: boolean` + `guard_inert: boolean` 추가 (백엔드 응답 1:1).
- **D-FE2** `BuyBlockSection`: `data.guard_inert === true` 시 `data-testid="buy-block-guard-inert"` 배너 렌더 (mode 행 직후, reasons 위 — 최상단 가시). **red/orange 강조**(amber 사유보다 강함 — false sense of protection 위험): `bg-red-100 text-red-800 border-red-300` 계열. 텍스트 = "⚠️ 매수 가드 무력 — 레짐 매크로 데이터 미유입. mode={data.mode} 설정됐으나 실제 방어 미작동 (데이터 복구 전까지 매수 무제한 통과)". `guard_inert === false` 시 미렌더.
- **D-FE3** e2e `api-mocks.ts` buy-block 라우트 응답에 `data_available: false`(또는 true) + `guard_inert` 추가 (기존 mode=HARD mock → guard_inert 정합값). MSW 는 인라인 per-test 라 vitest 케이스가 직접 stub.
- **D-FE4** 회귀 가드 (vitest, `IntegrationToggleCard.test.tsx` append): (a) guard_inert=true → 배너 렌더 + 텍스트 (b) guard_inert=false → 배너 미렌더. 기존 buy-block 케이스 무수정.

프론트 전용 — 백엔드/매매 무관. `useQuery retry:1`(사이클 65 H3) / KST(사이클 68) / Playwright LIFO(사이클 80#3) 영속.
