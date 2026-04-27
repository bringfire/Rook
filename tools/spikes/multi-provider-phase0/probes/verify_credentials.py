from __future__ import annotations

import httpx

from harness.capture import CaptureContext, write_manifest, write_redacted
from harness.env import load_keys, require_key


def main() -> None:
    keys = load_keys()
    # Each entry: (provider, key env name, key value, probe URL, proves_auth).
    # proves_auth=False means the URL is public/catalog and 200 does not validate the key —
    # the kickoff prereq must be satisfied by the first paid probe (e.g. P1) instead.
    checks = [
        ("fal", "FAL_KEY", keys.fal, "https://fal.ai/models", False),
        ("replicate", "REPLICATE_API_TOKEN", keys.replicate, "https://api.replicate.com/v1/models", True),
        ("gemini", "GOOGLE_API_KEY", keys.google, "https://generativelanguage.googleapis.com/v1beta/models", True),
    ]
    failures: list[str] = []
    with httpx.Client(timeout=30) as client:
        for provider, key_name, key_value, url, proves_auth in checks:
            if key_value is None and provider == "gemini":
                print("gemini: skipped; GOOGLE_API_KEY absent")
                continue
            key = require_key(key_name, key_value)
            headers = _headers(provider, key)
            ctx = CaptureContext(
                probe_id=f"auth_{provider}",
                provider=provider,
                model_id="auth-check",
                catalog_url=url,
                price_observed="non-generating auth/list check",
            )
            response = client.get(url, headers=headers)
            write_redacted("auth_check", {"method": "GET", "url": url, "headers": headers}, response, ctx)

            if not proves_auth:
                # Endpoint is public — 200 only confirms reachability and that a key value is present in .env,
                # NOT that the key is valid. The kickoff gate is partially unsatisfied; flag explicitly.
                write_manifest(
                    ctx,
                    "auth_only_unproven",
                    {
                        "status_code": response.status_code,
                        "reason": "endpoint_is_public_catalog",
                        "next_validation": "first paid probe (e.g. P1) must succeed before claiming kickoff prereq satisfied",
                    },
                )
                print(
                    f"{provider}: status={response.status_code}; "
                    "key present but auth NOT verified by this endpoint (auth_only_unproven)"
                )
                continue

            ok = response.is_success or (provider == "gemini" and response.status_code == 405)
            write_manifest(
                ctx,
                "complete" if ok else "blocked",
                {"status_code": response.status_code, "auth_check_ok": ok},
            )
            print(f"{provider}: status={response.status_code}; ok={ok}")
            if not ok:
                failures.append(provider)

    if failures:
        joined = ", ".join(failures)
        raise SystemExit(f"Credential checks failed for: {joined}")


def _headers(provider: str, key: str) -> dict[str, str]:
    if provider == "fal":
        return {"Authorization": f"Key {key}"}
    if provider == "replicate":
        return {"Authorization": f"Token {key}"}
    if provider == "gemini":
        return {"x-goog-api-key": key}
    raise ValueError(provider)


if __name__ == "__main__":
    main()
