-- 사이클 145 (2026-06-16) — strategy_funnel_snapshots 중복 row 영구 제거 + UPSERT 전환
--
-- 결함 3 (사용자 verbatim "단계가 늘어난 것처럼 보여"):
-- - 6/15 BFB step_no=1 = 8 row / donchian step_no=1~8 = 5~8 row 영역 영구 영속
-- - 기존 UNIQUE = (target_date, strategy_id, step_no, snapshot_at) 영역 영구 영속
-- - snapshot_at 영역 영구 영속 매 trigger 마다 달라서 중복 INSERT 가능
-- - UI 영역 영구 영속 모든 row 표시 → 같은 단계가 여러 번 보임 영역 영구 영속
--
-- 시정 (사용자 결정 Q1=C):
-- 1. 기존 중복 row 영역 영구 영속 = 최신 snapshot_at 만 유지 + 나머지 DELETE
-- 2. UNIQUE constraint 변경: (target_date, strategy_id, step_no, snapshot_at)
--    → (target_date, strategy_id, step_no) (snapshot_at 키 폐기)
-- 3. insert_snapshot() 영역 영구 영속 UPSERT 전환 (사이클 145 코드 시정 영역)
--
-- 매매 안전성 무영향 (진단/추적 영역 한정, scanner 매수 진입 전 영역).

-- Step 1: 중복 row 정리 — 같은 (target_date, strategy_id, step_no) 그룹 영역에서
--         최신 snapshot_at 영역 영구 영속 1건만 유지 + 나머지 영구 DELETE.
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY target_date, strategy_id, step_no
            ORDER BY snapshot_at DESC
        ) AS rn
    FROM strategy_funnel_snapshots
)
DELETE FROM strategy_funnel_snapshots
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- Step 2: 기존 UNIQUE constraint 영구 폐기.
ALTER TABLE strategy_funnel_snapshots
    DROP CONSTRAINT IF EXISTS strategy_funnel_snapshots_target_date_strategy_id_step_no_s_key;

-- Step 3: 신규 UNIQUE constraint 영구 영속 (snapshot_at 키 폐기, 사이클 145 영구 영속).
ALTER TABLE strategy_funnel_snapshots
    ADD CONSTRAINT strategy_funnel_snapshots_target_date_strategy_id_step_no_key
    UNIQUE (target_date, strategy_id, step_no);

COMMENT ON CONSTRAINT strategy_funnel_snapshots_target_date_strategy_id_step_no_key
    ON strategy_funnel_snapshots IS
    '사이클 145 — UPSERT 전환 영구 영속. snapshot_at 키 폐기 (중복 row 영구 차단).';
