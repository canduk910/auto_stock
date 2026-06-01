---
name: trading-dashboard
description: "주식 자동매매시스템의 React.js 트레이딩 대시보드 UI를 구현하는 스킬. 구동 관리(시작/정지 + 이중확인), 매매 실적(원금/평가금/수익률 + 차트), 거래 내역(페이징 그리드), 잔고 조회(실시간) 화면을 포함한다. 대시보드, 화면, UI, 모니터링, 차트, 프론트엔드 등을 언급하면 이 스킬을 사용할 것."
---

# 트레이딩 대시보드 스킬

React.js 기반 트레이딩 대시보드를 구현한다. 백엔드 FastAPI 서버와 REST API로 통신한다.

## 프로젝트 구조

```
frontend/
├── package.json
├── src/
│   ├── App.tsx
│   ├── api/                  # API 호출 함수
│   │   ├── client.ts         # axios/fetch 인스턴스 (baseURL 설정)
│   │   ├── trading.ts        # /api/trading/* 호출
│   │   ├── balance.ts        # /api/balance/* 호출
│   │   ├── history.ts        # /api/history/* 호출
│   │   └── performance.ts    # /api/performance/* 호출
│   ├── components/
│   │   ├── ControlPanel.tsx   # 시작/정지 + 상태 인디케이터
│   │   ├── PerformanceCard.tsx # 실적 요약 카드
│   │   ├── ProfitChart.tsx    # 일별/월별 차트
│   │   ├── TradeHistoryGrid.tsx # 거래 내역 테이블
│   │   ├── BalanceTable.tsx   # 잔고 테이블
│   │   └── ConfirmModal.tsx   # 이중 확인 모달
│   ├── types/
│   │   ├── trading.ts        # 매매 관련 타입
│   │   ├── balance.ts        # 잔고 관련 타입
│   │   └── common.ts         # 공통 타입 (페이징 등)
│   └── pages/
│       ├── Dashboard.tsx      # 메인 대시보드 (요약)
│       ├── History.tsx        # 거래 내역
│       └── Settings.tsx       # 설정
```

## 백엔드 API 엔드포인트 매핑

| 화면 | 엔드포인트 | Method | 용도 |
|------|-----------|--------|------|
| 구동 관리 | `/api/trading/start` | POST | 자동매매 시작 |
| 구동 관리 | `/api/trading/stop` | POST | 자동매매 정지 |
| 구동 관리 | `/api/trading/status` | GET | 현재 상태 조회 |
| 매매 실적 | `/api/performance/summary` | GET | 원금, 평가금, 수익률 |
| 매매 실적 | `/api/performance/daily` | GET | 일별 수익률 (차트) |
| 매매 실적 | `/api/performance/monthly` | GET | 월별 수익금 (차트) |
| 거래 내역 | `/api/history?page=&size=` | GET | 페이징된 거래 내역 |
| 잔고 조회 | `/api/balance` | GET | 예수금 + 보유종목 |

> 실제 응답 스키마는 backend-dev에게 SendMessage로 확인한다. 위 경로는 초기 설계안.

## 화면별 구현 가이드

### 1. 구동 관리 (ControlPanel)
- [시작] 클릭 → ConfirmModal("자동매매를 시작하시겠습니까?") → 확인 시 POST
- [정지] 클릭 → ConfirmModal("정지하시겠습니까? 미체결 주문이 있을 수 있습니다.") → 확인 시 POST
- 상태 인디케이터: `useQuery`로 `/api/trading/status` 주기 폴링 (5초)
- 상태값: `RUNNING`(초록), `STOPPED`(빨강), `STARTING`(노랑)

### 2. 매매 실적 (PerformanceCard + ProfitChart)
- 카드: 투자 원금 | 현재 평가금 | 누적 수익금 | 수익률(%)
- 수익률 색상: 양수(빨강), 음수(파랑), 0(검정)
- 금액 포맷: 천 단위 콤마, 원 단위
- 차트: Recharts 또는 Chart.js, 기간 선택 드롭다운

### 3. 거래 내역 (TradeHistoryGrid)
- TanStack Table, 서버사이드 페이징
- 컬럼: 일시 | 종목 | 매수/매도 | 단가 | 수량 | 정산금액 | 상태
- 상태 뱃지: COMPLETED(초록), PENDING(노랑), PARTIAL(주황)
- 필터: 기간 DateRangePicker, 매수/매도 셀렉트, 종목 검색
- 기본 정렬: 일시 내림차순

### 4. 잔고 조회 (BalanceTable)
- 상단: 예수금 (큰 숫자)
- 테이블: 종목명 | 보유수량 | 매입가 | 현재가 | 평가손익 | 수익률(%)
- `refetchInterval: 10000` (10초마다 자동 갱신)
- 손익 색상 적용

## 시각적 컨벤션
- 이익: `#FF3333` (빨강)
- 손실: `#3366FF` (파랑)
- 보합: `#333333` (검정)
- 금액: 천 단위 콤마, 소수점 불필요 시 정수 표시
- 수익률: 소수점 2자리, % 단위

## 환경 표시
- 실전: 상단 고정 배너 `🔴 실전 매매 환경` (빨간 배경)
- 모의: 상단 고정 배너 `🟢 모의투자 환경` (초록 배경)
- `/api/trading/status` 응답에 environment 필드 포함
