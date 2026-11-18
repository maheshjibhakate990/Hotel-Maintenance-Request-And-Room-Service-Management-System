from flask import Flask, request, redirect, url_for, session, flash, send_file, render_template_string
import mysql.connector
import pandas as pd
import numpy as np
import cv2
import os
from io import BytesIO
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "hotel_management_secret_key"

# CHANGE MYSQL PASSWORD HERE
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "2005",
    "database": "hotel_management"
}

os.makedirs("uploads", exist_ok=True)


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def setup_database():
    config = DB_CONFIG.copy()
    config.pop("database")

    con = mysql.connector.connect(**config)
    cur = con.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS hotel_management")
    cur.close()
    con.close()

    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE,
        password VARCHAR(255),
        role VARCHAR(50)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms(
        id INT AUTO_INCREMENT PRIMARY KEY,
        room_number VARCHAR(20) UNIQUE,
        room_type VARCHAR(50),
        floor_number INT,
        capacity INT,
        price_per_night FLOAT,
        status VARCHAR(30)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS guests(
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        phone VARCHAR(30),
        email VARCHAR(100),
        id_proof VARCHAR(100)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_requests(
        id INT AUTO_INCREMENT PRIMARY KEY,
        room_id INT,
        issue_type VARCHAR(100),
        description TEXT,
        priority VARCHAR(30),
        assigned_to VARCHAR(100),
        status VARCHAR(30),
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE SET NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS room_service_orders(
        id INT AUTO_INCREMENT PRIMARY KEY,
        room_id INT,
        guest_id INT,
        item_name VARCHAR(100),
        quantity INT,
        unit_price FLOAT,
        status VARCHAR(30),
        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE SET NULL,
        FOREIGN KEY(guest_id) REFERENCES guests(id) ON DELETE SET NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id INT AUTO_INCREMENT PRIMARY KEY,
        category VARCHAR(100),
        description TEXT,
        amount FLOAT,
        expense_date DATE
    )
    """)

    cur.execute("SELECT id FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(username,password,role) VALUES(%s,%s,%s)",
            ("admin", "admin123", "Admin")
        )

    cur.execute("SELECT COUNT(*) FROM rooms")
    if cur.fetchone()[0] == 0:
        rooms = [
            ("101", "Standard", 1, 2, 1800, "Available"),
            ("102", "Deluxe", 1, 2, 2600, "Occupied"),
            ("201", "Deluxe", 2, 2, 2800, "Available"),
            ("202", "Suite", 2, 4, 4500, "Maintenance"),
            ("301", "Family", 3, 4, 3800, "Available")
        ]

        cur.executemany("""
        INSERT INTO rooms
        (room_number,room_type,floor_number,capacity,price_per_night,status)
        VALUES(%s,%s,%s,%s,%s,%s)
        """, rooms)

    con.commit()
    cur.close()
    con.close()


def execute(sql, values=(), fetch=False):
    con = get_db()
    cur = con.cursor(dictionary=True)

    try:
        cur.execute(sql, values)
        result = cur.fetchall() if fetch else cur.lastrowid
        con.commit()
        return result
    finally:
        cur.close()
        con.close()


# ---------------- LOGIN SYSTEM ----------------

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


# ---------------- COMMON DESIGN ----------------

BASE = """
<!DOCTYPE html>
<html>
<head>
<title>Hotel Management System</title>
<style>
body{font-family:Arial;background:#f1f4f8;margin:0}
header{background:#17324d;color:white;padding:20px}
nav{background:#244b6b;padding:15px}
nav a{color:white;text-decoration:none;margin:10px}
main{padding:25px}
.card{background:white;padding:20px;margin:15px 0;border-radius:8px}
input,select,textarea{padding:10px;margin:5px;border:1px solid #ccc}
button,.btn{background:#176b87;color:white;padding:10px;border:0;cursor:pointer;text-decoration:none}
table{width:100%;background:white;border-collapse:collapse}
td,th{padding:12px;border:1px solid #ddd;text-align:left}
th{background:#dce8ef}
.stat{display:inline-block;background:white;padding:25px;margin:10px;min-width:150px}
</style>
</head>
<body>
<header>
<h2>HOTEL MAINTENANCE & ROOM SERVICE MANAGEMENT</h2>
Welcome {{session.get('user','')}}
<a style="color:white;float:right" href="/logout">Logout</a>
</header>

{% if session.get('user') %}
<nav>
<a href="/dashboard">Dashboard</a>
<a href="/rooms">Rooms</a>
<a href="/guests">Guests</a>
<a href="/maintenance">Maintenance</a>
<a href="/room-service">Room Service</a>
<a href="/expenses">Expenses</a>
<a href="/analytics">Analytics</a>
<a href="/reports">Reports</a>
<a href="/image-processing">Image Processing</a>
</nav>
{% endif %}

<main>
{% for msg in get_flashed_messages() %}
<div class="card">{{msg}}</div>
{% endfor %}
{{content|safe}}
</main>
</body>
</html>
"""


def page(html, **data):
    content = render_template_string(html, **data)
    return render_template_string(BASE, content=content)


def make_table(rows):
    if not rows:
        return "<p>No records found.</p>"

    html = "<table><tr>"

    for key in rows[0]:
        html += f"<th>{key}</th>"

    html += "</tr>"

    for row in rows:
        html += "<tr>"
        for value in row.values():
            html += f"<td>{value if value is not None else ''}</td>"
        html += "</tr>"

    return html + "</table>"


# ---------------- LOGIN ----------------

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        users = execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password), True
        )

        if users:
            session["user"] = username
            return redirect("/dashboard")

        flash("Invalid username or password.")

    return page("""
    <div class="card" style="max-width:400px;margin:70px auto">
    <h2>Admin Login</h2>
    <form method="post">
    <input name="username" placeholder="Username" required><br>
    <input name="password" type="password" placeholder="Password" required><br>
    <button>Login</button>
    </form>
    <p>Default: admin / admin123</p>
    </div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():

    rooms = execute("SELECT COUNT(*) AS total FROM rooms", fetch=True)[0]["total"]
    guests = execute("SELECT COUNT(*) AS total FROM guests", fetch=True)[0]["total"]
    maintenance = execute(
        "SELECT COUNT(*) AS total FROM maintenance_requests WHERE status='Pending'",
        fetch=True
    )[0]["total"]

    orders = execute(
        "SELECT COUNT(*) AS total FROM room_service_orders WHERE status='Pending'",
        fetch=True
    )[0]["total"]

    return page("""
    <h2>Dashboard</h2>
    <div class="stat">Total Rooms<h1>{{rooms}}</h1></div>
    <div class="stat">Total Guests<h1>{{guests}}</h1></div>
    <div class="stat">Pending Maintenance<h1>{{maintenance}}</h1></div>
    <div class="stat">Pending Orders<h1>{{orders}}</h1></div>
    <div class="card">
    <h3>Welcome to Hotel Management System</h3>
    Manage hotel rooms, guests, maintenance and room service.
    </div>
    """, rooms=rooms, guests=guests,
         maintenance=maintenance, orders=orders)


# ---------------- ROOMS ----------------

@app.route("/rooms", methods=["GET", "POST"])
@login_required
def rooms():

    if request.method == "POST":
        execute("""
        INSERT INTO rooms
        (room_number,room_type,floor_number,capacity,price_per_night,status)
        VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            request.form["room_number"],
            request.form["room_type"],
            request.form["floor_number"],
            request.form["capacity"],
            request.form["price"],
            request.form["status"]
        ))

        flash("Room added successfully.")
        return redirect("/rooms")

    rows = execute("SELECT * FROM rooms", fetch=True)

    return page("""
    <h2>Room Management</h2>
    <div class="card">
    <h3>Add Room</h3>
    <form method="post">
    <input name="room_number" placeholder="Room Number" required>
    <input name="room_type" placeholder="Room Type" required>
    <input name="floor_number" type="number" placeholder="Floor" required>
    <input name="capacity" type="number" placeholder="Capacity" required>
    <input name="price" type="number" placeholder="Price" required>
    <select name="status">
    <option>Available</option>
    <option>Occupied</option>
    <option>Maintenance</option>
    </select>
    <button>Add Room</button>
    </form>
    </div>
    <div class="card">{{table|safe}}</div>
    """, table=make_table(rows))


# ---------------- GUESTS ----------------

@app.route("/guests", methods=["GET", "POST"])
@login_required
def guests():

    if request.method == "POST":
        execute("""
        INSERT INTO guests(name,phone,email,id_proof)
        VALUES(%s,%s,%s,%s)
        """, (
            request.form["name"],
            request.form["phone"],
            request.form["email"],
            request.form["id_proof"]
        ))

        flash("Guest added successfully.")
        return redirect("/guests")

    rows = execute("SELECT * FROM guests", fetch=True)

    return page("""
    <h2>Guest Management</h2>
    <div class="card">
    <form method="post">
    <input name="name" placeholder="Guest Name" required>
    <input name="phone" placeholder="Phone">
    <input name="email" placeholder="Email">
    <input name="id_proof" placeholder="ID Proof">
    <button>Add Guest</button>
    </form>
    </div>
    <div class="card">{{table|safe}}</div>
    """, table=make_table(rows))


# ---------------- MAINTENANCE ----------------

@app.route("/maintenance", methods=["GET", "POST"])
@login_required
def maintenance():

    if request.method == "POST":
        execute("""
        INSERT INTO maintenance_requests
        (room_id,issue_type,description,priority,assigned_to,status)
        VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            request.form["room_id"],
            request.form["issue_type"],
            request.form["description"],
            request.form["priority"],
            request.form["assigned_to"],
            request.form["status"]
        ))

        flash("Maintenance request added.")
        return redirect("/maintenance")

    rooms = execute("SELECT id,room_number FROM rooms", fetch=True)

    rows = execute("""
    SELECT m.id,r.room_number,m.issue_type,m.description,
    m.priority,m.assigned_to,m.status,m.request_date
    FROM maintenance_requests m
    LEFT JOIN rooms r ON m.room_id=r.id
    ORDER BY m.id DESC
    """, fetch=True)

    return page("""
    <h2>Maintenance Requests</h2>
    <div class="card">
    <form method="post">
    <select name="room_id">
    {% for r in rooms %}
    <option value="{{r.id}}">{{r.room_number}}</option>
    {% endfor %}
    </select>
    <input name="issue_type" placeholder="Issue Type" required>
    <input name="assigned_to" placeholder="Assigned Staff">
    <select name="priority">
    <option>Low</option><option>Medium</option>
    <option>High</option><option>Urgent</option>
    </select>
    <select name="status">
    <option>Pending</option><option>In Progress</option><option>Completed</option>
    </select>
    <textarea name="description" placeholder="Description"></textarea>
    <button>Add Request</button>
    </form>
    </div>
    <div class="card">{{table|safe}}</div>
    """, rooms=rooms, table=make_table(rows))


# ---------------- ROOM SERVICE ----------------

@app.route("/room-service", methods=["GET", "POST"])
@login_required
def room_service():

    if request.method == "POST":
        execute("""
        INSERT INTO room_service_orders
        (room_id,guest_id,item_name,quantity,unit_price,status)
        VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            request.form["room_id"],
            request.form.get("guest_id") or None,
            request.form["item_name"],
            request.form["quantity"],
            request.form["unit_price"],
            request.form["status"]
        ))

        flash("Room service order added.")
        return redirect("/room-service")

    rooms = execute("SELECT id,room_number FROM rooms", fetch=True)
    guests = execute("SELECT id,name FROM guests", fetch=True)

    rows = execute("""
    SELECT o.id,r.room_number,g.name AS guest_name,
    o.item_name,o.quantity,o.unit_price,o.status,o.order_date
    FROM room_service_orders o
    LEFT JOIN rooms r ON o.room_id=r.id
    LEFT JOIN guests g ON o.guest_id=g.id
    ORDER BY o.id DESC
    """, fetch=True)

    return page("""
    <h2>Room Service Management</h2>
    <div class="card">
    <form method="post">
    <select name="room_id">
    {% for r in rooms %}
    <option value="{{r.id}}">{{r.room_number}}</option>
    {% endfor %}
    </select>
    <select name="guest_id">
    <option value="">Select Guest</option>
    {% for g in guests %}
    <option value="{{g.id}}">{{g.name}}</option>
    {% endfor %}
    </select>
    <input name="item_name" placeholder="Food / Item" required>
    <input name="quantity" type="number" value="1" min="1" required>
    <input name="unit_price" type="number" step="0.01" placeholder="Price" required>
    <select name="status">
    <option>Pending</option><option>Preparing</option>
    <option>Delivered</option><option>Cancelled</option>
    </select>
    <button>Add Order</button>
    </form>
    </div>
    <div class="card">{{table|safe}}</div>
    """, rooms=rooms, guests=guests, table=make_table(rows))


# ---------------- EXPENSES ----------------

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():

    if request.method == "POST":
        execute("""
        INSERT INTO expenses(category,description,amount,expense_date)
        VALUES(%s,%s,%s,%s)
        """, (
            request.form["category"],
            request.form["description"],
            request.form["amount"],
            request.form["expense_date"]
        ))

        flash("Expense added.")
        return redirect("/expenses")

    rows = execute("SELECT * FROM expenses ORDER BY id DESC", fetch=True)

    return page("""
    <h2>Expense Management</h2>
    <div class="card">
    <form method="post">
    <input name="category" placeholder="Category" required>
    <input name="description" placeholder="Description">
    <input name="amount" type="number" step="0.01" placeholder="Amount" required>
    <input name="expense_date" type="date" required>
    <button>Add Expense</button>
    </form>
    </div>
    <div class="card">{{table|safe}}</div>
    """, table=make_table(rows))


# ---------------- ANALYTICS ----------------

@app.route("/analytics")
@login_required
def analytics():

    expense = execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM expenses",
        fetch=True
    )[0]["total"]

    service = execute(
        "SELECT COALESCE(SUM(quantity*unit_price),0) AS total FROM room_service_orders",
        fetch=True
    )[0]["total"]

    statuses = execute(
        "SELECT status,COUNT(*) AS total FROM rooms GROUP BY status",
        fetch=True
    )

    counts = np.array([x["total"] for x in statuses])

    return page("""
    <h2>Hotel Analytics</h2>
    <div class="stat">Total Expenses<h2>₹{{expense}}</h2></div>
    <div class="stat">Room Service Sales<h2>₹{{service}}</h2></div>
    <div class="stat">Total Rooms<h2>{{rooms}}</h2></div>
    <div class="card">{{table|safe}}</div>
    """, expense=expense, service=service,
         rooms=int(np.sum(counts)), table=make_table(statuses))


# ---------------- EXCEL REPORT ----------------

@app.route("/reports")
@login_required
def reports():
    return page("""
    <h2>Reports</h2>
    <div class="card">
    <p>Download all hotel records in Excel format.</p>
    <a class="btn" href="/export">Download Excel Report</a>
    </div>
    """)


@app.route("/export")
@login_required
def export():

    tables = {
        "Rooms": "SELECT * FROM rooms",
        "Guests": "SELECT * FROM guests",
        "Maintenance": "SELECT * FROM maintenance_requests",
        "Room_Service": "SELECT * FROM room_service_orders",
        "Expenses": "SELECT * FROM expenses"
    }

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, sql in tables.items():
            data = execute(sql, fetch=True)
            pd.DataFrame(data).to_excel(
                writer, sheet_name=sheet, index=False
            )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="Hotel_Report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------- OPENCV IMAGE PROCESSING ----------------

@app.route("/image-processing", methods=["GET", "POST"])
@login_required
def image_processing():

    image_name = None

    if request.method == "POST":
        file = request.files["image"]

        if file:
            data = np.frombuffer(file.read(), np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)

            if image is not None:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

                image_name = "processed_" + datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg"

                cv2.imwrite(
                    os.path.join("uploads", image_name),
                    gray
                )

    return page("""
    <h2>Image Processing</h2>
    <div class="card">
    <form method="post" enctype="multipart/form-data">
    <input type="file" name="image" accept="image/*" required>
    <button>Process Image</button>
    </form>

    {% if image_name %}
    <h3>Processed Image</h3>
    <img src="/uploads/{{image_name}}" width="400">
    {% endif %}
    </div>
    """, image_name=image_name)


@app.route("/uploads/<filename>")
@login_required
def uploaded_image(filename):
    return send_file(os.path.join("uploads", filename))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":

    try:
        setup_database()
        print("MySQL Database Connected Successfully!")
        print("Open: http://127.0.0.1:5000")
        app.run(debug=True)

    except mysql.connector.Error as e:
        print("MYSQL CONNECTION ERROR:", e)
        print("Check your MySQL password in DB_CONFIG.")