# 사이클 229 명세 — VB·momentum 매수 컷 15:20 + [단일가매매] 분류기 편입 (P1-5)

> 작성: team-leader, 2026-08-28 11:2x KST
> 자문 정본: `_workspace/domain_consult/cycle229_vb_1530_single_price.md` (전제 정정 1건 포함 — 필독)
> 사용자 결정 (2026-08-28): 자문안 4건 일괄 채택 + **15:40 이후 cycle228 과 동반 푸시**(별도 커밋).

## 전제 (자문이 정정한 사실 — 구속력)

- 15:20~15:30 은 연속매매가 아니라 **KRX 장후 동시호가(종가 단일가)** — `session.py::is_call_auction_now` 가 이미 그렇게 판정(사이클 162/182). 평가할 틱이 구조적으로 희박하나 **종가 단일가는 시장가 호가를 접수**한다(15:20 강제청산 시장가 매도가 작동 중인 것이 방증) ⇒ 15:2x VB 시장가 매수는 거부가 아니라 **종가 체결 → 오버나잇**(우연한 안전판 없음).
- 15:30:0x~2x 9건(8/20~8/27)은 랜덤엔드 확정 종가 1틱이 15:19 마지막 연속체결가 대비 점프해 edge-crossing 을 만든 것. 그 시각 시장가는 `[단일가매매]` 변형으로 거부 → `execute_buy` 미매칭 `raise`(:487) → on_tick 탈출 → **매일 WS 재연결 1~4회**.

## 행위 목록

### W1. VB 매수 컷 15:20 (`volatility_breakout.py` — 8영역 아님)

- **모듈 상수** `BUY_CUTOFF_KST = time(15, 20)` — DB override 불가(OVERNIGHT 금지는 토글로 뚫리면 안 되는 규칙). PARAM_RANGES/DEFAULT_PARAMS 미편입.
- `check_buy_signal` **최상단**(모든 상태 변경 — 특히 `_prev_price` read/write — *이전*): `datetime.now(KST).time() >= BUY_CUTOFF_KST` → `Signal.NONE`.
  - ⚠️ **naive `datetime.now().time()` 금지** — BFB `:929`/VCP `:1045` 의 naive 는 P2-6 등재 결함이지 선례가 아니다. 선례는 kojiro(KST 명시).
  - 게이트가 `_prev_price` 앞이어야 하는 이유(자문 구현 원칙 2): 뒤에 두면 종가/예상체결가가 baseline 이 되어 장중 재시작 시 거짓 미돌파를 만든다. **컷 틱은 `_prev_price` 를 갱신하지 않는다** — 뮤테이션 가드 대상.
- 관측 `[vb_buy_cutoff]` INFO **1회/일**(첫 차단 시, 날짜 키 자기 리셋 — 훅 미의존): 사이클 224 교훈. 차단 누적 카운터는 불요(단순 시각 게이트).
- 청산 경로 무간섭 — `check_exit_signal`·15:20 강제청산·보드 흡수 마진(15:39:59 MAIN)은 byte 불변.

### W2. momentum 동일 15:20 컷 (`momentum.py` — 8영역 아님)

- W1 동형(상수 공유 금지 — 전략별 자기 상수, 파일 간 결합 회피. 값 동일 15:20). `[momentum_buy_cutoff]` 1회/일.
- 근거: 종가 확정 틱의 +29% 는 "돌파 순간"이 아니라 **상한가 잠금 실패 마감** 표본(momentum 이 30% 상한가를 제외하므로 이 틱이 잡는 것은 원 가설의 정확한 반대). 표본 0 영역이라 실측 차이 ≈0.

### W3. `[단일가매매]` 변형 분류기 편입 (`src/api/balance.py` — 8영역 아님)

- `_MARKET_ORDER_DISALLOWED_KEYWORDS` 에 **연속 부분문자열** `"단일가매매"` 추가(실측 msg1 = `[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다` — 기존 키워드 "지정가 및 최유리"는 중간 삽입어로 불성립했던 그 변형).
- **주 실익 = 매도**: 미분류 매도 거부는 3회 재시도 후 **무기록 포기**(`order_engine:815~828`, TTL 미등록)라 랜덤엔드 창 청산 실패가 기록조차 안 됐다. 편입 시 `step_down` 지정가 폴백(단일가 세션 유효 주문) + 30초 TTL 경로를 탄다.
- 매수 잔여 도달 경로 = LTV 야간(`nxt_tradable=False` 다운그레이드 → 시간외단일가)뿐 — W1/W2 가 VB·momentum 을 차단한 전제에서 지정가 폴백은 수용 가능(자문 Q3).
- **분류 순서 계약 불변**: `is_market_closed_rejection` 먼저 검사(기존 이중 매칭 계약) — 이 변형은 장운영 키워드 부재라 교차 없음을 테스트로 고정.
- ⚠️ D+1 감시: 매도 지정가 미체결 잔존 → `_selling` 좀비 가능성 — 기존 180s `[selling_reconcile]` 재대조 훅이 흡수(자문 반례 5).

### W4. 회귀·AST (자문 Red 8항)

1. 경계 3점: 15:19:59 통과 / 15:20:00 컷 / 15:29:00 컷 (VB·momentum 각).
2. TZ 독립성: `TZ=UTC` 환경에서도 KST 15:20 기준(freezegun UTC 시각으로 검증) — naive now 였다면 깨질 케이스.
3. 게이트 위치 뮤테이션: 컷 틱이 `_prev_price` 미갱신(컷 후 15:19 재평가 시나리오는 비현실이나 장중 재시작 baseline 오염 차단 계약).
4. 청산 무간섭: 15:25 의 `check_exit_signal` 정상 발화.
5. raise 소멸 e2e: 실측 msg1 전문으로 `KisApiError` 를 만들었을 때 `is_market_order_disallowed` True + 매도 폴백 경로 진입(execute_sell 레벨 — respx/mock).
6. 분류기: msg1 **전문** 매칭 + `is_market_closed_rejection` 비매칭(순서 계약) + `is_insufficient_*` 비매칭.
7. `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일 cap + 날짜 리셋.
8. AST: 두 전략 `check_buy_signal` 에 naive `datetime.now().time()` 신규 유입 0(기존 BFB/VCP 잔존은 P2-6 별건 — 이번 가드는 VB·momentum 한정) + `BUY_CUTOFF_KST` 상수 존재 + DEFAULT_PARAMS/PARAM_RANGES 미편입.

### W5. 문서 (커밋 시)

- 워크리스트 P1-5 종결 + CLAUDE.md 하네스 표 1행(최고 행 제거) + HARNESS_CHANGELOG verbatim + strategies/CLAUDE.md VB·momentum 행에 컷 명기.

## 제약

- **8영역·scheduler.py·session.py·order_engine.py diff 0** (수정 = volatility_breakout.py / momentum.py / balance.py / 테스트 / 문서 한정. balance.py 는 8영역 아님 — 8영역의 api 측은 order.py 만).
- G-REJECT-1(콜백 re-raise) 불변 — 없애는 것은 예외의 원인이지 전파 설계가 아니다.
- VB `DEFAULT_TRADABLE_BOARDS=("main",)` 불변. 커밋·푸시는 team-leader — 15:40+ cycle228 동반.
- cycle228 커밋 3개(4e7b302/0056db7/e139c42)와 파일 무겹침(BFB/VCP 무접촉) → sha 핀 무관.
