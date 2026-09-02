-- ---------------------------------------------------------------------------
-- 010_raw.sql -- the landing zone
--
-- One rule governs this layer: RAW IS APPEND-ONLY AND NEVER EDITED. Every
-- record arrives from the ASA API exactly as the API sent it, JSON and all,
-- and nothing downstream is allowed to write back here. If a mart turns out
-- to be wrong, the fix is a new query over the same raw rows -- not a
-- re-fetch, and not a mutation.
--
-- That is the whole reason a warehouse beats the current build_dashboard.py
-- pattern. Today a fetch function reads the API, reshapes the response in
-- Python, and throws the response away. When a field turns out to be a list
-- instead of a string (round 15), or `minutes_played` instead of `minutes`
-- (round 15 again), there is nothing left on disk to look at -- the only way
-- to see what the API actually said is to call it again and hope it says the
-- same thing. Here, the payload is still sitting in raw.asa_records and the
-- bug is one SELECT away from being visible.
--
-- Two tables:
--   raw.loads       -- one row per run of the loader, so a bad week can be
--                      identified and excluded rather than silently blended
--                      into the good ones
--   raw.asa_records -- one row per record the API returned, tagged with which
--                      load and which endpoint it came from
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.loads (
    load_id      BIGINT PRIMARY KEY,
    season       VARCHAR   NOT NULL,
    started_at   TIMESTAMP NOT NULL,
    finished_at  TIMESTAMP,
    source       VARCHAR   NOT NULL,   -- 'api' | 'fixture' | 'json-dir'
    n_records    BIGINT,
    n_endpoints  INTEGER,
    n_failed     INTEGER,
    notes        VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.asa_records (
    load_id     BIGINT    NOT NULL,
    endpoint    VARCHAR   NOT NULL,   -- 'players/xgoals', 'teams/goals-added', ...
    season      VARCHAR   NOT NULL,
    -- `variant` is what makes one endpoint able to answer several questions
    -- without a separate table per question. /players/xgoals is called once
    -- unfiltered and once with shot_pattern=Penalty; /players/goals-added is
    -- called once per position. The filter that produced a row is part of the
    -- row's identity, so it is stored, not inferred.
    variant     VARCHAR,
    fetched_at  TIMESTAMP NOT NULL,
    record      JSON      NOT NULL
);

-- Which load is "current" for a season. Every staging view reads through
-- this, so a half-finished or failed load never leaks into the dashboard:
-- the loader only stamps finished_at when the run completed, and anything
-- without it is invisible here.
CREATE OR REPLACE VIEW raw.current_load AS
SELECT season, max(load_id) AS load_id
FROM   raw.loads
WHERE  finished_at IS NOT NULL
GROUP  BY season;

CREATE OR REPLACE VIEW raw.current_records AS
SELECT r.*
FROM   raw.asa_records r
JOIN   raw.current_load c
  ON   r.season = c.season
 AND   r.load_id = c.load_id;
