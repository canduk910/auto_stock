#!/usr/bin/env bash
# 2026-10-19(월) D+1 확인 — cycle464·465·467·468 (+ 배포됐다면 469·470·472·473)
# 실행: ssh auto-stock 'bash -s' < _workspace/checks/2026-10-19_d1_check.sh
# 권장 시각: 1차 09:40 이후(장 시작 확인) · 2차 21:40 이후(정산·외부입출금 확인)
export TZ=Asia/Seoul
cd ~/auto_stock || exit 1
echo "== $(date '+%F %T') deployed=$(cut -c1-8 .deployed_sha)"
docker compose -f docker-compose.prod.yml ps --format '{{.Service}} {{.Status}}'

docker compose -f docker-compose.prod.yml exec -T backend python - <<"EOF" 2>&1 | tail -80
import asyncio
from src.db import pg

import os
from datetime import date
DAY = date.fromisoformat(os.environ.get("CHECK_DAY", "2026-10-19"))  # asyncpg 는 DATE 에 str 바인딩 불가
Q = """select to_char(timestamp,'HH24:MI:SS') t, log_level l, left(message, 230) m
       from system_logs where timestamp >= $1::date and timestamp < $1::date + 1
       and message ilike $2 order by timestamp limit $3"""

async def show(title, pat, limit=20):
    rows = await pg.fetch(Q, DAY, pat, limit)
    print(f"\n== {title} ({len(rows)}{'+' if len(rows) == limit else ''})")
    for r in rows:
        print(r["t"], r["l"], r["m"])

async def count(title, pat):
    n = await pg.fetchval("select count(*) from system_logs where timestamp >= $1::date and timestamp < $1::date + 1 and message ilike $2", DAY, pat)
    print(f"== {title}: {n}")

async def main():
    await pg.init_pool()
    # 1. cycle465 — 대표 구독 3건(07:45 기동 뒤)
    await show("대표 구독 [market_status_rep_subscribed] — 3건이어야", "%[market_status_rep_subscribed]%", 10)
    # 2. cycle468 — 코드 변화 기록. 정상일 = INFO 만, ST(숫자)에 110/112/121/129 가 보여야
    await show("코드 변화 [market_status_code_trace]", "%[market_status_code_trace]%", 60)
    n = await pg.fetchval("select count(*) from system_logs where timestamp >= $1::date and timestamp < $1::date + 1 and log_level = 'WARNING' and message ilike $2", DAY, "%[market_status_code_trace]%")
    print(f"== 그중 WARNING(정상 밖 코드): {n}")
    # 3. 평일에 AF8/AF1/BF9 가 나오면 _UN_CODES_DRIVE_STATE 를 False 로 내릴 대상
    await show("CB 상태 마커 [market_cb_active]/[market_cb_release]/[stale_skip_market_cb", "%[market_cb_%", 20)
    await show("처음 보는 코드 [market_status_unknown_code]", "%[market_status_unknown_code]%", 20)
    # 4. cycle464 — ndx2x 적재
    await show("ndx2x 적재 [ndx2x_ingest_outcome]", "%[ndx2x_ingest_outcome]%", 5)
    await count("ndx2x 낡음 경보 [ndx2x_data_stale] — 0 이어야", "%[ndx2x_data_stale]%")
    # 5. cycle467 — AI 매수평가(새 프롬프트, 문턱 50)
    rows = await pg.fetch("""select strategy_id, count(*) n, round(avg(score)) a, max(score) mx,
                                    sum(case when would_block then 1 else 0 end) blocked
                             from llm_buy_evaluations where trade_date = $1::date group by 1 order by 1""", DAY)
    print("\n== AI 매수평가(오늘)", [dict(r) for r in rows] or "0건")
    # 6. 시장 배수(오늘 적용)
    await show("시장 유닛 [market_unit_state]", "%[market_unit_state]%", 6)
    # 7. (배포됐다면) cycle470 섀도 · cycle469 외부입출금 · cycle473 시세 풀 본문
    await show("cycle470 [silent_inactive_ws_shadow]", "%[silent_inactive_ws_shadow]%", 10)
    await show("cycle470 [silent_inactive_market_wide_counter_evidence]", "%counter_evidence]%", 5)
    await show("cycle469 [settle_ext_cashflow] (21:30 뒤)", "%[settle_ext_cashflow]%", 3)
    await show("cycle473 시세 풀 5xx detail", "%[quote_pool] HTTP 5%", 5)
    # 8. 오류
    n = await pg.fetchval("select count(*) from system_logs where timestamp >= $1::date and timestamp < $1::date + 1 and log_level in ('ERROR','CRITICAL')", DAY)
    print(f"\n== ERROR/CRITICAL: {n}")
    for r in await pg.fetch("""select left(message, 120) m, count(*) c from system_logs
                               where timestamp >= $1::date and timestamp < $1::date + 1 and log_level in ('ERROR','CRITICAL')
                               group by 1 order by 2 desc limit 8""", DAY):
        print(r["c"], r["m"])
    await pg.close_pool()

asyncio.run(main())
EOF
