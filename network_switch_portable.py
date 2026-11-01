"""
桌面悬浮网络开关 - 便携版
- 乙太網 / Wi-Fi 双开关，标签+开关分列
- 全区域可拖动，winfo_pointer 定位，无延迟不跳
- 仅组件边框触碰到屏幕边缘时才吸附为侧边标签
- 鼠标悬停标签自动展开，鼠标离开自动收回侧边
- 自动检测网络适配器名称（无需手动配置）
- 首次运行自动创建桌面快捷方式，不自动加入开机启动
- netsh 为主 + NetAdapter cmdlet 为辅 + 完整日志
"""
import tkinter as tk
import subprocess
import threading
import time
import sys
import os
import math
import ctypes
import configparser

# ============================================================
#  便携路径
# ============================================================
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(APP_DIR, 'switch_debug.log')
CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')

POLL_INTERVAL = 3
DRAG_THRESHOLD = 8
EDGE_THRESHOLD = 2
TAB_SIZE = 14

# 适配器名称（启动时自动检测或从 config.ini 读取）
ETH_ADAPTER = None
WIFI_ADAPTER = None

# ---- 隐藏 PowerShell 窗口 ----
STARTUP_INFO = subprocess.STARTUPINFO()
STARTUP_INFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
STARTUP_INFO.wShowWindow = 0
_CF = 0x08000000


# ============================================================
#  日志 / PowerShell
# ============================================================
def log(msg):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass


def ps_full(cmd):
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
            capture_output=True, text=True, timeout=20,
            startupinfo=STARTUP_INFO, creationflags=_CF,
        )
        return r
    except subprocess.TimeoutExpired:
        log(f"  ps_full TIMEOUT (20s): {cmd[:80]}")
        return None
    except Exception as e:
        log(f"  ps_full EXCEPTION: {e}")
        return None


def ps_quote(s):
    """转义字符串用于 PowerShell 单引号"""
    return s.replace("'", "''")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


# ============================================================
#  适配器自动检测
# ============================================================
def detect_adapters():
    """自动检测以太网和 WiFi 适配器名称"""
    global ETH_ADAPTER, WIFI_ADAPTER

    # 先读配置文件
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE, encoding='utf-8')
            eth = config.get('network', 'ethernet_adapter', fallback='')
            wifi = config.get('network', 'wifi_adapter', fallback='')
            if eth.strip():
                ETH_ADAPTER = eth.strip()
                log(f"  ETH from config: {ETH_ADAPTER}")
            if wifi.strip():
                WIFI_ADAPTER = wifi.strip()
                log(f"  WIFI from config: {WIFI_ADAPTER}")
        except:
            pass

    # 自动检测以太网
    if not ETH_ADAPTER:
        # 方法1: MediaType = 802.3
        r = ps_full(
            "Get-NetAdapter -Physical | "
            "Where-Object { $_.MediaType -eq '802.3' -and $_.Status -ne 'Not Present' } | "
            "Select-Object -First 1 -ExpandProperty Name"
        )
        if r and r.stdout and r.stdout.strip():
            ETH_ADAPTER = r.stdout.strip()
        else:
            # 方法2: 名称匹配
            r = ps_full(
                "Get-NetAdapter | "
                "Where-Object { $_.Name -match 'Ethernet|以太|乙太' -and $_.Status -ne 'Not Present' } | "
                "Select-Object -First 1 -ExpandProperty Name"
            )
            if r and r.stdout and r.stdout.strip():
                ETH_ADAPTER = r.stdout.strip()

    # 自动检测 WiFi
    if not WIFI_ADAPTER:
        r = ps_full(
            "Get-NetAdapter -Physical | "
            "Where-Object { $_.MediaType -eq '802.11' } | "
            "Select-Object -First 1 -ExpandProperty Name"
        )
        if r and r.stdout and r.stdout.strip():
            WIFI_ADAPTER = r.stdout.strip()
        else:
            r = ps_full(
                "Get-NetAdapter | "
                "Where-Object { $_.Name -match 'Wi-?Fi|WLAN|无线' } | "
                "Select-Object -First 1 -ExpandProperty Name"
            )
            if r and r.stdout and r.stdout.strip():
                WIFI_ADAPTER = r.stdout.strip()

    log(f"Detected adapters: ETH={ETH_ADAPTER}, WIFI={WIFI_ADAPTER}")


# ============================================================
#  网络控制
# ============================================================
def get_adapter_status(name):
    """获取适配器的 AdminStatus（管理状态: Up=已启用 / Down=已禁用）"""
    r = ps_full(
        f"Get-NetAdapter -Name '{ps_quote(name)}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty AdminStatus"
    )
    if r and r.stdout:
        return r.stdout.strip()
    return "Unknown"


def toggle_adapter(name):
    """切换适配器状态：netsh 为主，Enable/Disable-NetAdapter 为辅"""
    current = get_adapter_status(name)
    if current not in ("Up", "Down"):
        log(f"  refusing toggle: unknown adapter status for {name}: {current}")
        return current

    want_enable = (current != "Up")

    action = "enable" if want_enable else "disable"
    log(f"--- toggle_adapter: name={name}, current={current}, target={'Up' if want_enable else 'Down'} ---")

    # 方法1: 直接传参数给 netsh，适配器名称不会被 PowerShell 解释
    netsh_args = ["netsh", "interface", "set", "interface", f"name={name}", f"admin={action}"]
    log(f"  [netsh] {netsh_args}")
    try:
        r = subprocess.run(
            netsh_args, capture_output=True, text=True, timeout=20,
            startupinfo=STARTUP_INFO, creationflags=_CF, shell=False,
        )
    except Exception as e:
        r = None
        log(f"  [netsh] EXCEPTION: {e}")
    if r:
        log(f"  [netsh] returncode={r.returncode}, stdout=[{r.stdout.strip()}], stderr=[{r.stderr.strip()}]")
        netsh_ok = (r.returncode == 0)
    else:
        netsh_ok = False
        log(f"  [netsh] returned None")

    # 方法2: 如果 netsh 失败，尝试 Enable/Disable-NetAdapter
    if not netsh_ok:
        if want_enable:
            cmdlet_cmd = f"Enable-NetAdapter -Name '{ps_quote(name)}' -Confirm:$false"
        else:
            cmdlet_cmd = f"Disable-NetAdapter -Name '{ps_quote(name)}' -Confirm:$false"
        log(f"  [cmdlet] {cmdlet_cmd}")
        r2 = ps_full(cmdlet_cmd)
        if r2:
            log(f"  [cmdlet] returncode={r2.returncode}, stdout=[{r2.stdout.strip()}], stderr=[{r2.stderr.strip()}]")
        else:
            log(f"  [cmdlet] ps_full returned None")

    time.sleep(2.5)
    new_status = get_adapter_status(name)
    log(f"  result: {current} -> {new_status} (expected: {'Up' if want_enable else 'Down'})")
    return new_status


# ============================================================
#  首次运行：创建桌面快捷方式 + 配置文件
# ============================================================
def ensure_config():
    """如果 config.ini 不存在则创建默认配置"""
    if os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(
                "# 网络开关配置文件\n"
                "# 留空 = 自动检测适配器名称\n"
                "# 查看适配器名称: PowerShell 中运行 Get-NetAdapter | Select-Object Name, MediaType\n"
                "\n"
                "[network]\n"
                "ethernet_adapter =\n"
                "wifi_adapter =\n"
            )
    except:
        pass


def ensure_shortcuts():
    """确保桌面快捷方式存在"""
    if not getattr(sys, 'frozen', False):
        return  # 仅打包成 exe 后才创建快捷方式

    exe_path = sys.executable
    exe_dir = APP_DIR

    desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
    shortcuts = [(os.path.join(desktop, '网络开关.lnk'), '桌面快捷方式')]

    for path, label in shortcuts:
        if os.path.exists(path):
            continue
        try:
            ps_script = (
                f"$ws = New-Object -ComObject WScript.Shell\n"
                f"$sc = $ws.CreateShortcut('{ps_quote(path)}')\n"
                f"$sc.TargetPath = '{ps_quote(exe_path)}'\n"
                f"$sc.WorkingDirectory = '{ps_quote(exe_dir)}'\n"
                f"$sc.IconLocation = 'shell32.dll,13'\n"
                f"$sc.Save()\n"
            )
            r = ps_full(ps_script)
            if r and r.returncode == 0:
                log(f"Created shortcut: {label} -> {path}")
            else:
                log(f"Failed to create shortcut {label}: rc={r.returncode if r else 'None'}")
        except Exception as e:
            log(f"Exception creating shortcut {label}: {e}")


# ============================================================
#  双开关 UI（精简版 + 侧边吸附 + 自动收回）
# ============================================================
class DesktopSwitch:
    W = 62     # 展开宽度
    H = 84     # 展开高度
    TAB = TAB_SIZE

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.geometry(f"{self.W}x{self.H}+100+100")
        self.root.configure(bg='#e8e8ed')
        self.root.attributes('-alpha', 0.4)

        self.canvas = tk.Canvas(
            self.root, width=self.W, height=self.H,
            bg='#e8e8ed', highlightthickness=0,
        )
        self.canvas.pack(fill='both', expand=True)

        # ---- 状态 ----
        self.eth_on = False
        self.wifi_on = False
        self.docked = False
        self.dock_edge = None
        self.expanded_x = 100
        self.expanded_y = 100

        # ---- 从侧边悬停展开后，鼠标离开需自动收回 ----
        self._should_redock = False
        self._redock_edge = None
        self._redock_after_id = None

        # ---- 拖动 ----
        self._offset_x = 0
        self._offset_y = 0
        self._dragging = False

        # ---- 绘制 ----
        self._draw_bg()
        self._draw_close()
        self._draw_labels()
        self._draw_switch('eth')
        self._draw_switch('wifi')

        # ---- 事件绑定 ----
        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_motion)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<Enter>', self._on_enter)
        self.canvas.bind('<Leave>', self._on_leave)

        self._busy_eth = False
        self._busy_wifi = False
        self._polling = True

        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ================================================================
    #  绘制
    # ================================================================

    def _draw_bg(self):
        r = 6
        w, h = self.W, self.H
        if self.docked:
            return
        self.canvas.delete('bg')
        self.canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill='#ffffff', outline='', tags='bg')
        self.canvas.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill='#ffffff', outline='', tags='bg')
        self.canvas.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill='#ffffff', outline='', tags='bg')
        self.canvas.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill='#ffffff', outline='', tags='bg')
        self.canvas.create_rectangle(r, 0, w-r, h, fill='#ffffff', outline='', tags='bg')
        self.canvas.create_rectangle(0, r, w, h-r, fill='#ffffff', outline='', tags='bg')
        self.canvas.tag_lower('bg')

    def _draw_close(self):
        self.canvas.delete('close_btn'); self.canvas.delete('close_text')
        if self.docked:
            return
        self.canvas.create_rectangle(self.W - 16, 0, self.W, 14, fill='', outline='', tags='close_btn')
        self.canvas.create_text(
            self.W - 8, 7,
            text="x", font=('Arial', 8, 'bold'),
            fill='#bbb', anchor='center', tags=('close_text',)
        )

    def _draw_labels(self):
        self.canvas.delete('label')
        self.canvas.create_text(
            self.W // 2, 10,
            text="乙太網",
            font=('Microsoft YaHei', 7),
            fill='#999',
            anchor='center',
            tags=('label',)
        )
        self.canvas.create_text(
            self.W // 2, 48,
            text="Wi-Fi",
            font=('Microsoft YaHei', 7),
            fill='#999',
            anchor='center',
            tags=('label',)
        )

    def _draw_switch(self, which):
        self.canvas.delete(f'{which}_body')
        self.canvas.delete(f'{which}_ball')
        self.canvas.delete(f'{which}_on_text')
        self.canvas.delete(f'{which}_off_text')

        sw, sh = 50, 20
        x0 = (self.W - sw) // 2
        y0 = 18 if which == 'eth' else 58
        r = sh // 2
        ball_r = r - 3

        is_on = self.eth_on if which == 'eth' else self.wifi_on

        if is_on:
            bg_color = '#22c55e'
            text, text_color, text_x = "On", '#ffffff', x0 + 13
            ball_x = x0 + sw - r - 2
        else:
            bg_color = '#c4c4cc'
            text, text_color, text_x = "Off", '#aaaaaf', x0 + sw - 11
            ball_x = x0 + r + 2

        self.canvas.create_arc(x0, y0, x0+sh, y0+sh, start=90, extent=180,
                               fill=bg_color, outline='', tags=f'{which}_body')
        self.canvas.create_arc(x0+sw-sh, y0, x0+sw, y0+sh, start=270, extent=180,
                               fill=bg_color, outline='', tags=f'{which}_body')
        self.canvas.create_rectangle(x0+sh//2, y0, x0+sw-sh//2, y0+sh,
                                     fill=bg_color, outline='', tags=f'{which}_body')
        self.canvas.create_text(
            text_x, y0 + r,
            text=text, font=('Segoe UI', 8, 'bold'),
            fill=text_color, anchor='center',
            tags=(f'{which}_on_text',) if is_on else (f'{which}_off_text',)
        )
        self.canvas.create_oval(
            ball_x - ball_r, y0 + r - ball_r,
            ball_x + ball_r, y0 + r + ball_r,
            fill='#ffffff', outline='',
            tags=f'{which}_ball'
        )
        self.canvas.create_oval(
            ball_x - ball_r, y0 + r - ball_r,
            ball_x + ball_r, y0 + r + ball_r,
            outline='#ddd', width=1,
            tags=f'{which}_ball'
        )

    def _draw_docked_tab(self):
        self.canvas.delete('all')
        w = self.root.winfo_width()
        h = self.root.winfo_height()

        any_on = self.eth_on or self.wifi_on
        color = '#22c55e' if any_on else '#aaa'

        if self.dock_edge in ('left', 'right'):
            self.canvas.create_rectangle(0, 0, w, h, fill=color, outline='', tags='tab_bg')
            self.canvas.create_text(
                w // 2, h // 2,
                text="网",
                font=('Microsoft YaHei', 7, 'bold'),
                fill='#ffffff',
                anchor='center',
                tags='tab_label'
            )
        else:
            self.canvas.create_rectangle(0, 0, w, h, fill=color, outline='', tags='tab_bg')
            self.canvas.create_text(
                w // 2, h // 2,
                text="网络",
                font=('Microsoft YaHei', 6),
                fill='#ffffff',
                anchor='center',
                tags='tab_label'
            )

    # ================================================================
    #  拖动 / 点击
    # ================================================================

    def _on_press(self, event):
        self._offset_x = event.x
        self._offset_y = event.y
        self._dragging = False

    def _on_motion(self, event):
        if not self._dragging:
            if abs(event.x - self._offset_x) <= DRAG_THRESHOLD and \
               abs(event.y - self._offset_y) <= DRAG_THRESHOLD:
                return
            self._dragging = True
            self._should_redock = False

        if self.docked:
            self._expand_instant(from_drag=True)
            self._offset_x = event.x
            self._offset_y = event.y
            return

        new_x = self.root.winfo_pointerx() - self._offset_x
        new_y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_release(self, event):
        if self._dragging:
            self._dragging = False
            self._after_drag()
        else:
            self._handle_click(event.x, event.y)

    def _handle_click(self, cx, cy):
        if cx >= self.W - 16 and cy <= 14 and not self.docked:
            self._on_close()
            return
        if 18 <= cy <= 38:
            self._on_toggle('eth')
        elif 58 <= cy <= 78:
            self._on_toggle('wifi')

    def _after_drag(self):
        self.expanded_x = self.root.winfo_x()
        self.expanded_y = self.root.winfo_y()
        self._check_edge_dock(from_drag=True)

    # ================================================================
    #  侧边吸附 / 展开
    # ================================================================

    def _check_edge_dock(self, from_drag=False):
        if self.docked:
            return

        x = self.root.winfo_x()
        y = self.root.winfo_y()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        dist_left = x
        dist_right = sw - (x + self.W)
        dist_top = y
        dist_bottom = sh - (y + self.H)

        mind = min(dist_left, dist_right, dist_top, dist_bottom)

        if mind > EDGE_THRESHOLD:
            return

        if dist_left == mind:
            self._dock('left')
        elif dist_right == mind:
            self._dock('right')
        elif dist_top == mind:
            self._dock('top')

    def _dock(self, edge):
        self._should_redock = False
        self._redock_edge = None
        self.dock_edge = edge
        self.docked = True
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        x = self.root.winfo_x()
        y = self.root.winfo_y()
        if x >= 0 and x + self.W <= sw:
            self.expanded_x = x
        if y >= 0 and y + self.H <= sh:
            self.expanded_y = y

        if edge == 'left':
            self.root.geometry(f"{self.TAB}x{self.H}+0+{self.expanded_y}")
        elif edge == 'right':
            self.root.geometry(f"{self.TAB}x{self.H}+{sw - self.TAB}+{self.expanded_y}")
        elif edge == 'top':
            self.root.geometry(f"{self.W}x{self.TAB}+{self.expanded_x}+0")

        self.root.attributes('-alpha', 0.75)
        self._draw_docked_tab()

    def _expand_instant(self, from_drag=False, from_hover=False):
        if not self.docked:
            return

        edge = self.dock_edge
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        y = self.expanded_y
        x = self.expanded_x

        if x + self.W > sw:
            x = sw - self.W
        if y + self.H > sh:
            y = sh - self.H
        if x < 0:
            x = 0
        if y < 0:
            y = 0

        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.docked = False
        self.dock_edge = None
        if from_hover:
            self._should_redock = True
            self._redock_edge = edge
        else:
            self._should_redock = False
        self.root.attributes('-alpha', 1.0)
        self._redraw_all()

    def _redraw_all(self):
        self.canvas.delete('all')
        self._draw_bg()
        self._draw_close()
        self._draw_labels()
        self._draw_switch('eth')
        self._draw_switch('wifi')

    # ================================================================
    #  鼠标进入/离开
    # ================================================================

    def _on_enter(self, event):
        if self._redock_after_id:
            self.root.after_cancel(self._redock_after_id)
            self._redock_after_id = None
        if self.docked:
            self._expand_instant(from_hover=True)
        else:
            self.root.attributes('-alpha', 1.0)

    def _on_leave(self, event):
        if self._should_redock:
            self._redock_after_id = self.root.after(400, self._do_redock)
        else:
            self.root.attributes('-alpha', 0.4)

    def _do_redock(self):
        self._redock_after_id = None
        if self._should_redock and not self.docked:
            edge = self._redock_edge
            self._should_redock = False
            self._redock_edge = None
            self._dock(edge)

    # ================================================================
    #  开关操作
    # ================================================================

    def _on_toggle(self, which):
        adapter = ETH_ADAPTER if which == 'eth' else WIFI_ADAPTER
        if not adapter:
            return

        busy_attr = f'_busy_{which}'
        if getattr(self, busy_attr):
            return
        setattr(self, busy_attr, True)

        on_attr = f'{which}_on'
        was_on = getattr(self, on_attr)
        setattr(self, on_attr, not was_on)
        self._draw_switch(which)

        log(f"UI toggle: {which} ({adapter}), was_on={was_on} -> {not was_on}")

        def do_toggle():
            try:
                new_s = toggle_adapter(adapter)
                log(f"toggle result: {which} -> {new_s}")
                self.root.after(0, lambda: self._update_state(which, new_s))
            except Exception as e:
                log(f"toggle EXCEPTION: {which} -> {e}")
                self.root.after(0, lambda: self._rollback_ui(which, was_on))
            finally:
                setattr(self, busy_attr, False)

        threading.Thread(target=do_toggle, daemon=True).start()

    def _rollback_ui(self, which, was_on):
        on_attr = f'{which}_on'
        setattr(self, on_attr, was_on)
        self._draw_switch(which)

    def _on_close(self, event=None):
        self._polling = False
        self.root.destroy()
        sys.exit(0)

    # ================================================================
    #  状态轮询
    # ================================================================

    def _update_state(self, which, status):
        is_on = (status == "Up")
        on_attr = f'{which}_on'
        if is_on != getattr(self, on_attr):
            setattr(self, on_attr, is_on)
            if self.docked:
                self._draw_docked_tab()
            else:
                self._draw_switch(which)

    def _poll_loop(self):
        last_eth, last_wifi = None, None
        while self._polling:
            if ETH_ADAPTER:
                try:
                    s = get_adapter_status(ETH_ADAPTER)
                    if s != last_eth:
                        last_eth = s
                        if not self._busy_eth:
                            self.root.after(0, lambda s=s: self._update_state('eth', s))
                except:
                    pass
            if WIFI_ADAPTER:
                try:
                    s = get_adapter_status(WIFI_ADAPTER)
                    if s != last_wifi:
                        last_wifi = s
                        if not self._busy_wifi:
                            self.root.after(0, lambda s=s: self._update_state('wifi', s))
                except:
                    pass
            time.sleep(POLL_INTERVAL)

    def run(self):
        self.root.mainloop()


# ============================================================
#  主入口
# ============================================================
if __name__ == "__main__":
    # 清空旧日志，记录启动信息
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== 网络开关 便携版 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"管理员权限: {is_admin()}\n")
            f.write(f"Python: {sys.executable}\n")
            f.write(f"APP_DIR: {APP_DIR}\n")
            f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
    except:
        pass

    # 创建默认配置文件
    ensure_config()

    # 检测适配器
    detect_adapters()

    if not ETH_ADAPTER and not WIFI_ADAPTER:
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox
        messagebox.showerror(
            '网络开关',
            '未检测到网络适配器！\n\n'
            '请打开 config.ini 手动填写适配器名称。\n'
            '查看方法：PowerShell 中运行 Get-NetAdapter'
        )
        root.destroy()
        sys.exit(1)

    # 创建桌面快捷方式
    try:
        ensure_shortcuts()
    except:
        pass

    # 启动
    app = DesktopSwitch()
    app.run()
