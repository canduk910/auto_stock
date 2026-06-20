# 사이클 167 — 시총 헬퍼 3개 dead code 폐기 (LOW, 행위 보존)

## 배경
사이클 166 인계 "헬퍼 명칭 통일(_millions→_eok)" 진단 결과, 3 헬퍼가 production 호출
0건 = dead code 확인. 명칭 통일이 아니라 폐기가 합당 (사용자 결정 = dead code 폐기).

실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 직접 수행 (사이클 166 억원
정합 완료). 3 헬퍼는 사이클 129 도입 이후 줄곧 미사용.

## 폐기 대상 (callsite 0건 확정)
`src/engine/scanner.py` 3 함수:
- `market_cap_master_to_millions` — `get_market_cap_millions` / `validate_market_cap_consistency`
  내부에서만 호출 (둘 다 함께 폐기되므로 동반 제거)
- `validate_market_cap_consistency` — production 호출 0 (테스트 + AST 가드만)
- `get_market_cap_millions` — production 호출 0 (테스트 + AST 가드만)

세 함수가 서로만 호출하는 폐쇄 그래프, 외부 진입점 0.

## Red 가드 (사이클 103 strategy.py dead code 폐기 패턴 100% 답습 + 코드리뷰 보강)
`tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` (18 케이스, AST 기반):
- 탐지기 `_name_is_reintroduced` — 사이클 136 `_ast_helpers` (`has_function_def` /
  `count_function_calls`) 재사용. def / async def / 메서드 / 모듈-레벨 할당 / import 바인딩 /
  호출 사이트 어느 형태든 재도입 포착. 문자열 / docstring / 주석 언급은 무시.
- HIGH-1 (parametrize 3): 폐기 3 함수가 scanner.py 네임스페이스에 재도입 0건.
- HIGH-2 (보강): 보존 영역 영속 (`_is_master_blocked_for_entry` / `apply_master_block_filter` /
  `MIN_MARKET_CAP`) — AST 검증.
- 탐지기 self-test 14: catches 10 (def/async/메서드/단일·튜플 할당/import/import-as/호출/공백
  호출/어노테이션) + ignores 4 (docstring/주석/문자열 리터럴/무관).

> **/code-review max 보강 (사이클 167 후속)**: 초기 정규식(`^def name`)·부분문자열(`name(`)
> 방식의 false negative (별칭 재export `name = alias` / `from x import name`, 공백 def
> `def name (`) + false positive (scanner.py docstring 이 폐기 함수명 단순 언급 시 빌드 red)
> 동시 차단 위해 AST 기반으로 견고화. 효율 — scanner.py 1회 read 후 전 케이스 공유.

## 의미 전환 (사이클 66 K-2 패턴)
폐기로 "헬퍼 존재" 단언이 뒤집히는 전용 테스트:
- `test_cycle129_master_load_once.py` G-ML3 / G-ML4 / G-ML5 → `@pytest.mark.xfail`
- `test_cycle129_master_uri_priority.py` G-UP3 → `@pytest.mark.xfail`
- `test_cycle166_krx_fallback_eok_unit.py` `TestHelperUnitDocumentation` → 제거 (AST 가드로 이관)
- **docstring 동기화 (코드리뷰 보강)**: 위 2 파일의 모듈/함수 docstring 이 G-ML3~5 / G-UP3 를
  *활성 회귀 가드* 처럼 서술하던 드리프트 시정 — "[사이클 167 폐기 — xfail]" 마커 + 환산/임계
  명세를 *역사적 기록* 으로 명시 (사이클 166 형제 파일 정리 방식 정합).

## 매매 안전성
dead code 폐기 = 행위 영향 0. risk/order_engine/realtime/auth 변경 0. scanner 시총 필터
본체(list_by_filter/list_paged_by_filter, 사이클 166) 변경 0. 사이클 81 G-AST1 / 116 / 153 / 166 영속.

## 문서 시정
- `src/engine/CLAUDE.md` (3 헬퍼 설명 → 폐기 1줄)
- `src/db/CLAUDE.md` (get_market_cap_millions 호출자 영역 폐기)
- `src/api/CLAUDE.md` (환산식 헬퍼 → 폐기)
- CLAUDE.md 하네스 변경 이력 1줄 + docs/HARNESS_CHANGELOG.md verbatim 행
