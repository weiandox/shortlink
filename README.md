# shortlink
极简短链系统（Python+Sqlite）

推荐docker-compose部署
···yml
version: '3'

services:
  shortlink:
    image: hunterluo/shortlink:latest
    container_name: shortlink-service
    ports:
      - "5000:5000" 
    volumes:
      - ./data:/app/data  # 挂载数据库目录
    environment:
      - ADMIN_USERNAME=admin # 默认用户名为admin
      - ADMIN_PASSWORD=admin123# 默认密码为admin123
    restart: unless-stopped
```
