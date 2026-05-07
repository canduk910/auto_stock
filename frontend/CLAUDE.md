# CLAUDE.md — frontend/ (React 대시보드)

React + TypeScript + Vite 기반 트레이딩 대시보드.

## 실행
```bash
npm install        # 의존성 설치
npm run dev        # 개발 서버 (http://localhost:5173)
npm run build      # 프로덕션 빌드 (타입 체크 포함)
npm run lint       # ESLint
```

## 핵심 라이브러리
- TanStack Query: 서버 상태 관리 + 자동 리페치
- TanStack Table: 데이터 그리드 (거래 내역)
- Recharts: 차트 (일별/월별 실적)
- Tailwind CSS v4: 스타일링
- React Router: 페이지 라우팅

## 디렉토리 구조
```
src/
├── api/           # 백엔드 API 호출 함수 (axios 기반)
│   └── client.ts  # axios 인스턴스 (baseURL, 인터셉터)
├── components/    # UI 컴포넌트
├── pages/         # 페이지 (라우트 단위)
└── types/         # TypeScript 타입 정의
```

## 백엔드 연동
- 모든 API 호출은 `api/client.ts`의 axios 인스턴스를 통해 수행
- 응답은 `types/common.ts`의 `ApiResponse<T>` 래퍼로 파싱
- 백엔드 응답 필드명 = TypeScript 타입 속성명 (일치 필수)

## 시각적 컨벤션
- 이익: `#FF3333` (빨강)
- 손실: `#3366FF` (파랑)
- 보합: `#333333` (검정)
- 금액: 천 단위 콤마
- 수익률: 소수점 2자리 + %

## 환경 표시
- 실전: 상단 빨간 배너 "실전 매매 환경"
- 모의: 상단 녹색 배너 "모의투자 환경"
- `/api/trading/status` 응답의 환경 정보로 결정

## ScanMonitor — 20일 신고가 스윙 깔때기
- `donchian_swing` 탭 선택 시 단계별 통과 카운트(코스피200+코스닥150 → 시총 → 일봉 → 신고가 → EMA → 거래량 → ATR → 최종)를 막대 + 숫자로 시각화. 0이 되는 첫 단계가 탈락 원인.
- 데이터 소스: `status.strategies.donchian_swing.scan_stats` (백엔드 `DonchianSwingStrategy.get_scan_stats()`)
- "전체" 탭에서는 한 줄 요약(`유니버스 N1/N → 최종 K`)만 노출, 세부 깔때기는 swing 탭 전용

## LogReports 페이지 (`/log-reports`)
- 매일 정산 직후 OpenAI가 생성한 일일 로그 분석 리포트 조회 (백엔드 `/api/log-reports`)
- 좌측: 영업일 리스트(최근 30일, 신규순) — 클릭 시 상세 표시
- 우측: 총평(summary) + findings 카드(severity high/medium/low + category 칩) + 원본 메트릭(접기/펼치기)
- 우상단 "지금 분석 실행" 버튼 — `POST /api/log-reports/run` (영업일당 1건 UNIQUE)

## Settings 페이지
- 전략 비중 슬라이더: 하한선(빨간 선) = 보유 포지션 매수금액 비율 (`min_weight`, `invested_amount` 필드)
- 파라미터 편집: 각 전략의 `params` 중 number 타입 + PARAM_LABELS에 정의된 키만 표시
- `position_ratio`: "전략 내 종목당 비중" — 전략 할당 자금 기준 (순자산 전체 아님), 예상 매수 금액 헬퍼 텍스트 표시
- `getStrategies` API 매퍼: `total_investment`, `invested_amount`, `min_weight` 필드 포함 필수

## 주문 안전성
- 시작/정지 버튼: ConfirmModal로 이중 확인 필수
- 주문 관련 버튼은 항상 확인 단계 포함 (오발주 방지)

## 타입 수정 시 주의
- `types/` 디렉토리의 타입은 백엔드 `src/models/` pydantic 모델과 1:1 매핑
- 백엔드 응답 구조가 변경되면 여기도 반드시 동기화
- `npm run build`로 타입 체크 확인
