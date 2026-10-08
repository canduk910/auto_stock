# journal_worker

거래일지 관찰자 워커(cycle412, 사용자 결정 E1a). `src/` 밖의 독립 Python 패키지로, 매매
엔진·주문·체결통보 경로를 전혀 모른다. 백엔드가 이미 끝낸 매매를 **관찰만** 한다 — 파일
로그(`/app/logs/auto_stock.log`)를 꼬리로 읽고, 리포터 전용 조회 API 둘(G0/G1)을 호출해
`trade_journal_orders`/`trade_journal_stops`에 행을 쌓는다.

정본 설계: `_workspace/design/2026-10-08_trade_journal_observer.md` · 인터페이스 계약:
`_workspace/red/cycle412/journal_contract.md` 3절.

## 구조

```
jw/config.py      상수(경로·주기·TTL) — "/api/..." 리터럴은 이 파일에만
jw/grammar.py     로그 한 줄 → 이벤트 dict. 문법 리터럴은 이 모듈 1곳
jw/pairing.py     Pairer — 이벤트를 주문 행(한 회전 보류)으로 짝짓는다
jw/stops.py       StopTracker — 손절선 사건(R8)
jw/reconcile.py   대사 — 항등식 점검 + trade_history 외부/미매칭 보강
jw/tailer.py      로그 꼬리 읽기(커서·회전·1회 상한)
jw/http.py        G0/G1 호출(허용 경로 화이트리스트)
jw/db.py          자동커밋 단문 DB 접근(트랜잭션 금지)
jw/main.py        한 회전 루프(Worker.rotate · run_forever)
jw/backfill.py    과거분 1회 적재(기동 경로 밖, `python -m jw backfill`)
```

## 격리 규약

- `src` import 0, KIS 접속 자격·토큰 관련 식별자 0, 체결통보·WebSocket 0.
- 읽는 환경변수는 `JOURNAL_DATABASE_URL`(DSN)·`API_REPORTER_KEY`(G0/G1 호출용) 둘뿐.
- 동시 요청 0(`gather`/`create_task`/`TaskGroup`/`Thread` 금지) — 매 회전 HTTP 호출은 순차.
- DB 접근은 자동커밋 단문만(`jw/db.py`) — 트랜잭션을 열면 배포 때마다 도는
  `ALTER TABLE trade_history`가 뒤에서 기다리고, 그 뒤로 backend의 체결통보 쓰기가 줄을 선다.

## 실행

```bash
docker compose -f docker-compose.prod.yml up -d journal_worker   # 상시 루프(기본 CMD)
docker compose run --rm journal_worker backfill                  # 과거분 1회(수동)
```

테스트: `pytest journal_worker/tests` (루트 `pyproject.toml` `testpaths` 에 포함되어
`pytest` 전체 실행에도 함께 돈다).
