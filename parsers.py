import fitz  # PyMuPDF
import docx
import io

async def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extracts text from PDF or DOCX file bytes."""
    text = ""
    filename = filename.lower()
    
    try:
        if filename.endswith(".pdf"):
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            for page in pdf_document:
                text += page.get_text("text") + "\n"
            pdf_document.close()
        elif filename.endswith(".docx") or filename.endswith(".doc"):
            doc = docx.Document(io.BytesIO(file_bytes))
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            text = file_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        raise ValueError(f"Failed to parse {filename}: {str(e)}")
    
    return text.strip()
