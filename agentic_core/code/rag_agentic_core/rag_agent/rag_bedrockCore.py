import asyncio
import boto3
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import json
import requests
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from requests.auth import HTTPBasicAuth
from opensearchpy import OpenSearch, RequestsHttpConnection
from langchain_aws import BedrockEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from operator import itemgetter
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser

app = BedrockAgentCoreApp()

class OpenSearchEmbeddingProcessor:
    """OpenSearch 임베딩 처리 및 저장 클래스"""
    
    def __init__(self, region = 'us-west-2', index_name= "aws-document-chunks" ):
        # AWS region
        self.region = region
        self.service = 'es'
        
        # AWS credential
        self.session = boto3.Session()
        self.credentials = self.session.get_credentials()
        
        # OpenSearch setting
        secrets_client = boto3.client('secretsmanager', region_name=self.region)
        response = secrets_client.get_secret_value(SecretId='opensearch-credentials')
        secrets = json.loads(response['SecretString'])
        self.username = secrets['username']
        self.password = secrets['password'] 
        self.host = secrets['opensearch_host']
        self.headers = {'Content-Type': 'application/json'}
        
        # embedding
        self.embeddings = self._setup_embeddings()
        self.os_client = OpenSearch(
                            hosts=[{'host': self.host, 'port': 443}],
                            http_auth=(self.username, self.password),
                            use_ssl=True,
                            verify_certs=True,
                            connection_class=RequestsHttpConnection
                        )
        self.index_name = index_name

    def _setup_embeddings(self):
        """Bedrock 임베딩 모델 설정"""
        try:
            return BedrockEmbeddings(
                client=boto3.client(
                    service_name='bedrock-runtime',
                    region_name=self.region
                ),
                model_id="amazon.titan-embed-text-v2:0"
            )
        except Exception as e:
            print(f"❌ 임베딩 모델 초기화 실패: {e}")
            return None

    def get_embedding(self, text):
        """BedrockEmbeddings를 사용한 임베딩 생성"""
        if not self.embeddings:
            self.embeddings = self._setup_embeddings()
        return self.embeddings.embed_query(text)

    def vector_search(self, query, k=5):
        try:
            # KNN vector search query
            query_vector = self.get_embedding(query)
            vector_search = {
                "size": k,
                "_source": {
                    "excludes": ["content_embedding"]
                },
                "query": {
                    "knn": {
                        "content_embedding": {
                            "vector": query_vector,
                            "k": k
                        }
                    }
                }
            }

            # Execute the search
            response = self.os_client.search(
                index=self.index_name,
                body=vector_search
            )

            documents = []
            for res in response["hits"]["hits"]:
                source = res['_source']
                page_content = {k: source[k] for k in source if k != "vector"}
                metadata = {"id": res['_id']}
                score = res['_score']
                documents.append((Document(page_content=json.dumps(page_content, ensure_ascii=False), metadata=metadata), score))
            return documents

        except Exception as e:
            print(f"Search error: {str(e)}")
            return []


class RagLLM:
    """RagLLM 스트리밍 관리자"""
    
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


# 전역 변수
agent = None
opensearh = None


def get_prompt():
    template_lambda = """The following is a friendly conversation between a human and an AI. 
    The AI is talkative and provides lots of specific details from its context. 
    If the AI does not know the answer to a question, it truthfully says it does not know. 
    The AI ONLY uses information contained in the "Relevant Information" section and does not hallucinate.
    
    Relevant Information:
    {document}
    
    Conversation:
    Human: {question}
    AI:"""
    
    prompt_lambda = PromptTemplate(
        input_variables=["document", "question"], 
        template=template_lambda
    )
    
    return prompt_lambda

@app.entrypoint
async def extract_text(payload):
    """텍스트 추출 AgentCore Runtime 엔트리포인트"""
    global agent
    global opensearh
    
    if agent is None:
        yield {"type": "status", "message": "🚀 LLM 초기화 중..."}
        agent = RagLLM()
    if opensearh is None:
        yield {"type": "status", "message": "🚀 Opensearch Connection 초기화 중..."}
        opensearh = OpenSearchEmbeddingProcessor()
    
    # payload에서 입력 데이터 추출
    user_input = payload.get("input_data", "태양의 온도에 대해 말해줘")

    rag_prompt = get_prompt()

    chain_lambda_rag = (
        {
            "document": lambda x: opensearh.vector_search(user_input),
            "question": itemgetter("question")
        }
        | rag_prompt
        | agent.llm
        | StrOutputParser()
    )
    
    yield {"type": "status", "message": "🔥 응답 생성 중..."}
    
    collected_text = []
    try:
        async for event in chain_lambda_rag.astream_events({"question": user_input}):
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
    
    # 최종 결과
    final_text = "".join(collected_text)
    yield {"type": "final", "content": final_text}



if __name__ == "__main__":
    app.run()









