from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

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
    return Settings()
