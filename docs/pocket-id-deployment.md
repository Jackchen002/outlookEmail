# Pocket ID 登录与服务器部署

网站登录使用 Pocket ID 的 OpenID Connect Authorization Code 流程。应用会通过 Pocket ID Discovery 文档获取授权、Token 和签名密钥端点，并由 Authlib 校验 `state`、`nonce`、Issuer、Audience 和 ID Token 签名。

参考：

- [Pocket ID OIDC 客户端示例](https://pocket-id.org/docs/client-examples/node-red)
- [Pocket ID OIDC 客户端认证](https://pocket-id.org/docs/guides/oidc-client-authentication)

## 1. 在 Pocket ID 创建 OIDC Client

进入 `https://sso.jackyccc.com` 的管理设置，在 **OIDC Clients** 中创建客户端，并配置：

- Callback URL：`https://<OutlookEmail 网站域名>/auth/pocket-id/callback`
- Scopes：`openid profile email`
- Client authentication：使用 Pocket ID 生成的 Client ID 和 Client Secret

Callback URL 必须与稍后 `.env` 中的 `POCKET_ID_REDIRECT_URI` 完全一致，包括协议、域名、端口和路径。

## 2. 创建 `.env`

```bash
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
```

至少修改：

```dotenv
SECRET_KEY=<上一步生成的随机串>

POCKET_ID_URL=https://sso.jackyccc.com
POCKET_ID_CLIENT_ID=<Pocket ID Client ID>
POCKET_ID_CLIENT_SECRET=<Pocket ID Client Secret>
POCKET_ID_REDIRECT_URI=https://<OutlookEmail 网站域名>/auth/pocket-id/callback
POCKET_ID_SCOPES=openid profile email

SESSION_COOKIE_SECURE=true
LOGIN_PASSWORD=<本地敏感操作确认密码>
```

`LOGIN_PASSWORD` 不再用于网站登录，但导出凭据、显示账号密码和修改 WebDAV 备份配置等现有敏感操作仍用它进行二次确认，以保持这些功能的保护机制不变。

不要提交 `.env`。仓库的 `.gitignore` 已忽略该文件。

## 3. 启动容器

合并代码后，仓库工作流会构建 `ghcr.io/jackchen002/outlookemail:latest`。在服务器上执行：

```bash
docker compose pull
docker compose up -d
docker compose logs -f outlook-mail-reader
```

默认监听宿主机 `5000` 端口，数据保存在 `./data`。

## 4. 配置 HTTPS 反向代理

以 Nginx 为例：

```nginx
server {
    listen 443 ssl http2;
    server_name <OutlookEmail 网站域名>;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

生产环境必须使用 HTTPS。应用已启用 `ProxyFix`，会读取反向代理传入的协议和主机头。

## 5. 验证

1. 打开 `https://<OutlookEmail 网站域名>/login`。
2. 页面应只显示登录有效期和“登录”按钮，不显示网站密码输入框。
3. 点击“登录”，浏览器应跳转到 `https://sso.jackyccc.com`。
4. 在 Pocket ID 完成验证后，应回到 `/auth/pocket-id/callback`，随后进入应用首页。
5. 退出后再次访问受保护页面，应重新显示应用登录页。

如果登录页提示 Pocket ID 配置不完整，检查容器中的四个必填变量。若 Pocket ID 报 `redirect_uri` 不匹配，逐字符核对 Pocket ID Callback URL 与 `POCKET_ID_REDIRECT_URI`。
