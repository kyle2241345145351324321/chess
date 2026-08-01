import sys
import os
import tkinter as tk
from tkinter import messagebox
import chess
import os
import subprocess
import chess.engine
from dataclasses import dataclass
from typing import Optional
import time
from datetime import datetime
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

engine_path = os.path.join(base_path, "stockfish", "stockfish-macos-x86-64")


@dataclass
class Evaluation:
    """Structured evaluation data from engine"""
    type: str  # 'cp' for centipawns, 'mate' for mate
    value: int  # For cp: centipawns (positive = white advantage), for mate: moves to mate (positive = white mating)
    white_advantage: bool  # True if position favors white, False if favors black
    display_text: str  # Formatted text for display

    @classmethod
    def from_score(cls, score, board_turn=None):
        """Create Evaluation from engine score"""
        if score.is_mate():
            moves_to_mate = score.mate()
            white_advantage = moves_to_mate > 0

            if moves_to_mate > 0:
                display_text = f"Mate in {moves_to_mate}"
            else:
                display_text = f"Mate in {-moves_to_mate}"

            return cls(
                type='mate',
                value=moves_to_mate,
                white_advantage=white_advantage,
                display_text=display_text
            )
        else:
            cp_score = score.score()
            white_advantage = cp_score > 0
            display_text = f"{cp_score / 100:+.2f}"

            return cls(
                type='cp',
                value=cp_score,
                white_advantage=white_advantage,
                display_text=display_text
            )


class PlayerStats:
    """Track player statistics"""

    def __init__(self):
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.total_moves = 0
        self.captures = 0
        self.checkmates = 0
        self.game_start_time = None
        self.total_play_time = 0

    def start_game(self):
        self.game_start_time = time.time()

    def end_game(self, result):
        self.games_played += 1
        if result == "win":
            self.wins += 1
        elif result == "loss":
            self.losses += 1
        elif result == "draw":
            self.draws += 1

        if self.game_start_time:
            self.total_play_time += time.time() - self.game_start_time
            self.game_start_time = None

    def add_move(self, is_capture=False):
        self.total_moves += 1
        if is_capture:
            self.captures += 1

    def add_checkmate(self):
        self.checkmates += 1

    def get_win_rate(self):
        if self.games_played == 0:
            return 0
        return (self.wins / self.games_played) * 100


class ChessGame:
    class StockfishAI:
        def __init__(self, path, elo=1200):
            self.engine = chess.engine.SimpleEngine.popen_uci(path)
            self.min_elo = 1320  # Stockfish 最小有效 ELO
            self.set_elo(elo)

        def set_elo(self, elo):
            self.elo = int(elo)
            if self.elo >= self.min_elo:
                self.engine.configure({
                    "UCI_LimitStrength": True,
                    "UCI_Elo": self.elo
                })
                self.use_depth_limit = False
            else:
                self.engine.configure({"UCI_LimitStrength": False})
                self.use_depth_limit = True

        def get_move(self, board):
            if self.use_depth_limit:
                if self.elo <= 400:
                    limit = chess.engine.Limit(depth=1)
                elif self.elo <= 800:
                    limit = chess.engine.Limit(depth=2)
                else:
                    limit = chess.engine.Limit(depth=3)
            else:
                if self.elo < 1500:
                    limit = chess.engine.Limit(time=0.1)
                elif self.elo < 2000:
                    limit = chess.engine.Limit(time=0.2)
                else:
                    limit = chess.engine.Limit(time=0.3)

            result = self.engine.play(board, limit)
            return result.move

        def get_evaluation(self, board) -> Evaluation:
            try:
                info = self.engine.analyse(board, chess.engine.Limit(time=0.1))
                score = info["score"].pov(chess.WHITE)
                return Evaluation.from_score(score)
            except Exception as e:
                print(f"Evaluation error: {e}")
                return Evaluation(
                    type='cp',
                    value=0,
                    white_advantage=True,
                    display_text="0.00"
                )

        def quit(self):
            self.engine.quit()

    def play_sound(self, filename):
        if hasattr(self, 'sound_var') and not self.sound_var.get():
            return
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "sounds", filename)
        try:
            subprocess.Popen(["afplay", path])
        except:
            pass

    def play_move_sound(self, move, is_capture, is_castle, is_promotion):
        if self.board.is_checkmate():
            self.play_sound("checkmate.wav")
            return

        if self.board.is_stalemate() or self.board.is_insufficient_material():
            self.play_sound("draw.wav")
            return

        if is_promotion:
            self.play_sound("promotion.wav")
            return

        if is_castle:
            self.play_sound("castle.wav")
            return

        if is_capture:
            self.play_sound("capture.wav")
            return

        if self.board.is_check():
            self.play_sound("check.wav")
            return

        self.play_sound("move.wav")

    def __init__(self, root):
        self.stockfish = ChessGame.StockfishAI(
            engine_path,
            elo=1500
        )
        self.root = root
        self.root.title("Chess")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", self.exit_fullscreen)

        # Initialize board
        self.board = chess.Board()
        self.selected_square = None
        self.player_color = chess.WHITE  # Default: player is white
        self.player_turn = True  # True if it's player's turn (depends on player_color)
        self.game_over = False
        self.ai_thinking = False
        self.pending_promotion = None
        self.game_paused = False

        # Piece symbols
        self.piece_symbols = {
            'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚', 'p': '♟',
            'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔', 'P': '♙'
        }

        # Promotion options
        self.promotion_pieces = [
            ("♕", chess.QUEEN, "Queen"),
            ("♖", chess.ROOK, "Rook"),
            ("♗", chess.BISHOP, "Bishop"),
            ("♘", chess.KNIGHT, "Knight")
        ]

        # Color scheme
        self.colors = {
            "light": "#f0d9b5",
            "dark": "#b58863",
            "selected": "#7cb9e8",
            "possible": "#90ee90",
            "check": "#ff6b6b",
            "last_move": "#A9A9A9",
            "bg": "#2d2d2d",
            "card_bg": "#363636",
            "button": "#3d3d3d",
            "button_hover": "#4d4d4d",
            "eval_white": "#ffffff",
            "eval_black": "#000000",
            "eval_equal": "#808080",
            "player_card": "#2a2a2a",
            "ai_card": "#1a1a1a",
            "stat_positive": "#4CAF50",
            "stat_neutral": "#FFC107",
            "stat_negative": "#f44336",
        }

        # Move history tracking
        self.move_history = []
        self.move_count = 1

        # Last move record
        self.last_move = None

        # Eval bar state
        self.current_eval: Optional[Evaluation] = None

        # Player statistics
        self.player_stats = PlayerStats()
        self.current_game_result = None
        self.ai_name = "Stockfish"
        self.player_name = "Player"

        # Start tracking current game
        self.player_stats.start_game()

        self.setup_ui()
        self.update_board_display()
        self.update_turn_display()
        self.root.attributes("-fullscreen", False)
        self.root.geometry("1400x850")

    def setup_ui(self):
        # Main horizontal container
        main_horizontal = tk.Frame(self.root, bg=self.colors["bg"])
        main_horizontal.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Left side - Player Cards and Eval Bar
        left_panel = tk.Frame(main_horizontal, bg=self.colors["bg"], width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        left_panel.pack_propagate(False)

        # Player Card (Human)
        self.create_player_card(left_panel, self.player_name, is_human=True)

        # Eval bar container
        eval_container = tk.Frame(left_panel, bg=self.colors["bg"])
        eval_container.pack(pady=20)

        # Eval bar
        self.eval_canvas = tk.Canvas(
            eval_container,
            width=80,
            height=400,
            bg="#333333",
            highlightthickness=2,
            highlightbackground="#555555"
        )
        self.eval_canvas.pack()

        # Eval text labels
        self.eval_value_label = tk.Label(
            eval_container,
            text="0.00",
            font=("Arial", 14, "bold"),
            bg=self.colors["bg"],
            fg="white"
        )
        self.eval_value_label.pack(pady=(5, 0))

        self.eval_desc_label = tk.Label(
            eval_container,
            text="Equal",
            font=("Arial", 12),
            bg=self.colors["bg"],
            fg="#cccccc"
        )
        self.eval_desc_label.pack()

        # AI Card
        self.create_player_card(left_panel, self.ai_name, is_human=False)

        # Middle - Main content (chess board)
        middle_panel = tk.Frame(main_horizontal, bg=self.colors["bg"])
        middle_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Title
        title_label = tk.Label(middle_panel, text="Chess",
                               font=("Arial", 24, "bold"),
                               bg=self.colors["bg"], fg="#ffffff")
        title_label.pack(pady=(0, 10))

        # Game info frame
        info_frame = tk.Frame(middle_panel, bg="#3d3d3d", padx=10, pady=20)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.turn_label = tk.Label(info_frame, text="⚪ Your turn (White)",
                                   font=("Arial", 20, "bold"),
                                   bg="#3d3d3d", fg="#ffffff")
        self.turn_label.pack(side=tk.LEFT, padx=10)

        self.status_label = tk.Label(info_frame, text="Click on a piece to start",
                                     font=("Arial", 20),
                                     bg="#3d3d3d", fg="#cccccc")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Board container
        chess_container = tk.Frame(middle_panel, bg=self.colors["bg"])
        chess_container.pack(pady=10)

        # Left rank numbers
        left_numbers = tk.Frame(chess_container, bg=self.colors["bg"])
        left_numbers.pack(side=tk.LEFT, padx=(0, 5))
        for i in range(8):
            number_label = tk.Label(left_numbers, text=str(8 - i),
                                    font=("Arial", 19, "bold"),
                                    bg=self.colors["bg"], fg="#cccccc",
                                    width=4, height=3)
            number_label.pack()

        # Board buttons
        self.board_frame = tk.Frame(chess_container, bg=self.colors["bg"])
        self.board_frame.pack(side=tk.LEFT)

        self.buttons = []
        for row in range(8):
            button_row = []
            for col in range(8):
                if (row + col) % 2 == 0:
                    bg_color = self.colors["light"]
                else:
                    bg_color = self.colors["dark"]

                btn = tk.Button(
                    self.board_frame,
                    width=4,
                    height=3,
                    font=("Arial", 18, "bold"),
                    bg=bg_color,
                    fg="black",
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    activebackground=bg_color,
                    activeforeground="black",
                    command=lambda r=row, c=col: self.square_clicked(r, c)
                )
                btn.grid(row=row, column=col, padx=1, pady=1)
                button_row.append(btn)
            self.buttons.append(button_row)

        # Bottom file letters
        bottom_frame = tk.Frame(middle_panel, bg=self.colors["bg"])
        bottom_frame.pack()
        spacer = tk.Label(bottom_frame, text="    ", bg=self.colors["bg"])
        spacer.pack(side=tk.LEFT)
        for i in range(8):
            letter_label = tk.Label(bottom_frame, text=chr(97 + i).upper(),
                                    font=("Arial", 20, "bold"),
                                    bg=self.colors["bg"], fg="#cccccc",
                                    width=6)
            letter_label.pack(side=tk.LEFT)

        # Control buttons - First row
        control_frame1 = tk.Frame(middle_panel, bg=self.colors["bg"])
        control_frame1.pack(fill=tk.X, pady=(15, 5))

        # New Game button
        new_game_btn = tk.Button(control_frame1, text="🔄 New Game",
                                 command=self.new_game,
                                 bg="#4CAF50", fg="black",
                                 font=("Arial", 16, "bold"),
                                 padx=15, pady=8, bd=0,
                                 width=12)
        new_game_btn.pack(side=tk.LEFT, padx=5)

        # Pause/Resume button
        self.pause_btn = tk.Button(control_frame1, text="⏸️ Pause",
                                   command=self.toggle_pause,
                                   bg="#FFA500", fg="black",
                                   font=("Arial", 16, "bold"),
                                   padx=15, pady=8, bd=0,
                                   width=12)
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        # Undo Move button
        undo_btn = tk.Button(control_frame1, text="↩️ Undo",
                             command=self.undo_move,
                             bg="#2196F3", fg="black",
                             font=("Arial", 16, "bold"),
                             padx=15, pady=8, bd=0,
                             width=12)
        undo_btn.pack(side=tk.LEFT, padx=5)

        # Hint button
        hint_btn = tk.Button(control_frame1, text="💡 Hint",
                             command=self.get_hint,
                             bg="#9C27B0", fg="black",
                             font=("Arial", 16, "bold"),
                             padx=15, pady=8, bd=0,
                             width=12)
        hint_btn.pack(side=tk.LEFT, padx=5)

        # Control buttons - Second row
        control_frame2 = tk.Frame(middle_panel, bg=self.colors["bg"])
        control_frame2.pack(fill=tk.X, pady=5)

        # Export PGN button
        export_btn = tk.Button(control_frame2, text="📥 Export PGN",
                               command=self.export_pgn,
                               bg="#795548", fg="black",
                               font=("Arial", 16, "bold"),
                               padx=15, pady=8, bd=0,
                               width=12)
        export_btn.pack(side=tk.LEFT, padx=5)

        # Flip Board button
        flip_btn = tk.Button(control_frame2, text="🔄 Flip Board",
                             command=self.flip_board,
                             bg="#607D8B", fg="black",
                             font=("Arial", 16, "bold"),
                             padx=15, pady=8, bd=0,
                             width=12)
        flip_btn.pack(side=tk.LEFT, padx=5)

        # Settings button
        settings_btn = tk.Button(control_frame2, text="⚙️ Settings",
                                 command=self.show_settings,
                                 bg="#607D8B", fg="black",
                                 font=("Arial", 16, "bold"),
                                 padx=15, pady=8, bd=0,
                                 width=12)
        settings_btn.pack(side=tk.LEFT, padx=5)

        # ELO selection
        depth_frame = tk.Frame(control_frame2, bg=self.colors["bg"])
        depth_frame.pack(side=tk.LEFT, padx=10)

        tk.Label(depth_frame, text="ELO:",
                 font=("Arial", 16), bg=self.colors["bg"], fg="white").pack(side=tk.LEFT)

        self.elo_var = tk.StringVar(value="1500")

        depth_menu = tk.OptionMenu(
            depth_frame,
            self.elo_var,
            "200", "400", "600", "800",
            "1000", "1200", "1400", "1600",
            "1800", "2000", "2200", "2400",
            "2600", "2800", "3000",
            command=self.change_elo
        )
        depth_menu.config(font=("Arial", 16), bg="#3d3d3d", fg="black", width=6)
        depth_menu.pack(side=tk.LEFT, padx=5)

        # Exit fullscreen button
        exit_fullscreen_btn = tk.Button(middle_panel, text="⏹️ Exit Fullscreen",
                                        command=self.exit_fullscreen,
                                        bg="#f44336", fg="black",
                                        font=("Arial", 14, "bold"),
                                        padx=15, pady=8, bd=0)
        exit_fullscreen_btn.pack(pady=10)

        # Hint text
        hint_label = tk.Label(middle_panel, text="Press ESC to exit fullscreen | Choose your color on the right panel",
                              font=("Arial", 12),
                              bg=self.colors["bg"], fg="#888888")
        hint_label.pack(pady=(0, 5))

        # Right side - Move History Panel
        right_panel = tk.Frame(main_horizontal, bg=self.colors["bg"], width=320)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(20, 0))
        right_panel.pack_propagate(False)

        # Color selection frame (移到 Move History 上面)
        color_frame = tk.Frame(right_panel, bg=self.colors["bg"])
        color_frame.pack(fill=tk.X, pady=(0, 10))

        # Color selection label
        tk.Label(color_frame, text="Play as:",
                 font=("Arial", 16, "bold"), bg=self.colors["bg"], fg="white").pack(anchor="w", padx=5)

        # Color buttons frame
        color_buttons_frame = tk.Frame(color_frame, bg=self.colors["bg"])
        color_buttons_frame.pack(fill=tk.X, pady=5)

        self.color_var = tk.StringVar(value="white")

        white_btn = tk.Radiobutton(color_buttons_frame, text="⚪ White", variable=self.color_var,
                                   value="white", command=self.change_color,
                                   bg=self.colors["bg"], fg="white",
                                   selectcolor=self.colors["bg"],
                                   font=("Arial", 14))
        white_btn.pack(side=tk.LEFT, padx=10)

        black_btn = tk.Radiobutton(color_buttons_frame, text="⚫ Black", variable=self.color_var,
                                   value="black", command=self.change_color,
                                   bg=self.colors["bg"], fg="white",
                                   selectcolor=self.colors["bg"],
                                   font=("Arial", 14))
        black_btn.pack(side=tk.LEFT, padx=10)

        # Separator line
        separator = tk.Frame(right_panel, bg="#555555", height=2)
        separator.pack(fill=tk.X, pady=(0, 10))

        # Move History header
        history_header = tk.Frame(right_panel, bg="#3d3d3d", height=50)
        history_header.pack(fill=tk.X, pady=(0, 10))
        history_header.pack_propagate(False)

        tk.Label(history_header, text="📜 Move History",
                 font=("Arial", 18, "bold"),
                 bg="#3d3d3d", fg="#ffffff").pack(expand=True)

        # Clear History button
        clear_history_btn = tk.Button(history_header, text="🗑️ Clear",
                                      command=self.clear_history,
                                      bg="#f44336", fg="black",
                                      font=("Arial", 10, "bold"),
                                      padx=5, pady=2, bd=0)
        clear_history_btn.pack(side=tk.RIGHT, padx=5)

        # Move History list with scrollbar
        history_container = tk.Frame(right_panel, bg=self.colors["bg"])
        history_container.pack(fill=tk.BOTH, expand=True)

        self.history_canvas = tk.Canvas(history_container, bg=self.colors["bg"],
                                        highlightthickness=0)
        self.history_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(history_container, orient=tk.VERTICAL,
                                 command=self.history_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_canvas.configure(yscrollcommand=scrollbar.set)

        self.history_frame = tk.Frame(self.history_canvas, bg=self.colors["bg"])
        self.history_canvas.create_window((0, 0), window=self.history_frame,
                                          anchor="nw", width=300)

        self.history_frame.bind("<Configure>", self.on_frame_configure)
        self.history_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        self.update_move_history_display()

        self.promotion_window = None
        self.settings_window = None

        # Board orientation
        self.board_flipped = False

        # Start periodic updates
        self.update_evaluation()
        self.update_player_stats_display()

    def change_color(self):
        """Change player's color"""
        self.player_color = chess.WHITE if self.color_var.get() == "white" else chess.BLACK
        self.new_game()  # Start new game with new color
        self.update_turn_display()

        # Auto-flip board if playing as black
        if self.player_color == chess.BLACK:
            self.board_flipped = True
        else:
            self.board_flipped = False
        self.update_board_display()

        self.status_label.config(text=f"Playing as {'White' if self.player_color == chess.WHITE else 'Black'}")

    def update_turn_display(self):
        """Update turn label based on player color"""
        if self.player_color == chess.WHITE:
            if self.player_turn:
                self.turn_label.config(text="⚪ Your turn (White)", fg="#ffffff")
            else:
                self.turn_label.config(text="⚫ AI thinking...", fg="#ffd700")
        else:
            if self.player_turn:
                self.turn_label.config(text="⚫ Your turn (Black)", fg="#ffffff")
            else:
                self.turn_label.config(text="⚪ AI thinking...", fg="#ffd700")

    def create_player_card(self, parent, title, is_human=True):
        """Create a player information card"""
        card_bg = self.colors["player_card"] if is_human else self.colors["ai_card"]

        # Card frame
        card = tk.Frame(parent, bg=card_bg, relief=tk.RAISED, bd=2)
        card.pack(fill=tk.X, pady=10, padx=5)

        # Player header
        header_frame = tk.Frame(card, bg=card_bg)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        avatar = "👤" if is_human else "🤖"
        piece_color = "⚪" if (is_human and self.player_color == chess.WHITE) or (
                    not is_human and self.player_color == chess.BLACK) else "⚫"
        tk.Label(header_frame, text=f"{avatar} {title} {piece_color}",
                 font=("Arial", 12, "bold"),
                 bg=card_bg, fg="#ffffff").pack(side=tk.LEFT)

        # Stats container
        stats_frame = tk.Frame(card, bg=card_bg)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        if is_human:
            # Human player stats
            self.player_stats_labels = {}

            # Games played
            games_frame = tk.Frame(stats_frame, bg=card_bg)
            games_frame.pack(fill=tk.X, pady=2)
            tk.Label(games_frame, text="Games:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.player_stats_labels['games'] = tk.Label(games_frame, text="0",
                                                         font=("Arial", 11, "bold"),
                                                         bg=card_bg, fg="#ffffff")
            self.player_stats_labels['games'].pack(side=tk.RIGHT)

            # Win/Loss/Draw
            wld_frame = tk.Frame(stats_frame, bg=card_bg)
            wld_frame.pack(fill=tk.X, pady=2)

            tk.Label(wld_frame, text="W:", font=("Arial", 11),
                     bg=card_bg, fg="#4CAF50").pack(side=tk.LEFT, padx=(0, 5))
            self.player_stats_labels['wins'] = tk.Label(wld_frame, text="0",
                                                        font=("Arial", 11, "bold"),
                                                        bg=card_bg, fg="#4CAF50")
            self.player_stats_labels['wins'].pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(wld_frame, text="L:", font=("Arial", 11),
                     bg=card_bg, fg="#f44336").pack(side=tk.LEFT, padx=(0, 5))
            self.player_stats_labels['losses'] = tk.Label(wld_frame, text="0",
                                                          font=("Arial", 11, "bold"),
                                                          bg=card_bg, fg="#f44336")
            self.player_stats_labels['losses'].pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(wld_frame, text="D:", font=("Arial", 11),
                     bg=card_bg, fg="#FFC107").pack(side=tk.LEFT, padx=(0, 5))
            self.player_stats_labels['draws'] = tk.Label(wld_frame, text="0",
                                                         font=("Arial", 11, "bold"),
                                                         bg=card_bg, fg="#FFC107")
            self.player_stats_labels['draws'].pack(side=tk.LEFT)

            # Win rate
            rate_frame = tk.Frame(stats_frame, bg=card_bg)
            rate_frame.pack(fill=tk.X, pady=2)
            tk.Label(rate_frame, text="Win Rate:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.player_stats_labels['win_rate'] = tk.Label(rate_frame, text="0%",
                                                            font=("Arial", 11, "bold"),
                                                            bg=card_bg, fg="#4CAF50")
            self.player_stats_labels['win_rate'].pack(side=tk.RIGHT)

            # Total moves
            moves_frame = tk.Frame(stats_frame, bg=card_bg)
            moves_frame.pack(fill=tk.X, pady=2)
            tk.Label(moves_frame, text="Moves:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.player_stats_labels['moves'] = tk.Label(moves_frame, text="0",
                                                         font=("Arial", 11, "bold"),
                                                         bg=card_bg, fg="#ffffff")
            self.player_stats_labels['moves'].pack(side=tk.RIGHT)

            # Captures
            captures_frame = tk.Frame(stats_frame, bg=card_bg)
            captures_frame.pack(fill=tk.X, pady=2)
            tk.Label(captures_frame, text="Captures:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.player_stats_labels['captures'] = tk.Label(captures_frame, text="0",
                                                            font=("Arial", 11, "bold"),
                                                            bg=card_bg, fg="#FF5722")
            self.player_stats_labels['captures'].pack(side=tk.RIGHT)

        else:
            # AI stats
            self.ai_stats_labels = {}

            elo_frame = tk.Frame(stats_frame, bg=card_bg)
            elo_frame.pack(fill=tk.X, pady=2)
            tk.Label(elo_frame, text="Current ELO:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.ai_stats_labels['elo'] = tk.Label(elo_frame, text="1500",
                                                   font=("Arial", 11, "bold"),
                                                   bg=card_bg, fg="#FFD700")
            self.ai_stats_labels['elo'].pack(side=tk.RIGHT)

            time_frame = tk.Frame(stats_frame, bg=card_bg)
            time_frame.pack(fill=tk.X, pady=2)
            tk.Label(time_frame, text="Think Time:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.ai_stats_labels['think_time'] = tk.Label(time_frame, text="0.2s",
                                                          font=("Arial", 11, "bold"),
                                                          bg=card_bg, fg="#2196F3")
            self.ai_stats_labels['think_time'].pack(side=tk.RIGHT)

            nodes_frame = tk.Frame(stats_frame, bg=card_bg)
            nodes_frame.pack(fill=tk.X, pady=2)
            tk.Label(nodes_frame, text="Depth:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.ai_stats_labels['depth'] = tk.Label(nodes_frame, text="Variable",
                                                     font=("Arial", 11, "bold"),
                                                     bg=card_bg, fg="#9C27B0")
            self.ai_stats_labels['depth'].pack(side=tk.RIGHT)

        # Current game status
        status_frame = tk.Frame(card, bg=card_bg)
        status_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        if is_human:
            tk.Label(status_frame, text="Status:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.player_status_label = tk.Label(status_frame, text="Waiting for your move",
                                                font=("Arial", 11, "bold"),
                                                bg=card_bg, fg="#4CAF50")
            self.player_status_label.pack(side=tk.RIGHT)
        else:
            tk.Label(status_frame, text="Status:", font=("Arial", 11),
                     bg=card_bg, fg="#cccccc").pack(side=tk.LEFT)
            self.ai_status_label = tk.Label(status_frame, text="Ready",
                                            font=("Arial", 11, "bold"),
                                            bg=card_bg, fg="#2196F3")
            self.ai_status_label.pack(side=tk.RIGHT)

    def update_player_stats_display(self):
        """Update player statistics display"""
        if hasattr(self, 'player_stats_labels'):
            stats = self.player_stats_labels

            stats['games'].config(text=str(self.player_stats.games_played))
            stats['wins'].config(text=str(self.player_stats.wins))
            stats['losses'].config(text=str(self.player_stats.losses))
            stats['draws'].config(text=str(self.player_stats.draws))
            stats['win_rate'].config(text=f"{self.player_stats.get_win_rate():.1f}%")
            stats['moves'].config(text=str(self.player_stats.total_moves))
            stats['captures'].config(text=str(self.player_stats.captures))

        if hasattr(self, 'ai_stats_labels'):
            ai_stats = self.ai_stats_labels
            ai_stats['elo'].config(text=self.elo_var.get())

        # Update status labels
        if self.game_paused:
            if hasattr(self, 'player_status_label'):
                self.player_status_label.config(text="Game Paused", fg="#FFA500")
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.config(text="Paused", fg="#FFA500")
        elif self.game_over:
            if self.current_game_result == "win":
                if hasattr(self, 'player_status_label'):
                    self.player_status_label.config(text="Winner! 🏆", fg="#4CAF50")
                if hasattr(self, 'ai_status_label'):
                    self.ai_status_label.config(text="Lost", fg="#f44336")
            elif self.current_game_result == "loss":
                if hasattr(self, 'player_status_label'):
                    self.player_status_label.config(text="Lost", fg="#f44336")
                if hasattr(self, 'ai_status_label'):
                    self.ai_status_label.config(text="Winner! 🏆", fg="#4CAF50")
            elif self.current_game_result == "draw":
                if hasattr(self, 'player_status_label'):
                    self.player_status_label.config(text="Draw", fg="#FFC107")
                if hasattr(self, 'ai_status_label'):
                    self.ai_status_label.config(text="Draw", fg="#FFC107")
        elif self.player_turn and not self.ai_thinking:
            if hasattr(self, 'player_status_label'):
                self.player_status_label.config(text="Your turn", fg="#4CAF50")
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.config(text="Thinking", fg="#2196F3")
        elif self.ai_thinking:
            if hasattr(self, 'player_status_label'):
                self.player_status_label.config(text="Waiting", fg="#FFC107")
            if hasattr(self, 'ai_status_label'):
                self.ai_status_label.config(text="Calculating...", fg="#2196F3")

        self.root.after(1000, self.update_player_stats_display)

    def on_frame_configure(self, event):
        self.history_canvas.configure(scrollregion=self.history_canvas.bbox("all"))

    def on_mousewheel(self, event):
        self.history_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def update_move_history_display(self):
        """Update the move history display"""
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        if not self.move_history:
            empty_label = tk.Label(self.history_frame,
                                   text="No moves yet\n\nMake your first move!",
                                   font=("Arial", 14),
                                   bg=self.colors["bg"],
                                   fg="#888888",
                                   justify=tk.CENTER)
            empty_label.pack(expand=True, pady=50)
            return

        for i in range(0, len(self.move_history), 2):
            move_frame = tk.Frame(self.history_frame, bg=self.colors["bg"])
            move_frame.pack(fill=tk.X, pady=2, padx=5)

            move_num = i // 2 + 1
            num_label = tk.Label(move_frame, text=f"{move_num}.",
                                 font=("Arial", 12, "bold"),
                                 bg=self.colors["bg"],
                                 fg="#888888",
                                 width=3)
            num_label.pack(side=tk.LEFT)

            white_move = self.move_history[i]
            white_bg = "#3d3d3d"
            white_frame = tk.Frame(move_frame, bg=white_bg, padx=8, pady=4)
            white_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

            white_label = tk.Label(white_frame,
                                   text=f"⚪ {white_move}",
                                   font=("Arial", 12),
                                   bg=white_bg,
                                   fg="#ffffff",
                                   anchor="w")
            white_label.pack(fill=tk.X)

            if i + 1 < len(self.move_history):
                black_move = self.move_history[i + 1]
                black_bg = "#2a2a2a"
                black_frame = tk.Frame(move_frame, bg=black_bg, padx=8, pady=4)
                black_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

                black_label = tk.Label(black_frame,
                                       text=f"⚫ {black_move}",
                                       font=("Arial", 12),
                                       bg=black_bg,
                                       fg="#cccccc",
                                       anchor="w")
                black_label.pack(fill=tk.X)

        total_moves = len(self.move_history)
        footer_frame = tk.Frame(self.history_frame, bg=self.colors["bg"])
        footer_frame.pack(fill=tk.X, pady=(10, 5))

        tk.Label(footer_frame,
                 text=f"Total moves: {total_moves}",
                 font=("Arial", 10, "italic"),
                 bg=self.colors["bg"],
                 fg="#888888").pack()

        self.history_canvas.yview_moveto(1.0)

    def add_move_to_history(self, move, is_player_move, is_capture=False):
        """Add a move to the history"""
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        piece = self.board.piece_at(move.to_square)
        if piece:
            piece_symbol = self.piece_symbols.get(piece.symbol(), '')
        else:
            piece_symbol = ''

        if move.promotion:
            promotion_names = {chess.QUEEN: "Q", chess.ROOK: "R",
                               chess.BISHOP: "B", chess.KNIGHT: "N"}
            move_str = f"{piece_symbol}{from_sq}→{to_sq}={promotion_names[move.promotion]}"
        else:
            move_str = f"{piece_symbol}{from_sq}→{to_sq}"

        if is_capture:
            move_str += " x"

        if self.board.is_checkmate():
            move_str += "#"
        elif self.board.is_check():
            move_str += "+"

        self.move_history.append(move_str)
        self.update_move_history_display()

        if is_player_move:
            self.player_stats.add_move(is_capture=is_capture)
            if self.board.is_checkmate():
                self.player_stats.add_checkmate()

    def clear_history(self):
        if messagebox.askyesno("Clear History", "Are you sure you want to clear the move history?"):
            self.move_history = []
            self.update_move_history_display()

    def toggle_pause(self):
        self.game_paused = not self.game_paused
        if self.game_paused:
            self.pause_btn.config(text="▶️ Resume", bg="#4CAF50")
            self.status_label.config(text="⏸️ Game Paused")
            self.turn_label.config(text="⏸️ Paused", fg="#FFA500")
        else:
            self.pause_btn.config(text="⏸️ Pause", bg="#FFA500")
            self.status_label.config(text="Game resumed")
            self.update_turn_display()

    def undo_move(self):
        if len(self.board.move_stack) < 2:
            messagebox.showinfo("Undo", "Not enough moves to undo")
            return

        self.board.pop()
        self.board.pop()

        if len(self.move_history) >= 2:
            self.move_history = self.move_history[:-2]
        elif len(self.move_history) == 1:
            self.move_history = self.move_history[:-1]
        self.update_move_history_display()

        self.selected_square = None
        self.player_turn = True
        self.ai_thinking = False
        self.game_over = False
        self.last_move = None
        self.clear_highlights()
        self.update_board_display()
        self.update_turn_display()
        self.status_label.config(text="Move undone")

    def get_hint(self):
        if not self.player_turn or self.game_over or self.ai_thinking or self.game_paused:
            messagebox.showinfo("Hint", "Wait for your turn to get a hint")
            return

        hint_move = self.stockfish.get_move(self.board)
        from_sq = chess.square_name(hint_move.from_square)
        to_sq = chess.square_name(hint_move.to_square)
        messagebox.showinfo("Hint", f"Consider moving from {from_sq} to {to_sq}")

    def flip_board(self):
        self.board_flipped = not self.board_flipped
        self.update_board_display()
        self.status_label.config(text=f"Board flipped ({'Black' if self.board_flipped else 'White'} side)")

    def export_pgn(self):
        if not self.move_history:
            messagebox.showinfo("Export PGN", "No moves to export")
            return

        pgn_lines = []
        pgn_lines.append('[Event "Chess Game"]')
        pgn_lines.append('[Site "Local"]')
        pgn_lines.append(f'[Date "{datetime.now().strftime("%Y.%m.%d")}"]')
        pgn_lines.append('[Round "-"]')
        pgn_lines.append(f'[White "{self.player_name if self.player_color == chess.WHITE else self.ai_name}"]')
        pgn_lines.append(f'[Black "{self.ai_name if self.player_color == chess.WHITE else self.player_name}"]')
        pgn_lines.append('[Result "*"]')
        pgn_lines.append('')

        move_text = ""
        for i, move in enumerate(self.move_history):
            if i % 2 == 0:
                move_text += f"{i // 2 + 1}. {move} "
            else:
                move_text += f"{move} "

        pgn_lines.append(move_text)

        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".pgn",
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")]
        )
        if filename:
            with open(filename, 'w') as f:
                f.write('\n'.join(pgn_lines))
            messagebox.showinfo("Export PGN", f"Game exported to {filename}")

    def show_settings(self):
        if self.settings_window:
            self.settings_window.destroy()

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("⚙️ Settings")
        self.settings_window.geometry("400x450")
        self.settings_window.configure(bg=self.colors["bg"])
        self.settings_window.transient(self.root)
        self.settings_window.grab_set()

        self.settings_window.update_idletasks()
        x = (self.root.winfo_x() + (self.root.winfo_width() // 2)) - (400 // 2)
        y = (self.root.winfo_y() + (self.root.winfo_height() // 2)) - (450 // 2)
        self.settings_window.geometry(f"+{x}+{y}")

        tk.Label(self.settings_window, text="Game Settings",
                 font=("Arial", 20, "bold"),
                 bg=self.colors["bg"], fg="#ffffff").pack(pady=20)

        name_frame = tk.Frame(self.settings_window, bg=self.colors["bg"])
        name_frame.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(name_frame, text="Player Name:",
                 font=("Arial", 14),
                 bg=self.colors["bg"], fg="#ffffff").pack(anchor="w")

        self.player_name_var = tk.StringVar(value=self.player_name)
        name_entry = tk.Entry(name_frame, textvariable=self.player_name_var,
                              font=("Arial", 12), bg="#3d3d3d", fg="white",
                              insertbackground="white")
        name_entry.pack(fill=tk.X, pady=5)

        sound_frame = tk.Frame(self.settings_window, bg=self.colors["bg"])
        sound_frame.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(sound_frame, text="Sound Effects:",
                 font=("Arial", 14),
                 bg=self.colors["bg"], fg="#ffffff").pack(anchor="w")

        self.sound_var = tk.BooleanVar(value=True)
        sound_check = tk.Checkbutton(sound_frame, text="Enable sounds",
                                     variable=self.sound_var,
                                     bg=self.colors["bg"], fg="#ffffff",
                                     selectcolor=self.colors["bg"],
                                     font=("Arial", 12))
        sound_check.pack(anchor="w", padx=20)

        time_frame = tk.Frame(self.settings_window, bg=self.colors["bg"])
        time_frame.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(time_frame, text="AI Thinking Time:",
                 font=("Arial", 14),
                 bg=self.colors["bg"], fg="#ffffff").pack(anchor="w")

        self.thinking_time_var = tk.StringVar(value="0.2")
        time_options = ["0.1", "0.2", "0.5", "1.0", "2.0"]
        time_menu = tk.OptionMenu(time_frame, self.thinking_time_var, *time_options)
        time_menu.config(font=("Arial", 12), bg="#3d3d3d", fg="black", width=10)
        time_menu.pack(anchor="w", padx=20, pady=5)

        reset_frame = tk.Frame(self.settings_window, bg=self.colors["bg"])
        reset_frame.pack(fill=tk.X, padx=20, pady=10)

        reset_btn = tk.Button(reset_frame, text="Reset Statistics",
                              command=self.reset_statistics,
                              bg="#f44336", fg="black",
                              font=("Arial", 12, "bold"),
                              padx=10, pady=5, bd=0)
        reset_btn.pack()

        save_btn = tk.Button(self.settings_window, text="Save Settings",
                             command=self.save_settings,
                             bg="#4CAF50", fg="black",
                             font=("Arial", 14, "bold"),
                             padx=20, pady=10, bd=0)
        save_btn.pack(pady=20)

    def reset_statistics(self):
        if messagebox.askyesno("Reset Statistics", "Are you sure you want to reset all statistics?"):
            self.player_stats = PlayerStats()
            self.update_player_stats_display()
            messagebox.showinfo("Reset", "Statistics have been reset")

    def save_settings(self):
        self.player_name = self.player_name_var.get()
        messagebox.showinfo("Settings", "Settings saved successfully!")
        self.settings_window.destroy()

    def normalize_eval_for_display(self, eval_value: int) -> float:
        clamped = max(-1000, min(1000, eval_value))
        return (clamped + 1000) / 2000

    def update_evaluation(self):
        if not self.game_over and not self.game_paused:
            self.current_eval = self.stockfish.get_evaluation(self.board)
            self.draw_eval_bar()
        self.root.after(500, self.update_evaluation)

    def draw_eval_bar(self):
        if not self.current_eval:
            return

        self.eval_canvas.delete("all")

        height = 400
        bar_height = height - 60

        if self.current_eval.type == 'mate':
            proportion = 1.0 if self.current_eval.white_advantage else 0.0
        else:
            proportion = self.normalize_eval_for_display(self.current_eval.value)

        white_height = int(proportion * bar_height)
        black_height = bar_height - white_height

        self.eval_canvas.create_rectangle(
            15, 40,
            65, 40 + bar_height,
            fill="#222222",
            outline=""
        )

        if black_height > 0:
            self.eval_canvas.create_rectangle(
                15, 40,
                65, 40 + black_height,
                fill="#333333",
                outline=""
            )

        if white_height > 0:
            self.eval_canvas.create_rectangle(
                15, 40 + black_height,
                65, 40 + black_height + white_height,
                fill="#f0f0f0",
                outline=""
            )

        self.eval_canvas.create_rectangle(
            15, 40, 65, 40 + bar_height,
            outline="#888888",
            width=2
        )

        center_y = 40 + bar_height // 2
        self.eval_canvas.create_line(
            13, center_y, 67, center_y,
            fill="#ffd700",
            width=3,
            dash=(4, 4)
        )

        self.eval_canvas.create_text(
            40, 25,
            text="BLACK",
            fill="#cccccc",
            font=("Arial", 10, "bold")
        )

        self.eval_canvas.create_text(
            40, 40 + bar_height + 15,
            text="WHITE",
            fill="#cccccc",
            font=("Arial", 10, "bold")
        )

        self.eval_value_label.config(text=self.current_eval.display_text)

        if self.current_eval.type == 'mate':
            if self.current_eval.white_advantage:
                self.eval_desc_label.config(text=f"White {self.current_eval.display_text}")
            else:
                self.eval_desc_label.config(text=f"Black {self.current_eval.display_text}")
        else:
            if self.current_eval.value > 30:
                self.eval_desc_label.config(text=f"White +{self.current_eval.value / 100:.2f}")
            elif self.current_eval.value < -30:
                self.eval_desc_label.config(text=f"Black +{abs(self.current_eval.value / 100):.2f}")
            else:
                self.eval_desc_label.config(text="Equal position")

    def change_elo(self, value):
        elo = int(value)
        self.stockfish.set_elo(elo)
        self.status_label.config(text=f"Stockfish Elo set to {elo}")

    def show_promotion_dialog(self, move):
        self.pending_promotion = move
        if self.promotion_window:
            self.promotion_window.destroy()

        self.promotion_window = tk.Toplevel(self.root)
        self.promotion_window.title("♟️ Pawn Promotion")
        self.promotion_window.geometry("1000x200")
        self.promotion_window.configure(bg=self.colors["bg"])
        self.promotion_window.transient(self.root)
        self.promotion_window.grab_set()

        self.promotion_window.update_idletasks()
        x = (self.root.winfo_x() + (self.root.winfo_width() // 2)) - (1000 // 2)
        y = (self.root.winfo_y() + (self.root.winfo_height() // 2)) - (200 // 2)
        self.promotion_window.geometry(f"+{x}+{y}")

        tk.Label(self.promotion_window, text="Choose piece for promotion",
                 font=("Arial", 16, "bold"),
                 bg=self.colors["bg"], fg="#ffffff").pack(pady=15)

        button_frame = tk.Frame(self.promotion_window, bg=self.colors["bg"])
        button_frame.pack(pady=10)

        for symbol, piece_value, name in self.promotion_pieces:
            btn = tk.Button(button_frame, text=f"{symbol} {name}",
                            command=lambda p=piece_value: self.promote_pawn(p),
                            font=("Arial", 24, "bold"),
                            bg=self.colors["button"], fg="black",
                            padx=20, pady=10, bd=0,
                            width=10)
            btn.pack(side=tk.LEFT, padx=10)

        tk.Label(self.promotion_window,
                 text="Pawns reaching the back rank can promote to Queen, Rook, Bishop, or Knight",
                 font=("Arial", 12),
                 bg=self.colors["bg"], fg="#cccccc").pack(pady=15)

    def promote_pawn(self, promotion_piece):
        if self.pending_promotion:
            move = chess.Move(
                self.pending_promotion.from_square,
                self.pending_promotion.to_square,
                promotion=promotion_piece
            )
            if self.promotion_window:
                self.promotion_window.destroy()
                self.promotion_window = None

            is_capture = self.board.is_capture(move)
            is_castle = self.board.is_castling(move)
            is_promotion = True

            self.board.push(move)

            self.play_move_sound(move, is_capture, is_castle, is_promotion)
            self.last_move = move
            self.pending_promotion = None
            self.selected_square = None
            self.clear_highlights()
            self.update_board_display()

            self.add_move_to_history(move, is_player_move=True, is_capture=is_capture)

            if self.check_game_over():
                return

            self.player_turn = False
            self.ai_thinking = True
            self.update_turn_display()
            self.root.update()
            self.root.after(500, self.ai_move)

    def square_clicked(self, row, col):
        if self.game_paused:
            self.status_label.config(text="⏸️ Game is paused. Click Resume to continue")
            return

        if not self.player_turn or self.game_over or self.ai_thinking:
            if not self.player_turn:
                self.status_label.config(text="AI's turn, please wait")
            return

        # Handle board flip
        if self.board_flipped:
            actual_row = 7 - row
        else:
            actual_row = row

        square = (7 - actual_row) * 8 + col
        piece = self.board.piece_at(square)

        if self.selected_square is None:
            if piece and piece.color == self.player_color:
                self.selected_square = square
                self.highlight_square(row, col, "selected")
                self.show_possible_moves(square)
                file_letter = chr(97 + col)
                rank_number = 8 - actual_row
                self.status_label.config(text=f"Selected: {file_letter}{rank_number}")
            else:
                if piece:
                    self.status_label.config(
                        text=f"That's a {'white' if piece.color == chess.WHITE else 'black'} piece, please choose your piece")
                else:
                    self.status_label.config(text="That's an empty square, please choose a piece")
        else:
            selected_piece = self.board.piece_at(self.selected_square)

            # Check for promotion
            if selected_piece and selected_piece.piece_type == chess.PAWN and selected_piece.color == self.player_color:
                # Check if pawn reaches last rank (row 0 for white, row 7 for black)
                if (self.player_color == chess.WHITE and actual_row == 0) or \
                        (self.player_color == chess.BLACK and actual_row == 7):
                    for promotion in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                        move = chess.Move(self.selected_square, square, promotion=promotion)
                        if move in self.board.legal_moves:
                            self.show_promotion_dialog(move)
                            return

            move = chess.Move(self.selected_square, square)
            if move in self.board.legal_moves:
                self.make_move(move)
            else:
                if piece and piece.color == self.player_color:
                    self.selected_square = square
                    self.clear_highlights()
                    self.highlight_square(row, col, "selected")
                    self.show_possible_moves(square)
                    file_letter = chr(97 + col)
                    rank_number = 8 - actual_row
                    self.status_label.config(text=f"Re-selected: {file_letter}{rank_number}")
                else:
                    self.selected_square = None
                    self.clear_highlights()
                    self.status_label.config(text="❌ Illegal move")

    def show_possible_moves(self, square):
        self.update_board_display()
        selected_row = 7 - (square // 8)
        selected_col = square % 8
        self.highlight_square(selected_row, selected_col, "selected")

        for move in self.board.legal_moves:
            if move.from_square == square:
                to_row = 7 - (move.to_square // 8)
                to_col = move.to_square % 8
                self.highlight_square(to_row, to_col, "possible")

    def make_move(self, move):
        is_capture = self.board.is_capture(move)
        is_castle = self.board.is_castling(move)
        is_promotion = move.promotion is not None

        self.board.push(move)

        self.play_move_sound(move, is_capture, is_castle, is_promotion)
        self.last_move = move
        self.selected_square = None
        self.clear_highlights()
        self.update_board_display()

        self.add_move_to_history(move, is_player_move=True, is_capture=is_capture)

        if self.check_game_over():
            return

        self.player_turn = False
        self.ai_thinking = True
        self.update_turn_display()
        self.root.update()
        self.root.after(500, self.ai_move)

    def ai_move(self):
        if self.game_over or self.game_paused:
            self.ai_thinking = False
            return

        if self.board.legal_moves:
            move = self.stockfish.get_move(self.board)
            is_capture = self.board.is_capture(move)
            is_castle = self.board.is_castling(move)
            is_promotion = move.promotion is not None

            self.board.push(move)

            self.play_move_sound(move, is_capture, is_castle, is_promotion)
            self.last_move = move
            self.update_board_display()

            self.add_move_to_history(move, is_player_move=False, is_capture=is_capture)

            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            promotion_text = ""
            if move.promotion:
                promotion_names = {chess.QUEEN: "Queen", chess.ROOK: "Rook",
                                   chess.BISHOP: "Bishop", chess.KNIGHT: "Knight"}
                promotion_text = f" promoted to {promotion_names[move.promotion]}"
            self.status_label.config(text=f"AI move: {from_sq} → {to_sq}{promotion_text}")
            print(f"AI move: {from_sq} → {to_sq}{promotion_text}")

        if self.check_game_over():
            self.ai_thinking = False
            return

        if self.board.is_check():
            self.status_label.config(text=f"{'Your' if self.player_turn else 'AI'} king is in check!", fg="#ffd700")

        self.player_turn = True
        self.ai_thinking = False
        self.update_turn_display()

    def update_board_display(self):
        for display_row in range(8):
            for col in range(8):
                if self.board_flipped:
                    actual_row = 7 - display_row
                else:
                    actual_row = display_row

                square = (7 - actual_row) * 8 + col
                piece = self.board.piece_at(square)
                btn = self.buttons[display_row][col]

                if (actual_row + col) % 2 == 0:
                    bg_color = self.colors["light"]
                else:
                    bg_color = self.colors["dark"]

                if self.last_move:
                    if square == self.last_move.from_square or square == self.last_move.to_square:
                        bg_color = self.colors["last_move"]

                if piece:
                    symbol = self.piece_symbols.get(piece.symbol(), '')
                    btn.config(
                        text=symbol,
                        fg="black",
                        bg=bg_color,
                        activebackground=bg_color
                    )
                else:
                    btn.config(
                        text="",
                        bg=bg_color,
                        activebackground=bg_color
                    )

    def highlight_square(self, row, col, highlight_type):
        if highlight_type == "selected":
            color = self.colors["selected"]
        elif highlight_type == "possible":
            color = self.colors["possible"]
        else:
            return
        self.buttons[row][col].config(bg=color, fg="black")

    def clear_highlights(self):
        self.update_board_display()

    def new_game(self):
        if not self.game_over and len(self.move_history) > 0:
            self.player_stats.end_game("loss")

        self.board.reset()
        self.selected_square = None
        self.player_turn = True  # Player always starts if playing white
        if self.player_color == chess.WHITE:
            self.player_turn = True
        else:
            self.player_turn = False  # AI starts if player is black

        self.game_over = False
        self.ai_thinking = False
        self.game_paused = False
        self.pending_promotion = None
        self.last_move = None
        self.current_game_result = None
        self.pause_btn.config(text="⏸️ Pause", bg="#FFA500")

        self.move_history = []
        self.move_count = 1
        self.update_move_history_display()

        if self.promotion_window:
            self.promotion_window.destroy()
            self.promotion_window = None
        self.clear_highlights()
        self.update_board_display()
        self.update_turn_display()

        status_text = f"Playing as {'White' if self.player_color == chess.WHITE else 'Black'}"
        if self.player_color == chess.BLACK:
            status_text += " - AI moves first"
        self.status_label.config(text=status_text)

        self.player_stats.start_game()

        self.current_eval = Evaluation(
            type='cp',
            value=0,
            white_advantage=True,
            display_text="0.00"
        )
        self.draw_eval_bar()

        self.update_player_stats_display()

        # If AI moves first (player is black), start AI move
        if self.player_color == chess.BLACK and not self.game_over:
            self.root.after(500, self.ai_move)

    def exit_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", False)
        self.root.geometry("1400x850")

    def check_game_over(self):
        if self.board.is_game_over():
            self.game_over = True
            self.player_turn = False
            self.ai_thinking = False

            if self.board.is_checkmate():
                self.play_sound("game_end.wav")
                if self.board.turn == chess.WHITE:
                    winner = "Black"
                    winner_is_player = (self.player_color == chess.BLACK)
                else:
                    winner = "White"
                    winner_is_player = (self.player_color == chess.WHITE)

                if winner_is_player:
                    self.current_game_result = "win"
                    self.player_stats.end_game("win")
                    winner_text = f"🏆 You ({winner}) win!"
                else:
                    self.current_game_result = "loss"
                    self.player_stats.end_game("loss")
                    winner_text = f"🏆 AI ({winner}) wins!"

                self.turn_label.config(text=winner_text, fg="#ffd700")
                messagebox.showinfo("Game Over", f"Checkmate! {winner_text}")

            elif self.board.is_stalemate():
                self.play_sound("game_end.wav")
                self.current_game_result = "draw"
                self.player_stats.end_game("draw")
                self.turn_label.config(text="🤝 Draw (Stalemate)", fg="#ffffff")
                messagebox.showinfo("Game Over", "Draw! Stalemate")

            elif self.board.is_insufficient_material():
                self.play_sound("game_end.wav")
                self.current_game_result = "draw"
                self.player_stats.end_game("draw")
                self.turn_label.config(text="🤝 Draw (Insufficient material)", fg="#ffffff")
                messagebox.showinfo("Game Over", "Draw! Insufficient material")

            else:
                self.play_sound("game_end.wav")
                self.current_game_result = "draw"
                self.player_stats.end_game("draw")
                self.turn_label.config(text="🤝 Draw", fg="#ffffff")
                messagebox.showinfo("Game Over", "Draw!")

            self.update_player_stats_display()
            return True
        return False


def main():
    root = tk.Tk()
    game = ChessGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()