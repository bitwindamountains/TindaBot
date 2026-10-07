from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite:///data/tindabot.db")
    meta_app_secret: SecretStr = SecretStr("")
    meta_verify_token: SecretStr = SecretStr("")
    meta_page_access_token: SecretStr = SecretStr("")
    meta_page_id: str = ""
    meta_app_id: str = ""
    meta_graph_version: str = ""
    admin_token: SecretStr = SecretStr("")
    status_token: SecretStr = SecretStr("")
    delivery_mode: Literal["dry_run", "live"] = "dry_run"
    automation_enabled: bool = True
    production_acknowledged: bool = False
    google_sheet_id: str = ""
    google_service_account_json_b64: SecretStr = SecretStr("")
    seller_notify_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    shop_name: str = "TindaBot Demo"
    privacy_url: str = ""
    shipping_minor: int = Field(8000, ge=0, le=100_000_000)
    pickup_address: str = "Contact the seller for pickup details"
    payment_methods: str = "cod"
    gcash_instructions: str = ""
    bank_instructions: str = ""
    max_messages_per_minute: int = Field(20, ge=1, le=1000)
    catalog_max_age_seconds: int = Field(3600, ge=60)
    order_pii_retention_days: int = Field(365, ge=1)
    event_retention_days: int = Field(7, ge=1)
    unpaid_expiry_hours: int = Field(24, ge=1)
    worker_poll_seconds: float = Field(1, ge=0.1, le=60)
    max_body_bytes: int = Field(262144, ge=1024)
    max_attempts: int = Field(6, ge=1, le=20)

    @property
    def payments(self) -> list[str]:
        return [p.strip() for p in self.payment_methods.split(",") if p.strip()]

    @model_validator(mode="after")
    def validate_configuration(self):
        if not self.payments or set(self.payments) - {"cod", "gcash", "bank"}:
            raise ValueError("PAYMENT_METHODS must contain cod, gcash and/or bank")
        if "gcash" in self.payments and not self.gcash_instructions:
            raise ValueError("GCASH_INSTRUCTIONS is required")
        if "bank" in self.payments and not self.bank_instructions:
            raise ValueError("BANK_INSTRUCTIONS is required")
        if self.app_env == "production":
            url = make_url(self.database_url.get_secret_value())
            if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") not in {
                "require",
                "verify-ca",
                "verify-full",
            }:
                raise ValueError("Production requires PostgreSQL with TLS")
            if not self.production_acknowledged or self.delivery_mode != "live":
                raise ValueError(
                    "Production requires explicit launch acknowledgement and live delivery"
                )
            for key in ("meta_app_secret", "meta_verify_token", "admin_token", "status_token"):
                if len(getattr(self, key).get_secret_value()) < 32:
                    raise ValueError(f"Production requires a strong {key.upper()}")
            if self.admin_token == self.status_token:
                raise ValueError("Operator and status credentials must differ")
            if not self.privacy_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS privacy notice")
        if self.delivery_mode == "live":
            for key in (
                "meta_page_id",
                "meta_app_id",
                "meta_graph_version",
                "google_sheet_id",
                "seller_notify_email",
                "smtp_host",
                "smtp_user",
                "smtp_from",
            ):
                if not getattr(self, key):
                    raise ValueError(f"Live delivery requires {key.upper()}")
            for key in (
                "meta_page_access_token",
                "google_service_account_json_b64",
                "smtp_password",
            ):
                if not getattr(self, key).get_secret_value():
                    raise ValueError(f"Live delivery requires {key.upper()}")
            import re

            if not re.fullmatch(r"v\d+\.\d+", self.meta_graph_version):
                raise ValueError("Pin META_GRAPH_VERSION to a supported version")
        return self

    def prepare_local_directory(self):
        url = make_url(self.database_url.get_secret_value())
        if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
