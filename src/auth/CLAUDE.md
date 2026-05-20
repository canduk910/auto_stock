# CLAUDE.md — src/auth/ (KIS 인증)

KIS OpenAPI OAuth 인증 및 보안 관련 모듈.

## 모듈별 역할

### token.py — 토큰 관리
- `token_manager.get_token()`: 접근토큰 발급 (`/oauth2/tokenP`)
- 만료 10분 전 자동 갱신
- 토큰 메모리 캐시 + 만료 시각 저장
- `token_manager.revoke()`: 앱 종료 시 토큰 폐기 (`/oauth2/revokeP`)

#### 사이클 20 (2026-05-20) — 분당 1개 한도 위반 차단
- KIS `/oauth2/tokenP` 분당 1개 / 전역 한도. 4 매니저 동시 발급 시 일부 403
- **모듈 전역 직렬화**: `_GLOBAL_ISSUE_LOCK` (asyncio.Lock, lazy create) + `_LAST_ISSUE_AT` (time.monotonic) + `_ISSUE_GAP_SECS=61.0` (1s 마진)
- `issue()` 진입 시 lock 획득 → gap 미달이면 `await asyncio.sleep(wait_secs)` → KIS POST → `_LAST_ISSUE_AT` 갱신 (HTTP 성공 *후*)
- `get_token()` 의 캐시 hit (`_is_valid()=True`) 경로는 `issue()` 호출 안 함 → lock/sleep 0 호출 (운영 정상 흐름)
- 테스트 전용 `reset_global_issue_state()` 제공 — 운영 코드 호출 금지
- **캐시 영속화**: `_TOKEN_CACHE_DIR=.token_cache/` 디렉토리 단위. 메인 `main.json` / 보조 `quote_<safe-label>.json`. Docker 볼륨 마운트 친화 (`./.token_cache:/app/.token_cache`)
- **호환 fallback**: 구 경로 `.token_cache.json` (`_LEGACY_MAIN_CACHE_PATH`) / `.token_cache_quote_<label>.json` (`_LEGACY_QUOTE_CACHE_PREFIX`) 존재 시 1회 읽고 새 경로로 즉시 마이그레이션 + 구 경로 unlink. 운영 중단 0

### hashkey.py — Hashkey 생성
- POST 요청 바디의 무결성 검증용 해시 ��성 (`/uapi/hashkey`)
- 주문 API 호출 시 헤더에 포함

## KIS 인증 플���우
```
앱 시작 → tokenP로 토큰 발급 → 메모리에 저장 + 만료 시각 기록
→ API 호출 �� 헤더에 Bearer 토큰 포함
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

### boot 사전 순차 발급 (사이클 20)

- `TradingScheduler._preissue_all_tokens()` — `_boot()` 진입 초입에 호출
- 메인 → 보조 N (`kqa.list_accounts(active_only=True)` 순회) 순차 호출
- 캐시 hit 면 즉시 return / miss 면 `_GLOBAL_ISSUE_LOCK` 안에서 60s gap 강제
- 보조 발급 실패는 try/except 흡수 — 다음 보조로 진행 + 메인 흐름 영향 0

## 주의사항
- 앱키/시크릿은 절대 코드에 하드코딩하지 않음 (.env 관리)
- 토큰 유효기간: 24시간
- WebSocket 접속키는 별도 발급 (`/oauth2/Approval`) — realtime/websocket.py에서 처리
- **`build_headers()` 는 메인 매니저 경로에서만 호출** — 보조 매니저는 시세 수신 한정이라 매매 헤더 구성에 사용 금지
