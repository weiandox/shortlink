#!/bin/bash

# build.sh - 构建和推送Docker镜像脚本

# 配置变量
DOCKER_USERNAME="hunterluo"  # 替换为你的Docker Hub用户名
IMAGE_NAME="shortlink"
TAG="latest"
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}:${TAG}"

echo "开始构建短链服务Docker镜像..."

# 检查必要文件是否存在
if [ ! -f "short_url.py" ]; then
    echo "错误: short_url.py 文件不存在"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo "错误: requirements.txt 文件不存在"
    exit 1
fi

if [ ! -f "Dockerfile" ]; then
    echo "错误: Dockerfile 文件不存在"
    exit 1
fi

# 构建Docker镜像
echo "构建镜像: ${FULL_IMAGE_NAME}"
docker build -t ${FULL_IMAGE_NAME} .

if [ $? -ne 0 ]; then
    echo "错误: Docker镜像构建失败"
    exit 1
fi

echo "镜像构建成功!"

# 询问是否推送到Docker Hub
read -p "是否推送镜像到Docker Hub? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "登录Docker Hub..."
    docker login
    
    if [ $? -eq 0 ]; then
        echo "推送镜像到Docker Hub..."
        docker push ${FULL_IMAGE_NAME}
        
        if [ $? -eq 0 ]; then
            echo "镜像推送成功!"
            echo "可以使用以下命令拉取镜像:"
            echo "docker pull ${FULL_IMAGE_NAME}"
        else
            echo "错误: 镜像推送失败"
            exit 1
        fi
    else
        echo "错误: Docker Hub登录失败"
        exit 1
    fi
fi

echo "完成!"
