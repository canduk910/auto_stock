# cycle270 Red 명세 — 보조 시세계정 토큰 강제 재발급이 만료 앵커를 못 옮기는 결함 (revoke → issue)

- 작성: tdd-engineer, 2026-09-10
- 상태: **Red 준비 완료** (테스트만 작성. `src/**` diff 0)
- 선행: cycle269 (`71b3bc2`, 09-09 배포) — 같은 결함의 1차 시도이며 **가설이 반증됐다**
- 병행 조사(정본): `_workspace/analysis/2026-09-10_cycle269_anchor_not_moved.md`
- ⚠️ **배포 선결 조건 있음 — §4.6 을 먼저 읽을 것**

---

## 1. 결함 사실

### 1.1 운영 실측 (메인 세션, 2026-09-10)

cycle269 는 매일 15:45 KST 에 보조 시세계정(주계정 제외) 전부에
`TokenManager.issue()` 를 강제 호출해 만료 앵커를 15:45 로 옮기려 했다. 09-10
라운드는 **7/7 성공**했다 (15:45:00~15:51:07):

```
[quote_token_refresh] label=ISA issued expired=2026-09-11 14:34:38
```

그런데 그 만료시각이 **같은 날 장중 자연 재발급이 남긴 값과 완전히 동일**했다:

```
14:34:38  토큰 발급 완료(label=ISA), 만료: 2026-09-11 14:34:38
```

7계좌 전부 같은 패턴 — fire 14:28:19 / gold 14:30:26 / 44606571 14:31:27 /
71513056 14:32:32 / 1004 14:33:35 / ISA 14:34:38 / RIA 14:50:22.

같은 날 병행 조사(`_workspace/analysis/2026-09-10_cycle269_anchor_not_moved.md`)가
09-09 첫 발화까지 확인해 **2일 × 7계정 = 14/14 앵커 무이동, 예외 0** 으로 못 박았다.
드리프트도 09-09→09-10 −9:18~−9:58 (7/7) 로 그대로 계속됐다.

즉 **강제 발급은 앵커를 한 번도 옮기지 못했고**, cycle269 는 배선은 정상인데
(카나리아·요약·계정별 행 전부 정상, 실패 0) **명세의 전제가 틀렸다**.

### 1.2 코드 근거 (원문 재확인)

| 사실 | 위치 |
|------|------|
| 만료는 **KIS 응답값 그대로** 대입 — 우리가 계산하지 않는다 | `src/auth/token.py:154-157` (`self.token_expired = datetime.strptime(data["access_token_token_expired"], ...)`) |
| ⇒ KIS `/oauth2/tokenP` 는 유효 토큰이 있으면 **같은 토큰·같은 만료**를 돌려준다 | 1.1 실측이 유일 증거 (KIS 문서 미확인 — **추정 아님, 관측 사실**로부터의 최소 설명) |
| 드리프트의 수학적 원인 = 만료 10분 전 선제 갱신 마진 | `src/auth/token.py:219-222` (`datetime.now() < self.token_expired - timedelta(minutes=10)`) |
| `revoke()` 는 **이미 존재**한다 (`POST /oauth2/revokeP`) | `src/auth/token.py:164-181` |
| 폐기 성공 시 `access_token=""` · `token_expired=None` · 캐시 파일 삭제 | `src/auth/token.py:178-180` |
| 토큰이 없으면 revoke 는 조용히 return | `src/auth/token.py:166-167` |

### 1.3 KIS 스펙 — 문서로는 확인되지 않는다

| 확인처 | 결과 |
|--------|------|
| KIS MCP `search_auth_api`(subcategory=인증) | `auth_token` / `auth_ws_token` **2건뿐**. `revokeP` 항목 자체가 없다 |
| `docs/kis/oauth.md:84~103` (revokeP) | 요청/응답 계약만. **폐기 직후 tokenP 가 새 토큰을 주는지 · 호출 한도 서술 없음** |
| `docs/kis/oauth.md:106~` (tokenP) | 요청/응답 예시만. **유효기간 내 재요청 시 동일 토큰 반환 규정 없음** |

⇒ "유효 토큰이 있으면 같은 것을 돌려준다" 는 **우리 실측으로만 확정된 사실**이고,
"폐기하면 새 것을 준다" 는 **아직 실측되지 않은 가정**이다. §4.6 을 반드시 읽을 것.

### 1.4 시정 방향

`revoke()` 로 **앵커를 비운 뒤** `issue()` 하면 KIS 는 새 토큰·새 만료(발급 시각
+24h)를 준다. `token.py` 는 **한 글자도 고치지 않는다**(기존 핀 `g269_6` +
신규 핀 `G-270-3` 이 잠근다).

---

## 2. 계약 (Red 로 잠근 것)

| # | 계약 | 잠근 테스트 |
|---|------|------------|
| C1 | 계정별 `revoke()` **먼저** → `issue()`. **계정 단위 페어**이지 "전부 revoke 뒤 전부 issue" 가 아니다 | `test_c1_revoke_precedes_issue_for_each_account` · `G-270-1` |
| C2 | 라운드 후 만료 앵커가 **재발급 시각 기준**으로 옮겨진다 (더블이 KIS 동일-토큰 의미론을 재현) | `test_c2_round_moves_expiry_anchor_to_refresh_time` (+ 더블 특성화 `test_c2b_issue_alone_cannot_move_anchor`) |
| C3 | `revoke()` 실패 시에도 그 계정에 `issue()` 를 **시도**한다(무토큰 방치 금지 = fail-open) + WARNING 이상으로 남긴다. 그 계정의 앵커는 안 옮겨지며 그 사실이 로그에 드러난다 | `test_c3_revoke_failure_still_attempts_issue` · `test_c3b_revoke_failure_is_logged_loudly` |
| C3-c | `issue()` 실패는 cycle269 c4 계약 그대로 계정 단위 흡수 + `failed` | `test_c3c_issue_failure_absorbed_per_account` |
| C4 | 주계정(`label=None`/빈 label)은 revoke 도 issue 도 하지 않는다 | `test_c4_main_account_never_revoked_or_issued` (+ cycle269 c3/c3b 유지) |
| C5 | 계정별 로그 = cycle269 접두 **byte 보존** + 끝에 ` revoked=<True\|False>` | `test_c5_per_account_log_appends_revoked_field` |
| C5-b | 회차 요약 3필드(`accounts/issued/failed`)와 반환 dict 키는 **불변** | `test_c5b_round_summary_contract_unchanged` · `test_c5c_summary_dict_keys_unchanged` |
| C6 | 61초 직렬화를 **우회하지 않는다** (leaf 자체 sleep·전역 시각 조작 0) | `G-270-4` |
| C7 | `get_token()` 금지 (캐시 hit 면 no-op → 앵커 못 옮김) | `test_c7_get_token_still_never_used` · cycle269 `c2`/`g269_4` |
| C8 | leaf 는 `src.auth.token` 에서 `get_token_manager` **하나만** 빌린다 (내부 심볼 0) | `G-270-2` |
| C9 | 15:45 KST · `immediate_first_run=False` 불변 | cycle269 `c8`/`c9` (무변경, 계속 GREEN) |

### 2.1 결정 — 회차 요약에 `revoked` 를 **넣지 않는다** (C5-b)

팀장 지시는 "필요하면 끝에 추가" 였다. 넣지 않기로 결정한 근거:

1. cycle269 의 `summary == {...}` **등식 단언 4건**(c1/c4/c5/c6)이 동시에 깨진다 —
   Red 범위를 넘는 의미 전환 4건이 사이클에 딸려 온다.
2. revoke 성패는 이미 **계정별 행**(` revoked=`)과 **WARNING**(C3)으로 전부 관측된다.
   `grep 'revoked=False' | wc -l` 한 줄이면 라운드 실패 계정 수가 나온다.
   요약에 넣어도 **새 정보가 없다**.

넣고 싶다면 위 4건의 의미 전환을 동반하는 **별도 사이클**이다. 이 결정 자체를
`test_c5b_round_summary_contract_unchanged` 가 잠갔다(Green 단계에서 임의로 4번째
키를 넣으면 형제 파일 4건이 붉어지기 전에 이 가드가 먼저 잡는다).

### 2.2 왜 "계정 단위 페어" 인가 (C1)

"전부 revoke → 전부 issue" 순서면 7계정이 **동시에** 무토큰이 되고 그 상태가 라운드
전체(≈7분) 지속된다. 계정 단위 페어는 무토큰 창을 **한 번에 한 계정 · ≤61초**로 묶는다.

---

## 3. Green 단계 — backend-dev 가 바꿀 정확한 지점

**대상 파일은 `src/engine/quote_token_refresh.py` 하나다.** `src/auth/token.py`,
`src/engine/scheduler.py`, 8영역, 전략 7파일 전부 diff 0.

| 지점 | 현재 | 해야 할 일 |
|------|------|-----------|
| `_emit_issued(label, expired)` — **L117~122** | `logger.info("%s label=%s issued expired=%s", MARKER, label, expired)` | 인자에 `revoked: bool` 추가 + 포맷을 `"%s label=%s issued expired=%s revoked=%s"` 로. **접두는 한 글자도 바꾸지 않는다** |
| `refresh_quote_tokens_once()` 루프 — **L162~172** | `manager = await get_token_manager(label)` → `await manager.issue()` → `summary["issued"] += 1` → `_emit_issued(...)` | 매니저 획득 뒤 **먼저** `await manager.revoke()` 를 **자체 try/except** 로 감싸 호출(성공/실패를 `revoked` 로 기록, 실패는 WARNING 이상 + MARKER 접두 + label 포함) → 이어서 기존 `issue()` 블록 그대로 → `_emit_issued(str(label), ..., revoked)` |
| 모듈 docstring — **L18~23 "어떻게 고치는가"** | "issue() 를 부르면 그 시각이 새 앵커" | 09-10 실측으로 반증된 사실 + `revoke()` 선행 이유 + 전환 날짜를 남긴다 (C7 docstring 의무) |

주의 3가지:

1. **revoke 실패를 `continue` 로 흡수하지 마라** — C3 가 RED 로 잡는다. 토큰 없는
   상태로 남기지 않는 쪽이 fail-open 방향이다.
2. **`failed` 카운터는 issue 실패 전용**이다 — revoke 실패는 `failed` 를 올리지 않는다
   (C3 가 `summary == {"accounts": 3, "issued": 3, "failed": 0}` 로 못 박았다).
3. **`asyncio` import 금지**(G-270-4) — 61초 gap 은 `issue()` 내부 전역 lock 하나가
   유일한 지점이다. leaf 에서 직접 sleep 하면 계약이 이원화되고 KIS 한도 위반은
   앱키 정지로 이어진다.

---

## 4. 위험

### 4.1 revoke~issue 사이 그 계정의 시세 REST — **401 이 아니라 지연**

`src/api/base.py:779` 의 `_request_via_quote_pool` 은 요청마다
`token = await manager.get_token()` 을 부른다. 폐기 직후라 `_is_valid()` 가 False 면
`get_token()` 이 **스스로 `issue()`** 를 부르고 같은 전역 lock 에서 순번을 기다린다
⇒ 인증 실패가 아니라 **최대 ~61초 대기**다. 그 자기 재발급도 앵커를 15:4x 로 잡으므로
설계 목적에 반하지 않는다(우리 `issue()` 는 그다음에 "유효 토큰 존재"를 만나 같은
만료를 돌려받을 뿐이다).

### 4.2 시간 예산 — 16:00 일봉 적재 전에 끝나는가

- 계정당 무토큰 창 ≈ `revoke`(HTTP 1회) + gap 대기 ≤61s.
- **revoke 는 61초 gap 을 소모하지 않는다**(§4.3) ⇒ 라운드 총 길이는 cycle269 와
  사실상 같다. 09-10 실측 라운드 = **15:45:00~15:51:07 (6분 7초)**.
- 7계정 × 61s ≈ 7분 ⇒ 종료 ≈ **15:52** < 16:00 일봉 적재. **여유 있다.**
- 15:45~15:52 는 KRX 마감 후이고 매매와 무관하다(보조 계정 = 시세 풀 전용).

### 4.3 61초 직렬화 — 코드로 확인한 것과 확인 못 한 것

- **확인됨(코드)**: `revoke()`(`token.py:164-181`)는 `_GLOBAL_ISSUE_LOCK` ·
  `_LAST_ISSUE_AT` · `_ISSUE_GAP_SECS` 어느 것도 참조하지 않는다. gap 을 소모하지도,
  우회하지도 않는다. gap 은 `issue()`(`token.py:132-141`)만 지킨다.
- **확인 불가(KIS 측)**: KIS MCP 인증 카테고리에 **`revokeP` 항목 자체가 없다**
  (`auth_token` / `auth_ws_token` 2건뿐, 2026-09-10 조회). KIS 가 revokeP 에 별도
  호출 한도를 두는지는 **확인 불가**다. 만약 한도가 있어 거부되면 C3 의 fail-open 이
  받아 `revoked=False` + WARNING 으로 드러나고 앵커만 안 옮겨진다(현행과 동일).

### 4.4 revoke 성공 + issue 실패 = 그 계정 토큰 없음

폐기는 캐시 파일까지 지운다(`_delete_cache`). 다음 시세 요청의 `get_token()` 이
스스로 재발급하므로 자기 치유되지만, **그 사실을 알고 있어야 한다**
(`test_c3c_issue_failure_absorbed_per_account` 가 `token_expired is None` 으로 명시).

### 4.5 herd — revoke 직후 창의 중복 발급 증폭

병행 조사 §2-e 실측: `get_token()` 은 `_is_valid()` 검사 **후 lock 안에서 재확인하지
않는다**(`token.py:118-123`). 그래서 문턱을 넘는 순간 in-flight 호출자 N개가 각자
`issue()` 를 부르고 전역 lock 에 줄을 선다 — 09-09 ISA 는 **15회 연속 발급**(61초 간격)
중 14회가 순수 낭비였고, 그 15분 lock 점유가 RIA 재발급을 15분 밀었다.

`revoke()` 는 `access_token` 을 비우므로 **같은 herd 를 인위로 트리거할 수 있다**.
15:45~15:52 는 장 마감 후라 보조 시세 REST 트래픽이 낮지만 **0 이라는 증거는 없다**.
D+1 에 `[token] 분당 한도 대기: label=` 행이 15:45~15:5x 구간에서 계정당 1행을
넘어가면 라운드가 16:00 을 침범할 수 있다 — §4.6 의 관측 항목이다.
(근본 시정 = `get_token()` double-check lock 이지만 `src/auth/**` = **8영역**이라
별건 승인 사안이다.)

### 4.6 ⚠️ 이 Red 가 심은 **미검증 가정** — 배포 전 선결 실측

이 사이클의 더블은 "폐기하면 KIS 가 새 토큰·새 만료를 준다" 를 **가정으로 심어**
잠갔다. 그 가정이 틀리면 **테스트는 전부 초록인데 운영에서는 앵커가 그대로**다 —
cycle269 가 실패한 것과 **정확히 같은 종류의 가정**이다(§1.3: 스펙 미확인).

- 병행 조사의 권고 = **코드를 쓰기 전에 1계정 수동 revoke→issue 실측**.
  그것은 되돌리기 어려운 외부 조치이므로 **사용자 승인 사안**이다.
- 실측이 부정되면 이 Red 는 폐기되고 선택지는 `_is_valid()` 마진 축소(8영역·완화일 뿐
  해소 아님) 또는 방치로 좁아진다.
- 이 Red 는 조사 문서의 **후보 A(무조건 revoke+issue)** 를 전제로 한다. 사용자가
  **후보 B(조건부 — 다음 자연 재발급 예정 시각이 원하는 창 밖일 때만 발동)** 를 고르면
  `test_c1_revoke_precedes_issue_for_each_account` 가 의미 전환 대상이 된다
  (나머지 계약 C2~C8 은 그대로 유효하다).

### 4.7 열린 질문 — 7분 창은 줄일 수 있을지도 모른다

`_ISSUE_GAP_SECS = 61.0`("분당 1개", `token.py:11,52`)은 사이클 20 의 403 실측 근거인데,
공식 문서 `docs/kis/rate-limits.md:18` 은 tokenP 를 **1초당 1건**으로 적는다. 계정마다
appkey 가 다르므로 전역 61초 직렬화가 과할 가능성이 있다. **이 사이클에서는 건드리지
않는다**(C6/G-270-4) — 다만 §4.2 의 "7분" 은 불변의 사실이 아니라 현행 상수의 결과다.

### 4.8 D+1 판독

- `[quote_token_refresh] label=… issued expired=… revoked=True` 7행 · `revoked=False` **0행**
- 각 행의 `expired` 가 **당일 15:4x~15:5x + 24h** 여야 한다 (14:xx 면 시정 실패)
- `[token] 분당 한도 대기: label=` 이 15:45~15:5x 에 계정당 **1행 이하** (§4.5 herd)
- ⚠️ **의미 반전** — cycle269 기간의 같은 마커는 `revoked=` 필드가 없다.
  배포 전후 grep 을 합산하지 말 것.

---

## 5. 롤백

leaf 1파일 원복(다음 커밋). `token.py`·`scheduler.py` 무접촉이라 blast radius 는
`src/engine/quote_token_refresh.py` 하나다. 라운드가 통째로 실패해도 매매 영향 0
(보조 계정은 주문에 쓰이지 않는다) — 드리프트가 cycle269 상태로 되돌아갈 뿐이다.
배포는 `src/**` 변경이므로 **full 모드**, 장외 창에서.

---

## 6. 산출물

- `tests/unit/engine/test_cycle270_quote_token_revoke_then_issue.py` (신규, 11 케이스)
- `tests/unit/ast/test_cycle270_ast_revoke_then_issue.py` (신규, 4 가드)
- `tests/unit/engine/test_cycle269_quote_token_refresh.py` (의미 전환 — 모듈 docstring
  C2 + `_DummyMgr.revoke()` 추가 + c2 docstring. **단언 약화 0**)
- `tests/unit/ast/test_cycle269_quote_token_refresh_wiring.py` (의미 전환 —
  `g269_4` 에 `assert "revoke" in attr_calls` 추가 + 표 1행)

### `_DummyMgr` 에 `revoke()` 를 더한 이유

더블에 그 메서드가 없으면 Green 구현의 `await manager.revoke()` 가
`AttributeError` 를 내고 계정 단위 `except Exception` 에 먹혀 **cycle269 전 케이스가
`failed` 로 뒤집힌다**. 지금 더해 두면 Red 시점(GREEN 유지)과 Green 시점 모두
정상이다. 폐기의 **행위 계약**은 cycle270 파일이 잠근다.

---

## 7. 실행 결과 (Red 확인, 2026-09-10)

```
$ python -m pytest tests/unit/engine/test_cycle269_quote_token_refresh.py \
                   tests/unit/engine/test_cycle270_quote_token_revoke_then_issue.py \
                   tests/unit/ast/test_cycle269_quote_token_refresh_wiring.py \
                   tests/unit/ast/test_cycle270_ast_revoke_then_issue.py -q

FAILED tests/unit/engine/test_cycle270_...::test_c1_revoke_precedes_issue_for_each_account
FAILED tests/unit/engine/test_cycle270_...::test_c2_round_moves_expiry_anchor_to_refresh_time
FAILED tests/unit/engine/test_cycle270_...::test_c3_revoke_failure_still_attempts_issue
FAILED tests/unit/engine/test_cycle270_...::test_c3b_revoke_failure_is_logged_loudly
FAILED tests/unit/engine/test_cycle270_...::test_c3c_issue_failure_absorbed_per_account
FAILED tests/unit/engine/test_cycle270_...::test_c5_per_account_log_appends_revoked_field
FAILED tests/unit/ast/test_cycle269_...::test_g269_4_leaf_calls_issue_not_get_token
FAILED tests/unit/ast/test_cycle270_...::test_g270_1_revoke_is_awaited_before_issue
8 failed, 44 passed in 1.53s
```

- **RED 8** = 신규 7 + 의미 전환 1(`g269_4`). 전부 "revoke 부재" 가 사유다.
- **GREEN 44** = cycle269 기존 전건(behavior 10 + AST 6 + `g269_7` 파라미터 22)
  + cycle270 신규 중 구현 무관 4건(`c2b` 더블 특성화 · `c4` 주계정 · `c5b`/`c5c`
  요약 불변) + `c7`.
- **회귀 0** — cycle269 에서 새로 깨진 행위 테스트는 없다.

C2 의 실패 메시지가 곧 결함 진술이다:

```
AssertionError: label=fire 만료가 2026-09-11 14:34:38 —
                재발급 시각 기준 앵커(2026-09-11 15:45:00)로 옮겨지지 않았다
```
