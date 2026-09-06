# 자문 — 시세 회선 재연결 규약 시정 (카드 ②, F-2 · F-3)

- 작성: 2026-09-06 (일) 저녁, 장외
- 의뢰: 카드 ② 승인 완료. 질문은 "해도 되나" 가 아니라 **"어떻게 해야 안전한가"**
- 원칙: 코드·DB·설정·git **무수정**. 운영 DB SELECT / 운영 컨테이너 `python -c` 읽기만
- 정본 인용: `_workspace/analysis/wake_0500_20260906/kis_constraints.md` §1.4 (F-2·F-3 발견)

---

## 0. 권고 요약 (한 문단)

**F-2 는 잡는 예외를 넓히는 것으로 끝나지 않는다 — 넓혀도 `_trigger_auto_restart` 가 cooldown·cap 에
걸리면 `break` 로 여전히 죽는다. 그러므로 시정의 골자는 "connect 루프를 불사(不死)로 만들고, 그 대가로
연결 시도 자체에 하드 레이트 상한을 씌우는 것" 이다.** 예외 튜플은 `websockets.WebSocketException` +
`httpx.HTTPError` + `OSError` + `ValueError` + `KeyError` 로 넓히고(현행 3종의 상위집합이므로 순수 확장),
그 뒤에 `except Exception` 최후 그물을 CRITICAL 마커와 함께 하나 더 두어 **무증상 사망을 구조적으로
불가능하게** 만든다(`CancelledError` 는 `BaseException` 이라 `except Exception` 에 **안 걸린다** — 운영
컨테이너 실측 확인, 종료 경로는 그대로 산다). F-3 은 `_reconnect_count` 리셋 규약을 **건드리지 않는다** —
그 카운터는 "연속 핸드셰이크 실패" 라는 다른 뜻이고, heartbeat 경로를 거기 태우면 15:0x/15:2x/15:4x 의
시장 침묵마다 8세션이 동시에 `stop()→start()` 를 하게 되어 cycle241 이 한 사이클 들여 없앤 오탐이
부활한다. 대신 **세션별 슬라이딩 1시간 연결 예산**(soft 12 / hard 24, 초과 시 30초 → 300초 단계 throttle,
**멈추지 않고 느려질 뿐**)을 `while` 루프 진입 지점 **한 곳**에 넣어 heartbeat·clean close·예외·auto-restart
**네 경로를 하나의 계량기로** 덮는다. 실측 기준선은 세션당 **시간 최대 2회 · 하루 3.1~5.1회**(`/oauth2/Approval`
발급 로그가 label 을 달고 있어 이것이 연결 시도의 정확한 카운터다) 이므로 soft 12 는 **6배 여유**다.
`/oauth2/Approval` 캐시는 **이번 사이클에 넣지 말 것을 권고한다** — 예산이 서면 KIS REST 부하는 전역
시간당 최대 96회로 이미 무해해지고(현재 하루 41회), approval_key 의 재사용 가능 여부·수명은 KIS 문서에도
공식 샘플에도 **없어서**(전수 확인) 캐시가 틀리면 전 세션이 안 붙는 정반대 사고가 된다. 배포는
**월요일 개장 전에 하지 말 것을 권고한다** — 이 두 결함은 30일 실측 발화 **0건**(`최대 재연결 횟수 초과` 0 ·
`[ws_auto_restart]` 0 · `_ws is None` 0 · heartbeat 연속 2회 0)인데 변경 대상은 8영역 `websocket.py` 의
연결 루프 그 자체라 **배포 실수 확률이 결함 실현 확률보다 훨씬 높고**, 오늘 이미 올린 cycle262(09:00~09:01:30
진입 보류)와 **정확히 같은 시각 창**에서 겹쳐 월요일 아침 이상의 원인 분리가 불가능해진다.

---

## 1. F-2 — 어떤 예외를 잡아야 하는가

### 1.1 운영 컨테이너 실측 (python 3.12.14 / websockets 14.2 / httpx 0.28.1)

```
WebSocketException  mro=[WebSocketException, Exception]           OSError? False
ConnectionClosed    mro=[ConnectionClosed, WebSocketException]    OSError? False   WSExc? True
InvalidURI          mro=[InvalidURI, WebSocketException]          OSError? False   WSExc? True   ← 중요
InvalidStatus       mro=[InvalidStatus, InvalidHandshake, WSExc]  OSError? False   WSExc? True
InvalidMessage      mro=[InvalidMessage, InvalidHandshake, WSExc] OSError? False   WSExc? True
SecurityError / ProtocolError / ConcurrencyError / PayloadTooBig  전부 WSExc? True

httpx.HTTPError        [HTTPError, Exception]                              OSError? False
httpx.HTTPStatusError  [HTTPStatusError, HTTPError]                        OSError? False
httpx.ConnectError     [ConnectError, NetworkError, TransportError, ...]   OSError? False   ← 중요
httpx.ReadTimeout      [ReadTimeout, TimeoutException, TransportError, ...] OSError? False  ← 중요

asyncio.TimeoutError is TimeoutError : True     TimeoutError ⊂ OSError : True
ssl.SSLError ⊂ OSError : True                   ssl.SSLCertVerificationError ⊂ OSError : True
json.JSONDecodeError ⊂ ValueError : True
asyncio.CancelledError ⊂ Exception : False      ⊂ BaseException : True
```

**정본이 놓친 확장 사실 두 가지:**

1. **`InvalidURI` 는 이미 `WebSocketException` 하위다.** 현행 튜플 `(ConnectionClosed, InvalidURI, OSError)`
   중 앞 둘이 통째로 `WebSocketException` 에 포섭되므로, `WebSocketException` 으로 바꾸는 것은
   **순수 확장**이다(잡던 것을 하나도 잃지 않는다). 회귀 표면이 0 이라는 뜻이다.
2. **문제는 "HTTP 상태 거부" 만이 아니다.** `httpx.ConnectError` / `ReadTimeout` / `ConnectTimeout` 도
   `OSError` 가 **아니다**. 즉 `/oauth2/Approval` POST 중 **평범한 네트워크 끊김 한 번**으로도 세션이
   무증상 사망한다. F-2 의 사정거리는 정본이 적은 "점검 시간대 403/503" 보다 넓다 —
   **DNS 흔들림, EC2 NAT 순단, KIS LB 리셋 전부 해당**한다.

### 1.2 확정 코드 — 정확한 튜플

```python
# src/realtime/websocket.py 모듈 상수 영역 (신규)
import httpx  # 신규 import — token.py 가 이미 의존, requirements 변경 0

# 재시도 대상 = 연결/핸드셰이크/접속키 발급의 "정상적 실패" 계열.
# 현행 (ConnectionClosed, InvalidURI, OSError) 의 **상위집합** — 잡던 것을 하나도 잃지 않는다.
_RETRYABLE_CONNECT_ERRORS: tuple[type[BaseException], ...] = (
    websockets.WebSocketException,  # ConnectionClosed·InvalidURI·InvalidStatus·InvalidHandshake
                                    # ·InvalidMessage·SecurityError·ProtocolError·ConcurrencyError
    httpx.HTTPError,                # /oauth2/Approval 의 HTTPStatusError(403/503)
                                    # + ConnectError/ReadTimeout/ConnectTimeout (전부 OSError 아님)
    OSError,                        # TCP/DNS/ssl.SSLError/TimeoutError(=asyncio.TimeoutError, 3.11+)
    ValueError,                     # resp.json() → json.JSONDecodeError
    KeyError,                       # data["approval_key"] 키 부재 (KIS 응답 스키마 변경)
)
```

`connect()` 의 except 절 배치:

```python
            except _RETRYABLE_CONNECT_ERRORS as e:
                await self._on_connect_failure(e, kind="retryable")   # 현행 블록 그대로 위임
            except asyncio.CancelledError:
                raise                       # 종료 경로 보존 (BaseException 이라 아래에 안 걸리지만 명시)
            except Exception as e:          # 최후 그물 — "무증상 사망" 을 구조적으로 불가능하게
                logger.critical(
                    "[ws_connect_unexpected] label=%s kind=%s err=%s",
                    self._label, type(e).__name__, e, exc_info=True,
                )
                await self._on_connect_failure(e, kind="unexpected")
```

### 1.3 `except Exception` 으로 넓히는 것이 위험한가 — 의뢰 전제의 정정

> 의뢰문: "`except Exception` 로 넓히면 `CancelledError` 를 삼켜 종료가 막힌다
> (`CancelledError` 는 3.8+ 에서 `BaseException`)"

**논리가 뒤집혀 있다.** `CancelledError` 가 `BaseException` 직속이기 **때문에** `except Exception` 은
그것을 **잡지 못한다**(위 실측: `CancelledError ⊂ Exception : False`). 즉 `except Exception` 은
취소 안전성 관점에서 **안전하다**. 이 정정은 중요하다 — 이 전제 때문에 최후 그물을 포기하면
F-2 는 "지금 아는 예외 목록" 만 막고 **다음번 새 예외 타입에 다시 열린다**.

진짜 위험은 다른 데 있다: `except Exception` + 재시도는 **프로그래밍 오류**(리팩터가 만든
`AttributeError`·`TypeError`)를 조용한 무한 재시도로 바꾼다. 그래서 최후 그물은
**(a) CRITICAL 레벨 + 전용 마커 `[ws_connect_unexpected]` + `exc_info=True`** 로 시끄럽게 하고,
**(b) throttle 계량기를 똑같이 통과**시켜 폭주를 막는다. 이 두 조건이면 "조용한 무한 재시도" 는
성립하지 않는다.

### 1.4 무증상 사망이 실제로 어떻게 보이는가 — `self._ws` 잔존이 위장한다

코드 추적 (`websocket.py:210-261`):

- `async with websockets.connect(...) as ws:` 진입 시 `self._ws = ws` 대입. **블록 이탈 시 clear 하지 않는다.**
  `self._ws = None` 은 `while` 루프를 **정상적으로 빠져나온 뒤**(:261)에만 실행된다.
- 따라서 **예외가 `while` 밖으로 탈출하면 `self._ws = None` 은 영원히 실행되지 않는다.**

두 갈래로 결과가 다르다:

| 사망 시점 | `self._ws` | 외부에서 보이는 것 |
|---|---|---|
| **첫 연결**(`__init__` 직후) | `None` | `_available_quotes()` 가 제외 · `[silent_inactive_force_reconnect] _ws is None — skip` WARNING → **관측 가능** |
| **재연결 도중**(한 번이라도 붙은 뒤) | **닫힌 ClientConnection 객체** | `_available_quotes()` 가 **살아있다고 판정**(`is not None` 만 본다) → 풀이 계속 종목을 배정 · `subscribe()` 의 `if self._ws:` 가 truthy → 닫힌 소켓에 send → 예외 · `force_reconnect_session` 은 닫힌 소켓에 `close()`(no-op) 하고 **"강제 발화" 를 5분마다 영원히 로그** → **완전 위장** |

**30일 실측 `_ws is None` = 0건.** 즉 첫 연결 사망은 없었다. 재연결 사망은 로그로 판별이 **불가능**하다
(위 표 두 번째 행에는 고유 서명이 없다) — 다만 후술 §4 의 정황상 발생하지 않았을 개연성이 높다.

### 1.5 task 사망 감시 — 필요한가

**필요하다. 단, 조건이 있다.**

최후 그물을 넣으면 `connect()` 루프는 예외로는 죽지 않는다. 그러나 **두 경로가 남는다**:

1. **설계된 사망** — `_reconnect_count > MAX_RECONNECT` → `_trigger_auto_restart()` 가
   cooldown(60s) 또는 시간당 cap(3회) 에 걸려 `False` 를 반환 → **`break`**(:249).
   30일 0건이지만 **걸리면 영구**다(부활 경로 0 — 정본 §1.4(c) 확인).
2. **외부 cancel** — 종료 경로 버그, `_trigger_auto_restart` 핸드오프 race.

1번은 코드로 닫는다(§2.4). 2번은 감시가 필요하다.

**⚠️ 그런데 `_ws_task.done()` 로 감시하면 안 된다 — 오탐이 확실하다.**
`start()`(:291-299)는 `asyncio.create_task(self.connect(...))` 를 만들면서 **그 task 를 아무 데도
저장하지 않는다.** scheduler 의 `self._ws_task`(scheduler.py:588)는 여전히 **구(舊) task** 를 가리킨다.
따라서 auto-restart 가 한 번이라도 성공하면 **새 루프가 정상 가동 중인데도 `_ws_task.done() == True`** 다.
그 상태에서 되살리면 **connect 루프 2개 = 구독 이중화 + OPSP0002 폭주**다.

**올바른 감시 대상 = 인스턴스 자신이 기록하는 현재 루프 핸들.**

```python
# connect() 진입부 (:196 부근)
self._connect_task = asyncio.current_task()     # 신규 필드, 두 spawn 경로(scheduler / start) 공통
```
```python
# 감시 (scheduler._session_health_loop, 5분) — 메인 + 풀 전 세션
if ws._running and (ws._connect_task is None or ws._connect_task.done()):
    logger.critical("[ws_task_dead] label=%s — connect 루프 부재, 1회 되살림", ws._label)
    await ws.start()            # 하루 1회 cap (KstDailyEmitCap, cycle258 표준 재사용)
```

**메인 세션에 한정해서라도 반드시 넣을 것을 권고한다** — 메인 세션은 **체결통보 H0STCNI0** 를
나르고, 그것이 끊기면 시세가 아니라 **포지션 등록과 손절 자체가 마비**된다(CLAUDE.md 절대 금기).
보조 세션 상실은 시세 일부 상실이지만, 메인 상실은 매매 계약의 붕괴다.

---

## 2. F-3 — `_reconnect_count` 리셋 규약을 어떻게 바꿔야 하는가

### 2.1 결론: **리셋 규약은 건드리지 않는다.** 상한은 다른 축에 씌운다

의뢰가 준 세 선택지에 대한 답:

| 선택지 | 판정 | 근거 |
|---|---|---|
| (가) `MIN_STABLE_SECONDS(5)` 를 늘린다 | **비권고** | 5초는 "핸드셰이크가 성공했는가" 의 문턱으로 정확하다. 늘리면 정상 재연결이 실패로 계상돼 `MAX_RECONNECT` 가 조기 발화 → auto-restart 오발 |
| (나) "정상 프레임 N개 수신 시에만 리셋" | **비권고 (적극 반대)** | `_reconnect_count` 의 뜻이 *핸드셰이크 건강* 에서 *데이터 건강* 으로 바뀐다. 그러면 **시장 침묵**(15:0x/15:2x/15:4x — §4 에서 실측 72.7%)마다 8세션이 동시에 카운트를 쌓아 `_trigger_auto_restart` 의 `stop()→start()` 를 동시 발화한다. cycle241 이 한 사이클 들여 제거한 오탐(`[silent_inactive_market_wide_skip]`)이 **다른 문으로 부활**한다 |
| (다) **시간창 기반 연결 시도 상한** | **✅ 권고** | KIS 공지가 경고하는 대상이 정확히 *연결/종료 반복 횟수* 이고, 이 축 하나가 **heartbeat · clean close · 예외 · auto-restart 네 경로를 전부** 덮는다. 기존 카운터의 의미를 하나도 바꾸지 않는다 |

### 2.2 진짜 최악의 시나리오는 정본이 적은 것보다 **훨씬 나쁘다**

정본 §1.4(b)는 "heartbeat 30초 → 세션당 분당 2회 = 시간당 960회(8세션)" 로 계산했다.
**그보다 심한 경로가 하나 더 있다:**

```
connect() → 핸드셰이크 성공 → _receive_loop → KIS 가 즉시 clean close
   → ConnectionClosed 흡수 → return
   → monotonic()-connected_at < 5  ⇒ _reconnect_count 리셋 **안 함** (그대로 0)
   → while 조건 (0 <= 5) 성립 → 즉시 재진입, **sleep 0초**
```

**`await asyncio.sleep(wait)` 는 `except` 절 안에만 있다**(:260). 정상 복귀 경로에는 **어떤 지연도 없다.**
`get_approval_key()` POST(~100ms) + 핸드셰이크(~100ms) 만이 유일한 자연 지연이므로
**세션당 초당 3~5회 = 시간당 10,000~18,000회, 8세션이면 시간당 8~14만 회**다.
그리고 이 루프는 `_reconnect_count` 도 `_heartbeat_timeout_count` 도 `_auto_restart_history` 도
**아무것도 움직이지 않는다** — 모든 상한이 무관하다.

30일 실측으로 발생한 적은 없다(§4). 그러나 **KIS 가 "앱키 차단" 을 실제로 집행한다면 이 경로다.**

### 2.3 확정 설계 — 세션별 슬라이딩 1시간 연결 예산

**삽입 지점은 `while` 루프 본문 첫 줄 한 곳뿐**(네 경로 전부가 이 지점을 지난다).

```python
# 모듈 상수 (신규)
_CONNECT_WINDOW_SECS   = 3600.0   # 슬라이딩 윈도우
_CONNECT_MIN_INTERVAL  = 1.0      # 재연결 최소 간격 (첫 연결 제외)
_CONNECT_SOFT_CAP      = 12       # 실측 세션당 시간 최대 2회의 6배
_CONNECT_SOFT_DELAY    = 30.0
_CONNECT_HARD_CAP      = 24       # 실측의 12배
_CONNECT_HARD_DELAY    = 300.0    # 정상상태 상한 = 12회/시간/세션 = 96회/시간/전역
```

```python
        while self._running and self._reconnect_count <= MAX_RECONNECT:
            await self._await_connect_slot()          # ← 신규 1행
            try:
                self._approval_key = await self._token_manager.get_approval_key()
                ...
```

```python
    async def _await_connect_slot(self) -> None:
        """연결 시도 레이트 상한. **멈추지 않고 느려질 뿐이다** (사망 금지)."""
        now = _time.monotonic()
        self._connect_history = [t for t in self._connect_history
                                 if now - t < _CONNECT_WINDOW_SECS]
        n = len(self._connect_history)
        if n == 0:
            delay = 0.0                       # 첫 연결 = 현행 byte 동일 (부팅 지연 0)
        elif n < _CONNECT_SOFT_CAP:
            delay = _CONNECT_MIN_INTERVAL
        elif n < _CONNECT_HARD_CAP:
            delay = _CONNECT_SOFT_DELAY
        else:
            delay = _CONNECT_HARD_DELAY
        if delay > 0.0:
            self._emit_connect_budget_once(n, delay)      # 1회/(label,단계)/일, 예외 흡수
            await self._sleep_chunked(delay)              # ⚠️ 2초 chunk (아래 주의)
        self._connect_history.append(_time.monotonic())
```

**⚠️ 반드시 chunked sleep 이어야 한다.** `disconnect()`(=`stop()`)는 `_running = False` 만 세우고
connect task 를 **cancel 하지 않는다**. 통짜 `await asyncio.sleep(300)` 이면 20:10 정산 disconnect 나
`_trigger_auto_restart` 의 `stop()` 이 최대 5분 지연된다. scheduler 의 `_sleep_chunked` 관례(2초 chunk +
`_running` 검사)를 그대로 답습한다.

**왜 이 숫자인가 (실측 근거):**

`/oauth2/Approval` 발급 로그는 **label 을 달고 있어** 연결 시도의 정확한 카운터다
(`get_approval_key` 호출처는 `websocket.py:213` **단 한 곳** — 전수 grep 확인).

| 지표 | 실측값 |
|---|---|
| 세션당 시간 최대 연결 시도 | **2회** (2026-09-04 16:00 시간대, 8세션 전부) |
| 세션당 하루 연결 시도 | **3.1회**(09-03) / **5.1회**(09-04) |
| 전역 하루 연결 시도 | **25회**(09-03) / **41회**(09-04) |
| 30일 `최대 재연결 횟수 초과` | **0건** |
| 30일 `[ws_auto_restart]` | **0건** |
| 30일 `WebSocket 끊김`(connect except 진입) | **1건** (08-24, clean close 가 새어 들어온 것) |

soft 12 는 실측 최대의 **6배**, hard 24 는 **12배**다. 그리고 hard 24 는 현행 예외 경로의 전체 에스컬레이션
사다리(백오프 5회 + auto-restart 3회 × 5회 = 20회)가 **한 시간에 한 번은 그대로 다 돌 수 있는** 크기다 —
즉 정상적인 장애 복구 노력을 throttle 이 삼키지 않는다.

### 2.4 auto-restart 실패 시 `break` 를 제거한다 (불사 루프)

```python
                if self._reconnect_count > MAX_RECONNECT:
                    logger.error("최대 재연결 횟수 초과, 종료")     # ← 문자열 유지 (회귀 표면 0)
                    if await self._trigger_auto_restart():
                        break                    # 핸드오프 성공 = 새 task 가 인계 (현행 유지, 필수)
                    # cooldown / 시간당 cap → **죽지 않는다.** 다음 라운드는 예산이 늦춘다.
                    self._reconnect_count = 0
                    continue
```

**`break` 를 True 분기에 남기는 것은 필수다.** `_trigger_auto_restart()` 가 True 면 `stop()` 이
`_running=False` 를 세우고 `start()` 가 새 task 를 띄운 상태다. 여기서 `continue` 하면 새 task 가
`_running=True` 를 세우는 시점과의 race 로 **루프 2개**가 될 수 있다.

이 변경으로 `connect()` 는 `_running=False` 또는 취소로만 끝난다 = **불사 루프**. 그리고 불사 루프가
안전한 유일한 이유가 §2.3 의 예산이다. **둘은 반드시 같은 커밋에 들어가야 한다** — 예산 없이 불사만
넣으면 §2.2 의 시간당 14만 회 경로가 *영구화*된다.

### 2.5 `/oauth2/Approval` 캐시 — **이번 사이클 비권고**

| 항목 | 판정 |
|---|---|
| KIS 문서 `docs/kis/oauth.md` | approval_key **수명·재사용 가능 여부 기재 없음** |
| KIS 공식 샘플 `auth_ws_token.py` (MCP 조회 원문) | 발급만. 캐시·수명 **언급 없음**. `raise_for_status` 도 안 쓴다 |
| 우리 운영 실적 | **재사용한 적이 한 번도 없다** — 매 connect 마다 새로 발급 |
| Approval 의 레이트 한도 | 사실상 없음 — 부팅 시 8세션이 **같은 초에** 8회 발급해 전부 성공(09-04 07:51:54 실측). `/oauth2/tokenP` 의 분당 1개와 **다르다** |
| 예산 도입 후 REST 부하 | 전역 최악 **시간당 96회** (현재 하루 41회). 캐시가 없어도 **이미 무해** |

**즉 캐시의 이득은 예산이 이미 가져가고, 위험만 남는다.** 만약 approval_key 가 1회용이라면
캐시는 **모든 재연결을 실패시키는** 정반대 사고가 된다. 넣는다면 반드시 이 조합이어야 한다:

- TTL **60초**(폭주 구간 전용 — 정상 재연결 간격 수십 분에는 사실상 무효 = 행위 변화 ≈ 0)
- **핸드셰이크 실패 시 즉시 무효화** — 잘못된 캐시 키의 피해를 "핸드셰이크 1회 실패" 로 상한
- 기본값 **`_APPROVAL_TTL_SECS = 0.0`(비활성 = 현행 byte 동일)** 로 배포하고, 별도 관측 후 켠다

이렇게 하면 `src/auth/token.py`(8영역) 를 이번에 **건드리지 않아도 되고**, 변경이
`src/realtime/websocket.py` **한 파일**로 수렴한다 — 이게 이 사이클의 가장 큰 안전 마진이다.

---

## 3. 장중 시세 끊김이 실제로 얼마나 위험한가 (분 단위)

### 3.1 청산 평가의 유일한 관문 — 코드 전수

`risk.on_tick` 호출처는 **전 소스에서 정확히 2곳**이다 (grep 전수):

| # | 위치 | 소스 | 창 | 대상 |
|---|---|---|---|---|
| 1 | `src/realtime/handler.py:485` | **WebSocket tick** | 24h | 구독 중인 전 종목 |
| 2 | `src/engine/scheduler.py:2800` | **REST 60초 폴** (`_run_swing_rest_poll_once`) | **09:05~15:20** | `_SWING_POLL_STRATEGIES = ("donchian_swing","kojiro")` 의 **보유 종목만** |

즉 **일곱 전략 중 다섯(momentum · VB · LTV · BFB · VCP)은 청산 평가가 WebSocket 단일 의존**이다.
`_scan_loop`(5분)는 재구독만 하고 `on_tick` 을 부르지 않는다 — 청산 평가는 0.

**WS 사망에도 살아남는 것 (스케줄 구동, tick 무관 — 코드 확인):**

- `_force_clear_main_only()` 15:20 VB·LTV 일괄청산 (:1913) — 시각 가드만 본다
- `_execute_next_day_clear()` 09:00 + `_drain_pending_next_day_clear()` (:1302, :1509) —
  시가 미수신이면 `_resolve_open_price` REST 폴백 → 그래도 0이면 `_pending_next_day_clear` 로
  이월 → 09:00 KRX 시장가. **degrade 는 하지만 죽지 않는다**
- `_swing_buy_poll_loop` 09:05~09:30 donchian·kojiro 매수 (REST)

**WS 사망과 함께 사라지는 것:**

- 다섯 전략의 손절·트레일링·브레이크이븐 승격 **전부**
- 다섯 전략의 **매수 신호 전부**(BFB·VCP 는 `on_tick` 외 매수 경로 없음 — scheduler.py:1727 주석)
- **메인 세션이면 체결통보 H0STCNI0** → 포지션 미등록 → 그날 산 종목은 손절 대상에도 안 들어간다
- `H0UNMKO0` 장운영정보(VI·사이드카 감지)

### 3.2 현재 포트폴리오로 환산 (2026-09-06 운영 DB 실측 9포지션)

| 전략 | 종목 | 매수원가 | WS 사망 시 청산 경로 |
|---|---|---|---|
| kojiro | 000815·003490·004690·005180·225570·285130 | 758,910원 | **60초 REST 폴** (09:05~15:20) |
| donchian | 138040·175330 | 161,850원 | **60초 REST 폴** |
| **bull_flag_breakout** | **452430 ×3 @32,200** | **96,600원** | **없음 — tick 전용** |
| 합계 | 9 | 1,017,360원 | tick 전용 노출 **9.5%** |

**주목할 실증**: kojiro 보유 `000815`·`003490` 은 cycle252 가 밝힌 **무송출(no_feed) 종목**이라
**이미 WS blind 상태로 60초 REST 폴만으로 운용 중**이다. 즉 **60초 폴이 스윙 포지션의 청산 경로로
충분하다는 것이 운영 실적으로 이미 증명돼 있다.** (§7 후속 권고의 근거)

### 3.3 "회선이 N분 끊기면 무엇을 잃는가"

| 끊김 길이 | donchian·kojiro (8포지션·92%) | BFB·VB·LTV·momentum·VCP | 매수 | 체결통보(메인) |
|---|---|---|---|---|
| **~60초** | 손실 0 (폴 주기 내) | 손절 지연 ≤60초 | VB/LTV 진입 기회 일부 | 지연 후 수신 |
| **1~5분** | 손실 0 | 손절선 관통 후 추가 이탈. 코스닥 중소형 5분 변동폭 통상 1~3% | 돌파 초기 진입 상실 | 지연 |
| **5~30분** | 손실 0 (09:05~15:20 창 안) | **유의미** — -5% 손절이 -8~15%에 체결되는 구간 | 그 창의 매수 전멸 | 미등록 포지션 발생 |
| **30분~종일** | 창 안이면 0, 창 밖(08:00~09:05·15:20~20:00)이면 전면 상실 | VB·LTV 는 **15:20 일괄청산이 받는다**(당일 최대 손실 = 종가 근처). momentum·BFB·VCP 는 **무방비 이월** | 그날 매수 0 | **그날 산 종목이 positions 에 없다 = 다음 날도 손절 대상 아님** |
| **익일까지** | `_boot()` 가 새 세션 생성 | 동일 | — | `_sync_orders_to_db` 가 REST 로 사후 보정 |

### 3.4 → 백오프 상한의 근거

**손절 규약의 실질 파탄점은 "5분 이상 연속으로 끊긴 채 남는 것" 이다.** 그러므로:

> **throttle 의 최대 간격은 300초를 넘겨서는 안 된다. 그리고 어떤 상태에서도 시도를 멈춰서는 안 된다.**

`_CONNECT_HARD_DELAY = 300.0` 은 이 문장에서 직접 나온 값이다. 그리고 "멈추지 않는다" 가
현행과의 가장 큰 차이다 — **현행은 최악의 경우 2~4분 안에 영구히 멈춘다.**

---

## 4. 30일 실측 44건 분류 — 시장 침묵인가 진짜 장애인가

`Heartbeat 타임아웃` 메시지는 `label=` 을 달고 있어 **500ms dedupe 를 받지 않는다** → 44건은 정확한 수다.

| 유형 | 에피소드 | 건수 | 비중 | 사례 |
|---|---|---|---|---|
| **전 세션 동시**(8/8) | 4 | **32** | **72.7%** | 08-26 15:22 · 08-28 15:26 · 09-01 15:01 · 09-03 15:46 |
| 부분(2~3세션) | 4 | 10 | 22.7% | 08-07 11:25(3) · 08-11 12:27(2) · 08-11 15:18(3) · 08-31 10:02(2) |
| 단독(1세션) | 2 | 2 | 4.5% | 08-07 16:25 main · 08-21 15:36 44606571 |

시각 분포: **15:00~15:46 = 30건(68%)** · 정규장(09:00~15:20) = 10건(23%) · 장외 = 4건.

**cycle241 과 같은 축인가 — 부분적으로 그렇다.**

- **같은 점**: 72.7% 가 "전 세션 동시" 다. cycle241 이 `[silent_inactive_market_wide_skip]` 으로
  기각하기로 한 판정(30일 522건 중 491건=94.1% 가 풀 전원 동시)과 **비중·시각대가 같다**
  (15:20 이후 장후 동시호가 + 15:30~15:40 마감 흡수).
- **다른 점**: cycle241 의 재료는 `ticker_last_tick` **종목 신선도**이고, heartbeat 는 **세션 프레임
  수신** 이다. 시장이 침묵해도 KIS 는 유휴 세션에 **평균 10.3~10.8초마다** PINGPONG 을 보낸다
  (09-04 20:06 실측 `avg_interval=10.3s`, 8세션 전부). 그러므로 원리상 heartbeat 30초 타임아웃은
  시장 침묵과 **무관해야 한다**. 그런데 실측은 72.7% 가 동시다 →
  **KIS 가 그 구간에 PINGPONG 도 함께 멈추거나, 우리 쪽 공통 요인(이벤트 루프 지연·NAT)이 있다.**
  어느 쪽이든 "우리 세션 한 개의 고장" 은 아니다.

### 4.1 그렇다면 heartbeat 경로에도 cycle241 식 세션 상대 판정을 넣어야 하는가 — **비권고**

| 근거 | 내용 |
|---|---|
| 이득이 작다 | 재연결 1회는 ~1초짜리 동작이고 실측 최대는 세션당 **시간 2회**다. 실제 문제는 무한 루프인데 그건 §2.3 예산이 이미 막는다 |
| 책임 경계가 무너진다 | `KisWebSocket` 인스턴스가 **다른 세션을 보려면 풀 참조**가 필요하다. cycle241 이 `stale_session_recovery` 로 분리해 둔 경계를 되돌린다 |
| 위험 방향이 나쁘다 | 진짜 KIS 전면 장애일 때 **재연결을 안 하게 된다**. 이 축의 오답은 "차단" 이 아니라 "시세 상실" 쪽이라 §3 의 손절 손실로 직결된다 |
| 실증 부재 | 30일간 heartbeat 폭주 **0건** — 뒤에서 근거 |

**폭주 0건의 근거**: `_heartbeat_timeout_count` 는 5분마다 `_heartbeat_metrics_emit_once` 가 0으로
리셋한다(`websocket.py:390`, scheduler `_session_health_loop` 300초). 그런데 **44행 전부가
`timeout_count=1`** 이다. 폭주(분당 2회)가 한 번이라도 있었다면 같은 5분 창에서 `2`~`10` 이 찍혔어야 한다.
**30일간 한 세션도 5분 안에 두 번 타임아웃한 적이 없다.**

권고는 **관측만**: 전 세션 동시 타임아웃일 때 `[ws_heartbeat_timeout_market_wide]` 를 1회/일 남긴다
(선택 항목 — 이번 사이클에서 빼도 무방).

---

## 5. 관측 — 무엇이 보여야 성공인가

### 5.1 신규 마커

| 마커 | 레벨 | cap | 뜻 |
|---|---|---|---|
| `[ws_connect_unexpected] label= kind= err=` | **CRITICAL** | 없음(+`exc_info`) | 최후 그물이 잡았다 = **알려지지 않은 예외 계열**. 나오면 즉시 튜플에 편입 검토 |
| `[ws_connect_budget] label= n=NN/3600s delay=NNs` | WARNING | 1회/(label,단계)/일 | 예산 throttle 진입. **평시 0건이 정상** |
| `[ws_task_dead] label=` | **CRITICAL** | 1회/label/일 | connect 루프 부재 → 1회 되살림 |

`DailyEmitCap` / `KstDailyEmitCap` 는 cycle197·cycle258 이 이미 표준화해 둔 것을 **재사용**한다(신규 cap 구현 금지).

### 5.2 기존 마커의 **의미가 바뀐다** — 문서·해석 동반 개정 필요

| 마커 | 종전 뜻 | 시정 후 뜻 |
|---|---|---|
| `최대 재연결 횟수 초과, 종료` | **세션 사망 직전** 신호 | **throttle 진입** 신호 (문자열은 유지하되 "종료" 가 더 이상 사실이 아니다) |
| `[ws_auto_restart_cooldown]` | 사망 확정 | throttle 진입 |
| `[ws_auto_restart_cap_exceeded]` | 사망 확정 | throttle 진입 |

셋 다 30일 **0건**이라 과거 로그와의 합산 문제는 없다. 다만 `src/realtime/CLAUDE.md`·
`src/engine/CLAUDE.md` 의 "4중 안전망" 서술과 대시보드 해석은 함께 고쳐야 한다.
**`최대 재연결 횟수 초과, 종료` 문자열 자체는 바꾸지 말 것을 권고한다** — 회귀 가드가 붙어 있을 수
있고(cycle92 계열), 마커 문자열 변경은 다른 축의 리스크다. 대신 **바로 다음 줄에**
`[ws_connect_budget]` 이 붙어 실태를 설명하게 한다.

### 5.3 관측 결손 하나를 같이 고칠 것 — `WebSocket 연결 성공/닫힘` 에 label 이 없다

**이번 조사에서 발견한 정본 보정 사항이다.**

`main.py:166` `_DbLogHandler` 는 **동일 메시지 문자열 500ms TTL dedupe** 를 한다(`_DEDUPE_TTL_SECS`).
`logger.info("WebSocket 연결 성공")`(:220) 과 `logger.warning("WebSocket 연결 닫힘")`(:637) 은
**label 이 없어 8세션이 같은 문자열**을 낸다 → **동시 발생 8건이 `system_logs` 에 1행으로 접힌다.**

실측 (2026-09-04, INFO 보존 창 안 = 완전 데이터):

```
07:51:54  접속키 발급 완료 × 8 (label 있음)  |  WebSocket 연결 성공 × 1 (label 없음)
16:00:41  접속키 발급 완료 × 8              |  WebSocket 연결 성공 × 1
16:02:01  접속키 발급 완료 × 8              |  WebSocket 연결 성공 × 1
...
하루 합계: 접속키 41  vs  연결 성공 6
```

**따라서 정본 `kis_constraints.md` §1.2 의 "08:57~08:58 매일 1개 세션(08-12·08-31 만 2개)" 은
읽는 법이 틀렸다** — `WebSocket 연결 닫힘` 139건은 최대 8배 접힌 값이고, 실제로는 **8세션이 동시에
닫혔을 개연성이 높다**(정본 §1.3 의 "07:50 은 통과했다" 결론 자체는 영향받지 않는다 — 그건 0건 관측이고
dedupe 는 첫 발생을 지우지 못한다).

**권고**: 두 로그에 `label=%s` 를 추가한다. 비용 2줄, 이득 = 세션별 연결 회계가 처음으로 가능해진다
(지금은 `/oauth2/Approval` 로그로 우회 추정 중). U-5 미결 항목도 함께 닫힌다.

### 5.4 D+1 성공 판정 (배포 익일 07:55~20:10)

| # | 확인 | 성공 기준 |
|---|---|---|
| 1 | `[ws_connect_unexpected]` | **0건** (나오면 그 kind 를 튜플에 편입) |
| 2 | `[ws_connect_budget]` | **0건** (나오면 실측 기준선 재산정) |
| 3 | `[ws_task_dead]` | **0건** |
| 4 | `접속키 발급 완료` 라벨별 카운트 | 세션당 **≤6회/일** (기준선 3.1~5.1) |
| 5 | `WebSocket 연결 성공` 행수 | label 추가 후 **≈ 접속키 발급 수와 일치**(dedupe 해소 확인) |
| 6 | `Heartbeat 타임아웃` | 기준선 유지(1~3건/일), **`timeout_count=1` 유지** |
| 7 | `[pool_start_ready] ready=7/7` | 07:51±3분, 현행과 동일 (예산이 부팅을 늦추지 않았음) |
| 8 | `[tick_coverage]` stale 비율 | 현행 대비 악화 0 |

---

## 6. 접촉 범위 · 회귀 표면 · 되돌리기

### 6.1 파일 (권고안 기준)

| 파일 | 8영역 | 변경 지점 | 필수/선택 |
|---|---|---|---|
| `src/realtime/websocket.py` | **예** | 6곳 — ① 모듈 상수 + `import httpx` ② `__init__` 필드 2개(`_connect_history`, `_connect_task`) ③ `connect()` 진입부 task 기록 ④ `while` 첫 줄 `_await_connect_slot()` ⑤ except 절 3단 ⑥ auto-restart False → continue. + 헬퍼 3개(`_await_connect_slot`/`_sleep_chunked`/`_emit_connect_budget_once`) | **필수** |
| `src/engine/scheduler.py` | 별도 승인 | `_session_health_loop` 에 `[ws_task_dead]` 감시 1블록 (~15줄) | **강권** (메인 = 체결통보) |
| `src/realtime/websocket.py` (로그) | 예 | `연결 성공`/`연결 닫힘` 에 `label=` | 강권 (별도 커밋 가능) |
| `src/auth/token.py` | 예 | **무접촉** (§2.5 캐시 비권고) | — |
| `src/realtime/websocket_pool.py` | 예 | **무접촉** (`_connect_task` 로 감시하므로 `_quote_connect_tasks` 손댈 필요 없음) | — |
| `src/engine/risk.py`·`order_engine.py`·`session.py`·`scanner.py`·`strategy_registry.py`·`api/order.py` | 예 | **diff 0** | — |
| 전략 7파일 | — | **diff 0** | — |

### 6.2 회귀 표면 (실측 조사)

- **`connect()` 의 except 튜플을 문자열/AST 로 고정한 테스트 = 0건** (`tests/` 전수 grep:
  `InvalidURI`·`OSError`·`ConnectionClosed` 매칭은 전부 다른 모듈 대상)
- **cycle92 계열 8파일이 핀하는 것**: `MAX_RECONNECT == 5` · 백오프 합 `31.0` · `_trigger_auto_restart`
  의 cooldown/cap/window prune/idempotent — **전부 보존된다**(권고안은 이 넷을 하나도 바꾸지 않는다)
- `test_cycle92_4_safety_nets_persistence.py` = 함수명 존재 확인 → 영향 0
- `test_cycle241_silent_inactive_relative.py` = `_reconnect_count` 의 **의미**를 docstring 으로 설명 →
  권고안이 그 의미를 바꾸지 않으므로 정합 유지
- 신규 가드 필요: ① 튜플이 현행 3종의 상위집합인지 ② `CancelledError` 가 `connect()` 밖으로
  전파되는지 ③ 예산 단계별 delay 테이블 ④ auto-restart False 에서 루프가 살아남는지
  ⑤ `_sleep_chunked` 가 `_running=False` 에 2초 내 반응하는지 ⑥ 첫 연결 delay 0 (부팅 무지연)

### 6.3 되돌리기

- 전량 원복 = **다음 커밋 revert 1회** (설정 다이얼 없음, DB 무관, 마이그레이션 0)
- 부분 완화 다이얼 = `_CONNECT_SOFT_CAP`/`_CONNECT_HARD_CAP` 를 **아주 크게**(예: 10_000) 두면
  예산이 사실상 off 되고 나머지(예외 확대·불사 루프)는 유지 — **다만 코드 상수라 재배포 필요**
- ⚠️ 되돌리기 어려운 항목 없음. 단 **배포 시점은 되돌릴 수 없다**(§7)

---

## 7. 배포 시점 — 카드 ① 과 같은 커밋으로 갈 것인가

### 7.1 권고: **나눈다. 그리고 월요일 개장 전에는 올리지 않는다.**

**근거 1 — 결함 실현 확률이 배포 실수 확률보다 낮다.**

| 결함 | 30일 실측 발화 |
|---|---|
| F-2 첫 연결 무증상 사망 (`_ws is None`) | **0건** |
| F-2 재연결 무증상 사망 | 고유 서명 없음. 단 8세션 상시 가동 중 소실 정황 0 |
| F-3 heartbeat 폭주 (같은 5분에 2회) | **0건** (44행 전부 `timeout_count=1`) |
| F-3 즉시-close 폭주 | **0건** |
| `최대 재연결 횟수 초과` / `[ws_auto_restart]` | **0건 / 0건** |

반면 변경 대상은 **8영역 `websocket.py` 의 연결 루프 그 자체**다. 여기서 실수하면 그날 아침
8세션이 안 붙는다 = **손절 전면 마비**, F-2/F-3 의 최악과 같은 크기다.

**근거 2 — 원인 분리가 불가능해진다.**
오늘 이미 두 사이클을 올렸다. 특히 **cycle262 는 09:00~09:01:30 의 VB·LTV 진입 행위를 바꾸고**,
이 변경은 **같은 시각 창의 연결 행태를 바꾼다.** 월요일 아침 이상이 나면
"진입 보류 탓인가, 재연결 탓인가, 일봉 게이트 탓인가" 를 가를 수 없다.

**근거 3 — 카드 ① 과의 결합.**
카드 ① 이 무엇이든 **같은 커밋에 넣지 말 것을 권고한다.** 이 사이클은 되돌리기가
"revert 1회" 로 깨끗한데, 다른 변경과 묶이면 그 성질을 잃는다.

### 7.2 권고 일정

| 시점 | 할 일 |
|---|---|
| 월 09-07 07:55~20:10 | **배포 없음.** cycle262·263 D+1 실측에만 쓴다 |
| 화 09-08 15:40 이후 (또는 수 새벽) | 카드 ② 배포 (full 모드 — `src/**` 변경) |
| 수 09-09 07:55~20:10 | §5.4 의 8항목 D+1 판독 |

### 7.3 순서를 뒤집어야 하는 유일한 조건

**05:00 기동(또는 07:45 보다 이른 기동)을 월요일에 켠다면, 카드 ② 가 반드시 선행이다.**
05:00~07:45 는 이 시스템이 KIS 로 WebSocket 도 REST 시세도 **한 번도 보낸 적 없는 완전 미관측 구간**이고
(정본 §2.3 전 테이블 07:45 이전 기록 0건), F-2 의 사정거리가 **정확히 그 구간을 향한다**
(점검 시간대의 전형적 응답 = HTTP 상태 거부 = 현행 튜플이 못 잡는 것). 그 경우:

1. 카드 ② 를 먼저(일요일 밤 또는 월요일 07:00 이전) 배포하고
2. 05:00 기동은 **그다음 날부터** 켠다 (같은 날 둘 다 바꾸지 않는다)

---

## 8. 반례 · 한계 — 내 권고가 틀릴 수 있는 경우

1. **`_CONNECT_SOFT_CAP = 12` 가 진짜 장애를 늦출 수 있다.** 실측 기준선(세션당 시간 2회)은
   **정상적인 30일**의 것이다. KIS 측 대형 장애나 우리 EC2 의 네트워크 flapping 처럼 관측 창 밖의
   사건에서는 시간당 12회를 정당하게 넘길 수 있고, 그때 30초 throttle 이 붙는다.
   **다만 그 시나리오의 현행 결말은 "2~4분 뒤 영구 사망" 이라, 30초 throttle 은 여전히 개선이다.**
   이 논리가 깨지는 유일한 경우 = "12회 안에 반드시 붙는데 13번째만 늦어지는" 장애 형태인데,
   그런 형태를 나는 구성하지 못했다.
2. **`_CONNECT_MIN_INTERVAL = 1.0` 은 순수 비용이다.** 월 ~630회 재연결에 각 1초를 더한다.
   §2.2 의 즉시-close 폭주가 실재하지 않는다면 이 1초는 아무것도 사지 못한다.
   **0.0 으로 두는 것도 defensible** — 예산(soft cap)만으로도 폭주는 잡힌다. 결정 항목으로 올린다.
3. **불사 루프는 "조용한 무한 재시도" 의 위험을 새로 만든다.** 최후 그물이 프로그래밍 오류를
   재시도로 바꾸므로, `[ws_connect_unexpected]` CRITICAL 이 **실제로 사람 눈에 닿아야** 이 설계가 성립한다.
   20:10 일일 리포트 번들에 이 마커가 들어가지 않으면 권고의 절반이 무효다.
4. **`[ws_task_dead]` 감시가 오탐하면 connect 루프가 둘이 된다** = 구독 이중화 + OPSP0002 폭주.
   `_connect_task` 설계(§1.5)가 그 오탐을 막는다고 판단했지만, `start()` 가 `create_task` 를 만든
   직후~`connect()` 본문 진입 전 사이에 감시가 돌면 `_connect_task` 가 아직 구 task 다.
   **하루 1회 cap + 5분 주기라 실현 확률은 낮지만 0은 아니다.** 감시를 `_ws is None` **동시 조건**으로
   묶어 이중 확인하는 것이 더 안전하다(결정 항목).
5. **§3 의 "5분이 파탄점" 은 현재 포트폴리오 기준이다.** tick 전용 노출이 지금은 9.5%(BFB 1종목,
   96,600원)라 5분 상한이 넉넉해 보인다. VB·LTV 가 다시 체결되기 시작하거나 BFB·VCP 비중이 커지면
   **같은 5분이 훨씬 비싸진다.** 그때는 `_CONNECT_HARD_DELAY` 를 다시 계산해야 한다.
6. **dedupe 발견(§5.3)이 정본 §1.2 의 다른 결론들을 흔들 수 있다.** 나는 "0건 관측은 dedupe 에
   영향받지 않는다"(첫 발생은 지워지지 않는다)는 이유로 §1.3 의 07:50 반증은 유효하다고 판단했다.
   그러나 **횟수를 세는 다른 서술은 전부 재검토 대상**이다.
7. **approval_key 캐시를 안 넣는다는 판단은 "예산이 선다" 는 전제 위에 있다.** 예산을 빼고
   예외 확대만 배포하면 §2.2 경로가 살아 있으므로 캐시 부재가 다시 위험해진다.
   **§2.3 과 §2.4 는 분리 배포 금지.**
8. **내가 확인하지 못한 것**: (a) F-2 재연결 무증상 사망이 과거에 실제 있었는지 — 고유 서명이 없어
   판별 불가 (b) approval_key 의 실제 수명·재사용 가능 여부 — KIS 문서·공식 샘플·우리 로그 어디에도 없음
   (c) 15:0x/15:2x/15:4x 에 KIS PINGPONG 이 실제로 멈추는지 — `[ws_heartbeat]` INFO 가 2일 보존이라
   과거 침묵 구간의 `avg_interval` 을 못 봤다.

---

## 9. 사람이 결정할 항목

| # | 항목 | 선택지 | 내 권고 |
|---|---|---|---|
| **D-1** | 배포 시점 | (a) 월 개장 전 (b) **화 09-08 15:40 이후** (c) 카드 ① 과 동일 커밋 | **(b)** — 30일 발화 0건 vs 8영역 연결 루프 변경. cycle262 와 시각 창이 겹쳐 원인 분리 불가 |
| **D-2** | 05:00(조기) 기동을 언제 켜는가 | (a) 카드 ② 보다 먼저 (b) **카드 ② 배포 후 다음 날** | **(b)** — 미관측 구간이 F-2 의 정확한 사정거리. 같은 날 둘 다 바꾸지 않는다 |
| **D-3** | 예산 상수 | soft/hard = (a) 8/16 (b) **12/24** (c) 20/40 | **(b)** — 실측 최대(시간 2회)의 6배/12배. hard 24 는 현행 에스컬레이션 사다리(20회)를 시간당 1회 통과시킨다 |
| **D-4** | `_CONNECT_MIN_INTERVAL` | (a) 0.0 (b) **1.0** | **(b)** — 즉시-close 폭주의 유일한 1차 방어. 비용은 월 630초 |
| **D-5** | `[ws_task_dead]` 감시 | (a) 넣지 않는다 (b) **메인만** (c) 전 세션 | **(b) 이상** — 메인은 체결통보를 나른다. 오탐 방지로 `_connect_task.done()` **∧** `_ws is None` 이중 조건 권고 |
| **D-6** | `/oauth2/Approval` 캐시 | (a) **이번엔 넣지 않는다** (b) TTL 60s + 실패 시 무효화 (c) TTL 600s | **(a)** — 예산이 서면 전역 시간당 96회로 이미 무해. 수명 미지 상태의 캐시는 "전 세션 불통" 리스크 |
| **D-7** | `연결 성공/닫힘` label 추가 | (a) 같은 커밋 (b) **별도 커밋(같은 날)** (c) 안 한다 | **(b)** — 세션별 회계가 처음 가능해진다. 별도 커밋이면 로그 변화만 따로 롤백 가능 |
| **D-8** | heartbeat 전 세션 동시 관측 마커 | (a) **넣는다(관측만)** (b) 뺀다 | **(a)** — 1회/일 cap, 행위 0. §4 의 72.7% 를 계속 추적 |
| **D-9** | `최대 재연결 횟수 초과, 종료` 문자열 | (a) **유지** (b) "종료" 를 뺀 문구로 수정 | **(a)** — 의미는 문서로 고치고 문자열은 건드리지 않는다(회귀 표면 최소) |

---

## 10. 후속 권고 (이번 사이클 범위 밖)

**F-4 — `_SWING_POLL_STRATEGIES` 를 "보유 종목 전체" 로 확장.**
가장 확실한 근본 대책은 "재연결을 더 잘하는 것" 이 아니라 **"WS 없이도 보유 종목 청산이 도는 것"** 이다.
그 경로는 이미 존재하고(`_run_swing_rest_poll_once`), **kojiro `000815`·`003490` 이 이미 무송출 상태로
60초 폴만으로 운용 중**이라는 운영 실적이 있다. 확장 비용은 종목당 50ms 슬립 + KIS 단건 시세 1콜이라
보유가 통상 10종목 미만인 지금 사실상 0이다.

**다만 이번 사이클에 넣지 말 것을 권고한다** — 셋을 먼저 풀어야 한다:
(a) 창이 09:05~15:20 이라 VB·LTV 의 08:00~09:05 프리장 청산과 15:20 이후를 못 덮는다
(b) VB·LTV 는 당일 청산이라 60초 해상도가 손절선 통과 판정에 충분한지 별도 검토가 필요하다
(c) `_swing_rest_poll_loop` 는 `on_tick` 을 부르므로 **매수 평가가 딸려 올 수 있다** —
   현행은 `held_set` 한정이지만 확장 시 그 불변식을 명시적으로 지켜야 한다

**F-5 — `docs/kis/` 에 approval_key 수명 미기재 사실을 명문화.** 지금은 "없다" 는 사실 자체가
어디에도 안 적혀 있어 다음 사람이 같은 조사를 반복한다.

---

## 부록 — 이 문서가 인용한 실측 출처

- 운영 DB: `ssh auto-stock` → `psql "$DATABASE_URL"` (RDS, SELECT 전용)
- 예외 계층: `docker exec auto_stock-backend-1 python -c ...` (py 3.12.14 / websockets 14.2 / httpx 0.28.1)
- 마커 30일 집계: `최대 재연결 초과` 0 · `[ws_auto_restart]*` 0 · `WebSocket 끊김` 1 ·
  `[silent_inactive_market_wide_skip]` 14 · `[silent_inactive_force_reconnect]` 490 ·
  `[silent_inactive_recovery_cap]` 1,116 · `WebSocket 연결 닫힘` 139 · `Heartbeat 타임아웃` 44 ·
  `_ws is None` **0**
- 연결 시도 정확 카운터: `WebSocket 접속키 발급 완료(label=…)` — 호출처 `websocket.py:213` 단 1곳(전수 grep).
  09-03 25회/8라벨 · 09-04 41회/8라벨 · 시간당 세션 최대 2회
- 포지션: `positions` 9행 (BFB 452430 / donchian 2 / kojiro 6), 매수원가 합 1,017,360원
- PINGPONG: `[ws_heartbeat]` 09-04 20:06 8세션 `avg_interval=10.3s`
- 로그 dedupe: `src/main.py:166-198` `_DbLogHandler` 500ms TTL, 동일 메시지 문자열 기준
- KIS 공식: MCP `search_auth_api(function_name="auth_ws_token")` → `auth_ws_token.py` 전문 ·
  `docs/kis/oauth.md:67-80` · `docs/kis/rate-limits.md:154-158`
