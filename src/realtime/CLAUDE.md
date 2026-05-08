# CLAUDE.md — src/realtime/ (WebSocket 실시간)

KIS WebSocket 실시간 시세 수신 및 체결통보 처리.

## 모듈별 역할

### websocket.py — 연결 관리
- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종목 시세 구독/해제 (최대 200종목)
- 체결통보 구독 (실전: H0STCNI0 키=HTS ID, 모의: H0STCNI9 키=계좌번호)
- Heartbeat 감시 (30초 미수신 시 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES 복호화용 iv/key 수신 및 저장
- 구독 한도 초과 시 에러 대신 경고 + 건너뜀

### handler.py — 메시지 처리
- 파이프(|) 구분 메시지 파싱
- 실시간 체결가(H0STCNT0/H0UNCNT0/H0NXCNT0): 현재가, 시가, 등락률 추출 → RiskManager.on_tick 콜백 (세 TR_ID 모두 동일 메시지 포맷이라 단일 파서로 처리)
- 체결통보(H0STCNI0/H0STCNI9): AES-256-CBC 복호화 → **계좌번호 필터** → OrderEngine.handle_execution_notice 콜백
- NXT 장운영정보(H0NXMKO0): 보드 전환 이벤트 → `register_board_handler`로 등록한 콜백(Phase 3 SessionTracker) 전달. KIS 명세 필드 미기재로 운영 데이터 기반 확정
- 체결통보 필드 매핑 (^ 구분): [0]HTS ID, **[1]계좌번호(8자리)+상품코드(2자리)**, [2]주문번호, [3]원주문번호, [4]매도매수구분, [5]정정구분, [6]주문종류, [7]주문조건, **[8]종목코드**, [9]주문수량, [10]체결단가, [11]체결시간, [12]거부여부, [13]체결구분(1:접수,2:체결), [14]?, [15]?, [16]체결수량, [17]고객명, [18]종목명
- 계좌 필터: `fields[1]`이 `settings.kis_account_no`로 시작하지 않으면 무시 (실전 H0STCNI0은 동일 HTS ID에 묶인 타 계좌 통보가 함께 푸시되므로 필수)

## WebSocket 메시지 포맷
```
수신: 0|H0STCNT0|001|005930^...^현재가^...
        │  │       │    └ 데이터 (캐럿 구분)
        │  │       └ 건수
        │  └ TR_ID
        └ 암호화 여부 (0: 평문, 1: 암호화)
```

## 구독 종류

| TR_ID | 용도 | 구독 키 | 비고 |
|-------|------|---------|------|
| H0UNCNT0 | 실시간 체결가 (KRX+NXT 통합) | 종목코드 | 현재 사용 — `scanner.TICK_TR_ID`. NXT 거래도 즉시 반영 |
| H0STCNT0 | 실시간 체결가 (KRX 단독) | 종목코드 | 메시지 포맷 H0UNCNT0과 동일. 호환성 유지 |
| H0NXCNT0 | 실시간 체결가 (NXT 단독) | 종목코드 | 메시지 포맷 동일 |
| H0NXMKO0 | NXT 장운영정보 | 시장구분 | Phase 3 SessionTracker가 보드 전환 이벤트로 사용 (운영 데이터로 필드 확정) |
| H0STCNI0 | 체결통보 (실전) | HTS ID | KRX/NXT/SOR 모두 같은 TR로 수신, ODER_KIND 필드로 거래소 식별 |
| H0STCNI9 | 체결통보 (모의) | 계좌번호 | KRX 한정 (VTS는 NXT/SOR 미지원) |

## 주의사항
- **체결통보 구독은 매매의 핵심 전제조건** — 미구독 시 포지션 등록 불가 → 손절 불가
- 체결통보는 실전에서 암호화됨 — 반드시 decrypt_aes_cbc 필요
- scheduler.py에서 WebSocket 연결 직후 체결통보 자동 구독
- 구독 종목 변경 시 기존 구독 해제 → 새 구독 등록 순서
- WebSocket URL은 REST와 다름 (ops.koreainvestment.com)
- **실전 체결통보(H0STCNI0)는 HTS ID 단위 푸시** — 동일 HTS ID에 묶인 타 계좌 체결 통보가 같이 들어옴. KIS API 스펙상 구독 단계에서 차단 불가하므로 handler.py에서 `fields[1]` 계좌번호 필터링 필수
