-- Grain: one row per player per season. What every player scatter reads.
-- per96, not per90: NWSL matches reliably run past 90, and the project's rate
-- convention is 96. nullif() is the divide-by-zero guard -- a zero-minutes
-- player yields NULL (plots as absent) instead of an inf that takes the axis
-- with it.
select
    f.season,
    f.player_id,
    f.player_name,
    f.team_id,
    coalesce(f.primary_team_abbr, f.team_abbr)       as team_abbr,
    f.team_abbr                                      as team_abbr_listed_first,
    f.team_count,
    coalesce(f.primary_position, f.general_position) as general_position,
    f.minutes,
    q.minutes_required,
    (f.minutes >= q.minutes_required) as qualified,
    q.games_imputed,
    f.goals, f.shots, f.xgoals, f.xassists, f.xplace,
    f.npxg, f.np_goals, f.np_shots,
    f.np_xplace,
    f.finishing_residual,
    f.goals    / nullif(f.minutes, 0) * 96 as goals96,
    f.shots    / nullif(f.minutes, 0) * 96 as shots96,
    f.xgoals   / nullif(f.minutes, 0) * 96 as xg96,
    f.xassists / nullif(f.minutes, 0) * 96 as xa96,
    f.npxg     / nullif(f.minutes, 0) * 96 as npxg96,
    f.np_goals / nullif(f.minutes, 0) * 96 as npgoals96,
    f.np_goals - f.npxg                    as np_goals_minus_npxg,
    f.npxg     / nullif(f.np_shots, 0)     as npxg_per_shot
from {{ ref('fct_player_season') }} f
left join {{ ref('mart_qualification') }} q
       on q.season = f.season and q.team_id = f.team_id
