"""Local launcher; optionally share only the Node API's recognition secret."""
import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Read RECOGNITION_API_KEY from this existing dotenv file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            parser.error("The specified environment file does not exist")
        key = dotenv_values(args.env_file).get("RECOGNITION_API_KEY")
        if not key or not key.strip():
            parser.error("The environment file must contain RECOGNITION_API_KEY")
        os.environ["RECOGNITION_API_KEY"] = key
    uvicorn.run("recognition_service.main:app", host=args.host, port=args.port,
                workers=1, limit_concurrency=8, timeout_keep_alive=5, access_log=False)


if __name__ == "__main__":
    main()
