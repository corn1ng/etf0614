@echo off
cd /d "%~dp0.."
".venv-win\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false > logs\streamlit.out.log 2> logs\streamlit.err.log
