-- Grain: one row per team per season.
-- /teams has 500'd while /teams/xgoals stayed healthy (round 3). Building the
-- dimension from the ids that appear in the STATS, then left-joining the name
-- lookup, means losing the lookup costs a name, not a club.
with ids as (
    select distinct season, team_id from {{ ref('stg_team_xgoals') }}
    union
    select distinct season, team_id from {{ ref('stg_team_goals_added_actions') }}
    union
    select distinct season, team_id from {{ ref('stg_player_xgoals') }}
)
select
    i.season,
    i.team_id,
    coalesce(t.team_name, i.team_id) as team_name,
    coalesce(t.team_abbr, i.team_id) as team_abbr,
    (t.team_id is null)              as name_missing
from ids i
left join {{ ref('stg_teams') }} t
       on t.season = i.season and t.team_id = i.team_id
