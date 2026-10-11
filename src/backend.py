from flask import Flask, render_template, request, jsonify, url_for
from google import genai
from dotenv import load_dotenv
from YoutubeDownloader import fetch
from pathlib import Path

load_dotenv("API.env")


app:Flask = Flask(__name__)
client = genai.Client()
PromptPrefill = """
You are a professional DJ trying to create a playlist for the user. Your objective is to follow their prompt, and try and create a playlist that they would enjoy. You MUST stay within the genre bounds that they
give, refrain from giving bad tracks, or tracks that don't exist.

Give your playlist in the form of a comma separated list in-between curly braces. Each track should be in the form "Track Name - Album - ArtistName". This should be sent at the end of your message.

You should have at minimum 3 songs, and at maximum 6 songs.

Examples:
{ Never Gonna Give You Up - Never Gonna Give You Up - Rick Astley, Set Fire to the Rain - 21 - Adele, Get Lucky - Single - Daft Punk featuring Pharrell Williams and Nile Rodgers}
{ I Got You Babe - Look at Us - Sonny & Cher,  Three Little Birds - Exodus - Bob Marley and the Wailers, I Want It That Way - Millennium - Backstreet Boys, Livin' on a Prayer - Slippery When Wet - Bon Jovi}

Here is the user prompt:

"""

@app.route('/')
def home():
    return render_template("index.html")

@app.route("/GemmaRequest", methods=["POST"])
def GemmaRequest():
    prompt = request.form["Request"]
    if len(prompt) > 300:
        return "Error", 400
    print("Sending Request")
    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it",
        config = genai.types.GenerateContentConfig(
            system_instruction=PromptPrefill
        ),
        contents=prompt,
    )
    print(response.text)
    if response.text == None:
        return "Error"
    DJ, songs = (response.text).split("{")
    DecodeAndDownload(songs)
    return DJ

def DecodeAndDownload(Songs: str):
    Songs = Songs.strip("{} ").split(",")
    for song in Songs:
        fetch(song)

@app.route("/playlist")
def playlist():
    music_folder = Path(app.static_folder) / "music"

    supported_formats = {".mp3", ".ogg", ".wav", ".m4a", ".flac"}

    tracks = sorted(
        (
            file for file in music_folder.iterdir()
            if file.is_file() and file.suffix.lower() in supported_formats
        ),
        key=lambda file: file.name.casefold()
    ) if music_folder.is_dir() else []

    return jsonify([
        {
            "title": file.stem,
            "url": url_for(
                "static",
                filename=f"music/{file.name}"
            )
        }
        for file in tracks
    ])

app.run(port=1111)
