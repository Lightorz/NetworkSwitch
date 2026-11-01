# 网络开关

Windows 桌面悬浮小组件，可查看并切换以太网和 Wi-Fi 适配器。组件支持拖动和屏幕边缘收纳。运行时需要管理员权限，Windows 会显示 UAC 提示。

## 下载和使用

从 GitHub Releases 下载 Windows ZIP，解压后运行 `网络开关.exe`。首次运行会创建桌面快捷方式；程序不会自动加入开机启动。需要时可按[使用指南](使用指南.txt)在任务计划程序中手动创建登录任务并启用最高权限。

程序会自动检测适配器。自动检测失败时，将 [`config.ini.example`](config.ini.example) 复制为同目录的 `config.ini` 并填写适配器名称。`config.ini` 和运行日志不会提交到源码仓库。

Windows 可在未签名程序首次运行时显示发布者提示。此项目的发布程序未签名。

## 从源码构建

参见[构建说明](BUILD.md)。

## 许可证

[MIT](LICENSE)
