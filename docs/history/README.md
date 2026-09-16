# docs/history — 정본에서 걷어낸 이력

정본 문서는 **지금 동작하는 규칙만** 적는다. "왜 그렇게 됐나, 전에는 어땠나" 는 여기로 온다.
규약의 출처 = 루트 [`CLAUDE.md`](../../CLAUDE.md) 「문서 규약」 절 (2026-09-17 사용자 결정).

## 세 종류의 문서 — 역할이 다르다

| 무엇 | 어디 | 무엇을 적나 |
|---|---|---|
| **정본** | `CLAUDE.md` 들 · `README.md` · `docs/architecture.md` · `docs/backtest-monitoring.md` · `_workspace/00_leader_trading_rules.md` | 지금 동작하는 규칙만. 현재형 |
| **history** | `docs/history/<정본 이름>.history.md` | 정본에서 걷어낸 경위·실측 수치·결정 근거 |
| **CHANGELOG** | [`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) | 사이클(작업 단위)별 보고 원문. **이력의 유일한 정본** |

history 는 문서 축(이 규칙이 왜 이 값인가)이고 CHANGELOG 는 사이클 축(그날 무엇을 했나)이다.
역할이 갈리므로 중복이 아니다.

## 파일 이름

정본 경로를 `-` 로 이은 뒤 `.history.md` 를 붙인다. 정본을 읽던 사람이 **이름을 계산하지 않고** 열 수 있어야 한다.

| 정본 | history |
|---|---|
| `CLAUDE.md` | `CLAUDE.history.md` |
| `src/engine/CLAUDE.md` | `src-engine-CLAUDE.history.md` |
| `src/engine/strategies/CLAUDE.md` | `src-engine-strategies-CLAUDE.history.md` |
| `src/realtime/CLAUDE.md` | `src-realtime-CLAUDE.history.md` |
| `src/api/CLAUDE.md` | `src-api-CLAUDE.history.md` |
| `src/db/CLAUDE.md` | `src-db-CLAUDE.history.md` |
| `src/routes/CLAUDE.md` | `src-routes-CLAUDE.history.md` |
| `src/auth/CLAUDE.md` | `src-auth-CLAUDE.history.md` |
| `frontend/CLAUDE.md` | `frontend-CLAUDE.history.md` |
| `docs/architecture.md` | `docs-architecture.history.md` |
| `docs/backtest-monitoring.md` | `docs-backtest-monitoring.history.md` |
| `_workspace/00_leader_trading_rules.md` | `workspace-00_leader_trading_rules.history.md` |

`_workspace/` 정본의 history 도 여기 둔다. `_workspace/` 에는 시점 문서(`red/` · `analysis/` ·
`reports/` · `domain_consult/` · `forensics/`)가 사는데, history 를 거기 두면 둘이 섞인다.

## 파일 형식

각 history 파일 맨 위에 1줄을 둔다.

> 원본: `src/engine/CLAUDE.md` · 이관: 2026-09-17

항목은 이 모양이다.

```
## <정본 절 제목 그대로>
### 2026-09-05 cycle255 — TLS 1단계 준비 경위
(정본에서 옮긴 원문 그대로, 편집 금지)
→ CHANGELOG: cycle255 행
```

절 제목을 그대로 쓰는 이유가 있다. 규칙의 "왜?" 가 궁금한 사람은 정본의 절 제목을 들고 온다.
사이클 번호로 찾는 사람은 CHANGELOG 로 간다.

## 규칙 7개

1. **verbatim 이관이다.** 정본에서 옮길 때 요약하지 않는다. 원문을 그대로 붙인다.
2. **append-only.** 이미 들어온 문장은 고치지 않는다 — 이력이기 때문이다. 옮긴 원문에 무언가를
   덧붙이고 싶어지면 그건 **정본**을 고쳐야 한다는 신호다.
3. **CHANGELOG 와 글자까지 같은 문단은 넣지 않는다.** 대신 `→ CHANGELOG: cycleN 행` 링크만 남긴다.
4. **정본에 다는 링크는 파일 상단 1줄뿐**이다 — `> 이력: docs/history/<이름>.history.md`.
   절마다 링크를 달면 그게 다시 덧칠 통로가 된다.
5. **비밀값은 history 로도 옮기지 않는다.** 키·비밀번호·토큰은 그냥 지운다.
6. **history 는 `/sync-docs` 의 덧칠 검사 대상이 아니다.** 여기는 옛 문장이 남아 있는 것이 정상이다.
7. **`docs/` 를 통째로 훑는 문서 가드를 새로 만들지 않는다.** 그런 스캐너는 "삭제된 심볼이 문서에
   남아 있다" 며 history 를 붉힌다. 기존 문서 가드(`_LIVE_DOCS`(`tests/unit/ast/test_cycle257_ast_dead_code_removed.py`) ·
   `_DOC_FILES`(`tests/unit/ast/test_cycle295_ast_gap_hold_removed.py`))처럼 **정본 파일을 이름으로 열거**한다.
