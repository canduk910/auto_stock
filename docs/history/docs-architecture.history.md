> 원본: `docs/architecture.md` · 이관: 2026-09-17

정본은 [`docs/architecture.md`](../architecture.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

절 제목은 **이관 시점의 정본 절 제목**이다. 이관하면서 제목 자체를 바꾼 절은 괄호로 구 제목을 적었다.

---

## 1. 전체 아키텍처

### 2026-09-17 이관 — TLS 부재(알려진 한계 L1) 시절의 인증 흐름 첫 줄

```
   | (1) http://<EC2>:80/…            ← 평문 HTTP (TLS 없음 = 알려진 한계 L1, 후속 F1)
```

→ CHANGELOG: cycle255(1단계) · cycle260/cycle267(2단계)

## 2. 백엔드 모듈 구조

### 2026-09-17 이관 — 시세 채널 리졸버 — cycle257→293→294 단계 서술

```
│   └── scanner.py           # 종목 스캔 + 공용 시세 캐시 + **시세 채널 리졸버**(cycle293 속성축 → **cycle294 시각축 합성**. `tick_tr_id_for(ticker, *, priority, now)` 가 프리장은 H0NXCNT0 · 정규장+애프터는 H0STCNT0 로 보내고 **정상 경로에서 통합을 반환하지 않는다**. 정본 집합 TICK_TR_IDS. 사이클 26 시각 분기는 cycle257 삭제)
```

→ CHANGELOG: cycle293 · cycle294

## 5. 일일 매매 스케줄 시퀀스

### 2026-09-17 이관 — 08:00 PRE_NXT — VB 도 프리장에서 매수한다는 서술

```
       │  VB + LTV PRE_NXT 매매 시작 (k_value_nxt_pre 적용)
```

→ CHANGELOG: 사이클 26 · 사이클 38

### 2026-09-17 이관 — 15:30 = 'NXT 애프터 전환' · VB/LTV 둘 다 POST_NXT 비활성 서술

```
15:30  KRX 메인 마감 → NXT 애프터 전환       (TIME_KRX_MAIN_CLOSE)
       │  _phase = "post_nxt_trading"
       │  _confirm_breakout_open_prices(board="post_nxt")  ← LTV 상한가 모드 보유 +
       │                                                      donchian 보유 시세 확정용
       │  구독 유지: VB/LTV 보유 종목 + donchian 보유 (positions HIGH 그룹)
       │  매수는 VB/LTV 둘 다 POST_NXT 비활성 — 손절 평가만 risk.on_tick 청산 분기로 작동
```

→ CHANGELOG: 사이클 26 · cycle287 · cycle294

### 2026-09-17 이관 — AI 자문이 19:50 블록에 적혀 있던 자리

```
19:50  NXT 애프터 신규 매수 중단              (TIME_NXT_POST_BUY_STOP)
       │  buy_disabled = True (모든 활성 전략)
       │  generate_recommendations()  (전략수정 AI자문)
       │  ├─ collect_metrics() ──────────────────→ DB trade_history 집계
       │  ├─ OpenAI Chat Completion ─────────────→ 외부 API
       │  └─ insert_recommendation() → DB parameter_recommendations (status: pending)
       │
20:00  NXT 애프터 종료, unsubscribe_all() ──→ WebSocket 구독 해제
       │                                       (TIME_NXT_POST_CLOSE)
```

→ CHANGELOG: Phase 0 (2026-05-15) · 사이클 101

## 9. DB 스키마

### 2026-09-17 이관 — Supabase → RDS 이전(M0~M6) 서술

```
> **DB 클라이언트 (Supabase→RDS 이전 M0~M6)**: 현재 정본 = AWS RDS PostgreSQL + `src/db/pg.py`(asyncpg 풀). 전 db 모듈이 `pg.fetch`/`pg.execute` 네이티브 async 경유. `src/db/supabase.py` 는 롤백용 병존(미사용). asyncpg 계약 = JSONB codec(raw dict) / TIMESTAMPTZ `to_char(+09:00)` 읽기 / DATE `_kst.to_date()` / NUMERIC→Decimal. 스키마(테이블 구조·마이그레이션)는 이전 전후 동일.
```

### 2026-09-17 이관 — stock_master_daily 적재 16:00 표기

```
| `stock_master_daily` | 033 | KIS FHKST03010100 일봉 정규화 — PK (ticker, bas_dd) + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (T-100 백필 → D-1 증분) |
```

→ CHANGELOG: cycle283 D2

### 2026-09-17 이관 — strategy_funnel_snapshots / stock_master_history 행의 변경 경위

```
| `strategy_funnel_snapshots` | 030 (+035) | 전략별 조건검색 단계별 후보/탈락 영구 추적 — UPSERT 전환 (사이클 145, snapshot_at 키 폐기) |
| `stock_master_history` | 032 (+036) | stock_master 갱신 이력 — PK (ticker, seq=0/1) + trigger 재설계 (사이클 150, 92K→4,358 row -96.9%) |
```

→ CHANGELOG: 사이클 145 · 사이클 150

## 12. 배포 환경 (AWS EC2)

### 2026-09-17 이관 — 무조건 `up --build` 였던 배포 도식

```
git push ───────────→ Actions trigger
                      ├─ appleboy/ssh-action
                      └──────────────────────────────→ SSH 접속
                                                       ├─ git pull origin main
                                                       ├─ docker compose build
                                                       └─ docker compose up -d
```

→ CHANGELOG: cycle114 · cycle248

### 2026-09-17 이관 — 구 CI/CD 파이프라인 블록

````
.github/workflows/deploy.yml
─────────────────────────────
트리거: push to main (*.md, docs/**, _workspace/** 제외)

jobs:
  deploy:
    ├─ SSH 접속 (appleboy/ssh-action)
    ├─ cd ~/auto_stock
    ├─ git pull origin main
    ├─ docker compose -f docker-compose.prod.yml up --build -d --remove-orphans
    └─ docker image prune -f
```

GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
````

→ CHANGELOG: cycle114 · 사이클 145 · cycle248

## 13. 확장 인프라 (구 제목: 13. 사이클 5~14 추가 인프라)

### 2026-09-17 이관 — 13장 제목·머리말이 사이클 범위였던 것

```
## 13. 사이클 5~14 추가 인프라 (2026-05-17 ~ 5/18)

본 절은 본문(1~12 섹션) 작성 이후 도입된 인프라를 요약. 상세는 `docs/HARNESS_CHANGELOG.md` 와 각 디렉토리 CLAUDE.md.
```

### 2026-09-17 이관 — 13.1 — kojiro 다크런치 · Phase 1/2 자금관리 표기

```
- 신규: `kojiro` (고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`. EMA 5/20/40 대순환 스테이지 + ATR/종가 밴드 1.0~4.5% → strict entry(스테이지1 + 6→1 인접 + 3선 우상향 + 종가>EMA5) → 09:05~09:30 시장가(갭업/갭다운/붕괴 스킵). 청산 = 고정%(-8%)→2ATR→스테이지3→2.5ATR 트레일. **멀티데이**. Phase1 = position_ratio, 터틀 유닛 sizing/피라미딩 = Phase 2. 지표 순수모듈 `kojiro_indicators.py`)
```

→ CHANGELOG: 사이클 R1 (2026-07)

### 2026-09-17 이관 — 13.1 — _MULTIDAY_STRATEGIES 리터럴 통합 경위

```
- **코드 정본 `_MULTIDAY_STRATEGIES = frozenset({donchian_swing, vcp_breakout, kojiro})`** — `is_next_day` 항상 False. 3 전략 모두 `strategy_base.py` 리터럴에 정적 선언 (2026-07 — vcp 동적 side-effect 추가 패턴을 리터럴로 통합)
```

→ CHANGELOG: 사이클 R1 (2026-07)

### 2026-09-17 이관 — 13.3 — 매수 가드 4모드가 실제로 매수를 막던 시절의 서술

```
### 13.3 시장 레짐 + 매수 가드 (4 모드)

- `src/engine/market_regime.py` — dkstock.cloud 매크로 fetch → `MarketRegime` dataclass (regime/vix/fear_greed/buffett/cash_min)
- 4 모드 매수 가드 (DB `buy_block_mode`): `OFF` / `WARN` (로그만) / `SOFT` (`execute_buy(soft_multiplier=0.5)` — 수량 절반 축소) / `HARD` (매수 skip)
- 4 임계 OR: `regime=defensive` (toggle) / `vix > vix_threshold` / `fear_greed_score > fg_high_threshold` / `< fg_low_threshold`
```

→ CHANGELOG: 사이클 8 · 사이클 I (2026-08-03) · 2026-08-07 자문 계층 정직화

### 2026-09-17 이관 — 13.6 — stale 임계 변천과 보조 세션 점진 활성화 기록

```
### 13.6 운영 안정성 (사이클 9 / 11 / 13 / 14)

- WebSocket stale watcher 임계 보수화 → 회복 강화:
  - `STALE_WATCHER_INTERVAL_SECS=120` / `STALE_FRESHNESS_SECS=60` / `MAX_STALE_RETRIES=5` (6회 이상 stale → 시간 기반 force_retry 경로 위임. 구 `STALE_FORCE_REREGISTER_AFTER` 는 2026-08-19 dead 상수로 제거)
  - 다중 안전망: F1 (재연결 1회) + `_scan_loop` (5분) + K watcher (120s) + `_resubscribe_stale_priority` (5분 우선) = 4중
- `_subscriptions` 정합성 가드 (in-flight ACK race 차단)
- `_report_tick_coverage()` 풀 통합 — 사이클 11 짝궁 누락 fix
- `list_accounts()` 60s TTL 메모리 캐시 — 폴링 race + supabase HTTP/2 stale connection 결함 차단
- 운영 점진 활성화: 보조 0개 → 1 → 5 (코드 배포 / 첫 등록 / 점진 추가). KRX 메인 시간 중 빈번한 push 자제 (재시작 race), NXT 애프터 또는 익일 boot 전 push 권장
```

→ CHANGELOG: 사이클 9 / 11 / 13 / 14 · cycle232 D6 · cycle283 D8

## 14. 운영 계약 (구 제목: 14. 사이클 26~165 추가 인프라)

### 2026-09-17 이관 — 14장 제목·머리말이 사이클 범위였던 것

```
## 14. 사이클 26~165 추가 인프라 (2026-05-20 ~ 6-19)

상세는 `docs/HARNESS_CHANGELOG.md` 와 각 디렉토리 CLAUDE.md. 본 절은 본문(1~13) 이후 도입된 핵심 사실 요약.
```

### 2026-09-17 이관 — 14.1 — VB/LTV 가 둘 다 main 단독이라는 서술

```
- 매매 정책 = KRX 메인 09:00~15:20 단독. VB/LTV `tradable_boards=("main",)` (PRE_NXT/POST_NXT 매수 비활성)
```

→ CHANGELOG: 사이클 26 · 사이클 38

### 2026-09-17 이관 — 14.1 — 시세 채널 cycle257→293→294 경위 문단

```
- 시세 채널 시간대별 6 구간 분기 + 사전 구독 마진(50초) 종목별 원자 전환은 **108일간 미배선으로 cycle257 에서 삭제**. **cycle293(2026-09-14)이 그 자리에 속성축 리졸버를 놓았고(2단계), cycle294 가 시각축을 합성해 통합 채널을 반환 경로에서 지웠다(3단계)** — `scanner.tick_tr_id_for(ticker, *, priority, now)` 가 프리장은 `H0NXCNT0`, 정규장+애프터는 `H0STCNT0` 를 돌려주고, 전환은 `tick_channel_clock.switch_windows()` 가 표에서 파생한 **창 안에서만** 일어난다(아침 1 + NXT 단독 연속 구간 경계 2). 판정 실패의 폴백도 전용 채널이다(L1=KRX / L2=프리 창 NXT / L3=`off` 만 통합). 킬스위치 `system_config.tick_channel_resolver_mode`(기본 `observe` = 행위 0) + 다이얼 5키. 종착지였던 통합 채널 폐기(2026-09-07 사용자 결정)는 **이 단계가 그 종착지다** — 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절
```

→ CHANGELOG: cycle252 · cycle257 · cycle293 · cycle294

### 2026-09-17 이관 — 14.2 — market_op_subscribe 사이클 사슬(214→221→230→292)

```
- `src/engine/market_op_subscribe.py` — **구독 배치**(cycle292 가 `scheduler._subscribe_market_operation_tickers` 본체를 leaf 로 추출, 행위 변경 0 · scheduler 에는 5줄 위임 wrapper). 현행 계약 = 대상은 **보유+익일청산뿐**(후보 VI 는 cycle221 F2 로 삭제 — 실질 noop 이던 경로) · 메인 세션 **0건**(cycle230 이 cycle214 의 `bypass_limit=True` 메인 직접 구독을 폐기 — 08-19 OPSP0008 사고) · 보조 세션 **직접** 라운드로빈 + `bypass_limit=False` · 실효 상한은 `MAX_SUBSCRIPTIONS`(41)이고 `cap`(기본 60) 은 cycle214 시그니처 잔재(vestigial)
```

→ CHANGELOG: cycle214 · cycle221 F2 · cycle230 · cycle292

### 2026-09-17 이관 — 14.3 — 용량 정합 사이클의 수치 기록

```
### 14.3 사이클 150 — SUPABASE 용량 정합

- migration 036 = stock_master_history PK (ticker, seq=0/1) + trigger 재설계 → 92K→4,358 row -96.9%
- `purge_old_rows()` T-150일 retention cron 매일 16:15 KST + protected_tickers 보호
- `_purge_by_cutoff` 2-step subquery — supabase-py DELETE chain `.limit()` 미지원 silent 24일 영구 차단
```

→ CHANGELOG: 사이클 150

### 2026-09-17 이관 — 14.4 — 절 제목 + 사고 서술

```
### 14.4 사이클 160 — `_wait_until` 본질 복원 (HIGH 매매 안전성)

- 2 모드 분기: default 즉시 break (run_daily phase 전환) + `advance_if_passed=True` (task_loop_helper 폭주 차단)
- 사이클 152 hotfix 가 깨뜨린 본질 복원 = 6/17 15:20 강제청산 누락 사고 (알테오젠/알지노믹스) 영속 차단
```

→ CHANGELOG: 사이클 152 · 사이클 160

### 2026-09-17 이관 — 14.5 — 사이클 147 패턴 답습 표기

```
- BUY trade_history.price = KIS CNTG_UNPR (체결단가) 강제 — 사이클 147 SELL fallback chain 패턴 답습
- UniqueViolation → 강제 UPDATE chain 영속
```

→ CHANGELOG: 사이클 147 · 사이클 161

### 2026-09-17 이관 — 14.7 — 절 제목 + 사이클 158 hook 부족 서술

```
### 14.7 사이클 163 — 2차 _boot stock_master race 가드 + 5 전략 prepare 재시도 hook

- `count_active()` polling 5분 cap (10초 주기) — 사이클 158 hook 90초 부족 영속 시정
```

→ CHANGELOG: 사이클 158 · 사이클 163

### 2026-09-17 이관 — 14.9 — 순수 작업 기록 + 14장 위임 메모

```
### 14.9 사이클 165 — docstring 보강 + CLAUDE.md 반복 단어 정리

- 6 파일 docstring 보강 (+96L) — TR_ID 분기 / msg_cd 누적 / KIS MCP 정본 fields 매핑 / 가드 계층 / 가드 매트릭스 인용
- 4 CLAUDE.md 반복 단어 30건 → 0건 정리 (의미 보존)
- 행위 변경 0 / 백엔드 풀 3,040 PASS

---

> 본 14장은 13장 이후 도입된 인프라의 요약. 14.1 (KRX ONLY 보드 전환) 영역 도식 갱신 + 14.6 (동시호가 시각 분기) 시퀀스 다이어그램은 별도 사이클로 위임.
```

→ CHANGELOG: 사이클 165

## 15. 프로세스 분리 로드맵

### 2026-09-17 이관 — "리포 안의 실재 최신 사이클은 cycle278" 시점 주석

```
> 1단계가 "진행 중"인 근거는 **사용자 결정(2026-09-11 — "1단계만 진행")** 이다. 사이클 번호
> `cycle279` 는 예약해 둔 것이고 명세·코드·changelog 항목은 아직 없다(리포 안의 실재 최신
> 사이클은 cycle278). 2·3단계는 승인된 설계가 아니라 방향 기록이다.
```

### 2026-09-17 이관 — 15.5.1 — "보류 표기는 지우지 않는다" 자기 편집 서술

```
**그래서 15.4 의 "보류" 표기는 지우지 않는다.** ①~④ 는 여전히 참이고, 4단계는 그중 셋에
답하는 설계안이다. 아래가 그 대조다.
```

### 2026-09-17 이관 — 15.5.1 — 앵커 밀림 정정 문단(문서 자기 편집 기록)

```
⚠️ 15.4 표의 파일:줄 앵커 중 둘은 그 뒤 사이클에서 **밀렸다**(실측 2026-09-15) —
`websocket_pool.py` 의 `_EXECUTION_NOTICE_TR_IDS` 는 `:59`→**`:64`**, `_enforce_main_only_execution_notice`
는 `:62`→**`:109`**(예외 `:57`), `order_engine.py` 의 A-ATOMIC 구간은 `:314`~`:355`→
**`:741`(`calc_buy_quantity`) ~ `:782`(`pending_buys.add`) ~ `:784`(`pending_buy_amounts`)** 다.
15.4 본문의 앵커는 이 사이클에서 현행 값으로 고쳤다. 제약 자체는 넷 다 그대로 살아 있다.
```

### 2026-09-17 이관 — 15.5.9 열린 질문 ① — 문서 구조를 어떻게 쓸까(문서 자기 편집 질문)

```
1. **문서 구조** — 15.4(3단계)를 "4단계 설계로 대체 검토 중" 으로 다시 쓸 것인가, 지금처럼
   병존시킬 것인가. 지금 문서만 읽으면 "3단계를 먼저 해야 4단계" 로 읽힐 여지가 있다.
```
