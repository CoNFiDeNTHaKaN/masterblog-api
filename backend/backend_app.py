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

POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post."},
    {"id": 2, "title": "Second post", "content": "This is the second post."},
]

SORT_FIELDS = ("title", "content")
SORT_DIRECTIONS = ("asc", "desc")


def generate_post_id():
    """Return a new unique integer ID (max existing ID + 1)."""
    return max((post["id"] for post in POSTS), default=0) + 1


def find_post_by_id(post_id):
    """Return the post with the given id, or None if it doesn't exist."""
    return next((post for post in POSTS if post["id"] == post_id), None)


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

    sorted_posts = sorted(
        POSTS,
        key=lambda post: post[sort_field].lower(),
        reverse=(direction == "desc")
    )
    return jsonify(sorted_posts)


@app.route('/api/posts', methods=['POST'])
def add_post():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    missing = [field for field in ("title", "content")
               if not str(data.get(field) or "").strip()]
    if missing:
        return jsonify({
            "error": "Missing required fields.",
            "missing_fields": missing
        }), 400

    new_post = {
        "id": generate_post_id(),
        "title": data["title"].strip(),
        "content": data["content"].strip(),
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

    # Only overwrite fields that were provided with a non-empty value
    for field in ("title", "content"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            post[field] = value.strip()

    return jsonify(post), 200


@app.route('/api/posts/search', methods=['GET'])
def search_posts():
    title_term = request.args.get('title', '').strip().lower()
    content_term = request.args.get('content', '').strip().lower()

    # No search terms given: return all posts
    if not title_term and not content_term:
        return jsonify(POSTS)

    results = [
        post for post in POSTS
        if (title_term and title_term in post["title"].lower())
        or (content_term and content_term in post["content"].lower())
    ]
    return jsonify(results)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, debug=True)
