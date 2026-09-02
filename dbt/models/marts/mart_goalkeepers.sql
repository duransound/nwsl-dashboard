-- Grain: one row per goalkeeper per season.
-- Goals saved above expected is the keeper's goals-minus-xG: the xG of the
-- shots they faced, minus what actually went in.
select
    k.season,
    k.player_id,
    p.player_name,
    k.team_id,
    d.team_abbr,
    k.minutes,
    k.shots_faced,
    k.goals_conceded,
    k.xgoals_faced,
    k.xgoals_faced - k.goals_conceded                               as goals_saved_above_expected,
    k.shots_faced / nullif(k.minutes, 0) * 96                       as shots_faced96,
    (k.xgoals_faced - k.goals_conceded) / nullif(k.minutes, 0) * 96 as gsae96
from {{ ref('stg_goalkeeper_xgoals') }} k
join      {{ ref('dim_player') }} p on p.season = k.season and p.player_id = k.player_id
left join {{ ref('dim_team') }}   d on d.season = k.season and d.team_id   = k.team_id
