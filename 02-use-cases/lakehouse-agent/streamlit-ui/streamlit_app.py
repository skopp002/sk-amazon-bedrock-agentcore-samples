"""
Streamlit UI for Health Lakehouse Data Agent with Cognito OAuth
"""
import streamlit as st
import requests
import json
import uuid
from typing import Optional

st.set_page_config(page_title="Lakehouse Data Assistant", page_icon="🏥", layout="wide")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "bearer_token" not in st.session_state:
    st.session_state.bearer_token = None
if "runtime_arn" not in st.session_state:
    st.session_state.runtime_arn = ""

def get_bearer_token(cognito_domain: str, client_id: str, client_secret: str, scope: str) -> Optional[str]:
    """Get OAuth2 bearer token from Cognito"""
    token_url = f"{cognito_domain}/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }
    try:
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        st.error(f"Failed to get token: {e}")
        return None

def invoke_agent(runtime_arn: str, prompt: str, bearer_token: str, region: str) -> str:
    """Invoke AgentCore Runtime with bearer token"""
    import boto3
    import json
    
    try:
        # Create AgentCore client
        client = boto3.client('bedrock-agentcore', region_name=region)
        
        # Prepare payload
        payload = {
            "prompt": prompt,
            "bearer_token": bearer_token
        }
        
        # Invoke the runtime
        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=st.session_state.session_id,
            payload=json.dumps(payload).encode('utf-8')
        )
        
        # Parse response
        if 'payload' in response:
            response_payload = json.loads(response['payload'].read().decode('utf-8'))
            if 'content' in response_payload:
                return response_payload['content']
            return str(response_payload)
        
        return "No response from agent"
        
    except Exception as e:
        return f"Error: {str(e)}"

# Sidebar configuration
with st.sidebar:
    st.title("🏥 Claims Assistant")
    st.markdown("---")

    with st.expander("🔐 Cognito Configuration", expanded=not st.session_state.bearer_token):
        cognito_domain = st.text_input("Cognito Domain", placeholder="https://...")
        client_id = st.text_input("Client ID")
        client_secret = st.text_input("Client Secret", type="password")
        scope = st.text_input("Scope", value="lakehouse-api/claims.query")

        if st.button("🔑 Get Bearer Token", use_container_width=True):
            if all([cognito_domain, client_id, client_secret, scope]):
                token = get_bearer_token(cognito_domain, client_id, client_secret, scope)
                if token:
                    st.session_state.bearer_token = token
                    st.success("✅ Token obtained!")
                    st.rerun()
            else:
                st.warning("⚠️ Fill in all fields")

    if st.session_state.bearer_token:
        st.success("🔓 Authenticated")
    else:
        st.warning("🔒 Not authenticated")

    st.markdown("---")

    with st.expander("⚙️ Runtime Configuration", expanded=True):
        runtime_arn = st.text_input("Runtime ARN", value=st.session_state.runtime_arn)
        st.session_state.runtime_arn = runtime_arn
        region = st.text_input("AWS Region", value="us-east-1")

    st.markdown("---")
    st.markdown("### 💡 Example Queries")
    examples = [
        "Show me all my claims",
        "What's the status of CLM-2024-001?",
        "Get my claims summary",
        "Show pending claims"
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex[:15]}", use_container_width=True):
            st.session_state.example_prompt = ex

# Main interface
st.title("🏥 Health Lakehouse Data Assistant")
st.markdown("Ask me about your lakehouse data!")

if not st.session_state.bearer_token:
    st.warning("⚠️ Please authenticate in the sidebar first!")
    st.stop()

if not st.session_state.runtime_arn:
    st.warning("⚠️ Please enter your Runtime ARN in the sidebar!")
    st.stop()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle input
prompt = st.session_state.pop("example_prompt", None) or st.chat_input("Ask about your claims...")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        response = invoke_agent(
            st.session_state.runtime_arn,
            prompt,
            st.session_state.bearer_token,
            region
        )
        try:
            data = json.loads(response)
            response = data.get("content", response)
        except:
            pass
        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
