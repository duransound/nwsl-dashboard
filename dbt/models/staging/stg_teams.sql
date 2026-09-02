select
    season,
    record->>'$.team_id'           as team_id,
    record->>'$.team_name'         as team_name,
    record->>'$.team_abbreviation' as team_abbr
from {{ ref('src_current_records') }}
where endpoint = 'teams'
