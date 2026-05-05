-- 010_recompute_performance_fn.sql
-- daily_performance를 trade_history 기반으로 일괄 재계산하는 함수.
-- 매일 정산 후 호출하거나 admin API로 강제 호출 시 사용.

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

  -- 2) daily_profit_rate 재계산 = daily_realized_pnl / 전일 total_asset * 100
  with ranked as (
    select date, strategy, daily_realized_pnl,
           lag(total_asset) over (partition by strategy order by date) as prev_asset
    from daily_performance
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
