import asyncio
import sys
import logging
import boto3
from boto3.session import Session
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from streamable_http_sigv4 import streamablehttp_client_with_sigv4
from botocore.auth import SigV4Auth


def create_streamable_http_transport_sigv4(
    mcp_url: str, service_name: str, region: str
):
    """
    Create a streamable HTTP transport with AWS SigV4 authentication.

    """
    # Get AWS credentials from the current boto3 session
    # These credentials will be used to sign requests with SigV4
    session = boto3.Session()
    credentials = session.get_credentials()

    # Create and return the custom transport with SigV4 signing capability
    return streamablehttp_client_with_sigv4(
        url=mcp_url,
        credentials=credentials,
        service=service_name,
        region=region,
    )
def get_full_tools_list(client):
    """
    Retrieve the complete list of tools from an MCP client, handling pagination.

    """
    more_tools = True
    tools = []
    pagination_token = None

    # Loop until we've fetched all pages
    while more_tools:
        tmp_tools = client.list_tools_sync(pagination_token=pagination_token)

        tools.extend(tmp_tools)

        # Check if there are more pages to fetch
        if tmp_tools.pagination_token is None:
            # No more pages - we're done
            more_tools = False
        else:
            # More pages exist - prepare to fetch the next one
            more_tools = True
            pagination_token = tmp_tools.pagination_token

    return tools


async def main():
    boto_session = Session()
    region = boto_session.region_name
    print(f"Using AWS region: {region}")

    ssm_client = boto3.client("ssm", region_name=region)

    agent_arn_response = ssm_client.get_parameter(
        Name="/mcp_server/runtime_iam/agent_arn"
    )
    agent_arn = agent_arn_response["Parameter"]["Value"]
    print(f"Retrieved Agent ARN: {agent_arn}")

    if not agent_arn:
        print("❌ Error: AGENT_ARN not found")
        sys.exit(1)

    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    try:
        async with create_streamable_http_transport_sigv4(
            mcp_url=mcp_url, service_name="bedrock-agentcore", region=region
        ) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                print("\n🔄 Initializing MCP session...")
                await session.initialize()
                print("✓ MCP session initialized")

                print("\n🔄 Listing available tools...")
                tool_result = await session.list_tools()

                print("\n📋 Available MCP Tools:")
                print("=" * 50)
                for tool in tool_result.tools:
                    print(f"🔧 {tool.name}")
                    print(f"   Description: {tool.description}")
                    if hasattr(tool, "inputSchema") and tool.inputSchema:
                        properties = tool.inputSchema.get("properties", {})
                        if properties:
                            print(f"   Parameters: {list(properties.keys())}")
                    print()

                print(f"✅ Successfully connected to MCP server!")
                print(f"Found {len(tool_result.tools)} tools available.")

    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        import traceback

        print("\n🔍 Full error traceback:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())