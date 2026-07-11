# Stockfish Chess Review

Streamlit에서 바로 실행하는 체스 분석 앱입니다.

## 주요 기능

- 직접 두기: 클릭형 체스판에서 실제 체스 수를 두고 Stockfish 추천 수를 확인
- PGN 복기: PGN 파일 또는 PGN 텍스트를 불러와 수순별로 분석
- FEN 분석: 특정 포지션을 입력해 바로 분석
- 전체 게임 분석: 각 수의 CPL, 추천 수, 추천 라인, 간단한 코치 설명 제공

## 이번 수정본에서 고친 점

- `한 수 취소`를 빠르게 누르거나 모바일/Streamlit Cloud에서 버튼 이벤트가 지연될 때 `IndexError`가 나던 문제를 막았습니다.
- GitHub 업로드/Streamlit Cloud 배포 중 `chessboard_component/index.html` 폴더가 누락되면 체스판이 안 뜨는 문제를 막았습니다.
- 체스판 HTML을 `chess_app.py` 안에 포함했고, 앱 실행 시 임시 폴더에 `index.html`을 자동 생성합니다.
- 따라서 GitHub에는 아래 3개 파일만 올려도 됩니다.

```text
chess_app.py
requirements.txt
packages.txt
```

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run chess_app.py
```

Stockfish 실행 파일이 PATH에 있으면 자동으로 찾습니다. 자동 탐색이 실패하면 사이드바에 실행 파일 경로를 직접 입력하세요.

## Streamlit Community Cloud 배포

- Main file path: `chess_app.py`
- `packages.txt`에 `stockfish`가 포함되어 있어 Debian/Ubuntu 기반 배포 환경에서 Stockfish가 설치됩니다.
- 앱이 자동으로 `/usr/games/stockfish`, `/usr/bin/stockfish`, `/usr/local/bin/stockfish`를 탐색합니다.

## GitHub에 올리는 방법

GitHub 웹에서 `Add file` -> `Upload files`를 누른 뒤 ZIP 파일 자체를 올리지 말고, 압축을 푼 다음 위의 3개 파일을 드래그해서 올리세요.

```text
chess_streamlit_github_ready/
├── chess_app.py
├── requirements.txt
└── packages.txt
```
