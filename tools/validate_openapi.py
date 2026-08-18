import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

OPENAPI_DIR = Path(__file__).resolve().parent.parent / "yoxa" / "openapi"

METHODS = {"get", "post", "put", "patch", "delete"}


def validate(path: Path) -> list[str]:
    errors = []
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return ["document is not a mapping"]
    if doc.get("openapi") != "3.1.0":
        errors.append("openapi must be 3.1.0")
    servers = doc.get("servers")
    if not isinstance(servers, list) or len(servers) != 1:
        errors.append("exactly one server required")
    else:
        url = servers[0].get("url", "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            errors.append(f"server url scheme invalid: {url}")
        if parsed.path not in ("", "/"):
            errors.append(f"server url must be origin only, has path: {url}")
    paths = doc.get("paths") or {}
    if len(paths) != 1:
        errors.append(f"exactly one path operation required, found {len(paths)}")
    else:
        for p, ops in paths.items():
            if not isinstance(ops, dict) or len(ops) != 1:
                errors.append(f"path {p}: exactly one method required")
                continue
            method, op = next(iter(ops.items()))
            if method.lower() not in METHODS:
                errors.append(f"path {p}: method {method} unsupported")
            if not op.get("operationId"):
                errors.append(f"path {p}: missing operationId")
            responses = op.get("responses") or {}
            if not any(code.startswith("2") for code in responses):
                errors.append(f"path {p}: no 2xx response documented")
    return errors


def main() -> int:
    files = sorted(OPENAPI_DIR.glob("*.openapi.yml"))
    total_errors = 0
    for f in files:
        errors = validate(f)
        total_errors += len(errors)
        status = "PASS" if not errors else "FAIL"
        print(f"{status}  {f.name}")
        for e in errors:
            print(f"    - {e}")
    print(f"\n{len(files)} files, {total_errors} errors")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
