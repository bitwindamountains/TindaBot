import pytest
from pydantic import ValidationError

from tindabot.config import Settings


def test_production_rejects_sqlite_and_missing_launch_configuration():
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(_env_file=None, app_env="production", database_url="sqlite:///:memory:")


def test_live_mode_requires_real_integrations():
    with pytest.raises(ValidationError, match="META_PAGE_ID"):
        Settings(_env_file=None, delivery_mode="live")


def test_invalid_payment_configuration_fails_fast():
    with pytest.raises(ValidationError, match="GCASH_INSTRUCTIONS"):
        Settings(_env_file=None, payment_methods="gcash")


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "production", "admin_token": "config-secret-sentinel"},
        {"smtp_port": "config-secret-sentinel"},
    ],
)
def test_configuration_errors_hide_raw_inputs(values):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "config-secret-sentinel" not in str(error.value)
    assert "input_value" not in str(error.value)
