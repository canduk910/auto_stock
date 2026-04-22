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

## 주의사항
- 앱키/시크릿은 절대 코드에 하드코딩하지 않음 (.env 관리)
- 토큰 유효기간: 24시간
- WebSocket 접속���는 별도 발급 (`/oauth2/Approval`) — realtime/websocket.py에서 처리
