import os
import fitz  # PyMuPDF for extracting text from PDF
from pdf2image import convert_from_bytes  # For converting PDF to images
from uagents import Agent, Context, Model, Bureau
from typing import List
import base64
from openai import OpenAI
import asyncio
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
import re
import hashlib


app = Flask(__name__)
update_api_url = 'http://localhost:9000/pdf-urls/update'
pdf_url = ""

load_dotenv(dotenv_path='./.env')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Ensure necessary directories exist
for directory in ['images', 'audio', 'subtitles']:
    os.makedirs(directory, exist_ok=True)

class UploadPDF(Model):
    filename: str
    filedata: str

class SlideText(Model):
    slide_number: int
    text: str
    
class ResponseSlides(Model):
    slides: List[SlideText]

class StringArrayModel(Model):
    messages: List[str]


def url_to_folder_name(url, max_length=255):
    """
    Converts a URL into a valid folder name by replacing invalid characters and truncating if necessary.
    Args:
        url (str): The URL to convert.
        max_length (int): Maximum allowed length of the folder name (default is 255).

    Returns:
        str: A valid folder name derived from the URL.
    """
    # Step 1: Replace invalid characters with underscores
    folder_name = re.sub(r'[<>:"/\\|?*]', '_', url)
    
    # Step 2: Limit the length of the folder name
    if len(folder_name) > max_length:
        # If the folder name is too long, use a hash of the URL to ensure uniqueness
        hash_object = hashlib.md5(url.encode('utf-8')).hexdigest()
        folder_name = folder_name[:max_length - len(hash_object) - 1] + '_' + hash_object
    
    return folder_name

### PDF to Text Agent: Handles PDF Upload and Text Extraction
pdf_to_text_agent = Agent(name="PDF_to_Text_agent", seed="pdf text recovery phrase")

@pdf_to_text_agent.on_message(model=UploadPDF)
async def handle_upload_pdf(ctx: Context, sender: str, req: UploadPDF):
    # Extract text directly from the PDF data
    pdf_data = base64.b64decode(req.filedata)
    slides = extract_text_per_slide(pdf_data)  # Remove limit if necessary

    await ctx.send(lecture_agent.address, ResponseSlides(slides=slides))

def extract_text_per_slide(pdf_data: bytes) -> List[SlideText]:
    slides = []
    try:
        # Open the PDF directly from bytes using PyMuPDF (fitz)
        pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

        # Extract text from each slide
        for page_num in range(pdf_document.page_count):
            page = pdf_document.load_page(page_num)
            text = page.get_text("text")

            print(f"Extracted text from slide {page_num + 1}:\n{text}")
            slides.append(SlideText(slide_number=page_num + 1, text=text))

        return slides

    except Exception as e:
        print(f"Error occurred: {e}")
        raise

### PDF to Image Agent: Handles PDF Upload and Image Extraction
pdf_to_image_agent = Agent(name="PDF_to_Image_agent", seed="pdf image recovery phrase")

@pdf_to_image_agent.on_message(model=UploadPDF)
async def convert_pdf_to_images(ctx: Context, sender: str, req: UploadPDF):
    global pdf_url
    pdf_data = base64.b64decode(req.filedata)
    images = convert_from_bytes(pdf_data)
    output = []

    # Save each page as an image
    for i, image in enumerate(images):
        image_path = f'images/{url_to_folder_name(pdf_url)}/page_{i+1}.png'
        image.save(image_path, 'PNG')
        output.append(image_path)

        upload_url = "http://localhost:9000/" + image_path
        print(upload_url)

        url = "http://localhost:9000/pdf-item/create"  # Adjust if different
        payload = {
            "page": i + 1,
            "pdf_url": pdf_url,
            "image_url": upload_url
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers)

    return StringArrayModel(messages=output)

### Lecture Agent: Generates Lecture from Extracted Text and Images
lecture_agent = Agent(name="Lecture_agent", seed="lecture recovery phrase")

@lecture_agent.on_message(model=ResponseSlides)
async def handle_generate_lecture(ctx: Context, sender: str, msg: ResponseSlides):
    lectures = generate_lecture_from_slides(msg.slides)
    
    await ctx.send(voice_agent.address, StringArrayModel(messages=lectures))
    # return StringArrayModel(messages=lectures)

def generate_lecture_from_slides(slides: List[SlideText], previous_lectures: str = "") -> List[str]:
    content = []
    lecture_history = previous_lectures  # Start with any existing lecture history

    # Loop through each slide to prepare the prompt for each slide
    for slide in slides:
        # Add each slide's text content to the message list
        messages = [
            {
                "role": "user",
                "content": f"Here is the lecture so far: {lecture_history}.\nNow, generate a minute long lecture speech for slide {slide.slide_number}: {slide.text}"
            }
        ]

        print(f"Generating lecture for slide {slide.slide_number}...")
        # Send request to OpenAI GPT-4 API for the current slide
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use the appropriate model
            messages=messages
        )

        # Extract the response for the current slide
        current_lecture = response.choices[0].message.content
        content.append(current_lecture)
        print(f"Lecture for slide {slide.slide_number}:\n{current_lecture}")

        # Append the generated lecture to the history
        lecture_history += f"\n\nLecture for slide {slide.slide_number}:\n{current_lecture}"
    
    return content

### Voice Agent: Handles Voice Synthesis
voice_agent = Agent(name="Voice_agent", seed="voice recovery phrase")

@voice_agent.on_message(model=StringArrayModel)
async def handle_voice_synthesis(ctx: Context, sender: str, msg: StringArrayModel):
    global pdf_url
    print("Received messages for voice synthesis.")
    outputs = []

    for index, lecture in enumerate(msg.messages):
        print(f"Synthesizing voice for lecture: {lecture}")
        audio_path = text_to_speech(lecture, f"audio/{url_to_folder_name(pdf_url)}/lecture_{index}.mp3")

        print(f"Audio content written to {audio_path}")
        requests.put(update_api_url, json={"url": pdf_url, "field": "audio_url", "page": index + 1, "value": "http://localhost:9000/" + f"audio/{url_to_folder_name(pdf_url)}/lecture_{index}.mp3"})
        print({"url": pdf_url, "field": "audio_url", "page": index + 1, "value": "http://localhost:9000/" + f"audio/{url_to_folder_name(pdf_url)}/lecture_{index}.mp3"})
        outputs.append(f"audio/{url_to_folder_name(pdf_url)}/lecture_{index}.mp3")

    await ctx.send(transcription_agent.address, StringArrayModel(messages=outputs))
    # return StringArrayModel(messages=outputs)

def text_to_speech(text: str, output_filename: str):
    response = client.audio.speech.create(
        model="tts-1",
        input=text,
        voice="nova"
    )
    response.stream_to_file(output_filename)
    print(f"Audio content written to {output_filename}")
    return output_filename

### Transcription Agent: Handles Audio Transcription
transcription_agent = Agent(name="Transcription_agent", seed="transcription recovery phrase")

@transcription_agent.on_message(model=StringArrayModel)
async def handle_audio_transcription(ctx: Context, sender: str, msg: StringArrayModel):
    global pdf_url
    outputs = []

    for index, audio_file in enumerate(msg.messages):
        output_srt_file = f'subtitles/{url_to_folder_name(pdf_url)}/{os.path.basename(audio_file)}.srt'
        transcription = transcribe_audio(audio_file)

        with open(output_srt_file, 'w') as f:
            f.write(transcription)
        requests.put(update_api_url, json={"url": pdf_url, "field": "transcription", "page": index + 1, "value": "http://localhost:9000/" + f"subtitles/{url_to_folder_name(pdf_url)}/{os.path.basename(audio_file)}.srt"})
        print({"url": pdf_url, "field": "transcription", "page": index + 1, "value": "http://localhost:9000/" + f"subtitles/{url_to_folder_name(pdf_url)}/{os.path.basename(audio_file)}.srt"})
        outputs.append(transcription)
    
    return StringArrayModel(messages=outputs)

def transcribe_audio(audio_file):
    with open(audio_file, 'rb') as audio:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio,
            language="en",
            response_format="srt",
            timestamp_granularities=["segment"]
        )

    return transcription

### User Agent: Handles User Interaction
user_agent = Agent(name="User_agent", seed="user recovery phrase")

@user_agent.on_interval(5)
async def send_message(ctx: Context):
    global pdf_url
    pdf_path = "CSS.pdf"  # Path to your PDF file
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    url = "http://localhost:9000/pdf-urls"
    response = requests.get(url)
    if response.status_code == 200:
        # Parse the JSON response and print the result
        data = response.json()
        print("PDF URLs with status 'processing' or 'not completed':")
        for pdf_uri in data.get("pdf_urls", []):
            pdf_url = pdf_uri
            print(pdf_url)
            pdf_response = requests.get(pdf_url)
            with open("CSS.pdf", "wb") as file:
                file.write(pdf_response.content)
    else:
        print(f"Failed to retrieve data. Status code: {response.status_code}")

    if not os.path.exists(pdf_path):
        return
    
    for directory in ['images', 'audio', 'subtitles']:
        os.makedirs(directory + f"/{url_to_folder_name(pdf_url)}", exist_ok=True)

    ctx.logger.info("Sending a message to the pdf parser.")

    # Read the file as bytes
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    if not pdf_bytes:
        raise FileNotFoundError("Failed to load PDF or file is empty.")

    # Encode the PDF bytes to base64 string
    encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

    # Simulate the request object
    req = UploadPDF(filename=pdf_path, filedata=encoded_pdf)

    await ctx.send(pdf_to_image_agent.address, req)
    await ctx.send(pdf_to_text_agent.address, req)


### Bureau to Manage Agents
bureau = Bureau()
bureau.add(pdf_to_text_agent)
bureau.add(pdf_to_image_agent)
bureau.add(lecture_agent)
bureau.add(voice_agent)
bureau.add(transcription_agent)
bureau.add(user_agent)

if __name__ == "__main__":
    bureau.run()
