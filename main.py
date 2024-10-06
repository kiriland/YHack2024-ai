import os
import fitz  # PyMuPDF for extracting text from PDF
from pdf2image import convert_from_path  # For converting PDF to images
from uagents import Agent, Context, Model, Bureau
from typing import List
import base64
from openai import OpenAI
from dotenv import load_dotenv
import asyncio


load_dotenv(dotenv_path='../../../.env')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


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


### PDF Agent: Handles PDF Upload and Text/Image Extraction
pdf_agent = Agent(name="PDF_agent", seed="pdf recovery phrase")


@pdf_agent.on_message(model=UploadPDF)
async def handle_upload_pdf(ctx: Context, sender: str, req: UploadPDF):
    # Extract text directly from the PDF data
    pdf_data = base64.b64decode(req.filedata)
    slides = extract_text_per_slide(pdf_data)[:3]

    # Extract images from the PDF
    convert_pdf_to_images(req.filename)

    # Prepare the response
    response = ResponseSlides(slides=slides)

    # Send the response to the lecture agent
    await ctx.send(lecture_agent.address, response)


def extract_text_per_slide(pdf_data: bytes) -> List[SlideText]:
    slides = []
    try:
        # Open the PDF directly from bytes using PyMuPDF (fitz)
        pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

        # Extract text from each slide
        for page_num in range(pdf_document.page_count):
            page = pdf_document.load_page(page_num)
            text = page.get_text("text")
            slides.append(SlideText(slide_number=page_num + 1, text=text))

        return slides

    except Exception as e:
        print(f"Error occurred: {e}")
        raise


def convert_pdf_to_images(pdf_path: str) -> None:
    # Convert PDF pages to images
    images = convert_from_path(pdf_path)

    # Save each page as an image
    for i, image in enumerate(images):
        image.save(f'images/page_{i+1}.png', 'PNG')



### Lecture Agent: Generates Lecture from Extracted Text and Images
lecture_agent = Agent(name="Lecture_agent", seed="lecture recovery phrase")

@lecture_agent.on_message(model=ResponseSlides)
async def handle_generate_lecture(ctx: Context, sender: str, msg: ResponseSlides):
    lectures = generate_lecture_from_slides(msg.slides)
    lectures_model = StringArrayModel(messages=lectures)
    
    # Send the generated lecture to the voice agent
    await ctx.send(voice_agent.address, lectures_model)


def generate_lecture_from_slides(slides: List[SlideText], previous_lectures: str = "") -> List[str]:
    messages = []
    content = []
    lecture_history = previous_lectures  # Start with any existing lecture history

    # Loop through each slide to prepare the prompt for each slide
    for slide in slides:
        image_path = f"images/page_{slide.slide_number}.png"
        
        # Encode the image to base64
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Add each slide's text content and image to the message list
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Here is the lecture so far: {lecture_history}.\n"
                            f"Now, generate a lecture speech for slide {slide.slide_number}: {slide.text}"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{encoded_image}"
                    }
                }
            ]
        })

        # Send request to OpenAI GPT-4 Vision API for the current slide
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using the Vision model
            messages=messages
        )

        # Extract the response for the current slide
        current_lecture = response.choices[0].message.content
        content.append(current_lecture)

        # Append the generated lecture to the history
        lecture_history += f"\n\nLecture for slide {slide.slide_number}:\n{current_lecture}"
    
    return content


### Voice Agent: Handles Voice Synthesis
voice_agent = Agent(name="Voice_agent", seed="voice recovery phrase")

@voice_agent.on_message(model=StringArrayModel)
async def handle_voice_synthesis(ctx: Context, sender: str, msg: StringArrayModel):
    for index, lecture in enumerate(msg.messages):
        print(f"Synthesizing voice for lecture: {lecture}")
        text_to_speech(lecture, f"audio/lecture_{index}.mp3")

    # Send the synthesized voice to the user agent
    await ctx.send(user_agent.address, "Voice synthesis completed.")


def text_to_speech(text: str, output_filename: str):
    response = client.audio.speech.create(
        model = "tts-1",
        input=text,
        voice="nova"
    )
    
    response.stream_to_file(output_filename)
    print(f"Audio content written to {output_filename}")
    return output_filename


### User Agent: Handles User Interaction
user_agent = Agent(name="User_agent", seed="user recovery phrase")

@user_agent.on_event("startup")
async def send_message(ctx: Context):
    ctx.logger.info("Sending a message to the pdf parser.")

    pdf_path = "CSS.pdf"  # Path to your PDF file

    # Read the file as bytes
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    if not pdf_bytes:
        raise FileNotFoundError("Failed to load PDF or file is empty.")

    # Encode the PDF bytes to base64 string
    encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

    # Simulate the request object
    req = UploadPDF(filename=pdf_path, filedata=encoded_pdf)

    print(await ctx.send(pdf_agent.address, req))


### Bureau to Manage Agents
bureau = Bureau()
bureau.add(pdf_agent)
bureau.add(lecture_agent)
bureau.add(user_agent)
bureau.add(voice_agent)

if __name__ == "__main__":
    # Example usage to simulate sending a PDF
    pdf_path = "CSS.pdf"  # Path to your PDF file

    # Read the file as bytes
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    if not pdf_bytes:
        raise FileNotFoundError("Failed to load PDF or file is empty.")

    # Simulate sending the PDF to the PDF agent
    encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    req = UploadPDF(filename=pdf_path, filedata=encoded_pdf)
    
    # Start the Bureau (runs all agents)
    bureau.run()

    async def run_agents(ctx: Context):
        # Send a message from one agent to another
        await ctx.send(pdf_agent.address, req)

    asyncio.run(run_agents())
    
if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))