# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + AWS RDS PostgreSQL(DB). 다중 전략 아키텍처.

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력 (verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
> 시스템 흐름 도식: [`docs/architecture.md`](docs/architecture.md)

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다. *매매 의사결정의 깊이* 는 도메인 전문가의 사전 자문으로 보완하고, *코드 품질 드리프트* 는 리팩토링 전문가의 주기적 검토로 흡수한다.

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})` 로 라우팅한다. team-leader 가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 매매 의사결정 자문 (신규 전략·파라미터·보드 행태·시장 레짐·KIS 거부 해석) → `domain-consult` 스킬 (`domain-expert` 에이전트) — Phase 2.5 명세 분해 *전* 또는 사이클 중 행위 영향 평가 시
- 주기적 리팩토링 검토 (사이클 5회 누적 또는 명시 요청) → `refactor-review` 스킬 (`refactor-expert` 에이전트) — Phase 4.5
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`
- KIS API 정본 스펙 (TR_ID·응답 구조·거부 코드) → `kis-mcp-query` 스킬 (backend-dev / tdd-engineer / tester / refactor-expert 공유)

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 구현 계획·검수·리팩토링 검토 | **fable** | `team-leader`, `tester`, `refactor-expert` |
| 테스트 설계·도메인 자문 | **opus** | `domain-expert`, `tdd-engineer` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 하네스 변경 이력 (요약)

이 표는 **최근 ~15개 사이클의 한 줄 요약만** 유지한다. 각 행은 반드시 한 줄 — verbatim 금지. 신규 사이클 완료 시: (1) 이 표 상단에 한 줄 요약 1행 추가 + 가장 오래된 1행 제거(15행 유지), (2) 사용자 보고 verbatim·회귀 가드·영속 의무·검증 수치 등 상세는 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 에만 append.

| 날짜 | 사이클 | 한 줄 요약 |
|------|--------|-----------|
| 2026-08-18 | kojiro 브레이크이븐 플로어 다크런치 (cycle220) + 청산손실 심층 리뷰 | 실측 9왕복(-14,450원·승률 11%·RR 3.19 vs 필요 8.0) + domain-consult(`kojiro_exit_loss_review.md`). **판정 = 진입결함 아님**: RR 은 안 깨졌고 승률이 defensive 레짐 세금(손익분기 23.8% vs 관측 11%), 오염 3건(DMS/iM/삼영 -8% 클러스터 = 08-04 `_effective_atr` 시정 전 2ATR 죽음 시기 백스톱 증폭) 보정 시 -2.98%→-2.2~-2.5%. **진짜 갭 = 이익보호 전무** — 08-18 샹들리에 3청산(영원무역 +9.4%→-4.4%·LG생건우 +6.7%→-3.4%·CJ CGV +10.7%→-1.1%) 전부 +1.5N 도달 후 전량 반납. 스테이지3 0발화는 설계 의도(대순환 롤오버 늦은 신호, 샹들리에 선행 정상). 시정 = `breakeven_promote_atr=0.0` **다크런치**(donchian P1 선례) — §2 승격(`high≥buy+mult×ATR`→`eff=max(eff,buy)`→`_stop_floor` tighten-only 래칫 영속) + `recompute_held_atr` 재시작 재도출(H-1 고점 복구 후) + `_position_stop_price` be_line 4선 max read-only 미러(커플링 불변식). **샹들리에 2.5 불변**(domain 금기 — 플로어≠트레일, fat-tail 미절단). AI weight 0.6→0.2 권고(08-13/14 pending) = **채택 반대**(오염데이터 기반+Σ캡 중복 디리스크+0.2 는 1주/0주 양자화로 표본 해상도 파괴) → N=10 재튜닝서 exit 패키지와 재결정(강제 시 0.4). 활성화 = N=10(청산 1건 남음) 시 DB UPDATE(운영 DB 키 부재 실측 확인=다크 확정). kojiro.py 단독 +40/-7, 8영역+scheduler diff 0, 신규 21 + kojiro 227 PASS, 백엔드 4,951 PASS |
| 2026-08-14 | 재구독 안전망 정합화 (cycle215~218) + 세션증설 | 실측 손절 사각 발견→3+1 사이클 시정→D+1 확증. **cycle215** split-brain 복구 — `resubscribe_stale_priority`(5분)의 subscribe *전* `unsubscribe_in_pool` 선행(K watcher 342 패턴). OPSP0008 거부 후 `_ticker_to_session[t]=main` 잔존→풀 dedup 가드가 재SEND 억제→개장러시 매수 보유 종목 온종일 미구독=손절 사각(실측 001450/053800 5h+ 미구독, 스윙폴 60s 보강뿐·非스윙폴이면 완전 사각). 3렌즈 적대적 검증(workflow)으로 근본원인 확정. **cycle216** 동시호가 LOW-scoped skip(HIGH 09:00 갭개장 대비 유지) + LOW-only throttle(`RESUBSCRIBE_THROTTLE_SECS=180 < 300` 불변식·HIGH 면제) — domain-consult(HIGH throttle 오작동=손절사각 vs LMS는 LOW cap10 상주). **cycle217** 배포 후 자가발견 회귀 — cycle215 `unsubscribe_in_pool`이 미구독 stale 후보(`ticker_last_tick` 소스)까지 KIS unsubscribe SEND→OPSP0003 'not found' 766건/일. 구독상태 가드(`get_subscribed_tickers` 스냅샷: 구독→`unsubscribe_in_pool` / 미구독→`_ticker_to_session.pop` 직접)로 D+1 766→0 확증. **cycle218** r 카운터 무한 climb(051905 r=131) 관찰성 — cooldown-skip 분기 `_stale_retry_count=MAX+1` 홀드(r>5 전부 동일 임계경로라 행위 불변, 소비자 전수 감사). **세션증설**(보조 4→6=287슬롯, 틱 OPSP0008 4→0). 전부 `stale_watcher_core.py` 단독·**8영역 diff 0**·백엔드 4,905 PASS. 배포 175612e/f8f5105/6d07d63 (verbatim `docs/HARNESS_CHANGELOG.md`) |
| 2026-08-08 | VCP·BFB 확대 유니버스 (kojiro식 전체 상장) | 사용자 지시 "VCP·BFB 도 kojiro 처럼 전체 상장 중 일부필터 적용한 확대 유니버스". **4개 조사(구독 압력·테스트 영향·일봉 데이터·도메인) + 자문 + EC2 실측 + 적대적 검증(3렌즈)**. **구독 압력 재프레이밍** — 구독은 유니버스가 아니라 **셋업 통과 후보(get_scanned_tickers)에 비례**(VCP≈0→1~2, BFB≈18). VCP/BFB 는 kojiro 와 달리 **REST 폴 경로 없음**(tick 구독 의존) — kojiro 는 후보를 tick 구독 안 하고 REST 로 스캔해 확대를 감당. **일봉 blocker 반증** — daily-load 유니버스(지수∪500억/10억)가 kojiro 확대의 상위집합, EC2 실측 비지수 자격 641종목 중 **95.8%(614) ≥100일 적재·폴백 27종목뿐** → **scanner 무변경**(domain "979 폴백 폭주" HIGH 우려 반증, test-impact 판단 채택). **VCP** = 지수 제거(is_kospi200/kosdaq150=None) + 거래대금 10억 신설(하드코딩 0→실사용) + max_scan 200→4000. **BFB** = 이미 지수 무제약, 거래대금 20억→15억(도메인 B2 — 장중 돌파 추격 슬리피지라 kojiro 10억 회피) + max_scan 100→4000 + return_stage_counts 배선. **시총 100억**(사용자 결정 — kojiro 500억보다 낮게, 소형주 포함). **병목 정직 평가** — VCP 병목은 유니버스가 아니라 추세필터(97.9% 탈락) → 확대는 근본 미해결이나 후보 0→1~2로 **관찰 표본 처음 생성**. 진입 임계=정체성 상수 불변, 체결 확보 후 별도 사이클. **적대적 검증 결함 시정** = F-A(funnel step0/step1 union/trade 배선 — "컷 전" 라벨 collapse) + F1(ScanMonitor VCP 스테일 라벨 시정 + BFB union 노출) + F-D(BFB graceful) / #2(max_scan 4000>PARAM_RANGES cap 500 — pre-existing kojiro 동일·test_cycle212 잔존 의무라 미변경) / F2(daily-load "20억" 스테일 주석 — 런타임 10억 정합·scanner 무변경 보존). **DB strategy_config 동반 갱신 필수**(코드가 DB 에 덮임 실측: VCP/BFB 라이브 mcap 100억·trade 20/50억·scan 500) → VCP trade 10억·BFB trade 15억·둘 다 scan 4000 UPDATE 완료(mcap 100억 유지, 다음 부팅 반영). 8영역 diff 0, 회귀 백엔드 12 신규+의미 전환 3, 백엔드 4,774 PASS + 프론트 35 PASS + build |
| 2026-08-08 | 구독 우선순위·cap 제거 + kojiro 한도 지혈 + 성장 경로 로드맵 | 선결과제 ②④⑤ 종합. **조사에서 ④⑤ 원 진단이 반전**(19+16 에이전트 2회). **⑤ kojiro 일봉 고갈 = 반증** — daily-load 자격 임계(시총500억·거래10억)와 kojiro 스캔 임계가 **완전 동일**이라 이탈 424종목은 kojiro 유니버스에도 없는 임계 미달 종목 = 표본 유실 아님. 지수편입 348 전부 fresh. **현행 유지**. **④ cap = vestigial 반증** — momentum 급등 스캔이 enabled 무관 리스트를 채워 `BREAKOUT_LOW_CAP=25` 가 살아있는 breakout(BFB/VCP) 슬롯을 죽은 momentum 으로 전용시키는 **능동적 손해**. 시정 = (a) cap 제거(breakout 전체 pass-1 최우선) (b) `_collect_breakout_tickers` 순서 VB→LTV→BFB→VCP → **BFB→VCP→VB→LTV**(사용자 결정, BFB 60% 미구독=tail 편중 실측, BFB/VCP 는 폴링 없이 tick 으로만 매수평가라 구독=매수기회) (c) `[priority_drop]` 에 pool_sessions/pool_slots 병기(미구독 진단). **② kojiro 한도 1.2 위반** — `ratio 0.20 × maxp 6 = 1.2 > 1.0`, DB 런타임 값에만(코드 기본 0.20×5=1.0). C-DEFAULT(소스 리터럴)·C-CROSS(AI추천) 가드가 **운영자 수동 DB apply 사각**을 못 막았다. 지혈 = **B′ ratio 0.166**(×6=0.996, 사용자 결정 — 성장 경로상 position_ratio 는 계속 낮아질 값이라 궤적 첫걸음. 자문 권고 0.167 은 ×6=1.002 미세위반이라 0.166 정정, DB 적용 완료) + **런타임 가드 신설**(`portfolio_risk.check_budget_invariant` 순수함수 + boot_manager 배선, 부트 실행값 검증 WARNING, 수동 apply 사각 영구 차단, fail-open). **종목수 제한 vs 유닛 캡 도메인 자문**(사용자 원질문 "유닛 제한 있으니 종목수 제한 걷어낼 수 있나, 피라미딩 빨리?") — **성장 경로(현 117만→500만→1-2억)** 전제 재자문. 결론: 사용자 직관은 **이상적 터틀에서 옳으나** 우리 유닛은 (1주 양자화·hard_stop·혼재로) 깨진 벽돌이라 개수≠리스크. **개수 캡은 걷어내는 게 아니라 역할 진화** — 소액 중복(무해)→중형 load-bearing→대형 상관군 캡 병행, 제거는 로드맵 **마지막**(T4 2억, 옵션). 정량: 피라미딩 해상도 임계 net 500만(현 117만은 1주=노이즈), ②개수천장=1/ratio, ③Σ리스크캡 규모불변(항상 4.5유닛). VCP/BFB 는 피라미딩 부적합(변동성수축/measured-move)이라 개수 캡 load-bearing 영구·활성은 체결+백테스트 게이트. **지금=지혈+문서화+inert 봉인, 나머지 자본/체결 게이트(기제 착수 net 500만)**. FREEZE(N=1·0/4) 표본 보호로 구조 재설계 금지. `strategies/CLAUDE.md` 생애주기 표 + `_workspace/domain_consult/` 성장 경로 개정판. 성과 표시 정직화(합성 total_asset→te 실현손익 병기) 동반. 의미 전환 6(cap 25 행위), 신규 회귀 백엔드 13, scheduler 외 7영역 diff 0 |
| 2026-08-07 | 레짐 관찰 전용 정직화 (자문 payload + buffett 버그 + 프론트 배너) | 선결과제 ③. **착수 전 내 "매핑 깨짐" 진단이 다각도 조사(19에이전트)로 반증됨** — dkstock 은 `raw.cycle`(경기순환=expansion 확장기)과 `raw.regime`(투자레짐=defensive)을 **별개 필드**로 준다("경기 좋지만 밸류에이션 극단이라 방어 권고"). 스냅샷 regime='defensive'는 `raw.regime.regime` 정확 반영 = 매핑 정상. **진짜 문제 = 표시/행위 정반대**: 사이클 I 가 레짐 매수 게이트를 전면 제거(관찰 전용)했는데 `/current` 만 `buy_blocked=False` 정직화했고 **자문 계층 `to_advisor_dict` 만 레거시 `buy_blocked=True`(defensive→block_reason→True) 방출** → SYSTEM_PROMPT 거짓 등가("buy_blocked=True=모든 전략 매수 차단→매수 튜닝 무용")와 결합해 **매일 20:00 자문이 매수 파라미터 권고를 통째 스킵**(엔진은 100% 자유 투입 중인데 AI 엔 "전면 차단" 거짓). 사용자 결정 = **방향 A(관찰 전용 확정, 행위 무변경)**. 시정 = (1) `to_advisor_dict` buy_blocked→False(`/current` 정합, block_reason 은 방어 '권고' 관찰용 유지) (2) SYSTEM_PROMPT 재작성(레짐 미개입·매수 튜닝 유효·block_reason 은 보수적 권고 참고) (3) **buffett_ratio 파싱 버그 F1** — `from_macro_cycle` 이 `params.pbr_max`(PBR상한, 라이브 0=비활성)를 buffett 로 읽어 /current·자문·스냅샷 전 계층 null → `regime.buffett_ratio`(라이브 1.45=방어권고 핵심근거) 정정 (4) 프론트 `MarketRegimeCard` auto_regime_adjust=false 시 "관찰 전용—실제 매매 미반영(cash N% 수동)" 배너 + 경보 "(권고·관찰)" 표기 (5) `CLAUDE.md:798` stale 독트린("buy poll 레짐 매수가드 복제") 정정=유령 게이트 복원 차단. buy_blocked 프로퍼티/is_buy_allowed/스냅샷 감사기록 유지(자문 payload 에서만 False). 의미 전환 2(payload buy_blocked True→False), 신규 회귀 백엔드 10+프론트 2, **8영역 diff 0**(market_regime/recommendation_engine 은 8영역 아님), 백엔드 4,748 PASS + 프론트 build 통과. 잔여(후속): 스냅샷 buy_blocked 재의미화·raw.errors 미검사·확장기/buffett_level 표시 축 — 전부 관찰성 후순위 |
| 2026-08-07 | 어제 반영 검증 + market_op 닫힌 소켓 send 레이스 가드 | **어제 배포 3건 라이브 검증 완료**: (1) 프리장 청산 평가 보류 게이트 08:00:11 `[pre_market_exit_deferred] strategy=kojiro` 발화 + 08:00~09:00 청산 로그 0 (2) 프리장 매도 거부 APBK0918 08-06·08-07 **연속 0건**(30일 반복하던 것 소멸) (3) H-1 고점 **부팅 생존** — 컨테이너 18h(07:55 부팅 경유)인데 슈프리마 07:48 복구 로그 57,400→60,800(+26.1%) DB 영속, 리셋 없음. **검증 중 발견한 결함 시정**: 어제 "051905만 구독 실패" 진단이 **틀렸음** — traceback = `ConnectionClosedError: no close frame received or sent`, 051905 는 알파벳순 첫 종목일 뿐 실제는 11:24:57 재연결 8초새 2회 튐 순간 **HIGH 7종목 전부** 실패(일회성 버스트). 진입 가드 `not getattr(kis_ws,"_ws",None)` 가 `_ws` None 여부만 봐서, 재연결 레이스로 "존재하지만 닫힌"(state≠OPEN) 소켓이 통과→`send()`→ERROR+traceback 폭주. H0UNMKO0=VI/거래정지 채널(시세·손절 무관)·다음 5분 사이클 자동 복구라 심각도 낮음. 사용자 결정 = **realtime `_send_subscribe`(8영역 hot path, 시세·체결통보 공유) 미접촉, scheduler 훅만 수정**. 진입 가드 `state is State.OPEN` 추가(미개방 시 사이클 skip + `[market_op_subscribe_skip]` INFO) + HIGH/LOW 루프 `except ConnectionClosedError: break`(종목별 ERROR→WARNING 1행). scheduler duck-typing `_ws.state` (AST 가드). 회귀 11 + mock 적응 2(cycle214/import_regression 픽스처 `_ws`→`SimpleNamespace(state=OPEN)`), scheduler 외 **7영역 diff 0**, 백엔드 4,745 PASS |
| 2026-08-06 | NXT 프리장 매도 시정 — 평가 보류 게이트 + 매도 사전 지정가 변환 | 30일 APBK0918 매도 거부 전수(8건·고유 6케이스) 실측 = **momentum 익일매도 2 + donchian 멀티데이 손절 3 + LTV 당일 손절 1**, 전부 09:00 KRX 체결로 종결. 사용자 판정 "전일 상한가 종목도 NXT 프리장 시초가가 하한가로 형성되는 경우가 많다 — 프리장 매도는 의도와 다르다" → **당초 제안(매도 일괄 지정가 사전변환)은 의도를 거스를 뻔**: 지금까지 KIS 거부가 우연히 가드 역할(전부 09:00 보류)을 해 왔고, 일괄 변환하면 momentum 이 왜곡 프리장 가격에 체결된다. scheduler 는 Tier-1(07-21 자문)이 이미 08:00 매도를 안 냄 — 문제는 **on_tick 이 프리장 첫 틱(08:00:00)으로 청산을 평가**하는 경로. 시정 3부(사용자 결정: 멀티데이 손절도 09:00 보류 정식화) = **(1) risk.py 프리장 평가 보류 게이트**(의도적 8영역 수정): `_PRE_MARKET_EXIT_EVAL_STRATEGIES={LTV}` 화이트리스트 외 전략은 PRE_NXT 단독 구간 동안 청산 평가+`high_since_buy` 갱신 보류. **평가 보류이지 주문 보류가 아님**(주문만 보류하면 허깨비 틱 신호가 09:00 실매도로 전환). 판정 소스=`session_tracker.active`(이벤트 구동, wall-clock 아님 → 기존 on_tick 테스트 11파일 결정적 무영향). `tradable_boards` 게이팅 금지(매수 전용 doctrine 커플링 차단, AST 가드). fail-open. **(2) order_engine.execute_sell 프리장 시장가→`step_down(현재가,5)` 지정가 사전 변환**(매수 PR-F :323 대칭, 실효 대상 LTV — 07-30 실측 손절 08:27→09:00 지연 비용의 재발 차단. 현재가 미수신 시 무변환=시장가 거부→보류 안전망). **(3) balance.py 분류기 "상호 배타" 서술 정정** — 프리마켓 msg1 은 market_closed·disallowed **이중 매칭** 실재, execute_sell 의 closed-먼저 순서가 보류를 만드는 **의도된 계약**으로 명문화(순서 반전 금지 가드). 부수 규명 = 08-03 08:44 재시도는 트래커 TTL 결함 아님(직접 검증 08:00 등록→09:00 만료 정상) — 재시작 인메모리 소멸 추정(INFO retention 소멸로 부팅 마커 확인 불가). 회귀 23(게이트 13+변환 6+분류 3+α), 의도 수정 = risk.py+order_engine.py 2영역, **나머지 6영역 diff 0**, 백엔드 4,737 PASS |
| 2026-08-06 | P1·P1.5 VCP/BFB 청산 복구 + 진단 대시보드 | 트레일링 감사 잔여분. **전제 정정**: VCP·BFB 는 비활성이 아니라 운영 DB `enabled=True`·`weight=0.10` **무장 상태**이고, 체결 0건은 꺼져서가 아니라 진입 조건 미통과 탓(trade_history 에 두 전략 부재). **(P1)** `prepare()` 가 매번 `_candidates` 를 와이프하는데 **보유 종목은 돌파 후 셋업이 무너져 후보 자격을 잃는 게 정상** → 청산이 거기 단독 의존하면 **재시작이 아니라 매일 T+1 아침** 죽는다(kojiro 삼영무역 동일 클래스). 죽는 범위가 트레일링 하나가 아니었다 — VCP=§1.5 래치·**§2 base_low 손절**·§3 트레일링·§4 ema50 이탈(하드손절만 생존) / BFB=§1.5·**§2 flag_low 손절**·**§3 measured-move 익절 전체**·§4(하드손절+시간청산만 생존). 시정=`_position_setup` 영속맵 + `_effective_setup` 리졸버(live 우선→폴백, 미지 종목은 **빈 dict** 로 호출부 `.get()` 안전). **필드별 갱신 규약 분리** = 구조레벨(base_low/flag_low/pole_*)은 BUY 직전 stamp 후 불변·지표(atr14/ema50)는 boot 훅이 **이미 fetch 하는 일봉으로 매일 갱신**(ema50 박제 시 상승추세에서 뒤처져 이탈청산 지연 — 규칙문서의 미해결 TODO 동반 종결). BFB §3 은 직접 인덱싱이라 부분 재채움 시 KeyError 로 청산 전체 사망 → `.get()` + **키 결손 시 미발화**(과잉청산 금지). **(P1.5)** 문서의 'BFB 는 익일청산이라 복구 불필요' 가 **거짓**(익일청산·15:20 목록 비멤버 + `check_force_clear()==[]` → max_hold_days 실질 멀티데이) — 그 전제 위에서 복구가 통째로 빠져 있었다. `_rederive_entry_atr`(매수일 *이전* 봉만, 부족 시 미스탬프) + `recompute_high_since_buy`(base 헬퍼 위임, 복사 금지) 신설. **배선=boot_manager**(positions 복구 후 + scheduler 8영역 diff 0). ⚠️ `_SWING_POLL_STRATEGIES` 편입 금지(그 상수는 매수 폴루프·구독에도 쓰여 매수 행위가 바뀐다) — 가드 신설. 구현 중 **반쪽 발견**: `_entry_atr` 만 살리면 구조레벨은 재시작 시 여전히 소실 → `_detect_base`/`_detect_pole_and_flag` 로 **매수일 이전 봉 재검출**, 실패 시 미복구(fail-safe, 현행보다 나빠지지 않음). **(P3 진단 대시보드)** 실측이 원인을 갈랐다 — VCP=후보 **0**(추세필터 329→7 = 97.9% 탈락 후 pullback 전멸) / BFB=후보 18 중 **6(33%) 미구독**(`BREAKOUT_LOW_CAP=25` 를 4전략이 41슬롯에서 공유. 사이클 48 이 *배선*은 고쳤고 남은 건 *슬롯 캡*). `get_targets_status` 키 **추가만**(VB 호환 5키는 scheduler 8영역 소비라 제거 금지) → registry 덕타이핑 제네릭이라 **route 수정 0**. 신규 `BreakoutCandidateMonitor`(진입게이트/구독커버리지/후보그리드, VB·LTV 경로 byte 보존) + StrategyFunnel 병목·14일 추이(**미사용이던 `getRecentFunnel` 활용, 백엔드 0**). ⚠️ 병목 판정은 **절대 감소 수** — 감소'율'이면 막판 7→0(100%)이 329→7 을 이겨 진짜 병목을 가린다(에이전트 스펙 정정, 실측 검증). 의미 전환 4(BFB 복구 부재 계약 2 + ScanMonitor BFB/VCP 렌더 경로 2). 8영역 diff 0, 회귀 백엔드 64 + 프론트 33, **백엔드 4,714 PASS + 프론트 423 PASS + build 통과** |
| 2026-08-06 | H-1 트레일링 기준점 영속 | 트레일링스탑 감사(사용자 요청 "수익 보전 최소 장치")에서 확증한 최대 결함. `risk.on_tick:114` 이 `high_since_buy` 를 **메모리에서만** 올리고 DB 되쓰기 경로는 `update_high` 뿐인데 그 호출자가 donchian/VCP 두 전략의 복구 메서드뿐 → **kojiro 는 영속 경로 자체가 없음**. `boot_manager:151-159` 가 매 영업일 07:55 `_boot()` 에서 DB row 로 Position 을 재생성하므로 **2.5ATR 샹들리에 기준점이 매일 아침 매수가로 리셋** = 트레일링이 하드손절과 사실상 구분 불가. **라이브 실증**: positions 7행 전부 `high_since_buy == buy_price`(슈프리마 236200 메모리 61,300 vs DB 48,200). 복구 가능 고점 = 영원무역 92,400(+6.5%)·슈프리마 57,400(+19.1%)·아모레 26,550·CJ CGV 5,540·우리금융 34,300. **시정 3부** = (A) `_apply_high_since_buy_from_candles` 가 donchian/VCP 에 로그 접두사만 다른 **byte-identical 2벌**로 존재 → kojiro 3번째 복사본 대신 `StrategyBase` **단일 진실원 추출**(sector_naming 선례). ⚠️ `recompute_high_since_buy` 자체는 base 로 **올리지 않음** — BFB 가 상속해 `test_bfb_turtle_sizing::test_bfb_not_multiday_and_no_rederive_infra` 가 깨진다. (B) kojiro 는 `recompute_held_atr` 안에서 **이미 fetch 한 candles 재사용** → KIS 추가 호출 0 + **scheduler(8영역) diff 0**(VCP 전용 훅은 하드코딩 `_vcp` 라 거기 끼우면 8영역 위반). 배치는 ATR/stage 블록 **앞** = 워밍업 봉 부족 `continue` 에도 복구 생존(donchian E3 동형). (C) `_candle_trade_date`/`_candle_high` 가 KIS 원본 키(`stck_bsop_date`/`stck_hgpr`)와 정규화 컬럼(`bas_dd` date 객체/`high_price` Decimal) **양쪽 수용** — kojiro 는 `get_recent_daily_normalized` 를 쓰는데 이 어댑터는 raw JSONB 없는 row 를 **row 자체로** 돌려줘 한 형태만 읽으면 그 종목이 조용히 전부 skip 된다. **과대복구 구조적 차단** = 경계 `buy_date < 영업일 < today`(매수 전 구간 오염·미확정 봉 배제) + 올리기 전용 ⇒ 남는 오차는 과소복구 한 방향뿐이고 그 방향은 청산을 늦춘다. **배포 전 실측 시뮬레이션**: 복구 후 샹들리에가 현재가보다 6.7~12.8% 아래 = **즉시 청산 위험 0**, 슈프리마는 실효 보호선이 −8%(44,344)→**+6.2%(51,203)** 로 전환. 잔여 갭 = 매수 당일 고가·장중 재시작분(영속 불가, on_tick DB 쓰기 금지). 동반 문서 정정 = "BFB 는 익일 청산" **거짓** 판명(익일청산·15:20 목록 모두 비멤버·`check_force_clear()==[]` → 실질 5영업일 보유, 복구 배선 0인 유일 보유형 전략). **적대적 검증(읽기전용 32 에이전트·6렌즈)** 확정 결함 4건 전부 LOW — (F1 시정) `_candle_high` 의 `except (TypeError,ValueError)` 가 **OverflowError 미포착** → `int(float("inf"))` 이 새면 봉 1행이 루프를 통째 중단시켜 남은 보유 종목 복구까지 유실(추출 전 대비 유일한 fail-closed 퇴행) → `except Exception` 으로 계약 복원. (F2 시정, **사용자 결정 "샹들리에 포함해서 정확하게"**) `_position_stop_price` 가 샹들리에 미참조 → 고점 복구로 샹들리에가 매수가를 넘은 포지션(실제 리스크 0)도 Σ캡이 만액 계상 = 매수 게이트가 근거 없이 잠김. **H-1 회귀는 아님**(출력 동일, 이전엔 매일 리셋돼 `max(pct,atr)` 가 실제로 정확했음) — H-1 이 비로소 간극을 의미 있게 만든 것. `max(pct, atr, high−trail_atr×ATR)` 로 청산 세 가격선 전부와 정합. 실측 Σ 27,162→**20,797**(캡 31,055 대비 87.5%→67.0%). 음수 기여는 기존 `stop<buy` 조건이 차단(확정 이익이 타 종목 실노출을 상쇄해 캡이 무력화되는 것 방지)·`_stop_floor` 읽기 전용 유지·`high==buy` 구간은 샹들리에가 항상 2ATR 선보다 낮아 **기존 테스트 회귀 0**. ⚠️ 샹들리에는 tighten-only 가 아니라(ATR 팽창 시 하락) "최악 보장"이 아닌 **평가 시점 실제 손절선** — 매수 시도마다 재평가하므로 정합. (F3 범위 외) 부분 체결 시 `buy_price` 만 갱신돼 `high<buy` 역전 — order_engine=8영역이라 별도 사이클. (F4 시정) 로그 접두사가 `strategy_id` 로 바뀌어 운영자 한글 grep 이력 단절 → `_HIGH_RECOVER_LABEL` 로 추출 전 리터럴 byte 복원. 8영역 diff 0, 회귀 34, 백엔드 4,650 PASS |
| 2026-08-04 | 포지션 표 섹터 컬럼 + 섹터명 단일 진실원 | 사용자 요청 "포지션현황에 종목과 거래시장 사이 섹터 추가". 착수 중 **섹터 해석 로직이 portfolio 라우트·일일리포트에 이미 2중 중복**임을 발견 — 잔고 라우트에 그대로 넣으면 3번째 복사본(세 곳 드리프트 시 대시보드·리포트·리스크 스냅샷 섹터명 불일치)이라 신규 `sector_naming.py` **단일 진실원 추출** 동반. 우선순위(`bstp_kor_isnm` → `_kojiro_sector_key(master_raw)` → `미분류-{ticker}`)·fail-open 은 사이클 H Phase 2a/I 후속 계약 **그대로 보존**(행위 0). `basics_raw` 주입 파라미터로 **잔고 라우트가 J1 이래 이미 조회 중인 basics 재사용 → 추가 DB 호출 0**. 3 소비처 전부 위임 + 중복 재발 가드(docstring 허용·**코드만** 검사). 프론트 = `BalanceTable` 헤더 `종목명→섹터→거래시장` + `sector-{ticker}` testid + 부재 시 `-` + `colSpan` 11/10 동반 갱신. 의미 전환 4(portfolio 라우트 테스트 monkeypatch seam → sector_naming 이동, 행위 불변). 회귀 백엔드 12 + 프론트 5, 백엔드 4,616 PASS + 프론트 390 PASS + tsc clean, 8영역 diff 0 |
| 2026-08-04 | kojiro 비중 집중 + Σ 오픈리스크 캡 | **터틀 첫 발화 실측**(09:05 아모레퍼시픽 002790, atr_ratio 4.92%>임계 2.50%) = 터틀 1주 vs position_ratio 2주 → **"터틀 수량 ≤ 비중 수량" 라이브 검증**. 단 실현 유닛 리스크가 **목표의 58%**(절삭 1.40→1주 −28% + `hard_stop_pct −8%` 가 2ATR 9.83% 캡 −19%) — 소액 계좌에서 1주 양자화가 정규화 효과를 상회. **비중 집중**(사용자 결정, **0.35 FREEZE 해제** — 재튜닝 트리거 청산≥20 미충족 N=1 상태): kojiro 0.30→**0.60**, VB/LTV 0.03→0.01, donchian 0.24→0.18, BFB·VCP 0.20→0.10, momentum 0 유지(비활성에 0.01 부여=재기동이라 제외). 예산 345K→690K, 해상도 1→2~3주 개선하나 **q_min≥5 여전히 미달**(필요 123만) = 집중은 완화지 해결 아님. ⚠️ 적용 직전 실측에서 **LTV 가 08:25 셀바스AI 보유** 발견 — weight 0 비활성화 안이었다면 `registry.enabled()` 이탈로 **손절 평가 정지**했을 것(극소 0.01 유지가 회피). **Σ 오픈리스크 캡 신설**(사용자 제기 "터틀이면 유닛 단위 제한이 맞지 않나") — 방향 정확하나 **피라미딩 부재 시 `max_units_total`≡`max_positions` 완전 동치**라 개명은 행위 0. 터틀 유닛 캡의 실제 통제 대상은 **Σ리스크**, 개수는 프록시. 이론상 atr_ratio≤4% 는 유닛 리스크 정확히 1.00% 상수·4~6%는 backstop 이 잘라 감소(안전)이나, 실측 6포지션=**3.2유닛**(예산 3.2%)·편차 8.3배(⚠️ 자체 정정: 8.3배는 터틀 아닌 **구 position_ratio 포지션 5개** 탓, 오귀인 교정). 신설 `max_open_risk_pct=4.5` + `_open_risk_won()`(실효손절선=청산과 동일 산식, `_stop_floor` tighten 반영) + `_is_open_risk_capped()` 게이트(`is_max_positions` 직후 **병존**). 4.5<6.0(=6×1.0%) 이라야 캡이 실제로 일함. **개수 캡 대체 금지**(리스크 캡만 두면 저ATR 종목 수 폭증 — 터틀도 유닛+시장군 병행) ⇒ 개수+명목+리스크 **삼중**. fail-open 3중, 청산 절대 미차단(AST). dead param `max_units_*` 는 미강제 명시(피라미딩 검토 예정 존속). 회귀 17, 8영역 diff 0, 백엔드 4,590 PASS |
| 2026-08-04 | 전일 로그 점검 — VI 화이트리스트 + 리포트 절단 감지 | 08-03 로그 점검에서 발견한 결함 2건. **(A) VI 화이트리스트 누락** — `market_operation.inquire_vi_status_today` 가 `kis_get_quote` 경유인데 `_QUOTE_ALLOWED_PATHS` 에 없어 사이클 149 도입 이래 **매 부팅/재시작 QuotePoolPathError** → VI 시드 100% 실패 + ERROR/traceback(08-03 ERROR 15중 8). 사이클 109 market-cap / C1 finance 와 **동일 클래스 세 번째 누락**이고 코드 주석이 "화이트리스트 추가 의무"라 자백해둔 채 미이행. KIS 정본="VI 현황" 업종/기타=시세성·`FID_*` 전용 → 정책 부합. 실사용=`is_ticker_stale_excluded`(VI 종목 stale 제외 → 강제 재구독 억제 = LMS chain 위험 완화), **장중 재배포 시점**에 실효(주석의 "07:50 부팅=영향 0"은 절반만 사실). **(C) 일일 리포트가 하루가 아니라 아침 2시간만 분석** — `_fetch_logs_in_range` 가 `ORDER BY ts ASC LIMIT 30000` 이라 08-03 총 97,353건(3.2배 초과) 중 **07:45~09:47** 만 보고 리포트 산출. 11:20 사이클 I 배포·20:10 정산·21:03 까지 전부 시야 밖 → AI 가 07:48 매크로 장애를 최상위 high 로, WARNING 을 27,507(실제 89,427)로 오집계. **조용함(잘림 신호 0) + 이른시각 편향(ASC)** 이 겹쳤고 평시 18,000건엔 미발동, **폭주한 날=리포트가 가장 필요한 날**에만 발동. 시정 3종 = `_count_logs_by_level`(GROUP BY 진짜 총계 → `level_counts_actual`) + `_fetch_high_severity_logs`(ERROR/CRITICAL 별도 전량, `_merge_high_severity` 중복제거+ASC 유지) + `_aggregate_logs(fetch_limit=)` 절단 플래그·커버구간. ⚠️ 커버구간/절단판정은 **ERROR 병합분 제외 레벨 기준** — 안 그러면 전량 병합된 18:06 ERROR 때문에 "오후까지 봤다"는 **역-오인** 발생(실증에서 자체 발견·정정). `[log_report_truncated]` WARNING + SYSTEM_PROMPT 가 AI 에 "총계는 level_counts_actual 인용, 분석구간 명시" 지시. **참고: 08-03 WARNING 89,427건(99.8%가 `[buy_block_warn]`)은 사이클 I 가 11:20 배포로 이미 종결** — 12시부터 0, 현 코드 0건. 회귀 16(VI 3 + 절단 13), 8영역 diff 0, 백엔드 4,573 PASS |
| 2026-08-03 | 리스크 유닛화 + 전략 예산 이중제한 | 사용자 요구 "1회 투자금액은 ATR 기반 유닛, 전략 투자한도는 전략별 포지션으로 이중제한". **결정적 수식** = `수량 = 예산×risk_pct ÷ (진입가−손절가)` → 손절이 고정%면 명목이 종목 무관 상수라 **비율 사이징이 이미 리스크 균등**, ATR 유닛은 **손절도 ATR일 때만** 의미 (사이징만 전환 시 정규화 붕괴 = 함정#1). **Part A(전 7전략, 8영역 diff 0)** = 신규 `StrategyBase._apply_budget_limit` 관문 — 주 분기가 `int(예산×ratio)//price` 를 **잔여 검증 없이 반환**하던 결함(D1) 시정. `잔여 = total_investment − _calc_used_funds()`, `qty<=0 → _fallback_one_share` 위임(분기 순서=계약), `qty>0 → min(qty, 잔여//price)` **부분 매수 허용**. 원자성 근거 = `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(**A-ATOMIC AST 가 8영역 미접촉으로 8영역 보호**). 동반 결함 시정 = kojiro `else unit_qty` fail-open 반전(D2) + `compute_unit_qty_guarded` 의 `remaining>0`/`pr_qty>0` 조건부 클램프(D3, 고가주 notional 상한 미적용) → strict narrowing. **Part B** = kojiro guarded 전환(unguarded 는 저변동 종목 단일종목 예산 43% 집중 허용) + VCP/BFB 터틀+하드손절 ATR화 **다크런치**(기본 position_ratio = byte-identical). 게이트는 `sizing_mode` 아닌 **`_entry_atr` 스탬프 존재**(DB 토글이 기보유 손절 규약을 바꾸는 것 금지). VCP 는 수축 셋업이라 2ATR 이 −3%로 과도 조임 → **`turtle_min_stop_pct` 3단 밴드**(`[backstop, min_stop]`) 신설이 유일 방어선, 활성화는 백테스트 게이트. **구조적 안전판** = guarded 의 notional 상한이 `position_ratio×예산` 이라 **터틀 수량 ≤ 비중 수량** 항상 성립 = 전환은 순수 축소. **Part C** = `max_positions` PARAM_RANGES/INT_PARAMS 영구 제외(리스크 정체성 상수) + `ratio×maxp≤1.0` 교차검증 + `[budget_clamp]` DailyEmitCap. **라이브 실측** = 계좌 122.5% 초과 청약(kojiro 0.20×10 / LTV 0.50×4 = 각 200%) → DB 즉시 조정(kojiro maxp 6, LTV ratio 0.2)으로 94.9% 해소. 8영역 diff 0, 백엔드 4,557 PASS |
| 2026-08-03 | 매매손익 실현손익 요약 바 + kojiro 필터 | 매매손익(TradePnLGrid) 관찰성 UI 2건(사용자 요청). (1) **실현손익 요약 바** 신설 — `/api/history/pnl` 응답 `data.summary`(슬라이스 전 `status=='closed'` 페어 전체 집계: `realized_total_krw`/`realized_rate_pct`(가중=합계/Σ매수원금×100)/`win_count`·`loss_count`·`even_count`/`win_rate_pct`(승/(승+패))/`closed_count`, **open 미실현 제외**·Decimal 안전·전략 필터 반영) + 프론트 요약 바(실현 합계·손익율·승/패/보합·승률, 이익 red/손실 blue `pnlClass` 재사용). (2) 전략 필터 드롭다운 kojiro(고지로 대순환) 추가(6→7전략). 기존 pairs/page/total 계약 불변, **read-only·매매 8영역 무관**. 회귀 = 백엔드 8(summary 값/필터/open제외/빈결과 0/계약불변) + 프론트 4(요약 렌더/부호색/kojiro option/필터 재조회). 백엔드 routes 111 PASS + 프론트 385 PASS + tsc clean + api-mocks AST 가드 PASS |
| 2026-08-03 | 사이클 J kojiro 섹터 캡 전일보유 집계 | kojiro 섹터/테마 동시보유 캡(`max_positions_per_sector=2`)이 **전일 보유를 동일섹터 카운트에 미집계**하던 잠복 결함(라이브 실증=5/5 만보유·held 5종목 전부 `_candidates` 부재→`same=0`, 후보 6중 4가 동일 `업종-0027` 화장품 대순환). 근본원인=held 가 ATR밴드(<1%)/유니버스 컷 이탈로 `_candidates` **완전 부재**(+prepare `_candidates={}` 와이프+refill sector 미저장). domain-consult 확정=캡 의도는 "포트폴리오 누적 섹터 노출 상한(전일 보유 포함)"(커밋 37c6ed9 목표 "5종목 한 섹터 집중→테마붕괴 동시 하한가 락")이라 현행 "당일 신선만 세기"는 정책 아닌 **버그**. **안 A 채택**=신규 `_position_sectors: dict` 영속 맵(`_candidates` 와이프 독립·포지션 수명 생존), stamp 3지점(`recompute_held_atr` 전일 held 정본 + `check_buy_signal` BUY 반환 직전 당일매수 walrus + `on_position_closed` pop) + 카운트 폴백(`_candidates.sector` **or** `_position_sectors`). cap=2·진입4조건·청산·소스(`_kojiro_sector_key` KRX basket)·fail-open 전부 불변=리스크 축소 정정이라 kojiro FREEZE·N=1 관찰창 무관. **`_reset_daily_state` override 추가 금지**(멀티데이 held 섹터 밤샘 소멸)=AST 봉인. 안B(refill sector만)=밴드/유니버스 이탈 held 못고쳐 기각·안C(bstp_kor_isnm 캡키)=과잉클러스터 시맨틱 변질 기각. kojiro.py 단독(+15/-3), 안전 8영역 diff 0, 회귀 11, 백엔드 4,364 PASS |

> 사이클 200 이하 및 초기 하네스 구성 전체 이력(verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)

### 테스트 실행

```bash
pip install -r requirements-dev.txt # 1회
python -m pytest -q # 백엔드 전체
cd frontend && npm install && npm test # 프론트엔드 전체
cd.. && npx playwright install && npx playwright test --config=e2e/playwright.config.ts # E2E

# 영향 테스트만 (PR 빠른 피드백)
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
pytest $(python tools/test_impact/affected.py origin/main --target=backend)
```

## 빌드 & 실행

```bash
# Docker (권장)
docker compose up --build # 개발: 프론트 :3000, 백엔드 :8002
docker compose -f docker-compose.prod.yml up --build -d # 프로덕션: Nginx :80

# 로컬
pip install -r requirements.txt && uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
cd frontend && npm install && npm run dev
```

## 환경 변수
`.env` 필수 (`.env.example` 참고).
- `KIS_ENV`: `vts`(모의) | `real`(실전)
- `KIS_APP_KEY_REAL/VTS`, `KIS_APP_SECRET_REAL/VTS`, `KIS_ACCOUNT_NO_REAL/VTS`
- `KIS_HTS_ID`: 실전 체결통보(H0STCNI0) 구독 키
- `DATABASE_URL`: AWS RDS PostgreSQL asyncpg DSN (`?sslmode=require`). **현재 DB 정본** — 전 db 모듈이 `src/db/pg.py` 풀로 사용
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용** (settings/.env 에 잔존하나 어느 db 모듈도 참조 안 함, `src/db/supabase.py` 롤백용 병존)
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `DKSTOCK_REGIME_ENABLED` (기본 false): dkstock.cloud 매크로 레짐 수신 + cash_usage_ratio 자동 조정 활성화 (매수 가드는 사이클 I 제거 — 레짐은 관찰 전용)
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 6 전략 × 2 kind = 12 job fire-and-forget

## 다중 전략 (요약)

7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`).

상세 매수/청산/tradable_boards/exchange 는 **`src/engine/strategies/CLAUDE.md`** 참조.

### 새 전략 추가
1. `src/engine/strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `src/engine/scheduler.py` `__init__` 에서 `registry.register()`
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. `strategies/CLAUDE.md` 표 + `_workspace/00_leader_trading_rules.md` 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- `position_ratio` 는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio = 종목당 매수금액)
- **전략별 투자한도 (2026-08-03 이중 → 2026-08-04 kojiro 삼중)** — ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment` + ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 터틀의 유닛 캡이 통제하려던 값은 ③이고 유닛 **개수는 프록시**일 뿐 — 수량 절삭·`hard_stop_pct` 캡·사이징 혼재로 프록시가 헐거워진다(08-04 실측 6포지션=3.2유닛). **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). ②는 ②는 `StrategyBase._apply_budget_limit` 공통 관문이 7 전략 `calc_buy_quantity` 의 모든 return 을 통과시켜 강제하며, 잔여가 부족하면 **부분 매수**(잔여 < 1주 → 0). 불변식 **`position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT)가, AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다: 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 ATR 로 바꾸면 정규화가 깨진다(함정 #1). 현재 배선 = donchian(라이브) · kojiro · VCP/BFB(다크런치, 하드손절 ATR화 동반). momentum/VB/LTV 는 제외(ATR 부재 / 당일 청산 / 상한가 2모드 재설계 선행). `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 순수 축소 방향
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`)

### 외부 통합 (백테스트 + 매크로 레짐)
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 6 전략 × 2 kind = 12 job fire-and-forget → `parameter_recommendations.backtest_summary` JSONB
- 매크로 레짐 (`dkstock.cloud`) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정 (`auto_regime_adjust`, `clamp((100-cash_min)/100)`). **매수 가드는 사이클 I(2026-08-03) 제거** — 레짐은 매수를 차단/축소하지 않는 관찰 지표(`buy_block_mode` 는 표시 전용 잔존, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). ETF 레짐(E-1)·포트폴리오 리스크(사이클 H) 관찰 활성
- 활성화 토글: `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` / `etf_regime_enabled` (Settings UI 즉시 토글). 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 레짐 관찰 비활성
- 운영 가이드: [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:

- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — 무언가를 "미사용/dead/낭비"라고 단정하기 **전에 소비처(consumers)를 전수 확인**하고, 비활성화 **후에는 그 소비처가 여전히 정상 동작하는지 라이브 실측**으로 검증한다. **비활성화는 "제거"가 아니라 "경로 변경"일 수 있다** — 주 경로를 끄면 폴백 경로가 조용히 degrade될 수 있으므로, 배포 후 반드시 실측 점검한다(설정 토글은 CI/Deploy 를 안 타므로 자동 검증도 없다). 실측 없는 비활성화 금지. ⚠️ **재발 방지 사례 (2026-08-08 KRX OpenAPI)**: `krx_open_api_enabled` 를 "무효 키·낭비"로 오판해 비활성화 → 소비처 `scanner._full_universe_load_krx_primary`(20:00/07:48 전체 유니버스 적재 주 소스)가 KIS market-cap 폴백으로 밀려 **full_universe_load 가 3,577→60종목으로 degrade**(D+1 실측 발견). 원인 = (a) 소비처 미확인(주 소스인데 "미사용" 오판) + (b) 비활성화 후 점검 절차 부재. 키는 실제 유효(40자)했고 재활성화로 복원. **끄기 전에 `grep` 으로 소비처를 찾고, 끈 뒤엔 그 소비처의 산출물(예: 적재 종목수)을 라이브로 확인하라.**
- **체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑** (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum" 으로 잘못 INSERT됨
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today 가 다음 날까지 잔류
- **익일 청산** 은 scheduler 에서 시가 수신 후 30s 안정화 처리 — `_pending_next_day_clear` 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지. on_tick 즉시 청산 금지
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비=손절 마비이므로 반드시 해제) + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s 주기, 1~5회 즉시 강제 재등록 + 6회 초과 시 10분 cooldown 기반 시간 기반 force_retry + 시간당 6회 cap, 사이클 102 임계 상향) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단)
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약**이다. 관문 안에서 `await`/DB/HTTP **절대 금지** — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지. DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다. position_ratio 매수는 미스탬프라 기존 % 손절 경로를 byte 동일하게 탄다. 스탬프 값은 반드시 sizing 에 쓴 ATR 과 동일(커플링 불변식)
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱(전일 상한가 종목 시초가 하한가 형성 등)의 허깨비 손절·트레일링 고점 오염을 차단하고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도로 전환). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정(AST 가드) — 매수 목적 보드 변경이 청산 규약을 바꾸는 커플링 차단. 매도 시장가는 `execute_sell` 이 프리장 단독 구간에서 `step_down(현재가,5)` 지정가로 사전 변환(매수 PR-F 대칭, 실효 대상 LTV). `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수)
- **donchian_swing `_swing_rest_poll_loop`** 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 손절 평가 보강
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트 `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시. `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
- 매매 파라미터 (`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 또는 `kis_get_quote()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID 는 `settings.get_tr_id()` 사용 — 하드코딩 금지
- DB 접근은 `src/db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유. JSONB=raw dict 바인딩(codec) / TIMESTAMPTZ 쓰기=`datetime.fromisoformat(now_kst_iso())`·읽기=`to_char(...,'+09:00')` / DATE=`_kst.to_date()` 강제 (상세 `src/db/CLAUDE.md`)

## DB 스키마 (AWS RDS PostgreSQL)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`. (마이그레이션 디렉토리명은 supabase/ 유지 — 스키마 SQL 정본, RDS 에 순차 적용)

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, cash_usage_ratio, buy_block_mode + 4 임계값, dkstock_regime_enabled, kis_mcp_enabled 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE). `recommended_weight`/`code_review_notes`/`applied_weight`/`weight_reasoning`/`backtest_summary` JSONB |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + **사이클 129 `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` 신규** (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. **사이클 168 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED** (migration 039 — raw.hts_avls/acml_tr_pbmn 가 jsonb *문자열* 로 저장되어 UI `list_paged_by_filter` jsonb numeric gte 가 0건 silent 결함 → 생성 컬럼 numeric 비교 + 인덱스로 시정. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL. raw 읽기만 = 사이클 81 G-AST1 영속) |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (백필 시 T-100일, 이후 D-1 영업일 증분). **사이클 172 — VCP universe (KOSPI200∪KOSDAQ150) backfill** (분할 fetch) + retention `DAILY_RETENTION_DAYS=230`. **사이클 196 (2026-07-07) — VCP backfill target 220→120 수렴** (retention 230cal=154영업일 실측 < 220 → 무한 재backfill churn → target 120 하향 + `fetch_daily_candles_backfill` 윈도우 클램프, VCP prepare 실사용 100일 << 154 보유 무영향). donchian (20일 신고가) / VCP (베이스+Pullback, prepare 100일 cap) / VB (ATR) 전략 활용 |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041, 사이클 C1). PK `(ticker, stac_yymm, div_cls)` (div_cls 0=년/1=분기) + 18 NUMERIC 컬럼(손익 5/대차 7/수익성 2/안정성 2/기타 2) + raw JSONB + refreshed_at. 마법공식(EV/EBITDA·ROC) + F-Score-7 원천 데이터. 주1회 16:40 적재. 매매 hot path 무관 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클) |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷. `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 수동 trigger `POST /api/strategy-funnel/snapshot` (현재 최종 단계 `step_no=99` 만, 자동 hook 은 후속 사이클) |

> **`trade_history` 부분 UNIQUE 인덱스 (migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.

> **`stock_master` / `stock_master_daily` UI 동기화 의무**: stock_master 컬럼 / raw JSONB 키 / stock_master_daily 컬럼 추가 시 UI 동기화 의무 영속. 전략에서 종목마스터 데이터 참고 시점 영역부터 신규 수집 데이터는 UI 노출 의무. 절차 = (1) `frontend/src/types/stock-master.ts` interface 갱신 (2) `frontend/src/api/stock-master.ts` 호출 영역 갱신 (3) `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키 추가 (4) `GET /api/stock-master/stats` 응답에 진단 카운트 추가 + 카드 1개 추가 (5) `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 갱신 (6) 회귀 가드 추가. 상세는 `frontend/CLAUDE.md` 참조.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분. deploy.yml 은 push 후 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용 (`SUPABASE_DB_URL` secret — **이름은 유지하되 값이 RDS DSN**, graceful skip)
- CI (`.github/workflows/ci.yml`): `postgres:15` service 컨테이너 + `DATABASE_URL_TEST` 로 통합 테스트 실행 (`tests/integration/pg_harness.py` 가 migration 001~041 적용)
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL` (값=RDS DSN)
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- 운영 가이드: KRX 메인 시간 (09:00~15:30) 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능. NXT 애프터 (15:30~) 또는 익일 07:50 _boot 전 push 권장

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 20:10 일일 분석 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 6 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `dkstock_client.py` 매크로 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
