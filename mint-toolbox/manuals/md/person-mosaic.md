# person-mosaic — 人物马赛克脚本入口

> 分类：图像与多媒体 · 状态：外部程序入口 / 功能待核查 · 风险：未知 · 启动器：register

## 功能

调用单独虚拟环境中的 `person_mosaic.py`，原样转发 CLI 参数。本压缩包只包含入口，未包含功能本体。

## 用法

```bash
person-mosaic [由 person_mosaic.py 定义的参数]
```

## 参数与选项

- 本包装器不解析任何参数；实际可用选项须查看外部 `person_mosaic.py`。

## 依赖与运行环境

- 固定依赖 `/home/andrew/.local/share/person-mosaic/venv/bin/python` 及同目录 `person_mosaic.py`。

## 输出与副作用

- 启动外部程序；具体读写和隐私处理行为无法仅凭本入口验证。

## 注意事项

- 不能把脚本名称理解为功能已经验收；LaunchOnOS 应采用 `register`，不要复制虚拟环境包装器为完整应用。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/person-mosaic`。
- 源文件 SHA-256：`d3a4b1136713f2a5e99736df1d2cb994a7e7a991c849d7ef798ee6349e9963d5`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
