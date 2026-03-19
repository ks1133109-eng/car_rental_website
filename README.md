# 🚗 DriveX: Premium Peer-to-Peer Car Rental SaaS Platform

**Live Demo:** [https://drivex.qzz.io](https://drivex.qzz.io)

DriveX is a full-stack, peer-to-peer car rental platform built with Python and Flask. It allows everyday users to rent vehicles, while empowering car owners to become "Partners" and list their own vehicles for passive income. 

The platform features robust role-based access control, e-KYC identity verification, secure online payments, and a comprehensive admin moderation dashboard.

---

## ✨ Key Features

### 🔒 Security & Authentication
* **e-KYC System:** Users must upload a Government ID and take a live webcam selfie before booking.
* **Two-Factor Authentication (2FA):** Optional enhanced security via Authenticator apps (PyOTP/QR code).
* **Role-Based Access Control:** Distinct roles and dashboards for Admins, Partners (Clients), and standard Users.

### 👨‍💼 Admin Dashboard (Platform Management)
* **Real-Time Analytics:** Track monthly revenue, fleet composition, and active bookings using interactive Chart.js graphs.
* **Global Offer System:** Create promotional banners that globally apply dynamic discounts at checkout.
* **Advanced Moderation:** Approve/Reject Partner vehicle listings, verify user KYC documents, and ban suspicious users.
* **Platform Control:** View global audit logs, manage active bookings, and generate discount coupons.

### 🤝 Partner Portal (Client Dashboard)
* **Dedicated Partner UI:** A specialized portal for car owners to track their personal fleet.
* **Seamless Vehicle Uploads:** List new cars using either image URLs or direct file uploads (Base64 conversion).
* **Fleet Management:** Edit vehicle details or remove cars from the platform (triggers automatic Admin re-approval for security).

### 🚘 Customer Experience (End Users)
* **Dynamic Fleet Filtering:** Filter available cars by location, category, seats, and date availability.
* **Smart Booking Engine:** Automatically calculates trip duration, daily rates, optional Chauffeur service (+₹500/day), delivery costs, tax, and applied discounts.
* **Invoicing:** Auto-generated PDF-style receipt pages for every booking.
* **Secure Payments:** Integrated with Razorpay for safe, seamless checkout.

---

## 🛠️ Tech Stack

* **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-Mail
* **Database:** PostgreSQL (Production/Render) & SQLite (Local Development)
* **Frontend:** HTML5, CSS3, Jinja2 Templates, JavaScript, Chart.js
* **Security:** Werkzeug Password Hashing, Flask-Talisman (CSP), Flask-Limiter, CSRF Protection
* **Integrations:** Razorpay API (Payments)

---

## 🚀 How to Run Locally (Visual Studio Code)

Follow these steps to run the website on your own computer.

### Step 1: Prerequisites
Make sure you have [Python](https://www.python.org/downloads/) installed. Clone the repository:
```bash
git clone [https://github.com/YOUR-GITHUB-USERNAME/car_rental_website.git](https://github.com/YOUR-GITHUB-USERNAME/car_rental_website.git)
cd car_rental_website

```

### Step 2: Set up a Virtual Environment

```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Mac/Linux:
source .venv/bin/activate



### Step 3: Install Dependencies

bash
pip install -r requirements.txt



### Step 4: Configure Environment Variables

Set the following environment variables in your terminal (or use a `.env` file):

```bash
# Example for Windows PowerShell:
$env:SECRET_KEY="your_secret_key_here"
$env:DATABASE_URL="postgresql://username:password@localhost:5432/drivex_db" # Optional: Leave blank to use SQLite
$env:RAZORPAY_KEY_ID="your_razorpay_key"
$env:RAZORPAY_KEY_SECRET="your_razorpay_secret"

```

### Step 5: Initialize the Database & Run

Start the server:

```bash
python app.py

```

**First Time Only:** Open your browser and visit `http://127.0.0.1:5000/reset-db`. This will build the database tables and inject the default Admin user and vehicles.

Now go to the home page: **`http://127.0.0.1:5000`**



### 💳 Test Coupons

Use these codes during checkout to test the discount logic:

* `WELCOME20` (₹500 OFF)
* `SUMMER10` (₹200 OFF)

---

## 📂 Project Structure

* `app.py` - Main backend logic (Routes, Models, Config).
* `requirements.txt` - Python dependencies.
* `templates/` - HTML UI files (Jinja2).
* `base.html` - Master layout & navbar.
* `admin.html` - Analytics dashboard for staff.
* `client_dashboard.html` - Partner portal for car owners.
* `kyc.html` - Identity verification page.


* `static/` - CSS stylesheets and static assets.



## ☁️ Deployment (Render.com)

This project is fully configured to run on Render with a PostgreSQL database.

1. Push your final code to GitHub.
2. Log into Render and create a new **PostgreSQL Database**.
3. Create a new **Web Service** and connect your GitHub repository.
4. Add the following Environment Variables in Render:
* `DATABASE_URL` (Use the Internal Postgres URL provided by Render)
* `PYTHON_VERSION` (e.g., `3.10.0`)
* `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`


5. Render will automatically detect `app.py`, install `requirements.txt`, and deploy the app!
6. Visit `https://your-app.onrender.com/reset-db` once to initialize the live database.

## 📄 License

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).

