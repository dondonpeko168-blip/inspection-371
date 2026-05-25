"""Vercel serverless function for 371 inspection viewer - dynamic schema Flask version."""
import json
import os
import sqlite3
import gzip
import io
from flask import Flask, request, jsonify, Response, send_from_directory

app = Flask(__name__, static_folder="../")

DB_PATH = "/tmp/insp_371.db"
PAGE_SIZE = 100
ITEM_PAGE = 200


def parse_xlsx(file_bytes):
    """Parse .xlsx bytes, return (headers: list[str], rows: list[list])"""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active
    headers = [str(cell.value).strip() if cell.value is not None else f"col_{i}"
               for i, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        r = [str(v) if v is not None else "" for v in row]
        # Pad or trim to match header count
        while len(r) < len(headers):
            r.append("")
        rows.append(r[:len(headers)])
    wb.close()
    return headers, rows


def ensure_db():
    """Build SQLite DB from data.xlsx.gz with dynamic schema."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    xlsx_gz = os.path.join(script_dir, "data.xlsx.gz")
    xlsx_path = os.path.join(script_dir, "data.xlsx")

    if os.path.exists(xlsx_gz):
        with gzip.open(xlsx_gz, "rb") as f:
            xlsx_data = f.read()
    elif os.path.exists(xlsx_path):
        with open(xlsx_path, "rb") as f:
            xlsx_data = f.read()
    else:
        return None, "Data file not found", []

    headers, rows = parse_xlsx(xlsx_data)
    if not headers:
        return None, "No columns found in Excel", []

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA cache_size = -16000")

    # Create table with dynamic column names (col_0, col_1, ...)
    col_names = [f"c{i}" for i in range(len(headers))]
    cols_def = ", ".join(f"{name} TEXT" for name in col_names)
    conn.execute(f"CREATE TABLE inspection ({cols_def})")

    placeholders = ",".join("?" * len(headers))
    batch_size = 5000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        conn.executemany(f"INSERT INTO inspection VALUES ({placeholders})", batch)
        conn.commit()

    conn.execute("ANALYZE")
    conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, None, headers


def get_conn_or_error():
    """Reuse cached DB if it exists and is valid, otherwise rebuild."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Check if DB is valid by reading headers from file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    xlsx_gz = os.path.join(script_dir, "data.xlsx.gz")
    xlsx_path = os.path.join(script_dir, "data.xlsx")

    # Read the current xlsx headers
    if os.path.exists(xlsx_gz):
        with gzip.open(xlsx_gz, "rb") as f:
            xlsx_data = f.read()
    elif os.path.exists(xlsx_path):
        with open(xlsx_path, "rb") as f:
            xlsx_data = f.read()
    else:
        return None, jsonify({"error": "Data file not found"}), 500, []

    current_headers, _ = parse_xlsx(xlsx_data)

    # Check if DB already has the right schema
    try:
        cursor = conn.execute("PRAGMA table_info(inspection)")
        db_cols = [row[1] for row in cursor.fetchall()]
        # Force rebuild if column count doesn't match
        if len(db_cols) != len(current_headers):
            conn.close()
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            conn, err, headers = ensure_db()
            if err:
                return None, jsonify({"error": err}), 500, []
            return conn, None, None, headers
        # Check row count
        cursor = conn.execute("SELECT COUNT(*) FROM inspection")
        total = cursor.fetchone()[0]
        if total == 0:
            conn.close()
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            conn, err, headers = ensure_db()
            if err:
                return None, jsonify({"error": err}), 500, []
            return conn, None, None, headers
        return conn, None, None, current_headers
    except sqlite3.OperationalError:
        conn.close()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        conn, err, headers = ensure_db()
        if err:
            return None, jsonify({"error": err}), 500, []
        return conn, None, None, headers


def row_to_dict(row, headers):
    """Convert a sqlite3.Row to a dict using dynamic headers."""
    d = {}
    for i, h in enumerate(headers):
        key = f"c{i}"
        d[h] = row[key] if key in row.keys() else ""
    return d


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/init", methods=["GET", "OPTIONS"])
def api_init():
    conn, err_resp, err_code, headers = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    try:
        cursor = conn.execute("SELECT COUNT(*) as total FROM inspection")
        total = cursor.fetchone()["total"]
    except Exception:
        total = 0

    return jsonify({
        "total": total,
        "headers": headers,
        "page_size": PAGE_SIZE,
        "item_page": ITEM_PAGE
    })


@app.route("/api/items", methods=["GET", "OPTIONS"])
def api_items():
    conn, err_resp, err_code, headers = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    page = int(request.args.get("page", 1))
    offset = (page - 1) * ITEM_PAGE
    limit = ITEM_PAGE

    # Use first header column for item list (or c0 if headers exist)
    first_col = "c0"
    cursor = conn.execute(f"SELECT DISTINCT {first_col} FROM inspection LIMIT ? OFFSET ?", (limit, offset))
    items = [row[first_col] for row in cursor.fetchall()]

    pages = {"current": page, "items": items}
    return jsonify(pages)


@app.route("/api/query", methods=["GET", "OPTIONS"])
def api_query():
    conn, err_resp, err_code, headers = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    offset = (page - 1) * PAGE_SIZE
    limit = PAGE_SIZE

    col_names = [f"c{i}" for i in range(len(headers))]

    conditions = []
    params = []

    if q:
        like = f"%{q}%"
        ors = " OR ".join([f"{c} LIKE ?" for c in col_names])
        conditions.append(f"({ors})")
        params.extend([like] * len(col_names))

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor = conn.execute(f"SELECT COUNT(*) as total FROM inspection {where}", params)
    total = cursor.fetchone()["total"]

    query_sql = f"SELECT * FROM inspection {where} LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
    cursor = conn.execute(query_sql, params)

    results = [row_to_dict(row, headers) for row in cursor.fetchall()]

    return jsonify({
        "total": total,
        "page": page,
        "per_page": limit,
        "data": results
    })


@app.route("/api/data", methods=["GET", "OPTIONS"])
def api_data():
    """Return all data records (browse endpoint)."""
    conn, err_resp, err_code, headers = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    limit = int(request.args.get("limit", 500))

    cursor = conn.execute(f"SELECT * FROM inspection LIMIT ?", (limit,))
    results = [row_to_dict(row, headers) for row in cursor.fetchall()]

    return jsonify(results)


@app.route("/api/export", methods=["POST", "OPTIONS"])
def api_export():
    conn, err_resp, err_code, headers = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    data = request.get_json() or {}
    text = data.get("text", "")
    export_format = data.get("format", "csv")

    col_names = [f"c{i}" for i in range(len(headers))]
    conditions = []
    params = []

    if text:
        like = f"%{text}%"
        ors = " OR ".join([f"{c} LIKE ?" for c in col_names])
        conditions.append(f"({ors})")
        params.extend([like] * len(col_names))

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor = conn.execute(f"SELECT * FROM inspection {where}", params)
    rows = cursor.fetchall()

    if export_format == "csv":
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row[f"c{i}"] for i in range(len(headers))])
        result = output.getvalue()
        return Response(result, mimetype="text/csv")

    elif export_format == "xlsx":
        import openpyxl
        from openpyxl.styles import Font, Alignment
        wb = openpyxl.Workbook()
        ws = wb.active
        # Header row with bold
        header_font = Font(bold=True)
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = header_font
        for row_idx, row in enumerate(rows, 2):
            for col_idx in range(len(headers)):
                ws.cell(row=row_idx, column=col_idx + 1,
                        value=row[f"c{col_idx}"])
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return Response(output.getvalue(),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return jsonify({"error": "Unsupported format"}), 400


# --- Upload: handle multipart/form-data ---
@app.route("/api/upload", methods=["POST", "OPTIONS"])
def api_upload():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    xlsx_gz_path = os.path.join(script_dir, "data.xlsx.gz")
    xlsx_path = os.path.join(script_dir, "data.xlsx")

    # Handle multipart form-data
    if request.content_type and 'multipart/form-data' in request.content_type:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        file_bytes = file.read()
        filename = file.filename
    else:
        raw_data = request.get_data()
        if not raw_data:
            return jsonify({"error": "No data"}), 400
        filename = request.args.get("filename", "upload.xlsx")
        if raw_data[:2] == b'\x1f\x8b':
            file_bytes = gzip.decompress(raw_data)
        else:
            file_bytes = raw_data

    if not filename.endswith('.xlsx') and not filename.endswith('.xlsx.gz'):
        return jsonify({"error": "Only .xlsx files are supported"}), 400

    # If uploaded as gzip, decompress
    if filename.endswith('.gz'):
        data_to_save = file_bytes  # keep as gzip
        xlsx_data = gzip.decompress(file_bytes)
    else:
        data_to_save = file_bytes
        xlsx_data = file_bytes

    # Parse and validate
    headers, rows = parse_xlsx(xlsx_data)
    if not headers:
        return jsonify({"error": "Failed to parse Excel"}), 400

    # Save as gzip
    if filename.endswith('.gz'):
        with open(xlsx_gz_path, "wb") as f:
            f.write(data_to_save)
    else:
        import gzip as gz_module
        with gz_module.open(xlsx_gz_path, "wb") as f:
            f.write(xlsx_data)

    # Also save .xlsx for fallback
    with open(xlsx_path, "wb") as f:
        f.write(xlsx_data)

    # Rebuild DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn, err, _ = ensure_db()
    if conn:
        conn.close()

    return jsonify({
        "success": True,
        "filename": filename,
        "rows": len(rows),
        "columns": headers,
        "sample": [{h: (rows[j][i] if i < len(rows[j]) else "") for i, h in enumerate(headers)}
                    for j in range(min(3, len(rows)))]
    })


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    """Serve index.html for all non-API routes."""
    return send_from_directory("../", "index.html")


# Vercel entry point
handler = app.wsgi_app