import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = "postgresql://neondb_owner:npg_yRkNWHg75rvV@ep-shiny-unit-alocqmh9.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require"
CSV_PATH = "laptops.csv"

CREATE_TABLE_SQL = """
DROP TABLE IF EXISTS laptops;
CREATE TABLE laptops (
    id              SERIAL PRIMARY KEY,
    brand           VARCHAR(100),
    name            TEXT,
    price           INTEGER,
    spec_rating     FLOAT,
    processor       TEXT,
    ram             VARCHAR(20),
    storage         VARCHAR(20),
    gpu             TEXT,
    screen_size     FLOAT,
    os              VARCHAR(50),
    stock           INTEGER
);
"""

def setup():
    print("جاري الاتصال بـ Neon...")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    print("جاري انشاء جدول laptops...")
    cur.execute(CREATE_TABLE_SQL)

    print(f"جاري قراءة {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    df = df.rename(columns={
        "Ram":         "ram",
        "ROM":         "storage",
        "GPU":         "gpu",
        "display_size":"screen_size",
        "OS":          "os",
        "Remaining":   "stock",
    })

    cols = ["brand","name","price","spec_rating","processor","ram","storage","gpu","screen_size","os","stock"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.where(pd.notnull(df), None)
    rows = [tuple(row) for row in df.itertuples(index=False, name=None)]

    execute_values(cur, f"INSERT INTO laptops ({','.join(cols)}) VALUES %s", rows)

    conn.commit()
    cur.close()
    conn.close()
    print(f"تم رفع {len(rows)} لاب على Neon بنجاح!")

if __name__ == "__main__":
    setup()
