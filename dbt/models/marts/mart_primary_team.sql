-- Grain: one row per player per season -- which club goes on their badge.
-- Not array position: the club they actually played the most minutes for.
-- QUALIFY filters on the window function directly, no wrapping subquery.
select season, player_id, team_id, team_abbr, general_position, minutes
from {{ ref('fct_player_team_season') }}
qualify row_number() over (partition by season, player_id
                           order by minutes desc, team_id) = 1
