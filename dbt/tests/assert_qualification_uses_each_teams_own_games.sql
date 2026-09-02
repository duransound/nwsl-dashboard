-- Round 22. The bar is minutes_per_game x THAT TEAM's games played. If it
-- ever collapses to one league-wide number, teams with games in hand are
-- silently penalized -- and the symptom is just "fewer players than usual",
-- which reads as a quiet week rather than a bug.
select q.team_abbr, q.games, q.minutes_required, p.minutes_per_game
from {{ ref('mart_qualification') }} q
cross join {{ ref('params') }} p
where p.flat_minutes is null
  and q.games is not null
  and abs(q.minutes_required - p.minutes_per_game * q.games) > 1e-9
