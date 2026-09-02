import os
import re
import base64
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, Response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from bson.errors import InvalidId

# Load a local .env file if python-dotenv is installed (handy for local dev).
# On Render, environment variables are set in the dashboard instead, so this is a no-op there.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
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

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Dip")
# Default password is "changeme123" -- CHANGE THIS before going live (see README)
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    generate_password_hash(os.environ.get("ADMIN_PASSWORD", "Dip@123"))
)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def file_to_mongo_image(file):
    """Read an uploaded werkzeug FileStorage and return a dict ready to
    store directly inside a MongoDB product document (base64-encoded bytes
    plus the mimetype needed to serve it back out again)."""
    raw = file.read()
    ext = file.filename.rsplit(".", 1)[1].lower()
    mimetype = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "gif": "image/gif",
    }.get(ext, file.mimetype or "application/octet-stream")
    return {
        "image_data": base64.b64encode(raw).decode("ascii"),
        "image_mimetype": mimetype,
        "image_filename": secure_filename(file.filename),  # kept only for display/alt text
    }


def now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# MongoDB connection
# ---------------------------------------------------------------------------
# Locally this defaults to a MongoDB running on your own machine. In production
# (Render), set MONGO_URI to your MongoDB Atlas connection string as an
# environment variable -- see README for how to get one for free.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/joymaalaxmi")

mongo_client = MongoClient(MONGO_URI)
# get_default_database() picks up the database name from the URI's path
# (e.g. ".../joymaalaxmi"); fall back to a fixed name if the URI didn't include one.
try:
    db = mongo_client.get_default_database()
except Exception:
    db = None
if db is None:
    db = mongo_client["joymaalaxmi"]

categories_col = db["categories"]
products_col = db["products"]
orders_col = db["orders"]


def to_oid(id_str):
    """Convert a string id from a URL into an ObjectId, or 404 if it's not valid."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        abort(404)


def serialize(doc):
    """Add a plain string 'id' field (mirrors what the templates expect from the old SQLite rows)."""
    if doc is None:
        return None
    doc["id"] = str(doc["_id"])
    return doc


def serialize_many(docs):
    return [serialize(d) for d in docs]


# ---------------------------------------------------------------------------
# Database setup / seeding
# ---------------------------------------------------------------------------
def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    categories_col.create_index("name", unique=True)
    products_col.create_index("product_code")
    products_col.create_index("category_id")
    products_col.create_index([("created_at", DESCENDING)])
    orders_col.create_index([("created_at", DESCENDING)])


def seed_db_if_empty():
    """Seed with categories + the SF Batteries price list so the site isn't empty on first run."""
    if products_col.count_documents({}) > 0:
        return

    categories = [
        "Vehicular Batteries", "2-Wheeler Batteries", "Lubricants & Oils", "Auto Parts",
        "Inverter Batteries", "Inverters (PowerSmart)",
    ]
    cat_ids = {}
    for c in categories:
        existing = categories_col.find_one({"name": c})
        if existing:
            cat_ids[c] = str(existing["_id"])
        else:
            result = categories_col.insert_one({"name": c})
            cat_ids[c] = str(result.inserted_id)

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
        products_col.insert_one({
            "name": name,
            "category_id": cat_ids[cat],
            "product_code": code,
            "description": f"SF Batteries {name}. MRCP as on 10th June 2026.",
            "price": price,
            "warranty": warranty,
            "stock": 100,
            "image_filename": None,
            "is_active": True,
            "created_at": now_str(),
        })

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
        products_col.insert_one({
            "name": name,
            "category_id": cat_ids["Inverter Batteries"],
            "product_code": code,
            "description": f"{name}. MRCP inclusive of GST, effective 1st July 2026.",
            "price": price,
            "warranty": warranty,
            "stock": 100,
            "image_filename": None,
            "is_active": True,
            "created_at": now_str(),
        })

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
        products_col.insert_one({
            "name": name,
            "category_id": cat_ids["Inverters (PowerSmart)"],
            "product_code": code,
            "description": f"{name} — {ptype}. MRCP inclusive of GST, effective 1st July 2026.",
            "price": price,
            "warranty": warranty,
            "stock": 100,
            "image_filename": None,
            "is_active": True,
            "created_at": now_str(),
        })


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
    cat = categories_col.find_one({"name": "Lubricants & Oils"})
    if not cat:
        result = categories_col.insert_one({"name": "Lubricants & Oils"})
        cat_id = str(result.inserted_id)
    else:
        cat_id = str(cat["_id"])

    for code, name, pack, stock, price in SUNOIL_LUBRICANTS:
        if products_col.find_one({"product_code": code}):
            continue
        full_name = f"{name} {pack}"
        products_col.insert_one({
            "name": full_name,
            "category_id": cat_id,
            "product_code": code,
            "description": f"{full_name}. SUNOIL retail price list.",
            "price": price,
            "warranty": None,
            "stock": stock,
            "image_filename": None,
            "is_active": True,
            "created_at": now_str(),
        })


# Run setup once at import time so it also works when served by gunicorn
# (gunicorn imports this module directly, it never hits the __main__ block below).
init_db()
seed_db_if_empty()
sync_lubricant_products()


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
    categories = serialize_many(list(categories_col.find().sort("name", ASCENDING)))

    selected_cat = request.args.get("category") or None
    if selected_cat:
        try:
            ObjectId(selected_cat)
        except (InvalidId, TypeError):
            selected_cat = None
    q = request.args.get("q", "").strip()

    query = {"is_active": True}
    if selected_cat:
        query["category_id"] = selected_cat
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"name": pattern},
            {"product_code": pattern},
            {"description": pattern},
        ]
    products = serialize_many(list(products_col.find(query).sort("created_at", DESCENDING)))

    return render_template(
        "index.html",
        categories=categories,
        products=products,
        selected_cat=selected_cat,
        q=q,
    )


@app.route("/product/<product_id>")
def product_detail(product_id):
    oid = to_oid(product_id)
    product = serialize(products_col.find_one({"_id": oid, "is_active": True}))
    if not product:
        abort(404)
    related = serialize_many(list(
        products_col.find({
            "category_id": product["category_id"],
            "_id": {"$ne": oid},
            "is_active": True,
        }).limit(4)
    ))
    return render_template("product.html", product=product, related=related)


@app.route("/order/<product_id>", methods=["GET", "POST"])
def order_product(product_id):
    oid = to_oid(product_id)
    product = serialize(products_col.find_one({"_id": oid, "is_active": True}))
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

        order_doc = {
            "customer_name": name,
            "phone": phone,
            "email": email,
            "address": address,
            "notes": notes,
            "status": "New",
            "stock_deducted": False,
            "created_at": now_str(),
            "items": [{
                "product_id": str(product["_id"]),
                "product_name": product["name"],
                "quantity": qty,
                "price_each": product["price"],
            }],
        }
        result = orders_col.insert_one(order_doc)
        return redirect(url_for("order_success", order_id=str(result.inserted_id)))

    return render_template("order_form.html", product=product)


@app.route("/order-success/<order_id>")
def order_success(order_id):
    oid = to_oid(order_id)
    order = serialize(orders_col.find_one({"_id": oid}))
    if not order:
        abort(404)
    items = order.get("items", [])
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
    order_count = orders_col.count_documents({})
    new_count = orders_col.count_documents({"status": "New"})
    product_count = products_col.count_documents({"is_active": True})
    recent_orders = serialize_many(list(orders_col.find().sort("created_at", DESCENDING).limit(6)))
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
    orders = serialize_many(list(orders_col.find().sort("created_at", DESCENDING)))
    orders_with_items = [(o, o.get("items", [])) for o in orders]
    return render_template("admin_orders.html", orders_with_items=orders_with_items)


@app.route("/admin/orders/<order_id>/status", methods=["POST"])
@login_required
def admin_update_order_status(order_id):
    oid = to_oid(order_id)
    new_status = request.form.get("status", "New")
    order = orders_col.find_one({"_id": oid})
    if not order:
        abort(404)

    was_delivered = order["status"] == "Delivered" and order.get("stock_deducted")

    if new_status == "Delivered" and not was_delivered:
        # Moving into "Delivered": deduct each ordered item's quantity from that product's stock.
        for item in order.get("items", []):
            if item.get("product_id"):
                product = products_col.find_one({"_id": ObjectId(item["product_id"])})
                if product:
                    new_stock = max(0, product.get("stock", 0) - item["quantity"])
                    products_col.update_one(
                        {"_id": product["_id"]},
                        {"$set": {"stock": new_stock}},
                    )
        orders_col.update_one(
            {"_id": oid},
            {"$set": {"status": new_status, "stock_deducted": True}},
        )
        flash("Order marked Delivered — stock updated.", "success")
    elif new_status != "Delivered" and was_delivered:
        # Moving OUT of "Delivered" (e.g. correcting a mistake): put the stock back.
        for item in order.get("items", []):
            if item.get("product_id"):
                product = products_col.find_one({"_id": ObjectId(item["product_id"])})
                if product:
                    products_col.update_one(
                        {"_id": product["_id"]},
                        {"$set": {"stock": product.get("stock", 0) + item["quantity"]}},
                    )
        orders_col.update_one(
            {"_id": oid},
            {"$set": {"status": new_status, "stock_deducted": False}},
        )
        flash("Order status updated — stock restored.", "success")
    else:
        orders_col.update_one({"_id": oid}, {"$set": {"status": new_status}})
        flash("Order status updated.", "success")

    return redirect(url_for("admin_orders"))


@app.route("/admin/products")
@login_required
def admin_products():
    cat_map = {str(c["_id"]): c["name"] for c in categories_col.find()}
    products = serialize_many(list(products_col.find().sort("created_at", DESCENDING)))
    for p in products:
        p["category_name"] = cat_map.get(p.get("category_id"))
    return render_template("admin_products.html", products=products)


@app.route("/product-image/<product_id>")
def product_image(product_id):
    """Serve a product's photo straight out of MongoDB (no files on disk,
    so it survives Render restarts/redeploys)."""
    oid = to_oid(product_id)
    product = products_col.find_one(
        {"_id": oid}, {"image_data": 1, "image_mimetype": 1}
    )
    if not product or not product.get("image_data"):
        abort(404)
    raw = base64.b64decode(product["image_data"])
    resp = Response(raw, mimetype=product.get("image_mimetype", "image/jpeg"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/admin/products/new", methods=["GET", "POST"])
@login_required
def admin_add_product():
    categories = serialize_many(list(categories_col.find().sort("name", ASCENDING)))

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

        image_fields = {"image_data": None, "image_mimetype": None, "image_filename": None}
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            image_fields = file_to_mongo_image(file)

        if not name:
            flash("Product name is required.", "error")
            return render_template("admin_add_product.html", categories=categories, product=None)

        products_col.insert_one({
            "name": name,
            "category_id": category_id,
            "product_code": product_code,
            "description": description,
            "price": price,
            "warranty": warranty,
            "stock": stock,
            **image_fields,
            "is_active": True,
            "created_at": now_str(),
        })
        flash(f'"{name}" was added.', "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html", categories=categories, product=None)


@app.route("/admin/products/<product_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_product(product_id):
    oid = to_oid(product_id)
    categories = serialize_many(list(categories_col.find().sort("name", ASCENDING)))
    product = serialize(products_col.find_one({"_id": oid}))
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
        is_active = request.form.get("is_active") == "on"

        # Keep the existing stored image unless a new file was uploaded.
        image_fields = {
            "image_data": product.get("image_data"),
            "image_mimetype": product.get("image_mimetype"),
            "image_filename": product.get("image_filename"),
        }
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            image_fields = file_to_mongo_image(file)

        products_col.update_one(
            {"_id": oid},
            {"$set": {
                "name": name,
                "category_id": category_id,
                "product_code": product_code,
                "description": description,
                "price": price,
                "warranty": warranty,
                "stock": stock,
                **image_fields,
                "is_active": is_active,
            }},
        )
        flash(f'"{name}" was updated.', "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html", categories=categories, product=product)


@app.route("/admin/products/<product_id>/delete", methods=["POST"])
@login_required
def admin_delete_product(product_id):
    oid = to_oid(product_id)
    products_col.delete_one({"_id": oid})
    flash("Product deleted.", "success")
    return redirect(url_for("admin_products"))


@app.route("/admin/categories", methods=["GET", "POST"])
@login_required
def admin_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            try:
                categories_col.insert_one({"name": name})
                flash(f'Category "{name}" added.', "success")
            except DuplicateKeyError:
                flash("That category already exists.", "error")
        return redirect(url_for("admin_categories"))

    categories = serialize_many(list(categories_col.find().sort("name", ASCENDING)))
    return render_template("admin_categories.html", categories=categories)
    
@app.route('/google4f17c1193746bef8.html')
def google_verify():
   return"google-site-verification: google4f17c1193746bef8.html"

if __name__ == "__main__":
    # init_db() / seed_db_if_empty() / sync_lubricant_products() already ran at import time above.
    app.run(debug=True, host="0.0.0.0", port=5000)
