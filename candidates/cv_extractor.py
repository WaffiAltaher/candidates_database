"""
CV extraction pipeline: PDF -> text -> structured data -> database.
"""

import logging
import os

from .database import Database
from .document_processor import DocumentProcessor
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a CV/resume parser. Extract structured information from the following CV text.
Return a JSON object with exactly these fields:

{
  "name": "Full name of the candidate",
  "date_of_birth": "YYYY-MM-DD format or null if not found",
  "university": "Most recent/highest university or null",
  "degree_field": "Field of study or null",
  "job_title": "Current or most recent job title or null",
  "years_experience": null,
  "technologies": ["list", "of", "technologies", "tools", "languages"],
  "experiences": [
    {
      "company": "Company name",
      "role": "Job title/role",
      "start_date": "YYYY-MM or YYYY format",
      "end_date": "YYYY-MM or YYYY format, or 'present'",
      "description": "Brief description of responsibilities"
    }
  ]
}

Rules:
- Return ONLY valid JSON, no markdown, no explanation
- Use null for fields you cannot determine from the text
- Normalize technology names (e.g., "JS" -> "JavaScript", "py" -> "Python")
- For years_experience, calculate from work history if not explicitly stated. Use null if you cannot determine it.
- List ALL technologies mentioned including programming languages, frameworks, databases, tools"""


class CVExtractor:
    def __init__(self, llm_client: LLMClient, database: Database, use_pdf_upload: bool = True):
        self.llm_client = llm_client
        self.database = database
        self.use_pdf_upload = use_pdf_upload
        if not use_pdf_upload:
            self.doc_processor = DocumentProcessor()

    def ingest_file(self, file_path: str) -> dict:
        """Process a single CV PDF and store extracted data.

        Returns the extracted candidate data dict.
        """
        logger.info(f"Ingesting CV: {file_path}")

        if self.use_pdf_upload:
            data = self.llm_client.extract_json_from_pdf(EXTRACTION_SYSTEM_PROMPT, file_path)
        else:
            doc = self.doc_processor.process(file_path)
            data = self._extract_structured_data(doc["text"])
        _, was_replaced = self._store_candidate(data)
        data["_was_replaced"] = was_replaced

        if was_replaced:
            logger.info(f"Replaced existing CV for: {data['name']}")
        else:
            logger.info(f"Successfully ingested CV for: {data['name']}")
        return data

    def ingest_folder(self, folder_path: str) -> list[dict]:
        """Process all PDFs in a folder."""
        if not os.path.isdir(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        pdf_files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        ]

        if not pdf_files:
            logger.warning(f"No PDF files found in {folder_path}")
            return []

        results = []
        errors = []

        for pdf_path in pdf_files:
            try:
                data = self.ingest_file(pdf_path)
                results.append(data)
            except Exception as e:
                logger.error(f"Failed to ingest {pdf_path}: {e}")
                errors.append((pdf_path, str(e)))

        if errors:
            logger.warning(f"Failed to ingest {len(errors)} of {len(pdf_files)} files:")
            for path, error in errors:
                logger.warning(f"  {path}: {error}")

        return results

    def _extract_structured_data(self, cv_text: str) -> dict:
        """Send CV text to LLM for structured extraction."""
        return self.llm_client.extract_json(EXTRACTION_SYSTEM_PROMPT, cv_text)

    def _store_candidate(self, data: dict) -> tuple[int, bool]:
        """Upsert candidate and related records into database. Returns (candidate_id, was_replaced)."""
        candidate_id, was_replaced = self.database.upsert_candidate(data)

        technologies = data.get("technologies", [])
        if technologies:
            self.database.add_technologies(candidate_id, technologies)

        experiences = data.get("experiences", [])
        if experiences:
            self.database.add_experiences(candidate_id, experiences)

        return candidate_id, was_replaced
