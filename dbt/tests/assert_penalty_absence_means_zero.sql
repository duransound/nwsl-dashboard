-- A player missing from the shot_pattern=Penalty response took no penalties;
-- it does not mean their npxG is unknown. If the coalesce were dropped they
-- would go NULL and vanish from every finishing chart.
select player_id
from {{ ref('fct_player_season') }}
where pen_xgoals is null or pen_goals is null or pen_shots is null
