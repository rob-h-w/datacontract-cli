"""Databricks nested model CTE (WITH clause) query generation.

For Databricks SQL warehouse backends that don't support CREATE TABLE/VIEW,
compile nested struct and array models to WITH-clause queries for read-only access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_data_contract_standard.model import OpenDataContractStandard, SchemaProperty


def build_databricks_virtual_model_queries_for_contract(
    data_contract: "OpenDataContractStandard | None",
    schema_name: str = "all",
) -> dict[str, str]:
    """Build query-only nested models for Databricks SQL backends using WITH clauses.

    The check-builder can target array item checks at ``{model}__{array_field}``.
    On a SQL warehouse backend we avoid creating helper tables and instead compile
    those synthetic models to CTE-based SELECTs resolved on demand.
    """
    if data_contract is None or not data_contract.schema_:
        return {}

    virtual_specs: dict[str, dict[str, str]] = {}
    for schema_obj in data_contract.schema_:
        if schema_name != "all" and schema_obj.name != schema_name:
            continue
        model_name = schema_obj.physicalName or schema_obj.name
        _collect_databricks_virtual_model_specs(model_name, schema_obj.properties, virtual_specs)

    return {model: _render_databricks_virtual_model_query(model, virtual_specs) for model in virtual_specs}


def _collect_databricks_virtual_model_specs(
    parent_model: str,
    properties: list["SchemaProperty"] | None,
    specs: dict[str, dict[str, str]],
):
    """Recursively collect nested struct and array model specifications."""
    for prop in properties or []:
        field_name = prop.physicalName or prop.name
        field_type = ((prop.physicalType or prop.logicalType) or "").lower()
        if field_type in {"object", "record", "struct"} and prop.properties:
            nested_model = f"{parent_model}__{field_name}"
            where_not_null = f" WHERE `{field_name}` IS NOT NULL" if not prop.required else ""
            specs[nested_model] = {
                "parent": parent_model,
                "template": f"SELECT `{field_name}`.* FROM {{source}}{where_not_null}",
            }
            _collect_databricks_virtual_model_specs(nested_model, prop.properties, specs)
        elif field_type == "array" and prop.items and prop.items.properties:
            nested_model = f"{parent_model}__{field_name}"
            specs[nested_model] = {
                "parent": parent_model,
                "template": (
                    "SELECT __dc_nested__.* "
                    f"FROM {{source}} LATERAL VIEW OUTER explode_outer(`{field_name}`) AS __dc_nested__"
                ),
            }
            _collect_databricks_virtual_model_specs(nested_model, prop.items.properties, specs)


def _render_databricks_virtual_model_query(model: str, specs: dict[str, dict[str, str]]) -> str:
    """Render a single nested model as a WITH-clause CTE query."""
    spec = specs[model]
    parent = spec["parent"]
    if parent in specs:
        parent_query = _render_databricks_virtual_model_query(parent, specs)
    else:
        parent_query = f"SELECT * FROM {parent}"
    source = "__dc_source__"
    return f"WITH {source} AS ({parent_query}) {spec['template'].format(source=source)}"
