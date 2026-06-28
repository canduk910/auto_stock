# 자문 — 사이클 181 토큰만료 분기 substring → msg_cd 화이트리스트 전환

## 질문 요약

`src/api/base.py` 의 토큰만료 분기(`_request` L560 / `_request_via_quote_pool` L866)가 순수 substring
(`"token" in msg1.lower() or "만료" in msg1`) 이라, KIS `EGW00120`(본 프로젝트에서 예수금부족 변형으로
활용, msg1 "기간이 만료된 code") 등 비-토큰 "만료" 메시지를 토큰만료로 오분류 → 불필요 `issue()` 재발급 +
동일 매수 body 재전송. msg_cd 화이트리스트 전환 설계의 5개 의제 확정.

---

## 의제 1 — KIS MCP 정본 재확인 (결과 + 한계)

**검색 범위/쿼리**:
- `mcp__kis-code-assistant__search_auth_api` — `subcategory="인증"`, `function_name="auth_token"` / `auth_ws_token` (2건 hit)
- `mcp__kis-code-assistant__read_source_code` — `auth_token.py` + `chk_auth_token.py` 정본 직독

**확인된 사실 (KIS 공식 OAuth 정본)**:
- `/oauth2/tokenP` POST `grant_type=client_credentials` → 응답 `access_token` / `token_type="Bearer"` /
  `expires_in`(초) / `access_token_token_expired`(일시). REST access token 발급 흐름 자체는 정본 일치.
- 공식 샘플의 에러 처리 = `response.status_code == 200` 분기뿐 (rt_cd/msg_cd 파싱 없음).

**한계 (명시)**: **KIS MCP 는 EGW0012x 에러코드 의미를 직접 문서화하지 않는다.** MCP 는 API 스펙
(TR_ID·요청/응답 필드) 어시스턴트이지 에러코드 DB 가 아니다. 따라서 토큰만료 msg_cd 정본은 MCP 로 직접
취득 불가 → **로컬 캐시 `docs/kis/error-codes.md` 를 정본으로 채택**한다.

**로컬 캐시 교차 검증 (KIS 공식 인증 EGW 표와 verbatim 일치, 불일치 0)**:
| 코드 | 의미 | 분류 |
|------|------|------|
| EGW00120 | 기간이 만료된 **code** | **OAuth authorization-code grant 산물 → 토큰만료 아님. 본 프로젝트 예수금부족 변형** |
| EGW00121 | 유효하지 않은 **token** | REST access token (load-bearing) |
| EGW00122 | **token**을 찾을 수 없습니다 | REST access token |
| EGW00123 | 기간이 만료된 **token** | REST access token (load-bearing) |
| EGW00124 | 유효하지 않은 **session_key** | websocket approval_key 영역 |
| EGW00125 | **session_key**를 찾을 수 없습니다 | websocket approval_key 영역 |
| EGW00126 | 기간이 만료된 **session_key** | websocket approval_key 영역 |

**REST vs websocket 구분 (중요)**: `_request` / `_request_via_quote_pool` 는 **둘 다 REST 경로**다.
REST 인증 = access token → 토큰만료는 **EGW00121 / EGW00123** (보조적으로 EGW00122)으로만 온다.
EGW00124~00126(session_key) 은 websocket approval_key 영역이라 **REST 응답엔 사실상 무발화**이며,
설령 발화해도 `token_manager.issue()`(access token 재발급)로는 해소되지 않는다. → 화이트리스트에 포함해도
**무해(절대 안 fire) + 대칭/방어 목적**일 뿐, load-bearing 은 EGW00121/00122/00123 3종이다. team-leader
제안 6종 셋 그대로 채택하되 이 구분을 명시한다 (EGW00120 절대 미포함은 정확).

---

## 의제 2 — hybrid vs 순수 화이트리스트 (핵심)

### 2(b) 먼저 — 토큰만료는 어느 HTTP 경로로 오는가 (결정적 구조 사실)

코드 직독 결과 `_request` L463~474:
```python
resp = await client.get/post(...)
resp.raise_for_status()   # L473 ← 먼저
data = resp.json()        # L474 ← 나중
```
`raise_for_status()` 가 json 파싱 **앞**에 있다. 따라서:
- KIS 가 토큰만료를 **HTTP 401/500** 으로 주면 → `HTTPStatusError` raise → 5xx/4xx 카운팅 + backoff 재시도
  분기(L475~516)로 흐른다. **토큰분기(L560)에 절대 도달하지 못한다** (현행도, 시정 후도 동일).
- 토큰분기(L560)는 오직 **HTTP 200 + rt_cd != "0"** 일 때만 도달한다.

team-leader 확인대로 L475~516 에 **401-특화 토큰 재발급은 없다**. 즉 현재 base.py 구조상 토큰 재발급
self-heal 은 "HTTP 200 + rt_cd!=0 + EGW0012x" 경로에서만 작동한다. KIS REST 가 만료토큰을 HTTP 500 으로
주는 빈도가 높다는 실측 보고가 다수임을 감안하면, **토큰분기의 현실 발화 대부분은 사실상
EGW00120(HTTP 200, rt_cd!=0, "만료") 오발화였을 개연성이 크다** — 즉 substring 의 살아있는 효과 = 오발화.
(이 HTTP-500 토큰만료 미흡수는 cycle 181 이 만든 결함이 아니라 **선재(先在) 갭**이다. 별도 인계.)

### 2(a) 권고 — **hybrid 채택** (순수 화이트리스트 + "token" 보조 폴백, "만료" 폐기)

**근거 — false-negative 위험 평가**:
- load-bearing 토큰만료(EGW00121/00123)는 msg_cd 가 **안정적**이라 화이트리스트가 정확히 포착 → 이 경로는
  순수 화이트리스트로 안전.
- 잔여 false-negative 리스크 = "HTTP 200 + rt_cd!=0 + 미등재/빈 msg_cd 로 실제 토큰만료 signal" 의 희박한
  엣지. 이 한 경우를 위해 보조 폴백을 **싸게** 남긴다.
- 단, **"만료" substring 은 완전 폐기**한다 (false-positive 의 뿌리: EGW00120 "code 만료" + 권리만료/
  청약기간 만료 등). 대신 **영문 "token" substring 만** 보조 폴백으로 유지한다 — 한국어 비-토큰 거부 메시지에
  영문 "token" 이 섞일 확률은 거의 0 이라 "만료" 보다 압도적으로 정밀하다(EGW00121 "유효하지 않은 token",
  EGW00122 "token을 찾을 수 없습니다", EGW00123 "기간이 만료된 token" 만 매칭).
- "token" 폴백에도 **msg_cd 배제가드**를 동반해 belt-and-suspenders (의제 5 참조).

**결론**: hybrid 는 load-bearing 이 아니라 **보험**이다. 가중치는 화이트리스트 ≫ "token" 폴백. 비용
(frozenset 1개 + 멤버십 1회)이 미미하고 self-heal 본질을 더 두텁게 보존하므로 순수 화이트리스트보다
risk-adjusted 우위.

### backend-dev 구현 형태 (그대로 사용)

```python
# === base.py 모듈 상수 (상단) ===
_TOKEN_EXPIRED_MSG_CODES = frozenset({
    "EGW00121", "EGW00122", "EGW00123",   # REST access token: invalid / not-found / expired (load-bearing)
    "EGW00124", "EGW00125", "EGW00126",   # session_key(websocket) — REST 무발화, 대칭/방어용
})
# 토큰분기 오발화 차단용 배제 코드 (예수금부족 변형 + 자금부족/공용)
_TOKEN_BRANCH_EXCLUDE_MSG_CODES = frozenset({
    "EGW00120",   # 기간이 만료된 code — 본 프로젝트 예수금부족 변형 (is_insufficient_cash 화이트리스트)
    "APBK0919",   # 예수금 부족(명시)
    "APBK0918",   # 장시간외/보유부족/자금부족 공용
})

# === _request L556~560 / _request_via_quote_pool L862~866 (양쪽 동일) ===
msg_cd = data.get("msg_cd", "")
msg1 = data.get("msg1", "")
msg_cd_u = (msg_cd or "").upper()

_token_expired = (
    msg_cd_u in _TOKEN_EXPIRED_MSG_CODES
    or ("token" in msg1.lower() and msg_cd_u not in _TOKEN_BRANCH_EXCLUDE_MSG_CODES)
)
if _token_expired:
    # ... 기존 issue() + (attempt < MAX_RETRIES) continue 본질 그대로 보존 ...
```

- `"만료"` 절은 **완전 삭제**. `or "token" in msg1.lower()` 만 배제가드와 함께 잔존.
- 양쪽 경로(`_request` = `token_manager.issue()` / `_request_via_quote_pool` = `manager.issue()`)에 동일 조건
  적용. R7 `[api_retry_exhausted] last_status=token_expired`(L568~575) 최종 실패 로그 **보존**.

---

## 의제 3 — 인증 chain 안전성 평가

**현행 오발화의 인증 chain 위해**: `token_manager.issue()` 는 분당 1개 한도(≤61초 블록), 토큰 24h 유효.
EGW00120 예수금부족 매수거부가 토큰분기로 빠지면 **거부 1건당 최대 2회 issue()** 강제 (attempt 1·2 재시도).
세션 후반 예수금 소진 구간엔 다수 후보가 연쇄적으로 예수금부족 거부 → `issue()` 연타 → 분당 1개 한도
근접/위반 → KIS 가 토큰 발급을 일시 차단. cycle 175/177 인계 **"잔고 영속 500 fallback / EC2 잔고 500 halt"**
가 정확히 이 spurious issue() 연타의 하류 증상일 개연성이 높다 (team-leader: 운영 로그에서 잔고 500 halt
직전 `issue()` 호출 빈도 + `[api_retry_exhausted] last_status=token_expired` 발생 시각 상관 확인 권고).

**시정의 효과**: EGW00120/APBK0919/APBK0918 가 토큰분기 미진입 → **false 재발급 벡터 완전 제거** →
분당 한도 압박 해소 → 인증 chain 사고 위험 **감소**. 동시에 진짜 토큰만료(EGW00121/00123)는 여전히
`issue()` + `continue` 로 self-heal **본질 보존** → 자동복구 충분. 즉 시정은 **위험은 줄이고 복구는 유지**한다.

---

## 의제 4 — 중복 체결 위험 평가 (트레이더 관점, 매매 안전성 직결)

**현행 흐름 (EGW00120 예수금부족 매수 TTTC0012U)**:
1. HTTP 200, rt_cd!=0, EGW00120, msg1 "...만료..." → "만료" 매칭 → 토큰분기.
2. `issue()`(≤61초 블록) → `continue` → **동일 매수 body 재전송** (scan 시점에 산정된 원래 수량·가격).
3. 또 EGW00120 → 또 `issue()`(≤61초) → `continue` → attempt 3 도달 → 토큰분기 fall-through.
4. kis_error → raise KisApiError → OrderEngine `is_insufficient_cash` True → `block_buy(900s)`.
→ 총 **~122초 지연 + 불필요 토큰 2회 재발급 + 동일 매수 2회 추가 재전송** 후에야 매수락.

**중복 체결 위험 (핵심 트레이더 판단)**:
- 정적으로 "예수금부족이니 재전송해도 또 거부될 뿐" 은 **안전한 경우에만** 참이다.
- **위험 시나리오 (race)**: ~122초 블록 동안 (a) 동일 계좌의 **타 종목 매도 체결**로 예수금이 충전되거나
  (b) 입금/정산 반영으로 주문가능금액이 회복되면 → **재전송된 매수가 갑자기 체결**된다. 이때 체결되는 주문은
  **scan 시점 산정 가격**(이미 2분 stale)이라 VB/LTV 같은 빠른 돌파 종목에선 슬리피지 노출이 크고, 운영자가
  의도하지 않은 **중복/유령 매수**가 된다. 이는 "execute_buy 가 현재가 기준으로 주문가를 결정한다"는 규율을
  정면으로 위반한다.
- 추가로, 프로세스는 단일 토큰을 공유하므로 매매 도중 spurious `issue()` 가 동시 진행 중인 타 주문/잔고
  호출의 토큰을 교체 → 인증 chain 교란 (의제 3 과 결합).

**시정 후 흐름**: EGW00120 → 토큰분기 미진입 → 즉시 kis_error → raise KisApiError → OrderEngine
`is_insufficient_cash` True → **즉시 `block_buy(900s)`**. 재발급 0 / 재전송 0 / 122초 지연 0 / 중복체결
윈도우 0. **모든 축에서 명백히 우월**하며, 특히 예수금 충전 race 로 인한 중복-fill 해저드를 제거하는 점이
순(純)매매 안전 이득이다. → **시정 후가 매매 안전상 명백히 우월함을 확정**한다.

---

## 의제 5 — 배제 가드 belt-and-suspenders 권고

**권고 = 옵션 (i) 변형 — base.py 인라인 msg_cd 배제 frozenset** (balance.py 분류함수 호출/어댑터 불채택).

**근거**:
- **순수 화이트리스트만으로도 EGW00120 은 이미 배제**된다 (whitelist 미포함). 하지만 의제 2 에서 **"token"
  보조 폴백을 유지**하므로, 그 폴백이 미래에 "token" 을 우연히 담은 자금/시간외 거부에 재오발화하지 않도록
  **폴백 절에만** 배제가드를 둔다. 이것이 `_TOKEN_BRANCH_EXCLUDE_MSG_CODES`(EGW00120/APBK0919/APBK0918) 다.
- **balance.py 분류함수(`is_insufficient_cash`/`is_market_closed_rejection`) 직접 호출은 불채택**:
  - (이유 1, 순환 import) balance.py 는 base.py 의 `kis_get` 를 import 한다. base.py 가 balance.py 를
    import 하면 **순환 import**. lazy-import 로 우회 가능하나 hot path 에 불필요한 결합.
  - (이유 2, 스코프) team-leader 의 "base.py 외 변경 0 / balance.py 재사용만" 원칙에 인라인 frozenset 이
    가장 부합. raw dict 어댑터 신설(옵션 i 원안)·임시 KisApiError 구성(옵션 ii)은 모두 과설계.
- `_request` 분기가 raw `data` dict 단계라 KisApiError 객체가 없다는 제약은, **분류함수를 쓰지 않으므로
  무의미**해진다. msg_cd 문자열 멤버십(`msg_cd_u in _TOKEN_BRANCH_EXCLUDE_MSG_CODES`)만으로 충분.

**정리**: 화이트리스트(정확성 담당) + "token" 폴백(엣지 self-heal) + 인라인 msg_cd 배제(폴백 오발화 차단)
3중. balance.py 변경 0, 순환 import 0, 과설계 0.

> 단, team-leader 가 hybrid 자체를 거부하고 **순수 화이트리스트**를 택하면 → "token" 폴백 삭제 → 그 경우
> `_TOKEN_BRANCH_EXCLUDE_MSG_CODES` 도 **불필요**(EGW00120 이 whitelist 에 없으니 자동 배제). 즉 배제가드의
> 존재 이유는 전적으로 "token" 폴백의 동반 여부에 종속된다. 두 결정은 한 쌍이다.

---

## 현 코드와의 정합성

- **충돌 항목**: 없음. 토큰분기의 재발급+retry 본질, R2/R4/R7/R8 ERROR 보존 매트릭스, `[kis_rejection]`
  영구저장(CLAUDE.md "절대 깨지 말 것")과 모두 양립. `"만료"` 삭제 + `"token"` 폴백+배제가드만 추가.
- **balance.py 영향 0**: `is_insufficient_cash` 의 EGW00120 화이트리스트는 그대로 유지된다. cycle 181 은
  base.py 토큰분기가 EGW00120 을 **가로채지 않게** 할 뿐, OrderEngine 의 예수금부족 처리(block_buy 900s)는
  오히려 **정상 도달**하게 된다 (현행은 토큰분기가 2회 가로챈 뒤에야 도달).
- **양쪽 경로 동일 적용 필수**: `_request_via_quote_pool`(시세 풀)도 동일 결함이라 동일 시정. 단 시세 풀은
  매매 무관(시세성)이라 매매 안전 위해는 `_request` 경로가 본질.

---

## 반례 / 한계

1. **HTTP-500 토큰만료 미흡수 선재 갭**: KIS 가 만료토큰을 HTTP 500 으로 주면 `raise_for_status` 가
   토큰분기 도달 전 가로채 → 재발급 없이 5xx 재시도만. 이는 cycle 181 무관 **선재 결함**이며, 본 시정으로
   악화되지 않는다. (별도 인계: 401/특정 5xx+토큰 body 감지 시 재발급 분기 — 단 HTTP 단계엔 rt_cd 없음이라
   별도 설계 필요. 현행 self-heal 은 다음 스케줄 토큰 갱신에 의존.)
2. **미등재 msg_cd 로 오는 진짜 토큰만료**: HTTP 200 + rt_cd!=0 인데 msg_cd 가 EGW0012x 가 아니고 빈/신규
   코드면 화이트리스트 miss. → "token" 보조 폴백이 msg1 에 영문 "token" 만 있으면 흡수. msg1 에도 "token"
   이 없으면 miss (극히 희박). 이 경우 self-heal 실패 → 다음 토큰 갱신/재시도 소진에 의존. hybrid 가 이
   잔여 위험을 최소화하는 이유.
3. **session_key(EGW00124~126) REST 무발화 가정**: REST 경로에서 발화하지 않는다는 전제. 만약 KIS 가
   REST 에 session_key 에러를 surface 하면 `issue()`(access token 재발급)로는 해소 안 됨 → 무한 재시도
   소진 후 R7 로깅. 화이트리스트 포함이 이를 만들지는 않으나(원래 access token 만 재발급), 운영 로그에서
   EGW00124~126 가 REST 경로에 찍히는지 D+1 점검 권고.

---

## 후속 검증 권고 (tdd-engineer / tester)

**Red 회귀 가드 (결정적 입력 시리즈)**:
- **G-181-FP-1 (false-positive 차단, 핵심)**: `data={"rt_cd":"1","msg_cd":"EGW00120","msg1":"기간이 만료된
  code 입니다"}` → 토큰분기 **미진입** → `token_manager.issue()` 호출 0회 + 동일 body 재전송 0회 → 즉시
  `raise KisApiError`. (mock `issue` call_count==0 단언이 핵심)
- **G-181-FP-2**: APBK0919 / APBK0918(자금부족 msg1) 동일 — issue 0회.
- **G-181-FP-3**: "권리만료"/"청약기간 만료" 등 비-토큰 "만료" msg1 + 임의 msg_cd → issue 0회 ("만료" 폐기
  검증).
- **G-181-TP-1 (true-positive 보존)**: EGW00123 "기간이 만료된 token" → 토큰분기 진입 → `issue()` 1회 +
  attempt<3 시 `continue` 재시도 → (재시도서 rt_cd=0 mock) 최종 성공. EGW00121 동일.
- **G-181-TP-2 (hybrid 폴백)**: msg_cd="" + msg1 에 "token" 포함 + 배제코드 아님 → 토큰분기 진입(issue 1회).
  반대로 msg_cd="EGW00120" + msg1 에 우연히 "token" 포함 → 배제가드로 **미진입**(issue 0회).
- **G-181-EXHAUST**: EGW00123 가 MAX_RETRIES 까지 지속 → R7 `[api_retry_exhausted]
  last_status=token_expired` ERROR 로그 1행 emit 보존 (freezegun/respx).
- **G-181-POOL**: `_request_via_quote_pool` 동일 5케이스 (`manager.issue` mock) — 양쪽 경로 동일성.
- **G-181-AST**: base.py 에 `"만료" in msg1` 잔존 0건 + `_TOKEN_EXPIRED_MSG_CODES` frozenset 에 EGW00120
  미포함(엔트리 검사, source 텍스트 스캔 아님 — cycle 167/179 dead code AST 패턴 답습) + EGW00121/00123
  포함 단언.

**tester (통합/안전성)**: OrderEngine 매수 거부 경로 — EGW00120 매수거부 시 시정 후 `block_buy(900s)` 가
**더 빨리**(122초 지연 없이) 발화하는지 + 동일 매수 재전송 0건 확인. 운영 로그 상관분석(잔고 500 halt ↔
spurious issue() 빈도)은 team-leader 영역.

---

# 추가 자문 (2차 패스 — domain-expert 코드 재정독)

> 1차 메모(위)는 정합성이 높고 의제 2~5 분석은 그대로 채택한다. 코드를 직접 태워본 결과 **설계를 더
> 견고하게 만드는 2가지 정정/보강**을 확정했다. 1차의 한 권고(session_key 6종 화이트리스트)는 **3종으로
> 좁히기를 권고**한다.

## 정정 1 — 화이트리스트는 access token 3종만: `{EGW00121, EGW00122, EGW00123}` (session_key 3종 제외)

1차는 team-leader 제안 6종(EGW00121~00126)을 "대칭/방어용"으로 그대로 채택했으나, **이는 무해한 방어가
아니라 잠복 footgun** 이다. 판정 원칙을 명시한다:

> **토큰만료 화이트리스트는 `token_manager.issue()` 가 *올바른 복구*인 코드만 담아야 한다.** `issue()` 는
> **access token** 을 재발급한다. EGW00121/00122/00123(access token invalid/not-found/expired)은 재발급으로
> 해소된다. EGW00124~00126(session_key)은 **websocket approval_key 도출 키**라 access token 재발급으로
> **해소 불가**다.

- 만약 EGW00126(만료 session_key)이 REST 에 surface 하면(1차 가정대로면 "무발화"), 화이트리스트 포함 시:
  `_token_expired=True` → `issue()` (access token 재발급, 무관) → `continue` → 동일 거부 → `issue()` 재발 →
  3회 소진 → **spurious issue 2회 + R7 exhaust**. 이는 cycle 181 이 제거하려는 바로 그 "issue 폭주 +
  전역 61초 락 직렬화"(정정 2) 를 session_key 에 대해 *재생산*한다.
- session_key 가 진짜 "REST 무발화"라면 화이트리스트 포함은 **value 0**(절대 매칭 안 함) + footgun(무발화
  가정이 깨질 때 issue 폭주). 제외하면 value 0 동일 + footgun 0. → **제외가 strictly dominant.**
- 1차 한계 #3 자체가 "EGW00124~126 무한 재시도 소진 후 R7 / D+1 REST 발화 점검 권고"라고 적었는데, 이는
  **포함을 정당화하는 게 아니라 제외를 정당화**하는 근거다. (session_key 에러는 화이트리스트로 잡아 issue()
  돌릴 게 아니라, generic KisApiError 로 즉시 raise 시켜 websocket 영역 진단으로 보내는 게 맞다.)

**확정 화이트리스트**: `_TOKEN_EXPIRED_MSG_CODES = frozenset({"EGW00121", "EGW00122", "EGW00123"})`.
배제 frozenset(`{EGW00120, APBK0919, APBK0918}`) + "token" 보조 폴백 + `"만료"` 폐기 = 1차 그대로 유지.

## 정정 2 — 증폭의 본질은 `_ISSUE_GAP_SECS=61.0` 의 *전역 직렬 락* (의제 3·4 보강)

1차는 "분당 1개 한도(≤61초 블록)"로만 기술했으나, `src/auth/token.py` 정독 결과 더 날카로운 구조 사실:

- `_GLOBAL_ISSUE_LOCK` + `_LAST_ISSUE_AT` + `_ISSUE_GAP_SECS = 61.0` 은 **모듈 전역** 이고 **메인 단일 +
  모든 시세 풀 보조 매니저가 공유**한다 (`token.py:47~52`). `issue()` 는 락 획득 후 **락 안에서** gap 미달분
  sleep (`token.py:138~141`).
- 따라서 spurious `issue()` 가 N개면 전역 락에 **직렬화**되고, 연속 spurious issue 는 각자 직전 발급으로 gap 이
  다시 <61s → **각 호출이 최대 61초씩 추가로 락 안 sleep** → 누적 **~N×61초 인증 체인 그리드락**. 1차가 추정한
  "잔고 500 halt 하류 증상" 의 정확한 증폭 기전이 이것이다 — 단순 "분당 1개 거부"가 아니라 **전역 락 직렬 sleep
  누적**. 부팅 구간 예수금부족 다발 → issue 폭주 → 토큰 락이 메인+풀의 모든 후속 인증을 직렬로 막음.
- **시정 후 정량**: 예수금부족발 issue = O(N) → 0. 토큰 발급 트리거가 합법 3종(콜드 부팅 1회 / 24h TTL /
  실 EGW00121·123)으로 복귀 → 부팅 토큰 발급 ≈ O(1)/일. 운영 검증 지표 = `[token] 분당 한도 대기` WARNING
  빈도(token.py:138 emit)가 시정 전후 급감해야 정상 — tester/team-leader 가 D+1 측정.

## 1차와의 정합 요약 (team-leader 채택 가이드)

| 항목 | 1차 권고 | 2차 정정 | 최종 |
|------|---------|---------|------|
| 화이트리스트 | EGW00121~00126 (6종) | **access token 3종만** | `{EGW00121,00122,00123}` |
| hybrid("token" 폴백 + "만료" 폐기) | 채택 | 동일 | **채택** |
| 배제 frozenset `{EGW00120,APBK0919,APBK0918}` | 채택 | 동일 | **채택** |
| 배제 가드 형태 (base.py 인라인 frozenset, balance.py 불호출, 순환 import 회피) | 채택 | 동일 | **채택** |
| 양 사이트(`_request`+`_request_via_quote_pool`) 동일 + AST 가드 | 채택 | 동일 | **채택** |
| 401 분기 신설 | 안 함(선재 갭 분리) | 동일 | **안 함** |
| 증폭 기전 | "분당 1개 ≤61초" | **전역 직렬 락 N×61초** | 보강 |

G-181-AST 가드는 정정 1 반영 — `_TOKEN_EXPIRED_MSG_CODES` frozenset 에 **EGW00124/00125/00126 미포함**
단언 추가(EGW00120 미포함 + EGW00121/00123 포함과 함께, 엔트리 검사).
