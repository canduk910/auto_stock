# 09-05(토) 아침 리포트 — 야간 자율 작업 (09-04 23:00 ~ 09-05 06:30 KST)

> 사용자 지시(09-05 00:2x): "06:30까지 승인 없이 진행, 커밋은 작업 단위로, 세션 한도 시 대기 후 재개, 06:30 리포트".
> 최종 갱신 09-05 04:35 (06:25 재점검 후 제시). 남은 `⏳` 없음.

## 0. 한눈에

| 항목 | 결과 |
|---|---|
| 배포 | **커밋 23건**(20:25~04:30, 코드 9 · 테스트 7 · 문서 7 — 리포트 자체 커밋 2건 포함). 서버에 올린 작업 묶음 8 = cycle248·245·249·250·251·252·253 + 화면(W2) 1건. backend 재시작 7회(20:25 이후, 밤 창 23:00 이후는 6회) 전부 장외(`market_blind_secs=0`), frontend 전용 1회(무재시작 실증), 문서 전용은 배포 자체 없음. EC2 최종 = HEAD·마커 05ebb51, 04:28 기동 |
| 루틴 | 일일 리포트(평일 20:20)·주간 자문(화 20:30) 생성, 일일 스모크 성공(Notion+DB). 첫 자동 실행 월 09-07 20:20 |
| 핵심 발견 | **장중 stale 33% = H0UNCNT0 이 KRX 단독(nxt_false) 종목 프레임을 안 보냄**(07-24~ 만성). 보유 000815·003490 WS blind(REST 폴만). A=cycle252 배포 완료 · 프로브 도구 cycle253 배포 완료(기본 OFF) · **월 09:30 프로브 실행 승인(D8)** → 결과로 B(채널 리졸버, 8영역) 결정 |
| 미결 결정 | D1~D11 (§4) — 특히 **D8 월 09:30 프로브 실행 승인**(코드 준비 완료), D3/D4 cycle245 잔여, D5 TLS 도메인, D11 리팩토링 카드 채택 |

## 1. 배포 이력 (전부 EC2 검증)

| 시각(KST) | 커밋 | 내용 | 배포 모드 | 백엔드 |
|---|---|---|---|---|
| 09-04 19:20 | 13db0d9 | cycle247 Basic Auth 이중 로그인(Safari 아이콘 탐침 → `return 204`) | (구 파이프라인) | 재시작 |
| 09-04 21:00 | 6249755 | cycle248 선택적 배포 파이프라인 + CI 핫픽스 | `full reason=marker_missing` | 재시작 |
| 09-04 23:27 | d4fecb1 | cycle245 비터틀 ρ축 랏 상한 K_ρ=2.5 (BFB·VCP DB 선반영 20.0) | `full reason=backend_inputs_changed changed=24` | 재시작 |
| 09-05 00:29 | 2f76490 | cycle249 리포터 스코프 키 + 번들/외부 리포트 API + nginx map (migration 042) | `full changed=28` | 재시작 |
| 09-05 00:52 | 25b6951 | W2 대시보드 Claude 분석 표시 (frontend 전용) | **`frontend reason=frontend_only changed=4`** | **무접촉(Up 24m 유지)** — cycle248 실증 |
| 09-05 01:2x | d9561f1 · 97a1ec9 | 문서 전용 2건(cycle249 후속 종결 기록 · CLAUDE.md 표 cycle246~249 보강 + none 모드 정정) | CI `paths-ignore` — 배포 자체 없음 | 무접촉 |
| 09-05 01:51 | 1423a90 | cycle250 계좌 리스크 감시 평가 타임아웃(`account_risk_watcher.py`·`boot_manager.py`) | `full`(src 변경) | 재시작(01:51 재생성, startup 정상, `[api_auth_config]` 유지, 마커=1423a90) |
| 09-05 02:26 | f86bcc3 | cycle251 계좌 게이트 관측 노출(`log_analysis_engine.py` + 프론트 2파일) | `full`(src 변경) | 재시작(02:26 재생성, startup 정상, `/api/portfolio/risk` `account_gate` 8키 실측, 마커=f86bcc3) |
| 09-05 03:19 | 8f57bee | cycle252 no_feed churn 중단(`no_feed_registry.py` 신규 + `stale_watcher_core.py` + `db/stock_master.py`) | **CI 실패 → Deploy skipped** | 미배포(아래 핫픽스) |
| 09-05 03:33 | a375f51 | cycle252 CI 핫픽스 — 테스트 T2 의 caplog 필터를 WARNING 레벨로 한정(구현 무변경) → cycle252 본체가 이 배포로 반영 | `full`(8f57bee 누적) | 재시작(03:33 재생성, startup 정상, `no_feed_registry` import 실측, 마커=a375f51) |
| 09-05 03:51~04:00 | cefc4c8 · db48e1a · 04f070d · 4c19807 · f793817 · 07285ba | 테스트 위생 6건(리팩토링 리뷰 카드 1·2·3 — 사이클 한정 bare `git diff HEAD` 가드 폐기, HEAD 동결 가드 → 소스 세그먼트 sha 핀/키 집합 계약, 자기소멸한 승인 sha 핀 11항목 비움 + dead skip 테스트 삭제) | tests 전용 → `none`(무재시작) | 무접촉. CI: 04f070d·4c19807·f793817 은 `ast.dump` 버전 의존 핀으로 실패 → 07285ba 에서 초록 |
| 09-05 03:5x | 558c7d4 | 리팩토링 리뷰 메모(문서) | 배포 없음 | 무접촉 |
| 09-05 04:28 | 05ebb51 | cycle253 H0STCNT0 프로브 엔드포인트(`routes/realtime.py` 단독 +506) | `full`(src 변경) | 재시작(04:28 재생성, startup 정상, `GET channel-probe` = `count 0`, H0UNCNT0·잘못된 ticker POST 422 실측, 마커=05ebb51) |

모든 백엔드 재시작은 장외(정산 20:10 이후)였고 `market_blind_secs=0`. 마지막 검증(04:28): EC2 HEAD 05ebb51, 마커 05ebb51, 시도 마커 없음, 외부 401·아이콘 204 유지, 최근 30분 ERROR 0.

## 2. 일일 로그 분석 이관 (cycle249 → 루틴)

- **백엔드 배포 검증(00:29)**: nginx 렌더본에 `map $remote_user` 와 두 키 각 1회 · 루프백 실측 = 리포터 키 GET 200 / 번들 200 / `manual-sell`·`log-reports/run` POST·PUT 403 / external POST 200(ext_provider=smoke, OpenAI summary 보존) / 오답 키 401 · `[api_auth_config] reporter_enabled=true reporter_distinct=true`.
- **nginx 경유 리포터 실측(00:41, 호스트명)**: GET log-reports 200 · bundle 200 · POST manual-sell 403 · 오답 비밀번호 401, access log `user=reporter`.
- **루틴 W1**: `trig_01E6XNiNTxaLWNn7jeTXR9qZ` "auto_stock 일일 운영 리포트 (20:20 KST)" — 평일 20:20 KST(`20 11 * * 1-5` UTC), env 자동매매, `claude-fable-5-1`, 커넥터 Notion 만, 수동 백필 `date=YYYY-MM-DD`. 첫 자동 실행 = **월 09-07 20:20**.
- **스모크**: 1차(00:31) nginx `password mismatch` 401 — 사용자가 htpasswd 에 넣은 비밀번호와 환경 변수 값이 달랐다. 루틴은 실패를 Notion 페이지·푸시 알림으로 남겼다(설계대로). 00:41 htpasswd `reporter` 줄을 **환경 변수 값 기준**으로 재생성 → **2차(00:42~00:59) 성공**: `POST …/external` 200, `ext_provider=claude-routine`, `ext_model=claude-fable-5-1`, findings 13, report_md 16,967자, Notion 09-04 페이지 갱신(https://app.notion.com/p/3d1438fa0d26812fa291c11314ff348e), 휴대폰 푸시 발송. OpenAI 행(summary·findings 6)은 보존됨.
- **루틴 리포트 요지(09-04)**: 실현 −20,350원(일 −0.78%, 누적 −6.09%), 체결 13건 전부 COMPLETED, KIS 거부·APBK·체결 불일치 0, 안전 규칙 위반 0. 최대 손실 = LTV 000500 1주 폴백 랏(설계 랏 4.23배, −11,000원) = cycle245 발단 재현. **HIGH 1건 = 장중 후보 35~38종목(구독의 33%)이 종일 stale**(삼성전자우·GS건설·한화솔루션 등 유동주 포함, `stale_force_retry` 877건/일에도 미회복, 09-01 이후 만성) + 보유 003490·000815 main 간헐 stale. 부수 = 15:30 이후 보유 9종목 HIGH 재구독 5분 반복(398 언급), VCP 후보 0 으로 5분마다 재-prepare 124회, 삼성화재우 1주 = 순자산 15.7%. D+1 서명(cycle228~241)은 전부 정상, BFB 첫 청산(001450 flag_low 50,500)으로 228-B stamp 계약 실증.
- **W2 대시보드**: 25b6951 — "Claude 분석" 블록·목록 배지·ext_findings 정규화·error boundary, vitest 479 PASS. 배포 완료(00:52, frontend 만 재생성) — 대시보드 Logs 탭 09-04 에서 바로 확인 가능.
- **W4(미결)**: OpenAI 20:00 자문·20:10 분석은 병행 비교(~09-19) 후 off 스위치 사이클로 처분.

## 2.5 cycle250 — 계좌 리스크 감시 평가 타임아웃 (cycle239 후속 A 종결)

- **발단**: `watch_loop`(5분)·부팅 동기 1회가 `run_account_risk_watch_once` 를 타임아웃 없이 await → KIS 세마포어·asyncpg acquire hang 이면 루프가 죽지 않고 **멈춰** `[account_risk_watch_loop_died]` 도 무발화, 그날 평가 소실 + 부팅 정지. cycle239 는 소비자 신선도 fail-open 으로 피해만 막았고 hang 자체는 못 풀었다.
- **시정**: `run_account_risk_watch_once_guarded` — `asyncio.wait_for(…, 300)`, **TimeoutError 만** 포착 → `_gate_active=False` + `_evaluated_mono` 스탬프 + 활성이었으면 `released reason=eval_timeout` + `[account_risk_eval_timeout] timeout_secs= count=` WARNING 1회/일. 호출 2곳 교체, 본체 무변경(AST 가 `ast.dump` 동일 검증). `CancelledError` 동반 포착 금지(외부 취소 전파). 부팅 hang 무한 → ≤300s(07:45 첫 줄이라 07:59 사전구독 무영향).
- **검증**: asyncio 렌즈 HIGH/MEDIUM 0(실제 KIS 세마포어·`_rate_lock`·asyncpg 0.31 취소 시 슬롯 누수 0) · 뮤테이션 31 → **31 KILLED**(escape 4 는 회귀로 봉인) · 신규 회귀 29 · 백엔드 6,359 PASS(flake 1 격리 통과) · 8영역·scheduler.py diff 0.
- **D+1(09-07)**: `[account_risk_eval_timeout]` **0건이 정상** — 1건이라도 있으면 그 자체가 hang 실측 = 후속 B(재스폰)·E(`pg` acquire 타임아웃) 착수 근거.

## 2.6 cycle251 — 계좌 SOFT 게이트 관측 노출 (cycle239 후속 F·G 종결)

- **왜**: cycle233 SOFT Σ상한 활성화 게이트(AND, ~09-12)의 한 축 "장중 `age_secs ≤ 600`" 과 cycle250 D+1(`eval_timeouts_today` 0)이 `curl /api/portfolio/risk` 로만 보였다.
- **무엇**: 20:10 리포트 스냅샷에 `account_gate`(`get_gate_state()` 복사 + `eval_timeouts_today`) 를 over_cap 과 **독립 try** 로 부착(→ OpenAI 프롬프트·JSONB·20:20 루틴 번들 동시 전파) + 대시보드 `PortfolioRiskCard` 배지(차단 중/경고/정상 · STALE N분 전 · KST HH:mm · 키 부재 시 "게이트 정보 없음"). `is_soft_gated()` 호출 금지(stale cap 선소비) AST 봉인. `account_risk_watcher.py`·`routes/portfolio.py` 무접촉.
- **검증**: 뮤테이션 19/19 KILLED(escape 2 + 실결함 1 = ko-KR 12시제 '오후 01:05' → `hour12:false`), 백엔드 3,962 PASS, vitest 488, tsc 0.

## 2.7 포렌식 — "후보 35~38종목 종일 stale" 의 정체 (루틴 HIGH 1건 → 원인 확정)

- **결론**: stale 고정 종목은 세션·전략·유동성과 무관하게 **`stock_master.nxt_tradable=False`(KRX 단독, NXT 비대상) 종목과 1:1** 이다. 09-01~09-04 나흘 × 184~209 구독 종목이 `nxt_true ↔ 프레임>0` / `nxt_false ↔ 프레임=0` 으로 **예외 0건 완전 분할**(유일한 예외 064550 은 09-02 NXT 편출과 동시에 프레임 0 = 자연 실험). 삼성전자우(거래대금 3,538억)·카카오·GS건설 포함이라 침묵이 아니라 **채널 결함** — 모든 구독이 통합 채널 `H0UNCNT0` 단일이고(사이클 26 의 시간대별 `H0STCNT0` 전환은 정의만 있고 호출자 0), **KIS 통합 채널이 NXT 거래대상 종목만 송출한다는 가설(≈90%)**. KIS 공식 문서·샘플엔 대상 범위 명시가 없다(MCP 재확인).
- **만성**: 최소 07-24 부터 매일 31~44%. "09-01 이후" 는 `system_logs` INFO 2일 retention 이 만든 관측창 착시. 09-01 배포 0건, cycle240/241 은 원인도 치유도 아님.
- **비용**: K stale watcher 가 그 종목들을 종목당 하루 ~134회 7개 보조 세션으로 옮기며 unsub/sub — 하루 SEND ≈14,600, `[ws_ack_orphan]` 7,120, 풀 슬롯 22~24% 를 회복 가치 0 에 소모.
- **손절 사각(중요)**: 보유 000815·003490(kojiro, 둘 다 nxt_false)은 WS 로 **매일 종일 blind** — 손절 평가는 `_swing_rest_poll_loop` 60s(09:05~15:20)만. 공백 = 09:00:00~09:05(시가 포함) + 15:20~15:30 + 60s 해상도. **tick 전략(VB/LTV/BFB/VCP/momentum)이 nxt_false 를 보유하게 되면(NXT 편출 사건) 손절 평가 0** 이 되는 경로가 있다. 또 최근 35일 tick 전략 매수 60건이 100% nxt_true = KRX 단독 종목(시총≥1,000억의 64%)이 tick 전략에 구조적으로 안 보인다.
- **조치**: A = cycle252(야간 진행, 비8영역 — LOW no_feed 종목 재등록 churn 중단 + `[no_feed_held]` 일일 WARNING, HIGH 경로 byte 동일 보존) · **B = 속성 기반 채널 리졸버(`nxt_tradable=False` → `H0STCNT0`), 8영역(`scanner.py`·`websocket.py`·`websocket_pool.py`·`order_engine.py`) 승인 필요 → §4 D8** · 보고서 정본 `_workspace/forensics/stale_candidates_0904.md`(177행, 검증 명령 부록 포함).

## 2.8 cycle252 — 무송출(no_feed) 종목 K watcher 재등록 churn 중단 (포렌식 권고 A, 보수 변형)

- **무엇**: `no_feed_registry`(stock_master `nxt_tradable=False` 집합, 600s TTL, fail-open) + K watcher 루프에서 **LOW no_feed 종목만** SEND·스탬프·history 생략(`continue`). **HIGH(보유) 경로 byte 동일** — 가설이 틀렸을 때 잃는 것이 손절 커버리지라 포렌식 원안(HIGH 도 제외)보다 보수적으로. 대신 `[no_feed_held] tickers=[000815, 003490]` WARNING 1회/일. `_stale_retry_count` 는 계속(r>5 홀드) → universe guard 저유동 축출 보존. `[tick_coverage] stale` 은 **불변이 정상**(은폐 금지).
- **검증**: 뮤테이션 26/26 KILLED, 차분 1,200 + 5,000 조합 불일치 0(no_feed ∅ 이면 HEAD 완전 동일, 아니면 차이는 LOW no_feed 의 SEND뿐, SEND 27,538→21,728), 소비처 4곳(universe guard 통합 테스트 포함), 기존 K watcher 회귀 541 무수정, 신규 51. 적대 검증이 잡은 실결함 1 = 관측 헬퍼가 예외를 전파하면 HIGH 재등록 사이클이 끊기던 경로(try/except 봉인).
- **2차 효과(수용)**: LOW no_feed 의 r=6 영구 홀드 → universe guard 평가 체류율 ≈50%→100% → 유동 nxt_false 후보 REST(`inquire_ccnl`) 5분당 ≈1→2회(+35~78/5분, KIS 20/s 대비 무시 가능). B 착지 시 소멸.
- **D+1(09-07)**: `[stale_force_retry]` 09:05~15:20 399→≈0 · 보조 SUBSCRIBE ≈957→<150 · `ws_ack_orphan` 7,120→<500 · `no_feed_skipped>0` · `[no_feed_held]` 1행 · `[tick_coverage] stale` 35~38 불변. ⚠️ SEND ≈14,600/일 감소는 **예상치**(포렌식 실측 낭비량) — 월요일 로그로 실측하며 HIGH 2종목 분은 설계상 남는다.

## 2.9 리팩토링 검토 (사이클 247~252 누적 6사이클, refactor-expert, 코드 무수정)

- 메모 = `_workspace/refactor/2026-09-05_review.md` — 카드 10장(LOW 6 · MEDIUM 4 · HIGH 0). 야간에 **카드 1 즉시 처리**(cefc4c8: cycle252 의 사이클 한정 bare `git diff HEAD` 가드 G-252-5/5b 폐기 — 5b 는 전 트리 화이트리스트라 cycle253 워킹트리에서 이미 RED 였다).
- 남은 카드 요지: ② HEAD 기준 `ast.dump` 동결 3건(G-250-5·G-251-2/2b — 커밋 후 공허, 편집 순간 RED) 재핀/전환 ③ 자기소멸한 sha 핀 dict 5개 11항목 정리 ④ **`DailyEmitCap` 표준 진입점**(peek→로그→mark + KST 날짜 자기 리셋 손 복제 22곳/5파일, mark-before-log 잔존 6곳) ⑤ 관측기 자기 실패 흔적 4방언 → `trace_observer_failure` 단일화 ⑥ `account_gate` 스냅샷 단일 소유자(리포트 9키 vs 라우트 8키) ⑦ `log_analysis_engine.py` 922L 분할 ⑧ 🔒 사이클 26 죽은 코드(`get_active_tick_tr_ids`·`_board_transition_loop`, src 호출 0·108일 미배선) 삭제 — 8영역 scanner 접촉이라 **P1-7 B 승인과 묶어서** ⑨ 프론트 KST 포맷 유틸(복제 15곳) ⑩ `AccountGate.level | string` 유니온 무력화.
- 부수 발견(행위 변경이라 판단 요청): `routes/log_reports.py:104` GET 만 `fromisoformat` — `20260904` 형 날짜 수용 규칙이 3 엔드포인트 간 불일치.

## 2.10 cycle253 — H0STCNT0 다크런치 프로브 엔드포인트 (P1-7 B 1단계, 8영역 무접촉)

- **무엇**: `POST/GET/DELETE /api/realtime/channel-probe` — 라우트 파일 하나(+506L). 기본 OFF. POST 는 `bypass_limit=False` 리터럴·LOW 슬롯, `H0UNCNT0` 422, 기구독·보유·익일청산·후보(breakout∪스윙∪momentum) 409, cap 3, 구독 후 세션 미배정이면 409 `subscribe_dropped`, 전일 항목 자동 축출. GET 은 `received(last_tick>started_at)`·`first_tick_at`·`price(current_price)`·`acml_vol`·`live_tick_subscribed`·`in_desired_now`. DELETE 는 세션 전수 순회 해제(HIGH 승격 후 보조 세션 고아 튜플까지) + 라이브 라우팅 보존.
- **검증**: 적대 검증 확증 11건 전부 처리(MEDIUM 3 = system_logs 이중 INSERT(cycle72 G-6 우회) 제거 · `price` 키 오류(명세 오류가 전파) · HIGH 승격 고아 튜플), 뮤테이션 17/18(+1 등가), routes·ast·realtime 1,233 PASS, 실 풀 2세션 재현으로 TICK 필터 격리 확증.
- **잔여 한계**: 5분 `resubscribe_stale_priority` 는 `ticker_last_tick` 전수 소스라 cycle240 desired 필터가 꺼진 비정상 상태에서만 이중 채널 가능 → 프로브 창 ≤15분 + DELETE 필수.

## 3. 주간 자문 루틴

- `trig_01H1TtfhP52CXKuyxwG2KnBW` "auto_stock 주간 파라미터 자문 (화 20:30 KST)" — `30 11 * * 2` UTC, 첫 실행 **화 09-08 20:32**(stagger).
- 프롬프트 = `advisor_prompt_review_20260903.md` §F v2 원칙 이식: 목적함수(기대값, 조임 편향 89.2% 재생산 금지) · 시스템 사실(상대 비중·불변식·터틀 2축 캡) · **절대 금지 키**(max_positions·buy_threshold·donchian_period·max_breakout_extension_pct·atr_trail_mult·breakout_fail_n_days·max_lot_units·max_lot_ratio_mult·sizing_mode·tradable_boards·cash_usage_ratio·enabled) · **사람 결정**(max_scan_stocks 4000 / BFB retention 0 동결(왕복≥10 ∧ 영업일≥10) / kojiro 0.166 / K_ρ 2.5·20) · 표본 규약(왕복<10 → 숫자 대신 가설) · 전략당 최대 3키.
- 산출 = PR `_workspace/domain_consult/weekly_advice_YYYY-MM-DD.md`(브랜치 `claude/weekly-advice-*`, **자동 적용 없음**) + Notion https://app.notion.com/p/3d1438fa0d2681ae9502c26d1a2c4ebe . 리포터 자격은 GET 만 통과하므로 PUT 은 구조적으로 불가.
- 첫 산출물(09-08) 검토 후 결정할 것: §4/§5 목록을 코드 정본(`advisor_policy.py`, 자문 리뷰 사이클 A)으로 옮길지, OpenAI 20:00 자문을 끌지.

## 4. 분기·결정 필요 항목 (사용자 판단 요청)

| # | 항목 | 권고 |
|---|---|---|
| D1 | **reporter 비밀번호 불일치** — 사용자가 htpasswd 에 넣은 값과 환경 변수 값이 달랐다. 야간에 htpasswd 를 **환경 변수 값 기준**으로 재생성했다(백업 `/tmp/htpasswd.bak.*`). 이제 유효 비밀번호 = 환경 변수에 입력한 값. 스크린샷에 값이 노출됐으므로 원하면 교체 | 당분간 유지, 교체 시 htpasswd 와 환경 변수를 함께 |
| D2 | **OpenAI 경로 처분(W4)** — 20:10 일일 분석·20:00 자문은 병행 비교(~09-19)까지 유지 | 09-19 이후 `system_config` 토글 사이클 |
| D3 | **cycle245 잔여 F-9** — 터틀 2전략(donchian·kojiro)의 1주 폴백 랏이 ρ 상한의 3.86~5.00배로 남음. 닫으려면 결정 ⑦(두 캡 상호배타)을 min 합성으로 재검토해야 함(cycle242 무손상 — 실측 97/0) | domain-consult 1회 후 결정 |
| D4 | **cycle245 F-10** — BFB/VCP/donchian/kojiro 가 주문 확정 전에 `_bought_today` 를 기록 → 캡 0 이 당일 표본을 소실. 8영역(`order_engine`/`check_buy_signal` 반환 계약) 승인 필요 | 승인 시 별도 사이클 |
| D5 | **TLS(F1)** — 루틴이 매일 Basic 자격을 평문 HTTP 로 보낸다. EC2 공개 DNS 는 Let's Encrypt 불가라 **도메인 확보**가 선결 | 도메인 있으면 알려 주세요 |
| D6 | **주간 자문 정본 위치** — 프롬프트 §4/§5(봉인 키·결정 로그)를 코드 정본(`advisor_policy.py`)으로 옮길지 | 09-08 첫 산출물 본 뒤 |
| D8 | **채널 리졸버(B) 착수 승인** — 1단계 다크런치 프로브: 보조 세션 1개에서 005935·035720 을 `H0STCNT0` 로만 구독해 프레임 수신 실측(장중 1시간) → 성공 시 `tick_tr_id_for(ticker)` 리졸버로 `TICK_TR_ID` 직접 사용처 전부 경유 + 풀 TICK 필터 `{H0UNCNT0,H0STCNT0}` + 편출/플리커 debounce. 접촉 8영역 4파일 → sha 핀 재핀·뮤테이션 실증 대상 | **프로브는 8영역 무접촉으로 가능** — `kis_ws_pool.subscribe` 가 tr_id 를 받고 handler 가 H0STCNT0 를 동일 처리하므로 라우트 전용 엔드포인트 `POST/GET/DELETE /api/realtime/channel-probe`(기본 OFF, 보유·후보·기구독 종목 409 거부, `bypass_limit` 금지)로 월 09:30 curl 실측 가능. 설계 = `_workspace/forensics/krx_channel_probe_design.md`. **야간에 cycle253 으로 구현·배포까지 시도**(승인 필요한 것은 월요일 '프로브 실행' 뿐) |
| D11 | **리팩토링 카드 채택** — 메모 10장 중 ①②③(테스트 위생)은 야간에 처리 완료. 남은 7장 = ④⑤⑥⑦(관측·모듈 구조, MEDIUM, 사이클 1~2개) + ⑧(사이클 26 죽은 코드, 8영역 승인 = B 와 동반) + ⑨⑩(프론트 소소, LOW) | ④~⑦ 은 결정, ⑧ 은 D8 결과와 함께, ⑨⑩ 은 승인 없이 진행 |
| D10 | **`pg._pool.acquire()` 타임아웃(cycle239 후속 E)** — 풀 생성은 `command_timeout=30`(문장 타임아웃)만 있고 **커넥션 획득 대기에는 타임아웃이 없다**(`src/db/pg.py:128` 등 5곳). 풀 고갈 시 모든 DB 호출이 무한 대기 = cycle250 이 300s 로 막은 hang 의 공통 뿌리. 시정안 = `acquire(timeout=30)` + `_with_retry` 의 재시도 예외에 `asyncio.TimeoutError` 편입. 단 **전 호출자(8영역 `order_engine` 의 `insert_trade` 등)의 실패 모드가 '무한 대기 → 예외' 로 바뀌므로** 호출자 계약 검토가 선행 — 야간 자율 범위 밖으로 판단해 미착수 | 주중 별도 사이클(호출자 전수 + 뮤테이션), 8영역 승인 동반 |
| D9 | **REST 폴 조기 시작(C)** — `SWING_REST_POLL_EARLY_START` 09:05 → 09:00:30(held_only) 로 시가 직후 5분 공백 축소. scheduler.py 상수(3,999L 라인 상한) | B 착지까지 임시. 승인 시 1줄 |
| D7 | **일일 리포트 판독 채널** — `[ratio_cap_config]` 등 INFO 마커는 20:10 리포트에 안 실림. 루틴 프롬프트가 `/api/logs/search` 로 직접 대조하도록 돼 있어 루틴 리포트가 D+1 채널 역할을 대신함 | 유지 |

## 5. 월요일(09-07) 아침 D+1 판독 체크리스트 (07:55 부팅 후, `system_logs` 직접 조회)

- [ ] `[ratio_cap_config]` 전략별 1행: LTV·VB·momentum `cap=on k=2.50` / BFB·VCP `cap=on k=20.00` / donchian·kojiro `cap=backstop`, `cutoff_price` 병기(예산 기준 LTV·VCP 130,100 / VB 341,515 / BFB 243,940 / MOM 81,312 부근)
- [ ] `[ratio_notional_blocked]` LTV 0~1건/일 정상, **BFB·VCP 0** (선반영 확인). `[ratio_cap_skipped]`·`[ratio_cap_clamped]` 0행
- [ ] cycle242 `[fallback_cap_config] cap=on k=2.00`(donchian·kojiro) 존속
- [ ] `[api_auth_config] reporter_enabled=true reporter_distinct=true`, `[api_auth_reject]` 급증 없음
- [ ] 월 20:20 일일 루틴 첫 자동 실행 → `ext_provider=claude-routine` 행 + Notion 페이지 + 대시보드 "Claude 분석" 블록
- [ ] **cycle250**: `[account_risk_eval_timeout]` 0건(1건이라도 있으면 hang 실측 = 후속 B·E 근거) · `[account_risk_watch_loop_exit] reason=running_false` 20:10 1건
- [ ] **cycle251**: 대시보드 포트폴리오 리스크 카드 "계좌 게이트" 블록 — 장중 `정상` + `마지막 평가 N분 전` 없음(fresh) · 20:10 이후 리포트 `portfolio_risk_snapshot.account_gate.eval_timeouts_today=0`
- [ ] **cycle252**(호스트 로그 `~/auto_stock/logs/auto_stock.log.2026-09-07`): `[stale_force_retry]` 09:05~15:20 ≈0(HIGH 2종목 분만) · 보조 세션 `[ws_action_summary]` SUBSCRIBE <150 · `grep -c ws_ack_orphan` <500 · `[stale_watcher_summary] no_feed_skipped>0` · `[no_feed_held] tickers=[000815, 003490]` 1행 · `[tick_coverage] stale` 35~38 **불변(정상)** · `[universe_excluded]` 증가는 정상 · `[no_feed_registry_refresh_failed]` 0
- [ ] **cycle253**(배포됐다면): 프로브 엔드포인트는 호출 전까지 무동작 — `GET /api/realtime/channel-probe` 가 `{probes: [], count: 0}`. 승인 시 §7 절차
- [ ] 이상 서명: 비터틀 `cap=off`(키 소실) / 터틀 `backstop` 부재 / `capped_qty>0` / `k_axis_probe_error`·`exception` ≥1 / cycle242 마커 소실 → 즉시 조사·롤백(K 다이얼 20.0 PUT)

## 7. 월요일 프로브 실행 절차 (D8 승인 시, 09:30 이후 — 코드 변경 없음, curl 3개)

1. 후보 2종목: `nxt_tradable=False ∧ 유동` 이면서 `GET /api/realtime/subscriptions` 의 `tickers.subscribed` 에 없고 보유가 아닌 종목(후보 유니버스에 있으면 라우트가 409 `in_desired_universe` 로 알려준다 → 다른 종목).
2. `POST /api/realtime/channel-probe {"ticker":"XXXXXX","tr_id":"H0STCNT0"}` ×2 → 5분 간격 `GET /api/realtime/channel-probe` 3회.
3. 판정: `received=true` → **가설 확정(H0STCNT0 송출)** → B 본 시정(채널 리졸버, 8영역) 착수 결정. 15분간 `subscribed∧acked∧!received` → **반증** → KIS 문의 + C(REST 폴 조기 시작) 임시 대응. GET 의 `in_desired_now=true` 가 뜨면 즉시 DELETE(프로브 중 후보 편입).
4. `DELETE /api/realtime/channel-probe/{ticker}` ×2 (안 해도 20:00 정리에 함께 해제). 결과를 `_workspace/00_URGENT_WORKLIST.md` P1-7 B 에 기록.
   - 안전장치: 프로브는 `bypass_limit=False`·LOW 슬롯, 동시 3개 상한, 기구독·보유·익일청산·후보 종목 거부(라우팅 맵 덮어쓰기·실매수 신호 경로 차단), TICK 필터 밖이라 K watcher·universe guard·델타 삭제 무관여.

## 6. 밤사이 발견·정정한 사실

- **Compose v5.1 `up --build` 는 이미지 ID 가 같아도 backend 를 재생성** → cycle248 로 diff 기반 선택 배포 도입. 실증: 첫 배포 full → cycle245 full(backend 변경) → W2 **frontend 만**(backend 무접촉) → 문서 전용 커밋 d9561f1 은 CI `paths-ignore`(`**.md`·`docs/**`·`_workspace/**`) 로 CI/Deploy 가 뜨지 않음(정상, `none` 은 재실행·tests 전용 push 에서만 발생)
- Mac 슬립이 21:0x~22:41 워크플로를 죽였다 → `caffeinate` 로 야간 유지(메모리 기록)
- 요일 착오 정정: 09-04 금 → **09-05 토**. 다음 거래일 09-07(월). 루틴 next_run 이 월요일로 잡힌 것은 정상
- 루틴 1차 스모크 실패 원인은 htpasswd 값 불일치(D1)이지 코드 결함이 아니었다. 루틴은 실패도 Notion·푸시로 남겨 관측 가능
- **cycle252 CI 1차 실패(구현 결함 아님)**: CI 는 루트 로거가 DEBUG 라 `[no_feed_held] emit 실패` debug 흔적 행까지 caplog 에 잡혀 "WARNING 1회" 단언이 2 로 깨졌다. 로컬은 INFO 라 통과 — `--log-level=DEBUG` 로 재현 후 레벨 필터로 시정(a375f51). 교훈 = caplog 단언은 레벨·prefix 로 한정하고 push 전 DEBUG 로 한 번 돌린다.
- **테스트 위생 커밋의 CI 2차 실패(구현 무관)**: 카드 2 에서 만든 `ast.dump` sha256 핀이 파이썬 버전 의존(로컬 3.13 vs CI 3.12 는 `ast.dump` 출력이 다름)이라 04f070d CI 만 붉어졌다 → 소스 세그먼트(`ast.get_source_segment`) sha 로 전환(07285ba). 교훈 = 핀은 파일 내용에서만 파생시킨다(AST 덤프·unparse 금지).
- 프리시드 확인: 00:41 `/api/trading/status` 에서 vcp `max_lot_ratio_mult=20.0`, kojiro `2.5` (DB 선반영이 d4fecb1 재시작으로 로드됨)

## 부록 A. 야간 커밋 목록 (신→구, 13db0d9 cycle247 이후 21건)

| 커밋 | 시각 | 제목 |
|---|---|---|
| 05ebb51 | 04:20 | feat: KRX 단독 채널(H0STCNT0) 다크런치 프로브 엔드포인트 (cycle253, 포렌식 P1-7 B 1단계, 8영역 무접촉) |
| 07285ba | 04:00 | test: G-250-5 핀을 ast.dump 에서 소스 세그먼트 sha256 으로 전환 — ast.dump 는 파이썬 버전(로컬 3.13 vs CI 3.12)마다 달라 CI 거짓 FAIL (04f |
| f793817 | 03:55 | test: cycleM5 가드 파일의 미사용 8영역 helper(_SAFETY_PATHS·_git_changed_files) 제거 — 카드 3 후속 정리 |
| 4c19807 | 03:55 | test: 자기소멸한 8영역 승인 sha 핀 dict 5개(11항목) 비움 + cycleM5 skip 처리된 dead 가드 삭제 (리팩토링 리뷰 카드 3) — 가드 본체·면제 기전은 유지 |
| 04f070d | 03:53 | test: HEAD 기준 ast.dump 동결 가드 3건 처분 (리팩토링 리뷰 카드 2) — G-250-5 는 sha256 리터럴 핀, G-251-2 는 get_gate_state 8키 = 프론트  |
| 558c7d4 | 03:52 | docs: 리팩토링 리뷰 2026-09-05 — 사이클 247~252 누적 6사이클, 카드 10장(LOW 6 · MEDIUM 4 · HIGH 0), 코드 무수정 |
| db48e1a | 03:51 | test: cycle252 AST 가드 파일 미사용 subprocess import 제거 |
| cefc4c8 | 03:51 | test: cycle252 사이클 한정 bare git-diff 가드 G-252-5/5b 폐기 — 배포 후 자기소멸 + 전 트리 화이트리스트가 후속 사이클 워킹트리를 즉시 RED 로 만들던 가드 ( |
| a375f51 | 03:26 | test: cycle252 T2 — CI(DEBUG 루트 로거)에서 실패 흔적 debug 행이 함께 캡처되던 caplog 필터를 WARNING 레벨로 한정 (CI 핫픽스) |
| 8f57bee | 03:18 | fix: 무송출(nxt_false) 종목 K stale watcher 재등록 churn 중단 (cycle252, 포렌식 P1-7 권고 A 보수 변형) |
| 8b146ff | 02:43 | docs: KRX 단독 채널(H0STCNT0) 프로브·채널 리졸버 설계 메모 (P1-7 B 결정 보조, 8영역 무접촉 프로브 경로) |
| f86bcc3 | 02:18 | feat: 계좌 SOFT 게이트 관측 노출 — 20:10 리포트 병기 + 대시보드 배지 (cycle251, cycle239 후속 F·G 종결) |
| 9dc3298 | 01:56 | docs: 포렌식 — 장중 stale 33% 의 정체 = 통합 채널 H0UNCNT0 이 nxt_tradable=False 종목을 무송출 (P1-7 등재, A=cycle252 · B=채널 리졸버 승인 |
| 1423a90 | 01:43 | fix: 계좌 리스크 감시 평가 타임아웃 — hang 시 루프 생존 + fail-open (cycle250, cycle239 후속 A 종결) |
| 97a1ec9 | 01:42 | docs: CLAUDE.md 하네스 표 cycle246~249 행 보강 + cycle248 none 모드 설명 정정 (paths-ignore 로 docs 전용 push 는 배포 자체가 뜨지 않음) |
| d9561f1 | 00:53 | docs: cycle249 후속 종결 기록 — W1 일일 루틴·W2 대시보드·W3 주간 자문 루틴 (문서 전용) |
| 25b6951 | 00:44 | feat(frontend): 일일 리포트 탭에 Claude 외부 분석(ext_*) 표시 (W2 — cycle249 후속, frontend 전용) |
| 2f76490 | 00:21 | feat: 일일 로그 분석 이관 1단계 — 리포터 스코프 키 + 번들/외부 리포트 API + nginx 사용자별 키 주입 (cycle249) |
| d4fecb1 | 23:19 | feat: 비터틀 전략 랏 명목 ρ축 상한 max_lot_ratio_mult(K_ρ=2.5) — 1주 폴백 과잉 시정 2단 (cycle245) |
| 6249755 | 20:51 | fix: cycle248 CI 핫픽스 — cycle145 배포 가드 재스코프 + T-16 60s timeout 회피 |
| 332045b | 20:25 | feat: 선택적 배포 — 모든 push 가 backend 를 재시작하던 파이프라인 시정 (cycle248) |

## 부록 B. 쉬운 말 리포트(아티팩트)에서 단순화한 곳 — 정확값 대응표

| 아티팩트 표기 | 정확값(출처) |
|---|---|
| 하루 130번씩 다시 신청 | 종목당 SUBSCRIBE 이벤트 중앙값 134(min 78·max 135), 포렌식 ②-5 |
| 하루 3,500억 원 거래 | 005935 삼성전자우 09-03 거래대금 3,538억(포렌식 ②-2) |
| 장중 약 400줄 → 거의 0 | `[stale_force_retry]` 09:05~15:20 399건(포렌식 ②-5) |
| 하루 약 14,600번 요청 | SUBSCRIBE 7,492 + UNSUBSCRIBE 7,118 = 14,610(포렌식 ②-5) — 감소는 **예상치**, 월 실측 |
| 보유 9종목 중 두 종목 | 09-04 기준 positions 9(포렌식 시점), 09-05 현재 4 |
