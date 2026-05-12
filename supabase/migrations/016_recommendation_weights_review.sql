-- Phase J4 (2026-05-12) — AI자문 고도화: 전략별 자산배정 + 로직/파라미터 자유 텍스트 자문.
-- 자동 적용은 없음 (운영자 수동 apply).

ALTER TABLE parameter_recommendations
    ADD COLUMN IF NOT EXISTS recommended_weight NUMERIC,
    ADD COLUMN IF NOT EXISTS code_review_notes TEXT,
    ADD COLUMN IF NOT EXISTS applied_weight NUMERIC;

COMMENT ON COLUMN parameter_recommendations.recommended_weight IS
    'AI가 추천한 strategy weight (0~1). null이면 변경 권고 없음.';
COMMENT ON COLUMN parameter_recommendations.code_review_notes IS
    '로직/파라미터 추가·삭제 자유 텍스트 자문. 최대 2000자. 자동 적용 없음 — 운영자 수동 검토.';
COMMENT ON COLUMN parameter_recommendations.applied_weight IS
    '사용자가 apply할 때 실제 적용된 weight (트래킹용).';
