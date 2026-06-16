"""Unit tests for Databricks auth-method selection in connect_ibis.
These do not hit Databricks: Backend.do_connect is patched and we only
assert which auth kwargs the dispatch passes for a given set of env vars.
"""
import pytest
from open_data_contract_standard.model import Server
from ibis.backends.databricks import Backend as DatabricksBackend
from datacontract.engines.ibis.connections.connect import connect_ibis
from datacontract.model.run import Run
DATABRICKS_ENV_VARS = [
    "DATACONTRACT_DATABRICKS_TOKEN",
    "DATACONTRACT_DATABRICKS_HTTP_PATH",
    "DATACONTRACT_DATABRICKS_SERVER_HOSTNAME",
    "DATACONTRACT_DATABRICKS_CLIENT_ID",
    "DATACONTRACT_DATABRICKS_CLIENT_SECRET",
    "DATACONTRACT_DATABRICKS_PROFILE",
    "DATACONTRACT_DATABRICKS_AUTH_TYPE",
]
@pytest.fixture
def clean_databricks_env(monkeypatch):
    for name in DATABRICKS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch
@pytest.fixture
def captured_connect(monkeypatch):
    """Patch Backend.do_connect to record the kwargs passed by connect_ibis.
    Our Databricks connector creates a _NoVolumeBackend subclass and calls
    .connect() on it. BaseBackend.connect() -> reconnect() -> do_connect(),
    so patching do_connect on the parent class intercepts the call.
    """
    calls = {}
    def fake_do_connect(self, *args, **kwargs):
        calls.update(kwargs)
        # Set the minimal attributes do_connect normally sets so that the
        # returned backend object is usable (tests only check calls, not queries).
        from unittest.mock import MagicMock
        self.con = MagicMock()
        self._memtable_volume = "dc-test"
        self._memtable_catalog = "cat"
        self._memtable_database = "db"
    monkeypatch.setattr(DatabricksBackend, "do_connect", fake_do_connect)
    return calls
def _server():
    return Server(type="databricks", host="dbc-x.cloud.databricks.com", catalog="cat", schema="sch")
def _connect(server=None):
    return connect_ibis(Run.create_run(), data_contract=None, server=server or _server())
def test_personal_access_token_is_default(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_TOKEN", "dapiTOKEN")
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
    result = _connect()
    assert result is not None
    assert captured_connect["access_token"] == "dapiTOKEN"
    assert captured_connect["http_path"] == "/sql/1.0/warehouses/abc"
    assert captured_connect["server_hostname"] == "dbc-x.cloud.databricks.com"
    assert captured_connect["catalog"] == "cat"
    assert captured_connect["schema"] == "sch"
    assert "credentials_provider" not in captured_connect
def test_oauth_service_principal_m2m(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_CLIENT_ID", "client-id")
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_CLIENT_SECRET", "client-secret")
    _connect()
    assert "access_token" not in captured_connect
    assert callable(captured_connect["credentials_provider"])
def test_token_wins_over_service_principal(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_TOKEN", "dapiTOKEN")
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_CLIENT_ID", "client-id")
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_CLIENT_SECRET", "client-secret")
    _connect()
    assert captured_connect["access_token"] == "dapiTOKEN"
    assert "credentials_provider" not in captured_connect
def test_config_profile(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_PROFILE", "my-profile")
    _connect()
    assert "access_token" not in captured_connect
    assert callable(captured_connect["credentials_provider"])
def test_explicit_auth_type_for_u2m_browser(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_AUTH_TYPE", "databricks-oauth")
    _connect()
    assert captured_connect["auth_type"] == "databricks-oauth"
    assert "access_token" not in captured_connect
    assert "credentials_provider" not in captured_connect
def test_hostname_falls_back_to_env(clean_databricks_env, captured_connect):
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_TOKEN", "dapiTOKEN")
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_SERVER_HOSTNAME", "from-env.cloud.databricks.com")
    _connect(Server(type="databricks", catalog="cat", schema="sch"))
    assert captured_connect["server_hostname"] == "from-env.cloud.databricks.com"
def test_no_volume_created_on_connect(clean_databricks_env, monkeypatch):
    """_post_connect must never execute CREATE VOLUME."""
    clean_databricks_env.setenv("DATACONTRACT_DATABRICKS_TOKEN", "dapiTOKEN")
    create_volume_called = []
    def fake_do_connect(self, *args, **kwargs):
        from unittest.mock import MagicMock
        self.con = MagicMock()
        self._memtable_volume = "dc-test"
        self._memtable_catalog = "cat"
        self._memtable_database = "db"
    def fake_post_connect(self, *, memtable_volume):
        create_volume_called.append(memtable_volume)
    monkeypatch.setattr(DatabricksBackend, "do_connect", fake_do_connect)
    # We deliberately DON't patch _post_connect here: if _NoVolumeBackend
    # correctly overrides it, fake_post_connect will never be reached.
    # Instead, confirm _post_connect on the REAL backend would have been called,
    # while our subclass silently skips it.
    original_post_connect = DatabricksBackend._post_connect
    try:
        DatabricksBackend._post_connect = fake_post_connect
        _connect()
        # The _NoVolumeBackend override should have prevented this from being
        # called, since it defines its own no-op _post_connect.
        assert create_volume_called == [], (
            "_post_connect was called despite _NoVolumeBackend override. "
            "CREATE VOLUME would have been attempted."
        )
    finally:
        DatabricksBackend._post_connect = original_post_connect
def test_missing_auth_raises(clean_databricks_env, captured_connect):
    from datacontract.model.exceptions import DataContractException
    with pytest.raises(DataContractException):
        _connect()
