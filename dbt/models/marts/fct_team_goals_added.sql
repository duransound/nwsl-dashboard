-- Grain: one row per team per season. Sums the nested action breakdown.
select
    a.season,
    a.team_id,
    d.team_abbr,
    d.team_name,
    sum(a.goals_added_for)                                  as ga_for,
    sum(a.goals_added_against)                              as ga_against,
    sum(a.goals_added_for) - sum(a.goals_added_against)     as ga_net
from {{ ref('stg_team_goals_added_actions') }} a
join {{ ref('dim_team') }} d on d.season = a.season and d.team_id = a.team_id
group by 1, 2, 3, 4
