# 사이클 2 행위 분해 (Red → Green)

## 행위 그룹 1 — `dkstock_client` (외부 의존, 격리 가능)
1. **B1-A** `DkstockClient.login()` 정상 → 200 + access_token/refresh_token 추출
2. **B1-B** 401 (잘못된 자격증명) → `ExternalAPIError` raise
3. **B1-C** 만료 토큰(401 first → refresh 후 200) → `_request()` 자동 재시도 1회
4. **B1-D** refresh_token 만료 → `ExternalAPIError` (운영자 SSH 갱신 안내 메시지 포함)
5. **B1-E** `get_macro_cycle()` 응답 파싱 (regime/cycle/params dict 추출)
6. **B1-F** 외부 서버 다운 (httpx.ConnectError) → `ExternalAPIError`
7. **B1-G** `DKSTOCK_REGIME_ENABLED=false` 시 `ConfigError` raise (생성자 가드)

## 행위 그룹 2 — `MarketRegime` (도메인 로직, dkstock_client 모킹)
1. **B2-A** `is_buy_allowed("momentum")` regime=aggressive, vix=15, fg=50 → True
2. **B2-B** regime=defensive → False, block_reason 포함
3. **B2-C** vix=26 → False, block_reason 포함
4. **B2-D** fear_greed_score=86 → False (극도 탐욕)
5. **B2-E** fear_greed_score=14 → False (극도 공포)
6. **B2-F** regime 정보 없음(None) → True (graceful fallback)
7. **B2-G** `cash_usage_ratio_from_regime({"cash_min": 75})` → 0.25 / 50 → 0.5 / 20 → 0.8
8. **B2-H** clamp [0.0, 1.0] (cash_min=-50 → 1.0 / cash_min=150 → 0.0)
9. **B2-I** `auto_regime_adjust=False` 시 cash_usage_ratio 변경 안 함

## 행위 그룹 3 — DB CRUD
1. **B3-A** `insert_snapshot()` 정상 INSERT + UUID 반환
2. **B3-B** UNIQUE(snapshot_date) 충돌 시 None 반환 (중복 INSERT 무시)
3. **B3-C** `get_latest()` snapshot_date DESC LIMIT 1

## 행위 그룹 4 — `system_config` auto_regime_adjust + 범위 확장
1. **B4-A** `get_auto_regime_adjust()` 미설정 시 True (기본값)
2. **B4-B** `set_auto_regime_adjust(False)` → upsert + 재조회 False
3. **B4-C** `set_cash_usage_ratio(0.0)` / `(0.25)` / `(1.0)` 정상 (범위 [0.0, 1.0])

## 행위 그룹 5 — `_boot()` 통합 (통합 테스트)
1. **B5-A** `DKSTOCK_REGIME_ENABLED=true` + auto_adjust=true 시:
   - 매크로 fetch → snapshot INSERT → cash_usage_ratio 자동 갱신 → `allocate_funds()` 호출

## 행위 그룹 6 — `risk.on_tick` 매수 가드
1. **B6-A** 매수 신호 발생 시점에 `market_regime.is_buy_allowed(strategy_id)=False` → `execute_buy` 호출 안 함
2. **B6-B** is_buy_allowed=True → 기존 동작 유지 (정상 매수)
3. **B6-C** 청산 신호는 가드 무관 → `execute_sell` 호출됨

## 행위 그룹 7 — 프론트엔드 `MarketRegimeCard`
1. **B7-A** regime=defensive 시 red 배지 + 매수 가드 amber 배너
2. **B7-B** regime=aggressive 시 blue 배지 + 가드 비활성
3. **B7-C** auto_regime_adjust 토글 클릭 → ConfirmModal 노출 → 확인 시 API 호출
4. **B7-D** VIX/Fear&Greed/Buffett 메트릭 grid 표시
5. **B7-E** API 에러 시 graceful fallback 메시지

## 의존 그래프

```
B1(dkstock_client)  →  B2(MarketRegime)
                         ↓
                     B3,B4(DB)
                         ↓
                     B5(_boot 통합)
                     B6(risk 매수가드)
                     B7(프론트)
```

병렬 가능: B1+B3+B4+B7 (서로 독립). B2 는 B1 모킹으로 진행 가능. B5/B6 는 B2 Green 이후.
