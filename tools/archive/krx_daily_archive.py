"""KRX 일별 전종목 시세 — 매매 DB 밖 별도 보관소 수집 스크립트 (cycle362).

설계 = `_workspace/domain_consult/cycle361_daily_retention_730.md` 안 C · §6.
사용자 결정(2026-09-25, D7): 매매 DB 밖 별도 보관소 · 5년 · DB retention 390 유지.

자금 안전 원칙 (반드시 지킨다):
- `src/` 무수정 (이 파일은 `tools/archive/` 신규 파일 — 배포 모드 `none`)
- 운영 DB 쓰기 0건 (모든 세션 `default_transaction_read_only = on`)
- KIS 호출 0건 — 이 스크립트가 부르는 것은 KRX 공개 API(`src/api/krx.py`) 뿐, KIS OpenAPI 무관
- KRX AUTH_KEY 평문은 print/저장하지 않는다 (fetch_krx_open_api 내부에서만 쓰인다)
- 배포 없음, git 커밋 없음(이 파일 자체 포함 — 커밋 여부는 메인 세션이 판단)

두 그룹의 서브커맨드로 나뉜다 (cycle351_pyramid_s0_replay.py 의 dump/analyze 분리 답습):

  컨테이너 안 (운영 backend, DB = os.environ["DATABASE_URL"], KRX 공개 API 키 필요):
    probe <basDd>                                    — 단일 날짜 스모크 테스트
    stream <start> <end> [--sleep S]                  — 날짜별 KOSPI+KOSDAQ raw 를 stdout 에 JSONL 로
                                                         흘려보낸다(진행 로그는 stderr). 호출자가
                                                         `> 로컬파일` 로 받는다 — 컨테이너 재기동에 안전
    collect <start> <end> <out_dir> [--sleep S]       — (구) 날짜별 파일을 컨테이너 디스크에 저장.
                                                         `/tmp` 는 배포 재기동에 지워진다 — `stream` 권장
    dump_kis_overlap <start> <end> <out_path>         — 검증용 KIS 수정주가 stock_master_daily 덤프

  로컬 (asyncpg/httpx 불필요, pandas 만):
    merge <raw_dir> <out_parquet_dir>                 — 날짜별 raw → 종목별 연도 parquet(원본+수정본)
    validate <merged_dir> <kis_overlap_dump>          — 수정주가 KIS 대조 (종목·날짜 단위 일치율)
    export_dump <merged_dir> <out_json_gz>            — S0 덤프 모양 daily[ticker]=[[...]] JSON.gz
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
    elif mode == "merge":
        merge(args[1], args[2])
    elif mode == "merge_jsonl":
        merge_jsonl(args[1], args[2])
    elif mode == "validate":
        validate(args[1], args[2])
    elif mode == "export_dump":
        export_dump(args[1], args[2])
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
