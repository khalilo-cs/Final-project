from fastapi import FastAPI

from app.routes import speech

app = FastAPI(title="Mihakk — Speech Service", version="0.1.0")
app.include_router(speech.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "speech-service"}
