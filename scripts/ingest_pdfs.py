from pathlib import Path
import shutil

from app.pipeline import PdfIngestionPipeline


INBOX = Path("inbox/pdf")
PROCESSED = Path("processed/pdf")
FAILED = Path("failed/pdf")


def main():
    pipeline = PdfIngestionPipeline()

    INBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    pdf_files = list(INBOX.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        return

    for pdf_path in pdf_files:
        print("=" * 60)
        print("Processing:", pdf_path.name)

        try:
            pipeline.run_one_pdf(pdf_path)
            shutil.move(str(pdf_path), PROCESSED / pdf_path.name)
            print("Moved to processed.")
        except Exception as e:
            print("Failed:", e)
            shutil.move(str(pdf_path), FAILED / pdf_path.name)
            print("Moved to failed.")


if __name__ == "__main__":
    main()
