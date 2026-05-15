# Phase 6 (보강) — 검증 가능한 행위 분해

**사이클 목적**: 외부 MCP 백테스트 서버 통합 결함 2건 + 선택 1건 즉시 수정.

## 결함 A — MCPClient.call_tool() MCP content 래핑 unwrap 누락 (Critical)

외부 서버 응답이 stock-manager Streamable HTTP 응답 컨벤션 그대로 옴:
```json
{"content":[{"type":"text","text":"{\"success\":true,\"data\":{...}}"}]}
```

→ 우리 `_parse_response` 는 JSON-RPC `result` 만 뽑고 그대로 반환 → `BacktestEngine._unwrap` 이 `data` 키 못 찾음 → `_extract_metrics`/`_extract_job_id` 빈값.

### 행위 (단위)
- **A1**: 일반 응답 `{"result": {...}}` → 그대로 반환 (회귀 보존 — Phase 1 16 케이스 패스 유지)
- **A2**: SSE 응답 `data: {"result": {...}}\n\n` → result 추출 (회귀 보존)
- **A3**: MCP content 래핑 응답 `{"content":[{"type":"text","text":"{\"success\":true,\"data\":{...}}"}]}` → `data` 평탄화 반환
- **A4**: content 래핑 + `success: false` + `error` 필드 → `ExternalAPIError(message=error)` raise
- **A5**: content 래핑 + `success: true` + `data` 없음 → parsed 전체 반환 (graceful)
- **A6**: content 배열에 여러 text 항목 → 첫 번째 text 만 사용
- **A7**: content[0].text 가 JSON 파싱 실패 → 원본 result 반환 + warning 로그
- **A8**: content[0].type != "text" → 원본 result 그대로 반환 (graceful)
- **A9**: content 키 자체 없음 → 기존 동작 (result 그대로 반환)

## 결함 B — donchian_swing YAML 호환성 검증

외부 preset 10개 미지원 → YAML 커스텀 경로(`run_backtest_tool`) 사용. `to_donchian_yaml` 출력이 외부 `validate_yaml_tool` 통과해야.

### 행위 (단위)
- **B1**: `build_yaml("donchian_swing", {})` 출력에 `maximum` + `ema` + `atr` 지표 모두 포함
- **B2**: 출력에 `risk.stop_loss.percent` + `risk.trailing_stop.percent` 둘 다 양수 값 명시
- **B3**: 출력 YAML 이 PyYAML 로 round-trip 파싱 OK (구조 손상 0)
- **B4**: 동일 입력 두 번 호출 → 동일 문자열 (결정성)
- **B5**: `donchian_period`/`long_ma_period` 사용자 override 가 YAML 에 반영

## 결함 C — initialize 세션-id 누락 로그 레벨 다운그레이드 (Low)

stock-manager 외부 서버는 stateless → `mcp-session-id` 헤더 미반환. 매 호출 WARNING 로그 노이즈.

### 행위
- **C1**: `initialize()` 응답에 session-id 없으면 DEBUG 레벨 로그 (WARNING 아님)
- **C2**: 빈 session_id 도 정상 처리 (이전과 동일하게 None 저장)

## 결함 D — BacktestEngine 통합

### 행위
- **D1**: `BacktestEngine.run_for_strategy()` 가 unwrap 된 응답에서 `job_id` 정상 추출 (content 래핑 통과 후)
- **D2**: `BacktestEngine.poll()` 이 unwrap 된 응답에서 `status` + `metrics` 정상 추출
- **D3**: `validate_yaml_tool` 응답이 `{"success":true,"data":{"valid":true}}` 로 와도 `_extract_validate_ok` 가 True 반환

## 의존성

A1~A9 는 mcp_client.py 만 수정. B1~B5 는 backtest_yaml.py 검증 (스냅샷). D1~D3 는 engine 통합. C1~C2 는 mcp_client 보강.

순서: **A → D → B → C** (A 가 D 의 전제). B는 독립 (병렬 가능). C는 최후.
