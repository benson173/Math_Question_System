from pathlib import Path

from app.document_extractor import DocumentExtractor
from app.extraction_validator import validate_extraction
from app.json_exporter import export_extraction_json
from app.repository import Repository


class PdfIngestionPipeline:
    def __init__(self):
        self.extractor = DocumentExtractor()
        self.repository = Repository()

    def run_one_pdf(self, pdf_path: str | Path) -> None:
        print("Step 1: Extract PDF")
        document = self.extractor.extract(pdf_path)

        print("Step 2: Validate extraction")
        issues = validate_extraction(document)

        print("Step 3: Save result")
        self.repository.save_extracted_document(document, issues)

        print("Done.")

        output_path = f"data/extracted/{document.file_name}.json"
        export_extraction_json(document, issues, output_path)
        print("Exported:", output_path)
