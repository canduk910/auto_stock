-- 사이클 129 (2026-06-13) — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) master_raw 별도 컬럼.
-- 사용자 결정: Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼 + Q8=A 정본 채택.
-- 사이클 81 G-AST1 영속 보호 (raw 영역 덮어쓰기 절대 차단) — master_raw 별도 컬럼으로 자동 분리.
-- domain-consult 자문 (cycle129_domain_consult.md) 5 의제 전수 채택 + SSL 영역 옵션 C (httpx + 폴백).
-- 16:30 KST cron task 영역 마스터 파일 다운로드 + cp949 파싱 + KOSPI 70 / KOSDAQ 64 컬럼 분기.

-- master_raw 컬럼 추가 (JSONB nullable, 기본값 {} 명시)
ALTER TABLE stock_master
    ADD COLUMN IF NOT EXISTS master_raw JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN stock_master.master_raw IS
    'KIS 종목마스터 파일 (kospi_code.mst / kosdaq_code.mst) 원본 JSONB. KOSPI 70 컬럼 / KOSDAQ 64 컬럼.
     사이클 129 도입 — Q4=A 마스터 우선 + Q6=C 별도 컬럼 (사이클 81 G-AST1 raw 분리 보호).
     매일 16:30 KST cron task 갱신. 17시간 lag 데이터 = D-1 KRX 영업 종료 후 영역 흡수.
     매매 hot path 활용 키: trht_yn (거래정지) / sltr_yn (정리매매) / mang_issu_yn (관리종목) /
     ssts_hot_yn (공매도과열) / stange_runup_yn (이상급등) / mrkt_alrm_cls_code (시장경고 00~03) /
     invt_alrm_yn (KOSDAQ 투자주의환기) / prdy_avls_scal (시총 억 단위 = raw.hts_avls 백만원 단위 ÷ 10000).';

-- 마스터 갱신 시점 추적 컬럼 (task lifecycle 정합)
ALTER TABLE stock_master
    ADD COLUMN IF NOT EXISTS master_raw_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN stock_master.master_raw_updated_at IS
    'master_raw 마지막 갱신 시각 (KST). 16:30 KST task 발화 시점 기록. NULL = 미갱신 (마스터 미수집 종목).';

-- GIN 인덱스 (master_raw JSONB 키 검색 최적화)
-- 사용 빈도: scanner 진입 차단 영역 (trht_yn/mang_issu_yn 등) = 단순 키 존재 검사 영역
-- 검토 결과: GIN 인덱스 = JSONB 영역 매수 진입 차단 영역 검색 빈도 영역 정밀화 의무
CREATE INDEX IF NOT EXISTS idx_stock_master_master_raw_gin
    ON stock_master USING gin (master_raw);

COMMENT ON INDEX idx_stock_master_master_raw_gin IS
    '사이클 129 — master_raw JSONB GIN 인덱스. scanner 진입 차단 키 검색 영역 최적화.
     활용 예: master_raw @> ''{"trht_yn":"Y"}'' 거래정지 종목 검색.';

-- master_raw_updated_at 인덱스 (16:30 task 진단 영역)
CREATE INDEX IF NOT EXISTS idx_stock_master_master_raw_updated_at
    ON stock_master (master_raw_updated_at DESC NULLS LAST);

COMMENT ON INDEX idx_stock_master_master_raw_updated_at IS
    '사이클 129 — master_raw 갱신 시각 영역 인덱스. 16:30 task 진단 + UI 영역 최신 갱신 시각 영역 검색.';
