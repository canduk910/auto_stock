# 09-05(토) 주말 오후 3부 보고 — 2부 결정 카드 4장의 답 → cycle256-F 배포 · cycle260(TLS 2단계) 스위치 OFF 준비 배포 · D10 착수 준비 (16:20 ~ 18:32 KST)

> 이 문서는 주말 2부 보고서(`_workspace/reports/2026-09-05_weekend_afternoon.md`, 아티팩트 https://claude.ai/code/artifact/d9e2ad29-74fe-4a60-976f-8a3905ff8509)의 **후속**이다. 2부가 남긴 결정 카드 4장(① 허용 도메인 · ② 일일 리포트 탭 시각 표기 · ③ D10 착수 요일 · ④ TLS 2단계 시점)에 사용자가 오후에 답을 줬고, 이 창은 그 답을 처리한 구간이다. 1부(`2026-09-05_weekend_decision_set.md`)·2부 창의 발견·수치는 그 문서들이 정본이고 여기서 반복하지 않는다.
> 집계 창 = 커밋 `ad368ec..8ef7fc1` = 16:20 ~ 18:32(6건). 시각은 `git log --date=format:%H:%M --pretty='%h %ad %s' ad368ec..8ef7fc1` 로 셌다. 전부 토요일 = 장 닫힘.
> 사용자 메시지(원문) = "1. 추가완료. 2. 바꾸자. 3. 화요일 4. 제안대로." — 2부 카드 ①②③④ 의 답. 답변 시각은 정본 두 곳이 다르게 적었다(워크리스트 "15:0x", 호출자 꾸러미 "16:1x"). 답을 기록한 첫 커밋이 16:20 이므로 이 보고서는 "오후" 로만 쓴다.
> 실측 주체 = EC2 배포 후 상태·로컬 nginx 실측은 **메인 세션**(운영자와 대화하는 Claude)이 수행했고, 이 문서는 그 기록을 옮긴 것이다. HTML 의 "제가/메인 세션(저)" 도 같은 주체다.

## 0. 한눈에

| 항목 | 결과 |
|---|---|
| 커밋 | **6건**(16:20 ~ 18:32) = 코드 3 · 문서 3. 분류 매핑 = `feat`·`fix` → 코드(e0644b8 화면 · 8fe9565 운영 스크립트/설정 · f27f55b 핫픽스 주석 1줄), `docs` → 문서(78a0b1d · eb774ad · 8ef7fc1) |
| 배포 | **1회** — **18:32 full**(f27f55b 까지 누적 = e0644b8 + 8fe9565 + f27f55b, backend·frontend 재생성). full 인 이유 = 8fe9565 가 `tools/deploy/compose_up_changed.sh` 를 바꿔서(cycle248 규칙: 배포 로직 변경은 항상 full). 18:16 첫 push 는 CI 실패로 Deploy skipped, 18:24 핫픽스로 통과. 문서 커밋 3건은 CI `paths-ignore` 로 CI/Deploy 미기동 |
| 사이클 | **2회** — cycle256-F(DailyReportTab 시각 표기 `utils/kst.ts` 위임) · cycle260(TLS 2단계 준비, 스위치 OFF) |
| 사용자 결정 처리 | **4건 전부** — ① 확인 시점 월요일로 확정 · ② 구현·배포 완료 · ③ 화요일 착수 준비물(호출자 목록) 작성 · ④ 스위치 OFF 상태로 준비·배포 완료 |
| 사고 | 장중 서버 중단 0(토요일) · 매매 사고 0 · 기동 오류 0(18:32 재시작 기준, startup complete·오류 grep 0) |
| CI 실패 | **1회**(18:16 8fe9565, backend-test) — 원인 = 추적 파일만 보는 가드가 커밋 뒤에야 붉어짐(§5.2). 핫픽스 f27f55b 18:24 → CI 성공 18:30 → Deploy 18:32 |
| 남은 결정 | **3건**(§7, 급한 순) — ① 월 09-07 20:25~22:00 2단계 가동을 자율 구간으로 허용할지(루틴 2개 프롬프트 수정 승인 포함) ② HSTS 상향 시점 ③ 자문 페이지(`Recommendations.tsx`) 시각 표기도 같은 서식으로 맞출지 |

## 1. 집계 창 커밋 목록 (신→구, 6건)

| 커밋 | 시각 | 분류 | 제목(요약) | 변경 파일 |
|---|---|---|---|---|
| 8ef7fc1 | 18:32 | 문서 | 카드 ②·④ 배포 완료 기록(18:32, 마커 f27f55b, tls2=off 실측) | `_workspace/00_URGENT_WORKLIST.md` |
| f27f55b | 18:24 | 코드(핫픽스) | `rotate_basic_auth.sh` 주석의 `openssl passwd` 레시피에 `-stdin` 명시 — cycle243 D-15 가드(git grep, 추적 파일만)가 커밋 후 붉어진 건 | `tools/ops/rotate_basic_auth.sh` 1파일(주석 1줄) |
| 8fe9565 | 18:16 | 코드 | cycle260 TLS 2단계 준비 — http→https 301 · HSTS(1일) · Basic 자격 회전, 스위치 OFF | 19파일 = `.gitignore` · `CLAUDE.md` · 워크리스트 · 명세 · `docker-compose.tls2.yml`(신규) · changelog · `frontend/nginx.conf.template` · `frontend/nginx.tls.conf.template` · 테스트 4(신규 3 + `test_cycle255_tls_enable_script.py` 개정) · `tools/deploy/compose_up_changed.sh` · `tools/ops/rotate_basic_auth.sh`(신규) · `tools/ops/tls_enable.sh` · `tools/ops/tls_stage2/{http-redirect,tls-srv-hsts,tls-loc-hsts}.conf`(신규 3) · `tools/ops/tls_stage2_enable.sh`(신규) |
| e0644b8 | 18:16 | 코드 | cycle256-F 일일 리포트 탭 시각 표기를 `utils/kst` 로 위임 — `2026-09-07 09:05:00` 서식 | 5파일 = 명세 · `frontend/CLAUDE.md` · `DailyReportTab.tsx` · `DailyReportTab.format.test.tsx`(신규) · `utils/__tests__/kst.test.ts` |
| eb774ad | 16:21 | 문서 | D10 명세 §3-a — `pg.*` 호출자 사전 목록(116건/18파일, 직접 acquire 6) 화요일 착수용 | `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md` |
| 78a0b1d | 16:20 | 문서 | 09-05 오후 사용자 답변 4건 기록 + cycle256-F · cycle260 명세 | 워크리스트 · 명세 2(신규) |

`src/**`·8영역·`scheduler.py`·`.env` diff = 0(두 사이클 모두).

## 2. 2부 카드 4장 — 답과 처리

| 카드 | 답 | 처리 | 상태 |
|---|---|---|---|
| ① 클라우드 환경 허용 도메인에 `auto.dkstock.cloud` 추가 | "추가완료" | 확인은 **월 09-07 20:20 자동 리포트(루틴)** 의 마지막 메시지 "(e) 사용 주소" 로 한다. 토요일에 루틴을 수동 실행하지 않은 이유 = (a) 거래 없는 날 리포트·Notion 페이지가 생기는 노이즈 (b) 확인 시점이 어차피 월요일 밤 2단계 가동 직전이면 충분 | 월요일 확인 대기 |
| ② 대시보드 '일일 리포트' 탭 시각 표기 | "바꾸자" | **cycle256-F** 구현·배포(§3). `2026. 9. 7. 9시 5분 0초`(ICU 의존) → `2026-09-07 09:05:00`(KST, 24시제, 환경 무관) | **완료·배포 18:32** |
| ③ D10(DB 연결 대기 타임아웃) 착수 요일 | "화요일" | 09-08(화) 아침 착수. 준비물 = 명세 §3-a 호출자 사전 목록(§6). 화요일 절차 = 재집계 → 8영역 호출 지점 분류 → 사용자 승인(코드 diff 는 `src/db/pg.py` 단독) → Red→Green→Verify → 장외 배포 | 화요일 착수 대기 |
| ④ TLS 2단계 시점 | "제안대로" | **cycle260** = 2단계를 **스위치 OFF 상태로 준비·배포**(§4). 가동은 월 09-07 20:20 루틴 https 성공 확인 뒤 | **준비 완료·배포 18:32, 스위치 OFF** |

## 3. cycle256-F — 일일 리포트 탭 시각 표기 위임 (커밋 e0644b8, 18:16)

- **범위** = `frontend/src/components/DailyReportTab.tsx` 의 `formatDateTime` 1함수(본문 9줄 → 2줄 — try/catch 8줄을 위임 1줄로, diffstat +3/−8, import 1줄 추가) + 신규 테스트 + `frontend/CLAUDE.md` 1줄. 백엔드 0줄, 8영역 무관. 숫자 표기 함수(`formatNumber`/`formatPnL`)는 무접촉.
- **행위** = 유효 ISO 입력 → `utils/kst.ts::formatKstDateTime` = `2026-09-07 09:05:00`. 빈 값(`null`/`undefined`/`''`) → 종전대로 `-`. 파싱 불가 문자열 → `—`(종전엔 `Invalid Date` 문자열이 화면에 그대로 보였다 — 실측).
- **Red** = HEAD 에서 신규 테스트 11 FAIL / 38 PASS(기대대로). **Green** = 표적 3파일(`DailyReportTab.format.test.tsx` 13 + `kst.test.ts` 36 + `DailyReportTab.ext.test.tsx` 10) 59 PASS · 전체 vitest **72파일 537 PASS** · `tsc -b` clean · `npm run build` 성공.
- 신규 테스트 13케이스 = 서식 5 · 빈 값 3 · 파싱 불가 2 · 렌더 1 · TZ 규율 2. `kst.test.ts` 의 `DELEGATING_COMPONENTS`(K4 가드) 에 `DailyReportTab.tsx` 추가 → K4-e 가 "미위임 보존" 에서 "위임 확인" 으로 반전.
- **뮤테이션** = 2라운드(Green 7종 + 적대 검토 8종) 전부 KILLED. 꾸러미가 대표로 적은 5종 = HH:mm 치환 · 빈 값 분기 삭제 · `'-'`→`'—'` · 옛 `toLocaleString` 복원 · timeZone 없는 `ko-KR`. TZ 4종(UTC · America/New_York · Asia/Kolkata · Asia/Seoul)에서 출력 동일 실측.
- **적대 검토 발견 3건** = (a) 문서 3곳 미반영 → 시정(루트 `CLAUDE.md` cycle256 행 구절, changelog 행, 워크리스트) (b) 인접 `frontend/src/pages/Recommendations.tsx`(대시보드 메뉴명 '전략수정 AI자문')의 동명 `formatDateTime` 이 timeZone 없는 `toLocaleString('ko-KR', { hour12: false })`(48행) = **KST 규칙 위반, 이번 범위 밖 기존 결함** → 결정 카드 ③(§7) (c) K4-e 가 import 줄만으로 통과(가드 의미 정밀도 한계 — 행위 테스트 13건이 보완).
- 백엔드 게이트 = `grep -rl frontend/ tests/unit` 가드 전부 실행 — cycle243 D-15 2건이 붉었는데 원인은 트랙 B(cycle260) 명세의 `openssl passwd -apr1`(`-stdin` 누락) 문구 → 트랙 B 가 명세를 정정. (같은 계열이 §5.2 CI 실패로 한 번 더 나타났다.)
- 배포 = 원래 frontend 모드(backend 무접촉)로 충분한 변경이지만, 같은 push 에 cycle260 의 `tools/deploy/` 변경이 섞여 **full** 로 배포됐다(18:32).

## 4. cycle260 — TLS 2단계 준비, 스위치 OFF (커밋 8fe9565 18:16 + 핫픽스 f27f55b 18:24)

### 4.1 무엇을 준비했나 (아무것도 켜지 않았다)
- **두 nginx 템플릿에 스니펫 include 게이트 — 지시어 4곳** = HTTP 템플릿 `server{}` 안 `include /etc/nginx/conf.d/stage2/http-*.conf;` 1줄(72행) + TLS 템플릿 server 레벨 `stage2/tls-srv-*.conf` 1줄(51행) + location 2곳(`location /` · 정적자산, 84·93행) `stage2/tls-loc-*.conf`. (HTTP 템플릿엔 그 밖에 `stage2` 를 설명하는 주석 3줄이 있다 — 지시어가 아니다.)
- **스니펫 3개** `tools/ops/tls_stage2/` = `http-redirect.conf`(`if ($uri !~ "^/\.well-known/acme-challenge/") { return 301 https://auto.dkstock.cloud$request_uri; }` — **도메인 리터럴 고정**, ACME 갱신 경로만 예외) · `tls-srv-hsts.conf` · `tls-loc-hsts.conf`(둘 다 `add_header Strict-Transport-Security "max-age=86400" always;` = **1일**, includeSubDomains·preload 없음).
- **오버레이** `docker-compose.tls2.yml` = frontend `volumes` 에 `./tools/ops/tls_stage2:/etc/nginx/conf.d/stage2:ro` 하나. 마커 파일 `.tls_stage2`(호스트, git 밖, `.gitignore` 등재)가 있을 때만 배포 스크립트가 `-f docker-compose.tls2.yml` 을 덧붙인다(`.tls_enabled` 와 **함께**일 때만, 로그 `tls2=on|off|ignored_no_tls`). **마커의 존재는 모드 판정(full/frontend/none)에 개입하지 않는다** — 개입하면 켠 날부터 모든 배포가 backend 재시작이 된다. 별개로, 스니펫 디렉터리 `tools/ops/tls_stage2/` 경로 변경은 **diff 규칙**(FRONTEND_RE)에 추가해 frontend 재기동 모드로 분류한다(어느 축에도 없으면 none 모드가 되어 스니펫을 고쳐도 실행 중인 nginx 가 옛 설정을 문다 — 적대 검토 F-8).
- **켜기·끄기 스크립트** `tools/ops/tls_stage2_enable.sh`(`enable` 기본 / `disable`) — 선결 4가지(`.tls_enabled` 존재 · 인증서 파일 · 로컬 https 401 · **`ROUTINE_HTTPS_CONFIRMED=1`** 사람 게이트) → 마커 생성 → `up -d --no-deps frontend`(backend 무접촉) → 검증 4경로(80 `/` → 301 + `Location: https://auto.dkstock.cloud/` · ACME 경로 → 404 · 443 무자격 401 + HSTS 정확값 · 443 정적자산 HSTS) ≤10초 폴링 → 실패 시 마커 삭제 + 1단계 원복을 스크립트가 실행. HSTS 검증은 161~162행 정규식이 `max-age=86400` 을 **정확값**으로 핀한다(§4.3 ESCAPED 봉인의 결과 — 값을 올릴 때 이 두 줄도 함께 바꿔야 한다, §9 ②). 성공 로그 끝에 운영 체크리스트 3항목(루틴 http 예비 주소 제거 → 비밀번호 회전 → 브라우저 재로그인).
- **비밀번호 회전 스크립트** `tools/ops/rotate_basic_auth.sh` — `secrets/.htpasswd` 사용자 목록을 파일에서 읽어(하드코딩 0) `openssl rand -base64 18` 뒤 `+/=` 제거(URL 안전 문자만 남김) + `openssl passwd -apr1 -stdin` 으로 교체, 백업 `secrets/.htpasswd.bak-<ts>`(644) → 원자 교체(644, nginx worker uid 101 이 읽어야 함) → 새 자격은 **화면 출력 없이** `secrets/.rotated-<ts>`(600) 파일로만 → 검증(**틀린 자격 401 · 새 자격 `/` 200** — 옛 자격은 해시만 남아 스크립트가 평문을 몰라 재현 불가, 그래서 '옛 자격 거부' 가 아니라 '인증이 여전히 강제되는가' 를 잰다; 2단계 뒤면 https SNI 루프백) → 실패 시 백업 복원 + `.rotated-*.FAILED`.
- cycle255 `tls_enable.sh` 는 `.tls_stage2` 가 있으면 재실행을 거부(2단계를 통째로 원복하던 사고 경로 차단).

### 4.2 설계 확정 (명세 원안에서 바뀐 것)
- 명세 원안 = TLS 템플릿에 `tls-*.conf` + `tls-loc-*.conf`. 실 nginx 음성 대조에서 `tls-*` 글롭이 `tls-loc-hsts.conf` 까지 매치해 HSTS 가 server·location 양쪽에서 **중복 적용**(헤더 2줄, 실측 n=2)되는 위반(G-260-1i)이 나와 **서버 글롭 `tls-srv-*` / location 글롭 `tls-loc-*` 로 분리**. 분리 후 4경로 전부 정확히 1줄. (nginx `add_header` 는 상속이 아니라 대체라 location 에 자체 add_header 가 있으면 server 레벨 HSTS 가 사라진다 — 그래서 location 안에도 같은 값을 include 해야 한다.)
- 명세 §1 의 2-오버레이 대안은 채택하지 않음 — 실 nginx:alpine 1.31.5 실측에서 **존재하지 않는 디렉터리의 와일드카드 include 도 `nginx -t` 정상**. 단일 `docker-compose.tls2.yml` 로 확정.
- 301 대상은 `$host` 가 아니라 리터럴 `https://auto.dkstock.cloud$request_uri` — IP 로 접속해도 인증서 불일치 없음.
- 명세 §2 과장 문구 정정 — "평문 자격 전송이 사라진다" ✗ → "80 이 자격을 **요구**하지 않을 뿐, 클라이언트가 선제로 보내는 자격(`curl -u` 는 301 을 받기 전에 `Authorization` 을 먼저 보낸다 — 실측)·브라우저 캐시 재전송은 못 막는다 → **자격 회전이 필수 후속**".

### 4.3 검증 (정확 수치)
- 신규 가드 G-260-1~5 **86케이스 PASS**, 기존 cycle255·cycle248 가드 125케이스 회귀 0. 표적 6파일(cycle260 3 + cycle255 3) **168 PASS**(신규 12건 포함).
- **실 nginx:alpine 1.31.5 실측 3구성 × 31프로브**(메인 세션 로컬) — BASE(HEAD 1단계 템플릿) vs OFF(워킹트리 템플릿 + 마운트 없음) = 응답 매트릭스 **완전 동일(diff IDENTICAL)** · ON(+stage2 마운트) = 80 전부 301(쿼리 보존, Host IP · HTTP/1.0 · HEAD · 자격 동봉 전부) · ACME 404 · 443 `/`·정적자산·`/api/health`·`/favicon.ico` 모두 HSTS 정확히 1회 · `/api/` 401 유지 · 오픈 리다이렉트 0 · compose 병합 시 backend 서비스 해시 불변.
- **뮤테이션 51종 → 50 KILLED, ESCAPED 1** = HSTS 검증이 `grep -qi 'max-age=86400'` 접두 매치라 `max-age=0`·`max-age=15552000; includeSubDomains` 도 통과 → 정확 값 매치(줄 끝 앵커, CRLF 허용)로 조이고 3변형(max-age=0 · 15552000 · includeSubDomains) 봉인.
- **적대 검토 확증 8건** — 7건 처리 · 1건 보류(계수 근거 §12):
  - (HIGH) `rotate_basic_auth.sh` 검증 경로가 `/api/health`(백엔드에 없는 라우트 — `/health` 만 존재) + 2단계 뒤엔 80 이 301 → **구조적으로 항상 실패** → `/` 경로 + 2단계면 https SNI 루프백으로 교체.
  - (HIGH) 위 ESCAPED 봉인.
  - `disable` 이 `.tls_enabled` 없어도 443 오버레이를 올리던 결함 → 1단계 마커 없으면 `-f prod` 단독 원복.
  - cycle255 `tls_enable.sh` 를 2단계 뒤 재실행하면 TLS 전체를 원복하던 사고 경로 → 선결에서 거부.
  - 가동 직후 체크리스트를 스크립트 출력에 추가.
  - 명세 §2 과장 문구 정정(§4.2).
  - (F-8) 스니펫만 바꾼 push 가 nginx 에 반영되지 않던 파이프라인 사각 → FRONTEND_RE 에 `tools/ops/tls_stage2/`.
  - (보류) 운영 문서의 http curl 예시(워크리스트 · `docs/backtest-monitoring.md`)를 https 로 전면 전환 — 다른 트랙과의 동시 편집 충돌 우려 → **가동 시 갱신**.
- 스위트 최종 = `tests/unit/deploy` + `tests/unit/ast` **976 passed / 3 skipped / 26 xfailed**, 백엔드 전체 **7,005 passed / 11 skipped / 328 xfailed / 13 xpassed / 0 failed**(cycle260 Docs 단계 실측, 약 3분 40초).

### 4.4 남긴 것 (문서·후속)
- 2단계 뒤 http 비상 curl 은 전부 301(`-L` 은 POST→GET 으로 바뀐다) → **비상 매도 curl 은 `https://auto.dkstock.cloud/...` 로**. 워크리스트·`docs/backtest-monitoring.md` 의 http 예시는 가동 시 갱신.
- `rotate` 산출물 `secrets/.rotated-<ts>`(600)는 nginx 컨테이너에 마운트되는 디렉터리 안 — 사용자가 읽은 뒤 **즉시 삭제**.
- 회전 스크립트가 htpasswd 주석 줄을 사용자로 오인할 수 있음(현 파일은 계정 2줄 = 운영자 계정·리포터 계정뿐이라 미발현).
- HSTS 1일 → 상향은 별도 결정(§7 ②). 상향 시 스니펫 2파일 + `tls_stage2_enable.sh` 검증 정규식 2줄 + G-260 가드 기대값을 **한 커밋에서** 갱신(§9 ②).

### 4.5 가동 절차 (월 09-07 밤, 순서 고정)
1. 20:20 루틴 마지막 메시지 "(e) 사용 주소" = `https://auto.dkstock.cloud` 확인 — 메인 세션. "예비 주소 사용" 이면 카드 ① 미완 → 2단계 보류.
2. 루틴 2개(일일 리포트 20:20 · 주간 자문 화 20:30) 프롬프트에서 **http EC2 예비 주소 문구 제거** — **외부 조치 = 승인 필요**(§7 ① 에 포함). 켠 뒤엔 그 주소가 301 만 돌려줘 실패한다.
3. EC2 `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh` — 메인 세션. 검증 4경로 실패 시 스크립트가 자동 원복.
4. EC2 `bash tools/ops/rotate_basic_auth.sh` — 메인 세션.
5. **사용자** — EC2 `secrets/.rotated-<ts>` 를 읽어 클라우드 환경 `REPORTER_BASIC_PASSWORD` 갱신 + 브라우저 재로그인.
6. 화 20:30 주간 자문(또는 수동 1회)로 200 확인 → `.rotated-*` 삭제 — 메인 세션(삭제는 사용자가 읽은 뒤).

## 5. 배포·검증

### 5.1 표

| 시각 | 커밋 | CI / Deploy | 확인 |
|---|---|---|---|
| 16:20 · 16:21 | 78a0b1d · eb774ad(문서) | CI 미기동(`paths-ignore`) | — |
| 18:16 | e0644b8 + 8fe9565 | CI **실패**(backend-test, 18:16 KST 시작 · gh 09:16Z) → Deploy **skipped**(18:22) | 원인 §5.2 |
| 18:24 | f27f55b 핫픽스(주석 1줄) | CI 성공(18:24 시작 → 18:30 완료) → Deploy **full** 18:31 시작 → 18:32 완료(backend·frontend 재생성) | EC2 마커 `.deployed_sha` = f27f55b · `.attempt` 없음 · 배포 로그 `tls=on tls2=off` · `nginx -t` OK(렌더된 설정의 stage2 include 지시어 4곳 = HTTP 1 + TLS server 1 + location 2, 디렉터리 부재) · 백엔드 오류 0 · startup complete · 루프백 `/api/strategies` 200 · 외부 https/http 무자격 401 · ACME 404 · HSTS 헤더 0 = **1단계(종전)와 동일** — 메인 세션 실측 |
| 18:32 | 8ef7fc1(문서) | CI 미기동 | — |

토요일 = 장 닫힘. 재시작 시각 18:32 는 운영 가이드 장외 창(15:30~19:55) 안. 20:00~20:15 금지 창과도 겹치지 않음.

### 5.2 CI 실패 1회 (18:16 → 18:24 시정)
- **증상** = 8fe9565 의 CI backend-test 실패. 로컬 전체 검사(백엔드 6,555 PASS · 프론트 537 PASS — 메인 세션 push 전 실행)는 초록이었다.
- **원인** = cycle243 D-15 가드(`tests/unit/ast/test_cycle243_ops_docs.py`)가 `git grep` 으로 **추적 파일만** 검사한다. `tools/ops/rotate_basic_auth.sh` 12행 주석의 `openssl passwd -apr1`(`-stdin` 누락 표기)이 금지 패턴에 걸리는데, 로컬 실행 시점엔 그 파일이 **미추적(untracked)** 상태라 가드가 보지 못했고 커밋 뒤 CI 에서만 붉어졌다.
- **시정** = f27f55b 주석 1줄에 `-stdin` 명시(코드 행위 무변경). CI 성공 → Deploy 성공.
- **재발 방지** = push 전에 `git grep`/`git ls-files` 기반 가드를 **커밋(또는 `git add`) 뒤** 다시 돌린다. 대상 = `grep -rl "git grep\|git ls-files" tests/unit` → 5파일(`ast/test_cycle223_ast_donchian_exit_fix.py` · `ast/test_cycle223f_ast_manual_apply_safeguard.py` · `ast/test_cycle223g3_ast_guard_sees_staged.py` · `ast/test_cycle243_ops_docs.py` · `engine/test_cycle259_gate_snapshot.py`). 메모리에 절차 기록.
- 수치 주의 = 위 "6,555" 는 push 전 로컬 실행, §4.3 의 "7,005" 는 cycle260 Docs 단계 실측 — **실행 시점·스코프가 다른 두 수치**라 서로 비교하지 않는다.

## 6. D10 준비 — `pg.*` 호출자 사전 목록 (명세 §3-a, 커밋 eb774ad 16:21, 09-05 15:2x 자동 집계)
- 총 `pg.*` 호출 **116건** / 18파일 / 함수별 fetch 52 · fetchrow 21 · execute 28 · fetchval 13 · executemany 2.
- 직접 `.acquire(` 호출 **6건** = `src/db/pg.py` 128·138·148·156·162행(5) + `src/engine/account_risk_watcher.py` 61행(1).
- 상위 파일 = `stock_master.py` 19 · `trade_history.py` 17 · `stock_master_daily.py` 11 · `kis_quote_accounts.py` 8 · `parameter_recommendations.py` 8 · `system_logs.py` 7 · … · `main.py` 1. 표에 8영역 파일로 표시(굵게)된 것은 없다 — 8영역은 이 db 모듈을 **통해** 간접 호출한다.
- 화요일 아침 절차 = ① 재집계 ② 8영역 파일의 호출 지점을 (a)/(b)/(c) 로 분류해 열 추가 ③ 사용자 승인(8영역 = 예외 타입 추가만, 코드 diff 는 `src/db/pg.py` 단독) ④ Red→Green→Verify ⑤ 장외 배포.

## 7. 결정 대기 (급한 순, 3건 = 호출자 목록 전부, M=3)

| # | 항목 | 답해 주실 것 | 제안 |
|---|---|---|---|
| ① | **월 09-07 20:25~22:00 을 2단계 가동 자율 구간으로 허용할지** — 허용하면 메인 세션이 §4.5 의 1·2·3·4·6 을 승인 없이 이어서 한다(커밋·push·장외 배포·**루틴 2개 프롬프트 수정(외부 조치) 포함**). 사용자는 ⑤(새 비밀번호를 클라우드 환경에 넣기 + 브라우저 재로그인)만. 20:20 루틴이 "예비 주소 사용" 이면 그 밤엔 가동하지 않고 보고만 | "허용" / "그때 물어봐" | 허용. 검증 실패 시 스크립트가 자동 원복하고, 20:25 시작은 20:00~20:15 금지 창 밖 |
| ② | **HSTS 기억 기간 상향 시점** — 1일(`max-age=86400`)로 시작. 브라우저에 되돌릴 수 없는 상태를 심는 값이라 짧게 시작. 인증서 사고 시 2단계를 꺼도 브라우저는 기간이 끝날 때까지 https 만 고집한다 — 1일이면 하루 뒤 http 복귀 가능 | "1주 뒤 올려" / "더 두고 보자" | 가동 1주 뒤(09-14 이후) **180일**(`max-age=15552000`). includeSubDomains·preload 는 그때도 넣지 않음. 실행 = 스니펫 2파일 + `tls_stage2_enable.sh` 검증 정규식 2줄 + G-260 가드 기대값을 **함께** 갱신(§9 ②) |
| ③ | **자문 페이지(`Recommendations.tsx`, 대시보드 메뉴 '전략수정 AI자문')의 시각 표기도 같은 서식으로 맞출지** — 생성·적용·거절 시각이 timeZone 없는 `toLocaleString('ko-KR', { hour12: false })` = **KST 규칙 위반**(브라우저 시간대를 따른다). 이번 적대 검토에서 발견한 기존 결함, 사용자 가시 변경이라 카드 | "바꾸자" / "그대로" | 바꿈(`2026-09-07 09:05:00` 으로 통일). frontend 전용 = 무재시작, 장중 가능. cycle256-F 와 같은 방식 |

정본 워크리스트에 추가 결정은 없다. 카드 ① 의 "루틴 프롬프트 수정 승인" 은 별도 항목이 아니라 ① 에 포함(허용하면 별도 답 불필요).

## 8. 다음 확인 시점 (누가 · 언제 · 무엇)

- **월 09-07 07:55 이후** — 메인 세션: 사이클 254 D+1 7서명(2부 보고서 §5) · 09:30 채널 프로브(D8, **EC2 cron 1회성 자동 실행** — 메인 세션은 실행이 아니라 **로그 판독**) · D4 착수(승인 완료).
- **월 09-07 20:20** — 메인 세션: 루틴 실행 로그(`list_runs` → `get_run_log`)에서 "(e) 사용 주소" 확인. `https://auto.dkstock.cloud` 면 카드 ① 완료 = 2단계 가동 조건 충족. "예비 주소 사용" 이면 미완 → 가동 보류·보고.
- **월 09-07 20:25~22:00** — 카드 ① 허용 시 §4.5 절차. 사용자는 ⑤.
- **화 09-08 아침** — 메인 세션: D10 착수, §6 재집계 → 8영역 호출 지점 분류 → 승인 요청.
- **화 09-08 20:30** — 주간 자문 루틴이 새 비밀번호로 200 인지(§4.5 ⑥).

## 9. 승인 시 절차 (주체 명시)
- **①** — 사용자: "허용". 메인 세션: 20:20 루틴 사용 주소 확인 → 루틴 2개 프롬프트에서 http 예비 주소 문구 제거 → EC2 `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh` → `bash tools/ops/rotate_basic_auth.sh` → 사용자에게 `.rotated-<ts>` 경로 알림. 사용자: 파일을 읽어 클라우드 환경 `REPORTER_BASIC_PASSWORD` 갱신 + 브라우저 재로그인. 메인 세션: 화 20:30 루틴 200 확인 → `.rotated-*` 삭제 → 운영 문서 http 예시 https 로 갱신(§4.4 보류분).
- **②** — 사용자: 시점. 메인 세션: 그 시점에 **한 커밋으로** (a) `tls-srv-hsts.conf`·`tls-loc-hsts.conf` 두 파일의 값을 `max-age=15552000` 으로(두 파일 반드시 동일) (b) `tools/ops/tls_stage2_enable.sh` 161~162행의 사후 검증 정규식 `max-age=86400` 2줄을 새 값으로 (c) G-260 가드의 기대값을 새 값으로 → push(frontend 재기동 모드) → 443 헤더 실측. **(b) 를 빼먹으면** 스니펫은 180일을 내보내는데 켜기 명령은 1일을 기대하므로, 이후 `enable` 재실행(예: 사고 뒤 재가동)이 검증 실패 → 마커 삭제 + 1단계 자동 원복으로 끝난다(15552000 은 ESCAPED 봉인 때 명시적 기각 변형으로 넣은 값).
- **③** — 사용자: "바꾸자". 메인 세션: `Recommendations.tsx::formatDateTime` 을 `formatKstDateTime` 위임으로 + 테스트 + K4 `DELEGATING_COMPONENTS` 등록 → vitest·`tsc -b` → frontend 모드 배포(장중 가능).

## 10. 함께 만든 것 · 배운 점

### 10.1 만든 것
- 화면: `DailyReportTab.tsx` 위임 2줄 + 행위 테스트 13케이스 + K4 가드 등록.
- 2단계: nginx 스니펫 3 · 오버레이 1 · 켜기/끄기 스크립트 · 비밀번호 회전 스크립트 · 배포 스크립트 마커 연동 · cycle255 스크립트 재실행 거부 · 가드 86케이스(테스트 파일 신규 3 + 개정 1).
- D10: 호출자 사전 목록(§6).
- 문서: 안내서 2개 파일 4곳 = 루트 `CLAUDE.md` 3곳(하네스 표 1행 + Docker/배포 절 cycle260 문단 + cycle256 행 구절) + `frontend/CLAUDE.md` 1줄 · `docs/HARNESS_CHANGELOG.md` 2행 · 워크리스트 답변 표 · 명세 3.

### 10.2 배운 점
- **`git grep` 기반 가드는 커밋 뒤에만 붉어진다** — 로컬 전체 검사가 초록이어도 CI 가 다를 수 있는 이유 중 하나. push 전 "커밋 뒤 가드 5파일 재실행" 을 절차로.
- **명세 원안의 글롭이 실측에서 헤더 중복을 만들었다** — `tls-*` 가 `tls-loc-*` 를 포함. 설정 파일 이름 규칙은 실 nginx 로 음성 대조까지 해야 확정된다.
- **"평문 전송이 사라진다" 는 과장이었다** — 301 은 서버가 요구하지 않을 뿐, 클라이언트 선제 전송은 못 막는다. 그래서 비밀번호 회전이 선택이 아니라 필수 후속.
- **인접 코드의 같은 결함** — 한 함수를 고칠 때 동명 함수를 grep 하면 기존 결함(자문 페이지)이 나온다. 범위 밖이면 카드로.
- **검증값을 여러 곳에 핀하면 상향 절차도 여러 곳이다** — HSTS 값은 스니펫 2 + 켜기 스크립트 정규식 2줄 + 가드 기대값에 있다. 한 곳만 올리면 켜기 명령이 자기 원복을 한다(사실 대조 렌즈 지적).

## 11. HTML 에서 단순화한 곳 (정확값 대응표)

| HTML 표현 | 정확값 (이 문서) |
|---|---|
| "오후에 답을 주셨다" | 워크리스트 15:0x / 꾸러미 16:1x, 첫 기록 커밋 16:20 |
| "이번 작업 시간(16:20~18:32)" | 집계 창 `ad368ec..8ef7fc1` |
| "화면 서버(nginx)" | frontend 컨테이너의 nginx — 정적 파일 · Basic Auth · `/api/` 프록시 |
| "저장소 서비스(GitHub)" · "자동 검사" | GitHub Actions CI(backend-test) + Deploy |
| "테스트" | 개별 pytest/vitest 케이스(가드 포함) |
| "메인 세션(저)" | 운영자와 대화하는 메인 세션 Claude(report-writer 아님) — 서버 실측 주체 |
| "설정 문법 검사 통과" | `nginx -t` OK, 렌더된 설정의 stage2 include 지시어 4곳(HTTP 1 + TLS server 1 + location 2), 디렉터리 부재 |
| "바깥에서 http·https 모두 종전과 같은 응답" | 외부 https/http 무자격 401 · ACME 404 · HSTS 헤더 0 |
| "자동 검사에서 막혔다" | CI backend-test 실패 → Deploy skipped(18:22) |
| "메모(주석) 한 줄" | `rotate_basic_auth.sh` 12행 주석 `openssl passwd -apr1` → `-stdin` 명시(f27f55b) |
| "테스트 5개" | `grep -rl "git grep\|git ls-files" tests/unit` = 5파일(§5.2) |
| "이름 주소 / 숫자 주소" | 도메인 `auto.dkstock.cloud` / IP `3.38.228.74` |
| "브라우저가 1일 동안 https 만 기억" | HSTS `max-age=86400`, includeSubDomains·preload 없음 |
| "180일" | `max-age=15552000` |
| "켜기 명령의 검사 값" · "테스트의 기준값" | `tools/ops/tls_stage2_enable.sh` 161~162행 정규식 `max-age=86400` · G-260 가드 기대값 |
| "설정 파일 3개 중 기억 기간이 적힌 2개" | `tls-srv-hsts.conf` · `tls-loc-hsts.conf`(`http-redirect.conf` 제외) |
| "테스트는 전부 초록" | vitest 72파일 537 PASS · 백엔드 7,005 PASS(cycle260 Docs 단계) / 6,555 PASS(push 전 로컬) — 스코프 상이 |
| "세 상태에 같은 요청 31가지" | 3구성(BASE/OFF/ON) × 31프로브, BASE=OFF diff IDENTICAL |
| "일부러 51가지 망가뜨려 50가지 잡음, 1가지 보강" | 뮤테이션 51 → 50 KILLED, ESCAPED 1(HSTS 접두 매치) 봉인 + 3변형 |
| "지적 8건, 7건 고침 · 1건 켜는 날" | 적대 검토 확증 8건 = 7건 처리 + 1건 보류(운영 문서 https 전환 → 가동 시) |
| "확인 주소가 서버에 없는 주소" | `rotate_basic_auth.sh` 가 `/api/health` 를 검증 경로로 씀(백엔드 라우트 `/health` 만 존재) → `/` 로 정정 |
| "테스트는 86건" | 신규 가드 G-260-1~5 86케이스 |
| "DB(데이터베이스) 호출 지점 116곳" | `pg.*` 호출 116건 / 18파일 / 직접 `.acquire(` 6 |
| "화면만 고치는 일은 무재시작" | frontend 모드(cycle248). 단 이번 push 는 `tools/deploy/` 변경이 섞여 full |
| "1주 뒤" | 가동(09-07) + 7일 = 09-14 이후 |
| "새 비밀번호 파일" | `secrets/.rotated-<ts>`(600), 읽은 뒤 즉시 삭제 |
| "채널 확인 명령이 서버에서 자동으로 한 번 실행" | D8 = EC2 cron 월 09:30 1회성 프로브(cycle253), 메인 세션은 로그 판독 |
| "'전략수정 AI자문' 페이지" | `frontend/src/pages/Recommendations.tsx`(메뉴 라벨 = `App.tsx` 24행) |
| "안내서 2개 파일 4곳" | 루트 `CLAUDE.md` 3곳 + `frontend/CLAUDE.md` 1줄 |
| "운영자 계정 · 리포터 계정" | `secrets/.htpasswd` 의 Basic 사용자 2명(사용자명은 보고서에 적지 않음) |

## 12. 출처 대조
- 커밋 수·시각·파일 = `git log --name-only ad368ec..8ef7fc1`(6건, 본 문서 §1 과 일치).
- CI/Deploy 시각 = `gh run list`(UTC): 8fe9565 CI 09:16:24Z 실패 · Deploy 09:22:17Z skipped · f27f55b CI 09:24:09Z 성공 · Deploy 09:31:00Z 성공 → KST = +9 시간(18:16 · 18:22 · 18:24 · 18:31).
- cycle256-F 수치 = 명세 `_workspace/specs/cycle256F_dailyreport_kst_delegation.md` "결과" 절 + changelog 행. 꾸러미의 "뮤테이션 5종" 은 대표 열거이고 정본은 명세의 "2라운드(7+8) 전부 KILLED". `formatDateTime` 줄 수 = `git show e0644b8^:frontend/src/components/DailyReportTab.tsx` 46~56행(본문 9줄) vs e0644b8 48~51행(본문 2줄), diffstat +3/−8 — 꾸러미의 "7줄" 은 어느 계산으로도 나오지 않아 채택하지 않았다.
- cycle260 수치 = 명세 `_workspace/specs/cycle260_tls_stage2_prep.md` "결과" 절 + changelog 상단 행 + 루트 `CLAUDE.md` Docker/배포 절 cycle260 문단. 31프로브·헤더 중복 n=2·nginx 1.31.5 = 꾸러미(tester 실측 인용).
- stage2 include 지시어 수 = `grep -n stage2 frontend/nginx.conf.template frontend/nginx.tls.conf.template` — 지시어 4(HTTP 72행 · TLS 51·84·93행) + HTTP 주석 3(63·64·68행) = 문자열 7. 꾸러미의 "7곳" 은 문자열 수라 지시어 수 4 로 정정.
- 적대 검토 8건 계수 = 꾸러미 "8건 전부 시정" 과 changelog·명세 "6건 코드 시정 + 문서 1건 보류"(7건만 열거)가 다르다. changelog 가 계수에 넣지 않은 8번째 = **F-8**(스니펫 변경의 frontend 분류) — 근거는 `tools/deploy/compose_up_changed.sh` 86행 주석 "cycle260 tester 후속(F-8)" + `tests/unit/deploy/test_cycle260_compose_tls2_overlay.py` 334행 docstring "T-260-11 (tester F-8 강화)". 따라서 6 + F-8 = **7건 처리 + 1건 보류**(§4.3). 꾸러미의 "1건 보류 없음" 은 명세와 직접 충돌해 채택하지 않았다.
- `rotate_basic_auth.sh` 검증 방식 = 스크립트 45~49행 주석(틀린 자격 401 + 새 자격 200, 옛 자격은 평문 재현 불가). `openssl rand` 뒤 `+/=` 제거 = 33~35행 주석.
- HSTS 검증 정규식 = `tools/ops/tls_stage2_enable.sh` 161~162행(`^Strict-Transport-Security: max-age=86400\r?$`).
- 사용자 답변 4건 = `_workspace/00_URGENT_WORKLIST.md` "2026-09-05 오후 사용자 답변" 표.
- D10 = `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md` §3-a.
- `Recommendations.tsx` 결함 = 소스 48행 직접 확인(`d.toLocaleString('ko-KR', { hour12: false })`, timeZone 없음). 대시보드 메뉴명 '전략수정 AI자문' = `frontend/src/App.tsx` 24행.
- D8 실행 주체(EC2 cron 자동) = 메모리 `project_0905_decisions` + 2부 보고서 §5.
- 가드 5파일 = `grep -rl "git grep\|git ls-files" tests/unit` 직접 실행.
- EC2 배포 후 상태·로컬 nginx 실측 = 메인 세션이 수행(꾸러미). 본 문서는 그 기록을 옮긴 것이다.
- 비밀값 없음 — 비밀번호·키·메일 주소·Basic 사용자명을 적지 않았다.

## 13. 게시 전 검토 지적 처리 (2렌즈)
- **쉬운 말 렌즈 39건**(HIGH 2 · MEDIUM 19 · LOW 18) — **전부 수용**. HIGH 2 = nginx → '화면 서버(nginx)' 용어 등재 + 본문 3곳 통일 / 콜아웃의 "~만 답해 주시면" 이 결정 카드 3장을 가리던 문장 교체. 그 밖에 '창' → '작업 시간', DB·GitHub·주석·인증서·헤더 풀이, '예비 주소'·'명령'·'테스트/자동 검사' 용어 통일, 수동태·명사 문장·60자 초과 문장 정리, 바닥글 3줄 분리, 자문 페이지 메뉴명 '전략수정 AI자문'.
- **사실 대조 렌즈 13건**(MEDIUM 3 · LOW 10) — **전부 수용**. rotate 검증 = "틀린 자격 401 · 새 자격 200"(§4.1) · stage2 include 7 → 지시어 4(§5.1·§11) · HSTS 상향 절차에 켜기 스크립트 정규식 2줄 + 가드 기대값 추가(§9 ②·§4.4·§7 ②) · 적대 검토 계수 근거 명시(§12) · `formatDateTime` 9줄 → 2줄(§3) · 마커/모드 판정 주어 명시(§4.1) · CI 시각 표기 "18:16 KST(gh 09:16Z)"(§5.1) · `openssl rand` URL 안전 문구(§4.1) · D8 = EC2 cron 자동 실행 + 로그 판독(§8) · 1인칭 주체 = 메인 세션(머리말·§12·HTML) · 안내서 2개 파일 4곳(§10.1·HTML) · Basic 사용자명 → 역할명(§4.4) · 원문 경로 = 이 게시에서 `_workspace/reports/` 에 파일을 써서 해소(커밋은 메인 세션).
- **메인 세션 결정 5건** 반영 = ① 계수 7+1 유지 + §12 근거 ② 카드 ② 실행 목록 확장 + 원복 이유 ③ 문구 8종(rotate 검증 · include 4곳 · 9줄→2줄 · KST 표기 · D8 · 안내서 4곳 · 실측 주체) ④ 사용자명 → 역할명 ⑤ 사용자 답변 시각 미기재 유지.
