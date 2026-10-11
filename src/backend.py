from flask import Flask, render_template, request
from google import genai


app:Flask = Flask(__name__)
client = genai.Client()
PromptPrefill = """
You are a professional DJ trying to create a playlist for the user. Your objective is to follow their prompt, and try and create a playlist that they would enjoy. You MUST stay within the genre bounds that they
give, refrain from giving bad tracks, or tracks that don't exist.

Give your playlist in the form of a comma separated list in-between curly braces. Each track should be in the form "Track Name - Album - ArtistName". This should be sent at the end of your message.

{ Never Gonna Give You Up - Never Gonna Give You Up - Rick Astley, }
"""

@app.route('/')
def home():
    return render_template("Frontend.html")

@app.route("/GemmaRequest", methods=["POST"])
def GemmaRequest():
    prompt = request.form["Request"]
    if len(prompt) > 300:
        return "Error"


    
    return "Hello"

@app.route("/api", methods=["POST"])
def api():
    pass



app.run(port=1111)