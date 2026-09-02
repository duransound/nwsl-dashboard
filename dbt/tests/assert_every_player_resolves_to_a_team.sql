-- The other half of the same bug: a player whose team join failed still
-- appears, badge blank, and nothing raises.
select player_id, team_id
from {{ ref('fct_player_season') }}
where team_abbr is null
