from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass
class Settings:
    gemini_api_key: str
    gemini_extractor_model: str
    supabase_url: str
    supabase_secret_key: str
    extraction_version: str
    question_object_version: str


def load_settings() -> Settings:
    load_dotenv()

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_extractor_model=os.getenv("GEMINI_EXTRACTOR_MODEL", ""),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", ""),
        extraction_version=os.getenv("EXTRACTION_VERSION", "QEE_v1"),
        question_object_version=os.getenv("QUESTION_OBJECT_VERSION", "QOS_v1"),
    )
