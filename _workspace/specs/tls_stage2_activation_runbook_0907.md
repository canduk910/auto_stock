# 런북 — TLS 2단계 가동 (월 2026-09-07 20:25~22:00, 사용자 승인 "허용" 09-05 23:xx)

자율 구간: 커밋·푸시·장외 배포·루틴 프롬프트 수정 포함. 사용자 직접 행동은 **⑤ 하나**. 실패 시 각 단계의 원복을 실행하고 멈춘다(추측 진행 금지).

## 0. 선결(20:25 이전에 확인)
- [ ] 20:20 일일 자동 리포트 실행 결과(`RemoteTrigger list_runs` → `get_run_log`)의 마지막 메시지 "(e) 사용 주소" = **https 정식**. http 예비면 **중단**(허용 도메인 미반영) → 사용자에게 보고.
- [ ] 보유 포지션 무관(장외). 20:00~20:15 정산 창 밖(20:25 시작).
- [ ] EC2: `.tls_enabled` 있음 · `.tls_stage2` 없음 · `docker ps` backend/frontend Up · `curl -s -o /dev/null -w '%{http_code}' https://auto.dkstock.cloud/api/health` = 401 · `sudo certbot certificates` 만료 ≥ 30일.

## 1. 루틴 2개 프롬프트에서 http 예비 주소 제거 (외부 조치 — 이 구간에 승인 포함)
`RemoteTrigger get` 으로 현재 프롬프트를 받아 아래 문장만 바꾼다(다른 글자 무변경, uuid 유지, mcp_connections 무접촉).
- 일일(trig_01E6XNiNTxaLWNn7jeTXR9qZ) §1 환경 첫 불릿:
  - 삭제: `curl 자체가 실패하면(도메인 미허용·DNS 실패 등 연결 오류) 예비 주소 `BASE=http://ec2-3-38-228-74.ap-northeast-2.compute.amazonaws.com` 로 같은 확인을 한 번 더 하고 그쪽을 쓴다. 어느 주소를 썼는지 마지막 메시지에 적는다(예비 주소를 썼다는 것은 사람이 클라우드 환경 허용 도메인에 auto.dkstock.cloud 를 추가해야 한다는 신호다).`
  - 대체: `연결이 실패하면 http 로 대체하지 말고(2단계 이후 http 는 전부 https 로 301 이동하며 curl 은 자격을 넘기지 않는다) 실패 사실과 curl 오류를 마지막 메시지에 적고 종료한다.`
  - §3 마지막 메시지의 `(e) 사용한 API 베이스 주소(https 정식 / http 예비)` → `(e) 접속 결과(https 200 확인 여부)`.
- 주간(trig_01H1TtfhP52CXKuyxwG2KnBW) §2 첫 불릿: 같은 치환(문장 형태만 다름 — `(예비 주소 사용 = … 신호)` 괄호까지 삭제). §8 (e) 동일.
- 검증: `RemoteTrigger get` 재조회로 `ec2-3-38-228-74` 문자열 0건.

## 2. 2단계 켜기 (EC2)
```
cd ~/auto_stock && git pull --ff-only   # 최신(런북 커밋 포함)
ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh
```
- 스크립트가 자체 검증(80 `/`→301 Location https://auto.dkstock.cloud/ · ACME 404 · 443 `/`·정적자산 HSTS `max-age=86400` 정확값 · 401)을 통과해야 마커 `.tls_stage2` 가 남는다. 실패 = 자동 원복(마커 삭제 + 1단계 up).
- 외부 확인: `curl -sI http://auto.dkstock.cloud/ | grep -i "^HTTP\|^location"` → 301 + https 도메인 / `curl -sI https://auto.dkstock.cloud/ | grep -i strict` → max-age=86400 / `curl -s -o /dev/null -w '%{http_code}' http://auto.dkstock.cloud/.well-known/acme-challenge/x` → 404 / 백엔드 `docker ps` Up 시간 불변.
- 배포 스크립트 dry-run: `DEPLOY_DRY_RUN=1 bash tools/deploy/compose_up_changed.sh` → `tls=on tls2=on`.

## 3. Basic 자격 회전 (EC2)
```
bash tools/ops/rotate_basic_auth.sh
```
- 산출: `secrets/.rotated-<ts>`(600, 운영자 계정·리포터 계정 새 비밀번호) — **화면·대화에 값을 옮기지 않는다**. 스크립트 검증 = 틀린 자격 401 · 새 자격 `/` 200(https SNI 루프백).
- 실패 시 스크립트가 백업 복원 → 원인 보고, ④ 이후 중단.

## 4. 사용자 안내(⑤) — 메시지로 전달
- EC2 에서 `cat ~/auto_stock/secrets/.rotated-*` 로 두 계정의 새 비밀번호 확인 → 클라우드 환경 "자동매매" 의 `REPORTER_BASIC_PASSWORD` 를 리포터 값으로 갱신 → 브라우저 https://auto.dkstock.cloud 재로그인(운영자 계정 값).
- 사용자가 "넣었어" 라고 하면 ⑥.

## 5. ⑥ 확인
- 일일 루틴 수동 1회 `RemoteTrigger run`(당일 리포트 재생성 — 월요일 정상 거래일이라 노이즈 아님) → 마지막 메시지 https 200 확인. 실패(401)면 비밀번호 오입력 → 재안내.
- 성공 후 EC2 `rm ~/auto_stock/secrets/.rotated-*` + `.htpasswd.bak-*` 는 1주 보관.

## 6. 문서·기록
- 워크리스트 ④ 행 "가동 완료 시각", CLAUDE.md cycle260 문단 "가동 09-07 …", 메모리. `docs/backtest-monitoring.md`·워크리스트의 `http://3.38.228.74/api/...` curl 예시를 `https://auto.dkstock.cloud/...` 로 갱신(비상 매도 curl 포함) — 문서 커밋.
- HSTS 상향(180일) = 09-14 이후 첫 장외 시간(사전 승인): 스니펫 2 + `tls_stage2_enable.sh` 정규식 2줄 + G-260 가드 기대값 동시 갱신 → push(frontend 모드) → 헤더 실측.

## 원복
- `bash tools/ops/tls_stage2_enable.sh disable`(마커 삭제 + 1단계 up, 80/443 401 재확인). 브라우저 HSTS 잔존 ≤ 1일. 루틴 프롬프트는 원복 불필요(https 가 계속 정식).
