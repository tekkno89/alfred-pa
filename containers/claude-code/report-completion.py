#!/usr/bin/env python3
"""Report container completion to the backend.

Supports three methods:
  - callback: HTTP POST to backend endpoint with HMAC token
  - redis:    PUBLISH to Redis channel via redis-cli
  - gcp_pubsub: POST to GCP Pub/Sub REST API with OAuth token

Uses only stdlib + subprocess (redis-cli / curl) to avoid extra deps.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error


def read_output_files(output_dir: str) -> dict[str, str]:
    """Read all files from the output directory into a dict."""
    files = {}
    if not os.path.isdir(output_dir):
        return files
    for name in os.listdir(output_dir):
        path = os.path.join(output_dir, name)
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    files[name] = f.read()
            except (UnicodeDecodeError, OSError):
                pass  # Skip binary or unreadable files
    return files


def report_callback(payload: dict) -> None:
    """POST to backend callback endpoint."""
    url = os.environ.get("CALLBACK_URL")
    token = os.environ.get("CALLBACK_TOKEN")
    if not url or not token:
        print("CALLBACK_URL or CALLBACK_TOKEN not set, skipping callback", file=sys.stderr)
        return

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Callback-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Callback response: {resp.status}")
    except urllib.error.URLError as e:
        print(f"Callback failed: {e}", file=sys.stderr)
        sys.exit(1)


def report_redis(payload: dict) -> None:
    """PUBLISH to Redis channel via redis-cli."""
    redis_url = os.environ.get("REDIS_URL", "")
    topic = os.environ.get("COMPLETION_TOPIC", "")
    if not redis_url or not topic:
        print("REDIS_URL or COMPLETION_TOPIC not set, skipping redis", file=sys.stderr)
        return

    channel = f"alfred:events:{topic}"
    message = json.dumps(payload)

    # Parse redis URL: redis://host:port
    url_part = redis_url.replace("redis://", "")
    host, _, port = url_part.partition(":")
    port = port or "6379"

    cmd = ["redis-cli", "-h", host, "-p", port, "PUBLISH", channel, message]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        print(f"redis-cli failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"Published to Redis channel {channel}")


def report_gcp_pubsub(payload: dict) -> None:
    """POST to GCP Pub/Sub REST API."""
    import base64

    project = os.environ.get("GCP_PUBSUB_PROJECT", "")
    topic = os.environ.get("COMPLETION_TOPIC", "")
    if not project or not topic:
        print("GCP_PUBSUB_PROJECT or COMPLETION_TOPIC not set, skipping pubsub", file=sys.stderr)
        return

    # Get access token via gcloud
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"gcloud auth failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    access_token = result.stdout.strip()

    # Pub/Sub REST API
    url = (
        f"https://pubsub.googleapis.com/v1/"
        f"projects/{project}/topics/{topic}:publish"
    )
    message_data = base64.b64encode(json.dumps(payload).encode()).decode()
    body = json.dumps({"messages": [{"data": message_data}]}).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Pub/Sub response: {resp.status}")
    except urllib.error.URLError as e:
        print(f"Pub/Sub publish failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Report container completion")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--output-dir", default="/output")
    parser.add_argument("--method", default="callback",
                        choices=["callback", "redis", "gcp_pubsub"])
    args = parser.parse_args()

    mode = os.environ.get("MODE", "unknown")
    success = args.exit_code == 0
    output_files = read_output_files(args.output_dir) if success else {}

    payload = {
        "job_id": args.job_id,
        "success": success,
        "exit_code": args.exit_code,
        "output_files": output_files,
        "error": None if success else f"Container exited with code {args.exit_code}",
        "logs": None,
        "mode": mode,
    }

    reporters = {
        "callback": report_callback,
        "redis": report_redis,
        "gcp_pubsub": report_gcp_pubsub,
    }
    reporters[args.method](payload)


if __name__ == "__main__":
    main()
