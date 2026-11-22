"""Run the cache eval harness on eval/cache_pairs.json and print a Markdown report (T-304).

Usage:
  python scripts/eval_cache.py [--embedder hashing] [--output report.json]
  python scripts/eval_cache.py --embedder ollama --model all-minilm [--url URL] [--output FILE]

The hashing embedder is a lexical baseline and needs no network. The Ollama embedder calls
GET /api/version once and POST /api/embed for each text, with the gateway's own client settings.
The URL can hold credentials, so it is never printed: every failure prints one fixed line.
Exit codes: 0 on success, 1 when the run fails (no report is printed or written), 2 on bad usage.
"""

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import httpx
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # running a script puts scripts/ first, not the repository root
    sys.path.insert(0, str(ROOT))

from app.cache.evaluation import (  # noqa: E402
    DatasetError,
    EvaluationError,
    dataset_sha256,
    evaluate,
    load_pairs,
    render_markdown,
    report_as_json,
)
from app.cache.hashing import HashingEmbedder  # noqa: E402
from app.clock import Clock, SystemClock  # noqa: E402
from app.main import build_embedder  # noqa: E402
from app.providers.errors import ProviderError  # noqa: E402
from app.providers.http_body import read_capped  # noqa: E402
from app.settings import (  # noqa: E402
    DEFAULT_CACHE_EMBEDDER_URL,
    DEFAULT_TTL_SECONDS,
    CacheSettings,
    SettingsError,
)

DATASET_PATH = ROOT / "eval" / "cache_pairs.json"
VERSION_PATH = "/api/version"
VERSION_MAX_BYTES = 4_096
VERSION_PATTERN = re.compile(r"[0-9A-Za-z.+_-]{1,64}")


class ScriptError(Exception):
    """A failure with a fixed message that holds no URL, prompt or reply body."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse repeats unrecognized tokens, and a mistyped flag can be followed by the URL.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments (not repeated: one may hold the URL)"
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Run the cache eval harness.", allow_abbrev=False)
    parser.add_argument("--embedder", choices=["hashing", "ollama"], default="hashing")
    parser.add_argument("--model", help="the Ollama embedding model (required with ollama)")
    parser.add_argument("--url", help=f"the Ollama URL (default {DEFAULT_CACHE_EMBEDDER_URL})")
    parser.add_argument("--output", type=Path, help="also write the report as JSON to this path")
    return parser


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.embedder == "ollama":
        if args.model is None or not args.model.strip():
            parser.error("--model is required with --embedder ollama")
        args.model = args.model.strip()
        if args.url is not None:
            if not args.url.strip():
                parser.error("--url must not be blank")
            args.url = args.url.strip()
    elif args.model is not None or args.url is not None:
        parser.error("--model and --url apply only to --embedder ollama")
    return args


async def fetch_ollama_version(client: httpx.AsyncClient) -> str:
    """The `version` from GET /api/version. Every failure is a ScriptError with a fixed reason."""
    reason: str | None = None
    body = b""
    try:
        async with client.stream("GET", VERSION_PATH) as response:
            if not 200 <= response.status_code < 300:
                reason = f"HTTP {response.status_code}"
            else:
                body = await read_capped(response, VERSION_MAX_BYTES)
    except httpx.TimeoutException:
        reason = "timeout"
    except httpx.HTTPError:  # its message can name the host
        reason = "connection"
    except ProviderError:
        reason = "the reply is too large"
    if reason is None:
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        version = payload.get("version") if isinstance(payload, dict) else None
        if isinstance(version, str) and VERSION_PATTERN.fullmatch(version):
            return version
        reason = "the reply has no valid version"
    raise ScriptError(f"GET {VERSION_PATH} failed: {reason}")


async def _run(
    args: argparse.Namespace, transport: httpx.AsyncBaseTransport | None, clock: Clock
) -> tuple[str, dict[str, object]]:
    try:
        data = DATASET_PATH.read_bytes()
        pairs = load_pairs(data)
    except (OSError, DatasetError) as error:
        message = "cannot read the dataset" if isinstance(error, OSError) else str(error)
        raise ScriptError(message) from None
    digest = dataset_sha256(data)
    version: str | None = None
    try:
        if args.embedder == "hashing":
            report = await evaluate(pairs, HashingEmbedder(), clock)
        else:
            settings = CacheSettings(
                embedder="ollama",
                embedder_model=args.model,
                embedder_url=SecretStr(args.url or DEFAULT_CACHE_EMBEDDER_URL),
                similarity_threshold=0.5,  # unused by build_embedder
                ttl_seconds=DEFAULT_TTL_SECONDS,  # unused by build_embedder
                max_entries=1,  # unused by build_embedder
            )
            try:
                client, embedder = build_embedder(settings, transport)
            except SettingsError:
                raise ScriptError("--url is not a valid URL") from None
            async with client:
                version = await fetch_ollama_version(client)
                report = await evaluate(pairs, embedder, clock)
    except EvaluationError as error:  # its message holds a pair id and an error kind only
        raise ScriptError(str(error)) from None
    return (
        render_markdown(report, dataset_sha256=digest, ollama_version=version),
        report_as_json(report, dataset_sha256=digest, ollama_version=version),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Clock | None = None,
) -> int:
    args = _parse(argv)
    try:
        markdown, report = asyncio.run(_run(args, transport, clock or SystemClock()))
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.output is not None:
        try:
            with args.output.open("w", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(report, indent=2) + "\n")
        except OSError:
            print("error: cannot write the --output file", file=sys.stderr)
            return 1
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
