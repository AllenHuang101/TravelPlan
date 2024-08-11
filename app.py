# -*- coding: utf-8 -*-

#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.


import os
import sys
from argparse import ArgumentParser

from flask import Flask, request, abort

from linebot.v3 import (
    WebhookHandler
)

from linebot import (
    WebhookParser
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    ShowLoadingAnimationRequest
)

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv
import requests
import os

app = Flask(__name__)
load_dotenv()

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv("CHANNEL_SECRET")
channel_access_token = os.getenv("CHANNEL_ACCESS_TOKEN")

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ORGANIZATION_ID = os.getenv("ORGANIZATION_ID")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
os.environ["OPENAI_ORGANIZATION"] = ORGANIZATION_ID

parser = WebhookParser(channel_secret)

configuration = Configuration(
    access_token=channel_access_token
)
handler = WebhookHandler(channel_secret)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)


    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    chat_template = ChatPromptTemplate.from_messages(
    [  
        ("system","""
            你是一位經驗豐富的旅遊規劃專家，專注於為各類遊客提供量身定制的旅遊行程。
            請詳細描述每一天的行程安排，包括參觀的景點、推薦的餐廳。
            請用條列式請用條列式，並保持精簡。
         """),
        ('human', '{question}'),
    ])
    

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=event.source.user_id, loadingSeconds=20))
        
        message = event.message.text
        chatMessages = chat_template.format_messages(question=message)
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        result = llm.invoke(chatMessages)

      
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=result.content)]
            )
        )
        

if __name__ == "__main__":
    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    )
    arg_parser.add_argument('-p', '--port', type=int, default=8000, help='port')
    arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    options = arg_parser.parse_args()

    app.run(debug=options.debug, port=options.port)
