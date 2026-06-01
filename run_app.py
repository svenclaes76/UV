"""Launch the Streamlit app — run this file directly from PyCharm."""
import subprocess
import sys
from pathlib import Path

venv_streamlit = Path(__file__).parent / ".venv" / "Scripts" / "streamlit.exe"
app = Path(__file__).parent / "app.py"

subprocess.run([str(venv_streamlit), "run", str(app)], check=True)
