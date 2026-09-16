FROM python:3.12-slim

WORKDIR /app

# 先装依赖（利用 docker 层缓存）
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic-settings>=2.5" \
    "langgraph>=0.2.50" "langchain-openai>=0.2" "langchain-core>=0.3" "python-dotenv>=1.0"

COPY app ./app

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
