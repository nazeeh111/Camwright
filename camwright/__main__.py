"""Launch the offline Camwright workspace."""
import argparse
import webbrowser

from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="Open Camwright's local cam design workspace")
    parser.add_argument("--port", type=int, default=0, help="localhost port; zero chooses a free port")
    parser.add_argument("--no-browser", action="store_true", help="print the URL without opening a browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be from 0 through 65535")
    try:
        server = make_server(args.port)
    except OSError as error:
        parser.exit(2, f"camwright: cannot open localhost server: {error}\n")
    url = server.expected_origin+"/"
    print(f"Camwright: {url}\nPress Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.calculator.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
