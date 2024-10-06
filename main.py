from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import os

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

audio_folder = os.path.join(os.getcwd(), 'audio')
images_folder = os.path.join(os.getcwd(), 'images')
subtitles_folder = os.path.join(os.getcwd(), 'subtitles')

# Serve files from the "audio" directory
@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory(audio_folder, filename)

# Serve files from the "images" directory
@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(images_folder, filename)

# Serve files from the "subtitles" directory
@app.route('/subtitles/<path:filename>')
def serve_subtitles(filename):
    return send_from_directory(subtitles_folder, filename)

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

class yhack2024_item(db.Model):
    page = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pdf_url = db.Column(db.String(1024), nullable=False)
    audio_url = db.Column(db.String(1024), nullable=False)
    image_url = db.Column(db.String(1024), nullable=False)
    transcription = db.Column(db.String(10256), nullable=False)
    user_id = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True),nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True))


# Route to get URLs of PDF files with status 'processing' or 'not completed'
@app.route('/pdf-urls', methods=['GET'])
def get_pdf_urls():
    # Query the database for URLs where status is 'processing' or 'not completed'
    file = db.session.query(yhack2024_slide).filter_by(status="processing").first()

    if not file:
        return jsonify({"pdf_urls": []})
    
    file = db.session.query(yhack2024_slide).filter_by(url=file.url).first()
    file.status = 'completed'
    db.session.commit()

    # Return the URLs as a JSON response
    return jsonify({"pdf_urls": [file.url]})


@app.route('/pdf-item/create', methods=['POST'])
def create_pdf_items():
    data = request.get_json()
    page = data.get('page')
    pdf_url = data.get('pdf_url')
    image_url = data.get('image_url')

    new_item = yhack2024_item(
        page=page,
        pdf_url=pdf_url,
        audio_url='',
        image_url=image_url,
        transcription='',
        user_id='',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.session.add(new_item)
    db.session.commit()

    return jsonify({"message": "PDF item created successfully"}), 200


# Route to update the status of a PDF file to 'completed' by URL
@app.route('/pdf-urls/update', methods=['PUT'])
def update_pdf_status():
    # Get the URL from the request body
    data = request.get_json()
    page = data.get('page')
    url_to_update = data.get('url')
    field = data.get('field')
    value = data.get('value')
    
    # Query the database for the URL provided
    item = db.session.query(yhack2024_item).filter_by(pdf_url=url_to_update, page=str(page)).first()
    if item:
        # Update the status to 'completed'
        setattr(item, field, value)
        db.session.commit()
        return jsonify({"message": f"Status updated for URL: {url_to_update}"}), 200
    else:
        return jsonify({"error": "URL not found"}), 404


# Create database tables in the PostgreSQL database if they don't exist yet
with app.app_context():
    db.create_all()

# Run the Flask app
if __name__ == '__main__':
    os.makedirs(audio_folder, exist_ok=True)
    os.makedirs(images_folder, exist_ok=True)
    os.makedirs(subtitles_folder, exist_ok=True)

    app.run(debug=True, port=os.getenv("PORT", default=9000))
