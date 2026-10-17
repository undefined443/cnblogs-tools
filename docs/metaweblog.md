# Cnblogs MetaWeblog API

API reference: <https://rpc.cnblogs.com/metaweblog/Blog%E5%90%8D>

Protocol reference: <https://xmlrpc.com/metaweblog>

## Endpoint and transport

Send XML-RPC requests using HTTP `POST` to `https://rpc.cnblogs.com/metaweblog/{blogName}` with `Content-Type: text/xml`. Replace `{blogName}` with the blog name shown in the Cnblogs settings. The blog name, login username, and returned `blogid` are distinct values; use the configured endpoint and the values returned by the service.

All methods use the same endpoint. The XML `methodName` identifies the operation, and `params` contains positional arguments in the order listed below. XML-RPC structs contain named members; arrays contain ordered values. The documented `dateTime` type is encoded as `dateTime.iso8601`, binary data as `base64`, and booleans as `0` or `1`. The documented `any` type means the reference does not specify a concrete type; it is not an XML-RPC element name.

## Authentication

Pass the login username as `username` and the MetaWeblog access token as `password` in each method call. The `password` parameter is an access token, rather than the account password or an HTTP Bearer header. Enable MetaWeblog access and obtain the endpoint and token in [Cnblogs settings](https://i.cnblogs.com/settings#enableServiceAccess). See the [Cnblogs team authentication guidance](https://q.cnblogs.com/q/140114).

Pass an empty string for `appKey` in `blogger.getUsersBlogs` and `blogger.deletePost`. The argument cannot be omitted.

## Methods

Pass arguments in the order listed. Optional struct members are distinct from positional arguments.

### `blogger.deletePost`

Deletes a post.

Parameters (in order):

| Parameter  | Type      | Description                                                     |
| ---------- | --------- | --------------------------------------------------------------- |
| `appKey`   | `string`  | Pass an empty string; do not omit.                              |
| `postid`   | `string`  | Post ID.                                                        |
| `username` | `string`  | Login username.                                                 |
| `password` | `string`  | MetaWeblog access token.                                        |
| `publish`  | `boolean` | Whether to republish the blog after deletion, where applicable. |

Returns: `boolean`. Always returns true.

### `blogger.getUsersBlogs`

Lists blogs accessible to the user.

Parameters (in order):

| Parameter  | Type     | Description                        |
| ---------- | -------- | ---------------------------------- |
| `appKey`   | `string` | Pass an empty string; do not omit. |
| `username` | `string` | Login username.                    |
| `password` | `string` | MetaWeblog access token.           |

Returns: array of struct [BlogInfo](#bloginfo).

### `metaWeblog.editPost`

Updates a post. The source describes a successful result as true but declares the return type as `any`.

Parameters (in order):

| Parameter  | Type                 | Description                  |
| ---------- | -------------------- | ---------------------------- |
| `postid`   | `string`             | Post ID.                     |
| `username` | `string`             | Login username.              |
| `password` | `string`             | MetaWeblog access token.     |
| `post`     | struct [Post](#post) | Post fields.                 |
| `publish`  | `boolean`            | Whether to publish the post. |

Returns: `any`.

### `metaWeblog.getCategories`

Lists blog categories.

Parameters (in order):

| Parameter  | Type     | Description                                  |
| ---------- | -------- | -------------------------------------------- |
| `blogid`   | `string` | Blog ID returned by `blogger.getUsersBlogs`. |
| `username` | `string` | Login username.                              |
| `password` | `string` | MetaWeblog access token.                     |

Returns: array of struct [CategoryInfo](#categoryinfo).

### `metaWeblog.getPost`

Gets a post by ID.

Parameters (in order):

| Parameter  | Type     | Description              |
| ---------- | -------- | ------------------------ |
| `postid`   | `string` | Post ID.                 |
| `username` | `string` | Login username.          |
| `password` | `string` | MetaWeblog access token. |

Returns: struct [Post](#post).

### `metaWeblog.getRecentPosts`

Lists recent posts.

Parameters (in order):

| Parameter       | Type      | Description                                  |
| --------------- | --------- | -------------------------------------------- |
| `blogid`        | `string`  | Blog ID returned by `blogger.getUsersBlogs`. |
| `username`      | `string`  | Login username.                              |
| `password`      | `string`  | MetaWeblog access token.                     |
| `numberOfPosts` | `integer` | Number of recent posts to retrieve.          |

Returns: array of struct [Post](#post).

### `metaWeblog.newMediaObject`

Uploads a file and returns its URL.

Parameters (in order):

| Parameter  | Type                         | Description                                  |
| ---------- | ---------------------------- | -------------------------------------------- |
| `blogid`   | `string`                     | Blog ID returned by `blogger.getUsersBlogs`. |
| `username` | `string`                     | Login username.                              |
| `password` | `string`                     | MetaWeblog access token.                     |
| `file`     | struct [FileData](#filedata) | File contents and metadata.                  |

Returns: struct [UrlData](#urldata).

### `metaWeblog.newPost`

Creates a post and returns its ID.

Parameters (in order):

| Parameter  | Type                 | Description                                  |
| ---------- | -------------------- | -------------------------------------------- |
| `blogid`   | `string`             | Blog ID returned by `blogger.getUsersBlogs`. |
| `username` | `string`             | Login username.                              |
| `password` | `string`             | MetaWeblog access token.                     |
| `post`     | struct [Post](#post) | Post fields.                                 |
| `publish`  | `boolean`            | Whether to publish the post.                 |

Returns: `string`.

### `wp.newCategory`

Creates a category.

Parameters (in order):

| Parameter  | Type                             | Description                                  |
| ---------- | -------------------------------- | -------------------------------------------- |
| `blog_id`  | `string`                         | Blog ID returned by `blogger.getUsersBlogs`. |
| `username` | `string`                         | Login username.                              |
| `password` | `string`                         | MetaWeblog access token.                     |
| `category` | struct [WpCategory](#wpcategory) | Category fields.                             |

Returns: `integer`.

## Data structures

Required and optional field annotations follow the source; unmarked fields have no stated requirement. Optional response fields may be absent.

### `BlogInfo`

| Field      | Type     | Description |
| ---------- | -------- | ----------- |
| `blogid`   | `string` |             |
| `url`      | `string` |             |
| `blogName` | `string` |             |

### `Post`

| Field               | Type                           | Description                                                                            |
| ------------------- | ------------------------------ | -------------------------------------------------------------------------------------- |
| `dateCreated`       | `dateTime`                     | Creation time. Required when posting.                                                  |
| `description`       | `string`                       | Post body. Required when posting.                                                      |
| `title`             | `string`                       | Post title. Required when posting.                                                     |
| `categories`        | `array of string`              | Category names. Optional.                                                              |
| `enclosure`         | struct [Enclosure](#enclosure) | Optional.                                                                              |
| `link`              | `string`                       | Optional.                                                                              |
| `permalink`         | `string`                       | Optional.                                                                              |
| `postid`            | `any`                          | Optional. May be an integer in responses; pass a string to methods accepting `postid`. |
| `source`            | struct [Source](#source)       | Optional.                                                                              |
| `userid`            | `string`                       | Optional.                                                                              |
| `mt_allow_comments` | `any`                          | Optional.                                                                              |
| `mt_allow_pings`    | `any`                          | Optional.                                                                              |
| `mt_convert_breaks` | `any`                          | Optional.                                                                              |
| `mt_text_more`      | `string`                       | Optional.                                                                              |
| `mt_excerpt`        | `string`                       | Optional.                                                                              |
| `mt_keywords`       | `string`                       | Optional.                                                                              |
| `wp_slug`           | `string`                       | Optional.                                                                              |

### `CategoryInfo`

| Field         | Type     | Description |
| ------------- | -------- | ----------- |
| `description` | `string` |             |
| `htmlUrl`     | `string` |             |
| `rssUrl`      | `string` |             |
| `title`       | `string` |             |
| `categoryid`  | `string` |             |

### `FileData`

| Field  | Type     | Description                    |
| ------ | -------- | ------------------------------ |
| `bits` | `base64` | File contents, base64-encoded. |
| `name` | `string` | File name.                     |
| `type` | `string` | MIME type.                     |

### `UrlData`

| Field | Type     | Description |
| ----- | -------- | ----------- |
| `url` | `string` |             |

### `WpCategory`

| Field         | Type      | Description |
| ------------- | --------- | ----------- |
| `name`        | `string`  |             |
| `slug`        | `string`  | Optional.   |
| `parent_id`   | `integer` |             |
| `description` | `string`  | Optional.   |

### `Enclosure`

| Field    | Type      | Description |
| -------- | --------- | ----------- |
| `length` | `integer` | Optional.   |
| `type`   | `string`  | Optional.   |
| `url`    | `string`  | Optional.   |

### `Source`

| Field  | Type     | Description |
| ------ | -------- | ----------- |
| `name` | `string` | Optional.   |
| `url`  | `string` | Optional.   |

## XML-RPC examples

Examples use placeholders and illustrative response values. Use an XML-RPC client library to encode values and escape XML safely.

### Read accessible blogs

Request body for `blogger.getUsersBlogs`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<methodCall>
  <methodName>blogger.getUsersBlogs</methodName>
  <params>
    <param><value><string></string></value></param>
    <param><value><string>YOUR_LOGIN_USERNAME</string></value></param>
    <param><value><string>YOUR_METAWEBLOG_ACCESS_TOKEN</string></value></param>
  </params>
</methodCall>
```

Illustrative success response:

```xml
<?xml version="1.0" encoding="utf-8"?>
<methodResponse>
  <params>
    <param>
      <value>
        <array><data>
          <value><struct>
            <member><name>blogid</name><value><string>123456</string></value></member>
            <member><name>url</name><value><string>https://www.cnblogs.com/example/</string></value></member>
            <member><name>blogName</name><value><string>Example Blog</string></value></member>
          </struct></value>
        </data></array>
      </value>
    </param>
  </params>
</methodResponse>
```

### Handle faults

An HTTP success status alone does not prove the RPC succeeded. Inspect the XML body for `fault`, or let the XML-RPC library raise a fault exception. The following is an illustrative fault, not a catalog of Cnblogs error codes:

```xml
<?xml version="1.0" encoding="utf-8"?>
<methodResponse>
  <fault>
    <value><struct>
      <member><name>faultCode</name><value><int>401</int></value></member>
      <member><name>faultString</name><value><string>Authentication failed</string></value></member>
    </struct></value>
  </fault>
</methodResponse>
```
