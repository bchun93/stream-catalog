"""Echo browser Origin on every response so Amplify → Render CORS always succeeds."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class EchoOriginCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")

        if request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            response = await call_next(request)

        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"
            )
            requested = request.headers.get("access-control-request-headers")
            response.headers["Access-Control-Allow-Headers"] = (
                requested if requested else "Content-Type, Accept, Authorization, Origin"
            )
            response.headers["Access-Control-Max-Age"] = "86400"
            response.headers["Vary"] = "Origin"

        return response
