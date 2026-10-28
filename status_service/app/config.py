from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_status"
    rabbitmq_url: str = "amqp://fleet:fleet@localhost:5672/"

    batch_size: int = 100
    flush_interval: float = 1.0
    prefetch: int = 200

    django_api_url: str = "http://127.0.0.1:8000"

    redis_url: str = "redis://localhost:6379/0"
    access_cache_ttl: int = 60


settings = Settings()



