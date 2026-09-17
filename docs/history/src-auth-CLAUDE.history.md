> 원본: `src/auth/CLAUDE.md` · 이관: 2026-09-17

정본은 [`src/auth/CLAUDE.md`](../../src/auth/CLAUDE.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

절 제목은 **이관 시점의 정본 절 제목**이다. 이관하면서 제목 자체를 바꾼 절은 괄호로 구 제목을 적었다.

---

## 발급 직렬화 (KIS `/oauth2/tokenP` 분당 1개 전역 한도) — 구 제목 「사이클 20 (2026-05-20) — 분당 1개 한도 위반 차단」

### 2026-09-17 이관 — 소제목이 담고 있던 도입 사이클·날짜

```
#### 사이클 20 (2026-05-20) — 분당 1개 한도 위반 차단
```

→ CHANGELOG: 사이클 20 행

## `.token_cache` 권한 (Dockerfile prod) — 구 제목 「사이클 22 (2026-05-20) — Dockerfile 권한 가드 영구화」

### 2026-09-17 이관 — 핫픽스에서 영구화까지의 경위 + 회귀 케이스 목록

```
#### 사이클 22 (2026-05-20) — Dockerfile 권한 가드 영구화
- 사이클 20 후 운영 결함: 호스트 `.token_cache/` bind mount 가 root:root 로 생성 → 컨테이너 `appuser` 가 `quote_sub.json` / `quote_gold.json` 쓰기 거부 (`PermissionError [Errno 13]`)
- `Dockerfile` prod 스테이지 변경: `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `chmod 755 /app/.token_cache` → `USER appuser` 순서. **mkdir 이 chown 보다 앞** + **USER 가 마지막** 순서 불변
- 재배포 시 `docker exec -u root chown` 핫픽스 없이 권한 매칭 자동 보장 (Docker bind mount 컨테이너 측 권한 우선 매칭)
- 회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py` 3 케이스 (A: mkdir 존재 / B: mkdir↔chown 순서 / C: USER 위치). 정적 텍스트 파싱이라 docker build 미실행
```

→ CHANGELOG: 사이클 22 행

## boot 사전 순차 발급

### 2026-09-17 이관 — 소제목의 사이클 꼬리표

```
### boot 사전 순차 발급 (사이클 20)
```

→ CHANGELOG: 사이클 20 행
