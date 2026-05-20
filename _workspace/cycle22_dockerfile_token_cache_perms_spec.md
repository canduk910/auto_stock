# 사이클 22 — Dockerfile `.token_cache` 디렉토리 권한 영구 보강

## 배경 (확정)

사이클 20 (35ebe3a) push 후 운영 결함 (2026-05-20 13:20:46):
```
PermissionError: [Errno 13] Permission denied: '.token_cache/quote_sub.json'
PermissionError: [Errno 13] Permission denied: '.token_cache/quote_gold.json'
```

**근본 원인**:
- `docker-compose.prod.yml` 볼륨 `./.token_cache:/app/.token_cache` 마운트
- 호스트 디렉토리 신규 생성 시 **root:root** 소유 (Docker bind mount 기본 동작)
- `Dockerfile:17-19` 의 `USER appuser` (non-root) 가 디렉토리 쓰기 거부
- 사이클 20 핫픽스 A 로 `docker exec -u root chown` 임시 해결, 재배포 시 재발 가능

**현업 판단 (팀장)**:
- 토큰 캐시 영속화는 사이클 20 의 핵심 안전 규칙 — 분당 1개 발급 한도 대응
- 컨테이너 재기동 / 신규 호스트 배포 시 PermissionError 재발 = 토큰 발급 폭주 위험
- 빌드 시점 디렉토리 생성 + chown 으로 영구 차단 필수
- 매매 코드 침범 0 — Dockerfile 1줄 변경 + 회귀 가드 3 케이스

## 변경 사양 (1 파일)

### `Dockerfile` (라인 17-19)

기존:
```dockerfile
RUN adduser --disabled-password --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser
```

변경 (chown *전* `.token_cache` 디렉토리 명시 생성):
```dockerfile
RUN adduser --disabled-password --no-create-home appuser \
    && mkdir -p /app/.token_cache \
    && chown -R appuser:appuser /app \
    && chmod 755 /app/.token_cache
USER appuser
```

**핵심 변경**:
- `mkdir -p /app/.token_cache` 를 chown *전* 에 실행
- chown -R 가 디렉토리 + 내부 파일 모두 appuser 소유로 변경
- 빌드 시점에 디렉토리 존재 + 권한 보장
- Docker 볼륨 마운트 시 호스트 디렉토리 권한도 자동 매칭 (컨테이너 측 권한 우선)

## 회귀 가드 (필수, 1 파일)

### `tests/integration/test_dockerfile_token_cache_perms.py` (신규)

3 케이스 (정적 텍스트 파싱, Docker build 미실행):

- **(A) `test_dockerfile_creates_token_cache_dir`**: Dockerfile 에 `mkdir -p /app/.token_cache` 라인 존재 검증 (정규식 매칭)
- **(B) `test_mkdir_before_chown_order`**: `mkdir -p /app/.token_cache` 가 `chown -R appuser:appuser /app` 라인보다 *앞* 에 있는지 순서 검증
- **(C) `test_user_appuser_after_chown`**: `USER appuser` 가 `mkdir`/`chown` 라인 *뒤* 에 있는지 순서 검증

**도구**: `pathlib.Path.read_text()` + 정규식. Docker build 자체는 회귀에서 실행 안 함 (CI 부담)

## 검증

```bash
# 신규 회귀 가드
python -m pytest tests/integration/test_dockerfile_token_cache_perms.py -v
# 기대: 3 신규 케이스 모두 pass

# 백엔드 전체 회귀
python -m pytest -q
# 기대: 1409 + 3 = 1412 passed, 회귀 0

# 영향 인덱스
python tools/test_impact/build_index.py
```

## 문서 동기화 (sync-docs)
- `CLAUDE.md` (루트) — Docker 절: `.token_cache` 디렉토리 빌드 시점 권한 보장 1행 추가
- `src/auth/CLAUDE.md` — 토큰 캐시 영속화 절에 Dockerfile 권한 가드 보강 명시
- `docs/HARNESS_CHANGELOG.md` — 사이클 22 1행 추가

## 안전 원칙

- **사이클 20 (35ebe3a) 코드 보존** — token.py / scheduler.py / docker-compose volumes 그대로
- **사이클 21 (256d063) 보존**
- **매매 코드 변경 0**
- **TDD** — tdd-engineer Red → backend-dev Green
- **한글 커밋 메시지**: `fix(docker): .token_cache 디렉토리 빌드 시점 권한 보장 (사이클 22 — 사이클 20 핫픽스 영구화)`
- **push 사용자 명시 승인 후** — 본 사이클은 매매 코드 침범 0 + Dockerfile 1줄 변경 + 회귀 가드 3 케이스. 핫픽스 영구화라 즉시 push 권장 (이전 chown 핫픽스가 컨테이너 재기동 시 사라질 수 있음)

## 커밋 단위
단일 커밋 — Dockerfile + 회귀 가드 + 문서

## 작업 흐름
1. tdd-engineer: 회귀 가드 3 케이스 Red 작성 → 실패 확인
2. backend-dev: Dockerfile 1줄 변경 → Red → Green 전환
3. tester: 백엔드 전체 회귀 + 영향 인덱스 갱신
4. sync-docs: 문서 3 파일 갱신
5. 커밋 (한글 메시지)
6. 사용자 push 승인 대기

## 보고 (팀장 → 사용자)
1. Dockerfile 변경 diff
2. 신규 회귀 가드 3 케이스 pass 결과
3. 백엔드 전체 회귀 (1409 → 1412)
4. 커밋 해시
5. sync-docs 결과
6. push 시점 권장 (즉시 vs 익일 boot 전)
7. 운영 영향 (재배포 시 PermissionError 영구 차단)
