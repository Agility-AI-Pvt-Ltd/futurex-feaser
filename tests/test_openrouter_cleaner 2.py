import argparse
import os
import sys

from openai import OpenAI


DEFAULT_MODEL = "meta-llama/llama-3-70b-instruct"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _read_input(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide `--text`, `--file`, or pipe text via stdin.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OpenRouter-based noisy text cleaning.")
    parser.add_argument("--text", help="Inline noisy text to clean.")
    parser.add_argument("--file", help="Path to a text file containing noisy text.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model name.")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENROUTER_API_KEY in environment.")

    text = _read_input(args).strip()
    if not text:
        raise SystemExit("Input text is empty.")

    client = OpenAI(
        base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
        api_key=api_key,
    )

    response = client.chat.completions.create(
        model=args.model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Clean the text while preserving meaning. "
                    "Remove leftover UI text, repeated phrases, and broken formatting. "
                    "Do not summarize or remove important details."
                ),
            },
            {
                "role": "user",
                "content": f"Clean this noisy text:\n\n{text}",
            },
        ],
    )

    print(response.choices[0].message.content or "")


if __name__ == "__main__":
    main()
