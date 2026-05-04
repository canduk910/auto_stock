-- 009_performance_cashflow.sql
-- 일일 실적 테이블에 입출금/실현손익/누적수익률 컬럼 추가
--
-- 사유: 운용 중 발생하는 외부 입출금이 수익률 계산을 왜곡하지 않도록
-- TWR(Time-Weighted Return) 복리 누적 수익률 + 실현손익 기반 일별 수익률 도입.

alter table daily_performance
  add column if not exists net_external_cashflow numeric default 0,
  add column if not exists daily_realized_pnl    numeric default 0,
  add column if not exists deposit               numeric default 0,
  add column if not exists cumulative_return_rate numeric default 0;

comment on column daily_performance.net_external_cashflow is '당일 외부 입출금 추정(입금 +, 출금 −). (Δ예수금) - (매도총액 - 매수총액)';
comment on column daily_performance.daily_realized_pnl    is '당일 실현손익 합 (trade_history 매도 profit_loss 합)';
comment on column daily_performance.deposit               is '당일 정산 시점 예수금';
comment on column daily_performance.cumulative_return_rate is 'TWR 복리 누적 수익률(%) — Π(1 + daily_rate) - 1';
