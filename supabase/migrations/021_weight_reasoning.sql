-- 사이클 1 (2026-05-17) — 자문 시스템 개선: 비중조절 사유 별도 필드.
-- recommended_weight 변경 권고 시 OpenAI 가 별도 사유(`weight_reasoning`) 를 채워
-- UI 자산 배정 카드 amber 영역에 강조 표시한다. 통합 `reasoning` 에 묻혀 있던 비중 사유를 분리.
-- recommended_weight 가 null 이면 weight_reasoning 도 null. 최대 1000자.

ALTER TABLE parameter_recommendations
    ADD COLUMN IF NOT EXISTS weight_reasoning TEXT;

COMMENT ON COLUMN parameter_recommendations.weight_reasoning IS
    '사이클 1 (2026-05-17) — 비중 변경 권고 사유 (별도 필드).
     recommended_weight 가 null 이 아닐 때만 채워짐. 최대 1000자.';
