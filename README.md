# CNblogs-dump

通过 MetaWeblog API 自动备份博客园文章，并上传本地编辑；无需手工下载 SQLite 备份。

## 配置

安装 [uv](https://docs.astral.sh/uv/)，在项目根目录的 `.env` 中配置，或设置同名环境变量：

```dotenv
CNBLOGS_USERNAME="your_login_username"
CNBLOGS_TOKEN="your_metaweblog_access_token"
CNBLOGS_BLOG_NAME="your_blog_name"
```

`CNBLOGS_USERNAME` 是登录名，`CNBLOGS_BLOG_NAME` 是博客地址中的名称，两者可能不同。Token 使用[博客园设置](https://i.cnblogs.com/settings#enableServiceAccess)中的 MetaWeblog 访问令牌，并启用客户端访问。

环境变量优先于 `.env` 中的同名配置。兼容原来的 `USERNAME`、`TOKEN`；未设置博客名时使用用户名。也可以用 `CNBLOGS_URL` 指定完整的 MetaWeblog 地址，它优先于 `CNBLOGS_BLOG_NAME`。`.env` 已被 Git 忽略。

## 备份

```sh
uv run cnblogs.py backup
```

文章保存为 `blogs/<id>.md`，包含 YAML front matter 和接口返回的原始正文。Markdown 与 HTML 正文均保留原样，不做格式转换。`blogs/.backup.json` 保存原始响应和内容哈希，用于识别本地编辑、检测远端冲突及判断上传是否成功，不包含 token。

重复备份会刷新未修改的文件，保留本地编辑、已有但尚未被快照跟踪的文件，以及本次接口未返回的历史文章。不要删除 `.backup.json`；已有本地修改的文章若在远端也发生变化，需要手动对比处理，程序不会覆盖或自动合并。

可指定目录和请求篇数：

```sh
uv run cnblogs.py backup --output backups --count 1000
```

备份范围是 `getRecentPosts` 实际返回的文章及元数据；接口没有分页参数或总数，不保证覆盖全部历史、草稿和其他内容。当前实测最多返回 300 篇，无法覆盖此账号的全部文章；全量备份问题尚未解决，不能将其视为完整的后台数据库导出。评论、附件文件、访问权限和 SQLite 中的全部后台字段不在此备份范围；图片链接保留在正文中，不自动下载图片。

## 更新文章

编辑备份中的正文或 front matter。`title`、`categories`、`tags`、`description`（摘要）、`date` 和 `is_markdown` 会用于更新；保留 `id` 和 `blog_id`。`is_markdown` 控制分类中的 `[Markdown]` 标记。

MetaWeblog 的读取结果不提供可靠的发布状态，因此备份中的 `publish` 初始为 `null`。每篇待上传文章必须明确设置 `publish: true`（发布）或 `publish: false`（以不发布模式保存）；对已发布文章，`false` 不保证撤回，具体行为由服务端决定。程序不会推断原有发布状态。

先预览改动，再执行上传：

```sh
uv run cnblogs.py upload --dry-run
uv run cnblogs.py upload
```

Dry-run 只检查本地文件，不读取凭据或调用接口。实际上传仅处理相对快照有改动的文章，并在写入前检查所有待上传文章的 `publish` 和远端冲突。成功后更新本地快照，重复运行不会重复上传。远端冲突检查与写入不是原子操作，期间仍应避免同时在网页编辑同一篇文章。

## 图片迁移

在 `.env` 或环境变量中设置图片托管地址：

```dotenv
ENDPOINT="https://your-image-host.example.com"
```

下载正文中的 `https://s2.loli.net/<年>/<月>/<日>/<文件名>` 图片，并替换为新地址：

```sh
uv run cnblogs.py images
```

图片保存到 `image-hosting/<年>/<月>/<日>/<文件名>`，正文链接改为 `${ENDPOINT}/image-hosting/<年>/<月>/<日>/<文件名>`。仅在一篇文章的所有图片下载成功后修改其正文，保留 front matter；已有图片不重复下载。可用 `--output` 指定文章目录。

该命令只下载图片并修改本地文章，不部署图片到托管服务，也不上传文章。将 `image-hosting/` 部署到对应地址后，再预览并上传文章改动。

## SQLite 转换

原 SQLite 转换功能仍可使用：将 `cnblogs_blog_*.db` 放在项目根目录后运行：

```sh
uv run cnblogs.py database --output legacy-blogs
```

SQLite 转换不生成 MetaWeblog 同步快照。通过 API 重新备份到一个新目录后，再迁入本地编辑并上传。

## 开发检查

安装提交钩子，统一检查 Python、Markdown、JSON、YAML 和 TOML 格式：

```sh
uv run pre-commit install
```

手动检查所有已跟踪文件：

```sh
uv run pre-commit run --all-files
```

Black 负责 Python，Prettier 负责 Markdown、JSON 和 YAML，Taplo 负责 TOML。Prettier 及其 Node 环境由 pre-commit 管理，无需运行 `npm install`。

## 接口参考

- [MetaWeblog](docs/metaweblog.md)
- [OpenAPI](docs/openapi.yaml)
