# 构建 Windows 版本

需要 Windows 和 Python 3.12。仅构建时需要 PyInstaller 6.22.3；程序本身只使用 Python 标准库。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install pyinstaller==6.22.3
.venv\Scripts\python -m unittest -v test_network_switch_portable
.venv\Scripts\python -m PyInstaller --clean --noconfirm --onefile --windowed --uac-admin --name 网络开关 network_switch_portable.py
```

生成文件位于 `dist\网络开关.exe`。`--uac-admin` 为程序加入管理员权限清单；运行时 Windows 会显示 UAC 提示。将该 EXE 与空白 `config.ini` 和 `使用指南.txt` 一起打包即可。
