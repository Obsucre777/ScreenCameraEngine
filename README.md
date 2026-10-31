# Screen Camera Engine

用 Python 程序化生成“手持相机近距离拍摄屏幕”的视频。桌面、Chrome 图标、光标、浏览器窗口、LCD 子像素、镜头效果和双击音轨均由代码生成，不需要外部图片、视频素材或 AI 模型。

默认输出：1920×1080、30fps、6 秒、H.264 视频与 AAC 立体声音轨。

## 演示

https://github.com/user-attachments/assets/8005fe9d-ca01-43ba-9007-b63829a1a72c

如果播放器未加载，可[下载仓库内的完整 MP4](demo/chrome_screen_camera.mp4)。

## 运行环境

- 推荐 Windows 10/11、Python 3.10+
- FFmpeg 已安装并加入系统 PATH
- 使用 Windows 的 Segoe UI / Arial 字体；其他系统可能可以运行，但字体和排版会不同

检查环境：

```powershell
python --version
ffmpeg -version
```

## 安装

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` 只安装 Python 依赖，不会安装 FFmpeg。请单独安装 FFmpeg，并确保 `ffmpeg -version` 可以正常执行。

## 生成视频

```powershell
python tools/screen_camera_engine.py --no-frames
```

输出位置：

```text
files/chrome_screen_camera.mp4
```

`--no-frames` 表示只编码视频。省略该参数时，还会把每一帧保存到 `images/`，默认共 180 张。

## 常用命令

指定输出文件：

```powershell
python tools/screen_camera_engine.py --output files/demo.mp4 --no-frames
```

生成第 4.8 秒的单张预览：

```powershell
python tools/screen_camera_engine.py --still files/preview.jpg --at 4.8
```

查看全部参数：

```powershell
python tools/screen_camera_engine.py --help
```

注意：输出文件已存在时，FFmpeg 会覆盖它。需要保留旧视频时，请使用新的 `--output` 路径。

## 项目文件

```text
tools/screen_camera_engine.py  核心生成代码
requirements.txt               Python 依赖
README.md                      使用说明
LICENSE                        MIT 许可证
```

`files/` 和 `images/` 都是运行后生成的目录，不属于源码分发内容。

## 提示词

> 写个引擎模拟像素点渲染成片，让视频的画面模仿手持相机近距离拍摄屏幕的画面，现实感很强，屏幕里的文字画面也很清晰。屏幕上是点击谷歌浏览器准备打开。

## 许可证

MIT，详见 `LICENSE`。
