#!/usr/bin/env python3
"""Vercel serverless function for 371 inspection viewer."""
import json
import os
import sqlite3
import gzip
import io
import tempfile
import openpyxl

DB_PATH = "/tmp/insp_371.db"
HEADERS = ["系統別","工項名稱","工項編號","檢修週期","派工日期","派工單號","檢修狀態","檢修單位","表單代號","表單名稱","表單編號","表單版次","車號/最小成本單位","進階分類1名稱","進階分類2名稱","檢查項目","檢查項目備註","設備編號","設備子編號","儀器編號","下限值","下限警戒值","上限警戒值","上限值","單位","異常","異常照片","檢查結果","備註","異常原因","處理對策","處理說明","報修單號","檢查時間","檢查人員","複查時間","督導/SCI"]
PAGE_SIZE = 100
ITEM_PAGE = 200


def ensure_db():
    if not os.path.exists(DB_PATH):
        # Find the gzipped xlsx
        xlsx_gz = os.path.join(os.path.dirname(__file__), "..", "data.xlsx.gz")
        xlsx_path = os.path.join(os.path.dirname(__file__), "..", "data.xlsx")
        
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
    
    # CORS headers
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}
    
    try:
        conn = ensure_db()
        
        # GET /api/init
        if path == "/api/init":
            total = conn.execute("SELECT COUNT(*) FROM inspection").fetchone()[0]
            total_items = conn.execute("SELECT COUNT(DISTINCT c16) FROM inspection WHERE c16 != ''").fetchone()[0]
            items = [r[0] for r in conn.execute("SELECT DISTINCT c16 FROM inspection WHERE c16 != '' ORDER BY c16 LIMIT 200")]
            conn.close()
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "total": total,
                    "total_items": total_items,
                    "check_items": items,
                    "headers_count": 37
                }, ensure_ascii=False)
            }
        
        # GET /api/items
        elif path == "/api/items":
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
                "headers": headers,
                "body": json.dumps({"items": items, "total": total, "offset": offset}, ensure_ascii=False)
            }
        
        # GET /api/query
        elif path == "/api/query":
            items_json = query.get("items", [None])[0]
            page = int(query.get("page", ["0"])[0])
            
            if not items_json:
                return {"statusCode": 200, "headers": headers, "body": json.dumps({"rows": [], "total": 0, "page": 0, "pages": 0})}
            
            selected = json.loads(items_json) if isinstance(items_json, str) else items_json
            if not selected:
                return {"statusCode": 200, "headers": headers, "body": json.dumps({"rows": [], "total": 0, "page": 0, "pages": 0})}
            
            placeholders = ",".join("?" * len(selected))
            total = conn.execute(f"SELECT COUNT(*) FROM inspection WHERE c16 IN ({placeholders})", selected).fetchone()[0]
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            if page >= total_pages:
                page = total_pages - 1
            
            rows = conn.execute(
                f"SELECT * FROM inspection WHERE c16 IN ({placeholders}) ORDER BY rowid LIMIT ? OFFSET ?",
                selected + [PAGE_SIZE, page * PAGE_SIZE]
            ).fetchall()
            conn.close()
            
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "rows": [list(r) for r in rows],
                    "total": total,
                    "page": page,
                    "pages": total_pages
                }, ensure_ascii=False)
            }
        
        else:
            conn.close()
            return {"statusCode": 404, "headers": headers, "body": json.dumps({"error": "Not found"})}
    
    except Exception as e:
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": str(e)})}