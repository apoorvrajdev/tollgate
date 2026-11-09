from fastapi import FastAPI

app = FastAPI(title="Tollgate")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
