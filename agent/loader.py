from pathlib import Path
from pypdf import PdfReader
import docx


def load_text(path: str | Path, max_chars: int = 24000) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _from_pdf(path)
    elif suffix in {".docx", ".doc"}:
        text = _from_docx(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = "\n".join(line for line in text.splitlines() if line.strip())
    if not text.strip():
        raise ValueError(f"{path.name} produced no extractable text (scanned image?)")
    return text[:max_chars]


def _from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _from_docx(path: Path) -> str:
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)
