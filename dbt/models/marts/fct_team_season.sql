-- Grain: one row per team per season, all shot patterns.
select
    x.season,
    x.team_id,
    d.team_name,
    d.team_abbr,
    x.xgoals_for,
    x.xgoals_against,
    x.xgoals_for - x.xgoals_against as xgoal_difference,
    x.points,
    x.games
from {{ ref('stg_team_xgoals') }} x
join {{ ref('dim_team') }} d on d.season = x.season and d.team_id = x.team_id
where x.variant is null
