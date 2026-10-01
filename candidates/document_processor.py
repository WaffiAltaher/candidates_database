"""
Document processor for extracting text and metadata from PDF files.
"""

import logging
import os
from typing import Dict

import pymupdf


logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Processes PDF documents to extract text and metadata.
    """

    def process(self, file_path: str) -> Dict:
        """Process a PDF file and return a document object with text and metadata."""
        try:
            text = self.extract_text(file_path)
            metadata = self.extract_metadata(file_path)

            return {
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "text": text,
                "metadata": metadata,
                "page_count": metadata.get("page_count", 0),
            }
        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {str(e)}")
            raise

    def extract_text(self, file_path: str) -> str:
        """Extract text content from PDF."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.lower().endswith(".pdf"):
            raise ValueError(f"File is not a PDF: {file_path}")

        try:
            text = ""
            with pymupdf.open(file_path) as doc:
                if doc.is_encrypted and not doc.is_open:
                    raise ValueError(f"Document is encrypted and cannot be opened: {file_path}")
                for page in doc:
                    text += page.get_text()
            return text
        except pymupdf.FileDataError as e:
            raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")

    def extract_metadata(self, file_path: str) -> Dict:
        """Extract metadata from PDF."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.lower().endswith(".pdf"):
            raise ValueError(f"File is not a PDF: {file_path}")

        try:
            with pymupdf.open(file_path) as doc:
                if doc.is_encrypted and not doc.is_open:
                    raise ValueError(f"Document is encrypted and cannot be opened: {file_path}")

                metadata = {
                    "title": doc.metadata.get("title", ""),
                    "author": doc.metadata.get("author", ""),
                    "subject": doc.metadata.get("subject", ""),
                    "keywords": doc.metadata.get("keywords", ""),
                    "creator": doc.metadata.get("creator", ""),
                    "producer": doc.metadata.get("producer", ""),
                    "creation_date": doc.metadata.get("creationDate", ""),
                    "modification_date": doc.metadata.get("modDate", ""),
                    "page_count": len(doc),
                    "file_size": os.path.getsize(file_path),
                }
                return metadata
        except pymupdf.FileDataError as e:
            raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")
