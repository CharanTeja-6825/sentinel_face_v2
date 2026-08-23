FROM python:3.11-slim

# build-essential: insightface 0.7.3 ships no arm64 wheel and compiles from
#   source, against numpy headers, at install time.
# libglib2.0-0 / libgomp1: opencv-python-headless and onnxruntime runtime deps.
# curl: /health probing from the compose healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# numpy + cython must exist BEFORE insightface's setup.py runs, or the build
# fails on a missing numpy include path.
RUN pip install --no-cache-dir numpy==1.26.4 cython==3.0.11

COPY requirements.txt requirements-mediapipe.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --no-deps is load-bearing: mediapipe declares opencv-contrib-python, which would
# shadow the headless cv2 installed above and then fail on a missing libGL. See the
# header of requirements-mediapipe.txt.
RUN pip install --no-cache-dir --no-deps -r requirements-mediapipe.txt \
 && python -c "from mediapipe.tasks.python import vision; import cv2; \
               print('mediapipe + headless cv2', cv2.__version__)"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
