# ASAV install troubleshooting

## Error: "Could not build wheels for yara-python" / "wheel is not installed"

This usually means you are on **Python 3.14**. Pip downloads source code and tries to compile `yara-python`, which fails on Windows without Visual C++ Build Tools.

**Fix:** run `install.bat` again. It installs Python 3.12 automatically if needed.

Manual options:

```bat
py install 3.12
```

or

```bat
winget install Python.Python.3.12
```

Then:

```bat
install.bat
run_asav.bat
```

## Error: "Microsoft Visual C++ 14.0 or greater is required"

Same root cause: pip is compiling `yara-python` from source because no wheel exists for your Python version.

Use Python **3.12** or **3.13** instead of 3.14.

## Verify your Python version

```bat
py -0p
py -3.12 --version
```

You want a line like `3.12` in the list before running install.

## "No module named customtkinter" but install seemed fine

You installed packages into a **different Python** than the one running ASAV.

- `pip install` alone often uses **Python 3.14** (your default `*`)
- `run_asav.bat` may use **3.13** via `py -3.13`
- Result: missing `customtkinter` at runtime

**Fix:** run `install.bat` only. It creates `.venv` and installs everything there. Then use `run_asav.bat`.

## Manual install with Python 3.12 or 3.13

```bat
cd c:\Users\Angga\Documents\ASAV
install.bat
run_asav.bat
```

Or:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

**Never use:** `pip install -r requirements.txt` without `py -3.12 -m pip` or `.venv\Scripts\python.exe -m pip`
