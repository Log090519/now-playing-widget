# -*- coding: utf-8 -*-
"""
새 버전을 GitHub 에 올립니다. 켜져 있는 위젯들이 알아채고 ⬇ 버튼으로 받아 갑니다.

    1) now_playing.pyw 의 APP_VERSION 숫자를 올림   (예: 1.1.0 → 1.1.1)
    2) python release.py "바뀐 점 한 줄"

하는 일: 바뀐 파일 커밋 · 푸시 → 설치 파일(.msi) 만들기 → GitHub Release v<버전> 만들고 .msi 첨부
필요: git, GitHub CLI 로그인 (gh auth login)
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(*cmd, check=True, capture=False):
    print("›", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, cwd=HERE, check=check, text=True, encoding="utf-8",
                          capture_output=capture)


def find_gh():
    gh = shutil.which("gh")
    if gh:
        return gh
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    for root, _, files in os.walk(base):
        if "gh.exe" in files:
            return os.path.join(root, "gh.exe")
    sys.exit("GitHub CLI(gh)를 찾을 수 없어요.  winget install GitHub.cli  로 설치하고  gh auth login  하세요.")


def main():
    sys.stdout.reconfigure(errors="replace")   # 출력을 파일로 돌릴 때 '›' 같은 글자 때문에 멈추지 않게
    notes = " ".join(sys.argv[1:]).strip()
    with open(os.path.join(HERE, "now_playing.pyw"), encoding="utf-8") as f:
        version = re.search(r'^APP_VERSION = "([\d.]+)"', f.read(), re.M).group(1)
    tag = f"v{version}"
    gh = find_gh()

    if run(gh, "release", "view", tag, check=False, capture=True).returncode == 0:
        sys.exit(f"{tag} 은 이미 올라가 있어요. now_playing.pyw 의 APP_VERSION 을 올린 뒤 다시 실행하세요.")

    if run("git", "status", "--porcelain", capture=True).stdout.strip():
        run("git", "add", "-A")
        run("git", "commit", "-m", f"Release {tag}" + (f": {notes}" if notes else ""))
    # push 할 때만 GitHub CLI 로그인 정보를 씀 (전역 git 설정은 건드리지 않음)
    helper = "!'" + gh.replace("\\", "/") + "' auth git-credential"
    run("git", "-c", "credential.helper=", "-c", f"credential.helper={helper}", "push", "origin", "HEAD")

    run(sys.executable, "setup.py", "bdist_msi")
    msi = os.path.join(HERE, "dist", f"NowPlaying-{version}-win64.msi")
    if not os.path.exists(msi):
        sys.exit("설치 파일이 만들어지지 않았어요. 위 출력의 오류를 확인하세요.")

    run(gh, "release", "create", tag, msi, "--title", f"Now Playing {version}",
        "--notes", notes or f"Now Playing {version}")
    print(f"\n완료: {tag} 을 올렸어요. 켜져 있는 위젯들은 다음 확인 때 새 버전을 알아채요.")


if __name__ == "__main__":
    main()
