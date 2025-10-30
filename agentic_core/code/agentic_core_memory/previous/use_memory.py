from bedrock_agentcore.memory import MemoryClient
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain.callbacks.base import BaseCallbackHandler
import logging
import asyncio
import boto3
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
from langchain_core.prompts import MessagesPlaceholder
from botocore.exceptions import ClientError






class Config:
    """Financial Analyst 배포 설정"""
    ACTOR_ID = "user123"
    SESSION_ID = "session126"
    MEMORY_PREFIX="agentic_memory"


class AdvancedLLM:
    """고급 LLM 스트리밍 관리자"""
    
    def __init__(self, region_name: str = "us-west-2"):
        self.region_name = region_name
        self.model_id = None
        self.bedrock_client = self._setup_bedrock_client()
        self.llm = self._setup_llm()
    
    def _setup_bedrock_client(self):
        """Bedrock 클라이언트 설정"""
        try:
            return boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region_name
            )
        except Exception as e:
            print(f"❌ Bedrock 클라이언트 초기화 실패: {e}")
            return None
    
    def _setup_llm(self, model_id="global.anthropic.claude-sonnet-4-20250514-v1:0"):
        """LLM 설정"""
        try:
            if not self.bedrock_client:
                print("❌ Bedrock 클라이언트가 없습니다.")
                return None
            self.model_id = model_id
            return ChatBedrock(
                client=self.bedrock_client,
                model_id=self.model_id,
                model_kwargs={
                    "max_tokens": 1000,
                    "temperature": 0.15,
                    "top_p": 0.9,
                }
            )
        except Exception as e:
            print(f"❌ LLM 초기화 실패: {e}")
            return None


import time
from botocore.exceptions import ClientError

class MemoryCallbackHandler(BaseCallbackHandler):
    def __init__(self, memory_client, memory_id, actor_id, session_id):
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.actor_id = actor_id
        self.session_id = session_id
        self.current_user_input = None
    
    def on_llm_end(self, response, **kwargs):
        try:
            if response and response.generations and self.current_user_input:
                ai_message = response.generations[0][0].text
                self.memory_client.save_turn(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    user_input=self.current_user_input,
                    agent_response=ai_message
                )
                self.current_user_input = None
        except Exception as e:
            print(f"❌ AI 메시지 저장 실패: {e}")
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        try:
            if "input" in inputs:
                self.current_user_input = inputs["input"]
        except Exception as e:
            print(f"❌ 사용자 메시지 저장 실패: {e}")
    
    def get_memory_context(self):
        try:
            events = self.memory_client.list_events(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                max_results=5
            )
            
            messages = []
            for event in events:  # Get last 10 events
                payload = event.get('payload', [])
                for item in payload:
                    if 'conversational' in item:
                        conv = item['conversational']
                        content = conv.get('content', {}).get('text', '')
                        role = conv.get('role', '')
                        
                        if role == 'USER' and content:
                            messages.append(HumanMessage(content=content))
                        elif role == 'ASSISTANT' and content:
                            messages.append(AIMessage(content=content))
            
            return messages
        except Exception as e:
            print(f"❌ 메모리 컨텍스트 가져오기 실패: {e}")
            return []


# Updated main function
async def main():

    con = Config() 
    memory_client = MemoryClient(region_name="us-west-2")
    shortterm_memory_id = "test_memory_1-RC2gPHHU6t"
    actor_id = con.ACTOR_ID
    session_id =con.SESSION_ID
    
    # Pass actor_id and session_id to handler
    memory_handler = MemoryCallbackHandler(memory_client, shortterm_memory_id, actor_id, session_id)
    
    llm_manager = AdvancedLLM()

    print("conversation history", memory_handler.get_memory_context())

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Use the conversation history to provide contextual responses."),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])
    
    chain = prompt | llm_manager.llm | StrOutputParser()


    response1 = await chain.ainvoke(
    {"input": "안녕하세요! 제 이름은 김철수입니다.","history": memory_handler.get_memory_context()},
    config={"callbacks": [memory_handler]}
    )
    print(f"응답 1: {response1}")
    
    response2 = await chain.ainvoke(
        {"input": "안녕하세요! 저는 결혼 했습니다.","history": memory_handler.get_memory_context()},
        config={"callbacks": [memory_handler]}
    )
    print(f"응답 2: {response2}")
    
    response3 = await chain.ainvoke(
        {"input": "제 데이터 엔지니어 입니다.","history": memory_handler.get_memory_context()},
        config={"callbacks": [memory_handler]}
    )
    print(f"응답 3: {response3}")
    
    response4 = await chain.ainvoke(
        {"input": "제 서울에 삽니다 입니다.","history": memory_handler.get_memory_context()},
        config={"callbacks": [memory_handler]}
    )
    print(f"응답 3: {response4}")
    
    

    
    # response = await chain.ainvoke(
    #     {"input": "제 정보에 대해 요약해 주세요?",  "history": memory_handler.get_memory_context()},
    #     config={"callbacks": [memory_handler]}
    # )
    # print(f"답변: {response}")

if __name__ == "__main__":
    asyncio.run(main())

