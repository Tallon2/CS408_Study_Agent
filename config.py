import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ZHIPU_API_KEY")
MODEL = "glm-4-flash"

if not API_KEY:
    raise ValueError("未找到 ZHIPU_API_KEY，请检查 .env 文件")