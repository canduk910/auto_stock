# macro-api — macro_lite 컨테이너 이미지 (cycle303). 매매 이미지(루트 Dockerfile)와 완전 분리.
# 빌드 컨텍스트는 `./macro` 로 닫혀 있다(`docker-compose.prod.yml`/`docker-compose.yml`
# 의 macro 서비스 `build.context`) — 매매 리포 전체가 이 이미지 빌드에 실리지 않는다.
FROM python:3.12-slim

ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY macro_lite/ ./macro_lite/
COPY data/ ./data/
# 🔴 우리가 더한 모듈은 **한 줄씩 명시**한다. 빠뜨리면 `docker build` 는 exit 0 이고
# 컨테이너 기동에서만 `ModuleNotFoundError` 로 죽는다 — `uvicorn` 누락(2026-09-18)과
# 같은 계열이라 두 번째로 밟은 함정이다. `main.py` 가 import 하는 파일을 늘릴 때마다
# 여기도 같이 늘린다(`macro_lite/` 는 vendor 라 디렉터리째 들어간다).
COPY main.py .
COPY sp500.py .

# ── 캐시 볼륨 권한 (cycle303) ────────────────────────────────────────────────
# `MACRO_LITE_CACHE_DIR=/var/lib/macro-lite` 는 compose 가 호스트 `./macro-cache` 를
# bind mount 하는 대상이다(영속 필수 — FRED 3년 제한 때문에 캐시가 사라지면 하이일드
# 스프레드 baseline 이 영구 퇴행한다. `docs/macro-lite.md` 참조).
#
# 이 리포는 같은 계열의 사고를 이미 한 번 겪었다 — `.token_cache` bind mount 가 호스트에
# 먼저 생기면 root:root 로 만들어져 non-root 컨테이너 유저가 쓰기 거부당했다
# (`tests/integration/test_dockerfile_token_cache_perms.py`). 여기서도 같은 순서 규약을
# 따른다: mkdir → chown → USER 전환. 단, bind mount 는 **런타임에 호스트 디렉터리가
# 이미지의 이 mkdir/chown 을 덮어쓴다** — 그래서 이 세 줄만으로는 운영 결함을 막지
# 못한다. **호스트 `~/auto_stock/macro-cache` 는 사람이 compose 실행 전에 먼저
# `mkdir -p` 해야 한다** (`docs/macro-lite.md` 「EC2 최초 설치」 절이 정확한 명령을 준다).
# 이미지 쪽 mkdir/chown 은 (a) bind mount 없이 이미지를 단독 실행할 때(로컬 진단·CI)와
# (b) 호스트 디렉터리가 이미 컨테이너 uid 와 같은 소유자로 존재할 때의 방어선이다.
#
# uid/gid 를 **명시 고정**(1000)한 이유 — EC2 운영 계정 `ubuntu` 도 관례상 uid 1000 이라,
# 사람이 `mkdir -p ~/auto_stock/macro-cache` 를 평범하게(ubuntu 권한으로) 실행하면 추가
# chmod 없이 컨테이너 유저와 소유권이 이미 맞는다(`secrets/`·`.htpasswd` 처럼 별도
# chmod 755 가 필요 없다 — 단, uid 가 다른 환경이면 `docs/macro-lite.md` 의 대안 절차를
# 따른다).
RUN groupadd -g 1000 macro \
    && useradd -m -u 1000 -g macro macro \
    && mkdir -p /var/lib/macro-lite \
    && chown -R macro:macro /app /var/lib/macro-lite

USER macro
ENV MACRO_LITE_CACHE_DIR=/var/lib/macro-lite
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
