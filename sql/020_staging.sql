-- ---------------------------------------------------------------------------
-- 020_staging.sql -- one view per endpoint, and nothing else
--
-- Staging does exactly three jobs and refuses the fourth:
--   1. pull fields out of the raw JSON
--   2. give them types
--   3. normalize the API's inconsistencies
-- It does NOT aggregate, join across endpoints, or compute a rate. Those
-- belong in 030_marts.sql. Keeping that line sharp is what makes a broken
-- number findable: if a value is wrong, it is wrong either because the API
-- said something unexpected (staging) or because the arithmetic is wrong
-- (marts), and the two are never tangled in the same file.
--
-- Every normalization below has a scar behind it. The comments name which.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS stg;

-- --------------------------------------------------------------- reference

CREATE OR REPLACE VIEW stg.teams AS
SELECT
    season,
    record->>'$.team_id'           AS team_id,
    record->>'$.team_name'         AS team_name,
    record->>'$.team_abbreviation' AS team_abbr
FROM raw.current_records
WHERE endpoint = 'teams';

CREATE OR REPLACE VIEW stg.players AS
SELECT
    season,
    record->>'$.player_id'   AS player_id,
    record->>'$.player_name' AS player_name
FROM raw.current_records
WHERE endpoint = 'players';

-- ------------------------------------------------------------------- teams

CREATE OR REPLACE VIEW stg.team_xgoals AS
SELECT
    season,
    variant,                                    -- NULL = all shots; else a shot_pattern
    record->>'$.team_id'                              AS team_id,
    TRY_CAST(record->>'$.xgoals_for'     AS DOUBLE)   AS xgoals_for,
    TRY_CAST(record->>'$.xgoals_against' AS DOUBLE)   AS xgoals_against,
    TRY_CAST(record->>'$.points'         AS DOUBLE)   AS points,
    -- Games played has been observed under three different names, and the
    -- minutes-qualification rule depends on it (qualification.py). TRY_CAST
    -- returns NULL rather than raising on a value that isn't a number, so a
    -- renamed field degrades to "unknown games" -- which the mart handles by
    -- falling back to the league median -- instead of aborting the run.
    COALESCE(
        TRY_CAST(record->>'$.count_games'  AS INTEGER),
        TRY_CAST(record->>'$.games'        AS INTEGER),
        TRY_CAST(record->>'$.games_played' AS INTEGER)
    ) AS games
FROM raw.current_records
WHERE endpoint = 'teams/xgoals';

-- /teams/goals-added does not return a flat row. Each team's row carries a
-- nested `data` array with one entry per action type (Passing, Fouling,
-- Interrupting, Dribbling, Receiving, Shooting, Claiming). Reading
-- goals_added_for straight off the row KeyErrors on every live call -- the
-- round-15 bug that survived five rounds of demo-only testing because the
-- demo hardcoded already-summed totals.
--
-- Unnesting it here, one row per team per action type, means the mart can
-- sum it OR break it down without another fetch, and the shape is visible
-- in the schema instead of buried in a Python loop.
CREATE OR REPLACE VIEW stg.team_goals_added_actions AS
SELECT
    season,
    -- Same list-vs-string normalization as the player endpoints below.
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[0]'
         ELSE record->>'$.team_id' END                    AS team_id,
    action->>'$.action_type'                              AS action_type,
    TRY_CAST(action->>'$.goals_added_for'     AS DOUBLE)  AS goals_added_for,
    TRY_CAST(action->>'$.goals_added_against' AS DOUBLE)  AS goals_added_against,
    TRY_CAST(action->>'$.num_actions_for'     AS DOUBLE)  AS num_actions_for
FROM (
    SELECT season, record, unnest(json_extract(record, '$.data[*]')) AS action
    FROM   raw.current_records
    WHERE  endpoint = 'teams/goals-added'
);

-- ----------------------------------------------------------------- players

-- The single most expensive lesson in this project, encoded once:
-- /players/xgoals returns team_id as a LIST, while /teams/xgoals returns it
-- as a bare string. Every player-level endpoint has to unwrap it, and the two
-- functions that forgot were the two that crashed on the first live run.
--
-- AND THE LIST IS NOT ALWAYS LENGTH 1. The first live load of this warehouse
-- (2026-09-02) found six players carrying two clubs -- mid-season transfers.
-- The array's ORDER CARRIES NO RELIABLE MEANING. It is not chronological
-- (Yazmeen Ryan reads ["DEN","HOU"] on a Houston -> Denver move) and it is not
-- minutes-ordered either: across the six, `[0]` names the club they played
-- MORE for in three cases and LESS in three. Lilly Reale reads Gotham-first on
-- 629 minutes at Gotham and 903 at Boston.
--
-- So `[0]` is neither "the only team" nor reliably anything else, and
-- build_dashboard.py's round-15 comment ("the first (only observed) element")
-- rests on an assumption the data does not support.
--
-- Until the attribution rule is decided, this view refuses to hide the
-- problem: it exposes first, last, and the count, keeps `team_id` on the
-- existing [0] behaviour so nothing changes silently, and dw.dq_multi_team
-- lists exactly who is affected.
CREATE OR REPLACE VIEW stg.player_xgoals AS
SELECT
    season,
    variant,                                    -- NULL = all shots, 'Penalty' = penalties only
    record->>'$.player_id'                            AS player_id,
    record->>'$.general_position'                     AS general_position,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[0]'
         ELSE record->>'$.team_id' END                AS team_id,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[#-1]'
         ELSE record->>'$.team_id' END                AS team_id_last,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN json_array_length(record->'$.team_id')
         ELSE 1 END                                   AS team_count,
    record->>'$.team_id'                              AS team_ids_raw,
    -- `minutes_played` on some endpoints, `minutes` on others. COALESCE is
    -- the honest version of the Python .get() chain: it reads as a rule
    -- ("either of these names") rather than as a defensive accident.
    COALESCE(
        TRY_CAST(record->>'$.minutes_played' AS DOUBLE),
        TRY_CAST(record->>'$.minutes'        AS DOUBLE)
    )                                                 AS minutes,
    TRY_CAST(record->>'$.goals'     AS DOUBLE)        AS goals,
    TRY_CAST(record->>'$.shots'     AS DOUBLE)        AS shots,
    TRY_CAST(record->>'$.xgoals'    AS DOUBLE)        AS xgoals,
    TRY_CAST(record->>'$.xassists'  AS DOUBLE)        AS xassists,
    TRY_CAST(record->>'$.key_passes' AS DOUBLE)       AS key_passes,
    -- Present on the live rows, and previously unused. `xplace` is ASA's
    -- shot-placement component -- finishing skill net of where the ball went,
    -- which is a sharper story than goals-minus-xG alone.
    TRY_CAST(record->>'$.shots_on_target' AS DOUBLE)  AS shots_on_target,
    TRY_CAST(record->>'$.xplace'          AS DOUBLE)  AS xplace,
    TRY_CAST(record->>'$.points_added'    AS DOUBLE)  AS points_added,
    TRY_CAST(record->>'$.xpoints_added'   AS DOUBLE)  AS xpoints_added
FROM raw.current_records
WHERE endpoint = 'players/xgoals'
  AND (variant IS NULL OR variant = 'Penalty');

-- The per-club split for players who changed clubs mid-season, from
-- team_id-filtered calls. Confirmed live: the parts sum to the unfiltered
-- total exactly, and general_position can differ between the two clubs --
-- Ally Sentnor is a striker at Kansas City and an attacking midfielder at
-- Angel City, which the aggregate row cannot say at all.
--
-- Third shape variation for the same field: on THESE rows team_id comes back
-- as a plain string, even though the unfiltered call returns an array.
CREATE OR REPLACE VIEW stg.player_team_xgoals AS
SELECT
    season,
    record->>'$.player_id'                            AS player_id,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[0]'
         ELSE record->>'$.team_id' END                AS team_id,
    record->>'$.general_position'                     AS general_position,
    COALESCE(
        TRY_CAST(record->>'$.minutes_played' AS DOUBLE),
        TRY_CAST(record->>'$.minutes'        AS DOUBLE)
    )                                                 AS minutes,
    TRY_CAST(record->>'$.goals'    AS DOUBLE)         AS goals,
    TRY_CAST(record->>'$.shots'    AS DOUBLE)         AS shots,
    TRY_CAST(record->>'$.xgoals'   AS DOUBLE)         AS xgoals,
    TRY_CAST(record->>'$.xassists' AS DOUBLE)         AS xassists
FROM raw.current_records
WHERE endpoint = 'players/xgoals' AND variant = 'by-team';

CREATE OR REPLACE VIEW stg.player_goals_added_actions AS
SELECT
    season,
    variant,                                    -- the general_position the call filtered on
    record->>'$.player_id'                                AS player_id,
    -- general_position rides along on the row. build_dashboard.py's
    -- fetch_position_gaps() makes eight separate filtered calls per run
    -- precisely because this had "never been confirmed to be present" -- the
    -- first live load confirms it, on all 245 rows. Eight calls collapse to one.
    record->>'$.general_position'                         AS general_position,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[0]'
         ELSE record->>'$.team_id' END                    AS team_id,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[#-1]'
         ELSE record->>'$.team_id' END                    AS team_id_last,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN json_array_length(record->'$.team_id')
         ELSE 1 END                                       AS team_count,
    COALESCE(
        TRY_CAST(record->>'$.minutes_played' AS DOUBLE),
        TRY_CAST(record->>'$.minutes'        AS DOUBLE)
    )                                                     AS minutes,
    action->>'$.action_type'                              AS action_type,
    TRY_CAST(action->>'$.goals_added_above_avg' AS DOUBLE) AS goals_added_above_avg,
    TRY_CAST(action->>'$.goals_added_raw'       AS DOUBLE) AS goals_added_raw,
    TRY_CAST(action->>'$.num_actions'           AS DOUBLE) AS num_actions
FROM (
    SELECT season, variant, record,
           unnest(json_extract(record, '$.data[*]')) AS action
    FROM   raw.current_records
    WHERE  endpoint = 'players/goals-added'
);

CREATE OR REPLACE VIEW stg.goalkeeper_xgoals AS
SELECT
    season,
    record->>'$.player_id'                             AS player_id,
    CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
         THEN record->>'$.team_id[0]'
         ELSE record->>'$.team_id' END                 AS team_id,
    COALESCE(
        TRY_CAST(record->>'$.minutes_played' AS DOUBLE),
        TRY_CAST(record->>'$.minutes'        AS DOUBLE)
    )                                                  AS minutes,
    TRY_CAST(record->>'$.shots_faced'      AS DOUBLE)  AS shots_faced,
    TRY_CAST(record->>'$.goals_conceded'   AS DOUBLE)  AS goals_conceded,
    TRY_CAST(record->>'$.xgoals_gk_faced'  AS DOUBLE)  AS xgoals_faced
FROM raw.current_records
WHERE endpoint = 'goalkeepers/xgoals';
