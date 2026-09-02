-- Grain: one row per player PER TEAM per season.
-- The model that makes transfers honest. A player who moved contributes one
-- row per club from the team_id-filtered calls; everyone else contributes
-- their single row. The not-exists guard is what stops a mover being counted
-- from both branches -- the classic grain bug, and the reason
-- assert_no_double_counted_player_team exists.
select s.season, s.player_id, p.player_name, s.team_id, d.team_abbr,
       s.general_position, s.minutes, s.goals, s.shots, s.xgoals, s.xassists,
       true as from_split
from {{ ref('stg_player_team_xgoals') }} s
join      {{ ref('dim_player') }} p on p.season = s.season and p.player_id = s.player_id
left join {{ ref('dim_team') }}   d on d.season = s.season and d.team_id   = s.team_id

union all

select x.season, x.player_id, p.player_name, x.team_id, d.team_abbr,
       x.general_position, x.minutes, x.goals, x.shots, x.xgoals, x.xassists,
       false as from_split
from {{ ref('stg_player_xgoals') }} x
join      {{ ref('dim_player') }} p on p.season = x.season and p.player_id = x.player_id
left join {{ ref('dim_team') }}   d on d.season = x.season and d.team_id   = x.team_id
where x.variant is null
  and x.team_count = 1
  and not exists (select 1 from {{ ref('stg_player_team_xgoals') }} s2
                  where s2.season = x.season and s2.player_id = x.player_id)
