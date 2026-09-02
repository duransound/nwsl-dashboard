-- Round 22. The unfiltered and penalty calls are independent snapshots. A
-- match finishing between them can leave a penalty in one and not the other;
-- a negative npxG then poisons every rate downstream without ever raising.
select player_id, xgoals, pen_xgoals, npxg
from {{ ref('fct_player_season') }}
where npxg < 0 or np_goals < 0 or np_shots < 0
