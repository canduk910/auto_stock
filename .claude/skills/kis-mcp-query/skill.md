---
name: kis-mcp-query
description: "한국투자증권(KIS) MCP 서버 (mcp__kis-code-assistant__*) 활용 가이드. KIS API 스펙 검색·공식 샘플 코드 조회·TR_ID/응답 구조 재확인이 필요할 때 사용한다. backend-dev / tdd-engineer / tester / refactor-expert 가 공유한다. 신규 KIS API 통합, 응답 파싱 분기 추가, 회귀 테스트의 응답 시리즈 합성, KIS 거부 코드 해석, KIS 호출 패턴 통일, KIS 응답 구조 변경 의심, TR_ID 확인 등 *KIS 측 정본 스펙* 이 필요할 때 반드시 이 스킬을 사용한다. `docs/kis/*.md` 의 로컬 캐시가 최신이 아닐 가능성에 대비한다."
---

# KIS MCP Query — 한국투자증권 공식 스펙 조회 흐름

`docs/kis/` 디렉토리는 KIS API 스펙의 *로컬 캐시* 다. 신규 API 통합 / 응답 분기 의문 / 회귀 시나리오 합성 시에는 **KIS MCP** 로 공식 스펙을 재확인하여 정본을 인용한다.

## 공식 출처 (반드시 최우선 참조)

KIS Code Assistant MCP 는 한국투자증권 공식 저장소에서 제공된다:

- **공식 저장소**: <https://github.com/koreainvestment/open-trading-api/tree/main/MCP/KIS%20Code%20Assistant%20MCP>
- 자연어 검색으로 *334 개 KIS Open API* 스펙 + 샘플 코드를 즉시 조회 (인증 2 / 국내주식 156 / 해외주식 50 / 국내선물옵션 43 / 해외선물옵션 35 / ELW 24 / 국내채권 18 / ETF/ETN 6)

설치·연동·도구 일람·문제 해결은 모두 *공식 README* 가 정본. 본 스킬에서 인용한 항목과 공식 README 가 불일치하면 *공식 README* 가 우선이며, 그 경우 본 스킬을 갱신 (team-leader 에 보고 → 사이클로 흡수).

### 설치 (로컬 stdio 권장)

이 프로젝트는 *Claude Code (CLI)* 환경이므로 **stdio 방식** 으로 연동한다.

```bash
# 1. 공식 저장소 클론 (예: ~/Projects/open-trading-api)
git clone https://github.com/koreainvestment/open-trading-api.git
cd "open-trading-api/MCP/KIS Code Assistant MCP"

# 2. uv 패키지 매니저로 의존성 설치 (Python 3.12+)
uv sync

# 3. stdio 로컬 실행 검증
uv run server.py --stdio
```

Claude Code 의 `.mcp.json` 또는 사용자 MCP 설정에 등록:

```json
{
  "mcpServers": {
    "kis-code-assistant-mcp": {
      "command": "<uv 절대 경로 — `which uv` 결과>",
      "args": [
        "--directory", "<공식 저장소 절대 경로>/MCP/KIS Code Assistant MCP",
        "run", "server.py", "--stdio"
      ]
    }
  }
}
```

> Docker / HTTP (`http://localhost:8081/mcp`) 방식도 가능하나, 개발 머신에서는 stdio 가 간단하다. 운영 EC2 / 공유 환경에서는 Docker + HTTP 권장 (공식 README "Docker (권장)" 참고).

### 공식 README 최신 사항 확인

도구 일람·카테고리 개수·설치 절차는 KIS 측 갱신 가능. 의문 시 1회 fetch 해 정본 재확인:

```bash
curl -sL "https://raw.githubusercontent.com/koreainvestment/open-trading-api/main/MCP/KIS%20Code%20Assistant%20MCP/README.md"
```

본 스킬과 공식 README 불일치 발견 시 team-leader 에 즉시 보고 + 본 스킬을 PR 수정.

## 사용 주체

| 에이전트 | 사용 시점 |
|---------|---------|
| **backend-dev** | 신규 KIS API 통합, 응답 파싱 분기 추가, KIS 거부 코드 해석 시 |
| **tdd-engineer** | KIS 응답 시리즈를 회귀 테스트로 합성할 때 (필드명·타입·null 패턴) |
| **tester** | 양쪽 동시 읽기에서 *코드 측 응답 파싱* vs *KIS 공식 응답* 정합성 검증 시 |
| **refactor-expert** | KIS 응답 처리 패턴 통일 카드 발의 시 공식 응답 구조 인용 |

## KIS MCP 도구 일람 (공식 README 기준)

| 도구 | API 개수 | 용도 |
|------|---------|------|
| `mcp__kis-code-assistant__search_domestic_stock_api` | **156** | **국내 주식 API 스펙 검색 (이 프로젝트 핵심)** — 현재가/호가/차트/잔고/주문/순위분석/시세분석/종목정보/실시간시세 |
| `mcp__kis-code-assistant__search_auth_api` | 2 | 접근토큰 / WebSocket 접속키 |
| `mcp__kis-code-assistant__search_overseas_stock_api` | 50 | 미국/아시아 주식 |
| `mcp__kis-code-assistant__search_domestic_futureoption_api` | 43 | 국내 선물옵션 (야간거래 포함) |
| `mcp__kis-code-assistant__search_overseas_futureoption_api` | 35 | 해외 선물옵션 |
| `mcp__kis-code-assistant__search_elw_api` | 24 | ELW (민감도/변동성/지표순위) |
| `mcp__kis-code-assistant__search_domestic_bond_api` | 18 | 국내 채권 |
| `mcp__kis-code-assistant__search_etfetn_api` | 6 | ETF/ETN (NAV 비교추이/구성종목시세) |
| `mcp__kis-code-assistant__read_source_code` | — | KIS 공식 샘플 코드 (Python) 읽기 |

이 프로젝트는 *국내 주식* 중심 → `search_domestic_stock_api` 가 1 차 도구. 토큰/Hashkey 는 `search_auth_api`.

### 공식 프롬프트 도구 (자연어 1 문장 → 완전 코드 생성)

검색 도구 외에 KIS MCP 가 제공하는 *프롬프트 도구* 2 개 — 신규 API 통합 시 *빠른 골격 생성* 에 유용. 단, 생성된 코드는 본 프로젝트의 컨벤션 (`kis_request()` 경유 / `settings.get_tr_id()` / 응답 래퍼 `ApiResponse`) 으로 변환 후 채택.

| 프롬프트 도구 | 입력 | 용도 |
|-------------|------|------|
| `kis_detailed_code` | `stock_code` (필수) + `task` (필수) + `category` (선택) | 종목코드 + 작업 명확할 때 정확한 코드 골격 생성 |
| `kis_easy_code` | `user_request` (자연어 1 문장) | 어떤 API 인지 모를 때 자동 분석 + 코드 골격 생성 |

활용 예: backend-dev 가 "삼성전자 일별 매수원 조회" 의 *API 가 무엇인지부터* 모를 때 `kis_easy_code("삼성전자 일별 매수원 조회 코드")` 로 1 차 탐색 → 그 후 `search_domestic_stock_api` 로 정본 스펙 재확인 → 본 프로젝트 컨벤션으로 변환.

## 활용 패턴 4 종

### 패턴 1 — 신규 API 통합 (backend-dev)

```
[신규 API 통합 요청]
1. team-leader 의 매매 규칙 명세 수신
2. 통합할 KIS API 카테고리 식별 (예: 일별 거래원 조회 → 국내 주식)
3. search_domestic_stock_api 호출 ── 키워드: "거래원" 등
4. 응답에서 TR_ID, URL, 요청/응답 필드, 예시 확인
5. (선택) read_source_code 로 공식 Python 샘플 패턴 참조
6. docs/kis/ 로컬 캐시와 대조 → 불일치 발견 시 사용자에 알림 (캐시 갱신 권고)
7. tdd-engineer 에 Red 의뢰 시 KIS 응답 구조 인용
```

### 패턴 2 — 회귀 테스트 응답 합성 (tdd-engineer)

```
[회귀 테스트 작성]
1. 회귀 대상 KIS API 식별 (예: TTTC8434R 잔고 조회)
2. search_domestic_stock_api 로 정상 응답 구조 + 빈 응답 + 에러 응답 (rt_cd != "0") 확인
3. respx 픽스처 합성 시 *모든 변형* 을 합성:
   - 정상 (rt_cd=0, output 다수 행)
   - 정상 (rt_cd=0, output 0 행)
   - 에러 (rt_cd=1, msg_cd 분기)
   - 부분 응답 (일부 필드 null)
4. 합성된 응답 시리즈를 _workspace/red/<feature>.md 에 메타데이터로 기록
```

### 패턴 3 — 양쪽 동시 읽기 (tester)

```
[FastAPI ↔ KIS 경계면 검증]
1. 검증 대상 KIS API 식별
2. 왼쪽: search_domestic_stock_api → 공식 응답 필드 목록 추출
3. 오른쪽: src/api/*.py 의 응답 파싱 코드 grep
4. 1:1 대조 — 누락 필드 / 잘못된 타입 / null 처리 누락 식별
5. 결함 발견 시 tdd-engineer 에 회귀 테스트 의뢰
```

### 패턴 4 — 응답 처리 통일 (refactor-expert)

```
[KIS 응답 처리 분기 통일 카드]
1. grep 으로 동일 KIS API 응답 파싱 N 군데 위치 식별
2. search_domestic_stock_api 로 공식 응답 구조 정본 확보
3. N 분기의 *공통 처리* + *예외 처리* 분리
4. 카드 메모에 "공식 응답: ... (KIS MCP 인용)" 명시
5. 카드는 *HIGH 등급* (응답 구조 통일은 행위 영향 가능)
```

## 호출 시 주의사항

- **KIS MCP 는 외부 의존성** — 호출 실패 시 `docs/kis/` 로컬 캐시로 폴백. 단, 사용자에게 *MCP 응답 받지 못함, 로컬 캐시 인용* 명시
- **응답 형식이 자유 텍스트** — 키워드 검색 후 *공식 표/예시 블록* 만 정본으로 인용. 부가 설명은 참고
- **TR_ID 모의/실전 차이** — KIS MCP 응답에 TR_ID 가 *실전 기준* 으로 나오면, 실제 호출 시에는 `settings.get_tr_id()` 로 환경 자동 변환 (CLAUDE.md 컨벤션). 하드코딩 금지
- **응답 갱신 의심** — KIS MCP 응답이 `docs/kis/` 와 불일치하면 *MCP 가 정본* 으로 간주 (KIS 측 갱신 가능성). 단, 사용자에 알림 + `docs/kis/` 캐시 갱신 권고

## 출력 인용 형식

KIS MCP 응답 인용 시 출처를 명시한다:

```markdown
## KIS 공식 응답 (MCP 인용 — search_domestic_stock_api, YYYY-MM-DD)
| 필드 | 타입 | 설명 |
|------|------|------|
| ... | ... | ... |

(키워드: "...")
```

## 안전 규칙

- **KIS MCP 응답을 무비판 채택 금지** — `docs/kis/` 와 *명백히 다른* 경우만 갱신 권고. 그 외에는 기존 캐시 + MCP 응답 차이를 사용자에 노출 후 판단 위임
- **KIS MCP 로 *실 데이터* 조회 시도 금지** — 이 MCP 는 *스펙 검색* 용. 실 시세/잔고는 항상 backend-dev 의 `kis_request()` 경로
- **API Key/Secret 노출 금지** — MCP 호출 시 자격증명 전달 불필요. 전달하지 않음
- **공식 프롬프트 (`kis_easy_code` / `kis_detailed_code`) 결과 즉시 채택 금지** — 생성된 코드는 *공식 샘플 패턴* 으로 본 프로젝트 컨벤션 (`kis_request()` / `settings.get_tr_id()` / Rate Limit / `ApiResponse` 래퍼) 미반영. tdd-engineer 의 Red 회귀 가드 통과 후에만 채택
- **공식 저장소 외 출처 금지** — KIS 공식 GitHub (`koreainvestment/open-trading-api`) 외의 비공식 fork/미러는 검증되지 않음. 출처는 항상 공식 저장소
