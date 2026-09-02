-- The per-club split for players who moved mid-season, from team_id-filtered
-- calls. The parts reconcile to the unfiltered total exactly (see the
-- singular test assert_player_splits_reconcile), and general_position can
-- differ between the two clubs -- Ally Sentnor is a striker at Kansas City
-- and an attacking midfielder at Angel City.
--
-- Third shape for the same field: on these rows team_id is a plain string.
select
    season,
    record->>'$.player_id'                       as player_id,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[0]'
         else record->>'$.team_id' end           as team_id,
    record->>'$.general_position'                as general_position,
    coalesce(
        try_cast(record->>'$.minutes_played' as double),
        try_cast(record->>'$.minutes'        as double)
    )                                            as minutes,
    try_cast(record->>'$.goals'    as double)    as goals,
    try_cast(record->>'$.shots'    as double)    as shots,
    try_cast(record->>'$.xgoals'   as double)    as xgoals,
    try_cast(record->>'$.xassists' as double)    as xassists
from {{ ref('src_current_records') }}
where endpoint = 'players/xgoals' and variant = 'by-team'
