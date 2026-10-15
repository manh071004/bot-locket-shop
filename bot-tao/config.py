import os
from dotenv import load_dotenv

load_dotenv()

# Uu tien BOT_TAO_TOKEN de khong trung voi BOT_TOKEN cua bot-v2 tren Render
BOT_TOKEN = os.getenv("BOT_TAO_TOKEN") or os.getenv("BOT_TOKEN_TAO") or "8998215728:AAFzSqnkolufJIZZoY2rMMExfvimvgzQlQ4"
BOT_USERNAME = os.getenv("BOT_TAO_USERNAME", "Shoppretool_bot")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql++asyncpg://user:password@localhost/botstore")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
