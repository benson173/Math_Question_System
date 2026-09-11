from app.document_loader import load_pdf


def main():
    pdf_path = "inbox/pdf/sample.pdf"
    doc = load_pdf(pdf_path)

    print("File:", doc.file_name)
    print("Pages:", doc.page_count)
    print("SHA256:", doc.sha256)


if __name__ == "__main__":
    main()
