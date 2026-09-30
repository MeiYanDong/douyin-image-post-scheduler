# douyin-image-post-scheduler

两个可安装到 Codex 的开源 Skill：将一段想法与人物图片制作成原生字幕拼图，再从结构化本地素材生成可复现的抖音图文队列，并在用户已登录的 Chrome 中完成上传、定时发布和后台核验。

静态图片入口沿用 [native-subtitle-quote-image](https://github.com/chengyi-ai/native-subtitle-quote-image) 的最终效果：一张 3:4 图片，上方人物主画面承载第一句，下方是连续、零间距的白字黑描边字幕条。原有视频流程仍可独立使用。

> 本项目不是抖音官方工具。网页结构可能变化，实际发布前必须检查当前页面和账号状态。

## 解决什么问题

- 一段想法先改成短句，用照片或无文字生图制作字幕拼图；
- 固定脚本写入中文，导出能直接进入队列的图片、正文、标题和话题文件；
- 批量检查图文素材是否齐全；
- 按第一张图片生成 20 字以内的发布标题；
- 为 1000 字正文限制和 5 个有效话题预留空间；
- 每天多条、指定时间窗口、固定随机种子的可复现排期；
- 避免把纯文本 `#标签` 误判为有效话题；
- 在每条发布前验证图片、标题、正文、话题、音乐和时间；
- 中断后从最后一个成功条目继续，避免重复发布；
- 区分“审核中”和“定时发布中”。

## 仓库结构

```text
skills/idea-subtitle-collage/
├── SKILL.md
├── VERSION
├── requirements.txt
├── agents/openai.yaml
├── references/input-format.md
└── scripts/
    ├── collage_layout.py
    └── render_image_collage.py
skills/douyin-image-post-scheduler/
├── SKILL.md
├── VERSION
├── agents/openai.yaml
├── references/browser-workflow.md
└── scripts/prepare_queue.py
```

仓库不包含抖音账号、Cookie、原始素材、已发布内容、排期结果或录屏。

## 安装

### Codex Skill Installer

在 Codex 中调用 `$skill-installer`，安装下面的 Skill 目录：

```text
https://github.com/MeiYanDong/douyin-image-post-scheduler/tree/main/skills/idea-subtitle-collage
https://github.com/MeiYanDong/douyin-image-post-scheduler/tree/main/skills/douyin-image-post-scheduler
```

### 手动安装

```bash
git clone https://github.com/MeiYanDong/douyin-image-post-scheduler.git
mkdir -p ~/.codex/skills
cp -R douyin-image-post-scheduler/skills/idea-subtitle-collage ~/.codex/skills/
cp -R douyin-image-post-scheduler/skills/douyin-image-post-scheduler ~/.codex/skills/
python3 -m pip install -r douyin-image-post-scheduler/skills/idea-subtitle-collage/requirements.txt
```

重新打开 Codex 任务后即可使用 `$idea-subtitle-collage` 和 `$douyin-image-post-scheduler`。

## 从一段想法制作字幕拼图

```text
使用 $idea-subtitle-collage，把我的这段吐槽改成短句，用指定人物的头像作为生图参考，制作与原工作流一致的字幕拼图，并导出素材包。
```

Agent 完成短句、无文字底图与 JSON 后，执行：

```bash
python3 skills/idea-subtitle-collage/scripts/render_image_collage.py \
  --image "/absolute/path/to/person.png" \
  --script "/absolute/path/to/post.json" \
  --post-dir "/absolute/path/to/content-root/001_内容名称"
```

脚本不调用生图服务，只用 Pillow 读取静态图片、写入字幕并打包。JSON 支持 2—7 句有序台词，可为每句指定不同底图；输入格式见 [input-format.md](skills/idea-subtitle-collage/references/input-format.md)。没有视频也能运行，不需要 FFmpeg 或虚构时间戳。

默认输出 1080×1440，第一句＋4 条字幕时主画面占 70%，第一句＋5 条时占 62.5%。生成清单记录来源、哈希、裁切区域和实际字号。默认标记“创作者评论 · AI配图”，防止把创作者文案误认成人物原话。中文需要系统 CJK 字体，缺失时用 `--font` 指定。

## 素材格式

每条内容放在以三位编号开头的目录中：

```text
001_内容名称/
├── 01_图片内容/
│   ├── 01_发布标题.jpg
│   ├── 02_第二张图.jpg
│   └── ...
├── 02_文字内容.txt
├── 03_标题内容.txt
└── 04_标签内容.txt
```

默认要求每条 8 张图片和至少 5 个 `#话题`。这些值可以通过脚本参数调整。

静态入口导出每条 1 张完整字幕拼图。预检使用 `--image-count 1`；图内字幕条数与发布图片数分别计算。

## 先生成队列

```bash
python3 skills/douyin-image-post-scheduler/scripts/prepare_queue.py \
  "/absolute/path/to/content-root" \
  --start-date 2026-08-26 \
  --posts-per-day 3 \
  --window-start 09:00 \
  --window-end 22:00 \
  --json-output "/absolute/path/to/douyin-queue.json" \
  --markdown-output "/absolute/path/to/douyin-schedule.md"
```

脚本只读取本地素材并生成计划文件，不会打开浏览器或发布内容。输出中的 `seed` 可用于保持同一批排期完全一致。

若这一批来自静态入口，在上述命令中加上 `--image-count 1`。

## 在 Codex 中使用

```text
使用 $douyin-image-post-scheduler 检查这个素材文件夹，按每天 3 条、北京时间 09:00—22:00 随机排期，并在我已登录的 Chrome 中发布。
```

Skill 的默认发布流程是：

1. 检查准确素材目录和当前抖音账号；
2. 生成 JSON 队列和 Markdown 排期；
3. 按队列中该条的图片数量上传，并填写标题、正文；
4. 把 5 个标签放在独立行，逐个从候选面板激活；
5. 选择收藏夹第一首音乐；
6. 检查公开、允许保存、不跨平台同步和定时时间；
7. 获得整批发布确认后提交；
8. 每条返回内容管理页，批次结束后核验总数和最后一条。

实际对外发布需要用户确认。本 Skill 不保存账号密码、不读取浏览器 Cookie，也不绕过验证码或登录验证。

## 验证

```bash
python3 -m pip install -r skills/idea-subtitle-collage/requirements.txt
python3 -m unittest discover -s tests -v
python3 skills/douyin-image-post-scheduler/scripts/prepare_queue.py --help
python3 skills/idea-subtitle-collage/scripts/render_image_collage.py --help
```

测试覆盖真实图片的零间距排版、白字黑描边、EXIF 方向、非法输入和旧文件保护，以及静态素材包接入原队列；同时保留队列、随机种子、标题/话题约束和排期测试。

## License

[MIT](LICENSE)

静态字幕排版改编自程意的 `native-subtitle-quote-image`，原始许可见 [upstream-license.txt](skills/idea-subtitle-collage/references/upstream-license.txt)。
