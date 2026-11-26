import json
import os
import threading
from datetime import date, datetime

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes

SWAGGER_URL = "/api/docs"  # Swagger UI endpoint, e.g. http://localhost:5002/api/docs
API_URL = "/static/masterblog.json"  # Served from backend/static/masterblog.json

swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': 'Masterblog API'}
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

DATE_FORMAT = "%Y-%m-%d"
DEFAULT_AUTHOR = "Anonymous"

# Posts are stored in a JSON file next to this script, so they survive restarts
POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")

# Used to create posts.json the first time the app runs
DEFAULT_POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post.",
     "author": "Hakan Samci", "date": "2023-06-07"},
    {"id": 2, "title": "Second post", "content": "This is the second post.",
     "author": "Jane Doe", "date": "2023-05-15"},
]

# Prevents two requests from writing the file at the same time
storage_lock = threading.Lock()


class StorageError(Exception):
    """Raised when posts.json cannot be read or written."""


def load_posts():
    """Read all posts from the JSON file. Creates the file if it doesn't exist."""
    if not os.path.exists(POSTS_FILE):
        save_posts(DEFAULT_POSTS)
        return [dict(post) for post in DEFAULT_POSTS]
    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as file:
            posts = json.load(file)
    except json.JSONDecodeError as error:
        raise StorageError(f"posts.json contains invalid JSON: {error}") from error
    except OSError as error:
        raise StorageError(f"Could not read posts.json: {error}") from error
    if not isinstance(posts, list):
        raise StorageError("posts.json must contain a JSON list of posts.")
    return posts


def save_posts(posts):
    """Write all posts to the JSON file (temp file + replace, so it never ends up half-written)."""
    temp_file = POSTS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(posts, file, indent=4, ensure_ascii=False)
        os.replace(temp_file, POSTS_FILE)
    except OSError as error:
        raise StorageError(f"Could not write posts.json: {error}") from error


@app.errorhandler(StorageError)
def handle_storage_error(error):
    return jsonify({"error": "Storage error.", "details": str(error)}), 500


REQUIRED_FIELDS = ("title", "content")
TEXT_FIELDS = ("title", "content", "author")
SEARCH_FIELDS = ("title", "content", "author", "date")
SORT_FIELDS = ("title", "content", "author", "date")
SORT_DIRECTIONS = ("asc", "desc")


def generate_post_id(posts):
    """Return a new unique integer ID (max existing ID + 1)."""
    return max((post["id"] for post in posts), default=0) + 1


def find_post_by_id(posts, post_id):
    """Return the post with the given id, or None if it doesn't exist."""
    return next((post for post in posts if post["id"] == post_id), None)


def parse_date(value):
    """Convert a 'YYYY-MM-DD' string to a date object. Raises ValueError if invalid."""
    if not isinstance(value, str):
        raise ValueError("Date must be a string.")
    return datetime.strptime(value.strip(), DATE_FORMAT).date()


def date_error(value):
    return jsonify({
        "error": f"Invalid date '{value}'. Expected format: YYYY-MM-DD."
    }), 400


def sort_key(field):
    """Return a key function: real dates for 'date', case-insensitive text otherwise."""
    if field == "date":
        return lambda post: parse_date(post["date"])
    return lambda post: post[field].lower()


@app.route('/api/posts', methods=['GET'])
def get_posts():
    sort_field = request.args.get('sort')
    direction = request.args.get('direction')

    if sort_field is not None and sort_field not in SORT_FIELDS:
        return jsonify({
            "error": f"Invalid sort field '{sort_field}'. "
                     f"Allowed values: {', '.join(SORT_FIELDS)}."
        }), 400

    if direction is not None and direction not in SORT_DIRECTIONS:
        return jsonify({
            "error": f"Invalid sort direction '{direction}'. "
                     f"Allowed values: {', '.join(SORT_DIRECTIONS)}."
        }), 400

    posts = load_posts()

    # No sort field: keep the original order
    if sort_field is None:
        return jsonify(posts)

    sorted_posts = sorted(posts, key=sort_key(sort_field),
                          reverse=(direction == "desc"))
    return jsonify(sorted_posts)


@app.route('/api/posts', methods=['POST'])
def add_post():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    missing = [field for field in REQUIRED_FIELDS
               if not str(data.get(field) or "").strip()]
    if missing:
        return jsonify({
            "error": "Missing required fields.",
            "missing_fields": missing
        }), 400

    # Optional fields: author defaults to "Anonymous", date defaults to today
    author = str(data.get("author") or "").strip() or DEFAULT_AUTHOR
    raw_date = data.get("date")
    if raw_date in (None, ""):
        post_date = date.today()
    else:
        try:
            post_date = parse_date(raw_date)
        except ValueError:
            return date_error(raw_date)

    with storage_lock:
        posts = load_posts()
        new_post = {
            "id": generate_post_id(posts),
            "title": data["title"].strip(),
            "content": data["content"].strip(),
            "author": author,
            "date": post_date.strftime(DATE_FORMAT),
        }
        posts.append(new_post)
        save_posts(posts)
    return jsonify(new_post), 201


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    with storage_lock:
        posts = load_posts()
        post = find_post_by_id(posts, post_id)
        if post is None:
            return jsonify({"error": f"Post with id {post_id} was not found."}), 404

        posts.remove(post)
        save_posts(posts)
    return jsonify({
        "message": f"Post with id {post_id} has been deleted successfully."
    }), 200


@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_post(post_id):
    data = request.get_json(silent=True)
    if data is None:
        data = {}  # Empty body: keep current values
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    # Validate the date first, so nothing changes if it is invalid
    new_date = None
    raw_date = data.get("date")
    if raw_date not in (None, ""):
        try:
            new_date = parse_date(raw_date)
        except ValueError:
            return date_error(raw_date)

    with storage_lock:
        posts = load_posts()
        post = find_post_by_id(posts, post_id)
        if post is None:
            return jsonify({"error": f"Post with id {post_id} was not found."}), 404

        # Only overwrite fields that were provided with a non-empty value
        for field in TEXT_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                post[field] = value.strip()
        if new_date is not None:
            post["date"] = new_date.strftime(DATE_FORMAT)

        save_posts(posts)
    return jsonify(post), 200


@app.route('/api/posts/search', methods=['GET'])
def search_posts():
    # Field-specific terms, e.g. ?title=flask&author=hakan
    terms = {field: request.args.get(field, '').strip().lower()
             for field in SEARCH_FIELDS}
    terms = {field: term for field, term in terms.items() if term}

    # Generic term that matches any field, e.g. ?search=2023
    general_term = request.args.get('search', '').strip().lower()

    posts = load_posts()

    # No search terms given: return all posts
    if not terms and not general_term:
        return jsonify(posts)

    def matches(post):
        if any(term in str(post[field]).lower() for field, term in terms.items()):
            return True
        if general_term:
            return any(general_term in str(post[field]).lower()
                       for field in SEARCH_FIELDS)
        return False

    return jsonify([post for post in posts if matches(post)])


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, debug=True)