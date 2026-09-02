-- /teams/goals-added nests a per-action-type breakdown under `data`. Reading
-- goals_added_for off the row is the round-15 bug that KeyError'd on every
-- live call after passing five rounds of demo-only tests.
select
    season,
    case when json_type(record->'$.team_id') = 'ARRAY'
         then record->>'$.team_id[0]'
         else record->>'$.team_id' end                   as team_id,
    action->>'$.action_type'                             as action_type,
    try_cast(action->>'$.goals_added_for'     as double) as goals_added_for,
    try_cast(action->>'$.goals_added_against' as double) as goals_added_against,
    try_cast(action->>'$.num_actions_for'     as double) as num_actions_for
from (
    select season, record, unnest(json_extract(record, '$.data[*]')) as action
    from {{ ref('src_current_records') }}
    where endpoint = 'teams/goals-added'
)
