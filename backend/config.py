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


def _resolve_groq_key() -> str:
    """
    In Lambda, GROQ_API_KEY_PATH points to an SSM SecureString — fetch it at
    cold start so key rotation only requires updating SSM, not redeploying.
    Locally, fall back to GROQ_API_KEY from .env.
    """
    ssm_path = os.getenv("GROQ_API_KEY_PATH", "")
    if ssm_path:
        import boto3
        ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "us-east-1"))
        return ssm.get_parameter(Name=ssm_path, WithDecryption=True)["Parameter"]["Value"]
    return os.getenv("GROQ_API_KEY", "")


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
    return settings
