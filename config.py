import os

from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('27666286'))
API_HASH = str(os.getenv('bb4c9fe90f5ea9b6d9fae18f2ea6c7fa'))
BOT_TOKEN = str(os.getenv('7223341399:AAFrbwFlc3mmEZFMDm6C7uzkZ1SQheQMAIA'))
SESSIONS_DIRECTORY = os.getenv('SESSIONS_DIRECTORY')
DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE_ECHO = bool(os.getenv('DATABASE_ECHO'))
