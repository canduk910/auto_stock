-- 023_cash_usage_ratio_range.sql
-- 사이클 2 (2026-05-17): cash_usage_ratio 범위 [0.5, 1.0] → [0.0, 1.0] 확장
--
-- 배경: 매크로 레짐 자동 조정 (auto_regime_adjust=true) 이 활성화되면
-- defensive 레짐 (cash_min=75) 에서 cash_usage_ratio = 0.25 같은 0.5 미만 값이
-- 정상 입력된다. 기존 system_config.set_cash_usage_ratio 의 MIN=0.5 가드는
-- 코드 레벨에서만 강제됐고 DB CHECK 제약은 없었다.
--
-- 본 마이그는 실제 스키마 변경 0건. 코드 (src/db/system_config.py) 의
-- _CASH_USAGE_RATIO_MIN 상수가 0.0 으로 변경됐다는 사실을 COMMENT 로 기록만 한다.
-- 기존 system_config row 영향: 운영 0.5 미만 값 존재하지 않아 무해.
--
-- 적용: 마이그 022 직후 실행. 운영 활성화와 무관하게 안전.

COMMENT ON TABLE system_config IS
    'KEY-VALUE 설정. cash_usage_ratio 범위 [0.0, 1.0] (사이클 2, 2026-05-17 확장 — defensive 레짐 자동 조정 수용). auto_regime_adjust 추가 (기본 true).';
