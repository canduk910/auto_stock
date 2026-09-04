-- cycle249: daily_log_reports 외부(Claude Code 클라우드 루틴) 분석 컬럼 추가
-- 병행 기간 동안 20:10 OpenAI 경로(summary/findings/metrics/model + 토큰 5)와
-- 20:20 클라우드 루틴 결과(ext_*)가 같은 행에 공존한다. 전부 NULL 허용 —
-- 기존 행(과거 전 영업일)은 ext_* 없이 자연 보존된다. `IF NOT EXISTS` 는
-- deploy.yml 이 매 push 마다 전 마이그레이션을 재적용하기 때문에 필수(031 선례).

ALTER TABLE daily_log_reports
    ADD COLUMN IF NOT EXISTS ext_provider TEXT NULL,
    ADD COLUMN IF NOT EXISTS ext_model TEXT NULL,
    ADD COLUMN IF NOT EXISTS ext_summary TEXT NULL,
    ADD COLUMN IF NOT EXISTS ext_findings JSONB NULL,
    ADD COLUMN IF NOT EXISTS ext_report_md TEXT NULL,
    ADD COLUMN IF NOT EXISTS ext_created_at TIMESTAMPTZ NULL;
