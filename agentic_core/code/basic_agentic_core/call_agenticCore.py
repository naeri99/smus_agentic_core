import json
import boto3
import asyncio
import argparse
from clean import load_deployment_info

async def invoke_agent(question):
    agentcore_client = boto3.client('bedrock-agentcore', region_name='us-west-2')
    deployment_info = load_deployment_info()
    
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=deployment_info["agent_arn"],
            qualifier="DEFAULT",
            payload=json.dumps({"input_data": question})
        )
    )
    
    for line in response['response'].iter_lines():
        if line and line.startswith(b'data: '):
            data = json.loads(line[6:].decode('utf-8'))
            if data['type'] == 'stream':
                print(data['content'], end='')
    print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=True, help='질문을 입력하세요')
    args = parser.parse_args()
    
    asyncio.run(invoke_agent(args.query))