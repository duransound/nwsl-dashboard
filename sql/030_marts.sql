-- ---------------------------------------------------------------------------
-- 030_marts.sql -- the layer the dashboard actually reads
--
-- Staging made the API's answers trustworthy. This file turns them into the
-- numbers the charts plot: joins across endpoints, non-penalty totals, the
-- games-scaled minutes bar, and per-96 rates.
--
-- The shape is the standard warehouse vocabulary, and it is worth knowing by
-- name because it is what a club's data stack will already be using:
--   dim_*  a dimension -- the things you slice BY. One row per team, one row
--          per player. Descriptive, not numeric.
--   fct_*  a fact -- the things you measure. One row per player per season,
--          per team per season, per player per action type. Numeric, and
--          always at a stated grain.
--   mart_* a model built for one consumer. Rates, flags, and rankings the
--          dashboard wants, computed once here instead of in every caller.
--
-- "Grain" is the word to hold onto: the grain of a table is what one row
-- means. Most warehouse bugs are grain bugs -- a join that silently turns one
-- row per player into one row per player per action type, and doubles every
-- total. Each table below states its grain in a comment. When a number comes
-- out wrong by a suspiciously round multiple, that is where to look first.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS dw;

-- Run parameters, so the SQL is not hardcoded to one set of thresholds and
-- the loader can pass through build_dashboard.py's flags unchanged.
CREATE TABLE IF NOT EXISTS dw.settings (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

CREATE OR REPLACE VIEW dw.params AS
SELECT
    COALESCE(MAX(CASE WHEN key = 'minutes_per_game'  THEN TRY_CAST(value AS DOUBLE) END), 30)  AS minutes_per_game,
              MAX(CASE WHEN key = 'flat_minutes'     THEN TRY_CAST(value AS DOUBLE) END)       AS flat_minutes,
    COALESCE(MAX(CASE WHEN key = 'fallback_minutes'  THEN TRY_CAST(value AS DOUBLE) END), 500) AS fallback_minutes
FROM dw.settings;

-- ------------------------------------------------------------- dimensions

-- Grain: one row per team per season.
--
-- /teams has gone down before while /teams/xgoals stayed healthy (round 3),
-- and losing the name lookup should not lose the season. So the dimension is
-- built from the team_ids that actually appear in the stats, LEFT JOINed to
-- the name lookup -- a missing name degrades to the id, and every downstream
-- join still finds its row.
CREATE OR REPLACE VIEW dw.dim_team AS
WITH ids AS (
    SELECT DISTINCT season, team_id FROM stg.team_xgoals
    UNION
    SELECT DISTINCT season, team_id FROM stg.team_goals_added_actions
    UNION
    SELECT DISTINCT season, team_id FROM stg.player_xgoals
)
SELECT
    i.season,
    i.team_id,
    COALESCE(t.team_name, i.team_id) AS team_name,
    COALESCE(t.team_abbr, i.team_id) AS team_abbr,
    (t.team_id IS NULL)              AS name_missing
FROM ids i
LEFT JOIN stg.teams t
       ON t.season = i.season AND t.team_id = i.team_id;

-- Grain: one row per player per season.
CREATE OR REPLACE VIEW dw.dim_player AS
WITH ids AS (
    SELECT DISTINCT season, player_id FROM stg.player_xgoals
    UNION
    SELECT DISTINCT season, player_id FROM stg.player_goals_added_actions
    UNION
    SELECT DISTINCT season, player_id FROM stg.goalkeeper_xgoals
)
SELECT
    i.season,
    i.player_id,
    COALESCE(p.player_name, i.player_id) AS player_name,
    (p.player_id IS NULL)                AS name_missing
FROM ids i
LEFT JOIN stg.players p
       ON p.season = i.season AND p.player_id = i.player_id;

-- ------------------------------------------------------------------ facts

-- Grain: one row per team per season (all shot patterns).
CREATE OR REPLACE VIEW dw.fct_team_season AS
SELECT
    x.season,
    x.team_id,
    d.team_name,
    d.team_abbr,
    x.xgoals_for,
    x.xgoals_against,
    x.xgoals_for - x.xgoals_against AS xgoal_difference,
    x.points,
    x.games
FROM stg.team_xgoals x
JOIN dw.dim_team d
  ON d.season = x.season AND d.team_id = x.team_id
WHERE x.variant IS NULL;

-- Grain: one row per team per season. Sums the nested action breakdown.
CREATE OR REPLACE VIEW dw.fct_team_goals_added AS
SELECT
    a.season,
    a.team_id,
    d.team_abbr,
    d.team_name,
    SUM(a.goals_added_for)                          AS ga_for,
    SUM(a.goals_added_against)                      AS ga_against,
    SUM(a.goals_added_for) - SUM(a.goals_added_against) AS ga_net
FROM stg.team_goals_added_actions a
JOIN dw.dim_team d
  ON d.season = a.season AND d.team_id = a.team_id
GROUP BY 1, 2, 3, 4;

-- Grain: one row per player PER TEAM per season.
--
-- The table that makes transfers honest. A player with one club contributes
-- their single row; a player who moved contributes one row per club, from the
-- team_id-filtered calls. Nobody is attributed to a club by array position.
CREATE OR REPLACE VIEW dw.fct_player_team_season AS
SELECT s.season, s.player_id, p.player_name, s.team_id, d.team_abbr,
       s.general_position, s.minutes, s.goals, s.shots, s.xgoals, s.xassists,
       TRUE AS from_split
FROM      stg.player_team_xgoals s
JOIN      dw.dim_player p ON p.season = s.season AND p.player_id = s.player_id
LEFT JOIN dw.dim_team   d ON d.season = s.season AND d.team_id   = s.team_id
UNION ALL
SELECT x.season, x.player_id, p.player_name, x.team_id, d.team_abbr,
       x.general_position, x.minutes, x.goals, x.shots, x.xgoals, x.xassists,
       FALSE AS from_split
FROM      stg.player_xgoals x
JOIN      dw.dim_player p ON p.season = x.season AND p.player_id = x.player_id
LEFT JOIN dw.dim_team   d ON d.season = x.season AND d.team_id   = x.team_id
WHERE x.variant IS NULL
  AND x.team_count = 1
  -- and never both: a transferred player whose split calls failed still has
  -- no row here, which is the honest outcome -- dw.dq_multi_team flags them.
  AND NOT EXISTS (SELECT 1 FROM stg.player_team_xgoals s2
                  WHERE s2.season = x.season AND s2.player_id = x.player_id);

-- Grain: one row per player per season. Which club to put on their badge.
-- Not a guess any more: whichever club they actually played the most minutes
-- for, computed from the split. QUALIFY filters on the window function
-- directly, so no subquery is needed to pick the top row per player.
CREATE OR REPLACE VIEW dw.mart_primary_team AS
SELECT season, player_id, team_id, team_abbr, general_position, minutes
FROM   dw.fct_player_team_season
QUALIFY row_number() OVER (PARTITION BY season, player_id
                           ORDER BY minutes DESC, team_id) = 1;

-- Grain: one row per player per season.
--
-- The npxG join is the interesting one. ASA publishes no non-penalty xG
-- field, so it is derived by asking /players/xgoals the same question twice
-- -- once unfiltered, once with shot_pattern=Penalty -- and subtracting. Both
-- answers are already in raw.asa_records, distinguished by `variant`, so the
-- subtraction is a LEFT JOIN rather than a second network call.
--
-- Two guards, both load-bearing:
--   COALESCE(pen.*, 0) -- absent from the penalty response means "took no
--     penalties", not "unknown". The filtered call drops nobody, but it is
--     not guaranteed to carry every player the unfiltered call does.
--   GREATEST(..., 0)   -- the two calls are independent snapshots. A match
--     finishing between them can leave a penalty in the filtered total that
--     is not yet in the unfiltered one, which would make npxG negative and
--     silently poison every downstream rate.
CREATE OR REPLACE VIEW dw.fct_player_season AS
SELECT
    a.season,
    a.player_id,
    p.player_name,
    a.general_position,
    a.team_id,
    d.team_abbr,
    d.team_name,
    -- Transfer handling. `team_abbr` above is whichever club the array listed
    -- first, kept only so nothing changes silently. Charts should read
    -- primary_team_abbr instead: the club the player actually played the most
    -- minutes for, resolved from the per-club splits rather than from array
    -- position. For the 99% who never moved the two are identical.
    a.team_count,
    pt.team_abbr        AS primary_team_abbr,
    pt.general_position AS primary_position,
    a.minutes,
    a.goals,
    a.shots,
    a.xgoals,
    a.xassists,
    COALESCE(pen.goals,  0) AS pen_goals,
    COALESCE(pen.shots,  0) AS pen_shots,
    COALESCE(pen.xgoals, 0) AS pen_xgoals,
    GREATEST(a.goals  - COALESCE(pen.goals,  0), 0) AS np_goals,
    GREATEST(a.shots  - COALESCE(pen.shots,  0), 0) AS np_shots,
    GREATEST(a.xgoals - COALESCE(pen.xgoals, 0), 0) AS npxg,
    a.xplace,
    coalesce(pen.xplace, 0) as pen_xplace,
    a.xplace - coalesce(pen.xplace, 0) as np_xplace,
    -- Finishing split into its two halves (round 31). Placement is the
    -- goals-worth of where the shots ended up; the residual is everything it
    -- does not explain -- keeper, deflections, luck. They sum to the margin by
    -- construction, which assert_placement_components_sum keeps true.
    -- Both sides clamped exactly as np_goals and npxg are. Leaving the
    -- goals term unclamped is what assert_placement_components_sum caught on
    -- its first run: eight fixture players whose penalty goals exceeded their
    -- total, where the residual then disagreed with the margin it is supposed
    -- to complete.
    greatest(a.goals - coalesce(pen.goals, 0), 0)
        - greatest(a.xgoals - coalesce(pen.xgoals, 0), 0)
        - (a.xplace - coalesce(pen.xplace, 0)) as finishing_residual
FROM       stg.player_xgoals a
LEFT JOIN  stg.player_xgoals pen
       ON  pen.season    = a.season
      AND  pen.player_id = a.player_id
      AND  pen.variant   = 'Penalty'
JOIN       dw.dim_player p
       ON  p.season = a.season AND p.player_id = a.player_id
LEFT JOIN  dw.dim_team d
       ON  d.season = a.season AND d.team_id = a.team_id
LEFT JOIN  dw.mart_primary_team pt
       ON  pt.season = a.season AND pt.player_id = a.player_id
WHERE a.variant IS NULL;

-- Data quality: every player carrying more than one club this season, with
-- the split that resolves them and a reconciliation column.
--
-- `minutes_unsplit` is the season total from the unfiltered call;
-- `minutes_split` is the sum of the per-club rows. They must match. If they
-- ever stop matching, a split call failed or the API changed, and the
-- attribution silently went back to being a guess -- which is exactly the
-- kind of drift that is invisible without a check like this.
CREATE OR REPLACE VIEW dw.dq_multi_team AS
SELECT
    x.season,
    p.player_name,
    x.team_count,
    x.team_ids_raw,
    df.team_abbr AS listed_first,
    dl.team_abbr AS listed_last,
    pt.team_abbr AS primary_team,
    x.minutes                     AS minutes_unsplit,
    s.minutes_split,
    (s.minutes_split IS NOT NULL AND abs(s.minutes_split - x.minutes) < 0.5) AS reconciles
FROM      stg.player_xgoals x
JOIN      dw.dim_player p  ON p.season = x.season AND p.player_id = x.player_id
LEFT JOIN dw.dim_team   df ON df.season = x.season AND df.team_id = x.team_id
LEFT JOIN dw.dim_team   dl ON dl.season = x.season AND dl.team_id = x.team_id_last
LEFT JOIN dw.mart_primary_team pt ON pt.season = x.season AND pt.player_id = x.player_id
LEFT JOIN (SELECT season, player_id, sum(minutes) AS minutes_split
           FROM stg.player_team_xgoals GROUP BY 1, 2) s
       ON s.season = x.season AND s.player_id = x.player_id
WHERE x.variant IS NULL AND x.team_count > 1
ORDER BY x.minutes DESC;

-- Grain: one row per player per season per action type.
-- Deliberately NOT pre-summed: keeping the breakdown means Playmaking Style
-- (Dribbling vs. Passing) and the Goals Added leaderboard (the total) both
-- come from one table instead of two fetches.
CREATE OR REPLACE VIEW dw.fct_player_goals_added AS
SELECT
    g.season,
    g.player_id,
    p.player_name,
    g.team_id,
    d.team_abbr,
    g.variant AS general_position,
    g.minutes,
    g.action_type,
    g.goals_added_above_avg
FROM      stg.player_goals_added_actions g
JOIN      dw.dim_player p
      ON  p.season = g.season AND p.player_id = g.player_id
LEFT JOIN dw.dim_team d
      ON  d.season = g.season AND d.team_id = g.team_id;

-- ------------------------------------------------- the qualification rule
--
-- qualification.py in SQL. A player qualifies if their minutes clear
-- minutes_per_game x their OWN team's games played -- not the league's, so a
-- team with games in hand is not quietly penalized. Teams with no games
-- figure fall back to the league median; if there is no median either
-- (the API stopped returning any games field), the flat fallback applies.
--
-- Grain: one row per team per season.
CREATE OR REPLACE VIEW dw.mart_qualification AS
WITH league AS (
    SELECT season, median(games) AS median_games
    FROM   dw.fct_team_season
    WHERE  games IS NOT NULL
    GROUP  BY season
)
SELECT
    t.season,
    t.team_id,
    t.team_abbr,
    t.games,
    COALESCE(t.games, l.median_games) AS games_used,
    (t.games IS NULL)                 AS games_imputed,
    CASE
        WHEN p.flat_minutes IS NOT NULL THEN p.flat_minutes
        WHEN COALESCE(t.games, l.median_games) IS NULL THEN p.fallback_minutes
        ELSE p.minutes_per_game * COALESCE(t.games, l.median_games)
    END AS minutes_required
FROM dw.fct_team_season t
LEFT JOIN league l ON l.season = t.season
CROSS JOIN dw.params p;

-- ------------------------------------------------------------------ marts

-- Grain: one row per player per season. The table every player scatter reads.
--
-- per96 is the project's rate convention: a counting stat scaled to 96
-- minutes rather than 90, because 90 ignores stoppage time and NWSL matches
-- reliably run past it. Computed here, once, instead of in each caller.
-- NULLIF guards the divide-by-zero: a player with 0 minutes yields NULL,
-- which plots as absent, rather than an inf that poisons an axis.
CREATE OR REPLACE VIEW dw.mart_player_rates AS
SELECT
    f.season,
    f.player_id,
    f.player_name,
    f.team_id,
    -- The club charts should badge: most minutes played, from the splits.
    COALESCE(f.primary_team_abbr, f.team_abbr) AS team_abbr,
    f.team_abbr AS team_abbr_listed_first,
    f.team_count,
    COALESCE(f.primary_position, f.general_position) AS general_position,
    f.minutes,
    q.minutes_required,
    (f.minutes >= q.minutes_required) AS qualified,
    q.games_imputed,
    f.goals,
    f.shots,
    f.xgoals,
    f.xassists,
    f.npxg,
    f.np_goals,
    f.np_shots,
    f.np_xplace,
    f.finishing_residual,
    f.goals    / NULLIF(f.minutes, 0) * 96 AS goals96,
    f.shots    / NULLIF(f.minutes, 0) * 96 AS shots96,
    f.xgoals   / NULLIF(f.minutes, 0) * 96 AS xg96,
    f.xassists / NULLIF(f.minutes, 0) * 96 AS xa96,
    f.npxg     / NULLIF(f.minutes, 0) * 96 AS npxg96,
    f.np_goals / NULLIF(f.minutes, 0) * 96 AS npgoals96,
    -- Finishing signal: goals above expectation, in non-penalty terms.
    -- Positive = outscoring the chances taken.
    f.np_goals - f.npxg                    AS np_goals_minus_npxg,
    f.npxg     / NULLIF(f.np_shots, 0)     AS npxg_per_shot
FROM      dw.fct_player_season f
LEFT JOIN dw.mart_qualification q
      ON  q.season = f.season AND q.team_id = f.team_id;

-- Grain: one row per player per season.
-- Total g+ plus the two components Playmaking Style plots, pivoted out of the
-- action-type breakdown. Doing this as a conditional SUM rather than a join
-- back to the same table is what keeps the grain honest -- see the note at
-- the top of this file about joins that silently multiply rows.
CREATE OR REPLACE VIEW dw.mart_goals_added AS
SELECT
    g.season,
    g.player_id,
    any_value(g.player_name) AS player_name,
    g.team_id,
    any_value(g.team_abbr)   AS team_abbr,
    any_value(g.minutes)     AS minutes,
    SUM(g.goals_added_above_avg)                                              AS ga_total,
    SUM(CASE WHEN g.action_type = 'Dribbling'    THEN g.goals_added_above_avg END) AS ga_dribbling,
    SUM(CASE WHEN g.action_type = 'Passing'      THEN g.goals_added_above_avg END) AS ga_passing,
    SUM(CASE WHEN g.action_type = 'Shooting'     THEN g.goals_added_above_avg END) AS ga_shooting,
    SUM(CASE WHEN g.action_type = 'Receiving'    THEN g.goals_added_above_avg END) AS ga_receiving,
    SUM(CASE WHEN g.action_type = 'Interrupting' THEN g.goals_added_above_avg END) AS ga_interrupting,
    SUM(CASE WHEN g.action_type = 'Fouling'      THEN g.goals_added_above_avg END) AS ga_fouling,
    SUM(g.goals_added_above_avg) / NULLIF(any_value(g.minutes), 0) * 96        AS ga96
FROM  dw.fct_player_goals_added g
GROUP BY g.season, g.player_id, g.team_id;

-- Grain: one row per goalkeeper per season.
-- Goals saved above expected is the keeper equivalent of goals minus xG:
-- xG faced minus goals actually conceded. Positive = saved more than the
-- shots deserved.
CREATE OR REPLACE VIEW dw.mart_goalkeepers AS
SELECT
    k.season,
    k.player_id,
    p.player_name,
    k.team_id,
    d.team_abbr,
    k.minutes,
    k.shots_faced,
    k.goals_conceded,
    k.xgoals_faced,
    k.xgoals_faced - k.goals_conceded                     AS goals_saved_above_expected,
    k.shots_faced / NULLIF(k.minutes, 0) * 96             AS shots_faced96,
    (k.xgoals_faced - k.goals_conceded) / NULLIF(k.minutes, 0) * 96 AS gsae96
FROM      stg.goalkeeper_xgoals k
JOIN      dw.dim_player p ON p.season = k.season AND p.player_id = k.player_id
LEFT JOIN dw.dim_team   d ON d.season = k.season AND d.team_id   = k.team_id;
