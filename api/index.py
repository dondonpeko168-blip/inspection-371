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

    total = conn.execute("SELECT COUNT(*) FROM inspection").fetchone()[0]
    total_items = conn.execute("SELECT COUNT(DISTINCT c16) FROM inspection WHERE c16 != ''").fetchone()[0]
    items = [r[0] for r in conn.execute("SELECT DISTINCT c16 FROM inspection WHERE c16 != '' ORDER BY c16 LIMIT 200")]
    conn.close()

    return jsonify({
        "total": total,
        "total_items": total_items,
        "check_items": items,
        "headers_count": 37
    })


@app.route("/api/items", methods=["GET", "OPTIONS"])
def api_items():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    q = request.args.get("q", "")
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", str(ITEM_PAGE)))

    where = "WHERE c16 != ''"
    params = []
    if q:
        where += " AND c16 LIKE ?"
        params.append(f"%{q}%")

    total = conn.execute(f"SELECT COUNT(DISTINCT c16) FROM inspection {where}", params).fetchone()[0]
    items = [r[0] for r in conn.execute(
        f"SELECT DISTINCT c16 FROM inspection {where} ORDER BY c16 LIMIT ? OFFSET ?",
        params + [limit, offset]
    )]
    conn.close()

    return jsonify({"items": items, "total": total, "offset": offset})


@app.route("/api/query", methods=["GET", "OPTIONS"])
def api_query():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    items_json = request.args.get("items", None)
    page = int(request.args.get("page", "0"))
    cols_param = request.args.get("cols", None)

    if not items_json:
        return jsonify({"rows": [], "total": 0, "page": 0, "pages": 0})

    selected = json.loads(items_json) if isinstance(items_json, str) else items_json
    if not selected:
        return jsonify({"rows": [], "total": 0, "page": 0, "pages": 0})

    if cols_param:
        col_indices = [int(x) for x in cols_param.split(",") if x.strip()]
    else:
        col_indices = list(range(37))

    sel_cols = ", ".join(f"c{i+1}" for i in col_indices)

    placeholders = ",".join("?" * len(selected))
    total = conn.execute(f"SELECT COUNT(*) FROM inspection WHERE c16 IN ({placeholders})", selected).fetchone()[0]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages:
        page = total_pages - 1

    rows = conn.execute(
        f"SELECT {sel_cols} FROM inspection WHERE c16 IN ({placeholders}) ORDER BY rowid LIMIT ? OFFSET ?",
        selected + [PAGE_SIZE, page * PAGE_SIZE]
    ).fetchall()
    conn.close()

    return jsonify({
        "rows": [list(r) for r in rows],
        "total": total,
        "page": page,
        "pages": total_pages
    })


@app.route("/api/export", methods=["POST", "OPTIONS"])
def api_export():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No body"}), 400

    items = data.get("items", [])
    cols = data.get("cols", list(range(37)))
    export_format = data.get("format", "xlsx")

    if not items:
        return jsonify({"error": "No items"}), 400

    sel_cols = ", ".join(f"c{i+1}" for i in cols)
    header_labels = [HEADERS[i] for i in cols]

    placeholders = ",".join("?" * len(items))
    rows = conn.execute(
        f"SELECT {sel_cols} FROM inspection WHERE c16 IN ({placeholders}) ORDER BY rowid",
        items
    ).fetchall()
    conn.close()

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header_labels)
        for r in rows:
            writer.writerow(list(r))
        csv_text = output.getvalue()
        output.close()
        return Response(
            csv_text,
            mimetype="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": "attachment; filename=inspection_export.csv"}
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "檢驗資料"

        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor="1A73E8")
        header_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

        for ci, label in enumerate(header_labels, 1):
            cell = ws.cell(row=1, column=ci, value=label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        for ri, row_data in enumerate(rows, 2):
            for ci, val in enumerate(row_data, 1):
                cell = ws.cell(row=ri, column=ci, value=str(val) if val is not None else "")
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        for col_cells in ws.columns:
            max_len = 0
            for cell in col_cells:
                val = str(cell.value or "")
                char_len = sum(2 if ord(c) > 127 else 1 for c in val)
                if char_len > max_len:
                    max_len = char_len
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 3, 60)

        xlsx_output = io.BytesIO()
        wb.save(xlsx_output)
        xlsx_bytes = xlsx_output.getvalue()
        xlsx_output.close()

        return Response(
            xlsx_bytes,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=inspection_export.xlsx"}
        )


@app.route("/api/upload", methods=["POST", "OPTIONS"])
def api_upload():
    conn, err_resp, err_code = get_conn_or_error()
    if err_resp:
        return err_resp, err_code

    filename = request.args.get("filename", "upload.xlsx")
    raw_data = request.get_data()

    if not raw_data:
        return jsonify({"error": "No data"}), 400

    # gzip decompress if needed
    if filename.endswith(".gz") or raw_data[:2] == b'\x1f\x8b':
        data = gzip.decompress(raw_data)
    else:
        data = raw_data

    tmp_path = os.path.join(tempfile.gettempdir(), "uploaded.xlsx")
    with open(tmp_path, "wb") as f:
        f.write(data)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn.close()
    return jsonify({"success": True, "message": "資料已更新！請重新整理頁面。"})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    """Serve index.html for all non-API routes."""
    return send_from_directory("../", "index.html")


# Vercel entry point
handler = app