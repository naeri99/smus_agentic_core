from bedrock_agentcore.memory import MemoryClient
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain.callbacks.base import BaseCallbackHandler
import logging
import asyncio
import boto3
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
from langchain_core.prompts import MessagesPlaceholder
from botocore.exceptions import ClientError
import time
import threading
import queue
from botocore.exceptions import ClientError


from use_memory_time import Config, AdvancedLLM, MemoryCallbackHandler



async def main():

    with open('deployment_info.json', 'r') as f:
        data = json.load(f)
        new_memory_id = data['memory_id']

    memory_client = MemoryClient(region_name="us-west-2")
    con = Config() 
    memory_client = MemoryClient(region_name="us-west-2")
    shortterm_memory_id = new_memory_id
    actor_id = con.ACTOR_ID
    session_id =con.SESSION_ID
    
    # Pass actor_id and session_id to handler
    memory_handler = MemoryCallbackHandler(memory_client, shortterm_memory_id, actor_id, session_id)
    
    try:
        llm_manager = AdvancedLLM()

        print("conversation history", memory_handler.get_memory_context())

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant. Use the conversation history to provide contextual responses."),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
        
        chain = prompt | llm_manager.llm | StrOutputParser()

        response = await chain.ainvoke(
        {"input": "제 정보에 대해 요약해 주세요?",  "history": memory_handler.get_memory_context()},
        config={"callbacks": [memory_handler]}
        )
        print(f"답변: {response}")
        
        
    finally:
        # Stop the background thread when done
        memory_handler.stop()

if __name__ == "__main__":
    asyncio.run(main())

