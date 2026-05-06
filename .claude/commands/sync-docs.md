---
description: 최근 코드 변경을 docs/, 각 디렉토리 CLAUDE.md, 메인 README.md에 반영한 뒤 커밋한다.
argument-hint: "[추가 컨텍스트(선택)]"
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(find:*), Read, Edit, Write, Grep, Glob
---

너는 이 프로젝트의 코드 변경 사항을 문서에 반영하는 작업을 수행한다.

추가 컨텍스트(선택): $ARGUMENTS

## 진행 절차

### 1. 변경 사항 수집
다음을 병렬 실행해서 무엇이 바뀌었는지 파악한다.
- `git status` — 작업 트리 상태
- `git diff HEAD` — HEAD 대비 unstaged + staged diff
- `git log -10 --oneline` — 최근 커밋 흐름
- 필요 시 `git diff origin/main...HEAD` 로 분기 차이 확인

### 2. 영향 영역 매핑
변경된 파일 경로를 보고 갱신 후보 문서를 정리한다.

| 변경 위치 | 갱신 후보 |
|---|---|
| `src/api/*` | `src/api/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md` (KIS API 호출 패턴/TR_ID 변경 시) |
| `src/auth/*` | `src/auth/CLAUDE.md`, `src/CLAUDE.md` |
| `src/realtime/*` | `src/realtime/CLAUDE.md`, `src/CLAUDE.md` (체결통보·구독 흐름 변경 시 `CLAUDE.md` 핵심 규칙 갱신) |
| `src/engine/*` (전략·스케줄러·OrderEngine·RiskManager 등) | `src/engine/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(전략 추가/규칙 변경 시), `docs/architecture.md`(흐름 변경 시) |
| `src/db/*` | `src/db/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(DB 스키마 섹션) |
| `src/models/*` | `src/models/CLAUDE.md` |
| `src/routes/*` | `src/routes/CLAUDE.md`, `README.md`(엔드포인트 노출 변경 시) |
| `frontend/*` | `frontend/CLAUDE.md`, `README.md`(UI 신규 화면/플로우 변경 시) |
| `Dockerfile`, `docker-compose*.yml`, `.github/workflows/*` | `CLAUDE.md`(Docker 구성, 배포 환경), `README.md`(빌드/실행 안내) |
| `requirements.txt`, `frontend/package.json` | `README.md`(의존성 안내 영향 있을 때만) |
| 신규 전략/매매 규칙 변경 | `CLAUDE.md`의 "다중 전략 아키텍처" 섹션 + 해당 전략 명세, `_workspace/00_leader_trading_rules.md` 동기화 여부 함께 안내 |
| 신규 DB 컬럼/테이블 | `CLAUDE.md`의 "DB 스키마" 섹션 + `src/db/CLAUDE.md` |

`docs/kis/` 하위는 KIS 공식 API 스펙이므로 코드 변경 동기화 대상이 **아니다**. 손대지 않는다.
`docs/architecture.md`는 시스템 흐름이 실제로 변한 경우에만 갱신한다.

### 3. 갱신 대상 후보 검토
- 각 후보 파일을 Read로 열어 현재 기술이 실제 코드와 일치하는지 확인한다.
- 코드의 사실(파일 경로, 함수명, 파라미터, TR_ID, 임계값, 시각, 스키마 컬럼 등)과 어긋난 부분을 모은다.
- 새로 추가된 모듈·전략·엔드포인트·DB 컬럼은 누락 없이 기재한다.
- 제거된 개념(삭제된 함수, 폐기된 패턴)은 문서에서도 함께 제거한다.

원칙:
- 코드 사실(file_path, line, 함수명, 파라미터, 시각, 임계값, 스키마)과 어긋난 부분을 우선 정정.
- 문서가 이미 정확하면 손대지 않는다 (불필요한 리포맷·재배열 금지).
- 새 개념은 기존 문서 톤·구조에 맞춰 자연스럽게 흡수.
- 추측·과장 표현 금지. "현재 코드 그대로"의 사실만 기재.

### 4. 문서 수정
Edit/Write로 정확히 필요한 부분만 갱신한다. 한국어 톤은 기존 문서 스타일을 따른다 (간결·명사형·표/코드 블록 활용).

### 5. 검증
수정 후 다음을 실행해 결과를 확인한다.
- `git diff -- '*.md'` — 문서 변경 요약
- 코드 변경과 문서 변경이 paired되어 있는지 짧게 요약 출력 (어느 코드 변경이 어느 문서 라인에 반영됐는지)

### 6. 커밋
사용자에게 다음을 요약 보고한다.
- 갱신한 문서 파일 목록 (각 파일의 핵심 변경 한 줄)
- 손대지 않은 후보 문서가 있다면 그 이유
- 추가로 사용자 확인이 필요한 항목 (예: 전략 명세 변경이 `_workspace/00_leader_trading_rules.md`에도 반영되어야 하는지)

그 다음 git 커밋을 수행한다. 커밋 시 주의:
- 코드 변경과 문서 변경을 한 커밋으로 묶을지, 문서만 별도 커밋할지는 현재 working tree 상태에 따라 판단.
  - 코드가 이미 별도 커밋으로 들어가 있고 문서만 남았다면 문서 단독 커밋.
  - 코드가 아직 unstaged이면 사용자에게 묶을지 분리할지 짧게 확인.
- 커밋 메시지: 한국어, 1줄 제목 + 필요 시 상세 본문. 변경의 "왜"가 코드 커밋과 같다면 그것을 반복하지 말고 "코드 변경에 따른 문서 동기화"의 관점으로 작성.
- 절대 `--no-verify`/`--no-gpg-sign` 사용 금지. 훅 실패 시 원인 진단 후 재시도.
- 커밋 메시지는 HEREDOC으로 전달해 줄바꿈 보존.

```
git commit -m "$(cat <<'EOF'
docs: <한 줄 요약>

- <세부 변경 1>
- <세부 변경 2>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### 7. 마무리
`git status`로 깨끗한 트리를 확인하고 사용자에게 커밋 해시 + 변경 통계를 짧게 보고한다.

## 금지 사항
- `docs/kis/` 하위 KIS 공식 스펙 md 수정 금지.
- 사용자 확인 없이 코드 변경을 같이 추가·삭제 금지 (이 커맨드의 범위는 "문서 동기화"이지 코드 수정이 아님).
- 추측성·미래형 표현으로 문서 채우지 말 것. 현재 코드의 사실만 기록.
- 빈 변경(작업 트리에 코드 변경이 없거나 문서 갱신이 불필요)이라면 이를 사용자에게 보고하고 커밋하지 말 것.
