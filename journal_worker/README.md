# journal_worker

거래일지 관찰자 워커(cycle412, 사용자 결정 E1a). `src/` 밖의 독립 Python 패키지로, 매매
엔진·주문·체결통보 경로를 전혀 모른다. 백엔드가 이미 끝낸 매매를 **관찰만** 한다 — 파일
로그(`/app/logs/auto_stock.log`)를 꼬리로 읽고, 조회 API 둘을 리포터 키로 호출해
`trade_journal_orders`/`trade_journal_stops`에 행을 쌓는다.

- G0 = 기존 `GET /api/trading/status?include=system,holdings,strategies` — 엔진 상태·전략별 매수 신호·파라미터
- G1 = `GET /api/balance/exit-lines` — 보유마다 손절선·목표가·진입 ATR·무장가(이 워커 전용, 읽기만)

정본 설계: `_workspace/design/2026-10-08_trade_journal_observer.md` · 인터페이스 계약:
`_workspace/red/cycle412/journal_contract.md` 3절. 금기·DB 역할의 정본은 루트 `CLAUDE.md`
「Docker / 배포」 의 `journal_worker` 항목이다.

## 구조

```
jw/config.py      상수(경로·주기·TTL) — "/api/..." 리터럴은 이 파일에만
jw/grammar.py     로그 한 줄 → 이벤트 dict. 문법 리터럴은 이 모듈 1곳
jw/pairing.py     Pairer — 이벤트를 주문 행(한 회전 보류)으로 짝짓는다. 보관은 압축 기록·TTL·날 단위
                  리셋뿐이고 원본 스냅샷은 들고 있지 않는다(회전이 쌓여도 메모리가 늘지 않는다)
jw/stops.py       StopTracker — 손절선 사건(R8). 보유 식별 = (전략,종목) + 보유 주문번호
jw/reconcile.py   대사 — 항등식 점검 + trade_history 외부/미매칭 보강. `rotate()` 가 60초마다 부른다
jw/tailer.py      로그 꼬리 읽기(커서·회전·1회 상한)
jw/http.py        G0/G1 호출(허용 경로 화이트리스트)
jw/db.py          자동커밋 단문 DB 접근(트랜잭션 금지)
jw/main.py        한 회전 루프(Worker.rotate · run_forever) — 대사 연결 + 행 단위 예외 격리(한 행
                  실패가 같은 회전의 다른 행을 지우지 않는다) + `exit` 사건 중복 차단
jw/backfill.py    과거분 파싱 + DB 적재(`run_backfill`) — 기동 경로 밖, `source='log_restore'`
jw/__main__.py    진입점 `python -m jw run`(기본) | `python -m jw backfill <경로…>` + 로깅 설정
ops/role.sql      워커 전용 DB 역할 — 마이그레이션이 아니다. 047 뒤 사람이 psql 로 1회 실행
```

## 한 회전 (`jw/main.py`)

1. G0 호출 — 엔진이 멈췄거나 `phase=="idle"` 이면 여기서 끝(쓰기 0, 다음 회전 300초 뒤)
2. G1 호출
3. 로그 이어 읽기(1회 상한 4MiB)
4. 짝짓기 — 앵커 줄(접수·완료·폴백·재주문·수동)은 **다음** 회전에 내보낸다
5. 주문 행·손절선 사건 쓰기(행 단위 예외 격리 — 한 건이 실패해도 WARNING 뒤 다음 행으로 넘어간다).
   로그 행(`unmatched`·`external` 아닌 source)은 `insert_order` 가 실패(이미 있음)하면
   `promote_order` 로 그 빈 행(`unmatched`·`external`)을 실측으로 승격한다.
   청산 사건(`exit`)은 그 회전에 매도 행을 **새로 넣었거나 승격했을 때만** 쓴다 —
   `trade_journal_stops` 에는 UNIQUE 가 없어서, 커서 저장 실패로 같은 덩어리를 다시 읽으면
   같은 매도의 `exit` 가 겹칠 수 있기 때문이다
6. 커서 저장 — 행이 다 쓰인 청크 끝까지만 전진한다
7. 대사 — **대사 기준 시각 W**(행까지 쓴 로그 줄의 시각, 벽시계가 아니다)가 생긴 뒤부터 60초마다
   `trade_history` 를 읽어 누락 행(`unmatched`/`external`)을 보강하고 항등식을 확인한다. 읽기 창이
   꽉 찬 회전(따라잡는 중)은 건너뛴다. 완료 줄·행은 (주문번호, side) 고유값으로 센다(커서 저장 실패로
   같은 덩어리를 다시 읽어도 거듭 세지 않는다).
   - 대사 기준선 = W − `RECONCILE_MIN_AGE_SECONDS`(120초). 이보다 늦은 완료 줄·행은 아직 세지 않는다.
   - 완료 줄과 그 주문의 행은 (주문번호, side) 로 짝지어 **두 시각 중 늦은 쪽**으로 함께 자른다
     (`_cutoff_split`). 기준선이 두 시각 사이(예: 1초 차이)에 걸려도 한쪽만 세는 일이 없다. 짝이
     없으면 자기 시각 그대로다.
   - 어긋나면 `[journal_gap]` WARNING — 직전 결과와 값이 다를 때만 1줄(어긋남이 계속되면 매번 다시
     남기지 않는다). 어긋났던 항등식이 맞으면 `[journal_gap_resolved]` INFO 1줄

평소 주기는 15초다. G0·G1 이 실패하면 스냅샷 없이 로그만 수확하고(`degraded`), 연속 실패는
30·60·120·240·300초로 물러난다. 예외가 올라오면(`run_forever`) WARNING 으로 남기고 같은 백오프를 탄다.
`httpx` 요청 로그(하루 약 6,600줄)는 WARNING 이상으로 낮춰 둔다 — `jw.*` 자체 로그는 INFO 그대로다.

## 로깅

`python -m jw` 가 `main()` 안에서 표준 출력·평문·INFO 로 `logging.basicConfig` 를 한 번 설정한다
(모듈을 가져오기만 하면 설정하지 않는다). 각 모듈은 `logging.getLogger(__name__)`(`jw.*`)만 쓴다.
JSON 포맷터는 없다 — `docker logs journal_worker` 로 그대로 읽는다.

## 메모리

`jw/pairing.py` 가 보관하는 것은 넷뿐이다 — ① (전략,종목)별 신호 링(신호 시각 기준 TTL 10분)
② 전략별 `params` 사본과 G1 압축 기록(칸 몇 개만, 전략×종목당 최근 2~8개) ③ 짝짓기 대기 항목
(완료 줄·접수 전문·사유 줄 등, 이벤트 시각 기준 TTL) ④ 날 단위 상태(익일청산 보류 줄 등, 날이
바뀌면 비운다). G0/G1 **원본 응답 dict 는 들고 있지 않는다** — 그래서 회전이 500·2000·5000번
누적돼도 점유 메모리가 늘지 않는다(`test_jw_memory.py` M1). 날짜 경계의 정리는 대기 항목 개수와
무관하게 돈다 — 64개 미만이어도 날이 바뀌면 전날 항목을 비운다(`test_jw_memory.py` M5). 과거분
적재(`source != "log_harvest"`)는 입력 전체를 한 번에 받으므로 이 보관 정책 밖이다.

## 격리 규약

- `src` import 0, KIS 접속 자격·토큰 관련 식별자 0, 체결통보·WebSocket 0.
- 읽는 환경변수는 `JOURNAL_DATABASE_URL`(DSN)·`API_REPORTER_KEY`(G0/G1 호출용) 둘뿐.
- 동시 요청 0(`gather`/`create_task`/`TaskGroup`/`Thread` 금지) — 매 회전 HTTP 호출은 순차.
- DB 접근은 자동커밋 단문만(`jw/db.py`) — 트랜잭션을 열면 배포 때마다 도는
  `ALTER TABLE trade_history`가 뒤에서 기다리고, 그 뒤로 backend의 체결통보 쓰기가 줄을 선다.
  연결 풀은 `min_size=1, max_size=2`(run·backfill 둘 다) — RDS 연결 수를 적게 쓴다.
- JSONB 칸은 `json.dumps` 문자열로 바인딩한다 — 이 워커의 풀에는 backend 의 JSONB codec 이 없다.
- 이 문서를 포함해 `journal_worker/` 안 어떤 파일에도 KIS 자격 변수 접두사·체결통보 TR 이름을
  적지 않는다(`tests/test_jw_isolation.py` I2 가 문서까지 훑는다).
- 이미지는 root 가 아닌 사용자(`journal`, uid 1000)로 돈다. 코드(`/app/jw`)는 COPY 그대로 root
  소유로 두고 `chown` 하지 않는다 — 실행 사용자는 읽기만 하고, 뚫려도 자기 코드를 고칠 수 없다.
  빌드 문맥은 `.dockerignore` 가 `tests`·`ops`·`__pycache__`·`.env*` 를 뺀다.

## 실행

```bash
docker compose -f docker-compose.prod.yml up -d journal_worker   # 상시 루프(기본 CMD)
```

- `journal_worker` 서비스는 `docker-compose.prod.yml` 에만 있다 — `-f` 를 빼면 개발용 compose 를 읽어
  서비스를 찾지 못한다.
- ⚠️ 배포 전 확인 — 호스트 `~/auto_stock/logs/auto_stock.log*` 를 컨테이너 uid(1000)가 읽을 수
  있어야 한다. 소유자가 uid 1000 이 아니면 다른 사용자 읽기 권한이 필요하다(`644` 면 충분하다).

### 사전 준비 (E1c — 운영 DB 역할, 1회성)

```bash
PW=$(openssl rand -hex 24)
psql "$DATABASE_URL" -v journal_pw="$PW" -f journal_worker/ops/role.sql   # 047 마이그레이션 적용 뒤
```

같은 `$PW` 를 `./secrets/journal_worker.env`(git 밖, 사람이 미리 만든다)의
`JOURNAL_DATABASE_URL` 에 역할 `journal_worker` 로 접속하는 DSN 으로 옮긴다. 이 파일이 없으면
`docker compose -f docker-compose.prod.yml up` 전체가 실패한다(`secrets/.htpasswd` 와 같은 규약).

### 과거분 적재 (D3 — backfill)

```bash
docker compose -f docker-compose.prod.yml run --rm journal_worker backfill /app/logs/auto_stock.log.2026-09-17 ...
```

- 평문·`.gz` 로그 파일 경로를 그대로 인자로 준다. 경로를 하나도 안 주면 사용법 오류(종료 코드 2)로
  끝나고 DB 에 붙지 않는다.
- 읽기 속도에 상한을 두고(`BACKFILL_MAX_BYTES_PER_SEC`), `insert_order` 의 `ON CONFLICT DO NOTHING`
  으로 멱등이다 — 같은 파일을 두 번 적재해도 행이 늘지 않는다.
- 적재한 행은 `source='log_restore'` 다. 손절선 사건·커서는 건드리지 않는다.
- 기동 경로(`CMD ["run"]`)는 이 분기를 타지 않는다 — 장외 창에 사람이 1회 실행한다. 운영 DB
  적재는 이 사이클의 배포와 분리한다.

테스트: `pytest journal_worker/tests` (루트 `pyproject.toml` `testpaths` 에 포함되어
`pytest` 전체 실행에도 함께 돈다. 영향 인덱스 `tools/test_impact/` 는 `tests/` 만 봐서 워커
테스트를 고르지 않는다).
