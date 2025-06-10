# Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY short_url.py .
COPY templates/ templates/

# 创建数据库目录
RUN mkdir -p /app/data

# 设置环境变量
ENV FLASK_APP=short_url.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 5000

# 启动应用
CMD ["python", "short_url.py"]
