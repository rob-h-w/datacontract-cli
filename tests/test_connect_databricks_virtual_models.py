from datacontract.data_contract import DataContract
from datacontract.engines.ibis.connections.databricks_nested_models import (
    build_databricks_virtual_model_queries_for_contract,
)
def test_builds_virtual_queries_for_structs_and_arrays():
    contract = """
apiVersion: v3.0.2
kind: DataContract
id: nested
version: 1.0.0
status: active
schema:
  - name: orders
    properties:
      - name: customer
        logicalType: object
        properties:
          - name: email
            logicalType: string
      - name: discounts
        logicalType: array
        items:
          logicalType: object
          properties:
            - name: code
              logicalType: string
"""
    odcs = DataContract(data_contract_str=contract).get_data_contract()
    queries = build_databricks_virtual_model_queries_for_contract(odcs)
    assert "orders__customer" in queries
    assert "orders__discounts" in queries
    assert "WITH __dc_source__ AS (SELECT * FROM orders)" in queries["orders__customer"]
    assert "SELECT `customer`.* FROM __dc_source__" in queries["orders__customer"]
    assert "explode_outer(`discounts`)" in queries["orders__discounts"]
def test_build_virtual_queries_respects_schema_filter():
    contract = """
apiVersion: v3.0.2
kind: DataContract
id: nested
version: 1.0.0
status: active
schema:
  - name: orders
    properties:
      - name: discounts
        logicalType: array
        items:
          logicalType: object
          properties:
            - name: code
              logicalType: string
  - name: customers
    properties:
      - name: addresses
        logicalType: array
        items:
          logicalType: object
          properties:
            - name: city
              logicalType: string
"""
    odcs = DataContract(data_contract_str=contract).get_data_contract()
    queries = build_databricks_virtual_model_queries_for_contract(odcs, schema_name="orders")
    assert "orders__discounts" in queries
    assert "customers__addresses" not in queries
