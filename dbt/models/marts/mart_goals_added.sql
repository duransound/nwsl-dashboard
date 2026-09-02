-- Grain: one row per player per season. Conditional SUM is the pivot -- a
-- self-join here would multiply the grain by the number of action types.
select
    g.season,
    g.player_id,
    any_value(g.player_name) as player_name,
    g.team_id,
    any_value(g.team_abbr)   as team_abbr,
    any_value(g.minutes)     as minutes,
    sum(g.goals_added_above_avg)                                                   as ga_total,
    sum(case when g.action_type = 'Dribbling'    then g.goals_added_above_avg end) as ga_dribbling,
    sum(case when g.action_type = 'Passing'      then g.goals_added_above_avg end) as ga_passing,
    sum(case when g.action_type = 'Shooting'     then g.goals_added_above_avg end) as ga_shooting,
    sum(case when g.action_type = 'Receiving'    then g.goals_added_above_avg end) as ga_receiving,
    sum(case when g.action_type = 'Interrupting' then g.goals_added_above_avg end) as ga_interrupting,
    sum(case when g.action_type = 'Fouling'      then g.goals_added_above_avg end) as ga_fouling,
    sum(g.goals_added_above_avg) / nullif(any_value(g.minutes), 0) * 96            as ga96
from {{ ref('fct_player_goals_added') }} g
group by g.season, g.player_id, g.team_id
