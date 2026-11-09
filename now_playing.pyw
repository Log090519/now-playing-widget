# -*- coding: utf-8 -*-
"""
Now Playing 위젯
바탕화면에 지금 재생 중인 곡(앨범아트 · 제목 · 가수 · 진행바)을 작게 띄워 줍니다.

- Windows 미디어 컨트롤에 곡 정보를 보내는 앱이면 다 됩니다.
  (Spotify, 크롬/엣지의 YouTube · YouTube Music, Windows 미디어 플레이어 등)
- 작업표시줄이 올라오면 위젯도 같이 밀려 올라가고, 내려가면 제자리로 돌아옵니다.
- 진행바는 Windows 강조색 그라데이션으로 칠해집니다 (설정 > 개인 설정 > 색).
- 드래그: 위치 이동 (자동 저장)
- 마우스를 올리면 왼쪽 위에 ⚙(설정), 오른쪽 위에 ✕(종료)가 나타납니다
- 설정: 강조색 진행바 · 강조색 위젯 배경 · 불투명도 · 바탕화면에 붙이기(Win+D 에도 보임) · 작업표시줄 따라가기 · 부드러움
        · 위치 초기화 (%APPDATA%\\NowPlayingWidget\\now_playing_config.json 에 저장)
- 작업표시줄 알림 영역(트레이) 아이콘: 클릭 = 설정, 우클릭 = 메뉴
- 소리 나는 앱이 여럿이면 음악 앱(Spotify 등) · 음악 사이트(YouTube Music 등)를 먼저 보여줍니다

실행:     now_playing.pyw 더블클릭
미리보기: python now_playing.pyw --demo [playing|paused|live|empty|long]
설치 파일(.msi) 만들기: python setup.py bdist_msi
필요 패키지:  pip install -r requirements.txt
"""
import asyncio
import ctypes
import hashlib
import io
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageOps, ImageTk

FROZEN = getattr(sys, "frozen", False)          # 설치용 exe 로 만들어졌으면 True
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
# 설정 · 로그는 %APPDATA%\NowPlayingWidget 에 (설치 폴더는 쓰기가 안 될 수 있음)
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NowPlayingWidget")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(DATA_DIR, "now_playing_config.json")
LOG_PATH = os.path.join(DATA_DIR, "now_playing.log")
_OLD_CONFIG = os.path.join(APP_DIR, "now_playing_config.json")   # 예전 버전은 프로그램 옆에 저장했음 → 한 번 옮겨옴
if not os.path.exists(CONFIG_PATH) and os.path.exists(_OLD_CONFIG):
    try:
        shutil.copyfile(_OLD_CONFIG, CONFIG_PATH)
    except OSError:
        pass
WINDOW_TITLE = "NowPlayingWidget"
APP_NAME = "Now Playing"

# ---- 버전 · 업데이트 ----
# 새 버전을 낼 때: 이 숫자를 올리고  python release.py  (설치 파일을 만들어 GitHub Release 에 올림)
APP_VERSION = "1.1.0"
GITHUB_REPO = "Log090519/now-playing-widget"   # 업데이트를 받아 올 공개 저장소 (비우면 확인 안 함)
UPDATE_CHECK_HOURS = 6       # 자동 확인 주기

# ---------------------------------------------------------------- 디자인 ----
# 크기는 100% 배율(96 DPI) 기준 픽셀이고, 실행할 때 화면 배율만큼 커집니다.
CARD_W, CARD_H = 360, 96
PAD = 14            # 카드 안쪽 여백
ART = 68            # 앨범아트 한 변
ART_RADIUS = 8      # 앨범아트 모서리 둥글기
GAP = 12            # 앨범아트와 글자 사이
BAR_H = 4           # 진행바 두께
MARGIN = 24         # 화면 아래(또는 작업표시줄)와 위젯 사이 간격
ALPHA = 0.92        # 카드 불투명도 (0~1)
FONT = "Malgun Gothic"

BG = "#141418"
FG = "#f2f2f5"
SUB = "#a3a3ad"
DIM = "#6c6c78"
TRACK = "#2c2c35"
FILL = "#e9e9ef"    # 강조색을 안 쓸 때 진행바 색
LIVE = "#ff5c5c"
ART_EMPTY = "#262630"

# 설정 창
PANEL = "#1b1b21"
CONTROL_OFF = "#3a3a45"
BUTTON = "#2a2a33"
BUTTON_HOVER = "#363641"

# ↓ 이 네 가지는 기본값이에요. 위젯 왼쪽 위 ⚙ 설정에서 바꾸면 now_playing_config.json 에 저장되고 그 값이 우선합니다.
USE_ACCENT = True         # 진행바에 Windows 강조색 그라데이션 (False 면 FILL 단색)
ACCENT_CARD = False       # 위젯 배경에도 강조색 그라데이션
DESKTOP_MODE = False      # 바탕화면에 붙이기 (Win+D 를 눌러도 사라지지 않음)
FOLLOW_TASKBAR = True     # 작업표시줄 따라 움직이기 (작업표시줄 자동 숨기기가 켜져 있을 때만)
SMOOTH_TIME = 0.10        # 따라가는 부드러움 (초). 클수록 느긋하고 부드럽게, 작을수록 바짝 붙어서
# ALPHA (불투명도) 는 위쪽에 있어요

ACCENT_STOPS = (4, 2, 1)  # 진행바 왼쪽 → 오른쪽에 쓸 강조색 단계 (0 = 가장 밝음 … 6 = 가장 어두움)
FOLLOW_IDLE_MS = 40       # 가만히 있을 때 작업표시줄 확인 주기 (움직이는 동안은 모니터 주사율에 맞춤)

POLL_SEC = 1.0      # 곡 정보 확인 주기
TICK_MS = 250       # 진행바 갱신 주기
ACCENT_POLL_MS = 3000

# GlobalSystemMediaTransportControlsSessionPlaybackStatus
PLAYING, PAUSED = 4, 5

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("NOWPLAYING_DEBUG") else logging.WARNING,   # 문제 찾을 때만 자세히
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8", delay=True)],
)

# ----------------------------------------------------------------- Win32 ----
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CHILD, WS_POPUP = 0x40000000, 0x80000000
WS_EX_TOOLWINDOW = 0x00000080   # 작업표시줄 · Alt+Tab 에 안 보이게
WS_EX_NOACTIVATE = 0x08000000   # 클릭해도 앞으로 튀어나오지 않게
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x2
HWND_TOP, HWND_BOTTOM = wintypes.HWND(0), wintypes.HWND(1)
SWP_NOZORDER = 0x0004
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
SPI_GETWORKAREA = 0x0030
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTONEAREST = 0, 2
ERROR_ALREADY_EXISTS = 183


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
user32.SetWindowRgn.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
ctypes.windll.gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
MUTEX_NAME = "Local\\NowPlayingWidget"            # 하나만 실행되게
QUIT_EVENT_NAME = "Local\\NowPlayingWidgetQuit"   # 제거 프로그램이 '종료해 줘' 하고 보내는 신호


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


ctypes.windll.shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
ctypes.windll.shell32.SHAppBarMessage.restype = ctypes.c_size_t


def taskbar_autohide():
    """Windows 설정의 '작업 표시줄 자동 숨기기' 가 켜져 있는지."""
    try:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        return bool(ctypes.windll.shell32.SHAppBarMessage(4, ctypes.byref(abd)) & 1)   # ABM_GETSTATE, ABS_AUTOHIDE
    except Exception:
        return False


def find_desktop_host():
    """바탕화면 아이콘(SHELLDLL_DefView)을 품고 있는 창 = 위젯을 붙일 바탕화면 (Progman 또는 WorkerW)."""
    progman = user32.FindWindowExW(None, None, "Progman", None)
    if progman and user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None):
        return progman
    h = None
    while True:   # 배경화면 프로그램 등이 아이콘을 WorkerW 쪽으로 옮겨 놓은 경우
        h = user32.FindWindowExW(None, h, "WorkerW", None)
        if not h:
            return None
        if user32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
            return h


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def visible_rect(hwnd):
    """그림자·투명 테두리를 뺀, 눈에 보이는 창 영역."""
    r = wintypes.RECT()
    try:
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r),
                                                      ctypes.sizeof(r)) == 0:   # EXTENDED_FRAME_BOUNDS
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return window_rect(hwnd)


APP_USER_MODEL_ID = "NowPlayingWidget.App"


def set_app_id():
    """
    작업표시줄이 이 프로그램을 'python' 이 아닌 별도 앱으로 보게 함.
    (안 하면 스크립트로 실행할 때 설정 창이 python 아이콘으로 묶여서 보임)
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def set_dpi_awareness():
    """Tk() 를 만들기 전에 불러야 고해상도 화면에서 흐릿하지 않습니다."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def work_area():
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def point_on_screen(x, y):
    return bool(user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONULL))


def monitor_rect_at(x, y, work=False):
    """(x, y) 가 있는 모니터 영역 (left, top, right, bottom). work=True 면 작업표시줄을 뺀 영역."""
    mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        r = info.rcWork if work else info.rcMonitor
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def window_rect(hwnd):
    r = wintypes.RECT()
    if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def find_bottom_taskbar(mon):
    """해당 모니터 아래쪽에 붙은 작업표시줄 창을 찾습니다 (없으면 None)."""
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        h = None
        while True:
            h = user32.FindWindowExW(None, h, cls, None)
            if not h:
                break
            r = window_rect(h)
            if r is None:
                continue
            left, top, right, bottom = r
            horizontal = (right - left) > (bottom - top)
            on_this_monitor = left < mon[2] and right > mon[0]
            at_bottom = bottom >= mon[3] - 2 and top > (mon[1] + mon[3]) // 2
            if horizontal and on_this_monitor and at_bottom:
                return h
    return None


def refresh_interval_ms():
    """모니터 주사율에 맞춘 프레임 간격 (165Hz → 6ms). 4~16ms 사이로 제한."""
    try:
        dc = user32.GetDC(0)
        hz = ctypes.windll.gdi32.GetDeviceCaps(dc, 116)   # VREFRESH
        user32.ReleaseDC(0, dc)
    except Exception:
        hz = 60
    if hz <= 1:
        hz = 60
    return max(4, min(16, int(1000 / hz)))


def smooth_damp(current, target, velocity, smooth_time, dt):
    """목표를 향해 부드럽게 가속했다가 감속하는 스프링 이동. (새 위치, 새 속도) 를 돌려줌."""
    omega = 2.0 / max(smooth_time, 1e-4)
    x = omega * dt
    decay = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
    change = current - target
    temp = (velocity + omega * change) * dt
    velocity = (velocity - omega * temp) * decay
    out = target + (change + temp) * decay
    if (target - current > 0) == (out > target):   # 목표를 넘어가지 않게
        out, velocity = target, 0.0
    return out, velocity


def follow_target(base_y, h, mon_bottom, tb_top, margin):
    """
    작업표시줄이 올라온 만큼 위젯을 밀어 올린 y 좌표.
    - 작업표시줄이 숨어 있으면(몇 px 만 보이면) 원래 위치 그대로
    - 위젯이 화면 아래쪽에 있으면, 화면 바닥과 떨어져 있던 간격(최대 margin)을 작업표시줄 위에서도 유지
    - 위젯이 위쪽에 있어서 부딪히지 않으면 움직이지 않음
    """
    if tb_top is None:
        return base_y
    visible_top = tb_top if (mon_bottom - tb_top) > 4 else mon_bottom
    gap = min(max(mon_bottom - (base_y + h), 0), margin)
    return min(base_y, visible_top - h - gap)


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except Exception:
        logging.exception("설정 저장 실패")


DEFAULT_SETTINGS = {
    "use_accent": USE_ACCENT,
    "accent_card": ACCENT_CARD,
    "desktop_mode": DESKTOP_MODE,
    "follow_taskbar": FOLLOW_TASKBAR,
    "smooth_time": SMOOTH_TIME,
    "alpha": ALPHA,
    "auto_update": True,      # 새 버전 자동 확인
}
SETTING_RANGES = {"smooth_time": (0.04, 0.20), "alpha": (0.40, 1.00)}


def clean_settings(cfg):
    """설정 파일 값 중 올바른 것만 골라 기본값 위에 덮어씁니다."""
    s = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        v = cfg.get(key)
        if isinstance(default, bool):
            if isinstance(v, bool):
                s[key] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            lo, hi = SETTING_RANGES[key]
            s[key] = min(max(float(v), lo), hi)
    return s


# ------------------------------------------------------------ 강조색 ----
def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def read_accent_palette():
    """
    Windows 강조색 팔레트 7단계 (0 = 가장 밝음 … 3 = 강조색 … 6 = 가장 어두움).
    읽을 수 없으면 None.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as k:
            data, _ = winreg.QueryValueEx(k, "AccentPalette")
        if isinstance(data, bytes) and len(data) >= 28:
            return [tuple(data[i * 4:i * 4 + 3]) for i in range(7)]
    except OSError:
        pass
    try:  # 팔레트가 없으면 강조색 하나로 단계를 만들어 씀
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
            v, _ = winreg.QueryValueEx(k, "AccentColor")   # 0xAABBGGRR
        base = (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)
        white, black = (255, 255, 255), (0, 0, 0)
        return [_mix(base, white, 0.75), _mix(base, white, 0.5), _mix(base, white, 0.25), base,
                _mix(base, black, 0.25), _mix(base, black, 0.5), _mix(base, black, 0.75)]
    except OSError:
        return None


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def gradient_image(width, height, colors):
    """colors 를 왼쪽 → 오른쪽으로 고르게 잇는 가로 그라데이션."""
    width = max(width, 1)
    row = Image.new("RGB", (width, 1))
    px = row.load()
    n = len(colors) - 1
    for x in range(width):
        if n == 0:
            px[x, 0] = colors[0]
            continue
        p = x / max(width - 1, 1) * n
        i = min(int(p), n - 1)
        px[x, 0] = _mix(colors[i], colors[i + 1], p - i)
    return row.resize((width, max(height, 1)), Image.NEAREST)


# ------------------------------------------------------------- 곡 정보 ----
@dataclass
class Track:
    key: tuple                 # 곡이 바뀌었는지 판단하는 값
    title: str
    artist: str
    status: int
    position: float            # 초
    duration: float            # 초 (0 = 정보 없음, 음수 = 라이브)
    updated: float             # position 이 기록된 시각 (epoch 초)
    rate: float
    thumb: Optional[bytes]     # 새 앨범아트가 생겼을 때만 들어 있음


# ---- 소리 나는 앱이 여러 개일 때 어느 것을 보여줄지 ----
# 음악 앱 (앱 ID 에 이 글자가 들어 있으면)
MUSIC_APPS = ("spotify", "applemusic", "itunes", "zunemusic", "foobar2000", "musicbee", "tidal", "deezer",
              "amazonmusic", "youtube-music", "youtubemusic", "melon", "winamp", "soundcloud", "qobuz",
              "cider", "pandora")
MUSIC_APP_WORDS = {"aimp", "flo", "bugs", "genie", "vibe"}   # 짧은 이름은 단어 단위로만 비교


def is_music_app(app_id):
    a = (app_id or "").lower()
    if any(k in a for k in MUSIC_APPS):
        return True
    return bool(set(re.split(r"[^a-z0-9]+", a)) & MUSIC_APP_WORDS)


def session_score(app_id, playing, album, artist, is_current):
    """
    높을수록 위젯에 보여줄 세션.
    - 실제로 재생 중인 것이 먼저 (일시정지된 음악보다 지금 소리 나는 영상)
    - 둘 다 재생 중이면 음악 앱, 그다음 앨범 정보가 있는 것 (YouTube Music · Spotify 웹 등은 앨범을 알려줌,
      일반 YouTube 영상은 비어 있음)
    """
    score = 0
    if playing:
        score += 100
    if is_music_app(app_id):
        score += 40
    if album:
        score += 25
    if artist:
        score += 5
    if is_current:      # Windows 가 '현재' 라고 고른 세션은 동점일 때만 의미 있게
        score += 1
    return score


class SessionPicker:
    """
    보여줄 세션 고르기.
    곡이 넘어가는 순간 잠깐 '재생 중 아님' 이 되는 앱이 많아서, 최근 3초 안에 재생 중이었으면 재생 중으로 봄.
    또 지금 보여주는 세션에 약간의 가산점을 줘서 점수가 비슷할 때 왔다 갔다 하지 않게 함.
    """
    GRACE = 3.0
    STICKY = 10

    def __init__(self):
        self.shown = None
        self.last_playing = {}

    def pick(self, cands, now):
        """cands: [(app_id, playing, album, artist, is_current)] → 보여줄 후보의 index (없으면 None)"""
        best = best_score = None
        for i, (app, playing, album, artist, current) in enumerate(cands):
            if playing:
                self.last_playing[app] = now
            recently = now - self.last_playing.get(app, -1e9) < self.GRACE
            s = session_score(app, playing or recently, album, artist, current)
            if app == self.shown:
                s += self.STICKY
            if best_score is None or s > best_score:
                best, best_score = i, s
        self.shown = cands[best][0] if best is not None else None
        return best


async def read_thumbnail(ref):
    if ref is None:
        return None
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
    stream = await ref.open_read_async()
    size = stream.size
    if not size:
        return None
    buf = Buffer(size)
    await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
    return bytes(buf)


class MediaWatcher(threading.Thread):
    """별도 스레드에서 Windows 미디어 세션을 주기적으로 읽어 큐에 넣습니다."""

    def __init__(self, out: queue.Queue):
        super().__init__(daemon=True)
        self.out = out

    def run(self):
        logging.debug("미디어 감시 시작")
        try:
            asyncio.run(self._loop())
        except BaseException:
            logging.exception("미디어 감시 스레드 종료")

    async def _loop(self):
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
            )
        except ImportError:
            logging.exception("winrt 불러오기 실패")
            self.out.put(("error", "winrt 패키지가 없어요 (파일 맨 위 설명 참고)"))
            return
        logging.debug("winrt 불러옴")

        mgr = None
        picker = SessionPicker()
        logged = set()
        last_key, last_thumb, thumb_tries = None, None, 0
        while True:
            try:
                if mgr is None:
                    mgr = await Manager.request_async()
                # 소리 나는 앱이 여럿이면 음악 앱 / 음악 사이트를 먼저 (SessionPicker 참고)
                current = mgr.get_current_session()
                cur_app = current.source_app_user_model_id if current else None
                cands, infos = [], []
                for s in mgr.get_sessions():
                    try:
                        p = await s.try_get_media_properties_async()
                        b = s.get_playback_info()
                    except Exception as e:
                        if type(e).__name__ not in logged:   # 같은 종류 오류는 한 번만 기록
                            logged.add(type(e).__name__)
                            logging.exception("미디어 세션 하나를 읽지 못함 (건너뜀)")
                        continue
                    app = s.source_app_user_model_id
                    cands.append((app, int(b.playback_status) == PLAYING, (p.album_title or "").strip(),
                                  (p.artist or "").strip(), app == cur_app))
                    infos.append((s, p, b))
                idx = picker.pick(cands, time.monotonic())
                logging.debug("세션 %d개 %s → %s", len(cands), [c[0] for c in cands], idx)
                session = infos[idx][0] if idx is not None else None
                if session is None:
                    last_key = None
                    self.out.put(("track", None))
                else:
                    session, props, pb = infos[idx]
                    tl = session.get_timeline_properties()

                    title = (props.title or "").strip()
                    artist = (props.artist or "").strip() or (props.album_artist or "").strip()
                    key = (session.source_app_user_model_id, title, artist)
                    if key != last_key:
                        # 앱이 앨범아트를 곡 정보보다 늦게 바꾸는 경우가 있어 몇 번 다시 확인
                        last_key, last_thumb, thumb_tries = key, None, 3

                    new_thumb = None
                    if thumb_tries > 0:
                        thumb_tries -= 1
                        try:
                            data = await read_thumbnail(props.thumbnail)
                        except Exception:
                            data = None
                        if data and data != last_thumb:
                            last_thumb = new_thumb = data

                    start = tl.start_time.total_seconds()
                    duration = tl.end_time.total_seconds() - start
                    position = tl.position.total_seconds() - start
                    try:
                        updated = tl.last_updated_time.timestamp()
                    except Exception:
                        updated = time.time()
                    if updated < 1e9:          # 기록이 없으면 1601년 같은 값이 옴
                        updated = time.time()

                    self.out.put(("track", Track(
                        key=key, title=title, artist=artist,
                        status=int(pb.playback_status),
                        position=position, duration=duration, updated=updated,
                        rate=pb.playback_rate or 1.0, thumb=new_thumb,
                    )))
            except Exception:
                logging.exception("곡 정보 읽기 실패")
                mgr = None
                await asyncio.sleep(3)
            await asyncio.sleep(POLL_SEC)


# ------------------------------------------------------------- 업데이트 ----
def parse_version(text):
    """'v1.2.3' → (1, 2, 3)"""
    nums = [int(n) for n in re.findall(r"\d+", text or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def ask_yes_no(text, title=APP_NAME):
    """Windows 기본 확인 창 (예 = True). 위젯이 멈추지 않도록 별도 스레드에서 부름."""
    MB_YESNO, MB_ICONQUESTION, MB_SETFOREGROUND, MB_TOPMOST = 0x4, 0x20, 0x10000, 0x40000
    return user32.MessageBoxW(None, text, title, MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST) == 6


def installed_exe_path():
    """설치 파일이 프로그램을 놓는 곳 (setup.py 의 initial_target_dir 와 같음)."""
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "NowPlaying", "NowPlaying.exe")


class Updater:
    """
    GitHub 의 최신 Release 를 확인해서, 지금보다 새 버전이면 설치 파일(.msi)을 받아 설치합니다.
    네트워크 작업은 별도 스레드에서 하고, 결과는 위젯 명령 큐로 보냅니다 (Tk 는 위젯 스레드에서만 만짐).
    상태: idle → checking → latest / available → downloading → (설치하며 종료) / error
    """
    API = "https://api.github.com/repos/{repo}/releases/latest"

    def __init__(self, widget: "Widget"):
        self.wd = widget
        self.state = "idle"
        self.latest = None        # {"version", "url", "name", "size", "digest", "page"}
        self.progress = 0.0
        self.message = ""

    @property
    def enabled(self):
        return bool(re.fullmatch(r"[\w.-]+/[\w.-]+", GITHUB_REPO or ""))

    def _request(self, url, accept="application/vnd.github+json"):
        return urllib.request.Request(url, headers={"Accept": accept,
                                                    "User-Agent": f"NowPlayingWidget/{APP_VERSION}"})

    # ---- 확인 ----
    def check(self, manual=False):
        if not self.enabled or self.state in ("checking", "downloading"):
            return
        self.state = "checking"
        threading.Thread(target=self._check, args=(manual,), daemon=True, name="update-check").start()

    def _check(self, manual):
        result, error = None, None
        try:
            with urllib.request.urlopen(self._request(self.API.format(repo=GITHUB_REPO)), timeout=15) as r:
                data = json.load(r)
            tag = data.get("tag_name") or ""
            asset = next((a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".msi")), None)
            if asset and parse_version(tag) > parse_version(APP_VERSION):
                result = {"version": tag.lstrip("vV"), "page": data.get("html_url"),
                          "url": asset.get("browser_download_url"), "name": asset.get("name"),
                          "size": asset.get("size"), "digest": asset.get("digest") or ""}
        except urllib.error.HTTPError as e:
            if e.code != 404:          # 404 = 아직 릴리스가 없음 → 최신으로 봄
                error = f"HTTP {e.code}"
        except Exception as e:
            error = str(e)
        if error:
            logging.warning("업데이트 확인 실패: %s", error)
        self.wd.commands.put(("update_checked", (result, manual, error)))

    def on_checked(self, result, manual, error):
        """(위젯 스레드) 확인 결과 반영."""
        if error:
            self.state, self.message = "error", "업데이트를 확인하지 못했어요"
        elif result:
            self.state, self.latest = "available", result
            self.message = f"새 버전 {result['version']} 이 있어요"
        else:
            self.state, self.message = "latest", "최신 버전이에요"
        if manual and self.state == "available":
            self.ask_and_update()
        elif manual:
            self.wd.notify(self.message if not error else f"{self.message} ({error})")
        elif self.state == "available":
            self.wd.notify(f"{self.message}. 위젯의 ⬇ 버튼으로 업데이트할 수 있어요")
        self.wd.update_ui_changed()

    # ---- 받기 · 설치 ----
    def ask_and_update(self):
        if self.state != "available":
            return
        v = self.latest["version"]
        text = (f"새 버전 {v} 이 있어요. (지금 {APP_VERSION})\n\n"
                "지금 업데이트할까요?\n위젯이 잠깐 꺼졌다가 새 버전으로 다시 켜져요.")
        threading.Thread(target=lambda: ask_yes_no(text) and self.wd.commands.put(("update_start", None)),
                         daemon=True).start()

    def start_download(self):
        if self.state != "available":
            return
        self.state, self.progress = "downloading", 0.0
        self.wd.update_ui_changed()
        threading.Thread(target=self._download, daemon=True, name="update-download").start()

    def _download(self):
        info = self.latest
        try:
            folder = os.path.join(tempfile.gettempdir(), "NowPlayingUpdate")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, os.path.basename(info["name"]))
            sha = hashlib.sha256()
            done, last = 0, -1
            with urllib.request.urlopen(self._request(info["url"], "application/octet-stream"), timeout=30) as r, \
                    open(path + ".part", "wb") as f:
                total = int(r.headers.get("Content-Length") or info.get("size") or 0)
                while True:
                    chunk = r.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    pct = int(done * 100 / total) if total else 0
                    if pct != last:
                        last = pct
                        self.wd.commands.put(("update_progress", pct / 100))
            if info.get("size") and done != info["size"]:
                raise IOError(f"받은 크기가 달라요 ({done} / {info['size']})")
            digest = info.get("digest", "")
            if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
                raise IOError("파일 검증(sha256)에 실패했어요")
            os.replace(path + ".part", path)
            self.wd.commands.put(("update_ready", path))
        except Exception as e:
            logging.exception("업데이트 받기 실패")
            self.wd.commands.put(("update_failed", str(e)))

    def install(self, msi_path):
        """
        (위젯 스레드) 받은 설치 파일 실행 → 위젯 종료.
        위젯이 켜져 있으면 파일을 바꿀 수 없어서, 숨은 명령 창이 잠깐 기다렸다가 설치하고 새 버전을 다시 켭니다.
        """
        exe = installed_exe_path()
        cmd = (f'ping -n 3 127.0.0.1 >nul & msiexec /i "{msi_path}" /passive /norestart'
               f' & if exist "{exe}" start "" "{exe}"')
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(f'cmd /s /c "{cmd}"', creationflags=CREATE_NO_WINDOW, close_fds=True)
        logging.info("업데이트 설치 시작: %s", msi_path)
        self.wd.quit()


# ------------------------------------------------------------- 화면 그리기 ----
def fmt_time(sec):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fit_text(font, text, max_px):
    """너무 긴 글자는 끝을 … 로 줄입니다."""
    if font.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def trim_letterbox(img):
    """유튜브 썸네일처럼 위아래 검은 띠가 있는 경우 잘라냅니다 (정사각형 이미지는 건드리지 않음)."""
    if abs(img.width / img.height - 1) < 0.1:
        return img
    mask = img.convert("L").point(lambda p: 255 if p > 18 else 0)
    box = mask.getbbox()
    if box and (box[2] - box[0]) > img.width * 0.5 and (box[3] - box[1]) > img.height * 0.5:
        return img.crop(box)
    return img


def rounded(img, radius, bg):
    w, h = img.size
    k = 4  # 4배로 그려서 줄이면 가장자리가 매끄러움
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=radius * k, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = bg.copy() if isinstance(bg, Image.Image) else Image.new("RGB", (w, h), bg)   # bg: 색 또는 배경 그림
    out.paste(img, (0, 0), mask)
    return out


def card_background(w, h, palette):
    """
    위젯 배경용 강조색 그라데이션.
    왼쪽 위(앨범아트 쪽)는 강조색이 은은하게 비치고, 오른쪽 아래로 갈수록 기본 배경색에 가까워짐.
    글자가 잘 읽히도록 강조색을 배경색에 섞어서 어둡게 씀.
    """
    bg = hex_rgb(BG)
    stops = [_mix(bg, palette[3], 0.68), _mix(bg, palette[4], 0.45), _mix(bg, palette[5], 0.30)]
    sw, sh = 96, 24   # 작게 계산한 뒤 부드럽게 키움
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    for y in range(sh):
        for x in range(sw):
            t = min(1.0, 0.8 * x / (sw - 1) + 0.2 * y / (sh - 1))   # 살짝 기운 대각선
            p = t * (len(stops) - 1)
            i = min(int(p), len(stops) - 2)
            px[x, y] = _mix(stops[i], stops[i + 1], p - i)
    return small.resize((w, h), Image.BICUBIC)


class Widget:
    def __init__(self, root: tk.Tk, source: queue.Queue, demo=False):
        self.root = root
        self.source = source
        self.demo = demo
        self.track: Optional[Track] = None
        self._drag = None
        self._moved = False
        self._pressed_btn = None
        self._settings_win = None
        self._save_job = None
        self.tray = None                  # main() 에서 붙임
        self.quit_event = None            # main() 에서 붙임 (제거 프로그램의 종료 신호)
        self.commands = queue.Queue()     # 트레이 메뉴 · 업데이트 스레드 → 위젯 명령
        self.updater = Updater(self)
        self.cfg = load_config()
        self.settings = clean_settings(self.cfg)

        self.k = root.winfo_fpixels("1i") / 96.0   # 화면 배율 (150% → 1.5)
        S = self.S
        self.w, self.h = S(CARD_W), S(CARD_H)

        root.title(WINDOW_TITLE)
        root.overrideredirect(True)
        root.configure(bg=BG)
        # base = 사용자가 놓아둔 자리(저장되는 값), shown = 지금 실제로 있는 자리
        self.base_x, self.base_y = self._initial_position()
        self.cur_y = float(self.base_y)
        self.shown_y = self.base_y
        root.geometry(f"{self.w}x{self.h}+{self.base_x}+{self.base_y}")

        self.f_title = tkfont.Font(family=FONT, size=11, weight="bold")
        self.f_artist = tkfont.Font(family=FONT, size=9)
        self.f_time = tkfont.Font(family=FONT, size=8)

        cv = self.cv = tk.Canvas(root, width=self.w, height=self.h, bg=BG, highlightthickness=0, bd=0)
        cv.pack()
        self.bg_item = cv.create_image(0, 0, anchor="nw", state="hidden")   # 강조색 배경 (맨 아래 층)
        self._card_bg = None
        self._art_data = None
        # 보조 글자색 · 진행바 홈 색 (강조색 배경일 때는 읽기 좋게 더 밝은 색으로 바뀜)
        self.sub, self.dim, self.track_col = SUB, DIM, TRACK
        self._colors_play = self._colors_pause = [hex_rgb(FILL)]

        ax, ay = S(PAD), (self.h - S(ART)) // 2
        self.tx = ax + S(ART) + S(GAP)
        self.right = self.w - S(PAD)
        self.title_max = self.right - self.tx - S(32)    # 오른쪽 위 ⬇ · ✕ 자리 비워둠
        self.artist_max = self.right - self.tx

        self._art_xy = (ax, ay)
        self.art_item = cv.create_image(ax, ay, anchor="nw")
        self.note_item = cv.create_text(ax + S(ART) // 2, ay + S(ART) // 2, text="♪",
                                        font=("Segoe UI Symbol", 20), fill=self.dim)
        self.title_item = cv.create_text(self.tx, ay - S(1), anchor="nw", font=self.f_title, fill=FG)
        self.artist_item = cv.create_text(self.tx, ay + S(23), anchor="nw", font=self.f_artist, fill=self.sub)

        bar_y = ay + S(ART) - S(BAR_H) - S(2)
        self.bar_y = bar_y
        self.left_time = cv.create_text(self.tx, bar_y - S(5), anchor="sw", font=self.f_time, fill=self.dim)
        self.right_time = cv.create_text(self.right, bar_y - S(5), anchor="se", font=self.f_time, fill=self.dim)
        # 진행바 = 회색 트랙 위에, 들은 길이만큼 그라데이션 이미지를 얹음
        self.bar_bg = cv.create_rectangle(self.tx, bar_y, self.right, bar_y + S(BAR_H), fill=self.track_col, width=0)
        self.bar_img = cv.create_image(self.tx, bar_y, anchor="nw")
        self._palette = None
        self._bar_key = None
        self._refresh_palette()

        # 마우스를 올렸을 때만 보이는 버튼: 왼쪽 위 ⚙ 설정, 오른쪽 위 ✕ 종료
        families = set(tkfont.families(root))
        icon_font = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
        if icon_font:
            gear, gear_font, close, close_font = "", (icon_font, 8), "", (icon_font, 7)
        else:
            gear, gear_font, close, close_font = "⚙", ("Segoe UI Symbol", 9), "✕", ("Segoe UI", 8)
        self._buttons = {}
        self._add_button("settings", S(11), S(11), gear, gear_font, self.open_settings)
        self._add_button("close", self.w - S(11), S(11), close, close_font, self.quit)
        # ✕ 왼쪽 ⬇ 업데이트: 평소엔 마우스를 올렸을 때만, 새 버전이 있으면 강조색으로 늘 보임
        dl, dl_font = ("", (icon_font, 8)) if icon_font else ("⬇", ("Segoe UI Symbol", 9))
        self._add_button("update", self.w - S(31), S(11), dl, dl_font, self._update_clicked)
        self._hovering = False

        cv.bind("<Enter>", lambda e: self._show_buttons(True))
        cv.bind("<Leave>", lambda e: self._show_buttons(False))
        cv.bind("<Motion>", self._hover)
        cv.bind("<ButtonPress-1>", self._press)
        cv.bind("<B1-Motion>", self._motion)
        cv.bind("<ButtonRelease-1>", self._release)

        self._set_art(None)
        self._show_empty()

        root.update_idletasks()
        self.hwnd = self._find_hwnd()
        self._host = None                 # 바탕화면에 붙어 있으면 그 바탕화면 창
        self.user_quit = False
        self.lost_window = False
        self.autohide = taskbar_autohide()
        self._apply_window_style()
        self._apply_alpha(self.settings["alpha"])

        if demo:
            root.attributes("-topmost", True)   # 미리보기는 잘 보이게 맨 위에
        else:
            if self.settings["desktop_mode"]:
                self._attach_desktop()
            root.after(300, self._keep_place)
        self._tb = None
        self._tb_checked = 0.0
        self._last_tb_top = None
        self.vel_y = 0.0
        self._last_frame = time.perf_counter()
        self._frame_ms = refresh_interval_ms()
        self._hires = False
        self._busy_until = 0.0
        self._mon = monitor_rect_at(self.base_x + self.w // 2, self.base_y + self.h // 2)
        self._follow_error_logged = False
        root.after(FOLLOW_IDLE_MS, self._follow)
        root.after(100, self._drain)
        root.after(TICK_MS, self._tick)
        root.after(ACCENT_POLL_MS, self._poll_accent)
        if not demo:
            root.after(15000, self._auto_check)   # 켜지고 15초 뒤 첫 업데이트 확인

    def S(self, v):
        return int(round(v * self.k))

    # ---- 창 설정 ----
    def _find_hwnd(self):
        try:
            return int(self.root.wm_frame(), 16)
        except Exception:
            return user32.GetParent(self.root.winfo_id())

    def _dwm_set(self, attr, value):
        try:
            v = ctypes.c_uint(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass

    def _apply_window_style(self):
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        self._dwm_set(33, 2)            # Windows 11 둥근 모서리 (DWMWCP_ROUND)
        self._dwm_set(34, 0xFFFFFFFF)   # 테두리 색: 기본값

    def _apply_alpha(self, value):
        """불투명도. 바탕화면에 붙어 있을 때 100% 라도 레이어드 창으로 유지해야 아이콘 층에 덮이지 않음."""
        self.root.attributes("-alpha", value)
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        if not ex & WS_EX_LAYERED:
            user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, int(round(value * 255)), LWA_ALPHA)

    def _keep_place(self):
        """
        보통 모드: 다른 창들 뒤(바탕화면 바로 위)에 머물게 합니다.
        바탕화면 모드: 아이콘 층 위에 있는지, 바탕화면 창이 바뀌지 않았는지 확인합니다.
        """
        if not user32.IsWindow(self.hwnd):
            # 탐색기가 재시작되면서 바탕화면 창과 함께 위젯 창도 사라진 경우 → 프로그램을 다시 띄움 (main 참고)
            logging.warning("위젯 창이 사라짐 (탐색기 재시작?) → 다시 실행")
            self.lost_window = True
            self.root.quit()
            return
        try:
            if self.settings["desktop_mode"]:
                host = find_desktop_host()
                if host and host != self._host:
                    self._attach_desktop(host)
                elif self._host and self._drag is None:
                    user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0,
                                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            elif self._drag is None:
                user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            logging.exception("위치 유지 실패")
        self.root.after(500, self._keep_place)

    # ---- 바탕화면에 붙이기 ----
    def screen_pos(self):
        r = window_rect(self.hwnd)
        return (r[0], r[1]) if r else (self.base_x, self.shown_y)

    def _move_to(self, x, y):
        """화면 좌표로 옮기기. 바탕화면에 붙어 있으면 바탕화면 창 기준 좌표로 바꿔서 옮김."""
        if self._host:
            p = wintypes.POINT(int(x), int(y))
            user32.ScreenToClient(self._host, ctypes.byref(p))
            user32.SetWindowPos(self.hwnd, None, p.x, p.y, 0, 0,
                                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        else:
            self.root.geometry(f"+{int(x)}+{int(y)}")

    def _attach_desktop(self, host=None):
        host = host or find_desktop_host()
        if not host:
            return False   # 탐색기가 아직 준비 안 됨 → _keep_place 가 나중에 다시 시도
        x, y = self.screen_pos()
        # Windows 11 이 창 둘레에 그리는 얇은 테두리가 붙인 뒤에도 남아서 다른 창 위에 보이는 문제 →
        # 붙이기 전에 테두리와 둥근 모서리를 끔 (모서리는 아래에서 직접 둥글게 자름)
        self._dwm_set(34, 0xFFFFFFFE)   # 테두리 색: 없음 (DWMWA_COLOR_NONE)
        self._dwm_set(33, 1)            # 둥근 모서리 끔 (DWMWCP_DONOTROUND)
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_STYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
        user32.SetParent(self.hwnd, host)
        self._host = host
        self._move_to(x, y)
        user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        # 자식 창에는 Windows 11 둥근 모서리가 안 먹어서 직접 둥글게 자름
        d = self.S(16)
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, self.w + 1, self.h + 1, d, d)
        user32.SetWindowRgn(self.hwnd, rgn, True)
        self._apply_alpha(self.settings["alpha"])
        return True

    def _detach_desktop(self):
        if not self._host:
            return
        x, y = self.screen_pos()
        user32.SetParent(self.hwnd, None)
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_STYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_STYLE, (style & ~WS_CHILD) | WS_POPUP)
        self._host = None
        user32.SetWindowRgn(self.hwnd, None, True)
        self._apply_window_style()
        self._move_to(x, y)
        self._apply_alpha(self.settings["alpha"])
        user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _initial_position(self):
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if isinstance(x, int) and isinstance(y, int) and point_on_screen(x + self.w // 2, y + self.h // 2):
            return x, y
        return self._default_position()

    def _default_position(self):
        _, _, right, bottom = work_area()
        return right - self.w - self.S(MARGIN), bottom - self.h - self.S(MARGIN)

    # ---- 설정 ----
    def set_setting(self, key, value):
        """설정을 바로 적용하고 (잠시 뒤) 파일에 저장합니다."""
        self.settings[key] = value
        self.cfg[key] = value
        if key in ("use_accent", "accent_card"):
            self._refresh_palette()
        elif key == "alpha":
            self._apply_alpha(value)
        elif key == "desktop_mode" and not self.demo:
            if value:
                self._attach_desktop()
            else:
                self._detach_desktop()
        # 트레이 메뉴 체크 표시 · 열려 있는 설정 창 스위치도 맞춰 줌
        if self.tray:
            self.tray.refresh()
        sw = self._settings_win
        if sw and sw.alive() and key in sw.controls and sw.controls[key].value != value:
            sw.controls[key].set(value)
        self._save_soon()

    def run_command(self, cmd):
        """트레이 메뉴 · 업데이트 스레드에서 온 명령."""
        cmd, arg = cmd if isinstance(cmd, tuple) else (cmd, None)
        up = self.updater
        if cmd == "settings":
            self.open_settings()
        elif cmd == "toggle_desktop":
            self.set_setting("desktop_mode", not self.settings["desktop_mode"])
        elif cmd == "reset_position":
            self.reset_position()
        elif cmd == "quit":
            self.quit()
        elif cmd == "check_update":
            self._update_clicked()
        elif cmd == "update_checked":
            up.on_checked(*arg)
        elif cmd == "update_start":
            up.start_download()
        elif cmd == "update_progress":
            up.progress = arg
            self._render_progress()
        elif cmd == "update_ready":
            up.install(arg)
        elif cmd == "update_failed":
            up.state, up.message = "available", "업데이트를 받지 못했어요"
            self.notify(f"{up.message}: {arg}")
            self.update_ui_changed()

    # ---- 업데이트 ----
    def _update_clicked(self):
        """⬇ 버튼 · 트레이 '업데이트': 새 버전이 있으면 설치할지 묻고, 아니면 지금 확인."""
        up = self.updater
        if not up.enabled:
            self.notify("업데이트를 받아 올 GitHub 저장소가 아직 정해지지 않았어요")
        elif up.state == "available":
            up.ask_and_update()
        elif up.state != "downloading":
            up.check(manual=True)

    def _auto_check(self):
        """시작하고 잠시 뒤, 그 뒤로는 몇 시간마다 새 버전 확인."""
        if self.settings["auto_update"] and self.updater.state not in ("available", "downloading"):
            self.updater.check()
        self.root.after(UPDATE_CHECK_HOURS * 3600 * 1000, self._auto_check)

    def notify(self, text):
        """트레이 알림 (Windows 알림 센터에 뜸)."""
        if self.tray:
            self.tray.notify(text)

    def update_ui_changed(self):
        """업데이트 상태가 바뀌면 ⬇ 버튼 · 트레이 메뉴 · 설정 창을 맞춰 줌."""
        self._show_buttons(self._hovering)
        self._render_progress()
        if self.tray:
            self.tray.refresh()
        sw = self._settings_win
        if sw and sw.alive():
            sw.refresh_update()

    def reset_position(self):
        self.base_x, self.base_y = self._default_position()
        self.cfg.pop("x", None)
        self.cfg.pop("y", None)
        self.cur_y, self.vel_y, self.shown_y = float(self.base_y), 0.0, self.base_y
        self._tb_checked = 0.0
        self._move_to(self.base_x, self.base_y)
        self._save_soon()

    def _save_soon(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self.save_now)

    def save_now(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        save_config(self.cfg)

    def open_settings(self):
        if self._settings_win and self._settings_win.alive():
            self._settings_win.bring_to_front()
        else:
            self._settings_win = SettingsWindow(self)

    def quit(self):
        self.user_quit = True
        if self._save_job:
            self.save_now()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    # ---- 작업표시줄 따라가기 ----
    def _follow(self):
        busy = False
        try:
            if self._drag is None:
                busy = self._follow_step()
        except Exception:
            if not self._follow_error_logged:
                logging.exception("작업표시줄 따라가기 실패")
                self._follow_error_logged = True
        # 움직이는 동안만 타이머를 정밀하게 + 주사율에 맞춰 촘촘히, 가만히 있을 땐 느긋하게 (CPU 절약)
        if busy != self._hires:
            try:
                (winmm.timeBeginPeriod if busy else winmm.timeEndPeriod)(1)
            except Exception:
                pass
            self._hires = busy
        self.root.after(self._frame_ms if busy else FOLLOW_IDLE_MS, self._follow)

    def _follow_step(self):
        now = time.perf_counter()
        dt = min(now - self._last_frame, 0.02)   # 쉬다가 막 움직이기 시작할 때 한 번에 튀지 않게
        self._last_frame = now
        if now - self._tb_checked > 1.0:   # 탐색기가 재시작되면 작업표시줄 창이 바뀌므로 가끔 다시 찾음
            self._tb_checked = now
            self._mon = monitor_rect_at(self.base_x + self.w // 2, self.base_y + self.h // 2)
            self._tb = find_bottom_taskbar(self._mon)
            self.autohide = taskbar_autohide()
        # 작업표시줄이 자동으로 숨는 경우에만 따라 움직임 (늘 보이는 작업표시줄과는 겹칠 일이 없음)
        following = self.settings["follow_taskbar"] and self.autohide
        r = window_rect(self._tb) if following else None
        tb_top = r[1] if r else None
        tb_moved = tb_top != self._last_tb_top
        self._last_tb_top = tb_top
        target = follow_target(self.base_y, self.h, self._mon[3], tb_top, self.S(MARGIN))

        self.cur_y, self.vel_y = smooth_damp(self.cur_y, target, self.vel_y, self.settings["smooth_time"], dt)
        if abs(self.cur_y - target) < 0.3 and abs(self.vel_y) < 5:
            self.cur_y, self.vel_y = float(target), 0.0
        y = int(round(self.cur_y))
        if y != self.shown_y:
            self._move_to(self.base_x, y)
            self.shown_y = y
        # 작업표시줄은 30ms 간격으로 띄엄띄엄 움직이므로, 움직임이 멈춘 뒤 잠깐은 계속 촘촘히 확인
        if tb_moved or self.cur_y != target:
            self._busy_until = now + 0.3
        return now < self._busy_until

    # ---- 강조색 ----
    def _bar_colors(self):
        if self.settings["use_accent"] and self._palette:
            return [self._palette[i] for i in ACCENT_STOPS]
        return [hex_rgb(FILL)]

    def _uses_accent(self):
        return self.settings["use_accent"] or self.settings["accent_card"]

    def _refresh_palette(self):
        if self._uses_accent():
            self._palette = read_accent_palette()
        if self.tray:
            self.tray.set_accent()
        self._build_card_background()
        self._colors_play = self._bar_colors()
        self._colors_pause = [_mix(c, hex_rgb(self.dim), 0.7) for c in self._colors_play]   # 일시정지 때
        self._bar_key = None   # 다음 그리기 때 새로 만들도록
        self._render_progress()

    def _build_card_background(self):
        """위젯 배경 강조색 그라데이션 (끄면 기본 단색 배경)."""
        pal = self._palette
        if self.settings["accent_card"] and pal:
            self._card_bg = card_background(self.w, self.h, pal)
            self._card_photo = ImageTk.PhotoImage(self._card_bg)
            self.cv.itemconfigure(self.bg_item, image=self._card_photo, state="normal")
            # 보라빛 배경 위에서도 잘 읽히도록 보조 글자를 더 밝게, 강조색 기운을 살짝 섞어서
            self.sub = rgb_hex(_mix(hex_rgb("#d0d0da"), pal[0], 0.3))
            self.dim = rgb_hex(_mix(hex_rgb("#a4a4b4"), pal[1], 0.3))
            self.track_col = rgb_hex(_mix(hex_rgb(BG), pal[6], 0.45))
        else:
            self._card_bg = None
            self.cv.itemconfigure(self.bg_item, state="hidden")
            self.sub, self.dim, self.track_col = SUB, DIM, TRACK
        # 이미 그려진 것들 색 다시 칠하기
        self.cv.itemconfigure(self.bar_bg, fill=self.track_col)
        self.cv.itemconfigure(self.note_item, fill=self.dim)
        self._set_art(self._art_data)   # 앨범아트 둥근 모서리를 새 배경 위에 다시 합성
        if self.track is not None:
            self.apply(self.track)
        else:
            self._set_text(self.cv.itemcget(self.title_item, "text"),
                           self.cv.itemcget(self.artist_item, "text"), self.sub, self.dim)

    def _draw_bar(self, fill_px, paused):
        """들은 길이(fill_px)만큼 그라데이션을 그립니다. 길이·상태가 바뀔 때만 이미지를 새로 만듦."""
        key = (fill_px, paused)
        if key == self._bar_key:
            return
        self._bar_key = key
        if fill_px <= 0:
            self.cv.itemconfigure(self.bar_img, state="hidden")
            return
        colors = self._colors_pause if paused else self._colors_play
        self._bar_photo = ImageTk.PhotoImage(gradient_image(fill_px, self.S(BAR_H), colors))
        self.cv.itemconfigure(self.bar_img, image=self._bar_photo, state="normal")

    def _poll_accent(self):
        self.root.after(ACCENT_POLL_MS, self._poll_accent)
        if self._uses_accent() and read_accent_palette() != self._palette:
            self._refresh_palette()

    # ---- 마우스 ----
    def _add_button(self, name, cx, cy, glyph, font, action):
        r = self.S(10)   # 누를 수 있는 범위 (아이콘보다 넉넉하게)
        item = self.cv.create_text(cx, cy, text=glyph, font=font, fill=self.dim, state="hidden")
        self._buttons[name] = ((cx - r, cy - r, cx + r, cy + r), item, action)

    def _update_color(self):
        """새 버전이 있으면 ⬇ 를 강조색으로."""
        if self.updater.state in ("available", "downloading") and self._palette:
            return rgb_hex(self._palette[1])
        return None

    def _show_buttons(self, on):
        self._hovering = on
        for name, (_, item, _) in self._buttons.items():
            special = self._update_color() if name == "update" else None
            visible = on or special is not None
            self.cv.itemconfigure(item, state="normal" if visible else "hidden", fill=special or self.dim)

    def _hit(self, e):
        for name, ((x0, y0, x1, y1), _, _) in self._buttons.items():
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return name
        return None

    def _hover(self, e):
        hit = self._hit(e)
        for name, (_, item, _) in self._buttons.items():
            special = self._update_color() if name == "update" else None
            self.cv.itemconfigure(item, fill=FG if name == hit else (special or self.dim))

    def _press(self, e):
        self._pressed_btn = self._hit(e)
        if self._pressed_btn:
            return
        # 좌표는 늘 실제 화면 기준 (바탕화면에 붙어 있을 때도 맞도록)
        cx, cy = cursor_pos()
        wx, wy = self.screen_pos()
        self._drag = (cx - wx, cy - wy)
        self._moved = False

    def _motion(self, e):
        if self._drag is None:
            return
        cx, cy = cursor_pos()
        self._move_to(cx - self._drag[0], cy - self._drag[1])
        self._moved = True

    def _release(self, e):
        if self._pressed_btn:
            name, self._pressed_btn = self._pressed_btn, None
            if self._hit(e) == name:          # 누른 버튼 위에서 뗐을 때만 실행
                self.root.after_idle(self._buttons[name][2])
            return
        if self._drag is not None and self._moved:
            self.base_x, self.base_y = self.screen_pos()
            self.cur_y = float(self.base_y)
            self.vel_y = 0.0
            self.shown_y = self.base_y
            self._tb_checked = 0.0          # 다른 모니터로 옮겼을 수도 있으니 다시 찾기
            self.cfg.update(x=self.base_x, y=self.base_y)
            self.save_now()
        self._drag = None

    # ---- 내용 ----
    def _set_art(self, data):
        self._art_data = data
        size = self.S(ART)
        img = None
        if data:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img = ImageOps.fit(trim_letterbox(img), (size, size), Image.LANCZOS)
            except Exception:
                img = None
        has_art = img is not None
        if not has_art:
            empty = ART_EMPTY if self._card_bg is None else rgb_hex(_mix(hex_rgb(BG), self._palette[6], 0.55))
            img = Image.new("RGB", (size, size), empty)
        bg = BG
        if self._card_bg is not None:   # 강조색 배경이면 앨범아트 자리의 배경을 잘라서 그 위에 합성
            ax, ay = self._art_xy
            bg = self._card_bg.crop((ax, ay, ax + size, ay + size))
        self._art_photo = ImageTk.PhotoImage(rounded(img, self.S(ART_RADIUS), bg))
        self.cv.itemconfigure(self.art_item, image=self._art_photo)
        self.cv.itemconfigure(self.note_item, state="hidden" if has_art else "normal")

    def _set_text(self, title, artist, title_color=FG, artist_color=SUB):
        self.cv.itemconfigure(self.title_item, text=fit_text(self.f_title, title, self.title_max), fill=title_color)
        self.cv.itemconfigure(self.artist_item, text=fit_text(self.f_artist, artist, self.artist_max), fill=artist_color)

    def _show_empty(self, message="재생 중인 곡 없음", sub="음악을 틀면 여기에 표시돼요"):
        self.track = None
        self._set_art(None)
        self._set_text(message, sub, self.sub, self.dim)
        self._render_progress()

    def apply(self, t: Optional[Track]):
        if t is None:
            if self.track is not None:
                self._show_empty()
                if self.tray:
                    self.tray.set_tooltip(APP_NAME)
            return
        if self.track is None or t.key != self.track.key:
            self._set_art(t.thumb)
            if self.tray:   # 트레이 아이콘에 마우스를 올리면 지금 곡이 보이게
                self.tray.set_tooltip(f"{APP_NAME}\n{t.title} — {t.artist}" if t.artist else f"{APP_NAME}\n{t.title}")
        elif t.thumb:
            self._set_art(t.thumb)
        paused = t.status != PLAYING
        self._set_text(t.title or "제목 없음", t.artist or "알 수 없는 아티스트",
                       self.sub if paused else FG, self.dim if paused else self.sub)
        self.track = t
        self._render_progress()

    def _render_progress(self):
        cv, t = self.cv, self.track
        bar = (self.bar_bg, self.bar_img)
        if self.updater.state == "downloading":
            # 업데이트를 받는 동안은 진행바를 다운로드 진행률로 씀
            for i in (*bar, self.left_time, self.right_time):
                cv.itemconfigure(i, state="normal")
            pct = self.updater.progress
            cv.itemconfigure(self.left_time, text=f"업데이트 받는 중 {round(pct * 100)}%", fill=self.sub)
            cv.itemconfigure(self.right_time, text=f"v{self.updater.latest['version']}", fill=self.sub)
            self._draw_bar(int(round((self.right - self.tx) * pct)), False)
            return
        self._bar_key = None if (t is None or t.duration <= 0) else self._bar_key
        if t is None or t.duration == 0:
            for i in (*bar, self.left_time, self.right_time):
                cv.itemconfigure(i, state="hidden")
            if t is not None and t.status != PLAYING:
                cv.itemconfigure(self.left_time, state="normal", text="일시정지", fill=self.dim)
            return
        paused = t.status != PLAYING
        if t.duration < 0:   # 라이브 방송
            for i in bar + (self.right_time,):
                cv.itemconfigure(i, state="hidden")
            cv.itemconfigure(self.left_time, state="normal",
                             text="일시정지" if paused else "● LIVE", fill=self.dim if paused else LIVE)
            return

        pos = t.position
        if not paused:
            pos += (time.time() - t.updated) * t.rate
        pos = min(max(pos, 0), t.duration)
        fill_px = int(round((self.right - self.tx) * (pos / t.duration)))
        for i in (self.bar_bg, self.left_time, self.right_time):
            cv.itemconfigure(i, state="normal")
        self._draw_bar(fill_px, paused)
        cv.itemconfigure(self.left_time, text=("일시정지 · " if paused else "") + fmt_time(pos), fill=self.dim)
        cv.itemconfigure(self.right_time, text=fmt_time(t.duration), fill=self.dim)

    # ---- 루프 ----
    def _drain(self):
        if self.quit_event and kernel32.WaitForSingleObject(self.quit_event, 0) == 0:
            self.quit()   # 제거 프로그램이 종료를 요청함
            return
        latest = None
        try:
            while True:
                latest = self.source.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            kind, value = latest
            if kind == "error":
                self._show_empty("곡 정보를 읽을 수 없어요", value)
            else:
                self.apply(value)
        try:   # 트레이 메뉴 명령
            while not self.user_quit:
                self.run_command(self.commands.get_nowait())
        except queue.Empty:
            pass
        if self.user_quit:
            return   # '종료' 로 창이 닫힘
        self.root.after(200, self._drain)

    def _tick(self):
        self._render_progress()
        self.root.after(TICK_MS, self._tick)


# ----------------------------------------------------------------- 설정 창 ----
def rgb_hex(c):
    return "#%02x%02x%02x" % tuple(c)


def app_icon(accent):
    """설정 창 아이콘: 강조색 둥근 사각형 + 이퀄라이저 막대."""
    n = 64
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, n - 3, n - 3], radius=14, fill=hex_rgb(accent))
    for i, hgt in enumerate((22, 36, 28)):
        x = 17 + i * 12
        d.rounded_rectangle([x, 50 - hgt, x + 7, 50], radius=3, fill=(255, 255, 255))
    return img


class Toggle(tk.Canvas):
    """켜기/끄기 스위치."""

    def __init__(self, master, value, on_change, accent, S):
        self.W, self.H = S(40), S(20)
        super().__init__(master, width=self.W, height=self.H, bg=PANEL,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.on_change, self.accent = value, on_change, accent
        self.enabled = True
        self.item = self.create_image(0, 0, anchor="nw")
        self.bind("<Button-1>", self._click)
        self.render()

    def _click(self, e):
        if not self.enabled:
            return
        self.set(not self.value)
        self.on_change(self.value)

    def set(self, value):
        self.value = value
        self.render()

    def set_enabled(self, on):
        if on != self.enabled:
            self.enabled = on
            self.configure(cursor="hand2" if on else "arrow")
            self.render()

    def render(self):
        k = 4   # 4배로 그려서 줄이면 가장자리가 매끄러움
        W, H = self.W * k, self.H * k
        track = hex_rgb(self.accent if self.value else CONTROL_OFF)
        knob = (255, 255, 255) if self.value else hex_rgb(SUB)
        if not self.enabled:   # 못 쓰는 상태는 흐리게
            track, knob = _mix(track, hex_rgb(PANEL), 0.65), _mix(knob, hex_rgb(PANEL), 0.65)
        img = Image.new("RGB", (W, H), hex_rgb(PANEL))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, fill=track)
        r = int(H * 0.3)
        cx = W - H // 2 if self.value else H // 2
        d.ellipse([cx - r, H // 2 - r, cx + r, H // 2 + r], fill=knob)
        self._photo = ImageTk.PhotoImage(img.resize((self.W, self.H), Image.LANCZOS))
        self.itemconfigure(self.item, image=self._photo)


class Slider(tk.Canvas):
    """끌어서 값을 바꾸는 슬라이더."""

    def __init__(self, master, value, lo, hi, on_change, accent, S, width=150, step=0.01):
        self.W, self.H = S(width), S(20)
        super().__init__(master, width=self.W, height=self.H, bg=PANEL,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.lo, self.hi, self.step = value, lo, hi, step
        self.on_change, self.accent = on_change, accent
        self.enabled = True
        self.item = self.create_image(0, 0, anchor="nw")
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.render()

    def _drag(self, e):
        if not self.enabled:
            return
        pad = self.H // 2
        t = min(max((e.x - pad) / max(self.W - 2 * pad, 1), 0.0), 1.0)
        v = round(round((self.lo + t * (self.hi - self.lo)) / self.step) * self.step, 4)
        if v != self.value:
            self.set(v)
            self.on_change(v)

    def set(self, value):
        self.value = value
        self.render()

    def set_enabled(self, on):
        if on != self.enabled:
            self.enabled = on
            self.configure(cursor="hand2" if on else "arrow")
            self.render()

    def render(self):
        k = 4
        W, H = self.W * k, self.H * k
        pad, cy, th = H // 2, H // 2, 2 * k
        accent, off, ring = hex_rgb(self.accent), hex_rgb(CONTROL_OFF), hex_rgb("#45454f")
        if not self.enabled:
            accent, off, ring = (_mix(c, hex_rgb(PANEL), 0.65) for c in (accent, off, ring))
        img = Image.new("RGB", (W, H), hex_rgb(PANEL))
        d = ImageDraw.Draw(img)
        t = (self.value - self.lo) / (self.hi - self.lo)
        cx = int(pad + t * (W - 2 * pad))
        d.rounded_rectangle([pad, cy - th, W - pad, cy + th], radius=th, fill=off)
        if cx > pad + 2 * th:
            d.rounded_rectangle([pad, cy - th, cx, cy + th], radius=th, fill=accent)
        r_out, r_in = int(H * 0.36), int(H * 0.2)
        d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=ring)
        d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=accent)
        self._photo = ImageTk.PhotoImage(img.resize((self.W, self.H), Image.LANCZOS))
        self.itemconfigure(self.item, image=self._photo)


def flat_button(parent, text, command, S):
    b = tk.Label(parent, text=text, font=(FONT, 9), bg=BUTTON, fg=FG,
                 padx=S(12), pady=S(5), cursor="hand2")
    b.bind("<Enter>", lambda e: b.configure(bg=BUTTON_HOVER))
    b.bind("<Leave>", lambda e: b.configure(bg=BUTTON))
    b.bind("<ButtonRelease-1>", lambda e: command())
    return b


class SettingsWindow:
    """⚙ 를 누르면 뜨는 설정 창. 바꾸는 즉시 위젯에 적용되고 저장됩니다."""

    def __init__(self, widget: "Widget"):
        self.wd = widget
        S = widget.S
        pal = read_accent_palette()
        self.accent = rgb_hex(pal[2]) if pal else "#7a8cff"

        top = self.top = tk.Toplevel(widget.root)
        top.withdraw()
        top.title("Now Playing 설정")
        top.configure(bg=PANEL)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda e: self.close())
        self._icon = ImageTk.PhotoImage(app_icon(self.accent))
        top.iconphoto(False, self._icon)

        # 창 너비를 위젯과 똑같이 맞춰서 위젯 위/아래에 딱 맞게 붙도록 (그래서 조금 촘촘한 배치)
        self.wrap = widget.w - S(40)
        body = tk.Frame(top, bg=PANEL, padx=S(18), pady=S(16))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        tk.Label(body, text="위젯 설정", font=(FONT, 13, "bold"), bg=PANEL, fg=FG).grid(
            row=0, column=0, columnspan=3, sticky="w")
        tk.Label(body, text="바꾸면 바로 적용되고 자동으로 저장돼요", font=(FONT, 8), bg=PANEL, fg=DIM).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(S(2), 0))

        self.controls, self.labels, self.values, self.hints = {}, {}, {}, {}
        self.row = 2
        self._section(body, "모양")
        self._toggle_row(body, "진행바에 Windows 강조색 쓰기", "use_accent")
        self._toggle_row(body, "위젯 배경에 Windows 강조색 쓰기", "accent_card")
        self._slider_row(body, "불투명도", "alpha", lambda v: f"{round(v * 100)}%")

        self._section(body, "바탕화면")
        self._toggle_row(body, "바탕화면에 붙이기", "desktop_mode",
                         hint="배경화면에 붙어서 Win+D 를 눌러도 사라지지 않아요")

        self._section(body, "작업표시줄")
        # 작업표시줄 자동 숨기기가 꺼져 있을 때만 보이는 안내
        self.notice = tk.Frame(body, bg=PANEL)
        tk.Label(self.notice, text="자동 숨기기가 켜져 있을 때만 쓸 수 있어요",
                 font=(FONT, 8), bg=PANEL, fg=SUB).pack(side="left")
        link = tk.Label(self.notice, text="설정 열기", font=(FONT, 8, "underline"),
                        bg=PANEL, fg=self.accent, cursor="hand2")
        link.pack(side="left", padx=(S(6), 0))
        link.bind("<ButtonRelease-1>", lambda e: self._open_taskbar_settings())
        self.notice.grid(row=self.row, column=0, columnspan=3, sticky="w", pady=(0, S(2)))
        self.row += 1
        self._toggle_row(body, "작업표시줄 따라 움직이기", "follow_taskbar")
        self._slider_row(body, "따라가는 부드러움", "smooth_time", lambda v: f"{v:.2f}초",
                         hint="왼쪽일수록 바짝, 오른쪽일수록 느긋하게")

        self._section(body, "업데이트")
        self._toggle_row(body, "새 버전 자동으로 확인", "auto_update")
        up_row = tk.Frame(body, bg=PANEL)
        up_row.grid(row=self.row, column=0, columnspan=3, sticky="we", pady=(S(4), 0))
        self.row += 1
        self.update_label = tk.Label(up_row, text="", font=(FONT, 9), bg=PANEL, fg=SUB, anchor="w")
        self.update_label.pack(side="left")
        self.update_button = flat_button(up_row, "", widget._update_clicked, S)
        self.update_button.pack(side="right")
        self.refresh_update()

        bar = tk.Frame(body, bg=PANEL)
        bar.grid(row=self.row, column=0, columnspan=3, sticky="we", pady=(S(20), 0))
        flat_button(bar, "위치 초기화", widget.reset_position, S).pack(side="left")
        flat_button(bar, "기본값으로", self.reset_defaults, S).pack(side="left", padx=(S(6), 0))
        flat_button(bar, "닫기", self.close, S).pack(side="right")

        self._notice_shown = None
        self._sync_enabled()

        # 보이지 않게 띄워서 실제 크기를 잰 다음, 위젯 가운데에 맞춰 놓고 보여줌
        top.attributes("-alpha", 0.0)
        top.deiconify()
        top.update()
        self._style_titlebar()
        self._place()
        top.attributes("-alpha", 1.0)
        self.bring_to_front()
        self._poll_job = top.after(1000, self._poll)

    # ---- 줄 만들기 ----
    def _section(self, body, text):
        tk.Label(body, text=text, font=(FONT, 9, "bold"), bg=PANEL, fg=SUB).grid(
            row=self.row, column=0, columnspan=3, sticky="w", pady=(self.wd.S(16), self.wd.S(4)))
        self.row += 1

    def _label(self, body, text, key, span=1):
        lbl = tk.Label(body, text=text, font=(FONT, 10), bg=PANEL, fg=FG)
        lbl.grid(row=self.row, column=0, columnspan=span, sticky="w", pady=self.wd.S(5))
        self.labels[key] = lbl

    def _hint(self, body, text, key):
        lbl = tk.Label(body, text=text, font=(FONT, 8), bg=PANEL, fg=DIM,
                       wraplength=self.wrap, justify="left")
        lbl.grid(row=self.row, column=0, columnspan=3, sticky="w")
        self.hints[key] = lbl
        self.row += 1

    def _toggle_row(self, body, text, key, hint=None):
        # 스위치 줄: 글자는 왼쪽 두 칸, 스위치는 맨 오른쪽 칸 (슬라이더 값 표시와 같은 칸)
        self._label(body, text, key, span=2)

        def changed(v):
            self.wd.set_setting(key, v)
            self._sync_enabled()

        t = Toggle(body, self.wd.settings[key], changed, self.accent, self.wd.S)
        t.grid(row=self.row, column=2, sticky="e", padx=(self.wd.S(8), 0))
        self.controls[key] = t
        self.row += 1
        if hint:
            self._hint(body, hint, key)

    def _slider_row(self, body, text, key, fmt, hint=None):
        S = self.wd.S
        self._label(body, text, key)
        value = tk.Label(body, text=fmt(self.wd.settings[key]), font=(FONT, 9), bg=PANEL, fg=SUB,
                         width=5, anchor="e")

        def changed(v):
            self.wd.set_setting(key, v)
            value.configure(text=fmt(v))

        lo, hi = SETTING_RANGES[key]
        s = Slider(body, self.wd.settings[key], lo, hi, changed, self.accent, S, width=112)
        s.grid(row=self.row, column=1, sticky="e", padx=(S(10), S(4)))
        value.grid(row=self.row, column=2, sticky="e")
        self.controls[key], self.values[key] = s, (value, fmt)
        self.row += 1
        if hint:
            self._hint(body, hint, key)

    # ---- 켜고 끌 수 있는지 ----
    def _set_row_enabled(self, key, on):
        self.controls[key].set_enabled(on)
        self.labels[key].configure(fg=FG if on else DIM)
        if key in self.values:
            self.values[key][0].configure(fg=SUB if on else DIM)

    def _sync_enabled(self):
        """작업표시줄 자동 숨기기가 켜져 있을 때만 '따라 움직이기' 를 쓸 수 있게."""
        auto = taskbar_autohide()
        self.wd.autohide = auto
        self._set_row_enabled("follow_taskbar", auto)
        self._set_row_enabled("smooth_time", auto and self.wd.settings["follow_taskbar"])
        want_notice = not auto
        if want_notice != self._notice_shown:
            first = self._notice_shown is None
            if want_notice:
                self.notice.grid()
            else:
                self.notice.grid_remove()
            self._notice_shown = want_notice
            if not first:      # 창 높이가 바뀌었으니 다시 가운데 맞춤
                self.top.update_idletasks()
                self._place()

    def _poll(self):
        if not self.alive():
            return
        self._sync_enabled()   # Windows 설정에서 자동 숨기기를 바꾸면 바로 반영
        self._poll_job = self.top.after(1000, self._poll)

    def _open_taskbar_settings(self):
        try:
            os.startfile("ms-settings:taskbar")
        except Exception:
            logging.exception("작업표시줄 설정 열기 실패")

    def refresh_update(self):
        """업데이트 칸: '버전 1.1.0 · 상태' + 버튼."""
        up = self.wd.updater
        status = {"checking": "확인 중…", "latest": "최신 버전이에요", "available": up.message,
                  "downloading": "받는 중…", "error": up.message}.get(up.state, "")
        if not up.enabled:
            status = "저장소가 정해지지 않았어요"
        self.update_label.configure(text=f"버전 {APP_VERSION}" + (f" · {status}" if status else ""),
                                    fg=self.accent if up.state == "available" else SUB)
        self.update_button.configure(text="지금 업데이트" if up.state == "available" else "업데이트 확인")

    # ---- 동작 ----
    def reset_defaults(self):
        for key, v in DEFAULT_SETTINGS.items():
            self.wd.set_setting(key, v)
            self.controls[key].set(v)
            if key in self.values:
                label, fmt = self.values[key]
                label.configure(text=fmt(v))
        self._sync_enabled()

    def _place(self):
        """위젯과 같은 너비로, 위젯 위(공간이 없으면 아래)에 양쪽 끝을 맞춰 띄웁니다."""
        S, top = self.wd.S, self.top
        frame = int(top.wm_frame(), 16)
        wl, wt, wr, wb = window_rect(self.wd.hwnd)
        left, top_y, right, bottom = monitor_rect_at((wl + wr) // 2, (wt + wb) // 2, work=True)
        # 보이는 창 너비 = 위젯 너비 (테두리 두께만큼 안쪽 너비를 줄임). 내용이 더 넓으면 내용에 맞춤
        vl, vt, vr, vb = visible_rect(frame)
        border = (vr - vl) - top.winfo_width()
        inner = max((wr - wl) - border, top.winfo_reqwidth())
        top.geometry(f"{inner}x{top.winfo_reqheight()}")
        top.update_idletasks()
        # Tk 가 아는 창 위치와 실제로 보이는 테두리 사이의 차이를 재서 보정
        gx, gy = (int(v) for v in top.wm_geometry().split("+")[1:3])
        vl, vt, vr, vb = visible_rect(frame)
        vw, vh = vr - vl, vb - vt
        gap = S(16)
        x = (wl + wr) // 2 - vw // 2
        y = wt - gap - vh
        if y < top_y + S(8):
            y = wb + gap
        x = min(max(x, left + S(8)), right - vw - S(8))
        y = min(max(y, top_y + S(8)), bottom - vh - S(8))
        top.geometry(f"+{x - (vl - gx)}+{y - (vt - gy)}")
        top.update_idletasks()

    def _style_titlebar(self):
        """제목 표시줄을 어둡게, 창 배경색과 같게."""
        try:
            hwnd = wintypes.HWND(int(self.top.wm_frame(), 16))
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            r, g, b = hex_rgb(PANEL)
            color = ctypes.c_int(r | (g << 8) | (b << 16))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
        except Exception:
            pass

    def bring_to_front(self):
        top = self.top
        top.deiconify()
        top.lift()
        top.attributes("-topmost", True)    # 잠깐 맨 위로 올렸다가
        top.focus_force()
        try:
            user32.SetForegroundWindow(wintypes.HWND(int(top.wm_frame(), 16)))
        except Exception:
            pass
        top.after(400, lambda: self.alive() and top.attributes("-topmost", False))   # 다시 보통 창으로

    def alive(self):
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        self.wd.save_now()
        self.top.destroy()
        self.wd._settings_win = None


# ---------------------------------------------------------------- 미리보기 ----
def demo_track(kind):
    img = Image.new("RGB", (300, 300))
    px = img.load()
    for yy in range(300):
        for xx in range(300):
            px[xx, yy] = (60 + xx * 160 // 300, 40 + yy * 60 // 300, 140 + (xx + yy) * 100 // 600)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    base = dict(key=("demo", kind), title="Midnight Drive", artist="The Placeholder Band",
                status=PLAYING, position=72, duration=215, updated=time.time(), rate=1.0,
                thumb=buf.getvalue())
    if kind == "empty":
        return None
    if kind == "paused":
        base["status"] = PAUSED
    if kind == "live":
        base.update(duration=-0.000001, title="새벽 라디오 라이브 스트리밍", artist="어느 채널")
    if kind == "long":
        base.update(title="아주아주 긴 노래 제목이 들어오면 이렇게 끝을 줄여서 보여줍니다 (Remastered 2026)",
                    artist="가수 이름도 길면 똑같이 줄여요 feat. 피처링 아티스트 여러 명")
    return Track(**base)


# -------------------------------------------------------------------- 시작 ----
def single_instance(wait_sec=0.0):
    """두 번 실행해도 하나만 뜨도록. 이미 떠 있으면 (wait_sec 동안 기다린 뒤) None."""
    deadline = time.monotonic() + wait_sec
    while True:
        ctypes.set_last_error(0)
        h = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            return h
        kernel32.CloseHandle(h)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def request_quit(timeout=8.0):
    """
    떠 있는 위젯에게 종료하라고 알리고 끝날 때까지 기다립니다. (NowPlaying.exe --quit)
    설치 파일이 프로그램을 지우거나 고치기 전에 불러서, '파일이 사용 중' 때문에 다시 시작해야 하는 일을 막음.
    """
    ev = kernel32.OpenEventW(0x0002, False, QUIT_EVENT_NAME)   # EVENT_MODIFY_STATE
    if not ev:
        return False   # 실행 중이 아님
    kernel32.SetEvent(ev)
    kernel32.CloseHandle(ev)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)   # SYNCHRONIZE
        if not m:
            return True   # 프로그램이 끝남
        kernel32.CloseHandle(m)
        time.sleep(0.2)
    return False


def relaunch():
    import subprocess
    if FROZEN:   # 설치된 exe
        subprocess.Popen([sys.executable, "--restart"], close_fds=True)
    else:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--restart"], close_fds=True)


class Tray:
    """
    작업표시줄 알림 영역(트레이) 아이콘. 클릭 = 설정, 우클릭 = 메뉴.
    트레이는 자기 스레드에서 돌아가므로 메뉴를 누르면 명령만 큐에 넣고, 위젯(Tk 스레드)이 꺼내서 실행합니다.
    """

    def __init__(self, widget: "Widget"):
        self.wd = widget
        self.icon = None
        try:
            import pystray
        except Exception:
            logging.warning("pystray 가 없어서 트레이 아이콘 없이 실행")
            return
        item = pystray.MenuItem

        def post(cmd):
            return lambda icon, it: widget.commands.put(cmd)

        menu = pystray.Menu(
            item("설정", post("settings"), default=True),
            item("바탕화면에 붙이기", post("toggle_desktop"),
                 checked=lambda it: widget.settings["desktop_mode"]),
            item("위치 초기화", post("reset_position")),
            item(lambda it: (f"업데이트 (새 버전 {widget.updater.latest['version']})"
                             if widget.updater.state == "available" else "업데이트 확인"),
                 post("check_update")),
            pystray.Menu.SEPARATOR,
            item("종료", post("quit")),
        )
        self.icon = pystray.Icon("NowPlayingWidget", self._image(), APP_NAME, menu)
        threading.Thread(target=self._run, daemon=True, name="tray").start()

    def _run(self):
        try:
            self.icon.run()
        except Exception:
            logging.exception("트레이 아이콘 오류")

    @staticmethod
    def _image():
        pal = read_accent_palette()
        return app_icon(rgb_hex(pal[2]) if pal else "#7a8cff")

    def refresh(self):
        """체크 표시는 메뉴를 다시 만들 때 반영되므로, 설정이 바뀔 때마다 호출."""
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def set_tooltip(self, text):
        if self.icon:
            try:
                self.icon.title = text[:120]   # 트레이 툴팁 길이 제한
            except Exception:
                pass

    def set_accent(self):
        if self.icon:
            try:
                self.icon.icon = self._image()
            except Exception:
                pass

    def notify(self, text):
        """Windows 알림 (트레이 풍선 → 알림 센터)."""
        if self.icon:
            try:
                self.icon.notify(text, APP_NAME)
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


def main():
    args = sys.argv[1:]
    if "--quit" in args:          # 떠 있는 위젯 끄기 (제거 프로그램이 사용)
        request_quit()
        return
    demo = "--demo" in args
    if not demo:
        # --restart: 앞 프로그램이 끝나기를 잠깐 기다림
        main.mutex = single_instance(wait_sec=15 if "--restart" in args else 0)
        if not main.mutex:
            return
        main.quit_event = kernel32.CreateEventW(None, True, False, QUIT_EVENT_NAME)

    set_app_id()
    set_dpi_awareness()
    root = tk.Tk()
    q = queue.Queue()
    w = Widget(root, q, demo=demo)
    w.quit_event = getattr(main, "quit_event", None) if not demo else None
    if demo:
        rest = [a for a in args if a not in ("--demo", "--restart")]
        q.put(("track", demo_track(rest[0] if rest else "playing")))
    else:
        w.tray = Tray(w)
        MediaWatcher(q).start()
    started = time.monotonic()
    root.mainloop()

    if w.tray:
        w.tray.stop()   # 안 지우면 마우스를 올릴 때까지 유령 아이콘이 남음
    # 탐색기 재시작 등으로 창을 잃었으면 다시 실행 (바로 또 잃는 경우엔 무한 반복하지 않도록 10초 조건)
    if w.lost_window and not w.user_quit:
        save_config(w.cfg)
        if time.monotonic() - started > 10:
            relaunch()
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 설치된 exe 는 콘솔이 없어서 그냥 꺼지면 이유를 알 수 없으므로 로그에 남김
        logging.exception("시작 실패")
        raise
