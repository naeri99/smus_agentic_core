import asyncio
import sys
import os
import boto3
from boto3.session import Session
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Generator, Any
import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.streamable_http import GetSessionIdCallback, StreamableHTTPTransport, streamablehttp_client
from mcp.shared._httpx_utils import McpHttpClientFactory, create_mcp_http_client
from mcp.shared.message import SessionMessage
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.tools import BaseTool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import json

app = BedrockAgentCoreApp()

class MCPTool(BaseTool):
    name: str
    description: str
    mcp_session: Any = None
    tool_info: Any = None
    
    def __init__(self, mcp_session, tool_info, **kwargs):
        super().__init__(
            name=tool_info.name,
            description=tool_info.description,
            mcp_session=mcp_session,
            tool_info=tool_info,
            **kwargs
        )
    
    def _run(self, **kwargs) -> str:
        try:
            return asyncio.run(self._async_run(**kwargs))
        except Exception as e:
            return f"Tool error: {str(e)}"
    
    async def _arun(self, **kwargs) -> str:
        return await self._async_run(**kwargs)
    
    async def _async_run(self, **kwargs) -> str:
        try:
            result = await self.mcp_session.call_tool(self.tool_info.name, kwargs)
            return str(result)
        except Exception as e:
            return f"MCP tool error: {str(e)}"

class SigV4HTTPXAuth(httpx.Auth):
    def __init__(self, credentials: Credentials, service: str, region: str):
        self.credentials = credentials
        self.service = service
        self.region = region
        self.signer = SigV4Auth(credentials, service, region)

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        headers = dict(request.headers)
        headers.pop("connection", None)
        
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=headers,
        )
        
        self.signer.add_auth(aws_request)
        request.headers.update(dict(aws_request.headers))
        yield request

@asynccontextmanager
async def streamablehttp_client_with_sigv4(
    url: str,
    credentials: Credentials,
    service: str,
    region: str,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 60 * 5,
    terminate_on_close: bool = True,
    httpx_client_factory: McpHttpClientFactory = create_mcp_http_client,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
        GetSessionIdCallback,
    ],
    None,
]:
    async with streamablehttp_client(
        url=url,
        headers=headers,
        timeout=timeout,
        sse_read_timeout=sse_read_timeout,
        terminate_on_close=terminate_on_close,
        httpx_client_factory=httpx_client_factory,
        auth=SigV4HTTPXAuth(credentials, service, region),
    ) as result:
        yield result

def create_streamable_http_transport_sigv4(mcp_url: str, service_name: str, region: str):
    session = boto3.Session()
    credentials = session.get_credentials()
    return streamablehttp_client_with_sigv4(
        url=mcp_url,
        credentials=credentials,
        service=service_name,
        region=region,
    )

async def llm_mcp_handler(mcp_session, region, query):
    try:
        # MCP 도구 정보 가져오기
        mcp_tools = await mcp_session.list_tools()
        tools_list = mcp_tools.tools if hasattr(mcp_tools, 'tools') else mcp_tools
        
        # LLM 초기화
        bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        llm = ChatBedrock(
            client=bedrock_client,
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            model_kwargs={"max_tokens": 1000, "temperature": 0}
        )
        
        # 도구 정보를 스키마와 함께 텍스트로 변환
        tool_descriptions = []
        for tool_info in tools_list:
            schema = tool_info.inputSchema
            required_params = schema.get('required', [])
            properties = schema.get('properties', {})
            
            param_info = []
            for param in required_params:
                param_type = properties.get(param, {}).get('type', 'unknown')
                param_info.append(f"{param} ({param_type})")
            
            tool_descriptions.append(
                f"- {tool_info.name}: {tool_info.description}\n"
                f"  필수 파라미터: {', '.join(param_info)}"
            )
        
        tools_text = "\n".join(tool_descriptions)
        
        # 개선된 도구 선택 프롬프트
        selection_prompt = f"""
        사용 가능한 도구들:
        {tools_text}
        
        질문: {query}
        
        이 질문을 분석하세요:
        1. 수학 계산이 필요한가? → add_numbers 또는 multiply_numbers 사용
        2. 사용자 인사가 필요한가? → greet_user 사용  
        3. 위 도구들로 해결할 수 없는 일반적인 질문인가? → "none" 선택
        
        응답 형식:
        {{
            "tool": "도구명 또는 none",
            "params": {{"파라미터": 값}} 또는 {{}}
        }}
        
        JSON만 응답하세요:
        """
        
        # LLM으로 도구 선택 및 파라미터 생성
        response = await llm.ainvoke(selection_prompt)
        
        try:
            import json
            decision = json.loads(response.content.strip())
            
            tool_name = decision.get("tool")
            params = decision.get("params", {})
            
            print(f"Selected tool: {tool_name}, params: {params}")
            
            if tool_name and tool_name.lower() != "none":
                # MCP 도구 실행
                tool_result = await mcp_session.call_tool(tool_name, params)
                return f"🔧 도구 '{tool_name}' 결과: {tool_result}"
            else:
                # 도구 없이 직접 답변
                direct_response = await llm.ainvoke(f"질문에 답하세요: {query}")
                return f"🤖 직접 답변: {direct_response.content}"
                
        except (json.JSONDecodeError, KeyError) as e:
            print(f"JSON 파싱 오류: {e}")
            # JSON 파싱 실패 시 직접 답변
            direct_response = await llm.ainvoke(f"질문에 답하세요: {query}")
            return f"🤖 직접 답변: {direct_response.content}"
        
    except Exception as e:
        return f"❌ Error: {str(e)}"



@app.entrypoint
async def extract_text(payload):
    try:
        yield {"type": "status", "message": "🚀 Initializing LLM..."}
        
        boto_session = Session()
        region = boto_session.region_name or 'us-west-2'
        ssm_client = boto3.client("ssm", region_name=region)
        
        agent_arn_response = ssm_client.get_parameter(Name="/mcp_server/runtime_iam/agent_arn")
        agent_arn = agent_arn_response["Parameter"]["Value"]
        
        encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        yield {"type": "status", "message": "✅ Connecting to MCP..."}
        
        stderr_backup = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        
        try:
            async with create_streamable_http_transport_sigv4(
                mcp_url=mcp_url, service_name="bedrock-agentcore", region=region
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as mcp_session:
                    await mcp_session.initialize()
                    
                    yield {"type": "status", "message": "✅ Processing..."}
                    
                    response = await llm_mcp_handler(mcp_session, region, payload["input_data"])
                    yield {"type": "stream", "content": response}
        finally:
            sys.stderr.close()
            sys.stderr = stderr_backup
                
    except Exception as e:
        yield {"type": "error", "message": str(e)}

if __name__ == "__main__":
    app.run()
