"""
大模型API调用封装（阿里云百炼 DashScope OpenAI兼容模式）
- chat: 对话生成
- chat_stream: 流式对话
"""
import requests
import time
from config import API_KEY, CHAT_MODEL_FAST, CHAT_MODEL_PREMIUM

API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def chat(messages: list[dict], model: str = None, temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """调用阿里云通义千问大模型"""
    if model is None:
        model = CHAT_MODEL_FAST
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=60)
            # 429 限流：指数退避重试
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)  # 5s/10s/15s
                print(f"API限流(429)，等待{wait}秒后第{attempt+1}次重试...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.ReadTimeout:
            print(f"请求超时，第{attempt+1}次重试...")
            time.sleep(2 ** attempt)
        except requests.exceptions.HTTPError:
            raise
        except Exception as e:
            print(f"API调用异常：{e}")
            raise
    return "服务暂时不可用，请稍后再试"


def chat_stream(messages: list[dict], model: str = None, temperature: float = 0.7):
    """流式调用通义千问（用于Streamlit聊天展示）"""
    if model is None:
        model = CHAT_MODEL_FAST
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2000,
        "stream": True
    }
    resp = requests.post(url, json=body, headers=headers, timeout=60, stream=True)
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            import json
            try:
                data = json.loads(data_str)
                delta = data["choices"][0].get("delta", {})
                if "content" in delta:
                    yield delta["content"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# 测试入口
if __name__ == "__main__":
    print("测试 chat...")
    result = chat([{"role": "user", "content": "你好"}])
    print(f"回复: {result}")
    print("✅ API 测试通过")
