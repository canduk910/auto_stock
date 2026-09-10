# cycle275 — `net_external_cashflow` T+2 결제 시점 불일치 시정 명세

작성일 2026-09-11. 코드·테스트 변경 없음(명세 전용). 사실은 파일:행 인용, 추측은 "추정"으로 표기.

---

## §0 요약

`_settle_daily_performance`(정확히는 `TradingScheduler._settle`, `src/engine/scheduler.py:3602`)가
매일 기록하는 `net_external_cashflow`(외부 입출금 추정)는 KIS 잔고조회 응답의 `dnca_tot_amt`
(예수금총금액, D+0 당일 잔고)를 기준으로 "오늘 Δ예수금 − 오늘 매매 순현금"을 계산한다. 국내주식은
T+2 결제이므로 오늘 예수금 변화는 실제로는 이틀 전(D−2) 매매의 결제분을 반영하고, 그 이틀치
시차가 매일 수십만 원대의 허수로 `net_external_cashflow`에 찍힌다. 16영업일 실측(사용자 확인 —
그 기간 실제 입출금 없음)에서 "Δ예수금(D) − 매매순현금(D−2)" 모델의 잔차 중앙값은 2,813원(수수료·
세금 크기)인 반면, 현재 기록값의 중앙값은 367,270원이다.

시정안은 KIS 응답의 `prvs_rcdl_excc_amt`(가수도정산금액)를 새 기준가로 채택해 계산식을
"오늘 Δ가수도정산금액 − 오늘 매매순현금"으로 바꾼다. **매매 행위(진입·청산·수량·사이징·손절)는
전혀 건드리지 않는다** — 순수하게 정산 기록(리포트) 로직이다. 다만 접점이 `scheduler.py`
(8영역은 아니나 라인 상한 때문에 동일 승인 대상, 루트 `CLAUDE.md` "여전히 승인이 필요한 것")를
지나므로 이 사이클 전체가 **승인 필요**다(§4).

`prvs_rcdl_excc_amt`의 공식 정의는 KIS 문서에서 필드명 한글 매핑("가수도정산금액")만 확인했고,
정확한 산식(어떤 미결제분을 어떻게 반영하는지)은 확정하지 못했다 — **확정 실패, 배포 후 실측
검증이 필요하다**(§2, §7).

---

## §1 결함 사실

### 1.1 현재 산식

`src/engine/scheduler.py:3602` `_settle()`:

```python
_, summary = await get_balance()
...
prev_total = await get_latest_performance(strategy="total")
prev_deposit = float(prev_total["deposit"]) if prev_total else float(summary.deposit)
...
net_trade_cashflow = sell_total - buy_total  # 매매로 인한 예수금 증가분   (scheduler.py:3629)
net_ext_cashflow = (float(summary.deposit) - prev_deposit) - net_trade_cashflow  # (scheduler.py:3632)
...
await upsert_daily_performance(
    ...
    net_external_cashflow=net_ext_cashflow,   # (scheduler.py:3650)
    deposit=float(summary.deposit),           # (scheduler.py:3652)
    ...
)
```

- `summary.deposit`는 `AccountSummary.deposit`(`src/models/balance.py:29`, 주석 "dnca_tot_amt
  (예수금총금액)")이고, `src/api/balance.py:214`에서 `deposit=int(s.get("dnca_tot_amt", 0))`로
  채운다 — KIS 잔고조회(TTTC8434R) output2의 D+0 당일 예수금이다.
- `net_trade_cashflow`는 **오늘(D) 체결분**의 매도금 − 매수금(`scheduler.py:3624-3629`,
  `get_today_trades_for_settlement()` 소스).
- 즉 현재 식은 "오늘 예수금 변화 − 오늘 매매 현금흐름"인데, 오늘 예수금 변화는 실제로는
  **D−2 매매의 결제 반영**이므로 두 항의 시점이 어긋난다.

### 1.2 실측 검증

읽기 전용 스크립트(`/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/823ca95c-aa00-4436-b4f5-5eac77e3c1db/scratchpad/cashflow_check.py`,
`daily_performance`·`trade_history` SELECT만 수행)로 2026-08-20~09-10(16영업일) 데이터를 재현:

- 비교 모델 A(T+2 정합): `Δdeposit(D) − net_trade(D−2)`. 잔차 절대값 중앙값 = **2,813원**
  (수수료·세금 규모 — 사실상 설명됨).
- 현재 기록값 `net_external_cashflow`(= `Δdeposit(D) − net_trade(D)`, T+0 가정): 절대값 중앙값 =
  **367,270원**.
- 사용자 확인: 해당 기간 실제 입출금 없음. → 기록값 367,270원은 전액 T+2 시점 불일치로 인한
  허수로 **확정**.

### 1.3 영향 범위

- `daily_performance.net_external_cashflow`(컬럼 정의: `supabase/migrations/001_init.sql` 기준
  원본 스키마 + `src/db/daily_performance.py:29,50,56,65` upsert 경로)에 매일 오염된 값이 영속화된다.
- `GET /api/performance/daily`(`src/routes/performance.py:58-71`) 응답에 그대로 노출되며, 응답
  docstring(`performance.py:66`)은 "외부 입출금 추정 (입금 +, 출금 −)"라고만 적혀 있어 소비자가
  이 값을 실제 입출금 시그널로 오인하기 쉽다.
- **매매 의사결정에는 미사용** — `net_external_cashflow`를 읽는 8영역·전략 코드는 없음(아래 grep
  결과, `__pycache__` 제외):

  ```
  src/db/daily_performance.py:29,50,56,65,72
  src/db/CLAUDE.md:54 (문서)
  src/engine/scheduler.py:3650
  src/routes/performance.py:66 (문서 주석)
  ```

  따라서 이 결함은 **리포트 정확도 문제**이지 매매 안전성 문제가 아니다. `domain-consult` 선행
  의무 대상("매매 행위를 바꾸는 코드 변경")에 해당하지 않는다 — 단, `scheduler.py` 접점 때문에
  8영역급 승인은 여전히 필요하다(§4).

---

## §2 KIS 필드 정본

### 2.1 확인된 사실

KIS 잔고조회(`inquire_balance`, TR_ID `TTTC8434R`/모의 `VTTC8434R`, URL
`/uapi/domestic-stock/v1/trading/inquire-balance`) output2의 공식 한글 필드명 매핑을
KIS 공식 GitHub 저장소(`examples_llm/domestic_stock/inquire_balance/chk_inquire_balance.py`의
`COLUMN_MAPPING` dict, `mcp__kis-code-assistant__read_source_code` 경유 확인)에서 다음을 확인:

| 필드 | 한글명 | 현재 코드 매핑 |
|------|--------|---------------|
| `dnca_tot_amt` | 예수금총금액 | `AccountSummary.deposit` (`src/api/balance.py:214`) |
| `nxdy_excc_amt` | 익일정산금액 | 미사용 |
| `prvs_rcdl_excc_amt` | 가수도정산금액 | 미사용 |
| `nass_amt` | 순자산금액 | `AccountSummary.net_asset` (`src/api/balance.py:217`) |
| `tot_evlu_amt` | 총평가금액 | `AccountSummary.total_eval_amount` (`src/api/balance.py:216`) |

로컬 캐시 `docs/kis/domestic-stock-order.md`(1865-1867행)에 주식잔고조회 응답 예시가 있고, 그
예시에서는 세 값이 우연히 모두 같다(`dnca_tot_amt=346455`, `nxdy_excc_amt=346455`,
`prvs_rcdl_excc_amt=346455` — 미결제 거래가 없는 예시로 추정). 반면 같은 문서의 "퇴직연금
예수금조회"(TTTC0506R, 258-330행) 예시에서는 `dnca_tota=57622382`와 `nxdy_excc_amt=11054042`가
**서로 다르다** — 두 필드가 실제로 다른 값을 가질 수 있음을 보여준다(다른 TR이라 직접 비교는
아니지만, "익일정산금액"이 "예수금총금액"과 독립적으로 변한다는 정황 증거).

### 2.2 확정 실패 — `prvs_rcdl_excc_amt` 정확한 산식

**KIS 공식 문서에서 "가수도정산금액"이라는 필드명 한글 매핑 이상의 상세 정의(계산식, 어떤
미결제 거래를 어떻게 반영하는지)를 찾지 못했다.** `mcp__kis-code-assistant__search_domestic_stock_api`
전문 검색과 로컬 `docs/kis/` 캐시 전수 grep 모두 필드명 매핑 수준에 그쳤다.

한글 용어("가수도"는 증권업계에서 "가지급·가수도" — 잠정/추정 결제를 뜻하는 관용어) 및 필드
배치(예수금총금액·익일정산금액·가수도정산금액이 연속으로 나열된 구조)로 미루어, "가수도정산금액"이
미결제(미체결 결제 대기) 거래를 가정산에 반영한 예수금 추정치일 **가능성이 높다고 추정**하지만,
이는 확정이 아니다.

**⚠️ 검증 대기.** 배포 후 실측(§6 D+1 절차)으로 이 필드가 실제로 T+2 결제 시차를 흡수하는지
확인해야 한다. 확인 실패 시 롤백(§6)한다.

### 2.3 대안 후보와 기각 사유

- `nxdy_excc_amt`(익일정산금액): 이름상 "다음 날" 시점이라 D+1 기준으로 보이며, 우리가 원하는
  "오늘 시점에서 미결제분까지 반영한 예수금"과는 창(window)이 다를 수 있다(추정). 1차 후보에서
  제외 — `prvs_rcdl_excc_amt`가 팀장 지시의 1차 후보였고, 정의 확정 실패로 두 필드 모두 배포 후
  실측 비교가 필요하다면 §7에서 병행 관찰을 제안한다.
- `nass_amt`(순자산금액): 예수금이 아니라 예수금+평가금액의 합이라 이 문제(예수금 자체의 시차)의
  직접 대안이 아니다. 다만 `total_asset` 분모로 이미 쓰이고 있어(§7 열린 질문) 별도로 T+2 지연
  여부를 확인해야 한다.

---

## §3 설계

**행위 변경 0** — 매매 진입·청산·수량·사이징·손절 규약 무접촉. 정산 기록(리포트)의 계산 기준만
바꾼다.

### 3.1 `AccountSummary` 필드 추가

`src/models/balance.py:28-35`:

```python
class AccountSummary(BaseModel):
    deposit: int               # dnca_tot_amt (예수금총금액)
    stock_eval_amount: int     # scts_evlu_amt (유가평가금액)
    total_eval_amount: int     # tot_evlu_amt (총평가금액)
    net_asset: int             # nass_amt (순자산금액)
    purchase_total: int        # pchs_amt_smtl_amt (매입금액합계)
    eval_total: int            # evlu_amt_smtl_amt (평가금액합계)
    profit_loss_total: int     # evlu_pfls_smtl_amt (평가손익합계)
    settled_deposit_d2: int = 0   # prvs_rcdl_excc_amt (가수도정산금액) — cycle275 신규, 옵션 기본 0
```

`src/api/balance.py:213-221` 파싱부에 1줄 추가:

```python
summary = AccountSummary(
    deposit=int(s.get("dnca_tot_amt", 0)),
    ...
    settled_deposit_d2=int(s.get("prvs_rcdl_excc_amt", 0)),   # 신규
)
```

기본값 0 + `.get(..., 0)` 폴백이라 키 부재(과거 응답 스키마·모의투자 차이 등)는 fail-open —
아래 leaf 함수가 0을 "신뢰 불가"로 취급해 방어한다(3.3절).

### 3.2 가산형 마이그레이션

신규 파일 `supabase/migrations/043_daily_performance_settled_deposit.sql`
(다음 사용 가능 번호 — 최신 파일 `042_daily_log_reports_external.sql` 확인, `ls
supabase/migrations/ | tail -1`):

```sql
-- cycle275: daily_performance 에 가수도정산금액(D+2 결제 반영 예수금) 기록 컬럼 추가
-- net_external_cashflow 계산 기준을 dnca_tot_amt(D+0)에서 prvs_rcdl_excc_amt 로
-- 교체하기 위한 선행 스키마. 기존 행은 NULL — 구 산식으로 기록된 값임을 구분하는 표식이다.
ALTER TABLE daily_performance
    ADD COLUMN IF NOT EXISTS settled_deposit BIGINT NULL;
```

가산형(NULL 허용 `ADD COLUMN`) — 사전 승인 범위의 DB 스키마 조건을 단독으로는 만족하지만,
`scheduler.py` 접점이 있어 사이클 전체는 승인 대상이다(§4).

### 3.3 신규 leaf `src/engine/settlement_cashflow.py`

```python
def compute_net_external_cashflow(
    today_settled: int | None,
    prev_settled: int | None,
    net_trade_today: float,
) -> tuple[float, str]:
    """가수도정산금액(prvs_rcdl_excc_amt) 기준 외부 입출금 추정.

    Δ가수도정산금액(D) - 오늘 매매순현금(D) 으로 계산한다. 이 필드가 실제로 미결제
    거래의 정산을 가정산 반영한다는 전제(§2.2, 확정 실패)가 성립해야 이 값이 T+0
    시차 없이 유효하다 — 배포 후 실측 검증 의무(cycle275 spec §6).

    reason 라벨:
    - "ok": 정상 계산
    - "no_prev": 전일 기록 부재(스키마 전환 첫날 등) — 0.0 반환, 계산하지 않음
    - "zero_settled": 오늘/전일 가수도정산금액이 0 또는 결측 — 신뢰 불가, 0.0 반환

    fail-open — 어떤 입력도 예외를 일으키지 않는다. DB/HTTP/시계 미접촉 순수 함수
    (quant_score.py/portfolio_risk.py 선례, 8영역 미접촉).
    """
    if prev_settled is None:
        return 0.0, "no_prev"
    if not today_settled or not prev_settled:
        return 0.0, "zero_settled"
    return float(today_settled - prev_settled) - net_trade_today, "ok"
```

- **순수 함수** — `quant_score.py`/`portfolio_risk.py`/`te_metrics.py` 선례와 동일하게 DB·HTTP·
  시계·8영역 미접촉. 호출자가 주입(pull).
- **전환 첫날(prev NULL)**: 신규 컬럼이 막 추가된 시점이므로 이전 행의 `settled_deposit`는
  NULL이다. `no_prev` 사유로 0을 기록하고, 호출자가 `[net_ext_cashflow_transition]` 마커를
  1회 발화한다(§6).
- **`zero_settled`**: 오늘 또는 전일 값이 0이면(키 부재 fail-open 0 포함) 델타를 신뢰할 수
  없으므로 0을 기록한다. 이 라벨이 잦게 나오면 §2.2의 확정 실패 리스크가 현실화된 것 —
  D+1 판독 대상(§6).
- **매수를 막지 않는다** — 이 함수의 반환값은 어떤 매매 분기에도 쓰이지 않는다(§1.3 grep 결과).
  fail-open 방향은 "잘못된 큰 값을 기록하지 않는다"이지 "매매를 막는다"가 아니다 — 정체성이
  다른 두 가지 fail-open 개념을 혼동하지 않는다(루트 CLAUDE.md `max_lot_units` 절의 K축/ρ축
  fail-open 방향 구분과 같은 원칙).

### 3.4 `scheduler.py` 접점 — 최소 라인

`_settle()`(`scheduler.py:3602`)의 기존 순서를 보존하며 다음만 바꾼다:

1. `prev_deposit` 계산 옆에 `prev_settled` 1줄 추가:
   ```python
   prev_settled = (
       int(prev_total["settled_deposit"])
       if prev_total and prev_total.get("settled_deposit") is not None
       else None
   )
   ```
2. `net_ext_cashflow = (float(summary.deposit) - prev_deposit) - net_trade_cashflow`
   (현 `scheduler.py:3632`) 를 leaf 호출로 교체:
   ```python
   net_ext_cashflow, _cashflow_reason = compute_net_external_cashflow(
       summary.settled_deposit_d2, prev_settled, net_trade_cashflow,
   )
   if _cashflow_reason == "no_prev":
       # 1회성 전환 마커 — daily_emit_cap 등 기존 cap 인프라 재사용
       ...
   ```
3. `upsert_daily_performance(...)` 호출(`scheduler.py:3645-3654`)에 `settled_deposit=` 인자
   1개 추가.

**순증 라인 수는 4~6행 수준**으로 추정(정확한 diff는 구현 사이클에서 확정). 현재 `scheduler.py`는
3,897행(`wc -l` 실측, 2026-09-11) — 상한 3,900행 대비 여유 3행뿐이라, 마커 발화·`prev_settled`
계산까지 scheduler.py 안에 다 넣으면 상한을 넘길 수 있다. **전환 마커 발화 로직(peek→로그→mark)은
leaf 쪽에 두고 scheduler.py는 leaf 호출 결과만 소비하는 방식으로 설계해야 한다** — 구현 사이클의
필수 제약으로 명시한다(§4).

### 3.5 구 행(NULL) 표시 후속 메모

`daily_performance.settled_deposit IS NULL`인 행은 구 산식(`dnca_tot_amt` 기준, D+0 가정)으로
기록된 `net_external_cashflow`다. 이번 사이클은 그 과거 행을 소급 정정하지 않는다(값 재계산은
`recompute_from_trades()`의 책임 범위 밖 — 그 함수는 실현손익만 재계산한다,
`src/db/daily_performance.py:107-124`). UI·리포트가 이 필드를 신뢰도 있게 보여주려면 별도
후속 사이클에서 `settled_deposit IS NULL`인 과거 행에 "구 산식(참고용)" 배지를 붙이는 작업이
필요하다 — 이번 명세의 범위 밖으로 남긴다.

---

## §4 승인 필요 항목

**이 사이클 전체가 승인 대상이다.** 이유:

1. `scheduler.py` 접점 변경 — 8영역은 아니나 라인 상한(<3,900행) 때문에 동일 승인 대상(루트
   `CLAUDE.md` "8영역" 절)이며, "여전히 승인이 필요한 것" 목록의 "8영역·`scheduler.py` 변경"에
   해당해 사전 승인 범위(무접촉 조건)를 벗어난다.
2. `AccountSummary`(모델)·`balance.py`(API 파싱) 변경은 8영역이 아니고 매매 행위도 바꾸지
   않지만, (1) 때문에 사전 승인 범위의 "8영역·scheduler.py 무접촉" 조건이 전체 사이클 단위로
   깨진다.

승인 시 확인해야 할 것:

- `compute_net_external_cashflow`의 fail-open 반환값(0.0, "zero_settled"/"no_prev")이 사용자
  의도와 맞는지 — 대안으로 "신뢰 불가 시 구 산식(dnca_tot_amt)으로 폴백"도 가능하다(이 명세는
  단순함과 관측 명확성을 위해 0 반환을 택했다. §3.3의 근거 참고).
- `scheduler.py` 순증 라인 수가 상한(3,900행)을 넘지 않도록 설계를 조정할 필요가 있는지(§3.4
  마지막 문단).
- 마이그레이션 파일 번호(043)가 구현 시점 최신 번호와 일치하는지 재확인(다른 병렬 작업이 먼저
  043을 점유했을 수 있음).

**배포 전 DB 선반영**은 이번 명세에 포함되지 않는다(cycle245 §7.1 K=20 선반영과 같은 사전
승인된 명세가 아니므로) — 통상 절차대로 승인 후 코드와 함께 배포한다.

---

## §5 Red 목록

최소 10건, 구현 사이클(tdd-engineer)이 그대로 착수할 수 있도록 파일명·케이스명·검증 내용을
명시한다.

1. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_ok_case_computes_delta_minus_net_trade`
   — 정상 입력(`today_settled=105, prev_settled=100, net_trade_today=3.0`) → `(2.0, "ok")`.
2. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_no_prev_returns_zero`
   — `prev_settled=None` → `(0.0, "no_prev")`, `today_settled`/`net_trade_today` 값 무관.
3. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_zero_today_settled_returns_zero`
   — `today_settled=0` (또는 `None`) → `(0.0, "zero_settled")`.
4. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_zero_prev_settled_returns_zero`
   — `prev_settled=0` → `(0.0, "zero_settled")`.
5. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_never_raises_on_bad_types`
   — 방어적 케이스: 비정상 입력(음수, 매우 큰 값)에도 예외를 던지지 않고 튜플 반환.
6. `tests/unit/engine/test_cycle275_settlement_cashflow.py::test_pure_function_no_side_effects`
   — DB/HTTP/시계 import 0건 AST 가드(`quant_score.py`/`portfolio_risk.py` 선례 패턴 답습).
7. `tests/unit/models/test_cycle275_account_summary_settled_deposit.py::test_default_zero_when_key_absent`
   — `AccountSummary(deposit=0, ..., )` (settled_deposit_d2 미지정) → 기본값 0, 기존 필드 전부
   정상 파싱(하위 호환).
8. `tests/unit/api/test_cycle275_balance_settled_deposit_parsing.py::test_parses_prvs_rcdl_excc_amt`
   — `get_balance()` mock 응답 output2에 `prvs_rcdl_excc_amt="12345"` 포함 → `summary.settled_deposit_d2 == 12345`.
9. `tests/unit/api/test_cycle275_balance_settled_deposit_parsing.py::test_missing_key_falls_back_to_zero`
   — output2에 `prvs_rcdl_excc_amt` 키 자체가 없는 legacy/모의투자 응답 → `settled_deposit_d2 == 0`
   (예외 없음).
10. `tests/unit/db/test_cycle275_migration_additive_guard.py::test_migration_is_add_column_nullable`
    — `043_daily_performance_settled_deposit.sql` 텍스트 파싱: `ADD COLUMN` 존재, `NOT NULL`
    부재, `DROP`/`ALTER COLUMN ... TYPE`/`UPDATE` 부재(가산형 강제 — cycle243/249 계열
    마이그레이션 가드 패턴 답습).
11. `tests/unit/ast/test_cycle275_scheduler_line_budget.py::test_scheduler_under_3900_lines`
    — `scheduler.py` 라인 수 < 3,900 (cycle257 영구 가드 재사용 패턴, `test_cycle272_ast_main_rest_basis.py`
    부류의 line-cap 가드 답습).
12. `tests/unit/ast/test_cycle275_settle_touch_scope.py::test_eight_areas_diff_zero_except_scheduler`
    — `git diff -- src/engine/{risk,order_engine,session,strategy_registry}.py src/api/order.py
    src/realtime/ src/auth/` = 0 (scanner.py는 무관, scheduler.py만 유일한 8영역급 접점임을
    고정).
13. `tests/unit/engine/test_cycle275_settle_calls_leaf.py::test_settle_delegates_to_compute_net_external_cashflow`
    — `scheduler._settle()`가 `settlement_cashflow.compute_net_external_cashflow`를 호출하는지
    monkeypatch로 검증(인라인 재구현 회귀 차단).
14. `tests/unit/engine/test_cycle275_settle_calls_leaf.py::test_settle_persists_settled_deposit_column`
    — `upsert_daily_performance` 호출 인자에 `settled_deposit=` 이 포함되는지 검증(스파이/mock).
15. `tests/unit/db/test_cycle275_daily_performance_settled_column.py::test_upsert_accepts_settled_deposit_kwarg`
    — `upsert_daily_performance(..., settled_deposit=12345)` 가 SQL 바인딩에 포함되는지(파라미터
    캡처 검증), 미지정 시 `None` 바인딩(하위 호환 — 기존 호출자 회귀 0).
16. `tests/unit/engine/test_cycle275_transition_marker.py::test_first_day_after_migration_emits_marker_once`
    — `prev_total.get("settled_deposit")`가 없는 첫 실행에서 `[net_ext_cashflow_transition]` 마커가
    정확히 1회 발화(freezegun/DailyEmitCap 패턴, 같은 날 재호출 시 재발화 0).
17. `tests/unit/engine/test_cycle275_synthetic_t2_scenario.py::test_synthetic_t2_settlement_series_residual_near_zero`
    — **실측 재현 대체**: 실제 16일치 `prvs_rcdl_excc_amt` 이력이 아직 없으므로(신규 필드,
    §7), T+2 결제를 흉내 낸 합성 시나리오(예: 매일 매수/매도 금액을 정해두고 "가수도정산금액이
    당일 매매를 즉시 반영한다"는 가정으로 합성 시계열을 만든 뒤 `compute_net_external_cashflow`를
    연속 호출)로 잔차가 0에 수렴하는지 확인. **이 테스트는 `prvs_rcdl_excc_amt`가 실제로 그렇게
    동작한다는 것을 증명하지 않는다** — 함수 자체의 산술이 의도대로 작동함만 검증한다. 실제 검증은
    §6 D+1 절차로 배포 후 수행한다.

---

## §6 관측·롤백·D+1

### 관측

- `[net_ext_cashflow_transition]` INFO 1회 — 스키마 전환 첫날(`prev_total.get("settled_deposit")
  is None`)에 leaf 또는 얇은 wrapper에서 발화. 이후 매일 미발화가 정상.
- `daily_performance.settled_deposit` 컬럼 값 자체가 주 관측 대상 — 매일 NULL이 아닌 값으로
  채워지는지 확인.
- (선택, 구현 사이클 판단) `_settle()` 기존 INFO 로그("일일 실적 저장: ...",
  `src/db/daily_performance.py:70-73`)에 `reason` 필드를 병기하면 `ok`/`no_prev`/`zero_settled`
  분포를 매일 grep으로 볼 수 있다 — `zero_settled`가 반복되면 §2.2 확정 실패 리스크가 현실화된
  신호.

### 롤백

- `scheduler.py`의 leaf 호출 4~6행을 이전 커밋으로 되돌리면 즉시 원복(구 산식 복원). leaf
  모듈(`settlement_cashflow.py`)과 마이그레이션 컬럼은 그대로 두어도 무해(미사용 상태로만
  남는다) — 별도 롤백 스위치 불필요.
- 마이그레이션은 가산형(NULL 허용)이라 컬럼을 남겨둬도 기존 읽기 경로에 영향 없음.

### D+1 판독 (배포 다음 영업일 20:10 정산 이후)

1. `daily_performance` 최신 `strategy='total'` 행의 `settled_deposit` 컬럼이 NULL이 아닌 정수
   값으로 채워졌는지 확인.
2. 배포 당일(전환 첫날) 로그에서 `[net_ext_cashflow_transition]`가 정확히 1행 발화했는지 확인
   (둘째 날부터는 미발화가 정상 — 배포 전후 grep 합산 금지).
3. `net_external_cashflow` 절대값이 §1.2 실측 중앙값(367,270원)보다 뚜렷이 작아지는지 확인 —
   단, 전환 후 첫 1~2영업일은 `no_prev`로 0이 찍히므로 유의미한 비교는 **3영업일째부터**.
4. `reason`(관측 로그에 병기했다면)의 `zero_settled` 발생 빈도 — 매일 반복되면 `prvs_rcdl_excc_amt`
   가 기대와 다르게 동작한다는 신호이므로 §2.2 재조사 및 §6 롤백 검토.
5. 사용자에게 그 기간 실제 입출금 여부를 재확인하고, 있었다면 그 금액과 기록값을 대조 —
   §1.2처럼 "무입출금 기간의 잔차"로 검증하는 것이 가장 깨끗하다.

---

## §7 열린 질문

1. **`prvs_rcdl_excc_amt` 정의 확정 실패**(§2.2) — KIS 공식 문서에서 필드명 매핑("가수도정산금액")
   이상의 산식 설명을 찾지 못했다. 배포 후 실측(§6)으로만 간접 검증 가능하다. 대안으로 KIS
   고객센터·공식 API 포럼 문의, 또는 `nxdy_excc_amt`와 병행 관찰(둘 다 기록해 어느 쪽이 T+2
   지연을 더 잘 설명하는지 비교)하는 방법이 있다 — 이번 명세는 후자를 채택하지 않았다(단일 필드
   전환이 관측을 단순하게 만든다는 판단), 필요시 후속 사이클에서 재검토.

2. **`nass_amt`(총자산) T+2 지연 여부 미확인** — `AccountSummary.net_asset`(`src/api/balance.py:217`,
   `daily_performance.total_asset`의 소스, `scheduler.py:3619,3647`)도 같은 방식으로 지연될 수
   있다면 일별 수익률(`daily_profit_rate = daily_realized_pnl / prev_total_asset`)의 분모가
   흔들린다. **읽기 전용 실측 절차 제안**:
   - 배포 후 무입출금이 확인된 기간에 대해 다음 SQL로 일별 `total_asset` 변화량을 뽑는다:
     ```sql
     SELECT date, total_asset,
            total_asset - LAG(total_asset) OVER (ORDER BY date) AS d_total_asset,
            daily_realized_pnl
     FROM daily_performance WHERE strategy='total' ORDER BY date DESC LIMIT 20;
     ```
   - 같은 기간 `trade_history`에서 그날 실현손익 + (보유 종목의 전일 대비 평가금액 변화)를
     별도로 추정하고, `d_total_asset`과 비교한다. `nass_amt`가 T+2 지연이 없다면 두 값이
     수수료 규모 이내로 일치해야 한다 — 만약 규칙적으로 D−2 방향으로 어긋난다면 `nass_amt`도
     같은 병리를 가진 것.
   - 평가금액 변화 추정에 필요한 종목별 일별 평가금액 이력이 DB에 없으므로(`AccountSummary`는
     스냅샷만, 과거 보유 종목별 평가금액을 일자별로 저장하지 않음), 이 절차는 완전 자동화가
     어렵고 **수작업 대조가 필요**하다 — 후속 사이클(별도 명세) 대상으로 남긴다.

3. **마이그레이션 번호 확정** — `043`은 이 명세 작성 시점(`042_daily_log_reports_external.sql`
   최신)의 다음 번호다. 구현 착수 시점에 다른 작업이 043을 먼저 점유했을 수 있으니 재확인 필요.

4. **`zero_settled`/`no_prev` fail-open 시 0 반환이 최선인가** — 대안으로 "신뢰 불가 시 구
   산식(`dnca_tot_amt` 기준)으로 자동 폴백"도 가능하다. 이 명세는 관측 단순성을 위해 0을
   택했지만, 사용자가 "폴백이 낫다"고 판단하면 §4 승인 시 반영한다.

---

**정의 확정 여부**: `prvs_rcdl_excc_amt`(가수도정산금액)는 KIS 공식 자료에서 필드명 매핑만
확인했고, 정확한 산식은 **확정하지 못했다** — 배포 후 실측 검증이 반드시 필요하다(§2.2, §6).
