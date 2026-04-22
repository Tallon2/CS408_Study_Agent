import os
import sys
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.llm_client import get_llm_client

def test_connection():
    client = get_llm_client()
    print(f"🔍 正在测试 LLM 连接...")
    print(f"   模型: {client.default_model}\n")

    response = client.chat.completions.create(
        model=client.default_model,
        messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}]
    )

    reply = response.choices[0].message.content
    print(f"✅ 连接成功！模型回复：\n{reply}")
    print(f"\n📊 Token 消耗：{response.usage.total_tokens} tokens")

if __name__ == "__main__":
    test_connection()