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
import time
import threading
import queue
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



class MemoryCallbackHandler(BaseCallbackHandler):
    def __init__(self, memory_client, memory_id, actor_id, session_id):
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.actor_id = actor_id
        self.session_id = session_id
        self.current_user_input = None
        self.save_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.save_thread = threading.Thread(target=self._background_save_worker, daemon=True)
        self.save_thread.start()
    
    def _background_save_worker(self):
        while not self.stop_event.is_set():
            try:
                print("save conversation")
                # Wait for 3 seconds or until stop event
                if self.stop_event.wait(3):
                    break
                
                # Process all queued items
                items_to_save = []
                while not self.save_queue.empty():
                    try:
                        items_to_save.append(self.save_queue.get_nowait())
                    except queue.Empty:
                        break
                
                # Save items if any
                for item in items_to_save:
                    try:
                        # Use create_event instead of deprecated save_turn
                        self.memory_client.create_event(
                            memory_id=item['memory_id'],
                            actor_id=item['actor_id'],
                            session_id=item['session_id'],
                            messages=[
                                (item['user_input'], 'USER'),
                                (item['agent_response'], 'ASSISTANT')
                            ]
                        )
                    except Exception as e:
                        print(f"❌ 백그라운드 저장 실패: {e}")
                        
            except Exception as e:
                print(f"❌ 백그라운드 워커 오류: {e}")
        
        # Process remaining items before exit
        print("처리 중인 남은 항목들...")
        while not self.save_queue.empty():
            try:
                item = self.save_queue.get_nowait()
                self.memory_client.create_event(
                    memory_id=item['memory_id'],
                    actor_id=item['actor_id'],
                    session_id=item['session_id'],
                    messages=[
                        (item['user_input'], 'USER'),
                        (item['agent_response'], 'ASSISTANT')
                    ]
                )
                print("남은 항목 저장 완료")
            except queue.Empty:
                break
            except Exception as e:
                print(f"❌ 남은 항목 저장 실패: {e}")
        print("백그라운드 워커 종료")
    
    def on_llm_end(self, response, **kwargs):
        try:
            if response and response.generations and self.current_user_input:
                ai_message = response.generations[0][0].text
                # Queue the save operation instead of saving immediately
                self.save_queue.put({
                    'memory_id': self.memory_id,
                    'actor_id': self.actor_id,
                    'session_id': self.session_id,
                    'user_input': self.current_user_input,
                    'agent_response': ai_message
                })
                self.current_user_input = None
        except Exception as e:
            print(f"❌ AI 메시지 큐잉 실패: {e}")
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        try:
            if "input" in inputs:
                self.current_user_input = inputs["input"]
        except Exception as e:
            print(f"❌ 사용자 메시지 저장 실패: {e}")
    
    def stop(self):
        """Stop the background thread"""
        self.stop_event.set()
        self.save_thread.join()
    
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

    with open('deployment_info.json', 'r') as f:
        data = json.load(f)
        new_memory_id = data['memory_id']
    
    memory_client = MemoryClient(region_name="us-west-2")
    con = Config() 
    memory_client = MemoryClient(region_name="us-west-2")
    shortterm_memory_id = new_memory_id
    actor_id = con.ACTOR_ID
    session_id =con.SESSION_ID
    
    # Pass actor_id and session_id to handler
    memory_handler = MemoryCallbackHandler(memory_client, shortterm_memory_id, actor_id, session_id)
    
    try:
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
            {"input": "저는 데이터 엔지니어 입니다.","history": memory_handler.get_memory_context()},
            config={"callbacks": [memory_handler]}
        )
        print(f"응답 4: {response3}")
        
        response4 = await chain.ainvoke(
            {"input": "저는 서울에 삽니다 입니다.","history": memory_handler.get_memory_context()},
            config={"callbacks": [memory_handler]}
        )
        print(f"응답 3: {response4}")


        response5 = await chain.ainvoke(
            {"input": "저는 37살입니다.","history": memory_handler.get_memory_context()},
            config={"callbacks": [memory_handler]}
        )
        print(f"응답 5: {response5}")
    
        
    finally:
        # Stop the background thread when done
        memory_handler.stop()

if __name__ == "__main__":
    asyncio.run(main())

