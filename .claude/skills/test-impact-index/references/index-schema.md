# Test Index Schema — 상세 명세

## 최상위 구조

```yaml
version: 1                       # 정수, 호환성 갱신 시 +1
generated_at: ISO8601            # KST 시각
backend: { ... }                 # path → entry
frontend: { ... }                # path → entry
overrides_applied: [path, ...]   # manual_overrides.yaml에서 병합된 항목
stats:
  backend_modules: int
  backend_tests: int
  frontend_modules: int
  frontend_tests: int
  unmapped_modules: [path, ...]  # 어떤 테스트도 없는 모듈 — 커버리지 갭 알림용
```

## entry 구조

```yaml
direct_tests: [path, ...]      # 이 모듈을 직접 import하는 테스트
transitive_tests: [path, ...]  # 이 모듈에 의존하는 다른 모듈을 import하는 테스트
domain_tags: [string, ...]     # 옵션. external-io / time-sensitive / single-worker / mock-required
last_modified: ISO8601         # git log 기반 (인덱스 비교용)
```

`direct_tests`는 정확하지만 좁고, `transitive_tests`는 넓지만 노이즈가 있을 수 있다. PR CI에서는 합집합을 실행하고, 로컬에서는 direct만 빠르게 돌릴 수 있게 두 필드를 분리한다.

## domain_tags 표준 어휘

| 태그 | 의미 |
|------|------|
| `external-io` | KIS REST/WebSocket 또는 Supabase에 닿는 모듈 — 모킹 정확도가 회귀 위험 |
| `time-sensitive` | 시간 분기 포함 — `freeze_time`으로 검증 필수 |
| `single-worker` | 다중 워커 시 동시성 결함 발생 가능 |
| `mock-required` | 단위 테스트에서 fake 주입 없이는 실행 불가 |
| `safety-critical` | 매매 안전성 직접 영향 — manual_overrides에서 항상 트랜지티브 포함 |

## manual_overrides.yaml 형식

키는 변경 파일 경로 또는 glob, 값은 추가로 실행할 테스트 경로 또는 glob.

```yaml
"<changed-file-path-or-glob>":
  - "<test-path-or-glob>"
  - "<test-path-or-glob>"
```

## 인덱스 빌드 알고리즘 (의사코드)

```python
def build_backend_index():
    src_files = glob("src/**/*.py")
    test_files = glob("tests/**/test_*.py") + glob("tests/**/*_test.py")

    # 1. 각 파일의 import 추출
    imports = {f: parse_imports(f) for f in src_files + test_files}

    # 2. 모듈 의존성 그래프 (src → src)
    src_graph = {f: [s for s in imports[f] if s in src_files] for f in src_files}

    # 3. 직접 테스트 매핑 (test → src 역방향)
    direct = {f: [] for f in src_files}
    for t in test_files:
        for imported in imports[t]:
            if imported in src_files:
                direct[imported].append(t)

    # 4. transitive: BFS로 src 그래프를 거꾸로 타고 직접 테스트 모음
    transitive = {}
    for f in src_files:
        deps = reverse_bfs(src_graph, f)  # f를 import하는 모든 src
        tests = set()
        for d in deps:
            tests.update(direct[d])
        transitive[f] = sorted(tests - set(direct[f]))

    return {f: {"direct_tests": sorted(direct[f]),
                "transitive_tests": transitive[f]}
            for f in src_files}
```

## 인덱스 검증 (CI에서)

PR이 들어올 때 다음을 확인:
1. `_workspace/test_index.yaml`이 최신인지 — 코드 변경이 있는데 인덱스가 같으면 fail
2. `manual_overrides.yaml`의 키/값 경로가 실제로 존재하는지
3. `unmapped_modules` 목록이 새로 늘었는지 — 새 모듈에 테스트가 없다는 신호 (warning)

## 진화 로드맵

- v1: 정적 import 분석 + manual overrides
- v2 (선택): 백엔드에 `pytest --collect-only --json`을 끼워서 fixture 의존성까지 그래프에 포함
- v3 (선택): 커버리지 데이터 기반 동적 보강 (testmon 스타일)
