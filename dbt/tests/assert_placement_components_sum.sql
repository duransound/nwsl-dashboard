-- Round 31. The Placement vs. Luck tab plots two numbers that must add back
-- up to the finishing margin the Finishing tab plots. They are computed in
-- different expressions, so a change to one and not the other would leave the
-- two tabs quietly disagreeing about the same player -- exactly the failure
-- round 23 hit when the MVP tracker started arguing with the finishing tab.
select
    player_id,
    np_goals - npxg              as margin,
    np_xplace,
    finishing_residual,
    (np_xplace + finishing_residual) - (np_goals - npxg) as drift
from {{ ref('mart_player_rates') }}
where abs((np_xplace + finishing_residual) - (np_goals - npxg)) > 1e-9
