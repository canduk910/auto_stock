"""cycle414 Red — 범위 가드: 전략 진행상황 화면은 **읽기 전용 화면 + 읽기 전용 라우트 1개**다(명세 §3.1 · §8.1 R7).

| # | 계약 |
|---|---|
| S1 | 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`) + `scheduler.py` 내용 sha 그대로 |
| S2 | 매매 판단·라우트가 읽는 엔진 이웃 그대로 — 전략 파일 전부 · `strategy_base.py` · `position_exit_lines.py` · `funnel_capture.py` · `etf_trend_core.py` · `tick_volume.py` · `market_unit.py` · `daily_emit_cap.py` · `boot_manager.py` · `routes/trading.py` · `routes/balance.py`(exit-lines G1) |
| S3 | `src/**/*.py` 파일 집합 그대로(새 `.py` 0 — 라우트는 `src/routes/strategies.py` 안) |
| S4 | 동시 진행 cycle413(거래일지 화면, `../auto_stock_tj2`)이 고치는 파일 무접촉 — `src/routes/history.py` · `frontend/src/pages/History.tsx` · `frontend/src/api/history.ts` · `frontend/src/components/TradeHistoryGrid.tsx` |
| S5 | 마이그레이션 파일 수 그대로(가산형도 0 — 이 사이클은 DB 를 건드리지 않는다) |

내용 sha 다 — `ast.dump` 는 3.12/3.13 출력이 달라 핀하지 않고, 스캔은 `Path.rglob`(미추적 새 파일까지 본다).

⚠️ **이 백엔드 가드는 프론트 파일(`frontend/src/pages/History.tsx` 등 S4)을 읽는다** — 프론트 전용 사이클의
검증 목록(`grep -rl 'frontend/' tests/unit`)에 들어간다(가드 설계 금기 · cycle256 g251_2/3).

⚠️ **사이클 한정 — cycle414 병합 후 삭제.** 기준 = 브랜치 `feat/strategy-monitors` 의 `434792d8`(main `1b3c95a1`
위 명세 커밋). 병합 전에 main 이 이 파일들을 정당하게 바꾸면(예: cycle413 이 먼저 병합되어 S4 파일이 바뀜)
해당 항목을 지운다(고아 가드 방지). dict 이름을 `*_CONTENT_SHA` 로 짓지 않는다(`test_cycle223g3` 관례 —
8영역 승인 핀 명부와 섞이지 않게).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_C414_EIGHT_AREAS = {
    "src/engine/risk.py": "a2187b8270446379988d24dfbe39b902d6ab37b112d4b6ce7330ee171434e222",
    "src/engine/order_engine.py": "08c479841352fb579f767c109de3e8f901d1c27bdce705b39b5ba6556fc0b3e1",
    "src/engine/session.py": "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/scanner.py": "611568c078c6f3779344e05b3dfa308c792c64e1c5e02480de6313200282f54f",
    "src/engine/strategy_registry.py": "3b6366c3cdb6e83907428435b95611880f1b8223e572c361a1cad2d00b13a067",
    "src/api/order.py": "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/engine/scheduler.py": "f53d41a11fe162f80e113c6ff48cf6d235581769be7979499c5782ff11d49646",
    "src/realtime/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py": "e1a484e9ac82d43f0fa85cba693ea5a206ecfbae1076dfee0f4e6bf6d4f2a2d4",
    "src/realtime/websocket.py": "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py": "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    "src/auth/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py": "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py": "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
}

_C414_ENGINE_NEIGHBORS = {
    "src/engine/strategy_base.py": "f4c2c5619fb3b2f70fa0b4faab0fd38d55c83d0b9370c986c97de4f564430822",
    "src/engine/position_exit_lines.py": "a760e3016f19e833280410e12cfa0357828fc468735985b647b31005e79700cf",
    "src/engine/funnel_capture.py": "7884e318c4c46fffd70d03863958a65a7add782abfcb7596f81a764f8b99fef5",
    "src/engine/etf_trend_core.py": "c22b9f90e2934af3edcae50544ea752629422c12b675934afe4b46221016699e",
    "src/engine/tick_volume.py": "457bd43d80e3cb46c64ae33cb6c1c5d0c12df54246c383bb3d81292d013ef267",
    "src/engine/market_unit.py": "c181cee7d6b9eb8e1534facc0bcc3b3ac2d6ee29a375fcfbaa58ba2a934f9db2",
    "src/engine/daily_emit_cap.py": "8c366b7e923829ebc756a86269bc0c9d91caa323df4abede2282c38f2f203103",
    "src/engine/boot_manager.py": "b595f0c1dadc924baf9c50c2775290d9326624b0ade697fb478df31fa8c28cf4",
    "src/routes/trading.py": "c3274c12323760a3939e6189ce5fd333118f6d188c35905238885ad04312b1f5",
    "src/routes/balance.py": "c22796223f2177a412484a6897044a14e2dc6178fd115dc31070bec2cba68346",
    "src/engine/strategies/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py": "879d85e779f9594ffbd9da93ce3ec41986f02abc78cc751cb22d022c20b0f298",
    "src/engine/strategies/donchian_swing.py": "c8c7172e8e33fa164e2d11c30641562e8ab2d6474e7a84f241320bf2fbab58f3",
    "src/engine/strategies/etf_trend.py": "31776865ec1c206df7f61020966fa2e21be17e39939f1c9e443557834f54c318",
    "src/engine/strategies/kojiro.py": "1d04d3d6dc0c72ff6c7e7d930be9da63f2408fb709e889906a133a9c5480fc74",
    "src/engine/strategies/long_tail_volatility.py": "44f7f103b3c714522b09da7de5a4de2ec0423ffc2a3032f43540c4c70943778d",
    "src/engine/strategies/momentum.py": "686171e29ac365e8ea66f7659f2e02962f58bbac9d9ab9545095c7b3544bb403",
    "src/engine/strategies/vcp_breakout.py": "9a53b5b6d9a5dcf96966b168291640df6b258daf059f03e4cdd5b12324589706",
    "src/engine/strategies/volatility_breakout.py": "c07e7298743496129601e79598b799472242d2f02b60eb2f92217b6bed1ee1b4",
}

#: 동시 진행 cycle413 소유 — 이 브랜치는 한 글자도 바꾸지 않는다(병합 충돌·덮어쓰기 차단).
_C414_CYCLE413_OWNED = {
    "src/routes/history.py": "229d0457850790ae6dcb1d55c31ad6064f6c6b4846bc12624f7ff9af56310a5f",
    "frontend/src/pages/History.tsx": "d2edfb281fb14ba64b5f6456d63d416bae88097dce23aeb391ea54856a04a043",
    "frontend/src/api/history.ts": "258477914298c236f30962012d18e21c3e84cf3d4c73bf8a5be4e588cd29d438",
    "frontend/src/components/TradeHistoryGrid.tsx": "b506fb10adda1aad439f95fd632bfe7786a2347624b0bd803d294e0c61684db3",
}

_SRC_PY_COUNT = 182
_SRC_PY_SET_SHA = "3d79f84854db3ce2f48f70502b9099a441fbefb9000e5766df472d4d0b2d1d37"
_MIGRATION_COUNT = 47


def _sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


@pytest.mark.parametrize("rel", sorted(_C414_EIGHT_AREAS))
def test_s1_eight_areas_and_scheduler_unchanged(rel):
    assert _sha(rel) == _C414_EIGHT_AREAS[rel], f"{rel} — cycle414 는 8영역·scheduler.py 0줄(읽기 전용 화면)"


@pytest.mark.parametrize("rel", sorted(_C414_ENGINE_NEIGHBORS))
def test_s2_engine_neighbors_unchanged(rel):
    assert _sha(rel) == _C414_ENGINE_NEIGHBORS[rel], (
        f"{rel} — 라우트는 `getattr` 로 읽기만 한다. 전략에 getter 가 필요하면 팀장이 이 핀을 다시 정한다(명세 C5)")


def test_s3_no_new_src_py():
    files = sorted(
        p.relative_to(_ROOT).as_posix() for p in (_ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts
    )
    assert len(files) == _SRC_PY_COUNT, f"src/*.py {len(files)}개 — 라우트는 기존 `src/routes/strategies.py` 안에 둔다"
    assert hashlib.sha256("\n".join(files).encode()).hexdigest() == _SRC_PY_SET_SHA


@pytest.mark.parametrize("rel", sorted(_C414_CYCLE413_OWNED))
def test_s4_cycle413_owned_files_untouched(rel):
    assert _sha(rel) == _C414_CYCLE413_OWNED[rel], f"{rel} 는 cycle413(거래일지 화면) 몫 — 이 브랜치에서 고치지 않는다"


def test_s5_no_migration_added():
    files = sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
    assert len(files) == _MIGRATION_COUNT, "cycle414 는 마이그레이션 0(읽기 전용)"
