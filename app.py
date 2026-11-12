
from flask import Flask, render_template, request, jsonify
from pathlib import Path
from datetime import datetime
import sqlite3
import json
import uuid

from analysis import run_comparison, search_scenes

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DB = DATA_DIR / "satellite_intelligence.db"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                area_name TEXT,
                start_year INTEGER,
                end_year INTEGER,
                geometry TEXT,
                result_json TEXT,
                status TEXT
            )
        """)


@app.route("/")
def home():
    init_db()
    return render_template("index.html")


@app.get("/api/health")
def health():
    init_db()

    return jsonify({
        "status": "ok",
        "application": "Satellite Blind-Spot Intelligence",
        "database": DB.exists(),
        "satellite_catalogue": "Earth Search STAC",
        "sentinel_collection": "sentinel-2-l2a"
    })


@app.post("/api/scenes")
def scenes():
    try:
        body = request.get_json(silent=True) or {}

        if "geometry" not in body or "year" not in body:
            return jsonify({
                "error": "Geometry and year are required."
            }), 400

        result = search_scenes(
            body["geometry"],
            int(body["year"])
        )

        return jsonify(result)

    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        app.logger.exception("Scene search failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/analyze")
def analyze():
    try:
        body = request.get_json(silent=True) or {}

        required = ("geometry", "year1", "year2")

        for field in required:
            if field not in body:
                return jsonify({
                    "error": f"Missing required field: {field}"
                }), 400

        year1 = int(body["year1"])
        year2 = int(body["year2"])

        if year1 < 2017 or year2 > datetime.now().year or year1 >= year2:
            return jsonify({
                "error": "Choose increasing years between 2017 and the current year."
            }), 400

        geometry = body["geometry"]

        max_cloud = float(body.get("max_cloud", 30))

        if not 0 <= max_cloud <= 100:
            return jsonify({
                "error": "Cloud cover must be between 0 and 100."
            }), 400

        result = run_comparison(
            geometry,
            year1,
            year2,
            max_cloud
        )

        analysis_id = str(uuid.uuid4())[:8]

        result["analysis_id"] = analysis_id

        result["area_name"] = (
            body.get("area_name")
            or "Selected Satara study area"
        )

        init_db()

        with db() as con:
            con.execute(
                """
                INSERT INTO analyses
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    datetime.now().isoformat(timespec="seconds"),
                    result["area_name"],
                    year1,
                    year2,
                    json.dumps(geometry),
                    json.dumps(result),
                    result.get("status", "unknown")
                )
            )

        return jsonify(result)

    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        app.logger.exception("Satellite analysis failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/history")
def history():
    init_db()

    with db() as con:
        rows = con.execute("""
            SELECT id, created_at, area_name,
                   start_year, end_year, status
            FROM analyses
            ORDER BY created_at DESC
            LIMIT 30
        """).fetchall()

    return jsonify([dict(row) for row in rows])


@app.get("/api/report/<analysis_id>")
def report(analysis_id):
    init_db()

    with db() as con:
        row = con.execute(
            "SELECT result_json FROM analyses WHERE id = ?",
            (analysis_id,)
        ).fetchone()

    if not row:
        return jsonify({
            "error": "Report not found."
        }), 404

    result = json.loads(row["result_json"])

    return render_template(
        "report.html",
        r=result
    )


# Initialize database when the application starts.
init_db()


if __name__ == "__main__":
    print("\nSatellite Blind-Spot Intelligence")
    print("Open: http://127.0.0.1:5000\n")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
