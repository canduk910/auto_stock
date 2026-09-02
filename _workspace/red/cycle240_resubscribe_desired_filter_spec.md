# cycle240 — 5분 우선 재구독 핑퐁 시정: LOW 후보를 desired 집합과 교집합 (08-31 포렌식 결함 ⓑ)

작성: team-leader, 2026-09-02 야간. 사용자 위임("대부분의 결정요소는 직접 권장하는대로 진행"). 3렌즈 진단(source·desired·tests)
검토 + 코드 재실측 후 확정. 렌즈 서술 중 **정정 2건**은 §0 ② 와 §1 마지막 두 행에 명시.

> **워킹트리 상태**: HEAD `756be67`(cycle239) 푸시 완료, 트리 클린(`_workspace/morning_0903_report.md` untracked 1건은 타 에이전트 산출물 — 무접촉).
> 다른 에이전트(피라미딩 검토)가 **읽기 전용** 동시 실행 중 — 이번 사이클 변경은 §5 허용 목록 밖으로 나가지 않는다.
> **git commit / push / stash / checkout / restore 금지.**

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py · strategy_registry.py)
> + **scheduler.py 무접촉**(라인 상한 가드 `< 4000`, 실측 **3,999L** = 헤드룸 0) + `stale_manager.py` facade 무접촉(신규 export 불요 — 헬퍼는 private)
> + `stale_session_recovery.py` 무접촉. src 변경 = **`src/engine/stale_watcher_core.py` 단독**.

## 0. 결정 요약 (착수 질문 ①~⑥)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | desired 정본 소스 + 교집합 위치 | **desired_low = breakout ∪ momentum**, breakout = `scheduler._collect_breakout_tickers()`(인스턴스 메서드, `_universe_excluded_today` 제거 내장) · momentum = `scanner._last_scan_result`(모듈 속성, 호출 시점 lazy read). HIGH(positions ∪ NDC)는 함수 안 기존 `high_tickers` 그대로. **적용 대상 = `low_targets` 만**, 위치 = `:477-478` 분리 대입 **직후** → cycle216 A(동시호가) → B(throttle) → cap **앞** | 코드에 desired 상주 객체가 없다 — 유일 정본은 `_scan_loop` 지역 `new_set`(`scheduler.py:2457` = `scan_stocks()` ∪ breakout ∪ positions)이고 위 정의는 `new_set ∪ NDC` 와 **동치**다(같은 try 블록·같은 이터레이션, 사이 변화는 `_reprepare_breakout_if_empty` 의 **가산**뿐 = 필터가 `_scan_loop` 자신이 구독하려는 종목을 자를 수 없다). `stale_tickers`(소스 `:449`)가 아니라 `low_targets` 에 걸면 HIGH 는 **필터 경로를 지나지 않아** 위험이 구조적으로 0 이고 G-17(`priority 분리 후 cap`)·GS-6·cycle216 순서 계약이 전부 무손상. `kis_ws_pool.get_subscribed_tickers()` 는 정본 **부적격** — cycle215/217 이 "미구독 split-brain 종목의 재구독" 을 계약으로 봉인했고 그것과 교집합하면 그 시정이 통째로 무력화(§4 F-14 가 실증). 스윙 후보(`_collect_swing_tickers`)는 **제외** — new_set 에도 없고(G안 2026-05-12), 넣는 순간 이번 결함의 대표 피해자(매도 완료 donchian/kojiro)가 desired 로 되살아난다 |
| ② | desired 비어 있음·판정 불가 시 fail-open | **활성 게이트 = `breakout_desired` 비어 있지 않음 ∧ HIGH 수집 무예외 ∧ desired 수집 무예외**. 하나라도 거짓이면 필터 미적용(현행 행위 byte 동일) + 로그 `desired_low=0`. **momentum 은 desired 에 가산만 하고 활성 판정에 참여하지 않는다** | 렌즈 2 의 "LOW 소스(breakout ∪ momentum) 공집합 → skip" 과 "잔여값은 더 허용적 방향" 은 **정정** — `scanner._last_scan_result` 는 모듈 전역이라 다른 테스트의 `scan_stocks()` 잔여값(`scanner/test_cycle183`·`strategies/test_cycle157` 가 호출, pytest 수집 순서상 `scanner/` < `stale_manager/` < `test_*.py`)이 **비어 있지 않으면 필터가 켜져** 기존 LOW 회귀 23파일이 순서 의존으로 깨진다(덜 허용적). 활성 판정을 scheduler **소유** 소스에만 걸면 결정적이다: 기존 fixture 는 `_EmptyRegistry`(`.get` 부재 → AttributeError → 빈 set) 또는 `MagicMock` registry(`.get()`→MagicMock→`get_scanned_tickers()`→MagicMock→`list.extend` 가 빈 iter 로 통과 → `[]`, 파이썬 실측)라 **전부 게이트 off** = 무변경 통과. 운영상 breakout 이 빈 순간 = 부팅~prepare 전 / 4 돌파 전략 전부 disabled — 그때 fail-open 은 현행과 같다. HIGH 수집 예외 시 skip 은 "positions 한 전략이 예외로 빠져 HIGH 가 LOW 로 오분류된 뒤 필터에 잘리는" 경로를 닫는 **이중 보호** |
| ③ | HIGH 보호 | `low_targets` 한정 적용(①) + `_high_collect_ok` 플래그(②) 이중. `high_targets` 는 분리 대입 이후 **재대입 0건**(AST G-240-2) | HIGH ⊆ desired 이므로 소스에 걸어도 결과는 같지만, "같다" 는 registry 정상일 때만이다. 구조로 봉인 |
| ④ | 관측 필드/마커·cap | **기존 INFO 1행 확장** — `[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d filtered_not_desired=%d filtered_sample=%s`(`count=` 첫 필드 유지, sample ≤10). 신규 마커 0 · cap 0 · WARNING 0 | 행 빈도가 불변(5분 1행, `stale_tickers` 공집합이면 종전대로 무로그)이라 cap 이 필요 없고, 따라서 peek→로그→mark 도 해당 없음. `filtered_not_desired` 는 매 사이클 "유령 수" 를 그대로 보여 주고(`ticker_last_tick` 을 정리하지 않으므로 하루 종일 누적 ≈ 30~80 유지가 **정상**), `desired_low=0` 이 장중에 찍히면 게이트 off = 조사 신호. `test_scan_loop_stale_priority` 가 `"count=10" in log_text` 를 substring 단언하므로 첫 필드 보존이 계약. cycle74 G-8-B 허용목록은 `check_and_resubscribe_stale` 스코프라 무관 |
| ⑤ | 걸러진 종목의 `ticker_last_tick` 잔존 | **이번엔 무접촉** | 소비처가 8곳(K watcher `.get` · universe guard · diagnostics · `get_scan_status` · `routes/realtime.py` 4곳 · `websocket.py:570` grace · 스윙 REST 폴 `preserve_last_tick`)이고 유일 정리가 20:10 `_reset_daily_state`(`scheduler.py:3912`)다. 매도 시 pop 의 자연 위치는 `order_engine._unsubscribe_if_no_other_strategy`(8영역) → 별도 승인 사이클(§8 A). 이번 시정은 잔존을 **무해화**(재구독 소스에서만 무시)한다 |
| ⑥ | 형제 경로 `check_and_resubscribe_stale`(120s) | **같은 결함 없음 — 무변경** | 소스가 `kis_ws_pool.get_subscribed_tickers()`(`:128` → `:213`) = 구독 집합 한정이라 미구독 유령을 만들지 못한다. 핑퐁에 대한 기여는 "되살아난 유령이 5분간 구독 집합에 있는 동안 stale 로 잡혀 재등록 SEND 1회 추가" 뿐이며 원천(5분 경로)이 닫히면 함께 소멸 — D+1 `[stale_watcher_detail]` stale 수 감소로 확인(§7). 한 사이클 한 엣지 |

**domain-consult 불요(`needs_domain_consult=false`)** — WebSocket 구독 관리 순수 배관. 진입·청산 파라미터 0 변경, 매수/매도 신호 경로 무접촉, HIGH(보유·익일청산) 시세 보장 불변·강화 방향(LOW 유령이 cap 10 을 소비하던 것이 사라져 desired LOW 의 복구 여지가 늘어난다).

## 1. 확증된 원인 (3렌즈 코드 실측 + EC2 read-only)

| 사실 | 근거 |
|---|---|
| `resubscribe_stale_priority` 의 stale 후보 소스 = `scanner.ticker_last_tick.items()` **전수** — 구독 집합/desired 와 교집합 0. 형제 `check_and_resubscribe_stale` 은 `get_subscribed_tickers()` 한정 → 비대칭이 뿌리 | `stale_watcher_core.py:449-453` vs `:128, :213-218` |
| `ticker_last_tick` 은 per-ticker pop/del 이 src 전체 0건, 유일 정리 = 20:10 정산 `_reset_daily_state` 의 `clear()`. 09:00 에 한 번 tick 받은 종목은 매도·이탈 후에도 20:10 까지 후보 자격 유지 | 선언 `scanner.py:465` · write `risk.py:504` · clear `scheduler.py:3912`(호출 `:952`, `TIME_SETTLEMENT=20:10`) |
| 핑퐁은 **같은 `_scan_loop` 이터레이션 안 ~12초**: `new_set` → `_delta_unsubscribe_dropped`(빼기) → `subscribe_filtered_stocks` → … → `_resubscribe_stale_priority(cap=10)`(되살리기) → `_evaluate_universe_guard(list(new_set))`(되살아난 종목은 평가 대상 밖 → 자동 수렴 경로 없음) | `scheduler.py:2457-2497` · `stale_session_recovery.py:204-250` · `stale_universe_guard.py:73-88` |
| cycle216 LOW throttle(180s) < 5분 주기(300s) → 이 핑퐁을 구조적으로 못 막음 | `stale_watcher_core.py:44` · `scheduler.py:78` |
| EC2 실측(UTC 저장 +9h): 09-02 09:40 RESUB 9종목 → 09:45 DELTA **동일 9** → 10:00 RESUB → 10:05 DELTA … 1:1 페어링 무한. 034020 은 09:00:29 매도 후 **19:59 까지 35회** 재구독. 09-01 993 종목언급/115행, 09-02 843/108행. `cap_exceeded` 0건(HIGH 가 cap 을 넘은 적 없음) | system_logs `[stale_priority_resubscribe]`·`[scan_loop_delta]`·trade_history 대조(렌즈 1) |
| desired 정본 = `_scan_loop` 지역 `new_set` = `scan_stocks()` ∪ `_collect_breakout_tickers()` ∪ positions. **NDC 는 new_set 에 없다**(`subscribe_filtered_stocks` 의 `next_day_clear` 그룹이 별도 복구) → new_set 그대로 desired 로 쓰면 부팅 복구 창(boot_manager NDC 선복원)에서 HIGH 가 깨질 수 있음 → 함수 안 기존 `high_tickers`(positions ∪ NDC)를 그대로 쓰고 필터는 LOW 에만 | `scheduler.py:2452-2457` · `:1868-1870` · `boot_manager.py:379-385` |
| `_collect_breakout_tickers` 는 `_universe_excluded_today` 를 이미 제거 → 축출 종목은 desired 에서 자동 이탈 = "가드가 해제 → 우선 재구독이 부활" 2차 핑퐁도 함께 닫힘 | `scheduler.py:1743-1746` |
| 이 함수는 `_stale_retry_count` 를 읽지도 쓰지도 않음(cycle218 G218-6 봉인) — 교집합이 실제로 줄이는 것은 **구독 슬롯·KIS SEND·로그 오염·`_stale_last_resubscribe_at` 오염** | `stale_watcher_core.py:429-562` · `test_cycle218_retry_counter_cap.py:305-340` |
| **착수 차단 가드**: `test_cycle222a_ast_day_high_scope.py::test_a11b_stale_watcher_core_untouched` 가 `git diff HEAD -- src/engine/stale_watcher_core.py` 공집합을 **영구** 요구(fail-closed). cycle222a 사이클 한정 스코프 가드가 수명을 넘겨 stale watcher 의 모든 후속 시정을 금지 중 → 이번 사이클에서 **내용 검사로 재스코프**(§2.5) | `tests/unit/ast/test_cycle222a_ast_day_high_scope.py:392-411`, `_git` 헬퍼 `:57-70` |
| **정정 1(렌즈 3)**: MagicMock registry 에서 `_collect_breakout_tickers()` 는 TypeError 가 아니라 `[]` 를 돌려준다(MagicMock `__iter__` 기본 = 빈 iter, 파이썬 실측). 따라서 기존 fixture 는 "예외" 가 아니라 "빈 소스" 로 게이트 off 를 탄다 — 두 경로 모두 skip 이어야 한다 | `python -c` 실측 |
| **정정 2(렌즈 2)**: `scanner._last_scan_result` 잔여값은 "더 허용적" 이 아니라 **필터를 켜는 방향**(덜 허용적) — 활성 판정에서 제외해야 결정적(§0 ②) | 수집 순서 `scanner/` < `stale_manager/` < `test_*.py` |

## 2. 시정 설계 (`src/engine/stale_watcher_core.py` 단독)

### 2.1 신규 private 헬퍼 (모듈 레벨, `resubscribe_stale_priority` 위)

```python
def _collect_low_desired(scheduler: Any) -> tuple[set[str], set[str]]:
    """cycle240 — LOW desired 소스 2종 (breakout, momentum). 각각 실패 시 빈 set.

    - breakout = `scheduler._collect_breakout_tickers()` — VB/LTV/BFB/VCP scanned ∖ `_universe_excluded_today`
      (scheduler **소유** 소스 = 활성 게이트의 유일 근거. 인스턴스 메서드 호출뿐 — scheduler 정적 import 0, D-1 동형).
    - momentum = `scanner._last_scan_result` — 같은 `_scan_loop` 이터레이션의 `scan_stocks()` 결과.
      **가산 전용**(활성 판정 불참 — 모듈 전역 잔여값이 행위를 뒤집지 못하게).
    await 0 · DB 0 · write_log 0 · 예외 전파 0.
    """
    breakout: set[str] = set()
    momentum: set[str] = set()
    try:
        breakout = set(scheduler._collect_breakout_tickers() or [])
    except Exception:
        breakout = set()
    try:
        from src.engine import scanner as _scanner_mod  # lazy — patch("src.engine.scanner._last_scan_result") 호환
        momentum = set(getattr(_scanner_mod, "_last_scan_result", None) or [])
    except Exception:
        momentum = set()
    return breakout, momentum
```

### 2.2 `resubscribe_stale_priority` 본문 삽입 (3곳, 기존 문장 재배치 0)

```python
    # (a) HIGH 수집 블록(:461-474) — 기존 try/except 4중 **구조 불변**, except 분기에 플래그만 추가
    high_tickers: set[str] = set()
    _high_collect_ok = True                          # cycle240 — HIGH 수집 실패 시 필터 fail-open
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                _high_collect_ok = False
    except Exception:
        _high_collect_ok = False
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        _high_collect_ok = False

    # (b) 분리 대입(:477-478) 직후 — cycle216 A/B 와 cap 보다 **앞**
    high_targets = [t for t in stale_tickers if t in high_tickers]
    low_targets = [t for t in stale_tickers if t not in high_tickers]

    # cycle240 — LOW desired 교집합 (재구독 핑퐁 차단). HIGH 는 이 블록을 지나지 않는다.
    try:
        _breakout_desired, _momentum_desired = _collect_low_desired(scheduler)
    except Exception:
        _breakout_desired, _momentum_desired = set(), set()
    _filter_active = bool(_breakout_desired) and _high_collect_ok   # momentum 은 게이트 불참(AST G-240-5)
    _desired_low = _breakout_desired | _momentum_desired
    filtered_not_desired: list[str] = []
    if _filter_active and low_targets:
        filtered_not_desired = [t for t in low_targets if t not in _desired_low]
        low_targets = [t for t in low_targets if t in _desired_low]

    # (c) 종료 INFO(:556-559) — prefix·첫 필드 byte 보존 + 3 필드 추가
    logger.info(
        "[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d "
        "filtered_not_desired=%d filtered_sample=%s",
        len(resubscribed), resubscribed,
        len(_desired_low) if _filter_active else 0,
        len(filtered_not_desired), filtered_not_desired[:10],
    )
```

- 순서 계약(확정): **분리 → desired 필터 → 동시호가 LOW skip(A) → LOW throttle(B) → cap 초과 WARNING → `targets = high + low[:cap-len(high)]`**. cap 은 "필터·throttle 통과분 LOW" 에만 적용 → 유령이 cap 10 을 소비하지 못한다.
- `_market_op_skip`(`:442-453`) 소스 단계 무변경. `subscribed_snapshot`·`_ticker_to_session.pop`·`unsubscribe_in_pool` 3 seam(cycle215/217) 위치·순서 무변경(GS-6 텍스트 index 는 `.subscribe(` 첫 출현 기준 — **새 블록·주석에 `.subscribe(` 문자열 금지**, 헬퍼 docstring 은 함수 밖이라 unparse 대상 아님).
- 걸러진 종목은 `_stale_last_resubscribe_at` 를 갱신하지 않는다(루프 미진입) — throttle/force_retry 타임스탬프 오염 소멸.
- `sys.modules.get("src.engine.scheduler")` 리터럴 3+3=6 유지(D-2 ≥4). 신규 모듈 import 0(daily_emit_cap 불요). logger 네임스페이스 `src.engine.scheduler` 유지.

### 2.3 fail-open 경계 (계약)

| 상황 | 게이트 | 행위 |
|---|---|---|
| breakout 비어 있음(부팅 전·4 돌파 전략 disabled·`_collect_breakout_tickers` 예외·registry `.get` 부재) | off | 현행 byte 동일, `desired_low=0 filtered_not_desired=0` |
| HIGH 수집 중 예외(outer/inner/NDC 어느 하나) | off | 동일 — HIGH 오분류 → 필터 절삭 경로 차단 |
| `_collect_low_desired` 자체 예외 | off | 호출부 try — 관측 실패 ≠ 행위 변화 |
| breakout 정상 ∧ momentum 예외/빈 | **on** | momentum 성분만 빈 set — breakout 후보는 정상 통과 |
| breakout 정상 ∧ 동시호가 | on → A 가 LOW 전량 skip | `[stale_skip_call_auction_priority] low=%d` 는 **필터 통과분** 수(더 정확) |

### 2.4 테스트 결정성 seam

- 시각: `@freeze_time("2026-09-02 10:00:00", tz_offset=-9)` + `KST=timezone(timedelta(hours=9))`(cycle216 정본). `_dt_mod` 는 scheduler 네임스페이스 우선 참조라 freezegun 호환.
- patch 4종 그대로: `asyncio.sleep` / `src.realtime.websocket_pool.kis_ws_pool` / `src.engine.scanner.ticker_last_tick`(new=dict) / `src.engine.session.session_tracker`.
- desired 주입: breakout = `sched._collect_breakout_tickers = lambda: [...]`(인스턴스 속성이 메서드를 가림) 또는 registry MagicMock `.get(sid)` → `get_scanned_tickers()` 리스트(F-6 처럼 **실제 `_collect_breakout_tickers` 경유**) · momentum = `patch("src.engine.scanner._last_scan_result", [...])` **모든 신규 테스트에서 명시**(잔여값 격리 — 활성 게이트엔 무관하나 desired 내용엔 관여).
- 헬퍼 patch 점 = `src.engine.stale_watcher_core._collect_low_desired`(facade 경유 금지 — G-16 facade patch 가드는 `stale_manager.X` 만 검사하므로 private 헬퍼는 core 직접).
- 진입점 = facade `stale_manager.resubscribe_stale_priority(sched, cap=10)`(기존 관례).

### 2.5 cycle222a 스코프 가드 재스코프 (`tests/unit/ast/test_cycle222a_ast_day_high_scope.py`)

- `test_a11b_stale_watcher_core_untouched`(bare `git diff HEAD` 영구 동결) → **`test_a11b_stale_watcher_core_no_anchor_coupling`**: `src/engine/stale_watcher_core.py` 내용에 `day_high` / `stck_hgpr` / `high_price` 토큰 0(A-5 와 같은 토큰 집합). cycle222a 의 실제 의도("앵커 blind 시정이 stale watcher 와 얽히지 않는다")를 **내용 기준**으로 보존.
- `_git` 헬퍼 + `import subprocess` 삭제(그 파일 안 유일 사용처가 a11b). 파일 헤더 A-11 항목 문구 갱신.
- 다른 사이클의 동형 영구 동결(`test_cycle223f:236`·`test_cycle223:325`)은 **이번 무접촉** — §8 C 로 수명 감사 등재.

## 3. 불변 계약

1. **HIGH(보유 ∪ 익일청산) 재구독 보장 불변** — 필터는 `low_targets` 에만, `high_targets` 재대입 0(G-240-2), HIGH 수집 실패 시 필터 skip.
2. **cap=10 불변** · `priority 분리 → (필터·A·B) → cap` — G-17 슬라이스 패턴 `low_targets[: max(0, cap - len(high_targets))]` byte 보존, `stale_tickers[:cap]` 부재.
3. **cycle215/217 split-brain 계약 불변** — desired 는 구독 집합이 아니다. 미구독이지만 desired 인 LOW 는 여전히 `_ticker_to_session.pop` + 재SEND(F-14).
4. **cycle216 순서 불변** — A(동시호가)·B(throttle 180s<300) 코드 무변경, 위치 관계만 "필터 뒤" 로 고정.
5. **prefix 보존** — `[stale_priority_resubscribe]`(첫 필드 `count=`) · `[stale_priority_resubscribe_cap_exceeded]` · `[stale_skip_call_auction_priority]` 서식 byte 보존(필드 **추가**만).
6. **D-1/D-2** — scheduler 정적 import 0, `sys.modules.get("src.engine.scheduler")` 합산 ≥4(현 6 유지). **G-6** logger 네임스페이스. **G-7** 의존 방향(core → scanner lazy 허용). **cycle72** write_log 0. **G-12** `high_tickers.update` 전부 Try 하위. **G218-6** `_stale_retry_count` 무접촉.
7. **fail-open 방향 고정** — 게이트 판정 불가·소스 부재·예외 = 필터 미적용(현행). 조용히 LOW 를 전멸시키는 구현(`desired` 공집합에 필터 적용)은 FAIL.
8. **momentum 은 게이트 불참** — 활성식에 `_momentum_desired` 등장 0(G-240-5).
9. **관측 실패 ≠ 행위** — 헬퍼/로그 예외가 재구독 루프를 끊지 않는다.
10. 8영역 diff 0 · scheduler.py diff 0 · facade diff 0.

## 4. Red 테스트 목록

### 4.1 `tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py` (신규 — ID 접두 `test_f240_`)

fixture 는 cycle216 파일에서 import 재사용(`_make_scheduler_with_high_tickers` · `_make_spy_pool` · `_session_tracker_mock` · `_capture_scheduler_warnings`), 중복 정의 금지. `(현행 FAIL)` 없는 항목은 회귀 가드. caplog 는 `logger="src.engine.scheduler"`.

| ID | 시나리오 | 기대 |
|---|---|---|
| F-1 **(현행 FAIL — 핵심)** | positions ∅ · breakout desired `['A','B']` · momentum `[]` · stale = `A,B,X,Y`(X,Y = 매도 완료/이탈 유령) · pool 미구독 | `result == ['A','B']`, X/Y `subscribe` 0회, INFO 에 `desired_low=2 filtered_not_desired=2 filtered_sample=['X', 'Y']` |
| F-2 (현행 FAIL) 페어링 재현 | 스파이 풀에 `_subscriptions`/`get_subscribed_tickers` 상태 부여 → `delta_unsubscribe_dropped(sched, {'A'})` 가 X 해제 → 곧바로 `resubscribe_stale_priority` | X 재구독 0(종전: 되살림), A 는 desired 라 stale 이면 재구독 |
| F-3 (현행 FAIL) HIGH 보호 | positions `['H1']` + NDC `{('N1','vb')}` 모두 stale, breakout desired `['A']`(H1/N1 미포함), LOW 유령 X | result ⊇ `H1,N1`(priority HIGH·bypass True), `filtered_not_desired=1`(X 만 — HIGH 는 집계 밖) |
| F-4 fail-open 게이트 | (a) breakout `[]` + momentum `['Z']`(patch) + LOW stale X → **X 재구독** + `desired_low=0` (b) `_collect_breakout_tickers` raise → X 재구독 (c) `registry.all` raise + breakout `['A']` → X 재구독(HIGH 수집 실패 → skip) (d) `_EmptyRegistry`(`.get` 부재) → 재구독 | (a) 가 §0 ② "momentum 은 게이트 불참" 의 봉인 |
| F-5 (현행 FAIL) momentum 가산 | breakout `['A']`, momentum `['M']`, stale `A,M,X` | result `['A','M']`, X filtered, `desired_low=2` |
| F-6 (현행 FAIL) universe 축출 결합 | registry MagicMock `.get(sid)` → strategy(`config.enabled=True`, `get_scanned_tickers()→['A','U']`) + `sched._universe_excluded_today={'U'}` — **실제 `_collect_breakout_tickers` 경유** | U filtered(desired 이탈), A 재구독. `_universe_excluded_today` 미설정 시 U 통과(getattr 폴백) |
| F-7 (현행 FAIL) 순서 계약(cycle216 T7 확장) | HIGH 3 + LOW 12(`000001~000012`), throttle seed `000001~000004`, desired = LOW 12 ∖ `{000005,000006}` | result = HIGH 3 + LOW `000007~000012`(6) = 9 — 필터→throttle→cap 순서(cap 이 필터 통과분에만). 대조군(desired=LOW 12 전부)은 T7 과 동일 10 |
| F-8 동시호가 병존 | `is_call_auction_now=True` + 필터 활성 + LOW 유령 2 + desired LOW 1 | HIGH 만 result, `[stale_skip_call_auction_priority] low=1`(필터 통과분), `filtered_not_desired=2` |
| F-9 (현행 FAIL) 로그 서식 | 활성/비활성 각각 1회 | 메시지가 `[stale_priority_resubscribe] count=` 로 시작, `desired_low=`·`filtered_not_desired=`·`filtered_sample=` 포함, sample 길이 ≤10(유령 15 주입), 비활성 시 `desired_low=0 filtered_not_desired=0` |
| F-10 관측 실패 격리 | `monkeypatch.setattr(stale_watcher_core, "_collect_low_desired", raise)` | 예외 전파 0, 게이트 off 로 LOW 재구독 정상, `count=` INFO 정상 |
| F-11 부수 상태 | 필터된 X | `_stale_last_resubscribe_at` 에 X 없음 · `_stale_retry_count == {}`(G218-6 동형) · `unsubscribe_in_pool`/`_ticker_to_session.pop` X 에 대해 0회(루프 미진입) |
| F-12 (현행 FAIL) split-brain 보존 | desired LOW `'035420'` 이 **미구독**(`_ticker_to_session` 잔존) + 유령 X 미구독 | 035420 → `._ticker_to_session.pop` + `subscribe(LOW)`(cycle217 계약), X → 어느 seam 도 호출 0. **desired ≠ subscribed 실증**(m5 표적) |
| F-13 기존 회귀 | §5 표적 목록 23파일 | 전부 그대로 PASS(fixture 전부 게이트 off 경로) |

### 4.2 `tests/unit/ast/test_cycle240_ast_desired_filter.py` (신규 — `parents[3]`)

| ID | 검사 | 뮤테이션 표적 |
|---|---|---|
| G-240-1 | `resubscribe_stale_priority` unparse 텍스트 index: `low_targets = [t for t in stale_tickers if t not in high_tickers]` < `_desired_low` 필터 comprehension < `is_call_auction_now(` < `RESUBSCRIBE_THROTTLE_SECS` < `max(0, cap - len(high_targets))` | 필터 위치 이동(throttle/cap 뒤) |
| G-240-2 | 분리 대입 이후 `high_targets` 를 타깃으로 하는 `Assign` 0건 ∧ `_desired_low` 를 참조하는 comprehension 의 iter 가 `low_targets` 뿐 | HIGH 필터 적용 |
| G-240-3 | `_collect_low_desired` 본문: `ImportFrom`/`Import` 에 `src.engine.scheduler` 0 · `Await` 0 · `write_log` 0 · `_collect_breakout_tickers` 호출 존재 · `_last_scan_result` 접근이 `Try` 하위 | scheduler 정적 import·await 삽입 |
| G-240-4 | 호출부: `_collect_low_desired(` 호출이 `Try` 하위 | 예외 전파 |
| G-240-5 | `_filter_active` 대입의 값 표현식 안에 `Name("_breakout_desired")` 존재 ∧ `Name("_momentum_desired")` 부재 ∧ `Name("_high_collect_ok")` 존재 | momentum 게이트 참여·HIGH 플래그 제거 |
| G-240-6 | 종료 `logger.info` 첫 인자 상수가 `"[stale_priority_resubscribe] count=%d tickers=%s"` 로 시작 ∧ `filtered_not_desired=%d` 포함 | 첫 필드/prefix 변조 |
| G-240-7 | HIGH 수집 3 `except` 분기 각각에 `_high_collect_ok = False` Assign 존재(G-12 와 병존 — `update` 호출은 Try 하위 유지) | 플래그 누락 |
| 재스코프 | `test_cycle222a_ast_day_high_scope.py::test_a11b_*` 를 §2.5 로 교체(같은 파일 편집, 신규 파일 아님) | — |

기존 가드 **재작성 금지**(중복) — 표적 실행에 포함만: G-17(cycle67) · GS-6(cycle215) · T6/T7(cycle216) · D-1/D-2(cycle63) · G-6~G-9/G-10~G-13(cycle67) · G-8-B(cycle74) · cycle72 write_log · G218-6(cycle218) · G-AST1(cycle78).

## 5. Green 범위

- `src/engine/stale_watcher_core.py` **단독**: `_collect_low_desired` 헬퍼 + §2.2 (a)(b)(c) + 모듈/함수 docstring 에 cycle240 항목(desired 정의·게이트·순서·로그 필드).
- `tests/unit/ast/test_cycle222a_ast_day_high_scope.py`: a11b 재스코프 + `_git`/`subprocess` 제거(§2.5) — **Red 단계 첫 작업**(이걸 먼저 하지 않으면 core 1줄 수정 즉시 전체 스위트 RED).
- 신규 테스트 2파일(§4.1·§4.2). 인덱스 `python tools/test_impact/build_index.py`.
- **무접촉 기대**: `scheduler.py`(3,999L) · `stale_manager.py` · `stale_session_recovery.py` · `stale_universe_guard.py` · `stale_diagnostics.py` · 8영역 · `scanner.py`(`_last_scan_result` 공개 접근자는 §8 G).
- 표적 실행(Green 후): `python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/ tests/unit/engine/test_scan_loop_stale_priority.py tests/unit/engine/test_breakout_candidate_low_priority.py tests/unit/engine/test_cycle63_phase2A3_delegation.py tests/unit/engine/test_cycle63_phase2A3_dependency_direction.py tests/unit/engine/test_cycle63_phase2A3_import_sanity.py tests/unit/engine/test_cycle63_phase2A3_priority_cap.py tests/unit/engine/test_cycle74_stale_watcher_aggregation.py tests/unit/engine/test_scheduler_stale_tracking.py tests/unit/engine/test_stale_force_reregister_constant_removed.py tests/unit/engine/test_stale_watcher_priority_split.py tests/unit/realtime/test_cycle135_subscribe_grace_period.py tests/unit/realtime/test_cycle92_4_safety_nets_persistence.py tests/unit/ast/test_cycle222a_ast_day_high_scope.py tests/unit/ast/test_cycle240_ast_desired_filter.py tests/unit/ast/test_cycle74_ast_aggregator_helper.py tests/unit/ast/test_cycle78_ast_flush_required.py tests/unit/ast/test_cycle92_g_reject_persistence.py tests/unit/ast/test_external_llm_reject_patterns.py tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py tests/unit/engine/test_refactor_b1_data_load_tasks.py`. 전체 스위트는 Docs 단계 1회.

## 6. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| m1 | 필터 블록 제거(환원) | F-1/F-2/F-5/F-6/F-12 FAIL |
| m2 | 필터를 `stale_tickers`(소스) 또는 `high_targets` 에도 적용 | F-3 FAIL + G-240-2 |
| m3 | 활성 게이트를 `bool(_desired_low)`(momentum 포함) 로 | F-4(a) FAIL + G-240-5 |
| m4 | 필터를 throttle 뒤 / cap 뒤로 이동 | F-7 FAIL + G-240-1 |
| m5 | desired 를 `kis_ws_pool.get_subscribed_tickers()` 로 교체 | F-12 FAIL(미구독 desired LOW 복구 소실) |
| m6 | HIGH 수집 except 에서 플래그 미설정(`_high_collect_ok` 항상 True) | F-4(c) FAIL + G-240-7 |
| m7 | INFO 첫 필드 순서 변경 / prefix 변조 | `test_scan_loop_stale_priority::count=10` + G-240-6 |
| m8 | 헬퍼 안 `from src.engine.scheduler import ...` | G-240-3 + cycle63 D-1 |
| m9 | breakout 을 `strategy.get_scanned_tickers()` 직접 합산(`_universe_excluded_today` 우회) | F-6 FAIL |
| m10 | 필터된 종목에도 `_stale_last_resubscribe_at` 갱신 | F-11 FAIL |
| m11 | 호출부 try 제거(헬퍼 예외 전파) | F-10 FAIL + G-240-4 |
| m12 | `filtered_sample` 무제한 | F-9 FAIL |

추가 렌즈: (i) **차분 실증** — 게이트 off 조건(fixture 23파일)에서 result·subscribe 호출 시퀀스가 현행과 **동일**(행위 변경은 게이트 on 구간에만) (ii) 3 seam 텍스트 순서(GS-6) 재확인 + 새 블록에 `.subscribe(` 문자열 0 (iii) `git diff HEAD --name-only` ⊆ §5 허용 목록, 8영역 경로 한정 가드 PASS (iv) `scheduler.py` `wc -l` 3,999 불변 (v) 헬퍼 비용 — `_collect_breakout_tickers` 는 4 전략 리스트 합산(수천 원소 가능) 5분 1회 → 무시 가능, set 변환 1회.

## 7. D+1 판독 채널

| 채널 | 정상 서명 | 이상 서명 → 해석 |
|---|---|---|
| `[stale_priority_resubscribe]` | 장중 `desired_low>0` · `filtered_not_desired` 대부분 사이클 ≥1(하루 누적 유령 30~80 이 **정상**, `ticker_last_tick` 미정리) · `count` 급감(09-01 993 언급 → 기대 <50/일, 대부분 `count=0`) | 장중 `desired_low=0` 지속 = 게이트 off(4 돌파 전략 후보 0 또는 registry 이상) → 조사. `count` 가 종전 수준 = 필터 미작동 |
| `[scan_loop_delta] unsubscribed=` | 매도·후보 이탈 **시점에만** 발화(09-02 222행 → 기대 수십 행), 직전 사이클 RESUB 종목과의 1:1 페어링 **0** | 페어링 재출현 = 새 소스 누락(예: 어떤 전략 후보가 desired 밖) |
| 페어링 SQL | `system_logs` 에서 `[stale_priority_resubscribe]` tickers 와 5분 뒤 `[scan_loop_delta]` tickers 교집합 = ∅ (timestamp UTC → +9h) | 교집합 ≠ ∅ → 해당 종목의 소속(전략·상태) 추적 |
| `[stale_watcher_detail]` | `stale=` 수·`r=` 분포 감소(유령 5분 점유 소멸) | 불변 = 형제 경로 독립 결함(§8 F) |
| `[stale_priority_resubscribe_cap_exceeded]` | 0 유지 | ≥1 = HIGH>10 — 필터와 무관, 보유 급증 |
| HIGH 회귀 | `/api/realtime/subscriptions` 보유 종목 fresh 비율 불변 · 매도 후 `[unsubscribe]` 정상 · `[universe_excluded]` 빈도 불변 | 보유 종목 stale 증가 = HIGH 경로 훼손(즉시 롤백 사유) |
| KIS SEND 총량 | `[scan_loop_delta]`+`[stale_priority_resubscribe]` 종목언급 합 ≈ 09-02 대비 −80% | — |

⚠️ **의미 반전** — `[stale_priority_resubscribe] count` 감소가 정상. 배포 전후 로그를 같은 grep 으로 합산·비교하지 않는다(cycle228 마커 은퇴 교훈). 배포 = 보유 있으면 KRX 메인 밖(15:30 NXT 애프터 이후 또는 07:55 전, cycle232 D6).

## 8. 후속 등재 (이번 사이클 밖)

- **A. `ticker_last_tick` 매도 시 pop** — 자연 위치 `order_engine._unsubscribe_if_no_other_strategy`(8영역) 또는 별도 정리 훅. 소비처 8곳 영향 평가 + 8영역 승인 필요. 이번 시정으로 **무해화**됐으므로 우선순위 P3.
- **B. `_scan_loop` `new_set` 에 NDC 부재**(`scheduler.py:2457`) — 부팅 복구 창에서 `delta_unsubscribe_dropped` 가 NDC 종목을 해제할 수 있는 잠재(렌즈 2 LOW). scheduler 소관(라인 상한 — 순증 0 편집 필요).
- **C. 사이클 한정 스코프 가드 수명 감사** — cycle222a a11b 동형의 bare `git diff HEAD -- <파일>` 영구 동결이 `test_cycle223f_ast_manual_apply_safeguard.py:236`·`test_cycle223_ast_donchian_exit_fix.py:325` 에 잔존. 다음 그 파일 접촉 사이클이 같은 벽에 부딪힌다 → sha 핀 자기소멸(cycle223 G3 기전) 또는 내용 검사로 일괄 전환.
- **D. `[scan_loop_delta]` `reason` 축** — 매도/후보이탈/universe 축출 구분 필드(관측).
- **E. universe 가드 평가 대상 = `new_set` 한정** — 핑퐁 소멸로 실질 영향 축소, 관측만.
- **F. K watcher(120s) 의 subscribed∖desired 재등록** — 이론상 다음 delta 까지 ≤5분 창. `[stale_watcher_detail]` D+1 이 불변이면 별도 카드.
- **G. `scanner._last_scan_result` 공개 접근자** — private 전역 cross-module read 해소(scanner 8영역 승인 시).

## 9. 문서 동기화 (Docs 단계)

- 루트 `CLAUDE.md` 하네스 표: L69 상단 1행 추가 + 최고령 L83(2026-08-22 cycle224) 제거 → 15행 유지, 한 줄. 제거분은 `docs/HARNESS_CHANGELOG.md` L7(헤더 아래) 최상단 append(verbatim).
- `src/engine/CLAUDE.md`: L16 모듈 맵 `stale_watcher_core.py 399L` → 실측 라인 + "cycle240 desired 교집합" 한 구절 · L548 영속 의무 영역에 "`resubscribe_stale_priority` LOW desired 교집합(breakout ∪ momentum, HIGH 면제, 게이트 = breakout 소유 소스, cycle240)" 불변식 · L710 `_scan_loop()` 문단(cycle215~217 서술 옆)에 cycle240 서술(핑퐁 원인·순서 계약·로그 필드·의미 반전).
- `_workspace/00_URGENT_WORKLIST.md`: `## P1`(L344) 하위 `### P1-5`(L379) 뒤·`## P2`(L416) 앞에 **`### P1-7 · 5분 우선 재구독 핑퐁 — ✅ cycle240 종결`** 신규(실측·원인·시정·D+1 채널·후속 A~G).
- `_workspace/00_leader_trading_rules.md`: 파라미터 변경 0 — 무변경.
- 커밋·푸시 사용자 지시 대기.

## 10. 적대 검증 확증/시정 (cycle240-R1)

**대상 = 3렌즈 적대 검증(총 5건 보고, 실질 1개 결함 + 1개 범위 밖 후보) — backend-dev/tdd-engineer 겸임 수행.**

### 10.1 확증 시정 — F-8 테스트 픽스처 결함 (보고 #1/#2/#3/#5, 동일 근본원인 4중 확증)

- **판정**: 구현(`src/engine/stale_watcher_core.py`) 결함 **아님** — `tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py::test_f240_8_call_auction_warning_counts_filtered_survivors` 단독 결함. 재구독 필터 자체(§2.2 (a)(b)(c))는 무접촉·무변경.
- **근본원인**: F-8 이 cycle216 재사용 헬퍼 `_capture_scheduler_warnings()`(`test_cycle216_priority_throttle_call_auction.py:142-153`)를 `caplog.set_level(logging.INFO, ...)` 뒤에 병용 — 그 컨텍스트가 `with` 블록 동안 `src.engine.scheduler` 로거 레벨을 **WARNING** 으로 올려 caplog 의 INFO 설정을 덮어쓴다. 그 결과 종료 `logger.info("[stale_priority_resubscribe] ...")`(`stale_watcher_core.py:610` 부근)가 **방출 단계에서 버려져** caplog 핸들러에 도달하지 못하고, `_info_lines(caplog)[0]` 가 빈 리스트에서 `IndexError`.
- **Red 재현(시정 전, 격리 실행)**: `python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py::test_f240_8_call_auction_warning_counts_filtered_survivors` → `IndexError: list index out of range` at `:581`. Captured log 에는 `WARNING src.engine.scheduler:stale_watcher_core.py:542 [stale_skip_call_auction_priority] low=1 skip` 만 존재 — `low=1` 은 **정확**(필터 통과분, 유령 2 는 이미 걸러짐) = 구현 §2.2 행위는 시정 전부터 옳았다는 방증.
- **시정(테스트 파일 단독, src 무변경)**: F-8 에서 `_capture_scheduler_warnings()` 컨텍스트 사용을 제거하고, 이미 걸린 `caplog.set_level(logging.INFO, logger="src.engine.scheduler")` 하나로 WARNING·INFO 를 동시 캡처(`caplog.records` 에서 `r.levelno == logging.WARNING` 필터로 `[stale_skip_call_auction_priority]` 를 선별, INFO 는 기존 `_info_lines(caplog)` 그대로). import 목록에서 미사용이 된 `_capture_scheduler_warnings` 제거(주석으로 사유 명시, 다른 파일의 정의는 무접촉).
- **Green 재검증**:
  - F-8 격리: `python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py::test_f240_8_call_auction_warning_counts_filtered_survivors` → **1 passed**.
  - 신규 파일 전체: `python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py` → **18 passed**.
  - §5 표적 세트(23파일, stale_manager 디렉토리 + AST + 형제 stale 회귀 + cycle63/72/74/78/92): `python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/ tests/unit/engine/test_scan_loop_stale_priority.py tests/unit/engine/test_breakout_candidate_low_priority.py tests/unit/engine/test_cycle63_phase2A3_delegation.py tests/unit/engine/test_cycle63_phase2A3_dependency_direction.py tests/unit/engine/test_cycle63_phase2A3_import_sanity.py tests/unit/engine/test_cycle63_phase2A3_priority_cap.py tests/unit/engine/test_cycle74_stale_watcher_aggregation.py tests/unit/engine/test_scheduler_stale_tracking.py tests/unit/engine/test_stale_force_reregister_constant_removed.py tests/unit/engine/test_stale_watcher_priority_split.py tests/unit/realtime/test_cycle135_subscribe_grace_period.py tests/unit/realtime/test_cycle92_4_safety_nets_persistence.py tests/unit/ast/test_cycle222a_ast_day_high_scope.py tests/unit/ast/test_cycle240_ast_desired_filter.py tests/unit/ast/test_cycle74_ast_aggregator_helper.py tests/unit/ast/test_cycle78_ast_flush_required.py tests/unit/ast/test_cycle92_g_reject_persistence.py tests/unit/ast/test_external_llm_reject_patterns.py tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py tests/unit/engine/test_refactor_b1_data_load_tasks.py tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` → **198 passed, 5 xfailed, 0 failed**(시정 전 197 passed/1 failed/5 xfailed 에서 실패 1건이 통과로 전환 — 총 수 불변, 다른 회귀 0건).
  - `src/engine/stale_watcher_core.py` diff = 이번 라운드 무변경(§2.2 구현은 R1 이전에 이미 완료돼 있었음 — R1 은 테스트 파일 1개만 편집).

### 10.2 범위 밖 확인 — 보고 #4 뮤테이션 m5a (`resubscribed.append`/타임스탬프 순서)

- **판정**: cycle240 diff 밖(사이클 28/216 기존 `resubscribe_stale_priority` 루프 본문, §2.2 신규 블록과 무관) — 이번 사이클이 만든 회귀가 아니라 **기존 커버리지 공백**. tester 보고 자체가 "실트리 미추가 — 원복 계약 준수"로 결론(mutation 검증은 사본 저장소에서만 수행, `/private/tmp/.../scratchpad/mut_repo/` 하위).
- **본 라운드 처리**: R1 허용 파일 목록(§ 서두)에 해당 없음 + tester 의 자체 결론을 존중해 실트리 무변경. `§8 후속 등재` 에 항목 H 로 등재(아래) — 별도 사이클에서 `resubscribed.append`/`_stale_last_resubscribe_at` 갱신을 `subscribe` 성공 **이후**로 못박는 회귀 테스트 추가 여부를 결정한다(현재는 cycle216 throttle/cycle29 force_retry 가 그 타이밍에 실운영 의존하지 않는지 별도 확인 필요 — 도메인 영향 미평가).

### 10.3 §8 후속 등재 추가

- **H. `resubscribed.append`/`_stale_last_resubscribe_at` 대입이 `await kis_ws_pool.subscribe(...)` 성공 확인 전에 일어난다**(사이클 28/216 기존 루프, cycle240 diff 밖) — subscribe 가 예외 없이 던지기만 해도 결과·타임스탬프가 이미 찍혀 throttle(180s)/force_retry 게이트가 "방금 재구독 성공"으로 오판할 수 있는 잠재 경로. tester 사본 검증(`test_cycle240_tester_m5a_stamp_after_success.py`, 실트리 미추가)이 뮤턴트에서 FAIL 실증. 다음 stale_watcher_core 접촉 사이클에서 순서 보정 + 회귀 테스트 여부 판단(§ 참고: `stale_watcher_core.py` 자체는 이번 라인 상한 제약 없음 — scheduler.py 만 헤드룸 0).

### 10.4 최종 표적 결과 (R1 종료 시점)

```
python -m pytest -q -p no:cacheprovider tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py
→ 18 passed

python -m pytest -q -p no:cacheprovider <§5 표적 21파일+디렉토리>
→ 198 passed, 5 xfailed
```

전체 백엔드 스위트(참고용 보조 확인 — Docs 단계 정식 1회는 §11 에서 별도 기입):
`python -m pytest -q -p no:cacheprovider` → **5963 passed, 10 skipped, 328 xfailed, 13 xpassed** (exit 0, 196.55s). FAIL 0.

## 11. Docs 단계 최종 상태 — 착수 후 기입

**기입: team-leader, 2026-09-02 22:5x KST.**

- 문서 동기화 완료: 루트 `CLAUDE.md` 하네스 표 상단 1행(cycle240) 추가 + 최고령(2026-08-22 cycle224) 1행 제거 = 15행 유지
  (cycle224 상세는 `docs/HARNESS_CHANGELOG.md` L21 에 이미 존재 — 이동 불요) · `docs/HARNESS_CHANGELOG.md` 표 최상단 cycle240 상세 1행 append ·
  `src/engine/CLAUDE.md` L16 모듈 맵(399L → 619L, 헬퍼 명시) + L548 영속 의무(LOW desired 교집합 불변식) + L710 `_scan_loop()` 문단 cycle240 서술 +
  L713 `_stale_watcher_loop()` 문단 형제 경로 무결함 주석 · `_workspace/00_URGENT_WORKLIST.md` `### P1-7`(P1-5 뒤·P2 앞) 신설 ·
  `_workspace/00_leader_trading_rules.md` 무변경(파라미터 0).
- 인덱스: `python tools/test_impact/build_index.py` 재실행(신규 2 테스트 파일 매핑 확인).
- 전체 백엔드 스위트(Docs 단계 정식 1회): `find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q -p no:cacheprovider` → **5963 passed, 10 skipped, 328 xfailed, 13 xpassed in 206.34s (exit 0, FAIL 0)**
- 변경 파일 확정(`git status --short` / `git diff HEAD --stat`): src = `stale_watcher_core.py` 단독(+61/-4) · 8영역 diff 0 · `scheduler.py` 3,999L 불변 ·
  facade/recovery diff 0. 타 에이전트 untracked 산출물(`_workspace/pyramiding_review_20260903/`·`morning_0903_report.md`·`domain_consult/pyramiding_deep_review_20260903.md`) 무접촉.
- 커밋·푸시: 사용자 지시 대기. 배포 권고 = 20:10 정산 이후 야간 창(현재 시각 해당) 또는 익일 07:55 `_boot` 전 — 부팅 직후엔 breakout 이 비어 게이트 off(현행 byte 동일)이고
  필터는 09:30~ `_scan_loop` 첫 이터레이션부터 켜지므로 장중 재시작 위험 0. 롤백 기준 = D+1 보유 종목 stale 증가(HIGH 경로 훼손 서명).
