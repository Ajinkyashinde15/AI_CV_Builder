"""
Lambda handler for FastAPI application.
Adapts API Gateway events to FastAPI ASGI application.
"""

from mangum import Mangum
from app.main import app

# Mangum adapter converts API Gateway events to ASGI
handler = Mangum(app, lifespan="off")

# ALB-style handler support
alb_handler = Mangum(app, lifespan="off")
