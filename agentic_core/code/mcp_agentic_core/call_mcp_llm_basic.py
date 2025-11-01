import asyncio
import sys
import boto3
import json
import argparse
from boto3.session import Session
from mcp import ClientSession
from streamable_http_sigv4 import streamablehttp_client_with_sigv4
from langchain_aws import ChatBedrock

def create_streamable_http_transport_sigv4(mcp_url: str, service_name: str, region: str):
    session = boto3.Session()
    credentials = session.get_credentials()
    return streamablehttp_client_with_sigv4(
        url=mcp_url,
        credentials=credentials,
        service=service_name,
        region=region,
    )

async def llm_mcp_handler(mcp_session, query):
    # Get available tools
    tools = await mcp_session.list_tools()
    tool_descriptions = [f"- {t.name}: {t.description}" for t in tools.tools]
    
    # Initialize LLM
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    llm = ChatBedrock(
        client=bedrock_client,
        model_id="global.anthropic.claude-sonnet-4-20250514-v1:0",
        model_kwargs={"max_tokens": 1000, "temperature": 0}
    )
    
    # Create prompt
    prompt = f"""Query: {query}

Available tools:
{chr(10).join(tool_descriptions)}

Respond in JSON format:
- To use tool: {{"tool": "tool_name", "params": {{"param1": "value1"}}}}
- Direct answer: {{"tool": null, "response": "your_answer"}}"""

    # Get LLM response
    response = llm.invoke(prompt).content.strip()
    
    # Parse and execute
    try:
        decision = json.loads(response)
        
        if decision.get("tool"):
            result = await mcp_session.call_tool(
                decision["tool"], 
                decision.get("params", {})
            )
            return f"🔧 Tool result: {result}"
        else:
            return f"🤖 LLM response: {decision.get('response', response)}"
            
    except (json.JSONDecodeError, KeyError):
        return f"🤖 LLM response: {response}"

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
        
        async with create_streamable_http_transport_sigv4(
            mcp_url=mcp_url, service_name="bedrock-agentcore", region=region
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                
                yield {"type": "status", "message": "✅ Processing..."}
                
                response = await llm_mcp_handler(mcp_session, payload["input_data"])
                yield {"type": "stream", "content": response}
                
    except Exception as e:
        yield {"type": "error", "message": str(e)}

async def test_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="User query")
    args = parser.parse_args()
    
    payload = {"input_data": args.query}
    
    async for result in extract_text(payload):
        if result["type"] == "stream":
            print(result["content"])
        elif result["type"] == "status":
            print(f"\n{result['message']}")
        elif result["type"] == "error":
            print(f"\n❌ {result['message']}")

if __name__ == "__main__":
    asyncio.run(test_main())