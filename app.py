
import os
from datetime import datetime
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-development-secret")

DATABASE_URL = os.getenv("DATABASE_URL")


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/report", methods=["GET", "POST"])
def report_incident():
    if request.method == "POST":
        required = [
            "reporter_name",
            "phone",
            "location",
            "incident_type",
            "description"
        ]

        data = {
            key: request.form.get(key, "").strip()
            for key in required
        }

        if any(not value for value in data.values()):
            flash("Please complete all required fields.", "error")
            return render_template("report.html", data=data)

        try:
            with psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO incidents
                        (reporter_name, phone, location,
                         incident_type, description, status)
                        VALUES (%s, %s, %s, %s, %s, 'Pending')
                        RETURNING id
                    """, tuple(data[k] for k in required))

                    incident_id = cur.fetchone()["id"]

            flash(
                f"Report submitted successfully. Reference number: FIR-{incident_id:05d}",
                "success"
            )

            return redirect(url_for("report_incident"))

        except Exception:
            app.logger.exception("Incident submission failed")
            flash("Unable to submit your report. Please try again.", "error")

    return render_template("report.html", data={})




@app.route("/login", methods=["GET", "POST"])

def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            with psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, username, password_hash, role
                        FROM users
                        WHERE username = %s
                    """, (username,))

                    user = cur.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session.update(
                    user_id=user["id"],
                    username=user["username"],
                    role=user["role"]
                )
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "error")

        except Exception:
            app.logger.exception("Login database error")
            flash("Unable to log in right now. Please try again.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required(role="admin")

def dashboard():
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT COUNT(*) AS total FROM incidents")
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT status, COUNT(*) AS amount
                FROM incidents
                GROUP BY status
            """)
            status_counts = cur.fetchall()

            cur.execute("""
                SELECT *
                FROM incidents
                ORDER BY created_at DESC
                LIMIT 100
            """)
            incidents = cur.fetchall()

    return render_template(
        "dashboard.html",
        total=total,
        status_counts=status_counts,
        incidents=incidents
    )


@app.route("/incident/<int:incident_id>", methods=["GET", "POST"])

@login_required(role="admin")
def incident_detail(incident_id):
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT * FROM incidents WHERE id=%s",
                (incident_id,)
            )
            incident = cur.fetchone()

            if not incident:
                abort(404)

            if request.method == "POST":
                action = request.form.get("action", "")

                # Administrator updates incident status
                if action == "status":
                    status = request.form.get("status", "")
                    allowed = {
                        "Pending", "Under Review", "Assigned",
                        "Resolved", "Closed"
                    }

                    if status not in allowed:
                        abort(400)

                    cur.execute("""
                        UPDATE incidents
                        SET status=%s, updated_at=%s
                        WHERE id=%s
                    """, (status, datetime.utcnow(), incident_id))

                    flash("Incident status updated.", "success")

                # Administrator assigns a response team
                elif action == "assign":
                    team_id = request.form.get("team_id", type=int)
                    notes = request.form.get(
                        "assignment_notes", ""
                    ).strip()

                    if not team_id:
                        flash("Please select a response team.", "error")
                        return redirect(url_for(
                            "incident_detail",
                            incident_id=incident_id
                        ))

                    cur.execute("""
                        SELECT id, team_name, status
                        FROM response_teams
                        WHERE id=%s AND status='Active'
                    """, (team_id,))

                    team = cur.fetchone()

                    if not team:
                        flash(
                            "Selected response team is not active.",
                            "error"
                        )
                        return redirect(url_for(
                            "incident_detail",
                            incident_id=incident_id
                        ))

                    cur.execute("""
                        SELECT COUNT(*) AS total
                        FROM team_members tm
                        JOIN firefighters f
                            ON f.id = tm.firefighter_id
                        WHERE tm.team_id=%s
                    """, (team_id,))

                    member_count = cur.fetchone()["total"]

                    if member_count == 0:
                        flash(
                            "This team has no registered firefighters.",
                            "error"
                        )
                        return redirect(url_for(
                            "incident_detail",
                            incident_id=incident_id
                        ))

                    cur.execute("""
                        INSERT INTO incident_assignments
                        (incident_id, team_id, assigned_by,
                         assignment_notes)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        incident_id,
                        team_id,
                        session["user_id"],
                        notes
                    ))

                    cur.execute("""
                        UPDATE incidents
                        SET status='Assigned', updated_at=%s
                        WHERE id=%s
                    """, (datetime.utcnow(), incident_id))

                    flash(
                        f"Response team {team['team_name']} assigned successfully.",
                        "success"
                    )

                else:
                    abort(400)

                return redirect(url_for(
                    "incident_detail",
                    incident_id=incident_id
                ))

            # Get active response teams and firefighter counts
            cur.execute("""
                SELECT
                    rt.id,
                    rt.team_name,
                    rt.station,
                    COUNT(tm.firefighter_id) AS member_count
                FROM response_teams rt
                LEFT JOIN team_members tm ON tm.team_id = rt.id
                WHERE rt.status='Active'
                GROUP BY rt.id, rt.team_name, rt.station
                ORDER BY rt.team_name
            """)

            response_teams = cur.fetchall()

            # Get assignment history
            cur.execute("""
                SELECT
                    ia.id,
                    ia.assigned_at,
                    ia.assignment_notes,
                    rt.team_name,
                    rt.station,
                    u.username AS assigned_by_name
                FROM incident_assignments ia
                JOIN response_teams rt ON rt.id = ia.team_id
                JOIN users u ON u.id = ia.assigned_by
                WHERE ia.incident_id=%s
                ORDER BY ia.assigned_at DESC
            """, (incident_id,))

            assignments = cur.fetchall()

    return render_template(
        "incident_detail.html",
        incident=incident,
        response_teams=response_teams,
        assignments=assignments
    )

 

@app.route("/search")

@login_required(role="admin")
def search():
    term = request.args.get("q", "").strip()
    pattern = f"%{term}%"

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM incidents
                WHERE CAST(id AS TEXT) LIKE %s
                   OR reporter_name ILIKE %s
                   OR location ILIKE %s
                   OR incident_type ILIKE %s
                ORDER BY created_at DESC
                LIMIT 100
            """, (pattern, pattern, pattern, pattern))

            incidents = cur.fetchall()

    return render_template(
        "search.html",
        incidents=incidents,
        term=term
    )

@app.route("/reports")

@login_required(role="admin")
def reports():
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT incident_type, status, COUNT(*) AS total
                FROM incidents
                GROUP BY incident_type, status
                ORDER BY incident_type, status
            """)

            rows = cur.fetchall()

    return render_template("reports.html", rows=rows)



@app.route("/response-teams", methods=["GET", "POST"])

@login_required(role="admin")
def response_teams():
    if request.method == "POST":
        action = request.form.get("action", "create_team")

        try:
            with psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:

                    # CREATE A RESPONSE TEAM
                    if action == "create_team":
                        team_name = request.form.get(
                            "team_name", ""
                        ).strip()
                        station = request.form.get(
                            "station", ""
                        ).strip()

                        if not team_name or not station:
                            flash(
                                "Please complete all required fields.",
                                "error"
                            )
                        else:
                            cur.execute("""
                                INSERT INTO response_teams
                                (team_name, station, status)
                                VALUES (%s, %s, 'Active')
                            """, (team_name, station))

                            flash(
                                "Response team created successfully.",
                                "success"
                            )

                    # ADD A FIREFIGHTER TO A TEAM
                    elif action == "add_member":
                        team_id = request.form.get(
                            "team_id", type=int
                        )
                        firefighter_id = request.form.get(
                            "firefighter_id", type=int
                        )

                        if not team_id or not firefighter_id:
                            flash(
                                "Please select a team and firefighter.",
                                "error"
                            )
                        else:
                            # Confirm active team
                            cur.execute("""
                                SELECT id
                                FROM response_teams
                                WHERE id=%s AND status='Active'
                            """, (team_id,))

                            team = cur.fetchone()

                            if not team:
                                flash(
                                    "Selected response team is not active.",
                                    "error"
                                )
                            else:
                                # Confirm firefighter availability
                                cur.execute("""
                                    SELECT id
                                    FROM firefighters
                                    WHERE id=%s
                                    AND availability='Available'
                                """, (firefighter_id,))

                                firefighter = cur.fetchone()

                                if not firefighter:
                                    flash(
                                        "Selected firefighter is not available.",
                                        "error"
                                    )
                                else:
                                    # Prevent multiple team memberships
                                    cur.execute("""
                                        SELECT id
                                        FROM team_members
                                        WHERE firefighter_id=%s
                                    """, (firefighter_id,))

                                    if cur.fetchone():
                                        flash(
                                            "This firefighter already belongs to a response team.",
                                            "error"
                                        )
                                    else:
                                        cur.execute("""
                                            INSERT INTO team_members
                                            (team_id, firefighter_id)
                                            VALUES (%s, %s)
                                        """, (
                                            team_id,
                                            firefighter_id
                                        ))

                                        flash(
                                            "Firefighter successfully added to the response team.",
                                            "success"
                                        )

                    else:
                        abort(400)

        except psycopg.errors.UniqueViolation:
            flash(
                "This record already exists. Check the team name or firefighter assignment.",
                "error"
            )

        except Exception:
            app.logger.exception("Response team operation failed")
            flash(
                "Unable to complete the operation. Please try again.",
                "error"
            )

        return redirect(url_for("response_teams"))

    # GET ALL RESPONSE TEAMS
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    rt.id,
                    rt.team_name,
                    rt.station,
                    rt.status,
                    COUNT(tm.firefighter_id) AS member_count
                FROM response_teams rt
                LEFT JOIN team_members tm
                    ON tm.team_id = rt.id
                GROUP BY
                    rt.id, rt.team_name, rt.station, rt.status
                ORDER BY rt.team_name
            """)

            teams = cur.fetchall()

            # GET AVAILABLE FIREFIGHTERS WITHOUT A TEAM
            cur.execute("""
                SELECT
                    f.id,
                    f.full_name,
                    f.firefighter_rank,
                    f.station,
                    f.availability
                FROM firefighters f
                WHERE f.availability='Available'
                AND NOT EXISTS (
                    SELECT 1
                    FROM team_members tm
                    WHERE tm.firefighter_id=f.id
                )
                ORDER BY f.full_name
            """)

            unassigned_firefighters = cur.fetchall()

    return render_template(
        "response_teams.html",
        teams=teams,
        unassigned_firefighters=unassigned_firefighters
    )



@app.route("/firefighters", methods=["GET", "POST"])

@login_required(role="admin")
def firefighters():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        firefighter_rank = request.form.get(
            "firefighter_rank", ""
        ).strip()
        station = request.form.get("station", "").strip()

        if not all([
            username, password, full_name,
            phone, firefighter_rank, station
        ]):
            flash("Please complete all required fields.", "error")
            return redirect(url_for("firefighters"))

        if len(password) < 10:
            flash(
                "Password must contain at least 10 characters.",
                "error"
            )
            return redirect(url_for("firefighters"))

        try:
            password_hash = generate_password_hash(password)

            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:

                    cur.execute("""
                        INSERT INTO users
                        (username, password_hash, role)
                        VALUES (%s, %s, 'firefighter')
                        RETURNING id
                    """, (username, password_hash))

                    user_id = cur.fetchone()[0]

                    cur.execute("""
                        INSERT INTO firefighters
                        (user_id, full_name, phone,
                         firefighter_rank, station)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        full_name,
                        phone,
                        firefighter_rank,
                        station
                    ))

            flash(
                "Firefighter registered successfully.",
                "success"
            )

        except psycopg.errors.UniqueViolation:
            flash(
                "Registration failed. The username or firefighter record already exists.",
                "error"
            )

        except Exception:
            app.logger.exception("Firefighter registration failed")
            flash(
                "Unable to register firefighter. Please try again.",
                "error"
            )

        return redirect(url_for("firefighters"))

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    f.id,
                    f.full_name,
                    f.phone,
                    f.firefighter_rank,
                    f.station,
                    f.availability,
                    u.username
                FROM firefighters f
                JOIN users u ON u.id = f.user_id
                ORDER BY f.full_name
            """)

            firefighter_list = cur.fetchall()

    return render_template(
        "firefighters.html",
        firefighters=firefighter_list
    )

      

@app.route("/dispatch", methods=["GET", "POST"])
@login_required(role="admin")
def dispatch():

    if request.method == "POST":
        incident_id = request.form.get("incident_id", type=int)
        team_id = request.form.get("team_id", type=int)
        notes = request.form.get("assignment_notes", "").strip()
        action = request.form.get("action", "dispatch")

        try:
            with psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:

                    # COMPLETE A RESCUE OPERATION
                    if action == "complete":

                        if not incident_id:
                            raise ValueError("Invalid incident selected.")

                        cur.execute("""
                            SELECT status
                            FROM incidents
                            WHERE id=%s
                        """, (incident_id,))

                        incident = cur.fetchone()

                        if not incident or incident["status"] != "Assigned":
                            raise ValueError(
                                "This incident has no active rescue operation."
                            )

                        cur.execute("""
                            SELECT team_id
                            FROM incident_assignments
                            WHERE incident_id=%s
                            ORDER BY assigned_at DESC
                            LIMIT 1
                        """, (incident_id,))

                        assignment = cur.fetchone()

                        if not assignment:
                            raise ValueError(
                                "No response team assignment was found."
                            )

                        assigned_team_id = assignment["team_id"]

                        cur.execute("""
                            UPDATE incidents
                            SET status='Resolved', updated_at=%s
                            WHERE id=%s
                        """, (datetime.utcnow(), incident_id))

                        cur.execute("""
                            SELECT COUNT(*) AS total
                            FROM incident_assignments ia
                            JOIN incidents i
                                ON i.id=ia.incident_id
                            WHERE ia.team_id=%s
                            AND ia.incident_id != %s
                            AND i.status='Assigned'
                        """, (assigned_team_id, incident_id))

                        other_active = cur.fetchone()["total"]

                        # Release firefighters if the team has no other active rescue
                        if other_active == 0:
                            cur.execute("""
                                UPDATE firefighters
                                SET availability='Available'
                                WHERE id IN (
                                    SELECT firefighter_id
                                    FROM team_members
                                    WHERE team_id=%s
                                )
                                AND availability='On Duty'
                            """, (assigned_team_id,))

                        flash(
                            "Rescue completed successfully. Incident marked as Resolved.",
                            "success"
                        )

                    # DISPATCH A RESPONSE TEAM
                    elif action == "dispatch":

                        if not incident_id or not team_id:
                            raise ValueError(
                                "Please select an incident and response team."
                            )

                        cur.execute("""
                            SELECT id, status
                            FROM incidents
                            WHERE id=%s
                        """, (incident_id,))

                        incident = cur.fetchone()

                        if not incident:
                            raise ValueError("Incident not found.")

                        if incident["status"] in ("Resolved", "Closed"):
                            raise ValueError(
                                "This incident is already closed or resolved."
                            )

                        cur.execute("""
                            SELECT id
                            FROM incident_assignments
                            WHERE incident_id=%s
                        """, (incident_id,))

                        if cur.fetchone():
                            raise ValueError(
                                "This incident already has a response team assigned."
                            )

                        cur.execute("""
                            SELECT id, team_name
                            FROM response_teams
                            WHERE id=%s AND status='Active'
                        """, (team_id,))

                        team = cur.fetchone()

                        if not team:
                            raise ValueError(
                                "Selected response team is not active."
                            )

                        cur.execute("""
                            SELECT f.id
                            FROM firefighters f
                            JOIN team_members tm
                                ON tm.firefighter_id=f.id
                            WHERE tm.team_id=%s
                            AND f.availability='Available'
                        """, (team_id,))

                        available_members = cur.fetchall()

                        if not available_members:
                            raise ValueError(
                                "This team has no available firefighters."
                            )

                        # Record assignment
                        cur.execute("""
                            INSERT INTO incident_assignments
                            (incident_id, team_id, assigned_by, assignment_notes)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            incident_id,
                            team_id,
                            session["user_id"],
                            notes
                        ))

                        # Mark available team members as on duty
                        cur.execute("""
                            UPDATE firefighters
                            SET availability='On Duty'
                            WHERE id IN (
                                SELECT firefighter_id
                                FROM team_members
                                WHERE team_id=%s
                            )
                            AND availability='Available'
                        """, (team_id,))

                        # Update incident status
                        cur.execute("""
                            UPDATE incidents
                            SET status='Assigned', updated_at=%s
                            WHERE id=%s
                        """, (datetime.utcnow(), incident_id))

                        flash(
                            f"{team['team_name']} successfully dispatched.",
                            "success"
                        )

                    else:
                        abort(400)

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            app.logger.exception("Dispatch operation failed")
            flash(
                "Dispatch failed. Please check your database and try again.",
                "error"
            )

        return redirect(url_for("dispatch"))

    # DISPLAY DISPATCH INFORMATION
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:

            # Count unassigned incidents
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM incidents i
                WHERE i.status NOT IN ('Resolved', 'Closed')
                AND NOT EXISTS (
                    SELECT 1
                    FROM incident_assignments ia
                    WHERE ia.incident_id=i.id
                )
            """)

            unassigned_count = cur.fetchone()["total"]

            # Count active assigned incidents
            cur.execute("""
                SELECT COUNT(DISTINCT ia.incident_id) AS total
                FROM incident_assignments ia
                JOIN incidents i
                    ON i.id=ia.incident_id
                WHERE i.status='Assigned'
            """)

            active_count = cur.fetchone()["total"]

            # Count available response teams
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM response_teams rt
                WHERE rt.status='Active'
                AND EXISTS (
                    SELECT 1
                    FROM team_members tm
                    JOIN firefighters f
                        ON f.id=tm.firefighter_id
                    WHERE tm.team_id=rt.id
                    AND f.availability='Available'
                )
            """)

            available_count = cur.fetchone()["total"]

            # Get incidents and their latest assignment
            cur.execute("""
                SELECT
                    i.*,
                    rt.team_name,
                    rt.station AS team_station
                FROM incidents i
                LEFT JOIN incident_assignments ia
                    ON ia.id = (
                        SELECT MAX(ia2.id)
                        FROM incident_assignments ia2
                        WHERE ia2.incident_id=i.id
                    )
                LEFT JOIN response_teams rt
                    ON rt.id=ia.team_id
                ORDER BY
                    CASE
                        WHEN i.status='Pending' THEN 1
                        WHEN i.status='Under Review' THEN 2
                        WHEN i.status='Assigned' THEN 3
                        ELSE 4
                    END,
                    i.created_at DESC
            """)

            incidents = cur.fetchall()

            # Get active teams with available firefighters
            cur.execute("""
                SELECT
                    rt.id,
                    rt.team_name,
                    rt.station,
                    COUNT(
                        CASE
                            WHEN f.availability='Available' THEN f.id
                        END
                    ) AS available_members,
                    COUNT(f.id) AS total_members
                FROM response_teams rt
                LEFT JOIN team_members tm
                    ON tm.team_id=rt.id
                LEFT JOIN firefighters f
                    ON f.id=tm.firefighter_id
                WHERE rt.status='Active'
                GROUP BY rt.id, rt.team_name, rt.station
                HAVING COUNT(
                    CASE
                        WHEN f.availability='Available' THEN f.id
                    END
                ) > 0
                ORDER BY rt.team_name
            """)

            available_teams = cur.fetchall()

    return render_template(
        "dispatch.html",
        incidents=incidents,
        available_teams=available_teams,
        unassigned_count=unassigned_count,
        active_count=active_count,
        available_count=available_count,
        critical_count=0
    )



if __name__ == "__main__":
    app.run(debug=True) 