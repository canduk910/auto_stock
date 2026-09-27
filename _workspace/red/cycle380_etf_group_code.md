# cycle380 Red 명세 — ETF 판정을 이름 키워드에서 증권그룹코드로 (tdd-engineer)

작성 2026-09-27 · 사용자 결정 2026-09-27 「운영db 조회 허용 및 판정 변경 채택」(`scanner.py` 8영역 변경 승인 포함)
근거 = `_workspace/domain_consult/cycle378_etf_universe.md` §2.1·§2.2·§6.1 · 운영 DB 읽기 전용 조회(2026-09-27, 스크래치 `c378/q1_out.json`)

## 1. 한 줄

매수 후보에서 ETF 를 빼는 판정을 `stock_master.raw.scty_grp_id_cd ∈ {EF,EN,FE}` 로 바꾸고(코드가 없을 때만 기존 이름 규칙), SQL 에서 LIMIT **전에** 뺀다. 매수 후보 변화는 둘뿐이다 — 이름이 바뀐 ETF(KIWOOM·TIME·1Q…)가 빠지고, YG PLUS·BNK금융지주가 들어온다.

## 2. 헬퍼 — 신규 leaf `src/engine/etf_like.py`

- 표준 라이브러리만 import 한다. `src.db.stock_master` 가 같은 상수를 읽어야 해서 scanner(8영역·무거운 import)에 두지 않는다.
- `ETF_GROUP_CODES: frozenset[str] = frozenset({"EF", "EN", "FE"})`
- `ETF_KEYWORDS` = `scanner.py:494-497` 의 25개를 **순서까지 그대로** 옮긴다. scanner 는 leaf 에서 import 한다(이번 사이클에 키워드는 한 글자도 바꾸지 않는다).
- `is_etf_like(raw, name) -> bool`
  - `raw` 가 Mapping 이고 `raw.get("scty_grp_id_cd")` 가 None 이 아니며 `str(v).strip()` 가 비어 있지 않으면 → `str(v).strip().upper() in ETF_GROUP_CODES`. 이름은 보지 않는다.
  - 그 밖(raw None·dict 아님·키 없음·None·빈 문자열·공백) → `any(kw in (name or "") for kw in ETF_KEYWORDS)`. 대소문자 구분 부분일치로, 현행과 같다.
  - raw 를 바꾸지 않는다. 반환형은 `bool` 이다.

## 3. 호출 자리 (7곳, AST 가 정확히 이 7곳을 잡는다)

| 자리 | 바꿀 것 |
|---|---|
| `scanner.scan_stocks` :1257 (momentum) | `is_etf_like(None, name)`(또는 `item`). 원천(KIS 등락률 순위) 행에 코드가 없다. **결과는 이름 규칙과 같다** — 판정 자리만 하나로 모은다 |
| VB :457/:473 · LTV :525/:541 · donchian :702/:735 · BFB :727/:757 · VCP :963/:995 · kojiro :631/:656 | ① `list_by_filter(..., exclude_etf_like=True)` ② 루프 안 `if is_etf_like(row.get("raw"), name): continue`. `name` 을 구하는 식(`row["name"] or raw["prdt_abrv_name"]`)과 `isdigit` 규칙은 그대로 둔다 |

- 전략 파일은 `ETF_KEYWORDS` 를 import 도 하지 않는다(G2). `ticker_names` 는 지금처럼 scanner 에서 가져온다.
- **건드리지 않는 것**: `order_engine._observe_after_exit_etp`(8영역, 관측 전용 — G7 이 집합이 같은지만 본다) · `scanner._ALLOWED_PRODUCT_TYPE_CD`(KIS 폴백 적재) · RT/FS/DR/IF/MF 처리.

## 4. `stock_master.list_by_filter`

- keyword-only `exclude_etf_like: bool = False`. **기본값이면 SQL 이 지금과 같다**(`scty_grp_id_cd` 가 SQL 에 나오지 않는다). 전략 밖 호출자인 재무 적재 `scanner.py:3264` 와 `tools/validate_turtle_sizing.py:80` 는 무변경이다. 둘 다 지수 편입 필터라 ETF 가 원래 들어오지 않는다.
- True 면 `_build_sql` 이 만드는 **모든** 쿼리(단일 쿼리, stage 3쿼리)의 WHERE 에 판정을 넣는다. 위치는 `ORDER BY … LIMIT` 앞이다.
- SQL 판정은 헬퍼와 **행 단위로 같아야 한다**(PG 차등 테스트).
  - 코드: `UPPER(BTRIM(raw->>'scty_grp_id_cd', E' \t\r\n'))` 가 비어 있지 않으면 `= ANY(ETF_GROUP_CODES)`.
  - 폴백: SELECT 와 같은 COALESCE 이름(`COALESCE(NULLIF(name,''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'),''), '')`)이 `LIKE ANY('%kw%' …)`.
  - 상수는 leaf 에서 import 한다. `"EF"` 같은 코드나 키워드 문자열을 stock_master.py 에 다시 적지 않는다(G6).
- 참조 구현(스크래치에서 138/138 초록 확인):

```python
if exclude_etf_like:
    from src.engine.etf_like import ETF_GROUP_CODES, ETF_KEYWORDS
    grp = "UPPER(BTRIM(raw->>'scty_grp_id_cd', E' \\t\\r\\n'))"
    args.append(sorted(ETF_GROUP_CODES)); gi = len(args)
    args.append([f"%{k}%" for k in ETF_KEYWORDS]); ki = len(args)
    name_expr = "COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '')"
    clauses.append(f"NOT (CASE WHEN COALESCE({grp}, '') <> '' THEN {grp} = ANY(${gi}::text[]) "
                   f"ELSE {name_expr} LIKE ANY(${ki}::text[]) END)")
```

## 5. 테스트 (Red, HEAD d644ea68 기준)

| 파일 | 수 | HEAD |
|---|---|---|
| `tests/unit/engine/test_cycle380_etf_like_helper.py` | 97 | 전부 RED(leaf 부재) |
| `tests/unit/engine/strategies/test_cycle380_strategy_etf_exclusion.py` | 18(6전략×3) | 전부 RED(새는 ETF 3종 통과 · YG PLUS·BNK 탈락 · 인자 부재) |
| `tests/unit/db/test_cycle380_list_by_filter_etf_sql.py` | 6 | 4 RED · 2 초록(기본 SQL 무변경 보존 가드) |
| `tests/unit/ast/test_cycle380_ast_etf_like.py` | 12 | 전부 RED(G1 7곳 · G4 6곳 · leaf 부재) |
| `tests/integration/test_cycle380_list_by_filter_etf_pg.py` | 5 | 4 RED(TypeError) · 1 초록(기본값 현행 보존) |

## 6. 돌연변이 (참조 구현에 20건 → 20건 모두 잡힘)

M1 코드 upper 누락 · M2 strip 누락 · M3 코드가 있어도 이름이 막음 · M4 코드 무시(옛 규칙) · M5 집합에서 FE 누락 · M6 빈 코드를 결측으로 안 봄 · M7 폴백 없음 · M8 폴백 대소문자 무시 · M9 SQL 제외를 최종 쿼리에만 · M10 SQL 이름 폴백 누락 · M11 SQL 폴백이 COALESCE 대신 name 컬럼 · M12 SQL UPPER/TRIM 누락 · M13 기본값 True · M14 kojiro 인자 누락 · M15 VB 가 이름 규칙 유지 · M16 BFB 가 raw 대신 row 전달 · M17 scan_stocks 이름 규칙 복귀 · M18 order_engine 집합 표류 · M19 LTV isdigit 삭제 · M20 SQL 제외 없음(파이썬 후필터만)

## 7. Green 에게

- 8영역 `scanner.py` → `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 와 scanner 를 핀하는 모든 파일에서 **값만** 다시 핀하고, 사유(cycle380 사용자 승인 2026-09-27)를 적는다. 핀 목록은 참조 구현 전체 unit 실행 결과로 뽑아 반환 메시지에 적었다.
- 전략 파일은 8영역이 아니지만 핀이 걸려 있을 수 있다. 값만 다시 핀한다.
- 문서 정정은 `/sync-docs` 몫이다. 대상은 두 가지다.
  - 루트 CLAUDE.md 「종목코드 형식 비대칭」과 `00_leader_trading_rules.md:823` 은 「6자리 숫자 = ETF 차단」 이라고 적었다. 사실이 아니다.
  - `strategies/CLAUDE.md:143` 은 「ETF 키워드 제외는 호출자 책임」 이라고 적었다. 바뀐 판정에 맞게 고친다.
