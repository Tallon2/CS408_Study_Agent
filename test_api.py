from zhipuai import ZhipuAI
from config import API_KEY, MODEL

def test_connection():
    print(f"🔍 正在测试智谱 AI 连接...")
    print(f"   模型: {MODEL}")
    print(f"   API Key: {API_KEY[:8]}...{API_KEY[-4:]}\n")

    client = ZhipuAI(api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}]
    )

    reply = response.choices[0].message.content
    print(f"✅ 连接成功！模型回复：\n{reply}")
    print(f"\n📊 Token 消耗：{response.usage.total_tokens} tokens")

if __name__ == "__main__":
    test_connection()