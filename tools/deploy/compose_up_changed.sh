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
#   full     — backend 이미지·구성 입력 또는 배포 로직 자체가 바뀜 → `up --build -d --remove-orphans`
#              (현행 동일: 양 서비스 재생성)
#   frontend — frontend/ 만 바뀜 → `up --build -d --no-deps frontend` (backend 무접촉 — 실측.
#              의도적으로 정지된 backend 도 기동하지 않는다 — 필요하면 수동 `up -d backend`)
#   none     — 어느 입력도 아님(docs/tests/_workspace/…) 또는 마커==HEAD(이미 성공 배포된 SHA 의
#              재실행) → `up -d --remove-orphans` (빌드 없음 = Running, 재생성 0 — 실측)
#   판정 불가(마커 없음 · 마커 SHA 미지 · diff 실패) → **full** (fail-safe = 현행 동작)
#
# ■ 분류 규칙의 근거 = 이미지 입력의 **구성적** 정의
#   backend  : 루트 Dockerfile 의 COPY 소스는 `requirements.txt` · `src/` 뿐(AST 가드 D-8 이 고정)
#              + `Dockerfile` + `docker-compose.prod.yml`(config hash) + `.dockerignore`
#              + 배포 로직(`.github/workflows/deploy.yml` · `tools/deploy/`) — 로직이 바뀐 배포는
#              한 번 보수적으로 전체를 돈다.
#   frontend : `frontend/` 전체(frontend/Dockerfile 이 `COPY . .`)
#   `.env` 은 git 밖이라 여기서 못 본다 — `.env` 를 손댄 운영자는 스스로 재시작을 안다(cycle243 Phase 2 규약).
#   ⚠️ 오분류의 실패 방향은 비대칭이다: backend 변경을 none 으로 놓치면 **stale backend 가 조용히
#   돈다**(fail-dangerous). 그래서 backend 목록은 "명시적 입력의 합집합"이 아니라 위 구성적 정의를
#   그대로 옮긴 것이고, 가드 `tests/unit/ast/test_cycle248_deploy_pipeline.py` 가 Dockerfile COPY
#   소스 ↔ 이 정규식의 정합을 강제한다.
#
# ■ 환경변수
#   DEPLOY_MARKER      마커 파일 경로 (기본 .deployed_sha — .gitignore 등재). `<마커>.attempt` 는 시도 마커.
#   DEPLOY_DRY_RUN=1   docker 를 호출하지 않고 명령만 출력, 마커·시도 마커도 쓰지 않는다 (true/yes/on 동치,
#                      그 외 값은 exit 2 — 오타가 실배포로 이어지면 안 된다)
#   COMPOSE_FILE_PATH  compose 파일 (기본 docker-compose.prod.yml)
#
# ■ 운영 규칙 — 마커는 "이 git SHA 가 성공 배포됐다" 만 뜻하고 실행 중 이미지와 대조하지 않는다.
#   EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build`
#   를 했으면 `rm .deployed_sha` 로 다음 자동 배포를 full 로 만든다. 수동 배포는 이 스크립트로 한다.
#   `.env` 편집 후 수동 `up -d` 는 이미지가 그대로라 마커를 건드리지 않아도 된다.
set -euo pipefail
# 마커·compose 경로는 저장소 루트 기준이다 — 하위 디렉터리에서 손으로 실행해도 같은 마커를 본다.
cd "$(git rev-parse --show-toplevel)"

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
BACKEND_RE='^(src/|requirements\.txt$|Dockerfile$|docker-compose\.prod\.yml$|\.dockerignore$|\.github/workflows/deploy\.yml$|tools/deploy/)'
FRONTEND_RE='^(frontend/)'

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

if [ -z "$MODE" ]; then
    BACKEND_HITS="$(printf '%s\n' "$CHANGED" | grep -E "$BACKEND_RE" || true)"
    FRONTEND_HITS="$(printf '%s\n' "$CHANGED" | grep -E "$FRONTEND_RE" || true)"
    if [ -n "$BACKEND_HITS" ]; then
        MODE="full"; REASON="backend_inputs_changed"
    elif [ -n "$FRONTEND_HITS" ]; then
        MODE="frontend"; REASON="frontend_only"
    else
        MODE="none"; REASON="no_image_inputs_changed"
    fi
fi

N_CHANGED=0
if [ -n "$CHANGED" ]; then
    N_CHANGED="$(printf '%s\n' "$CHANGED" | grep -c . || true)"
fi
log "mode=${MODE} reason=${REASON} prev=${PREV_SHA:-none} head=${HEAD_SHA} changed=${N_CHANGED}"
if [ -n "$CHANGED" ]; then
    # ⚠️ `head` 금지 — pipefail 아래서 head 가 40행 뒤 닫힐 때 printf 가 아직 쓰고 있으면(목록이 파이프
    # 버퍼 64KB 를 넘는 큰 diff) SIGPIPE(141) → 스크립트 통째 중단. sed 는 입력을 끝까지 읽는다(T-16).
    printf '%s\n' "$CHANGED" | sed -n '1,40p' | sed 's/^/[deploy]   changed: /'
    if [ "$N_CHANGED" -gt 40 ]; then log "  … (+$((N_CHANGED - 40)) more)"; fi
fi

if [ "$DRY_RUN" != "1" ]; then
    printf '%s\n' "$HEAD_SHA" > "$ATTEMPT"
fi

case "$MODE" in
    full)
        run docker compose -f "$COMPOSE_FILE" up --build -d --remove-orphans
        ;;
    frontend)
        # --no-deps 가 계약이다: 빼면 depends_on(backend) 까지 --build 대상이 돼 backend 가 재생성된다(실측).
        run docker compose -f "$COMPOSE_FILE" up --build -d --remove-orphans --no-deps frontend
        ;;
    none)
        # 빌드 없는 up = 구성 일치 시 Running(재생성 0), 죽어 있던 컨테이너만 기동.
        run docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
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
