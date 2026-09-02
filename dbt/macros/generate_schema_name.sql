{#
  dbt's default puts every model in <target_schema>_<custom_schema>, which
  would rename stg -> dw_stg and break every query already written against
  this warehouse. This override uses the custom schema verbatim, so models
  land in exactly `stg` and `dw` -- the same names the hand-written .sql
  files produced.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
