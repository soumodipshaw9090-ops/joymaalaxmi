import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "shop.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB uploads

# ---------------------------------------------------------------------------
# Shop / admin settings (edit these for your shop, or move to a config file)
# ---------------------------------------------------------------------------
SHOP_NAME = "Joy Maa Laxmi Enterprises"
SHOP_TAGLINE = "Wheeling and dealing in slick lubricants and every auto part under the sun!"
SHOP_PHONE_1 = "+91 7439297237"
SHOP_PHONE_2 = "+91 6289388558"
SHOP_EMAIL = "joymaalaxmi2k26@gmail.com"
SHOP_ADDRESS = "23, G.T Road, Uttarpara, Hooghly - 712258, West Bengal, India"

# GST registration details (from Form GST REG-06, Registration Certificate)
GST_NUMBER = "19BKZPD8808D1ZO"
GST_LEGAL_NAME = "Dipsankar Das"
GST_CONSTITUTION = "Proprietorship"
GST_PRINCIPAL_ADDRESS = "N/A, Ghoshpara, Nischinda, Rabindranagar, Bally, Howrah, West Bengal, 711227"
GST_ADDITIONAL_ADDRESS = "2nd, 2C, Casa Del Tower 1, 2 No Govt Colony, Puja Sweets, 2 No Govt Colony Bazar, Uttarpara Kotrung, Hooghly, West Bengal, 712233"
GST_VALID_FROM = "08/04/2022"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# Default password is "changeme123" -- CHANGE THIS before going live (see README)
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    generate_password_hash(os.environ.get("ADMIN_PASSWORD", "changeme123"))
)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            product_code TEXT,
            description TEXT,
            price REAL NOT NULL DEFAULT 0,
            warranty TEXT,
            stock INTEGER DEFAULT 100,
            image_filename TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            address TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'New',
            stock_deducted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            price_each REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        """
    )
    # Migration: add stock_deducted column for databases created before this feature existed.
    try:
        db.execute("ALTER TABLE orders ADD COLUMN stock_deducted INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    db.commit()
    db.close()


def seed_db_if_empty():
    """Seed with categories + the SF Batteries price list so the site isn't empty on first run."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    count = db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    if count > 0:
        db.close()
        return

    categories = [
        "Vehicular Batteries", "2-Wheeler Batteries", "Lubricants & Oils", "Auto Parts",
        "Inverter Batteries", "Inverters (PowerSmart)",
    ]
    cat_ids = {}
    for c in categories:
        cur = db.execute("INSERT INTO categories (name) VALUES (?)", (c,))
        cat_ids[c] = cur.lastrowid

    # A representative slice of the SF Batteries MRCP price list (10 June 2026)
    batteries = [
        # (name, code, warranty, price, category)
        ("Car/SUV 4W Series 72 - 35Ah", "72S-35R/L", "36F+36P", 4935, "Vehicular Batteries"),
        ("Car/SUV 4W Series 72 - 45Ah", "72S-55LS", "36F+36P", 8299, "Vehicular Batteries"),
        ("Car/SUV 4W Series 72 - 74Ah", "72S-DIN74L", "36F+36P", 12592, "Vehicular Batteries"),
        ("Car/SUV 4W Series 66 - 35Ah", "66S-38B20R/L", "30F+36P", 4610, "Vehicular Batteries"),
        ("Car/SUV 4W Series 60 - 44Ah", "60S-DIN44R/LH", "30F+30P", 6674, "Vehicular Batteries"),
        ("Car/SUV 4W Series 60 - 50Ah", "60S-DIN50L", "30F+30P", 7439, "Vehicular Batteries"),
        ("Car/SUV 4W Series 48 - 35Ah", "48S-38B20L/R", "24F+24P", 4430, "Vehicular Batteries"),
        ("Car/SUV 4W Series 48 - 65Ah", "48S-70R/L", "24F+24P", 8118, "Vehicular Batteries"),
        ("Car/SUV Hybrid X - 38Ah", "HX-M42", "30F+30P", 5932, "Vehicular Batteries"),
        ("CV Trucker Series 42 - 80Ah", "42S-80R", "24F+18P", 8013, "Vehicular Batteries"),
        ("Tractor Series 42 - 75Ah", "42S-75R/RFT", "24F+18P", 7931, "Vehicular Batteries"),
        ("2WL 2W Series 48 - 2.5Ah", "48S-TZ2.5L", "24F+24P", 1053, "2-Wheeler Batteries"),
        ("2WL 2W Series 48 - 4Ah", "48S-TZ4A", "24F+24P", 1198, "2-Wheeler Batteries"),
        ("2WL 2W Series 48 - 5Ah", "48S-TZ5A", "24F+24P", 1432, "2-Wheeler Batteries"),
        ("2WL 2W Series 48 - 9Ah", "48S-TZ9", "24F+24P", 2230, "2-Wheeler Batteries"),
        ("2WL 2W Series 48 - 12Ah", "48S-TX14", "24F+24P", 3435, "2-Wheeler Batteries"),
        ("2WL 2W Series 48 - 14Ah", "48S-14L-A2", "24F+24P", 3872, "2-Wheeler Batteries"),
    ]
    for name, code, warranty, price, cat in batteries:
        db.execute(
            """INSERT INTO products (name, category_id, product_code, description, price, warranty, image_filename)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (name, cat_ids[cat], code, f"SF Batteries {name}. MRCP as on 10th June 2026.", price, warranty),
        )

    # Inverter batteries (SF Protubular / Protubular+ / Flat Plate / Exide Home Invamagic)
    inverter_batteries = [
        ("SF Protubular+ Tall Tubular 150Ah", "FSP0-TT60S150", "36F+24P", 20125),
        ("SF Protubular+ Tall Tubular 200Ah", "FSP0-TT60S200", "36F+24P", 25576),
        ("SF Protubular+ Tall Tubular 220Ah", "FSP0-TT60S220", "36F+24P", 28733),
        ("SF Protubular+ Tall Tubular 250Ah", "FSP0-TT60S250", "36F+24P", 34011),
        ("SF Protubular+ Tall Tubular 150Ah (48M)", "FSP1-TT48S150", "24F+24P", 19622),
        ("SF Protubular+ Tall Tubular 180Ah (48M)", "FSP0-TT48S180", "24F+24P", 23634),
        ("SF Protubular+ Tall Tubular 200Ah (48M)", "FSP0-TT48S200", "24F+24P", 23993),
        ("SF Protubular Short Tubular 100Ah (60M)", "FSP3-ST60S100", "36F+24P", 15756),
        ("SF Protubular Short Tubular 150Ah (60M)", "FSP3-ST60S150", "36F+24P", 19652),
        ("SF Protubular Short Tubular 120Ah (48M)", "FSP0-ST48S120", "24F+24P", 14399),
        ("SF Inverter Battery Flat Plate 100Ah", "FSI0-FP42S1200", "21F+21P", 12452),
        ("SF Inverter Battery Flat Plate 138Ah", "FSI0-FP42S1500", "21F+21P", 16917),
        ("Exide Home Invamagic Hi Backup 400W 02:00", "48HBST2000", "24F+24P", 14399),
        ("Exide Home Invamagic Hi Backup 400W 02:25", "48HBST2250", "24F+24P", 16898),
    ]
    for name, code, warranty, price in inverter_batteries:
        db.execute(
            """INSERT INTO products (name, category_id, product_code, description, price, warranty, image_filename)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (name, cat_ids["Inverter Batteries"], code,
             f"{name}. MRCP inclusive of GST, effective 1st July 2026.", price, warranty),
        )

    # PowerSmart pure sine wave inverters / UPS units
    powersmart_inverters = [
        ("SF PowerSmart Sine Pro CU 900 (12V)", "HF00-SNPROCU900", "MC Cu Pure Sine", "42M", 10010),
        ("SF PowerSmart Sine Pro CU 1200 (12V)", "HF00-SNPROCU1200", "MC Cu Pure Sine", "42M", 11535),
        ("SF PowerSmart Sine Pro AL 700 (12V)", "HF00-SNPROAL700", "MC Al Pure Sine", "42M", 7386),
        ("SF PowerSmart Sine Pro AL 900 (12V)", "HF00-SNPROAL900", "MC Al Pure Sine", "42M", 7720),
        ("SF PowerSmart Sine Pro AL 1200 (12V)", "HF00-SNPROAL1200", "MC Al Pure Sine", "42M", 8451),
        ("SF PowerSmart Sine Pro AL 1500 (24V)", "HF00-SNPROAL1500", "MC Al Pure Sine", "42M", 11943),
        ("SF PowerSmart Sine Pro AL 2200 (24V)", "HF00-SNPROAL2200", "MC Al Pure Sine", "42M", 16069),
        ("SF PowerSmart Sine Pro AL 2750 (24V)", "HF00-SNPROAL2750", "MC Al Pure Sine", "42M", 15710),
        ("SF PowerSmart SQ Pro AL 850 (12V)", "HF00-SQPROAL850", "MC Aluminium", "42M", 6516),
        ("SF PowerSmart SQ Pro AL 950 (12V)", "HF00-SQPROAL950", "MC Aluminium", "42M", 6873),
        ("SF PowerSmart SQ Pro AL 1250 (12V)", "HF00-SQPROAL1250", "MC Aluminium", "42M", 7408),
        ("SF PowerSmart SQ Pro AL 1750 (24V)", "HF00-SQPROAL1750", "MC Aluminium", "42M", 10310),
        ("SF PowerSmart Sine Pro Plus 2.5KVA (36V)", "SNPP036V02500", "DSP Al Pure Sine", "24M", 27323),
        ("SF PowerSmart Sine Pro Plus 2.5KVA (48V)", "SNPP048V02500", "DSP Al Pure Sine", "24M", 29145),
        ("SF PowerSmart Sine Pro Plus 3.5KVA (48V)", "SNPP048V03500", "DSP Al Pure Sine", "24M", 30967),
        ("SF PowerSmart Sine Pro Plus 5.2KVA (48V)", "SNPP048V05200", "DSP Al Pure Sine", "24M", 54647),
        ("SF PowerSmart Sine Pro Plus 10KVA (180V)", "SNPP180V10000", "DSP Cu Pure Sine", "24M", 109294),
    ]
    for name, code, ptype, warranty, price in powersmart_inverters:
        db.execute(
            """INSERT INTO products (name, category_id, product_code, description, price, warranty, image_filename)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (name, cat_ids["Inverters (PowerSmart)"], code,
             f"{name} — {ptype}. MRCP inclusive of GST, effective 1st July 2026.", price, warranty),
        )

    db.commit()
    db.close()


# SUNOIL lubricants & greases price list (rates as on file, retail price used as customer price)
SUNOIL_LUBRICANTS = [
    # (sl_code, name, pack, stock_cartons, retail_price)
    ("SUN-01", "RX Gear 90/140 Gear Oil", "1 Lt", 2, 230),
    ("SUN-02", "RX Gear 90/140 Gear Oil", "500ml", 7, 130),
    ("SUN-03", "RX Gear 90/140 Gear Oil", "350ml", 10, 100),
    ("SUN-04", "Shocker Oil (Water Colour)", "350ml", 7, 125),
    ("SUN-05", "Shocker Oil (Water Colour)", "175ml", 19, 85),
    ("SUN-06", "Sunol Super 4T 10W-30 SN", "1 Lt", 3, 325),
    ("SUN-07", "Sunol Super 4T 10W-30 SN", "900ml", 27, 315),
    ("SUN-08", "Sunol Super 4T 10W-30 SN", "800ml", 4, 305),
    ("SUN-09", "Sunol Super 4T 20W-50 SN", "1 Lt", 2, 325),
    ("SUN-10", "RLO 4T 20W-40", "1 Lt", 4, 285),
    ("SUN-11", "RLO 4T 20W-40", "900ml", 9, 275),
    ("SUN-12", "Sunol Super 4T 20W-40 SN", "900ml", 22, 300),
    ("SUN-13", "Sunol Super 4T 20W-40 SN", "1 Lt", 3, 320),
    ("SUN-14", "RLO 20W-50 CNG Green Special", "1 Lt", 4, 295),
    ("SUN-15", "Brake Fluid", "250ml", 26, 100),
    ("SUN-16", "CG Super 3 Grease", "200ml", 6, 85),
    ("SUN-17", "CG Super 3 Grease", "500ml", 0, 165),
    ("SUN-18", "CG Super 3 Grease Red Gel", "500ml", 3, 165),
    ("SUN-19", "Lazer 3 Grease (Milk White) Ball Racer", "200ml", 15, 105),
    ("SUN-20", "Lazer 3 Grease (Milk White) Ball Racer", "500ml", 5, 245),
    ("SUN-21", "Sunol AP-3 Grease", "200ml", 7, 120),
    ("SUN-22", "Sunol AP-3 Grease", "500ml", 5, 235),
    ("SUN-23", "Sunol Protect Plus", "200ml", 2, 125),
    ("SUN-24", "Sunol Protect Plus", "500ml", 2, 250),
    ("SUN-25", "Sunol 2T Super (API-TC & JASO FC)", "500ml", 2, 170),
    ("SUN-26", "Sunol 2T Super (API-TC & JASO FC)", "1 Lt", 2, 310),
    ("SUN-27", "RX 40 Engine Oil", "500ml", 2, 140),
    ("SUN-28", "Sunol Turbo Plus 20W-50", "3 Lt", 3, 950),
    ("SUN-29", "Engine Coolant", "500ml", 2, 130),
    ("SUN-30", "Engine Coolant", "1 Lt", 2, 250),
    ("SUN-31", "Sunol Double Duty Engine Oil-40", "5 Lt", 2, 1750),
]


def sync_lubricant_products():
    """Add the SUNOIL lubricants price list into 'Lubricants & Oils', skipping any already added."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cat = db.execute("SELECT id FROM categories WHERE name = ?", ("Lubricants & Oils",)).fetchone()
    if not cat:
        cur = db.execute("INSERT INTO categories (name) VALUES (?)", ("Lubricants & Oils",))
        cat_id = cur.lastrowid
    else:
        cat_id = cat["id"]

    for code, name, pack, stock, price in SUNOIL_LUBRICANTS:
        exists = db.execute("SELECT 1 FROM products WHERE product_code = ?", (code,)).fetchone()
        if exists:
            continue
        full_name = f"{name} {pack}"
        db.execute(
            """INSERT INTO products (name, category_id, product_code, description, price, warranty, stock, image_filename)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (full_name, cat_id, code, f"{full_name}. SUNOIL retail price list.", price, None, stock),
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_shop_info():
    return dict(
        SHOP_NAME=SHOP_NAME,
        SHOP_TAGLINE=SHOP_TAGLINE,
        SHOP_PHONE_1=SHOP_PHONE_1,
        SHOP_PHONE_2=SHOP_PHONE_2,
        SHOP_EMAIL=SHOP_EMAIL,
        SHOP_ADDRESS=SHOP_ADDRESS,
        GST_NUMBER=GST_NUMBER,
        GST_LEGAL_NAME=GST_LEGAL_NAME,
        GST_CONSTITUTION=GST_CONSTITUTION,
        GST_PRINCIPAL_ADDRESS=GST_PRINCIPAL_ADDRESS,
        GST_ADDITIONAL_ADDRESS=GST_ADDITIONAL_ADDRESS,
        GST_VALID_FROM=GST_VALID_FROM,
    )


# ---------------------------------------------------------------------------
# Storefront routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    selected_cat = request.args.get("category", type=int)
    q = request.args.get("q", "").strip()

    query = "SELECT * FROM products WHERE is_active = 1"
    params = []
    if selected_cat:
        query += " AND category_id = ?"
        params.append(selected_cat)
    if q:
        query += " AND (name LIKE ? OR product_code LIKE ? OR description LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    query += " ORDER BY created_at DESC"
    products = db.execute(query, params).fetchall()

    return render_template(
        "index.html",
        categories=categories,
        products=products,
        selected_cat=selected_cat,
        q=q,
    )


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
    if not product:
        abort(404)
    related = db.execute(
        "SELECT * FROM products WHERE category_id = ? AND id != ? AND is_active = 1 LIMIT 4",
        (product["category_id"], product_id),
    ).fetchall()
    return render_template("product.html", product=product, related=related)


@app.route("/order/<int:product_id>", methods=["GET", "POST"])
def order_product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
    if not product:
        abort(404)

    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        try:
            qty = max(1, int(request.form.get("quantity", 1)))
        except ValueError:
            qty = 1

        if not name or not phone or not address:
            flash("Please fill in your name, phone number and address.", "error")
            return render_template("order_form.html", product=product)

        cur = db.execute(
            "INSERT INTO orders (customer_name, phone, email, address, notes) VALUES (?, ?, ?, ?, ?)",
            (name, phone, email, address, notes),
        )
        order_id = cur.lastrowid
        db.execute(
            """INSERT INTO order_items (order_id, product_id, product_name, quantity, price_each)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, product["id"], product["name"], qty, product["price"]),
        )
        db.commit()
        return redirect(url_for("order_success", order_id=order_id))

    return render_template("order_form.html", product=product)


@app.route("/order-success/<int:order_id>")
def order_success(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    return render_template("order_success.html", order=order, items=items)


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["is_admin"] = True
            flash("Welcome back!", "success")
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    order_count = db.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    new_count = db.execute("SELECT COUNT(*) c FROM orders WHERE status = 'New'").fetchone()["c"]
    product_count = db.execute("SELECT COUNT(*) c FROM products WHERE is_active = 1").fetchone()["c"]
    recent_orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 6").fetchall()
    return render_template(
        "admin_dashboard.html",
        order_count=order_count,
        new_count=new_count,
        product_count=product_count,
        recent_orders=recent_orders,
    )


@app.route("/admin/orders")
@login_required
def admin_orders():
    db = get_db()
    orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    orders_with_items = []
    for o in orders:
        items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (o["id"],)).fetchall()
        orders_with_items.append((o, items))
    return render_template("admin_orders.html", orders_with_items=orders_with_items)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@login_required
def admin_update_order_status(order_id):
    new_status = request.form.get("status", "New")
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)

    was_delivered = order["status"] == "Delivered" and order["stock_deducted"]

    if new_status == "Delivered" and not was_delivered:
        # Moving into "Delivered": deduct each ordered item's quantity from that product's stock.
        items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            if item["product_id"] is not None:
                db.execute(
                    "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )
        db.execute("UPDATE orders SET status = ?, stock_deducted = 1 WHERE id = ?", (new_status, order_id))
        flash("Order marked Delivered — stock updated.", "success")
    elif new_status != "Delivered" and was_delivered:
        # Moving OUT of "Delivered" (e.g. correcting a mistake): put the stock back.
        items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            if item["product_id"] is not None:
                db.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )
        db.execute("UPDATE orders SET status = ?, stock_deducted = 0 WHERE id = ?", (new_status, order_id))
        flash("Order status updated — stock restored.", "success")
    else:
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        flash("Order status updated.", "success")

    db.commit()
    return redirect(url_for("admin_orders"))


@app.route("/admin/products")
@login_required
def admin_products():
    db = get_db()
    products = db.execute(
        """SELECT p.*, c.name AS category_name FROM products p
           LEFT JOIN categories c ON p.category_id = c.id
           ORDER BY p.created_at DESC"""
    ).fetchall()
    return render_template("admin_products.html", products=products)


@app.route("/admin/products/new", methods=["GET", "POST"])
@login_required
def admin_add_product():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id") or None
        product_code = request.form.get("product_code", "").strip()
        description = request.form.get("description", "").strip()
        warranty = request.form.get("warranty", "").strip()
        try:
            price = float(request.form.get("price", 0))
        except ValueError:
            price = 0
        try:
            stock = int(request.form.get("stock", 100))
        except ValueError:
            stock = 100

        image_filename = None
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
            image_filename = unique_name

        if not name:
            flash("Product name is required.", "error")
            return render_template("admin_add_product.html", categories=categories, product=None)

        db.execute(
            """INSERT INTO products
               (name, category_id, product_code, description, price, warranty, stock, image_filename)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, category_id, product_code, description, price, warranty, stock, image_filename),
        )
        db.commit()
        flash(f'"{name}" was added.', "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html", categories=categories, product=None)


@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_product(product_id):
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id") or None
        product_code = request.form.get("product_code", "").strip()
        description = request.form.get("description", "").strip()
        warranty = request.form.get("warranty", "").strip()
        try:
            price = float(request.form.get("price", 0))
        except ValueError:
            price = 0
        try:
            stock = int(request.form.get("stock", 100))
        except ValueError:
            stock = 100
        is_active = 1 if request.form.get("is_active") == "on" else 0

        image_filename = product["image_filename"]
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
            image_filename = unique_name

        db.execute(
            """UPDATE products SET name=?, category_id=?, product_code=?, description=?,
               price=?, warranty=?, stock=?, image_filename=?, is_active=? WHERE id=?""",
            (name, category_id, product_code, description, price, warranty, stock,
             image_filename, is_active, product_id),
        )
        db.commit()
        flash(f'"{name}" was updated.', "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html", categories=categories, product=product)


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@login_required
def admin_delete_product(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin_products"))


@app.route("/admin/categories", methods=["GET", "POST"])
@login_required
def admin_categories():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            try:
                db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                db.commit()
                flash(f'Category "{name}" added.', "success")
            except sqlite3.IntegrityError:
                flash("That category already exists.", "error")
        return redirect(url_for("admin_categories"))

    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("admin_categories.html", categories=categories)


if __name__ == "__main__":
    init_db()
    seed_db_if_empty()
    sync_lubricant_products()
    app.run(debug=True, host="0.0.0.0", port=5000)
