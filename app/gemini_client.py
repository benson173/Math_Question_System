from pathlib import Path
from google import genai
from google.genai import types

from app.config import load_settings


def read_prompt(prompt_path: str | Path) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


class GeminiClient:
    def __init__(self):
        self.settings = load_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY in .env")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def extract_pdf_json(self, pdf_path: str | Path, prompt_path: str | Path, schema):
        prompt = read_prompt(prompt_path)
        uploaded_file = self.client.files.upload(file=str(pdf_path))

        response = self.client.models.generate_content(
            model=self.settings.gemini_extractor_model,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        if response.parsed is not None:
            return response.parsed

        return schema.model_validate_json(response.text)
