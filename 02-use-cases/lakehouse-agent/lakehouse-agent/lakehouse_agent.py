#!/usr/bin/env python3
"""
Health Lakehouse Data Agent using Strands and AgentCore Gateway
Connects to Gateway tools for querying and managing lakehouse data with OAuth-based access control
"""
import os
import logging
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore import BedrockAgentCoreApp
from typing import Dict, Any
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bypass tool consent for AgentCore deployment
os.environ["BYPASS_TOOL_CONSENT"] = "true"

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# System prompt for lakehouse data agent
CLAIMS_SYSTEM_PROMPT = """
You are a helpful health lakehouse data assistant. You help users with:
- Querying their lakehouse data
- Submitting new data records
- Checking data record status
- Updating data records
- Getting data summaries

You have access to tools that query an Athena database with row-level security,
meaning users can only see and manage their own claims.

Be professional, empathetic, and clear. Explain insurance terms in simple language.
When helping with claims, gather all necessary information before submission.
"""

# Gateway configuration (from environment)
GATEWAY_ARN = os.environ.get('GATEWAY_ARN', '')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"


def get_gateway_url(gateway_arn: str) -> str:
    """Convert Gateway ARN to URL using AgentCore API."""
    try:
        # Extract gateway ID from ARN
        # Format: arn:aws:bedrock-agentcore:region:account:gateway/gateway-id
        gateway_id = gateway_arn.split('/')[-1]
        
        # Get gateway details
        agentcore_client = boto3.client('bedrock-agentcore-control', region_name=AWS_REGION)
        response = agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
        gateway_url = response['gatewayUrl']
        
        logger.info(f"✅ Gateway URL: {gateway_url}")
        return gateway_url
    except Exception as e:
        logger.error(f"❌ Error getting gateway URL: {e}")
        return ''


@app.entrypoint
def handle_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle requests to the lakehouse agent.

    Args:
        payload: Request with prompt and bearer token

    Returns:
        Agent response
    """
    user_prompt = payload.get('prompt', 'Hello')
    bearer_token = payload.get('bearer_token', '')
    
    logger.info(f"📥 Received request: {user_prompt[:100]}...")
    logger.info(f"🔑 Bearer token present: {bool(bearer_token)}")

    # Get tools from Gateway if configured
    tools = []
    if GATEWAY_ARN and bearer_token:
        try:
            logger.info(f"🔗 Connecting to Gateway: {GATEWAY_ARN}")
            gateway_url = get_gateway_url(GATEWAY_ARN)
            
            if gateway_url:
                # Create auth headers with bearer token
                auth_headers = {'Authorization': f'Bearer {bearer_token}'}
                
                # Create MCP client with authentication
                mcp_client = MCPClient(
                    lambda: streamablehttp_client(gateway_url, headers=auth_headers),
                    prefix="claims"
                )
                
                # Open connection and get tools
                mcp_client.__enter__()
                tools = mcp_client.list_tools_sync()
                logger.info(f"✅ Loaded {len(tools)} tools from Gateway")
            else:
                logger.warning("⚠️  Gateway URL not available")
        except Exception as e:
            logger.error(f"❌ Error connecting to Gateway: {e}")
            # Continue without tools - agent can still respond
    else:
        logger.info("ℹ️  No Gateway configured or no bearer token - running without tools")

    # Create Bedrock model
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION
    )

    # Create agent with Gateway tools (if available)
    agent = Agent(
        model=model,
        tools=tools if tools else [],
        system_prompt=CLAIMS_SYSTEM_PROMPT
    )

    # Process request
    logger.info("⏳ Processing request...")
    response = agent(user_prompt)
    logger.info("✅ Request processed")

    # Extract response content
    response_text = ""
    if hasattr(response, 'message') and 'content' in response.message:
        for content in response.message['content']:
            if isinstance(content, dict) and 'text' in content:
                response_text += content['text']
    else:
        response_text = str(response)

    return {
        "content": response_text,
        "tool_calls": len(response.tool_calls) if hasattr(response, 'tool_calls') else 0
    }

if __name__ == "__main__":
    app.run()
