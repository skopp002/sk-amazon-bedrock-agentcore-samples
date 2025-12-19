"""
AgentCore Gateway Interceptor for Health Lakehouse Data

This Lambda function acts as a Gateway Interceptor to:
1. Validate JWT bearer tokens from incoming requests
2. Extract user identity (email) from JWT claims
3. Enforce fine-grained access control based on JWT scopes
4. Add user identity to request headers for downstream MCP server
5. Filter tools based on user permissions

The interceptor implements both request and response interceptors.
"""

import json
import logging
import os
import re
from typing import Dict, Any, List, Optional
import urllib.request
import base64
from jose import jwt, JWTError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cognito configuration (from environment variables)
COGNITO_REGION = os.environ.get('COGNITO_REGION', 'us-east-1')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_APP_CLIENT_ID = os.environ.get('COGNITO_APP_CLIENT_ID', '')
COGNITO_ISSUER = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}'

# Cache for Cognito public keys
_jwks = None


def get_cognito_public_keys() -> Dict[str, Any]:
    """
    Fetch Cognito public keys for JWT validation.

    Returns:
        Dictionary of public keys
    """
    global _jwks

    if _jwks is not None:
        return _jwks

    try:
        jwks_url = f'{COGNITO_ISSUER}/.well-known/jwks.json'
        with urllib.request.urlopen(jwks_url) as response:
            _jwks = json.loads(response.read())
            logger.info("Successfully fetched Cognito public keys")
            return _jwks
    except Exception as e:
        logger.error(f"Error fetching Cognito public keys: {str(e)}")
        raise


def validate_and_decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate JWT token and decode claims.

    Args:
        token: JWT bearer token

    Returns:
        Decoded JWT claims or None if invalid
    """
    try:
        # Get Cognito public keys
        jwks = get_cognito_public_keys()

        # Decode token header to get key ID
        unverified_headers = jwt.get_unverified_header(token)
        kid = unverified_headers.get('kid')

        # Find the correct public key
        key = None
        for k in jwks.get('keys', []):
            if k.get('kid') == kid:
                key = k
                break

        if not key:
            logger.error("Public key not found for token")
            return None

        # Validate and decode JWT
        claims = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=COGNITO_APP_CLIENT_ID,
            issuer=COGNITO_ISSUER
        )

        logger.info(f"Successfully validated JWT for user: {claims.get('username', claims.get('sub'))}")
        return claims

    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error validating JWT: {str(e)}")
        return None


def extract_bearer_token(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract bearer token from Authorization header.

    Args:
        event: Lambda event

    Returns:
        Bearer token or None if not found
    """
    headers = event.get('headers', {})

    # Check standard Authorization header
    auth_header = headers.get('Authorization') or headers.get('authorization')

    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.replace('Bearer ', '')

    logger.warning("Bearer token not found in request")
    return None


def extract_user_identity(claims: Dict[str, Any]) -> Optional[str]:
    """
    Extract user identity (email) from JWT claims.

    Args:
        claims: Decoded JWT claims

    Returns:
        User email or None
    """
    # Try multiple claim fields
    user_id = (
        claims.get('email') or
        claims.get('username') or
        claims.get('cognito:username') or
        claims.get('sub')
    )

    if user_id:
        logger.info(f"Extracted user identity: {user_id}")
        return user_id

    logger.warning("User identity not found in JWT claims")
    return None


def get_user_scopes(claims: Dict[str, Any]) -> List[str]:
    """
    Extract OAuth scopes from JWT claims.

    Args:
        claims: Decoded JWT claims

    Returns:
        List of scopes
    """
    # Scopes can be in 'scope' claim (space-separated) or 'cognito:groups'
    scope_string = claims.get('scope', '')
    scopes = scope_string.split() if scope_string else []

    # Add groups as scopes
    groups = claims.get('cognito:groups', [])
    scopes.extend(groups)

    logger.info(f"User scopes: {scopes}")
    return scopes


def check_tool_permission(tool_name: str, scopes: List[str]) -> bool:
    """
    Check if user has permission to access a tool based on scopes.

    Tool permissions mapping:
    - claims/query: query_claims, get_claim_details, get_claims_summary
    - claims/submit: submit_claim
    - claims/update: update_claim_status
    - claims/approve: update_claim_status (for approval/denial)

    Args:
        tool_name: Name of the tool
        scopes: User's OAuth scopes

    Returns:
        True if user has permission, False otherwise
    """
    # Define tool-to-scope mapping
    tool_permissions = {
        'query_claims': ['claims/query', 'claims/read'],
        'get_claim_details': ['claims/query', 'claims/read'],
        'get_claims_summary': ['claims/query', 'claims/read'],
        'submit_claim': ['claims/submit', 'claims/write'],
        'update_claim_status': ['claims/update', 'claims/write', 'claims/approve']
    }

    required_scopes = tool_permissions.get(tool_name, [])

    # Check if user has any of the required scopes
    for scope in scopes:
        if scope in required_scopes:
            return True

    # Check for admin scope (has access to everything)
    if 'claims/admin' in scopes or 'admin' in scopes:
        return True

    logger.warning(f"User does not have permission to access tool: {tool_name}")
    return False


def request_interceptor(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Request interceptor - validates JWT and adds user identity to request.

    This interceptor:
    1. Extracts and validates JWT bearer token
    2. Extracts user identity and scopes
    3. Checks tool permissions
    4. Adds user identity to headers for downstream MCP server
    5. Returns error if unauthorized

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Modified event or error response
    """
    logger.info("Request interceptor invoked")
    logger.info(f"Event keys: {event.keys()}")

    try:
        # Extract bearer token
        token = extract_bearer_token(event)

        if not token:
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Unauthorized',
                    'message': 'Bearer token required'
                })
            }

        # Validate and decode JWT
        claims = validate_and_decode_jwt(token)

        if not claims:
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Unauthorized',
                    'message': 'Invalid or expired token'
                })
            }

        # Extract user identity
        user_id = extract_user_identity(claims)

        if not user_id:
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Unauthorized',
                    'message': 'User identity not found in token'
                })
            }

        # Get user scopes
        scopes = get_user_scopes(claims)

        # Check if this is a tool invocation
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)

        tool_name = body.get('tool_name') or body.get('name')

        if tool_name:
            # Check tool permission
            if not check_tool_permission(tool_name, scopes):
                return {
                    'statusCode': 403,
                    'body': json.dumps({
                        'error': 'Forbidden',
                        'message': f'Insufficient permissions to access tool: {tool_name}'
                    })
                }

        # Add user identity to headers for downstream MCP server
        if 'headers' not in event:
            event['headers'] = {}

        event['headers']['X-User-Identity'] = user_id
        event['headers']['X-User-Scopes'] = ','.join(scopes)

        # Also add to body if it's a tool request
        if isinstance(body, dict):
            if 'context' not in body:
                body['context'] = {}
            body['context']['user_id'] = user_id
            body['context']['scopes'] = scopes
            event['body'] = json.dumps(body)

        logger.info(f"Request authorized for user: {user_id}")
        return event

    except Exception as e:
        logger.error(f"Error in request interceptor: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal Server Error',
                'message': f'Error processing request: {str(e)}'
            })
        }


def response_interceptor(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Response interceptor - filters tools based on user permissions.

    This interceptor:
    1. Filters tool lists based on user scopes
    2. Removes tools the user doesn't have permission to access
    3. Returns filtered response

    Args:
        event: Lambda event with response data
        context: Lambda context

    Returns:
        Modified response
    """
    logger.info("Response interceptor invoked")

    try:
        # Extract user scopes from request headers
        headers = event.get('headers', {})
        scopes_header = headers.get('X-User-Scopes', '')
        scopes = scopes_header.split(',') if scopes_header else []

        # Extract response body
        response_body = event.get('responseBody', {})
        if isinstance(response_body, str):
            response_body = json.loads(response_body)

        # Check if this is a tools/list response
        if 'tools' in response_body:
            # Filter tools based on user permissions
            filtered_tools = []
            for tool in response_body.get('tools', []):
                tool_name = tool.get('name')
                if tool_name and check_tool_permission(tool_name, scopes):
                    filtered_tools.append(tool)
                else:
                    logger.info(f"Filtered out tool: {tool_name} for user scopes: {scopes}")

            response_body['tools'] = filtered_tools
            event['responseBody'] = json.dumps(response_body)

            logger.info(f"Filtered tools list: {len(filtered_tools)} tools accessible")

        return event

    except Exception as e:
        logger.error(f"Error in response interceptor: {str(e)}")
        # Return original event on error
        return event


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Gateway interceptor.

    Routes to request or response interceptor based on event type.

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Interceptor response
    """
    logger.info(f"Gateway interceptor invoked")

    # Determine interceptor type based on event structure
    if 'responseBody' in event:
        # This is a response interceptor call
        return response_interceptor(event, context)
    else:
        # This is a request interceptor call
        return request_interceptor(event, context)
