# cycle241 — silent_inactive 오판 시정: 세션 상대 판정 (08-31 포렌식 결함 ⓐ MEDIUM · 워크리스트 P1-4)

작성: team-leader, 2026-09-02 야간. 사용자 위임("대부분의 결정요소는 직접 권장하는대로 진행"). 3렌즈 진단(logic·evidence·tests)
검토 + 코드 재실측 후 확정. 착수 컨텍스트의 **전제 정정 3건**은 §0 하단에 명시(수치 정정이며 결론 L1 채택은 그대로 유효).

> **워킹트리 상태**: HEAD `140a79a`(cycle240 커밋) 기준 트리 클린. untracked 3건(`_workspace/pyramiding_review_20260903/` ·
> `_workspace/morning_0903_report.md` · `_workspace/domain_consult/pyramiding_deep_review_20260903.md`)은 타 작업 산출물 — **무접촉**.
> **git commit / push / stash / checkout / restore 금지.**

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py · strategy_registry.py)
> + **scheduler.py 무접촉**(실측 **3,999L**, 상한 4,000 = 헤드룸 1 — 이번 사이클은 순증 0 이 아니라 **diff 0**: 호출부 `:3024-3029` 와
> wrapper `:3195-3198` 은 이미 필요한 형태다) + `stale_manager.py` facade 무접촉(신규 export 0 — 상수·상태·헬퍼 전부 private)
> + `stale_diagnostics.py` · `stale_watcher_core.py` · `stale_universe_guard.py` 무접촉. src 변경 = **`src/engine/stale_session_recovery.py` 단독**.

## 0. 결정 요약 (착수 질문 ①~⑧)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | 상대 판정 삽입 위치 + '판정 가능 세션' 정의 | **first_seen 누적 앞**. 함수를 2-pass 로 재구성 — pass 1 이 세션별 `(label, subscribed, silent_suspect)` 를 **상태 무변경**으로 계산 → 상대 판정 게이트 → pass 2 = 기존 누적 루프(사이클 24/29-R2 식 byte 동일, 입력만 튜플). **판정 가능 세션 = `subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED`(기존 상수 재사용, 신규 임계 없음)**, 개수는 **리스트 길이**로 센다(라벨 set 아님 — `unknown` 라벨 충돌 오염 차단). **시장 침묵 = `eligible >= _MARKET_WIDE_MIN_ELIGIBLE(=2)` ∧ `silent == eligible`** | 반환 직전 필터는 침묵 구간 동안 first_seen 이 계속 자라므로 시장이 재개돼 **한 세션만 늦게 깨어나는 순간 elapsed ≥ 300 이 이미 성립 → 즉발** = 오판이 재개 경계로 이동할 뿐이다. 그 성질을 가진 세션이 실재한다(main — 야간 무거래 우선주 8종목, 09-02 15:40:33 재개 시 4/8 · 16:05 1/8). `silent_suspect` 가 이미 `subscribed >= 5` 를 포함하므로 `silent <= eligible` 항등 → `==` 비교가 곧 "판정 가능 전원 침묵". `subscribed < 5` 세션은 원래도 suspect 가 될 수 없어 분모에서 빼는 것이 현행과 정합 |
| ② | 전 세션 침묵 시 처리 | **기각 + 현재 `sessions` 의 전 라벨 `first_seen` pop** + `return []`. '보류(누적 정지, 값 유지)' 기각 | 보류면 에피소드 이전에 무장된 first_seen(예: 15:15 부터 main 단독 침묵 → 15:20 전원 침묵)이 살아남아 재개 직후 첫 사이클에 즉발(§4 F-7 이 hold 변형을 검출). pop 이면 재개 시점부터 다시 5분을 세므로 **"침묵 종료 후 5분 뒤 진짜 결함만"** 성질 보존. `dict.clear()` 가 아니라 라벨별 `pop` — 현재 세션 목록 밖의 키(비활성화된 세션 잔재)는 손대지 않아 테스트 결정성 유지(어차피 20:10 `reset_daily` 가 일괄 clear) |
| ③ | 단일 세션·비교 불가 | **`eligible < 2` → 현행 byte 동일(fail-open = 현행)**. `eligible == 0` 은 현행 루프가 이미 전부 pop 후 `[]` | 비교 대상이 없으면 "그 세션만 죽었다" 도 "시장이 조용하다" 도 성립하지 않는다 — 원래 설계(사이클 24/29-R2)를 그대로 둔다. 부수 효과 = 기존 silent_inactive 회귀 **15 케이스 전부 단일 `main` 픽스처**라 무수정 통과(저장소 전체 다중 세션 픽스처 0건 실측). 운영 8세션·VTS 단일 세션 모두 "현행보다 나빠지는 입력" 이 없다 — **결과 집합 ⊆ 현행 결과 집합**(순수 축소 방향)이 설계 불변식 |
| ④ | 08-31 형 전 세션 실제 두절 트레이드오프 | **상대 판정 채택, 보조 조건(장중 N분 지속 시 1회 허용) 불채택**. 가시성은 기존 `[tick_coverage] ratio=0.0%` WARNING(5분) + 신규 `transition=persisting` WARNING(30분 이상 지속 시 30분마다)이 담보 | 렌즈 1(d)·2(c) **독립 일치**: 08-31 88회·08-12 40회 재연결의 회복 가치 **0**(재등록 실패가 20:08 종료까지 지속, 회복은 익일 07:5x 부팅), 평상일도 재연결 2분 뒤 8세션 여전히 fresh=0 → 회복 시각은 항상 `_BOARD_SCHEDULE` POST_NXT 진입 15:40 과 일치 = 시장 재개가 원인. 30일 522건 중 **09:00~15:20 정규장 0건**. 에스케이프 해치는 근거 표본 0 인 시나리오에 코드·뮤테이션 표면만 늘린다 → §8 E 로 재검토 트리거(장중 market_wide 에피소드 ≥10분 실측)만 등재 |
| ⑤ | 시장 상태 보조 신호(8영역 읽기만) | **게이트에 미사용**. `is_call_auction_now` · `boards_at` · `last_nxt_mkop_code` · `ticker_last_tick` 전수 신선도 전부 불채택. 유일한 채택 = 이미 소비 중인 `get_session_status()` dict 의 `ws_connected` 를 **마커 진단 필드 `connected=`** 로만 병기(`.get` graceful — 기존 5min 픽스처는 키 부재) | (a) 운영 8세션에서 L1 단독이 3 슬롯 전부(94.1%)를 덮으므로 동시호가 게이트는 **무효 코드**가 되고, 단일 세션 풀(VTS/개발)에서만 살아 있는 코드는 아무도 보지 않는 환경에서만 도는 부채다 (b) 15:30~15:40 D 슬롯(22.4%)은 `boards_at` 이 의도적 MAIN 갭 마진이라 어떤 시각 표로도 못 닫는다 — **세션 비교만이 닫는다** (c) 이질 게이트 2개면 D+1 마커가 `reason` 으로 갈려 판독이 흐려지고 뮤테이션 표면 2배 (d) `session_tracker._last_nxt_mkop_code` 는 cycle162 테스트가 직접 대입·복원하는 프로세스 전역 — 순서 누수 시 게이트가 뒤집힌다 (e) Q1 import 표면(scanner · websocket_pool · websocket · stale_diagnostics)에 `session` 을 더하지 않는다(AST G-241-5 로 봉인). `ws_connected` 를 게이트에 안 쓰는 이유 = `_ws is None` 이면 `force_reconnect_session` 이 어차피 skip 하므로 결과가 안 바뀐다 — 대신 08-31 형에서 `connected=0/8` 이 소켓 사망을 즉시 말해 주므로 진단 필드로는 가치 있음 |
| ⑥ | 관측 마커·cap | prefix **`[silent_inactive_market_wide_skip]`** 고정, 첫 필드 `transition=` (cycle233 `[account_risk_gate]` 선례). **entered**(INFO, 에피소드 진입 1회) · **exited**(INFO, 이탈 1회, `elapsed_secs`·`cycles` 동반) · **persisting**(WARNING, 지속 ≥ `_MARKET_WIDE_PERSIST_WARN_SECS=1800` 이후 1800s 마다). 상태 = **모듈 전역 `_MW_EPISODE` dict**(날짜 키 자기 리셋, 테스트용 `reset_market_wide_episode_state()` export). cap 상태(`since`·`last_warn_at`)는 **peek→로그→mark**, 실패 흔적 `[silent_inactive_market_wide_skip_failed]` WARNING 1회/일. `write_log` 0(cycle72) | 에피소드당 1회만 캡하면 08-31 형 4시간 두절이 **1줄로 축약**된다(렌즈 1) — exited 의 `elapsed_secs` 가 3분(08:5x→09:00)·19분(15:2x→15:40) 정상 vs 수 시간 이상을 가르고, persisting 이 30분 넘는 지속을 30분마다 알린다(4시간 두절 = 8행 상한). 정상 최장 에피소드 = 15:20→15:40 **1,200s** 라 1,800 은 1.5배 마진(수능일 10:00 개장은 예외로 WARNING 1~2행 = 무해). `StaleTrackerState` 는 **7필드 정확 일치 가드 2벌**(cycle61/63 F-1/F-2)이 신규 필드를 거부하고 `_reset_daily_state` 훅은 scheduler 편집이라 모듈 전역이 유일한 무충돌 위치(cycle237 `DailyEmitCap`+날짜 키 선례). 시각은 전부 함수 안 `now`(KST aware, `_dt.now(_KST_TZ)`)에서 파생 — freezegun/`patch(scheduler.datetime)` 양쪽 호환, monotonic 미사용 |
| ⑦ | '본체 동일' 가드 재스코프 | **기계 가드 없음 — 처분 대상은 산문 4곳 + 정본 문서 1곳**. `stale_session_recovery.py:7`(모듈 docstring "함수 본체 변경 0") · `:11`(Q1 문구 — G-7 실제 검사보다 과하게 서술, `:35` 의 `stale_diagnostics` import 가 이미 그 문구와 모순) · `:40-41`(인라인 "행위 변경 0건 의무") · `:44`("L2423 본체 그대로 이주") + `src/engine/CLAUDE.md:721` "함수 본체 라인 단위" 서술 | 3렌즈 독립 일치 + grep 재확인: 이 파일에 대한 `ast.unparse` 본문 핀·라인수 단언 **0건**(본문 핀은 `stale_watcher_core`/`stale_diagnostics` 함수만, cycle194 G-194-4 는 `force_reconnect_session` 한정). 살아 있는 계약 = D-2 패턴 카운트(≥4 합산, 이 파일 3) · G-6 logger · G-7 단방향(**watcher_core 만 금지**) · cycle72 write_log 0 · G-ERR2 문자열 존속 — 전부 §3 에 보존. 나머지 2 함수(`force_reconnect_session`·`delta_unsubscribe_dropped`)는 **diff 0** 이 계약이며 신규 본문 핀은 만들지 않는다(cycle240 §8 C — 사이클 한정 동결의 수명 초과 재발 방지) |
| ⑧ | 정본 문서 문구 | 루트 `CLAUDE.md:167` 항목에 **세션 상대 판정** 절 추가(문안 §9) + 하네스 표 1행 + `src/engine/CLAUDE.md` 3곳 + 워크리스트 P1-4 종결 | §9 |

**domain-consult 불요(`needs_domain_consult=false`)** — WebSocket 세션 복구 배관. 진입·청산 파라미터 0, 매수/매도 신호 경로 무접촉, 보유 종목 시세 보장은
**강화 방향**(개장 3분 전·NXT 애프터 개장 1분 전에 하필 8세션 close → 전 구독 재SEND → 60초 F1 재검증이 반복되던 공백이 사라진다). ④ 의 트레이드오프는
시장 행태가 아니라 "재연결이 무엇을 고쳤는가" 의 실측 문제이고 답이 0 이라 공학 결정으로 닫는다.

### 착수 컨텍스트 전제 정정 (3렌즈 실측, 결론 불변)

1. **"동시호가 게이트 이식만으론 4% 해결"** → 실측 **54.4%**(284/522, `is_call_auction_now` 창 08:30~09:00 ∪ 15:20~15:30). 그래도 L1 이 필요한 이유는
   그대로다 — 잔여 45.6% 중 D 슬롯 15:30~16:00(117건 22.4%)은 `boards_at` MAIN 갭 마진·`is_call_auction_now` 121 창 상한 15:35 어느 쪽도 못 닫고,
   15:40:33 정각 8세션 동시 회복이 그 구간이 구조적 무틱임을 증명한다. "400/416 건이 장 마감 후" 는 08-12·08-31 저녁의 `[silent_inactive_recovery_cap]`(406·632건)이
   섞인 표본이다 — `force_reconnect` 만 세면 A 27.2 / C 27.2 / D 22.4 / E 10.9 / F 12.3%.
2. **D+1 기대 "24/일 → 0~수건"** → **0~3건/일**. main 세션 단독 침묵(09-02 16:05·18:18·18:59, sub=8 분해능 1/8 × 야간 무거래 우선주)은 타 7세션이 fresh 라
   상대 판정을 **통과해 계속 발화**한다 — 설계상 옳다(비교 대상이 fresh). 이 잔여는 L1 밖 별개 축(§8 A).
3. **skip 마커 슬롯 "08:58·15:27·15:39"** → 마커는 발화 시각이 아니라 **에피소드 진입 시각**에 찍힌다: 전원 침묵은 NXT 프리 마감 08:50 · 연속매매 종료 15:20 직후
   `STALE_FRESHNESS_SECS=60` 이 지나면 성립하므로 `entered` 는 **≈08:51~53 · ≈15:21~23**, `exited` 는 ≈09:00~02 · ≈15:40~42 다. 종전 15:27 과 15:39 두 발화는
   `force_reconnect_session` 이 first_seen 을 pop 해 5분 카운트가 다시 돌던 **인공 분할**이라 L1 아래선 **한 에피소드로 병합**된다. 07:59 presubscribe~08:00
   NXT 프리 개장 사이에 K 사이클이 걸리면 3번째 짧은 에피소드가 생긴다 → 평상일 `entered` **2~3행**.

## 1. 확증된 원인 (3렌즈 코드 실측 + EC2 read-only)

| 사실 | 근거 |
|---|---|
| `detect_silent_inactive_sessions` 는 세션마다 **독립적으로** `fresh_ratio < 0.2 ∧ subscribed ≥ 5 ∧ 5분` 을 판정한다. 세션 간 비교·시장 상태 참조 0 — "8세션이 같은 초에 전부 침묵" 을 "8개 동시 고장" 과 구분할 방법이 코드에 없다 | `src/engine/stale_session_recovery.py:79-113`(단일 루프, `:104-113` first_seen 누적) · 호출 `scheduler.py:3024-3029`(120s K 루프) |
| 30일 522건 중 **491건(94.1%)이 그 시점 세션 풀 전원 동시 발화** — 버스트 크기가 풀 증설 시기(5→7→8)와 정확히 일치. 09-01/09-02 는 8행이 **동일 timestamp**(단일 K 이터레이션). 단독 발화 15건(2.9%) 전부 16:00 이후 main | EC2 `system_logs` `[silent_inactive_force_reconnect]` 분 단위 버스트 히스토그램(렌즈 2 (a′)) |
| 정규장 09:00~15:20 발화 **0건**. 슬롯 = 장전 동시호가 27.2% / 장후 동시호가 27.2% / 15:30~16:00 22.4% / 16:00~18:00 10.9% / 18:00~ 12.3% | 렌즈 2 (a″) |
| 재연결의 회복 가치 0 — 09-01 15:36:35 재연결 → 15:38:46 8세션 여전히 fresh=0 → **15:40:51 8세션 동시 회복** = `_BOARD_SCHEDULE` POST_NXT 진입. 08-31: 16:02 WS 닫힘 이후 20:08 종료까지 `[stale_watcher] 강제 재등록 실패` 지속, 88회 재연결 + cap 632건, 회복은 익일 07:5x 부팅 | `[stale_watcher_detail]` fresh/sub 시계열(`stale_diagnostics.py:83,125` 가 같은 `STALE_FRESHNESS_SECS` 라 `fresh_ratio` 와 동일 정의) · `session.py:61-68` |
| 비용 = 재연결 1회당 접속키 발급 1(무캐시 `token.py:183`, 재연결 루프 첫 줄 `websocket.py:213`) + 세션 전 구독 재SEND(`_restore_subscriptions_after_reconnect`) + 60초 F1 재검증, 발화 시각이 08:57(개장 3분 전)·15:39(NXT 애프터 1분 전). 09-02 접속키 53건 중 **27건(50.9%)** 이 silent_inactive 발 | EC2 `auto_stock.log` `접속키 발급 완료` 분 단위 집계 |
| 시간당 세션당 2회 cap 이 유일한 방파제 — 08-31 장애일 cap-skip 632 : 재연결 88 | `force_reconnect_session:154-163` |
| 형제 `check_and_resubscribe_stale` 는 같은 K 루프 안에서 `is_call_auction_now` 로 매일 정확히 20건 `[stale_skip_call_auction]` 을 발화하는데 이 함수만 그 신호를 안 봤다 — 그러나 §0 ⑤ 대로 **이식하지 않는다**(D 슬롯 미커버 + 운영 무효 코드) | `stale_watcher_core.py:198-199` |
| `StaleTrackerState` 는 **7필드 정확 일치**를 두 가드가 단언(F-1 set 동등 + F-2 dict/set 외 타입 raise) → 마커 cap 상태를 필드로 못 넣는다. `scheduler.py` 3,999L → `_reset_daily_state` 훅 추가 불가. 유일 위치 = 모듈 전역 + 날짜 키 자기 리셋 | `tests/unit/engine/test_cycle61_phase2A2_dataclass_completeness.py:24-95` · 동형 cycle63 · `donchian_swing.py:204-246`(cycle237 선례) |
| 위임 가드가 `assert_called_once_with(sched)` 로 **인자 1개**를 핀 → 상대 판정 재료(세션 목록)는 함수 안에서 이미 fetch 하는 `sessions` 로 계산해야 한다(인자 추가 금지) | `tests/unit/engine/test_cycle61_phase2A2_delegation.py:38-53` |
| 기존 회귀 픽스처는 **전부 단일 `main` 세션**(ratio 9 · recovery 4 · 5min 1) → `eligible < 2` fail-open 이면 전량 무수정 통과. 다중 세션 픽스처는 저장소 전체 0건 = 이번 Red 가 처음 만든다 | `test_session_silent_inactive_ratio.py:88-282` 등 grep |
| 렌즈 3 정정: 모듈 docstring `:11` 은 "3 모듈 import 금지" 라 쓰지만 G-7 은 **`stale_watcher_core` 만** 검사하고 `:35` 는 이미 `stale_diagnostics` 를 import 한다 — 문구가 가드보다 엄격해 거짓. Phase 1 에서 가드와 일치시킨다 | `test_cycle67_dependency_logger_g6_g9.py:96-145` |

## 2. 시정 설계 (`src/engine/stale_session_recovery.py` 단독)

### 2.1 신규 private 상수·상태·헬퍼 (모듈 레벨, 기존 5 상수 블록 아래)

```python
# ── cycle241 세션 상대 판정 (private — facade 미노출, 5 상수 SoT 와 별개) ──────────
_MARKET_WIDE_MIN_ELIGIBLE = 2            # 비교 가능 최소 판정 가능 세션 수. 미만 = 현행 유지(fail-open)
_MARKET_WIDE_PERSIST_WARN_SECS = 1800.0  # 에피소드 지속 WARNING 첫 발화·재발화 간격 (정상 최장 15:20→15:40 1,200s × 1.5)

# 에피소드 관측 상태 — StaleTrackerState(7필드 정확 일치 가드)·scheduler(3,999L) 어느 쪽에도 못 두므로 모듈 전역.
# 날짜 키 자기 리셋(cycle237). 행위(기각·pop)는 이 dict 를 읽지 않는다 — 관측 전용.
_MW_EPISODE: dict[str, Any] = {
    "day": "", "since": None, "cycles": 0, "last_warn_at": None, "fail_warned_day": "",
}

def reset_market_wide_episode_state() -> None:
    """테스트 전용 — 에피소드 관측 상태 초기화 (facade 미노출, 운영 호출처 0)."""
    _MW_EPISODE.update(day="", since=None, cycles=0, last_warn_at=None, fail_warned_day="")

def _count_connected(sessions: Any) -> int:
    """`ws_connected is True` 세션 수 — 진단 필드 전용. 키 부재·비 dict 는 0 (5min 픽스처 호환)."""
    try:
        return sum(1 for s in sessions if isinstance(s, dict) and s.get("ws_connected") is True)
    except Exception:
        return 0

def _observe_market_wide(now: datetime, *, sessions_n: int, eligible_n: int, silent_n: int,
                         connected_n: int, reset_n: int) -> None:
    """시장 침묵 기각 관측 — entered(INFO 1회) / persisting(WARNING, ≥1800s 후 1800s 마다). never-raise.

    peek→로그→mark: `since`(entered) · `last_warn_at`(persisting) 은 로그 성공 **뒤**에 기록.
    `cycles` 는 카운터라 cap 대상이 아니다. 날짜 키가 바뀌면 상태를 먼저 비운다.
    """
    try:
        day = now.date().isoformat()
        if _MW_EPISODE["day"] != day:
            _MW_EPISODE.update(day=day, since=None, cycles=0, last_warn_at=None)
        if _MW_EPISODE["since"] is None:                       # peek
            logger.info(
                "[silent_inactive_market_wide_skip] transition=entered sessions=%d eligible=%d "
                "silent=%d/%d connected=%d reset=%d",
                sessions_n, eligible_n, silent_n, eligible_n, connected_n, reset_n,
            )                                                   # 로그
            _MW_EPISODE.update(since=now, cycles=1, last_warn_at=None)   # mark
            return
        _MW_EPISODE["cycles"] += 1
        elapsed = (now - _MW_EPISODE["since"]).total_seconds()
        ref = _MW_EPISODE["last_warn_at"] or _MW_EPISODE["since"]
        if (elapsed >= _MARKET_WIDE_PERSIST_WARN_SECS
                and (now - ref).total_seconds() >= _MARKET_WIDE_PERSIST_WARN_SECS):   # peek
            logger.warning(
                "[silent_inactive_market_wide_skip] transition=persisting elapsed_secs=%d cycles=%d "
                "sessions=%d eligible=%d silent=%d/%d connected=%d",
                int(elapsed), _MW_EPISODE["cycles"], sessions_n, eligible_n, silent_n, eligible_n, connected_n,
            )                                                   # 로그
            _MW_EPISODE["last_warn_at"] = now                   # mark
    except Exception:
        _trace_market_wide_failure(now)

def _close_market_wide_episode(now: datetime) -> None:
    """열린 에피소드가 있으면 exited(INFO 1회) 후 상태 해제. never-raise. 없으면 no-op."""
    try:
        if _MW_EPISODE["since"] is None:
            return
        elapsed = (now - _MW_EPISODE["since"]).total_seconds()
        logger.info(
            "[silent_inactive_market_wide_skip] transition=exited elapsed_secs=%d cycles=%d",
            int(elapsed), _MW_EPISODE["cycles"],
        )                                                       # 로그
        _MW_EPISODE.update(since=None, cycles=0, last_warn_at=None)   # mark
    except Exception:
        _trace_market_wide_failure(now)

def _trace_market_wide_failure(now: datetime) -> None:
    """관측기 자기 실패 흔적 — WARNING 1회/일 + debug 스택 (cycle225 J-3: debug 단독은 `_DbLogHandler` INFO 컷을 못 넘는다).
    가장 안쪽은 어떤 경우에도 조용히 통과."""
    try:
        logger.debug("[silent_inactive_market_wide_skip_failed]", exc_info=True)
        day = now.date().isoformat()
        if _MW_EPISODE.get("fail_warned_day") != day:
            logger.warning("[silent_inactive_market_wide_skip_failed] observer raised — 기각 행위는 수행됨")
            _MW_EPISODE["fail_warned_day"] = day
    except Exception:
        pass
```

- 신규 import 0(`Any`·`datetime` 은 이미 import). `DailyEmitCap` 도 불요(에피소드는 전이형이라 set 이 아니라 시각 2개).
- 헬퍼 이름·`_MW_EPISODE` 는 모듈 private. `reset_market_wide_episode_state` 만 테스트가 `from src.engine.stale_session_recovery import` 로 쓴다(facade 경유 금지 — G-16 은 `stale_manager.X` patch 만 검사하지만 `__all__` 을 늘리지 않는 것이 facade 무접촉 계약).

### 2.2 `detect_silent_inactive_sessions` 본문 재구성 (2-pass)

```python
    sessions = kis_ws_pool.get_session_status()
    now = _dt.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt.min.replace(tzinfo=_KST_TZ)
    silent_labels: list[str] = []

    # ── pass 1 (cycle241): 세션별 판정 재료 — 상태 무변경. fresh/ratio/suspect 식은 사이클 29-R2 byte 동일.
    judged: list[tuple[str, int, bool]] = []          # (label, subscribed_count, silent_suspect)
    for s in sessions:
        label = s["label"]
        subscribed_count = s["subscribed"]
        subscribed_tickers = s["tickers"]["subscribed"]
        fresh_count = sum(1 for t in subscribed_tickers if (now - ticker_last_tick.get(t, min_dt)) <= threshold)
        if subscribed_count > 0:
            fresh_ratio = fresh_count / subscribed_count
        else:
            fresh_ratio = 0.0
        silent_suspect = (
            fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD
            and subscribed_count >= SILENT_INACTIVE_MIN_SUBSCRIBED
        )
        judged.append((label, subscribed_count, silent_suspect))

    # ── cycle241 세션 상대 판정: 판정 가능 세션(sub ≥ MIN) 이 2개 이상이고 전부 침묵이면 시장 침묵 → 기각.
    eligible_n = sum(1 for (_l, n, _s) in judged if n >= SILENT_INACTIVE_MIN_SUBSCRIBED)
    silent_n = sum(1 for (_l, _n, s) in judged if s)
    _market_wide = eligible_n >= _MARKET_WIDE_MIN_ELIGIBLE and silent_n == eligible_n
    if _market_wide:
        # 행위 (cap 밖): 전 라벨 first_seen pop — 누적 금지. 재개 시점부터 다시 5분을 센다.
        reset_n = sum(
            1 for (label, _n, _s) in judged
            if scheduler._silent_inactive_first_seen.pop(label, None) is not None
        )
        # 관측 (예외 흡수): 에피소드 entered/persisting
        _observe_market_wide(now, sessions_n=len(judged), eligible_n=eligible_n, silent_n=silent_n,
                             connected_n=_count_connected(sessions), reset_n=reset_n)
        return []
    _close_market_wide_episode(now)                    # 열린 에피소드 있으면 exited 1행

    # ── pass 2: 사이클 24/29-R2 누적 루프 — 입력만 judged 튜플, 분기·대입·pop 위치 byte 동일.
    for (label, _n, silent_suspect) in judged:
        if silent_suspect:
            if label not in scheduler._silent_inactive_first_seen:
                scheduler._silent_inactive_first_seen[label] = now
            elapsed = (now - scheduler._silent_inactive_first_seen[label]).total_seconds()
            if elapsed >= SILENT_INACTIVE_PERSIST_SECS:
                silent_labels.append(label)
        else:
            scheduler._silent_inactive_first_seen.pop(label, None)

    return silent_labels
```

- **순서 계약(확정)**: `sessions` fetch → pass 1(무변경) → **상대 판정 게이트(pop + return [])** → exit 관측 → pass 2(기존 누적) → return. 게이트가 pass 2 **앞**에 있어야 한다(AST G-241-1).
- `sys.modules.get("src.engine.scheduler")` seam(`:59-71`) **무변경** — `kis_ws_pool`·`_dt` 는 계속 scheduler 네임스페이스 우선(ratio 테스트가 `patch("src.engine.scheduler.datetime")` 로 `now` 를 잡는 경로). 이 파일 패턴 카운트 3 유지(D-2 합산 ≥4).
- 기각 경로는 `_silent_inactive_recovery_count` 를 읽지도 쓰지도 않고 `force_reconnect_session` 을 부르지 않는다(F-15) — cap 계약·dict 동일성 무접촉.
- `now` 하나에서 모든 시각이 파생(`now.date()` 날짜 키 · `since`/`last_warn_at` 비교) — monotonic 미사용, KST aware.
- **결과 집합 ⊆ 현행**: 게이트는 발화를 만들지 않고 pop 은 elapsed 를 줄이기만 한다(순수 축소 방향).

### 2.3 fail-open 경계 (계약)

| 상황 | 게이트 | 행위 |
|---|---|---|
| `eligible == 0`(20:00 `unsubscribe_all` 후 · 부팅 07:59 전) | off | 현행 — 루프가 전부 pop 후 `[]` |
| `eligible == 1`(VTS/개발 단일 세션 · 보조 계정 미로드 · 나머지 세션 sub<5) | off | 현행 byte 동일 — 단일 세션은 5분 후 발화(기존 N-2/N-3/H-1 이 곧 이 경로) |
| `eligible ≥ 2` ∧ 하나라도 fresh(`silent < eligible`) | off | 현행 — 침묵 세션만 누적·발화(진짜 단독 결함 보존, F-3/F-4) |
| `eligible ≥ 2` ∧ 전원 침묵 | **on** | 전 라벨 pop + `[]` + entered/persisting 관측 |
| 관측 헬퍼 예외(logger 등) | on 유지 | pop·`[]` 은 이미 수행 — 관측 실패 ≠ 행위 변화, `_failed` WARNING 1회/일 |
| `sessions` 항목이 `ws_connected` 키 없음 | — | `connected=0`, 예외 0 |
| 라벨 중복(`unknown` ×N) | 길이 기준 | eligible/silent 는 리스트 길이라 오염 없음. pop 은 라벨 키라 중복 라벨은 한 번에 지워짐(현행 충돌과 동일, §8 C) |

### 2.4 테스트 결정성 seam

- 감지 테스트 = **ratio 파일 관용구**: `TradingScheduler()` 풀 생성자 fixture + `patch.object(sch_mod, "kis_ws_pool")`(`get_session_status = MagicMock(return_value=sessions)`) + `patch("src.engine.scanner.ticker_last_tick", map)` + `patch("src.engine.scheduler.datetime")`(`mock_dt.now.return_value = NOW`, `mock_dt.min = datetime.min`). 다중 사이클 시나리오는 `mock_dt.now.return_value` 를 120s 씩 전진시켜 재호출.
- `_make_session(label, subscribed, tickers)` 는 `tests.unit.engine.test_session_silent_inactive_ratio` 에서 import(cycle240 이 cycle216 픽스처를 import 한 선례, `tests/` 패키지 확인). 8세션 픽스처 헬퍼 `_make_pool(silent_labels: set[str], fresh_ratio_map)` 는 신규 파일 로컬.
- 신규 파일 **autouse fixture** 가 각 테스트 전후 `reset_market_wide_episode_state()` 호출(모듈 전역 누수 차단 — 다른 파일의 단일 세션 테스트가 `_close_market_wide_episode` 를 지나며 잔존 에피소드의 `exited` 를 찍는 일 방지).
- caplog = `caplog.set_level(logging.INFO, logger="src.engine.scheduler")` **단일 호출**, WARNING 은 `r.levelno == logging.WARNING` 필터(cycle240 §10.1 함정 — `_capture_scheduler_warnings()` 병용 금지).
- 관측 실패 주입 = `monkeypatch.setattr(stale_session_recovery.logger, "info", raiser)`(같은 Logger 객체 — monkeypatch 가 복원).
- KST 명시: `KST = timezone(timedelta(hours=9))`, `NOW = datetime(2026, 9, 3, 15, 22, 0, tzinfo=KST)` 류 aware 상수만.

### 2.5 헤더·docstring 재스코프 (⑦ 처분)

- `:1-12` 모듈 docstring — "함수 본체 변경 0" 을 **"사이클 61/67 이주 당시 계약. cycle241 이 `detect_silent_inactive_sessions` 에 의도된 행위 변경(세션 상대 판정)을 도입 — `force_reconnect_session` · `delta_unsubscribe_dropped` 는 diff 0"** 로 갱신. `:11` Q1 문구를 G-7 실검사와 일치("`stale_watcher_core` import 금지. `stale_diagnostics` 의 `STALE_FRESHNESS_SECS` 는 허용된 단방향 예외(`:35`)").
- `:38-41` 인라인 주석 — "행위 변경 0건 의무 (refactor only)" 를 "사이클 61 이주 시점 계약 — cycle241 예외 1건 명시" 로.
- `:44-58` 함수 docstring — 판정을 **4중**으로 갱신(비율 · sub≥5 · 5분 · **세션 상대**), 기각 규칙·fail-open 경계·마커 3전이·"결과 ⊆ 현행" 불변식·`_MW_EPISODE` 가 관측 전용임을 명시.

## 3. 불변 계약

1. **시간당 세션당 2회 cap 불변** — `force_reconnect_session` diff 0, `_silent_inactive_recovery_count` dict 동일성(cycle61 C-1) 무접촉, 기각 경로가 그 dict 를 참조하지 않는다.
2. **위임 시그니처 불변** — `detect_silent_inactive_sessions(scheduler)` 인자 1개(A-1 `assert_called_once_with(sched)`), 반환 `list[str]`.
3. **`sys.modules.get("src.engine.scheduler")` seam 위치·개수 불변**(이 파일 3, D-2 합산 ≥4) · **logger `src.engine.scheduler`**(G-6) · **Q1 단방향**(G-7 — `stale_watcher_core` import 0) · **scheduler 정적 import 0**(D-1) · **cycle72 write_log 0**(신규 마커 포함) · **`[silent_inactive_force_reconnect]` 서식 byte 보존**(G-ERR2 존속).
4. **5 상수 값·SoT 불변** — 신규 2 상수는 private 이며 facade `__all__` 미편입.
5. **`StaleTrackerState` 7필드 불변** — 에피소드 상태는 모듈 전역. `reset_daily` 무접촉.
6. **판정 가능 세션 정의 = `subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED`** 재사용 — 신규 임계·시간창 리터럴(08:30/15:20 등)·`tradable_boards`·`session` import **금지**(AST G-241-5).
7. **기각은 pop + `return []`** — 보류(first_seen 값 유지) 금지(G-241-1 + F-7).
8. **행위는 cap 밖** — 관측 헬퍼 성패와 무관하게 pop·`[]` 수행(F-10). `_MW_EPISODE` 를 읽어 행위를 바꾸는 코드 0(G-241-2).
9. **fail-open 방향 고정** — `eligible < 2` · 하나라도 fresh · 판정 불가 = 현행 byte 동일. 단일 세션도 기각하는 구현은 FAIL(기존 N-2/N-3/H-1 이 그 뮤테이션을 잡는다).
10. **결과 집합 ⊆ 현행** — 새 발화 경로 0.
11. 8영역 diff 0 · `scheduler.py` diff 0(3,999L) · facade/diagnostics/watcher_core/universe_guard diff 0.

## 4. Red 테스트 목록

### 4.1 `tests/unit/engine/test_cycle241_silent_inactive_relative.py` (신규 — ID 접두 `test_f241_`)

8세션 표준 픽스처 = 라벨 `main·ISA·RIA·fire·gold·44606571·71513056·1004`(운영 실측), sub 8~17. `(현행 FAIL)` 없는 항목은 회귀 가드.

| ID | 시나리오 | 기대 |
|---|---|---|
| F-1 **(현행 FAIL — 핵심)** | 8세션 전부 fresh=0, 8라벨 first_seen 전부 NOW−301s 사전 무장 | `result == []` · 8라벨 전부 first_seen 에서 제거 · INFO `[silent_inactive_market_wide_skip] transition=entered sessions=8 eligible=8 silent=8/8 connected=8 reset=8` 정확히 1행 · `[silent_inactive_force_reconnect]` 0 |
| F-2 (현행 FAIL) 누적 금지 | 같은 8세션, first_seen 미무장 | `result == []` ∧ `first_seen == {}`(등록조차 안 됨) |
| F-3 진짜 단독 결함 보존 | main fresh 1/8(0.125) + first_seen NOW−301, 타 7세션 fresh 0.5~0.8(09-02 16:05 실측 재현) | `result == ["main"]` · skip 마커 0 · 타 7 라벨 first_seen 없음 |
| F-4 (현행 FAIL 아님 — 경계 회귀) 하나라도 fresh | 7 침묵(first_seen NOW−301) + RIA fresh 11/16 | 7라벨 발화(현행 동일), RIA pop, 마커 0 — "하나라도 fresh 면 상대 판정 불성립" |
| F-5 단일·비교 불가 fail-open | (a) main 단독 침묵 first_seen NOW−301 → `["main"]` (b) main 침묵 + 두 번째 세션 sub=4(비판정) 침묵 → eligible=1 → `["main"]`, sub=4 세션은 pop | 현행 byte 동일. (a) 는 기존 N-2/N-3 과 같은 입력 |
| F-6 (현행 FAIL) eligible 하한 | 정확히 2세션 모두 eligible·침묵 | 기각 `[]` + entered `sessions=2 eligible=2 silent=2/2` |
| F-7 **(현행 FAIL — (b) 봉인)** 재개 후 5분 | main first_seen NOW−200 사전 무장 → 사이클1(NOW) 8세션 침묵 → 사이클2(NOW+120) 7 fresh + main 침묵 → 사이클3(NOW+120+300) 7 fresh + main 침묵 | 사이클1 `[]`(pop, reset=1) · 사이클2 `[]` ∧ `first_seen["main"] == NOW+120`(재등록) · 사이클3 `["main"]`. **hold 변형은 사이클2 에서 elapsed 320 → 즉발 = 검출** |
| F-8 (현행 FAIL) 마커 전이 cap | 5사이클 연속 전원 침묵 → 1사이클 혼합(1세션 fresh) → 다시 전원 침묵 | `entered` 1행 · `exited elapsed_secs=600 cycles=5` 1행(진입 t=0 → 이탈 사이클 t=600) · 그 뒤 `entered` 재발화 1행. 5사이클 동안 마커 총 1행(폭주 0) |
| F-9 (현행 FAIL) persisting | 전원 침묵을 120s 간격으로 NOW~NOW+3720 (32사이클) | `entered` 1 · 첫 WARNING `transition=persisting elapsed_secs>=1800` 은 elapsed 가 1800 을 처음 넘는 사이클 1행 · 다음 WARNING 은 ≥1800s 뒤 1행(총 2) · 매 사이클 `result == []` 유지 |
| F-10 관측 실패 격리 | `logger.info` 가 마커 문자열에 raise 하도록 monkeypatch → 전원 침묵 1사이클 → 복원 → 1사이클 | 두 사이클 모두 `[]` + pop 수행 · 예외 전파 0 · 1사이클째 `_failed` WARNING 1행 · 2사이클째 `entered` 정상 발화(**peek→로그→mark** — 실패 시 `since` 미기록) |
| F-11 `unknown` 라벨 충돌 | `unknown`×2 + main, 전부 침묵 | eligible=3(길이 기준) → 기각, pop 예외 0. 라벨 set 으로 세는 변형(eligible=2)도 이 케이스는 기각이므로 **대조군** 추가: `unknown`×2 만(총 2세션, 라벨 set 이면 1 → 현행 유지 → 발화 / 길이면 2 → 기각) |
| F-12 날짜 키 자기 리셋 | `_MW_EPISODE["since"]` = 전일 19:58 · cycles=60 상태 주입 → NOW = 익일 08:52 전원 침묵 | `entered` 로 새 에피소드(cycles=1), persisting 미발화(전일 since 로 13h 계산 금지) |
| F-13 `connected=` 필드 | 8세션 중 `ws_connected` True 5 · False 2 · 키 부재 1 | 마커 `connected=5`, 예외 0 |
| F-14 dict 동일성·cap 무접촉 | 전원 침묵 기각 전후 | `sched._silent_inactive_recovery_count is sched._stale_state.silent_inactive_recovery_count` ∧ 내용 불변 ∧ `first_seen` 객체 동일(`is`)·값만 pop |
| F-15 기각 경로 호출 0 | `patch.object(stale_manager, "force_reconnect_session")` | 기각 사이클에서 호출 0 (K 루프 wrapper 통합 — `sched._detect_silent_inactive_sessions()` 가 `[]` 라 for 루프 미진입) |
| F-16 sub=0 혼합 | 8세션 중 6세션 sub=0(20:00 race) + 2세션 eligible 침묵 | eligible=2 → 기각. 1세션만 eligible 이면 현행 |
| F-17 기존 회귀 | §5 표적 목록 | 전부 무수정 PASS(단일 `main` 픽스처 = 게이트 off 경로) |

### 4.2 `tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py` (신규 — `parents[3]`, `_ast_helpers` 재사용)

| ID | 검사 | 뮤테이션 표적 |
|---|---|---|
| G-241-1 | `detect_silent_inactive_sessions` 안 게이트 `If`(test 가 `_MARKET_WIDE_MIN_ELIGIBLE` Name 을 직접 참조하거나, 그 Name 을 참조하는 지역 대입의 타깃 — **전이 1단계 추적**, cycle226 L-2 교훈) 존재 ∧ 그 body 에 `Return` + `_silent_inactive_first_seen` 대상 `.pop(` Call 존재 ∧ unparse 텍스트에서 게이트 index < `_silent_inactive_first_seen[label] = now` index | 게이트 제거·pass 2 뒤로 이동·hold(pop 부재)·리터럴 `2` |
| G-241-2 | 게이트 body 에 `silent_labels.append` 0 · `force_reconnect` 토큰 0 · `_silent_inactive_recovery_count` 토큰 0 · `_MW_EPISODE` 를 읽는 `Compare`/`If.test` 가 함수 본문(헬퍼 밖)에 0 | 기각이 발화·cap 접촉·관측 상태로 행위 분기 |
| G-241-3 | 모듈에 `"[silent_inactive_market_wide_skip]"` 상수 ≥3(entered/persisting/exited) ∧ 각 emit 사이트가 `Try`(handler `except Exception`) 하위 ∧ cycle72 `_count_write_log_calls_near_prefix` 동형 검사 0 | 예외 전파·write_log 이중 INSERT |
| G-241-4 | `_observe_market_wide` 안에서 `since` 를 기록하는 `_MW_EPISODE.update(since=...)`/`["since"] =` 의 source 위치 > 같은 블록의 `logger.info` 호출 위치 ∧ `last_warn_at` 기록 > `logger.warning` 위치 | mark-before-log |
| G-241-5 | `ImportFrom`/`Import` 의 모듈 집합 ⊆ {stdlib, `src.engine.scanner`, `src.realtime.websocket_pool`, `src.realtime.websocket`, `src.engine.stale_diagnostics`} — 특히 `src.engine.session` 0 · `stale_watcher_core` 0 · `src.engine.scheduler` 0 ∧ 파일 내 `sys.modules.get("src.engine.scheduler")` 카운트 ≥3 | 시장 상태 신호 유입·seam 제거 |
| G-241-6 | `scheduler.py` 에 `market_wide`·`_MW_EPISODE` 토큰 0 ∧ `wc -l == 3999`(cycle233 `test_scheduler_untouched` 동형, 라인수 단언은 이 사이클 한정 — docstring 에 자기소멸 조건 명시) | scheduler 편집 |
| G-241-7 | `stale_manager.py` 에 `market_wide`·`reset_market_wide_episode_state` 토큰 0(facade 무접촉) | facade export 추가 |

기존 가드 **재작성 금지**(중복) — 표적 실행에 포함만: A-1(cycle61 위임) · C-1(cap dict 동일성) · F-1/F-2(dataclass 7필드, cycle61+63) · D-1/D-2(cycle63) · G-6~G-9(cycle67) · G-A7/A8/A9(cycle72) · G-ERR2(cycle74) · G-194-1~4 · N-1~N-9(ratio) · H-1(5min) · G-1(cap) · cycle226 `test_common_1_eight_areas_untouched`.

## 5. Green 범위

- `src/engine/stale_session_recovery.py` **단독**: §2.1 상수·상태·헬퍼 4 + §2.2 본문 2-pass + §2.5 헤더/docstring 재스코프. 예상 +110L 안팎(251L → ~360L, 이 파일엔 라인 상한 없음).
- 신규 테스트 2파일(§4.1·§4.2). 인덱스 `python tools/test_impact/build_index.py`.
- **무접촉 기대**: `scheduler.py`(3,999L diff 0) · `stale_manager.py` · `stale_diagnostics.py` · `stale_watcher_core.py` · `stale_universe_guard.py` · `stale_tracker.py` · 8영역 · `src/realtime/CLAUDE.md`(8영역 디렉토리 — cycle226 정본 가드가 git pathspec `src/realtime/` 이라 .md 편집도 잡힌다, §9).
- 표적 실행(Green 후):
  `python -m pytest -q -p no:cacheprovider tests/unit/engine/test_cycle241_silent_inactive_relative.py tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py tests/unit/engine/test_session_silent_inactive_ratio.py tests/unit/engine/test_session_silent_inactive_recovery.py tests/unit/engine/test_cycle61_phase2A2_silent_inactive_cap.py tests/unit/engine/test_cycle61_phase2A2_silent_inactive_5min.py tests/unit/engine/test_cycle61_phase2A2_delegation.py tests/unit/engine/test_cycle61_phase2A2_cap_dict_identity.py tests/unit/engine/test_cycle61_phase2A2_constants.py tests/unit/engine/test_cycle61_phase2A2_reset_daily.py tests/unit/engine/test_cycle194_force_reconnect_db_label.py tests/unit/engine/test_cycle61_phase2A2_dataclass_completeness.py tests/unit/engine/test_cycle63_phase2A3_dataclass_completeness.py tests/unit/engine/test_cycle61_phase2A2_dependency_direction.py tests/unit/engine/test_cycle63_phase2A3_dependency_direction.py tests/unit/engine/test_cycle61_phase2A2_import_sanity.py tests/unit/engine/test_cycle63_phase2A3_import_sanity.py tests/unit/engine/test_cycle63_phase2A3_reset_daily.py tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py tests/unit/engine/stale_manager/ tests/unit/realtime/test_cycle74_error_preservation_matrix.py tests/unit/realtime/test_cycle92_auto_restart_hourly_cap.py tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::test_common_1_eight_areas_untouched tests/unit/ast/test_cycle221_ast_market_op_no_main.py tests/unit/ast/test_cycle222a_ast_day_high_scope.py tests/unit/ast/test_cycle234_ast_uptime.py tests/unit/ast/test_cycle233_ast_account_risk.py tests/unit/engine/test_refactor_b1_data_load_tasks.py`
  전체 스위트는 Docs 단계 1회(cycle240 기준선 **5963 passed, 10 skipped, 328 xfailed, 13 xpassed** + 신규분).

## 6. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| m1 | 상대 판정 블록 제거(환원) | F-1/F-2/F-6/F-7/F-8/F-9 FAIL + G-241-1 |
| m2 | 기각하되 first_seen 유지(hold) | F-2/F-7 FAIL + G-241-1(pop 부재) |
| m3 | `_MARKET_WIDE_MIN_ELIGIBLE` 를 1 로 / 게이트 `>= 1` | F-5 FAIL + 기존 N-2/N-3/H-1/recovery #2 무더기 FAIL |
| m4 | eligible 분모에 `sub < 5` 세션 포함(`len(sessions)`) | F-5(b)/F-16 FAIL |
| m5 | 세션 수를 라벨 set 으로 계산 | F-11 대조군 FAIL |
| m6 | `silent_n >= 1` 로 기각(방향 오류) | F-3/F-4 FAIL |
| m7 | 게이트를 pass 2 뒤(반환 직전 필터)로 이동 | F-7 FAIL + G-241-1 |
| m8 | 매 사이클 `entered` 로그(전이 cap 제거) | F-8 FAIL |
| m9 | mark-before-log(`since` 먼저 기록) | F-10 FAIL + G-241-4 |
| m10 | persisting 제거 / 매 사이클 WARNING | F-9 FAIL |
| m11 | 날짜 키 제거 | F-12 FAIL |
| m12 | 기각 경로에서 `recovery_count` 접촉 또는 `force_reconnect` 호출 | F-14/F-15 FAIL + G-241-2 |
| m13 | `from src.engine.session import session_tracker` 게이트 유입 | G-241-5 |
| m14 | 관측 헬퍼 try 제거(예외 전파) | F-10 FAIL + G-241-3 |
| m15 | `_MW_EPISODE` 값으로 기각 여부 분기 | G-241-2 |
| m16 | `scheduler.py` 1줄이라도 편집 | G-241-6 + 라인 3,999 |

추가 렌즈: (i) **차분 실증** — 게이트 off 입력(단일 세션 15 픽스처 + F-3/F-4/F-5)에서 result·first_seen 전이가 현행과 **동일**(행위 변경은 `eligible ≥ 2 ∧ 전원 침묵` 구간에만) (ii) `git diff HEAD --name-only` ⊆ §5 허용 목록, cycle226 정본 8영역 가드 PASS (iii) `wc -l src/engine/scheduler.py` 3,999 (iv) 비용 — pass 1/2 분리로 `ticker_last_tick.get` 호출 수 불변(세션당 1회 순회), 추가 연산 = 튜플 리스트 8개·sum 2회 (v) F-7 hold 변형과 m7 반환 직전 변형을 **사본 저장소**에서 실제 주입해 FAIL 실증(cycle240 §10.2 규약 — 실트리 미접촉).

## 7. D+1 판독 채널 (배포 = 20:10 정산 이후 야간 창 또는 07:55 전, cycle232 D6)

| 채널 | 정상 서명 | 이상 서명 → 해석 |
|---|---|---|
| `[silent_inactive_force_reconnect]` | **0~3건/일**, 전부 16:00 이후 `label=main`(단독 침묵 — §8 A 축) | 같은 초 8행 버스트 = 시정 미작동. 09:00~15:20 발화 = 신규(종전 0) → 즉시 조사 |
| `[silent_inactive_market_wide_skip] transition=entered` | **2~3행/일**: ≈08:51~53(NXT 프리 마감 08:50+60s) · ≈15:21~23(연속매매 종료+60s) · 간헐 ≈07:59(presubscribe~08:00). `sessions=8 eligible=8 silent=8/8 connected=8` | `connected<8` 동반 = 소켓 사망 혼재. entered 가 정규장에 찍힘 = 전 세션 침묵 사고 → `[tick_coverage]` 교차 |
| `… transition=exited` | entered 와 1:1, `elapsed_secs` ≈ 180~600(아침) · ≈1,000~1,300(15:2x→15:40) · ≤120(07:59) | elapsed ≫ 1,300 = 시장 재개 후에도 침묵 = 두절 |
| `… transition=persisting` (WARNING) | **0행**(수능일 등 개장 지연일 1~2행 예외) | ≥1행 = 30분 이상 전 세션 침묵 — 08-31 형. `[tick_coverage] ratio=0.0%` 와 함께 읽고 필요 시 `POST /api/trading/restart` |
| `[silent_inactive_market_wide_skip_failed]` | 0 | ≥1 = 관측기 자기 실패(행위는 수행됨) — 로거/서식 조사 |
| `[silent_inactive_recovery_cap]` | 평상일 0 유지(종전에도 0) | — |
| 접속키 발급(`접속키 발급 완료`, EC2 로그) | 일 53 → **≈26~29**(부팅 8 + 보드 전환 8 + 정기 16:02 8 + 개별 1~5) | 감소 없음 = 발화 잔존 |
| `[stale_watcher_detail]` 15:40:3x | 8세션 동시 fresh 회복 서명 불변(15:36 재연결이 사라져도 회복 시각 동일 = ④ 근거 재확인) | 회복 지연 = 재연결이 실제로 기여했었다는 반증 → ④ 재검토 |
| 보유 종목 시세 공백 | 08:57·15:39 재연결 직후 HIGH 종목 `stale` 스파이크 소멸 | — |

⚠️ **의미 반전** — `[silent_inactive_force_reconnect]` 감소가 정상, skip 마커는 신규. 배포 전후 로그를 같은 grep 으로 합산 비교하지 않는다(cycle228/240 교훈).

## 8. 후속 등재 (이번 사이클 밖)

- **A. main 단독 잔여 위양성** — sub=8 분해능(1/8=0.125)에 야간 무거래 우선주(000815·003490·285130…) 구성이 0.2 임계를 무작위 왕복(09-02 18:50~19:26 fresh 시계열 2,1,1,1,1,0,0,1,2…), 재연결 후 계단 변화 0. 후보 = `SILENT_INACTIVE_MIN_SUBSCRIBED` 상향 또는 절대 fresh 하한 — **비율·표본 임계 변경이라 domain-consult 대상**(저유동 보유 종목 시세 감시 사각 vs 재연결 소음 교환).
- **B. 단일 세션 풀 2차 게이트** — VTS/개발 환경에서만 실익 있는 `is_call_auction_now` 이식(54.4%). 운영 8세션엔 무효. 필요 시 별도.
- **C. `unknown` 라벨 충돌** — `_label` 없는 보조 세션이 같은 라벨을 공유해 first_seen/cap dict 키가 충돌(realtime 8영역 `websocket_pool.py:538-540`). 운영 8라벨은 전부 DB 라벨이라 미발현.
- **D. 접속키 캐시** — `token.py:183` 무캐시(auth 8영역). L1 로 수요가 절반으로 줄어 우선순위 하락.
- **E. 장중 전 세션 침묵 에스케이프 해치** — `entered` 가 09:00~15:20 에 찍히고 `exited elapsed ≥ 600` 이 실측되면 재검토(현재 표본 0).
- **F. `_MARKET_WIDE_PERSIST_WARN_SECS` 재조정** — 수능일·조기 마감일 실측 후.
- **G. 형제 `check_and_resubscribe_stale` 의 `[stale_skip_call_auction]`** — 이번 무접촉. L1 과 관측 축이 다르므로 유지.

## 9. 문서 동기화 (Docs 단계)

- 루트 `CLAUDE.md`:
  - 하네스 표 L69 상단 1행 추가(한 줄) + 최고령 L83(2026-08-24 cycle225) 제거 → 15행 유지. 제거분은 `docs/HARNESS_CHANGELOG.md` L21 에 이미 verbatim 존재 — 이동 불요. 변경로그 L7 에 cycle241 상세 1행 append(`| 날짜 | 변경 내용 | 대상 | 사유 |` 형식, **■ 발단/확증 원인/구현/검증**).
  - L167 핵심 안전 규칙 항목 갱신 문안: "- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단). **세션 상대 판정 (cycle241)** — 판정 가능 세션(`subscribed >= 5`)이 **2개 이상이고 그 전부**가 `fresh_ratio < 0.2` 이면 '세션 고장' 이 아니라 **시장 침묵**(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가+15:30~15:40 마감 흡수)으로 보고 그 사이클을 **기각 + 전 라벨 `first_seen` pop**(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다). 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 세션 결함 보존), 판정 가능 세션 < 2 면 현행 유지(fail-open). 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측하고 30분 이상 지속 시 WARNING. 근거 = 30일 522건 중 491건(94%)이 풀 전체 동시 발화·09:00~15:20 정규장 0건·재연결이 회복시킨 사례 0건(08-31/08-12 전 세션 두절도 익일 부팅으로만 회복). **시장 침묵 기각에 시간창 리터럴(08:30/15:20)·`tradable_boards`·`session` import 를 쓰지 않는다** — 세션 간 비교만이 15:30~15:40 갭까지 닫는다(AST G-241-5)"
- `src/engine/CLAUDE.md`: L16 모듈 맵 `stale_session_recovery.py 274L (3 함수 + 5 상수 …)` → 실측 라인 + "cycle241 세션 상대 판정 + private 2 상수 + `_MW_EPISODE` 관측 상태" · L713 `_stale_watcher_loop()` 문단의 "사이클 29-R2 정의 완화" 뒤에 cycle241 서술(원인·2-pass·기각 규칙·fail-open 경계·마커 3전이·전제 정정·의미 반전) · L717 사이클 61 서술에 "cycle241 행위 변경 예외 1건" · L721 "함수 본체 라인 단위" 무변경 영역 목록에서 `detect_silent_inactive_sessions` 제외 명시(2회 cap 은 그대로 무변경).
- `_workspace/00_URGENT_WORKLIST.md`: `### P1-4 · silent_inactive 오판 — 하루 16~24 접속키 낭비` → `… — ✅ cycle241 종결 (2026-09-02, 커밋 대기)` + 인용 블록(시정 요약·전제 정정 3·D+1 채널·후속 A~G), P1-5/P1-7 형식 답습.
- `src/realtime/CLAUDE.md` L55/L69 의 `[silent_inactive_force_reconnect]` 서술 — **무접촉**(cycle226 정본 가드 git pathspec). 필요 시 후속 사이클에서 sha 면제와 함께.
- `_workspace/00_leader_trading_rules.md`: 파라미터 변경 0 — 무변경.
- 인덱스 재생성 + 전체 스위트 1회 + 커밋·푸시 사용자 지시 대기.

## 10. 적대 검증 확증/시정 — 착수 후 기입 (라운드 1)

3렌즈 적대 검증(§6 뮤테이션 체크리스트 실행 + 2 차 tester 리뷰)에서 확증된 8건 중, 아래 5건을
`src/engine/stale_session_recovery.py`(단독) + 두 테스트 파일에 시정했다. 나머지 3건은 코드
결함이 아니라 (a) 이미 §0 ④/§8 A 에서 명시적으로 다룬 트레이드오프의 변형 재확인, (b) 동일 근본
원인의 중복 리포트였다 — 아래에 각각 처분을 명시한다.

### 10.1 시정 완료

| # | 등급 | 파일 | 시정 |
|---|------|------|------|
| AST 헬퍼 `_resolve` tuple−set TypeError | **HIGH**(중복 리포트 4건 = #1/#3/#4/#6) | `tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py:93` | `assign_map.get(name, ())` → `assign_map.get(name, set())`. 지역 대입 타깃이 아닌 이름(예: `sum`/`s`/`subscribed_count`/`_MARKET_WIDE_MIN_ELIGIBLE` 자신)에 닿는 순간 `() - set()` 이 `TypeError` 를 던져 `_find_gate()` 를 쓰는 G-241-1(2건)·G-241-2(1건) 이 정확한 Green 구현에서도 크래시했다. 이 파일은 tdd-engineer 소유 Red 파일이라 **가드의 자기 결함**이지 구현 결함이 아니다 — "테스트 하네스 결함이면 테스트 쪽 시정" 원칙대로 테스트 쪽 1토큰 수정. 수정 후 AST 스위트 14/14 PASS(수정 전 3 FAIL: `test_gate_body_pops_first_seen_and_returns` / `test_gate_precedes_first_seen_accumulation` / `test_gate_body_has_no_fire_or_cap_tokens`) |
| `connected=` 필드 오독 위험 | **MEDIUM**(#2) | `stale_session_recovery.py` | (a) `_count_connected` docstring 에 "`_ws` 객체 보유(재연결 대기 stale 포함) — 소켓 생존 확증 아님" 명시 (b) 신규 `_count_reconnects(sessions)` 헬퍼(세션별 `reconnect_count` 합, `websocket_pool.get_session_status()` 가 이미 반환하는 키 — 8영역 신규 read 0, 기존 read-only 소비 확장) (c) `_observe_market_wide` 의 entered/persisting 마커에 `reconnects=%d` 필드 병기(신규 kwarg `reconnects_n: int = 0`, 기본값이라 기존 호출부 무영향 — 실제 호출부는 즉시 갱신) (d) §7 D+1 판독 채널 문서 표현은 §10.2 에서 후속 처리(Docs 단계 소관). 회귀 `test_f241_13b_reconnects_field_sums_reconnect_count_across_sessions` 신규 |
| Escape M06a/M06b (pass 1 예외 흡수) 테스트 공백 | **HIGH**(escape, #7) | `tests/unit/engine/test_cycle241_silent_inactive_relative.py` | `test_f241_18_malformed_session_when_missing_label_then_exception_propagates`(parametrize first/middle/last) + `test_f241_18b_malformed_session_when_market_wide_shape_then_still_raises` 신규 — malformed 세션(필수 키 결손) 이 섞이면 `KeyError` 가 전파돼야 하고(현행 계약, `scheduler.py:3024-3029` K 루프가 흡수), 마커·first_seen 변경이 0 이어야 함을 봉인. 사본에서 "pass 1 + 게이트를 `try/except Exception: return []` 로 감싸는" 변조를 재현해 4건 모두 FAIL(무변조 시 25/25 PASS) 확인 후 실트리 무접촉으로 복원 |
| Escape M19 (기각 경로가 suspect 만 pop) 테스트 공백 | **HIGH**(escape, #8) | `tests/unit/engine/test_cycle241_silent_inactive_relative.py` | `test_f241_19_market_wide_reject_pops_non_eligible_stale_labels_but_not_ghost_keys` 신규 — sub<5(`fire`)·sub=0(`1004`) 처럼 애초에 suspect 가 될 수 없는 라벨의 stale first_seen 도 기각 시 pop 되고, 현재 세션 목록 밖 `ghost` 키는 무접촉임을 검증. 사본에서 `if _s and ...pop(...)` 변조(suspect 만 pop)를 재현해 FAIL(`remaining` 에 fire/1004 잔존) 확인 후 실트리 무접촉으로 복원 — **현행 구현(`stale_session_recovery.py`)은 이미 올바르게(`judged` 전체 pop) 동작 중이었다**, 이 항목은 순수 회귀 커버리지 보강 |

### 10.2 확인만 하고 코드 변경 없음 (스펙 결정 재확인 / 후속 등재로 처분)

| # | 등급 | 처분 |
|---|------|------|
| main 세션 단독 저녁 시간대 구조적 침묵이 **7개 보조 세션 실제 동시 결함** 케이스를 가리는 변형 | **MEDIUM**(#5) | §0 ④ 가 채택한 트레이드오프("8/8 실제 두절")와 §8 A(main 단독 저녁 위양성)의 **교차** 변형(1 구성상 + 7 실제)이며, 발의자 스스로 "처분 후보(코드 아님, 결정 사안)" 로 명시했다 — team-leader/도메인 자문 없이 백엔드 라운드에서 임의로 게이트 조건(예: "보유 종목 포함 세션 한정 허용")을 바꾸면 §0 ④ 의 승인된 결정("보조 조건 불채택 — 표본 0")을 되돌리는 것과 같다. §8 A 에 이미 "표본 관찰 후 SILENT_INACTIVE_MIN_SUBSCRIBED 상향 또는 절대 fresh 하한, domain-consult 대상" 으로 등재돼 있어 **별도 신규 항목 불요** — 표본 축적(§8 A) 완료 후 재평가 대상임을 재확인만 하고 코드 변경 0 |
| AST 헬퍼 버그의 중복 리포트 (#1/#3/#4/#6) | HIGH | 10.1 의 단일 시정으로 4건 모두 해소 — 동일 근본원인 |

### 10.3 표적 스위트 (Green, 시정 후)

```
python -m pytest -q -p no:cacheprovider \
  tests/unit/engine/test_cycle241_silent_inactive_relative.py \
  tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py \
  tests/unit/engine/test_session_silent_inactive_ratio.py \
  tests/unit/engine/test_session_silent_inactive_recovery.py \
  tests/unit/engine/test_cycle61_phase2A2_silent_inactive_cap.py \
  tests/unit/engine/test_cycle61_phase2A2_silent_inactive_5min.py \
  tests/unit/engine/test_cycle61_phase2A2_delegation.py \
  tests/unit/engine/test_cycle61_phase2A2_cap_dict_identity.py \
  tests/unit/engine/test_cycle61_phase2A2_constants.py \
  tests/unit/engine/test_cycle61_phase2A2_reset_daily.py \
  tests/unit/engine/test_cycle194_force_reconnect_db_label.py \
  tests/unit/engine/test_cycle61_phase2A2_dataclass_completeness.py \
  tests/unit/engine/test_cycle63_phase2A3_dataclass_completeness.py \
  tests/unit/engine/test_cycle61_phase2A2_dependency_direction.py \
  tests/unit/engine/test_cycle63_phase2A3_dependency_direction.py \
  tests/unit/engine/test_cycle61_phase2A2_import_sanity.py \
  tests/unit/engine/test_cycle63_phase2A3_import_sanity.py \
  tests/unit/engine/test_cycle63_phase2A3_reset_daily.py \
  tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py \
  tests/unit/engine/stale_manager/ \
  tests/unit/realtime/test_cycle74_error_preservation_matrix.py \
  tests/unit/realtime/test_cycle92_auto_restart_hourly_cap.py \
  tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py \
  tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::test_common_1_eight_areas_untouched \
  tests/unit/ast/test_cycle221_ast_market_op_no_main.py \
  tests/unit/ast/test_cycle222a_ast_day_high_scope.py \
  tests/unit/ast/test_cycle234_ast_uptime.py \
  tests/unit/ast/test_cycle233_ast_account_risk.py \
  tests/unit/engine/test_refactor_b1_data_load_tasks.py
# → 218 passed, 2 xfailed (cycle241 신규 39: 25 behavior + 14 AST)
```

8영역 diff 0 · `scheduler.py` diff 0(3,999L 불변) · `stale_manager.py`/`stale_diagnostics.py`/`stale_watcher_core.py`/`stale_universe_guard.py` diff 0. `_workspace/test_index.yaml` 재생성(신규 테스트 2파일 반영, 내용 diff 0 — cycle240 종료 시점에 이미 최신). 커밋/푸시는 사용자 지시 대기(라운드 1 종료, 후속 라운드/Docs 단계는 team-leader 인계).

## 10.4 적대 검증 확증 — 라운드 2 (2026-09-03)

라운드 1 종료 후 재검증에서 **10.1 #2(MEDIUM, `connected=`/`reconnects=` 오독 위험)가 닫히지
않았음**이 확인됐다. 라운드 1 이 도입한 `_count_reconnects` 필드와 그 docstring 의 "재연결
폭풍 중엔 세션 수를 크게 웃도는 값으로 뛴다(예: 08-31 형 88회)" 주장이 `src/realtime/websocket.py`
의 실제 재연결 카운팅 로직과 **정반대**였다 — 그 결과 D+1 판독자는 08-31 형 재연결 폭풍
중에도 `connected=8 reconnects=0` 두 필드를 모두 "정상" 으로 읽는 마커를 보게 되고, docstring
이 그 값을 "순수 시장 침묵" 의 확증으로 읽도록 유도해 **시정 전보다 오독 위험이 커졌다**.

| # | 등급 | 근거(정본 = `src/realtime/websocket.py`) |
|---|------|------|
| `reconnects=` 08-31 형 검출 주장 반증 | **MEDIUM**(라운드 1 #2 미종결 재확인) | (1) `_receive_loop` 가 `except websockets.ConnectionClosed: logger.warning(...); return` 으로 예외를 삼켜 정상 반환한다(`_receive_loop`, heartbeat/연결종료 양쪽 분기). (2) `connect()` 의 `if monotonic - connected_at >= MIN_STABLE_SECONDS: self._reconnect_count = 0`(`MIN_STABLE_SECONDS=5`)가 while 루프 복귀마다 평가되는데, silent_inactive 강제 close 는 정의상 5분 이상 유지된 연결이라 **항상** 0 으로 리셋된 뒤 except 경로 없이 즉시 재접속한다(증가 0). (3) `+= 1` 은 `connect()` 의 `except (ConnectionClosed, InvalidURI, OSError)` 분기(핸드셰이크/연결 유지 도중 예기치 못한 단절)에서만 발생하고 `MAX_RECONNECT=5` 초과 시 auto-restart(`start()`)가 다시 0 으로 초기화한다. 따라서 8세션 합 상한은 40, "88" 은 코드상 도달 불가하다. (4) L1 게이트 아래서는 market_wide 에피소드 중 강제 close 자체가 발생하지 않으므로(§2.2 — `_market_wide` 참이면 `force_reconnect_session` 미호출, F-15 봉인), 마커가 찍히는 맥락에서 `reconnects=` 가 0 이 아닌 경우는 "접속 단계 backoff 중인 세션" 뿐이다 — 필드의 실제 의미는 "현재 connect-phase backoff 인덱스 합(세션당 ≤5)" 이지 "재연결 폭풍 지표" 가 아니다. 반면 `connected=` 에 대한 docstring 주장(backoff 대기 중 stale `_ws` 잔존)은 `self._ws = None` 이 while 루프 **밖**이라 사실로 확인된다 |

## 10.5 시정 — 라운드 2

| # | 파일 | 시정 |
|---|------|------|
| `_count_reconnects` docstring | `src/engine/stale_session_recovery.py` | "재연결 폭풍 중엔 …크게 웃도는 값으로 뛴다(예: 08-31 형 88회)" 주장 삭제 → 실제 의미("핸드셰이크 재시도 인덱스, `force_reconnect_session` 강제 close 는 미반영·08-31 형 폭풍에도 0 에 가깝게 머묾")로 정정 + 소켓 생존 판별은 `[ws_heartbeat]` 로 안내 |
| `_observe_market_wide` docstring | `src/engine/stale_session_recovery.py` | "`reconnects=` 를 함께 읽어야 … 오판하지 않는다" 주장을 "메우지 못한다" 로 반전 + `[ws_heartbeat]`/`transition=persisting` 를 소켓 생존 판별 채널로 안내 |
| `_count_connected` docstring (finding 목록 밖 — 같은 오류의 3번째 발생지, 자체 발견) | `src/engine/stale_session_recovery.py` | 마지막 문장 "폭풍 여부는 `reconnects=` 필드…와 함께 읽는다" 를 동일하게 반전. 이 함수의 앞부분 주장("backoff 대기 중 stale `_ws` 잔존으로 `connected=8` 이 찍힐 수 있다")은 `websocket.py:260`(`self._ws = None` 이 while 루프 **밖**)로 사실 확인돼 **무변경** |
| F-13b 테스트 docstring | `tests/unit/engine/test_cycle241_silent_inactive_relative.py` | 동일 반전 — assertion(`reconnects=6` 등)은 **무변경**, 테스트 목적을 "D+1 오독 방지" 에서 "필드가 `get_session_status()` 소스에서 정확히 합산되는지" 로 재정의(진단 필드 정확성 검증으로 좁힘) |

**코드 행위 변경 0** — 세 곳 전부 docstring/주석이며 `reconnects=` 필드 자체(계산식·마커
kwarg·기본값 `reconnects_n: int = 0`)는 라운드 1 그대로 유지한다. 필드를 유지하든 폐기하든은
team-leader 결정 사안(이번 라운드는 서술 정정에 한정). §7 D+1 판독 채널 표는 `reconnects=`
를 아직 인용하지 않으므로(§10.1 (d) 가 Docs 단계로 이연한 항목) 추가 변경 없음 — Docs
단계에서 `[ws_heartbeat]` 를 소켓 생존 판별자로 명시할 때 이 정정을 반영한다.

## 10.6 표적 스위트 (Green, 라운드 2 시정 후)

```
python -m pytest -q -p no:cacheprovider \
  <§10.3 과 동일 29개 경로>
# → 218 passed, 2 xfailed (라운드 1과 동일 — 이번 라운드는 docstring 전용, assertion 변경 0)
```

8영역 diff 0 · `scheduler.py` diff 0(3,999L 불변) · facade/diagnostics/watcher_core/universe_guard
diff 0. 코드 변경 파일 = `src/engine/stale_session_recovery.py` + 테스트 1파일(docstring만).
커밋/푸시는 사용자 지시 대기.

## 11. Docs 단계 최종 상태 — 착수 후 기입 (라운드 1·2 범위 밖, 후속 라운드/team-leader 인계)

기입: team-leader, 2026-09-03 야간 (Docs 단계). 기준 HEAD = `89fe8e3`(타 작업 피라미딩 검토 docs 커밋 — cycle240
`140a79a` 의 직후. 상단 워킹트리 주석의 untracked 3건 중 2건은 그 커밋에 포함돼 이제 `_workspace/morning_0903_report.md` 만 untracked 로 남았고 여전히 무접촉).

### 11.1 team-leader 결정 (라운드 2 이연분)

| 항목 | 결정 | 근거 |
|---|---|---|
| `reconnects=` 필드 존폐 | **유지** | 값의 실제 의미("connect-phase backoff 인덱스 합", 세션당 ≤5)는 보조 진단으로 무해하고, 라운드 2 가 docstring 3곳을 사실과 일치시켰다. 폐기는 마커 서식·F-13b·`_observe_market_wide` 시그니처를 다시 건드려 적대 검증을 재소환하는 반면 실익은 로그 필드 하나 삭제뿐. 후속 H 로 등재 — 다음 이 파일 접촉 사이클에서 F-13b 회귀 동반 폐기 가능 |
| 소켓 생존 판별 채널 | `[ws_heartbeat]`(세션별 PINGPONG, `websocket.py` 사이클 42/46) + `transition=persisting` 지속 시간 | §7 표의 `persisting`·`entered` 행에 `[ws_heartbeat]` 교차를 명시(정본 문서 4곳 동일 문안). `connected=`·`reconnects=` 는 어느 쪽도 소켓 생존 확증이 아님을 CLAUDE.md 표·engine CLAUDE.md·워크리스트에 병기 |
| §10.2 #5(main 구조적 침묵 + 7보조 실제 동시 결함 교차 변형) | 후속 A 에 흡수, 코드 변경 0 | ④ 의 승인된 트레이드오프 + 후속 A(domain-consult) 의 교차 — 표본 축적 후 한 번에 재평가 |

### 11.2 문서 동기화 완료 (§9 대비)

- 루트 `CLAUDE.md`: 하네스 표 상단 1행(cycle241) 추가 + 최고령 1행(2026-08-24 cycle225, 변경로그에 verbatim 기존재) 제거 → 15행 유지. 핵심 안전 규칙 "세션 단위 silent inactive 자동 reconnect" 항목에 **세션 상대 판정** 절 추가(§9 문안 기준).
- `docs/HARNESS_CHANGELOG.md`: cycle241 상세 1행 append(■ 발단 / 확증 원인 + 전제 정정 3 / 결정 8 / 구현 / Red·Green / 적대 검증 라운드 1·2 / D+1 / 후속 / 수치).
- `src/engine/CLAUDE.md`: L16 모듈 맵(274L → 438L + cycle241 요소) · L713 사이클 24/29-R2 문단에 cycle241 서술 · L717 사이클 61 서술에 행위 변경 예외 1건 · L721 사이클 67 "무변경 영역" 재스코프.
- `_workspace/00_URGENT_WORKLIST.md`: `### P1-4` → `✅ cycle241 종결 (2026-09-02, 커밋 대기)` + 실측·원인·전제 정정 3·결정 8·관측·적대 검증·D+1 표·후속 A~H(P1-7 형식).
- `src/realtime/CLAUDE.md`: **무접촉**(cycle226 정본 가드 git pathspec `src/realtime/`). `_workspace/00_leader_trading_rules.md`: 파라미터 변경 0 — 무변경.

### 11.3 최종 검증

- `python tools/test_impact/build_index.py` 재생성 완료.
- 전체 백엔드(`__pycache__` 제거 후 `python -m pytest -q -p no:cacheprovider`): **6002 passed, 10 skipped, 328 xfailed, 13 xpassed in 133.66s (0:02:13)** (cycle240 기준선 5963 passed + 신규 39 = 6,002 기대).
- 변경 파일(`git status --short`, 타 작업 untracked 3건 제외): `src/engine/stale_session_recovery.py`(+196/-9) · `_workspace/test_index.yaml` · `CLAUDE.md` · `docs/HARNESS_CHANGELOG.md` · `src/engine/CLAUDE.md` · `_workspace/00_URGENT_WORKLIST.md` · 신규 `tests/unit/engine/test_cycle241_silent_inactive_relative.py` · `tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py` · 본 스펙.
- 8영역 diff 0 · `scheduler.py` 3,999L diff 0 · facade/diagnostics/watcher_core/universe_guard diff 0.
- 커밋·푸시 = 사용자 지시 대기. 배포 창 = 20:10 정산 이후 야간 또는 07:55 `_boot` 전(cycle232 D6).

