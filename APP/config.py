from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str 
    SECRET_KEY: str = "troque-esta-chave"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = "env"
        extra = "ignore" # Ignora variáveis extras no .envs

settings = Settings()