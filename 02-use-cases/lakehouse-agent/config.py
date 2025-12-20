#!/usr/bin/env python3
"""
Centralized Configuration Management for Lakehouse Agent

This module loads configuration from AWS Systems Manager (SSM) Parameter Store
and provides easy access to all configuration values across the application.

All parameters are stored in SSM with the 'lh_' prefix.
AWS_REGION and AWS_ACCOUNT_ID are auto-detected from the boto3 session.

Usage:
    from config import config

    # Access configuration
    bucket_name = config.S3_BUCKET_NAME
    region = config.AWS_REGION

    # Or get with default
    mode = config.get('SECURITY_MODE', 'lakeformation')
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from ssm_config import SSMConfigLoader

logger = logging.getLogger(__name__)

# Get the directory where this config file is located
CONFIG_DIR = Path(__file__).parent.absolute()


class Config:
    """
    Configuration class that loads and provides access to SSM parameters.
    """

    def __init__(self):
        """Initialize configuration from SSM Parameter Store."""
        self._loaded = False
        self._ssm_loader: Optional[SSMConfigLoader] = None
        self._load_config()

    def _substitute_variables(self, value: str) -> str:
        """
        Substitute placeholders in configuration values.

        Replaces ${VARIABLE_NAME} with actual values from already loaded config.
        AWS_REGION and AWS_ACCOUNT_ID are auto-detected from boto3 session.

        Args:
            value: String that may contain placeholders

        Returns:
            String with placeholders replaced
        """
        if not value or not isinstance(value, str):
            return value

        # Replace ${AWS_ACCOUNT_ID} with actual account ID
        if '${AWS_ACCOUNT_ID}' in value and hasattr(self, 'AWS_ACCOUNT_ID'):
            value = value.replace('${AWS_ACCOUNT_ID}', self.AWS_ACCOUNT_ID)

        # Replace ${AWS_REGION} with actual region
        if '${AWS_REGION}' in value and hasattr(self, 'AWS_REGION'):
            value = value.replace('${AWS_REGION}', self.AWS_REGION)

        return value

    def _load_from_ssm(self) -> Dict[str, Any]:
        """
        Load configuration from SSM Parameter Store.
        
        Returns:
            Dictionary of configuration parameters
            
        Raises:
            RuntimeError: If SSM is unavailable or required parameters are missing
        """
        try:
            # Initialize SSM loader
            self._ssm_loader = SSMConfigLoader()
            
            # Check SSM availability
            if not self._ssm_loader.is_available():
                raise RuntimeError(
                    "❌ SSM Parameter Store unavailable\n\n"
                    "Required IAM permissions:\n"
                    "  - ssm:GetParameter\n"
                    "  - ssm:GetParametersByPath\n"
                    "  - kms:Decrypt (for SecureString parameters)\n\n"
                    "Please ensure your AWS credentials have the necessary permissions."
                )
            
            # Load all parameters with lh_ prefix
            parameters = self._ssm_loader.get_parameters_by_prefix()
            
            logger.info(f"Loaded {len(parameters)} parameters from SSM Parameter Store")
            return parameters
            
        except Exception as e:
            logger.error(f"Failed to load configuration from SSM: {e}")
            raise RuntimeError(
                f"❌ Failed to load configuration from SSM Parameter Store: {e}\n\n"
                "Please ensure:\n"
                "  1. AWS credentials are configured\n"
                "  2. SSM parameters exist with 'lh_' prefix\n"
                "  3. IAM permissions are sufficient\n"
            ) from e

    def _load_config(self):
        """Load all configuration values from SSM Parameter Store."""
        # Load parameters from SSM
        ssm_params = self._load_from_ssm()
        
        # AWS Configuration (auto-detected, not from SSM)
        self.AWS_REGION = self._ssm_loader.get_region()
        self.AWS_ACCOUNT_ID = self._ssm_loader.get_account_id()
        
        logger.info(f"Auto-detected AWS_REGION: {self.AWS_REGION}")
        logger.info(f"Auto-detected AWS_ACCOUNT_ID: {self.AWS_ACCOUNT_ID}")

        # S3 Configuration
        self.S3_BUCKET_NAME = ssm_params.get('S3_BUCKET_NAME', '')
        self.S3_CLAIMS_PREFIX = ssm_params.get('S3_CLAIMS_PREFIX', 'lakehouse-data/claims/')
        self.S3_USERS_PREFIX = ssm_params.get('S3_USERS_PREFIX', 'lakehouse-data/users/')
        self.S3_ATHENA_RESULTS_PREFIX = ssm_params.get('S3_ATHENA_RESULTS_PREFIX', 'athena-results/')

        # Computed S3 paths
        self.S3_OUTPUT_LOCATION = f"s3://{self.S3_BUCKET_NAME}/{self.S3_ATHENA_RESULTS_PREFIX}"

        # Athena Configuration
        self.ATHENA_DATABASE_NAME = ssm_params.get('ATHENA_DATABASE_NAME', 'lakehouse_db')
        self.ATHENA_WORKGROUP = ssm_params.get('ATHENA_WORKGROUP', 'primary')

        # Lake Formation (Production Security) - with variable substitution
        self.RLS_ROLE_ARN = self._substitute_variables(ssm_params.get('RLS_ROLE_ARN', ''))
        self.RLS_ROLE_NAME = ssm_params.get('RLS_ROLE_NAME', 'lakehouse-rls-role')

        # Cognito Configuration - with variable substitution for ARN
        self.COGNITO_USER_POOL_ID = ssm_params.get('COGNITO_USER_POOL_ID', '')
        self.COGNITO_USER_POOL_ARN = self._substitute_variables(ssm_params.get('COGNITO_USER_POOL_ARN', ''))
        self.COGNITO_APP_CLIENT_ID = ssm_params.get('COGNITO_APP_CLIENT_ID', '')
        self.COGNITO_APP_CLIENT_SECRET = ssm_params.get('COGNITO_APP_CLIENT_SECRET', '')
        self.COGNITO_DOMAIN = ssm_params.get('COGNITO_DOMAIN', '')
        self.COGNITO_RESOURCE_SERVER_ID = ssm_params.get('COGNITO_RESOURCE_SERVER_ID', 'lakehouse-api')

        # OAuth Scopes
        self.COGNITO_SCOPE_QUERY = ssm_params.get('COGNITO_SCOPE_QUERY', 'lakehouse-api/claims/query')
        self.COGNITO_SCOPE_SUBMIT = ssm_params.get('COGNITO_SCOPE_SUBMIT', 'lakehouse-api/claims/submit')
        self.COGNITO_SCOPE_UPDATE = ssm_params.get('COGNITO_SCOPE_UPDATE', 'lakehouse-api/claims/update')
        self.COGNITO_SCOPE_APPROVE = ssm_params.get('COGNITO_SCOPE_APPROVE', 'lakehouse-api/claims/approve')

        # AgentCore Gateway Configuration - with variable substitution
        self.GATEWAY_NAME = ssm_params.get('GATEWAY_NAME', 'lakehouse-gateway')
        self.GATEWAY_ARN = self._substitute_variables(ssm_params.get('GATEWAY_ARN', ''))
        self.GATEWAY_ID = ssm_params.get('GATEWAY_ID', '')

        # Gateway Interceptor Lambda - with variable substitution
        self.INTERCEPTOR_LAMBDA_NAME = ssm_params.get('INTERCEPTOR_LAMBDA_NAME', 'lakehouse-gateway-interceptor')
        self.INTERCEPTOR_LAMBDA_ARN = self._substitute_variables(ssm_params.get('INTERCEPTOR_LAMBDA_ARN', ''))
        self.INTERCEPTOR_LAMBDA_ROLE_ARN = self._substitute_variables(ssm_params.get('INTERCEPTOR_LAMBDA_ROLE_ARN', ''))

        # MCP Athena Server Configuration - with variable substitution
        self.MCP_SERVER_NAME = ssm_params.get('MCP_SERVER_NAME', 'lakehouse-mcp-server')
        self.MCP_SERVER_ARN = self._substitute_variables(ssm_params.get('MCP_SERVER_ARN', ''))
        self.MCP_SERVER_ROLE_ARN = self._substitute_variables(ssm_params.get('MCP_SERVER_ROLE_ARN', ''))

        # Security Mode (PRODUCTION ONLY: lakeformation)
        self.SECURITY_MODE = ssm_params.get('SECURITY_MODE', 'lakeformation')
        # Note: 'basic' mode has been removed for security reasons

        # SageMaker Unified Studio (DataZone) Configuration
        self.DATAZONE_DOMAIN_ID = ssm_params.get('DATAZONE_DOMAIN_ID', '')
        self.DATAZONE_DOMAIN_NAME = ssm_params.get('DATAZONE_DOMAIN_NAME', 'lakehouse-domain')
        self.DATAZONE_PROJECT_ID = ssm_params.get('DATAZONE_PROJECT_ID', '')
        self.DATAZONE_PROJECT_NAME = ssm_params.get('DATAZONE_PROJECT_NAME', 'health-lakehouse')
        self.DATAZONE_ENVIRONMENT_ID = ssm_params.get('DATAZONE_ENVIRONMENT_ID', '')
        self.DATAZONE_DATA_SOURCE_ID = ssm_params.get('DATAZONE_DATA_SOURCE_ID', '')
        self.ENABLE_DATAZONE_INTEGRATION = ssm_params.get('ENABLE_DATAZONE_INTEGRATION', 'false').lower() == 'true'

        # Lakehouse Agent Runtime Configuration - with variable substitution
        self.LAKEHOUSE_AGENT_NAME = ssm_params.get('LAKEHOUSE_AGENT_NAME', 'lakehouse-agent')
        self.RUNTIME_ARN = self._substitute_variables(ssm_params.get('RUNTIME_ARN', ''))
        self.RUNTIME_ID = ssm_params.get('RUNTIME_ID', '')

        # Streamlit UI Configuration
        streamlit_port = ssm_params.get('STREAMLIT_PORT', '8501')
        self.STREAMLIT_PORT = int(streamlit_port) if streamlit_port else 8501
        self.STREAMLIT_CALLBACK_URL = ssm_params.get('STREAMLIT_CALLBACK_URL', 'http://localhost:8501')

        # Test Users
        self.TEST_USER_1 = ssm_params.get('TEST_USER_1', 'user001@example.com')
        self.TEST_USER_2 = ssm_params.get('TEST_USER_2', 'user002@example.com')
        self.TEST_USER_3 = ssm_params.get('TEST_USER_3', 'adjuster001@example.com')
        self.TEST_PASSWORD = ssm_params.get('TEST_PASSWORD', 'TempPass123!')

        # Logging and Monitoring
        self.LOG_LEVEL = ssm_params.get('LOG_LEVEL', 'INFO')
        self.ENABLE_CLOUDTRAIL_LOGGING = ssm_params.get('ENABLE_CLOUDTRAIL_LOGGING', 'true').lower() == 'true'
        self.ENABLE_XRAY_TRACING = ssm_params.get('ENABLE_XRAY_TRACING', 'false').lower() == 'true'

        # Development/Testing Configuration
        self.LOCAL_DEVELOPMENT = ssm_params.get('LOCAL_DEVELOPMENT', 'false').lower() == 'true'
        self.MOCK_ATHENA_QUERIES = ssm_params.get('MOCK_ATHENA_QUERIES', 'false').lower() == 'true'

        # Feature Flags
        self.ENABLE_CLAIM_SUBMISSION = ssm_params.get('ENABLE_CLAIM_SUBMISSION', 'true').lower() == 'true'
        self.ENABLE_CLAIM_UPDATES = ssm_params.get('ENABLE_CLAIM_UPDATES', 'true').lower() == 'true'
        self.ENABLE_CLAIM_APPROVAL = ssm_params.get('ENABLE_CLAIM_APPROVAL', 'true').lower() == 'true'
        self.REQUIRE_MFA = ssm_params.get('REQUIRE_MFA', 'false').lower() == 'true'

        self._loaded = True

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return getattr(self, key, os.getenv(key, default))

    def validate(self) -> Dict[str, bool]:
        """
        Validate that required configuration values are set.

        Returns:
            Dictionary of validation results
        """
        required_fields = {
            'AWS_REGION': bool(self.AWS_REGION),
            'S3_BUCKET_NAME': bool(self.S3_BUCKET_NAME),
            'ATHENA_DATABASE_NAME': bool(self.ATHENA_DATABASE_NAME),
        }

        # Cognito fields (required for OAuth)
        cognito_fields = {
            'COGNITO_USER_POOL_ID': bool(self.COGNITO_USER_POOL_ID),
            'COGNITO_APP_CLIENT_ID': bool(self.COGNITO_APP_CLIENT_ID),
            'COGNITO_DOMAIN': bool(self.COGNITO_DOMAIN),
        }

        # Security mode specific validation
        if self.SECURITY_MODE == 'lakeformation':
            security_fields = {
                'RLS_ROLE_ARN': bool(self.RLS_ROLE_ARN),
            }
        else:
            security_fields = {}

        return {
            **required_fields,
            **cognito_fields,
            **security_fields
        }

    def is_valid(self) -> bool:
        """
        Check if all required configuration is valid.

        Returns:
            True if all required fields are set, False otherwise
        """
        validation = self.validate()
        return all(validation.values())

    def print_status(self):
        """Print configuration status for debugging."""
        print("\n" + "=" * 60)
        print("Configuration Status")
        print("=" * 60)
        print(f"\n📍 Configuration Source: SSM Parameter Store")
        print(f"   Region: {self.AWS_REGION}")
        print(f"   Account ID: {self.AWS_ACCOUNT_ID}")
        print(f"   Parameter Prefix: lh_")

        validation = self.validate()

        print("\n✅ = Configured | ❌ = Missing\n")

        for field, is_valid in validation.items():
            status = "✅" if is_valid else "❌"
            value = getattr(self, field, 'Not Set')
            # Mask secrets
            if 'SECRET' in field or 'PASSWORD' in field:
                value = '***' if value else 'Not Set'
            print(f"{status} {field}: {value}")

        print("\n" + "=" * 60)
        print(f"Security Mode: {self.SECURITY_MODE}")
        print(f"Overall Status: {'✅ Valid' if self.is_valid() else '❌ Invalid - Check missing fields'}")
        print("=" * 60 + "\n")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary of configuration values
        """
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith('_')
        }


# Global configuration instance
config = Config()


# Convenience function for scripts
def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Configuration instance
    """
    return config


# For command-line usage
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Configuration Management Utility')
    parser.add_argument('--validate', action='store_true', help='Validate configuration')
    parser.add_argument('--show', action='store_true', help='Show configuration status')
    parser.add_argument('--get', type=str, help='Get specific configuration value')

    args = parser.parse_args()

    if args.validate:
        if config.is_valid():
            print("✅ Configuration is valid")
            exit(0)
        else:
            print("❌ Configuration is invalid")
            config.print_status()
            exit(1)

    elif args.show:
        config.print_status()

    elif args.get:
        value = config.get(args.get)
        print(value if value else f"Configuration key '{args.get}' not found")

    else:
        # Default: show status
        config.print_status()
