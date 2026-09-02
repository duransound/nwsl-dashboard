select
    season,
    record->>'$.player_id'   as player_id,
    record->>'$.player_name' as player_name
from {{ ref('src_current_records') }}
where endpoint = 'players'
