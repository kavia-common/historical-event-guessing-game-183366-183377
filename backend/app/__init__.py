from flask import Flask
from flask_cors import CORS
from flask_smorest import Api

# Load .env if present to ease local development (non-fatal if missing)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # dotenv is optional; ignore if not installed
    pass

# Flask app setup
app = Flask(__name__)
app.url_map.strict_slashes = False
CORS(app, resources={r"/*": {"origins": "*"}})

# OpenAPI/Swagger config
app.config["API_TITLE"] = "My Flask API"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.3"
app.config["OPENAPI_URL_PREFIX"] = "/docs"
app.config["OPENAPI_SWAGGER_UI_PATH"] = ""
app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

# Initialize API
api = Api(app)

# Initialize database (models import happens in init_db)
from .db import init_db  # noqa: E402

try:
    init_db()
except Exception as e:
    # Avoid crashing app startup in some environments; log instead.
    # Real deployment should ensure DB is reachable/configured.
    app.logger.error(f"Database initialization failed: {e}")

# Register blueprints
from .routes.health import blp as health_blp  # noqa: E402

api.register_blueprint(health_blp)

# Placeholder for future blueprints:
# from .routes.events import blp as events_blp
# api.register_blueprint(events_blp)
