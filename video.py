# 提供本地音频文件的路由
import uuid
from flask import app, send_from_directory
from openai import OpenAI
from mutagen.mp3 import MP3


def generate_audio(file_path: str, text: str):
    client = OpenAI()
    response = client.audio.speech.create(
        model="tts-1",
        voice="onyx",
        input=text
    )
    
    response.stream_to_file(file_path)
    audio = MP3(file_path)
    return audio


