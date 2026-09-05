#!/usr/bin/env bash
# cycle260 (2026-09-05, tester 후속 시정 포함) — nginx Basic Auth 자격(htpasswd) 회전.
#
# cycle243 이래 Basic 자격은 평문 HTTP 로 오갔다(TLS 준비 전). 2단계(http→https 301) 전환
# 뒤 EC2 에서 운영자가 1회 수동으로 실행해 그동안 평문으로 오갔을 수 있는 자격을 바꾼다.
# 게이트는 없다 — 언제 돌려도 안전한 절차다.
#
# ■ 사용자 목록은 **파일에서 읽는다**(하드코딩 금지). 운영 `secrets/.htpasswd` 에는
#   `ubuntu`(대시보드)·`reporter`(20:20 자동 리포트) 두 계정이 있고, 하나라도 하드코딩
#   목록에서 빠지면 그 계정의 다음 로그인/자동 리포트가 조용히 401 이 된다(예: 리포터를
#   빠뜨리면 다음 날 리포트가 통째로 사라진다). `htpasswd` 명령(apache2-utils)은 EC2 에
#   설치돼 있지 않다 — 해시는 `openssl passwd -apr1 -stdin` 로만 만든다(비밀은 stdin 으로, argv 금지).
#
# ■ 검증 대상 경로 — **`/`**(SPA 정적 파일), `/api/health` 가 아니다. `/api/health` 는
#   백엔드에 그런 라우트가 없다(백엔드는 `/health` 만 등록하고, `ApiAuthMiddleware.EXEMPT_PATHS`
#   가 예외로 두는 것도 `/health` 뿐 — `/api/health` 는 nginx 인증을 통과해도 FastAPI 가
#   404 를 낸다). 즉 이 경로로는 인증이 통과해도 **200 이 나올 수 없다** — 회전이 TLS 단계와
#   무관하게 항상 실패해 백업을 복원하는 구조적 결함이었다(tester 실측). `/` 는 nginx 가
#   백엔드 없이 직접 서빙하는 정적 파일이라 인증 통과 여부만 순수하게 잰다.
#
# ■ 검증 스킴 — `.tls_enabled`(cycle255, 443 오버레이) 가 있으면 **https**(도메인 SNI,
#   `--resolve …:443:127.0.0.1` 로 루프백 고정 — 외부 DNS 무의존)로, 없으면 종전대로
#   http 루프백으로 검증한다. 2단계(cycle260, http→https 301)가 함께 켜진 상태에서 80 의
#   `if + return 301` 은 **rewrite 단계**라 access 단계(auth_basic)보다 먼저 끝나 자격과
#   무관하게 항상 301 이 난다(tester 실 nginx 실측) — http 로 검증하면 새 자격도 틀린 자격도
#   똑같이 301 이라 이 스크립트가 자기 사용 시점("2단계 전환 뒤")에 구조적으로 성공할 수
#   없었다. `.tls_enabled` 단계부터 https 로 전환해두면 이후 2단계가 켜져도 그대로 통한다.
#
# ■ 순서 — 반쪽 상태(해시는 새로 바뀌었는데 아무도 그 비밀번호를 모르는 상태)를 남기지
#   않는다:
#   1) `secrets/.htpasswd` 존재 확인 — 없으면 아무것도 만들지 않고 멈춘다(빈 목록으로
#      진행하면 사용자 0명짜리 파일을 써서 모든 자격을 무효화한다).
#   2) 사용자별 새 비밀번호 생성 — `openssl rand -base64 18` 뒤 `+/=` 제거(URL 안전 문자만
#      남긴다. 자동 리포트 루틴이 자격을 URL(`https://user:pass@host/…`)에 넣는데 `@`·`/`·
#      `+` 가 있으면 파싱이 깨진다는 것이 실제로 보고된 문제다). 해시는
#      `openssl passwd -apr1 -stdin`(비밀번호를 **argv 로 넘기지 않는다** — argv 는 같은
#      호스트의 다른 사용자에게 `ps` 로 보이고 셸 히스토리에도 남는다).
#   3) 기존 파일을 `secrets/.htpasswd.bak-<타임스탬프>`(644) 로 백업.
#   4) 새 htpasswd 를 **임시파일 + `mv`** 로 원자 교체(직접 `>` truncate 금지 — 도중에
#      죽으면 그 순간부터 아무도 로그인할 수 없다). 권한은 **644**(600 이면 nginx worker
#      uid 101 이 못 읽어 자격 요청이 전부 500 — cycle243 §10.1 F2 실측, `.token_cache`
#      root 소유 사고와 동일 계열).
#   5) 새 자격을 `secrets/.rotated-<타임스탬프>`(**600**, 운영자만 ssh 로 읽는다 — 화면에
#      찍지 않는다)에 기록.
#   6) 검증 — **두 축**: 새 자격으로 `/` 이 200 **그리고** 의도적으로 틀린 자격으로는 401.
#      새 자격만 확인하면 "auth_basic 이 통째로 빠져 아무 자격이나 200" 인 구성을 성공으로
#      본다(옛 자격은 해시만 남아 스크립트가 평문을 몰라 재현할 수 없다 — 그래서 '옛 자격
#      거부' 대신 '틀린 자격 거부'로 인증이 여전히 강제되는지 잰다). 파일은 요청 시점에
#      열리므로 nginx reload 는 필요 없다.
#   7) 검증 실패 → 백업으로 원본 복원 + 실패 종료. 이때 `.rotated-*` 파일도 `.FAILED` 로
#      개명한다(600 유지) — 그 안의 비밀번호는 **적용되지 않았다**(htpasswd 는 원본으로
#      되돌아갔다). 개명하지 않으면 운영자가 실패 로그를 놓치고 그 파일의 비밀번호를 그대로
#      클라우드 환경에 넣어 다음 자동 리포트가 조용히 401 이 될 수 있다.
#
# ■ 사용 절차(성공 뒤) — ① 이 스크립트 실행 ② `secrets/.rotated-*` 를 읽어 클라우드 환경의
#   `REPORTER_BASIC_PASSWORD`(리포터 계정) 갱신 + 브라우저 재로그인(다른 계정) ③ 다음
#   자동 리포트 실행에서 200 확인 ④ `.rotated-*` 삭제(평문 비밀번호가 파일로 남는 유일한
#   시간창을 최소화한다).
#
# ⚠️ 비밀값을 이 파일에 리터럴로 두지 않는다(git 커밋 대상). 생성된 비밀번호는 화면에
# 찍지 않고 600 파일로만 남긴다.
set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "${REPO_DIR}"

HTPASSWD="secrets/.htpasswd"
TS="$(date +%Y%m%d%H%M%S)"
BACKUP="secrets/.htpasswd.bak-${TS}"
ROTATED="secrets/.rotated-${TS}"
TMP_HT="secrets/.htpasswd.new-${TS}"
TMP_ROT="secrets/.rotated.new-${TS}"
DOMAIN="auto.dkstock.cloud"
TLS_MARKER=".tls_enabled"

# 검증 대상 — `.tls_enabled` 가 있으면 https(도메인 SNI, 루프백 고정), 없으면 http 루프백.
# `/` 로 고정한다(`/api/health` 는 백엔드에 라우트가 없어 인증 통과와 무관하게 200 이 될 수
# 없다 — tester 실측).
CURL_EXTRA=()
if [ -f "${TLS_MARKER}" ]; then
    HEALTH_URL="https://${DOMAIN}/"
    CURL_EXTRA=(-k --resolve "${DOMAIN}:443:127.0.0.1")
else
    HEALTH_URL="http://127.0.0.1/"
fi

log() { echo "[rotate_basic_auth] $*"; }

# 1 — 자격 파일 부재는 멈춘다(빈 목록 진행 = 전원 로그인 불가).
if [ ! -f "${HTPASSWD}" ]; then
    log "실패: ${HTPASSWD} 가 없다 — 이 호스트에는 회전할 자격 파일이 없다."
    exit 1
fi
USERS="$(cut -d: -f1 "${HTPASSWD}" | sed '/^[[:space:]]*$/d')"
if [ -z "${USERS}" ]; then
    log "실패: ${HTPASSWD} 에 사용자가 없다."
    exit 1
fi

cp "${HTPASSWD}" "${BACKUP}"
chmod 644 "${BACKUP}"
: > "${TMP_HT}"
chmod 644 "${TMP_HT}"
: > "${TMP_ROT}"
chmod 600 "${TMP_ROT}"

# 2 — 사용자별 새 비밀번호/해시 생성. 파일에서 읽은 순서를 그대로 보존한다.
CREDS=()
while IFS= read -r u; do
    [ -n "${u}" ] || continue
    NEW_PW="$(openssl rand -base64 18 | tr -d '+/=')"
    NEW_HASH="$(printf '%s' "${NEW_PW}" | openssl passwd -apr1 -stdin)"
    printf '%s:%s\n' "${u}" "${NEW_HASH}" >> "${TMP_HT}"
    printf '%s:%s\n' "${u}" "${NEW_PW}" >> "${TMP_ROT}"
    CREDS+=("${u}:${NEW_PW}")
done <<< "${USERS}"

# 4/5 — 원자 교체(mv) + 권한. htpasswd 644(worker uid 101 이 읽어야 한다) / rotated 600.
mv "${TMP_HT}" "${HTPASSWD}"
chmod 644 "${HTPASSWD}"
mv "${TMP_ROT}" "${ROTATED}"
chmod 600 "${ROTATED}"
log "회전 파일 작성 완료(백업=${BACKUP}, 새 자격=${ROTATED} 600) — reload 불필요"

# 6 — 검증 두 축: 새 자격 200 + 틀린 자격 401. `${cred%%:*}` 로 사용자명만 로그에 남긴다
# (비밀번호는 여기서도 화면에 찍지 않는다).
FAILED=0
for cred in "${CREDS[@]}"; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "${CURL_EXTRA[@]:-}" -u "${cred}" "${HEALTH_URL}" || true)"
    if [ "${code}" != "200" ]; then
        FAILED=1
        log "실패: 새 자격 검증 미통과(user=${cred%%:*} code=${code})"
    fi
done
BAD="$(curl -s -o /dev/null -w '%{http_code}' "${CURL_EXTRA[@]:-}" -u "rotate-canary-$$:wrong-on-purpose-$$" "${HEALTH_URL}" || true)"
if [ "${BAD}" != "401" ]; then
    FAILED=1
    log "실패: 의도적으로 틀린 자격이 401 이 아니다(code=${BAD}) — 인증이 강제되지 않는 구성이다."
fi

# 7 — 검증 실패 → 백업 복원(반쪽 상태를 남기지 않는다) + rotated 파일을 무효로 표시.
if [ "${FAILED}" != "0" ]; then
    cp "${BACKUP}" "${HTPASSWD}"
    chmod 644 "${HTPASSWD}"
    mv "${ROTATED}" "${ROTATED}.FAILED"
    chmod 600 "${ROTATED}.FAILED"
    log "백업 복원 완료: ${BACKUP} → ${HTPASSWD}"
    log "경고: ${ROTATED}.FAILED 의 비밀번호는 적용되지 않았다(htpasswd 는 원본으로 복원됨) — 사용 금지, 삭제할 것."
    exit 1
fi

log "완료. 다음 절차: ${ROTATED} 를 읽어 클라우드 환경 비밀번호 갱신 → 재로그인 → 확인 후 ${ROTATED} 삭제."
