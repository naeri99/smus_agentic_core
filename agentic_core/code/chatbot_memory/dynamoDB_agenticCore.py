from bedrock_agentcore.runtime import BedrockAgentCoreApp
import boto3
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
import boto3
import json
import sys
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from typing import List, Optional, Dict, Tuple
from langchain_core.prompts import PromptTemplate
import uuid
from datetime import datetime
from botocore.exceptions import ClientError
from operator import itemgetter
from langchain_core.runnables import RunnableLambda
from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_aws import ChatBedrock
from langchain_core.runnables.history import RunnableWithMessageHistory
import time
from botocore.exceptions import ClientError
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.chat_history import BaseChatMessageHistory




app = BedrockAgentCoreApp()


def get_dynamodb_credentials():
    """Get DynamoDB credentials from AWS Secrets Manager"""
    
    # Initialize Secrets Manager client
    secrets_client = boto3.client('secretsmanager')
    
    try:
        # Get the secret value
        response = secrets_client.get_secret_value(SecretId='dynamodb-credentials')
        
        # Parse the JSON string
        secret_data = json.loads(response['SecretString'])
        
        return secret_data
        
    except Exception as e:
        print(f"Error retrieving secret: {e}")
        raise



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
                    "max_tokens": 2000,
                    "temperature": 0.15,
                    "top_p": 0.9,
                }
            )
        except Exception as e:
            print(f"❌ LLM 초기화 실패: {e}")
            return None


class DynamoDBHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str, table_name: str = "conversations-table"):
        self.session_id = session_id
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
    
    @property
    def messages(self) -> list[BaseMessage]:
        """DynamoDB에서 메시지 로드"""
        try:
            response = self.table.query(
                KeyConditionExpression=Key('session_id').eq(self.session_id),
                ScanIndexForward=True,  
                Limit=10,
            )
            
            messages = []
            for item in response['Items']:
                if item['role'] == 'human':
                    messages.append(HumanMessage(content=item['message']))
                elif item['role'] == 'ai':
                    messages.append(AIMessage(content=item['message']))
            
            return messages
        except Exception as e:
            print(f"메시지 로드 실패: {e}")
            return []
    
    def add_message(self, message: BaseMessage) -> None:
        """새 메시지를 DynamoDB에 저장"""
        sequence = int(time.time() * 1000)  # millisecond timestamp
        
        if isinstance(message, HumanMessage):
            role = 'human'
        elif isinstance(message, AIMessage):
            role = 'ai'
        else:
            return
        
        self.table.put_item(
            Item={
                'session_id': self.session_id,
                'sequence': sequence,
                'role': role,
                'message': message.content,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    def clear(self) -> None:
        """대화 기록 삭제"""
        try:
            # Query all items for this session
            response = self.table.query(
                KeyConditionExpression=Key('session_id').eq(self.session_id)
            )
            
            # Delete each item
            for item in response['Items']:
                self.table.delete_item(
                    Key={
                        'session_id': item['session_id'],
                        'sequence': item['sequence']
                    }
                )
        except Exception as e:
            print(f"메시지 삭제 실패: {e}")



credentials = get_dynamodb_credentials()
table_name = credentials['table_name']
region = credentials['region']
table_arn = credentials['table_arn']

# Use in DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name=region)
table = dynamodb.Table(table_name)

# 전역 변수
agent = None

@app.entrypoint
async def extract_text(payload):
    """텍스트 추출 AgentCore Runtime 엔트리포인트"""
    global agent
    global table_name
    
    if agent is None:
        yield {"type": "status", "message": "🚀 LLM 초기화 중..."}
        agent = AdvancedLLM()
    
    # payload에서 입력 데이터 추출
    user_input = payload.get("input_data", "태양의 온도에 대해 말해줘")
    session_id = payload.get("seesion_id", "test-session")  # Fixed typo

    # 체인 구성
    template_dynamo = """The following is a friendly conversation between a human and an AI. 
                        The AI is talkative and provides lots of specific details from its context. 
                        
                        Relevant Information:
                        
                        {chat_history}
                        
                        Conversation:
                        Human: {question}
                        AI:"""
    
    prompt_dynamo = PromptTemplate(
        input_variables=["chat_history", "question"], 
        template=template_dynamo
    )

    # Create chain with DynamoDB history
    chain = prompt_dynamo | agent.llm | StrOutputParser()
    
    chain_dynamo = RunnableWithMessageHistory(
        chain,
        get_session_history=lambda session_id: DynamoDBHistory(session_id, table_name),
        input_messages_key="question",
        history_messages_key="chat_history"
    )
    
    yield {"type": "status", "message": "🔥 응답 생성 중..."}
    
    collected_text = []
    try:
        # Use chain_dynamo and pass proper input
        async for event in chain_dynamo.astream_events(
            {"question": user_input},
            config={"configurable": {"session_id": session_id}}
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, 'content') and chunk.content:
                    if isinstance(chunk.content, str):
                        collected_text.append(chunk.content)
                        yield {"type": "stream", "content": chunk.content}
                                
    except Exception as e:
        yield {"type": "error", "message": f"❌ 스트리밍 실패: {e}"}
    
    # 최종 결과
    final_text = "".join(collected_text)
    yield {"type": "final", "content": final_text}

async def test():
    # Test payload
    test_payload = {
        "input_data": "내가 생각하는 상사병은 무엇인가요?",
        "seesion_id": "test-session-001"
    }
    
    print("🚀 Starting chat...")
    
    # Run the extract_text function
    async for result in extract_text(test_payload):
        if result["type"] == "status":
            print(f"📊 {result['message']}")
        elif result["type"] == "stream":
            print(result["content"], end="", flush=True)
        elif result["type"] == "error":
            print(f"\n❌ {result['message']}")
        elif result["type"] == "final":
            print(f"\n\n✅ Final result: {len(result['content'])} characters")

if __name__ == "__main__":
    # asyncio.run(test())
    app.run()
    









