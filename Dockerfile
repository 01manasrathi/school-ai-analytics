# Container image for the Student Analytics dashboard.
#
# Streamlit Community Cloud does not need this (it builds from requirements.txt
# directly). It is here for any Docker-based host — Render, Railway, Fly.io,
# Koyeb, a Hugging Face Docker Space, or a plain VPS.
#
#   docker build -t school-ai-analytics .
#   docker run --rm -p 8501:8501 school-ai-analytics
#
# Only the dashboard's runtime dependencies are installed (see
# requirements-space.txt), not the School AI FastAPI backend's, which keeps the
# image small and the build fast.
FROM python:3.11-slim

# Run as UID 1000 (the convention on most managed container hosts). Matching it
# keeps /app writable, which the dashboard needs for generated PDF report cards.
RUN useradd -m -u 1000 user

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user:user requirements-space.txt ./
RUN pip install --upgrade pip && pip install -r requirements-space.txt

COPY --chown=user:user . .

USER user
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "student_analytics/dashboard/Home.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
