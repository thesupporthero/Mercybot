from __future__ import annotations

import aiohttp.web

from .public import routes as public_routes
from .auth import routes as auth_routes
from .dashboard import routes as dashboard_routes


def setup_routes(app: aiohttp.web.Application) -> None:
    """Register all route handlers."""
    app.router.add_routes(public_routes)
    app.router.add_routes(auth_routes)
    app.router.add_routes(dashboard_routes)
