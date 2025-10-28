import asyncio
import boto3
import time
from typing import List, Dict, Any, AsyncGenerator, Optional
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue
import json
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class OrignalLLM:
    """고급 LLM 스트리밍 관리자"""
    
    def __init__(self, region_name: str = "us-west-2"):
        self.region_name = region_name
        self.model_id = None
        self.bedrock_client = self._setup_bedrock_client()  # Initialize bedrock_client first!
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



async def extract_text(chain):
    """텍스트 추출 함수"""
    collected_text = []
    try:
        async for event in chain.astream_events({}):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, 'content') and chunk.content:
                    # Handle different content formats
                    if isinstance(chunk.content, str):
                        collected_text.append(chunk.content)
                        print(chunk.content, end="", flush=True)
                    elif isinstance(chunk.content, list):
                        for content_item in chunk.content:
                            if isinstance(content_item, dict):
                                if text := content_item.get('text'):
                                    collected_text.append(text)
                                    print(text, end="", flush=True)
                            elif isinstance(content_item, str):
                                collected_text.append(content_item)
                                print(content_item, end="", flush=True)
    except Exception as e:
        print(f"❌ 스트리밍 실패: {e}")
        # Fallback to regular invoke
        try:
            result = await chain.ainvoke({})
            return result
        except:
            # Final fallback to sync
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, chain.invoke, {})
            return result
    
    return "".join(collected_text)

async def main():
    print("🚀 LLM 초기화 중...")
    agent = OrignalLLM()
    
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", "태양의 온도에 대해 말해줘")
    ])
    
    chain = prompt | agent.llm | StrOutputParser()
    
    print("🔥 응답 생성 중...")
    try:
        full_text = await extract_text(chain)
        print(f"\n\n✅ 완료! 총 {len(full_text)} 글자 생성됨")
    except Exception as e:
        print(f"❌ 실행 실패: {e}")
        # Fallback
        try:
            result = chain.invoke({})
            print(f"✅ Fallback 성공: {result}")
        except Exception as fallback_error:
            print(f"❌ Fallback도 실패: {fallback_error}")

if __name__ == "__main__":
    asyncio.run(main())







