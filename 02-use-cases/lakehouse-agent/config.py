#!/usr/bin/env python3
"""
Centralized Configuration Management for Lakehouse Agent

This module loads configuration from .env file and provides
easy access to all configuration values across the application.

Usage:
    from config import config

    # Access configuration
    bucket_name = config.S3_BUCKET_NAME
    region = config.AWS_REGION

    # Or get with default
    mode = config.get('SECURITY_MODE', 'basic')
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Get the directory where this config file is located
CONFIG_DIR = Path(__file__).parent.absolute()

# Load .env file from the project root
ENV_FILE = CONFIG_DIR / '.env'

# Load environment variables from .env file
load_dotenv(ENV_FILE)


class Config:
    """
    Configuration class that loads and provides access to environment variables.
    """

    def __init__(self):
        """Initialize configuration from environment variables."""
        self._loaded = False
        self._load_config()

    def _substitute_variables(self, value: str) -> str:
        """
        Substitute placeholders in configuration values.

        Replaces ${VARIABLE_NAME} with actual values from already loaded config.

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

    def _load_config(self):
        """Load all configuration values from environment."""
        # AWS Configuration (load these first as they're used in substitutions)
        self.AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
        self.AWS_ACCOUNT_ID = os.getenv('AWS_ACCOUNT_ID', '')

        # S3 Configuration
        self.S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', '')
        self.S3_CLAIMS_PREFIX = os.getenv('S3_CLAIMS_PREFIX', 'lakehouse-data/claims/')
        self.S3_USERS_PREFIX = os.getenv('S3_USERS_PREFIX', 'lakehouse-data/users/')
        self.S3_ATHENA_RESULTS_PREFIX = os.getenv('S3_ATHENA_RESULTS_PREFIX', 'athena-results/')

        # Computed S3 paths
        self.S3_OUTPUT_LOCATION = f"s3://{self.S3_BUCKET_NAME}/{self.S3_ATHENA_RESULTS_PREFIX}"

        # Athena Configuration
        self.ATHENA_DATABASE_NAME = os.getenv('ATHENA_DATABASE_NAME', 'lakehouse_db')
        self.ATHENA_WORKGROUP = os.getenv('ATHENA_WORKGROUP', 'primary')

        # Lake Formation (Production Security) - with variable substitution
        self.RLS_ROLE_ARN = self._substitute_variables(os.getenv('RLS_ROLE_ARN', ''))
        self.RLS_ROLE_NAME = os.getenv('RLS_ROLE_NAME', 'lakehouse-rls-role')

        # Cognito Configuration - with variable substitution for ARN
        self.COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID', '')
        self.COGNITO_USER_POOL_ARN = self._substitute_variables(os.getenv('COGNITO_USER_POOL_ARN', ''))
        self.COGNITO_APP_CLIENT_ID = os.getenv('COGNITO_APP_CLIENT_ID', '')
        self.COGNITO_APP_CLIENT_SECRET = os.getenv('COGNITO_APP_CLIENT_SECRET', '')
        self.COGNITO_DOMAIN = os.getenv('COGNITO_DOMAIN', '')
        self.COGNITO_RESOURCE_SERVER_ID = os.getenv('COGNITO_RESOURCE_SERVER_ID', 'lakehouse-api')

        # OAuth Scopes
        self.COGNITO_SCOPE_QUERY = os.getenv('COGNITO_SCOPE_QUERY', 'lakehouse-api/claims/query')
        self.COGNITO_SCOPE_SUBMIT = os.getenv('COGNITO_SCOPE_SUBMIT', 'lakehouse-api/claims/submit')
        self.COGNITO_SCOPE_UPDATE = os.getenv('COGNITO_SCOPE_UPDATE', 'lakehouse-api/claims/update')
        self.COGNITO_SCOPE_APPROVE = os.getenv('COGNITO_SCOPE_APPROVE', 'lakehouse-api/claims/approve')

        # AgentCore Gateway Configuration - with variable substitution
        self.GATEWAY_NAME = os.getenv('GATEWAY_NAME', 'lakehouse-gateway')
        self.GATEWAY_ARN = self._substitute_variables(os.getenv('GATEWAY_ARN', ''))
        self.GATEWAY_ID = os.getenv('GATEWAY_ID', '')

        # Gateway Interceptor Lambda - with variable substitution
        self.INTERCEPTOR_LAMBDA_NAME = os.getenv('INTERCEPTOR_LAMBDA_NAME', 'lakehouse-gateway-interceptor')
        self.INTERCEPTOR_LAMBDA_ARN = self._substitute_variables(os.getenv('INTERCEPTOR_LAMBDA_ARN', ''))
        self.INTERCEPTOR_LAMBDA_ROLE_ARN = self._substitute_variables(os.getenv('INTERCEPTOR_LAMBDA_ROLE_ARN', ''))

        # MCP Athena Server Configuration - with variable substitution
        self.MCP_SERVER_NAME = os.getenv('MCP_SERVER_NAME', 'lakehouse-mcp-server')
        self.MCP_SERVER_ARN = self._substitute_variables(os.getenv('MCP_SERVER_ARN', ''))
        self.MCP_SERVER_ROLE_ARN = self._substitute_variables(os.getenv('MCP_SERVER_ROLE_ARN', ''))

        # Security Mode (PRODUCTION ONLY: lakeformation)
        self.SECURITY_MODE = os.getenv('SECURITY_MODE', 'lakeformation')
        # Note: 'basic' mode has been removed for security reasons

        # SageMaker Unified Studio (DataZone) Configuration
        self.DATAZONE_DOMAIN_ID = os.getenv('DATAZONE_DOMAIN_ID', '')
        self.DATAZONE_DOMAIN_NAME = os.getenv('DATAZONE_DOMAIN_NAME', 'lakehouse-domain')
        self.DATAZONE_PROJECT_ID = os.getenv('DATAZONE_PROJECT_ID', '')
        self.DATAZONE_PROJECT_NAME = os.getenv('DATAZONE_PROJECT_NAME', 'health-lakehouse')
        self.DATAZONE_ENVIRONMENT_ID = os.getenv('DATAZONE_ENVIRONMENT_ID', '')
        self.DATAZONE_DATA_SOURCE_ID = os.getenv('DATAZONE_DATA_SOURCE_ID', '')
        self.ENABLE_DATAZONE_INTEGRATION = os.getenv('ENABLE_DATAZONE_INTEGRATION', 'false').lower() == 'true'

        # Lakehouse Agent Runtime Configuration - with variable substitution
        self.LAKEHOUSE_AGENT_NAME = os.getenv('LAKEHOUSE_AGENT_NAME', 'lakehouse-agent')
        self.RUNTIME_ARN = self._substitute_variables(os.getenv('RUNTIME_ARN', ''))
        self.RUNTIME_ID = os.getenv('RUNTIME_ID', '')

        # Streamlit UI Configuration
        self.STREAMLIT_PORT = int(os.getenv('STREAMLIT_PORT', '8501'))
        self.STREAMLIT_CALLBACK_URL = os.getenv('STREAMLIT_CALLBACK_URL', 'http://localhost:8501')

        # Test Users
        self.TEST_USER_1 = os.getenv('TEST_USER_1', 'user001@example.com')
        self.TEST_USER_2 = os.getenv('TEST_USER_2', 'user002@example.com')
        self.TEST_USER_3 = os.getenv('TEST_USER_3', 'adjuster001@example.com')
        self.TEST_PASSWORD = os.getenv('TEST_PASSWORD', 'TempPass123!')

        # Logging and Monitoring
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.ENABLE_CLOUDTRAIL_LOGGING = os.getenv('ENABLE_CLOUDTRAIL_LOGGING', 'true').lower() == 'true'
        self.ENABLE_XRAY_TRACING = os.getenv('ENABLE_XRAY_TRACING', 'false').lower() == 'true'

        # Development/Testing Configuration
        self.LOCAL_DEVELOPMENT = os.getenv('LOCAL_DEVELOPMENT', 'false').lower() == 'true'
        self.MOCK_ATHENA_QUERIES = os.getenv('MOCK_ATHENA_QUERIES', 'false').lower() == 'true'

        # Feature Flags
        self.ENABLE_CLAIM_SUBMISSION = os.getenv('ENABLE_CLAIM_SUBMISSION', 'true').lower() == 'true'
        self.ENABLE_CLAIM_UPDATES = os.getenv('ENABLE_CLAIM_UPDATES', 'true').lower() == 'true'
        self.ENABLE_CLAIM_APPROVAL = os.getenv('ENABLE_CLAIM_APPROVAL', 'true').lower() == 'true'
        self.REQUIRE_MFA = os.getenv('REQUIRE_MFA', 'false').lower() == 'true'

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
    parser.add_argument('--create-env', action='store_true', help='Create .env from .env.example')

    args = parser.parse_args()

    if args.create_env:
        # Copy .env.example to .env if it doesn't exist
        env_example = CONFIG_DIR / '.env.example'
        env_file = CONFIG_DIR / '.env'

        if env_file.exists():
            print(f"❌ .env file already exists at: {env_file}")
            print("   Delete it first if you want to recreate it")
        elif not env_example.exists():
            print(f"❌ .env.example not found at: {env_example}")
        else:
            import shutil
            shutil.copy(env_example, env_file)
            print(f"✅ Created .env file at: {env_file}")
            print(f"   Please edit it and fill in your actual values")

    elif args.validate:
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
