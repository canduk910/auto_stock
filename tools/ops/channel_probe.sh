#!/usr/bin/env bash
# tools/ops/channel_probe.sh — KRX 단독 채널(H0STCNT0) 프로브 자동 실행 (cycle253 엔드포인트 사용)
#
# 목적: "통합 채널 H0UNCNT0 이 nxt_tradable=False 종목 프레임을 안 보내는데, KRX 전용 채널
#       H0STCNT0 은 보내는가" 를 장중 15분 실측한다 (포렌식 P1-7 B 1단계, 사용자 승인 D8 2026-09-05).
#
# 동작: 후보 종목을 순서대로 POST 해 2개가 수락될 때까지 시도(409 = 다음 후보) → 5분 간격 상태 3회
#       → DELETE 로 전부 해제 → 결과를 로그 파일과 stdout 에 남긴다. 실패·예외 경로에서도 해제를 시도한다.
# 안전: 엔드포인트가 기구독·보유·익일청산·후보(desired) 종목을 409 로 거부하고 bypass_limit=False·LOW 슬롯만
#       쓴다. 이 스크립트는 그 위에 (a) 프로브 창 ≤15분 (b) in_desired_now=true 관측 시 즉시 해제
#       (c) 종료 시 무조건 DELETE (d) 자기 cron 항목 제거 를 더한다.
# 사용: EC2 ~/auto_stock 에서  bash tools/ops/channel_probe.sh run [후보,후보,...]
#       상태만:               bash tools/ops/channel_probe.sh status
#       전부 해제:             bash tools/ops/channel_probe.sh stop
#       cron 등록(1회성):      bash tools/ops/channel_probe.sh install-cron "30 9 7 9 *"
# 키: .env 의 API_AUTH_KEY 를 읽어 루프백(127.0.0.1:8000)에만 보낸다. 키는 출력하지 않는다.
set -u

cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo "$HOME/auto_stock")" || exit 2
BASE="${PROBE_BASE:-http://127.0.0.1:8000}"
TR_ID="${PROBE_TR_ID:-H0STCNT0}"
WANT="${PROBE_WANT:-2}"
POLLS="${PROBE_POLLS:-3}"
POLL_SECS="${PROBE_POLL_SECS:-300}"
LOG_DIR="logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/channel_probe_$(date +%Y%m%d).log"
# 후보 기본값 = 포렌식 4일 공통 no_feed 유동주 + KRX 단독 ETF 예비 (엔드포인트가 부적격은 409 로 거른다)
DEFAULT_CANDS="005935,035720,006360,009830,047040,002990,353200,403870,079650,010170,069500,102110"

key() { grep '^API_AUTH_KEY=' .env | cut -d= -f2-; }
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
api() { # method path [json]
  local m="$1" p="$2" d="${3:-}"
  if [ -n "$d" ]; then
    curl -s -m 20 -X "$m" -H "X-API-Key: $(key)" -H 'Content-Type: application/json' -d "$d" "$BASE$p"
  else
    curl -s -m 20 -X "$m" -H "X-API-Key: $(key)" "$BASE$p"
  fi
}
jget() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

status() { api GET /api/realtime/channel-probe; }

stop_all() {
  local st; st=$(status)
  local tickers; tickers=$(printf '%s' "$st" | jget "' '.join(p['ticker'] for p in d.get('data',{}).get('probes',[]))")
  for t in $tickers; do
    local r; r=$(api DELETE "/api/realtime/channel-probe/$t")
    log "DELETE $t → $(printf '%s' "$r" | cut -c1-160)"
  done
  [ -z "$tickers" ] && log "DELETE: 활성 프로브 없음"
}

run() {
  local cands="${1:-$DEFAULT_CANDS}"
  log "=== channel_probe run 시작 tr_id=$TR_ID want=$WANT polls=$POLLS×${POLL_SECS}s cands=$cands"
  trap 'log "trap: 종료 전 해제"; stop_all' EXIT
  local accepted=0
  IFS=',' read -ra arr <<< "$cands"
  for t in "${arr[@]}"; do
    [ "$accepted" -ge "$WANT" ] && break
    local r code
    r=$(curl -s -m 20 -o /tmp/cp_body.json -w '%{http_code}' -X POST -H "X-API-Key: $(key)" -H 'Content-Type: application/json' \
        -d "{\"ticker\":\"$t\",\"tr_id\":\"$TR_ID\"}" "$BASE/api/realtime/channel-probe")
    code="$r"; local body; body=$(cut -c1-200 </tmp/cp_body.json)
    log "POST $t → $code $body"
    if [ "$code" = "200" ]; then accepted=$((accepted+1)); fi
    sleep 1
  done
  if [ "$accepted" -eq 0 ]; then log "결과: 수락된 후보 0 — 후보 목록을 바꿔 재시도 필요"; return 1; fi
  local i received_any=0
  for i in $(seq 1 "$POLLS"); do
    sleep "$POLL_SECS"
    local st; st=$(status)
    log "STATUS $i/$POLLS: $(printf '%s' "$st" | cut -c1-600)"
    # in_desired_now=true 인 프로브는 즉시 해제 (프로브 중 후보 편입 — 라우팅 덮어쓰기 차단)
    local hot; hot=$(printf '%s' "$st" | jget "' '.join(p['ticker'] for p in d.get('data',{}).get('probes',[]) if p.get('in_desired_now') is True)")
    for t in $hot; do log "in_desired_now=true → 즉시 해제 $t: $(api DELETE "/api/realtime/channel-probe/$t" | cut -c1-120)"; done
    local rec; rec=$(printf '%s' "$st" | jget "sum(1 for p in d.get('data',{}).get('probes',[]) if p.get('received') is True)")
    [ "${rec:-0}" -gt 0 ] && received_any=1
  done
  if [ "$received_any" = 1 ]; then
    log "결론: received=true 관측 — KRX 전용 채널($TR_ID)이 nxt_false 종목 시세를 송출함 (가설 확정 → B 채널 리졸버 착수 후보)"
  else
    log "결론: ${POLLS}회 모두 received=false — 반증(또는 후보 부적격). subscribed/acked 값과 함께 KIS 문의 검토"
  fi
  return 0
}

install_cron() {
  local spec="${1:-30 9 7 9 *}"  # 기본 = 2026-09-07 09:30 (월) 1회성 — 실행 후 자기 항목 제거
  local here; here="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  local line="$spec cd $HOME/auto_stock && bash $here run >> $HOME/auto_stock/logs/channel_probe_cron.out 2>&1; crontab -l | grep -v channel_probe.sh | crontab -  # channel_probe.sh one-shot"
  ( crontab -l 2>/dev/null | grep -v 'channel_probe.sh' ; echo "$line" ) | crontab -
  log "cron 등록: $spec (실행 후 자기 제거)"; crontab -l | grep channel_probe.sh
}

case "${1:-}" in
  run) run "${2:-}";;
  status) status; echo;;
  stop) stop_all;;
  install-cron) install_cron "${2:-}";;
  *) echo "usage: $0 run [cands] | status | stop | install-cron [cron-spec]"; exit 2;;
esac
