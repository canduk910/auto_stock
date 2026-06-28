# Red 메모 — 사이클 181 (base-1, HIGH) 토큰만료 분기 substring → msg_cd 화이트리스트 전환

> **Red 단계 산출물.** production 코드 변경 0. backend-dev 가 Green 구현.
> 설계 정본: `_workspace/domain_consult/cycle181_token_expiry_whitelist.md` (domain-expert 2차 패스 확정).

## 결함 (현재 코드, `src/api/base.py`)

| 사이트 | 라인 | 조건 (현행) |
|--------|------|-------------|
| `_request` (메인) | L560 | `if "token" in msg1.lower() or "만료" in msg1:` → `await token_manager.issue()` + `if attempt < MAX_RETRIES: continue` |
| `_request_via_quote_pool` (시세 풀) | L866 | 동일 복제 → `await manager.issue()` + continue |

**오발화 뿌리** = `"만료" in msg1`. KIS `EGW00120` = msg1 "기간이 만료된 code 입니다" (→ "만료" 포함) = 본 프로젝트 예수금부족 변형 (`balance.py:99` `is_insufficient_cash` 화이트리스트 `{APBK0919, EGW00120}`). 매수 예수금부족 거부 → 토큰 분기 True → 불필요 `issue()` 재발급 (전역 직렬 락 `_ISSUE_GAP_SECS=61.0` × N) + 동일 매수 body 재전송 (중복 체결 race).

## 확정 시정 설계 (Green 목표 — 테스트가 가정하는 동작)

base.py 모듈-레벨 frozenset:
```python
_TOKEN_EXPIRED_MSG_CODES = frozenset({"EGW00121", "EGW00122", "EGW00123"})  # access token 3종
# 배제 frozenset (이름은 Green 재량 — 테스트는 *동작* 으로 검증, 이름에 결합 안 함)
#   {"EGW00120", "APBK0919", "APBK0918"}
```
조건 (양 사이트 동일):
```python
is_token_expired = (
    msg_cd.upper() in _TOKEN_EXPIRED_MSG_CODES
    or ("token" in msg1.lower()
        and msg_cd.upper() not in _TOKEN_BRANCH_EXCLUDE_CODES
        and "부족" not in msg1)
)
```
`"만료" in msg1` 절 영구 폐기. 토큰 분기 본질 (`issue()` + `continue` 재시도 + 최종 `[api_retry_exhausted] last_status=token_expired` ERROR = 사이클 76 R7) 은 진짜 토큰만료에서 보존.

## 의제 → 가드 매핑 + 현재 FAIL 근거

### 행위 가드 (`tests/unit/api/test_cycle181_token_expiry_whitelist.py`)

| 가드 | 입력 (msg_cd / msg1) | 기대 동작 | 현재 코드 | RED? |
|------|---------------------|----------|----------|------|
| **FP-1** (핵심) | EGW00120 / "기간이 만료된 code 입니다" (지속) | 토큰 분기 미진입 → `issue` 0회 + 단일 HTTP 호출 + KisApiError | "만료" 매칭 → 분기 진입 → issue 3회 + HTTP 3회 | **FAIL** ✓ |
| **FP-2** (핵심) | IGW00001(비-화이트/비-배제) / "청약기간이 만료되었습니다" | issue 0회 + 단일 호출 | "만료" 매칭 → 진입 → issue ≥1 | **FAIL** ✓ |
| FP-3a/b (회귀) | APBK1943 / "시장가호가불가" · APBK0918 / "장운영시간 외" | issue 0회 (token/만료 미포함) | 미진입 (이미 0) | PASS-PASS |
| TP-1 (회귀) | EGW00123 / "기간이 만료된 token" → 재시도서 rt_cd=0 | 진입 → issue ≥1 → 최종 성공 | 진입(token/만료) → 성공 | PASS-PASS |
| **TP-1b** (화이트리스트 load-bearing) | EGW00121 / "유효하지 않은 접근" (영문 token·만료 *없음*) → 재시도 rt_cd=0 | msg_cd 단독으로 진입 → issue ≥1 → 성공 | 미진입 (키워드 없음) → 즉시 raise, issue 0 | **FAIL** ✓ |
| TP-2 (회귀) | "" / "invalid token detected" → 재시도 rt_cd=0 | "token" 폴백 진입 → issue ≥1 → 성공 | 진입(token) → 성공 | PASS-PASS |
| **TP-2 배제** (핵심) | EGW00120 / "token 기간이 만료된 code" (token 우연 포함, 지속) | 배제코드 → 폴백 미진입 → issue 0회 | "token" 매칭 → 진입 → issue ≥1 | **FAIL** ✓ |
| EXHAUST (회귀, 76 R7) | EGW00123 / "기간이 만료된 token" (3회 지속) | issue 호출 + `[api_retry_exhausted] last_status=token_expired` 1행 + `retry_exhausted==1` + raise | 동일 | PASS-PASS |
| **POOL-FP-1** (핵심) | (시세 풀, no-secondary fallback) EGW00120 / "기간이 만료된 code" 지속 | `manager.issue` 0회 + 단일 호출 + KisApiError | "만료" 진입 → issue 호출 | **FAIL** ✓ |
| POOL-TP-1 (회귀) | (시세 풀) EGW00123 / "기간이 만료된 token" → rt_cd=0 | 진입 → issue ≥1 → 성공 | 진입 → 성공 | PASS-PASS |
| **POOL-배제** (핵심) | (시세 풀) EGW00120 / "token ... code" 지속 | 배제 → issue 0회 | "token" 진입 → issue 호출 | **FAIL** ✓ |

> POOL 테스트는 보조 계좌 0개 → `_select_quote_label() == None` → 메인 fallback → `manager is token_manager` 경로로 동작시켜 `token_manager.issue` mock 의 call_count 를 검증한다 (사이클 7-C A-1 패턴 답습).

### 정적 가드 (`tests/unit/ast/test_cycle181_token_whitelist_ast.py`)

| 가드 | 검증 | 현재 코드 | RED? |
|------|------|----------|------|
| AST-1 | `from src.api.base import _TOKEN_EXPIRED_MSG_CODES` + `{EGW00121, EGW00122, EGW00123} ⊆` (frozenset 엔트리 검사) | 심볼 부재 → ImportError | **FAIL(error)** ✓ |
| AST-2 | EGW00120 / EGW00124 / EGW00125 / EGW00126 **∉** `_TOKEN_EXPIRED_MSG_CODES` | 심볼 부재 → ImportError | **FAIL(error)** ✓ |
| AST-3 | base.py AST 에 `Compare(left=Const("만료"), op=In)` 0건 (토큰 분기 `"만료" in msg1` 폐기. 주석/문서 false-positive 회피 = AST 노드 검사, 사이클 167/179 패턴) | L560 + L866 2건 잔존 | **FAIL** ✓ |

frozenset 엔트리 검사 = **실 객체 멤버십** (source 텍스트 스캔 아님). `"만료"` 잔존 검사 = **AST Compare 노드** (주석의 "윈도우 만료"/"토큰 만료 감지" 등 텍스트 false-positive 차단 — 사이클 167 교훈).

## 사이클 76 충돌 점검 (결론: 충돌 0)

- `test_cycle76_error_preservation_matrix.py::test_g_err3` = `assert '"token" in msg1.lower()' in source or 'in msg1.lower()' in source`. Green 후에도 hybrid 폴백에 `"token" in msg1.lower()` 잔존 → **PASS 유지**.
- `test_base_retry_logging.py::test_when_token_expired_persists_then_exhausted_counted` = EGW00123 / "token expired" → Green 후 화이트리스트 진입 → issue + exhausted → **PASS 유지**.
- R7 `[api_retry_exhausted] last_status=token_expired` 사이트 = 진짜 토큰만료 (화이트리스트/폴백 진입) 경로에 보존. 본 사이클 EXHAUST 가드가 이를 재확인.
- **단, "만료" substring 폐기로 잠재 의미전환 가능 영역**: `test_g_err3` docstring 이 "`token`/`만료` 키워드"를 언급하나 *단언* 은 `in msg1.lower()` 만 검사 → 코드 단언 영향 0. 의미전환 불요. (만약 backend-dev/tester 가 G-ERR3 docstring 을 "token 단독"으로 정정하려면 사이클 66 K-2 의미전환 절차 — 본 Red 는 손대지 않음.)

## 매매 안전성

`_request` 경로 = 매수 거부 (TTTC0012U) hot path 직결이나, 본 사이클은 **테스트만** 추가 (production diff 0). Green 시정의 안전 이득 (예수금부족 race 중복체결 제거 + 인증 체인 그리드락 해소) 은 자문 의제 3·4 참조.

## 실행 결과 (Red 확인)

```
pytest tests/unit/api/test_cycle181_token_expiry_whitelist.py tests/unit/ast/test_cycle181_token_whitelist_ast.py
```
→ 결과는 본 사이클 보고에 첨부 (핵심 FP/배제/AST 가드 FAIL, 회귀 PASS-PASS 가드 PASS).
