FROM python:3.11-slim

# FFmpeg および OpenCV描画に必要なシステムライブラリのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションソースのコピー
COPY core/ ./core/
COPY main.py .
COPY LICENSE .

# ボリューム設定 (入力音声や出力動画の受け渡し用)
RUN mkdir -p /app/shared

ENTRYPOINT [ "python", "main.py" ]
