# Running the Chess GUI

`chess_game.py` is a Tkinter front end for the Stockfish engine that is bundled in
`src/` (a complete Stockfish 18 source tree). The GUI does **not** ship a prebuilt
engine, so you need one of the three options below once.

## Requirements

- Python 3.8+
- [`python-chess`](https://python-chess.readthedocs.io/): `python3 -m pip install chess`
- A Stockfish binary (see below)
- macOS only: sound effects use `afplay` (built in)

## 1. Build Stockfish from the bundled source (recommended on this machine)

```bash
# Apple silicon
make -C src -j profile-build ARCH=apple-silicon

# Intel Mac / generic 64-bit x86
make -C src -j profile-build ARCH=x86-64
```

This produces `src/stockfish`, which the GUI finds automatically. The build
downloads the NNUE networks once (`src/nn-*.nnue`); it needs network access, and
the networks are embedded into the binary afterwards. A faster, unoptimised build
for a quick test is `make -C src -j build ARCH=x86-64`.

## 2. Download a release binary

Grab a build from <https://github.com/official-stockfish/Stockfish/releases>,
rename it to the name the GUI looks for, and drop it next to `chess_game.py`:

```bash
mkdir -p stockfish
cp ~/Downloads/stockfish-macos-x86-64 stockfish/          # Intel Mac
cp ~/Downloads/stockfish-macos-arm64  stockfish/          # Apple silicon
chmod +x stockfish/stockfish-macos-x86-64
```

`stockfish/` is git-ignored, so downloaded binaries never end up in commits.

## 3. Point at an existing binary

```bash
STOCKFISH_PATH=/usr/local/bin/stockfish python3 chess_game.py
```

## Run it

```bash
python3 chess_game.py
```

Press `Esc` to leave fullscreen. If no engine can be found, the app now shows a
dialog with these instructions instead of crashing with a traceback.

## How the engine is located

`find_engine()` in `chess_game.py` searches, in order:

1. `$STOCKFISH_PATH`
2. `stockfish/`, the script directory, and `src/` for a platform-matching binary
   (`stockfish-macos-arm64` / `stockfish-macos-x86-64` on macOS, `stockfish.exe`
   on Windows, `stockfish-linux-*` elsewhere), then any `stockfish*` executable
3. `stockfish` on `PATH`

When packaged with PyInstaller (`sys.frozen`), the same search runs inside the
bundle (`sys._MEIPASS`) and next to the executable.
