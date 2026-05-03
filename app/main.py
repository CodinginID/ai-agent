import uvicorn

from app.bot import main as run_polling
from app.config import settings
from app.interfaces.gateway import app as gateway_app


def main() -> None:
    if settings.enable_webhook:
        uvicorn.run(
            gateway_app,
            host="0.0.0.0",
            port=settings.port,
            log_level="info",
        )
    else:
        run_polling()


if __name__ == "__main__":
    main()
