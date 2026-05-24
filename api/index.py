"""Vercel serverless function for 371 inspection viewer - Flask version."""
import json
import os
import sqlite3
import gzip
import io
import tempfile
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from flask import Flask, request, jsonify, Response, send_from_directory

app = Flask(__name__, static_folder="../")

DB_PATH = "/tmp/insp_371.db"
HEADERS = ["系統別","工項名稱","工項編號","檢修週期","派工日期","派工單號","檢修狀態","檢修單位","表單代號","表單名稱","表單編號","表單版次","車號/最小成本單位","進階分類1名稱","進階分類2名稱","檢查項目","檢查項目備註","設備編號","設備子編號","儀器編號","下限值","下限警戒值","上限警戒值","上限值","單位","異常","異常照片","檢查結果","備註","異常原因","處理對策","處理說明","報修單號","檢查時間","檢查人員","複查時間","督導/SCI"]
PAGE_SIZE = 100
ITEM_PAGE = 200


def ensure_db():
    if not os.path.exists(DB_PATH):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        xlsx_gz = os.path.join(script_dir, "data.xlsx.gz")
        xlsx_path = os.path.join(script_dir, "data.xlsx")

        if not os.path.exists(xlsx_path) and os.path.exists(xlsx_gz):
            with gzip.open(xlsx_gz, "rb") as f:
                xlsx_data = f.read()
        elif os.path.exists(xlsx_path):
            with open(xlsx_path, "rb") as f:
                xlsx_data = f.read()
        else:
            return None, "Data file not found"

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_data), read_only=True)
        ws = wb.active

        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA cache_size = -16000")

        cols = ", ".join(f"c{i} TEXT" for i in range(1, 38))
        conn.execute(f"CREATE TABLE inspection ({cols})")
        conn.execute("CREATE INDEX idx_c16 ON inspection(c16)")

        batch = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            r = [str(v) if v is not None else "" for v in row]
            batch.append(r)
            if len(batch) >= 5000:
                conn.executemany(f"INSERT INTO inspection VALUES ({','.join('?' * 37)})", batch)
                conn.commit()
                batch = []
        if batch:
            conn.executemany(f"INSERT INTO inspection VALUES ({','.join('?' * 37)})", batch)
            conn.commit()

        conn.execute("ANALYZE")
        conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, None


def get_conn_or_error():
    conn, err = ensure_db()
    if err:
        return None, jsonify({"error": err}), 500
    return conn, None, None


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/init", methods=["GET", "OPTIONS"])
def api_init():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    try:
        cursor = conn.execute("SELECT COUNT(*) as total FROM inspection")
        total = cursor.fetchone()["total"]
    except Exception:
        total = 0

    headers = HEADERS
    return jsonify({
        "total": total,
        "headers": headers,
        "page_size": PAGE_SIZE,
        "item_page": ITEM_PAGE
    })


@app.route("/api/items", methods=["GET", "OPTIONS"])
def api_items():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    offset = (page - 1) * ITEM_PAGE
    limit = ITEM_PAGE

    cursor = conn.execute("SELECT DISTINCT c16 FROM inspection LIMIT ? OFFSET ?", (limit, offset))
    items = [row["c16"] for row in cursor.fetchall()]

    pages = {"current": page, "items": items}
    return jsonify(pages)


@app.route("/api/query", methods=["GET", "OPTIONS"])
def api_query():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    item = request.args.get("item", "").strip()
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    offset = (page - 1) * PAGE_SIZE
    limit = PAGE_SIZE

    conditions = []
    params = []

    if item:
        conditions.append("c16 = ?")
        params.append(item)

    if q:
        # Simple keyword search across searchable columns
        like = f"%{q}%"
        cols = ["c1", "c2", "c5", "c16", "c17", "c26", "c27", "c30"]
        ors = " OR ".join([f"{c} LIKE ?" for c in cols])
        conditions.append(f"({ors})")
        params.extend([like] * len(cols))

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor = conn.execute(f"SELECT COUNT(*) as total FROM inspection {where}", params)
    total = cursor.fetchone()["total"]

    query_sql = f"SELECT * FROM inspection {where} LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
    cursor = conn.execute(query_sql, params)

    results = []
    for row in cursor.fetchall():
        results.append({k: row[k] for k in row.keys()})

    return jsonify({
        "total": total,
        "page": page,
        "per_page": limit,
        "data": results
    })


@app.route("/api/export", methods=["POST", "OPTIONS"])
def api_export():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    data = request.get_json() or {}
    item = data.get("item", "")
    text = data.get("text", "")
    export_format = data.get("format", "csv")

    conditions = []
    params = []

    if item:
        conditions.append("c16 = ?")
        params.append(item)

    if text:
        like = f"%{text}%"
        cols = ["c1", "c2", "c5", "c16", "c17", "c26", "c27", "c30"]
        ors = " OR ".join([f"{c} LIKE ?" for c in cols])
        conditions.append(f"({ors})")
        params.extend([like] * len(cols))

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor = conn.execute(f"SELECT * FROM inspection {where}", params)
    rows = cursor.fetchall()

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        for row in rows:
            writer.writerow([row[f"c{i}"] for i in range(1, 38)])
        result = output.getvalue()
        return Response(result, mimetype="text/csv")

    elif export_format == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(HEADERS)
        for row in rows:
            ws.append([row[f"c{i}"] for i in range(1, 38)])
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return Response(output.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return jsonify({"error": "Unsupported format"}), 400


# --- 上傳功能：處理 multipart/form-data ---
def parse_excel_bytes(file_bytes):
    """Parse .xlsx file and return list of records."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        records = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            record = {}
            for i, h in enumerate(headers):
                if h is not None:
                    key = str(h).strip()
                    if key:
                        record[key] = row[i] if i < len(row) else None
            if any(v is not None for v in record.values()):
                records.append(record)
        return records, None
    except Exception as e:
        return None, str(e)


from werkzeug.utils import secure_filename

@app.route("/api/upload", methods=["POST", "OPTIONS"])
def api_upload():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    # Handle multipart form-data uploads from the frontend
    if request.content_type and 'multipart/form-data' in request.content_type:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        file_bytes = file.read()
        filename = secure_filename(file.filename)
    else:
        # Fallback for raw POST data
        raw_data = request.get_data()
        if not raw_data:
            return jsonify({"error": "No data"}), 400
        filename = request.args.get("filename", "upload.xlsx")
        if filename.endswith(".gz") or raw_data[:2] == b'\x1f\x8b':
            data = gzip.decompress(raw_data)
        else:
            data = raw_data
        file_bytes = data

    if not filename.endswith('.xlsx'):
        return jsonify({"error": "Only .xlsx files are supported"}), 400

    # Parse the Excel file
    records, error = parse_excel_bytes(file_bytes)
    if error:
        return jsonify({"error": f"Failed to parse Excel: {error}"}), 400

    # Optional: Save uploaded file to temp and rebuild DB (commented out for safety)
    # tmp_path = os.path.join(tempfile.gettempdir(), "uploaded.xlsx")
    # with open(tmp_path, "wb") as f:
    #     f.write(file_bytes)
    # if os.path.exists(DB_PATH):
    #     os.remove(DB_PATH)

    columns = []
    if records:
        columns = list(records[0].keys())

    return jsonify({
        "success": True,
        "filename": filename,
        "rows": len(records),
        "columns": columns,
        "sample": records[:3] if records else []
    })


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    """Serve index.html for all non-API routes."""
    return send_from_directory("../", "index.html")


# Vercel entry point - Flask app
handler = app.wsgi_app
