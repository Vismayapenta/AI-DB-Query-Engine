from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader
import pytesseract
from PIL import Image
from sentence_transformers import SentenceTransformer
import json
import pymysql
from pymysql.err import OperationalError
import spacy
import io
import cv2
import faiss
import re
import numpy as np
import requests
import platform
import logging
import os
from dotenv import load_dotenv

load_dotenv()


# ---------- LOGGING ----------
# FIX: previously errors were swallowed with `except: pass`. Now every
# failure is logged so you can actually see what went wrong in the terminal.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aidb")

# ---------- LOAD MODELS ----------
model = SentenceTransformer("all-MiniLM-L6-v2")
nlp = spacy.load("en_core_web_sm")

app = FastAPI(title="AI-Driven DB-SQL Engine", version="2.1")

# ---------- CORS (for React frontend) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OCR PATH ----------
# FIX: hardcoded Windows-only path crashed on Mac/Linux. Now it only sets the
# path on Windows, and only if the file actually exists there.
if platform.system() == "Windows":
    _tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    import os
    if os.path.exists(_tess_path):
        pytesseract.pytesseract.tesseract_cmd = _tess_path
    else:
        logger.warning("Tesseract not found at default path. OCR may fail unless tesseract is on PATH.")

# ---------- FAISS IN-MEMORY CACHE ----------
faiss_index = None
faiss_documents = []


# ---------- MYSQL CONNECTION (with auto-reconnect) ----------
def get_connection():
    return pymysql.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
)


def get_cursor():
    conn = get_connection()
    return conn, conn.cursor()


# ---------- ENSURE BASE TABLE EXISTS ----------
def ensure_base_table():
    conn, cursor = get_cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            filename TEXT,
            content TEXT,
            embedding LONGTEXT
        )
    """)
    conn.commit()
    conn.close()


ensure_base_table()


# ---------- TEXT CLEANING ----------
def clean_text(text):
    doc = nlp(text)
    cleaned = " ".join(
        token.text
        for token in doc
        if not token.is_punct
    )
    return cleaned


def clean_ocr_noise(text):
    text = re.sub(r'[^A-Za-z0-9.,()\-\n ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


# ---------- CHUNKING ----------
def chunk_text(text, chunk_size=300):
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]


# ---------- IMAGE PREPROCESS ----------
def preprocess_image(image):
    img = np.array(image)
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return thresh


# ---------- FAISS INDEX BUILDER ----------
def rebuild_faiss_index():
    global faiss_index, faiss_documents
    conn, cursor = get_cursor()
    cursor.execute("SELECT content, embedding FROM documents")
    rows = cursor.fetchall()
    conn.close()

    documents = []
    embeddings = []

    for row in rows:
        if row["embedding"]:
            documents.append(row["content"])
            embeddings.append(json.loads(row["embedding"]))

    if not embeddings:
        faiss_index = None
        faiss_documents = []
        return

    emb_array = np.array(embeddings).astype("float32")
    index = faiss.IndexFlatL2(emb_array.shape[1])
    index.add(emb_array)

    faiss_index = index
    faiss_documents = documents


# ---------- OLLAMA CALL ----------
def ollama(prompt, model_name="llama3"):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=90
        )
        response.raise_for_status()
        return response.json()["response"].strip()
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return f"Ollama Error: {str(e)}"


# ---------- SAFE JSON EXTRACTION ----------
# FIX: centralizes JSON parsing so both schema generation and value
# extraction handle malformed / truncated AI output the same, safer way.
def safe_json_extract(raw, kind="object"):
    """kind = 'object' looks for {...}, 'array' looks for [...]"""
    if not raw or raw.startswith("Ollama Error"):
        return None

    pattern = r'\{.*\}' if kind == "object" else r'\[.*\]'
    match = re.search(pattern, raw, re.DOTALL)
    if not match:
        logger.warning(f"No {kind} found in AI response: {raw[:200]}")
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed ({e}) on: {match.group()[:200]}")
        return None


# ============================================================
# MODULE 1: AI SCHEMA GENERATOR
# ============================================================

ALLOWED_TYPES = {"TEXT", "INTEGER", "DECIMAL", "DATE"}


def generate_schema_from_text(text):
    prompt = f"""
Analyze this document text and identify all data fields present.
Also suggest a short table_name describing WHAT TYPE of entity this document
represents (e.g. "invoices", "students", "employees", "orders") — NOT based
on the filename, based on the actual content/entity type.

Return ONLY a JSON object. No explanation, no markdown, no backticks.

Format:
{{
  "table_name": "invoices",
  "fields": [
    {{"field_name": "invoice_number", "data_type": "TEXT"}},
    {{"field_name": "amount", "data_type": "DECIMAL"}},
    {{"field_name": "date", "data_type": "DATE"}}
  ]
}}

Rules:
- table_name must be lowercase, plural, with underscores, no spaces (e.g. "invoices", "student_records")
- Use only these data types: TEXT, INTEGER, DECIMAL, DATE
- field_name must be lowercase with underscores, no spaces
- Return at least 2 fields, max 10 fields
- Only include fields that are clearly visible in the document

Document text:
{text[:1500]}

Return ONLY the JSON object:
"""
    raw = ollama(prompt)
    parsed = safe_json_extract(raw, kind="object")
    if not parsed or "fields" not in parsed:
        return [], None

    raw_fields = parsed.get("fields", [])
    suggested_name = str(parsed.get("table_name", "")).strip().lower()
    suggested_name = re.sub(r'[^a-z0-9_]', '_', suggested_name)[:50] or None

    # FIX: validate each field so a bad AI response can't create a broken
    # table (e.g. invalid data_type, empty field_name, duplicate names).
    cleaned_fields = []
    seen_names = set()
    for f in raw_fields:
        if not isinstance(f, dict):
            continue
        name = str(f.get("field_name", "")).strip().lower()
        name = re.sub(r'[^a-z0-9_]', '_', name)
        dtype = str(f.get("data_type", "")).strip().upper()

        if not name or name in seen_names or name == "id" or name == "source_file":
            continue
        if dtype not in ALLOWED_TYPES:
            dtype = "TEXT"  # fall back instead of dropping the field

        seen_names.add(name)
        cleaned_fields.append({"field_name": name, "data_type": dtype})

    return cleaned_fields[:10], suggested_name


def create_table_from_schema(table_name, fields):
    conn, cursor = get_cursor()
    safe_name = re.sub(r'[^a-z0-9_]', '_', table_name.lower())[:50]

    field_defs = ", ".join(
        [f"`{f['field_name']}` {f['data_type']}" for f in fields]
    )

    sql = f"""
    CREATE TABLE IF NOT EXISTS `{safe_name}` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source_file TEXT,
        {field_defs}
    )
    """
    cursor.execute(sql)
    conn.commit()

    # FIX: if the table already existed (e.g. same filename uploaded before
    # with a different detected schema), CREATE TABLE IF NOT EXISTS silently
    # does nothing — the new columns never get added. This caused
    # "Unknown column" errors on insert. Now we check for missing columns
    # and ALTER TABLE to add them, so the schema evolves with new uploads.
    cursor.execute(f"DESCRIBE `{safe_name}`")
    existing_cols = {row["Field"] for row in cursor.fetchall()}

    for f in fields:
        if f["field_name"] not in existing_cols:
            try:
                cursor.execute(
                    f"ALTER TABLE `{safe_name}` ADD COLUMN `{f['field_name']}` {f['data_type']}"
                )
                conn.commit()
                logger.info(f"Added missing column `{f['field_name']}` to `{safe_name}`")
            except Exception as e:
                logger.error(f"Failed to add column {f['field_name']}: {e}")

    conn.close()
    return safe_name


def extract_values_from_text(text, fields):
    field_list = ", ".join([f["field_name"] for f in fields])

    # FIX: example now uses the ACTUAL field names for this document instead
    # of a hardcoded unrelated example (invoice_number/customer/amount/date).
    # This was a major cause of the AI returning mismatched keys.
    example = {f["field_name"]: f"<{f['data_type'].lower()} value or null>" for f in fields}

    prompt = f"""
Extract the following fields from the document below.

Return ONLY valid JSON with exactly these keys: {field_list}
If a field's value is not present in the document, use null.

Example format (keys must match exactly):
{json.dumps(example)}

Document:
{text[:2000]}

JSON:
"""
    # FIX: text[:2000] truncation added — previously the FULL document was
    # sent here with no limit, which could exceed the model's context window
    # and cause garbled/truncated output that failed to parse.

    raw = ollama(prompt)
    logger.info(f"RAW EXTRACTION RESPONSE: {raw[:300]}")

    parsed = safe_json_extract(raw, kind="object")
    if not parsed:
        return {}

    # FIX: only keep keys that actually match a real column in the schema.
    # This was the #1 cause of "Unknown column" insert failures being
    # silently swallowed.
    valid_keys = {f["field_name"] for f in fields}
    field_types = {f["field_name"]: f["data_type"] for f in fields}

    cleaned_values = {}
    for k, v in parsed.items():
        key = str(k).strip().lower()
        key = re.sub(r'[^a-z0-9_]', '_', key)
        if key not in valid_keys:
            continue
        if v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "n/a", "none")):
            continue

        # FIX: light type coercion so a DECIMAL/INTEGER column doesn't
        # reject a value like "50,000" or "₹50000".
        dtype = field_types[key]
        if dtype in ("DECIMAL", "INTEGER") and isinstance(v, str):
            numeric = re.sub(r'[^0-9.\-]', '', v)
            if numeric in ("", "-", "."):
                continue
            v = numeric

        cleaned_values[key] = v

    return cleaned_values


# ============================================================
# MODULE 2: QUERY AGENT
# ============================================================

def classify_query(question):
    prompt = f"""
Classify this question into exactly ONE category.
Reply with ONLY one word: SQL or VECTOR or HYBRID

SQL   → specific numbers, counts, filters, comparisons, aggregations
VECTOR → meaning, summary, explanation, context, "what does it say about"
HYBRID → needs both structured data AND contextual explanation

Question: {question}

Reply (one word only):
"""
    result = ollama(prompt).strip().upper()
    for keyword in ["SQL", "HYBRID", "VECTOR"]:
        if keyword in result:
            return keyword
    return "VECTOR"


def get_all_tables():
    conn, cursor = get_cursor()
    cursor.execute("SHOW TABLES")
    rows = cursor.fetchall()
    conn.close()
    tables = []
    for row in rows:
        table_name = list(row.values())[0]
        if table_name != "documents":
            tables.append(table_name)
    return tables


def get_table_schema(table_name):
    conn, cursor = get_cursor()
    cursor.execute(f"DESCRIBE `{table_name}`")
    rows = cursor.fetchall()
    conn.close()
    return [(r["Field"], r["Type"]) for r in rows]


def sql_search(question):
    tables = get_all_tables()
    if not tables:
        return "No structured tables found. Only vector search available."

    schema_info = ""
    for table in tables:
        cols = get_table_schema(table)
        col_str = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
        schema_info += f"Table `{table}`: {col_str}\n"

    prompt = f"""
You are a SQL expert. Write a single MySQL SELECT query to answer the question.
Return ONLY the SQL query. No explanation, no markdown, no backticks, no semicolon-separated multiple statements.

Available tables and columns:
{schema_info}

Question: {question}

SQL query:
"""
    raw_sql = ollama(prompt)
    sql_query = re.sub(r'```sql|```', '', raw_sql).strip()
    sql_query = sql_query.split(";")[0].strip()  # FIX: guard against multiple statements

    # FIX: only allow SELECT queries — the AI could otherwise write a
    # DROP/DELETE/UPDATE and this would execute it directly.
    if not sql_query.upper().startswith("SELECT"):
        logger.warning(f"Blocked non-SELECT query: {sql_query}")
        return "Query blocked: only SELECT statements are allowed."

    try:
        conn, cursor = get_cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "Query returned no results."
        return json.dumps(rows, default=str)
    except Exception as e:
        logger.error(f"SQL execution error: {e} | Query: {sql_query}")
        return f"SQL execution error: {str(e)} | Query attempted: {sql_query}"


def search_similar_documents(query):
    global faiss_index, faiss_documents

    if faiss_index is None:
        rebuild_faiss_index()

    if faiss_index is None:
        return "No documents found in vector database."

    query_embedding = model.encode(query).astype("float32").reshape(1, -1)
    k = min(3, len(faiss_documents))
    distances, indices = faiss_index.search(query_embedding, k=k)

    top_chunks = [faiss_documents[i] for i in indices[0] if 0 <= i < len(faiss_documents)]
    return " ".join(top_chunks) if top_chunks else "No relevant documents found."


def generate_ai_answer(question, context, query_type="VECTOR"):
    prompt = f"""
You are an intelligent assistant analyzing documents and databases.

Answer ONLY from the context provided below.
If the answer is not present, say "Not found in the available data."
Be concise and accurate.

Query Type: {query_type}
Context:
{context[:3000]}

Question:
{question}

Answer:
"""
    # FIX: context truncated to 3000 chars — an unbounded context (e.g. many
    # SQL rows or long vector chunks) could overflow the model context window.
    return ollama(prompt)


# ============================================================
# API ENDPOINTS
# ============================================================

# ---------- UPLOAD ----------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    logger.info(f"Upload started: {file.filename}")
    content = await file.read()
    text = ""

    try:
        if file.filename.endswith(".pdf"):
            pdf = PdfReader(io.BytesIO(content))
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted
            if text.strip() == "":
                image = Image.open(io.BytesIO(content))
                processed = preprocess_image(image)
                text = pytesseract.image_to_string(processed)

        elif file.filename.endswith(".txt"):
            text = content.decode("utf-8")

        elif file.filename.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(content))
            processed = preprocess_image(image)
            text = pytesseract.image_to_string(processed)

        else:
            return {"error": "Unsupported file type. Use PDF, TXT, PNG, JPG."}

        if not text.strip():
            return {"error": "Could not extract any text from the file."}

        # ---------- CLEAN + CHUNK ----------
        cleaned_text = clean_ocr_noise(clean_text(text))
        chunks = chunk_text(cleaned_text)

        # ---------- STORE IN DOCUMENTS TABLE (vector search) ----------
        conn, cursor = get_cursor()
        try:
            for chunk in chunks:
                embedding = model.encode(chunk).tolist()
                cursor.execute(
                    "INSERT INTO documents (filename, content, embedding) VALUES (%s, %s, %s)",
                    (file.filename, chunk, json.dumps(embedding))
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store document chunks: {e}")
        finally:
            conn.close()

        # ---------- AI SCHEMA GENERATION ----------
        schema_result = {"status": "skipped", "table": None, "fields": []}

        fields, suggested_name = generate_schema_from_text(text)
        logger.info(f"Generated fields: {fields} | suggested table: {suggested_name}")

        if fields:
            # FIX: table name now comes from the AI's detected entity type
            # (e.g. "invoices") instead of the raw filename. This means
            # multiple similar documents (invoice1.txt, invoice2.txt, a
            # scanned invoice photo, etc) all land in the SAME table and
            # accumulate rows, instead of each upload creating its own
            # separate 1-row table named after the file.
            table_name = suggested_name or file.filename.rsplit(".", 1)[0]
            created_table = create_table_from_schema(table_name, fields)
            values = extract_values_from_text(text, fields)
            logger.info(f"Extracted values (post-validation): {values}")

            insert_error = None
            if values:
                conn, cursor = get_cursor()
                cols = ", ".join([f"`{k}`" for k in values.keys()])
                placeholders = ", ".join(["%s"] * len(values))
                try:
                    cursor.execute(
                        f"INSERT INTO `{created_table}` (source_file, {cols}) VALUES (%s, {placeholders})",
                        [file.filename] + list(values.values())
                    )
                    conn.commit()
                except Exception as e:
                    # FIX: no longer silently swallowed. Logged AND surfaced
                    # to the API response so the frontend/user can see it.
                    conn.rollback()
                    insert_error = str(e)
                    logger.error(f"Structured insert failed: {e}")
                finally:
                    conn.close()
            else:
                insert_error = "No valid field values could be extracted from the document."

            schema_result = {
                "status": "success" if not insert_error else "partial",
                "table": created_table,
                "fields": fields,
                "extracted_values": values,
                "insert_error": insert_error,
            }

        # ---------- REBUILD FAISS ----------
        rebuild_faiss_index()

        return {
            "message": "File processed successfully",
            "filename": file.filename,
            "chunks_created": len(chunks),
            "preview": chunks[0][:300] if chunks else "",
            "ai_schema": schema_result
        }

    except Exception as e:
        logger.exception("Upload failed")
        return {"error": str(e)}


# ---------- ASK ----------
@app.post("/ask")
async def ask_question(question: str = Query(...)):
    query_type = classify_query(question)

    if query_type == "SQL":
        context = sql_search(question)
    elif query_type == "HYBRID":
        vector_context = search_similar_documents(question)
        sql_context = sql_search(question)
        context = f"Structured Data:\n{sql_context}\n\nDocument Context:\n{vector_context}"
    else:
        context = search_similar_documents(question)

    answer = generate_ai_answer(question, context, query_type)

    return {
        "question": question,
        "query_type": query_type,
        "answer": answer,
        "context_preview": context[:300]
    }


# ---------- LIST TABLES ----------
@app.get("/tables")
async def list_tables():
    tables = get_all_tables()
    result = {}
    for table in tables:
        schema = get_table_schema(table)
        conn, cursor = get_cursor()
        cursor.execute(f"SELECT COUNT(*) as count FROM `{table}`")
        count = cursor.fetchone()["count"]
        conn.close()
        result[table] = {
            "columns": [{"name": c[0], "type": c[1]} for c in schema],
            "row_count": count
        }
    return {"tables": result}


# ---------- GET TABLE DATA ----------
@app.get("/table/{table_name}")
async def get_table_data(table_name: str):
    try:
        safe_name = re.sub(r'[^a-z0-9_]', '_', table_name.lower())
        conn, cursor = get_cursor()
        cursor.execute(f"SELECT * FROM `{safe_name}` LIMIT 50")
        rows = cursor.fetchall()
        conn.close()
        return {"table": safe_name, "rows": rows}
    except Exception as e:
        logger.error(f"get_table_data failed: {e}")
        return {"error": str(e)}


# ---------- HEALTH CHECK ----------
@app.get("/health")
async def health():
    return {"status": "ok", "faiss_loaded": faiss_index is not None}