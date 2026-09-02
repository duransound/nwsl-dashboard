-- Grain: one row per player per season.
with ids as (
    select distinct season, player_id from {{ ref('stg_player_xgoals') }}
    union
    select distinct season, player_id from {{ ref('stg_player_goals_added_actions') }}
    union
    select distinct season, player_id from {{ ref('stg_goalkeeper_xgoals') }}
)
select
    i.season,
    i.player_id,
    coalesce(p.player_name, i.player_id) as player_name,
    (p.player_id is null)                as name_missing
from ids i
left join {{ ref('stg_players') }} p
       on p.season = i.season and p.player_id = i.player_id
