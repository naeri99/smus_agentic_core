from bedrock_agentcore.memory import MemoryClient
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain.schema import HumanMessage, AIMessage
import boto3
import json
import asyncio
import threading
from collections import deque
from bedrock_agentcore.runtime import app

# Global variables
memory_client = None
llm = None
conversation_queue = deque()
save_thread = None
stop_saving = threading.Event()

def get_memory_id_from_secrets():
    secrets_client = boto3.client('secretsmanager', region_name='us-west-2')
    response = secrets_client.get_secret_value(SecretId='agentic-memory-config')
    secret_data = json.loads(response['SecretString'])
    return secret_data['memory_id']

def get_memory_context(memory_client, memory_id, actor_id, session_id):
    try:
        events = memory_client.list_events(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            max_results=5
        )
        
        messages = []
        for event in events:
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
    except:
        return []

def save_conversation_batch():
    """10초 간격으로 대화 저장하는 백그라운드 스레드"""
    while not stop_saving.wait(10):  # 10초 대기
        if conversation_queue:
            batch_to_save = []
            # 큐에서 모든 대화 가져오기
            while conversation_queue:
                try:
                    batch_to_save.append(conversation_queue.popleft())
                except IndexError:
                    break
            
            # 배치로 저장
            for conv_data in batch_to_save:
                try:
                    memory_client.create_event(
                        memory_id=conv_data['memory_id'],
                        actor_id=conv_data['actor_id'],
                        session_id=conv_data['session_id'],
                        messages=[
                            (conv_data['user_input'], 'USER'),
                            (conv_data['ai_response'], 'ASSISTANT')
                        ]
                    )
                    print(f"✅ 저장 완료: {conv_data['session_id']}")
                except Exception as e:
                    print(f"❌ 저장 실패: {e}")

def start_save_thread():
    """저장 스레드 시작"""
    global save_thread
    if save_thread is None or not save_thread.is_alive():
        stop_saving.clear()
        save_thread = threading.Thread(target=save_conversation_batch, daemon=True)
        save_thread.start()

def queue_conversation(memory_id, actor_id, session_id, user_input, ai_response):
    """대화를 큐에 추가"""
    conversation_queue.append({
        'memory_id': memory_id,
        'actor_id': actor_id,
        'session_id': session_id,
        'user_input': user_input,
        'ai_response': ai_response
    })

@app.entrypoint
async def chat_with_memory(payload):
    global memory_client, llm
    
    if memory_client is None:
        yield {"type": "status", "message": "🚀 Memory 초기화 중..."}
        memory_client = MemoryClient(region_name="us-west-2")
    
    if llm is None:
        yield {"type": "status", "message": "🚀 LLM 초기화 중..."}
        bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
        llm = ChatBedrock(
            client=bedrock_client,
            model_id="global.anthropic.claude-sonnet-4-20250514-v1:0",
            model_kwargs={"max_tokens": 1000, "temperature": 0.15, "top_p": 0.9}
        )
    
    # 저장 스레드 시작
    start_save_thread()
    
    # Load memory ID from Secrets Manager
    memory_id = get_memory_id_from_secrets()
    
    # Get parameters from payload
    actor_id = payload.get("actor_id", "user123")
    session_id = payload.get("session_id", "session126")
    user_input = payload.get("input_data", "안녕하세요!")
    
    # Get conversation history
    loop = asyncio.get_event_loop()
    history = await loop.run_in_executor(
        None, 
        get_memory_context, 
        memory_client, memory_id, actor_id, session_id
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Use the conversation history to provide contextual responses."),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    yield {"type": "status", "message": "🔥 응답 생성 중..."}
    
    collected_text = []
    try:
        async for event in chain.astream_events({"input": user_input, "history": history}):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, 'content') and chunk.content:
                    if isinstance(chunk.content, str):
                        collected_text.append(chunk.content)
                        yield {"type": "stream", "content": chunk.content}
                    elif isinstance(chunk.content, list):
                        for content_item in chunk.content:
                            if isinstance(content_item, dict):
                                if text := content_item.get('text'):
                                    collected_text.append(text)
                                    yield {"type": "stream", "content": text}
                            elif isinstance(content_item, str):
                                collected_text.append(content_item)
                                yield {"type": "stream", "content": content_item}
                                
    except Exception as e:
        yield {"type": "error", "message": f"❌ 스트리밍 실패: {e}"}
        return
    
    # 완성된 응답을 큐에 추가 (10초마다 저장됨)
    final_response = "".join(collected_text)
    queue_conversation(memory_id, actor_id, session_id, user_input, final_response)
    
    yield {"type": "final", "content": final_response}

if __name__ == "__main__":
    try:
        app.run()
    finally:
        # 종료 시 저장 스레드 정리
        stop_saving.set()
        if save_thread and save_thread.is_alive():
            save_thread.join(timeout=1)