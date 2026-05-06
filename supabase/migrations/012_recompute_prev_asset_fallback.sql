-- 012_recompute_prev_asset_fallback.sql
-- recompute_daily_performance 보강: prev_asset=0인 영업일이 있어도
-- 가장 가까운 0 아닌 이전 영업일의 total_asset을 분모로 사용하도록 변경.
--
-- 배경: 정산 시점 state.total_investment=0이면 daily_performance.total_asset이 0으로
-- 기록되어 다음 영업일 daily_profit_rate 계산 시 분모 0 → daily_rate=0 → cumulative 정체.
-- correlated subquery로 더 이전 영업일까지 거슬러 0 아닌 total_asset을 찾는다.
-- (PostgreSQL이 IGNORE NULLS 윈도우 옵션을 지원하지 않아 subquery 방식 사용)

create or replace function recompute_daily_performance() returns void as $$
begin
  -- 1) trade_history SELL의 profit_loss 합 → daily_realized_pnl (전략별 + total)
  with pnl_strategy as (
    select date(timestamp at time zone 'Asia/Seoul') as d,
           strategy as sid,
           sum(coalesce(profit_loss, 0)) as pnl
    from trade_history
    where trade_type = 'SELL' and status in ('COMPLETED','PARTIAL')
    group by 1, 2
  ),
  pnl_all as (
    select d, sid, pnl from pnl_strategy
    union all
    select d, 'total' as sid, sum(pnl) from pnl_strategy group by d
  )
  update daily_performance dp
     set daily_realized_pnl = p.pnl
    from pnl_all p
   where dp.date = p.d and dp.strategy = p.sid;

  -- 2) daily_profit_rate 재계산 = daily_realized_pnl / 가장 가까운 0 아닌 이전 영업일 total_asset * 100
  --    correlated subquery로 자기보다 이전 영업일 중 total_asset>0인 최신 row를 찾는다.
  with ranked as (
    select dp.date, dp.strategy, dp.daily_realized_pnl,
           (select dp2.total_asset
              from daily_performance dp2
             where dp2.strategy = dp.strategy
               and dp2.date < dp.date
               and dp2.total_asset > 0
             order by dp2.date desc
             limit 1) as prev_asset
    from daily_performance dp
  )
  update daily_performance dp
     set daily_profit_rate = case
       when r.prev_asset > 0
       then (r.daily_realized_pnl::numeric / r.prev_asset) * 100
       else 0
     end
    from ranked r
   where dp.date = r.date and dp.strategy = r.strategy;

  -- 3) TWR 복리 누적: cumulative_return_rate = (Π(1 + daily/100) - 1) * 100
  with twr as (
    select date, strategy,
           (exp(sum(ln(1 + daily_profit_rate/100.0))
                over (partition by strategy order by date
                      rows between unbounded preceding and current row)) - 1) * 100 as cum
    from daily_performance
    where daily_profit_rate > -100
  )
  update daily_performance dp
     set cumulative_return_rate = t.cum
    from twr t
   where dp.date = t.date and dp.strategy = t.strategy;
end;
$$ language plpgsql;
