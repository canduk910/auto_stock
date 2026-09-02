# cycle237 — donchian 청산 계열 관측 로그 폭주 cap (관측 전용, 8영역 diff 0)

> 발단 = 2026-09-02 D+1 실측. 사용자 지시 "breakeven 로그 cap 작업 시작하자".
> 허용 파일 = `src/engine/strategies/donchian_swing.py` 단독(+ 테스트/AST 가드).

## 실측 근거

```
2026-08-31  [donchian_breakeven_promote] 192820 : 11,453건 / 401분  (그날 system_logs 의 36.9%)
2026-09-01  [donchian_breakeven_promote] 192820 :  9,027건 / 512분  (51.0%)
2026-09-02  도치안 시간 기반 청산        034020 :     68건 / 08:00~09:00
```

메시지 패턴별 집계에서 **압도적 1위**. 08-31 전체 31,064행 중 11,453행, 09-01 전체
17,698행 중 9,027행이 **단일 종목(192820) 한 문장**이다.

## 근본 원인 — 래칫 부재 (kojiro 와 갈리는 지점)

| 전략 | 승격 결과 영속 | 다음 틱 조건 | 결과 |
|---|---|---|---|
| kojiro | `self._stop_floor[ticker] = eff` | `promoted == eff` → 거짓 | **자연 1회** |
| donchian | 없음 (`base_stop` 매 틱 재계산) | `promoted_stop != base_stop` → **영원히 참** | 매 틱 로그 |

donchian 은 `base_stop = pos.buy_price - stop_atr × entry_atr` 를 매 틱 새로 만들므로
`base_stop < buy_price` 인 한 승격 조건이 계속 참이다. **승격 자체는 매 틱 올바르게
일어나고 결과도 동일하다** — 잘못된 것은 로그뿐이다.

시간청산은 성격이 다르다. `Signal.STOP_LOSS` 와 짝이라 정상 흐름에선 1회지만, 매도가
거부되면(034020 = 프리마켓 APBK0918) 포지션이 잔존해 매 틱 재발화한다.

## 시정 2축 (둘 다 `donchian_swing.py`)

| # | 대상 | 내용 |
|---|------|------|
| S1 | `[donchian_breakeven_promote]` | 신규 `_emit_breakeven_promote(...)` — `DailyEmitCap[str]` 1회/ticker/일 + 날짜 키 자기 리셋. 호출부는 `if promoted_stop != base_stop:` 안, **`base_stop = promoted_stop` 대입은 cap 밖** |
| S2 | `도치안 시간 기반 청산` | 신규 `_emit_time_exit(...)` — 동형 cap. **`return Signal.STOP_LOSS` 는 cap 밖** |

두 cap 은 **별개 인스턴스**(기존 5개 cap 과도 별개 — OB-11: 한 사실이 다른 사실을
침묵시키지 않는다). 관측 순서 = peek → 로그 → mark(cycle226 D-3). 예외 전량 흡수 +
`logger.debug` 흔적. 메시지 서식은 **byte 동일**(운영 grep 연속성).

## 핵심 계약 — cap 은 로그에만, 행위는 cap 밖

이게 이 사이클의 유일한 위험 지점이다. cap 이 신호 반환까지 삼키면 매도 거부 후
재시도가 끊겨 **포지션이 청산되지 못한 채 잔존**한다 = 관측 시정이 아니라 매매 결함 주입.
BE-2 / TE-2 가 이 계약을 못박는다.

## 범위 한정 (의도적으로 제외한 것)

- **kojiro `[kojiro_breakeven_promote]` 무접촉** — `_stop_floor` 래칫으로 자연 1회다.
  다크런치(`breakeven_promote_atr=0`)라 실측 0건인 것과는 **별개 이유**이며, 활성화해도
  폭주하지 않는다. 불필요한 변경을 하지 않는다.
- **donchian 나머지 청산 로그**(`도치안 스윙 손절` · `[donchian_turtle_stop]` ·
  `[donchian_turtle_backstop]` · `[donchian_channel_exit]` · `도치안 스윙 트레일링`)는
  같은 구조적 폭주가 **가능하지만 실측 0건**이다(손절은 대개 정상 체결돼 포지션이 사라진다).
  TE-4 픽스처 작업 중 `도치안 스윙 손절` 5회 반복이 우연히 실증됐으므로 **후속 후보로 등재**한다.

## Red 목록 (10, 전부 신규 파일)

| ID | 검증 | Red 시점 |
|---|---|---|
| BE-1 | 100틱 → 승격 로그 1행 | FAIL |
| BE-2 | **행위 가드** — cap 이후에도 승격 손절선(=매수가) 유효 | PASS(구현 후에도 PASS 의무) |
| BE-3 | 날짜 경계 → 2행 | FAIL |
| BE-4 | ticker 단위 cap | FAIL |
| BE-5 | 관측기 예외 → 청산 판정 정상 | FAIL(try 부재) |
| TE-1 | 20틱 → 시간청산 로그 1행 | FAIL |
| TE-2 | **행위 가드** — 로그 1행이어도 신호는 매 틱 | FAIL(로그 카운트 축) |
| TE-3 | 날짜 경계 | FAIL |
| TE-4 | ticker 단위 | FAIL |
| TE-5 | 관측기 예외 → STOP_LOSS 유지 | FAIL |

## 뮤테이션 실증 2

1. **cap 게이트 제거**(`should_emit` 검사 삭제) → 7 FAIL. cap 가드 비공허.
2. **`return Signal.STOP_LOSS` 를 cap 안으로 종속** → **TE-2 FAIL**.
   매매 결함 주입을 정확히 검출 — 이 사이클에서 가장 중요한 가드다.

## 의미 전환 1

`tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::test_g223_8_exit_branch_order_unchanged`
의 ② 마커 `"도치안 시간 기반 청산"` → `"_emit_time_exit"`. 로그 문장이 헬퍼로 이동해
`check_exit_signal` 본문에서 사라졌기 때문이며, **분기는 같은 자리**라 순서 검사 강도는
보존된다(가드가 지키는 것은 문자열 위치가 아니라 청산 분기 순서).

## 적대 검증 (3렌즈 18에이전트, 발견 15 → 확증/부분 8 · 반증 7) — 2026-09-02

**HIGH/MEDIUM 0건.** 렌즈 1(행위 변경)은 검증자가 **독립 차분 실증**까지 수행해 확증했다 —
변경 전/후 모듈에 동일 상태·동일 틱열(11 시나리오 × 3 동결시각 = **3,240 틱**)을 먹여
반환 Signal 수열 **불일치 0건** + `get_effective_stop_price` **불일치 0건**.

부수 발견(검증자) — 종전 `int(entry_atr)`/`int(base_stop)`/`int(promoted_stop)` 은
`logger.info` **인자 평가 시점 = try 밖**이라 던지면 뒤따르는 승격 대입·backstop·시간청산·
채널·샹들리에가 통째 유실됐다(cycle226 L-2 동형 잠복). 헬퍼로 옮기며 try 안으로 들어가
그 표면이 **닫혔다** = 이번 변경은 안전 방향으로만 다르다.

| ID | 판정 | 시정 |
|---|---|---|
| C237-V0 | CONFIRMED / NONE | 무결함 확증(3,240틱 차분). 조치 불요 |
| **C237-F1** | PARTIAL / LOW | 시각 귀인 의문 → **실측 판별**(아래 별도 절). docstring 판독법 추가 + 후속 등재 |
| C237-F2 · L3-2 | PARTIAL / LOW | 계약 §3(peek→로그→mark) 무가드 → **BE-6 / TE-6** 신설 |
| C237-L2-1 | PARTIAL / LOW | `logger.debug` 단독은 `_DbLogHandler`(INFO 컷) 미도달 → 같은 파일의 `_trace_observer_failure`(cycle225 J-3) 헬퍼로 교체(WARNING 1행 동반) |
| C237-L2-4 | CONFIRMED / LOW | docstring 근거 부정확("매도 실패는 `[market_closed_blocked]` 가 기록") → 클래스별 거부 로그(cap 없음)가 정본, `[market_closed_blocked]` 는 게이트 차단분만 찍는 **보조** 신호로 정정 |
| C237-L3-3 | PARTIAL / LOW | 계약 §2(별개 cap 인스턴스) 무가드 → 동시 무장 테스트 신설 |
| C237-L3-4 | PARTIAL / LOW | 인자 전치·서식 무가드 → 행 개수 단언을 **완성 문자열 일치**로 승격(BE-7 / TE-7) |

반증 7 = 서식 가드 부재(F4·L2-2 — 실제로는 L3-4 로 수렴) · cap 키 ticker 단독(L2-3) ·
날짜 게이트 복제(L2-5) · 잔여 5로그 dedupe 우회(L3-1) · 의미 반전 경고 부재(L3-5) ·
`_trace_observer_failure` 미사용 주장 중복(F3).

## C237-F1 실측 판별 — (a)도 (b)도 아닌 **제3의 답**

검증자는 "08:00~09:00 68건"이 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`(LTV 단독) 게이트와
모순이라며 (a) 시각 오기(UTC 시버킷) 또는 (b) 게이트 미적용을 제시했다. EC2 실측 결과:

- **(a) 반증** — DB 세션 `TimeZone = Asia/Seoul`. 같은 행 UTC 환산은 09-01 23:00 이다.
  표기 08:00 은 **진짜 KST 08:00**이고, 같은 초에 APBK0918 "[프리마켓] 시장가 매매 불가"가
  찍힌 것이 독립 확인이다. 정확한 분포는 **08시 67건 + 09시 1건**.
- **(b) 부분 성립** — `[pre_market_exit_deferred] donchian_swing` 은 3일 연속 발화 중이라
  게이트 자체는 **작동한다**. 그러나 09-02 첫 발화 시각이 **08:00:29** 인 반면 시간청산
  67건은 **08:00:00~08:00:0x** 에 집중됐다. `_session_loop` 30초 주기라 08:00 정각에는
  `session_tracker.active` 에 PRE_NXT 가 아직 없고, 게이트는 `PRE_NXT ∈ active` 를 요구하므로
  **fail-open** 한다 ⇒ **매일 ~30초 구멍**. 그 창에서 실제 매도 주문이 나갔고 APBK0918 로
  거부됐다(NXT 거래가능 종목이었다면 체결됐을 수 있다).

**이건 사이클 237 범위 밖의 독립 결함**이며 후속 사이클 대상이다(→ 워크리스트 등재).
cap 이 이 신호를 지우지 않는다 — cap 은 그날 **첫** 발화를 남기고, 그 타임스탬프가
09:00 이전이라는 사실 자체가 게이트 미적용의 증거다(버스트 크기는 잃지만 **시각은 남는다**).
`_emit_time_exit` docstring 에 이 판독법을 명시했다.

## 검증

- 표적 **15 PASS**(10 + 적대 검증 후속 5) · 전략+AST 스위트 PASS · 8영역 diff 0.
- 뮤테이션 **5종** 전부 검출 실증:
  ① cap 게이트 제거 → 7 FAIL ② `return Signal.STOP_LOSS` 를 cap 에 종속 → **TE-2 FAIL**
  ③ mark-before-log → **BE-6 FAIL** ④ 인자 전치(before↔after) → **BE-7 FAIL**
  ⑤ cap+day 완전 공유 → **별개 인스턴스 테스트 FAIL**
- ⚠️ 뮤테이션 ⑤의 **약한 변형**(cap 만 공유, day 필드는 별개)은 15 PASS 였다. 이는 가드
  공허가 아니라 **설계의 자기 치유** — 두 헬퍼가 각자의 day 필드로 `reset_daily()` 를
  트리거해 서로의 mark 를 지우므로 같은 틱에 둘 다 emit 된다. 진짜 계약 위반(cap+day
  동시 공유)은 가드가 잡는다.
- 예상 효과: donchian 보유 1종목 기준 `system_logs` **일 ~1만 행 감소**(전체의 37~51%).
