# CLAUDE.md — src/auth/ (KIS 인증)

KIS OpenAPI OAuth 인증 및 보안 관련 모듈.

## 모듈별 역할

### token.py — 토큰 관리
- `token_manager.get_token()`: 접근토큰 발급 (`/oauth2/tokenP`)
- 만료 10분 전 자동 갱신
- 토큰 메모리 캐시 + 만료 시각 저장
- `token_manager.revoke()`: 앱 종료 시 토큰 폐기 (`/oauth2/revokeP`)

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

## Multi-Account 토큰 매니저 (사이클 7-A, 2026-05-17)

**메인 계좌 (token_manager) 흐름 100% 보존** — 매매/잔고/체결통보는 영원히 메인 단일.

- `token_manager` (모듈 전역 인스턴스) — 메인 계좌 토큰. 기존 import 경로 변경 없음.
- `get_token_manager(label=None)` async — 보조 시세 계좌 매니저 lazy 발급. `label=None` 이면 메인 반환.
- 보조 매니저는 `kis_quote_accounts.app_key/app_secret/kis_env` 자격증명을 DB 에서 로드 + `_safe_cache_filename(label)` 격리 캐시 파일 사용.
- 같은 label 두 번 호출 → 동일 인스턴스 (싱글톤, `_quote_token_managers: dict[str, TokenManager]` + `asyncio.Lock`).
- 미등록 label / `active=False` → `ValueError` raise — 호출자가 흡수해야 메인 흐름 영향 0.

**보조 계좌(quote_accounts)는 시세 수신 전용. order.py / balance.py / 체결통보(H0STCNI0) 구독은 영원히 메인 계좌만 사용. 코드 리뷰 시 보조 계좌 label/account_id 변수가 매매/잔고 함수로 전달되는지 반드시 확인.**

본 사이클(7-A) 은 인프라만 — 실제 시세 활용은 7-B (WebSocketPool) / 7-C (REST 라운드로빈) 사이클에서.

## 주의사항
- 앱키/시크릿은 절대 코드에 하드코딩하지 않음 (.env 관리)
- 토큰 유효기간: 24시간
- WebSocket 접속키는 별도 발급 (`/oauth2/Approval`) — realtime/websocket.py에서 처리
- **`build_headers()` 는 메인 매니저 경로에서만 호출** — 보조 매니저는 시세 수신 한정이라 매매 헤더 구성에 사용 금지
