import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Walk up from backend/ to find .env in the project root
_here = Path(__file__).parent
_env_file = next(
    (str(p / ".env") for p in [_here, _here.parent] if (p / ".env").exists()),
    ".env",
)


def _resolve_ssm_or_env(ssm_path_env: str, direct_env: str) -> str:
    """
    Fetch a secret from SSM SecureString (Lambda) or fall back to a plain
    env var (local dev). Decouples key rotation from redeployment.
    """
    ssm_path = os.getenv(ssm_path_env, "")
    if ssm_path:
        import boto3
        ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "us-east-1"))
        return ssm.get_parameter(Name=ssm_path, WithDecryption=True)["Parameter"]["Value"]
    return os.getenv(direct_env, "")


def _resolve_groq_key() -> str:
    return _resolve_ssm_or_env("GROQ_API_KEY_PATH", "GROQ_API_KEY")


def _resolve_voyage_key() -> str:
    return _resolve_ssm_or_env("VOYAGE_API_KEY_PATH", "VOYAGE_API_KEY")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")

    # Groq — resolved from SSM in Lambda, from .env locally
    groq_api_key: str = ""

    # Voyage AI — optional, enables semantic embeddings; falls back to Jaccard if unset
    voyage_api_key: str = ""

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # DynamoDB
    dynamodb_leads_table: str = "leads"
    dynamodb_jobs_table: str = "batch_jobs"

    # S3
    s3_input_bucket: str = ""
    s3_output_bucket: str = ""

    # SQS
    sqs_queue_url: str = ""

    # Runtime
    environment: str = "local"  # "local" | "staging" | "production"
    log_level: str = "INFO"

    # Agent behaviour
    lead_score_priority_threshold: float = 0.75
    lead_score_standard_threshold: float = 0.50
    max_concurrent_leads: int = 10

    @property
    def is_local(self) -> bool:
        return self.environment == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if not settings.groq_api_key:
        settings.groq_api_key = _resolve_groq_key()
    if not settings.voyage_api_key:
        settings.voyage_api_key = _resolve_voyage_key()
    return settings
