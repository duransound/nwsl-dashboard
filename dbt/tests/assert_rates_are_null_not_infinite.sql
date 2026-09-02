-- The nullif() guard. A zero-minutes player must yield NULL (plots as absent);
-- without it the row is inf and takes the axis of the whole scatter with it.
-- Also asserts the opposite direction: a player WITH minutes must have a rate.
select player_id, minutes, xg96
from {{ ref('mart_player_rates') }}
where (minutes = 0 and xg96 is not null)
   or (minutes > 0 and xgoals is not null and xg96 is null)
   or (xg96 = 'inf'::double or xg96 = '-inf'::double)
