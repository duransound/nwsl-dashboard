-- Round 15's nested-shape bug, asserted from the other end: the pivoted total
-- must equal the sum of its own action rows. A join that multiplied the grain
-- would inflate this by exactly the number of action types.
select m.player_id, m.ga_total, f.summed
from {{ ref('mart_goals_added') }} m
join (select player_id, sum(goals_added_above_avg) as summed
      from {{ ref('fct_player_goals_added') }} group by 1) f
  on f.player_id = m.player_id
where abs(m.ga_total - f.summed) > 1e-9
