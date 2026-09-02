select
    season,
    record->>'$.player_id'                            as player_id,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[0]'
         else record->>'$.team_id' end                as team_id,
    coalesce(
        try_cast(record->>'$.minutes_played' as double),
        try_cast(record->>'$.minutes'        as double)
    )                                                 as minutes,
    try_cast(record->>'$.shots_faced'     as double)  as shots_faced,
    try_cast(record->>'$.goals_conceded'  as double)  as goals_conceded,
    try_cast(record->>'$.xgoals_gk_faced' as double)  as xgoals_faced
from {{ ref('src_current_records') }}
where endpoint = 'goalkeepers/xgoals'
