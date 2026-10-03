"""cycle404 — 요인 ETF 후보 실측 + 픽스처 추출 (운영 DB 읽기 전용, 사람이 실행).

⚠️ 이 스크립트는 domain-expert 가 실행하지 못했다(운영 DB 읽기 권한 거부, 10-03).
   운영자가 아래처럼 직접 돌리고 결과 두 파일을 워크트리에 놓는다.

    ssh auto-stock 'cd ~/auto_stock && docker compose -f docker-compose.prod.yml \
        exec -T backend python -' < _workspace/domain_consult/cycle404_extract_fixture.py \
        > /tmp/cycle404_out.json

    python - <<'EOF'
    import json; o = json.load(open('/tmp/cycle404_out.json'))
    json.dump(o['fixture'], open('tests/fixtures/cycle404_cluster_closes.json', 'w'), ensure_ascii=False)
    json.dump(o['survey'], open('_workspace/domain_consult/cycle404_factor_survey.json', 'w'),
              ensure_ascii=False, indent=1)
    EOF

세션 첫 문장 = `SET default_transaction_read_only = on`. SELECT 만 한다. 쓰기 0.
"""
import asyncio
import json
import os

import asyncpg

WINDOW_BARS = 121

MARKET = "069500"
HOLDINGS = [
    "232140", "101160", "083450", "046890", "011790", "425040", "005930",
    "417200", "126340", "217590", "121600", "003490", "006120",
]
# 후보는 넉넉히 넣는다 — 봉 수·거래대금·상관 중복으로 걸러 10~15개로 줄인다.
FACTOR_CANDIDATES = [
    "091160", "091230",            # 반도체 (KODEX · TIGER)
    "305720", "305540",            # 2차전지
    "244580", "143860", "266420",  # 바이오·헬스케어
    "091180",                      # 자동차
    "139230", "466920",            # 중공업 · 조선
    "449450",                      # 방산
    "117460", "139250",            # 에너지화학
    "117680",                      # 철강
    "117700",                      # 건설
    "091170", "102970", "140700",  # 은행 · 증권 · 보험
    "266370", "139260",            # IT
    "228810",                      # 미디어·콘텐츠
    "229200",                      # 코스닥150 (요인 후보 아님 — 비교용)
]


async def main():
    c = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql"))
    await c.execute("SET default_transaction_read_only = on")
    tickers = sorted(set([MARKET] + HOLDINGS + FACTOR_CANDIDATES))

    meta = {
        r["ticker"]: r
        for r in await c.fetch(
            "SELECT ticker, name, is_kospi200, is_kosdaq150, "
            "raw->>'hts_avls' AS hts_avls, raw->>'acml_tr_pbmn' AS acml_tr_pbmn, "
            "raw->>'scty_grp_id_cd' AS grp "
            "FROM stock_master WHERE ticker = ANY($1)",
            tickers,
        )
    }
    survey, series = {}, {}
    as_of = None
    for t in tickers:
        rows = await c.fetch(
            "SELECT bas_dd, close_price, trade_value FROM stock_master_daily "
            "WHERE ticker = $1 ORDER BY bas_dd DESC LIMIT 225",
            t,
        )
        tv20 = [int(r["trade_value"] or 0) for r in rows[:20]]
        m = meta.get(t)
        survey[t] = {
            "name": m and m["name"],
            "bars_total": len(rows),
            "newest": rows and str(rows[0]["bas_dd"]),
            "avg_trade_value_20d_won": (sum(tv20) // len(tv20)) if tv20 else None,
            "min_trade_value_20d_won": min(tv20) if tv20 else None,
            "is_index": bool(m and (m["is_kospi200"] or m["is_kosdaq150"])),
            "raw_hts_avls_eok": m and m["hts_avls"],
            "raw_acml_tr_pbmn_won": m and m["acml_tr_pbmn"],
            "grp": m and m["grp"],
        }
        win = list(reversed(rows[:WINDOW_BARS]))
        series[t] = [[str(r["bas_dd"]), float(r["close_price"])] for r in win]
        if t == MARKET and rows:
            as_of = str(rows[0]["bas_dd"])
    await c.close()
    print(json.dumps({"survey": survey, "fixture": {"as_of": as_of, "series": series}},
                     ensure_ascii=False))


asyncio.run(main())
