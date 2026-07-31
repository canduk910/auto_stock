# 사이클 E-1 Red 로그 — 지수ETF 고지로 스테이지 레짐 신호 (관찰 전용 다크런치)

- 작성: tdd-engineer (Red 단계, 구현 금지)
- 명세: `_workspace/red/_behaviors_cycleE_etf_regime_20260731.md`
- 자문: `_workspace/domain_consult/cycle_etf_kojiro_regime_20260731.md` (GO — 다크런치 우선)
- 범위: E-1 = 계산 + 로그 + API 노출까지. 매수 가드 행위(blocked/soft_multiplier/reasons) byte 동일 = **배제 0**. block 통합·SOFT 상한·reasons 태깅은 E-2 인계.

## 신규 파일 (2)

| 파일 | 케이스 | 커버 |
|------|--------|------|
| `tests/unit/engine/test_cycleE_etf_regime.py` | 32 | E-1 config / E-2 방어집합·2일확인·스테이지계산·OR / E-3 신선도 / E-4·E-5 boot 관찰 / E-8 안전 |
| `tests/unit/routes/test_cycleE_etf_observe_field.py` | 4 | E-6 buy-block 응답 etf 관찰 4 필드 |

합계 36 케이스.

## 실행 결과 (Red 확인)

```
python -m pytest tests/unit/engine/test_cycleE_etf_regime.py \
                 tests/unit/routes/test_cycleE_etf_observe_field.py -q
→ 32 failed, 4 passed
```

- **RED 32** = 미구현 심볼 부재 (`get_etf_regime_enabled`/`DEFENSIVE_STAGES`/`is_two_day_defensive`/`compute_etf_stage_signal`/`get_current_etf_signal`/`[etf_regime]` 로그/응답 etf_* 필드).
- **GREEN 4 (의도된 안전 기준선/회귀 가드)**:
  - `test_buy_block_state_unchanged_empty_soft` — empty+SOFT → blocked/mult/reasons 기존 동일 (E-8 배제 0).
  - `test_buy_block_state_unchanged_defensive_soft` — defensive+SOFT → ×0.5 (etf 무관 기존 동작).
  - `test_boot_graceful_when_etf_compute_raises` — 현재 vacuous PASS (boot 가 아직 compute 미호출). 구현 후 etf 예외 graceful 을 강제 (naive 구현 시 RED 전환 → 재-GREEN 의무).
  - `test_buy_block_status_existing_fields_unchanged` — mode/blocked/soft_multiplier/data_available 기존 동일.

## 안전 기준선 확인 (무영향)

```
tests/unit/engine/test_cycleD_regime_inert.py
tests/unit/routes/test_cycleD_buyblock_inert_field.py
tests/unit/engine/test_market_regime*.py
→ 43 passed
```

## Green 도달성 사전 검증 (합성 일봉 → 실 지표)

`kojiro_indicators.ema`/`stage_of` 실호출로 합성 시리즈가 목표 스테이지를 유도함을 확인 (mock 금지 = 스테이지 정확성 검증):

```
rising  (10000 + 30*i, n=90)  → 최종 stage 1, last2 [1,1]
falling (13000 - 30*i, n=90)  → 최종 stage 4, last2 [4,4]
```

→ E-2 end-to-end 테스트(양지수 하락→방어 True / 상승→False / 편측 OR)가 Green 에서 도달 가능.

## backend-dev 인계 인터페이스 (Green 계약)

### 1. `src/db/system_config.py` — config 토글
```python
async def get_etf_regime_enabled() -> bool          # 키 부재 → False (auto_apply_enabled 패턴, .env fallback 없음)
async def set_etf_regime_enabled(value: bool) -> None  # JSONB {"value": bool} upsert
# 키 = "etf_regime_enabled"
```
- 테스트 seam: `sc._select_value` / `sc._upsert_value` monkeypatch. `get` 은 `_get_bool_or_none` 답습 권장.

### 2. `src/engine/market_regime.py` — 순수 로직 + 계산
```python
DEFENSIVE_STAGES = frozenset({3, 4, 5})   # 자문 §Q2 하락 사분면 정본

def is_two_day_defensive(stages: list[int | None]) -> bool
# 최근 2 스테이지(stages[-2:]) 모두 ∈ DEFENSIVE_STAGES → True.
# len < 2 / None 포함 → False.

@dataclass(frozen=True)
class EtfStageSignal:
    kospi_stage: int | None
    kosdaq_stage: int | None
    kospi_defensive_2d: bool
    kosdaq_defensive_2d: bool
    etf_defensive: bool | None   # 신선 지수들의 defensive_2d OR. 양쪽 stale → None
    stale_kospi: bool
    stale_kosdaq: bool

ETF_KOSPI_TICKER = "069500"    # KODEX 200
ETF_KOSDAQ_TICKER = "229200"   # KODEX 코스닥150

async def compute_etf_stage_signal(*, now: datetime | None = None) -> EtfStageSignal
```
- **일봉 소스 seam = `stock_master_daily.get_recent_daily(ticker, N)`** (정규화 컬럼 `close_price`/`bas_dd`, DESC). 테스트가 이 함수를 monkeypatch. `get_recent_daily_normalized`(KIS 폴백) 는 지수ETF 잉여 KIS 호출 유발 → 미채택.
- 계산: rows 를 bas_dd **ASC 정렬** 후 `pd.Series(close_price)` → kojiro `ema(5/20/40)` + `stage_of`(prev 캐리, 동가 유지) 순차 → 최종 스테이지 + `is_two_day_defensive`.
- **5/20/40 = 정체성 상수** — ETF 전용 파라미터화 금지 (`KojiroIndicatorConfig` 기본값 그대로).
- **신선도 게이트**: 최신 bas_dd(`rows[0]["bas_dd"]`, DESC) 가 `now.date()` 대비 오래되면(예: `ETF_STALE_MAX_BUSINESS_DAYS`=5 초과) 그 지수 = stale → `stage=None`, `defensive_2d=False`, `stale=True`, WARNING. 빈 조회도 stale.
  - 테스트는 30일 gap(명백 stale) / 0일(fresh) 만 검증 — 임계 구현 방식(달력일/영업일) 은 backend 재량, 상수명 미강제.
- `etf_defensive` = 신선 지수들의 `defensive_2d` OR. 양쪽 stale → `None`.

```python
_current_etf_signal: EtfStageSignal | None = None
def get_current_etf_signal() -> EtfStageSignal | None
def set_current_etf_signal(sig) -> None
# get_current_regime/set_current_regime 싱글톤 패턴 답습 (E-6 API 소스).
```

### 3. `src/engine/scheduler.py::_refresh_market_regime_and_persist` — boot 관찰 배선
- `set_current_regime(regime)` 직후, **dkstock 성패 독립** 으로:
  ```python
  try:
      sig = await compute_etf_stage_signal()
      set_current_etf_signal(sig)
      enabled = await get_etf_regime_enabled()
      logger.info("[etf_regime] kospi=stage%s kosdaq=stage%s etf_defensive=%s enabled=%s (관찰)",
                  sig.kospi_stage, sig.kosdaq_stage, sig.etf_defensive, enabled)
  except Exception:
      logger.exception("[etf_regime] 계산 실패 graceful")   # boot 진행 (E-8)
  ```
- 로그 계약(테스트 단언): `[etf_regime]` 1행 + `enabled=False` + `etf_defensive=True` + `kospi=stage4` + `kosdaq=stage4` 부분문자열.
- **compute 는 enabled=False(다크런치) 여도 호출** + **dkstock empty 여도 호출**.
- `get_buy_block_state()` / blocked / reasons / soft_multiplier 로직 **완전 무변경** (E-1 배제 0).

### 4. `src/models/system_integrations.py` + `src/routes/system_integrations.py::_build_buy_block_status` — E-6 관찰 노출
- `BuyBlockStatusResponse` 에 4 필드 추가:
  ```python
  etf_kospi_stage: int | None = None
  etf_kosdaq_stage: int | None = None
  etf_defensive: bool | None = None
  etf_enabled: bool = False
  ```
- `_build_buy_block_status()`: `sig = mr_mod.get_current_etf_signal()` (요청마다 재계산 X, boot 부착 싱글톤) + `enabled = await sc.get_etf_regime_enabled()`. `sig` None 시 스테이지/방어 None.
- 기존 mode/blocked/reasons/soft_multiplier/data_available/guard_inert 무변경.

## E-2 (활성) 인계 (2주 관찰 후, 별도 사이클 — 범위 밖)
- block_reason etf OR 통합 + reasons 태깅(dkstock/etf 구분) + SOFT 상한(etf-only → ×0.5, HARD 승격 금지) + cycle D `has_regime_data`/`guard_inert` etf 반영 + 프론트 배너 + `etf_regime_enabled` 토글 UI.

## tester 인계 (데이터 검증)
- EC2 로컬 RDS 부재로 미산출 — 069500/229200 최근 3~6개월 스테이지 시퀀스 + dkstock defensive overlap + 헛방어율 + 2일확인 후 잔존 whipsaw.
