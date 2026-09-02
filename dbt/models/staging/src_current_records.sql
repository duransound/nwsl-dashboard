{{ config(materialized='view', schema='raw', alias='current_records_dbt') }}
-- Every staging model reads through here, so an unfinished load can never
-- reach a chart: raw.loads only gets finished_at stamped on success, and a
-- half-written load is therefore invisible rather than half-visible.
with current_load as (
    select season, max(load_id) as load_id
    from {{ source('raw', 'loads') }}
    where finished_at is not null
    group by season
)
select r.*
from {{ source('raw', 'asa_records') }} r
join current_load c on r.season = c.season and r.load_id = c.load_id
