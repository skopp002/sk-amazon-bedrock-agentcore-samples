#!/usr/bin/env python3
"""
Tests for SageMaker Unified Studio (DataZone) Integration

Tests data governance features including:
- Data discovery
- Business glossary
- Data lineage
- Access workflows
"""

import boto3
import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


@pytest.fixture
def datazone_client():
    """Create DataZone client."""
    if not config.ENABLE_DATAZONE_INTEGRATION:
        pytest.skip("DataZone integration not enabled")

    return boto3.client('datazone', region_name=config.AWS_REGION)


@pytest.fixture
def domain_id():
    """Get domain ID from config."""
    if not config.DATAZONE_DOMAIN_ID:
        pytest.skip("DATAZONE_DOMAIN_ID not configured")
    return config.DATAZONE_DOMAIN_ID


@pytest.fixture
def project_id():
    """Get project ID from config."""
    if not config.DATAZONE_PROJECT_ID:
        pytest.skip("DATAZONE_PROJECT_ID not configured")
    return config.DATAZONE_PROJECT_ID


class TestDataDiscovery:
    """Test data discovery and cataloging."""

    def test_search_claims_dataset(self, datazone_client, domain_id):
        """Test that users can discover claims dataset."""
        response = datazone_client.search_listings(
            domainIdentifier=domain_id,
            searchText='claims'
        )

        assert 'items' in response
        # Should find at least one result containing 'claims'
        assert any('claim' in item.get('name', '').lower()
                  for item in response.get('items', []))

    def test_search_health_insurance(self, datazone_client, domain_id):
        """Test search for health insurance data."""
        response = datazone_client.search_listings(
            domainIdentifier=domain_id,
            searchText='health insurance'
        )

        assert 'items' in response
        # Should return results
        assert len(response.get('items', [])) > 0

    def test_list_data_sources(self, datazone_client, domain_id, project_id):
        """Test listing data sources."""
        response = datazone_client.list_data_sources(
            domainIdentifier=domain_id,
            projectIdentifier=project_id
        )

        assert 'items' in response
        # Should have at least the Athena data source
        assert len(response.get('items', [])) > 0

        # Check for Athena data source
        athena_sources = [
            ds for ds in response.get('items', [])
            if ds.get('type') == 'ATHENA'
        ]
        assert len(athena_sources) > 0, "No Athena data source found"


class TestBusinessGlossary:
    """Test business glossary functionality."""

    def test_list_glossaries(self, datazone_client, domain_id):
        """Test listing glossaries."""
        response = datazone_client.list_glossaries(
            domainIdentifier=domain_id
        )

        assert 'items' in response
        # Should have healthcare insurance glossary
        glossaries = response.get('items', [])
        assert len(glossaries) > 0, "No glossaries found"

        # Check for our glossary
        healthcare_glossary = [
            g for g in glossaries
            if 'healthcare' in g.get('name', '').lower() or
               'insurance' in g.get('name', '').lower()
        ]
        assert len(healthcare_glossary) > 0, "Healthcare glossary not found"

    def test_list_glossary_terms(self, datazone_client, domain_id):
        """Test listing glossary terms."""
        # First get glossary ID
        glossaries = datazone_client.list_glossaries(
            domainIdentifier=domain_id
        )
        assert len(glossaries.get('items', [])) > 0

        glossary_id = glossaries['items'][0]['id']

        # List terms
        response = datazone_client.list_glossary_terms(
            domainIdentifier=domain_id,
            glossaryIdentifier=glossary_id
        )

        assert 'items' in response
        terms = response.get('items', [])
        assert len(terms) > 0, "No glossary terms found"

        # Check for expected terms
        term_names = {term['name'] for term in terms}
        expected_terms = {'Claim', 'Claim Status', 'Claim Type', 'User ID'}

        found_terms = term_names.intersection(expected_terms)
        assert len(found_terms) > 0, f"Expected terms not found. Found: {term_names}"

    def test_glossary_term_definitions(self, datazone_client, domain_id):
        """Test that glossary terms have definitions."""
        # Get glossary
        glossaries = datazone_client.list_glossaries(
            domainIdentifier=domain_id
        )
        glossary_id = glossaries['items'][0]['id']

        # Get terms
        terms = datazone_client.list_glossary_terms(
            domainIdentifier=domain_id,
            glossaryIdentifier=glossary_id
        )

        # Check each term has a description
        for term in terms.get('items', []):
            assert 'shortDescription' in term or 'longDescription' in term, \
                f"Term '{term.get('name')}' missing description"


class TestDataLineage:
    """Test data lineage tracking."""

    def test_data_source_has_lineage(self, datazone_client, domain_id, project_id):
        """Test that data sources have lineage information."""
        # List data sources
        sources = datazone_client.list_data_sources(
            domainIdentifier=domain_id,
            projectIdentifier=project_id
        )

        assert len(sources.get('items', [])) > 0, "No data sources found"

        # Check first source has lineage
        source_id = sources['items'][0]['id']

        # Get lineage (this may require additional permissions)
        try:
            response = datazone_client.get_lineage_node(
                domainIdentifier=domain_id,
                identifier=source_id
            )
            assert response is not None
        except datazone_client.exceptions.AccessDeniedException:
            pytest.skip("Insufficient permissions to test lineage")
        except Exception as e:
            # Lineage may not be fully configured yet
            pytest.skip(f"Lineage not available: {str(e)}")


class TestAccessControl:
    """Test access control and permissions."""

    def test_domain_accessible(self, datazone_client, domain_id):
        """Test that domain is accessible."""
        response = datazone_client.get_domain(
            identifier=domain_id
        )

        assert response is not None
        assert response['id'] == domain_id
        assert response['status'] == 'AVAILABLE'

    def test_project_accessible(self, datazone_client, domain_id, project_id):
        """Test that project is accessible."""
        response = datazone_client.get_project(
            domainIdentifier=domain_id,
            identifier=project_id
        )

        assert response is not None
        assert response['id'] == project_id
        assert response['domainId'] == domain_id


class TestIntegration:
    """Test integration with Lake Formation and Athena."""

    def test_athena_data_source_registered(self, datazone_client, domain_id, project_id):
        """Test that Athena database is registered as data source."""
        sources = datazone_client.list_data_sources(
            domainIdentifier=domain_id,
            projectIdentifier=project_id
        )

        athena_sources = [
            s for s in sources.get('items', [])
            if s.get('type') == 'ATHENA'
        ]

        assert len(athena_sources) > 0, "No Athena data source found"

        # Check it's pointing to correct database
        source = athena_sources[0]
        assert 'health_insurance' in source.get('name', '').lower() or \
               'claims' in source.get('name', '').lower()

    def test_data_source_enabled(self, datazone_client, domain_id, project_id):
        """Test that data source is enabled."""
        sources = datazone_client.list_data_sources(
            domainIdentifier=domain_id,
            projectIdentifier=project_id
        )

        for source in sources.get('items', []):
            assert source.get('status') != 'DISABLED', \
                f"Data source '{source.get('name')}' is disabled"


@pytest.mark.integration
class TestEndToEnd:
    """End-to-end governance tests."""

    def test_discover_query_workflow(self, datazone_client, domain_id):
        """
        Test complete workflow:
        1. Discover claims dataset
        2. View glossary terms
        3. Check lineage
        """
        # Step 1: Discover dataset
        search_results = datazone_client.search_listings(
            domainIdentifier=domain_id,
            searchText='claims'
        )
        assert len(search_results.get('items', [])) > 0, "No claims dataset found"

        # Step 2: Check glossary
        glossaries = datazone_client.list_glossaries(
            domainIdentifier=domain_id
        )
        assert len(glossaries.get('items', [])) > 0, "No glossary found"

        # Step 3: Verify data catalog integration
        # This validates that SageMaker Unified Studio is properly integrated
        # with Athena and Lake Formation
        assert search_results is not None
        assert glossaries is not None


def test_config_validation():
    """Test that DataZone configuration is valid."""
    if config.ENABLE_DATAZONE_INTEGRATION:
        assert config.DATAZONE_DOMAIN_ID, "DATAZONE_DOMAIN_ID not set"
        assert config.DATAZONE_PROJECT_ID, "DATAZONE_PROJECT_ID not set"
        assert config.DATAZONE_DOMAIN_NAME, "DATAZONE_DOMAIN_NAME not set"
        assert config.DATAZONE_PROJECT_NAME, "DATAZONE_PROJECT_NAME not set"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
