# 🔴 최우선 과제 — BFB·VCP 매수 전면 차단 (2026-08-25 확정)

> **이 파일이 현재 최우선 작업 지시서다.** 새 세션은 다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.
> 근거 보고서: https://claude.ai/code/artifact/75081207-15a8-4d43-9574-2352dae049b2
> 작성 시점 상태 = 미푸시 커밋 0 · 워킹트리에 미커밋 cycle221 잔류.
>
> **✅ P0-1 종결 (2026-08-28 사이클 228 게이트 전환 — 커밋 A `4e7b302` + B, 배포 대기)**
> 사이클 227 배포(a7245af) → 이틀 관측 would_pass 0/5 → 래치 선행 확정 → 사이클 228 이
> 게이트를 tick_volume 실측 + 충족 래치 + 추격 상한으로 전환(**매수 개방**, 비중 현행).
> 228-B = `_effective_setup` 구조 레벨 stamp 우선 복원(별도 커밋, D+1 귀인 분리).
> 다음 액션 = **15:30 NXT 애프터 이후 푸시**(KRX 장중 자제) → D+1 관찰(첫 체결·청산 경로
> 첫 실가동·`latch_age_sec`·`[setup_structure_conflict]`·진입 임계 재튜닝 금지 N=10).
> ⚠️ `[*_vol_gate_observe]` 마커 은퇴 — 08-28 전후 로그 같은 grep 합산 금지.
> tester 조건부 GO(`_workspace/test_report_cycle228.md`, 결함 6) → 228-C 로 D-1(C-6 가드
> 공허화, 뮤테이션 실증)·D-2(죽은 필드+invariant 경고 1회/일 cap)·D-3(release cap reason 축)
> 시정 완료. **이관 잔여**: D-4(read 예외 debug 단독 — no_data WARNING 동반이라 LOW 수용) ·
> D-5(대시보드 래치 상태 미노출 — 후속 사이클 후보, `get_targets_status` 키 추가만으로 가능).

---

## 🔴 월요일(2026-08-31) 아침 최우선 — `257720` VB 주말 오버나잇 (cycle232 자문 부속 발견)

`257720`(실리콘투, VB 2주/51,050원, 08-28 09:15 매수, `status=PARTIAL`)이 **주말 오버나잇 보유 중**.
VB 는 15:20 전량청산 전략이라 **오버나잇 손절 규약이 설계에 없다** = 무통제 포지션(계좌 3.9%).
1차 판단 = cycle229 가 시정한 `[단일가매매]` 미분류 매도 거부(3회 재시도 후 **무기록** 포기)의
시정 **전** 마지막 희생자 — 08-28 15:20 청산 시도가 cycle229 배포(15:40+) 직전이었다.

**사용자 결정(08-29): 월요일 09:00 즉시 청산 — 절차 정본 = `_workspace/monday_0831_guide.md`.**

**⚠️ 08-29(토) 로그 실측으로 자문 §5 가설 반증** — 15:20 강제청산은 정상 발화했고("대상:
['035420','257720']"), 실패 원인은 `[단일가매매]` 가 아니라 **APBK0400 "주문 가능한 수량
초과" ×3 → CRITICAL**. 근본 = BUY `0000411400` 이 **PARTIAL 2주** 체결인데
`positions.quantity=3`(주문수량) 잔존 → 3주 매도 시도 → 실보유 2주라 거부.
**월요일 15:20 자동 재청산도 같은 이유로 재실패 확정** → `manual-sell {"ticker":"257720",
"quantity":2}` (실보유 수량!) 이 유일 확실. 사후 = positions 잔량 1 유령 정리 확인.

**신규 결함 2건**:
- **N1 — ✅ cycle235 시정 완료(08-29, 커밋 대기)**. 근본 = handler 가 체결수량을
  `fields[16]`(ODER_QTY 주문수량)으로 오독(주석이 KIS 정본과 반대) — 단일 전량 체결에선
  잠복, 부분/분할에서 positions 과대. 시정 = ①`fields[9]`(CNTG_QTY) 정본 전환 ②엔진
  overrun 클램프(`[fill_qty_overrun]`, 증분 동반 캡 = 손익 정합) + `quantity<=0` drop
  (`[fill_qty_zero]`) ③강제 UPDATE WHERE PENDING+PARTIAL 포괄(N1-b). 적대 검증 확증 4
  전부 시정. 8영역 승인 = handler·order_engine 한정(sha 핀 4가드, 커밋 시 자기소멸).
  **후속 후보(행위 결정 사안)** = 전량 체결 분기의 잔여취소 타이머 해제 + 1차
  update_trade_status 의 PARTIAL 포괄(C235-V2) · `_completed_orders` 일일 리셋 확인(C235-R3).
- **N2 (잔여)** APBK0400 이 `is_insufficient_quantity`(APBK1234+"부족" 키워드) 미매칭 →
  3회 재시도 낭비 + positions 정리·reconciliation 미발동(`balance.py` 분류기 = 비8영역.
  KIS 정본으로 APBK0400 의미 범위(매수 문맥 겸용 여부) 확인 선행). N1 시정으로 유령 수량
  발생원 자체는 닫혔으나 분류기는 독립 결함 — cycle236 후보.

---

## cycle232 · 리스크 통제 3의제 검토 — ✅ 사용자 결정 완료 (2026-08-29, 구현 대기)

터틀 원전 대사 보고서(https://claude.ai/code/artifact/5cd3fe2d-e405-4911-866c-74f03c1bf3a2)의 액션 1·2·3 을
검토(사실 조사 3축 + domain-consult `_workspace/domain_consult/cycle232_risk_control_review.md`) 후 **전부 자문 권고안 채택**.

| 의제 | 결정 | 구현 |
|---|---|---|
| **G3′ 계좌 통합 통제** | **자문 권고 패키지 착수** — ⓪척도 병기(프록시+실효, 관찰 전용) ①SOFT Σ상한 다크런치(관측 4%/차단 6%, 임계 비활성→2주 후 DB 활성, HARD 금지). Σ상한=순간 게이트/드로다운=일 래칫 **이원 설계**(D1). fail-open+LOUD(D2). 1주 폴백 notional 초과는 **관측만** `[oversized_fallback]`(D3). 드로다운 3층은 **다음 사이클**(입출금 보정 선행) | **✅ cycle233 구현 완료 (2026-08-29) — 커밋·배포 대기.** 스펙 `_workspace/red/cycle233_account_risk_spec.md` · 적대 검증 21→확증 6 전부 시정(HIGH 2 = 자기 가드 공허, 뮤테이션 실증) · 백엔드 **5,818 PASS** · 8영역+scheduler diff 0(라인 상한 가드로 감시자를 자기 종료 루프로 설계). 활성화 = 2주 관측 후 DB `account_risk_block_pct=6.0` 한 줄 |
| **G2 역지정가** | **보류 + 대체 조치** — 착수 게이트 3(스탑지정가 `ORD_DVSN` 스펙 확정 · 모의/소액 실주문 검증 · T1 자본) AND 충족 전 도입 금지. 근거 = KIS 는 스탑**지정가**만(`CNDT_PRIC` 정본) — 갭 관통 미체결 = Defect 2 재현 + 다일 잔존 주문의 체결통보 오귀속("momentum" INSERT 경로). 지금 할 것 = tick blind 총시간/일 계측 + 부팅 직후 청산 평가 우선순위 확인 + **D6 운영 규약 승격**(보유 포지션 有 시 09:00~15:30 push 금지) | 대체 조치 진행(08-29): **D6 승격 완료**(CLAUDE.md 운영 가이드) · **청산 우선순위 확인 완료** — 청산 평가는 tick 기반(`risk.on_tick` 첫 tick 즉시)이라 매수 스캔(09:30) 비의존 + 보유는 07:59 HIGH 사전구독 = 현행 충족, 실사각은 재구독 지연의 tick blind 자체 → **✅ ① tick blind 계측 완료(cycle234, 08-29)** — `uptime_monitor.py`(60s 하트비트 + `[tick_blind_boot]` + 20:10 `tick_blind` metrics). **G2 대체 조치 3건 전부 종결.** G2 재검토 = `market_blind_secs_total` 주간 분포 실측 후. 재검토 트리거 = `_pending_next_day_clear` 미집행 실측 1회 |
| **G1 risk_pct 0.5→1.0%** | **보류 — T2 재분류.** 해제 게이트(AND) = net≥500만 ∧ kojiro·donchian 각 N≥20 TE>0 ∧ 상관군 캡 활성(`max_open_risk_pct` 4.5→9 동반 — 로드맵 규칙 4). 근거 = 체결 ~70% 1주 폴백 무관 + 효과 비단조(저가주 편향) + kojiro 동시 유닛 4.5→2.25 반토막 | 코드 변경 0 — 문서 등재만 |

**자문의 전제 정정 3**(보고서 반영 완료): ①"1유닛 고정=R15 초과달성" 불성립(1주 폴백이 4유닛 초과 생성)
②리스크 척도 이원(프록시 60,713 vs 정밀 미측정 — 월요일 장중 `GET /api/portfolio/risk` 실측 필요)
③머신 슬립은 로컬 사건(EC2 사각 과대평가 금지).

---

## P0-1 · BFB·VCP 가 존재하지 않는 키를 읽어 매수가 구조적으로 불가능하다

### ✅ 시정 현황 (2026-08-25 사이클 227 — Stage 0 구현 완료·미커밋)

- **결정 (사용자, 2026-08-25)**: ① 방향 **A-raw** + 8영역 승인(handler.py·risk.py 한정)
  ② **Stage 0 관측 우선** — 게이트 행위 변경 0, 배관+`would_pass` 로그만 ③ 비중 현행 유지
  (BFB 0.15/VCP 0.10 — 다크런치는 Σ 정규화 위험 이전이라 반대, 자문) ④ P0-2 동반.
- **자문 판정** (`_workspace/domain_consult/bfb_vcp_acml_vol_gate.md`): 방향 B(전일 확정치)
  **폐기** — 전일은 플래그/베이스 수축 구간이라 통과 확률 ~0 = 결함 재생산. **게이트 전환 시
  P1-3 충족 래치 동반 필수** — 래치 없이 A-raw 만 켜면 BFB 통과율 0% 예상(역선택).
- **구현** (명세 `_workspace/red/cycle227_acml_vol_stage0_spec.md`, 검증
  `_workspace/test_report_cycle227.md` **GO**): handler `fields[13]`(ACML_VOL) 파싱 →
  `on_tick(*, acml_vol=-1)` → 신규 leaf `src/engine/tick_volume.py`(KST 날짜 자기 리셋,
  미관측 None — sentinel 0 금지). BFB/VCP 게이트 **직전** 관측 훅
  `[bfb_vol_gate_observe]`/`[vcp_vol_gate_observe]` (cap 1회/(ticker,outcome)/일 +
  `_scan_stats` 3카운터). **기존 게이트 블록 byte 불변**(AST-2 봉인) — 매수는 여전히 차단.
  백엔드 5,617 PASS/실패 0.
- **게이트 전환 판정 기준** (1~2영업일 관측 후): 주 3건↑ would_pass = 전환 진행 /
  **0건 = P1-3 래치 선행 필수** / 일 10건↑ = 스코프 불일치 등 재조사.
- **✅ 관측 결과 (2026-08-26~27 이틀 실측, 2026-08-27 16:00 판정)**:
  배관 정상 — 게이트 평가 5회 전부 실측 acml_vol 관측(no_obs **0**), `observe_failed` 0, ERROR 0(cycle227 기인분).
  **would_pass = 0/5** ⇒ 판정 기준상 **P1-3 충족 래치 선행 확정**(자문 예측 그대로 — A-raw 단독은 역선택).
  정량 근거 = 관측치/임계 비율: 280360 8%(09:08) · 257720 19%(09:19) · 161890 25%(09:26) ·
  001450 40%(10:00) · **357780 70%(12:25)** — 시각이 늦을수록 임계에 접근 = 래치(완주 후 재평가 유지) 도입 시
  통과 발생이 정량적으로 예고된다. 컨텍스트 = 8/26 돌파 1차 감지 247 vs retention 완주 4(진동이 완주를 깎음 — P1-3 동일 뿌리).
  VCP 는 후보 0(final_prepared=0)이라 관측 0 — 자문 예측 범위("몇 주 무체결 가능"), 관측 계획은 BFB 중심 유지.
  Stage 0 불변식 확인 = BFB·VCP 8/26 이후 체결 **0건**(게이트 byte 불변 정상 작동).
- **전환 사이클 의무**: 은폐 테스트 3파일 손주입 → tick_volume 주입 의미 전환(주석 마커
  11곳) + AST-2 pin 의미 전환 + 8영역 sha 핀 4항목 자기소멸 확인 + 비중/디리스크 재확인.
- 인지된 노이즈원(자문 §B): H0UNCNT0 통합 누적(NXT 프리 포함) vs 일봉 J(KRX 단독) 스코프
  불일치 + 다중 레코드 프레임 첫-레코드 과소 계상 — 정합화는 행위 변경이라 별도 사이클.

### 사실 (직접 재확인 완료)

```python
# src/engine/strategies/bull_flag_breakout.py:846-850
info_price    = ticker_prices.get(ticker, {})
acml_vol      = int(info_price.get("acml_vol", 0) or 0)              # ← 항상 0
vol_threshold = int(info["flag_avg_volume"] * breakout_volume_mult)  # ← 항상 ≥ 1
if acml_vol < vol_threshold:
    return Signal.NONE                                                # ← 무조건 실행
```

`src/engine/strategies/vcp_breakout.py:955-961` 동형.

- `scanner.ticker_prices` 에 값을 넣는 **유일한 대입부**는 `src/engine/risk.py:397` 이고
  **4키만** 쓴다 — `current_price` / `open_price` / `change_rate` / `prdy_ctrt`.
- **`acml_vol` 을 `ticker_prices` 에 쓰는 코드가 전체 소스에 없다.**
  WS 핸들러(`src/realtime/handler.py`)도 체결 payload 의 누적거래량 필드를 파싱하지 않는다.
- `prepare()` 가 `flag_avg_volume > 0` 을 강제하므로 임계는 항상 1 이상
  (2026-08-25 실측 48건 = 12,775 ~ 3,628,183).
- 라이브 API 응답 키 출현: `acml_vol` **0회** vs `current_price` **115회**.

⇒ `0 < threshold` 가 **항상 참** ⇒ `check_buy_signal` 이 **구조적으로 `Signal.BUY` 를 반환할 수 없다.**

### 실측 증거

- 7전략 중 이 키를 읽는 **두 전략만 정확히 전 기간 체결 0건** (BFB 0 / VCP 0, 나머지 31~203).
- 2026-08-25 BFB: 후보 **48건** 준비, retention **21회 이상 완주**, 매수 신호 **0**.
  완주 경로(`:829` pop)가 무로그라 그동안 보이지 않았다.
- `CLAUDE.md` 의 기존 귀인 **"BFB·VCP 체결 0 = 진입 조건 미통과 탓"은 반증됐다.**
  조건은 오늘 하루만 21회 이상 충족됐다.

### ⚠️ 왜 지금까지 안 잡혔나

**회귀 테스트가 결함을 은폐하고 있다.** 아래 테스트들이 `ticker_prices` 에 `acml_vol` 을
**손으로 주입**해서, 테스트는 통과하는데 프로덕션은 절대 매수하지 못한다.

- `tests/unit/engine/strategies/test_bull_flag_breakout.py` (:118-124, :147-150, :196-197, :209-210)
- `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py` (:59-60, :82-83, :109-110)
- `tests/unit/engine/strategies/test_vcp_breakout.py` (:145, :167, :215, :228)

**시정 시 테스트도 반드시 함께 고친다.** 그러지 않으면 시정이 검증되지 않는다.

### 시정 방향 (택1 또는 병행)

**A. 실시간 누적거래량을 흘린다**
핸들러가 체결 payload 의 누적거래량을 파싱해 `on_tick` **키워드 인자**로 전달
(사이클 222-a 의 `day_high` 가 정확히 같은 패턴 — 그 선례를 따르라).

> ⚠️ **`ticker_prices` 에 주입 금지.** `donchian_swing.py` 가 같은 dict 에서 고가 키를 읽고 있어
> (`daily_high = max(stck_hgpr, high_price, current_price, open_price)`),
> 키가 채워지면 `ext_pct` 과열 가드가 켜져 **donchian 매수 행위가 바뀐다.**
> `risk.py` 의 관련 주석과 AST 가드가 이미 이 커플링을 경고하고 있다.

**B. 컷을 전일 확정치 기준으로 재정의**
`stock_master.raw.acml_vol` / `stock_master_daily` 기준. 장중 누적 vs 일평균 비교는
09:05 시점엔 구조적으로 불리하다(하루가 시작도 안 했는데 일평균과 비교).

### 🚨 배포 전 반드시 결정할 것

**이걸 고치면 두 전략(비중 합 25%)이 갑자기 매수를 시작한다.**
실체결 표본이 **전 기간 0건**이라 검증된 적이 없는 전략이 한 번에 열린다.

- 한 번에 열 것인가, **다크런치(비중 극소)로 관찰부터** 할 것인가?
- ⚠️ 비중을 **0 으로 내리지 말 것** — `registry.enabled()` 이탈로 손절 평가가 정지한다
  (`enabled` 축 독트린, 아래 참조).
- 체결 확보 전까지 **진입 임계 재튜닝 금지** — 표본 해상도가 파괴된다.

---

## P0-2 · stale universe 가드가 후보 40%를 당일 영구 축출한다

### ✅ 시정 현황 (2026-08-25 사이클 227 — 구현 완료·미커밋)

안전조건 소스를 진짜 당일 누적으로 교체: ① tick 관측(`tick_volume`) 우선 ② 부재 시
`inquire_acml_vol`(FHKST01010100, 화이트리스트 기존재 — FHKST01010300 응답엔 `acml_vol`
부재 확인) REST 폴백 ③ 둘 다 부재 → **제외 보류**. `[universe_excluded]` 에
`acml_vol=… vol_source=tick|rest` 병기. 임계 10,000·보유/익일청산 절대 보호 불변.
**✅ D+1·D+2 실측 확증 (2026-08-27)**: 축출 **85건(8/25) → 1건(8/26) → 0건(8/27)**.
8/26 유일 1건(004800)은 `vol_source=tick acml_vol=3,442` = 진짜 저유동 — 가드가 설계
의도("거래가 실제로 빈약한 종목만 축출")대로 복원됐다. BFB 후보 구독 상실 축도 소멸
= would_pass 관측이 "게이트 탈락" 단일 축으로 해석 가능해졌다.

### 사실

- 2026-08-25 BFB 후보 48 중 **20건(41.7%) 미구독**.
- 원인은 슬롯 부족이 **아니다**(아래 반증 참조). `_universe_excluded_today` 축출이다.
- `[universe_excluded]` 로그 46건 중 이 20건 전부 매칭 (`reason=stale_6plus_low_volume`, ~10:01,
  `today_volume` 254~6,197).
- 필터링 지점 = `src/engine/scheduler.py:1740-1745`
  (`if excluded: tickers = [t for t in tickers if t not in excluded]`).
- **BFB·VCP 는 `_SWING_POLL_STRATEGIES` 비멤버**라 REST 폴 보강이 없다
  (`scheduler.py:144` = `("donchian_swing", "kojiro")`).
  ⇒ **미구독 = 매수 평가 완전 상실**(donchian/kojiro 는 60초 REST 폴이 받쳐준다).

### 근본 결함

가드의 "거래량 빈약" **안전조건이 실질 무력화**돼 있다.
`today_volume` 이 최근 ~30 체결의 합이라 임계 `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 을
사실상 항상 충족한다 ⇒ 가드가 **"스테일 6회 → 무조건 축출"** 로 퇴화했다.

### 시정 방향

안전조건을 **진짜 당일 누적거래량**으로 교체(`stock_master.raw.acml_vol` 또는 `FHKST01010100`).
대량 동시 축출 버스트는 배관 장애 신호로 보고 별도 판단.

---

## P1 · 관측을 가리거나 자원을 낭비함

### P1-3 · BFB retention 진동 — 로그의 42% 점유

- 2026-08-25 2시간 로그 1,753행 중 **738행**이 한 종목(`001450`)의 왕복.
  `BFB 돌파 1차 감지` 374 / `BFB 돌파 후퇴` 364.
- **오늘 실제로 진단을 방해했다** — 로그 상위를 전부 덮었다.
- 원인 셋:
  1. retention 이 **연속 유지** 요구 — 대기 중 한 틱만 `flag_high` 미만이면 즉시 취소
     (`bull_flag_breakout.py:818-822`). 돌파선이 전일종가 근처면 노이즈만으로 무한 재시작
     (001450: `flag_high` 50,800 vs `prev_close` 50,600 = +0.40%).
  2. **완주 후 재무장 불가** — `:829` pop 직후 `_prev_price ≥ flag_high` 라
     `:832` edge-crossing(`prev < flag_high <= current`)이 재성립하지 않는다.
     가격이 돌파선 아래로 내려갔다 와야만 재평가된다.
  3. `_prev_price` 가 `_reset_daily_state`(`:1094-1100`)에서 **청소되지 않아** 일 경계를 넘어 잔존.
- 시정: 완주 후 거래량 탈락 시 `first_seen` 을 pop 하지 말고 **충족 래치**로 유지 +
  `_prev_price` 일일 청소 + 히스테리시스 밴드 검토.

### P1-4 · `silent_inactive` 오판 — 하루 16~24 접속키 낭비

- **매일 08:57 · 15:27 에 8개 세션 동시 강제 재연결.**
  `[silent_inactive_force_reconnect]` — 08-24 3회, 08-21 9회(애프터 포함).
- 가드 조건 = `fresh_ratio < 0.2` + `subscribed >= 5` + **5분 지속**
  (`src/engine/stale_session_recovery.py:24-31`).
  그 두 시각은 **하루 중 거래가 가장 없는 순간**이라, 가드가
  "거래가 없어 조용한 것"과 "세션이 죽어 조용한 것"을 구분하지 못한다.
- 접속키에 **캐시가 없다** — `src/auth/token.py:183` 이 호출마다 `POST /oauth2/Approval`,
  그 호출이 **재연결 루프 안**(`src/realtime/websocket.py:213`)이라 재연결 = 접속키 1개 무조건.
- 시정: 장 상태를 판정에 반영(프리장 단독·마감 직후 제외 또는 임계 완화).
- **2026-08-27 실측 갱신 — 지속·확대 중**: 8/26·8/27 각각 **24건/일**
  (08:58 ×8세션 + 15:27~28 ×8 + **15:39 ×8** — 종전 서술의 2슬롯이 아니라 **3슬롯**).
- ℹ️ **2026-08-25 KIS 메일 폭주의 원인은 이것이 아니다** —
  같은 KIS 계정에 묶인 **다른 계좌 앱키의 외부 배치**였음이 사용자 확인으로 판명.
  이 시스템의 12시간 인증 호출은 토큰 7 + 접속키 17 = **24건**뿐(DB·컨테이너 로그 일치).

### P1-5 · VB 15:30 종가 매수 발사 + APBK3013 [단일가매매] 미분류 — ✅ cycle229 종결 (2026-08-28)

> 시정 = VB·momentum 매수 컷 **15:20**(`BUY_CUTOFF_KST` 모듈 상수·KST 명시·check_buy_signal
> 최상단·상태 무갱신, `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일) + `[단일가매매]`
> 변형 `is_market_order_disallowed` 편입(주 실익 = 매도 무기록 포기 경로 → step_down
> 지정가 폴백+TTL). 부수 = 무-freeze 레거시 테스트 6곳 장중 KST 동결(벽시계 독립 확보).
> D+1(월) 확인: `[callback_exception]` 15:30 대 0건(의미 반전 — 있음→없음이 정상) +
> `[selling_reconcile]` 빈도(지정가 매도 미체결 잔존 감시). 상세 자문 = 아래 정정 블록.

- **실측**: 8/20 ×2 · 8/21 ×1 · 8/25 ×4 · 8/27 ×2 — 전부 **15:30:0x~2x**. 체인 =
  VB 매수 신호(예: 8/27 15:30:20 에코프로 086520 "현재가 92,000 ≥ 목표가 90,050") →
  시장가 SOR 1주 매수 → APBK3013 `[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선
  취소 주문만 가능합니다` → **이 msg1 변형이 `is_market_order_disallowed` 키워드 미매칭**
  (기존 키워드 "지정가 및 최유리"가 중간 "(신규/정정/취소)" 삽입으로 substring 미성립) →
  KisApiError 가 `on_tick` 밖으로 전파 → `[callback_exception]` → **WS 재연결**(G-REJECT-1
  설계상 의도된 전파이나, 15:30 마다 1~4회 재연결 churn + 그 순간 보유 종목 시세 감시 공백).
- **⚠️ cycle227 무관 확증** — 8/20 부터 존재(8/25 발생분은 cycle227 배포 19:30 *이전* 15:30).
  8/26 15:40 `[애프터마켓]` 변형은 기존 키워드에 매칭돼 정상 폴백(무예외) — 변형별 갈림 실증.
- **🚨 단순 키워드 추가 금지 — 시간 가드 선행** (자문 `cycle229_vb_1530_single_price.md`,
  2026-08-28 **전제 정정 포함**): ~~"15:20~15:29 연속매매에서 우연히 K-돌파가 없었다"~~ 는
  **반증** — 그 구간은 KRX **장후 동시호가(종가 단일가)** 다(`session.py::is_call_auction_now`
  사이클 162/182 가 이미 그렇게 판정, 6/17 15:21:48 `fresh=0/10` 실측 = 평가할 틱 자체가
  구조적으로 희박). 15:30:0x~2x 에 몰린 9건은 **랜덤엔드 체결로 확정 종가 1틱이 흐르며
  15:19 마지막 연속체결가 대비 점프 → edge-crossing** 생성이 원인. ⚠️ 종가 단일가는
  **시장가 호가를 접수**한다(15:20 강제청산 시장가 매도가 작동 중인 것이 방증) — 15:2x
  VB 매수는 "거부되는" 게 아니라 **종가로 체결돼 오버나잇**된다(우연한 안전판 없음).
  시정 = (a) VB·momentum 매수 컷 **15:20**(명시 시각 모듈 상수·KST — 보드 결합 금지,
  momentum 종가 확정 틱 +29% 는 "상한가 잠금 실패 마감" 표본이라 원 가설의 반대) +
  (b) `[단일가매매]` 변형 `is_market_order_disallowed` 편입(정당화 축은 **매도** —
  미분류 매도 거부는 3회 재시도 후 무기록 포기(`order_engine:815~828`)라 랜덤엔드 창
  청산 실패가 기록조차 안 됨. 낮은 매도 지정가는 단일가 세션 유효 주문 = 폴백이 정확한
  처방. 잔여 매수 경로는 LTV 야간 다운그레이드→시간외단일가뿐). 8영역 무접촉 달성 가능.
- 부수 미규명 1건: 8/24 09:46:49 `[callback_exception] ticker=377300` — 15:30 패턴과 다른
  시각. 별도 규명 필요(단발).

---

## P2 · 정확성 · 잠재 위험

### P2-5 · kojiro `_held_stage3` stale True — ✅ cycle231 종결 (2026-08-29)

> 시정 = 플래그를 `(판정 수행일, bool)` 로 전환, 소비처는 **오늘 판정만** 인정(stale True
> 억제 + `[kojiro_stage3_stale_skip]` age 1=INFO/≥2=WARNING, cap 1회/ticker/일).
> `:649` fail-open 계약을 prepare·소비 축까지 통일한 것 — §1·§2·§4 가 방어. 자문 정정 2 =
> cycle225 게이트는 donchian 것(kojiro recompute 는 전수 순회, 실스테일 경로 = 07:59/16:20
> 재-prepare) + ATR 밴드 **상한** 이탈(급등 종목)이 마킹을 못 받는 경로. 부수 방어 =
> `:685` buy_date 비교 try 밖(cycle226 L-2 동형, 잠복) isinstance 가드. Red 가 추가 실증한
> 현행 결함 = 소비처가 비어 있지 않은 튜플을 전부 참으로 읽음(`(오늘, False)` 도 발화).
> 자문 한계 명시 = 다수 케이스에서 하루 늦은 청산 실비용(kojiro 저승률·고RR 라 유리한
> 교환 — **고승률·저RR 전략에 복사 금지**) + `[kojiro_stage3_exit]` 표본 ~20건 시 §3
> 존재 가치 재검정. 자문 = `cycle231_kojiro_stage3_stale.md`.

`prepare()` 경로는 실패 시 `False` 를 **쓰지 않는다**. ATR 밴드 이탈·스테이지 판별 불가로
중간에 걸리면 **직전 값이 그대로 남는다**(`kojiro.py:393-401` vs `:664-668`, `:701-703`, `:742`).
어제 `True` 였던 종목이 오늘 데이터 열화로 재판정되지 못하면
**가격과 무관하게 즉시 `TRAILING_STOP`** 이 나간다. fail-open 이 아니다.

### P2-6 · BFB 진입창 naive 시각 + 좀비 타이머 — ⚠️ 좀비 타이머 축은 cycle228 부분 종결

> cycle228 이 `_breakout_first_seen` 에 일 경계 스테일 자기 방어(진짜 롤오버 시 clear,
> `_roll_gate_day_if_needed`)를 넣어 "익일 09:05 elapsed 수만 초 → retention 즉시 충족
> 우회" 축은 닫혔다. **잔여 = naive 시각 비대칭**(`:794` `datetime.now().time()` vs
> `:801` KST — 컨테이너 TZ 의존)과 `scheduler.py:2984` 스윙 폴 시간 가드 동형.

- `bull_flag_breakout.py:794` 가 `datetime.now().time()`(naive), 두 줄 뒤 `:801` 은
  `datetime.now(KST)` — **같은 함수 안에서 비대칭**. 컨테이너 `TZ=Asia/Seoul` 에 의존.
- 시간 가드가 retention 블록보다 **앞**이라 12:59:58 등록분이 영구 동결된다.
  익일 09:05 에 `elapsed` 가 수만 초라 retention 이 즉시 "충족" 처리되는 **우회**가 생긴다.
- `scheduler.py:2984-2989` 의 스윙 REST 폴 시간 가드도 동일하게 naive.

### P2-7 · `[day_high_scope_skip]` 문구가 grep 을 모호하게 함

note 본문이 교차 판별자로 `[day_high_adopted]` 를 언급해, 단순 substring grep 이
두 마커를 구분하지 못한다. **2026-08-25 실제로 4건을 114건으로 오집계**했다.
정밀 매칭은 `'[day_high_adopted] strategy='` / `'[day_high_scope_skip] ticker='`.

### P2-8 · F-E 잔여 코호트 관측

2026-08-25 실측: **110종목**이 첫 MAIN 관측 시 당일고가가 프리장(`hgpr_hour=08시대`)에 있었고,
09:47 시점 **3종목만** 전환. 보유 7종 중 4종이 걸렸고 3종 미전환 =
그 시간 동안 사이클 222-a 의 blind 내성이 꺼져 있었다.
며칠 관측해 규모를 확정한 뒤 대응을 정한다(현재는 fail-closed = 안전 방향).

---

## P3 · 사람 결정이 필요함

### P3-9 · `prepare()` 관용 읽기 — 매수를 넓히는 방향

`prepare()` 가 `stck_hgpr` 만 읽어서, `_extract_raw` 가 `raw` 없는 row 를 그대로 반환하면
(`src/db/stock_master_daily.py`) `0` 을 읽는다. `high_price` 도 수용하면 해결되나
**매수를 넓히는 방향**이라 사람 결정 사안으로 남겼다.
현재 **잠복** — 일봉 writer 가 `raw` 를 항상 저장하고 라이브 샘플도 전부 보유였다.
사이클 226 이 안전 방향 3중 방어(후보 거부 · 재도출 자가치유 · 폴백 가시화)만 닫았다.

### P3-10 · cycle221 슬롯 축 — ✅ cycle230 으로 채택·종결 (2026-08-29)

> 재평가 결론(사용자 결정) = **채택·커밋**. "슬롯 부족" 반증(08-25)은 *BFB 미구독 원인*
> 주장만 반증(실원인 = P0-2 축출), 08-19 실사고(메인 45/41 서버 한도·VI 누수·보유 4종목
> tick blind)는 유효. 적대적 리뷰 "주 목적 미달성"은 불완전 지적일 뿐 — 누수 차단·main_over
> 계측·VI 메인 퇴출은 독립적으로 옳고, P0-2 시정+cycle228 매수 개방으로 구독·보유 압력이
> **재증가 추세**(8/28 구독 144 = 8/25 대비 +30%)라 가치 회복. **잔여 후속(신규)** =
> 메인 헤드룸 관리 — LOW tick 후보의 메인 fallback 이 VI 퇴출로 빈 슬롯을 되채우는 축
> (적대적 리뷰의 미달성 지적 그 자체). 관측 = 신규 `main_over` 필드로 실측 후 판단.

- 미커밋 잔류: `src/engine/scheduler.py +135/-46` + 테스트 6파일.
- 적대적 리뷰 **주 목적 미달성** 판정(VI 를 main 에서 빼도 LOW tick 후보가 슬롯을 되채움).
- **⚠️ 2026-08-25 BFB 조사에서 "슬롯 부족" 전제 자체가 반증됐다** —
  라이브 구독 111/328 = **34% 사용**, 217슬롯 유휴, `[priority_drop]` 08-20 이후 **0건**.
  이 사이클을 계속할지부터 재검토하라.

### P3-11 · donchian 라이브 이탈값 재튜닝

`breakout_fail_n_days=2`(코드 5) · `atr_trail_mult=1.8`(코드 2.0).
사이클 223 S1 봉인 후 **복원 경로는 운영자 수동 DB UPDATE 뿐**.
2026-08-25 에 S1·S2·S3 전부 실측 확증됐으므로, 표본이 쌓이면 재튜닝 판단 가능.

---

## 이번 조사에서 반증된 가설 (다시 파지 말 것)

| 가설 | 판정 근거 |
|---|---|
| "retention 을 못 버텨서 매수 0" | **반증** — 2026-08-25 **21회 이상 완주**. 완주 경로가 무로그라 안 보였을 뿐 |
| "구독 슬롯 부족" | **반증** — 111/328 = 34% 사용, 217 유휴, `[priority_drop]` 0건 |
| "후보 48이 과다해 구독 압력" | **반증** — 08-08 확대 이후 **최저치**(08-13 142 / 08-18 146 → 48) |
| "BFB 가 구독 대기열 후순위라 tail 절단" | **반증** — 병합 순서 **최선두**, `BREAKOUT_LOW_CAP` 은 08-08 제거 |
| "같은 dict 를 읽는 donchian 도 동일 결함" | **반증** — donchian 은 `max(...)` 라 **fail-open**. BFB·VCP 만 fail-closed |
| "수량 산출·예산 클램프가 병목" | **반증** — 애초에 BUY 분기에 도달하지 못해 `calc_buy_quantity` 가 호출조차 안 됨 |

---

## 작업 시 지켜야 할 제약

- **8영역 무단 수정 금지** — `risk.py` · `order_engine.py` · `src/realtime/` · `src/auth/` ·
  `api/order.py` · `session.py` · `scanner.py` · `strategy_registry.py`.
  P0-1 방향 A 는 `handler.py`(8영역) 수정이 필요하니 **명시적 승인** 후 진행.
- **워킹트리에 미커밋 cycle221 잔류** — `git checkout` / `stash` / `restore` **절대 금지**.
- **배포 창** — NXT 애프터(15:30~) 또는 익일 07:45 부팅 전. KRX 메인(09:00~15:30)과
  20:00 자문 / 20:10 로그분석 회피.
- **커밋·푸시는 사용자 명시 지시가 있을 때만.** 푸시 후 `gh run list` 로 CI/Deploy 확인 의무.
- **`enabled=False` 금지** — `risk.on_tick` 이 `registry.enabled()` 만 순회해
  보유 포지션의 손절·트레일링이 **전부 정지**한다. 비중 축소는 극소값(0.01)으로.

## 검증에 쓸 명령

```bash
# 유령 키 확인 (대입부는 risk.py:397 하나뿐, acml_vol 없음)
grep -rn "ticker_prices\[" src/ | grep -v CLAUDE.md

# 라이브 키 출현 대조
curl -s "http://3.38.228.74/api/trading/status" | grep -o '"acml_vol"' | wc -l   # → 0

# BFB 상태
curl -s "http://3.38.228.74/api/strategies" | python3 -c \
  "import sys,json;r=json.load(sys.stdin)['data']['bull_flag_breakout'];print(r['scan_stats'],r['positions'],r['buy_signals'])"

# 전체 회귀
find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q
```
