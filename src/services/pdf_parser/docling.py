import logging 
from pathlib import Path
from typing import List, Optional
import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from fastapi import logger
from src.exceptions import PDFParsingException, PDFValidationError
from src.schemas.pdf_parser.models import PdfContent, ParserType, PaperSection, PaperFigure, PaperTable

logger = logging.getLogger(__name__)

class DoclingParser:
    """Docling PDF parser implementation."""

    def __init__(self,max_pages: int = 20, max_file_size_mb : int = 20, do_ocr: bool = False, do_table_structure: bool = True):
        """
        Initialize the Docling parser with configuration options.
        Args: 
            max_pages (int): Maximum number of pages to parse from the PDF.
            max_file_size_mb (int): Maximum allowed file size in megabytes.
            do_ocr (bool): Whether to perform OCR on scanned PDFs.
            do_table_structure (bool): Whether to extract table structure information.
        """
        # configure the pipeline
        pipeline_options = PdfPipelineOptions(
            do_tables_structure = do_table_structure,
            do_ocr = do_ocr
        )

        self._converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
        )
        self.max_pages = max_pages
        self.max_file_size_mb = max_file_size_mb * 1024 * 1024 # convert to bytes
        self._warmed_up = False

    def _warm_up_models(self):
        """Pre-warm the Docling models to reduce latency for the first PDF parsing using dummy documents."""
        if not self._warmed_up:
            self._warmed_up = True
            logger.info("Warming up Docling models with dummy documents...")
    def _validate_pdf(self, pdf_path: Path) -> bool:
        """Validate the PDF file for size and page count constraints before parsing.
        Args: 
            pdf_path (Path): The file path to the PDF document to validate.
        
        """
        try: 
            # check if the file exist and is a valid PDF
            if pdf_path.stat().st_size == 0:
                logger.error(f"PDF file {pdf_path} is empty.")
                raise PDFValidationError(f"PDF file {pdf_path} is empty.")
            # check the size of the pdf file 
            file_size = pdf_path.stat().st_size 
            if file_size > self.max_file_size_mb:
                raise PDFValidationError(f"PDF file size {file_size} exceeds the maximum allowed size of {self.max_file_size_mb} bytes.")

            # check if the file starts with a pdf header 
            with open(pdf_path, "rb") as f:
                header = f.read(8)
                if not header.startswith(b"%PDF-"):
                    logger.error(f"File {pdf_path} does not appear to be a valid PDF.")
                    raise PDFValidationError(f"File {pdf_path} does not appear to be a valid PDF.")

            # checking the page count limit 
            pdf_doc_len = len(pdfium.PdfDocument(pdf_path)) 
            if pdf_doc_len > self.max_pages:
                logger.error(f"PDF file {pdf_path} has {pdf_doc_len} pages, which exceeds the maximum allowed {self.max_pages} pages.")
                raise PDFValidationError(f"PDF file {pdf_path} has {pdf_doc_len} pages, which exceeds the maximum allowed {self.max_pages} pages.")
            return True
        except PDFValidationError:
            raise
        except Exception as e:
            logger.error(f"PDF validation failed for {pdf_path}: {str(e)}")
            raise PDFValidationError(f"PDF validation failed for {pdf_path}: {str(e)}") from e
            
    async def parse_pdf(self, pdf_path: Path) -> Optional[PdfContent]:
        """Parse the PDF document and extract structured content.
        Args:
            pdf_path (Path): The file path to the PDF document to parse.
            
        Returns:
            Optional[PdfContent]: The extracted content from the PDF, or None if parsing fails.
        """

        try: 
            # validate the pdf file before parsing
            self._validate_pdf(pdf_path)
            # warm up the models on the first run to reduce latency
            self._warm_up_models()
            # convert the document using docling into a structured format
            result = self._converter.convert(str(pdf_path),max_num_pages=self.max_pages, max_file_size=self.max_file_size_mb)

            # Extract structured content from the conversion result
            doc = result.document

            # extract sections from the document struture 
            sections = []
            current_section = {"title": "content", "content": ""} 
            for element in doc.texts:
                if hasattr(element, "label") and element.label in ["title" , "section_header"]:
                    # start of a new section
                    if current_section["content"].strip(): # if there is content in the current section, save it before starting a new one
                        sections.append(PaperSection(title=current_section["title"], content=current_section["content"].strip()))
                    # start a new section with the current element as the title
                    current_section = {"title": element.text.strip(), "content": ""}   
                else:
                    if hasattr(element, "text") and element.text:
                        current_section["content"] += element.text + "\n"

            # add the last section if it has content
            if current_section["content"].strip():
                sections.append(PaperSection(title=current_section["title"], content=current_section["content"].strip()))
            
            # Focus on what arixiv api doesnt provide 
            return PdfContent(
                sections = sections,
                figures = [],
                tables = [], # basic metdata not useful
                raw_text = doc.export_to_text(),
                references = [],
                parser_used = ParserType.DOCLING,
                metadata = {
                    "source": "docling",
                    "note": "Content extracted from pdf, metadata comes from arxiv api."
                }
            )
        except PDFValidationError as e:
            error_msg = str(e).lower()
            if "too large" in error_msg or "too many pages" in error_msg:
                logger.error(f"PDF parsing failed for {pdf_path} due to size/page limit: {str(e)}")
                return None
            else:
                raise
        except Exception as e:
            logger.error(f"PDF parsing failed for {pdf_path}: {str(e)}")
            logger.error(f"pdf_path: {pdf_path}, file_size: {pdf_path.stat().st_size}, max_file_size: {self.max_file_size_mb}, max_pages: {self.max_pages}")
            # Add specific handling for common issues
            error_msg = str(e).lower()

            # Note: Page and size limit checks are now handled in _validate_pdf method

            if "not valid" in error_msg:
                logger.error("PDF appears to be corrupted or not a valid PDF file")
                raise PDFParsingException(f"PDF appears to be corrupted or invalid: {pdf_path}")
            elif "timeout" in error_msg:
                logger.error("PDF processing timed out - file may be too complex")
                raise PDFParsingException(f"PDF processing timed out: {pdf_path}")
            elif "memory" in error_msg or "ram" in error_msg:
                logger.error("Out of memory - PDF may be too large or complex")
                raise PDFParsingException(f"Out of memory processing PDF: {pdf_path}")
            elif "max_num_pages" in error_msg or "page" in error_msg:
                logger.error(f"PDF processing issue likely related to page limits (current limit: {self.max_pages} pages)")
                raise PDFParsingException(
                    f"PDF processing failed, possibly due to page limit ({self.max_pages} pages). Error: {e}"
                )
            else:
                raise PDFParsingException(f"Failed to parse PDF with Docling: {e}")
        
