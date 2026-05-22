"""Pandas Excel reader for .xlsx files."""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document


class PandasExcelReader(BaseReader):
    """Pandas-based Excel parser."""

    def __init__(
        self,
        *args: Any,
        pandas_config: Optional[dict] = None,
        concat_rows: bool = True,
        row_joiner: str = "\n",
        **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._pandas_config = pandas_config or {}
        self._concat_rows = concat_rows
        self._row_joiner = row_joiner if row_joiner else "\n"

    def load_data(
        self,
        file: Path,
        include_sheetname: bool = False,
        sheet_name: Optional[Union[str, int, list]] = None,
        extra_info: Optional[Dict] = None,
        include_different_sheet_docs: bool = False,
    ) -> List[Document]:
        """Parse Excel file and return Documents per sheet (or combined)."""

        import pandas as pd

        if sheet_name is not None:
            sheet_name = (
                [sheet_name] if not isinstance(sheet_name, list) else sheet_name
            )

        dfs = pd.read_excel(file, sheet_name=sheet_name, **self._pandas_config)

        if include_different_sheet_docs:
            documents = []
            for sheet_name, df in dfs.items():
                sheet_data = df.values.astype(str).tolist()
                if self._concat_rows:
                    text = self._row_joiner.join(
                        self._row_joiner.join(row) for row in sheet_data
                    )
                else:
                    text = [self._row_joiner.join(row) for row in sheet_data]

                doc_extra_info = {"sheet_name": sheet_name}
                if extra_info:
                    doc_extra_info.update(extra_info)

                documents.append(
                    Document(
                        text=text,
                        extra_info=doc_extra_info,
                    )
                )
            return documents
        else:
            all_sheets_data = []
            for sheet_name, df in dfs.items():
                if include_sheetname:
                    all_sheets_data.append([sheet_name])
                all_sheets_data.extend(df.values.astype(str).tolist())

            if self._concat_rows:
                text = self._row_joiner.join(
                    self._row_joiner.join(row) for row in all_sheets_data
                )
            else:
                text = [self._row_joiner.join(row) for row in all_sheets_data]

            return [
                Document(
                    text=text,
                    extra_info=extra_info or {},
                )
            ]