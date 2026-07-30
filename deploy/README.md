# 部署说明

整套服务由 `docker-compose.prod.yml` 编排：MySQL + 后端（uvicorn）+ nginx（含两个前端产物）。

只有 nginx 发布端口（80）。后端和数据库都只在内部网络，不暴露到宿主机。

```
                    ┌─ www.<域名>   → student/dist ─┐
浏览器 ── nginx:80 ─┤                                ├─ /api/v1 → backend:8000 → db:3306
                    └─ admin.<域名> → frontend/dist ─┘
```

## 前置准备

1. **改域名**。`deploy/nginx.conf` 里两处 `server_name` 的 `example.com` 换成真实域名。
2. **配 `.env`**（在项目根目录，不是 `deploy/`）：

   ```bash
   cp .env.example .env
   ```

   生产必填：

   | 变量 | 说明 |
   |------|------|
   | `ENV` | 设为 `production`（收敛 CORS、关闭 `/docs`） |
   | `ALLOWED_ORIGINS` | 真实域名，逗号分隔，**必须与 nginx 的 `server_name` 一致** |
   | `JWT_SECRET` | `openssl rand -hex 32` 生成，不要沿用 `.env.example` 的占位值 |
   | `DB_PASSWORD` | 数据库密码 |
   | `DEEPSEEK_API_KEY` | LLM 密钥 |

   `DB_HOST`/`DB_PORT` 不用改 —— compose 会覆盖成容器内的 `db:3306`。

   ```env
   ENV=production
   ALLOWED_ORIGINS=https://www.example.com,https://admin.example.com
   ```

   `.env` 建议收紧权限：`chmod 600 .env`。

## 首次部署

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

容器起来后还要建表、建管理员、导题库 —— 这三步不会自动跑。

### 1. 建表

**`schema.sql` 不含 `chat_sessions` / `chat_messages` 两张表**，只建它会导致 AI 对话功能不可用。两步都要执行：

```bash
# 主表
docker compose -f docker-compose.prod.yml exec -T db \
  mysql -uroot -p"$DB_PASSWORD" jlpt < crawler/db/schema.sql

# 对话表（在迁移脚本里，不在 schema.sql）
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.migrate_chat
```

### 2. 建管理员

公开注册接口只能注册 `student`（`schemas/user.py` 用 `pattern="^student$"` 限制），管理员只能用脚本建：

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.create_admin --email admin@example.com --password '<强密码>'
```

### 3. 导题库

题库源数据在 `data/raw/`，**该目录是 gitignored，不在仓库里**。新机器上有两条路：

- **推荐**：从现有环境导 mysqldump 过去，最快且不依赖源 JSON。

  ```bash
  # 旧环境
  mysqldump -h127.0.0.1 -P3307 -uroot -p jlpt > jlpt_backup.sql
  # 新环境
  docker compose -f docker-compose.prod.yml exec -T db \
    mysql -uroot -p"$DB_PASSWORD" jlpt < jlpt_backup.sql
  ```

- 或者把 `data/raw/` 拷到服务器再跑入库函数。注意 `crawler/spiders/write_to_mysql.py`
  的 `__main__` 里入库调用是注释掉的（跑的是 `write_to_csv`），要按
  `docs/data-sources.md` 的清单显式调用对应函数。入库是幂等的（按 `source_ref` upsert）。

### 4. 听力音频

数据库只存相对路径（如 `mp3/n1/tiku79/xxx.mp3`），不存 mp3 文件本身。

当前 `student/.env` 指向的源站 `http://account.for-test.cn` **没有有效 HTTPS 证书**，站点上 HTTPS 后音频会被浏览器 mixed-content 全部拦掉（778 组听力题不可用）。两个选择：

- **临时**：把音频文件放到宿主机 `AUDIO_DIR`（默认 `./audio`），保持 `VITE_AUDIO_BASE_URL` 留空，nginx 的 `/mp3/` 会从那里伺服。目录结构要对上 `mp3/n1/...`。
- **推荐**：传对象存储，构建时传入基址。注意 Vite 把这个值**静态内联**进产物，改完必须重新 build：

  ```bash
  VITE_AUDIO_BASE_URL=https://cdn.example.com \
    docker compose -f docker-compose.prod.yml up -d --build nginx
  ```

## HTTPS

`nginx.conf` 目前只监听 80。建议在这台机器前面再放一层终止 TLS（云负载均衡、Caddy、或宿主机的 certbot+nginx），转发到 80 即可 —— 后端已经带 `--proxy-headers`，会正确识别 `X-Forwarded-Proto`。

要在容器内直接终止 TLS：放开 `docker-compose.prod.yml` 里的 443 端口和证书挂载，并在 `nginx.conf` 两个 server 块里加 `listen 443 ssl` 及证书路径。

## 日常操作

```bash
# 看日志
docker compose -f docker-compose.prod.yml logs -f backend

# 健康检查
curl http://localhost/nginx-health          # nginx
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"

# 更新代码后重建
docker compose -f docker-compose.prod.yml up -d --build

# 停止（保留数据）
docker compose -f docker-compose.prod.yml down
```

### 备份

数据在命名卷 `mysql_prod_data` 里，**没有自动备份**，需自己加 cron：

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  mysqldump -uroot -p"$DB_PASSWORD" --single-transaction jlpt \
  | gzip > "backup-$(date +%F).sql.gz"
```

注意 `down -v` 会删卷连数据一起清掉，别在生产误用。

## 上线检查

- [ ] `ENV=production`，`curl https://<域名>/api/v1/../docs` 返回 404
- [ ] `ALLOWED_ORIGINS` 与 nginx `server_name` 一致，且不含 `*`
- [ ] `JWT_SECRET` 不是 `.env.example` 的占位值
- [ ] `chmod 600 .env`
- [ ] `chat_sessions` / `chat_messages` 两张表存在（否则 AI 对话报错）
- [ ] 建了管理员账号，且能登录后台
- [ ] 学生端能组卷、能听音频、AI 对话是逐字输出的（若整段才出现，说明反代还在缓冲）
- [ ] 数据库备份 cron 已配
- [ ] `docker compose logs backend` 能看到 JSON 格式的 access 日志
- [ ] 日志里 `token=` 显示为 `***`（不是明文 JWT）
- [ ] 连打 11 次错密码登录，第 11 次返回 429
- [ ] 未跑 `--workers N`（会让限流配额翻倍，见「限流」一节）

## 构建拉不到镜像时

如果本机走代理（如 Clash 在 `127.0.0.1:7890`），`docker build` / `docker pull` 会因为
Docker daemon 不读 shell 的 `http_proxy` 而超时（报 `context deadline exceeded`）。
需要给 Docker Desktop 单独配代理：**Settings → Resources → Proxies**，填上同一个地址。
命令行工具同理，用 `--noproxy '*'` 或临时 `unset http_proxy https_proxy` 访问本地服务。

> 本次改动就是在这个环境下完成的：镜像拉取被代理阻断，所以 Dockerfile 和
> `deploy/nginx.conf` **未经过实际构建和 `nginx -t` 验证**，首次部署时请留意报错。
> 后端配置本身已用本地 uvicorn 验证过（见下）。

## 依赖复现

后端依赖在 `pyproject.toml` 里全是无上界的 `>=`（`fastapi>=0.115` 实际能解析到 0.139），镜像里用 `uv sync --frozen` 强制走 `uv.lock`。改依赖要先 `uv lock` 再重建镜像，否则构建会因 lock 不匹配失败。

## 日志

生产输出**单行 JSON 到 stdout**（开发是人类可读文本），不落文件 —— 容器里写文件要挂卷还会涨满磁盘，交给 `docker logs` 或日志采集器更省心。

```bash
docker compose -f docker-compose.prod.yml logs -f backend

# 只看错误
docker compose -f docker-compose.prod.yml logs backend | grep '"level": "ERROR"'

# 按 request_id 追一次请求
docker compose -f docker-compose.prod.yml logs backend | grep 'eea3e7b998a9'
```

每条 access 日志形如：

```json
{"ts":"2026-07-30T15:12:53+0800","level":"WARNING","logger":"backend.access",
 "msg":"GET /api/v1/agent/stream 401","request_id":"e76d4a0ae221",
 "query":"message=hi&token=%2A%2A%2A","status":401,"elapsed_ms":5.1}
```

几个要点：

- **query 会脱敏**。SSE 端点把 JWT 放在 `?token=`（EventSource 不能设自定义头），token 有效期 7 天，日志里一律打成 `***`。`password`、`api_key`、`secret` 同样处理。
- **每个响应带 `X-Request-ID`**。用户报错时让他们提供这个 id，就能在日志里定位到那一次请求和完整堆栈。
- **异常不再外泄**。未捕获异常在服务端记完整堆栈，客户端只拿到 `request_id`。之前 `str(e)` 会把 DB 连接信息或上游 API 报错体直接返回给浏览器。
- **`/health` 不记日志**，否则容器探针每 30s 一条会把日志淹掉。
- **审计事件**：登录成功/失败、注册、管理员改角色或停用账号（记 `actor_id` + `target_user_id`）。登录失败不区分"用户不存在"和"密码错"，避免被用来枚举邮箱。
- uvicorn 自带的 access 日志已关闭 —— 它不脱敏 query，会把 SSE 的 token 原样打出来。

## 限流

进程内固定窗口计数，默认配额（可用环境变量调）：

| 端点 | 配额 | 计数维度 |
|------|------|----------|
| `/auth/login` | 10/分钟 | IP |
| `/auth/register` | 20/小时 | IP |
| `/agent/*`、`/exams/smart-generate*` | 10/分钟 | 用户 |

超限返回 429 并带 `Retry-After`。LLM 端点按用户计数是因为背后是按 token 计费的 DeepSeek 调用，任何学生账号都能刷成本。

> **⚠️ 多 worker 会让配额翻倍。** 计数在进程内存里，`uvicorn --workers N` 会让每个 worker 各算一份，实际配额变成 N 倍；重启即清零。当前 Dockerfile 是单 worker，够用。要扩多 worker 或多实例，得把 `backend/utils/ratelimit.py` 的 `_Bucket` 换成 Redis 后端（`check()` 的接口不用动）。
>
> IP 取自 `X-Forwarded-For` 第一段（nginx 设置的）。这个头可被伪造，但攻击者伪造只能绕过自己的配额，拿不到别人的额度。

## 前端 XSS 消毒

学生端所有 `v-html` 出口都过 `student/src/utils/sanitize.js`（DOMPurify 白名单）。
注入源有两条真实路径：题库文章里的原始 `<table>`（`renderArticle` 刻意放行的部分）
和 LLM 输出（`marked` 默认不过滤 HTML）。token 存 localStorage 且有效期 7 天，
一次 XSS 就等于拿到长效凭证。

```bash
cd student && npm test    # 56 个 XSS 回归测试
```

改动 `renderArticle` / `renderContent` / `renderMd` 时注意：**每个 return 出口都要消毒**，
包括提前 return 的分支（排序题那条就差点漏掉）。后台管理端没有 `v-html`，无需处理。

## 尚未处理的运维缺口

- **DB 无连接池**。每请求新建 `pymysql.connect()`，会是第一个压力瓶颈。
- **无 CI**。142 个后端测试 + 56 个前端测试都没有自动化触发。
- **听力音频**仍依赖第三方 HTTP 站点，见上文第 4 步。
- **`npm audit` 有一条 high**：`postcss <=8.5.17`，来自 vite/vue 的构建期传递依赖，
  不进浏览器产物。属于既有问题，升级 vite 时会一并解决。
