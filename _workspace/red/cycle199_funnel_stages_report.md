# 사이클 199 (E-1) — 일일 리포트 전략별 funnel 단계별 노출 + 0신호 자동 판정 (Red)

## 출처
- `_workspace/ai_advisory_review/2026-07-09_3day_consolidation.md` §6-4 E-1 (최우선)
- `_workspace/domain_consult/cycle198_pattern_strictness_korea.md` 후속검증 #2
  (VCP step5 EMA 정렬 생존 수 노출 = EMA 축소 vs 순수 희소 분리 판정 근거)

## 문제
현재 `metrics["strategy_funnel"]` = `_collect_strategy_funnel()` = coarse 3-count
`{signals, orders, fills}` 뿐 → AI 가 "왜 0신호인지" (패턴 희소 vs 후보 부족) 못 봄.
풍부한 per-step funnel 은 `strategy_funnel_snapshots` DB (사이클 170/175) 에 이미 있음.

## 검증 가능 행위 (관찰성 전용, 매매 무관)
신규 `_collect_strategy_funnel_stages(target_date)` 가 `list_snapshots` 로 읽어
전략별 `steps` + `verdict` 산출 후 metrics dict 에 `strategy_funnel_stages` 키로 추가.
기존 coarse `strategy_funnel` 키는 병존 (회귀 0).

## Red 결과
격리 실행 `test_cycle199_funnel_stages_report.py` (9) + `test_cycle199_metrics_integration.py` (2):
- **11 FAIL / 0 PASS** — 전부 유효한 Red.
  - 단위 9건: `AttributeError: module ... has no attribute '_collect_strategy_funnel_stages'`
  - 통합 2건: metrics dict 에 `strategy_funnel_stages` 키 부재 (assert 실패) —
    단, `strategy_funnel` coarse 키는 이미 존재 확인 (병존 baseline 정확).

인접 회귀 확인 (Green 전, 회귀 0):
- `test_log_analysis_funnel_crosscheck.py` + `test_log_analysis_metrics.py`
  + `test_log_analysis_openai_meta.py` + `test_cycle171_evening_funnel.py` = **35 PASS**.

## 회귀 가드 매핑
| # | 케이스 | 검증 |
|---|--------|------|
| (1) 패턴희소 | `test_bfb_pattern_scarce_verdict` | BFB 폴2→플래그0 → verdict="패턴희소", drop_step.step_no=6("플래그"), final_prepared=0 |
| (2) 후보부족 | `test_donchian_candidate_shortage_verdict` | donchian union→필터→차단0 (이른 단계, 패턴 도달 전) → verdict="후보부족", drop_step.step_no=3 |
| (3) 후보준비완료 | `test_final_prepared_ready_verdict` | VB final_prepared=30>0 → verdict="후보준비완료" (intraday 대기) |
| (4) VCP step5 노출 | `test_vcp_ema_step5_exposed` | steps 에 step5(EMA 정렬) survived_count==2 포함 + drop_step=Pullback(7) → 패턴희소 |
| (5) graceful | `test_graceful_on_list_snapshots_exception` / `test_graceful_on_empty_snapshots` | 예외/빈 → {} 반환 |
| (6) metrics+병존 | `test_metrics_includes_funnel_stages_and_coarse_coexist` | metrics 에 strategy_funnel_stages(verdict) + strategy_funnel(coarse) 병존 + `test_metrics_funnel_stages_receives_target_date` (target_date 인자 주입) |
| (7) step99 제외 | `test_step99_excluded_from_pipeline` | step99 → steps/final_prepared/peak_survived 배제 |
| 보강 | `test_steps_sorted_and_final_is_max_step` / `test_no_steps_verdict` | 정렬 + final=최대 step / steps 없음 → "기록없음" |

## 의미 전환
없음 (신규 함수 + 신규 metrics 키. 기존 테스트 수정 0).

## backend-dev Green 지시

### 1. import 추가 (`src/engine/log_analysis_engine.py` L29 부근)
```python
from src.db.strategy_funnel import list_snapshots
```

### 2. 신규 함수
```python
# 패턴 단계 키워드 (verdict 판정용). drop_step.step_name 이 이 중 하나를 포함하면
# "패턴희소", 아니면 (유니버스/필터/차단 등 이른 단계) "후보부족".
_PATTERN_STEP_KEYWORDS = (
    "신고가", "돌파", "폴", "플래그", "베이스", "Pullback", "수축", "검출", "EMA", "정렬",
)


async def _collect_strategy_funnel_stages(target_date: date) -> dict[str, dict]:
    """전략별 per-step funnel + 0신호 자동 판정 (E-1, 사이클 199).

    strategy_funnel_snapshots (DB) 를 읽어 전략별 단계별 생존 수 + verdict 산출.
    순수 관찰성 — 매매 무관. 실패/빈 → {} graceful (리포트 무중단, 사이클 88 패턴).
    """
    try:
        rows = await list_snapshots(target_date=target_date)
    except Exception:
        logger.exception("[funnel_stages] list_snapshots 실패 — graceful {}")
        return {}
    if not rows:
        return {}

    # strategy_id 별 그룹핑 (step_no != 99 만 파이프라인)
    by_sid: dict[str, list[dict]] = {}
    for row in rows:
        sid = row.get("strategy_id") or "unknown"
        by_sid.setdefault(sid, []).append(row)

    result: dict[str, dict] = {}
    for sid, sid_rows in by_sid.items():
        pipeline = sorted(
            (r for r in sid_rows if int(r.get("step_no", 0)) != 99),
            key=lambda r: int(r.get("step_no", 0)),
        )
        steps = [
            {
                "step_no": int(r.get("step_no", 0)),
                "step_name": r.get("step_name") or "",
                "survived_count": int(r.get("survived_count", 0)),
                "excluded_count": int(r.get("excluded_count", 0)),
            }
            for r in pipeline
        ]

        if not steps:
            result[sid] = {
                "steps": [], "peak_survived": 0, "final_prepared": 0,
                "drop_step": None, "verdict": "기록없음",
            }
            continue

        peak_survived = max(s["survived_count"] for s in steps)
        final_prepared = steps[-1]["survived_count"]  # 최대 step_no(≠99) survived

        # drop_step = 직전 step>0 → 현재 step==0 으로 처음 떨어지는 step
        drop_step = None
        for i in range(1, len(steps)):
            if steps[i - 1]["survived_count"] > 0 and steps[i]["survived_count"] == 0:
                drop_step = {"step_no": steps[i]["step_no"], "step_name": steps[i]["step_name"]}
                break

        # verdict
        if final_prepared > 0:
            verdict = "후보준비완료"
        elif drop_step is not None:
            if any(kw in drop_step["step_name"] for kw in _PATTERN_STEP_KEYWORDS):
                verdict = "패턴희소"
            else:
                verdict = "후보부족"
        else:
            verdict = "미상"

        result[sid] = {
            "steps": steps,
            "peak_survived": peak_survived,
            "final_prepared": final_prepared,
            "drop_step": drop_step,
            "verdict": verdict,
        }
    return result
```

### 3. 배선 (`generate_daily_log_report`, L416 부근)
`strategy_funnel = await _collect_strategy_funnel()` 아래에:
```python
strategy_funnel_stages = await _collect_strategy_funnel_stages(target_date)
```
그리고 L419 metrics dict 에 키 추가 (기존 `strategy_funnel` 병존 불변):
```python
    metrics = {
        "target_date": target_date.isoformat(),
        "logs": log_metrics,
        "trades": trade_metrics,
        "api_metrics": api_metrics,
        "strategy_funnel": strategy_funnel,           # 병존 (coarse, 불변)
        "strategy_funnel_stages": strategy_funnel_stages,  # 신규 (E-1)
        "next_day_clear": next_day_clear_metrics,
    }
```

### 주의
- `final_prepared = steps[-1]["survived_count"]` — pipeline 이 step_no ASC 정렬이므로
  `steps[-1]` = 최대 step_no(≠99). (테스트 (7) step99 제외 + 보강 정렬 케이스가 가드.)
- 케이스 (4) 는 verdict 판정을 drop_step 만으로 결정 (final_prepared==0) — step6 베이스2 는
  survived>0 이라 drop 아님, step7 Pullback0 이 첫 drop → "Pullback" 키워드 매칭 → 패턴희소.
- 케이스 (2) donchian step3 차단0 은 "1단계 진입 차단 통과" step_name → 패턴 키워드 미포함
  → "후보부족". ("차단"은 `_PATTERN_STEP_KEYWORDS` 에 없음 — 확인.)
