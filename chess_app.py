# chess_app.py
# 실행:
#   pip install streamlit python-chess pandas
#   streamlit run chess_app.py
#
# Stockfish:
#   1) 이 파일과 같은 폴더에 stockfish.exe(Windows) 또는 stockfish 실행 파일을 둡니다.
#   2) 또는 Stockfish가 PATH에 등록되어 있으면 자동 탐색합니다.
#   3) 자동 탐색 실패 시 앱 사이드바에서 실행 파일 경로를 직접 입력할 수 있습니다.

from __future__ import annotations

import html as html_lib
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
import chess.svg
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


APP_TITLE = "Stockfish Chess Review"
DEFAULT_DEPTH = 14
MATE_SCORE = 100_000

BASE_DIR = Path(__file__).resolve().parent

# GitHub 웹 업로드/Streamlit Cloud 배포에서 별도 HTML 폴더가 빠져도
# 체스판 컴포넌트가 동작하도록 HTML을 Python 파일 안에 포함합니다.
# 앱 시작 시 임시 폴더에 index.html을 자동 생성한 뒤 Streamlit 컴포넌트로 로드합니다.
CHESSBOARD_COMPONENT_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    :root {
      --light: #eeeed2;
      --dark: #769656;
      --light-hover: #f7f7df;
      --dark-hover: #86a666;
      --last: rgba(246, 246, 105, 0.42);
      --selected: rgba(255, 214, 10, 0.95);
      --target: rgba(28, 28, 28, 0.34);
      --capture: rgba(35, 35, 35, 0.38);
    }

    html, body {
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .wrap {
      width: min(100%, 640px);
      max-width: 640px;
      margin: 0 auto;
      padding: 0;
    }

    .board {
      width: 100%;
      aspect-ratio: 1 / 1;
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      grid-template-rows: repeat(8, 1fr);
      overflow: hidden;
      border-radius: 6px;
      box-shadow: 0 10px 32px rgba(0, 0, 0, 0.24);
      background: var(--dark);
      user-select: none;
      touch-action: manipulation;
    }

    .square {
      position: relative;
      appearance: none;
      border: 0;
      border-radius: 0;
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      min-width: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      color: #111;
      font-size: clamp(28px, 8.6vw, 62px);
      line-height: 1;
      font-family: "Segoe UI Symbol", "Noto Sans Symbols 2", "Apple Symbols", "DejaVu Sans", sans-serif;
      transition: filter 70ms ease, transform 70ms ease;
    }

    .square.light { background: var(--light); }
    .square.dark { background: var(--dark); }
    .square.light:hover { background: var(--light-hover); }
    .square.dark:hover { background: var(--dark-hover); }
    .square:hover { filter: brightness(1.03); }
    .square:focus-visible {
      outline: 3px solid #4aa3ff;
      outline-offset: -3px;
      z-index: 5;
    }

    .square.last::before {
      content: "";
      position: absolute;
      inset: 0;
      background: var(--last);
      pointer-events: none;
    }

    .square.selected::after {
      content: "";
      position: absolute;
      inset: 0;
      box-shadow: inset 0 0 0 clamp(3px, 0.8vw, 6px) var(--selected);
      pointer-events: none;
      z-index: 4;
    }

    .square.target-empty .target-dot {
      position: absolute;
      width: 28%;
      height: 28%;
      border-radius: 50%;
      background: var(--target);
      pointer-events: none;
      z-index: 3;
    }

    .square.target-capture .target-ring {
      position: absolute;
      inset: 6%;
      border-radius: 50%;
      border: clamp(3px, 0.7vw, 6px) solid var(--capture);
      pointer-events: none;
      z-index: 3;
    }

    .coord-file,
    .coord-rank {
      position: absolute;
      z-index: 6;
      font-size: clamp(9px, 2vw, 13px);
      font-weight: 800;
      line-height: 1;
      pointer-events: none;
      opacity: 0.9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .coord-file { right: 4px; bottom: 3px; }
    .coord-rank { left: 4px; top: 3px; }
    .square.dark .coord-file, .square.dark .coord-rank { color: var(--light); }
    .square.light .coord-file, .square.light .coord-rank { color: var(--dark); }

    .piece {
      position: relative;
      z-index: 2;
      transform: translateY(-1px);
      text-shadow: 0 2px 2px rgba(0,0,0,.28);
      font-size: 1.06em;
    }

    .board.reviewing .square {
      cursor: default;
    }

    .review-badge {
      position: absolute;
      left: 50%;
      bottom: 10px;
      transform: translateX(-50%);
      z-index: 20;
      background: rgba(28, 28, 28, .82);
      color: #fff;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 800;
      pointer-events: none;
      white-space: nowrap;
    }

    @media (max-width: 700px) {
      .wrap { width: 100%; max-width: none; }
      .square { font-size: clamp(25px, 10.5vw, 54px); }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div id="board" class="board" aria-label="Clickable chess board"></div>
  </main>

  <script>
    const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
    const RANKS = ["1", "2", "3", "4", "5", "6", "7", "8"];

    function streamlitPost(type, payload) {
      window.parent.postMessage({ isStreamlitMessage: true, type, ...payload }, "*");
    }

    function setFrameHeight() {
      const height = document.documentElement.scrollHeight || document.body.scrollHeight || 640;
      streamlitPost("streamlit:setFrameHeight", { height });
    }

    function sendSquare(square) {
      const id = `${Date.now()}-${square}-${Math.random().toString(36).slice(2)}`;
      streamlitPost("streamlit:setComponentValue", { value: { square, id } });
    }

    function squareColorClass(square) {
      const fileIndex = FILES.indexOf(square[0]);
      const rankIndex = RANKS.indexOf(square[1]);
      return ((fileIndex + rankIndex) % 2 === 0) ? "dark" : "light";
    }

    function render(args) {
      const board = document.getElementById("board");
      const pieces = args.pieces || {};
      const orientation = args.orientation === "black" ? "black" : "white";
      const selected = args.selected || "";
      const legalTargets = new Set(args.legal_targets || []);
      const lastMove = new Set(args.last_move || []);
      const interactive = args.interactive !== false;

      board.classList.toggle("reviewing", !interactive);

      const files = orientation === "white" ? FILES : [...FILES].reverse();
      const ranks = orientation === "white" ? [...RANKS].reverse() : RANKS;
      const bottomRank = ranks[ranks.length - 1];
      const leftFile = files[0];

      board.innerHTML = "";
      const fragment = document.createDocumentFragment();

      for (const rank of ranks) {
        for (const file of files) {
          const square = `${file}${rank}`;
          const piece = pieces[square] || "";
          const isTarget = legalTargets.has(square);

          const button = document.createElement("button");
          button.type = "button";
          button.className = `square ${squareColorClass(square)}`;
          button.dataset.square = square;
          button.setAttribute("aria-label", square + (piece ? ` ${piece}` : ""));

          if (lastMove.has(square)) button.classList.add("last");
          if (selected === square) button.classList.add("selected");
          if (isTarget && piece) button.classList.add("target-capture");
          if (isTarget && !piece) button.classList.add("target-empty");

          if (piece) {
            const pieceSpan = document.createElement("span");
            pieceSpan.className = "piece";
            pieceSpan.textContent = piece;
            button.appendChild(pieceSpan);
          }

          if (file === leftFile) {
            const rankLabel = document.createElement("span");
            rankLabel.className = "coord-rank";
            rankLabel.textContent = rank;
            button.appendChild(rankLabel);
          }
          if (rank === bottomRank) {
            const fileLabel = document.createElement("span");
            fileLabel.className = "coord-file";
            fileLabel.textContent = file;
            button.appendChild(fileLabel);
          }
          if (isTarget && piece) {
            const ring = document.createElement("span");
            ring.className = "target-ring";
            button.appendChild(ring);
          }
          if (isTarget && !piece) {
            const dot = document.createElement("span");
            dot.className = "target-dot";
            button.appendChild(dot);
          }

          if (interactive) {
            button.addEventListener("click", () => sendSquare(square));
          } else {
            button.disabled = true;
          }
          fragment.appendChild(button);
        }
      }

      board.appendChild(fragment);
      requestAnimationFrame(setFrameHeight);
    }

    window.addEventListener("message", (event) => {
      const data = event.data || {};
      if (data.type !== "streamlit:render") return;
      render(data.args || {});
    });

    streamlitPost("streamlit:componentReady", { apiVersion: 1 });
    setFrameHeight();
  </script>
</body>
</html>
"""


def ensure_chessboard_component() -> Path:
    """로컬 Streamlit 컴포넌트용 index.html을 항상 사용 가능한 위치에 생성합니다."""
    component_dir = Path(tempfile.gettempdir()) / "stockfish_chess_review_component"
    component_dir.mkdir(parents=True, exist_ok=True)

    index_path = component_dir / "index.html"
    if not index_path.exists() or index_path.read_text(encoding="utf-8") != CHESSBOARD_COMPONENT_HTML:
        index_path.write_text(CHESSBOARD_COMPONENT_HTML, encoding="utf-8")

    return component_dir


CHESSBOARD_COMPONENT_DIR = ensure_chessboard_component()


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="♟️",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.3rem; padding-bottom: 2rem;}
        .small-muted {color: #8b949e; font-size: 0.88rem;}
        .review-box {
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 12px;
            padding: 14px 16px;
            margin: 8px 0;
        }
        .eval-wrap {
            width: 100%;
            margin: 0.15rem 0 0.9rem 0;
        }
        .eval-bar {
            position: relative;
            height: 42px;
            overflow: hidden;
            background: #403c3a;
            border-radius: 5px;
            box-shadow: inset 0 0 0 1px rgba(0,0,0,.16);
        }
        .eval-white {
            height: 100%;
            background: #f0f0f0;
            transition: width .18s ease;
        }
        .eval-score {
            position: absolute;
            top: 6px;
            left: 11px;
            font-size: 1.28rem;
            font-weight: 900;
            color: #222;
            letter-spacing: -.03em;
        }
        .eval-meta {
            display: flex;
            justify-content: space-between;
            color: #8b949e;
            font-size: .84rem;
            margin-top: 5px;
        }
        .move-strip {
            background: #2b2725;
            color: #d7d4cf;
            border-radius: 0 0 10px 10px;
            padding: 12px 14px;
            line-height: 1.95;
            max-height: 180px;
            overflow-y: auto;
            font-size: 1.02rem;
            font-weight: 700;
        }
        .move-number { color: #918d88; margin-right: 3px; }
        .move-item {
            display: inline-block;
            padding: 1px 6px;
            margin-right: 2px;
            border-radius: 6px;
        }
        .move-item.active {
            background: #86ad57;
            color: #10120d;
        }
        .reviewing-note {
            background: rgba(255, 193, 7, .12);
            border: 1px solid rgba(255, 193, 7, .30);
            border-radius: 10px;
            padding: 9px 11px;
            margin: 8px 0;
            font-weight: 700;
        }
        @media (max-width: 700px) {
            .block-container { padding-left: .7rem; padding-right: .7rem; }
            .eval-bar { height: 38px; }
            .eval-score { top: 5px; font-size: 1.18rem; }
            .move-strip { max-height: 155px; font-size: .96rem; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

clickable_chessboard = components.declare_component(
    "clickable_chessboard",
    path=str(CHESSBOARD_COMPONENT_DIR),
)


# -----------------------------
# 유틸
# -----------------------------
def detect_stockfish() -> str | None:
    """Stockfish 실행 파일을 PATH 또는 현재 폴더 주변에서 찾습니다."""
    path_hit = shutil.which("stockfish")
    if path_hit:
        return path_hit

    # Streamlit Community Cloud / Debian 계열에서 apt stockfish 설치 위치
    cloud_candidates = [
        Path("/usr/games/stockfish"),
        Path("/usr/bin/stockfish"),
        Path("/usr/local/bin/stockfish"),
    ]
    for candidate in cloud_candidates:
        if candidate.is_file():
            return str(candidate)

    base = Path(__file__).resolve().parent
    names = [
        "stockfish.exe",
        "stockfish",
        "stockfish-windows-x86-64-avx2.exe",
        "stockfish-windows-x86-64.exe",
    ]

    for name in names:
        candidate = base / name
        if candidate.is_file():
            return str(candidate)

    # 공식 압축 해제 폴더까지 고려해 얕게 재귀 탐색
    patterns = ["stockfish*.exe", "stockfish"]
    for pattern in patterns:
        for candidate in base.glob(f"**/{pattern}"):
            if candidate.is_file():
                return str(candidate)

    return None


def validate_engine_path(path_text: str) -> tuple[bool, str]:
    path_text = path_text.strip().strip('"')
    if not path_text:
        return False, "Stockfish 경로가 비어 있습니다."

    resolved = shutil.which(path_text)
    if resolved:
        return True, resolved

    p = Path(path_text).expanduser()
    if p.is_file():
        return True, str(p.resolve())

    return False, f"실행 파일을 찾지 못했습니다: {path_text}"


def parse_pgn_bytes(raw: bytes) -> list[chess.pgn.Game]:
    text = raw.decode("utf-8-sig", errors="replace")
    stream = io.StringIO(text)
    games: list[chess.pgn.Game] = []

    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        games.append(game)

    return games


def game_label(game: chess.pgn.Game, idx: int) -> str:
    h = game.headers
    white = h.get("White", "White")
    black = h.get("Black", "Black")
    result = h.get("Result", "*")
    date = h.get("Date", "?")
    return f"{idx + 1}. {white} vs {black} · {result} · {date}"


def game_positions(game: chess.pgn.Game) -> tuple[list[chess.Board], list[chess.Move], list[str]]:
    """
    positions[i] = i개의 수가 진행된 보드.
    moves[i] = i번째 실제 수.
    sans[i] = 해당 수의 SAN.
    """
    board = game.board()
    positions = [board.copy(stack=False)]
    moves: list[chess.Move] = []
    sans: list[str] = []

    for move in game.mainline_moves():
        sans.append(board.san(move))
        moves.append(move)
        board.push(move)
        positions.append(board.copy(stack=False))

    return positions, moves, sans


def render_board(board: chess.Board, last_move: chess.Move | None, orientation: chess.Color) -> None:
    svg = chess.svg.board(
        board=board,
        lastmove=last_move,
        orientation=orientation,
        size=600,
        coordinates=True,
    )
    components.html(
        f"""
        <div style="display:flex;justify-content:center;align-items:center;">
            {svg}
        </div>
        """,
        height=625,
        scrolling=False,
    )


def score_cp(score: chess.engine.PovScore, pov: chess.Color) -> int:
    value = score.pov(pov).score(mate_score=MATE_SCORE)
    return 0 if value is None else int(value)


def score_text(score: chess.engine.PovScore, pov: chess.Color = chess.WHITE) -> str:
    pov_score = score.pov(pov)
    mate = pov_score.mate()
    if mate is not None:
        return f"M{mate:+d}"
    cp = pov_score.score()
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


def pv_to_san(board: chess.Board, pv: list[chess.Move], max_plies: int = 8) -> str:
    temp = board.copy(stack=False)
    out: list[str] = []

    for move in pv[:max_plies]:
        if move not in temp.legal_moves:
            break
        out.append(temp.san(move))
        temp.push(move)

    return " ".join(out) if out else "-"


def classify_loss(loss_cp: int) -> tuple[str, str]:
    """
    간단한 초보자용 판정.
    CPL 기준은 앱 내부 휴리스틱이며 공식 Stockfish 분류 기준이 아닙니다.
    """
    if loss_cp < 20:
        return "정확", "✅"
    if loss_cp < 50:
        return "좋음", "👍"
    if loss_cp < 100:
        return "부정확", "⚠️"
    if loss_cp < 200:
        return "실수", "❌"
    return "블런더", "💥"


def coach_message(
    board_before: chess.Board,
    played_move: chess.Move,
    best_move: chess.Move | None,
    loss_cp: int,
    label: str,
) -> str:
    mover = "백" if board_before.turn == chess.WHITE else "흑"
    played_san = board_before.san(played_move)

    if loss_cp < 20:
        return f"{mover}의 **{played_san}**는 엔진 최선에 매우 가까운 수입니다."

    best_san = "-"
    if best_move is not None and best_move in board_before.legal_moves:
        best_san = board_before.san(best_move)

    if label == "부정확":
        return (
            f"**{played_san}**도 둘 수 있지만 평가를 조금 잃었습니다. "
            f"이 포지션에서는 **{best_san}**를 먼저 검토해 보세요."
        )
    if label == "실수":
        return (
            f"**{played_san}** 이후 상대에게 눈에 띄는 기회를 줬습니다. "
            f"수를 두기 전 **체크 → 잡기 → 공격받는 기물** 순서로 확인하고, "
            f"엔진 추천 **{best_san}**와 비교해 보세요."
        )
    if label == "블런더":
        return (
            f"**{played_san}**에서 평가가 크게 떨어졌습니다. "
            f"즉시 전술이나 큰 기물 손실 가능성을 먼저 확인해야 합니다. "
            f"엔진의 첫 선택은 **{best_san}**입니다."
        )

    return f"**{played_san}**: {label}. 추천 수는 **{best_san}**입니다."


PIECE_NAMES_KO = {
    chess.PAWN: "폰",
    chess.KNIGHT: "나이트",
    chess.BISHOP: "비숍",
    chess.ROOK: "룩",
    chess.QUEEN: "퀸",
    chess.KING: "킹",
}

PIECE_VALUES_CP = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

CENTER_SQUARES = {chess.D4, chess.E4, chess.D5, chess.E5}
EXTENDED_CENTER_SQUARES = {
    chess.C3, chess.D3, chess.E3, chess.F3,
    chess.C4, chess.D4, chess.E4, chess.F4,
    chess.C5, chess.D5, chess.E5, chess.F5,
    chess.C6, chess.D6, chess.E6, chess.F6,
}


def piece_name_ko(piece_type: int | None) -> str:
    if piece_type is None:
        return "기물"
    return PIECE_NAMES_KO.get(piece_type, "기물")


def eval_gap_text(gap_cp: int) -> str:
    gap_cp = max(0, int(gap_cp))
    if gap_cp >= MATE_SCORE // 2:
        return "메이트 여부가 갈릴 만큼 큰 차이"
    if gap_cp < 15:
        return f"{gap_cp}cp 차이로 거의 동급"
    if gap_cp < 50:
        return f"{gap_cp}cp 차이로 근소하게 우세"
    if gap_cp < 120:
        return f"{gap_cp}cp 차이로 의미 있게 우세"
    if gap_cp < 250:
        return f"{gap_cp}cp 차이로 꽤 크게 우세"
    return f"{gap_cp}cp 차이로 압도적으로 우세"


def san_if_legal(board: chess.Board, move: chess.Move | None) -> str:
    if move is None or move not in board.legal_moves:
        return "-"
    return board.san(move)


def attacked_high_value_targets(after_board: chess.Board, move: chess.Move) -> list[str]:
    moved_piece = after_board.piece_at(move.to_square)
    if moved_piece is None:
        return []

    targets: list[tuple[int, str]] = []
    for square in after_board.attacks(move.to_square):
        piece = after_board.piece_at(square)
        if piece is None or piece.color == moved_piece.color or piece.piece_type == chess.KING:
            continue
        value = PIECE_VALUES_CP.get(piece.piece_type, 0)
        if value >= PIECE_VALUES_CP[chess.KNIGHT]:
            targets.append((value, f"{piece_name_ko(piece.piece_type)}({chess.square_name(square)})"))

    targets.sort(reverse=True)
    return [name for _, name in targets[:2]]


def pv_followup_hint(board: chess.Board, pv: list[chess.Move]) -> str | None:
    """PV 안에서 '상대 응수 뒤에도 이어지는 전술'을 짧게 설명합니다."""
    if len(pv) < 3:
        return None

    temp = board.copy(stack=False)
    for move in pv[:2]:
        if move not in temp.legal_moves:
            return None
        temp.push(move)

    followup = pv[2]
    if followup not in temp.legal_moves:
        return None

    tags: list[str] = []
    if temp.gives_check(followup):
        tags.append("체크")
    if temp.is_capture(followup):
        captured = temp.piece_at(followup.to_square)
        if captured is None and temp.is_en_passant(followup):
            captured_name = "폰"
        else:
            captured_name = piece_name_ko(captured.piece_type if captured else None)
        tags.append(f"{captured_name} 포획")

    if not tags:
        return None

    return f"엔진 예상 라인에서는 상대가 한 번 대응해도 **{temp.san(followup)}** 같은 {'/'.join(tags)} 전술이 이어집니다."


def best_move_reason_lines(board: chess.Board, infos: list[dict[str, Any]]) -> list[str]:
    if not infos:
        return []

    best_info = infos[0]
    pv = best_info.get("pv", [])
    if not pv:
        return []

    best_move = pv[0]
    if best_move not in board.legal_moves:
        return []

    lines: list[str] = []
    legal_count = board.legal_moves.count()
    moving_piece = board.piece_at(best_move.from_square)
    captured_piece = board.piece_at(best_move.to_square)
    if captured_piece is None and board.is_en_passant(best_move):
        captured_piece = chess.Piece(chess.PAWN, not board.turn)

    if legal_count == 1:
        lines.append("합법수가 하나뿐이라 사실상 강제수입니다.")

    if board.is_check():
        lines.append("현재 체크를 받은 상황이라, 먼저 킹의 안전을 해결합니다.")

    if board.gives_check(best_move):
        lines.append("체크를 걸어 상대 응수를 제한하고 템포를 얻습니다.")

    if board.is_capture(best_move):
        captured_name = piece_name_ko(captured_piece.piece_type if captured_piece else None)
        moving_name = piece_name_ko(moving_piece.piece_type if moving_piece else None)
        captured_value = PIECE_VALUES_CP.get(captured_piece.piece_type, 0) if captured_piece else 0
        moving_value = PIECE_VALUES_CP.get(moving_piece.piece_type, 0) if moving_piece else 0
        if captured_value > moving_value:
            lines.append(f"{moving_name}로 더 비싼 {captured_name}을 잡아 물질적으로 이득입니다.")
        else:
            lines.append(f"{captured_name}을 잡으면서 구체적인 전술/평가 이득을 유지합니다.")

    if best_move.promotion:
        lines.append(f"폰을 {piece_name_ko(best_move.promotion)}으로 승진시켜 결정적인 물질 이득을 만듭니다.")

    if board.is_castling(best_move):
        lines.append("캐슬링으로 킹 안전을 확보하고 룩을 중앙 싸움에 연결합니다.")

    after = board.copy(stack=False)
    best_san = board.san(best_move)
    after.push(best_move)

    if after.is_checkmate():
        lines.append("이 수 자체가 체크메이트입니다.")

    targets = attacked_high_value_targets(after, best_move)
    if targets:
        lines.append(f"착수 후 {', '.join(targets)}을 공격해 다음 수 위협을 만듭니다.")

    if (
        moving_piece is not None
        and moving_piece.piece_type in (chess.KNIGHT, chess.BISHOP)
        and board.fullmove_number <= 10
        and best_move.to_square in EXTENDED_CENTER_SQUARES
        and not board.is_capture(best_move)
    ):
        lines.append("초반 원칙상 기물을 전개하면서 중앙 영향력을 늘립니다.")

    if best_move.to_square in CENTER_SQUARES and not board.is_capture(best_move):
        lines.append("중앙 핵심 칸을 차지하거나 압박합니다.")

    followup = pv_followup_hint(board, pv)
    if followup:
        lines.append(followup)

    # 후보수 간 평가 차이도 이유의 핵심입니다.
    if len(infos) >= 2:
        best_cp = score_cp(best_info["score"], board.turn)
        alt_info = infos[1]
        alt_pv = alt_info.get("pv", [])
        alt_move = alt_pv[0] if alt_pv else None
        alt_san = san_if_legal(board, alt_move)
        alt_cp = score_cp(alt_info["score"], board.turn)
        gap = max(0, best_cp - alt_cp)
        lines.insert(0, f"2순위 후보 **{alt_san}**보다 착수자 기준 {eval_gap_text(gap)}입니다.")

    if not lines:
        lines.append(
            f"핵심은 전술적 한 방보다 엔진 예상 라인 전체입니다. **{best_san}** 이후의 PV에서 평가가 가장 안정적으로 유지됩니다."
        )

    # 너무 장황해지지 않게 상위 5개만 노출합니다.
    return lines[:5]


def best_move_explanation_markdown(board: chess.Board, infos: list[dict[str, Any]]) -> str | None:
    if not infos:
        return None

    best_info = infos[0]
    pv = best_info.get("pv", [])
    if not pv:
        return None

    best_move = pv[0]
    if best_move not in board.legal_moves:
        return None

    best_san = board.san(best_move)
    side_name = "백" if board.turn == chess.WHITE else "흑"
    eval_for_side = score_text(best_info["score"], board.turn)
    eval_for_white = score_text(best_info["score"], chess.WHITE)
    pv_line = pv_to_san(board, pv, max_plies=10)

    out = [
        f"**최선수: {best_san}**",
        f"- {side_name} 기준 평가: `{eval_for_side}` / 백 기준 평가: `{eval_for_white}`",
        f"- 엔진 예상 라인: `{pv_line}`",
    ]

    for line in best_move_reason_lines(board, infos):
        out.append(f"- {line}")

    if len(infos) >= 3:
        comparisons: list[str] = []
        best_cp = score_cp(best_info["score"], board.turn)
        for rank, info in enumerate(infos[1:3], start=2):
            alt_pv = info.get("pv", [])
            alt_move = alt_pv[0] if alt_pv else None
            alt_san = san_if_legal(board, alt_move)
            alt_cp = score_cp(info["score"], board.turn)
            gap = max(0, best_cp - alt_cp)
            comparisons.append(f"#{rank} {alt_san}: {score_text(info['score'], board.turn)} ({eval_gap_text(gap)})")
        if comparisons:
            out.append("- 후보 비교: " + " / ".join(comparisons))

    out.append(
        "\n작동 방식: Stockfish가 직접 한국어 설명을 쓰는 것은 아니고, 평가값·후보수·PV를 앱이 전술 단서로 해석합니다."
    )
    return "\n".join(out)


def render_best_move_explanation(board: chess.Board, infos: list[dict[str, Any]]) -> None:
    explanation = best_move_explanation_markdown(board, infos)
    if not explanation:
        return

    with st.expander("💡 왜 이 수가 최선인가", expanded=True):
        st.markdown(explanation)



def free_position_history() -> tuple[list[chess.Board], list[chess.Move], list[str]]:
    """직접 둔 게임의 모든 포지션을 시작 위치부터 반환합니다."""
    board = chess.Board()
    boards = [board.copy(stack=False)]
    moves: list[chess.Move] = []
    sans: list[str] = []

    valid_moves: list[str] = []
    for uci in st.session_state.get("free_moves", []):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        sans.append(board.san(move))
        moves.append(move)
        board.push(move)
        boards.append(board.copy(stack=False))
        valid_moves.append(uci)

    if valid_moves != st.session_state.get("free_moves", []):
        st.session_state.free_moves = valid_moves

    return boards, moves, sans


def position_cache_key(engine_path: str, board: chess.Board, depth: int, multipv: int) -> tuple[str, str, int, int]:
    return (engine_path, board.fen(), int(depth), int(multipv))


def analyse_position_cached(
    engine_path: str,
    board: chess.Board,
    depth: int,
    multipv: int = 3,
    force: bool = False,
) -> list[dict[str, Any]]:
    """세션 안에서 포지션별 엔진 결과를 캐시해 뒤로/앞으로 이동을 빠르게 합니다."""
    cache = st.session_state.setdefault("position_analysis_cache", {})
    key = position_cache_key(engine_path, board, depth, multipv)
    if force or key not in cache:
        cache[key] = analyse_current(engine_path, board, depth=depth, multipv=multipv)
    return cache[key]


def evaluation_bar_values(infos: list[dict[str, Any]] | None) -> tuple[str, float]:
    if not infos:
        return "0.00", 50.0

    score = infos[0].get("score")
    if score is None:
        return "0.00", 50.0

    white = score.pov(chess.WHITE)
    mate = white.mate()
    if mate is not None:
        label = f"M{mate:+d}"
        width = 95.0 if mate > 0 else 5.0
        return label, width

    cp = white.score()
    if cp is None:
        return "0.00", 50.0

    pawns = max(-6.0, min(6.0, cp / 100.0))
    width = max(5.0, min(95.0, 50.0 + pawns * 7.5))
    return f"{cp / 100:+.2f}", width


def render_evaluation_bar(
    infos: list[dict[str, Any]] | None,
    current_ply: int,
    max_ply: int,
    depth: int,
) -> None:
    label, width = evaluation_bar_values(infos)
    st.markdown(
        f"""
        <div class="eval-wrap">
          <div class="eval-bar">
            <div class="eval-white" style="width:{width:.2f}%"></div>
            <div class="eval-score" style="color:{'#f5f5f5' if width < 22 else '#222'}">{html_lib.escape(label)}</div>
          </div>
          <div class="eval-meta">
            <span>백 기준 평가</span>
            <span>수순 {current_ply}/{max_ply} · Depth {depth}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_move_strip(sans: list[str], active_ply: int) -> None:
    if not sans:
        st.markdown('<div class="move-strip"><span style="color:#918d88">아직 둔 수가 없습니다.</span></div>', unsafe_allow_html=True)
        return

    tokens: list[str] = []
    for idx, san in enumerate(sans, start=1):
        if idx % 2 == 1:
            tokens.append(f'<span class="move-number">{(idx + 1) // 2}.</span>')
        active = " active" if idx == active_ply else ""
        tokens.append(f'<span class="move-item{active}">{html_lib.escape(san)}</span>')

    st.markdown(f'<div class="move-strip">{" ".join(tokens)}</div>', unsafe_allow_html=True)


def set_free_view_ply(target: int) -> None:
    max_ply = len(st.session_state.get("free_moves", []))
    st.session_state.free_view_ply = max(0, min(int(target), max_ply))
    st.session_state.free_selected_square = None
    clear_free_analysis()


def analyse_current(
    engine_path: str,
    board: chess.Board,
    depth: int,
    multipv: int,
) -> list[dict[str, Any]]:
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        result = engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=multipv,
        )
        if isinstance(result, dict):
            return [result]
        return list(result)
    finally:
        engine.quit()


def analyse_full_game(
    engine_path: str,
    game: chess.pgn.Game,
    depth: int,
    progress_callback,
) -> pd.DataFrame:
    positions, moves, sans = game_positions(game)
    if not moves:
        return pd.DataFrame()

    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    rows: list[dict[str, Any]] = []

    try:
        # 각 position을 한 번씩만 분석해 이전/이후 평가를 재사용
        infos: list[dict[str, Any]] = []
        total_positions = len(positions)

        for idx, board in enumerate(positions):
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            infos.append(info)
            progress_callback((idx + 1) / total_positions)

        for idx, move in enumerate(moves):
            board_before = positions[idx]
            mover = board_before.turn

            before_info = infos[idx]
            after_info = infos[idx + 1]

            before_score = score_cp(before_info["score"], mover)
            after_score = score_cp(after_info["score"], mover)
            loss_cp = max(0, before_score - after_score)

            label, icon = classify_loss(loss_cp)
            pv = before_info.get("pv", [])
            best_move = pv[0] if pv else None
            best_san = (
                board_before.san(best_move)
                if best_move is not None and best_move in board_before.legal_moves
                else "-"
            )
            best_reason = " / ".join(best_move_reason_lines(board_before, [before_info]))

            fullmove = board_before.fullmove_number
            side = "백" if mover == chess.WHITE else "흑"
            move_no = f"{fullmove}." if mover == chess.WHITE else f"{fullmove}..."

            rows.append(
                {
                    "Ply": idx + 1,
                    "수": f"{move_no} {sans[idx]}",
                    "진영": side,
                    "판정": f"{icon} {label}",
                    "CPL": loss_cp,
                    "백 기준 평가 전": score_text(before_info["score"], chess.WHITE),
                    "백 기준 평가 후": score_text(after_info["score"], chess.WHITE),
                    "추천 수": best_san,
                    "추천 라인": pv_to_san(board_before, pv, max_plies=8),
                    "추천 이유": best_reason,
                    "코치 설명": coach_message(
                        board_before,
                        move,
                        best_move,
                        loss_cp,
                        label,
                    ),
                }
            )
    finally:
        engine.quit()

    return pd.DataFrame(rows)



PIECE_SYMBOLS = {
    (chess.WHITE, chess.KING): "♔",
    (chess.WHITE, chess.QUEEN): "♕",
    (chess.WHITE, chess.ROOK): "♖",
    (chess.WHITE, chess.BISHOP): "♗",
    (chess.WHITE, chess.KNIGHT): "♘",
    (chess.WHITE, chess.PAWN): "♙",
    (chess.BLACK, chess.KING): "♚",
    (chess.BLACK, chess.QUEEN): "♛",
    (chess.BLACK, chess.ROOK): "♜",
    (chess.BLACK, chess.BISHOP): "♝",
    (chess.BLACK, chess.KNIGHT): "♞",
    (chess.BLACK, chess.PAWN): "♟",
}

PROMOTION_MAP = {
    "퀸": chess.QUEEN,
    "룩": chess.ROOK,
    "비숍": chess.BISHOP,
    "나이트": chess.KNIGHT,
}


def free_board_from_state() -> chess.Board:
    board = chess.Board()
    for uci in st.session_state.free_moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            break
        board.push(move)
    return board


def free_san_history() -> list[str]:
    board = chess.Board()
    history: list[str] = []
    for uci in st.session_state.free_moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            break
        history.append(board.san(move))
        board.push(move)
    return history


def free_pgn_text() -> str:
    game = chess.pgn.Game()
    game.headers["Event"] = "Direct Play"
    game.headers["White"] = "White"
    game.headers["Black"] = "Black"
    game.headers["Result"] = "*"
    node = game
    board = chess.Board()
    for uci in st.session_state.free_moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            break
        node = node.add_variation(move)
        board.push(move)
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def clear_free_analysis() -> None:
    st.session_state.free_infos = None
    st.session_state.free_analysis_fen = None
    st.session_state.free_analysis_depth = None


def undo_free_move() -> bool:
    """직접 두기 탭에서 마지막 착수를 안전하게 취소합니다.

    Streamlit Cloud/mobile 환경에서는 사용자가 버튼을 빠르게 두 번 누르거나
    버튼 이벤트가 지연되어 도착할 수 있습니다. 그 경우 렌더링 시점에는
    버튼이 활성화되어 있었어도 실행 시점의 free_moves가 이미 비어 있을 수
    있으므로 pop() 전에 반드시 다시 확인합니다.
    """
    moves = st.session_state.get("free_moves", [])
    if not isinstance(moves, list):
        moves = list(moves) if moves else []
        st.session_state.free_moves = moves

    st.session_state.free_selected_square = None
    st.session_state.free_pending_review = None
    st.session_state.free_last_review = None

    if not moves:
        st.session_state.free_message = "취소할 수가 없습니다."
        clear_free_analysis()
        return False

    moves.pop()
    st.session_state.free_view_ply = len(moves)
    st.session_state.free_message = "한 수 취소"
    clear_free_analysis()
    return True


def make_free_move(board: chess.Board, to_square: int, promotion_piece: int) -> bool:
    selected = st.session_state.free_selected_square
    if selected is None:
        piece = board.piece_at(to_square)
        if piece is not None and piece.color == board.turn:
            st.session_state.free_selected_square = to_square
        return False

    if to_square == selected:
        st.session_state.free_selected_square = None
        return False

    clicked_piece = board.piece_at(to_square)
    if clicked_piece is not None and clicked_piece.color == board.turn:
        st.session_state.free_selected_square = to_square
        return False

    moving_piece = board.piece_at(selected)
    promotion = None
    if (
        moving_piece is not None
        and moving_piece.piece_type == chess.PAWN
        and chess.square_rank(to_square) in (0, 7)
    ):
        promotion = promotion_piece

    move = chess.Move(selected, to_square, promotion=promotion)
    if move not in board.legal_moves:
        st.session_state.free_message = "그 수는 둘 수 없습니다."
        st.session_state.free_selected_square = None
        return False

    before_fen = board.fen()
    san = board.san(move)
    mover = board.turn
    before_info = None
    before_infos = None
    if (
        st.session_state.free_infos
        and st.session_state.free_analysis_fen == before_fen
    ):
        before_infos = list(st.session_state.free_infos)
        before_info = before_infos[0]

    # 과거 수순에서 새 수를 두면 그 지점 이후의 기존 수순을 버리고
    # 새로운 변형으로 이어갑니다. 체스 분석 앱의 일반적인 분기 동작입니다.
    branch_ply = max(0, min(
        int(st.session_state.get("free_view_ply", len(st.session_state.free_moves))),
        len(st.session_state.free_moves),
    ))
    branched = branch_ply < len(st.session_state.free_moves)
    if branched:
        st.session_state.free_moves = st.session_state.free_moves[:branch_ply]

    board.push(move)
    st.session_state.free_moves.append(move.uci())
    st.session_state.free_view_ply = len(st.session_state.free_moves)
    st.session_state.free_selected_square = None
    st.session_state.free_message = (
        f"{san} 착수 · 이 위치부터 새 수순으로 변경"
        if branched
        else f"{san} 착수"
    )
    st.session_state.free_last_review = None
    st.session_state.free_pending_review = {
        "before_fen": before_fen,
        "after_fen": board.fen(),
        "move_uci": move.uci(),
        "san": san,
        "mover": mover,
        "before_info": before_info,
        "before_infos": before_infos,
    }
    clear_free_analysis()
    return True


def board_payload(board: chess.Board) -> dict[str, str]:
    """클릭형 보드 컴포넌트에 넘길 칸별 기물 정보를 만듭니다."""
    pieces: dict[str, str] = {}
    for square, piece in board.piece_map().items():
        pieces[chess.square_name(square)] = PIECE_SYMBOLS[(piece.color, piece.piece_type)]
    return pieces


def render_clickable_board(
    board: chess.Board,
    orientation: chess.Color,
    promotion_piece: int,
    last_move: chess.Move | None = None,
    interactive: bool = True,
) -> None:
    """모바일에서도 깨지지 않는 단일 HTML 컴포넌트 체스판입니다."""
    selected = st.session_state.free_selected_square if interactive else None
    legal_targets: set[int] = set()
    if selected is not None:
        legal_targets = {
            move.to_square
            for move in board.legal_moves
            if move.from_square == selected
        }

    click = clickable_chessboard(
        fen=board.fen(),
        pieces=board_payload(board),
        orientation="white" if orientation == chess.WHITE else "black",
        turn="white" if board.turn == chess.WHITE else "black",
        selected=chess.square_name(selected) if selected is not None else "",
        legal_targets=[chess.square_name(square) for square in sorted(legal_targets)],
        last_move=(
            [
                chess.square_name(last_move.from_square),
                chess.square_name(last_move.to_square),
            ]
            if last_move is not None
            else []
        ),
        interactive=interactive,
        key="free_clickable_chessboard",
        default=None,
    )

    if not interactive or not isinstance(click, dict):
        return

    click_id = str(click.get("id", ""))
    square_name = str(click.get("square", ""))
    if not click_id or click_id == st.session_state.free_processed_click_id:
        return
    if square_name not in chess.SQUARE_NAMES:
        return

    st.session_state.free_processed_click_id = click_id
    make_free_move(board, chess.parse_square(square_name), promotion_piece)
    st.rerun()


def build_free_review(current_infos: list[dict[str, Any]], board_after: chess.Board) -> None:
    pending = st.session_state.free_pending_review
    if not pending or pending.get("after_fen") != board_after.fen():
        return

    before_info = pending.get("before_info")
    if before_info is None or not current_infos:
        st.session_state.free_last_review = {
            "title": f"{pending['san']} 분석",
            "body": "이전 포지션 평가가 없어 이번 수의 CPL 판정은 생략했습니다.",
        }
        st.session_state.free_pending_review = None
        return

    mover = pending["mover"]
    after_info = current_infos[0]
    before_score = score_cp(before_info["score"], mover)
    after_score = score_cp(after_info["score"], mover)
    loss_cp = max(0, before_score - after_score)
    label, icon = classify_loss(loss_cp)

    before_board = chess.Board(pending["before_fen"])
    played_move = chess.Move.from_uci(pending["move_uci"])
    pv = before_info.get("pv", [])
    best_move = pv[0] if pv else None
    best_san = (
        before_board.san(best_move)
        if best_move is not None and best_move in before_board.legal_moves
        else "-"
    )

    before_infos = pending.get("before_infos") or ([before_info] if before_info else [])
    st.session_state.free_last_review = {
        "title": f"{icon} {pending['san']} · {label} · CPL {loss_cp}",
        "body": coach_message(
            before_board,
            played_move,
            best_move,
            loss_cp,
            label,
        ),
        "best": best_san,
        "line": pv_to_san(before_board, pv, max_plies=8),
        "best_reason": best_move_reason_lines(before_board, before_infos),
    }
    st.session_state.free_pending_review = None

def init_state() -> None:
    defaults = {
        "games": [],
        "source_id": None,
        "selected_game": 0,
        "ply": 0,
        "full_analysis": None,
        "full_analysis_game": None,
        "fen_game": None,
        "free_moves": [],
        "free_selected_square": None,
        "free_infos": None,
        "free_analysis_fen": None,
        "free_analysis_depth": None,
        "free_pending_review": None,
        "free_last_review": None,
        "free_message": "",
        "free_processed_click_id": None,
        "free_view_ply": 0,
        "position_analysis_cache": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# -----------------------------
# 제목
# -----------------------------
st.title("♟️ Stockfish Chess Review")
st.caption("직접 수를 두면서 실시간 Stockfish 분석을 받거나, PGN 게임 전체를 복기합니다.")


# -----------------------------
# 사이드바: 엔진 / 설정
# -----------------------------
with st.sidebar:
    st.header("⚙️ 설정")

    auto_engine = detect_stockfish()
    default_engine = auto_engine or ""
    engine_input = st.text_input(
        "Stockfish 실행 파일 경로",
        value=default_engine,
        placeholder=r"C:\...\stockfish.exe",
        help="같은 폴더 또는 PATH에 있으면 자동 탐색합니다.",
    )

    engine_ok, engine_path_or_error = validate_engine_path(engine_input)
    if engine_ok:
        engine_path = engine_path_or_error
        st.success(f"엔진 연결 준비 완료\n\n`{Path(engine_path).name}`")
    else:
        engine_path = ""
        st.warning(engine_path_or_error)

    depth = st.slider(
        "분석 Depth",
        min_value=8,
        max_value=22,
        value=DEFAULT_DEPTH,
        step=1,
        help="높을수록 깊게 분석하지만 전체 게임 분석 시간이 늘어납니다.",
    )

    orientation_name = st.radio("체스판 방향", ["백", "흑"], horizontal=True)
    orientation = chess.WHITE if orientation_name == "백" else chess.BLACK

    st.divider()
    st.markdown("**설치 명령어**")
    st.code("pip install streamlit python-chess pandas", language="bash")
    st.code("streamlit run chess_app.py", language="bash")
    st.caption("Stockfish는 별도 UCI 엔진 실행 파일이 필요합니다.")


# -----------------------------
# 입력
# -----------------------------
play_tab, input_tab, fen_tab = st.tabs(["♟️ 직접 두기", "📂 PGN 불러오기", "🧩 FEN 분석"])

with play_tab:
    st.subheader("♟️ 직접 두기 + 수순 복기 + 실시간 Stockfish")
    st.caption("뒤로/앞으로 이동하면 해당 포지션의 점수가 표시됩니다. 과거 위치에서도 착수할 수 있으며, 그 경우 이후 수순은 새 변형으로 교체됩니다.")

    control1, control2, control3, control4 = st.columns([1, 1, 1, 1])
    with control1:
        auto_analyse = st.toggle("매 수 자동 분석", value=True, key="free_auto_analyse")
    with control2:
        promotion_name = st.selectbox("프로모션", list(PROMOTION_MAP), index=0)
        promotion_piece = PROMOTION_MAP[promotion_name]
    with control3:
        if st.button("↩ 한 수 취소", use_container_width=True, disabled=not st.session_state.free_moves):
            undo_free_move()
            st.rerun()
    with control4:
        if st.button("🔄 새 게임", use_container_width=True):
            st.session_state.free_moves = []
            st.session_state.free_view_ply = 0
            st.session_state.free_selected_square = None
            st.session_state.free_pending_review = None
            st.session_state.free_last_review = None
            st.session_state.free_message = "새 게임 시작"
            clear_free_analysis()
            st.rerun()

    free_boards, free_history_moves, san_history = free_position_history()
    max_free_ply = len(free_history_moves)
    st.session_state.free_view_ply = max(0, min(st.session_state.free_view_ply, max_free_ply))
    view_ply = st.session_state.free_view_ply
    free_board = free_boards[view_ply]
    free_last_move = free_history_moves[view_ply - 1] if view_ply > 0 else None
    at_latest = view_ply == max_free_ply

    manual_analyse = st.button(
        "🔄 현재 위치 다시 분석",
        use_container_width=True,
        disabled=not engine_ok,
        key="free_manual_analysis_top",
    )

    viewed_infos: list[dict[str, Any]] | None = None
    should_analyse = engine_ok and (auto_analyse or manual_analyse)
    if should_analyse:
        try:
            with st.spinner(f"수순 {view_ply}/{max_free_ply} Stockfish 분석 중..."):
                viewed_infos = analyse_position_cached(
                    engine_path,
                    free_board,
                    depth=depth,
                    multipv=3,
                    force=manual_analyse,
                )
            st.session_state.free_infos = viewed_infos
            st.session_state.free_analysis_fen = free_board.fen()
            st.session_state.free_analysis_depth = depth
            if at_latest:
                build_free_review(viewed_infos, free_board)
        except Exception as exc:
            st.error(f"엔진 분석 실패: {exc}")
    elif (
        st.session_state.free_infos
        and st.session_state.free_analysis_fen == free_board.fen()
        and st.session_state.free_analysis_depth == depth
    ):
        viewed_infos = st.session_state.free_infos

    # 사용자가 요청한 핵심: 어느 수순을 보고 있든 상단에 그 포지션 점수 표시
    render_evaluation_bar(viewed_infos, view_ply, max_free_ply, depth)

    free_board_col, free_analysis_col = st.columns([1.06, 0.94], gap="large")
    with free_board_col:
        turn_text = "백" if free_board.turn == chess.WHITE else "흑"
        status_text = "체크메이트" if free_board.is_checkmate() else "스테일메이트" if free_board.is_stalemate() else "체크" if free_board.is_check() else f"{turn_text} 차례"
        st.markdown(f"### {status_text}")

        if not at_latest:
            st.markdown(
                '<div class="reviewing-note">과거 수순입니다. 여기서 새 수를 두면 이후 수순은 삭제되고 새 변형으로 이어집니다.</div>',
                unsafe_allow_html=True,
            )

        render_clickable_board(
            free_board,
            orientation,
            promotion_piece,
            last_move=free_last_move,
            interactive=True,
        )
        render_move_strip(san_history, view_ply)

        nav1, nav2, nav_mid, nav3, nav4 = st.columns([1, 1, 1.1, 1, 1])
        if nav1.button("⏮", use_container_width=True, disabled=view_ply == 0, key="free_first"):
            set_free_view_ply(0)
            st.rerun()
        if nav2.button("◀", use_container_width=True, disabled=view_ply == 0, key="free_back"):
            set_free_view_ply(view_ply - 1)
            st.rerun()
        nav_mid.markdown(
            f"<div style='text-align:center;padding-top:9px;font-weight:850'>{view_ply} / {max_free_ply}</div>",
            unsafe_allow_html=True,
        )
        if nav3.button("▶", use_container_width=True, disabled=view_ply == max_free_ply, key="free_forward"):
            set_free_view_ply(view_ply + 1)
            st.rerun()
        if nav4.button("⏭", use_container_width=True, disabled=view_ply == max_free_ply, key="free_end"):
            set_free_view_ply(max_free_ply)
            st.rerun()

        if st.session_state.free_message and at_latest:
            st.caption(st.session_state.free_message)

        st.download_button(
            "PGN 저장",
            data=free_pgn_text().encode("utf-8"),
            file_name="direct_game.pgn",
            mime="application/x-chess-pgn",
            use_container_width=True,
        )

    with free_analysis_col:
        st.subheader("🔬 Stockfish 분석")

        if not engine_ok:
            st.error("Stockfish 실행 파일을 연결해야 분석할 수 있습니다.")
        elif viewed_infos:
            top = viewed_infos[0]
            side_name = "백" if free_board.turn == chess.WHITE else "흑"
            m1, m2 = st.columns(2)
            m1.metric("백 기준 평가", score_text(top["score"], chess.WHITE))
            m2.metric(f"{side_name} 기준 평가", score_text(top["score"], free_board.turn))

            for rank, info in enumerate(viewed_infos, start=1):
                pv = info.get("pv", [])
                first_move = pv[0] if pv else None
                first_san = (
                    free_board.san(first_move)
                    if first_move is not None and first_move in free_board.legal_moves
                    else "-"
                )
                st.markdown(
                    f"""
                    <div class="review-box">
                        <b>#{rank} {first_san}</b> · 백 기준 {score_text(info['score'], chess.WHITE)}<br>
                        <span class="small-muted">{pv_to_san(free_board, pv, max_plies=10)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            render_best_move_explanation(free_board, viewed_infos)
        else:
            st.info("자동 분석을 켜거나 ‘현재 위치 다시 분석’을 누르면 점수와 추천 수가 표시됩니다.")

        review = st.session_state.free_last_review
        if review and at_latest:
            st.subheader("🎯 방금 둔 수")
            st.markdown(f"**{review['title']}**")
            st.markdown(review["body"])
            if review.get("best"):
                st.caption(f"추천 수: {review['best']} · {review.get('line', '-')}")
            if review.get("best_reason"):
                with st.expander("추천 수가 더 나은 이유", expanded=False):
                    for reason in review["best_reason"]:
                        st.markdown(f"- {reason}")

with input_tab:
    uploaded = st.file_uploader(
        "PGN 파일 업로드",
        type=["pgn"],
        accept_multiple_files=False,
    )

    pgn_text = st.text_area(
        "또는 PGN 텍스트 붙여넣기",
        height=120,
        placeholder='[Event "..."]\n[White "..."]\n[Black "..."]\n\n1. e4 e5 2. Nf3 Nc6 ...',
    )

    raw: bytes | None = None
    source_id: tuple[str, int] | None = None

    if uploaded is not None:
        raw = uploaded.getvalue()
        source_id = (uploaded.name, hash(raw))
    elif pgn_text.strip():
        raw = pgn_text.encode("utf-8")
        source_id = ("pasted_pgn", hash(raw))

    if raw is not None and source_id != st.session_state.source_id:
        try:
            parsed = parse_pgn_bytes(raw)
            if not parsed:
                st.error("유효한 게임을 PGN에서 찾지 못했습니다.")
            else:
                st.session_state.games = parsed
                st.session_state.source_id = source_id
                st.session_state.selected_game = 0
                st.session_state.ply = 0
                st.session_state.full_analysis = None
                st.session_state.full_analysis_game = None
                st.success(f"{len(parsed)}개 게임을 불러왔습니다.")
        except Exception as exc:
            st.error(f"PGN 파싱 실패: {exc}")

with fen_tab:
    fen_text = st.text_input(
        "FEN",
        placeholder="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    )
    if st.button("FEN 적용", use_container_width=True):
        try:
            board = chess.Board(fen_text.strip())
            game = chess.pgn.Game()
            game.setup(board)
            game.headers["Event"] = "FEN Position"
            game.headers["White"] = "White"
            game.headers["Black"] = "Black"
            game.headers["Result"] = "*"

            st.session_state.games = [game]
            st.session_state.source_id = ("fen", hash(fen_text.strip()))
            st.session_state.selected_game = 0
            st.session_state.ply = 0
            st.session_state.full_analysis = None
            st.session_state.full_analysis_game = None
            st.rerun()
        except ValueError as exc:
            st.error(f"FEN 오류: {exc}")


# -----------------------------
# 게임 화면
# -----------------------------
games: list[chess.pgn.Game] = st.session_state.games

if not games:
    st.info("PGN 복기를 하려면 위 탭에서 `.pgn` 파일을 업로드하거나 FEN을 입력하세요. 직접 두기는 첫 번째 탭에서 바로 사용할 수 있습니다.")
    st.stop()

labels = [game_label(game, i) for i, game in enumerate(games)]
selected_game = st.selectbox(
    "게임 선택",
    range(len(games)),
    index=min(st.session_state.selected_game, len(games) - 1),
    format_func=lambda i: labels[i],
)

if selected_game != st.session_state.selected_game:
    st.session_state.selected_game = selected_game
    st.session_state.ply = 0
    st.session_state.full_analysis = None
    st.session_state.full_analysis_game = None
    st.rerun()

game = games[selected_game]
positions, moves, sans = game_positions(game)
max_ply = len(moves)
st.session_state.ply = min(st.session_state.ply, max_ply)

headers = game.headers
meta1, meta2, meta3, meta4 = st.columns(4)
meta1.metric("White", headers.get("White", "White"))
meta2.metric("Black", headers.get("Black", "Black"))
meta3.metric("Result", headers.get("Result", "*"))
meta4.metric("Moves", max_ply)

st.divider()

board_col, review_col = st.columns([1.05, 1], gap="large")

with board_col:
    ply = st.session_state.ply
    board = positions[ply]
    last_move = moves[ply - 1] if ply > 0 else None

    pgn_infos = None
    if engine_ok:
        try:
            pgn_infos = analyse_position_cached(engine_path, board, depth=depth, multipv=3)
        except Exception as exc:
            st.caption(f"현재 수순 자동 평가는 계산하지 못했습니다: {exc}")

    render_evaluation_bar(pgn_infos, ply, max_ply, depth)
    render_board(board, last_move, orientation)

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("⏮", use_container_width=True, disabled=ply == 0):
        st.session_state.ply = 0
        st.rerun()
    if b2.button("◀", use_container_width=True, disabled=ply == 0):
        st.session_state.ply -= 1
        st.rerun()
    b3.markdown(
        f"<div style='text-align:center;padding-top:8px'><b>{ply} / {max_ply}</b></div>",
        unsafe_allow_html=True,
    )
    if b4.button("▶", use_container_width=True, disabled=ply == max_ply):
        st.session_state.ply += 1
        st.rerun()
    if b5.button("⏭", use_container_width=True, disabled=ply == max_ply):
        st.session_state.ply = max_ply
        st.rerun()

    slider_ply = st.slider(
        "수 위치",
        min_value=0,
        max_value=max_ply,
        value=ply,
        step=1,
        key=f"ply_slider_{selected_game}_{max_ply}",
    )
    if slider_ply != st.session_state.ply:
        st.session_state.ply = slider_ply
        st.rerun()

    if ply == 0:
        st.caption("게임 시작 위치")
    else:
        move_board = positions[ply - 1]
        move_no = move_board.fullmove_number
        prefix = f"{move_no}." if move_board.turn == chess.WHITE else f"{move_no}..."
        st.markdown(f"### 현재 수: `{prefix} {sans[ply - 1]}`")

with review_col:
    st.subheader("🔬 현재 포지션 분석")

    if not engine_ok:
        st.error("Stockfish 실행 파일을 연결해야 분석할 수 있습니다.")
    else:
        if st.button("현재 포지션 분석", type="primary", use_container_width=True):
            with st.spinner("Stockfish 분석 중..."):
                try:
                    current_infos = analyse_current(
                        engine_path,
                        board,
                        depth=depth,
                        multipv=3,
                    )
                    st.session_state["current_infos"] = current_infos
                    st.session_state["current_fen"] = board.fen()
                    st.session_state["current_depth"] = depth
                except Exception as exc:
                    st.error(f"엔진 분석 실패: {exc}")

        infos = pgn_infos or st.session_state.get("current_infos")
        same_position = pgn_infos is not None or st.session_state.get("current_fen") == board.fen()
        same_depth = pgn_infos is not None or st.session_state.get("current_depth") == depth

        if infos and same_position and same_depth:
            top = infos[0]
            score = top.get("score")
            if score is not None:
                side_name = "백" if board.turn == chess.WHITE else "흑"
                m1, m2 = st.columns(2)
                m1.metric("백 기준 평가", score_text(score, chess.WHITE))
                m2.metric(f"{side_name} 기준 평가", score_text(score, board.turn))

            for rank, info in enumerate(infos, start=1):
                pv = info.get("pv", [])
                first_move = pv[0] if pv else None
                first_san = (
                    board.san(first_move)
                    if first_move is not None and first_move in board.legal_moves
                    else "-"
                )
                line = pv_to_san(board, pv, max_plies=10)
                eval_text = score_text(info["score"], chess.WHITE)

                st.markdown(
                    f"""
                    <div class="review-box">
                        <b>#{rank} {first_san}</b> · 백 기준 {eval_text}<br>
                        <span class="small-muted">{line}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            render_best_move_explanation(board, infos)

    st.subheader("📝 기보")
    if sans:
        tokens: list[str] = []
        temp = game.board()

        for idx, san in enumerate(sans):
            if temp.turn == chess.WHITE:
                tokens.append(f"{temp.fullmove_number}.")
            tokens.append(f"**{san}**" if idx + 1 == ply else san)
            temp.push(moves[idx])

        st.markdown(" ".join(tokens))
    else:
        st.caption("메인라인 수가 없습니다.")


# -----------------------------
# 전체 게임 분석
# -----------------------------
st.divider()
st.header("📊 전체 게임 자동 분석")

if not engine_ok:
    st.warning("전체 분석을 하려면 먼저 Stockfish 실행 파일을 연결하세요.")
elif not moves:
    st.info("분석할 게임 수가 없습니다.")
else:
    st.caption(
        "각 포지션을 Stockfish로 분석해, 실제 수를 둔 진영 기준 평가 손실(CPL)을 계산합니다. "
        "판정 구간은 이 앱의 초보자용 휴리스틱입니다."
    )

    if st.button("🚀 전체 게임 분석 시작", type="primary", use_container_width=True):
        progress = st.progress(0, text="Stockfish 분석 준비 중...")

        def update_progress(value: float) -> None:
            progress.progress(
                min(100, max(0, int(value * 100))),
                text=f"포지션 분석 중... {int(value * 100)}%",
            )

        try:
            df = analyse_full_game(
                engine_path,
                game,
                depth=depth,
                progress_callback=update_progress,
            )
            st.session_state.full_analysis = df
            st.session_state.full_analysis_game = selected_game
            st.session_state.full_analysis_depth = depth
            progress.progress(100, text="분석 완료")
        except Exception as exc:
            st.error(f"전체 분석 실패: {exc}")

    df = st.session_state.full_analysis
    analysis_matches = (
        isinstance(df, pd.DataFrame)
        and st.session_state.full_analysis_game == selected_game
        and st.session_state.get("full_analysis_depth") == depth
    )

    if analysis_matches and not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("평균 CPL", f"{df['CPL'].mean():.1f}")
        c2.metric("부정확", int(df["판정"].str.contains("부정확").sum()))
        c3.metric("실수", int(df["판정"].str.contains("실수").sum()))
        c4.metric("블런더", int(df["판정"].str.contains("블런더").sum()))

        st.dataframe(
            df[
                [
                    "수",
                    "진영",
                    "판정",
                    "CPL",
                    "백 기준 평가 전",
                    "백 기준 평가 후",
                    "추천 수",
                    "추천 라인",
                    "추천 이유",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=500,
        )

        st.subheader("🎯 복습 우선순위")
        mistakes = df[df["CPL"] >= 50].sort_values("CPL", ascending=False).head(10)

        if mistakes.empty:
            st.success("큰 평가 손실이 거의 없습니다. 깔끔한 게임입니다.")
        else:
            for _, row in mistakes.iterrows():
                st.markdown(
                    f"""
                    <div class="review-box">
                        <b>{row['수']} · {row['판정']} · CPL {row['CPL']}</b><br>
                        {row['코치 설명']}<br>
                        <span class="small-muted">
                            추천: {row['추천 수']} · {row['추천 라인']}<br>
                            이유: {row.get('추천 이유', '')}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        csv_data = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 분석 결과 저장",
            data=csv_data,
            file_name="chess_analysis.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.caption(
            "참고: 엔진 평가는 분석 Depth와 Stockfish 버전에 따라 달라질 수 있습니다. "
            "또한 이 앱의 '정확/좋음/부정확/실수/블런더' 구간은 단순 CPL 휴리스틱입니다."
        )
