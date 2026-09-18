#!/usr/bin/env bash
# 매크로 화면 미리 데우기 — 매일 00:05 KST (cycle314, 사용자 결정 2026-09-19 "D2 ⓒ 둘 다")
#
# 왜 필요한가 — 콜드 캐시 첫 호출 실측(2026-09-18 운영):
#   yield-curve 14.2s · credit-spread 52.4s · **macro-cycle 107.0s** · 환율/원자재 1s 내외
# `macro-cycle` 은 5지표를 다 모으느라 nginx `proxy_read_timeout` 을 넘겨 **504** 가 났다.
# 그 107초의 대부분은 FRED 가 아니라 **yfinance**(섹터 ETF 11종·버핏지수·공포탐욕)라
# `MACRO_LITE_FRED_TIMEOUT` 을 낮춰도 줄지 않는다. 그래서 사람이 열기 전에 미리 한 번 친다.
#
# 🔴 **호출 순서가 설계다** — credit-spread 를 먼저 친다. 그 응답이 일일 캐시
# (`macro:daily:credit_spread:{날짜}`)와 fetcher 24h 캐시를 채우므로, 뒤이은 macro-cycle 은
# 신용스프레드 구간을 캐시로 건너뛴다. 순서를 뒤집으면 같은 FRED 왕복을 두 번 한다.
#
# 🔴 **nginx 를 거치지 않는다** — 사이트 전체가 Basic Auth 뒤에 있어 자격이 필요하고,
# 그 자격을 cron 스크립트에 두면 비밀값이 파일로 새어 나간다. 도커 네트워크 안에서
# macro 컨테이너를 직접 쳐서 **같은 캐시**를 채운다(캐시는 컨테이너 안 `MACRO_LITE_CACHE_DIR`).
#
# 🔴 **EC2 는 UTC 다** — crontab 시각은 KST 가 아니다. 등록 예:
#     # 00:05 KST = 15:05 UTC (전날)
#     5 15 * * * /home/ubuntu/auto_stock/tools/ops/macro_prewarm.sh >> /home/ubuntu/auto_stock/logs/macro_prewarm.log 2>&1
# FRED 는 전 영업일분을 KST 밤 22~23시에 게시하므로 00:05 면 최신값이 잡힌다.
#
# 매매와 무접촉이다 — macro 컨테이너만 건드리고 backend 는 쳐다보지도 않는다.
set -uo pipefail
export TZ=Asia/Seoul

cd "$(dirname "$0")/../.." || exit 1

COMPOSE="docker compose -f docker-compose.prod.yml"
[ -f .tls_enabled ] && COMPOSE="$COMPOSE -f docker-compose.tls.yml"
[ -f .tls_stage2 ] && COMPOSE="$COMPOSE -f docker-compose.tls2.yml"

# credit-spread 를 먼저 — 그 캐시를 macro-cycle 이 재사용한다.
ENDPOINTS="credit-spread macro-cycle yield-curve currencies commodities"

echo "[$(date '+%F %H:%M:%S %Z')] macro prewarm 시작"

sudo $COMPOSE exec -T macro python - "$ENDPOINTS" <<'PY'
import sys, time, urllib.request

total = 0.0
for path in sys.argv[1].split():
    t = time.time()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8000/api/macro/{path}", timeout=300) as r:
            code, size = r.status, len(r.read())
    except Exception as e:                      # 하나가 죽어도 나머지는 계속 데운다
        code, size = f"ERR {type(e).__name__}", 0
    el = time.time() - t
    total += el
    print(f"  {path:<14} {code} {el:6.1f}s {size}B", flush=True)
print(f"  합계 {total:.1f}s", flush=True)
PY

echo "[$(date '+%F %H:%M:%S %Z')] macro prewarm 끝"
