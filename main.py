import argparse
import os

from app import create_app


def main():
    parser = argparse.ArgumentParser(description="AI News Web Service")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 5000)), help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

