"""
Extrator de texto — converte arquivos brutos em texto plano.

MVP: suporta .md e .txt (leitura direta).
Futuro: adicionar PDF (pdf-parse/pymupdf), DOCX (python-docx), imagens (OCR via Tesseract).
"""

import os
from typing import Tuple

# Mapeamento de extensão → tipo de extração
SUPPORTED_EXTENSIONS = {
    ".md": "text",
    ".txt": "text",
    ".csv": "text",
    # Futuro:
    # ".pdf": "pdf",
    # ".docx": "docx",
    # ".png": "ocr",
    # ".jpg": "ocr",
}


def extract_text(file_path: str) -> Tuple[str, str]:
    """Extrai texto bruto de um arquivo.

    Args:
        file_path: Caminho do arquivo na Bronze.

    Returns:
        Tupla (texto_extraído, mime_type).

    Raises:
        ValueError: Se o tipo de arquivo não é suportado.
        FileNotFoundError: Se o arquivo não existe.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Tipo de arquivo não suportado: {ext}. "
            f"Suportados: {list(SUPPORTED_EXTENSIONS.keys())}"
        )

    extraction_type = SUPPORTED_EXTENSIONS[ext]

    if extraction_type == "text":
        return _extract_text_file(file_path), f"text/{ext.lstrip('.')}"

    # Futuro: outros tipos
    raise ValueError(f"Extração do tipo '{extraction_type}' não implementada")


def _extract_text_file(file_path: str) -> str:
    """Lê arquivo de texto plano com detecção de encoding."""
    encodings = ["utf-8", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            return content.strip()
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Não foi possível decodificar {file_path} com nenhum encoding suportado")


def get_source_type_from_path(file_path: str) -> str:
    """Infere o source_type baseado no diretório do arquivo.

    Mapeamento:
        data/bronze/calls/    → transcricao_reuniao
        data/bronze/docs/     → documento_produto
        data/bronze/chats/    → chat

    Para o MVP, os diretórios são fixos. Futuro: configurável.
    """
    # Normalizar path
    normalized = file_path.replace("\\", "/")

    if "/calls/" in normalized:
        return "transcricao_reuniao"
    elif "/chats/" in normalized:
        return "chat"
    elif "/docs/" in normalized:
        # Heurística: se contém "requisitos-cliente" ou "cliente" no nome, é doc do cliente
        basename = os.path.basename(normalized).lower()
        if "cliente" in basename or "enterprise" in basename or "contrato" in basename:
            return "documento_cliente"
        return "documento_produto"

    # Fallback
    return "documento_produto"
