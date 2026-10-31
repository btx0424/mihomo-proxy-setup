"""Entry point: uv run mihomo-web"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("MIHOMO_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("MIHOMO_WEB_PORT", "8765"))
    uvicorn.run(
        "mihomo_web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
