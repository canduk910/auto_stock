-- 사이클 23 (2026-05-20) — parameter_recommendations.status 에 'applied_auto' 추가
-- AI 자문 자동 적용 (P3-1) 전용 status. 운영자 수동 'applied' 와 분리하여 추적성 확보.

ALTER TABLE parameter_recommendations
  DROP CONSTRAINT IF EXISTS parameter_recommendations_status_check;

ALTER TABLE parameter_recommendations
  ADD CONSTRAINT parameter_recommendations_status_check
  CHECK (status IN ('pending', 'applied', 'partial', 'rejected', 'expired', 'applied_auto'));
