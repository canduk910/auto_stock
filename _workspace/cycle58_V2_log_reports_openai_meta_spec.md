# 사이클 58 발주서 — V-2: `daily_log_reports` OpenAI 모델/토큰/비용 메타 컬럼

- **위험 등급**: LOW
- **매매 안전성 영향**: 0 (read-path 보강 + write-path metadata 추가만, 매수/매도 hot path 무관)
- **domain-expert 자문**: 미필요 (운영 가시성 메타 컬럼)
- **TDD 사이클**: tdd-engineer Red → backend-dev Green → tester Verify → team-leader 종료 검수
- **프론트엔드 영향**: 본 사이클 = backend 만 (V-2 후속 카드에서 프론트 표시 처리)
- **발주일**: 2026-06-04

---

## 1. 배경 및 목적

### 1-1. 현재 상태
- `daily_log_reports` 테이블은 `model VARCHAR(64)` 만 기록 (예: `gpt-5.4`).
- OpenAI 응답의 `usage` 객체 (`prompt_tokens` / `completion_tokens` / `total_tokens`) 미수집.
- API 호출 소요시간, 비용 추정치 미기록.
- **운영 결과**: 일일 OpenAI 사용량/비용 추적 불가, 모델 변경 시 비용 영향 측정 불가.

### 1-2. 사이클 53.1 사고 연관성
- `OPENAI_API_KEY 미설정 early return` → row 누락 → 메인 세션 수동 복구 (model='cycle53.1-metrics-only', 빈 summary/findings).
- V-2 가 *미리* 도입됐다면 비용/토큰도 같이 기록되어 운영 정량 진단 가능했을 것.
- 본 사이클 V-2 도입 후 6/1 row 의 정량 메타는 *없는 채* 보존 (다음 OpenAI 재집계 시점에 자연 채워짐).

### 1-3. 본 사이클 목표
1. OpenAI 응답 `usage` 객체 → `daily_log_reports` 3 컬럼 영속화
2. 호출 소요시간 (latency) 측정 + 영속화
3. 모델별 단가 dict 기반 비용 추정 (USD 단위 저장)
4. 후방 호환 (기존 row NULL 유지) + 회귀 가드 6~8 케이스

---

## 2. 결정 사항 (D-1 ~ D-8)

### D-1. 컬럼 정의 → **D-1-b 변형 (input/output 분리 + 호환 wrapper)**

분석 메모 D-1-a (3 컬럼) 와 D-1-b (세분화) 사이 선택:
- **결정**: input/output token 은 분리 저장한다. OpenAI billing 이 input/output 별도 단가이므로 분리 안 하면 비용 산식 검증 불가.
- **단, `retry_count`/`status` 는 본 사이클 제외** (현재 호출부에 retry 로직 없음, status 는 row 존재 자체가 success 의미). YAGNI 적용.

**최종 5 컬럼 (모두 NULL 허용)**:

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `prompt_tokens` | INTEGER | OpenAI 응답 `usage.prompt_tokens` |
| `completion_tokens` | INTEGER | OpenAI 응답 `usage.completion_tokens` |
| `total_tokens` | INTEGER | OpenAI 응답 `usage.total_tokens` (=prompt+completion 동일 보장 안 함, 응답 그대로 저장) |
| `latency_ms` | INTEGER | `chat.completions.create` 호출 elapsed milliseconds |
| `cost_estimate_usd` | NUMERIC(10, 6) | 모델별 단가 dict 기반 추정 (USD, 6자리 소수) |

### D-2. 비용 환산 통화 → **D-2-c (USD 저장)**

- **결정**: `cost_estimate_usd NUMERIC(10, 6)` 로 저장. KRW 환산은 조회 시점 (대시보드 UI 또는 후속 카드).
- 사유:
  1. OpenAI billing 은 USD 기준 — 정확한 비교 가능
  2. 환율 변동에 따른 stale 데이터 방지 (저장 시점 환율 ≠ 조회 시점 환율)
  3. 외부 의존 (환율 API) 0건

### D-3. 모델별 단가 → **D-3-a (모듈 상수 dict)**

- **결정**: `src/engine/log_analysis_engine.py` 내부 모듈 상수 `_OPENAI_PRICING_USD_PER_1K_TOKENS` dict 추가.
- 형식: `{model_name: (input_per_1k_usd, output_per_1k_usd)}`
- 초기 등록 모델 (현행 사용 + 마진):
  ```python
  _OPENAI_PRICING_USD_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
      # 2026-06 기준 OpenAI 공시 단가 (입력 / 출력 per 1K tokens, USD)
      "gpt-5.4":      (0.0050, 0.0150),  # 현행 디폴트
      "gpt-4o":       (0.0025, 0.0100),
      "gpt-4o-mini":  (0.00015, 0.00060),
      "gpt-4-turbo":  (0.0100, 0.0300),
      "gpt-4":        (0.0300, 0.0600),
      "gpt-3.5-turbo":(0.0005, 0.0015),
  }
  ```
- **모델 미등록 시 동작**: `cost_estimate_usd = None` 으로 INSERT. WARNING 로그 1행 `[openai_pricing_miss] model={name} — _OPENAI_PRICING_USD_PER_1K_TOKENS 등록 필요`.
- 사유: system_config DB 보관은 운영 가치 부족 (모델 추가 빈도 낮음). 코드 갱신 시 PR 가시화 효과 + 회귀 테스트 동행.

### D-4. OpenAI 응답 수집 위치 → **`_call_openai` 시그너처 확장**

**현재**:
```python
async def _call_openai(metrics: dict) -> dict:
    # 응답 dict 만 반환
```

**변경**:
```python
@dataclass
class _OpenAIMeta:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cost_estimate_usd: float | None = None

async def _call_openai(metrics: dict) -> tuple[dict, _OpenAIMeta]:
    # 응답 dict + 메타 동시 반환
```

- `time.monotonic()` 기반 latency 측정 (`chat.completions.create` 호출 전후).
- `response.usage` 객체 접근 (`prompt_tokens` / `completion_tokens` / `total_tokens`).
- `_compute_cost_usd(model, prompt_tokens, completion_tokens)` 헬퍼로 비용 추정.
- **모든 메타 필드는 graceful** — 예외 발생 시 해당 필드만 None, 다른 필드는 채움. 호출 자체 실패 시 메타 전부 None + 빈 dict 반환 (현재 동작 보존).

### D-5. 후방 호환성 → **자명 (NULL 허용)**

- 기존 row (사이클 53.1 등) 는 새 컬럼 NULL 로 유지.
- migration 은 `ALTER TABLE ... ADD COLUMN ... NULL` (NOT NULL 금지).
- `insert_log_report` 시그너처 확장 시 신규 파라미터는 keyword-only + default `None`.

### D-6. 회귀 가드 → **8 케이스 (신규 파일)**

신규 파일 `tests/unit/engine/test_log_analysis_openai_meta.py`:
1. `_compute_cost_usd` — 등록 모델 정확성 (gpt-5.4 기준 prompt=1000, completion=500 → 0.0050 + 0.0075 = 0.0125)
2. `_compute_cost_usd` — 미등록 모델 → None 반환 + WARNING 로그
3. `_compute_cost_usd` — prompt/completion None 입력 → None 반환 (zero division 방지)
4. `_call_openai` — 정상 응답 시 메타 5 필드 모두 채워짐 (mock `AsyncOpenAI` + `usage`)
5. `_call_openai` — `response.usage` 부재 시 토큰 필드 None, latency 는 채워짐
6. `_call_openai` — `chat.completions.create` 예외 시 빈 dict + 메타 전부 None
7. `_call_openai` — latency_ms 측정 정확성 (mock sleep 50ms → 50±20ms 허용)
8. `generate_daily_log_report` — `insert_log_report` 호출 시 5 신규 컬럼 keyword arg 포함 (mock spy)

신규 파일 `tests/unit/db/test_log_reports_openai_meta.py`:
9. `insert_log_report` — 5 신규 keyword 파라미터 default None 시 payload 에 None 포함
10. `insert_log_report` — 5 신규 파라미터 값 전달 시 payload 에 정확히 포함

총 10 케이스 (당초 6~8 예상 → 분리로 10).

### D-7. Migration 번호 → **`031_daily_log_reports_openai_meta.sql`**

기존 마지막: `030_strategy_funnel_snapshots.sql` → 다음 **031**.

```sql
-- 031_daily_log_reports_openai_meta.sql
-- 사이클 58 V-2: OpenAI 호출 메타 (토큰/비용/latency) 5 컬럼 추가.
-- 기존 row NULL 유지, 신규 row 부터 채움. NOT NULL 제약 금지 (후방호환).

ALTER TABLE daily_log_reports
    ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS total_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER,
    ADD COLUMN IF NOT EXISTS cost_estimate_usd NUMERIC(10, 6);

COMMENT ON COLUMN daily_log_reports.prompt_tokens IS
    'OpenAI 응답 usage.prompt_tokens (입력 토큰). 사이클 58 V-2';
COMMENT ON COLUMN daily_log_reports.completion_tokens IS
    'OpenAI 응답 usage.completion_tokens (출력 토큰). 사이클 58 V-2';
COMMENT ON COLUMN daily_log_reports.total_tokens IS
    'OpenAI 응답 usage.total_tokens. 사이클 58 V-2';
COMMENT ON COLUMN daily_log_reports.latency_ms IS
    'chat.completions.create 호출 elapsed milliseconds. 사이클 58 V-2';
COMMENT ON COLUMN daily_log_reports.cost_estimate_usd IS
    '모델별 단가 dict 기반 비용 추정 (USD, 6자리 소수). 사이클 58 V-2';
```

### D-8. 프론트엔드 영향 → **D-8-a (backend 만)**

- **결정**: 본 사이클은 backend 전용. 프론트 표시는 V-2 후속 카드.
- 사유: 단일 책임 원칙. 백엔드 데이터 수집 검증 → 운영 1주 데이터 누적 후 UI 디자인 결정.

---

## 3. 구현 명세

### 3-1. Migration 적용 (수동, EC2 직접)

**중요 — `deploy.yml` 자동 적용 메커니즘 없음**:
```yaml
# .github/workflows/deploy.yml 현행
script: |
  cd ~/auto_stock
  git pull origin main
  docker compose -f docker-compose.prod.yml up --build -d --remove-orphans
  docker image prune -f
```
→ Supabase migration 은 **수동 적용**.

**적용 순서** (운영자가 사용자 명시 commit/push 후 수행):
1. EC2 SSH → `cd ~/auto_stock && git pull` (이미 deploy.yml 이 수행)
2. Supabase Dashboard → SQL Editor → `supabase/migrations/031_daily_log_reports_openai_meta.sql` 내용 복사 + 실행
3. 검증 쿼리:
   ```sql
   SELECT column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_name = 'daily_log_reports'
     AND column_name IN ('prompt_tokens', 'completion_tokens', 'total_tokens', 'latency_ms', 'cost_estimate_usd');
   -- 5 행 반환 + 모두 is_nullable='YES' 확인
   ```
4. 다음 영업일 20:10 정산 시 신규 row 의 5 컬럼 자동 채움 확인

### 3-2. `src/db/log_reports.py` 변경

```python
async def insert_log_report(
    *,
    target_date: date,
    summary: str,
    findings: list[dict],
    metrics: dict,
    model: str | None,
    prompt_tokens: int | None = None,         # 신규
    completion_tokens: int | None = None,     # 신규
    total_tokens: int | None = None,          # 신규
    latency_ms: int | None = None,            # 신규
    cost_estimate_usd: float | None = None,   # 신규
) -> dict | None:
    payload = {
        "target_date": target_date.isoformat(),
        "summary": summary,
        "findings": findings,
        "metrics": metrics,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "cost_estimate_usd": cost_estimate_usd,
    }
    # 이하 동일 (try/except, 중복 핸들링)
```

### 3-3. `src/engine/log_analysis_engine.py` 변경

```python
import time
from dataclasses import dataclass


@dataclass
class _OpenAIMeta:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cost_estimate_usd: float | None = None


# 사이클 58 V-2: 모델별 단가 (USD per 1K tokens, input/output 분리).
# 신규 모델 추가 시 PR 가시화 효과 + 회귀 테스트 동행.
_OPENAI_PRICING_USD_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-5.4":       (0.0050, 0.0150),
    "gpt-4o":        (0.0025, 0.0100),
    "gpt-4o-mini":   (0.00015, 0.00060),
    "gpt-4-turbo":   (0.0100, 0.0300),
    "gpt-4":         (0.0300, 0.0600),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}


def _compute_cost_usd(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """모델별 단가 dict 기반 비용 추정 (USD).

    미등록 모델 또는 토큰 None 시 None 반환 + WARNING 로그.
    """
    if not model or prompt_tokens is None or completion_tokens is None:
        return None
    pricing = _OPENAI_PRICING_USD_PER_1K_TOKENS.get(model)
    if pricing is None:
        logger.warning(
            "[openai_pricing_miss] model=%s — _OPENAI_PRICING_USD_PER_1K_TOKENS 등록 필요",
            model,
        )
        return None
    in_per_1k, out_per_1k = pricing
    cost = (prompt_tokens / 1000.0) * in_per_1k + (completion_tokens / 1000.0) * out_per_1k
    return round(cost, 6)


async def _call_openai(metrics: dict) -> tuple[dict, _OpenAIMeta]:
    """OpenAI 호출 + 메타(토큰/latency/비용) 수집. 실패 시 빈 dict + 메타 None."""
    meta = _OpenAIMeta()
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다")
        return {}, meta

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_msg = (
        "아래는 당일 시스템 로그 집계와 거래 통계다.\n"
        "이를 보고 운영 개선 리포트를 위 스키마에 맞춰 JSON으로 작성하라.\n\n"
        + json.dumps(metrics, ensure_ascii=False, indent=2, default=str)
    )

    started = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=settings.openai_recommend_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        logger.exception("OpenAI 호출 실패 (log analysis)")
        meta.latency_ms = int((time.monotonic() - started) * 1000)
        return {}, meta

    meta.latency_ms = int((time.monotonic() - started) * 1000)

    # usage 메타 수집 (graceful)
    usage = getattr(response, "usage", None)
    if usage is not None:
        meta.prompt_tokens = getattr(usage, "prompt_tokens", None)
        meta.completion_tokens = getattr(usage, "completion_tokens", None)
        meta.total_tokens = getattr(usage, "total_tokens", None)
        meta.cost_estimate_usd = _compute_cost_usd(
            settings.openai_recommend_model,
            meta.prompt_tokens,
            meta.completion_tokens,
        )

    try:
        content = response.choices[0].message.content or "{}"
        return json.loads(content), meta
    except (json.JSONDecodeError, IndexError, AttributeError):
        logger.exception("OpenAI 응답 파싱 실패 (log analysis)")
        return {}, meta
```

**`generate_daily_log_report` 호출부 변경**:
```python
# 기존
try:
    raw = await asyncio.wait_for(_call_openai(metrics), timeout=60)
except asyncio.TimeoutError:
    logger.warning("OpenAI 호출 타임아웃 (log analysis)")
    raw = {}

# 신규
meta = _OpenAIMeta()
try:
    raw, meta = await asyncio.wait_for(_call_openai(metrics), timeout=60)
except asyncio.TimeoutError:
    logger.warning("OpenAI 호출 타임아웃 (log analysis)")
    raw = {}
    # meta 는 기본값 (전부 None) 보존

# ... (summary, findings 검증 동일)

# INSERT 시 5 신규 keyword 추가
row = await insert_log_report(
    target_date=target_date,
    summary=summary,
    findings=findings,
    metrics=metrics,
    model=settings.openai_recommend_model,
    prompt_tokens=meta.prompt_tokens,
    completion_tokens=meta.completion_tokens,
    total_tokens=meta.total_tokens,
    latency_ms=meta.latency_ms,
    cost_estimate_usd=meta.cost_estimate_usd,
)
```

---

## 4. TDD 사이클 진입 분배

### Phase 1 — tdd-engineer Red (실패 테스트 작성)
**산출물**:
- `tests/unit/engine/test_log_analysis_openai_meta.py` 8 케이스 (D-6 #1~#8)
- `tests/unit/db/test_log_reports_openai_meta.py` 2 케이스 (D-6 #9~#10)

**검증**: `pytest tests/unit/engine/test_log_analysis_openai_meta.py tests/unit/db/test_log_reports_openai_meta.py -v` → 10 FAIL (Red 확인)

### Phase 2 — backend-dev Green (최소 구현)
**산출물**:
1. `supabase/migrations/031_daily_log_reports_openai_meta.sql` 신규
2. `src/db/log_reports.py` — `insert_log_report` 5 keyword 파라미터 추가
3. `src/engine/log_analysis_engine.py`:
   - `_OpenAIMeta` dataclass 추가
   - `_OPENAI_PRICING_USD_PER_1K_TOKENS` 모듈 상수 추가
   - `_compute_cost_usd` 헬퍼 추가
   - `_call_openai` 시그너처 `→ tuple[dict, _OpenAIMeta]` 변경
   - `generate_daily_log_report` 호출부 + `insert_log_report` 호출부 5 keyword 추가

**검증**:
- `pytest tests/unit/engine/test_log_analysis_openai_meta.py tests/unit/db/test_log_reports_openai_meta.py -v` → 10 PASS
- `pytest -q` 전체 → 1748 + 10 = 1758 PASS (기존 회귀 0)

### Phase 3 — tester Verify
**검증 항목**:
1. Migration 031 dry-run (Supabase Dashboard SQL Editor 검증 쿼리) — 사용자 수동 적용 후 column 5건 + nullable 확인
2. `_compute_cost_usd` 단위 정확성: gpt-5.4 / prompt=10000 / completion=2000 → (10*0.005 + 2*0.015) = 0.080 USD (수기 계산 일치)
3. `_OpenAIMeta` graceful: `response.usage = None` 시 latency 만 채워지고 토큰/비용 None
4. 후방 호환: 기존 row (사이클 53.1) 조회 시 새 컬럼 NULL 정상 반환
5. `insert_log_report` 기존 호출자 (다른 모듈에서 호출하지 않음 — `log_analysis_engine` 단독) 영향 0건 확인 (grep)
6. `_workspace/00_leader_trading_rules.md` — V-2 변경 사항 동기화 (운영 메타 컬럼 추가 명시)

### Phase 4 — team-leader 종료 검수
- 회귀 가드 10 케이스 PASS 확인
- migration 파일명 / 컬럼명 / 단가 dict 초기값 검토
- `docs/HARNESS_CHANGELOG.md` 사이클 58 행 추가 권고 (사용자 commit 시점에 동행)
- `src/db/CLAUDE.md` `log_reports.py` 섹션 갱신 (5 신규 컬럼 명시) — backend-dev 가 Green 단계에서 동행

---

## 5. 제약 사항

1. **커밋/푸시**: 사용자 명시 시에만. tdd-engineer Red → backend-dev Green → tester PASS 까지 진행 후 사용자에게 commit 승인 요청.
2. **Migration 적용**: `deploy.yml` 자동 적용 없음. 사용자가 `commit & push` 후 별도로 Supabase Dashboard 수동 실행 필요.
3. **매매 안전성**: hot path 무영향. 단, `generate_daily_log_report` 20:10 정산 직후 호출 — KRX 마감(15:30) 이후 + NXT 19:50 buy_stop 이후라 매매 0건 시점. 안전.
4. **타임아웃**: 기존 60s 타임아웃 보존. 타임아웃 발생 시에도 latency_ms 측정 가능하나 신뢰성 낮음 → 본 사이클은 `asyncio.TimeoutError` 시 meta 기본값 (전부 None) 유지. 다음 사이클에서 timeout 표시 컬럼 추가 검토.
5. **단가 갱신**: OpenAI 가격 변동 시 `_OPENAI_PRICING_USD_PER_1K_TOKENS` 코드 갱신 PR 별도 사이클. 본 사이클 범위 외.

---

## 6. 다음 액션

- **자동 진행**: tdd-engineer 에게 SendMessage 로 Red 단계 지시
- **사용자 확인 의뢰 시점**:
  1. backend-dev Green PASS 후 — commit/push 승인 요청
  2. commit/push 완료 후 — Supabase Dashboard 수동 migration 적용 안내
  3. 다음 영업일 (2026-06-05) 20:10 정산 후 — 신규 row 5 컬럼 채움 검증 결과 보고

---

## 7. 파일 변경 요약

| 파일 | 변경 | 비고 |
|------|------|------|
| `supabase/migrations/031_daily_log_reports_openai_meta.sql` | 신규 | ALTER TABLE 5 컬럼 추가 (NULL 허용) |
| `src/db/log_reports.py` | 수정 | `insert_log_report` 5 keyword 파라미터 추가 |
| `src/engine/log_analysis_engine.py` | 수정 | `_OpenAIMeta` + `_OPENAI_PRICING_USD_PER_1K_TOKENS` + `_compute_cost_usd` + `_call_openai` 시그너처 변경 + 호출부 갱신 |
| `tests/unit/engine/test_log_analysis_openai_meta.py` | 신규 | 8 케이스 |
| `tests/unit/db/test_log_reports_openai_meta.py` | 신규 | 2 케이스 |
| `src/db/CLAUDE.md` | 수정 | log_reports 섹션 5 컬럼 명시 |
| `_workspace/00_leader_trading_rules.md` | 수정 | V-2 운영 메타 명세 동기화 (사이클 58 행 추가) |
| `docs/HARNESS_CHANGELOG.md` | 수정 | 사이클 58 행 추가 (사용자 commit 시점) |
