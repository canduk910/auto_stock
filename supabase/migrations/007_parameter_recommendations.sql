CREATE TABLE parameter_recommendations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    target_date DATE NOT NULL,                 -- 분석 기준일 (당일)
    strategy_id VARCHAR(30) NOT NULL,
    current_params JSONB NOT NULL,             -- 추천 시점의 현재 파라미터
    recommended_params JSONB NOT NULL,         -- 변경 권고 파라미터만 (변경 없으면 빈 객체)
    reasoning TEXT,                            -- 추천 근거 (LLM 출력)
    metrics JSONB,                             -- 분석 통계 (승률/평균손익/거래건수 등)
    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','applied','rejected','partial','expired')),
    applied_params JSONB,                      -- 실제로 적용된 키-값 (partial/applied 시)
    applied_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ
);
CREATE INDEX idx_param_rec_target_date ON parameter_recommendations(target_date DESC);
CREATE INDEX idx_param_rec_status ON parameter_recommendations(status);
CREATE UNIQUE INDEX idx_param_rec_unique_per_day
    ON parameter_recommendations(target_date, strategy_id)
    WHERE status IN ('pending','applied','partial');
