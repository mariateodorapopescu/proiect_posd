FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /experiment
COPY requirements-lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-lock.txt \
    && useradd --create-home --uid 10001 experiment
COPY measure.py analyze.py test_experiment.py ./
USER experiment
CMD ["python", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"]
