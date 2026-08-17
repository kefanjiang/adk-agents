"""Google Sheets tools: OAuth-backed create / read / modify operations."""

import re

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from .oauth_client import get_gspread_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHEET_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def _extract_sheet_id(sheet_url_or_id: str) -> str:
    """Accept either a full Google Sheets URL or a raw spreadsheet ID."""
    text = (sheet_url_or_id or "").strip()
    if not text:
        raise ValueError("sheet_url_or_id is required")
    match = _SHEET_ID_PATTERN.search(text)
    if match:
        return match.group(1)
    return text


def _open_sheet(sheet_url_or_id: str) -> gspread.Spreadsheet:
    client = get_gspread_client()
    sheet_id = _extract_sheet_id(sheet_url_or_id)
    return client.open_by_key(sheet_id)


def _pick_worksheet(
    sh: gspread.Spreadsheet, worksheet_name: str | None
) -> gspread.Worksheet:
    if worksheet_name:
        return sh.worksheet(worksheet_name)
    return sh.sheet1


def _normalize_rows(rows: list[list]) -> list[list[str]]:
    """Coerce every cell to str so gspread doesn't reject mixed types."""
    out: list[list[str]] = []
    for row in rows or []:
        out.append(["" if v is None else str(v) for v in row])
    return out


def _success(sh: gspread.Spreadsheet, **extra) -> dict:
    payload = {
        "status": "success",
        "url": sh.url,
        "sheet_id": sh.id,
    }
    payload.update(extra)
    return payload


def _handle_common_errors(exc: Exception) -> dict:
    if isinstance(exc, (RuntimeError, ValueError)):
        return {"status": "error", "error_message": str(exc)}
    if isinstance(exc, SpreadsheetNotFound):
        return {
            "status": "error",
            "error_message": (
                "Spreadsheet not found, or the authorized Google account does "
                "not have access to it.  With the drive.file scope, the agent "
                "can only see sheets it created itself."
            ),
        }
    if isinstance(exc, WorksheetNotFound):
        return {
            "status": "error",
            "error_message": f"Worksheet not found: {exc}",
        }
    if isinstance(exc, APIError):
        return {
            "status": "error",
            "error_message": f"Google API error: {exc}",
        }
    return {"status": "error", "error_message": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_google_sheet(title: str, rows: list[list[str]]) -> dict:
    """Create a brand-new Google Spreadsheet owned by the authorized user.

    Args:
        title: Sheet file name (e.g. "Q1 Sales Report").
        rows: 2D list of cell values.  Treat the first row as a header if
              you want one; gspread doesn't care.  Cells are stringified.

    Returns:
        dict with status, url, sheet_id, title, rows_written, error_message.
    """
    try:
        title_value = (title or "Untitled Sheet").strip() or "Untitled Sheet"
        clean_rows = _normalize_rows(rows)

        client = get_gspread_client()
        sh = client.create(title_value)

        if clean_rows:
            sh.sheet1.update(
                range_name="A1",
                values=clean_rows,
                value_input_option="USER_ENTERED",
            )

        return _success(sh, title=sh.title, rows_written=len(clean_rows))
    except Exception as exc:  
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Worksheet (tab) operations
# ---------------------------------------------------------------------------

def add_worksheet_tab(
    sheet_url_or_id: str,
    tab_name: str,
    rows: list[list[str]],
) -> dict:
    """Add a new worksheet tab to an existing spreadsheet and write rows into it."""
    try:
        tab = (tab_name or "").strip()
        if not tab:
            return {"status": "error", "error_message": "tab_name is required"}

        clean_rows = _normalize_rows(rows)
        sh = _open_sheet(sheet_url_or_id)

        ws = sh.add_worksheet(
            title=tab,
            rows=max(100, len(clean_rows) + 10),
            cols=max(26, (len(clean_rows[0]) if clean_rows else 0) + 2),
        )

        if clean_rows:
            ws.update(
                range_name="A1",
                values=clean_rows,
                value_input_option="USER_ENTERED",
            )

        return _success(sh, worksheet=ws.title, rows_written=len(clean_rows))
    except Exception as exc:
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------

def read_sheet_contents(
    sheet_url_or_id: str,
    worksheet_name: str | None = None,
    range_a1: str | None = None,
) -> dict:
    """Read cells from an existing sheet.

    Args:
        sheet_url_or_id: Full Google Sheets URL or raw spreadsheet ID.
        worksheet_name: Tab name.  Defaults to the first tab.
        range_a1: Optional A1 range like "A1:D10".  If None, reads all
                  non-empty cells in the worksheet.

    Returns:
        dict with status, url, sheet_id, worksheet, values (2D list),
        rows_read, cols_read.
    """
    try:
        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        values = ws.get(range_a1) if range_a1 else ws.get_all_values()

        rows_read = len(values)
        cols_read = max((len(r) for r in values), default=0)

        return _success(
            sh,
            worksheet=ws.title,
            range=range_a1 or "all",
            values=values,
            rows_read=rows_read,
            cols_read=cols_read,
        )
    except Exception as exc:  
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Update values
# ---------------------------------------------------------------------------

def update_range(
    sheet_url_or_id: str,
    range_a1: str,
    values: list[list[str]],
    worksheet_name: str | None = None,
) -> dict:
    """Overwrite cell values in an A1 range.

    `range_a1` can target a single cell ("B3"), a row ("A5:D5"), a column
    ("C:C"), or a block ("A1:D10").  `values` must be a 2D list whose
    shape matches the range.
    """
    try:
        if not range_a1:
            return {"status": "error", "error_message": "range_a1 is required"}

        clean_values = _normalize_rows(values)
        if not clean_values:
            return {"status": "error", "error_message": "values cannot be empty"}

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        ws.update(
            range_name=range_a1,
            values=clean_values,
            value_input_option="USER_ENTERED",
        )

        return _success(
            sh,
            worksheet=ws.title,
            range=range_a1,
            cells_updated=sum(len(r) for r in clean_values),
        )
    except Exception as exc:  
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Insert rows / columns
# ---------------------------------------------------------------------------

def insert_rows(
    sheet_url_or_id: str,
    rows: list[list[str]],
    position: int | None = None,
    worksheet_name: str | None = None,
) -> dict:
    """Insert rows at a specific 1-indexed position.

    Args:
        rows: 2D list of cell values to insert.
        position: 1-indexed row number.  Rows are inserted *above* this row,
                  pushing existing rows down.  Pass None to append at the end.
        worksheet_name: Tab name.  Defaults to the first tab.
    """
    try:
        clean_rows = _normalize_rows(rows)
        if not clean_rows:
            return {"status": "error", "error_message": "rows cannot be empty"}

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        if position is None:
            ws.append_rows(clean_rows, value_input_option="USER_ENTERED")
        else:
            if position < 1:
                return {
                    "status": "error",
                    "error_message": "position must be >= 1 (rows are 1-indexed)",
                }
            ws.insert_rows(
                clean_rows, row=position, value_input_option="USER_ENTERED"
            )

        return _success(
            sh,
            worksheet=ws.title,
            position=position if position is not None else "appended",
            rows_inserted=len(clean_rows),
        )
    except Exception as exc:  
        return _handle_common_errors(exc)


def insert_columns(
    sheet_url_or_id: str,
    columns: list[list[str]],
    position: int | None = None,
    worksheet_name: str | None = None,
) -> dict:
    """Insert columns at a specific 1-indexed position.

    Args:
        columns: List of columns; each inner list is the cells of one column
                 top-to-bottom.  E.g. [["Header", "a", "b"], ["H2", "1", "2"]]
                 inserts two columns side by side.
        position: 1-indexed column number.  Columns inserted to the LEFT of
                  this column.  Pass None to append after the last column.
        worksheet_name: Tab name.  Defaults to the first tab.
    """
    try:
        clean_cols = _normalize_rows(columns)
        if not clean_cols:
            return {"status": "error", "error_message": "columns cannot be empty"}

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        if position is None:
            position = ws.col_count + 1
        if position < 1:
            return {
                "status": "error",
                "error_message": "position must be >= 1 (columns are 1-indexed)",
            }

        ws.insert_cols(
            clean_cols, col=position, value_input_option="USER_ENTERED"
        )

        return _success(
            sh,
            worksheet=ws.title,
            position=position,
            columns_inserted=len(clean_cols),
        )
    except Exception as exc:
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Delete rows / columns
# ---------------------------------------------------------------------------

def delete_rows(
    sheet_url_or_id: str,
    start_row: int,
    end_row: int | None = None,
    worksheet_name: str | None = None,
) -> dict:
    """Delete a range of rows (1-indexed, inclusive).

    Args:
        start_row: First row to delete (1-indexed).
        end_row: Last row to delete (inclusive).  Defaults to start_row
                 (delete a single row).
    """
    try:
        if start_row < 1:
            return {
                "status": "error",
                "error_message": "start_row must be >= 1 (rows are 1-indexed)",
            }
        end = end_row if end_row is not None else start_row
        if end < start_row:
            return {
                "status": "error",
                "error_message": "end_row must be >= start_row",
            }

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        ws.delete_rows(start_row, end)

        return _success(
            sh,
            worksheet=ws.title,
            rows_deleted=end - start_row + 1,
            range=f"rows {start_row}-{end}",
        )
    except Exception as exc:  
        return _handle_common_errors(exc)


def delete_columns(
    sheet_url_or_id: str,
    start_col: int,
    end_col: int | None = None,
    worksheet_name: str | None = None,
) -> dict:
    """Delete a range of columns (1-indexed, inclusive).

    Args:
        start_col: First column to delete (1-indexed; A=1, B=2, ...).
        end_col: Last column to delete (inclusive).  Defaults to start_col.
    """
    try:
        if start_col < 1:
            return {
                "status": "error",
                "error_message": "start_col must be >= 1 (columns are 1-indexed)",
            }
        end = end_col if end_col is not None else start_col
        if end < start_col:
            return {
                "status": "error",
                "error_message": "end_col must be >= start_col",
            }

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        ws.delete_columns(start_col, end)

        return _success(
            sh,
            worksheet=ws.title,
            columns_deleted=end - start_col + 1,
            range=f"cols {start_col}-{end}",
        )
    except Exception as exc:  
        return _handle_common_errors(exc)


# ---------------------------------------------------------------------------
# Clear range
# ---------------------------------------------------------------------------

def clear_range(
    sheet_url_or_id: str,
    range_a1: str,
    worksheet_name: str | None = None,
) -> dict:
    """Clear cell values in an A1 range without removing rows or columns.

    Use this when the user says "delete the value in B3" or "empty this
    cell" -- the cell stays in place but its content is wiped.
    """
    try:
        if not range_a1:
            return {"status": "error", "error_message": "range_a1 is required"}

        sh = _open_sheet(sheet_url_or_id)
        ws = _pick_worksheet(sh, worksheet_name)

        ws.batch_clear([range_a1])

        return _success(sh, worksheet=ws.title, range=range_a1, cleared=True)
    except Exception as exc:  
        return _handle_common_errors(exc)
