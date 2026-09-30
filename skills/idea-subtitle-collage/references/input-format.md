# 静态图片脚本

最小输入：

```json
{
  "label": "创作者评论 · AI配图",
  "lines": [
    "你的钱包准备好了吗？",
    "新的订阅，又来了",
    "工具负责打工，钱包负责上班"
  ]
}
```

`lines` 是 2—7 句非空单行文字，顺序就是阅读顺序。第一句落在主画面底部，其余句子各占一个连续字幕条。先拆长句再渲染；不要把一段文章挤进一条字幕。

命令行 `--image` 是所有句子的默认底图。某句需要另一张图时，改成 `{"text": "这一句", "image": "another-scene.png"}`；相对路径以脚本 JSON 所在目录为基准。无需视频、FFmpeg 或时间戳；视频输入继续使用原有 `native-subtitle-quote-image`。

素材包模式额外需要：

```json
{
  "title": "工具负责打工",
  "body": "这里放配图对应的完整正文。",
  "tags": ["#人工智能", "#AI工具", "#程序员", "#内容创作", "#效率"],
  "label": "创作者评论 · AI配图",
  "lines": ["工具负责打工", "钱包负责上班"],
  "sources": [
    {"url": "https://example.com/official-announcement", "status": "primary_verified", "claim": "核验过的事实"}
  ]
}
```

- `title`：1—20 字，不含路径字符。第一张图片名自动生成 `01_标题.jpg`，供发布队列提取标题。
- `body`：完整正文；脚本按现有队列预算为 5 个话题预留空间，超限直接报错。
- `tags`：恰好 5 个不同的 `#话题`；这是候选文字，平台是否识别为有效话题由发布流程核验。
- `label`：默认 `创作者评论 · AI配图`。照片底图改为 `创作者评论 · 照片配图`；不冒充人物的原话。
- `sources`：可选的事实来源与核验状态，原样保存在生成清单。脚本只记录来源，不自动核验事实。

输出模式二选一：

```bash
python3 scripts/render_image_collage.py \
  --image /absolute/path/person.png --script /absolute/path/lines.json \
  --out /absolute/path/collage.jpg

python3 scripts/render_image_collage.py \
  --image /absolute/path/person.png --script /absolute/path/post.json \
  --post-dir /absolute/path/content/001_工具负责打工
```

第一种生成图片和同名 JSON；第二种生成 `01_图片内容/`、`02_文字内容.txt`、`03_标题内容.txt`、`04_标签内容.txt` 和 `05_生成清单.json`。清单记录输入/输出 SHA-256、图片来源、实际字号、每句位置和裁切区域。输出路径必须是新的；出错不覆盖旧图片或旧素材。

默认 1080×1440；可用 `--width`、`--aspect`、`--band-center`、`--hero-center`、`--hero-fraction`、`--font`、`--font-size` 调整。建议保持默认 3:4。静态入口的 `--hero-center` 默认 0.35，竖向裁切稍偏上以保留人像头部。中文字体自动查找 macOS 黑体、Windows 微软雅黑或 Linux Noto CJK；不存在时明确报错。Linux 可安装 `fonts-noto-cjk`，或用 `--font /path/to/font.ttc` 指定字体。

共用排版核心为 `scripts/collage_layout.py`。它接收图片对象和文字，独立于图片读取、视频取帧和文件写入，方便后续视频适配器复用同一套几何与字体规则。

排版算法改编自 [native-subtitle-quote-image](https://github.com/chengyi-ai/native-subtitle-quote-image/blob/f9485e20f03fc0b9e5dfd77d03d5be24f7cebdcd/skills/native-subtitle-quote-image/scripts/native_subtitle_stitch.py) 的脚本字幕模式：主画面比例随字幕条数自适应、下部窄带裁切、居中白字黑描边、零间距。原作者 MIT 许可保存在 [upstream-license.txt](upstream-license.txt)。
