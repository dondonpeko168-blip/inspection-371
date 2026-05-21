#!/usr/bin/env python3
"""Vercel serverless function for 371 inspection viewer."""
import json
import os
import sqlite3
import gzip
import io
import tempfile
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

DB_PATH = "/tmp/insp_371.db"
HEADERS = ["系統別","工項名稱","工項編號","檢修週期","派工日期","派工單號","檢修狀態","檢修單位","表單代號","表單名稱","表單編號","表單版次","車號/最小成本單位","進階分類1名稱","進階分類2名稱","檢查項目","檢查項目備註","設備編號","設備子編號","儀器編號","下限值","下限警戒值","上限警戒值","上限值","單位","異常","異常照片","檢查結果","備註","異常原因","處理對策","處理說明","報修單號","檢查時間","檢查人員","複查時間","督導/SCI"]
PAGE_SIZE = 100
ITEM_PAGE = 200


def ensure_db():
    if not os.path.exists(DB_PATH):
        # Find the gzipped xlsx
        script_dir = os.path.dirname(os.path.abspath(__file__))
        xlsx_gz = os.path.join(script_dir, "..", "data.xlsx.gz")
        xlsx_path = os.path.join(script_dir, "..", "data.xlsx")

        # Decompress
        if not os.path.exists(xlsx_path) and os.path.exists(xlsx_gz):
            with gzip.open(xlsx_gz, "rb") as f:
                xlsx_data = f.read()
        elif os.path.exists(xlsx_path):
            with open(xlsx_path, "rb") as f:
                xlsx_data = f.read()
        else:
            raise Exception("Data file not found")

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
    return conn


def handler(request):
    path = request.get("path", "/")
    query = request.get("query", {})
    method = request.get("method", "GET")
    body = request.get("body", None)

    # CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": ""}

    try:
        conn = ensure_db()

        # GET /api/init
        if path == "/api/init" and method == "GET":
            total = conn.execute("SELECT COUNT(*) FROM inspection").fetchone()[0]
            total_items = conn.execute("SELECT COUNT(DISTINCT c16) FROM inspection WHERE c16 != ''").fetchone()[0]
            items = [r[0] for r in conn.execute("SELECT DISTINCT c16 FROM inspection WHERE c16 != '' ORDER BY c16 LIMIT 200")]
            conn.close()
            return {
                "statusCode": 200,
                "headers": {**cors_headers, "Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps({
                    "total": total,
                    "total_items": total_items,
                    "check_items": items,
                    "headers_count": 37
                }, ensure_ascii=False)
            }

        # GET /api/items
        elif path == "/api/items" and method == "GET":
            q = query.get("q", [""])[0]
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", [str(ITEM_PAGE)])[0])

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
            return {
                "statusCode": 200,
                "headers": {**cors_headers, "Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps({"items": items, "total": total, "offset": offset}, ensure_ascii=False)
            }

        # GET /api/query
        elif path == "/api/query" and method == "GET":
            items_json = query.get("items", [None])[0]
            page = int(query.get("page", ["0"])[0])
            cols_param = query.get("cols", [None])[0]

            if not items_json:
                return {"statusCode": 200, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"rows": [], "total": 0, "page": 0, "pages": 0})}

            selected = json.loads(items_json) if isinstance(items_json, str) else items_json
            if not selected:
                return {"statusCode": 200, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"rows": [], "total": 0, "page": 0, "pages": 0})}

            # Determine which columns to return
            if cols_param:
                col_indices = [int(x) for x in cols_param.split(",") if x.strip()]
            else:
                col_indices = list(range(37))

            # Build SELECT clause
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

            return {
                "statusCode": 200,
                "headers": {**cors_headers, "Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps({
                    "rows": [list(r) for r in rows],
                    "total": total,
                    "page": page,
                    "pages": total_pages
                }, ensure_ascii=False)
            }

        # POST /api/export
        elif path == "/api/export" and method == "POST":
            if not body:
                return {"statusCode": 400, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"error": "No body"})}

            data = json.loads(body) if isinstance(body, str) else body
            items = data.get("items", [])
            cols = data.get("cols", list(range(37)))
            export_format = data.get("format", "xlsx")

            if not items:
                return {"statusCode": 400, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"error": "No items"})}

            # Build SELECT
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
                return {
                    "statusCode": 200,
                    "headers": {
                        **cors_headers,
                        "Content-Type": "text/csv; charset=utf-8-sig",
                        "Content-Disposition": "attachment; filename=inspection_export.csv"
                    },
                    "body": csv_text
                }

            else:
                # xlsx
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "檢驗資料"

                # Header styling
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

                # Auto-width
                for col_cells in ws.columns:
                    max_len = 0
                    for cell in col_cells:
                        val = str(cell.value or "")
                        # Estimate width (CJK chars ~2x)
                        char_len = sum(2 if ord(c) > 127 else 1 for c in val)
                        if char_len > max_len:
                            max_len = char_len
                    ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 3, 60)

                xlsx_output = io.BytesIO()
                wb.save(xlsx_output)
                xlsx_bytes = xlsx_output.getvalue()
                xlsx_output.close()

                return {
                    "statusCode": 200,
                    "headers": {
                        **cors_headers,
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "Content-Disposition": "attachment; filename=inspection_export.xlsx"
                    },
                    "body": base64_bytes(xlsx_bytes),
                    "encoding": "base64"
                }

        # POST /api/upload
        elif path == "/api/upload" and method == "POST":
            filename = query.get("filename", ["upload.xlsx"])[0]
            raw_body = request.get("rawBody", None)
            if raw_body:
                # gzip decompress if needed
                if filename.endswith(".gz") or raw_body[:2] == b'\x1f\x8b':
                    data = gzip.decompress(raw_body)
                else:
                    data = raw_body
            else:
                data = body

            # Save to tmp and rebuild db
            tmp_path = os.path.join(tempfile.gettempdir(), "uploaded.xlsx")
            with open(tmp_path, "wb") as f:
                if isinstance(data, str):
                    f.write(data.encode("utf-8"))
                else:
                    f.write(data)

            # Remove old DB so it rebuilds on next request
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)

            conn.close()
            return {
                "statusCode": 200,
                "headers": {**cors_headers, "Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps({"success": True, "message": "資料已更新！請重新整理頁面。"}, ensure_ascii=False)
            }

        else:
            conn.close()
            return {"statusCode": 404, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"error": "Not found"})}

    except Exception as e:
        return {"statusCode": 500, "headers": {**cors_headers, "Content-Type": "application/json"}, "body": json.dumps({"error": str(e)}, ensure_ascii=False)}


def base64_bytes(data):
    """Encode bytes to base64 string for Vercel Python runtime response."""
    import base64
    return base64.b64encode(data).decode("ascii")