# Laptop Chatbot - Egypt Smart Sales
## مجاني 100% - Groq + Neon PostgreSQL

## تشغيل السيرفر

### 1. ثبّت المكتبات
pip install fastapi uvicorn psycopg2-binary groq python-multipart

### 2. شغّل السيرفر
uvicorn main:app --reload --port 8000

### 3. اختبر
افتح المتصفح على: http://localhost:8000/health

## دمج الـ Widget في الموقع
افتح widget.html وغير هذا السطر:
const API_URL = "http://localhost:8000/chat";
لعنوان السيرفر الحقيقي بعد الـ deployment.

## الداتابيز
الداتا موجودة على Neon (السحابة) - مش محتاج تعمل أي حاجة.
لو عايز تحدث الداتا: python setup_db.py
