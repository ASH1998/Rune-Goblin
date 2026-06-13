# Rune Goblin RPG sandbox — Hugging Face Docker Space.
#
# Runs app/rpg_app.py (the Gradio canvas RPG) under uvicorn. No model weights
# ship: the drawn-rune vision model is OFF (RG_USE_MODEL=0 -> deterministic rule
# engine reads glyphs) and NPC dialogue is a remote HTTP call to the Modal API
# (RG_DIALOGUE_API_* set as Space secrets). Small, CPU-only image.

FROM python:3.12-slim

# git is needed by HF "Dev Mode": when enabled, HF appends build steps
# (openvscode-server + `git config --global ...`) after our COPYs, and the slim
# base ships no git -> the build fails with "git: not found". Install it as root
# before dropping to the unprivileged user. Harmless when Dev Mode is off.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces run containers as uid 1000.
RUN useradd -m -u 1000 user
USER user

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/user/.local/bin:$PATH" \
    # vision model OFF -> rule engine reads drawn glyphs (no weights needed)
    RG_USE_MODEL=0 \
    # NPC dialogue ON -> remote Modal API (configure via Space secrets)
    RG_USE_DIALOGUE_API=1 \
    # HF Spaces expect the app on port 7860
    GRADIO_SERVER_PORT=7860 \
    PYTHONPATH=/home/user/app:/home/user/app/src

WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user src ./src
COPY --chown=user app ./app

EXPOSE 7860
CMD ["uvicorn", "app.rpg_app:app", "--host", "0.0.0.0", "--port", "7860"]
