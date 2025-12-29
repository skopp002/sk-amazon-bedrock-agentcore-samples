#!/usr/bin/env python3
"""
SageMaker Unified Studio (DataZone) Setup for Lakehouse Agent

This script sets up data governance infrastructure including:
- DataZone domain for data governance
- Project for health lakehouse data
- Environment for analytics
- Athena data source registration
- Business glossary with healthcare terms
- Data lineage tracking

Prerequisites:
- AWS credentials configured
- Lake Formation already set up (run setup_lake_formation.py first)
- Athena database exists (run setup_athena.py first)
- S3 bucket name stored in SSM Parameter Store

Usage:
    python setup_sagemaker_unified_studio.py --domain-name DOMAIN_NAME

Arguments:
    --domain-name: (Required) Name for the DataZone domain

Outputs ARNs to update in SSM Parameter Store:
- DATAZONE_DOMAIN_ID
- DATAZONE_PROJECT_ID
- DATAZONE_ENVIRONMENT_ID
- DATAZONE_DATA_SOURCE_ID
"""

import boto3
import json
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional


class SageMakerUnifiedStudioSetup:
    """Sets up SageMaker Unified Studio (DataZone) for data governance."""

    def __init__(self, domain_name: str):
        """
        Initialize AWS clients and configuration.
        
        Args:
            domain_name: Name for the DataZone domain
        """
        # Get region and account from boto3 session
        session = boto3.Session()
        self.region = session.region_name
        
        # Initialize AWS clients
        sts_client = boto3.client('sts')
        self.account_id = sts_client.get_caller_identity()['Account']
        
        self.ssm = boto3.client('ssm', region_name=self.region)
        self.datazone = boto3.client('datazone', region_name=self.region)
        self.iam = boto3.client('iam', region_name=self.region)
        self.sts = sts_client
        
        # Get configuration from SSM Parameter Store
        self.s3_bucket = self._get_ssm_parameter('/app/lakehouse-agent/s3-bucket-name')
        self.athena_database = self._get_ssm_parameter('/app/lakehouse-agent/database-name')
        self.domain_name = domain_name
        
        print(f"Initialized SageMaker Unified Studio setup for account {self.account_id}")
        print(f"Region: {self.region}")
        print(f"S3 Bucket: {self.s3_bucket}")
        print(f"Athena Database: {self.athena_database}")
        print(f"Domain Name: {self.domain_name}")

    def _get_ssm_parameter(self, parameter_name: str) -> str:
        """
        Get parameter value from SSM Parameter Store.
        
        Args:
            parameter_name: SSM parameter name
            
        Returns:
            Parameter value
        """
        try:
            response = self.ssm.get_parameter(Name=parameter_name)
            return response['Parameter']['Value']
        except self.ssm.exceptions.ParameterNotFound:
            print(f"❌ SSM parameter {parameter_name} not found")
            print(f"   Please run setup_athena.py first to create the required parameters")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error retrieving parameter {parameter_name}: {e}")
            sys.exit(1)

    def _store_ssm_parameter(self, parameter_name: str, parameter_value: str, description: str):
        """
        Store parameter value in SSM Parameter Store.
        
        Args:
            parameter_name: SSM parameter name
            parameter_value: Parameter value to store
            description: Parameter description
        """
        try:
            self.ssm.put_parameter(
                Name=parameter_name,
                Value=parameter_value,
                Description=description,
                Type='String',
                Overwrite=True
            )
            print(f"✅ Stored parameter: {parameter_name} = {parameter_value}")
        except Exception as e:
            print(f"❌ Error storing parameter {parameter_name}: {e}")
            raise

    def create_domain_execution_role(self) -> str:
        """
        Create IAM role for DataZone domain execution.

        Returns:
            Role ARN
        """
        role_name = 'DataZoneDomainExecutionRole-lakehouse'

        # Trust policy for DataZone
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "datazone.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        # Permissions policy
        permissions_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "glue:GetDatabase",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:GetPartition",
                        "glue:GetPartitions",
                        "athena:ListWorkGroups",
                        "athena:GetWorkGroup",
                        "athena:ListDataCatalogs",
                        "athena:GetDataCatalog",
                        "s3:ListBucket",
                        "s3:GetObject",
                        "lakeformation:GetDataAccess",
                        "lakeformation:GrantPermissions",
                        "lakeformation:ListPermissions"
                    ],
                    "Resource": "*"
                }
            ]
        }

        try:
            # Create role
            print(f"Creating IAM role: {role_name}")
            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='DataZone domain execution role for lakehouse data governance'
            )
            role_arn = response['Role']['Arn']

            # Attach inline policy
            self.iam.put_role_policy(
                RoleName=role_name,
                PolicyName='DataZonePermissions',
                PolicyDocument=json.dumps(permissions_policy)
            )

            print(f"✅ Created IAM role: {role_arn}")
            time.sleep(10)  # Wait for IAM eventual consistency
            return role_arn

        except self.iam.exceptions.EntityAlreadyExistsException:
            print(f"ℹ️  Role {role_name} already exists, retrieving ARN")
            response = self.iam.get_role(RoleName=role_name)
            return response['Role']['Arn']

    def create_domain(self, role_arn: str) -> str:
        """
        Create DataZone domain for data governance.

        Args:
            role_arn: Domain execution role ARN

        Returns:
            Domain ID
        """
        try:
            print(f"Creating DataZone domain: {self.domain_name}")
            response = self.datazone.create_domain(
                name=self.domain_name,
                description='Health lakehouse data governance and cataloging',
                domainExecutionRole=role_arn
                # Note: kmsKeyIdentifier omitted to use default encryption
                # If you need a specific KMS key, provide the full ARN:
                # arn:aws:kms:region:account-id:key/key-id
            )

            domain_id = response['id']
            print(f"✅ Created DataZone domain: {domain_id}")
            print(f"   Status: {response['status']}")

            # Wait for domain to be available
            print("   Waiting for domain to be available...")
            self._wait_for_domain_available(domain_id)

            return domain_id

        except self.datazone.exceptions.ConflictException as e:
            print(f"ℹ️  Domain already exists (ConflictException), listing domains to find ID")
            return self._find_existing_domain(self.domain_name)
        except Exception as e:
            if 'conflict' in str(e).lower() or 'already exists' in str(e).lower():
                print(f"ℹ️  Domain already exists, listing domains to find ID")
                return self._find_existing_domain(self.domain_name)
            raise

    def _wait_for_domain_available(self, domain_id: str, timeout: int = 300):
        """Wait for domain to be available."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = self.datazone.get_domain(identifier=domain_id)
                status = response['status']
                if status == 'AVAILABLE':
                    print("   ✅ Domain is available")
                    return
                elif status == 'FAILED':
                    raise Exception(f"Domain creation failed: {response.get('statusReason', 'Unknown')}")
                else:
                    print(f"   Status: {status}, waiting...")
                    time.sleep(10)
            except Exception as e:
                print(f"   Error checking domain status: {e}")
                time.sleep(10)

        raise TimeoutError(f"Domain did not become available within {timeout} seconds")

    def _find_existing_domain(self, domain_name: str) -> str:
        """Find existing domain by name."""
        paginator = self.datazone.get_paginator('list_domains')
        for page in paginator.paginate():
            for domain in page.get('items', []):
                if domain['name'] == domain_name:
                    return domain['id']
        raise Exception(f"Domain {domain_name} not found")

    def create_project(self, domain_id: str) -> str:
        """
        Create DataZone project for health lakehouse data.

        Args:
            domain_id: DataZone domain ID

        Returns:
            Project ID
        """
        project_name = 'health-lakehouse'

        try:
            print(f"Creating DataZone project: {project_name}")
            response = self.datazone.create_project(
                domainIdentifier=domain_id,
                name=project_name,
                description='Health lakehouse data processing and analytics'
            )

            project_id = response['id']
            print(f"✅ Created DataZone project: {project_id}")
            return project_id

        except self.datazone.exceptions.ConflictException as e:
            print(f"ℹ️  Project already exists (ConflictException), listing to find ID")
            return self._find_existing_project(domain_id, project_name)
        except Exception as e:
            if 'conflict' in str(e).lower() or 'already exists' in str(e).lower():
                print(f"ℹ️  Project already exists, listing to find ID")
                return self._find_existing_project(domain_id, project_name)
            raise

    def _find_existing_project(self, domain_id: str, project_name: str) -> str:
        """Find existing project by name."""
        paginator = self.datazone.get_paginator('list_projects')
        for page in paginator.paginate(domainIdentifier=domain_id):
            for project in page.get('items', []):
                if project['name'] == project_name:
                    return project['id']
        raise Exception(f"Project {project_name} not found")

    def create_environment_profile(self, domain_id: str, project_id: str) -> str:
        """
        Create environment profile for Athena access.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID

        Returns:
            Environment profile ID
        """
        try:
            print("Creating environment profile for Athena")
            response = self.datazone.create_environment_profile(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='athena-analytics-profile',
                description='Environment profile for Athena analytics',
                environmentBlueprintIdentifier='DefaultAthenaEnvironmentBlueprint',
                awsAccountId=self.account_id,
                awsAccountRegion=self.region
            )

            profile_id = response['id']
            print(f"✅ Created environment profile: {profile_id}")
            return profile_id

        except Exception as e:
            print(f"⚠️  Could not create environment profile: {e}")
            print("   You may need to create this manually in the console")
            return None

    def create_environment(self, domain_id: str, project_id: str, profile_id: Optional[str]) -> str:
        """
        Create DataZone environment.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID
            profile_id: Environment profile ID

        Returns:
            Environment ID
        """
        if not profile_id:
            print("⚠️  Skipping environment creation (no profile)")
            return None

        try:
            print("Creating DataZone environment")
            response = self.datazone.create_environment(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='claims-analytics-env',
                description='Environment for claims analytics',
                environmentProfileIdentifier=profile_id
            )

            env_id = response['id']
            print(f"✅ Created environment: {env_id}")
            return env_id

        except Exception as e:
            print(f"⚠️  Could not create environment: {e}")
            print("   You may need to create this manually in the console")
            return None

    def register_athena_data_source(self, domain_id: str, project_id: str) -> str:
        """
        Register Athena database as data source.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID

        Returns:
            Data source ID
        """
        try:
            print(f"Registering Athena data source: {self.athena_database}")
            response = self.datazone.create_data_source(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='claims-athena-source',
                description=f'Athena data source for {self.athena_database} database',
                type='ATHENA',
                configuration={
                    'athenaConfiguration': {
                        'databaseName': self.athena_database,
                        'workgroupName': 'primary'  # Default workgroup
                    }
                },
                enableSetting='ENABLED',
                publishOnImport=True
            )

            source_id = response['id']
            print(f"✅ Registered data source: {source_id}")
            return source_id

        except Exception as e:
            print(f"⚠️  Could not register data source: {e}")
            print(f"   Error details: {str(e)}")
            return None

    def create_business_glossary(self, domain_id: str) -> Dict[str, str]:
        """
        Create business glossary with healthcare insurance terms.

        Args:
            domain_id: DataZone domain ID

        Returns:
            Dict of term names to term IDs
        """
        # Load glossary definitions from file
        glossary_file = Path(__file__).parent / 'business_glossary.json'
        if glossary_file.exists():
            with open(glossary_file) as f:
                terms = json.load(f)
        else:
            # Default terms if file doesn't exist
            terms = [
                {
                    "name": "Claim",
                    "shortDescription": "Request for payment for healthcare services",
                    "longDescription": "A claim is a request for payment submitted by a patient or healthcare provider for medical services rendered. It includes details about the service, cost, and patient information."
                },
                {
                    "name": "Claim Status",
                    "shortDescription": "Current state of claim processing",
                    "longDescription": "The status of a claim in the processing workflow. Valid values: pending (submitted but not reviewed), approved (accepted for payment), denied (rejected), in_review (under investigation)."
                },
                {
                    "name": "Claim Type",
                    "shortDescription": "Category of medical service",
                    "longDescription": "The type of healthcare service covered by the claim. Valid values: medical (doctor visits, procedures), prescription (medication), hospital (inpatient care)."
                },
                {
                    "name": "Diagnosis Code",
                    "shortDescription": "ICD-10 medical diagnosis code",
                    "longDescription": "Standardized ICD-10 code representing the medical diagnosis associated with the claim. Used for billing and statistical purposes."
                },
                {
                    "name": "Provider",
                    "shortDescription": "Healthcare service provider",
                    "longDescription": "The healthcare facility, hospital, clinic, or physician who provided the medical services for this claim."
                },
                {
                    "name": "Claim Amount",
                    "shortDescription": "Dollar amount requested for payment",
                    "longDescription": "The total amount in USD requested for reimbursement for the healthcare services provided. Must be a positive decimal value."
                },
                {
                    "name": "User ID",
                    "shortDescription": "Patient or adjuster identifier",
                    "longDescription": "Unique identifier for the user (patient or claims adjuster). Typically an email address. Used for row-level security to ensure users only see their own claims."
                },
                {
                    "name": "Patient Name",
                    "shortDescription": "Name of the patient receiving care",
                    "longDescription": "Full name of the patient who received the healthcare services covered by this claim."
                }
            ]

        print(f"Creating business glossary with {len(terms)} terms")
        created_terms = {}

        try:
            # Create glossary
            glossary_response = self.datazone.create_glossary(
                domainIdentifier=domain_id,
                name='Healthcare Insurance Glossary',
                description='Standard terminology for health lakehouse data',
                owningProjectIdentifier=domain_id  # Domain-level glossary
            )
            glossary_id = glossary_response['id']
            print(f"✅ Created glossary: {glossary_id}")

            # Create terms
            for term in terms:
                try:
                    term_response = self.datazone.create_glossary_term(
                        domainIdentifier=domain_id,
                        glossaryIdentifier=glossary_id,
                        name=term['name'],
                        shortDescription=term['shortDescription'],
                        longDescription=term.get('longDescription', term['shortDescription'])
                    )
                    term_id = term_response['id']
                    created_terms[term['name']] = term_id
                    print(f"   ✅ Created term: {term['name']}")
                except Exception as e:
                    print(f"   ⚠️  Could not create term '{term['name']}': {e}")

        except Exception as e:
            print(f"⚠️  Could not create glossary: {e}")
            print("   You may need to create this manually in the console")

        return created_terms

    def store_parameters_in_ssm(self, domain_id: str, project_id: str, 
                                env_id: Optional[str], source_id: Optional[str]):
        """
        Store DataZone configuration in SSM Parameter Store.
        
        Args:
            domain_id: DataZone domain ID
            project_id: Project ID
            env_id: Environment ID (optional)
            source_id: Data source ID (optional)
        """
        print("\n💾 Storing configuration in SSM Parameter Store...")
        
        # Store domain name
        self._store_ssm_parameter(
            '/app/lakehouse-agent/datazone-domain-name',
            self.domain_name,
            'DataZone domain name for lakehouse governance'
        )
        
        # Store domain ID
        self._store_ssm_parameter(
            '/app/lakehouse-agent/datazone-domain-id',
            domain_id,
            'DataZone domain ID for lakehouse governance'
        )
        
        # Store project ID
        self._store_ssm_parameter(
            '/app/lakehouse-agent/datazone-project-id',
            project_id,
            'DataZone project ID for health lakehouse'
        )
        
        # Store environment ID if available
        if env_id:
            self._store_ssm_parameter(
                '/app/lakehouse-agent/datazone-environment-id',
                env_id,
                'DataZone environment ID for analytics'
            )
        
        # Store data source ID if available
        if source_id:
            self._store_ssm_parameter(
                '/app/lakehouse-agent/datazone-data-source-id',
                source_id,
                'DataZone data source ID for Athena'
            )
        
        # Enable DataZone integration flag
        self._store_ssm_parameter(
            '/app/lakehouse-agent/enable-datazone-integration',
            'true',
            'Flag to enable DataZone integration'
        )

    def print_summary(self, domain_id: str, project_id: str, env_id: Optional[str],
                     source_id: Optional[str], glossary_terms: Dict[str, str]):
        """
        Print setup summary with values stored in SSM Parameter Store.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID
            env_id: Environment ID
            source_id: Data source ID
            glossary_terms: Dict of glossary term IDs
        """
        print("\n" + "=" * 70)
        print("SageMaker Unified Studio Setup Complete!")
        print("=" * 70)

        print("\n🔗 Access SageMaker Unified Studio:")
        print(f"https://console.aws.amazon.com/datazone/home?region={self.region}#/domains/{domain_id}")

        print("\n✅ Created Resources:")
        print(f"   • Domain Name: {self.domain_name}")
        print(f"   • Domain ID: {domain_id}")
        print(f"   • Project: {project_id}")
        if env_id:
            print(f"   • Environment: {env_id}")
        if source_id:
            print(f"   • Data Source: {source_id}")
        print(f"   • Glossary Terms: {len(glossary_terms)}")

        print("\n💾 SSM Parameters Stored:")
        print(f"   • /app/lakehouse-agent/datazone-domain-name")
        print(f"   • /app/lakehouse-agent/datazone-domain-id")
        print(f"   • /app/lakehouse-agent/datazone-project-id")
        if env_id:
            print(f"   • /app/lakehouse-agent/datazone-environment-id")
        if source_id:
            print(f"   • /app/lakehouse-agent/datazone-data-source-id")
        print(f"   • /app/lakehouse-agent/enable-datazone-integration")

        print("\n📚 Next Steps:")
        print("   1. Access SageMaker Unified Studio console to:")
        print("      - Configure data lineage")
        print("      - Set up access workflows")
        print("      - Explore the data catalog")
        print("   2. Continue with deployment (Phase 4+)")

        print("\n" + "=" * 70)


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description='Setup SageMaker Unified Studio (DataZone) for data governance'
    )
    parser.add_argument(
        '--domain-name',
        required=True,
        help='Name for the DataZone domain'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("SageMaker Unified Studio (DataZone) Setup")
    print("Lakehouse Agent - Data Governance Layer")
    print("=" * 70)

    # Confirm setup
    response = input("\nProceed with SageMaker Unified Studio setup? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Setup cancelled")
        sys.exit(0)

    # Initialize setup
    setup = SageMakerUnifiedStudioSetup(domain_name=args.domain_name)

    try:
        # Step 1: Create IAM role
        print("\n" + "=" * 70)
        print("Step 1: Creating IAM Role")
        print("=" * 70)
        role_arn = setup.create_domain_execution_role()

        # Step 2: Create domain
        print("\n" + "=" * 70)
        print("Step 2: Creating DataZone Domain")
        print("=" * 70)
        domain_id = setup.create_domain(role_arn)

        # Step 3: Create project
        print("\n" + "=" * 70)
        print("Step 3: Creating Project")
        print("=" * 70)
        project_id = setup.create_project(domain_id)

        # Step 4: Create environment profile
        print("\n" + "=" * 70)
        print("Step 4: Creating Environment Profile")
        print("=" * 70)
        profile_id = setup.create_environment_profile(domain_id, project_id)

        # Step 5: Create environment
        print("\n" + "=" * 70)
        print("Step 5: Creating Environment")
        print("=" * 70)
        env_id = setup.create_environment(domain_id, project_id, profile_id)

        # Step 6: Register data source
        print("\n" + "=" * 70)
        print("Step 6: Registering Athena Data Source")
        print("=" * 70)
        source_id = setup.register_athena_data_source(domain_id, project_id)

        # Step 7: Create business glossary
        print("\n" + "=" * 70)
        print("Step 7: Creating Business Glossary")
        print("=" * 70)
        glossary_terms = setup.create_business_glossary(domain_id)

        # Step 8: Store configuration in SSM Parameter Store
        print("\n" + "=" * 70)
        print("Step 8: Storing Configuration in SSM")
        print("=" * 70)
        setup.store_parameters_in_ssm(domain_id, project_id, env_id, source_id)

        # Print summary
        setup.print_summary(domain_id, project_id, env_id, source_id, glossary_terms)

    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
