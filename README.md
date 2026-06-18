# CNblogs-dump

将博客园 SQLite 备份文件转储为 Markdown 文件

## Usage

1. [导出博客备份](https://i.cnblogs.com/posts/export)并下载 SQLite 格式文件
2. 将解压得到的 `.db` 文件放到项目根目录

    ```sh
    unzip ~/Downloads/cnblogs_blog_*.zip
    ```

3. 将 `.db` 文件转换为 Markdown 文件：

    ```sh
    uv run db2md.py
    ```

4. 在 `blogs/` 目录下编辑转换后的 Markdown 文件
5. 将编辑后的 Markdown 文件上传到博客园：

    ```sh
    node upload.js
    ```
