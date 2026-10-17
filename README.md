# cnblogs-tools

博客园命令行工具，支持文章备份、更新、图片迁移和 SQLite 备份转换。

## 配置

复制 `.env.example` 为 `.env`，填写登录名、MetaWeblog 访问令牌和博客名：

```dotenv
CNBLOGS_USERNAME="your_login_username"
CNBLOGS_TOKEN="your_metaweblog_access_token"
CNBLOGS_BLOG_NAME="your_blog_name"
```

在[博客园设置](https://i.cnblogs.com/settings#enableServiceAccess)中启用客户端访问并获取令牌。登录名和博客名可能不同。

也支持同名环境变量，优先于 `.env`。配置和文件路径均以运行命令时的目录为准。

## 用法

查看命令帮助：

```sh
uv run cnblogs --help
```

备份文章到 `blogs/`，保留已有本地编辑：

```sh
uv run cnblogs backup
```

**目前实测最多返回 300 篇，尚不支持全量备份。** 图片和附件不会随文章自动下载。

编辑 `blogs/` 中的文章，将待上传文章的 `publish` 明确设为 `true`（发布）或 `false`（不发布模式保存），然后预览并上传：

```sh
uv run cnblogs upload --dry-run
uv run cnblogs upload
```

仅支持上传公开文章，需设置 `access_permission: Anonymous`。`publish: false` 不保证撤回已发布文章。

迁移正文中的 `s2.loli.net` 图片，需先在 `.env` 中设置 `ENDPOINT="https://your-image-host.example.com"`：

```sh
uv run cnblogs images
```

图片下载到 `image-hosting/`，正文链接替换为新地址。图片部署和文章上传需另行完成。

将 `cnblogs_blog_*.db` 放在当前目录，可转换为文章文件：

```sh
uv run cnblogs database --output legacy-blogs
```

使用 `--output <directory>` 指定文章目录。

## 开发

```sh
uv run pre-commit install
uv run pre-commit run --all-files
uv run -m unittest discover -s tests
```

## 接口参考

- [MetaWeblog](docs/metaweblog.md)
- [OpenAPI](docs/openapi.yaml)

更多接口实现可参考[博客园官方 VSCode 插件](https://github.com/cnblogs/vscode-cnb)。
