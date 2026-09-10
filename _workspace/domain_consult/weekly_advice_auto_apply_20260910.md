# 자문 — 주간 파라미터 자문의 안전 자동 적용 확대 (방향 ①)

> 작성 = domain-expert (읽기 전용 자문). 2026-09-10.
> 의뢰 = 메인 세션 / team-lead. 워크리스트 "결정 대기" 10번.
> **이 문서는 코드·DB·설정·PR 을 아무것도 바꾸지 않았다.** 모든 인용은 실제 파일을 열어 확인했고
> 줄번호를 병기한다. 확인하지 못한 것은 "확인 불가"로 명시한다.

---

## 질문 요약

목 20:30 클라우드 루틴이 만드는 주간 파라미터 자문(현재 100% 수동 반영)에 cycle23/cycle210 의
휴면 자동 적용 인프라(`auto_apply_recommendations`)를 확장할 수 있는가.

1. **트리거를 어디에 둘 것인가** — (a) PR 머지 훅 / (b) `parameter_recommendations` 적재 후 기존
   함수 재사용 / (c) 별도 파싱 배치. 사람이 승인하는 지점과 롤백 경로를 함께 비교.
2. **cycle210 안전장치를 그대로 재사용해도 되는가** — 특히 "권고가 있다 = 표본 충분" 이 성립하는지,
   전략당 최대 3키 제한과 자동 적용 대상 키 수의 관계.
3. **승인 없는 자동 적용의 범위** — weight 감액만인가 파라미터까지인가. 밤사이 자동으로 바뀌어도
   되는 것과 사람이 아침에 봐야 하는 것의 경계. 단조 편향 재생산을 구조적으로 막는 조건.

---

## 결론 먼저 (3문장)

1. **cycle210 안전장치를 그대로 켜면 이번 주 권고 3건 중 0건이 통과한다** — 게이트가 "조이는 방향"
   으로 하드코딩돼 있고 새 자문은 3건 전부 "완화" 다(§트레이더 시각 T3). 재사용은 부족한 것이
   아니라 **방향이 직교**한다.
2. **"weight 감액 = 안전" 은 이 시스템에서 거짓이다** — `allocate_funds` 가 Σ 로 정규화하므로
   감액은 리스크를 줄이지 않고 **다른 전략으로 자금을 옮긴다**(§T1). 계좌 노출을 줄이는 다이얼은
   `cash_usage_ratio` 하나뿐이다.
3. 자동화해야 할 것은 **판단이 아니라 전사(transcription)** 다 — 사람이 읽고 고르는 단계는 남기고,
   손으로 값을 타이핑해 PUT 을 만드는 단계를 없앤다(§정량 권고 R1). 무승인 자동 적용은
   **"코드 기본값 방향으로만 한 걸음"** 이라는 앵커 규칙 아래에서만, 4주 새도 관측 후 검토한다.

---

## 트레이더 시각

### T1. 시장 가설이 아니라 산술의 문제 — 비중 감액은 리스크를 줄이지 않는다

트레이더 어법으로: **"비중을 줄였다"는 말은 이 시스템에서 "그 돈을 옆 전략에 줬다"는 뜻이다.**
현금으로 빠지는 게 아니다.

```python
# src/engine/strategy_registry.py:36-45
def allocate_funds(self, total_asset: int) -> None:
    enabled = self.enabled()
    total_weight = sum(s.config.weight for s in enabled)     # :39
    for s in enabled:
        ratio = s.config.weight / total_weight if total_weight > 0 else 0   # :41
        s.state.total_investment = int(total_asset * ratio)                 # :42
```

`ratio` 의 분모가 **Σweight** 다. 따라서 enabled 전략들의 `total_investment` 합은 Σweight 값과
무관하게 **항상 `total_asset` 전액**이다. 한 전략의 weight 를 절반으로 깎으면 그 몫은 남김없이
나머지 전략으로 재배분된다.

정량 예시 — 09-08 라이브 비중(주간 자문 §2.3 표: momentum .05 / VB .15 / LTV .10 / donchian .15 /
BFB .15 / VCP .10 / kojiro .30, Σ=1.00) 에서 donchian 을 50% 캡까지 자동 감액(.15→.075)하면:

| | 감액 전 | 감액 후 | 변화 |
|---|---:|---:|---:|
| Σweight | 1.000 | 0.925 | −7.5% |
| donchian 예산 비율 | 15.0% | 8.1% | **−6.9%p** |
| **vcp_breakout 예산 비율** | 10.0% | **10.8%** | **+0.8%p (+8.1%)** |
| kojiro 예산 비율 | 30.0% | 32.4% | +2.4%p |
| 계좌 총 투입액 | `total_asset` | `total_asset` | **불변** |

`vcp_breakout` 은 **전 기간 체결 0건**이다(주간 자문 §3.7: `/api/history` 609행 중 vcp_breakout 0행).
즉 이 "안전한 감액" 은 **증거가 0건인 전략의 예산을 밤사이 8% 올린다.** 자문은 VCP 비중에 대해
아무 말도 하지 않았고(권고 `recommended_weight: null`), 사람도 그 변경을 승인하지 않았다.

그리고 2차 효과가 하나 더 있다. cycle245 의 ρ축 랏 상한은 예산에 비례한다:

```
매수 가능 주가 상한 ≈ 순자산 × cash_usage_ratio × (weight ÷ Σweight) × position_ratio × K_ρ
```
(주간 자문 §2.3 의 식. K_ρ = `max_lot_ratio_mult`, 라이브 7전략 전부 2.5)

예산이 8% 오르면 그 전략의 **매수 가능 종목 유니버스가 밤사이 넓어진다.** VCP 상한은
≈126,700원 → ≈136,900원이 된다. 어제까지 못 사던 종목을 오늘 아침 살 수 있게 되는데, 이건
"비중 감액" 이라는 이름으로 승인된 적이 없는 **진입 행위의 변경**이다.

> **핵심** — 이 시스템에서 무승인 자동 적용의 대상으로 weight 는 **가장 안전한 축이 아니라
> 가장 은밀한 축**이다. 권고 대상 전략에는 축소로 보이지만, 아무 말도 없던 전략에는 확대로
> 작동하고, 그 확대는 로그에 "축소" 로만 남는다(`[auto_weight_apply]` 는 감액한 전략 1행만 찍는다,
> `recommendation_engine.py:629-633`).

### T2. 실전 사례 — 토글 하나가 주간 실험이 아니라 일일 튜너를 깨운다

`auto_apply_enabled` 는 **제공자(provider) 스코프가 없는 전역 불리언**이다
(`src/db/system_config.py:410-419`, 키 `auto_apply_enabled`, 기본 False). 그리고 이 토글을 읽는
곳은 하나뿐이다 — 매일 20:00 OpenAI 자문 직후 호출되는 경로다:

```
src/engine/scheduler.py:73    TIME_RECOMMENDATION = time(20, 0)
src/engine/scheduler.py:897-900   auto_apply_recommendations(target_date)   # generate_recommendations 직후
src/engine/recommendation_engine.py:570   enabled = await get_auto_apply_enabled()
```

즉 **주간 자문 실험을 위해 이 토글을 켜는 순간, 하루 5회 도는 OpenAI 일일 자문의 weight 감액이
자동 집행된다.** 이 자문은 4개월간 조임:완화 1,370:166 편향을 보인 바로 그 튜너다.

정량 시뮬레이션 — 주간 자문 §3.5 가 실측한 사실(`/api/recommendations` 최근 8일 momentum
`recommended_weight` 0.02~0.03 반복, `applied` 전건 `None`)에 현행 캡 로직
(`recommendation_engine.py:611`, `:622-623`)을 그대로 대입하면:

| 일자 | current | rw | cap = cur×0.5 | new = max(rw, cap) |
|---|---:|---:|---:|---:|
| D+1 | 0.050 | 0.02 | 0.025 | **0.025** |
| D+2 | 0.025 | 0.02 | 0.0125 | **0.020** |
| D+3 | 0.020 | 0.02 | — | skip (`rw >= current`, :611) |

**momentum 은 이틀 만에 0.05 → 0.02 로 자동 감액된다.** momentum 은 주간 자문 §3.5 기준
**원(+41,594) · %(+36.09%p) 양쪽 모두 양수인 유일한 전략**이다. 그리고 그 몫은 T1 의 산술에 따라
VCP(체결 0건) 를 포함한 나머지로 흘러간다.

50% 캡은 "하루 절반까지" 를 뜻하지 하한을 뜻하지 않는다. 매일 도는 경로에서 캡은 **속도 제한일 뿐
목적지 제한이 아니다** — 권고값에 며칠 안에 도달한다.

### T3. 위험 시나리오 — cycle210 게이트를 그대로 켜면 이번 주는 0/3 통과다

파라미터 자동 적용 루프의 실제 코드(`recommendation_engine.py:635-663`):

```python
for k, v in recommended_params.items():
    if k not in _CONSERVATIVE_KEYS:      # :637  ← _CONSERVATIVE_KEYS = frozenset()  (:531)
        continue                         #        지금은 전건 continue = 죽은 분기
    if k not in PARAM_RANGES:            # :639
        ... [auto_apply_safeguard_skip]; continue
    current_v = strategy.config.params.get(k)
    is_conservative = False
    if k in _STOP_LOSS_KEYS:             # :648
        if current_v is not None and float(v) > float(current_v):   # 절대값 축소 = 조임만
            is_conservative = True
    elif k == "position_ratio":          # :652
        if current_v is not None and float(v) < float(current_v):   # 축소만
            is_conservative = True
    if is_conservative:                  # :656
        strategy.config.params[k] = v
```

`_CONSERVATIVE_KEYS` 를 다시 채웠다고 가정하고(= cycle210 을 되돌리고) 이번 주 권고 3건을
그대로 넣어 보면:

| # | 전략 | 키 | 현재 → 권고 | `_STOP_LOSS_KEYS` 소속 | 방향 판정 | 결과 |
|---|---|---|---|---|---|---|
| 1 | LTV | `trailing_stop_rate` | −1.2 → **−2.0** | **아니오** (:534-541 에 없음) | 두 분기 어디에도 안 걸림 → `is_conservative=False` | **미적용** |
| 2 | LTV | `overnight_stop_loss` | −2.0 → **−3.5** | 예 | `−3.5 > −2.0` 거짓 | **미적용** |
| 3 | VCP | `last_pullback_max` | 0.10 → **0.15** | 아니오 | 두 분기 어디에도 안 걸림 | **미적용** |

**3건 중 0건 통과.** 이유는 표본이나 위험도가 아니라 **게이트가 조이는 방향만 통과시키도록
하드코딩돼 있기 때문**이다(`float(v) > float(current_v)` = 손절선을 위로, `< ` = 비중을 아래로).
새 주간 자문은 §7 에 "적용 대상 3키, **전부 완화**" 라고 명시한다.

그리고 이 비대칭이 바로 cycle210 이 없앤 그 래칫이다:

> `float(v)>current` 게이트가 조이는 방향만 통과 + 완화 경로 부재 = 단조 조임(monotone ratchet)
> → 전략 교살(donchian daily_loss −6→−0.8 방치가 산물)
> — `src/engine/CLAUDE.md:824`

즉 선택지는 두 갈래뿐이다:
- **(가) 게이트를 그대로 둔다** → 새 자문의 산출물은 구조적으로 하나도 자동 적용되지 않는다.
  자동화의 가치가 0 이다.
- **(나) 게이트에 완화 방향을 연다** → cycle210 이 닫은 래칫을 **반대 방향으로** 다시 연다.
  완화 단조는 손절폭 확대·보유기간 연장으로 나타나므로 조임 단조보다 **손실 꼬리가 두껍다**.

어느 쪽도 답이 아니다. 방향 게이트 자체를 다른 기준으로 갈아야 한다(→ §정량 권고 R2 앵커 규칙).

### T4. "권고가 있다 = 표본 충분" 은 이번 주 산출물에서 이미 거짓이다

주간 루틴은 왕복 N<10 이면 숫자 대신 가설을 내도록 설계됐다. 그런데 09-08 산출물 §3.7:

```json
{"strategy_id":"vcp_breakout","sample_status":"insufficient","closed_round_trips_30d":0,
 "recommended_params":{"last_pullback_max":0.15}, ...}
```

`sample_status` 가 **insufficient** 이고 확정 왕복이 **0** 인데 파라미터 권고가 **있다**.
설계 위반이 아니다 — 표본 규약은 *청산·비중 축*에 걸리고, 이 권고는 *후보 공급(진입 필터) 축*이라
증거가 왕복이 아니라 funnel 카운트이기 때문이다(자문 스스로 그렇게 밝힌다).

**따라서 "recommended_params 가 비어 있지 않다" 를 자동 적용 게이트로 쓰면, 왕복 0건짜리 변경이
통과한다.** 자동 경로는 반드시 행 안의 `sample_status` / `closed_round_trips_30d` 를 **직접**
읽어야 한다.

문제는 현행 검증기가 그 필드를 **모른다**는 것이다. `_validate_recommendations`
(`recommendation_engine.py:172-270`)는 `recommended_params` · `reasoning` · `recommended_weight` ·
`code_review_notes` · `weight_reasoning` 5개만 본다. 주간 자문의 `sample_status` ·
`closed_round_trips_30d` · `hypotheses` · `needs_human_decision` · `no_change_reason` 은 **전부
버려진다.** 새 자문의 안전 정보가 기존 파이프라인에서는 소실된다.

**전략당 최대 3키 제한과 자동 적용 대상 키 수의 관계**: 무관하다. 3키는 **자문이 말할 수 있는
상한**이고 자동 적용 대상은 **시스템이 집행해도 되는 상한**이다. 이번 주 실측은 7전략 합계 3키
(LTV 2 + VCP 1)로 전략당 상한에 한참 못 미쳤다 — 제한이 바인딩되지 않았으므로 이 값이 자동 적용
예산의 근거가 될 수 없다. 자동 적용 예산은 **주당 총 N키**로 별도 규정해야 한다(→ R2-④).

### T5. 반례 — 이번 주 자문은 생성 직후 스스로 틀렸고, 사람이 잡았다

주간 자문 §3.7 의 D-3 항목 evidence 마지막 문장(원문):

> 이 자문의 초안은 이를 3키 변경으로 잘못 기술했고 PR #20 codex 리뷰 지적으로 정정했다

**주간 산출물이 생성 시점에는 틀려 있었고, 리뷰 단계에서 고쳐졌다는 기록이 산출물 자신 안에
있다.** VCP 5단계 EMA 판정선이 config 50/150/200 이 아니라 런타임 캡을 거친 실효 50/65/75 라는
사실을 초안이 놓쳤고, 그래서 "3키를 바꾸자" 는 잘못된 권고를 냈다.

이 한 건이 트리거 설계에 두 가지를 못박는다:
- **PR 생성 시점 자동 적용(=리뷰 전)은 배제**된다. 실측된 오류율이 1주차 1/1 이다.
- 파싱 대상은 스키마가 강제되지 않는 **LLM 산문 안의 ```json 펜스**다. 주마다 필드가 빠지거나
  형태가 바뀔 수 있고, 그때 **부분 적용은 절대 금지**다(파싱 실패 = 적용 0, fail-closed).

---

## 정량 권고

### R1. 트리거 — (a)/(b)/(c) 비교, 그리고 권고안 (c′)

#### (b) `parameter_recommendations` 적재 후 기존 함수 재사용 — **구조적으로 불가**

블로커가 셋이고, 전부 코드/스키마에서 확인했다.

**B-1. UNIQUE 인덱스 충돌 → 조용한 소실.**
```sql
-- supabase/migrations/007_parameter_recommendations.sql:18-20
CREATE UNIQUE INDEX idx_param_rec_unique_per_day
    ON parameter_recommendations(target_date, strategy_id)
    WHERE status IN ('pending','applied','partial');
```
목요일 20:00 OpenAI 자문이 (목, 7전략) 7행을 이미 넣는다. 20:30 주간 루틴이 같은 (목, strategy_id)
로 넣으면 23505 다. 그런데 INSERT 헬퍼는 이걸 **예외로 올리지 않고 None 을 반환**한다:
```python
# src/db/parameter_recommendations.py:96-101
if "duplicate" in msg or "unique" in msg or "23505" in msg:
    logger.warning("파라미터 추천 중복 — 이미 존재함: %s (%s)", strategy_id, target_date)
    return None
```
**주간 자문 7행이 WARNING 한 줄만 남기고 통째로 사라진다.** `provider` 컬럼은 스키마에 없다
(007:1-15) — 추가하려면 마이그레이션 + 부분 UNIQUE 인덱스 재정의가 함께 필요하다.

**B-2. 시각이 어긋나 어떤 auto_apply 패스도 그 행을 보지 못한다.**
`auto_apply_recommendations` 는 20:00 에 `generate_recommendations` **직후** 호출되고
(`scheduler.py:897-900`), 대상은 `list_pending_by_date(오늘)` 로 `target_date = $1` 필터다
(`db/parameter_recommendations.py:199-208`). 주간 루틴은 **20:30 — 30분 뒤**다. 그 행이 평가받을
기회는 다음 날 20:00 뿐인데, 그날 `generate_recommendations` 가 먼저
`expire_pending_before(오늘)` 을 호출해(`recommendation_engine.py:399`) `target_date < 오늘` 인
pending 을 전부 `expired` 로 만든다. **주간 행은 태어나서, 무시당하고, 만료된다.**

**B-3. 루틴에 쓰기 권한이 없다.**
주간 루틴은 리포터 스코프 키로 접속한다. 허용은 GET/HEAD 전체 + `POST /api/log-reports/{date}/external`
**한 경로**뿐이고 그 외 상태변경은 403 `reporter_scope` 다:
```python
# src/middleware/api_auth.py:262-269
if reporter_key and secrets.compare_digest(provided, reporter_key.encode("utf-8")):
    if method in REPORTER_READ_METHODS: return ""
    if method == "POST" and REPORTER_WRITE_PATH_RE.fullmatch(path): ... return ""
    return REASON_REPORTER_SCOPE
```
루틴이 DB 에 후보를 적재하려면 **새 리포터 허용 경로를 뚫거나 운영 키를 클라우드에 두어야 한다.**
후자는 인터넷 노출 자격에 전 권한을 주는 것이라 권고하지 않는다.

**판정: (b) 는 "재사용" 이 아니라 마이그레이션 + 인덱스 재정의 + 스케줄 슬롯 신설 + 인증 스코프
확장의 4중 신규 작업이다. 재사용률이 가장 높다는 가설은 성립하지 않는다.**

#### (a) PR 머지 훅 — 위치는 맞지만 신호가 잘못됐다

PR #20 은 **파일 1개**(`_workspace/domain_consult/weekly_advice_2026-09-08.md`, +315/−0, `gh pr view 20`
실측)만 건드린다. 그리고 `_workspace/**` 는 CI/Deploy `paths-ignore` 라 **머지해도 오늘은 아무것도
안 뜬다**(루트 CLAUDE.md cycle248 항). 즉 현재 머지의 의미는 **순수 보관**이다.

거기에 적용을 얹으면 세 가지가 깨진다:
1. **읽기 순서가 뒤집힌다.** 머지 대상 파일이 곧 사람이 읽고 판단할 자료다. "머지=적용" 이면
   다 읽기 전에 결정해야 하거나, 읽으려면 머지를 미뤄야 한다.
2. **부분 동의를 표현할 수 없다.** 이번 주만 봐도 사람은 3키 중 LTV 2건은 받고 VCP 1건은
   (왕복 0건이라) 보류하고 싶을 수 있다. 머지는 전부/전무 신호다.
3. **보관 의도와 적용 의도가 같은 제스처를 공유한다** — team-lead 가 가설에서 지적한 그대로이며,
   나도 동의한다.

**단, (a) 의 *타이밍* 은 유일하게 옳다** — T5 가 보여주듯 리뷰 **후** 시점이라야 정정된 버전이
대상이 된다. 그래서 결론은 "머지 훅을 쓰되 머지 자체를 신호로 삼지 않는다" 이다.

#### (c′) 권고안 — 별도 파싱 배치 + 명시적 2단계

```
목 20:30  루틴이 PR 을 낸다                        [현행 무변경]
          ↓
          파싱 배치가 PR 브랜치의 md 를 읽어 "적용 후보 큐" 를 만든다.
          각 항목 = {전략, 키, 현재값, 권고값, 코드 기본값, sample_status,
                     closed_round_trips_30d, 게이트 통과 여부, 사전 계산된 PUT payload}
          ↓
사람      큐를 보고 **항목 단위로** 체크 → 적용 버튼 (또는 PR 에 `apply:` 라인 추가 후 머지)
          ↓
시스템    체크된 항목만, R2 게이트를 통과한 것만 PUT 을 집행하고 결과를 되쓴다
```

- **사람이 승인하는 지점** = 항목 체크 (머지가 아니다). 머지는 계속 보관만 뜻한다.
- **자동화되는 것** = 값 전사·PUT 조립·범위 검증·기본값 대조·결과 기록. **판단은 자동화하지 않는다.**
- 사용자가 오늘 잃은 신뢰의 지점이 정확히 "확인 없이 값이 바뀐 것" 이므로, 없애야 할 토일은
  **눈이 아니라 손가락**이다.

#### 롤백 경로 (세 안 공통 — 적용 축에 따라 다르다)

| 적용 축 | 발효 시점 | 롤백 수단 | 롤백 반영 | 사람의 실질 점검 창 |
|---|---|---|---|---|
| **params** | **즉시** (`strategy.config.params[k]=v` + `save_params`, `recommendation_engine.py:657-666` / 라우트는 `routes/strategies.py:176-182`) | `PUT /api/strategies/{id}/params` | **즉시** | 20:30 적용 → 다음 매매 08:00(LTV pre_nxt) 또는 09:00 = **약 11시간** |
| **weight** | **다음 07:55 `_boot()`** (`allocate_funds` 재호출 없음 — `routes/recommendations.py:57` 주석) | `PUT /api/strategies/weights` | 다음 `_boot()` | 20:30 → 07:55 = **약 11시간 25분** |
| **weight (DB 직접)** | — | `strategy_config` SQL UPDATE | **다음 백엔드 재시작에서만** | 보유 중 장중이면 D6 로 재시작 금지 ⇒ 사실상 불가 |

두 축 모두 밤사이 11시간의 점검 창이 있다. **차이는 창의 길이가 아니라 무엇이 바뀌느냐다**(→ R3).

### R2. 주간 자문 전용 규약 — cycle210 재사용 불가, 4개 게이트로 대체

cycle210 게이트(방향 하드코딩)는 T3 에서 보듯 새 자문과 직교한다. 대체 규약:

#### ① 코드 기본값 앵커 (가장 중요 — 단조 편향의 구조적 차단기)

> **자동 적용은 라이브 값을 `DEFAULT_PARAMS` 쪽으로만 움직일 수 있고, 기본값을 지나칠 수 없다.**
> `new` 는 반드시 `[min(current, default), max(current, default)]` 구간 안이어야 한다.

왜 이게 래칫을 죽이는가:
- 방향을 **고정하지 않는다.** 라이브가 기본값보다 조여 있으면 완화만, 완화돼 있으면 조임만
  허용된다. 편향은 방향 게이트에서 나오는데 그 게이트가 사라진다.
- **자기 종료적**이다. 기본값에 닿으면 그 키의 자동 경로는 영구 no-op 이 된다. 무한 조임도
  무한 완화도 산술적으로 불가능하다.
- **상한이 이미 사람이 승인한 값**이다. `DEFAULT_PARAMS` 는 소스에 있고 리뷰·커밋을 거쳤다.
  자동 적용의 목적지가 "AI 가 고른 숫자" 가 아니라 "우리가 코드에 적어 둔 숫자" 가 된다.
- **드리프트 회수 도구로 정확히 맞는다.** 주간 자문이 찾아낸 드리프트는 전부 한 방향이다 —
  LTV trailing −1.2 vs 기본 −2.0 / donchian atr_trail 1.8 vs 2.0 / breakout_fail 2 vs 5 /
  momentum trailing −1.3 vs −2.0. **전부 조임.** 앵커 규칙은 이 래칫을 되감는 일만 한다.

이번 주 3건에 대입:

| # | 키 | 현재 | 권고 | 코드 기본 | 앵커 판정 | 결과 |
|---|---|---:|---:|---:|---|---|
| 1 | LTV `trailing_stop_rate` | −1.2 | −2.0 | **−2.0** | 기본값과 정확히 일치 | **통과 (−2.0)** |
| 2 | LTV `overnight_stop_loss` | −2.0 | −3.5 | −5.0 | 기본값 쪽 부분 이동 | **통과 (−3.5)** |
| 3 | VCP `last_pullback_max` | 0.10 | 0.15 | **0.12** | 기본값을 **지나침** (0.12 < 0.15) | **클램프 0.12 또는 차단** |

3번은 게이트 ②(왕복 0건)에서도 걸린다. 두 게이트가 독립적으로 같은 항목을 잡는 것은 설계가
건강하다는 신호다.

> ⚠️ 앵커 규칙은 `DEFAULT_PARAMS` 를 읽으므로, **기본값을 바꾸는 코드 변경이 곧 자동 적용의
> 목적지를 바꾼다.** 기본값 변경은 이미 승인 대상이므로 계약이 깨지지는 않지만, 이 커플링을
> 문서와 회귀 가드에 명시해야 한다.

#### ② 왕복 표본 하드 게이트 — 행에서 직접 읽는다, 추론 금지

`closed_round_trips_30d >= 10` **그리고** `sample_status == "sufficient"` 를 둘 다 요구한다.
"권고가 있으니 충분하겠지" 는 T4 에서 반증됐다. 두 필드가 **없으면 fail-closed**(미적용).

#### ③ 축 제한 — 진입/공급 축만. 청산 축은 사람.

근거는 R3 에 있다. 요약하면 청산 파라미터 변경은 **이미 보유 중인 포지션의 계약**을 바꾼다.

#### ④ 주당 예산 — 총 1키

전략당 3키는 자문의 발화 상한이지 집행 상한이 아니다(T4). 자동 집행은 **주 1키**로 시작한다.
한 주에 한 개만 바뀌면 다음 주 자문이 그 변화를 **귀인할 수 있다** — 두 개를 동시에 바꾸면
`§6 검증 계획` 의 성공 판정이 성립하지 않는다. (자문 §6 이 "한 번에 한 축" 을 스스로 권고한다.)

#### ⑤ 공통 — 파싱은 fail-closed, weight 는 전건 제외

- ```json 펜스 파싱 실패·필드 누락·타입 불일치 = **그 주 자동 적용 0건**. 부분 적용 금지.
- `PARAM_RANGES` 관문은 그대로 유지(현행 `:639` 와 동일 정본 참조, 사본 금지 — `routes/recommendations.py:16-18`
  이 이미 그 규약을 명문화했다).
- **weight 는 자동 적용 대상에서 전면 제외**(→ R3).

### R3. 승인 없는 자동 적용의 범위 — 경계선

#### 트레이더의 경계: **"이미 잡은 포지션의 계약을 바꾸는가"**

내가 어제 어떤 종목을 살 때, 나는 손절선·트레일링 폭·보유 상한을 **전제로** 그 진입을 결정했다.
진입과 청산은 한 덩어리의 계약이다. **밤사이 그 청산 조건이 내 동의 없이 바뀌면, 나는 내가
동의한 적 없는 포지션을 아침에 들고 있는 것이다.** 이것이 재량 트레이더가 알고리즘에게 절대
맡기지 않는 단 하나다. 프로젝트도 같은 원칙을 이미 명문화하고 있다 — "DB 토글 하나로 **기보유
포지션의 손절 규약**이 바뀌면 안 된다"(루트 CLAUDE.md, 터틀 ATR 손절 게이트 항).

| | 밤사이 자동으로 바뀌어도 되는 것 | 사람이 아침에 봐야 하는 것 |
|---|---|---|
| **대상** | **다음 진입**에만 영향 | **보유 중 포지션**의 청산·계좌 전체 노출 |
| **키 예시** | `last_pullback_max` · `base_depth_pct` · `volume_contraction_ratio` · `breakout_volume_mult` · `min_prdy_rate` · `min_market_cap` · `min_trade_amount` · `max_scan_stocks` · `gap_up_threshold` · `k_value_*` | `stop_loss_*` · `trailing_stop_rate` · `intraday/overnight_stop_loss` · `daily_loss_limit` · `position_ratio` · **`weight` 전부** |
| **되돌리면** | 후보가 다시 좁아질 뿐, 손실 미확정 | 되돌리기 전에 **그 손절선에 이미 닿았을 수 있다 — 손실이 확정된다** |
| **틀렸을 때 비용** | 기회비용 | 실현손실 |

`position_ratio` 가 오른쪽에 있는 이유는 두 겹이다 — 랏 크기(다음 진입)이면서 동시에
`position_ratio × max_positions ≤ 1.0` 불변식의 한 축이고(`_validate_recommendations` 가 이미
교차검증한다, `recommendation_engine.py:222-241`), 게다가 ρ축 상한을 통해 **매수 가능 주가 상한**을
움직인다(주간 자문 §3.2 D 항: 0.20→0.25 면 상한 126,700→158,500원). 유니버스가 밤사이 바뀌는
변경은 진입 축이어도 사람이 본다.

#### weight 를 무승인 범위에서 **전면 제외**하는 이유 (재확인)

1. **T1** — Σ 정규화 때문에 감액이 리스크를 줄이지 않고 재배분한다. "감액 = 안전" 이라는 전제가
   이 코드베이스에서 거짓이다.
2. **T1 2차** — 수혜 전략의 ρ축 매수 가능 주가 상한이 함께 올라 **진입 유니버스가 넓어진다.**
3. **T2** — 토글에 provider 스코프가 없어 일일 튜너까지 함께 깨어난다.
4. 로그가 축소 1행만 남겨 **확대는 관측되지 않는다**(`:629-633`).

> 계좌 노출을 실제로 줄이는 유일한 다이얼은 `cash_usage_ratio` 다(`allocate_funds(total_asset)`
> 의 `total_asset` 자체를 줄인다). weight 자동 감액을 굳이 하려면 `cash_usage_ratio` 동반 조정이
> 짝이어야 하는데, 그건 계좌 전체 결정이라 정의상 사람 몫이다.

**보존해야 할 안전 성질 하나** — 현행 50% 캡은 속도 제한처럼 보이지만 실은
**`enabled=False` 방지 장치**다. `save_weights` 가 `enabled = weight > 0` 으로 쓰기 때문에
(`src/db/strategy_config.py:64`) weight 0 은 축소가 아니라 **전략 비활성화 = 손절 정지**다.
`new_weight = max(rw, current × 0.5)` 는 `current > 0` 인 한 항상 양수라 0 에 닿지 못한다
(`:622-623`). 앞으로 어떤 캡 변경도 이 성질을 깨면 안 된다.

### R4. 단계별 도입안

| 레벨 | 내용 | 승인 | 도입 시점 |
|---|---|---|---|
| **0** | **적용 후보 큐** — 파싱·전사·PUT 조립·기본값 대조·게이트 사전판정까지 자동. **적용은 사람이 항목 단위 체크.** | 항목마다 사람 | **지금 권고.** 이번 주 3키 전부 여기서 처리 |
| **1** | 레벨 0 큐 항목 중 **앵커 ∧ 왕복≥10 ∧ 진입축 ∧ 주1키** 4조건 전부 만족만 무승인 자동 적용 | 레벨 승격 자체가 사용자 결정 | **4주 새도 관측 후 재판단** |
| **2** | weight 자동 적용 | — | **도입하지 않는다** (R3) |

**레벨 0 → 1 승격 판정 기준(정량)**: 레벨 0 을 돌리는 동안, 매주 "게이트가 통과시켰을 항목" 과
"사람이 실제로 체크한 항목" 의 집합을 나란히 기록한다. **4주 연속 불일치 0** 이면 승격을 검토한다.
불일치가 1건이라도 나오면 그 사유를 게이트에 반영하고 카운터를 리셋한다.
이 새도 관측은 **행위 변경이 0** 이므로 8영역·`scheduler.py` 무접촉으로 만들 수 있다.

---

## 현 코드와의 정합성

### 충돌 항목

| # | 충돌 | 위치 | 심각도 |
|---|---|---|---|
| **C-1** | `_CONSERVATIVE_KEYS` 를 다시 채우는 것 = **cycle210 되돌리기** | `src/engine/recommendation_engine.py:528-531` + `src/engine/CLAUDE.md:824` | **HIGH** — 명문화된 결정의 반전. 되돌린다면 그 문서를 함께 개정해야 한다 |
| **C-2** | 방향 게이트가 새 자문의 산출 방향과 직교 (0/3 통과) | `recommendation_engine.py:648-655` | **HIGH** — 재사용 가설의 근거 소멸 |
| **C-3** | `auto_apply_enabled` 에 provider 스코프 없음 → 주간용 토글이 일일 경로를 깨움 | `src/db/system_config.py:410-419` · `scheduler.py:897-900` | **HIGH** — 의도치 않은 일일 weight 자동 감액 |
| **C-4** | UNIQUE `(target_date, strategy_id)` 로 목요일 두 자문 충돌, 중복은 예외 없이 None | `supabase/migrations/007:18-20` · `db/parameter_recommendations.py:96-101` | **HIGH** — (b) 안 차단 |
| **C-5** | 20:00 auto_apply 가 20:30 산출물보다 30분 먼저 돌고, 다음날 expire 가 먼저 지운다 | `scheduler.py:73,897` · `recommendation_engine.py:399` · `db/parameter_recommendations.py:199-208` | **HIGH** — (b) 안 차단 |
| **C-6** | 리포터 키는 GET/HEAD + log-reports POST 1경로만. 루틴이 DB·params 에 쓸 수 없다 | `src/middleware/api_auth.py:262-269` | **MEDIUM** — 인증 스코프 확장은 별도 보안 결정 |
| **C-7** | `_validate_recommendations` 가 `sample_status`·`closed_round_trips_30d` 를 모른다 → 안전 정보 소실 | `recommendation_engine.py:172-270` | **MEDIUM** — 주간 전용 검증기 필요 |
| **C-8** | 자동 적용 전반이 하네스의 "사용자 결정 항목(파라미터 값·비중)" 에 해당 | 루트 `CLAUDE.md` 승인 절 | **계약** — 레벨 1 도입 자체가 사용자 승인 사안 |
| **C-9** | 주간 자문 §3.6 — 절차 문서의 "BFB·VCP K_ρ=20 표본 보호" 가 라이브에 없다(7전략 전부 2.5) | 주간 자문 §3.6 D-8 | **MEDIUM** — 자동 적용 도입 전에 절차↔라이브 정합을 먼저 맞춰야 한다 |

### 변경 vs 유지 선택지

| 항목 | **유지** | **변경** |
|---|---|---|
| `_CONSERVATIVE_KEYS = frozenset()` | **권고** — cycle210 결정을 지키고, 자동 적용은 앵커 규칙 기반 **신규 경로**로 만든다 | 다시 채우면 C-1/C-2 를 동시에 떠안는다 |
| `auto_apply_enabled` 토글 | **권고: OFF 유지** | 켜면 C-3 로 일일 weight 감액이 즉시 발효 |
| weight 자동 적용 | **권고: 영구 제외** | 하려면 `cash_usage_ratio` 동반 조정 설계가 선행 |
| 주간 산출물 경로 | **권고: PR + Notion 유지**, DB 적재 안 함 | (b) 는 4중 신규 작업 (C-4~C-6) |

---

## 반례 / 한계

1. **앵커 규칙은 "기본값이 옳다" 를 가정한다.** 라이브 값이 사람의 의도적 결정인 경우
   (kojiro `position_ratio` 0.166 = 2026-08-08 불변식 지혈, `max_positions` 6 등) 자동 되돌림은
   **그 결정을 지운다.** → 앵커 경로는 **결정 로그(`DECISION_LOG`)에 등재된 (전략,키) 쌍을 반드시
   제외**해야 한다. `advisor_prompt_review_20260903.md` §F.3.1 이 제안한 `advisor_policy.py`
   단일 정본이 정확히 이 자리다. **앵커 규칙은 그 정본 없이는 도입하면 안 된다.**
2. **N≥10 왕복은 통계적으로 약하다.** 주간 자문 §1 이 스스로 밝히듯 289왕복 전체의 t 값이 −0.57 다.
   왕복 10건으로는 어떤 파라미터 효과도 유의하지 않다. 이 게이트는 *유의성* 이 아니라
   *최소한의 관측 존재* 를 보증할 뿐이다. **"게이트를 통과했으니 근거가 있다" 로 읽으면 안 된다.**
3. **1주 폴백 86% 가 모든 귀인을 오염시킨다.** 주간 자문 §2.3 — 최근 30일 확정 왕복 91건 중 78건
   (86%)이 1주 폴백이고 명목이 50배 차이 난다. 이 상태에서는 파라미터 변경의 효과와 랏 크기
   잡음이 분리되지 않는다. **자동 적용의 선행 조건으로 "1주 폴백 비율 60% 이하"(자문 §6 의 판정선)
   를 요구하는 것이 정직하다.** 이 조건이 미충족인 동안은 레벨 0 만 돌린다.
4. **09-07 `[7] STCK_OPRC` 프리장 오염이 아직 열려 있다**(워크리스트 cycle265/F-2). 진입가 자체가
   설계와 달랐던 기간의 관측으로 파라미터를 자동 조정하면, 데이터 결함을 파라미터로 보상하게 된다.
5. **cycle262(09:00 직후 90초 진입 보류)의 첫 실전 효과가 아직 판독 전이다.** 최근 표본에 정책
   변경이 섞여 있어 지금은 어떤 자동 적용도 "무엇의 효과인지" 를 물을 수 없다.
6. **표본 규약이 바인딩되지 않은 상태다.** 이번 주 7전략 중 `sufficient` 는 4개(VB 41 / LTV 18 /
   donchian 17 / kojiro 10)뿐이고, 권고 3건 중 자동 적용 후보가 될 만한 것은 LTV 2건이다.
   **자동화의 처리량이 주 0~2건이다** — 이 규모에서 무승인 자동 적용이 절약하는 시간은 분 단위다.
   위험 대비 이득 비율이 나쁘다는 것이 레벨 1 을 서두르지 말라는 가장 실무적인 이유다.
7. **확인 불가**: 운영 DB 의 `system_config.auto_apply_enabled` 현재 실측값. 코드 기본은 False 이고
   워크리스트/changelog 는 "한 번도 켠 적 없음 · `applied_auto` 상태 이력 0건" 이라 기재하나,
   이 자문은 DB 를 조회하지 않았다. **도입 전 실측 확인 필요.**
8. **확인 불가**: 주간 루틴 프롬프트의 원문 전문. 워크리스트 W3 행과
   `_workspace/reports/2026-09-05_night_autonomous_work.md:88` 의 요약(절대 금지 키 12종 · 표본 규약
   · 전략당 최대 3키)만 확인했고, 클라우드 루틴에 등록된 실제 프롬프트 텍스트는 열지 못했다.

---

## 후속 검증 권고

### tdd-engineer 에게

레벨 0 을 구현한다면 Red 로 먼저 박아야 할 행위:

| # | 케이스 | 기대 |
|---|---|---|
| V-1 | 앵커 — `current=−1.2, rec=−2.0, default=−2.0` | 통과, `new=−2.0` |
| V-2 | 앵커 — `current=0.10, rec=0.15, default=0.12` | **클램프 0.12 또는 차단** (기본값 통과 금지) |
| V-3 | 앵커 — `current=−5.0, rec=−3.0, default=−7.0` (기본값 **반대** 방향) | **차단** |
| V-4 | 표본 — `sample_status="insufficient"` ∧ `recommended_params` 비어있지 않음 (= 09-08 VCP 실제 행) | **차단** |
| V-5 | 표본 — `sample_status` 필드 자체 부재 | **차단** (fail-closed) |
| V-6 | 파싱 — ```json 펜스 5개 중 3번째가 깨진 JSON | **그 주 전건 0 적용** (부분 적용 금지) |
| V-7 | 축 — `stop_loss_rate`(청산축)가 앵커·표본을 **둘 다 통과**해도 | **차단** (사람 큐로) |
| V-8 | 예산 — 통과 항목 3건 | **1건만 적용**, 나머지는 큐 잔류 |
| V-9 | 결정 로그 — kojiro `position_ratio` 0.166 (등재된 사람 결정) | **차단** (한계 1) |
| V-10 | 회귀 — `save_weights` 경로에 자동 적용이 **도달하지 않음** (weight 전면 제외) | 호출 0회 |
| V-11 | 회귀(영속) — `new_weight` 가 0 이 될 수 있는 경로 부재 (`enabled=False` 방지, `strategy_config.py:64`) | 상시 > 0 |

**골든 픽스처 권고**: `weekly_advice_2026-09-08.md` 의 7개 ```json 블록을 **원문 그대로** 픽스처로
고정한다. 이 파일은 (i) insufficient 인데 권고가 있는 행(VCP), (ii) 기본값을 지나치는 권고(VCP),
(iii) 기본값에 정확히 착지하는 권고(LTV trailing), (iv) 부분 복원(LTV overnight), (v) 권고 0 인 행
4개를 **한 파일 안에 전부** 담고 있다. 합성 시리즈를 만들 필요가 없다.

### tester 에게

- **T-1**: 운영 DB `system_config.auto_apply_enabled` 실측(한계 7). False 가 아니면 **다른 모든 논의보다
  먼저** 보고할 것 — 일일 weight 자동 감액이 이미 돌고 있다는 뜻이다.
  교차 확인 = `parameter_recommendations.status = 'applied_auto'` 행 수, `[auto_weight_apply]` 로그 존재 여부.
- **T-2**: 주간 자문 §3.6 D-8 검증 — 라이브 7전략 `max_lot_ratio_mult` 가 정말 전부 2.5 인지
  (`GET /api/strategies`). 절차 문서는 BFB·VCP 20 이라 기재한다. **절차↔라이브 불일치는 자동 적용
  도입 전에 닫아야 한다** (C-9).
- **T-3**: 1주 폴백 비율 주간 추적(현재 86%). 60% 이하로 내려가기 전에는 레벨 1 판정을 시작하지 않는다.

### backend-dev / refactor-expert 에게

- 앵커 규칙은 `DEFAULT_PARAMS` 를 읽는다 → 전략 7파일에 대한 **읽기 전용** 의존이 생긴다.
  `recommendation_engine` 이 전략 모듈을 import 하는 방향이 맞는지, 아니면
  `advisor_policy.py`(신규 leaf, `advisor_prompt_review_20260903.md:63-66` 제안)가 그 대조를 소유해야
  하는지 판단이 필요하다. **8영역 무접촉은 어느 쪽이든 유지 가능**하다(자문 경로는 20:00/20:30 배치).
- `advisor_prompt_review_20260903.md:145-148` 이 이미 경고한다 — 화이트리스트를 `advisor_policy`
  경유로 **교체**하면 AST 가드 G-223F-1/G-223F-2 가 FAIL 한다. **후속 축소 대입으로 얹어야** 한다.

### team-leader 에게

레벨 0 도 하네스 계약상 **"매매 행위를 바꾸는 코드 변경"** 의 인접 영역이다(적용을 집행하는 경로가
생긴다). 착수 전 사용자 승인 + 이 자문의 결정 카드 3장 회신이 선행돼야 한다.

---

## 사용자 결정 카드

### 카드 ① — 자동화의 대상: 판단인가, 전사인가

**질문**: 주간 자문의 무엇을 자동화하는가.

- **A. 레벨 0 — 적용 후보 큐** (파싱·전사·PUT 조립·기본값 대조·게이트 사전판정 자동, **적용은 사람이
  항목 단위 체크**)
- **B. 레벨 1 — 조건부 무승인 자동 적용** (앵커 ∧ 왕복≥10 ∧ 진입축 ∧ 주1키)
- **C. 현행 유지** (100% 수동)

**권고: A**, 그리고 4주 새도 관측(게이트 판정 vs 사람 선택 불일치 0)이 쌓인 뒤에 B 를 재검토.

**근거 한 줄**: 이번 주 실제 처리량은 자동 적용 후보 주 0~2건이라 무승인이 절약하는 시간은 분
단위인데, 잃는 것은 "값이 내 확인 없이 바뀌지 않는다" 는 성질이다 — 사용자가 오늘 잃은 신뢰의
지점이 정확히 그것이므로 없앨 토일은 눈이 아니라 손가락이다.

---

### 카드 ② — weight 자동 적용을 범위에 넣을 것인가

**질문**: 승인 없는 weight 감액(50% 캡)을 범위에 포함할 것인가.

- **A. 전면 제외** — weight 는 어떤 레벨에서도 자동 적용하지 않는다
- **B. 감액만 포함** (현행 cycle210 잔존 로직 재사용)
- **C. 포함하되 `cash_usage_ratio` 동반 조정을 짝으로 설계**

**권고: A.**

**근거 한 줄**: `allocate_funds` 가 Σ 로 정규화하므로(`strategy_registry.py:39-42`) 감액은 리스크를
줄이지 않고 **체결 0건 전략(VCP)을 포함한 나머지로 예산을 옮기며**, 그 수혜는 ρ축 상한을 통해
매수 가능 종목 유니버스까지 넓히는데 로그에는 감액 1행만 남는다.

---

### 카드 ③ — `auto_apply_enabled` 토글을 건드릴 것인가

**질문**: 실험을 위해 기존 토글을 켤 것인가, 새 경로를 별도 토글로 만들 것인가.

- **A. 기존 토글 OFF 유지 + 주간 전용 신규 경로·신규 토글**
- **B. 기존 토글 ON** (기존 함수 재사용)
- **C. 판단 보류 — 먼저 운영 DB 실측(T-1)부터**

**권고: A**, 단 **C 를 먼저 1회 실행**한다(코드 기본은 False 이나 이 자문은 DB 를 조회하지 않았다).

**근거 한 줄**: 토글에 provider 스코프가 없어(`system_config.py:410-419`) 켜는 순간 매일 20:00
OpenAI 경로가 함께 깨어나고, 실측 반복 권고값(momentum 0.02)을 캡 로직에 대입하면 **유일하게
원·% 양쪽 양수인 전략이 이틀 만에 0.05→0.02 로 자동 감액**된다.

---

*이 문서는 읽기 전용 자문이다. 어떤 코드·DB·설정·PR 도 변경하지 않았다. 권고의 채택 여부는
team-leader 와 사용자에게 있다.*
