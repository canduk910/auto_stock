# 사이클 138 — AST DRY 3차 마이그레이션 (10 파일)

- **카드**: 사이클 130 권고 카드 #25 LOW (-1,500L 추정)
- **차수**: 3차 (사이클 136 = 7파일 / 137 = 10파일 / 138 = 10파일 / 139 잔존 ~12파일 후 종결)
- **위험**: LOW (테스트 영역 한정, production 영향 0)

## 우선순위 10 파일 (read 패턴 빈도 + 효과 기준)

1. test_cycle92_g_reject_persistence.py (9 read)
2. test_external_llm_reject_patterns.py (7 read)
3. test_cycle112_security_ast.py (5 read / 3 parse)
4. test_cycle89_g_reject_persistence.py (4 read)
5. test_cycle103_ast_no_dead_strategy_funcs.py (4 read)
6. test_cycle115_krx_endpoint_urls.py (4 read)
7. test_cycle76_ast_api_retry_helper.py (3 read / 1 parse)
8. test_cycle115_krx_no_plaintext_key.py (3 read / 2 parse)
9. test_cycle103_ast_momentum_log_format.py (3 read)
10. test_cycle98_ast_chk_citation_required.py (1 read / 1 parse)

## Red 가드 영역

- G-138-A1: 10 파일 영역 헬퍼 import 영속 (`from tests.unit.ast._ast_helpers import`)
- G-138-B1: 헬퍼 모듈 ≤ 250L 영속 (사이클 137 한도 답습)
- G-138-B2: __all__ ≥ 8 영속 (사이클 137 baseline)

## 신규 헬퍼 (필요 시)

기존 8 함수로 충분 — 신규 헬퍼 불필요 (read_module_source / has_function_def / count_function_calls / count_function_calls_in_node / find_function_def / find_constant_value / count_string_occurrences / count_imports_from).

## 행위 보존

- 사이클 38 명문화 (테스트 영역 한정)
- 사이클 67 facade re-export 패턴
- 사이클 89 G-AST1 의미 전환 영속
- 사이클 84/124/127/129/131/135 화이트리스트 영속
