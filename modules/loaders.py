from llama_index.readers.file import (
    DocxReader,
    PDFReader,
    MarkdownReader,
    PptxReader,
    UnstructuredReader,
    XMLReader,
    CSVReader
)

from llama_index.readers.json import (
    JSONReader
)

from restai.loaders.excel import PandasExcelReader

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
    ".json": (JSONReader, {}),
    ".xls": (PandasExcelReader, {}),
    ".xlsx": (PandasExcelReader, {}),
    ".xml": (XMLReader, {}),
}
