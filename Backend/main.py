from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests
import base64
from twilio.rest import Client
# from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import aiofiles
import whisper
from google import genai
from dotenv import load_dotenv
import os



model = whisper.load_model("base")
load_dotenv() 

api_key2 = os.getenv("API_KEY")

WEBHOOK_URL = "https://ce23-122-252-228-30.ngrok-free.app/ivr"

#google client
client = genai.Client(api_key=api_key2)

twilio_sid = os.getenv("TWILIO_SID")
twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
INDIA_PHONE_NUMBER = "+918088012208"

#twilio client
twilio_client = Client(twilio_sid, twilio_auth_token)

app = FastAPI()

# CORS Middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to the frontend's URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/make-call")
def make_call():
    """Make an outbound call to an Indian number."""
    call = twilio_client.calls.create(
        to=INDIA_PHONE_NUMBER, 
        from_=twilio_phone_number,
        url="https://257c-122-252-228-30.ngrok-free.app/ivr"  # Your IVR webhook
    )
    return {"status": "Call initiated", "call_sid": call.sid}


@app.post("/ivr")
async def ivr_response():
    """Handle incoming IVR call and provide response."""
    response = VoiceResponse()

    # Gather user speech input
    gather = Gather(input="speech", enhanced=True, speech_model="phone_call",
                    speech_timeout="auto", timeout=10, language="en-GB", action="/process-audio")
    
    gather.say("Welcome to the AI-powered IVR. Please state your symptoms after the beep.")
    response.append(gather)
    
    # Fallback in case no input is received
    response.say("Sorry, we didn't hear anything.")
    response.redirect("/ivr")

    return Response(content=str(response), media_type="application/xml")

@app.post("/process-audio")
async def process_audio(request: Request):
    """Download Twilio audio, transcribe it, and generate a response."""
    form_data = await request.form()
    recording_url = form_data.get("RecordingUrl")
    call_sid = form_data.get("CallSid")
    speech_result = form_data.get("SpeechResult")
    confidence = form_data.get("Confidence")

    if not recording_url:
        return {"detail": "No recording URL found in Twilio request."}

    # Check if recording exists before fetching
    metadata_url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Recordings/{call_sid}.json"
    metadata_response = requests.get(metadata_url, auth=(twilio_sid, twilio_auth_token))

    if metadata_response.status_code != 200:
        return {"detail": f"Failed to fetch recording metadata: {metadata_response.status_code}"}

    # Download the audio file
    headers = {
        "Authorization": f"Basic {base64.b64encode(f'{twilio_sid}:{twilio_auth_token}'.encode()).decode()}",
        "Accept": "*/*"
    }
    audio_response = requests.get(recording_url, headers=headers)

    if audio_response.status_code != 200:
        return {"detail": f"Failed to download audio from Twilio: {audio_response.status_code}"}

    # Save the audio file
    audio_path = "twilio_recording.wav"
    with open(audio_path, "wb") as audio_file:
        audio_file.write(audio_response.content)

    # If speech is already transcribed by Twilio
    if speech_result:
        transcribed_text = speech_result
    else:
        # Perform local transcription using OpenAI Whisper (assuming it's set up)
        result = model.transcribe(audio_path)
        transcribed_text = result["text"]

    print(f"Transcribed text: {transcribed_text}, Confidence: {confidence}")

    # Send data to webhook for further processing
    twilio_data = {
        "SpeechResult": transcribed_text,
        "Confidence": confidence,
        "CallSid": call_sid
    }
    requests.post(WEBHOOK_URL, json=twilio_data, headers={'Content-Type': 'application/json'})

    # Respond to Twilio IVR
    twilio_response = VoiceResponse()
    twilio_response.say(f"You said: {transcribed_text}. Thank you!")
    
    return Response(content=str(twilio_response), media_type="application/xml")