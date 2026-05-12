# L1+L2+L3+L5 — KST 시각 통일 + `_sync_db_from_orders` timezone/중복 체크 보강

**날짜**: 2026-05-12
**컨텍스트**: 005930(삼성전자) 보완 INSERT 결함 추적 결과 → timezone + 시각 표시 일관성 결여 → 한 묶음 처리

L4 (DB DELETE) 는 이미 메인 세션에서 완료 — 재실행 금지.

---

## 행위 목록 (TDD 사이클 입력)

### L1 — `_build_pnl_pairs` 체결시각 KST 변환

A. UTC ISO `"2026-05-11T23:05:47+00:00"` 가 `buy_date="2026-05-12" / buy_time="08:05:47"` 으로 표시된다 (KST 환산)
B. KST ISO `"2026-05-12T08:05:47+09:00"` 가 `buy_date="2026-05-12" / buy_time="08:05:47"` 으로 표시된다 (재변환 안 함)
C. tz-naive ISO `"2026-05-12T08:05:47"` 가 KST 가정 → `buy_date="2026-05-12" / buy_time="08:05:47"`
D. None/빈 문자열 → `buy_date=None / buy_time=None`. sell_ts 동일 규약

### L5 — `_today_kst_iso` + `(ticker, order_no)` 페어 중복 체크

E. `get_today_buy_trades` / `get_today_sell_trades` / `get_today_trades_for_settlement` 의 `.gte("timestamp", ...)` 인수에 `+09:00` 명시 KST timezone 포함
F. `_sync_orders_to_db` 가 같은 ticker 다른 order_no 의 주문은 둘 다 INSERT (위양성 차단)
G. 같은 ticker + 같은 order_no 는 1회만 INSERT (멱등 — 다음 주기 재호출 시 skip)
H. 매도(`sll_buy_dvsn_cd="01"`) 경로도 동일 `(ticker, order_no)` 페어 사용

### L3 — 프론트엔드 시각 표시 일관성

I. `TradeHistoryGrid.formatDate / formatTime` 이 `Asia/Seoul` 강제 사용 — `d.getFullYear()` (브라우저 로컬) 대신 `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ... })` 또는 동등한 KST 추출
J. `LogReports.formatDateTime` 이 `toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })` 사용 (이미 KST 컨벤션 맞춘 옵션 추가)

### L2 — CLAUDE.md 한국시 강제 지침

K. 루트 `CLAUDE.md` "코딩 컨벤션" 섹션에 KST 강제 항목 1줄 추가. `frontend/CLAUDE.md` "시각적 컨벤션" 섹션에 KST 강제 항목 보강

---

## 안전 불변식

- `_build_pnl_pairs` 출력 스키마(buy_date/buy_time/sell_date/sell_time 등 키 + 문자열 형식) 그대로 유지
- `get_today_*` 시그니처/반환타입 변경 금지
- `_sync_orders_to_db` 호출 위치(15분 주기) 유지, 새 분기 추가 없음. 중복 체크가 strict 해질 뿐
- 매수 진입 6자리 숫자 / 사후처리 6자리 영숫자 — 영향 없음
- TradeHistoryGrid 표시 포맷(`yy-mm-dd` / `hh:mm:ss`) 유지, 시각 값만 KST 명시
- LogReports 표시 포맷(`toLocaleString` 기본) 유지, `timeZone` 옵션만 추가

---

## 절대 금지

- git commit/add/push 금지 — 사용자 명시 지시 전까지 워킹 트리에만
- L4 (DB DELETE) 재실행 금지 — 이미 완료
