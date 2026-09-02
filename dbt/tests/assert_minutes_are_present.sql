-- Round 15. minutes_played on some endpoints, minutes on others. If the
-- coalesce breaks, minutes goes NULL, every per-96 rate goes NULL with it,
-- and the scatters render empty rather than wrong -- which is worse, because
-- it looks like a slow week.
select player_id
from {{ ref('stg_player_xgoals') }}
where minutes is null
