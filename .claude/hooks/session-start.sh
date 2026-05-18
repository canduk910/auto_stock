#!/bin/bash
# SessionStart hook — Claude Code on the web 세션 부팅 시 의존성 설치
# 로컬 개발 환경에서는 실행하지 않는다 (개발자가 직접 setup).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  echo "[session-start] not in remote env, skip"
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

echo "[session-start] python deps (requirements-dev.txt)"
# 컨테이너 base 이미지가 Debian 패키지로 PyJWT 등 일부 deps 를 RECORD 없이 설치해 둬서
# 일반 pip install 이 uninstall 단계에서 실패한다. --ignore-installed 로 우회.
python3 -m pip install --quiet --disable-pip-version-check \
  --ignore-installed --no-warn-script-location \
  -r requirements-dev.txt

echo "[session-start] root npm deps (playwright runner / js-yaml)"
npm install --silent --no-audit --no-fund --no-progress

echo "[session-start] frontend npm deps"
npm install --silent --no-audit --no-fund --no-progress --prefix frontend

# pytest 가 src/ 를 import 할 때 PYTHONPATH 가 cwd 인지 확인
echo 'export PYTHONPATH="${PYTHONPATH:-}:."' >> "${CLAUDE_ENV_FILE:-/dev/null}"

echo "[session-start] done"
