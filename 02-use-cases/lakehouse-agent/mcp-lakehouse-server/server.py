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
- Reads from SSM Parameter Store
- Auto-detects region from boto3 session
- Requires SECURITY_MODE=lakeformation
- Requires RLS_ROLE_ARN to be set
"""

import sys
import os
import logging
from typing import Any, Dict, Optional
import boto3
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("=" * 70)
logger.info("🚀 SERVER.PY INITIALIZATION - VERSION 2026-01-08-v3")
logger.info("=" * 70)

# Import aws_session_utils from local directory (copied during build)
from aws_session_utils import get_aws_session

# Initialize MCP server
mcp = FastMCP(host="0.0.0.0", stateless_http=True)
logger.info("✅ FastMCP initialized")

# PRODUCTION ONLY: Use Lake Formation row-level security
from athena_tools_secure import SecureAthenaClaimsTools as AthenaTools

logger.info("🔒 Using Lake Formation row-level security (production mode)")

# Global Athena tools instance
athena_tools = None

# Configuration cache
_config_cache = None


def get_config() -> Dict[str, Optional[str]]:
    """
    Load configuration from environment variables and SSM Parameter Store.
    """
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    config = {}

    # Get validated AWS session with SSO support
    # Note: verbose=False to reduce logging in Lambda/container environments
    try:
        session, region, account_id = get_aws_session(verbose=False)
        config['region'] = region
        config['account_id'] = account_id
        logger.info(f"✅ Region: {config['region']}")
        logger.info(f"✅ Account ID: {config['account_id']}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize AWS session: {e}")
        raise

    ssm = session.client('ssm', region_name=config['region'])
    
    def get_param(name: str, default: str = None, required: bool = True) -> Optional[str]:
        """Get parameter from SSM Parameter Store only. No environment variable fallback."""
        try:
            response = ssm.get_parameter(Name=f'/app/lakehouse-agent/{name}')
            value = response['Parameter']['Value']
            logger.info(f"✅ {name} from SSM: {value}")
            return value
        except ssm.exceptions.ParameterNotFound:
            if default is not None:
                logger.info(f"ℹ️  {name} using default: {default}")
                return default
            if required:
                logger.error(f"❌ Required parameter {name} not found in SSM")
                raise ValueError(f"Required SSM parameter missing: /app/lakehouse-agent/{name}")
            logger.warning(f"⚠️  {name} not found")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting {name}: {e}")
            if default is not None:
                return default
            if required:
                raise
            return None
    
    config['s3_bucket_name'] = get_param('s3-bucket-name')
    config['database_name'] = get_param('database-name')
    config['rls_role_arn'] = get_param('rls-role-arn')
    config['security_mode'] = get_param('security-mode', default='lakeformation', required=False)
    config['log_level'] = os.environ.get('LOG_LEVEL', 'INFO')
    
    if config['s3_bucket_name']:
        config['s3_output_location'] = f"s3://{config['s3_bucket_name']}/athena-results/"
    else:
        config['s3_output_location'] = None
    
    config['test_user'] = os.environ.get('TEST_USER_1', 'user001@example.com')
    config['local_development'] = os.environ.get('LOCAL_DEVELOPMENT', 'false').lower() == 'true'
    
    _config_cache = config
    return config


def validate_config(config: Dict[str, Optional[str]]) -> bool:
    required_params = [
        ('region', 'AWS Region'),
        ('s3_bucket_name', 'S3 Bucket Name'),
        ('database_name', 'Athena Database Name'),
        ('rls_role_arn', 'RLS Role ARN'),
        ('security_mode', 'Security Mode')
    ]
    
    missing = []
    for param, display_name in required_params:
        if not config.get(param):
            missing.append(display_name)
    
    if missing:
        logger.error(f"❌ Missing required configuration: {', '.join(missing)}")
        return False
    
    if config['security_mode'] != 'lakeformation':
        logger.error(f"❌ Invalid security mode: {config['security_mode']}")
        logger.info("   Only 'lakeformation' is supported")
        return False
    
    return True


def get_athena_tools():
    global athena_tools
    if athena_tools is None:
        config = get_config()
        
        logger.info("Initializing Athena tools with Lake Formation RLS...")
        logger.info(f"  Region: {config['region']}")
        logger.info(f"  Database: {config['database_name']}")
        logger.info(f"  S3 Output: {config['s3_output_location']}")

        if not config['rls_role_arn']:
            raise ValueError(
                "❌ RLS_ROLE_ARN not set in configuration.\n"
                "   Lake Formation is required for production security."
            )

        logger.info(f"  RLS Role: {config['rls_role_arn']}")

        athena_tools = AthenaTools(
            region=config['region'],
            database_name=config['database_name'],
            s3_output_location=config['s3_output_location'],
            rls_role_arn=config['rls_role_arn']
        )

        logger.info("✅ Athena tools initialized with Lake Formation RLS")

    return athena_tools


def get_user_id_with_fallback(context_arg: Dict[str, Any] = None) -> str:
    """Get user ID from context argument or fallback to test user."""
    config = get_config()
    user_id = None
    
    if context_arg:
        logger.info(f"📋 Context argument received: {context_arg}")
        user_id = context_arg.get('user_id')
        if user_id:
            logger.info(f"   Got user_id from context argument: {user_id}")
            return user_id
    
    if config['local_development']:
        user_id = config['test_user']
        logger.warning(f"⚠️  Using test user for local development: {user_id}")
        return user_id
    
    logger.error("❌ User identity not found in request")
    return None


@mcp.tool(
    name="query_claims",
    description="Query health lakehouse data for the authenticated user with optional filters"
)
def query_claims(
    claim_status: str = None,
    claim_type: str = None,
    start_date: str = None,
    end_date: str = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Query lakehouse data for the authenticated user."""
    logger.info("=" * 60)
    logger.info("🔧 TOOL INVOKED: query_claims")
    logger.info("=" * 60)
    
    logger.info("📥 INPUT PARAMETERS:")
    logger.info(f"   claim_status: {claim_status}")
    logger.info(f"   claim_type: {claim_type}")
    logger.info(f"   start_date: {start_date}")
    logger.info(f"   end_date: {end_date}")
    logger.info(f"   context: {context}")
    
    try:
        user_id = get_user_id_with_fallback(context)
        logger.info(f"👤 USER ID: {user_id}")
        
        if not user_id:
            return {"success": False, "error": "User identity not found in request"}
        
        filters = {k: v for k, v in {
            'claim_status': claim_status,
            'claim_type': claim_type,
            'start_date': start_date,
            'end_date': end_date
        }.items() if v is not None}
        
        logger.info(f"🔍 FILTERS: {filters}")

        tools = get_athena_tools()
        result = tools.query_claims(user_id, filters if filters else None)
        
        logger.info("📤 OUTPUT:")
        logger.info(f"   success: {result.get('success', 'N/A')}")
        if result.get('success'):
            claims_count = len(result.get('claims', []))
            logger.info(f"   claims_count: {claims_count}")
        else:
            logger.info(f"   error: {result.get('error', 'N/A')}")
        
        logger.info("=" * 60)
        return result

    except Exception as e:
        logger.error(f"❌ ERROR in query_claims: {str(e)}")
        import traceback
        logger.info(f"   Stack trace: {traceback.format_exc()}")
        logger.info("=" * 60)
        return {"success": False, "error": str(e)}


@mcp.tool(
    name="get_claim_details",
    description="Get detailed information about a specific claim by ID"
)
def get_claim_details(claim_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get details of a specific claim."""
    logger.info("=" * 60)
    logger.info("🔧 TOOL INVOKED: get_claim_details")
    logger.info("=" * 60)
    
    logger.info("📥 INPUT PARAMETERS:")
    logger.info(f"   claim_id: {claim_id}")
    logger.info(f"   context: {context}")
    
    try:
        user_id = get_user_id_with_fallback(context)
        logger.info(f"👤 USER ID: {user_id}")
        
        if not user_id:
            return {"success": False, "error": "User identity not found in request"}
        
        tools = get_athena_tools()
        result = tools.get_claim_details(user_id, claim_id)
        
        logger.info("📤 OUTPUT:")
        logger.info(f"   success: {result.get('success', 'N/A')}")
        if result.get('success'):
            claim_data = result.get('claim', {})
            logger.info(f"   claim_id: {claim_data.get('claim_id', 'N/A')}")
            logger.info(f"   claim_status: {claim_data.get('claim_status', 'N/A')}")
        else:
            logger.info(f"   error: {result.get('error', 'N/A')}")
        
        logger.info("=" * 60)
        return result

    except Exception as e:
        logger.error(f"❌ ERROR in get_claim_details: {str(e)}")
        import traceback
        logger.info(f"   Stack trace: {traceback.format_exc()}")
        logger.info("=" * 60)
        return {"success": False, "error": str(e)}


@mcp.tool(
    name="get_claims_summary",
    description="Get summary statistics of all claims for the authenticated user"
)
def get_claims_summary(context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get claims summary for the user."""
    logger.info("=" * 60)
    logger.info("🔧 TOOL INVOKED: get_claims_summary")
    logger.info("=" * 60)
    
    logger.info("📥 INPUT PARAMETERS:")
    logger.info(f"   context: {context}")
    
    try:
        user_id = get_user_id_with_fallback(context)
        logger.info(f"👤 USER ID: {user_id}")
        
        if not user_id:
            return {"success": False, "error": "User identity not found in request"}
        
        tools = get_athena_tools()
        result = tools.get_claims_summary(user_id)
        
        logger.info("📤 OUTPUT:")
        logger.info(f"   success: {result.get('success', 'N/A')}")
        if result.get('success'):
            summary = result.get('summary', {})
            logger.info(f"   total_claims: {summary.get('total_claims', 'N/A')}")
            logger.info(f"   total_amount: {summary.get('total_amount', 'N/A')}")
            logger.info(f"   by_status: {summary.get('by_status', 'N/A')}")
        else:
            logger.info(f"   error: {result.get('error', 'N/A')}")
        
        logger.info("=" * 60)
        return result

    except Exception as e:
        logger.error(f"❌ ERROR in get_claims_summary: {str(e)}")
        import traceback
        logger.info(f"   Stack trace: {traceback.format_exc()}")
        logger.info("=" * 60)
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    logger.info("\n🔍 Validating configuration...")
    
    config = get_config()
    
    if config['security_mode'] != 'lakeformation':
        logger.info("\n❌ Error: Only Lake Formation security mode is supported!")
        logger.info(f"   Current SECURITY_MODE: {config['security_mode']}")
        sys.exit(1)

    if not validate_config(config):
        logger.info("\n❌ Configuration is invalid!")
        sys.exit(1)

    if not config['rls_role_arn']:
        logger.info("\n❌ Error: Lake Formation RLS is not configured!")
        sys.exit(1)

    logger.info("✅ Configuration validated")
    logger.info("🔒 Lake Formation row-level security enabled")

    logger.info(f"Starting MCP Server with Lake Formation RLS:")
    logger.info(f"  Region: {config['region']}")
    logger.info(f"  Database: {config['database_name']}")
    logger.info(f"  S3 Output: {config['s3_output_location']}")
    logger.info(f"  RLS Role: {config['rls_role_arn']}")

    mcp.run(transport="streamable-http")
