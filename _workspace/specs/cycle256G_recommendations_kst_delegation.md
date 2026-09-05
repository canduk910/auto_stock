# cycle256-G 명세 — '전략수정 AI자문' 페이지(`pages/Recommendations.tsx`) 시각 표기를 `utils/kst.ts` 로 위임 (사용자 결정 09-05 "바꿔")

- 배경: cycle261 적대 검토가 발견 — `Recommendations.tsx:44~52` `formatDateTime` 이 `toLocaleString('ko-KR', { hour12: false })` 로 **timeZone 없이**(브라우저 로컬타임 = frontend/CLAUDE.md "시각 표시는 KST 강제" 위반) 렌더. 사용처 3곳(343 생성 · 582 적용 시각 · 584 거절 시각). 3부 보고서 카드 ③ 답 = "바꿔".
- 범위: `frontend/src/pages/Recommendations.tsx` 의 `formatDateTime` 1함수 + 테스트 + `utils/__tests__/kst.test.ts` 가드 확장 + `frontend/CLAUDE.md` 1줄. 백엔드 0줄. 배포 = frontend 모드.

## 행위
- 유효 ISO → `formatKstDateTime(iso)` = `2026-09-07 09:05:00`(KST 강제, 24시제, 환경 무관). 종전 출력은 실행 환경 TZ 에 따라 달랐다(서버 빌드 UTC 컨테이너에서는 화면이 브라우저 TZ 를 따르므로 사용자 브라우저가 KST 면 우연히 맞았고, ICU 서식 `2026. 9. 7. 09:05:00`).
- 빈 값(`null`/`''`) → 종전대로 `'-'`. 파싱 불가 → `'—'`(cycle256-F 와 동일 계약).
- 같은 파일의 숫자 포맷(`value.toLocaleString()` 41행)은 무접촉.

## 테스트
- 신규 `frontend/src/pages/__tests__/Recommendations.format.test.tsx`: (a) 유효 ISO(UTC·+09:00·날짜 경계) → `yyyy-MM-dd HH:mm:ss`, ICU 서식 토큰(`'. '`·`오전`·`오후`) 0건 (b) 빈 값 `'-'` (c) 파싱 불가 `'—'` (d) 렌더: 기존 Recommendations 테스트 픽스처의 `created_at` 으로 "생성 2026-…" 문자열이 화면에 보임(적용/거절 시각도 픽스처에 있으면 1건) (e) TZ 규율 = 동적 import + `process.env.TZ` 고정(kst.test.ts 방식). `formatDateTime` 이 export 돼 있지 않으면 export 를 추가해 단위 테스트한다(export 추가는 Green).
- `utils/__tests__/kst.test.ts` K4 가드를 `pages/` 도 읽을 수 있게 확장(예: `DELEGATING_FILES = ['components/PortfolioRiskCard.tsx', 'components/DailyReportTab.tsx', 'pages/Recommendations.tsx']` 처럼 상대 경로로) — 기존 두 항목의 검사 의미는 무변경. K4-b(날짜용 `toLocaleString`)가 `Recommendations.tsx:48` 을 HEAD 에서 잡는지 확인(Red). 숫자용 41행은 hit 가 아니어야 함(6줄 창 규칙).
- 기존 `Recommendations*.test.tsx` 4파일 무수정 통과(시각 문자열을 단언하는 곳이 있으면 새 서식으로 갱신하고 notes 에 기록).
- 게이트: `npm test` · `npx tsc -b` · `npm run build`. 백엔드 `grep -rl 'frontend/' tests/unit` 가드 전부 실행.

## 문서
- `frontend/CLAUDE.md` cycle256 불릿의 위임 목록에 `Recommendations`(cycle256-G) 추가 + "KST 강제" 예시 줄(65행)에서 이 함수가 timeZone 없이 있던 결함 시정 명기. 루트 CLAUDE.md 표는 행 추가 없이 cycle256 행 구절에 "· 256-G Recommendations(09-05 '바꿔')" 덧붙임. changelog 짧은 행 1개. 워크리스트 3부 답변 표 ③ 행 → 완료(배포 대기).

## 결과 (2026-09-06, Green→검증 완료)
- `formatDateTime` export 전환 + `utils/kst.ts::formatKstDateTime` 위임 배포(사용처 3곳 = 생성/적용 시각/거절 시각). 빈 값 `'-'`, 파싱 불가 `'—'` 계약 유지. `kst.test.ts` K4 가드를 `DELEGATING_COMPONENTS`(파일명)→`DELEGATING_FILES`(상대 경로) 로 확장해 `pages/Recommendations.tsx` 도 검사 범위에 편입(기존 두 항목 판정 로직 무변경).
- 표적 6파일 74 tests 전부 PASS(Red 16 FAIL 전환), 프론트 전체 77 files/579 tests PASS(회귀 0), `npx tsc -b` exit 0, `npm run build` 성공(Recommendations 청크 23.73kB). 백엔드 `test_cycle251_report_account_gate.py`(frontend/ 참조 유일 파일) 12 passed 무영향.
- 뮤테이션 13/13 KILLED(escape 0) + 적대 검토(사용처 3곳 렌더값·빈값/파싱불가/UTC↔+09:00 동치·K4 가드 확장이 기존 검사 약화 안 함·숫자 포맷 무접촉) 전부 반증 실패 = 구현 정상.
- 문서 동기화: `frontend/CLAUDE.md`(Green, 위임 목록+KST 강제 문단) · 루트 `CLAUDE.md` 하네스 표(15행 유지, cycle256 행에 "· 256-G Recommendations(09-05 '바꿔', timeZone 없던 결함 시정)" 부기) · `docs/HARNESS_CHANGELOG.md`(cycle256-F 다음 행 삽입) · `_workspace/00_URGENT_WORKLIST.md` 3부 답변 표 ③ 행 → "구현 완료(배포 대기)" 갱신 완료.
- 잔여 = 배포(frontend 모드, backend 무접촉·장중 가능) — 코드는 커밋 전 상태(메인 세션이 커밋 정책에 따라 처리).
