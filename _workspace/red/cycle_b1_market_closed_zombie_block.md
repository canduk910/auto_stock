# 사이클 B-1 Red — 매도 좀비 폭주 차단 (시장 closed 거부 후 외부 재호출 게이트)

> **작성일**: 2026-06-01
> **단계**: Red (실패 테스트 작성 완료)
> **다음 단계**: Green (backend-dev → `src/engine/order_engine.py` 진입 게이트 + 차단 등록 + reset 헬퍼)
> **명세서**: `_workspace/cycle_b1_market_closed_zombie_block_spec.md` 3-A
> **분석 카드**: `_workspace/2026-06-01_log_analysis.md` B-1

---

## 1. 산출물

- **테스트 파일**: `tests/unit/engine/test_b1_market_closed_zombie_block.py` (7 시나리오, 약 470 LOC)

---

## 2. Red 실행 결과 (2026-06-01)

```
python -m pytest tests/unit/engine/test_b1_market_closed_zombie_block.py -v
========================= 6 failed, 2 passed in 0.31s ==========================
```

### 시나리오별 상태

| # | 시나리오 | 상태 | root cause / 회귀 가드 의도 |
|---|---------|------|---------------------------|
| S1 | APBK0918 100회 호출 시 KIS 1회만 | **FAIL** | 진입 게이트 미구현 — 100회 모두 KIS 호출됨. `_market_closed_blocked` 속성 부재. |
| S2 | KIOK0320 도 동일 차단 | **FAIL** | 동일 — 진입 게이트 미구현. |
| S3a | `is_insufficient_quantity` 차단 set 미등록 (회귀 가드) | PASS | **우연 PASS 아님** — set 자체 부재 → `getattr(...,{})` 빈 dict → 명세 의도 그대로. Green 구현 후에도 등록 안 되어야 정상 (회귀 가드 본의). |
| S3b | `is_market_order_disallowed` 폴백 + 차단 set 미등록 (회귀 가드) | PASS | 동일 — 기존 폴백 분기 정상 작동 + set 미등록 (set 자체 부재). |
| S4 | TTL 만료 후 재진입 가능 | **FAIL** | `_market_closed_blocked` 속성 부재 → 등록 검증 단계에서 AttributeError. |
| S5 | ticker별 격리 (064400 차단 후 005930 정상) | **FAIL** | 동일 — 등록 검증 단계에서 set 부재. |
| S6 | `reset_daily_state()` 호출 시 set clear | **FAIL** | `OrderEngine.reset_daily_state` 메서드 부재 → AttributeError. |
| S7 | 진입 차단 INFO emit cap (ticker별 일일 1회) | **FAIL** | `[market_closed_blocked]` prefix write_log 0건 — emit 자체 미구현. |

### S3a/S3b PASS 해명

명세 3-A 의 산출물 #3 "일부 PASS 하면 *왜* 인지 확인" 요구에 대한 답:
- **회귀 가드 테스트** 의 본의: "다른 거부 분류 (보유 부족 / 시장가 호가 불가 / 예수금 부족) 가 신규 차단 set 에 *잘못* 등록되면 안 됨" 검증.
- 현재 set 자체가 부재 → 자연스럽게 등록 안 됨 → PASS. Green 구현 후에도 set 등록 분기는 `is_market_closed_rejection(e) == True` 에만 작동해야 하므로 동일하게 PASS 유지가 *정상*.
- Green 구현이 다른 분기에 set 등록을 잘못 끼워 넣으면 S3a/S3b 가 FAIL 로 전환 → 회귀 가드로 기능.

---

## 3. Green 단계 발주 정보 (backend-dev 전달)

### 신규 인스턴스 필드 후보 (명세 3-B-1 그대로)

```python
# OrderEngine.__init__
self._market_closed_blocked: dict[str, datetime] = {}        # ticker -> expiry (KST aware)
self._market_closed_blocked_logged_today: set[str] = set()   # ticker (S7 cap)
```

### TTL 계산 헬퍼

**grep 결과**: `src/` 전역에 `_next_market_open_kst` / `_compute_next_market_open` 등 *기존 헬퍼 없음*.
- Green 단계에서 `order_engine.py` 모듈 함수로 신규 추가 필요:
  ```python
  def _compute_next_market_open_kst(now: datetime) -> datetime:
      """now KST 기준 다음 KRX 정규시간 시작 시각 (09:00) 반환.
      now < 09:00 → 당일 09:00. now >= 09:00 → 다음 영업일 09:00.
      주말 스킵 (평일 단순 +1일). KIS 휴장일 처리는 본 사이클 비범위 (보류).
      """
  ```
- 시간 비교는 `KST_TZ = timezone(timedelta(hours=9))` aware datetime — `scanner.KST_TZ` 재사용 또는 모듈 내 재정의 둘 다 OK.
- 사이클 36 NameError 선례 (datetime.now() 단독 금지) 회피.

### 차단 검사 위치

`execute_sell()` 진입 직후, `self._selling` 가드 *전* 또는 *직후*:
```python
# self._selling.add(ticker) 직후 권장 — _selling 중복 차단과 동급 진입 게이트
now_kst = datetime.now(KST_TZ)
expiry = self._market_closed_blocked.get(ticker)
if expiry:
    if now_kst < expiry:
        if ticker not in self._market_closed_blocked_logged_today:
            self._market_closed_blocked_logged_today.add(ticker)
            await write_log(
                "INFO",
                f"[market_closed_blocked] ticker={ticker} strategy={strategy_id} "
                f"expiry={expiry.isoformat()}",
            )
        self._selling.discard(ticker)  # _selling 추가했다면 정리
        return
    else:
        del self._market_closed_blocked[ticker]  # 자연 만료
```

### 차단 등록 위치

`is_market_closed_rejection(e)` True 분기 내 (현재 `order_engine.py:523~569`), 기존 `WARNING + write_log + stock_master 사후 보강 + return` 동작 *그대로 보존* + 다음 1줄 추가:
```python
self._market_closed_blocked[ticker] = _compute_next_market_open_kst(datetime.now(KST_TZ))
```

### `reset_daily_state()` 헬퍼 (캡슐화)

```python
def reset_daily_state(self) -> None:
    """매일 정산 후 호출 (scheduler `_reset_daily_state` 가 위임)."""
    self._market_closed_blocked.clear()
    self._market_closed_blocked_logged_today.clear()
```
- `scheduler._reset_daily_state()` 가 `self.order_engine.reset_daily_state()` 호출 추가.

---

## 4. 회귀 가드 확인 항목 (Green 후 tester 검증)

- 기존 1748 PASS 무회귀 — `python -m pytest -q tests/`
- `tests/unit/engine/test_order_engine_sell_fallback.py` 전체 PASS (시나리오 D2 `_market_closed_rejection` 분기와 본 사이클 진입 게이트 *상호 작용* 영향)
- S3a/S3b PASS 유지 — 다른 거부 분류는 차단 set 미등록 (회귀)

---

## 5. 비범위 (본 사이클 외, 후속 카드)

- 휴장일 API 통합 — `_compute_next_market_open_kst` 가 KIS `chk-holiday` 호출 안 함 (보수적 다음 영업일 단순 추정).
- 진입 차단 메트릭 — `[market_closed_blocked_drop] count=N` 등 일일 분석 통합 (V-1 카드).
- 09:00 직후에도 동일 거부가 이어지는 케이스 — TTL 단순 만료가 부족할 때 보강 (별도 사이클).
