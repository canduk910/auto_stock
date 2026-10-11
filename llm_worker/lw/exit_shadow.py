"""cycle446 — 청산 AI 섀도 오케스트레이터. http·db·features·prompt·targets·bars 를 엮는다.

**매매 행위 0** — 여기서 만든 어떤 값도 backend 로 되돌아가지 않는다(워커는 backend 를
GET 만 한다). 평가 1건 실패가 다른 포지션 평가를 막지 않는다(종목 단위 예외 격리).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from lw import bars as bars_mod
from lw import features as features_mod
from lw import outcome as outcome_mod
from lw import prompt as prompt_mod
from lw import targets as targets_mod
from lw.config import (
    BAR_FETCH_DAYS,
    CALL_TIMEOUT_SECS,
    DAILY_CALL_CAP,
    EXIT_AI_MODEL_DEFAULT,
    G0_PATH,
    G1_PATH,
    MARKET_PROXY_TICKER,
    MAX_ATTEMPTS_PER_DAY,
    MAX_COMPLETION_TOKENS,
)
from lw.http import FetchError, fetch

KST = timezone(timedelta(hours=9))
log = logging.getLogger(__name__)


def _parse_date(value) -> "date | None":
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def _as_row_map(r: dict) -> dict:
    """DB 행(open_price·…) → `llm_features.compute_technicals` 이 기대하는 KIS 키."""
    return {
        "stck_oprc": r.get("open_price"), "stck_hgpr": r.get("high_price"),
        "stck_lwpr": r.get("low_price"), "stck_clpr": r.get("close_price"),
        "acml_vol": r.get("volume"),
    }


class Runner:
    """하루 1회 회전(08:15/08:35/08:55 — 호출자는 `schedule.py`)."""

    def __init__(self, *, client, db, openai_client, model=None, mode="shadow", now=None):
        self.client = client
        self.db = db
        self.openai = openai_client
        self.model = model or EXIT_AI_MODEL_DEFAULT
        self.mode = str(mode or "shadow").strip().lower()
        self._now = now
        self._calls_today = 0
        self._calls_day = None

    def _clock(self) -> datetime:
        return self._now() if self._now is not None else datetime.now(KST)

    def _call_count_today(self, now: datetime) -> int:
        if self._calls_day != now.date():
            return 0
        return self._calls_today

    def _bump_call_count(self, now: datetime) -> None:
        if self._calls_day != now.date():
            self._calls_day = now.date()
            self._calls_today = 0
        self._calls_today += 1

    async def run_once(self) -> dict:
        now = self._clock()
        run_row = {
            "run_date": now.date(), "bar_date": None, "started_at": now, "finished_at": None,
            "status": "unknown", "n_targets": 0, "n_ok": 0, "n_failed": 0, "n_skipped": 0,
            "n_next_open_filled": 0, "n_outcome_filled": 0, "model": self.model,
            "prompt_version": None, "note": None,
        }

        if self.mode == "off":
            run_row.update(status="disabled", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        try:
            g0 = await fetch(self.client, G0_PATH)
        except FetchError as exc:
            run_row.update(status="engine_not_running", note=f"g0_error:{exc}", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        if not isinstance(g0, dict) or not g0.get("running") or g0.get("phase") == "idle":
            run_row.update(status="engine_not_running", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        try:
            g1 = await fetch(self.client, G1_PATH)
        except FetchError as exc:
            run_row.update(status="g1_failed", note=str(exc), finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        # 사후 채움 먼저(설계 §3.2 ②) — 다음 단계(대상 선정)의 실패와 무관하게 돈다.
        try:
            n_next_open = await outcome_mod.fill_next_open(self.db, today=now.date())
        except Exception as exc:  # pragma: no cover — never-raise
            log.warning("[exit_ai_next_open_error] %s", exc)
            n_next_open = 0
        try:
            held_keys = {
                (str(it.get("strategy_id")), str(it.get("ticker")),
                 _parse_date(it.get("buy_date")), str(it.get("order_no") or ""))
                for it in ((g1 or {}).get("items") or []) if isinstance(it, dict)
            }
            n_outcome = await outcome_mod.fill_outcomes(self.db, today=now.date(), held_keys=held_keys)
        except Exception as exc:  # pragma: no cover — never-raise
            log.warning("[exit_ai_outcome_error] %s", exc)
            n_outcome = 0
        run_row["n_next_open_filled"] = n_next_open
        run_row["n_outcome_filled"] = n_outcome

        try:
            proxy_rows = await self.db.fetch_recent_daily(MARKET_PROXY_TICKER, 10)
        except Exception as exc:
            run_row.update(status="g1_failed", note=f"proxy_error:{exc}", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        bar_date = bars_mod.determine_bar_date(proxy_rows, today=now.date())
        if bar_date is None:
            run_row.update(status="no_targets", note="bar_date_unresolved", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row
        run_row["bar_date"] = bar_date

        items = (g1 or {}).get("items") or []
        selected = targets_mod.select_targets(items, bar_date=bar_date)
        run_row["n_targets"] = len(selected)
        if not selected:
            run_row.update(status="no_targets", finished_at=self._clock())
            await self.db.upsert_run(run_row)
            return run_row

        strategies_raw = (g0 or {}).get("strategies")
        strategies: dict = {}
        if isinstance(strategies_raw, dict):
            strategies = strategies_raw
        elif isinstance(strategies_raw, list):
            for s in strategies_raw:
                if isinstance(s, dict):
                    key = s.get("strategy_id") or s.get("id")
                    if key:
                        strategies[key] = s

        n_ok = n_failed = n_skipped = 0
        prompt_version_used = None
        for item in selected:
            try:
                result, used_version = await self._evaluate_one(
                    item, bar_date=bar_date, now=now, strategies=strategies,
                )
            except Exception as exc:  # pragma: no cover — 종목 단위 예외 격리
                log.warning("[exit_ai_target_error] ticker=%s err=%s", item.get("ticker"), exc)
                result, used_version = "failed", None
            if used_version:
                prompt_version_used = used_version
            if result == "ok":
                n_ok += 1
            elif result == "skipped":
                n_skipped += 1
            else:
                n_failed += 1

        status = "done" if n_failed == 0 and n_skipped == 0 else "partial"
        run_row.update(status=status, n_ok=n_ok, n_failed=n_failed, n_skipped=n_skipped,
                       prompt_version=prompt_version_used, finished_at=self._clock())
        await self.db.upsert_run(run_row)
        return run_row

    async def _evaluate_one(self, item: dict, *, bar_date, now, strategies) -> tuple:
        strategy_id = str(item.get("strategy_id"))
        ticker = str(item.get("ticker"))
        buy_date = _parse_date(item.get("buy_date"))
        buy_order_no = str(item.get("order_no") or "")

        existing = await self.db.get_existing_evaluation(
            bar_date=bar_date, strategy_id=strategy_id, ticker=ticker,
            buy_date=buy_date, buy_order_no=buy_order_no,
        )
        if existing is not None:
            if existing["result"] == "ok":
                return "ok", None
            if existing["attempts"] >= MAX_ATTEMPTS_PER_DAY:
                return "skipped", None
        attempts = (existing["attempts"] + 1) if existing is not None else 1

        base_row = {
            "bar_date": bar_date, "act_date": now.date(), "strategy_id": strategy_id,
            "ticker": ticker, "buy_date": buy_date, "buy_order_no": buy_order_no,
            "quantity": item.get("quantity"), "buy_price_won": item.get("buy_price"),
            "high_since_buy_won": item.get("high_since_buy"),
            "stop_price_won": item.get("stop_price"), "stop_source": item.get("stop_source"),
            "target_price_won": item.get("target_price"), "entry_atr": item.get("entry_atr"),
            "kk_armed": item.get("kk_armed"),
            "mode": "shadow", "attempts": attempts, "model": self.model,
        }

        head = await self.db.fetch_head_row(ticker)
        if head is None:
            base_row.update(result="skipped", reason="no_bars")
            await self.db.upsert_evaluation(base_row)
            return "skipped", None

        rows = await self.db.fetch_recent_daily(ticker, BAR_FETCH_DAYS)
        rows = [r for r in rows if r.get("bas_dd") != now.date()]  # 오늘 봉 미래 정보 차단
        if not rows or rows[0].get("bas_dd") != bar_date:
            base_row.update(result="skipped", reason="stale_bar")
            await self.db.upsert_evaluation(base_row)
            return "skipped", None

        if not bars_mod.is_row_confirmed(
            bas_dd=rows[0]["bas_dd"], updated_at=rows[0].get("updated_at"),
            head_bas_dd=head.get("bas_dd"), now=now,
        ):
            base_row.update(result="skipped", reason="provisional_bar")
            await self.db.upsert_evaluation(base_row)
            return "skipped", None

        if self._call_count_today(now) >= DAILY_CALL_CAP:
            base_row.update(result="failed", reason="cap_exceeded")
            await self.db.upsert_evaluation(base_row)
            return "failed", None

        if self.openai is None:
            base_row.update(result="failed", reason="no_key")
            await self.db.upsert_evaluation(base_row)
            return "failed", None

        close_won = rows[0].get("close_price")
        try:
            tech = features_mod.compute_technicals(
                [_as_row_map(r) for r in rows], current_price=close_won or 0,
            )
        except Exception:
            tech = {}

        buy_price = base_row["buy_price_won"]
        bars_held = len([r for r in rows if buy_date is not None and r.get("bas_dd") >= buy_date])

        def _pct(a, b):
            try:
                if a is None or not b:
                    return None
                return (float(a) - float(b)) / float(b) * 100.0
            except Exception:
                return None

        unrealized_pct = _pct(close_won, buy_price)
        high_since_buy = base_row["high_since_buy_won"]
        mfe_pct = _pct(high_since_buy, buy_price)
        try:
            post_buy_lows = [r.get("low_price") for r in rows
                             if buy_date is not None and r.get("bas_dd") >= buy_date
                             and r.get("low_price") is not None]
            mae_pct = _pct(min(post_buy_lows), buy_price) if post_buy_lows else None
        except Exception:
            mae_pct = None

        stop_price = base_row["stop_price_won"]
        stop_dist_pct = _pct(close_won, stop_price) if stop_price else None
        try:
            atr14 = tech.get("atr14_won")
            stop_dist_atr = (
                (float(close_won) - float(stop_price)) / float(atr14)
                if close_won is not None and stop_price is not None and atr14 else None
            )
        except Exception:
            stop_dist_atr = None

        strat_info = strategies.get(strategy_id) if isinstance(strategies, dict) else None
        params = (strat_info or {}).get("params") if isinstance(strat_info, dict) else {}
        exit_rule_text = prompt_mod.describe_exit_rule(strategy_id, params or {})

        time_exit_bars_left = None
        if strategy_id == "donchian_swing" and isinstance(params, dict):
            try:
                time_exit_bars_left = int(params.get("kk_time_exit_bars", 20)) - bars_held
            except Exception:
                time_exit_bars_left = None
        base_row["time_exit_bars_left"] = time_exit_bars_left

        position_payload = {
            "strategy_id": strategy_id,
            "buy_price_won": buy_price,
            "buy_date": str(buy_date) if buy_date else None,
            "bars_held": bars_held,
            "close_won": close_won,
            "unrealized_pct": unrealized_pct,
            "mfe_pct": mfe_pct,
            "mae_pct": mae_pct,
            "stop_price_won": stop_price,
            "stop_source": base_row["stop_source"],
            "stop_dist_pct": stop_dist_pct,
            "stop_dist_atr": stop_dist_atr,
            "target_price_won": base_row["target_price_won"],
            "entry_atr": base_row["entry_atr"],
            "kk_armed": base_row["kk_armed"],
            "time_exit_bars_left": time_exit_bars_left,
            "ema5_won": tech.get("ema5_won"), "ema20_won": tech.get("ema20_won"),
            "ema50_won": tech.get("ema50_won"),
            "rsi14": tech.get("rsi14"), "macd": tech.get("macd"),
            "macd_signal": tech.get("macd_signal"), "macd_hist": tech.get("macd_hist"),
            "atr14_pct": tech.get("atr14_pct"), "hv20_pct": tech.get("hv20_pct"),
            "pos_in_ch20_pct": tech.get("pos_in_ch20_pct"), "up_days_streak": tech.get("up_days_streak"),
            "exit_rule_text": exit_rule_text,
        }
        base_row["unrealized_pct"] = unrealized_pct
        base_row["mfe_pct"] = mfe_pct
        base_row["mae_pct"] = mae_pct
        base_row["stop_dist_pct"] = stop_dist_pct
        base_row["close_won"] = close_won
        base_row["feature_version"] = _feature_version()

        messages = prompt_mod.build_messages(position_payload)
        prompt_version = prompt_mod.prompt_version(self.model)
        base_row["prompt_version"] = prompt_version
        base_row["input_payload"] = {"position": position_payload}

        self._bump_call_count(now)

        try:
            resp = await asyncio.wait_for(
                self.openai.chat.completions.create(
                    model=self.model, messages=messages,
                    response_format={"type": "json_object"},
                    max_completion_tokens=MAX_COMPLETION_TOKENS,
                ),
                timeout=CALL_TIMEOUT_SECS,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            base_row.update(result="failed", reason="timeout")
            await self.db.upsert_evaluation(base_row)
            return "failed", prompt_version
        except Exception:
            base_row.update(result="failed", reason="api_error")
            await self.db.upsert_evaluation(base_row)
            return "failed", prompt_version

        try:
            content = resp.choices[0].message.content
        except Exception:
            content = None
        try:
            finish_reason = resp.choices[0].finish_reason
        except Exception:
            finish_reason = None
        try:
            usage = getattr(resp, "usage", None)
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else None
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage else None
        except Exception:
            tokens_in, tokens_out = None, None

        action, score, rationale, key_risks, invalidations, inconsistent, reason = (
            prompt_mod.validate_output(content, finish_reason)
        )
        if reason is not None:
            base_row.update(result="failed", reason=reason, raw_response=str(content) if content else None)
            await self.db.upsert_evaluation(base_row)
            return "failed", prompt_version

        base_row.update(
            result="ok", reason=None, action=action, exit_score=score, inconsistent=inconsistent,
            rationale=rationale, key_risks=key_risks, invalidations=invalidations,
            tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=None,
            evaluated_at=now, raw_response=str(content) if content else None,
        )
        await self.db.upsert_evaluation(base_row)
        return "ok", prompt_version


_FEATURE_VERSION_CACHE: "str | None" = None


def _feature_version() -> str:
    global _FEATURE_VERSION_CACHE
    if _FEATURE_VERSION_CACHE is not None:
        return _FEATURE_VERSION_CACHE
    try:
        import hashlib

        keys = sorted(features_mod.compute_technicals([], current_price=0).keys())
        _FEATURE_VERSION_CACHE = hashlib.sha256("|".join(keys).encode("utf-8")).hexdigest()[:12]
    except Exception:
        _FEATURE_VERSION_CACHE = ""
    return _FEATURE_VERSION_CACHE
