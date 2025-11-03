import json
import boto3
import asyncio
import argparse
from clean import load_deployment_info

async def invoke_agent(question, session_id="test-session-001"):
    agentcore_client = boto3.client('bedrock-agentcore', region_name='us-west-2')
    deployment_info = load_deployment_info()
    
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=deployment_info["agent_arn"],
            qualifier="DEFAULT",
            payload=json.dumps({
                "input_data": question,
                "seesion_id": session_id
            })
        )
    )
    
    for line in response['response'].iter_lines():
        if line and line.startswith(b'data: '):
            data = json.loads(line[6:].decode('utf-8'))
            if data['type'] == 'status':
                print(f"📊 {data['message']}")
            elif data['type'] == 'stream':
                print(data['content'], end='', flush=True)
            elif data['type'] == 'error':
                print(f"\n❌ {data['message']}")
            elif data['type'] == 'final':
                print(f"\n\n✅ Final result: {len(data['content'])} characters")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', help='질문을 입력하세요')
    parser.add_argument('--session', default='test-session-001', help='세션 ID')
    args = parser.parse_args()
    asyncio.run(invoke_agent(args.query, args.session))


