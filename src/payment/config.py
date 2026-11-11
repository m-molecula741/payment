from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://payment:payment@localhost:5432/payment"
    rabbitmq_url: str = "amqp://payment:payment@localhost:5672/"
    api_key: str = "dev-api-key"
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    webhook_timeout_seconds: float = 10.0
    webhook_attempts: int = 3
    processing_min_seconds: float = 2.0
    processing_max_seconds: float = 5.0
    processing_success_rate: float = 0.9


settings = Settings()
