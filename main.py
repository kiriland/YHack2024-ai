from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Set up the SQLAlchemy database URI
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("POSTGRES_CONN")

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Define the Book model according to the given schema
class yhack2024_slide(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    url = db.Column(db.String, nullable=False)
    user_id = db.Column(db.String, nullable=False)
    status = db.Column(db.String, nullable=False)  # Status can be 'processing' or 'not completed'
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

# Route to get URLs of PDF files with status 'processing' or 'not completed'
@app.route('/pdf-urls', methods=['GET'])
def get_pdf_urls():
    # Query the database for URLs where status is 'processing' or 'not completed'
    file = db.session.query(yhack2024_slide).filter_by(status="processing").first()

    if not file:
        return jsonify({"pdf_urls": []})

    # Return the URLs as a JSON response
    return jsonify({"pdf_urls": [file.url]})


# Route to update the status of a PDF file to 'completed' by URL
@app.route('/pdf-urls/update', methods=['PUT'])
def update_pdf_status():
    # Get the URL from the request body
    data = request.get_json()
    url_to_update = data.get('url')

    # Query the database for the URL provided
    file = db.session.query(yhack2024_slide).filter_by(url=url_to_update).first()

    if file:
        # Update the status to 'completed'
        file.status = 'completed'
        db.session.commit()  # Commit the change to the database
        return jsonify({"message": f"Status updated for URL: {url_to_update}"}), 200
    else:
        return jsonify({"error": "URL not found"}), 404


# Create database tables in the PostgreSQL database if they don't exist yet
with app.app_context():
    db.create_all()

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))
