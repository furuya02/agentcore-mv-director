FROM public.ecr.aws/docker/library/python:3.12-slim-trixie

# ffmpeg（連結・音声合成・フレーム抽出）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/output

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mvcore/ ./mvcore/
COPY main.py ./main.py

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080

CMD ["python", "-m", "main"]
