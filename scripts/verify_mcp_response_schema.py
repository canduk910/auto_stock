"""의문점 #2 사전 확인 — 외부 MCP 서버 응답 키 구조 검증.

Phase 5 보고에서 발견: `BacktestEngine._extract_metrics()` 가
`data.get("metrics") or {}` 만 반환 → `BacktestMetrics.model_validate()` 에
직접 전달. 외부 서버 응답이 stock-manager 패턴(metrics.basic/risk/trading 중첩)이면
모든 필드 None 처리되어 백테스트 결과 무용.

본 스크립트는 외부 서버에 직접 호출해서:
1. tools/list — 사용 가능 도구 확인
2. list_presets_tool — preset 목록
3. run_preset_backtest_tool + get_backtest_result_tool — 실제 응답 dict raw 출력
4. 응답 키 구조가 평탄(8 키) vs 중첩(basic/risk/trading) 판별

실행:
    KIS_MCP_ENABLED=true python scripts/verify_mcp_response_schema.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 환경변수 강제 (메인 .env 와 격리)
os.environ.setdefault("KIS_MCP_ENABLED", "true")
os.environ.setdefault("KIS_MCP_URL", "http://43.202.187.5:3846/mcp")


async def main() -> None:
    from src.services.mcp_client import get_mcp_client

    client = get_mcp_client()

    # ----------------------------------------------------------------
    # 1. tools/list
    # ----------------------------------------------------------------
    print("=" * 70)
    print("[1] tools/list — 외부 서버 도구 목록")
    print("=" * 70)
    tools = await client.list_tools()
    if isinstance(tools, list):
        for t in tools:
            name = t.get("name") if isinstance(t, dict) else str(t)
            print(f"  - {name}")
    else:
        print(json.dumps(tools, ensure_ascii=False, indent=2)[:1500])
    print()

    # ----------------------------------------------------------------
    # 2. list_presets_tool
    # ----------------------------------------------------------------
    print("=" * 70)
    print("[2] list_presets_tool — 사용 가능 preset 목록")
    print("=" * 70)
    try:
        presets_resp = await client.call_tool("list_presets_tool", {})
        print(json.dumps(presets_resp, ensure_ascii=False, indent=2)[:3000])
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()

    # ----------------------------------------------------------------
    # 3. run_preset_backtest_tool — 단발 실행
    # ----------------------------------------------------------------
    # stock-manager 패턴: preset id = "momentum_breakout" or "sma_crossover"
    preset_candidates = [
        "sma_crossover",
        "momentum",
        "momentum_breakout",
        "donchian_swing",
    ]
    symbol = "005930"  # 삼성전자
    initial_capital = 10_000_000

    print("=" * 70)
    print("[3] run_preset_backtest_tool — 단발 실제 백테스트 호출")
    print(f"    candidates={preset_candidates}, symbol={symbol}")
    print("=" * 70)

    job_id: str | None = None
    used_preset: str | None = None
    for preset in preset_candidates:
        try:
            print(f"  → preset='{preset}' 시도...")
            run_resp = await client.call_tool(
                "run_preset_backtest_tool",
                {
                    "strategy_id": preset,
                    "symbols": [symbol],
                    "initial_capital": initial_capital,
                    "start_date": "2026-02-01",
                    "end_date": "2026-04-30",
                },
            )
            # job_id 추출
            data = run_resp.get("data") if isinstance(run_resp, dict) and "data" in run_resp else run_resp
            job_id = data.get("job_id") if isinstance(data, dict) else None
            if job_id:
                used_preset = preset
                print(f"  ✓ job_id 받음: {job_id} (preset={preset})")
                break
            else:
                print(f"  ✗ job_id 없음. 응답: {json.dumps(run_resp, ensure_ascii=False)[:500]}")
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {e}")

    if not job_id:
        print("\n  ❌ 모든 preset 실패. 사용 가능한 preset id 를 [2] 응답에서 직접 확인하세요.")
        await client.close()
        return

    # ----------------------------------------------------------------
    # 4. get_backtest_result_tool (wait=True) — 응답 dict raw 출력
    # ----------------------------------------------------------------
    print()
    print("=" * 70)
    print(f"[4] get_backtest_result_tool — wait=True (외부 서버 폴링)")
    print(f"    job_id={job_id}, preset={used_preset}")
    print("=" * 70)
    try:
        result_resp = await client.call_tool(
            "get_backtest_result_tool",
            {"job_id": job_id, "wait": True, "timeout": 120},
        )
        print("RAW 응답:")
        print(json.dumps(result_resp, ensure_ascii=False, indent=2)[:5000])

        # ----------------------------------------------------------------
        # 5. 응답 구조 분석
        # ----------------------------------------------------------------
        print()
        print("=" * 70)
        print("[5] 응답 구조 분석")
        print("=" * 70)

        # Phase 6 unwrap 적용 후 result_resp 자체가 unwrap 된 data (또는 그 안의 dict)
        data = result_resp if isinstance(result_resp, dict) else {}
        if not isinstance(data, dict):
            print("  ❌ data 가 dict 아님")
        else:
            # 실측: metrics 가 한 단계 더 안쪽(data.result.metrics)에 있음
            metrics = data.get("metrics") or {}
            if not metrics and isinstance(data.get("result"), dict):
                metrics = data["result"].get("metrics") or {}
                print("  (metrics 경로: data.result.metrics — Phase 6 평탄화 적용 위치)")
            print(f"  metrics 키 타입: {type(metrics).__name__}")
            print(f"  metrics 키 목록: {sorted(metrics.keys()) if isinstance(metrics, dict) else 'N/A'}")

            # 중첩 vs 평탄 판별
            if isinstance(metrics, dict):
                nested_keys = ("basic", "risk", "trading")
                flat_keys = (
                    "total_return_pct",
                    "cagr",
                    "sharpe_ratio",
                    "max_drawdown",
                    "win_rate",
                    "profit_factor",
                    "total_trades",
                )
                is_nested = any(k in metrics for k in nested_keys)
                is_flat = any(k in metrics for k in flat_keys)

                print()
                if is_nested:
                    print("  ⚠️  중첩 구조 감지 (basic/risk/trading) — 평탄화 필요!")
                    print("     `_extract_metrics()` 보강 필수")
                    for sub in nested_keys:
                        if sub in metrics:
                            print(f"     metrics.{sub} 키: {sorted(metrics[sub].keys()) if isinstance(metrics[sub], dict) else 'N/A'}")
                elif is_flat:
                    print("  ✓ 평탄 구조 감지 — 현재 `_extract_metrics()` 그대로 OK")
                else:
                    print("  ❌ 알 수 없는 구조 — 위 RAW 응답 확인 필요")

                # MDD 부호 확인
                mdd = None
                if isinstance(metrics, dict):
                    if "max_drawdown" in metrics:
                        mdd = metrics["max_drawdown"]
                    elif "basic" in metrics and isinstance(metrics["basic"], dict):
                        mdd = metrics["basic"].get("max_drawdown")
                if mdd is not None:
                    print(f"  MDD 부호: {mdd} ({'양수=절대값' if mdd > 0 else '음수=손실 누적'})")

            # ----------------------------------------------------------------
            # 6. Phase 6 통합 검증 — BacktestEngine 평탄화 결과 직접 출력
            # ----------------------------------------------------------------
            print()
            print("=" * 70)
            print("[6] Phase 6 _extract_metrics + BacktestMetrics 평탄화 결과")
            print("=" * 70)
            try:
                from src.engine.backtest_engine import _extract_metrics, _normalize_metrics
                from src.models.backtest import BacktestMetrics

                # _extract_metrics 는 unwrap 전 응답 dict 를 받지만,
                # 이미 unwrap 된 result_resp 를 흉내내기 위해 {"metrics": ..., "result": ...} 직접 전달.
                flat_metrics = _extract_metrics(result_resp)
                print(f"  평탄화 metrics dict: {json.dumps(flat_metrics, ensure_ascii=False, indent=2)}")
                bm = BacktestMetrics.model_validate(flat_metrics)
                print()
                print("  BacktestMetrics 8 키 채집 결과:")
                print(f"    total_return_pct = {bm.total_return_pct}")
                print(f"    cagr             = {bm.cagr}")
                print(f"    sharpe_ratio     = {bm.sharpe_ratio}")
                print(f"    sortino_ratio    = {bm.sortino_ratio}")
                print(f"    max_drawdown     = {bm.max_drawdown}")
                print(f"    win_rate         = {bm.win_rate}")
                print(f"    profit_factor    = {bm.profit_factor}")
                print(f"    total_trades     = {bm.total_trades}")
                filled = sum(
                    1 for v in
                    (bm.total_return_pct, bm.cagr, bm.sharpe_ratio, bm.sortino_ratio,
                     bm.max_drawdown, bm.win_rate, bm.profit_factor, bm.total_trades)
                    if v is not None
                )
                print(f"  ✓ {filled}/8 키 채워짐 (Phase 6 평탄화 정상 동작 검증)")
            except Exception as e:
                print(f"  ❌ {type(e).__name__}: {e}")

    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")

    # ----------------------------------------------------------------
    # 7. donchian_swing YAML 외부 호환성 검증 (Phase 6 결함 B)
    # ----------------------------------------------------------------
    print()
    print("=" * 70)
    print("[7] donchian_swing YAML → validate_yaml_tool 외부 서버 검증")
    print("=" * 70)
    try:
        from src.engine.backtest_yaml import build_yaml

        donchian_yaml = build_yaml("donchian_swing", {})
        print("  생성된 YAML (요약):")
        # 첫 20 라인만 미리보기
        preview = "\n    ".join(donchian_yaml.split("\n")[:20])
        print(f"    {preview}")
        print()
        validate_resp = await client.call_tool(
            "validate_yaml_tool", {"yaml_content": donchian_yaml}
        )
        print(f"  validate_yaml_tool 응답: {json.dumps(validate_resp, ensure_ascii=False, indent=2)[:600]}")
        # _extract_validate_ok 사용
        from src.engine.backtest_engine import _extract_validate_ok, _extract_validate_errors
        valid = _extract_validate_ok(validate_resp)
        errors = _extract_validate_errors(validate_resp)
        if valid:
            print("  ✓ donchian_swing YAML → 외부 서버 validate_yaml_tool 통과 — (a) 분류 유지")
        else:
            print(f"  ⚠️ donchian_swing YAML 거부 → (b) 폴백 다운그레이드 검토 필요")
            print(f"     errors: {errors}")
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
