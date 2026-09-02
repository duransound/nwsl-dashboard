select
    season,
    variant,
    record->>'$.team_id'                            as team_id,
    try_cast(record->>'$.xgoals_for'     as double) as xgoals_for,
    try_cast(record->>'$.xgoals_against' as double) as xgoals_against,
    try_cast(record->>'$.points'         as double) as points,
    -- Games played has been seen under three names, and the qualification
    -- rule depends on it. try_cast degrades a rename to NULL (handled
    -- downstream by the league median) rather than aborting the run.
    coalesce(
        try_cast(record->>'$.count_games'  as integer),
        try_cast(record->>'$.games'        as integer),
        try_cast(record->>'$.games_played' as integer)
    ) as games
from {{ ref('src_current_records') }}
where endpoint = 'teams/xgoals'
