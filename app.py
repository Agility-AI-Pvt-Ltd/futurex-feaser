import sys
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes import router

app = FastAPI(
    title="Feasibility Check - AI Analysis System",
    description="AI-powered startup feasibility analysis using LangGraph & OpenAI",
    version="1.0.0",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("--- INTERNAL SERVER ERROR ---")
    traceback.print_exc(file=sys.stdout)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"},
    )


# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "Feasibility Check API is running"}
