def normalize_table_data(table_data):
    if table_data is None:
        return []

    if hasattr(table_data, "values"):
        try:
            return table_data.values.tolist()
        except Exception:
            pass

    if isinstance(table_data, dict):
        data = table_data.get("data") or table_data.get("value")
        return data if isinstance(data, list) else []

    if isinstance(table_data, list):
        return table_data

    return []

def safe_get_filename(table_data, row_index: int):
    rows = normalize_table_data(table_data)
    if row_index < 0 or row_index >= len(rows):
        return None
    row = rows[row_index]
    if not isinstance(row, list) or len(row) < 3:
        return None
    fn = str(row[2]).strip()
    return fn if fn else None
