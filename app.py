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
import uuid
from pydantic import Field

from argparse import ArgumentParser
from flask import Flask, request, abort, send_from_directory

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
    AudioMessage,
    ShowLoadingAnimationRequest
)
from uuid import UUID
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import ConfigurableFieldSpec
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from openai import BaseModel
from langchain_community.utilities import GoogleSerperAPIWrapper

from dotenv import load_dotenv
import os
from memory import get_session_history
from video import generate_audio

app = Flask(__name__)
load_dotenv()

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv("CHANNEL_SECRET")
channel_access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
host = "https://travel-plan-deecdwgvdwgpdzcz.eastus-01.azurewebsites.net"
# host = "https://6605-49-216-32-22.ngrok-free.app"


parser = WebhookParser(channel_secret)

configuration = Configuration(
    access_token=channel_access_token
)
handler = WebhookHandler(channel_secret)

jonery_store = {}

# Define your desired data structure.
class TravelReply(BaseModel):
    Answer: str = Field(description="詳細版回答")
    ShortAnswer: str = Field(description="精簡版回答")
    
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
            jonery_store[user_id] = message.strip()
                
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
        pdf_combined_text = pdf_combined_text.replace("###").replace("**")
 
        word_loader = Docx2txtLoader("./doc/行程_東京.docx")
        word_doc = word_loader.load()
        word_combined_text = "\n".join([page.page_content for page in word_doc])
        word_combined_text = word_combined_text.replace("###").replace("**")
    
        context = ""
        
        if user_id not in jonery_store:
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"您好，請先選擇【東京行程】或【名古屋行程】")]
                )
            )
            return
        else:
            if(jonery_store[user_id]=="東京行程"):
                context = f"""
                    [東京行程]
                    {word_combined_text}
                """
            else:
                context = f"""
                    [名古屋行程]
                    {pdf_combined_text}
                """

        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=user_id, loadingSeconds=20))

        # 1.構建樣板
        prompt = ChatPromptTemplate.from_messages(
        [  
            ("system","""
                你是一個旅遊行程助理，請檢索context區塊及Google Search結果，生成兩個版本的回答，並以 JSON 格式輸出。
                {{
                    "Answer": "詳細版回答",
                    "ShortAnswer": "精簡版回答"
                }}
     
                1. 詳細版回答：請提供全面且詳細的回答，涵蓋所有相關的背景信息、細節和例子，**務必**保留**全部**網址訊息，將其放進 Answer 欄位。
                2. 精簡版回答：請提取出最關鍵的要點，並用簡短的語句進行總結，將其放進 ShowAnswer 欄位。
                
                若沒有檢索到相關資料、無法回答，無論如何，依然**務必**要使用 JSON 格式輸出
                {{
                    "Answer": "...",
                    "ShortAnswer": "..."
                }}
                
                若答案參考記憶，依然**務必**要使用 JSON 格式輸出
                {{
                    "Answer": "...",
                    "ShortAnswer": "..."
                }}
                
                Google Search 結果：
                {search}
                
                <context>
                    {context}
                </context>
                
                ## 輸出 Json 格式
                {{
                    "Answer": "詳細版回答",
                    "ShortAnswer": "精簡版回答"
                }}
                
                ## 注意
                1. 確認回答的內容在 Context 區段內。
                2. 請一步一步思考，確認回答的內容都來自以上參考資料且正確無誤。
                3. **務必**生成兩個版本的答案，並將結果分別放入 Answer、ShortAnswer。
                4. 請**務必**將答案中的 ###、** 語法移除：
                   範例1:### 厥餅，移除後為 厥餅。
                   範例2:**店名**，移除後為 店名。
                    
                ## 重要
                請再次確認輸出內容是否使用 {{"Answer": "詳細版回答", "ShortAnswer": "精簡版回答"}} JSON 輸出，否則系統會Crash，後果會非常嚴重。   
                           
                {format_instructions}
                
                若使用者問附近景點或附近美食，請用條列式回答問題。
            """),
            MessagesPlaceholder(variable_name="history"),
            ('human', "我要問{plan}"),
            ('human', '{query}'),
        ])
        
        is_search_prompt = ChatPromptTemplate.from_messages(
        [  
            ("system","""
              若使用者問附近景點或附近美食，則回答 Y，否則回答 N。
            """),
            ('human', '{query}')
        ])
        
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  
        parser = JsonOutputParser(pydantic_object=TravelReply)
        
        nearby_chain = is_search_prompt | llm | StrOutputParser()
        is_nearby_quest = nearby_chain.invoke({
            "query": message
        })
        print(is_nearby_quest)
        
        searchResult = ""
        if is_nearby_quest == "Y":
            search = GoogleSerperAPIWrapper()
            searchResult = search.run(message)
            # print(searchResult)
                     
        # 2. 創建鏈
        # chain = prompt | llm | StrOutputParser()
        chain = prompt | llm | parser

        # 3. 加入記憶
        with_history_chain = RunnableWithMessageHistory(
            chain,
            get_session_history,
            input_messages_key="query",
            history_messages_key="history",
            history_factory_config=[
                ConfigurableFieldSpec(
                    id="session_id",
                    annotation=str,
                    name="Session ID",
                    default="",
                    is_shared=True,
                ),
                ConfigurableFieldSpec(
                    id="plan",
                    annotation=str,
                    name="plan",
                    default="",
                    is_shared=True,
                )
            ]
        )
        
        # 3. 調用鏈得到結果
        result = with_history_chain.invoke(
            {
                "context": context,
                "search": searchResult,
                "plan": jonery_store[user_id],
                "query": message,
                "format_instructions": parser.get_format_instructions()
            }, 
            config={"configurable": {"session_id": user_id, "plan": jonery_store[user_id]}}
        )

        print(result)
        
        # 4. 透過 OpenAI TTS 產生音檔
        file_name = f"{user_id}-{uuid.uuid4()}.mp3"
        file_path = f"./audio/{file_name}"
        audio = generate_audio(file_path, result.get("ShortAnswer"))      
        length = int(audio.info.length * 1000)
    
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=result.get("Answer")),
                    AudioMessage(
                        type="audio",
                        originalContentUrl = f'{host}/audio/{file_name}',
                        duration=length
                    )
                    ]
            )
        )
                
# 提供本地音訊檔案的路由
@app.route('/audio/<filename>')
def get_audio(filename):
    return send_from_directory(directory='./audio', path=filename)

if __name__ == "__main__":
    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    )
    arg_parser.add_argument('-p', '--port', type=int, default=8000, help='port')
    arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    options = arg_parser.parse_args()

    app.run(debug=options.debug, port=options.port)
    
    
    
