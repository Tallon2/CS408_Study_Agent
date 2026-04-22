"""
config.py — 兼容层（向后兼容，逐步废弃）

⚠️ 已废弃：此文件仅作为向后兼容层存在，不得在新代码中引用。
   新代码请使用：
       from core.settings import get_settings
       settings = get_settings()

   预计在 Phase 6 完成后彻底移除。
"""
from core.settings import get_settings

_s = get_settings()

# 兼容旧 import: from config import API_KEY
API_KEY: str = _s.ZHIPU_API_KEY

# 兼容旧 import: from config import MODEL
MODEL: str = _s.MODEL_NAME