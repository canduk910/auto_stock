# 사이클 29 — Stale 영구 skip 결함 → 시간 기반 강제 재시도 전환

> **작성일**: 2026-05-21
> **작성자**: team-leader
> **사유 분류**: 인프라 안정성 결함 (매매 로직 변경 없음)
> **연관 사이클**: 사이클 24 (세션 단위 reconnect), 사이클 28 (stale 추적 강화), 사이클 17 (KIS 공식 답변 반영)

---

## 1. 결함 요약 (실측 데이터 — 2026-05-21 13:13~13:29)

```
[stale_watcher] subscribed=34 stale=23 force_reregistered=1 skipped=22
[stale_watcher_detail] session=main sub=25/41 fresh=2 stale=23 ratio=0.92
  stale=[(005935,r=9,@13:21:41), (006340,r=9,@13:21:42), ..., (232680,r=9,@13:21:43), ...+3]
```

### 결함의 본질
- `MAX_STALE_RETRIES=5` 초과 후 22개 종목이 `r=6→9` 카운터만 증가, 강제 재등록 0건
- 13:21:41 마지막 시도 후 8분 이상 추가 시도 없음
- `_check_and_resubscribe_stale` 의 `if retry > MAX_STALE_RETRIES: skipped_giveup += 1; continue` 분기(`src/engine/scheduler.py:2695-2699`)가 **무한 skip**으로 작동
- 설계 의도(거래정지·이상 종목 보호) 와 실상(정상 종목까지 12분 이상 영구 stale 잔류) 의 괴리

### 매매 영향 (현업 관점)
- **보유 종목 005935(삼성전자우) 가 stale 명단에 포함** — ATR×2 트레일링 / 하드 -7% 손절 평가 지연 위험
- 사용자 09:13 캡처에서 보고된 미매수 사고와 동일 패턴 (시세 단절 → 매수 신호 미발화)
- 사이클 28 의 추적 강화로 결함은 가시화됐으나, 복구 로직 부재로 단순 진단만 가능

---

## 2. 요구사항 (R1)

### 핵심 동작
영구 stale 무한 skip → **종목 단위 시간 기반 강제 재시도**로 전환.

1. `retry > MAX_STALE_RETRIES` (=5, 6회 이상) 분기에서 즉시 `continue` 금지
2. `_stale_last_resubscribe_at[ticker]` 마지막 강제 재등록 시각 확인 (사이클 28 신규 필드 재활용)
3. 분기 처리:
   - **마지막 재등록 후 `STALE_FORCE_RETRY_AFTER_SECS` (=300s, 5분) 이상 경과** → 강제 재등록 1회 + `_stale_retry_count[ticker] = 0` 카운터 리셋 (영구 stale 의심 해제, 신규 사이클 시작)
   - **5분 미경과** → 기존대로 skip (LMS / 앱키 정지 위험 차단 — KIS 공지)
   - **`_stale_last_resubscribe_at` 부재 (@ -)** → 즉시 1회 시도 (영구 stale 의심 첫 진입, 마지막 시각 미기록 케이스)
4. **시간당 동일 종목 최대 12회 재시도 cap** (5분 × 12 = 60분, 시간당 12회) — LMS 위험 추가 가드

### 새 로그 포맷
```
[stale_force_retry] ticker={t} retries={r} last_resub_age={elapsed:.0f}s — 강제 재시도 + 카운터 리셋
```
- INFO 레벨, `write_log` 영구 저장 (사이클 28 패턴 동일)
- 시간당 cap 도달 시: `[stale_force_retry_cap] ticker={t} attempts_in_hour={n} — LMS 위험 차단 skip` WARNING

### 신규 상수 (`scheduler.py` 상단, `MAX_STALE_RETRIES` 옆)
```python
STALE_FORCE_RETRY_AFTER_SECS = 300      # 영구 stale 의심 종목 최소 재시도 간격 (5분)
STALE_FORCE_RETRY_HOURLY_CAP = 12       # 시간당 동일 종목 최대 재시도 횟수 (LMS 위험 차단)
```

### 신규 인스턴스 필드 (`__init__`)
```python
# 사이클 29 — 영구 stale 시간 기반 강제 재시도 (시간당 cap 추적)
# 60분 슬라이딩 윈도우. _reset_daily_state 시 동행 clear.
self._stale_force_retry_history: dict[str, list[datetime]] = {}
```

### `_reset_daily_state` 동행 clear
```python
self._stale_force_retry_history.clear()
```

---

## 3. 안전 가드 (반드시 보존)

| 가드 항목 | 보존 사유 |
|-----------|----------|
| `[stale_watcher]` / `[stale_watcher_detail]` 로그 포맷 | 사이클 28 호환, Grafana/Loki 쿼리 영향 차단 |
| `STALE_FRESHNESS_SECS=60s` / 120s 주기 | 변경 시 회귀 위험 (사이클 17 안정화 완료) |
| 종목별 `await asyncio.sleep(0.05)` Rate Limit | KIS 권고 50ms 간격 유지 |
| 5분 cooldown 은 **종목 단위** (전체 cooldown 아님) | 일부 종목 정상화 / 일부 영구 stale 케이스 양립 |
| `bypass_limit=True` + `priority='HIGH'` | 메인 세션 강제 재등록 패턴 (사이클 17) |
| `r ≤ MAX_STALE_RETRIES` 분기 기존 동작 | 1~5회 첫 강제 재등록 로직 변경 금지 |
| `_stale_last_resubscribe_at` 갱신 위치 | 강제 재등록 직후 (사이클 28 진단 출처) |
| 모두 fresh 회복 시 `_stale_retry_count.clear()` + `_stale_last_resubscribe_at.clear()` | 사이클 28 G5 cleanup 동행 |

---

## 4. 회귀 가드

- 기존 73 회귀 케이스 전부 보존 (`test_stale_watcher_thresholds` 포함)
- `r ≤ MAX_STALE_RETRIES` 분기는 **기존 동작 그대로** (변경 없음)
- `r > MAX_STALE_RETRIES` 분기만 시간 기반으로 변경

---

## 5. 진행 방식 (TDD-First 필수)

### Phase 1 — tdd-engineer (Red)

신규 테스트 5+ 케이스 (`tests/test_scheduler_stale_force_retry.py` 또는 기존 stale watcher 테스트 파일 확장):

1. **상수 노출 검증**: `STALE_FORCE_RETRY_AFTER_SECS == 300`, `STALE_FORCE_RETRY_HOURLY_CAP == 12`
2. **r=6 + last_resub_age >= 300s** → 강제 재시도 호출됨 + `_stale_retry_count[ticker] == 0` 리셋
3. **r=6 + last_resub_age < 300s** → skip (기존 동작 보존), 카운터 그대로
4. **r=6 + `_stale_last_resubscribe_at` 부재** → 즉시 1회 시도 (영구 stale 의심 첫 진입)
5. **`[stale_force_retry]` 로그 포맷 검증** — prefix + ticker/retries/last_resub_age 필드
6. **시간당 cap 12회 검증** — 60분 슬라이딩 윈도우 내 13번째 시도는 skip + `[stale_force_retry_cap]` WARNING
7. **`_reset_daily_state` 동행 clear** — `_stale_force_retry_history` 도 비워짐
8. **r ≤ 5 분기 기존 동작 회귀** — r=1~5 시 즉시 강제 재등록 (사이클 17 보존)

freezegun 시간 조작 + `kis_ws_pool.subscribe` mock 패턴은 기존 stale watcher 테스트와 동일.

### Phase 2 — backend-dev (Green)

- `src/engine/scheduler.py::_check_and_resubscribe_stale` 분기 수정 (line 2695-2699 영역)
- 상수 2개 추가 (`MAX_STALE_RETRIES` 옆, line 88 근처)
- 인스턴스 필드 `_stale_force_retry_history` 추가 (line 195 영역)
- `_reset_daily_state` 동행 clear 추가 (line 3325 영역)
- 60분 슬라이딩 윈도우: 새 시도 등록 전 `datetime.now(_KST_TZ) - timedelta(hours=1)` 이전 항목 제거

### Phase 3 — tester (검증)

- 신규 단위 테스트 전체 PASS
- 기존 73 회귀 케이스 전부 PASS (`pytest tests/test_scheduler*.py -q`)
- 운영 시나리오 시뮬레이션:
  ```
  t=13:21:41 — 22개 종목 r=5 강제 재등록 (사이클 28 정상 동작)
  t=13:23:43 — _stale_watcher_loop 발화, 모두 r=6, last_resub_age=122s → 5분 미경과, skip 22건 (기존 동작)
  t=13:26:43 — _stale_watcher_loop, r=7, age=302s ≥ 300s → 강제 재시도 22건 + 카운터 0 리셋
  t=13:27:43 — 시세 회복 → 모두 fresh → _stale_retry_count.clear() + _stale_last_resubscribe_at.clear()
  ```

---

## 6. 산출물 요구

- 변경 파일 diff 요약
- 신규/회귀 테스트 결과
- 운영 시나리오 시뮬레이션 (위 13:30~13:35 가정)
- 후속 안전 가드 검토 (LMS 위험 잔존 여부, 시간당 12회 cap 적정성)

---

## 7. 후속 검토 (사이클 30+ 후보)

- **시간당 cap 12회의 적정성**: 운영 1주 후 `[stale_force_retry_cap]` 발화 빈도 모니터링 → 필요시 8회로 강화
- **5분 cooldown 의 적정성**: 영구 stale 종목 회복 시간 분포 분석 후 3분/7분 조정 검토
- **세션 단위 force_reconnect 와의 race**: 사이클 24 `_force_reconnect_session` 발화 직후 종목별 force_retry 가 중복될 수 있음 — 세션 reconnect 직후 60s 종목별 force_retry 유예 가드 검토
- **보유 종목 우선 force_retry**: 시간당 cap 도달해도 보유 종목은 cap 우회 검토 (매매 안전성 우선)

---

## 8. 커밋 정책

- **커밋 금지** — 사용자 명시 지시 대기
- 커밋 메시지 한글 컨벤션 준수
