import logging
from pathlib import Path
from typing import List, Optional

from src.exceptions import PDFParsingException, PDFValidationError
from src.schemas.pdf_parser.models import PdfContent

from .docling import DoclingParser

logger = logging.getLogger(__name__)

class PDFParserService:
    def __init__(self, max_pages : int = 20, max_file_size_mb : int = 20, do_ocr : bool = False, do_table_structure: bool = True):
        """Initialize the PDFParserService with configuratble limits. 
         
          
        Args:
            max_pages (int, optional): Maximum number of pages to parse. Defaults to 20.
            max_file_size_mb (int, optional): Maximum file size in megabytes. Defaults to 20.
            do_ocr (bool, optional): Whether to perform OCR on scanned PDFs. Defaults to False.
            do_table_structure (bool, optional): Whether to extract table structure. Defaults to True.
        
        """

        self.docling_parser = DoclingParser(
            max_file_size_mb=max_file_size_mb,
            max_pages=max_pages,
            do_ocr=do_ocr,
            do_table_structure=do_table_structure
        )

        async def parse_pdf(self, file_path: Path) -> PdfContent:
            """
            Parse a PDF file and return its content as a PdfContent object.
            Args:
                file_path (Path): The path to the PDF file to be parsed.
            Returns:
                PdfContent: An object containing the parsed content of the PDF.
            Raises:
                PDFParsingException: If there is an error during parsing.
                PDFValidationError: If the parsed content fails validation.
            """
            if not file_path.exists():
                logger.error(f"File not found: {file_path}") 
                raise PDFParsingException(f"File not found: {file_path}")
            try:
                results = await self.docling_parser.parse_pdf(file_path)
                if not results:
                    logger.warning(f"No content returned for file: {file_path}")
                    raise PDFParsingException(f"No content returned for file: {file_path}")
                else:
                    logger.info(f"Successfully parsed PDF file: {file_path}")
                    return results
            except (PDFParsingException, PDFValidationError):
                raise
            except Exception as e:
                logger.error(f"Unexpected error parsing PDF: {e}")
                raise PDFParsingException(f"Unexpected error parsing PDF: {e}")
                
