# CLAUDE.md — src/auth/ (KIS 인증)

> 이력: [`docs/history/src-auth-CLAUDE.history.md`](../../docs/history/src-auth-CLAUDE.history.md)

KIS OpenAPI OAuth 인증 및 보안 관련 모듈.

## 모듈별 역할

### token.py — 토큰 관리
- `token_manager.get_token()`: 접근토큰 발급 (`/oauth2/tokenP`)
- 만료 10분 전 자동 갱신
- 토큰 메모리 캐시 + 만료 시각 저장
- `token_manager.revoke()`: 앱 종료 시 토큰 폐기 (`/oauth2/revokeP`)

#### 발급 직렬화 (KIS `/oauth2/tokenP` 분당 1개 전역 한도)

한도는 **전역**이다 — 4 매니저가 동시에 발급하면 일부가 403 을 받는다.

- **모듈 전역 직렬화**: `_GLOBAL_ISSUE_LOCK` (asyncio.Lock, lazy create) + `_LAST_ISSUE_AT` (time.monotonic) + `_ISSUE_GAP_SECS=61.0` (1s 마진)
- `issue()` 진입 시 lock 획득 → gap 미달이면 `await asyncio.sleep(wait_secs)` → KIS POST → `_LAST_ISSUE_AT` 갱신 (HTTP 성공 *후*)
- `get_token()` 의 캐시 hit (`_is_valid()=True`) 경로는 `issue()` 호출 안 함 → lock/sleep 0 호출 (운영 정상 흐름)
- **락을 매니저별로 쪼개지 않는다** — 분당 1개는 전역 한도라 쪼개면 403 이 재발한다
- 테스트 전용 `reset_global_issue_state()` 제공 — 운영 코드 호출 금지

#### `issue()` in-flight 합류 (매니저 단위)

`asyncio.Lock` 은 **직렬화만 하고 합류시키지 않는다** — 같은 매니저의 토큰을 원하는 두 코루틴이
각자 KIS 를 친다. 그래서 진행 중인 발급에 합류하는 층을 락 **바깥**에 둔다. 전역 61초 직렬화는
그대로이고 리더만 락에 들어간다.

- 상태 3개는 **매니저 단위**다 — `self._inflight` (진행 중 `issue()` 의 Future, 없으면 `None`) + `self._inflight_token_snapshot` (리더 등록 시점의 `access_token`) + `self.issue_history` (**공개** deque, maxlen=64. 리더가 KIS 를 쳐서 성공한 `time.monotonic()` 만 기록)
- 합류 판단은 **첫 `await` 앞**에서 동기적으로 끝난다(원자성). 진행 중 Future 가 있고 스냅샷이 현재 `access_token` 과 같으면 대기자는 KIS 를 치지 않고 그 Future 를 기다린다
- **스냅샷 비교를 빼지 않는다** — `revoke()` 가 `access_token=""` 을 만든 뒤 들어온 새 리더가 옛 리더(스냅샷=구 토큰)에 합류하면 그 계정은 폐기된 토큰을 들고 앵커도 안 옮겨진다
- 리더는 **락 획득 *전*** 에 `_inflight`/스냅샷을 등록한다 — 락 대기 중인 리더에도 뒤에 온 호출자가 합류할 수 있어야 한다
- 실패·취소는 대기자에게 **전파**한다 — 삼키면 대기자가 빈 토큰으로 REST 를 쏜다. 단 리더 **취소**는 `RuntimeError` 로 바꿔 건넨다 (`CancelledError` 를 그대로 심으면 대기자 자신이 취소된 것처럼 보여 `base.py::_request` 재시도 루프가 끊긴다)
- 합류 대기는 `asyncio.shield` 로 감싼다 — 한 대기자의 취소·타임아웃이 공유 Future 를 죽이면 전원이 실패한다. 상한 `_ISSUE_JOIN_TIMEOUT_SECS=600.0`(cycle296)은 교착 방지용이지 리스크 다이얼이 아니다 — `system_config` 편입 금지
- `finally` 는 `self._inflight is fut` 일 때만 비운다 — 그새 새 리더가 등록했다면(스냅샷 불일치로 합류 거부) 그 등록을 지우면 안 된다
- 합류는 **"진행 중"에만** 성립한다 — 순차 `issue()` 두 번은 여전히 KIS 두 번이다. `src/engine/quote_token_refresh.py` 의 `revoke()`→`issue()` 가 이 성질에 기댄다
- `issue_history` 는 **공개 속성**이다 — `src/engine/quote_token_refresh.py` 가 `getattr(manager, "issue_history", ())` 로 읽어 `window_issues_total` 을 센다. 이름을 바꾸면 그 관측이 조용히 0 이 된다

#### 토큰 캐시 영속화 (`.token_cache/`)
- **디렉토리 단위**: `_TOKEN_CACHE_DIR=.token_cache/`. 메인 `main.json` / 보조 `quote_<safe-label>.json`. Docker 볼륨 마운트 친화 (`./.token_cache:/app/.token_cache`)
- **호환 fallback**: 구 경로 `.token_cache.json` (`_LEGACY_MAIN_CACHE_PATH`) / `.token_cache_quote_<label>.json` (`_LEGACY_QUOTE_CACHE_PREFIX`) 존재 시 1회 읽고 새 경로로 즉시 마이그레이션 + 구 경로 unlink. 운영 중단 0

#### `.token_cache` 권한 (Dockerfile prod)
- `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `chmod 755 /app/.token_cache` → `USER appuser` 순서 불변 (**mkdir 이 chown 보다 앞** + **USER 가 마지막**). 호스트 bind mount 가 root:root 로 생기면 컨테이너 `appuser` 가 캐시를 쓰지 못한다 (2026-05-20 `PermissionError [Errno 13]` 사고) — 이 순서가 그것을 막는다
- 회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py` 3 케이스. 정적 텍스트 파싱이라 docker build 미실행

### hashkey.py — Hashkey 생성
- POST 요청 바디의 무결성 검증용 해시 생성 (`/uapi/hashkey`)
- 주문 API 호출 시 헤더에 포함

## KIS 인증 플로우
```
앱 시작 → tokenP로 토큰 발급 → 메모리에 저장 + 만료 시각 기록
→ API 호출 시 헤더에 Bearer 토큰 포함
→ 만료 10분 전 자동 갱신
→ 앱 종료 시 revokeP로 토큰 폐기
```

## Multi-Account 토큰 매니저

**메인 계좌 (token_manager) 흐름 100% 보존** — 매매/잔고/체결통보는 영원히 메인 단일.

- `token_manager` (모듈 전역 인스턴스) — 메인 계좌 토큰. 기존 import 경로 변경 없음
- `get_token_manager(label=None)` async — 보조 시세 계좌 매니저 lazy 발급. `label=None` 이면 메인 반환
- 보조 매니저는 `kis_quote_accounts.app_key/app_secret/kis_env` 자격증명을 DB 에서 로드 + `_safe_cache_filename(label)` 격리 캐시 파일 사용
- 같은 label 두 번 호출 → 동일 인스턴스 (싱글톤, `_quote_token_managers: dict[str, TokenManager]` + `asyncio.Lock`)
- 미등록 label / `active=False` → `ValueError` raise — 호출자가 흡수해야 메인 흐름 영향 0

**보조 계좌(quote_accounts)는 시세 수신 전용. order.py / balance.py / 체결통보(H0STCNI0) 구독은 영원히 메인 계좌만 사용. 코드 리뷰 시 보조 계좌 label/account_id 변수가 매매/잔고 함수로 전달되는지 반드시 확인.**

### boot 사전 순차 발급

- `TradingScheduler._preissue_all_tokens()` — `_boot()` 진입 초입에 호출
- 메인 → 보조 N (`kqa.list_accounts(active_only=True)` 순회) 순차 호출
- 캐시 hit 면 즉시 return / miss 면 `_GLOBAL_ISSUE_LOCK` 안에서 60s gap 강제
- 보조 발급 실패는 try/except 흡수 — 다음 보조로 진행 + 메인 흐름 영향 0

## 주의사항
- 앱키/시크릿은 절대 코드에 하드코딩하지 않음 (.env 관리)
- 토큰 유효기간: 24시간
- WebSocket 접속키는 별도 발급 (`/oauth2/Approval`) — realtime/websocket.py에서 처리
- **`build_headers()` 는 메인 매니저 경로에서만 호출** — 보조 매니저는 시세 수신 한정이라 매매 헤더 구성에 사용 금지
