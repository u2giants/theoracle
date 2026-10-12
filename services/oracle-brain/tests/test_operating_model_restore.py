import os
from scripts.oracle2.verify_workflow_restore import verify

def test_fresh_database_blob_restore_and_actual_sdk_reload(tmp_path,admin_url):
    result=verify(admin_url,tmp_path,os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'])
    assert result['passed'] and result['fresh_database_restored'] and result['source_database_removed']
    assert result['sdk_rebuilt_reloaded'] and result['blob_checksums_verified']>0
    assert result['synthetic'] and not result['business_accepted']
