 DriveX - Premium Car Rental Platform
A full-stack car rental application built with **Python (Flask)**. 
Features include e-KYC verification (Webcam/Upload), Admin Dashboard, PDF Invoicing, Booking System with Coupons, and Role-Based Access Control.

## 🚀 Features
* **User Authentication:** Secure Login & Registration.
* **e-KYC System:** Users must upload ID and take a live selfie before booking.
* **Booking Engine:** * Date calculation.
    * Chauffeur service option (+₹500).
    * Coupon code system (e.g., `WELCOME20`).
* **Admin Dashboard:**
    * View real-time revenue and fleet stats.
    * Approve/Reject KYC documents.
    * Add/Delete Cars.
    * Manage active bookings.
* **Invoicing:** Auto-generated receipt pages for every booking.
* **Hybrid Database:** Works on SQLite (Local) and PostgreSQL (Cloud/Render).



## 🛠️ How to Run Locally (Visual Studio Code)

Follow these steps to run the website on your own computer.

### **Step 1: Prerequisites**
Make sure you have [Python](https://www.python.org/downloads/) installed.

### **Step 2: Install Dependencies**
Open your terminal in the project folder and run:

```bash
pip install flask flask-sqlalchemy flask-login psycopg2-binary

Step 3: Run the Application
Start the server by running:
python app.py

You should see: Running on http://127.0.0.1:5000
Step 4: Initialize the Database (First Time Only)
 * Open your browser and visit:
   http://127.0.0.1:5000/reset-db
   (This creates the drivex.db file and sets up the Admin user).
 * Now go to the home page:
   http://127.0.0.1:5000
🔑 Login Credentials
The system comes with a pre-configured Admin account after you run /reset-db.
| Role | Email | Password |
|---|---|---|
| Admin | admin@drivex.com | admin123 |
| User | (Register a new account) | (Your choice) |
💳 Test Coupons
Use these codes during checkout to test discounts:
 * WELCOME20 (₹200 OFF)
📂 Project Structure
 * app.py - Main backend logic (Routes, Models, Config).
 * templates/ - HTML files (Frontend).
   * admin.html - Dashboard for staff.
   * kyc.html - Identity verification page.
   * index.html - Home page.
 * static/ - CSS and images.
 * drivex.db - Local database file (created automatically).
☁️ Deployment (Render.com)
This project is configured to run on Render.
 * Push code to GitHub.
 * Create a Web Service on Render.
 * Add Environment Variable: DATABASE_URL (Internal Postgres URL).
 * Render detects app.py and runs it automatically.
<!-- end list -->

