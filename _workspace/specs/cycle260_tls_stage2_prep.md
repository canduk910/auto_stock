# cycle260 명세 — TLS 2단계 준비: http→https 301 · HSTS · Basic 자격 회전 (스위치 OFF 상태로 준비)

- 사용자 결정(09-05 보고서 2부 카드 ④ "제안대로"): 2단계 **가동 시점** = 월 09-07 20:20 자동 리포트가 https 로 성공한 것을 확인한 뒤. 이 사이클은 코드·절차만 준비하고 **아무것도 켜지 않는다**(cycle255 와 같은 마커 게이트 패턴).
- 범위: `frontend/nginx.conf.template`(include 1줄) · `frontend/nginx.tls.conf.template`(include 1줄) · `docker-compose.tls2.yml`(신규, frontend 전용 RO 마운트 1개) · `tools/ops/tls_stage2/http-redirect.conf`·`tls-hsts.conf`(신규 스니펫) · `tools/ops/tls_stage2_enable.sh`(신규, enable/disable) · `tools/ops/rotate_basic_auth.sh`(신규) · `tools/deploy/compose_up_changed.sh`(마커 `.tls_stage2` → `-f docker-compose.tls2.yml` 추가, `docker-compose\.tls2\.yml$` 를 full 판정 정규식에 추가) · `.gitignore`(`.tls_stage2`) · 테스트 · 문서. **src/·8영역·scheduler diff 0.** 배포 = `tools/deploy/` 변경이라 full(주말이므로 허용).

## 설계
1. **스니펫 include 게이트** — 두 템플릿의 `server {}` 안(location 들보다 앞)에 각각
   - HTTP: `include /etc/nginx/conf.d/stage2/http-*.conf;`
   - TLS:  `include /etc/nginx/conf.d/stage2/tls-*.conf;`
   `stage2/` 디렉터리는 **`docker-compose.tls2.yml` 이 마운트할 때만 존재**한다(`./tools/ops/tls_stage2:/etc/nginx/conf.d/stage2:ro`). 마커가 없으면 디렉터리가 없고 glob 이 아무것도 못 찾아 렌더 결과가 1단계와 **행위 동일**해야 한다 — ⚠️ nginx 가 "존재하지 않는 디렉터리의 와일드카드 include" 를 오류 없이 넘기는지 **로컬 nginx:alpine 실측이 선결**(cycle255 가 30여 변형을 실측한 방식). 오류가 나면 대안 = 오버레이 tls.yml 의 마운트를 늘리지 말고(G-255-3 이 3개로 핀) `docker-compose.tls2.yml` 이 **stage-1 에도 항상 빈 디렉터리를** 마운트하도록 배포 스크립트가 `.tls_enabled` 만 있을 때 `-f tls2` 에 빈 디렉터리(`tools/ops/tls_stage2/off/`)를, `.tls_stage2` 가 있을 때 실제 스니펫 디렉터리를 마운트하는 2-오버레이 파일(`docker-compose.tls2.off.yml`/`docker-compose.tls2.yml`)로 나눈다. 실측 결과에 따라 Green 이 택하고 명세에 기록.
2. **`http-redirect.conf`** (80 서버 블록에 include):
   ```
   # cycle260 2단계 — ACME 챌린지만 남기고 전부 https 로. `if` + `return` 은 nginx 가 안전하다고 보증하는 유일한 if 용법.
   if ($uri !~ "^/\.well-known/acme-challenge/") { return 301 https://$host$request_uri; }
   ```
   `$host` 는 Host 헤더(포트 없음) — IP 로 접속한 요청도 `https://3.38.228.74/` 로 보내져 인증서 불일치가 난다. 그래서 `return 301 https://auto.dkstock.cloud$request_uri;` 로 **도메인 고정**한다(설계 확정). 80 의 Basic Auth 는 rewrite 단계 return 이 access 단계보다 앞이라 더 이상 **자격을 요구하지 않는다**(cycle247 실측과 동일 원리, 응답에 `WWW-Authenticate` 도 없다 — tester 실측) = 80 이 자격을 묻지 않는 것이 2단계의 목적이다. ⚠️ **과장 금지** — 이것이 "평문 자격 전송이 사라진다"는 뜻은 아니다: 301 은 서버가 자격을 *요구*하지 않을 뿐 클라이언트가 *선제로 보내는* 자격까지 막지는 못한다(tester 실측: `curl -u` 는 301 을 받기 전에 `Authorization: Basic` 헤더를 먼저 평문으로 보낸다). http 오리진에 Basic 자격을 캐시해 둔 브라우저(옛 북마크)도 같은 이유로 첫 요청에, 그리고 HSTS `max-age`(1일)가 지날 때마다 다시 새어 보낼 수 있다 — 그래서 §7 자격 회전이 가동 절차의 **필수 후속**이지 선택이 아니다.
3. **`tls-hsts.conf`** (443 서버 블록에 include): `add_header Strict-Transport-Security "max-age=86400" always;` — **1일**로 시작(includeSubDomains·preload 없음). 1주 안정 뒤 별도 결정으로 `max-age=15552000`(180일) 상향. ⚠️ nginx `add_header` 는 location 에 자체 add_header 가 있으면 **상속이 끊긴다** — `location /`(Cache-Control) 와 정적자산 location 에서 HSTS 가 사라진다. 그래서 스니펫은 server 레벨 add_header 가 아니라 `map`/`include` 만으로는 해결이 안 되고, 두 location 안에도 HSTS 를 넣어야 한다 → 해법 = TLS 템플릿의 두 location 안에 `include /etc/nginx/conf.d/stage2/tls-loc-*.conf;` 를 추가로 두고 스니펫 `tls-loc-hsts.conf` 를 같은 add_header 로 둔다(서버 레벨 `tls-hsts.conf` 는 `/api/`·아이콘 204 응답용). 실측으로 `/`, `/assets/x.js`(정적 정규식 location), `/api/health`(401), `/favicon.ico`(204) 네 경로 전부에서 헤더 존재를 확인한다.
4. **`docker-compose.tls2.yml`**: `services.frontend.volumes` 에 `./tools/ops/tls_stage2:/etc/nginx/conf.d/stage2:ro` 하나. frontend 외 키 금지(G-255-3 과 동일 가드 신설).
5. **배포 스크립트**: `.tls_stage2` 마커는 `.tls_enabled` 가 **함께** 있을 때만 유효(없으면 무시 + 로그 `tls2=ignored_no_tls`). 순서 `-f prod -f tls -f tls2`. 모드 판정 무개입. 로그 `tls2=on|off`.
6. **`tools/ops/tls_stage2_enable.sh`** (`enable` 기본 / `disable`): 
   - 선결: `.tls_enabled` 존재 · 인증서 파일(sudo test) · 로컬 https 401(SNI) · **환경변수 `ROUTINE_HTTPS_CONFIRMED=1`**(사람이 월요일 루틴 결과를 보고 넣는 게이트 — 없으면 종료) .
   - `touch .tls_stage2` → `docker compose -f prod -f tls -f tls2 up -d --no-deps frontend` → ≤10초 폴링 검증: `http://127.0.0.1/` → **301** + `Location: https://auto.dkstock.cloud/` · `http://127.0.0.1/.well-known/acme-challenge/probe` → **404**(301 이면 갱신이 깨진다 — 실패 처리) · `https://127.0.0.1/`(SNI) → 401 + `Strict-Transport-Security: max-age=86400` · `https .../assets/` 정적 경로 헤더 존재 · frontend running.
   - 실패 시 마커 삭제 + `-f prod -f tls up -d --no-deps frontend` 원복 + 80/443 401 재확인. `disable` = 같은 원복 절차(HSTS 는 max-age 1일이라 브라우저 잔존 ≤1일).
   - 스크립트 안에 비밀값·이메일 없음. `set -euo pipefail`.
7. **`tools/ops/rotate_basic_auth.sh`**: 사용자 목록은 `secrets/.htpasswd` 에서 읽는다(현재 `ubuntu`·`reporter` — 하드코딩 금지). 각 사용자 새 비밀번호 `openssl rand -base64 18`(URL 안전하게 `+/=` 제거 → `@` 같은 특수문자 없음: 루틴 프롬프트가 "비밀번호에 @ 가 있어 URL 에 넣으면 깨진다" 고 경고한 그 문제를 없앤다), 해시 `openssl passwd -apr1 -stdin`(htpasswd 미설치, argv 유출 차단). 기존 파일 백업 `secrets/.htpasswd.bak-<ts>`(644) → 새 파일 원자적 교체(`mv`, 644 유지 — nginx uid 101 이 읽어야 한다, 600 금지) → 새 자격을 `secrets/.rotated-<ts>`(**600**, 운영자만 ssh 로 읽음, 화면 출력 금지) 에 기록 → 검증: 옛 자격 401·새 자격 `/api/health` 200(nginx 경유 루프백, 파일은 요청 시점에 읽히므로 reload 불필요) → 실패 시 백업 복원. 사용 순서(문서): ① 스크립트 실행 ② 사용자가 `secrets/.rotated-*` 를 읽어 클라우드 환경 `REPORTER_BASIC_PASSWORD` 갱신 + 브라우저 재로그인 ③ 다음 루틴 실행에서 200 확인 ④ `.rotated-*` 삭제.
8. **문서**: `CLAUDE.md` Docker/배포 절의 cycle255 문단 뒤에 cycle260 문단(스위치 OFF·가동 조건·검증·롤백·HSTS 1일) + 하네스 표 1행(15행 유지) + changelog + `docs/`(운영 가이드가 있으면) + 워크리스트 카드 ④ 행.

## 테스트 (tdd-engineer) — cycle255 가드 파일 패턴을 그대로 따른다
- G-260-1 템플릿: HTTP 템플릿에 stage2 include 정확 1줄(server 안, ACME location 보다 앞), TLS 템플릿에 server 레벨 1줄 + location 2곳 include, HSTS 리터럴은 템플릿에 **0건**(G-255-2 `no_hsts_header` 유지), `auth_basic off` 0건, map 중복 0(G-255-2f 유지). 스니펫 파일: redirect 는 `return 301 https://auto.dkstock.cloud$request_uri` 도메인 고정 + ACME 부정 정규식, HSTS 는 `max-age=86400` + `always`, includeSubDomains/preload 0건.
- G-260-2 오버레이: tls2.yml frontend 키만, volumes 1개 RO, ports/build/environment 없음. `.gitignore` 에 `.tls_stage2`.
- G-260-3 배포 스크립트(기존 `test_cycle255_compose_tls_overlay.py` 의 fake docker 픽스처 재사용): 마커 조합 4가지(tls×tls2) 각각의 compose 인자 순서, tls2 단독은 무시 + 로그, 모드 판정 무개입, dry-run 출력, `docker-compose.tls2.yml` 변경 → full.
- G-260-4 enable 스크립트(기존 `test_cycle255_tls_enable_script.py` 의 fake curl/docker/sudo 하네스 재사용): 게이트 env 부재 → 아무것도 안 함, 선결 실패 → 마커 없음, 정상 → 마커·up 1회·검증 4경로, ACME 301 → 실패+원복, HSTS 부재 → 실패+원복, disable → 원복 절차, 비밀 리터럴 0.
- G-260-5 rotate 스크립트: 사용자 목록을 파일에서 읽음(하드코딩 0), `openssl passwd -apr1 -stdin` 사용, 백업 후 교체, 새 파일 644·rotated 600, 화면에 비밀번호 echo 0건(`echo`/`printf` 로 `$NEW_` 변수 출력 금지 — 파일 리다이렉트만), 검증 실패 시 백업 복원.
- **실측(tester)**: 로컬 nginx:alpine 에 두 템플릿 + 스니펫 디렉터리 있음/없음 두 구성을 실제 렌더·기동해 (a) stage2 디렉터리 부재 시 `nginx -t` OK + 80/443 행위 1단계와 동일 (b) 스니펫 있을 때 80 `/` 301(Location 도메인 고정) · ACME 경로 404 · 443 네 경로 HSTS 헤더 존재(자체 서명 인증서로) · `/api/` 401 유지. cycle255 가 한 방식(임시 htpasswd·자체 서명 cert·docker run -p 임의 포트)을 재사용.

## 결과 (2026-09-05 실측)
- §1 분기 = **서버 글롭과 location 글롭을 분리**(`tls-srv-*.conf`/`tls-loc-*.conf`)해 확정. 원안(`tls-*.conf`+`tls-loc-*.conf`)은 `tls-*` 가 `tls-loc-hsts.conf` 까지 매치해 HSTS 가 서버·location 양쪽에서 중복 적용되는 위반(G-260-1i)으로 실 nginx 음성 대조에서 반증됐다. §1 의 2-오버레이 대안은 채택하지 않고 단일 `docker-compose.tls2.yml` 로 진행.
- Green 신규 가드(G-260-1~5) **86케이스 PASS**, 기존 cycle255·cycle248 가드 125케이스 회귀 0.
- tester 뮤테이션 51종 중 **50 KILLED**(1건 ESCAPED — HSTS 헤더 검사가 접두 매치라 `max-age=0`도 통과 — 아래 시정으로 봉인) + 실 nginx:alpine(1.31.5) 3구성(BASE/OFF/ON) 실측: BASE vs OFF 프로브 매트릭스 byte 동일, ON 은 80 전 경로 301+도메인 고정 Location·443 전 경로 HSTS 정확히 1회, compose 병합 해시로 backend 가 tls2 유무와 무관하게 동일함을 확인.
- 적대 검토 확증 8건 중 **6건 코드 시정**(HIGH 2 — rotate 검증이 존재하지 않는 `/api/health` 를 찔러 항상 실패하던 결함 → `/` 로 정정, HSTS 뮤테이션 ESCAPED 봉인 / MEDIUM 4 — disable 이 `.tls_enabled` 무관 443 을 올리던 결함, `tls_enable.sh` 재실행이 2단계를 원복시키던 결함, 가동 후 체크리스트 로그 누락, 명세 §2 과장 문구), 문서 전면 재작성 1건은 동시 편집 충돌 우려로 보류.
- 최종 스위트 = cycle260 3파일 + cycle255 3파일 **168 PASS**, `tests/unit/deploy`+`tests/unit/ast` **976 passed / 3 skipped / 26 xfailed**, 백엔드 전체 **7,005 passed / 11 skipped / 328 xfailed / 13 xpassed / 0 failed**.
- 스위치는 여전히 **OFF**(`.tls_stage2` 마커·오버레이 미생성) — 가동은 월 09-07 20:20 루틴 https 성공 확인 뒤 `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh`.
