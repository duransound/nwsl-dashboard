-- 2026-09-02. Six players changed clubs mid-season; ASA returns them with a
-- two-element team_id and every metric summed. The per-club split obtained by
-- team_id-filtered calls must add back up to the unfiltered total, to the
-- digit -- verified live on Ally Sentnor (1070 + 1009 = 2079 minutes,
-- 26 + 38 = 64 shots, 2.8846 + 2.7988 = 5.6834 xG).
--
-- The day this stops passing, a split call failed or the endpoint changed
-- shape, and team attribution has quietly gone back to being a guess.
select player_name, minutes_unsplit, minutes_split
from {{ ref('dq_multi_team') }}
where not reconciles
