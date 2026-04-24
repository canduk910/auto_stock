-- 시스템 설정 영속화 테이블
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(50) PRIMARY KEY,
    value JSONB DEFAULT 'null'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO system_config (key, value) VALUES ('auto_start', 'true'::jsonb) ON CONFLICT (key) DO NOTHING;
