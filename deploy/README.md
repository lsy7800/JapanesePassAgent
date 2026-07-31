# 部署说明

整套服务由 `docker-compose.prod.yml` 编排：MySQL + 后端（uvicorn）+ nginx（含两个前端产物）。

**当前配置面向「还没有域名、直接用 IP 访问」的场景**，两个前端按端口分流：

```
浏览器 ─┬─ http://<IP>/      → student/dist  ─┐
        │                                     ├─ /api/v1 → backend:8000 → db:3306
        └─ http://<IP>:8080/ → frontend/dist ─┘
              ↑ 默认只绑 127.0.0.1，走 SSH 隧道访问
```

后端和数据库都只在 compose 内部网络，不暴露到宿主机。后台管理端口默认只绑本机。

> 为什么用端口而不是 `/admin/` 路径前缀：两个 SPA 的 `vite base` 和 `vue-router base`
> 都是默认 `/`，用端口零代码改动。

## 前置准备

**不需要改 `deploy/nginx.conf`** —— 它的 `server_name _` 是通配，IP 访问直接命中。

配 `.env`（在项目根目录，不是 `deploy/`）：

```bash
cp .env.example .env
chmod 600 .env
```

必填四项：

| 变量 | 值 |
|------|-----|
| `ENV` | `production` |
| `JWT_SECRET` | `openssl rand -hex 32` 生成，别沿用占位值 |
| `DB_PASSWORD` | 自己定一个强密码 |
| `DEEPSEEK_API_KEY` | LLM 密钥 |

```env
ENV=production
JWT_SECRET=<openssl rand -hex 32 的输出>
DB_PASSWORD=<强密码>
DEEPSEEK_API_KEY=<你的密钥>

# 关键：用 IP 部署时留空！
ALLOWED_ORIGINS=
```

**`ALLOWED_ORIGINS` 必须留空。** 前端和 `/api` 由同一个 nginx 从同一 origin 提供，
浏览器根本不发跨域请求，不需要 CORS。留空时代码不挂 CORS 中间件（已验证不会
回落成 `*`）。填成 `http://<IP>` 也不会报错，但纯属多余。

`DB_HOST`/`DB_PORT` 不用改 —— compose 会覆盖成容器内的 `db:3306`。

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

> 🔴 **最容易踩的坑：根目录 `.env` 里的 `VITE_AUDIO_BASE_URL` 必须显式填，不能留空。**
>
> 本地开发能播音频，是因为 `student/.env` 里有这个变量。但那个文件被
> `.dockerignore`（`**/.env`，防止密钥进镜像）排除了，**不进构建上下文**，
> 容器里读不到。Vite 拿到空值后，音频路径退化成相对路径 `/mp3/...`，
> 落到 nginx 挂载的 `./audio` 空目录 → **全部 404，且不报任何错误**。
>
> 本地正常、线上静默失效，这个组合很难自己想到，所以单独列出来。

**用 IP + HTTP 试运行时**，直接指向原源站最省事 —— 站点本身是 HTTP，不存在
mixed-content 拦截问题。在根目录 `.env` 里填：

```env
VITE_AUDIO_BASE_URL=http://account.for-test.cn
```

缺点是依赖对方可用性，它同时是爬虫目标站，随时可能断。

**想自己托管音频**：把文件放到宿主机 `AUDIO_DIR`（默认 `./audio`），
`VITE_AUDIO_BASE_URL` 才留空，nginx 的 `/mp3/` 会从那里伺服。
目录结构要对上 `mp3/n1/tiku79/xxx.mp3`。

无论哪种，改完都**必须重新构建**（Vite 把值静态内联进 JS 产物，重启容器无效）：

```bash
docker compose -f docker-compose.prod.yml up -d --build nginx
```

验证变量确实进了产物：

```bash
# 指向源站时应有输出
docker compose -f docker-compose.prod.yml exec nginx \
  grep -o "account\.for-test\.cn" /usr/share/nginx/html/student/assets/*.js | head -1
```

浏览器 F12 看 Network，音频请求应指向 `http://account.for-test.cn/mp3/...`，
而不是 `http://<IP>:<端口>/mp3/...`。改完记得强制刷新（`Ctrl+Shift+R`），旧 JS 有缓存。

> ⚠️ **等你上了 HTTPS 域名，这件事就变成阻塞项**：那个源站没有有效 HTTPS 证书
> （实测 `SSL: no alternative certificate subject name matches`），HTTPS 页面加载
> HTTP 音频会被浏览器全部拦掉，778 组听力题不可用。届时必须迁到对象存储或自己托管。
>
> 注意 Vite 把 `VITE_AUDIO_BASE_URL` **静态内联**进产物，改完必须重新 build：
>
> ```bash
> VITE_AUDIO_BASE_URL=https://cdn.example.com \
>   docker compose -f docker-compose.prod.yml up -d --build nginx
> ```

## 80 端口已被占用时

如果服务器上已经跑着别的 nginx（或任何占用 80 的服务），本项目的 nginx 容器会因
端口冲突起不来（`bind: address already in use`）。两种解法。

### 方案 A：让已有的 nginx 反代过来（推荐）

本项目 nginx 换个不冲突的宿主机端口，只监听本机；已有的 nginx 作为唯一入口。
好处是 80 仍由原来那套统管，将来上 HTTPS 也只需在它上面配证书。

`.env` 里加：

```env
HTTP_PORT=8000
```

再把宿主机端口绑到本机（避免 8000 直接暴露公网）—— 编辑 `docker-compose.prod.yml`：

```yaml
      - "127.0.0.1:${HTTP_PORT:-80}:80"
```

然后在**已有的** nginx 里加一个 server 块：

```nginx
server {
    listen 80;
    server_name <你的IP或域名>;

    # SSE 两个端点必须关缓冲，否则 AI 对话不是逐字输出
    location /api/v1/agent/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        access_log off;    # JWT 走 query string，别记进日志
    }
    location /api/v1/exams/smart-generate/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        access_log off;
    }

    # 其余全部（静态资源、/api、SPA fallback 都由容器内的 nginx 处理）
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }
}
```

`nginx -t && systemctl reload nginx` 生效。之后访问 `http://<IP>/` 即可。

> **两层 nginx 不是浪费**：容器内那层管 SPA fallback、静态资源缓存、`/api` 与 SSE 的
> 分流规则，这些配置跟着镜像走；外层只做一次转发。想省掉内层就得把
> `deploy/nginx.conf` 的规则全部手抄到外层，还得把 `dist/` 产物挂出来，
> 反而更难维护。
>
> **`access_log off` 别漏**：SSE 的 JWT 走 query string（EventSource 不能设自定义头）
> 且有效期 7 天，外层 nginx 会把它原样记进访问日志。

### 方案 B：直接换个端口对外

最省事，但访问地址得带端口，且和已有服务共存时容易混。

```env
HTTP_PORT=8000
```

访问 `http://<IP>:8000/`。记得在云主机安全组放行 8000。

### 后台管理端口

无论哪种方案，后台管理仍是 `127.0.0.1:8080`，走 SSH 隧道访问，不受影响。
若 8080 也被占用，改 `docker-compose.prod.yml` 里那行的宿主机侧端口即可。

## 后台管理的访问方式

后台管理默认**只绑 `127.0.0.1:8080`**，公网访问不到。这是有意的：它能改用户角色、
停用账号、增删题库。

从本地机器建隧道访问：

```bash
ssh -L 8080:localhost:8080 user@<服务器IP>
# 然后本地浏览器开 http://localhost:8080
```

确实要直接暴露到公网（不推荐），在 `.env` 里加：

```env
ADMIN_BIND=0.0.0.0
```

同时建议打开 `deploy/nginx.conf` 后台 server 块里的 `allow`/`deny` 白名单，
只放行你的固定出口 IP。

## 从 IP 切换到域名

拿到域名后：

1. `deploy/nginx.conf`：两个 server 块的 `listen` 都改回 `80`，`server_name` 分别填
   `www.<域名>` 和 `admin.<域名>`，删掉 `default_server` 和 `listen 8080`。
2. `docker-compose.prod.yml`：删掉 `"${ADMIN_BIND:-127.0.0.1}:8080:8080"` 这行。
3. `.env`：`ALLOWED_ORIGINS` 仍可留空（同域），除非前端要跨域访问 API。
4. 处理听力音频（见上文 ⚠️）。
5. 重新 build：`docker compose -f docker-compose.prod.yml up -d --build`。

## HTTPS

`nginx.conf` 目前只监听 HTTP。建议在这台机器前面再放一层终止 TLS（云负载均衡、Caddy、
或宿主机的 certbot+nginx），转发到 80 即可 —— 后端已经带 `--proxy-headers`，会正确
识别 `X-Forwarded-Proto`。

要在容器内直接终止 TLS：放开 `docker-compose.prod.yml` 里的 443 端口和证书挂载，
并在 `nginx.conf` 的 server 块里加 `listen 443 ssl` 及证书路径。

> HTTP 部署期间要知道的风险：登录密码和 JWT 都以明文经过网络。仅用于内部试运行
> 尚可，**正式对学生开放前必须上 HTTPS**。

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

逐条在服务器上跑，把 `<IP>` 换成实际地址。

```bash
# 1. 三个容器都是 Up（backend/nginx 还应显示 healthy）
docker compose -f docker-compose.prod.yml ps

# 2. nginx 活着
curl -s http://<IP>/nginx-health          # 期望 ok

# 3. 后端活着（经 nginx 反代到 backend 的 /health）
curl -s http://<IP>/api-health            # 期望 {"status":"ok"}

# 4. 生产收敛生效：文档出口全关。
#    注意不能测 http://<IP>/docs —— nginx 的 SPA fallback 会返回 index.html(200)，
#    看起来"没关掉"其实是假象。要直接问后端容器。
docker compose -f docker-compose.prod.yml exec backend python -c "
import urllib.request, urllib.error
for p in ['/docs','/redoc','/openapi.json','/health']:
    try:
        c = urllib.request.urlopen('http://127.0.0.1:8000'+p, timeout=5).status
    except urllib.error.HTTPError as e:
        c = e.code
    print(p, '->', c)
"
# 期望 /docs /redoc /openapi.json 都是 404，/health 是 200

# 5. 答案泄漏已堵：无 token 拿不到题组
curl -s -o /dev/null -w "%{http_code}\n" http://<IP>/api/v1/questions/1   # 期望 401

# 6. 限流生效：连打 11 次，最后应出现 429
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://<IP>/api/v1/auth/login \
    -H 'Content-Type: application/json' -d '{"email":"x@y.com","password":"wrong"}'
done; echo

# 7. 日志是 JSON 且 token 已脱敏
docker compose -f docker-compose.prod.yml logs backend | tail -5
docker compose -f docker-compose.prod.yml logs backend | grep -c 'token=%2A' || true
```

配置与数据：

- [ ] `.env` 里 `ENV=production`、`ALLOWED_ORIGINS` 留空、`JWT_SECRET` 不是占位值
- [ ] `chmod 600 .env`
- [ ] `chat_sessions` / `chat_messages` 两张表存在（否则 AI 对话报错）
- [ ] 建了管理员账号
- [ ] 后台管理走 SSH 隧道能打开 `http://localhost:8080`，且**公网** `http://<IP>:8080` 打不开
- [ ] 数据库备份 cron 已配
- [ ] 未跑 `--workers N`（会让限流配额翻倍，见「限流」一节）

浏览器端手测（这几项脚本测不了）：

- [ ] 学生端能注册、登录、组卷、提交判分
- [ ] 听力题能播放音频（F12 看 Network，音频 URL 应指向 `VITE_AUDIO_BASE_URL`
      配的地址；若指向 `http://<IP>:<端口>/mp3/...` 说明构建时该变量为空，见上文第 4 步）
- [ ] AI 对话是**逐字**出现的 —— 若整段才出现，说明反代还在缓冲 SSE
- [ ] 刷新 `/exam`、`/result/1` 等深链接不 404（SPA fallback 生效）

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
