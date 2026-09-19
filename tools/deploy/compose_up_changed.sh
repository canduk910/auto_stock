#!/usr/bin/env bash
# cycle248 (2026-09-04) — 변경된 입력에 따라 필요한 서비스만 올리는 선택적 배포.
#
# ■ 왜 필요한가
#   Compose v5.1 의 `up --build` 는 이미지 ID 가 동일해도 `build:` 가 있는 서비스를 전부
#   재생성한다(빌드가 이미지를 재태그해 LastTagTime 이 컨테이너보다 새로워진다 — EC2 v5.1.3·
#   로컬 v5.1.1 재현). 그래서 프론트·문서만 바꾼 push 도 backend 를 ~100초 tick blind 로
#   몰았다(13db0d9 · b985938 실측). 이 스크립트는 "무엇이 바뀌었는가"를 git 으로 판정해
#   backend 입력이 안 바뀐 배포에서 backend 컨테이너를 건드리지 않는다.
#
# ■ 판정 (마지막 **성공** 배포 SHA 마커 ↔ HEAD 의 누적 diff)
#   full          — backend 이미지·구성 입력 또는 배포 로직 자체가 바뀜 → `up --build -d --remove-orphans`
#                   (현행 동일: 전 서비스 재생성)
#   frontend      — frontend/ 만 바뀜 → `up --build -d --no-deps frontend` (backend 무접촉 — 실측.
#                   의도적으로 정지된 backend 도 기동하지 않는다 — 필요하면 수동 `up -d backend`)
#   macro         — macro/ 만 바뀜(cycle303) → `up --build -d --no-deps macro` (backend·frontend 무접촉)
#   frontend+macro — frontend/ 와 macro/ 만 바뀜(cycle303) → `up --build -d --no-deps frontend macro`
#   none          — 어느 입력도 아님(docs/tests/_workspace/…) 또는 마커==HEAD(이미 성공 배포된 SHA 의
#                   재실행) → `up -d --remove-orphans` (빌드 없음 = Running, 재생성 0 — 실측)
#   판정 불가(마커 없음 · 마커 SHA 미지 · diff 실패) → **full** (fail-safe = 현행 동작)
#
# ■ 분류 규칙의 근거 = 이미지 입력의 **구성적** 정의
#   backend  : 루트 Dockerfile 의 COPY 소스는 `requirements.txt` · `src/` 뿐(AST 가드 D-8 이 고정)
#              + `Dockerfile` + `docker-compose.prod.yml`(config hash) + `.dockerignore`
#              + 배포 로직(`.github/workflows/deploy.yml` · `tools/deploy/`) — 로직이 바뀐 배포는
#              한 번 보수적으로 전체를 돈다.
#   frontend : `frontend/` 전체(frontend/Dockerfile 이 `COPY . .`)
#   macro    : `macro/` 전체(cycle303 — 독립 이미지, 빌드 컨텍스트 `./macro`. `macro/Dockerfile`
#              이 `COPY macro_lite/ data/ main.py` 이므로 그 밖의 리포 파일은 이 이미지에
#              실리지 않는다)
#   `.env` 은 git 밖이라 여기서 못 본다 — `.env` 를 손댄 운영자는 스스로 재시작을 안다(cycle243 Phase 2 규약).
#   ⚠️ 오분류의 실패 방향은 비대칭이다: backend 변경을 none 으로 놓치면 **stale backend 가 조용히
#   돈다**(fail-dangerous). 그래서 backend 목록은 "명시적 입력의 합집합"이 아니라 위 구성적 정의를
#   그대로 옮긴 것이고, 가드 `tests/unit/ast/test_cycle248_deploy_pipeline.py` 가 Dockerfile COPY
#   소스 ↔ 이 정규식의 정합을 강제한다.
#
# ■ cycle303 — 서비스 목록 일반화 (왜 frontend 전용 모드를 없애지 않고 넓혔는가)
#   macro 서비스가 추가되며 "frontend 만/backend 나머지 전부" 2분류로는 부족해졌다.
#   frontend·macro 두 축을 각자 판정(FRONTEND_RE/MACRO_RE)한 뒤 SERVICES 배열에 모아
#   **하나의 `--no-deps` 라인을 공유**하는 형태로 일반화했다 — backend 축(BACKEND_RE)과
#   그 우선순위(backend 히트 → 무조건 full)는 cycle248 과 완전히 동일하게 **보존**한다.
#   SERVICES 는 FRONTEND_HITS/MACRO_HITS 로만 채워지므로 backend 가 이 배열에 들어갈
#   길이 구조적으로 없다(정합 가드 = `tests/unit/ast/test_cycle248_deploy_pipeline.py`
#   G-248-5, 행위 가드 = `tests/unit/deploy/test_cycle303_macro_deploy_classification.py`).
#
# ■ 환경변수
#   DEPLOY_MARKER      마커 파일 경로 (기본 .deployed_sha — .gitignore 등재). `<마커>.attempt` 는 시도 마커.
#   DEPLOY_DRY_RUN=1   docker 를 호출하지 않고 명령만 출력, 마커·시도 마커도 쓰지 않는다 (true/yes/on 동치,
#                      그 외 값은 exit 2 — 오타가 실배포로 이어지면 안 된다)
#   COMPOSE_FILE_PATH  compose 파일 (기본 docker-compose.prod.yml)
#
# ■ cycle255 — TLS(443) 오버레이 마커
#   호스트 파일 `.tls_enabled`(git 밖, `tools/ops/tls_enable.sh` 가 인증서 발급 **성공 뒤**에만
#   만든다)가 있으면 모든 compose 호출에 `-f docker-compose.tls.yml` 를 base 파일 **뒤**에
#   덧붙인다(compose 는 뒤에 오는 파일이 이긴다 — base 위에 얹는 것이 의도다). 마커가 없으면
#   이 파일이 리포에 있어도 명령은 cycle248 과 byte 동일하다(인증서 없이 443 을 열면 nginx 가
#   기동 실패해 같은 컨테이너인 80 까지 죽는다). **마커는 모드 판정(full/frontend/none)에
#   개입하지 않는다** — 개입하면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어 cycle248
#   이 없앤 비용이 부활한다. `docker-compose.tls.yml` 자체의 변경은 다른 compose 파일과 동일하게
#   backend 축(full)으로 분류한다(BACKEND_RE, fail-safe).
#
# ■ 운영 규칙 — 마커는 "이 git SHA 가 성공 배포됐다" 만 뜻하고 실행 중 이미지와 대조하지 않는다.
#   EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build`
#   를 했으면 `rm .deployed_sha` 로 다음 자동 배포를 full 로 만든다. 수동 배포는 이 스크립트로 한다.
#   `.env` 편집 후 수동 `up -d` 는 이미지가 그대로라 마커를 건드리지 않아도 된다.
#
# ■ cycle260 — TLS 2단계(http→https 301 · HSTS) 오버레이 마커, 1단계에 **종속**
#   호스트 파일 `.tls_stage2`(git 밖, `tools/ops/tls_stage2_enable.sh` 가 사후 검증까지 통과한
#   뒤에만 만든다)가 있고 **`.tls_enabled` 도 함께** 있을 때만 모든 compose 호출에
#   `-f docker-compose.tls2.yml` 를 1단계 오버레이 **뒤**에 덧붙인다(`-f prod -f tls -f tls2` —
#   compose 는 뒤에 오는 파일이 이긴다). `.tls_stage2` 만 있고 `.tls_enabled` 가 없으면 443 이
#   없는 상태에서 80 을 https 로 301 하는 꼴이라 사이트가 통째로 도달 불가가 된다 — 그래서
#   조용히 무시하고(1단계만 켠 것과 byte 동일 명령) 로그에 `tls2=ignored_no_tls` 로 사유를
#   남긴다(마커는 git 밖이라 리포만 봐서는 그날 무엇이 켜졌는지 알 수 없다). 마커는 이번에도
#   **모드 판정(full/frontend/none)에 개입하지 않는다** — 개입하면 2단계를 켠 날부터 모든
#   배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다. `docker-compose.tls2.yml`
#   자체의 변경은 다른 compose 파일과 동일하게 backend 축(full)으로 분류한다(BACKEND_RE,
#   fail-safe) — `tools/ops/tls_stage2/*.conf` 스니펫은 볼륨 마운트라 이미지 재빌드가
#   필요 없으므로 여기 포함하지 않는다(frontend 재기동만으로 반영).
set -euo pipefail
# 마커·compose 경로는 저장소 루트 기준이다 — 하위 디렉터리에서 손으로 실행해도 같은 마커를 본다.
cd "$(git rev-parse --show-toplevel)"

# 🔴 cycle305 — **이미지는 한 번에 하나씩 굽는다.** 2026-09-18 19:17 운영 사고:
# cycle303 이 macro 서비스를 추가하자 `up --build` 가 frontend(npm build)와 macro
# (pandas·numpy·yfinance 설치)를 **동시에** 빌드했고, t4g.small **2GB** 박스의 메모리가
# 말라 sshd·nginx 까지 굶었다 — 배포는 SSH 10분 타임아웃으로 죽고(`Run Command Timeout`)
# 박스는 그 뒤 15분간 SSH·HTTPS 모두 무응답이었다(인스턴스 상태검사는 내내 `ok` 였다.
# OS 는 살아 있고 사용자 프로세스만 굶은 것이다). 복구는 EC2 재부팅이었고 그 사이
# 보유 11종목이 손절 감시를 받지 못했다.
#   - `COMPOSE_PARALLEL_LIMIT=1` = compose 의 컨테이너/빌드 작업 동시성 상한
#   - `COMPOSE_BAKE=0` = bake 경로(여러 타깃을 한 번에 굽는다)를 끄고 서비스별 순차 빌드
# 서비스가 둘뿐일 때는 무해했다 — **세 번째 이미지가 생긴 순간 임계를 넘었다.**
# 넷째 이미지(예: `llm_worker`)를 추가하기 전에 이 값을 다시 확인하라.
export COMPOSE_PARALLEL_LIMIT=1
export COMPOSE_BAKE=0

COMPOSE_FILE="${COMPOSE_FILE_PATH:-docker-compose.prod.yml}"
MARKER="${DEPLOY_MARKER:-.deployed_sha}"
# 시도 마커 — compose 호출 **직전**에 쓰고 성공 마커를 쓴 뒤 지운다. 남아 있으면 직전 배포가 중간에
# 죽은 것이다. compose 는 실패해도 이미지 태그·컨테이너를 **부분적으로** 전진시키므로(실측: frontend
# 빌드 실패 + backend 태그는 새 이미지로), 그 뒤 revert 로 HEAD 트리가 마커 트리와 같아지면 diff 는
# 0 인데 `up -d` 가 backend 를 main 에 없는 이미지로 교체한다 — 그래서 시도 마커가 있으면 무조건 full.
ATTEMPT="${MARKER}.attempt"
case "$(printf '%s' "${DEPLOY_DRY_RUN:-0}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)      DRY_RUN=1 ;;
    0|false|no|off|"")  DRY_RUN=0 ;;
    *) echo "[deploy] invalid DEPLOY_DRY_RUN='${DEPLOY_DRY_RUN}' — 1/0 (true/false) 만 허용. 오타가 실배포가 되면 안 된다." >&2; exit 2 ;;
esac

# 정규식은 ERE. 앵커(^ … / 또는 $)가 계약이다 — `srcs/`·`frontendx/`·`requirements-dev.txt` 가 새면 안 된다.
# cycle255 — docker-compose.tls.yml 추가(다른 compose 파일과 동일하게 backend 축, fail-safe).
BACKEND_RE='^(src/|requirements\.txt$|Dockerfile$|docker-compose\.prod\.yml$|docker-compose\.tls\.yml$|docker-compose\.tls2\.yml$|\.dockerignore$|\.github/workflows/deploy\.yml$|tools/deploy/)'
# cycle260 tester 후속(F-8) — `tools/ops/tls_stage2/*.conf` 스니펫은 `docker-compose.tls2.yml`
# 이 볼륨으로 마운트한다(이미지 재빌드 불필요, 반영에 필요한 것은 frontend **재기동**뿐).
# 이 디렉터리를 어느 축에도 안 넣으면 `none` 모드(`up -d`, 재생성 0)가 되어 스니펫을 고쳐도
# 실행 중인 nginx 는 옛 설정을 계속 문다(nginx 는 기동·reload 시점에만 설정을 읽는다) — 스니펫
# 변경이 frontend 모드(`--no-deps frontend`, cycle248 실측대로 이미지 동일해도 컨테이너
# 재생성)를 타도록 frontend 축에 추가한다. backend 이미지 입력이 아니므로 BACKEND_RE 에는
# 넣지 않는다(넣으면 헤더 한 글자 고칠 때마다 backend 가 재시작돼 cycle232 D6 이 발동한다).
FRONTEND_RE='^(frontend/|tools/ops/tls_stage2/)'
# cycle303 — macro_lite 이식 1단계. `macro/` 는 독립 이미지(빌드 컨텍스트 `./macro`)라
# backend 이미지 입력이 아니다(BACKEND_RE 에 넣지 않는다 — 넣으면 매크로 화면 문구
# 하나 고칠 때마다 매매 backend 가 재시작돼 cycle232 D6 이 발동한다). FRONTEND_RE 와
# 합치지 않고 별도 축으로 두는 이유는 "macro 만 바뀜" 과 "frontend 만 바뀜" 을
# 구분해 `--no-deps` 대상 서비스 목록을 정확히 고르기 위해서다(아래 서비스 목록
# 일반화 참조).
MACRO_RE='^macro/'

# cycle322 (사용자 결정 D2) — backend 축에 걸리지만 **이미지에는 안 들어가는** 경로.
# `src/**` 는 확장자 무관 이미지 입력이라 `src/db/CLAUDE.md` 한 줄이 full 을 불러 매매
# 백엔드를 재생성했다(2026-09-19 실측 `4b862d9`: 그 커밋이 바꾼 건 테스트 1개뿐이었다).
# 평일이면 cycle232 D6 위반이고, 실질 비용은 `/sync-docs` 가 필수인 문서 동기화가
# 장외 창에만 묶이는 것이다.
# 🔴 정규식만 좁히지 않았다 — 그 파일들이 **실제로 이미지 안에 있었기** 때문이다.
# `.dockerignore` 의 `**/*.md` 가 먼저 빼고, 그 다음에 여기서 분류를 맞춘다. 한쪽만 고치면
# "안 바뀌었다" 고 말하면서 이미지가 바뀌는, 지금보다 나쁜 상태가 된다.
# 두 파일이 갈라지지 않게 `tests/unit/ast/test_cycle322_image_excluded_paths.py` 가 묶는다.
# ⚠️ `src/` 안 `.md` 로만 한정한다 — `.*\.md$` 처럼 넓히면 `tools/deploy/` 축이 흔들린다.
IMAGE_EXCLUDED_RE='^src/.*\.md$'

# cycle255 — TLS 오버레이 마커. **모드 판정에는 관여하지 않는다** — 여기서 읽어 두는 것은
# compose 호출에 붙일 `-f` 목록뿐이다. 마커는 존재만 본다(내용 파싱 금지 — `touch` 로 만든
# 빈 파일도 켜짐이다).
TLS_MARKER=".tls_enabled"
TLS_COMPOSE="docker-compose.tls.yml"
TLS_STATE="off"
COMPOSE_FILE_ARGS=(-f "$COMPOSE_FILE")
if [ -f "$TLS_MARKER" ]; then
    TLS_STATE="on"
    COMPOSE_FILE_ARGS+=(-f "$TLS_COMPOSE")
fi

# cycle260 — 2단계(리다이렉트·HSTS) 스니펫 오버레이 마커. 1단계에 **종속**이다(443 없이
# 80 을 https 로 301 하면 사이트가 도달 불가가 된다).
TLS2_MARKER=".tls_stage2"
TLS2_COMPOSE="docker-compose.tls2.yml"
TLS2_STATE="off"
if [ -f "$TLS2_MARKER" ]; then
    if [ "$TLS_STATE" = "on" ]; then
        TLS2_STATE="on"
        COMPOSE_FILE_ARGS+=(-f "$TLS2_COMPOSE")
    else
        TLS2_STATE="ignored_no_tls"
    fi
fi

log() { echo "[deploy] $*"; }

run() {
    if [ "$DRY_RUN" = "1" ]; then
        echo "[deploy][dry-run] $*"
    else
        "$@"
    fi
}

HEAD_SHA="$(git rev-parse HEAD)"
PREV_SHA=""
if [ -f "$MARKER" ]; then
    PREV_SHA="$(tr -d '[:space:]' < "$MARKER" || true)"
fi

MODE=""
REASON=""
CHANGED=""

if [ -z "$PREV_SHA" ]; then
    MODE="full"; REASON="marker_missing"
elif [ -f "$ATTEMPT" ]; then
    MODE="full"; REASON="previous_attempt_failed"
elif ! git cat-file -e "${PREV_SHA}^{commit}" 2>/dev/null; then
    MODE="full"; REASON="marker_unknown_commit"
elif [ "$PREV_SHA" = "$HEAD_SHA" ]; then
    MODE="none"; REASON="already_deployed"
else
    # --no-renames: 이름 변경을 삭제+추가로 펼쳐 원 경로도 잡는다(src 밖으로 옮긴 파일도 backend 변경).
    # -z + tr: 기본 core.quotePath 는 한글·`"`·`\` 경로를 C-quote("src/\355…") 로 감싸 `^src/` 앵커가
    #          빗나간다(실측 → mode=none 오분류). NUL 구분 출력엔 quoting 자체가 없다.
    #          (`-c core.quotePath=false` 는 `"`·`\` 를 여전히 감싼다 — 실측.)
    #          pipefail 이 $( ) 안에서도 전파되므로 git 실패는 그대로 diff_failed → full.
    if ! CHANGED="$(git diff --name-only --no-renames -z "$PREV_SHA" "$HEAD_SHA" 2>/dev/null | tr '\0' '\n')"; then
        MODE="full"; REASON="diff_failed"
    fi
fi

# cycle303 — 서비스 목록 일반화. backend 축(BACKEND_RE)은 cycle248 과 완전히 동일하게
# "하나라도 있으면 full" 이다. backend 가 아닌 나머지는 SERVICES 배열로 모아 하나의
# `--no-deps` 라인을 공유한다(frontend/macro/frontend+macro 3가지 조합).
# ⚠️ `set -e` 아래서 `[ -n "$X" ] && ARR+=(x)` 는 조건이 거짓일 때(= 히트 없음) 그 라인의
# 종료코드가 1 이 되어 스크립트 전체가 죽는다(`&&` 단축평가 실패가 `set -e` 트리거) —
# 그래서 반드시 `if … then … fi` 로 쓴다.
SERVICES=()
if [ -z "$MODE" ]; then
    # cycle322 — backend 축에 걸린 뒤 **이미지에 안 들어가는 경로만** 덜어낸다(`grep -vE`).
    # ERE 에는 부정 전방탐색이 없어 BACKEND_RE 안에 negation 을 넣을 수 없다 — 그래서 2단이다.
    BACKEND_HITS="$(printf '%s\n' "$CHANGED" | grep -E "$BACKEND_RE" | grep -vE "$IMAGE_EXCLUDED_RE" || true)"
    FRONTEND_HITS="$(printf '%s\n' "$CHANGED" | grep -E "$FRONTEND_RE" || true)"
    MACRO_HITS="$(printf '%s\n' "$CHANGED" | grep -E "$MACRO_RE" || true)"
    if [ -n "$BACKEND_HITS" ]; then
        MODE="full"; REASON="backend_inputs_changed"
    else
        if [ -n "$FRONTEND_HITS" ]; then
            SERVICES+=(frontend)
        fi
        if [ -n "$MACRO_HITS" ]; then
            SERVICES+=(macro)
        fi
        case "${#SERVICES[@]}" in
            0)
                MODE="none"; REASON="no_image_inputs_changed"
                ;;
            1)
                MODE="${SERVICES[0]}"; REASON="${SERVICES[0]}_only"
                ;;
            *)
                MODE="frontend+macro"; REASON="frontend_and_macro_only"
                ;;
        esac
    fi
fi

N_CHANGED=0
if [ -n "$CHANGED" ]; then
    N_CHANGED="$(printf '%s\n' "$CHANGED" | grep -c . || true)"
fi
log "mode=${MODE} reason=${REASON} prev=${PREV_SHA:-none} head=${HEAD_SHA} changed=${N_CHANGED} tls=${TLS_STATE} tls2=${TLS2_STATE}"
if [ -n "$CHANGED" ]; then
    # ⚠️ `head` 금지 — pipefail 아래서 head 가 40행 뒤 닫힐 때 printf 가 아직 쓰고 있으면(목록이 파이프
    # 버퍼 64KB 를 넘는 큰 diff) SIGPIPE(141) → 스크립트 통째 중단. sed 는 입력을 끝까지 읽는다(T-16).
    printf '%s\n' "$CHANGED" | sed -n '1,40p' | sed 's/^/[deploy]   changed: /'
    if [ "$N_CHANGED" -gt 40 ]; then log "  … (+$((N_CHANGED - 40)) more)"; fi
fi

if [ "$DRY_RUN" != "1" ]; then
    printf '%s\n' "$HEAD_SHA" > "$ATTEMPT"
fi

# cycle303 — G-248-5(정합 가드) 갱신 사유: macro 서비스 추가 전엔 frontend 전용 모드가
# 리터럴 `--no-deps frontend` 한 줄이었다. 이제 frontend/macro/frontend+macro 세 모드가
# 같은 코드 라인(SERVICES 배열 확장)을 공유한다 — "up" 라인 총수는 3(full·none·
# 서비스목록)으로 cycle248 당시와 **동일**하게 유지된다(가드가 그 수를 그대로 잰다).
case "$MODE" in
    full)
        run docker compose "${COMPOSE_FILE_ARGS[@]}" up --build -d --remove-orphans
        ;;
    none)
        # 빌드 없는 up = 구성 일치 시 Running(재생성 0), 죽어 있던 컨테이너만 기동.
        run docker compose "${COMPOSE_FILE_ARGS[@]}" up -d --remove-orphans
        ;;
    frontend|macro|"frontend+macro")
        # --no-deps 가 계약이다: 빼면 depends_on(backend/macro) 까지 --build 대상이 돼
        # backend 가 재생성된다(실측, cycle248). SERVICES 는 FRONTEND_HITS/MACRO_HITS
        # 로만 채워진다(위 분류 블록) — backend 가 이 목록에 들어갈 길이 **구조적으로
        # 없다**: backend 히트가 하나라도 있으면 그 즉시 MODE=full 로 확정되어 이
        # 분기 자체에 도달하지 않는다.
        run docker compose "${COMPOSE_FILE_ARGS[@]}" up --build -d --remove-orphans --no-deps "${SERVICES[@]}"
        ;;
    *)
        log "internal error: unknown mode '$MODE'"; exit 2
        ;;
esac

# 마커는 성공한 뒤에만 — set -e 라 compose 가 실패하면 여기 오지 않는다.
if [ "$DRY_RUN" = "1" ]; then
    echo "[deploy][dry-run] would write marker ${MARKER} = ${HEAD_SHA}"
else
    printf '%s\n' "$HEAD_SHA" > "$MARKER"
    rm -f "$ATTEMPT"
    log "marker written: ${MARKER} = ${HEAD_SHA}"
fi

run docker image prune -f
