# Fire Incident Reporting and Response Management System

Academic prototype for structured fire incident reporting and administrative record management. It does not dispatch emergency services and is not connected to the Federal Fire Service.

## Features

- Public incident submission form
- Server-side required-field validation
- Generated incident reference number
- Administrator login with hashed passwords
- Admin dashboard and incident list
- Incident status updates
- Search and summary reports
- Response team management
- Firefighter management
- Incident tracking

## Requirements

- Python 3.13+
- PostgreSQL database
- A web browser

## Local Setup (Windows PowerShell)

1. Install Python 3.13.
2. Open the project folder in VS Code or PowerShell.
3. Create and activate a virtual environment:

   ```powershell
   py -3.13 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Create a PostgreSQL database and execute the PostgreSQL database schema.

6. Create a `.env` file in the project root with:

   ```env
   SECRET_KEY=your-secure-secret-key
   DATABASE_URL=your-postgresql-connection-string
   ```

7. Create the administrator account:

   ```powershell
   python create_admin.py
   ```

8. Start the application:

   ```powershell
   python app.py
   ```

9. Open `http://127.0.0.1:5000` in your browser.

## Deployment

The application can be deployed using Render with a PostgreSQL database hosted on Neon. Configure `DATABASE_URL` and `SECRET_KEY` in the hosting provider's environment variables.

## Important

- Keep secret keys and database credentials private.
- Do not upload your `.env` file to GitHub.
- Do not enter real victims' personal information into this academic prototype.
- Before real-world deployment, add CSRF protection, rate limiting, secure cookie settings, HTTPS, audit logging, backups, stronger input controls and an authorized operational review.
- Emergency reporting must continue through official emergency channels.