# 사이클 229 — 행위 분해 (Red 착수 정본)

> 작성: tdd-engineer, 2026-08-28
> 명세 정본: `_workspace/red/cycle229_buy_cutoff_spec.md` (W1~W5)
> 자문 정본: `_workspace/domain_consult/cycle229_vb_1530_single_price.md` (§9 Red 8항)
> 워크리스트: `_workspace/00_URGENT_WORKLIST.md` P1-5
>
> **Red 단계 — 실패 테스트만 작성. 프로덕션 코드 변경 0. 기존 테스트 수정 0.**

---

## 0. 명세를 "검증 가능한 행위"로 자르기

명세 W1~W4 는 4개 축(VB 컷 / momentum 컷 / 분류기 / e2e·AST)인데, 축마다 성격이 다르다.

| 축 | 성격 | 지금 실패해야 하는가 |
|---|---|---|
| W1·W2 시각 게이트 | **신규 행위** (없던 분기) | 예 — 게이트 부재라 돌파 틱이 BUY |
| W3 분류기 | **기존 함수의 입력 커버리지 확장** | 예 — 실측 msg1 이 미매칭 |
| W4-5 매도 폴백 | **W3 의 하류 효과** (분기 재사용) | 예 — 미분류라 폴백 진입 못 함 |
| 청산 무간섭 · 보드 불변 · 기존 변형 매칭 | **보존 계약** | 아니오 — 지금도 통과해야 정상 |

보존 계약을 Red 파일에 섞는 이유는 **Green 이 그것을 깨는지 감시**하기 위해서다. 다만
"지금 통과 = 검증됨" 이 아니므로 §3 에서 *공허 PASS* 를 따로 표시한다(사이클 224 자기 가드
공허성 · 사이클 228 red_result 양식 계승).

---

## 1. 행위 목록 — VB (W1)

`src/engine/strategies/volatility_breakout.py` · 8영역 아님

| # | 행위 | 관측 방법 | 기대 |
|---|---|---|---|
| B1-1 | KST 15:19:59 돌파 틱 → `Signal.BUY` | `check_buy_signal` 반환값 | 게이트 도입 후에도 **불변** |
| B1-2 | KST 15:20:00 돌파 틱 → `Signal.NONE` | 동상 | 신규 |
| B1-3 | KST 15:29:00 돌파 틱 → `Signal.NONE` | 동상 | 신규 |
| B1-4 | **UTC 벽시계 15:20 = KST 익일 00:20** 돌파 틱 → `Signal.BUY` | 동상 | naive 구현 반증기 |
| B1-5 | 컷 틱은 `_prev_price[t][board]` 를 **갱신하지 않는다** | 내부 dict 직접 관측 | 게이트 위치(=`_prev_price` 앞) 뮤테이션 가드 |
| B1-6 | KST 15:25 `check_exit_signal` 정상 발화 | `Signal.STOP_LOSS` | 청산 무간섭 **보존** |
| B1-7 | `[vb_buy_cutoff]` INFO 가 하루 **1행** (컷 2회 → 1행) | caplog | 신규 |
| B1-8 | 날짜가 바뀌면 다시 1행 (총 2행) | caplog + freeze 2일 | **훅 미의존 자기 리셋** |
| B1-9 | 모듈 상수 `BUY_CUTOFF_KST == time(15, 20)` | import | 신규 |
| B1-10 | `DEFAULT_PARAMS` 에 컷 키 미편입 | dict 검사 | DB override 불가 계약 |
| B1-11 | `PARAM_RANGES` / `INT_PARAMS` 에 컷 키 미편입 | import | AI 야간 튜닝 차단 |
| B1-12 | `DEFAULT_TRADABLE_BOARDS == ("main",)` | 클래스 속성 | 보드 축 무접촉 **보존** |

### B1-4 의 설계 근거 (TZ 독립성을 *양방향* 으로 잡는다)

freezegun 은 naive 문자열을 **UTC** 로 동결한다. 따라서

- `freeze_time("2026-08-28 06:20:00")` → `datetime.now(KST).time()` = **15:20:00** / `datetime.now().time()` = 06:20:00
- `freeze_time("2026-08-28 15:20:00")` → `datetime.now(KST)` = **08-29 00:20** / `datetime.now().time()` = 15:20:00

B1-2 는 "naive 면 컷을 **놓친다**", B1-4 는 "naive 면 **엉뚱한 때 컷한다**" 를 각각 잡는다.
한쪽만으로는 `datetime.now().time()` 구현이 절반의 케이스를 우연히 통과할 수 있다.
B1-4 는 KST 00:20 이라는 비현실적 매매 시각을 쓰지만, 이 케이스가 주장하는 것은 시장 시각이
아니라 **게이트가 어느 타임존을 읽는가** 하나뿐이다.

---

## 2. 행위 목록 — momentum (W2)

`src/engine/strategies/momentum.py` · 8영역 아님. W1 동형. prev 상태 필드만 다르다.

| # | 행위 | VB 대응 | 차이점 |
|---|---|---|---|
| B2-1~4 | 경계 3점 + TZ 역방향 | B1-1~4 | 신호 정의가 `_prev_prdy_rate` 기반 |
| B2-5 | 컷 틱이 **`_prev_prdy_rate`** 미갱신 | B1-5 | momentum 은 첫 틱 기록도 이 dict — 게이트가 그보다 앞이어야 한다 |
| B2-6 | 15:25 `check_exit_signal` 정상 | B1-6 | |
| B2-7·8 | `[momentum_buy_cutoff]` 1회/일 + 날짜 리셋 | B1-7·8 | 마커 문자열이 다르다 |
| B2-9~11 | 상수 존재 · DEFAULT_PARAMS · PARAM_RANGES | B1-9~11 | **상수 공유 금지** — 자기 파일에 자기 상수 |

momentum 의 근거는 실측이 아니라 기대값 논증이다(자문 §2-4: 종가 확정 틱의 +29% 는
"상한가 잠금 **실패** 마감" 표본 = 원 가설의 정확한 반대). 자문 §8-4 가 스스로 "표본 없이
내린 판단" 이라고 적었으므로, 테스트도 **행위 계약만** 고정하고 수익성 주장은 하지 않는다.

---

## 3. 행위 목록 — 분류기 (W3)

`src/api/balance.py` · 8영역 아님(8영역의 api 측은 `order.py` 만)

실측 msg1 (전문, `msg_cd=APBK3013`):

```
[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다
```

| # | 행위 | 기대 | 지금 |
|---|---|---|---|
| B3-1 | `is_market_order_disallowed` → **True** | 신규 | False = RED |
| B3-2 | `is_market_closed_rejection` → False | 순서 계약 무교차 | False = PASS |
| B3-3 | `is_insufficient_cash` → False | 상호 배타 | False = PASS |
| B3-4 | `is_insufficient_quantity` → False | 상호 배타 | False = PASS |
| B3-5 | 기존 변형 `[애프터마켓]지정가 및 최유리/최우선지정가 주문만…` 여전히 True | 회귀 보존 | PASS |
| B3-6 | 기존 변형 `시장가호가불가로 주문이 불가합니다.`(APBK1943) 여전히 True | 회귀 보존 | PASS |
| B3-7 | 프리마켓 msg1 의 **이중 매칭**(closed·disallowed 양쪽 True) 보존 | 2026-08-06 계약 | PASS |
| B3-8 | 실측 msg1 은 기존 키워드 2종("지정가 및 최유리" / "최유리/최우선지정가 주문만") 어느 것으로도 매칭 **불가** | 결함 원인 고정 | PASS |
| B3-9 | 신규 키워드 `"단일가매매"` 가 키워드 튜플에 존재 + 실측 msg1 의 연속 부분문자열 | 신규 | RED |
| B3-10 | 정상 안내 문구(`지정가 주문이 정상적으로 접수되었습니다.`) 오탐 없음 | 신규 키워드 부작용 차단 | PASS |

**B3-8 이 B3-1 과 짝을 이룬다.** B3-1 만 있으면 "기존 키워드를 느슨하게 고쳐서" 통과시킬 수
있는데, B3-8 이 그 경로를 차단한다 — 실측 msg1 은 기존 2 키워드로 **구조적으로** 못 잡히므로
B3-1 이 통과했다면 그것은 반드시 신규 키워드의 공로다.

---

## 4. 행위 목록 — 매도 폴백 e2e (W4-5)

`src/engine/order_engine.py::execute_sell` — **수정 대상 아님**. W3 의 하류 효과만 검증한다.

| # | 행위 | 기대 |
|---|---|---|
| B4-1 | 실측 msg1 시장가 매도 거부 → `place_order` 2회(시장가 → `step_down(현재가,5)` **LIMIT**) | RED (현행 3회 재시도, LIMIT 0회) |
| B4-2 | 예외가 호출자로 전파되지 않는다 | PASS (`execute_sell` 는 re-raise 안 함) — "무기록 포기" 가 조용한 이유 |
| B4-3 | 폴백 성공 후 주문번호 매핑 3종 등록 + positions 보존 | RED |
| B4-4 | 프리마켓 msg1 은 **여전히** market_closed 분기(폴백 미진입, `place_order` 1회) | PASS — 순서 계약 e2e 고정 |

⚠️ B4-1 의 Red 는 재시도 3회 × 지수 백오프(1s + 2s)를 타므로 `SELL_RETRY_DELAY` 를 0 으로
monkeypatch 한다. 상수를 건드리는 게 아니라 **테스트 내 대체**다(TDD 원칙: 테스트 1초 초과 금지).

---

## 5. 행위 목록 — AST 가드 (W4-8)

`tests/unit/ast/test_cycle229_ast_cutoff_guards.py`

| # | 가드 | 지키는 것 |
|---|---|---|
| G-1 | VB·momentum `check_buy_signal` 안에 naive `datetime.now().time()` **0건** | 자문 구현 3원칙 #1. BFB `:929`/VCP `:1045` 잔존은 **P2-6 별건 — 이 가드 범위 밖** |
| G-2 | 두 파일 각각 **모듈 레벨** `BUY_CUTOFF_KST == time(15,20)` | 상수 공유 금지 + 클래스/params 안으로 숨지 않음 |
| G-3 | `check_buy_signal` 안에서 `BUY_CUTOFF_KST` 첫 참조 라인 < prev 상태(`_prev_price`/`_prev_prdy_rate`) 첫 참조 라인 | 자문 구현 3원칙 #2. 게이트를 아래로 내리는 뮤테이션 검출 |
| G-4 | 두 전략 파일이 서로를 import 하지 않는다 | 상수 공유 금지(파일 간 결합 회피) |
| G-5 | 게이트 판정문에 인자 있는 `datetime.now(<tz>)` 동반 | naive 금지의 **양성** 짝 (G-1 은 음성) |

### G-3 의 비-공허성 검토 (사이클 224 교훈)

사이클 224 의 AST 가드는 기준선을 **호출 위치 자신** 에서 유도해 정의상 항상 참이었다.
G-3 의 기준선은 `_prev_price` / `_prev_prdy_rate` 의 첫 참조 라인 — **게이트 위치와 독립**이다.
게이트를 그 아래로 옮기면 부등식이 즉시 뒤집힌다. 상수가 아예 없으면 "참조 0건"으로 FAIL 한다
(조용한 vacuous PASS 없음).

---

## 6. 범위 밖 (이번 사이클에서 **하지 않는 것**)

- `execute_buy`(8영역) 미접촉 — 시간 게이트가 매수를 원천 차단하므로 분류 분기 수정 불요(자문 §5-3 (b) 기각).
- G-REJECT-1(콜백 re-raise) 불변 — 예외를 만드는 **원인**을 없애는 것이지 전파 설계를 바꾸는 게 아니다.
- VB `DEFAULT_TRADABLE_BOARDS` 불변 · `check_exit_signal` / `check_force_clear` / 15:20 강제청산 diff 0.
- BFB `:794`/`:929` · VCP `:1045` naive 시각 — **P2-6**.
- momentum `krx_open` 보드의 09:00 시가 단일가 확정 틱 노출 — 자문 §4 "범위 밖 참고 1건", 별도 사이클.
