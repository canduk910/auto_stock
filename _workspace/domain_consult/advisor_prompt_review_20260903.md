# AI 자문 프롬프트 개선 검토 — **최종본** (적대적 비판 29건 반영)

- 작성: team-leader (2026-09-03) · 개정: 비판 2렌즈(엔지니어링·트레이딩) 29 지적 대조 후 최종 판정
- 성격: **읽기 전용 검토**. 소스·테스트·DB 무변경. 설계 제안이며 구현 승인 전 단계다.
- 구성: **§F 최종본**(정본 — 이것이 판정이다) → **§원안**(1차 검토 전문, 증거 기반은 유지하되 판정은 §F 가 대체) → **§부록 비판 반영표**(29건 처분)

> ⚠️ **원안의 §0 수치 2개는 재현 불가로 판정되어 폐기했다.** "30일 138행 중 135행(97.8%) 봉인 결정 충돌" 과 "4개월 조임:완화 1,370:166(89.2%)" 은 산출식이 문서에 없었고 내 재실측과 모집단이 달랐다. 대체 수치와 재현 스크립트는 **§F.8 실측 부록**에 있다. 원안의 나머지 file:line 인용과 격차 진단은 두 비판 렌즈의 독립 대조를 **전부 통과**했다.

---

## F.0 최종 결론

**진단은 유지, 처방은 개정한다.** 자문 프롬프트가 시스템을 담고 있지 않다는 원안 §0 의 판정은 두 렌즈의 독립 대조를 통과했고, 3겹 처방(ⓐ 단일 정본 · ⓑ 프롬프트를 정본에서 생성 · ⓒ 검증기·라우트가 같은 정본을 강제)의 **방향도 유지**한다. 바뀐 것은 **어떻게 실행하느냐**다 — 원안의 사이클 1 설계는 그대로 실행하면 (i) 기존 테스트 40여 곳을 불필요하게 깨고 (ii) 존재하지 않는 데이터를 참조하는 프롬프트를 배포하며 (iii) 가드 하나가 태어날 때부터 공허하고 (iv) 정작 결함을 만든 제3의 쓰기 경로를 손대지 않는다.

**가장 중요한 개정 하나를 먼저 적는다.** 원안은 "라이브 값이 `PARAM_RANGES` 밖이면 그 키의 권고를 폐기" 하는 가드(`[advisor_range_pull_reject]`)를 핵심으로 삼았다. 이 판정축은 **틀렸다**. 그러면 클램프 산출물뿐 아니라 *안전 방향의 교정 권고까지* 함께 삼킨다. 운영자가 Settings 에서 오타로 범위 밖 값을 넣어도(그 경로엔 검증도 로그도 없다) 자문은 그 키를 영구히 지적할 수 없게 된다 — **미기록 오설정을 의도적 결정과 똑같이 보호**하는 셈이다. 올바른 축은 **`DECISION_LOG` 멤버십**이다: 사람이 사유와 함께 등재한 값만 방패를 받고, 등재 없는 범위 밖 값은 **통과시키되 `[advisor_live_out_of_range]` 로 시끄럽게 표시**한다. 이 한 줄의 축 교체가 결정 #1 의 답(봉인 → 현행 유지)과 결정 #6(신규, 제3 쓰기 경로 감사)까지 연쇄로 바꾼다.

**오늘 밤은 코드가 필요 없다.** 09-02 pending 7건은 이미 전부 `rejected` 로 처분됐고(실측), `auto_apply_enabled` 키는 `system_config` 에 부재하며(실측 — auto/advisor 관련 키는 `auto_regime_adjust`·`auto_start` 둘뿐), 적용 이력은 06-08 이후 0건이다. 위험 경로는 운영자 클릭 하나뿐이다. 반면 워킹트리엔 다른 워크플로(cycle242)의 미커밋 매매 로직 변경 5파일이 올라와 있어 야간 급행 push 는 검증 미완 코드를 동반 출하한다. **오늘 밤 조치 = "20:00 자문을 적용하지 말 것" 한 줄**(§F.7).

---

## F.1 원안에서 바뀐 것 — 10건

| # | 원안 | 최종 | 사유 (검증된 근거) |
|---|---|---|---|
| **1** | `_validate_recommendations` 반환 5-tuple → **6-tuple**, "기본값을 둬서 회귀 파급 0" | **시그니처 무변경.** 거부 원장은 keyword-only out-parameter `sink: dict \| None = None` 로 채운다 | "회귀 파급 0" 이 거짓. 실측 = `= _validate_recommendations(` 호출 **33곳 전부 5-tuple 언팩** + `assert len(result) == 5` **3건**(`test_recommendation_weight_reasoning.py:27` · `test_recommendation_weights.py:127,158`). 게다가 가장 값어치 있는 가드(범위-끌어당김)는 시그니처 변경이 **불필요**하다 — `current_params` 도 `PARAM_RANGES[key]` 도 이미 `:196-216` 루프 스코프 안이다 |
| **2** | 사이클 1 = 정본+검증기+**프롬프트 v2** | **순서 반전.** A=정본·검증기·감사 → B=payload·metrics·계측 → C=프롬프트 v2 → D=출력스키마·프론트 | 프롬프트 v2 초안이 참조하는 `funnel`·`past_recommendations`·`data_quality_notes`·`RR` 이 **전부 원안 사이클 2 항목**(댕글링 참조 4종). 단독 배포하면 모델이 없는 필드를 지어낼 유인이 생기고, §0 의 탈편향 지시는 RR 데이터 없이 "부호만 뒤집으라"는 지시가 된다 |
| **3** | `[advisor_range_pull_reject]` 판정축 = **범위 멤버십**("추천값은 범위 내인데 current 가 범위 밖") | 판정축 = **`DECISION_LOG` 멤버십**. 미등재 범위 밖 값은 **통과 + `[advisor_live_out_of_range]` WARNING** | 범위 축은 과광범 — 라이브 `stop_loss_rate` 가 어떤 경로로 −20(범위 (−15,0) 밖)이 되면 자문의 −8 **교정** 권고까지 폐기되고 드리프트가 자문 채널에서 영구 불가시화된다. 검증기는 reasoning 을 읽지 않으므로 프롬프트 §3 의 "관측 증거가 있으면 권고 가능" 단서를 강제할 수단이 없다(코드는 키 단위 무조건 drop) |
| **4** | 결정 #1 `max_scan_stocks` → **(b) 봉인 편입** | **(c) 현행 유지 + DECISION_LOG 등재 + 축-교체된 가드** | (b)는 잔존의무 가드 4건(`test_cycle212_entry_threshold_param_range.py:83,96` · `test_cycle223_donchian_exit_param_ranges.py:124,137`)과 `INT_PARAMS ⊆ PARAM_RANGES` 불변식 2건(`:108`·`:145`)을 깨고 `INT_PARAMS` 동반 제거를 요구하는데 원안 롤아웃에 그 언급이 없다. 게다가 `PARAM_RANGES` 는 **전역**이라 (b)는 라이브 값이 정상 범위 안인 donchian(400)·VB·LTV(100)의 튜닝 축까지 함께 봉인한다. 그리고 자기모순 — 봉인하면 그 키는 `PARAM_RANGES` 를 떠나므로 `[advisor_range_pull_reject]` 가 구조적으로 미발화가 되어 원안 §4 관측 판독 #1("3전략에서 매일 발화해야 정상")이 자가 붕괴한다 |
| **5** | 표본 게이트 = `recommended_weight` **None 강등** + `weight_reasoning` 보존, `metrics: dict \| None = None`(fail-open) | **`withheld_weight` + `withheld_reason` 신설**(기존 계약 무접촉) · 소스 `closed_round_trips` 를 **사이클 A 에서** `compute_metrics` 에 추가 · **fail-closed** | (i) "weight null ⇒ weight_reasoning 무조건 null" 은 `recommendation_engine.py:275-276` 의 명시 계약이고 전용 테스트가 봉인한다(`test_recommendation_weight_reasoning.py:88-101,220` · `test_recommendation_weights.py:146`) — 원안 형태는 그 짝 계약의 정확한 위반 (ii) 게이트가 참조할 지표가 없다 — `compute_metrics` 반환 **16키**에 `closed_round_trips` 부재(`recommendation_metrics.py:82-100`)인데 원안은 그 필드를 사이클 2 에 배치하고 게이트는 사이클 1 에 뒀다 (iii) 기본값 None = 미주입 시 게이트 무효인데 원안 회귀 목록이 그 무효 상태를 계약으로 굳힌다 |
| **6** | 동결 창 = `active_freezes(today, overlay)` **날짜 순수함수**, 해제일 = "N=10 또는 2주 중 늦은 쪽" | freeze 레코드 = `{sid, key, from, to, decided_on, release:{min_closed_trips, min_business_days}}` · 해제 판정은 `generate_recommendations` **peer 수집 직후 비동기 평가** 후 데이터로 주입 | 설계(날짜 전용)·결정표 권고(표본 조건 필요)·cycle228 원본(변경 시점 기준 왕복 카운트)이 서로 다른 **세 물건**이었다. 날짜만 쓰면 BFB 실측(30·90일 청산 **0건**)에서 2주 뒤 N≈0 인데 동결이 풀린다. 롤링 표본 게이트로 대체하면 완화 성공 직후 1주짜리 표본으로 재튜닝 — cycle228 이 금지한 바로 그 행위. 동기 순수성 제약은 `_validate_recommendations` 에만 걸리므로 비동기 평가 후 주입은 위반이 아니다 |
| **7** | 정본 = `FROZEN_PARAMS: dict[str,str]` 평면 맵 + 불변식 `FROZEN ∩ PARAM_RANGES = ∅` | 봉인 항목 = **`(strategy_id \| None, key)` 스코프 + `review_when` 필수** · 불변식 = **"전 전략 `DEFAULT_PARAMS` 의 모든 키가 `PARAM_RANGES` / `FROZEN` / `UNCLASSIFIED` 중 정확히 하나"** | (i) 평면 맵은 cycle223 이 명시한 전략별 재검토 조항을 표현 못 한다 — `recommendation_engine.py:87-104` 주석이 "VCP/BFB 는 표본이 없어 donchian 근거에 묶인 상태 … 왕복 ≥20 이면 **그 전략에 한해** 독립 판정" 이라 못박고 `test_cycle223f_ast_manual_apply_safeguard.py:185-190`(G-223F-8)이 그 주석을 핀으로 고정한다. ∅ 불변식은 잠정 결정을 영구 결정으로 승격시킨다 (ii) ∅ 불변식은 약하다 — AST 실측으로 `DEFAULT_PARAMS` 중 `PARAM_RANGES` 밖 키가 **124 키슬롯**(kojiro 31/36 · BFB 26/34 · VCP 26/36 · donchian 20/28 · VB 13/23 · LTV 4/20 · momentum 4/9)이고 payload 는 이를 전량 `current_params` 로 싣는다. ~10키 FROZEN 시드는 10% 미만을 덮고 신규 키는 계속 침묵 범주로 떨어진다 |
| **8** | (없음) | **신규 편입** — `PUT /api/strategies/{id}/params` 와 자문 apply 양쪽에 `[param_change] strategy=… key=… old→new` 감사 마커 | 제3의 쓰기 경로가 검증도 로그도 0 이다 — `src/routes/strategies.py:168-187 update_params` 는 `if key in strategy.config.params` 만 보고 `PARAM_RANGES` 검증 0 · logger 호출 0. 실사용 caller = `Settings.tsx:67,513 → api/trading.ts:41-49`. 유일한 흔적은 `strategy_config.updated_at` **행 단위** 타임스탬프이고 다음 쓰기에 덮인다(실측: BFB/VCP = 2026-09-02 22:40:43Z = **09-03 07:40 KST**, 나머지 5전략 = 08-18 — 오늘 아침 변경의 키 단위 이력은 이미 없다). 손으로 적어 배포하는 `DECISION_LOG` 는 UI 클릭 한 번에 스테일이 된다. cycle223-F2 독트린("제외 결정이 한쪽 경로에만 걸리면 제외가 아니다")을 설계 자신에게 적용한 결과다 |
| **9** | 결정 #8 착수 = **(a) 오늘 장 마감 후, 오늘 밤 20:00 자문 전 배포 목표** | **(b) 내일 정규 사이클.** 오늘 밤 = 코드 0 | 09-02 pending 7건은 이미 전부 `rejected`(실측) · `auto_apply_enabled` 키 부재(실측) · 적용 06-08 이후 0건. 반면 워킹트리에 cycle242 미커밋 5파일. 사이클 A 는 신규 회귀 외에 **수정 대상이 최소 8~10 파일**이라 야간 급행으로 넣을 크기가 아니다 |
| **10** | §0 인용 통계 2개 | **폐기 후 재실측 대체** (§F.8) | 산출식·분류 규칙·모집단이 문서에 없어 재현 불가. 특히 "봉인 결정과 97.8% 충돌" 은 08-21 이후 `recommended_params` 안의 봉인 키가 **0건**이므로 산문 언급 + 비봉인 키 + weight 권고를 합쳐야만 나오는 수치다 — 성격이 다른 셋을 한 지표로 합치면 심각도가 과대 표시된다 |

---

## F.2 내가 추가로 찾은 것 — 비판 2렌즈도 짚지 않은 실측 2건

**① BFB `breakout_retention_minutes` 라이브 값은 3 이 아니라 1 이었다. 오늘 밤이 이 키가 범위 밖인 첫 밤이다.**

원안 B5 는 "코드 DEFAULT 는 3" 만 인용했는데, `parameter_recommendations.current_params` 시계열 실측 결과 08-20~09-02 **전 영업일 `current=1`** 이다.

```
2026-08-20 cur=1 rec=None     2026-08-28 cur=1 rec=None
2026-08-21 cur=1 rec=None     2026-08-31 cur=1 rec=None
...                           2026-09-01 cur=1 rec=3    ← 유일한 권고
2026-08-27 cur=1 rec=None     2026-09-02 cur=1 rec=None
```

귀결 셋: (i) 09-01 의 `rec=3` 은 라이브 1 에서 **DEFAULT 3 쪽으로 끌어당긴 권고**였고, 그때 라이브는 범위 `(1,30)` **안**이었다 — 즉 범위-끌어당김이 아니라 통상 권고였다 (ii) 오늘 07:40 에 1→**0** 이 되면서 **처음으로 범위 밖**이 됐다. 즉 원안이 예상한 기전은 오늘 밤 **처음 발화**하며, 그 예상 자체는 검증 전이다 — D+1 관측 판독의 기준선이 오늘 밤 0시부터 시작한다 (iii) 이 키는 08-20~09-02 13 영업일 중 **1일만** 권고 대상이었으므로 "매일 재발화" 라는 원안의 서술은 `max_scan_stocks`(58/138행) 쪽에만 해당한다.

**② 프롬프트 효과 측정의 분자가 실측 0 이라 원안 관측 판독 #2 는 태어날 때부터 공허하다** (트레이딩 렌즈 지적을 전수 실측으로 확증).

봉인 6키의 `recommended_params` 출현: **08-21 이전 212건 / 08-21 이후 0건**(478행 전수). 따라서 `[advisor_frozen_key_reject]` 는 실행돼도 0 을 찍고, "시간이 지나며 감소해야 한다" 는 판독은 0에서 감소를 관측하라는 요구가 된다. 더구나 원안 §3(d)가 `frozen_params` 를 payload 에 **다시 싣기** 때문에(키 이름 재노출) 발화는 0에서 **증가**할 수도 있어 판독 방향 자체가 뒤집힌다. 대체 분자 = **자문 산문의 봉인 키 언급 빈도**(원안 B1 실측 기준선: `buy_threshold` 37 · `max_positions` 34 · `atr_trail_mult` 11 · `breakout_fail_n_days` 9 · `donchian_period` 6).

**부수 정정** — 검증기 순서상 봉인 검사를 `PARAM_RANGES` 검사(`:200`) **뒤**에 두면 ∅ 불변식 때문에 영원히 도달하지 않는다. 봉인 검사는 `:196`(current_params 멤버십) 다음, `:200` **앞**에 둔다고 명시한다.

---

## F.3 최종 설계

### F.3.1 단일 정본 — `src/engine/advisor_policy.py` (신규 leaf)

```
src/engine/advisor_policy.py        # 8영역 밖. import 는 recommendation_engine / routes 만
├── FrozenEntry(scope: str|None, key: str, reason: str, review_when: str)
│     scope=None 이면 전역, "vcp_breakout" 이면 그 전략만.
│     review_when 필수 — cycle223 의 "왕복 ≥20 이면 그 전략에 한해 독립 판정" 을 데이터로 표현.
├── FROZEN: tuple[FrozenEntry, ...]
├── UNCLASSIFIED: frozenset[str]     # 124 키슬롯 스냅샷 — 침묵의 제3범주를 명시 범주로 승격
├── Decision(scope, key, value, decided_on: date, reason: str, review_by: date)
├── DECISION_LOG: tuple[Decision, ...]
├── Freeze(scope, key, frm: date, to: date, decided_on: date,
│          release: {min_closed_trips: int, min_business_days: int})
├── FREEZES: tuple[Freeze, ...]
├── MIN_CLOSED_SAMPLE: int = 10       # cycle228 N=10
├── MAX_KEYS_PER_CYCLE: int = 3
├── effective_frozen(strategy_id, overlay) -> dict[str, str]
├── effective_decisions(strategy_id) -> dict[str, Decision]
├── active_freezes(strategy_id, today, closed_trips, overlay) -> dict[str, date]
└── render_*_block(...) -> str        # 프롬프트 §2~§4 생성 (사이클 C)
```

**초기 시드**

| 범주 | 항목 |
|---|---|
| `FROZEN` 전역 | `max_positions`(2026-08-03 · review_when="리스크 캡 재설계 시") · `buy_threshold`·`donchian_period`(cycle212) · `max_breakout_extension_pct`(cycle209) |
| `FROZEN` 스코프 | `atr_trail_mult`·`breakout_fail_n_days` — scope=`donchian_swing`, review_when="왕복 ≥20". **VCP/BFB 는 별도 항목**으로 같은 키를 담되 review_when="첫 체결 후 왕복 ≥20 이면 그 전략에 한해 독립 판정"(`:87-104` 주석 원문 보존) |
| `DECISION_LOG` | `max_scan_stocks=4000` (scope=BFB/VCP/kojiro, 2026-08-08, "KRX 전체 유니버스 3,577 스캔 확대", review_by=2026-11-08) · `breakout_retention_minutes=0` (scope=BFB, 2026-09-03, "진입 완화 실험", review_by=2026-10-03) |
| `FREEZES` | BFB `breakout_retention_minutes` — from 2026-09-03, release={min_closed_trips: 10, min_business_days: 10} |
| `UNCLASSIFIED` | 124 키슬롯 스냅샷(§F.8 스크립트로 산출) |

**불변식(AST 가드)**
1. `FROZEN.keys ∩ PARAM_RANGES.keys == ∅` (원안 유지 — 스코프 항목은 키 단위로 판정)
2. **전 전략 `DEFAULT_PARAMS` 의 모든 키 ∈ `PARAM_RANGES` ⊎ `FROZEN` ⊎ `UNCLASSIFIED` (정확히 하나).** 신규 키는 분류 전까지 테스트 FAIL — 결정 #9(`max_lot_units`)가 사람 판단이 아니라 테스트 실패로 자동 표면화된다
3. 오버레이는 **가산 전용** — `|` 만, `-`/`difference` 금지(원안 유지)
4. `DECISION_LOG` 전 항목 `review_by` 비어 있지 않음. 경과 시 `[advisor_decision_stale]` WARNING — 낡은 방패가 침묵하지 않고 시끄러워진다

**테스트 리터럴 회수 규약(원안 유지)** — AST 가드 5파일의 리터럴은 **자기검사로 존치**한다. 전부 참조로 바꾸면 누군가 `FROZEN` 을 비웠을 때 모든 가드가 공허하게 통과한다(cycle224·226 에서 두 번 겪은 자기 가드 공허화의 정확한 재발 형태).

### F.3.2 검증기 — 시그니처 무변경

```python
def _validate_recommendations(
    raw: dict,
    current_params: dict,
    *,
    strategy_id: str | None = None,
    metrics: dict | None = None,
    decisions: Mapping[str, Decision] | None = None,
    freezes: Mapping[str, date] | None = None,
    frozen: Mapping[str, str] | None = None,
    sink: dict | None = None,          # ← 거부 원장 out-parameter (반환값 5-tuple 유지)
) -> tuple[dict, str, float | None, str | None, str | None]:
```

**거부 사유 5종** (전부 WARNING — `logger.warning` 은 `src/main.py:161-201 _DbLogHandler`(INFO 컷)를 넘어 `system_logs` 에 도달한다. ⚠️ `main.py:177-186` 이 **동일 메시지 문자열**을 500ms 내 재emit 하면 큐 적재를 skip 하므로 **모든 마커는 `strategy=`·`key=` 를 문자열에 포함**해야 한다)

| 마커 | 조건 | 처리 | 검증기 내 위치 |
|---|---|---|---|
| `[advisor_frozen_key_reject]` | `key ∈ effective_frozen(sid)` | 키 폐기 + 사유 | **`:196` 다음, `:200` 앞** (∅ 불변식 때문에 뒤에 두면 미발화) |
| `[advisor_decision_reject]` | `key ∈ effective_decisions(sid)` ∧ 추천값 ≠ 결정값 | 키 폐기 + 결정일·사유·review_by 병기 | `:200` 뒤 |
| `[advisor_live_out_of_range]` | `current_params[key]` 가 범위 밖인데 **DECISION_LOG 미등재** | **통과**(폐기 아님) + WARNING | 같은 지점 |
| `[advisor_freeze_window_reject]` | `key ∈ active_freezes(sid, today, closed_trips)` | 키 폐기 + 해제 조건 병기 | 같은 지점 |
| `[advisor_sample_gate]` | `metrics["closed_round_trips"] < MIN_CLOSED_SAMPLE` **또는 metrics 결손** | `recommended_weight` → `withheld_weight`, `weight_reasoning` → `withheld_reason`. **params 무접촉** | weight 블록(`:243-257`) |

⚠️ **세 가지 계약**
- **`[advisor_live_out_of_range]` 는 차단이 아니라 표시다.** 사유가 기록되지 않은 범위 밖 값은 "의도된 결정" 과 "미기록 오설정" 을 구별할 수 없다 — 조용히 보호하면 후자를 영구 은폐한다. 표시하고 통과시켜 자문이 지적할 수 있게 남긴다(비중 단위 계약 사이클의 금기: "추론 분기는 결함이 아니라 결함 은폐 장치다" 의 동형 적용).
- **표본 게이트는 fail-closed.** `metrics` 결손(현행 `:422-424` 이 peer 수집 실패 시 조용히 `{}` 로 만든다)은 '표본 부족' 과 구별 불가이므로 **강등 + WARNING**. cycle228 vol 게이트가 `no_data` 를 fail-closed 로 처리한 선례와 방향을 맞춘다.
- **`withheld_*` 는 신설 필드다.** 기존 "weight null ⇒ weight_reasoning null" 계약(`:275-276`)과 하류 `routes/recommendations.py:104-109`(weight null 이면 apply 거부)를 **깨지 않고** "근거는 읽되 적용 버튼은 못 누르게" 를 구현한다.

### F.3.3 감사 경로 — 제3의 쓰기 경로 봉합 (신규)

| 경로 | 현재 | 최종 |
|---|---|---|
| `routes/strategies.py:168-187 update_params` | 검증 0 · 로그 0 | `[param_change] source=ui strategy=… key=… old=… new=…` WARNING (값 변경분만). **차단은 도입하지 않는다** — 운영자 직접 조정은 정당한 권한이고, 여기서 막으면 §F.3.2 의 `[advisor_live_out_of_range]` 가 재현할 수 없는 상태가 만들어진다 |
| `routes/recommendations.py` apply | `[manual_apply_safeguard_skip]` 만 | `[param_change] source=advisor …` 동일 서식 추가 |

**`DECISION_LOG` 파생은 기각한다** — 로그 라인은 "왜" 를 담을 수 없다(사유는 사람이 쓴다). 대신 스테일을 **탐지 가능하게** 만든다: `[param_change]` 로 변경 사실이 남고, `[advisor_live_out_of_range]` 가 미등재 범위 밖 값을 매일 표시하며, `[advisor_decision_stale]` 이 `review_by` 경과를 알린다. 세 마커가 함께 "DECISION_LOG 가 현실과 어긋났다" 를 시끄럽게 만든다.

### F.3.4 수동 apply 미러 — 기존 AST 가드 준수

- **필터는 반드시 후속 축소 대입으로 얹는다.** `test_cycle223f_ast_manual_apply_safeguard.py:48-56`(G-223F-1: `apply_rec` 본문에 리터럴 `PARAM_RANGES` 존재) · `:58-75`(G-223F-2: **첫 번째** `valid_keys` 대입식에 `PARAM_RANGES` 포함, 첫 대입에서 return). 단일 정본으로 화이트리스트를 `advisor_policy` 경유로 **교체**하면 둘 다 FAIL 한다.
  ```python
  valid_keys = {k for k in requested_keys if k in PARAM_RANGES}   # ← 첫 대입 무변경 (G-223F-2 통과)
  valid_keys = _advisor_policy_filter(valid_keys, ...)            # ← 후속 축소
  ```
- **거부 메시지를 사유별로 분기한다.** 현행 `src/routes/recommendations.py:106-116` 은 `valid_keys` 가 비면 무조건 "전략 정체성 상수(진입/청산 임계·슬롯 수)는 AI 자문으로 적용할 수 없습니다" 를 반환한다 — 결정 충돌·동결 창 거부에는 **사실과 다른 안내**다. 운영자에게 알리려던 바로 그 순간에 거짓을 말하게 된다.
- `weight = 0.0` 확인 가드(원안 D6) 유지 · 감액 복구 경로 무조건 통과(N1 계약) 유지.

### F.3.5 payload — 구조 분할 + 결손 보완

원안은 문제를 **제조하는 payload 구조**를 그대로 두고 산문만 고쳤다. `current_params` 전량(33~35키)을 싣고 범위는 8~10키만 실으므로 봉인 키가 "금지" 가 아니라 "범위만 안 알려준 튜닝 대상" 으로 보인다는 진단(B1)은 원안 자신의 것인데, 처방은 프롬프트 문장이었다.

**구조 분할(토큰 증가 ≈0, 효과는 문장보다 크다)**
```
current_params → tunable_params  {key: {value, min, max}}
                 frozen_params   {key: {value, reason, review_when}}
                 decided_params  {key: {value, decided_on, reason, review_by}}
                 readonly_params {key: value}          ← UNCLASSIFIED 124
```
⚠️ `tests/unit/engine/test_recommendation_market_regime_payload.py:391 assert set(payload.keys()) == expected_keys`(8키 정확 일치) + `:392` 가 필연 FAIL 한다 — **정당한 의미 전환**이며 이 프로젝트 규약상 문서화 대상이다. `_call_openai` 시그니처 확장 자체는 Case I 가 kwargs 호출이라 기본값으로 흡수된다.

**신규 필드**(원안 §3(d) 유지, 우선순위만 조정): `sample`{closed_round_trips, analyzed_days, min_required} · `funnel`(최근 3영업일) · `past_recommendations`(14일 요약) · `metrics.rr`/`expectancy`/`avg_hold_days`/`exit_reason_breakdown` · `metrics.data_quality_notes`(08-18 오염 표시) · `strategy_facts` · `account` · `active_freezes` · `backtest_summary`(불가 시 `{"status":"unavailable","since":"2026-08-18"}` 명시).

**계측 동반**(원안 미검토) — 현행 `:461-473` 은 `asyncio.wait_for(..., timeout=30)` → `except asyncio.TimeoutError: raw = {}` → `:502` 로 **빈 자문이 INSERT** 되고 흔적은 `logger.warning` 한 줄이다. payload 를 키우면서 이걸 두면 "v2 가 판단 보류를 늘렸다" 와 "LLM 이 시간 초과했다" 가 D+1 에 구별되지 않는다. → `response.usage` + 지연 캡처(migration 1건, `tests/integration/pg_harness.py:117` 이 `sorted(glob("*.sql"))` 라 CI 비용 ≈0) + 타임아웃 파라미터화 + `[advisor_llm_timeout] strategy=…` 마커. **프롬프트 v2(사이클 C) 보다 앞선다.**

### F.3.6 프롬프트 v2 — 상수가 아니라 함수

```python
SYSTEM_PROMPT_BASE = """..."""                    # 정적 부분 — 모듈 상수로 존치
def build_system_prompt(strategy_id, today, live_params, overlay) -> str: ...
```
- 원안 초안은 **그대로는 동작하지 않는다** — 모듈 레벨 f-string 안에서 `{{SYSTEM_FACTS}}` 로 이중 중괄호 처리해 렌더 결과가 치환값이 아니라 리터럴 `{SYSTEM_FACTS}` 다(단일 중괄호면 import 시점 NameError). 게다가 `PR_HEADROOM`·`SIZING_MODE`·`active_freezes` 는 전략별·날짜별 값이라 모듈 상수로는 애초에 표현 불가.
- **정적 부분을 `SYSTEM_PROMPT_BASE` 로 남기면 기존 단언 4건이 그대로 물린다** — `test_regime_observation_honesty.py:126,136` · `test_recommendation_market_regime_payload.py:341-351`. 적응 비용 ≈0(모듈 속성명만 교체).
- 실측 크기: 현행 `SYSTEM_PROMPT` **1,542자** → v2 초안 **4,869자**(주입 블록 렌더 전, ~3.2배).

**본문 개정 4곳**

| 원안 | 최종 |
|---|---|
| §0 "조임을 권고할 때는 반드시 RR 에 미치는 영향을 함께 적어라" + 편향 비율 인용 | **편향 비율을 프롬프트에 싣지 않는다.** 근거 없이 방향 지시만 주면 모델은 순응해 부호만 뒤집는다. 대신 사이클 B 가 넣는 `metrics.rr`/`expectancy` 를 인용하라고 지시. ⚠️ **완화는 fail-safe 가 아니다** — 표본 게이트를 통과하는 4전략 중 **VB·LTV 는 터틀 미배선 = 고정 명목**이라 `stop_loss` 확대가 곧 포지션당 손실 확대다. "손절 완화 시 사이징 모드를 확인하라" 를 명시 |
| §5 "표본 미만이면 `recommended_params` 와 `recommended_weight` 를 **모두 null**" | **`recommended_weight` 만.** `recommended_params` 는 계속 내되 **근거 등급**(`fill` 체결 기반 / `funnel` 체결 이전 / `a-priori` 설계 논리)을 밝히게 한다. 원안대로면 프롬프트(넓음)가 검증기 C-2(params 는 폐기 안 함)와 정면 충돌하고 넓은 쪽이 이겨 **BFB·VCP·momentum 의 파라미터 자문이 전면 소멸**한다(실측 30일 청산: BFB **0** · VCP **0** · momentum 2). 그런데 BFB/VCP 는 오늘 07:40 완화의 당사자이고 그 효과 판정에 필요한 증거는 체결이 아니라 funnel 이다 |
| §5 "비중을 깎으면 표본은 더 안 쌓인다" | **기전이 틀렸다.** `strategy_base.py:450-464 _fallback_one_share` 가 `qty<=0` 일 때 "잔여 ≥ 현재가면 1주" 를 반환하므로(`:475,497` 위임) 비중 축소는 체결 **건수**가 아니라 건당 명목을 줄인다. 운영 관용구도 반대다(2026-08-04 VB·LTV 1% = "손절 평가 유지용 극소값"). 더 나쁜 것은 방향 반전 — 깊은 축소는 포지션을 1주 폴백 구간으로 밀어 넣고 그 구간의 명목은 의도 리스크를 **초과**할 수 있다(cycle233 `[oversized_fallback]` 실측 000815 4.11유닛 = 지금 cycle242 가 고치는 중인 결함). → "비중 축소는 표본 수가 아니라 표본의 금액 유의성을 줄인다. 깊은 축소는 1주 폴백 구간으로 밀어 포지션당 리스크를 오히려 키울 수 있다" |
| `:142` 삭제("화이트리스트 **외** 신규 파라미터 도입 또는 폐기 자유 텍스트 자문") | **삭제가 아니라 분리.** 이 문장이 바로 원안 E2 가 "지난 2주 유용 산출 전량" 이라고 평가한 `code_review_notes` 를 **생성시키던 유일한 지시문**이다. 가치 역전을 고친다면서 가치의 원천을 제거하면 안 된다. → "**파라미터 값 제안**은 `param_ranges` 키만" 은 유지하되, "구조·배관·관측 공백에 대한 자유 자문" 지시는 `code_review_notes` 항목에 **명시적으로 보존**한다 |

### F.3.7 출력 스키마·프론트 (사이클 D)

- `sample_status` · `no_change_reason` · `needs_human_decision[]` · `hypotheses[]` 채택. **단** `confidence` 필드는 **제거**(검증도 소비도 없는 미교정 숫자 = 원안 E1 이 비판한 "확신 없어도 숫자를 내놓게 강제" 의 재생산), `hypotheses` 는 저장 시 `(strategy, claim_hash)` **dedupe** — 최초 제기일·재제기 횟수만 갱신하고 `required_sample` 도달일에 "검증 가능" 배지. 중복 억제가 없으면 BFB 기준 `required_sample=10` 도달까지 두 달, 같은 가설이 40+ 영업일 반복 출력돼 `max_scan` 172회와 형식만 다른 같은 현상이 된다.
- **반대 통로에 소비자를 준다** — `needs_human_decision` 비어있지 않으면 `[advisor_dissent] strategy=… topic=…` WARNING + 20:10 리포트 편입. 원안 상태로는 기계의 *순응 실패* 는 시끄럽고(거부 마커 5종) 기계의 *반대* 는 조용한 비대칭이었고, 종착지는 06-08 이후 86일 무적용 UI 카드였다.
- **catch-22 해소** — 원안 §3 은 "매매 결과를 나쁘게 만든다는 **관측 증거**가 있을 때만 권고" 인데 사람 결정이 걸린 키의 전략이 정확히 표본 0(BFB/VCP 90일 청산 0건)이라 증거 생성이 불가능하다. 근거 등급 `a-priori` 이의는 **폐기 대신 통과**시켜 `needs_human_decision` 으로 흐르게 한다.
- 프론트 배지 6종 · notes/hypotheses 상단 이동 · 정규화 미리보기 · weight 0 확인 — 원안 유지. **누락 파일 보완**: `src/db/parameter_recommendations.py`(insert 시그니처) · migration 042 · `src/models/recommendation.py` · `frontend/src/types/recommendations.ts` · MSW 핸들러 · Playwright LIFO 픽스처(CLAUDE.md 의무).
- **거부 원장은 신규 컬럼**(migration 042). 기존 `metrics` JSONB 하위 키에 넣지 않는다 — `src/db/parameter_recommendations.py:37,71` 의 `metrics` 는 `compute_metrics` 결과를 그대로 저장한 **LLM 이 본 입력의 충실한 기록**이고, 산출물 아티팩트를 섞으면 그 성질이 소멸한다(원안 자신의 결정 #5 "조용히 고치지 말고 시끄럽게 표시" 위반). migration 031(daily_log_reports 5컬럼) 선례가 있다.

---

## F.4 최종 롤아웃 — 4 사이클, 순서 반전

**전 사이클 공통: 8영역 diff 0.** 접촉 파일 어느 것도 `test_cycle223f_ast_manual_apply_safeguard.py:196-205 _EIGHT_AREAS` 에 없다. 매매 hot path 무접촉(자문은 20:00 배치 경로).

### 사이클 A — 정본 + 검증기 + 감사 (~1.5 사이클)
- 신규 `src/engine/advisor_policy.py`(스코프 봉인 · DECISION_LOG · FREEZES · UNCLASSIFIED 124 · MIN_CLOSED_SAMPLE)
- `_validate_recommendations` **시그니처 무변경** + `sink` out-parameter + 거부 5종(봉인 검사는 `:200` **앞**)
- `compute_metrics` 에 `closed_round_trips` 추가(정의: 포지션 단위 청산 완결 건수 — `trades_count`(buy+sell 합, 최대 2배 과대)·`win_count+loss_count`(PARTIAL 분할 청산에서 과대) 대리 금지)
- `withheld_weight`/`withheld_reason` 신설 + 거부 원장 컬럼(migration 042)
- 수동 apply **후속 축소 대입** 미러 + 사유별 메시지 분기 + weight 0.0 가드
- **`[param_change]` 감사 마커 2경로**(`routes/strategies.py` · `routes/recommendations.py`)
- AST 불변식 4종 + 테스트 리터럴 자기검사 존치
- **프롬프트 무변경**(댕글링 참조 차단)
- 회귀: 결정충돌 거부 · 봉인 거부(순서 포함) · 동결 거부 · `live_out_of_range` **통과** 확인 · 표본 게이트 fail-closed · `sink` 미주입 시 기존 행위 byte 동일 · 오버레이 가산 전용 · `[param_change]` 도달
- 뮤테이션: 봉인 검사를 `:200` 뒤로 이동 → 미발화 FAIL · `FROZEN` 비우기 → 자기검사 FAIL · 오버레이 `-` 도입 → AST FAIL · `live_out_of_range` 를 폐기로 바꾸기 → FAIL
- 수정 대상: 신규 회귀 ~35 + **기존 0**(시그니처 무변경 채택 효과)

### 사이클 B — payload 구조 분할 + metrics 파생 + 계측 (~1 사이클)
- payload 4분할 + 신규 필드 10 · `metrics` 파생 4 + `data_quality_notes` · D-1 `daily_log_reports` 요약
- 토큰/지연 캡처 + 타임아웃 파라미터화 + `[advisor_llm_timeout]`
- 회귀: payload 키 존재/부재 graceful(funnel DB 실패 시 `{}` 로 자문 계속) · 오염 탐지 순수함수 · RR 경계(손실 0건·이익 0건)
- **기존 수정**: `test_recommendation_market_regime_payload.py:391,392` 완전일치 단언 적응(의미 전환 1)

### 사이클 C — 프롬프트 v2 (~1 사이클)
- `SYSTEM_PROMPT_BASE` + `build_system_prompt()` · 본문 개정 4곳 · 근거 등급 도입
- **기존 수정**: 프롬프트 내용 단언 4건(기저 상수 보존 시 속성명 교체만)

### 사이클 D — 출력 스키마 + 프론트 (~1.5 사이클)
- 신규 필드 4 + dedupe · `[advisor_dissent]` · 20:10 리포트 편입
- 프론트 배지 6 + 상단 이동 + 정규화 미리보기 + MSW/Playwright 픽스처
- 회귀: 구 스키마 하위호환(신규 필드 없어도 저장 성공) · dedupe · 배지 조건

### 관측 판독 (개정)

| # | 지표 | 정상 판독 | 기준선(실측) |
|---|---|---|---|
| 1 | `[advisor_decision_reject]` | max_scan 3전략 + BFB retention = **최대 4건/일**. 0이면 가드 공허 | max_scan 58/138행(42.0%) · retention 1/13영업일 |
| 2 | **자문 산문의 봉인 키 언급 빈도** (구 판독 #2 폐기 — 분자 실측 0) | 사이클 C 후 감소 | buy_threshold 37 · max_positions 34 · atr_trail_mult 11 · breakout_fail_n_days 9 · donchian_period 6 |
| 3 | `[advisor_live_out_of_range]` | **0 이 정상**(4쌍 전부 DECISION_LOG 등재 예정). >0 = 미기록 오설정 발견 | 오늘 기준 4쌍 |
| 4 | `withheld_weight` 비율 | 표본 게이트 후 급증해야 정상(BFB/VCP/momentum) | weight 동봉 30일 118/138(85.5%) · 전체 425/478(88.9%) |
| 5 | `[param_change] source=ui` | UI 변경이 로그에 남는지 — 남지 않으면 DECISION_LOG 는 유지 불가 | 현재 0(로그 자체가 없음) |
| 6 | `[advisor_llm_timeout]` | 프롬프트 3배 확장 후 급증하면 타임아웃 상향 | 현재 관측 불가 |

---

## F.5 사용자 결정 필요 항목 (개정)

| # | 결정 | 선택지 | 최종 권고 | 원안 대비 |
|---|---|---|---|---|
| **1** | `max_scan_stocks` 범위 모순(라이브 4000 vs 상한 500) | (a) 범위 상한 4000~5000 상향 (b) 봉인 편입 (c) 현행 유지 + DECISION_LOG 등재 + 결정충돌 가드 | **(c)**. (b)는 가드 4건 + ⊆ 불변식 2건을 깨고 `INT_PARAMS` 동반 제거를 요구하며, 전역 범위라 라이브 값이 정상인 donchian(400)·VB·LTV(100)의 튜닝 축까지 봉인한다. (c)는 라이브 결과가 (b)와 같고 테스트 비용 0 | **변경** (b)→(c) |
| **2** | BFB `breakout_retention_minutes = 0` | (a) 범위 하한 0 (b) 결정 로그 + 동결 창 (c) 봉인 | **(b) 유지, 사양 개정** — 해제 조건 = `min_closed_trips=10` **∧** `min_business_days=10`(둘 다 충족). 날짜 단독은 BFB 체결률(30·90일 0건)에서 N≈0 인데 풀리고, 표본 단독은 완화 성공 직후 1주 표본 재튜닝을 부른다 | 사양 개정 |
| **3** | 자문 주기·형식 | (a) 현행 (b) 축 분리(일간=브리핑/주간=숫자/월간=비중) (c) 격일 | **(b) 를 사이클 D 이후로 유지 이연.** 표본 게이트가 자동으로 "표본 있는 전략만 숫자" 를 만든다 | 유지 |
| **4** | 표본 문턱 | (a) N=10 (b) N=20 (c) 전략별 차등 | **(a) N=10 단일값 + 축 분리.** weight·청산 파라미터 = `closed_round_trips ≥ 10` / 진입 파라미터 = 게이트 없음(사이클 A) → funnel 근거 게이트(사이클 B 이후) | 축 분리 추가 |
| **5** | 08-18 metrics 오염 | (a) 08-18 행 제외 (b) `data_quality_notes` 표시 + 09-15 자연소멸 (c) 재계산 | **(b) 유지.** ⚠️ 표시 수단이 사이클 B 이므로 그 전까지는 오염 입력 위에서 판독한다는 사실을 명시. `cumulative_return_rate` TWR 컬럼 오염 여부는 별도 확인 필요 | 한계 명시 추가 |
| **6** | **(신규)** 제3 쓰기 경로 `PUT /api/strategies/{id}/params` | (a) `[param_change]` 감사 마커만(차단 없음) (b) 마커 + `PARAM_RANGES` 검증 (c) 현행 유지 | **(a).** (b)는 운영자의 정당한 권한을 막고 `[advisor_live_out_of_range]` 가 잡을 대상 자체를 없앤다. 감사 마커만으로 DECISION_LOG 스테일이 탐지 가능해진다 | **신규** |
| **7** | 백테스트 MCP(11일 다운, 무경보) | (a) 복구 (b) 토글 OFF + "unavailable" 명시 (c) 방치 | **(b) 즉시, (a) 후속.** 전 이력 349건 중 유의 결과 0건이라 복구 편익 자체가 미검증 | 유지(번호만 이동) |
| **8** | `auto_apply` 처분 | (a) 현행 (b) 표본 게이트 얹고 유지 (c) 제거 | **(b).** ⚠️ `tests/unit/engine/test_auto_apply_recommendations.py` 픽스처 5건에 `metrics` 가 0건이므로 fail-closed 게이트를 얹으면 전부 깨진다 — 픽스처 적응을 사이클 A 계획에 포함 | 파급 명시 추가 |
| **9** | 착수 시점 | (a) 오늘 밤 20:00 전 (b) 내일 정규 사이클 | **(b).** 오늘 밤은 코드 0(§F.7). 15:30~20:00 창은 16:00 stock_master · 16:20 funnel capture · 16:40 financial 적재와 겹치고, 워킹트리에 cycle242 미커밋 5파일이 있다 | **변경** (a)→(b) |
| **10** | 강한 불변식(`UNCLASSIFIED` 124키 레지스터) 채택 | (a) 채택 — 신규 키는 분류 전까지 테스트 FAIL (b) 약한 ∅ 불변식만 | **(a).** 124 키슬롯이 지금 payload 에 전량 실리면서 아무 라벨이 없다. (a)면 결정 #11 이 사람 판단이 아니라 테스트 실패로 자동 표면화된다. 비용 = 리터럴 1파일 + AST 가드 1 | **신규** |
| **11** | cycle242 신규 키 `max_lot_units` | (a) `FROZEN` 즉시 편입 (b) `UNCLASSIFIED` 등재 후 cycle242 소유 판정 | **(b).** 분류는 그 사이클의 설계 판단이다. #10 채택 시 `DEFAULT_PARAMS` 에 들어가는 순간 테스트가 분류를 강제하므로 침묵 범주로 떨어질 수 없다 | (a)→(b) |

---

## F.6 남은 위험 — 이 설계가 닫지 못하는 것

1. **`DECISION_LOG` 는 여전히 사람이 손으로 유지한다.** `[param_change]`·`[advisor_live_out_of_range]`·`[advisor_decision_stale]` 3중 탐지는 *어긋남을 알려줄* 뿐 *자동 정합*하지 않는다. 로그는 사유를 담을 수 없으므로 이건 의도적 잔여다.
2. **`UNCLASSIFIED` 124 는 스냅샷**이다. 기존 키의 분류를 미룬 상태를 명시화했을 뿐 해소한 게 아니다 — 실제 분류는 전략별 후속 작업.
3. **08-18 오염은 사이클 B 까지 입력에 남는다.** 그동안의 D+1 판독은 오염 입력 위에서 수행된다.
4. **효과 측정의 반사실이 없다.** 적용 15/478 · 06-08 이후 0건이므로 "자문의 조임이 틀렸다" 는 증거는 이 설계 후에도 생기지 않는다. 측정 가능한 것은 *권고의 성질 변화*(거부 마커·근거 등급·withheld 비율)뿐이다.
5. **BFB/VCP 표본 문제는 자문 개선으로 풀리지 않는다.** 30·90일 청산 0건이고 체결률 추정 ≈0.5건/일이다. 자문이 할 수 있는 최선은 "숫자를 내지 않고 funnel 근거로 가설을 남기는 것" 이며, 실제 해소는 오늘 07:40 완화의 결과에 달렸다.

---

## F.7 오늘 밤(09-03) 20:00 조치 — 코드 0

**예상 산출**(전부 이력 기반):
1. BFB `breakout_retention_minutes: 0 → 1~3` — **오늘이 이 키가 범위 밖인 첫 밤**이므로 이 예상은 미검증이다. 발화하면 F.2① 의 기전이 확증되고, 안 하면 원안의 범위-끌어당김 가설이 이 키에 대해서는 반증된다. **어느 쪽이든 관측 가치가 있다 — 그래서 오늘 밤은 막지 않는 편이 낫다.**
2. BFB/VCP/kojiro `max_scan_stocks: 4000 → 500` — 09-02 까지 연속. 30일 138행 중 58행(42.0%)
3. BFB/VCP `recommended_weight` 감액 — 거래 0건 논리(30·90일 청산 실측 0)
4. donchian/LTV/VB 손절·`daily_loss_limit` 조임

**조치: `Recommendations` 화면에서 적용 버튼을 누르지 말 것.** `auto_apply` 는 비활성이므로 방치해도 라이브에 유입되지 않는다. 특히 1·2 는 오늘 오전과 08-08 의 사람 결정을 되돌리는 것이고, 3 은 완화 실험의 표본 형성을 자금 측면에서 방해한다.

**스톱갭이 필요하다고 판단되면**(관측 기준선을 오늘부터 쌓고 싶은 경우) 최소판은 이것뿐이다 — `recommendation_engine.py:209` 아래 `DECISION_LOG` 2행 + 결정충돌 거부 6줄 + `logger.warning` 마커. 시그니처 무변경, 신규 모듈 0, 기존 테스트 파급 0, 신규 회귀 3~5. 다만 **오늘 밤 배포는 권고하지 않는다**(워킹트리 cycle242 동반 출하 위험 + 위 1번의 관측 가치 소멸).

---

## F.8 실측 부록 — 재현 가능한 통계

전부 `parameter_recommendations` 478행 · `strategy_config` 7행 · `trade_history` 전수 기준. EC2 read-only.

| 지표 | 값 | 산출 방법 |
|---|---|---|
| 총 자문 행 | 478 | `count(*)` |
| status 분포 | expired 428 / partial 28 / **applied 15** / rejected 7 | `group by status`. applied 최종 = **2026-06-08**(86일 무적용). rejected 7 = 09-02분, **보고서 1차 작성 이후 처분됨** |
| 키 단위 권고 총량 | **2,151** | `Σ len(recommended_params)` |
| 손절 계열 방향 | **조임 773 : 완화 16 (98.0%)**, 표본 789 | 키 7종(`stop_loss_rate`·`trailing_stop_rate`·`intraday_stop_loss`·`overnight_stop_loss`·`stop_loss_main`·`stop_loss_pre_nxt`·`daily_loss_limit`), `abs(rec) < abs(cur)` = 조임. 동률 0 |
| 봉인 6키 `recommended_params` 출현 | 08-21 **이전 212** / **이후 0** | 키 = max_positions·buy_threshold·donchian_period·max_breakout_extension_pct·atr_trail_mult·breakout_fail_n_days |
| `max_scan_stocks` 권고 | 총 **172** (08-21 이후 32) | 행 단위 포함 여부 |
| 최근 30일(08-04~) 138행 | max_scan 포함 **58 (42.0%)** · 봉인키 포함 **18 (13.0%, 전부 08-21 이전)** · weight 동봉 **118 (85.5%)** · `recommended_params` 빈 행 5 | ⚠️ **원안 "135행(97.8%) 봉인 충돌" 대체** |
| 전체 weight 동봉 | 425/478 (**88.9%**) | 원안 D2 수치와 일치 |
| 라이브 범위 밖 값 | **4쌍** — `max_scan_stocks=4000`(BFB·VCP·kojiro) · `breakout_retention_minutes=0`(BFB) | `strategy_config.params` × `PARAM_RANGES` |
| `strategy_config.updated_at` | BFB·VCP = **2026-09-02 22:40:43Z**(= 09-03 07:40 KST) · 나머지 5 = 2026-08-18 | 행 단위 — 키 단위 이력 없음 |
| 청산(SELL, COMPLETED\|PARTIAL) 30일/90일 | VB 34/75 · LTV 15/48 · donchian 13/18 · kojiro 10/14 · momentum 2/10 · **BFB 0/0** · **VCP 0/0** | `trade_history` `timestamp` 기준 |
| `system_config` auto/advisor 키 | `auto_regime_adjust` · `auto_start` **둘뿐** — `auto_apply_enabled` **부재** | `key ILIKE '%auto%' OR '%advisor%'` |
| `DEFAULT_PARAMS` 중 `PARAM_RANGES` 밖 | **124 키슬롯** — kojiro 31/36 · BFB 26/34 · VCP 26/36 · donchian 20/28 · VB 13/23 · LTV 4/20 · momentum 4/9 | 로컬 AST(`ast.Assign` → `DEFAULT_PARAMS` dict 리터럴 키) × `PARAM_RANGES`(26키) |
| BFB `breakout_retention_minutes` 시계열 | 08-20~09-02 **전 영업일 `current=1`**, 09-01 만 `rec=3` | `current_params`/`recommended_params` 시계열 |

**재현 스크립트** — `_workspace/scripts/` 미보관(읽기 전용 검토). 위 표의 각 행은 EC2 `docker exec … python -` 로 `src.db.pg` 를 통해 산출했으며, 산출식은 표의 "산출 방법" 열이 전부다. 사이클 A 착수 시 `tests/` 안 순수함수 회귀로 이식할 것을 권고한다(현재는 일회성 조회).

---

# 원안 (2026-09-03 1차 검토) — 증거 기반은 유지, **판정은 §F 최종본이 정본**

> 아래는 개정 전 1차 검토 전문이다. 격차 진단(§2 A~E)과 file:line 인용은 2렌즈 대조를 전부 통과했으므로
> **증거 문서로 보존**한다. 다만 다음 5가지는 §F 가 대체했다:
> ① §0 통계 2개(97.8% · 89.2%) = **재현 불가로 폐기**(→ §F.8)
> ② §3(c) C-1 6-tuple 시그니처 = **무변경 + out-parameter 로 교체**(→ §F.3.2)
> ③ §3(c) C-2 `[advisor_range_pull_reject]` 판정축 = **DECISION_LOG 멤버십으로 교체**(→ §F.3.2)
> ④ §4 롤아웃 순서·§5 결정 #1/#8 = **개정**(→ §F.4 · §F.5)
> ⑤ §0·B5 의 BFB `breakout_retention_minutes` 서술 = **정정** — 라이브 값은 3 이 아니라 **1** 이었고,
>    09-01 의 `rec=3` 은 범위 **안**에서 나온 통상 권고였다. 범위-끌어당김은 **오늘 밤이 첫 발화**다(→ §F.2①)

## 원안 전문 — 20:00 자문 파이프라인 감사

- 작성: team-leader (2026-09-03)
- 발단: 사용자 질문 2 — ① "자문 프롬프트에도 하면 안 되는 내용을 명시하자" ② "아니면 자문 프롬프트가 우리의 현재 시스템을 제대로 못 담고 있는 거 아닐까?"
- 근거: 렌즈 4종(프롬프트·payload 내용 감사 / 추천 이력 실측 / 파이프라인 관문 / 도메인) + EC2 read-only 실측 + 로컬 소스 대조
- 성격: **읽기 전용 검토**. 소스·테스트·DB 무변경. 본 문서는 설계 제안이며 구현 승인 전 단계다.

---

### 0. 결론

**질문 ②가 근본이고 ①은 그 증상의 부분 처방이다.** 자문 프롬프트(`src/engine/recommendation_engine.py:132-163`, 32줄)는 현재 시스템을 담고 있지 않다 — 절반이 매크로 레짐 지침이고, 이 시스템의 실제 매매 계약(비중이 Σ 로 상대 정규화된다는 사실, `position_ratio × max_positions ≤ 1.0` 불변식, 터틀 ATR 사이징, `tradable_boards` 매수 전용 규약, 청산 정체성 상수, cycle228 N=10 표본 보호, 2026-08-08 유니버스 확대 결정)은 **한 줄도 들어가 있지 않다**. 그 결과 자문은 시스템의 1/3만 보고 매일 7장의 카드를 쓴다 — 읽는 소스가 `trade_history`(30일)·`daily_performance`(20일)·`strategy_config`·`market_regime` 넷뿐이고, funnel·관측 마커·백테스트·과거 처분 이력은 payload 에 0건이다. 그래서 "체결 0건"의 원인을 *임계가 빡빡한 것*과 *배관이 끊긴 것*(= P0-1 유령 키)으로 구분하지 못하고, 유일한 반응이 비중 감액이 된다. 실측이 이를 확증한다 — 30일 138행 중 **135행(97.8%)** 이 봉인 결정과 최소 1개 충돌하고, 4개월 방향 분포는 조임:완화 = **1,370:166 (89.2%)** 단조 래칫이며, 채택률은 478건 중 applied 15건(3.1%)·expired 428건(89.5%)이다.

**금지 목록 명시는 필요하지만, 프롬프트에만 적으면 효과가 없다.** 근거는 두 가지다. (i) *효과가 있다는 증거* — `max_positions`(2026-08-03 제외)·`atr_trail_mult`/`breakout_fail_n_days`(cycle223, 08-21 제외)는 제외 직후 권고가 **0건으로 끊겼다**(08-21 이후 63행 중 0). 즉 "자문에 알려주면 지킨다"가 실측된 유일한 기전이고, 이는 금지 목록을 프롬프트에 실을 근거가 된다. (ii) *프롬프트만으로는 부족하다는 증거* — 지금 매일 반복되는 최악의 권고 `max_scan_stocks 4000→500`(누적 172회, BFB/VCP/kojiro 17 자문일 연속)은 금지 키가 아니라 **화이트리스트 내부값**이라 `_validate_recommendations`(`:196-216`)도 cycle223-F2 수동 apply 가드(`src/routes/recommendations.py:88`)도 통과한다. 적용 버튼 하나로 라이브 유니버스가 87.5% 축소된다. 그리고 이 권고는 LLM 의 실수가 아니라 **우리 코드가 제조한 것**이다 — `PARAM_RANGES["max_scan_stocks"]=(10,500)`(`:67`)이 2026-08-08 유니버스 확대 결정(라이브 4000)을 반영하지 않은 채 payload 에 `current=4000` 과 `max=500` 을 나란히 실어 보내기 때문이다. 오늘 07:40 적용한 BFB `breakout_retention_minutes=0` 도 범위 `(1,30)`(`:109`) 밖이라 **오늘 밤 20:00 부터 정확히 같은 기전에 들어간다**(선행 실증: 09-01 BFB 자문이 이미 `retention: 3` 복귀를 권고했다).

따라서 처방은 "프롬프트에 금지 문구 추가"가 아니라 **세 겹**이다 — ⓐ 금지·결정의 **단일 정본**(`FROZEN_PARAMS` + `DECISION_LOG`)을 코드에 두고, ⓑ 프롬프트 문자열을 그 정본에서 **생성**하고, ⓒ 같은 정본을 검증기·수동 apply 라우트가 **강제**한다. 프롬프트는 권고이고 검증기가 계약이다. 어느 한쪽만 두면 "제외 결정이 한쪽 경로에만 걸리면 제외가 아니다"(`routes/recommendations.py:75-81`, cycle223-F2 가 이미 명문화한 규약)의 재발이다.

**즉시성 판단:** 오늘 밤 20:00 자문은 (a) BFB retention 0 되돌리기 (b) max_scan 500 (c) 표본 0 전략 비중 감액 — 세 가지를 다시 낼 것이 거의 확실하다. 다만 auto_apply 는 현재 **비활성**(`system_config` 에 `auto_apply_enabled` 키 부재 → `get_auto_apply_enabled()` 기본 False, 전 이력 `applied_auto` 0건)이므로 **자동 유입 위험은 없다**. 위험은 운영자가 UI 에서 잘못 누르는 경로 하나뿐이다. 그래서 **작업 중단 사유는 아니며**, 사이클 1(§4)을 오늘 장 마감 이후 정상 TDD 절차로 진행하는 것을 권고한다.

---

### 1. 현재 자문 파이프라인 (8홉)

```
[20:00 KST]  scheduler.py:74 TIME_RECOMMENDATION=time(20,0)
     │        scheduler.py:875  await generate_recommendations()
     ▼
① 사전정리   recommendation_engine.py:417  expire_pending_before(target_date)   ← 어제 pending 만료
     ▼
② peer 수집  :434-451  registry.enabled() 전수 × { weight, trades(30일), perf(20일) → compute_metrics }
     ▼
③ 전략 루프  :453  for strategy in registry.enabled():        (라이브 7 전략 전부 enabled)
     │
     ├─ payload :324-345   ┌ strategy_name / strategy_description(= __doc__ :468)
     │                     ├ current_params  ← **전량**(봉인 키 포함)
     │                     ├ metrics         ← 체결 기반 17지표
     │                     ├ param_ranges    ← current_params ∩ PARAM_RANGES **만**
     │                     ├ current_weight / peer_weights / peer_metrics
     │                     └ market_regime   ← 조건부 12키 (market_regime.py:467-508)
     │
     ├─ LLM     :359-376   SYSTEM_PROMPT(:132-163) + user_msg, model=gpt-5.6-luna, 30s 타임아웃
     │
     └─ 검증    :172-296   _validate_recommendations  ← **동기 순수함수 · DB 접근 0**
                            :197 키∉current_params → logger.debug drop
                            :200 키∉PARAM_RANGES   → logger.debug drop      ◀ 무관측
                            :209 범위 밖           → logger.warning drop
                            :215 INT 캐스트
                            :220-241 position_ratio × max_positions ≤ 1.0
                            :243-257 weight [0,1]   :258-294 notes/weight_reasoning
     ▼
④ INSERT     :495-507  insert_recommendation(recommended_params = **검증 통과분만**)   ← 원본 응답 미영속
     ▼
⑤ 백테스트   :518 → backtest_orchestration.py  (write-only, 다음날 payload 재투입 없음)
     ▼
⑥ auto_apply scheduler.py:894 → :547-681   토글 OFF(키 부재) · 감액만 · 50% cap
                                            :531 _CONSERVATIVE_KEYS=frozenset() ⇒ :637 params 분기 **死코드**
     ▼
⑦ 수동 apply routes/recommendations.py:45-244   :88 PARAM_RANGES 재검증(cycle223-F2) · :146-175 증액 Σ 가드
     ▼
⑧ 프론트     Recommendations.tsx:102 목록 · :471-484 code_review_notes 카드(params 그리드 아래)
```

**금지·정책을 실제로 강제할 수 있는 관문은 ③ 검증과 ⑦ 수동 apply 둘뿐이다.** ①②③payload·④⑤⑧ 에는 관문이 0개이고, ⑥은 현재 비활성이다.

**시각 정합 문제 하나** — 20:10 일일 로그 리포트(`daily_log_reports`, funnel·by_ticker_pnl·api_metrics 보유)는 자문 **10분 뒤**에 생성된다. 그런데 `recommendation_engine` 은 D-1 리포트조차 읽지 않으므로(`log_reports`/`strategy_funnel` import 0건), 자문은 자기 시스템의 하루 요약본을 **한 번도 본 적이 없다**. 반면 funnel 스냅샷 자체는 16:20(`scheduler.py:72 TIME_EVENING_FUNNEL_CAPTURE`)에 이미 DB 에 있다 — **타이밍 제약이 아니라 배관 부재다.**

---

### 2. 격차 표

심각도 기준: **HIGH** = 잘못된 권고를 매일 생산하거나 라이브 적용 시 매매 안전에 직접 영향 / **MEDIUM** = 자문 품질을 구조적으로 깎거나 관측을 지움 / **LOW** = 드리프트·유지보수 상류.

#### A. 낡은 서술 (프롬프트·문서가 코드와 어긋남)

| # | 격차 | 심각도 | 근거 (file:line) | 실측 |
|---|---|---|---|---|
| A1 | 프롬프트가 말하는 weight 의미론이 런타임과 다르다 — "합계 1.0 정규화는 운영자가 apply 시점에 책임"인데 실제로는 `allocate_funds` 가 Σ 로 **상대 정규화**한다. 한 전략을 깎으면 그 돈은 현금이 아니라 다른 전략으로 간다 | **HIGH** | `recommendation_engine.py:138` vs `strategy_registry.py:38-41` (`ratio = weight / total_weight`), `CLAUDE.md:140` 동일 사실 명기 | 09-02 pending 7건 Σ 1.00→**0.64**, 전원 "보수적 축소" 주장. 정규화 후 donchian 은 15%→**31.3%** 로 배증한다. 실제 노출을 줄이는 유일한 레버 `cash_usage_ratio` 는 payload 에 없다 |
| A2 | `auto_apply_recommendations` docstring 이 존재하지 않는 안전장치를 광고 — "보수적 파라미터만 자동 적용" | MEDIUM | `:559-563` docstring vs `:531 _CONSERVATIVE_KEYS = frozenset()` ⇒ `:637 if k not in _CONSERVATIVE_KEYS: continue` 로 params 분기 전체 도달 불가 | cycle210(07-14)이 래칫 차단으로 비운 것. 문서만 남아 "params 도 자동 적용된다"는 오독을 만든다 |
| A3 | `strategy_description` 으로 나가는 docstring 이 라이브 값과 모순인데 어느 쪽이 정본인지 지시가 없다 | MEDIUM | `:468 getattr(strategy,"__doc__")`. donchian docstring "ATR(14)×2 트레일링" ↔ 라이브 `atr_trail_mult=1.8`. BFB docstring "거래량 ≥ 플래그 평균 × 2" ↔ DB `breakout_volume_mult=1.0` (CLAUDE.md cycle228 배너: 실효 BFB 1.0/VCP 1.2) | 자문은 서사와 숫자가 어긋난 두 소스를 동시에 받는다 |
| A4 | 모듈 docstring "매일 16:00에 호출" — 실제 20:00 | LOW | `:3`, `:385` vs `scheduler.py:74` (Phase 0 에서 19:50→20:00 이동) | — |
| A5 | "6 전략" 표기 잔존 — 라이브는 7 전략 전부 `enabled=True` | LOW | `backtest_orchestration.py:101/263/456`, `CLAUDE.md:126`("kojiro 다크런치 enabled=False")·`:146` | EC2 `strategy_config` 7행 전부 enabled(kojiro 0.30 포함). `scheduler.py:872` 주석 "전략당 30s × 6 = 3분" 도 실제 3.5분이라 20:10 settlement 마진 계산이 낙관적 |

#### B. 빠진 봉인 결정 (프롬프트가 말하지 않는 계약)

| # | 격차 | 심각도 | 근거 | 실측 |
|---|---|---|---|---|
| B1 | **봉인 키 목록이 프롬프트에도 payload 에도 없다.** payload 는 `current_params` 전량(BFB 33키·VCP 35키·kojiro 34키)을 싣고 범위는 8~10키만 실으므로, 봉인 키는 "금지"가 아니라 "범위만 안 알려준 튜닝 대상"으로 보인다. 게다가 SYSTEM_PROMPT `:142` 는 정반대로 "PARAM_RANGES 화이트리스트 **외** 신규 파라미터 도입 또는 폐기 자유 텍스트 자문"을 요청한다 | **HIGH** | `:151`("키는 반드시 현재 파라미터에 있는 키"), `:324-326` relevant_ranges, `:331` current_params. 제외 사유는 코드 주석에만: `:57-61`(max_positions) `:87-104`(atr_trail_mult) `:111-116`(breakout_fail_n_days) | 자문 본문이 봉인 키를 거론한 횟수 — `max_positions` 34회(최신 09-02) · `buy_threshold` 37회 · `atr_trail_mult` 11회(08-31) · `breakout_fail_n_days` 9회 · `donchian_period` 6회 |
| B2 | **금지 목록의 현재 정본이 src 가 아니라 AST 테스트 4개 파일의 리터럴이다.** 프롬프트도 검증기도 그것을 읽을 수 없다 | **HIGH** | `tests/unit/ast/test_cycle212_ast_entry_threshold.py:28 _FORBIDDEN=("buy_threshold","donchian_period")` · `test_cycle223_ast_donchian_exit_fix.py:45 _EXCLUDED_KEYS=("breakout_fail_n_days","atr_trail_mult")` · `test_cycle209_ast_extension_param_range.py:47` · `test_cycle228_ast_gate_guards.py:123` · `tests/unit/engine/test_recommendation_param_ranges.py:225` | src 에 대응 상수 0건 ⇒ 단일 정본화는 **신규 설계가 아니라 이미 흩어진 정본의 회수** |
| B3 | **cycle228 N=10 표본 보호가 프롬프트에 없다.** '표본'이라는 단어가 0회 | **HIGH** | SYSTEM_PROMPT `:132-163` 전문. metrics 에 `trades_count`/`analyzed_days` 는 있으나(`recommendation_metrics.py:84-92`) 판단 보류 근거로 쓰라는 지시 없음 | 09-02 BFB weight_reasoning: "최근 20일간 거래 및 성과 데이터가 전혀 없어 검증되지 않은 상태이므로 0.15→0.10 축소". VCP 동일 논리로 0.10→0.05. **두 전략이 정확히 오늘 07:40 진입 완화의 대상이다** — 증거를 만들기 전에 자금이 깎이고, 자금이 줄면 표본은 더 안 쌓인다 |
| B4 | **2026-08-08 유니버스 확대 결정(max_scan 4000)이 어디에도 없고, `PARAM_RANGES` 가 그 결정과 정면 모순**(상한 500) | **HIGH** | `:67 "max_scan_stocks": (10, 500)` vs EC2 라이브 kojiro/BFB/VCP = **4000**(donchian 400, VB/LTV 100) | 축소 권고 누적 **172회**(VCP 46·BFB 40·VB 41·kojiro 22·donchian 17·LTV 6), BFB/VCP/kojiro는 **17 자문일 연속**. 09-02 자문 자신의 문장: "max_scan_stocks 는 현재값 4000이 허용 상한 500을 초과하므로 상한값인 500으로 조정해 **설정 불일치를 해소**". 08-31 VCP notes 는 한 발 더 나가 "설정 검증 단계에서 자동 거부 또는 **상한값 클램프가 필요**" — 사람 결정을 버그로 판정하고 시스템에 강제 클램프 도입을 요구 중 |
| B5 | **오늘 07:40 적용한 BFB `breakout_retention_minutes=0` 이 범위 밖**이라 오늘 밤부터 같은 기전에 들어간다 | **HIGH** | `:109 "breakout_retention_minutes": (1, 30)`. EC2 라이브 BFB = **0**(코드 DEFAULT 는 3, `bull_flag_breakout.py:157`) | 이 키 권고 누적 32회. 09-01 expired 건이 이미 `{"breakout_retention_minutes": 3}` — **완화 이전 값으로의 복귀 권고가 관성으로 존재한다** |
| B6 | `position_ratio × max_positions ≤ 1.0` 불변식이 프롬프트에 없는데, 레짐 섹션은 "aggressive 면 position_ratio 확대 가능"을 **적극 지시**한다 | MEDIUM | `:160` vs 교차제약은 검증기 `:220-241` 에만. `CLAUDE.md:141` 이 계약으로 명시 | 여유 실측: kojiro 0.166×6=0.996 · BFB 0.25×4=**1.00** · VCP 0.20×5=**1.00** · momentum 0.25×4=**1.00** · LTV 0.80 · VB 0.70 · donchian 0.60 ⇒ 7 중 4가 상한에 붙어 있어 증액 권고는 구조적으로 100% 폐기 |
| B7 | **`recommended_weight = 0.0` 이 곧 전략 비활성화**라는 사실이 프롬프트에 없다 | MEDIUM | `:137`("0.0~1.0 범위"), 검증기 `:243-255` 는 0.0 정상 통과. 저장 시 `src/db/strategy_config.py:64 enabled = weight > 0`, 메모리 `strategy_registry.py:54` 동일 | auto_apply 는 50% cap(`:621-623`)으로 0 도달을 막지만 **수동 경로에는 대응 가드가 없다** |
| B8 | **자문 결과가 20:00 직후 자동 적용될 수 있다는 사실이 고지되지 않는다** | MEDIUM | 프롬프트는 `code_review_notes` 에 대해서만 "코드 자동 변경 없이 운영자 수동 검토용"(`:143`)이라 밝히고 weight 자동 적용 가능성은 침묵. 실제 경로 `scheduler.py:889-895` → `:611-637` | **현재 안전** — `system_config` 에 `auto_apply_enabled` 키 부재, `get_auto_apply_enabled` 기본 False(`src/db/system_config.py:413-419`), `applied_auto` 전 이력 0건. 단 토글 한 번에 "표본 0 → 감액"만 자동 발화하는 잠복 상태 |
| B9 | 매매를 실제로 지배하는 축의 상당수가 params 밖 모듈 상수라 자문 시야에 아예 없다 | LOW | `momentum.py:27`/`volatility_breakout.py:30` `BUY_CUTOFF_KST=15:20`(cycle229, DB override 불가) · cycle228 추격 상한 BFB 5.0/VCP 7.5(PARAM_RANGES 미편입) · `_vol_latch` 상태기계 · `risk.py:79 _PRE_MARKET_EXIT_EVAL_STRATEGIES=frozenset({"long_tail_volatility"})` · cycle233 SOFT Σ상한 | 09-02 LTV 자문이 `overnight_stop_loss -1.5`/`trailing_stop_rate -0.8` 을 권고했는데, LTV 가 **프리장 청산 평가 보류 화이트리스트의 유일 전략**이라는 사실을 모르고 낸 값이다 |

#### C. payload 결손·오염

| # | 격차 | 심각도 | 근거 | 실측 |
|---|---|---|---|---|
| C1 | **사람 결정 로그가 전무**해, 의도적으로 결정된 라이브 값이 전부 "설정 오류"로 읽힌다 | **HIGH** | `user_payload` = `:328-345` 9키. 결정 이력 필드 0 | 범위 밖 라이브 값 4건(max_scan 4000 ×3전략, BFB retention 0). B4·B5 의 172+32회 권고가 전부 여기서 나온다 |
| C2 | **funnel 데이터가 payload 에 없어 "왜 안 샀는가"를 볼 수 없다** — P0-1(유령 키로 전 기간 체결 0)이 재발해도 자문은 똑같이 "임계가 빡빡하다"고 답할 배관 | **HIGH** | `recommendation_engine` 에 `strategy_funnel`/`log_reports` import 0건. 데이터는 이미 존재: `log_analysis_engine.py:749-822 _collect_strategy_funnel_stages`(단계별 생존 + verdict "후보준비완료/패턴희소/후보부족"), `:823-871 _collect_strategy_funnel`(signals/orders/fills), `src/db/strategy_funnel.py:143 list_snapshots`·`:187 list_recent_by_strategy`. 캡처 16:20 < 자문 20:00 | 자문이 스스로 이 데이터를 요청 중 — 09-02 VCP: "거래가 0건인 원인을 파악하기 위해 후보 종목 수, 각 필터 통과율, 돌파 신호 발생 수, 주문 거절·유동성 탈락 사유를 별도 진단 로그로 수집하는 것을 권고" |
| C3 | **자문 입력 metrics 가 08-18 비중 재배분 아티팩트로 오염**돼 있다 | **HIGH** | `src/db/daily_performance.py:38,:115` `daily_profit_rate = daily_realized_pnl / 직전 영업일 total_asset`. 08-18 에 비중 계약 시정으로 예산이 22~34배 재배분됐는데 분모가 직전일 | EC2 08-18: LTV total_asset 11,470→263,494, pnl −4,900 ⇒ rate **−42.72%**(당일 예산 기준 −1.86%) · VB −1,400/11,470 ⇒ **−12.21%**(실 −0.35%). `recommendation_metrics.py:165` 20행 복리 ⇒ LLM 이 본 LTV 누적 **−45.87%**(실 −6.36%)·VB **−15.89%**(실 −4.27%). 09-02 VCP weight_reasoning 이 두 수치를 peer 부진 근거로 인용. 20영업일 창이라 **~09-15 까지 잔류** |
| C4 | metrics 에 **RR·기대값·MFE/MAE·평균 보유기간·청산사유 분해가 없다** — 이 프로젝트가 내린 가장 중요한 튜닝 결정(cycle223)을 뒷받침한 수치가 payload 에 하나도 없다 | **HIGH** | `compute_metrics` 반환 16키(`recommendation_metrics.py:82-100`)에 RR/expectancy 없음 | cycle223 결정 근거 = MFE 대비 실현 −12% · RR 0.47 vs 손익분기 필요 2.25 · 이익보호 3층 발화 0회 — 어느 것도 산출되지 않는다. 결과: 08-10 이후 `recommended_weight` 진폭 kojiro 0.10~0.30(3배, 같은 기간 trades 21~29·승률 0.15~0.25) · VB 0.005~0.12(**24배**) · LTV 0.005~0.08(16배) · donchian 0.05~0.20(4배) |
| C5 | 과거 권고와 그 처분(applied/expired)이 재투입되지 않아 **기각된 조언이 무기한 재생산**된다 | MEDIUM | payload 에 이력 필드 0. `src/db/parameter_recommendations.py:99 list_recommendations(days)` 로 즉시 조회 가능한데 미사용 | 478건 status = expired 428(89.5%)/partial 28/applied 15(3.1%)/pending 7. **06-08 이후 applied 0 = 86일째 무적용**. BFB/VCP 는 최근 17일 중 15일이 `max_scan_stocks` **단 하나만** 제안 |
| C6 | 백테스트 되먹임이 write-only 이고, 게다가 **19일째 끊겨 있는데 경보가 없다** | MEDIUM | `:518` 자문 INSERT **이후** enqueue → `backtest_orchestration.py:509` DB 기록. payload 에 `backtest_summary` 키 없음. `:45-51 _SUPPORTED={momentum, VB, donchian}` / `_FALLBACK={LTV, BFB, VCP, kojiro}` 즉시 skipped | 08-18~20 "MCP 서버 응답 시간 초과(initialize)", 08-21~09-02 **11일 연속** "연결할 수 없습니다 … All connection attempts failed". `kis_mcp_enabled=True` 인데 무경보. 전 이력 349건 'set' 중 `total_trades>0` **0건**. **아웃오브샘플 증거가 가장 필요한 표본 0 전략(BFB/VCP/kojiro)이 정확히 미지원 집합** |
| C7 | D-1 `daily_log_reports` 를 읽지 않아 자문이 자기 시스템의 하루 요약을 한 번도 못 본다 | MEDIUM | `src/db/log_reports.py:84 get_log_report(target_date)` 존재, `recommendation_engine` 미참조. 리포트 metrics 에 api_metrics·strategy_funnel·strategy_funnel_stages·by_ticker_pnl·by_hour_pnl·next_day_clear 보유 | — |
| C8 | `sizing_mode`·`max_open_risk_pct`·`cash_usage_ratio` 가 payload 에 없다 — 터틀 ATR 유닛 사이징이 배선된 전략(donchian 라이브/kojiro/VCP/BFB)에 `position_ratio` 권고를 낼 때 그 의미가 다르다는 걸 자문이 모른다 | MEDIUM | payload 는 `strategy.config.params` 만 직렬화. `CLAUDE.md:142` 터틀 배선 · `:141` kojiro 삼중 한도 | `kojiro.max_open_risk_pct=4.5` 는 params 안이라 데이터로는 보이나 PARAM_RANGES 밖이라 논평 근거가 없다 |
| C9 | peer 비교가 **표본 게이트 없이** 배분 신호로 쓰여 전 전략 동시 감액(herding)을 만든다 | MEDIUM | `:338-339` peer_weights/peer_metrics + `:137`("다른 전략 weight + 성과를 함께 고려") — 최소 표본·기간 조건 없음 | 09-02 pending **7/7 전원**이 donchian(누적 +2.04%) 하나를 유일 양(+) 기준점으로 인용하며 자기 비중을 깎았다: momentum "승률 0%"(손절 2건) · VCP/BFB "거래 0건" · kojiro "승률 20%" · LTV "−45.87%"(← C3 오염값). 한 자릿수 표본의 상대 순위가 계좌 배분을 흔든다 |

#### D. 검증기 공백

| # | 격차 | 심각도 | 근거 | 실측 |
|---|---|---|---|---|
| D1 | **"라이브 값이 PARAM_RANGES 밖일 때"라는 개념이 검증기에 아예 없다** — 범위 안으로 끌어오는 '교정'을 정상 자문과 구분 없이 통과시킨다 | **HIGH** | `:196-216` 은 **추천값**만 `[lo,hi]` 로 검사하고 `current_params` 값이 범위 안인지 한 번도 보지 않는다. `:324-326` relevant_ranges 도 키 존재만 확인 | max_scan 500 은 범위 내부라 검증기·cycle223-F2 가드(`routes/recommendations.py:88`) **양쪽 다 통과** ⇒ UI 버튼 하나로 유니버스 87.5% 축소 |
| D2 | **표본 게이트가 없다** — `trades_count=0` 인 전략의 weight 권고가 그대로 저장된다 | **HIGH** | `:243-257` 은 `[0,1]` 범위만 본다 | 478행 중 425행(88.9%)이 weight 권고 동봉. VCP 는 trades=0 인 채 11일 연속 0.05 를 냈다 |
| D3 | 화이트리스트 밖 키 탈락이 `logger.debug` 라 `system_logs` 에 도달하지 않는다 — **"자문이 금지 키를 얼마나 제안하는가"를 측정할 수 없다**(개선 효과 측정 지표 부재) | MEDIUM | `:198`, `:201` debug / `:211` 범위 초과만 warning. 대조군: 적용 차단은 두 겹으로 관측됨(`routes/recommendations.py:90-95 [manual_apply_safeguard_skip]` + `recommendation_engine.py:640-648 [auto_apply_safeguard_skip]`) | 30일 `system_logs` WARNING 마커 `[manual_apply_safeguard_skip]`/`[weight_sum_violation]`/"추천 값 범위 초과"/"추천 거부" 전부 **0건**. 즉 **생성 차단은 0겹 관측** |
| D4 | 원본 LLM 응답이 어디에도 영속되지 않는다 | MEDIUM | `:378-384` 파싱 결과는 지역변수, `insert_recommendation(:495-507)` 은 검증 통과분만 저장 | 개선 전/후 비교의 기준선을 만들 수 없다 |
| D5 | **동결 창(freeze window) 개념이 시스템에 0개**다 — "이 키는 오늘 사람이 바꿨으니 N영업일 건드리지 마라"를 표현할 자리가 없다 | MEDIUM | `expire_pending_before(:417)` 은 어제 pending 만기 처리일 뿐. cycle228 N=10 표본 보호는 `CLAUDE.md` 산문에만 존재 | 오늘 07:40 완화가 정확히 이 창을 필요로 한다 |
| D6 | 수동 apply 경로에 `weight = 0.0` 하한 가드가 없다(B7 의 강제 측면) | MEDIUM | `routes/recommendations.py:194-209` 은 `float(recommended_weight)` 를 그대로 `save_weights` | auto_apply 의 50% cap 에 대응하는 수동 가드 부재 |

#### E. 출력 스키마 결손

| # | 격차 | 심각도 | 근거 | 실측 |
|---|---|---|---|---|
| E1 | **"사람 결정 필요 / 표본 부족 / 판단 보류"를 표현할 필드가 없다.** 5개 필드 전부가 실행 가능한 변경을 전제하므로 모델은 확신이 없어도 숫자를 내놓도록 강제된다 | **HIGH** | `:144-150` 스키마 = recommended_params/reasoning/recommended_weight/weight_reasoning/code_review_notes. 검증기 `:172-296` 도 이 5개만 파싱 | 전형적 과잉 산출: 09-02 LTV 단일 자문이 **14개 키**를 한꺼번에 갈아치우는 전면 재설계 제출(k_period·min_prdy_rate·position_ratio·k_value 3종·max_scan_stocks·daily_loss_limit·gap_up_threshold·min_trade_amount·intraday/overnight_stop_loss·trailing_stop_rate·exclude_consecutive_limit) |
| E2 | **가치 역전** — 실제로 유용한 산출은 전부 `code_review_notes` 산문인데 스키마상 4번째 부차 필드이고 UI 에서도 params 그리드 아래 | MEDIUM | `:142-143` 배치, `Recommendations.tsx:471-484` | 지난 2주 유용 산출 전량이 notes: 0건 원인 진단(08-31 BFB), 범위 불일치 지적, 그리고 정확히 옳은 처방(09-02 VCP: "**최소 거래 표본 확보 전에는 성과 기반 자동 튜닝을 실행하지 않는 안전장치**도 검토"). 같은 날들의 구조화 출력은 `{max_scan_stocks: 500}` 뿐 |
| E3 | "변경 없음"과 "판단 보류"가 구분되지 않는다(둘 다 빈 객체/null) | MEDIUM | `:136`("필요 없으면 빈 객체"), `:137`("변경 없으면 null") | 운영자가 침묵의 의미를 매일 육안 추정 |
| E4 | 권고에 **검증 방법·필요 표본**을 담을 자리가 없어, 자문이 "가설"을 낼 수 없고 "값"만 낼 수 있다 | MEDIUM | 스키마 전체 | 표본 유입 속도 실측 — BFB/VCP ≈0.5건/일, kojiro 30일 왕복 10~13건, donchian 13~15건, momentum 2건. **하루는 물론 주 단위로도 안 쌓이는데 프롬프트는 매일 4가지를 요구한다** |

---

### 3. 개선안

#### (a) 프롬프트 v2 — 교체본 전문 초안

설계 원칙 4가지:
1. **생성물이지 원본이 아니다** — 금지 목록·결정 로그·동결 창 블록은 §3(b)의 단일 정본에서 렌더링해 삽입한다. 프롬프트에 키 이름을 손으로 적지 않는다(사본 표류 차단).
2. **금지는 두 종류로 나눈다** — ⓐ 영구 봉인(정체성 상수) ⓑ 사람의 최근 결정(되돌리기 금지, 이의는 별도 필드로).
3. **목적함수를 명시한다** — 단조 조임 89.2% 래칫의 근인은 "단기 손실 최소화"가 암묵 목적함수였기 때문이다.
4. **판단 보류를 1급 출력으로 승격한다.**

```python
SYSTEM_PROMPT_V2 = f"""
너는 한국 주식 자동매매 시스템의 **파라미터 자문역**이다. 너는 코드를 직접 바꾸지 않는다.
네 출력은 운영자가 검토 후 수동으로 적용하며, 일부 필드는 자동 적용 경로에 연결될 수 있다.

## 0. 목적함수
단기 손실 최소화가 아니라 **기대값 = (승률 × 평균이익) − (패율 × 평균손실)** 의 개선이다.
- 손절·트레일링을 조이면 승률은 오르고 손익비(RR)는 떨어진다. RR 이 손익분기 아래로 내려가면
  조임은 개선이 아니라 열화다. 조임을 권고할 때는 반드시 RR 에 미치는 영향을 함께 적어라.
- 추세추종 전략(도치안·고지로·VCP·BFB)의 수익은 소수의 큰 이익 왕복에서 나온다.
  청산을 조이면 그 오른쪽 꼬리를 잘라 전략을 데이트레이딩으로 변질시킨다.
- 이 시스템의 자문 이력은 4개월간 조임:완화 = 1,370:166 (89.2%) 의 단조 편향을 보였다.
  너는 그 편향을 재생산하지 마라. 완화가 옳으면 완화를 권고하라.

## 1. 시스템 사실 (정본 — 아래 서술과 payload 값이 어긋나면 payload 가 정본)
{{SYSTEM_FACTS}}
<!-- 자동 주입 예시:
- 자산배분: 최종 종목당 매수금액 = 순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio.
  ⚠️ weight 는 **상대 비율**이다. 한 전략의 weight 를 낮추면 그 자금은 현금이 되지 않고
  나머지 전략으로 재배분된다. 계좌 전체 노출을 줄이는 레버는 cash_usage_ratio 이며 네 권고 대상이 아니다.
- weight = 0.0 은 축소가 아니라 **전략 비활성화**다(enabled=False 로 번역된다). 비활성화를 의도하지 않으면 0.0 을 쓰지 마라.
- 불변식: position_ratio × max_positions ≤ 1.0. max_positions 는 봉인 키다.
  현재 여유: {{PR_HEADROOM}} (여유 0 이면 position_ratio 증액은 자동 폐기된다).
- 사이징: {{SIZING_MODE}}. sizing_mode="turtle" 인 전략은 수량이 ATR 유닛으로 결정되므로
  position_ratio 는 상한(notional cap) 으로만 작동한다.
- 청산은 매수 보드 설정과 무관하게 항상 작동한다(tradable_boards 는 매수 진입 전용).
  단 프리장(08:00~09:00) 청산 평가 보류 화이트리스트 = {{PRE_MARKET_EXIT_WHITELIST}}.
- params 밖에서 매매를 지배하는 상수(네 권고 대상 아님, 해석에만 사용):
  {{MODULE_CONSTANTS}}  예) VB·momentum 매수 컷 15:20 · BFB 추격상한 5.0 / VCP 7.5
-->

## 2. 절대 금지 (권고 대상 아님 — 제안하면 자동 폐기되고 경고로 기록된다)
{{FROZEN_PARAMS_BLOCK}}
<!-- 자동 주입 예시:
- max_positions : 동시보유 슬롯 = 리스크 정체성 상수 (2026-08-03. 조합 사고: kojiro 10×0.20 / LTV 4×0.50 = 예산 200%)
- buy_threshold, donchian_period : 진입 임계 = 전략 정체성 (사이클 212)
- max_breakout_extension_pct : 추격 상한 (사이클 209 — 하한 과튜닝)
- atr_trail_mult, breakout_fail_n_days : 청산 = 보유기간 정체성 (사이클 223.
  근거 = 도치안 19왕복 실측 MFE 대비 실현 −12%, RR 0.47 vs 손익분기 2.25)
-->
이 키들에 대한 의견이 있으면 recommended_params 가 아니라 **needs_human_decision** 에 적어라.

## 3. 사람이 내린 결정 (라이브 값이 아래 param_ranges 밖일 수 있다 — 오류가 아니다)
{{DECISION_LOG_BLOCK}}
<!-- 자동 주입 예시:
- max_scan_stocks = 4000 (bull_flag_breakout / vcp_breakout / kojiro), 결정일 2026-08-08,
  사유: KRX 전체 유니버스(3,577종목) 스캔 확대. param_ranges 상한 500 은 이 결정 이전 값이다.
- breakout_retention_minutes = 0 (bull_flag_breakout), 결정일 2026-09-03,
  사유: 진입 완화 실험. 동결 창 종료 예정 {{FREEZE_UNTIL}}.
-->
**규칙:** 라이브 값이 param_ranges 밖이라는 사실 자체는 권고 근거가 될 수 없다.
"허용 범위를 초과하므로 상한값으로 조정한다" 류의 권고는 자동 폐기된다.
그 값이 매매 결과를 나쁘게 만든다는 **관측 증거**가 있을 때만, 그 증거를 명시하고 권고하라.
증거 없이 이의만 있으면 needs_human_decision 에 적어라.

## 4. 동결 창 (아래 키는 지정일까지 어떤 방향으로도 권고 금지)
{{FREEZE_WINDOW_BLOCK}}
<!-- 자동 주입 예시: bull_flag_breakout.breakout_retention_minutes — 2026-09-17 까지 동결
     (사유: 진입 완화 효과 관측 중. 표본 N=10 왕복 도달 전 재튜닝은 실험을 파괴한다) -->

## 5. 표본 규약 (가장 중요)
- 이 시스템의 표본 유입 속도는 전략당 하루 0~1 왕복이다. 파라미터·비중 결정에 필요한 표본은
  하루는 물론 주 단위로도 잘 쌓이지 않는다.
- **청산 왕복 표본(closed round trips)이 {{MIN_SAMPLE}} 미만이면 recommended_params 와
  recommended_weight 를 모두 null 로 두고, sample_status="insufficient" 로 답하라.**
  이때 네가 낼 가치 있는 출력은 숫자가 아니라 **가설 + 검증 방법 + 필요 표본**이다.
- "거래가 0건이라 검증되지 않았으므로 비중을 축소한다" 는 **금지된 추론**이다.
  거래 0건은 (a) 임계가 엄격 (b) 후보가 없음 (c) 배관 결함 — 셋을 구분하지 않고는 해석할 수 없다.
  payload 의 funnel 을 먼저 읽어라. funnel 이 "배관 결함/기록없음" 을 시사하면 비중이 아니라
  그 사실을 needs_human_decision 에 적어라. 비중을 깎으면 표본은 더 안 쌓인다.
- peer 비교로 비중을 조정하려면 **자신과 상대 양쪽 모두** 표본 문턱을 넘어야 한다.

## 6. 증거 사용
- payload 의 metrics 는 체결 결과다. funnel 은 체결 이전 단계다. 둘을 구분해 인용하라.
- past_recommendations 에 같은 권고가 이미 기각(expired/rejected)돼 있으면 그대로 반복하지 마라.
  반복하려면 **새 증거**를 제시하거나, 왜 여전히 유효한지 적어라.
- strategy_description(docstring)은 **설계 의도**이고 current_params 가 **현재 정본**이다.
  둘이 어긋나면 current_params 를 사실로 삼고, 어긋남 자체를 code_review_notes 에 지적하라.
- metrics 에 data_quality_notes 가 있으면 그 경고를 반영하라(오염 구간 수치를 근거로 쓰지 마라).

## 7. 출력 스키마 (이 JSON 만 사용)
{{
  "sample_status": "sufficient" | "insufficient" | "unknown",
  "recommended_params": {{"<key>": <number>, ...}},      // 없으면 {{}}
  "reasoning": "<2~4문장>",
  "recommended_weight": <number 0.0~1.0> | null,
  "weight_reasoning": "<최대 1000자>" | null,
  "hypotheses": [                                        // 표본 부족 시 여기가 주 산출물
    {{"claim": "<가설 한 문장>",
     "evidence": "<현재 관측 근거>",
     "test": "<무엇을 어떻게 보면 검증되는가>",
     "required_sample": <정수>,
     "confidence": <0.0~1.0>}}
  ],
  "needs_human_decision": [                              // 봉인 키·사람 결정에 대한 이의
    {{"topic": "<대상 키 또는 주제>",
     "issue": "<무엇이 문제인가>",
     "evidence": "<근거>",
     "options": ["<선택지1>", "<선택지2>"]}}
  ],
  "no_change_reason": "<변경을 권고하지 않는 이유>" | null,
  "code_review_notes": "<최대 2000자>" | null
}}

규칙:
- recommended_params 의 키는 payload 의 param_ranges 에 있는 키만 사용한다.
  param_ranges 에 없는 키(§2 금지 키 포함)를 쓰면 폐기된다.
- 변경이 필요 없으면 recommended_params={{}} + no_change_reason 을 채워라.
  판단을 보류하는 것과 변경이 불필요한 것은 다르다 — 전자는 sample_status="insufficient".
- 한 사이클에 권고하는 파라미터는 **최대 3키**로 제한한다. 동시에 여러 축을 바꾸면
  다음 사이클에 원인 귀속이 불가능해진다.
- 모든 수치 주장에는 근거가 되는 payload 필드명을 함께 적어라.
"""
```

**v1 대비 삭제/변경**
- 삭제: `:142` "PARAM_RANGES 화이트리스트 **외** 신규 파라미터 도입 또는 폐기 자유 텍스트 자문" — 이 문장이 금지 키 튜닝을 명시적으로 초대한다. `code_review_notes` 의 자유 자문 성격은 §7 에 보존하되 "화이트리스트 외 파라미터 제안"이라는 유인은 제거.
- 정정: `:138` "합계 1.0 정규화는 운영자 책임" → §1 의 상대 정규화 사실.
- 유지·축소: 레짐 섹션은 존치하되 "aggressive → position_ratio 확대 가능"(`:160`)을 삭제하고 "레짐은 관찰 지표이며 매수를 차단하지 않는다" 사실만 남긴다(B6 근인 제거).

#### (b) 단일 정본 설계 — 3안 비교 후 채택

| | A. 프롬프트 하드코딩 | **B. 중앙 상수 (채택)** | C. DB 정책 (system_config) |
|---|---|---|---|
| 강제력 | **0** (권고일 뿐) | 검증기·라우트가 같은 객체 참조 | 검증기 도달 가능하나 동기 계약 파괴 |
| 표류 | PARAM_RANGES 변경 시 조용히 어긋남 | AST 불변식으로 봉인 | DB 행은 **테스트를 깨지 않고 삭제**된다 |
| 배포 없이 변경 | 불가 | 불가 | **가능** |
| 접촉 규모 | src 1 파일 / 0.5 사이클 | src 2 + 테스트 5 / 1 사이클 | src 2 + migration / 0.5 사이클 |
| 8영역 diff | 0 | 0 | 0 |
| 치명적 약점 | D1·D2 그대로 잔존. "제외 결정이 한쪽 경로에만 걸리면 제외가 아니다"(`routes/recommendations.py:75-81`)의 재발 | 배포 없이 임시 동결 불가 | **영구 금지를 여기 두면 2026-08-08 kojiro DB 사각(운영자 직접 UPDATE 로 ratio×maxp=1.2)과 같은 클래스** |

**채택: B 를 정본, C 를 가산 전용 오버레이, A 는 B 로부터 생성.**

```
src/engine/advisor_policy.py   (신규 leaf — 8영역 밖, import 는 recommendation_engine / routes 만)
├── FROZEN_PARAMS: dict[str, str]              # key → 봉인 사유 (영구)
├── DECISION_LOG: tuple[Decision, ...]          # (strategy_id|None, key, value, decided_on, reason)
├── MIN_CLOSED_SAMPLE: int = 10                 # cycle228 N=10
├── MAX_KEYS_PER_CYCLE: int = 3
├── render_frozen_block() -> str                # 프롬프트 §2 생성
├── render_decision_block(live_params) -> str   # 프롬프트 §3 생성
├── render_freeze_block(today, overlay) -> str  # 프롬프트 §4 생성
└── active_freezes(today, overlay) -> dict[(sid,key), date]
```

- **불변식(AST 가드)**: `FROZEN_PARAMS.keys() & PARAM_RANGES.keys() == ∅`. 한쪽에만 추가하는 실수를 구조적으로 차단한다.
- **테스트 리터럴 회수**: `test_cycle212_ast_entry_threshold.py:28`·`test_cycle223_ast_donchian_exit_fix.py:45`·`test_cycle209_ast_extension_param_range.py:47`·`test_cycle228_ast_gate_guards.py:123`·`test_recommendation_param_ranges.py:225` 의 리터럴을 `FROZEN_PARAMS` 참조로 바꾼다. **단, 리터럴 자체는 각 테스트에 "자기검사"로 존치**한다 — 전부 참조로 바꾸면 누군가 `FROZEN_PARAMS` 를 비웠을 때 모든 가드가 공허하게 통과한다(cycle224·cycle226 에서 두 번 겪은 자기 가드 공허화의 정확한 재발 형태).
- **C 오버레이 규약**: `system_config["advisor_policy"]` JSON 은 **가산만** 가능하다 — 실효 금지 집합 = `FROZEN_PARAMS ∪ overlay.frozen`, 실효 동결 = `DECISION_LOG freeze ∪ overlay.freeze`. 오버레이가 코드 정본을 **약화시킬 수 없다**는 규칙 자체를 AST 로 봉인한다(`|` 만 사용, `-`/`difference` 금지). 용도는 "오늘 밤부터 이 키 5영업일 동결" 같은 배포 없는 임시 조치 하나뿐이다.
- **동기 계약 보존**: `_validate_recommendations` 는 DB 를 읽지 않는 동기 순수함수다(`:172-176`). 오버레이는 `generate_recommendations` 의 peer 수집 블록(`:434-437`) 직후에 **루프 밖 1회** 해석해 키워드 인자로 주입한다. 여기서 `await` 를 하면 호출부와 기존 테스트 4파일(28곳 이상)이 전부 async 파급된다.

#### (c) 검증기 · auto_apply · 수동 apply 변경점

**C-1. `_validate_recommendations` 시그니처 (동기 유지)**
```python
def _validate_recommendations(
    raw: dict,
    current_params: dict,
    *,
    strategy_id: str | None = None,
    metrics: dict | None = None,
    frozen: Mapping[str, str] = FROZEN_PARAMS,
    freezes: Mapping[tuple[str, str], date] | None = None,
    today: date | None = None,
) -> tuple[dict, str, float | None, str | None, str | None, dict]:   # ← 6번째 = 거부 원장
```
기본값을 둬서 기존 호출부·테스트가 그대로 통과한다(회귀 파급 0).

**C-2. 신규 거부 사유 4종 (전부 WARNING + `system_logs` 마커 — D3 시정)**

| 마커 | 조건 | 처리 |
|---|---|---|
| `[advisor_frozen_key_reject]` | `key in FROZEN_PARAMS` | 키 폐기 + 사유 문자열 동반 |
| `[advisor_range_pull_reject]` | 추천값은 범위 내인데 **`current_params[key]` 가 범위 밖** | 키 폐기 — "네 라이브 값이 내 허용창 밖" 이 유일 근거인 권고는 자문이 아니라 클램프 산출물이다. **이 한 줄이 max_scan 172회와 오늘 밤 retention 교정을 동시에 차단한다** |
| `[advisor_freeze_window_reject]` | `(sid, key)` 가 동결 창 안 | 키 폐기 + 해제일 병기 |
| `[advisor_sample_gate]` | 청산 왕복 표본 < `MIN_CLOSED_SAMPLE` | `recommended_weight` 를 **None 으로 강등**하고 `weight_reasoning` 보존(운영자가 근거는 읽되 적용은 못 하도록). params 는 폐기하지 않음(진입 임계 실험은 표본 이전에도 의미가 있다) |

⚠️ **강등이지 삭제가 아니다** — 자문 본문(reasoning/notes)은 그대로 저장한다. 렌즈 4가 확인한 대로 이 시스템에서 가장 유용한 산출은 산문이므로, 숫자를 막되 문장을 지우면 안 된다.

**C-3. 거부 원장 영속(D4 시정)** — 6번째 반환값 `rejected: {key: reason}` 을 `insert_recommendation` 에 넘겨 `parameter_recommendations` 신규 컬럼(또는 기존 metrics JSONB 하위 키 `advisor_rejections`)에 저장한다. 이것이 개선 효과 측정의 분자다: "금지 키 제안 건수 / 자문 건수"가 v2 배포 전후로 어떻게 변하는지.

**C-4. `auto_apply_recommendations`**
- docstring 정정(A2) — `_CONSERVATIVE_KEYS` 가 빈 집합이므로 params 자동 적용이 **없다**는 사실 명기. `:636-658` 死코드는 **삭제하지 않는다**(cycle210 의 의도적 봉인 형태를 보존하고, 삭제하면 나중에 누군가 다른 형태로 되살릴 유인이 생긴다). 대신 `assert not _CONSERVATIVE_KEYS` 성격의 회귀 가드를 추가해 "비어 있음"을 계약화한다.
- weight 감액 경로에도 표본 게이트 적용(C-2 와 동일 정본) — 토글이 켜졌을 때 "표본 0 → 감액" 래칫만 자동 발화하는 잠복(B8)을 여기서 닫는다.

**C-5. `routes/recommendations.py` 수동 apply (cycle223-F2 미러)**
- `valid_keys` 산출(`:88`) 직후 **같은 정본**으로 `FROZEN` + 범위-끌어당김 + 동결 창 재검사. 마커는 기존 `[manual_apply_safeguard_skip]` 계열을 유지하되 `reason=` 을 4종으로 분기.
- `weight = 0.0` 적용 시 확인 요구(D6) — `ApplyRequest` 에 명시 플래그가 없으면 "0.0 은 전략 비활성화입니다" 로 `success=False`. auto_apply 의 50% cap 에 대응하는 수동 가드.
- **감액 복구 경로는 계속 무조건 통과**(`:140` 규약 보존) — Σ 오염 상태에서 감액이 유일한 복구 수단이라는 N1 계약을 깨지 않는다.

#### (d) payload 추가 필드

| 필드 | 소스 (이미 존재) | 닫는 격차 | 비고 |
|---|---|---|---|
| `frozen_params` | `advisor_policy.FROZEN_PARAMS` | B1·B2 | key → 사유. **프롬프트와 payload 양쪽에** 실어 중복 고지 |
| `decision_log` | `advisor_policy.DECISION_LOG` (라이브 값 필터링) | C1·B4·B5 | 범위 밖 라이브 값에 결정일·사유를 붙여 "오류 아님" 을 못박는다 |
| `active_freezes` | `advisor_policy.active_freezes(today, overlay)` | D5 | `{(sid,key): 해제일}` |
| `funnel` | `src/db/strategy_funnel.py:143 list_snapshots` / `:187 list_recent_by_strategy`, 또는 `log_reports.get_log_report(D-1).metrics.strategy_funnel_stages` | **C2** | 단계별 생존 수 + `verdict`(후보준비완료/패턴희소/후보부족/기록없음) + drop_step. **"체결 0"의 원인 분해가 여기서만 가능하다** |
| `past_recommendations` | `parameter_recommendations.list_recommendations(days=14)` | C5 | `[{date, keys, weight, status}]` 요약만(전문 금지 — 토큰). 기각된 조언 재생산 차단 |
| `backtest_summary` | `parameter_recommendations` 기존 컬럼(D-1 행) | C6 | **선행조건 = MCP 서버 복구**(11일 다운). 복구 전에는 `{"status":"unavailable","since":"2026-08-18"}` 로 **명시**해 자문이 "없음"과 "고장"을 구분하게 한다 |
| `metrics.data_quality_notes` | 신규 계산 (08-18 이상치 탐지) | **C3** | `daily_profit_rate` 절대값이 임계 초과 + 같은 날 `total_asset` 이 배수 점프 → "재배분 아티팩트 의심, 근거로 쓰지 마라". **오염 데이터를 조용히 고치지 말고 시끄럽게 표시**(비중 단위 계약 사이클의 교훈 — 추론 보정은 결함 은폐 장치다) |
| `metrics.rr` / `expectancy` / `avg_hold_days` / `exit_reason_breakdown` | `trade_history` 기존 데이터에서 파생 | **C4** | RR = 평균이익/|평균손실|, 기대값 = 승률×평균이익 − 패율×평균손실. cycle223 을 결정지은 축 |
| `sample` | `{closed_round_trips, analyzed_days, min_required}` | B3·D2 | 표본 규약의 판정 근거를 payload 에 명시 |
| `strategy_facts` | `{sizing_mode, max_open_risk_pct, tradable_boards, buy_cutoff, extension_cap, pre_market_exit_eval}` | C8·B9 | params 밖 모듈 상수를 **읽기 전용 사실**로 전달 |
| `account` | `{cash_usage_ratio, weight_sum, normalization: "relative"}` | A1 | weight 의미론을 데이터로도 뒷받침 |

**토큰 예산 주의** — payload 가 커지면 비용보다 *주의 분산*이 문제다. `past_recommendations` 는 14일 요약, `funnel` 은 최근 3영업일, `peer_metrics` 는 현행 유지. 현 비용 대리 지표는 20:10 로그 분석 8.8k 토큰·$0.019/일이므로 자문 7콜/일은 월 $2~5 규모로 추정된다(단 `parameter_recommendations` 에는 token/latency/cost 컬럼이 없어 실측 불가 — `daily_log_reports` 는 migration 031 로 5컬럼 보유. **이 관측 비대칭 자체가 후속 항목**).

#### (e) 프론트 표시

`frontend/src/pages/Recommendations.tsx` — 판단 근거를 카드 상단으로 끌어올린다.

| 배지 | 조건 | 색 |
|---|---|---|
| `봉인 충돌` | `advisor_rejections` 에 `frozen_key` 존재 | 적 |
| `범위 끌어당김` | `advisor_rejections` 에 `range_pull` 존재 | 적 |
| `동결 창` | `freeze_window` 존재 | 황 |
| `표본 부족` | `sample_status="insufficient"` 또는 `sample_gate` 강등 | 황 |
| `사람 결정 필요` | `needs_human_decision` 비어있지 않음 | 청 (알림 성격) |
| `변경 없음` | `recommended_params={}` ∧ `no_change_reason` | 회 |

- `code_review_notes`(`:471-484`)와 `hypotheses`/`needs_human_decision` 을 **params 그리드 위**로 이동(E2 가치 역전 시정).
- weight 적용 버튼에 정규화 결과 미리보기 — "적용 시 Σ=0.64 → 실효 배분: donchian 31.3%(+16.3%p)". A1 을 운영자 화면에서도 닫는다.
- `weight = 0.0` 체크 시 별도 확인 다이얼로그("전략이 비활성화됩니다").

---

### 4. 롤아웃

**전 사이클 공통: 8영역(`src/engine/risk.py`·`order_engine.py`·`scanner.py`·`session.py`·`strategy_registry.py`·`src/api/order.py`·`src/realtime`·`src/auth`) diff 0.** 접촉 파일은 `recommendation_engine.py`·신규 `advisor_policy.py`·`routes/recommendations.py`·`recommendation_metrics.py`·프론트 — `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py:196-205` 의 `_EIGHT_AREAS` 어디에도 없다. **매매 hot path 무접촉**(자문은 20:00 배치 경로).

#### 사이클 1 — 정본 + 검증기 (권고: 오늘 장 마감 후 착수, 오늘 밤 자문 전 배포 가능하면 최선)
- 신규 `src/engine/advisor_policy.py`(FROZEN_PARAMS·DECISION_LOG·MIN_CLOSED_SAMPLE·렌더러 3)
- `_validate_recommendations` 키워드 주입 + 거부 4종 + 거부 원장 반환
- 프롬프트 v2 §0~§4 + §7 스키마(§5 표본 규약 포함) 적용, `:142` 삭제, `:138`·`:160` 정정
- 수동 apply 라우트 미러 + weight 0.0 가드
- AST 불변식 `FROZEN_PARAMS ∩ PARAM_RANGES = ∅` + 테스트 리터럴 회수(자기검사 존치)
- **회귀 가드**: 범위-끌어당김 거부(max_scan 4000→500 시나리오 실측 재현) · 봉인 키 거부 · 동결 창 거부 · 표본 게이트 강등(문장 보존 확인) · 마커 4종 `system_logs` 도달 · 기본 인자 미주입 시 기존 행위 동일(회귀 0) · 오버레이 가산 전용
- **뮤테이션 실증**: 거부 가드 제거 → FAIL, `FROZEN_PARAMS` 비우기 → 자기검사 FAIL, 오버레이에 `-` 도입 → AST FAIL
- 예상: src +250~350L, 신규 회귀 ~35

#### 사이클 2 — payload 확장 + metrics 정합
- `funnel`·`decision_log`·`past_recommendations`·`strategy_facts`·`account`·`sample` 주입
- `metrics` 파생 지표 4종(RR·기대값·평균보유일·청산사유 분해) + `data_quality_notes`(08-18 오염 표시)
- D-1 `daily_log_reports` 요약 주입
- **회귀 가드**: payload 키 존재/부재 graceful(funnel DB 실패 시 `{}` 로 자문 계속) · 오염 탐지 순수함수 · RR 계산 경계(손실 0건·이익 0건)
- 예상: src +200L, 신규 회귀 ~30

#### 사이클 3 — 출력 스키마 v2 + 프론트
- `sample_status`·`hypotheses`·`needs_human_decision`·`no_change_reason` 파싱·저장(DB 컬럼 또는 JSONB)
- 프론트 배지 6종 + notes/hypotheses 상단 이동 + 정규화 미리보기 + weight 0 확인
- **회귀 가드**: 구 스키마 응답 하위호환(신규 필드 없어도 자문 저장 성공) · 배지 조건 · MSW/Playwright 픽스처 동기화
- 예상: src +150L / 프론트 +200L, 신규 회귀 ~25(백+프론트)

#### 관측 판독 (배포 후 D+1~D+5)
1. `[advisor_range_pull_reject]` 발화 — **BFB retention·max_scan 3전략에서 매일 발화해야 정상**. 0이면 가드가 공허하다.
2. `[advisor_frozen_key_reject]` 발화 빈도 = 프롬프트 v2 의 효과 측정 분자. 시간이 지나며 감소해야 한다(프롬프트가 읽히고 있다는 신호).
3. `sample_status="insufficient"` 비율 — BFB/VCP 가 여기 들어가야 정상.
4. `recommended_weight` 가 null 인 자문 비율 — 현재 88.9%가 weight 를 낸다. 표본 게이트 후 급감해야 한다.
5. `hypotheses` 품질 — 검증 가능한 형태인지 육안 검수 3일.

---

### 5. 사용자 결정 필요 항목

| # | 결정 | 선택지 | team-leader 권고 |
|---|---|---|---|
| **1** | `max_scan_stocks` 범위 모순(라이브 4000 vs 상한 500). 172회 권고의 근원 | (a) 범위 상한을 4000~5000 으로 상향 (b) 봉인 키로 편입(유니버스 규모는 사람 결정) (c) 현행 유지 + 범위-끌어당김 가드만 | **(b) 봉인 편입.** 유니버스 규모는 전략 파라미터가 아니라 시스템 용량·구독 압력(MAX_SUBSCRIPTIONS=41, 메인 헤드룸)과 결합된 **운영 결정**이다. (a)는 튜닝 대상으로 남겨 다음 이탈을 부른다 |
| **2** | BFB `breakout_retention_minutes = 0`(오늘 07:40 적용, 범위 (1,30) 밖) | (a) 범위 하한을 0 으로 내려 정합 (b) 결정 로그 + 동결 창 N영업일(권고 10) (c) 봉인 편입 | **(b) 동결 창.** 이건 진행 중 실험이므로 값을 영구 고정하는 (c)는 과잉이고, (a)만 하면 다음 사이클에 다시 3으로 끌려간다. 동결 해제일은 **N=10 왕복 도달 또는 2주 중 늦은 쪽** |
| **3** | 자문 주기·형식 | (a) 현행 유지(매일 7전략 × 4산출) (b) **축 분리** — 일간=관측 브리핑(숫자 금지)·주간=표본 문턱 넘은 전략만 숫자·월간=비중 (c) 격일 | 렌즈 4 권고는 (b). **단 사이클 3 이후로 미룬다** — 표본 게이트(사이클 1)가 들어가면 자동으로 "표본 있는 전략만 숫자"가 되므로, 주기까지 동시에 바꾸면 D+1 귀인이 불가능하다 |
| **4** | 표본 문턱 값 | (a) N=10 왕복(cycle228 선례) (b) N=20 (c) 전략별 차등 | **(a) N=10 단일값**으로 시작. 전략별 차등은 튜닝 가능한 축을 또 하나 만드는 일이라 표본이 쌓인 뒤 재검토 |
| **5** | 08-18 metrics 오염(LTV −45.87% vs 실 −6.36%) | (a) 자문 입력에서 08-18 행 제외 (b) `data_quality_notes` 로 표시만 하고 09-15 자연 소멸 대기 (c) `daily_performance` 재계산 | **(b) 표시 + 대기.** (a)는 조용한 보정이라 비중 단위 계약 사이클의 금기("추론 분기는 결함이 아니라 결함 은폐 장치")에 걸린다. (c)는 대시보드 TWR 까지 건드리는 별건 — **단 `cumulative_return_rate` TWR 컬럼 오염 여부는 별도 확인 필요** |
| **6** | 백테스트 MCP 서버(11일 다운, `kis_mcp_enabled=True`, 무경보) | (a) 서버 복구 (b) 토글 OFF + 자문에 "unavailable" 명시 (c) 방치 | **(b) 를 즉시, (a) 를 후속.** 지금은 매일 6 job 이 실패하며 조용히 쌓인다. 최소한 **다운 경보**는 필요하다. 참고로 전 이력 349건 중 유의 결과 0건이라 복구 편익 자체가 미검증 |
| **7** | `auto_apply` 처분 | (a) 현행(토글 부재로 비활성) 유지 (b) 표본 게이트 얹고 유지 (c) 경로 자체 제거 | **(b).** 제거는 되살릴 유인을 남기고, 방치는 잠복이다. 게이트를 얹어 "켜도 안전한 상태"로 만든 뒤 토글은 계속 끈 채 둔다 |
| **9** | (동시 진행 중인 cycle242 관련) 신규 키 `max_lot_units` 의 자문 노출 — `DEFAULT_PARAMS` 에 들어가면 `current_params` 로 payload 에 실리는데 `PARAM_RANGES` 에는 없으므로, 오늘 지적한 "값은 보이는데 금지 표시는 없는" 상태(B1)가 하나 더 생긴다 | (a) `FROZEN_PARAMS` 에 최초 편입(피라미딩 유닛 상한 = 리스크 정체성 상수) (b) 표본 축적 후 재판정 | **(a).** 사이클 1 의 `FROZEN_PARAMS` 초기 시드에 함께 넣으면 비용 0 이다. cycle242 배포와 무관하게 정본 쪽만 준비해두면 된다 (⚠️ 본 항목은 다른 워크플로의 진행 중 작업에 대한 관찰이며, 그 사이클의 설계 판단을 대신하지 않는다) |
| **8** | 사이클 1 착수 시점 | (a) 오늘 장 마감 후 즉시(오늘 밤 20:00 자문 전 배포 목표) (b) 내일 정규 사이클 | **(a) 권고하되 (b) 도 허용.** auto_apply 비활성이라 자동 유입 위험이 없으므로 긴급성은 낮다. 다만 **보유 포지션이 있으면 KRX 메인 시간 push 금지**(cycle232 D6) — 배포는 15:30 이후 NXT 애프터 창에서 |

---

### 부록 — 오늘 밤(09-03) 20:00 자문 예상

가드 없이 그대로 돌면 다음이 재현될 것으로 예상한다(전부 이력 기반):
1. BFB `breakout_retention_minutes: 0 → 1~3` (범위 하한 끌어당김. 09-01 에 이미 `3` 권고 선례)
2. BFB/VCP/kojiro `max_scan_stocks: 4000 → 500` (09-02 까지 17 자문일 연속 — 오늘이 18일째가 된다)
3. BFB/VCP `recommended_weight` 추가 감액 (거래 0건 논리 — 오늘 완화의 대상 전략)
4. donchian/LTV/VB 손절·`daily_loss_limit` 조임 (30일 창에서 21/21일 연속)

**전부 적용하지 말 것.** 특히 1·2 는 오늘 오전 사람이 내린 결정과 08-08 결정을 되돌리는 것이다. 3 은 완화 실험의 표본 형성을 자금 측면에서 방해한다.

---

# 부록 — 비판 반영표 (29건)

- 렌즈 2종(엔지니어링 14 · 트레이딩 15). 각 지적을 **소스·테스트·EC2 로 독립 대조**한 뒤 처분했다.
- 처분: **채택 27 · 부분 채택 2 · 기각 0**(부분 채택 2건 안에 하위 기각 각 1). 사실 오류로 반려한 지적은 없다.
- "대조" 열 = team-leader 가 실제로 확인한 것. 인용만 옮긴 항목은 없다.

## 엔지니어링 렌즈

| # | 심각도 | 지적 요지 | 대조 결과 | 처분 | 반영 위치 |
|---|---|---|---|---|---|
| E1 | HIGH | C-1 의 6-tuple 전환 + "회귀 파급 0" 은 거짓. 33곳이 5-tuple 언팩. 정작 핵심 가드는 시그니처 변경 불필요 | **확증** — `= _validate_recommendations(` **33건**(grep), `assert len(result) == 5` **3건**(weight_reasoning:27 · weights:127,158). `:209 lo, hi = PARAM_RANGES[key]` 가 루프 스코프 안임도 확인 | **채택** | F.1-1 · F.3.2 (`sink` out-parameter, 5-tuple 유지) |
| E2 | HIGH | 결정 #1(b) 봉인은 과제거 가드 4 + `INT_PARAMS ⊆ PARAM_RANGES` 2 를 깨고, 전역 범위라 정상 전략의 튜닝까지 봉인 | **확증** — `INT_PARAMS` 에 `max_scan_stocks` 포함(`:120-131`, 주석이 ⊆ 규약 명문화) · 열거 가드 `test_cycle212_…:83,96` · `test_cycle223_…:124,137` · 불변식 `:108`·`:145` · 라이브 값 donchian 400 / VB·LTV 100(EC2) | **채택** | F.1-4 · 결정 #1 (b)→(c) |
| E3 | HIGH | `[advisor_range_pull_reject]` 판정축이 과광범 — 안전 방향 교정 권고까지 삼킨다. 축은 DECISION_LOG 멤버십이어야 | **확증** — 검증기는 reasoning 을 읽지 않으므로(`:196-216` 전수) 프롬프트 §3 단서를 강제할 수단 없음 | **채택** | F.0 · F.1-3 · F.3.2 (`[advisor_decision_reject]` + `[advisor_live_out_of_range]` 분리) |
| E4 | HIGH | 표본 게이트의 데이터 소스가 사이클 2 에 있고 결손 시 fail 방향 미규정 | **확증** — `compute_metrics` docstring 반환 **16키**에 `closed_round_trips` 부재(`recommendation_metrics.py:78-100`) · `:422-424` → `:445` 조용한 `{}` 경로 | **채택** | F.1-5 · 사이클 A 로 이동 + fail-closed |
| E5 | MEDIUM | 프롬프트 v2 초안은 이중 중괄호로 렌더 불가. 전략별·날짜별 값이라 상수가 아니라 함수여야. 기존 단언 4건 파급 | **확증** — `test_regime_observation_honesty.py:126,136` · `test_recommendation_market_regime_payload.py:341-351` 이 `SYSTEM_PROMPT` 모듈 속성 참조 | **채택** | F.3.6 (`SYSTEM_PROMPT_BASE` + `build_system_prompt()`) |
| E6 | MEDIUM | 30초 하드 타임아웃 · 계측 0 상태에서 프롬프트/출력 3배 확장. 타임아웃 시 **빈 자문 INSERT** | **확증** — `:461-473` `wait_for(timeout=30)` → `raw = {}` → `:502` INSERT, 흔적은 `logger.warning` 1줄 | **채택(강화)** — 계측을 프롬프트 v2 **앞 사이클**로 당김 | F.3.5 계측 · 사이클 B |
| E7 | MEDIUM | payload 확장이 키 완전일치 단언을 깬다. 회귀 목록에 적응 누락 | **확증** — `test_recommendation_market_regime_payload.py:391,392` | **채택** | 사이클 B "기존 수정" |
| E8 | MEDIUM | 거부 원장을 `metrics` JSONB 에 넣으면 "LLM 이 본 입력의 기록" 성질이 소멸. 접촉 파일 누락 | **확증** — `parameter_recommendations.py:37,71` 이 `compute_metrics` 결과를 그대로 저장 · `pg_harness.py:117` glob 확인 | **채택** | F.3.7 (migration 042 신규 컬럼 + 누락 6파일) |
| E9 | MEDIUM | 정본 입도 자기모순(전역 dict vs (sid,key)) + ∅ 불변식이 약함. 침묵의 제3범주 124 키슬롯 | **확증(자체 실측)** — AST 로 **124** 산출, 비판이 제시한 전략별 수치와 완전 일치. `:87-104` 주석 + `test_cycle223f_…:185-190`(G-223F-8) 확인 | **채택** | F.3.1 (스코프 + `UNCLASSIFIED` + 강한 불변식) · 결정 #10 신규 |
| E10 | MEDIUM | v2 는 문제를 제조하는 payload 구조를 그대로 두고 산문만 고친다 | **확증** — `:328-345` `"current_params": current_params` 전량 | **채택** | F.3.5 4분할(`tunable`/`frozen`/`decided`/`readonly`) |
| E11 | MEDIUM | 수동 apply 미러가 G-223F-1/2 와 충돌. 형태를 맞춰도 **틀린 사유**를 반환 | **확증** — `test_cycle223f_…:48-56,58-75`(첫 대입에서 return) · `routes/recommendations.py:106-116` 무조건 "전략 정체성 상수" 문구 | **채택** | F.3.4 (후속 축소 대입 + 사유별 분기) |
| E12 | LOW | D3 의 "생성 차단 0겹 관측" 은 과장 — `logger.warning` 은 이미 `system_logs` 도달. 진짜 무관측은 debug 3경로. 마커는 500ms dedupe 를 넘도록 strategy 포함 필수 | **확증** — `main.py:161-201 _DbLogHandler`(`src.` prefix + INFO 컷) · `:177-186` 동일 문자열 500ms skip | **채택(원안 근거 문장 정정)** | F.3.2 마커 서식 규약 |
| E13 | LOW | DECISION_LOG 항목이 해제 불가능한 영구 방패. 오버레이는 가산 전용이라 걷어낼 수도 없다 | **확증** — 원안 §3(b) 규약이 `|` 만 허용 | **채택** | F.3.1 불변식 4 (`review_by` 필수 + `[advisor_decision_stale]`) |
| E14 | LOW | 사이클 추정 낙관적. 결정 #8(a) 오늘 밤 배포는 현 범위로 도달 불가 | **확증** — 사이클 A 수정 대상 실측 8~10파일(33+3+4+4+2). 프론트 사이클은 MSW/Playwright 미계상 | **채택** | F.4 (A 1.5 · D 1.5) · 결정 #9 (a)→(b) |

## 트레이딩 렌즈

| # | 심각도 | 지적 요지 | 대조 결과 | 처분 | 반영 위치 |
|---|---|---|---|---|---|
| T1 | HIGH | 프롬프트 §5(params 도 null)와 검증기 C-2(params 폐기 안 함)가 정면 충돌하고 넓은 쪽이 이겨 BFB·VCP·momentum 파라미터 자문이 소멸 | **확증(EC2 재실측)** — 30일 청산 BFB **0** · VCP **0** · momentum 2 · VB 34 · LTV 15 · donchian 13 · kojiro 10. 90일에도 BFB/VCP 0 | **채택** | F.3.6 §5 개정(weight 만) + 근거 등급 · 결정 #4 축 분리 |
| T2 | HIGH | `[advisor_frozen_key_reject]` 는 ∅ 불변식 때문에 도달 불가한 데다 발화량 실측 0. 관측 판독 #2 는 태어날 때부터 공허 | **확증(전수 실측)** — 봉인 6키 `recommended_params` 출현 08-21 이전 **212** / 이후 **0**. 검증기 순서 `:196 → :200` 확인 | **채택** | F.2② · F.3.2 검사 순서 명시 · 관측 판독 #2 교체(산문 언급 빈도) |
| T3 | HIGH | 동결 창 설계(날짜)·결정표(N=10 또는 2주)·cycle228 원본이 서로 다른 세 물건. anchor 로 쓸 `updated_at` 은 행 단위 | **확증** — EC2 `strategy_config.updated_at`: BFB/VCP 2026-09-02 22:40:43Z, 나머지 5 = 08-18. 키 단위 이력 부재 확인 | **채택** | F.1-6 · F.3.1 `Freeze.release` 이중 조건 + 비동기 평가 |
| T4 | HIGH | 반대 통로 3중 폐색 — 소비자 부재 · catch-22 · `:142` 삭제가 가장 유용한 산출의 원천 제거 | **확증** — `:142` 원문 확인, `needs_human_decision` 소비자 0. 적용 15/478 · 06-08 이후 0건 | **부분 채택** — 소비자(`[advisor_dissent]`+20:10 편입)·근거 등급·catch-22 해소는 **채택**. 단 "`:142` 원문 복원" 은 **하위 기각** — 그 문장의 *자유 자문* 역할만 `code_review_notes` 항목으로 이관하고, *화이트리스트 외 파라미터 제안* 유인은 제거한다(둘은 분리 가능하다) | F.3.6 `:142` 행 · F.3.7 |
| T5 | HIGH | §0 탈편향 지시가 사이클 1 시점에 없는 RR 을 근거로 요구. 완화는 고정 명목 전략에서 fail-safe 아님 | **확증** — `compute_metrics` 16키에 RR/expectancy 부재. CLAUDE.md 자금관리상 터틀 배선 = donchian·kojiro·VCP·BFB(VB·LTV 제외) | **채택** | F.1-2 순서 반전 · F.3.6 §0 개정(편향 비율 미인용 + 사이징 모드 확인) |
| T6 | HIGH | 제3 쓰기 경로 `PUT /api/strategies/{id}/params` 에 검증·감사 0. DECISION_LOG 는 UI 클릭 한 번에 스테일 | **확증** — `routes/strategies.py:168-187` 전문 확인(`PARAM_RANGES` 0 · logger 0), caller `Settings.tsx:67,513` | **부분 채택** — `[param_change]` 감사 마커 2경로는 **채택**(사이클 A 신규 편입). 단 "DECISION_LOG 를 로그에서 **파생**" 은 **하위 기각** — 로그 라인은 *사유* 를 담을 수 없다. 대신 3중 탐지로 스테일을 시끄럽게 만든다 | F.1-8 · F.3.3 · 결정 #6 신규 |
| T7 | MEDIUM | 결정 #1(b) 채택이 관측 판독 #1 을 자가 붕괴시킨다(봉인하면 range_pull 미발화) | **확증** — 범위 밖 라이브 값 실측 **4쌍**뿐 확인 | **채택** | F.1-4 (E2 와 수렴) · 관측 판독 #1 개정 |
| T8 | MEDIUM | `weight=None` + reasoning 보존은 기존 짝 계약의 위반. 전용 테스트가 봉인 | **확증** — `:275-276` "weight 가 null 이면 weight_reasoning 도 무조건 null" · `test_recommendation_weight_reasoning.py:88-101,220` · `test_recommendation_weights.py:146` · 하류 `routes/recommendations.py:104-109` | **채택** | F.1-5 · F.3.2 `withheld_weight`/`withheld_reason` 신설 |
| T9 | MEDIUM | 게이트 지표 미정의 + `metrics=None` 기본값이 fail-open 이고 회귀 목록이 그 우회를 계약으로 굳힌다. 대리 지표도 편향 | **확증** — `trades_count` = buy+sell 합 · `win_count+loss_count` 는 PARTIAL 에서 과대 | **채택** | 사이클 A `closed_round_trips` 정의 명시 + fail-closed |
| T10 | MEDIUM | 사이클 1 프롬프트가 사이클 2 필드를 근거로 지시(댕글링 4종). 단독 배포 시 없는 필드 조작 유인 | **확증** — v2 초안 §5·§6·§0 의 funnel·past_recommendations·data_quality_notes·RR 이 전부 사이클 2 항목 | **채택** | F.1-2 순서 반전(A 는 프롬프트 무변경) |
| T11 | MEDIUM | "비중을 깎으면 표본이 안 쌓인다" 는 이 코드베이스에서 거짓. 깊은 축소는 1주 폴백으로 밀어 리스크를 오히려 키운다 | **확증** — `strategy_base.py:450-464 _fallback_one_share`("잔여 ≥ 현재가면 1주") + `:475,497` 위임 경로 확인. cycle242 가 지금 그 결함을 시정 중 | **채택** | F.3.6 §5 문구 교체 |
| T12 | MEDIUM | 평면 FROZEN + ∅ 불변식이 cycle223 의 전략별 재검토 조항을 구조적으로 삭제 → 잠정 결정이 영구 결정으로 승격 | **확증** — `:87-104` 주석 원문 + G-223F-8 핀 | **채택** | F.3.1 스코프 + `review_when` 필수 (E9 와 수렴) |
| T13 | LOW | `hypotheses` 는 소비자·마감·중복 제어가 없는 새 write-only 채널. `confidence` 는 미교정 숫자 | **확증** — §6 반복 금지가 `past_recommendations` 에만 걸림. BFB `required_sample=10` 도달 두 달 이상(체결 0 실측) | **채택** | F.3.7 (`confidence` 제거 · `claim_hash` dedupe · 도달일 배지) |
| T14 | LOW | 오늘 밤 배포 권고가 자체 증거와 어긋나고 cycle242 미커밋 변경 동반 출하 위험 | **확증** — 09-02 7건 전부 `rejected`(EC2) · `auto_apply_enabled` 키 부재(EC2 전수) · 워킹트리 5파일 | **채택** | F.1-9 · F.7 · 결정 #9 |
| T15 | LOW | 프롬프트에 직접 인용될 통계 2개가 재현 불가. '충돌' 정의에 따라 값이 크게 달라짐 | **확증(재실측으로 반증)** — 08-21 이후 봉인 키 출현 0 이므로 97.8% 는 성격이 다른 셋을 합쳐야만 산출. 조임 비율도 모집단이 달랐다(손절 계열 773:16 = 98.0%, 표본 789) | **채택** | 문서 상단 경고 배너 · F.8 실측 부록(산출식 동반) · F.3.6(§0 에서 비율 인용 삭제) |

## 비판이 짚지 않았고 이번에 새로 찾은 것

| # | 발견 | 근거 | 반영 |
|---|---|---|---|
| N1 | **BFB `breakout_retention_minutes` 라이브 값은 3 이 아니라 1 이었다.** 08-20~09-02 전 영업일 `current=1`, 09-01 만 `rec=3`. 즉 오늘 밤이 이 키가 범위 밖인 **첫 밤**이고 원안이 예상한 기전은 아직 한 번도 발화하지 않았다 | `parameter_recommendations.current_params` 시계열 전수 | F.2① · F.7-1(관측 가치 때문에 오늘 밤은 막지 않는 편이 낫다는 판단의 근거) |
| N2 | 원안 §0 의 "봉인 결정과 97.8% 충돌" 은 **08-21 이후 봉인 키 출현 0** 이라는 사실과 양립하지 않는다. 실측 대체치 = 최근 30일 138행 중 max_scan 포함 42.0% · 봉인키 포함 13.0%(전부 08-21 이전) | 478행 전수 | 상단 경고 배너 · F.8 |
| N3 | 검증기의 **봉인 검사 위치**가 설계에 없었다 — `:200` 뒤에 두면 ∅ 불변식 때문에 영원히 미발화(T2 의 구조적 귀결을 코드 위치로 못박음) | `:196-201` | F.3.2 위치 열 · 사이클 A 뮤테이션 |
| N4 | `auto_apply` 에 fail-closed 표본 게이트를 얹으면 `test_auto_apply_recommendations.py` 픽스처 5건이 전부 깨진다(해당 파일에 `metrics` 0건) | grep | 결정 #8 파급 명시 |
