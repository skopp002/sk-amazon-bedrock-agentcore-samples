# Gateway Interceptor Update - MCP Protocol Compliance

**Date:** December 19, 2024  
**Status:** ✅ **COMPLETE**

## Overview

Updated the AgentCore Gateway interceptor to follow the proper MCP (Model Context Protocol) structure for extracting JWT tokens and user principals, based on the reference implementation from AWS samples.

**Reference:** [token-exchange-at-request-interceptor](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/02-AgentCore-gateway/14-token-exchange-at-request-interceptor/token-exchange-at-request-interceptor.ipynb)

## Changes Made

### 1. Updated Event Structure Handling

**Before:**
```python
# Incorrectly accessed event directly
headers = event.get('headers', {})
body = event.get('body', '{}')
```

**After:**
```python
# Correctly extracts from MCP structure
mcp_data = event.get('mcp', {})
gateway_request = mcp_data.get('gatewayRequest', {})
headers = gateway_request.get('headers', {})
body = gateway_request.get('body', {})
```

### 2. Updated Response Format

**Before:**
```python
# Returned standard Lambda response
return event  # or modified event
```

**After:**
```python
# Returns proper MCP interceptor format
return {
    "interceptorOutputVersion": "1.0",
    "mcp": {
        "transformedGatewayRequest": {
            "headers": transformed_headers,
            "body": transformed_body
        }
    }
}
```

### 3. Simplified Token Extraction

**Before:**
```python
def extract_bearer_token(event: Dict[str, Any]) -> Optional[str]:
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization')
    # ...
```

**After:**
```python
def extract_bearer_token_from_mcp(event: Dict[str, Any]) -> Optional[str]:
    mcp_data = event.get('mcp', {})
    gateway_request = mcp_data.get('gatewayRequest', {})
    headers = gateway_request.get('headers', {})
    auth_header = headers.get('Authorization')
    # ...
```

### 4. Renamed Functions for Clarity

- `extract_user_identity()` → `extract_user_principal()` (more accurate terminology)
- `extract_bearer_token()` → `extract_bearer_token_from_mcp()` (explicit about MCP structure)

### 5. Removed Unused Code

Removed the following functions that were not needed for the current implementation:
- `check_tool_permission()` - Tool-level permissions not required (Lake Formation handles RLS)
- `request_interceptor()` - Consolidated into main `lambda_handler()`
- `response_interceptor()` - Not needed for current use case

## OAuth Flow

The complete OAuth token flow through the system:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Streamlit UI (streamlit_app.py)                             │
│    - User authenticates with Cognito                            │
│    - Gets OAuth2 access token (client_credentials flow)         │
│    - Passes token in payload: {"bearer_token": "<token>"}       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Lakehouse Agent (lakehouse_agent.py)                         │
│    - Receives bearer_token from payload                         │
│    - Creates MCP client with Authorization header               │
│    - Passes to Gateway: {"Authorization": "Bearer <token>"}     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. AgentCore Gateway                                            │
│    - Receives request with Authorization header                 │
│    - Wraps in MCP structure:                                    │
│      {                                                           │
│        "mcp": {                                                  │
│          "gatewayRequest": {                                    │
│            "headers": {"Authorization": "Bearer <token>"},      │
│            "body": {...}                                        │
│          }                                                       │
│        }                                                         │
│      }                                                           │
│    - Invokes interceptor Lambda                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Gateway Interceptor (lambda_function.py) ⭐ UPDATED          │
│    - Extracts token from event['mcp']['gatewayRequest']         │
│    - Validates JWT against Cognito                              │
│    - Extracts user principal (email/username) from claims       │
│    - Adds X-User-Identity header                                │
│    - Returns transformed request in MCP format                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. MCP Lakehouse Server (server.py)                             │
│    - Receives request with X-User-Identity header               │
│    - Extracts user principal from header                        │
│    - Uses principal for Lake Formation session tags             │
│    - Enforces row-level security via Lake Formation             │
│    - Returns filtered data to user                              │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### JWT Validation
- Validates JWT tokens against Cognito public keys
- Verifies token signature, audience, and issuer
- Caches Cognito public keys for performance

### Principal Extraction
Extracts user principal from JWT claims in priority order:
1. `email` (preferred for user identification)
2. `username`
3. `cognito:username`
4. `sub` (user ID as fallback)

### Headers Added
The interceptor adds the following headers for the MCP server:
- `X-User-Identity`: User principal (email/username)
- `X-User-Scopes`: Comma-separated list of OAuth scopes
- `Accept`: application/json
- `Content-Type`: application/json

### Context Enrichment
Also adds user context to request body if it contains `params.arguments`:
```json
{
  "params": {
    "arguments": {
      "context": {
        "user_id": "user@example.com",
        "scopes": ["lakehouse-api/claims.query"]
      }
    }
  }
}
```

## Testing

To test the updated interceptor:

### 1. Deploy the Updated Interceptor
```bash
cd gateway-setup/interceptor
zip lambda_function.zip lambda_function.py
aws lambda update-function-code \
  --function-name <interceptor-function-name> \
  --zip-file fileb://lambda_function.zip
```

### 2. Test with Streamlit UI
```bash
cd streamlit-ui
streamlit run streamlit_app.py
```

1. Enter Cognito configuration
2. Click "Get Bearer Token"
3. Enter Runtime ARN
4. Send a query (e.g., "Show me all my claims")

### 3. Check CloudWatch Logs
Look for these log messages in the interceptor Lambda logs:
```
✅ Bearer token extracted from MCP gateway request
✅ Extracted user principal: user@example.com
👤 User: user@example.com, Scopes: [...]
✅ Request authorized for user: user@example.com
📤 Returning transformed request
```

## Configuration

The interceptor requires these environment variables:
- `COGNITO_REGION`: AWS region for Cognito (e.g., us-east-1)
- `COGNITO_USER_POOL_ID`: Cognito User Pool ID
- `COGNITO_APP_CLIENT_ID`: Cognito App Client ID

These are set during Gateway creation via `create_gateway.py`.

## Security

### JWT Validation
- Validates token signature using Cognito public keys
- Verifies audience matches the configured client ID
- Verifies issuer matches the Cognito User Pool
- Checks token expiration

### Error Handling
- Returns 401 for missing or invalid tokens
- Returns 401 for missing user principal in claims
- Returns 500 for internal errors
- Logs all errors with stack traces

### No Secrets in Code
- Uses Cognito public keys (not secrets)
- No hardcoded credentials
- Configuration via environment variables

## Compatibility

### Backward Compatibility
The updated interceptor maintains compatibility with:
- Existing MCP server implementation
- Lake Formation row-level security
- Current authentication flow

### Breaking Changes
None - this is a bug fix to follow the correct MCP protocol.

## Next Steps

1. **Deploy to Production**
   - Update the interceptor Lambda function
   - Test with production Cognito configuration
   - Monitor CloudWatch logs

2. **Verify End-to-End Flow**
   - Test Streamlit → Agent → Gateway → MCP server
   - Verify user principal is correctly extracted
   - Confirm Lake Formation RLS is working

3. **Monitor Performance**
   - Check Lambda execution time
   - Monitor Cognito public key cache hits
   - Review CloudWatch metrics

## References

- [AgentCore Gateway MCP Protocol](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/01-tutorials/02-AgentCore-gateway)
- [Token Exchange at Request Interceptor](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/02-AgentCore-gateway/14-token-exchange-at-request-interceptor/token-exchange-at-request-interceptor.ipynb)
- [Lake Formation Row-Level Security](https://docs.aws.amazon.com/lake-formation/latest/dg/row-col-filtering.html)

## Conclusion

The interceptor now correctly follows the AgentCore Gateway MCP protocol for:
- ✅ Extracting JWT tokens from MCP gateway request structure
- ✅ Validating tokens against Cognito
- ✅ Extracting user principals from JWT claims
- ✅ Returning responses in proper MCP format
- ✅ Passing user identity to MCP server for Lake Formation RLS

The OAuth flow is complete and secure from Streamlit UI through to the MCP server with Lake Formation row-level security enforcement.
