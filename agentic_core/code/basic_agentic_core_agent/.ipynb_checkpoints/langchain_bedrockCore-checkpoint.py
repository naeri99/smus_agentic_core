import asyncio
import boto3
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import json
app = BedrockAgentCoreApp()

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

# 전역 변수
agent = None

@app.entrypoint
async def extract_text(payload):
    """텍스트 추출 AgentCore Runtime 엔트리포인트"""
    global agent
    
    if agent is None:
        yield {"type": "status", "message": "🚀 LLM 초기화 중..."}
        agent = AdvancedLLM()
    
    # payload에서 입력 데이터 추출
    user_input = payload.get("input_data", "태양의 온도에 대해 말해줘")
    
    # 체인 구성
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", user_input)
    ])
    
    chain = prompt | agent.llm | StrOutputParser()
    
    yield {"type": "status", "message": "🔥 응답 생성 중..."}
    
    collected_text = []
    try:
        async for event in chain.astream_events({}):
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









