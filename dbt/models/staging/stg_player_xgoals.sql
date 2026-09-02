-- team_id arrives as a LIST here and a bare string on /teams/xgoals -- and
-- the list is not always length 1: mid-season transfers carry two clubs in an
-- order that means nothing. Not chronological, and not minutes-ordered either
-- -- across the six 2026 transfers, [0] names the club they played MORE for in
-- three cases and LESS in three. `team_id` below keeps the historical [0]
-- behaviour so nothing changes silently; charts should read
-- primary_team_abbr from mart_player_rates, which resolves the club from the
-- per-club minutes split instead.
select
    season,
    variant,
    record->>'$.player_id'                            as player_id,
    record->>'$.general_position'                     as general_position,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[0]'
         else record->>'$.team_id' end                as team_id,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[#-1]'
         else record->>'$.team_id' end                as team_id_last,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then json_array_length(record->'$.team_id')
         else 1 end                                   as team_count,
    record->>'$.team_id'                              as team_ids_raw,
    -- minutes_played on some endpoints, minutes on others
    coalesce(
        try_cast(record->>'$.minutes_played' as double),
        try_cast(record->>'$.minutes'        as double)
    )                                                 as minutes,
    try_cast(record->>'$.goals'           as double)  as goals,
    try_cast(record->>'$.shots'           as double)  as shots,
    try_cast(record->>'$.shots_on_target' as double)  as shots_on_target,
    try_cast(record->>'$.xgoals'          as double)  as xgoals,
    try_cast(record->>'$.xassists'        as double)  as xassists,
    try_cast(record->>'$.key_passes'      as double)  as key_passes,
    try_cast(record->>'$.xplace'          as double)  as xplace,
    try_cast(record->>'$.points_added'    as double)  as points_added,
    try_cast(record->>'$.xpoints_added'   as double)  as xpoints_added
from {{ ref('src_current_records') }}
where endpoint = 'players/xgoals'
  and (variant is null or variant = 'Penalty')
