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

import io
import os
import shutil
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
    </style>
    """,
    unsafe_allow_html=True,
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


def init_state() -> None:
    defaults = {
        "games": [],
        "source_id": None,
        "selected_game": 0,
        "ply": 0,
        "full_analysis": None,
        "full_analysis_game": None,
        "fen_game": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# -----------------------------
# 제목
# -----------------------------
st.title("♟️ Stockfish Chess Review")
st.caption("PGN을 불러와 수를 넘겨 보고, Stockfish로 현재 포지션과 전체 게임을 분석합니다.")


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
input_tab, fen_tab = st.tabs(["📂 PGN 불러오기", "🧩 FEN 분석"])

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
    st.info("위에서 `.pgn` 파일을 업로드하거나 PGN/FEN을 입력하세요.")
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

        infos = st.session_state.get("current_infos")
        same_position = st.session_state.get("current_fen") == board.fen()
        same_depth = st.session_state.get("current_depth") == depth

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
                            추천: {row['추천 수']} · {row['추천 라인']}
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
