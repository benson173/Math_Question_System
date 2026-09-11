from app.pipeline import PdfIngestionPipeline


def main():
    pdf_path = "inbox/pdf/sample.pdf"
    pipeline = PdfIngestionPipeline()
    pipeline.run_one_pdf(pdf_path)


if __name__ == "__main__":
    main()
