# Joy Maa Laxmi Enterprises — Website

A website for the shop with two parts:

1. **Storefront** — customers browse batteries/lubricants/parts and place orders.
2. **Admin panel** — you log in, upload product photos + details, and see every order that comes in.

Built with Python (Flask) + HTML/CSS, using a small SQLite database file (`shop.db`) — no separate database server needed.

## 1. Install (one-time)

You need Python 3.9+ installed. Then, in this folder:

```bash
pip install -r requirements.txt
```

## 2. Run the website

```bash
python3 app.py
```

You'll see `Running on http://127.0.0.1:5000`. Open that link in your browser — that's your website.

- The first time you run it, it automatically creates `shop.db` and fills it with SF Batteries price lists (vehicular & 2-wheeler batteries as of 10 June 2026, and inverter batteries & home UPS/inverters as of 1 July 2026) as sample products, sorted into categories: "Vehicular Batteries", "2-Wheeler Batteries", "Inverter Batteries", "Inverters (PowerSmart)", plus empty "Lubricants & Oils" and "Auto Parts" categories ready for you to fill in via the admin panel.

To make the site visible to other devices on your shop's Wi-Fi (e.g. to test on your phone), visit `http://<your-computer's-local-IP>:5000` instead of `127.0.0.1`.

## 3. Log into the admin panel

Go to `http://127.0.0.1:5000/admin/login`

- **Username:** `admin`
- **Password:** `changeme123`

**Change this password before you put the site online.** Easiest way: set an environment variable before starting the app:

```bash
export ADMIN_USERNAME="youradminname"
export ADMIN_PASSWORD="a-strong-password-here"
python3 app.py
```
(On Windows, use `set` instead of `export`.)

## 4. Using the admin panel

- **Dashboard** — quick summary: total orders, new orders, active products.
- **Products** — click **+ Add product** to upload a photo, name, price, warranty, description, and stock. Click **Edit** on any product to change it or swap the photo, and untick "Visible on site" to hide it without deleting it.
- **Categories** — add new categories (e.g. "Engine Oils", "2W Lubricants") so products can be grouped and filtered on the site.
- **Orders** — every order a customer places shows up here immediately with their name, phone, address, items and any notes. Use the status dropdown to mark it New → Confirmed → Delivered. **When you mark an order "Delivered", the ordered quantity is automatically subtracted from that product's stock** — you don't need to update stock by hand. If you pick "Delivered" by mistake and switch it back, the stock is added back automatically too.

Uploaded photos are stored in `static/uploads/`.

## 5. How customers order

A customer opens a product, clicks **Order this item**, fills in their name/phone/address, and submits. There's no payment step — the order lands in your **Orders** page and you call them to confirm, exactly like a phone order. (Online payment can be added later if you want it — see below.)

## 6. Putting it online (so anyone can visit, not just your computer)

Right now this runs on your own computer only. To get a real web address (like `joymaalaxmiuttarpara.com`) reachable from anywhere, you deploy it to a hosting service. Two simple, inexpensive options:

- **PythonAnywhere** or **Render.com** — both have free/cheap tiers, support Flask directly, and have simple upload/deploy instructions.
- Ask whoever manages hosting to run `pip install -r requirements.txt` then serve `app.py` with a production server (e.g. `gunicorn app:app`) instead of the built-in `python3 app.py` (that one's just for testing on your own machine).

I'm happy to walk through deployment with you when you're ready — just let me know which host you'd like to use.

## 7. Optional next steps I can add

- Email or WhatsApp notification to you automatically when a new order comes in (right now you check the Orders page).
- Online payment (UPI/Razorpay) instead of pay-on-confirmation.
- Multiple product photos per item, and customer reviews.
- A proper domain name + HTTPS once it's hosted.

## Project structure

```
app.py                  Flask app: all routes (storefront + admin)
shop.db                  SQLite database (created automatically)
templates/                HTML pages
static/css/style.css      All styling
static/uploads/           Product photos you upload via admin
requirements.txt
```
