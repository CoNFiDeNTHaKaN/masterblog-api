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

POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post.",
     "author": "Hakan Samci", "date": "2023-06-07"},
    {"id": 2, "title": "Second post", "content": "This is the second post.",
     "author": "Jane Doe", "date": "2023-05-15"},
]

REQUIRED_FIELDS = ("title", "content")
TEXT_FIELDS = ("title", "content", "author")
SEARCH_FIELDS = ("title", "content", "author", "date")
SORT_FIELDS = ("title", "content", "author", "date")
SORT_DIRECTIONS = ("asc", "desc")


def generate_post_id():
    """Return a new unique integer ID (max existing ID + 1)."""
    return max((post["id"] for post in POSTS), default=0) + 1


def find_post_by_id(post_id):
    """Return the post with the given id, or None if it doesn't exist."""
    return next((post for post in POSTS if post["id"] == post_id), None)


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

    # No sort field: keep the original order
    if sort_field is None:
        return jsonify(POSTS)

    sorted_posts = sorted(POSTS, key=sort_key(sort_field),
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

    new_post = {
        "id": generate_post_id(),
        "title": data["title"].strip(),
        "content": data["content"].strip(),
        "author": author,
        "date": post_date.strftime(DATE_FORMAT),
    }
    POSTS.append(new_post)
    return jsonify(new_post), 201


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    post = find_post_by_id(post_id)
    if post is None:
        return jsonify({"error": f"Post with id {post_id} was not found."}), 404

    POSTS.remove(post)
    return jsonify({
        "message": f"Post with id {post_id} has been deleted successfully."
    }), 200


@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_post(post_id):
    post = find_post_by_id(post_id)
    if post is None:
        return jsonify({"error": f"Post with id {post_id} was not found."}), 404

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

    # Only overwrite fields that were provided with a non-empty value
    for field in TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            post[field] = value.strip()
    if new_date is not None:
        post["date"] = new_date.strftime(DATE_FORMAT)

    return jsonify(post), 200


@app.route('/api/posts/search', methods=['GET'])
def search_posts():
    # Field-specific terms, e.g. ?title=flask&author=hakan
    terms = {field: request.args.get(field, '').strip().lower()
             for field in SEARCH_FIELDS}
    terms = {field: term for field, term in terms.items() if term}

    # Generic term that matches any field, e.g. ?search=2023
    general_term = request.args.get('search', '').strip().lower()

    # No search terms given: return all posts
    if not terms and not general_term:
        return jsonify(POSTS)

    def matches(post):
        if any(term in str(post[field]).lower() for field, term in terms.items()):
            return True
        if general_term:
            return any(general_term in str(post[field]).lower()
                       for field in SEARCH_FIELDS)
        return False

    return jsonify([post for post in POSTS if matches(post)])


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, debug=True)