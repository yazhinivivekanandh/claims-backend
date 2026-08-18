from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import API_TOKEN, APP_HOST, APP_PORT
from .db import init_db
from .seed import seed_if_empty
from .routers import intake, clinical, billing, claims, queries, trigger

app = FastAPI(
    title="Inpatient Discharge and Cashless Claims API",
    description="Backend for the Seven-Step Inpatient Discharge and Cashless Claims workflow.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_if_empty()


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(intake.router, prefix="/api")
app.include_router(clinical.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(claims.router, prefix="/api")
app.include_router(queries.router, prefix="/api")
app.include_router(trigger.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)
