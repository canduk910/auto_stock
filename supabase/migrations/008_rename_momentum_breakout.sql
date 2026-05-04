-- 008_rename_momentum_breakout.sql
-- 전략 ID 변경: momentum_breakout → long_tail_volatility
-- 표시명: "모멘텀 브레이크아웃" → "롱테일 변동성 돌파"
--
-- 사유: 본질(VB 조기 진입 + 상한가 도달 시 익일 청산)을 더 정확히 표현하는 명칭으로 통일.
-- strategy_id는 30자 VARCHAR이며 외래키 제약이 없으므로 단순 UPDATE로 일괄 이전한다.
-- long_tail_volatility 길이 = 21자 (한도 내).

update strategy_config
   set strategy_id = 'long_tail_volatility'
 where strategy_id = 'momentum_breakout';

update positions
   set strategy_id = 'long_tail_volatility'
 where strategy_id = 'momentum_breakout';

update parameter_recommendations
   set strategy_id = 'long_tail_volatility'
 where strategy_id = 'momentum_breakout';

update trade_history
   set strategy = 'long_tail_volatility'
 where strategy = 'momentum_breakout';

update daily_performance
   set strategy = 'long_tail_volatility'
 where strategy = 'momentum_breakout';
