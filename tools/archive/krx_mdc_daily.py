"""KRX 정보데이터시스템(data.krx.co.kr) 로그인 경로 — 날짜별 전 종목 시세 (2026-10-06).

결과 보고 = `_workspace/domain_consult/2026-10-05_archive_30y_build.md` §9.

1996~2009 보강용(상장폐지 종목·시가총액·원주가). 화면 「전종목 시세」(MDCSTAT01501) 와 같은 요청이다.
계정 = `~/.krx_credentials`(권한 600, `KRX_ID=`·`KRX_PW=` 두 줄, 사용자가 만든 파일).

🔴 계정 취급: 파일은 이 프로세스 안에서만 읽어 로그인 요청 본문에 넣는다. ID·PW 를 출력·로그·저장하지 않는다.
   pykrx 의 `build_krx_session()` 은 로그인 ID 를 print 하므로 쓰지 않고 `login_krx()` 만 직접 부른다.
   요청 간격은 기본 2초, 실패 시 지수 대기.

  python tools/archive/krx_mdc_daily.py probe <YYYYMMDD> [<YYYYMMDD> ...] --out <jsonl>
      날짜마다 KOSPI(STK)·KOSDAQ(KSQ) 두 번 요청해 원본 행을 jsonl 한 줄(날짜×시장)로 쓴다.
      진행·요약은 stderr.
  python tools/archive/krx_mdc_daily.py stream <start YYYY-MM-DD> <end YYYY-MM-DD> --out <jsonl> [--sleep 2]
      영업일 후보(평일 + 1998-12-05 까지의 토요일)를 날짜×시장으로 요청해 한 줄씩 덧붙인다.
      out 에 이미 있는 (날짜, 시장)은 건너뛴다(이어 받기). KOSDAQ 은 1996-07-01 부터.
      멈춤 조건(차단 징후) = 연속 실패 3회 · 평일 빈 응답 연속 8일 → 종료 코드 2.
  python tools/archive/krx_mdc_daily.py index <start YYYYMMDD> <end YYYYMMDD> --out <jsonl>
      지수 일별 시세(MDCSTAT00301) — KOSPI(1/001)·KOSPI200(1/028)·KOSDAQ(2/001), 2년 단위로 끊어 요청.
"""
from __future__ import annotations

import json
import os
import sys
import time

_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"


def _read_credentials(path: str = "~/.krx_credentials") -> tuple[str, str]:
    kv = {}
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip().strip('"').strip("'")
    if not kv.get("KRX_ID") or not kv.get("KRX_PW"):
        raise SystemExit("[krx_mdc] 계정 파일에 KRX_ID/KRX_PW 가 없다")
    return kv["KRX_ID"], kv["KRX_PW"]


def _login():
    import requests
    from pykrx.website.comm.auth import USER_AGENT, login_krx

    sid, spw = _read_credentials()
    s = requests.Session()
    ok = login_krx(sid, spw, s)
    del sid, spw
    if not ok:
        raise SystemExit("[krx_mdc] 로그인 실패(계정 값은 출력하지 않는다)")
    s.headers.update({"User-Agent": USER_AGENT, "Referer": _REFERER, "X-Requested-With": "XMLHttpRequest"})
    return s


def _fetch(s, mkt: str, trd_dd: str, sleep: float) -> list[dict]:
    data = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
        "locale": "ko_KR",
        "mktId": mkt,
        "trdDd": trd_dd,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    for attempt in range(4):
        try:
            r = s.post(_URL, data=data, timeout=30)
            if r.status_code == 200 and r.text.strip() not in ("", "LOGOUT"):
                return r.json().get("OutBlock_1", [])
            print(f"[krx_mdc] {mkt} {trd_dd} http={r.status_code} body={r.text[:40]!r}", file=sys.stderr, flush=True)
        except Exception as ex:  # 네트워크 예외 메시지에는 계정이 들어가지 않는다(본문은 로그인 요청에만 있음)
            print(f"[krx_mdc] {mkt} {trd_dd} {type(ex).__name__}", file=sys.stderr, flush=True)
        time.sleep(sleep * (2 ** (attempt + 1)))
    raise RuntimeError(f"{mkt} {trd_dd} 실패")


def probe(dates: list[str], out: str, sleep: float) -> None:
    s = _login()
    print("[krx_mdc] 로그인 성공", file=sys.stderr, flush=True)
    time.sleep(sleep)
    with open(out, "a", encoding="utf-8") as fh:
        for d in dates:
            for mkt in ("STK", "KSQ"):
                rows = _fetch(s, mkt, d, sleep)
                fh.write(json.dumps({"trd_dd": d, "mkt": mkt, "n": len(rows), "rows": rows}, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"[krx_mdc] {d} {mkt} rows={len(rows)}", file=sys.stderr, flush=True)
                time.sleep(sleep)


def _candidate_days(start: str, end: str):
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    e = date.fromisoformat(end)
    last_sat = date(1998, 12, 5)  # 토요일 장 마지막 날(네이버 보관소 실측)
    while d <= e:
        if d.weekday() < 5 or (d.weekday() == 5 and d <= last_sat):
            yield d
        d += timedelta(days=1)


def stream(start: str, end: str, out: str, sleep: float) -> int:
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                    done.add((o["trd_dd"], o["mkt"]))
                except (json.JSONDecodeError, KeyError):
                    continue
    s = _login()
    login_t = time.time()
    print(f"[krx_mdc] 로그인 성공 · 이미 받은 날짜×시장 {len(done)}", file=sys.stderr, flush=True)
    time.sleep(sleep)
    n_req = n_rows = 0
    empty_weekday_run = 0
    t0 = time.time()
    with open(out, "a", encoding="utf-8") as fh:
        for d in _candidate_days(start, end):
            dd = d.strftime("%Y%m%d")
            day_rows = 0
            for mkt in ("STK", "KSQ"):
                if mkt == "KSQ" and dd < "19960701":
                    continue
                if (dd, mkt) in done:
                    day_rows = -1
                    continue
                if time.time() - login_t > 50 * 60:  # 세션 1시간 만료 전 재로그인
                    s = _login()
                    login_t = time.time()
                    print("[krx_mdc] 재로그인", file=sys.stderr, flush=True)
                    time.sleep(sleep)
                try:
                    rows = _fetch(s, mkt, dd, sleep)
                except RuntimeError:
                    # 한 번 재로그인 후 재시도, 그래도 실패면 멈춘다(차단 징후)
                    print(f"[krx_mdc] {dd} {mkt} 연속 실패 — 재로그인 후 1회 재시도", file=sys.stderr, flush=True)
                    time.sleep(sleep * 10)
                    s = _login()
                    login_t = time.time()
                    try:
                        rows = _fetch(s, mkt, dd, sleep)
                    except RuntimeError:
                        print(f"[krx_mdc] STOP 연속 실패 at {dd} {mkt}", file=sys.stderr, flush=True)
                        return 2
                n_req += 1
                n_rows += len(rows)
                if day_rows >= 0:
                    day_rows += len(rows)
                fh.write(json.dumps({"trd_dd": dd, "mkt": mkt, "n": len(rows), "rows": rows}, ensure_ascii=False) + "\n")
                fh.flush()
                time.sleep(sleep)
            if day_rows == 0 and d.weekday() < 5:
                empty_weekday_run += 1
                if empty_weekday_run >= 8:
                    print(f"[krx_mdc] STOP 평일 빈 응답 8일 연속(마지막 {dd}) — 차단 의심", file=sys.stderr, flush=True)
                    return 2
            elif day_rows != 0:
                empty_weekday_run = 0
            if n_req and n_req % 100 == 0:
                print(f"[krx_mdc] progress date={dd} req={n_req} rows={n_rows} elapsed_s={time.time() - t0:.0f}",
                      file=sys.stderr, flush=True)
    print(f"[krx_mdc] DONE {start}~{end} req={n_req} rows={n_rows} elapsed_s={time.time() - t0:.0f}",
          file=sys.stderr, flush=True)
    return 0


_INDEXES = (("KOSPI", "1", "001"), ("KOSPI200", "1", "028"), ("KOSDAQ", "2", "001"))


def index(start: str, end: str, out: str, sleep: float) -> None:
    s = _login()
    time.sleep(sleep)
    with open(out, "a", encoding="utf-8") as fh:
        for name, i1, i2 in _INDEXES:
            y = int(start[:4])
            while y <= int(end[:4]):
                a = max(start, f"{y}0101")
                b = min(end, f"{y + 1}1231")
                data = {"bld": "dbms/MDC/STAT/standard/MDCSTAT00301", "locale": "ko_KR", "indIdx": i1,
                        "indIdx2": i2, "strtDd": a, "endDd": b, "share": "1", "money": "1", "csvxls_isNo": "false"}
                r = s.post(_URL, data=data, timeout=30)
                rows = r.json().get("output", []) if r.status_code == 200 and r.text.strip() != "LOGOUT" else None
                if rows is None:
                    print(f"[krx_mdc] index {name} {a}~{b} http={r.status_code} body={r.text[:40]!r}", file=sys.stderr, flush=True)
                    rows = []
                fh.write(json.dumps({"index": name, "start": a, "end": b, "n": len(rows), "rows": rows}, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"[krx_mdc] index {name} {a}~{b} rows={len(rows)}", file=sys.stderr, flush=True)
                y += 2
                time.sleep(sleep)


def main() -> None:
    a = sys.argv[1:]
    if not a or a[0] not in ("probe", "stream", "index"):
        print(__doc__)
        sys.exit(1)
    out = a[a.index("--out") + 1]
    sleep = float(a[a.index("--sleep") + 1]) if "--sleep" in a else 2.0
    if a[0] == "probe":
        probe([x for x in a[1:] if x.isdigit() and len(x) == 8], out, sleep)
    elif a[0] == "stream":
        sys.exit(stream(a[1], a[2], out, sleep))
    else:
        index(a[1], a[2], out, sleep)


if __name__ == "__main__":
    main()
