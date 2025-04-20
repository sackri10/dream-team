# File: main.py
from fastapi import FastAPI, Depends, UploadFile, HTTPException, Query, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.storage.blob import BlobServiceClient
# from sqlalchemy.orm import Session
import schemas, crud
from database import CosmosDB
import os
import uuid
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse, Response
import json, asyncio
from magentic_one_helper import MagenticOneHelper
from autogen_agentchat.messages import MultiModalMessage, TextMessage, ToolCallExecutionEvent, ToolCallRequestEvent
from autogen_agentchat.base import TaskResult
from magentic_one_helper import generate_session_name
import aisearch
import logging

from datetime import datetime 
from schemas import AutoGenMessage
from typing import List
import time

import util

util.load_dotenv_from_azd()

oot_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)

# Clear existing handlers and set the new one
root_logger.handlers.clear()
root_logger.addHandler(handler)

logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logging.getLogger('azure.monitor.opentelemetry.exporter.export').setLevel(logging.WARNING)

print("Starting the server...")
#print(f'AZURE_OPENAI_ENDPOINT:{os.getenv("AZURE_OPENAI_ENDPOINT")}')
#print(f'COSMOS_DB_URI:{os.getenv("COSMOS_DB_URI")}')
#print(f'AZURE_SEARCH_SERVICE_ENDPOINT:{os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")}')

session_data = {}
MAGENTIC_ONE_DEFAULT_AGENTS = [
            {
            "input_key":"0001",
            "type":"MagenticOne",
            "name":"Coder",
            "system_message":"",
            "description":"",
            "icon":"👨‍💻"
            },
            {
            "input_key":"0002",
            "type":"MagenticOne",
            "name":"Executor",
            "system_message":"",
            "description":"",
            "icon":"💻"
            },
            {
            "input_key":"0003",
            "type":"MagenticOne",
            "name":"FileSurfer",
            "system_message":"",
            "description":"",
            "icon":"📂"
            },
            {
            "input_key":"0004",
            "type":"MagenticOne",
            "name":"WebSurfer",
            "system_message":"",
            "description":"",
            "icon":"🏄‍♂️"
            },
            ]

# Lifespan handler for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code: initialize database and configure logging
    # app.state.db = None
    app.state.db = CosmosDB()
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s: %(asctime)s - %(message)s')
    print("Database initialized.")
    yield
    # Shutdown code (optional)
    # Cleanup database connection
    app.state.db = None

app = FastAPI(lifespan=lifespan)

# Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Azure AD Authentication (Mocked for example)
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    tokenUrl="https://login.microsoftonline.com/common/oauth2/v2.0/token"
)

async def validate_tokenx(token: str = Depends(oauth2_scheme)):
    # In production, implement proper token validation
    logging.debug(f"Received token (mock validation): {token}")    
    return {"sub": "user123", "name": "Test User"}  # Mocked user data

async def validate_token(token: str = None):
    # In production, implement proper token validation
    logging.debug(f"Received token (mock validation): {token}")
    return {"sub": "user123", "name": "Test User"}  # Mocked user data

from openai import AsyncAzureOpenAI

# Azure OpenAI Client
async def get_openai_client():
    azure_credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        azure_credential, "https://cognitiveservices.azure.com/.default"
    )
    
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
         logging.error("AZURE_OPENAI_ENDPOINT environment variable not set!")
         # Handle error appropriately, maybe raise an exception or return None
         raise ValueError("Azure OpenAI endpoint is not configured.")

    return AsyncAzureOpenAI(
        api_version="2024-05-01-preview", # Use a specific, non-preview version if possible
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider
    )


def write_log(path, log_entry):
    # check if the file exists if not create it
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("")
    # append the log entry to a file
    with open(path, "a") as f:
        try:
            f.write(f"{json.dumps(log_entry)}\n")
        except Exception as e:
            # TODO: better handling of the error
            log_entry["content"] = f"Error writing log entry: {str(e)}"
            f.write(f"{json.dumps(log_entry)}\n")



def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def get_agent_icon(agent_name) -> str:
    if agent_name == "MagenticOneOrchestrator":
        agent_icon = "🎻"
    elif agent_name == "WebSurfer":
        agent_icon = "🏄‍♂️"
    elif agent_name == "Coder":
        agent_icon = "👨‍💻"
    elif agent_name == "FileSurfer":
        agent_icon = "📂"
    elif agent_name == "Executor":
        agent_icon = "💻"
    elif agent_name == "user":
        agent_icon = "👤"
    else:
        agent_icon = "🤖"
    return agent_icon

async def summarize_plan(plan, client):
    prompt = "You are a project manager."
    text = f"""Summarize the plan for each agent into single-level only bullet points.

    Plan:
    {plan}
    """
    
    from autogen_core.models import UserMessage, SystemMessage
    messages = [
        UserMessage(content=text, source="user"),
        SystemMessage(content=prompt)
    ]
    result = await client.create(messages)
    # print(result.content)
    
    plan_summary = result.content
    return plan_summary
async def display_log_message(log_entry, logs_dir, session_id, user_id, conversation=None):
    # ... (existing logic to parse log_entry and create _response) ...
    _log_entry_json = log_entry
    _user_id = user_id

    _response = AutoGenMessage(
        time=get_current_time(),
        session_id=session_id,
        session_user=_user_id
        )

    # Check if the message is a TaskResult class
    if isinstance(_log_entry_json, TaskResult):
        _response.type = "TaskResult"
        _response.source = "TaskResult"
        _response.content = _log_entry_json.messages[-1].content if _log_entry_json.messages else "Task finished."
        _response.stop_reason = _log_entry_json.stop_reason
        app.state.db.store_conversation(_log_entry_json, _response, conversation)

    elif isinstance(_log_entry_json, MultiModalMessage):
        _response.type = _log_entry_json.type
        _response.source = _log_entry_json.source
        _response.content = _log_entry_json.content[0] if _log_entry_json.content else "" # text wthout image
        _response.content_image = _log_entry_json.content[1].data_uri if len(_log_entry_json.content) > 1 else None # TODO: base64 encoded image -> text / serialize

    elif isinstance(_log_entry_json, TextMessage):
        _response.type = _log_entry_json.type
        _response.source = _log_entry_json.source
        _response.content = _log_entry_json.content

    elif isinstance(_log_entry_json, ToolCallExecutionEvent):
        _response.type = _log_entry_json.type
        _response.source = _log_entry_json.source
        _response.content = _log_entry_json.content[0].content if _log_entry_json.content else "" # tool execution

    elif isinstance(_log_entry_json, ToolCallRequestEvent):
        # _models_usage = _log_entry_json.models_usage
        _response.type = _log_entry_json.type
        _response.source = _log_entry_json.source
        _response.content = _log_entry_json.content[0].arguments if _log_entry_json.content else "" # tool execution

    else:
        _response.type = "Unknown"
        _response.source = "System"
        _response.content = f"Received unknown log entry type: {type(_log_entry_json)}"
        logging.warning(f"Unknown log entry type received: {type(_log_entry_json)}")


    try:
        # Save message using CRUD operation
        crud.save_message(
                id=str(uuid.uuid4()), # Ensure ID is string if needed by DB
                user_id=_user_id,
                session_id=session_id,
                message=_response.to_json(),
                agents=None, # Populate if available/needed
                run_mode_locally=None, # Populate if available/needed
                timestamp=_response.time
            )
        logging.debug(f"Saved message for session {session_id}, source {_response.source}")
    except Exception as e:
        logging.error(f"Failed to save message for session {session_id}: {e}", exc_info=True)
        # Decide if you want to surface this error to the stream

    return _response



# Azure Services Setup (Mocked for example)
blob_service_client = BlobServiceClient.from_connection_string(
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;" + \
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;" + \
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

# Get tracer instance for manual spans (optional)
tracer = get_tracer(__name__)
# Chat Endpoint
@app.post("/chat")
async def chat_endpoint(
    message: schemas.ChatMessageCreate,
    user: dict = Depends(validate_token)
):
    # ...existing code...
    mock_response = "This is a mock AI response (Markdown formatted)."
    # Log the user message.
    crud.save_message(
        user_id=user["sub"],
        session_id="session_direct",  # or generate a session id if needed
        message={"content": message.content, "role": "user"}
    )
    # Log the AI response message.
    response = {
        "time": get_current_time(),
        "type": "Muj",
        "source": "MagenticOneOrchestrator",
        "content": mock_response,
        "stop_reason": None,
        "models_usage": None,
        "content_image": None,
    }
    crud.save_message(
        user_id=user["sub"],
        session_id="session_direct",
        message=response
    )

    return Response(content=json.dumps(response), media_type="application/json")


# Chat Endpoint
@app.post("/start", response_model=schemas.ChatMessageResponse)
async def chat_endpoint(
    message: schemas.ChatMessageCreate,
    user: dict = Depends(validate_token)
):
     with tracer.start_as_current_span("start_chat_request") as span:
        _user_id = message.user_id if message.user_id else user["sub"]
        logging.info(f"Starting new chat for user: {_user_id}")
        span.set_attribute("user_id", _user_id) # Add attributes to span

        try:
            _agents = json.loads(message.agents) if message.agents else MAGENTIC_ONE_DEFAULT_AGENTS
            _session_id = generate_session_name()
            logging.info(f"Generated session ID: {_session_id}")
            span.set_attribute("session_id", _session_id)
            span.set_attribute("num_agents", len(_agents))

            # Save the initial user message
            conversation = crud.save_message(
                id=str(uuid.uuid4()),
                user_id=_user_id,
                session_id=_session_id,
                message={"content": message.content, "role": "user"},
                agents=_agents,
                run_mode_locally=False, # Assuming default, adjust if needed
                timestamp=get_current_time()
            )
            logging.info(f"Initial message saved for session: {_session_id}")

            # Return session_id as the conversation identifier
            db_message = schemas.ChatMessageResponse(
                id=str(uuid.uuid4()), # This seems like a response ID, not conversation ID
                content=message.content,
                response=_session_id, # This is the key identifier
                timestamp=get_current_time(),
                user_id=_user_id,
                # orm_mode=True # Deprecated in Pydantic v2, use model_config
                model_config = schemas.ConfigDict(from_attributes=True)
            )
            span.set_attribute("app.status", "success")
            return db_message
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in agents data: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("app.status", "error")
            raise HTTPException(status_code=400, detail=f"Invalid agents JSON: {e}")
        except Exception as e:
            logging.error(f"Error starting chat session: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("app.status", "error")
            raise HTTPException(status_code=500, detail=f"Internal server error starting chat: {e}")



# Streaming Chat Endpoint
@app.get("/chat-stream")
async def chat_stream(
    session_id: str = Query(...),
    user_id: str = Query(...),
    # db: Session = Depends(get_db),
    user: dict = Depends(validate_token)
):
    # Start a new span for this streaming request
    with tracer.start_as_current_span("chat_stream_request") as span:
        logging.info(f"Initiating chat stream for session: {session_id}, user: {user_id}")
        span.set_attribute("session_id", session_id)
        span.set_attribute("user_id", user_id)

        logs_dir="./logs"
        try:
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
                logging.info(f"Created logs directory: {logs_dir}")

            # Fetch conversation details
            conversation = crud.get_conversation(user_id, session_id)
            if not conversation or not conversation.get("messages"):
                logging.error(f"Conversation not found or empty for session: {session_id}, user: {user_id}")
                span.set_attribute("app.error", "ConversationNotFound")
                raise HTTPException(status_code=404, detail="Conversation not found or is empty.")

            first_message = conversation["messages"][0]
            task = first_message.get("content")
            if not task:
                 logging.error(f"Task content missing in first message for session: {session_id}")
                 span.set_attribute("app.error", "TaskMissing")
                 raise HTTPException(status_code=400, detail="Task content missing in conversation.")

            logging.info(f"Retrieved task for session {session_id}: {task[:100]}...") # Log truncated task
            span.set_attribute("app.task_length", len(task))

            _run_locally = conversation.get("run_mode_locally", False)
            _agents = conversation.get("agents", MAGENTIC_ONE_DEFAULT_AGENTS)
            span.set_attribute("app.run_locally", _run_locally)
            span.set_attribute("app.num_agents", len(_agents))

            # Initialize MagenticOne (SDK calls within this will be traced)
            magentic_one = MagenticOneHelper(logs_dir=logs_dir, save_screenshots=False, run_locally=_run_locally)
            await magentic_one.initialize(agents=_agents, session_id=session_id)
            logging.info(f"MagenticOne initialized for session: {session_id}")

            # Start the main processing stream (SDK calls within this will be traced)
            stream, cancellation_token = magentic_one.main(task=task)
            logging.info(f"MagenticOne main process started for session: {session_id}")

            # Store cancellation token (Consider a more robust distributed cache/store)
            session_data[session_id] = {"cancellation_token": cancellation_token}

        except HTTPException as http_exc:
            # Don't record HTTPException again if already raised
            span.set_attribute("app.status", "error")
            raise http_exc # Re-raise known HTTP exceptions
        except Exception as e:
            logging.error(f"Error setting up chat stream for session {session_id}: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("app.status", "error")
            raise HTTPException(status_code=500, detail=f"Failed to initialize chat stream: {e}")

        # --- Event Generator for Streaming Response ---
        async def event_generator(stream_source):
            # This part runs *after* the initial setup span has finished,
            # but operations within MagenticOneHelper should still generate their own spans.
            logging.debug(f"Starting event generator for session: {session_id}")
            message_count = 0
            try:
                async for log_entry in stream_source:
                    message_count += 1
                    logging.debug(f"Stream received item {message_count} for session {session_id}: {type(log_entry)}")
                    try:
                        # Process and format the log entry (SDK calls inside display_log_message might be traced)
                        json_response = await display_log_message(log_entry=log_entry, logs_dir=logs_dir, session_id=session_id, client=getattr(magentic_one, 'client', None), user_id=user_id)
                        yield f"data: {json.dumps(json_response.to_json())}\n\n"
                    except Exception as display_err:
                         logging.error(f"Error processing/displaying log entry for session {session_id}: {display_err}", exc_info=True)
                         # Optionally yield an error message to the client
                         error_msg = {"error": "Failed to process message", "details": str(display_err)}
                         yield f"data: {json.dumps(error_msg)}\n\n"

                logging.info(f"Event generator finished for session {session_id} after {message_count} messages.")
                # You might want to add a final "completed" message here
                yield f"data: {json.dumps({'status': 'completed', 'session_id': session_id})}\n\n"

            except asyncio.CancelledError:
                 logging.warning(f"Stream cancelled for session: {session_id}")
                 yield f"data: {json.dumps({'status': 'cancelled', 'session_id': session_id})}\n\n"
            except Exception as gen_err:
                logging.error(f"Error during stream generation for session {session_id}: {gen_err}", exc_info=True)
                # Yield an error message to the client
                error_msg = {"error": "Streaming error occurred", "details": str(gen_err)}
                yield f"data: {json.dumps(error_msg)}\n\n"
            finally:
                 logging.debug(f"Cleaning up event generator for session: {session_id}")
                 # Clean up session data if needed
                 session_data.pop(session_id, None)


        # Return the streaming response
        # Note: The initial setup span ends here. Spans within event_generator are separate.
        span.set_attribute("app.status", "streaming") # Indicate streaming started
        return StreamingResponse(event_generator(stream), media_type="text/event-stream")

@app.get("/stop")
async def stop(session_id: str = Query(...)):
    try:
        print("Stopping session:", session_id)
        cancellation_token = session_data[session_id].get("cancellation_token")
        if (cancellation_token):
            cancellation_token.cancel()
            return {"status": "success", "message": f"Session {session_id} cancelled successfully."}
        else:
            return {"status": "error", "message": "Cancellation token not found."}
    except Exception as e:
        print(f"Error stopping session {session_id}: {str(e)}")
        return {"status": "error", "message": f"Error stopping session: {str(e)}"}

# New endpoint to retrieve all conversations with pagination.
@app.post("/conversations")
async def list_all_conversations(
    request_data: dict,
    user: dict = Depends(validate_token)
    ):
    with tracer.start_as_current_span("list_all_conversations") as span:
        target_user_id = user_id_data.user_id # Extract user_id from request body
        logging.info(f"Fetching all conversations (requested for user: {target_user_id})")
        span.set_attribute("requesting_user_id", user.get("sub")) # Log who requested it
        span.set_attribute("target_user_id", target_user_id) # Log which user's data was requested (even if fetching all)
        try:
            # conversations = fetch_user_conversatons(user_id=target_user_id) # Fetch for specific user
            conversations = fetch_user_conversatons(user_id=None) # Fetch all conversations as per original code
            span.set_attribute("num_conversations_fetched", len(conversations))
            span.set_attribute("app.status", "success")
            return conversations
        except Exception as e:
            logging.error(f"Error retrieving conversations: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("app.status", "error")
            # Return empty list or raise appropriate HTTP error
            # raise HTTPException(status_code=500, detail="Failed to retrieve conversations")
            return [] # Returning empty list as per original code

# New endpoint to retrieve conversations for the authenticated user.
@app.post("/conversations/user")
async def list_user_conversation(request_data: dict = None, user: dict = Depends(validate_token)):
    session_id = request_data.get("session_id") if request_data else None
    user_id = request_data.get("user_id") if request_data else None
    conversations = app.state.db.fetch_user_conversation(user_id, session_id=session_id)
    return conversations

@app.post("/conversations/delete")
async def delete_conversation(session_id: str = Query(...), user_id: str = Query(...), user: dict = Depends(validate_token)):
    logger = logging.getLogger("delete_conversation")
    logger.setLevel(logging.INFO)
    logger.info(f"Deleting conversation with session_id: {session_id} for user_id: {user_id}")
    try:
        # result = crud.delete_conversation(user["sub"], session_id)
        result = app.state.db.delete_user_conversation(user_id=user_id, session_id=session_id)
        if result:
            logger.info(f"Conversation {session_id} deleted successfully.")
            return {"status": "success", "message": f"Conversation {session_id} deleted successfully."}
        else:
            logger.warning(f"Conversation {session_id} not found.")
            return {"status": "error", "message": f"Conversation {session_id} not found."}
    except Exception as e:
        logger.error(f"Error deleting conversation {session_id}: {str(e)}")
        return {"status": "error", "message": f"Error deleting conversation: {str(e)}"}
    
@app.get("/health")
async def health_check():
    logger = logging.getLogger("health_check")
    logger.setLevel(logging.INFO)
    logger.info("Health check endpoint called")
    with tracer.start_as_current_span("health_check"):
        logging.debug("Health check endpoint called")
        return {"status": "healthy"}

@app.post("/upload")
async def upload_files(indexName: str = Form(...), files: List[UploadFile] = File(...)):
     with tracer.start_as_current_span("upload_files") as span:
        logging.info(f"Upload request received for index: {indexName}, files: {[f.filename for f in files]}")
        span.set_attribute("index_name", indexName)
        span.set_attribute("num_files", len(files))
        try:
            # Calls within process_upload_and_index might be auto-instrumented if they use Azure SDKs
            aisearch.process_upload_and_index(indexName, files)
            logging.info(f"Successfully processed upload for index: {indexName}")
            span.set_attribute("app.status", "success")
            return {"status": "success", "filenames": [f.filename for f in files]}
        except Exception as err:
            logging.error(f"Error processing upload and index for {indexName}: {err}", exc_info=True)
            span.record_exception(err)
            span.set_attribute("app.status", "error")
            # Return error status, avoid raising HTTPException if client expects JSON status
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"Error processing upload: {err}"}
            )

from fastapi import HTTPException

@app.get("/teams")
async def get_teams_api():
    try:
        teams = app.state.db.get_teams()
        return teams
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving teams: {str(e)}")

@app.get("/teams/{team_id}")
async def get_team_api(team_id: str):
    try:
        team = app.state.db.get_team(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        return team
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving team: {str(e)}")

@app.post("/teams")
async def create_team_api(team: dict):
    try:
        team["agents"] = MAGENTIC_ONE_DEFAULT_AGENTS
        response = app.state.db.create_team(team)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating team: {str(e)}")

@app.put("/teams/{team_id}")
async def update_team_api(team_id: str, team: dict):
    logger = logging.getLogger("update_team_api")
    logger.info(f"Updating team with ID: {team_id} and data: {team}")
    try:
        response = app.state.db.update_team(team_id, team)
        if "error" in response:
            logger.error(f"Error updating team: {response['error']}")
            raise HTTPException(status_code=404, detail=response["error"])
        return response
    except Exception as e:
        logger.error(f"Error updating team: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating team: {str(e)}")

@app.delete("/teams/{team_id}")
async def delete_team_api(team_id: str):
    try:
        response = app.state.db.delete_team(team_id)
        if "error" in response:
            raise HTTPException(status_code=404, detail=response["error"])
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting team: {str(e)}")