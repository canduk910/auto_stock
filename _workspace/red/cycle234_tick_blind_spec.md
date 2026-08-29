# cycle234 — tick blind 계측 (G2 대체 조치 ①, 관측 전용)

> 근거: cycle232 자문 §3.5-γ "그때까지의 대체 조치" — *"`[boot]` 시각과 직전 종료 시각의
> 차이를 기록해 tick blind 총 시간/일을 집계하라. 이 숫자가 없으면 서버 스탑의 편익을
> 영원히 정량화할 수 없다."* 사용자 결정(08-29) = G2 보류 + 대체 조치 착수. D6 승격·
> 부팅 청산 우선순위 확인은 완료 — 본 사이클 = 잔여 ①(코드).
> **행위 변경 0** — 하트비트 기록 + 부팅 갭 로그 + 20:10 리포트 집계뿐. 8영역·scheduler diff 0.

## 설계

| # | 모듈 | 내용 |
|---|------|------|
| M1 | `src/engine/uptime_monitor.py` 신규 | ① `market_blind_overlap_secs(start, end)` 순수함수 — 다운 구간이 **평일 09:00~15:30 KST** 와 겹치는 초(멀티데이 지원, 주말 제외, **공휴일 미고려 근사** — docstring 명시: 과대계상 방향 = 보수, 편익 정량화에 안전) ② `record_heartbeat()` — `system_config.set_task_last_success("engine_alive_heartbeat", now_kst_iso())` graceful(사이클 193 마커 인프라 재사용 — 신규 테이블/키 체계 0) ③ `report_boot_blind_gap()` — 직전 하트비트 read → 부재 = `[tick_blind_boot] first_boot` INFO / 존재 = `[tick_blind_boot] downtime_secs=… market_blind_secs=… last_alive=…` (**market_blind_secs>0 → WARNING** — 장중 다운 = 손절 사각 실측, 그 외 INFO). 미래 마커(시계 역행)는 0 clamp. 직후 하트비트 1회 기록. **never-raise** ④ `heartbeat_loop(scheduler)` 60s 자기 종료 루프(`_running`, cycle233 watch_loop 동형 — cancel 불요) + `ensure_heartbeat_loop` idempotent 스폰 |
| M2 | `boot_manager.py` | cycle233 watcher 블록 옆 — `await report_boot_blind_gap()` + `ensure_heartbeat_loop(scheduler)` try/except graceful |
| M3 | `log_analysis_engine.py` | `_aggregate_tick_blind(logs) -> {boot_count, downtime_secs_total, market_blind_secs_total}` (`_aggregate_next_day_clear` 선례 — prefix 정규식) + metrics `"tick_blind"` 키 배선 → **일 단위 tick blind 총량**이 리포트에 영속(자문이 요구한 그 숫자) |

## 계측 의미 (판독법)

- 하트비트 60s = blind 계측 오차 상한 ≤60s. DB 부하 = system_config upsert 1,440회/일(미미).
- `downtime_secs` = 프로세스 부재 축만 — WS 재연결 blind 는 기존 fresh_ratio/stale watcher 계측 소관(중복 금지).
- **서버 스탑(G2) 재검토의 정량 근거** = `market_blind_secs_total` 의 주간 분포. 0 에 수렴하면
  서버 스탑의 편익도 0 에 수렴한다(자문 §3.5 표의 마지막 두 행만 커버하는 장치였으므로).

## Red 결정적 입력

- R1 overlap: 평일 장중 완전 포함(09:30→10:30=3600) / 야간 0 / 주말 0 / 경계(08:00→09:10=600) / 멀티데이(금 15:00 → 월 09:20 = 1800+1200).
- R2 report: 마커 존재 → downtime·market_blind 필드 로그 + 하트비트 재기록 / 부재 → first_boot / 미래 마커 → 0 clamp / 내부 예외 → 무전파.
- R3 loop: 반복 ≥2(while→if 뮤테이션 검출 — cycle233 F2 교훈) + `_running` False 즉시 종료 + ensure idempotent.
- R4 집계: `[tick_blind_boot] downtime_secs=125 market_blind_secs=60 …` 2행 → {boot_count 2, 합산 정확} / first_boot 행은 boot_count 만 / 무로그 0.
- R5 AST: scheduler.py 에 `uptime` 토큰 0(라인 상한 가드 보호) / 8영역 무참조 / boot 배선 존재 / heartbeat_loop 최상위 While.test 에 `_running`(구조 검사 — docstring 문자열 금지).
