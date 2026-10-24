# BeetBox

A short project coded for the University of Manchester Open Source Society X Major League Hacking Hacktoberfest event.

The project using a very simple python backend with Flask, to take in a prompt, send it to Google Gemma and have it design a playlist. Said playlist is then checked on MusicBrainz and then downloaded from Youtube, for you to play in your browser. It isn't perfect, and youtube is likely to block you when downloading (just like in our demo).

# Setup
Create the file ```API.env``` containing ```GEMINI_API_KEY = "blablablaPutTheKeyHere"```.

Then run ```pip -r requirements.txt```, and then run backend.py. This should create a Flask web server running on port 1111. You can then find BeetBox at http://localhost:1111


# Credit

- Website Frontend based on [Telephasic by HTML5UP](https://html5up.net/)
- Backend using [Flask](https://palletsprojects.com/projects/flask)
- MusicBrainz querying using [MusicBrainzngs](https://github.com/alastair/python-musicbrainzngs)
- Youtube downloader is of course [yt-dlp](https://github.com/yt-dlp/yt-dlp)
