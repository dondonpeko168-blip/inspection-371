# 371型電聯車 電子巡檢保養查詢

台北捷運371型電聯車巡檢保養紀錄查詢工具。

## 技術架構
- **前端**: 純 HTML/CSS/JS
- **後端**: Python Serverless Function (Vercel)
- **資料庫**: SQLite (於 /tmp 即時建立)
- **資料來源**: openpyxl 解析 .xlsx