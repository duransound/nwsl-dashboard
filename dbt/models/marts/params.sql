-- One row, always. Cross-joined wherever a threshold is needed, so the rule
-- lives in SQL but the numbers come from the loader's flags.
select
    coalesce(max(case when key = 'minutes_per_game' then try_cast(value as double) end), 30)  as minutes_per_game,
              max(case when key = 'flat_minutes'    then try_cast(value as double) end)       as flat_minutes,
    coalesce(max(case when key = 'fallback_minutes' then try_cast(value as double) end), 500) as fallback_minutes
from {{ source('dw_settings', 'settings') }}
