# 사이클 E-1 — 지수ETF 고지로 스테이지 레짐 신호 (관찰 전용 다크런치)

자문: `_workspace/domain_consult/cycle_etf_kojiro_regime_20260731.md` (GO — 다크런치 우선)
사용자 지시: "최종 레짐판정에 dkstock뿐 아니라 지수ETF의 고지로 스테이지도 고려" + defensive_enabled 이미 활성

## 실측 검증 (2026-07-31 EC2)
KODEX200(069500) 현재 stage4, 60일 whipsaw 3회 / 코스닥150(229200) 현재 stage4, 60일 방어 88%. 둘 다 dkstock=defensive 와 독립 부합. 개념 검증 완료.

## 범위 (E-1 = 관찰만, 매수 가드 행위 무변경)
**block_reason 통합·SOFT 상한·reasons 태깅·cycle D robustness 는 E-2(2주 관찰 후) 인계.** E-1 은 계산 + 로그 + API 관찰 노출만 = **배제 0, 매매 행위 byte 동일**.

## 스테이지 의미 (kojiro_indicators._STAGE_MAP 정본, 재사용)
1: EMA5>20>40(안정상승) / 2: 20>5>40 / 3: 20>40>5(하락전환) / 4: 40>20>5(안정하락) / 5: 40>5>20 / 6: 5>40>20(상승전환). 대순환 1→2→3→4→5→6→1. **방어집합 {3,4,5}** (자문).

## 행위
- **E-1 (config)**: `system_config` `etf_regime_enabled: bool = False` get/set 헬퍼 (`dkstock_regime_enabled`/`defensive_enabled` 답습). DB 토글. **E-1 에선 저장/조회만 — 아직 block 경로 미소비**(활성은 E-2).
- **E-2 (스테이지 계산 순수 로직)**: `market_regime.py` 신규 `compute_etf_stage_signal() -> EtfStageSignal` — `stock_master_daily` 069500 + 229200 최근 일봉 조회 → `kojiro_indicators.ema(5/20/40)` + `stage_of` 로 각 지수 현재 스테이지 + **2일 연속 방어 확인**(최근 2 스테이지 모두 ∈ {3,4,5}) 산출. 반환 = `{kospi_stage, kosdaq_stage, kospi_defensive_2d, kosdaq_defensive_2d, etf_defensive(OR), stale_kospi, stale_kosdaq}`. **FREEZE 무관** — stage_of 순수함수 재사용, ETF 전용 5/20/40 파라미터화 금지(정체성 상수).
- **E-3 (신선도 게이트)**: 각 지수 최근 `bas_dd` 가 `ETF_STALE_MAX_BUSINESS_DAYS`(예: 5) 초과 stale → 그 지수 신호 skip(defensive 판정 제외) + `stale_*=True` + WARNING. 양쪽 stale → etf_defensive=None(신호 없음).
- **E-4 (MarketRegime 관찰 필드)**: `MarketRegime` 에 etf 신호 보관(관찰). boot(`_refresh_market_regime_and_persist`)이 dkstock fetch **와 독립**으로 `compute_etf_stage_signal()` 호출(dkstock 죽어도 계산) → 결과를 regime 에 부착(관찰). **block_reason/get_buy_block_state 미변경**(E-1 배제 0).
- **E-5 (boot 관찰 로그)**: `[etf_regime] kospi=stageN kosdaq=stageM etf_defensive=X enabled=Y (관찰)` 1행. enabled=False 여도 계산·로그(다크런치 관찰).
- **E-6 (API 관찰 노출)**: buy-block 상태 또는 market-regime 응답에 관찰 필드(`etf_kospi_stage`/`etf_kosdaq_stage`/`etf_defensive`/`etf_enabled`) 추가 — 운영자/tester 가 2주 관찰 가능(curl). 프론트 배너는 E-2 활성 시.
- **E-7 (snapshot 기록, no migration)**: `market_regime_snapshots.raw_response` JSONB 에 etf 신호 동봉(마이그레이션 회피) — 2주 관찰 이력 영속.
- **E-8 (안전/회귀)**: `get_buy_block_state()` blocked/soft_multiplier/reasons **완전 무변경**(E-1). `git diff risk.py order_engine.py realtime/ auth/ api/order.py` = 0. etf 계산 실패 graceful(regime 유효 보존, boot 진행). 매매 안전성 8영역 diff 0.

## E-2 인계 (2주 관찰 후, 별도 사이클)
- block_reason 에 etf 방어 OR 사유 통합(dkstock 독립) — 도메인 ① reasons 태깅(dkstock/etf 구분)
- SOFT 상한(etf 사유는 HARD 승격 금지, etf-only 트리거 → ×0.5) — 도메인 ④
- cycle D robustness: dkstock empty 여도 etf 신선하면 `has_regime_data`/`guard_inert` 반영(무력 아님) — 도메인 ②
- 프론트 배너 + `etf_regime_enabled` 토글 UI
- 게이트 4조건: dkstock overlap / 지수단독방어 유효성 / 헛방어율 / 잔존 whipsaw (2주 실측)

## 데이터 검증 인계 (tester)
069500/229200 최근 3~6개월 스테이지 시퀀스 + dkstock defensive overlap 산출(EC2, 로컬 RDS 부재). E-1 실측(60일 whipsaw 2~3회/현재 stage4 양지수) 확장.
