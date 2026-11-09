# -*- coding: utf-8 -*-
"""
Now Playing 위젯 설치 파일(.msi) 만들기

    pip install -r requirements.txt
    python setup.py bdist_msi

결과물: dist\\NowPlaying-<버전>-win64.msi   (버전은 now_playing.pyw 의 APP_VERSION)
새 버전을 GitHub 에 올리는 건 release.py 가 이 과정까지 한 번에 해 줌
- 관리자 권한 없이 현재 사용자에게 설치 (%LOCALAPPDATA%\\Programs\\NowPlaying)
- 첫 화면에서 언어(한국어 / English)를 고르면 나머지 설치 화면과 위젯이 그 언어로 나옴
- 설치 화면에서 '시작프로그램에 추가' 를 고를 수 있음
- 시작 메뉴 · 바탕화면 바로가기, 설치가 끝나면 바로 실행
- 같은 UPGRADE_CODE 로 버전만 올려서 다시 만들면, 새 msi 가 이전 버전을 자동으로 교체

자동 설치 (위젯의 업데이트 기능이 이렇게 부름):
    msiexec /i NowPlaying-x.y.z-win64.msi /passive UILANG=ko AUTOSTART=1
"""
import ctypes
import os
import re
import tempfile
from ctypes import wintypes

import msilib
from cx_Freeze import Executable, setup
from cx_Freeze.command.bdist_msi import bdist_msi
from msilib import Dialog, add_data
from PIL import Image, ImageDraw

NAME = "Now Playing"
HERE = os.path.dirname(os.path.abspath(__file__))
# 버전은 now_playing.pyw 의 APP_VERSION 한 곳에서만 관리 (위젯이 업데이트를 비교할 때도 이 값을 씀)
with open(os.path.join(HERE, "now_playing.pyw"), encoding="utf-8") as _f:
    VERSION = re.search(r'^APP_VERSION = "([\d.]+)"', _f.read(), re.M).group(1)
UPGRADE_CODE = "{44960FD7-CC3F-440D-AA02-741F687AC766}"   # 바꾸지 마세요 (업데이트할 때 같은 프로그램으로 알아보는 값)
# 레지스트리 항목을 담는 구성요소 ID. 버전이 바뀌어도 같아야 업데이트 때 값이 지워지지 않음 (바꾸지 마세요)
LANG_COMPONENT_ID = "{6B0E3B53-2B7C-4C55-9A3E-7E1C0F4D2A11}"
AUTOSTART_COMPONENT_ID = "{0D5C8E2A-71F4-4B9B-8C61-3F2A9B7D5E42}"
# 위젯(now_playing.pyw)이 읽는 곳과 같아야 함
LANG_KEY = r"Software\NowPlayingWidget"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "NowPlaying"
EXE = "NowPlaying.exe"
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


# ------------------------------------------------------------ 설치 화면 글자 ----
# 설치 화면 글자는 전부 [T_이름] 속성으로 넣어 둠. 기본값은 영어이고,
# 언어가 ko 이면 (첫 화면에서 고르거나 / 전에 고른 언어 / Windows 가 한국어) 한국어 값으로 바꿔 넣음.
# 주의: 값 안에 [ProductName] 같은 속성을 쓰면 풀리지 않고 그대로 보임 → 이름은 직접 적음
T = {
    "T_DlgTitle": ("Now Playing Setup", "Now Playing 설치"),
    "T_Back": ("< Back", "< 뒤로"),
    "T_Install": ("Install", "설치"),
    "T_Cancel": ("Cancel", "취소"),
    "T_Finish": ("Finish", "마침"),
    "T_Yes": ("Yes", "예"),
    "T_No": ("No", "아니요"),
    "T_OK": ("OK", "확인"),
    "T_Retry": ("Retry", "다시 시도"),
    "T_Ignore": ("Ignore", "무시"),
    "T_Abort": ("Abort", "중단"),
    "T_Exit": ("Exit", "끝내기"),
    "T_Return": ("Back", "돌아가기"),
    "T_Remove": ("Remove", "제거"),
    "T_Preparing": ("Getting ready…", "준비하는 중이에요…"),
    "T_InstTitle": ("Install Now Playing", "Now Playing 설치"),
    "T_InstBody": ("A small widget that shows the song playing right now on your desktop. "
                   "It installs for your account only, so no admin rights are needed.",
                   "바탕화면에 지금 재생 중인 곡을 띄워 주는 작은 위젯이에요. "
                   "관리자 권한 없이 지금 사용자 계정에만 설치돼요."),
    "T_InstPath": ("Install location", "설치 위치"),
    "T_AutoStart": ("Start automatically when I sign in to Windows", "Windows에 로그인하면 자동으로 켜기 (시작프로그램에 추가)"),
    "T_AutoHint": ("You can turn this off later in Task Manager > Startup apps.",
                   "나중에 작업 관리자 > 시작 앱에서 끌 수 있어요."),
    "T_InstGo": ("Click Install to begin.", "설치를 누르면 시작해요."),
    "T_ProgTitle": ("Installing Now Playing", "Now Playing 설치하는 중"),
    "T_RmProgTitle": ("Removing Now Playing", "Now Playing 제거하는 중"),
    "T_ProgText": ("Please wait a moment.", "잠시만 기다려 주세요."),
    "T_Status": ("Status:", "진행:"),
    "T_ExitTitle": ("Now Playing is installed", "Now Playing 설치를 마쳤어요"),
    "T_ExitBody": ("Click Finish to close setup.", "마침을 누르면 설치 프로그램이 닫혀요."),
    "T_RmExitTitle": ("Now Playing has been removed", "Now Playing을 제거했어요"),
    "T_RmExitBody": ("Your widget settings are kept in case you install it again.",
                     "다시 설치할 때를 위해 위젯 설정은 남겨 뒀어요."),
    "T_Launch": ("Start Now Playing now", "지금 Now Playing 켜기"),
    "T_UserExitTitle": ("Setup was cancelled", "설치 프로그램을 취소했어요"),
    "T_UserExitBody": ("Nothing on your computer was changed. You can run setup again any time.",
                       "컴퓨터에는 아무것도 바뀌지 않았어요. 언제든 다시 실행할 수 있어요."),
    "T_FatalTitle": ("Setup ended because of an error", "오류 때문에 설치 프로그램이 끝났어요"),
    "T_FatalBody": ("Nothing on your computer was changed. Please run setup again.",
                    "컴퓨터에는 아무것도 바뀌지 않았어요. 설치 프로그램을 다시 실행해 주세요."),
    "T_CancelAsk": ("Are you sure you want to cancel?", "정말 취소할까요?"),
    "T_Costing": ("Checking how much disk space is needed…", "필요한 디스크 공간을 확인하는 중이에요…"),
    "T_FilesTitle": ("Files in use", "사용 중인 파일"),
    "T_FilesText": ("These apps are using files that need to be updated. Close them and click Retry, "
                    "click Ignore to continue anyway, or Exit to stop.",
                    "아래 프로그램이 바꿔야 할 파일을 쓰고 있어요. 프로그램을 닫고 '다시 시도' 를 누르세요. "
                    "그냥 계속하려면 '무시', 그만두려면 '끝내기' 를 누르세요."),
    "T_MaintTitle": ("Remove Now Playing", "Now Playing 제거"),
    "T_MaintBody": ("Now Playing is already installed on this computer. Click Remove to uninstall it.",
                    "이 컴퓨터에 Now Playing이 이미 설치돼 있어요. 제거를 누르면 프로그램을 지워요."),
}


def force_codepage(path, codepage):
    """
    msi 글자 저장 방식을 한글이 들어가는 코드페이지(949)로 바꿈.
    msilib 는 이걸 못 해서 Windows Installer 함수(_ForceCodepage 가져오기)를 직접 부름.
    글자를 하나라도 넣기 전에 해야 함.
    """
    msi = ctypes.windll.msi
    h = wintypes.HANDLE()
    r = msi.MsiOpenDatabaseW(path, ctypes.c_wchar_p(1), ctypes.byref(h))   # 1 = MSIDBOPEN_TRANSACT
    if r:
        raise OSError(f"MsiOpenDatabase failed: {r}")
    try:
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "_ForceCodepage.idt"), "w", newline="") as f:
            f.write(f"\r\n\r\n{codepage}\t_ForceCodepage\r\n")
        r = msi.MsiDatabaseImportW(h, folder, "_ForceCodepage.idt")
        if r:
            raise OSError(f"MsiDatabaseImport(_ForceCodepage) failed: {r}")
        r = msi.MsiDatabaseCommit(h)
        if r:
            raise OSError(f"MsiDatabaseCommit failed: {r}")
    finally:
        msi.MsiCloseHandle(h)


def sql(db, query):
    view = db.OpenView(query)
    view.Execute(None)
    view.Close()


class NowPlayingMsi(bdist_msi):
    """cx_Freeze 의 bdist_msi 에 한국어/영어 설치 화면 · 언어 선택 · 시작프로그램 선택을 더함."""

    W, H = 370, 270           # 설치 창 크기 (설치 프로그램 단위)
    MODAL, MODELESS = 3, 1

    # ---- 데이터베이스 ----
    def add_properties(self):
        # 한글을 넣기 전에 코드페이지부터 바꾸고 다시 엶
        path = os.path.abspath(os.path.join(self.dist_dir, self.output_name))
        self.db.Commit()
        self.db.Close()
        force_codepage(path, 949)
        self.db = msilib.OpenDatabase(path, msilib.MSIDBOPEN_TRANSACT)
        super().add_properties()
        add_data(self.db, "Property", [(k, en) for k, (en, _) in T.items()] + [("LAUNCHAPP", "1")])

    def add_config(self):
        super().add_config()
        db = self.db
        # 폴더 고르기 · 사용권 화면은 안 씀 (설치 위치는 고정)
        sql(db, "DELETE FROM `InstallUISequence` WHERE `Action`='SelectDirectoryDlg' OR `Action`='LicenseAgreementDlg'")
        add_data(db, "InstallUISequence", [("LangDlg", "not Installed", 1230)])
        sql(db, "UPDATE `Property` SET `Value`='TARGETDIR;REINSTALLMODE;UILANG;AUTOSTART' "
                "WHERE `Property`='SecureCustomProperties'")
        # 업데이트할 때: 이전 버전을 먼저 지우고 새 버전을 설치
        # (msilib 기본값처럼 설치 뒤에 지우면, 새 버전이 방금 쓴 시작프로그램 · 언어 값이 같이 지워질 수 있음)
        sql(db, "UPDATE `InstallExecuteSequence` SET `Sequence`=1401 WHERE `Action`='RemoveExistingProducts'")

        # ---- 언어 정하기 (UILANG = ko / en) ----
        # 1) 명령줄로 받은 값 (위젯 업데이트)  2) 전에 설치할 때 고른 값  3) Windows 가 한국어면 ko  4) en
        # 첫 화면(PrepareDlg, 140)부터 맞는 언어로 나오도록 AppSearch 를 앞(50)으로 당기고 그 바로 뒤에 정함
        for table in ("InstallUISequence", "InstallExecuteSequence"):
            sql(db, f"UPDATE `{table}` SET `Sequence`=50 WHERE `Action`='AppSearch'")
        add_data(db, "RegLocator", [("NP_LangSig", 1, LANG_KEY, "Language", 2)])   # 1 = HKCU, 2 = 값 그대로
        add_data(db, "AppSearch", [("UILANG_REG", "NP_LangSig")])
        lang_actions = [
            ("NP_LangReg", "[UILANG_REG]", 'NOT UILANG AND (UILANG_REG="ko" OR UILANG_REG="en")'),
            ("NP_LangKo", "ko", "NOT UILANG AND (UserLanguageID=1042 OR SystemLanguageID=1042)"),
            ("NP_LangEn", "en", "NOT UILANG"),
            ("NP_LangFix", "en", 'UILANG<>"ko" AND UILANG<>"en"'),
        ]
        add_data(db, "CustomAction", [(name, 51, "UILANG", value) for name, value, _ in lang_actions])
        for table in ("InstallUISequence", "InstallExecuteSequence"):
            add_data(db, table, [(name, cond, 51 + i) for i, (name, _, cond) in enumerate(lang_actions)])
        # 한국어면 화면 글자를 한국어로 (설치 화면에서만 필요)
        seqs = [s for s in range(60, 140) if s != 100]   # 100 = LaunchConditions
        add_data(db, "CustomAction", [(f"NP_{k}", 51, k, ko) for k, (_, ko) in T.items()])
        add_data(db, "InstallUISequence", [(f"NP_{k}", 'UILANG="ko"', seqs[i]) for i, k in enumerate(T)])

    def add_files(self):
        super().add_files()
        db = self.db
        # 레지스트리 값 두 개를 각자 구성요소로 (기본 기능에 포함)
        # - 언어: 늘 설치. 위젯이 읽음 (설정에서 바꾸면 위젯이 덮어씀)
        # - 시작프로그램: AUTOSTART=1 일 때만 설치 (설치 화면 체크박스 · 업데이트 때 위젯이 넘김)
        add_data(db, "Component", [
            ("C_Language", LANG_COMPONENT_ID, "TARGETDIR", 4, None, "R_Language"),         # 4 = 레지스트리가 키
            ("C_Autostart", AUTOSTART_COMPONENT_ID, "TARGETDIR", 4, 'AUTOSTART="1"', "R_Autostart"),
        ])
        add_data(db, "Registry", [
            ("R_Language", 1, LANG_KEY, "Language", "[UILANG]", "C_Language"),
            ("R_Autostart", 1, RUN_KEY, RUN_NAME, f'"[TARGETDIR]{EXE}"', "C_Autostart"),
        ])
        add_data(db, "FeatureComponents", [("default", "C_Language"), ("default", "C_Autostart")])

    # ---- 화면 ----
    def add_text_styles(self):
        # 한글이 나오는 글꼴로 (Tahoma · Verdana 에는 한글이 없음)
        add_data(self.db, "TextStyle", [
            ("DlgFont8", "Malgun Gothic", 9, None, 0),
            ("DlgFontBold8", "Malgun Gothic", 9, None, 1),
            ("NP_Title", "Malgun Gothic", 13, None, 1),
            ("NP_Path", "Segoe UI", 9, None, 0),   # 폴더 경로: 한글 글꼴은 \ 를 ₩ 로 그림
        ])

    def _dialog(self, name, first, default, cancel, attr=None, w=None, h=None, title="[T_DlgTitle]"):
        d = Dialog(self.db, name, 50, 50, w or self.W, h or self.H, attr or self.MODAL, title, first, default, cancel)
        return d

    def _frame(self, d, title, body=None, body_h=40):
        """제목 + 본문 + 아래 구분선."""
        d.text("Title", 20, 14, self.W - 40, 22, 0x30003, r"{\NP_Title}" + title)
        if body:
            d.text("Body", 20, 46, self.W - 40, body_h, 0x30003, body)
        d.line("BottomLine", 0, self.H - 36, self.W, 0)

    def _button(self, d, name, slot, text, nxt, enabled=True, w=56):
        """아래 버튼 자리: slot 0 = 뒤로, 1 = 다음/설치, 2 = 취소."""
        x = {0: 178, 1: 238, 2: 300}[slot]
        return d.pushbutton(name, x, self.H - 27, w, 17, 3 if enabled else 1, text, nxt)

    def add_ui(self):
        db = self.db
        self.add_text_styles()
        W, H = self.W, self.H

        # 오류 창 (Windows Installer 가 필요한 버튼만 보여 줌)
        d = Dialog(db, "ErrorDlg", 50, 10, 330, 101, 65543, "[T_DlgTitle]", "ErrorText", None, None)
        d.text("ErrorText", 50, 9, 280, 48, 3, "")
        for key, x in (("No", 120), ("Yes", 240), ("Abort", 0), ("Cancel", 42), ("Ignore", 81), ("OK", 159),
                       ("Retry", 198)):
            d.pushbutton(key[0], x, 72, 81, 21, 3, f"[T_{key}]", None).event(
                "EndDialog", "ErrorOk" if key == "OK" else f"Error{key}")

        # 취소 확인
        d = Dialog(db, "CancelDlg", 50, 10, 260, 85, self.MODAL, "[T_DlgTitle]", "No", "No", "No")
        d.text("Text", 20, 15, 220, 30, 0x30003, "[T_CancelAsk]")
        d.pushbutton("Yes", 72, 57, 56, 17, 3, "[T_Yes]", "No").event("EndDialog", "Exit")
        d.pushbutton("No", 132, 57, 56, 17, 3, "[T_No]", "Yes").event("EndDialog", "Return")

        # 디스크 공간 계산 기다리기
        d = Dialog(db, "WaitForCostingDlg", 50, 10, 260, 85, self.MODAL, "[T_DlgTitle]", "Return", "Return", "Return")
        d.text("Text", 20, 15, 220, 30, 0x30003, "[T_Costing]")
        d.pushbutton("Return", 102, 57, 56, 17, 3, "[T_Return]", None).event("EndDialog", "Exit")

        # 준비 중 (언어 정하는 동작들 뒤에 나옴)
        d = self._dialog("PrepareDlg", "Cancel", "Cancel", "Cancel", attr=self.MODELESS)
        self._frame(d, "Now Playing", "[T_Preparing]", 20)
        d.text("ActionText", 20, 80, W - 40, 20, 0x30003, "").mapping("ActionText", "Text")
        d.text("ActionData", 20, 100, W - 40, 30, 0x30003, "").mapping("ActionData", "Text")
        self._button(d, "Cancel", 2, "[T_Cancel]", None).event("SpawnDialog", "CancelDlg")

        # 1) 언어 고르기 (두 언어로 같이 적음)
        d = self._dialog("LangDlg", "LangGroup", "Next", "Cancel", title="Now Playing")
        self._frame(d, "Now Playing")
        d.text("Ko", 20, 46, W - 40, 14, 0x30003, "설치에 쓸 언어를 고르세요.")
        d.text("En", 20, 61, W - 40, 14, 0x30003, "Choose a language for setup.")
        g = d.radiogroup("LangGroup", 30, 88, 200, 44, 3, "UILANG", "", "Next")
        g.add("ko", 0, 0, 190, 18, "한국어", "ko")
        g.add("en", 0, 22, 190, 18, "English", "en")
        d.text("Note1", 20, 146, W - 40, 14, 0x30003, "고른 언어는 위젯에도 쓰여요. (위젯 설정에서 바꿀 수 있어요)")
        d.text("Note2", 20, 161, W - 40, 14, 0x30003, "The widget uses this language too. (You can change it in Settings.)")
        nb = d.pushbutton("Next", 206, H - 27, 72, 17, 3, "다음 / Next", "Cancel")
        order = 1
        for k, (en, ko) in T.items():   # 고른 언어로 나머지 화면 글자를 바꿔 넣고 다음 화면으로
            nb.event(f"[{k}]", ko, 'UILANG="ko"', order)
            nb.event(f"[{k}]", en, 'UILANG<>"ko"', order + 1)
            order += 2
        nb.event("NewDialog", "InstallDlg", "1", order)
        d.pushbutton("Cancel", 284, H - 27, 72, 17, 3, "취소 / Cancel", "LangGroup").event("SpawnDialog", "CancelDlg")

        # 2) 설치 확인 + 시작프로그램
        d = self._dialog("InstallDlg", "AutoStart", "Install", "Cancel")
        self._frame(d, "[T_InstTitle]", "[T_InstBody]", 30)
        d.text("PathLabel", 20, 84, W - 40, 14, 0x30003, "[T_InstPath]")
        d.text("Path", 30, 99, W - 50, 14, 0x30003, r"{\NP_Path}[TARGETDIR]")
        d.checkbox("AutoStart", 20, 126, W - 40, 18, 3, "AUTOSTART", "[T_AutoStart]", "Back")
        d.text("AutoHint", 34, 145, W - 54, 14, 0x30003, "[T_AutoHint]")
        d.text("Go", 20, H - 58, W - 40, 14, 0x30003, "[T_InstGo]")
        self._button(d, "Back", 0, "[T_Back]", "Install").event("NewDialog", "LangDlg")
        b = self._button(d, "Install", 1, "[T_Install]", "Cancel")
        b.event("SetTargetPath", "TARGETDIR", "1", 1)
        b.event("SpawnWaitDialog", "WaitForCostingDlg", "CostingComplete = 1", 2)
        b.event("EndDialog", "Return", "1", 3)
        self._button(d, "Cancel", 2, "[T_Cancel]", "AutoStart").event("SpawnDialog", "CancelDlg")
        add_data(db, "CheckBox", [("AUTOSTART", "1"), ("LAUNCHAPP", "1")])

        # 설치 / 제거 진행
        d = self._dialog("ProgressDlg", "Cancel", "Cancel", "Cancel", attr=self.MODELESS)
        self._frame(d, "[T_ProgTitle]", "[T_ProgText]", 20)
        d.text("StatusLabel", 20, 84, 40, 14, 0x30003, "[T_Status]")
        d.text("ActionText", 62, 84, W - 82, 14, 0x30003, "").mapping("ActionText", "Text")
        d.control("ProgressBar", "ProgressBar", 20, 104, W - 40, 12, 65537, None, "Progress done", None,
                  None).mapping("SetProgress", "Progress")
        self._button(d, "Cancel", 2, "[T_Cancel]", None).event("SpawnDialog", "CancelDlg")

        # 이미 설치돼 있을 때 (같은 msi 를 다시 실행): 제거만
        d = self._dialog("MaintenanceTypeDlg", "Remove", "Remove", "Cancel")
        self._frame(d, "[T_MaintTitle]", "[T_MaintBody]", 40)
        b = self._button(d, "Remove", 1, "[T_Remove]", "Cancel")
        for i, (event, arg) in enumerate([
                ("[REMOVE]", "ALL"), ("[T_ProgTitle]", "[T_RmProgTitle]"),
                ("[T_ExitTitle]", "[T_RmExitTitle]"), ("[T_ExitBody]", "[T_RmExitBody]"),
                ("Remove", "ALL"), ("EndDialog", "Return")], 1):
            b.event(event, arg, "1", i)
        self._button(d, "Cancel", 2, "[T_Cancel]", "Remove").event("SpawnDialog", "CancelDlg")

        # 끝 (설치했으면 '지금 켜기' 체크박스)
        d = self._dialog("ExitDialog", "Finish", "Finish", "Finish")
        self._frame(d, "[T_ExitTitle]", "[T_ExitBody]", 30)
        c = d.checkbox("LaunchOnFinish", 20, 90, W - 40, 18, 3, "LAUNCHAPP", "[T_Launch]", "Finish")
        c.condition("Hide", 'REMOVE="ALL"')
        b = self._button(d, "Finish", 2, "[T_Finish]", "LaunchOnFinish")
        b.event("DoAction", "VSDCA_Launch", 'LAUNCHAPP=1 AND NOT REMOVE="ALL"', 1)
        b.event("EndDialog", "Return", "1", 2)
        add_data(db, "CustomAction", [("VSDCA_Launch", 226, "TARGETDIR", f"[TARGETDIR]{EXE}")])

        for name, title, body in (("UserExit", "[T_UserExitTitle]", "[T_UserExitBody]"),
                                  ("FatalError", "[T_FatalTitle]", "[T_FatalBody]")):
            d = self._dialog(name, "Finish", "Finish", "Finish")
            self._frame(d, title, body, 40)
            self._button(d, "Finish", 2, "[T_Finish]", None).event("EndDialog", "Exit")

        # 파일 사용 중
        d = self._dialog("FilesInUse", "Retry", "Retry", "Retry", attr=19)
        self._frame(d, "[T_FilesTitle]", "[T_FilesText]", 40)
        d.control("List", "ListBox", 20, 92, W - 40, H - 140, 7, "FileInUseProcess", None, None, None)
        self._button(d, "Exit", 0, "[T_Exit]", "Ignore").event("EndDialog", "Exit")
        self._button(d, "Ignore", 1, "[T_Ignore]", "Retry").event("EndDialog", "Ignore")
        self._button(d, "Retry", 2, "[T_Retry]", "Exit").event("EndDialog", "Retry")


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
    f"[TARGETDIR]{EXE}",          # Target
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
    # 설치(업데이트) · 제거할 때 위젯이 켜져 있으면 먼저 끔 → '파일 사용 중 / 다시 시작 필요' 를 막음
    # 설치 폴더에 NowPlaying.exe 가 있으면 (AppSearch 가 찾아서 NP_EXISTING_EXE 에 경로를 넣음) 그걸 --quit 로 실행
    # 50 = 속성에 든 exe 실행, +64 = 결과와 상관없이 계속 진행
    "Signature": [("NP_ExeSig", EXE, None, None, None, None, None, None, None)],
    "DrLocator": [("NP_ExeSig", None, r"[LocalAppDataFolder]Programs\NowPlaying", 0)],
    "AppSearch": [("NP_EXISTING_EXE", "NP_ExeSig")],
    "CustomAction": [("A_CLOSE_APP", 50 + 64, "NP_EXISTING_EXE", "--quit")],
    "InstallExecuteSequence": [("A_CLOSE_APP", "NP_EXISTING_EXE", 1390)],   # InstallValidate(1400) 전에
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
    cmdclass={"bdist_msi": NowPlayingMsi},
    executables=[Executable(
        "now_playing.pyw",
        base="gui",                      # 콘솔 창 없이
        target_name=EXE,
        icon=ICON,
        shortcut_name=NAME,
        shortcut_dir="ProgramMenuFolder",
    )],
)
