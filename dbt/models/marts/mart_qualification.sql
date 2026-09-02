-- qualification.py, in SQL. A player qualifies on minutes_per_game x THEIR OWN
-- team's games played -- per team, so a club with games in hand is not
-- penalized. Missing games fall back to the league median, then to a flat
-- number. Grain: one row per team per season.
with league as (
    select season, median(games) as median_games
    from {{ ref('fct_team_season') }}
    where games is not null
    group by season
)
select
    t.season,
    t.team_id,
    t.team_abbr,
    t.games,
    coalesce(t.games, l.median_games) as games_used,
    (t.games is null)                 as games_imputed,
    case
        when p.flat_minutes is not null then p.flat_minutes
        when coalesce(t.games, l.median_games) is null then p.fallback_minutes
        else p.minutes_per_game * coalesce(t.games, l.median_games)
    end as minutes_required
from {{ ref('fct_team_season') }} t
left join league l on l.season = t.season
cross join {{ ref('params') }} p
