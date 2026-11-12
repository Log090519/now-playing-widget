# Now Playing

바탕화면에 지금 재생 중인 곡(앨범아트 · 제목 · 가수 · 진행바)을 작게 띄워 주는 Windows 위젯이에요.

- Windows 미디어 컨트롤에 곡 정보를 보내는 앱이면 다 돼요 (Spotify, 브라우저의 YouTube · YouTube Music, 미디어 플레이어 등)
- 소리 나는 앱이 여럿이면 음악 앱 · 음악 사이트를 먼저 보여줘요
  (Chrome · Edge 에서 탭 여러 개가 소리를 내면 음악 탭의 제목을 보여줘요. 브라우저가 Windows 에 탭 하나만 알려 줘서,
  알려 주지 않은 탭은 앨범아트 · 진행바 없이 제목만 나와요)
- 진행바 · 위젯 배경에 Windows 강조색 그라데이션
- 바탕화면에 붙이기 (Win+D 를 눌러도 사라지지 않음)
- 작업표시줄 자동 숨기기를 쓰면 작업표시줄을 따라 부드럽게 움직임
- 트레이 아이콘, 새 버전 자동 확인 · 업데이트
- 한국어 · English (설치할 때 고르고, 위젯 설정에서 바꿀 수 있어요)

## 설치

[Releases](../../releases/latest) 에서 `NowPlaying-<버전>-win64.msi` 를 받아 실행하세요.

- 첫 화면에서 언어(한국어 / English)를 고르면 나머지 설치 화면과 위젯이 그 언어로 나와요
- 설치 화면에서 **Windows에 로그인하면 자동으로 켜기**(시작프로그램)를 고를 수 있어요
- 관리자 권한 없이 내 계정에만 설치돼요 (`%LOCALAPPDATA%\Programs\NowPlaying`, 위치는 고정)
- 서명이 없는 설치 파일이라 SmartScreen 경고가 나오면 **추가 정보 → 실행**
- 제거: **설정 › 앱 › 설치된 앱** 또는 **제어판 › 프로그램 제거** 에서 "Now Playing"
- 설정은 `%APPDATA%\NowPlayingWidget` 에 저장돼요 (제거해도 남음)

## 사용법

- 드래그: 위치 이동
- 위젯에 마우스를 올리면: 왼쪽 위 ⚙ 설정, 오른쪽 위 ⬇ 업데이트 · ✕ 종료
- 새 버전이 나오면 ⬇ 버튼이 강조색으로 늘 보여요 → 누르면 받아서 설치하고 다시 켜져요
  (언어 · 시작프로그램 선택은 그대로 이어져요. 이미 최신이면 위젯 안에 잠깐 표시돼요)
- 트레이 아이콘: 클릭 = 설정, 우클릭 = 메뉴

## 개발

```bash
pip install -r requirements.txt
python now_playing.pyw            # 실행
python now_playing.pyw --demo     # 가짜 곡으로 미리보기 (playing | paused | live | empty | long)
python setup.py bdist_msi         # 설치 파일만 만들기 → dist\
```

## 새 버전 올리기

1. `now_playing.pyw` 의 `APP_VERSION` 숫자를 올려요 (예: `1.2.0` → `1.2.1`)
2. 실행:

   ```bash
   python release.py "바뀐 점 한 줄"
   ```

   바뀐 파일을 커밋 · 푸시하고, 설치 파일을 만들어 GitHub Release `v<버전>` 에 올려요.
   켜져 있는 위젯들은 몇 시간 안에 (또는 ⬇ 버튼 / 트레이 '업데이트 확인' 을 누르면 바로) 새 버전을 알아채요.

필요한 것: git, [GitHub CLI](https://cli.github.com/) 로그인 (`gh auth login`)
