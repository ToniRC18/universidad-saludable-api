from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_PORT: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()
