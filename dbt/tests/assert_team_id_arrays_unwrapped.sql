-- Round 15. /players/xgoals returns team_id as a list. Left unwrapped it
-- becomes the literal string '["315VnJ759x"]' and every join to dim_team
-- misses silently -- no error, just an empty chart.
select player_id, team_id
from {{ ref('stg_player_xgoals') }}
where team_id like '[%' or team_id like '%"%'
