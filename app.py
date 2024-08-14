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
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader
from dotenv import load_dotenv
import requests
import os

app = Flask(__name__)
load_dotenv()

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv("CHANNEL_SECRET")
channel_access_token = os.getenv("CHANNEL_ACCESS_TOKEN")

parser = WebhookParser(channel_secret)

configuration = Configuration(
    access_token=channel_access_token
)
handler = WebhookHandler(channel_secret)

store = {}

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
    user_id = event.source.user_id
    message = event.message.text 

    with ApiClient(configuration) as api_client: 
        line_bot_api = MessagingApi(api_client)
        
        if(message.strip()=="東京行程" or message.strip()=="名古屋行程"):
            store[user_id] = message.strip()
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"您好，我是您的旅遊助理，你可以問我任何【{message.strip()}】的問題")]
                )
            )
            return 
    
        pdf_loader = PyMuPDFLoader('./doc/行程_名古屋.pdf')
        pdf_doc = pdf_loader.load()
        
        # 將所有頁面的文本合併成一個字符串
        pdf_combined_text = "\n".join([page.page_content for page in pdf_doc])

        word_loader = Docx2txtLoader("./doc/行程_東京.docx")
        word_doc = word_loader.load()
        word_combined_text = "\n".join([page.page_content for page in word_doc])
    
        context = ""
        
        if user_id not in store:
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"您好，請先選擇【東京行程】或【名古屋行程】")]
                )
            )
            return
        else:
            if(store[user_id]=="東京行程"):
                context = f"""
                    [東京行程]
                    {word_combined_text}
                """
            else:
                context = f"""
                    [名古屋行程]
                    {pdf_combined_text}
                """
        
        chat_template = ChatPromptTemplate.from_messages(
        [  
            ("system","""
                你是一個旅遊行程助理，若使用者提問名古屋行程，則到[名古屋行程]檢索資料，若使用者提問東京行程，則到[東京行程]檢索資料，
                請使用繁體中文回答。
                
                <context>
                    {context}
                </context>

                ## 注意
                確認回答的內容在[名古屋行程]、 [東京行程]區段內。
                最後請一步一步思考，確認回答的內容都來自以上參考資料且正確無誤。
            """),
            ('human', "我要問{plan}"),
            ('human', '{question}'),
        ])
        
 
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=user_id, loadingSeconds=20))
        
        
        chatMessages = chat_template.format_messages(context=context, plan = store[user_id],question=message)
       
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
