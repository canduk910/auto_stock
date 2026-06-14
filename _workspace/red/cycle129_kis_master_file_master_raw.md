# 사이클 129 — KIS 종목 마스터 파일 도입 + master_raw 별도 컬럼 (HIGH)

## 사용자 결정 영구 영속 (verbatim)

- **Q4=A 마스터 우선** (HIGH 위험 명시 수용)
- **Q5=C 전수 보존** (사이클 101 universe + 사이클 126 basics task 변경 0)
- **Q6=C master_raw 별도 컬럼** (사이클 81 G-AST1 영속 보호 = raw 영역 덮어쓰기 차단)
- **Q7 KIS MCP 정본 검증 완료** (KOSPI 70 컬럼 / KOSDAQ 64 컬럼)
- **Q8=A 정본 채택**
- 단위 환산 (억 vs 백만원) → domain-consult 자문 의제 2 채택
- SSL 우회 → urllib → httpx 전환 + 옵션 C 폴백 chain

## domain-consult 5 의제 + SSL 영역 전수 채택 (cycle129_domain_consult.md)

| 의제 | 추천 옵션 | net effect |
|------|---------|-----------|
| 의제 1 (마스터 lag silent 결함) | 옵션 (1) 마스터 우선 + raw 폴백 | POSITIVE |
| 의제 2 (시총 단위 100배 충돌) | 옵션 (a) master_raw 우선 + WARNING/ERROR 임계 (±5% / ±20%) | POSITIVE |
| 의제 3 (키별 우선순위) | 키별 표 채택 (master_raw 단독/우선/raw 영속/양쪽 정합) | POSITIVE |
| 의제 4 (hot path 키 선별) | 1~4단계 전수 구현 | HIGH POSITIVE |
| 의제 5 (16:30 task 시점) | 옵션 A 단일 task | NEUTRAL |
| SSL 영역 | 옵션 C (httpx + SSL 검증 + 폴백) | POSITIVE |

## 명세 영역 8건 (통합 구현 의무)

### 명세 1 — KIS 마스터 파일 다운로드 모듈 (`src/api/kis_master.py`)

- **신규 파일** = httpx 비동기 다운로드 + cp949 파싱 + ZIP 해제 + KOSPI 70 / KOSDAQ 64 분기
- URL 정본:
  - KOSPI: `https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip`
  - KOSDAQ: `https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip`
- 인코딩: `cp949` (KIS 정본 영구 영속)
- 후미 byte: KOSPI 228 byte / KOSDAQ 222 byte
- SSL 영역: 옵션 C = `httpx.AsyncClient(verify=True)` 우선 + 실패 시 `verify=False` 폴백 + WARNING 로그
- field_specs:
  - KOSPI part2: `[2,1,4,4,4, 1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 1,9,5,5,1, 1,1,2,1,1, 1,2,2,2,3, 1,3,12,12,8, 15,21,2,7,1, 1,1,1,1,9, 9,9,5,9,8, 9,3,1,1,1]` (70 컬럼)
  - KOSDAQ part2: `[2,1, 4,4,4,1,1, 1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,9, 5,5,1,1,1, 2,1,1,1,2, 2,2,3,1,3, 12,12,8,15,21, 2,7,1,1,1, 1,9,9,9,5, 9,8,9,3,1, 1,1]` (64 컬럼)
- 함수 시그너처:
  ```python
  async def download_kospi_master() -> list[dict]:
      """KOSPI 마스터 다운로드 + cp949 파싱 + 종목별 dict 반환. ticker 키 = mksc_shrn_iscd."""
  
  async def download_kosdaq_master() -> list[dict]:
      """KOSDAQ 마스터 다운로드 + cp949 파싱 + 종목별 dict 반환. ticker 키 = mksc_shrn_iscd."""
  ```

### 명세 2 — `src/db/stock_master.py` master_raw 컬럼 영역

- migration 034 적용 후 신규 함수:
  ```python
  async def upsert_master_raw(ticker: str, master_raw: dict, updated_at_kst: datetime) -> None:
      """master_raw + master_raw_updated_at 컬럼 영역 upsert. 사이클 81 G-AST1 영속 보호 (raw 영역 절대 변경 0)."""
  
  async def get_master_raw(ticker: str) -> dict | None:
      """master_raw 조회. NULL/{} 반환 = 마스터 미수집."""
  
  async def count_master_raw_today() -> int:
      """오늘 16:30 task 갱신 영역 카운트 (UI 진단)."""
  ```
- 기존 `get(ticker)` 응답에 `master_raw` + `master_raw_updated_at` 키 추가 (사이클 124 패턴 답습)

### 명세 3 — `src/engine/scanner.py` `_stock_master_master_load_once()` 신규

- 신규 함수:
  ```python
  async def _stock_master_master_load_once(force: bool = True) -> dict:
      """KOSPI + KOSDAQ 마스터 일괄 적재. KIS 공식 정본 (cp949 + ZIP + 70/64 분기).
         반환: {kospi_count, kosdaq_count, total, errors, skipped}.
         사이클 120 force 영속 답습."""
  ```
- scanner 진입 차단 영역 분기 (1단계 7건 필수 차단):
  ```python
  def _is_master_blocked_for_entry(master_raw: dict) -> tuple[bool, str]:
      """1단계 차단 7건 + 조건부 5건 분기.
         반환: (차단 여부, 차단 사유)."""
      if master_raw.get("trht_yn") == "Y":
          return True, "거래정지"
      if master_raw.get("sltr_yn") == "Y":
          return True, "정리매매"
      if master_raw.get("mang_issu_yn") == "Y":
          return True, "관리종목"
      if master_raw.get("ssts_hot_yn") == "Y":
          return True, "공매도과열"
      if master_raw.get("stange_runup_yn") == "Y":
          return True, "이상급등"
      if master_raw.get("mrkt_alrm_cls_code", "00") >= "02":
          return True, f"시장경고 {master_raw.get('mrkt_alrm_cls_code')}"
      if master_raw.get("invt_alrm_yn") == "Y":  # KOSDAQ 전용
          return True, "투자주의환기"
      return False, ""
  ```
- 시총 단위 환산 헬퍼 (사이클 129 Q12 시정 영구 영속):
  ```python
  def market_cap_master_to_millions(master_value_eok: int | str) -> int:
      """마스터 (억) → 백만원 환산 = raw.hts_avls 단위 정합. 사이클 116 패턴 답습.

      1 억 원 = 100,000,000 원 = 100 백만원 → × 100.
      Q12 시정 영구 영속 (사용자 verbatim "× 100" 정합).
      """
      return int(master_value_eok) * 100
  
  def validate_market_cap_consistency(master_raw_eok: int, raw_hts_avls_millions: int) -> tuple[str, float]:
      """시총 정합 검증. 반환: (정합 등급 OK/WARNING/ERROR, 차이 비율 %)."""
      master_millions = market_cap_master_to_millions(master_raw_eok)
      if master_millions == 0 or raw_hts_avls_millions == 0:
          return "OK", 0.0  # 정합 검증 회피
      diff_ratio = abs(master_millions - raw_hts_avls_millions) / max(master_millions, raw_hts_avls_millions) * 100
      if diff_ratio <= 5.0:
          return "OK", diff_ratio
      elif diff_ratio <= 20.0:
          return "WARNING", diff_ratio
      else:
          return "ERROR", diff_ratio
  ```

### 명세 4 — `src/engine/scheduler.py` 16:30 KST task lifecycle

- 신규 task:
  ```python
  async def _stock_master_master_load_loop():
      """매일 16:30 KST KIS 마스터 일괄 다운로드. cron 영역 사이클 122/126 패턴 답습."""
  ```
- task_attrs 3곳 동행 추가 (사이클 79 G-AST2 패턴):
  - `_stock_master_master_load_task` 인스턴스 변수
  - `start()` 영역 task 시작
  - `stop()` 영역 task cancel 양쪽 (사이클 79 영구 영속)
- finally + stop() 양쪽 task_attrs 튜플에 추가 의무

### 명세 5 — `src/routes/stock_master.py` POST `/master/refresh` + refresh_progress TaskKey 확장

- 신규 라우트:
  ```python
  @router.post("/master/refresh")
  async def trigger_master_refresh(background_tasks: BackgroundTasks):
      """수동 KIS 마스터 다운로드 trigger. 사이클 127 fire-and-forget 패턴 답습.
         refresh_progress state 'master' 키 분기."""
  ```
- `refresh_progress.py` TaskKey Literal 확장 (사이클 127 영역):
  - L34: `TaskKey = Literal["universe", "basics", "daily", "master"]` (3 → 4)
  - L37: `TASK_KEYS: tuple[TaskKey, ...] = ("universe", "basics", "daily", "master")` 동행
- 사이클 128 envelope 응답 영속 (GET /list 영향 0)

### 명세 6 — 프론트 `frontend/src/types/stock-master.ts` master_raw 키 영역

- interface 확장 (사이클 124 패턴 답습):
  ```typescript
  export interface StockMaster {
    // ... 기존 영역 변경 0
    master_raw: Record<string, string | number | null>;  // KOSPI 70 / KOSDAQ 64 컬럼
    master_raw_updated_at: string | null;
  }
  ```

### 명세 7 — 프론트 `frontend/src/pages/StockMaster.tsx` 4번째 새로고침 버튼

- 4번째 버튼: "마스터 새로고침" (`master` 키)
- FIELD_LABELS 한글 라벨 추가 (1단계 차단 7건 영역 우선):
  - `master_raw.trht_yn` → "거래정지"
  - `master_raw.sltr_yn` → "정리매매"
  - `master_raw.mang_issu_yn` → "관리종목"
  - `master_raw.ssts_hot_yn` → "공매도과열"
  - `master_raw.stange_runup_yn` → "이상급등"
  - `master_raw.mrkt_alrm_cls_code` → "시장경고 (00:없음 01:주의 02:경고 03:위험)"
  - `master_raw.invt_alrm_yn` → "투자주의환기 (KOSDAQ)"
  - `master_raw.prdy_avls_scal` → "전일 시총 (억)"
  - `master_raw.lstn_stcn` → "상장주수 (천주)"
  - `master_raw.roe` → "ROE (%)"
  - `master_raw.kospi200_apnt_cls_code` → "KOSPI200 섹터"
  - `master_raw.ksq150_nmix_yn` → "KOSDAQ150 영역"
  - (총 ~30 키 영역, 1~3단계 영역 우선)
- CATEGORY_KEYS 배치 (사이클 124):
  - "마스터 진입 차단" 카테고리 (1단계 7건)
  - "마스터 펀더멘털" 카테고리 (2단계 5건)
  - "마스터 지수편입" 카테고리 (3단계 5건)

### 명세 8 — `frontend/src/components/RefreshProgressBanner.tsx` 자동 흡수

- TaskKey "master" 영역 자동 흡수 (사이클 127 영역 패턴 답습)
- 동적 5초 폴링 + state 기반 409 가드 + 60초 타임아웃 영속

## 회귀 가드 영역 (~30 케이스)

### 백엔드 (~20)
- `tests/unit/api/test_cycle129_kis_master_download.py` (~5):
  - KOSPI URL 정본 확정
  - KOSDAQ URL 정본 확정
  - cp949 인코딩 영역 정합
  - KOSPI 70 / KOSDAQ 64 컬럼 분기
  - SSL 검증 + 폴백 chain
- `tests/unit/db/test_cycle129_master_raw_upsert.py` (~3):
  - master_raw 컬럼 적재
  - master_raw_updated_at 영역 정합
  - 사이클 81 G-AST1 raw 영역 변경 0 (영속 보호)
- `tests/unit/engine/scanner/test_cycle129_master_load.py` (~5):
  - `_stock_master_master_load_once()` 정상 + force 영속
  - 1단계 차단 7건 분기 (trht_yn / sltr_yn / mang_issu_yn / ssts_hot_yn / stange_runup_yn / mrkt_alrm_cls_code / invt_alrm_yn)
  - 시총 단위 환산 (마스터 억 → 백만원)
  - 정합 검증 임계 (±5% / ±20%)
  - 0/비결정 영역 회피
- `tests/unit/engine/test_cycle129_master_task_lifecycle.py` (~3):
  - 16:30 KST cron task 영속
  - task_attrs 3곳 정합 (사이클 79 G-AST2)
  - lifecycle race 차단 (사이클 106)
- `tests/unit/routes/test_cycle129_master_routes.py` (~4):
  - POST /master/refresh 정상
  - fire-and-forget 영역 (사이클 127)
  - refresh_progress TaskKey 4 확장
  - 사이클 128 envelope 응답 영속

### 프론트 (~5)
- `frontend/src/pages/__tests__/StockMaster_master_button.test.tsx` (~3):
  - 4번째 버튼 렌더링
  - master 키 분기
  - 사이클 124 카테고리 영역 정합
- `frontend/src/components/__tests__/RefreshProgressBanner_master.test.tsx` (~2):
  - TaskKey master 영역 자동 흡수
  - 동적 폴링 영역

### AST 가드 (~5)
- `tests/unit/ast/test_cycle129_ast_master_raw_separation.py`:
  - master_raw 컬럼 = raw 영역과 분리 영속 (사이클 81 G-AST1 영역 확장)
  - `upsert_master_raw` 함수 = raw 영역 미참조 영속

## 영속 의무 (변경 0)

- 사이클 17 KIS LMS chain
- 사이클 38 명문화
- 사이클 79 G-AST2 task_attrs (`_stock_master_master_load_task` 추가)
- 사이클 81 G-AST1 raw 덮어쓰기 금지 (master_raw 분리로 자동 보호)
- 사이클 84 L-2 화이트리스트 (POST 4 라우트 영속)
- 사이클 88 G-REJECT graceful
- 사이클 106 lifecycle race 차단
- 사이클 122/126 task 패턴 100% 답습
- 사이클 127 fire-and-forget + refresh_progress + RefreshProgressBanner 영속
- 사이클 128 envelope 응답 영속 (GET /list 영향 0)

## 매매 안전성 net effect: HIGH POSITIVE

- 1단계 차단 7건 = 작전주/위험종목 매수 진입 영구 차단
- 시총 단위 환산 silent 결함 영구 차단 (사이클 116 패턴 답습)
- 6 전략 전수 net positive (momentum/VB/LTV/donchian/BFB/VCP)

## 후속 단계 (team-leader 인계)

1. **tdd-engineer Red** — 회귀 가드 ~30 케이스 작성
2. **backend-dev Green** — 명세 1~5 통합 구현
3. **frontend-dev Green** — 명세 6~8 통합 구현
4. **tester verify** — 회귀 0 + Supabase MCP READ-ONLY 검증
