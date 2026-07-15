# DB 마이그레이션 런북 — auto_stock → 신규 auto_trading (7GB 디스크 리셋)

> 상태: **대기 중** — 사용자가 도쿄(ap-northeast-1) 또는 서울(ap-northeast-2) region 으로
> auto_trading 을 재생성하고 프로젝트 ref 를 알려주면 즉시 실행.
> 뭄바이(ap-south-1) 프로젝트(upttiwaydjlvwwxadjhu)에는 **쓰지 않음** (region 부적합, 사용자 재생성 예정).

## 배경 (왜 마이그레이션인가)

- auto_stock(etaligxesjtjfkbntdve, 도쿄)의 **프로비저닝 디스크가 7GB로 자동확장**됨(수개월 churn/대형작업 누적).
- 실데이터는 **269MB**(전 테이블+인덱스) + WAL 384MB + 스토리지 0 = **실사용 ~650MB**.
- Supabase 디스크는 **데이터를 지워도 자동 축소 안 됨** → 데이터 감축으로는 7GB 못 줄임.
- **해결 = fresh 프로젝트로 이전**(10MB 디스크로 시작) → cycle 206 유니버스 한정 + retention 이 재증가 방지.

## 데이터 범위 (사용자 확정)

| 분류 | 테이블 | 처리 |
|---|---|---|
| **마이그레이션** | positions, trade_history, strategy_config, system_config, daily_performance, parameter_recommendations, kis_quote_accounts, pending_next_day_clear, market_regime_snapshots, backtest_runs, daily_log_reports, **stock_master** | MCP SELECT→INSERT |
| **재생성(스킵)** | stock_master_daily (KIS 폴백 + 16:00 daily load backfill), system_logs(로그), stock_master_history(재생성), strategy_funnel_snapshots(재생성) | 미이전 |

- stock_master_daily 재생성 = 월요일 prepare 시 KIS 폴백(cycle 173, 856종목×1콜≈43초, 기능정상) + 16:00 daily load 가 100일 backfill → 월요일 저녁 완전 복구. (사용자 (가) 재생성 선택.)

## 실행 절차 (신규 ref 확보 후)

### Phase 1 — 스키마 (40 마이그레이션)
- `apply_migration`/`list_migrations` 는 히스토리 테이블 초기화 연결 타임아웃 발생 → **execute_sql 로 DDL 직접 적용**(추적만 생략, 스키마 배치엔 무관).
- 4개 청크로 분할 적용. 청크 재생성:
  ```bash
  cd /Users/koscom/Projects/auto_stock
  T=/tmp/mig  # 또는 job tmp
  mkdir -p $T
  g(){ for n in "$@"; do cat supabase/migrations/${n}_*.sql; echo; done; }
  g 001 002 003 004 005 006 007 008 009 010 > $T/c1.sql
  g 011 012 013 014 015 016 017 018 019 020 > $T/c2.sql
  g 021 022 023 024 025 026 027 028 029 030 > $T/c3.sql
  g 031 032 033 034 035 036 037 038 039 040 > $T/c4.sql
  ```
- 각 청크를 Read → execute_sql. **주의: 007/030 등 `CREATE INDEX`(비 IF NOT EXISTS)는 재실행 시 에러 → execute_sql 은 청크당 1회만.** (007 파라미터 인덱스, 015 stock_master 인덱스는 IF NOT EXISTS 아님 → 최초 1회 성공이면 OK.)
- **대안**: 커밋 후 SUPABASE_DB_URL secret 을 신규로 바꾸고 deploy 트리거 → deploy.yml 이 psql 로 40 마이그레이션 자동 적용(cycle 145). 단 데이터가 먼저 있어야 하므로 이 경로는 스키마 전용.

### Phase 2 — 데이터 (MCP)
- stateful 11테이블: auto_stock 에서 `SELECT` → 신규에 `INSERT`. 대부분 소량(trade_history ~300, daily_performance ~322, parameter_recommendations ~233, backtest_runs ~435, 나머지 <20).
- stock_master ~3576행(raw+master_raw JSONB): 배치(~500행)로 SELECT→INSERT.
- **순서 주의**: strategy_config/positions/parameter_recommendations 는 008 마이그레이션이 momentum_breakout→long_tail_volatility UPDATE 하므로, 데이터 INSERT 는 스키마(008 포함) 적용 *후* = 이미 long_tail_volatility 로 저장돼 있어 무해.

### Phase 3 — Config 전환 (사용자 액션)
1. 신규 프로젝트 대시보드 → Settings/API 에서 확보:
   - Project URL (`https://<ref>.supabase.co`)
   - anon(publishable) key
   - DB connection string (Settings → Database)
2. EC2 `~/auto_stock/.env`: `SUPABASE_URL` / `SUPABASE_KEY` 교체.
3. GitHub Secret `SUPABASE_DB_URL` 교체(향후 마이그레이션 자동적용용).
4. 재배포(git push 또는 EC2 재시작) + 검증.
5. **타이밍**: 월요일 07:50 _boot 전(주말) 권장. 현재 positions=0 → 유실 위험 낮음.

### Phase 4 — 검증
- 신규 프로젝트: positions/strategy_config(VB weight 0.28 포함)/system_config(cash_usage_ratio 등)/stock_master 존재 확인.
- 앱 boot: 유니버스 로드(stock_master present), 매매 정상.
- `pg_database_size` = 신규는 소형(~80MB) 시작.
- 월요일 16:00 daily load 후 stock_master_daily 재구축 확인.

## 사용자에게 필요한 것
- **재생성한 auto_trading 의 project ref/id** (도쿄 또는 서울 region).
- (Config 전환 시) URL/anon key/DB URL — Phase 3.

## 진행 로그
- 2026-07-12: 도쿄 프로젝트(rilvnvmllcljcmzarwng) 스키마 적용 시도 중 사용자가 삭제 → 뭄바이(upttiwaydjlvwwxadjhu) 생성됨. region 부적합 → 사용자 재생성 대기. **뭄바이엔 미기록.**
- 2026-07-12: **신규 타겟 확정 = `auto-trading` (qqylpfzlbfxnkrrdcsxr, ap-northeast-2 서울)**. 스키마 40 마이그레이션 4청크 execute_sql 적용 완료(16테이블). 데이터 이전 완료:
  - config: strategy_config 6 / system_config 18 / kis_quote_accounts 4 (transcribe INSERT)
  - dblink(`aws-1-ap-northeast-1.pooler.supabase.com`, user=postgres.etaligxesjtjfkbntdve) pull: trade_history 317 / daily_performance 322 / market_regime_snapshots 2 / parameter_recommendations 253 / backtest_runs 435 / daily_log_reports 42 / **stock_master 3576**(생성컬럼 자동, history 트리거 자동 3576)
  - 재생성(미이전): stock_master_daily(16:00 daily load), system_logs, strategy_funnel_snapshots
  - dblink 확장 DROP 완료. 전 카운트 소스 일치.
- **남은 것 = Config cutover(사용자)**: 신규 URL/anon key로 EC2 .env 교체 + 재시작. ↓
  - URL: `https://qqylpfzlbfxnkrrdcsxr.supabase.co`
  - anon key(role=anon): `eyJ...aJYJDo1QwgNscx0IC7JDfLKEqoypkan3fxbs1z3mUkA`
  - auto_stock DB 비번 `wlgPdmsdn0910@` = 이전용, rotate 권장.
