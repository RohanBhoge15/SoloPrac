FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# libmagic1 is required by python-magic (ctypes wrapper) for file-type sniffing.
# espeak-ng is the phonemization engine used by misaki (Kokoro TTS) and the
# universal TTS fallback.
# g++ is required by torch.compile / torch._inductor to JIT-compile CPU
# kernels — without it Docling first-parse spams InvalidCxxCompiler warnings
# and falls back to slow eager mode.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libmagic1 \
    espeak-ng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# torch: CPU-only build (this stack has no NVIDIA GPU). Installing it first
# with the CPU index satisfies the `torch>=2.4.0` requirement in pyproject.toml,
# so `pip install -e .` reuses it instead of pulling the ~3 GB CUDA wheel.
COPY pyproject.toml .
RUN pip install "torch>=2.4.0" --index-url https://download.pytorch.org/whl/cpu \
    && pip install -e "."
# torchvision MUST use the CPU custom-op build. The default PyPI wheel fails with
# "operator torchvision::nms does not exist" under the CPU torch wheel, which breaks
# MedCPT/BGE-M3 embeddings (and thus Qdrant indexing + vector RAG). Installing the
# +cpu build explicitly keeps it pinned across image rebuilds.
RUN pip install "torchvision==0.28.0+cpu" --index-url https://download.pytorch.org/whl/cpu

# Install spacy model for misaki (Kokoro G2P)
RUN python -m spacy download en_core_web_sm

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# Copy application code
COPY . .

EXPOSE 8000

# curl is NOT installed in python:3.11-slim, so use urllib (same check the
# backend service overrides with in docker-compose.yml).
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
    CMD python -c "import urllib.request; exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live').status == 200 else 1)"

# Production CMD: 4 workers + uvloop + httptools for real multi-tenant concurrency.
# With 4 workers, 30 doctors can be served in parallel without one long request
# (PDF gen, OCR, RAG) starving the others.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
