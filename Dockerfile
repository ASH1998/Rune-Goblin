# Rune Goblin RPG sandbox — Hugging Face Docker Space.
#
# Runs app/rpg_app.py (the Gradio canvas RPG) under uvicorn. No model weights
# ship: the drawn-rune vision model is OFF (RG_USE_MODEL=0 -> deterministic rule
# engine reads glyphs) and NPC dialogue is a remote HTTP call to the Modal API
# (RG_DIALOGUE_API_* set as Space secrets). Small, CPU-only image.

FROM python:3.12-slim

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
