#!/usr/bin/env python3
"""Open (or refresh) the GitLab merge request for the package-update branch.

Used by the scheduled ``update-packages`` CI job. Reads the GitLab
credentials + API location from the standard CI environment variables
(``GL_TOKEN`` project access token with api scope, ``CI_API_V4_URL``,
``CI_PROJECT_ID``, ``CI_DEFAULT_BRANCH``).

argv[1] = source branch (ci/update-packages)
argv[2] = optional path to the markdown report (package-update-report.md)

The branch is a single, long-lived branch: if an open MR for it already
exists, its description is refreshed with the new report instead of
opening a duplicate MR.
"""
import json
import os
import sys
import urllib.request
from urllib.parse import quote


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <source-branch> [report-file]", file=sys.stderr)
        return 2
    branch = sys.argv[1]
    report_path = sys.argv[2] if len(sys.argv) > 2 else None
    for var in ("GL_TOKEN", "CI_API_V4_URL", "CI_PROJECT_ID"):
        if not os.environ.get(var):
            print(f"error: environment variable {var} is required", file=sys.stderr)
            return 1

    description = None
    if report_path:
        try:
            description = open(report_path).read().rstrip()
        except OSError as exc:
            print(
                f"warning: could not read report {report_path}: {exc}", file=sys.stderr
            )

    base = f"{os.environ['CI_API_V4_URL']}" f"/projects/{os.environ['CI_PROJECT_ID']}"
    headers = {"Authorization": f"Bearer {os.environ['GL_TOKEN']}"}

    # Reuse the open MR if this branch already has one (it does after the
    # first run - the branch is long-lived by design).
    req = urllib.request.Request(
        f"{base}/merge_requests?state=opened&source_branch={quote(branch)}",
        headers=headers,
    )
    open_mrs = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if open_mrs:
        mr = open_mrs[0]
        if description is not None:
            body = json.dumps({"description": description}).encode()
            req = urllib.request.Request(
                f"{base}/merge_requests/{mr['iid']}",
                data=body,
                method="PUT",
                headers={**headers, "Content-Type": "application/json"},
            )
            json.loads(urllib.request.urlopen(req, timeout=30).read())
        print(
            f"MR !{mr['iid']} already open for {branch} - description refreshed: {mr['web_url']}"
        )
        return 0

    url = f"{base}/merge_requests"
    body = json.dumps(
        {
            "source_branch": branch,
            "target_branch": os.environ.get("CI_DEFAULT_BRANCH", "main"),
            "title": "chore: update pip/apk packages (minor/patch only)",
            "description": description
            or "Automated package update (report missing, see pipeline log).",
            "labels": ["requirements-update"],
            "remove_source_branch": True,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    print(f"created MR !{data['iid']}: {data['web_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
