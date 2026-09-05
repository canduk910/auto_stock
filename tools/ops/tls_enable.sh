#!/usr/bin/env bash
# cycle255 (2026-09-05) — auto.dkstock.cloud HTTPS(TLS) 1단계 발급·전환.
#
# EC2 에서 **DNS A 레코드(auto.dkstock.cloud → 3.38.228.74)가 이미 등록된 뒤** 운영자가
# 1회 수동으로 실행한다. 자동 배포 파이프라인(`tools/deploy/compose_up_changed.sh`)에는
# 배선하지 않는다 — 인증서 발급은 Let's Encrypt 실패 rate limit 이 있는 일회성 절차라
# 사람이 각 단계 결과를 보며 진행하는 편이 안전하다.
#
# ■ 순서 — 실패 지점마다 반쪽 상태(인증서는 있는데 마커만 없음 / 마커는 있는데 컨테이너는
#   옛 설정)를 만들지 않는다:
#   1/6) `dig` 로 A 레코드가 기대 IP 를 가리키는지 확인 — certbot 호출보다 반드시 **앞**
#        (실패하면 certbot 을 부르지 않는다 — Let's Encrypt 실패 rate limit 소모 방지,
#        하루치가 봉쇄되면 DNS 를 고쳐도 기다리는 것 외엔 방법이 없다).
#   2/6) ACME 챌린지 경로가 이미 무자격 200 인지 확인(cycle255 HTTP 템플릿의 ACME
#        location 이 배포돼 있어야 한다 — 이 스크립트는 그 배포를 만들지 않는다).
#        ⚠️ `./certbot-www` 는 그 배포(prod compose 의 bind mount)가 **root:root 755** 로
#        먼저 만들어 둔다(bind 소스 부재 시 Docker 가 만든다 — `.token_cache` root 소유
#        사고와 동일 계열). ubuntu 의 `mkdir -p` 는 EACCES 로 죽으므로 probe 디렉터리는
#        `sudo install -d -o $(id -u)` 로 만든다(ubuntu:24.04 실측 — 재현·시정 확인. 기존
#        root 소유 최종 디렉터리도 chown 된다). certbot 자체는 sudo 라 영향 없다 — 죽는 건
#        ubuntu 가 쓰는 probe 뿐이다.
#   3/6) `certbot certonly --webroot` 로 발급(80 은 nginx 가 계속 쓴다 — `--standalone`
#        은 80 을 점유해 운영 중인 사이트와 충돌하므로 쓰지 않는다). `--deploy-hook` 으로
#        nginx **reload** 훅을 함께 등록한다 — certbot 이 renewal conf 에 영속시켜 snap/apt
#        timer·수동 `renew` 어느 경로로 갱신돼도 nginx 가 새 인증서를 문다(훅이 없으면
#        디스크 인증서만 바뀌고 nginx 는 옛 인증서를 물고 있다가 만료된다).
#   4/6) 발급 산출물(`fullchain.pem`) 존재를 확인한 **뒤에만** `.tls_enabled` 마커를
#        만든다 — 순서가 뒤집히면 인증서 없는 443 오버레이가 붙어 frontend 가 기동
#        실패하고, 같은 컨테이너인 80 까지 함께 내려간다.
#   5/6) frontend 컨테이너만 재기동(backend 무접촉, cycle232 D6 — 장중에도 전환할 수
#        있어야 한다) + **사후 검증**. `docker compose up -d` 는 컨테이너가 크래시 루프여도
#        exit 0 이다(compose v5.1 실측 — nginx `[emerg]` 로 restarting 이어도 0). 그래서 up 의
#        종료 코드가 아니라 실제 응답(80 → 401 ∧ 443 → 401 ∧ State=running, ≤10×1s 폴링)으로
#        판정하고, 하나라도 실패하면 마커를 지우고 base 단독 up 으로 **원복을 실행**한다
#        (안내만 하지 않는다 — 오버레이 up 이 non-zero 인 상태(443 선점 등)는 컨테이너가
#        created 로 멈춰 80 도 000 이다. base 단독 up 이 Recreate 해야 80 이 돌아온다).
#   6/6) 갱신 경로 검증 — reload 훅 명령을 그 자리에서 1회 실행 + `certbot renew --dry-run`.
#        실패해도 전환은 되돌리지 않는다(인증서는 90일 유효 — 갱신 결함은 그 안에 고친다).
#        대신 WARNING 으로 크게 남기고 종료 코드는 0 이다(전환 성공과 갱신 결함을 섞지 않는다).
#
# ■ 원복 절차 — 전환 실패 시 **스크립트가 자동 실행**한다. 되돌리고 싶을 때 수동으로도 동일:
#     rm -f .tls_enabled
#     docker compose -f docker-compose.prod.yml up -d --no-deps frontend
#   80 은 이 원복 up 이 성공한 뒤에 다시 살아있다(오버레이 up 실패 직후엔 000 일 수 있다).
#   인증서(/etc/letsencrypt)는 남으므로 재실행 시 certbot 은 재발급하지 않는다(rate limit 무소모).
#
# ■ 갱신 — `certbot renew` 는 파일만 바꾸고 nginx 는 시작 시점 인증서를 물고 있으므로
#   **reload**(재기동이 아니다) 훅이 필수다. 훅은 3/6 의 `--deploy-hook` 으로 renewal conf
#   (`/etc/letsencrypt/renewal/auto.dkstock.cloud.conf` 의 `renew_hook`)에 영속되고, snap/apt
#   certbot 의 systemd timer 가 하루 2회 `renew` 를 돌린다 — **별도 crontab 을 두지 않는다**
#   (ubuntu crontab 은 /etc/letsencrypt 쓰기 권한이 없고, 상대경로 compose 는 cron cwd 에서
#   'no configuration file' 로 실패한다). 훅은 절대경로 docker + `--project-directory` +
#   절대경로 `-f` 둘 + `exec -T` 로 적어 cwd·TTY 에 의존하지 않는다.
#   확인: `systemctl list-timers | grep certbot` · `sudo grep renew_hook /etc/letsencrypt/renewal/auto.dkstock.cloud.conf`
#
# ⚠️ 비밀값을 이 파일에 리터럴로 두지 않는다(git 커밋 대상). Let's Encrypt 알림 메일은
# 환경변수로 받는다: `LE_EMAIL=ops@example.com bash tools/ops/tls_enable.sh`
# LE_LIVE_DIR — certbot live 디렉터리(기본 /etc/letsencrypt/live/auto.dkstock.cloud).
#   certbot `--config-dir` 를 바꾼 환경과 테스트 하네스만 덮어쓴다. 잘못 주면 4/6 이 실패해
#   마커를 만들지 않는다(안전 방향 — 마커가 먼저 생기는 경로는 없다).
set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "${REPO_DIR}"

if [ -z "${LE_EMAIL:-}" ]; then
    echo "[tls_enable] LE_EMAIL 환경변수(Let's Encrypt 알림 메일)가 없다 — 예:" >&2
    echo "[tls_enable]   LE_EMAIL=ops@example.com bash tools/ops/tls_enable.sh" >&2
    exit 1
fi

log() { echo "[tls_enable] $*"; }

# 0/6 (cycle260 tester 후속) — 2단계(http→https 301) 가 이미 켜져 있으면 재실행을 거부한다.
# 이 스크립트의 사후 검증은 `http://127.0.0.1/api/health` → **401** 을 기대한다(무자격 Basic
# Auth 거부). 2단계가 켜지면 80 은 자격과 무관하게 **301** 을 낸다(rewrite 단계가 access
# 단계보다 앞 — cycle260 실 nginx 실측) — 즉 재발급 목적으로 2단계 뒤에 이 스크립트를 다시
# 돌리면 certbot 발급까지 성공하고도 "80 이 401 이 아니다" 로 `rollback_to_http_only` 가
# **TLS 전체를 원복**하고 `.tls_stage2` 만 고아로 남는다(다음 자동 배포가 `tls2=ignored_no_tls`
# 로 조용히 무시 — 사이트는 평문 80 으로 회귀한다). certbot/docker 호출 전에 막는다.
STAGE2_MARKER=".tls_stage2"
if [ -f "${STAGE2_MARKER}" ]; then
    log "실패: ${STAGE2_MARKER}(2단계 http→https 301) 가 이미 켜져 있다 — 이 스크립트를"
    log "  재실행하면 사후 검증(80→401 기대)이 실제로는 301 이라 발급에 성공해도 TLS 전체를"
    log "  원복한다. 인증서 갱신만 필요하면: sudo certbot renew"
    log "  이 스크립트를 다시 쓰려면 먼저 2단계를 꺼라: bash tools/ops/tls_stage2_enable.sh disable"
    exit 1
fi

# 호스트 webroot — nginx `root /var/www/certbot`(컨테이너) 과 짝인 호스트 경로. certbot 은
# 호스트에서 돌므로 **호스트 경로**를 준다. 절대경로로 고정한다 — renewal conf 에 영속되는
# 값이라 상대경로가 남으면 timer(cwd `/`)의 갱신이 webroot 를 못 찾는다.
WEBROOT="${REPO_DIR}/certbot-www"

# 갱신 reload 훅 — certbot 이 root 로 실행한다. cwd 가 `/` 이고 PATH 가 짧을 수 있으므로
# docker 절대경로 + `--project-directory` + 절대경로 `-f` 둘 + `exec -T`(TTY 없음) 로 적는다.
DOCKER_BIN="$(command -v docker)"
RELOAD_HOOK="${DOCKER_BIN} compose --project-directory ${REPO_DIR} -f ${REPO_DIR}/docker-compose.prod.yml -f ${REPO_DIR}/docker-compose.tls.yml exec -T frontend nginx -s reload"

# 1/6 — DNS 사전 점검. certbot 호출보다 반드시 앞이어야 한다(실패 rate limit 소모 방지).
log "1/6 DNS 점검: dig +short auto.dkstock.cloud"
RESOLVED_IP="$(dig +short auto.dkstock.cloud | tail -n1)"
if [ "${RESOLVED_IP}" != "3.38.228.74" ]; then
    log "실패: A 레코드(${RESOLVED_IP:-없음})가 3.38.228.74 와 다르다."
    log "  도메인 관리 화면에서 auto.dkstock.cloud → 3.38.228.74 등록 후 재실행하라."
    log "  (certbot 은 호출하지 않았다 — rate limit 소모 없음)"
    exit 1
fi

# 2/6 — ACME 챌린지 경로가 이미 무자격 200 인지 확인(HTTP 템플릿의 ACME location 배포 여부).
log "2/6 ACME 챌린지 경로 점검"
# `./certbot-www` 는 prod compose 의 bind mount 가 root:root 755 로 먼저 만들어 둔다 — ubuntu 의
# `mkdir -p` 는 EACCES 다. `sudo install -d` 가 빠진 구성요소를 만들고 최종 디렉터리를 ubuntu
# 소유(755)로 맞춘다(이미 root 소유여도 chown 된다 — ubuntu:24.04 coreutils 실측). 컨테이너의
# nginx(uid 101)는 755/644 로 읽는다.
sudo install -d -m 755 -o "$(id -u)" -g "$(id -g)" "${WEBROOT}/.well-known/acme-challenge"
echo cycle255-probe > "${WEBROOT}/.well-known/acme-challenge/probe"
PROBE_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://auto.dkstock.cloud/.well-known/acme-challenge/probe || true)"
rm -f "${WEBROOT}/.well-known/acme-challenge/probe"
if [ "${PROBE_CODE}" != "200" ]; then
    log "실패: 챌린지 경로가 200 이 아니다(응답=${PROBE_CODE})."
    log "  frontend/nginx.conf.template 의 ACME location 이 배포됐는지 먼저 확인하라."
    log "  (certbot 은 호출하지 않았다)"
    exit 1
fi

# 3/6 — 발급. --webroot 는 80 을 nginx 와 공유한다. --standalone 은 80 을 점유해 충돌한다.
#        --deploy-hook 은 renewal conf 에 영속된다(갱신 경로 어느 쪽이든 nginx reload).
log "3/6 인증서 발급 시작(webroot 방식, reload 훅 동반 등록)"
sudo certbot certonly --webroot -w "${WEBROOT}" -d auto.dkstock.cloud --agree-tos -m "${LE_EMAIL}" -n --deploy-hook "${RELOAD_HOOK}"

# 4/6 — 산출물 확인 뒤에만 마커 생성. 순서가 뒤집히면 인증서 없는 443 기동 = frontend 전면 실패.
log "4/6 발급 산출물 확인"
FULLCHAIN="${LE_LIVE_DIR:-/etc/letsencrypt/live/auto.dkstock.cloud}/fullchain.pem"
# `/etc/letsencrypt/live` 는 root 700 이라 ubuntu 의 `[ -f ]` 는 EACCES 로 거짓 "없음" 을 낸다
# (2026-09-05 첫 실행 실측 — 인증서는 발급됐는데 4/6 에서 멈춤). 존재 확인은 sudo 로 한다.
if ! sudo test -f "${FULLCHAIN}"; then
    log "실패: certbot 이 성공했다고 종료했지만 발급 산출물이 없다:"
    log "  ${FULLCHAIN}"
    exit 1
fi
touch .tls_enabled
log "마커 생성: .tls_enabled"

# 5/6 — frontend 만 재기동(backend 무접촉 — cycle232 D6, 장중에도 전환 가능해야 한다) + 사후 검증.
log "5/6 frontend 전환(오버레이 up, backend 무접촉)"

# 원복 = 마커 삭제 + **base 단독** up(오버레이를 붙이면 원복이 아니다). "80 은 살아있다" 는
# 이 up 이 성공한 뒤에만 참이다 — 오버레이 up 이 non-zero 로 끝난 컨테이너는 created 상태로
# 80 도 000 이고, base 단독 up 이 Recreate 해야 돌아온다.
rollback_to_http_only() {
    rm -f .tls_enabled
    log "원복 실행: 마커 삭제 → base 단독 구성으로 frontend 재기동(오버레이 없음)"
    if docker compose -f docker-compose.prod.yml up -d --no-deps frontend; then
        log "원복 완료 — 80 은 다시 살아있다. 인증서는 /etc/letsencrypt 에 남아 재실행 시 재발급하지 않는다."
    else
        log "원복 up 도 실패 — 80 이 내려가 있을 수 있다. 수동 조치(그대로 실행):"
        log "  docker compose -f docker-compose.prod.yml up -d --no-deps frontend"
    fi
}

if ! docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml up -d --no-deps frontend; then
    log "실패: 오버레이 up 이 non-zero — 443 선점(확인: sudo ss -ltnp | grep ':443') 등."
    rollback_to_http_only
    exit 1
fi

# 사후 검증 — `up -d` 의 exit 0 은 기동 성공이 아니다(크래시 루프도 0). 실제 응답으로 판정한다:
# 80 → 401(Basic, 무자격) ∧ 443 → 401 ∧ frontend State=running, 같은 이터레이션에서 셋 다.
log "    사후 검증(≤10초 폴링): 80 → 401 ∧ 443 → 401 ∧ frontend State=running"
HEALTH_OK=0
HTTP_CODE=""
HTTPS_CODE=""
FE_STATE=""
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/api/health || true)"
    HTTPS_CODE="$(curl -sk -o /dev/null -w '%{http_code}' --resolve auto.dkstock.cloud:443:127.0.0.1 https://auto.dkstock.cloud/api/health || true)"
    # compose v2.21+/v5 `ps --format json` = NDJSON, `"State":"running"|"restarting"|"exited"|"created"`.
    FE_STATE="$(docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml ps --format json frontend 2>/dev/null | grep -o -m1 '"State":"[a-z]*"' || true)"
    if [ "${HTTP_CODE}" = "401" ] && [ "${HTTPS_CODE}" = "401" ] && [ "${FE_STATE}" = '"State":"running"' ]; then
        HEALTH_OK=1
        break
    fi
    sleep 1
done
if [ "${HEALTH_OK}" != "1" ]; then
    log "실패: 사후 검증 미통과 — http=${HTTP_CODE:-none} https=${HTTPS_CODE:-none} state=${FE_STATE:-none} (기대 401 / 401 / \"State\":\"running\")."
    log "  진단: docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml logs --tail=50 frontend"
    rollback_to_http_only
    exit 1
fi
log "    사후 검증 통과: http=401 https=401 state=running"

# 6/6 — 갱신 경로 검증. 실패해도 전환은 되돌리지 않는다(인증서 90일 유효) — WARNING 으로 남긴다.
log "6/6 갱신 경로 검증(reload 훅 1회 실행 + certbot renew --dry-run)"
RENEW_WARN=0
if bash -c "${RELOAD_HOOK}"; then
    log "    reload 훅 실행 성공: ${RELOAD_HOOK}"
else
    RENEW_WARN=1
    log "WARNING: reload 훅 명령이 실패했다 — 갱신 시 nginx 가 새 인증서를 물지 못한다(90일 내 조치)."
    log "  훅: ${RELOAD_HOOK}"
fi
if sudo certbot renew --dry-run; then
    log "    certbot renew --dry-run 성공(갱신 챌린지 경로 정상)"
else
    RENEW_WARN=1
    log "WARNING: certbot renew --dry-run 실패 — 갱신 경로 결함. 전환은 유지한다(인증서 90일 유효)."
    log "  원인 수정 후 재검증: sudo certbot renew --dry-run"
fi

if [ "${RENEW_WARN}" = "1" ]; then
    log "완료(전환 성공 — 단 갱신 경로 WARNING 있음, 위 메시지를 90일 안에 처리하라)."
else
    log "완료."
fi
log "확인:"
log "  curl -sk -o /dev/null -w '%{http_code}' https://auto.dkstock.cloud/api/health   # 401 기대(무자격)"
log "  curl -sk -u <user>:<pass> -o /dev/null -w '%{http_code}' https://auto.dkstock.cloud/api/health   # 200 기대"
log "  echo | openssl s_client -connect auto.dkstock.cloud:443 -servername auto.dkstock.cloud 2>/dev/null | openssl x509 -noout -issuer"
log ""
log "갱신: reload 훅은 renewal conf 에 영속됐다(별도 crontab 없음) — 확인:"
log "  sudo grep renew_hook /etc/letsencrypt/renewal/auto.dkstock.cloud.conf"
log "  systemctl list-timers | grep certbot"
