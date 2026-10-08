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
jw/pairing.py     Pairer — 이벤트를 주문 행(한 회전 보류)으로 짝짓는다
jw/stops.py       StopTracker — 손절선 사건(R8)
jw/reconcile.py   대사 — 항등식 점검 + trade_history 외부/미매칭 보강 (⚠️ 루프가 부르지 않는다)
jw/tailer.py      로그 꼬리 읽기(커서·회전·1회 상한)
jw/http.py        G0/G1 호출(허용 경로 화이트리스트)
jw/db.py          자동커밋 단문 DB 접근(트랜잭션 금지)
jw/main.py        한 회전 루프(Worker.rotate · run_forever)
jw/backfill.py    과거분 파싱(기동 경로 밖) — ⚠️ DB 에 쓰는 경로가 아직 없다
ops/role.sql      워커 전용 DB 역할 — 마이그레이션이 아니다. 047 뒤 사람이 psql 로 1회 실행
```

## 한 회전 (`jw/main.py`)

1. G0 호출 — 엔진이 멈췄거나 `phase=="idle"` 이면 여기서 끝(쓰기 0, 다음 회전 300초 뒤)
2. G1 호출
3. 로그 이어 읽기(1회 상한 20MB)
4. 짝짓기 — 앵커 줄(접수·완료·폴백·재주문·수동)은 **다음** 회전에 내보낸다
5. 주문 행·손절선 사건 쓰기
6. 커서 저장 — 행이 다 쓰인 청크 끝까지만 전진한다

평소 주기는 15초다. G0·G1 이 실패하면 스냅샷 없이 로그만 수확하고(`degraded`), 연속 실패는
30·60·120·240·300초로 물러난다.

## 격리 규약

- `src` import 0, KIS 접속 자격·토큰 관련 식별자 0, 체결통보·WebSocket 0.
- 읽는 환경변수는 `JOURNAL_DATABASE_URL`(DSN)·`API_REPORTER_KEY`(G0/G1 호출용) 둘뿐.
- 동시 요청 0(`gather`/`create_task`/`TaskGroup`/`Thread` 금지) — 매 회전 HTTP 호출은 순차.
- DB 접근은 자동커밋 단문만(`jw/db.py`) — 트랜잭션을 열면 배포 때마다 도는
  `ALTER TABLE trade_history`가 뒤에서 기다리고, 그 뒤로 backend의 체결통보 쓰기가 줄을 선다.
- JSONB 칸은 `json.dumps` 문자열로 바인딩한다 — 이 워커의 풀에는 backend 의 JSONB codec 이 없다.
- 이 문서를 포함해 `journal_worker/` 안 어떤 파일에도 KIS 자격 변수 접두사·체결통보 TR 이름을
  적지 않는다(`tests/test_jw_isolation.py` I2 가 문서까지 훑는다).

## 실행

```bash
docker compose -f docker-compose.prod.yml up -d journal_worker   # 상시 루프(기본 CMD)
```

- `journal_worker` 서비스는 `docker-compose.prod.yml` 에만 있다 — `-f` 를 빼면 개발용 compose 를 읽어
  서비스를 찾지 못한다.
- ⚠️ `docker compose -f docker-compose.prod.yml run --rm journal_worker backfill` 은 지금 과거분을
  적재하지 않는다. 안내 문구만 찍고 종료 코드 1 로 끝난다.

테스트: `pytest journal_worker/tests` (루트 `pyproject.toml` `testpaths` 에 포함되어
`pytest` 전체 실행에도 함께 돈다. 영향 인덱스 `tools/test_impact/` 는 `tests/` 만 봐서 워커
테스트를 고르지 않는다).
