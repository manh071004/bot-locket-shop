import os
from dotenv import load_dotenv

load_dotenv()

# Token chính xác của @Shoppretool_bot
BOT_TOKEN = os.getenv("BOT_TAO_TOKEN") or os.getenv("BOT_TOKEN_TAO") or "8998215728:AAFzSqnkolufJcZZoY2rMMExfvimvgzQlQ4"
BOT_USERNAME = os.getenv("BOT_TAO_USERNAME", "Shoppretool_bot")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8088")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/botstore")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
