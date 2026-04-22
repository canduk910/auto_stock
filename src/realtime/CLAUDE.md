# CLAUDE.md — src/realtime/ (WebSocket 실시간)

KIS WebSocket 실시간 시��� 수신 및 체결통보 처리.

## 모듈별 역할

### websocket.py — 연결 관리
- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종��� 시세 구독/해제 (최대 40종목)
- Heartbeat 감시 (30초 미수신 시 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES 복호화용 iv/key 수신 및 저장

### handler.py — 메시지 처리
- 파이프(|) 구분 메시지 파싱
- 체결통보(H0STCNI0) AES-256-CBC 복호화
- 파싱된 시세 데이터를 engine/strategy.py 콜백으로 전달

## WebSocket 메시지 포맷
```
수신: 0|H0STCNT0|001|005930^...^현재가^...
        │  │       │    └ 데이터 (캐럿 ��분)
        │  │       └ 건수
        │  └ TR_ID
        └ 암호화 여부 (0: ���문, 1: 암호화)
```

## 주의사항
- 체결통보(H0STCNI0)는 실전에��� 암호화됨 — 반드시 decrypt 필요
- 모의투자 체결통보 TR_ID: H0STCNI9 (실전: H0STCNI0)
- 구독 종목 변경 시 기존 구독 해제 → 새 구독 등록 순서
- WebSocket URL은 REST와 다��� (ops.koreainvestment.com)
