"""Application configuration for the Terraform Platform Agent."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPOSITORY_ROOT / ".env")


class Settings(BaseSettings):
    """Validated configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    google_cloud_project: str = Field(alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(
        default="us-central1",
        alias="GOOGLE_CLOUD_LOCATION",
    )
    google_genai_use_vertexai: bool = Field(
        default=True,
        alias="GOOGLE_GENAI_USE_VERTEXAI",
    )

    adk_model: str = Field(
        default="gemini-2.5-flash",
        alias="ADK_MODEL",
    )

    terraform_executable: str = Field(
        default="terraform",
        alias="TERRAFORM_EXECUTABLE",
    )
    terraform_output_root: str = Field(
        default="generated",
        alias="TERRAFORM_OUTPUT_ROOT",
    )
    terraform_command_timeout: int = Field(
        default=1800,
        ge=10,
        le=3600,
        alias="TERRAFORM_COMMAND_TIMEOUT",
    )

    terraform_mcp_enabled: bool = Field(
        default=False,
        alias="TERRAFORM_MCP_ENABLED",
    )
    terraform_allow_apply: bool = Field(
        default=False,
        alias="TERRAFORM_ALLOW_APPLY",
    )
    terraform_allow_destroy: bool = Field(
        default=False,
        alias="TERRAFORM_ALLOW_DESTROY",
    )
    terraform_allow_state_modification: bool = Field(
        default=False,
        alias="TERRAFORM_ALLOW_STATE_MODIFICATION",
    )

    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    @property
    def repository_root(self) -> Path:
        return REPOSITORY_ROOT

    @property
    def output_root(self) -> Path:
        return (self.repository_root / self.terraform_output_root).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached settings object."""

    settings = Settings()
    settings.output_root.mkdir(parents=True, exist_ok=True)
    return settings