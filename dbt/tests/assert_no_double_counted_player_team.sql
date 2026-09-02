-- The grain check. fct_player_team_season unions split rows with single-club
-- rows; if a transferred player leaked in from both branches their minutes
-- would double and nothing would look obviously wrong -- just a striker with
-- suspiciously good numbers.
select season, player_id, team_id, count(*) as n
from {{ ref('fct_player_team_season') }}
group by 1, 2, 3
having count(*) > 1
