#!/usr/bin/env python3
"""Validate frontend API calls against backend endpoint definitions.

Auto-discovers:
  - Backend endpoints by reading router file decorators
  - Frontend API calls from axios/fetch patterns in source
  - Reports mismatches: methods, paths, double-prefix, raw-fetch

Usage:
    python testing/validate_endpoints.py
    python testing/validate_endpoints.py --fix     # print fix suggestions
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend" / "app"
FRONTEND_DIR = ROOT / "frontend" / "src"
API_BASE = "/api/v1"

# Colors for output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

pass_count = 0
fail_count = 0
warn_count = 0


def ok(msg: str):
    global pass_count
    pass_count += 1
    print(f"  {GREEN}OK{RESET} {msg}")


def fail(msg: str, fix: str = ""):
    global fail_count
    fail_count += 1
    output = f"  {RED}FAIL{RESET} {msg}"
    if fix:
        output += f"\n       {CYAN}Fix:{RESET} {fix}"
    print(output)


def warn(msg: str):
    global warn_count
    warn_count += 1
    print(f"  {YELLOW}(!){RESET} {msg}")


# ── Backend Discovery ───────────────────────────────────────

ROUTER_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}


class BackendRoute:
    def __init__(self, method: str, path: str, file: str, line: int):
        self.method = method.upper()
        self.path = path
        self.file = file
        self.line = line

    def normalized_path(self) -> str:
        p = re.sub(r"\{[^}:]*(?::[^}]+)?\}", "{param}", self.path).rstrip("/")
        return p or "/"

    def __repr__(self):
        return f"{self.method} {self.path}"


def _resolve_router_prefix(lines: List[str], router_var: str = "router") -> str:
    """Extract the prefix from `router_var = APIRouter(prefix=...)`."""
    for line in lines:
        m = re.search(
            rf"{re.escape(router_var)}\s*=\s*APIRouter\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']",
            line,
        )
        if m:
            return m.group(1)
    return ""


def _resolve_router_mounts() -> Dict[str, str]:
    """Read routers/__init__.py to find mount paths for every included router variable.

    Returns dict like: {"auth.router": "/auth", "portal.public_router": "", ...}
    """
    init_path = BACKEND_DIR / "routers" / "__init__.py"
    if not init_path.exists():
        return {}
    text = init_path.read_text(encoding="utf-8")
    mounts: Dict[str, str] = {}
    # Match: include_router(module.router_var, prefix="...", ...)
    for m in re.finditer(
        r"include_router\((\w+(?:\.\w+)?)\s*(?:,\s*prefix\s*=\s*[\"']([^\"']+)[\"'])?",
        text,
    ):
        var_path = m.group(1)  # e.g. "auth" or "portal.public"
        prefix = m.group(2) or ""
        mounts[var_path] = prefix
    return mounts


def _find_file_routers(lines: List[str]) -> Dict[str, str]:
    """Find all router variables in a file and their inline APIRouter prefixes.
    
    Returns: {"router": "/patients/{patient_id}/certificates", "public_router": "/public", ...}
    """
    result: Dict[str, str] = {}
    for line in lines:
        m = re.search(r"^(\w+)\s*=\s*APIRouter\(([^)]*)\)", line)
        if m:
            var = m.group(1)
            args = m.group(2)
            pm = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', args)
            result[var] = pm.group(1) if pm else ""
    return result


def discover_backend() -> List[BackendRoute]:
    routes: List[BackendRoute] = []
    routers_dir = BACKEND_DIR / "routers"
    if not routers_dir.exists():
        print(f"  {YELLOW}(!) Backend routers dir not found: {routers_dir}{RESET}")
        return routes

    # Read __init__.py to get mount prefixes per module
    # e.g. include_router(auth.router, prefix="/auth")  ->  "auth.router": "/auth"
    # e.g. include_router(certificates.router, ...)     ->  "certificates.router": ""
    mounts = _resolve_router_mounts()

    # Build: module_name -> { router_var -> mount_prefix_from_init }
    init_prefixes: Dict[str, Dict[str, str]] = {}
    for var_path, mount_prefix in mounts.items():
        parts = var_path.split(".")
        module_name = parts[0]
        router_var = parts[1] if len(parts) > 1 else "router"
        init_prefixes.setdefault(module_name, {})[router_var] = mount_prefix

    for fpath in sorted(routers_dir.glob("*.py")):
        if fpath.name == "__init__.py":
            continue
        module_name = fpath.stem  # "certificates" -> "certificates.py"
        text = fpath.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Find all router vars and their file-level prefixes
        # e.g. "router" -> "/patients/{patient_id}/certificates"
        file_prefixes = _find_file_routers(lines)

        # Merge: prefer init mount_prefix if non-empty, else use file-level prefix
        module_init = init_prefixes.get(module_name, {})
        effective_prefixes: Dict[str, str] = {}
        for rv, fp in file_prefixes.items():
            init_p = module_init.get(rv, "")
            effective_prefixes[rv] = init_p if init_p else fp

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for method in ROUTER_METHODS:
                pattern = rf'@(\w+)\.{method}\(\s*["\']([^"\']*)["\']'
                for m in re.finditer(pattern, stripped):
                    router_var = m.group(1)
                    path = m.group(2)
                    full_path = effective_prefixes.get(router_var, "") + path
                    routes.append(
                        BackendRoute(method, full_path, fpath.name, i)
                    )
    return routes


# ── Frontend Discovery ──────────────────────────────────────


class FrontendCall:
    def __init__(
        self,
        method: str,
        url: str,
        file: str,
        line: int,
        uses_api_client: bool,
        raw_line: str = "",
    ):
        self.raw_url = url.strip().strip("'\"`")
        self.file = file
        self.line = line
        self.uses_api_client = uses_api_client

        self.method = method.upper()

    @property
    def url(self) -> str:
        """Return the URL relative to API_BASE (strip /api/v1 if present)."""
        u = self.raw_url
        if u.startswith(API_BASE):
            u = u[len(API_BASE):] or "/"
        return u

    def effective_url(self) -> str:
        """The actual URL the browser will send (after apiClient base)."""
        if self.uses_api_client:
            base = API_BASE.rstrip("/")
            return base + ("/" + self.raw_url.lstrip("/") if self.raw_url else "")
        return self.raw_url

    def normalized_path(self) -> str:
        """Normalize for comparison: replace template vars and strip trailing slash."""
        p = re.sub(r"\$\{[^}]+\}", "{param}", self.url).rstrip("/")
        return p or "/"

    def has_double_prefix(self) -> bool:
        """Check if apiClient call has /api/v1 hardcoded in the path."""
        if not self.uses_api_client:
            return False
        return self.raw_url.startswith(API_BASE)

    def __repr__(self):
        return f"{self.method} {self.raw_url}"


def discover_frontend() -> List[FrontendCall]:
    calls: List[FrontendCall] = []
    api_client_patterns = [
        (True, r"apiClient\.(get|post|put|patch|delete)\(\s*([`'\"])"),
        (False, r"\bfetch\(\s*([`'\"])"),
    ]

    for fpath in sorted(FRONTEND_DIR.rglob("*")):
        if not fpath.is_file() or fpath.suffix not in (".ts", ".tsx"):
            continue
        text = fpath.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        rel = fpath.relative_to(FRONTEND_DIR)

        for uses_api, pattern in api_client_patterns:
            for i, line in enumerate(lines, 1):
                for m in re.finditer(pattern, line):
                    method = m.group(1) if uses_api else "GET"
                    # For raw fetch(), check the same line and next line for method: 'VERB'
                    if not uses_api:
                        method_line = line
                        if i < len(lines):
                            method_line += "\n" + lines[i]  # peek next line
                        m_method = re.search(r"method\s*:\s*['\"](\w+)['\"]", method_line, re.DOTALL)
                        if m_method:
                            method = m_method.group(1)
                        else:
                            method = "GET"  # fetch() defaults to GET
                    # Find the full URL string
                    quote = m.group(2) if uses_api else m.group(1)
                    rest = line[m.end():]
                    url_match = re.match(rf"([^\\{quote}]*(?:\\.[^\\{quote}]*)*)", rest)
                    if url_match:
                        url = url_match.group(1)
                        url = re.sub(r"['\"`,\s\)]+$", "", url)
                        if url.strip():
                            calls.append(
                                FrontendCall(method, url, str(rel), i, uses_api, raw_line=line)
                            )
    return calls


# ── Comparison ──────────────────────────────────────────────

def normalize_for_match(path: str) -> str:
    """Normalize both backend and frontend paths to a common pattern."""
    p = re.sub(r"\{[^}:]*(?::[^}]+)?\}", "{param}", path)
    p = re.sub(r"\$\{[^}]+\}", "{param}", p)
    p = p.rstrip("/")
    return p or "/"


def match_backend_route(
    frontend_call: FrontendCall,
    backend_routes: List[BackendRoute],
) -> Optional[BackendRoute]:
    """Find matching backend route by normalized path and method."""
    fnorm = normalize_for_match(frontend_call.normalized_path())
    for br in backend_routes:
        bnorm = normalize_for_match(br.normalized_path())
        if fnorm == bnorm:
            if frontend_call.method == br.method:
                return br
            # Store the method mismatch finding but keep looking for exact match
            # Actually return the first path match so we can report method mismatch
    # Method didn't match, but return first path match for error reporting
    for br in backend_routes:
        bnorm = normalize_for_match(br.normalized_path())
        if fnorm == bnorm:
            return br
    return None


def validate():
    global pass_count, fail_count, warn_count
    pass_count = fail_count = warn_count = 0

    print(f"\n{BOLD}--- Backend Endpoint Discovery ---{RESET}\n")
    backend_routes = discover_backend()
    if not backend_routes:
        print(f"  {YELLOW}(!) No backend routes discovered{RESET}")
        return

    # Deduplicate and sort
    seen = set()
    unique_routes = []
    for r in backend_routes:
        key = (r.method, r.path)
        if key not in seen:
            seen.add(key)
            unique_routes.append(r)
    backend_routes = unique_routes

    for r in sorted(backend_routes, key=lambda x: (x.path, x.method)):
        print(f"  {CYAN}{r.method:7s}{RESET} {r.path}  ({r.file}:{r.line})")
    ok(f"Discovered {len(backend_routes)} unique backend endpoints")

    print(f"\n{BOLD}--- Frontend API Call Discovery ---{RESET}\n")
    frontend_calls = discover_frontend()
    if not frontend_calls:
        print(f"  {YELLOW}(!) No frontend API calls discovered{RESET}")
        return

    for c in sorted(frontend_calls, key=lambda x: x.file):
        client_str = f"apiClient.{c.method.lower()}" if c.uses_api_client else "fetch"
        print(f"  {CYAN}{client_str:30s}{RESET} {c.raw_url:60s}  ({c.file}:{c.line})")
    ok(f"Discovered {len(frontend_calls)} frontend API calls")

    print(f"\n{BOLD}--- Validation Results ---{RESET}\n")

    # Check each frontend call
    frontend_checked: List[FrontendCall] = []
    for fc in frontend_calls:
        frontend_checked.append(fc)

        # Check 1: Double /api/v1 prefix
        if fc.has_double_prefix():
            fixed = fc.raw_url.replace(API_BASE, "", 1)
            fail(
                f"{fc.file}:{fc.line} - {fc.method} \"{fc.raw_url}\" has double /api/v1 prefix "
                f"(apiClient already prepends it)",
                fix=f'Change to: apiClient.{fc.method.lower()}("{fixed}")',
            )
            continue

        # Check 2: Raw fetch usage (suggest migration)
        if not fc.uses_api_client:
            warn(
                f"{fc.file}:{fc.line} - uses raw fetch() instead of apiClient "
                f"(bypasses auth interceptor, token refresh)"
            )

        # Check 3: Path + method match against backend
        matched_route = match_backend_route(fc, backend_routes)
        if matched_route is None:
            fail(
                f"{fc.file}:{fc.line} - {fc.method} \"{fc.raw_url}\" "
                f"has no matching backend endpoint",
                fix="Check the path spelling or add the missing backend route",
            )
            continue

        # Check 4: Method match
        fnorm = normalize_for_match(fc.normalized_path())
        bnorm = normalize_for_match(matched_route.normalized_path())
        if fnorm == bnorm and fc.method != matched_route.method:
            fail(
                f"{fc.file}:{fc.line} - {fc.method} \"{fc.raw_url}\" "
                f"method mismatch: backend expects {matched_route.method}",
                fix=f'Change to: {matched_route.method.lower()}("{fc.raw_url}") '
                    f'(or fix backend in {matched_route.file}:{matched_route.line})',
            )
            continue

        ok(f"{fc.file}:{fc.line} - {fc.method} {fc.raw_url} matches backend")

    # Check 4: Orphaned backend routes (not called by frontend)
    print(f"\n{BOLD}--- Orphaned Backend Routes ---{RESET}\n")
    orphaned_count = 0
    for br in backend_routes:
        # Skip evaluation/ routes and admin/ routes (not called from frontend directly)
        if br.path.startswith("/evaluation") or br.path.startswith("/admin"):
            continue
        matched = False
        for fc in frontend_calls:
            fnorm = normalize_for_match(fc.normalized_path())
            bnorm = normalize_for_match(br.normalized_path())
            if fnorm == bnorm:
                matched = True
                break
        if not matched:
            orphaned_count += 1
            warn(f"{br.file}:{br.line} - {br.method} {br.path} has no frontend caller")

    if orphaned_count == 0:
        ok("No orphaned backend routes")

    # Summary
    print(f"\n{BOLD}--- Summary ---{RESET}")
    total = pass_count + fail_count + warn_count
    print(f"  Passed: {GREEN}{pass_count}{RESET}")
    print(f"  Failed: {RED}{fail_count}{RESET}")
    print(f"  Warnings: {YELLOW}{warn_count}{RESET}")
    print(f"  Total checks: {total}")
    print()

    return fail_count


if __name__ == "__main__":
    errors = validate()
    if errors:
        print(f"{RED}!! {errors} validation error(s) found{RESET}")
    else:
        print(f"{GREEN}All endpoint validations passed{RESET}")
    sys.exit(1 if errors else 0)
