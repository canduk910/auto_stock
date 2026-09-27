"""KRX 일별 전종목 시세 — 매매 DB 밖 별도 보관소 수집 스크립트 (cycle362 · ETF cycle383).

설계 = `_workspace/domain_consult/cycle361_daily_retention_730.md` 안 C · §6.
사용자 결정(2026-09-25, D7): 매매 DB 밖 별도 보관소 · 5년 · DB retention 390 유지.
ETF 확장 설계 = `_workspace/design/2026-09-27_etf_trend_strategy.md` §8.1(S0).
ETF 실행 기록 = `_workspace/domain_consult/cycle383_krx_etf_archive_build.md`.

자금 안전 원칙 (반드시 지킨다):
- `src/` 무수정 (이 파일은 `tools/archive/` 신규 파일 — 배포 모드 `none`)
- 운영 DB 쓰기 0건 (모든 세션 `default_transaction_read_only = on`)
- KIS 호출 0건 — 이 스크립트가 부르는 것은 KRX 공개 API(`src/api/krx.py`) 뿐, KIS OpenAPI 무관
- KRX AUTH_KEY 평문은 print/저장하지 않는다 (fetch_krx_open_api 내부에서만 쓰인다)
- 배포 없음, git 커밋 없음(이 파일 자체 포함 — 커밋 여부는 메인 세션이 판단)

두 그룹의 서브커맨드로 나뉜다 (cycle351_pyramid_s0_replay.py 의 dump/analyze 분리 답습):

  컨테이너 안 (운영 backend, DB = os.environ["DATABASE_URL"], KRX 공개 API 키 필요):
    probe <basDd>                                    — 단일 날짜 스모크 테스트(주식 KOSPI+KOSDAQ)
    stream <start> <end> [--sleep S]                  — 날짜별 KOSPI+KOSDAQ raw 를 stdout 에 JSONL 로
                                                         흘려보낸다(진행 로그는 stderr). 호출자가
                                                         `> 로컬파일` 로 받는다 — 컨테이너 재기동에 안전
    collect <start> <end> <out_dir> [--sleep S]       — (구) 날짜별 파일을 컨테이너 디스크에 저장.
                                                         `/tmp` 는 배포 재기동에 지워진다 — `stream` 권장
    dump_kis_overlap <start> <end> <out_path>         — 검증용 KIS 수정주가 stock_master_daily 덤프
    probe_etf <basDd>                                 — ETF 단일 날짜 스모크 테스트(cycle383)
    stream_etf <start> <end> [--sleep S]              — ETF 날짜별 raw 를 stdout 에 JSONL 로 흘려보낸다.
                                                         `stream` 과 달리 필드명을 전혀 가공하지 않고
                                                         KRX 원본 dict 를 그대로 담는다(§ETF 절 참조)

  로컬 (asyncpg/httpx 불필요, pandas 만):
    merge <raw_dir> <out_parquet_dir>                 — 날짜별 raw → 종목별 연도 parquet(원본+수정본)
    validate <merged_dir> <kis_overlap_dump>          — 수정주가 KIS 대조 (종목·날짜 단위 일치율)
    export_dump <merged_dir> <out_json_gz>            — S0 덤프 모양 daily[ticker]=[[...]] JSON.gz
    normalize_etf_jsonl <raw_jsonl> <out_jsonl>       — stream_etf 원본 → merge_jsonl 이 읽는 12칸 모양
                                                         (cycle383, 필드명 가설 적용 — §ETF 절 참조).
                                                         변환 후에는 merge_jsonl/validate/export_dump 를
                                                         ETF 경로(`data/archive/krx_etf_daily/...`)에
                                                         그대로 재사용한다 — ETF 전용 merge/validate 없음
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
sys.path.insert(0, "/app")  # 컨테이너 안에서만 의미 있음 (로컬 모드는 미사용)


# ══════════════════════════════════ 공통 ══════════════════════════════════

def _iter_weekdays(start: date, end: date):
    d = start
    one = timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:  # 0=월 ... 4=금
            yield d
        d += one


def _blocked_window_sleep_secs(now: datetime | None = None) -> float:
    """20:00~21:35 KST 창 안이면 그 창이 끝날 때까지의 대기초 반환, 아니면 0.

    루트 CLAUDE.md 「20:00~21:35 도 피한다」(cycle283 D8) — 이 스크립트는 배포·매매와
    무관하지만 운영자 지시를 그대로 따른다(KRX 호출도 운영 백엔드 프로세스와 같은 컨테이너에서
    돈다 — CPU/네트워크 경합을 그 저녁 블록과 겹치지 않게 한다).
    """
    now = now or datetime.now(KST)
    start_blk = now.replace(hour=20, minute=0, second=0, microsecond=0)
    end_blk = now.replace(hour=21, minute=35, second=0, microsecond=0)
    if start_blk <= now < end_blk:
        return (end_blk - now).total_seconds() + 5.0
    return 0.0


def _num(v, cast=int):
    if v in (None, "", "-"):
        return 0
    try:
        return cast(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _row_to_list(r: dict, market: str) -> list:
    """KRX OutBlock_1 한 행 → 압축 배열.

    [ticker, name, open, high, low, close, prev_diff(전일대비), volume, trade_value,
     mktcap, list_shrs, market]
    """
    return [
        r.get("ISU_CD", ""),
        r.get("ISU_NM", ""),
        _num(r.get("TDD_OPNPRC")),
        _num(r.get("TDD_HGPRC")),
        _num(r.get("TDD_LWPRC")),
        _num(r.get("TDD_CLSPRC")),
        _num(r.get("CMPPREVDD_PRC")),
        _num(r.get("ACC_TRDVOL")),
        _num(r.get("ACC_TRDVAL")),
        _num(r.get("MKTCAP")),
        _num(r.get("LIST_SHRS")),
        market,
    ]


# ══════════════════════════════════ 컨테이너 안 ══════════════════════════════════

async def _open_ro_conn():
    import asyncpg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn, server_settings={"timezone": "Asia/Seoul"})
    # src/db/pg.py::_init_conn 과 동일한 JSONB/JSON codec — 없으면 asyncpg 가 jsonb 를
    # str 로 반환해 get_krx_open_api_config() 의 dict 기대가 깨진다(활성화 오판 원인).
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.execute("SET default_transaction_read_only = on")
    return conn


async def _patch_pg_for_readonly(conn) -> None:
    """`src.db.system_config.get_krx_open_api_config()` 가 asyncpg 풀(init_pool 미실행) 없이도
    동작하도록 `pg.fetch` 를 이 read-only 연결로 돌린다. cycle351_pyramid_s0_replay.py 패턴 답습.
    쓰기(`pg.execute`)는 건드리지 않고 호출도 되지 않는다 — system_config 조회는 SELECT 뿐이다.
    """
    from src.db import pg

    async def _ro_fetch(sql, *args):
        return [dict(r) for r in await conn.fetch(sql, *args)]

    pg.fetch = _ro_fetch


async def probe(bas_dd: str) -> None:
    conn = await _open_ro_conn()
    await _patch_pg_for_readonly(conn)
    from src.api.krx import KrxApiError, fetch_ksq_bydd_trd, fetch_stk_bydd_trd

    try:
        kospi = await fetch_stk_bydd_trd(bas_dd)
        kosdaq = await fetch_ksq_bydd_trd(bas_dd)
        print(f"[probe] date={bas_dd} kospi_rows={len(kospi)} kosdaq_rows={len(kosdaq)}")
        if kospi:
            print(f"[probe] kospi sample keys={sorted(kospi[0].keys())}")
            print(f"[probe] kospi sample row(masked)={_row_to_list(kospi[0], 'KOSPI')}")
    except KrxApiError as e:
        print(f"[probe] KrxApiError: {e}")
    finally:
        await conn.close()


async def stream(start: str, end: str, sleep_secs: float) -> None:
    """`collect` 의 스트리밍 변형 — 컨테이너 로컬 디스크(휘발성 `/tmp`, 배포 재기동에 취약)에

    쓰지 않고 **날짜 하나 끝날 때마다 stdout 한 줄**(JSON)로 흘려보낸다. 호출자(로컬 ssh)가
    `> 로컬파일` 로 리다이렉트하면 원격 컨테이너가 배포로 재생성돼도 이미 흘러나온 줄은
    로컬 디스크에 안전하다(2026-09-25 실측 — 무관한 push 의 자동배포가 컨테이너를 재생성해
    `/tmp/krx_archive/raw` 전체를 지웠다). 진행 로그는 stderr 로 분리한다(stdout = 순수 JSONL).
    """
    import asyncio

    conn = await _open_ro_conn()
    await _patch_pg_for_readonly(conn)
    from src.api.krx import KrxApiError, fetch_ksq_bydd_trd, fetch_stk_bydd_trd

    sd = date.fromisoformat(start)
    ed = date.fromisoformat(end)

    total_calls = 0
    total_rows = 0
    holidays = 0
    errors: list[tuple[str, str]] = []
    t0 = datetime.now(KST)

    for d in _iter_weekdays(sd, ed):
        wait = _blocked_window_sleep_secs()
        if wait > 0:
            print(f"[stream] 20:00~21:35 KST 창 — {wait:.0f}s 대기", file=sys.stderr, flush=True)
            await asyncio.sleep(wait)

        bas_dd = d.strftime("%Y%m%d")
        try:
            kospi = await fetch_stk_bydd_trd(bas_dd)
            total_calls += 1
            await asyncio.sleep(sleep_secs)
            kosdaq = await fetch_ksq_bydd_trd(bas_dd)
            total_calls += 1
            await asyncio.sleep(sleep_secs)
        except KrxApiError as e:
            errors.append((bas_dd, str(e)))
            print(f"[stream] {bas_dd} ERROR {e}", file=sys.stderr, flush=True)
            await asyncio.sleep(sleep_secs)
            continue

        rows = [_row_to_list(r, "KOSPI") for r in kospi] + [_row_to_list(r, "KOSDAQ") for r in kosdaq]
        if not rows:
            holidays += 1
        total_rows += len(rows)

        payload = {"bas_dd": bas_dd, "n_kospi": len(kospi), "n_kosdaq": len(kosdaq), "rows": rows}
        print(json.dumps(payload, ensure_ascii=False), flush=True)

        if total_calls % 40 == 0:
            elapsed = (datetime.now(KST) - t0).total_seconds()
            print(
                f"[stream] progress date={bas_dd} calls={total_calls} rows={total_rows} "
                f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
                file=sys.stderr,
                flush=True,
            )

    await conn.close()
    elapsed = (datetime.now(KST) - t0).total_seconds()
    print(
        f"[stream] DONE start={start} end={end} calls={total_calls} rows={total_rows} "
        f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
        file=sys.stderr,
        flush=True,
    )
    if errors:
        print(f"[stream] error_dates={[e[0] for e in errors]}", file=sys.stderr, flush=True)


# ══════════════════════════════════ ETF (cycle383) ══════════════════════════════════
#
# 엔드포인트 = `/etp/etf_bydd_trd` (KRX Open API 「ETF 일별매매정보」).
#
# 검증 방법(사이클 115 가 4 endpoint 에 쓴 것과 같은 방식 — 외부 정본 2건 교차 확인):
#   1) `raccoonyy/pykrx-openapi` (`src/pykrx_openapi/constants.py`) — `CATEGORY_ETP = "etp"`,
#      `ENDPOINTS["etf_bydd_trd"] = ("etp", "ETF 일별매매정보")`. base URL·GET·AUTH_KEY query
#      파라미터 관례가 `src/api/krx.py` 와 동일 소스 계열(같은 저자군)에서 재확인됨.
#   2) 설계 문서(`_workspace/design/2026-09-27_etf_trend_strategy.md` §8.1)의 사전 추정과 일치.
#   3) 실측(2026-09-27, 운영 컨테이너에서 직접 호출) — **404 가 아니라 401**
#      (`{"respMsg":"Unauthorized API Call","respCode":"401"}`). 경로 자체는 존재하고, 이
#      KRX 계정이 ETP(ETF/ETN/ELW) 카테고리 서비스를 신청·승인받지 않았다는 뜻이다
#      (`src/api/krx.py` 의 기존 4 endpoint 는 sto/idx 카테고리만 승인된 상태 — etp 는 별도
#      신청 필요, `docs/krx-openapi.md` 「3. API 이용 신청」 절차와 일치).
#
# 🔴 응답 필드는 확인하지 못했다 — probe_etf 가 401 이라 실제 OutBlock_1 을 한 번도 못 봤다.
#    그래서 이 절은 두 층으로 나뉜다:
#      - probe_etf / stream_etf: KRX 원본 dict 를 그대로 다룬다(필드명 추측 0). ETP 서비스가
#        승인되면 가장 먼저 `probe_etf` 로 실제 키를 확인한다.
#      - _extract_etf_row / normalize_etf_jsonl (로컬 절): 필드명이 sto/idx 계열과 같다는
#        **가설**(미검증)을 쓰되, 핵심 키(종목코드·종가)가 없으면 조용히 0 을 채우지 않고
#        즉시 ValueError 로 멈춘다 — 가설이 틀렸을 때 숫자가 아니라 예외가 먼저 나와야 한다.
_ENDPOINT_ETF_BYDD_TRD = "/etp/etf_bydd_trd"


async def probe_etf(bas_dd: str) -> None:
    """`probe()` 의 ETF 버전 — 실제 OutBlock_1 필드명을 처음 확인할 때 쓴다.

    ETP 서비스 승인 전에는 401 이 정상이다(openapi.krx.co.kr 마이페이지 > 서비스 이용 > ETP >
    API 이용신청 필요 — cycle383 실측, 사람이 포털에서 신청해야 하는 절차라 이 스크립트가
    대신할 수 없다).
    """
    conn = await _open_ro_conn()
    await _patch_pg_for_readonly(conn)
    from src.api.krx import KrxApiError, fetch_krx_open_api

    try:
        data = await fetch_krx_open_api(_ENDPOINT_ETF_BYDD_TRD, {"basDd": bas_dd})
        rows = data.get("OutBlock_1", [])
        print(f"[probe_etf] date={bas_dd} rows={len(rows)}")
        if rows:
            print(f"[probe_etf] sample keys={sorted(rows[0].keys())}")
            print(f"[probe_etf] sample row={rows[0]}")
    except KrxApiError as e:
        print(f"[probe_etf] KrxApiError: {e}")
        print(
            "[probe_etf] 401 이면 openapi.krx.co.kr 마이페이지 > 서비스 이용 > ETP 서비스 "
            "승인 여부를 확인한다 (cycle383 실측 — 이 계정은 2026-09-27 기준 미승인)"
        )
    finally:
        await conn.close()


async def stream_etf(start: str, end: str, sleep_secs: float, max_retries: int = 2) -> None:
    """ETF 일별매매정보(`etf_bydd_trd`) stdout 스트리밍 — `stream()` 의 ETF 버전.

    ETF 는 KOSPI/KOSDAQ 분리가 없는 단일 엔드포인트라 날짜당 1콜(주식의 절반). 응답 행은
    **원본 dict 그대로** 내보낸다(필드명 추측 0 — 로컬 `normalize_etf_jsonl` 이 나중에 변환).
    실패한 날짜는 `max_retries`(기본 2)회 재시도 후에도 실패하면 `errors` 에 기록하고 다음
    날짜로 진행한다 — 완주 후 stderr `error_dates` 목록만 별도 좁은 범위로 재수집해 로컬에서
    JSONL 을 이어붙이면 전량 재시작 없이 이어받을 수 있다.
    """
    import asyncio

    conn = await _open_ro_conn()
    await _patch_pg_for_readonly(conn)
    from src.api.krx import KrxApiError, fetch_krx_open_api

    sd = date.fromisoformat(start)
    ed = date.fromisoformat(end)

    total_calls = 0
    total_rows = 0
    holidays = 0
    errors: list[tuple[str, str]] = []
    t0 = datetime.now(KST)

    for d in _iter_weekdays(sd, ed):
        wait = _blocked_window_sleep_secs()
        if wait > 0:
            print(f"[stream_etf] 20:00~21:35 KST 창 — {wait:.0f}s 대기", file=sys.stderr, flush=True)
            await asyncio.sleep(wait)

        bas_dd = d.strftime("%Y%m%d")
        rows = None
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                data = await fetch_krx_open_api(_ENDPOINT_ETF_BYDD_TRD, {"basDd": bas_dd})
                rows = data.get("OutBlock_1", [])
                total_calls += 1
                break
            except KrxApiError as e:
                last_err = e
                if attempt < max_retries:
                    print(
                        f"[stream_etf] {bas_dd} 재시도 {attempt + 1}/{max_retries} ({e})",
                        file=sys.stderr,
                        flush=True,
                    )
                    await asyncio.sleep(sleep_secs * (attempt + 2))
        await asyncio.sleep(sleep_secs)

        if rows is None:
            errors.append((bas_dd, str(last_err)))
            print(f"[stream_etf] {bas_dd} ERROR {last_err}", file=sys.stderr, flush=True)
            continue

        if not rows:
            holidays += 1
        total_rows += len(rows)

        payload = {"bas_dd": bas_dd, "n_rows": len(rows), "rows": rows}
        print(json.dumps(payload, ensure_ascii=False), flush=True)

        if total_calls % 40 == 0:
            elapsed = (datetime.now(KST) - t0).total_seconds()
            print(
                f"[stream_etf] progress date={bas_dd} calls={total_calls} rows={total_rows} "
                f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
                file=sys.stderr,
                flush=True,
            )

    await conn.close()
    elapsed = (datetime.now(KST) - t0).total_seconds()
    print(
        f"[stream_etf] DONE start={start} end={end} calls={total_calls} rows={total_rows} "
        f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
        file=sys.stderr,
        flush=True,
    )
    if errors:
        print(f"[stream_etf] error_dates={[e[0] for e in errors]}", file=sys.stderr, flush=True)


async def collect(start: str, end: str, out_dir: str, sleep_secs: float) -> None:
    import asyncio

    conn = await _open_ro_conn()
    await _patch_pg_for_readonly(conn)
    from src.api.krx import KrxApiError, fetch_ksq_bydd_trd, fetch_stk_bydd_trd

    os.makedirs(out_dir, exist_ok=True)
    sd = date.fromisoformat(start)
    ed = date.fromisoformat(end)

    total_calls = 0
    total_rows = 0
    holidays = 0
    errors: list[tuple[str, str]] = []
    t0 = datetime.now(KST)

    for d in _iter_weekdays(sd, ed):
        wait = _blocked_window_sleep_secs()
        if wait > 0:
            print(f"[collect] 20:00~21:35 KST 창 — {wait:.0f}s 대기", flush=True)
            await asyncio.sleep(wait)

        bas_dd = d.strftime("%Y%m%d")
        out_path = os.path.join(out_dir, f"{bas_dd}.json.gz")
        if os.path.exists(out_path):
            continue  # 재개 — 이미 받은 날짜는 건너뛴다

        try:
            kospi = await fetch_stk_bydd_trd(bas_dd)
            total_calls += 1
            await asyncio.sleep(sleep_secs)
            kosdaq = await fetch_ksq_bydd_trd(bas_dd)
            total_calls += 1
            await asyncio.sleep(sleep_secs)
        except KrxApiError as e:
            errors.append((bas_dd, str(e)))
            print(f"[collect] {bas_dd} ERROR {e}", flush=True)
            await asyncio.sleep(sleep_secs)
            continue

        rows = [_row_to_list(r, "KOSPI") for r in kospi] + [_row_to_list(r, "KOSDAQ") for r in kosdaq]
        if not rows:
            holidays += 1
        total_rows += len(rows)

        payload = {"bas_dd": bas_dd, "n_kospi": len(kospi), "n_kosdaq": len(kosdaq), "rows": rows}
        tmp_path = out_path + ".tmp"
        with gzip.open(tmp_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp_path, out_path)

        if total_calls % 40 == 0:
            elapsed = (datetime.now(KST) - t0).total_seconds()
            print(
                f"[collect] progress date={bas_dd} calls={total_calls} rows={total_rows} "
                f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
                flush=True,
            )

    await conn.close()
    elapsed = (datetime.now(KST) - t0).total_seconds()
    print(
        f"[collect] DONE start={start} end={end} calls={total_calls} rows={total_rows} "
        f"holidays={holidays} errors={len(errors)} elapsed_s={elapsed:.0f}",
        flush=True,
    )
    if errors:
        print(f"[collect] error_dates={[e[0] for e in errors]}", flush=True)


async def dump_kis_overlap(start: str, end: str, out_path: str) -> None:
    """검증용 — 운영 `stock_master_daily`(KIS 수정주가) 겹치는 구간을 SELECT 만 해서 덤프한다.

    쓰기 0건. 이 함수는 `system_config` 조회조차 필요 없다(KRX 무관 — 순수 운영 DB read).
    """
    conn = await _open_ro_conn()
    fh = gzip.open(out_path, "wt", encoding="utf-8")

    def w(obj):
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")

    try:
        rows = await conn.fetch(
            "select ticker, bas_dd, open_price, high_price, low_price, close_price, volume, "
            "trade_value, flng_cls_code, prtt_rate from stock_master_daily "
            "where bas_dd >= $1::date and bas_dd <= $2::date order by ticker, bas_dd",
            date.fromisoformat(start),
            date.fromisoformat(end),
        )
        n = 0
        from collections import defaultdict

        by = defaultdict(list)
        for r in rows:
            by[r["ticker"]].append(
                [
                    r["bas_dd"].isoformat(),
                    r["open_price"],
                    r["high_price"],
                    r["low_price"],
                    r["close_price"],
                    r["volume"],
                    r["trade_value"],
                    r["flng_cls_code"],
                    float(r["prtt_rate"] or 0),
                ]
            )
            n += 1
        for t, rs in by.items():
            w({"t": t, "rows": rs})
        print(f"[dump_kis_overlap] tickers={len(by)} rows={n} start={start} end={end}")
    finally:
        await conn.close()
        fh.close()


# ══════════════════════════════════ 로컬 (pandas) ══════════════════════════════════

def _open_maybe_gz(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


# ══════════════════════════════════ ETF 로컬 변환 (cycle383) ══════════════════════════════════
#
# probe_etf 가 아직 401 이라 실물 응답을 한 번도 못 봤다 — 아래 키 이름은 sto/idx 계열
# (`src/api/krx.py` 4 endpoint)의 확립된 명명을 그대로 물려받는다는 **가설**이다. 여러 후보를
# 두는 것은 "이름이 조금 다를 수 있다"는 대비이지, 후보 전부가 없을 때 조용히 0 을 채우겠다는
# 뜻이 아니다 — 핵심 키(종목코드·종가)가 전혀 없으면 `_extract_etf_row` 가 즉시 ValueError.
_ETF_TICKER_KEYS = ("ISU_CD", "ISU_SRT_CD")
_ETF_NAME_KEYS = ("ISU_NM", "ISU_ABBRV")
_ETF_OPEN_KEYS = ("TDD_OPNPRC",)
_ETF_HIGH_KEYS = ("TDD_HGPRC",)
_ETF_LOW_KEYS = ("TDD_LWPRC",)
_ETF_CLOSE_KEYS = ("TDD_CLSPRC",)
_ETF_PREV_DIFF_KEYS = ("CMPPREVDD_PRC",)
_ETF_VOLUME_KEYS = ("ACC_TRDVOL",)
_ETF_TRADE_VALUE_KEYS = ("ACC_TRDVAL",)
# ETF 는 시총 대신 순자산총액 계열 필드가 나올 가능성이 있어 후보를 넓힌다(둘 다 미확인).
_ETF_MKTCAP_KEYS = ("MKTCAP", "NAV_TOTAMT", "INVSTASST_NETASST_TOTAMT")
_ETF_LIST_SHRS_KEYS = ("LIST_SHRS", "LST_SHRS")


def _first_present(raw: dict, keys: tuple):
    """`keys` 순서대로 `raw` 에서 처음 발견되는 값을 반환. 전부 없으면 None."""
    for k in keys:
        if k in raw:
            return raw[k]
    return None


def _extract_etf_row(raw: dict) -> list:
    """ETF raw dict(KRX OutBlock_1 한 행) → `_row_to_list` 와 같은 모양의 12칸 압축 배열.

    [ticker, name, open, high, low, close, prev_diff, volume, trade_value, mktcap,
     list_shrs, market="ETF"] — `merge_jsonl` 이 그대로 읽을 수 있게 주식과 칸을 맞춘다.

    필드명은 **미확인 가설**이다(§ETF 절 참조). 핵심 키(종목코드·종가) 후보가 전부 없으면
    즉시 `ValueError` — 조용한 0 채움 금지(가설이 틀렸을 때 숫자가 아니라 예외가 먼저 나와야
    부분적으로 틀린 5년 원장이 검증 없이 만들어지는 것을 막는다).
    """
    ticker = _first_present(raw, _ETF_TICKER_KEYS)
    close = _first_present(raw, _ETF_CLOSE_KEYS)
    if ticker is None or close is None:
        raise ValueError(
            "ETF 응답 필드 가설이 어긋난다 — 예상 키 "
            f"{_ETF_TICKER_KEYS + _ETF_CLOSE_KEYS} 중 어느 것도 없다. "
            f"실제 키={sorted(raw.keys())}. probe_etf 로 재확인 필요(cycle383)."
        )
    return [
        str(ticker),
        _first_present(raw, _ETF_NAME_KEYS) or "",
        _num(_first_present(raw, _ETF_OPEN_KEYS)),
        _num(_first_present(raw, _ETF_HIGH_KEYS)),
        _num(_first_present(raw, _ETF_LOW_KEYS)),
        _num(close),
        _num(_first_present(raw, _ETF_PREV_DIFF_KEYS)),
        _num(_first_present(raw, _ETF_VOLUME_KEYS)),
        _num(_first_present(raw, _ETF_TRADE_VALUE_KEYS)),
        _num(_first_present(raw, _ETF_MKTCAP_KEYS)),
        _num(_first_present(raw, _ETF_LIST_SHRS_KEYS)),
        "ETF",
    ]


def normalize_etf_jsonl(raw_jsonl_path: str, out_jsonl_path: str) -> None:
    """`stream_etf` 원본 캡처(날짜당 1줄, `rows`=KRX raw dict 리스트) → `merge_jsonl` 이 읽는

    모양(`rows`=12칸 리스트)으로 변환한다. 이 단계에서만 필드명 가설(`_extract_etf_row`)을
    쓴다 — 실패하면 그 줄에서 즉시 멈춘다(부분적으로 틀린 변환본을 남기지 않는다). 변환이
    끝나면 `merge_jsonl(out_jsonl_path, etf_parquet_dir)` 를 그대로 이어 쓴다 — ETF 전용
    merge 함수는 없다(수정주가 보정 방법 §ETF 절 참조 — `_adjust_one` 그대로 재사용).
    """
    n_dates = 0
    n_rows = 0
    with _open_maybe_gz(raw_jsonl_path) as fin, open(out_jsonl_path, "wt", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            bas_dd = payload["bas_dd"]
            out_rows = [_extract_etf_row(r) for r in payload["rows"] if r]
            fout.write(json.dumps({"bas_dd": bas_dd, "rows": out_rows}, ensure_ascii=False) + "\n")
            n_dates += 1
            n_rows += len(out_rows)
    print(f"[normalize_etf_jsonl] dates={n_dates} rows={n_rows} -> {out_jsonl_path}")


def merge_jsonl(jsonl_path: str, out_dir: str) -> None:
    """`stream` 이 만든 단일 JSONL(날짜당 1줄) → 종목별 연도 parquet(원본+수정본).

    조정 방법은 `merge()` 와 같다(§6 C-2) — 이 함수가 실제 5년 원장 처리 경로다.
    """
    import pandas as pd

    all_rows = []
    n_dates = 0
    with _open_maybe_gz(jsonl_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                print(f"[merge_jsonl] 손상된 줄 스킵(마지막 줄일 가능성): {line[:80]}")
                continue
            n_dates += 1
            bas_dd = payload["bas_dd"]
            for r in payload["rows"]:
                ticker, name, o, h, l, c, prev_diff, vol, tval, mktcap, list_shrs, market = r
                if not ticker:
                    continue
                all_rows.append(
                    (ticker, name, bas_dd, o, h, l, c, prev_diff, vol, tval, mktcap, list_shrs, market)
                )

    cols = [
        "ticker", "name", "bas_dd", "open", "high", "low", "close", "prev_diff",
        "volume", "trade_value", "mktcap", "list_shrs", "market",
    ]
    df = pd.DataFrame(all_rows, columns=cols)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"], format="%Y%m%d")
    df = df.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)

    os.makedirs(out_dir, exist_ok=True)
    df = df.groupby("ticker", group_keys=False).apply(_adjust_one)

    df["year"] = df["bas_dd"].dt.year
    for yr, gdf in df.groupby("year"):
        gdf = gdf.drop(columns=["year"])
        gdf.to_parquet(os.path.join(out_dir, f"krx_daily_{yr}.parquet"), index=False)
        print(f"[merge_jsonl] {yr}: {len(gdf)} rows -> krx_daily_{yr}.parquet")

    print(
        f"[merge_jsonl] dates={n_dates} total rows={len(df)} tickers={df['ticker'].nunique()} "
        f"years={sorted(df['year'].unique())}"
    )


def _adjust_one(g):
    """종목 하나의 시계열에 누적 조정계수를 곱해 수정주가 칼럼을 만든다.

    주식·ETF 공용(cycle383) — **ETF 의 분배금 조정 규칙도 이 함수 그대로 쓴다.** KRX 는
    분배락일에 종목 종류(주식 배당락/ETF 분배락/액면분할 등)에 무관하게 기준가를 이미
    조정해서 내려준다 — 이 함수는 "왜" 기준가가 바뀌었는지 몰라도 되고, 기준가가 전일 종가와
    달라졌다는 사실 하나만으로 조정 이벤트를 잡는다. 그래서 ETF 전용 조정 로직을 새로
    만들지 않는다: 필드명(종가/전일대비 칸)만 맞으면(§ETF 절) 사이클362 의 배당락 처리와
    동일한 메커니즘이 분배락에도 그대로 성립한다(cycle362 실측에서도 "조정계수 발생 다수가
    12월 마지막 거래일 배당락" — 같은 신호로 잡혔다). 미실측 한계 = 감자·합병처럼 KRX 기준가
    보정법이 드물게 KIS 와 다르게 나올 수 있는 사건(§ETF 절, cycle362 README 한계와 동일).
    """
    import pandas as pd  # noqa: F401  (dtype ops below rely on pandas being imported by caller)

    g = g.sort_values("bas_dd").reset_index(drop=True)
    # 기준가 = 종가 - 전일대비. 기준가가 전일 종가와 다르면 그 비율이 조정계수.
    base_price = g["close"] - g["prev_diff"]
    prev_close = g["close"].shift(1)
    ratio = base_price / prev_close
    ratio = ratio.where((prev_close > 0) & base_price.notna(), 1.0)
    ratio = ratio.mask(~ratio.between(0.01, 100.0), 1.0)  # 이상치(첫 행 NaN 등) 방어
    cum = ratio[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    for col in ("open", "high", "low", "close"):
        g[f"{col}_adj"] = (g[col] * cum).round(2)
    g["adj_factor"] = cum
    return g


def merge(raw_dir: str, out_dir: str) -> None:
    """날짜별 raw json.gz → 종목별 연도 parquet. 원본(비수정) + 수정본(조정계수 누적) 둘 다 만든다.

    조정 방법(설계 §6 C-2): 그날 기준가 = 종가 − 전일대비(CMPPREVDD_PRC). 기준가가 전일 종가와
    다르면 그 비율이 조정계수다. 과거 쪽으로 누적곱해 내려간다(뒤에서 앞으로, 최신일부터).
    """
    import pandas as pd

    files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".json.gz"))
    if not files:
        print(f"[merge] {raw_dir} 에 파일이 없다")
        return

    all_rows = []
    for fn in files:
        with gzip.open(os.path.join(raw_dir, fn), "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        bas_dd = payload["bas_dd"]
        for r in payload["rows"]:
            ticker, name, o, h, l, c, prev_diff, vol, tval, mktcap, list_shrs, market = r
            if not ticker:
                continue
            all_rows.append(
                (ticker, name, bas_dd, o, h, l, c, prev_diff, vol, tval, mktcap, list_shrs, market)
            )

    cols = [
        "ticker", "name", "bas_dd", "open", "high", "low", "close", "prev_diff",
        "volume", "trade_value", "mktcap", "list_shrs", "market",
    ]
    df = pd.DataFrame(all_rows, columns=cols)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"], format="%Y%m%d")
    df = df.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)

    os.makedirs(out_dir, exist_ok=True)

    def _adjust_one(g: "pd.DataFrame") -> "pd.DataFrame":
        g = g.sort_values("bas_dd").reset_index(drop=True)
        # 기준가 = 종가 - 전일대비. 기준가가 전일 종가와 다르면 그 비율이 조정계수.
        base_price = g["close"] - g["prev_diff"]
        prev_close = g["close"].shift(1)
        ratio = base_price / prev_close
        ratio = ratio.where((prev_close > 0) & base_price.notna(), 1.0)
        ratio = ratio.mask(~ratio.between(0.01, 100.0), 1.0)  # 이상치(첫 행 NaN 등) 방어
        # 누적 조정계수(최신일=1.0, 과거로 갈수록 그날까지 있었던 액션 반영). shift(-1)로
        # "그 이후 조정계수"를 먼저 곱한 뒤 과거로 누적한다.
        cum = ratio[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        for col in ("open", "high", "low", "close"):
            g[f"{col}_adj"] = (g[col] * cum).round(2)
        g["adj_factor"] = cum
        return g

    df = df.groupby("ticker", group_keys=False).apply(_adjust_one)

    df["year"] = df["bas_dd"].dt.year
    for yr, gdf in df.groupby("year"):
        gdf = gdf.drop(columns=["year"])
        gdf.to_parquet(os.path.join(out_dir, f"krx_daily_{yr}.parquet"), index=False)
        print(f"[merge] {yr}: {len(gdf)} rows -> krx_daily_{yr}.parquet")

    print(f"[merge] total rows={len(df)} tickers={df['ticker'].nunique()} years={sorted(df['year'].unique())}")


def validate(merged_dir: str, kis_overlap_dump: str) -> None:
    """수정본 종가 vs KIS 수정주가(stock_master_daily) 종목·날짜 단위 일치율."""
    import pandas as pd

    files = sorted(f for f in os.listdir(merged_dir) if f.startswith("krx_daily_") and f.endswith(".parquet"))
    df = pd.concat([pd.read_parquet(os.path.join(merged_dir, f)) for f in files], ignore_index=True)
    df["bas_dd_str"] = df["bas_dd"].dt.strftime("%Y-%m-%d")

    kis_by_ticker = {}
    with gzip.open(kis_overlap_dump, "rt", encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            kis_by_ticker[o["t"]] = {r[0]: r[4] for r in o["rows"]}  # bas_dd -> close_price(수정주가)

    total = 0
    match = 0
    close_enough = 0  # 0.5% 이내
    mismatches = []
    for row in df.itertuples(index=False):
        kis_dates = kis_by_ticker.get(row.ticker)
        if not kis_dates:
            continue
        kis_close = kis_dates.get(row.bas_dd_str)
        if kis_close is None:
            continue
        total += 1
        archive_close = row.close_adj
        if archive_close is None or kis_close in (None, 0):
            continue
        diff = abs(float(archive_close) - float(kis_close))
        rel = diff / float(kis_close) if kis_close else 1.0
        if diff < 0.01:
            match += 1
        if rel <= 0.005:
            close_enough += 1
        else:
            mismatches.append((row.ticker, row.bas_dd_str, archive_close, kis_close, round(rel * 100, 3)))

    print(f"[validate] compared={total} exact_match={match} within_0.5pct={close_enough}")
    if total:
        print(f"[validate] exact_rate={match/total*100:.3f}% within_0.5pct_rate={close_enough/total*100:.3f}%")
    mismatches.sort(key=lambda x: -x[4])
    print(f"[validate] top mismatches (ticker, date, archive_adj, kis_adj, rel_pct):")
    for m in mismatches[:30]:
        print(f"  {m}")
    print(f"[validate] total mismatch tickers (>0.5%%): {len(set(m[0] for m in mismatches))}")


def export_dump(merged_dir: str, out_json_gz: str) -> None:
    """S0 덤프 모양 daily[ticker] = [[날짜, 시, 고, 저, 종, 거래량, 거래대금], ...] (수정본 기준)."""
    import pandas as pd

    files = sorted(f for f in os.listdir(merged_dir) if f.startswith("krx_daily_") and f.endswith(".parquet"))
    df = pd.concat([pd.read_parquet(os.path.join(merged_dir, f)) for f in files], ignore_index=True)
    df["bas_dd_str"] = df["bas_dd"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["ticker", "bas_dd"])

    daily: dict[str, list] = {}
    for ticker, g in df.groupby("ticker"):
        daily[ticker] = [
            [r.bas_dd_str, r.open_adj, r.high_adj, r.low_adj, r.close_adj, int(r.volume), int(r.trade_value)]
            for r in g.itertuples(index=False)
        ]

    with gzip.open(out_json_gz, "wt", encoding="utf-8") as fh:
        json.dump({"daily": daily}, fh, ensure_ascii=False)
    print(f"[export_dump] tickers={len(daily)} -> {out_json_gz}")


# ══════════════════════════════════ dispatch ══════════════════════════════════

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    mode = args[0]
    if mode == "probe":
        import asyncio

        asyncio.run(probe(args[1]))
    elif mode == "collect":
        import asyncio

        start, end, out_dir = args[1], args[2], args[3]
        sleep_secs = 0.7
        if "--sleep" in args:
            sleep_secs = float(args[args.index("--sleep") + 1])
        asyncio.run(collect(start, end, out_dir, sleep_secs))
    elif mode == "stream":
        import asyncio

        start, end = args[1], args[2]
        sleep_secs = 0.7
        if "--sleep" in args:
            sleep_secs = float(args[args.index("--sleep") + 1])
        asyncio.run(stream(start, end, sleep_secs))
    elif mode == "dump_kis_overlap":
        import asyncio

        asyncio.run(dump_kis_overlap(args[1], args[2], args[3]))
    elif mode == "probe_etf":
        import asyncio

        asyncio.run(probe_etf(args[1]))
    elif mode == "stream_etf":
        import asyncio

        start, end = args[1], args[2]
        sleep_secs = 0.7
        if "--sleep" in args:
            sleep_secs = float(args[args.index("--sleep") + 1])
        asyncio.run(stream_etf(start, end, sleep_secs))
    elif mode == "merge":
        merge(args[1], args[2])
    elif mode == "merge_jsonl":
        merge_jsonl(args[1], args[2])
    elif mode == "normalize_etf_jsonl":
        normalize_etf_jsonl(args[1], args[2])
    elif mode == "validate":
        validate(args[1], args[2])
    elif mode == "export_dump":
        export_dump(args[1], args[2])
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
