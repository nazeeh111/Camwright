"""Launch the offline Camwright workspace."""
import argparse
import sys
import webbrowser

from .server import make_server
from . import __version__


def main():
    if len(sys.argv)>1 and sys.argv[1] in {'example','check','export','explore','select','replay'}:
        from .cli import main as operation_main
        return operation_main(sys.argv[1:])
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description="Open Camwright's local cam design workspace", epilog="Data operations (JSON stdout):\n  example --out PROJECT       create editable exact inputs\n  check PROJECT               inspect Pass, Fail or Unresolved\n  explore PROJECT             check a declared finite radius grid\n  select REPORT --out PROJECT freshly recheck a chosen pair\n  export PROJECT --out ZIP    recompute certified geometry\n  replay ZIP                  compare with fresh current outputs\nUse camwright COMMAND --help for options.\nExit 0: complete command; inspect geometric status. Exit 3: refusal or unfinished grid.\nExit 2: invalid input, I/O or replay mismatch. Exit 130: interrupted.")
    parser.add_argument("--version", action="version", version=f"Camwright {__version__}")
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
