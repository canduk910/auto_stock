# 사이클 20 — 토큰 발급 분당 1개 한도 위반 차단

작성일: 2026-05-20 (팀장)
명령 출처: 사용자 직접 지시 + 운영 결함 진단

## 1. 진단 (트레이더 관점)

### 1.1 KIS 명시 한도

- `/oauth2/tokenP` (접근토큰 발급): **분당 1개 / 전역** (사용자 인용 2026-05-20)
- 위반 시 즉시 `403 Forbidden` 응답 + LMS 경고 + 앱키 일시 정지 가능성

### 1.2 운영 결함 (2026-05-20 10:40:31 사고)

boot 직후 4 매니저가 거의 동시에 발급:
- 메인 매니저 (`token_manager`) — `main.py lifespan` 호출
- 보조 `quote-sub-1` / `quote-gold` / `quote-isa` — `scheduler._boot()` lazy 발급

→ KIS 분당 1개 한도 위반 → 일부 매니저 **403 Forbidden** → VB 일봉 fetch 8+ 종목 영향 → 매수 후보 prepare 불완전.

### 1.3 결함 3 계층

| 계층 | 결함 | 영향 |
|------|------|------|
| A | Docker 캐시 미영속화 (`./logs:/app/logs` 만 마운트) | 컨테이너 재기동마다 `.token_cache*.json` 미스 → 4 매니저 모두 신규 발급 |
| B | `issue()` 모듈 전역 직렬화 0 (`asyncio.Lock` 없음 + rate-limit gap 없음) | 동시 호출 시 KIS 한도 위반 |
| C | boot 시점 사전 순차 발급 부재 | 메인 + 보조 lazy 호출이 비동기로 산개 |

## 2. 변경 명세 (3 영역)

### 2.1 A — Docker 캐시 영속화

**대상**: `docker-compose.yml`, `docker-compose.prod.yml`, `.gitignore`

**근거**: `_TOKEN_CACHE_PATH = Path(".token_cache.json")` + `_QUOTE_TOKEN_CACHE_PREFIX = ".token_cache_quote_"` → CWD 기준 상대 경로. 컨테이너 내 `/app/.token_cache.json`, `/app/.token_cache_quote_<label>.json` 저장.

**Step 1**: 경로 변경 안 함 (마이그레이션 위험). 대신 *디렉토리 단위 마운트* 추가 — `/app/.token_cache/` 디렉토리로 전환:

token.py 변경:
```python
# 사이클 20 (2026-05-20) — Docker 볼륨 영속화를 위해 디렉토리 단위 경로
_TOKEN_CACHE_DIR = Path(".token_cache")
_TOKEN_CACHE_PATH = _TOKEN_CACHE_DIR / "main.json"   # 메인 (기존 .token_cache.json 호환 fallback)
_QUOTE_TOKEN_CACHE_PREFIX = "quote_"                 # 디렉토리 내 prefix (기존 .token_cache_quote_ 호환 fallback)
```

호환성 처리: `_load_cache()` 첫 호출 시
- 새 경로 (`/app/.token_cache/main.json`) 존재 → 우선 사용
- 미존재 + 구 경로 (`/app/.token_cache.json`) 존재 → 구 경로에서 로드 + 새 경로로 즉시 마이그레이션 + 구 경로 unlink
- 보조 매니저도 동일 패턴

**Step 2**: Docker volumes 추가 (개발/운영):

`docker-compose.yml`:
```yaml
volumes:
  - ./src:/app/src
  - ./logs:/app/logs
  - ./.env:/app/.env:ro
  - ./.token_cache:/app/.token_cache  # 사이클 20 — 토큰 캐시 영속화 (분당 1개 한도 대응)
```

`docker-compose.prod.yml`:
```yaml
volumes:
  - ./logs:/app/logs
  - ./.token_cache:/app/.token_cache  # 사이클 20 — 토큰 캐시 영속화
```

**Step 3**: `.gitignore` 갱신:
```
.token_cache.json    # 기존 (호환)
.token_cache/        # 사이클 20 — 신규 디렉토리 단위
```

**Step 4**: 호스트 디렉토리 사전 생성 — Docker 마운트 시 Docker가 자동 생성하지만 명시적으로 생성하여 권한 이슈 차단.

### 2.2 B — 모듈 전역 발급 직렬화 (`src/auth/token.py`)

**Step 1**: 모듈 전역 상수 + lock + 마지막 발급 시각:

```python
import time
_GLOBAL_ISSUE_LOCK: asyncio.Lock | None = None  # lazy create
_LAST_ISSUE_AT: float = 0.0                      # time.monotonic()
_ISSUE_GAP_SECS: float = 61.0                    # 분당 1개 보장 (1초 마진)


def _get_global_issue_lock() -> asyncio.Lock:
    global _GLOBAL_ISSUE_LOCK
    if _GLOBAL_ISSUE_LOCK is None:
        _GLOBAL_ISSUE_LOCK = asyncio.Lock()
    return _GLOBAL_ISSUE_LOCK


def reset_global_issue_state() -> None:
    """테스트 전용 — 모듈 전역 lock + 마지막 발급 시각 초기화."""
    global _GLOBAL_ISSUE_LOCK, _LAST_ISSUE_AT
    _GLOBAL_ISSUE_LOCK = None
    _LAST_ISSUE_AT = 0.0
```

**Step 2**: `issue()` 직렬화 + gap 강제:

```python
async def issue(self) -> None:
    """POST /oauth2/tokenP 로 접근토큰을 발급받는다.

    사이클 20 (2026-05-20) — 모듈 전역 직렬화 + 60s gap (KIS 분당 1개 한도).
    """
    global _LAST_ISSUE_AT
    async with _get_global_issue_lock():
        elapsed = time.monotonic() - _LAST_ISSUE_AT
        if _LAST_ISSUE_AT > 0 and elapsed < _ISSUE_GAP_SECS:
            wait_secs = _ISSUE_GAP_SECS - elapsed
            logger.info(
                "[token] 분당 한도 대기: label=%s wait=%.1fs",
                self._label or "main", wait_secs,
            )
            await asyncio.sleep(wait_secs)
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        self.access_token = data["access_token"]
        self.token_expired = datetime.strptime(
            data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S"
        )
        self._save_cache()
        _LAST_ISSUE_AT = time.monotonic()
        logger.info(
            "토큰 발급 완료(label=%s), 만료: %s", self._label or "main", self.token_expired,
        )
```

**핵심 보안**:
- Lock 안에서 sleep — 다음 매니저는 자연 대기
- `_LAST_ISSUE_AT` 갱신 위치: HTTP POST *성공 후*. 실패 시 갱신 안 함 (다음 호출은 재발급 시도 가능)
- `_is_valid()` 캐시 hit 면 `issue()` 자체 호출 안 됨 → sleep + lock 둘 다 skip

**Step 3**: `get_approval_key()` — WebSocket 접속키. 동일 한도 적용되는지 사용자 명시 안 했으나 보수적으로 분리 lock 검토. 사이클 20 본 작업에서는 **별도 lock 미적용** (사용자 요구 외 변경 최소화), 회귀 테스트 1건만 추가하여 미적용 사실을 명문화.

### 2.3 C — boot 시점 사전 순차 발급 (`src/engine/scheduler.py`)

**Step 1**: `TradingScheduler._preissue_all_tokens()` 신규 메서드:

```python
async def _preissue_all_tokens(self) -> None:
    """사이클 20 (2026-05-20) — 모든 매니저 토큰 사전 순차 발급.

    캐시 hit 면 즉시 return. miss 면 모듈 전역 lock 안에서 60s gap 강제 직렬화.
    보조 매니저 발급 실패는 메인 흐름 보존 (try/except 흡수).
    """
    from src.auth.token import token_manager, get_token_manager
    from src.db import kis_quote_accounts as kqa

    # 1) 메인 매니저
    try:
        await token_manager.get_token()
    except Exception:
        logger.exception("[boot_preissue] main 토큰 발급 실패 — 메인 흐름 보존")

    # 2) 보조 매니저 list (active=true)
    try:
        accounts = await kqa.list_accounts(active_only=True)
    except Exception:
        logger.exception("[boot_preissue] kis_quote_accounts list 실패 — 보조 skip")
        return

    for account in accounts:
        try:
            manager = await get_token_manager(account.label)
            await manager.get_token()  # 캐시 hit 면 즉시 return, miss 면 lock 안에서 60s 대기
            logger.info("[boot_preissue] label=%s 사전 발급 완료", account.label)
        except Exception:
            logger.exception("[boot_preissue] label=%s 발급 실패 — 다음 보조로 진행", account.label)
```

**Step 2**: `_boot()` 진입 초입에 호출:

```python
async def _boot(self) -> None:
    """시스템 기동: ..."""
    # 사이클 20 (2026-05-20) — 모든 매니저 토큰 사전 순차 발급 (KIS 분당 1개 한도)
    await self._preissue_all_tokens()

    # 기존 흐름 보존 (token_manager.get_token() 는 캐시 hit 면 즉시 return)
    await token_manager.get_token()
    # ...
```

**Step 3**: `lifespan` 의 `token_manager.get_token()` 호출은 그대로 유지 — 캐시 hit 시 0초.

**효과**:
- 캐시 hit: 0초 boot 추가
- miss (재기동 첫 회): 메인 1회 + 보조 N × 60s = N분 boot 지연. 07:50 _boot 라 KRX 메인 시간 영향 0
- 향후 매일 보조 토큰 24h 만료 자동 갱신 시 자연스럽게 순차 직렬화

## 3. 신규 회귀 가드 (7 케이스)

### 3.1 `tests/unit/auth/test_token_global_serialization.py` (신규 5 케이스)

| ID | 케이스 | 단언 |
|----|--------|------|
| A | Lock 직렬화 | 동시 2 매니저 `issue()` 호출 시 두 번째는 60s 대기 후 실행 (mock httpx + freezegun + asyncio.gather) |
| B | gap 강제 | 첫 발급 직후 두 번째 호출 시 `_ISSUE_GAP_SECS` 미달이면 `asyncio.sleep` 호출됨 |
| C | gap 충분히 지남 | `_LAST_ISSUE_AT` 후 61s+ 경과 → sleep 호출 안 함 + 즉시 발급 |
| D | 캐시 hit 시 issue() skip | `_is_valid()=True` 면 `get_token()` 이 `issue()` 호출 안 함 (httpx mock 0회) |
| E | gather race 직렬화 | `asyncio.gather(mgr1.issue(), mgr2.issue())` 2 호출이 순차 실행 + 두 번째 sleep 호출 |

### 3.2 `tests/unit/engine/test_boot_preissue_tokens.py` (신규 2 케이스)

| ID | 케이스 | 단언 |
|----|--------|------|
| F | 메인 + 보조 N 순차 발급 | `_preissue_all_tokens()` 호출 시 메인 + 보조 N 매니저 `get_token()` 호출됨 (mock) |
| G | 보조 1개 발급 실패 graceful | 보조 매니저 1개 `issue()` 예외 raise → 다음 보조로 진행 + 메인 흐름 영향 0 |

### 3.3 회귀 가드 구현 가이드 (tdd-engineer 에게)

- `asyncio.sleep` mock: `monkeypatch.setattr("asyncio.sleep", AsyncMock())` 후 `assert_awaited_once_with(<expected_secs>)`. 실제 60s 대기 금지 (테스트 속도)
- `time.monotonic` mock: `monkeypatch.setattr("src.auth.token.time.monotonic", lambda: <value>)` 로 시점 고정
- `_LAST_ISSUE_AT` 초기화: 각 테스트 setup 에서 `reset_global_issue_state()` 호출
- httpx mock: `respx.mock` 또는 단순 `monkeypatch.setattr` 로 `httpx.AsyncClient` 후킹 — KIS 더미 응답
- 보조 매니저 자격증명: DB `kqa.get_credentials_for_token_manager(label)` mock 으로 `{"app_key": "...", "app_secret": "...", "kis_env": "vts"}` 반환
- 캐시 격리: `isolated_cache` fixture 패턴 활용 (기존 `test_token.py` 참고)

## 4. 검증 명령

```bash
# 신규 회귀 가드
python -m pytest tests/unit/auth/test_token_global_serialization.py \
                 tests/unit/engine/test_boot_preissue_tokens.py -v
# 기대: 7 신규 케이스 모두 pass

# 백엔드 전체 회귀
python -m pytest -q
# 기대: 1395 + 7 = 1402 passed, 회귀 0

# 영향 인덱스
python tools/test_impact/build_index.py
```

## 5. 문서 동기화 (sync-docs 스킬)

- `src/auth/CLAUDE.md` — token.py 절: 분당 1개 한도 + 모듈 전역 직렬화 (`_GLOBAL_ISSUE_LOCK` + `_ISSUE_GAP_SECS=61.0`) + 디렉토리 단위 캐시 + 호환 fallback
- `src/engine/CLAUDE.md` — `_boot()` 흐름에 `_preissue_all_tokens()` 단계 추가
- `CLAUDE.md` (루트) — Docker 구성 절: `./.token_cache:/app/.token_cache` 볼륨 추가 + `.gitignore` 추가
- `docs/HARNESS_CHANGELOG.md` — 사이클 20 1행

## 6. 안전 원칙

- **자금 안전 절대 원칙 보존** — 메인 매니저 매매 흐름 그대로 (token.py 가 lock 안에서 발급, 캐시 hit 면 lock 자체 거치지 않음 → 운영 정상 흐름에서 sleep 없음)
- **사이클 17/18/6/19/빌드핫픽스 보존**
- **token.py 의 매니저 격리 캐시 그대로** — 디렉토리 단위 마운트 + 호환 fallback 으로 운영 중단 0
- **TDD** — tdd-engineer Red → backend-dev Green → tester 검증
- **한글 커밋 메시지**: `fix(auth): 토큰 발급 분당 1개 한도 직렬화 + 사전 순차 + 캐시 영속화 (사이클 20)`
- **push 사용자 별도 명시 승인 후** — 현재 KRX 메인 시간대 (11:00+ KST). boot 변경이 큰 작업이라 익일 07:50 boot 전 push 강력 권장

## 7. 시간 추정

- 코드 변경 (Docker 포함) ~2시간
- 회귀 가드 7 케이스 작성 + Red→Green ~1시간
- 문서 동기화 + 커밋 ~30분
- 전체 ~3.5시간

## 8. 보고 항목 (완료 후)

1. 변경 파일 / LOC (Docker 포함)
2. 신규 회귀 가드 7 케이스 pass 결과
3. 전체 백엔드 회귀 카운트 (1395 → 1402 기대)
4. 커밋 해시
5. sync-docs 결과
6. **push 권장 시점** — KRX 메인 마감 후 (15:30+) 또는 익일 07:50 boot 전. 본 사이클은 boot 변경이 큰 작업이라 익일 boot 전 권장
7. 운영 효과 요약 (캐시 hit 율 + 발급 race 차단 + 분당 발급 카운트 ≤ 1)
