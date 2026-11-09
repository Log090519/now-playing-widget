# -*- coding: utf-8 -*-
"""
Now Playing 위젯 설치 파일(.msi) 만들기

    pip install -r requirements.txt
    python setup.py bdist_msi

결과물: dist\\NowPlaying-<버전>-win64.msi   (버전은 now_playing.pyw 의 APP_VERSION)
새 버전을 GitHub 에 올리는 건 release.py 가 이 과정까지 한 번에 해 줌
- 관리자 권한 없이 현재 사용자에게 설치 (%LOCALAPPDATA%\\Programs\\NowPlaying)
- 시작 메뉴 · 바탕화면 바로가기, 설치가 끝나면 바로 실행
- 같은 UPGRADE_CODE 로 버전만 올려서 다시 만들면, 새 msi 가 이전 버전을 자동으로 교체
"""
import os
import re
import tempfile

from cx_Freeze import Executable, setup
from PIL import Image, ImageDraw

NAME = "Now Playing"
HERE = os.path.dirname(os.path.abspath(__file__))
# 버전은 now_playing.pyw 의 APP_VERSION 한 곳에서만 관리 (위젯이 업데이트를 비교할 때도 이 값을 씀)
with open(os.path.join(HERE, "now_playing.pyw"), encoding="utf-8") as _f:
    VERSION = re.search(r'^APP_VERSION = "([\d.]+)"', _f.read(), re.M).group(1)
UPGRADE_CODE = "{44960FD7-CC3F-440D-AA02-741F687AC766}"   # 바꾸지 마세요 (업데이트할 때 같은 프로그램으로 알아보는 값)
# 중간 결과물은 짧은 경로에서 만듦 (프로젝트 폴더 경로가 길면 Windows 260자 경로 제한에 걸림)
WORK = os.path.join(tempfile.gettempdir(), "nowplaying_build")
ICON = os.path.join(WORK, "now_playing.ico")


def make_icon(path):
    """앱 아이콘: 보라색 둥근 사각형 + 이퀄라이저 막대 (위젯 트레이 아이콘과 같은 모양)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 256
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, n - 9, n - 9], radius=56, fill=(0x76, 0x6B, 0xC7))
    for i, hgt in enumerate((88, 144, 112)):
        x = 68 + i * 48
        d.rounded_rectangle([x, 200 - hgt, x + 28, 200], radius=12, fill=(255, 255, 255))
    img.save(path, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])


make_icon(ICON)

build_exe_options = {
    # 실행 중에 불러오는 모듈들 (자동으로 못 찾을 수 있어서 직접 적어 둠)
    "packages": [
        "winrt",
        "winrt.windows.media.control",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.storage.streams",
        "pystray",
        "PIL",
        "asyncio",
        "tkinter",
    ],
    "includes": ["pystray._win32"],
    "excludes": ["unittest", "test", "pydoc_data", "setuptools", "cx_Freeze"],
    "include_msvcr": True,
    "build_exe": os.path.join(WORK, "exe"),
}

# 바탕화면 바로가기 (시작 메뉴 바로가기는 아래 Executable 에서 만듦)
desktop_shortcut = [(
    "DesktopShortcut",            # Shortcut
    "DesktopFolder",              # Directory_
    NAME,                         # Name
    "TARGETDIR",                  # Component_
    "[TARGETDIR]NowPlaying.exe",  # Target
    None, "Now Playing desktop widget", None, None, None, None,
    "TARGETDIR",                  # WkDir
)]

msi_data = {
    "Shortcut": desktop_shortcut,
    # 제어판 '프로그램 제거' · 설정 '설치된 앱' 에 보이는 정보
    "Property": [
        ("ARPNOMODIFY", "1"),   # '변경' 버튼 숨김 (바꿀 옵션이 없음)
        ("ARPNOREPAIR", "1"),   # '복구' 버튼 숨김 → '제거' 만
        ("ARPCOMMENTS", "Shows the song that is playing now on your desktop"),
    ],
    # 제거(또는 다시 설치)할 때 위젯이 켜져 있으면 먼저 끔 → '파일 사용 중 / 다시 시작 필요' 를 막음
    # 18 = 설치된 파일(NowPlaying.exe)을 실행, +64 = 결과와 상관없이 계속 진행
    "CustomAction": [("A_CLOSE_APP", 18 + 64, "NowPlaying.exe", "--quit")],
    "InstallExecuteSequence": [("A_CLOSE_APP", "Installed", 1390)],   # InstallValidate(1400) 전에
}

bdist_msi_options = {
    "upgrade_code": UPGRADE_CODE,
    "product_name": NAME,
    "all_users": False,
    "initial_target_dir": r"[LocalAppDataFolder]Programs\NowPlaying",
    "install_icon": ICON,
    "add_to_path": False,
    "launch_on_finish": True,
    "bdist_dir": os.path.join(WORK, "msi"),
    "dist_dir": os.path.join(HERE, "dist"),
    "output_name": f"NowPlaying-{VERSION}-win64.msi",   # 공백 없는 이름 (GitHub 다운로드 주소용)
    # 바로가기를 놓을 Windows 폴더 (Directory 표에 있어야 바로가기가 만들어지고 제거 때 지워짐)
    "directories": [
        ("ProgramMenuFolder", "TARGETDIR", "."),
        ("DesktopFolder", "TARGETDIR", "."),
    ],
    "data": msi_data,
    "summary_data": {"author": NAME, "comments": "Shows the song that is playing now on your desktop"},
}

setup(
    name="NowPlaying",
    version=VERSION,
    description=NAME,
    author=NAME,   # 제어판 · 설정의 '게시자' (없으면 UNKNOWN 으로 나옴)
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
    executables=[Executable(
        "now_playing.pyw",
        base="gui",                      # 콘솔 창 없이
        target_name="NowPlaying.exe",
        icon=ICON,
        shortcut_name=NAME,
        shortcut_dir="ProgramMenuFolder",
    )],
)
