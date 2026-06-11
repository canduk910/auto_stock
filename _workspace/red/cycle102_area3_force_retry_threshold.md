# Cycle 102 Red 명세 — 영역 3: force_retry 임계 상향 (Q73=B)

**명세 출처**: `_workspace/cycle102_phase2_design.md` §영역 3 + `_workspace/cycle102_domain_consult.md` §A6
**위급도**: HIGH — 사이클 29 R1 패턴 답습 (영역 폐기 0, 임계만 상향)
**행위**: `STALE_FORCE_RETRY_AFTER_SECS` 5분(300s) → 10분(600s) + `STALE_FORCE_RETRY_HOURLY_CAP` 12회 → 6회 — KIS LMS chain 안전 마진 증가 (124~141건/일 → 50~70건/일 예상)

## 사용자 결정 (영속)

- **Q73=B**: 5분 → 10분 + 12회 → 6회 (사이클 29 R1 패턴 답습)
- **영역 폐기 0**: 영역 자체 영속 (사이클 29 005935 사고 패턴 영구 차단 의무)

## 결정적 발견 (domain-consult §A6 운영 실측)

- `[stale_force_retry]` 124~141건/일 = 사이클 29 R1 정상 영역이나 *과도 영역* (LMS chain 안전 마진 증가 의무)
- 임계 상향 후 예상: 50~70건/일 (~50% 감소) — 사이클 29 R1 폐기 0 + 영역 영속

## Production 시정 (Green 단계 backend-dev 인계)

### `src/engine/stale_diagnostics.py` (L26~L31)

```python
# 사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영
MAX_STALE_RETRIES = 5                       # 연속 N회 초과 stale 시 skip (영구 stale 의심). 6회 이상 → 다음 _scan_loop 위임.

# 사이클 29 (2026-05-21) — 영구 stale 무한 skip → 시간 기반 강제 재시도 전환
# 사이클 102 (2026-06-11) Q73=B — 임계 상향 (LMS chain 안전 마진 증가)
STALE_FORCE_RETRY_AFTER_SECS = 600          # 영구 stale 의심 종목 최소 재시도 간격 (10분, 사이클 29 5분 → 사이클 102 10분)
STALE_FORCE_RETRY_HOURLY_CAP = 6            # 시간당 동일 종목 최대 재시도 횟수 (사이클 29 12회 → 사이클 102 6회, LMS / 앱키 정지 위험 차단)
```

### `src/engine/stale_watcher_core.py` (L32~L33 + L193 + L210)

**변경 0** — 상수 정의처 단일 SoT (사이클 60 Phase 2-A1 영속). 사용 영역 L193 + L210 모두 영속 (상수 값만 변경 영역).

## Red 케이스 5 (HIGH 3 + MEDIUM 2)

| 가드 | 위급도 | 파일 | 영역 |
|------|------|------|------|
| **G-THRESHOLD1** | HIGH | `tests/unit/engine/test_cycle102_force_retry_threshold.py` | `STALE_FORCE_RETRY_AFTER_SECS == 600` 영속 (사이클 102 Q73=B 상향 확정) |
| **G-THRESHOLD2** | HIGH | `tests/unit/engine/test_cycle102_force_retry_threshold.py` | `STALE_FORCE_RETRY_HOURLY_CAP == 6` 영속 (사이클 102 Q73=B 상향 확정) |
| **G-THRESHOLD3** | HIGH | `tests/unit/engine/test_cycle102_force_retry_threshold.py` | 구 값 영구 부재 AST (`= 300` / `= 12` 잔존 0건, 사이클 88 G-REJECT 답습 영구 차단) |
| **G-LMS1** | MEDIUM | `tests/unit/engine/test_cycle102_force_retry_threshold.py` | 9분 미경과 시 force_retry skip + 11분 경과 시 force_retry 발화 정합 (freezegun, 사이클 29 R1 패턴 답습) |
| **G-PERSIST1** | MEDIUM | `tests/unit/engine/test_cycle102_force_retry_threshold.py` | 60분 윈도우 내 6회 force_retry 후 7회째 cap 차단 + 사이클 29 R1/R2/R3 영속 (변경 0) |

## Red 검증 명령

```bash
python -m pytest -x tests/unit/engine/test_cycle102_force_retry_threshold.py -v
# Red 단계 = production 영역 상수 미시정 (300 / 12) → G-THRESHOLD1~3 + G-LMS1 + G-PERSIST1 모두 FAIL 영역
# Green 단계 backend-dev 1줄 시정 후 5 PASS 영역 전환
```

## 영속 의무 매트릭스 (HIGH)

- **사이클 29 R1 영속 (영역 폐기 0)**: 시간 기반 force_retry 영역 영속, 임계만 상향
- **사이클 29 R2 silent_inactive 세션 단위 3중 가드 영속**: 영역 3 영향 0
- **사이클 29 R3 HIGH/LOW 우선순위 분리 영속**: 영역 3 영향 0 (별도 분기)
- **사이클 66 cap=10 priority 분리 영속**: 영역 3 영향 0 (별도 분기)
- **사이클 67 stale_manager 4 sub-module 영속**: `stale_diagnostics.py` L30~L31 상수 영역만 변경 (행위 영역 0)
- **사이클 17 OPSP0002 backoff 300s 영속**: 영역 3과 분리 (별도 분기)
- 4중 안전망 영속 (F1 + scan_loop + K + priority)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## Green 인계 (backend-dev)

- `src/engine/stale_diagnostics.py` L30~L31 **2 줄 시정만** (`300` → `600` + `12` → `6`)
- 주석 갱신 (사이클 102 명시) 동행

## Refactor

- 영역 3 = 단일 상수 시정 영역 (refactor 영역 외)
- 영향 인덱스 갱신: `python tools/test_impact/build_index.py`
