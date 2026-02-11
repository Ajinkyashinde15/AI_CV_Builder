from fastapi import FastAPI
from .routers import resume
# app/main.py (before creating FastAPI app)
import logging
import os
from logging.config import dictConfig

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": LOG_LEVEL,
        }
    },
    "loggers": {
        "": {  # root
            "handlers": ["default"],
            "level": LOG_LEVEL,
        },
        "uvicorn": {
            "handlers": ["default"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["default"],
            "level": os.getenv("ACCESS_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
        "resume_app": {
            "handlers": ["default"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    }
})

app = FastAPI(
title="AI CV Builder",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json"
)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(resume.router)
