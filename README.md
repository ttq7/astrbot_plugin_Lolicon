# 我要涩涩 · 可配置版 (v2.0)

一个对接 AstrBot 的涩图插件，基于 [Lolicon API](https://api.lolicon.app) 获取随机涩图，支持本地缓存池、触发词匹配模式可配置、多数据源切换。

> **衍生声明**：本仓库 fork 自 [ttq7/astrbot_plugin_Lolicon](https://github.com/ttq7/astrbot_plugin_Lolicon)（作者 hello七七），在原版基础上重写了缓存机制并增加了 WebUI 可视化配置。感谢原作者的工作。

## 功能特点

- 支持 R18 / 非 R18 / 混合（仅 lolicon 数据源）
- **触发词匹配方式可配置**：完整短语 / 子串 / 正则三种模式
- **本地图片缓存池**：预下载图片，请求时直接取缓存，响应快且降低 API 压力
- **多数据源**：lolicon（支持标签/宽高比/AI 排除筛选）或 nyan（直接返回图片）
- 自动清理已发送图片缓存
- 全部参数 WebUI 可视化配置，无需改代码
- 图片存储路径规范化（AstrBot 官方 data 目录），不再写当前工作目录

## 安装方法

将本仓库克隆或下载到 AstrBot 的 `plugins` 目录下，重启机器人即可自动加载：

```bash
cd AstrBot/plugins
git clone https://github.com/<your-fork>/astrbot_plugin_Lolicon
```

## 配置

插件目录下的 `_conf_schema.json` 定义了所有配置项。AstrBot 会自动在 **WebUI → 插件管理** 中生成可视化配置面板，直接编辑即可，无需修改代码。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `match_mode` | string | `contains` | 触发词匹配方式：`exact`(完整短语) / `contains`(子串) / `regex`(正则) |
| `trigger_words` | list | `["色图","涩图","瑟图"]` | 触发词列表，按 match_mode 解释 |
| `reply_style` | string | `plain` | 回复风格：`plain`(简洁) / `playful`(俏皮，还原原版语气) |
| `r18` | int | `0` | 0=非R18 / 1=仅R18 / 2=混合 |
| `data_source` | string | `lolicon` | 数据源：`lolicon` / `nyan` |
| `exclude_ai` | bool | `true` | 排除 AI 生成图（仅 lolicon） |
| `aspect_ratio` | string | `gt1` | 宽高比：留空/`gt1`/`lt1`/`eq1`（仅 lolicon） |
| `cache_size` | int | `10` | 缓存池目标数量 |
| `refill_threshold` | int | `5` | 触发补充的阈值 |
| `refill_interval` | int | `300` | 后台巡检间隔（秒） |

## 使用说明

发送包含触发词的消息即可，默认触发词为 `色图` / `涩图` / `瑟图`（子串匹配）。

```
用户：我要涩涩
机器人：[图片] 给你涩图~ 12345678
```

若想还原原版"必须完整输入 我要涩涩 才触发"的行为，把 `match_mode` 改为 `exact`，`trigger_words` 改为 `["我要色色","我要色图","我要涩涩"]`，`reply_style` 改为 `playful`。

## 配置要求

- Python 3.8+
- 依赖：`aiohttp`、`aiofiles`
- 需要连接互联网访问数据源 API

## 注意事项

- 请遵守相关法律法规，禁止传播非法内容
- Lolicon API 存在请求频率限制（约 5 秒 / 次），缓存池机制可有效规避
- 图片缓存在发送后自动删除，存储于 AstrBot data 目录的 `plugin_data/astrbot_plugin_lolicon/imgs`
- 部分图片可能因网络问题加载失败

## License

MIT，见 [LICENSE](LICENSE)。衍生自 ttq7/astrbot_plugin_Lolicon（原作者 hello七七）。

## 贡献

欢迎提交 Pull Request。建议提交前先创建 Issue 讨论新特性。
