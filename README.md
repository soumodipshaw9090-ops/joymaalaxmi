# Joy Maa Laxmi Enterprises — Website

A website for the shop with two parts:

1. **Storefront** — customers browse batteries/lubricants/parts and place orders.
2. **Admin panel** — you log in, upload product photos + details, and see every order that comes in.

Built with Python (Flask) + HTML/CSS, storing everything in **MongoDB** (a database server), and ready to deploy on **Render.com**.

## 1. Install (one-time)

You need Python 3.9+ installed. Then, in this folder:

```bash
pip install -r requirements.txt
```

## 2. Set up MongoDB

The app needs a MongoDB connection string in the `MONGO_URI` environment variable. Two options:

**Option A — MongoDB Atlas (free, recommended, works from anywhere, no local install):**
1. Go to [mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register) and create a free account.
2. Create a free "M0" cluster.
3. Under **Database Access**, create a database user (username + password).
4. Under **Network Access**, add `0.0.0.0/0` (allow access from anywhere) — simplest for a small shop site; Render's servers have changing IPs.
5. Click **Connect → Drivers**, copy the connection string. It looks like:
   `mongodb+srv://<username>:<password>@<cluster-url>/joymaalaxmi?retryWrites=true&w=majority`
6. Fill in your username/password and use that as `MONGO_URI`.

**Option B — MongoDB running on your own computer (for local testing only):**
Install MongoDB Community Server, run it, and use the default:
`mongodb://localhost:27017/joymaalaxmi`

Copy `.env.example` to `.env` and fill in your real `MONGO_URI` (and the other values) for local development:

```bash
cp .env.example .env
```

## 3. Run the website locally

```bash
python3 app.py
```

You'll see `Running on http://127.0.0.1:5000`. Open that link in your browser — that's your website.

- The first time it connects to an empty database, it automatically fills it with SF Batteries price lists (vehicular & 2-wheeler batteries as of 10 June 2026, and inverter batteries & home UPS/inverters as of 1 July 2026) as sample products, sorted into categories: "Vehicular Batteries", "2-Wheeler Batteries", "Inverter Batteries", "Inverters (PowerSmart)", plus empty "Lubricants & Oils" and "Auto Parts" categories ready for you to fill in via the admin panel.

To make the site visible to other devices on your shop's Wi-Fi (e.g. to test on your phone), visit `http://<your-computer's-local-IP>:5000` instead of `127.0.0.1`.

## 4. Log into the admin panel

Go to `http://127.0.0.1:5000/admin/login`

- **Username:** `admin`
- **Password:** `changeme123`

**Change this password before you put the site online.** Set it via the `ADMIN_USERNAME` / `ADMIN_PASSWORD` environment variables (in `.env` locally, or in Render's dashboard once deployed — see below).

## 5. Using the admin panel

- **Dashboard** — quick summary: total orders, new orders, active products.
- **Products** — click **+ Add product** to upload a photo, name, price, warranty, description, and stock. Click **Edit** on any product to change it or swap the photo, and untick "Visible on site" to hide it without deleting it.
- **Categories** — add new categories (e.g. "Engine Oils", "2W Lubricants") so products can be grouped and filtered on the site.
- **Orders** — every order a customer places shows up here immediately with their name, phone, address, items and any notes. Use the status dropdown to mark it New → Confirmed → Delivered. **When you mark an order "Delivered", the ordered quantity is automatically subtracted from that product's stock** — you don't need to update stock by hand. If you pick "Delivered" by mistake and switch it back, the stock is added back automatically too.

Uploaded photos are stored in `static/uploads/` (see the note about this under Render deployment — it doesn't survive redeploys on Render's free tier).

## 6. How customers order

A customer opens a product, clicks **Order this item**, fills in their name/phone/address, and submits. There's no payment step — the order lands in your **Orders** page and you call them to confirm, exactly like a phone order. (Online payment can be added later if you want it — see below.)

## 7. Deploying to Render.com

Render will run your Flask app on a real web address, reachable from anywhere, using `gunicorn` as the production server (instead of `python3 app.py`, which is just for testing on your own machine).

**Steps:**

1. Push this project to a GitHub (or GitLab) repository.
2. Set up a MongoDB Atlas cluster if you haven't already (see step 2 above) — Render doesn't provide MongoDB itself, so you connect to Atlas.
3. In the [Render dashboard](https://dashboard.render.com), click **New → Web Service** and connect your repository.
   - Render will detect the included `render.yaml` and pre-fill most settings (this repo includes one, so you can also use **New → Blueprint** instead for a fully guided setup).
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app`
   - **Runtime:** Python 3
4. Under **Environment**, add these environment variables:
   - `MONGO_URI` — your MongoDB Atlas connection string from step 2.
   - `SECRET_KEY` — any long random string (Render can auto-generate this if you use the `render.yaml` blueprint).
   - `ADMIN_USERNAME` — your chosen admin username.
   - `ADMIN_PASSWORD` — a strong password.
5. Click **Create Web Service**. Render will build and deploy — you'll get a URL like `https://joymaalaxmi-website.onrender.com`.
6. Once it's live, you can point your own domain (e.g. `joymaalaxmiuttarpara.com`) at it from Render's **Settings → Custom Domains**.

**A note on product photos:** Render's free/starter web services use an *ephemeral* filesystem — anything written to `static/uploads/` (like product photos you upload through the admin panel) is lost whenever the service restarts or redeploys. For a production shop site, the reliable fix is to store uploaded photos in an external service (e.g. Cloudinary's free tier, or an S3-compatible bucket) instead of the local disk, or to add a paid Render "Disk" for persistent storage. I'm happy to wire this up if you'd like — just let me know.

## 8. Optional next steps I can add

- Persistent photo storage (Cloudinary/S3) so uploads survive redeploys on Render.
- Email or WhatsApp notification to you automatically when a new order comes in (right now you check the Orders page).
- Online payment (UPI/Razorpay) instead of pay-on-confirmation.
- Multiple product photos per item, and customer reviews.
- A proper domain name + HTTPS once it's hosted (Render provides free HTTPS automatically).

## Project structure

```
app.py                    Flask app: all routes (storefront + admin), MongoDB via PyMongo
requirements.txt          Python dependencies
Procfile                  Tells Render/gunicorn how to start the app
render.yaml                Render "Blueprint" config (service + env vars)
.env.example               Template for local environment variables (copy to .env)
templates/                 HTML pages
static/css/style.css       All styling
static/uploads/            Product photos you upload via admin (ephemeral on Render free tier — see above)
```
