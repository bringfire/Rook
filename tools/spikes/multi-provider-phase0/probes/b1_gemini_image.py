from __future__ import annotations

import base64

import httpx

from harness.capture import CaptureContext, append_notes, write_manifest, write_redacted
from harness.env import load_keys, require_key
from harness.fixtures import assert_synthetic_prompt, synthetic_prompt, write_red_cube_png


MODEL_ID = "gemini-3.1-flash-image-preview"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"
CATALOG_URL = "https://ai.google.dev/gemini-api/docs/image-generation"


def main() -> None:
    key = require_key("GOOGLE_API_KEY", load_keys().google)
    prompt = synthetic_prompt("red_cube")
    assert_synthetic_prompt(prompt)
    image_path = write_red_cube_png()
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/png", "data": image_base64}},
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": "1K"},
        },
    }
    ctx = CaptureContext("b1", "gemini", MODEL_ID, CATALOG_URL, "existing direct provider baseline")
    with httpx.Client(timeout=300) as client:
        response = client.post(ENDPOINT, headers=headers, json=body)
    write_redacted("submit", {"method": "POST", "url": ENDPOINT, "headers": headers, "json": body}, response, ctx)
    write_redacted(
        "fetch",
        {"method": "none", "url": None, "headers": {}, "source": "Gemini synchronous submit response"},
        response,
        ctx,
    )
    write_manifest(ctx, "complete" if response.is_success else "incomplete", {"status_code": response.status_code})
    append_notes("b1", f"- status_code={response.status_code}")


if __name__ == "__main__":
    main()
