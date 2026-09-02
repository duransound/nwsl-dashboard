-- Grain: one row per player per season per action type.
-- Deliberately not pre-summed, so the leaderboard total and the Playmaking
-- Style split come from one model instead of two fetches.
select
    g.season,
    g.player_id,
    p.player_name,
    g.team_id,
    d.team_abbr,
    g.general_position,
    g.minutes,
    g.action_type,
    g.goals_added_above_avg
from {{ ref('stg_player_goals_added_actions') }} g
join      {{ ref('dim_player') }} p on p.season = g.season and p.player_id = g.player_id
left join {{ ref('dim_team') }}   d on d.season = g.season and d.team_id   = g.team_id
