"""
MCP Server for Health Lakehouse Data - Production Security with Lake Formation

This MCP server provides tools for querying and managing health lakehouse data
with enterprise-grade row-level security enforced by AWS Lake Formation.

Security Architecture:
- OAuth authentication (Cognito JWT tokens)
- User identity extraction from Gateway interceptor
- Lake Formation session tag-based row-level security
- No SQL string interpolation (eliminates SQL injection risk)

IMPORTANT: This server ONLY supports Lake Formation security mode.
Application-level SQL filtering has been removed for security reasons.

Configuration:
- Reads from config.py/SSM Parameter Store
- Requires SECURITY_MODE=lakeformation
- Requires RLS_ROLE_ARN to be set
"""

import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
import logging
from typing import Any, Dict
from bedrock_agentcore import BedrockAgentCoreApp

# PRODUCTION ONLY: Use Lake Formation row-level security
from athena_tools_secure import SecureAthenaClaimsTools as AthenaTools

print(f"🔒 Using Lake Formation row-level security (production mode)")

# Configure logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

# Initialize Bedrock AgentCore App for MCP server
app = BedrockAgentCoreApp()

# Global Athena tools instance
athena_tools = None


def get_athena_tools():
    """
    Get or create Athena tools instance with Lake Formation security.

    Raises:
        ValueError: If Lake Formation is not properly configured
    """
    global athena_tools
    if athena_tools is None:
        logger.info(f"Initializing Athena tools with Lake Formation RLS...")
        logger.info(f"  Region: {config.AWS_REGION}")
        logger.info(f"  Database: {config.ATHENA_DATABASE_NAME}")
        logger.info(f"  S3 Output: {config.S3_OUTPUT_LOCATION}")

        # Validate Lake Formation configuration
        if not config.RLS_ROLE_ARN:
            raise ValueError(
                "❌ RLS_ROLE_ARN not set in configuration.\n"
                "   Lake Formation is required for production security.\n"
                "   Run: python athena-setup/setup_lake_formation.py\n"
                "   Then add RLS_ROLE_ARN to SSM Parameter Store:\n"
                "   aws ssm put-parameter --name lh_rls_role_arn --value 'arn:aws:iam::ACCOUNT:role/ROLE_NAME' --type String"
            )

        logger.info(f"  RLS Role: {config.RLS_ROLE_ARN}")

        # Initialize with Lake Formation security
        athena_tools = AthenaTools(
            region=config.AWS_REGION,
            database_name=config.ATHENA_DATABASE_NAME,
            s3_output_location=config.S3_OUTPUT_LOCATION,
            rls_role_arn=config.RLS_ROLE_ARN
        )

        logger.info(f"✅ Athena tools initialized with Lake Formation RLS")

    return athena_tools


def extract_user_identity(payload: Dict[str, Any]) -> str:
    """Extract user identity from request payload."""
    headers = payload.get('headers', {})
    user_id = headers.get('X-User-Identity') or headers.get('x-user-identity')

    if user_id:
        logger.info(f"Extracted user identity: {user_id}")
        return user_id

    context = payload.get('context', {})
    user_id = context.get('user_id') or context.get('user_identity')

    if user_id:
        logger.info(f"Extracted user identity from context: {user_id}")
        return user_id

    # Fallback to test user for development
    if config.LOCAL_DEVELOPMENT:
        logger.warning("Using test user for local development")
        return config.TEST_USER_1

    logger.error("User identity not found in request")
    return None


@app.tool(
    name="query_claims",
    description="Query health lakehouse data for the authenticated user with optional filters"
)
def query_claims(
    claim_status: str = None,
    claim_type: str = None,
    start_date: str = None,
    end_date: str = None
) -> Dict[str, Any]:
    """Query lakehouse data for the authenticated user."""
    try:
        user_id = app.get_context().get('user_id', config.TEST_USER_1)
        filters = {k: v for k, v in {
            'claim_status': claim_status,
            'claim_type': claim_type,
            'start_date': start_date,
            'end_date': end_date
        }.items() if v is not None}

        tools = get_athena_tools()
        return tools.query_claims(user_id, filters if filters else None)

    except Exception as e:
        logger.error(f"Error in query_claims: {str(e)}")
        return {"success": False, "error": str(e)}


@app.tool(
    name="get_claim_details",
    description="Get detailed information about a specific claim by ID"
)
def get_claim_details(claim_id: str) -> Dict[str, Any]:
    """Get details of a specific claim."""
    try:
        user_id = app.get_context().get('user_id', config.TEST_USER_1)
        tools = get_athena_tools()
        return tools.get_claim_details(user_id, claim_id)

    except Exception as e:
        logger.error(f"Error in get_claim_details: {str(e)}")
        return {"success": False, "error": str(e)}


@app.tool(
    name="get_claims_summary",
    description="Get summary statistics of all claims for the authenticated user"
)
def get_claims_summary() -> Dict[str, Any]:
    """Get claims summary for the user."""
    try:
        user_id = app.get_context().get('user_id', config.TEST_USER_1)
        tools = get_athena_tools()
        return tools.get_claims_summary(user_id)

    except Exception as e:
        logger.error(f"Error in get_claims_summary: {str(e)}")
        return {"success": False, "error": str(e)}


@app.entrypoint
def handle_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming requests to the MCP server."""
    try:
        logger.info(f"Received request")

        user_id = extract_user_identity(payload)

        if not user_id:
            return {
                "success": False,
                "error": "User identity not found",
                "message": "Authentication required"
            }

        # Store user_id in context for tools
        app.set_context({'user_id': user_id})

        return {
            "success": True,
            "message": "Request processed",
            "user_id": user_id,
            "security_mode": config.SECURITY_MODE
        }

    except Exception as e:
        logger.error(f"Error handling request: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Validate configuration before starting
    print("\n🔍 Validating configuration...")

    # Enforce Lake Formation security mode
    if config.SECURITY_MODE != 'lakeformation':
        print("\n❌ Error: Only Lake Formation security mode is supported!")
        print(f"   Current SECURITY_MODE: {config.SECURITY_MODE}")
        print(f"\n📝 Please update SSM Parameter Store:")
        print(f"   aws ssm put-parameter --name lh_security_mode --value 'lakeformation' --type String --overwrite")
        print(f"\n   Application-level SQL filtering has been removed for security reasons.")
        print(f"   See SECURITY_BEST_PRACTICES.md for details.")
        sys.exit(1)

    if not config.is_valid():
        print("\n❌ Configuration is invalid!")
        config.print_status()
        print("\n📝 Please update your SSM parameters.")
        print("   See CONFIGURATION_GUIDE.md for details.")
        sys.exit(1)

    # Validate Lake Formation is configured
    if not config.RLS_ROLE_ARN:
        print("\n❌ Error: Lake Formation RLS is not configured!")
        print("\n📝 Setup Lake Formation:")
        print("   cd athena-setup")
        print("   python setup_lake_formation.py")
        print("\n   Then add RLS_ROLE_ARN to SSM Parameter Store:")
        print("   aws ssm put-parameter --name lh_rls_role_arn --value 'arn:aws:iam::ACCOUNT:role/ROLE_NAME' --type String")
        sys.exit(1)

    print("✅ Configuration validated")
    print("🔒 Lake Formation row-level security enabled")

    # Print configuration summary
    logger.info(f"Starting MCP Server with Lake Formation RLS:")
    logger.info(f"  Region: {config.AWS_REGION}")
    logger.info(f"  Database: {config.ATHENA_DATABASE_NAME}")
    logger.info(f"  S3 Output: {config.S3_OUTPUT_LOCATION}")
    logger.info(f"  RLS Role: {config.RLS_ROLE_ARN}")

    # Run the MCP server
    app.run()
