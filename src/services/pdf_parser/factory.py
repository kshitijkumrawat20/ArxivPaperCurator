""" Factory for creating PDF parser services.
This module provides a factory function to create instances of PDFParserService with configurable options.
"""

from functools import lru_cache
from pathlib import Path
from .parser import PDFParserService
from src.config import get_settings


@lru_cache(maxsize=1) # max size of 1 to ensure only one instance is created and cached
def make_pdf_parser_service() -> PDFParserService:
    """
    Factory function to create and cache a PDFParserService instance.
    Returns:
        PDFParserService: An instance of the PDFParserService class.
    """
    settings = get_settings()
    return PDFParserService(
        max_pages=settings.pdf_parser.max_pages,
        max_file_size_mb=settings.pdf_parser.max_file_size_mb,
        do_ocr=settings.pdf_parser.do_ocr,
        do_tables_structure=settings.pdf_parser.do_table_structure
    )


