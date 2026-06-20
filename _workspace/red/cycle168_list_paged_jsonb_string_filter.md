# 사이클 168 — 종목마스터 UI 시총/거래대금 필터 0건 결함 시정 (작업 지시서)

## 사용자 보고
"종목마스터에서 필터링이 이름빼고는 작동을 안하네 확인해줘."

## 확정 진단 (메인 세션 + team-leader, Supabase MCP 운영 DB 실측)
운영 DB project_id = `etaligxesjtjfkbntdve`.

1. **근본 원인**: `stock_master.raw.hts_avls` / `raw.acml_tr_pbmn` / `raw.bfdy_clpr` 가 운영 DB 에 전부 **JSONB 문자열**로 저장됨.
   - 실측: hts_avls number=0 / string=3573, acml_tr_pbmn string=3441, bfdy_clpr string=3573.
   - 적재부 `src/api/condition.py` merge 가 KIS 응답 문자열("1503" 등)을 그대로 저장.
2. **결함 메커니즘**: `list_paged_by_filter` (L459-462) 가 `q.gte("raw->hts_avls", N)` / `q.gte("raw->acml_tr_pbmn", N)` 로 jsonb numeric 비교. PostgreSQL jsonb 정렬은 number > string → `"1503"(jsonb string) >= 1000(jsonb number)` 항상 false → **0건**.
   - 실측: `raw->'hts_avls' >= '1000'::jsonb` = 0 vs `hts_avls_eok >= 1000` = **1734**.
   - 실측: `raw->'acml_tr_pbmn' >= '10000000000'::jsonb` = 0 vs `acml_tr_pbmn_won >= 10000000000` = **366**.
3. **market / name 필터 정상**: `excg_dvsn_cd` `.eq()` (KOSPI 1796 / KOSDAQ 1777) + `ilike("name", ...)` 문자열 비교 → 무관.
4. **get_stats NOT 깨짐 (점검 완료)**: `with_hts_avls`/`with_acml_tr_pbmn`/`bfdy_clpr_present` 는 `raw->>` (text path) 의 non-null / `<> '0'` / `<> ''` *존재성* 체크일 뿐 numeric 비교가 아님 → string 에서도 정상 (실측 3566 / 3441 / 3566). **동행 시정 불필요.**
5. **매매(트레이딩) 무영향**: scanner `list_by_filter` 는 Python-side `int(str(value))` 파싱(사이클 108/166) → 후보 풀(1734) 정확. UI 읽기 경로 `list_paged_by_filter` 의 jsonb 비교만 깨짐.

## 사용자 결정 — Option A (생성 컬럼 + 인덱스)
migration 039 = `hts_avls_eok bigint GENERATED ... STORED` (억원) + `acml_tr_pbmn_won bigint GENERATED ... STORED` (원) + 2 인덱스. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL.
**운영 DB 즉시 적용 완료** (Supabase MCP `apply_migration`). 실측 재현: `hts_avls_eok>=1000`=1734, `acml_tr_pbmn_won>=10000000000`=366, hts NULL=0, acml NULL=132 (graceful 제외).

## 구현 명세
1. migration 039 — 작성 + 운영 DB 적용 완료 (team-leader 선반영). deploy.yml psql 자동 적용(사이클 145) 정합.
2. `src/db/stock_master.py::list_paged_by_filter`:
   - L459-462: `.gte("raw->hts_avls", hts_avls_threshold)` → `.gte("hts_avls_eok", hts_avls_threshold)`,
     `.gte("raw->acml_tr_pbmn", acml_tr_pbmn_threshold)` → `.gte("acml_tr_pbmn_won", acml_tr_pbmn_threshold)`.
   - 임계 환산 로직(L430-437) 유지: `hts_avls_eok`=억원이므로 `min_market_cap // 100_000_000` (ceil) 정합. `acml_tr_pbmn_won`=원이므로 `int(min_trade_amount)` 정합.
   - 주석 블록(L426-433 / L454-458) 갱신: jsonb string 타입 결함 + 생성 컬럼 전환 사유 명문화.
3. get_stats: 점검 완료 — 깨지지 않음 → 변경 0.

## 회귀 가드 (TDD Red→Green) — `tests/unit/db/test_cycle168_*.py` 신규
- G-168-COL-1: `min_market_cap>0` → `.gte("hts_avls_eok", threshold)` 호출 (mock query builder, col 정확 검증).
- G-168-COL-2: `min_trade_amount>0` → `.gte("acml_tr_pbmn_won", threshold)` 호출.
- G-168-THRESH-1: `min_market_cap=100_000_000_000`(1,000억) → 임계 1000 정합.
- G-168-THRESH-2: `min_market_cap=10_000_000_000_000`(10조) → 임계 100_000.
- G-168-THRESH-3: `min_trade_amount=10_000_000_000` → 임계 10_000_000_000 (원 그대로).
- G-168-EMPTY-1: 빈 필터 → hts_avls_eok / acml_tr_pbmn_won gte 미호출 (무필터 보존, T-1).
- G-168-AST-1 (HIGH): `src/db/stock_master.py` 본체 `list_paged_by_filter` 영역에 `raw->hts_avls` / `raw->acml_tr_pbmn` jsonb gte 잔존 **0건** (생성 컬럼 전환 영구 가드 — 미래 silent 결함 차단).

## 기존 테스트 영향 (의미 전환 점검 결과)
- `test_cycle128_list_paged_by_filter.py` G-LIST6/G-LIST7: 단언이 `"avls" in col` / `"acml_tr_pbmn" in str(c)` 관용 매칭 → `hts_avls_eok`("avls" 포함) / `acml_tr_pbmn_won`("acml_tr_pbmn" 포함) **여전히 PASS**. 변경 불필요.
- `test_cycle166_hts_avls_unit_correction.py` G-166-EOK-2 / CONSISTENCY: `if "hts_avls" in str(col)` 관용 매칭 + 임계값 1000/500/100000 불변 → **여전히 PASS**. 변경 불필요.
- → 의미 전환(사이클 66 K-2) 0건. 신규 가드만 추가.

## 매매 안전성 의무
- scanner `list_by_filter`(Python-side) / risk / order_engine / realtime / auth **변경 0** (UI 읽기 경로 한정).
- 사이클 81 G-AST1(raw JSONB 덮어쓰기 0) / 108 / 166 영속. 생성 컬럼은 raw 읽기만(GENERATED) → raw 변경 0.

## 문서 동기화
- `docs/HARNESS_CHANGELOG.md`(사이클 168 verbatim 행) + `CLAUDE.md`(이력 1줄 + DB 스키마 stock_master 절 생성 컬럼) + `src/db/CLAUDE.md`(list_paged_by_filter 절 + 사이클 128/166 정합) + `src/routes/CLAUDE.md`(GET /list min_market_cap/min_trade_amount 설명).

## 커밋 금지
구현·검증·문서까지만. git commit/push 금지 (사용자 명시 승인 후 메인 세션 처리).
