FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 以可编辑模式安装项目包（消除 sys.path hack）
RUN pip install -e .

# 创建存储目录
RUN mkdir -p storage/sessions storage/tasks storage/user_profile \
    storage/chroma_db storage/bm25_index

EXPOSE 8000 7861

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
