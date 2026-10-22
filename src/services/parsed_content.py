"""Serialization shared by scheduled metadata ingestion and on-demand preparation."""

import logging
from datetime import datetime
from typing import Any

from src.schema.pdf_parser.models import ParsedPaper

logger = logging.getLogger(__name__)


def serialize_parsed_content(parsed_paper: ParsedPaper) -> dict[str, Any]:
    """Convert parser output into the existing ``Paper`` parsed-content fields."""
    try:
        pdf_content = parsed_paper.pdf_content
        if pdf_content is None:
            raise ValueError("Parsed paper has no PDF content")
        sections = [{"title": section.title, "content": section.content} for section in pdf_content.sections]
        return {
            "raw_text": pdf_content.raw_text,
            "sections": sections,
            "references": list(pdf_content.references),
            "parser_used": pdf_content.parser_used.value if pdf_content.parser_used else None,
            "parser_metadata": pdf_content.metadata or {},
            "pdf_processed": True,
            "pdf_processing_date": datetime.now(),
        }
    except Exception as exc:
        logger.error("Failed to serialize parsed content: %s", exc)
        return {"pdf_processed": False, "parser_metadata": {"error": str(exc)}}
