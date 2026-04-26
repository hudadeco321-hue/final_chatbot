import os
import json
import psycopg2
from psycopg2 import pool
import psycopg2.extras
from groq import Groq
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# ==========================================
# 0. طبقة الأمان (Security Layer)
# ==========================================
# تحميل المتغيرات البيئية من ملف .env المخفي
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# الفحص الدفاعي: السيرفر لن يعمل إذا كانت المفاتيح مفقودة
if not GROQ_API_KEY or not DATABASE_URL:
    raise RuntimeError("CRITICAL ERROR: Environment variables are missing! Check your .env file or Cloud configuration.")

client = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 1. طبقة إدارة الموارد (Connection Pooling)
# ==========================================
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    try:
        # إنشاء حوض اتصالات يحتفظ بـ 1 إلى 10 اتصالات مفتوحة
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)
        print("System Log: Connection Pool Initialized.")
    except Exception as e:
        print(f"System Log: Pool Initialization Failed: {e}")
    yield
    if db_pool:
        db_pool.closeall()
        print("System Log: Connection Pool Closed.")

app = FastAPI(title="Laptop Chatbot API", lifespan=lifespan)

# إعدادات CORS: حالياً مفتوحة لغرض التجربة، يجب تقييدها برابط الموقع لاحقاً
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. طبقة حماية البيانات (Firewall & Execution)
# ==========================================
def run_query(sql: str, params=None) -> list[dict]:
    # فحص أمني صارم لمنع هجمات SQL Injection
    sql_upper = sql.upper().strip()
    forbidden_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    
    if any(kw in sql_upper for kw in forbidden_keywords):
        raise ValueError("SECURITY ALERT: Unauthorized execution attempt.")
    if not sql_upper.startswith("SELECT"):
        raise ValueError("SECURITY ALERT: Only SELECT operations are allowed.")

    if not db_pool:
        raise Exception("Connection pool is unavailable.")

    # استعارة اتصال جاهز من الحوض
    conn = db_pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        # إعادة الاتصال للحوض فور الانتهاء
        db_pool.putconn(conn)

# ==========================================
# 3. طبقة المنطق والتوجيه (Routing & Logic)
# ==========================================
SQL_SYSTEM = """You are a SQL generator for a laptop database.
CRITICAL RULE: If the user asks about ANYTHING other than laptops (e.g., love songs, weather, politics, general greetings, philosophy), reply ONLY with the exact word: IRRELEVANT

Otherwise, reply ONLY with a valid PostgreSQL query, no explanation, no markdown, no backticks.
Table: laptops
Columns: id, brand, name, price, spec_rating, processor, ram, storage, gpu, screen_size, os, stock

Rules:
- Always SELECT: brand, name, price, spec_rating, processor, ram, storage, gpu, screen_size, os, stock
- Always add: WHERE stock > 0
- Always add: ORDER BY spec_rating DESC, price ASC
- Always add: LIMIT 5
- Budget in Egyptian pounds -> price <= [amount]
- Gaming request -> gpu ILIKE '%nvidia%' OR gpu ILIKE '%radeon rx%'
- Office/work -> gpu ILIKE '%intel%iris%' OR gpu ILIKE '%integrated%'
- Programming/coding -> ram ILIKE '%16%' OR ram ILIKE '%32%'
- Mac request -> brand = 'Apple'
"""

def question_to_sql(question: str, history: list) -> str:
    messages = [{"role": "system", "content": SQL_SYSTEM}]
    for m in history[-4:]:
        messages.append({"role": m["role"], "content": m["text"]})
    messages.append({"role": "user", "content": f"User question: {question}"})
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0,
        max_tokens=300,
    )
    sql = response.choices[0].message.content.strip()
    return sql.replace("```sql", "").replace("```", "").strip()

CHAT_SYSTEM = """انت مساعد مبيعات ودود ومحترف متخصص في اللابتوبات لدى Egypt Smart Sales.
قواعد:
١. رد بنفس لغة الزبون (عربي او انجليزي).
٢. لو كان السؤال خارج سياق اللابتوبات (تمت الإشارة إليه بـ 'السؤال خارج السياق')، اعتذر بأدب شديد، ووضح أنك مبرمج فقط لبيع اللابتوبات، ولا تقدم أي معلومات أخرى.
٣. لو الزبون بيسلم، رحب به واسأله عن ميزانيته.
٤. لو استلمت بيانات لابتوبات، اذكر: اسم الجهاز، السعر بالجنيه، المعالج، الرام، الكارت، وسبب التوصية. قارن بايجاز.
٥. لو مفيش نتائج، قول للزبون ووسع البحث.
٦. كن مختصرا - مش اكتر من 5 اسطر.
"""

def build_reply(question: str, laptops: list[dict], history: list, is_irrelevant: bool = False) -> str:
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["text"]})
    
    if is_irrelevant:
        content = f"سؤال الزبون: {question}\n\nتنبيه للنظام: السؤال خارج السياق تماماً. اعتذر للعميل فوراً."
    elif laptops:
        data_text = json.dumps(laptops, ensure_ascii=False, indent=2)
        content = f"سؤال الزبون: {question}\n\nنتائج قاعدة البيانات:\n{data_text}"
    else:
        content = f"سؤال الزبون: {question}\n\nنتائج قاعدة البيانات: لا توجد اجهزة مطابقة."
        
    messages.append({"role": "user", "content": content})
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

# ==========================================
# 4. طبقة واجهة برمجة التطبيقات (API Endpoints)
# ==========================================
class Message(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []

class ChatResponse(BaseModel):
    reply:    str
    sql_used: str
    results:  int

@app.get("/")
def serve_widget():
    return FileResponse("widget.html")

@app.get("/health")
def health():
    try:
        rows = run_query("SELECT COUNT(*) as total FROM laptops;")
        return {"status": "ok", "db": "Neon connected via Pool", **rows[0]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    history = [{"role": m.role, "text": m.text} for m in req.history]
    
    # 1. تحديد النية واستخراج الاستعلام
    try:
        sql = question_to_sql(req.message, history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq SQL Error: {e}")

    laptops = []
    is_irrelevant = False
    sql_used = ""

    # 2. التوجيه (Routing)
    if sql.upper() == "IRRELEVANT":
        is_irrelevant = True
        sql_used = "NONE - Out of Domain"
    else:
        try:
            laptops = run_query(sql)
            sql_used = sql
        except ValueError as ve:
            print(f"تم حظر الاستعلام: {ve}")
            is_irrelevant = True
            sql_used = "BLOCKED - Security Violation"
        except Exception as e:
            print(f"خطأ في قاعدة البيانات: {e}")
            fallback = "SELECT brand, name, price, spec_rating, processor, ram, storage, gpu, screen_size, os, stock FROM laptops WHERE stock > 0 ORDER BY spec_rating DESC LIMIT 5"
            laptops = run_query(fallback)
            sql_used = fallback

    # 3. صياغة الرد النهائي
    try:
        reply = build_reply(req.message, laptops, history, is_irrelevant)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq Reply Error: {e}")
        
    return ChatResponse(reply=reply, sql_used=sql_used, results=len(laptops))