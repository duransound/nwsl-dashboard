-- general_position rides along on the row -- confirmed on all 245 live rows.
-- build_dashboard.py's fetch_position_gaps() makes eight filtered calls per
-- run only because that had never been checked.
select
    season,
    variant,
    record->>'$.player_id'                                 as player_id,
    record->>'$.general_position'                          as general_position,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[0]'
         else record->>'$.team_id' end                     as team_id,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then json_array_length(record->'$.team_id')
         else 1 end                                        as team_count,
    coalesce(
        try_cast(record->>'$.minutes_played' as double),
        try_cast(record->>'$.minutes'        as double)
    )                                                      as minutes,
    action->>'$.action_type'                               as action_type,
    try_cast(action->>'$.goals_added_above_avg' as double) as goals_added_above_avg,
    try_cast(action->>'$.goals_added_raw'       as double) as goals_added_raw,
    try_cast(action->>'$.num_actions'           as double) as num_actions
from (
    select season, variant, record,
           unnest(json_extract(record, '$.data[*]')) as action
    from {{ ref('src_current_records') }}
    where endpoint = 'players/goals-added'
)
