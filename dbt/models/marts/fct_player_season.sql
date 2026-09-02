-- Grain: one row per player per season.
--
-- npxG is derived, not published: ask /players/xgoals the same question twice
-- (unfiltered, then shot_pattern=Penalty) and subtract. Both answers are
-- already in raw, so it is a join rather than a second network call.
--   coalesce(pen, 0)  absent from the penalty response means zero, not unknown
--   greatest(.., 0)   the two calls are independent snapshots; a match landing
--                     between them must not produce a negative npxG
select
    a.season,
    a.player_id,
    p.player_name,
    a.general_position,
    a.team_id,
    d.team_abbr,
    d.team_name,
    a.team_count,
    pt.team_abbr        as primary_team_abbr,
    pt.general_position as primary_position,
    a.minutes,
    a.goals,
    a.shots,
    a.shots_on_target,
    a.xgoals,
    a.xassists,
    a.xplace,
    coalesce(pen.goals,  0) as pen_goals,
    coalesce(pen.shots,  0) as pen_shots,
    coalesce(pen.xgoals, 0) as pen_xgoals,
    greatest(a.goals  - coalesce(pen.goals,  0), 0) as np_goals,
    greatest(a.shots  - coalesce(pen.shots,  0), 0) as np_shots,
    greatest(a.xgoals - coalesce(pen.xgoals, 0), 0) as npxg
from {{ ref('stg_player_xgoals') }} a
left join {{ ref('stg_player_xgoals') }} pen
       on pen.season = a.season and pen.player_id = a.player_id and pen.variant = 'Penalty'
join      {{ ref('dim_player') }} p on p.season = a.season and p.player_id = a.player_id
left join {{ ref('dim_team') }}   d on d.season = a.season and d.team_id   = a.team_id
left join {{ ref('mart_primary_team') }} pt on pt.season = a.season and pt.player_id = a.player_id
where a.variant is null
