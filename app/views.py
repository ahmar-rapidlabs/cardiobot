# myapp/views.py

import logging
from django.shortcuts import render
import os
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core.agent import ReActAgent
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool
from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage
from llama_index.core import SimpleDirectoryReader
from llama_index.core.memory.chat_memory_buffer import ChatMemoryBuffer, SimpleChatStore, ChatMessage

# Ensure the environment variable is set
openai_api_key = os.environ.get('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set")

# Set up logging
logging.basicConfig(level=logging.DEBUG)

def get_index(data, index_name):
    index = None
    if not os.path.exists(index_name):
        print("building index", index_name)
        index = VectorStoreIndex.from_documents(data, show_progress=True)
        index.storage_context.persist(persist_dir=index_name)
    else:
        index = load_index_from_storage(
            StorageContext.from_defaults(persist_dir=index_name)
        )
    return index

cardiac_pdf = SimpleDirectoryReader(input_dir='data')
cardiac_documents = cardiac_pdf.load_data()
cardiac_index = get_index(cardiac_documents, "cardiac")
cardiac_engine = cardiac_index.as_query_engine()

tools = [
    QueryEngineTool(
        query_engine=cardiac_engine,
        metadata=ToolMetadata(
            name="cardiac_data",
            description="this gives detailed information about Cardiac Health Disorders from the PDF only",
        ),
    ),
]

base_context = """Purpose: The primary role of this agent is to assist users by providing accurate factual 
               information from the PDF only. The agent must not answer any questions related to general knowledge.
               You are a CardioBot and you are trained on a specific knowledge base.
               If you do not know the answer, just say I dont know the relevant answer.
               Do not give any answer if you do not find it from the PDF.
               Do not give any answers related to general knowledge questions.
               While answering new questions, also remember past responses from {chat_memory}
               Do not provide any answer related to countries. """

# Initialize chat memory buffer
chat_memory = ChatMemoryBuffer.from_defaults(
    chat_store=SimpleChatStore(), 
    token_limit=2048
)

llm = OpenAI(model="gpt-4", api_key=openai_api_key)
agent = ReActAgent.from_tools(tools, llm=llm, verbose=True, context=base_context, memory=chat_memory)

def query_with_memory(agent, prompt):
    chat_history = chat_memory.get_all()
    context_with_memory = base_context + "\n" + "\n".join(f"User: {msg.content}" if msg.role == "user" else f"Bot: {msg.content}" for msg in chat_history)
    context_with_memory += f"\nUser: {prompt}"
    
    response = agent.query(context_with_memory)
    chat_memory.put(ChatMessage(role="user", content=prompt))
    chat_memory.put(ChatMessage(role="assistant", content=response))
    return response

@csrf_exempt
def chatbot(request):
    if request.method == 'POST':
        try:
            logging.debug("Received request: %s", request.POST)
            query = request.POST.get('query', '')
            logging.debug("Query: %s", query)
            response = query_with_memory(agent, query)
            logging.debug("Response: %s", response)
            return JsonResponse({'response': str(response)})
        except Exception as e:
            logging.error("Error processing request: %s", e)
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
