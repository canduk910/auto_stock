# cycle256-F 명세 — DailyReportTab 시각 표기를 `utils/kst.ts` 로 위임 (사용자 결정 09-05 "바꾸자")

- 범위: `frontend/src/components/DailyReportTab.tsx` 의 `formatDateTime` 1함수 + 테스트 + `frontend/CLAUDE.md` 1줄. 백엔드 0줄, 8영역 무관. 배포 = frontend 모드(backend 무접촉, 장중 가능).
- 배경: cycle256 이 `PortfolioRiskCard` 만 위임하고 DailyReportTab 은 **사용자 가시 서식 변경**이라 결정을 미뤘다. 09-05 보고서 2부 카드 ② 답 = "바꾸자".

## 행위
- 유효한 ISO 입력: `toLocaleString('ko-KR', {timeZone:'Asia/Seoul', hour12:false})`(ICU 의존, 예 `2026. 9. 7. 09:05:00`) → `formatKstDateTime(iso)` = `2026-09-07 09:05:00`(KST, 24시제, 초 포함, 환경 무관).
- `null`/`undefined`/빈 문자열: 현행 `'-'` **유지**(빈 값 표기는 이번 결정 범위 밖).
- 파싱 불가 문자열: 현행은 `toLocaleString` 이 `Invalid Date` 문자열을 돌려주거나 예외 시 원문 반환 → 새 행위 = `formatKstDateTime` 의 `'—'`. (표시 사고 방지 — 원문 노출보다 대시 표기가 안전.) 테스트로 고정.
- `formatNumber`/`formatPnL` 의 숫자용 `toLocaleString()` 은 무접촉(K4 가드는 **날짜용**만 본다 — 가드 정규식을 읽고 확인, 숫자용이 걸리면 가드가 아니라 명세를 재검토).

## 테스트 (frontend vitest)
- `frontend/src/components/__tests__/DailyReportTab.format.test.tsx` 신규: (a) `formatDateTime('2026-09-07T00:05:00Z')` → `2026-09-07 09:05:00` (b) `+09:00` 입력 동일 (c) `null`/`''` → `'-'` (d) `'garbage'` → `'—'` (e) 렌더 스냅샷: ext 카드 헤더 "생성 2026-09-02 20:20:00 · …" 이 화면에 보임(기존 픽스처 `ext_created_at: '2026-09-02T20:20:00+09:00'` 재사용) (f) 동적 import + `process.env.TZ` 고정(cycle256 교훈: 정적 import 는 TZ 고정을 무력화한다 — `utils/__tests__/kst.test.ts` 의 방식을 그대로).
- `utils/__tests__/kst.test.ts` 의 `DELEGATING_COMPONENTS` 에 `'DailyReportTab.tsx'` 추가 → K4 가드가 이 파일의 날짜용 `Intl.DateTimeFormat`/`toLocaleString(... timeZone` 0건을 잠근다. 숫자용 `toLocaleString()` 이 K4 정규식에 걸리면 K4 를 "날짜용(인자에 timeZone 또는 'ko-KR' 포함)" 으로 좁히는 것이 맞다(가드 의도 = 포맷터 자체 생성 금지).
- 기존 `DailyReportTab.ext.test.tsx` 10케이스 무수정 통과.
- 타입 게이트 `npx tsc -b`(`--noEmit` 은 0파일 검사). 전체 `npm test`.
- 백엔드 쪽: `grep -rl 'frontend/' tests/unit` 로 나오는 가드 전부 실행(프론트 전용 사이클 규칙).

## 문서
- `frontend/CLAUDE.md` 66행 cycle256 불릿: "현재 위임 = PortfolioRiskCard … DailyReportTab 은 결정 대기" → "위임 = PortfolioRiskCard(byte 동일) + DailyReportTab(cycle256-F, 09-05 사용자 결정 '바꾸자' — 서식 `2026-09-07 09:05:00`, 빈 값 `'-'` 유지)". 
- 루트 CLAUDE.md 하네스 표에는 **행을 추가하지 않는다**(cycle256 행의 "DailyReportTab 위임은 되돌림(사용자 결정 카드)" 문구 뒤에 "→ 09-05 오후 '바꾸자' 로 cycle256-F 적용" 한 구절만). changelog 에는 짧은 행 1개 append.
- 워크리스트 결정 카드 ② 행 → 완료.

## 결과 (2026-09-05 실측)
- 구현 = `DailyReportTab.tsx::formatDateTime` 를 `utils/kst.ts::formatKstDateTime` 위임 2줄로 교체(빈 값 `'-'` 유지, 파싱 불가 `'—'`). `formatNumber`/`formatPnL` 무접촉.
- 표적 3파일(`DailyReportTab.format.test.tsx` 13 + `kst.test.ts` 36 + `DailyReportTab.ext.test.tsx` 10) = **59 PASS**. 전체 `npm test` = **72 files / 537 tests PASS**. `npx tsc -b` = clean(exit 0).
- 뮤테이션 검증 2라운드(Green 7종 + 적대 검토 8종) **전부 KILLED** — 위임 제거·`toLocaleString` 복원·빈 값/파싱불가 반환값 변경 등 모두 표적 테스트가 잡음.
- 문서 동기화 완료: `frontend/CLAUDE.md`(cycle256 불릿 갱신), 루트 `CLAUDE.md`(cycle256 행에 "→ cycle256-F 적용" 구절 추가, 신규 행 없음), `docs/HARNESS_CHANGELOG.md`(cycle256-F 행 append), 워크리스트 카드 ② → 완료.
- 배포 = frontend 모드(backend 무접촉, 장중 가능) — 실제 push 는 메인 세션의 커밋 정책에 따라 별도 진행(이 사이클은 커밋/push 미실행).
