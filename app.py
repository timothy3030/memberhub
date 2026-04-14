from flask import Flask, render_template, request, redirect, session, send_file, send_from_directory
from datetime import datetime, timedelta
from reportlab.lib.colors import black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import sqlite3
import os
import time

DB_PATH = os.environ.get("DB_PATH", "/tmp/memberhub.db")

UPLOAD_FOLDER = "/tmp/uploads"
CERT_FOLDER = "/tmp/certificates"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CERT_FOLDER, exist_ok=True)

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        membership_type TEXT,
        join_date TEXT,
        expiry_date TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        file_name TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT
    )
    """)

    cursor.execute("SELECT * FROM admin WHERE username=?", ("admin",))
    if not cursor.fetchone():
        default_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        cursor.execute(
            "INSERT INTO admin (username,password) VALUES (?,?)",
            ("admin", default_password)
        )

    conn.commit()
    conn.close()


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "memberhub_secret_dev")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

init_db()


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


# Home / Login
@app.route("/", methods=["GET", "POST"])
def login():
    if "admin" in session:
        return redirect("/dashboard")

    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password)
        )
        admin = cursor.fetchone()
        conn.close()

        if admin:
            session["admin"] = username
            return redirect("/dashboard")
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")


@app.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM members")
    total = cursor.fetchone()[0]

    cursor.execute("""
    SELECT COUNT(*) FROM members
    WHERE expiry_date <= date('now','+7 day')
    AND expiry_date >= date('now')
    """)
    expiring = cursor.fetchone()[0]

    cursor.execute("""
    SELECT name, expiry_date
    FROM members
    WHERE expiry_date <= date('now','+7 day')
    AND expiry_date >= date('now')
    ORDER BY expiry_date
    """)
    expiring_members = cursor.fetchall()

    cursor.execute("""
    SELECT name, email, membership_type
    FROM members
    ORDER BY id DESC
    LIMIT 5
    """)
    recent = cursor.fetchall()

    cursor.execute("""
    SELECT membership_type, COUNT(*)
    FROM members
    GROUP BY membership_type
    """)
    type_data = cursor.fetchall()

    cursor.execute("""
    SELECT date(join_date), COUNT(*)
    FROM members
    GROUP BY date(join_date)
    """)
    data = dict(cursor.fetchall())

    growth_data = []
    for i in range(6, -1, -1):
        day = (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        growth_data.append([day, data.get(day, 0)])

    cursor.execute("SELECT COUNT(*) FROM documents")
    certificates = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        total=total,
        expiring=expiring,
        recent=recent,
        type_data=type_data,
        growth_data=growth_data,
        certificates=certificates,
        expiring_members=expiring_members
    )


# Members
@app.route("/members")
@login_required
def members():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members")
    members = cursor.fetchall()
    conn.close()
    return render_template("members.html", members=members)


# Add Member
@app.route("/add_member")
@login_required
def add_member():
    return render_template("add_member.html")


# Save Member
@app.route("/save_member", methods=["POST"])
@login_required
def save_member():
    name            = request.form["name"]
    email           = request.form["email"]
    phone           = request.form["phone"]
    membership_type = request.form["membership_type"]
    join_date       = request.form["join_date"]
    expiry_date     = request.form["expiry_date"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO members (name, email, phone, membership_type, join_date, expiry_date)
    VALUES (?,?,?,?,?,?)
    """, (name, email, phone, membership_type, join_date, expiry_date))
    conn.commit()
    conn.close()

    return redirect("/members")


# Edit Member
@app.route("/edit/<int:id>")
@login_required
def edit_member(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE id=?", (id,))
    member = cursor.fetchone()
    conn.close()
    return render_template("edit_member.html", member=member)


# Update Member
@app.route("/update_member", methods=["POST"])
@login_required
def update_member():
    id              = request.form["id"]
    name            = request.form["name"]
    email           = request.form["email"]
    phone           = request.form["phone"]
    membership_type = request.form["membership_type"]
    join_date       = request.form["join_date"]
    expiry_date     = request.form["expiry_date"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE members
    SET name=?, email=?, phone=?, membership_type=?, join_date=?, expiry_date=?
    WHERE id=?
    """, (name, email, phone, membership_type, join_date, expiry_date, id))
    conn.commit()
    conn.close()

    return redirect("/members")


# Delete Member
@app.route("/delete/<int:id>")
@login_required
def delete_member(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM members WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/members")


# Search
@app.route("/search", methods=["GET"])
@login_required
def search():
    query = request.args.get("query", "")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM members WHERE name LIKE ? OR email LIKE ?",
        ('%' + query + '%', '%' + query + '%')
    )
    members = cursor.fetchall()
    conn.close()
    return render_template("members.html", members=members)


# Upload Document
@app.route("/upload/<int:id>", methods=["GET", "POST"])
@login_required
def upload(id):
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            timestamp = int(time.time())
            filename = f"{id}_{timestamp}_{file.filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents (member_id, file_name) VALUES (?,?)",
                (id, filename)
            )
            conn.commit()
            conn.close()

            return redirect("/members")

    return render_template("upload.html", member_id=id)


# View Documents
@app.route("/documents/<int:id>")
@login_required
def documents(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_name FROM documents WHERE member_id=?", (id,))
    docs = cursor.fetchall()
    conn.close()
    return render_template("documents.html", docs=docs)


# Generate Certificate
@app.route("/generate_certificate/<name>")
@login_required
def generate_certificate(name):
    file_path = os.path.join(CERT_FOLDER, f"{name}_certificate.pdf")
    c = canvas.Canvas(file_path, pagesize=letter)

    c.setStrokeColor(black)
    c.rect(30, 30, 550, 730)

    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(300, 700, "Certificate of Membership")

    c.setFont("Helvetica", 18)
    c.drawCentredString(300, 640, "This certificate is proudly presented to")

    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(300, 600, name)

    c.setFont("Helvetica", 16)
    c.drawCentredString(300, 560, "for being a valued member of MemberHub")

    c.setFont("Helvetica", 14)
    c.drawCentredString(300, 500, "Congratulations!")

    c.save()

    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
