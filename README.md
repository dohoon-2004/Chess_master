# Stockfish Chess Review

## Streamlit Community Cloud 배포

이 저장소의 파일을 GitHub에 그대로 업로드합니다.

- chess_app.py
- requirements.txt
- packages.txt

Streamlit Community Cloud에서 새 앱을 만들고 GitHub 저장소를 연결한 뒤
Main file path를 `chess_app.py`로 지정합니다.

Cloud에서는 `packages.txt`를 통해 Stockfish를 설치하고 앱이
`/usr/games/stockfish` 등 일반적인 Linux 설치 경로를 자동 탐색합니다.
