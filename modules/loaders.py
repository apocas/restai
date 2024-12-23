from llama_index.readers.file import (
    DocxReader,
    PDFReader,
    MarkdownReader,
    PptxReader,
    UnstructuredReader,
    XMLReader,
    CSVReader,
)

from app.loaders.excel import PandasExcelReader

LOADERS = {
    ".csv": (CSVReader, {}),
    ".docx": (DocxReader, {}),
    ".eml": (UnstructuredReader, {}),
    ".epub": (UnstructuredReader, {}),
    ".html": (UnstructuredReader, {}),
    ".md": (MarkdownReader, {}),
    ".odt": (PandasExcelReader, {}),
    ".pdf": (PDFReader, {}),
    ".pptx": (PptxReader, {}),
    ".txt": (UnstructuredReader, {}),
    ".json": (UnstructuredReader, {}),
    ".xls": (PandasExcelReader, {}),
    ".xlsx": (PandasExcelReader, {}),
    ".xml": (XMLReader, {}),
}
