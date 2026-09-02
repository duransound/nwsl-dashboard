-- Data quality, kept as a model rather than a test so it can be read as well
-- as asserted: every player carrying more than one club, the split that
-- resolves them, and whether the two reconcile.
select
    x.season,
    p.player_name,
    x.team_count,
    x.team_ids_raw,
    df.team_abbr as listed_first,
    dl.team_abbr as listed_last,
    pt.team_abbr as primary_team,
    x.minutes    as minutes_unsplit,
    s.minutes_split,
    (s.minutes_split is not null and abs(s.minutes_split - x.minutes) < 0.5) as reconciles
from {{ ref('stg_player_xgoals') }} x
join      {{ ref('dim_player') }} p  on p.season  = x.season and p.player_id = x.player_id
left join {{ ref('dim_team') }}   df on df.season = x.season and df.team_id  = x.team_id
left join {{ ref('dim_team') }}   dl on dl.season = x.season and dl.team_id  = x.team_id_last
left join {{ ref('mart_primary_team') }} pt on pt.season = x.season and pt.player_id = x.player_id
left join (select season, player_id, sum(minutes) as minutes_split
           from {{ ref('stg_player_team_xgoals') }} group by 1, 2) s
       on s.season = x.season and s.player_id = x.player_id
where x.variant is null and x.team_count > 1
