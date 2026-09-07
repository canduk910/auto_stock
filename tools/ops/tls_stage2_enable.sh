#!/usr/bin/env bash
# cycle260 (2026-09-05) — TLS 2단계(http→https 301 · HSTS) 전환/해제.
#
# EC2 에서 운영자가 1회 수동으로 실행한다. **가동 조건(사용자 결정, 09-05 보고서 2부 카드
# ④) = 월 09-07 20:20 자동 리포트가 https 로 성공한 것을 사람이 확인한 뒤.** 그 확인은
# 기계가 대신할 수 없으므로 `ROUTINE_HTTPS_CONFIRMED=1` 환경변수를 사람이 직접 넣는 것이
# 유일한 게이트다 — 스크립트는 그 값을 검사만 하고 리포트 자체를 확인하지 않는다.
#
# ■ 1단계 종속 — 이 스크립트는 `.tls_enabled`(cycle255, 443 오버레이) 가 이미 켜져 있고
#   실제로 살아 있을 때만 진행한다. 443 이 없는 상태에서 80 을 https 로 301 하면 사이트가
#   **도달 불가**가 된다(리다이렉트 뒤에 듣는 서버가 없다 — 무한 리다이렉트보다 나쁘다).
#
# ■ 순서 — 실패 지점마다 반쪽 상태를 만들지 않는다:
#   1) 사람 게이트: `ROUTINE_HTTPS_CONFIRMED` 가 정확히 `1` 이 아니면 아무것도 부르지
#      않고 멈춘다(`0`·`yes`·빈 문자열 같은 오타 통과 금지).
#   2) `.tls_enabled` 존재 확인.
#   3) 인증서 산출물 확인 — `/etc/letsencrypt/live` 는 root 700 이라 일반 사용자의
#      `[ -f ]` 는 EACCES 로 거짓 '없음'을 낸다(cycle255 실측) → `sudo test -f`.
#   4) 전환 **전** https 가 실제로 401 인지 확인 — 여기서 통과시키고 전환하면, 그 다음
#      실패가 "2단계가 깼다"로 오귀인된다.
#   5) `.tls_stage2` 마커 생성(**up 앞**) → `-f prod -f tls -f tls2 up -d --no-deps
#      frontend`(backend 무접촉, cycle232 D6).
#   6) 사후 검증 4경로 + frontend State, ≤10초 폴링:
#      80 `/` → 301 + `Location: https://auto.dkstock.cloud/`(도메인 고정 — IP 접속이
#      인증서 이름 불일치로 막히면 안 된다) · 80 ACME 경로 → 404(301 이면 90일 뒤 갱신이
#      깨진다) · 443 `/` → 401 + HSTS(문서 응답) · 443 정적자산 → HSTS(add_header 는
#      상속이 아니라 **대체** — location 마다 따로 붙어야 한다. 정적자산만 누락되는
#      경우는 브라우저 개발자도구를 열지 않으면 안 보인다). HSTS 매치는 `hsts_ok()`
#      (cycle267) — `tr -d '\r'` 로 CR 을 먼저 제거한 뒤 정확 값 앵커 매치한다. GNU
#      grep `-E` 는 패턴 속 `\r` 을 리터럴 `r` 로 해석해 CRLF 헤더에 영구히 매치 실패하고
#      (2026-09-07 EC2 가동 실패 원인), macOS BSD grep 은 같은 패턴을 CR 로 해석해 개발기
#      에서만 통과한다 — `tr` 사전 제거가 이 셸 차이를 없앤다.
#   7) 실패(전환 up 자체의 실패 포함) → `.tls_stage2` 만 삭제 + `-f prod -f tls up -d
#      --no-deps frontend` 로 **1단계로 원복** + 원복 뒤 80/443 재확인. `.tls_enabled` 는
#      절대 지우지 않는다 — 지우면 443 이 함께 내려가 2단계 원복이 아니라 TLS 전체
#      후퇴가 된다.
#
# ■ `disable` — 같은 원복 절차를 사람이 부르는 경로(게이트 불필요, 끄는 것은 언제나 허용).
#   `.tls_enabled` 는 건드리지 않는다 — 2단계만 끄고 443 은 유지하는 것이 이 명령의 정의다.
#
# ■ 환경변수
#   ROUTINE_HTTPS_CONFIRMED=1   사람 게이트(필수, enable 만). 다른 값·미설정은 실패.
#   LE_LIVE_DIR                 certbot live 디렉터리 seam(기본 /etc/letsencrypt/live/<도메인>).
#                               cycle255 `tls_enable.sh` 와 같은 이름 — 테스트 하네스가 덮어쓴다.
#
# ⚠️ 비밀값을 이 파일에 리터럴로 두지 않는다(git 커밋 대상).
set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "${REPO_DIR}"

ACTION="${1:-enable}"
DOMAIN="auto.dkstock.cloud"
BASE="docker-compose.prod.yml"
TLS="docker-compose.tls.yml"
TLS2="docker-compose.tls2.yml"
MARKER=".tls_stage2"
STAGE1=".tls_enabled"
LIVE_DIR="${LE_LIVE_DIR:-/etc/letsencrypt/live/${DOMAIN}}"

log() { echo "[tls_stage2] $*"; }

# `-D -`(헤더를 stdout 으로 덤프) + `-w '%{http_code}'`(상태코드를 본문 뒤에 이어 붙임) —
# 한 번의 호출로 헤더 존재와 상태코드를 모두 얻는다. `-D-` 붙여쓰기는 curl 이 다른 인자로
# 오인하므로 반드시 공백으로 띄운다.
probe80() { curl -s -o /dev/null -D - -w '%{http_code}' "$1" || true; }
probe443() { curl -sk -o /dev/null -D - -w '%{http_code}' --resolve "${DOMAIN}:443:127.0.0.1" "$1" || true; }
# probe 결과 문자열의 마지막 줄이 상태코드다(그 앞은 헤더 덤프).
code_of() { printf '%s' "$1" | tail -n1; }

HSTS_VALUE="max-age=86400"
# HSTS 헤더 검사. CR 을 **먼저 제거**한 뒤 정확 값으로 앵커 매치한다.
# GNU grep 의 -E 는 패턴 안의 `\r` 을 캐리지 리턴이 아니라 리터럴 `r` 로 해석하므로
# (GNU grep 3.11 실측), `...86400\r?$` 는 CRLF 로 끝나는 실제 HTTP 헤더에 절대 매치되지
# 않는다 — 2026-09-07 EC2 2단계 가동 실패의 원인이다(cycle260 이 접두 매치 뮤테이션을
# 막으려다 심은 결함). macOS BSD grep 은 같은 패턴을 CR 로 해석해 개발기에서 은폐된다.
# `tr -d '\r'` 는 셸·grep 의 이스케이프 해석에 전혀 의존하지 않아 CRLF·LF 양쪽에서
# 동일하게 동작하고, 끝 `$` 앵커가 `max-age=0`·`max-age=864000`·초과 속성을 계속 막는다.
hsts_ok() { printf '%s' "$1" | tr -d '\r' | grep -qiE "^Strict-Transport-Security: ${HSTS_VALUE}$"; }

# 원복 = 마커 삭제(1단계 마커는 절대 건드리지 않는다) + **그 자리의 1단계 상태**로 frontend
# 재기동. `enable` 경로의 실패 원복은 항상 `.tls_enabled` 가 있는 상태에서 일어난다(2 가
# 그것을 이미 확인했다) — 그러나 `disable` 은 게이트 없이 언제든 불릴 수 있어 1단계가 이미
# 원복된 호스트(마커 없음·인증서 없음/만료)에서 불릴 수 있다. 그 상태에서 443 오버레이를
# 올리면 nginx 가 인증서 부재로 `[emerg]` 기동 실패하고 **같은 컨테이너인 80 까지 내려간다**
# (cycle255 F1 이 고친 실패 계열의 재현) — 그래서 파일 목록을 `.tls_enabled` 존재로
# 조건부 구성한다. `docker compose up -d` 는 크래시 루프여도 exit 0 이다(compose v5.1 실측,
# cycle255) — 원복이 실제로 사이트를 되살렸는지 여기서 다시 80(/443)을 재확인해 로그로 남긴다.
rollback_to_stage1() {
    rm -f "${MARKER}"
    if [ -f "${STAGE1}" ]; then
        FILES=(-f "${BASE}" -f "${TLS}")
        log "원복 실행: 2단계 마커 삭제 → 1단계 구성(prod+tls)으로 frontend 재기동"
    else
        FILES=(-f "${BASE}")
        log "원복 실행: 2단계 마커 삭제 → 1단계 마커도 없다 — prod 단독 구성으로 frontend 재기동(443 오버레이 생략 — 인증서 없이 올리면 80 까지 죽는다)"
    fi
    if docker compose "${FILES[@]}" up -d --no-deps frontend; then
        R80="$(probe80 "http://127.0.0.1/")"
        if [ -f "${STAGE1}" ]; then
            R443="$(probe443 "https://${DOMAIN}/api/health")"
            log "원복 후 재확인: 80=$(code_of "${R80}") 443=$(code_of "${R443}")"
        else
            log "원복 후 재확인: 80=$(code_of "${R80}") (443 오버레이 없음 — 1단계 마커 부재)"
        fi
    else
        log "원복 up 도 실패 — 수동 조치: docker compose ${FILES[*]} up -d --no-deps frontend"
    fi
}

if [ "${ACTION}" = "disable" ]; then
    rollback_to_stage1
    if [ -f "${STAGE1}" ]; then
        log "완료(2단계 해제). 443 은 그대로 유지된다(.tls_enabled 무변경)."
    else
        log "완료(2단계 해제). 1단계 마커도 이미 없어 443 오버레이 없이 원복했다."
    fi
    exit 0
fi

# 1 — 사람 게이트. 20:20 자동 리포트가 https 로 성공한 것을 사람이 눈으로 확인한 뒤에만
# 넣는 값이다 — 그 확인 자체를 스크립트가 대신할 수 없다.
if [ "${ROUTINE_HTTPS_CONFIRMED:-}" != "1" ]; then
    echo "[tls_stage2] 실패: ROUTINE_HTTPS_CONFIRMED=1 이 필요하다." >&2
    echo "[tls_stage2]   (월 09-07 20:20 자동 리포트가 https 로 성공한 것을 확인한 뒤 실행)" >&2
    echo "[tls_stage2]   예: ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh" >&2
    exit 1
fi

# 2 — 1단계 종속. 443 없이 80 을 301 하면 사이트가 도달 불가가 된다.
if [ ! -f "${STAGE1}" ]; then
    log "실패: 1단계 마커(${STAGE1})가 없다 — 443 없이 301 하면 사이트가 도달 불가가 된다."
    exit 1
fi

# 3 — 인증서 산출물 확인. root 700 디렉터리라 일반 사용자의 `[ -f ]` 는 EACCES 로 거짓
# '없음'을 낸다(cycle255 실측) — `sudo test -f` 로 확인한다.
if ! sudo test -f "${LIVE_DIR}/fullchain.pem"; then
    log "실패: 인증서 산출물이 없다: ${LIVE_DIR}/fullchain.pem"
    exit 1
fi

# 4 — 전환 전 https 가 실제로 살아 있는지 응답으로 재확인(파일 존재만으론 부족하다).
PRE="$(probe443 "https://${DOMAIN}/api/health")"
if [ "$(code_of "${PRE}")" != "401" ]; then
    log "실패: 전환 전 443 이 401 이 아니다(응답=$(code_of "${PRE}")) — 1단계가 살아 있지 않다."
    exit 1
fi

# 5 — 마커는 up **앞**(뒤면 그 up 은 2단계 없는 구성이고, 마커만 남아 다음 자동 배포가
# 검증 없이 2단계를 올린다).
touch "${MARKER}"
log "마커 생성: ${MARKER}"
if ! docker compose -f "${BASE}" -f "${TLS}" -f "${TLS2}" up -d --no-deps frontend; then
    log "실패: 2단계 오버레이 up 이 non-zero."
    rollback_to_stage1
    exit 1
fi

# 6 — 사후 검증. `up -d` 의 exit 0 은 기동 성공이 아니다 — 실제 응답 4경로 + State 를
# 같은 이터레이션에서 본다.
OK=0
R80=""; RACME=""; RDOC=""; RASSET=""; STATE=""
log "사후 검증(≤10초 폴링): 80→301(도메인 고정) · ACME→404 · 443 문서/정적자산→401+HSTS"
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    R80="$(probe80 "http://127.0.0.1/")"
    RACME="$(probe80 "http://127.0.0.1/.well-known/acme-challenge/probe")"
    RDOC="$(probe443 "https://${DOMAIN}/")"
    RASSET="$(probe443 "https://${DOMAIN}/assets/index.js")"
    STATE="$(docker compose -f "${BASE}" -f "${TLS}" -f "${TLS2}" ps --format json frontend 2>/dev/null | grep -o -m1 '"State":"[a-z]*"' || true)"
    if [ "$(code_of "${R80}")" = "301" ] \
       && printf '%s' "${R80}" | grep -qi "^Location: https://${DOMAIN}/" \
       && [ "$(code_of "${RACME}")" = "404" ] \
       && [ "$(code_of "${RDOC}")" = "401" ] \
       && hsts_ok "${RDOC}" \
       && hsts_ok "${RASSET}" \
       && [ "${STATE}" = '"State":"running"' ]; then
        OK=1
        break
    fi
    sleep 1
done
if [ "${OK}" != "1" ]; then
    log "실패: 사후 검증 미통과 — 80=$(code_of "${R80}") acme=$(code_of "${RACME}") 443=$(code_of "${RDOC}") state=${STATE:-none}"
    log "  진단: docker compose -f ${BASE} -f ${TLS} -f ${TLS2} logs --tail=50 frontend"
    rollback_to_stage1
    exit 1
fi
log "사후 검증 통과: 80=301 acme=404 443=401+HSTS state=running"
log "완료(2단계 가동)."
log ""
log "다음 절차(가동 직후 필수 — 80 은 이제 자격을 요구하지 않을 뿐 선제 전송까지 막지는 못한다):"
log "  ① Claude 루틴 2개(일일 리포트 20:20 · 주간 자문 화 20:30) 프롬프트의 http EC2 예비 경로"
log "     제거 — 가동 뒤 http 로 curl 하면 평문 Authorization 헤더를 먼저 보내고 301 을 받는다."
log "  ② bash tools/ops/rotate_basic_auth.sh 실행 → secrets/.rotated-* 를 읽어 클라우드 환경"
log "     REPORTER_BASIC_PASSWORD 갱신 → 다음 자동 리포트 실행에서 200 확인 → .rotated-* 삭제."
log "  ③ http 로 열어 둔 브라우저 탭을 https://${DOMAIN}/ 로 재접속(HSTS 학습 전 첫 요청은"
log "     여전히 평문으로 나갈 수 있다)."
