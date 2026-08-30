# Starts the Streamlit frontend (School AI) on http://localhost:8501
Set-Location "$PSScriptRoot\frontend"
python -m streamlit run app.py --server.port 8501
