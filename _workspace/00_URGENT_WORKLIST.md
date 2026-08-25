# 🔴 최우선 과제 — BFB·VCP 매수 전면 차단 (2026-08-25 확정)

> **이 파일이 현재 최우선 작업 지시서다.** 새 세션은 다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.
> 근거 보고서: https://claude.ai/code/artifact/75081207-15a8-4d43-9574-2352dae049b2
> 작성 시점 상태 = 미푸시 커밋 0 · 워킹트리에 미커밋 cycle221 잔류.
>
> **⏳ 2026-08-25 사이클 227 — P0-1 Stage 0 + P0-2 구현 완료 (미커밋, 배포 대기).**
> 상세는 아래 각 절의 "시정 현황" 참조. 다음 액션 = 사용자 커밋 지시 → 배포 창(NXT 애프터
> 15:30~ 또는 익일 07:45 전) 배포 → 1~2영업일 `would_pass` 관측 → 게이트 전환 사이클 판정.

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
배포 후 D+1 실측 항목 = `reason=stale_6plus_low_volume` 축출 건수 급감 확인
(2026-08-25 기준 46건/일 → 실거래 종목 0건 기대) + 관측 시 "게이트 탈락" 과
"구독 상실" 분리 집계(자문 보너스 항목).

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
- ℹ️ **2026-08-25 KIS 메일 폭주의 원인은 이것이 아니다** —
  같은 KIS 계정에 묶인 **다른 계좌 앱키의 외부 배치**였음이 사용자 확인으로 판명.
  이 시스템의 12시간 인증 호출은 토큰 7 + 접속키 17 = **24건**뿐(DB·컨테이너 로그 일치).

---

## P2 · 정확성 · 잠재 위험

### P2-5 · kojiro `_held_stage3` stale True — 방향이 반대인 실패

`prepare()` 경로는 실패 시 `False` 를 **쓰지 않는다**. ATR 밴드 이탈·스테이지 판별 불가로
중간에 걸리면 **직전 값이 그대로 남는다**(`kojiro.py:393-401` vs `:664-668`, `:701-703`, `:742`).
어제 `True` 였던 종목이 오늘 데이터 열화로 재판정되지 못하면
**가격과 무관하게 즉시 `TRAILING_STOP`** 이 나간다. fail-open 이 아니다.

### P2-6 · BFB 진입창 naive 시각 + 좀비 타이머

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

### P3-10 · cycle221 슬롯 축 — ⚠️ 우선순위 재평가 필요

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
